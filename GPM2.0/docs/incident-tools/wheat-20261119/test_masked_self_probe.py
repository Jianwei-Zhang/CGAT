import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import masked_self_probe as probe


class MaskedSelfProbeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "source.fa"; self.output = self.root / "masked.fa"
        self.sequence = b"ACGT" * 8
        self.source.write_bytes(b">q full original header\n" + self.sequence[:16] + b"\n" + self.sequence[16:] + b"\n")
        self.windows = [(0, 4), (12, 16), (28, 32)]
        self.report = {"baseline": {"sampled_distinct_placements": 1000},
            "position_support": {"100": {"missing_baseline_placements": 1, "extra_candidate_placements": 1}},
            "pairs": [{"candidate_present": True, "query_aligned_coverage": {"baseline": 100000, "missing": 50}}]}

    def test_one_mb_cli_option_is_passed_to_the_probe(self):
        args = ["probe", "--work", "/work", "--manifest", "/manifest", "--batch-index", "3",
                "--candidate-dir", "/candidate", "--output", "/output", "--window-bases", "1000000"]
        with patch.object(probe.sys, "argv", args), patch.object(probe, "execute") as execute, \
             patch.object(probe.signal, "signal"):
            probe.main()
        self.assertEqual(execute.call_args.kwargs, {"window_bases": 1000000})

    def test_mask_preserves_name_length_and_exact_window_bases(self):
        original = self.source.read_bytes()
        probe.write_masked_query(self.source, self.output, "q", 32, self.windows)
        header, sequence = self.output.read_bytes().splitlines()
        self.assertEqual(header, b">q full original header")
        self.assertEqual(len(sequence), 32)
        for index, base in enumerate(sequence):
            inside = any(lo <= index < hi for lo, hi in self.windows)
            self.assertEqual(base, self.sequence[index] if inside else ord("N"))
        self.assertEqual(original, self.source.read_bytes())

    def test_fixed_windows_are_disjoint_and_cover_both_ends(self):
        windows = probe.fixed_windows(32, 5)
        self.assertEqual(windows, [(0, 5), (14, 19), (27, 32)])
        self.assertEqual(sum(hi - lo for lo, hi in windows), 15)
        with self.assertRaises(ValueError): probe.fixed_windows(29, 5)

    def test_changed_name_length_or_record_count_is_rejected(self):
        for name, length in (("other", 32), ("q", 31)):
            with self.assertRaises(ValueError):
                probe.write_masked_query(self.source, self.output, name, length, self.windows)
        self.source.write_bytes(self.source.read_bytes() + b">second\nACGT\n")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            probe.write_masked_query(self.source, self.output, "q", 32, self.windows)
        self.assertFalse(self.output.exists())

    def test_overlapping_invalid_or_existing_output_is_refused(self):
        for windows in ([(0, 10), (5, 15)], [(0, 33)], [(-1, 5)], [(2, 2)]):
            with self.assertRaises(ValueError):
                probe.write_masked_query(self.source, self.output, "q", 32, windows)
        self.output.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "already exists"):
            probe.write_masked_query(self.source, self.output, "q", 32, self.windows)
        self.assertEqual(self.output.read_text(), "preserve")

    def test_passing_local_quality_never_adopts_or_guarantees_whole_query(self):
        result = probe.window_quality(self.report)
        self.assertTrue(result["passes_proposed_window_limits"])
        self.assertFalse(result["candidate_adopted"])
        self.assertFalse(result["whole_query_agreement_guaranteed"])

    def test_loss_and_extra_positions_are_both_checked(self):
        for field, reason in (("missing_baseline_placements", "missing_positions"),
                              ("extra_candidate_placements", "extra_positions")):
            report = copy.deepcopy(self.report); report["position_support"]["100"][field] = 3
            self.assertIn(reason, probe.window_quality(report)["reasons"])

    def test_low_evidence_and_coverage_loss_are_rejected(self):
        report = copy.deepcopy(self.report); report["baseline"]["sampled_distinct_placements"] = 0
        self.assertIn("insufficient_baseline_placements", probe.window_quality(report)["reasons"])
        report = copy.deepcopy(self.report); report["pairs"][0]["query_aligned_coverage"]["missing"] = 101
        self.assertIn("pair_query_coverage_loss", probe.window_quality(report)["reasons"])

    def test_missing_significant_pair_is_not_hidden_by_other_pairs(self):
        report = copy.deepcopy(self.report)
        report["pairs"].append({"candidate_present": False, "query_aligned_coverage": {"baseline": 10000, "missing": 10000}})
        self.assertIn("significant_pair_missing", probe.window_quality(report)["reasons"])


if __name__ == "__main__":
    unittest.main()
