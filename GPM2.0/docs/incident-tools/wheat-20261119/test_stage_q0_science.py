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


class ReferenceAdoptionTests(InstallationTests):
    def setUp(self):
        super().setUp()
        key='reference-index-'+'a'*24
        self.index_source=self.root/'isolated'/key;self.index_source.mkdir(parents=True)
        db=self.index_source/'reference.sqlite';db.write_bytes(b'fixture already-verified sealed database')
        receipt=self.index_source/'success.json'
        receipt.write_text(json.dumps({'status':'success','key':key,'inputs':[],
                                      'sha256':stage.digest(db),'size':db.stat().st_size}))
        self.ready=self.root/'ready.json'
        self.proof={'status':'complete_reference_cache_ready_for_owned_adoption','workspace_modified':False,
            'relative':'grt/evidence/q0_prepare/indexes/'+key,'source':str(self.index_source),
            'files':[{'name':p.name,'sha256':stage.digest(p),'size':p.stat().st_size} for p in (db,receipt)]}
        self.bind_ready()
        self.index_target=self.ctx.work/self.proof['relative']

    def bind_ready(self):
        self.ready.write_text(json.dumps(self.proof))
        self.ctx.transition['reference_index_adoption']={'path':str(self.ready),'sha256':stage.digest(self.ready)}

    def test_reference_is_atomically_moved_without_rebuilding_or_copying(self):
        inode=(self.index_source/'reference.sqlite').stat().st_ino
        journal=self.install()
        self.assertFalse(self.index_source.exists())
        self.assertEqual((self.index_target/'reference.sqlite').stat().st_ino,inode)
        self.assertTrue(json.loads(journal.read_text())['reference_index_adoption']['moved'])

    def test_runtime_failure_returns_the_whole_index_to_its_source(self):
        def fail():raise RuntimeError('new reader rejected')
        with self.assertRaises(RuntimeError):self.install(fail)
        self.assertTrue((self.index_source/'reference.sqlite').is_file())
        self.assertFalse(self.index_target.exists())
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)

    def test_changed_index_is_rejected_before_runtime_changes(self):
        (self.index_source/'reference.sqlite').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'content changed'):self.install()
        self.assertEqual([p.read_bytes() for p in self.paths],self.before)
        self.assertFalse((self.root/'installation').exists())

    def test_existing_destination_is_never_overwritten(self):
        self.index_target.mkdir(parents=True);(self.index_target/'preserved').write_text('original')
        with self.assertRaisesRegex(ValueError,'already exists'):self.install()
        self.assertTrue((self.index_target/'preserved').is_file())
        self.assertTrue(self.index_source.is_dir())

    def test_incomplete_and_linked_inputs_are_rejected(self):
        (self.index_source/'result.tmp').write_bytes(b'partial')
        with self.assertRaisesRegex(ValueError,'unexpected'):self.install()
        (self.index_source/'result.tmp').unlink()
        db=self.index_source/'reference.sqlite';real=self.root/'real-db';db.rename(real);db.symlink_to(real)
        with self.assertRaisesRegex(ValueError,'linked'):self.install()

    def test_ready_descriptor_drift_is_rejected(self):
        self.ready.write_text(self.ready.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'dependency'):self.install()



class MappingAdoptionTests(ReferenceAdoptionTests):
    def setUp(self):
        super().setUp()
        spec={'schema':'lgz_q0_mapping_v1','query_ids':['q'],'target_ids':['t'],
              'members':[['q','a'*64],['t','b'*64]],'tool':{},'preset':'asm10',
              'alignment_flags':['-D','-P','--dual=yes','--no-long-join','-m','2000']}
        key='q0-map-'+stage.hashlib.sha256(json.dumps(spec,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
        self.mapping_source=self.root/'isolated'/key;self.mapping_source.mkdir()
        relative='grt/evidence/q0_prepare/tasks/'+key;self.mapping_target=self.ctx.work/relative
        for name in ('query.fa','target.fa','result.paf','command.json'):(self.mapping_source/name).write_text('fixture '+name)
        outputs=[{'path':relative+'/'+name,'sha256':stage.digest(self.mapping_source/name),
                  'size':(self.mapping_source/name).stat().st_size} for name in ('query.fa','target.fa','result.paf','command.json')]
        (self.mapping_source/'success.json').write_text(json.dumps({'status':'success','spec':spec,'outputs':outputs}))
        self.mapping_ready=self.root/'mapping-ready.json'
        self.mapping_proof={'status':'complete_mapping_cache_ready_for_owned_adoption','source':str(self.mapping_source),
            'relative':relative,'task_id':key,'workspace_modified':False,'normal_cache_validation_completed':True}
        self.bind_mapping()

    def bind_mapping(self):
        self.mapping_proof['files']=[{'name':p.name,'sha256':stage.digest(p),'size':p.stat().st_size}
                                     for p in sorted(self.mapping_source.iterdir()) if p.is_file()]
        self.mapping_ready.write_text(json.dumps(self.mapping_proof))
        self.ctx.transition['mapping_adoptions']=[{'path':str(self.mapping_ready),'sha256':stage.digest(self.mapping_ready)}]

    def test_mapping_move_preserves_raw_bytes_and_file_inodes(self):
        inode=(self.mapping_source/'target.fa').stat().st_ino
        journal=self.install();record=json.loads(journal.read_text())
        self.assertFalse(self.mapping_source.exists())
        self.assertEqual((self.mapping_target/'target.fa').stat().st_ino,inode)
        self.assertTrue(record['mapping_adoptions'][0]['moved'])

    def test_mapping_failure_rolls_back_both_index_and_mapping(self):
        def fail():raise RuntimeError('declaration unavailable')
        with self.assertRaises(RuntimeError):self.install(fail)
        self.assertTrue(self.mapping_source.is_dir());self.assertTrue(self.index_source.is_dir())
        self.assertFalse(self.mapping_target.exists());self.assertFalse(self.index_target.exists())

    def test_raw_key_cannot_be_relabelled_after_parameter_change(self):
        path=self.mapping_source/'success.json';row=json.loads(path.read_text())
        row['spec']['alignment_flags'].remove('2000');path.write_text(json.dumps(row));self.bind_mapping()
        with self.assertRaisesRegex(ValueError,'normal receipt'):self.install()
        self.assertTrue(self.index_source.is_dir());self.assertFalse((self.root/'installation').exists())

    def test_success_receipt_must_match_actual_output_manifest(self):
        path=self.mapping_source/'success.json';row=json.loads(path.read_text())
        row['outputs'][0]['sha256']='0'*64;path.write_text(json.dumps(row));self.bind_mapping()
        with self.assertRaisesRegex(ValueError,'normal receipt'):self.install()

    def test_mapping_without_completed_cache_validation_is_rejected(self):
        self.mapping_proof['normal_cache_validation_completed']=False;self.bind_mapping()
        with self.assertRaisesRegex(ValueError,'normal receipt'):self.install()

    def test_mapping_tmp_and_hard_links_are_not_adopted(self):
        temporary=self.mapping_source/'result.paf.tmp';temporary.write_text('partial')
        with self.assertRaisesRegex(ValueError,'unexpected'):self.install()
        temporary.unlink();(self.root/'external-target').hardlink_to(self.mapping_source/'target.fa')
        with self.assertRaisesRegex(ValueError,'linked'):self.install()

    def test_second_move_failure_restores_the_first_adoption(self):
        original=stage.move_reference
        def move(ctx,lock,row):
            if row['source']==str(self.mapping_source):raise OSError('second move failed')
            return original(ctx,lock,row)
        with patch.object(stage,'move_reference',side_effect=move):
            with self.assertRaises(OSError):self.install()
        self.assertTrue(self.mapping_source.is_dir());self.assertTrue(self.index_source.is_dir())
        self.assertFalse(self.mapping_target.exists());self.assertFalse(self.index_target.exists())


if __name__=='__main__':unittest.main()
