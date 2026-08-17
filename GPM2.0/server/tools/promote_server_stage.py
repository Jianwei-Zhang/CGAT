#!/usr/bin/env python3

"""Replace allowlisted server entries from an incremental stage."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


BASE_ENTRIES = (
    "metadata",
    "data",
    "runs",
    "tel",
    "cen",
    ".prepare_lib",
    "assign_chr_groups.sh",
    "run_all.sh",
    "package_full_zip.sh",
    "package_light_no_fasta_zip.sh",
    "export_final_path_fasta.sh",
    "add_dataset.sh",
)
OPTIONAL_ENTRIES = frozenset({"add_ctg.sh"})


def promote(stage_dir: Path, server_dir: Path, optional_entries: list[str]) -> None:
    unexpected = set(optional_entries) - OPTIONAL_ENTRIES
    if unexpected:
        raise ValueError(f"unsupported promotion entries: {sorted(unexpected)}")

    stage_dir = stage_dir.resolve()
    server_dir = server_dir.resolve()
    for path in stage_dir.rglob("*.sh"):
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(str(stage_dir), str(server_dir)),
            encoding="utf-8",
            newline="",
        )

    for name in (*BASE_ENTRIES, *optional_entries):
        source = stage_dir / name
        destination = server_dir / name
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--entry", action="append", default=[])
    args = parser.parse_args()
    try:
        promote(args.stage_dir, args.server_dir, args.entry)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
