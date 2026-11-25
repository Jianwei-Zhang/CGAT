"""Bounded, process-local 4D shadow optimizations. Never imported by the Server."""
from collections import Counter, OrderedDict
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from lgz_core import q0_paths as paths


def may_overlap(link, left, right):
    """A CIGAR pair cannot escape its validated PAF envelopes on either source axis."""
    if (link.hit.strand == "+") != (left.orientation == right.orientation):
        return False
    h = link.hit
    def overlaps(iv, outer, shift):
        return iv.start < outer.end + shift and outer.start + shift < iv.end
    return ((link.query_source == left.source and link.target_source == right.source and
             overlaps(left.interval, h.query, link.query_offset) and overlaps(right.interval, h.target, link.target_offset)) or
            (link.target_source == left.source and link.query_source == right.source and
             overlaps(right.interval, h.query, link.query_offset) and overlaps(left.interval, h.target, link.target_offset)))


class AxesCache:
    """Keep a few immutable sets; removing even a nonwinning competing link invalidates a hit."""
    def __init__(self, original, counts, slots=4, max_units=64000):
        self.original, self.stats = original, counts
        self.entries = OrderedDict()
        self.slots, self.max_units = slots, max_units

    def __call__(self, links, left, right, minimum):
        links = tuple(links)
        key = left, right, minimum
        old = self.entries.get(key)
        if old is not None and len(old[0]) == len(links) and all(a is b for a, b in zip(old[0], links)):
            self.entries.move_to_end(key)
            self.stats["axis_builds_avoided"] += 1
            return old[1]
        self.stats["axis_builds"] += 1
        result = self.original(links, left, right, minimum)
        if old is not None:
            del self.entries[key]
        # Limits affect reuse, never candidate scope or the result of this call.
        if len(links) + sum(len(axis.starts) for axis in result) <= self.max_units:
            self.entries[key] = links, result
            if len(self.entries) > self.slots:
                self.entries.popitem(last=False)
        return result


@contextmanager
def exact_kernel():
    counts = Counter()
    original = paths.pair_blocks
    def pair_blocks(link, left, right):
        if not may_overlap(link, left, right):
            counts["pair_blocks_proven_empty"] += 1
            return ()
        counts["pair_blocks_original"] += 1
        return original(link, left, right)
    with ExitStack() as stack:
        stack.enter_context(patch.object(paths, "_competing_axes", AxesCache(paths._competing_axes, counts)))
        stack.enter_context(patch.object(paths, "pair_blocks", pair_blocks))
        yield counts
