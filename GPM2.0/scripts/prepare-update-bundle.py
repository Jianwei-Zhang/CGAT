#!/usr/bin/env python3
"""Assemble the self-contained updater artifact for docs staging."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_name(value: str) -> str:
    assert re.fullmatch(r"[A-Za-z0-9._-]+", value) and value not in (".", ".."), value
    return value


def prepare(assets: Path, feed: Path, output: Path) -> dict:
    manifest_path = feed / "latest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources: dict[str, Path] = {}
    for package in manifest["platforms"].values():
        name = safe_name(package["url"].rsplit("/", 1)[-1])
        sources[name] = assets / name
    for note in manifest["release_notes"].values():
        name = safe_name(note["url"].rsplit("/", 1)[-1])
        sources[name] = feed / name
    entries = [*manifest["platforms"].values(), *manifest["release_notes"].values()]
    assert len(sources) == 6 == len(entries), "Expected four packages and two localized notes"
    for info, name in zip(entries, sources, strict=True):
        source = sources[name]
        assert source.is_file(), f"Missing updater staging input: {source}"
        assert source.stat().st_size == info["size"], f"Size mismatch: {name}"
        assert digest(source) == info["sha256"], f"SHA-256 mismatch: {name}"
    output.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        target = output / name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        assert digest(target) == digest(source)
    latest_raw = manifest_path.read_bytes()
    target = output / "latest.json"
    if not target.exists() or target.read_bytes() != latest_raw:
        target.write_bytes(latest_raw)
    assert target.read_bytes() == latest_raw
    files = sorted(path.name for path in output.iterdir() if path.is_file())
    assert files == sorted([*sources, "latest.json"]), "Unexpected updater artifact contents"
    return {"version": manifest["version"], "files": files,
            "bytes": sum((output / name).stat().st_size for name in files)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--feed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.assets, args.feed, args.output), indent=2))
