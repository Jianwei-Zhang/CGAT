from pathlib import Path
import unittest

from probe_regional_moderate_dp import CAPS, argv_for, cross_disqualifiers, isolated, ordered_profiles


class ModerateCapTests(unittest.TestCase):
    def test_only_exact_cap_changes(self):
        target, query = Path('/tmp/target.fa'), Path('/tmp/query.fa')
        argv = ['/bin/minimap2', '-c', '-x', 'asm10', '-P', '-m', '2000', '-t', '2', str(target), str(query)]
        case = {'argv': argv, 'paths': {'target.fa': target, 'query.fa': query}}
        self.assertEqual(argv_for(case, 'original'), argv)
        for cap in CAPS:
            self.assertEqual(argv_for(case, cap), argv[:-2] + ['--cap-sw-mem', cap] + argv[-2:])
        with self.assertRaises(ValueError):
            argv_for(case, '10m')
        case['argv'] = argv[:-2] + ['--cap-sw-mem=10m'] + argv[-2:]
        with self.assertRaises(ValueError):
            argv_for(case, '50m')

    def test_profile_order_rotates(self):
        self.assertEqual({ordered_profiles(i)[0] for i in range(3)}, {'original', *CAPS})

    def test_coverage_does_not_hide_cross_competition_change(self):
        coverage = {'lost_core_bp': 0, 'old_core_bp': 1000, 'missing_oriented_targets_ge_1kb': 0}
        pairs = {'gained_previously_observed_but_unqualified_paired_bp': 0,
                 'lost_qualified_paired_bp': 20, 'old_qualified_paired_bp': 1000}
        self.assertFalse(cross_disqualifiers(coverage, pairs))
        pairs['gained_previously_observed_but_unqualified_paired_bp'] = 1
        self.assertEqual(cross_disqualifiers(coverage, pairs), ['new_cross_admission'])
        coverage['missing_oriented_targets_ge_1kb'] = 1
        self.assertIn('cross_oriented_target_missing', cross_disqualifiers(coverage, pairs))

    def test_cannot_write_inside_workspace_or_archive(self):
        for out in (Path('/work/out'), Path('/archive/out'), Path('/')):
            with self.assertRaises(ValueError):
                isolated(Path('/work'), (Path('/archive'),), out)
        isolated(Path('/work'), (Path('/archive'),), Path('/output'))


if __name__ == '__main__':
    unittest.main()
