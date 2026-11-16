"""Internal adaptive metrics and large-reference projection risk screening.

The package-bound initial-reference adapter may enable bounded ordinary calibration.
Size selects a bounded pilot, never a sensitivity change. A candidate is eligible
only from completed, comparable measurements and per-query loss checks. Limits
are provisional experimental acceptance budgets, not biological accuracy claims.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math

POLICY = "adaptive-screening-v4"
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
    maximum_anchor_spread_fraction: float = 0.20


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
    target_strands = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    qualified = defaultdict(lambda: defaultdict(lambda: {"spans": [], "anchors": [], "anchors_by_strand": {"+": [], "-": []}, "weights": {"+": 0, "-": 0}}))
    with path.open() as stream:
        for line in stream:
            f = line.rstrip("\n").split("\t")
            if len(f) < 12 or f[0] not in lengths or int(f[1]) != lengths[f[0]]:
                raise ValueError("PAF query identity mismatch")
            start, end = int(f[2]), int(f[3])
            if f[4] not in ("+", "-") or not 0 <= start < end <= lengths[f[0]]:
                raise ValueError("PAF query range invalid")
            spans[f[0]].append((start, end))
            targets[f[0]][f[5]].append((start, end))
            target_strands[f[0]][f[5]][f[4]].append((start, end))
            block = int(f[10])
            # Match assign_chr_groups.py: small hits must cover >=25% of the
            # query; otherwise the block must be >=1000 bp. Every qualifying
            # chromosome can be assigned, not just the best-scoring target.
            if block >= 1000 or block * 4 >= lengths[f[0]]:
                bucket = qualified[f[0]][f[5]]
                bucket["spans"].append((start, end))
                anchor = int(f[7]) - start + 1 if f[4] == "+" else int(f[7]) + 1 - lengths[f[0]] + end
                bucket["anchors"].append((anchor, block))
                bucket["anchors_by_strand"][f[4]].append((anchor, block))
                bucket["weights"][f[4]] += block
    return {q: {"length": n, "covered": union_length(spans[q]),
                "targets": {t: union_length(s) for t, s in sorted(targets[q].items())},
                "target_strands": {t: {strand: union_length(s) for strand, s in sorted(by_strand.items())}
                                   for t, by_strand in sorted(target_strands[q].items())},
                "assignment_candidates": {t: {"covered": union_length(b["spans"]),
                    "strand_weights": b["weights"], "anchor_start": weighted_anchor(b["anchors"]),
                    "anchor_spans": {strand: weighted_anchor_span(values) for strand, values in b["anchors_by_strand"].items() if values}}
                    for t, b in sorted(qualified[q].items())}}
            for q, n in lengths.items()}


def weighted_anchor(values):
    threshold = sum(w for _, w in values) // 2 + 1
    cumulative = 0
    for position, weight in sorted(values):
        cumulative += weight
        if cumulative >= threshold:
            return position
    raise ValueError("positive anchor weights required")


def weighted_anchor_span(values):
    """10th/90th block-weighted anchor quantiles; not a native chain proof."""
    total = sum(w for _, w in values)
    if total <= 0:raise ValueError("positive anchor weights required")
    low = high = None; cumulative = 0
    for position, weight in sorted(values):
        cumulative += weight
        if low is None and cumulative * 10 >= total:low = position
        if cumulative * 10 >= total * 9:
            high = position; break
    return [low, high]


def consumer_assignments(row, limits):
    """Projection of current assign_chr_groups.py, including multiple targets."""
    result = {}
    for target, candidate in row["assignment_candidates"].items():
        covered, weights = candidate["covered"], candidate["strand_weights"]
        if (type(covered) is not int or not 0 < covered <= row["length"]
                or set(weights) != {"+", "-"} or any(type(v) is not int or v < 0 for v in weights.values())
                or sum(weights.values()) <= 0 or type(candidate["anchor_start"]) is not int):
            raise ValueError("invalid downstream assignment evidence")
        if covered / row["length"] >= limits.assignment_coverage:
            result[target] = {"orientation": "-" if weights["-"] > weights["+"] else "+",
                              "anchor_start": candidate["anchor_start"], "covered": covered}
    return result


def assignment(row, limits):
    ranked = sorted(row["targets"].items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return None
    first = ranked[0][1] / row["length"]
    second = ranked[1][1] / row["length"] if len(ranked) > 1 else 0
    if first < limits.assignment_coverage or first - second < limits.assignment_margin:
        return None
    return ranked[0][0]


def ambiguous_assignment(row, limits):
    ranked = sorted(row["targets"].values(), reverse=True)
    return (len(ranked) > 1 and ranked[0] / row["length"] >= limits.assignment_coverage
            and (ranked[0] - ranked[1]) / row["length"] < limits.assignment_margin)


def strand_assignment(row, target, limits):
    return assignment({"length": row["length"], "targets": row["target_strands"].get(target, {})}, limits)


def assess_loss(before, after, limits=Limits(), *, require_consumer=True):
    if not before or before.keys() != after.keys():
        raise ValueError("complete identical query sets required")
    losses, flips, lost_assignment, lost_queries, false_certainty = [], [], [], [], []
    strand_flips, strand_lost, strand_hidden, strand_missing = [], [], [], []
    consumer_removed, consumer_added, consumer_flips, consumer_missing, anchors = [], [], [], [], []
    consumer_extra = []
    support_changes, support_losses = [], []
    for q, a in before.items():
        b = after[q]
        if a["length"] != b["length"]:
            raise ValueError("query length changed")
        for row in (a, b):
            if (type(row["length"]) is not int or row["length"] <= 0
                    or type(row["covered"]) is not int or not 0 <= row["covered"] <= row["length"]
                    or any(type(v) is not int or not 0 < v <= row["covered"] for v in row["targets"].values())):
                raise ValueError("invalid coverage evidence")
            if "target_strands" in row:
                if set(row["target_strands"]) != set(row["targets"]):
                    raise ValueError("incomplete target/strand evidence")
                for target, values in row["target_strands"].items():
                    if (not values or not set(values) <= {"+", "-"}
                            or any(type(v) is not int or not 0 < v <= row["targets"][target] for v in values.values())
                            or sum(values.values()) < row["targets"][target]):
                        raise ValueError("invalid target/strand coverage")
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
        if not old and new and ambiguous_assignment(a, limits):
            false_certainty.append(q)
        if "target_strands" not in a or "target_strands" not in b:
            strand_missing.append(q)
        elif old and old == new:
            old_strand, new_strand = strand_assignment(a, old, limits), strand_assignment(b, new, limits)
            if old_strand and new_strand and old_strand != new_strand:
                strand_flips.append(q)
            elif old_strand and not new_strand:
                strand_lost.append(q)
            elif not old_strand and new_strand and len(a["target_strands"][old]) > 1:
                strand_hidden.append(q)
        if "assignment_candidates" not in a or "assignment_candidates" not in b:
            if require_consumer:
                consumer_missing.append(q)
        else:
            old_assignments, new_assignments = consumer_assignments(a, limits), consumer_assignments(b, limits)
            consumer_removed.extend({"query": q, "target": t} for t in sorted(old_assignments.keys() - new_assignments.keys()))
            added = [{"query": q, "target": t} for t in sorted(new_assignments.keys() - old_assignments.keys())]
            consumer_added.extend(added)
            if old_assignments:
                consumer_extra.extend(added)
            for target in sorted(old_assignments.keys() & new_assignments.keys()):
                old_row, new_row = old_assignments[target], new_assignments[target]
                if old_row["orientation"] != new_row["orientation"]:
                    consumer_flips.append({"query": q, "target": target})
                support_delta = new_row["covered"] - old_row["covered"]
                if support_delta:
                    support = {"query": q, "target": target, "delta_bp": support_delta,
                               "fraction_of_query_length": support_delta / a["length"]}
                    support_changes.append(support)
                    if -support_delta / a["length"] > limits.per_query_loss_fraction:
                        support_losses.append(support)
                delta = new_row["anchor_start"] - old_row["anchor_start"]
                if delta:
                    anchors.append({"query": q, "target": target, "delta_bp": delta,
                                    "fraction_of_query_length": abs(delta) / a["length"]})
    total = sum(r["length"] for r in before.values())
    positive_loss = sum(r["bases"] for r in losses)
    reasons = []
    if positive_loss / total > limits.global_loss_fraction:
        reasons.append("global_positive_coverage_loss")
    if any(r["fraction"] > limits.per_query_loss_fraction for r in losses):
        reasons.append("per_query_coverage_loss")
    for name, items in (("assignment_flip", flips), ("assignment_lost", lost_assignment),
                        ("mapped_query_lost", lost_queries), ("ambiguity_hidden", false_certainty),
                        ("strand_flip", strand_flips), ("strand_assignment_lost", strand_lost),
                        ("strand_ambiguity_hidden", strand_hidden), ("strand_evidence_missing", strand_missing),
                        ("downstream_assignment_removed", consumer_removed), ("downstream_extra_assignment", consumer_extra),
                        ("downstream_orientation_changed", consumer_flips), ("downstream_evidence_missing", consumer_missing),
                        ("downstream_qualified_support_loss", support_losses)):
        if items:
            reasons.append(name)
    return {"passed": not reasons, "reasons": reasons, "coverage_losses": losses,
            "positive_loss_fraction": positive_loss / total, "assignment_flips": flips,
            "lost_assignments": lost_assignment, "lost_queries": lost_queries,
            "newly_confident_ambiguous_queries": false_certainty,
            "strand_flips": strand_flips, "lost_strand_assignments": strand_lost,
            "newly_confident_strand_ambiguous_queries": strand_hidden,
            "queries_missing_strand_evidence": strand_missing,
            "downstream_assignments_removed": consumer_removed, "downstream_assignments_added": consumer_added,
            "downstream_orientation_changes": consumer_flips, "downstream_anchor_shifts": anchors,
            "downstream_support_changes": support_changes,
            "downstream_support_loss_limit_fraction_of_query": limits.per_query_loss_fraction,
            "queries_missing_downstream_evidence": consumer_missing,
            "downstream_projection_required": require_consumer,
            "scientific_accuracy_proven": False}


def screen_candidate_projection(profile, limits=Limits()):
    """Request bounded review from full-record evidence, without a baseline.

    Absence of a risk is NOT proof that window selection retained all global
    competitors. Never turn union coverage alone into a quality approval.
    Multiple valid chromosome assignments remain represented, not collapsed.
    """
    if not assess_loss(profile, profile, limits)["passed"]:
        raise ValueError("complete assignment/strand evidence required for projection screening")
    queries = []
    for name, row in profile.items():
        assigned = consumer_assignments(row, limits)
        covered = row["covered"] / row["length"]
        reasons = []
        if not assigned:
            reasons.append("covered_but_unassigned" if covered >= limits.assignment_coverage
                           else "low_reference_support")
        if len(assigned) > 1:
            reasons.append("multiple_chromosome_assignments")
        if any(value["covered"] / row["length"] < limits.assignment_coverage + limits.assignment_margin
               for value in assigned.values()):
            reasons.append("near_assignment_threshold")
        for target in assigned:
            weights = row["assignment_candidates"][target]["strand_weights"]
            if abs(weights["+"] - weights["-"]) / sum(weights.values()) < limits.assignment_margin:
                reasons.append("orientation_ambiguous")
                break
        anchor_spreads = {}
        for target, assignment_row in assigned.items():
            candidate = row["assignment_candidates"][target]
            span = candidate.get("anchor_spans", {}).get(assignment_row["orientation"])
            if (not isinstance(span, list) or len(span) != 2
                    or any(type(n) is not int for n in span) or span[0] > span[1]):
                if "anchor_coherence_evidence_missing" not in reasons:reasons.append("anchor_coherence_evidence_missing")
                continue
            spread = (span[1] - span[0]) / row["length"]
            anchor_spreads[target] = spread
            if spread > limits.maximum_anchor_spread_fraction and "non_collinear_target_support" not in reasons:
                reasons.append("non_collinear_target_support")
        queries.append({"query": name, "coverage_fraction": covered,
                        "dominant_anchor_spread_fractions": anchor_spreads,
                        "assigned_targets": sorted(assigned), "reasons": reasons,
                        "action": "bounded_review" if reasons else "no_obvious_assignment_risk"})
    return {"policy": POLICY, "queries": queries, "baseline_comparison_performed": False,
            "production_approved": False, "scientific_accuracy_proven": False}


def plan_completed_record_review(before, after, limits=Limits()):
    """Select ONE complete source per query from already verified paired PAFs.

    No new mapping, partial-output reuse, cost extrapolation or production
    admission. Caller must verify completed source artifacts before using this
    profile-only plan. Baseline rows replace candidate rows, never supplement
    them: duplicate blocks would alter downstream strand/anchor weights.
    """
    unchanged = assess_loss(before, before, limits)
    original = assess_loss(before, after, limits)
    if not unchanged["passed"] or not any(row["covered"] for row in before.values()):
        return {"status": "baseline_evidence_incomplete", "production_approved": False,
                "speedup_measured": False, "requires_verified_completed_sources": True,
                "original_loss": original, "queries": []}
    decisions = {}
    # The global loss budget applies to the complete set, not as an additional
    # tighter per-record limit.
    per_record = replace(limits, global_loss_fraction=1.0)
    for name in before:
        risk = assess_loss({name: before[name]}, {name: after[name]}, per_record)
        decisions[name] = {"query": name, "source": "candidate" if risk["passed"] else "baseline",
                           "reasons": risk["reasons"]}
    remaining = [(max(0, before[q]["covered"] - after[q]["covered"]), i, q)
                 for i, q in enumerate(before) if decisions[q]["source"] == "candidate"]
    total_loss = sum(loss for loss, _, _ in remaining)
    total_bases = sum(row["length"] for row in before.values())
    # Preserve the greatest amount of lost evidence first. This is a quality
    # ordering over COMPLETED artifacts, never an estimate of remapping cost.
    for loss, _, name in sorted(remaining, key=lambda row: (-row[0], row[1])):
        if total_loss / total_bases <= limits.global_loss_fraction:
            break
        decisions[name].update(source="baseline", reasons=["global_positive_coverage_loss"])
        total_loss -= loss
    combined = {q: before[q] if decisions[q]["source"] == "baseline" else after[q] for q in before}
    checked = assess_loss(before, combined, limits)
    if not checked["passed"]:
        raise ValueError("complete-record review did not resolve measured quality risks")
    sources = {row["source"] for row in decisions.values()}
    return {"status": "completed_record_review_planned", "production_approved": False,
            "speedup_measured": False, "requires_verified_completed_sources": True,
            "selection": "mixed" if len(sources) > 1 else next(iter(sources)),
            "queries": list(decisions.values()), "original_loss": original,
            "reviewed_loss": checked, "new_mapping_commands": 0,
            "partial_PAF_reused": False, "per_query_sources_combined": False}


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
