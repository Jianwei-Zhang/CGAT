"""Normalize native proposals without adopting an unproven whole-genome output.

DEGAP v2 native reports are 1-based inclusive; CGAT edit placement is 0-based half-open.
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
    # Part2 writes start/end +1; Part3 forwards them unchanged despite its
    # stale "0-based" comments. Never infer coordinates from those comments or
    # accept a legacy controlled fixture by shifting to whichever gap matches.
    name, start, end = row.get("chromosome"), row["gap_start"] - 1, row["gap_end"]
    if name not in baseline.records:
        return None, "unknown_baseline_chromosome"
    length = baseline.records[name][0]
    left, right = row["left_flank_len"], row["right_flank_len"]
    if (not 0 <= start < end <= length or left <= 0 or right <= 0 or row["gap_len"] != end - start
            or row["replace_start"] != start - left + 1 or row["replace_end"] != end + right
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


def degap_family_proposal(row, baseline, integration, full_candidate, gaps, *, source_dataset, native_job,
                          artifact_sha256, junction_policy, max_flank_replacement_bp):
    """Require the sealed integration slice and intact anchors outside the junction.

    GAP coordinates remain 1-based inclusive; the new integrator's replace_*
    fields are 0-based inclusive. Native read support is recorded, not inferred
    from the full candidate or reinterpreted as an independent CGAT call.
    """
    fields = ("gap_start", "gap_end", "gap_len", "left_flank_len", "right_flank_len",
              "replace_start", "replace_end", "replace_len")
    if row.get("filled") is not True:
        return None, "native_unfilled"
    junction = row.get("junction")
    if (not isinstance(junction, dict) or not isinstance(junction.get("policy"), dict)
            or junction["policy"].get("version") != junction_policy
            or any(type(row.get(k)) is not int for k in fields)
            or any(type(junction.get(k)) is not int for k in ("left_replace_bases", "right_replace_bases",
                                                             "gap_length", "flank_length_delta", "overlap_trim"))):
        return None, "invalid_native_junction_coordinates"
    name = row.get("chromosome")
    if name not in baseline.records:
        return None, "unknown_baseline_chromosome"
    size = baseline.records[name][0]
    g0, g1 = row["gap_start"] - 1, row["gap_end"]
    left, right = row["left_flank_len"], row["right_flank_len"]
    lcut, rcut = junction["left_replace_bases"], junction["right_replace_bases"]
    start, end = g0 - lcut, g1 + rcut
    if (not 0 <= g0 - left <= start <= g0 < g1 <= end <= g1 + right <= size
            or not 0 <= lcut < left or not 0 <= rcut < right or row["gap_len"] != g1 - g0
            or (row["replace_start"], row["replace_end"], row["replace_len"]) != (start, end - 1, end - start)):
        return None, "invalid_native_junction_coordinates"
    distinct = [gap for gap in gaps if gap.chromosome == name and start < gap.end and gap.start < end]
    if not distinct or distinct[0].start != g0 or distinct[-1].end != g1:
        return None, "native_junction_does_not_identify_original_gaps"
    mode, gap_len = junction.get("mode"), junction["gap_length"]
    delta, trim = junction["flank_length_delta"], junction["overlap_trim"]
    if mode == "overlap":
        if (lcut != 0 or delta != 0 or not 0 < trim == rcut <= left or gap_len != -trim
                or not exact_anchor(baseline, name, g0 - trim, baseline, name, g1, trim)):
            return None, "unproven_native_overlap"
    elif (mode != "gap" or trim != 0 or min(gap_len, lcut + rcut + delta) < 0
          or max(lcut, rcut) > max_flank_replacement_bp):
        return None, "native_flank_replacement_exceeds_policy"
    bridge_len = lcut + rcut + gap_len + delta
    if len(full_candidate.records) != 1 or (integration is not None and len(integration.records) != 1):
        return None, "ambiguous_candidate_records"
    full_name, (full_length, *_) = next(iter(full_candidate.records.items()))
    a, b = left - lcut, right - rcut
    if (full_length != a + bridge_len + b
            or not exact_anchor(baseline, name, g0 - left, full_candidate, full_name, 0, a)
            or not exact_anchor(baseline, name, end, full_candidate, full_name, a + bridge_len, b)):
        return None, "native_junction_exterior_does_not_reconstruct_baseline"
    replacement = None
    if integration is not None:
        cname, (length, *_) = next(iter(integration.records.items()))
        if length != bridge_len or not exact_anchor(full_candidate, full_name, a, integration, cname, 0, length):
            return None, "native_integration_slice_disagrees_with_full_candidate"
        replacement = {"dataset": source_dataset, "contig": cname, "start": 1, "end": length, "orientation": "+"}
    elif bridge_len != 0:
        return None, "missing_native_junction_sequence"
    method = "sealed_family_overlap" if mode == "overlap" else "sealed_family_junction"
    edit_id = "degap-" + identity([name, start, end, native_job, artifact_sha256])[:24]
    return Edit(edit_id, "degap", name, start, end, replacement, tuple(g.gap_id for g in distinct), native_job,
                {"method": method, "candidate_sha256": artifact_sha256, "native_gap_id": row.get("gap_id"),
                 "native_coordinates": {key: row[key] for key in fields}, "junction": junction,
                 "anchors": {"left_bp": a, "right_bp": b},
                 "claim": "traceable native edit; not independent biological validation"}), "accepted"


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
        from refinement_native_trace import split_retained_islands, equal_regions, TraceError, UNSEPARABLE_FLANK
    except ModuleNotFoundError:
        from .refinement_native_trace import split_retained_islands, equal_regions, TraceError, UNSEPARABLE_FLANK
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
        for start, end, left, right in parts:
            if end - start == right - left and equal_regions(baseline, edit.chromosome, start, candidate, left, end - start):
                continue
            gap_ids = tuple(gap.gap_id for gap in gaps if gap.chromosome == edit.chromosome and start < gap.end and gap.start < end)
            if not gap_ids or start >= end:
                raise TraceError("joint candidate split is not bound to an original gap")
            if len(gap_ids) > 1:
                rejected.append({"edit_id": edit.edit_id, "gap_ids": list(gap_ids), "native_job": edit.native_job,
                                 "chromosome": edit.chromosome, "baseline_interval": [start, end],
                                 "native_interval": [left, right], "reason": UNSEPARABLE_FLANK})
                continue
            replacement = None if left == right else {**source, "start": left + 1, "end": right}
            accepted.append(replace(edit, edit_id="degap-" + identity([edit.edit_id, start, end, left, right])[:24],
                                    start=start, end=end, replacement=replacement, gap_ids=gap_ids,
                                    evidence={**edit.evidence, "parent_native_edit_id": edit.edit_id,
                                              "unchanged_internal_islands_retained": True}))
    return accepted, rejected
