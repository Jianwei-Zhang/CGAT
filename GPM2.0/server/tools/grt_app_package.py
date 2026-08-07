#!/usr/bin/env python3
"""Build the minimal App delivery payload from a validated Server workdir.

The Server workdir is the audit/validation boundary.  This tool deliberately
projects only the files consumed by the App importer and chromosome views;
intermediate GRT FASTA, evidence, cache, checkpoint, and Server tooling files
never cross that boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


APP_WORKFLOW = "gpm_grt_app_precomputed_v1"
APP_SCHEMA_VERSION = "1"
FINAL_PATH_SCHEMA_VERSION = "1"
FASTA_SUFFIXES = {".fa", ".fasta"}

REQUIRED_METADATA = (
    "reference.tsv",
    "datasets.tsv",
    "source_seq_locator.tsv",
    "chr_assignments.tsv",
    "grt_recipe.tsv",
    "grt_used_contigs.tsv",
)
OPTIONAL_METADATA = (
    "track_member_orders.tsv",
    "reference_chr_locator.tsv",
    "source_seq_n_regions.tsv",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_fai_lengths(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        columns = raw.rstrip("\r").split("\t")
        if len(columns) < 2 or not columns[0]:
            raise ValueError(f"invalid FAI row {path}:{line_number}")
        length = int(columns[1])
        if length <= 0 or columns[0] in lengths:
            raise ValueError(f"invalid or duplicate FAI record {path}:{columns[0]}")
        lengths[columns[0]] = length
    if not lengths:
        raise ValueError(f"FAI contains no records: {path}")
    return lengths


def copy_file(source_root: Path, staging_root: Path, relpath: str) -> None:
    source = source_root / relpath
    if not source.is_file():
        raise FileNotFoundError(f"required App payload file is missing: {relpath}")
    target = staging_root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_tree_filtered(source_root: Path, staging_root: Path, directory: str, include_fasta: bool) -> None:
    source_dir = source_root / directory
    if not source_dir.is_dir():
        return
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file():
            continue
        relpath = source.relative_to(source_root)
        if not include_fasta and source.suffix.lower() in FASTA_SUFFIXES:
            continue
        target = staging_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_annotation_tree(source_root: Path, staging_root: Path, directory: str) -> None:
    source_dir = source_root / directory
    if not source_dir.is_dir():
        return
    for source in sorted(source_dir.rglob("*.tsv")):
        if not source.is_file():
            continue
        relpath = source.relative_to(source_root)
        target = staging_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def project_package_table(source: Path, target: Path, package_mode: str) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
        if len(rows) != 1:
            raise ValueError("metadata/package.tsv must contain exactly one row")
        fieldnames = list(rows[0])
    rows[0]["workflow"] = APP_WORKFLOW
    rows[0]["schema_version"] = APP_SCHEMA_VERSION
    rows[0]["package_mode"] = package_mode
    rows[0]["grt_precompute_enabled"] = "true"
    rows[0]["recipe_locked"] = "true"
    rows[0]["final_path_schema_version"] = FINAL_PATH_SCHEMA_VERSION
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])


def project_recipe(source: Path, target: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        if len(rows) != 1:
            raise ValueError("metadata/grt_recipe.tsv must contain exactly one row")
        fieldnames = list(reader.fieldnames or [])
    # The App never reconstructs q0 or donor sets.  Keep the stable columns so
    # older catalog persistence code can consume the recipe row without making
    # those Server artifacts part of the delivery contract.
    for key in ("donor_set_id", "tel_donor_set_id", "q0_relpath"):
        rows[0][key] = ""
    rows[0]["final_q_relpath"] = "grt/q/q4.fa"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])


def project_used_contigs(source: Path, target: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    required = {
        "source_card_key",
        "dataset_name",
        "contig_name",
        "original_assignment",
        "target_chr",
        "placement_mode",
        "ref_alignment_status",
        "anchor_start",
        "orientation",
    }
    if not required.issubset(fieldnames):
        raise ValueError("metadata/grt_used_contigs.tsv is missing App source-card columns")
    trace_fields = {
        "ref_evidence_ids_json",
        "accepted_event_ids_json",
        "final_path_segment_ids_json",
        "pairwise_evidence_ids_json",
    }
    for row in rows:
        for key in trace_fields:
            if key in row:
                row[key] = "[]"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def project_final_path(source: Path, target: Path) -> tuple[dict, dict[str, int]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("chromosomes"), list):
        raise ValueError("metadata/grt_final_path.json has an invalid shape")
    payload["workflow"] = APP_WORKFLOW
    payload["schema_version"] = APP_SCHEMA_VERSION
    payload["q4_relpath"] = "grt/q/q4.fa"
    q4_lengths: dict[str, int] = {}
    for chromosome in payload["chromosomes"]:
        if not isinstance(chromosome, dict):
            raise ValueError("Final Path chromosome must be an object")
        chr_name = chromosome.get("chr")
        q4_lengths[chr_name] = int(chromosome["q4_length"])
        for segment in chromosome.get("segments", []):
            if isinstance(segment, dict):
                for key in ("event_id", "eventId", "evidence_ids", "evidenceIds", "source_card_key", "sourceCardKey"):
                    segment.pop(key, None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload, q4_lengths


def validate_source_locators(source_root: Path) -> dict[str, int]:
    path = source_root / "metadata/source_seq_locator.tsv"
    dataset_fai: dict[str, dict[str, int]] = {}
    with (source_root / "metadata/datasets.tsv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            dataset_fai[row["dataset_name"]] = read_fai_lengths(source_root / row["fai_relpath"])
    lengths: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            key = f"{row['dataset_name']}:{row['seq_name']}"
            if key in lengths:
                raise ValueError(f"duplicate source locator: {key}")
            records = dataset_fai.get(row["dataset_name"])
            if records is None:
                raise ValueError(f"source locator references unknown dataset: {key}")
            if row["seq_name"] not in records:
                raise ValueError(f"source locator sequence is missing from FAI: {key}")
            lengths[key] = records[row["seq_name"]]
    return lengths


def write_manifest(staging_root: Path, package_mode: str, include_fasta: bool, final_path: dict, q4_artifact_sha256: str, q4_lengths: dict[str, int]) -> None:
    manifest = {
        "workflow": APP_WORKFLOW,
        "schema_version": APP_SCHEMA_VERSION,
        "package_kind": "full" if include_fasta else "no_fasta",
        "fasta_available": include_fasta,
        "q4_relpath": "grt/q/q4.fa",
        "q4_artifact_sha256": q4_artifact_sha256,
        "q4_length_bp": sum(q4_lengths.values()),
        "q4_chromosome_lengths": q4_lengths,
        "final_path_sha256": hashlib.sha256(json.dumps(final_path, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    target = staging_root / "metadata/grt_app_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(source_root: Path, staging_root: Path, include_fasta: bool) -> None:
    source_root = source_root.resolve()
    staging_root = staging_root.resolve()
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)

    source_lengths = validate_source_locators(source_root)
    del source_lengths
    for filename in REQUIRED_METADATA:
        if filename == "grt_recipe.tsv":
            project_recipe(source_root / "metadata/grt_recipe.tsv", staging_root / "metadata/grt_recipe.tsv")
        elif filename == "grt_used_contigs.tsv":
            project_used_contigs(source_root / "metadata/grt_used_contigs.tsv", staging_root / "metadata/grt_used_contigs.tsv")
        else:
            copy_file(source_root, staging_root, f"metadata/{filename}")
    for filename in OPTIONAL_METADATA:
        if (source_root / "metadata" / filename).is_file():
            copy_file(source_root, staging_root, f"metadata/{filename}")
    final_path, q4_lengths = project_final_path(source_root / "metadata/grt_final_path.json", staging_root / "metadata/grt_final_path.json")
    project_package_table(source_root / "metadata/package.tsv", staging_root / "metadata/package.tsv", "full" if include_fasta else "no_fasta")

    copy_tree_filtered(source_root, staging_root, "data", include_fasta)
    # Alignment views consume result.paf only.  Query/target FASTA, commands,
    # logs, and tool caches are Server-only and intentionally omitted.
    for result in sorted((source_root / "runs").rglob("result.paf")):
        relpath = result.relative_to(source_root)
        target = staging_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result, target)
    copy_annotation_tree(source_root, staging_root, "tel")
    copy_annotation_tree(source_root, staging_root, "cen")

    q4_source = source_root / "grt/q/q4.fa"
    if include_fasta:
        copy_file(source_root, staging_root, "grt/q/q4.fa")
        if (source_root / "grt/q/q4.fa.fai").is_file():
            copy_file(source_root, staging_root, "grt/q/q4.fa.fai")
        q4_hash = sha256_file(q4_source)
    else:
        q4_hash = sha256_file(q4_source)
    write_manifest(staging_root, "full" if include_fasta else "no_fasta", include_fasta, final_path, q4_hash, q4_lengths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--include-fasta", action="store_true")
    group.add_argument("--no-fasta", action="store_true")
    args = parser.parse_args()
    build(args.source, args.staging, args.include_fasta)
    print(f"App payload staged at {args.staging}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
