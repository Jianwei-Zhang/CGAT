"""Immutable manual-candidate catalogs, separate from the frozen LGZ workspace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from workspace_layout import WorkspaceLayout, relative_path
from workspace_migration import durable_json, ensure_directory, rename_synced, sync_directories
from run_orchestration import sha256_file as digest
from refinement_commit import layout_and_lock

HOME = "04_refinement/01_degap/06_manual/01_catalog"
POINTER = ".runtime/manual_degap/current.json"
PENDING = ".runtime/manual_degap/pending.json"
MANIFEST = ".runtime/manual_catalog.json"
_HASHES = {}
BASE_TABLES = ("prepare_options.tsv", "reference.tsv", "reference_chr_locator.tsv", "datasets.tsv",
               "source_seq_locator.tsv", "source_seq_n_regions.tsv", "chr_assignments.tsv",
               "track_members.tsv", "track_member_orders.tsv")


def read_object(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("manual catalog state must be a regular file: " + str(path))
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("invalid manual catalog state: " + str(path))
    return value


def base_binding(server):
    layout = WorkspaceLayout.detect(server)
    result = {}
    for name in BASE_TABLES:
        path = layout.path("metadata/" + name)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("original LGZ source table is not a regular file: " + name)
        result[name] = digest(path) if path.is_file() else None
    return result


def content_digest(path):
    """Content proof once per unchanged file in this process, never persisted."""
    path = path.resolve(strict=True)
    def stamp():
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    before = stamp()
    key = str(path)
    previous = _HASHES.get(key)
    if previous is not None and previous[0] == before:
        return previous[1]
    sha256 = digest(path)
    if stamp() != before:
        raise ValueError("manual catalog input changed during content verification")
    _HASHES[key] = (before, sha256)
    return sha256


def inventory(catalog, server):
    result = {}
    for path in sorted(catalog.rglob("*")):
        name = path.relative_to(catalog).as_posix()
        if name == MANIFEST:
            continue
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_file() or not target.is_relative_to(server):
                raise ValueError("manual catalog has an unowned input link: " + name)
            result[name] = {"link": os.readlink(path), "sha256": content_digest(target)}
        elif path.is_file():
            result[name] = {"sha256": content_digest(path)}
        elif not path.is_dir():
            raise ValueError("manual catalog has a special file: " + name)
    return result


def catalog_path(server, value):
    name = relative_path(value)
    if re.fullmatch(re.escape(HOME) + r"/[0-9a-f]{32}", name) is None:
        raise ValueError("invalid manual catalog location")
    path = WorkspaceLayout.detect(server).path(name)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("manual catalog must be a real directory")
    return path


def package_paths(server, row):
    layout = WorkspaceLayout.detect(server)
    paths = []
    for key in ("archive", "info"):
        name = relative_path(row[key])
        if not name.startswith(HOME + "/"):
            raise ValueError("manual package cache is outside its catalog")
        path = layout.path(name)
        if path.is_symlink() or not path.is_file() or digest(path) != row[key + "_sha256"]:
            raise ValueError("manual candidate package cache changed")
        paths.append(path)
    return tuple(paths)


def catalog_binding(server, pointer):
    server = Path(server).resolve()
    if pointer.get("schema") != "cgat.manual-degap-current" or pointer.get("schema_version") != 1:
        raise ValueError("unsupported manual candidate pointer")
    catalog = catalog_path(server, pointer["catalog"])
    manifest_path = WorkspaceLayout.detect(catalog).path(MANIFEST)
    if digest(manifest_path) != pointer["catalog_sha256"]:
        raise ValueError("manual catalog completion receipt changed")
    manifest = read_object(manifest_path)
    if (WorkspaceLayout.detect(catalog).version != 2 or manifest.get("schema") != "cgat.manual-degap-catalog"
            or manifest.get("schema_version") != 1 or manifest.get("base") != base_binding(server)):
        raise ValueError("manual catalog or its original LGZ base changed")
    return catalog, manifest


def verify_catalog(server, pointer):
    catalog, manifest = catalog_binding(server, pointer)
    if manifest.get("files") != inventory(catalog, Path(server).resolve()):
        raise ValueError("manual catalog or its original LGZ base changed")
    for token, row in manifest["packages"].items():
        if re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise ValueError("invalid manual candidate token")
        archive, info = package_paths(server, row)
        data = read_object(info)
        if data.get("recipe", {}).get("token") != token or data.get("sha256") != digest(archive):
            raise ValueError("manual candidate registry does not bind its package")
    return catalog, manifest


def bound_current(server):
    """Verify catalog/base binding; callers must verify consumed file closure.

    Use current() when claiming full catalog/registry completion instead.
    """
    layout = WorkspaceLayout.detect(server)
    pending = layout.path(PENDING)
    if pending.exists() or pending.is_symlink():
        raise ValueError("manual candidate publication is incomplete; collect again under the workspace lock")
    path = layout.path(POINTER)
    if not path.exists() and not path.is_symlink():
        return layout.root, {"base": base_binding(server), "packages": {}}, None
    pointer = read_object(path)
    catalog, manifest = catalog_binding(layout.root, pointer)
    return catalog, manifest, pointer


def current(server):
    catalog, manifest, pointer = bound_current(server)
    if pointer:
        catalog, manifest = verify_catalog(Path(server).resolve(), pointer)
    return catalog, manifest, pointer


def new_path(server):
    return WorkspaceLayout.detect(server).path(HOME + "/" + uuid.uuid4().hex)


def seal(server, staging, destination, base, packages):
    """Seal a fresh immutable catalog; directory presence alone never adopts it."""
    server, staging, destination = Path(server).resolve(), Path(staging), Path(destination)
    if base_binding(server) != base or catalog_path(server, destination.relative_to(server).as_posix()) != destination:
        raise ValueError("original LGZ metadata changed during manual collection")
    ensure_directory(destination.parent)
    with tempfile.TemporaryDirectory(prefix=".catalog-", dir=destination.parent) as name:
        prepared = Path(name) / "catalog"
        shutil.copytree(staging, prepared, symlinks=True)
        for command in prepared.rglob("*.sh"):
            if not command.is_symlink():
                command.write_text(command.read_text().replace(str(staging), str(destination)))
        manifest = {"schema": "cgat.manual-degap-catalog", "schema_version": 1, "base": base,
                    "packages": packages, "files": inventory(prepared, server)}
        # Sync regular artifacts before the last completion receipt and rename.
        for path in prepared.rglob("*"):
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        durable_json(prepared / MANIFEST, manifest)
        sync_directories(*(path for path in prepared.rglob("*") if path.is_dir() and not path.is_symlink()), prepared)
        if inventory(prepared, server) != manifest["files"] or base_binding(server) != base:
            raise ValueError("manual catalog changed while being sealed")
        rename_synced(prepared, destination)
    pointer = {"schema": "cgat.manual-degap-current", "schema_version": 1,
               "catalog": destination.relative_to(server).as_posix(), "catalog_sha256": digest(destination / MANIFEST)}
    verify_catalog(server, pointer)
    return pointer


def copy_synced(source, destination):
    ensure_directory(destination.parent)
    descriptor, name = tempfile.mkstemp(prefix=".manual-publish-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, Path(source).open("rb") as stream:
            shutil.copyfileobj(stream, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, destination)
        sync_directories(destination.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def output_path(value):
    path = Path(value)
    if (not path.is_absolute() or path.name != "degap_results.zip"
            or any(p.is_symlink() for p in (path, *path.parents)) or (path.exists() and not path.is_file())):
        raise ValueError("manual result ZIP must use its explicit nonsymlink export destination")
    return path


def recover(server, lock, *, rollback=False):
    layout = layout_and_lock(server, lock)
    fence = layout.path(PENDING)
    if not fence.exists() and not fence.is_symlink():
        return None
    owner = read_object(fence)
    if owner.get("schema") != "cgat.manual-degap-pending" or re.fullmatch(r"[0-9a-f]{32}", owner.get("transaction", "")) is None:
        raise ValueError("invalid manual publication fence")
    home = layout.path(".runtime/manual_degap/transactions/" + owner["transaction"])
    plan = read_object(home / "plan.json")
    if digest(home / "plan.json") != owner.get("plan_sha256") or plan.get("schema") != "cgat.manual-degap-publication":
        raise ValueError("manual publication plan changed")
    pointer_file = layout.path(POINTER)
    pointer = read_object(pointer_file) if pointer_file.exists() or pointer_file.is_symlink() else None
    if pointer not in (plan["previous"], plan["next"]):
        raise ValueError("manual publication pointer changed; refusing recovery")
    output = output_path(plan["output"])
    actual = digest(output) if output.is_file() else None
    if actual not in (plan["previous_output_sha256"], plan["next"]["output_sha256"]):
        raise ValueError("manual result ZIP changed; refusing recovery")
    for key in ("pointer", "output"):
        expected = plan["backup_sha256"][key]
        if expected is not None and digest(home / (key + ".previous")) != expected:
            raise ValueError("manual publication backup changed")
    if not rollback and actual == plan["next"]["output_sha256"]:
        verify_catalog(layout.root, plan["next"])
        durable_json(pointer_file, plan["next"])
        outcome = "committed"
    else:
        if actual != plan["previous_output_sha256"]:
            if plan["previous_output_sha256"] is None:
                output.unlink()
                sync_directories(output.parent)
            else:
                copy_synced(home / "output.previous", output)
        if plan["previous"] is None:
            pointer_file.unlink(missing_ok=True)
            sync_directories(pointer_file.parent)
        else:
            copy_synced(home / "pointer.previous", pointer_file)
        outcome = "rolled_back"
    durable_json(home / "outcome.json", {"status": outcome})
    fence.unlink()
    sync_directories(fence.parent)
    return outcome


def check_output(output, previous):
    """Reject unknown prior ZIPs before staging as well as before publication."""
    output = output_path(str(Path(output).absolute()))
    before = digest(output) if output.is_file() else None
    if before is not None and (not previous or previous.get("output") != str(output) or previous.get("output_sha256") != before):
        raise ValueError("refusing to replace an unowned or changed manual result ZIP; preserve it and collect unchanged original jobs/receipts in a fresh export folder")
    return output, before


def publish(server, lock, pointer, temporary_zip, output):
    layout = layout_and_lock(server, lock)
    if layout.path(PENDING).exists():
        raise ValueError("recover the prior manual publication first")
    verify_catalog(layout.root, pointer)
    _, _, previous = current(layout.root)
    output, before = check_output(output, previous)
    home = layout.path(".runtime/manual_degap/transactions/" + uuid.uuid4().hex)
    ensure_directory(home)
    backups = {"pointer": None, "output": None}
    for key, source in (("pointer", layout.path(POINTER)), ("output", output)):
        if source.exists():
            copy_synced(source, home / (key + ".previous"))
            backups[key] = digest(home / (key + ".previous"))
    copy_synced(temporary_zip, home / "output.next")
    next_pointer = {**pointer, "output": str(output), "output_sha256": digest(home / "output.next")}
    plan = {"schema": "cgat.manual-degap-publication", "previous": previous, "next": next_pointer,
            "output": str(output), "previous_output_sha256": before, "backup_sha256": backups}
    durable_json(home / "plan.json", plan)
    durable_json(layout.path(PENDING), {"schema": "cgat.manual-degap-pending", "transaction": home.name,
                                     "plan_sha256": digest(home / "plan.json")})
    try:
        if before != (digest(output) if output.is_file() else None):
            raise ValueError("manual result ZIP changed before publication")
        pointer_file = layout.path(POINTER)
        if (read_object(pointer_file) if pointer_file.exists() or pointer_file.is_symlink() else None) != previous:
            raise ValueError("manual pointer changed before publication")
        copy_synced(home / "output.next", output)
        if (read_object(pointer_file) if pointer_file.exists() or pointer_file.is_symlink() else None) != previous:
            raise ValueError("manual pointer changed during publication")
        durable_json(pointer_file, next_pointer)
    except Exception:
        recover(layout.root, lock, rollback=True)
        raise
    recover(layout.root, lock)
    return next_pointer
