from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
from alignment_tasks import AlignmentTask
import native_fair_admission as admission
import native_batch_guard as guard
import self_two_lane_admission as old
import test_self_two_lane_admission as fixtures


def record(path):
    return {"path":str(path), "sha256":guard.digest(path)}


class NativeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        fixture = fixtures.TwoLaneTests(); fixture.setUp()
        self.bindings = fixture.bindings
        self.fast = fixture.tasks
        # Real files: constructor must not accept merely claimed hashes.
        scripts = {}
        for i in range(20):
            path = Path(self.tmp.name) / (str(i) + ".sh")
            path.write_text("verified-by-bindings fixture " + str(i))
            scripts[str(i)] = record(path)
        self.bindings.rows["op"]["native_scripts"] = scripts
        self.bindings.verify_native_resources = lambda: None
        self.bindings.plan.update(dependencies={"fast_admission":record(old.__file__),
            "native_guard":record(guard.__file__)},
            resource_policy={"reservation_policy":admission.POLICY.copy()})
        self.native = [AlignmentTask("native", Path(row["path"]), 8,
            work=100-i, largest_fraction=1) for i,row in enumerate(scripts.values())]

    def dispatcher(self):
        return admission.SelfDispatcher(self.bindings, lambda task: True, max_fast=2)

    def test_sixteen_single_core_lanes_not_fixed_four(self):
        selected = self.dispatcher()(self.native,16,16,[],32)
        self.assertEqual(len(selected),16)
        self.assertEqual(sum(n for _,n in selected),16)
        self.assertTrue(all(t is self.native[i] for i,(t,_) in enumerate(selected)))

    def test_memory_caps_thirty_two_cpu_budget_at_sixteen_lanes(self):
        self.assertEqual(len(self.dispatcher()(self.native,32,32,[],32)),16)
        active = [{"task":t,"threads":1} for t in self.native[:16]]
        self.assertEqual(self.dispatcher()(self.native[16:],16,32,active,32),[])

    def test_cpu_and_slot_limits(self):
        d=self.dispatcher()
        self.assertEqual(len(d(self.native,3,3,[],32)),3)
        self.assertEqual(len(d(self.native,16,16,[],2)),2)
        active=[{"task":self.native[0],"threads":1}]
        self.assertEqual(len(d(self.native[1:],100,4,active,32)),3)

    def test_four_eight_thread_batches_fit_thirty_two(self):
        tasks=[AlignmentTask("native",t.command,8,work=t.work,largest_fraction=0)
               for t in self.native]
        selected=self.dispatcher()(tasks,32,32,[],32)
        self.assertEqual([n for _,n in selected],[8,8,8,8])

    def test_preferred_grant_is_capped_instead_of_starving_higher_work(self):
        d=self.dispatcher()
        large=AlignmentTask("native",self.native[0].command,8,work=1000,largest_fraction=0)
        active=[{"task":self.native[19],"threads":1}]
        selected=d([large]+self.native[1:5],3,4,active,32)
        self.assertEqual(selected,[(large,3)])
        self.assertEqual(large.max_threads,8)  # Descriptor/scientific inputs are unchanged.

    def test_eight_thread_preference_can_use_one_free_cpu_without_oversale(self):
        d=self.dispatcher()
        large=AlignmentTask("native",self.native[0].command,8,work=1000,largest_fraction=0)
        active=[{"task":self.native[i],"threads":n} for i,n in zip(range(1,5),(8,8,8,7))]
        selected=d([large]+self.native[5:],1,32,active,32)
        self.assertEqual(selected,[(large,1)])
        self.assertEqual(sum(n for _,n in selected)+sum(x["threads"] for x in active),32)

    def test_continual_small_arrivals_do_not_bypass_a_large_preference(self):
        d=self.dispatcher()
        head=AlignmentTask("native",self.native[0].command,5,work=1000,largest_fraction=.2)
        active=[{"task":self.native[i],"threads":2} for i in range(1,16)]
        self.assertEqual(d([head]+self.native[16:],2,32,active,32),[(head,2)])

    def test_regression_original_backfill_skips_head_but_candidate_starts_it(self):
        import native_resource_admission as current
        head=AlignmentTask("native",self.native[0].command,5,work=1000,largest_fraction=.2)
        active=[{"task":self.native[i],"threads":2} for i in range(1,16)]
        small=self.native[16]
        old=current.SelfDispatcher(self.bindings,lambda task:True,max_fast=2)
        self.assertEqual(old([head,small],2,32,active,32),[(small,1)])
        self.assertEqual(self.dispatcher()([head,small],2,32,active,32),[(head,2)])

    def test_fast_pool_stays_two_and_never_mixes(self):
        d=self.dispatcher()
        self.assertEqual(len(d(self.fast,32,32,[],32)),2)
        self.assertEqual(d(self.native,31,32,[{"task":self.fast[0],"threads":1}],32),[])
        self.assertEqual(d(self.fast,31,32,[{"task":self.native[0],"threads":1}],32),[])
        selected=d(self.fast+self.native[1:],31,32,[{"task":self.native[0],"threads":1}],32)
        self.assertEqual(len(selected),15)
        self.assertTrue(all(d.kind(t)=="native" for t,_ in selected))

    def test_unguarded_unknown_and_cross_remain_exclusive(self):
        d=self.dispatcher()
        for path in ("/native/old.sh","/work/a_vs_b/command.sh","/unknown.sh"):
            task=AlignmentTask("native",Path(path),1,work=1000)
            self.assertEqual(d.kind(task),"exclusive")
            self.assertEqual(d([task]+self.native,32,32,[],32),[(task,1)])
            self.assertEqual(d(self.native,31,32,[{"task":task,"threads":1}],32),[])

    def test_no_duplicate_object_admission(self):
        task=self.native[0]
        self.assertEqual(self.dispatcher()([task,task],16,16,[],16),[(task,1)])
        self.assertEqual(self.dispatcher()([task],15,16,[{"task":task,"threads":1}],16),[])

    def test_dependencies_and_policy_are_bound(self):
        self.bindings.plan["dependencies"]["native_guard"]["sha256"]="wrong"
        with self.assertRaises(ValueError): self.dispatcher()
        self.bindings.plan["dependencies"]["native_guard"]=record(guard.__file__)
        self.bindings.plan["resource_policy"]["reservation_policy"]={}
        with self.assertRaises(ValueError): self.dispatcher()

    def test_requires_binding_verifier_and_current_wrapper(self):
        self.bindings.verify_native_resources=lambda: (_ for _ in ()).throw(ValueError("bad spec"))
        with self.assertRaisesRegex(ValueError,"bad spec"): self.dispatcher()
        self.bindings.verify_native_resources=lambda: None
        self.native[0].command.write_text("changed")
        with self.assertRaises(ValueError): self.dispatcher()

    def test_active_grants_fail_closed(self):
        with self.assertRaises(ValueError):
            self.dispatcher()(self.native,32,32,[{"task":self.native[0]}],32)


if __name__ == "__main__": unittest.main()
