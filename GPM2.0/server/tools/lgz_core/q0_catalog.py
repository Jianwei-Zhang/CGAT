"""Cross-dataset q0 candidate discovery, not path selection or chr reassignment."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .q0_regional_index import RegionalIndex

from .common import stable_id
from .q0_alignments import PafAlignment, read_paf
from .q0_sources import Interval, Q0EvidenceError, SourceKey, SourceSegment, merged_intervals, split_source

CATALOG_SCHEMA = "lgz_q0_candidates_v1"
DISCOVERY_REFERENCE_IDENTITY = 0.90
DISCOVERY_REFERENCE_MAPQ = 20



class _IntervalUnion:
    """Exact union with amortized compaction, not an interval-count cutoff.

    Retain all evidence IDs elsewhere, without storing repeated geometry for
    every hit/anchor. For disjoint intervals the buffer grows with the union,
    avoiding a quadratic full-union rescan for each small batch of additions.
    """
    __slots__ = ("_merged", "_pending", "_threshold", "_starts")

    def __init__(self):
        self._merged: tuple[Interval, ...] = ()
        self._pending: list[Interval] = []
        self._threshold = 1024
        self._starts: tuple[int, ...] = ()

    def append(self, interval: Interval) -> None:
        # Repeated full/overlapping alignments often add no new geometry.
        # Evidence IDs are retained by the caller; avoid buffering/sorting an
        # interval already represented exactly by one merged interval.
        if self._merged:
            index = bisect_right(self._starts, interval.start) - 1
            if index >= 0 and interval.end <= self._merged[index].end:
                return
        self._pending.append(interval)
        if len(self._pending) >= self._threshold:
            self._compact()

    def extend(self, intervals: Iterable[Interval]) -> None:
        for interval in intervals:
            self.append(interval)

    def _compact(self) -> None:
        if self._pending:
            self._merged = merged_intervals((*self._merged, *self._pending))
            self._pending.clear()
            self._starts = tuple(interval.start for interval in self._merged)
            self._threshold = max(1024, len(self._merged))

    def __iter__(self):
        self._compact()
        return iter(self._merged)


class ObservedSourcePairs(set):
    """Observed relations plus exact cross-source coverage for work selection.

    This does not imply uniqueness, placement or exhaustive alternatives. Only
    callers that have verified a complete PAF may supply hits. Ordinary set
    semantics are retained for existing missing-neighbor consumers.
    """
    def __init__(self, source_lengths: Mapping[SourceKey, int]):
        super().__init__()
        if any(not isinstance(key, SourceKey) or type(length) is not int or length < 1
               for key, length in source_lengths.items()):
            raise Q0EvidenceError("invalid observed source inventory")
        self.source_lengths = dict(source_lengths)
        self.cross_coverage: dict[SourceKey, _IntervalUnion] = {}

    def observe_alignment(self, hit: PafAlignment, query: SourceKey, target: SourceKey,
                          *, query_offset: int = 0, target_offset: int = 0) -> None:
        if (type(query_offset) is not int or type(target_offset) is not int
                or min(query_offset, target_offset) < 0
                or query not in self.source_lengths or target not in self.source_lengths
                or query_offset+hit.query_length > self.source_lengths[query]
                or target_offset+hit.target_length > self.source_lengths[target]):
            raise Q0EvidenceError("observed source coverage exceeds its bound inputs")
        qualify = (query.dataset != target.dataset and hit.matches/hit.block_length >= .95
                   and sum(n for n, op in hit.cigar if op in "M=") >= 100)
        paired = False
        for block in hit.aligned_blocks():
            paired = True
            if qualify and block.operation != "X":
                for source, interval, offset in ((query,block.query,query_offset), (target,block.target,target_offset)):
                    union = self.cross_coverage.get(source)
                    if union is None:
                        union = self.cross_coverage[source] = _IntervalUnion()
                    union.append(Interval(interval.start+offset, interval.end+offset))
        if paired:
            self.add(tuple(sorted((query,target))))


def interval_rows(intervals: Iterable[Interval]) -> list[list[int]]:
    return [[i.start, i.end] for i in merged_intervals(intervals)]


def evidence_ref(hit: PafAlignment) -> dict:
    return {"evidence_id": hit.evidence_id, "artifact": hit.artifact,
            "line_number": hit.line_number, "record_sha256": hit.record_sha256}


@dataclass
class CandidateCatalog:
    payload: dict
    sequences: Mapping[SourceKey, str]
    parts: dict[str, SourceSegment]
    regional_index_path: Path | None = None
    regional_index_report: dict | None = None

    def sequence(self, segment_id: str) -> str:
        part = self.parts[segment_id]
        return self.sequences[part.source][part.interval.start:part.interval.end].upper()

    def by_chromosome(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)
        for candidate in self.payload["candidates"]:
            result[candidate["chromosome"]].add(candidate["segment_id"])
        return dict(result)

    def unplaced(self) -> list[str]:
        known = {row["segment_id"] for row in self.payload["candidates"]}
        return sorted(set(self.parts) - known)

    def finish(self) -> dict:
        self.payload["candidates"].sort(key=lambda row: row["candidate_id"])
        self.payload["unplaced_segment_ids"] = self.unplaced()
        return self.payload


def build_catalog(root: Path, sequences: Mapping[SourceKey, str],
                  reference_lengths: Mapping[str, int],
                  assignments: Iterable[dict[str, str]], *, min_gap: int = 100,
                  regional_factory: Callable[[Mapping[str, SourceSegment], Mapping[str, int]], RegionalIndex] | None = None) -> CandidateCatalog:
    if type(min_gap) is not int or min_gap < 1:
        raise Q0EvidenceError("q0 minimum gap must be a positive integer")
    grouped = {(row["dataset_name"], row["seq_name"], row["assigned_chr_name"])
               for row in assignments}
    payload = {"schema": CATALOG_SCHEMA, "min_gap": min_gap, "sources": [], "segments": [],
               "gaps": [], "original_connections": [], "candidates": [],
               "evidence": {}, "discovery_rounds": []}
    parts: dict[str, SourceSegment] = {}
    by_source = {}
    for key, sequence in sorted(sequences.items()):
        try:
            index = split_source(key, sequence, min_gap=min_gap)
        except Q0EvidenceError as exc:
            payload["sources"].append({"source": asdict(key), "length": len(sequence),
                                       "status": "invalid_sequence", "reason": str(exc)})
            continue
        payload["sources"].append({"source": asdict(key), "length": index.length,
                                   "sequence_sha256": index.sequence_sha256,
                                   "status": "indexed"})
        payload["segments"].extend(asdict(part) for part in index.segments)
        payload["gaps"].extend(asdict(gap) for gap in index.gaps)
        payload["original_connections"].extend(asdict(edge) for edge in index.adjacencies)
        parts.update((part.segment_id, part) for part in index.segments)
        by_source[key] = (index.segments, [part.interval.end for part in index.segments])
    accumulated = {}
    lengths_by_dataset: dict[str, dict[str, int]] = defaultdict(dict)
    for key, sequence in sequences.items():
        lengths_by_dataset[key.dataset][key.contig] = len(sequence)
    # Optional routing index is fed in the same validated reference scan. Its
    # grid/hulls never enter candidate coverage or scientific evidence payload.
    routing = regional_factory(parts, reference_lengths) if regional_factory else None
    routing_report = None
    try:
        for dataset, lengths in sorted(lengths_by_dataset.items()):
            relative = f"runs/{dataset}_vs_ref/result.paf"
            observer = None
            records_index = routing is not None and hasattr(routing, "observe_record")
            if records_index and not routing.sealed:
                routing.register_artifact(relative)
                observer = lambda hit, offset, size, dataset=dataset: routing.observe_record(dataset, hit, offset, size)
            for hit in read_paf(root / relative, query_lengths=lengths,
                                target_lengths=reference_lengths, artifact=relative, record_observer=observer):
                key = SourceKey(dataset, hit.query_name)
                if key not in by_source:
                    continue
                source_parts, ends = by_source[key]
                used = False
                for block in hit.aligned_blocks():
                    offset = bisect_right(ends, block.query.start)
                    while offset < len(source_parts) and source_parts[offset].interval.start < block.query.end:
                        part = source_parts[offset]
                        offset += 1
                        overlap = part.interval.intersection(block.query)
                        if overlap is None:
                            continue
                        if hit.strand == "+":
                            target = Interval(block.target.start + overlap.start - block.query.start,
                                              block.target.start + overlap.end - block.query.start)
                        else:
                            target = Interval(block.target.start + block.query.end - overlap.end,
                                              block.target.start + block.query.end - overlap.start)
                        if (routing is not None and not records_index and not routing.sealed and block.operation != "X"
                                and hit.matches / hit.block_length >= DISCOVERY_REFERENCE_IDENTITY):
                            routing.observe(part.segment_id, hit.target_name,
                                            Interval(overlap.start-part.interval.start, overlap.end-part.interval.start),
                                            target, hit.strand)
                        identity = (part.segment_id, hit.target_name, hit.strand)
                        row = accumulated.get(identity)
                        if row is None:
                            row = {"query": _IntervalUnion(), "target": _IntervalUnion(),
                                   "evidence": set(), "maximum_mapq": None, "discovery_query": _IntervalUnion()}
                            accumulated[identity] = row
                        row["query"].append(overlap)
                        row["target"].append(target)
                        if (block.operation != "X" and hit.mapping_quality is not None
                                and hit.mapping_quality >= DISCOVERY_REFERENCE_MAPQ
                                and hit.matches / hit.block_length >= DISCOVERY_REFERENCE_IDENTITY):
                            row["discovery_query"].append(overlap)
                        row["evidence"].add(hit.evidence_id)
                        if (hit.mapping_quality is not None
                                and (row["maximum_mapq"] is None or hit.mapping_quality > row["maximum_mapq"])):
                            row["maximum_mapq"] = hit.mapping_quality
                        used = True
                if used:
                    payload["evidence"][hit.evidence_id] = evidence_ref(hit)
        if routing is not None:
            routing_report = routing.build_report() if routing.sealed else routing.seal()
    finally:
        if routing is not None:
            routing.close()
    for (segment_id, chromosome, strand), row in sorted(accumulated.items()):
        part = parts[segment_id]
        payload["candidates"].append({
            "candidate_id": stable_id("q0-candidate", [segment_id, chromosome, strand, "reference"]),
            "segment_id": segment_id, "chromosome": chromosome, "orientation": strand,
            "placement_kind": "reference", "origin_group": (
                "main" if (part.source.dataset, part.source.contig, chromosome) in grouped else "expanded"),
            "query_intervals": interval_rows(row["query"]),
            "discovery_query_intervals": interval_rows(row["discovery_query"]),
            "reference_intervals": interval_rows(row["target"]),
            "reference_evidence_ids": sorted(row["evidence"]), "pairwise_evidence_ids": [],
            "anchor_candidate_ids": [], "maximum_available_mapq": row["maximum_mapq"],
        })
    catalog = CandidateCatalog(payload, sequences, parts, routing.path if routing else None, routing_report)
    # split_source just verified these immutable strings and part digests. A
    # regional mapper need not hash a 289Mb parent again for every short window.
    catalog._regional_verified_parts = {key:(sequences[p.source],p.interval,p.sequence_sha256) for key,p in parts.items()}
    catalog.finish()
    return catalog


def add_pairwise_candidates(catalog: CandidateCatalog, hits: Iterable[PafAlignment],
                            query_ids: set[str], target_ids: set[str], *, include_placed: bool = False,
                            known_pairs: set | None = None) -> set[str]:
    """Discover candidate chr relations; never fabricate direct ref alignments.

    Only previously unplaced segments are expanded in a round. Candidate links
    point backwards to existing anchors, so discovery cannot form a proof cycle.
    Multiple chr/strand alternatives survive for the later path selector.
    """
    before = {row["segment_id"] for row in catalog.payload["candidates"]}
    anchors: dict[str, list[dict]] = defaultdict(list)
    for candidate in catalog.payload["candidates"]:
        anchors[candidate["segment_id"]].append(candidate)
    pending = {}
    for hit in hits:
        if hit.query_name not in query_ids or hit.target_name not in target_ids:
            raise Q0EvidenceError("supplementary PAF references an undeclared segment")
        if hit.query_name == hit.target_name or (hit.query_name in before and not include_placed):
            continue
        query = catalog.parts[hit.query_name]
        query_intervals = [Interval(query.interval.start + block.query.start,
                                    query.interval.start + block.query.end)
                           for block in hit.aligned_blocks()]
        if not query_intervals:
            continue
        # The caller supplies only a successfully committed, validated PAF.
        # Its observed source pairs are evidence just like the initial chr-local
        # pairs; later missing-neighbor planning must not forget this work.
        if known_pairs is not None:
            known_pairs.add(tuple(sorted((query.source, catalog.parts[hit.target_name].source))))
        for anchor in anchors[hit.target_name]:
            orientation = "+" if hit.strand == anchor["orientation"] else "-"
            identity = (hit.query_name, anchor["chromosome"], orientation)
            row = pending.get(identity)
            if row is None:
                row = {"query": _IntervalUnion(), "anchors": set(), "evidence": set()}
                pending[identity] = row
            row["query"].extend(query_intervals)
            row["anchors"].add(anchor["candidate_id"])
            row["evidence"].add(hit.evidence_id)
            catalog.payload["evidence"][hit.evidence_id] = evidence_ref(hit)
    for (segment_id, chromosome, strand), row in sorted(pending.items()):
        catalog.payload["candidates"].append({
            "candidate_id": stable_id("q0-candidate", [segment_id, chromosome, strand, "pairwise"]),
            "segment_id": segment_id, "chromosome": chromosome, "orientation": strand,
            "placement_kind": "pairwise", "origin_group": "expanded",
            "query_intervals": interval_rows(row["query"]), "reference_intervals": [],
            "reference_evidence_ids": [], "pairwise_evidence_ids": sorted(row["evidence"]),
            "anchor_candidate_ids": sorted(row["anchors"]), "maximum_available_mapq": None,
        })
    catalog.finish()
    return {row["segment_id"] for row in catalog.payload["candidates"]} - before


def supplemental_groups(catalog: CandidateCatalog, assignments: Iterable[dict[str, str]],
                        known_pairs: frozenset | set = frozenset()) -> list[dict]:
    """Cover missing chr-local relationships without global all-versus-all.

    A query is needed for an out-of-group source or a split source whose internal
    segments were excluded by ordinary same-record self-alignment suppression.
    Reference overlaps/neighbors with no observed source-pair hit also need
    targeted evidence: a completed high-threshold self task may miss short ends.
    Reference bounds only request a comparison; they never authorize a join.
    """
    grouped = {(row["dataset_name"], row["seq_name"], row["assigned_chr_name"])
               for row in assignments}
    parts_per_source: dict[SourceKey, int] = defaultdict(int)
    for part in catalog.parts.values():
        parts_per_source[part.source] += 1
    tasks = []
    for chromosome, segment_ids in sorted(catalog.by_chromosome().items()):
        if len(segment_ids) < 2:
            continue
        queries = {segment_id for segment_id in segment_ids
                   if parts_per_source[catalog.parts[segment_id].source] > 1
                   or (catalog.parts[segment_id].source.dataset,
                       catalog.parts[segment_id].source.contig, chromosome) not in grouped}
        bounds = {}
        for row in catalog.payload["candidates"]:
            if row["chromosome"] != chromosome or not row["reference_intervals"]:
                continue
            low = min(start for start, end in row["reference_intervals"])
            high = max(end for start, end in row["reference_intervals"])
            previous = bounds.get(row["segment_id"], (low, high))
            bounds[row["segment_id"]] = (min(low, previous[0]), max(high, previous[1]))
        active = []
        rightmost = None
        for segment_id, (low, high) in sorted(bounds.items(), key=lambda item: (*item[1], item[0])):
            active = [(other, end) for other, end in active if end > low]
            neighbors = {other for other, end in active}
            if rightmost is not None:
                neighbors.add(rightmost[0])
            for other in neighbors:
                pair = tuple(sorted((catalog.parts[segment_id].source, catalog.parts[other].source)))
                if pair not in known_pairs:
                    queries.add(min(segment_id, other))
            active.append((segment_id, high))
            if rightmost is None or high > rightmost[1]:
                rightmost = (segment_id, high)
        if queries:
            tasks.append({"kind": "candidate_chr", "chromosome": chromosome,
                          "query_ids": sorted(queries), "target_ids": sorted(segment_ids)})
    return tasks


def partial_source_intervals(catalog: CandidateCatalog, *, minimum_uncovered_bp: int = 100,
                             observed: ObservedSourcePairs | None = None) -> dict[str, tuple[Interval, ...]]:
    """Return segment-relative missing pieces, never hulls or accepted placements.

    With `observed`, already covered cross-source bases are excluded from new
    discovery requests. This is an explicit recall/work-selection policy choice,
    not proof that every possible alternative relationship was discovered.
    """
    from .q0_sources import subtract_intervals
    if type(minimum_uncovered_bp) is not int or minimum_uncovered_bp < 1:
        raise Q0EvidenceError("invalid minimum uncovered interval")
    coverage: dict[str, _IntervalUnion] = {}
    for candidate in catalog.payload["candidates"]:
        if candidate["placement_kind"] == "reference":
            key = candidate["segment_id"]
            union = coverage.get(key)
            if union is None:
                union = coverage[key] = _IntervalUnion()
            union.extend(Interval(*i) for i in candidate["discovery_query_intervals"])
    result = {}
    for key, intervals in sorted(coverage.items()):
        part = catalog.parts[key]
        if observed is not None:
            if observed.source_lengths.get(part.source) != len(catalog.sequences[part.source]):
                raise Q0EvidenceError("observed coverage source inventory changed")
            intervals.extend(observed.cross_coverage.get(part.source, ()))
        holes = tuple(Interval(i.start-part.interval.start, i.end-part.interval.start)
                      for i in subtract_intervals(part.interval, intervals) if i.length >= minimum_uncovered_bp)
        if holes:
            result[key] = holes
    return result


def partial_source_request(catalog: CandidateCatalog, *, minimum_uncovered_bp: int = 100) -> dict | None:
    """Request whole-source native context for the ordinary discovery path."""
    queries = sorted(partial_source_intervals(catalog, minimum_uncovered_bp=minimum_uncovered_bp))
    anchors = sorted({row["segment_id"] for row in catalog.payload["candidates"]})
    if queries and len(anchors) > 1:
        return {"kind": "partial_source_discovery", "query_ids": queries, "target_ids": anchors,
                "minimum_uncovered_bp": minimum_uncovered_bp}
    return None
