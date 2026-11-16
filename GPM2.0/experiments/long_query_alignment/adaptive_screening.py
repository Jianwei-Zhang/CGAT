"""Internal adaptive-policy calibration; not a production default yet.

Size selects a bounded pilot, never a sensitivity change. A candidate is eligible
only from completed, comparable measurements and per-query loss checks. Limits
are provisional experimental acceptance budgets, not biological accuracy claims.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import math

POLICY = "adaptive-screening-v1"
LONG_QUERY_LIMIT = (1 << 28) - 1


@dataclass(frozen=True)
class Limits:
    reference_bases: int = 5_000_000_000
    long_record_bases: int = 20_000_000
    minimum_speedup: float = 2.0
    global_loss_fraction: float = 0.005
    per_query_loss_fraction: float = 0.02
    assignment_coverage: float = 0.60
    assignment_margin: float = 0.10


def screening_gate(reference_bases, records, limits=Limits()):
    if type(reference_bases) is not int or reference_bases <= 0:
        raise ValueError("positive reference length required")
    lengths = record_lengths(records)
    long_queries = [q for q, n in lengths.items() if n > LONG_QUERY_LIMIT]
    expensive_shape = reference_bases >= limits.reference_bases and max(lengths.values()) >= limits.long_record_bases
    reasons = []
    if long_queries:
        reasons.append("query_exceeds_packed_operation_limit")
    if expensive_shape:
        reasons.append("large_reference_and_long_queries")
    return {"policy": POLICY, "action": "bounded_pilot" if reasons else "standard",
            "reasons": reasons, "long_queries": long_queries,
            "automatic_sensitivity_change": False, "thresholds_calibrated": False,
            "limits": asdict(limits)}


def record_lengths(records):
    lengths = {}
    for row in records:
        name, length = row["name"], row["length"]
        if not isinstance(name, str) or not name or name in lengths or type(length) is not int or length <= 0:
            raise ValueError("unique named positive-length records required")
        lengths[name] = length
    if not lengths:
        raise ValueError("query records required")
    return lengths


def union_length(spans):
    total, right = 0, 0
    for start, end in sorted(spans):
        total += max(0, end - max(start, right))
        right = max(right, end)
    return total


def coverage_profile(path, records):
    """Read only a separately validated PAF; retain competing target coverage.

    Reject oversized audit inputs rather than silently truncate them. MAPQ is
    not used as a stand-alone confidence signal for multipart reference mapping.
    """
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("audit PAF exceeds 64 MiB; no automatic recommendation")
    lengths = record_lengths(records)
    spans, targets = defaultdict(list), defaultdict(lambda: defaultdict(list))
    with path.open() as stream:
        for line in stream:
            f = line.rstrip("\n").split("\t")
            if len(f) < 12 or f[0] not in lengths or int(f[1]) != lengths[f[0]]:
                raise ValueError("PAF query identity mismatch")
            start, end = int(f[2]), int(f[3])
            if not 0 <= start < end <= lengths[f[0]]:
                raise ValueError("PAF query range invalid")
            spans[f[0]].append((start, end))
            targets[f[0]][f[5]].append((start, end))
    return {q: {"length": n, "covered": union_length(spans[q]),
                "targets": {t: union_length(s) for t, s in sorted(targets[q].items())}}
            for q, n in lengths.items()}


def assignment(row, limits):
    ranked = sorted(row["targets"].items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return None
    first = ranked[0][1] / row["length"]
    second = ranked[1][1] / row["length"] if len(ranked) > 1 else 0
    if first < limits.assignment_coverage or first - second < limits.assignment_margin:
        return None
    return ranked[0][0]


def assess_loss(before, after, limits=Limits()):
    if not before or before.keys() != after.keys():
        raise ValueError("complete identical query sets required")
    losses, flips, lost_assignment, lost_queries, false_certainty = [], [], [], [], []
    for q, a in before.items():
        b = after[q]
        if a["length"] != b["length"]:
            raise ValueError("query length changed")
        for row in (a, b):
            if (type(row["length"]) is not int or row["length"] <= 0
                    or type(row["covered"]) is not int or not 0 <= row["covered"] <= row["length"]
                    or any(type(v) is not int or not 0 < v <= row["covered"] for v in row["targets"].values())):
                raise ValueError("invalid coverage evidence")
        loss = max(0, a["covered"] - b["covered"])
        if loss:
            losses.append({"query": q, "bases": loss, "fraction": loss / a["length"]})
        if a["covered"] and not b["covered"]:
            lost_queries.append(q)
        old, new = assignment(a, limits), assignment(b, limits)
        if old and new and old != new:
            flips.append(q)
        if old and not new:
            lost_assignment.append(q)
        # Pruning an alternative must not masquerade as increased confidence.
        if not old and new and len(a["targets"]) > 1:
            false_certainty.append(q)
    total = sum(r["length"] for r in before.values())
    positive_loss = sum(r["bases"] for r in losses)
    reasons = []
    if positive_loss / total > limits.global_loss_fraction:
        reasons.append("global_positive_coverage_loss")
    if any(r["fraction"] > limits.per_query_loss_fraction for r in losses):
        reasons.append("per_query_coverage_loss")
    for name, items in (("assignment_flip", flips), ("assignment_lost", lost_assignment),
                        ("mapped_query_lost", lost_queries), ("ambiguity_hidden", false_certainty)):
        if items:
            reasons.append(name)
    return {"passed": not reasons, "reasons": reasons, "coverage_losses": losses,
            "positive_loss_fraction": positive_loss / total, "assignment_flips": flips,
            "lost_assignments": lost_assignment, "lost_queries": lost_queries,
            "newly_confident_ambiguous_queries": false_certainty,
            "scientific_accuracy_proven": False}


def compare(baseline, candidate, before=None, after=None, limits=Limits()):
    result = {"policy": POLICY, "eligible": False, "limits": asdict(limits),
              "scope": "pilot_only", "production_approved": False}
    if candidate["outcome"] != "completed":
        return {**result, "reason": "candidate_not_completed"}
    if baseline["outcome"] != "completed":
        # A timed-out baseline gives a speed lower bound, NOT a quality baseline.
        if baseline["outcome"] == "timeout" and candidate["wall_seconds"] > 0:
            result["speedup_lower_bound"] = min(baseline["wall_seconds"], baseline.get("wall_budget_seconds", baseline["wall_seconds"])) / candidate["wall_seconds"]
        return {**result, "reason": "baseline_quality_unavailable"}
    for r in (baseline, candidate):
        if not math.isfinite(r["wall_seconds"]) or r["wall_seconds"] <= 0:
            raise ValueError("positive finite completed measurement required")
    if baseline["mid_occ"] == candidate["mid_occ"]:
        return {**result, "reason": "filter_threshold_unchanged"}
    if before is None or after is None:
        return {**result, "reason": "coverage_evidence_missing"}
    loss = assess_loss(before, after, limits)
    if not sum(r["covered"] for r in before.values()):
        return {**result, "reason": "baseline_has_no_mapped_evidence"}
    speedup = baseline["wall_seconds"] / candidate["wall_seconds"]
    reason = "loss_budget_exceeded" if not loss["passed"] else "insufficient_speedup" if speedup < limits.minimum_speedup else "eligible_for_expanded_validation"
    return {**result, "eligible": reason == "eligible_for_expanded_validation",
            "reason": reason, "speedup": speedup, "loss": loss}


def receipt_identity(inputs, options):
    """Scientific policy is identity, independent of directory or runtime speed."""
    return hashlib.sha256(json.dumps({"policy": POLICY, "inputs": inputs, "options": options},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
