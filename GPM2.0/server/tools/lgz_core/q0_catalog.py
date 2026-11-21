"""Cross-dataset q0 candidate discovery, not path selection or chr reassignment."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .common import stable_id
from .q0_alignments import PafAlignment, read_paf
from .q0_sources import Interval, Q0EvidenceError, SourceKey, SourceSegment, merged_intervals, split_source

CATALOG_SCHEMA = "lgz_q0_candidates_v1"
DISCOVERY_REFERENCE_IDENTITY = 0.90
DISCOVERY_REFERENCE_MAPQ = 20


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
                  assignments: Iterable[dict[str, str]], *, min_gap: int = 100) -> CandidateCatalog:
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
    for dataset, lengths in sorted(lengths_by_dataset.items()):
        relative = f"runs/{dataset}_vs_ref/result.paf"
        for hit in read_paf(root / relative, query_lengths=lengths,
                            target_lengths=reference_lengths, artifact=relative):
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
                    identity = (part.segment_id, hit.target_name, hit.strand)
                    row = accumulated.setdefault(identity, {"query": [], "target": [],
                                                             "evidence": set(), "mapq": [], "discovery_query": []})
                    row["query"].append(overlap)
                    row["target"].append(target)
                    if (block.operation != "X" and hit.mapping_quality is not None
                            and hit.mapping_quality >= DISCOVERY_REFERENCE_MAPQ
                            and hit.matches / hit.block_length >= DISCOVERY_REFERENCE_IDENTITY):
                        row["discovery_query"].append(overlap)
                    row["evidence"].add(hit.evidence_id)
                    if hit.mapping_quality is not None:
                        row["mapq"].append(hit.mapping_quality)
                    used = True
            if used:
                payload["evidence"][hit.evidence_id] = evidence_ref(hit)
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
            "anchor_candidate_ids": [], "maximum_available_mapq": max(row["mapq"], default=None),
        })
    catalog = CandidateCatalog(payload, sequences, parts)
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
            row = pending.setdefault(identity, {"query": [], "anchors": set(), "evidence": set()})
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


def partial_source_request(catalog: CandidateCatalog, *, minimum_uncovered_bp: int = 100) -> dict | None:
    """Request evidence for poorly covered pieces of an already grouped source.

    Whole source segments remain mapper context. This is a targeted subset of
    queries against the anchored set, not unconditional genome all-versus-all.
    The coarse coverage screen never authorizes placement or clipping.
    """
    from .q0_sources import subtract_intervals
    coverage = defaultdict(list)
    for candidate in catalog.payload["candidates"]:
        if candidate["placement_kind"] == "reference":
            coverage[candidate["segment_id"]].extend(Interval(*i) for i in candidate["discovery_query_intervals"])
    queries = [key for key, intervals in sorted(coverage.items())
               if any(i.length >= minimum_uncovered_bp for i in subtract_intervals(catalog.parts[key].interval, intervals))]
    anchors = sorted({row["segment_id"] for row in catalog.payload["candidates"]})
    if queries and len(anchors) > 1:
        return {"kind": "partial_source_discovery", "query_ids": queries, "target_ids": anchors,
                "minimum_uncovered_bp": minimum_uncovered_bp}
    return None
