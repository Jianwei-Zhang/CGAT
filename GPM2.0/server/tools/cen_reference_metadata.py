#!/usr/bin/env python3

"""Validate and write centromere reference metadata."""

import csv
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


output_path = Path(sys.argv[1])
cen_fasta = Path(sys.argv[2])
ref_fai = Path(sys.argv[3])
fasta_relpath = sys.argv[4]
min_len = sys.argv[5]
min_identity = sys.argv[6]

ref_chrs = set()
with ref_fai.open(encoding="utf-8") as handle:
    for line in handle:
        fields = line.rstrip("\n").split("\t")
        if fields and fields[0]:
            ref_chrs.add(fields[0])

seen_chrs = set()
rows = []
with cen_fasta.open(encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.strip()
        if not line.startswith(">"):
            continue
        sequence_name = line[1:].split()[0]
        suffix = "_centromere"
        if not sequence_name.endswith(suffix):
            fail(f"--cen FASTA header must end with _centromere: {sequence_name}")
        chr_name = sequence_name[: -len(suffix)]
        if not chr_name:
            fail(f"--cen FASTA header has empty chromosome name: {sequence_name}")
        if chr_name in seen_chrs:
            fail(f"Duplicate --cen chromosome entry: {chr_name}")
        if chr_name not in ref_chrs:
            fail(f"Unknown --cen chromosome entry: {chr_name}")
        seen_chrs.add(chr_name)
        rows.append(["cen", chr_name, sequence_name, fasta_relpath, min_len, min_identity])

if not rows:
    fail("--cen FASTA contains no centromere records")

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["cen_id", "chr_name", "sequence_name", "fasta_relpath", "min_len", "min_identity"])
    writer.writerows(rows)
