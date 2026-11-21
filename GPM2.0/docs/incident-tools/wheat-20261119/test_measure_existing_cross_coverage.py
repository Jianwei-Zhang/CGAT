from pathlib import Path
import random
import tempfile
import json
import hashlib
import os
from unittest.mock import patch
import sys
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[3])]
import measure_existing_cross_coverage as probe
from server.tools.lgz_core.q0_alignments import parse_paf_line


class CoverageTests(unittest.TestCase):
    def test_subtract_boundaries_and_short_residuals(self):
        holes = [[0, 1000], [1100, 2100]]
        probe.subtract(holes, 1000, 1100)
        self.assertEqual(holes, [[0, 1000], [1100, 2100]])
        probe.subtract(holes, 100, 900)
        self.assertEqual(holes, [[0, 100], [900, 1000], [1100, 2100]])
        probe.subtract(holes, 950, 2001)
        self.assertEqual(holes, [[0, 100]])

    def test_incremental_subtraction_matches_base_mask(self):
        rng = random.Random(193)
        for _ in range(100):
            holes, covered = [[0, 3000]], set()
            for _ in range(40):
                a = rng.randrange(3000); b = rng.randrange(a+1, 3001)
                covered.update(range(a, b)); probe.subtract(holes, a, b)
                expected = []; start = None
                for i in range(3001):
                    if i < 3000 and i not in covered:
                        if start is None: start = i
                    elif start is not None:
                        if i-start >= 100: expected.append([start, i])
                        start = None
                self.assertEqual(holes, expected)

    def test_geometry_matches_production_both_strands(self):
        rng = random.Random(194)
        for strand in ("+", "-"):
            for _ in range(100):
                ops = [(rng.randrange(1, 100), rng.choice("MIDN=X")) for _ in range(20)]
                qlen = sum(n for n, op in ops if op in "MI=X")
                tlen = sum(n for n, op in ops if op in "MDN=X")
                cigar = "".join(f"{n}{op}" for n, op in ops)
                f = ["q", str(qlen+20), "10", str(qlen+10), strand, "t", str(tlen+40),
                     "20", str(tlen+20), "0", str(qlen+tlen), "255", "cg:Z:"+cigar]
                hit = parse_paf_line("\t".join(f), artifact="fixture", line_number=1)
                expected = [(b.query.start, b.query.end, b.target.start, b.target.end)
                            for b in hit.aligned_blocks() if b.operation in "M="]
                self.assertEqual(probe.paired_geometry(f), expected)

    def test_bad_cigar_is_rejected_even_if_low_identity(self):
        f = "q 100 0 100 + t 100 0 100 0 100 0 cg:Z:99M".split()
        with self.assertRaises(ValueError): probe.paired_geometry(f)
        f[-1] = "cg:Z:100Mgarbage"
        with self.assertRaises(ValueError): probe.paired_geometry(f)

    def test_complete_probe_binds_receipts_and_rejects_changed_paf(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); work = root/"work"; lookup = root/"lookup"; cov = root/"cov"; out = root/"out"
                for d in (work, lookup, cov, out): d.mkdir()
                def write(path, value):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(value))
                parts = {"part-a": {"dataset":"a", "contig":"q", "length":1000},
                         "part-b": {"dataset":"b", "contig":"t", "length":1000}}
                write(lookup/"source-part-lookup.json", parts)
                write(lookup/"receipt.json", {"lookup_sha256":hashlib.sha256((lookup/"source-part-lookup.json").read_bytes()).hexdigest()})
                write(cov/"summary.json", {"minimum_reference_mapq":20, "include_unavailable_mapq":False,
                      "datasets":[{"dataset":d,"partial_query_count":1,"window_total_bp_by_flank":{"0":1000}} for d in ("a","b")]})
                write(cov/"partial-coverage.json", [{"dataset":d,"contig":c,"length":1000,"uncovered":[[0,1000]]} for d,c in (("a","q"),("b","t"))])
                rel = "runs/chr_c/cross/result.paf"; f = work/rel; f.parent.mkdir(parents=True)
                f.write_text("q\t1000\t100\t200\t+\tt\t1000\t200\t300\t100\t100\t255\tcg:Z:100M\n")
                identity = {"path":rel,"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"size":f.stat().st_size}
                write(work/".run_all/checkpoints/q0-chr-c.json", {"status":"success","outputs":[identity]})
                write(work/"runs/chr_c/q0_alignment_inputs.json", {"alignments":[{"paf":rel,"query_dataset":"a","target_dataset":"b"}]})
                supp = "supp"; (work/supp).mkdir(); (work/supp/"result.paf").write_bytes(b"")
                write(work/supp/"success.json", {"outputs":[{"path":supp+"/result.paf","size":0,"sha256":hashlib.sha256(b"").hexdigest()}]})
                if corrupt: f.write_text(f.read_text().replace("255", "254"))
                args = ["probe", "--workspace",str(work), "--lookup-dir",str(lookup),"--coverage-dir",str(cov),"--completed-supplement",supp]
                old = Path.cwd()
                try:
                    os.chdir(out)
                    with patch.object(sys,"argv",args), patch("builtins.print"):
                        if corrupt:
                            with self.assertRaisesRegex(ValueError,"PAF changed"): probe.main()
                            self.assertFalse((out/"summary.json").exists())
                        else:
                            probe.main(); result=json.loads((out/"summary.json").read_text())
                            self.assertEqual(result["after"]["a"]["residual_bp"],900)
                            self.assertEqual(result["after"]["b"]["residual_bp"],900)
                            self.assertFalse(result["scientific_acceptance"])
                finally: os.chdir(old)


if __name__ == "__main__": unittest.main()
