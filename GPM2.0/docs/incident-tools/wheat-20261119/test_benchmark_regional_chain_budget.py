import unittest
from benchmark_regional_chain_budget import candidate_argv


class ChainBudgetTests(unittest.TestCase):
    def setUp(self):self.argv=['mm2','-c','-x','asm10','-D','-P','--dual=yes','--no-long-join','-m','2000','-t','2','old-t','old-q']
    def test_legacy_command_preserved(self):
        self.assertEqual(candidate_argv(self.argv,'t','q',False),self.argv[:-2]+['t','q'])
    def test_cap_is_not_silently_disabled_by_all_chains(self):
        result=candidate_argv(self.argv,'t','q',True)
        self.assertNotIn('-P',result);self.assertNotIn('-X',result)
        self.assertEqual(result[-6:],['-p','0.5','-N','50','t','q'])
        self.assertIn('-D',result);self.assertIn('--dual=yes',result)
        self.assertEqual(result[result.index('-m')+1],'2000')
        self.assertIn('-P',self.argv)
    def test_combined_all_vs_all_and_conflicting_policies_rejected(self):
        for flag in ('-X','-P','-N','-p','--secondary=no'):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                candidate_argv(self.argv[:-2]+[flag,*self.argv[-2:]],'t','q',True)
    def test_missing_explicit_original_flag_rejected(self):
        with self.assertRaises(ValueError):candidate_argv([x for x in self.argv if x!='-P'],'t','q',True)
    def test_exact_cigar_and_two_threads_stay_required(self):
        with self.assertRaises(ValueError):candidate_argv([x for x in self.argv if x!='-c'],'t','q',True)
        with self.assertRaises(ValueError):candidate_argv([*self.argv[:-3],'4',*self.argv[-2:]],'t','q',True)


if __name__=='__main__':unittest.main()
