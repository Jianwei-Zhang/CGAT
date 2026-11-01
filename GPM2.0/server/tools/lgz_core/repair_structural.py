"""Shared structural anchor analysis and path edits used by Step2 and Step3."""

from __future__ import annotations

from .repair_common import *


def _step3_alignment_features(
    gap_pos: int,
    left: dict[str, object],
    right: dict[str, object] | None,
) -> dict[str, object]:
    """Return the alignment feature vector used by LGZ's gap analyzer.

    MUMmer rows are already normalized to 1-based closed coordinates by
    :func:`parse_mummer_coords`.  Keeping this adapter on those rows avoids
    importing the standalone LGZ package (which would lose GPM provenance).
    """
    if right is None:
        return {
            "crossing_alignment": True,
            "query_overlap": True,
            "query_overlap_length": int(left["query_max"]) - int(left["query_min"]) + 1,
            "query_overlap_region": (int(left["query_min"]), int(left["query_max"])),
            "ref_overlap": False,
            "ref_overlap_length": 0,
            "ref_overlap_region": (0, 0),
            "ref_overlap_ratio": 0.0,
            "direction_match": True,
            "ref_contig_match": True,
            "left_distance": 0,
            "right_distance": 0,
            "left_anchor_quality": int(left["query_aligned"]) * float(left["identity"]),
            "right_anchor_quality": 0.0,
            "left_anchor_length": int(left["query_aligned"]),
            "right_anchor_length": 0,
            "total_gap_size": 0,
            "ref_record": str(left["ref_record"]),
        }

    left_q_min, left_q_max = int(left["query_min"]), int(left["query_max"])
    right_q_min, right_q_max = int(right["query_min"]), int(right["query_max"])
    query_overlap_start = max(left_q_min, right_q_min)
    query_overlap_end = min(left_q_max, right_q_max)
    query_overlap = query_overlap_start <= query_overlap_end
    same_ref = str(left["ref_record"]) == str(right["ref_record"])
    ref_overlap_start = max(int(left["ref_min"]), int(right["ref_min"]))
    ref_overlap_end = min(int(left["ref_max"]), int(right["ref_max"]))
    ref_overlap = same_ref and ref_overlap_start <= ref_overlap_end
    ref_overlap_length = ref_overlap_end - ref_overlap_start + 1 if ref_overlap else 0
    min_anchor = min(
        int(left["ref_max"]) - int(left["ref_min"]) + 1,
        int(right["ref_max"]) - int(right["ref_min"]) + 1,
    )
    return {
        "crossing_alignment": False,
        "query_overlap": query_overlap,
        "query_overlap_length": query_overlap_length if query_overlap else 0,
        "query_overlap_region": (
            (query_overlap_start, query_overlap_end) if query_overlap else (0, 0)
        ),
        "ref_overlap": ref_overlap,
        "ref_overlap_length": ref_overlap_length,
        "ref_overlap_region": (
            (ref_overlap_start, ref_overlap_end) if ref_overlap else (0, 0)
        ),
        "ref_overlap_ratio": ref_overlap_length / min_anchor if ref_overlap and min_anchor else 0.0,
        "direction_match": left["orientation"] == right["orientation"],
        "ref_contig_match": same_ref,
        "left_distance": gap_pos - left_q_max,
        "right_distance": right_q_min - gap_pos,
        "left_anchor_quality": int(left["query_aligned"]) * float(left["identity"]),
        "right_anchor_quality": int(right["query_aligned"]) * float(right["identity"]),
        "left_anchor_length": int(left["query_aligned"]),
        "right_anchor_length": int(right["query_aligned"]),
        "total_gap_size": (gap_pos - left_q_max) + (right_q_min - gap_pos),
        "ref_record": str(left["ref_record"]),
    }



def _step3_classify_features(features: dict[str, object]) -> tuple[str, str, list[str], float]:
    """Classify one anchor pair using LGZ Type1--Type6 precedence."""
    if features.get("crossing_alignment"):
        return "type1", "crossing_alignment", ["crossing_alignment"], 0.90

    if features["ref_overlap"]:
        overlap = int(features["ref_overlap_length"])
        subtype = "small_ref_overlap" if overlap < 10_000 else (
            "medium_ref_overlap" if overlap < 50_000 else "large_ref_overlap"
        )
        return (
            "type5",
            subtype,
            [f"ref_overlap_{overlap}"],
            min(0.9 + overlap / 1_000_000.0, 0.99),
        )

    feature_names: list[str] = []
    if features["query_overlap"]:
        feature_names.append(f"query_overlap_{features['query_overlap_length']}")
    if not features["direction_match"]:
        feature_names.append("direction_conflict")
    if not features["ref_contig_match"]:
        feature_names.append("ref_contig_conflict")
    if int(features["left_distance"]) > 100_000:
        feature_names.append(f"large_left_gap_{features['left_distance']}")
    if int(features["right_distance"]) > 100_000:
        feature_names.append(f"large_right_gap_{features['right_distance']}")
    gap_size = int(features["total_gap_size"])
    feature_names.append(
        "small_gap" if gap_size < 1_000 else "medium_gap" if gap_size < 50_000 else "large_gap"
    )

    conflicts = sum(
        [
            not bool(features["direction_match"]),
            not bool(features["ref_contig_match"]),
            bool(features["query_overlap"]) and bool(features["ref_overlap"]),
        ]
    )
    if conflicts >= 2:
        error_type, subtype = "type6", "complex_conflict"
    elif not features["direction_match"]:
        error_type, subtype = "type2", "direction_conflict"
    elif not features["ref_contig_match"]:
        error_type, subtype = "type3", "simple_translocation"
    elif features["query_overlap"]:
        error_type, subtype = "type4", "query_overlap"
    else:
        error_type = "type1"
        subtype = "small_gap" if gap_size < 1_000 else (
            "medium_gap" if gap_size < 50_000 else "large_gap"
        )

    anchor_quality = float(features["left_anchor_quality"]) + float(features["right_anchor_quality"])
    quality_factor = min(anchor_quality / 1_000_000.0, 1.0)
    distance_factor = 1.0 if max(int(features["left_distance"]), int(features["right_distance"])) <= 10_000 else (
        0.9 if max(int(features["left_distance"]), int(features["right_distance"])) <= 100_000 else 0.5
    )
    base = {"type1": 0.55, "type2": 0.75, "type3": 0.70, "type4": 0.70, "type5": 0.85, "type6": 0.80}[error_type]
    confidence_score = min(1.0, 0.45 * base + 0.35 * quality_factor + 0.20 * distance_factor)
    if error_type in {"type2", "type3", "type5", "type6"}:
        confidence_score = max(confidence_score, 0.60)
    return error_type, subtype, sorted(set(feature_names)), confidence_score



def _step3_edit_scope_decision(
    error_type: str,
    features: dict[str, object],
    start: int,
    end: int,
) -> tuple[bool, str]:
    """Reject overlap-driven automatic edits that greatly exceed their evidence."""
    edit_length = max(1, end - start + 1)
    if error_type not in {"type4", "type5"} or edit_length <= CORRECTION_LARGE_EDIT_BP:
        return True, ""
    overlap_length = max(
        int(features.get("query_overlap_length", 0)),
        int(features.get("ref_overlap_length", 0)),
    )
    if overlap_length > 0 and edit_length > overlap_length * CORRECTION_MAX_OVERLAP_EDIT_RATIO:
        return False, "automatic_edit_exceeds_overlap_evidence"
    return True, ""



def _exact_suffix_prefix_by_left_trim(
    left_sequence: str,
    right_sequence: str,
    max_overlap: int,
    max_left_trim: int,
) -> list[int]:
    """Return exact terminal overlaps for every left trim in one O(n) scan."""
    maximum_trim = min(max_left_trim, max(0, len(left_sequence) - 1))
    results = [0] * (maximum_trim + 1)
    limit = min(max_overlap, len(left_sequence), len(right_sequence))
    if limit <= 0:
        return results
    pattern = right_sequence[:limit].upper()
    prefix = [0] * len(pattern)
    for index in range(1, len(pattern)):
        matched = prefix[index - 1]
        while matched and pattern[index] != pattern[matched]:
            matched = prefix[matched - 1]
        if pattern[index] == pattern[matched]:
            matched += 1
        prefix[index] = matched

    scan_start = max(0, len(left_sequence) - max_overlap - maximum_trim)
    boundaries = {
        len(left_sequence) - left_trim: left_trim
        for left_trim in range(maximum_trim + 1)
    }
    matched = 0
    for absolute_index, base in enumerate(
        left_sequence[scan_start:].upper(), start=scan_start
    ):
        while matched and base != pattern[matched]:
            matched = prefix[matched - 1]
        if base == pattern[matched]:
            matched += 1
        boundary = absolute_index + 1
        left_trim = boundaries.get(boundary)
        if left_trim is not None:
            results[left_trim] = matched
        if matched == len(pattern):
            matched = prefix[matched - 1]
    return results



def _longest_exact_suffix_prefix(
    left_sequence: str,
    right_sequence: str,
    max_overlap: int,
) -> int:
    """Return the longest exact left-suffix/right-prefix overlap in O(n)."""
    return _exact_suffix_prefix_by_left_trim(
        left_sequence, right_sequence, max_overlap, 0
    )[0]



def _adjacent_primary_segments(
    path: list[dict[str, object]],
    gap: dict[str, object],
    primary_dataset: str,
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Resolve the exact source-gap-source triplet around one q gap."""
    gap_start0 = int(gap["start0"])
    gap_end0 = int(gap["end0"])
    cursor = 0
    left: dict[str, object] | None = None
    right: dict[str, object] | None = None
    exact_gap = False
    for segment in path:
        segment_end = cursor + int(segment["length"])
        if segment_end == gap_start0 and segment["segment_kind"] == "source":
            left = segment
        if (
            cursor == gap_start0
            and segment_end == gap_end0
            and segment["segment_kind"] == "gap"
        ):
            exact_gap = True
        if cursor == gap_end0 and segment["segment_kind"] == "source":
            right = segment
        cursor = segment_end
    if not exact_gap or left is None or right is None:
        return None
    if (
        str(left["dataset_name"]) != primary_dataset
        or str(right["dataset_name"]) != primary_dataset
        or str(left["contig_name"]) == str(right["contig_name"])
    ):
        return None
    return left, right



def promote_direct_primary_overlap_merges(
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    input_paths: dict[str, list[dict[str, object]]],
    sources: dict[tuple[str, str], str],
    primary_dataset: str,
    *,
    min_overlap: int = PRIMARY_OVERLAP_MIN_BP,
    max_overlap: int = PRIMARY_OVERLAP_MAX_BP,
    max_left_trim: int = PRIMARY_OVERLAP_MAX_LEFT_TRIM,
) -> None:
    """Promote safe Type5 gaps to primary-only direct overlap deletions.

    A flush suffix-prefix match always wins.  Trimming a short unsupported
    left tail is considered only when no flush overlap reaches ``min_overlap``.
    """
    gaps_by_key = {(str(row["chr"]), str(row["object_id"])): row for row in gaps}
    overlap_by_gap: dict[tuple[str, str], dict[str, object] | None] = {}
    for candidate in candidates:
        if candidate.get("outcome") != "candidate" or candidate.get("error_type") != "type5":
            continue
        key = (str(candidate["chr"]), str(candidate["object_id"]))
        if key not in overlap_by_gap:
            gap = gaps_by_key[key]
            adjacent = _adjacent_primary_segments(
                input_paths[str(candidate["chr"])], gap, primary_dataset
            )
            resolution: dict[str, object] | None = None
            if adjacent is not None:
                left, right = adjacent
                left_length = int(left["length"])
                right_length = int(right["length"])
                left_sequence = path_sequence(
                    slice_path(
                        [left],
                        max(0, left_length - max_overlap - max_left_trim),
                        left_length,
                    ),
                    sources,
                )
                right_sequence = path_sequence(
                    slice_path([right], 0, min(right_length, max_overlap)),
                    sources,
                )
                maximum_trim = min(max_left_trim, max(0, left_length - 1))
                overlaps = _exact_suffix_prefix_by_left_trim(
                    left_sequence,
                    right_sequence,
                    max_overlap,
                    maximum_trim,
                )
                selected: tuple[int, int] | None = None
                if overlaps[0] >= right_length:
                    # Do not manufacture a one-base right remainder by shifting
                    # the left boundary when the flush overlap consumes it all.
                    selected = None
                elif min_overlap <= overlaps[0]:
                    selected = (0, overlaps[0])
                else:
                    shifted = [
                        (overlap, -left_trim, left_trim)
                        for left_trim, overlap in enumerate(overlaps[1:], start=1)
                        if min_overlap <= overlap < right_length
                    ]
                    if shifted:
                        overlap, _negative_trim, left_trim = max(shifted)
                        selected = (left_trim, overlap)
                if selected is not None:
                    left_trim, right_trim = selected
                    resolution = {
                        "left": left,
                        "right": right,
                        "left_trim": left_trim,
                        "right_trim": right_trim,
                    }
            overlap_by_gap[key] = resolution

        resolution = overlap_by_gap[key]
        if resolution is None:
            continue
        gap = gaps_by_key[key]
        left = resolution["left"]
        right = resolution["right"]
        left_trim = int(resolution["left_trim"])
        right_trim = int(resolution["right_trim"])
        feature_names = list(candidate.get("error_features", []))
        feature_names.extend(
            [
                f"direct_primary_overlap_{right_trim}",
                f"junction_policy_{PRIMARY_OVERLAP_POLICY}",
                f"left_trim_{left_trim}",
                f"right_trim_{right_trim}",
            ]
        )
        candidate.update(
            {
                "input_start": int(gap["start0"]) + 1 - left_trim,
                "input_end": int(gap["end0"]) + right_trim,
                "trim_left": left_trim,
                "trim_right": right_trim,
                "fill_length": 0,
                "reason": "direct_primary_overlap_keep_left_trim_right",
                "classification_reason": "direct_primary_overlap_keep_left_trim_right",
                "error_features": sorted(set(feature_names)),
                "error_features_json": canonical_json(sorted(set(feature_names))),
                "direct_primary_overlap": True,
                "direct_overlap_bp": right_trim,
                "junction_policy": PRIMARY_OVERLAP_POLICY,
                "primary_left_dataset": left["dataset_name"],
                "primary_left_contig": left["contig_name"],
                "primary_left_orientation": left["orientation"],
                "primary_right_dataset": right["dataset_name"],
                "primary_right_contig": right["contig_name"],
                "primary_right_orientation": right["orientation"],
            }
        )



def _step3_project_ref_interval(row: dict[str, object], ref_start: int, ref_end: int) -> tuple[int, int]:
    ref_min, ref_max = int(row["ref_min"]), int(row["ref_max"])
    query_min, query_max = int(row["query_min"]), int(row["query_max"])
    ref_span = max(1, ref_max - ref_min)
    query_span = max(1, query_max - query_min)
    if row["orientation"] == "+":
        start = query_min + int((ref_start - ref_min) * query_span / ref_span)
        end = query_min + int((ref_end - ref_min) * query_span / ref_span)
    else:
        start = query_max - int((ref_end - ref_min) * query_span / ref_span)
        end = query_max - int((ref_start - ref_min) * query_span / ref_span)
    return min(start, end), max(start, end)



def _step3_replace_region(
    gap_pos: int,
    gap_end: int,
    left: dict[str, object],
    right: dict[str, object] | None,
    error_type: str,
) -> tuple[int, int, str]:
    if right is None:
        return int(left["query_min"]), int(left["query_max"]), "crossing_alignment_error_region"
    if error_type in {"type1", "type6"}:
        return int(left["query_max"]) + 1, int(right["query_min"]) - 1, (
            "complex_conflict" if error_type == "type6" else "simple_gap"
        )
    if error_type == "type2":
        reverse_anchor = left if left["orientation"] == "-" else right
        return int(reverse_anchor["query_min"]), int(reverse_anchor["query_max"]), "direction_conflict"
    if error_type in {"type3", "type4"}:
        shorter = left if int(left["query_aligned"]) <= int(right["query_aligned"]) else right
        return int(shorter["query_min"]), int(shorter["query_max"]), (
            "reference_contig_conflict" if error_type == "type3" else "reference_overlap"
        )
    if error_type == "type5":
        overlap_start = max(int(left["ref_min"]), int(right["ref_min"]))
        overlap_end = min(int(left["ref_max"]), int(right["ref_max"]))
        overlap_row = right
        query_start, query_end = _step3_project_ref_interval(overlap_row, overlap_start, overlap_end)
        if overlap_row["orientation"] == "+":
            return query_start, query_end + CORRECTION_MARGIN, "reference_overlap_with_margin"
        return query_start, query_end + CORRECTION_MARGIN, "reference_overlap_with_margin"
    return gap_pos, gap_end, "unclassified_structural_error"



def _step3_repair_decision(
    error_type: str,
    confidence_score: float,
    left: dict[str, object],
    right: dict[str, object] | None,
    start: int,
    end: int,
    repair_mode: str,
) -> tuple[bool, str]:
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    if right is None:
        return True, "crossing alignment is an error-region anchor"
    anchor_distance = int(right["query_min"]) - int(left["query_max"])
    large_distance = anchor_distance > CORRECTION_SEARCH_RANGE
    if not large_distance and confidence_score >= 0.40:
        return True, "conservative_conditions_met"
    if repair_mode == "aggressive":
        anchor_length = int(left["query_aligned"]) + int(right["query_aligned"])
        replacement_length = max(1, end - start + 1)
        if anchor_length > replacement_length:
            return True, "aggressive_sufficient_anchors"
    return False, "repair_mode_conditions_not_met"



def _step3_anchor_pairs(
    gap_pos: int,
    chromosome_alignments: list[dict[str, object]],
    coordinate_index: AlignmentCoordinateIndex | None = None,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    lefts: list[dict[str, object]] = []
    rights: list[dict[str, object]] = []
    for window in range(100_000, CORRECTION_SEARCH_RANGE + 100_000, 100_000):
        if coordinate_index is not None:
            lefts, rights = coordinate_index.anchors(gap_pos, window)
        else:
            lefts = [
                row
                for row in chromosome_alignments
                if int(row["query_max"]) < gap_pos
                and (
                    abs(int(row["query_min"]) - gap_pos) <= window
                    or abs(int(row["query_max"]) - gap_pos) <= window
                )
            ]
            rights = [
                row
                for row in chromosome_alignments
                if int(row["query_min"]) > gap_pos
                and (
                    abs(int(row["query_min"]) - gap_pos) <= window
                    or abs(int(row["query_max"]) - gap_pos) <= window
                )
            ]
        if lefts and rights:
            break
    if not lefts or not rights:
        return []
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    grouped_left: dict[str, list[dict[str, object]]] = defaultdict(list)
    grouped_right: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in lefts:
        grouped_left[str(row["ref_record"])].append(row)
    for row in rights:
        grouped_right[str(row["ref_record"])].append(row)
    # Dict insertion order follows the merged coords stream, matching the
    # upstream analyzer's first-supporting-record boundary choice.
    for ref_record in grouped_left:
        if ref_record not in grouped_right:
            continue
        left = max(grouped_left[ref_record], key=lambda row: int(row["query_max"]))
        right = min(grouped_right[ref_record], key=lambda row: int(row["query_min"]))
        pairs.append((left, right))
    return pairs



def build_correction_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    repair_mode: str = DEFAULT_REPAIR_MODE,
    *,
    structural_target: str = "ordinary_donor",
    use_index: bool = False,
) -> list[dict[str, object]]:
    """Build Server-native Type1--Type6 CorrectRefill candidates.

    The standalone LGZ analyzer operates on implicit files.  This adapter uses
    the already parsed, hash-bound MUMmer rows so source cards and donor-set
    coordinates remain owned by GPM.
    """
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for alignment in alignments:
        by_chr[str(alignment["chr"])].append(alignment)
    coordinate_indexes = {chromosome: AlignmentCoordinateIndex(rows) for chromosome, rows in by_chr.items()} if use_index else {}
    candidates: list[dict[str, object]] = []
    for gap in gaps:
        chromosome = str(gap["chr"])
        gap_pos = (int(gap["start0"]) + int(gap["end0"]) + 1) // 2
        chromosome_alignments = by_chr.get(chromosome, [])
        coordinate_index = coordinate_indexes.get(chromosome)
        crossing = coordinate_index.crossing(gap_pos) if coordinate_index is not None else [
            row for row in chromosome_alignments
            if int(row["query_min"]) <= gap_pos <= int(row["query_max"])
        ]
        prototypes: list[tuple[dict[str, object], dict[str, object] | None]] = []
        if crossing:
            prototypes.append((sorted(
                crossing,
                key=lambda row: (-float(row["identity"]), -int(row["query_aligned"]), int(row["line_number"])),
            )[0], None))
        else:
            prototypes.extend(_step3_anchor_pairs(gap_pos, chromosome_alignments, coordinate_index))
        for left, right in prototypes:
            features = _step3_alignment_features(gap_pos, left, right)
            error_type, subtype, feature_names, confidence_score = _step3_classify_features(features)
            start, end, reason = _step3_replace_region(
                gap_pos, int(gap["end0"]), left, right, error_type
            )
            # Upstream reasons from the gap midpoint and normalizes the
            # surviving N run afterward. GPM records an equivalent replayable
            # edit that explicitly covers the complete origin gap.
            start = min(start, int(gap["start0"]) + 1)
            end = max(end, int(gap["end0"]))
            query_length = int(left["query_length"])
            start = max(1, min(start, query_length))
            end = max(start, min(end, query_length))
            eligible, repair_reason = _step3_repair_decision(
                error_type, confidence_score, left, right, start, end, repair_mode
            )
            anchor_pair_executable = right is None or (
                bool(features["ref_contig_match"])
                and bool(features["direction_match"])
            )
            edit_scope_safe, edit_scope_reason = _step3_edit_scope_decision(
                error_type, features, start, end
            )
            if not edit_scope_safe:
                eligible = False
                repair_reason = edit_scope_reason
            if not anchor_pair_executable:
                eligible = False
                repair_reason = "anchor_pair_source_or_orientation_conflict"
            ref_start = int(left["ref_min"])
            ref_end = int(left["ref_max"])
            if right is not None and str(left["ref_record"]) == str(right["ref_record"]):
                ref_start = min(ref_start, int(right["ref_min"]))
                ref_end = max(ref_end, int(right["ref_max"]))
            member = members_by_record[str(left["ref_record"])]
            source_start, source_end = member_source_interval(member, ref_start, ref_end)
            payload = {
                "stage": "step3",
                "object_id": gap["object_id"],
                "action": "replace" if error_type in {"type1", "type3"} else (
                    "delete" if error_type in {"type4", "type5"} else "correct_boundary"
                ),
                "member_id": member["member_id"],
                "source_start": source_start,
                "source_end": source_end,
                "input_start": start,
                "input_end": end,
                "error_type": error_type,
                "error_subtype": subtype,
                "repair_mode": repair_mode,
            }
            action = str(payload["action"])
            candidates.append(
                {
                    "candidate_id": stable_id("step3-correction", payload, 24),
                    "stage": "step3",
                    "chr": chromosome,
                    "object_id": gap["object_id"],
                    "action": action,
                    "member_id": member["member_id"],
                    "ref_record": left["ref_record"],
                    "source_dataset": member["dataset_name"],
                    "source_contig": member["contig_name"],
                    "source_start": source_start,
                    "source_end": source_end,
                    "orientation": left["orientation"],
                    "target_start": int(gap["start0"]) + 1,
                    "target_end": int(gap["end0"]),
                    "input_start": start,
                    "input_end": end,
                    "trim_left": int(gap["start0"]) - (start - 1),
                    "trim_right": end - int(gap["end0"]),
                    "fill_length": NORMALIZED_GAP_LENGTH,
                    "identity": (
                        float(left["identity"])
                        if right is None
                        else (float(left["identity"]) + float(right["identity"])) / 2
                    ),
                    "aligned_length": int(left["query_aligned"])
                    + (0 if right is None else int(right["query_aligned"])),
                    "mapq": 0,
                    "left_line": left["line_number"],
                    "right_line": "" if right is None else right["line_number"],
                    "validation_passed": anchor_pair_executable,
                    "outcome": "candidate" if eligible else "rejected",
                    "reason": reason if eligible else repair_reason,
                    "classification_reason": reason,
                    "error_type": error_type,
                    "error_subtype": subtype,
                    "error_features": feature_names,
                    "error_features_json": canonical_json(feature_names),
                    "confidence": "high" if confidence_score >= 0.70 else "medium" if confidence_score >= 0.40 else "low",
                    "confidence_score": confidence_score,
                    "gap_in_error_region": True,
                    "repair_mode": repair_mode,
                    "repair_reason": repair_reason,
                    "eligible": eligible,
                    "structural_target": structural_target,
                    # Structural correction uses the alignment only as
                    # evidence; it inserts a normalized gap, not donor bases.
                    "source_consumable": False,
                    "event_id": "",
                    "final_path_segment_id": "",
                }
            )
    return candidates



def reject_ambiguous_reference_anchors(
    candidates: list[dict[str, object]],
    alignments: list[dict[str, object]],
    *,
    minimum_query_overlap_ratio: float = 0.50,
    minimum_span_ratio: float = 0.80,
    maximum_identity_drop: float = 0.01,
) -> None:
    """Reject structural edits whose selected reference anchor is non-unique.

    Upstream exposes all Type1--Type6 proposals, but a repeat-supported anchor
    must not authorize a destructive edit.  An anchor is ambiguous when a
    comparable alignment covers the same query interval on another reference
    record, or on a disjoint locus of the same record.
    """
    rows_by_chr_line = {
        (str(row["chr"]), int(row["line_number"])): row for row in alignments
    }
    rows_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in alignments:
        rows_by_chr[str(row["chr"])].append(row)
    for candidate in candidates:
        if (
            candidate.get("outcome") != "candidate"
            or candidate.get("structural_target") != "reference"
        ):
            continue
        selected = [
            rows_by_chr_line.get((str(candidate["chr"]), int(line_number)))
            for line_number in (candidate.get("left_line"), candidate.get("right_line"))
            if str(line_number).strip()
        ]
        ambiguity: dict[str, object] | None = None
        for anchor in (row for row in selected if row is not None):
            anchor_start = int(anchor["query_min"])
            anchor_end = int(anchor["query_max"])
            anchor_span = max(1, anchor_end - anchor_start + 1)
            for alternative in rows_by_chr[str(candidate["chr"])]:
                if int(alternative["line_number"]) == int(anchor["line_number"]):
                    continue
                overlap = max(
                    0,
                    min(anchor_end, int(alternative["query_max"]))
                    - max(anchor_start, int(alternative["query_min"]))
                    + 1,
                )
                if overlap / anchor_span < minimum_query_overlap_ratio:
                    continue
                if int(alternative["query_aligned"]) < anchor_span * minimum_span_ratio:
                    continue
                if float(alternative["identity"]) < float(anchor["identity"]) - maximum_identity_drop:
                    continue
                different_record = str(alternative["ref_record"]) != str(anchor["ref_record"])
                disjoint_locus = not intervals_overlap(
                    int(anchor["ref_min"]),
                    int(anchor["ref_max"]),
                    int(alternative["ref_min"]),
                    int(alternative["ref_max"]),
                )
                if different_record or disjoint_locus:
                    ambiguity = alternative
                    break
            if ambiguity is not None:
                break
        if ambiguity is None:
            continue
        candidate["outcome"] = "rejected"
        candidate["eligible"] = False
        candidate["validation_passed"] = False
        candidate["reason"] = (
            "non_unique_reference_anchor:"
            f"{ambiguity['ref_record']}:{ambiguity['line_number']}"
        )
        candidate["repair_reason"] = candidate["reason"]
        features = sorted(
            set([*candidate.get("error_features", []), "non_unique_reference_anchor"])
        )
        candidate["error_features"] = features
        candidate["error_features_json"] = canonical_json(features)



def _covered_length(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    total = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start + 1
        current_start, current_end = start, end
    return total + current_end - current_start + 1



def build_dominated_terminal_component_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    reference_lengths: dict[str, int],
    input_records: dict[str, str],
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> list[dict[str, object]]:
    """Build safe component drops backed by a near-complete reference backbone.

    This handles the case where a terminal repeat-bearing prefix/suffix is
    attached to an independently near-complete chromosome component.  The
    ambiguous repeat is evidence that the small terminal component is not a
    trustworthy extension; it is never used as a boundary anchor into the
    full backbone.
    """
    rows_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    gaps_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in alignments:
        if float(row["identity"]) >= 0.90 and int(row["query_aligned"]) >= MUMMER_MIN_ALIGNMENT:
            rows_by_chr[str(row["chr"])].append(row)
    for gap in gaps:
        gaps_by_chr[str(gap["chr"])].append(gap)

    candidates: list[dict[str, object]] = []
    for chromosome, chromosome_gaps in gaps_by_chr.items():
        reference_length = reference_lengths.get(chromosome)
        if not reference_length:
            continue
        ordered_gaps = sorted(chromosome_gaps, key=lambda row: int(row["start0"]))
        sequence_length = len(input_records[chromosome])
        components: list[tuple[int, int]] = []
        cursor = 0
        for gap in ordered_gaps:
            components.append((cursor, int(gap["start0"])))
            cursor = int(gap["end0"])
        components.append((cursor, sequence_length))

        def metrics(component: tuple[int, int]) -> dict[str, object]:
            start0, end0 = component
            component_length = max(1, end0 - start0)
            target_rows = []
            cross_rows = []
            query_intervals: list[tuple[int, int]] = []
            reference_intervals: list[tuple[int, int]] = []
            for row in rows_by_chr.get(chromosome, []):
                query_start = max(start0 + 1, int(row["query_min"]))
                query_end = min(end0, int(row["query_max"]))
                if query_end < query_start:
                    continue
                overlap = query_end - query_start + 1
                if overlap < MUMMER_MIN_ALIGNMENT:
                    continue
                if str(row["ref_record"]) == chromosome:
                    target_rows.append(row)
                    query_intervals.append((query_start, query_end))
                    reference_intervals.append((int(row["ref_min"]), int(row["ref_max"])))
                else:
                    cross_rows.append(row)
            best = max(
                target_rows,
                key=lambda row: (
                    int(row["query_aligned"]),
                    float(row["identity"]),
                    -int(row["line_number"]),
                ),
                default=None,
            )
            return {
                "length": component_length,
                "query_coverage": _covered_length(query_intervals) / component_length,
                "reference_coverage": _covered_length(reference_intervals) / reference_length,
                "target_rows": target_rows,
                "cross_rows": cross_rows,
                "best": best,
                "ref_min": min((int(row["ref_min"]) for row in target_rows), default=0),
                "ref_max": max((int(row["ref_max"]) for row in target_rows), default=0),
            }

        component_metrics = [metrics(component) for component in components]
        for gap_index, gap in enumerate(ordered_gaps):
            possibilities = []
            if gap_index == 0:
                possibilities.append(("left", components[0], component_metrics[0], component_metrics[1]))
            if gap_index == len(ordered_gaps) - 1:
                possibilities.append(
                    (
                        "right",
                        components[-1],
                        component_metrics[-1],
                        component_metrics[-2],
                    )
                )
            for side, dominated_component, dominated, backbone in possibilities:
                dominated_best = dominated["best"]
                backbone_best = backbone["best"]
                if dominated_best is None or backbone_best is None:
                    continue
                if (
                    int(backbone["length"]) < 0.70 * reference_length
                    or float(backbone["query_coverage"]) < 0.75
                    or float(backbone["reference_coverage"]) < 0.75
                    or int(dominated["length"]) > 0.25 * reference_length
                    or not dominated["cross_rows"]
                ):
                    continue
                containment_tolerance = max(100_000, int(0.01 * reference_length))
                if (
                    int(dominated["ref_min"]) < int(backbone["ref_min"]) - containment_tolerance
                    or int(dominated["ref_max"]) > int(backbone["ref_max"]) + containment_tolerance
                ):
                    continue
                if side == "left":
                    input_start, input_end = 1, int(gap["end0"])
                    trim_left, trim_right = int(gap["start0"]), 0
                else:
                    input_start, input_end = int(gap["start0"]) + 1, sequence_length
                    trim_left, trim_right = 0, sequence_length - int(gap["end0"])
                payload = {
                    "stage": "step3",
                    "object_id": gap["object_id"],
                    "policy": DOMINATED_COMPONENT_POLICY,
                    "side": side,
                    "input_start": input_start,
                    "input_end": input_end,
                    "backbone_line": backbone_best["line_number"],
                }
                features = [
                    "ambiguous_terminal_component",
                    "near_complete_reference_backbone",
                    f"dominated_{side}_component",
                    f"junction_policy_{DOMINATED_COMPONENT_POLICY}",
                ]
                candidates.append(
                    {
                        "candidate_id": stable_id("step3-dominated-component", payload, 24),
                        "stage": "step3",
                        "chr": chromosome,
                        "object_id": gap["object_id"],
                        "action": "delete",
                        "member_id": f"reference:{chromosome}",
                        "ref_record": chromosome,
                        "source_dataset": "__reference__",
                        "source_contig": chromosome,
                        "source_start": int(dominated["ref_min"]),
                        "source_end": int(dominated["ref_max"]),
                        "orientation": dominated_best["orientation"],
                        "target_start": int(gap["start0"]) + 1,
                        "target_end": int(gap["end0"]),
                        "input_start": input_start,
                        "input_end": input_end,
                        "trim_left": trim_left,
                        "trim_right": trim_right,
                        "fill_length": 0,
                        "identity": min(
                            float(dominated_best["identity"]),
                            float(backbone_best["identity"]),
                        ),
                        "aligned_length": int(dominated_best["query_aligned"])
                        + int(backbone_best["query_aligned"]),
                        "mapq": 0,
                        "left_line": dominated_best["line_number"],
                        "right_line": backbone_best["line_number"],
                        "validation_passed": True,
                        "outcome": "candidate",
                        "reason": "reference_dominated_terminal_component",
                        "classification_reason": "reference_dominated_terminal_component",
                        "error_type": "type5",
                        "error_subtype": "dominated_terminal_component",
                        "error_features": features,
                        "error_features_json": canonical_json(features),
                        "confidence": "high",
                        "confidence_score": 0.95,
                        "gap_in_error_region": True,
                        "repair_mode": repair_mode,
                        "repair_reason": "near_complete_backbone_with_ambiguous_terminal_repeat",
                        "eligible": True,
                        "structural_target": "reference",
                        "source_consumable": False,
                        "junction_policy": DOMINATED_COMPONENT_POLICY,
                        "dominated_side": side,
                        "event_id": "",
                        "final_path_segment_id": "",
                    }
                )
    return candidates



def correction_usage_rows(
    run_id: str,
    donor_set_id: str,
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        event_id = stable_id("event", [run_id, "step3", candidate["object_id"], "correction"], 24)
        candidate["event_id"] = event_id
        if not candidate.get("source_consumable", True):
            candidate["usage_ids"] = []
            continue
        candidate_usage_id = stable_id("usage-candidate", ["step3", candidate["candidate_id"]], 22)
        outcome_usage_id = stable_id("usage-outcome", ["step3", candidate["candidate_id"]], 22)
        rows.extend(
            [
                {
                    "usage_id": candidate_usage_id,
                    "donor_set_id": donor_set_id,
                    "member_id": candidate["member_id"],
                    "source_dataset": candidate["source_dataset"],
                    "source_contig": candidate["source_contig"],
                    "source_start": candidate["source_start"],
                    "source_end": candidate["source_end"],
                    "stage": "step3",
                    "status": "candidate",
                    "event_id": event_id,
                    "final_path_segment_id": "",
                    "reason": "mummer_structural_candidate",
                },
                {
                    "usage_id": outcome_usage_id,
                    "donor_set_id": donor_set_id,
                    "member_id": candidate["member_id"],
                    "source_dataset": candidate["source_dataset"],
                    "source_contig": candidate["source_contig"],
                    "source_start": candidate["source_start"],
                    "source_end": candidate["source_end"],
                    "stage": "step3",
                    "status": "accepted" if candidate["outcome"] == "accepted" else candidate["outcome"],
                    "event_id": event_id,
                    "final_path_segment_id": "",
                    "reason": candidate["reason"],
                },
            ]
        )
        candidate["usage_ids"] = [candidate_usage_id, outcome_usage_id]
    return rows



def apply_corrections(
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, str],
    list[dict[str, object]],
    dict[tuple[str, int, int], dict[str, object]],
]:
    accepted_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["outcome"] == "accepted":
            accepted_by_chr[str(candidate["chr"])].append(candidate)
    output_paths: dict[str, list[dict[str, object]]] = {}
    output_records: dict[str, str] = {}
    prototypes: list[dict[str, object]] = []
    gap_origin_by_output: dict[tuple[str, int, int], dict[str, object]] = {}
    for chromosome in chromosome_order:
        sequence = input_records[chromosome]
        path = input_paths[chromosome]
        accepted = sorted(accepted_by_chr.get(chromosome, []), key=lambda row: int(row["input_start"]))
        chromosome_gaps = [gap for gap in gaps if gap["chr"] == chromosome]
        gaps_by_object = {str(gap["object_id"]): gap for gap in chromosome_gaps}
        cursor = 0
        output_cursor = 0
        result_path: list[dict[str, object]] = []
        # This writer is shared by Step2 and Step3. Reject incomplete or
        # ambiguous provenance before creating paths/origins, rather than
        # silently overwriting a repaired GAP with a supposedly untouched one.
        accepted_by_object: dict[str, dict[str, object]] = {}
        for candidate in accepted:
            primary = str(candidate["object_id"])
            start, end = int(candidate["input_start"]), int(candidate["input_end"])
            associated_gap = gaps_by_object.get(primary)
            if associated_gap is None:
                fail(f"Step3 correction references an unknown q2 gap: {candidate['candidate_id']}")
            if start > int(associated_gap["start0"]) + 1 or end < int(associated_gap["end0"]):
                fail(f"Step3 correction edit does not cover associated q2 gap: {candidate['candidate_id']}")
            actual = []
            for gap in chromosome_gaps:
                if not intervals_overlap(start, end, int(gap["start0"]) + 1, int(gap["end0"])):
                    continue
                if start > int(gap["start0"]) + 1 or end < int(gap["end0"]):
                    fail(f"correction partially overlaps origin gap: {candidate['candidate_id']}:{gap['object_id']}")
                actual.append(str(gap["object_id"]))
            declared = [str(value) for value in candidate.get("covered_object_ids", [primary])]
            if len(declared) != len(set(declared)) or set(declared) != set(actual):
                fail(f"invalid correction gap coverage: {candidate['candidate_id']}; declared={declared}; actual={actual}")
            for object_id in declared:
                if object_id in accepted_by_object:
                    fail(f"multiple accepted corrections claim origin gap: {object_id}")
                accepted_by_object[object_id] = candidate
        edit_deltas: list[tuple[int, int]] = []
        for candidate in accepted:
            start0 = int(candidate["input_start"]) - 1
            end0 = int(candidate["input_end"])
            covered_object_ids = [
                str(value)
                for value in candidate.get(
                    "covered_object_ids", [str(candidate["object_id"])]
                )
            ]
            primary = str(candidate["object_id"])
            covered_object_ids = [primary, *[value for value in covered_object_ids if value != primary]]
            if start0 < cursor or end0 < start0 or end0 > len(sequence):
                fail(f"overlapping or invalid Step3 correction edit: {candidate['candidate_id']}")
            result_path.extend(slice_path(path, cursor, start0))
            output_cursor += start0 - cursor
            gapless_junction = candidate.get("junction_policy") in {
                PRIMARY_OVERLAP_POLICY,
                DOMINATED_COMPONENT_POLICY,
            }
            replacement_length = 0 if gapless_junction else NORMALIZED_GAP_LENGTH
            edit_deltas.append((end0, replacement_length - (end0 - start0)))
            output_start = output_cursor + 1
            if gapless_junction:
                # Anchor at the first retained right-side base, or the last
                # retained left-side base when deleting a terminal component.
                # The edit inserts no sequence and creates no corrected gap.
                if end0 == len(sequence):
                    if output_cursor < 1:
                        fail(f"gapless correction would remove the entire chromosome: {candidate['candidate_id']}")
                    output_start = output_cursor
                output_end = output_start
            else:
                gap_segment = {
                    "segment_kind": "gap",
                    "length": NORMALIZED_GAP_LENGTH,
                    "dataset_name": "",
                    "contig_name": "",
                    "source_start": None,
                    "source_end": None,
                    "orientation": "",
                    "source_card_key": "",
                    # Gap path segments are sequence placeholders, not evidence
                    # carriers.  The correction event owns the supporting
                    # evidence and keeps the audit link without violating the
                    # q-segment contract.
                    "evidence_ids": [],
                    "origin_object_ids": covered_object_ids,
                }
                result_path.append(gap_segment)
                output_end = output_start + NORMALIZED_GAP_LENGTH - 1
                output_cursor = output_end
            cursor = end0
            prototype = {
                "candidate": candidate,
                "chr": chromosome,
                "object_id": candidate["object_id"],
                "input_start": int(candidate["input_start"]),
                "input_end": int(candidate["input_end"]),
                "intermediate_start": output_start,
                "intermediate_end": output_end,
                "replacement_length": replacement_length,
            }
            prototypes.append(prototype)
            if not gapless_junction:
                key = (chromosome, output_start - 1, output_end)
                if key in gap_origin_by_output:
                    fail(f"correction output gap origins collide: {key}")
                gap_origin_by_output[key] = {
                    "object_id": candidate["object_id"],
                    "q2_start": int(candidate["input_start"]),
                    "q2_end": int(candidate["input_end"]),
                    "correction_candidate_id": candidate["candidate_id"],
                    "coalesced_object_ids": covered_object_ids[1:],
                }
        result_path.extend(slice_path(path, cursor, len(sequence)))
        output_paths[chromosome] = result_path
        output_records[chromosome] = path_sequence(result_path, sources)
        for gap in chromosome_gaps:
            if str(gap["object_id"]) in accepted_by_object:
                continue
            # Use the bytes actually emitted above, not a candidate's fill
            # hint (which can differ for gapless/normalized structural edits).
            shift = sum(delta for end, delta in edit_deltas if end <= int(gap["start0"]))
            output_start0 = int(gap["start0"]) + shift
            output_end0 = int(gap["end0"]) + shift
            key = (chromosome, output_start0, output_end0)
            if key in gap_origin_by_output:
                fail(f"correction output gap origins collide: {key}")
            gap_origin_by_output[key] = {
                "object_id": gap["object_id"],
                "q2_start": int(gap["start0"]) + 1,
                "q2_end": int(gap["end0"]),
                "correction_candidate_id": "",
            }
    return output_paths, output_records, prototypes, gap_origin_by_output
