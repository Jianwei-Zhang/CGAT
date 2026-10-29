#!/usr/bin/env python3
"""Internal initial-reference adapter for the UNVALIDATED hypothesis branch.

Not a customer command/configuration surface. Only a separate branch package
installs this into generated commands. Native success can publish unchanged;
recovered publication is deliberately closed until the final acceptance phase.
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
import windowed_alignment as wa

MANIFEST = "branch-runtime.json"
RUNTIME_FILES = (
    "server_alignment.py","selective_reference_alignment.py","guided_alignment.py","windowed_alignment.py",
    "native_first.py","native_evaluation.py","native_chain_state.py","build_native_chain_state.py",
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
            or value.get("status")!="unvalidated_branch_runtime"
            or value.get("scope")!="initial_reference_asm10_only"
            or value.get("recovered_output_admission")!="closed_pending_final_acceptance"
            or value.get("files_sha256")!=runtime_files(root)):
        raise wa.ExperimentError("branch runtime source/contract mismatch")
    return {"path":str(path),"sha256":hashlib.sha256(raw).hexdigest(),"files_sha256":value["files_sha256"],
            "recovered_output_admission":"closed_pending_final_acceptance",
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


def publication_source(report,attempt):
    if (report.get("status")!="experimental_candidate_only"
            or report.get("original_inputs_unchanged") is not True
            or report.get("partial_PAF_reused") is not False):
        raise wa.ExperimentError("native-first result lacks complete unchanged-input evidence")
    if report.get("routing_mode")!="native_complete_unchanged":
        # Explicit implementation boundary, NOT a customer-controlled policy.
        # Final acceptance must resolve path completeness/confidence and replace
        # this closed branch admission; no flag/environment/JSON can enable it.
        raise wa.ExperimentError("recovery candidate retained, but formal output admission is CLOSED pending final acceptance; no result.paf or success may be emitted")
    if report.get("recovered_query_part_cells")!=0 or report.get("native_confidence_unchanged") is not True:
        raise wa.ExperimentError("native-only publication cannot include recovered confidence")
    path = attempt/"selective"/"reference.candidate.experimental.paf"
    digest = report.get("output_sha256")
    if (type(digest) is not str or not HASH.fullmatch(digest) or not path.is_file()
            or path.is_symlink() or wa.sha256(path)!=digest):
        raise wa.ExperimentError("complete native candidate changed before result publication")
    return path,digest


def publish_atomic(source,expected_sha256,output,attempt):
    """Hash the same bytes written to a same-filesystem pending result.

    No in-place result append. Failure before publication leaves only an
    attempt-local file. Earlier result is quarantined before mapping, never
    silently reused. Keep the linked complete file as immutable attempt evidence.
    """
    if output.exists() or output.is_symlink():
        raise wa.ExperimentError("result appeared concurrently; refusing to overwrite another attempt")
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
                minimap2="minimap2",threads=args.threads,timeout=21600,memory_gib=0,native_state_bundle=None)
            result = sr.experiment(options,prepared_workspace=workspace)
            report["candidate_receipt_sha256"] = wa.sha256(options.out/"selective-reference.json")
            source,digest = publication_source(result,attempt)
            if validate_runtime(runtime_root)!=runtime:
                raise wa.ExperimentError("branch runtime changed while mapping")
            report["publication"] = publish_atomic(source,digest,output,attempt)
            report.update(status="native_complete_published",result_published=True,
                          recovered_query_part_cells=0,recovered_output_admission="closed_pending_final_acceptance")
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
