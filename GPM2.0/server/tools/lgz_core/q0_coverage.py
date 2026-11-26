"""Coordinate equivalence for source representation, not evidence voting.

Split at actual paired-base relation boundaries, propagate corresponding cuts,
then identify equal-length atoms. Indels create separate atoms. A component
mapping two different loci from one source together is ambiguous, not a license
to collapse a biological repeat. Callers must discard its implicated evidence.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from time import monotonic
from typing import Callable, Iterable, Mapping

from .q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals, subtract_intervals


@dataclass(frozen=True)
class _CoordinateMap:
    left_source: SourceKey
    left: Interval
    right_source: SourceKey
    right: Interval
    reverse: bool

    def __post_init__(self):
        if self.left.length != self.right.length:
            raise Q0EvidenceError("homology equivalence requires equal paired-base spans")


@dataclass(frozen=True)
class Equivalence(_CoordinateMap):
    evidence_id: str


class _IncidentRelations:
    """Closed boundary queries over immutable paired half-open base spans."""

    def __init__(self, relations):
        self.rows = sorted(relations, key=lambda row: row[0].start)
        self.starts, self.prefix_ends = [], []
        farthest = 0
        for interval, *_ in self.rows:
            farthest = max(farthest, interval.end)
            self.starts.append(interval.start)
            self.prefix_ends.append(farthest)

    def at(self, point):
        # End coordinates are valid cuts, despite the underlying base spans
        # being half-open. In particular, visit both adjacent relations here.
        first = bisect_left(self.prefix_ends, point)
        stop = bisect_right(self.starts, point, lo=first)
        for i in range(first, stop):
            interval, other, dest, reverse = self.rows[i]
            if point <= interval.end:
                yield other, (dest.end - (point - interval.start) if reverse
                              else dest.start + point - interval.start)


def _affine_key(row):
    # Maps *cuts*: y = x + offset (forward) or y = offset - x (reverse).
    offset = row.right.end + row.left.start if row.reverse else row.right.start - row.left.start
    return row.left_source, row.right_source, row.reverse, offset


def _compact_maps(maps):
    """Input is sorted by (left_source, left interval, ...). No second sort or copy on a miss."""
    out = None
    for _, group in groupby(enumerate(maps), key=lambda item: item[1].left_source):
        last = {}  # most recent disjoint run of each isometry on this source
        for i, row in group:
            key = _affine_key(row)
            slot = last.get(key)
            if slot is not None:
                prev = (maps if out is None else out)[slot]
                if row.left.start <= prev.left.end:
                    if out is None:
                        out = list(maps[:i])
                    if row.left.end > prev.left.end:
                        dest = Interval(min(prev.right.start, row.right.start), max(prev.right.end, row.right.end))
                        out[slot] = _CoordinateMap(row.left_source, Interval(prev.left.start, row.left.end),
                                                   row.right_source, dest, row.reverse)
                    continue
            last[key] = i if out is None else len(out)
            if out is not None:
                out.append(row)
    return maps if out is None else tuple(out)


class CoverageBoundaryLimit(Q0EvidenceError):
    """The exact coverage closure exceeded its resource budget, not malformed evidence."""


class _BoundaryLimit(CoverageBoundaryLimit):
    def __init__(self, limit, seeds, points, maps, *, pending=None):
        self.seeds = seeds
        # Failure-only accounting. Components here connect whole source keys,
        # not necessarily overlapping loci within a source. Include the cut
        # that would cross the cap, without installing or propagating it.
        neighbors = defaultdict(set)
        for row in maps:
            neighbors[row.left_source].add(row.right_source)
            neighbors[row.right_source].add(row.left_source)
        seen = set()
        sizes = []
        pending_component = None
        for source in points:
            if source in seen:
                continue
            stack, size, has_pending = [source], 0, False
            seen.add(source)
            while stack:
                key = stack.pop()
                size += len(points[key])
                if pending is not None and key == pending[0]:
                    size += 1
                    has_pending = True
                for other in neighbors.get(key, ()):
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
            sizes.append(size)
            if has_pending:
                pending_component = size
        where = (f"propagation next={pending[0].dataset}:{pending[0].contig}:{pending[1]} "
                 f"next_component_cuts={pending_component}"
                 if pending is not None else "initial")
        super().__init__(f"q0 coordinate-equivalence boundary limit exceeded: limit={limit} phase={where} "
                         f"seed_cuts={seeds} observed_cuts={sum(sizes)} source_components={len(sizes)} "
                         f"largest_component_cuts={max(sizes, default=0)}")


def _close_cuts(required, maps, limit, *, fewer_seeds_than=None, progress=None):
    points = {key: {p for i in value for p in (i.start, i.end)} for key, value in required.items()}
    incident = defaultdict(list)
    for r in maps:
        for source, interval, other, dest in ((r.left_source, r.left, r.right_source, r.right),
                                               (r.right_source, r.right, r.left_source, r.left)):
            if source not in required or not any(i.contains(interval) for i in required[source]):
                raise Q0EvidenceError("homology relation escapes required source intervals")
            points[source].update((interval.start, interval.end))
            incident[source].append((interval, other, dest, r.reverse))
    count = seeds = sum(map(len, points.values()))
    if fewer_seeds_than is not None and seeds >= fewer_seeds_than:
        return None  # compact seeds are a subset; identical seeds imply identical closure
    if limit is not None and count > limit:
        raise _BoundaryLimit(limit, seeds, points, maps)
    queue = deque((source, point) for source in sorted(points) for point in sorted(points[source]))
    indexes = {source: _IncidentRelations(rows) for source, rows in incident.items()}
    del incident
    if progress:
        progress(f"cut propagation: seeds={seeds} limit={limit if limit is not None else 'none'}")
    next_report = monotonic() + 60
    processed = 0
    while queue:
        processed += 1
        if progress and not (processed & 4095) and monotonic() >= next_report:
            progress(f"cut propagation: processed={processed} cuts={count} pending={len(queue)}")
            next_report = monotonic() + 60
        source, point = queue.popleft()
        index = indexes.get(source)
        if index is None:
            continue
        for other, mapped in index.at(point):
            if mapped not in points[other]:
                if limit is not None and count >= limit:
                    raise _BoundaryLimit(limit, seeds, points, maps, pending=(other, mapped))
                points[other].add(mapped)
                count += 1
                queue.append((other, mapped))
    return points, count


def _partition(required, maps, limit, progress, compact_first):
    if compact_first:
        compact = _compact_maps(maps)
        if progress:
            progress(f"request coverage: exact maps={len(maps)}->{len(compact)} before cut propagation")
        # Only representation changes. Every raw evidence span is still used
        # for ambiguity attribution; all required endpoints remain.
        try:
            points, count = _close_cuts(required, compact, limit, progress=progress)
        except _BoundaryLimit as exc:
            raise CoverageBoundaryLimit(f"{exc}; exact request geometry exceeds budget") from None
        return compact, points, count
    try:
        points, count = _close_cuts(required, maps, limit, progress=progress)
        return maps, points, count
    except _BoundaryLimit as exc:
        original, seeds = str(exc), exc.seeds
    # Outside the handler: do not retain the overflowing partition/traceback.
    if progress:
        progress(f"coverage: {original}; checking for redundant collinear cuts")
    compact = _compact_maps(maps)
    if len(compact) < len(maps):
        # Retain the published fallback's original map traversal order.
        compact = tuple(sorted(compact, key=lambda r: (_affine_key(r), r.left)))
        try:
            partition = _close_cuts(required, compact, limit, fewer_seeds_than=seeds)
        except _BoundaryLimit as exc:
            raise CoverageBoundaryLimit(f"{exc}; exact compact geometry also exceeds budget") from None
        if partition is not None:
            points, count = partition
            if progress:
                progress(f"coverage: exact compact geometry maps={len(maps)}->{len(compact)} "
                         f"closed_cuts={count} limit={limit}")
            return compact, points, count
    raise CoverageBoundaryLimit(f"{original}; no redundant seed cuts to remove")


def _relation_islands(relations):
    """Independent map domains. Closed spans include touching cuts on either source axis."""
    parents = list(range(len(relations)))
    sizes = [1] * len(parents)

    def root(i):
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def connect(i, j):
        i, j = root(i), root(j)
        if i != j:
            if sizes[i] < sizes[j]:
                i, j = j, i
            parents[j] = i
            sizes[i] += sizes[j]

    spans = defaultdict(list)
    for i, r in enumerate(relations):
        spans[r.left_source].append((r.left.start, r.left.end, i))
        spans[r.right_source].append((r.right.start, r.right.end, i))
    for rows in spans.values():
        farthest = -1
        for start, end, i in sorted(rows):
            if start > farthest:
                leader = i
            else:
                connect(leader, i)
            farthest = max(farthest, end)
    islands = defaultdict(list)
    for i, r in enumerate(relations):
        islands[root(i)].append(r)
    return sorted(islands.values(), key=len, reverse=True)


def _consistent_source_axes(rows):
    """Sufficient, not necessary: one injective signed coordinate frame per source.

    Each map says y=s*x+d on its own domain. If these equations compose to
    identity around every cycle, no atom can return to another locus or with
    reversed parity in its own source. Never infer extra aligned bases here.
    """
    if len(rows) == 1 and rows[0].left_source != rows[0].right_source:
        return True
    edges = defaultdict(list)
    for row in rows:
        a, b, reverse, delta = _affine_key(row)
        sign = -1 if reverse else 1
        edges[a].append((b, sign, delta))
        edges[b].append((a, sign, -sign * delta))
    frames = {}
    for source in edges:
        if source in frames:
            continue
        frames[source] = (1, 0)
        todo = [source]
        while todo:
            a = todo.pop()
            orientation, origin = frames[a]
            for b, sign, delta in edges[a]:
                want = (sign * orientation, sign * origin + delta)
                if b not in frames:
                    frames[b] = want
                    todo.append(b)
                elif frames[b] != want:
                    return False  # Only failure to prove; never an evidence rejection.
    return True


def preliminary_ambiguity(required, relations, *, maximum_boundaries=None, progress=None, compact_first=False):
    """Prove simple islands; solve the remaining domains exactly, one at a time."""
    # Validate even rows skipped by the affine proof or excluded from the final
    # model. Required intervals were normalized by PathGraph. Within a mapped
    # span no required interval can introduce an interior seed of its own.
    for r in relations:
        for source, span in ((r.left_source, r.left), (r.right_source, r.right)):
            if not any(i.contains(span) for i in required.get(source, ())):
                raise Q0EvidenceError("homology relation escapes required source intervals")
    islands = _relation_islands(relations)
    if progress:
        progress(f"preliminary ambiguity: islands={len(islands)} evidence_spans={len(relations)} "
                 f"largest_island_relations={len(islands[0]) if islands else 0}")
    excluded = set()
    simple = 0
    for n, rows in enumerate(islands, 1):
        if _consistent_source_axes(rows):
            simple += 1
            continue
        footprint = defaultdict(list)
        for r in rows:
            footprint[r.left_source].append(r.left)
            footprint[r.right_source].append(r.right)
        # Emit inner progress for substantial domains without flooding logs for tiny ones.
        report = None
        if progress and (n == 1 or len(rows) >= 256):
            prefix = f"ambiguity island {n}/{len(islands)} relations={len(rows)}: "
            report = lambda message: progress(prefix + message)
        model = CoverageModel(footprint, rows, maximum_boundaries=maximum_boundaries,
                              progress=report, compact_first=compact_first)
        excluded.update(model.ambiguous_evidence_ids)
        del model
    if progress:
        progress(f"preliminary ambiguity complete: simple_islands={simple} exact_islands={len(islands)-simple} "
                 f"excluded_evidence_ids={len(excluded)}")
    return excluded


class CoverageModel:
    def __init__(self, required: Mapping[SourceKey, Iterable[Interval]], relations: Iterable[Equivalence],
                 *, maximum_boundaries: int | None = None, progress: Callable[[str], None] | None = None,
                 compact_first: bool = False, reference_domains=None):
        started = monotonic() if progress else 0.0
        self.required = {key: merged_intervals(value) for key, value in required.items()}
        geometry = attrgetter("left_source", "left", "right_source", "right", "reverse")
        relations = sorted(set(relations), key=geometry)
        # Duplicate geometric maps need only one propagation/union, regardless
        # of how many distinct evidence records support the same bases.
        maps = tuple(next(group) for _, group in groupby(relations, key=geometry))
        maps, points, count = _partition(self.required, maps, maximum_boundaries, progress, compact_first)
        if progress:
            closed_at = monotonic()
            progress(f"coverage partition ready: evidence_spans={len(relations)} maps={len(maps)} "
                     f"cuts={count} partition_s={closed_at-started:.2f}")
        self.atoms, self.by_source = [], defaultdict(list)
        self._atom_starts, self._atom_ends = defaultdict(list), defaultdict(list)
        self._sources = tuple(sorted(points))
        lookup = {}
        for source in self._sources:
            ordered = sorted(points[source])
            for required_interval in self.required[source]:
                start = bisect_left(ordered, required_interval.start)
                end = bisect_right(ordered, required_interval.end)
                for a, b in zip(ordered[start:end], ordered[start + 1:end]):
                    atom = (source, Interval(a, b))
                    index = len(self.atoms)
                    lookup[atom] = index
                    self.atoms.append(atom)
                    self.by_source[source].append(index)
                    self._atom_starts[source].append(a)
                    self._atom_ends[source].append(b)
        from .q0_reference_locus import intersection
        feasible = ([reference_domains.atom(source, iv) for source, iv in self.atoms]
                    if reference_domains is not None else None)
        self.locus_audit = defaultdict(int)
        parent = list(range(len(self.atoms)))
        parity = [False] * len(parent)
        sizes = [1] * len(parent)
        inconsistent = set()

        def find(index):
            if parent[index] != index:
                root, flip = find(parent[index])
                parity[index] ^= flip
                parent[index] = root
            return parent[index], parity[index]

        def union(a, b, reverse):
            ra, pa = find(a); rb, pb = find(b)
            if ra == rb:
                if pa ^ pb != reverse:
                    inconsistent.add(a)
                return
            if feasible is not None:
                common = intersection(feasible[ra], feasible[rb])
                if common == ():
                    self.locus_audit["rejected_unions"] += 1
                    self.locus_audit["rejected_atom_bp_sum"] += self.atoms[a][1].length
                    self.locus_audit["maximum_rejected_map_bp"] = max(self.locus_audit["maximum_rejected_map_bp"], relation.left.length)
                    self.locus_audit["rejected_large_map_unions"] += relation.left.length > 100_000
                    return
                self.locus_audit["accepted_unions"] += 1
            if sizes[ra] < sizes[rb]:
                ra, rb = rb, ra
            if feasible is not None:
                feasible[ra] = common
            parent[rb] = ra
            parity[rb] = pa ^ pb ^ reverse
            sizes[ra] += sizes[rb]

        for relation in maps:
            for index in self._overlapping_atoms(relation.left_source, relation.left):
                # Relation endpoints were installed as cuts before building
                # the atoms, so every overlapping atom is wholly contained.
                interval = self.atoms[index][1]
                other = (Interval(relation.right.end - (interval.end - relation.left.start),
                                  relation.right.end - (interval.start - relation.left.start)) if relation.reverse else
                         Interval(relation.right.start + interval.start - relation.left.start,
                                  relation.right.start + interval.end - relation.left.start))
                target = lookup[(relation.right_source, other)]
                union(index, target, relation.reverse)
        self.units = [find(index) for index in range(len(parent))]
        del union, find  # Break the recursive closure; do not retain parent/parity between islands.
        members = defaultdict(list)
        for index, (root, flip) in enumerate(self.units):
            members[root].append(index)
        ambiguous_roots = {self.units[index][0] for index in inconsistent}
        for root, indices in members.items():
            sources = [self.atoms[index][0] for index in indices]
            if len(set(sources)) != len(sources):
                ambiguous_roots.add(root)
        # A compact map may span several original evidence records. Attribute
        # ambiguity by actual half-open intersection, never by the merged map's
        # envelope/ID. All bases of an ambiguous atom have a same-source alias
        # or inconsistent orientation; refining it cannot clear that ambiguity.
        ambiguous_ids = set()
        if ambiguous_roots:
            starts, ends = defaultdict(list), defaultdict(list)
            for (source, interval), (root, _) in zip(self.atoms, self.units):
                if root in ambiguous_roots:
                    starts[source].append(interval.start)
                    ends[source].append(interval.end)
            for r in relations:
                lefts = starts.get(r.left_source)
                if lefts:
                    i = bisect_right(ends[r.left_source], r.left.start)
                    if i < len(lefts) and lefts[i] < r.left.end:
                        ambiguous_ids.add(r.evidence_id)
        self.ambiguous_evidence_ids = frozenset(ambiguous_ids)
        self.unit_lengths = {root: self.atoms[indices[0]][1].length for root, indices in members.items()}
        self.boundary_count = count
        self.total_bp = sum(self.unit_lengths.values())
        if progress:
            progress(f"coverage units ready: atoms={len(self.atoms)} ambiguous_ids={len(ambiguous_ids)} "
                     f"units_s={monotonic()-closed_at:.2f}")

    def _overlapping_atoms(self, source, interval):
        first = bisect_right(self._atom_ends.get(source, ()), interval.start)
        stop = bisect_left(self._atom_starts.get(source, ()), interval.end, lo=first)
        indices = self.by_source.get(source, ())
        for i in range(first, stop):
            yield indices[i]

    def _project_selected(self, selected: Iterable[tuple[SourceKey, Interval]], *, score_only=False):
        """Validate every slice; only a full assessment needs the per-unit coverage inventory."""
        if self.ambiguous_evidence_ids:
            raise Q0EvidenceError("ambiguous homology must be removed before q0 path scoring")
        covered = defaultdict(list)
        whole_roots = set() if score_only else None
        duplicate = False
        selected_bp = 0
        for source, interval in selected:
            if source not in self.required or not any(i.contains(interval) for i in self.required[source]):
                raise Q0EvidenceError("selected interval escapes q0 coverage requirements")
            selected_bp += interval.length
            if score_only and duplicate:
                continue  # Later slices must still pass the source/bounds check above.
            for index in self._overlapping_atoms(source, interval):
                atom = self.atoms[index][1]
                root, flip = self.units[index]
                if whole_roots is not None:
                    # A whole atom occupies its whole unit, even on the reverse strand.
                    # No clipped coordinates are needed except at slice boundaries.
                    if root in whole_roots:
                        duplicate = True
                        break
                    if interval.contains(atom):
                        if root in covered:  # A previous clipped piece already occupies this unit.
                            duplicate = True
                            break
                        whole_roots.add(root)
                        continue
                overlap = atom.intersection(interval)
                local = (Interval(atom.end - overlap.end, atom.end - overlap.start) if flip else
                         Interval(overlap.start - atom.start, overlap.end - atom.start))
                duplicate |= any(local.intersection(previous) is not None for previous in covered[root])
                if score_only and duplicate:
                    break
                covered[root].append(local)
        return (None if score_only else covered), duplicate, selected_bp

    def unique_selected_bp(self, selected: Iterable[tuple[SourceKey, Interval]]) -> int | None:
        """Exact candidate score, or None if any represented base occurs twice.

        The atoms partition each required interval. Mapping to a unit (including a
        reversed unit) preserves length. After the overlap check, the union of disjoint
        projected slices therefore has exactly their summed input length. No missing
        inventory, or walk over the chromosome's unselected atoms, is needed to rank it.
        """
        _, duplicate, selected_bp = self._project_selected(selected, score_only=True)
        return None if duplicate else selected_bp

    def assess(self, selected: Iterable[tuple[SourceKey, Interval]]):
        covered, duplicate, _ = self._project_selected(selected)
        covered = {key: value if len(value) == 1 else merged_intervals(value)
                   for key, value in covered.items()}
        represented = sum(i.length for intervals in covered.values() for i in intervals)
        missing = defaultdict(list)
        for index, (source, atom) in enumerate(self.atoms):
            root, flip = self.units[index]
            local_spans = covered.get(root)
            if local_spans is None:
                missing[source].append(atom)
                continue
            if len(local_spans) == 1 and local_spans[0].length == atom.length:
                continue
            for local in subtract_intervals(Interval(0, atom.length), local_spans):
                original = (Interval(atom.end - local.end, atom.end - local.start) if flip else
                            Interval(atom.start + local.start, atom.start + local.end))
                missing[source].append(original)
        return represented, duplicate, tuple((source, merged_intervals(missing[source])) for source in self._sources)
