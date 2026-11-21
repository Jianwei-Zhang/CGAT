from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import resume_q0_science as owner


class OwnerTests(unittest.TestCase):
    def setUp(self):
        # Production installation is a fresh process. Other test modules may
        # import q0 during discovery; isolate that state without relaxing the guard.
        isolated=patch.dict(owner.sys.modules);isolated.start();self.addCleanup(isolated.stop)
        for name in list(owner.sys.modules):
            if name.startswith('lgz_core.q0_'):owner.sys.modules.pop(name)
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);work=root/'work';(work/'.run_all').mkdir(parents=True)
        (work/'.prepare_lib/tools').mkdir(parents=True)
        resource=work/'.run_all/resources.json';resource.write_text('{"old":32}')
        self.events=[];self.units=[SimpleNamespace(unit_id='initial:'+str(i),command_relpath='command') for i in range(25)]
        self.units += [SimpleNamespace(unit_id='q0_evidence',command_relpath='prepare_q0_evidence.sh')]
        self.units += [SimpleNamespace(unit_id='later:'+str(i),command_relpath='command') for i in range(29)]
        self.lock=SimpleNamespace(acquired=False)
        def acquire():self.lock.acquired=True;self.events.append('lock')
        def release():self.lock.acquired=False;self.events.append('release')
        self.lock.acquire=acquire;self.lock.release=release
        checkpoint=root/'checkpoint';checkpoint.write_text('{}')
        class Readonly:
            def __init__(self,*args):pass
            def prepare(self,unit,command):return SimpleNamespace(path=checkpoint,input_fingerprint='initial-key')
            def validate(self,prepared):return True,'valid'
        rr=SimpleNamespace(load_plan=lambda w:self.units,new_run_id=lambda:'test',WorkspaceLock=lambda *a:self.lock,
            Runner=lambda *a,**kw:SimpleNamespace(run=lambda:self.events.append('run') or 0))
        self.ctx=SimpleNamespace(work=work,transition_path=root/'transition.json',transition_sha='new',plan_sha='old',
            plan={'dependencies':{'entry':{'path':str(root/'original.py')}}},transition={'dependencies':{
                'reader':{'path':str(root/'reader.py')},'stager':{'path':str(root/'stager.py')}}},
            base=SimpleNamespace(rr=rr),
            verify=lambda:self.events.append('verify'),
            contract=SimpleNamespace(sha256_file=owner.digest,atomic_write_json=lambda p,x:p.write_text(json.dumps(x))),
            native_original_context=SimpleNamespace(compose=lambda *a,**kw:Readonly))
        def configure(ctx):self.events.append('configure');return lambda w:object()
        def install(ctx,lock,callback):self.assertTrue(lock.acquired);self.events.append('install')
        modules={'authentic_initial_alignment_owner':SimpleNamespace(configure=configure),
                 'explicit_q0_reader':SimpleNamespace(),'explicit_q0_installer':SimpleNamespace(install=install)}
        self.ctx.native_bootstrap=SimpleNamespace(module=lambda name,p:modules[name])
        @contextmanager
        def opened(*a,**kw):self.events.append(('open',kw['require_installed']));yield self.ctx
        runtime=SimpleNamespace(__file__=str(work/'.prepare_lib/tools/run_resources.py'),
            update_resources=lambda *a:self.events.append('resources'))
        self.available=set(range(32))
        for mock in [patch.object(owner,'opened_transition',opened),patch.object(owner,'checked',lambda row:Path(row['path'])),
                     patch.object(owner,'installed',lambda ctx:self.events.append('installed')),
                     patch.object(owner.os,'sched_getaffinity',lambda _:self.available),
                     patch.dict(owner.sys.modules,{'run_resources':runtime,'run_outer_checkpoints':SimpleNamespace(OuterCheckpointManager=Readonly)})]:
            mock.start();self.addCleanup(mock.stop)

    def test_normal_owner_orders_lock_install_resources_run(self):
        self.assertEqual(owner.execute('plan',install_runtime=True),0)
        self.assertEqual(self.events,[('open',False),'lock','verify','install','installed','resources','configure','run','release'])
        self.assertEqual((self.ctx.transition_path.parent/'resources-before-test.json').read_text(),'{"old":32}')

    def test_readonly_validates_all_initial_units_without_lock_or_install(self):
        self.assertEqual(owner.execute('plan',validate_only=True),0)
        self.assertEqual(self.events,[('open',False),'configure','verify'])
        report=json.loads((self.ctx.transition_path.parent/'validation.json').read_text())
        self.assertEqual(len(report['initial_checkpoints']),25)
        self.assertFalse(report['workspace_modified'])

    def test_changed_workflow_is_rejected_before_install(self):
        self.units.pop()
        with self.assertRaisesRegex(ValueError,'workflow'):owner.execute('plan',install_runtime=True)
        self.assertNotIn('install',self.events);self.assertEqual(self.events[-1],'release')

    def test_cpu_shortfall_is_rejected_before_install(self):
        self.available=set(range(8))
        with self.assertRaisesRegex(ValueError,'CPU affinity'):owner.execute('plan',install_runtime=True)
        self.assertNotIn('install',self.events);self.assertEqual(self.events[-1],'release')

    def test_loaded_old_builder_is_not_relabelled(self):
        with patch.dict(owner.sys.modules,{'lgz_core.q0_preparation':object()}):
            with self.assertRaisesRegex(ValueError,'already imported'):owner.execute('plan',install_runtime=True)
        self.assertNotIn('install',self.events)

    def test_resume_without_install_requires_installed_context(self):
        self.assertEqual(owner.execute('plan'),0)
        self.assertEqual(self.events[0],('open',True));self.assertNotIn('install',self.events)


if __name__=='__main__':unittest.main()
