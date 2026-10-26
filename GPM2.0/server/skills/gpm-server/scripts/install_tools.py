#!/usr/bin/env python3
"""First installation from docs first, then GitHub Release on failure; never overwrite."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tarfile
import shlex
import tempfile

sys.dont_write_bytecode = True
import official_download as downloads
import server_paths as paths


def yes(prompt):
    while True:
        try:
            answer = input(prompt + " [y/N]: ").strip()
        except EOFError:
            return False
        if answer in ("Y", "y"):
            return True
        if answer in ("", "N", "n"):
            return False
        print("Please enter Y/y or N/n.")


def install(skill, destination, release):
    destination = paths.checked(destination)
    if destination.exists():
        raise ValueError("Destination already exists; bind existing tools or choose another directory: " + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gpm-install-", dir=destination.parent) as tmp:
        source = downloads.extract(release, Path(tmp))
        info = downloads.verify_bundle(source, release)
        for name, record in info["files"].items():
            (source / name).chmod(record["mode"])
        (source / "SOURCE.json").chmod(0o644)
        destination.mkdir()  # Exclusive reservation, even an existing empty dir is refused.
        try:
            os.rename(source, destination)
        except BaseException:
            destination.rmdir()
            raise
    try:
        paths.bind(skill, destination)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Tools were installed at {destination}, but skill binding failed: {exc}. "
                         "Keep that directory and bind it after resolving the error; do not reinstall over it") from exc
    return destination


def main():
    if len(sys.argv) != 1:
        print("Usage: bash scripts/install_tools.sh (interactive; no arguments)", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print("No interactive terminal; nothing installed.", file=sys.stderr)
        return 2
    try:
        value = input("Server tools destination [" + paths.DEFAULT_TOOLS + "]: ").strip()
        destination = paths.checked(Path(value or paths.DEFAULT_TOOLS).expanduser().absolute())
        if destination.exists():
            raise ValueError("Destination exists. Ask for the installed tools path and bind it; do not reinstall over it")
        if not yes("Download and install Server tools to " + str(destination) + "?"):
            print("Cancelled; nothing installed.")
            return 0
        release = downloads.discover()
        install(Path(__file__).absolute().parents[1], destination, release)
        print("Server tools installed and skill bound: " + str(destination))
        print("Dependencies have NOT been installed or verified.")
        print("install.sh manages cgat-server; if no manager exists it bootstraps micromamba and initializes Bash.")
        if yes("Run install.sh to install/verify the dependency environment now?"):
            subprocess.run(["bash", str(destination / "install.sh")], check=True)
        else:
            print("Before analysis, install/validate the dependency environment or site modules.")
        print("Update later: bash " + shlex.quote(str(destination / "update.sh")))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, EOFError, tarfile.TarError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}. No analysis was started; existing installations were not overwritten.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
