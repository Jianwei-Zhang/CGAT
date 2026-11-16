from pathlib import Path
import tempfile
import unittest

import benchmark_adaptive_windows as windows


class WindowProbeTests(unittest.TestCase):
    def test_core_ownership_same_span_without_gaps_or_duplicate_cores(self):
        length,start,end=289508469,100000000,150000000
        for core in (50000000,10000000,5000000):
            plan=windows.window_plan(length,start,end,core)
            self.assertEqual(plan[0]["core_start"],start)
            self.assertEqual(plan[-1]["core_end"],end)
            self.assertEqual(sum(w["core_end"]-w["core_start"] for w in plan),end-start)
            self.assertTrue(all(a["core_end"]==b["core_start"] for a,b in zip(plan,plan[1:])))
            self.assertEqual(plan[0]["query_start"],start-100000)
            self.assertEqual(plan[-1]["query_end"],end+100000)

    def test_record_edges_clip_context(self):
        plan=windows.window_plan(250,0,250,100,10)
        self.assertEqual([(w["query_start"],w["query_end"]) for w in plan],[(0,110),(90,210),(190,250)])

    def test_invalid_span_rejected(self):
        for args in ((100,0,101,50,1),(100,50,50,20,1),(100,0,100,10,10)):
            with self.assertRaises(ValueError):windows.window_plan(*args)

    def test_extract_preserves_actual_bases_with_wrapped_input(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"q.fa";p.write_bytes(b">q description\nACGT\nNNNN\nTGCA\n")
            self.assertEqual(windows.extract_span(p,2,10),b"GTNNNNTG")
            with self.assertRaises(ValueError):windows.extract_span(p,0,13)

    def test_overlap_does_not_inflate_owned_coverage(self):
        plan=windows.window_plan(250,0,250,100,10)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.paf"
            p.write_text("".join(f'{w["name"]}\t{w["query_end"]-w["query_start"]}\t0\t{w["query_end"]-w["query_start"]}\t+\tt\t300\t0\t100\t100\t100\t60\n' for w in plan))
            r=windows.owned_coverage(p,plan,0,250)["probe"]
            self.assertEqual(r["covered"],250)
            self.assertEqual(r["targets"],{"t":250})

    def test_flank_only_alignment_does_not_cover_the_core(self):
        plan=windows.window_plan(300,100,200,100,10)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.paf";p.write_text("w0000\t120\t0\t10\t+\tt\t300\t0\t10\t10\t10\t60\n")
            self.assertEqual(windows.owned_coverage(p,plan,100,200)["probe"]["covered"],0)


if __name__=="__main__":unittest.main()
