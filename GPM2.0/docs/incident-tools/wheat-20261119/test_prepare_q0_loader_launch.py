import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from prepare_q0_loader_launch import prepare, record, POLICY


class PrepareLoaderLaunchTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bundle = self.root / 'fresh'; self.bundle.mkdir()
        self.work = self.root / 'workspace'; self.work.mkdir()
        self.prior = self.root / 'prior'; self.prior.mkdir()
        self.env = self.root / 'environment.sh'; self.env.write_text('# test environment\n')
        (self.bundle / 'probe_q0_loader_allocation.py').write_text('# test probe\n')
        (self.bundle / 'live-sample.json').write_text('{}\n')
        rel = '.prepare_lib/tools/lgz_core/q0_regional_mapping.py'
        target = self.work / rel; target.parent.mkdir(parents=True); target.write_text('# old runtime\n')
        source = self.bundle / 'candidate.py'; source.write_text('# new runtime\n')
        launcher = self.work / 'prepare_q0_evidence.sh'; launcher.write_text('# old launcher\n')
        decl = self.work / 'metadata/incident_q0_routing_reader.json'; decl.parent.mkdir(); decl.write_text('{}\n')
        previous = self.prior / 'transition.json'; previous.write_text('{}\n')
        fresh = self.bundle / 'transition.json'
        fresh.write_text(json.dumps({'runtime': [{'relative': rel, 'prior_sha256': record(target)['sha256'],
                'new_sha256': record(source)['sha256'], 'source': record(source)}], 'workspace': str(self.work),
                'regional_mapper_loader_policy': POLICY, 'prior_launcher_sha256': record(launcher)['sha256'],
                'prior_declaration_sha256': record(decl)['sha256']}))
        (self.bundle/'candidate-prepared.json').write_text(json.dumps({'status': 'q0_candidate_prepared_not_installed',
                'job_stopped': False, 'workspace_modified': False, 'previous_job': 1, 'protected_baseline': 2,
                'transition': record(fresh), 'previous_transition': record(previous)}))
        ids = ['ref:a', 'ref:b', 'assign']+[f'q0_chr:{i}' for i in range(22)]
        for t in (previous, fresh):
            t.with_name('validation.json').write_text(json.dumps({'status': 'q0_transition_all_initial_checkpoints_verified_only',
                 'transition_sha256': record(t)['sha256'], 'workspace_modified': False, 'main_task_submitted': False,
                 'q0_runtime_installed': False, 'initial_checkpoints': [{'unit_id': uid, 'checkpoint_sha256': 'same'} for uid in ids]}))
        smoke = self.bundle/'smoke-v2/smoke.jsonl'; smoke.parent.mkdir()
        smoke.write_text(json.dumps({'status': 'real_regional_writer_parity_and_old_reader_reuse', 'production_modified': False,
               'old_project_receipts': [{'project': 'a'}, {'project': 'b'}], 'new_execution_in_isolated_dir': [
                   {'mode': m, 'child_loader': {'policy': POLICY}} for m in ('precise', 'chaining')]}))

    def test_launch_prep_only_writes_bound_files_and_checks_loader_before_old_gate(self):
        before = {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        result = prepare(self.bundle, self.env)
        self.assertFalse(result['workspace_modified'])
        self.assertEqual(json.loads((self.bundle/'handoff-config.json').read_text())['protected_baseline'], 2)
        script = (self.bundle/'resume.dsub').read_text()
        self.assertLess(script.index('mv loader-ready.json.tmp loader-ready.json'), script.index('exec python3'))
        self.assertEqual(before, {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError, 'not overwrite'):
            prepare(self.bundle, self.env)

    def test_checks_real_prior_identities_and_does_not_write_a_partial_launch(self):
        current = self.bundle/'validation.json'
        payload = json.loads(current.read_text()); payload['initial_checkpoints'][-1]['checkpoint_sha256'] = 'different'
        current.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'identities changed'):
            prepare(self.bundle, self.env)
        self.assertFalse((self.bundle/'resume.dsub').exists())

    def test_never_prepares_when_q0_has_a_completed_result(self):
        (self.work/'metadata/grt_q0_evidence.json').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'already completed'):
            prepare(self.bundle, self.env)
        self.assertFalse((self.bundle/'resume.dsub').exists())


if __name__ == '__main__':
    unittest.main()
