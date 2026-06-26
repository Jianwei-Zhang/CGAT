#!/usr/bin/env python3

import csv
import shutil
import sys
from pathlib import Path


def read_one_tsv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 1:
        raise SystemExit(f"expected exactly one row in {path}")
    return rows[0]


def read_tsv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def copy_file(src, dst):
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree(src, dst):
    if not src.exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return True


def write_filtered_tsv(src, dst, predicate):
    rows, fieldnames = read_tsv(src)
    selected = [row for row in rows if predicate(row)]
    if not selected:
        return []
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return selected


def write_filtered_tsv_allow_empty(src, dst, predicate):
    rows, fieldnames = read_tsv(src)
    selected = [row for row in rows if predicate(row)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return selected


def main(argv):
    if len(argv) != 16:
        raise SystemExit(
            "usage: add_dataset_package.py <server_dir> <package_dir> <dataset_name> "
            "<chr_score> <alignment_engine> <minimap_preset> <blastn_task> <blastn_evalue> "
            "<blastn_dust> <winnowmap_preset> <winnowmap_kmer> <winnowmap_repeat_fraction> "
            "<skip_self> <tel_enabled> <cen_enabled>"
        )

    server_dir = Path(argv[1])
    package_dir = Path(argv[2])
    dataset_name = argv[3]
    chr_score = argv[4]
    alignment_engine = argv[5]
    minimap_preset = argv[6]
    blastn_task = argv[7]
    blastn_evalue = argv[8]
    blastn_dust = argv[9]
    winnowmap_preset = argv[10]
    winnowmap_kmer = argv[11]
    winnowmap_repeat_fraction = argv[12]
    skip_self = argv[13].lower()
    tel_enabled = argv[14].lower()
    cen_enabled = argv[15].lower()
    reference = read_one_tsv(server_dir / "metadata" / "reference.tsv")
    self_alignment_available = "false" if skip_self == "true" else "true"

    manifest_rows = [
        ("package_type", "add_dataset"),
        ("dataset_name", dataset_name),
        ("reference_name", reference["reference_name"]),
        ("sequence_layout", "partitioned"),
        ("preassigned_chr", "true"),
        ("chr_assignment_min_coverage_percent", chr_score),
        ("alignment_engine", alignment_engine),
        ("minimap_preset", minimap_preset),
        ("blastn_task", blastn_task),
        ("blastn_evalue", blastn_evalue),
        ("blastn_dust", blastn_dust),
        ("winnowmap_preset", winnowmap_preset),
        ("winnowmap_kmer", winnowmap_kmer),
        ("winnowmap_repeat_fraction", winnowmap_repeat_fraction),
        ("skip_self", skip_self),
        ("self_alignment_available", self_alignment_available),
        ("tel_enabled", tel_enabled),
        ("cen_enabled", cen_enabled),
    ]
    with (package_dir / "add_package" / "manifest.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerows(manifest_rows)

    payload_root = package_dir / "gpm_server"
    metadata_dir = server_dir / "metadata"

    dataset_rows = write_filtered_tsv(
        metadata_dir / "datasets.tsv",
        payload_root / "metadata" / "datasets.tsv",
        lambda row: row.get("dataset_name") == dataset_name,
    )
    assignment_rows = write_filtered_tsv(
        metadata_dir / "chr_assignments.tsv",
        payload_root / "metadata" / "chr_assignments.tsv",
        lambda row: row.get("dataset_name") == dataset_name,
    )
    locator_rows = write_filtered_tsv(
        metadata_dir / "source_seq_locator.tsv",
        payload_root / "metadata" / "source_seq_locator.tsv",
        lambda row: row.get("dataset_name") == dataset_name,
    )
    write_filtered_tsv_allow_empty(
        metadata_dir / "source_seq_n_regions.tsv",
        payload_root / "metadata" / "source_seq_n_regions.tsv",
        lambda row: row.get("dataset_name") == dataset_name,
    )
    if not dataset_rows:
        raise SystemExit(f"add payload is missing dataset metadata for {dataset_name}")
    if not assignment_rows:
        raise SystemExit(f"add payload is missing chr assignments for {dataset_name}")
    if not locator_rows:
        raise SystemExit(f"add payload is missing source locators for {dataset_name}")

    copy_file(
        server_dir / "data" / "datasets" / f"{dataset_name}.fa",
        payload_root / "data" / "datasets" / f"{dataset_name}.fa",
    )
    copy_file(
        server_dir / "data" / "datasets" / f"{dataset_name}.fa.fai",
        payload_root / "data" / "datasets" / f"{dataset_name}.fa.fai",
    )
    for row in locator_rows:
        relpath = row.get("fasta_relpath", "")
        if relpath:
            copy_file(server_dir / relpath, payload_root / relpath)

    copy_tree(
        server_dir / "runs" / f"{dataset_name}_vs_ref",
        payload_root / "runs" / f"{dataset_name}_vs_ref",
    )
    for chr_dir in sorted((server_dir / "runs").glob("chr_*")):
        if not chr_dir.is_dir():
            continue
        rel_chr = chr_dir.relative_to(server_dir)
        copy_file(
            chr_dir / "datasets" / f"{dataset_name}.fa",
            payload_root / rel_chr / "datasets" / f"{dataset_name}.fa",
        )
        for child in sorted(chr_dir.iterdir()):
            if not child.is_dir():
                continue
            if (
                child.name == f"{dataset_name}_vs_self"
                or child.name.startswith(f"{dataset_name}_vs_")
                or child.name.endswith(f"_vs_{dataset_name}")
            ):
                copy_tree(child, payload_root / rel_chr / child.name)

    for tel_path in sorted((server_dir / "tel").glob(f"chr_*/{dataset_name}.tsv")):
        copy_file(tel_path, payload_root / tel_path.relative_to(server_dir))

    for marks_path in sorted((server_dir / "cen").glob("chr_*/marks.tsv")):
        write_filtered_tsv_allow_empty(
            marks_path,
            payload_root / marks_path.relative_to(server_dir),
            lambda row: row.get("dataset_name") == dataset_name,
        )


if __name__ == "__main__":
    main(sys.argv)
