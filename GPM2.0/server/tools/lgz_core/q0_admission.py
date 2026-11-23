"""Validated alignment evidence -> localized source intervals -> q0 paths.

Catalog membership is a discovery fact, never a placement verdict. This module
re-reads the bound PAFs and retains observed competing loci. Original adjacency
may retain an unaligned neighbor, but cannot become an independent seed or a
sequence-overlap anchor. No direct reference coordinates are invented for a
pairwise-derived placement.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
import math
from pathlib import Path
from typing import Mapping

from .common import read_fasta, sha256_file, stable_id
from .q0_alignments import PafAlignment, read_paf
from .q0_catalog import evidence_ref
from .q0_paths import (PairLink, PathGraph, PathPolicy, Placement, ReferenceAnchor,
                       SearchResult, qualify_pair_blocks, reconstruct, search_paths)
from .q0_preparation import artifact_path, json_file, load_verified_evidence, table
from .q0_sources import (Interval, OriginalAdjacency, Q0EvidenceError, SourceKey, SourceSegment,
                         merged_intervals, split_source, subtract_intervals)


@dataclass(frozen=True)
class AdmissionPolicy:
    version: int = 1
    minimum_reference_identity: float = 0.90
    competing_identity_margin: float = 0.02
    minimum_reference_mapq: int = 20
    minimum_anchor_bp: int = 100
    minimum_whole_support_fraction: float = 0.20
    kmer_size: int = 15
    minimum_distinct_kmer_fraction: float = 0.50
    minimum_base_entropy: float = 1.20

    def __post_init__(self):
        for name in ("minimum_reference_identity", "minimum_whole_support_fraction", "minimum_distinct_kmer_fraction"):
            if not 0 < getattr(self, name) <= 1:
                raise Q0EvidenceError(f"invalid q0 admission fraction: {name}")
        if not 0 <= self.competing_identity_margin <= 1 or not 0 <= self.minimum_reference_mapq <= 254:
            raise Q0EvidenceError("invalid q0 competing-hit or MAPQ policy")
        if self.minimum_anchor_bp < 1 or self.kmer_size < 1 or not 0 <= self.minimum_base_entropy <= 2:
            raise Q0EvidenceError("invalid q0 anchor complexity policy")


@dataclass
class EvidenceInput:
    sources: dict[SourceKey, str]
    parts: dict[str, SourceSegment]
    reference_lengths: dict[str, int]
    reference_hits: dict[SourceKey, list[PafAlignment]]
    pair_links: tuple[PairLink, ...]
    original_adjacencies: tuple[OriginalAdjacency, ...]
    evidence: dict[str, dict]
    input_fingerprint: str
    catalog: dict = field(default_factory=dict)
    ready_manifest_identity: str = ""


@dataclass
class Admission:
    placements: tuple[Placement, ...]
    records: list[dict]
    unplaced_segment_ids: tuple[str, ...]
    ambiguous_intervals: dict[SourceKey, tuple[Interval, ...]]
    policy: AdmissionPolicy


@dataclass
class PathSelection:
    admission: Admission
    paths: dict[str, SearchResult]
    occupied: dict[SourceKey, list[Interval]]


@dataclass
class Construction:
    records: dict[str, str]
    paths: dict[str, SearchResult]
    admission: Admission
    decisions: dict


def _size(intervals):
    return sum(i.length for i in merged_intervals(intervals))


def _hull(intervals):
    intervals = tuple(intervals)
    return Interval(min(i.start for i in intervals), max(i.end for i in intervals))


def _project(source: Interval, target: Interval, strand: str, interval: Interval) -> Interval:
    if not source.contains(interval) or source.length != target.length:
        raise Q0EvidenceError("q0 paired-block projection outside evidence")
    if strand == "+":
        return Interval(target.start + interval.start - source.start, target.start + interval.end - source.start)
    return Interval(target.end - (interval.end - source.start), target.end - (interval.start - source.start))


def load_evidence_input(root: Path, *, _draft=None) -> EvidenceInput:
    root = root.resolve()
    def verified():
        return load_verified_evidence(root) if _draft is None else load_verified_evidence(root, _draft=_draft)

    manifest = verified()
    catalog = json_file(artifact_path(root, manifest["catalog"]))
    if catalog.get("min_gap") != manifest["policy"]["min_gap"]:
        raise Q0EvidenceError("q0 catalog gap policy differs from ready manifest")
    datasets = table(root, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath"))
    references = table(root, "metadata/reference.tsv", ("fasta_relpath",))
    sources = {}
    by_dataset = {}
    for row in datasets:
        dataset = row["dataset_name"]
        if dataset in by_dataset:
            raise Q0EvidenceError("duplicate q0 input dataset")
        by_dataset[dataset] = dict(read_fasta(artifact_path(root, row["fasta_relpath"])))
        sources.update((SourceKey(dataset, name), sequence) for name, sequence in by_dataset[dataset].items())
    if len(references) != 1:
        raise Q0EvidenceError("q0 admission requires one reference")
    lengths = {name: len(seq) for name, seq in read_fasta(artifact_path(root, references[0]["fasta_relpath"]))}
    parts, adjacencies = {}, []
    for source, sequence in sorted(sources.items()):
        try:
            index = split_source(source, sequence, min_gap=catalog["min_gap"])
        except Q0EvidenceError:
            continue  # Retained in the catalog with its invalid-sequence verdict.
        parts.update((p.segment_id, p) for p in index.segments)
        adjacencies.extend(index.adjacencies)
    if (sorted((asdict(p) for p in parts.values()), key=lambda p: p["segment_id"])
            != sorted(catalog["segments"], key=lambda p: p["segment_id"])
            or sorted((asdict(e) for e in adjacencies), key=lambda e: e["adjacency_id"])
            != sorted(catalog["original_connections"], key=lambda e: e["adjacency_id"])):
        raise Q0EvidenceError("q0 catalog source geometry differs from original FASTAs")
    reference_hits, evidence, links = defaultdict(list), {}, []
    for dataset, sequences in sorted(by_dataset.items()):
        relative = f"runs/{dataset}_vs_ref/result.paf"
        for hit in read_paf(root / relative, query_lengths={k: len(v) for k, v in sequences.items()},
                            target_lengths=lengths, artifact=relative):
            reference_hits[SourceKey(dataset, hit.query_name)].append(hit)
            evidence[hit.evidence_id] = evidence_ref(hit)
    for descriptor in catalog["base_alignments"]:
        query, target = descriptor["query_dataset"], descriptor["target_dataset"]
        for hit in read_paf(root / descriptor["paf"], query_lengths={k: len(v) for k, v in by_dataset[query].items()},
                            target_lengths={k: len(v) for k, v in by_dataset[target].items()}, artifact=descriptor["paf"]):
            links.append(PairLink(hit, SourceKey(query, hit.query_name), SourceKey(target, hit.target_name)))
            evidence[hit.evidence_id] = evidence_ref(hit)
    visited = set()
    for task in catalog["supplementary_alignments"]:
        if task["paf"] in visited:
            continue
        visited.add(task["paf"])
        for hit in read_paf(root / task["paf"], query_lengths={key: parts[key].interval.length for key in task["query_ids"]},
                            target_lengths={key: parts[key].interval.length for key in task["target_ids"]}, artifact=task["paf"]):
            query, target = parts[hit.query_name], parts[hit.target_name]
            links.append(PairLink(hit, query.source, target.source, query.interval.start, target.interval.start))
            evidence[hit.evidence_id] = evidence_ref(hit)
    for key, row in catalog["evidence"].items():
        if evidence.get(key) != row:
            raise Q0EvidenceError("q0 catalog evidence record differs from the bound PAF")
    for edge in adjacencies:
        evidence[edge.adjacency_id] = {"kind": "input_assembly_adjacency", "catalog": manifest["catalog"], **asdict(edge)}
    if manifest != verified():
        raise Q0EvidenceError("q0 evidence changed during admission loading")
    return EvidenceInput(sources, parts, lengths, dict(reference_hits), tuple(links), tuple(adjacencies),
                         evidence, manifest["input_fingerprint"], catalog, stable_id("q0-ready-evidence", manifest))


def _complex_intervals(sequence: str, interval: Interval, policy: AdmissionPolicy):
    """Local masks, not a whole-record average hiding a repetitive long tail."""
    result = []
    for start in range(interval.start, interval.end, policy.minimum_anchor_bp):
        end = min(interval.end, start + policy.minimum_anchor_bp)
        text = sequence[start:end].upper()
        if len(text) < min(policy.kmer_size, len(sequence)) or set(text) - set("ACGT"):
            continue
        counts = Counter(text)
        entropy = -sum((n / len(text)) * math.log2(n / len(text)) for n in counts.values())
        k = min(policy.kmer_size, len(text))
        kmers = [text[i:i+k] for i in range(len(text) - k + 1)]
        if entropy >= policy.minimum_base_entropy and len(set(kmers)) / len(kmers) >= policy.minimum_distinct_kmer_fraction:
            result.append(Interval(start, end))
    return merged_intervals(result)


@dataclass(frozen=True)
class _RefBlock:
    query: Interval
    target: Interval
    chromosome: str
    strand: str
    evidence_id: str
    identity: float
    mapq: int | None


class _ReferenceBlockCandidates:
    """Safe overlap bounds; a long block may widen the scan, never omit hits."""

    def __init__(self, blocks):
        self.blocks = sorted(blocks, key=lambda b: b.query.start)
        self.starts = []
        self.prefix_end = []
        farthest = 0
        for b in self.blocks:
            farthest = max(farthest, b.query.end)
            self.starts.append(b.query.start)
            self.prefix_end.append(farthest)

    def intersecting(self, interval):
        # Before first: all earlier ends <= interval.start. From stop onward
        # all starts >= interval.end. A remaining block can still be disjoint.
        first = bisect_right(self.prefix_end, interval.start)
        stop = bisect_left(self.starts, interval.end, lo=first)
        for index in range(first, stop):
            other = self.blocks[index]
            overlap = interval.intersection(other.query)
            if overlap is not None:
                yield other, overlap


def _reference_groups(data: EvidenceInput, part: SourceSegment, policy: AdmissionPolicy):
    blocks = []
    for hit in data.reference_hits.get(part.source, ()):
        identity = hit.matches / hit.block_length
        if identity < policy.minimum_reference_identity:
            continue
        for block in hit.aligned_blocks():
            overlap = part.interval.intersection(block.query)
            if overlap is not None and block.operation != "X":
                blocks.append(_RefBlock(overlap, _project(block.query, block.target, hit.strand, overlap),
                                        hit.target_name, hit.strand, hit.evidence_id, identity, hit.mapping_quality))
    groups, high, ambiguity = defaultdict(list), defaultdict(list), []
    candidates = _ReferenceBlockCandidates(blocks)
    for block in blocks:
        conflicts = []
        for other, overlap in candidates.intersecting(block.query):
            if other.identity + policy.competing_identity_margin < block.identity:
                continue
            if (block.chromosome != other.chromosome or block.strand != other.strand
                    or _project(block.query, block.target, block.strand, overlap)
                    != _project(other.query, other.target, other.strand, overlap)):
                conflicts.append(overlap)
        ambiguity.extend(conflicts)
        for unique in subtract_intervals(block.query, conflicts):
            for interval in _complex_intervals(data.sources[part.source], unique, policy):
                anchor = ReferenceAnchor(interval, _project(block.query, block.target, block.strand, interval), block.evidence_id)
                key = (block.chromosome, block.strand)
                groups[key].append(anchor)
                if block.mapq is not None and block.mapq >= policy.minimum_reference_mapq:
                    high[key].append(interval)
    minimum = min(policy.minimum_anchor_bp, part.interval.length)
    groups = {key: tuple(sorted(set(value), key=lambda a: (a.source, a.reference, a.evidence_id)))
              for key, value in groups.items() if _size(a.source for a in value) >= minimum}
    return groups, {key for key in groups if _size(high[key]) >= minimum}, merged_intervals(ambiguity)


def _ordered(anchors, orientation):
    # Only disjoint source intervals constrain order. Scan their two boundary
    # orders together, keeping the one most restrictive earlier reference end
    # (forward) or start (reverse). Touching half-open intervals are disjoint.
    anchors = tuple(anchors)
    if len(anchors) < 2:
        return True
    by_end = sorted(anchors, key=lambda a: a.source.end)
    pointer = 0
    bound = None
    forward = orientation == "+"
    for current in sorted(anchors, key=lambda a: a.source.start):
        while pointer < len(by_end) and by_end[pointer].source.end <= current.source.start:
            ref = by_end[pointer].reference
            pos = ref.end if forward else ref.start
            if bound is None:
                bound = pos
            else:
                bound = max(bound, pos) if forward else min(bound, pos)
            pointer += 1
        if bound is not None and (bound > current.reference.start if forward else current.reference.end > bound):
            return False
    return True


def _placement(part, chromosome, strand, interval, anchors, reference_blocks, evidence_ids, *, kind, seed=True):
    reference_blocks = tuple(reference_blocks)
    evidence_ids = tuple(sorted(set(evidence_ids)))
    identity = [part.segment_id, interval.start, interval.end, chromosome, strand, kind, evidence_ids]
    return Placement(stable_id("q0-placement", identity), part.segment_id, part.source, interval, strand, chromosome,
                     merged_intervals(a.reference for a in reference_blocks), merged_intervals(anchors), evidence_ids,
                     reference_blocks, seed, kind)


def _pair_neighbors(links):
    """Share one encounter-ordered link list between the two source directions."""
    neighbors = defaultdict(dict)
    for link in links:
        a, b = link.query_source, link.target_source
        if a == b:
            continue  # Unchanged admission rule; path construction is separate.
        group = neighbors[a].get(b)
        if group is None:
            group = neighbors[a][b] = neighbors[b][a] = []
        group.append(link)
    return neighbors


class _PlacementNeighbors:
    """Join a fixed placement snapshot to actual pair links, in snapshot order."""

    def __init__(self, placements, links_by_source):
        self.by_source = defaultdict(list)
        for rank, placement in enumerate(placements):
            self.by_source[placement.source].append((rank, placement))
        self.links_by_source = links_by_source

    def for_source(self, source, *, after=-1):
        candidates = [(rank, placement, links)
                      for other, links in self.links_by_source.get(source, {}).items()
                      for rank, placement in self.by_source.get(other, ()) if rank > after]
        return [(placement, links) for _, placement, links in sorted(candidates, key=lambda row: row[0])]


def admit_placements(data: EvidenceInput, *, policy: AdmissionPolicy = AdmissionPolicy(),
                     path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None) -> Admission:
    if quality_pass is not None and (set(quality_pass) != set(data.sources) or any(type(v) is not bool for v in quality_pass.values())):
        raise Q0EvidenceError("q0 QC decisions must explicitly cover every source")
    records, accepted = [], {}
    groups, high, ambiguous = {}, {}, defaultdict(list)
    allowed = {key for key in data.parts if quality_pass is None or quality_pass[data.parts[key].source]}
    for key, part in sorted(data.parts.items()):
        if key not in allowed:
            records.append({"segment_id": key, "status": "rejected", "reason": "failed_reads_qc"})
            continue
        groups[key], high[key], mask = _reference_groups(data, part, policy)
        ambiguous[part.source].extend(mask)
        records.append({"segment_id": key, "status": "reference_screen",
                        "evidence_ids": sorted(h.evidence_id for h in data.reference_hits.get(part.source, ()) if h.query.intersection(part.interval)),
                        "unique_groups": [{"chromosome": group[0], "orientation": group[1],
                                           "support_bp": _size(a.source for a in anchors)} for group, anchors in sorted(groups[key].items())],
                        "ambiguous_intervals": [asdict(i) for i in mask]})
        if len(groups[key]) == 1 and high[key] and all(_ordered(anchors, group[1]) for group, anchors in groups[key].items()):
            (chromosome, strand), anchors = next(iter(groups[key].items()))
            support = merged_intervals(a.source for a in anchors)
            interval = part.interval if _size(support) / part.interval.length >= policy.minimum_whole_support_fraction else _hull(support)
            placement = _placement(part, chromosome, strand, interval, support, anchors,
                                   (a.evidence_id for a in anchors), kind="reference")
            accepted[placement.placement_id] = placement
            records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted",
                            "reason": "unique_reference_blocks" if interval == part.interval else "supported_reference_subinterval",
                            "qc": "not_measured" if quality_pass is None else "passed"})
    ambiguous = {key: merged_intervals(value) for key, value in ambiguous.items()}
    pair_neighbors = _pair_neighbors(data.pair_links)

    def clean_intervals(part, intervals):
        return merged_intervals(piece for i in intervals
                                for unique in subtract_intervals(i, ambiguous.get(part.source, ()))
                                for piece in _complex_intervals(data.sources[part.source], unique, policy))

    # Revisit a reference seed when independently ref-anchored sequence on
    # another chr supports a previously unlocalized tail. This is local source
    # selection, not a claim that the input assembler made a biological error.
    reference_seeds = tuple(accepted.values())
    seed_neighbors = _PlacementNeighbors(reference_seeds, pair_neighbors)
    for current in reference_seeds:
        part = data.parts[current.segment_id]
        if current.interval != part.interval:
            continue
        main_anchors = merged_intervals(a.source for a in current.reference_blocks)
        alternatives = defaultdict(lambda: {"intervals": [], "ids": set(), "parents": set()})
        linked_seeds = seed_neighbors.for_source(current.source)
        for anchor, links in linked_seeds:
            if anchor.chromosome == current.chromosome:
                continue
            for orientation in ("+", "-"):
                probe = _placement(part, anchor.chromosome, orientation, part.interval, (part.interval,), (),
                                   (link.hit.evidence_id for link in links), kind="pairwise")
                qualified = qualify_pair_blocks(probe, anchor, links, path_policy, require_supported=False)
                by_evidence = defaultdict(list)
                for block, eid in qualified:
                    for target_anchor in anchor.reference_blocks:
                        overlap = block.right.intersection(anchor.local(target_anchor.source))
                        if overlap:
                            start = block.left.start + overlap.start - block.right.start
                            by_evidence[eid].append(probe.source_interval(Interval(start, start + overlap.length)))
                for eid, intervals in by_evidence.items():
                    # A chain also matching the known chr locus is a repeated
                    # sequence relationship, not evidence for moving its tail.
                    if _size(overlap for a in intervals for b in main_anchors
                             if (overlap := a.intersection(b))) >= policy.minimum_anchor_bp:
                        continue
                    clean = clean_intervals(part, intervals)
                    if _size(clean) < policy.minimum_anchor_bp:
                        continue
                    item = alternatives[(anchor.chromosome, orientation)]
                    item["intervals"].extend(clean)
                    item["ids"].update({eid, *anchor.evidence_ids})
                    item["parents"].add(anchor.placement_id)
        if not alternatives:
            continue
        continuity_ids = set()
        for anchor, links in linked_seeds:
            if anchor.chromosome != current.chromosome:
                continue
            by_evidence = defaultdict(list)
            for block, eid in qualify_pair_blocks(current, anchor, links, path_policy, require_supported=False):
                by_evidence[eid].append(current.source_interval(block.left))
            for eid, intervals in by_evidence.items():
                left_support = _size(overlap for a in intervals for b in main_anchors if (overlap := a.intersection(b)))
                right_support = _size(overlap for a in intervals for value in alternatives.values()
                                      for b in value["intervals"] if (overlap := a.intersection(b)))
                if min(left_support, right_support) >= policy.minimum_anchor_bp:
                    continuity_ids.add(eid)
        if continuity_ids:
            records.append({"placement_id": current.placement_id, "status": "retained",
                            "reason": "cross_chr_tail_continuity_supported", "evidence_ids": sorted(continuity_ids),
                            "competing_evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
            continue
        main_interval = _hull(main_anchors)
        bounds = [_hull(value["intervals"]) for value in alternatives.values()]
        if any(main_interval.intersection(i) for i in bounds) or any(a.intersection(b) for n, a in enumerate(bounds) for b in bounds[n+1:]):
            records.append({"placement_id": current.placement_id, "status": "unresolved",
                            "reason": "overlapping_structural_selection_bounds",
                            "evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
            continue
        accepted.pop(current.placement_id)
        records.append({"placement_id": current.placement_id, "placement": asdict(current), "status": "superseded",
                        "reason": "independently_anchored_cross_chr_tail"})
        main = _placement(part, current.chromosome, current.orientation, main_interval, main_anchors,
                          current.reference_blocks, current.evidence_ids, kind="reference")
        accepted[main.placement_id] = main
        records.append({"placement_id": main.placement_id, "segment_id": part.segment_id, "status": "accepted",
                        "reason": "supported_local_interval", "replaces_placement_id": current.placement_id})
        for (chromosome, strand), value in sorted(alternatives.items()):
            interval = _hull(value["intervals"])
            local = _placement(part, chromosome, strand, interval, value["intervals"], (), value["ids"], kind="pairwise")
            accepted[local.placement_id] = local
            records.append({"placement_id": local.placement_id, "segment_id": part.segment_id, "status": "accepted",
                            "reason": "independently_anchored_cross_chr_tail", "anchor_placement_ids": sorted(value["parents"])})

    # A fragmented pair can have thousands of CIGAR blocks rooting to the
    # same immutable admitted span. Screen that full source context once,
    # not once per block. Keep the cache local to this admission and bounded.
    @lru_cache(maxsize=128)
    def rooted_context(segment_id, interval):
        return clean_intervals(data.parts[segment_id], (interval,))

    # Only previous-round independent anchors can establish new placements.
    # Multiple loci/strands remain alternatives, not a majority vote by ds.
    for round_number in range(1, len(data.parts) + 1):
        before = tuple(accepted.values())
        placed = {p.segment_id for p in before}
        placed_neighbors = _PlacementNeighbors(before, pair_neighbors)
        proposed = defaultdict(dict)
        for key in sorted(allowed - placed):
            part = data.parts[key]
            for anchor, links in placed_neighbors.for_source(part.source):
                for orientation in ("+", "-"):
                    # Geometry probe has explicit raw evidence; it is never returned as admitted.
                    temporary = _placement(part, anchor.chromosome, orientation, part.interval, (part.interval,), (),
                                           (l.hit.evidence_id for l in links), kind="pairwise")
                    qualified = qualify_pair_blocks(temporary, anchor, links, path_policy, require_supported=False)
                    if not qualified:
                        continue
                    # Full accepted contig context can root an off-ref
                    # neighbor; known ambiguous/repetitive positions cannot.
                    context = rooted_context(anchor.segment_id, anchor.interval)
                    intervals, ids = [], set()
                    for block, evidence_id in qualified:
                        for source_anchor in context:
                            overlap = block.right.intersection(anchor.local(source_anchor))
                            if overlap is None:
                                continue
                            start = block.left.start + overlap.start - block.right.start
                            intervals.append(temporary.source_interval(Interval(start, start + overlap.length)))
                            ids.add(evidence_id)
                    intervals = clean_intervals(part, intervals)
                    if _size(intervals) < min(policy.minimum_anchor_bp, part.interval.length):
                        continue
                    group = (anchor.chromosome, orientation)
                    # Contradictory uniquely localized ref segments are never
                    # overridden by a pairwise vote. They can support selection
                    # of a bounded local interval instead of the whole parent.
                    direct = groups.get(key, {}).get(group, ())
                    if groups.get(key) and not direct:
                        continue
                    item = proposed[key].setdefault(group, {"intervals": [], "ids": set(), "parents": set(), "refs": direct})
                    if direct:
                        intervals = merged_intervals(overlap for a in intervals for b in direct
                                                     if (overlap := a.intersection(b.source)) is not None)
                    item["intervals"].extend(intervals)
                    item["ids"].update(ids | set(anchor.evidence_ids))
                    item["parents"].add(anchor.placement_id)
        added = 0
        for key, alternatives in sorted(proposed.items()):
            part = data.parts[key]
            alternatives = {group: value for group, value in alternatives.items()
                            if _size(value["intervals"]) >= min(policy.minimum_anchor_bp, part.interval.length)}
            bounds = {group: _hull(a.source for a in value["refs"]) if value["refs"] else _hull(value["intervals"])
                      for group, value in alternatives.items()}
            if any(bounds[a].intersection(bounds[b]) for i, a in enumerate(bounds) for b in list(bounds)[i+1:]):
                records.append({"segment_id": key, "status": "unresolved", "reason": "competing_pairwise_loci", "round": round_number,
                                "evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
                continue
            for (chromosome, strand), value in sorted(alternatives.items()):
                support = merged_intervals(value["intervals"])
                partial = len(groups.get(key, {})) > 1 or len(alternatives) > 1 or _size(support) / part.interval.length < policy.minimum_whole_support_fraction
                interval = bounds[(chromosome, strand)] if partial else part.interval
                refs = []
                for a in value["refs"]:
                    overlap = a.source.intersection(interval)
                    if overlap:
                        refs.append(ReferenceAnchor(overlap, _project(a.source, a.reference, strand, overlap), a.evidence_id))
                if not _ordered(refs, strand):
                    records.append({"segment_id": key, "status": "unresolved", "reason": "noncollinear_reference_anchors",
                                    "evidence_ids": sorted(value["ids"])})
                    continue
                placement = _placement(part, chromosome, strand, interval, merged_intervals((*support, *(a.source for a in refs))), refs,
                                       value["ids"] | {a.evidence_id for a in refs}, kind="pairwise")
                accepted[placement.placement_id] = placement
                records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted",
                                "reason": "supported_local_interval" if partial else "pairwise_reference_anchoring",
                                "anchor_placement_ids": sorted(value["parents"]), "round": round_number,
                                "qc": "not_measured" if quality_pass is None else "passed"})
                added += 1
        if not added:
            break

    rooted_context.cache_clear()

    # Extend supported anchors into non-ref sequence only with a noncompeting,
    # high-complexity pair match between already localized sources. Direct ref
    # blocks check actual corresponding loci, not reference hull intersection.
    additions = defaultdict(list)
    addition_ids = defaultdict(set)
    placed_list = sorted(accepted.values(), key=lambda p: p.placement_id)
    placed_neighbors = _PlacementNeighbors(placed_list, pair_neighbors)
    for i, left in enumerate(placed_list):
        for right, links in placed_neighbors.for_source(left.source, after=i):
            if left.chromosome != right.chromosome:
                continue
            for block, evidence_id in qualify_pair_blocks(left, right, links, path_policy, require_supported=False):
                for placement, interval in ((left, left.source_interval(block.left)), (right, right.source_interval(block.right))):
                    part = data.parts[placement.segment_id]
                    clean = clean_intervals(part, (interval,))
                    additions[placement.placement_id].extend(clean)
                    addition_ids[placement.placement_id].add(evidence_id)
    for key, intervals in additions.items():
        p = accepted[key]
        accepted[key] = replace(p, anchor_intervals=merged_intervals((*p.anchor_intervals, *intervals)),
                                evidence_ids=tuple(sorted(set(p.evidence_ids) | addition_ids[key])))
        records.append({"placement_id": key, "status": "anchor_extension", "reason": "localized_pairwise_sequence_context",
                        "evidence_ids": sorted(addition_ids[key])})

    # Original assembly N adjacency is a soft relation, not a new independent
    # sequence anchor. Unaligned neighbors can only survive attached to a seed.
    for round_number in range(1, len(data.parts) + 1):
        by_part = defaultdict(list)
        for p in accepted.values():
            by_part[p.segment_id].append(p)
        proposed = defaultdict(list)
        for edge in data.original_adjacencies:
            for missing, other in ((edge.left_segment_id, edge.right_segment_id), (edge.right_segment_id, edge.left_segment_id)):
                if missing in allowed and missing not in by_part:
                    for parent in by_part[other]:
                        proposed[missing].append((parent, edge))
        added = 0
        for key, contexts in sorted(proposed.items()):
            identities = {(p.chromosome, p.orientation) for p, _ in contexts}
            if (len(identities) != 1 or any(group not in identities for group in groups.get(key, {}))
                    or any(not _ordered(anchors, group[1]) for group, anchors in groups.get(key, {}).items())):
                records.append({"segment_id": key, "status": "unresolved", "reason": "input_adjacency_conflict"})
                continue
            chromosome, strand = next(iter(identities))
            part = data.parts[key]
            ids = {edge.adjacency_id for _, edge in contexts} | {eid for p, _ in contexts for eid in p.evidence_ids}
            placement = _placement(part, chromosome, strand, part.interval, (), (), ids, kind="input_adjacency", seed=False)
            accepted[placement.placement_id] = placement
            records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted_soft_neighbor",
                            "reason": "input_assembly_adjacency", "anchor_placement_ids": sorted(p.placement_id for p, _ in contexts)})
            added += 1
        if not added:
            break
    placed = {p.segment_id for p in accepted.values()}
    for key in sorted(allowed - placed):
        records.append({"segment_id": key, "status": "unresolved",
                        "reason": ("structural_ref_conflict" if len(groups.get(key, {})) > 1 else
                                   "noncollinear_reference_anchors" if any(not _ordered(a, g[1]) for g, a in groups.get(key, {}).items()) else
                                   "no_sufficient_localization_evidence")})
    return Admission(tuple(sorted(accepted.values(), key=lambda p: p.placement_id)), records,
                     tuple(sorted(set(data.parts) - placed)), ambiguous, policy)


def _links_for_path_graphs(placements, links):
    # A graph's lookup and coverage model only consume pairs where both
    # endpoints have a placement on its chromosome. Keep all such records in
    # original order (including conflicts and same-source non-overlap links).
    chromosomes_by_source = defaultdict(set)
    for placement in placements:
        chromosomes_by_source[placement.source].add(placement.chromosome)
    by_chromosome = defaultdict(list)
    absent = frozenset()
    for link in links:
        for chromosome in chromosomes_by_source.get(link.query_source, absent) & chromosomes_by_source.get(link.target_source, absent):
            by_chromosome[chromosome].append(link)
    return by_chromosome


def select_q0_paths(data: EvidenceInput, *, admission_policy: AdmissionPolicy = AdmissionPolicy(),
                    path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None) -> PathSelection:
    """Select and check source geometry without reconstructing sequences or building a report."""
    admission = admit_placements(data, policy=admission_policy, path_policy=path_policy, quality_pass=quality_pass)
    groups = defaultdict(list)
    for placement in admission.placements:
        groups[placement.chromosome].append(placement)
    searches, occupied = {}, defaultdict(list)
    graph_links = _links_for_path_graphs(admission.placements, data.pair_links)
    for chromosome in sorted(data.reference_lengths):
        search = search_paths(PathGraph(groups[chromosome], graph_links.get(chromosome, ()), data.original_adjacencies, path_policy))
        searches[chromosome] = search
        if search.path is None:
            continue
        for item in search.path.slices:
            if item.interval.end > len(data.sources[item.source]):
                raise Q0EvidenceError("q0 path source exceeds sequence length")
            if any(item.interval.intersection(previous) for previous in occupied[item.source]):
                raise Q0EvidenceError("q0 source interval selected on multiple chromosomes")
            occupied[item.source].append(item.interval)
        for join in search.path.joins:
            if join.kind == "input_assembly_gap":
                if any(join.gap_interval.intersection(previous) for previous in occupied[join.gap_source]):
                    raise Q0EvidenceError("original N source interval selected more than once")
                occupied[join.gap_source].append(join.gap_interval)
    return PathSelection(admission, searches, occupied)


def construct_q0(data: EvidenceInput, *, admission_policy: AdmissionPolicy = AdmissionPolicy(),
                 path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None) -> Construction:
    selection = select_q0_paths(data, admission_policy=admission_policy, path_policy=path_policy,
                                quality_pass=quality_pass)
    admission, searches, occupied = selection.admission, selection.paths, selection.occupied
    if not any(search.path is not None for search in searches.values()):
        raise Q0EvidenceError("no chromosome has a trustworthy q0 path")
    if "supplement_scope" in data.catalog:
        from .q0_frontier_scope import audit_selected_scope
        audit_selected_scope(data, admission, searches)
    records, chromosomes = {}, []
    by_id = {p.placement_id: p for p in admission.placements}
    for chromosome, search in searches.items():
        if search.path is None:
            chromosomes.append({"chromosome": chromosome, "status": "not_constructed"})
            continue
        ref_coverage = []
        for item in search.path.slices:
            placement = by_id[item.placement_id]
            for anchor in placement.reference_blocks:
                overlap = anchor.source.intersection(item.interval)
                if overlap:
                    ref_coverage.append(_project(anchor.source, anchor.reference, item.orientation, overlap))
        records[chromosome] = reconstruct(search.path, data.sources)
        length = data.reference_lengths[chromosome]
        chromosomes.append({"chromosome": chromosome, "status": "partial_path",
                            "reference_unrepresented": [asdict(i) for i in subtract_intervals(Interval(0, length), ref_coverage)],
                            "unknown_joins": sum(j.kind == "reference_unknown" for j in search.path.joins),
                            "input_gap_joins": sum(j.kind == "input_assembly_gap" for j in search.path.joins)})
    decisions = {"schema": "lgz_q0_construction_v1", "input_fingerprint": data.input_fingerprint,
                 "admission_policy": asdict(admission_policy), "path_policy": asdict(path_policy),
                 "selector_identity": selector_identity(), "ready_manifest_identity": data.ready_manifest_identity,
                 "qc_source_decisions": [] if quality_pass is None else [
                     {"source": asdict(source), "passed": passed} for source, passed in sorted(quality_pass.items())],
                 "placements": [asdict(p) for p in admission.placements], "admission": admission.records,
                 "unplaced_segment_ids": list(admission.unplaced_segment_ids), "chromosomes": chromosomes,
                 "searches": {key: value.record() for key, value in searches.items()},
                 "occupied_intervals": [{"source": asdict(source), "intervals": [asdict(i) for i in merged_intervals(intervals)]}
                                         for source, intervals in sorted(occupied.items())],
                 "unselected_source_intervals": [{"source": asdict(source), "intervals": [asdict(i) for i in (subtract_intervals(Interval(0, len(sequence)), occupied[source]) if sequence else ())]}
                                                 for source, sequence in sorted(data.sources.items())],
                 "qc": "not_measured" if quality_pass is None else "supplied_source_decisions"}
    used_ids = set()
    def evidence_ids(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"evidence_ids", "competing_evidence_ids"}:
                    used_ids.update(item)
                elif key in {"evidence_id", "original_adjacency_id"} and item:
                    used_ids.add(item)
                else:
                    evidence_ids(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                evidence_ids(item)
    evidence_ids(decisions)
    if used_ids - set(data.evidence):
        raise Q0EvidenceError("q0 construction references missing evidence records")
    decisions["evidence"] = {key: data.evidence[key] for key in sorted(used_ids)}
    return Construction(records, searches, admission, decisions)


def selector_identity() -> str:
    root = Path(__file__).parent
    return stable_id("q0-selector", [(name, sha256_file(root / name)) for name in
                                    ("q0_admission.py", "q0_paths.py", "q0_coverage.py", "q0_sources.py", "q0_alignments.py", "q0_frontier_scope.py", "common.py")])


def build_q0(root: Path, **kwargs) -> Construction:
    before = selector_identity()
    data = load_evidence_input(root)
    result = construct_q0(data, **kwargs)
    if stable_id("q0-ready-evidence", load_verified_evidence(root)) != data.ready_manifest_identity:
        raise Q0EvidenceError("q0 evidence changed while selecting paths")
    if selector_identity() != before:
        raise Q0EvidenceError("q0 selector changed while building paths")
    return result
