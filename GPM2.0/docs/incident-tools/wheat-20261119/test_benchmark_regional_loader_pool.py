import unittest

from benchmark_regional_loader_pool import exact_child_env, smoke_comparison


class LoaderPoolTests(unittest.TestCase):
    def test_only_verified_child_ld_variable_can_change(self):
        parent = {'LD_LIBRARY_PATH':'/old/path', 'PATH':'/bin','LC_ALL':'C'}
        child = {'PATH':'/bin','LC_ALL':'C'}
        self.assertIs(exact_child_env(parent,child),child)
        self.assertEqual(parent['LD_LIBRARY_PATH'],'/old/path')
        for invalid in (None, parent.copy(), {**child,'PATH':'/other'}, {**child,'LD_PRELOAD':'extra'}):
            with self.assertRaisesRegex(ValueError,'loader'):
                exact_child_env(parent,invalid)

    def test_local_candidate_gets_no_cross_node_authority(self):
        proof = {'policy':'clear_same_dependencies_v1','tool_sha256':'tool','inherited_path_sha256':'h','dependencies_sha256':'old'}
        local = dict(proof,dependencies_sha256='new')
        self.assertEqual(smoke_comparison(proof,proof),[])
        with self.assertRaisesRegex(ValueError,'dependencies_sha256'):
            smoke_comparison(local,proof)
        self.assertEqual(smoke_comparison(local,proof,allow_node_local_proof=True),['dependencies_sha256'])
        for changed in (dict(local,tool_sha256='other'),dict(local,policy='other'),dict(local,new_proof='unexpected')):
            with self.assertRaisesRegex(ValueError,'loader proof'):
                smoke_comparison(changed,proof,allow_node_local_proof=True)


if __name__ == '__main__':
    unittest.main()
