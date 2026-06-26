#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path


FIELDS = [
    "qseqid",
    "sseqid",
    "pident",
    "length",
    "mismatch",
    "gapopen",
    "qstart",
    "qend",
    "sstart",
    "send",
    "evalue",
    "bitscore",
    "qlen",
    "slen",
    "nident",
    "gaps",
]


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_int(value, field_name, line_number):
    try:
        return int(value)
    except ValueError:
        fail(f"invalid {field_name} on BLAST row {line_number}: {value!r}")


def parse_float(value, field_name, line_number):
    try:
        return float(value)
    except ValueError:
        fail(f"invalid {field_name} on BLAST row {line_number}: {value!r}")


def convert_row(values, line_number):
    if len(values) != len(FIELDS):
        fail(
            f"expected {len(FIELDS)} BLAST columns on row {line_number}, got {len(values)}"
        )
    row = dict(zip(FIELDS, values))
    qstart = parse_int(row["qstart"], "qstart", line_number)
    qend = parse_int(row["qend"], "qend", line_number)
    sstart = parse_int(row["sstart"], "sstart", line_number)
    send = parse_int(row["send"], "send", line_number)
    qlen = parse_int(row["qlen"], "qlen", line_number)
    slen = parse_int(row["slen"], "slen", line_number)
    block_length = parse_int(row["length"], "length", line_number)
    nident = parse_int(row["nident"], "nident", line_number)
    pident = parse_float(row["pident"], "pident", line_number)

    query_start = min(qstart, qend) - 1
    query_end = max(qstart, qend)
    target_start = min(sstart, send) - 1
    target_end = max(sstart, send)
    if min(query_start, target_start) < 0:
        fail(f"BLAST row {line_number} has non-positive coordinates")
    if query_end < query_start or target_end < target_start:
        fail(f"BLAST row {line_number} has invalid coordinate order")

    strand = "+" if sstart <= send else "-"
    divergence = max(0.0, min(1.0, 1.0 - (pident / 100.0)))

    return [
        row["qseqid"],
        str(qlen),
        str(query_start),
        str(query_end),
        strand,
        row["sseqid"],
        str(slen),
        str(target_start),
        str(target_end),
        str(nident),
        str(block_length),
        "255",
        f"dv:f:{divergence:.6f}",
        f"de:f:{divergence:.6f}",
        f"eg:i:{parse_int(row['gaps'], 'gaps', line_number)}",
        f"bs:f:{parse_float(row['bitscore'], 'bitscore', line_number):.3f}",
        f"ev:f:{parse_float(row['evalue'], 'evalue', line_number):.6g}",
    ]


def convert(input_path, output_path):
    with input_path.open(encoding="utf-8") as source, output_path.open(
        "w", encoding="utf-8"
    ) as sink:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            paf_row = convert_row(line.split("\t"), line_number)
            sink.write("\t".join(paf_row) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Convert GPM BLAST outfmt 6 rows to PAF.")
    parser.add_argument("--input", required=True, help="BLAST outfmt 6 input path")
    parser.add_argument("--output", required=True, help="PAF output path")
    args = parser.parse_args()
    convert(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
