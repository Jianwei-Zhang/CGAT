"""Exact legacy missing-neighbor query selection without enumerating dense gaps.

Reference hulls here only decide which source needs more evidence, just as in
legacy supplemental_groups. They never authorize an alignment, join or edit.
"""
from collections import defaultdict
import heapq


class _ActiveRanks:
    def __init__(self, size):
        self.size = size
        self.tree = [0]*(size+1)
        self.present = [False]*size

    def set(self, index, present):
        if self.present[index] == present:
            return
        delta = 1 if present else -1
        self.present[index] = present
        i = index+1
        while i <= self.size:
            self.tree[i] += delta
            i += i & -i

    def count(self, end):
        """Active ranks strictly below end."""
        result = 0
        while end:
            result += self.tree[end]
            end -= end & -end
        return result

    def select(self, order):
        """Zero-based rank of the one-based order-th active item."""
        position = 0
        bit = 1 << self.size.bit_length()
        while bit:
            candidate = position+bit
            if candidate <= self.size and self.tree[candidate] < order:
                position = candidate
                order -= self.tree[candidate]
            bit >>= 1
        return position

    def before(self, end):
        cursor = 0
        while cursor < end:
            order = self.count(cursor)+1
            if order > self.count(end):
                break
            index = self.select(order)
            yield index
            cursor = index+1


def known_neighbors(pairs):
    result = defaultdict(set)
    for left, right in pairs:
        result[left].add(right)
        result[right].add(left)
    return result


def missing_neighbor_queries(bounds, sources, neighbors, initial=()):
    """Return exactly the original min(id1,id2) missing-pair query set.

    Unknown dense overlaps are handled by active counts and one-time removal
    from the unselected tree. Known relationships are visited through their
    adjacency lists, rather than enumerating every absent relationship.
    """
    selected = set(initial)
    ids = sorted(bounds)
    if not ids:
        return selected
    rank = {key: i for i, key in enumerate(ids)}
    by_source = defaultdict(list)
    for i, key in enumerate(ids):
        by_source[sources[key]].append(i)
    active = _ActiveRanks(len(ids))
    unselected = _ActiveRanks(len(ids))
    endings = []
    rightmost = None

    def choose(index):
        selected.add(ids[index])
        unselected.set(index, False)

    for key, (low, high) in sorted(bounds.items(), key=lambda row: (*row[1], row[0])):
        i = rank[key]
        while endings and endings[0][0] <= low:
            _, old = heapq.heappop(endings)
            active.set(old, False)
            unselected.set(old, False)
        known = neighbors.get(sources[key], ())
        lower = unselected.count(i)
        higher = active.count(len(ids))-active.count(i+1) if key not in selected else 0
        if lower or higher:
            known_lower = known_higher = 0
            for source in known:
                for other in by_source.get(source, ()):
                    if active.present[other]:
                        if other > i:
                            known_higher += 1
                        elif other < i and unselected.present[other]:
                            known_lower += 1
            if higher > known_higher:
                choose(i)
            if lower > known_lower:
                for other in unselected.before(i):
                    if sources[ids[other]] not in known:
                        choose(other)
        if rightmost is not None:
            other, _ = rightmost
            if sources[other] not in known:
                choose(min(i, rank[other]))
        active.set(i, True)
        unselected.set(i, key not in selected)
        heapq.heappush(endings, (high, i))
        if rightmost is None or high > rightmost[1]:
            rightmost = key, high
    return selected
