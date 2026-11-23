import unittest
from types import SimpleNamespace

from lgz_core.q0_sources import Interval
from replay_regional_reciprocal_coverage import add_reverse, clip_pair, covered_bases, locus_loss, qualified_pairs


class TestReciprocalCoverage(unittest.TestCase):
    def test_disjoint_cores_exactly_covered(self):
        self.assertEqual(covered_bases([Interval(1,4),Interval(6,10)],[Interval(3,9)]),4)

    def test_reverse_clipping_keeps_target_coordinates(self):
        self.assertEqual(clip_pair(Interval(100,200),Interval(50,150),'-',Interval(100,120)),
                         (Interval(100,120),Interval(130,150)))

    def test_covered_base_is_not_oriented_relationship(self):
        hit=SimpleNamespace(query_name='a',target_name='b',strand='+'); seeds={}
        q,t=Interval(0,1200),Interval(1500,2700); add_reverse(seeds,hit,q,t)
        self.assertEqual(locus_loss({('b','a','-'):([t],[q])},seeds)['groups_completely_missing_ge_1kb'],1)
        self.assertEqual(locus_loss({('b','a','+'):([t],[q])},seeds)['target_group_bp_not_covered'],0)

    def test_excludes_same_dataset_and_mismatch_runs(self):
        def block(op,a,b):
            return SimpleNamespace(operation=op,query=a,target=b)
        q,t=Interval(1,201),Interval(50,250)
        hit=SimpleNamespace(query_name='a',target_name='b',matches=199,block_length=200,
            cigar=[(199,'='),(1,'X')],aligned_blocks=lambda:[block('=',q,t),block('X',q,t)])
        self.assertEqual(list(qualified_pairs(hit,{'a':'1','b':'1'})),[])
        self.assertEqual(list(qualified_pairs(hit,{'a':'1','b':'2'})),[(q,t)])
