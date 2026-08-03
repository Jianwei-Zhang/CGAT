#!/usr/bin/env python3

import argparse
import csv
import os
import tempfile
from collections import defaultdict
from pathlib import Path


FIELDNAMES = [
    "target_track",
    "target_chr",
    "member_dataset",
    "member_ctg",
    "member_order",
]
DERIVED_DATASET = "derived_ctg"


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def read_tsv(path, required=True):
    if not path.exists():
        if required:
            fail(f"required metadata file is missing: {path}")
        return [], []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def require_header(path, actual, expected):
    if actual != expected:
        fail(f"unexpected header in {path}: expected {expected}, got {actual}")


def parse_anchor(row, row_number):
    raw = (row.get("anchor_start") or "").strip()
    try:
        return int(raw)
    except ValueError:
        fail(f"invalid anchor_start at chr_assignments.tsv row {row_number}: {raw!r}")


def load_existing_ranks(path):
    rows, fieldnames = read_tsv(path, required=False)
    if not rows and not fieldnames:
        return {}
    require_header(path, fieldnames, FIELDNAMES)
    ranks = {}
    for row_number, row in enumerate(rows, start=2):
        key = (
            (row.get("target_track") or "").strip(),
            (row.get("target_chr") or "").strip(),
            (row.get("member_dataset") or "").strip(),
            (row.get("member_ctg") or "").strip(),
        )
        try:
            member_order = int((row.get("member_order") or "").strip())
        except ValueError:
            fail(f"invalid member_order in {path} row {row_number}")
        if not all(key) or member_order < 1 or key in ranks:
            fail(f"invalid or duplicate member order row in {path} at row {row_number}")
        ranks[key] = member_order
    return ranks


def build_member_rows(server_dir):
    metadata_dir = server_dir / "metadata"
    assignment_path = metadata_dir / "chr_assignments.tsv"
    member_path = metadata_dir / "track_members.tsv"
    output_path = metadata_dir / "track_member_orders.tsv"

    assignments, assignment_fields = read_tsv(assignment_path)
    require_header(
        assignment_path,
        assignment_fields,
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "support_bp",
            "support_percent",
            "anchor_start",
        ],
    )
    track_members, member_fields = read_tsv(member_path, required=False)
    if member_fields:
        require_header(
            member_path,
            member_fields,
            [
                "member_dataset",
                "member_ctg",
                "target_chr",
                "target_track",
                "member_role",
                "created_at",
            ],
        )

    derived_targets = {}
    for row_number, row in enumerate(track_members, start=2):
        member_dataset = (row.get("member_dataset") or "").strip()
        member_ctg = (row.get("member_ctg") or "").strip()
        target_track = (row.get("target_track") or "").strip()
        target_chr = (row.get("target_chr") or "").strip()
        key = (member_dataset, member_ctg)
        if not all((*key, target_track, target_chr)):
            fail(f"empty track member field in {member_path} row {row_number}")
        if key in derived_targets:
            fail(f"duplicate track member mapping for {member_dataset}:{member_ctg}")
        derived_targets[key] = (target_track, target_chr)

    existing_ranks = load_existing_ranks(output_path)
    grouped = defaultdict(list)
    seen_members = set()
    used_derived_targets = set()
    for source_index, row in enumerate(assignments):
        row_number = source_index + 2
        member_dataset = (row.get("dataset_name") or "").strip()
        member_ctg = (row.get("seq_name") or "").strip()
        assigned_chr = (row.get("assigned_chr_name") or "").strip()
        if not member_dataset or not member_ctg or not assigned_chr:
            fail(f"empty assignment field in {assignment_path} row {row_number}")

        if member_dataset == DERIVED_DATASET:
            member_key = (member_dataset, member_ctg)
            target = derived_targets.get(member_key)
            if target is None:
                fail(
                    f"derived assignment has no track member mapping: {member_dataset}:{member_ctg}"
                )
            target_track, target_chr = target
            if target_chr != assigned_chr:
                fail(
                    f"derived assignment chromosome mismatch for {member_dataset}:{member_ctg}: "
                    f"assignment={assigned_chr}, track_member={target_chr}"
                )
            used_derived_targets.add(member_key)
        else:
            target_track = member_dataset
            target_chr = assigned_chr

        identity = (target_track, target_chr, member_dataset, member_ctg)
        if identity in seen_members:
            fail(
                f"duplicate ordered member: {target_track}:{target_chr} "
                f"{member_dataset}:{member_ctg}"
            )
        seen_members.add(identity)
        anchor = parse_anchor(row, row_number)
        previous_rank = existing_ranks.get(identity)
        tie_rank = (0, previous_rank) if previous_rank is not None else (1, source_index)
        grouped[(target_track, target_chr)].append(
            (anchor, tie_rank, source_index, member_dataset, member_ctg)
        )

    unused_derived = set(derived_targets) - used_derived_targets
    if unused_derived:
        formatted = ", ".join(f"{dataset}:{ctg}" for dataset, ctg in sorted(unused_derived))
        fail(f"track member mappings have no chr assignment: {formatted}")

    output_rows = []
    for (target_track, target_chr), members in grouped.items():
        members.sort(key=lambda item: (item[0], item[1], item[2]))
        for member_order, (
            _anchor,
            _tie_rank,
            _source_index,
            member_dataset,
            member_ctg,
        ) in enumerate(members, start=1):
            output_rows.append(
                {
                    "target_track": target_track,
                    "target_chr": target_chr,
                    "member_dataset": member_dataset,
                    "member_ctg": member_ctg,
                    "member_order": member_order,
                }
            )
    return output_path, output_rows


def write_atomic_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Compute authoritative ds-track member order metadata"
    )
    parser.add_argument("--server-dir", required=True, type=Path)
    args = parser.parse_args()
    server_dir = args.server_dir.resolve()
    if not server_dir.is_dir():
        fail(f"server directory does not exist: {server_dir}")
    output_path, rows = build_member_rows(server_dir)
    write_atomic_tsv(output_path, rows)
    group_count = len({(row["target_track"], row["target_chr"]) for row in rows})
    print(f"Wrote {output_path} ({group_count} groups, {len(rows)} members)")


if __name__ == "__main__":
    main()
