import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import await_buffered_preflight_retry as watch


class TestBufferedRetry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bundle = self.root/'probe'; self.bundle.mkdir()
        self.original = self.root/'original'; self.original.mkdir()
        work = self.root/'work'; (work/'.run_all/lock').mkdir(parents=True)
        self.write(work/'.run_all/lock/owner.json',{'workspace':str(work),'run_id':'test','hostname':'node'})
        t = self.original/'transition.json'; self.write(t,{'workspace':str(work)})
        transition = {'path':str(t),'sha256':watch.sha(t)}
        self.write(self.bundle/'config.json',{'original_staged_transition':transition})
        replay = self.original/'preflight-3h.dsub'; replay.write_text('diagnostic')
        self.write(self.original/'preflight-3h-retry-submitted.json',{'new_preflight':1,
                   'scope':'read_only_same_25_checks','script_sha256':watch.sha(replay)})
        w = self.original/'watch.json'; self.write(w,{'preflight_job':1,'running_job':2,'baseline_job':3,
                                                   'running_run_id':'test','smoke_job':4,'transition':transition})
        self.config = {'existing_watch':str(w),'existing_watch_sha256':watch.sha(w)}
        for name in ('job.sha256','config.sha256'):
            f = self.bundle/name; f.write_text(name)
            self.config[name] = watch.sha(f)
        self.jobs = {1:{'jobId':1,'state':'FAILED','jobExitCode':124,'endTime':'at',
                        'cmd':str(replay),'execPath':str(self.original),
                        'resGroups':[{'nodeResUsages':[{'pids':'-'}]}]},
                     2:{'jobId':2,'state':'RUNNING','taskExecNodes':'node'},3:{'jobId':3,'state':'RUNNING'},
                     4:{'jobId':4,'state':'SUCCEEDED','jobExitCode':0}}
        self.commands = []

    @staticmethod
    def write(p,data):
        p.write_text(json.dumps(data))

    def attempt(self,result='Submit job <5> successfully.'):
        def run(cmd,**args):
            self.commands.append(cmd)
            return SimpleNamespace(stdout=result)
        with patch.object(watch,'query',side_effect=self.jobs.__getitem__), patch.object(watch.subprocess,'run',side_effect=run):
            return watch.maybe_retry(self.bundle,self.config)

    def test_original_running_or_success_never_submits(self):
        for state, end in (('RUNNING','-'),('SUCCEEDED','at')):
            self.jobs[1].update(state=state,endTime=end)
            self.assertIsNone(self.attempt()[1])
        self.assertFalse(self.commands)

    def test_only_expected_timeout_without_remaining_processes(self):
        self.jobs[1]['resGroups'][0]['nodeResUsages'][0]['pids'] = '123'
        self.assertEqual(self.attempt(),('waiting_for_old_diagnostic_processes_to_exit',None))
        self.jobs[1]['resGroups'][0]['nodeResUsages'][0]['pids'] = '-'
        self.jobs[1]['jobExitCode'] = 7
        self.assertEqual(self.attempt(),('original_preflight_terminal_not_retryable',None))
        self.assertFalse(self.commands)

    def test_existing_handoff_or_wrong_running_owner_refuses(self):
        ready = self.original/'ready.json'; ready.touch()
        with self.assertRaisesRegex(ValueError,'already has'):
            self.attempt()
        ready.unlink()
        self.jobs[2]['taskExecNodes'] = 'another'
        with self.assertRaisesRegex(ValueError,'owner changed'):
            self.attempt()
        self.assertFalse(self.commands)

    def test_verified_timeout_submits_once(self):
        self.assertEqual(self.attempt(),('new_buffered_probe_submitted',5))
        self.assertEqual(self.commands[-1],['dsub','-s','run.dsub'])
        self.assertIn('Submit job <5>',(self.bundle/'submit.txt').read_text())
        with self.assertRaisesRegex(ValueError,'already has output'):
            self.attempt()
        self.assertEqual(self.commands.count(['dsub','-s','run.dsub']),1)

    def test_ambiguous_dsub_keeps_intent_without_resubmitting(self):
        with self.assertRaisesRegex(ValueError,'ambiguous dsub'):
            self.attempt('transport lost')
        self.assertTrue((self.bundle/'submission.intent').is_file())
        with self.assertRaises(FileExistsError):
            self.attempt()
        self.assertEqual(self.commands.count(['dsub','-s','run.dsub']),1)


if __name__ == '__main__':
    unittest.main()
