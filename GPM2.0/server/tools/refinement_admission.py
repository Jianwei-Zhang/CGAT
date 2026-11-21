"""Normalize native proposals without adopting an unproven whole-genome output.

DEGAP v2 native coordinates are inclusive; CGAT edit placement is half-open.
Exact anchors establish where an edit applies, not biological correctness.
"""
from __future__ import annotations

from typing import Protocol

try:
    from refinement_path import BLOCK, Edit, Gap, identity
except ModuleNotFoundError:
    from .refinement_path import BLOCK, Edit, Gap, identity


class Genome(Protocol):
    records: dict
    def fetch(self, name: str, start: int, end: int) -> bytes: ...


def exact_anchor(left: Genome, name: str, start: int, right: Genome, rname: str,
                 rstart: int, length: int) -> bool:
    for offset in range(0, length, BLOCK):
        size = min(BLOCK, length - offset)
        a = left.fetch(name, start + offset, start + offset + size).upper()
        b = right.fetch(rname, rstart + offset, rstart + offset + size).upper()
        if len(a) != size or a != b or b"N" in a:
            return False
    return True


def degap_proposal(row: dict, baseline: Genome, candidate: Genome, gaps: list[Gap], *,
                   source_dataset: str, native_job: str, artifact_sha256: str) -> tuple[Edit | None, str]:
    fields = ("gap_start", "gap_end", "gap_len", "left_flank_len", "right_flank_len",
              "replace_start", "replace_end", "replace_len")
    if any(type(row.get(field)) is not int for field in fields):
        return None, "invalid_native_coordinates"
    name, start, end = row.get("chromosome"), row["gap_start"], row["gap_end"] + 1
    if name not in baseline.records:
        return None, "unknown_baseline_chromosome"
    length = baseline.records[name][0]
    left, right = row["left_flank_len"], row["right_flank_len"]
    if (not 0 <= start < end <= length or left <= 0 or right <= 0 or row["gap_len"] != end - start
            or row["replace_start"] != start - left or row["replace_end"] != end + right - 1
            or row["replace_len"] != left + end - start + right or start < left or end + right > length):
        return None, "invalid_native_coordinates"
    covered = [gap for gap in gaps if gap.chromosome == name and start <= gap.start < gap.end <= end]
    intersecting = [gap for gap in gaps if gap.chromosome == name and start < gap.end and gap.start < end]
    if (not covered or covered != intersecting or covered[0].start != start or covered[-1].end != end):
        return None, "native_interval_does_not_identify_original_gaps"
    if row.get("filled") is not True:
        return None, "native_unfilled"
    if len(candidate.records) != 1:
        return None, "ambiguous_candidate_records"
    cname, (clength, *_) = next(iter(candidate.records.items()))
    if clength < max(left, right):
        return None, "candidate_shorter_than_anchors"
    if (not exact_anchor(baseline, name, start - left, candidate, cname, 0, left)
            or not exact_anchor(baseline, name, end, candidate, cname, clength - right, right)):
        return None, "native_anchors_do_not_reconstruct_baseline"
    bridge_length = clength - left - right
    if bridge_length < 0:
        # Candidate anchors overlap. Keep the original left source and remove the
        # duplicate beginning of the right source, instead of demanding a bridge.
        end -= bridge_length
        replacement = None
        method = "exact_anchors_overlap_closure"
    elif bridge_length == 0:
        replacement = None
        method = "exact_anchors_gap_deletion"
    else:
        replacement = {"dataset": source_dataset, "contig": cname,
                       "start": left + 1, "end": clength - right, "orientation": "+"}
        method = "exact_anchors_joint_repair" if len(covered) > 1 else "exact_anchors_gap_repair"
    # Extended overlap deletion must not silently consume another unidentified gap.
    affected = [gap for gap in gaps if gap.chromosome == name and start < gap.end and gap.start < end]
    if affected != covered:
        return None, "overlap_crosses_another_gap"
    if replacement is not None:
        different, informative = bridge_length != end - start, False
        for offset in range(0, bridge_length, BLOCK):
            size = min(BLOCK, bridge_length - offset)
            block = candidate.fetch(cname, left + offset, left + offset + size).upper()
            informative |= bool(block.strip(b"N"))
            if bridge_length == end - start:
                different |= block != baseline.fetch(name, start + offset, start + offset + size).upper()
        if not informative:
            return None, "candidate_has_no_filled_bases"
        if not different:
            return None, "candidate_does_not_change_baseline"
    edit_id = "degap-" + identity([name, start, end, native_job, artifact_sha256])[:24]
    evidence = {"method": method, "candidate_sha256": artifact_sha256,
                "native_gap_id": row.get("gap_id"), "native_coordinates": {key: row[key] for key in fields},
                "anchors": {"left_bp": left, "right_bp": right},
                "claim": "traceable native edit; not independent biological validation"}
    return Edit(edit_id, "degap", name, start, end, replacement, tuple(g.gap_id for g in covered),
                native_job, evidence), "accepted"


def exclude_conflicts(edits: list[Edit]) -> tuple[list[Edit], list[dict]]:
    """Reject every conflicting proposal; never prefer arbitrary file/list order."""
    conflicts = set()
    grouped = {}
    for index, edit in enumerate(edits):
        grouped.setdefault(edit.chromosome, []).append((index, edit))
    for group in grouped.values():
        active = []
        for index, edit in sorted(group, key=lambda item: (item[1].start, item[1].end)):
            active = [(i, item) for i, item in active if item.end > edit.start]
            for other_index, _ in active:
                conflicts.update((index, other_index))
            active.append((index, edit))
    return ([edit for index, edit in enumerate(edits) if index not in conflicts],
            [{"edit_id": edits[index].edit_id, "gap_ids": list(edits[index].gap_ids),
              "native_job": edits[index].native_job, "reason": "conflicting_native_proposals"}
             for index in sorted(conflicts)])


def preserve_joint_sources(edits, baseline, catalog, gaps):
    """Keep uniquely unchanged original islands inside a native merged-gap job."""
    from dataclasses import replace
    try:
        from refinement_native_trace import split_retained_islands, equal_regions, TraceError
    except ModuleNotFoundError:
        from .refinement_native_trace import split_retained_islands, equal_regions, TraceError
    accepted, rejected = [], []
    for edit in edits:
        if edit.replacement is None or len(edit.gap_ids) < 2:
            accepted.append(edit)
            continue
        source = edit.replacement
        class CandidateGenome:
            records = {edit.chromosome: (catalog.length(source["dataset"], source["contig"]),)}
            def fetch(self, name, a, b):
                if name != edit.chromosome:
                    raise TraceError("joint candidate chromosome differs")
                return catalog.fetch(source["dataset"], source["contig"], a, b)
        candidate = CandidateGenome()
        if source["orientation"] != "+":
            raise TraceError("DEGAP joint candidate must be in native forward orientation")
        try:
            parts = split_retained_islands(baseline, candidate, edit.chromosome,
                                          (edit.start, edit.end, source["start"] - 1, source["end"]), gaps)
        except TraceError as error:
            rejected.append({"edit_id": edit.edit_id, "gap_ids": list(edit.gap_ids),
                             "native_job": edit.native_job, "reason": str(error)})
            continue
        if len(parts) == 1:
            accepted.append(edit)
            continue
        for start, end, left, right in parts:
            if end - start == right - left and equal_regions(baseline, edit.chromosome, start, candidate, left, end - start):
                continue
            gap_ids = tuple(gap.gap_id for gap in gaps if gap.chromosome == edit.chromosome and start < gap.end and gap.start < end)
            if not gap_ids or start >= end:
                raise TraceError("joint candidate split is not bound to an original gap")
            replacement = None if left == right else {**source, "start": left + 1, "end": right}
            accepted.append(replace(edit, edit_id="degap-" + identity([edit.edit_id, start, end, left, right])[:24],
                                    start=start, end=end, replacement=replacement, gap_ids=gap_ids,
                                    evidence={**edit.evidence, "parent_native_edit_id": edit.edit_id,
                                              "unchanged_internal_islands_retained": True}))
    return accepted, rejected
