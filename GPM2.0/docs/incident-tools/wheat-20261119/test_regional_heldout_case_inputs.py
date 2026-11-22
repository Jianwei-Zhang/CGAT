import unittest
from regional_heldout_case_inputs import select_rows, ORDINALS
from benchmark_regional_chain_budget_heldout import candidate_argv


class CohortTests(unittest.TestCase):
    def rows(self):
        return {'rows':[{'ordinal':i,'raw_receipt':'raw-'+str(i),'anchor_case':False,'legacy_target_bases':1000} for i in ORDINALS]}
    def test_exact_predeclared_order(self):
        self.assertEqual([r['ordinal'] for r in select_rows(self.rows(),{'other'})],list(ORDINALS))
    def test_native_tuning_anchors_never_reused(self):
        with self.assertRaises(ValueError):select_rows(self.rows(),{'raw-90'})
        rows=self.rows();rows['rows'][0]['anchor_case']=True
        with self.assertRaises(ValueError):select_rows(rows,set())
    def test_ambiguous_or_missing_rows_rejected(self):
        for rows in [self.rows()['rows'][1:],self.rows()['rows']+[self.rows()['rows'][0]]]:
            with self.assertRaises(ValueError):select_rows({'rows':rows},set())
    def test_expanded_candidate_is_declared_gentler_policy(self):
        argv=['mm2','-c','-x','asm10','-P','-t','2','old-t','old-q']
        result=candidate_argv(argv,'t','q',True)
        self.assertNotIn('-P',result)
        self.assertEqual(result[-6:],['-p','0.1','-N','200','t','q'])
        self.assertEqual(candidate_argv(argv,'t','q',False),argv[:-2]+['t','q'])
    def test_input_budget_is_bounded(self):
        rows=self.rows();rows['rows'][0]['legacy_target_bases']=1024**3
        with self.assertRaises(ValueError):select_rows(rows,set())


if __name__=='__main__':unittest.main()
