"""Publish one named Full/Light generation (and, if present, its automatic patch).

An interrupted rename is rolled back under the workspace lock. Only the durable
receipt declares a new generation committed. Manual files are never enumerated,
renamed or included in this transaction.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import zipfile

from delivery_archive import archive_options, create_archive
from project_auto_patch import INDEX as PATCH_INDEX
from project_delivery import INDEX, VERSION_DIR, generation, project_payload
from refinement_commit import PublicationError, inventory, layout_and_lock, read_json
from refinement_tools import fingerprint
from run_orchestration import sha256_file
from server_report import _final_report_files, _stage_final_report, _validate_delivery_archive
from workspace_migration import durable_json, ensure_directory, sync_directories

HOME = ".runtime/refinement/project-delivery"
SCHEMA = "cgat.project-delivery-publication"


def _identity(path):
    if path.is_symlink() or path.exists() and not path.is_file():
        raise PublicationError(f"expected a regular project delivery file: {path}")
    return sha256_file(path) if path.exists() else None


def _names(layout, fmt):
    if fmt not in ("zip", "tar.gz") or not layout.result_prefix:
        raise PublicationError("invalid project delivery format or layout")
    prefix = layout.result_prefix
    return {"full": f"{prefix}.full.{fmt}", "light": f"{prefix}.light.{fmt}", "auto": f"{prefix}.auto.patch.zip"}


def _checked_receipt(proof, names):
    if not proof:
        return {}
    files = proof.get("files", {})
    if (proof.get("schema") != SCHEMA or proof.get("schema_version") != 1
            or set(files) not in ({"full", "light"}, set(names))
            or not re.fullmatch(r"[0-9a-f]{64}", proof.get("generation", ""))):
        raise PublicationError("invalid project delivery receipt")
    for key, item in files.items():
        if item.get("file") != names[key] or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise PublicationError("project delivery receipt has a different name, format or digest")
    return {key: row["sha256"] for key, row in files.items()}


def _recover(home, dest, names):
    pointer = home / "committed.json"
    prior = read_json(pointer) if pointer.exists() or pointer.is_symlink() else {}
    actual = _checked_receipt(prior, names)
    journal = home / "publishing.json"
    if journal.exists() or journal.is_symlink():
        tx = read_json(journal)
        if not re.fullmatch(r"[0-9a-f]{32}", tx["id"]) or prior not in (tx["old"], tx["new"]):
            raise PublicationError("unrecognized interrupted project publication")
        backup = home / tx["id"]
        if backup.is_symlink() or not backup.is_dir():
            raise PublicationError("missing project recovery directory")
        new = _checked_receipt(tx["new"], names)
        old = _checked_receipt(tx["old"], names)
        if prior != tx["new"]:
            for key, name in names.items():
                target = dest / name
                seen = _identity(target)
                if seen == old.get(key):
                    continue
                if seen != new.get(key) or seen is None:
                    raise PublicationError(f"project archive changed during recovery: {name}")
                if key in old:
                    source = backup / key
                    if _identity(source) != old[key]:
                        raise PublicationError("old project archive backup does not verify")
                    # Keep the recovery inode available even if another crash interrupts rollback.
                    with tempfile.TemporaryDirectory(dir=backup) as tmp:
                        replacement = Path(tmp) / "old"
                        os.link(source, replacement)
                        os.replace(replacement, target)
                else:
                    target.unlink()
                sync_directories(dest)
        for key, name in names.items():
            if _identity(dest/name) != actual.get(key):
                raise PublicationError(f"cannot close recovery with a changed project archive: {name}")
        journal.unlink()
        sync_directories(home)
        shutil.rmtree(backup)
        return prior
    for key, name in names.items():
        if _identity(dest/name) != actual.get(key):
            raise PublicationError(f"unowned, missing or changed project delivery: {name}")
    return prior


def _rows(dest, proof):
    return [{**proof["files"][key], "path": str(dest / proof["files"][key]["file"])} for key in ("full", "light")]


def publish_pair(root, lock, stages, patch, patch_sha):
    layout = layout_and_lock(root, lock)
    if not layout.project_delivery:
        raise PublicationError("project generation publishing is not enabled on this workspace")
    fmt, threads = archive_options(layout.root)
    names = _names(layout, fmt)
    dest, home = layout.path("07_delivery"), layout.path(HOME)
    for directory in (dest, home):
        ensure_directory(directory)
    prev = _recover(home, dest, names)
    baseline_receipt = read_json(layout.path(".runtime/refinement/lgz_baseline.json"))
    path = layout.path("metadata/grt_final_path.json")
    if (baseline_receipt.get("state") != "committed" or _identity(path) != baseline_receipt["binding"]["final_path_sha256"]):
        raise PublicationError("project deliveries require a committed immutable LGZ baseline")
    baseline = {"final_path_sha256": fingerprint(read_json(path)), "assembly_sha256": baseline_receipt["binding"]["assembly_sha256"]}
    variants = {}
    if patch is not None:
        if _identity(patch) != patch_sha or not patch_sha:
            raise PublicationError("project delivery automatic patch identity changed")
        with zipfile.ZipFile(patch) as archive:
            patch_index = json.loads(archive.read(PATCH_INDEX))
            if patch_index["baseline"] != baseline:
                raise PublicationError("automatic patch belongs to another LGZ job")
            variants = patch_index["variants"]
    elif patch_sha is not None or prev and "auto" in prev["files"]:
        raise PublicationError("missing previously committed automatic patch")
    key = generation(baseline, variants)
    if set(stages) != {"full", "light"}:
        raise PublicationError("both project delivery stages are required")
    # Report timestamps do not make a new scientific generation. Baseline input/metadata
    # drift, however, cannot be silently adopted under the old immutable version.
    inputs = {mode: fingerprint(inventory(stage)["files"]) for mode,stage in stages.items()}
    if prev and prev["inputs"] != inputs:
        raise PublicationError("LGZ delivery payload changed since this job was published")
    if prev and prev["generation"] == key:
        if patch_sha != prev["files"].get("auto", {}).get("sha256"):
            raise PublicationError("automatic patch bytes differ for a published generation")
        return _rows(dest, prev)
    from server_source_identity import read_rows
    reference_sources={row["reference_chr_name"]:sha256_file(layout.path(row["fasta_relpath"]))
                       for row in read_rows(layout.path("metadata/reference_chr_locator.tsv"))}
    report, report_files, required = _final_report_files(layout.root)
    members = {f"{layout.root.name}/report/{p.relative_to(report).as_posix()}" for p in required}
    members.add(f"{layout.root.name}/{INDEX}")
    files = {}
    with tempfile.TemporaryDirectory(dir=home,prefix="build-") as tmp:
        pending = Path(tmp)
        for mode in ("full", "light"):
            stage = stages[mode]
            if stage.name != layout.root.name or (stage/VERSION_DIR).exists() or (stage/"report").exists():
                raise PublicationError("invalid LGZ staging for project publication")
            with tempfile.TemporaryDirectory(dir=pending) as scratch:
                staged = Path(scratch) / layout.root.name
                shutil.copytree(stage,staged,copy_function=os.link,symlinks=True)
                manifest = project_payload(staged,mode,baseline,patch,patch_sha=patch_sha,reference_sources=reference_sources)
                if manifest["generation"] != key:
                    raise PublicationError("Full and Light do not represent the same project generation")
                _stage_final_report(layout.root,staged,report,report_files)
                archive = pending / names[mode]
                create_archive(staged,archive,fmt,threads)
                proof = _validate_delivery_archive(archive,members,fmt)
                files[mode] = {"file": names[mode], "size_bytes": archive.stat().st_size, "sha256": proof.sha256}
        if patch is not None:
            os.link(patch,pending / names["auto"])
            files["auto"] = {"file":names["auto"],"size_bytes":patch.stat().st_size,"sha256":patch_sha}
        if {m: fingerprint(inventory(s)["files"]) for m,s in stages.items()} != inputs:
            raise PublicationError("LGZ staging changed during project archive construction")
        for mode, row in files.items():
            file = pending / names[mode]
            if _identity(file) != row["sha256"]:
                raise PublicationError("prepared project archive changed before publishing")
            with file.open("rb") as stream:
                os.fsync(stream.fileno())
        layout_and_lock(root, lock)
        current = _recover(home,dest,names)
        if current != prev:
            raise PublicationError("project delivery changed during construction")
        next_proof = {"schema":SCHEMA,"schema_version":1,"generation":key,"inputs":inputs,"files":files,
                      "tools":{tool:{k:v[k] for k in ("run_id","light_manifest")} for tool,v in variants.items()}}
        txid = uuid.uuid4().hex
        backup = home / txid
        ensure_directory(backup)
        for mode, row in prev.get("files",{}).items():
            os.link(dest / row["file"], backup / mode)
        sync_directories(backup,home)
        durable_json(home / "publishing.json", {"id":txid,"old":prev,"new":next_proof})
        try:
            for mode in files:
                target = dest / names[mode]
                if mode in prev.get("files",{}):
                    if _identity(target) != prev["files"][mode]["sha256"]:
                        raise PublicationError("project archive changed during replacement")
                    os.replace(pending / names[mode], target)
                else:
                    os.link(pending / names[mode], target)
                sync_directories(dest)
            if any(_identity(dest / names[m]) != row["sha256"] for m,row in files.items()):
                raise PublicationError("project delivery did not verify before commit")
            durable_json(home / "committed.json",next_proof)
        except Exception:
            _recover(home,dest,names)
            raise
        (home / "publishing.json").unlink()
        sync_directories(home)
        shutil.rmtree(backup)
        return _rows(dest,next_proof)


def publish_current(root, lock, *, runner_staging=False):
    """Runner and standalone refinement share one writer and the same workspace lock."""
    from delivery_archive import delivery_staging_path
    from lgz_app_package import build, _derive_light, _pair_inventory
    from project_auto_patch import patch_path, publish_auto_patch

    layout = layout_and_lock(root, lock)
    patch_sha = publish_auto_patch(layout.root, lock)
    patch = patch_path(layout) if patch_sha else None
    if runner_staging:
        stages = {mode:delivery_staging_path(layout.root,mode) for mode in ("full","light")}
        rows = publish_pair(layout.root, lock, stages, patch, patch_sha)
        # These are exact private builder-owned trees, not the workspace or user archives.
        for stage in stages.values():
            shutil.rmtree(stage)
            with contextlib.suppress(OSError):
                stage.parent.rmdir()
        with contextlib.suppress(OSError):
            stages["full"].parent.parent.rmdir()
        return rows
    home = layout.path(HOME)
    ensure_directory(home)
    with tempfile.TemporaryDirectory(prefix="projection-",dir=home) as tmp:
        stages = {mode:Path(tmp)/mode/layout.root.name for mode in ("full","light")}
        build(layout.root, stages["full"], True, standalone_delivery=True)
        _derive_light(stages["full"], stages["light"], _pair_inventory(stages["full"]))
        return publish_pair(layout.root, lock, stages, patch, patch_sha)


def publish_standalone(root):
    from run_all_runner import WorkspaceLock, new_run_id
    root = Path(root).resolve()
    lock = WorkspaceLock(root,new_run_id())
    lock.acquire()
    try:
        return publish_current(root,lock)
    finally:
        lock.release()


def tool_links(layout,tool,run_id,light_manifest):
    """Resolve a whole-project pair only if this exact tool generation went into it."""
    home = layout.path(HOME)
    pointer = home / "committed.json"
    journal = home / "publishing.json"
    if journal.exists() or journal.is_symlink() or not pointer.exists():
        return {}
    proof = read_json(pointer)
    if proof.get("tools",{}).get(tool) != {"run_id":run_id,"light_manifest":light_manifest}:
        return {}
    names = _names(layout,archive_options(layout.root)[0])
    hashes = _checked_receipt(proof,names)
    for mode in hashes:
        target = layout.path("07_delivery/" + names[mode])
        if target.is_symlink() or not target.is_file() or target.stat().st_size != proof["files"][mode]["size_bytes"]:
            return {}
    return {m:"07_delivery/" + names[m] for m in hashes}
