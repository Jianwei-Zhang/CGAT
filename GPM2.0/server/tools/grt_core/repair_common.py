"""Shared repair constants, candidate arbitration, validation and engine identity."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path
from threading import Event, Lock

from . import *
from .common import *
from .alignment_index import AlignmentCoordinateIndex, Step2MemberIndex
from .mummer import (
    command_identity, is_header_only_mummer_delta, mummer_parameters,
    parse_mummer_coords, run_logged, write_skipped_command_logs,
)


def repair_engine_sha256(core_root: Path | None = None) -> str:
    """Hash the complete staged engine, independent of its installation path.

    Step2 and Step3 intentionally share one identity: changing either stage or
    a shared helper invalidates stage decisions, never independent raw alignments.
    Entry scripts are included so changing their CLI contract is also detected.
    """
    core_root = Path(__file__).resolve().parent if core_root is None else core_root
    tools_root = core_root.parent
    files = sorted(core_root.rglob("*.py")) + [
        tools_root / "grt_step2.py", tools_root / "grt_step3.py",
    ]
    return sha256_bytes(canonical_json({
        path.relative_to(tools_root).as_posix(): sha256_file(path)
        for path in files
    }).encode("utf-8"))

ENGINE_VERSION = 14
MUMMER_MIN_CLUSTER = 1_000
MUMMER_MIN_MATCH = 100
MUMMER_MIN_ALIGNMENT = 10_000
MUMMER_LARGE_TARGET_BP = 1_000_000
MUMMER_SMALL_CHUNK_BP = 10_000_000
PATCH_FLANK = 10_000
PATCH_MAX_ANCHOR_DISTANCE = 1_000_000
PATCH_SEARCH_RANGE = 500_000
PATCH_MIN_SCORE = 0.70
PATCH_MIN_MATCH = 100
PATCH_MIN_MAPQ = 20
REFILL_MIN_ALIGNMENT = 1_000
REFILL_MIN_IDENTITY = 0.40
REFILL_MAX_LENGTH = 1_000_000
CORRECTION_SEARCH_RANGE = 500_000
CORRECTION_MARGIN = 100
CORRECTION_LARGE_EDIT_BP = 100_000
CORRECTION_MAX_OVERLAP_EDIT_RATIO = 5.0
PRIMARY_OVERLAP_MIN_BP = 10_000
PRIMARY_OVERLAP_MAX_BP = CORRECTION_SEARCH_RANGE
PRIMARY_OVERLAP_MAX_LEFT_TRIM = CORRECTION_MARGIN
PRIMARY_OVERLAP_POLICY = "keep_left_trim_right"
DOMINATED_COMPONENT_POLICY = "drop_dominated_terminal_component"
NORMALIZED_GAP_LENGTH = 100
MINIMAP_PRESET = "asm5"
REPAIR_MODES = {"conservative", "aggressive"}
DEFAULT_REPAIR_MODE = "aggressive"
MUMMER_SCOPES = {"full", "gap-screen"}
DEFAULT_MUMMER_SCOPE = "full"
DEFAULT_STEP3_MUMMER_SCOPE = "gap-screen"
EXECUTION_PROFILES = {"baseline", "optimized"}
DEFAULT_EXECUTION_PROFILE = "optimized"
ENGINE_SHA256 = repair_engine_sha256()
EXECUTION_HELPER_SHA256 = sha256_file(Path(sys.modules[AlignmentCoordinateIndex.__module__].__file__))

MUMMER_ALIGNMENT_FIELDS = [
    "stage",
    "chr",
    "line_number",
    "member_id",
    "source_dataset",
    "source_contig",
    "ref_record",
    "ref_start",
    "ref_end",
    "query_start",
    "query_end",
    "orientation",
    "identity",
    "ref_length",
    "query_length",
    "raw_line",
]

CANDIDATE_FIELDS = [
    "candidate_id",
    "stage",
    "chr",
    "object_id",
    "action",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "target_start",
    "target_end",
    "input_start",
    "input_end",
    "trim_left",
    "trim_right",
    "fill_length",
    "identity",
    "aligned_length",
    "mapq",
    "left_line",
    "right_line",
    "validation_passed",
    "outcome",
    "reason",
    "event_id",
    "final_path_segment_id",
    "error_type",
    "error_subtype",
    "error_features_json",
    "confidence",
    "confidence_score",
    "gap_in_error_region",
    "repair_mode",
    "repair_reason",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
]

REJECTION_FIELDS = [
    "stage",
    "chr",
    "object_id",
    "candidate_id",
    "left_line",
    "right_line",
    "reason",
]
STRATEGY_FIELDS = [
    "chr",
    "strategy",
    "strategy_applied",
    "gap_count",
    "patch_candidate_count",
    "validated_patch_count",
    "accepted_patch_count",
    "fallback_candidate_count",
    "accepted_fallback_count",
    "reason",
]
CLASSIFICATION_FIELDS = [
    "chr",
    "object_id",
    "candidate_id",
    "error_type",
    "error_subtype",
    "error_features_json",
    "confidence",
    "confidence_score",
    "gap_in_error_region",
    "repair_mode",
    "repair_reason",
    "outcome",
    "event_id",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
]


def reject_candidates_spanning_other_gaps(
    candidates: list[dict[str, object]],
    gaps: list[dict[str, object]],
    rejections: list[dict[str, object]] | None = None,
) -> None:
    """Keep one accepted edit tied to exactly one auditable gap object."""
    gaps_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for gap in gaps:
        gaps_by_chr[str(gap["chr"])].append(gap)
    for candidate in candidates:
        if candidate.get("outcome") != "candidate":
            continue
        other_gap = next(
            (
                gap
                for gap in gaps_by_chr[str(candidate["chr"])]
                if str(gap["object_id"]) != str(candidate["object_id"])
                and intervals_overlap(
                    int(candidate["input_start"]),
                    int(candidate["input_end"]),
                    int(gap["start0"]) + 1,
                    int(gap["end0"]),
                )
            ),
            None,
        )
        if other_gap is None:
            continue
        candidate["outcome"] = "rejected"
        candidate["reason"] = f"target_interval_spans_other_gap:{other_gap['object_id']}"
        if rejections is not None:
            rejections.append(
                {
                    "stage": candidate["stage"],
                    "chr": candidate["chr"],
                    "object_id": candidate["object_id"],
                    "candidate_id": candidate["candidate_id"],
                    "left_line": candidate.get("left_line", ""),
                    "right_line": candidate.get("right_line", ""),
                    "reason": candidate["reason"],
                }
            )


def reference_overlap_score(candidate: dict[str, object]) -> int:
    """Return the largest Type5 reference-overlap feature in base pairs."""
    overlaps = []
    for feature in candidate.get("error_features", []):
        match = re.fullmatch(r"ref_overlap_(\d+)", str(feature))
        if match:
            overlaps.append(int(match.group(1)))
    return max(overlaps, default=0)


def arbitrate(
    candidates: list[dict[str, object]],
    consumed: list[dict[str, object]],
) -> list[dict[str, object]]:
    valid = [row for row in candidates if row.get("outcome") == "candidate"]
    ordered = sorted(
        valid,
        key=lambda row: (
            -int(bool(row.get("validation_passed", False))),
            -reference_overlap_score(row),
            (
                int(row["input_end"]) - int(row["input_start"]) + 1
                if row.get("direct_patch_anchor_pair")
                else 0
            ),
            -float(row["identity"]),
            -int(row["aligned_length"]),
            -int(row.get("mapq", 0)),
            str(row["source_dataset"]),
            str(row["source_contig"]),
            int(row["source_start"]),
            int(row["source_end"]),
            str(row["chr"]),
            int(row["input_start"]),
            str(row["candidate_id"]),
        ),
    )
    occupied_sources = [dict(row) for row in consumed]
    occupied_targets: list[dict[str, object]] = []
    accepted_objects: set[str] = set()
    for candidate in ordered:
        object_id = str(candidate["object_id"])
        if object_id in accepted_objects:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "lower_ranked_candidate_for_object"
            continue
        source_consumable = bool(candidate.get("source_consumable", True))
        source_collision = next(
            (
                row
                for row in occupied_sources
                if source_consumable
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
        source_collision_same_object = (
            source_collision is not None
            and source_collision.get("object_id")
            and str(source_collision.get("object_id")) == object_id
        )
        source_collision_orientation_conflict = (
            source_collision is not None
            and source_collision.get("orientation")
            and str(source_collision.get("orientation")) != str(candidate.get("orientation"))
        )
        if source_collision is not None and (
            source_collision_same_object or source_collision_orientation_conflict
        ):
            candidate["outcome"] = "conflicted"
            blocker = source_collision.get("candidate_id") or source_collision.get("usage_id") or "prior_usage"
            candidate["reason"] = (
                "source_interval_reuse_orientation_conflict"
                if source_collision_orientation_conflict
                else f"source_interval_consumed_by:{blocker}"
            )
            continue
        target_collision = next(
            (
                row
                for row in occupied_targets
                if row["chr"] == candidate["chr"]
                and intervals_overlap(
                    int(row["input_start"]),
                    int(row["input_end"]),
                    int(candidate["input_start"]),
                    int(candidate["input_end"]),
                )
            ),
            None,
        )
        if target_collision is not None:
            candidate["outcome"] = "conflicted"
            candidate["reason"] = f"target_interval_overlaps:{target_collision['candidate_id']}"
            continue
        candidate["outcome"] = "accepted"
        candidate["reason"] = (
            f"accepted_with_donor_reuse_of:{source_collision.get('candidate_id', '')}"
            if source_collision is not None
            else "accepted_by_global_interval_arbitration"
        )
        if source_collision is not None:
            candidate["donor_reuse"] = True
            candidate["donor_reuse_of"] = source_collision.get("candidate_id", "")
        accepted_objects.add(object_id)
        if source_consumable:
            occupied_sources.append(candidate)
        occupied_targets.append(candidate)
    return sorted(
        candidates,
        key=lambda row: (
            str(row["chr"]),
            int(row["target_start"]),
            str(row["candidate_id"]),
        ),
    )


def candidate_table_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        row = {field: candidate.get(field, "") for field in CANDIDATE_FIELDS}
        row["identity"] = f"{float(candidate['identity']):.9f}"
        row["validation_passed"] = str(bool(candidate.get("validation_passed", False))).lower()
        rows.append(row)
    return rows


def consumed_intervals(
    usage_rows: list[dict[str, str]],
    event_rows: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    events_by_id = {
        str(row["event_id"]): row
        for row in (event_rows or [])
        if row.get("event_id")
    }
    return [
        {
            "candidate_id": row.get("event_id") or row["usage_id"],
            "usage_id": row["usage_id"],
            "source_dataset": row["source_dataset"],
            "source_contig": row["source_contig"],
            "source_start": int(row["source_start"]),
            "source_end": int(row["source_end"]),
            "stage": row["stage"],
            "object_id": str(events_by_id.get(str(row.get("event_id")), {}).get("object_id", "")),
            "chr": str(events_by_id.get(str(row.get("event_id")), {}).get("chr", "")),
            "orientation": str(events_by_id.get(str(row.get("event_id")), {}).get("source", {}).get("orientation", "")),
        }
        for row in usage_rows
        if row["status"] in {"consumed", "accepted", "superseded"}
    ]


def annotate_candidate_fragments(
    candidates: list[dict[str, object]],
    donor_members: list[dict[str, str]],
    fragment_rows: list[dict[str, str]],
) -> None:
    members_by_id = {row["member_id"]: row for row in donor_members}
    fragments_by_member: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in fragment_rows:
        fragments_by_member[row["member_id"]].append(row)
    for candidate in candidates:
        member = members_by_id.get(str(candidate.get("member_id", "")))
        if member is None:
            continue
        source_start = int(candidate["source_start"])
        source_end = int(candidate["source_end"])
        fragment = None
        for row in fragments_by_member.get(member["member_id"], []):
            fragment_start, fragment_end = member_source_interval(
                member,
                int(row["fragment_start"]),
                int(row["fragment_end"]),
            )
            if fragment_start <= source_start and source_end <= fragment_end:
                fragment = row
                break
        if fragment is None:
            if candidate.get("outcome") == "candidate":
                candidate["outcome"] = "rejected"
                candidate["reason"] = "donor_interval_not_within_fragment"
            candidate["fragment_id"] = ""
        else:
            candidate["fragment_id"] = fragment["fragment_id"]


def evidence_row(
    *,
    evidence_id: str,
    stage: str,
    evidence_type: str,
    status: str,
    q_version: str,
    q_source_sha256: str,
    query_relpath: str,
    query_sha256: str,
    donor_set_id: str,
    target_relpath: str,
    target_sha256: str,
    candidate: dict[str, object],
    tool: str,
    tool_version: str,
    preset: str,
    parameters: dict[str, object],
    raw_relpath: str,
    raw_sha256: str,
    coordinate_system: str,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "stage": stage,
        "evidence_type": evidence_type,
        "status": status,
        "q_version": q_version,
        "q_source_sha256": q_source_sha256,
        "query_artifact_relpath": query_relpath,
        "query_sha256": query_sha256,
        "donor_set_id": donor_set_id,
        "target_artifact_relpath": target_relpath,
        "target_sha256": target_sha256,
        "source_dataset": candidate["source_dataset"],
        "source_contig": candidate["source_contig"],
        "source_start": candidate["source_start"],
        "source_end": candidate["source_end"],
        "orientation": candidate["orientation"],
        "target_chr": candidate["chr"],
        "target_start": candidate["target_start"],
        "target_end": candidate["target_end"],
        "tool": tool,
        "tool_version": tool_version,
        "preset": preset,
        "parameters_json": canonical_json(parameters),
        "raw_artifact_relpath": raw_relpath,
        "raw_artifact_sha256": raw_sha256,
        "coordinate_system": coordinate_system,
        "projection_status": "projected",
    }
