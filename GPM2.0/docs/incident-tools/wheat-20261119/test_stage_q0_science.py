import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import stage_q0_science as stage


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);work=self.root/'work';work.mkdir()
        (work/'.prepare_lib/tools/lgz_core').mkdir(parents=True);(work/'metadata').mkdir()
        runtime=work/'.prepare_lib/tools/lgz_core/q0_preparation.py';runtime.write_text('old runtime')
        launcher=work/'prepare_q0_evidence.sh';launcher.write_text('old launcher');launcher.chmod(0o755)
        declaration=work/'metadata/incident_q0_routing_reader.json';declaration.write_text('{"old":true}')
        source=self.root/'new.py';source.write_text('new runtime')
        new_launcher=self.root/'new.sh';new_launcher.write_text('new launcher')
        row=lambda p:{'path':str(p),'sha256':stage.digest(p)}
        transition={'runtime':[{'relative':str(runtime.relative_to(work)),'prior_sha256':stage.digest(runtime),
                                'source':row(source),'new_sha256':stage.digest(source)}],
                    'launcher':row(new_launcher),'prior_launcher_sha256':stage.digest(launcher),
                    'prior_declaration_sha256':stage.digest(declaration)}
        self.ctx=SimpleNamespace(work=work,verify=lambda:None,transition=transition,transition_sha='bound',
            transition_path=self.root/'transition.json',
            helper=SimpleNamespace(LAUNCHER=launcher.name,RECEIPT=str(declaration.relative_to(work))),
            contract=SimpleNamespace(atomic_write_json=lambda p,x:p.write_text(json.dumps(x))))
        self.lock=SimpleNamespace(acquired=True,server_dir=work,run_id='current',_existing_owner=lambda:{'run_id':'current'})
        self.paths=[runtime,launcher,declaration];self.before=[p.read_bytes() for p in self.paths]
        self.declaration=lambda:{'scientific_builder_modified':True,'native_checkpoint_rewritten':False,'transition_sha256':'bound'}

    def install(self,declare=None):return stage.install(self.ctx,self.lock,declare or self.declaration)

    def test_installs_exact_slice_with_backups_and_truthful_declaration(self):
        journal=self.install();report=json.loads(journal.read_text())
        self.assertEqual(report['status'],'installed')
        self.assertEqual(self.paths[0].read_text(),'new runtime')
        self.assertEqual(self.paths[1].stat().st_mode&0o777,0o755)
        self.assertEqual(json.loads(self.paths[2].read_text()),self.declaration())
        self.assertEqual([Path(r['backup']).read_bytes() for r in report['files']],self.before)

    def test_failure_restores_all_bytes_and_retains_journal(self):
        def failure():raise RuntimeError('reader failed')
        with self.assertRaisesRegex(RuntimeError,'reader failed'):self.install(failure)
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)
        self.assertEqual(json.loads((self.root/'installation/receipt.json').read_text())['status'],'rolled_back')

    def test_mislabelled_science_rolls_back(self):
        with self.assertRaisesRegex(ValueError,'declaration'):self.install(lambda:{'scientific_builder_modified':False})
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)

    def test_missing_new_runtime_is_removed_on_rollback(self):
        self.paths[0].unlink();self.ctx.transition['runtime'][0]['prior_sha256']=None
        with self.assertRaises(ValueError):self.install(lambda:{})
        self.assertFalse(self.paths[0].exists())
        self.assertEqual(self.paths[1].read_bytes(),self.before[1])

    def test_owner_identity_is_required(self):
        self.lock._existing_owner=lambda:{'run_id':'other'}
        with self.assertRaisesRegex(ValueError,'ownership'):self.install()
        self.assertFalse((self.root/'installation').exists())

    def test_prior_drift_is_rejected_before_installation(self):
        self.paths[0].write_text('external edit')
        with self.assertRaisesRegex(ValueError,'prior identity'):self.install()
        self.assertFalse((self.root/'installation').exists())
        self.assertEqual(self.paths[1].read_bytes(),self.before[1])

    def test_published_evidence_and_existing_journal_are_not_overwritten(self):
        manifest=self.ctx.work/'metadata/grt_q0_evidence.json';manifest.write_text('{}')
        with self.assertRaisesRegex(ValueError,'published'):self.install()
        manifest.unlink();(self.root/'installation').mkdir()
        with self.assertRaisesRegex(ValueError,'journal'):self.install()
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)

    def test_replacement_failure_rolls_back_prior_replacements(self):
        actual=stage.atomic_bytes
        def replacement(path,data,mode):
            if data==b'new launcher':raise OSError('simulated rename failure')
            return actual(path,data,mode)
        with patch.object(stage,'atomic_bytes',replacement):
            with self.assertRaises(OSError):self.install()
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)


if __name__=='__main__':unittest.main()
