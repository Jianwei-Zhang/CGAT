#!/usr/bin/env python3
"""Persistent, opt-in native-DP/control comparisons; PLAN ONLY by default.

Maintainer final-validation entry, not customer configuration or Server admission.
Never compiles/downloads/submits jobs or edits installed minimap2/workspaces.
Preserve ALL failed/refused case evidence, not merely an exit code or temp test.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from itertools import zip_longest
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True

import guided_alignment as ga
import minimap_index_context as mic
import native_chain_state as nst
import native_controls as controls
import native_evaluation as ne
import selective_reference_alignment as sr
import server_alignment as sa
import windowed_alignment as wa

MAX_DIFFERENCES = 100


@contextmanager
def cancellation_guard():
    state = {"signal":None}
    previous = {}
    def interrupt(number,frame):
        state["signal"] = number
        raise KeyboardInterrupt(f"native control validation cancelled by signal {number}")
    try:
        for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            previous[number] = signal.signal(number,interrupt)
        yield state
    finally:
        for number,handler in previous.items():
            signal.signal(number,handler)


def sources():
    root = Path(__file__).resolve().parent
    names = [*sa.RUNTIME_FILES,Path(__file__).name,Path(controls.__file__).name,"audit_post_dp.py","compare_small_fixtures.py"]
    return {name:wa.sha256(root/name) for name in sorted(set(names))}


def compare_signatures(baseline,candidate):
    differences = []
    count = 0
    for index,(left,right) in enumerate(zip_longest(baseline,candidate),1):
        changed = {}
        if left is None or right is None:
            changed["candidate_presence"] = {"baseline":left,"candidate":right}
        else:
            if any(len(row)!=2 or len(row[0])!=len(ne.CORE_FIELDS) or len(row[1])!=len(ne.COMPARISON_TAGS)
                   for row in (left,right)):
                raise wa.ExperimentError("native comparison signature omitted required core/tag fields")
            for name,a,b in zip(ne.CORE_FIELDS,left[0],right[0]):
                if a!=b:
                    changed[name] = {"baseline":a,"candidate":b}
            for name,a,b in zip(ne.COMPARISON_TAGS,left[1],right[1]):
                if a!=b:
                    changed["tag:"+name] = {"baseline":a,"candidate":b}
        if changed:
            count += 1
            if len(differences)<MAX_DIFFERENCES:
                differences.append({"ordered_row":index,"fields":changed})
    return {"equal":not count,"baseline_rows":len(baseline),"candidate_rows":len(candidate),
            "different_rows":count,"differences":differences,"reported_difference_limit":MAX_DIFFERENCES,
            "additional_differences_omitted":count-len(differences),"comparison_is_ordered":True,
            "core_fields":list(ne.CORE_FIELDS),"compared_tags":list(ne.COMPARISON_TAGS),"AS_compared":False,
            "scope":"ordered_core_and_known_native_tags_only_not_AS_or_global_DP_equivalence"}


def run_case(name,targets,query_bases,root,args,mm,bundle,tool_hash):
    root.mkdir()
    target,query,index,baseline = root/"ref.fa",root/"query.fa",root/"original.mmi",root/"baseline.paf"
    target.write_bytes(b"".join(b">"+key.encode()+b"\n"+sequence+b"\n" for key,sequence in targets.items()))
    query.write_bytes(b">query\n"+query_bases+b"\n")
    input_hashes = {p.name:wa.sha256(p) for p in (target,query)}
    record = {"case":name,"status":"running","production_ready":False,"customer_validated":False,
              "source_input_sha256":input_hashes,"forced_small_bridge_not_actual_assertion_recovery":True,
              "AS_reconstructed":False,"whole_query_dp_equivalence_certified":False}
    try:
        wa.run_command([mm,"-x","asm10","-t","1","-d",str(index),str(target)],root,"index",args.timeout,args.memory_gib)
        catalog = mic.read_catalog(index,{key:{"length":len(bases)} for key,bases in targets.items()})
        if len(catalog["parts"])!=1:
            raise wa.ExperimentError("small native controls unexpectedly exceed one DEFAULT index part; no forced -I override permitted")
        wa.run_command([mm,"-c","--eqx","-x","asm10","-t","1","-o",str(baseline),str(index),str(query)],
                       root,"baseline",args.timeout,args.memory_gib)
        context = {"part_index":0,"path":str(index),"sha256":wa.sha256(index),"preset":"asm10",
            "tool_sha256":tool_hash,"reference_sha256":input_hashes[target.name],
            "mid_occ":sr.read_shared_mid_occ(root/"baseline.stderr",1),
            "records":[{"name":key,"length":len(bases)} for key,bases in targets.items()]}
        wa.write_json(root/"index-context.json",context)
        options = argparse.Namespace(target=target,query=query,out=root/"recovery",minimap2=mm,preset="asm10",
            core_bases=50000,context_bases=4000,guide_slack=1000,threads=args.threads,timeout=args.timeout,
            memory_gib=args.memory_gib,require_full_query_coverage=False,index_context=context,
            allow_empty_index_part=False,window_candidate_policy="all_chains_pool",recover_path_scores=True,
            native_state_bundle=Path(bundle["manifest_path"]).parent)
        recovered = ga.experiment(options)
        native = recovered["native_recovery"]
        public,private = options.out/"guided.experimental.paf",Path(native["native_evaluated_paf"])
        validator = lambda raw:sr.validate_row(raw,{"query":{"length":len(query_bases)}},
            {key:{"length":len(bases)} for key,bases in targets.items()},{"query"},"risk")
        pair = ne.validate_pair(public,private,public_sha256=recovered["output_sha256"],
                               evaluated_sha256=native["native_evaluated_sha256"],validator=validator)
        if (not native["selection"].get("native_decisions_applied")
                or native.get("raw_overlap_consistency_checked") is not True
                or native.get("public_confidence_withheld") is not True):
            raise wa.ExperimentError("native comparison did not actually execute the state/selection/raw-overlap bridge")
        comparison = compare_signatures(ne.comparison_signature(baseline),ne.comparison_signature(private))
        record.update(status="equal_on_compared_contract" if comparison["equal"] else "different",
            comparison=comparison,pair=pair,baseline_sha256=wa.sha256(baseline),
            native_evaluated_paf=str(private),native_evaluated_sha256=wa.sha256(private),
            guidance_sha256=wa.sha256(options.out/"guidance.json"),
            native_recovery_sha256=wa.sha256(options.out/"native-recovery/native-recovery.json"))
        if input_hashes!={p.name:wa.sha256(p) for p in (target,query)}:
            raise wa.ExperimentError("native control inputs changed during comparison")
    except BaseException as exc:
        record.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root/"comparison.json",record)
    return record


def summarize(records,requested):
    complete = [r["case"] for r in records]
    requested_equal = (complete==list(requested) and bool(records)
                       and all(r["status"]=="equal_on_compared_contract" and r["comparison"]["equal"] for r in records))
    full_covered = complete==list(controls.CASE_NAMES)
    return {"requested_cases_equal":requested_equal,"full_native_matrix_covered":full_covered,
            "full_native_matrix_equal":full_covered and requested_equal,
            "native_confidence_promoted":False,"production_ready":False,"customer_validated":False,
            "whole_query_dp_equivalence_certified":False}


def experiment(args):
    root = args.out.resolve()
    if not root.parent.is_dir() or root.exists() or args.out.is_symlink():
        raise wa.ExperimentError("native controls require a fresh output directory under an existing parent")
    for parent in (root.parent,*root.parent.parents):
        if (parent/".prepare_lib").exists() or (parent/"run_all.sh").exists():
            raise wa.ExperimentError("native controls must remain outside prepared/customer workspaces")
    if args.threads<1 or args.timeout<1 or args.memory_gib<0:
        raise wa.ExperimentError("invalid native-control resource bounds")
    selected = args.case or list(controls.CASE_NAMES)
    if len(selected)!=len(set(selected)) or not set(selected)<=set(controls.CASE_NAMES):
        raise wa.ExperimentError("native controls require unique known case names; no silent omission")
    requested = [name for name in controls.CASE_NAMES if name in selected]
    mm = shutil.which(args.minimap2)
    if not mm:
        raise wa.ExperimentError("unchanged minimap2 is unavailable")
    mm = str(Path(mm).resolve())
    tool_hash = wa.sha256(Path(mm))
    if subprocess.check_output([mm,"--version"],text=True,timeout=10).strip()!="2.31-r1302":
        raise wa.ExperimentError("native controls require the pinned unchanged minimap2 2.31-r1302")
    bundle = nst.validate_bundle(args.native_state_bundle)
    before = sources()
    root.mkdir(mode=0o700)
    (root/"cases").mkdir()
    report = {"schema":1,"status":"running","production_ready":False,"customer_validated":False,
        "tool":{"path":mm,"sha256":tool_hash,"version":"2.31-r1302"},"helper":bundle,"sources_sha256":before,
        "required_native_cases":list(controls.CASE_NAMES),"requested_cases":requested,"cases":[],
        "scope":"persistent_forced_small_native_bridge_controls_only","actual_assertion_recovery_tested":False,
        "AS_compared":False,"native_confidence_promoted":False,"whole_query_dp_equivalence_certified":False,
        "long_query_over_28bit_tested":False,"default_multipart_context_executed":False}
    wa.write_json(root/"native-controls.json",report)
    def unchanged():
        if (sources()!=before or wa.sha256(Path(mm))!=tool_hash
                or wa.sha256(Path(bundle["path"]))!=bundle["sha256"]
                or wa.sha256(Path(bundle["manifest_path"]))!=bundle["manifest_sha256"]):
            raise wa.ExperimentError("native comparison source/tool/helper changed; attribution invalidated")
    try:
        fixtures = controls.fixtures()
        if tuple(row[0] for row in fixtures)!=controls.CASE_NAMES:
            raise wa.ExperimentError("native matrix registry differs from its actual fixtures")
        with cancellation_guard() as cancelled:
            for name,targets,query_bases in fixtures:
                if name not in requested:
                    continue
                unchanged()
                try:
                    record = run_case(name,targets,query_bases,root/"cases"/name,args,mm,bundle,tool_hash)
                except Exception:
                    path = root/"cases"/name/"comparison.json"
                    if not path.is_file():
                        raise
                    record = json.loads(path.read_text())
                report["cases"].append(record)
                wa.write_json(root/"native-controls.json",report)
                print(json.dumps({"case":name,"status":record["status"],"evidence":str(root/"cases"/name)}),flush=True)
                if cancelled["signal"] is not None:
                    raise KeyboardInterrupt(f"native matrix cancelled by signal {cancelled['signal']}")
                unchanged()
        report.update(status="completed_comparisons_not_production_acceptance",**summarize(report["cases"],requested))
    except BaseException as exc:
        report.update(status="interrupted" if isinstance(exc,KeyboardInterrupt) else "refused_or_failed",
                      error=f"{type(exc).__name__}: {exc}",requested_cases_equal=False,full_native_matrix_equal=False)
        raise
    finally:
        wa.write_json(root/"native-controls.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--minimap2",default="minimap2")
    parser.add_argument("--native-state-bundle",type=Path,default=None)
    parser.add_argument("--case",action="append",choices=controls.CASE_NAMES)
    parser.add_argument("--threads",type=int,default=2)
    parser.add_argument("--timeout",type=int,default=180)
    parser.add_argument("--memory-gib",type=int,default=0)
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","production_ready":False,"output":str(args.out),
            "required_native_cases":list(controls.CASE_NAMES),"requested_cases":args.case or list(controls.CASE_NAMES),
            "prebuilt_pinned_companion_required":True,"no_files_or_programs_started":True,
            "actual_assertion_recovery_tested":False,"native_confidence_promoted":False},indent=2))
        return 0
    try:
        report = experiment(args)
    except KeyboardInterrupt:
        return 130
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"refused_or_failed","error":str(exc),"production_ready":False}))
        return 2
    print(json.dumps({key:report[key] for key in ("status","requested_cases_equal","full_native_matrix_covered",
                                                "full_native_matrix_equal","production_ready")},indent=2))
    return 0 if report["requested_cases_equal"] else 1


if __name__=="__main__":
    raise SystemExit(main())
