"""Validated alignment evidence -> localized source intervals -> q0 paths.

Catalog membership is a discovery fact, never a placement verdict. This module
re-reads the bound PAFs and retains observed competing loci. Original adjacency
may retain an unaligned neighbor, but cannot become an independent seed or a
sequence-overlap anchor. No direct reference coordinates are invented for a
pairwise-derived placement.
"""
from __future__ import annotations

from array import array
from bisect import bisect_right
from collections import Counter, OrderedDict, defaultdict
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
import math
from operator import attrgetter
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, strftime
from typing import Callable, Mapping

from .common import read_fasta, sha256_file, stable_id
from .q0_alignments import PafAlignment, read_paf
from .q0_catalog import evidence_ref
from .q0_reference_competition import reference_masks
from .q0_paths import (PairLink, PathGraph, PathPolicy, Placement, ReferenceAnchor, RequestPathResult,
                       SearchResult, qualify_pair_blocks, reconstruct, search_paths, search_request_path)
from .q0_preparation import artifact_path, json_file, load_verified_evidence, table
from .q0_sources import (Interval, OriginalAdjacency, Q0EvidenceError, SourceKey, SourceSegment,
                         merged_intervals, split_source, subtract_intervals)


from .q0_collinear import ContinuousAdmissionPolicy, continuous_candidates


@dataclass(frozen=True)
class AdmissionPolicy:
    version: int = 2
    minimum_reference_identity: float = 0.90
    competing_identity_margin: float = 0.02
    minimum_reference_mapq: int = 20
    minimum_anchor_bp: int = 100
    minimum_whole_support_fraction: float = 0.20
    kmer_size: int = 15
    minimum_distinct_kmer_fraction: float = 0.50
    minimum_base_entropy: float = 1.20
    continuous: ContinuousAdmissionPolicy | None = ContinuousAdmissionPolicy()

    def __post_init__(self):
        if self.continuous is not None and not isinstance(self.continuous, ContinuousAdmissionPolicy):
            raise Q0EvidenceError("invalid continuous reference admission policy")
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
    evidence: Mapping[str, dict]
    input_fingerprint: str
    catalog: dict = field(default_factory=dict)
    ready_manifest_identity: str = ""
    threshold_scope: object | None = None
    verified_manifest: dict | None = field(default=None, repr=False, compare=False)


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
class RequestAdmission:
    placements: tuple[Placement, ...]


@dataclass
class FirstRequestSelection:
    admission: RequestAdmission
    paths: dict[str, RequestPathResult]


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
    # The full source maps to the full target in either orientation.
    if interval is source or (interval.start == source.start and interval.end == source.end):
        return target
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
    threshold = 'threshold' in manifest['policy'].get('decision_frontier', {})
    stored, links, reference_hits = {}, [], defaultdict(list)
    if threshold:
        from .q0_retained_hits import EvidenceRows, RetainedHit
        keys = {(s.dataset, s.contig): s for s in sources}
        ref_names = {name: name for name in lengths}
        evidence = EvidenceRows(stored)
    else:
        evidence = stored
    for dataset, sequences in sorted(by_dataset.items()):
        relative = f"runs/{dataset}_vs_ref/result.paf"
        for hit in read_paf(artifact_path(root, relative), query_lengths={k: len(v) for k, v in sequences.items()},
                            target_lengths=lengths, artifact=relative):
            source = keys[dataset, hit.query_name] if threshold else SourceKey(dataset, hit.query_name)
            if threshold:
                hit = RetainedHit.from_validated(hit, source.contig, ref_names[hit.target_name])
            reference_hits[source].append(hit)
            stored[hit.evidence_id] = hit if threshold else evidence_ref(hit)
    for descriptor in catalog["base_alignments"]:
        query, target = descriptor["query_dataset"], descriptor["target_dataset"]
        for hit in read_paf(artifact_path(root, descriptor["paf"]), query_lengths={k: len(v) for k, v in by_dataset[query].items()},
                            target_lengths={k: len(v) for k, v in by_dataset[target].items()}, artifact=descriptor["paf"]):
            if threshold:
                q, t = keys[query, hit.query_name], keys[target, hit.target_name]
                hit = RetainedHit.from_validated(hit, q.contig, t.contig)
            else:
                q, t = SourceKey(query, hit.query_name), SourceKey(target, hit.target_name)
            links.append(PairLink(hit, q, t))
            stored[hit.evidence_id] = hit if threshold else evidence_ref(hit)
    visited = set()
    for task in catalog["supplementary_alignments"]:
        if task["paf"] in visited:
            continue
        visited.add(task["paf"])
        for hit in read_paf(artifact_path(root, task["paf"]), query_lengths={key: parts[key].interval.length for key in task["query_ids"]},
                            target_lengths={key: parts[key].interval.length for key in task["target_ids"]}, artifact=task["paf"]):
            query, target = parts[hit.query_name], parts[hit.target_name]
            if threshold:
                hit = RetainedHit.from_validated(hit, query.segment_id, target.segment_id)
            links.append(PairLink(hit, query.source, target.source, query.interval.start, target.interval.start))
            stored[hit.evidence_id] = hit if threshold else evidence_ref(hit)
    for key, row in catalog["evidence"].items():
        if evidence.get(key) != row:
            raise Q0EvidenceError("q0 catalog evidence record differs from the bound PAF")
    for edge in adjacencies:
        stored[edge.adjacency_id] = {"kind": "input_assembly_adjacency", "catalog": manifest["catalog"], **asdict(edge)}
    ready_id = stable_id("q0-ready-evidence", manifest)
    binding = None
    if "threshold" in manifest["policy"].get("decision_frontier", {}):
        from .q0_threshold_acceptance import VerifiedScope
        keys = ("dataset_name", "seq_name", "assigned_chr_name")
        binding = VerifiedScope(ready_id, tuple(tuple(row[k] for k in keys) for row in table(root, "metadata/chr_assignments.tsv", keys)),
                                stable_id("threshold-search", catalog["supplement_scope"]))
    if manifest != verified():
        raise Q0EvidenceError("q0 evidence changed during admission loading")
    return EvidenceInput(sources, parts, lengths, dict(reference_hits), tuple(links), tuple(adjacencies),
                         evidence, manifest["input_fingerprint"], catalog, ready_id, binding, manifest)


_DNA = frozenset("ACGT")


@lru_cache(maxsize=64)
def _window_plan(n, k, fraction):
    # Small windows only. Cache arithmetic/slices, never source sequence or verdicts.
    terms = tuple((i/n) * math.log2(i/n) if i else 0.0 for i in range(n + 1))
    total = n - k + 1
    # Use the original division (including equality and one-ULP boundaries).
    wanted = next(i for i in range(1, total + 1) if i / total >= fraction)
    spans = tuple(slice(i, i+k) for i in range(total))
    return terms, wanted, spans[:wanted], spans[wanted:]


def _passes_complexity(text, policy):
    n = len(text)
    if 64 <= n <= 256:
        # Four native string scans are cheaper than building a per-character Counter.
        # Keep its first-occurrence order for the identical entropy sum, even at a one-ULP tie.
        counts = [c for base in sorted("ACGT", key=text.find) if (c := text.count(base))]
        if sum(counts) != n:
            return False
    else:
        histogram = Counter(text)
        if not histogram.keys() <= _DNA:
            return False
        counts = histogram.values()
    k = min(policy.kmer_size, n)
    if n <= 256:
        terms, wanted, first, rest = _window_plan(n, k, policy.minimum_distinct_kmer_fraction)
        if -sum(terms[v] for v in counts) < policy.minimum_base_entropy:
            return False
        distinct = set(map(text.__getitem__, first))
        if len(distinct) < wanted:
            distinct.update(map(text.__getitem__, rest))
        return len(distinct) >= wanted
    # A custom large window must not leave O(window size) slicing plans in memory.
    if -sum((v/n) * math.log2(v/n) for v in counts) < policy.minimum_base_entropy:
        return False
    total = n - k + 1
    return len({text[i:i+k] for i in range(total)}) / total >= policy.minimum_distinct_kmer_fraction


def _complex_intervals(sequence: str, interval: Interval, policy: AdmissionPolicy):
    """Screen on the original local grid; emit maximal passing runs directly."""
    result = []
    run = None
    minimum = min(policy.kmer_size, len(sequence))
    for start in range(interval.start, interval.end, policy.minimum_anchor_bp):
        end = min(interval.end, start + policy.minimum_anchor_bp)
        if end - start >= minimum and _passes_complexity(sequence[start:end].upper(), policy):
            if run is None:
                run = start
        elif run is not None:
            result.append(Interval(run, start))
            run = None
    if run is not None:
        result.append(Interval(run, interval.end))
    return tuple(result)


_end = attrgetter("end")


def _outside_merged_mask(span, mask):
    """Subtract a previously merged mask; touching endpoints are not overlaps."""
    cursor = span.start
    for i in range(bisect_right(mask, cursor, key=_end), len(mask)):
        other = mask[i]
        if other.start >= span.end:
            break
        if cursor < other.start:
            yield Interval(cursor, other.start)
        cursor = other.end
        if cursor >= span.end:
            return
    if cursor == span.start:
        yield span
    else:
        yield Interval(cursor, span.end)


@dataclass(frozen=True)
class _RefBlock:
    query: Interval
    target: Interval
    chromosome: str
    strand: str
    evidence_id: str
    identity: float
    mapq: int | None


def _possible_support_bp(blocks, masks, minimum):
    # The sum can overcount overlapping spans, so it can rule groups out, never in.
    bounds = defaultdict(int)
    for block, spans in zip(blocks, masks):
        key = (block.chromosome, block.strand)
        total = bounds[key]
        if total < minimum:
            for span in spans:
                total += span.length
                if total >= minimum:
                    break
            bounds[key] = total
    return bounds


def _reference_groups(data: EvidenceInput, part: SourceSegment, policy: AdmissionPolicy, *, evidence_ids=None, high_intervals=False):
    blocks = []
    for hit in data.reference_hits.get(part.source, ()):
        if hit.query.end <= part.interval.start or hit.query.start >= part.interval.end:
            continue  # No CIGAR run from this hit can intersect this part.
        if evidence_ids is not None:
            # Report every intersecting hit, even if it supplies no admissible anchor.
            evidence_ids.append(hit.evidence_id)
        identity = hit.matches / hit.block_length
        if identity < policy.minimum_reference_identity:
            continue
        for block in hit.aligned_blocks():
            if block.operation == "X":
                continue
            # Reuse the immutable original span unless the part actually clips it.
            overlap = block.query if part.interval.contains(block.query) else part.interval.intersection(block.query)
            if overlap is not None:
                blocks.append(_RefBlock(overlap, _project(block.query, block.target, hit.strand, overlap),
                                        hit.target_name, hit.strand, hit.evidence_id, identity, hit.mapping_quality))
    groups, high = defaultdict(list), defaultdict(list)
    masks, ambiguity = reference_masks(blocks, policy.competing_identity_margin)
    minimum = min(policy.minimum_anchor_bp, part.interval.length)
    bounds = None
    for block, unique_intervals in zip(blocks, masks):
        if not unique_intervals:
            continue
        key = (block.chromosome, block.strand)
        # A long span already makes this group a possible candidate. Only build
        # the per-group bounds if a short span needs its other blocks considered.
        if unique_intervals[0].length < minimum:
            if bounds is None:
                bounds = _possible_support_bp(blocks, masks, minimum)
            if bounds[key] < minimum:
                continue
        for unique in unique_intervals:
            for interval in _complex_intervals(data.sources[part.source], unique, policy):
                anchor = ReferenceAnchor(interval, _project(block.query, block.target, block.strand, interval), block.evidence_id)
                groups[key].append(anchor)
                if block.mapq is not None and block.mapq >= policy.minimum_reference_mapq:
                    high[key].append(interval)
    groups = {key: tuple(sorted(set(value), key=lambda a: (a.source, a.reference, a.evidence_id)))
              for key, value in groups.items() if _size(a.source for a in value) >= minimum}
    eligible = {key: merged_intervals(high[key]) for key in groups if _size(high[key]) >= minimum}
    return groups, eligible if high_intervals else set(eligible), ambiguity


def _reference_screen(data, part, policy):
    evidence_ids = []
    groups, high, ambiguity = _reference_groups(data, part, policy, evidence_ids=evidence_ids, high_intervals=policy.continuous is not None)
    evidence_ids.sort()  # Same report order and multiplicity for serial and worker results.
    return groups, high, ambiguity, evidence_ids


def _request_reference_screen(data, part, policy):
    # Keep every ID attached to an actual anchor. Only the report-only list of
    # all intersecting hits (including rejected hits) is not built or sorted.
    return (*_reference_groups(data, part, policy, high_intervals=policy.continuous is not None), ())


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


def _quiet(_message: str) -> None:
    pass


class _PlacementProgress:
    """One optional reporter per admission. A long single item still gets a heartbeat."""

    def __init__(self, log):
        self.log = log
        self.stop = Event()
        self.lock = Lock()
        self.state = None
        self.thread = None

    def __enter__(self):
        return self

    def _message(self, status):
        label, start, count, total = self.state
        units = "" if total is None else f" completed={count}/{total}"
        return f"placement {label}: {status}{units} elapsed_s={int(monotonic() - start)}"

    def emit(self, message):
        # The heartbeat calls the same sink under this lock. Keep its newline
        # together with its message even when the coordinator reports at once.
        with self.lock:
            self.log(message)

    def _heartbeat(self):
        while not self.stop.wait(60):
            with self.lock:
                if self.state:
                    self.log(self._message("working"))

    def start(self, label, total=None):
        if self.log is _quiet:
            return
        with self.lock:
            if self.state:
                self.log(self._message("finished"))
            self.state = [label, monotonic(), 0, total]
            self.log(self._message("started"))
        if self.thread is None:
            self.thread = Thread(target=self._heartbeat, name="q0-placement-progress", daemon=True)
            self.thread.start()

    def completed(self, count):
        if self.log is not _quiet:
            with self.lock:
                self.state[2] = count

    def items(self, label, values):
        if self.log is _quiet:
            yield from values
            return
        self.start(label, len(values))
        for index, value in enumerate(values, 1):
            yield value
            with self.lock:
                self.state[2] = index

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
            self.log(self._message("finished" if exc_type is None else "interrupted"))


def _overlapping_spans(span, disjoint):
    """Original source order, half-open overlaps; disjoint is sorted and merged."""
    for i in range(bisect_right(disjoint, span.start, key=_end), len(disjoint)):
        candidate = disjoint[i]
        if candidate.start >= span.end:
            break
        yield candidate


def _clean_source_intervals(sequence, mask, intervals, policy):
    return merged_intervals(piece for i in intervals for unique in _outside_merged_mask(i, mask)
                            for piece in _complex_intervals(sequence, unique, policy))


class _PackedIntervals:
    """Lossless source-coordinate runs: bounded by bytes, not Python objects."""
    def __init__(self, spans):
        self.coordinates = array("Q", (n for iv in spans for n in (iv.start, iv.end)))

    def __len__(self):
        return len(self.coordinates) // 2

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return Interval(self.coordinates[2 * index], self.coordinates[2 * index + 1])

    @property
    def nbytes(self):
        return len(self.coordinates) * self.coordinates.itemsize


class _ComplexityCache:
    """Exact original windows, including their phase and short end window.

    A window starting at 101 is NOT interchangeable with one starting at 100.
    Byte-packed blocks avoid millions of Python tuple keys. Cache eviction only
    repeats computation; it never changes thresholds, mask edges, or the grid.
    """
    BLOCK_WINDOWS = 4096
    MAX_BLOCKS = 16384  # 64 MiB of verdict bytes, plus bounded index overhead
    MAX_SHORT = 4096

    def __init__(self, policy):
        self.policy = policy
        self.blocks, self.short = OrderedDict(), OrderedDict()
        self.hits = self.misses = 0

    def passes(self, sequence, source, start, end):
        width = self.policy.minimum_anchor_bp
        if end - start == width:
            block, offset = divmod(start // width, self.BLOCK_WINDOWS)
            key = source, start % width, block
            data = self.blocks.get(key)
            if data is None:
                if len(self.blocks) >= self.MAX_BLOCKS:
                    self.blocks.popitem(last=False)
                data = self.blocks[key] = bytearray(self.BLOCK_WINDOWS)
            else:
                self.blocks.move_to_end(key)
            value = data[offset]
            if value:
                self.hits += 1
                return value == 1
            value = _passes_complexity(sequence[start:end].upper(), self.policy)
            data[offset] = 1 if value else 2
        else:
            key = source, start, end
            if key in self.short:
                self.hits += 1
                self.short.move_to_end(key)
                return self.short[key]
            value = _passes_complexity(sequence[start:end].upper(), self.policy)
            if len(self.short) >= self.MAX_SHORT:
                self.short.popitem(last=False)
            self.short[key] = value
        self.misses += 1
        return value

    def intervals(self, sequence, source, interval):
        result, run = [], None
        minimum = min(self.policy.kmer_size, len(sequence))
        for start in range(interval.start, interval.end, self.policy.minimum_anchor_bp):
            end = min(interval.end, start + self.policy.minimum_anchor_bp)
            if end - start >= minimum and self.passes(sequence, source, start, end):
                if run is None:
                    run = start
            elif run is not None:
                result.append(Interval(run, start)); run = None
        if run is not None:
            result.append(Interval(run, interval.end))
        return tuple(result)

    def clear(self):
        self.blocks.clear(); self.short.clear()


class _RootedContext:
    """Exact grid: retain cheap whole-anchor summaries, screen sparse long anchors on demand."""
    def __init__(self, sequence_for, masks, policy):
        self.width = 8 * policy.minimum_anchor_bp
        self.cached_spans = self.cached_bytes = 0
        self.complexity = complexity = _ComplexityCache(policy)
        self.sequence_for, self.masks = sequence_for, masks
        self.screened_bp = screened_bp = [0, 0]  # whole, tiled; closures do not retain the context
        # Results are passing runs, not DNA. Bound fragmentation as well as number
        # of anchors; the previous 128-anchor count alone caused avoidable evictions.
        self.whole = OrderedDict()
        def full(source, parent):
            legs = unmasked(source, parent)
            screened_bp[0] += sum(i.length for i in legs)
            return tuple(piece for leg in legs
                         for piece in complexity.intervals(sequence_for(source, parent), source, leg))

        @lru_cache(maxsize=8192)
        def unmasked(source, parent):
            return tuple(_outside_merged_mask(parent, masks.get(source, ())))

        @lru_cache(maxsize=65536)
        def tile(source, parent, start, end):
            screened_bp[1] += end - start
            return complexity.intervals(sequence_for(source, parent), source, Interval(start, end))

        self._full, self._unmasked, self._tile = full, unmasked, tile

    def __call__(self, anchor, targets):
        source, parent = key = anchor.source, anchor.interval
        whole = self.whole.get(key)
        if whole is not None:
            self.whole.move_to_end(key)
            return whole  # Caller clips by each actual CIGAR block, as on the original route.
        if parent.length > 1024**2:
            targets = merged_intervals(targets)
        # Only a long, sparsely contacted parent benefits from localized evaluation.
        # This changes evaluation cost, never the grid or the numerical thresholds.
        if parent.length <= 1024**2 or 8 * sum(i.length for i in targets) >= parent.length:
            whole = _PackedIntervals(self._full(source, parent))
            if whole.nbytes <= 128 * 1024**2:
                while self.whole and (len(self.whole) >= 8192 or self.cached_bytes + whole.nbytes > 128 * 1024**2):
                    previous = self.whole.popitem(last=False)[1]
                    self.cached_spans -= len(previous); self.cached_bytes -= previous.nbytes
                self.whole[key] = whole; self.cached_spans += len(whole); self.cached_bytes += whole.nbytes
            return whole
        legs = self._unmasked(source, parent); pieces = []
        for target in targets:
            for leg in _overlapping_spans(target, legs):
                lo, hi = max(target.start, leg.start), min(target.end, leg.end)
                start = lo - (lo - leg.start) % self.width
                while start < hi:
                    end = min(start + self.width, leg.end)
                    spans = self._tile(source, parent, start, end)
                    pieces.extend(i.intersection(target) for i in _overlapping_spans(target, spans))
                    start = end
        # Join runs across tiles BEFORE projection: splitting a passing interval
        # here would shift the separate candidate-side complexity grid downstream.
        return merged_intervals(pieces)

    def clean(self, source, parent, intervals):
        sequence = self.sequence_for(source, parent)
        return merged_intervals(piece for iv in intervals
                                for unique in _outside_merged_mask(iv, self.masks.get(source, ()))
                                for piece in self.complexity.intervals(sequence, source, unique))

    def clear(self, *, keep_complexity=False):
        self._tile.cache_clear(); self._unmasked.cache_clear(); self.whole.clear()
        self.cached_spans = self.cached_bytes = 0
        if not keep_complexity:
            self.complexity.clear()


def _candidate_delta(part, groups, linked, policy, path_policy, clean, rooted_context):
    """One candidate, fixed round inputs; no shared proposal writes or early tie-breaking."""
    delta = {}; geometry = rooted = candidate = 0.0
    full_bp, tile_bp = rooted_context.screened_bp
    direct_spans = {}  # Immutable source coverage, only for this segment and round.
    for anchor, links in linked:
        for orientation in ("+", "-"):
            group = (anchor.chromosome, orientation)
            direct = groups.get(group, ())
            if groups and not direct:
                continue  # This locus cannot propose a placement, regardless of pair evidence.
            # Geometry probe has explicit raw evidence; it is never returned as admitted.
            stamp = monotonic()
            temporary = _placement(part, anchor.chromosome, orientation, part.interval, (part.interval,), (),
                                   (l.hit.evidence_id for l in links), kind="pairwise")
            qualified = qualify_pair_blocks(temporary, anchor, links, path_policy, require_supported=False)
            geometry += monotonic() - stamp
            if not qualified:
                continue
            # Full accepted contig context can root an off-ref
            # neighbor; known ambiguous/repetitive positions cannot.
            stamp = monotonic()
            context = rooted_context(anchor, (anchor.source_interval(b.right) for b, _ in qualified))
            rooted += monotonic() - stamp
            intervals, ids = [], set()
            for block, evidence_id in qualified:
                # Screen only source intervals that touch this block; keep the original
                # source-coordinate order and orientation-specific projection below.
                target_span = anchor.source_interval(block.right)
                for source_anchor in _overlapping_spans(target_span, context):
                    overlap = block.right.intersection(anchor.local(source_anchor))
                    if overlap is None:
                        continue
                    start = block.left.start + overlap.start - block.right.start
                    intervals.append(temporary.source_interval(Interval(start, start + overlap.length)))
                    ids.add(evidence_id)
            stamp = monotonic()
            intervals = clean(intervals)
            candidate += monotonic() - stamp
            if sum(i.length for i in intervals) < min(policy.minimum_anchor_bp, part.interval.length):
                continue
            item = delta.setdefault(group, {"intervals": [], "ids": set(), "parents": set()})
            if direct:
                # Only the union of intersections is consumed here. Both axes are
                # merged before clipping, so these half-open overlaps are already
                # ordered and disjoint. Keep the original reference anchors in refs.
                if group not in direct_spans:
                    direct_spans[group] = merged_intervals(b.source for b in direct)
                cover = direct_spans[group]
                item["intervals"].extend(a.intersection(b) for a in intervals
                                         for b in _overlapping_spans(a, cover))
            else:
                item["intervals"].extend(intervals)
            item["ids"].update(ids | set(anchor.evidence_ids))
            item["parents"].add(anchor.placement_id)
    for item in delta.values():
        item['intervals'] = merged_intervals(item['intervals'])
    return (delta, geometry, rooted, candidate, rooted_context.screened_bp[0] - full_bp,
            rooted_context.screened_bp[1] - tile_bp)


def validate_admission_occupancy(placements):
    """Reject cross-chromosome collisions by physical source, not segment or strand."""
    by_source = defaultdict(list)
    for p in placements:
        by_source[p.source].append(p)
    for source, rows in by_source.items():
        farthest = {}
        for p in sorted(rows, key=lambda p: p.interval.start):
            for chromosome, prev in farthest.items():
                if chromosome != p.chromosome and prev.interval.end > p.interval.start:
                    raise Q0EvidenceError(f"admission source overlap: {source} "
                                          f"{chromosome} {prev.interval} ({prev.placement_id}) vs "
                                          f"{p.chromosome} {p.interval} ({p.placement_id})")
            prev = farthest.get(p.chromosome)
            if prev is None or prev.interval.end < p.interval.end:
                farthest[p.chromosome] = p


def admit_placements(data: EvidenceInput, *, policy: AdmissionPolicy = AdmissionPolicy(),
                     path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None,
                     screen_threads: int = 1, screen_progress: Callable[[str], None] = _quiet) -> Admission:
    with _PlacementProgress(screen_progress) as phases:
        return _admit_placements(data, policy, path_policy, quality_pass, screen_threads, phases)


def pair_locus_allowed(chromosome, direct_chromosomes, high_intervals, support, minimum):
    """Inherited evidence cannot overturn another rooted locus without local anchors."""
    if not (direct_chromosomes - {chromosome}):
        return True
    return _size(overlap for iv in support for hit in _overlapping_spans(iv, high_intervals)
                 if (overlap := hit.intersection(iv))) >= minimum


def _admit_placements(data, policy, path_policy, quality_pass, screen_threads, phases, *, first_request=False):
    screen_progress = _quiet if phases.log is _quiet else phases.emit
    if quality_pass is not None and (set(quality_pass) != set(data.sources) or any(type(v) is not bool for v in quality_pass.values())):
        raise Q0EvidenceError("q0 QC decisions must explicitly cover every source")
    records, accepted = [], {}
    groups, ambiguous = {}, defaultdict(list)
    allowed = {key for key in data.parts if quality_pass is None or quality_pass[data.parts[key].source]}
    ordered = sorted(data.parts.items())
    screen = _request_reference_screen if first_request else _reference_screen
    if screen_threads > 1:
        from .q0_source_screen import ordered_screens
        screened = ordered_screens(data, ordered, allowed, policy, screen_threads, screen, screen_progress)
    else:
        screened = ((key, part, screen(data, part, policy) if key in allowed else None)
                    for key, part in ordered)
    direct_groups, direct_high = {}, {}
    for key, part, result in screened:
        if key not in allowed:
            if not first_request:
                records.append({"segment_id": key, "status": "rejected", "reason": "failed_reads_qc"})
            continue
        groups[key], high, mask, evidence_ids = result
        # Small screened hits alone do not veto an inherited locus. Require
        # substantial high-MAPQ support on this same source.
        direct_groups[key] = {chrom for (chrom, strand), spans in high.items()
                              if _size(spans) >= policy.continuous.minimum_terminal_foreign_bp} if policy.continuous else set()
        if policy.continuous and direct_groups[key]:
            direct_high[key] = high
        ambiguous[part.source].extend(mask)
        if not first_request:
            records.append({"segment_id": key, "status": "reference_screen",
                            "evidence_ids": evidence_ids,
                            "unique_groups": [{"chromosome": group[0], "orientation": group[1],
                                               "support_bp": _size(a.source for a in anchors)} for group, anchors in sorted(groups[key].items())],
                            "ambiguous_intervals": [asdict(i) for i in mask]})
        reference_seed = None
        if len(groups[key]) == 1 and high and all(_ordered(anchors, group[1]) for group, anchors in groups[key].items()):
            (chromosome, strand), anchors = next(iter(groups[key].items()))
            support = merged_intervals(a.source for a in anchors)
            interval = part.interval if (not policy.continuous or not policy.continuous.is_unplaced(chromosome)) and _size(support) / part.interval.length >= policy.minimum_whole_support_fraction else _hull(support)
            placement = _placement(part, chromosome, strand, interval, support, anchors,
                                   (a.evidence_id for a in anchors), kind="reference")
            accepted[placement.placement_id] = placement
            reference_seed = placement
            if not first_request:
                records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted",
                                "reason": "unique_reference_blocks" if interval == part.interval else "supported_reference_subinterval",
                                "qc": "not_measured" if quality_pass is None else "passed"})
        if reference_seed is None and policy.continuous is not None:
            continuous, audit = continuous_candidates(part, groups[key], high, policy, _placement, policy.continuous)
            if not continuous and any(row.get("status") == "unresolved" for row in audit):
                # Do not relabel this contested part later via weaker pair/gap inheritance.
                allowed.discard(key)
                if not first_request:
                    records.append({"segment_id": key, "status": "unresolved",
                                    "reason": "overlapping_cross_chromosome_chain_hulls"})
            for placement in continuous:
                accepted[placement.placement_id] = placement
                if not first_request:
                    records.append({"placement_id": placement.placement_id, "segment_id": key,
                                    "status": "accepted", "reason": "continuous_collinear_chain",
                                    "qc": "not_measured" if quality_pass is None else "passed"})
            if audit and not first_request:
                records.append({"segment_id": key, "status": "continuous_reference_audit", "regions": list(audit)})
    del screened, ordered
    if first_request and not accepted:
        # Pair propagation, tail splits and original-gap neighbors can inherit
        # a reference root, never create one. initial_generation still rejects
        # a draft with no trustworthy path; this is not a successful empty Q0.
        screen_progress("request admission: no reference seed; skipping pair and adjacency expansion")
        return RequestAdmission(())
    phases.start(f"index pair evidence (links={len(data.pair_links)})")
    ambiguous = {key: merged_intervals(value) for key, value in ambiguous.items()}
    pair_neighbors = _pair_neighbors(data.pair_links)

    rooted_context = _RootedContext(lambda source, _span: data.sources[source], ambiguous, policy)

    def clean_intervals(part, intervals):
        return rooted_context.clean(part.source, part.interval, intervals)

    # Revisit a reference seed when independently ref-anchored sequence on
    # another chr supports a previously unlocalized tail. This is local source
    # selection, not a claim that the input assembler made a biological error.
    reference_seeds = tuple(accepted.values())
    seed_neighbors = _PlacementNeighbors(reference_seeds, pair_neighbors)
    no_tail_room = continuity_stops = continuous_tail_stops = 0
    for current in phases.items("check cross-chromosome seed tails", reference_seeds):
        if current.localization_kind == "continuous_reference":
            # These carriers already passed the scale-aware foreign-chain
            # barriers. A tiny paired repeat must not cut them a second time
            # or downgrade their continuous-reference localization identity.
            continuous_tail_stops += 1
            continue
        part = data.parts[current.segment_id]
        if current.interval != part.interval:
            continue
        main_anchors = merged_intervals(a.source for a in current.reference_blocks)
        main_interval = Interval(main_anchors[0].start, main_anchors[-1].end)
        # To replace this seed, the ordinary selector requires a disjoint
        # alternative hull with at least minimum_anchor_bp of clean support.
        # Interior holes in the main hull cannot qualify; equality still can.
        if first_request and max(main_interval.start - part.interval.start,
                                 part.interval.end - main_interval.end) < policy.minimum_anchor_bp:
            no_tail_room += 1
            continue
        alternatives = defaultdict(lambda: {"intervals": [], "ids": set(), "parents": set()})
        linked_seeds = seed_neighbors.for_source(current.source)
        for anchor, links in linked_seeds:
            if anchor.chromosome == current.chromosome:
                continue
            if policy.continuous and current.chromosome in direct_groups[part.segment_id]:
                # A reference seed with only one direct locus cannot be split
                # onto another chromosome solely by an unanchored pair tail.
                continue
            for orientation in ("+", "-"):
                probe = _placement(part, anchor.chromosome, orientation, part.interval, (part.interval,), (),
                                   (link.hit.evidence_id for link in links), kind="pairwise")
                qualified = qualify_pair_blocks(probe, anchor, links, path_policy, require_supported=False)
                by_evidence = defaultdict(list)
                for block, eid in qualified:
                    # The per-placement index preserves each actual reference block,
                    # including overlapping anchors. Do not merge before complexity screening.
                    for lo, hi, _ in anchor._reference_loci.intersecting(block.right.start, block.right.end):
                        start = block.left.start + lo - block.right.start
                        by_evidence[eid].append(probe.source_interval(Interval(start, start + hi - lo)))
                for eid, intervals in by_evidence.items():
                    # A chain also matching the known chr locus is a repeated
                    # sequence relationship, not evidence for moving its tail.
                    if _size(overlap for a in intervals for b in _overlapping_spans(a, main_anchors)
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
                left_support = _size(overlap for a in intervals for b in _overlapping_spans(a, main_anchors) if (overlap := a.intersection(b)))
                right_support = _size(overlap for a in intervals for value in alternatives.values()
                                      for b in value["intervals"] if (overlap := a.intersection(b)))
                if min(left_support, right_support) >= policy.minimum_anchor_bp:
                    continuity_ids.add(eid)
                    if first_request:
                        break
            if first_request and continuity_ids:
                continuity_stops += 1
                break  # keep the seed; extra same-decision witnesses only populate the full report
        if continuity_ids:
            if not first_request:
                records.append({"placement_id": current.placement_id, "status": "retained",
                                "reason": "cross_chr_tail_continuity_supported", "evidence_ids": sorted(continuity_ids),
                                "competing_evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
            continue
        bounds = [_hull(value["intervals"]) for value in alternatives.values()]
        if any(main_interval.intersection(i) for i in bounds) or any(a.intersection(b) for n, a in enumerate(bounds) for b in bounds[n+1:]):
            if not first_request:
                records.append({"placement_id": current.placement_id, "status": "unresolved",
                                "reason": "overlapping_structural_selection_bounds",
                                "evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
            continue
        accepted.pop(current.placement_id)
        if not first_request:
            records.append({"placement_id": current.placement_id, "placement": asdict(current), "status": "superseded",
                            "reason": "independently_anchored_cross_chr_tail"})
        main = _placement(part, current.chromosome, current.orientation, main_interval, main_anchors,
                          current.reference_blocks, current.evidence_ids, kind="reference")
        accepted[main.placement_id] = main
        if not first_request:
            records.append({"placement_id": main.placement_id, "segment_id": part.segment_id, "status": "accepted",
                            "reason": "supported_local_interval", "replaces_placement_id": current.placement_id})
        for (chromosome, strand), value in sorted(alternatives.items()):
            interval = _hull(value["intervals"])
            local = _placement(part, chromosome, strand, interval, value["intervals"], (), value["ids"], kind="pairwise")
            accepted[local.placement_id] = local
            if not first_request:
                records.append({"placement_id": local.placement_id, "segment_id": part.segment_id, "status": "accepted",
                                "reason": "independently_anchored_cross_chr_tail", "anchor_placement_ids": sorted(value["parents"])})

    screen_progress(f"continuous reference tail decisions: protected_carriers={continuous_tail_stops}")
    if first_request:
        screen_progress(f"request tail decisions: no_disjoint_tail_room={no_tail_room} first_continuity_witness={continuity_stops}")

    # Anchors are immutable until the extension phase below. Accumulate each
    # candidate/anchor contribution exactly once, but resolve at the original round
    # boundary (never let encounter order choose between competing loci).
    old_neighbors = Counter()
    frontier = tuple(accepted.values())
    unplaced = allowed - {p.segment_id for p in frontier}
    proposed = defaultdict(dict)
    for round_number in range(1, len(data.parts) + 1):
        placed_neighbors = _PlacementNeighbors(frontier, pair_neighbors)
        neighbors = {s for anchor_source in placed_neighbors.by_source for s in pair_neighbors.get(anchor_source, ())}
        candidates = sorted(key for key in unplaced if data.parts[key].source in neighbors)
        screen_progress(f"placement pair round={round_number}: new_anchors={len(frontier)} "
                        f"unplaced={len(unplaced)} with_new_neighbors={len(candidates)}")
        from .q0_pair_lanes import ordered_deltas
        def owner(key, linked):
            part = data.parts[key]
            return _candidate_delta(part, groups.get(key, {}), linked, policy, path_policy,
                                    lambda spans: clean_intervals(part, spans),
                                    rooted_context)

        prior = sum(old_neighbors.get(data.parts[k].source, 0) for k in unplaced)
        for src, anchors in placed_neighbors.by_source.items():
            for other in pair_neighbors.get(src, ()):
                old_neighbors[other] += len(anchors)
        screen_progress(f"placement pair round={round_number}: old_relations_not_recomputed={prior}")
        phases.start(f"anchor unplaced segments round={round_number}", len(candidates))
        deltas = ordered_deltas(candidates, data, groups, ambiguous, placed_neighbors, policy,
                                path_policy, screen_threads, owner, screen_progress, round_number,
                                time_phases=screen_progress is not _quiet)
        for n, (key, delta) in enumerate(deltas, 1):
            for group, row in delta.items():
                item = proposed[key].get(group)
                if item is None:
                    row['refs'] = groups.get(key, {}).get(group, ())
                    proposed[key][group] = row
                else:
                    item['intervals'] = merged_intervals((*item['intervals'], *row['intervals']))
                    item['ids'].update(row['ids']); item['parents'].update(row['parents'])
            phases.completed(n)
        next_frontier = []
        for key, alternatives in phases.items(f"resolve pair proposals round={round_number}", sorted(proposed.items())):
            part = data.parts[key]
            # Only the union is consumed. Keep below-threshold contributions too:
            # a later anchor can make their union pass. Keep every ID and parent.
            alternatives = {group: value for group, value in alternatives.items()
                            if sum(i.length for i in value["intervals"]) >= min(policy.minimum_anchor_bp, part.interval.length)}
            bounds = {group: _hull(a.source for a in value["refs"]) if value["refs"] else _hull(value["intervals"])
                      for group, value in alternatives.items()}
            if any(bounds[a].intersection(bounds[b]) for i, a in enumerate(bounds) for b in list(bounds)[i+1:]):
                if not first_request:
                    records.append({"segment_id": key, "status": "unresolved", "reason": "competing_pairwise_loci", "round": round_number,
                                    "evidence_ids": sorted({eid for value in alternatives.values() for eid in value["ids"]})})
                continue
            for (chromosome, strand), value in sorted(alternatives.items()):
                support = value["intervals"]
                partial = ((policy.continuous and policy.continuous.is_unplaced(chromosome)) or len(groups.get(key, {})) > 1 or len(alternatives) > 1 or
                           sum(i.length for i in support) / part.interval.length < policy.minimum_whole_support_fraction)
                interval = bounds[(chromosome, strand)] if partial else part.interval
                refs = []
                for a in value["refs"]:
                    overlap = a.source.intersection(interval)
                    if overlap:
                        refs.append(ReferenceAnchor(overlap, _project(a.source, a.reference, strand, overlap), a.evidence_id))
                if policy.continuous and not pair_locus_allowed(
                        chromosome, direct_groups[key], direct_high.get(key, {}).get((chromosome, strand), ()),
                        support, min(policy.minimum_anchor_bp, interval.length)):
                    if not first_request:
                        records.append({"segment_id": key, "status": "unresolved", "chromosome": chromosome,
                                        "reason": "pair_only_conflicts_with_direct_reference"})
                    continue
                if policy.continuous and policy.continuous.is_unplaced(chromosome) and refs:
                    interval = _hull(a.source for a in refs)
                    support = tuple(ov for iv in support if (ov := iv.intersection(interval)))
                if not _ordered(refs, strand):
                    if not first_request:
                        records.append({"segment_id": key, "status": "unresolved", "reason": "noncollinear_reference_anchors",
                                        "evidence_ids": sorted(value["ids"])})
                    continue
                placement = _placement(part, chromosome, strand, interval, merged_intervals((*support, *(a.source for a in refs))), refs,
                                       value["ids"] | {a.evidence_id for a in refs}, kind="pairwise")
                accepted[placement.placement_id] = placement
                if not first_request:
                    records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted",
                                    "reason": "supported_local_interval" if partial else "pairwise_reference_anchoring",
                                    "anchor_placement_ids": sorted(value["parents"]), "round": round_number,
                                    "qc": "not_measured" if quality_pass is None else "passed"})
                next_frontier.append(placement)
                unplaced.discard(key)
            if key not in unplaced:
                # An accepted placement never needs a second competition. It can
                # still be the evidence that localizes a different, unplaced part.
                del proposed[key]
        if not next_frontier:
            break
        frontier = next_frontier

    proposed.clear()
    # Extension has its OWN interval-origin grids. Reuse only exact same
    # 100bp windows/short tails, never clip a different grid's whole result.
    rooted_context.clear(keep_complexity=True)

    # Extend supported anchors into non-ref sequence only with a noncompeting,
    # high-complexity pair match between already localized sources. Direct ref
    # blocks check actual corresponding loci, not reference hull intersection.
    additions = defaultdict(list)
    addition_ids = defaultdict(set)
    placed_list = sorted(accepted.values(), key=lambda p: p.placement_id)
    placed_neighbors = _PlacementNeighbors(placed_list, pair_neighbors)
    for i, left in enumerate(phases.items("extend localized anchors", placed_list)):
        for right, links in placed_neighbors.for_source(left.source, after=i):
            if left.chromosome != right.chromosome:
                continue
            for block, evidence_id in qualify_pair_blocks(left, right, links, path_policy, require_supported=False):
                for placement, interval in ((left, left.source_interval(block.left)), (right, right.source_interval(block.right))):
                    part = data.parts[placement.segment_id]
                    clean = clean_intervals(part, (interval,))
                    additions[placement.placement_id].extend(clean)
                    addition_ids[placement.placement_id].add(evidence_id)
    for key, intervals in phases.items("merge anchor extensions", additions.items()):
        p = accepted[key]
        accepted[key] = replace(p, anchor_intervals=merged_intervals((*p.anchor_intervals, *intervals)),
                                evidence_ids=tuple(sorted(set(p.evidence_ids) | addition_ids[key])))
        if not first_request:
            records.append({"placement_id": key, "status": "anchor_extension", "reason": "localized_pairwise_sequence_context",
                            "evidence_ids": sorted(addition_ids[key])})

    # Original assembly N adjacency is a soft relation, not a new independent
    # sequence anchor. Unaligned neighbors can only survive attached to a seed.
    for round_number in range(1, len(data.parts) + 1):
        phases.start(f"resolve input adjacency round={round_number}")
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
                if not first_request:
                    records.append({"segment_id": key, "status": "unresolved", "reason": "input_adjacency_conflict"})
                continue
            chromosome, strand = next(iter(identities))
            part = data.parts[key]
            ids = {edge.adjacency_id for _, edge in contexts} | {eid for p, _ in contexts for eid in p.evidence_ids}
            placement = _placement(part, chromosome, strand, part.interval, (), (), ids, kind="input_adjacency", seed=False)
            accepted[placement.placement_id] = placement
            if not first_request:
                records.append({"placement_id": placement.placement_id, "segment_id": key, "status": "accepted_soft_neighbor",
                                "reason": "input_assembly_adjacency", "anchor_placement_ids": sorted(p.placement_id for p, _ in contexts)})
            added += 1
        if not added:
            break
    placements = tuple(sorted(accepted.values(), key=lambda p: p.placement_id))
    validate_admission_occupancy(placements)
    if first_request:
        return RequestAdmission(placements)
    placed = {p.segment_id for p in placements}
    for key in phases.items("record unresolved segments", sorted(allowed - placed)):
        records.append({"segment_id": key, "status": "unresolved",
                        "reason": ("structural_ref_conflict" if len(groups.get(key, {})) > 1 else
                                   "noncollinear_reference_anchors" if any(not _ordered(a, g[1]) for g, a in groups.get(key, {}).items()) else
                                   "no_sufficient_localization_evidence")})
    return Admission(placements, records,
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
                    path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None,
                    progress: Callable[[str], None] = _quiet, screen_threads: int = 1, review=None) -> PathSelection:
    """Select and check source geometry without reconstructing sequences or building a report."""
    return _select_paths(data, admission_policy, path_policy, quality_pass, progress, screen_threads, first_request=False, review=review)


def select_request_paths(data: EvidenceInput, *, progress: Callable[[str], None] = _quiet,
                         screen_threads: int = 1, checkpoint=None, review=None) -> FirstRequestSelection:
    """Initial threshold routing only; never publish this selection as ordinary Q0."""
    return _select_paths(data, AdmissionPolicy(), PathPolicy(), None, progress, screen_threads, first_request=True, checkpoint=checkpoint, review=review)


def _select_paths(data, admission_policy, path_policy, quality_pass, progress, screen_threads, *, first_request, checkpoint=None, review=None):
    if checkpoint is not None and review is not None:
        raise Q0EvidenceError("winner-only checkpoints cannot restore junction review evidence")
    progress(f"placing candidate segments · pair links={len(data.pair_links)}")
    if first_request:
        admission = checkpoint.load_admission() if checkpoint is not None else None
        if admission is None:
            with _PlacementProgress(progress) as phases:
                admission = _admit_placements(data, admission_policy, path_policy, quality_pass, screen_threads,
                                              phases, first_request=True)
            if checkpoint is not None:
                checkpoint.save_admission(admission)
        else:
            validate_admission_occupancy(admission.placements)
        if checkpoint is not None:
            checkpoint.after_admission()
    else:
        admission = admit_placements(data, policy=admission_policy, path_policy=path_policy, quality_pass=quality_pass,
                                     screen_threads=screen_threads, screen_progress=progress)
    groups = defaultdict(list)
    for placement in admission.placements:
        groups[placement.chromosome].append(placement)
    searches, occupied = {}, defaultdict(list)
    progress(f"building chromosome paths · placements={len(admission.placements)}")
    index_started = monotonic()
    if first_request:
        # Admission is already global and complete. Pairwise or adjacency-only
        # neighbors cannot start a path. Keep them all in any group WITH a seed.
        seeded = {p.chromosome for p in admission.placements if p.seed_eligible}
        graph_links = (_links_for_path_graphs((p for p in admission.placements if p.chromosome in seeded), data.pair_links)
                       if seeded else {})
    else:
        graph_links = _links_for_path_graphs(admission.placements, data.pair_links)
    progress(f"chromosome path link index ready: index_s={monotonic()-index_started:.2f}")
    for index, chromosome in enumerate(sorted(data.reference_lengths), 1):
        progress(f"chromosome path {index}/{len(data.reference_lengths)}: {chromosome} started_at={strftime('%Y-%m-%dT%H:%M:%S%z')}")
        search = checkpoint.load_group(index, chromosome) if checkpoint is not None else None
        restored = search is not None
        if not restored:
            if first_request and chromosome not in seeded:
                search = RequestPathResult(None)
                progress(f"chromosome {chromosome}: no admitted seed; request graph not built")
            else:
                started = monotonic()
                report = None if progress is _quiet else lambda message: progress(f"chromosome {chromosome} {message}")
                graph = PathGraph(groups[chromosome], graph_links.get(chromosome, ()), data.original_adjacencies, path_policy,
                                  progress=report, first_request=first_request)
                progress(f"chromosome {chromosome} graph ready: placements={len(graph.placements)} "
                         f"coverage_atoms={len(graph.coverage.atoms)} graph_s={monotonic()-started:.2f}")
                search = search_request_path(graph, progress=report) if first_request else search_paths(graph, progress=report)
                if review is not None:
                    # The result owns the pruning log of the original search. Extra
                    # edge lookups for routing must not alter that diagnostic.
                    graph.edge_pruning = []
                    review.observe(graph, search.path)
                del graph  # do not keep the previous chromosome graph while building the next
        searches[chromosome] = search
        if search.path is None:
            if checkpoint is not None and not restored:
                checkpoint.save_group(index, chromosome, search)
            continue
        _occupy_path(data, search, occupied)
        if checkpoint is not None and not restored:
            checkpoint.save_group(index, chromosome, search)  # only after canonical occupancy checks
    return FirstRequestSelection(admission, searches) if first_request else PathSelection(admission, searches, _intervals_only(occupied))


def _occupy_path(data, search, occupied):
    """The same linear source-occupancy check for fresh and restored paths."""
    if search.path is None:
        return
    def claim(source, interval, reason):
        rows = occupied.setdefault(source, [])
        for previous, chromosome in rows:
            overlap = interval.intersection(previous)
            if overlap:
                raise Q0EvidenceError(f"{reason}: source={source} {chromosome} {previous} vs "
                                      f"{search.path.chromosome} {interval}; overlap={overlap}")
        rows.append((interval, search.path.chromosome))

    for item in search.path.slices:
        if item.interval.end > len(data.sources[item.source]):
            raise Q0EvidenceError("q0 path source exceeds sequence length")
        claim(item.source, item.interval, "q0 source interval selected on multiple chromosomes or slices")
    for join in search.path.joins:
        if join.kind == "input_assembly_gap":
            claim(join.gap_source, join.gap_interval, "original N source interval selected more than once")


def _intervals_only(occupied):
    return defaultdict(list, {src: [iv for iv, _ in rows] for src, rows in occupied.items()})


def construct_q0(data: EvidenceInput, *, admission_policy: AdmissionPolicy = AdmissionPolicy(),
                 path_policy: PathPolicy = PathPolicy(), quality_pass: Mapping[SourceKey, bool] | None = None,
                 progress: Callable[[str], None] = _quiet, screen_threads: int = 1, _accepted=None) -> Construction:
    if _accepted is None:
        selection = select_q0_paths(data, admission_policy=admission_policy, path_policy=path_policy,
                                    quality_pass=quality_pass, progress=progress, screen_threads=screen_threads)
    else:
        from .q0_selection_cache import VerifiedSelection
        if type(_accepted) is not VerifiedSelection:
            raise Q0EvidenceError('formal Q0 reuse requires a verified accepted selection')
        selection = _accepted.for_data(data, admission_policy, path_policy, quality_pass)
        progress('reusing accepted Q0 selection; placement/graph/ranking skipped')
    admission, searches, occupied = selection.admission, selection.paths, selection.occupied
    if not any(search.path is not None for search in searches.values()):
        raise Q0EvidenceError("no chromosome has a trustworthy q0 path")
    report = data.catalog.get("supplement_scope")
    threshold = data.threshold_scope is not None or (isinstance(report, dict) and report.get("requested") == "positive_threshold")
    if threshold:
        from .q0_threshold_acceptance import audit
        threshold_counts = audit(data, selection, admission_policy=admission_policy, path_policy=path_policy, quality_pass=quality_pass)
    elif "supplement_scope" in data.catalog:
        from .q0_frontier_scope import audit_selected_scope
        audit_selected_scope(data, admission, searches)
    progress("reconstructing Q0 sequences and recording decisions")
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
    if threshold:
        decisions["supplement_acceptance"] = {"semantics": report["acceptance"], "search_mode": report["effective"],
                                            "alternatives_exhaustive": False, "decision_counts": threshold_counts}
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
    if any(key not in data.evidence for key in used_ids):
        raise Q0EvidenceError("q0 construction references missing evidence records")
    decisions["evidence"] = {key: data.evidence[key] for key in sorted(used_ids)}
    return Construction(records, searches, admission, decisions)


def selector_identity() -> str:
    root = Path(__file__).parent
    return stable_id("q0-selector", [(name, sha256_file(root / name)) for name in
                                    ("q0_admission.py", "q0_reference_competition.py", "q0_source_screen.py", "q0_pair_lanes.py", "q0_pair_transport.py", "q0_paths.py", "q0_coverage.py", "q0_collinear.py", "q0_interval_index.py", "q0_reference_locus.py", "q0_backbone.py", "q0_threshold_questions.py", "q0_junction_review.py", "q0_sources.py", "q0_alignments.py", "q0_paf_io.py", "q0_selection_cache.py", "q0_frontier_scope.py", "common.py")])


def build_q0(root: Path, *, progress: Callable[[str], None] = _quiet, screen_threads: int = 1, **kwargs) -> Construction:
    before = selector_identity()
    progress("loading Q0 alignment evidence")
    data = load_evidence_input(root)
    from .q0_retained_hits import EvidenceRows
    # The bounded worker packets support retained hits. The legacy full loader uses
    # unpacked alignments; do not set up pools whose packets would all fall back.
    budget = screen_threads if isinstance(data.evidence, EvidenceRows) else 1
    progress(f"Q0 placement thread budget={budget}")
    from .q0_selection_cache import load as load_selection
    accepted = load_selection(root, data.verified_manifest, data) if data.verified_manifest is not None else None
    result = construct_q0(data, progress=progress, screen_threads=budget, _accepted=accepted, **kwargs)
    if stable_id("q0-ready-evidence", load_verified_evidence(root)) != data.ready_manifest_identity:
        raise Q0EvidenceError("q0 evidence changed while selecting paths")
    if selector_identity() != before:
        raise Q0EvidenceError("q0 selector changed while building paths")
    return result
