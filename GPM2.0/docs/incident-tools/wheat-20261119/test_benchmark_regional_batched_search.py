"""Focused tests for diagnostic batching ownership, resource caps and flags."""
from types import SimpleNamespace
import unittest

from benchmark_regional_batched_search import make_groups, filtered_argv, interval_quality


def case(query, targets, extra=()):
    return {'query':SimpleNamespace(window_id=query),
            'targets':[SimpleNamespace(window_id=k,length=v) for k,v in targets],
            'argv':['minimap2','-c','-x','asm10',*extra,'-t','2','old-target','old-query'],
            'tool':{'sha256':'fixed','resolved':'minimap2'}}


class BatchTests(unittest.TestCase):
    def test_target_union_not_sum(self):
        rows=[case('q1',[('t1',6)]),case('q2',[('t1',6),('t2',3)])]
        self.assertEqual([g['ordinals'] for g in make_groups(rows,target_cap=10)],[[0,1]])

    def test_cap_and_ownership(self):
        rows=[case('q'+str(i), [('t'+str(i),4)]) for i in range(7)]
        groups=make_groups(rows,maximum=4,target_cap=9)
        self.assertEqual([g['ordinals'] for g in groups],[[0,1],[2,3],[4,5],[6]])
        self.assertTrue(all(sum(g['lengths'].values())<=9 for g in groups))

    def test_flags_never_mixed(self):
        rows=[case('q1',[('t',1)]),case('q2',[('t',1)],('-m','2000')),case('q3',[('t',1)])]
        self.assertEqual([g['ordinals'] for g in make_groups(rows)],[[0,2],[1]])

    def test_duplicate_query_kept_in_separate_batch(self):
        self.assertEqual([g['ordinals'] for g in make_groups([case('q',[('a',1)]),case('q',[('b',1)])])],[[0],[1]])

    def test_oversize_single_case_rejected(self):
        with self.assertRaises(ValueError): make_groups([case('q',[('a',11)])],target_cap=10)

    def test_no_filter_silently_overridden(self):
        argv=case('q',[('t',1)])['argv']
        self.assertEqual(filtered_argv(argv,'target','query'),argv[:-2]+['target','query'])
        candidate=filtered_argv(argv,'target','query',coarse=True,filtered=True)
        self.assertNotIn('-c',candidate);self.assertEqual(candidate[-4:],['-f','0.005','target','query'])
        with self.assertRaises(ValueError): filtered_argv(argv[:-2]+['-f','0.01',*argv[-2:]],'t','q',filtered=True)

    def test_quality_preserves_core_frame_and_ignores_mismatch(self):
        query=SimpleNamespace(window_id='q',length=100,start=1000,cores=((1010,1050),))
        hit=SimpleNamespace(matches=95,block_length=100,target_name='t',aligned_blocks=lambda:[
            SimpleNamespace(operation='M',query=SimpleNamespace(start=0,end=30,length=30)),
            SimpleNamespace(operation='X',query=SimpleNamespace(start=30,end=50,length=20)),
            SimpleNamespace(operation='M',query=SimpleNamespace(start=50,end=100,length=50))])
        c={'query':query,'lengths':{'t':100},'td':{'t':'other'},'qd':'self'}
        result=interval_quality(None,c,lambda *args,**kwargs:[hit])
        self.assertEqual(result['intervals'],{'intra':[],'cross':[(1010,1030)]})
        self.assertEqual(result['bases'],{'intra':0,'cross':20})


if __name__ == '__main__': unittest.main()
