import unittest
from collections import Counter
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
from lgz_core.q0_paths import Placement
from lgz_core.q0_coverage import CoverageModel,Equivalence
from wheat_locus_guard_readonly import ReferenceDomains,guarded_model
from wheat_top_chain_admission_readonly import top_chain
from wheat_continuous_dominant_admission_readonly import adm,continuous_candidates
from test_wheat_continuous_dominant_admission import anchor


def placement(name,ref=None,reverse=False):
    src=SourceKey('d',name)
    aa=() if ref is None else (anchor(0,100,ref),)
    return Placement(name,name,src,Interval(0,100),'-' if reverse else '+','1A',tuple(a.reference for a in aa),tuple(a.source for a in aa),('e',),aa,ref is not None,'reference' if ref is not None else 'input_adjacency')


class LocusTests(unittest.TestCase):
    def model(self,ps,edges):
        domains=ReferenceDomains(ps,1000);audit=Counter();cls,_=guarded_model(domains,audit)
        m=cls({p.source:(p.interval,) for p in ps},edges,compact_first=True)
        return m,audit
    def test_native_relation_set_reconstructed_before_locus_filter(self):
        from test_wheat_continuity_refinement import fixture
        from wheat_locus_guard_readonly import replace_coverage
        from unittest.mock import patch
        graph,_,_=fixture()
        with patch.object(graph,'homologous_blocks',side_effect=AssertionError('post-exclusion requalification forbidden')):
            report=replace_coverage(graph,1000,progress=None)
        self.assertTrue(all(report['native_equivalence_reconstruction_proof'].values()))

    def test_same_locus_still_duplicates(self):
        a,b=placement('a',10000),placement('b',10000)
        r=Equivalence(a.source,a.interval,b.source,b.interval,False,'ab')
        m,stats=self.model([a,b],[r]);native=CoverageModel({p.source:(p.interval,) for p in [a,b]},[r],compact_first=True)
        self.assertEqual(m.atoms,native.atoms);self.assertEqual(m.units,native.units)
        self.assertIsNone(m.unique_selected_bp([(a.source,a.interval),(b.source,b.interval)]))
        self.assertFalse(stats['rejected_unions'])
    def test_distant_loci_not_redundant(self):
        a,b=placement('a',10000),placement('b',10000000)
        r=Equivalence(a.source,a.interval,b.source,b.interval,False,'ab')
        m,stats=self.model([a,b],[r])
        self.assertEqual(m.unique_selected_bp([(a.source,a.interval),(b.source,b.interval)]),200)
        self.assertEqual(stats['rejected_unions'],1)
    def test_unknown_bridge_cannot_reconnect_distant_loci(self):
        a,b,c=placement('a',10000),placement('b'),placement('c',10000000)
        es=[Equivalence(a.source,a.interval,b.source,b.interval,False,'ab'),Equivalence(b.source,b.interval,c.source,c.interval,False,'bc')]
        m,stats=self.model([a,b,c],es)
        self.assertEqual(m.unique_selected_bp([(a.source,a.interval),(c.source,c.interval)]),200)
        self.assertEqual(stats['rejected_unions'],1)
    def test_unknown_loci_are_not_discarded(self):
        a,b=placement('a'),placement('b')
        m,stats=self.model([a,b],[Equivalence(a.source,a.interval,b.source,b.interval,False,'ab')])
        self.assertIsNone(m.unique_selected_bp([(a.source,a.interval),(b.source,b.interval)]))
        self.assertFalse(stats['rejected_unions'])
    def test_reverse_same_locus_remains_duplicate(self):
        a,b=placement('a',10000),placement('b',10000,True)
        m,stats=self.model([a,b],[Equivalence(a.source,a.interval,b.source,b.interval,True,'ab')])
        self.assertIsNone(m.unique_selected_bp([(a.source,a.interval),(b.source,b.interval)]))
    def test_different_internal_anchors_share_same_atom_start_frame(self):
        from dataclasses import replace
        a=placement('a',10000);b=placement('b',10000)
        left=anchor(0,20,10000);right=anchor(80,100,10080)
        a=replace(a,reference_blocks=(left,),reference_intervals=(left.reference,),anchor_intervals=(left.source,))
        b=replace(b,reference_blocks=(right,),reference_intervals=(right.reference,),anchor_intervals=(right.source,))
        domains=ReferenceDomains([a,b],0);stats=Counter();model,_=guarded_model(domains,stats)
        m=model({p.source:(p.interval,) for p in (a,b)},[Equivalence(a.source,a.interval,b.source,b.interval,False,'ab')])
        self.assertIsNone(m.unique_selected_bp([(a.source,a.interval),(b.source,b.interval)]))
        self.assertFalse(stats['rejected_unions'])

    def test_nearby_structural_uncertainty_is_preserved(self):
        a,b=placement('a',10000),placement('b',10500)
        m,stats=self.model([a,b],[Equivalence(a.source,a.interval,b.source,b.interval,False,'ab')])
        self.assertFalse(stats['rejected_unions'])


class TopChainTests(unittest.TestCase):
    def setup_groups(self):
        main=[anchor(i*150000,i*150000+100000,i*150000) for i in range(10)]
        groups={('1A','+'):main}
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,1500000),'a'*64,0,'start','end')
        return main,groups,part
    def test_many_tiny_foreign_groups_do_not_veto_strong_chain(self):
        main,groups,part=self.setup_groups()
        for i in range(10):
            for j in range(4):
                lo=i*150000+100000+j*10000
                groups[(str(i)+'foreign'+str(j),'+')]=[anchor(lo,lo+10000,1000000+lo)]
        high={k:tuple(a.source for a in aa) for k,aa in groups.items()}
        old,_=continuous_candidates(part,groups,high)
        self.assertFalse(old['75'])
        new,detail=top_chain(part,groups,high,('1A','+'))
        self.assertEqual(len(new['10']),1)
    def test_large_single_group_total_blocks_scattered_competitor(self):
        main,groups,part=self.setup_groups()
        groups[('1B','+')]=[anchor(i*150000+100000,i*150000+140000,2000000-i*100000) for i in range(10)]
        high={k:tuple(a.source for a in aa) for k,aa in groups.items()}
        new,_=top_chain(part,groups,high,('1A','+'))
        self.assertFalse(new['5']);self.assertFalse(new['10'])
    def test_true_foreign_chain_is_cut_before_acceptance(self):
        groups={('1A','+'):[anchor(0,600000)],('1B','+'):[anchor(600000,1500000)]}
        high={k:tuple(a.source for a in aa) for k,aa in groups.items()}
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,1500000),'a'*64,0,'start','end')
        new,detail=top_chain(part,groups,high,('1A','+'))
        self.assertEqual([p.interval for p in new['10']],[Interval(0,600000)])

class CrossGroupCacheTests(unittest.TestCase):
    def test_cross_group_physical_source_overlap_not_silently_accepted(self):
        from types import SimpleNamespace as NS
        from wheat_top_chain_cross_readonly import cross_source_overlaps
        src=SourceKey('d','c')
        def path(lo,hi):return NS(slices=[NS(source=src,interval=Interval(lo,hi))],joins=[])
        conflicts=cross_source_overlaps({'1A':path(0,100),'3B':path(99,150),'3D':path(150,200)})
        self.assertEqual(len(conflicts),1);self.assertEqual(conflicts[0]['bp'],1)

    def test_complete_cached_rows_keep_requested_chromosome(self):
        import wheat_top_chain_cross_readonly as cross
        from unittest.mock import patch
        for group in ('3B','3D'):
            src=SourceKey('d','c')
            row={'source':['d','c'],'length':1000000,'sequence_sha256':'a'*64,
                 'groups':[[[group,'+'],[[0,600000,0,600000,'e']],[[0,600000]]]]}
            with patch.dict(cross.CACHED,{src:row},clear=True),patch.object(cross.original.frozen,'LOOKUP',{src:{'length':1000000,'sequence_sha256':'a'*64}},create=True),patch.dict(cross.original.legacy.PART_ID,{src:'p'},clear=True):
                result=cross.screen_task((group,src))
            self.assertTrue(result['cached']);self.assertEqual(result['group'],group)
            self.assertEqual(len(result['new']),1)
            self.assertEqual(cross.decode(result['new'][0]).chromosome,group)

if __name__=='__main__':unittest.main()
