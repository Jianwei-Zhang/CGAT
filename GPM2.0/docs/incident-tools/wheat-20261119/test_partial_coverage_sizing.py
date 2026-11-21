"""The sizing probe must preserve the actual >=100bp coverage predicate."""
from pathlib import Path
import importlib.util
import random
import sys
import unittest
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from server.tools.lgz_core.q0_alignments import parse_paf_line
spec = importlib.util.spec_from_file_location("partial_coverage_sizing", HERE / "partial_coverage_sizing.py")
diag = importlib.util.module_from_spec(spec); spec.loader.exec_module(diag)


class CoverageSizingTests(unittest.TestCase):
    def test_compact_intervals_match_production_geometry_for_both_strands(self):
        rng = random.Random(20261121)
        cases = 0
        for _ in range(1000):
            ops = [(rng.randrange(1, 201), rng.choice("MIDN=X")) for _ in range(rng.randrange(1, 40))]
            qspan = sum(n for n, op in ops if op in "MI=X")
            tspan = sum(n for n, op in ops if op in "MDN=X")
            if not qspan or not tspan: continue
            cigar = "".join(str(n) + op for n, op in ops)
            for strand in ("+", "-"):
                line = f"q\t{qspan+20}\t7\t{qspan+7}\t{strand}\tt\t{tspan+30}\t11\t{tspan+11}\t0\t{qspan+tspan}\t60\tcg:Z:{cigar}"
                hit = parse_paf_line(line, artifact="control.paf", line_number=1)
                native = [[b.query.start, b.query.end] for b in hit.aligned_blocks() if b.operation != "X"]
                compact, used = diag.blocks(cigar, 7, qspan+7, 11, tspan+11, strand)
                self.assertEqual(used, any(True for _ in hit.aligned_blocks()))
                self.assertEqual(diag.missing(qspan+20, compact), diag.missing(qspan+20, native))
                cases += 1
        self.assertGreater(cases, 1800)

    def test_no_indel_hull_is_treated_as_covered(self):
        rows, _ = diag.blocks("100M100I100D100M", 0, 300, 0, 300, "+")
        self.assertEqual(diag.missing(300, rows), [[100, 200]])
        rows, used = diag.blocks("300X", 0, 300, 0, 300, "+")
        self.assertTrue(used)
        self.assertEqual(diag.missing(300, rows), [[0, 300]])

    def test_malformed_cigar_is_not_sized(self):
        for cigar in ("100Mgarbage", "0M", "101M", "100S", ""):
            with self.assertRaises(ValueError): diag.blocks(cigar, 0, 100, 0, 100, "+")


if __name__ == "__main__": unittest.main()
