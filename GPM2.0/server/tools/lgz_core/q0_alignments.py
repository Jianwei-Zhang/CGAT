"""Strict PAF evidence and CIGAR-coordinate projection for q0 candidates.

Projection proves coordinates only, not unique placement, matching bases,
biological adjacency, or permission to edit. Those require path-level evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator, Mapping

from .common import sha256_bytes, stable_id
from .q0_sources import Interval, Q0EvidenceError

_CIGAR = re.compile(r"([1-9][0-9]*)([MIDN=X])")


@dataclass(frozen=True)
class AlignmentBlock:
    query: Interval
    target: Interval
    strand: str
    operation: str


@dataclass(frozen=True)
class PafAlignment:
    evidence_id: str
    artifact: str
    line_number: int
    record_sha256: str
    query_name: str
    query_length: int
    query: Interval
    strand: str
    target_name: str
    target_length: int
    target: Interval
    matches: int
    block_length: int
    mapq: int
    cigar: tuple[tuple[int, str], ...]
    tags: tuple[str, ...]

    @property
    def mapping_quality(self) -> int | None:
        # 255 denotes unavailable, not stronger evidence than MAPQ 60.
        return None if self.mapq == 255 else self.mapq

    def aligned_blocks(self) -> Iterator[AlignmentBlock]:
        """Yield only paired-base runs; no reference-span hull or gap coverage."""
        for length, operation, q0, q1, t0, t1 in _runs(self):
            if operation in "M=X":
                query = (Interval(self.query.start + q0, self.query.start + q1)
                         if self.strand == "+"
                         else Interval(self.query.end - q1, self.query.end - q0))
                yield AlignmentBlock(query, Interval(t0, t1), self.strand, operation)


@dataclass(frozen=True)
class Projection:
    interval: Interval | None
    status: str
    aligned_bp: int = 0
    target_skip_bp: int = 0

    @property
    def exact(self) -> bool:
        return self.status == "exact"


def parse_paf_line(line: str, *, artifact: str, line_number: int) -> PafAlignment:
    location = f"{artifact}:{line_number}"
    raw = line.rstrip("\r\n")
    fields = raw.split("\t")
    if len(fields) < 12:
        raise Q0EvidenceError(f"{location}: PAF requires at least 12 fields")
    if not artifact or type(line_number) is not int or line_number < 1:
        raise Q0EvidenceError("PAF evidence requires an artifact and a positive line number")
    if any(not fields[i] or any(c.isspace() for c in fields[i]) for i in (0, 5)):
        raise Q0EvidenceError(f"{location}: invalid PAF sequence name")
    try:
        qlen, qs, qe = (int(fields[i]) for i in (1, 2, 3))
        tlen, ts, te = (int(fields[i]) for i in (6, 7, 8))
        matches, block_length, mapq = (int(fields[i]) for i in (9, 10, 11))
        query, target = Interval(qs, qe), Interval(ts, te)
    except ValueError as exc:
        raise Q0EvidenceError(f"{location}: invalid PAF numeric fields or intervals") from exc
    if (qlen < qe or tlen < te or fields[4] not in {"+", "-"}
            or block_length < 1 or not 0 <= matches <= min(block_length, query.length, target.length)
            or not 0 <= mapq <= 255):
        raise Q0EvidenceError(f"{location}: invalid PAF bounds, strand or statistics")
    cigar_tags = [tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")]
    if len(cigar_tags) != 1:
        raise Q0EvidenceError(f"{location}: exactly one cg:Z CIGAR is required")
    text = cigar_tags[0]
    cigar = tuple((int(length), op) for length, op in _CIGAR.findall(text))
    if not cigar or "".join(f"{length}{op}" for length, op in cigar) != text:
        raise Q0EvidenceError(f"{location}: malformed or unsupported PAF CIGAR")
    if (sum(n for n, op in cigar if op in "MI=X") != query.length
            or sum(n for n, op in cigar if op in "MDN=X") != target.length):
        raise Q0EvidenceError(f"{location}: CIGAR span differs from PAF coordinates")
    record_hash = sha256_bytes(raw.encode("utf-8"))
    return PafAlignment(
        stable_id("q0-paf", [artifact, line_number, record_hash]),
        artifact, line_number, record_hash, fields[0], qlen, query, fields[4],
        fields[5], tlen, target, matches, block_length, mapq, cigar, tuple(fields[12:]),
    )


def read_paf(path: Path, *, query_lengths: Mapping[str, int],
             target_lengths: Mapping[str, int], artifact: str | None = None,
             record_observer=None) -> Iterator[PafAlignment]:
    """Stream validated records; callers separately require task-success evidence.

    An empty stream alone does NOT prove a successful no-hit alignment task.
    Unknown names and length drift fail instead of silently removing evidence.
    """
    try:
        # Keep original newline bytes while retaining universal line iteration.
        # Thus UTF-8, CRLF and CR-only files have real byte offsets, while
        # record identities still use the existing normalized parse_paf_line.
        with path.open(encoding="utf-8", newline="") as handle:
            offset = 0
            for number, line in enumerate(handle, 1):
                if record_observer is not None:
                    size = len(line.encode("utf-8"))
                    start, offset = offset, offset + size
                if not line.strip() or line.startswith("#"):
                    continue
                hit = parse_paf_line(line, artifact=artifact if artifact is not None else path.as_posix(), line_number=number)
                if (query_lengths.get(hit.query_name) != hit.query_length
                        or target_lengths.get(hit.target_name) != hit.target_length):
                    raise Q0EvidenceError(f"{path}:{number}: PAF names/lengths differ from inputs")
                if record_observer is not None:
                    record_observer(hit, start, size)
                yield hit
    except (OSError, UnicodeError) as exc:
        raise Q0EvidenceError(f"cannot read q0 alignment evidence {path}: {exc}") from exc


def _runs(hit: PafAlignment) -> Iterator[tuple[int, str, int, int, int, int]]:
    # q is relative to the query interval in target-forward traversal order.
    q, t = 0, hit.target.start
    for length, operation in hit.cigar:
        q_next = q + (length if operation in "MI=X" else 0)
        t_next = t + (length if operation in "MDN=X" else 0)
        yield length, operation, q, q_next, t, t_next
        q, t = q_next, t_next


def _project_boundary(hit: PafAlignment, position: int, *, from_query: bool) -> tuple[int | None, str]:
    positions: set[int] = set()
    paired = False
    for length, operation, q0, q1, t0, t1 in _runs(hit):
        start, end, dest_start, dest_end = ((q0, q1, t0, t1) if from_query else (t0, t1, q0, q1))
        if operation in "M=X" and start <= position <= end:
            positions.add(dest_start + position - start)
            paired = True
        elif start == end == position:
            # Insertion on the destination side: no unique clipping boundary.
            positions.update((dest_start, dest_end))
        elif start < position < end and dest_start == dest_end:
            return None, "inside_alignment_gap"
    if len(positions) > 1:
        return None, "ambiguous_indel_boundary"
    if not paired or not positions:
        return None, "no_paired_boundary"
    return next(iter(positions)), "exact"


def _project(hit: PafAlignment, interval: Interval, *, from_query: bool) -> Projection:
    source = hit.query if from_query else hit.target
    if not source.contains(interval):
        return Projection(None, "outside_alignment")
    if from_query:
        lo, hi = ((interval.start - source.start, interval.end - source.start)
                  if hit.strand == "+" else (source.end - interval.end, source.end - interval.start))
    else:
        lo, hi = interval.start, interval.end
    start, reason = _project_boundary(hit, lo, from_query=from_query)
    if start is None:
        return Projection(None, reason)
    end, reason = _project_boundary(hit, hi, from_query=from_query)
    if end is None:
        return Projection(None, reason)
    if start >= end:
        return Projection(None, "no_paired_bases")
    if from_query:
        output = Interval(start, end)
    elif hit.strand == "+":
        output = Interval(hit.query.start + start, hit.query.start + end)
    else:
        output = Interval(hit.query.end - end, hit.query.end - start)
    paired_bp = sum((overlap.length if overlap else 0)
                    for block in hit.aligned_blocks()
                    for overlap in [(block.query if from_query else block.target).intersection(interval)])
    # Report target skips rather than letting callers mistake a hull for coverage.
    target_interval = output if from_query else interval
    skipped_bp = sum((overlap.length if overlap else 0)
                     for n, op, q0, q1, t0, t1 in _runs(hit) if op == "N"
                     for overlap in [Interval(t0, t1).intersection(target_interval)])
    return Projection(output, "exact", paired_bp, skipped_bp)


def project_target_interval(hit: PafAlignment, interval: Interval) -> Projection:
    """Map exact clipping boundaries to source-forward query coordinates."""
    return _project(hit, interval, from_query=False)


def project_query_interval(hit: PafAlignment, interval: Interval) -> Projection:
    """Map source-forward query boundaries to target-forward coordinates."""
    return _project(hit, interval, from_query=True)
