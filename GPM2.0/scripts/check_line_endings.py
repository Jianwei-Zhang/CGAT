#!/usr/bin/env python3
"""Fail when a tracked text file in GPM2.0 contains a carriage return."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BINARY_SUFFIXES = {
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pptx",
    ".xlsx",
}


def git_output(*args: str, cwd: Path) -> bytes:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
    except FileNotFoundError:
        print("error: git is required to check tracked line endings", file=sys.stderr)
        raise SystemExit(2) from None
    except subprocess.CalledProcessError as exc:
        print(f"error: git command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    git_root = Path(
        git_output("rev-parse", "--show-toplevel", cwd=project_root)
        .decode()
        .strip()
    )
    project_prefix = project_root.relative_to(git_root).as_posix()
    tracked = git_output(
        "ls-files",
        "-z",
        "--",
        project_prefix,
        cwd=git_root,
    ).split(b"\0")

    violations: list[str] = []
    scanned = 0
    for raw_path in tracked:
        if not raw_path:
            continue
        relative_path = Path(raw_path.decode(errors="surrogateescape"))
        path = git_root / relative_path
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue

        data = path.read_bytes()
        if b"\0" in data:
            continue
        scanned += 1

        offset = data.find(b"\r")
        if offset < 0:
            continue
        line = data.count(b"\n", 0, offset) + 1
        ending = "CRLF" if data[offset : offset + 2] == b"\r\n" else "lone CR"
        violations.append(f"{relative_path.as_posix()}:{line}: contains {ending}")

    if violations:
        print("Line-ending check failed; tracked text files must use LF:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1

    print(f"Line-ending check passed ({scanned} tracked text files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
