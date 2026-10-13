#!/usr/bin/env python3
"""Stage official skill files with user-local state; never replace an installation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import sys

OFFICIAL = (".gitignore", "SKILL.md", "agents", "references", "scripts")


def checked_path(value: Path) -> Path:
    """Reject symlinked paths, including parents, before canonicalizing."""
    path = value.absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlinked path is not supported: {component}")
    return path.resolve()


def inventory(root: Path, *, official: bool = False) -> list[Path]:
    """List only regular files/directories, without following symlinks."""
    result = []

    def visit(path: Path) -> None:
        mode = path.lstat().st_mode
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"Non-regular or symlinked content is not supported: {path}")
        result.append(path)
        if stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()):
                if official and (child.name == "__pycache__" or child.suffix == ".pyc"):
                    continue
                visit(child)

    visit(root)
    return result


def preserved_binding(installed: Path) -> bytes:
    path = installed / "server-tools.path"
    inventory(path)
    if not path.is_file():
        raise ValueError("server-tools.path must be a regular file")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) != 1 or not lines[0] or "\r" in text or "\0" in text:
        raise ValueError("server-tools.path must contain one nonempty LF path line")
    recorded = Path(lines[0])
    if recorded.is_absolute():
        return raw
    # Anchor a relative binding to the OLD installation, not the new bundle.
    # Never execute the old installation's helper to discover it.
    return (str((installed / recorded).resolve()) + "\n").encode("utf-8")


def copy_entries(entries: list[Path], root: Path, output: Path) -> None:
    for source in entries:
        dest = output / source.relative_to(root)
        # Recheck type before copying; callers must keep both inputs quiescent.
        mode = source.lstat().st_mode
        if stat.S_ISDIR(mode):
            dest.mkdir(mode=0o700, exist_ok=True)
        elif stat.S_ISREG(mode):
            shutil.copy2(source, dest)
        else:
            raise ValueError(f"Content changed to an unsupported type: {source}")


def stage(source: Path, installed: Path, output: Path) -> Path:
    source, installed = checked_path(source), checked_path(installed)
    output = checked_path(output)
    if not source.is_dir() or not installed.is_dir():
        raise ValueError("Source and installed skill must be existing directories")
    # Reject overlap, including output ancestors: this is not an in-place update.
    roots = (source, installed, output)
    for i, first in enumerate(roots):
        for second in roots[i + 1:]:
            if first == second or first in second.parents or second in first.parents:
                raise ValueError("Source, installed and output paths must not overlap")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError("Output parent must already exist")
    if not (installed / "SKILL.md").is_file():
        raise ValueError("Installed skill is missing SKILL.md")
    official_entries = []
    for name in OFFICIAL:
        official_entries.extend(inventory(source / name, official=True))
    for name in (".gitignore", "SKILL.md"):
        if not (source / name).is_file():
            raise ValueError(f"Source {name} must be a regular file")
    for name in ("agents", "references", "scripts"):
        if not (source / name).is_dir():
            raise ValueError(f"Source {name} must be a directory")
    binding = preserved_binding(installed)
    local = installed / "local"
    local_entries = inventory(local) if os.path.lexists(local) else []
    if local_entries and not local.is_dir():
        raise ValueError("Installed local state must be a directory")

    # Exclusive mkdir refuses even a concurrently-created empty directory.
    # On copy failure remove only the new output owned by this invocation.
    output.mkdir(mode=0o700)
    try:
        copy_entries(official_entries, source, output)
        copy_entries(local_entries, installed, output)
        (output / "server-tools.path").write_bytes(binding)
    except BaseException:
        shutil.rmtree(output)
        raise
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, required=True,
                        help="Existing user skill on this host (never modified)")
    parser.add_argument("--out", type=Path, required=True,
                        help="New staging directory outside agent discovery; parent must exist")
    args = parser.parse_args()
    try:
        output = stage(Path(__file__).absolute().parents[1], args.installed, args.out)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Staged: {output}")
    print("Preserved user-local state and tools binding; no tools were run.")
    print("Not activated. Review customizations, consent scope and note applicability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
