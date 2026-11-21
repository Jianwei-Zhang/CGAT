"""Explicit, bounded query contexts for large partial-source discovery.

This changes mapper context, NOT source sequences or placement coordinates.
Planning is opt-in at the caller until a policy is integrated and content-bound.
Whole-segment native receipts must never be relabeled as windowed execution.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from bisect import bisect_right
from functools import cached_property
from typing import Iterable, Mapping
from .common import stable_id
from .q0_alignments import parse_paf_line
from .q0_sources import Interval, Q0EvidenceError, merged_intervals


@dataclass(frozen=True)
class WindowPolicy:
    version: int = 1
    trigger_query_bases: int = 1_000_000_000
    trigger_longest_bases: int = 20_000_000
    core_bases: int = 1_000_000
    context_bases: int = 10_000
    minimum_uncovered_bases: int = 100

    def __post_init__(self):
        for name in ("trigger_query_bases", "trigger_longest_bases", "core_bases", "minimum_uncovered_bases"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise Q0EvidenceError(f"invalid window policy: {name}")
        if type(self.context_bases) is not int or self.context_bases < 0 or self.version != 1:
            raise Q0EvidenceError("invalid window context or policy version")


@dataclass(frozen=True)
class QueryWindow:
    segment_id: str
    segment_length: int
    start: int
    end: int
    # Segment-relative forward coordinates. The original source offset of a
    # split segment is applied by admission, NOT by this normalizer.
    cores: tuple[tuple[int, int], ...]

    def __post_init__(self):
        if (not self.segment_id or any(c.isspace() for c in self.segment_id)
                or type(self.segment_length) is not int or self.segment_length < 1
                or type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= self.segment_length):
            raise Q0EvidenceError("invalid query window geometry")
        if not self.cores:
            raise Q0EvidenceError("query window lacks an uncovered core")
        intervals = tuple(Interval(*row) for row in self.cores)
        if (intervals != merged_intervals(intervals)
                or any(i.start < self.start or i.end > self.end for i in intervals)):
            raise Q0EvidenceError("query window cores must be ordered, disjoint and inside its context")

    @cached_property
    def window_id(self) -> str:
        return stable_id("q0-query-window", asdict(self))

    @cached_property
    def core_ends(self) -> tuple[int, ...]:
        return tuple(end for start, end in self.cores)

    @property
    def length(self) -> int:
        return self.end - self.start

    def record(self) -> dict:
        return {"window_id": self.window_id, **asdict(self)}


def plan_query_windows(lengths: Mapping[str, int], uncovered: Mapping[str, Iterable[Interval]], *,
                       policy: WindowPolicy = WindowPolicy()) -> tuple[QueryWindow, ...] | None:
    """Return None for native-sized work; never infer cores from reference hulls.

    Every qualifying uncovered base is retained, including a short final tile.
    Nearby expanded contexts are grouped, then long groups are tiled with context.
    No target/chr is excluded here. Context reduction is NOT lossless alignment.
    """
    pending = {}
    for key, rows in uncovered.items():
        length = lengths.get(key)
        if type(length) is not int or length < 1:
            raise Q0EvidenceError("window request has an unknown or invalid source length")
        intervals = merged_intervals(rows)
        if any(i.end > length for i in intervals):
            raise Q0EvidenceError("uncovered interval exceeds its segment")
        holes = tuple(i for i in intervals if i.length >= policy.minimum_uncovered_bases)
        if holes:
            pending[key] = holes
    if not pending or (sum(lengths[key] for key in pending) < policy.trigger_query_bases
                       and max(lengths[key] for key in pending) < policy.trigger_longest_bases):
        return None
    result = []
    for key, holes in sorted(pending.items()):
        length = lengths[key]
        groups: list[list[Interval]] = []
        for hole in holes:
            if groups and hole.start - groups[-1][-1].end <= 2 * policy.context_bases:
                groups[-1].append(hole)
            else:
                groups.append([hole])
        for group in groups:
            first = 0
            for low in range(group[0].start, group[-1].end, policy.core_bases):
                high = min(low + policy.core_bases, group[-1].end)
                while first < len(group) and group[first].end <= low:
                    first += 1
                cores = []
                index = first
                while index < len(group) and group[index].start < high:
                    cores.append((max(low, group[index].start), min(high, group[index].end)))
                    index += 1
                if cores:
                    result.append(QueryWindow(key, length,
                        max(0, cores[0][0] - policy.context_bases),
                        min(length, cores[-1][1] + policy.context_bases), tuple(cores)))
    return tuple(result)


def project_window_paf(line: str, windows: Mapping[str, QueryWindow],
                       target_lengths: Mapping[str, int], *, artifact: str,
                       line_number: int) -> str | None:
    """Validate and project paired evidence to original segment coordinates.

    Context-only and original-self hits are not new donor evidence. An indel
    spanning a core is not paired coverage. Raw PAF + window manifest must be
    retained by the caller. No CIGAR clipping or source-sequence trimming occurs.
    Forward query coordinates shift identically on both strands. Window-local
    confidence and chain/selection scores are not whole-source confidence:
    projected MAPQ is unknown (255); the unmodified raw PAF remains authoritative
    for those local tags and is required as a separate bound artifact.
    """
    hit = parse_paf_line(line, artifact=artifact, line_number=line_number)
    window = windows.get(hit.query_name)
    if (window is None or hit.query_length != window.length
            or target_lengths.get(hit.target_name) != hit.target_length):
        raise Q0EvidenceError("window PAF references an unknown input or changed length")
    if any(tag.startswith("qw:") for tag in hit.tags):
        raise Q0EvidenceError("raw window PAF already carries a projection marker")
    if hit.target_name == window.segment_id:
        return None
    for block in hit.aligned_blocks():
        start, end = block.query.start + window.start, block.query.end + window.start
        index = bisect_right(window.core_ends, start)
        if index < len(window.cores) and window.cores[index][0] < end:
            break
    else:
        return None
    fields = line.rstrip("\r\n").split("\t")
    fields[:4] = [window.segment_id, str(window.segment_length),
                  str(hit.query.start + window.start), str(hit.query.end + window.start)]
    fields[11] = "255"
    # Retain unchanged alignment statistics, not local primary/secondary labels,
    # chain scores or repetitive-base counts under the full source's identity.
    fields[12:] = [tag for tag in fields[12:] if tag.startswith(("cg:Z:", "NM:i:", "nn:i:"))]
    fields.append("qw:Z:" + window.window_id)
    result = "\t".join(fields)
    parse_paf_line(result, artifact=artifact + ".projected", line_number=line_number)
    return result
