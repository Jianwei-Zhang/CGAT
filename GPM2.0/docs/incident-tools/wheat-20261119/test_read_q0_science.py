from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import read_q0_science as reader


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.extra=[{'path':'native-success.json','sha256':'bound'}]
        self.module=SimpleNamespace(_initial_inputs=lambda root:(None,None,None,None,['input.fa'],[],set()),builder_identity=lambda:'changed-builder')
        self.original=self.module._initial_inputs
        old=SimpleNamespace(provenance_inputs=lambda ctx:self.extra)
        self.ctx=SimpleNamespace(work=self.work,plan={'dependencies':{'reader':{'path':'old-reader'}}},
            plan_sha='native-plan',transition_sha='new-transition',transition={'launcher':{'sha256':'new-launcher'}},
            native_bootstrap=SimpleNamespace(module=lambda *a:old),cross=SimpleNamespace(plan_hash='cross'),
            selfs=SimpleNamespace(profiles={}),contract=SimpleNamespace(sha256_file=lambda p:'new-reader'),verify=lambda:None)
        self.ctx.helper=SimpleNamespace(prepare_with_reader=self.prepare)
        mock=patch.object(reader,'checked',lambda row:Path(row['path']));mock.start();self.addCleanup(mock.stop)

    def prepare(self,module,root,checkpoint_reader,ctx,record,**kwargs):
        self.record=record
        return {'inputs':[{'path':p} for p in module._initial_inputs(root)[4]]}

    def execute(self):return reader.prepare(self.ctx,self.module,object(),threads=32,minimap2='minimap2')

    def test_truthful_declaration_preserves_initial_profile_and_extra_inputs(self):
        result=self.execute()
        self.assertTrue(self.record['scientific_builder_modified'])
        self.assertFalse(self.record['initial_alignment_profiles_modified'])
        self.assertFalse(self.record['native_checkpoint_rewritten'])
        self.assertEqual(self.record['scientific_builder_identity'],'changed-builder')
        self.assertIn({'path':'native-success.json'},result['inputs'])
        self.assertIs(self.module._initial_inputs,self.original)

    def test_loader_policy_is_bound_to_the_immutable_reader_declaration(self):
        self.ctx.transition['regional_mapper_loader_policy'] = 'clear_same_dependencies_v1'
        self.execute()
        self.assertEqual(self.record['regional_mapper_loader_policy'], 'clear_same_dependencies_v1')
        self.assertFalse(self.record['initial_alignment_profiles_modified'])

    def test_missing_provenance_is_rejected(self):
        self.ctx.helper.prepare_with_reader=lambda *a,**kw:{'inputs':[]}
        with self.assertRaisesRegex(ValueError,'missing'):self.execute()
        self.assertIs(self.module._initial_inputs,self.original)

    def test_provenance_drift_is_rejected(self):
        def changed(*args,**kwargs):
            result=self.prepare(*args,**kwargs);self.extra=[{'path':'different.json'}];return result
        self.ctx.helper.prepare_with_reader=changed
        with self.assertRaisesRegex(ValueError,'provenance changed'):self.execute()
        self.assertIs(self.module._initial_inputs,self.original)

    def test_wrong_workspace_and_changed_tuple_fail_closed(self):
        def wrong(module,*args,**kwargs):module._initial_inputs(self.work.parent)
        self.ctx.helper.prepare_with_reader=wrong
        with self.assertRaisesRegex(ValueError,'workspace'):self.execute()
        self.assertIs(self.module._initial_inputs,self.original)
        self.ctx.helper.prepare_with_reader=self.prepare;self.module._initial_inputs=lambda root:(None,)
        with self.assertRaisesRegex(ValueError,'contract'):self.execute()


    def test_fresh_description_uses_genuine_reader_process_not_parent_package_reload(self):
        self.ctx.transition['dependencies']={'reader':{'path':str(self.work/'reader.py')}}
        self.ctx.transition_path=self.work/'transition.json'
        record={'reader_sha256':'new-reader','transition_sha256':'new-transition','scientific_builder_modified':True}
        with patch.object(reader.subprocess,'run',return_value=SimpleNamespace(stdout=__import__('json').dumps(record))) as run:
            self.assertEqual(reader.describe_in_fresh_process(self.ctx),record)
        command=run.call_args.args[0]
        self.assertEqual(command[0],reader.sys.executable)
        self.assertEqual(command[3],str(self.work/'reader.py'))
        self.assertIn('--describe-only',command);self.assertTrue(run.call_args.kwargs['check'])

    def test_fresh_description_refuses_another_builder_origin(self):
        self.ctx.transition['dependencies']={'reader':{'path':str(self.work/'reader.py')}}
        self.ctx.transition_path=self.work/'transition.json'
        record={'reader_sha256':'other','transition_sha256':'new-transition','scientific_builder_modified':True}
        with patch.object(reader.subprocess,'run',return_value=SimpleNamespace(stdout=__import__('json').dumps(record))):
            with self.assertRaisesRegex(ValueError,'unbound'):reader.describe_in_fresh_process(self.ctx)


if __name__=='__main__':unittest.main()
