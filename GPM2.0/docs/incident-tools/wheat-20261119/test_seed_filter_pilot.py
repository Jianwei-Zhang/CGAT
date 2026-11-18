import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import seed_filter_pilot as pilot


class PilotMetricTests(unittest.TestCase):
    def test_union_counts_overlaps_and_empty_groups_once(self):
        self.assertEqual(pilot.union([(20, 25), (0, 10), (5, 12)]), [(0, 12), (20, 25)])
        self.assertEqual(pilot.covered({"q": [(0, 10), (5, 12)], "empty": []}), 12)
        self.assertEqual(pilot.covered({}), 0)

    def test_primary_support_requires_same_destination_and_strand(self):
        baseline = {("q", "a", "+"): [(0, 10), (5, 12)]}
        other = {("q", "a", "+"): [(6, 15)], ("q", "b", "+"): [(0, 20)],
                 ("q", "a", "-"): [(0, 20)]}
        self.assertEqual(pilot.shared_primary_support(baseline, other), 6)
        self.assertEqual(pilot.shared_primary_support(baseline, {}), 0)

    def test_secondary_records_do_not_inflate_primary_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.paf"
            path.write_text("q\t20\t0\t10\t+\ta\t100\t0\t10\t10\t10\t60\ttp:A:P\tcg:Z:10M\n"
                            "q\t20\t0\t10\t+\tb\t100\t0\t10\t10\t10\t0\ttp:A:S\tcg:Z:10M\n")
            metrics, _ = pilot.measure(path)
            self.assertEqual(metrics, {"paf_rows": 2, "query_covered_bases": 10,
                                       "primary_query_covered_bases": 10})

    def test_extract_windows_are_bound_to_full_source_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.fa"
            destination = Path(tmp) / "windows.fa"
            content = b">short\nAC\n>long\nACGTACGTACGTACGTACGT\n"
            source.write_bytes(content)
            with patch.object(pilot, "WINDOW", 5):
                rows = pilot.extract_longest(source, len(content), hashlib.sha256(content).hexdigest(), destination)
            self.assertEqual([row["start"] for row in rows], [0, 7, 15])
            self.assertEqual({row["source_name"] for row in rows}, {"long"})
            self.assertEqual(destination.read_text().splitlines()[1::2], ["ACGTA", "TACGT", "TACGT"])
            self.assertEqual(source.read_bytes(), content)

    def test_wrong_source_digest_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.fa"
            destination = Path(tmp) / "windows.fa"
            source.write_bytes(b">q\nACGTACGTACGTACGT\n")
            with patch.object(pilot, "WINDOW", 5), self.assertRaises(AssertionError):
                pilot.extract_longest(source, source.stat().st_size, "0" * 64, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
