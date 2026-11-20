"""Owning entry order tests with synthetic scheduler/Runner, no real execution."""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
import native_resource_bootstrap as bootstrap
import resume_native_resources as owner


class ResourceOwnerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);self.work=root/"work";self.work.mkdir();out=root/"overlay";out.mkdir()
        (self.work/".prepare_lib/tools").mkdir(parents=True);(self.work/".run_all").mkdir()
        self.resource=self.work/".run_all/resources.json";self.resource.write_text('{"effective":{"threads":16}}')
        self.original_bytes=self.resource.read_bytes();self.events=[]
        runtime_file=self.work/".prepare_lib/tools/run_resources.py";runtime_file.write_text("fixture")
        entry=root/"original-owner.py";entry.write_text("fixture")
        launcher=out/"prepare_q0_evidence.sh";launcher.write_text("new-reader")
        (self.work/"prepare_q0_evidence.sh").write_text("old-reader")
        row=lambda p:{"path":str(p),"sha256":bootstrap.digest(p)}
        self.plan={"workspace":str(self.work),"resource_policy":{"max_fast":2},
            "dependencies":{"entry":row(entry),"launcher":row(launcher)}}
        self.lock=SimpleNamespace(acquired=False)
        def acquire():self.events.append("acquire");self.lock.acquired=True
        def release():self.events.append("release");self.lock.acquired=False
        self.lock.acquire=acquire;self.lock.release=release
        self.units=[SimpleNamespace(unit_id="u"+str(i)) for i in range(55)]
        def run():self.events.append("run");return 0
        rr=SimpleNamespace(new_run_id=lambda:"test-run",WorkspaceLock=lambda *a:self.lock,
            load_plan=lambda work:self.units,Runner=lambda *a,**kw:SimpleNamespace(run=run))
        self.ctx=SimpleNamespace(work=self.work,path=out/"self-plan.json",plan=self.plan,plan_sha="bound",
            base=SimpleNamespace(rr=rr,TwoMappingDispatcher=lambda:SimpleNamespace(exclusive=lambda t:True)),
            helper=SimpleNamespace(LAUNCHER="prepare_q0_evidence.sh"),
            selfs=SimpleNamespace(profiles={"op":None},native_tasks={"task":None}),
            contract=SimpleNamespace(sha256_file=bootstrap.digest))
        def verify():self.assertTrue(self.lock.acquired);self.events.append("verify")
        self.ctx.verify=verify
        def install(ctx,lock):
            self.assertTrue(lock.acquired);self.events.append("install")
            (self.work/"prepare_q0_evidence.sh").write_bytes(launcher.read_bytes())
        def configure(ctx):self.events.append("configure");return lambda work:object()
        self.owning=SimpleNamespace(install_reader=install,configure=configure)
        def update(work,options,run_id):
            self.assertTrue(self.lock.acquired)
            self.assertEqual((out/"resources-before-test-run.json").read_bytes(),self.original_bytes)
            self.events.append(("resources",options,run_id))
        self.runtime=SimpleNamespace(__file__=str(runtime_file),update_resources=update)
        @contextmanager
        def installed(*args,**kwargs):yield self.plan
        patches=[patch.object(owner,"installed",installed),patch.object(owner,"module",return_value=self.owning),
            patch.object(owner.os,"sched_getaffinity",return_value=set(range(32))),
            patch.dict(sys.modules,{"self_profile_context":SimpleNamespace(load_context=lambda *a,**kw:self.ctx),
                "self_profile_admission":SimpleNamespace(SelfDispatcher=lambda *a,**kw:None),"run_resources":self.runtime})]
        for mocked in patches:mocked.start();self.addCleanup(mocked.stop)

    def test_updates_budget_only_under_lock_after_reader_and_backup(self):
        self.assertEqual(owner.execute(self.ctx.path,install_reader=True),0)
        self.assertEqual(self.events,["acquire","verify","install",
            ("resources",{"--threads":[["32"]]},"test-run"),"configure","run","release"])

    def test_validation_does_not_own_or_modify_workspace(self):
        self.assertEqual(owner.execute(self.ctx.path,validate_only=True),0)
        self.assertEqual(self.events,["configure"])
        self.assertEqual(self.resource.read_bytes(),self.original_bytes)

    def test_uninstalled_reader_does_not_change_budget(self):
        with self.assertRaisesRegex(ValueError,"reader"):owner.execute(self.ctx.path)
        self.assertEqual(self.events,["acquire","verify","release"])

    def test_workflow_and_cpu_shortfall_fail_before_install(self):
        self.units.pop()
        with self.assertRaisesRegex(ValueError,"workflow"):owner.execute(self.ctx.path,install_reader=True)
        self.assertEqual(self.events,["acquire","verify","release"])
        self.events.clear();self.units.append(SimpleNamespace(unit_id="u54"))
        with patch.object(owner.os,"sched_getaffinity",return_value=set(range(16))):
            with self.assertRaisesRegex(ValueError,"CPU affinity"):owner.execute(self.ctx.path,install_reader=True)
        self.assertEqual(self.events,["acquire","verify","release"])

    def test_runtime_substitution_rejected(self):
        self.runtime.__file__="/unrelated/run_resources.py"
        with self.assertRaisesRegex(ValueError,"frozen"):owner.execute(self.ctx.path,install_reader=True)
        self.assertEqual(self.events,["acquire","verify","install","release"])
        self.assertEqual(self.resource.read_bytes(),self.original_bytes)

    def test_bad_budget_never_enters_owner(self):
        with self.assertRaises(ValueError):owner.execute(self.ctx.path,threads=64)
        self.assertEqual(self.events,[])


if __name__=="__main__":unittest.main()
