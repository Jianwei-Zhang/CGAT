"""Grammar/span equivalence when removing CIGAR reconstruction and repeat int parsing."""
import random
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.tools import run_orchestration as contract
from server.tools.lgz_core.common import sha256_bytes, stable_id
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_sources import Q0EvidenceError


PATTERN = re.compile(r"([1-9][0-9]*)([MIDN=X])")


def previous_spans(text):
    tokens = PATTERN.findall(text)
    if not tokens or "".join(length + op for length, op in tokens) != text:
        return None
    return (sum(int(length) for length, op in tokens if op in "MI=X"),
            sum(int(length) for length, op in tokens if op in "MDN=X"))


def paf(text, spans):
    query, target = spans
    return (f"q\t{query + 10}\t5\t{query + 5}\t-\tt\t{target + 20}\t7\t{target + 7}"
            f"\t0\t{query + target}\t255\tcg:Z:{text}")


class CigarScanTests(unittest.TestCase):
    def test_random_valid_spans_and_q0_geometry_record_identity_are_unchanged(self):
        rng = random.Random(512)
        for number in range(1200):
            text = "100M" + "".join(str(rng.randrange(1, 10000)) + rng.choice("MIDN=X")
                                    for _ in range(rng.randrange(60)))
            spans = previous_spans(text)
            self.assertEqual(contract._paf_cigar_spans(text), spans)
            line = paf(text, spans)
            hit = parse_paf_line(line, artifact="source.paf", line_number=number + 1)
            self.assertEqual(hit.cigar, tuple((int(length), op) for length, op in PATTERN.findall(text)))
            self.assertEqual((hit.query.length, hit.target.length), spans)
            record = sha256_bytes(line.encode("utf-8"))
            self.assertEqual(hit.record_sha256, record)
            self.assertEqual(hit.evidence_id, stable_id("q0-paf", ["source.paf", number + 1, record]))

    def test_full_coverage_rejects_the_same_random_malformed_tokens(self):
        rng = random.Random(227)
        for _ in range(8000):
            text = "".join(rng.choice("0123456789MIDN=XHSPQ? \u00b2\u0661\x00")
                           for _ in range(rng.randrange(70)))
            self.assertEqual(contract._paf_cigar_spans(text), previous_spans(text), repr(text))

    def test_gaps_only_spans_zero_query_and_each_supported_opcode(self):
        for text in ("12N", "12I", "12D", "12=", "12X", "12M", "1I2D3N4=5X6M"):
            with self.subTest(text=text):
                self.assertEqual(contract._paf_cigar_spans(text), previous_spans(text))
        self.assertEqual(contract._paf_cigar_spans("12N"), (0, 12))
        self.assertEqual(contract._paf_cigar_spans("12I"), (12, 0))

    def test_leading_zero_unknown_opcode_or_uncovered_characters_are_never_accepted(self):
        for text in ("", "0M", "01M", "10M0I", "10M01I", "?10M", "10M?", "10M?20M",
                     "1.5M", "-10M", "+10M", "10S", "10H", "10P", "10B", "\u0661M", "1\u0661M"):
            with self.subTest(text=text):
                self.assertIsNone(contract._paf_cigar_spans(text))
                with self.assertRaises(Q0EvidenceError):
                    parse_paf_line(paf(text, (10, 10)), artifact="source.paf", line_number=1)

    def test_long_cigar_keeps_the_complete_native_geometry_and_q0_tokens(self):
        text = "100M" + "1M1I1D1N1=1X" * 12000
        spans = previous_spans(text)
        self.assertEqual(contract._paf_cigar_spans(text), spans)
        line = paf(text, spans)
        hit = parse_paf_line(line, artifact="complete.paf", line_number=1)
        self.assertEqual(len(hit.cigar), 72001)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.paf"; path.write_text(line + "\n")
            self.assertEqual(contract.validate_paf(path, require_cigar=True).record_count, 1)
            path.write_text(line.replace("\tcg:Z:", "\tcg:Z:?") + "\n")
            with self.assertRaisesRegex(contract.OrchestrationContractError, "invalid CIGAR"):
                contract.validate_paf(path, require_cigar=True)

    def test_grammar_is_checked_before_unbounded_integer_conversion(self):
        text = "9" * 5000 + "M?"
        self.assertIsNone(previous_spans(text))
        self.assertIsNone(contract._paf_cigar_spans(text))
        if hasattr(sys, "get_int_max_str_digits") and sys.get_int_max_str_digits():
            valid = "9" * max(5000, sys.get_int_max_str_digits() + 1) + "M"
            for method in (previous_spans, contract._paf_cigar_spans):
                with self.assertRaises(ValueError):method(valid)

    def test_span_mismatch_still_fails_native_and_q0_validation(self):
        line = paf("9M", (10, 10))
        with self.assertRaisesRegex(Q0EvidenceError, "CIGAR span"):
            parse_paf_line(line, artifact="bad.paf", line_number=1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.paf";path.write_text(line + "\n")
            with self.assertRaisesRegex(contract.OrchestrationContractError, "CIGAR span mismatch"):
                contract.validate_paf(path, require_cigar=True)


if __name__ == "__main__":unittest.main()
