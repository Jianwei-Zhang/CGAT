#!/usr/bin/env python3
"""Maintainer-only companion build; default PLAN ONLY, never a customer step.

Export the exact pinned upstream Git object into a fresh private source tree;
never compile a dirty checkout, modify minimap2, install over it, or invoke it.
The helper and its unvalidated receipt belong in a branch artifact, not Release.
No build or test has been executed during the current implementation phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import shutil
import subprocess
import tarfile

import windowed_alignment as wa

UPSTREAM_COMMIT = "3c28777e7e2dcc90f825de1b9f17a89cca7d4452"
VERSION = "2.31-r1302"
BINARY = "cgat-chain-state"
MANIFEST = "chain-state-helper.json"
FLAGS = ["-O2","-fno-fast-math","-ffp-contract=off","-fsigned-char","-D_FILE_OFFSET_BITS=64"]


def host_platform():
    machine = platform.machine().lower()
    if platform.system() != "Linux" or machine not in ("x86_64","aarch64","arm64"):
        raise wa.ExperimentError("native-state companion currently targets Linux x86_64/aarch64")
    return "linux-aarch64" if machine in ("aarch64","arm64") else "linux-x86_64"


def default_bundle():
    return Path(__file__).resolve().parent/"native"/host_platform()


def export_pinned_source(repository, destination):
    """Copy canonical Git archive bytes, not checkout files or stale objects."""
    commit = subprocess.check_output(["git","-C",str(repository),"rev-parse",UPSTREAM_COMMIT+"^{commit}"],text=True).strip()
    if commit != UPSTREAM_COMMIT:
        raise wa.ExperimentError("required upstream source object is unavailable")
    destination.mkdir(exist_ok=False)
    receipt = {}
    with (destination.parent/"source-export.stderr").open("xb") as err:
        process = subprocess.Popen(["git","-C",str(repository),"archive","--format=tar",commit],stdout=subprocess.PIPE,stderr=err)
        try:
            total = 0
            with tarfile.open(fileobj=process.stdout,mode="r|") as archive:
                for member in archive:
                    name = PurePosixPath(member.name)
                    if (name.is_absolute() or ".." in name.parts or not name.parts
                            or name.parts[0] == ".git" or "\\" in member.name):
                        raise wa.ExperimentError("unexpected source archive path")
                    target = destination.joinpath(*name.parts)
                    if member.isdir():
                        target.mkdir(parents=True,exist_ok=True)
                        continue
                    total += member.size
                    if (not member.isfile() or not 0 <= member.size <= 16*1024**2
                            or total > 256*1024**2 or member.name in receipt):
                        raise wa.ExperimentError("unsupported upstream source archive member")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with archive.extractfile(member) as src,target.open("xb") as out:
                        shutil.copyfileobj(src,out,1024**2)
                    target.chmod(0o755 if member.mode&0o111 else 0o644)
                    receipt[member.name] = wa.sha256(target)
            if process.wait(timeout=60):
                raise wa.ExperimentError("upstream source export failed")
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
    return receipt


def build(args):
    output = args.out.resolve()
    if output.exists() or args.jobs < 1 or args.jobs > 64:
        raise wa.ExperimentError("build requires a fresh output directory and 1..64 jobs")
    architecture = host_platform()
    compiler = shutil.which(args.compiler)
    make = shutil.which("make")
    archiver = shutil.which("ar")
    if not compiler or not make or not archiver:
        raise wa.ExperimentError("maintainer build toolchain is unavailable; do not ask the customer to build")
    compiler,make,archiver = (str(Path(p).resolve()) for p in (compiler,make,archiver))
    output.mkdir(parents=True,exist_ok=False)
    report = {"schema":1,"status":"building","protocol":1,"version":VERSION,"preset":"asm10",
              "upstream_commit":UPSTREAM_COMMIT,"platform":architecture,"binary":BINARY,
              "production_ready":False,"execution_validated":False,"customer_validated":False,
              "installed_minimap2_modified":False,"customer_compiler_required":False}
    try:
        source = output/"upstream-source"
        source_hashes = export_pinned_source(args.source.resolve(),source)
        from post_dp_selection import UPSTREAM
        for file,expected in UPSTREAM.items():
            if file != "version" and source_hashes.get(file.removesuffix("_sha256")) != expected:
                raise wa.ExperimentError("canonical source does not match the pinned selection/scoring contract")
        helper_source = Path(__file__).with_name("native_chain_state.c")
        shutil.copyfile(helper_source,output/"native_chain_state.c")
        shutil.copyfile(source/"LICENSE.txt",output/"MINIMAP2_LICENSE.txt")
        environment = {key:os.environ[key] for key in ("PATH","HOME","TMPDIR") if key in os.environ}
        environment.update(LC_ALL="C",TZ="UTC")
        commands = [[make,"-C",str(source),f"-j{args.jobs}","libminimap2.a",
                     "CC="+shlex.quote(compiler),"AR="+shlex.quote(archiver),"CFLAGS="+" ".join(FLAGS)]]
        if architecture == "linux-aarch64":
            commands[0].append("aarch64=1")
        commands.append([compiler,*FLAGS,"-I",str(source),str(output/"native_chain_state.c"),
                         str(source/"libminimap2.a"),"-lz","-lm","-lpthread","-o",str(output/BINARY)])
        wa.write_json(output/"build.commands.json",commands)
        for number,command in enumerate(commands):
            with (output/f"build-{number}.stdout").open("xb") as stdout,(output/f"build-{number}.stderr").open("xb") as stderr:
                subprocess.run(command,check=True,stdout=stdout,stderr=stderr,env=environment,timeout=600)
        # Verify upstream SOURCES stayed unchanged; no generated file is blessed
        # as a replacement source. Do not run the newly built helper here.
        if any(wa.sha256(source/file) != digest for file,digest in source_hashes.items()):
            raise wa.ExperimentError("upstream sources changed during companion build")
        report.update(status="built_unvalidated",binary_sha256=wa.sha256(output/BINARY),
                      helper_source_sha256=wa.sha256(output/"native_chain_state.c"),
                      builder_sha256=wa.sha256(Path(__file__)),source_files_sha256=source_hashes,
                      static_library_sha256=wa.sha256(source/"libminimap2.a"),cflags=FLAGS,
                      compiler={"path":compiler,"sha256":wa.sha256(Path(compiler))},
                      archiver={"path":archiver,"sha256":wa.sha256(Path(archiver))},
                      make={"path":make,"sha256":wa.sha256(Path(make))})
    except BaseException as exc:
        report.update(status="failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(output/MANIFEST,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True,help="Maintainer's upstream Git object store")
    parser.add_argument("--out",type=Path,default=None)
    parser.add_argument("--compiler",default="cc")
    parser.add_argument("--jobs",type=int,default=2)
    parser.add_argument("--execute",action="store_true",help="Explicit maintainer build, not a test or a customer command")
    args = parser.parse_args()
    args.out = args.out or default_bundle()
    if not args.execute:
        print(json.dumps({"status":"plan_only","source":str(args.source),"out":str(args.out),
                          "upstream_commit":UPSTREAM_COMMIT,"production_ready":False,
                          "note":"No files, compiler, make, minimap2 or mapping started."}))
        return 0
    print(json.dumps(build(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
