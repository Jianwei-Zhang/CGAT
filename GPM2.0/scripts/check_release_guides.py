#!/usr/bin/env python3
"""Fail when the project guides disagree on the current Server release version.

The GitHub landing page, the toolkit overview and the two Server install guides all
advertise the same `GPM_Server_<version>_source.tar.gz` archive together with its
mirror and GitHub download paths, and the root READMEs carry a release badge. Those
copies drift independently, so one guide can keep pointing users at an older Server
after a release. Quality and the release workflow run this check instead.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every guide that advertises the downloadable Server source archive.
GUIDES = (
    "README.md",
    "README_zh.md",
    "GPM2.0/README.md",
    "GPM2.0/README_zh.md",
    "GPM2.0/server/README.md",
    "GPM2.0/server/README_zh.md",
)

# Guides that must also show the release badge on the project landing page.
BADGED_GUIDES = ("README.md", "README_zh.md")

REFERENCES = (
    ("Server archive", re.compile(r"GPM_Server_(\d+\.\d+\.\d+)_source\.tar\.gz")),
    ("mirror download path", re.compile(r"/cgat/downloads/v(\d+\.\d+\.\d+)/")),
    ("GitHub download path", re.compile(r"/releases/download/v(\d+\.\d+\.\d+)/")),
    ("GitHub release link", re.compile(r"/releases/tag/v(\d+\.\d+\.\d+)(?![\d.])")),
)

BADGE = re.compile(r"badge/Releases-v(\d+\.\d+\.\d+)-")

VERSION = re.compile(r"\d+\.\d+\.\d+")


def normalize_version(value: str) -> str:
    candidate = value.strip()
    if candidate[:1] in ("v", "V"):
        candidate = candidate[1:]
    if not VERSION.fullmatch(candidate):
        raise ValueError(f"expected a version like v1.2.3, got: {value}")
    return candidate


def guide_references(path: Path) -> dict[str, set[str]]:
    """Return the versions each reference kind uses inside one guide."""
    text = path.read_text(encoding="utf-8")
    found: dict[str, set[str]] = {}
    for label, pattern in REFERENCES:
        versions = set(pattern.findall(text))
        if versions:
            found[label] = versions
    return found


def collect(root: Path = REPO_ROOT) -> tuple[str, list[str]]:
    """Return the single agreed Server version plus a human-readable report."""
    report: list[str] = []
    versions: dict[str, set[str]] = {}
    for relative in GUIDES:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"{relative}: release guide is missing")
        references = guide_references(path)
        if "Server archive" not in references:
            raise ValueError(
                f"{relative}: no GPM_Server_<version>_source.tar.gz reference found"
            )
        for label, found in references.items():
            if len(found) > 1:
                raise ValueError(
                    f"{relative}: conflicting {label} versions: {sorted(found)}"
                )
            version = next(iter(found))
            versions.setdefault(version, set()).add(relative)
            report.append(f"{relative}: {label} -> {version}")

    if len(versions) != 1:
        details = "; ".join(
            f"v{version} in {', '.join(sorted(files))}"
            for version, files in sorted(versions.items())
        )
        raise ValueError(f"guides disagree on the Server version: {details}")
    version = next(iter(versions))

    for relative in BADGED_GUIDES:
        badge = BADGE.search((root / relative).read_text(encoding="utf-8"))
        if badge is None:
            raise ValueError(f"{relative}: release badge is missing")
        if badge.group(1) != version:
            raise ValueError(
                f"{relative}: release badge shows v{badge.group(1)}, guides use v{version}"
            )
        report.append(f"{relative}: release badge -> {badge.group(1)}")

    return version, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="also require the guides to match this release version (for example v1.2.3)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to inspect (defaults to the checkout containing this script)",
    )
    args = parser.parse_args(argv)

    try:
        expected = normalize_version(args.version) if args.version else None
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        version, report = collect(args.root)
    except ValueError as error:
        print(f"Release guide check failed: {error}", file=sys.stderr)
        return 1

    if expected is not None and version != expected:
        print(
            f"Release guide check failed: guides advertise v{version}, "
            f"but this release is v{expected}",
            file=sys.stderr,
        )
        for line in report:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"Release guide check passed (all guides advertise v{version}).")
    if expected is None:
        for line in report:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
