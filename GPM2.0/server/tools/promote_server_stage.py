#!/usr/bin/env python3

"""Replace allowlisted server entries from an incremental stage."""

from __future__ import annotations

try:
    from workspace_layout import WorkspaceLayout
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout


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
    "package_light_zip.sh",
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
    source_layout, destination_layout = (WorkspaceLayout.detect(root) for root in (stage_dir, server_dir))
    if source_layout.version != destination_layout.version:
        raise ValueError("incremental stage and workspace use different layouts")
    names = (*BASE_ENTRIES, *optional_entries)
    if source_layout.version == 2:
        # The legacy data root splits into separate physical subtrees; these
        # incrementals write assemblies/derived files, not reference or reads.
        names = tuple(name for name in names if name != "data") + ("data/datasets", "data")
    entries = [(source_layout.path(name), destination_layout.path(name)) for name in names]
    # A staged copy must retain the prepared runtime and entrypoints. Refuse
    # before replacing anything if the input is not a complete stage.
    for name in (".prepare_lib", "run_all.sh"):
        source = source_layout.path(name)
        destination = destination_layout.path(name)
        if destination.exists() and (not source.exists() or source.is_symlink()):
            raise ValueError(f"incremental stage is missing a prepared entry: {name}")
    for path in stage_dir.rglob("*.sh"):
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(str(stage_dir), str(server_dir)),
            encoding="utf-8",
            newline="",
        )

    for source, destination in entries:
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
