import unittest
from server.tools.lgz_core.q0_cigar_policy import ChainWork, CigarWorkPolicy, select_cigar_profile
from server.tools.lgz_core.q0_sources import Q0EvidenceError


class CigarPolicyTests(unittest.TestCase):
    def test_measured_cheap_controls_stay_native_and_residual_costs_trigger(self):
        for chains,weak,cost in [(727,161,2509615085),(1160,287,3132028850),(1332,338,4223120158)]:
            self.assertEqual(select_cigar_profile(5_000_000_000,100000,ChainWork(chains,weak,cost),complete=True)["additional_flags"],[])
        for chains,weak,cost in [(12058,7119,220948050217),(5230,2123,18856486820),(2817,1329,14091272945)]:
            profile=select_cigar_profile(5_000_000_000,100000,ChainWork(chains,weak,cost),complete=True)
            self.assertEqual(profile["additional_flags"],["-m","2000"])
            self.assertTrue(profile["short_additional_chain_recall_reduced"])
            self.assertFalse(profile["approximate_chaining_is_evidence"])

    def test_size_preset_and_exact_threshold_boundaries(self):
        work=ChainWork(1,1,10_000_000_000)
        for ref,query,preset in [(4_999_999_999,20000,"asm10"),(5_000_000_000,19999,"asm10"),(5_000_000_000,20000,"asm20")]:
            self.assertEqual(select_cigar_profile(ref,query,work,complete=True,preset=preset)["additional_flags"],[])
        self.assertEqual(select_cigar_profile(5_000_000_000,20000,work,complete=True)["additional_flags"],["-m","2000"])
        self.assertEqual(select_cigar_profile(5_000_000_000,20000,ChainWork(1,1,9_999_999_999),complete=True)["additional_flags"],[])

    def test_chain_accumulation_is_cost_not_identity_or_actual_paired_coverage(self):
        work=ChainWork()
        work.observe(1000,2000,499);work.observe(1000,2000,500);work.observe(999,10000,1)
        self.assertEqual(work,ChainWork(3,1,2_000_000))
        # A long strong chain is not classified as weak merely for its length.
        work.observe(100000,100000,70000)
        self.assertEqual(work.weak_span_product,2_000_000)

    def test_incomplete_or_malformed_summaries_are_not_accepted(self):
        with self.assertRaises(Q0EvidenceError):select_cigar_profile(5_000_000_000,100000,ChainWork(),complete=False)
        for work in [ChainWork(-1,0,0),ChainWork(0,1,100),ChainWork(1,0,100)]:
            with self.assertRaises(Q0EvidenceError):select_cigar_profile(5_000_000_000,100000,work,complete=True)
        with self.assertRaises(Q0EvidenceError):ChainWork().observe(0,100,1)
        with self.assertRaises(Q0EvidenceError):CigarWorkPolicy(weak_density_denominator=1)


if __name__=="__main__":unittest.main()
