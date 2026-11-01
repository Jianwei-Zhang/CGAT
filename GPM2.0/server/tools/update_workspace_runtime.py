#!/usr/bin/env python3
"""Verified, backed-up code-only update of Server tools and one prepared runtime.

Use a freshly extracted official archive with SOURCE.json file hashes. This
never installs dependencies, rewrites a generated plan, deletes checkpoints,
or runs analysis. The original tool directory's unlisted/user files remain.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
ENTRYPOINTS = {
    "tools/grt_step2.py", "tools/grt_step3.py", "tools/grt_telomere_finalize.py",
    "tools/grt_evidence_package.py", "tools/grt_display_evidence.py",
    "tools/run_all_runner.py", "tools/run_progress.py", "tools/view_run_log.py",
}
LGZ_ENTRYPOINTS = {
    "tools/grt_app_package.py",
    "tools/grt_contract.py",
    "tools/grt_display_evidence.py",
    "tools/grt_evidence_package.py",
    "tools/grt_prepare_inputs.py",
    "tools/grt_step1.py",
    "tools/grt_step2.py",
    "tools/grt_step3.py",
    "tools/grt_telomere_finalize.py",
    "tools/lgz_app_package.py",
    "tools/lgz_compat.py",
    "tools/lgz_contract.py",
    "tools/lgz_display_evidence.py",
    "tools/lgz_evidence_package.py",
    "tools/lgz_prepare_inputs.py",
    "tools/lgz_step1.py",
    "tools/lgz_step2.py",
    "tools/lgz_step3.py",
    "tools/lgz_telomere_finalize.py",
    "tools/render_server_report.py",
    "tools/run_outer_checkpoints.py",
    "tools/run_orchestration.py",
    "tools/server_report.py",
    "tools/server_report_collect.py",
    "tools/server_run.py",
    "tools/update_server.py",
    "tools/update_workspace_runtime.py",
}

BINDING = "skills/gpm-server/server-tools.path"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if not relative or parts.is_absolute() or ".." in parts.parts or "\\" in relative:
        raise ValueError(f"unsafe relative path: {relative!r}")
    current = root
    for index, part in enumerate(parts.parts):
        current = current / part
        if current.is_symlink():
            raise ValueError(f"refusing symlink: {current}")
        if current.exists() and index < len(parts.parts) - 1 and not current.is_dir():
            raise ValueError(f"non-directory path component: {current}")
    if current.exists() and not current.is_file():
        raise ValueError(f"not a regular file: {current}")
    return current


def write_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.update-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def engine_hash(tools: Path) -> str:
    try:
        from lgz_compat import engine_source_files
    except ModuleNotFoundError:
        from .lgz_compat import engine_source_files
    files = engine_source_files(tools)
    payload = {str(path.relative_to(tools).as_posix()): digest(path.read_bytes()) for path in files}
    return digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def verified_source(root: Path, revision: str) -> dict[str, dict]:
    source = regular_path(root, "SOURCE.json")
    metadata = json.loads(source.read_text())
    if metadata.get("git_revision") != revision:
        raise ValueError("SOURCE.json Git revision does not match --expected-revision")
    files = metadata.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("this archive has no source-file hash manifest; use the new update package")
    manifest = {}
    for relative, record in files.items():
        path = regular_path(root, relative)
        mode = record.get("mode")
        if mode not in (0o644, 0o755) or not path.is_file() or digest(path.read_bytes()) != record.get("sha256"):
            raise ValueError(f"source integrity check failed: {relative}")
        manifest[relative] = dict(record)
    canonical = (any(key.startswith("tools/lgz_") for key in manifest)
                 or (root / "tools/lgz_core").exists()
                 or any((root / "tools").glob("lgz_*.py")))
    required = ENTRYPOINTS | {"run.sh", "prepare.sh", "install.sh", "tools/server_run.py"}
    if canonical:
        required |= LGZ_ENTRYPOINTS
    for relative in required:
        if relative not in manifest:
            raise ValueError(f"source manifest is incomplete: {relative}")
    for name in (("grt_core", "lgz_core") if canonical else ("grt_core",)):
        if f"tools/{name}/__init__.py" not in manifest:
            raise ValueError(f"source manifest is incomplete: tools/{name}/__init__.py")
        expected_core = {key.removeprefix("tools/") for key in manifest
                         if key.startswith(f"tools/{name}/") and key.endswith(".py")}
        actual_core = {path.relative_to(root / "tools").as_posix()
                       for path in (root / "tools" / name).rglob("*.py")}
        if not expected_core or expected_core != actual_core:
            raise ValueError(f"source core contains missing or unmanifested modules: {name}")
    manifest["SOURCE.json"] = {"sha256": digest(source.read_bytes()), "mode": 0o644}
    return manifest


def validate_targets(workspace: Path, tools_root: Path, source: Path, *,
                     allow_nested_workspace: bool = False) -> None:
    for first, second in ((workspace, tools_root), (source, workspace), (source, tools_root)):
        if allow_nested_workspace and first == workspace and second == tools_root and tools_root in workspace.parents:
            continue
        if first == second or first in second.parents or second in first.parents:
            raise ValueError("source, tools directory and workspace must be separate non-nested directories")
    for root in (workspace, tools_root):
        for relative in (".run_all", ".run_all/lock", ".run_all/lock/owner.json"):
            if (root / relative).is_symlink():
                raise ValueError(f"refusing symlinked lock state: {root / relative}")
    for relative in ("run.sh", "prepare.sh", "install.sh", "tools/server_run.py"):
        if not regular_path(tools_root, relative).is_file():
            raise ValueError(f"not an installed Server tools directory: {tools_root}")
    for relative in ("run_all.sh", "run_grt_step2.sh", "run_grt_step3.sh",
                     ".prepare_lib/tools/grt_step2.py", ".prepare_lib/tools/grt_step3.py"):
        if not regular_path(workspace, relative).is_file():
            raise ValueError(f"workspace lacks independent Step2/Step3 runtime: {relative}")
    package = regular_path(workspace, "metadata/package.tsv")
    with package.open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 1 or rows[0].get("workflow") != "gpm_grt_precomputed_v2" or rows[0].get("schema_version") != "2":
        raise ValueError("unsupported workspace workflow/schema; no legacy migration is performed")
    for root in (workspace, tools_root):
        regular_path(root, "tools/grt_core/__init__.py" if root == tools_root
                     else ".prepare_lib/tools/grt_core/__init__.py")


def check_direct_processes(workspace: Path, tools_root: Path) -> None:
    # Runner's lock protects normal runs. Also catch standalone generated LGZ
    # scripts, which can bypass run_all.sh. Other-host work must be stopped by
    # the operator; a foreign-host runner lock is never stolen.
    proc = Path("/proc")
    if not proc.is_dir():
        raise ValueError("runtime updates require Linux process inspection")
    prefixes = (str(workspace / ".prepare_lib") + "/", str(tools_root) + "/")
    scripts = {str(workspace / name) for name in
               ("run_all.sh", "run_grt_step2.sh", "run_grt_step3.sh",
                "run_grt_telomere_finalize.sh", "finalize_grt_evidence.sh",
                "prepare_grt_inputs.sh", "prepare_lgz_inputs.sh", "run_lgz_step1.sh",
                "run_lgz_step2.sh", "run_lgz_step3.sh", "run_lgz_telomere_finalize.sh",
                "finalize_lgz_evidence.sh")}
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            args = (process / "cmdline").read_bytes().decode(errors="replace").split("\0")
        except OSError:
            continue
        for arg in args:
            if not arg or arg.startswith("-") or "\n" in arg:
                continue
            if arg in scripts or arg.startswith(prefixes):
                raise ValueError(f"stop the active Server process before updating: PID {process.name}")
            # /proc stores argv as supplied: relative scripts must be resolved
            # from THAT process's cwd, not the updater's cwd. Resolve aliases
            # too, since update() canonicalizes both installation roots.
            if "/" not in arg and not arg.endswith((".py", ".sh")):
                continue
            try:
                path = Path(arg)
                if not path.is_absolute():
                    path = (process / "cwd").resolve(strict=True) / path
                resolved = str(path.resolve())
            except (FileNotFoundError, ProcessLookupError):
                continue  # process exited during inspection
            except (OSError, RuntimeError) as exc:
                known = Path(arg).name in {Path(name).name for name in scripts | ENTRYPOINTS}
                if known or ".prepare_lib/" in arg:
                    raise ValueError(f"cannot inspect possible Server process PID {process.name}") from exc
                continue
            if resolved in scripts or resolved.startswith(prefixes):
                raise ValueError(f"stop the active Server process before updating: PID {process.name}")


def workspace_lock(workspace: Path):
    # Load from this verified package, not from a partially updated target.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from run_all_runner import WorkspaceLock
    finally:
        sys.path.pop(0)
    return WorkspaceLock(workspace, "runtime-update-" + uuid.uuid4().hex)


def restore_files(journal: dict, backup: Path, *, verify_current: bool) -> None:
    roots = ({key: Path(value) for key, value in journal["roots"].items()} if "roots" in journal else
             {"tools": Path(journal["tools_root"]), "runtime": Path(journal["workspace"]) / ".prepare_lib"})
    for item in reversed(journal["files"]):
        path = regular_path(roots[item["kind"]], item["relative"])
        if verify_current and path.exists():
            allowed = {item["new_sha256"], item.get("old_sha256")}
            if digest(path.read_bytes()) not in allowed:
                raise ValueError(f"target changed after update; refusing rollback: {path}")
        if item["existed"]:
            saved = regular_path(backup, f"original/{item['kind']}/{item['relative']}")
            if digest(saved.read_bytes()) != item["old_sha256"]:
                raise ValueError(f"backup integrity check failed: {saved}")
    for item in reversed(journal["files"]):
        path = regular_path(roots[item["kind"]], item["relative"])
        if item["existed"]:
            saved = regular_path(backup, f"original/{item['kind']}/{item['relative']}")
            data = saved.read_bytes()
            if digest(data) != item["old_sha256"]:
                raise ValueError(f"backup integrity check failed: {saved}")
            write_atomic(path, data, item["old_mode"])
        else:
            path.unlink(missing_ok=True)


def update(source: Path, workspace: Path, tools_root: Path, revision: str, *, apply: bool) -> dict:
    source, workspace, tools_root = source.resolve(), workspace.resolve(), tools_root.resolve()
    manifest = verified_source(source, revision)
    validate_targets(workspace, tools_root, source)
    runtime = workspace / ".prepare_lib"
    canonical = "tools/lgz_core/__init__.py" in manifest
    selected = {relative: record for relative, record in manifest.items()
                if relative == "SOURCE.json" or relative in ENTRYPOINTS | LGZ_ENTRYPOINTS
                or relative.startswith(("tools/grt_core/", "tools/lgz_core/"))
                or canonical and relative.startswith("tools/") and (
                    len(PurePosixPath(relative).parts) == 2 and relative.endswith(".py")
                    or relative.startswith("tools/long_cigar_recovery/"))}
    # Old untracked Python modules would contaminate the content fingerprint.
    for target in (tools_root / "tools", runtime / "tools"):
        extra = {p.relative_to(target.parent).as_posix()
                 for name in ("grt_core", "lgz_core")
                 for p in (target / name).rglob("*.py")} - set(selected)
        if extra:
            raise ValueError(f"unexpected old core modules; inspect before updating: {sorted(extra)}")
        if canonical and any(name.startswith("tools/long_cigar_recovery/") for name in selected):
            extra_runtime = {p.relative_to(target.parent).as_posix()
                             for p in (target / "long_cigar_recovery").rglob("*")
                             if p.is_file() and "__pycache__" not in p.parts} - set(selected)
            if extra_runtime:
                raise ValueError(f"unexpected recovery runtime files; inspect before updating: {sorted(extra_runtime)}")
    plan = []
    preserved = []
    for kind, root, files in (("tools", tools_root, manifest), ("runtime", runtime, selected)):
        for relative, record in sorted(files.items()):
            path = regular_path(root, relative)
            if kind == "tools" and relative == BINDING and path.exists():
                preserved.append(str(path))
                continue
            existed = path.exists()
            plan.append({"kind": kind, "relative": relative, "existed": existed,
                         "old_sha256": digest(path.read_bytes()) if existed else None,
                         "old_mode": stat.S_IMODE(path.stat().st_mode) if existed else None,
                         "new_sha256": record["sha256"], "new_mode": record["mode"]})
    result = {"status": "verified_dry_run", "source_revision": revision,
              "workspace": str(workspace), "tools_root": str(tools_root),
              "files": len(plan), "preserved_bindings": preserved,
              "analysis_started": False}
    check_direct_processes(workspace, tools_root)
    if not apply:
        return result
    tools_lock = workspace_lock(tools_root)
    tools_lock.acquire()
    lock = workspace_lock(workspace)
    try:
        lock.acquire()
    except BaseException:
        tools_lock.release()
        raise
    backup = None
    try:
        check_direct_processes(workspace, tools_root)
        backup = Path(tempfile.mkdtemp(prefix="runtime-update-", dir=workspace / ".run_all"))
        journal = {**result, "status": "applying", "files": plan, "backup": str(backup)}
        for item in plan:
            root = tools_root if item["kind"] == "tools" else runtime
            path = regular_path(root, item["relative"])
            if path.exists() != item["existed"]:
                raise ValueError(f"target appeared/disappeared after planning: {path}")
            if item["existed"]:
                data = regular_path(root, item["relative"]).read_bytes()
                if digest(data) != item["old_sha256"]:
                    raise ValueError("target changed while preparing backup; retry only when idle")
                write_atomic(backup / "original" / item["kind"] / item["relative"], data, item["old_mode"])
        write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        try:
            for item in plan:
                root = tools_root if item["kind"] == "tools" else runtime
                data = regular_path(source, item["relative"]).read_bytes()
                if digest(data) != item["new_sha256"]:
                    raise ValueError("source changed after verification")
                write_atomic(regular_path(root, item["relative"]), data, item["new_mode"])
            for item in plan:
                root = tools_root if item["kind"] == "tools" else runtime
                if digest(regular_path(root, item["relative"]).read_bytes()) != item["new_sha256"]:
                    raise ValueError("installed file hash verification failed")
            expected_engine = engine_hash(source / "tools")
            if any(engine_hash(root / "tools") != expected_engine for root in (tools_root, runtime)):
                raise ValueError("installed core/entrypoint fingerprint mismatch")
        except BaseException:
            restore_files(journal, backup, verify_current=True)
            journal["status"] = "rolled_back_after_failure"
            write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
            raise
        result.update(status="updated", backup=str(backup), engine_sha256=expected_engine)
        journal.update(status="updated", engine_sha256=expected_engine)
        write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        return result
    finally:
        lock.release()
        tools_lock.release()


def rollback(backup: Path) -> dict:
    backup = backup.resolve()
    journal = json.loads(regular_path(backup, "journal.json").read_text())
    workspace = Path(journal["workspace"])
    tools_root = Path(journal["tools_root"])
    if any(not root.is_dir() or root.resolve() != root for root in (workspace, tools_root)):
        raise ValueError("rollback target roots moved or became symlinks")
    if backup.parent != workspace / ".run_all" or not backup.name.startswith("runtime-update-"):
        raise ValueError("backup is not a runtime-update journal inside this workspace")
    check_direct_processes(workspace, Path(journal["tools_root"]))
    tools_lock = workspace_lock(Path(journal["tools_root"]))
    tools_lock.acquire()
    lock = workspace_lock(workspace)
    try:
        lock.acquire()
    except BaseException:
        tools_lock.release()
        raise
    try:
        check_direct_processes(workspace, tools_root)
        restore_files(journal, backup, verify_current=True)
        journal["status"] = "rolled_back"
        write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        return {"status": "rolled_back", "backup": str(backup), "analysis_started": False}
    finally:
        lock.release()
        tools_lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tools-root", type=Path)
    parser.add_argument("--expected-revision")
    parser.add_argument("--apply", action="store_true", help="perform update; default only verifies and plans")
    parser.add_argument("--rollback", type=Path, metavar="BACKUP_DIR")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("terminated")))
    try:
        if args.rollback:
            result = rollback(args.rollback)
        else:
            if not all((args.workspace, args.tools_root, args.expected_revision)):
                parser.error("--workspace, --tools-root and --expected-revision are required")
            result = update(args.source_root, args.workspace, args.tools_root,
                            args.expected_revision, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
