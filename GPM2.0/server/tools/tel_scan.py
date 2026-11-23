#!/usr/bin/env python3
"""Scan prepared telomere motifs in either workspace layout, in source coordinates."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:
    from workspace_layout import workspace_join, relative_path
    from annotation_library import verify_snapshot
except ModuleNotFoundError:
    from .workspace_layout import workspace_join, relative_path
    from .annotation_library import verify_snapshot


def fail(message):
    raise ValueError(message)


def read_rules(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rules = []
    for row in rows:
        rule_id = str(row.get("rule_id", "")).strip()
        motif = str(row.get("motif", "")).strip().upper()
        try:
            min_repeat = int(row.get("min_repeat", ""))
        except ValueError:
            fail(f"invalid tel min_repeat in {path}: {row!r}")
        if not rule_id or not motif or min_repeat < 1:
            fail(f"invalid tel rule in {path}: {row!r}")
        rules.append(
            {
                "rule_id": rule_id,
                "motif": motif,
                "min_repeat": min_repeat,
                "provenance": row.get("provenance", "[]"),
            }
        )
    return rules


def read_fasta_records(path):
    records = []
    current_name = None
    current_parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_name is not None:
                    records.append((current_name, "".join(current_parts)))
                current_name = line[1:].split()[0]
                current_parts = []
                continue
            current_parts.append(line)
    if current_name is not None:
        records.append((current_name, "".join(current_parts)))
    return records


def reverse_complement(motif):
    table = str.maketrans("ACGTacgt", "TGCAtgca")
    return motif.translate(table)[::-1].upper()


def scan_pattern(sequence, pattern, min_repeat):
    import re
    motif = pattern.upper()
    for match in re.finditer(f"(?:{re.escape(motif)}){{{min_repeat},}}", sequence.upper()):
        yield match.start() + 1, match.end(), (match.end() - match.start()) // len(motif)


def iter_rule_hits(sequence, rule):
    motif = rule["motif"]
    min_repeat = rule["min_repeat"]
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, motif, min_repeat):
        yield start_bp, end_bp, repeat_count, "+"
    rc = reverse_complement(motif)
    if rc == motif:
        return
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, rc, min_repeat):
        yield start_bp, end_bp, repeat_count, "-"


def parse_dataset_specs(values):
    specs = []
    for value in values:
        if "=" not in value:
            fail(f"invalid dataset spec: {value}")
        dataset_name, fasta_path = value.split("=", 1)
        dataset_name = dataset_name.strip()
        fasta = Path(fasta_path)
        if not dataset_name or not fasta.exists():
            fail(f"invalid dataset spec: {value}")
        specs.append((dataset_name, fasta))
    return specs



def output_name(value):
    """Preserve valid Unicode/punctuation; reject only unsafe path components."""
    if not isinstance(value, str) or not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("unsafe chromosome/dataset name for telomere scan")
    relative_path("name_" + value)
    return value

def scan(work_root, chr_name, datasets):
    work_root = Path(work_root).resolve()
    dataset_specs = parse_dataset_specs(datasets)
    for name in [chr_name, *(name for name, _ in dataset_specs)]:
        output_name(name)
    verify_snapshot(work_root)
    rules = read_rules(workspace_join(work_root, "tel/rules.tsv"))
    with_provenance = workspace_join(work_root, "metadata/annotation_library_snapshot.json").is_file()
    output_dir = workspace_join(work_root, "tel", f"chr_{chr_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    header = [
        "rule_id",
        "dataset_name",
        "seq_name",
        "assigned_chr_name",
        "motif",
        "min_repeat",
        "repeat_count",
        "start_bp",
        "end_bp",
        "strand",
    ]
    if with_provenance:
        header.append("provenance")

    for dataset_name, fasta_path in dataset_specs:
        output_path = output_dir / f"{dataset_name}.tsv"
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(header)
            for seq_name, sequence in read_fasta_records(fasta_path):
                for rule in rules:
                    for start_bp, end_bp, repeat_count, strand in iter_rule_hits(sequence, rule):
                        writer.writerow(
                            [
                                rule["rule_id"],
                                dataset_name,
                                seq_name,
                                chr_name,
                                rule["motif"],
                                rule["min_repeat"],
                                repeat_count,
                                start_bp,
                                end_bp,
                                strand,
                            ] + ([rule["provenance"]] if with_provenance else [])
                        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chr", required=True)
    parser.add_argument("--dataset", action="append", required=True)
    args = parser.parse_args()
    try:
        scan(args.root, args.chr, args.dataset)
    except (OSError, ValueError) as error:
        parser.exit(2, "ERROR: " + str(error) + "\n")


if __name__ == "__main__":
    main()
