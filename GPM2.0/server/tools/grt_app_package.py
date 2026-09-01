#!/usr/bin/env python3
"""Build the minimal App delivery payload from a validated Server workdir.

The Server workdir is the audit/validation boundary.  This tool deliberately
projects only the files consumed by the App importer and chromosome views.
Raw GRT FASTA, aligner evidence, cache, checkpoint, and Server tooling files
never cross that boundary; accepted alignments are reduced to compact display
evidence in the Final Path document.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from grt_display_evidence import build_display_evidence


APP_WORKFLOW = "gpm_grt_app_precomputed_v2"
APP_SCHEMA_VERSION = "2"
SERVER_FINAL_PATH_SCHEMA_VERSION = "1"
FINAL_PATH_SCHEMA_VERSION = "3"
FASTA_SUFFIXES = {".fa", ".fasta"}

REQUIRED_METADATA = (
    "reference.tsv",
    "datasets.tsv",
    "source_seq_locator.tsv",
    "chr_assignments.tsv",
    "grt_recipe.tsv",
    "grt_used_contigs.tsv",
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


def load_display_source_cards(source_root: Path) -> set[tuple[str, str, str]]:
    cards: set[tuple[str, str, str]] = set()
    table_specs = (
        (
            source_root / "metadata/chr_assignments.tsv",
            ("dataset_name", "seq_name", "assigned_chr_name"),
        ),
        (
            source_root / "metadata/grt_used_contigs.tsv",
            ("dataset_name", "contig_name", "target_chr"),
        ),
    )
    for path, columns in table_specs:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            fieldnames = set(reader.fieldnames or [])
            if not set(columns).issubset(fieldnames):
                raise ValueError(f"{path.relative_to(source_root)} is missing App display-card columns")
            for row_number, row in enumerate(reader, 2):
                values = tuple(str(row.get(column, "")).strip() for column in columns)
                if not all(values):
                    raise ValueError(
                        f"{path.relative_to(source_root)}:{row_number} has an empty App display-card identity"
                    )
                cards.add(values)
    return cards


def validate_display_final_path(
    payload: dict,
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> dict[str, int]:
    if payload.get("workflow") != "gpm_grt_precomputed_v2" or str(payload.get("schema_version")) != SERVER_FINAL_PATH_SCHEMA_VERSION:
        raise ValueError("metadata/grt_final_path.json has an unsupported Server workflow/schema")
    chromosomes = payload.get("chromosomes")
    if not isinstance(chromosomes, list) or not chromosomes:
        raise ValueError("metadata/grt_final_path.json chromosomes must be non-empty")

    q4_lengths: dict[str, int] = {}
    segment_ids: set[str] = set()
    for chromosome in chromosomes:
        if not isinstance(chromosome, dict):
            raise ValueError("Final Path chromosome must be an object")
        chr_name = str(chromosome.get("chr", "")).strip()
        if not chr_name or chr_name in q4_lengths:
            raise ValueError(f"invalid or duplicate Final Path chromosome: {chr_name or '<empty>'}")
        segments = chromosome.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"Final Path chromosome {chr_name} must contain segments")
        total_length = 0
        for index, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                raise ValueError(f"Final Path {chr_name} segment {index} must be an object")
            segment_id = str(segment.get("segment_id", "")).strip()
            if not segment_id or segment_id in segment_ids:
                raise ValueError(f"invalid or duplicate Final Path segment_id: {segment_id or '<empty>'}")
            segment_ids.add(segment_id)
            length = segment.get("length")
            if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
                raise ValueError(f"Final Path segment {segment_id} has an invalid length")
            total_length += length
            if segment.get("kind") == "gap":
                continue
            orientation = segment.get("orientation")
            source = segment.get("source")
            if orientation not in {"+", "-"} or not isinstance(source, dict):
                raise ValueError(f"Final Path segment {segment_id} has an invalid source/orientation")
            dataset_name = str(source.get("dataset", "")).strip()
            contig_name = str(source.get("contig", "")).strip()
            start = source.get("start")
            end = source.get("end")
            if source.get("orientation") != orientation:
                raise ValueError(f"Final Path segment {segment_id} source orientation does not match")
            source_length = source_lengths.get((dataset_name, contig_name))
            if (
                not dataset_name
                or not contig_name
                or not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start <= 0
                or end < start
                or source_length is None
                or end > source_length
                or end - start + 1 != length
            ):
                raise ValueError(f"Final Path segment {segment_id} has an invalid App source interval")
            if (dataset_name, contig_name, chr_name) not in display_source_cards:
                raise ValueError(
                    f"Final Path segment {segment_id} has no App display source card for {dataset_name}:{contig_name}:{chr_name}"
                )
        q4_length = chromosome.get("q4_length")
        if not isinstance(q4_length, int) or isinstance(q4_length, bool) or q4_length != total_length:
            raise ValueError(f"Final Path chromosome {chr_name} q4_length does not match its segments")
        q4_lengths[chr_name] = q4_length
    return q4_lengths


def project_final_path(
    source_root: Path,
    source: Path,
    target: Path,
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> tuple[dict, dict[str, int]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("metadata/grt_final_path.json has an invalid shape")
    q4_lengths = validate_display_final_path(payload, source_lengths, display_source_cards)
    display_evidence_by_chr = build_display_evidence(
        source_root,
        payload,
        source_lengths,
        display_source_cards,
    )
    payload["workflow"] = APP_WORKFLOW
    payload["schema_version"] = FINAL_PATH_SCHEMA_VERSION
    payload["q4_relpath"] = "grt/q/q4.fa"
    for chromosome in payload["chromosomes"]:
        chromosome["display_evidence"] = display_evidence_by_chr.get(
            str(chromosome.get("chr", "")),
            [],
        )
        for segment in chromosome.get("segments", []):
            if isinstance(segment, dict):
                # Schema 3 retains the accepted event identity solely so the
                # App importer can reject dangling display-evidence links. The
                # project read model still strips this trace field before the
                # Final Path reaches the frontend.
                for key in ("eventId", "evidence_ids", "evidenceIds", "source_card_key", "sourceCardKey"):
                    segment.pop(key, None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload, q4_lengths


def validate_source_locators(source_root: Path) -> dict[tuple[str, str], int]:
    path = source_root / "metadata/source_seq_locator.tsv"
    dataset_fai: dict[str, dict[str, int]] = {}
    with (source_root / "metadata/datasets.tsv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            dataset_fai[row["dataset_name"]] = read_fai_lengths(source_root / row["fai_relpath"])
    lengths: dict[tuple[str, str], int] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            key = (row["dataset_name"], row["seq_name"])
            if key in lengths:
                raise ValueError(f"duplicate source locator: {key[0]}:{key[1]}")
            records = dataset_fai.get(row["dataset_name"])
            if records is None:
                raise ValueError(f"source locator references unknown dataset: {key[0]}:{key[1]}")
            if row["seq_name"] not in records:
                raise ValueError(f"source locator sequence is missing from FAI: {key[0]}:{key[1]}")
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
    display_source_cards = load_display_source_cards(source_root)
    for filename in REQUIRED_METADATA:
        if filename == "grt_recipe.tsv":
            project_recipe(source_root / "metadata/grt_recipe.tsv", staging_root / "metadata/grt_recipe.tsv")
        elif filename == "grt_used_contigs.tsv":
            project_used_contigs(source_root / "metadata/grt_used_contigs.tsv", staging_root / "metadata/grt_used_contigs.tsv")
        else:
            copy_file(source_root, staging_root, f"metadata/{filename}")
    final_path, q4_lengths = project_final_path(
        source_root,
        source_root / "metadata/grt_final_path.json",
        staging_root / "metadata/grt_final_path.json",
        source_lengths,
        display_source_cards,
    )
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
