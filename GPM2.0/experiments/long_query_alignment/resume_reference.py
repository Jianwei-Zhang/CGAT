"""Internal, journaled handoff of unfinished initial-reference commands only.

Called by the separate branch package INSIDE the existing run.sh workspace lock.
Never launches analysis, edits FASTA/results/checkpoints/GRT code, or asks the
customer to create configuration. Unsupported/custom provenance refuses unchanged.
Implementation only; no current handoff/package/customer acceptance is claimed.
"""
from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import socket
import stat
import subprocess
import tempfile

import build_native_chain_state as build
import native_chain_state as nst
import server_alignment as sa
import windowed_alignment as wa

BASE = "resume-base.json"
PREFIX = "long-cigar-handoff-"
MAX_METADATA = 4*1024**2
MAX_COMMAND = 1024**2
NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


def regular(root,name,*,optional=False):
    part = PurePosixPath(name)
    if not name or part.is_absolute() or ".." in part.parts or "\\" in name:
        raise wa.ExperimentError("reference handoff path escaped its declared root")
    path = root.joinpath(*part.parts)
    for ancestor in (path,*path.parents):
        if ancestor==root:
            break
        if ancestor.is_symlink():
            raise wa.ExperimentError("reference handoff refuses symlinked code/metadata paths")
    if not path.exists() and optional:
        return path
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise wa.ExperimentError(f"reference handoff requires a regular file: {path}")
    return path


def small(path,limit=MAX_METADATA):
    if path.stat().st_size>limit:
        raise wa.ExperimentError("reference handoff metadata/command exceeds its explicit bound")
    with path.open("rb") as source:
        data = source.read(limit+1)
    if len(data)>limit:
        raise wa.ExperimentError("reference handoff file changed beyond its supported bound")
    return data


def json_file(root,name):
    return json.loads(small(regular(root,name)))


def save_json(path,value):
    data = (json.dumps(value,indent=2,ensure_ascii=True)+"\n").encode()
    fd,name = tempfile.mkstemp(prefix=".journal-",dir=path.parent)
    with os.fdopen(fd,"wb") as out:
        out.write(data); out.flush(); os.fsync(out.fileno())
    os.replace(name,path)
    fd = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def owner_locked(workspace,run_id):
    owner = json_file(workspace,".run_all/lock/owner.json")
    if (type(owner) is not dict or type(owner.get("workspace")) is not str
            or owner.get("run_id")!=run_id or owner.get("pid")!=os.getpid()
            or owner.get("hostname")!=socket.gethostname()):
        raise wa.ExperimentError("reference handoff requires the caller's actual existing workspace lock")
    try:
        same_workspace = Path(owner["workspace"]).samefile(workspace)
    except OSError as exc:
        raise wa.ExperimentError("reference lock workspace identity cannot be verified") from exc
    if not same_workspace:
        raise wa.ExperimentError("reference handoff lock belongs to another workspace")


def direct_process_guard(workspace,*,proc_root=None):
    """Supplement the normal cross-host workspace lock for local direct jobs."""
    proc = Path("/proc") if proc_root is None else Path(proc_root)
    if not proc.is_dir():
        raise wa.ExperimentError("reference resume handoff requires Linux process inspection")
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():
            continue
        try:
            with (process/"cmdline").open("rb") as source:
                raw = source.read(1024**2+1)
            if len(raw)>1024**2:
                continue
            args = [a for a in raw.decode(errors="replace").split("\0") if a]
        except OSError:
            continue
        if not args:
            continue
        mapper = Path(args[0]).name=="minimap2"
        for position,arg in enumerate(args):
            # A bare executable/option value is not a path relative to cwd.
            # In particular "minimap2", "2" (-t) and "asm10" must not invent
            # files inside runs/ and falsely block a completely unrelated job.
            if mapper and position==0:
                continue
            if arg.startswith("-") or "\n" in arg:
                continue
            if not mapper and not arg.endswith((".sh",".py")):
                continue
            try:
                path = Path(arg)
                if not path.is_absolute():
                    path = (process/"cwd").resolve(strict=True)/path
                path = path.resolve()
                if (mapper and not Path(arg).is_absolute() and "/" not in arg
                        and not path.exists() and args[position-1] not in ("-o","-d")):
                    continue
            except (FileNotFoundError,ProcessLookupError):
                continue
            except (OSError,RuntimeError):
                if str(workspace) in arg or ".prepare_lib/" in arg:
                    raise wa.ExperimentError(f"cannot inspect possible reference process PID {process.name}")
                continue
            if workspace not in path.parents:
                continue
            relative = path.relative_to(workspace)
            if (relative.parts[0] in ("runs",".prepare_lib") or path==workspace/"run_all.sh"
                    or mapper and relative.parts[0]=="data"):
                raise wa.ExperimentError(f"reference handoff refuses an active standalone workspace process: PID {process.name}")


def runtime_tree(root):
    checked = sa.validate_runtime(root)
    manifest = json_file(root,sa.MANIFEST)
    base_path = regular(root,BASE)
    if wa.sha256(base_path)!=manifest.get("handoff_base_sha256"):
        raise wa.ExperimentError("reference handoff lacks a package-bound baseline receipt")
    native = nst.validate_bundle(root/"native"/build.host_platform())
    names = [*sa.RUNTIME_FILES,sa.MANIFEST,BASE,
             f"native/{native['platform']}/{build.BINARY}",f"native/{native['platform']}/{build.MANIFEST}"]
    files = {name:{"sha256":wa.sha256(regular(root,name)),"mode":stat.S_IMODE((root/name).stat().st_mode)} for name in names}
    return checked,json_file(root,BASE),files


def compare_tree(root,files):
    if root.is_symlink() or not root.is_dir():
        return False
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual!=set(files):
        return False
    return all(wa.sha256(regular(root,n))==r["sha256"] and stat.S_IMODE((root/n).stat().st_mode)==r["mode"] for n,r in files.items())


def quote_values(values):
    # The original generator uses Bash printf %q. Format DATA arguments in one
    # fixed builtin-only child; never eval a saved command or interpolate data.
    text = subprocess.check_output(["bash","-c",'printf "%q\\n" "$@"',"cgat-reference-quote",*map(str,values)],text=True,timeout=5)
    rows = text.splitlines()
    if len(rows)!=len(values):
        raise wa.ExperimentError("cannot preserve original generated-shell quoting")
    return rows


def render_commands(workspace,run_dir,target,query,threads):
    qr,qt,qq,unknown,adapter,qw = quote_values([run_dir,target,query,"unknown\n",
        workspace/".prepare_lib/tools/long_cigar_recovery/server_alignment.py",workspace])
    prefix = ("#!/usr/bin/env bash\nset -euo pipefail\n"+f"cd {qr}\n"+
              f"(minimap2 --version > tool_version.txt 2>&1 || printf {unknown} > tool_version.txt)\n")
    cpu = '"${GPM_TASK_THREADS:-'+str(threads)+'}"'
    old = prefix+f"minimap2 -c -x asm10 -t {cpu} -o result.paf {qt} {qq} > stdout.log 2> stderr.log\n"
    new = prefix+f"exec python3 {adapter} --server-dir {qw} --run-dir {qr} --target {qt} --query {qq} --threads {cpu} --preset asm10 --result result.paf > stdout.log 2> stderr.log\n"
    return old.encode(),new.encode()


def table(workspace,name):
    text = small(regular(workspace,name)).decode("utf-8")
    return list(csv.DictReader(text.splitlines(),delimiter="\t"))


def metadata(workspace):
    options = table(workspace,"metadata/prepare_options.tsv")
    if any(set(row)!={"key","value"} for row in options) or len({r["key"] for r in options})!=len(options):
        raise wa.ExperimentError("reference handoff options are duplicated/malformed")
    options = {r["key"]:r["value"] for r in options}
    if options.get("alignment_engine")!="minimap2" or options.get("minimap_preset")!="asm10":
        return options,None,None
    if options.get("grt_workflow")!="gpm_grt_precomputed_v2":
        raise wa.ExperimentError("reference handoff does not migrate a different prepared workflow")
    if type(options.get("threads")) is not str or not re.fullmatch(r"[1-9][0-9]{0,5}",options["threads"]):
        raise wa.ExperimentError("reference handoff requires the original positive thread budget")
    references = table(workspace,"metadata/reference.tsv")
    datasets = table(workspace,"metadata/datasets.tsv")
    if len(references)!=1 or not datasets or len({r.get("dataset_name") for r in datasets})!=len(datasets):
        raise wa.ExperimentError("reference handoff input identities are missing/duplicated")
    if any(type(r.get("dataset_name")) is not str or not NAME.fullmatch(r["dataset_name"]) for r in datasets):
        raise wa.ExperimentError("reference handoff dataset identity is unsupported")
    reference = regular(workspace,references[0]["fasta_relpath"])
    queries = {r["dataset_name"]:regular(workspace,r["fasta_relpath"]) for r in datasets}
    return options,reference,queries


def baseline_matches(workspace,server_source,base):
    profiles = base.get("source_profiles") if type(base) is dict else None
    if (type(base) is not dict or base.get("schema")!=1 or type(profiles) is not list or not profiles):
        raise wa.ExperimentError("reference handoff baseline source inventory is incomplete")
    tools = workspace/".prepare_lib/tools"
    actual = {"tools/"+p.relative_to(tools).as_posix() for p in tools.rglob("*.py")
              if "__pycache__" not in p.parts and p.relative_to(tools).parts[0]!="long_cigar_recovery"
              and not p.relative_to(tools).parts[0].startswith(".long-cigar-runtime-")}
    for profile in profiles:
        hashes = profile.get("base_tools_files_sha256") if type(profile) is dict else None
        if (type(hashes) is not dict or not hashes or profile.get("reference_launch_checkpoint_recipe_equal") is not True):
            raise wa.ExperimentError("reference handoff baseline profile is malformed")
        if any(not n.startswith("tools/") or not n.endswith(".py") for n in hashes):
            raise wa.ExperimentError("reference handoff baseline escaped its declared code scope")
        if actual!=set(hashes):
            continue
        equal = True
        for name,expected in hashes.items():
            staged = regular(workspace,".prepare_lib/"+name)
            allowed = {expected}
            if name in ("tools/run_outer_checkpoints.py","tools/server_run.py"):
                allowed.add(wa.sha256(regular(server_source,name)))
            if wa.sha256(staged) not in allowed:
                equal = False
                break
        if equal:
            return profile["revision"]
    raise wa.ExperimentError("staged Server provenance differs from the package-bound compatible source profiles; preserving the workspace unchanged")


def atomic_script(path,data,mode):
    fd,name = tempfile.mkstemp(prefix=".long-cigar-command-",dir=path.parent)
    with os.fdopen(fd,"wb") as out:
        out.write(data); out.flush(); os.fsync(out.fileno())
    os.chmod(name,mode)
    os.replace(name,path)


def validate_journal_commands(journal):
    seen = set()
    for item in journal["commands"]:
        if type(item) is not dict:
            raise wa.ExperimentError("reference handoff journal has a malformed command entry")
        name = str(item.get("unit_id","")).removeprefix("ref:")
        if (not NAME.fullmatch(name) or item.get("unit_id")!="ref:"+name
                or item.get("path")!=f"runs/{name}_vs_ref/command.sh" or name in seen
                or type(item.get("mode")) is not int or not 0<=item["mode"]<=0o777
                or type(item.get("backup")) is not str
                or not re.fullmatch(r"[0-9]{6}\.command\.sh",item["backup"])
                or any(type(item.get(k)) is not str or not re.fullmatch(r"[0-9a-f]{64}",item[k]) for k in ("old_sha256","new_sha256"))):
            raise wa.ExperimentError("reference handoff journal escaped the exact reference-command scope")
        seen.add(name)


def restore_commands(workspace,backup,journal):
    validate_journal_commands(journal)
    for item in reversed(journal["commands"]):
        path = regular(workspace,item["path"])
        before = regular(backup,item["backup"])
        old = small(before,MAX_COMMAND)
        if hashlib.sha256(old).hexdigest()!=item["old_sha256"]:
            raise wa.ExperimentError("reference handoff backup identity changed; refusing rollback")
        actual = wa.sha256(path)
        if actual==item["old_sha256"]:
            continue
        if actual!=item["new_sha256"]:
            raise wa.ExperimentError("reference command changed outside the handoff; refusing to overwrite user edits")
        atomic_script(path,old,item["mode"])
    journal.update(status="rolled_back",analysis_started=False,runtime_preserved_for_retry=True)
    save_json(backup/"journal.json",journal)


def recover_incomplete(workspace,run_id):
    recovered = []
    for backup in sorted((workspace/".run_all").glob(PREFIX+"*")):
        if backup.is_symlink() or not backup.is_dir():
            raise wa.ExperimentError("reference handoff backup root must be an original directory")
        if not (backup/"journal.json").exists():
            continue  # No mutation is allowed before the durable journal exists.
        journal = json_file(backup,"journal.json")
        if (journal.get("schema")!=1 or journal.get("workspace")!=str(workspace)
                or type(journal.get("commands")) is not list):
            raise wa.ExperimentError("reference handoff journal has foreign/invalid provenance")
        validate_journal_commands(journal)
        if journal.get("status") in ("applied","rolled_back"):
            continue
        if journal.get("status") not in ("applying","rolling_back"):
            raise wa.ExperimentError("reference handoff journal has an unknown completion state")
        owner_locked(workspace,run_id)
        with ExitStack() as stack:
            for item in journal["commands"]:
                stack.enter_context(sa.task_lock(regular(workspace,item["path"]).parent))
            direct_process_guard(workspace)
            restore_commands(workspace,backup,journal)
        recovered.append(str(backup))
    return recovered


def handoff(workspace,server_source,run_id,units,manager):
    workspace,server_source = Path(workspace).resolve(),Path(server_source).resolve()
    owner_locked(workspace,run_id)
    direct_process_guard(workspace)
    recovered = recover_incomplete(workspace,run_id)
    runtime_source = server_source/"tools/long_cigar_recovery"
    checked = sa.validate_runtime(runtime_source)  # No companion lookup on a completed/native-only no-op.
    snapshots = {name:wa.sha256(regular(workspace,name)) for name in (
        "metadata/prepare_options.tsv","metadata/reference.tsv","metadata/datasets.tsv",".run_all/plan.tsv")}
    options,target,queries = metadata(workspace)
    if any(wa.sha256(regular(workspace,n))!=h for n,h in snapshots.items()):
        raise wa.ExperimentError("workspace metadata changed during reference handoff planning")
    report = {"schema":1,"scope":"unfinished_initial_reference_only","analysis_started":False,
              "production_ready":False,"recovered_output_admission":"closed_pending_final_acceptance",
              "preserved_completed_units":[],"already_adapted_units":[],"prior_recoveries":recovered}
    if target is None:
        return {**report,"status":"not_applicable_preset_unchanged"}
    references = [u.unit_id for u in units if u.unit_id.startswith("ref:")]
    if len(references)!=len(set(references)) or set(references)!={"ref:"+n for n in queries}:
        raise wa.ExperimentError("reference handoff plan does not cover exactly the prepared datasets")
    status_path = regular(workspace,"logs/status.tsv",optional=True)
    if status_path.exists():
        snapshots["logs/status.tsv"] = wa.sha256(status_path)
    statuses = table(workspace,"logs/status.tsv") if status_path.exists() else []
    if status_path.exists() and wa.sha256(status_path)!=snapshots["logs/status.tsv"]:
        raise wa.ExperimentError("reference prior status changed during handoff planning")
    if len({r.get("unit_id") for r in statuses})!=len(statuses):
        raise wa.ExperimentError("reference handoff prior status has duplicated execution units")
    statuses = {r["unit_id"]:r.get("state") for r in statuses}
    changes = []
    runtime = workspace/".prepare_lib/tools/long_cigar_recovery"
    runtime_present = runtime.exists() or runtime.is_symlink()
    for unit in units:
        if not unit.unit_id.startswith("ref:"):
            continue
        name = unit.unit_id[4:]
        expected_path = f"runs/{name}_vs_ref/command.sh"
        if name not in queries or unit.command_relpath!=expected_path:
            raise wa.ExperimentError("reference handoff refuses custom/missing plan-to-dataset command ownership")
        path = regular(workspace,expected_path)
        prepared = manager.prepare(unit.unit_id,unit.command_relpath)
        if prepared is None:
            raise wa.ExperimentError("reference handoff has no original checkpoint contract")
        valid,reason = manager.validate(prepared)
        if valid:
            report["preserved_completed_units"].append(unit.unit_id)
            continue
        if statuses.get(unit.unit_id)=="success":
            raise wa.ExperimentError("a previously completed reference checkpoint is now incompatible; refusing to reclassify it as the reported failed task")
        old,new = render_commands(workspace,path.parent,target,queries[name],options["threads"])
        data = small(path,MAX_COMMAND)
        if data==new:
            report["already_adapted_units"].append(unit.unit_id)
            continue
        if data!=old:
            raise wa.ExperimentError(f"initial-reference command is customized or from an unsupported generator: {unit.unit_id}; not overwriting it")
        manifest = regular(workspace,f"runs/{name}_vs_ref/alignment_tasks.json",optional=True)
        if manifest.exists():
            payload = json.loads(small(manifest))
            if (payload.get("version") not in (1,2,3) or len(payload.get("tasks",[]))!=1
                    or payload["tasks"][0].get("command")!=unit.command_relpath):
                raise wa.ExperimentError("reference handoff refuses a custom/batched alignment task manifest")
        changes.append({"unit_id":unit.unit_id,"path":expected_path,"old":data,"new":new,
                        "mode":stat.S_IMODE(path.stat().st_mode),"checkpoint_reason":reason})
    if not changes:
        if report["already_adapted_units"] and sa.validate_runtime(runtime)["sha256"]!=checked["sha256"]:
            raise wa.ExperimentError("adapted reference command has a missing/different packaged runtime")
        return {**report,"status":"no_reference_command_handoff_needed"}
    checked,base,files = runtime_tree(runtime_source)
    matched_profile = baseline_matches(workspace,server_source,base)
    report["staged_source_profile"] = matched_profile
    if runtime_present and not compare_tree(runtime,files):
        raise wa.ExperimentError("a different branch runtime already exists; preserving it rather than silently replacing shared code")
    with ExitStack() as stack:
        for row in changes:
            stack.enter_context(sa.task_lock((workspace/row["path"]).parent))
        owner_locked(workspace,run_id)
        direct_process_guard(workspace)
        backup = Path(tempfile.mkdtemp(prefix=PREFIX,dir=workspace/".run_all"))
        journal = {**report,"schema":1,"status":"applying","workspace":str(workspace),"run_id":run_id,
                   "source_runtime_sha256":checked["sha256"],"commands":[],"preserved_logs":[]}
        for i,row in enumerate(changes):
            before = f"{i:06d}.command.sh"
            with (backup/before).open("xb") as out:
                out.write(row["old"]); out.flush(); os.fsync(out.fileno())
            journal["commands"].append({k:row[k] for k in ("unit_id","path","mode","checkpoint_reason")}|{
                "backup":before,"old_sha256":hashlib.sha256(row["old"]).hexdigest(),
                "new_sha256":hashlib.sha256(row["new"]).hexdigest()})
            for name in ("stdout.log","stderr.log","tool_version.txt"):
                source = regular(workspace,str(PurePosixPath(row["path"]).parent/name),optional=True)
                if source.exists():
                    saved = backup/f"{i:06d}.{name}"
                    shutil.copy2(source,saved)
                    digest = wa.sha256(source)
                    if wa.sha256(saved)!=digest:
                        raise wa.ExperimentError("original reference log changed while being retained")
                    journal["preserved_logs"].append({"path":str(source.relative_to(workspace)),"backup":saved.name,"sha256":digest})
        validate_journal_commands(journal)
        save_json(backup/"journal.json",journal)
        try:
            if not runtime_present:
                staging = Path(tempfile.mkdtemp(prefix=".long-cigar-runtime-",dir=runtime.parent))
                for name,record in files.items():
                    destination = staging/name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(runtime_source/name,destination)
                if not compare_tree(staging,files) or runtime.exists() or runtime.is_symlink():
                    raise wa.ExperimentError("staged runtime changed or a concurrent installation appeared")
                staging.rename(runtime)
            for i,row in enumerate(changes):
                owner_locked(workspace,run_id)
                if (any(wa.sha256(regular(workspace,n))!=h for n,h in snapshots.items())
                        or wa.sha256(regular(workspace,row["path"]))!=journal["commands"][i]["old_sha256"]):
                    raise wa.ExperimentError("workspace metadata/command changed during handoff; not guessing intent")
                atomic_script(workspace/row["path"],row["new"],row["mode"])
            if (any(wa.sha256(regular(workspace,r["path"]))!=r["new_sha256"] for r in journal["commands"])
                    or not compare_tree(runtime,files) or not compare_tree(runtime_source,files)
                    or sa.validate_runtime(runtime_source)!=checked
                    or any(wa.sha256(regular(workspace,n))!=h for n,h in snapshots.items())):
                raise wa.ExperimentError("reference runtime/metadata changed before handoff completion")
            if baseline_matches(workspace,server_source,base)!=matched_profile:
                raise wa.ExperimentError("staged Server source profile changed during handoff")
            journal.update(status="applied",analysis_started=False)
            save_json(backup/"journal.json",journal)
        except BaseException as exc:
            journal.update(status="rolling_back",error=f"{type(exc).__name__}: {exc}")
            save_json(backup/"journal.json",journal)
            restore_commands(workspace,backup,journal)
            raise
    return {**report,"status":"unfinished_reference_commands_adapted","backup":str(backup),
            "adapted_units":[r["unit_id"] for r in changes],"analysis_started":False}
