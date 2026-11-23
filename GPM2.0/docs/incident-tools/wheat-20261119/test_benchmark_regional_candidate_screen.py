import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('native_candidate_probe', HERE/'benchmark_regional_candidate_screen.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class NativeCandidatePilotTests(unittest.TestCase):
    def test_exact_paths_change_without_scientific_flags(self):
        argv = ['mm2', '-c', '-x', 'asm10', '-P', '-m', '2000', '-t', '2', '/old/t', '/old/q']
        self.assertEqual(m.input_argv(argv, Path('/new/t'), Path('/new/q')), argv[:-2]+['/new/t', '/new/q'])
        self.assertEqual(argv[-2:], ['/old/t', '/old/q'])
    def test_coarse_removes_only_cigar_flag(self):
        argv = ['mm2', '-c', '-x', 'asm10', '-P', '-t', '2', 't', 'q']
        self.assertEqual(m.input_argv(argv, 'T', 'Q', coarse=True), ['mm2', '-x', 'asm10', '-P', '-t', '2', 'T', 'Q'])
    def test_wrong_thread_or_missing_exact_flag_rejected(self):
        for argv in (['mm2', '-c', '-t', '32', 't', 'q'], ['mm2', '-t', '2', 't', 'q']):
            with self.assertRaises(ValueError): m.input_argv(argv, 'T', 'Q')

    def test_shifted_equal_coverage_does_not_hide_lost_bases(self):
        self.assertEqual(m.difference_bases([(0, 100)], [(50, 150)]), 50)
        self.assertEqual(m.difference_bases([(50, 150)], [(0, 100)]), 50)
    def test_overlap_touching_union_and_nested_difference(self):
        self.assertEqual(m.merged([(50, 100), (0, 60), (100, 120)]), [(0, 120)])
        self.assertEqual(m.difference_bases([(0, 120)], [(20, 40), (60, 80)]), 80)
        self.assertEqual(m.difference_bases([(20, 40), (60, 80)], [(0, 120)]), 0)
    def test_invalid_coverage_fails(self):
        with self.assertRaises(ValueError): m.merged([(1, 1)])

if __name__ == '__main__': unittest.main()
