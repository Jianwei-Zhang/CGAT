"""Loss-aware Q0 supplement scope derived from unresolved path decisions.

This module only selects mapper work. It never edits a PAF, removes a target
from a retained window, or turns an unsearched region into a negative result.
When no provisional path exists callers must use the full supplement fallback.
"""
from __future__ import annotations

from collections import defaultdict

from .q0_sources import Interval, Q0EvidenceError, merged_intervals

OPEN_JOIN_KINDS = frozenset(("reference_unknown", "input_assembly_gap"))


def decision_frontier(construction, *, flank_bp: int = 100_000):
    """Return source-coordinate shoulders around unresolved Q0 decisions.

    ``None`` means the provisional graph did not produce a path and therefore
    cannot justify lossy pruning. A mapping means paths exist; every terminal
    and every unresolved join keeps both participating source shoulders.
    """
    if type(flank_bp) is not int or flank_bp < 1:
        raise Q0EvidenceError("q0 frontier flank must be a positive integer")
    paths = [result.path for result in construction.paths.values() if result.path is not None]
    if not paths:
        return None
    placements = {p.placement_id: p for p in construction.admission.placements}
    frontier = defaultdict(list)

    def add(slice_, *, entering: bool):
        placement = placements.get(slice_.placement_id)
        if placement is None or slice_.source != placement.source or slice_.orientation not in {"+", "-"}:
            raise Q0EvidenceError("q0 frontier slice is not bound to an admitted placement")
        if not placement.interval.contains(slice_.interval):
            raise Q0EvidenceError("q0 frontier slice escapes its placement")
        # The path's entering side is low in a forward placement and high in a
        # reverse placement; exiting is the opposite source-coordinate side.
        low_side = entering == (slice_.orientation == "+")
        cut = slice_.interval.start if low_side else slice_.interval.end
        start = max(placement.interval.start, cut - flank_bp)
        end = min(placement.interval.end, cut + flank_bp)
        if start < end:
            frontier[slice_.source].append(Interval(start, end))

    for path in paths:
        if len(path.slices) != len(path.joins) + 1:
            raise Q0EvidenceError("q0 path has mismatched slices and joins")
        add(path.slices[0], entering=True)
        add(path.slices[-1], entering=False)
        for left, join, right in zip(path.slices, path.joins, path.slices[1:]):
            if join.kind in OPEN_JOIN_KINDS:
                add(left, entering=False)
                add(right, entering=True)
    return {source: merged_intervals(intervals) for source, intervals in frontier.items()}


def _window_span(window, parts):
    part = parts.get(window.segment_id)
    if part is None or window.segment_length != part.interval.length:
        raise Q0EvidenceError("regional window source geometry differs from q0 parts")
    relative = Interval(window.start, window.end)
    return part.source, Interval(part.interval.start + relative.start, part.interval.start + relative.end)


def window_touches_frontier(query, targets, parts, frontier) -> bool:
    """Keep a whole original query/target window if any source shoulder hits."""
    if frontier is None:
        return True
    for window in (query, *targets):
        source, span = _window_span(window, parts)
        if any(span.intersection(shoulder) for shoulder in frontier.get(source, ())):
            return True
    return False
