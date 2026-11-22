#!/usr/bin/env python3
"""Explicit original-engine continuation, preceding completed LGZ migration."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys

from legacy_lgz_runner import digest, owned, verify_engine

SCHEMA = "cgat.legacy-lgz-continuation"
REGISTRY = "contracts/legacy_lgz_engines.json"
HELPERS = ("legacy_lgz_continuation.py", "legacy_lgz_runner.py", "migrate_workspace.py")


def data(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def original_engine(root, source):
    registry = json.loads((source / REGISTRY).read_text())
    if registry.get("schema") != "cgat.legacy-lgz-engine-registry" or registry.get("schema_version") != 1:
        raise ValueError("invalid reviewed legacy engine registry")
    failures = []
    for engine in registry["engines"]:
        try:
            verify_engine(root, engine)
            return engine
        except (OSError, ValueError) as error:
            failures.append(str(error))
    raise ValueError("no reviewed historical engine matches this workspace; do not upgrade/reprepare it: " + "; ".join(failures))


def check_script_roots(root, rows):
    """Refuse stale literal roots in generated scripts; never rewrite them.

    A moved legacy workspace must not execute commands still targeting the old
    customer's directory. This covers the supported generated root bindings,
    not arbitrary custom shell-program semantics.
    """
    bindings = []
    launch = root / ".run_all/launch.json"
    if launch.exists():
        recorded = json.loads(owned(root, ".run_all/launch.json").read_text())
        values = recorded.get("options", {}).get("--out", [])
        if values:
            bindings.append((".run_all/launch.json", "--out", values[-1][-1]))
    for row in rows:
        command = row["command_relpath"]
        tokens = shlex.split(owned(root, command).read_text(), comments=True)
        for index, token in enumerate(tokens):
            value = token
            if "=" in token and token.split("=", 1)[0].isidentifier():
                name, value = token.split("=", 1)
                if (name.endswith("WORK_ROOT") or name.lower() == "server_dir") and value.startswith("/"):
                    bindings.append((command, name, value))
            if token == "--server-dir" and index + 1 < len(tokens) and tokens[index + 1].startswith("/"):
                bindings.append((command, "--server-dir", tokens[index + 1]))
            path = Path(value)
            if path.is_absolute() and ".prepare_lib" in path.parts:
                prefix = Path(*path.parts[:path.parts.index(".prepare_lib")])
                bindings.append((command, "historical-runtime-root", str(prefix)))
    for command, role, value in bindings:
        if Path(value).resolve() != root:
            raise ValueError("stale generated workspace root; continuation must not write another workspace: "
                             + command + " " + role + "=" + value)
    return [{"command": command, "role": role, "path": value} for command, role, value in bindings]


def inspect(root, source, engine):
    inspected = subprocess.run([sys.executable, "-I", "-B", str(source / "tools/legacy_lgz_runner.py"),
                                "--server-dir", str(root)], input=data({"mode": "inspect", "engine": engine}),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if inspected.returncode:
        raise ValueError(inspected.stderr.decode(errors="replace").strip())
    return json.loads(inspected.stdout)


@dataclass
class PreparedContinuation:
    approval: dict

    @property
    def digest(self):
        from workspace_migration import json_digest
        return json_digest(self.approval)

    def summary(self):
        return {"schema": SCHEMA, "approval_sha256": self.digest,
                "engine": self.approval["engine"]["id"],
                "reviewed_source_git_revision": self.approval["engine"]["source_git_revision"],
                "prefix": self.approval["prefix"], "generated_root_bindings": self.approval["generated_root_bindings"],
                "validated_checkpoints": self.approval["inspection"]["checkpoints"],
                "eligible": True, "analysis_started": False, "layout_migrated": False,
                "boundary": "original-engine LGZ only; old DEGAP/delivery tail excluded; migration needs a second approval",
                "confirmation_required": "--continue-lgz --approve <approval_sha256> --confirm-idle"}


def preview(root, source, *, owned_lock=False):
    from migrate_workspace import legacy_rows, process_guard
    from workspace_layout import WorkspaceLayout, LayoutError
    from workspace_migration import plan_migration
    from lgz_contract import validate_contract, ContractError
    root, source = Path(root).resolve(), Path(source).resolve()
    if not root.is_dir() or any(not owned(root, name).is_file() for name in ("run_all.sh", ".run_all/plan.tsv")):
        raise ValueError("not a prepared regular legacy Server workspace")
    if root == source or root in source.parents or source in root.parents:
        raise LayoutError("continuation source must be separate from the legacy workspace")
    if WorkspaceLayout.detect(root).version != 1:
        raise LayoutError("original-engine continuation is only for an unmigrated legacy workspace")
    process_guard(root, source, owned=owned_lock)
    prefix, _rows = legacy_rows(root)
    roots = check_script_roots(root, prefix)
    engine = original_engine(root, source)
    inspected = inspect(root, source, engine)
    if inspected["prefix"] != [row["unit_id"] for row in prefix]:
        raise LayoutError("historical engine disagrees with the reviewed scientific prefix")
    try:
        validate_contract(root)
    except ContractError:
        pass
    else:
        raise LayoutError("LGZ is already complete; use --preview and completed-baseline migration instead")
    physical = plan_migration(root)
    approval = {"schema": SCHEMA, "workspace": str(root), "source": str(source),
                "physical_inventory_sha256": physical.digest, "engine": engine,
                "registry_sha256": digest(source / REGISTRY),
                "adapter_sha256": {name: digest(source / "tools" / name) for name in HELPERS},
                "prefix": prefix, "generated_root_bindings": roots, "inspection": inspected}
    return PreparedContinuation(approval)


def continue_lgz(root, source, approval, *, confirm_idle=False):
    from migrate_workspace import preview as migration_preview
    from run_all_runner import WorkspaceLock, new_run_id, timestamp
    from run_orchestration import atomic_write_json
    from workspace_layout import LayoutError
    if not confirm_idle:
        raise LayoutError("confirm no active/queued jobs on any node with --confirm-idle")
    root, source = Path(root).resolve(), Path(source).resolve()
    if not root.is_dir() or any(not owned(root, name).is_file() for name in ("run_all.sh", ".run_all/plan.tsv")):
        raise ValueError("not a prepared regular legacy Server workspace")
    run_id = new_run_id()
    lock = WorkspaceLock(root, run_id, for_migration=True)
    lock.acquire()
    try:
        prepared = preview(root, source, owned_lock=True)
        if approval != prepared.digest:
            raise LayoutError("workspace/runtime changed after preview; review a fresh continuation approval")
        relative = ".run_all/legacy_continuation/" + run_id
        attempt = owned(root, relative)
        attempt.mkdir(parents=True, mode=0o700)
        hook = attempt / "python-hook"
        hook.mkdir(mode=0o700)
        request = {"mode": "run", "engine": prepared.approval["engine"], "run_id": run_id,
                   "events": relative + "/cache_events.jsonl", "hook": relative + "/python-hook"}
        atomic_write_json(attempt / "request.json", request)
        atomic_write_json(attempt / "approval.json", prepared.approval)
        helper = str(source / "tools/legacy_lgz_runner.py")
        # Python deliberately reports/ignores ordinary sitecustomize errors.
        # Fail closed with _exit before any customer engine code can execute.
        startup = ("import os, sys, json, hashlib, runpy\ntry:\n"
                   + "    path = " + repr(helper) + "\n"
                   + "    expected = " + repr(digest(Path(helper))) + "\n"
                   + "    if hashlib.sha256(open(path, 'rb').read()).hexdigest() != expected: raise RuntimeError('continuation helper changed')\n"
                   + "    api = runpy.run_path(path)\n"
                   + "    from pathlib import Path\n"
                   + "    root = Path(" + repr(str(root)) + ")\n"
                   + "    request = json.loads(Path(" + repr(str(attempt / "request.json")) + ").read_text())\n"
                   + "    api['verify_engine'](root, request['engine'])\n"
                   + "    api['install_cache_fence'](root, request['engine'], root / request['events'])\n"
                   + "except BaseException as error:\n    sys.stderr.write('legacy continuation cache fence failed: ' + str(error) + '\\n')\n    os._exit(86)\n")
        (hook / "sitecustomize.py").write_text(startup)
        receipt = {"schema": SCHEMA, "status": "running", "run_id": run_id,
                   "approval_sha256": prepared.digest, "engine": request["engine"]["id"],
                   "started_at": timestamp(), "layout_migrated": False}
        atomic_write_json(attempt / "attempt.json", receipt)
        child = subprocess.Popen([sys.executable, "-I", "-B", helper, "--server-dir", str(root)],
                                 stdin=subprocess.PIPE, stdout=sys.stderr, stderr=sys.stderr, start_new_session=True)
        received = []
        def forward(number, _frame):
            received.append(number)
            if child.poll() is None:
                child.send_signal(number)
        handlers = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            for number in handlers:
                signal.signal(number, forward)
            child.communicate(data(request))
        finally:
            for number, handler in handlers.items():
                signal.signal(number, handler)
        code = child.returncode if child.returncode >= 0 else 128 - child.returncode
        if received:
            code = 128 + received[0]
        receipt.update(status="failed" if code else "lgz_finished", exit_code=code, ended_at=timestamp())
        atomic_write_json(attempt / "attempt.json", receipt)
        if code:
            return {**receipt, "attempt": relative, "next": "inspect failure; fresh --preview-lgz-continuation before retry"}
        # Recheck original proof + quiescence under the same lock before offering
        # the *separate*, newly content-bound physical migration approval.
        migration = migration_preview(root, source, owned=True).summary()
        receipt.update(status="lgz_complete_ready_for_migration", migration_approval_sha256=migration["approval_sha256"])
        # Do not change inventory after constructing the new approval digest.
        return {**receipt, "attempt": relative, "migration_preview": migration,
                "next": "--apply --approve " + migration["approval_sha256"] + " --confirm-idle"}
    finally:
        lock.release()
