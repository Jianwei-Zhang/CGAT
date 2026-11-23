import unittest
from unittest.mock import patch
from types import SimpleNamespace

from lgz_core.q0_query_windows import QueryWindow
from lgz_core.q0_sources import Interval
from replay_regional_matched_reciprocal import locus_groups, ranked_matches


class TestMatchedReciprocal(unittest.TestCase):
    def test_full_precedes_partial_and_completed_seed_excluded(self):
        q=[QueryWindow(str(i),100,0,100,((0,100),)) for i in range(1189)]
        raw=[{'raw_receipt':str(i),'cpu_seconds':i} for i in range(1189)]
        trace={'raw_markers':raw,'new_projects':[{'raw':str(i),'query':x.record()} for i,x in enumerate(q)]}
        cover={'0':[Interval(0,100)],'1':[Interval(0,100)],'2':[Interval(0,40)],'3':[Interval(0,80)]}
        full,part=ranked_matches(trace,{q[0].window_id},cover)
        self.assertEqual([r['raw_receipt'] for r in full],['1'])
        self.assertEqual([r['raw_receipt'] for r in part],['3','2'])

    def test_locus_test_uses_covered_subset_and_reverse_target_offsets(self):
        hit=SimpleNamespace(query_name='a',target_name='b',strand='-')
        with patch('replay_regional_matched_reciprocal.qualified_pairs',return_value=[(Interval(0,100),Interval(10,110))]):
            actual=locus_groups([hit],{},[Interval(0,10),Interval(50,60)])
        self.assertEqual(actual,{('a','b','-'):([Interval(0,10),Interval(50,60)],[Interval(100,110),Interval(50,60)])})
