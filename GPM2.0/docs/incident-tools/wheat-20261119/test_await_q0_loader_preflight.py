import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import await_q0_loader_preflight as watcher


class AwaitLoaderPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        self.config = root/'config.json'; self.config.write_text('{}')
        self.work = root/'workspace'; self.work.mkdir()
        self.env = root/'environment.sh'; self.env.write_text('# env')
        self.script = root/'resume.dsub'; self.script.write_text('# job')
        self.owner = self.work/'.run_all/lock/owner.json'; self.owner.parent.mkdir(parents=True)
        self.owner.write_text(json.dumps({'workspace': str(self.work), 'run_id': 'expected-run', 'hostname': 'x86-fixture'}))
        self.settings = dict(preflight_job=1, running_job=2, baseline_job=3, smoke_job=4, running_run_id='expected-run',
                             environment=watcher.record(self.env))
        self.args = self.config, watcher.record(self.config), self.work
        binding = patch.object(watcher, 'load_config', return_value=(self.settings, self.work))
        binding.start(); self.addCleanup(binding.stop)

    def test_live_preflight_cannot_prepare_or_submit(self):
        with (patch.object(watcher, 'query', return_value={'state': 'RUNNING'}),
              patch.object(watcher, 'prepare') as prepare,
              patch.object(watcher.subprocess, 'run') as command):
            self.assertEqual(watcher.maybe_submit(*self.args), (None, 'RUNNING'))
        prepare.assert_not_called(); command.assert_not_called()

    def test_submit_only_one_waiting_resource_job(self):
        state = lambda job: {'state': 'SUCCEEDED' if job in {1, 4} else 'RUNNING', 'execNodes': 'x86-fixture'}
        staged = {'script': watcher.record(self.script), 'config': watcher.record(self.config)}
        with (patch.object(watcher, 'query', side_effect=state), patch.object(watcher, 'prepare', return_value=staged),
              patch.object(watcher.subprocess, 'run', return_value=SimpleNamespace(stdout='Submit job <42> successfully.')) as run):
            receipt, proof_state = watcher.maybe_submit(*self.args)
            self.assertEqual((receipt['resource_job'], proof_state), (42, 'SUCCEEDED'))
            with self.assertRaises(FileExistsError):
                watcher.maybe_submit(*self.args)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ['dsub', '-s', str(self.script)])

    def test_different_live_owner_stops_without_submit(self):
        self.owner.write_text('{}')
        state = lambda job: {'state': 'SUCCEEDED' if job in {1, 4} else 'RUNNING', 'execNodes': 'x86-fixture'}
        with patch.object(watcher, 'query', side_effect=state), patch.object(watcher, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'owner changed'):
                watcher.maybe_submit(*self.args)
            prepare.assert_not_called()

    def test_failed_preflight_or_finished_q0_stops_without_submit(self):
        with patch.object(watcher, 'query', return_value={'state': 'FAILED'}):
            with self.assertRaisesRegex(ValueError, 'without success'):
                watcher.maybe_submit(*self.args)
        meta = self.work/'metadata'; meta.mkdir(); (meta/'grt_q0_evidence.json').write_text('preserve')
        state = lambda job: {'state': 'SUCCEEDED' if job in {1, 4} else 'RUNNING', 'execNodes': 'x86-fixture'}
        with patch.object(watcher, 'query', side_effect=state), patch.object(watcher, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'already completed'):
                watcher.maybe_submit(*self.args)
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
