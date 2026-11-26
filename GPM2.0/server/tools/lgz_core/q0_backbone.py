"""Reference-ordered continuous-source proposals, always exact-gated."""
from bisect import bisect_right
from collections import Counter


def reference_spine(graph):
    """Weighted interval scheduling followed by ordinary exact path validation.

    Full reference hulls must be disjoint and ordered. Source length is only a
    proposal weight: every emitted path still passes the real join/duplicate
    gates. If the full proposal fails, keep a valid prefix and skip invalid
    additions. No local fragment refinement or global-optimality claim.
    """
    rows = sorted((p for p in graph.placements.values() if p.reference_intervals),
                  key=lambda p: (max(i.end for i in p.reference_intervals),
                                 min(i.start for i in p.reference_intervals), p.placement_id))
    ends = [max(iv.end for iv in p.reference_intervals) for p in rows]
    dp, back, take = [(0, 0)], [], []
    for i, placement in enumerate(rows):
        previous = bisect_right(ends, min(iv.start for iv in placement.reference_intervals), 0, i)
        value = (dp[previous][0] + placement.interval.length, dp[previous][1] - 1)
        chosen = value > dp[-1]
        dp.append(value if chosen else dp[-1])
        back.append(previous)
        take.append(chosen)
    chosen = []
    i = len(rows)
    while i:
        if take[i-1]:
            chosen.append(rows[i-1].placement_id)
            i = back[i-1]
        else:
            i -= 1
    nodes = tuple(reversed(chosen))
    joins = []
    missing_edge = False
    for left, right in zip(nodes, nodes[1:]):
        variants = graph.joins(left, right)
        if not variants:
            missing_edge = True
            break
        joins.append(variants[0])
    candidate = None if missing_edge else graph._score_candidate(nodes, tuple(joins))
    full_valid = candidate is not None
    skipped = Counter()
    evaluations = 1
    if candidate is None:
        current = None
        for node in nodes:
            options = []
            if current is None:
                evaluations += 1
                path = graph._score_candidate((node,), ())
                if path is not None:
                    options.append(path)
            else:
                variants = graph.joins(current.nodes[-1], node)
                if not variants:
                    skipped["no_legal_join"] += 1
                    continue
                for join in variants:
                    evaluations += 1
                    path = graph._score_candidate(current.nodes + (node,), current.joins + (join,))
                    if path is not None:
                        options.append(path)
                        # Join order encodes evidence quality. Do not replace a
                        # valid exact join with an unknown gap just because the
                        # latter carries more (potentially redundant) bases.
                        break
            if options:
                current = min(options, key=graph.rank)
            else:
                skipped["exact_score_or_duplicate_gate"] += 1
        candidate = current
    return candidate, {"proposal_nodes": len(nodes), "proposal_source_length_weight": dp[-1][0],
                       "full_proposal_passed": full_valid, "score_calls": evaluations,
                       "fallback_skips": dict(skipped)}
