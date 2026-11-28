"""Cross-dataset q0 candidate discovery, not path selection or chr reassignment."""
from __future__ import annotations


from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from operator import attrgetter
from pathlib import Path
from time import monotonic
from typing import Callable, Iterable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .q0_regional_index import RegionalIndex

from .common import stable_id
from .q0_alignments import PafAlignment, PafObservation, read_paf
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
            # Emit one interval per connected run, not one allocation per
            # overlapping CIGAR block. Reuse the first interval if unchanged.
            ordered = iter(sorted((*self._merged, *self._pending), key=attrgetter("start")))
            first = next(ordered)  # pending is nonempty
            end = first.end
            out = []
            for row in ordered:
                if row.start > end:
                    out.append(first if end == first.end else Interval(first.start, end))
                    first, end = row, row.end
                elif row.end > end:
                    end = row.end
            out.append(first if end == first.end else Interval(first.start, end))
            self._merged = tuple(out)
            self._pending.clear()
            self._starts = tuple(interval.start for interval in self._merged)
            self._threshold = max(1024, len(self._merged))

    def fork(self):
        self._compact()
        other = _IntervalUnion()
        other._merged, other._starts, other._threshold = self._merged, self._starts, self._threshold
        return other

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
        self._canonical_sources = {key:key for key in self.source_lengths}
        self.cross_coverage: dict[SourceKey, _IntervalUnion] = {}

    def fork(self):
        """Give a new pass the same observations, never later round mutations."""
        other = ObservedSourcePairs(self.source_lengths)
        other.update(self)
        other.cross_coverage = {key: union.fork() for key, union in self.cross_coverage.items()}
        return other

    def observe_alignment(self, hit: PafAlignment | PafObservation, query: SourceKey, target: SourceKey,
                          *, query_offset: int = 0, target_offset: int = 0) -> None:
        if (type(query_offset) is not int or type(target_offset) is not int
                or min(query_offset, target_offset) < 0
                or query not in self.source_lengths or target not in self.source_lengths
                or query_offset+hit.query_length > self.source_lengths[query]
                or target_offset+hit.target_length > self.source_lengths[target]):
            raise Q0EvidenceError("observed source coverage exceeds its bound inputs")
        query = self._canonical_sources.setdefault(query,query); target = self._canonical_sources.setdefault(target,target)
        qualify = (query.dataset != target.dataset and hit.matches/hit.block_length >= .95
                   and sum(n for n, op in hit.cigar if op in "M=") >= 100)
        if not qualify:
            # Only a paired-base relationship is needed here, not projected
            # coordinates. Keep X relationships and gap-only negatives exactly.
            if any(op in "M=X" for _length,op in hit.cigar):
                self.add(tuple(sorted((query,target))))
            return
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
    rows = intervals if isinstance(intervals, _IntervalUnion) else merged_intervals(intervals)
    return [[i.start, i.end] for i in rows]


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
    reference_routable_parts: frozenset[str] | None = None
    reference_routable_footprints: dict[tuple[str, str], tuple[Interval, ...]] | None = None

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


def _reference_blocks(hit, parts, ends):
    """Project paired blocks onto source parts without treating hulls as coverage.

    If one part contains the *whole query envelope*, every paired block is
    already in that part and its reference coordinates need no clipping. A
    hit crossing a source boundary (including an N gap) must still project
    and clip each block individually, in the original CIGAR traversal order.
    """
    index = bisect_right(ends, hit.query.start)
    if index < len(parts) and parts[index].interval.contains(hit.query):
        part = parts[index]
        for block in hit.aligned_blocks():
            yield part, block.query, block.target, block.operation
        return
    for block in hit.aligned_blocks():
        index = bisect_right(ends, block.query.start)
        while index < len(parts) and parts[index].interval.start < block.query.end:
            part = parts[index]
            index += 1
            overlap = part.interval.intersection(block.query)
            if overlap is None:
                continue
            delta = (overlap.start - block.query.start if hit.strand == "+"
                     else block.query.end - overlap.end)
            start = block.target.start + delta
            yield part, overlap, Interval(start, start + overlap.length), block.operation


def build_catalog(root: Path, sequences: Mapping[SourceKey, str],
                  reference_lengths: Mapping[str, int],
                  assignments: Iterable[dict[str, str]], *, min_gap: int = 100,
                  progress: Callable[[str], None] | None = None,
                  regional_factory: Callable[[Mapping[str, SourceSegment], Mapping[str, int]], RegionalIndex] | None = None) -> CandidateCatalog:
    if type(min_gap) is not int or min_gap < 1:
        raise Q0EvidenceError("q0 minimum gap must be a positive integer")
    started = monotonic()
    grouped = {(row["dataset_name"], row["seq_name"], row["assigned_chr_name"])
               for row in assignments}
    payload = {"schema": CATALOG_SCHEMA, "min_gap": min_gap, "sources": [], "segments": [],
               "gaps": [], "original_connections": [], "candidates": [],
               "evidence": {}, "discovery_rounds": []}
    parts: dict[str, SourceSegment] = {}
    by_dataset = defaultdict(dict)
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
        by_dataset[key.dataset][key.contig] = (index.segments, [part.interval.end for part in index.segments])
    accumulated = {}
    reference_routable_parts = set()
    reference_routable_footprints = {} if regional_factory else None
    lengths_by_dataset: dict[str, dict[str, int]] = defaultdict(dict)
    for key, sequence in sequences.items():
        lengths_by_dataset[key.dataset][key.contig] = len(sequence)
    from .q0_preparation import artifact_path

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
            dataset_parts = by_dataset.get(dataset, {})
            report_blocks = routing is not None and not records_index and not routing.sealed
            scan_sealed = records_index and routing.sealed
            paf = routing.reference_scan_path(relative) if scan_sealed else artifact_path(root, relative)
            for hit in read_paf(paf, query_lengths=lengths,
                                target_lengths=reference_lengths, artifact=relative, record_observer=observer):
                source = dataset_parts.get(hit.query_name)
                if source is None:
                    continue
                previous_part = None
                mapq = hit.mapping_quality
                qualified_reference = hit.matches / hit.block_length >= DISCOVERY_REFERENCE_IDENTITY
                qualified_discovery = qualified_reference and mapq is not None and mapq >= DISCOVERY_REFERENCE_MAPQ
                for part, overlap, target, operation in _reference_blocks(hit, *source):
                    if part is not previous_part:
                        # Consecutive CIGAR blocks in the same source part
                        # share this row; evidence/MAPQ need recording once.
                        identity = (part.segment_id, hit.target_name, hit.strand)
                        row = accumulated.get(identity)
                        if row is None:
                            row = {"query": _IntervalUnion(), "target": _IntervalUnion(),
                                   "evidence": set(), "maximum_mapq": None, "discovery_query": _IntervalUnion()}
                            accumulated[identity] = row
                        row["evidence"].add(hit.evidence_id)
                        if mapq is not None and (row["maximum_mapq"] is None or mapq > row["maximum_mapq"]):
                            row["maximum_mapq"] = mapq
                        previous_part = part
                        footprint = None
                    row["query"].append(overlap)
                    row["target"].append(target)
                    if operation == "X" or not qualified_reference:
                        continue
                    if reference_routable_footprints is not None and footprint is None:
                        footprint_key = (part.segment_id, hit.target_name)
                        footprint = reference_routable_footprints.get(footprint_key)
                        if footprint is None:
                            footprint = reference_routable_footprints[footprint_key] = _IntervalUnion()
                    if reference_routable_footprints is not None:
                        footprint.append(overlap)
                    reference_routable_parts.add(part.segment_id)
                    if report_blocks:
                        routing.observe(part.segment_id, hit.target_name,
                                        Interval(overlap.start-part.interval.start, overlap.end-part.interval.start),
                                        target, hit.strand)
                    if qualified_discovery:
                        row["discovery_query"].append(overlap)
                if previous_part is not None:
                    payload["evidence"][hit.evidence_id] = evidence_ref(hit)
            if scan_sealed:
                routing.verify_inputs()
        if routing is not None:
            routing_report = routing.build_report() if routing.sealed else routing.seal()
    finally:
        if routing is not None:
            routing.close()
    total = len(accumulated)
    materialize_start = last_log = monotonic()
    if progress:
        progress(f"reference scan complete; materializing candidates 0/{total}; "
                 f"catalog preparation so far={materialize_start - started:.1f}s")
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
        if progress and monotonic() - last_log >= 60:
            last_log = monotonic()
            done = len(payload["candidates"])
            progress(f"materializing candidates {done}/{total}; "
                     f"elapsed={last_log - materialize_start:.1f}s")
    if progress:
        progress(f"candidate rows ready {total}/{total}; elapsed={monotonic() - materialize_start:.1f}s")
    catalog = CandidateCatalog(payload, sequences, parts, routing.path if routing else None, routing_report,
                               frozenset(reference_routable_parts),
                               {key: tuple(value) for key, value in reference_routable_footprints.items()}
                               if reference_routable_footprints is not None else None)
    # split_source just verified these immutable strings and part digests. A
    # regional mapper need not hash a 289Mb parent again for every short window.
    catalog._regional_verified_parts = {key:(sequences[p.source],p.interval,p.sequence_sha256) for key,p in parts.items()}
    catalog.finish()
    if progress:
        progress(f"catalog ready; candidates={total}; total elapsed={monotonic() - started:.1f}s")
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
        query_intervals = [interval if query.interval.start == 0 else
                           Interval(query.interval.start+interval.start,query.interval.start+interval.end)
                           for interval in hit.paired_query_intervals()]
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
    from .q0_neighbor_requests import known_neighbors, missing_neighbor_queries
    neighbors = known_neighbors(known_pairs)
    source_by_part = {key: part.source for key, part in catalog.parts.items()}
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
        queries = missing_neighbor_queries(bounds, source_by_part, neighbors, queries)
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
