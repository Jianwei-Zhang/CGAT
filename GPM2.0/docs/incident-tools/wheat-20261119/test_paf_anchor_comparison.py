import tempfile
import unittest
from pathlib import Path
from paf_anchor_comparison import anchors, compare


def paf(strand="+", target_start=100, cigar="5M2I3M2D2M", primary=True):
    return (f"q\t12\t0\t12\t{strand}\tt\t1000\t{target_start}\t{target_start + 12}"
            f"\t10\t14\t60\ttp:A:{'P' if primary else 'S'}\tcg:Z:{cigar}\n")


class AnchorTests(unittest.TestCase):
    def test_forward_projection_skips_query_insertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "paf"; p.write_text(paf())
            result = anchors(p, 1)
            self.assertNotIn(("q", 5), result)
            self.assertNotIn(("q", 6), result)
            self.assertEqual(result[("q", 7)], {("t", "+", 105)})
            self.assertEqual(result[("q", 10)], {("t", "+", 110)})
            self.assertEqual(len(result), 10)

    def test_reverse_projection_is_target_forward(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "paf"; p.write_text(paf("-"))
            result = anchors(p, 1)
            self.assertEqual(result[("q", 11)], {("t", "-", 100)})
            self.assertEqual(result[("q", 0)], {("t", "-", 111)})
            self.assertNotIn(("q", 5), result)
            self.assertNotIn(("q", 6), result)

    def test_tolerance_does_not_hide_shifted_or_opposite_strand_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.write_text(paf()); b.write_text(paf(target_start=300))
            report = compare(a, b, 1)
            self.assertEqual(report["baseline_anchors_supported_within_100bp"], 0)
            self.assertEqual(report["baseline_anchors_supported_within_1000bp"], 10)
            b.write_text(paf("-"))
            self.assertEqual(compare(a, b, 1)["baseline_anchors_supported_within_1000bp"], 0)

    def test_secondary_is_excluded_and_extra_primary_locations_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.write_text(paf()); b.write_text(paf() + paf(target_start=300, primary=False))
            self.assertEqual(compare(a, b, 1)["ambiguous_candidate_anchors"], 0)
            b.write_text(paf() + paf(target_start=300))
            report = compare(a, b, 1)
            self.assertEqual(report["ambiguous_candidate_anchors"], 10)
            self.assertEqual(report["candidate_anchors_with_extra_positions_beyond_100bp"], 10)

    def test_invalid_cigar_span_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "paf"; p.write_text(paf(cigar="11M"))
            with self.assertRaises(ValueError):
                anchors(p)


if __name__ == "__main__":
    unittest.main()
