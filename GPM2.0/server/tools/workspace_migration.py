"""Content-bound, resumable physical migration primitives.

This module's CLI offers physical inspection. The completed-LGZ runtime adapter
in migrate_workspace.py supplies rewritten scripts/receipts and new runtime
files, then validates the complete destination contract. Moving files alone is NOT a completed migration.
All mutations require the existing workspace lock, including cross-host owners.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Callable
import uuid

try:
    from run_orchestration import sha256_file
    from workspace_layout import (LAYOUT_VERSION, MANIFEST, MIGRATION, LayoutError,
                                  WorkspaceLayout, canonical_relative, relative_path)
except ModuleNotFoundError:
    from .run_orchestration import sha256_file
    from .workspace_layout import (LAYOUT_VERSION, MANIFEST, MIGRATION, LayoutError,
                                   WorkspaceLayout, canonical_relative, relative_path)

SCHEMA = "cgat.workspace-migration"
EXCLUDED = {".run_all/lock"}


def json_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sync_directories(*paths: Path) -> None:
    for path in set(paths):
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def rename_synced(source: Path, target: Path) -> None:
    source.rename(target)
    sync_directories(source.parent, target.parent)


def ensure_directory(path: Path) -> None:
    """New migration storage must not broaden access to formerly private files."""
    missing = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise LayoutError(f"directory is a broken symlink: {cursor}")
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise LayoutError(f"not a regular directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        sync_directories(directory.parent)


def durable_json(path: Path, value: dict) -> None:
    ensure_directory(path.parent)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directories(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def plain_path(root: Path, relative: str) -> Path:
    """Only the final input leaf may be a symlink; never follow parent aliases."""
    return WorkspaceLayout(root, 1).path(relative_path(relative))


def identity(path: Path) -> dict:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(path)
        return {"kind": "symlink", "target": target,
                "sha256": hashlib.sha256(os.fsencode(target)).hexdigest()}
    if not stat.S_ISREG(info.st_mode):
        raise LayoutError(f"migration requires regular files or file symlinks: {path}")
    return {"kind": "file", "size": info.st_size, "mode": stat.S_IMODE(info.st_mode),
            "sha256": sha256_file(path)}


def matches(path: Path, expected: dict) -> bool:
    try:
        return identity(path) == expected
    except FileNotFoundError:
        return False


@dataclass(frozen=True)
class MigrationPlan:
    entries: tuple[dict, ...]
    directories: tuple[str, ...]

    def document(self) -> dict:
        return {"schema": SCHEMA, "from_version": 1, "to_version": LAYOUT_VERSION,
                "entries": list(self.entries), "directories": list(self.directories)}

    @property
    def digest(self) -> str:
        return json_digest(self.document())

    def summary(self) -> dict:
        moves = [entry for entry in self.entries if entry["source"] != entry["destination"]]
        return {"schema": SCHEMA, "from_version": 1, "to_version": LAYOUT_VERSION,
                "plan_sha256": self.digest, "file_count": len(self.entries),
                "move_count": len(moves), "moves": moves,
                "preserved_root_entries": [entry["source"] for entry in self.entries
                    if entry["source"] == entry["destination"] and "/" not in entry["source"]],
                "analysis_started": False, "applied": False,
                "note": "Physical plan only. Runtime, references and checkpoints must be adapted and validated before commit."}


def plan_migration(root: Path) -> MigrationPlan:
    """Read-only snapshot; no locks, directories or migration marker are created."""
    root = root.resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 1:
        raise LayoutError("workspace already uses the numbered layout")
    if not (root / "run_all.sh").is_file() or not (root / ".run_all/plan.tsv").is_file():
        raise LayoutError("not a prepared legacy Server workspace")
    if (root / ".runtime").exists():
        previous_path = root / MIGRATION
        if not previous_path.is_file() or previous_path.is_symlink():
            raise LayoutError("unmarked .runtime directory exists; inspect it before migration")
        previous = json.loads(previous_path.read_text())
        _check_journal(root, previous)
        if previous["state"] != "rolled_back":
            raise LayoutError("previous migration must finish or roll back first")
        # Rolled-back transaction backups/receipts remain for diagnosis. Never
        # silently skip unrelated user data hidden in an unmarked runtime tree.
        for path in (root / ".runtime").rglob("*"):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise LayoutError("symlink in rolled-back migration storage")
            if path.is_file() and rel != MIGRATION and not rel.startswith(".runtime/migrations/"):
                raise LayoutError(f"unexpected runtime file after rollback: {rel}")
    entries, directories = [], []
    destinations = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(dirnames):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if relative in EXCLUDED or relative == ".runtime":
                dirnames.remove(name)
                continue
            if path.is_symlink():
                raise LayoutError(f"directory symlink needs explicit migration handling: {relative}")
            directories.append(relative)
        for name in sorted(filenames):
            path = parent / name
            source = path.relative_to(root).as_posix()
            destination = canonical_relative(source)
            if source == MANIFEST or source == MIGRATION:
                raise LayoutError("legacy workspace has reserved migration files")
            if destination in destinations:
                raise LayoutError(f"migration destination collision: {destination}")
            destinations.add(destination)
            target = plain_path(root, destination)
            if destination != source and (target.exists() or target.is_symlink()):
                raise LayoutError(f"migration destination already exists: {destination}")
            before = identity(path)
            after = dict(before)
            if before["kind"] == "symlink":
                original_target = Path(os.path.abspath(path.parent / before["target"]))
                try:
                    relative_target = original_target.relative_to(root).as_posix()
                except ValueError:
                    new_target = original_target
                else:
                    new_target = root / canonical_relative(relative_target)
                # Rebase both internal and external relative links when moving.
                link = os.path.relpath(new_target, target.parent)
                after = {"kind": "symlink", "target": link,
                         "sha256": hashlib.sha256(os.fsencode(link)).hexdigest()}
            entries.append({"source": source, "destination": destination,
                            "before": before, "after": after})
    return MigrationPlan(tuple(sorted(entries, key=lambda x: x["source"])), tuple(sorted(directories)))


def inventory_document(journal: dict) -> dict:
    payload = {"entries": journal["entries"], "directories": journal["directories"]}
    for name in ("additions", "adapter_metadata"):
        if name in journal:
            payload[name] = journal[name]
    return payload


def validate_addition_path(root: Path, destination: str) -> Path:
    if not isinstance(destination, str):
        raise LayoutError("migration addition destination must be a relative path")
    relative_path(destination)
    if (canonical_relative(destination) != destination or destination in {MANIFEST, MIGRATION, ".runtime"}
            or destination == ".runtime/migrations" or destination.startswith(".runtime/migrations/")
            or destination == ".runtime/run_all/lock" or destination.startswith(".runtime/run_all/lock/")):
        raise LayoutError("migration addition overlaps reserved or legacy state: " + destination)
    return plain_path(root, destination)


def _check_journal(root: Path, journal: dict) -> None:
    if (not isinstance(journal, dict) or not isinstance(journal.get("entries"), list)
            or not isinstance(journal.get("directories"), list)):
        raise LayoutError("invalid migration journal shape")
    for directory in journal["directories"]:
        relative_path(directory)
    if (journal.get("schema") != SCHEMA or journal.get("from_version") != 1
            or journal.get("to_version") != LAYOUT_VERSION
            or journal.get("workspace") != str(root)
            or not isinstance(journal.get("adapter"), str) or not journal["adapter"]
            or not isinstance(journal.get("id"), str)
            or len(journal["id"]) != 32
            or any(c not in "0123456789abcdef" for c in journal["id"])):
        raise LayoutError("invalid migration journal identity")
    if journal.get("state") not in {"prepared", "moving", "validating", "committed", "rolling_back", "rolled_back"}:
        raise LayoutError("invalid migration state")
    if journal.get("inventory_sha256") != json_digest(inventory_document(journal)):
        raise LayoutError("migration journal entries changed")
    sources, targets = set(), set()
    for entry in journal["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"source", "destination", "before", "after"}
                or not isinstance(entry["before"], dict) or not isinstance(entry["after"], dict)):
            raise LayoutError("invalid migration entry")
        source, target = relative_path(entry["source"]), relative_path(entry["destination"])
        if canonical_relative(source) != target or source in sources or target in targets:
            raise LayoutError("invalid or duplicate migration path mapping")
        if source.startswith(".runtime/") or source in {".runtime", MANIFEST, MIGRATION}:
            raise LayoutError("migration source overlaps journal")
        sources.add(source)
        targets.add(target)
        plain_path(root, source)
        plain_path(root, target)
        if set(entry) != {"source", "destination", "before", "after"}:
            raise LayoutError("invalid migration entry")
        for value in (entry["before"], entry["after"]):
            if value.get("kind") not in {"file", "symlink"}:
                raise LayoutError("invalid migration file type")
            digest = value.get("sha256", "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise LayoutError("invalid migration file digest")
            if value["kind"] == "file":
                if (type(value.get("size")) is not int or value["size"] < 0
                        or type(value.get("mode")) is not int or not 0 <= value["mode"] <= 0o7777):
                    raise LayoutError("invalid migration file metadata")
            elif not isinstance(value.get("target"), str) or "\0" in value["target"]:
                raise LayoutError("invalid migration symlink")
        if entry["before"]["kind"] != entry["after"]["kind"]:
            raise LayoutError("migration cannot change artifact type")
    additions = journal.get("additions", [])
    if not isinstance(additions, list) or ("adapter_metadata" in journal and not isinstance(journal["adapter_metadata"], dict)):
        raise LayoutError("invalid migration adapter/addition record")
    for addition in additions:
        if not isinstance(addition, dict) or set(addition) != {"destination", "after"}:
            raise LayoutError("invalid migration addition")
        destination, after = addition["destination"], addition["after"]
        validate_addition_path(root, destination)
        if destination in targets:
            raise LayoutError("duplicate migration addition destination")
        targets.add(destination)
        if (not isinstance(after, dict) or set(after) != {"kind", "size", "mode", "sha256"}
                or after["kind"] != "file" or type(after["size"]) is not int or after["size"] < 0
                or type(after["mode"]) is not int or not 0 <= after["mode"] <= 0o777
                or not isinstance(after["sha256"], str) or len(after["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in after["sha256"])):
            raise LayoutError("invalid migration addition file metadata")
    for destination in targets:
        if any(parent.as_posix() in targets for parent in Path(destination).parents if str(parent) != "."):
            raise LayoutError("migration file destinations overlap as parent/child")


class MigrationTransaction:
    """Internal migration adapter API; caller must hold and retain WorkspaceLock.

    No generic CLI can call commit: a format-aware validator is mandatory. The
    adapters that regenerate scripts, translate references and preserve valid
    checkpoints are integrated separately, never guessed by string replacement.
    """
    def __init__(self, root: Path, lock, journal: dict):
        self.root = root.resolve()
        self.lock = lock
        self.journal = journal
        self._require_lock()
        _check_journal(self.root, journal)
        self.private = self.root / ".runtime/migrations" / journal["id"]

    def _require_lock(self) -> None:
        if (not self.lock.acquired or not self.lock.for_migration
                or self.lock.server_dir.resolve() != self.root
                or self.lock.state_dir != self.root / ".run_all"
                or self.lock._existing_owner() != self.lock.owner):
            raise LayoutError("migration requires the held legacy workspace lock")

    def save(self, state: str) -> None:
        self._require_lock()
        self.journal["state"] = state
        private = plain_path(self.root, f".runtime/migrations/{self.journal['id']}/journal.json")
        durable_json(private, self.journal)
        durable_json(plain_path(self.root, MIGRATION), self.journal)

    @classmethod
    def begin(cls, root: Path, lock, plan: MigrationPlan, *, adapter: str,
              rewrites: dict[str, bytes], additions: dict[str, tuple[bytes, int]] | None = None,
              adapter_metadata: dict | None = None) -> "MigrationTransaction":
        root = root.resolve()
        if not adapter:
            raise LayoutError("migration needs a versioned runtime adapter")
        if WorkspaceLayout.detect(root).version != 1:
            raise LayoutError("workspace is already migrated")
        # Recompute inventory after taking the lock; approval of an old preview
        # never authorizes migration of different files.
        actual = plan_migration(root)
        if actual.digest != plan.digest:
            raise LayoutError("workspace changed after migration preview")
        known = {entry["source"]: entry for entry in actual.entries}
        if set(rewrites) - known.keys():
            raise LayoutError("rewrite references an unknown source file")
        entries = json.loads(json.dumps(list(actual.entries)))
        for entry in entries:
            if entry["source"] in rewrites:
                if entry["before"]["kind"] != "file":
                    raise LayoutError("cannot rewrite a symlink as text")
                content = rewrites[entry["source"]]
                if not isinstance(content, bytes):
                    raise LayoutError("migration rewrite must be bytes")
                entry["after"] = {**entry["before"], "size": len(content),
                                  "sha256": hashlib.sha256(content).hexdigest()}
        journal = {"schema": SCHEMA, "from_version": 1, "to_version": LAYOUT_VERSION,
                   "id": uuid.uuid4().hex, "workspace": str(root), "adapter": adapter,
                   "state": "prepared", "plan_sha256": plan.digest, "entries": entries,
                   "directories": list(plan.directories),
                   "inventory_sha256": json_digest({"entries": entries, "directories": list(plan.directories)})}
        generated = []
        for destination, (content, mode) in sorted((additions or {}).items()):
            path = validate_addition_path(root, destination)
            if destination in {entry["destination"] for entry in entries} or path.exists() or path.is_symlink():
                raise LayoutError("migration addition destination is occupied: " + destination)
            if not isinstance(content, bytes) or type(mode) is not int or not 0 <= mode <= 0o777:
                raise LayoutError("migration addition requires bytes and a regular file mode")
            generated.append({"destination": destination, "after": {"kind": "file", "mode": mode,
                              "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}})
        if generated:
            journal["additions"] = generated
        if adapter_metadata is not None:
            if not isinstance(adapter_metadata, dict):
                raise LayoutError("migration adapter metadata must be an object")
            journal["adapter_metadata"] = json.loads(json.dumps(adapter_metadata))
        journal["inventory_sha256"] = json_digest(inventory_document(journal))
        transaction = cls(root, lock, journal)
        # Publish intent first. Incomplete staging blocks normal execution and
        # can still be explicitly rolled back without deleting original files.
        transaction.save("prepared")
        for entry in entries:
            if entry["source"] in rewrites and entry["before"] != entry["after"]:
                path = plain_path(root, f".runtime/migrations/{journal['id']}/rewrites/{entry['source']}")
                ensure_directory(path.parent)
                with path.open("xb") as stream:
                    stream.write(rewrites[entry["source"]])
                    stream.flush()
                    os.fsync(stream.fileno())
                path.chmod(entry["after"]["mode"])
        for addition in generated:
            path = plain_path(root, f".runtime/migrations/{journal['id']}/additions/{addition['destination']}")
            ensure_directory(path.parent)
            with path.open("xb") as stream:
                stream.write(additions[addition["destination"]][0])
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(addition["after"]["mode"])
        return transaction

    @classmethod
    def resume(cls, root: Path, lock, *, adapter: str) -> "MigrationTransaction":
        path = plain_path(root.resolve(), MIGRATION)
        if path.is_symlink():
            raise LayoutError("migration journal must not be a symlink")
        if not path.exists():
            # A crash between private intent persistence and publishing the
            # active marker has not moved data. Recover that intent for rollback.
            candidates = []
            store = plain_path(root.resolve(), ".runtime/migrations")
            for candidate in store.glob("*/journal.json"):
                checked = plain_path(root.resolve(), candidate.relative_to(root.resolve()).as_posix())
                if checked.is_symlink():
                    raise LayoutError("private migration journal must not be a symlink")
                value = json.loads(checked.read_text())
                if isinstance(value, dict) and value.get("state") not in {"committed", "rolled_back"}:
                    candidates.append(checked)
            if len(candidates) != 1:
                raise LayoutError("cannot identify one recoverable migration intent")
            path = candidates[0]
        journal = json.loads(path.read_text())
        if not isinstance(journal, dict) or journal.get("adapter") != adapter:
            raise LayoutError("resume needs the same migration adapter")
        return cls(root, lock, journal)

    def _install(self, entry: dict) -> None:
        source = plain_path(self.root, entry["source"])
        target = plain_path(self.root, entry["destination"])
        before, after = entry["before"], entry["after"]
        backup = plain_path(self.root, f".runtime/migrations/{self.journal['id']}/originals/{entry['source']}")
        changed = before != after
        if source == target and not changed:
            if not matches(source, before):
                raise LayoutError(f"unmoved file changed: {entry['source']}")
            return
        if matches(target, after) and (changed and matches(backup, before) or not changed and not (source.exists() or source.is_symlink())):
            return  # Previous process completed this atomic operation.
        if target != source and (target.exists() or target.is_symlink()):
            raise LayoutError(f"migration target changed or occupied: {entry['destination']}")
        ensure_directory(target.parent)
        if not changed:
            if not matches(source, before):
                raise LayoutError(f"migration input changed: {entry['source']}")
            rename_synced(source, target)
            return
        if not backup.exists() and not backup.is_symlink():
            if not matches(source, before):
                raise LayoutError(f"migration rewrite input changed: {entry['source']}")
            ensure_directory(backup.parent)
            rename_synced(source, backup)
        elif not matches(backup, before):
            raise LayoutError("migration backup changed")
        if source.exists() or source.is_symlink():
            raise LayoutError("migration source reappeared after backup")
        if after["kind"] == "symlink":
            target.symlink_to(after["target"])
            sync_directories(target.parent)
        else:
            staged = plain_path(self.root, f".runtime/migrations/{self.journal['id']}/rewrites/{entry['source']}")
            if not matches(staged, after):
                raise LayoutError("migration rewrite staging is incomplete or changed")
            temporary = target.with_name(target.name + ".migration-" + self.journal["id"])
            if temporary.exists() or temporary.is_symlink():
                if not matches(temporary, after):
                    raise LayoutError("migration temporary file changed")
                rename_synced(temporary, target)
            else:
                # Staging is already durable and on this same filesystem.
                # Consume it with one rename: no partially copied live file.
                rename_synced(staged, target)

    def _install_addition(self, addition: dict) -> None:
        target = validate_addition_path(self.root, addition["destination"])
        expected = addition["after"]
        if matches(target, expected):
            return
        if target.exists() or target.is_symlink():
            raise LayoutError("migration addition destination changed or occupied: " + addition["destination"])
        staged = plain_path(self.root, f".runtime/migrations/{self.journal['id']}/additions/{addition['destination']}")
        if not matches(staged, expected):
            raise LayoutError("migration addition staging is incomplete or changed")
        ensure_directory(target.parent)
        temporary = target.with_name(target.name + ".migration-" + self.journal["id"])
        if temporary.exists() or temporary.is_symlink():
            if not matches(temporary, expected):
                raise LayoutError("migration addition temporary file changed")
            rename_synced(temporary, target)
        else:
            rename_synced(staged, target)

    def apply(self, validate: Callable[[WorkspaceLayout], dict]) -> dict:
        self._require_lock()
        if self.journal["state"] in {"rolling_back", "rolled_back", "committed"}:
            raise LayoutError("transaction is not available for forward migration")
        self.save("moving")
        for entry in self.journal["entries"]:
            self._install(entry)
        for addition in self.journal.get("additions", []):
            self._install_addition(addition)
        self.save("validating")
        layout = WorkspaceLayout(self.root, LAYOUT_VERSION)
        proof = validate(layout)
        if not isinstance(proof, dict) or proof.get("adapter") != self.journal["adapter"]:
            raise LayoutError("runtime adapter did not provide a validation receipt")
        # A concurrent writer/new output must not be lost in an inventory that
        # only checks files known before the migration.
        expected = {entry["destination"] for entry in self.journal["entries"]}
        expected.update(addition["destination"] for addition in self.journal.get("additions", []))
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            parent = Path(directory)
            for name in list(dirs):
                rel = (parent / name).relative_to(self.root).as_posix()
                if rel in EXCLUDED or rel == ".runtime/migrations":
                    dirs.remove(name)
                elif (parent / name).is_symlink():
                    raise LayoutError(f"unexpected directory symlink after migration: {rel}")
            for name in files:
                rel = (parent / name).relative_to(self.root).as_posix()
                if rel not in expected and rel not in {MIGRATION, MANIFEST}:
                    raise LayoutError(f"unexpected file after migration: {rel}")
        # No callback can silently edit migrated artifacts after verification.
        for entry in self.journal["entries"]:
            if not matches(plain_path(self.root, entry["destination"]), entry["after"]):
                raise LayoutError(f"migrated artifact changed during validation: {entry['destination']}")
        for addition in self.journal.get("additions", []):
            if not matches(plain_path(self.root, addition["destination"]), addition["after"]):
                raise LayoutError("migration addition changed during validation: " + addition["destination"])
        manifest = plain_path(self.root, MANIFEST)
        if manifest.exists() or manifest.is_symlink():
            if manifest.is_symlink() or json.loads(manifest.read_text()).get("migration_id") != self.journal["id"]:
                raise LayoutError("migration found an unrelated layout manifest")
        durable_json(plain_path(self.root, f".runtime/migrations/{self.journal['id']}/validation.json"), proof)
        durable_json(manifest, {**layout.manifest(), "migration_id": self.journal["id"], "migration_adapter": self.journal["adapter"]})
        self.save("committed")
        self.prune_empty_legacy_directories()
        return proof

    def rollback(self) -> None:
        self._require_lock()
        if self.journal["state"] == "committed":
            raise LayoutError("committed migration requires a separate validated reverse migration")
        self.save("rolling_back")
        for addition in reversed(self.journal.get("additions", [])):
            target = validate_addition_path(self.root, addition["destination"])
            temporary = target.with_name(target.name + ".migration-" + self.journal["id"])
            for path in (target, temporary):
                if path.exists() or path.is_symlink():
                    if not matches(path, addition["after"]):
                        raise LayoutError("rollback refuses to delete changed migration addition: " + str(path))
                    path.unlink()
                    sync_directories(path.parent)
        for entry in reversed(self.journal["entries"]):
            source = plain_path(self.root, entry["source"])
            target = plain_path(self.root, entry["destination"])
            backup = plain_path(self.root, f".runtime/migrations/{self.journal['id']}/originals/{entry['source']}")
            before, after = entry["before"], entry["after"]
            if matches(source, before) and not (backup.exists() or backup.is_symlink()):
                if source != target and (target.exists() or target.is_symlink()):
                    raise LayoutError("rollback refuses to remove an unexpected target")
                continue
            if source != target and (source.exists() or source.is_symlink()):
                raise LayoutError("rollback source path is occupied")
            ensure_directory(source.parent)
            if before != after:
                if not matches(backup, before):
                    raise LayoutError("rollback backup missing or changed")
                if target.exists() or target.is_symlink():
                    if not matches(target, after):
                        raise LayoutError("rollback refuses to overwrite changed data")
                    target.unlink()
                rename_synced(backup, source)
            else:
                if not matches(target, after):
                    raise LayoutError("rollback target missing or changed")
                rename_synced(target, source)
        manifest = self.root / MANIFEST
        if manifest.exists():
            value = json.loads(manifest.read_text())
            if value.get("migration_id") != self.journal["id"]:
                raise LayoutError("rollback found an unrelated layout manifest")
            manifest.unlink()
            sync_directories(manifest.parent)
        self.save("rolled_back")

    def prune_empty_legacy_directories(self) -> None:
        for relative in sorted(self.journal["directories"], key=lambda s: s.count("/"), reverse=True):
            path = plain_path(self.root, relative)
            if path.is_dir():
                try:
                    path.rmdir()  # Never delete a non-empty or unknown directory.
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the numbered-layout migration without changing the workspace")
    parser.add_argument("--server-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(plan_migration(args.server_dir).summary(), indent=2, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: migration inspection failed: {exc}\n")


if __name__ == "__main__":
    main()
