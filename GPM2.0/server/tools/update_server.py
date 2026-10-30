#!/usr/bin/env python3
"""Noninteractive, backed-up release update; optional pre-run exec handoff."""
from __future__ import annotations

from contextlib import ExitStack
import datetime as dt
import json
import os
from pathlib import Path
import signal
import stat
import shlex
import tarfile
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / "skills/gpm-server/scripts"))
sys.path.insert(0, str(ROOT / "tools"))
import official_download as downloads
import server_paths as paths
import update_workspace_runtime as core

SKILL_PREFIX = "skills/gpm-server/"
LEGACY_RUN_ALL = b'''#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "${server_dir}/.prepare_lib/tools/run_all_runner.py" --server-dir "$server_dir" "$@"
'''


def project_at(cwd):
    for directory in (cwd, *cwd.parents):
        if (directory / ".prepare_lib").exists() or (directory / "run_all.sh").exists():
            return paths.checked(directory)
    return None


def runtime_file(name):
    return (name.startswith("lib/") or name.startswith("tools/long_cigar_recovery/") or
            (name.startswith("contracts/") and name.endswith(".json")) or
            (name.startswith("tools/") and name.endswith(".py") and
             (len(Path(name).parts) == 2 or name.startswith("tools/grt_core/"))))


def metadata(root):
    file = core.regular_path(root, "SOURCE.json")
    return json.loads(file.read_text()) if file.exists() else {}


def skill_targets(tools, log=print):
    bundled = tools / "skills/gpm-server"
    candidates = [bundled, *paths.registered(tools)]
    if os.environ.get("GPM_SERVER_SKILL_DIR"):
        candidates.append(paths.checked(os.environ["GPM_SERVER_SKILL_DIR"]))
    result = []
    for skill in dict.fromkeys(candidates):
        if not skill.exists():
            log("Registered skill no longer exists; left untouched: " + str(skill))
            continue
        if paths.resolve(skill) != tools:
            if skill == bundled or str(skill) == os.environ.get("GPM_SERVER_SKILL_DIR"):
                raise ValueError("Skill binding conflicts with this tools installation: " + str(skill))
            log("Skill was rebound to another installation; left untouched: " + str(skill))
            continue
        # Do not read/copy local/ during updates: it remains byte-for-byte in place.
        if skill != bundled:
            if any(skill == root or root in skill.parents or skill in root.parents for root in (tools,)):
                raise ValueError("Separate installed skills must not overlap the tools directory")
        result.append(skill)
    return result


def ensure_idle(tools, workspace):
    # The tools-only call still catches commands anywhere under this installation.
    core.check_direct_processes(workspace or tools, tools)


def prepare(source, tools, workspace, release):
    tools = paths.validate_tools(tools)
    source_info = downloads.verify_bundle(source, release)
    source_files = core.verified_source(source, source_info["git_revision"])
    if not metadata(tools) and any((p / ".git").exists() for p in (tools, *tools.parents)):
        raise ValueError("This is a Git checkout, not an installed source package; update it with Git")
    if source == tools or source in tools.parents or tools in source.parents:
        raise ValueError("Source staging and installed tools must be separate non-nested directories")
    previous = metadata(tools)
    if previous.get("release"):
        version = lambda tag: tuple(map(int, tag.lstrip("v").split(".")))
        if version(previous["release"]) > version(release["tag"]):
            raise ValueError("Available source is older than the installation; refusing downgrade")
    if previous.get("built_at") and source_info.get("built_at"):
        if (dt.datetime.fromisoformat(previous["built_at"]) > dt.datetime.fromisoformat(source_info["built_at"])
                and previous.get("git_revision") != source_info["git_revision"]):
            raise ValueError("Available source predates the installation; refusing stale-mirror downgrade")
    for name in ("cgat-server.conda-spec.txt", "cgat-server.linux-aarch64.conda-spec.txt"):
        old, new = core.regular_path(tools, name), core.regular_path(source, name)
        if old.exists() and new.exists() and old.read_bytes() != new.read_bytes():
            raise ValueError("Dependency specification changed. Review/install a separate compatible environment before this code-only update: " + name)
    if workspace:
        paths.checked(workspace / ".prepare_lib")
        nested = tools in workspace.parents
        if nested:
            relative = workspace.relative_to(tools).as_posix()
            managed = set(source_files) | set(previous.get("files", {}))
            if (relative.split("/")[0] in {".run_all", ".git", "skills", "tools", "lib", "contracts", "templates"}
                    or any(name == relative or name.startswith(relative + "/") or relative.startswith(name + "/") for name in managed)):
                raise ValueError("Nested project overlaps managed Server files")
        core.validate_targets(workspace, tools, source, allow_nested_workspace=nested)
        binding = core.regular_path(workspace / ".prepare_lib", "server-tools.path")
        if binding.exists():
            recorded = binding.read_text().strip()
            if not Path(recorded).is_absolute() or paths.checked(recorded) != tools:
                raise ValueError("Project tools binding conflicts with the invoked installation: " + recorded)
        else:
            print("Legacy project has no saved tools path; the backed-up update will bind it to: " + str(tools))
    skills = skill_targets(tools)
    roots = {"tools": tools}
    targets = [("tools", source_files, previous.get("files", {}), "")]
    if workspace:
        runtime = workspace / ".prepare_lib"
        roots["runtime"] = runtime
        selected = {n: r for n, r in source_files.items() if runtime_file(n) or n == "SOURCE.json"}
        targets.append(("runtime", selected, metadata(runtime).get("files", {}), ""))
    skill_files = {n[len(SKILL_PREFIX):]: r for n, r in source_files.items() if n.startswith(SKILL_PREFIX)}
    for i, skill in enumerate(skills):
        if skill == tools / "skills/gpm-server":
            continue
        key = f"skill-{i}"
        roots[key] = skill
        state = core.regular_path(skill, "official-source.json")
        old = json.loads(state.read_text()).get("files", {}) if state.exists() else {}
        # v3 stored Git blob records; do not mistake them for a SHA-256 baseline.
        targets.append((key, skill_files, old if isinstance(old, dict) else {}, SKILL_PREFIX))
    # Roots may be nested only for a project in a separate, unowned tools subdir.
    # Registered skills cannot overlap the project or each other.
    skill_roots = [Path(value) for key, value in roots.items() if key.startswith("skill-")]
    for i, skill in enumerate(skill_roots):
        for other in skill_roots[i + 1:] + ([workspace] if workspace else []):
            if skill == other or skill in other.parents or other in skill.parents:
                raise ValueError("Registered skill and project roots must not overlap")
    changes, unknown, observations = [], [], {}
    def observe(kind, name):
        path = core.regular_path(roots[kind], name)
        exists = path.exists()
        observations[(kind, name)] = {
            "kind": kind, "relative": name, "existed": exists,
            "sha256": core.digest(path.read_bytes()) if exists else None,
            "mode": stat.S_IMODE(path.stat().st_mode) if exists else None,
        }
    def add(kind, name, data, mode, old_record=None):
        target = core.regular_path(roots[kind], name)
        exists = target.exists()
        before = target.read_bytes() if exists else None
        old_mode = stat.S_IMODE(target.stat().st_mode) if exists else None
        observe(kind, name)
        if before == data and (data is None or old_mode == mode):
            return
        if exists and old_record and core.digest(before) != old_record.get("sha256"):
            raise ValueError("Locally modified official file; review before updating: " + str(target))
        if exists and not old_record and name not in ("SOURCE.json", "official-source.json", "server-tools.path"):
            unknown.append(str(target))
        changes.append({"kind": kind, "relative": name, "existed": exists,
            "old_sha256": core.digest(before) if exists else None, "old_mode": old_mode,
            "new_sha256": core.digest(data) if data is not None else None,
            "new_mode": mode, "data": data})
    for kind, files, old_files, prefix in targets:
        root = roots[kind]
        for name, record in sorted(files.items()):
            if name in (core.BINDING, "server-tools.path"):
                observe(kind, name)
                continue
            add(kind, name, (source / (prefix + name)).read_bytes(), record["mode"], old_files.get(name))
        # Remove only manifest-owned retired files, with an unchanged baseline.
        for name, record in old_files.items():
            if name in files or name in (core.BINDING, "server-tools.path", "SOURCE.json"):
                continue
            if kind == "runtime" and not runtime_file(name):
                continue
            if name.startswith(("local/", "skills/gpm-server/local/")):
                continue
            add(kind, name, None, None, record)
        if kind.startswith("skill-"):
            data = (json.dumps({"release": release["tag"], "git_revision": source_info["git_revision"], "files": skill_files}, indent=2) + "\n").encode()
            add(kind, "official-source.json", data, 0o644)
        if kind in ("runtime", "tools"):
            expected = {n for n in files if n.startswith("tools/grt_core/") and n.endswith(".py")}
            actual = {p.relative_to(root).as_posix() for p in (root / "tools/grt_core").rglob("*.py")}
            if actual - expected - set(old_files):
                raise ValueError("Unrecognized old core modules; inspect before updating: " + str(sorted(actual - expected - set(old_files))))
    if workspace and "lib/run_all_launcher.sh" in source_files:
        # Only a byte-recognized generated launcher is upgraded. Custom scripts
        # stay untouched. This is journaled with the code update, not a shell edit.
        launcher = core.regular_path(workspace, "run_all.sh")
        template = core.regular_path(source, "lib/run_all_launcher.sh")
        known = {LEGACY_RUN_ALL, template.read_bytes()}
        old_template = core.regular_path(workspace / ".prepare_lib", "lib/run_all_launcher.sh")
        old_record = metadata(workspace / ".prepare_lib").get("files", {}).get("lib/run_all_launcher.sh")
        if old_template.is_file() and old_record and core.digest(old_template.read_bytes()) == old_record.get("sha256"):
            known.add(old_template.read_bytes())
        if launcher.is_file() and launcher.read_bytes() in known:
            roots["workspace"] = workspace
            add("workspace", "run_all.sh", template.read_bytes(), 0o755,
                {"sha256": core.digest(launcher.read_bytes())})
    observe("tools", paths.REGISTRY)
    if workspace:
        add("runtime", "server-tools.path", (str(tools) + "\n").encode(), 0o644)
    return {"roots": {k: str(v) for k, v in roots.items()}, "workspace": str(workspace) if workspace else None,
            "tools_root": str(tools), "source_revision": source_info["git_revision"],
            "release": release["tag"], "files": changes, "unknown_baselines": unknown,
            "preconditions": list(observations.values()),
            "analysis_started": False}


def locks_for(plan):
    roots = [Path(plan["tools_root"])]
    if plan["workspace"]:
        roots.append(Path(plan["workspace"]))
    roots += [Path(root) for key, root in plan["roots"].items() if key.startswith("skill-")]
    return sorted(set(roots))


def acquire(stack, plan):
    for root in plan["roots"].values():
        paths.checked(root)
    for root in locks_for(plan):
        paths.checked(root)
        for name in (".run_all", ".run_all/lock", ".run_all/lock/owner.json"):
            paths.checked(root / name)
        lock = core.workspace_lock(root)
        lock.acquire()
        stack.callback(lock.release)


def restore(journal, backup):
    # The lower-level restorer supports the extended explicit roots map, and
    # verifies all originals/current files before restoring any of them.
    core.restore_files(journal, backup, verify_current=True)


def apply(plan):
    tools = Path(plan["tools_root"])
    workspace = Path(plan["workspace"]) if plan["workspace"] else None
    with ExitStack() as stack:
        acquire(stack, plan)
        ensure_idle(tools, workspace)
        changes = plan["files"]
        for item in plan["preconditions"]:
            path = core.regular_path(Path(plan["roots"][item["kind"]]), item["relative"])
            if path.exists() != item["existed"] or (path.exists() and (
                    core.digest(path.read_bytes()) != item["sha256"] or
                    stat.S_IMODE(path.stat().st_mode) != item["mode"])):
                raise ValueError("Target changed after planning; check again: " + str(path))
        home = (workspace or tools) / ".run_all"
        backup = Path(tempfile.mkdtemp(prefix="server-update-", dir=home))
        journal = {**plan, "files": [{k: v for k, v in item.items() if k != "data"} for item in changes], "status": "applying"}
        for item in changes:
            if item["existed"]:
                path = core.regular_path(Path(plan["roots"][item["kind"]]), item["relative"])
                data = path.read_bytes()
                if core.digest(data) != item["old_sha256"]:
                    raise ValueError("Target changed during backup: " + str(path))
                core.write_atomic(backup / "original" / item["kind"] / item["relative"], data, item["old_mode"])
        def save():
            core.write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        save()
        print("Backup prepared: " + str(backup))
        try:
            for item in changes:
                path = core.regular_path(Path(plan["roots"][item["kind"]]), item["relative"])
                if item["data"] is None:
                    path.unlink(missing_ok=True)
                else:
                    core.write_atomic(path, item["data"], item["new_mode"])
            expected = {(p["kind"], p["relative"]): dict(p) for p in plan["preconditions"]}
            for item in changes:
                expected[(item["kind"], item["relative"])].update(
                    existed=item["data"] is not None, sha256=item["new_sha256"], mode=item["new_mode"])
            for item in expected.values():
                path = core.regular_path(Path(plan["roots"][item["kind"]]), item["relative"])
                if path.exists() != item["existed"] or (path.exists() and (
                        core.digest(path.read_bytes()) != item["sha256"] or
                        stat.S_IMODE(path.stat().st_mode) != item["mode"])):
                    raise ValueError("Post-update verification failed: " + str(path))
        except BaseException:
            restore(journal, backup)
            journal["status"] = "rolled_back_after_failure"
            save()
            raise
        journal["status"] = "updated"
        save()
    return backup


def rollback(backup):
    backup = paths.checked(backup)
    journal = json.loads(core.regular_path(backup, "journal.json").read_text())
    home = Path(journal["workspace"] or journal["tools_root"]) / ".run_all"
    if backup.parent != home or not backup.name.startswith("server-update-"):
        raise ValueError("Not a coordinated-update backup")
    with ExitStack() as stack:
        acquire(stack, journal)
        ensure_idle(Path(journal["tools_root"]), Path(journal["workspace"]) if journal["workspace"] else None)
        restore(journal, backup)
        journal["status"] = "rolled_back"
        core.write_atomic(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())


def align_installed_runtime(tools, workspace):
    """Repair a stopped prepared runtime from verified local tools, offline.

    Older updaters copy the new SOURCE.json but omit nested runtime modules.
    A compute node may have no network: do not require a second download or a
    customer-written copy/config step. Unknown/custom files still fail closed.
    """
    if workspace is None:
        return
    info = metadata(tools)
    try:
        manifest = core.verified_source(tools, info["git_revision"])
    except (OSError, ValueError, KeyError, TypeError):
        # An incomplete installation is not a repair source; a verified network
        # payload may still repair missing files. Offline verification will stop.
        return
    runtime = workspace / ".prepare_lib"
    old = metadata(runtime)
    wanted = {name: record for name, record in manifest.items() if runtime_file(name)}
    equal = old.get("git_revision") == info["git_revision"]
    for name, record in wanted.items():
        path = core.regular_path(runtime, name)
        if not path.is_file() or core.digest(path.read_bytes()) != record["sha256"]:
            equal = False
            break
    if equal:
        return
    with tempfile.TemporaryDirectory(prefix="gpm-local-runtime-") as temporary:
        source = Path(temporary) / "GPM_Server"
        for name, record in manifest.items():
            data = core.regular_path(tools, name).read_bytes()
            if core.digest(data) != record["sha256"]:
                raise ValueError("Installed source changed while preparing offline runtime update: " + name)
            core.write_atomic(source / name, data, record["mode"])
        plan = prepare(source, tools, workspace, {"tag": info["release"]})
        if plan["unknown_baselines"]:
            raise ValueError("Local runtime update has unknown baselines; explicit update.sh adoption is required")
        if plan["files"]:
            backup = apply(plan)  # No exception swallowing after writes/rollback.
            print("[UPDATE] Prepared runtime aligned from verified installed source (no download). Backup: " + str(backup))


def run(tools, *, startup=False, workspace=None):
    tools = paths.validate_tools(tools)
    if not startup:
        workspace = project_at(Path.cwd())
    else:
        align_installed_runtime(tools, workspace)
    print("Server tools: " + str(tools))
    print("Current project: " + (str(workspace) if workspace else "none (other projects will not be scanned)"))
    print("Checking CGAT docs first, GitHub Release on failure (tools and skill share one verified source)...")
    with tempfile.TemporaryDirectory(prefix="gpm-server-update-") as tmp:
        # Only pre-mutation failures may fall back during startup. apply() and
        # its rollback stay outside this catch: uncertain updates MUST stop.
        try:
            release = downloads.discover()
            source = downloads.extract(release, Path(tmp))
            plan = prepare(source, tools, workspace, release)
            if startup and plan["unknown_baselines"]:
                raise ValueError("legacy files have no recorded baseline; use update.sh explicitly for a backed-up adoption")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, tarfile.TarError) as exc:
            if not startup:
                raise
            verify_installed(tools, workspace)
            print("[UPDATE] Check unavailable; keeping the verified installed runtime: " + str(exc), file=sys.stderr)
            return 0
        if not plan["files"]:
            print("Already up to date / 当前已是最新版本，无需更新: " + release["tag"])
            return 0
        print("Target: " + release["tag"] + " / " + plan["source_revision"])
        for key, root in plan["roots"].items():
            count = sum(item["kind"] == key for item in plan["files"])
            if count:
                print(f"  {root}: {count} file changes")
        if plan["unknown_baselines"]:
            print("Legacy files have no recorded baseline; preserving originals in the update backup:")
            print("\n".join("  " + p for p in plan["unknown_baselines"]))
        ensure_idle(tools, workspace)
        print("Preserves skill local/, bindings, inputs, results, logs, caches and environment. Does not run analysis.")
        print("Applying the code-only update without a Y/N prompt. All affected jobs must be stopped.")
        # Source payload and every target precondition are pinned before writes.
        backup = apply(plan)
        print("Updated successfully. Backup: " + str(backup))
        print("Rollback: python3 " + shlex.quote(str(tools / "tools/update_server.py")) + " --rollback " + shlex.quote(str(backup)))
        print("No analysis was started. Start a fresh agent session to reload the skill.")
    return 0


def verify_installed(tools, workspace):
    """Never continue offline with a corrupted official source/runtime."""
    info = metadata(tools)
    core.verified_source(tools, info["git_revision"])
    if workspace is not None:
        runtime = workspace / ".prepare_lib"
        old = metadata(runtime)
        if not isinstance(old.get("files"), dict) or not old["files"]:
            raise ValueError("Prepared runtime has no integrity baseline; update.sh must adopt it before automatic startup")
        for name, record in old["files"].items():
            if runtime_file(name):
                path = core.regular_path(runtime, name)
                if not path.is_file() or core.digest(path.read_bytes()) != record.get("sha256"):
                    raise ValueError("Prepared runtime integrity check failed: " + name)


def launch(tools, mode, argv):
    """Exec chain removes launcher parents; no PID exemptions or loaded-old-code reuse."""
    tools = paths.validate_tools(tools)
    if mode == "--launch-run":
        from server_run import parse_options
        help_only = any(flag in argv for flag in ("--help", "-h"))
        options = {} if help_only else parse_options(argv, Path.cwd())
        candidate = Path(options.get("--out", [[str(Path.cwd() / "gpm_server")]])[-1][0])
        workspace = paths.checked(candidate) if (candidate / ".prepare_lib").is_dir() else None
        command = [sys.executable, "-B", str(tools / "tools/server_run.py"), *argv]
    elif mode == "--launch-workspace":
        if not argv:
            raise ValueError("Missing prepared workspace for internal launch")
        workspace = paths.checked(argv[0])
        if not (workspace / ".prepare_lib").is_dir():
            raise ValueError("Not a prepared Server workspace")
        binding = core.regular_path(workspace / ".prepare_lib", "server-tools.path")
        if not binding.is_file() or paths.checked(binding.read_text().strip()) != tools:
            raise ValueError("Prepared workspace belongs to a different Server installation")
        help_only = any(flag in argv[1:] for flag in ("--help", "-h"))
        command = [sys.executable, "-B", str(workspace / ".prepare_lib/tools/run_all_runner.py"),
                   "--server-dir", str(workspace), *argv[1:]]
    else:
        raise ValueError("Unknown internal launch mode")
    info = metadata(tools)
    if not help_only and info.get("release") and info.get("official_release") is not False:
        # An older updater may have copied SOURCE.json but omitted newly nested
        # runtime files. Let the verified update fill missing files first. Only
        # continue (online or offline) after the installed tree is complete.
        run(tools, startup=True, workspace=workspace)
        verify_installed(tools, workspace)
    elif not help_only:
        print("[UPDATE] Development/legacy source without an official release manifest: automatic update skipped.", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    # Reload all code from disk after an update; never run previously imported Runner.
    os.execv(sys.executable, command)


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("terminated")))
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--rollback":
            rollback(Path(sys.argv[2]))
            return 0
        if len(sys.argv) >= 3 and sys.argv[2] in ("--launch-run", "--launch-workspace"):
            return launch(paths.checked(sys.argv[1]), sys.argv[2], sys.argv[3:])
        if len(sys.argv) != 2:
            raise ValueError("Use bash /actual/Server/update.sh (no arguments)")
        return run(paths.checked(sys.argv[1]))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, tarfile.TarError, EOFError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}. No analysis was started.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
