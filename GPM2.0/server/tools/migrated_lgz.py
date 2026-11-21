"""A validated original-engine LGZ baseline, never a current-engine cache hit."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from workspace_layout import WorkspaceLayout, MIGRATION, LayoutError, relative_path
from workspace_migration import _check_journal, matches
from run_orchestration import fingerprint
from lgz_contract import validate_contract, ContractError

PROOF = ".runtime/refinement/migrated_lgz.json"
SCHEMA = "cgat.migrated-lgz-baseline"
ADAPTER = "cgat.completed-lgz-numbered.v1"
_CACHE = {}


def plan_rows(root):
    path = WorkspaceLayout.detect(root).path(".run_all/plan.tsv")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != ["unit_id", "command_relpath", "detail_log_relpath"]:
            raise LayoutError("unsupported migrated execution plan")
        rows = list(reader)
    ids = [row["unit_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise LayoutError("duplicate migrated execution units")
    return rows


def _stamp(path):
    info = path.lstat()
    stamp = (info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_mtime_ns, info.st_ctime_ns)
    if path.is_symlink():
        target = path.stat()
        stamp += (target.st_dev, target.st_ino, target.st_size, target.st_mtime_ns, target.st_ctime_ns)
    return stamp


def verified_baseline(root):
    """Fail closed if a certified baseline exists but no longer proves closure.

    A process-local stat fence avoids rehashing the same multi-GB baseline at
    launch, reference handoff and dispatch. A new process always checks bytes.
    """
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    proof_path = layout.path(PROOF)
    if not proof_path.exists() and not proof_path.is_symlink():
        marker = root / MIGRATION
        if marker.is_file():
            journal = json.loads(marker.read_text())
            if journal.get("adapter") == ADAPTER and journal.get("state") == "committed":
                raise LayoutError("certified original-engine baseline receipt is missing; refusing new-engine recomputation")
        return None
    if layout.version != 2 or proof_path.is_symlink() or not proof_path.is_file():
        raise LayoutError("invalid migrated LGZ baseline receipt")
    try:
        raw = proof_path.read_bytes()
        proof = json.loads(raw)
        journal_path = layout.path(MIGRATION)
        if journal_path.is_symlink():
            raise LayoutError("migration journal cannot be a symlink")
        journal = json.loads(journal_path.read_text())
        _check_journal(root, journal)
        if (journal["state"] != "committed" or journal["adapter"] != ADAPTER
                or proof.get("schema") != SCHEMA or proof.get("schema_version") != 1
                or proof.get("plan_sha256") != journal["plan_sha256"]):
            raise LayoutError("migrated LGZ baseline is not bound to a committed migration")
        additions = {row["destination"]: row["after"] for row in journal.get("additions", [])}
        if not matches(proof_path, additions[PROOF]):
            raise LayoutError("migrated LGZ baseline receipt changed")
        rows = plan_rows(root)
        finalizer = [i for i, row in enumerate(rows) if row["unit_id"] == "finalize_evidence"]
        if len(finalizer) != 1 or rows[:finalizer[0] + 1] != proof["prefix"] or rows != proof["execution_plan"]:
            raise LayoutError("certified original-engine scientific execution plan changed")
        files = []
        for row in proof["scientific_files"]:
            path = layout.path(relative_path(row["destination"]))
            files.append((path, row["identity"]))
        entries = {row["source"]: row for row in journal["entries"]}
        for source, expected in proof["runtime_snapshot_at_migration"].items():
            entry = entries[source]
            if entry["before"] != expected:
                raise LayoutError("legacy runtime snapshot binding changed")
            path = (root / ".runtime/migrations" / journal["id"] / "originals" / source
                    if entry["before"] != entry["after"] else layout.path(entry["destination"]))
            files.append((path, expected))
        stamps = tuple((str(path), _stamp(path)) for path, _ in files)
        key = (str(root), fingerprint(proof), fingerprint(journal), fingerprint(rows))
        if _CACHE.get(key) == stamps:
            return proof
        for path, expected in files:
            if not matches(path, expected):
                raise LayoutError("certified original-engine LGZ artifact changed: " + str(path))
        if validate_contract(root) != proof["contract"]:
            raise LayoutError("original LGZ scientific contract changed after migration")
        if tuple((str(path), _stamp(path)) for path, _ in files) != stamps:
            raise LayoutError("original LGZ baseline changed while being verified")
        _CACHE.clear()
        _CACHE[key] = stamps
        return proof
    except (OSError, ValueError, KeyError, TypeError, ContractError) as error:
        raise LayoutError("migrated LGZ baseline is not valid; refusing to recompute it with a new engine: " + str(error)) from error
