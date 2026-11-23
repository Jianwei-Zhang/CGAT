"""Journaled publication of one tool's final, report and both App deliveries.

The receipt is the commit point across three physical directories. Readers must
not infer completion from directory existence. The caller holds WorkspaceLock
and supplies the versioned App-delivery validator; no public CLI bypass exists.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES
    from workspace_migration import durable_json, ensure_directory, rename_synced, sync_directories
    from run_orchestration import sha256_file as digest
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES
    from .workspace_migration import durable_json, ensure_directory, rename_synced, sync_directories
    from .run_orchestration import sha256_file as digest

SCHEMA = "cgat.refinement-commit"
AREAS = ("final", "report", "delivery")


class PublicationError(ValueError):
    pass


def layout_and_lock(root, lock):
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if (layout.version != 2 or lock is None or not lock.acquired or lock.for_migration
            or lock.server_dir.resolve() != root or lock.state_dir != layout.path(".run_all")
            or lock._existing_owner() != lock.owner):
        raise PublicationError("refinement publication requires the held numbered-workspace lock")
    return layout


def inventory(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise PublicationError("publication tree is missing or symlinked: " + str(directory))
    files, directories = {}, []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise PublicationError("publication tree cannot contain symlinks")
        relative = path.relative_to(directory).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = digest(path)
        else:
            raise PublicationError("publication tree contains a non-regular entry")
    return {"files": files, "directories": directories}


def sync_tree(directory):
    directories = [directory]
    for path in directory.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        elif path.is_dir():
            directories.append(path)
    sync_directories(*directories)


def matches(directory, expected):
    try:
        return inventory(directory) == expected
    except (OSError, ValueError):
        return False


def targets(layout, tool):
    if tool not in TOOL_DIRECTORIES:
        raise PublicationError("unknown refinement publication tool")
    code = TOOL_DIRECTORIES[tool]
    return {"final": layout.path(f"05_final/{code}"),
            "report": layout.path(f"06_report/02_refinement/{code}"),
            "delivery": layout.path(f"07_delivery/{code}")}


def pointer_path(layout, tool):
    if tool not in TOOL_DIRECTORIES:
        raise PublicationError("unknown refinement publication tool")
    return layout.path(f".runtime/refinement/publication/{tool}.json")


def journal_path(layout, transaction):
    if not isinstance(transaction, str) or not re.fullmatch(r"[0-9a-f]{32}", transaction):
        raise PublicationError("invalid publication transaction")
    return layout.path(f".runtime/refinement/publications/{transaction}/journal.json")


def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise PublicationError("publication metadata must be a regular file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise PublicationError("invalid publication metadata")
    return value


def current_publication(root, tool, *, verify=True):
    layout = WorkspaceLayout.detect(Path(root))
    pointer = pointer_path(layout, tool)
    if not pointer.exists():
        return None
    state = read_json(pointer)
    if state.get("schema") != SCHEMA or state.get("tool") != tool:
        raise PublicationError("invalid tool publication pointer")
    if state.get("status") == "none":
        return None
    if state.get("status") != "committed":
        raise PublicationError("tool publication is incomplete; recover it before treating any result as final")
    journal_file = journal_path(layout, state.get("transaction"))
    if digest(journal_file) != state.get("journal_sha256"):
        raise PublicationError("publication receipt changed")
    journal = read_json(journal_file)
    if (journal.get("schema") != SCHEMA or journal.get("schema_version") != 1 or journal.get("state") != "committed"
            or journal.get("tool") != tool or journal.get("transaction") != state["transaction"]
            or set(journal.get("areas", {})) != set(AREAS)):
        raise PublicationError("unsupported or incomplete publication receipt")
    if verify:
        for name, target in targets(layout, tool).items():
            if not matches(target, journal["areas"][name]["new"]):
                raise PublicationError("published " + name + " changed or is incomplete")
    return journal


def committed_final_history(layout, tool):
    """Older App projects can still resolve their exact sources after staging is reclaimed."""
    yield from committed_area_history(layout, tool, "final")


def committed_area_history(layout, tool, name):
    if name not in AREAS:
        raise PublicationError("unknown publication area")
    current = current_publication(layout.root,tool,verify=False)
    seen = set()
    while current:
        txid = current["transaction"]
        if txid in seen:
            raise PublicationError("cycle in tool publication history")
        seen.add(txid)
        previous = current.get("previous_pointer")
        if not previous or previous.get("status") == "none":
            break
        if previous.get("status") != "committed" or previous.get("tool") != tool:
            raise PublicationError("invalid previous tool publication pointer")
        old = journal_path(layout,previous["transaction"])
        if digest(old) != previous["journal_sha256"]:
            raise PublicationError("previous tool publication journal changed")
        history = read_json(old)
        area = current["areas"][name]
        if (history.get("state") != "committed" or history.get("tool") != tool
                or history.get("transaction") != previous["transaction"] or history["areas"][name]["new"] != area["previous"]):
            raise PublicationError("previous tool publication does not match its successor")
        if not area.get("unchanged"):
            yield journal_path(layout,txid).parent / "previous" / name, area["previous"]["files"]
        current = history


def release_published_stages(layout, tool, result, record, receipt, delivery, batch):
    """Only remove an exact regular-file stage already present in the verified public generation."""
    code, run = TOOL_DIRECTORIES[tool], receipt["run_id"]
    live = targets(layout,tool)
    private = {"final":layout.path(f".runtime/refinement/{code}/{run}/final"),
               "delivery":layout.path(f".runtime/refinement/delivery/{tool}/{run}/{receipt['delivery_validation']['generation_sha256']}")}
    selected = {"final":Path(result["staging"]), "report":Path(record["report"]["directory"]), "delivery":delivery}
    base = layout.path(f"04_refinement/{code}/05_report/{run}")
    if selected["report"].parent == base and re.fullmatch(r"site-[a-f0-9]{20}",selected["report"].name):
        private["report"] = selected["report"]
    # Redirect live references before reclaiming. An interruption can only leave an extra copy.
    result["staging"] = record["final_staging"] = str(live["final"])
    record["report"].update(directory=str(live["report"]), report=str(live["report"] / "report.html"))
    durable_json(layout.path(f".runtime/refinement/batches/{batch['batch_id']}.json"),batch)
    for area, path in private.items():
        if selected.get(area) != path or path == live[area] or not path.exists():
            continue
        expected = receipt["areas"][area]["new"]
        if matches(path,expected) and matches(live[area],expected):
            try:
                shutil.rmtree(path)
                sync_directories(path.parent)
            except OSError as exc:
                print(f"[PROJECT STAGING] publication is committed; could not remove {path}: {exc}",file=sys.stderr)


def validate_set(final, report, delivery, tool, run_id, validate_delivery):
    provenance = read_json(final / "provenance.json")
    if (provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or provenance.get("execution", {}).get("status") != "success"):
        raise PublicationError("publication needs a successful tool-bound admitted result")
    if set(provenance.get("artifacts", {})) != {"assembly.fa", "final_path.json", "sources.tsv", "remaining_gaps.tsv"}:
        raise PublicationError("incomplete final result")
    for name, sha in provenance["artifacts"].items():
        if digest(final / name) != sha:
            raise PublicationError("final artifact changed before publication")
    path = read_json(final / "final_path.json")
    if (path.get("schema") != "cgat.refined-final-path" or path.get("schema_version") != 1 or path.get("tool") != tool
            or path.get("baseline") != provenance.get("baseline")
            or path.get("recipe_sha256") != provenance["execution"].get("recipe_sha256")):
        raise PublicationError("delivery Final Path is not the admitted refined path")
    manifest = read_json(report / "manifest.json")
    if (manifest.get("schema") != "cgat.refinement-report"
            or manifest.get("binding", {}).get("provenance_sha256") != digest(final / "provenance.json")
            or manifest.get("files") != {name: sha for name, sha in inventory(report)["files"].items() if name != "manifest.json"}
            or not (report / "report.html").is_file()):
        raise PublicationError("portable report does not bind the admitted result")
    # The real App format validator must inspect both archives, sequence/source
    # availability and Final Path identities. Hashes supplied by a user are not
    # an alternative. Tests inject a fixture validator, never a production flag.
    proof = validate_delivery(delivery, final)
    expected = {row["chr"]: {"length": row["length"], "sha256": row["sha256"]} for row in path["chromosomes"]}
    if (not isinstance(proof, dict) or proof.get("schema") != "cgat.refinement-delivery-validation"
            or proof.get("schema_version") != 1 or proof.get("tool") != tool or proof.get("run_id") != run_id
            or proof.get("modes") != ["full", "light"] or not proof.get("validator")
            or proof.get("final_path_sha256") != provenance["artifacts"]["final_path.json"]
            or proof.get("assemblies") != expected
            or proof.get("provenance_sha256") != digest(final / "provenance.json")
            or proof.get("report_manifest_sha256") != digest(report / "manifest.json")):
        raise PublicationError("App delivery validator did not prove both packages represent this refined result")
    return proof


def _save(layout, journal):
    durable_json(journal_path(layout, journal["transaction"]), journal)


def _commit_pointer(layout, journal):
    durable_json(pointer_path(layout, journal["tool"]), {"schema": SCHEMA, "tool": journal["tool"], "status": "committed",
                 "transaction": journal["transaction"], "journal_sha256": digest(journal_path(layout, journal["transaction"]))})


def _rollback(layout, journal):
    private = journal_path(layout, journal["transaction"]).parent
    for area, target in reversed(list(targets(layout, journal["tool"]).items())):
        row = journal["areas"][area]
        prepared, backup = private / "prepared" / area, private / "previous" / area
        if row.get("unchanged") is True:
            if (row["new"] != row["previous"] or not matches(target, row["new"])
                    or prepared.exists() or backup.exists()):
                raise PublicationError("unchanged publication area changed; refusing rollback: " + area)
            continue
        if target.exists():
            if matches(target, row["new"]) and not prepared.exists():
                rename_synced(target, prepared)
            elif not matches(target, row["previous"]):
                raise PublicationError("publication target changed; refusing destructive rollback: " + area)
        if backup.exists():
            if target.exists() or not matches(backup, row["previous"]):
                raise PublicationError("publication backup changed; refusing overwrite: " + area)
            rename_synced(backup, target)
        if row["previous"] is None and target.exists():
            raise PublicationError("unexpected data appeared during publication rollback")
    journal["state"] = "rolled_back"
    _save(layout, journal)
    durable_json(pointer_path(layout, journal["tool"]), journal["previous_pointer"] or
                 {"schema": SCHEMA, "tool": journal["tool"], "status": "none"})


def recover_publication(root, lock, tool, validate_delivery):
    layout = layout_and_lock(root, lock)
    state = read_json(pointer_path(layout, tool))
    if state.get("schema") != SCHEMA or state.get("tool") != tool or state.get("status") != "publishing":
        raise PublicationError("no interrupted publication to recover")
    journal = read_json(journal_path(layout, state.get("transaction")))
    if (journal.get("schema") != SCHEMA or journal.get("schema_version") != 1 or journal.get("tool") != tool
            or journal.get("transaction") != state["transaction"] or set(journal.get("areas", {})) != set(AREAS)):
        raise PublicationError("invalid interrupted publication journal")
    if journal.get("state") == "committed":
        current = targets(layout, tool)
        if not all(matches(current[area], journal["areas"][area]["new"]) for area in AREAS):
            raise PublicationError("completed publication changed before receipt recovery")
        validate_set(current["final"], current["report"], current["delivery"], tool, journal["run_id"], validate_delivery)
        _commit_pointer(layout, journal)
        return {"status": "committed", "transaction": journal["transaction"]}
    if journal.get("state") not in {"publishing", "rolling_back", "rolled_back"}:
        raise PublicationError("unsupported publication recovery state")
    _rollback(layout, journal)
    return {"status": "rolled_back", "transaction": journal["transaction"]}


def publish_result(root, lock, result, report, delivery, validate_delivery):
    layout = layout_and_lock(root, lock)
    root, tool, run_id = layout.root, result["tool"], result["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise PublicationError("invalid publication run")
    current = targets(layout, tool)
    previous = current_publication(root, tool)
    pointer = pointer_path(layout, tool)
    prior_pointer = read_json(pointer) if pointer.exists() else None
    for target in current.values():
        if (target.exists() or target.is_symlink()) and previous is None:
            raise PublicationError("refusing to replace an unowned final/report/delivery directory")
    source = {"final": Path(result["staging"]), "report": Path(report["directory"]), "delivery": Path(delivery)}
    transaction = uuid.uuid4().hex
    private = journal_path(layout, transaction).parent
    for area, path in source.items():
        if not path.is_absolute() or not path.resolve().is_relative_to(root):
            raise PublicationError("publication staging must belong to its workspace")
        if path == root or private.is_relative_to(path) or any(path in target.parents for target in current.values()):
            raise PublicationError("publication staging cannot contain public or transaction namespaces")
        layout.path(path.relative_to(root).as_posix())
        inventory(path)
    marker = read_json(layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json"))
    if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool or marker.get("run_id") != run_id
            or marker.get("provenance_sha256") != digest(source["final"] / "provenance.json")):
        raise PublicationError("native attempt completion marker does not bind this publication")
    if digest(source["report"] / "manifest.json") != report.get("manifest_sha256"):
        raise PublicationError("prepared report manifest changed")
    proof = validate_set(source["final"], source["report"], source["delivery"], tool, run_id, validate_delivery)
    ensure_directory(private / "prepared")
    ensure_directory(private / "previous")
    journal = {"schema": SCHEMA, "schema_version": 1, "transaction": transaction, "tool": tool, "run_id": run_id,
               "state": "preparing", "previous_pointer": prior_pointer, "delivery_validation": proof, "areas": {}}
    for area in AREAS:
        expected = inventory(source[area])
        old = previous["areas"][area]["new"] if previous else None
        unchanged = expected == old and matches(current[area], expected)
        if not unchanged:
            shutil.copytree(source[area], private / "prepared" / area)
            if not matches(private / "prepared" / area, expected) or not matches(source[area], expected):
                raise PublicationError("publication staging changed during preparation")
            sync_tree(private / "prepared" / area)
        journal["areas"][area] = {"new": expected, "previous": old, "unchanged": unchanged}
        ensure_directory(current[area].parent)
    layout_and_lock(root, lock)
    journal["state"] = "publishing"
    _save(layout, journal)
    durable_json(pointer, {"schema": SCHEMA, "tool": tool, "status": "publishing", "transaction": transaction})
    try:
        for area in AREAS:
            if journal["areas"][area].get("unchanged") is True:
                if not matches(current[area], journal["areas"][area]["new"]):
                    raise PublicationError("unchanged publication area changed before commit")
                continue
            if current[area].exists():
                if not matches(current[area], journal["areas"][area]["previous"]):
                    raise PublicationError("previous publication changed before replacement")
                rename_synced(current[area], private / "previous" / area)
            rename_synced(private / "prepared" / area, current[area])
        layout_and_lock(root, lock)
        if not all(matches(current[area], journal["areas"][area]["new"]) for area in AREAS):
            raise PublicationError("new publication changed before commit")
        validate_set(current["final"], current["report"], current["delivery"], tool, run_id, validate_delivery)
        journal["state"] = "committed"
        _save(layout, journal)
        _commit_pointer(layout, journal)
    except Exception:
        if journal["state"] != "committed":
            journal["state"] = "rolling_back"
            _save(layout, journal)
            _rollback(layout, journal)
        raise
    return current_publication(root, tool)
