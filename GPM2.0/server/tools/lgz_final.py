"""Publish an explicitly named LGZ baseline, never a fake refined tool result."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import tempfile
import uuid

try:
    from workspace_layout import WorkspaceLayout
    from refinement_sources import FastaCatalog
    from refinement_publication import verify_baseline, write_table
    from refinement_commit import inventory, matches, layout_and_lock, sync_tree
    from post_lgz_degap import IndexedFasta, digest
    from workspace_migration import durable_json, rename_synced, ensure_directory
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout
    from .refinement_sources import FastaCatalog
    from .refinement_publication import verify_baseline, write_table
    from .refinement_commit import inventory, matches, layout_and_lock, sync_tree
    from .post_lgz_degap import IndexedFasta, digest
    from .workspace_migration import durable_json, rename_synced, ensure_directory


def publish_baseline(root, lock):
    layout = layout_and_lock(root, lock)
    root = layout.root
    pointer = layout.path(".runtime/refinement/lgz_baseline.json")
    target = layout.path("05_final/00_lgz")
    if pointer.is_symlink():
        raise ValueError("LGZ baseline publication receipt must not be a symbolic link")
    old = json.loads(pointer.read_text()) if pointer.exists() else None
    if old is not None and (not isinstance(old, dict) or old.get("state") not in {"none", "publishing", "committed"}):
        raise ValueError("invalid LGZ baseline publication receipt")
    if old and old.get("state") == "publishing":
        prepared, backup = layout.path(old["prepared"]), layout.path(old["backup"])
        if target.exists() and matches(target, old["files"]):
            old["state"] = "committed"
            durable_json(pointer, old)
        else:
            prior = old.get("previous")
            if backup.exists():
                if target.exists() or not prior or not matches(backup, prior["files"]):
                    raise ValueError("LGZ baseline recovery refuses changed or unowned data")
                rename_synced(backup, target)
            elif target.exists() and (not prior or not matches(target, prior["files"])):
                raise ValueError("LGZ baseline publication was modified while interrupted")
            durable_json(pointer, prior or {"state": "none"})
            old = prior
    if old and old.get("state") == "none":
        old = None
    if old and not target.exists():
        raise ValueError("committed LGZ baseline publication is missing; refusing to claim it complete")
    if target.exists() and (not old or not matches(target, old["files"])):
        raise ValueError("refusing to overwrite an unowned or modified LGZ baseline")
    final_file = layout.path("metadata/grt_final_path.json")
    baseline = json.loads(final_file.read_text())
    fasta = layout.path(baseline["q4_relpath"])
    binding = {"final_path_sha256": digest(final_file), "assembly_sha256": digest(fasta)}
    if old and old.get("binding") == binding:
        return old
    home = layout.path(".runtime/refinement/lgz_baselines/" + uuid.uuid4().hex)
    ensure_directory(home)
    with tempfile.TemporaryDirectory(prefix="indexes-", dir=home) as temporary:
        catalog = FastaCatalog(root, Path(temporary) / "sources")
        catalog.load_workspace()
        indexed = IndexedFasta(fasta, Path(temporary) / "baseline.fa")
        gaps = verify_baseline(baseline, catalog, indexed)
        prepared = home / "final"
        prepared.mkdir()
        shutil.copyfile(fasta, prepared / "assembly.fa")
        shutil.copyfile(final_file, prepared / "final_path.json")
        write_table(prepared / "sources.tsv", ["dataset", "contig", "length", "fasta_path", "path_scope", "origin", "fasta_sha256"], catalog.manifest_rows(baseline))
        write_table(prepared / "remaining_gaps.tsv", ["gap_id", "chromosome", "start", "end"], [asdict(gap) for gap in gaps])
        durable_json(prepared / "provenance.json", {"schema": "cgat.lgz-baseline", "schema_version": 1,
                     "tool": "lgz", "status": "lgz_only_baseline", "refinement_applied": False, "binding": binding})
        catalog.verify_unchanged()
        if digest(fasta) != binding["assembly_sha256"] or digest(final_file) != binding["final_path_sha256"]:
            raise ValueError("LGZ baseline changed during final staging")
    sync_tree(prepared)
    record = {"schema": "cgat.lgz-baseline-publication", "state": "publishing", "binding": binding,
              "files": inventory(prepared), "prepared": prepared.relative_to(root).as_posix(),
              "backup": (home / "previous").relative_to(root).as_posix(), "previous": old}
    ensure_directory(target.parent)
    durable_json(pointer, record)
    if target.exists():
        rename_synced(target, home / "previous")
    rename_synced(prepared, target)
    record["state"] = "committed"
    durable_json(pointer, record)
    return record


def validate_baseline(root):
    try:
        layout = WorkspaceLayout.detect(root)
        pointer = layout.path(".runtime/refinement/lgz_baseline.json")
        if pointer.is_symlink():
            return False
        receipt = json.loads(pointer.read_text())
        baseline_file = layout.path("metadata/grt_final_path.json")
        baseline = json.loads(baseline_file.read_text())
        return (receipt.get("schema") == "cgat.lgz-baseline-publication" and receipt.get("state") == "committed"
                and receipt["binding"] == {"final_path_sha256": digest(baseline_file), "assembly_sha256": digest(layout.path(baseline["q4_relpath"]))}
                and matches(layout.path("05_final/00_lgz"), receipt["files"]))
    except (OSError, ValueError, KeyError, TypeError):
        return False
