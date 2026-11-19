import tempfile
import unittest
from pathlib import Path

import self_paf_comparison as compare


def row(q="q", t="t", qs=0, qe=10, ts=20, te=30, strand="+", cigar="10M", kind="S", qlen=1000):
    return "\t".join(map(str, (q, qlen, qs, qe, strand, t, 1000, ts, te, 10, 10, 0))) + f"\ttp:A:{kind}\tcg:Z:{cigar}\n"


class SelfEvidenceComparisonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def load(self, text, name="a.paf", step=1):
        path = self.root / name; path.write_text(text)
        return compare.read_evidence(path, step)

    def report(self, left, right, step=1):
        return compare.compare_evidence(self.load(left, step=step),
            self.load(right, "b.paf", step), step)

    def test_secondary_zero_mapq_hits_are_not_dropped(self):
        r = self.report(row(kind="P") + row(t="t2"), row(kind="P"))
        self.assertEqual(r["baseline"]["hit_types"], {"P": 1, "S": 1})
        self.assertEqual(r["missing_pairs"], 1)
        self.assertEqual(r["position_support"]["0"]["missing_baseline_placements"], 10)
        self.assertFalse(r["primary_or_mapq_filter_applied"])

    def test_one_surviving_repeat_placement_cannot_hide_another_loss(self):
        r = self.report(row() + row(ts=50, te=60), row())
        for tolerance in ("0", "100", "1000"):
            self.assertEqual(r["position_support"][tolerance]["matched"], 10)
            self.assertEqual(r["position_support"][tolerance]["missing_baseline_placements"], 10)
        self.assertEqual(r["pairs"][0]["query_aligned_coverage"]["missing"], 0)
        self.assertEqual(r["pairs"][0]["target_aligned_coverage"]["missing"], 10)

    def test_extra_repeat_placements_are_reported_symmetrically(self):
        r = self.report(row(), row() + row(ts=50, te=60))
        self.assertEqual(r["position_support"]["100"]["extra_candidate_placements"], 10)

    def test_identical_duplicate_rows_are_coalesced_but_counted(self):
        r = self.report(row() + row(), row())
        self.assertEqual(r["baseline"]["paf_rows"], 2)
        self.assertEqual(r["baseline"]["duplicate_sampled_placement_observations"], 10)
        self.assertEqual(r["position_support"]["0"]["missing_baseline_placements"], 0)

    def test_reverse_strand_projection(self):
        e = self.load(row(qs=10, qe=20, ts=100, te=110, strand="-"))
        self.assertEqual(e.anchors[("q", "t", "-", 10)], {109})
        self.assertEqual(e.anchors[("q", "t", "-", 19)], {100})

    def test_forward_and_reverse_indels(self):
        a = self.load(row(qe=12, ts=100, te=111, cigar="3M2I4M1D3M"))
        self.assertNotIn(("q", "t", "+", 3), a.anchors)
        self.assertEqual(a.anchors[("q", "t", "+", 5)], {103})
        self.assertEqual(a.anchors[("q", "t", "+", 9)], {108})
        b = self.load(row(qe=12, ts=100, te=111, strand="-", cigar="3M2I4M1D3M"))
        self.assertEqual(b.anchors[("q", "t", "-", 6)], {103})
        self.assertEqual(b.anchors[("q", "t", "-", 0)], {110})

    def test_strand_or_target_change_is_not_positional_support(self):
        for changed in (row(strand="-"), row(t="t2")):
            r = self.report(row(), changed)
            self.assertEqual(r["position_support"]["1000"]["matched"], 0)
            self.assertEqual(r["missing_pairs"], 1)
            self.assertEqual(r["extra_pairs"], 1)

    def test_short_unsampled_coverage_loss_is_still_reported(self):
        r = self.report(row(qs=2, qe=8, ts=12, te=18, cigar="6M"),
            row(qs=2, qe=4, ts=12, te=14, cigar="2M") + row(qs=6, qe=8, ts=16, te=18, cigar="2M"), 1000)
        self.assertEqual(r["baseline"]["sampled_distinct_placements"], 0)
        self.assertEqual(r["pairs"][0]["query_aligned_coverage"]["missing"], 2)

    def test_exact_tolerance_boundary_and_one_to_one(self):
        self.assertEqual(compare.one_to_one_support([0, 10], [9, 20], 10), 2)
        self.assertEqual(compare.one_to_one_support([0, 10], [9], 10), 1)
        self.assertEqual(compare.one_to_one_support([0], [10], 9), 0)
        self.assertEqual(compare.one_to_one_support([0, 0], [0], 0), 1)
        with self.assertRaises(ValueError): compare.one_to_one_support([], [], -1)

    def test_union_and_intersection(self):
        a = compare.union([(2, 5), (4, 6), (0, 2), (8, 10)])
        self.assertEqual(a, [(0, 6), (8, 10)])
        self.assertEqual(compare.intersection_length(a, [(1, 9)]), 6)

    def test_empty_baseline_has_no_fabricated_agreement_fraction(self):
        r = self.report("", row())
        self.assertIsNone(r["position_support"]["0"]["missing_fraction"])
        self.assertEqual(r["position_support"]["0"]["extra_fraction"], 1)

    def test_invalid_rows_or_geometry_are_rejected(self):
        for text in ("bad\n", row(strand="?"), row(cigar="9M"), row(cigar="10Mbad"),
                     row().replace("cg:Z:10M", ""), row(qe=0)):
            with self.subTest(text=text):
                with self.assertRaises(ValueError): self.load(text)

    def test_length_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lengths disagree"):
            self.report(row(), row(qlen=999))
        with self.assertRaisesRegex(ValueError, "inconsistent sequence length"):
            self.load(row() + row(qlen=999))

    def test_sampling_resolution_cannot_be_mislabelled(self):
        a = self.load(row(), step=10)
        with self.assertRaisesRegex(ValueError, "sampling steps disagree"):
            compare.compare_evidence(a, a, step=1)
        with self.assertRaises(ValueError): self.load(row(), step=0)


if __name__ == "__main__":
    unittest.main()
