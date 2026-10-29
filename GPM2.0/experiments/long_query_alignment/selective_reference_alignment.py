#!/usr/bin/env python3
"""Branch-only selective reference mapping under a long-CIGAR hypothesis.

Developer harness, not a replacement Server entry point. Default CLI is plan
only. No production result.paf, completion checkpoint or customer job is written.
Ordinary records keep -c mapping; only records longer than the encoded operation
limit enter the existing checked-window/whole-query-guidance prototype.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import guided_alignment as ga
import windowed_alignment as wa

DEFAULT_INDEX_BASES = 8_000_000_000
MAX_PAF_LINE = 32*1024**2
CIGAR = re.compile(r"([1-9][0-9]*)([M=XID])")


def partition_records(records, *, limit=wa.LIMIT):
    """Length is a risk-routing rule, NOT proof of an overflowing alignment."""
    if type(limit) is not int or limit < 1 or limit > wa.LIMIT:
        raise wa.ExperimentError("invalid CIGAR routing boundary")
    ordinary, risk = [], []
    for name, row in records.items():
        length = row.get("length")
        if type(length) is not int or not 0 < length <= wa.INT32_MAX:
            raise wa.ExperimentError("invalid source record length")
        (risk if length > limit else ordinary).append(name)
    if not ordinary and not risk:
        raise wa.ExperimentError("no query records")
    return ordinary, risk


def split_record_files(source, records, ordinary, risk, root, expected_sha256):
    """Copy complete raw records, preserving case, headers, wrapping and order.

    Never split long records here. Windowing is performed by the existing guided
    prototype on the risk-only file; every source record belongs to one route.
    """
    routes = {name:"ordinary" for name in ordinary}
    if set(ordinary) & set(risk) or set(ordinary) | set(risk) != set(records):
        raise wa.ExperimentError("query routes overlap or omit records")
    routes.update({name:"risk" for name in risk})
    paths = {key:root/(key+".fa") for key,names in (("ordinary",ordinary),("risk",risk)) if names}
    digest, seen = hashlib.sha256(), []
    with ExitStack() as stack:
        outputs = {key:stack.enter_context(path.open("xb")) for key,path in paths.items()}
        stream = stack.enter_context(Path(source).open("rb"))
        writer, line_start = None, True
        while raw := stream.readline(wa.CHUNK):
            digest.update(raw)
            if line_start and raw.startswith(b">"):
                if len(raw) >= wa.CHUNK and not raw.endswith(b"\n"):
                    raise wa.ExperimentError("oversized FASTA header during routing")
                name = raw[1:].split()[0].decode("ascii")
                if name not in routes:
                    raise wa.ExperimentError("query identity changed during routing")
                seen.append(name)
                writer = outputs[routes[name]]
            line_start = raw.endswith(b"\n")
            if writer is not None:
                writer.write(raw)
            elif raw.strip():
                raise wa.ExperimentError("sequence before header during routing")
    if seen != list(records) or digest.hexdigest() != expected_sha256:
        raise wa.ExperimentError("query bytes/order changed during routing")
    return paths


def validate_row(raw, queries, targets, allowed, route):
    """Validate ownership/spans without replacing ordinary CIGAR/tags/confidence."""
    if len(raw) > MAX_PAF_LINE or not raw.endswith(b"\n"):
        raise wa.ExperimentError("oversized or incomplete candidate PAF line")
    fields = raw.rstrip(b"\r\n").decode("ascii").split("\t")
    if len(fields) < 12 or fields[0] not in allowed or fields[5] not in targets:
        raise wa.ExperimentError("PAF record assigned to wrong query route or unknown target")
    try:
        qlen,qs,qe = map(int,fields[1:4])
        tlen,ts,te,matches,block,mapq = map(int,fields[6:12])
    except ValueError as exc:
        raise wa.ExperimentError("noninteger PAF core column") from exc
    if (qlen != queries[fields[0]]["length"] or tlen != targets[fields[5]]["length"] or
            fields[4] not in ("+","-") or not 0 <= qs < qe <= qlen or
            not 0 <= ts < te <= tlen or not 0 <= matches <= block or block <= 0 or not 0 <= mapq <= 255):
        raise wa.ExperimentError("PAF length/coordinates/counts/confidence inconsistent with source")
    tags = [tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")]
    if len(tags) != 1:
        raise wa.ExperimentError("exactly one CIGAR required in routed candidate")
    ops = [(int(size),op) for size,op in CIGAR.findall(tags[0])]
    if (not ops or "".join(f"{n}{op}" for n,op in ops) != tags[0] or any(n>wa.LIMIT for n,_ in ops) or
            sum(n for n,op in ops if op in "M=XI") != qe-qs or
            sum(n for n,op in ops if op in "M=XD") != te-ts):
        raise wa.ExperimentError("CIGAR operation or consumption outside supported bounds")
    if route == "risk" and (mapq != 255 or any(tag[:3] in ("AS:","ms:","s1:","s2:","tp:") for tag in fields[12:])):
        raise wa.ExperimentError("window candidate must not claim restored ranking/confidence")
    return fields[0]


def combine_candidates(root, query_records, target_records, ordinary, risk, route_pafs):
    """Disk-backed routing in original query order; retain rows, not just unions.

    Do not silently deduplicate alternative placements or mark an unaligned record
    covered. All final output remains experimental, including unchanged short rows.
    """
    shards = root/"rows_by_query"
    shards.mkdir()
    shard_paths = {name:shards/f"{i:08d}.paf" for i,name in enumerate(query_records)}
    counts = {name:0 for name in query_records}
    for route,names in (("ordinary",ordinary),("risk",risk)):
        if not names:
            continue
        allowed = set(names)
        with route_pafs[route].open("rb") as inp:
            while raw := inp.readline(MAX_PAF_LINE+1):
                name = validate_row(raw,query_records,target_records,allowed,route)
                with shard_paths[name].open("ab") as out:
                    out.write(raw)
                counts[name] += 1
    pending = root/"reference.candidate.pending.paf"
    with pending.open("xb") as out:
        for name in query_records:
            if counts[name]:
                with shard_paths[name].open("rb") as inp:
                    shutil.copyfileobj(inp,out,length=wa.CHUNK)
    return pending, {"rows_by_query":counts, "queries_without_alignment":[name for name,n in counts.items() if not n],
                     "row_bytes_preserved":True, "output_grouped_in_original_query_order":True,
                     "full_query_coverage_claimed":False}


def experiment(args):
    root = args.out.resolve()
    if not root.parent.is_dir() or root.exists() or args.out.is_symlink():
        raise wa.ExperimentError("fresh output directory under an existing parent required")
    for parent in (root.parent,*root.parent.parents):
        if (parent/".prepare_lib").exists() or (parent/"run_all.sh").exists():
            raise wa.ExperimentError("branch experiment must be outside a prepared Server workspace")
    target_path, query_path = args.target.resolve(),args.query.resolve()
    if target_path == query_path:
        raise wa.ExperimentError("initial reference alignment only; self-alignment is unsupported")
    if args.threads < 1 or args.timeout < 1 or args.memory_gib < 0:
        raise wa.ExperimentError("invalid experiment resource bounds")
    mm = shutil.which(args.minimap2)
    if not mm:
        raise wa.ExperimentError("minimap2 not found")
    mm = str(Path(mm).resolve())
    root.mkdir(mode=0o700)
    report = {"schema":1,"status":"running","production_ready":False,"customer_validated":False,
              "hypothesis":"single long CIGAR operation overflow; customer mechanism unconfirmed",
              "scope":"selective initial-reference experiment only","tests_deferred":True,
              "harness_sha256":wa.sha256(Path(__file__)), "server_result_published":False,
              "promotion_blockers":["candidate retention and post-DP ranking", "global MAPQ",
                                    "customer reproduction", "downstream scientific acceptance"]}
    wa.write_json(root/"selective-reference.json",report)
    stores = []
    try:
        target = wa.FastaStore(target_path,root/"target.bases"); stores.append(target)
        query = wa.FastaStore(query_path,root/"query.bases"); stores.append(query)
        tool_hash = wa.sha256(Path(mm))
        version = subprocess.check_output([mm,"--version"],text=True,timeout=5).strip()
        report.update(tool={"path":mm,"sha256":tool_hash,"version":version},
                      reference=target.identity, query=query.identity,
                      helper_sha256={Path(module.__file__).name:wa.sha256(Path(module.__file__)) for module in (ga,wa)})
        if version != "2.31-r1302":
            raise wa.ExperimentError("this branch experiment is pinned to customer minimap2 2.31-r1302")
        ordinary,risk = partition_records(query.records)
        report["routing"] = {"ordinary":ordinary,"risk":risk,"length_threshold":wa.LIMIT,
                             "risk_is_not_root_cause_confirmation":True}
        if risk and sum(row["length"] for row in target.records.values()) > DEFAULT_INDEX_BASES:
            report["promotion_blockers"].append("customer multipart-index context not supported by current guidance")
            raise wa.ExperimentError("multipart-reference context unsupported: do not silently replace it by a larger single index")
        subsets = split_record_files(query_path,query.records,ordinary,risk,root,query.identity["sha256"]) if risk else {"ordinary":query_path}
        report["subset_sha256"] = {key:wa.sha256(path) for key,path in subsets.items()}
        pafs = {}
        if ordinary:
            pafs["ordinary"] = root/"ordinary.paf"
            wa.run_command([mm,"-c","-x","asm10","-t",str(args.threads),"-o",str(pafs["ordinary"]),
                            str(target_path),str(subsets["ordinary"])],root,"ordinary",args.timeout,args.memory_gib)
        if risk:
            options = argparse.Namespace(target=target_path, query=subsets["risk"], out=root/"risk-windows", minimap2=mm,
                preset="asm10", core_bases=50_000_000, context_bases=100_000, guide_slack=1000,
                threads=args.threads,timeout=args.timeout,memory_gib=args.memory_gib,require_full_query_coverage=False)
            report["risk_experiment"] = ga.experiment(options)
            pafs["risk"] = options.out/"guided.experimental.paf"
        pending,report["combination"] = combine_candidates(root,query.records,target.records,ordinary,risk,pafs)
        if not all(store.unchanged() for store in stores) or wa.sha256(Path(mm)) != tool_hash:
            raise wa.ExperimentError("input/tool changed during selective experiment")
        output = root/"reference.candidate.experimental.paf"
        pending.rename(output)
        report.update(status="experimental_candidate_only",output_sha256=wa.sha256(output),
                      original_inputs_unchanged=True,ordinary_rows_keep_original_tags=True,
                      risk_confidence="unknown; never promoted from window MAPQ")
    except BaseException as exc:
        report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        for store in stores:
            store.close()
        wa.write_json(root/"selective-reference.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",type=Path,required=True)
    parser.add_argument("--query",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--minimap2",default="minimap2")
    parser.add_argument("--threads",type=int,default=2)
    parser.add_argument("--timeout",type=int,default=21600)
    parser.add_argument("--memory-gib",type=int,default=0,help="developer experiment child address-space cap; 0 keeps inherited limit")
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","production_ready":False,"query":str(args.query),
                          "target":str(args.target),"output":str(args.out),"core_bases":50_000_000,
                          "context_each_side":100_000,"query_length_trigger":wa.LIMIT,
                          "customer_run_sh_integration":False,"no_files_or_commands_started":True},indent=2))
        return 0
    try:
        report = experiment(args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"refused_or_failed","error":str(exc),"production_ready":False}))
        return 2
    print(json.dumps({"status":report["status"],"production_ready":False,
                      "promotion_blockers":report["promotion_blockers"]},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
