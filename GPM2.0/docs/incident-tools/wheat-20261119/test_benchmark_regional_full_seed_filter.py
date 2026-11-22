import unittest
from benchmark_regional_full_seed_filter import candidate_argv


class FilterTests(unittest.TestCase):
    def setUp(self):self.argv=['mm2','-c','-x','asm10','-m','2000','-t','2','old-t','old-q']
    def test_control_does_not_add_a_filter(self):
        self.assertEqual(candidate_argv(self.argv,'t','q',False),self.argv[:-2]+['t','q'])
    def test_only_declared_candidate_flag_added(self):
        self.assertEqual(candidate_argv(self.argv,'t','q',True),self.argv[:-2]+['-f','0.001','t','q'])
        self.assertEqual(self.argv[-2:],['old-t','old-q'])
    def test_existing_filter_never_silently_overridden(self):
        with self.assertRaises(ValueError):candidate_argv(self.argv[:-2]+['-f','0.01',*self.argv[-2:]],'t','q',True)
    def test_original_cigar_and_threads_required(self):
        with self.assertRaises(ValueError):candidate_argv([x for x in self.argv if x!='-c'],'t','q',True)
        with self.assertRaises(ValueError):candidate_argv([*self.argv[:-3],'4',*self.argv[-2:]],'t','q',True)


if __name__=='__main__':unittest.main()
