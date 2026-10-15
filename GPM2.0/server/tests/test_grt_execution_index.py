import random
import unittest

from server.tools.grt_core.alignment_index import AlignmentCoordinateIndex, Step2MemberIndex
from server.tools import grt_step23 as engine


class AlignmentIndexTests(unittest.TestCase):
    def test_exact_ranges_and_stable_top_two_match_linear_search(self):
        rng = random.Random(2665)
        rows = []
        for i in range(1500):
            start = rng.randrange(0, 200) * 10000
            end = start + rng.randrange(1, 100) * 10000
            rows.append({"query_min": start, "query_max": end,
                         "identity": rng.choice([0.90, 0.99, 0.99]),
                         "ref_record": f"donor-{i % 7}", "line_number": i + 1})
        index, step2 = AlignmentCoordinateIndex(rows), Step2MemberIndex(rows)
        for position in [0, 10, 99990, 100000, 100010, 2000000, 4000000] + [rng.randrange(0, 3000000) for _ in range(100)]:
            with self.subTest(position=position):
                self.assertEqual(index.crossing(position), [r for r in rows if r["query_min"] <= position <= r["query_max"]])
                for window in (100000, 200000, 500000):
                    left = [r for r in rows if r["query_max"] < position and (
                        abs(r["query_min"] - position) <= window or abs(r["query_max"] - position) <= window)]
                    right = [r for r in rows if r["query_min"] > position and (
                        abs(r["query_min"] - position) <= window or abs(r["query_max"] - position) <= window)]
                    self.assertEqual(index.anchors(position, window), (left, right))
                left = sorted((r for r in rows if r["query_max"] <= position + 10),
                              key=lambda r: (-r["query_max"], -r["identity"]))[:2]
                right = sorted((r for r in rows if r["query_min"] >= position - 10),
                               key=lambda r: (r["query_min"], -r["identity"]))[:2]
                self.assertEqual(step2.anchors(position), (left, right))
                self.assertEqual(engine._step3_anchor_pairs(position, rows, index),
                                 engine._step3_anchor_pairs(position, rows))

    def test_index_keeps_near_one_sided_anchor_stop_and_boundary_ties(self):
        position = 1000050
        rows = [
            {"ref_record": "near-left", "query_min": position - 60000, "query_max": position - 50000},
            {"ref_record": "near-right", "query_min": position + 50000, "query_max": position + 60000},
            {"ref_record": "far-pair", "query_min": position - 160000, "query_max": position - 150000},
            {"ref_record": "far-pair", "query_min": position + 150000, "query_max": position + 160000},
        ]
        self.assertEqual(engine._step3_anchor_pairs(position, rows, AlignmentCoordinateIndex(rows)), [])
        self.assertEqual(AlignmentCoordinateIndex([]).crossing(1), [])
        self.assertEqual(Step2MemberIndex([]).anchors(1), ([], []))


if __name__ == "__main__":
    unittest.main()
