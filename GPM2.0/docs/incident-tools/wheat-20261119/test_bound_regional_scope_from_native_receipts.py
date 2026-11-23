import importlib.util
from pathlib import Path
import random
import unittest
from lgz_core.q0_query_windows import WindowPolicy,plan_query_windows
from lgz_core.q0_sources import Interval
p=Path(__file__).with_name('bound_regional_scope_from_native_receipts.py')
spec=importlib.util.spec_from_file_location('scope_bound',p)
bound=importlib.util.module_from_spec(spec);spec.loader.exec_module(bound)


class NativeScopeBoundTests(unittest.TestCase):
    def test_bound_dominates_real_window_planning_for_5000_geometries(self):
        policy=WindowPolicy(core_bases=100000,context_bases=10000,trigger_query_bases=1,trigger_longest_bases=1,minimum_uncovered_bases=100)
        rng=random.Random(20261122)
        for length in (1,99,100,500,20000,20101,40000,100000,150000,1000000):
            cases=[(Interval(0,length),)]
            cases.append(tuple(Interval(start,min(length,start+100)) for start in range(0,length,20101)))
            for _ in range(500):
                cases.append(tuple(Interval(a,b) for a,b in (sorted(rng.sample(range(length+1),2)) for _ in range(20))))
            for holes in cases:
                windows=plan_query_windows({'part':length},{'part':holes},policy=policy) or ()
                self.assertLessEqual(len(windows),bound.window_bound(length,policy),(length,holes))

    def test_invalid_lengths_fail_and_shorter_than_minimum_cannot_map(self):
        policy=WindowPolicy(minimum_uncovered_bases=100)
        for length in (True,0,-1,1.0):
            with self.assertRaises(ValueError):bound.window_bound(length,policy)
        self.assertEqual(bound.window_bound(99,policy),0)


if __name__=='__main__':unittest.main()
