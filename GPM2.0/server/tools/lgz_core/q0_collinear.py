"""Continuous reference admission. Reference orientation never cuts an inversion.

Only independently supported cross-chromosome chains can divide a source part.
Actual anchors, not their hulls, measure support. No mapper or dataset-specific
logic lives here. Opposite-strand evidence remains a dominance competitor, but
is never separately peeled from a continuous primary-oriented carrier.
"""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from heapq import heappop, heappush
from .q0_sources import Interval, merged_intervals, subtract_intervals, Q0EvidenceError
from .q0_paths import ReferenceAnchor


@dataclass(frozen=True)
class ContinuousAdmissionPolicy:
    minimum_main_chain_bp: int = 100_000
    minimum_new_chain_bp: int = 500_000
    legacy_dominance_fraction: float = 0.75
    top_chain_ratio: float = 10.0
    maximum_single_group_fraction: float = 0.25
    foreign_cluster_gap_bp: int = 50_000
    minimum_terminal_foreign_bp: int = 10_000
    minimum_internal_foreign_bp: int = 100_000
    minimum_internal_fraction: float = 0.01
    minimum_foreign_density: float = 0.50
    maximum_main_overlap_fraction: float = 0.10

    def __post_init__(self):
        import math
        for name in ("minimum_main_chain_bp", "minimum_new_chain_bp", "foreign_cluster_gap_bp",
                     "minimum_terminal_foreign_bp", "minimum_internal_foreign_bp"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise Q0EvidenceError("invalid continuous admission length: " + name)
        if not math.isfinite(self.top_chain_ratio) or self.top_chain_ratio < 1:
            raise Q0EvidenceError("invalid continuous admission dominance ratio")
        for name in ("legacy_dominance_fraction", "maximum_single_group_fraction", "minimum_internal_fraction",
                     "minimum_foreign_density", "maximum_main_overlap_fraction"):
            if not 0 < getattr(self, name) <= 1:
                raise Q0EvidenceError("invalid continuous admission fraction: " + name)


def size(intervals):
    return sum(iv.length for iv in merged_intervals(intervals))


def hull(intervals):
    rows = tuple(intervals)
    return Interval(min(iv.start for iv in rows), max(iv.end for iv in rows))


class OverlapIndex:
    """Exact union-overlap queries; prefix sums avoid repeated contig scans."""
    def __init__(self, intervals):
        self.rows = merged_intervals(intervals)
        self.starts = tuple(iv.start for iv in self.rows)
        self.ends = tuple(iv.end for iv in self.rows)
        self.sums = [0]
        for iv in self.rows:
            self.sums.append(self.sums[-1] + iv.length)

    def overlap(self, intervals):
        total = 0
        for iv in merged_intervals(intervals):
            lo = bisect_right(self.ends, iv.start)
            hi = bisect_left(self.starts, iv.end)
            if lo < hi:
                total += (self.sums[hi] - self.sums[lo]
                          - max(0, iv.start - self.starts[lo]) - max(0, self.ends[hi-1] - iv.end))
        return total


def chain(anchors, strand):
    """Exact weighted interval-chain DP on source-disjoint collinear anchors."""
    rows = sorted(set(anchors), key=lambda a: (a.source.start, a.source.end, a.reference.start,
                                             a.reference.end, a.evidence_id))
    if not rows:
        return ()
    def coordinates(a):
        return (a.reference.start, a.reference.end) if strand == "+" else (-a.reference.end, -a.reference.start)
    ends = sorted({coordinates(a)[1] for a in rows})
    tree = [(0, -1)] * (len(ends) + 1)
    pending, scores, previous = [], [], []
    def update(pos, value):
        while pos < len(tree):
            tree[pos] = max(tree[pos], value)
            pos += pos & -pos
    def query(pos):
        best = (0, -1)
        while pos:
            best = max(best, tree[pos])
            pos -= pos & -pos
        return best
    for i, a in enumerate(rows):
        while pending and pending[0][0] <= a.source.start:
            _, j = heappop(pending)
            update(bisect_left(ends, coordinates(rows[j])[1]) + 1, (scores[j], j))
        score, parent = query(bisect_right(ends, coordinates(a)[0]))
        scores.append(score + a.source.length)
        previous.append(parent)
        heappush(pending, (a.source.end, i))
    i = max(range(len(rows)), key=lambda n: (scores[n], n))
    selected = []
    while i >= 0:
        selected.append(rows[i])
        i = previous[i]
    return tuple(reversed(selected))


def clipped(anchors, interval, strand):
    out = []
    for a in anchors:
        ov = a.source.intersection(interval)
        if ov is None:
            continue
        start = (a.reference.start + ov.start - a.source.start if strand == "+"
                 else a.reference.end - (ov.end - a.source.start))
        out.append(ReferenceAnchor(ov, Interval(start, start + ov.length), a.evidence_id))
    return tuple(out)


def foreign_barriers(groups, high, main_key, main_chain, length, *, minimum_anchor_bp,
                     policy=ContinuousAdmissionPolicy()):
    main_hull = hull(a.source for a in main_chain)
    main_index = OverlapIndex(a.source for a in main_chain)
    barriers, audit = [], []
    for key, anchors in sorted(groups.items()):
        if key[0] == main_key[0]:
            continue  # Same-chromosome inversions never create cuts.
        high_index = OverlapIndex(high.get(key, ()))
        clusters = []
        reach = -policy.foreign_cluster_gap_bp - 1
        for a in sorted(anchors, key=lambda a: (a.source, a.reference, a.evidence_id)):
            if not clusters or a.source.start > reach + policy.foreign_cluster_gap_bp:
                clusters.append([])
            clusters[-1].append(a)
            reach = max(reach, a.source.end)
        for cluster in clusters:
            selected = chain(cluster, key[1])
            span = hull(a.source for a in selected)
            bp = size(a.source for a in selected)
            terminal = span.end <= main_hull.start or span.start >= main_hull.end
            required = (policy.minimum_terminal_foreign_bp if terminal else
                        max(policy.minimum_internal_foreign_bp, int(length * policy.minimum_internal_fraction)))
            main_overlap = main_index.overlap((span,))
            high_bp = high_index.overlap(a.source for a in selected)
            split = (bp >= required and high_bp >= max(required, minimum_anchor_bp)
                     and bp >= policy.minimum_foreign_density * span.length
                     and main_overlap <= policy.maximum_main_overlap_fraction * bp)
            audit.append({"group": list(key), "source_interval": [span.start, span.end],
                          "support_bp": bp, "high_mapq_bp": high_bp, "split": split})
            if split:
                barriers.append(span)
    return merged_intervals(barriers), audit


def continuous_candidates(part, groups, high, admission_policy, make_placement,
                          policy=ContinuousAdmissionPolicy()):
    support = {key: size(a.source for a in rows) for key, rows in groups.items()}
    if not support:
        return (), ()
    chains = {key: chain(rows, key[1]) for key, rows in groups.items()
              if support[key] >= policy.minimum_main_chain_bp}
    chain_bp = {key: size(a.source for a in rows) for key, rows in chains.items()}
    raw_dominant = min(support, key=lambda k: (-support[k], k))
    total = size(a.source for rows in groups.values() for a in rows)
    placements, audit = [], []
    for chromosome in sorted({key[0] for key in chains}):
        key = min((k for k in chains if k[0] == chromosome), key=lambda k: (-chain_bp[k], k))
        main = chains[key]
        legacy = (key == raw_dominant and chain_bp[key] >= policy.minimum_main_chain_bp
                  and chain_bp[key] >= policy.legacy_dominance_fraction * total)
        if not legacy and chain_bp[key] < policy.minimum_new_chain_bp:
            continue
        barriers, foreign = foreign_barriers(groups, high, key, main, part.interval.length,
                                             minimum_anchor_bp=admission_policy.minimum_anchor_bp, policy=policy)
        high_index = OverlapIndex(high.get(key, ()))
        for region in subtract_intervals(part.interval, barriers):
            anchors = clipped(main, region, key[1])
            bp = size(a.source for a in anchors)
            high_bp = high_index.overlap(a.source for a in anchors)
            if (high_bp < admission_policy.minimum_anchor_bp or
                    bp < admission_policy.minimum_whole_support_fraction * region.length):
                continue
            legacy_pass = legacy and bp >= policy.minimum_main_chain_bp
            competitors = []
            if bp >= policy.minimum_new_chain_bp:
                for other, rows in groups.items():
                    if other == key:
                        continue
                    local = clipped(rows, region, other[1])
                    competitors.append((size(a.source for a in chain(local, other[1])), size(a.source for a in local)))
            top = max((v[0] for v in competitors), default=0)
            maximum_group = max((v[1] for v in competitors), default=0)
            top_pass = (bp >= policy.minimum_new_chain_bp and bp >= policy.top_chain_ratio * top
                        and maximum_group <= policy.maximum_single_group_fraction * bp)
            if legacy_pass or top_pass:
                placements.append(make_placement(part, *key, region, (a.source for a in anchors), anchors,
                                                 (a.evidence_id for a in anchors), kind="continuous_reference"))
                audit.append({"chromosome": chromosome, "orientation": key[1],
                              "source_interval": [region.start, region.end], "main_chain_bp": bp,
                              "high_mapq_bp": high_bp, "top_competing_chain_bp": top,
                              "maximum_single_group_support_bp": maximum_group,
                              "legacy_dominance_passed": legacy_pass, "top_chain_passed": top_pass,
                              "foreign_barriers": foreign})
    return tuple(placements), tuple(audit)
