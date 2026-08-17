from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .common import *
from .stage_schema import *
from .stage_io import *

def stage_status_row(server_dir: Path, result: dict[str, object]) -> dict[str, object]:
    stage = str(result["stage"])
    checkpoint_relpath = f"grt/checkpoints/{stage}.json"
    checkpoint_path = server_dir / checkpoint_relpath
    if not checkpoint_path.is_file():
        fail(f"stage checkpoint is missing: {checkpoint_path}")
    return {
        "stage": stage,
        "q_input_version": result["q_input_version"],
        "q_input_sha256": result["q_input_sha256"],
        "q_output_version": result["q_output_version"],
        "q_output_sha256": result["q_output_sha256"],
        "donor_set_id": result["donor_set_id"],
        "status": "success",
        "checkpoint_relpath": checkpoint_relpath,
        "checkpoint_sha256": sha256_file(checkpoint_path),
    }

def read_donor_fragments(
    server_dir: Path,
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    donor_records: dict[str, str],
) -> list[dict[str, str]]:
    path = server_dir / "metadata/grt_donor_fragments.tsv"
    rows = [
        row
        for row in read_tsv(path, DONOR_FRAGMENT_FIELDS)
        if row["donor_set_id"] == donor_set["donor_set_id"]
    ]
    members_by_id = {row["member_id"]: row for row in donor_members}
    actual_by_record: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in rows:
        member = members_by_id.get(row["member_id"])
        if member is None or row["fasta_record_name"] != member["fasta_record_name"]:
            fail("D0 fragment references an unknown or mismatched donor member")
        sequence = donor_records[row["fasta_record_name"]]
        start, end = int(row["fragment_start"]), int(row["fragment_end"])
        if not (1 <= start <= end <= len(sequence)):
            fail("D0 fragment has invalid member coordinates")
        fragment = sequence[start - 1 : end]
        if (
            int(row["fragment_length"]) != len(fragment)
            or row["sequence_sha256"] != sha256_bytes(fragment.encode("ascii"))
            or re.search(r"N{100,}", fragment)
        ):
            fail("D0 fragment content or checksum is invalid")
        actual_by_record[row["fasta_record_name"]].append((start, end))
    for record_name, sequence in donor_records.items():
        expected: list[tuple[int, int]] = []
        cursor = 0
        for match in re.finditer(r"N{100,}", sequence):
            if cursor < match.start():
                expected.append((cursor + 1, match.start()))
            cursor = match.end()
        if cursor < len(sequence):
            expected.append((cursor + 1, len(sequence)))
        if sorted(actual_by_record.get(record_name, [])) != expected:
            fail(f"D0 fragment index does not exactly cover non-gap sequence: {record_name}")
    return rows

def verify_donor_freeze(
    server_dir: Path,
    recipe: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, str]], dict[str, str]]:
    donor_sets = read_tsv(
        server_dir / "metadata/grt_donor_sets.tsv",
        [
            "donor_set_id",
            "donor_kind",
            "manifest_relpath",
            "fasta_relpath",
            "fasta_sha256",
            "member_count",
        ],
    )
    ordinary = [
        row
        for row in donor_sets
        if row["donor_set_id"] == recipe["donor_set_id"] and row["donor_kind"] == "ordinary"
    ]
    if len(ordinary) != 1:
        fail("recipe ordinary donor_set_id does not resolve exactly once")
    donor_set = ordinary[0]
    donor_path = server_dir / donor_set["fasta_relpath"]
    if sha256_file(donor_path) != donor_set["fasta_sha256"]:
        fail("frozen ordinary donor FASTA checksum mismatch")
    member_rows = [
        row
        for row in read_tsv(
            server_dir / "metadata/grt_donor_members.tsv",
            [
                "donor_set_id",
                "member_id",
                "dataset_name",
                "contig_name",
                "source_start",
                "source_end",
                "orientation",
                "fasta_record_name",
                "sequence_sha256",
            ],
        )
        if row["donor_set_id"] == donor_set["donor_set_id"]
    ]
    if len(member_rows) != int(donor_set["member_count"]):
        fail("frozen ordinary donor member count mismatch")
    manifest_rows = read_tsv(server_dir / donor_set["manifest_relpath"], list(member_rows[0]) if member_rows else [
        "donor_set_id",
        "member_id",
        "dataset_name",
        "contig_name",
        "source_start",
        "source_end",
        "orientation",
        "fasta_record_name",
        "sequence_sha256",
    ])
    if manifest_rows != member_rows:
        fail("frozen ordinary donor manifest differs from member registry")
    read_donor_fragments(
        server_dir,
        donor_set,
        member_rows,
        dict(read_fasta_allow_empty(donor_path)),
    )
    stage_rows = read_tsv(server_dir / "metadata/grt_stage_status.tsv", STAGE_FIELDS)
    donor_rows = [row for row in stage_rows if row["stage"] == "donor_freeze"]
    if len(donor_rows) != 1:
        fail("donor_freeze stage row is missing or duplicated")
    donor_freeze = donor_rows[0]
    checkpoint_path = server_dir / donor_freeze["checkpoint_relpath"]
    if (
        not checkpoint_path.is_file()
        or sha256_file(checkpoint_path) != donor_freeze["checkpoint_sha256"]
        or donor_freeze["donor_set_id"] != donor_set["donor_set_id"]
    ):
        fail("donor_freeze checkpoint identity is invalid")
    return donor_set, member_rows, donor_freeze
