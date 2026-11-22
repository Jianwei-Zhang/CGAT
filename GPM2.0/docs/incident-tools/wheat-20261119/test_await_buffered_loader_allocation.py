import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import await_buffered_loader_allocation as watcher


class BufferedAllocationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.stage, self.buffered, self.work = [root/name for name in ('stage','buffered','work')]
        for d in (self.stage, self.buffered, self.work):
            d.mkdir()
        self.env = root/'environment.sh'; self.env.write_text('true\n')
        self.proof = self.buffered/'buffered-proof.json'; self.proof.write_text('{}\n')
        (self.buffered/'submit.txt').write_text('Submit job <4> successfully.\n')
        transition = self.stage/'transition.json'; transition.write_text(json.dumps({'workspace': str(self.work)}))
        self.watched = {'running_job': 1, 'baseline_job': 2, 'preflight_job': 3, 'smoke_job': 5,
                        'running_run_id': 'verified-run', 'transition': watcher.record(transition),
                        'environment': watcher.record(self.env)}
        candidate = self.stage/'candidate-prepared.json'
        candidate.write_text(json.dumps({'transition': self.watched['transition'], 'previous_job': 1, 'protected_baseline': 2}))
        smoke = self.stage/'writer-smoke'; smoke.write_text('{}')
        self.watched.update(candidate=watcher.record(candidate), loader_smoke=watcher.record(smoke))
        self.owner = self.work/'.run_all/lock/owner.json'; self.owner.parent.mkdir(parents=True)
        self.owner.write_text(json.dumps({'workspace':str(self.work), 'run_id':'verified-run', 'hostname':'node1', 'pid':123}))
        self.state = {'1':{'state':'RUNNING','taskExecNodes':'node1'},'2':{'state':'RUNNING'}, '5':{'state':'SUCCEEDED','jobExitCode':0},
                      '4':{'jobId':'4','state':'SUCCEEDED','jobExitCode':0,'endTime':'time',
                           'cmd':str(self.buffered/'run.dsub'),'execPath':str(self.buffered)}}
        self.intention = self.stage/'loader-resource-submit-intent.json'
        self.scheduler = self.buffered/'terminal-4.json'

    def run_advance(self):
        with patch.object(watcher, 'query', side_effect=lambda j: self.state[str(j)]):
            return watcher.advance(self.stage, self.buffered, self.env, self.watched)

    def test_live_preflight_ignores_even_visible_proof(self):
        self.state['4']['state'] = 'RUNNING'
        with patch.object(watcher, 'prepare', side_effect=AssertionError('unexpected setup')):
            self.assertEqual(self.run_advance(), ('waiting_for_same_preflight_terminal', None))
        self.assertFalse(self.intention.exists())

    def test_cannot_prepare_without_real_success_and_matching_live_owner(self):
        with patch.object(watcher, 'prepare', side_effect=AssertionError('unexpected setup')):
            self.state['4']['jobExitCode'] = 1
            with self.assertRaisesRegex(ValueError, 'finish successfully'):
                self.run_advance()
            self.state['4']['jobExitCode'] = 0
            self.state['1']['taskExecNodes'] = 'another'
            with self.assertRaisesRegex(ValueError, 'workspace or phase'):
                self.run_advance()
        self.assertFalse(self.intention.exists())
        self.assertFalse(self.scheduler.exists())

    def test_ready_submission_preserves_real_proof_and_attempts_once(self):
        script = self.stage/'actual.sh'; script.write_text('true\n')
        with patch.object(watcher, 'prepare', return_value={'script':watcher.record(script), 'config':{}}) as prepare, \
             patch.object(watcher.subprocess, 'check_output', return_value='Submit job <6> successfully.\n') as submit:
            state, receipt = self.run_advance()
            self.assertEqual(state,'waiting_resource_submitted_not_released')
            self.assertEqual(receipt['resource_job'],6)
            self.assertFalse((self.stage/'handoff.json').exists())
            prepare.assert_called_once_with(self.stage,self.env,buffered_proof=self.proof,
                                            buffered_scheduler=self.scheduler,allocation_replay=True)
            submit.assert_called_once_with(['dsub','-s',str(script)], cwd=self.stage, text=True, timeout=60)
            with self.assertRaisesRegex(ValueError,'already advanced'):
                self.run_advance()
        self.assertEqual(json.loads(self.scheduler.read_text())['data']['successData'],[self.state['4']])

    def test_ambiguous_job_return_fences_retries(self):
        script = self.stage/'actual.sh'; script.write_text('true\n')
        with patch.object(watcher, 'prepare', return_value={'script':watcher.record(script), 'config':{}}), \
             patch.object(watcher.subprocess, 'check_output', return_value='uncertain') as submit:
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                self.run_advance()
            self.assertTrue(self.intention.exists())
            with self.assertRaisesRegex(ValueError,'already advanced'):
                self.run_advance()
            self.assertEqual(submit.call_count,1)


if __name__ == '__main__':
    unittest.main()
