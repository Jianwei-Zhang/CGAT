from collections import defaultdict
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'server/tools'))
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import Interval,merged_intervals
spec=importlib.util.spec_from_file_location('global_seed_probe',Path(__file__).with_name('probe_global_seed_controls.py'))
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


def hit(qs,qe,ts,te,strand='+'):
    n=qe-qs
    return parse_paf_line(f'q\t20000\t{qs}\t{qe}\t{strand}\tt\t20000\t{ts}\t{te}\t{n}\t{n}\t0\tcg:Z:{n}M',artifact='test.paf',line_number=1)


class CoordinateRetentionTests(unittest.TestCase):
    def test_split_hits_retain_exact_long_baseline_on_both_strands(self):
        for strand in ('+','-'):
            baseline=defaultdict(list);candidate=defaultdict(list)
            probe.add_frames(baseline,hit(0,10000,100,10100,strand),10000,Interval)
            fragments=[(0,5000,100,5100),(5000,10000,5100,10100)] if strand=='+' else [(5000,10000,100,5100),(0,5000,5100,10100)]
            for row in fragments:probe.add_frames(candidate,hit(*row,strand),100,Interval)
            result=probe.retention(baseline,candidate,merged_intervals)
            self.assertEqual(result['retained_paired_coordinate_bp'],10000);self.assertEqual(result['retention'],1)

    def test_query_coverage_alone_cannot_hide_a_changed_target_coordinate(self):
        baseline=defaultdict(list);candidate=defaultdict(list)
        probe.add_frames(baseline,hit(0,10000,100,10100),10000,Interval)
        probe.add_frames(candidate,hit(0,10000,101,10101),100,Interval)
        self.assertEqual(probe.retention(baseline,candidate,merged_intervals)['retention'],0)

    def test_absent_long_baseline_is_not_reported_as_perfect_retention(self):
        self.assertIsNone(probe.retention({}, {},merged_intervals)['retention'])


if __name__=='__main__':unittest.main()
