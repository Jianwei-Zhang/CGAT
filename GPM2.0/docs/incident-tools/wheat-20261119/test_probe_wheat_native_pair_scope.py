import unittest
from probe_wheat_native_pair_scope import EXACT,MISSING,SCOPED,SELF,evaluate,src_id


class PairScopeTests(unittest.TestCase):
    def setUp(self):
        a,b,c,d,e=[src_id('ds',v) for v in 'abcde'];self.a=a;self.b=b
        self.mask=dict(lengths={a:10,b:20,c:30,d:40,e:50},parents={a:{a:SELF,c:EXACT},b:{b:SELF,c:SCOPED,d:EXACT}},parent_parts={a:'parent-A',b:'parent-B'})

    def run_case(self,rows):
        src=sorted({s for _,v in rows for s in v});return evaluate(self.mask,dict(has_path=True,source_intervals=[[{'dataset':'ds','contig':s},[[0,1]]] for s in src],issues=[dict(kind=k,spans=[['ds',s,0,1] for s in v]) for k,v in rows]))

    def test_targets_only_distinguish_exact_from_declared_coverage(self):
        r=self.run_case([('weak_placement',['c']),('unproven_join',['c','d'])]);self.assertEqual(r['distinct_untested_target_count'],1);self.assertEqual(r['distinct_untested_target_bases'],40)
        self.assertEqual(r['question_classes'],{'previously_scoped_or_self:weak_placement':1,'some_untested_relationship:unproven_join':1});self.assertEqual(r['parents']['parent-A']['direct_join_role'],{})

    def test_query_side_need_cannot_discard_other_targets(self):
        r=self.run_case([('unproven_join',['a','d'])]);a=r['parents']['parent-A'];self.assertTrue(a['query_has_demand']);self.assertEqual(a['whole_targets_examined_by_axis'],4);self.assertEqual(a['untested_pair_scope'],3);self.assertEqual(a['direct_join_role'],{'untested_endpoint_pair':1});self.assertEqual(r['distinct_untested_target_count'],4)

    def test_does_not_accept_foreign_or_shortened_question_geometry(self):
        detail={'has_path':True,'issues':[{'kind':'weak_placement','spans':[['ds','c',2,7]]}],
                'source_intervals':[[{'dataset':'ds','contig':'c'},[[0,1]]]]}
        with self.assertRaisesRegex(ValueError,'question union'):evaluate(self.mask,detail)
        detail['issues'][0]['spans']=[['ds','c',0,100]]
        with self.assertRaisesRegex(ValueError,'outside original'):evaluate(self.mask,detail)

    def test_no_path_is_not_a_zero_work_result(self):
        r=evaluate(self.mask,{'issues':[],'source_intervals':None,'has_path':False});self.assertFalse(r['bounded_request']);self.assertNotIn('distinct_untested_target_count',r)
        r=self.run_case([]);self.assertTrue(r['bounded_request']);self.assertEqual(r['distinct_untested_target_count'],0)


if __name__=='__main__':unittest.main()
