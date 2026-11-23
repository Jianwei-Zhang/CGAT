from types import SimpleNamespace as NS
import unittest

from probe_regional_dp_budget import command_for, paired_quality, summarize_quality


class DpBudgetProbeTests(unittest.TestCase):
    def test_only_candidate_dp_cap_changes(self):
        original=['minimap2','-c','-x','asm10','-P','-D','-m','2000','-t','2','old-target','old-query']
        baseline=command_for(original,'target','query',False)
        candidate=command_for(original,'target','query',True)
        self.assertEqual(candidate[:-4],baseline[:-2]);self.assertEqual(candidate[-4:],['--cap-sw-mem','10m','target','query'])
        self.assertEqual(original[-2:],['old-target','old-query'])

    def test_cannot_change_secondary_policy_or_overwrite_existing_cap(self):
        base=['minimap2','-c','-t','2','a','b']
        for prefix in ([],['-P','--cap-sw-mem=20m'],['-P','--cap-sw-mem','20m']):
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):command_for([*prefix,*base],'a','b',True)

    def test_same_core_coverage_can_still_lose_target_and_strand(self):
        q={'cross':[(0,2000)],'intra':[]}
        old={'by_kind':q,'query_by_oriented_target':{('a','-'): [(0,2000)]},'target_by_oriented_target':{('a','-'): [(0,2000)]}}
        new={'by_kind':q,'query_by_oriented_target':{('a','+'): [(0,2000)]},'target_by_oriented_target':{('a','+'): [(0,2000)]}}
        r=summarize_quality(old,new,{'qd':'self','td':{'a':'other'}})['cross']
        self.assertEqual(r['lost_core_bp'],0);self.assertEqual(r['missing_oriented_targets_ge_1kb'],1)
        self.assertEqual(r['lost_target_group_query_bp'],2000);self.assertEqual(r['lost_target_group_target_bp'],2000)

    def test_reverse_target_geometry_clipped_to_original_core(self):
        query=NS(window_id='q',length=200,start=1000,cores=((1030,1070),))
        block=NS(operation='M',query=NS(start=20,end=120),target=NS(start=50,end=150))
        hit=NS(target_name='t',strand='-',matches=100,block_length=100,cigar=[(100,'M')],aligned_blocks=lambda:[block])
        c={'query':query,'qd':'self','td':{'t':'other'},'lengths':{'t':300}}
        got=paired_quality('fixture',c,lambda *a,**k:[hit])
        self.assertEqual(got['by_kind']['cross'],[(30,70)])
        self.assertEqual(got['target_by_oriented_target'][('t','-')],[(100,140)])


if __name__=='__main__':unittest.main()
