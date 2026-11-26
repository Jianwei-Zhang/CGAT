import unittest
from types import SimpleNamespace
from lgz_core.q0_paths import Placement
from wheat_continuity_gap_rescue_readonly import hull_variant, split_first
from test_wheat_continuous_dominant_admission import anchor, adm, Interval, SourceKey, SourceSegment, continuous_candidates


class GapRescueTests(unittest.TestCase):
    def test_hull_variant_keeps_original_coverage_and_original_placement(self):
        a=anchor(100,900)
        p=Placement('p','s',SourceKey('d','c'),Interval(0,1000),'+','1A',(a.reference,),(a.source,),('e',),(a,))
        coverage=object();graph=SimpleNamespace(placements={'p':p},coverage=coverage)
        v=hull_variant(graph,'p')
        self.assertEqual(graph.placements[v].interval,Interval(100,900))
        self.assertIs(graph.coverage,coverage)
        self.assertIs(graph.placements['p'],p)
        self.assertEqual(graph.placements[v].reference_blocks,p.reference_blocks)
        self.assertIsNone(hull_variant(graph,v))

    def test_split_first_restores_large_independent_chain_below_global75(self):
        main=(anchor(0,600_000),);other=(anchor(600_000,1_500_000,name='foreign'),)
        groups={('1A','+'):main,('1B','+'):other}
        high={k:tuple(a.source for a in rows) for k,rows in groups.items()}
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,1_500_000),'a'*64,0,'start','end')
        original,_=continuous_candidates(part,groups,high)
        self.assertFalse(original['75'])
        actual,_=split_first(part,groups,high,('1A','+'))
        self.assertEqual([p.interval for p in actual],[Interval(0,600_000)])

    def test_low_mapq_barrier_cannot_rescue_mixed_source(self):
        groups={('1A','+'):(anchor(0,600_000),),('1B','+'):(anchor(600_000,1_500_000),)}
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,1_500_000),'a'*64,0,'start','end')
        actual,_=split_first(part,groups,{('1A','+'):(Interval(0,600_000),)},('1A','+'))
        self.assertFalse(actual)

    def test_small_chain_is_never_promoted(self):
        groups={('1A','+'):(anchor(0,100_000),)}
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,100_000),'a'*64,0,'start','end')
        actual,_=split_first(part,groups,{('1A','+'):(Interval(0,100_000),)},('1A','+'))
        self.assertFalse(actual)

class DuplicateProjectionTests(unittest.TestCase):
    def test_duplicate_coordinates_respect_reverse_units(self):
        from lgz_core.q0_coverage import CoverageModel, Equivalence
        from wheat_duplicate_geometry_readonly import duplicate_intervals
        a,b=SourceKey('d','a'),SourceKey('d','b')
        model=CoverageModel({a:(Interval(0,100),),b:(Interval(100,200),)},
                            [Equivalence(a,Interval(0,100),b,Interval(100,200),True,'e')])
        self.assertEqual(duplicate_intervals(model,((a,Interval(0,30)),),b,Interval(100,200)),
                         (Interval(170,200),))
        self.assertEqual(duplicate_intervals(model,((a,Interval(0,30)),),b,Interval(100,160)),())

if __name__=='__main__':unittest.main()
