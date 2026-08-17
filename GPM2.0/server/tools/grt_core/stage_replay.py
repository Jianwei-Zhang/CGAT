from __future__ import annotations

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

from .common import *
from .stage_schema import *
from .stage_io import *
from .stage_alignment import *

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
            event["fragment_id"] = candidate.get("fragment_id", "")
            if candidate.get("donor_reuse"):
                event["donor_reuse"] = {
                    "reused": True,
                    "reused_from_candidate_id": candidate.get("donor_reuse_of", ""),
                    "policy": "same_orientation_distinct_target",
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
