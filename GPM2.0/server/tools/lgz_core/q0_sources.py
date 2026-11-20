"""Immutable source intervals for evidence-guided q0 construction.

These are indexes, not rewritten FASTAs or placement decisions. Coordinates are
0-based half-open internally; existing metadata conversion happens explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .common import DNA_ALPHABET, sha256_bytes, stable_id


_INVALID_DNA = re.compile("[^" + re.escape("".join(sorted(DNA_ALPHABET))) + "]")


class Q0EvidenceError(ValueError):
    """Required evidence is malformed, rather than a valid negative result."""


@dataclass(frozen=True, order=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if (type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end):
            raise Q0EvidenceError(f"invalid half-open interval: {self.start}:{self.end}")

    @property
    def length(self) -> int:
        return self.end - self.start

    def inclusive(self) -> tuple[int, int]:
        return self.start + 1, self.end

    @classmethod
    def from_inclusive(cls, start: int, end: int) -> Interval:
        if type(start) is not int or type(end) is not int:
            raise Q0EvidenceError("inclusive coordinates must be integers")
        return cls(start - 1, end)

    def intersection(self, other: Interval) -> Interval | None:
        start, end = max(self.start, other.start), min(self.end, other.end)
        return Interval(start, end) if start < end else None

    def contains(self, other: Interval) -> bool:
        return self.start <= other.start and other.end <= self.end


def merged_intervals(intervals: Iterable[Interval]) -> tuple[Interval, ...]:
    result: list[Interval] = []
    for interval in sorted(intervals):
        if result and interval.start <= result[-1].end:
            result[-1] = Interval(result[-1].start, max(result[-1].end, interval.end))
        else:
            result.append(interval)
    return tuple(result)


def subtract_intervals(whole: Interval, occupied: Iterable[Interval]) -> tuple[Interval, ...]:
    """Return unused source coordinates, never sequence content or a donor verdict."""
    result: list[Interval] = []
    cursor = whole.start
    for interval in merged_intervals(occupied):
        overlap = whole.intersection(interval)
        if overlap is None:
            continue
        if cursor < overlap.start:
            result.append(Interval(cursor, overlap.start))
        cursor = max(cursor, overlap.end)
    if cursor < whole.end:
        result.append(Interval(cursor, whole.end))
    return tuple(result)


@dataclass(frozen=True, order=True)
class SourceKey:
    dataset: str
    contig: str

    def __post_init__(self) -> None:
        for value in (self.dataset, self.contig):
            if not isinstance(value, str) or not value or any(c.isspace() for c in value):
                raise Q0EvidenceError("source identity requires non-empty names without whitespace")


@dataclass(frozen=True)
class SourceSegment:
    segment_id: str
    source: SourceKey
    interval: Interval
    sequence_sha256: str
    n_bp: int
    left_boundary: str
    right_boundary: str


@dataclass(frozen=True)
class SourceGap:
    gap_id: str
    source: SourceKey
    interval: Interval
    left_segment_id: str | None
    right_segment_id: str | None

    @property
    def is_internal(self) -> bool:
        return self.left_segment_id is not None and self.right_segment_id is not None


@dataclass(frozen=True)
class OriginalAdjacency:
    """Forward-source order; reversing a placement must reverse both endpoints."""
    adjacency_id: str
    source: SourceKey
    left_segment_id: str
    right_segment_id: str
    gap_id: str
    gap_interval: Interval
    kind: str = "input_assembly_gap"


@dataclass(frozen=True)
class SourceIndex:
    source: SourceKey
    length: int
    sequence_sha256: str
    min_gap: int
    segments: tuple[SourceSegment, ...]
    gaps: tuple[SourceGap, ...]
    adjacencies: tuple[OriginalAdjacency, ...]


def split_source(source: SourceKey, sequence: str, *, min_gap: int = 100) -> SourceIndex:
    """Index long N runs without claiming biological gap length or correctness.

    Like the existing FASTA reader, sequence case is normalized for indexing.
    Terminal runs and all-N records retain gap provenance but create no links
    to invented empty segments. Short N runs stay visible in segment.n_bp.
    """
    if type(min_gap) is not int or min_gap < 1:
        raise Q0EvidenceError("minimum N run must be a positive integer")
    sequence = sequence.upper()
    if not sequence or _INVALID_DNA.search(sequence):
        raise Q0EvidenceError(f"empty or invalid source sequence: {source.dataset}:{source.contig}")
    digest = sha256_bytes(sequence.encode("ascii"))
    gap_intervals = [Interval(m.start(), m.end()) for m in re.finditer(r"N{%d,}" % min_gap, sequence)]
    segment_intervals = subtract_intervals(Interval(0, len(sequence)), gap_intervals)
    segments: list[SourceSegment] = []
    for interval in segment_intervals:
        fragment = sequence[interval.start:interval.end]
        # The unsplit segment is exactly the normalized source already hashed.
        # Retain independent content hashes for every proper subinterval.
        fragment_hash = (digest if interval.start == 0 and interval.end == len(sequence)
                         else sha256_bytes(fragment.encode("ascii")))
        identity = [source.dataset, source.contig, interval.start, interval.end, fragment_hash]
        segments.append(SourceSegment(
            stable_id("q0-source-part", identity), source, interval, fragment_hash,
            fragment.count("N"),
            "record_start" if interval.start == 0 else "long_n",
            "record_end" if interval.end == len(sequence) else "long_n",
        ))
    by_start = {part.interval.start: part.segment_id for part in segments}
    by_end = {part.interval.end: part.segment_id for part in segments}
    gaps: list[SourceGap] = []
    adjacencies: list[OriginalAdjacency] = []
    for interval in gap_intervals:
        gap_id = stable_id("q0-input-gap", [source.dataset, source.contig, digest,
                                           interval.start, interval.end])
        left, right = by_end.get(interval.start), by_start.get(interval.end)
        gaps.append(SourceGap(gap_id, source, interval, left, right))
        if left is not None and right is not None:
            adjacencies.append(OriginalAdjacency(
                stable_id("q0-input-adjacency", [left, right, gap_id]),
                source, left, right, gap_id, interval,
            ))
    return SourceIndex(source, len(sequence), digest, min_gap,
                       tuple(segments), tuple(gaps), tuple(adjacencies))
