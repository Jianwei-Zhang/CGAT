#!/usr/bin/env python3
"""Branch-only selective reference mapping under a long-CIGAR hypothesis.

Developer harness, not a replacement Server entry point. Default CLI is plan
only. No production result.paf, completion checkpoint or customer job is written.
Native success is retained unchanged, including long records. Only singleton
records that actually trigger the exact target assertion can enter recovery.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import guided_alignment as ga
import minimap_index_context as mic
import native_chain_state as nst
import native_first as nf
import native_evaluation as ne
import windowed_alignment as wa

MAX_PAF_LINE = 32*1024**2
CIGAR = re.compile(r"([1-9][0-9]*)([M=XID])")


def validate_row(raw, queries, targets, allowed, route):
    """Strict recovered-path validation; native bodies use opaque streaming."""
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


def build_default_index(mm, target, root, args, tool_hash):
    """Build with the SAME default partition policy as original reference mapping."""
    index = root/"target.default.mmi"
    wa.run_command([mm,"-x","asm10","-t",str(args.threads),"-d",str(index),str(target.source)],
                   root,"default-index",args.timeout,args.memory_gib)
    try:
        catalog = mic.copy_parts(index,root/"index-parts",target.records)
    except mic.IndexContextError as exc:
        raise wa.ExperimentError(str(exc)) from exc
    for part in catalog["parts"]:
        part.update(reference_sha256=target.identity["sha256"],tool_sha256=tool_hash,preset="asm10")
    catalog.update(reference_sha256=target.identity["sha256"],tool_sha256=tool_hash,
                   index_policy="original_default_no_I_override",production_ready=False)
    wa.write_json(root/"index-context.json",catalog)
    return catalog


def read_shared_mid_occ(path, expected_parts):
    """Read the threshold retained by upstream mm_mapopt_update across parts."""
    pattern = re.compile(rb"\[M::mm_mapopt_update::[^\]]+\] mid_occ = ([0-9]+)\s*$")
    values,total = [],0
    with Path(path).open("rb") as stream:
        while raw := stream.readline(65537):
            total += len(raw)
            if len(raw)>65536 or total>16*1024**2:
                raise wa.ExperimentError("minimizer-threshold log exceeds bounded metadata scan")
            match = pattern.search(raw)
            if match:
                value = match[1]
                if len(value)>10 or not 1 <= int(value) <= wa.INT32_MAX:
                    raise wa.ExperimentError("invalid minimizer threshold")
                values.append(int(value))
    if len(values) != expected_parts or len(set(values)) != 1:
        raise wa.ExperimentError("missing or inconsistent original first-part minimizer threshold")
    return values[0]


def experiment(args):
    root = args.out.resolve()
    if not root.parent.is_dir() or root.exists() or args.out.is_symlink():
        raise wa.ExperimentError("fresh output directory under an existing parent required")
    for parent in (root.parent,*root.parent.parents):
        if (parent/".prepare_lib").exists() or (parent/"run_all.sh").exists():
            raise wa.ExperimentError("branch experiment must be outside a prepared Server workspace")
    target_path,query_path = args.target.resolve(),args.query.resolve()
    if target_path==query_path:
        raise wa.ExperimentError("initial reference alignment only; self-alignment is unsupported")
    if args.threads<1 or args.timeout<1 or args.memory_gib<0:
        raise wa.ExperimentError("invalid experiment resource bounds")
    mm = shutil.which(args.minimap2)
    if not mm:
        raise wa.ExperimentError("minimap2 not found")
    mm = str(Path(mm).resolve())
    root.mkdir(mode=0o700)
    report = {"schema":2,"status":"running","production_ready":False,"customer_validated":False,
              "hypothesis":"single long CIGAR operation overflow; customer mechanism unconfirmed",
              "scope":"native-first initial-reference experiment only","tests_deferred":True,
              "harness_sha256":wa.sha256(Path(__file__)),"server_result_published":False,
              "promotion_blockers":["native/recovery path-context equivalence and candidate completeness",
                                    "formal confidence contract","deferred branch validation",
                                    "transparent Server integration and prebuilt bundle",
                                    "customer reproduction","downstream scientific acceptance"]}
    wa.write_json(root/"selective-reference.json",report)
    try:
        target_identity = nf.source_identity(target_path)
        query_identity = nf.source_identity(query_path)
        tool_identity = nf.source_identity(Path(mm))
        tool_hash = tool_identity["sha256"]
        version = subprocess.check_output([mm,"--version"],text=True,timeout=5).strip()
        report.update(tool={"path":mm,"sha256":tool_hash,"version":version},
                      reference=target_identity,query=query_identity,
                      helper_sha256={Path(module.__file__).name:wa.sha256(Path(module.__file__))
                                     for module in (ga,wa,mic,nst,nf,ne)})

        def unchanged():
            if (not nf.identity_unchanged(target_path,target_identity)
                    or not nf.identity_unchanged(query_path,query_identity)
                    or not nf.identity_unchanged(Path(mm),tool_identity)):
                raise wa.ExperimentError("original input/tool changed during native-first experiment")

        unchanged()
        native = nf.attempt(mm,target_path,query_path,root/"original-native",args)
        report["original_native"] = native
        unchanged()
        pending = root/"reference.candidate.pending.paf"
        evaluated_pending = None
        if native["status"]=="native_success":
            # No FASTA normalization, length routing, MMI split, companion lookup,
            # PAF parsing/tag policy or windowing on the normal native path.
            # Even a zero-byte native-complete PAF is retained as native output.
            source = Path(native["path"])
            shutil.copyfile(source,pending)
            if wa.sha256(pending)!=native["paf_sha256"] or wa.sha256(source)!=native["paf_sha256"]:
                raise wa.ExperimentError("native-complete PAF changed before unchanged publication")
            report.update(routing_mode="native_complete_unchanged",native_row_bytes_preserved=True,
                          recovered_query_part_cells=0,companion_required=False,
                          native_confidence_unchanged=True,partial_PAF_reused=False)
        else:
            if native["status"]!="target_assertion":
                raise wa.ExperimentError("original mapping failed outside the exact target assertion; no recovery attempted")
            if version!="2.31-r1302":
                raise wa.ExperimentError("target-assertion recovery is pinned to customer minimap2 2.31-r1302")
            # Parse only now: native-successful compressed/other accepted input
            # must not gain a plain-FASTA restriction or a normalized disk copy.
            target,query = nf.RawFastaCatalog(target_path),nf.RawFastaCatalog(query_path)
            if (target.identity!=target_identity or query.identity!=query_identity):
                raise wa.ExperimentError("source bytes/identity changed after original native failure")
            catalog = build_default_index(mm,target,root,args,tool_hash)
            mid_occ = nf.shared_mid_occ(native,len(catalog["parts"]))
            for part in catalog["parts"]:
                part["mid_occ"] = mid_occ
            catalog.update(shared_mid_occ=mid_occ,threshold_source="original_failed_mapping_prefix")
            wa.write_json(root/"index-context.json",catalog)
            report.update(routing_mode="exact_assertion_whole_record_isolation",
                          index_catalog_sha256=wa.sha256(root/"index-context.json"),shared_mid_occ=mid_occ,
                          threshold_source=catalog["threshold_source"],index_policy=catalog["index_policy"],
                          length_is_not_a_recovery_trigger=True,index_part_count=len(catalog["parts"]),
                          risk_window_candidate_policy="all_chains_pool",parts=[],
                          whole_query_candidate_completeness_certified=False,global_mapq_restored=False)
            merger = nf.CellMerger(root/"complete-cells",query.records,target.records,catalog["parts"])
            native_bundle = None

            def accept_native(receipt,names,part):
                unchanged()
                merger.add_native(receipt,names,part_index=part["part_index"])

            def recover_assertion(name,query_file,part,directory):
                nonlocal native_bundle
                unchanged()
                if native_bundle is None:
                    # The artifact must carry the companion; never require it
                    # for a long record that already succeeded natively.
                    native_bundle = nst.validate_bundle(getattr(args,"native_state_bundle",None))
                    report["original_chain_state_helper"] = native_bundle
                options = argparse.Namespace(target=target_path,query=query_file,out=directory/"recovery",
                    minimap2=mm,preset="asm10",core_bases=50_000_000,context_bases=100_000,guide_slack=1000,
                    threads=args.threads,timeout=args.timeout,memory_gib=args.memory_gib,
                    require_full_query_coverage=False,index_context=part,allow_empty_index_part=False,
                    window_candidate_policy="all_chains_pool",recover_path_scores=True,
                    native_state_bundle=Path(native_bundle["manifest_path"]).parent)
                result = ga.experiment(options)
                validator = lambda raw: validate_row(raw,query.records,target.records,{name},"risk")
                witness = nf.long_operation_witness(options.out,result,name,validator)
                wa.write_json(options.out/"long-operation-witness.json",witness)
                unchanged()
                count = merger.add_recovered(options.out/"guided.experimental.paf",result["output_sha256"],
                    name,part["part_index"],validator,native_evaluated={
                        "path":result["native_recovery"]["native_evaluated_paf"],
                        "sha256":result["native_recovery"]["native_evaluated_sha256"]})
                return {"query":name,"rows":count,"guidance_sha256":wa.sha256(options.out/"guidance.json"),
                        "long_operation_witness_sha256":wa.sha256(options.out/"long-operation-witness.json"),
                        "long_operation_witness":witness,"native_confidence_promoted":False,
                        "native_evaluation_pair":merger.evaluated_cells[(part["part_index"],name)]}

            for part in catalog["parts"]:
                unchanged()
                isolated = nf.isolate_part(mm,part,query,root/f"part-{part['part_index']:04d}",args,
                    on_native=accept_native,on_assertion=recover_assertion,check_unchanged=unchanged)
                if wa.sha256(Path(part["path"]))!=part["sha256"]:
                    raise wa.ExperimentError("original index part changed during assertion isolation")
                report["parts"].append(isolated)
                wa.write_json(root/"selective-reference.json",report)
            if not any(part["assertion_leaves"] for part in report["parts"]):
                raise wa.ExperimentError("original assertion did not reproduce in any singleton; recovery hypothesis unverified")
            unchanged()
            report["combination"] = merger.finish(pending)
            evaluated_pending = root/"reference.native-evaluated.pending.paf"
            report["native_evaluation_combination"] = merger.finish(evaluated_pending,native_evaluated=True)
            if report["combination"]["rows_by_query"]!=report["native_evaluation_combination"]["rows_by_query"]:
                raise wa.ExperimentError("public/private complete candidate sets differ")
            report.update(recovered_query_part_cells=report["combination"]["recovered_cells"],
                          native_row_bytes_preserved=True,partial_PAF_reused=False,
                          recovered_confidence="unknown; native-evaluated confidence remains private",
                          companion_required=True)
        unchanged()
        output = root/"reference.candidate.experimental.paf"
        output_sha256 = wa.sha256(pending)
        if evaluated_pending is None:
            report["native_evaluation"] = {"path":str(output),"sha256":output_sha256,
                "scope":"unchanged_native_complete_output","native_confidence_promoted":False,"production_ready":False}
        else:
            evaluated_output = root/"reference.native-evaluated.experimental.paf"
            evaluated_sha256 = wa.sha256(evaluated_pending)
            evaluated_pending.rename(evaluated_output)
            report["native_evaluation"] = {"path":str(evaluated_output),"sha256":evaluated_sha256,
                "scope":"private_native_API_on_supplied_recovered_state_only","ordered_candidate_path_equal":True,
                "native_confidence_promoted":False,"whole_query_dp_equivalence_certified":False,"production_ready":False}
        pending.rename(output)
        report.update(status="experimental_candidate_only",output_sha256=output_sha256,
                      original_inputs_unchanged=True,ordinary_rows_keep_original_tags=True)
    except BaseException as exc:
        report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
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
    parser.add_argument("--native-state-bundle",type=Path,default=None,
                        help="Maintainer harness only; defaults to the prebundled platform companion. Not a run.sh option.")
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","production_ready":False,"query":str(args.query),
                          "target":str(args.target),"output":str(args.out),"core_bases":50_000_000,
                          "context_each_side":100_000,"recovery_trigger":"exact assertion on a singleton after native failure",
                          "length_is_not_a_recovery_trigger":True,
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
