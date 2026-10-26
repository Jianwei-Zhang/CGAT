#!/usr/bin/env python3
"""Shared tool binding and explicit skill registration; never search the host."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
DEFAULT_TOOLS = "~/bin/GPM_Server"
REGISTRY = ".gpm-server-skills.json"


def checked(path):
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError(f"Refusing symlinked path: {parent}")
    return path


def validate_tools(root):
    root = checked(root)
    if not root.is_dir():
        raise ValueError("Recorded Server directory is unavailable: " + str(root))
    if not checked(root / "tools/grt_core").is_dir():
        raise ValueError("Incomplete Server tools: missing tools/grt_core")
    for name in ("run.sh", "prepare.sh", "install.sh", "tools/server_run.py"):
        if not checked(root / name).is_file():
            raise ValueError(f"Not a complete companion Server tools directory: {root} (missing {name})")
    return root


def resolve(skill):
    skill = checked(skill)
    text = checked(skill / "server-tools.path").read_text()
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0] or any(c in text for c in "\r\0"):
        raise ValueError("server-tools.path must contain exactly one nonempty LF path line")
    value = Path(lines[0])
    # Resolve the shipped ../.. before validating components, but reject links in
    # the installed skill itself. Absolute user bindings never contain literal ~.
    return validate_tools(Path(os.path.abspath(value if value.is_absolute() else skill / value)))


def atomic(path, data, mode=0o600):
    path = checked(path)
    fd, name = tempfile.mkstemp(prefix=".binding-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def registered(tools):
    file = checked(tools / REGISTRY)
    if not file.exists():
        return []
    entries = json.loads(file.read_text())
    if not isinstance(entries, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in entries):
        raise ValueError("Invalid skill registry; inspect " + str(file))
    return [checked(p) for p in entries]


def matching_provenance(skill, tools):
    """Record a baseline only when every companion skill file really matches."""
    source = checked(tools / "SOURCE.json")
    if not source.exists():
        return None
    info = json.loads(source.read_text())
    prefix = "skills/gpm-server/"
    files = {name[len(prefix):]: record for name, record in info.get("files", {}).items()
             if name.startswith(prefix)}
    if "SKILL.md" not in files:
        return None
    for name, record in files.items():
        if name == "server-tools.path":
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name.startswith("local/"):
            raise ValueError("Invalid skill provenance file path")
        path = checked(skill / name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            return None
    return {"release": info.get("release"), "git_revision": info.get("git_revision"), "files": files}


def bind(skill, tools):
    skill, tools = checked(skill), validate_tools(tools)
    if not checked(skill / "SKILL.md").is_file():
        raise ValueError("Installed skill is missing SKILL.md")
    location = checked(skill / "server-tools.path")
    old = location.read_text() if location.exists() else None
    provenance = checked(skill / "official-source.json")
    old_provenance = provenance.read_text() if provenance.exists() else None
    baseline = matching_provenance(skill, tools) if old_provenance is None else None
    # Registration is explicit; no scan of agent homes or configuration files.
    lock = checked(tools / ".gpm-server-skills.lock")
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        entries = registered(tools)
        entries.append(skill)
        try:
            atomic(location, str(tools) + "\n")
            if baseline is not None:
                atomic(provenance, json.dumps(baseline, indent=2) + "\n", mode=0o644)
            atomic(tools / REGISTRY, json.dumps(sorted({str(p) for p in entries}), indent=2) + "\n")
        except BaseException:
            if baseline is not None:
                provenance.unlink(missing_ok=True)
            if old is None:
                location.unlink(missing_ok=True)
            else:
                atomic(location, old)
            raise
    return tools


def main():
    skill = Path(__file__).absolute().parents[1]
    args = sys.argv[1:]
    try:
        if args in (["--help"], ["-h"]):
            print("Usage: bash server_tools_path.sh [--set /absolute/path/to/Server]")
            print("Validate saved binding; --set also registers this skill for coordinated updates.")
            print("New tools default: " + DEFAULT_TOOLS + "; existing/custom paths are retained.")
        elif not args:
            print(resolve(skill))
        elif len(args) == 2 and args[0] == "--set" and Path(args[1]).is_absolute() and not any(c in args[1] for c in "\r\n\0"):
            print(bind(skill, Path(args[1])))
        else:
            raise ValueError("Use --set with one absolute Server tools path, or no arguments")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}. Ask for the existing tools path; no search or installation was performed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
