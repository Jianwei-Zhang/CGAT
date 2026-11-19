import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_self_profile_bindings as self_fixtures
import test_routing_resume_support as cross_fixtures
import self_profile_bindings as self_support
import self_profile_admission as admission
import self_profile_context as context
import self_profile_evidence_reader as reader_driver
import routing_q0_evidence_reader as reader_helper
import routing_resume_support as cross_support
import stage_self_profile as stager
import resume_with_self_profile as entry
from alignment_tasks import AlignmentTask
from lgz_core import q0_preparation as q0
import run_orchestration as contract


class AdmissionTests(unittest.TestCase):
    def dispatcher(self, *, max_fast=1, target=600_000_000, query=200_000_000):
        scripts = {str(i): {'path': '/isolated/fast-%s.sh' % i} for i in range(6)}
        batches = [{'directory': '/work/batch-%s' % i, 'entries': [{'length': query}]} for i in range(6)]
        profile = SimpleNamespace(native={'target_lengths': {'t': target}, 'batches': batches}, selected=list(range(6)))
        bindings = SimpleNamespace(profiles={'operation': profile}, rows={'operation': {'scripts': scripts}})
        dispatcher = admission.SelfDispatcher(bindings, lambda t: t.unit_id == 'exclusive', max_fast=max_fast)
        tasks = [AlignmentTask('fast', Path(scripts[str(i)]['path']), 1, work=100-i, largest_fraction=1) for i in range(6)]
        return dispatcher, tasks

    def test_fast_long_query_remains_exclusive_despite_low_observed_peak(self):
        d, tasks = self.dispatcher()
        selected = d(tasks, 16, 16, [], 32)
        self.assertEqual(len(selected), 1); self.assertEqual(sum(n for _, n in selected), 1)
        self.assertLessEqual(sum(d.cost(t) for t, _ in selected), admission.POLICY['reservation_pool_gib'])

    def test_conservative_calibration_allows_only_one_fast_query(self):
        d, tasks = self.dispatcher(max_fast=1)
        self.assertEqual(len(d(tasks, 16, 16, [], 32)), 1)

    def test_native_overlap_remains_capped_and_reservations_account_for_active_work(self):
        d, tasks = self.dispatcher()
        native = [AlignmentTask('native', Path('/native/%s.sh' % i), 1, work=1000-i) for i in range(3)]
        self.assertEqual(len(d(native, 16, 16, [], 32)), 2)
        active = [{'task': native[0], 'threads': 1}]
        selected = d(tasks, 15, 16, active, 32)
        self.assertEqual(selected, [])
        self.assertEqual(d(native, 15, 16, [{'task': tasks[0], 'threads': 1}], 32), [])

    def test_cross_and_unknown_keep_exclusivity(self):
        d, tasks = self.dispatcher()
        for task in (AlignmentTask('native', Path('/work/a_vs_b/command.sh'), 1, work=1000),
                     AlignmentTask('exclusive', Path('/unknown.sh'), 1, work=1000)):
            self.assertEqual(d([task] + tasks, 15, 16, [{'task': tasks[0], 'threads': 1}], 32), [])
            self.assertEqual([t for t, _ in d([task] + tasks, 16, 16, [], 32)], [task])
            self.assertEqual(d(tasks, 15, 16, [{'task': task, 'threads': 1}], 32), [])

    def test_oversized_targets_or_queries_not_granted_fast_overlap(self):
        for kw in ({'target': 1_000_000_001}, {'query': 300_000_001}):
            d, tasks = self.dispatcher(**kw)
            # Unknown external commands normally fail closed in native admission.
            d.native_exclusive = lambda _task: True
            self.assertNotIn(tasks[0].command, d.fast)
            self.assertEqual(len(d(tasks, 16, 16, [], 32)), 1)

    def test_cpu_and_process_slots_remain_hard_admission_bounds(self):
        d, tasks = self.dispatcher()
        self.assertEqual(len(d(tasks, 2, 16, [], 32)), 1)
        self.assertEqual(len(d(tasks, 16, 16, [], 1)), 1)
        self.assertEqual(d(tasks, 0, 16, [], 32), [])
        for count in (0, 2, 4, 5):
            with self.assertRaises(ValueError): self.dispatcher(max_fast=count)


class CombinedReaderTests(unittest.TestCase):
    def setUp(self):
        self.s = self_fixtures.SelfBindingTests(); self.s.setUp(); self.addCleanup(self.s.doCleanups)
        self.c = cross_fixtures.BindingTests(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        s, c = self.s, self.c
        c.work = s.fx.work; c.rel = 'runs/chr_X/left_vs_right/command.sh'
        c.command = c.work/c.rel; c.command.parent.mkdir(parents=True); c.command.write_text('native cross')
        c.task = AlignmentTask('q0_chr:X', c.command, 1)
        c.plan['workspace'] = str(c.work)
        c.plan['overrides'][0].update(unit_id='q0_chr:X', native_command=c.rel,
            native_command_sha256=contract.sha256_file(c.command), receipt=str(c.command.parent/'routing-receipt.json'))
        c.write_plan(); c.receipt()
        self.native, _old_writer = c.checkpoint_fixture()
        s.invoke(s.mapper)
        self.ctx = SimpleNamespace(work=c.work, contract=contract, plan_sha='self-plan-fixture',
            selfs=s.bindings, cross=c.bindings(), cross_support=cross_support,
            native_inputs=lambda task, assigned: c.inputs, assignment={}, helper=reader_helper)
        def verify(): self.ctx.cross.verify(); self.ctx.selfs.verify()
        self.ctx.verify = verify
        (c.work/'metadata').mkdir()
        (c.work/reader_helper.LAUNCHER).write_text('combined reader launcher')
        self.ctx.plan = {'preview_only': False, 'dependencies': {'launcher': s.fx.row(c.work/reader_helper.LAUNCHER)}}
        writer_type = context.compose(self.ctx, type(self.native))
        writer = writer_type(c.work)
        self.prepared = writer.prepare(c.task.unit_id, c.rel); writer.commit(self.prepared)
        self.reader = context.compose(self.ctx, type(self.native), readonly=True)
        self.original_inputs = lambda root: (None, None, None, None,
            ['source.fa', (c.command.parent/'result.paf').relative_to(root).as_posix(),
             (s.fx.op/'result.paf').relative_to(root).as_posix()], [], set())
        self.module = SimpleNamespace(OuterCheckpointManager=type(self.native), _initial_inputs=self.original_inputs,
            builder_identity=q0.builder_identity, load_verified_evidence=q0.load_verified_evidence,
            prepare_evidence=self.prepare_fixture)

    def prepare_fixture(self, root, *, threads, minimap2):
        manager = self.module.OuterCheckpointManager(root)
        valid, reason = manager.validate(manager.prepare(self.c.task.unit_id, self.c.rel))
        if not valid: raise ValueError(reason)
        paths = self.module._initial_inputs(root)[4]
        catalog = 'catalog.json'
        (root/catalog).write_text(json.dumps({'schema': q0.CATALOG_SCHEMA, 'base_alignments': [],
                                           'supplementary_alignments': [], 'evidence': {}}))
        inputs = [q0.identity(root, path) for path in paths]
        result = {'schema': q0.SCHEMA, 'status': 'success', 'policy': q0.POLICY,
            'builder': self.module.builder_identity(), 'inputs': inputs, 'outputs': [q0.identity(root,catalog)],
            'catalog': catalog, 'tool': {'fixture': True}}
        result['input_fingerprint'] = q0.stable_id('q0-evidence-input', {'inputs': inputs,
            'tool': result['tool'], 'policy': q0.POLICY, 'builder': result['builder']})
        (root/q0.MANIFEST).write_text(json.dumps(result))
        return result

    def execute(self):
        return reader_driver.prepare(self.ctx, self.module, self.reader, threads=1, minimap2='unused-fixture')

    def test_real_cross_and_self_adapters_compose_and_downstream_accepts_provenance(self):
        before = self.prepared.path.read_bytes()
        self.assertFalse(self.native.validate(self.native.prepare(self.c.task.unit_id,self.c.rel))[0])
        result = self.execute()
        self.assertEqual(q0.load_verified_evidence(self.c.work), result)
        paths = {r['path'] for r in result['inputs']}
        self.assertTrue(any(p.endswith('routing-receipt.json') for p in paths))
        self.assertTrue(any(p.endswith('self-profile-receipt.json') for p in paths))
        self.assertTrue(any(p.endswith('self_batch_result.json') for p in paths))
        self.assertEqual(self.prepared.path.read_bytes(), before)
        self.assertIs(self.module._initial_inputs, self.original_inputs)
        self.assertEqual(result['builder'], q0.builder_identity())

    def test_reader_cannot_commit(self):
        with self.assertRaisesRegex(ValueError, 'cannot publish'):
            self.reader(self.c.work).commit(self.prepared)

    def test_preview_plan_cannot_publish_evidence(self):
        self.ctx.plan['preview_only'] = True
        with self.assertRaisesRegex(ValueError, 'preview'): self.execute()
        self.assertFalse((self.c.work/q0.MANIFEST).exists())

    def test_wrong_launcher_is_rejected_before_publication(self):
        (self.c.work/reader_helper.LAUNCHER).write_text('old launcher')
        with self.assertRaisesRegex(ValueError, 'not installed'): self.execute()
        self.assertFalse((self.c.work/q0.MANIFEST).exists())

    def test_downstream_rejects_later_cross_and_self_receipt_changes(self):
        result = self.execute()
        for row in result['inputs']:
            if row['path'].endswith(('routing-receipt.json','self-profile-receipt.json')):
                path=self.c.work/row['path']; before=path.read_bytes(); path.write_bytes(before+b' ')
                with self.assertRaises(q0.Q0EvidenceError): q0.load_verified_evidence(self.c.work)
                path.write_bytes(before)

    def test_module_hooks_restored_after_builder_failure(self):
        with patch.object(self.module,'prepare_evidence',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError): self.execute()
        self.assertIs(self.module._initial_inputs,self.original_inputs)
        self.assertIs(self.module.OuterCheckpointManager,type(self.native))


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root=Path(temp.name)
        self.report=self.root/'candidate.json'; self.stderr=self.root/'stderr.log'

    def write(self, peak=13, status='moderate_candidate_complete_not_adopted'):
        self.stderr.write_text('[M::worker_pipeline::0] mapped 1 sequences\nReal time: 1 sec; Peak RSS: %s GB\n' % peak)
        data={'scope':'one_complete_self_query_moderate_candidate_only','status':status,'seed_fraction':'0.001',
              'mapping':{'returncode':0},'restoration':{'returncode':0},'analysis_workspace_modified':False,'candidate_adopted':False,'whole_records_preserved':True,
              'outputs':stager.pilot.identities([self.stderr])}
        self.report.write_text(json.dumps(data))

    def test_completed_calibration_does_not_authorize_long_query_concurrency(self):
        self.write(); self.assertEqual(stager.calibration(self.report)[1]['max_fast'],1)
        self.write(peak=33); self.assertEqual(stager.calibration(self.report)[1]['max_fast'],1)
        self.write(status='running')
        with self.assertRaises(ValueError): stager.calibration(self.report)

    def test_middle_fraction_is_not_silently_adoptable_as_f0001(self):
        self.write()
        data=json.loads(self.report.read_text()); data['seed_fraction']='0.002'
        self.report.write_text(json.dumps(data))
        with self.assertRaises(ValueError): stager.calibration(self.report)

    def test_changed_resource_log_not_used_for_admission(self):
        self.write(); self.stderr.write_text('forged low RSS')
        with self.assertRaisesRegex(ValueError,'resource evidence'): stager.calibration(self.report)


    def test_aggressive_calibration_requires_matching_complete_loss_audit(self):
        self.write(peak=5)
        data=json.loads(self.report.read_text())
        native=['minimap2','-c','index','query']
        data.update(scope='one_complete_self_query_candidate_only',
            status='candidate_complete_not_compared_not_adopted',native_command=native,
            command=native[:-2]+['-f','0.005']+native[-2:],driver_sha256=stager.pilot.digest(Path(stager.pilot.__file__)))
        for key in ('seed_fraction','whole_records_preserved','restoration'):data.pop(key)
        self.report.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'evidence-loss audit'):
            stager.calibration(self.report,'0.005')
        audit=self.root/'audit.json'
        audit.write_text(json.dumps({'status':'full_self_identity_strata_compared_not_adopted',
            'candidate_adopted':False,'analysis_workspace_modified':False,'checked_source_files':data['outputs']}))
        self.assertEqual(stager.calibration(self.report,'0.005',audit)[1]['max_fast'],1)
        audit.write_text('{}')
        with self.assertRaisesRegex(ValueError,'does not bind'):
            stager.calibration(self.report,'0.005',audit)


class ReaderInstallationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.work=self.root/'work';self.work.mkdir();self.stage=self.root/'stage';self.stage.mkdir()
        self.target=self.work/'prepare_q0_evidence.sh';self.target.write_text('old launcher');self.target.chmod(0o755)
        self.source=self.stage/'launcher';self.source.write_text('new launcher')
        self.ctx=SimpleNamespace(work=self.work,path=self.stage/'plan.json',plan_sha='plan',contract=contract,
            helper=SimpleNamespace(LAUNCHER=self.target.name,RECEIPT='metadata/incident_q0_routing_reader.json'),
            plan={'preview_only':False,'prior_launcher':stager.record(self.target),
                  'dependencies':{'launcher':stager.record(self.source)}})
        self.lock=SimpleNamespace(acquired=True,server_dir=self.work,run_id='run',_existing_owner=lambda:{'run_id':'run'})

    def test_install_backup_receipt_and_repeat_without_replacing_again(self):
        entry.install_reader(self.ctx,self.lock)
        self.assertEqual(self.target.read_text(),'new launcher')
        self.assertEqual((self.stage/'reader-installation/prepare_q0_evidence.sh').read_text(),'old launcher')
        self.assertEqual(self.target.stat().st_mode&0o777,0o755)
        before=self.target.stat().st_ino
        entry.install_reader(self.ctx,self.lock)
        self.assertEqual(before,self.target.stat().st_ino)

    def test_no_lock_preview_changed_source_or_published_evidence_rejected(self):
        self.lock.acquired=False
        with self.assertRaises(ValueError):entry.install_reader(self.ctx,self.lock)
        self.lock.acquired=True;self.ctx.plan['preview_only']=True
        with self.assertRaises(ValueError):entry.install_reader(self.ctx,self.lock)
        self.ctx.plan['preview_only']=False
        (self.work/'metadata').mkdir();(self.work/'metadata/grt_q0_evidence.json').write_text('{}')
        with self.assertRaises(ValueError):entry.install_reader(self.ctx,self.lock)
        self.assertEqual(self.target.read_text(),'old launcher')
        self.assertFalse((self.stage/'reader-installation').exists())

    def test_receipt_publication_failure_restores_original_launcher(self):
        with patch.object(contract,'atomic_write_json',side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):entry.install_reader(self.ctx,self.lock)
        self.assertEqual(self.target.read_text(),'old launcher')

    def test_linked_target_or_changed_target_not_overwritten(self):
        self.target.write_text('unexpected')
        with self.assertRaises(ValueError):entry.install_reader(self.ctx,self.lock)
        self.assertEqual(self.target.read_text(),'unexpected')



class StagingTests(unittest.TestCase):
    def setUp(self):
        self.s = self_fixtures.SelfBindingTests(); self.s.setUp(); self.addCleanup(self.s.doCleanups)
        self.f = self.s.fx
        self.cross = self.f.root/'cross-plan.json'
        self.cross.write_text(json.dumps({'schema':'incident_q0_routing_v1','workspace':str(self.f.work)}))
        (self.f.work/'prepare_q0_evidence.sh').write_text('old launcher retained')
        self.output = self.f.root/'new-staging'

    def test_preview_selects_long_batches_without_modifying_native_inputs(self):
        before = stager.pilot.identities([self.f.source, self.f.work/'prepare_q0_evidence.sh', *[t.command for t in self.s.tasks]])
        proof = stager.stage(self.f.work,self.cross,Path(reader_helper.__file__),self.output,preview=True)
        self.assertEqual(proof['approximate_batches'],1)
        self.assertTrue(proof['preview_only'])
        self.assertEqual(before,stager.pilot.identities([Path(p) for p in before]))
        plan=json.loads((self.output/'self-plan.json').read_text())
        self.assertEqual(plan['resource_policy']['max_fast'],1)
        self.assertEqual(len(plan['operations']),1)

    def test_existing_native_completion_excluded_without_erasing_marker(self):
        directory=self.f.directory
        for name in self_fixtures.runtime.OUTPUTS: (directory/name).write_text('native output fixture')
        self.f.profile.helper.publish(directory,'native-0',self_fixtures.runtime.OUTPUTS)
        marker=directory/'complete.json'; before=marker.read_bytes()
        proof=stager.stage(self.f.work,self.cross,Path(reader_helper.__file__),self.output,preview=True)
        self.assertEqual(proof['approximate_batches'],0)
        self.assertEqual(marker.read_bytes(),before)

    def test_final_plan_requires_completed_calibration(self):
        with self.assertRaisesRegex(ValueError,'requires completed'):
            stager.stage(self.f.work,self.cross,Path(reader_helper.__file__),self.output,preview=False)
        self.assertFalse(self.output.exists())

    def test_existing_staging_directory_is_not_overwritten(self):
        self.output.mkdir(); (self.output/'preserve').write_text('preserve')
        with self.assertRaisesRegex(ValueError,'new isolated'):
            stager.stage(self.f.work,self.cross,Path(reader_helper.__file__),self.output,preview=True)
        self.assertEqual((self.output/'preserve').read_text(),'preserve')


if __name__ == '__main__':
    unittest.main()
