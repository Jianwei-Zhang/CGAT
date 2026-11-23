#!/usr/bin/env python3
"""Run the bundled, pinned DEGAP v2 in the active cgat-server environment."""
import argparse
from pathlib import Path
import os
import sys


def prepare_shared_reads(runtime, argv):
    parser = argparse.ArgumentParser(description="Prepare the pinned DEGAP shared reads and input manifest")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hifi", nargs="+", default=[])
    parser.add_argument("--ont", nargs="+", default=[])
    options = parser.parse_args(argv)
    if not (options.hifi or options.ont):
        parser.error("shared preparation requires --hifi and/or --ont")
    sys.path.insert(0, str(runtime))
    from PreparedReads import contract, prepare

    try:
        prepare(options.out / "processed_reads", contract(options.hifi, options.ont))
    except (ValueError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")


def main():
    args = sys.argv[1:]
    runtime = Path(__file__).resolve().parent / "degap_core/bin"
    if args[:1] == ["prepare-shared-reads"]:
        return prepare_shared_reads(runtime, args[1:])

    # Retain the existing manual GapFiller parameter contract.
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
    output = option("--out") or option("-o")
    if output and option("--mode") in {"gapfiller", "telseeker_ctg"}:
        prepared = Path(output) / "processed_reads"
        if prepared.is_symlink() and not (prepared / "manifest.json").is_file():
            raise SystemExit("This shared reads cache predates the pinned DEGAP input manifest. "
                             "Keep the old results; for a new run, re-export DEGAP-JOBS from the updated App "
                             "and use a fresh job output directory.")
    entry = runtime / "DEGAP.py"
    if not entry.is_file():
        raise SystemExit("Bundled DEGAP runtime is missing; update the Server tools and project runtime.")
    os.execv(sys.executable, [sys.executable, "-B", str(entry), *args])


if __name__ == "__main__":
    main()
