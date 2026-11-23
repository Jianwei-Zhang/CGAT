"""Loss-aware Q0 supplement scope derived from unresolved path decisions.

This module only selects mapper work. It never edits a PAF, removes a target
from a retained window, or turns an unsearched region into a negative result.
When no provisional path exists callers must use the full supplement fallback.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict

from .q0_catalog import _IntervalUnion

from .q0_sources import Interval, Q0EvidenceError, merged_intervals

FRONTIER_FLANK_BP = 100_000
OPEN_JOIN_KINDS = frozenset(("reference_unknown", "input_assembly_gap"))


class UnsearchedQ0Context(Q0EvidenceError):
    """A valid partial search may require more contexts before publication."""


def decision_frontier(construction, *, flank_bp: int = FRONTIER_FLANK_BP):
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
        if placement is None or slice_.source != placement.source or slice_.orientation != placement.orientation or slice_.orientation not in {"+", "-"}:
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
    if relative.end > window.segment_length:
        raise Q0EvidenceError("regional window exceeds its source part")
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


class UnsearchedWindows:
    """Conservative union of both axes of every deliberately omitted window.

    Compressed by source part; no per-pair cross product or PAF-derived mask.
    Coordinates describe planning omissions, not positive or negative evidence.
    """

    def __init__(self):
        self._parts = defaultdict(_IntervalUnion)

    def observe(self, query, targets, parts):
        for window in (query, *targets):
            _window_span(window, parts)  # Validate the segment/frame before recording it.
            self._parts[window.segment_id].append(Interval(window.start, window.end))

    def record(self):
        return [[key, [[v.start, v.end] for v in spans]] for key, spans in sorted(self._parts.items())]


def _unsearched_axes(report, parts):
    if not isinstance(report, dict):
        raise Q0EvidenceError("q0 scope is not a bound report")
    rows = report.get("unsearched_part_intervals")
    if not isinstance(rows, list):
        raise Q0EvidenceError("q0 scope has no bound unsearched intervals")
    by_source = defaultdict(list)
    seen = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str):
            raise Q0EvidenceError("invalid q0 unsearched interval row")
        segment_id, spans = row
        if (segment_id not in parts or segment_id in seen or not isinstance(spans, list) or not spans
                or any(not isinstance(span, list) or len(span) != 2 for span in spans)):
            raise Q0EvidenceError("invalid q0 unsearched interval inventory")
        seen.add(segment_id)
        part = parts[segment_id]
        relative = tuple(Interval(*r) for r in spans)
        if relative != merged_intervals(relative) or relative[-1].end > part.interval.length:
            raise Q0EvidenceError("invalid q0 unsearched interval bounds")
        start = part.interval.start
        by_source[part.source].extend(Interval(start + r.start, start + r.end) for r in relative)
    return {source: (tuple(i.start for i in compact), compact) for source, spans in by_source.items()
            if (compact := merged_intervals(spans))}


def _selected_proof_axes(data, admission, searches):
    """Positive-proof geometry shared by the dispatch repair and final guard."""
    placements = {p.placement_id: p for p in admission.placements}
    exact, optional = set(), set()
    for search in searches.values():
        path = search.path
        if path is None:
            continue
        for join in path.joins:
            if join.kind == "sequence_overlap":
                if not join.evidence_ids:
                    raise Q0EvidenceError("q0 sequence overlap has no recorded pair evidence")
                exact.update(join.evidence_ids)
        for s in path.slices:
            placement = placements[s.placement_id]
            if placement.localization_kind != "pairwise":
                continue
            yield "placement", placement.source, placement.interval
            optional.update(placement.evidence_ids)

    wanted = exact | optional
    if not wanted:
        return
    seen = set()
    # Keep only IDs needed by the selected paths, not another index over all
    # source PAF records (the large self matrices can dominate this inventory).
    for link in data.pair_links:
        eid = link.hit.evidence_id
        if eid not in wanted:
            continue
        seen.add(eid)
        for source, interval, offset in ((link.query_source, link.hit.query, link.query_offset),
                                         (link.target_source, link.hit.target, link.target_offset)):
            yield "pair evidence", source, Interval(interval.start + offset, interval.end + offset)
    if exact - seen:
        raise Q0EvidenceError("q0 sequence overlap has no recorded pair evidence")


def selected_proof_frontier(data, admission, searches):
    """Find omitted whole contexts that could affect the selected claims.

    This is work selection, not authorization: after adding those contexts the
    paths can change and the ordinary omission guard must run again.
    """
    spans = defaultdict(_IntervalUnion)
    for _kind, source, span in _selected_proof_axes(data, admission, searches):
        spans[source].append(span)
    return {source: tuple(intervals) for source, intervals in spans.items()}


def audit_selected_scope(data, admission, searches):
    """Reject exact cuts or pairwise-localized slices exposed to omitted work.

    A missing competitor could overlap either axis of a positive proof. To
    avoid inferring absence from skipped work, use the conservative union
    (even another-pair context on that axis can make the decision uncertain).
    This guard does not claim equivalence with full discovery or certify the
    mapper's search. A trial can abstain and request full evidence instead.
    """
    axes = _unsearched_axes(data.catalog.get("supplement_scope"), data.parts)
    if not axes:
        return

    for kind, source, span in _selected_proof_axes(data, admission, searches):
        axis = axes.get(source)
        if axis is None:
            continue
        starts, intervals = axis
        i = bisect_right(starts, span.end - 1) - 1
        if i >= 0 and intervals[i].end > span.start:
            raise UnsearchedQ0Context(f"q0 scoped {kind} has unsearched competing context; rerun with full supplemental evidence")
