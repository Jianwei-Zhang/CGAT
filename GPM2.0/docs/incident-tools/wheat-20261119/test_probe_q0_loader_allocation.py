from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from probe_q0_loader_allocation import checked, probe, smoke_scope, POLICY


@dataclass(frozen=True)
class StubLoader:
    tool_path: str
    tool_sha256: str
    path_sha256: str
    dependencies_sha256: str

    def child(self, tool):
        return {}, {'policy': POLICY, 'tool_sha256': tool['sha256'],
                    'inherited_path_sha256': self.path_sha256, 'dependencies_sha256': self.dependencies_sha256}


class AllocationLoaderProofTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.path = self.root / 'smoke.jsonl'
        self.loader = {'policy': POLICY, 'tool_sha256': 'a'*64,
                       'inherited_path_sha256': 'b'*64, 'dependencies_sha256': 'c'*64}

    def save(self, writer=POLICY, *, modified=False):
        last = {'status': 'real_regional_writer_parity_and_old_reader_reuse',
                'production_modified': modified, 'old_project_receipts': [{'project': 'a'}, {'project': 'b'}],
                'new_execution_in_isolated_dir': [{'mode': 'precise', 'child_loader': self.loader},
                     {'mode': 'chaining', 'child_loader': {**self.loader, 'policy': writer}}]}
        self.path.write_text('{}\n'+json.dumps(last)+'\n')
        return {'path': str(self.path), 'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()}

    def test_read_only_smoke_requires_same_real_environment_for_both_stages(self):
        self.assertEqual(smoke_scope(checked(self.save(), self.root)), self.loader)
        with self.assertRaisesRegex(ValueError, 'exact loader proofs differ'):
            smoke_scope(checked(self.save('other'), self.root))
        with self.assertRaisesRegex(ValueError, 'no successful isolated'):
            smoke_scope(checked(self.save(modified=True), self.root))

    def test_no_proof_mutation_or_path_escape(self):
        proof = self.save()
        self.path.write_text('changed\n')
        with self.assertRaisesRegex(ValueError, 'drifted'):
            checked(proof, self.root)
        link = self.root / 'linked'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'drifted'):
            checked({**proof, 'path': str(link)}, self.root)


    def test_actual_pre_ready_scope_accepts_only_matching_candidate_dependencies_and_cpu(self):
        def record(path):
            return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        work = self.root/'workspace'; work.mkdir()
        stage = self.root/'stage'; stage.mkdir()
        # Simulate an immutable isolated package distinct from the real workspace.
        loader_smoke = self.save()
        inside = stage/self.path.name; inside.write_bytes(self.path.read_bytes())
        module = stage/'package/server/tools/lgz_core/q0_regional_mapping.py'
        module.parent.mkdir(parents=True); module.write_text('# scope\n')
        source = stage/'runtime.py'; source.write_bytes(module.read_bytes())
        t = stage/'transition.json'; t.write_text(json.dumps({'workspace': str(work), 'regional_mapper_loader_policy': POLICY,
             'runtime': [{'relative': '.prepare_lib/tools/lgz_core/q0_regional_mapping.py', 'source': record(source),
                          'new_sha256': record(source)['sha256']}]}))
        c = stage/'config.json'; c.write_text(json.dumps({'workspace': str(work), 'old_job': 1, 'protected_baseline': 2,
             'transition': record(t), 'loader_smoke': {**loader_smoke, 'path': str(inside)}}))
        loader = StubLoader('/path/to/minimap2', 'a'*64, 'b'*64, 'c'*64)
        mapping = SimpleNamespace(__file__=str(module), _probe_mapper_loader=lambda command: loader)
        with patch.dict(sys.modules, {'lgz_core': SimpleNamespace(q0_regional_mapping=mapping)}):
            with patch('os.sched_getaffinity', return_value=set(range(32)), create=True):
                self.assertEqual(probe(c)['config_sha256'], record(c)['sha256'])
                self.assertFalse(probe(c)['workspace_modified'])
                mapping._probe_mapper_loader = lambda command: StubLoader('/path/to/minimap2', 'a'*64, 'b'*64, 'd'*64)
                with self.assertRaisesRegex(ValueError, 'identities differ'):
                    probe(c)
            mapping._probe_mapper_loader = lambda command: loader
            with patch('os.sched_getaffinity', return_value={1, 2}, create=True):
                with self.assertRaisesRegex(ValueError, 'less than 32'):
                    probe(c)


if __name__ == '__main__':
    unittest.main()
