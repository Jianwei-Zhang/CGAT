#!/usr/bin/env python3
"""Create small, deterministic synthetic GPM inputs, never production data."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

SEED = 20261013
CHROMOSOME_LENGTH = 60_000
GAP_START = 25_000
GAP_LENGTH = 200


def fasta_bytes(records: list[tuple[str, str]]) -> bytes:
    lines = []
    for name, sequence in records:
        lines.append(">" + name)
        lines.extend(sequence[pos:pos + 80] for pos in range(0, len(sequence), 80))
    return ("\n".join(lines) + "\n").encode("ascii")


def generate(destination: Path) -> dict:
    # mkdir(exist_ok=False) also rejects existing empty directories and symlinks.
    # Do not clean up on error: leave evidence without risking unrelated files.
    destination.mkdir(parents=True, exist_ok=False)
    rng = random.Random(SEED)
    sequences = ["".join(rng.choice("ACGT") for _ in range(CHROMOSOME_LENGTH))
                 for _ in range(2)]
    reference = [(f"chr{i + 1}", seq) for i, seq in enumerate(sequences)]
    primary = [(f"primary_ctg{i + 1}", seq[:GAP_START] + "N" * GAP_LENGTH
                + seq[GAP_START + GAP_LENGTH:]) for i, seq in enumerate(sequences)]
    support = [(f"support_ctg{i + 1}", seq) for i, seq in enumerate(sequences)]
    inputs = []
    for role, records in (("reference", reference), ("primary", primary), ("support", support)):
        payload = fasta_bytes(records)
        filename = f"{role}.fa"
        with (destination / filename).open("xb") as handle:
            handle.write(payload)
        inputs.append({"role": role, "file": filename, "records": len(records),
                       "bases": sum(len(seq) for _, seq in records),
                       "n_bases": sum(seq.count("N") for _, seq in records),
                       "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {"schema_version": 1, "purpose": "synthetic workflow smoke test only",
                "seed": SEED, "chromosome_length": CHROMOSOME_LENGTH,
                "primary_gap_start_0based": GAP_START, "primary_gap_length": GAP_LENGTH,
                "reads_qc": "not tested", "inputs": inputs}
    with (destination / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="New destination directory; existing paths are refused")
    args = parser.parse_args()
    try:
        manifest = generate(args.out)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
