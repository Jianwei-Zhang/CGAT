import copy
import unittest
from produce_unroutable_native_seed import experiment_policy


class ExperimentalPolicyTests(unittest.TestCase):
    def setUp(self):self.policy={'version':4,'supplement_flags':['-D','-P','--dual=yes','--no-long-join']}
    def test_default_does_not_change_native_raw_identity(self):
        self.assertIs(experiment_policy(self.policy,None),self.policy)
    def test_experiment_has_distinct_flags_and_does_not_mutate_native_policy(self):
        before=copy.deepcopy(self.policy);new=experiment_policy(self.policy,2000)
        self.assertEqual(new['supplement_flags'],before['supplement_flags']+['-m','2000'])
        self.assertEqual(self.policy,before)
    def test_unknown_score_or_inherited_override_is_rejected(self):
        for value in (True,1999,'2000'):
            with self.assertRaises(ValueError):experiment_policy(self.policy,value)
        self.policy['supplement_flags']+=['-m','2000']
        with self.assertRaises(ValueError):experiment_policy(self.policy,2000)


if __name__=='__main__':unittest.main()
