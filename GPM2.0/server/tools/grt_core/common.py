from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

WORKFLOW = "gpm_grt_precomputed_v2"

SCHEMA_VERSION = "2"

FINAL_PATH_SCHEMA_VERSION = "1"

Q_GAP_LENGTH = 100

MIN_DONOR_LENGTH = 1_000

MIN_QV = 30.0

MIN_QC_LENGTH = 100_000

MIN_TELOMERE_BP = 500

DNA_ALPHABET = frozenset("ACGTRYSWKMBDHVN")

COMPLEMENT = str.maketrans(
    "ACGTRYSWKMBDHVN",
    "TGCAYRSWMKVHDBN",
)

Q_SEGMENT_FIELDS = [
    "q_version",
    "chr",
    "segment_id",
    "segment_kind",
    "q_start",
    "q_end",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "source_card_key",
    "evidence_ids_json",
]

DONOR_MEMBER_FIELDS = [
    "donor_set_id",
    "member_id",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "fasta_record_name",
    "sequence_sha256",
]

DONOR_FRAGMENT_FIELDS = [
    "donor_set_id",
    "member_id",
    "fragment_id",
    "fasta_record_name",
    "fragment_start",
    "fragment_end",
    "fragment_length",
    "sequence_sha256",
    "left_boundary",
    "right_boundary",
]

EVIDENCE_FIELDS = [
    "evidence_id",
    "stage",
    "evidence_type",
    "status",
    "q_version",
    "q_source_sha256",
    "query_artifact_relpath",
    "query_sha256",
    "donor_set_id",
    "target_artifact_relpath",
    "target_sha256",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "target_chr",
    "target_start",
    "target_end",
    "tool",
    "tool_version",
    "preset",
    "parameters_json",
    "raw_artifact_relpath",
    "raw_artifact_sha256",
    "coordinate_system",
    "projection_status",
]

CHR_ASSIGNMENT_FIELDS = [
    "dataset_name",
    "seq_name",
    "seq_length_bp",
    "assigned_chr_name",
    "source_orientation",
    "orientation_source",
    "support_bp",
    "support_percent",
    "anchor_start",
]

def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def compose_orientation(left: str, right: str) -> str:
    """Compose two canonical +/- orientations."""
    return "+" if left == right else "-"


def intervals_overlap(
    left_start: int,
    left_end: int,
    right_start: int,
    right_end: int,
) -> bool:
    return left_start <= right_end and right_start <= left_end


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def stable_id(prefix: str, value: object, length: int = 24) -> str:
    return f"{prefix}-{sha256_bytes(canonical_json(value).encode('utf-8'))[:length]}"

def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]

def donor_fragment_rows(
    donor_set_id: str,
    members: list[dict[str, str]],
    sequences: dict[tuple[str, str], str],
) -> list[dict[str, object]]:
    """Index D0 sequence fragments without changing the frozen donor FASTA.

    GRT treats long N-runs as fragment boundaries.  The fragment table is an
    index only: all repair candidates still point to the original D0 member,
    source coordinates and donor-set hash.
    """
    rows: list[dict[str, object]] = []
    for member in members:
        sequence = sequences[(member["dataset_name"], member["contig_name"])]
        intervals: list[tuple[int, int]] = []
        cursor = 0
        for match in re.finditer(r"N{100,}", sequence):
            if cursor < match.start():
                intervals.append((cursor, match.start()))
            cursor = match.end()
        if cursor < len(sequence):
            intervals.append((cursor, len(sequence)))
        for start0, end0 in intervals:
            fragment = sequence[start0:end0]
            fragment_start = start0 + 1
            fragment_end = end0
            fragment_id = stable_id(
                "d0-fragment",
                {
                    "donor_set_id": donor_set_id,
                    "member_id": member["member_id"],
                    "start": fragment_start,
                    "end": fragment_end,
                    "sequence_sha256": sha256_bytes(fragment.encode("ascii")),
                },
                20,
            )
            rows.append(
                {
                    "donor_set_id": donor_set_id,
                    "member_id": member["member_id"],
                    "fragment_id": fragment_id,
                    "fasta_record_name": member["fasta_record_name"],
                    "fragment_start": fragment_start,
                    "fragment_end": fragment_end,
                    "fragment_length": len(fragment),
                    "sequence_sha256": sha256_bytes(fragment.encode("ascii")),
                    "left_boundary": str(start0 == 0).lower(),
                    "right_boundary": str(end0 == len(sequence)).lower(),
                }
            )
    return rows

def read_tsv(path: Path, expected_header: list[str] | None = None) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"required TSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = list(reader.fieldnames or [])
        if expected_header is not None and header != expected_header:
            fail(f"unexpected header in {path}: expected {expected_header}, got {header}")
        return list(reader)

def read_key_values(path: Path) -> dict[str, str]:
    rows = read_tsv(path, ["key", "value"])
    return {row["key"]: row["value"] for row in rows}

def read_fasta(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        fail(f"FASTA is missing: {path}")
    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    name: str | None = None
    parts: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    records.append((name, "".join(parts).upper()))
                name = line[1:].split()[0]
                if not name or name in seen:
                    fail(f"empty or duplicate FASTA ID at {path}:{line_number}: {name!r}")
                seen.add(name)
                parts = []
            else:
                if name is None:
                    fail(f"sequence appears before FASTA header at {path}:{line_number}")
                parts.append(line)
    if name is not None:
        records.append((name, "".join(parts).upper()))
    if not records:
        fail(f"FASTA has no records: {path}")
    return records

def write_fasta(path: Path, records: Iterable[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")

def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def merged_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]

def intervals_cover(container: list[tuple[int, int]], subject: list[tuple[int, int]]) -> bool:
    if not subject:
        return False
    index = 0
    for start, end in subject:
        while index < len(container) and container[index][1] < start:
            index += 1
        if index == len(container) or container[index][0] > start or container[index][1] < end:
            return False
    return True

def path_hashes(paths: Iterable[Path], root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda value: value.as_posix())
    }

def executable_identity(command: str) -> dict[str, str]:
    resolved = shutil.which(command) if "/" not in command else str(Path(command).resolve())
    if not resolved or not Path(resolved).is_file() or not os.access(resolved, os.X_OK):
        fail(f"required executable is unavailable: {command}")
    version = "unknown"
    try:
        completed = subprocess.run(
            [resolved, "--version"], check=False, capture_output=True, text=True, timeout=10
        )
        text = (completed.stdout or completed.stderr).strip()
        if completed.returncode == 0 and text:
            version = text.splitlines()[0][:200]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "command": command,
        "resolved": str(Path(resolved).resolve()),
        "sha256": sha256_file(Path(resolved)),
        "version": version,
    }

def run_command(command: list[str], cwd: Path, log_prefix: Path) -> None:
    log_prefix.parent.mkdir(parents=True, exist_ok=True)
    log_prefix.with_suffix(".command.txt").write_text(
        shlex.join(command) + "\n", encoding="utf-8", newline=""
    )
    stdout_path = log_prefix.with_suffix(".stdout.log")
    stderr_path = log_prefix.with_suffix(".stderr.log")
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
    if completed.returncode != 0:
        fail(f"command failed ({completed.returncode}): {shlex.join(command)}")
