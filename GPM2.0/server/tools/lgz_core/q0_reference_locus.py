"""Reference-locus constraints for paired-base equivalence components.

A component must retain a common feasible reference-forward atom START.
Unknown evidence is unconstrained, not grounds for dropping homology. Components
are joined in the native map order; this is not a global optimization claim.
"""
from collections import Counter, defaultdict
from operator import attrgetter
from .q0_sources import Interval, merged_intervals, Q0EvidenceError
from .q0_interval_index import IntervalIndex


def intersection(left, right):
    if left is None:
        return right
    if right is None:
        return left
    i = j = 0
    out = []
    while i < len(left) and j < len(right):
        overlap = left[i].intersection(right[j])
        if overlap is not None:
            out.append(overlap)
        if left[i].end <= right[j].end:
            i += 1
        else:
            j += 1
    return merged_intervals(out)


class ReferenceDomains:
    def __init__(self, placements, tolerance=100_000):
        if type(tolerance) is not int or tolerance < 0:
            raise Q0EvidenceError("reference-locus padding must be a nonnegative integer")
        self.tolerance = tolerance
        self.stats = Counter()
        by_source = defaultdict(list)
        self.anchors, self.bounds = {}, {}
        chromosomes = set()
        for p in placements:
            chromosomes.add(p.chromosome)
            by_source[p.source].append(p)
            self.bounds[p.placement_id] = (min((v.start for v in p.reference_intervals), default=0),
                                           max((v.end for v in p.reference_intervals), default=0))
            self.anchors[p.placement_id] = IntervalIndex(p.reference_blocks, attrgetter("source"))
        if len(chromosomes) > 1:
            raise Q0EvidenceError("reference-locus domains require one chromosome")
        self.index = {source: IntervalIndex(rows, attrgetter("interval")) for source, rows in by_source.items()}

    def atom(self, source, interval):
        exact, fallback = [], []
        index = self.index.get(source)
        if index is not None:
            for _, p in index.overlapping(interval):
                for _, a in self.anchors[p.placement_id].overlapping(interval):
                    start = (a.reference.start + interval.start - a.source.start if p.orientation == "+"
                             else a.reference.start + a.source.end - interval.end)
                    exact.append(Interval(max(0, start-self.tolerance), max(0, start+self.tolerance)+1))
                if p.reference_intervals:
                    lo, hi = self.bounds[p.placement_id]
                    fallback.append(Interval(max(0, lo-interval.length-self.tolerance), hi+self.tolerance+1))
        if exact:
            feasible = (exact[0],)
            for iv in exact[1:]:
                feasible = intersection(feasible, (iv,))
            if not feasible:
                self.stats["inconsistent_anchor_frame_atoms"] += 1
                return None
            self.stats["actual_anchor_atoms"] += 1
            return feasible
        if fallback:
            self.stats["envelope_only_atoms"] += 1
            return merged_intervals(fallback)
        self.stats["unknown_atoms"] += 1
        return None
