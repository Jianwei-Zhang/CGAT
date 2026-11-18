"""Exact-equivalence coverage for the long-contig telomere prefilter."""
import itertools
import re
import unittest
from unittest import mock

from server.tools import lgz_prepare_inputs as prepare


def legacy(sequence, rules, threshold):
    for rule in rules:
        motif = str(rule["motif"])
        minimum = int(rule["donor_min_repeat"])
        for match in re.finditer(f"(?:{re.escape(motif)}){{{minimum},}}", sequence):
            if match.end() - match.start() >= threshold:
                return True
    return False


def rule(motif, minimum=20):
    return {"motif": motif, "donor_min_repeat": minimum}


class TelomereSignalScanTests(unittest.TestCase):
    def assert_equivalent(self, sequence, rules, threshold=500):
        expected = legacy(sequence, rules, threshold)
        with mock.patch.object(prepare, "MIN_TELOMERE_BP", threshold):
            self.assertEqual(prepare.has_telomere_signal(sequence, rules), expected)

    def test_real_threshold_and_reverse_complement_rules(self):
        rules = [rule(m) for m in ("TTTAGGG", "CCCTAAA", "TTAGGG", "CCCTAA", "TTAGG", "CCTAA")]
        for motif in [r["motif"] for r in rules]:
            for copies in (0, 19, 20, 70, 71, 72, 99, 100, 101):
                with self.subTest(motif=motif, copies=copies):
                    self.assert_equivalent("ACGT" * 31 + motif * copies + "ACGT" * 31, rules)
        for length in (499, 500, 501):
            self.assert_equivalent("A" * length, [rule("A")])

    def test_empty_custom_and_case_sensitive_rules(self):
        for sequence in ("", "A" * 501, "a" * 501, "A.C" * 200, "[A]" * 200):
            for rules in ([], [rule("")], [rule("A", 0)], [rule("A", -1)],
                          [rule("A.C")], [rule("[A]")], [rule("A"), rule("a")]):
                self.assert_equivalent(sequence, rules)
        for threshold in (0, -1):
            self.assert_equivalent("AC", [rule("A", 0)], threshold)

    def test_overlap_requires_authoritative_regex(self):
        sequence = "ABABAABAABA"
        self.assertIn("ABA" * 3, sequence)
        self.assertFalse(legacy(sequence, [rule("ABA", 1)], 9))
        self.assert_equivalent(sequence, [rule("ABA", 1)], 9)

    def test_large_custom_rule_and_short_sequence(self):
        self.assert_equivalent("A" * 10, [rule("A", 100_000_000)])
        self.assert_equivalent("AC" * 3000, [rule("AC", 2500)])
        self.assert_equivalent("AC" * 3000, [rule("AG", 2500)])
        self.assert_equivalent("A" * 6000, [rule("A" * 5000, 1)])

    def test_invalid_repeat_preserves_regex_error(self):
        with self.assertRaises(OverflowError):
            prepare.has_telomere_signal("", [rule("A", 10**100)])

    def test_negative_fast_path_does_not_iterate_regex(self):
        pattern = mock.Mock()
        with mock.patch.object(prepare.re, "compile", return_value=pattern):
            self.assertFalse(prepare.has_telomere_signal("ACGT" * 1000, [rule("TTTAGGG")]))
        pattern.finditer.assert_not_called()

    def test_exhaustive_small_sequences(self):
        # Self-overlapping motifs and zero repeats exercise legacy regex details.
        for threshold in (1, 4, 7):
            with mock.patch.object(prepare, "MIN_TELOMERE_BP", threshold):
                for length in range(10):
                    for bases in itertools.product("AC", repeat=length):
                        sequence = "".join(bases)
                        for motif in ("A", "AC", "ACA", "AAC", "AAAA"):
                            for minimum in (0, 1, 2, 3):
                                rules = [rule(motif, minimum)]
                                self.assertEqual(prepare.has_telomere_signal(sequence, rules),
                                                 legacy(sequence, rules, threshold),
                                                 (sequence, motif, minimum, threshold))


if __name__ == "__main__":
    unittest.main()
