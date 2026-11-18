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
        while queue:
            source, point = queue.popleft()
            for interval, other, dest, reverse in incident[source]:
                if not interval.start <= point <= interval.end:
                    continue
                mapped = dest.end - (point - interval.start) if reverse else dest.start + point - interval.start
                if mapped not in points[other]:
                    count += 1
                    if count > maximum_boundaries:
                        raise Q0EvidenceError("q0 coordinate-equivalence boundary limit exceeded")
                    points[other].add(mapped)
                    queue.append((other, mapped))
        self.atoms, self.by_source = [], defaultdict(list)
        lookup = {}
        for source in sorted(points):
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
            for index in self.by_source[relation.left_source]:
                interval = self.atoms[index][1]
                if not relation.left.contains(interval):
                    continue
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

    def assess(self, selected: Iterable[tuple[SourceKey, Interval]]):
        if self.ambiguous_evidence_ids:
            raise Q0EvidenceError("ambiguous homology must be removed before q0 path scoring")
        covered = defaultdict(list)
        duplicate = False
        for source, interval in selected:
            if source not in self.required or not any(i.contains(interval) for i in self.required[source]):
                raise Q0EvidenceError("selected interval escapes q0 coverage requirements")
            for index in self.by_source[source]:
                atom = self.atoms[index][1]
                overlap = atom.intersection(interval)
                if overlap is None:
                    continue
                root, flip = self.units[index]
                local = (Interval(atom.end - overlap.end, atom.end - overlap.start) if flip else
                         Interval(overlap.start - atom.start, overlap.end - atom.start))
                duplicate |= any(local.intersection(previous) is not None for previous in covered[root])
                covered[root].append(local)
        covered = {key: merged_intervals(value) for key, value in covered.items()}
        represented = sum(i.length for intervals in covered.values() for i in intervals)
        missing = defaultdict(list)
        for index, (source, atom) in enumerate(self.atoms):
            root, flip = self.units[index]
            for local in subtract_intervals(Interval(0, atom.length), covered.get(root, ())):
                original = (Interval(atom.end - local.end, atom.end - local.start) if flip else
                            Interval(atom.start + local.start, atom.start + local.end))
                missing[source].append(original)
        return represented, duplicate, tuple((source, merged_intervals(missing[source])) for source in sorted(self.required))
