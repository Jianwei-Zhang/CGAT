"""Bounded, reversible q0 path search over evidence-admitted source intervals.

This is the path kernel, not a substitute for placement qualification. Callers
must supply uniquely localized placements and their actually supported anchor
intervals. The production evidence adapter owns that admission decision. The
kernel never treats reference containment as sequence redundancy, never creates
consensus bases, and never treats an N count as a measured physical distance.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import product
from typing import Iterable, Mapping

from .common import reverse_complement, stable_id
from .q0_alignments import PafAlignment
from .q0_coverage import CoverageModel, Equivalence
from .q0_sources import Interval, OriginalAdjacency, Q0EvidenceError, SourceKey, merged_intervals


@dataclass(frozen=True)
class PathPolicy:
    version: int = 2
    minimum_pair_identity: float = 0.95
    minimum_anchor_bp: int = 100
    unknown_join_n: int = 100
    beam_width: int = 8
    maximum_evaluations: int = 20000
    maximum_rounds: int = 32
    maximum_replaced_nodes: int = 3
    maximum_edge_variants: int = 4
    maximum_seed_positions: int = 8
    maximum_coverage_boundaries: int = 200000

    def __post_init__(self):
        if not 0 < self.minimum_pair_identity <= 1:
            raise Q0EvidenceError("q0 pair identity must be in (0, 1]")
        for name in ("version", "minimum_anchor_bp", "unknown_join_n", "beam_width",
                     "maximum_evaluations", "maximum_rounds", "maximum_replaced_nodes", "maximum_edge_variants", "maximum_seed_positions", "maximum_coverage_boundaries"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise Q0EvidenceError(f"q0 path policy requires positive integer {name}")


@dataclass(frozen=True)
class ReferenceAnchor:
    source: Interval
    reference: Interval
    evidence_id: str

    def __post_init__(self):
        if self.source.length != self.reference.length or not self.evidence_id:
            raise Q0EvidenceError("reference anchor must be an actual equal-length paired block")


@dataclass(frozen=True)
class Placement:
    placement_id: str
    segment_id: str
    source: SourceKey
    interval: Interval
    orientation: str
    chromosome: str
    reference_intervals: tuple[Interval, ...]
    anchor_intervals: tuple[Interval, ...]
    evidence_ids: tuple[str, ...]
    reference_blocks: tuple[ReferenceAnchor, ...] = ()
    seed_eligible: bool = True
    localization_kind: str = "reference"

    def __post_init__(self):
        if not self.placement_id or not self.segment_id or not self.chromosome or self.orientation not in {"+", "-"}:
            raise Q0EvidenceError("invalid q0 placement identity/orientation")
        if not self.evidence_ids or (self.seed_eligible and not self.anchor_intervals):
            raise Q0EvidenceError("q0 placement needs localization evidence and supported source anchors")
        if not self.seed_eligible and self.localization_kind != "input_adjacency":
            raise Q0EvidenceError("only original-adjacency placements may lack independent anchors")
        if merged_intervals(self.reference_intervals) != merged_intervals(a.reference for a in self.reference_blocks):
            raise Q0EvidenceError("reference footprint must come from actual paired blocks")
        if any(not self.interval.contains(a.source) for a in self.reference_blocks):
            raise Q0EvidenceError("reference block escapes q0 placement")
        if any(not self.interval.contains(interval) for interval in self.anchor_intervals):
            raise Q0EvidenceError("q0 anchor escapes source placement")

    def local(self, interval: Interval) -> Interval:
        if not self.interval.contains(interval):
            raise Q0EvidenceError("q0 source interval escapes placement")
        if self.orientation == "+":
            return Interval(interval.start - self.interval.start, interval.end - self.interval.start)
        return Interval(self.interval.end - interval.end, self.interval.end - interval.start)

    def source_interval(self, local: Interval) -> Interval:
        if local.end > self.interval.length:
            raise Q0EvidenceError("q0 local interval escapes placement")
        if self.orientation == "+":
            return Interval(self.interval.start + local.start, self.interval.start + local.end)
        return Interval(self.interval.end - local.end, self.interval.end - local.start)


@dataclass(frozen=True)
class PairLink:
    """A real PAF, including offsets when its FASTAs contain source fragments."""
    hit: PafAlignment
    query_source: SourceKey
    target_source: SourceKey
    query_offset: int = 0
    target_offset: int = 0

    def __post_init__(self):
        if min(self.query_offset, self.target_offset) < 0:
            raise Q0EvidenceError("negative q0 PAF fragment offset")

    def source_blocks(self):
        for block in self.hit.aligned_blocks():
            if block.operation == "X":
                continue
            yield (Interval(block.query.start + self.query_offset, block.query.end + self.query_offset),
                   Interval(block.target.start + self.target_offset, block.target.end + self.target_offset))


@dataclass(frozen=True, order=True)
class Block:
    """Corresponding intervals in the two oriented placement coordinate systems."""
    left: Interval
    right: Interval

    def clip_left(self, interval: Interval) -> Block | None:
        overlap = self.left.intersection(interval)
        if overlap is None:
            return None
        return Block(overlap, Interval(self.right.start + overlap.start - self.left.start,
                                      self.right.start + overlap.end - self.left.start))


def pair_blocks(link: PairLink, left: Placement, right: Placement) -> tuple[Block, ...]:
    if (link.hit.strand == "+") != (left.orientation == right.orientation):
        return ()
    swaps = []
    if (link.query_source, link.target_source) == (left.source, right.source):
        swaps.append(False)
    if (link.target_source, link.query_source) == (left.source, right.source):
        swaps.append(True)
    result = set()
    for query, target in link.source_blocks():
        for swap in swaps:
            a, b = (target, query) if swap else (query, target)
            overlap = a.intersection(left.interval)
            if overlap is None:
                continue
            mapped = (Interval(b.start + overlap.start - a.start, b.start + overlap.end - a.start)
                      if link.hit.strand == "+" else
                      Interval(b.end - (overlap.end - a.start), b.end - (overlap.start - a.start)))
            clipped = mapped.intersection(right.interval)
            if clipped is None:
                continue
            back = (Interval(overlap.start + clipped.start - mapped.start, overlap.start + clipped.end - mapped.start)
                    if link.hit.strand == "+" else
                    Interval(overlap.end - (clipped.end - mapped.start), overlap.end - (clipped.start - mapped.start)))
            result.add(Block(left.local(back), right.local(clipped)))
    return tuple(sorted(result))


def reference_consistent(block: Block, left: Placement, right: Placement) -> bool:
    """Compare corresponding paired bases, never reference bounding hulls."""
    for a in left.reference_blocks:
        local_a = left.local(a.source)
        clipped = block.clip_left(local_a)
        if clipped is None:
            continue
        for b in right.reference_blocks:
            local_b = right.local(b.source)
            overlap = clipped.right.intersection(local_b)
            if overlap is None:
                continue
            left_position = clipped.left.start + overlap.start - clipped.right.start
            if a.reference.start + left_position - local_a.start != b.reference.start + overlap.start - local_b.start:
                return False
    return True


def _source_pairs(link: PairLink, left: SourceKey, right: SourceKey):
    for q, t in link.source_blocks():
        if (link.query_source, link.target_source) == (left, right):
            yield q, t
        if (link.target_source, link.query_source) == (left, right):
            yield t, q


def qualify_pair_blocks(left: Placement, right: Placement, links: Iterable[PairLink], policy: PathPolicy,
                        *, require_supported: bool = True) -> tuple[tuple[Block, str], ...]:
    """Retain coordinate-unique blocks; all observed loci compete, even outside
    the proposed fragments, with opposite orientation, or inconsistent with ref.
    require_supported=False only proposes anchors to the admission layer; it is
    not an authorization to edit or to bypass that layer's sequence checks.
    """
    links = tuple(link for link in links if link.hit.matches / link.hit.block_length >= policy.minimum_pair_identity)
    result = []
    for link in links:
        blocks = pair_blocks(link, left, right)
        if not blocks or any(not reference_consistent(block, left, right) for block in blocks):
            continue
        supported = []
        for block in blocks:
            if not require_supported:
                supported.append(block.left)
                continue
            for a in left.anchor_intervals:
                clipped = block.clip_left(left.local(a))
                if clipped:
                    for b in right.anchor_intervals:
                        overlap = clipped.right.intersection(right.local(b))
                        if overlap:
                            start = clipped.left.start + overlap.start - clipped.right.start
                            supported.append(Interval(start, start + overlap.length))
        if _size(supported) < policy.minimum_anchor_bp:
            continue
        for block in blocks:
            left_global, right_global = left.source_interval(block.left), right.source_interval(block.right)
            reverse = left.orientation != right.orientation
            conflicts = False
            for alternative in links:
                for a, b in _source_pairs(alternative, left.source, right.source):
                    qa, qb = left_global.intersection(a), right_global.intersection(b)
                    if max(qa.length if qa else 0, qb.length if qb else 0) < policy.minimum_anchor_bp:
                        continue
                    opposite = (alternative.hit.strand == "-") != reverse
                    # For matching orientations, a single boundary identifies
                    # the affine paired-base map over each ungapped run.
                    same_map = (right_global.end + left_global.start == b.end + a.start if reverse else
                                right_global.start - left_global.start == b.start - a.start)
                    if opposite or not same_map:
                        conflicts = True
                        break
                if conflicts:
                    break
            if not conflicts:
                result.append((block, link.hit.evidence_id))
    return tuple(sorted(set(result), key=lambda item: (item[0], item[1])))


@dataclass(frozen=True)
class Join:
    join_id: str
    left_id: str
    right_id: str
    kind: str
    left_end: int
    right_start: int
    n_bp: int
    evidence_ids: tuple[str, ...]
    original_adjacency_id: str | None = None
    gap_source: SourceKey | None = None
    gap_interval: Interval | None = None


@dataclass(frozen=True)
class Slice:
    placement_id: str
    source: SourceKey
    interval: Interval
    orientation: str


@dataclass(frozen=True)
class Path:
    chromosome: str
    nodes: tuple[str, ...]
    joins: tuple[Join, ...]
    slices: tuple[Slice, ...]
    score: tuple[int, ...]
    missing: tuple[tuple[SourceKey, tuple[Interval, ...]], ...]

    @property
    def path_id(self):
        return stable_id("q0-path", [self.chromosome, list(self.nodes), [join.join_id for join in self.joins]])


@dataclass
class SearchResult:
    path: Path | None
    alternatives: tuple[Path, ...]
    decisions: list[dict]
    diagnostics: dict

    def record(self) -> dict:
        return {"schema": "lgz_q0_path_search_v1", "path": asdict(self.path) if self.path else None,
                "alternatives": [asdict(path) for path in self.alternatives],
                "decisions": self.decisions, "diagnostics": self.diagnostics}


def _size(intervals: Iterable[Interval]) -> int:
    return sum(interval.length for interval in merged_intervals(intervals))


def _overlap_size(left: Iterable[Interval], right: Iterable[Interval]) -> int:
    return _size(overlap for a in left for b in right if (overlap := a.intersection(b)) is not None)


class PathGraph:
    """Immutable evidence facts; no ds-order ranking or whole-source exclusion."""
    def __init__(self, placements: Iterable[Placement], links: Iterable[PairLink],
                 original_adjacencies: Iterable[OriginalAdjacency] = (), policy: PathPolicy = PathPolicy()):
        placements = tuple(placements)
        self.placements = {p.placement_id: p for p in placements}
        if len(self.placements) != len(placements):
            raise Q0EvidenceError("duplicate q0 placement ID")
        chromosomes = {p.chromosome for p in placements}
        if len(chromosomes) > 1:
            raise Q0EvidenceError("one q0 path graph must belong to one chromosome")
        self.chromosome = next(iter(chromosomes), "")
        self.policy = policy
        self.links = defaultdict(list)
        for link in links:
            if link.hit.matches / link.hit.block_length >= policy.minimum_pair_identity:
                self.links[tuple(sorted((link.query_source, link.target_source)))].append(link)
        self.original = tuple(original_adjacencies)
        self.required = defaultdict(list)
        for p in placements:
            self.required[p.source].append(p.interval)
        self.required = {key: merged_intervals(value) for key, value in self.required.items()}
        self._blocks = {}
        self._joins = {}
        self.edge_pruning = []
        self.ambiguous_equivalence_ids = set()
        relations = []
        by_source = defaultdict(list)
        for p in placements:
            by_source[p.source].append(p)
        for (a, b), links_for_pair in list(self.links.items()):
            if a == b:
                continue  # Distinct loci in one source are not redundant copies.
            for left in by_source[a]:
                for right in by_source[b]:
                    for block, evidence_id in self.homologous_blocks(left, right):
                        relations.append(Equivalence(left.source, left.source_interval(block.left),
                                                     right.source, right.source_interval(block.right),
                                                     left.orientation != right.orientation, evidence_id))
        self.coverage = CoverageModel(self.required, relations, maximum_boundaries=policy.maximum_coverage_boundaries)
        if self.coverage.ambiguous_evidence_ids:
            self.ambiguous_equivalence_ids.update(self.coverage.ambiguous_evidence_ids)
            self._blocks.clear()
            self.coverage = CoverageModel(self.required, [r for r in relations if r.evidence_id not in self.ambiguous_equivalence_ids],
                                          maximum_boundaries=policy.maximum_coverage_boundaries)

    def homologous_blocks(self, left: Placement, right: Placement) -> tuple[tuple[Block, str], ...]:
        key = (left.placement_id, right.placement_id)
        if key not in self._blocks:
            links = [link for link in self.links[tuple(sorted((left.source, right.source)))]
                     if link.hit.evidence_id not in self.ambiguous_equivalence_ids]
            self._blocks[key] = qualify_pair_blocks(left, right, links, self.policy)
        return self._blocks[key]

    def joins(self, left_id: str, right_id: str) -> tuple[Join, ...]:
        key = (left_id, right_id)
        if key in self._joins:
            return self._joins[key]
        left, right = self.placements[left_id], self.placements[right_id]
        result = []
        if left_id == right_id or (left.source == right.source and left.interval.intersection(right.interval)):
            self._joins[key] = ()
            return ()
        # Only supported paired-base coordinates can authorize an overlap cut.
        blocks = self.homologous_blocks(left, right)
        if blocks:
            for block, evidence_id in blocks:
                # One actual chain must reach both ends. Its interior indels
                # are allowed; the chosen cut itself must be inside a supported
                # paired run, never projected across an ambiguous indel boundary.
                chain = [b for b, eid in blocks if eid == evidence_id]
                if max(b.left.end for b in chain) != left.interval.length or min(b.right.start for b in chain) != 0:
                    continue
                anchors_left = tuple(left.local(i) for i in left.anchor_intervals)
                anchors_right = tuple(right.local(i) for i in right.anchor_intervals)
                supported = []
                for a in anchors_left:
                    clipped = block.clip_left(a)
                    if clipped is None:
                        continue
                    for b in anchors_right:
                        overlap = clipped.right.intersection(b)
                        if overlap is not None:
                            start = clipped.left.start + overlap.start - clipped.right.start
                            supported.append(Interval(start, start + overlap.length))
                supported = merged_intervals(supported)
                if _size(supported) < self.policy.minimum_anchor_bp:
                    continue
                anchor = max(supported, key=lambda i: (i.length, -i.start))
                if anchor.length < self.policy.minimum_anchor_bp:
                    continue
                cut = anchor.start + anchor.length // 2
                right_cut = block.right.start + cut - block.left.start
                if not 0 < cut <= left.interval.length or not 0 <= right_cut < right.interval.length:
                    continue
                result.append(self._join(left, right, "sequence_overlap", cut, right_cut, 0, (evidence_id,)))
        for edge in self.original:
            forward = (left.segment_id, right.segment_id) == (edge.left_segment_id, edge.right_segment_id)
            reverse = (left.segment_id, right.segment_id) == (edge.right_segment_id, edge.left_segment_id)
            if (left.source != edge.source or right.source != edge.source
                    or left.orientation != right.orientation
                    or not ((forward and left.orientation == "+") or (reverse and left.orientation == "-"))):
                continue
            # Check the actual source boundaries, not just the segment names.
            lo, hi = (left, right) if forward else (right, left)
            if lo.interval.end != edge.gap_interval.start or hi.interval.start != edge.gap_interval.end:
                continue
            if left.reference_intervals and right.reference_intervals and not self.reference_order(left, right):
                continue
            result.append(self._join(left, right, "input_assembly_gap", left.interval.length, 0,
                                     edge.gap_interval.length, (edge.adjacency_id,), edge))
        if self.reference_order(left, right):
            result.append(self._join(left, right, "reference_unknown", left.interval.length, 0,
                                     self.policy.unknown_join_n, tuple(sorted(set(left.evidence_ids + right.evidence_ids)))))
        # Collapse identical cuts supported by duplicated/reciprocal PAFs.
        unique = {}
        for join in result:
            geometry = (join.kind, join.left_end, join.right_start, join.n_bp, join.original_adjacency_id)
            if geometry not in unique:
                unique[geometry] = join
            else:
                previous = unique[geometry]
                unique[geometry] = self._join(left, right, join.kind, join.left_end, join.right_start, join.n_bp,
                                             tuple(sorted(set(previous.evidence_ids + join.evidence_ids))),
                                             next((e for e in self.original if e.adjacency_id == join.original_adjacency_id), None))
        ordered = sorted(unique.values(), key=lambda j: (j.kind == "reference_unknown", j.n_bp > 0,
                                                         j.left_end, j.right_start, j.join_id))
        if len(ordered) > self.policy.maximum_edge_variants:
            self.edge_pruning.append({"left_id": left_id, "right_id": right_id,
                                      "reason": "maximum_edge_variants", "omitted": len(ordered) - self.policy.maximum_edge_variants})
        self._joins[key] = tuple(ordered[:self.policy.maximum_edge_variants])
        return self._joins[key]

    @staticmethod
    def reference_order(left: Placement, right: Placement) -> bool:
        return bool(left.reference_intervals and right.reference_intervals
                    and max(i.end for i in left.reference_intervals) <= min(i.start for i in right.reference_intervals))

    def _join(self, left, right, kind, left_end, right_start, n_bp, evidence_ids, original=None):
        identity = [left.placement_id, right.placement_id, kind, left_end, right_start, n_bp,
                    sorted(evidence_ids), original.adjacency_id if original else None]
        return Join(stable_id("q0-join", identity), left.placement_id, right.placement_id, kind,
                    left_end, right_start, n_bp, tuple(sorted(evidence_ids)),
                    original.adjacency_id if original else None, original.source if original else None,
                    original.gap_interval if original else None)

    def materialize(self, nodes: tuple[str, ...], joins: tuple[Join, ...]) -> Path | None:
        if (not nodes or len(joins) != len(nodes) - 1 or len(set(nodes)) != len(nodes)
                or not any(self.placements[node].seed_eligible for node in nodes)):
            return None
        for left_id, right_id, join in zip(nodes, nodes[1:], joins):
            if join not in self.joins(left_id, right_id):
                raise Q0EvidenceError("unregistered q0 evidence join")
        slices, used = [], defaultdict(list)
        for index, node in enumerate(nodes):
            placement = self.placements[node]
            start = joins[index - 1].right_start if index else 0
            end = joins[index].left_end if index < len(joins) else placement.interval.length
            if start >= end:
                return None
            if index < len(joins) and (joins[index].left_id, joins[index].right_id) != (node, nodes[index + 1]):
                raise Q0EvidenceError("q0 join does not belong to path nodes")
            interval = placement.source_interval(Interval(start, end))
            if any(interval.intersection(other) for other in used[placement.source]):
                return None
            used[placement.source].append(interval)
            slices.append(Slice(node, placement.source, interval, placement.orientation))
        represented, duplicate, missing = self.coverage.assess((s.source, s.interval) for s in slices)
        if duplicate:
            return None
        switches = sum(a.source != b.source for a, b in zip(slices, slices[1:]))
        score = (represented, -sum(j.kind == "reference_unknown" for j in joins),
                 -sum(j.n_bp > 0 for j in joins), -switches, -len(slices), max(s.interval.length for s in slices))
        return Path(self.chromosome, nodes, joins, tuple(slices), score, missing)

    def source_rank(self, node: str):
        p = self.placements[node]
        return (p.source.dataset, p.source.contig, p.interval.start, p.interval.end, p.orientation, p.chromosome)

    def rank(self, path: Path):
        # Provenance IDs include PAF record identity and can change with row
        # ordering. They must not choose the source or clipping geometry.
        return (tuple(-value for value in path.score), tuple(self.source_rank(node) for node in path.nodes),
                tuple((j.kind, j.left_end, j.right_start, j.n_bp) for j in path.joins),
                path.nodes, tuple(j.join_id for j in path.joins))


def search_paths(graph: PathGraph) -> SearchResult:
    """Length-first seed, then reversible local beam search with explicit limits.

    Coverage is source bookkeeping under nonambiguous paired-base equivalence,
    not a vote across datasets. Unrepresented source intervals stay visible.
    A reference hull alone never discharges another source's contribution.
    """
    policy = graph.policy
    ordered = sorted(graph.placements, key=lambda key: (-graph.placements[key].interval.length, graph.source_rank(key), key))
    evaluations, seen, decisions = 0, set(), []
    stopped = set()

    def evaluate(nodes, *, quota=None):
        nonlocal evaluations
        if nodes in seen or len(set(nodes)) != len(nodes):
            return []
        if evaluations >= policy.maximum_evaluations or (quota is not None and evaluations >= quota):
            if evaluations >= policy.maximum_evaluations:
                stopped.add("maximum_evaluations")
            return []
        seen.add(nodes)
        evaluations += 1  # Failed/disconnected proposals consume the budget too.
        choices = [graph.joins(a, b) for a, b in zip(nodes, nodes[1:])]
        if any(not variants for variants in choices):
            return []
        paths = []
        for variant, joins in enumerate(product(*choices)):
            if variant:
                if evaluations >= policy.maximum_evaluations:
                    stopped.add("maximum_evaluations")
                    break
                evaluations += 1
            path = graph.materialize(nodes, joins)
            if path is not None:
                paths.append(path)
        return paths

    seeds = [node for node in ordered if graph.placements[node].seed_eligible]
    if not seeds:
        return SearchResult(None, (), [], {"policy": asdict(policy), "evaluations": 0,
                                          "stop_reasons": ["no_admitted_placements"], "global_optimality_claimed": False})
    seed = evaluate((seeds[0],))[0]
    observed = {seed.path_id: seed}
    seed_position_pruning = []

    def seed_positions(node):
        candidate = graph.placements[node]
        positions = set()
        referenced = [(min(i.start for i in graph.placements[key].reference_intervals), index)
                      for index, key in enumerate(seed.nodes) if graph.placements[key].reference_intervals]
        if candidate.reference_intervals and referenced:
            referenced.sort()
            pivot = bisect_left([start for start, _ in referenced], min(i.start for i in candidate.reference_intervals))
            insertion = referenced[pivot][1] if pivot < len(referenced) else len(seed.nodes)
            positions.update(i for i in (insertion - 1, insertion, insertion + 1) if 0 <= i <= len(seed.nodes))
        # Pairwise-only and original-N neighbors use actual incident evidence,
        # not invented ref coordinates. These are proposals; joins still prove
        # the cuts and connectivity before a path can be accepted.
        for index, key in enumerate(seed.nodes):
            neighbor = graph.placements[key]
            if (graph.links.get(tuple(sorted((candidate.source, neighbor.source))))
                    or candidate.source == neighbor.source):
                positions.update((index, index + 1))
        ordered_positions = sorted(positions)
        if len(ordered_positions) > policy.maximum_seed_positions:
            seed_position_pruning.append({"placement_id": node, "omitted": len(ordered_positions) - policy.maximum_seed_positions})
        return ordered_positions[:policy.maximum_seed_positions]

    for node in (node for node in ordered if node != seeds[0]):
        choices = [path for index in seed_positions(node)
                   for path in evaluate(seed.nodes[:index] + (node,) + seed.nodes[index:])]
        if choices:
            best = min([seed, *choices], key=graph.rank)
            observed.update((p.path_id, p) for p in choices)
            if best.score > seed.score:
                decisions.append(_decision("length_first_add", seed, best, node))
                seed = best
        if "maximum_evaluations" in stopped:
            break
    initial = seed
    # Alternative single-source starts can displace the initial long source.
    for node in ordered:
        observed.update((p.path_id, p) for p in evaluate((node,)))
        if "maximum_evaluations" in stopped:
            break
    beam = sorted(observed.values(), key=graph.rank)[:policy.beam_width]
    beam_pruning = []
    if len(observed) > len(beam):
        beam_pruning.append({"phase": "seeds", "omitted": len(observed) - len(beam)})
    best = beam[0]
    if best.path_id != initial.path_id:
        decisions.append(_decision("alternative_seed", initial, best, None))
    rounds = 0
    for rounds in range(1, policy.maximum_rounds + 1):
        if "maximum_evaluations" in stopped:
            break
        next_paths = {p.path_id: p for p in beam}
        for current in beam:
            # Pure removal is necessary after a bridge makes an earlier source
            # redundant; requiring a new node here would freeze the old choice.
            for start in range(len(current.nodes)):
                for removed in range(1, min(policy.maximum_replaced_nodes, len(current.nodes) - start) + 1):
                    nodes = current.nodes[:start] + current.nodes[start + removed:]
                    if nodes:
                        next_paths.update((p.path_id, p) for p in evaluate(nodes))
                    if "maximum_evaluations" in stopped:
                        break
                if "maximum_evaluations" in stopped:
                    break
            for node in ordered:
                if node in current.nodes:
                    continue
                for start in range(len(current.nodes) + 1):
                    for removed in range(min(policy.maximum_replaced_nodes, len(current.nodes) - start) + 1):
                        nodes = current.nodes[:start] + (node,) + current.nodes[start + removed:]
                        for candidate in evaluate(nodes):
                            next_paths[candidate.path_id] = candidate
                        if "maximum_evaluations" in stopped:
                            break
                    if "maximum_evaluations" in stopped:
                        break
                if "maximum_evaluations" in stopped:
                    break
            if "maximum_evaluations" in stopped:
                break
        next_beam = sorted(next_paths.values(), key=graph.rank)[:policy.beam_width]
        if len(next_paths) > len(next_beam):
            beam_pruning.append({"phase": "local_search", "round": rounds, "omitted": len(next_paths) - len(next_beam)})
        if next_beam[0].score > best.score:
            updated = next_beam[0]
            decisions.append(_decision("local_replacement", best, updated, None))
            best = updated
        if [p.path_id for p in next_beam] == [p.path_id for p in beam]:
            stopped.add("beam_fixed_point")
            beam = next_beam
            break
        beam = next_beam
    else:
        stopped.add("maximum_rounds")
    selected = set(best.nodes)
    for node in ordered:
        if node not in selected:
            p = graph.placements[node]
            remaining = next(intervals for source, intervals in best.missing if source == p.source)
            uncovered = [overlap for interval in remaining if (overlap := interval.intersection(p.interval))]
            decisions.append({"operation": "not_selected", "placement_id": node,
                              "reason": "represented_by_selected_sources" if not uncovered else "unresolved_or_search_limited",
                              "unrepresented_intervals": [asdict(i) for i in uncovered]})
    return SearchResult(best, tuple(p for p in beam if p.path_id != best.path_id), decisions,
                        {"policy": asdict(policy), "evaluations": evaluations, "rounds": rounds,
                         "initial_path_id": initial.path_id, "initial_score": list(initial.score),
                         "stop_reasons": sorted(stopped), "edge_pruning": graph.edge_pruning, "beam_pruning": beam_pruning,
                         "seed_position_pruning": seed_position_pruning,
                         "ambiguous_equivalence_ids": sorted(graph.ambiguous_equivalence_ids),
                         "coverage_atoms": len(graph.coverage.atoms), "unique_required_bp": graph.coverage.total_bp,
                         "global_optimality_claimed": False})


def _decision(operation: str, old: Path, new: Path, candidate: str | None) -> dict:
    old_gaps = {j.join_id for j in old.joins if j.n_bp}
    new_ids = set(new.nodes) - set(old.nodes)
    bridge = any(new.joins[i - 1].kind == new.joins[i].kind == "sequence_overlap"
                 for i, node in enumerate(new.nodes) if node in new_ids and 0 < i < len(new.nodes) - 1)
    removed = old_gaps - {j.join_id for j in new.joins if j.n_bp}
    return {"operation": "bridge_replacement" if bridge and removed else operation,
            "candidate_id": candidate, "before_path_id": old.path_id, "after_path_id": new.path_id,
            "before_nodes": list(old.nodes), "after_nodes": list(new.nodes),
            "before_slices": [asdict(s) for s in old.slices], "after_slices": [asdict(s) for s in new.slices],
            "before_score": list(old.score), "after_score": list(new.score),
            "evidence_ids": sorted({e for join in new.joins for e in join.evidence_ids}),
            "replaced_connections": [asdict(j) for j in old.joins if j.join_id in removed],
            "removed_reference_unknown_ids": sorted(j.join_id for j in old.joins if j.join_id in removed and j.kind == "reference_unknown"),
            "removed_input_gap_ids": sorted(j.join_id for j in old.joins if j.join_id in removed and j.kind == "input_assembly_gap"),
            "reason": "greater_source_representation_then_fewer_unsupported_connections"}


def reconstruct(path: Path, sequences: Mapping[SourceKey, str]) -> str:
    parts = []
    for index, item in enumerate(path.slices):
        sequence = sequences[item.source]
        if item.interval.end > len(sequence):
            raise Q0EvidenceError("q0 path source exceeds sequence length")
        piece = sequence[item.interval.start:item.interval.end]
        parts.append(piece if item.orientation == "+" else reverse_complement(piece))
        if index < len(path.joins):
            join = path.joins[index]
            if join.kind == "input_assembly_gap":
                gap = sequences[join.gap_source][join.gap_interval.start:join.gap_interval.end]
                if len(gap) != join.n_bp or set(gap.upper()) != {"N"}:
                    raise Q0EvidenceError("original q0 gap differs from input assembly")
            parts.append("N" * join.n_bp)
    return "".join(parts)
