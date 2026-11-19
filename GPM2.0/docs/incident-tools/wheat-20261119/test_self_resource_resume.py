import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'server/tools'))
import alignment_tasks
import stage_self_resource_resume as staging
import resume_self_resources as wrapper


class ResourceOverlayTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.work=self.root/'work';self.work.mkdir();(self.work/'.prepare_lib').mkdir()
        (self.work/'.prepare_lib/tools').symlink_to(Path(alignment_tasks.__file__).parent,target_is_directory=True)
        self.launcher=self.work/'prepare_q0_evidence.sh';self.launcher.write_text('old launcher')
        self.entry=self.root/'old-entry.py';self.entry.write_text('# frozen entry fixture\n')
        self.reader=self.root/'old-reader.py';self.reader.write_text('# frozen reader fixture\n')
        self.native=self.work/'self_batch_manifest.json'
        batches=[];self.dirs=[]
        for i in range(2):
            d=self.work/f'batch-{i}';d.mkdir();self.dirs.append(d)
            batches.append({'directory':str(d),'key':f'native-{i}',
                'query_sha256':hashlib.sha256(str(i).encode()).hexdigest(),'entries':[{'length':220_000_000}]})
        self.native.write_text(json.dumps({'batches':batches,'target_lengths':{'t':731_737_596}}))
        policy={'scope':'q0_self_single_whole_record','seed_fraction':'0.005','minimum_query_bases':100_000_000,
                'native_flags_unchanged':True,'mapper_timeout_seconds':None}
        self.profile=self.root/'profile.json';self.profile.write_text(json.dumps({'policy':policy,'selected_batches':[0,1],
            'native_manifest':staging.record(self.native)}))
        for i,d in enumerate(self.dirs):
            for name,text in [('raw.paf','raw fixture'),('result.paf','restored fixture'),
                ('stderr.log','[M::worker_pipeline::1] mapped 1 sequences\nReal time: 1 sec; Peak RSS: 5.8 GB\n')]:
                (d/name).write_text(text)
            outputs={name:staging.digest(d/name) for name in ('raw.paf','result.paf','stderr.log')}
            receipt={'status':'complete','profile_sha256':staging.digest(self.profile),'native_key':f'native-{i}',
                'key':f'profile-{i}','batch_index':i,'policy':policy,'outputs':outputs,'mapping':{'returncode':0},
                'command':['minimap2','-f','0.005','index','query']}
            (d/'self-profile-receipt.json').write_text(json.dumps(receipt))
            (d/'complete.json').write_text(json.dumps({'key':f'profile-{i}','outputs':outputs}))
        scripts={}
        for i in range(2):
            p=self.root/f'script-{i}.sh';p.write_text('#!/bin/bash\nexit 0\n');scripts[str(i)]=staging.file_record(p)
        self.origin={'schema':'incident_self_dispatch_v1','preview_only':False,'workspace':str(self.work),
            'dependencies':{'entry':staging.record(self.entry),'reader':staging.record(self.reader),'launcher':staging.record(self.launcher)},
            'resource_policy':{'max_fast':1},'operations':[{'operation':'runs/chr_X/a_vs_self','unit_id':'q0_chr:X',
                'profile':staging.record(self.profile),'scripts':scripts,'native_commands':{'0':'unchanged'},'task_manifest':'unchanged'}]}
        self.origin_path=self.root/'origin.json';self.origin_path.write_text(json.dumps(self.origin))
        self.output=self.root/'overlay'

    def stage(self):
        proof=staging.stage(self.origin_path,self.output)
        return json.loads((self.output/'self-plan.json').read_text()),proof

    def test_stage_changes_only_resources_preserving_old_profiles_and_keys(self):
        before=self.profile.read_bytes();plan,proof=self.stage()
        self.assertTrue(proof['scientific_profiles_preserved']);self.assertEqual(proof['completed_calibrations'],2)
        self.assertEqual(plan['operations'][0]['profile'],self.origin['operations'][0]['profile'])
        self.assertEqual(self.profile.read_bytes(),before)
        self.assertEqual(self.launcher.read_text(),'old launcher')
        staging.verify_transition(plan,self.origin)
        for row in plan['operations'][0]['scripts'].values():
            self.assertIn('--limit-bytes 68719476736',Path(row['path']).read_text())

    def test_missing_second_complete_calibration_rejected(self):
        (self.dirs[1]/'complete.json').unlink()
        with self.assertRaisesRegex(ValueError,'two distinct'):staging.stage(self.origin_path,self.output)
        self.assertFalse(self.output.exists())

    def test_corrupt_calibration_rejected(self):
        (self.dirs[0]/'result.paf').write_text('changed')
        with self.assertRaisesRegex(ValueError,'output changed'):staging.stage(self.origin_path,self.output)

    def test_changed_profile_or_execution_dependency_rejected(self):
        self.entry.write_text('changed')
        with self.assertRaisesRegex(ValueError,'execution dependency'):staging.stage(self.origin_path,self.output)

    def test_completed_q0_or_existing_output_not_overwritten(self):
        (self.work/'metadata').mkdir();(self.work/'metadata/grt_q0_evidence.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'already published'):staging.stage(self.origin_path,self.output)
        (self.work/'metadata/grt_q0_evidence.json').unlink();self.output.mkdir()
        with self.assertRaises(ValueError):staging.stage(self.origin_path,self.output)

    def test_guard_and_profile_substitution_rejected(self):
        plan,_=self.stage()
        for edit in ('profile','guard','dependency'):
            changed=copy.deepcopy(plan)
            if edit=='profile':changed['operations'][0]['profile']['sha256']='changed'
            elif edit=='guard':changed['resource_guard']['scripts'].clear()
            else:changed['dependencies']['reader']['sha256']='changed'
            with self.subTest(edit=edit),self.assertRaises(ValueError):staging.verify_transition(changed,self.origin)

    def test_wrapper_runs_exact_old_entry_and_restores_module_selection(self):
        plan,_=self.stage();old=list(sys.path);argv=list(sys.argv);before=sys.modules.get('self_profile_admission')
        with patch.object(wrapper.runpy,'run_path',return_value={}) as run:
            wrapper.execute(self.output/'self-plan.json',install_reader=True)
        run.assert_called_once_with(str(self.entry),run_name='__main__')
        self.assertEqual(sys.path,old);self.assertEqual(sys.argv,argv)
        self.assertIs(sys.modules.get('self_profile_admission'),before)

    def test_wrapper_rejects_changed_guard_code_before_entry(self):
        plan,_=self.stage();plan['dependencies']['memory_guard']['sha256']='changed'
        (self.output/'self-plan.json').write_text(json.dumps(plan))
        with patch.object(wrapper.runpy,'run_path') as run:
            with self.assertRaisesRegex(ValueError,'dependency changed'):wrapper.execute(self.output/'self-plan.json')
        run.assert_not_called()

if __name__=='__main__':unittest.main()
