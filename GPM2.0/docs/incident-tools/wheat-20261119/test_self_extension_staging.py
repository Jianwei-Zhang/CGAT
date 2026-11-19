import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_composite_self_profile as fixtures
import stage_self_extension as staging
import stage_self_profile as original_staging
import self_profile_bindings as bindings
import self_two_lane_admission as admission
import self_extension_context as bootstrap
import self_seed_profile as original_runtime


class ExtensionStagingTests(unittest.TestCase):
    def setUp(self):
        self.fx=fx=fixtures.CompositeTests();fx.setUp();self.addCleanup(fx.doCleanups)
        f=fx.fx;self.f=f
        (f.work/'prepare_q0_evidence.sh').write_text('old launcher')
        commands={}
        for i,b in enumerate(f.native['batches']):
            path=Path(b['directory'])/'command.sh';path.write_text('original command '+str(i))
            commands[str(i)]=f.profile.contract.file_identity(path,relative_to=f.work)
        task_file=f.op.parent/'q0_alignment_tasks.json'
        task_file.write_text(json.dumps({'tasks':[{'command':v['path']} for v in commands.values()]}))
        script=f.root/'old-guard.sh';script.write_text('frozen original guarded command')
        script_row=staging.file_record(script)
        here=Path(staging.__file__).parent
        self.parent={'schema':bindings.SCHEMA,'workspace':str(f.work),'preview_only':False,
            'dependencies':{name:f.row(here/namefile) for name,namefile in original_staging.MODULES.items()},
            'resource_policy':{'max_fast':2,'reservation_policy':admission.POLICY},
            'resource_guard':{'scope':'per_process_virtual_address_space','limit_bytes':staging.LIMIT,
                'scripts':{str(script):{'guarded_script_sha256':script_row['sha256'],'source':script_row}}},
            'operations':[{'operation':f.op.relative_to(f.work).as_posix(),'unit_id':'q0_chr:X','profile':f.row(f.path),
                'scripts':{'0':script_row},'task_manifest':f.row(task_file),'native_commands':commands}]}
        self.parent['dependencies']['admission']=f.row(here/'self_two_lane_admission.py')
        self.parent['dependencies']['memory_guard']=f.row(here/'self_memory_guard.py')
        self.parent_path=f.root/'parent-plan.json';self.parent_path.write_text(json.dumps(self.parent))
        self.candidate=f.root/'candidate-report.json';self.candidate.write_text('{}')
        self.output=f.root/'staged-extension'
        # The production candidate gate is separately checked against real data;
        # this tiny fixture isolates metadata migration, not mapping evidence.
        mock=patch.object(staging,'calibration',return_value=((self.parent['operations'][0]['operation'],1),
            {'report':f.row(self.candidate),'mapping':{'returncode':0},'scope':'synthetic fixture'}))
        mock.start();self.addCleanup(mock.stop)

    def stage(self):
        proof=staging.stage(self.parent_path,self.output,self.candidate)
        return json.loads((self.output/'self-plan.json').read_text()),proof

    def test_extension_preserves_original_profile_script_and_completed_bytes(self):
        old=self.f.path.read_bytes();plan,proof=self.stage()
        self.assertEqual(proof['extension_batches'],1)
        row=plan['operations'][0];prior=self.parent['operations'][0]
        self.assertEqual(row['scripts']['0'],prior['scripts']['0'])
        self.assertEqual(row['native_commands'],prior['native_commands'])
        self.assertEqual(self.f.path.read_bytes(),old)
        self.assertEqual(self.fx.before,{n:(self.f.directory/n).read_bytes() for n in self.fx.before})
        self.assertEqual((self.f.work/'prepare_q0_evidence.sh').read_text(),'old launcher')
        self.assertIn('PYTHONPATH=',Path(plan['resource_guard']['scripts'][row['scripts']['1']['path']]['source']['path']).read_text())
        staging.verify_transition(plan,self.parent)

    def test_completed_native_before_staging_is_never_reprofiled(self):
        self.f.publish_native_small()
        marker=Path(self.f.native['batches'][1]['directory'])/'complete.json';before=marker.read_bytes()
        with self.assertRaisesRegex(ValueError,'no unfinished'):self.stage()
        self.assertEqual(marker.read_bytes(),before)

    def test_native_completion_after_staging_requires_restage_not_overwrite(self):
        plan,_=self.stage();self.f.publish_native_small()
        with self.assertRaisesRegex(ValueError,'completed since staging'):staging.verify_transition(plan,self.parent)

    def test_scientific_dependency_or_original_script_substitution_rejected(self):
        plan,_=self.stage()
        for field in ('runtime','script'):
            changed=copy.deepcopy(plan)
            if field=='runtime':changed['dependencies']['runtime']['sha256']='changed'
            else:changed['operations'][0]['scripts']['0']['sha256']='changed'
            with self.subTest(field=field),self.assertRaises(ValueError):staging.verify_transition(changed,self.parent)

    def test_bootstrap_composes_real_bindings_and_restores_module_selection(self):
        plan,_=self.stage();old={name:sys.modules.get(name) for name in
            ('self_seed_profile','self_profile_admission','self_profile_context','self_profile_bindings')}
        # Preserve the patched tiny legacy fixture under an exact-file alias.
        with patch.dict(sys.modules,{'original_profile_fixture':original_runtime}):
            with bootstrap.installed(self.output/'self-plan.json',role='extension_entry',
                    caller=plan['dependencies']['extension_entry']['path']):
                from self_profile_bindings import SelfBindings
                actual=SelfBindings(self.f.work,self.output/'self-plan.json',self.f.profile.contract)
                profile=next(iter(actual.profiles.values()))
                self.assertEqual(profile.selected,[0,1]);self.assertTrue(profile.validate_batch(0))
                self.assertEqual(actual.rows[self.parent['operations'][0]['operation']]['scripts']['0'],
                                 self.parent['operations'][0]['scripts']['0'])
        for name,value in old.items():self.assertIs(sys.modules.get(name),value)


if __name__=='__main__':unittest.main()
