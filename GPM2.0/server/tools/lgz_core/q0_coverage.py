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
from typing import Iterable, Mapping

from .q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals, subtract_intervals


@dataclass(frozen=True)
class Equivalence:
    left_source: SourceKey
    left: Interval
    right_source: SourceKey
    right: Interval
    reverse: bool
    evidence_id: str

    def __post_init__(self):
        if self.left.length != self.right.length:
            raise Q0EvidenceError("homology equivalence requires equal paired-base spans")


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


class CoverageModel:
    def __init__(self, required: Mapping[SourceKey, Iterable[Interval]], relations: Iterable[Equivalence],
                 *, maximum_boundaries: int = 200000):
        self.required = {key: merged_intervals(value) for key, value in required.items()}
        relations = tuple(sorted(set(relations), key=lambda r: (r.left_source, r.left, r.right_source, r.right, r.reverse, r.evidence_id)))
        points = {key: {p for i in value for p in (i.start, i.end)} for key, value in self.required.items()}
        incident = defaultdict(list)
        for relation in relations:
            for source, interval, other, dest in (
                (relation.left_source, relation.left, relation.right_source, relation.right),
                (relation.right_source, relation.right, relation.left_source, relation.left),
            ):
                if source not in self.required or not any(i.contains(interval) for i in self.required[source]):
                    raise Q0EvidenceError("homology relation escapes required source intervals")
                points[source].update((interval.start, interval.end))
                incident[source].append((interval, other, dest, relation.reverse))
        queue = deque((source, point) for source in sorted(points) for point in sorted(points[source]))
        count = len(queue)
        if count > maximum_boundaries:
            raise Q0EvidenceError("q0 coordinate-equivalence boundary limit exceeded")
        indexes = {source: _IncidentRelations(rows) for source, rows in incident.items()}
        while queue:
            source, point = queue.popleft()
            index = indexes.get(source)
            if index is None:
                continue
            for other, mapped in index.at(point):
                if mapped not in points[other]:
                    count += 1
                    if count > maximum_boundaries:
                        raise Q0EvidenceError("q0 coordinate-equivalence boundary limit exceeded")
                    points[other].add(mapped)
                    queue.append((other, mapped))
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
            if sizes[ra] < sizes[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            parity[rb] = pa ^ pb ^ reverse
            sizes[ra] += sizes[rb]

        relation_atoms = []
        for relation in relations:
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
                relation_atoms.append((index, relation.evidence_id))
        self.units = [find(index) for index in range(len(parent))]
        members = defaultdict(list)
        for index, (root, flip) in enumerate(self.units):
            members[root].append(index)
        ambiguous_roots = {self.units[index][0] for index in inconsistent}
        for root, indices in members.items():
            sources = [self.atoms[index][0] for index in indices]
            if len(set(sources)) != len(sources):
                ambiguous_roots.add(root)
        self.ambiguous_evidence_ids = frozenset(eid for index, eid in relation_atoms
                                                if self.units[index][0] in ambiguous_roots)
        self.unit_lengths = {root: self.atoms[indices[0]][1].length for root, indices in members.items()}
        self.boundary_count = count
        self.total_bp = sum(self.unit_lengths.values())

    def _overlapping_atoms(self, source, interval):
        first = bisect_right(self._atom_ends.get(source, ()), interval.start)
        stop = bisect_left(self._atom_starts.get(source, ()), interval.end, lo=first)
        indices = self.by_source.get(source, ())
        for i in range(first, stop):
            yield indices[i]

    def _project_selected(self, selected: Iterable[tuple[SourceKey, Interval]]):
        """Validate every slice and project it onto the same oriented units for both callers."""
        if self.ambiguous_evidence_ids:
            raise Q0EvidenceError("ambiguous homology must be removed before q0 path scoring")
        covered = defaultdict(list)
        duplicate = False
        selected_bp = 0
        for source, interval in selected:
            if source not in self.required or not any(i.contains(interval) for i in self.required[source]):
                raise Q0EvidenceError("selected interval escapes q0 coverage requirements")
            selected_bp += interval.length
            for index in self._overlapping_atoms(source, interval):
                atom = self.atoms[index][1]
                overlap = atom.intersection(interval)
                root, flip = self.units[index]
                local = (Interval(atom.end - overlap.end, atom.end - overlap.start) if flip else
                         Interval(overlap.start - atom.start, overlap.end - atom.start))
                duplicate |= any(local.intersection(previous) is not None for previous in covered[root])
                covered[root].append(local)
        return covered, duplicate, selected_bp

    def unique_selected_bp(self, selected: Iterable[tuple[SourceKey, Interval]]) -> int | None:
        """Exact candidate score, or None if any represented base occurs twice.

        The atoms partition each required interval. Mapping to a unit (including a
        reversed unit) preserves length. After the overlap check, the union of disjoint
        projected slices therefore has exactly their summed input length. No missing
        inventory, or walk over the chromosome's unselected atoms, is needed to rank it.
        """
        _, duplicate, selected_bp = self._project_selected(selected)
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
