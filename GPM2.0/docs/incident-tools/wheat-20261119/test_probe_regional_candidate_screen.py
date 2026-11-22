import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('candidate_probe', Path(__file__).with_name('probe_regional_candidate_screen.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class CandidateProbeTests(unittest.TestCase):
    def test_core_overlap_not_context_only_chain_wins_budget(self):
        chains = [('a', 0, 200, 200, 200, 1000, '+'), ('b', 400, 600, 200, 200, 200, '+'), ('c', 0, 100, 100, 100, 20, '+')]
        selected = m.choose_targets(chains, {'a': 'other', 'b': 'other', 'c': 'other'}, 'query', ((400, 600),), 1, 1)
        self.assertEqual(selected, {'a', 'b'})  # b covers the core; a preserves strong flank context.

    def test_independent_datasets_cores_and_strands_retain_diversity(self):
        chains = [('a', 0, 100, 100, 100, 100, '+'), ('b', 100, 200, 100, 100, 100, '+'), ('c', 0, 100, 90, 100, 90, '-'), ('d', 0, 100, 100, 100, 100, '+')]
        datasets = {'a': 'q', 'b': 'q', 'c': 'other', 'd': 'third'}
        self.assertEqual(m.choose_targets(chains, datasets, 'q', ((0, 100), (100, 200)), 1, 1), set(datasets))

    def test_deterministic_under_input_permutation_and_duplicate_chain(self):
        chains = [('b', 0, 100, 100, 100, 100, '+'), ('a', 0, 100, 100, 100, 100, '+')]
        args = ({'a': 'q', 'b': 'q'}, 'q', ((0, 100),), 1, 1)
        self.assertEqual(m.choose_targets(chains, *args), {'a'})
        self.assertEqual(m.choose_targets(chains[::-1]+chains, *args), {'a'})

    def test_empty_coarse_is_only_an_empty_proposal_not_negative_evidence(self):
        self.assertEqual(m.choose_targets([], {'a': 'q'}, 'q', ((0, 100),), 1, 1), set())

    def test_coverage_is_union_and_separates_intra_cross(self):
        values = {'a': [(0, 100), (50, 150)], 'b': [(0, 80)], 'c': [(20, 120)]}
        ds = {'a': 'q', 'b': 'other', 'c': 'other'}
        self.assertEqual(m.coverage_summary(values, ds, 'q', set(ds)), {'intra': 150, 'cross': 120})
        self.assertEqual(m.coverage_summary(values, ds, 'q', {'c'}), {'intra': 0, 'cross': 100})

    def test_invalid_hint_or_budget_rejected(self):
        for chain in [('x', 0, 1, 1, 1, 1, '+'), ('a', 1, 0, 1, 1, 1, '+'), ('a', 0, 1, 2, 1, 1, '+')]:
            with self.assertRaises(ValueError): m.choose_targets([chain], {'a': 'q'}, 'q', ((0, 1),), 1, 1)
        with self.assertRaises(ValueError): m.choose_targets([], {}, 'q', ((0, 1),), 0, 1)


if __name__ == '__main__': unittest.main()
