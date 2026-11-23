#!/usr/bin/env python3
"""Stage byte-identical actual Server tar deliveries and external FASTA oracles.

Use a new Windows-readable output directory, outside the Server workspaces.
This copies only the named delivery artifacts, not reads or native runtimes.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

TOOLS = ("01_degap", "02_tgsgapcloser", "03_quartet", "04_lrgapcloser")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def transfer(source, destination, expected=None):
    actual = sha(source)
    if expected is not None and actual != expected:
        raise ValueError(f"Server artifact differs from its receipt: {source}")
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
    if sha(destination) != actual:
        raise ValueError(f"Staged artifact differs from Server: {destination}")
    return actual


def stage(out, workspaces):
    out = out.resolve()
    out.mkdir()  # Never adopt an existing evidence/app directory.
    cases, prefixes = [], set()
    for item in workspaces:
        prefix, _, value = item.partition("=")
        if not re.fullmatch(r"[A-Za-z0-9-]+", prefix) or not value or prefix in prefixes:
            raise ValueError("Each workspace needs a unique label=path (letters/digits/hyphens)")
        prefixes.add(prefix)
        workspace = Path(value).resolve(strict=True)
        for group in ("00_lgz", *TOOLS):
            final, delivery = workspace / "05_final" / group, workspace / "07_delivery" / group
            if group != "00_lgz" and not delivery.exists():
                continue
            tool = None if group == "00_lgz" else group.split("_", 1)[1]
            ident = f"{prefix}-{tool or 'lgz'}"
            provenance = json.loads((final / "provenance.json").read_text())
            if provenance["tool"] != (tool or "lgz"):
                raise ValueError(f"Mismatched tool in provenance: {final}")
            if tool:
                accepted = provenance["accepted_edit_count"]
                if type(accepted) is not int or accepted < 0:
                    raise ValueError(f"Invalid accepted edit count: {final}")
                assembly_hash = provenance["artifacts"]["assembly.fa"]
                receipt = json.loads((delivery / "delivery.json").read_text())
                if receipt["tool"] != tool or receipt["run_id"] != provenance["run_id"]:
                    raise ValueError(f"Delivery belongs to a different run: {delivery}")
                archives = receipt["archives"]
            else:
                accepted, archives = 0, None
                assembly_hash = provenance["binding"]["assembly_sha256"]
            entry = {"id": ident, "tool": tool, "accepted": accepted, "assembly": ident + ".fa"}
            entry["assembly_sha256"] = transfer(
                final / "assembly.fa", out / entry["assembly"], assembly_hash,
            )
            for mode, suffix in (("full", ".tar.gz"), ("light", ".light.tar.gz")):
                if archives is not None:
                    row = archives[mode]
                    filename, expected = row["file"], row["sha256"]
                    if Path(filename).name != filename or not filename.endswith(suffix):
                        raise ValueError(f"Expected a portable tar delivery name: {filename}")
                else:
                    filename, expected = workspace.name + suffix, None
                entry[mode] = ident + suffix
                entry[mode + "_sha256"] = transfer(delivery / filename, out / entry[mode], expected)
            cases.append(entry)
    (out / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    print(f"Staged {len(cases)} Full/Light pairs: {out / 'cases.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workspace", action="append", required=True, metavar="LABEL=PATH")
    args = parser.parse_args()
    stage(args.out, args.workspace)
