import random
import unittest
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_query_windows import (QueryWindow, WindowPolicy,
                                                  plan_query_windows, project_window_paf)
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, merged_intervals


class QueryWindowTests(unittest.TestCase):
    def policy(self):
        return WindowPolicy(trigger_query_bases=1000, trigger_longest_bases=500,
                            core_bases=200, context_bases=10, minimum_uncovered_bases=5)

    def test_small_requests_keep_native_path(self):
        self.assertIsNone(plan_query_windows({"a": 200}, {"a": [Interval(10, 20)]}, policy=self.policy()))
        self.assertIsNone(plan_query_windows({"a": 1000}, {"a": [Interval(10, 14)]}, policy=self.policy()))
        self.assertIsNone(plan_query_windows({}, {}, policy=self.policy()))

    def test_total_size_also_triggers_with_no_long_source(self):
        sizes = {key: 400 for key in "abc"}
        windows = plan_query_windows(sizes, {key: [Interval(10, 20)] for key in sizes}, policy=self.policy())
        self.assertEqual(len(windows), 3)
        self.assertTrue(all(w.start == 0 and w.end == 30 for w in windows))

    def test_full_uncovered_source_has_bounded_context_and_retains_last_base(self):
        windows = plan_query_windows({"a": 1001}, {"a": [Interval(0, 1001)]}, policy=self.policy())
        self.assertEqual(len(windows), 6)
        self.assertTrue(all(w.length <= 220 for w in windows))
        self.assertEqual(windows[-1].cores, ((1000, 1001),))
        self.assertEqual(merged_intervals(Interval(*c) for w in windows for c in w.cores), (Interval(0, 1001),))
        self.assertEqual(len({w.window_id for w in windows}), len(windows))

    def test_nearby_holes_share_context_without_claiming_covered_gap(self):
        windows = plan_query_windows({"a": 1000}, {"a": [Interval(50, 60), Interval(70, 80)]}, policy=self.policy())
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].cores, ((50, 60), (70, 80)))
        self.assertEqual((windows[0].start, windows[0].end), (40, 90))

    def test_randomized_coverage_and_order_invariance(self):
        rng = random.Random(21)
        for _ in range(100):
            holes = [Interval(a, a + rng.randint(1, 100)) for a in sorted(rng.sample(range(900), 30))]
            a = plan_query_windows({"x": 1000}, {"x": holes}, policy=self.policy())
            b = plan_query_windows({"x": 1000}, {"x": list(reversed(holes))}, policy=self.policy())
            self.assertEqual(a, b)
            expected = tuple(i for i in merged_intervals(holes) if i.length >= 5)
            self.assertEqual(merged_intervals(Interval(*c) for w in a for c in w.cores), expected)
            self.assertTrue(all(w.length <= 220 for w in a))

    def test_invalid_geometry_fails_closed(self):
        with self.assertRaises(Q0EvidenceError):
            plan_query_windows({}, {"x": [Interval(1, 5)]}, policy=self.policy())
        with self.assertRaises(Q0EvidenceError):
            plan_query_windows({"x": 5}, {"x": [Interval(1, 6)]}, policy=self.policy())
        for kwargs in ({"core_bases": 0}, {"context_bases": -1}, {"trigger_query_bases": True}):
            with self.assertRaises(Q0EvidenceError): WindowPolicy(**kwargs)
        with self.assertRaises(Q0EvidenceError): QueryWindow("x", 20, 0, 10, ((9, 11),))


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.window = QueryWindow("source-part", 1000, 100, 140, ((110, 120),))
        self.windows = {self.window.window_id: self.window}
        self.targets = {"target": 2000, "source-part": 1000}

    def line(self, strand="+", qs=0, qe=40, cigar="40M", target="target", qlen=40):
        tspan = qe - qs
        return f"{self.window.window_id}\t{qlen}\t{qs}\t{qe}\t{strand}\t{target}\t{self.targets[target]}\t200\t{200+tspan}\t0\t{tspan}\t60\tcg:Z:{cigar}"

    def project(self, line):
        return project_window_paf(line, self.windows, self.targets, artifact="raw.paf", line_number=1)

    def test_both_strands_project_without_reversing_forward_coordinates(self):
        for strand in ("+", "-"):
            result = self.project(self.line(strand=strand))
            hit = parse_paf_line(result, artifact="result.paf", line_number=1)
            self.assertEqual((hit.query_name, hit.query_length, hit.query), ("source-part", 1000, Interval(100, 140)))
            self.assertEqual(hit.strand, strand)
            self.assertEqual(hit.target, Interval(200, 240))
            self.assertIn("qw:Z:" + self.window.window_id, hit.tags)

    def test_context_only_and_original_self_hits_are_not_donors(self):
        self.assertIsNone(self.project(self.line(qs=0, qe=5, cigar="5M")))
        self.assertIsNone(self.project(self.line(target="source-part")))
        self.assertIsNone(self.project(self.line(cigar="10M10I10D20M")))

    def test_input_drift_or_double_projection_fails(self):
        for line in (self.line(qlen=41), self.line().replace(self.window.window_id, "unknown"),
                     self.line() + "\tqw:Z:already", self.line(cigar="41M")):
            with self.assertRaises(Q0EvidenceError): self.project(line)


class RealWindowMappingTests(unittest.TestCase):
    def test_cross_source_core_evidence_survives_both_strands_and_tile_edges(self):
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from server.tools.lgz_core.common import write_fasta
        mapper = shutil.which("minimap2")
        if mapper is None:
            self.skipTest("requires minimap2")
        rng = random.Random(20261121)
        source = "".join(rng.choices("ACGT", k=30000))
        cores = [Interval(9000, 12000)]
        windows = plan_query_windows({"source": len(source)}, {"source": cores},
            policy=WindowPolicy(trigger_query_bases=1, core_bases=1000, context_bases=500))
        by_id = {w.window_id: w for w in windows}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for strand in ("+", "-"):
                target = source[8500:12500]
                if strand == "-": target = target.translate(str.maketrans("ACGT", "TGCA"))[::-1]
                write_fasta(root / "target.fa", [("source", source), ("other", target)])
                write_fasta(root / "whole.fa", [("source", source)])
                write_fasta(root / "windows.fa", [(w.window_id, source[w.start:w.end]) for w in windows])
                found = []
                for mode in ("whole", "windows"):
                    completed = subprocess.run([mapper, "-c", "-x", "asm10", "-D", "-P", "--dual=yes",
                        "--no-long-join", "-t", "1", str(root / "target.fa"), str(root / (mode + ".fa"))],
                        text=True, capture_output=True, check=True)
                    hits = []
                    for number, raw in enumerate(completed.stdout.splitlines(), 1):
                        line = (project_window_paf(raw, by_id, {"source": len(source), "other": len(target)},
                                artifact="raw", line_number=number) if mode == "windows" else raw)
                        if line:
                            hit = parse_paf_line(line, artifact=mode, line_number=number)
                            if hit.target_name == "other":
                                self.assertEqual(hit.strand, strand)
                                hits.extend(overlap for block in hit.aligned_blocks() for core in cores
                                            if (overlap := block.query.intersection(core)) is not None)
                    found.append(merged_intervals(hits))
                self.assertEqual(found[0], tuple(cores))
                self.assertEqual(found[1], found[0])


if __name__ == "__main__": unittest.main()
