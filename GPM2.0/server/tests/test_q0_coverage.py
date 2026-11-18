from __future__ import annotations

import random
import unittest

from server.tools.lgz_core.q0_coverage import CoverageModel, Equivalence
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey


class CoverageEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = [SourceKey(name, name) for name in "abc"]

    def test_partial_cuts_propagate_through_forward_and_reverse_relations(self):
        required = {self.a: [Interval(10, 30)], self.b: [Interval(100, 120)], self.c: [Interval(200, 210)]}
        relations = [Equivalence(self.a, Interval(10, 30), self.b, Interval(100, 120), True, "ab"),
                     Equivalence(self.b, Interval(105, 115), self.c, Interval(200, 210), False, "bc")]
        model = CoverageModel(required, relations)
        self.assertEqual(model.total_bp, 20)
        represented, duplicate, missing = model.assess([(self.a, Interval(10, 17)), (self.c, Interval(201, 205))])
        # a 10:17 maps b 113:120; c 201:205 maps b 106:110.
        self.assertEqual(represented, 11)
        self.assertFalse(duplicate)
        self.assertEqual(dict(missing)[self.b], (Interval(100, 106), Interval(110, 113)))

    def test_same_homology_coordinates_are_duplicate_not_extra_coverage(self):
        required = {self.a: [Interval(0, 10)], self.b: [Interval(20, 30)]}
        model = CoverageModel(required, [Equivalence(self.a, Interval(0, 10), self.b, Interval(20, 30), True, "ab")])
        represented, duplicate, _ = model.assess([(self.a, Interval(0, 3)), (self.b, Interval(27, 30))])
        self.assertEqual(represented, 3)
        self.assertTrue(duplicate)

    def test_unpaired_inserted_sequence_stays_independent(self):
        required = {self.a: [Interval(0, 20)], self.b: [Interval(0, 25)]}
        relations = [Equivalence(self.a, Interval(0, 10), self.b, Interval(0, 10), False, "ab1"),
                     Equivalence(self.a, Interval(10, 20), self.b, Interval(15, 25), False, "ab2")]
        model = CoverageModel(required, relations)
        self.assertEqual(model.total_bp, 25)
        self.assertEqual(model.assess([(self.a, Interval(0, 20))])[0], 20)
        self.assertEqual(dict(model.assess([(self.a, Interval(0, 20))])[2])[self.b], (Interval(10, 15),))
        self.assertEqual(model.assess([(self.b, Interval(0, 25))])[0], 25)

    def test_nonidentical_loci_from_same_source_are_ambiguous(self):
        required = {self.a: [Interval(0, 10), Interval(20, 30)], self.b: [Interval(100, 110)]}
        model = CoverageModel(required, [Equivalence(self.a, Interval(0, 10), self.b, Interval(100, 110), False, "ab1"),
                                         Equivalence(self.a, Interval(20, 30), self.b, Interval(100, 110), False, "ab2")])
        self.assertEqual(model.ambiguous_evidence_ids, {"ab1", "ab2"})
        with self.assertRaisesRegex(Q0EvidenceError, "ambiguous homology"):
            model.assess([(self.b, Interval(100, 110))])

    def test_limit_is_explicit_not_a_fallback_to_dataset_votes(self):
        with self.assertRaisesRegex(Q0EvidenceError, "boundary limit"):
            CoverageModel({self.a: [Interval(0, 10)], self.b: [Interval(0, 10)]}, [], maximum_boundaries=3)

    def test_invalid_equivalence_and_selected_intervals_fail(self):
        with self.assertRaises(Q0EvidenceError):
            Equivalence(self.a, Interval(0, 10), self.b, Interval(0, 9), False, "bad")
        model = CoverageModel({self.a: [Interval(0, 10)]}, [])
        with self.assertRaises(Q0EvidenceError):
            model.assess([(self.a, Interval(5, 11))])

    def test_random_small_relations_against_independent_per_base_oracle(self):
        rng = random.Random(20261118)
        for trial in range(120):
            required = {source: [Interval(0, 24)] for source in (self.a, self.b, self.c)}
            relations = []
            for i, (a, b) in enumerate(((self.a, self.b), (self.b, self.c))):
                length = rng.randint(2, 16)
                left, right = rng.randrange(25 - length), rng.randrange(25 - length)
                relations.append(Equivalence(a, Interval(left, left + length), b, Interval(right, right + length),
                                             rng.choice((False, True)), str(i)))
            vertices = {(source, base) for source in required for base in range(24)}
            adjacent = {v: set() for v in vertices}
            for r in relations:
                for offset in range(r.left.length):
                    a = (r.left_source, r.left.start + offset)
                    b = (r.right_source, r.right.end - 1 - offset if r.reverse else r.right.start + offset)
                    adjacent[a].add(b); adjacent[b].add(a)
            components = []
            while vertices:
                todo, component = [min(vertices)], set()
                while todo:
                    vertex = todo.pop()
                    if vertex in component:
                        continue
                    component.add(vertex)
                    todo.extend(adjacent[vertex] - component)
                vertices -= component
                components.append(component)
            selected = [(source, Interval(a := rng.randrange(20), rng.randint(a + 1, 24))) for source in required]
            chosen = {(source, base) for source, interval in selected for base in range(interval.start, interval.end)}
            expected_covered = {v for c in components if c & chosen for v in c}
            expected_score = sum(bool(c & chosen) for c in components)
            expected_duplicate = any(len(c & chosen) > 1 for c in components)
            model = CoverageModel(required, relations)
            actual, duplicate, missing = model.assess(selected)
            missing_bases = {(source, base) for source, intervals in missing for i in intervals for base in range(i.start, i.end)}
            with self.subTest(trial=trial):
                self.assertEqual(model.total_bp, len(components))
                self.assertEqual(actual, expected_score)
                self.assertEqual(duplicate, expected_duplicate)
                self.assertEqual(missing_bases, set(adjacent) - expected_covered)


if __name__ == "__main__":
    unittest.main()
