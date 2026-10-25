#!/usr/bin/env python3
"""Read-only, optionally colored tail of a prepared workspace log."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

from run_progress import colorize, use_color


def tail(handle, count: int) -> list[str]:
    handle.seek(0, 2)
    end = handle.tell()
    position, chunks, newlines = end, [], 0
    while position and newlines <= count and count:
        size = min(position, 65536)
        position -= size
        handle.seek(position)
        chunk = handle.read(size)
        chunks.append(chunk)
        newlines += chunk.count(b"\n")
    handle.seek(end)
    return b"".join(reversed(chunks)).decode("utf-8", errors="replace").splitlines()[-count:] if count else []


def watch(path: Path, count: int, follow: bool, colored: bool):
    handle = path.open("rb")
    try:
        for line in tail(handle, count):
            print(colorize(line, colored), flush=True)
        pending = b""
        while follow:
            chunk = handle.read(65536)
            if chunk:
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    print(colorize(line.decode("utf-8", errors="replace"), colored), flush=True)
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                time.sleep(0.2)
                continue
            current = os.fstat(handle.fileno())
            if (stat.st_dev, stat.st_ino) != (current.st_dev, current.st_ino):
                try:
                    replacement = path.open("rb")
                except FileNotFoundError:
                    time.sleep(0.2)
                    continue
                handle.close()
                handle = replacement
                pending = b""
            elif stat.st_size < handle.tell():
                handle.seek(0)
                pending = b""
            time.sleep(0.2)
    finally:
        handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--detailed", action="store_true", help="read run_all.log instead of progress.log")
    parser.add_argument("--follow", "-f", action="store_true")
    parser.add_argument("--lines", "-n", type=int, default=40)
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    args = parser.parse_args()
    if args.lines < 0:
        parser.error("--lines must be non-negative")
    path = args.server_dir / "logs" / ("run_all.log" if args.detailed else "progress.log")
    try:
        watch(path, args.lines, args.follow, use_color(args.color))
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}; older workspaces may need --detailed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
