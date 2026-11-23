import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_q0_loader_launch as launch
from q0_buffered_proof import verify_buffered_proof
import q0_science_handoff_gate as gate
import q0_buffered_proof as verifier


class BufferedProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.stage = self.root/'staged'; self.stage.mkdir()
        self.probe = self.root/'probe'; self.probe.mkdir()
        self.work = self.root/'work'; self.work.mkdir()
        control = self.root/'control'; control.mkdir()
        self.control = control
        self.gate = control/'q0_science_handoff_gate.py'; self.gate.write_text('fixture gate')
        self.verifier = control/'q0_buffered_proof.py'; self.verifier.write_text('fixture verifier')
        old = self.root/'old'; old.mkdir()
        for n in ('run.dsub','probe_q0_buffered_preflight.py','test_probe_q0_buffered_preflight.py','buffered_reader.py'):
            (self.probe/n).write_text(n)
        self.env = self.root/'env.sh'; self.env.write_text('env')
        initial = self.work/'prepare_q0_evidence.sh'; initial.write_text('launcher')
        declare = self.work/'metadata/incident_q0_routing_reader.json'; declare.parent.mkdir(); declare.write_text('decl')
        rel = '.prepare_lib/tools/lgz_core/q0_regional_mapping.py'
        target = self.work/rel; target.parent.mkdir(parents=True); target.write_text('old code')
        staged = self.stage/'candidate.py'; staged.write_text('new code')
        self.prior = self.put(old/'transition.json',{'previous':True})
        self.transition = self.put(self.stage/'transition.json',{
            'workspace':str(self.work),'native_origin':{'sha256':'original'},'dependencies':{'context':{'authentic':True}},
            'regional_mapper_loader_policy':launch.POLICY,'prior_launcher_sha256':launch.record(initial)['sha256'],
            'prior_declaration_sha256':launch.record(declare)['sha256'],'runtime':[{'relative':rel,'source':launch.record(staged),
            'prior_sha256':launch.record(target)['sha256'],'new_sha256':launch.record(staged)['sha256']}]})
        stage = self.put(self.stage/'candidate-prepared.json',{'status':'q0_candidate_prepared_not_installed',
            'job_stopped':False,'workspace_modified':False,'transition':self.transition,'previous_transition':self.prior,
            'previous_job':10,'protected_baseline':20})
        self.rows = []
        for unit in ['ref:a','ref:b','assign',*[f'q0_chr:{i}' for i in range(22)]]:
            label = ''.join(c if c.isalnum() else '-' for c in unit)
            h = hashlib.sha256(json.dumps(unit).encode()).hexdigest()[:16]
            path = self.work/f'.run_all/checkpoints/{label}.{h}.json'; path.parent.mkdir(parents=True,exist_ok=True)
            row = self.put(path,{'complete':unit}); self.rows.append({'unit_id':unit,'input_fingerprint':'e'*64,'checkpoint_sha256':row['sha256']})
        flags = {'workspace_modified':False,'main_task_submitted':False,'q0_runtime_installed':False}
        previous = self.put(old/'validation.json',{'status':'q0_transition_all_initial_checkpoints_verified_only',
            'transition_sha256':self.prior['sha256'],'initial_checkpoints':self.rows,**flags})
        origin = self.put(self.probe/'origin-probe.json',{'workspace':str(self.work),'native_origin':{'sha256':'original'},
            'phase':'origin_probe','scientific_builder_modified':False,'dependencies':{'context':{'authentic':True},
            'probe':launch.record(self.probe/'probe_q0_buffered_preflight.py')}})
        bound = {'candidate_prepared':stage,'original_staged_transition':self.transition,'previous_transition':self.prior,
                 'previous_report':previous,'origin_probe':origin,'candidate_reader':launch.record(self.probe/'buffered_reader.py')}
        self.put(self.probe/'config.json',bound)
        self.proof = self.put(self.probe/'buffered-proof.json',{'status':'buffered_preflight_probe_only_no_handoff_authority',
             'bindings':bound,'initial_checkpoints':self.rows,**flags})
        self.terminal = self.put(self.probe/'terminal-30.json',{'data':{'successData':[{'jobId':'30','state':'SUCCEEDED',
             'jobExitCode':0,'queue':'x86','taskExecNodesCount':1,'execPath':str(self.probe),'cmd':str(self.probe/'run.dsub')}]}})
        (self.probe/'submit.txt').write_text('Submit job <30> successfully.\n')
        self.put(self.probe/'submission.intent',{'operation':'once_read_only_after_timeout','prior':{'jobId':'9','state':'FAILED',
             'jobExitCode':124},'main_job':'10','protected_baseline':'20'})
        watched = self.put(self.stage/'loader-watcher-3h-config.json',{'preflight_job':9,'transition':self.transition})
        (self.probe/'job.sha256').write_text(''.join(launch.record(p)['sha256']+'  '+p.name+'\n' for p in
            sorted([*self.probe.glob('*.py'),self.probe/'run.dsub'])))
        (self.probe/'config.sha256').write_text('fixture')
        self.put(self.probe/'retry-launcher.json',{'existing_watch':watched['path'],'existing_watch_sha256':watched['sha256'],
            **{name:launch.record(self.probe/name)['sha256'] for name in ('job.sha256','config.sha256')}})
        smoke = self.stage/'smoke-v2/smoke.jsonl'; smoke.parent.mkdir()
        self.put(smoke,{'status':'real_regional_writer_parity_and_old_reader_reuse','production_modified':False,
            'old_project_receipts':[{'project':'a'},{'project':'b'}],
            'new_execution_in_isolated_dir':[{'mode':m,'child_loader':{'policy':launch.POLICY}} for m in ('precise','chaining')]})
        for name in ('live-sample.json','probe_q0_loader_allocation.py'):
            (self.stage/name).write_text('fixture')

    @staticmethod
    def put(path,value):
        path.write_text(json.dumps(value))
        return launch.record(path)

    def verify(self):
        return verify_buffered_proof(self.stage,self.transition,self.proof,self.terminal)

    def test_real_envelope_feeds_launch_and_both_checks_without_forging_legacy_file(self):
        self.assertEqual(self.verify(),self.rows)
        with patch.object(launch,'__file__',str(self.control/'prepare_q0_loader_launch.py')):
            launch.prepare(self.stage,self.env,buffered_proof=Path(self.proof['path']),buffered_scheduler=Path(self.terminal['path']))
        config = json.loads((self.stage/'handoff-config.json').read_text())
        self.assertEqual(config['initial_preflight'],self.proof)
        self.assertIn(str(self.gate),(self.stage/'resume.dsub').read_text())
        self.assertFalse((self.stage/'validation.json').exists())
        with patch.object(gate,'__file__',str(self.gate)),patch.object(verifier,'__file__',str(self.verifier)):
            gate.validate_initial(config,self.stage)
            (self.probe/'run.dsub').write_text('changed program')
            with self.assertRaisesRegex(ValueError,'changed/unbound'):
                gate.validate_initial(config,self.stage)

    def test_terminal_job_and_immutable_initial_file_required(self):
        doc = json.loads(Path(self.terminal['path']).read_text())
        doc['data']['successData'][0]['jobId'] = '31'
        self.terminal = self.put(Path(self.terminal['path']),doc)
        with self.assertRaisesRegex(ValueError,'verified path'):
            self.verify()
        doc['data']['successData'][0]['jobId'] = '30'
        self.terminal = self.put(Path(self.terminal['path']),doc)
        next((self.work/'.run_all/checkpoints').glob('assign*')).write_text('changed')
        with self.assertRaisesRegex(ValueError,'receipt changed'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
