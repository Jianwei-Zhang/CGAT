import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_orchestration as lib
from probe_q0_buffered_preflight import rows_from_previous, verifier


class TestBufferedVerifier(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.paf = self.root/'runs/wheat_vs_ref/result.paf'
        self.paf.parent.mkdir(parents=True)
        self.paf.write_bytes(b'q\t10\t0\t10\t-\tt\t10\t0\t10\t10\t10\t60\tcg:Z:10M\r\n')
        self.version = self.paf.with_name('tool_version.txt')
        self.version.write_text('fixture')
        self.reference = SimpleNamespace(kind='reference_alignment',unit_id='ref:wheat')
        self.assignment = SimpleNamespace(kind='assignment',unit_id='assign')
        self.chromosome = SimpleNamespace(kind='q0_chromosome_alignments',unit_id='q0_chr:1A')
        path = self.paf

        class FrozenBase:
            def __init__(self, server_dir):
                self.server_dir = server_dir

            def _identities(self, paths):
                return [lib.file_identity(p, relative_to=self.server_dir) for p in paths]

            def _assignment_output_paths(self):
                return [path.with_name('tool_version.txt')]

            def _chromosome_output_paths(self, chromosome, *, alignment_only=False):
                if chromosome != '1A' or not alignment_only:
                    raise ValueError('wrong discovery arguments')
                return [path.with_name('tool_version.txt'), path, path]

        self.manager = verifier(FrozenBase,lib,ValueError)(self.root)

    def test_output_manifests_match_original_path_size_sha(self):
        expected = [lib.file_identity(p,relative_to=self.root) for p in (self.paf,self.version)]
        for unit in (self.reference,self.chromosome):
            self.assertEqual(self.manager._output_identities(unit),expected)
        with patch.object(lib,'paf_file_identity',side_effect=AssertionError('assignment has no PAF')):
            self.assertEqual(self.manager._output_identities(self.assignment),expected[1:])

    def test_refuses_bad_geometry_and_cannot_commit_or_validate_other_kinds(self):
        self.paf.write_bytes(self.paf.read_bytes().replace(b'cg:Z:10M',b'cg:Z:9M'))
        lib.file_identity(self.paf)
        with self.assertRaisesRegex(ValueError,'CIGAR span mismatch'):
            self.manager._output_identities(self.reference)
        with self.assertRaisesRegex(ValueError,'outside the audited'):
            self.manager._output_identities(SimpleNamespace(kind='chromosome_local'))
        with self.assertRaisesRegex(ValueError,'cannot commit'):
            self.manager.commit(self.chromosome)

    def test_prior_proof_must_be_complete_and_bound(self):
        p = self.root/'prior.json'
        rows = [{'unit_id':i,'input_fingerprint':'input','checkpoint_sha256':'output'} for i in range(25)]
        original = {'status':'q0_transition_all_initial_checkpoints_verified_only','transition_sha256':'origin',
                    'workspace_modified':False,'main_task_submitted':False,'q0_runtime_installed':False,
                    'initial_checkpoints':rows}
        p.write_text(json.dumps(original))
        self.assertEqual(rows_from_previous(p,'origin'),rows)
        for changed in ({'transition_sha256':'wrong'}, {'initial_checkpoints':rows[:-1]},
                        {'initial_checkpoints':[rows[0]]*25}, {'workspace_modified':True}):
            p.write_text(json.dumps({**original,**changed}))
            with self.assertRaisesRegex(ValueError,'previous complete'):
                rows_from_previous(p,'origin')


if __name__ == '__main__':
    unittest.main()
