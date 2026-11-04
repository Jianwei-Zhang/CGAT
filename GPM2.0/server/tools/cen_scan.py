#!/usr/bin/env python3
"""Search centromere-related repeats, then merge supported candidate regions.

MUMmer --maxmatch deliberately keeps repetitive seeds; minimap2's genome-scale
presets and secondary-hit caps are not appropriate for ~155-180 bp monomers.
Coordinates in marks.tsv remain 1-based inclusive, as required by the App.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess

try:
    from annotation_library import fasta_records, fasta_bytes, atomic_write, write_tsv, json_text, verify_snapshot
except ModuleNotFoundError:  # Imported through server.tools.
    from .annotation_library import fasta_records, fasta_bytes, atomic_write, write_tsv, json_text, verify_snapshot

# Internal v1 policy, deliberately not another user parameter. Needs real-data
# calibration during acceptance; gaps never count as aligned support.
MERGE_GAP_BP = 200
MARK_FIELDS = ("cen_id", "chr_name", "query_name", "dataset_name", "ctg_name", "ctg_start", "ctg_end",
               "strand", "align_length", "identity", "mapq", "region_length", "provenance")


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def parse_coords(path, entries, minimum_identity):
    hits = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 13:
                raise ValueError(f"{path}: expected 13 show-coords -THrcl columns")
            ref_start, ref_end, start, end, ref_length, query_length = map(int, fields[:6])
            identity = float(fields[6])
            query_name, contig = fields[11:13]
            if query_name not in entries:
                raise ValueError(f"unknown cen sequence in {path}: {query_name}")
            if identity < minimum_identity:
                continue
            hits.append({"start": min(start, end), "end": max(start, end), "query": query_name,
                         "contig": contig, "strand": "+" if (end >= start) == (ref_end >= ref_start) else "-",
                         "identity": identity, "weight": min(ref_length, query_length)})
    return hits


def merge_hits(hits, entries, chromosome, dataset, min_len):
    # Include both strands and all library entries in each connected region.
    # Track union support rather than adding overlapping hits or bridging gaps.
    hits.sort(key=lambda hit: (hit["contig"], hit["start"], hit["end"], hit["query"]))
    groups = []
    for hit in hits:
        if not groups or groups[-1]["contig"] != hit["contig"] or hit["start"] > groups[-1]["end"] + MERGE_GAP_BP + 1:
            groups.append({"contig": hit["contig"], "start": hit["start"], "end": hit["end"], "hits": [hit]})
        else:
            groups[-1]["end"] = max(groups[-1]["end"], hit["end"])
            groups[-1]["hits"].append(hit)
    rows = []
    for group in groups:
        covered, last_end = 0, 0
        queries, source_entries = set(), {}
        weighted_identity, total_weight = 0.0, 0
        strand_weight = {"+": 0, "-": 0}
        for hit in group["hits"]:
            covered += max(0, hit["end"] - max(hit["start"], last_end + 1) + 1)
            last_end = max(last_end, hit["end"])
            queries.add(hit["query"])
            weight = hit["weight"]
            weighted_identity += hit["identity"] * weight
            total_weight += weight
            strand_weight[hit["strand"]] += weight
            for source in json.loads(entries[hit["query"]].get("provenance") or "[]"):
                source_entries[json_text(source)] = source
        if covered < min_len:
            continue
        query_names = ";".join(sorted(queries))
        rows.append({"cen_id": ";".join(sorted({entries[q]["cen_id"] for q in queries})),
                     "chr_name": chromosome, "query_name": query_names, "dataset_name": dataset,
                     "ctg_name": group["contig"], "ctg_start": group["start"], "ctg_end": group["end"],
                     "strand": "+" if strand_weight["+"] >= strand_weight["-"] else "-",
                     "align_length": covered, "identity": f"{weighted_identity / max(1, total_weight):.3f}",
                     # nucmer does not report mapping quality; do not invent one.
                     "mapq": 0, "region_length": group["end"] - group["start"] + 1,
                     "provenance": json_text(list(source_entries.values()))})
    return rows


def scan(root, chromosome, datasets, threads, run_dir):
    verify_snapshot(root)
    rows = [r for r in table(root / "cen/reference.tsv") if r.get("chr_name") in ("*", chromosome)]
    output = root / "cen" / f"chr_{chromosome}"
    # Preserve legacy package/append TSV headers for an already-prepared project.
    fields = MARK_FIELDS if (root / "metadata/annotation_library_snapshot.json").is_file() else MARK_FIELDS[:11]
    if not rows:
        write_tsv(output / "marks.tsv", fields, [])
        return
    entries = {row["sequence_name"]: row for row in rows}
    sequences = {}
    for relative in sorted({r["fasta_relpath"] for r in rows}):
        for name, sequence in fasta_records(root / relative):
            if name in entries:
                sequences[name] = sequence
    if set(sequences) != set(entries):
        raise ValueError("prepared cen FASTA and reference.tsv disagree")
    min_len = max(int(row["min_len"]) for row in rows)
    min_identity = max(float(row["min_identity"]) for row in rows)
    run_dir.mkdir(parents=True, exist_ok=True)
    query = run_dir / "scan_inputs/library.fa"
    atomic_write(query, fasta_bytes(sorted(sequences.items())))
    marks = []
    shortest = min(len(sequence) for sequence in sequences.values())
    min_match, min_cluster = min(12, shortest), min(40, shortest)
    for index, spec in enumerate(datasets):
        name, fasta = spec.split("=", 1)
        prefix = run_dir / f"dataset_{index}"
        with (run_dir / f"nucmer_{index}.log").open("w") as log:
            subprocess.run(["nucmer", "--maxmatch", "--nosimplify", "-l", str(min_match), "-c", str(min_cluster),
                            "-t", str(threads), "-p", str(prefix), str(query), str(Path(fasta).resolve())],
                           check=True, stdout=log, stderr=subprocess.STDOUT)
        coords = prefix.with_suffix(".coords.tsv")
        with coords.open("w") as out, (run_dir / f"coords_{index}.log").open("w") as log:
            subprocess.run(["show-coords", "-THrcl", str(prefix) + ".delta"], check=True, stdout=out, stderr=log)
        marks.extend(merge_hits(parse_coords(coords, entries, min_identity), entries, chromosome, name, min_len))
    write_tsv(output / "marks.tsv", fields, marks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chr", required=True)
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    scan(args.root.resolve(), args.chr, args.dataset, args.threads, args.run_dir.resolve())


if __name__ == "__main__":
    main()
