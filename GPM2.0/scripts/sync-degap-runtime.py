#!/usr/bin/env python3
"""Reproducibly vendor the pinned DEGAP submodule; never copy a dirty checkout.

Run from any directory. --check verifies the complete generated snapshot without
writing. Edit DEGAP2.0 upstream, update its gitlink, then regenerate this snapshot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "GPM2.0/server/tools/degap_core"


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd)


def snapshot():
    # The index permits regenerating immediately after staging a new gitlink.
    entry = git("ls-files", "--stage", "DEGAP2.0").decode().split()
    if len(entry) < 3 or entry[0] != "160000" or entry[2] != "0":
        raise ValueError("DEGAP2.0 must be an unconflicted pinned submodule")
    revision = entry[1]
    upstream = ROOT / "DEGAP2.0"
    paths = git("ls-tree", "-r", "--name-only", revision, cwd=upstream).decode().splitlines()
    selected = [p for p in paths if p.startswith("bin/") and p.endswith(".py")]
    selected += [p for p in paths if p in ("README.md", "environment.yml") or
                 ("/" not in p and p.upper().startswith(("LICENSE", "COPYING", "NOTICE")))]
    files = {p: git("show", f"{revision}:{p}", cwd=upstream) for p in selected}
    if "bin/DEGAP.py" not in files:
        raise ValueError("Pinned submodule does not contain bin/DEGAP.py")
    manifest = {"schema": "gpm.degap.runtime.v1", "repository": "https://github.com/Jianwei-Zhang/DEGAP",
                "revision": revision, "files": {p: hashlib.sha256(data).hexdigest() for p, data in sorted(files.items())}}
    files["SOURCE.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = snapshot()
    existing = {p.relative_to(DEST).as_posix(): p for p in DEST.rglob("*") if p.is_file()
                and "__pycache__" not in p.parts}
    differences = sorted(p for p in set(files) | set(existing)
                         if p not in files or p not in existing or existing[p].read_bytes() != files[p])
    if args.check:
        if differences:
            raise SystemExit("DEGAP runtime differs: " + ", ".join(differences))
    else:
        for name in existing.keys() - files.keys():
            existing[name].unlink()
        for name, data in files.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f"DEGAP runtime {'verified' if args.check else 'generated'}: {len(files)} files")


if __name__ == "__main__":
    main()
