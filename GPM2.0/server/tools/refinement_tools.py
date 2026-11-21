"""Locked refinement runtimes in the existing cgat-server environment.

Installation is explicit. Pipeline resolution is read-only and never downloads,
installs, substitutes another PATH tool, or accepts a different conda build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request

LOCK_PATH = Path(__file__).resolve().parents[1] / "contracts/refinement-tools.lock.json"
TOOLS = ("degap", "tgsgapcloser", "quartet", "lrgapcloser")
RECEIPT = "conda-meta/cgat-refinement-runtime.json"
WRAPPER = b"""#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "source"))
from quartet.main import main
main()
"""


class ToolError(ValueError):
    pass


def digest(path):
    # Stable-content memo is process-local, never a persistent stat-only cache.
    # Shared orchestration avoids re-reading the same packages for each tool.
    try:
        from run_orchestration import sha256_file
    except ModuleNotFoundError:
        from .run_orchestration import sha256_file
    return sha256_file(Path(path))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def current_platform():
    machine = platform.machine().lower()
    if platform.system() != "Linux" or machine not in {"x86_64", "amd64", "aarch64", "arm64"}:
        raise ToolError("refinement runtime supports Linux x86_64 and aarch64 only")
    return "linux-64" if machine in {"x86_64", "amd64"} else "linux-aarch64"


def load_lock(path=LOCK_PATH):
    lock = json.loads(Path(path).read_text())
    if (lock.get("schema") != "cgat.refinement-tool-lock" or lock.get("schema_version") != 1
            or set(lock.get("tools", {})) != set(TOOLS)):
        raise ToolError("unsupported refinement tool lock")
    return lock


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ToolError("unsafe runtime artifact path")
    value = PurePosixPath(relative)
    if (value.is_absolute() or ".." in value.parts
            or "\\" in relative or value.as_posix() != relative):
        raise ToolError("unsafe runtime artifact path")
    result = Path(root) / relative
    if not result.resolve().is_relative_to(Path(root).resolve()):
        raise ToolError("runtime artifact resolves outside its installation")
    return result


def package_pin(definition, architecture):
    entries = definition.get("packages", {})
    return entries.get(architecture, entries.get("noarch"))


def package_receipt(prefix, name, definition, architecture):
    pin = package_pin(definition, architecture)
    records = []
    for path in (prefix / "conda-meta").glob(name + "-*.json"):
        record = json.loads(path.read_text())
        if record.get("name") == name:
            records.append(record)
    if len(records) != 1:
        raise ToolError(f"expected exactly one installed conda package: {name}")
    record = records[0]
    expected_version = pin["version"] if pin else definition["version"]
    if record.get("version") != expected_version:
        raise ToolError(f"{name} differs from pinned version {expected_version}; rerun install.sh")
    if pin and (record.get("build") != pin["build"] or record.get("sha256") != pin["sha256"]):
        raise ToolError(f"{name} conda build/archive differs from the tool lock; rerun install.sh")
    paths = record.get("paths_data", {}).get("paths")
    if not isinstance(paths, list) or not paths:
        raise ToolError(f"{name} lacks installed-content metadata; reinstall the managed environment")
    hashes = {}
    for row in paths:
        if row.get("path_type") == "directory":
            continue
        relative = row.get("_path")
        path = safe_path(prefix, relative)
        actual = digest(path)
        expected = row.get("sha256_in_prefix") or row.get("sha256")
        if expected and actual != expected:
            raise ToolError(f"installed {name} content changed: {relative}")
        if not expected and row.get("path_type") != "softlink":
            raise ToolError(f"installed {name} artifact has no content identity: {relative}")
        hashes[relative] = actual
    return {"name": name, "version": record["version"], "build": record["build"],
            "archive_sha256": record.get("sha256"), "license": record.get("license", "NOASSERTION"), "files_sha256": hashes}


def source_location(prefix, definition):
    return safe_path(prefix, "share/cgat-refinement/quartet/" + definition["revision"])


def source_receipt(prefix, definition):
    root = source_location(prefix, definition)
    manifest = json.loads((root / "SOURCE.json").read_text())
    if (manifest.get("schema") != "cgat.refinement-installed-source" or manifest.get("schema_version") != 1
            or manifest.get("revision") != definition["revision"]
            or manifest.get("archive_sha256") != definition["archive"]["sha256"]
            or manifest.get("patches", []) != definition.get("patches", [])):
        raise ToolError("installed quarTeT source does not match the lock")
    expected = manifest.get("files_sha256", {})
    paths = [path for path in (root / "source").rglob("*") if path.is_file() or path.is_symlink()]
    actual = {}
    for path in paths:
        if path.is_symlink():
            raise ToolError("quarTeT source must not contain symlinks")
        actual[path.relative_to(root / "source").as_posix()] = digest(path)
    if not expected or actual != expected:
        raise ToolError("installed quarTeT source content changed")
    if (root / "quartet_runner.py").read_bytes() != WRAPPER:
        raise ToolError("quarTeT entrypoint changed")
    return {"version": definition["version"], "revision": definition["revision"],
            "archive_sha256": definition["archive"]["sha256"], "files_sha256": actual,
            "entrypoint_sha256": hashlib.sha256(WRAPPER).hexdigest(), "patches": definition.get("patches", []),
            "license": definition.get("license", {"spdx": "NOASSERTION"})}


def bundled_receipt(definition):
    root = Path(__file__).resolve().parent / "degap_core"
    path = root / "SOURCE.json"
    if digest(path) != definition["manifest_sha256"]:
        raise ToolError("bundled DEGAP source manifest differs from the lock")
    manifest = json.loads(path.read_text())
    if manifest.get("revision") != definition["revision"]:
        raise ToolError("bundled DEGAP revision differs from the lock")
    for relative, expected in manifest["files"].items():
        if digest(safe_path(root, relative)) != expected:
            raise ToolError(f"bundled DEGAP source changed: {relative}")
    python_files = {p.relative_to(root).as_posix() for p in root.rglob("*.py")}
    if python_files != {name for name in manifest["files"] if name.endswith(".py")}:
        raise ToolError("bundled DEGAP contains unpinned Python sources")
    return {"version": definition["version"], "revision": definition["revision"], "manifest_sha256": digest(path), "license": definition.get("license", {"spdx": "NOASSERTION"})}


def collect_receipt(prefix, lock):
    architecture = current_platform()
    tools = {}
    for name in TOOLS:
        definition = lock["tools"][name]
        if definition["distribution"] == "bundled":
            tools[name] = bundled_receipt(definition)
        elif definition["distribution"] == "source":
            tools[name] = source_receipt(prefix, definition)
        else:
            pin = package_pin(definition, architecture)
            if pin is None:
                raise ToolError(f"no locked {name} package for {architecture}")
            tools[name] = package_receipt(prefix, pin["name"], definition, architecture)
    dependencies = {name: package_receipt(prefix, name, definition, architecture)
                    for name, definition in lock["dependencies"].items()}
    return {"schema": "cgat.refinement-runtime", "schema_version": 1,
            "platform": architecture, "lock_sha256": fingerprint(lock), "tools": tools, "dependencies": dependencies}


def validate_runtime(prefix=None, lock=None):
    prefix = Path(prefix or sys.prefix).resolve()
    lock = lock or load_lock()
    receipt_path = prefix / RECEIPT
    if not receipt_path.is_file():
        raise ToolError("refinement runtime is not installed in the active environment; run install.sh and activate cgat-server")
    saved = json.loads(receipt_path.read_text())
    actual = collect_receipt(prefix, lock)
    if saved != actual:
        raise ToolError("refinement runtime receipt is stale or its content changed; rerun install.sh")
    return actual


def install_source(prefix, definition, archive=None):
    destination = source_location(prefix, definition)
    if destination.exists():
        source_receipt(prefix, definition)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temporary:
        temporary = Path(temporary)
        downloaded = temporary / "source.tar.gz"
        if archive:
            shutil.copyfile(archive, downloaded)
        else:
            with urllib.request.urlopen(definition["archive"]["url"], timeout=120) as response, downloaded.open("xb") as output:
                shutil.copyfileobj(response, output)
        if digest(downloaded) != definition["archive"]["sha256"]:
            raise ToolError("quarTeT archive checksum differs from the pinned source")
        stage = temporary / "runtime"
        source = stage / "source"
        source.mkdir(parents=True)
        with tarfile.open(downloaded) as tar:
            members = tar.getmembers()
            top = {PurePosixPath(member.name).parts[0] for member in members if member.name}
            if len(top) != 1:
                raise ToolError("source archive must contain one root directory")
            for member in members:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ToolError("source archive links/devices are not allowed")
                relative = PurePosixPath(member.name).relative_to(next(iter(top))).as_posix()
                target = safe_path(source, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as input_stream, target.open("xb") as output:
                    shutil.copyfileobj(input_stream, output)
        for patch in definition.get("patches", []):
            target = safe_path(source, patch["file"])
            if digest(target) != patch["before_sha256"]:
                raise ToolError("quarTeT compatibility patch source differs from its pin")
            text = target.read_text()
            if text.count(patch["old"]) != 1:
                raise ToolError("quarTeT compatibility patch does not match exactly once")
            target.write_text(text.replace(patch["old"], patch["new"]))
            if digest(target) != patch["after_sha256"]:
                raise ToolError("quarTeT compatibility patch output differs from its pin")
        manifest = {"schema": "cgat.refinement-installed-source", "schema_version": 1,
                    "revision": definition["revision"], "archive_sha256": definition["archive"]["sha256"],
                    "patches": definition.get("patches", []),
                    "files_sha256": {path.relative_to(source).as_posix(): digest(path) for path in sorted(source.rglob("*")) if path.is_file()}}
        (stage / "SOURCE.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        (stage / "quartet_runner.py").write_bytes(WRAPPER)
        # Never overwrite a different or concurrently created installation.
        if destination.exists():
            raise ToolError("quarTeT installation appeared concurrently; rerun verification")
        os.rename(stage, destination)
    source_receipt(prefix, definition)


def install_runtime(prefix=None, lock=None, archive=None):
    prefix = Path(prefix or sys.prefix).resolve()
    lock = lock or load_lock()
    if not (prefix / "conda-meta").is_dir():
        raise ToolError("refinement tools must be installed inside the shared conda environment")
    install_source(prefix, lock["tools"]["quartet"], archive)
    receipt = collect_receipt(prefix, lock)
    target = prefix / RECEIPT
    fd, temporary = tempfile.mkstemp(prefix=".refinement-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--quartet-archive", type=Path, help="installer-only offline copy; checksum still required")
    args = parser.parse_args()
    try:
        if args.quartet_archive and not args.install:
            raise ToolError("--quartet-archive requires --install")
        receipt = install_runtime(archive=args.quartet_archive) if args.install else validate_runtime()
        print(json.dumps({"status": "installed" if args.install else "verified", "platform": receipt["platform"],
                          "tools": {name: row["version"] for name, row in receipt["tools"].items()},
                          "runtime_sha256": fingerprint(receipt)}, sort_keys=True))
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(2, f"ERROR: refinement environment: {error}\n")


if __name__ == "__main__":
    main()
