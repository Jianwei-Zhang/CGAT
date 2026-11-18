"""Isolated first-leaf QC, existing length strata and one medium-record candidate.

Run through Donau. Never rerun a full dataset, change the main policy, or adopt a candidate. Length
strata assess recorded baseline agreement, not truth or deployment admission.
"""
import dataclasses
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path.home()/"cgat-reads-debug/jm19-compare-614589f-20261118"
WORK=ROOT/"gpm_server"
HERE=Path(__file__).resolve().parent


def main():
    sys.path[:0]=[str(ROOT/"routing-audit-validation-20261119"),
                 str(ROOT/"long-query-router-validation-v2-20261119"),
                 str(WORK/".prepare_lib/tools")]
    from export_routing_provenance import compact_decisions
    from routing_resume_support import RoutingBindings
    from paf_anchor_comparison import compare
    from seed_filter_pilot import measure
    import run_orchestration as contract
    if (HERE/"first-leaf-qc.json").exists() or (HERE/"length-strata.json").exists():
        raise RuntimeError("preserve existing diagnostics; use a new directory")
    bindings=RoutingBindings(WORK,ROOT/"routing-resume-staged-20261119/routing-plan.json",contract)
    command="runs/chr_5D/JM19_flye_ABD_vs_JM19_hifiasm/command.sh"
    marker_path=ROOT/"memory-resume-20261118/cross-leaf-checkpoints"/(contract.fingerprint(command)+".json")
    marker=json.loads(marker_path.read_text())
    assert marker["status"]=="success" and marker["command"]==command
    assert marker["inputs"]["execution_override"]==bindings.proof(command)
    task=SimpleNamespace(command=WORK/command,unit_id="q0_chr:5D")
    identity=bindings.receipt_identity(task,marker["inputs"])
    assert marker["outputs"]==[contract.file_identity(task.command.parent/name,relative_to=WORK)
                               for name in ("result.paf","stderr.log","stdout.log")]+[identity]
    receipt=json.loads((WORK/identity["path"]).read_text())
    summary=compact_decisions(receipt,contract)
    lengths={row["query"]:row["length"] for row in receipt["decisions"]}
    with (task.command.parent/"result.paf").open() as handle:
        for line in handle:
            fields=line.split("\t");assert fields[0] in lengths and int(fields[1])==lengths[fields[0]]
    groups=[]
    for group in receipt["group_evidence"]:
        cache_root=Path(group["path"]).parents[1]
        assert group["outputs"]==[contract.file_identity(cache_root/row["path"],relative_to=cache_root) for row in group["outputs"]]
        metrics,_=measure(Path(group["path"]))
        stderr=cache_root/next(row["path"] for row in group["outputs"] if row["path"].endswith("/stderr.log"))
        groups.append({"filter":group["identity"]["filter"],"queries":len(group["identity"]["queries"]),
            "query_bases":sum(group["identity"]["queries"].values()),"metrics":metrics,
            "native_timing_lines":[s for s in stderr.read_text().splitlines() if "Real time:" in s]})
    contract.atomic_write_json(HERE/"first-leaf-qc.json",{
        "status":"single_completed_leaf_verified", "scope":"5D cross only",
        "certifies_complete_routing_plan":False,"certifies_whole_workflow":False,
        "native_marker_sha256":contract.sha256_file(marker_path),"receipt":identity,
        "records":summary,"groups":groups,"final_paf":receipt["output"],
        "inputs_basis":"recorded_completed_checkpoint_not_rehashed_here"})
    print("FIRST_REAL_LEAF_QC",json.dumps({"queries":summary["query_count"],"groups":groups}),flush=True)

    # Reuse the already completed full-native and full-f0.005 3D PAFs.
    pilot_root=ROOT/"seed-filter-full-3D-pilot-20261119"
    report=json.loads((pilot_root/"result.json").read_text())
    assert report["status"]=="candidate_and_native_compared_not_adopted"
    baseline_marker=json.loads(Path(report["native_leaf_checkpoint"]).read_text())
    assert baseline_marker["inputs"]["files"]==report["inputs"]
    assert baseline_marker["inputs"]["tool"]["sha256"]==report["tool_sha256"]
    baseline_row=next(r for r in baseline_marker["outputs"] if r["path"].endswith("/result.paf"))
    candidate_row=next(r for r in report["outputs"] if r["path"].endswith("/result.paf"))
    baseline,candidate=WORK/baseline_row["path"],pilot_root/candidate_row["path"]
    assert contract.file_identity(baseline,relative_to=WORK)==baseline_row
    assert contract.file_identity(candidate,relative_to=pilot_root)==candidate_row
    output=HERE/"strata";output.mkdir()
    results=[]
    bins=[("lt20M",0,20000000),("20M_to50M",20000000,50000000),
          ("50M_to100M",50000000,100000000),("ge100M",100000000,None)]
    for name,low,high in bins:
        for mapq in (0,60):
            paths=[]
            for label,source in (("baseline",baseline),("candidate",candidate)):
                destination=output/(name+"_baseline_mapq"+str(mapq)+"_"+label+".paf")
                with source.open() as src,destination.open("x") as dst:
                    for line in src:
                        f=line.split("\t");n=int(f[1])
                        if low<=n and (high is None or n<high) and (label!="baseline" or int(f[11])>=mapq):
                            dst.write(line)
                paths.append(destination)
            value=compare(*paths)
            value.update(group=name,minimum_baseline_mapq=mapq)
            value["baseline_metrics"],_=measure(paths[0])
            value["candidate_metrics"],_=measure(paths[1])
            results.append(value)
    contract.atomic_write_json(HERE/"length-strata.json",{
        "scope":"existing full 3D outputs; no new alignments or parameter changes",
        "baseline":baseline_row,"candidate":candidate_row,"results":results,
        "ground_truth_accuracy_claim":False,"new_trigger_adopted":False})
    print("EXISTING_3D_LENGTH_STRATA",json.dumps(results),flush=True)

    # One complete ~51 Mb record, not the entire ordinary group. Its completed
    # original-parameter baseline already exists: do NOT rerun a native pilot.
    from long_query_cross_router import Router, Policy, MappingFailed, acceptable
    ordinary=[d for d in receipt["decisions"] if d.get("effective_filter",d["filter"]) is None
              and d["length"]<100000000]
    selected=max(ordinary,key=lambda d:d["length"])
    medium={"scope":"one complete ordinary 5D record; existing native baseline reused",
            "new_trigger_adopted":False,"automatic_window_gate_tested":False,
            "native_per_record_time_known":False,"query":selected["query"],"length":selected["length"]}
    if selected["length"]<50000000:
        medium["status"]="no_eligible_medium_record"
    else:
        native_group=next(g for g in receipt["group_evidence"]
                          if g["cache_key"]==receipt["effective_sources"][selected["query"]])
        assert native_group["identity"]["filter"] is None
        native=HERE/"medium-native-baseline.paf"
        with Path(native_group["path"]).open() as src,native.open("x") as dst:
            for line in src:
                if line.startswith(selected["query"]+"\t"):dst.write(line)
        inputs=marker["inputs"]["files"]
        router=Router(WORK/inputs[1]["path"],WORK/inputs[2]["path"],marker["inputs"]["tool"]["path"],
                      HERE/"medium-candidate-cache",WORK/".prepare_lib/tools",threads=2,
                      policy=dataclasses.replace(Policy(),long_bases=50000000))
        assert router.target.source_sha256==inputs[1]["sha256"]
        assert router.query.source_sha256==inputs[2]["sha256"]
        assert router.tool_hash==marker["inputs"]["tool"]["sha256"]
        assert router.records[selected["query"]].length==selected["length"]
        assert router.policy.minimum_target_bases<=sum(router.target_lengths.values())<=router.policy.maximum_target_bases
        with router.signals():
            router.stable(check_code=True)
            try:
                group=router.mapping(router.materialize([selected["query"]]),
                    {selected["query"]:selected["length"]},.005,phase="whole_records",timeout=300)
            except MappingFailed as error:
                medium.update(status="candidate_failed_or_timed_out",error=str(error))
            else:
                bm,_=measure(native);cm,_=measure(Path(group["path"]))
                comparisons=[compare(native,Path(group["path"]),step) for step in (10000,1000)]
                medium.update(status="full_context_candidate_compared_not_adopted",
                    baseline=contract.file_identity(native,relative_to=HERE),candidate=group,
                    baseline_metrics=bm,candidate_metrics=cm,comparisons=comparisons,
                    matches_internal_quality_limits_at_both_grids=(
                        cm["primary_query_covered_bases"]/selected["length"]>=router.policy.minimum_full_query_coverage
                        and group["mid_occ"] is not None and native_group["mid_occ"] is not None
                        and group["mid_occ"]<native_group["mid_occ"]
                        and all(acceptable(bm,cm,c,router.policy) for c in comparisons)))
            router.stable(check_code=True)
    contract.atomic_write_json(HERE/"medium-record-study.json",medium)
    print("MEDIUM_RECORD_STUDY",json.dumps({k:v for k,v in medium.items() if k!="candidate"}),flush=True)


if __name__=="__main__":main()
