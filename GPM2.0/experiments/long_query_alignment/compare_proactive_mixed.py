#!/usr/bin/env python3
"""Opt-in 9-normal/1-long proactive control, not a production dispatcher.

Reuse an explicitly supplied, source-validated recovery package. No original
whole-input crash, bisection or singleton crash is requested. QA baseline calls
are labelled separately from the candidate execution. The small fixture lowers
the INTERNAL test threshold; the large fixture uses the actual operation limit.
Neither path publishes result.paf, success checkpoints or customer packages.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import random
import shutil
import sys

import proactive_reference_plan as pp


def experiment(args):
    root=args.out.resolve()
    if root.exists() or not root.parent.is_dir():
        raise pp.PlanError("fresh experiment output directory required")
    for parent in (root.parent,*root.parent.parents):
        if (parent/".prepare_lib").exists() or (parent/"run_all.sh").exists():
            raise pp.PlanError("experiment cannot write inside a prepared workspace")
    engine=args.engine_root.resolve()
    if engine==root or root in engine.parents or engine in root.parents:
        raise pp.PlanError("engine and output must not overlap")
    sys.path.insert(0,str(engine))
    sa=importlib.import_module("server_alignment")
    if Path(sa.__file__).resolve().parent!=engine:
        raise pp.PlanError("wrong recovery engine imported")
    checked=sa.validate_runtime(engine)
    ga,wa,sr,nst=sa.sr.ga,sa.wa,sa.sr,sa.nst
    ne=importlib.import_module("native_evaluation")
    mic=importlib.import_module("minimap_index_context")
    bundle=nst.validate_bundle(engine/"native"/nst.build.host_platform())
    mm=shutil.which(args.minimap2)
    if mm is None:raise pp.PlanError("pinned minimap2 not found")
    mm=str(Path(mm).resolve());tool_hash=wa.sha256(Path(mm))
    if tool_hash!="b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d":
        raise pp.PlanError("control requires the exact previously tested customer minimap2 binary")
    root.mkdir(mode=0o700)
    report={"status":"running","scope":"proactive_mixed_control_not_server_publication",
            "production_ready":False,"customer_data_used":False,"engine":checked,
            "planner_sha256":wa.sha256(Path(pp.__file__)),"harness_sha256":wa.sha256(Path(__file__)),
            "minimap2_sha256":tool_hash,"commands":[],"single_original_query_failure_required":False}
    def run(name,command,scope):
        report["commands"].append({"name":name,"scope":scope,"command":command})
        return wa.run_command(command,root,name,21600,args.memory_gib)
    try:
        large=args.large_reference is not None
        if large:
            target=args.large_reference.resolve(strict=True)
            if root==target or root in target.parents:raise pp.PlanError("reference overlaps output")
            reference_catalog=pp.scan_query(target)
            if len(reference_catalog.records)!=1 or reference_catalog.records[0].length<=pp.MAX_OPERATION:
                raise pp.PlanError("large control requires a single genuinely over-limit reference")
            with target.open("rb") as source:
                header=source.readline(pp.CHUNK)
                if not header.startswith(b">"):raise pp.PlanError("fixture needs a leading reference header")
                sample=source.read(72000).replace(b"\n",b"").replace(b"\r",b"")
            length=reference_catalog.records[0].length
            policy=pp.WindowPolicy()
        else:
            target=root/"reference.fa"
            rng=random.Random(20261030)
            bases=bytes(rng.choices(b"ACGT",k=120000))
            target.write_bytes(b">target\n"+bases+b"\n")
            reference_catalog=pp.scan_query(target)
            sample=bases[:72000];length=90000
            policy=pp.WindowPolicy(20000,4000)
        ordinary=[(f"q{9-i}",sample[i*5000:i*5000+2500]) for i in range(8)]+[("q1",b"N"*2500)]
        query=root/"mixed.fa"
        with query.open("xb") as output:
            for i,(name,sequence) in enumerate(ordinary):
                if i==4:
                    output.write(b">long_record original identity\n")
                    if large:
                        with target.open("rb") as source:
                            source.readline(pp.CHUNK)
                            shutil.copyfileobj(source,output,pp.CHUNK)
                        output.write(b"\n")
                    else:output.write(bases[:length]+b"\n")
                output.write(b">"+name.encode()+b" ordinary original header\n"+sequence+b"\n")
        old_limit=pp.MAX_OPERATION
        try:
            if not large:pp.MAX_OPERATION=64000  # TEST ONLY, never a customer option.
            catalog=pp.scan_query(query);plan=pp.make_plan(catalog,policy)
            groups=pp.materialize(catalog,plan,root/"inputs")
        finally:
            pp.MAX_OPERATION=old_limit
        wa.write_json(root/"plan.json",plan);wa.write_json(root/"query-catalog.json",{
            "source_sha256":catalog.source_sha256,"records":[pp.asdict(r) for r in catalog.records]})
        assert len(plan["native_queries"])==9 and plan["long_queries"]==["long_record"]
        native=Path(next(g["path"] for g in groups["groups"] if g["route"]=="native"))
        long_query=Path(next(g["path"] for g in groups["groups"] if g["route"]=="long_query"))
        index=root/"original-default.mmi"
        run("index",[mm,"-x","asm10","-t","1","-d",str(index),str(target)],"candidate")
        targets={r.name:{"length":r.length} for r in reference_catalog.records}
        parts=mic.read_catalog(index,targets)
        if len(parts["parts"])!=1:raise pp.PlanError("this control is single-part; multipart acceptance is separate")
        native_paf=root/"ordinary.native.paf"
        run("ordinary",[mm,"-c","-x","asm10","-t","1","-o",str(native_paf),str(index),str(native)],"candidate")
        mid=sr.read_shared_mid_occ(root/"ordinary.stderr",1)
        context={"part_index":0,"path":str(index),"sha256":wa.sha256(index),"preset":"asm10",
                 "tool_sha256":tool_hash,"reference_sha256":reference_catalog.source_sha256,"mid_occ":mid,
                 "records":[{"name":r.name,"length":r.length} for r in reference_catalog.records]}
        wa.write_json(root/"index-context.json",context)
        options=argparse.Namespace(target=target,query=long_query,out=root/"long-direct",minimap2=mm,preset="asm10",
            core_bases=policy.core_bases,context_bases=policy.context_bases,guide_slack=1000,threads=1,
            timeout=21600,memory_gib=args.memory_gib,require_full_query_coverage=False,index_context=context,
            allow_empty_index_part=False,window_candidate_policy="all_chains_pool",recover_path_scores=True,
            native_state_bundle=Path(bundle["manifest_path"]).parent)
        recovered=ga.experiment(options)
        state=recovered["native_recovery"]
        private=Path(state["native_evaluated_paf"])
        validator=lambda raw:sr.validate_row(raw,{"long_record":{"length":length}},targets,{"long_record"},"risk")
        pair=ne.validate_pair(options.out/"guided.experimental.paf",private,public_sha256=recovered["output_sha256"],
                              evaluated_sha256=state["native_evaluated_sha256"],validator=validator)
        if not (state["selection"]["native_decisions_applied"] and state["raw_overlap_consistency_checked"]):
            raise pp.PlanError("direct recovery lacks actual native-state/overlap evidence")
        # QA-only baseline, NEVER an original whole-long-input attempt.
        baseline=root/"qa-baseline.paf"
        baseline_query=native if large else query
        run("qa-baseline",[mm,"-c","-x","asm10","-t","1","-o",str(baseline),str(target),str(baseline_query)],"independent_QA_only")
        with baseline.open("rb") as source:
            expected=b"".join(raw for raw in source if raw.split(b"\t",1)[0]!=b"long_record")
        if native_paf.read_bytes()!=expected:raise pp.PlanError("ordinary native PAF changed after proactive partitioning")
        if large:
            rows=ne.comparison_signature(private)
            expected_core=("long_record",str(length),"0",str(length),"+",reference_catalog.records[0].name,
                           str(length),"0",str(length),str(length),str(length),"60")
            if len(rows)!=1 or rows[0][0]!=expected_core:raise pp.PlanError("long analytic identity differs")
            long_equal=True
        else:
            eqx=root/"qa-eqx.paf"
            run("qa-eqx",[mm,"-c","--eqx","-x","asm10","-t","1","-o",str(eqx),str(index),str(query)],"independent_QA_only")
            expected_long=[row for row in ne.comparison_signature(eqx) if row[0][0]=="long_record"]
            long_equal=ne.comparison_signature(private)==expected_long
            if not long_equal:raise pp.PlanError("small full-query native metadata/path contract differs")
        executions=list((root/"long-direct").rglob("*.execution.json"))
        for path in executions:
            execution=json.loads(path.read_bytes())
            if execution.get("returncode")!=0:raise pp.PlanError("direct recovery contains a failed subprocess")
            cmd=execution["command"]
            if "-c" in cmd and str(long_query) in cmd:
                raise pp.PlanError("unwindowed long query reached full-CIGAR mapper")
            report["commands"].append({"name":path.relative_to(root).as_posix(),"scope":"candidate","command":cmd})
        catalog.require_unchanged();reference_catalog.require_unchanged()
        if sa.validate_runtime(engine)!=checked:raise pp.PlanError("frozen recovery engine changed")
        report.update(status="proactive_mixed_control_passed",large_actual_limit=large,
            forced_small_test_threshold=not large,total_queries=10,ordinary_queries=9,special_queries=1,
            no_original_whole_long_input_trial=True,no_bisection=True,no_singleton_crash_replay=True,
            candidate_reference_index_builds=1,ordinary_paf_bytes_equal=True,
            ordinary_zero_hit_query_accounted=True,long_compared_contract_equal=long_equal,pair=pair,
            source_catalog_physical_bytes_read=catalog.physical_bytes_read,
            query_materialization_physical_bytes_read=groups["query_materialization_physical_bytes_read"],
            window_work=next(row["work"] for row in plan["records"] if row["query"]=="long_record"),
            AS_compared=False,whole_query_DP_equivalence_certified=False,result_published=False,
            remaining_engine_redundancy=["two normalized reference/query stores in frozen window+guidance engine",
                                         "independent native coarse mapping and helper chain-state comparison",
                                         "repeated evidence hashing before admission"])
    except BaseException as exc:
        report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}");raise
    finally:
        wa.write_json(root/"proactive-control.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root",type=Path,required=True,help="Maintainer frozen source-validated packaged runtime")
    parser.add_argument("--minimap2",default="minimap2")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--large-reference",type=Path,default=None,help="Existing deterministic single-record >268-Mb identity fixture, NOT customer data")
    parser.add_argument("--memory-gib",type=int,default=6)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","no_files_or_commands_started":True}));return 0
    if args.memory_gib<0:parser.error("memory cap must be nonnegative")
    report=experiment(args)
    print(json.dumps({key:report[key] for key in ("status","large_actual_limit","ordinary_paf_bytes_equal","long_compared_contract_equal","result_published")}))
    return 0


if __name__=="__main__":raise SystemExit(main())
