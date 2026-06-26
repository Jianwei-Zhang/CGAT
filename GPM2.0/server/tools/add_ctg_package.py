#!/usr/bin/env python3

import csv
import shutil
import sys
from pathlib import Path

DERIVED_DATASET = "derived_ctg"


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_tsv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def read_manifest(path):
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) >= 2:
                rows.append((row[0], row[1]))
    return dict(rows), rows


def write_key_value_manifest(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def write_filtered_tsv(src, dst, predicate, allow_empty=False):
    rows, fieldnames = read_tsv(src)
    selected = [row for row in rows if predicate(row)]
    if not selected and not allow_empty:
        fail(f"add_ctg payload is missing rows from {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return selected


def copy_file(src, dst, required=True):
    if not src.exists():
        if required:
            fail(f"add_ctg payload is missing file: {src}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree(src, dst, required=True):
    if not src.exists():
        if required:
            fail(f"add_ctg payload is missing directory: {src}")
        return False
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return True


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: add_ctg_package.py <server_dir> <package_dir> <ctg_name>")

    server_dir = Path(argv[1])
    package_dir = Path(argv[2])
    ctg_name = argv[3]
    manifest_src = server_dir / "metadata" / "add_ctg_manifests" / f"{ctg_name}.tsv"
    manifest, manifest_rows = read_manifest(manifest_src)
    if manifest.get("package_type") != "add_ctg":
        fail(f"invalid add_ctg manifest: {manifest_src}")
    if manifest.get("ctg_name") != ctg_name:
        fail(f"manifest ctg_name does not match requested ctg: {ctg_name}")

    target_chr = manifest.get("target_chr", "")
    target_track = manifest.get("target_track", "")
    skip_self = manifest.get("skip_self", "false").lower() == "true"
    contains_fasta = manifest.get("contains_fasta", "true").lower() == "true"
    if not target_chr or not target_track:
        fail(f"manifest is missing target_chr or target_track: {manifest_src}")

    write_key_value_manifest(package_dir / "add_ctg" / "manifest.tsv", manifest_rows)

    payload_root = package_dir / "gpm_server"
    metadata_dir = server_dir / "metadata"
    write_filtered_tsv(
        metadata_dir / "datasets.tsv",
        payload_root / "metadata" / "datasets.tsv",
        lambda row: row.get("dataset_name") == DERIVED_DATASET,
    )
    write_filtered_tsv(
        metadata_dir / "derived_ctgs.tsv",
        payload_root / "metadata" / "derived_ctgs.tsv",
        lambda row: row.get("derived_dataset") == DERIVED_DATASET and row.get("ctg_name") == ctg_name,
    )
    write_filtered_tsv(
        metadata_dir / "track_members.tsv",
        payload_root / "metadata" / "track_members.tsv",
        lambda row: row.get("member_dataset") == DERIVED_DATASET and row.get("member_ctg") == ctg_name,
    )
    write_filtered_tsv(
        metadata_dir / "chr_assignments.tsv",
        payload_root / "metadata" / "chr_assignments.tsv",
        lambda row: row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == ctg_name,
    )
    locator_rows = write_filtered_tsv(
        metadata_dir / "source_seq_locator.tsv",
        payload_root / "metadata" / "source_seq_locator.tsv",
        lambda row: row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == ctg_name,
    )
    write_filtered_tsv(
        metadata_dir / "source_seq_n_regions.tsv",
        payload_root / "metadata" / "source_seq_n_regions.tsv",
        lambda row: row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == ctg_name,
        allow_empty=True,
    )

    if contains_fasta:
        for row in locator_rows:
            relpath = row.get("fasta_relpath", "")
            if relpath:
                copy_file(server_dir / relpath, payload_root / relpath)
                copy_file(server_dir / f"{relpath}.fai", payload_root / f"{relpath}.fai")

        copy_file(
            server_dir / f"data/derived_ctgs/{ctg_name}.fa",
            payload_root / f"data/datasets/{DERIVED_DATASET}.fa",
        )
        copy_file(
            server_dir / f"data/derived_ctgs/{ctg_name}.fa.fai",
            payload_root / f"data/datasets/{DERIVED_DATASET}.fa.fai",
        )

        chr_dataset_payload = payload_root / "runs" / f"chr_{target_chr}" / "datasets" / f"{DERIVED_DATASET}.fa"
        copy_file(server_dir / f"data/derived_ctgs/{ctg_name}.fa", chr_dataset_payload)

    copy_tree(
        server_dir / "runs" / "add_ctg" / f"{ctg_name}_vs_ref",
        payload_root / "runs" / "add_ctg" / f"{ctg_name}_vs_ref",
    )
    if not skip_self:
        add_ctg_runs_dir = server_dir / "runs" / f"chr_{target_chr}" / "add_ctg"
        if not add_ctg_runs_dir.exists():
            fail(f"add_ctg payload is missing directory: {add_ctg_runs_dir}")
        copied = 0
        for run_dir in sorted(add_ctg_runs_dir.iterdir()):
            if not run_dir.is_dir() or not run_dir.name.endswith(f"_vs_{ctg_name}"):
                continue
            copy_tree(
                run_dir,
                payload_root / "runs" / f"chr_{target_chr}" / "add_ctg" / run_dir.name,
            )
            copied += 1
        if copied == 0:
            fail(f"add_ctg payload is missing pairwise runs for {ctg_name} on {target_chr}")


if __name__ == "__main__":
    main(sys.argv)
