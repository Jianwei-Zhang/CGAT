"""Exact source-coordinate masks for competing reference alignments, never a placement verdict."""
from array import array
from bisect import bisect_left, bisect_right

from .q0_sources import Interval, merged_intervals, subtract_intervals


def _locus(block):
    # On a paired block the base-boundary map is x + shift or -x + shift.
    # For two maps of the same strand, equality anywhere on their nonempty
    # overlap is exactly equality of these shifts. Evidence IDs are NOT merged.
    shift = (block.target.start - block.query.start if block.strand == '+' else
             block.target.end + block.query.start)
    return block.chromosome, block.strand, shift


class _ReferenceBlockCandidates:
    def __init__(self, blocks):
        self.blocks = sorted(blocks, key=lambda b: b.query.start)
        self.starts = []
        self.prefix_end = []
        self.has_overlap = False
        farthest = 0
        for b in self.blocks:
            if b.query.start < farthest:  # Equal endpoints share no query base.
                self.has_overlap = True
            farthest = max(farthest, b.query.end)
            self.starts.append(b.query.start)
            self.prefix_end.append(farthest)

    def bounds(self, interval):
        first = bisect_right(self.prefix_end, interval.start)
        return first, bisect_left(self.starts, interval.end, lo=first)

    def intersecting(self, interval):
        first, stop = self.bounds(interval)
        for i in range(first, stop):
            b = self.blocks[i]
            overlap = interval.intersection(b.query)
            if overlap is not None:
                yield b, overlap


class _LocusCoverage:
    """Compressed elementary intervals: empty, one locus, or two or more distinct loci.

    MIXED means child states differ spatially; MANY means *every* base of the
    node already has at least two loci. Only MANY is terminal for future adds.
    """
    MIXED, MANY = -1, -2

    def __init__(self, points):
        self.points = points
        self.n = len(points) - 1
        self.nodes = array('i', [0]) * (4 * self.n)

    def add(self, i, lo, hi, start, end, locus):
        nodes = self.nodes
        state = nodes[i]
        if state == locus or state == self.MANY:
            return
        if start <= lo and hi <= end and state != self.MIXED:
            nodes[i] = locus if state == 0 else self.MANY
            return
        child = i * 2
        if state != self.MIXED:
            nodes[child] = nodes[child + 1] = state
        mid = (lo + hi) // 2
        if start < mid:
            self.add(child, lo, mid, start, end, locus)
        if mid < end:
            self.add(child + 1, mid, hi, start, end, locus)
        left = nodes[child]
        nodes[i] = left if left == nodes[child + 1] else self.MIXED

    def runs(self, start, end, state):
        # Coalesce tree splits *before* the complexity filter, whose chunk grid
        # starts at the first unique base. Artificial boundaries would change anchors.
        result = []
        def visit(i, lo, hi):
            value = self.nodes[i]
            if value == state:
                a, b = self.points[max(start, lo)], self.points[min(end, hi)]
                if result and result[-1][1] == a:
                    result[-1][1] = b
                else:
                    result.append([a, b])
            elif value == self.MIXED:
                mid = (lo + hi) // 2
                if start < mid:
                    visit(i * 2, lo, mid)
                if mid < end:
                    visit(i * 2 + 1, mid, hi)
        visit(1, 0, self.n)
        return tuple(Interval(a, b) for a, b in result)


def _dense_masks(blocks, labels, margin):
    points = sorted({p for b in blocks for p in (b.query.start, b.query.end)})
    ranks = {p: i for i, p in enumerate(points)}
    bounds = [(ranks[b.query.start], ranks[b.query.end]) for b in blocks]
    tree = _LocusCoverage(points)
    order = sorted(range(len(blocks)), key=lambda i: blocks[i].identity, reverse=True)
    unique = [None] * len(blocks)
    added = 0
    for i in order:
        threshold = blocks[i].identity
        # Keep the original floating-point expression, including equality at the margin.
        while added < len(order) and blocks[order[added]].identity + margin >= threshold:
            k = order[added]
            tree.add(1, 0, tree.n, *bounds[k], labels[k])
            added += 1
        # The current block itself is present throughout its interval. It is
        # unopposed exactly where every eligible covering block has the same locus.
        unique[i] = tree.runs(*bounds[i], labels[i])
    # Any two coexisting different maps cause a conflict for at least the
    # lower-identity block. This union is not used in place of per-block masks.
    return unique, tree.runs(0, tree.n, tree.MANY)


def reference_masks(blocks, margin):
    """Unique intervals per input block (in input order) and the union of all ambiguities."""
    keys = {}
    labels = [keys.setdefault(_locus(b), len(keys) + 1) for b in blocks]
    if len(keys) < 2:
        return [(b.query,) for b in blocks], ()
    candidates = _ReferenceBlockCandidates(blocks)
    if not candidates.has_overlap:
        # Distinct placements cannot mask one another on disjoint query bases.
        # Return in the original block order, not the index order.
        return [(b.query,) for b in blocks], ()
    # A sparse matrix is cheaper to scan directly. Count candidate visits, not
    # just rows: one long nested interval can widen the scan over disjoint hits.
    if len(blocks) >= 32:
        visits = 0
        for b in blocks:
            lo, hi = candidates.bounds(b.query)
            visits += hi - lo
            if visits > 8 * len(blocks):
                return _dense_masks(blocks, labels, margin)
    unique, ambiguous = [], []
    for b, label in zip(blocks, labels):
        conflicts = [span for other, span in candidates.intersecting(b.query)
                     if other.identity + margin >= b.identity and keys[_locus(other)] != label]
        unique.append(subtract_intervals(b.query, conflicts) if conflicts else (b.query,))
        ambiguous.extend(conflicts)
    return unique, merged_intervals(ambiguous)
