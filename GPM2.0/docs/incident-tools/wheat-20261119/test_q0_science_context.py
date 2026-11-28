"""Transition identity fences; no real workspace or native mapping is used."""
from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import q0_science_context as context


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.work=self.root/'work';self.work.mkdir()
        self.caller=self.root/'probe.py';self.caller.write_text('# real caller\n')
        self.native=self.root/'native.json';self.native.write_text('{}')
        self.path=self.root/'transition.json'
        self.record={'schema':context.SCHEMA,'phase':'origin_probe','workspace':str(self.work),
            'scientific_builder_modified':False,'native_origin':self.row(self.native),
            'dependencies':{'context':self.row(Path(context.__file__).resolve()),'probe':self.row(self.caller)}}
        self.verifications=[]
        @contextmanager
        def native_libraries(row):
            context.checked(row)
            yield self.native,{'workspace':str(self.work)},object()
            context.checked(row)
        def origin(*args):
            return SimpleNamespace(verify=lambda:self.verifications.append('origin'),
                                   helper=SimpleNamespace(LAUNCHER='prepare_q0_evidence.sh'))
        for mock in [patch.object(context,'native_libraries',native_libraries),
                     patch.object(context,'origin_context',origin)]:
            mock.start();self.addCleanup(mock.stop)

    def row(self,path):return {'path':str(path),'sha256':context.digest(path)}
    def save(self):self.path.write_text(json.dumps(self.record))
    def opened(self,role='probe',installed=False,caller=None):
        self.save()
        return context.opened_transition(self.path,role=role,caller=caller or self.caller,require_installed=installed)

    def prepared(self):
        self.record.update(phase='prepared',scientific_builder_modified=True)
        self.record['dependencies']={'context':self.row(Path(context.__file__).resolve()),
                                    **{key:self.row(self.caller) for key in ('entry','reader','stager')}}
        source=self.root/'q0.py';source.write_text('# changed science\n')
        rel='.prepare_lib/tools/lgz_core/q0_preparation.py'
        self.record['runtime']=[{'relative':rel,'source':self.row(source),'new_sha256':context.digest(source)}]
        launcher=self.root/'launcher.sh';launcher.write_text('# new reader\n')
        self.record['launcher']=self.row(launcher)
        target=self.work/rel;target.parent.mkdir(parents=True);target.write_bytes(source.read_bytes())
        (self.work/'prepare_q0_evidence.sh').write_bytes(launcher.read_bytes())
        return source,target

    def test_actual_new_probe_keeps_origin_separate(self):
        with self.opened() as ctx:
            self.assertEqual(ctx.transition['scientific_builder_modified'],False)
            ctx.verify()
        self.assertEqual(len(self.verifications),3)

    def test_wrong_actual_caller_is_rejected(self):
        other=self.root/'other.py';other.write_text(self.caller.read_text())
        with self.assertRaisesRegex(ValueError,'caller/context'):
            with self.opened(caller=other):pass

    def test_probe_cannot_install_or_execute(self):
        for role,installed in [('probe',True),('entry',False),('stager',False)]:
            with self.assertRaisesRegex(ValueError,'origin-only'):
                with self.opened(role,installed):pass

    def test_origin_and_dependency_drift_rejected_at_exit(self):
        for path in (self.native,self.caller):
            original=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'dependency'):
                with self.opened():path.write_bytes(original+b'# changed')
            path.write_bytes(original)

    def test_plan_drift_rejected_at_exit(self):
        with self.assertRaisesRegex(ValueError,'plan changed'):
            with self.opened():self.path.write_text(self.path.read_text()+'\n')

    def test_installed_runtime_and_launcher_are_bound(self):
        source,target=self.prepared()
        with self.opened('entry',True):pass
        target.write_text('# unexpected runtime')
        with self.assertRaisesRegex(ValueError,'runtime is not installed'):
            with self.opened('reader',True):pass
        target.write_bytes(source.read_bytes())
        (self.work/'prepare_q0_evidence.sh').write_text('# old launcher')
        with self.assertRaisesRegex(ValueError,'launcher is not installed'):
            with self.opened('reader',True):pass

    def test_runtime_source_drift_is_rejected(self):
        source,_=self.prepared()
        with self.assertRaisesRegex(ValueError,'dependency'):
            with self.opened('stager'):source.write_text('# changed source')

    def test_only_explicit_readless_threshold_may_install_layout_support(self):
        self.prepared()
        package=self.work/'metadata/package.tsv';package.parent.mkdir();package.write_text('reads_qc_enabled\nfalse\n')
        self.record['q0_supplement_scope']='positive_threshold'
        self.record['proof_repair_package']=self.row(package)
        source=self.root/'workspace_layout.py';source.write_text('# support\n')
        target=self.work/'.prepare_lib/tools/workspace_layout.py';target.write_bytes(source.read_bytes())
        self.record['runtime'].append({'relative':str(target.relative_to(self.work)),
                                      'source':self.row(source),'new_sha256':context.digest(source)})
        with self.opened('reader',True):pass
        self.record['q0_supplement_scope']='decision_frontier_repair'
        with self.assertRaisesRegex(ValueError,'runtime path'):
            with self.opened('reader',True):pass

    def test_runtime_path_cannot_escape_allowed_slice(self):
        self.prepared();row=self.record['runtime'][0]
        for relative in ('../oops.py','/tmp/oops.py','.prepare_lib/tools/run_all_runner.py',
                         '.prepare_lib/tools/lgz_core/../q0.py','a\\b.py'):
            row['relative']=relative
            with self.assertRaisesRegex(ValueError,'unsafe'):
                with self.opened('stager'):pass

    def test_prepared_inventory_cannot_be_empty_or_duplicate(self):
        self.prepared();row=self.record['runtime'][0]
        for rows in ([],[row,row]):
            self.record['runtime']=rows
            with self.assertRaises(ValueError):
                with self.opened('stager'):pass

    def test_plan_must_remain_outside_workspace(self):
        self.path=self.work/'transition.json'
        with self.assertRaisesRegex(ValueError,'isolated'):
            with self.opened():pass


if __name__=='__main__':unittest.main()
