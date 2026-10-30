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

import selective_reference_alignment as sr
import proactive_reference_alignment as pa
import proactive_publication as pub
import native_chain_state as nst
import native_first as nf
import recovery_publication as rp
import windowed_alignment as wa

MANIFEST = "branch-runtime.json"
RUNTIME_FILES = (
    "proactive_reference_plan.py","proactive_reference_alignment.py","proactive_publication.py",
    "server_alignment.py","selective_reference_alignment.py","guided_alignment.py","windowed_alignment.py",
    "native_first.py","native_evaluation.py","native_chain_state.py","build_native_chain_state.py","recovery_publication.py",
    "native_recovery.py","native_selection.py","post_dp_selection.py","whole_query_scores.py",
    "batch_seed_ownership.py","stream_seed_trace.py","trace_memory.py","sequential_split_witness.py",
    "minimap_index_context.py","seam_witness.py","resume_reference.py","native_chain_state.c","MINIMAP2_LICENSE.txt",
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
            "native_companion_sha256":value.get("native_companion_sha256"),
            "native_companion_platform":value.get("native_companion_platform"),
            "handoff_base_sha256":value.get("handoff_base_sha256"),"production_ready":False}


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


def publication_source(report,attempt,*,runtime=None,runtime_root=None):
    if (report.get("status")!="proactive_candidate_complete"
            or report.get("original_inputs_unchanged") is not True
            or report.get("partial_PAF_reused") is not False):
        raise wa.ExperimentError("proactive result lacks complete unchanged-input evidence")
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


def run_reference(args,*,runtime_root=None):
    workspace,run_dir = args.server_dir.resolve(),args.run_dir.resolve()
    if (not (workspace/".prepare_lib").is_dir() or not (workspace/"metadata").is_dir()
            or run_dir.parent!=workspace/"runs" or not run_dir.is_dir() or not run_dir.name.endswith("_vs_ref")
            or args.result!="result.paf" or args.preset!="asm10" or args.threads<1):
        raise wa.ExperimentError("branch adapter supports only a prepared initial-reference asm10 run")
    runtime_root = Path(runtime_root).resolve() if runtime_root is not None else Path(__file__).resolve().parent
    runtime = validate_runtime(runtime_root)
    output = run_dir/args.result
    with task_lock(run_dir),cancellation_scope():
        attempt = Path(tempfile.mkdtemp(prefix=".long-cigar-attempt-",dir=run_dir))
        report = {"schema":1,"status":"running","production_ready":False,"customer_validated":False,
                  "runtime":runtime,"attempt":str(attempt),"result_published":False,
                  "minimap2_modified":False,"automatic_parameter_retry":False,
                  "scope":"initial_reference_asm10_only","customer_configuration_required":False}
        wa.write_json(attempt/"server-alignment.json",report)
        try:
            if output.is_symlink() or (output.exists() and not stat.S_ISREG(output.stat().st_mode)):
                raise wa.ExperimentError("existing result is not a regular file; preserving it without mapping")
            if output.is_file():
                previous = attempt/"prior-result.paf"
                output.rename(previous)
                report["previous_result"] = {"path":str(previous),"sha256":wa.sha256(previous),"restored_automatically":False}
            options = argparse.Namespace(target=args.target,query=args.query,out=attempt/"selective",
                minimap2="minimap2",threads=args.threads,timeout=21600,memory_gib=0,
                native_state_bundle=runtime_root/"native"/nst.build.host_platform())
            result = pa.experiment(options,prepared_workspace=workspace,admit_output=False)
            report["candidate_receipt_sha256"] = wa.sha256(options.out/"proactive-candidate.json")
            source,digest = publication_source(result,attempt,runtime=runtime,runtime_root=runtime_root)
            if validate_runtime(runtime_root)!=runtime:
                raise wa.ExperimentError("branch runtime changed while mapping")
            recovered = result.get("recovered_query_part_cells",0)>0
            proactive = result.get("routing_mode")!="native_complete_unchanged"
            admission = json.loads((attempt/"recovery-admission.json").read_text()) if proactive else None
            def unchanged():
                if all(name in result for name in ("reference","query","tool")):
                    for name in ("reference","query","tool"):
                        identity = result[name]
                        path = Path(identity["path"] if name=="tool" else identity["source"])
                        if not nf.identity_unchanged(path,identity):
                            raise wa.ExperimentError("original input/tool changed before atomic result publication")
                if validate_runtime(runtime_root)!=runtime:
                    raise wa.ExperimentError("recovery runtime changed before atomic result publication")
                if admission is not None:
                    current = nst.validate_bundle(Path(runtime_root)/"native"/nst.build.host_platform())
                    if (current["sha256"]!=admission["helper_sha256"]
                            or current["manifest_sha256"]!=admission["helper_manifest_sha256"]):
                        raise wa.ExperimentError("native companion changed before atomic result publication")
            report["publication"] = publish_atomic(source,digest,output,attempt,check_unchanged=unchanged)
            report.update(status="proactive_complete_published" if proactive else "native_complete_published",
                          result_published=True,proactive_routing=proactive,recovered_query_part_cells=result.get("recovered_query_part_cells",0),
                          recovered_output_admission=runtime["recovered_output_admission"],
                          recovered_native_confidence_published=recovered,
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
