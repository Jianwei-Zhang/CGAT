#!/usr/bin/env python3
"""Preview and explicitly migrate a completed LGZ workspace without recomputation."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import socket
import stat
import sys

sys.dont_write_bytecode = True

from workspace_layout import (WorkspaceLayout, LayoutError, MIGRATION, canonical_relative,
                              relative_path, render_workspace_shell, migration_validation, _ROOT_COMMANDS)
from workspace_migration import (MigrationTransaction, MigrationPlan, plan_migration, json_digest,
                                 identity, matches, plain_path)
from run_all_runner import WorkspaceLock, new_run_id, RunnerError
from lgz_contract import validate_contract, ContractError
from refinement_config import SCRIPT, COMMAND, CONFIG, SCHEMA as CONFIG_SCHEMA, validate_config
from migrated_lgz import ADAPTER, PROOF, SCHEMA


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def source_runtime(source):
    """The same runtime areas as prepare.sh; never import customer Python code."""
    files = {}
    for name in ("lib", "contracts", "tools"):
        if not (source / name).is_dir() or (source / name).is_symlink():
            raise LayoutError("missing regular Server source directory: " + name)
    selected = [p for p in (source / "tools").glob("*.py")]
    for name in ("lib", "contracts", "tools/grt_core", "tools/lgz_core", "tools/degap_core", "tools/long_cigar_recovery"):
        directory = source / name
        if not directory.is_dir() or directory.is_symlink():
            raise LayoutError("incomplete Server runtime source: " + name)
        for path in directory.rglob("*"):
            if "__pycache__" in path.parts or path.name.endswith(".pyc"):
                continue
            if path.is_symlink():
                raise LayoutError("runtime source may not contain symlinks: " + str(path))
            if path.is_file():
                selected.append(path)
    if (source / "SOURCE.json").exists():
        selected.append(source / "SOURCE.json")
    for path in sorted(set(selected)):
        if path.is_symlink() or not path.is_file():
            raise LayoutError("runtime source must be regular files")
        relative = path.relative_to(source).as_posix()
        files[".runtime/prepared/" + relative] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode) & 0o777)
    if not (source / "SOURCE.json").exists():
        files[".runtime/prepared/SOURCE.json"] = (encoded({"schema": "cgat.unreleased-migration-runtime",
            "official_release": False, "source_root": str(source),
            "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, (data, _mode) in sorted(files.items())}}), 0o600)
    binding = str(source) if (source / "SOURCE.json").is_file() else ""
    files[".runtime/prepared/server-tools.path"] = ((binding + "\n").encode(), 0o600)
    return files


def process_guard(root, source, *, owned=False):
    """Check the real legacy lock and standalone scripts, not just lock absence.

    Other-node/queued jobs still require explicit operator idle confirmation.
    """
    probe = WorkspaceLock(root, "migration-inspection", for_migration=True)
    if probe.lock_dir.exists() or probe.lock_dir.is_symlink():
        if probe.lock_dir.is_symlink():
            raise LayoutError("symlinked or unknown migration lock")
        owner = probe._existing_owner()
        if not (owned and owner.get("pid") == os.getpid() and owner.get("workspace") == str(root)
                and owner.get("hostname") == socket.gethostname()):
            if probe._owner_is_active(owner):
                raise LayoutError("workspace has a live, foreign-host or unknown owner; stop/verify jobs before migration")
    proc = Path("/proc")
    if not proc.is_dir():
        raise LayoutError("migration requires Linux process inspection and operator scheduler-idle confirmation")
    prefixes = tuple(str(path) + "/" for path in (root / ".prepare_lib", root / ".runtime/prepared",
                     root / "runs", root / "02_alignments", root / ".runtime/commands", source / "tools"))
    scripts = {str(root / name) for name in _ROOT_COMMANDS | {"run_all.sh"}}
    scripts |= {str(root / canonical_relative(name)) for name in _ROOT_COMMANDS}
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            args = (process / "cmdline").read_bytes().decode(errors="replace").split("\0")
        except OSError:
            continue
        if args and Path(args[0]).name in {"bash", "sh", "python", "python3", "perl", "minimap2", "nucmer", "samtools", "bwa", "racon"}:
            try:
                cwd = (process / "cwd").resolve(strict=True)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError:
                cwd = None
            if cwd is not None and any(cwd == directory or directory in cwd.parents
                                       for directory in (root / "runs", root / "02_alignments", root / "04_refinement")):
                raise LayoutError("active stage process must stop before migration: PID " + process.name)
        for arg in args:
            if not arg or arg.startswith("-") or "\n" in arg:
                continue
            if arg in scripts or arg.startswith(prefixes):
                raise LayoutError("active Server process must stop before migration: PID " + process.name)
            if not arg.endswith((".py", ".sh")):
                continue
            try:
                path = Path(arg)
                if not path.is_absolute():
                    path = (process / "cwd").resolve(strict=True) / path
                resolved = str(path.resolve())
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, RuntimeError) as error:
                if Path(arg).name in {Path(name).name for name in scripts}:
                    raise LayoutError("cannot inspect possible Server process: PID " + process.name) from error
                continue
            if resolved in scripts or resolved.startswith(prefixes):
                raise LayoutError("active Server process must stop before migration: PID " + process.name)


def legacy_rows(root):
    with (root / ".run_all/plan.tsv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != ["unit_id", "command_relpath", "detail_log_relpath"]:
            raise LayoutError("unsupported legacy execution plan")
        rows = list(reader)
    ids = [row["unit_id"] for row in rows]
    if len(ids) != len(set(ids)) or ids.count("finalize_evidence") != 1:
        raise LayoutError("completed adapter requires one unique LGZ evidence-finalization unit")
    kept = [row for row in rows if row["unit_id"] != "degap_gapfill"]
    prefix = kept[:next(i for i, row in enumerate(kept) if row["unit_id"] == "finalize_evidence") + 1]
    fixed = {"assign", "q0_evidence", "grt_prepare", "grt_step1", "grt_step2", "grt_step12", "grt_step3", "finalize_evidence"}
    for row in prefix:
        unit = row["unit_id"]
        if unit not in fixed and not (unit.startswith(("ref:", "chr:", "q0_chr:")) and unit.count(":") == 1 and unit.split(":")[1]):
            raise LayoutError("unrecognized scientific plan unit requires a specific adapter: " + unit)
    if [row["unit_id"] for row in kept[len(prefix):]] != ["package_full", "package_light"]:
        raise LayoutError("custom post-LGZ plan must be reviewed before migration")
    for row in kept:
        for name in ("command_relpath", "detail_log_relpath"):
            relative_path(row[name])
        command = plain_path(root, row["command_relpath"])
        if command.is_symlink() or not command.is_file() or row["command_relpath"].startswith(".prepare_lib/"):
            raise LayoutError("legacy plan command must be an owned regular generated script")
    for row in prefix:
        if row["command_relpath"] in {"run_all.sh", "package_full_zip.sh", "package_light_zip.sh", "export_final_path_fasta.sh"}:
            raise LayoutError("scientific command overlaps a launcher/delivery helper")
    for row, name in zip(kept[len(prefix):], ("package_full_zip.sh", "package_light_zip.sh")):
        if row["command_relpath"] != name:
            raise LayoutError("custom packaging command requires a reviewed adapter")
    return prefix, kept


def rebased_path(root, text):
    path = Path(text)
    if not path.is_absolute():
        return text
    try:
        role = path.relative_to(root).as_posix()
    except ValueError:
        return text
    return str(root / canonical_relative(role)) if role != "." else str(root)


@dataclass
class Prepared:
    physical: MigrationPlan
    rewrites: dict
    additions: dict
    baseline: dict
    approval: dict

    @property
    def digest(self):
        return json_digest(self.approval)

    def summary(self):
        return {"schema": "cgat.completed-lgz-migration-preview", "adapter": ADAPTER,
                "approval_sha256": self.digest, "physical_plan_sha256": self.physical.digest,
                "file_count": len(self.physical.entries), "moves": self.physical.summary()["moves"],
                "rewritten_files": sorted(self.rewrites), "added_files": sorted(self.additions),
                "original_contract": self.baseline["contract"], "eligible": True,
                "analysis_started": False, "applied": False,
                "confirmation_required": "Confirm no active or queued jobs on any node, then use --apply --approve <approval_sha256> --confirm-idle"}


def preview(root, source, *, owned=False):
    root, source = Path(root).resolve(), Path(source).resolve()
    if root == source or root in source.parents or source in root.parents:
        raise LayoutError("migration source must be separate from the workspace")
    process_guard(root, source, owned=owned)
    physical = plan_migration(root)
    try:
        contract = validate_contract(root)
    except ContractError as error:
        raise LayoutError("completed-baseline migration requires a fully validated LGZ result; retain/resume the original workspace, do not re-prepare it: " + str(error)) from error
    prefix, rows = legacy_rows(root)
    layout = WorkspaceLayout(root, 2)
    entries = {entry["source"]: entry for entry in physical.entries}
    destinations = {entry["destination"]: entry for entry in physical.entries}
    runtime = source_runtime(source)
    old_python = {entry["source"] for entry in physical.entries if entry["source"].startswith(".prepare_lib/tools/") and entry["source"].endswith(".py")}
    if not old_python:
        raise LayoutError("original engine source is missing; cannot certify original-engine provenance")
    unknown = [name for name in old_python if canonical_relative(name) not in runtime]
    if unknown:
        raise LayoutError("unrecognized legacy runtime modules require a reviewed adapter: " + ", ".join(sorted(unknown)))
    rewrites, additions = {}, {}
    def install(destination, content, mode=0o644):
        if destination in destinations:
            entry = destinations[destination]
            if entry["before"]["kind"] != "file":
                raise LayoutError("cannot replace a symlinked runtime/command: " + entry["source"])
            if hashlib.sha256(content).hexdigest() != entry["before"]["sha256"]:
                rewrites[entry["source"]] = content
        else:
            additions[destination] = (content, mode)
    for destination, (content, mode) in runtime.items():
        install(destination, content, mode)
    launcher = source / "lib/run_all_launcher.sh"
    if launcher.is_symlink() or not launcher.is_file():
        raise LayoutError("new Server launcher is missing")
    install("run_all.sh", launcher.read_bytes(), 0o755)
    for name in ("package_full_zip.sh", "package_light_zip.sh", "export_final_path_fasta.sh"):
        template = source / "templates" / name
        if template.is_symlink() or not template.is_file():
            raise LayoutError("new Server template is missing: " + name)
        install(layout.relative(name), render_workspace_shell(template.read_text(), layout, name).encode(), 0o755)
    guarded = {row["command_relpath"] for row in prefix}
    guarded.update(name for name in _ROOT_COMMANDS if name in entries and name not in {"package_full_zip.sh", "package_light_zip.sh", "export_final_path_fasta.sh"})
    guarded.update(name for name in entries if name.startswith("runs/") and name.endswith(".sh"))
    for name in sorted(guarded):
        message = "Original-engine LGZ is frozen after migration. Use run_all.sh to append refinement; use a new workspace to recompute LGZ. Historical command: " + name
        install(layout.relative(name), ("#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' " + shlex.quote(message) + " >&2\nexit 2\n").encode(), 0o755)
    projected = [{key: layout.relative(value) if key != "unit_id" else value for key, value in row.items()} for row in rows]
    frozen_prefix = projected[:len(prefix)]
    projected.insert(len(prefix), {"unit_id": "refinement", "command_relpath": COMMAND, "detail_log_relpath": ".runtime/logs/run_all.log"})
    output = io.StringIO()
    writer = csv.DictWriter(output, ["unit_id", "command_relpath", "detail_log_relpath"], delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(projected)
    install(layout.relative(".run_all/plan.tsv"), output.getvalue().encode(), 0o600)
    install(COMMAND, SCRIPT.encode(), 0o755)
    groups = {"hifi": [], "ont": []}
    old_reads = root / "metadata/degap_inputs.json"
    if old_reads.is_file():
        from post_lgz_degap import read_groups, PURPOSE
        value = json.loads(old_reads.read_text())
        if value.get("purpose") == PURPOSE:
            groups = {kind: [rebased_path(root, path) for path in paths] for kind, paths in read_groups(value).items()}
    config = {"schema": CONFIG_SCHEMA, "schema_version": 1, "groups": groups, "tools": None}
    validate_config(config)
    install(CONFIG, encoded(config), 0o600)
    launch = root / ".run_all/launch.json"
    if launch.is_file():
        value = json.loads(launch.read_text())
        if value.get("schema_version") != 1 or not value.get("prepared"):
            raise LayoutError("unsupported or incomplete legacy launch record")
        for key in ("--ref", "--ds", "--reads", "--cen", "--out", "--hifi", "--ont"):
            for values in value["options"].get(key, []):
                values[-1] = rebased_path(root, values[-1])
        value["argv"] = [item for key, groups in value["options"].items() for values in groups for item in [key, *values]]
        value["inputs"] = {rebased_path(root, name): identity for name, identity in value["inputs"].items()}
        install(layout.relative(".run_all/launch.json"), encoded(value), 0o600)
    scientific = []
    for entry in physical.entries:
        name = entry["source"]
        if (name.startswith(("data/", "metadata/", "grt/", "runs/", "tel/", "cen/", ".run_all/checkpoints/"))
                and name not in rewrites):
            scientific.append({"destination": entry["destination"], "identity": entry["after"]})
    baseline = {"schema": SCHEMA, "schema_version": 1, "plan_sha256": physical.digest,
                "contract": contract, "prefix": frozen_prefix, "execution_plan": projected, "scientific_files": scientific,
                "runtime_snapshot_at_migration": {name: entries[name]["before"] for name in sorted(old_python)},
                "producer_receipts": [{key: row[key] for key in ("stage", "checkpoint_relpath", "checkpoint_sha256")}
                                      for row in csv.DictReader((root / "metadata/grt_stage_status.tsv").read_text().splitlines(), delimiter="\t")],
                "policy": "original_engine_frozen_lgz_not_new_engine_cache"}
    install(PROOF, encoded(baseline), 0o600)
    if "README.txt" not in entries:
        install("README.txt", b"CGAT migrated workspace / original-engine LGZ baseline\n\nRun: bash run_all.sh --hifi /path/to/reads.fq.gz [--ont /path/to/ont.fq.gz]\nTools: --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser (default DEGAP with reads)\nOverview: 06_report/report.html\nUnrefined LGZ baseline: 05_final/00_lgz/\nRefined final FASTA and Final Path: 05_final/<numbered_tool>/\nFull/light App archives: 07_delivery/<numbered_tool>/\nOriginal scientific proof is frozen; LGZ changes require a new workspace.\n", 0o644)
    approval = {"adapter": ADAPTER, "physical_plan_sha256": physical.digest,
                "rewrites": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(rewrites.items())},
                "additions": {name: {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode} for name, (data, mode) in sorted(additions.items())},
                "baseline_sha256": hashlib.sha256(encoded(baseline)).hexdigest(),
                "runtime_sha256": json_digest({name: {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
                                              for name, (content, mode) in sorted(runtime.items())})}
    return Prepared(physical, rewrites, additions, baseline, approval)


def validate_destination(transaction, source):
    root = transaction.root
    metadata = transaction.journal["adapter_metadata"]
    process_guard(root, source, owned=True)
    current = source_runtime(source)
    runtime_sha = json_digest({name: {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
                               for name, (content, mode) in sorted(current.items())})
    if runtime_sha != metadata["approval"]["runtime_sha256"]:
        raise LayoutError("Server source changed after approval; use the original version or roll back")
    with migration_validation(root, transaction.lock, transaction.journal["id"]):
        actual = validate_contract(root)
        if actual != metadata["contract"]:
            raise LayoutError("destination differs from the original LGZ scientific contract")
        proof = json.loads((root / PROOF).read_text())
        if proof["contract"] != actual or proof["plan_sha256"] != transaction.journal["plan_sha256"]:
            raise LayoutError("destination baseline receipt does not bind the original proof")
        for row in proof["scientific_files"]:
            if not matches(plain_path(root, row["destination"]), row["identity"]):
                raise LayoutError("scientific artifact changed during migration")
        return {"adapter": ADAPTER, "contract": actual, "approval_sha256": metadata["approval_sha256"],
                "original_proof_preserved": True, "analysis_started": False}


def apply(root, source, approval, *, confirm_idle=False):
    root, source = Path(root).resolve(), Path(source).resolve()
    if not confirm_idle:
        raise LayoutError("confirm no active/queued jobs on any node with --confirm-idle")
    if not root.is_dir() or not (root / "run_all.sh").is_file() or not (root / ".run_all/plan.tsv").is_file():
        raise LayoutError("not a prepared legacy Server workspace")
    lock = WorkspaceLock(root, new_run_id(), for_migration=True)
    lock.acquire()
    transaction = None
    try:
        prepared = preview(root, source, owned=True)
        if approval != prepared.digest:
            raise LayoutError("workspace/runtime changed after preview; review a fresh approval digest")
        transaction = MigrationTransaction.begin(root, lock, prepared.physical, adapter=ADAPTER,
            rewrites=prepared.rewrites, additions=prepared.additions,
            adapter_metadata={"approval_sha256": prepared.digest, "approval": prepared.approval,
                              "contract": prepared.baseline["contract"], "source": str(source), "operator_confirmed_idle": True})
        result = transaction.apply(lambda _layout: validate_destination(transaction, source))
        return {**result, "status": "committed", "migration_id": transaction.journal["id"]}
    finally:
        lock.release()
        if transaction is not None and transaction.journal["state"] == "committed":
            transaction.prune_empty_legacy_directories()


def recover(root, source, *, rollback=False, confirm_idle=False):
    root, source = Path(root).resolve(), Path(source).resolve()
    if not confirm_idle:
        raise LayoutError("confirm no active/queued jobs on any node with --confirm-idle")
    if not root.is_dir() or (not (root / MIGRATION).is_file()
                              and not list((root / ".runtime/migrations").glob("*/journal.json"))):
        raise LayoutError("no migration transaction to recover")
    process_guard(root, source)
    lock = WorkspaceLock(root, new_run_id(), for_migration=True)
    lock.acquire()
    transaction = None
    try:
        transaction = MigrationTransaction.resume(root, lock, adapter=ADAPTER)
        if rollback:
            transaction.rollback()
            return {"adapter": ADAPTER, "status": "rolled_back", "analysis_started": False}
        # Resume consumes staged bytes, never regenerated science or new code.
        expected = transaction.journal["adapter_metadata"]["source"]
        if str(source) != expected:
            raise LayoutError("resume must use the same recorded Server source; rollback remains available")
        result = transaction.apply(lambda _layout: validate_destination(transaction, source))
        return {**result, "status": "committed", "migration_id": transaction.journal["id"]}
    finally:
        lock.release()
        if transaction is not None and transaction.journal["state"] == "committed":
            transaction.prune_empty_legacy_directories()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--approve")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    try:
        if args.apply:
            if not args.approve:
                raise LayoutError("--apply requires the reviewed --approve digest")
            result = apply(args.server_dir, args.source, args.approve, confirm_idle=args.confirm_idle)
        elif args.resume or args.rollback:
            result = recover(args.server_dir, args.source, rollback=args.rollback, confirm_idle=args.confirm_idle)
        else:
            result = preview(args.server_dir, args.source).summary()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RunnerError, ContractError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
