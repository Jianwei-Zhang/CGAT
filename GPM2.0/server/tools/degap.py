#!/usr/bin/env python3
"""Run the bundled, pinned DEGAP v2 in the active cgat-server environment."""
from pathlib import Path
import os
import sys


def main():
    # The pinned upstream GapFiller accesses roundDir before initialization at
    # zero rounds. Fail with a useful message; do not silently execute a round.
    args = sys.argv[1:]
    def option(name):
        for index, arg in enumerate(args):
            if arg == name and index + 1 < len(args):
                return args[index + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
        return None
    if option("--mode") == "gapfiller" and option("--MaximumExtensionRound") == "0":
        raise SystemExit("Bundled GapFiller requires --MaximumExtensionRound >= 1 (or leave it unset). Zero-round TelSeeker remains supported.")
    for index, arg in enumerate(args):
        if arg in ("--out", "-o") and index + 1 < len(args):
            args[index + 1] = args[index + 1].rstrip("/") or "/"
        elif arg.startswith("--out="):
            args[index] = "--out=" + (arg.split("=", 1)[1].rstrip("/") or "/")
    entry = Path(__file__).resolve().parent / "degap_core/bin/DEGAP.py"
    if not entry.is_file():
        raise SystemExit("Bundled DEGAP runtime is missing; update the Server tools and project runtime.")
    os.execv(sys.executable, [sys.executable, "-B", str(entry), *args])


if __name__ == "__main__":
    main()
