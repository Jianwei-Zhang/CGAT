#!/usr/bin/env python3
"""Bounded same-span window-size probe on an ORIGINAL reference index part.

This measures mapping/owned query coverage, not whole-query chain recovery or
final confidence. Reuse a completed pilot's original index, never shrink the
reference or rebuild a different -I layout. No production recommendation emitted.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import signal
import subprocess
import time

import adaptive_screening as policy
import benchmark_adaptive_screening as runner
import benchmark_ordinary_existing as existing
import benchmark_ordinary_partitions as parts
import minimap_index_context as mic
import ordinary_batch_performance as perf


def window_plan(length, start, end, core, context=100_000):
    if not 0 <= start < end <= length or not 0 <= context < core:
        raise ValueError("invalid probe span/window")
    return [{"name": f"w{i:04d}", "core_start": a, "core_end": min(a + core, end),
             "query_start": max(0, a - context), "query_end": min(length, min(a + core, end) + context)}
            for i, a in enumerate(range(start, end, core))]


def extract_span(path, start, end):
    """Called after complete single-record catalogue/content verification."""
    result = bytearray()
    with path.open("rb") as stream:
        header = stream.readline(1024**2)
        if not header.startswith(b">") or not header.endswith(b"\n"):
            raise ValueError("bounded single-record FASTA header required")
        position = 0
        while position < end:
            raw = stream.readline(1024**2)
            if not raw:
                break
            sequence = raw.rstrip(b"\r\n")
            if sequence.translate(None, existing.ALPHABET):
                raise ValueError("invalid probe sequence")
            stop = position + len(sequence)
            if stop > start:
                result.extend(sequence[max(0, start-position):min(len(sequence), end-position)])
            position = stop
    if len(result) != end - start:
        raise ValueError("probe span was not completely read")
    return bytes(result)


def owned_coverage(path, windows, start, end):
    by_name = {w["name"]: w for w in windows}
    spans, targets = [], defaultdict(list)
    strands = defaultdict(lambda: defaultdict(list))
    with path.open() as stream:
        for line in stream:
            f = line.rstrip("\n").split("\t")
            w = by_name[f[0]]
            a = max(w["core_start"], w["query_start"] + int(f[2]))
            b = min(w["core_end"], w["query_start"] + int(f[3]))
            if a < b:
                spans.append((a-start, b-start)); targets[f[5]].append((a-start, b-start))
                strands[f[5]][f[4]].append((a-start, b-start))
    return {"probe": {"length": end-start, "covered": policy.union_length(spans),
                      "targets": {t: policy.union_length(s) for t, s in targets.items()},
                      "target_strands": {t: {strand: policy.union_length(s) for strand, s in values.items()}
                                         for t, values in strands.items()}}}


def execute(args):
    started = time.monotonic()
    receipt = json.loads(args.index_receipt.read_text())
    query_receipt = json.loads(args.query_subset.read_text())
    if not receipt.get("input_content_unchanged") or receipt["index"]["outcome"] != "completed":
        raise ValueError("completed, source-verified original index receipt required")
    if query_receipt.get("status") != "complete" or len(query_receipt["records"]) != 1:
        raise ValueError("one complete original query required")
    mm = shutil.which(args.minimap2)
    if not mm or perf.sha256(mm) != receipt["code_sha256"]["mapper"]:
        raise ValueError("mapper differs from original-index build")
    if subprocess.check_output([mm,"--version"],text=True,timeout=5).strip() != perf.VERSION:
        raise ValueError("pinned mapper required")
    query = existing.catalog(Path(query_receipt["path"]))
    if (len(query["records"]) != 1 or query["records"][0]["name"] != query_receipt["records"][0]["name"]
            or query["records"][0]["length"] != query_receipt["records"][0]["length"]
            or query["sha256"] != query_receipt["output_sha256"]):
        raise ValueError("query content differs from subset receipt")
    index = args.index_receipt.parent / "target.default.mmi"
    if perf.sha256(index) != receipt["index_sha256"]:
        raise ValueError("original index changed")
    target_records = {r["name"]: {"length": r["length"]} for r in receipt["sources"]["reference"]["records"]}
    length = query["records"][0]["length"]
    end = args.start + args.span_bases
    plans = {size: window_plan(length, args.start, end, size) for size in (50_000_000,10_000_000,5_000_000)}
    left = min(w["query_start"] for plan in plans.values() for w in plan)
    right = max(w["query_end"] for plan in plans.values() for w in plan)
    sequence = extract_span(Path(query["source"]), left, right)
    root = args.out.resolve(); root.mkdir(parents=True,exist_ok=False)
    r = {"status":"running", "scope":"window_mapping_only_not_whole_query_recovery",
         "production_approved":False,"final_confidence_restored":False,"query":query,
         "original_span":{"start":args.start,"end":end},"fraction":args.fraction,
         "runs":[],"comparisons":[],"index_receipt_sha256":perf.sha256(args.index_receipt)}
    guarded={"harness":__file__, **{m.__name__:m.__file__ for m in (policy,runner,existing,parts,mic,perf,mic.wa)}}
    r["code_sha256"]={name:perf.sha256(path) for name,path in guarded.items()}
    report=root/"windows.json"; runner.atomic_json(report,r)
    profiles={}
    try:
        layout=mic.copy_parts(index,root/"original-index-parts",target_records,reuse_single_part=True)
        if not 0 <= args.part < len(layout["parts"]):
            raise ValueError("original part index out of range")
        part=layout["parts"][args.part];r["original_part"]=part
        empty=root/"empty.fa";empty.write_bytes(b"")
        flags=[] if args.fraction=="default" else ["-f",args.fraction]
        r["preparation_seconds"]=time.monotonic()-started
        deadline=time.monotonic()+args.total_seconds
        r["threshold_pass"]=runner.run_bounded([mm,"-x","asm10",*flags,"-t",str(args.threads),
            "-o",str(root/"empty.paf"),part["path"],str(empty)],root,"threshold",min(120,args.case_seconds),args.memory_mib)
        if r["threshold_pass"]["outcome"]!="completed":
            r["status"]="threshold_incomplete";return r
        mids=parts.thresholds(root/"threshold.stderr")
        if len(mids)!=1: raise ValueError("single original-part threshold required")
        mid=mids[0];r["mid_occ"]=mid
        for core,windows in plans.items():
            remaining=deadline-time.monotonic()
            if remaining<=0:r["status"]="budget_exhausted";break
            stem=f"core-{core}";fasta=root/(stem+".fa");out=root/(stem+".paf")
            with fasta.open("xb") as stream:
                for w in windows:
                    stream.write((">"+w["name"]+"\n").encode())
                    stream.write(sequence[w["query_start"]-left:w["query_end"]-left]);stream.write(b"\n")
            command=[mm,"-c","--eqx","-x","asm10","-f",str(mid),"-P","-t",str(args.threads),
                     "-o",str(out),part["path"],str(fasta)]
            run=runner.run_bounded(command,root,stem,min(args.case_seconds,remaining),args.memory_mib)
            run.update(core_bases=core,windows=windows,window_fasta_sha256=perf.sha256(fasta))
            r["runs"].append(run)
            if run["outcome"]=="completed":
                try:
                    if out.stat().st_size>64*1024**2:raise ValueError("PAF exceeds bounded audit size")
                    qrows=[{"name":w["name"],"length":w["query_end"]-w["query_start"]} for w in windows]
                    run["paf_rows"]=parts.validate_paf(out,qrows,part["records"],allow_empty=True)
                    log=perf.parse_log((root/(stem+".stderr")).read_text())
                    if len(log["parts"])!=1 or sum(b["records"] for b in log["parts"][0]["batches"])!=len(windows):
                        raise ValueError("incomplete window mapping")
                    if parts.thresholds(root/(stem+".stderr"))!=[mid]:raise ValueError("window threshold changed")
                    profiles[core]=owned_coverage(out,windows,args.start,end)
                    run.update(paf_sha256=perf.sha256(out),owned_coverage=profiles[core])
                except (OSError,ValueError,KeyError) as exc:run.update(outcome="audit_failure",error=str(exc))
            runner.atomic_json(report,r)
            print(json.dumps({k:run.get(k) for k in ["core_bases","outcome","wall_seconds","paf_rows"]}),flush=True)
        baseline=r["runs"][0] if r["runs"] else None
        for run in r["runs"][1:]:
            comparison={"core_bases":run["core_bases"],"production_approved":False}
            if baseline["outcome"]==run["outcome"]=="completed":
                comparison.update(mapping_speedup=baseline["wall_seconds"]/run["wall_seconds"],
                    coverage_risks=policy.assess_loss(profiles[50_000_000],profiles[run["core_bases"]],require_consumer=False))
            elif baseline["outcome"]=="timeout" and run["outcome"]=="completed":
                comparison.update(mapping_speedup_lower_bound=min(baseline["wall_seconds"],baseline["wall_budget_seconds"])/run["wall_seconds"],quality_baseline_available=False)
            r["comparisons"].append(comparison)
        if perf.sha256(index)!=receipt["index_sha256"] or perf.sha256(query["source"])!=query["sha256"]:
            raise ValueError("input/index changed during probe")
        if perf.sha256(mm)!=receipt["code_sha256"]["mapper"]:raise ValueError("mapper changed")
        if any(perf.sha256(path)!=r["code_sha256"][name] for name,path in guarded.items()):
            raise ValueError("probe implementation changed")
        if r["status"]=="running":r["status"]="diagnostic_complete_not_recovery_acceptance"
    except BaseException as exc:
        r.update(status="failed",error=f"{type(exc).__name__}: {exc}");raise
    finally:
        r["total_elapsed_seconds"]=time.monotonic()-started
        runner.atomic_json(report,r)
    return r


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["index-receipt","query-subset","out"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--minimap2",default="minimap2")
    p.add_argument("--part",type=int,default=0)
    p.add_argument("--start",type=int,default=0)
    p.add_argument("--span-bases",type=int,default=50_000_000)
    p.add_argument("--fraction",choices=["default","0.005","0.01"],default="default")
    p.add_argument("--threads",type=int,default=16)
    p.add_argument("--memory-mib",type=int,default=131072)
    p.add_argument("--case-seconds",type=int,default=600)
    p.add_argument("--total-seconds",type=int,default=2000)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args(argv)
    if not (a.start>=0 and a.part>=0 and 1<=a.span_bases<=50_000_000 and 1<=a.threads<=64
            and 256<=a.memory_mib<=524288 and 1<=a.case_seconds<=1200 and a.case_seconds<=a.total_seconds<=7200):
        p.error("bounded span and resources required")
    if not a.execute:
        print(json.dumps({"execute":False,"span_bases":a.span_bases,"cores":[50_000_000,10_000_000,5_000_000]}));return
    def interrupted(number,frame):raise KeyboardInterrupt(f"cancelled by signal {number}")
    previous={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGHUP)}
    try:
        for s in previous:signal.signal(s,interrupted)
        execute(a)
    finally:
        for s,handler in previous.items():signal.signal(s,handler)


if __name__=="__main__":main()
