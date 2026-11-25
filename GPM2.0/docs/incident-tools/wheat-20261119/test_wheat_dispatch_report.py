import unittest
from collections import Counter

from wheat_dispatch_report import disposition, historic_ok


class WorkCensusTests(unittest.TestCase):
    def test_positive_complete_scope_precedes_parent_and_window_routes(self):
        self.assertEqual(disposition('exact_complete_matrices', True, [], [8], 'no_stored_context'), 'skip_complete_native')
        self.assertEqual(disposition('declared_long_part_scope', False, [2], [], 'verified'), 'skip_scoped_native')

    def test_single_failed_sibling_makes_parent_fallback_even_if_other_window_has_no_demand(self):
        self.assertEqual(disposition(None, True, [], [], 'geometrically_omitted'), 'whole_parent_fallback')
        self.assertEqual(disposition(None, False, [], [], 'geometrically_omitted'), 'omit_both_axes')

    def test_target_only_is_neither_an_automatic_skip_nor_an_automatic_mapper_launch(self):
        for status, expected in [('verified','reuse_exact_raw'),('no_stored_context','cold_exact'),
                                 ('missing_raw','cold_exact'),('missing_chain_and_raw','cold_exact'),
                                 ('missing_chain','needs_review'),('cache_needs_review','needs_review')]:
            self.assertEqual(disposition(None,False,[],[1],status), expected)
            self.assertEqual(disposition(None,False,[2],[1],status), expected)

    def test_prior_coverage_check_requires_matching_axes_statuses_and_exception_ids(self):
        hist=Counter(verified=3);axes=Counter(query=1,target_only=2);old=dict(raw_observations=dict(hist),two_axis=dict(axes),total_windows=3)
        seen={'q1','q2','q3'};prior={'q3':'parent'}
        self.assertTrue(historic_ok(old,axes,hist,seen,prior,{'q3'}))
        self.assertFalse(historic_ok(old,axes,hist,seen,prior,{'q1'}))
        self.assertFalse(historic_ok(old,axes,hist,seen-{'q2'},prior,{'q3'}))
        self.assertFalse(historic_ok(old,axes,Counter(verified=2,omitted=1),seen,prior,{'q3'}))


if __name__=='__main__':unittest.main()
