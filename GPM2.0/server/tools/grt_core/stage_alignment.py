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
    fragments_by_record: dict[str, list[dict[str, str]]] | None = None,
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
                        fragment = next(
                            (
                                row
                                for row in (fragments_by_record or {}).get(str(left["target"]), [])
                                if int(row["fragment_start"]) <= local_start
                                and local_end <= int(row["fragment_end"])
                            ),
                            None,
                        )
                        if fragments_by_record is not None and fragment is None:
                            rejection["reason"] = "donor_interval_not_within_fragment"
                        elif re.search(r"N{100,}", donor_sequence):
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
                                "fragment_id": "" if fragment is None else fragment["fragment_id"],
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
                                    "fragment_id": "" if fragment is None else fragment["fragment_id"],
                                    "donor_reuse": False,
                                    "donor_reuse_of": "",
                                }
                            )
                            continue
                rejections.append(rejection)
    return candidates, rejections

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
        collision_same_object = (
            collision is not None
            and collision.get("object_id")
            and str(collision.get("object_id")) == object_id
        )
        collision_orientation_conflict = (
            collision is not None
            and collision.get("orientation")
            and str(collision.get("orientation")) != str(candidate.get("orientation"))
        )
        if collision is not None and (collision_same_object or collision_orientation_conflict):
            candidate["outcome"] = "conflicted"
            candidate["reason"] = (
                "source_interval_reuse_orientation_conflict"
                if collision_orientation_conflict
                else f"source_interval_consumed_by:{collision['candidate_id']}"
            )
            continue
        candidate["outcome"] = "accepted"
        candidate["reason"] = (
            f"accepted_with_donor_reuse_of:{collision['candidate_id']}"
            if collision is not None
            else "accepted_by_global_interval_arbitration"
        )
        if collision is not None:
            candidate["donor_reuse"] = True
            candidate["donor_reuse_of"] = collision.get("candidate_id", "")
        accepted_gaps.add(object_id)
        occupied.append(candidate)
    return ordered
