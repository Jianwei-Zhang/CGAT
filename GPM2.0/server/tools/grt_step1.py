#!/usr/bin/env python3

"""Run the two canonical AssembleFill rounds against one frozen GRT donor set."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from grt_prepare_inputs import (
    EVIDENCE_FIELDS,
    Q_SEGMENT_FIELDS,
    WORKFLOW,
    canonical_json,
    executable_identity,
    read_fasta,
    read_tsv,
    reverse_complement,
    sha256_bytes,
    sha256_file,
    stable_id,
    write_fasta,
    write_tsv,
)


ENGINE_VERSION = 1
MIN_GAP_LENGTH = 100
FLANK_LENGTH = 10_000
MIN_ALIGNMENT_LENGTH = 1_000
MIN_IDENTITY = 0.40
MAX_FILL_LENGTH = 1_000_000
MIN_COMPONENT_LENGTH = 100_000
FILTER_CONNECTOR_LENGTH = 100
PRESET = "asm5"

USAGE_FIELDS = [
    "usage_id",
    "donor_set_id",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "stage",
    "status",
    "event_id",
    "final_path_segment_id",
    "reason",
]
ATTEMPT_FIELDS = [
    "attempt_id",
    "chr",
    "object_id",
    "stage",
    "status",
    "reason",
    "candidate_count",
    "accepted_event_id",
]
STAGE_FIELDS = [
    "stage",
    "q_input_version",
    "q_input_sha256",
    "q_output_version",
    "q_output_sha256",
    "donor_set_id",
    "status",
    "checkpoint_relpath",
    "checkpoint_sha256",
]
TOOL_FIELDS = ["tool", "version", "executable"]
CANDIDATE_FIELDS = [
    "candidate_id",
    "stage",
    "chr",
    "object_id",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "trim_left",
    "trim_right",
    "fill_length",
    "identity",
    "aligned_length",
    "mapq",
    "left_paf_line",
    "right_paf_line",
]
ARBITRATION_FIELDS = CANDIDATE_FIELDS + ["outcome", "reason", "event_id", "final_path_segment_id"]
REJECTION_FIELDS = ["stage", "chr", "object_id", "left_paf_line", "right_paf_line", "reason"]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def read_single(path: Path, header: list[str] | None = None) -> dict[str, str]:
    rows = read_tsv(path, header)
    if len(rows) != 1:
        fail(f"{path} must contain exactly one row")
    return rows[0]


def read_fasta_allow_empty(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        fail(f"FASTA is missing: {path}")
    if path.stat().st_size == 0:
        return []
    return read_fasta(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def atomic_write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    write_tsv(temporary, fields, rows)
    os.replace(temporary, path)


def atomic_write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    write_jsonl(temporary, rows)
    os.replace(temporary, path)


def json_hash(value: object) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def source_catalog(server_dir: Path) -> dict[tuple[str, str], str]:
    datasets = read_tsv(
        server_dir / "metadata/datasets.tsv",
        [
            "dataset_name",
            "assembler",
            "assembler_version",
            "fasta_relpath",
            "fai_relpath",
            "self_alignment_available",
        ],
    )
    sources: dict[tuple[str, str], str] = {}
    for dataset in datasets:
        for name, sequence in read_fasta(server_dir / dataset["fasta_relpath"]):
            key = (dataset["dataset_name"], name)
            if key in sources:
                fail(f"duplicate source identity: {key[0]}:{key[1]}")
            sources[key] = sequence
    locator_keys = {
        (row["dataset_name"], row["seq_name"])
        for row in read_tsv(
            server_dir / "metadata/source_seq_locator.tsv",
            ["dataset_name", "seq_name", "fasta_relpath"],
        )
    }
    if locator_keys != set(sources):
        fail("source_seq_locator.tsv does not match the initial source catalog")
    return sources


def sequence_from_segment(segment: dict[str, object], sources: dict[tuple[str, str], str]) -> str:
    if segment["segment_kind"] == "gap":
        return "N" * int(segment["length"])
    key = (str(segment["dataset_name"]), str(segment["contig_name"]))
    sequence = sources[key][int(segment["source_start"]) - 1 : int(segment["source_end"])]
    return sequence if segment["orientation"] == "+" else reverse_complement(sequence)


def load_q_paths(
    server_dir: Path,
    q_version: str,
    q_rows: list[dict[str, str]],
    sources: dict[tuple[str, str], str],
) -> tuple[list[str], dict[str, list[dict[str, object]]], dict[str, str]]:
    q_records = read_fasta(server_dir / f"grt/q/{q_version}.fa")
    record_order = [name for name, _sequence in q_records]
    record_map = dict(q_records)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in q_rows:
        if row["q_version"] == q_version:
            grouped[row["chr"]].append(row)
    if set(grouped) != set(record_map):
        fail(f"q segment mapping does not cover every {q_version} record")
    paths: dict[str, list[dict[str, object]]] = {}
    for chromosome in record_order:
        expected_start = 1
        segments: list[dict[str, object]] = []
        for row in sorted(grouped[chromosome], key=lambda value: int(value["q_start"])):
            start = int(row["q_start"])
            end = int(row["q_end"])
            if start != expected_start or end < start:
                fail(f"non-contiguous {q_version} mapping for {chromosome}")
            evidence_ids = json.loads(row["evidence_ids_json"])
            if not isinstance(evidence_ids, list):
                fail(f"invalid evidence list for q segment {row['segment_id']}")
            segment: dict[str, object] = {
                "segment_kind": row["segment_kind"],
                "length": end - start + 1,
                "dataset_name": row["dataset_name"],
                "contig_name": row["contig_name"],
                "source_start": int(row["source_start"]) if row["source_start"] else None,
                "source_end": int(row["source_end"]) if row["source_end"] else None,
                "orientation": row["orientation"],
                "source_card_key": row["source_card_key"],
                "evidence_ids": evidence_ids,
            }
            expected = record_map[chromosome][start - 1 : end]
            if sequence_from_segment(segment, sources) != expected:
                fail(f"q segment {row['segment_id']} does not reconstruct {q_version}:{chromosome}")
            segments.append(segment)
            expected_start = end + 1
        if expected_start != len(record_map[chromosome]) + 1:
            fail(f"q segment mapping ends early for {q_version}:{chromosome}")
        paths[chromosome] = segments
    return record_order, paths, record_map


def slice_segment(segment: dict[str, object], left: int, right: int) -> dict[str, object]:
    length = int(segment["length"])
    if left < 0 or right > length or left >= right:
        fail("invalid q segment slice")
    result = dict(segment)
    result["evidence_ids"] = list(segment["evidence_ids"])
    result["length"] = right - left
    if segment["segment_kind"] == "source":
        if segment["orientation"] == "+":
            result["source_start"] = int(segment["source_start"]) + left
            result["source_end"] = int(segment["source_start"]) + right - 1
        else:
            result["source_start"] = int(segment["source_end"]) - right + 1
            result["source_end"] = int(segment["source_end"]) - left
    return result


def slice_path(path: list[dict[str, object]], start: int, end: int) -> list[dict[str, object]]:
    if start < 0 or end < start:
        fail("invalid q path interval")
    result: list[dict[str, object]] = []
    cursor = 0
    for segment in path:
        segment_end = cursor + int(segment["length"])
        overlap_start = max(start, cursor)
        overlap_end = min(end, segment_end)
        if overlap_start < overlap_end:
            result.append(slice_segment(segment, overlap_start - cursor, overlap_end - cursor))
        cursor = segment_end
    if end > cursor:
        fail("q path slice exceeds chromosome")
    return result


def path_sequence(path: list[dict[str, object]], sources: dict[tuple[str, str], str]) -> str:
    return "".join(sequence_from_segment(segment, sources) for segment in path)


def q_rows_for_paths(
    q_version: str,
    chromosome_order: list[str],
    paths: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        position = 1
        for index, segment in enumerate(paths[chromosome], start=1):
            length = int(segment["length"])
            identity = {
                "q_version": q_version,
                "chr": chromosome,
                "index": index,
                "kind": segment["segment_kind"],
                "length": length,
                "dataset": segment["dataset_name"],
                "contig": segment["contig_name"],
                "source_start": segment["source_start"],
                "source_end": segment["source_end"],
                "orientation": segment["orientation"],
                "evidence": segment["evidence_ids"],
            }
            rows.append(
                {
                    "q_version": q_version,
                    "chr": chromosome,
                    "segment_id": stable_id(f"{q_version}-segment", identity, 20),
                    "segment_kind": segment["segment_kind"],
                    "q_start": position,
                    "q_end": position + length - 1,
                    "dataset_name": segment["dataset_name"],
                    "contig_name": segment["contig_name"],
                    "source_start": "" if segment["source_start"] is None else segment["source_start"],
                    "source_end": "" if segment["source_end"] is None else segment["source_end"],
                    "orientation": segment["orientation"],
                    "source_card_key": segment["source_card_key"],
                    "evidence_ids_json": canonical_json(segment["evidence_ids"]),
                }
            )
            position += length
    return rows


def gap_objects(chromosome: str, q_version: str, sequence: str) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for index, match in enumerate(re.finditer(r"N{100,}", sequence), start=1):
        identity = {
            "q_version": q_version,
            "chr": chromosome,
            "index": index,
            "start": match.start() + 1,
            "end": match.end(),
            "sequence_sha256": sha256_bytes(match.group().encode("ascii")),
        }
        objects.append(
            {
                "chr": chromosome,
                "object_id": stable_id("gap", identity, 20),
                "start0": match.start(),
                "end0": match.end(),
                "index": index,
            }
        )
    return objects


def build_flanks(
    q_version: str,
    chromosome_order: list[str],
    records: dict[str, str],
) -> tuple[list[tuple[str, str]], list[dict[str, object]], dict[str, tuple[dict[str, object], str]]]:
    fasta_records: list[tuple[str, str]] = []
    gaps: list[dict[str, object]] = []
    query_map: dict[str, tuple[dict[str, object], str]] = {}
    for chromosome in chromosome_order:
        sequence = records[chromosome]
        for gap in gap_objects(chromosome, q_version, sequence):
            gap = dict(gap)
            left = sequence[max(0, int(gap["start0"]) - FLANK_LENGTH) : int(gap["start0"])]
            right = sequence[int(gap["end0"]) : min(len(sequence), int(gap["end0"]) + FLANK_LENGTH)]
            invalid_reason = ""
            if not left or not right:
                invalid_reason = "missing_terminal_flank"
            elif re.search(r"N{100,}", left) or re.search(r"N{100,}", right):
                invalid_reason = "neighbor_gap_in_flank"
            gap["invalid_flank_reason"] = invalid_reason
            gaps.append(gap)
            if invalid_reason:
                continue
            for side, flank in (("L", left), ("R", right)):
                query_name = f"flank__{gap['object_id']}__{side}"
                fasta_records.append((query_name, flank))
                query_map[query_name] = (gap, side)
    return fasta_records, gaps, query_map


def parse_paf(
    path: Path,
    query_map: dict[str, tuple[dict[str, object], str]],
    target_lengths: dict[str, int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                fail(f"invalid Step1 PAF row at {path}:{line_number}")
            if not any(field.startswith("cg:Z:") for field in fields[12:]):
                fail(f"Step1 PAF row lacks the required -c CIGAR tag at {path}:{line_number}")
            query, strand, target = fields[0], fields[4], fields[5]
            if query not in query_map:
                fail(f"Step1 PAF has unknown flank query at {path}:{line_number}: {query}")
            if target not in target_lengths:
                fail(f"Step1 PAF has unknown D0 target at {path}:{line_number}: {target}")
            if strand not in {"+", "-"}:
                fail(f"Step1 PAF has invalid strand at {path}:{line_number}")
            try:
                qlen, qstart, qend = map(int, (fields[1], fields[2], fields[3]))
                tlen, tstart, tend = map(int, (fields[6], fields[7], fields[8]))
                matches, block_length, mapq = map(int, (fields[9], fields[10], fields[11]))
            except ValueError:
                fail(f"Step1 PAF has non-integer core fields at {path}:{line_number}")
            if not (0 <= qstart < qend <= qlen and 0 <= tstart < tend <= tlen):
                fail(f"Step1 PAF has invalid coordinates at {path}:{line_number}")
            if tlen != target_lengths[target] or block_length < 1 or matches < 0 or matches > block_length:
                fail(f"Step1 PAF has inconsistent lengths at {path}:{line_number}")
            gap, side = query_map[query]
            rows.append(
                {
                    "line_number": line_number,
                    "raw": line,
                    "query": query,
                    "side": side,
                    "object_id": gap["object_id"],
                    "chr": gap["chr"],
                    "qlen": qlen,
                    "qstart": qstart,
                    "qend": qend,
                    "strand": strand,
                    "target": target,
                    "tstart": tstart,
                    "tend": tend,
                    "matches": matches,
                    "block_length": block_length,
                    "mapq": mapq,
                    "identity": matches / block_length,
                }
            )
    return rows


def compose_orientation(member_orientation: str, paf_strand: str) -> str:
    return member_orientation if paf_strand == "+" else ("-" if member_orientation == "+" else "+")


def member_source_interval(member: dict[str, str], local_start: int, local_end: int) -> tuple[int, int]:
    if member["orientation"] == "+":
        return int(member["source_start"]) + local_start - 1, int(member["source_start"]) + local_end - 1
    return int(member["source_end"]) - local_end + 1, int(member["source_end"]) - local_start + 1


def build_candidates(
    stage: str,
    paf_rows: list[dict[str, object]],
    gaps: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    donor_records: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    alignments: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    rejections: list[dict[str, object]] = []
    gap_by_id = {str(gap["object_id"]): gap for gap in gaps}
    for alignment in paf_rows:
        if int(alignment["block_length"]) < MIN_ALIGNMENT_LENGTH:
            rejections.append(
                {
                    "stage": stage,
                    "chr": alignment["chr"],
                    "object_id": alignment["object_id"],
                    "left_paf_line": alignment["line_number"] if alignment["side"] == "L" else "",
                    "right_paf_line": alignment["line_number"] if alignment["side"] == "R" else "",
                    "reason": "alignment_length_lt_1000",
                }
            )
            continue
        if float(alignment["identity"]) < MIN_IDENTITY:
            rejections.append(
                {
                    "stage": stage,
                    "chr": alignment["chr"],
                    "object_id": alignment["object_id"],
                    "left_paf_line": alignment["line_number"] if alignment["side"] == "L" else "",
                    "right_paf_line": alignment["line_number"] if alignment["side"] == "R" else "",
                    "reason": "alignment_identity_lt_0.40",
                }
            )
            continue
        alignments[(str(alignment["object_id"]), str(alignment["side"]))].append(alignment)
    candidates: list[dict[str, object]] = []
    for object_id, gap in gap_by_id.items():
        left_rows = alignments.get((object_id, "L"), [])
        right_rows = alignments.get((object_id, "R"), [])
        for left in left_rows:
            for right in right_rows:
                rejection = {
                    "stage": stage,
                    "chr": gap["chr"],
                    "object_id": object_id,
                    "left_paf_line": left["line_number"],
                    "right_paf_line": right["line_number"],
                    "reason": "",
                }
                if left["target"] != right["target"]:
                    rejection["reason"] = "anchors_on_different_donor_members"
                elif left["strand"] != right["strand"]:
                    rejection["reason"] = "anchor_strands_disagree"
                else:
                    lower, upper = (left, right) if left["strand"] == "+" else (right, left)
                    local_start = int(lower["tend"]) + 1
                    local_end = int(upper["tstart"])
                    if local_start > local_end:
                        rejection["reason"] = "empty_or_overlapping_donor_interval"
                    elif local_end - local_start + 1 > MAX_FILL_LENGTH:
                        rejection["reason"] = "fill_length_gt_1000000"
                    else:
                        donor_sequence = donor_records[str(left["target"])][local_start - 1 : local_end]
                        if re.search(r"N{100,}", donor_sequence):
                            rejection["reason"] = "donor_interval_crosses_unresolved_gap"
                        else:
                            member = members_by_record[str(left["target"])]
                            source_start, source_end = member_source_interval(member, local_start, local_end)
                            orientation = compose_orientation(member["orientation"], str(left["strand"]))
                            fill_sequence = (
                                donor_sequence
                                if left["strand"] == "+"
                                else reverse_complement(donor_sequence)
                            )
                            trim_left = int(left["qlen"]) - int(left["qend"])
                            trim_right = int(right["qstart"])
                            identity = (float(left["identity"]) + float(right["identity"])) / 2
                            payload = {
                                "stage": stage,
                                "object_id": object_id,
                                "member_id": member["member_id"],
                                "source_start": source_start,
                                "source_end": source_end,
                                "orientation": orientation,
                                "left_line": left["line_number"],
                                "right_line": right["line_number"],
                            }
                            candidates.append(
                                {
                                    "candidate_id": stable_id("candidate", payload, 24),
                                    "stage": stage,
                                    "chr": gap["chr"],
                                    "object_id": object_id,
                                    "target_start": int(gap["start0"]) + 1,
                                    "target_end": int(gap["end0"]),
                                    "member_id": member["member_id"],
                                    "source_dataset": member["dataset_name"],
                                    "source_contig": member["contig_name"],
                                    "source_start": source_start,
                                    "source_end": source_end,
                                    "orientation": orientation,
                                    "trim_left": trim_left,
                                    "trim_right": trim_right,
                                    "fill_length": len(fill_sequence),
                                    "fill_sequence": fill_sequence,
                                    "identity": identity,
                                    "aligned_length": int(left["block_length"]) + int(right["block_length"]),
                                    "mapq": min(int(left["mapq"]), int(right["mapq"])),
                                    "left_paf_line": left["line_number"],
                                    "right_paf_line": right["line_number"],
                                }
                            )
                            continue
                rejections.append(rejection)
    return candidates, rejections


def intervals_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return left_start <= right_end and right_start <= left_end


def arbitrate_candidates(
    candidates: list[dict[str, object]],
    consumed: list[dict[str, object]],
) -> list[dict[str, object]]:
    ordered = sorted(
        candidates,
        key=lambda row: (
            -float(row["identity"]),
            -int(row["aligned_length"]),
            -int(row["mapq"]),
            str(row["source_dataset"]),
            str(row["source_contig"]),
            int(row["source_start"]),
            int(row["source_end"]),
            str(row["chr"]),
            str(row["object_id"]),
            str(row["candidate_id"]),
        ),
    )
    accepted_gaps: set[str] = set()
    occupied = [dict(row) for row in consumed]
    for candidate in ordered:
        object_id = str(candidate["object_id"])
        if object_id in accepted_gaps:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "lower_ranked_candidate_for_gap"
            continue
        collision = next(
            (
                row
                for row in occupied
                if (row["source_dataset"], row["source_contig"])
                == (candidate["source_dataset"], candidate["source_contig"])
                and intervals_overlap(
                    int(row["source_start"]),
                    int(row["source_end"]),
                    int(candidate["source_start"]),
                    int(candidate["source_end"]),
                )
            ),
            None,
        )
        if collision is not None:
            candidate["outcome"] = "conflicted"
            candidate["reason"] = f"source_interval_consumed_by:{collision['candidate_id']}"
            continue
        candidate["outcome"] = "accepted"
        candidate["reason"] = "accepted_by_global_interval_arbitration"
        accepted_gaps.add(object_id)
        occupied.append(candidate)
    return ordered


def source_assignment(
    assignments: dict[tuple[str, str], object],
    candidate: dict[str, object],
) -> tuple[str, str, str]:
    key = (str(candidate["source_dataset"]), str(candidate["source_contig"]))
    target_chr = str(candidate["chr"])
    assigned_value = assignments.get(key)
    if assigned_value is None:
        assigned_chromosomes: set[str] = set()
    elif isinstance(assigned_value, str):
        assigned_chromosomes = {assigned_value}
    else:
        assigned_chromosomes = {str(value) for value in assigned_value}
    if not assigned_chromosomes:
        original_assignment = "unplaced"
        placement_mode = "grt_promoted"
    elif target_chr in assigned_chromosomes:
        original_assignment = "assigned"
        placement_mode = "normal"
    else:
        original_assignment = "cross_chr"
        placement_mode = "cross_chr_grt_usage"
    return original_assignment, placement_mode, f"{key[0]}:{key[1]}:{target_chr}:{placement_mode}"


def replay_round_records(
    input_records: dict[str, str],
    events: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
) -> dict[str, str]:
    accepted: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in events:
        if event["status"] in {"accepted", "superseded"}:
            accepted[str(event["chr"])].append(event)
    output: dict[str, str] = {}
    for chromosome, sequence in input_records.items():
        cursor = 0
        parts: list[str] = []
        for event in sorted(accepted.get(chromosome, []), key=lambda row: int(row["edit"]["input_start"])):
            edit = event["edit"]
            start = int(edit["input_start"]) - 1
            end = int(edit["input_end"])
            if start < cursor or end < start:
                fail(f"overlapping replay edits for {chromosome}")
            parts.append(sequence[cursor:start])
            source = event["source"]
            source_sequence = sources[(source["dataset"], source["contig"])][
                int(source["start"]) - 1 : int(source["end"])
            ]
            if source["orientation"] == "-":
                source_sequence = reverse_complement(source_sequence)
            if sha256_bytes(source_sequence.encode("ascii")) != edit["replacement_sequence_sha256"]:
                fail(f"event replacement hash mismatch during replay: {event['event_id']}")
            parts.append(source_sequence)
            cursor = end
        parts.append(sequence[cursor:])
        output[chromosome] = "".join(parts)
    return output


def apply_round(
    run_id: str,
    stage: str,
    q_input_version: str,
    q_output_version: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    assignments: dict[tuple[str, str], str],
    q_input_sha256: str,
    sources: dict[tuple[str, str], str],
    action: str = "fill",
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, str],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    candidates_by_gap: dict[str, list[dict[str, object]]] = defaultdict(list)
    accepted_by_gap: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        object_id = str(candidate["object_id"])
        candidates_by_gap[object_id].append(candidate)
        if candidate["outcome"] == "accepted":
            accepted_by_gap[object_id] = candidate

    output_paths: dict[str, list[dict[str, object]]] = {}
    output_records: dict[str, str] = {}
    event_prototypes: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        path = input_paths[chromosome]
        sequence = input_records[chromosome]
        chromosome_gaps = sorted(
            (gap for gap in gaps if gap["chr"] == chromosome),
            key=lambda gap: int(gap["start0"]),
        )
        cursor = 0
        output_cursor = 0
        result_path: list[dict[str, object]] = []
        for gap in chromosome_gaps:
            object_id = str(gap["object_id"])
            candidate = accepted_by_gap.get(object_id)
            if candidate is None:
                start0, end0 = int(gap["start0"]), int(gap["end0"])
                result_path.extend(slice_path(path, cursor, end0))
                output_start = output_cursor + (start0 - cursor) + 1
                output_end = output_start + (end0 - start0) - 1
                output_cursor += end0 - cursor
                cursor = end0
                related = candidates_by_gap.get(object_id, [])
                conflict = any(row["outcome"] == "conflicted" for row in related)
                if gap.get("invalid_flank_reason"):
                    reason = str(gap["invalid_flank_reason"])
                elif conflict:
                    reason = "all_valid_candidates_conflicted"
                elif related:
                    reason = "all_valid_candidates_rejected"
                else:
                    reason = "no_valid_candidate"
                event_prototypes.append(
                    {
                        "object_id": object_id,
                        "chr": chromosome,
                        "status": "conflicted" if conflict else "unresolved",
                        "reason": reason,
                        "q_before_start": start0 + 1,
                        "q_before_end": end0,
                        "q_after_start": output_start,
                        "q_after_end": output_end,
                        "source": None,
                        "source_card_key": "",
                        "final_path_segment_id": "",
                        "candidate": None,
                    }
                )
                continue
            before_end = int(gap["start0"]) - int(candidate["trim_left"])
            after_start = int(gap["end0"]) + int(candidate["trim_right"])
            if before_end < cursor or after_start > len(sequence) or before_end > int(gap["start0"]):
                fail(f"accepted candidate has invalid q trim interval: {candidate['candidate_id']}")
            result_path.extend(slice_path(path, cursor, before_end))
            output_cursor += before_end - cursor
            original_assignment, _placement_mode, source_card_key = source_assignment(assignments, candidate)
            evidence_id = stable_id("ev-step1", candidate["candidate_id"], 22)
            event_id = stable_id("event", [run_id, stage, object_id], 24)
            final_path_segment_id = stable_id("grt-segment", [event_id, candidate["candidate_id"]], 24)
            candidate["event_id"] = event_id
            candidate["final_path_segment_id"] = final_path_segment_id
            candidate["evidence_id"] = evidence_id
            candidate_evidence_ids = list(
                candidate.get("evidence_ids", [evidence_id])
            )
            donor_segment = {
                "segment_kind": "source",
                "length": int(candidate["fill_length"]),
                "dataset_name": candidate["source_dataset"],
                "contig_name": candidate["source_contig"],
                "source_start": int(candidate["source_start"]),
                "source_end": int(candidate["source_end"]),
                "orientation": candidate["orientation"],
                "source_card_key": source_card_key,
                "evidence_ids": candidate_evidence_ids,
            }
            if sequence_from_segment(donor_segment, sources) != candidate["fill_sequence"]:
                fail(f"accepted donor source projection mismatch: {candidate['candidate_id']}")
            result_path.append(donor_segment)
            output_start = output_cursor + 1
            output_end = output_start + int(candidate["fill_length"]) - 1
            output_cursor = output_end
            cursor = after_start
            source = {
                "dataset": candidate["source_dataset"],
                "contig": candidate["source_contig"],
                "start": int(candidate["source_start"]),
                "end": int(candidate["source_end"]),
                "orientation": candidate["orientation"],
                "original_assignment": original_assignment,
            }
            prototype = {
                "object_id": object_id,
                "chr": chromosome,
                "status": "accepted",
                "reason": "accepted_by_global_interval_arbitration",
                "q_before_start": before_end + 1,
                "q_before_end": after_start,
                "q_after_start": output_start,
                "q_after_end": output_end,
                "source": source,
                "source_card_key": source_card_key,
                "final_path_segment_id": final_path_segment_id,
                "candidate": candidate,
            }
            event_prototypes.append(prototype)
        result_path.extend(slice_path(path, cursor, len(sequence)))
        output_paths[chromosome] = result_path
        output_records[chromosome] = path_sequence(result_path, sources)

    q_output_bytes = bytearray()
    for chromosome in chromosome_order:
        q_output_bytes.extend(f">{chromosome}\n".encode("utf-8"))
        sequence = output_records[chromosome]
        for start in range(0, len(sequence), 80):
            q_output_bytes.extend((sequence[start : start + 80] + "\n").encode("utf-8"))
    q_output_sha256 = sha256_bytes(bytes(q_output_bytes))
    events: list[dict[str, object]] = []
    usage_rows: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    for prototype in event_prototypes:
        object_id = str(prototype["object_id"])
        candidate = prototype["candidate"]
        event_id = (
            str(candidate["event_id"])
            if candidate is not None
            else stable_id("event", [run_id, stage, object_id], 24)
        )
        related = candidates_by_gap.get(object_id, [])
        event_usage_ids: list[str] = []
        for row in related:
            candidate_usage_id = stable_id("usage-candidate", [stage, row["candidate_id"]], 22)
            usage_rows.append(
                {
                    "usage_id": candidate_usage_id,
                    "donor_set_id": "",
                    "member_id": row["member_id"],
                    "source_dataset": row["source_dataset"],
                    "source_contig": row["source_contig"],
                    "source_start": row["source_start"],
                    "source_end": row["source_end"],
                    "stage": stage,
                    "status": "candidate",
                    "event_id": event_id,
                    "final_path_segment_id": "",
                    "reason": "passed_pair_validation",
                }
            )
            outcome_usage_id = stable_id("usage-outcome", [stage, row["candidate_id"]], 22)
            outcome = str(row["outcome"])
            usage_rows.append(
                {
                    "usage_id": outcome_usage_id,
                    "donor_set_id": "",
                    "member_id": row["member_id"],
                    "source_dataset": row["source_dataset"],
                    "source_contig": row["source_contig"],
                    "source_start": row["source_start"],
                    "source_end": row["source_end"],
                    "stage": stage,
                    "status": "consumed" if outcome == "accepted" else outcome,
                    "event_id": event_id,
                    "final_path_segment_id": row.get("final_path_segment_id", ""),
                    "reason": row["reason"],
                }
            )
            event_usage_ids.extend([candidate_usage_id, outcome_usage_id])
        evidence_ids = sorted(
            {
                str(evidence_id)
                for row in related
                for evidence_id in row.get(
                    "evidence_ids",
                    [row["evidence_id"]] if row.get("evidence_id") else [],
                )
            }
        )
        event = {
            "run_id": run_id,
            "event_id": event_id,
            "stage": stage,
            "chr": prototype["chr"],
            "object_id": object_id,
            "action": action,
            "status": prototype["status"],
            "reason": prototype["reason"],
            "q_before": {
                "version": q_input_version,
                "start": prototype["q_before_start"],
                "end": prototype["q_before_end"],
                "sha256": q_input_sha256,
            },
            "q_after": {
                "version": q_output_version,
                "start": prototype["q_after_start"],
                "end": prototype["q_after_end"],
                "sha256": q_output_sha256,
            },
            "source": prototype["source"],
            "evidence_ids": evidence_ids,
            "usage_ids": event_usage_ids,
            "source_card_key": prototype["source_card_key"],
            "final_path_segment_id": prototype["final_path_segment_id"],
        }
        if candidate is not None:
            event["edit"] = {
                "operation": "replace_interval",
                "replacement_kind": "source",
                "input_start": prototype["q_before_start"],
                "input_end": prototype["q_before_end"],
                "trim_left": candidate["trim_left"],
                "trim_right": candidate["trim_right"],
                "replacement_sequence_sha256": sha256_bytes(str(candidate["fill_sequence"]).encode("ascii")),
            }
        events.append(event)
        attempts.append(
            {
                "attempt_id": stable_id("attempt", [run_id, stage, object_id], 22),
                "chr": prototype["chr"],
                "object_id": object_id,
                "stage": stage,
                "status": prototype["status"],
                "reason": prototype["reason"],
                "candidate_count": len(related),
                "accepted_event_id": event_id if prototype["status"] == "accepted" else "",
            }
        )
    if replay_round_records(input_records, events, sources) != output_records:
        fail(f"{stage} events do not deterministically reconstruct {q_output_version}")
    return output_paths, output_records, events, usage_rows, attempts


def replay_filter_records(
    input_records: dict[str, str],
    events: list[dict[str, object]],
) -> dict[str, str]:
    event_by_chr = {str(event["chr"]): event for event in events}
    output: dict[str, str] = {}
    for chromosome, sequence in input_records.items():
        event = event_by_chr[chromosome]
        if event["status"] != "accepted":
            output[chromosome] = sequence
            continue
        kept = event["edit"]["kept_intervals"]
        output[chromosome] = ("N" * int(event["edit"]["connector_length"])).join(
            sequence[int(interval[0]) - 1 : int(interval[1])] for interval in kept
        )
    return output


def apply_filter(
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    q_input_sha256: str,
    sources: dict[tuple[str, str], str],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, str], list[dict[str, object]]]:
    output_paths: dict[str, list[dict[str, object]]] = {}
    output_records: dict[str, str] = {}
    prototypes: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        sequence = input_records[chromosome]
        gaps = list(re.finditer(r"N{100,}", sequence))
        if not gaps:
            output_paths[chromosome] = [dict(segment) for segment in input_paths[chromosome]]
            output_records[chromosome] = sequence
            prototypes.append(
                {
                    "chr": chromosome,
                    "status": "unresolved",
                    "reason": "no_isolated_components",
                    "kept": [[1, len(sequence)]],
                    "removed": [],
                }
            )
            continue
        components: list[tuple[int, int]] = []
        cursor = 0
        for gap in gaps:
            if cursor < gap.start():
                components.append((cursor, gap.start()))
            cursor = gap.end()
        if cursor < len(sequence):
            components.append((cursor, len(sequence)))
        kept0 = [interval for interval in components if interval[1] - interval[0] >= MIN_COMPONENT_LENGTH]
        removed0 = [interval for interval in components if interval[1] - interval[0] < MIN_COMPONENT_LENGTH]
        if not kept0:
            output_paths[chromosome] = [dict(segment) for segment in input_paths[chromosome]]
            output_records[chromosome] = sequence
            prototypes.append(
                {
                    "chr": chromosome,
                    "status": "rejected",
                    "reason": "filter_would_remove_entire_chromosome",
                    "kept": [[1, len(sequence)]],
                    "removed": [[start + 1, end] for start, end in removed0],
                }
            )
            continue
        if not removed0:
            output_paths[chromosome] = [dict(segment) for segment in input_paths[chromosome]]
            output_records[chromosome] = sequence
            prototypes.append(
                {
                    "chr": chromosome,
                    "status": "unresolved",
                    "reason": "no_component_lt_100000",
                    "kept": [[start + 1, end] for start, end in kept0],
                    "removed": [],
                }
            )
            continue
        filtered_path: list[dict[str, object]] = []
        for index, (start, end) in enumerate(kept0):
            if index:
                filtered_path.append(
                    {
                        "segment_kind": "gap",
                        "length": FILTER_CONNECTOR_LENGTH,
                        "dataset_name": "",
                        "contig_name": "",
                        "source_start": None,
                        "source_end": None,
                        "orientation": "",
                        "source_card_key": "",
                        "evidence_ids": [],
                    }
                )
            filtered_path.extend(slice_path(input_paths[chromosome], start, end))
        output_paths[chromosome] = filtered_path
        output_records[chromosome] = path_sequence(filtered_path, sources)
        prototypes.append(
            {
                "chr": chromosome,
                "status": "accepted",
                "reason": f"removed_{len(removed0)}_isolated_components_lt_100000",
                "kept": [[start + 1, end] for start, end in kept0],
                "removed": [[start + 1, end] for start, end in removed0],
            }
        )
    q_output_bytes = bytearray()
    for chromosome in chromosome_order:
        q_output_bytes.extend(f">{chromosome}\n".encode("utf-8"))
        for start in range(0, len(output_records[chromosome]), 80):
            q_output_bytes.extend((output_records[chromosome][start : start + 80] + "\n").encode("utf-8"))
    q_output_sha256 = sha256_bytes(bytes(q_output_bytes))
    events: list[dict[str, object]] = []
    for prototype in prototypes:
        chromosome = str(prototype["chr"])
        object_id = stable_id(
            "component-filter",
            [run_id, chromosome, prototype["kept"], prototype["removed"]],
            22,
        )
        events.append(
            {
                "run_id": run_id,
                "event_id": stable_id("event", [run_id, "step1_filter", object_id], 24),
                "stage": "step1_filter",
                "chr": chromosome,
                "object_id": object_id,
                "action": "filter_component",
                "status": prototype["status"],
                "reason": prototype["reason"],
                "q_before": {
                    "version": "q0r1",
                    "start": 1,
                    "end": len(input_records[chromosome]),
                    "sha256": q_input_sha256,
                },
                "q_after": {
                    "version": "q0f",
                    "start": 1,
                    "end": len(output_records[chromosome]),
                    "sha256": q_output_sha256,
                },
                "source": None,
                "evidence_ids": [],
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "edit": {
                    "operation": "retain_components",
                    "kept_intervals": prototype["kept"],
                    "removed_intervals": prototype["removed"],
                    "min_component_length": MIN_COMPONENT_LENGTH,
                    "connector_length": FILTER_CONNECTOR_LENGTH,
                },
            }
        )
    if replay_filter_records(input_records, events) != output_records:
        fail("step1_filter events do not deterministically reconstruct q0f")
    return output_paths, output_records, events


def reconcile_filtered_round1_events(
    round1: dict[str, object],
    filter_result: dict[str, object],
) -> None:
    removed_by_chr: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for filter_event in filter_result["events"]:
        if filter_event["status"] != "accepted":
            continue
        for start, end in filter_event["edit"]["removed_intervals"]:
            removed_by_chr[str(filter_event["chr"])].append(
                (int(start), int(end), str(filter_event["event_id"]))
            )
    evidence_to_filter: dict[str, str] = {}
    for row in round1["q_rows"]:
        chromosome = str(row["chr"])
        for removed_start, removed_end, filter_event_id in removed_by_chr.get(chromosome, []):
            if not intervals_overlap(
                int(row["q_start"]),
                int(row["q_end"]),
                removed_start,
                removed_end,
            ):
                continue
            for evidence_id in json.loads(str(row["evidence_ids_json"])):
                evidence_to_filter[str(evidence_id)] = filter_event_id
    superseded_events: dict[str, str] = {}
    for event in round1["events"]:
        if event["status"] != "accepted":
            continue
        filter_event_id = next(
            (
                evidence_to_filter[str(evidence_id)]
                for evidence_id in event["evidence_ids"]
                if str(evidence_id) in evidence_to_filter
            ),
            None,
        )
        if filter_event_id is None:
            continue
        event["status"] = "superseded"
        event["reason"] = "accepted_then_removed_by_step1_filter"
        event["superseded_by_event_id"] = filter_event_id
        event["final_path_segment_id"] = ""
        superseded_events[str(event["event_id"])] = filter_event_id
    if not superseded_events:
        return
    for row in round1["evidence_rows"]:
        if row["status"] == "accepted" and any(
            row["evidence_id"] in event["evidence_ids"]
            for event in round1["events"]
            if event["event_id"] in superseded_events
        ):
            row["status"] = "superseded"
    for row in round1["usage_rows"]:
        if row["event_id"] not in superseded_events:
            continue
        if row["status"] == "consumed":
            row["status"] = "superseded"
        row["final_path_segment_id"] = ""
        row["reason"] = "accepted_then_removed_by_step1_filter"
    for filter_event in filter_result["events"]:
        event_ids = sorted(
            event_id
            for event_id, filter_event_id in superseded_events.items()
            if filter_event_id == filter_event["event_id"]
        )
        if event_ids:
            filter_event["superseded_event_ids"] = event_ids


def candidate_public_row(candidate: dict[str, object]) -> dict[str, object]:
    row = {field: candidate.get(field, "") for field in CANDIDATE_FIELDS}
    row["identity"] = f"{float(candidate['identity']):.9f}"
    return row


def stage_evidence_rows(
    stage: str,
    q_input_version: str,
    q_input_sha256: str,
    donor_set: dict[str, str],
    tool: dict[str, str],
    artifact_identity_by_chr: dict[str, dict[str, str]],
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    parameters = {
        "flank_length": FLANK_LENGTH,
        "min_gap_length": MIN_GAP_LENGTH,
        "min_alignment_length": MIN_ALIGNMENT_LENGTH,
        "min_identity": MIN_IDENTITY,
        "max_fill_length": MAX_FILL_LENGTH,
        "preset": PRESET,
        "cigar": True,
    }
    for candidate in candidates:
        artifacts = artifact_identity_by_chr[str(candidate["chr"])]
        evidence_id = stable_id("ev-step1", candidate["candidate_id"], 22)
        candidate["evidence_id"] = evidence_id
        rows.append(
            {
                "evidence_id": evidence_id,
                "stage": stage,
                "evidence_type": "flank_pair_alignment",
                "status": candidate["outcome"],
                "q_version": q_input_version,
                "q_source_sha256": q_input_sha256,
                "query_artifact_relpath": artifacts["query_relpath"],
                "query_sha256": artifacts["query_sha256"],
                "donor_set_id": donor_set["donor_set_id"],
                "target_artifact_relpath": donor_set["fasta_relpath"],
                "target_sha256": donor_set["fasta_sha256"],
                "source_dataset": candidate["source_dataset"],
                "source_contig": candidate["source_contig"],
                "source_start": candidate["source_start"],
                "source_end": candidate["source_end"],
                "orientation": candidate["orientation"],
                "target_chr": candidate["chr"],
                "target_start": candidate["target_start"],
                "target_end": candidate["target_end"],
                "tool": "minimap2",
                "tool_version": tool["version"],
                "preset": PRESET,
                "parameters_json": canonical_json(parameters),
                "raw_artifact_relpath": artifacts["raw_relpath"],
                "raw_artifact_sha256": artifacts["raw_sha256"],
                "coordinate_system": "paf_0_based_half_open",
                "projection_status": "projected",
            }
        )
    return rows


def fasta_bytes(records: Iterable[tuple[str, str]]) -> bytes:
    payload = bytearray()
    for name, sequence in records:
        payload.extend(f">{name}\n".encode("utf-8"))
        for start in range(0, len(sequence), 80):
            payload.extend((sequence[start : start + 80] + "\n").encode("utf-8"))
    return bytes(payload)


def checkpoint_result(
    server_dir: Path,
    stage: str,
    fingerprint: str,
) -> dict[str, object] | None:
    checkpoint_path = server_dir / f"grt/checkpoints/{stage}.json"
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("workflow") != WORKFLOW or checkpoint.get("stage") != stage:
            return None
        if checkpoint.get("status") != "success" or checkpoint.get("input_fingerprint") != fingerprint:
            return None
        output_hashes = checkpoint.get("output_hashes")
        if not isinstance(output_hashes, dict) or not output_hashes:
            return None
        for relpath, expected_hash in output_hashes.items():
            path = server_dir / relpath
            if not path.is_file() or sha256_file(path) != expected_hash:
                return None
        result_path = server_dir / str(checkpoint["result_relpath"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("stage") != stage or result.get("input_fingerprint") != fingerprint:
            return None
        return result
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def commit_stage_directory(temporary: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    os.replace(temporary, destination)


def invalidate_from(server_dir: Path, stage: str) -> None:
    order = ["step1_round1", "step1_filter", "step1_round2"]
    q_outputs = {
        "step1_round1": "q0r1",
        "step1_filter": "q0f",
        "step1_round2": "q1",
    }
    artifact_paths = {
        "step1_round1": server_dir / "grt/evidence/step1/round1",
        "step1_filter": server_dir / "grt/evidence/step1/filter",
        "step1_round2": server_dir / "grt/evidence/step1/round2",
    }
    start = order.index(stage)
    for invalid_stage in order[start:]:
        checkpoint = server_dir / f"grt/checkpoints/{invalid_stage}.json"
        checkpoint.unlink(missing_ok=True)
        q_path = server_dir / f"grt/q/{q_outputs[invalid_stage]}.fa"
        q_path.unlink(missing_ok=True)
        artifact = artifact_paths[invalid_stage]
        if artifact.is_dir():
            shutil.rmtree(artifact)
    for downstream_stage, q_output in (
        ("step2", "q2"),
        ("step3", "q3"),
        ("step4_telomere", "q4"),
        ("finalize", ""),
    ):
        (server_dir / f"grt/checkpoints/{downstream_stage}.json").unlink(missing_ok=True)
        if q_output:
            (server_dir / f"grt/q/{q_output}.fa").unlink(missing_ok=True)
    for downstream_artifact in ("step2", "step3", "step4_telomere"):
        path = server_dir / f"grt/evidence/{downstream_artifact}"
        if path.is_dir():
            shutil.rmtree(path)
    (server_dir / "metadata/grt_final_path.json").unlink(missing_ok=True)


def write_checkpoint(
    server_dir: Path,
    stage: str,
    fingerprint: str,
    fingerprint_payload: dict[str, object],
    result_relpath: str,
    output_relpaths: list[str],
) -> Path:
    checkpoint_path = server_dir / f"grt/checkpoints/{stage}.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "status": "success",
        "input_fingerprint": fingerprint,
        "fingerprint_payload": fingerprint_payload,
        "result_relpath": result_relpath,
        "output_hashes": {
            relpath: sha256_file(server_dir / relpath) for relpath in sorted(output_relpaths)
        },
    }
    temporary = checkpoint_path.with_name(f".{checkpoint_path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    os.replace(temporary, checkpoint_path)
    return checkpoint_path


def run_minimap(
    executable: str,
    threads: int,
    donor_fasta: Path,
    flank_fasta: Path,
    paf_path: Path,
    stage_dir: Path,
) -> None:
    command = [
        executable,
        "-x",
        PRESET,
        "-t",
        str(threads),
        "-c",
        "-o",
        str(paf_path),
        str(donor_fasta),
        str(flank_fasta),
    ]
    (stage_dir / "command.txt").write_text(shlex.join(command) + "\n", encoding="utf-8", newline="")
    with (stage_dir / "stdout.log").open("w", encoding="utf-8", newline="") as stdout_handle, (
        stage_dir / "stderr.log"
    ).open("w", encoding="utf-8", newline="") as stderr_handle:
        completed = subprocess.run(command, stdout=stdout_handle, stderr=stderr_handle, check=False)
    if completed.returncode != 0:
        fail(
            f"minimap2 failed for {stage_dir.name} with exit code {completed.returncode}; "
            f"command={stage_dir / 'command.txt'}, stderr={stage_dir / 'stderr.log'}"
        )
    if not paf_path.is_file():
        fail(f"minimap2 did not create the expected PAF: {paf_path}")


def cached_chromosome_alignment(
    server_dir: Path,
    stage: str,
    chromosome: str,
    q_input_sha256: str,
    q_chromosome_sha256: str,
    q_segment_rows: list[dict[str, object]],
    flank_records: list[tuple[str, str]],
    query_map: dict[str, tuple[dict[str, object], str]],
    donor_set: dict[str, str],
    donor_has_records: bool,
    target_lengths: dict[str, int],
    minimap: dict[str, str],
    parameters: dict[str, object],
    threads: int,
    cache_scope: str = "step1",
) -> tuple[Path, bool, str]:
    flank_payload = fasta_bytes(flank_records)
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "chr": chromosome,
        "q_source_sha256": q_input_sha256,
        "q_chromosome_sha256": q_chromosome_sha256,
        "q_segments_sha256": json_hash(q_segment_rows),
        "flank_query_sha256": sha256_bytes(flank_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tool": minimap,
        "parameters": parameters,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/{cache_scope}/{stage}/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            output_hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("input_fingerprint") == fingerprint
                and checkpoint.get("status") == "success"
                and output_hashes
                and all(
                    (cache_dir / name).is_file()
                    and sha256_file(cache_dir / name) == expected_hash
                    for name, expected_hash in output_hashes.items()
                )
            ):
                try:
                    parse_paf(cache_dir / "result.paf", query_map, target_lengths)
                    return cache_dir, True, chromosome_key
                except SystemExit:
                    pass
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        flank_path = temporary / "flanks.fa"
        flank_path.write_bytes(flank_payload)
        paf_path = temporary / "result.paf"
        if flank_records and donor_has_records:
            run_minimap(
                str(minimap["resolved"]),
                threads,
                server_dir / donor_set["fasta_relpath"],
                flank_path,
                paf_path,
                temporary,
            )
        else:
            paf_path.write_bytes(b"")
            (temporary / "command.txt").write_text(
                "skipped: chromosome has no valid flank query or frozen D0 is empty\n",
                encoding="utf-8",
                newline="",
            )
            (temporary / "stdout.log").write_text("", encoding="utf-8")
            (temporary / "stderr.log").write_text("", encoding="utf-8")
        parse_paf(paf_path, query_map, target_lengths)
        output_names = ["flanks.fa", "result.paf", "command.txt", "stdout.log", "stderr.log"]
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": stage,
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {
                name: sha256_file(temporary / name) for name in output_names
            },
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        return cache_dir, False, chromosome_key
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def round_artifact_relpath(stage: str) -> str:
    return "grt/evidence/step1/round1" if stage == "step1_round1" else "grt/evidence/step1/round2"


def run_round_stage(
    server_dir: Path,
    run_id: str,
    stage: str,
    q_input_version: str,
    q_output_version: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    consumed: list[dict[str, object]],
    minimap: dict[str, str],
    threads: int,
) -> tuple[dict[str, object], bool]:
    q_input_path = server_dir / f"grt/q/{q_input_version}.fa"
    q_input_sha256 = sha256_file(q_input_path)
    flank_records, gaps, query_map = build_flanks(q_input_version, chromosome_order, input_records)
    flank_payload = fasta_bytes(flank_records)
    flank_sha256 = sha256_bytes(flank_payload)
    parameters = {
        "preset": PRESET,
        "cigar": True,
        "threads": threads,
        "flank_length": FLANK_LENGTH,
        "min_gap_length": MIN_GAP_LENGTH,
        "min_alignment_length": MIN_ALIGNMENT_LENGTH,
        "min_identity": MIN_IDENTITY,
        "max_fill_length": MAX_FILL_LENGTH,
        "arbitration": "identity,aligned_length,mapq,source_identity,source_interval,target_gap",
    }
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "q_version": q_input_version,
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "flank_query_sha256": flank_sha256,
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tool": minimap,
        "parameters": parameters,
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT {stage} cache hit: {fingerprint}")
        return cached, True

    invalidate_from(server_dir, stage)

    artifact_relpath = round_artifact_relpath(stage)
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage}.", dir=artifact_dir.parent))
    try:
        flank_path = temporary / "flanks.fa"
        flank_path.write_bytes(flank_payload)
        paf_path = temporary / "result.paf"
        donor_path = server_dir / donor_set["fasta_relpath"]
        donor_records = dict(read_fasta_allow_empty(donor_path))
        members_by_record = {row["fasta_record_name"]: row for row in donor_members}
        if set(donor_records) != set(members_by_record):
            fail("ordinary D0 FASTA records differ from its frozen member manifest")
        artifact_identity_by_chr: dict[str, dict[str, str]] = {}
        chromosome_task_rows: list[dict[str, object]] = []
        paf_parts: list[bytes] = []
        paf_rows: list[dict[str, object]] = []
        for chromosome in chromosome_order:
            chromosome_flanks = [
                (name, sequence)
                for name, sequence in flank_records
                if query_map[name][0]["chr"] == chromosome
            ]
            chromosome_q_rows = [
                row for row in input_q_rows if row["chr"] == chromosome
            ]
            chromosome_query_map = {
                name: query_map[name] for name, _sequence in chromosome_flanks
            }
            target_lengths = {
                name: len(sequence) for name, sequence in donor_records.items()
            }
            cache_dir, cache_hit, chromosome_key = cached_chromosome_alignment(
                server_dir,
                stage,
                chromosome,
                q_input_sha256,
                sha256_bytes(input_records[chromosome].encode("ascii")),
                chromosome_q_rows,
                chromosome_flanks,
                chromosome_query_map,
                donor_set,
                bool(donor_records),
                target_lengths,
                minimap,
                parameters,
                threads,
            )
            print(
                f"GRT {stage} chromosome {chromosome}: "
                f"{'cache hit' if cache_hit else 'computed'}"
            )
            chromosome_artifact = temporary / "by_chr" / chromosome_key
            chromosome_artifact.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_dir, chromosome_artifact)
            chromosome_paf = chromosome_artifact / "result.paf"
            paf_parts.append(chromosome_paf.read_bytes())
            paf_rows.extend(
                parse_paf(chromosome_paf, chromosome_query_map, target_lengths)
            )
            query_relpath = f"{artifact_relpath}/by_chr/{chromosome_key}/flanks.fa"
            raw_relpath = f"{artifact_relpath}/by_chr/{chromosome_key}/result.paf"
            artifact_identity_by_chr[chromosome] = {
                "query_relpath": query_relpath,
                "query_sha256": sha256_file(chromosome_artifact / "flanks.fa"),
                "raw_relpath": raw_relpath,
                "raw_sha256": sha256_file(chromosome_paf),
            }
            chromosome_task_rows.append(
                {
                    "chr": chromosome,
                    "chromosome_key": chromosome_key,
                    "cache_key": cache_dir.name,
                    "query_relpath": query_relpath,
                    "query_sha256": artifact_identity_by_chr[chromosome]["query_sha256"],
                    "raw_relpath": raw_relpath,
                    "raw_sha256": artifact_identity_by_chr[chromosome]["raw_sha256"],
                }
            )
        paf_path.write_bytes(b"".join(paf_parts))
        write_tsv(
            temporary / "chromosome_tasks.tsv",
            [
                "chr",
                "chromosome_key",
                "cache_key",
                "query_relpath",
                "query_sha256",
                "raw_relpath",
                "raw_sha256",
            ],
            chromosome_task_rows,
        )
        candidates, rejections = build_candidates(
            stage, paf_rows, gaps, members_by_record, donor_records
        )
        candidates = arbitrate_candidates(candidates, consumed)
        query_relpath = f"{artifact_relpath}/flanks.fa"
        raw_relpath = f"{artifact_relpath}/result.paf"
        evidence_rows = stage_evidence_rows(
            stage,
            q_input_version,
            q_input_sha256,
            donor_set,
            minimap,
            artifact_identity_by_chr,
            candidates,
        )
        output_paths, output_records, events, usage_rows, attempts = apply_round(
            run_id,
            stage,
            q_input_version,
            q_output_version,
            chromosome_order,
            input_paths,
            input_records,
            gaps,
            candidates,
            assignments,
            q_input_sha256,
            sources,
        )
        for row in usage_rows:
            row["donor_set_id"] = donor_set["donor_set_id"]
        q_rows = q_rows_for_paths(q_output_version, chromosome_order, output_paths)
        q_output_temporary = server_dir / f"grt/q/.{q_output_version}.fa.tmp.{os.getpid()}"
        write_fasta(
            q_output_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail(f"internal {stage} q output hash disagreement")
        write_tsv(temporary / "candidates.tsv", CANDIDATE_FIELDS, [candidate_public_row(row) for row in candidates])
        write_tsv(temporary / "rejections.tsv", REJECTION_FIELDS, rejections)
        write_tsv(
            temporary / "arbitration.tsv",
            ARBITRATION_FIELDS,
            [
                {
                    **candidate_public_row(row),
                    "outcome": row["outcome"],
                    "reason": row["reason"],
                    "event_id": row.get("event_id", ""),
                    "final_path_segment_id": row.get("final_path_segment_id", ""),
                }
                for row in candidates
            ],
        )
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_jsonl(temporary / "events.jsonl", events)
        accepted_intervals = [
            {
                "candidate_id": row["candidate_id"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "stage": stage,
            }
            for row in candidates
            if row["outcome"] == "accepted"
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": q_input_version,
            "q_input_sha256": q_input_sha256,
            "q_output_version": q_output_version,
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "query_sha256": flank_sha256,
            "target_sha256": donor_set["fasta_sha256"],
            "q_rows": q_rows,
            "evidence_rows": evidence_rows,
            "usage_rows": usage_rows,
            "events": events,
            "attempts": attempts,
            "accepted_intervals": accepted_intervals,
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        (server_dir / "grt/q").mkdir(parents=True, exist_ok=True)
        os.replace(q_output_temporary, server_dir / f"grt/q/{q_output_version}.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix()
            for path in artifact_dir.rglob("*")
            if path.is_file()
        ] + [f"grt/q/{q_output_version}.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            f"GRT {stage} complete: gaps={len(gaps)}, candidates={len(candidates)}, "
            f"accepted={len(accepted_intervals)}"
        )
        return result, False
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def run_filter_stage(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
    donor_set_id: str,
) -> tuple[dict[str, object], bool]:
    stage = "step1_filter"
    q_input_sha256 = sha256_file(server_dir / "grt/q/q0r1.fa")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "q_version": "q0r1",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "min_component_length": MIN_COMPONENT_LENGTH,
        "connector_length": FILTER_CONNECTOR_LENGTH,
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT {stage} cache hit: {fingerprint}")
        return cached, True
    invalidate_from(server_dir, stage)
    artifact_relpath = "grt/evidence/step1/filter"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage}.", dir=artifact_dir.parent))
    try:
        output_paths, output_records, events = apply_filter(
            run_id,
            chromosome_order,
            input_paths,
            input_records,
            q_input_sha256,
            sources,
        )
        q_rows = q_rows_for_paths("q0f", chromosome_order, output_paths)
        q_output_temporary = server_dir / f"grt/q/.q0f.fa.tmp.{os.getpid()}"
        write_fasta(
            q_output_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail("internal step1_filter q output hash disagreement")
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_jsonl(temporary / "events.jsonl", events)
        write_tsv(
            temporary / "components.tsv",
            ["chr", "status", "reason", "kept_intervals_json", "removed_intervals_json"],
            [
                {
                    "chr": event["chr"],
                    "status": event["status"],
                    "reason": event["reason"],
                    "kept_intervals_json": canonical_json(event["edit"]["kept_intervals"]),
                    "removed_intervals_json": canonical_json(event["edit"]["removed_intervals"]),
                }
                for event in events
            ],
        )
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": "q0r1",
            "q_input_sha256": q_input_sha256,
            "q_output_version": "q0f",
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set_id,
            "q_rows": q_rows,
            "evidence_rows": [],
            "usage_rows": [],
            "events": events,
            "attempts": [],
            "accepted_intervals": [],
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q_output_temporary, server_dir / "grt/q/q0f.fa")
        output_relpaths = [
            f"{artifact_relpath}/{path.name}" for path in artifact_dir.iterdir() if path.is_file()
        ] + ["grt/q/q0f.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        removed = sum(len(event["edit"]["removed_intervals"]) for event in events if event["status"] == "accepted")
        print(f"GRT step1_filter complete: removed_components={removed}")
        return result, False
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


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


def publish_metadata(
    server_dir: Path,
    base_q_rows: list[dict[str, str]],
    base_evidence_rows: list[dict[str, str]],
    donor_freeze_row: dict[str, str],
    base_tool_rows: list[dict[str, str]],
    minimap: dict[str, str],
    results: list[dict[str, object]],
) -> None:
    metadata = server_dir / "metadata"
    q_rows: list[dict[str, object]] = list(base_q_rows)
    evidence_rows: list[dict[str, object]] = list(base_evidence_rows)
    usage_rows: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    stage_rows: list[dict[str, object]] = [donor_freeze_row]
    for result in results:
        q_rows.extend(result["q_rows"])
        evidence_rows.extend(result["evidence_rows"])
        usage_rows.extend(result["usage_rows"])
        events.extend(result["events"])
        attempts.extend(result["attempts"])
        stage_rows.append(stage_status_row(server_dir, result))
    tool_rows = [
        row
        for row in base_tool_rows
        if row["tool"] not in {"grt_step1", "step1_minimap2"}
    ]
    if results:
        tool_rows.extend(
            [
                {
                    "tool": "grt_step1",
                    "version": str(ENGINE_VERSION),
                    "executable": ".prepare_lib/tools/grt_step1.py",
                },
                {
                    "tool": "step1_minimap2",
                    "version": minimap["version"],
                    "executable": minimap["resolved"],
                },
            ]
        )
    atomic_write_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS, usage_rows)
    atomic_write_jsonl(metadata / "grt_events.jsonl", events)
    atomic_write_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
    atomic_write_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS, stage_rows)
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)


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


def execute(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != "1"
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; Step1 has no legacy fallback")
    recipe = read_single(
        server_dir / "metadata/grt_recipe.tsv",
        [
            "recipe_id",
            "primary_dataset",
            "support_datasets_json",
            "reads_qc_enabled",
            "donor_set_id",
            "tel_donor_set_id",
            "q0_relpath",
            "final_q_relpath",
        ],
    )
    donor_set, donor_members, donor_freeze_row = verify_donor_freeze(server_dir, recipe)
    sources = source_catalog(server_dir)
    all_q_rows = read_tsv(server_dir / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS)
    base_q_rows = [row for row in all_q_rows if row["q_version"] == "q0"]
    all_evidence_rows = read_tsv(server_dir / "metadata/grt_evidence_registry.tsv", EVIDENCE_FIELDS)
    base_evidence_rows = [row for row in all_evidence_rows if row["stage"] == "assignment"]
    base_tool_rows = read_tsv(server_dir / "metadata/grt_tool_versions.tsv", TOOL_FIELDS)
    minimap = executable_identity(args.minimap2)
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in read_tsv(
        server_dir / "metadata/chr_assignments.tsv",
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "support_bp",
            "support_percent",
            "anchor_start",
        ],
    ):
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    chromosome_order, q0_paths, q0_records = load_q_paths(
        server_dir, "q0", base_q_rows, sources
    )
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "donor_set_id": donor_set["donor_set_id"],
            "q0_sha256": sha256_file(server_dir / "grt/q/q0.fa"),
            "engine_version": ENGINE_VERSION,
            "minimap": minimap,
        },
        24,
    )
    results: list[dict[str, object]] = []
    round1, _round1_cached = run_round_stage(
        server_dir,
        run_id,
        "step1_round1",
        "q0",
        "q0r1",
        chromosome_order,
        q0_paths,
        q0_records,
        base_q_rows,
        donor_set,
        donor_members,
        assignments,
        sources,
        [],
        minimap,
        args.threads,
    )
    results.append(round1)
    publish_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    _, q0r1_paths, q0r1_records = load_q_paths(
        server_dir, "q0r1", round1["q_rows"], sources
    )
    filter_result, _filter_cached = run_filter_stage(
        server_dir,
        run_id,
        chromosome_order,
        q0r1_paths,
        q0r1_records,
        round1["q_rows"],
        sources,
        donor_set["donor_set_id"],
    )
    reconcile_filtered_round1_events(round1, filter_result)
    results.append(filter_result)
    publish_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    _, q0f_paths, q0f_records = load_q_paths(
        server_dir, "q0f", filter_result["q_rows"], sources
    )
    round2, _round2_cached = run_round_stage(
        server_dir,
        run_id,
        "step1_round2",
        "q0f",
        "q1",
        chromosome_order,
        q0f_paths,
        q0f_records,
        filter_result["q_rows"],
        donor_set,
        donor_members,
        assignments,
        sources,
        round1["accepted_intervals"],
        minimap,
        args.threads,
    )
    results.append(round2)
    publish_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    q1_records = dict(read_fasta(server_dir / "grt/q/q1.fa"))
    replayed_round1 = replay_round_records(q0_records, round1["events"], sources)
    replayed_filter = replay_filter_records(replayed_round1, filter_result["events"])
    replayed_round2 = replay_round_records(replayed_filter, round2["events"], sources)
    if replayed_round2 != q1_records:
        fail("recorded Step1 events do not deterministically reconstruct q1")
    if donor_set["donor_set_id"] != round1["donor_set_id"] or donor_set["donor_set_id"] != round2["donor_set_id"]:
        fail("Step1 rounds do not reference the same frozen donor set")
    print(
        f"GRT Step1 complete: run={run_id}, donor_set={donor_set['donor_set_id']}, "
        f"q1_sha256={sha256_file(server_dir / 'grt/q/q1.fa')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=10)
    args = parser.parse_args()
    if args.threads < 1:
        fail("threads must be a positive integer")
    execute(args)


if __name__ == "__main__":
    main()
