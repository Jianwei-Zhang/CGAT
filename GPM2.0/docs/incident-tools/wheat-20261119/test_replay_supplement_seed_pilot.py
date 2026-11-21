from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_supplement_seed_pilot as pilot


class RetentionMetricTests(unittest.TestCase):
    def test_full_query_coverage_does_not_hide_lost_alternative_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.paf'
            one='q\t200\t0\t200\t+\tt1\t200\t0\t200\t200\t200\t60\tcg:Z:200M\n'
            two='q\t200\t0\t200\t-\tt2\t200\t0\t200\t200\t200\t60\tcg:Z:200M\n'
            path.write_text(one+two);old=pilot.stats(path,{'q':200},{'t1':200,'t2':200})
            path.write_text(one);new=pilot.stats(path,{'q':200},{'t1':200,'t2':200})
            self.assertEqual(pilot.overlap_bp(old['coverage']['q'],new['coverage']['q']),200)
            self.assertEqual(len(old['pairs']),2)
            self.assertEqual(len(old['pairs']&new['pairs']),1)

    def test_gaps_and_low_identity_do_not_count_as_paired_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.paf'
            path.write_text('q\t20100\t0\t20100\t+\tt\t20100\t0\t20100\t20000\t20200\t60\tcg:Z:10000M100I100D10000M\n'
                            'q\t20100\t0\t20100\t+\tt\t20100\t0\t20100\t100\t20100\t60\tcg:Z:20100M\n')
            stats=pilot.stats(path,{'q':20100},{'t':20100})
            self.assertEqual(stats['coverage']['q'],[[0,10000],[10100,20100]])
            self.assertEqual(stats['qualified_rows'],1)

    def test_malformed_or_unknown_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.paf'
            for raw in ['q\t200\t0\t200\t+\tt\t200\t0\t200\t200\t200\t60\tcg:Z:199M\n',
                        'other\t200\t0\t200\t+\tt\t200\t0\t200\t200\t200\t60\tcg:Z:200M\n']:
                path.write_text(raw)
                with self.assertRaises(ValueError):pilot.stats(path,{'q':200},{'t':200})


class CandidateCommandTests(unittest.TestCase):
    def native(self):
        return ["mapper", "-c", "-x", "asm10", "-D", "-P", "--dual=yes", "--no-long-join",
                "-t", "32", "-o", "original.paf", "target.fa", "query.fa"]

    def test_seed_profile_does_not_change_all_chain_policy(self):
        native=self.native();saved=list(native)
        argv,profile=pilot.candidate_command(native,result="candidate.paf",threads=8,seed_fraction="0.001")
        self.assertEqual(native,saved);self.assertIn("-P",argv)
        self.assertEqual(argv[-4:],["-f","0.001","target.fa","query.fa"])
        self.assertEqual(profile["kind"],"seed_filter")

    def test_secondary_profile_removes_P_and_explicitly_retains_low_score_ratio(self):
        argv,profile=pilot.candidate_command(self.native(),result="candidate.paf",threads=8,secondary_cap=100)
        self.assertNotIn("-P",argv)
        self.assertEqual(argv[-6:],["-p","0","-N","100","target.fa","query.fa"])
        for flag in ["-c","-D","--dual=yes","--no-long-join"]:self.assertIn(flag,argv)
        self.assertTrue(profile["all_chain_retention_disabled"])

    def test_ambiguous_or_unsupported_profiles_fail(self):
        for kwargs in [{},{"seed_fraction":"0.001","secondary_cap":100},{"secondary_cap":1}]:
            with self.assertRaises(ValueError):pilot.candidate_command(self.native(),result="x",threads=8,**kwargs)


if __name__=='__main__':unittest.main()
