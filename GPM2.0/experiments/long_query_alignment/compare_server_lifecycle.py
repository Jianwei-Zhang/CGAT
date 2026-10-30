#!/usr/bin/env python3
"""Exercise packaged adapter subprocess safety, not biological recovery.

Maintainer-only, PLAN ONLY by default. A clearly identified fake mapper tests
native byte preservation, non-target errors and real process-group cancellation.
It never substitutes for real pinned-minimap2 scientific/long-input controls.
Only fresh test directories are created; the package and installed tools stay
unchanged. No scheduler, compiler, download or customer configuration is used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import server_alignment as sa
import windowed_alignment as wa

MAPPER = r'''#!/usr/bin/env python3
import json,os,pathlib,subprocess,sys,time
if sys.argv[1:]==["--version"]:
    print("2.31-r1302");raise SystemExit(0)
output=pathlib.Path(sys.argv[sys.argv.index("-o")+1])
mode=os.environ["CGAT_LIFECYCLE_TEST_MODE"]
if mode=="native":
    output.write_bytes(b"opaque native test bytes\n");raise SystemExit(0)
output.write_text("failed partial MUST NOT be published\n")
if mode=="error":
    print("[morecore] insufficient memory (injected lifecycle test)",file=sys.stderr);raise SystemExit(1)
child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"])
pathlib.Path(os.environ["CGAT_LIFECYCLE_TEST_PIDS"]).write_text(json.dumps([os.getpid(),child.pid]))
child.wait()
'''


def live(pid):
    try:
        # A dead reparented zombie is not a still-running abandoned mapper.
        text=Path(f"/proc/{pid}/stat").read_text()
        return text[text.rfind(")")+2:].split()[0]!="Z"
    except FileNotFoundError:
        return False


def experiment(args):
    package=args.package_root.resolve(); out=args.out.resolve()
    runtime=package/"tools/long_cigar_recovery"
    checked=sa.validate_runtime(runtime)
    if out.exists() or not out.parent.is_dir() or out==package or package in out.parents or out in package.parents:
        raise wa.ExperimentError("lifecycle controls need a fresh directory outside the package")
    out.mkdir(mode=0o700)
    binary_dir=out/"fake-bin";binary_dir.mkdir()
    mapper=binary_dir/"minimap2";mapper.write_text(MAPPER);mapper.chmod(0o755)
    report={"status":"running","scope":"packaged_subprocess_lifecycle_only_fake_mapper",
            "package_runtime":checked,"harness_sha256":wa.sha256(Path(__file__)),
            "real_minimap2_recovery_test":False,"cases":[]}
    try:
        for mode in ("native","error","cancel"):
            workspace=out/mode;run=workspace/"runs/test_vs_ref"
            run.mkdir(parents=True);(workspace/".prepare_lib").mkdir();(workspace/"metadata").mkdir()
            target=workspace/"target.fa";query=workspace/"query.fa"
            target.write_text(">t\nACGTACGT\n");query.write_text(">q\nACGTACGT\n")
            result=run/"result.paf";result.write_bytes(b"previous stale result\n")
            pids_file=workspace/"pids.json"
            env={**os.environ,"PATH":str(binary_dir)+os.pathsep+os.environ["PATH"],
                 "CGAT_LIFECYCLE_TEST_MODE":mode,"CGAT_LIFECYCLE_TEST_PIDS":str(pids_file),
                 "PYTHONDONTWRITEBYTECODE":"1"}
            cmd=[sys.executable,str(runtime/"server_alignment.py"),"--server-dir",str(workspace),
                 "--run-dir",str(run),"--target",str(target),"--query",str(query),"--threads","1"]
            with (workspace/"process.log").open("wb") as log:
                proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
                try:
                    if mode=="cancel":
                        deadline=time.monotonic()+15
                        while not pids_file.exists() and proc.poll() is None and time.monotonic()<deadline:
                            time.sleep(.05)
                        if not pids_file.exists():
                            raise wa.ExperimentError("fake cancellation mapper never reached its child process")
                        pids=json.loads(pids_file.read_bytes());proc.send_signal(signal.SIGTERM)
                    code=proc.wait(timeout=20)
                finally:
                    if proc.poll() is None:
                        proc.send_signal(signal.SIGTERM)
                        try:proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:proc.kill();proc.wait()
            attempts=list(run.glob(".long-cigar-attempt-*"))
            if len(attempts)!=1:raise wa.ExperimentError("lifecycle case has missing/duplicate adapter attempt")
            receipt=json.loads((attempts[0]/"server-alignment.json").read_bytes())
            if (attempts[0]/"prior-result.paf").read_bytes()!=b"previous stale result\n":
                raise wa.ExperimentError("old result was destroyed or silently reused")
            if mode=="native":
                if code!=0 or result.read_bytes()!=b"opaque native test bytes\n" or receipt["status"]!="native_complete_published":
                    raise wa.ExperimentError("native test bytes were not published unchanged")
            else:
                if code==0 or result.exists() or receipt["status"]!="refused_or_failed":
                    raise wa.ExperimentError("error/cancellation published a stale/partial success")
                if (attempts[0]/"selective/original-guidance").exists():
                    raise wa.ExperimentError("non-target failure entered recovery")
            row={"case":mode,"returncode":code,"expected_behavior":True,"attempt_receipt_sha256":wa.sha256(attempts[0]/"server-alignment.json")}
            if mode=="cancel":
                deadline=time.monotonic()+5
                while any(live(pid) for pid in pids) and time.monotonic()<deadline:time.sleep(.05)
                if any(live(pid) for pid in pids):raise wa.ExperimentError("cancellation abandoned a live mapping process")
                row.update(child_processes_terminated=True,pids=pids)
            report["cases"].append(row)
        if sa.validate_runtime(runtime)!=checked:raise wa.ExperimentError("package changed during lifecycle controls")
        report.update(status="all_packaged_lifecycle_controls_passed",package_unchanged=True)
    except BaseException as exc:
        report.update(status="refused_or_failed",error=repr(exc));raise
    finally:
        wa.write_json(out/"lifecycle-controls.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","no_files_or_commands_started":True,"real_minimap2_recovery_test":False}));return 0
    try:report=experiment(args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"refused_or_failed","error":str(exc)}));return 2
    print(json.dumps({"status":report["status"],"cases":len(report["cases"])}));return 0


if __name__=="__main__":raise SystemExit(main())
