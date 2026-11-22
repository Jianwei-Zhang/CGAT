import unittest

from benchmark_regional_loader_pool import exact_child_env


class LoaderPoolTests(unittest.TestCase):
    def test_only_verified_child_ld_variable_can_change(self):
        parent = {'LD_LIBRARY_PATH':'/old/path', 'PATH':'/bin','LC_ALL':'C'}
        child = {'PATH':'/bin','LC_ALL':'C'}
        self.assertIs(exact_child_env(parent,child),child)
        self.assertEqual(parent['LD_LIBRARY_PATH'],'/old/path')
        for invalid in (None, parent.copy(), {**child,'PATH':'/other'}, {**child,'LD_PRELOAD':'extra'}):
            with self.assertRaisesRegex(ValueError,'loader'):
                exact_child_env(parent,invalid)


if __name__ == '__main__':
    unittest.main()
