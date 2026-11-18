#!/usr/bin/env python3
"""Internal original-state recovery adapter for separately validated packages.

Not a customer command/configuration surface. Native success publishes unchanged.
An eligible portable package can publish recovered known native-API metadata ONLY
with complete per-result original-cell, proactive eligibility, evidence and native input/
stdout binding. Package/product acceptance remains a separate requirement.
No compiler/download, scheduler policy, user data skip or minimap2 modification.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

import approximate_reference_cells as ap
import selective_reference_alignment as sr
import proactive_reference_alignment as pa
import proactive_publication as pub
import proactive_resume as pr
import native_chain_state as nst
import native_first as nf
import minimap_options as mo
import ordinary_resource_grant as org
import adaptive_ordinary_controller as oc
import adaptive_screening as screening
import recovery_publication as rp
import windowed_alignment as wa
import ordinary_tool_transition as ott

MANIFEST = "branch-runtime.json"
RUNTIME_FILES = (
    "approximate_reference_cells.py","adaptive_screening.py","metadata_json.py","ordinary_tool_transition.py",
    "adaptive_ordinary_controller.py","adaptive_ordinary_units.py","automatic_ordinary_pilot.py",
    "proactive_reference_plan.py","proactive_reference_alignment.py","proactive_publication.py","proactive_resume.py",
    "server_alignment.py","selective_reference_alignment.py","guided_alignment.py","windowed_alignment.py",
    "native_first.py","native_evaluation.py","native_chain_state.py","build_native_chain_state.py","recovery_publication.py",
    "native_recovery.py","native_selection.py","post_dp_selection.py","whole_query_scores.py",
    "batch_seed_ownership.py","stream_seed_trace.py","trace_memory.py","sequential_split_witness.py",
    "ordinary_partition_alignment.py","ordinary_resource_grant.py","minimap_options.py","minimap_index_context.py","seam_witness.py","resume_reference.py","native_chain_state.c","MINIMAP2_LICENSE.txt",
)
HASH = re.compile(r"[0-9a-f]{64}\Z")


def runtime_files(root):
    root = Path(root).resolve()
    result = {}
    for name in RUNTIME_FILES:
        path = root/name
        if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise wa.ExperimentError(f"branch runtime lacks an original regular source file: {name}")
        result[name] = wa.sha256(path)
    return result


def validate_runtime(root):
    root = Path(root).resolve()
    path = root/MANIFEST
    if not path.is_file() or path.is_symlink() or path.stat().st_size>1024**2:
        raise wa.ExperimentError("branch runtime receipt is missing/oversized; do not ask the customer to create one")
    raw = path.read_bytes()
    value = json.loads(raw)
    if (type(value) is not dict or value.get("schema")!=1
            or (value.get("status"),value.get("recovered_output_admission")) not in (
                ("unvalidated_branch_runtime","closed_pending_final_acceptance"),
                ("source_checked_recovery_runtime",pub.POLICY))
            or value.get("scope")!="initial_reference_asm10_only"
            or value.get("recovered_output_admission")==pub.POLICY and (
                type(value.get("native_companion_sha256")) is not str
                or not HASH.fullmatch(value["native_companion_sha256"])
                or value.get("native_companion_platform") not in ("linux-x86_64","linux-aarch64"))
            or value.get("files_sha256")!=runtime_files(root)):
        raise wa.ExperimentError("branch runtime source/contract mismatch")
    return {"path":str(path),"sha256":hashlib.sha256(raw).hexdigest(),"files_sha256":value["files_sha256"],
            "recovered_output_admission":value["recovered_output_admission"],
            "approximate_output_admission":value.get("approximate_output_admission"),
            "ordinary_output_admission":value.get("ordinary_output_admission"),
            "native_companion_sha256":value.get("native_companion_sha256"),
            "native_companion_platform":value.get("native_companion_platform"),
            "handoff_base_sha256":value.get("handoff_base_sha256"),
            "native_resume_source_profiles":value.get("native_resume_source_profiles",[]),
            "completed_reference_resume_source_profiles":value.get("completed_reference_resume_source_profiles",[]),
            "production_ready":False}


@contextmanager
def task_lock(run_dir):
    """A live advisory lock, never infer execution state from a leftover file."""
    path = run_dir/".long-cigar-alignment.lock"
    fd = os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise wa.ExperimentError("alignment lock must be a regular file")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise wa.ExperimentError("another initial-reference alignment owns this run directory") from exc
        yield
    finally:
        os.close(fd)


@contextmanager
def cancellation_scope():
    # Mapping children use their own process group. Turn shell/job termination
    # into the existing run_command cancellation path so it terminates/waits
    # that group instead of abandoning a live native mapper.
    previous = {}
    def interrupted(number,frame):
        raise KeyboardInterrupt(f"branch alignment cancelled by signal {number}")
    try:
        for number in (signal.SIGTERM,signal.SIGHUP):
            previous[number] = signal.signal(number,interrupted)
        yield
    finally:
        for number,handler in previous.items():
            signal.signal(number,handler)


def publication_source(report,attempt,*,runtime=None,runtime_root=None,ordinary_catalog=None):
    if (report.get("status")!="proactive_candidate_complete"
            or report.get("original_inputs_unchanged") is not True
            or report.get("partial_PAF_reused") is not False):
        raise wa.ExperimentError("proactive result lacks complete unchanged-input evidence")
    if report.get("ordinary_adaptive") is not None:
        if not runtime or runtime.get("ordinary_output_admission") != oc.POLICY:
            raise wa.ExperimentError("automatic ordinary publication is not enabled by this package")
    if report.get("routing_mode") in ("adaptive_large_reference", "adaptive_large_ordinary"):
        if report.get("routing_mode") == "adaptive_large_reference" and (not runtime or runtime.get("approximate_output_admission") != ap.POLICY):
            raise wa.ExperimentError("approximate initial-reference publication is not enabled by this package")
        bundle = None
        if report.get("helper") is not None:
            bundle = nst.validate_bundle(Path(runtime_root)/"native"/nst.build.host_platform())
            if bundle["sha256"] != runtime.get("native_companion_sha256"):
                raise wa.ExperimentError("legacy recovered confidence companion differs")
        admitted = pub.admit(report, attempt/"selective", bundle=bundle,
            **({"ordinary_catalog": ordinary_catalog} if report.get("ordinary_adaptive") is not None else {}))
        if bundle is not None:
            admitted.update(helper_sha256=bundle["sha256"], helper_manifest_sha256=bundle["manifest_sha256"])
        wa.write_json(attempt/"recovery-admission.json", admitted)
        return Path(admitted["path"]), admitted["sha256"]
    if report.get("routing_mode")!="native_complete_unchanged":
        if not runtime or runtime.get("recovered_output_admission")!=pub.POLICY:
            raise wa.ExperimentError("recovery candidate retained, but formal output admission is CLOSED pending final acceptance; no result.paf or success may be emitted")
        bundle = nst.validate_bundle(Path(runtime_root)/"native"/nst.build.host_platform())
        if (bundle["sha256"]!=runtime.get("native_companion_sha256")
                or bundle["platform"]!=runtime.get("native_companion_platform")
                or (bundle.get("runtime_abi") or {}).get("legacy_2_17_checked") is not True):
            raise wa.ExperimentError("proactive publication requires its package-bound portable native companion")
        admitted = pub.admit(report,attempt/"selective",bundle=bundle)
        admitted.update(helper_sha256=bundle["sha256"],helper_manifest_sha256=bundle["manifest_sha256"])
        wa.write_json(attempt/"recovery-admission.json",admitted)
        return Path(admitted["path"]),admitted["sha256"]
    if report.get("recovered_query_part_cells")!=0 or report.get("native_confidence_unchanged") is not True:
        raise wa.ExperimentError("native-only publication cannot include recovered confidence")
    path = rp.regular_under(report["output_path"],attempt/"selective")
    digest = report.get("output_sha256")
    if type(digest) is not str or not HASH.fullmatch(digest) or wa.sha256(path)!=digest:
        raise wa.ExperimentError("complete native candidate changed before result publication")
    return path,digest


def publish_atomic(source,expected_sha256,output,attempt,*,check_unchanged=None):
    """Hash the same bytes written to a same-filesystem pending result.

    No in-place result append. Failure before publication leaves only an
    attempt-local file. Earlier result is quarantined before mapping, never
    silently reused. Keep the linked complete file as immutable attempt evidence.
    """
    if output.exists() or output.is_symlink():
        raise wa.ExperimentError("result appeared concurrently; refusing to overwrite another attempt")
    if check_unchanged is not None:
        check_unchanged()
    before = wa.fingerprint(source)
    pending = attempt/"publication.complete.paf"
    digest = hashlib.sha256()
    with source.open("rb") as inp,pending.open("xb") as out:
        while raw := inp.read(wa.CHUNK):
            out.write(raw); digest.update(raw)
        out.flush(); os.fsync(out.fileno())
    if digest.hexdigest()!=expected_sha256 or wa.fingerprint(source)!=before:
        raise wa.ExperimentError("native result changed while preparing atomic publication")
    if output.exists() or output.is_symlink():
        raise wa.ExperimentError("result appeared before atomic publication; refusing overwrite")
    if check_unchanged is not None:
        check_unchanged()
    # A hard link creates the name atomically and refuses existing paths rather
    # than clobbering one in the check/rename race. Both directories are inside
    # the same run filesystem. Failure is nonzero; there is no unsafe fallback.
    os.link(pending,output,follow_symlinks=False)
    return {"path":str(output),"sha256":expected_sha256,"bytes":output.stat().st_size,
            "publication":"atomic_no_clobber_from_complete_native_output","native_bytes_preserved":True}



def alignment_policy_receipt(result, runtime, requested_options, policy, output_sha256):
    """Compact delivery provenance from already admitted sources, without paths.

    This is not a new admission or biological-accuracy certificate. Native
    options describe the ACTUAL source command, not later requested resources.
    """
    def options(command):
        if not isinstance(command, list) or command[:1] == []:
            raise wa.ExperimentError("native source command missing for policy receipt")
        return {name: command[command.index(flag) + 1] if flag in command else None
                for name, flag in (("preset", "-x"), ("query_batch", "-K"),
                                   ("minimizer_filter_argument", "-f"), ("threads", "-t"))}
    ordinary = result.get("ordinary_adaptive")
    transition = (ott.verify_transition(result["execution_tool_transition"])
                  if result.get("execution_tool_transition") is not None else None)
    sources = []
    if ordinary is not None:
        for selection in ordinary["composition"]["identity"]["selections"]:
            source = selection["source"]
            path = Path(source["directory"]) / "native-attempt.json"
            try:
                native = pr.metadata.load(path, fields={"execution"}, expected_sha256=source["receipt_sha256"])
            except pr.metadata.MetadataError as exc:
                raise wa.ExperimentError("native source changed while recording delivery policy: " + str(exc)) from exc
            sources.append({"queries": selection["queries"], "paf_sha256": source["sha256"],
                            "receipt_sha256": source["receipt_sha256"], "options": options(native["execution"]["command"])})
            if transition is not None:
                binaries = {transition[role]["path"]: transition[role]["sha256"] for role in ("origin", "execution")}
                executable = native["execution"]["command"][0]
                if executable not in binaries:
                    raise wa.ExperimentError("native delivery source uses an unbound execution tool")
                sources[-1]["tool_sha256"] = binaries[executable]
    else:
        native = result.get("native") or result.get("ordinary_native")
        if native is not None:
            rows = native.get("parts", []) if native.get("kind") == pa.opa.KIND else [{"native": native}]
            for row in rows:
                leaf = row["native"]
                sources.append({"queries": result.get("plan", {}).get("native_queries", []),
                    "part_index": row.get("part_index"), "paf_sha256": leaf["paf_sha256"],
                    "options": options(leaf["execution"]["command"])})
    reviewed_names = {r["query"] for r in result.get("native_reviews", [])}
    for review in result.get("native_reviews", []):
        native = review["native"]
        sources.append({"queries": [review["query"]], "paf_sha256": native["paf_sha256"],
                        "role": "long_query_native_review", "options": options(native["execution"]["command"])})
    window_sources = [{"query": row["query"], "part_index": row["part_index"],
        "paf_sha256": row["sha256"], "receipt_sha256": row["receipt_sha256"],
        "policy": {k: row["identity"][k] for k in ("core_bases", "context_bases", "mid_occ", "preset", "candidate_policy")}}
        for row in result.get("parts", []) if row.get("kind") == ap.POLICY and row["query"] not in reviewed_names]
    if transition is not None:
        for source in sources:
            if source.get("role") == "long_query_native_review":
                source["tool_sha256"] = transition["execution"]["sha256"]
        for source in window_sources:
            source["tool_sha256"] = transition["execution"]["sha256"]
    fallback = (ordinary or {}).get("default_continuation")
    return {"schema": 1, "status": "complete", "scope": "initial_reference_asm10",
        "output_sha256": output_sha256, "policy": policy,
        "chr_assignment_min_coverage_percent": requested_options.get("assignment_coverage", 0.60) * 100,
        "requested_options": {k: v for k, v in requested_options.items() if k in ("minimap_batch", "minimap_filter")}, "ordinary_selected_filter": (ordinary or {}).get("selected_filter"),
        "ordinary_default_continuation": ({k: fallback[k] for k in
            ("ordinal", "reason", "transition_queries", "transition_bases", "future_filter", "whole_assembly_restart")}
            if fallback else None), "native_sources": sources, "window_sources": window_sources,
        "long_queries": result.get("plan", {}).get("long_queries", []),
        "long_native_review_queries": [r["query"] for r in result.get("native_reviews", [])],
        "approximate_query_part_cells": result.get("approximate_query_part_cells", 0),
        **({"execution_tool_transition": {role: {k: transition[role][k] for k in ("sha256", "architecture", "version")}
                                           for role in ("origin", "execution")}} if transition is not None else {}),
        "input_sha256": {name: result[name]["sha256"] for name in ("query", "reference", "tool")
                         if result.get(name, {}).get("sha256")},
        "runtime_source_profile": hashlib.sha256(json.dumps(runtime["files_sha256"], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "scientific_accuracy_proven": False}


def write_alignment_policy(path, receipt, output):
    fd, temporary = tempfile.mkstemp(prefix=".alignment-policy-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(output.stat().st_mode) & 0o666)
        os.replace(temporary, path)
    finally:
        if temporary.exists():temporary.unlink()

def run_reference(args,*,runtime_root=None):
    workspace,run_dir = args.server_dir.resolve(),args.run_dir.resolve()
    if (not (workspace/".prepare_lib").is_dir() or not (workspace/"metadata").is_dir()
            or run_dir.parent!=workspace/"runs" or not run_dir.is_dir() or not run_dir.name.endswith("_vs_ref")
            or args.result!="result.paf" or args.preset!="asm10" or args.threads<1):
        raise wa.ExperimentError("branch adapter supports only a prepared initial-reference asm10 run")
    runtime_root = Path(runtime_root).resolve() if runtime_root is not None else Path(__file__).resolve().parent
    runtime = validate_runtime(runtime_root)
    mapping_options = mo.workspace_options(workspace)
    args.assignment_coverage = screening.prepared_assignment_coverage(workspace)
    mapping_options.update(screening.assignment_identity(screening.assignment_limits(args.assignment_coverage)))
    # Fraction changes alter scientific policy. K only affects future executions.
    args.minimap_filter = mapping_options.get("minimap_filter")
    output = run_dir/args.result
    policy_output = output.with_suffix(".alignment.json")
    with task_lock(run_dir),cancellation_scope():
        resume_identity = pr.adapter_key(args, runtime)
        attempt, attempt_reused = pr.select_attempt(run_dir, resume_identity, runtime=runtime)
        pr.archive_partial(attempt / "server-alignment.json")
        report = {"schema":1,"status":"running","production_ready":False,"customer_validated":False,
                  "runtime":runtime,"attempt":str(attempt),"result_published":False,"attempt_reused":attempt_reused,
                  "minimap2_modified":False,"automatic_parameter_retry":False,
                  "scope":"initial_reference_asm10_only","customer_configuration_required":False,
                  "initial_reference_options":mapping_options,
                  "ordinary_resource_context":org.dispatch_context(run_dir,args.threads)}
        wa.write_json(attempt/"server-alignment.json",report)
        try:
            if any(path.is_symlink() or (path.exists() and not stat.S_ISREG(path.stat().st_mode))
                   for path in (output, policy_output)):
                raise wa.ExperimentError("existing result/policy is not a regular file; preserving it without mapping")
            if output.is_file():
                previous = attempt/"prior-result.paf"
                if previous.exists():
                    previous = attempt/("prior-result-" + uuid.uuid4().hex + ".paf")
                output.rename(previous)
                if policy_output.exists():policy_output.rename(previous.with_suffix(".alignment.json"))
                report["previous_result"] = {"path":str(previous),"sha256":wa.sha256(previous),"restored_automatically":False}
            if policy_output.exists():
                policy_output.rename(attempt / ("orphan-alignment-policy-" + uuid.uuid4().hex + ".json"))
            options = argparse.Namespace(target=args.target,query=args.query,out=attempt/"selective",
                minimap2="minimap2",threads=args.threads,timeout=None,memory_gib=0,
                ordinary_resource_context=report["ordinary_resource_context"],
                approximate_initial_reference=runtime.get("approximate_output_admission") == ap.POLICY,
                adaptive_ordinary=runtime.get("ordinary_output_admission") == oc.POLICY,
                native_state_bundle=runtime_root/"native"/nst.build.host_platform(), **mapping_options)
            result = pa.experiment(options,prepared_workspace=workspace,admit_output=False,resume_identity=resume_identity)
            if result.get("assignment_coverage", 0.60) != args.assignment_coverage:
                raise wa.ExperimentError("candidate assignment threshold differs from the prepared project")
            report["candidate_receipt_sha256"] = wa.sha256(options.out/"proactive-candidate.json")
            source,digest = publication_source(result,attempt,runtime=runtime,runtime_root=runtime_root,
                **({"ordinary_catalog": getattr(options, "_ordinary_catalog", None)} if result.get("ordinary_adaptive") is not None else {}))
            if validate_runtime(runtime_root)!=runtime:
                raise wa.ExperimentError("branch runtime changed while mapping")
            recovered = result.get("recovered_query_part_cells",0)>0
            proactive = result.get("routing_mode")!="native_complete_unchanged"
            admission = json.loads((attempt/"recovery-admission.json").read_text()) if proactive else None
            def unchanged():
                if result.get("execution_tool_transition") is not None:
                    ott.verify_transition(result["execution_tool_transition"])
                if all(name in result for name in ("reference","query","tool")):
                    for name in ("reference","query","tool"):
                        identity = result[name]
                        path = Path(identity["path"] if name=="tool" else identity["source"])
                        if not nf.identity_unchanged(path,identity):
                            raise wa.ExperimentError("original input/tool changed before atomic result publication")
                if validate_runtime(runtime_root)!=runtime:
                    raise wa.ExperimentError("recovery runtime changed before atomic result publication")
                if admission is not None and "helper_sha256" in admission:
                    current = nst.validate_bundle(Path(runtime_root)/"native"/nst.build.host_platform())
                    if (current["sha256"]!=admission["helper_sha256"]
                            or current["manifest_sha256"]!=admission["helper_manifest_sha256"]):
                        raise wa.ExperimentError("native companion changed before atomic result publication")
            policy_receipt = alignment_policy_receipt(result, runtime, mapping_options,
                admission.get("policy") if admission else "native_complete_unchanged", digest)
            if policy_receipt["output_sha256"] != digest:
                raise wa.ExperimentError("alignment policy does not bind the admitted output")
            publication_attempt = attempt
            if any((attempt / name).exists() for name in ("publication.pending.paf", "publication.complete.paf")):
                publication_attempt = Path(tempfile.mkdtemp(prefix=".publication-", dir=attempt))
            report["publication_evidence"] = str(publication_attempt)
            report["publication"] = publish_atomic(source,digest,output,publication_attempt,check_unchanged=unchanged)
            try:
                write_alignment_policy(policy_output, policy_receipt, output)
            except BaseException:
                # Preserve validated bytes privately, but do not leave a public
                # result without its requested policy companion after failure.
                retained = publication_attempt / ("unpublished-policy-result-" + uuid.uuid4().hex + ".paf")
                if output.is_file() and not output.is_symlink():output.rename(retained)
                raise
            report["alignment_policy_receipt"] = {"path": str(policy_output), "sha256": wa.sha256(policy_output)}
            report["cache_reused"] = result.get("cache_reused", {})
            report.update(status="proactive_complete_published" if proactive else "native_complete_published",
                          result_published=True,proactive_routing=proactive,recovered_query_part_cells=result.get("recovered_query_part_cells",0),
                          recovered_output_admission=runtime["recovered_output_admission"],
                          recovered_native_confidence_published=recovered and result.get("routing_mode") != "adaptive_large_reference",
                          approximate_query_part_cells=result.get("approximate_query_part_cells", 0),
                          initial_reference_policy=admission.get("policy") if admission else "native_complete_unchanged",
                          ordinary_adaptive_policy=oc.POLICY if result.get("ordinary_adaptive") is not None else None,
                          ordinary_selected_filter=(result.get("ordinary_adaptive") or {}).get("selected_filter"),
                          ordinary_default_continuation=(result.get("ordinary_adaptive") or {}).get("default_continuation"),
                          whole_query_dp_equivalence_certified=False,AS_reconstructed=False)
        except BaseException as exc:
            report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            wa.write_json(attempt/"server-alignment.json",report)
            print(f"CGAT branch alignment evidence: {attempt}",file=sys.stderr,flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir",type=Path,required=True)
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--target",type=Path,required=True)
    parser.add_argument("--query",type=Path,required=True)
    parser.add_argument("--threads",type=int,required=True)
    parser.add_argument("--preset",default="asm10")
    parser.add_argument("--result",default="result.paf")
    args = parser.parse_args(argv)
    try:
        report = run_reference(args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"CGAT branch reference alignment failed: {exc}",file=sys.stderr)
        return 2
    print(json.dumps({"status":report["status"],"result_published":True,"production_ready":False}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
