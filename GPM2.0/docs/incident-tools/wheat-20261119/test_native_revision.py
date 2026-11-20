"""Receipt-preserving resource revisions; synthetic fixtures are not mapper proof."""
import copy
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_batch_guard as guard
import native_resource_bootstrap as bootstrap
import native_resource_audit as audit
import stage_native_revision as revision
import test_native_resource_staging as fixtures


class NativeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ResourceStagingTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.work=self.fx.work; self.root=self.fx.fx.f.root
        # The actual extension has an isolated immutable reader, not a pointer
        # to the mutable installed workspace reader. Model that boundary here.
        immutable=self.root/"original-reader.sh"
        shutil.copyfile(self.work/"prepare_q0_evidence.sh",immutable)
        self.fx.origin["dependencies"]["launcher"]=revision.record(immutable)
        self.fx.origin_path.write_text(json.dumps(self.fx.origin))
        self.previous_path,self.previous,_=self.fx.stage()
        shutil.copyfile(self.previous["dependencies"]["launcher"]["path"],self.work/"prepare_q0_evidence.sh")
        self.bundle=self.root/"new-native-runtime";self.bundle.mkdir()
        for filename in revision.MODULES.values():
            shutil.copyfile(Path(revision.__file__).parent/filename,self.bundle/filename)
        self.new_bootstrap=bootstrap.module("new_native_bootstrap_test",self.bundle/"native_resource_bootstrap.py")
        self.stager=bootstrap.module("new_native_stager_test",self.bundle/"stage_native_revision.py")
        self.output=self.root/"revised-plan"
        self.proof=self.root/"thread-proof.json";self.config=self.root/"thread-config.json"
        source=[{"manifest":{"path":"fixture-manifest"},"batch_index":i,
                 "baseline_threads":8,"threads":2} for i in (1,2)]
        runtime=self.previous["native_runtime"]
        # Pilot uses a genuinely distinct, same-content guard path.
        self.pilot_guard=self.root/"pilot-guard.py"
        shutil.copyfile(guard.__file__,self.pilot_guard)
        adapter=revision.record(self.pilot_guard)
        config={"workspace":str(self.work),"lanes":2,"allow_thread_rebudget":True,"cases":source,
                "runtime":{"helper":runtime["helper"],"tool":runtime["mapper"],
                "minimap_diagnostics":runtime["diagnostics"],"native_adapter":adapter}}
        self.config.write_text(json.dumps(config))
        self.report={"status":"guarded_native_replays_byte_identical","main_workspace_modified":False,
            "thread_counts_changed":True,"native_resource_policy":guard.POLICY,"lanes":2,
            "baseline_thread_grants":[8,8],"thread_grants":[2,2],"config":revision.record(self.config),
            "implementation":revision.record(Path(revision.__file__).parent/"native_concurrency_pilot.py"),
            "cases":[{"source":row,"identical":{"raw.paf":True,"result.paf":True},
                "native_resource_receipt":{"status":"complete","policy":guard.POLICY,"thread_grant":2,
                    "runtime":{"adapter":adapter},"scientific_parameters_changed":False}} for row in source]}
        self.proof.write_text(json.dumps(self.report))

    def stage(self):
        result=self.stager.stage(self.previous_path,self.output,self.proof)
        path=self.output/"self-plan.json"
        return path,json.loads(path.read_text()),result

    def publish_old_receipt(self,threads=8):
        fixture=self.fx.fx.f;fixture.publish_native_small()
        row=self.previous["operations"][0];spec_row=row["native_specs"]["1"]
        spec=json.loads(Path(spec_row["path"]).read_text())
        directory=Path(fixture.native["batches"][1]["directory"])
        marker=directory/"complete.json"
        receipt={"schema":guard.SCHEMA,"status":"complete","native_key":spec["native_key"],
            "spec_sha256":spec_row["sha256"],"manifest":spec["manifest"],"runtime":spec["runtime"],
            "policy":guard.POLICY,"thread_grant":threads,"complete_marker_sha256":bootstrap.digest(marker),
            "outputs":json.loads(marker.read_text())["outputs"],"scientific_parameters_changed":False,
            "children":[{"kind":"mapping","as_limit_bytes":guard.POLICY["mapper_as_bytes"],"returncode":0},
                        {"kind":"restore","as_limit_bytes":guard.POLICY["restore_as_bytes"],"returncode":0}]}
        path=directory/guard.RECEIPT;path.write_text(json.dumps(receipt));return path

    def selected(self,path,plan):
        return self.new_bootstrap.installed(path,role="native_entry",caller=plan["dependencies"]["native_entry"]["path"])

    def test_preserves_receipts_and_real_module_paths_across_separate_bundles(self):
        receipt=self.publish_old_receipt()
        before={str(p):p.read_bytes() for p in self.work.rglob("*") if p.is_file()}
        path,plan,result=self.stage()
        self.assertEqual(result["preserved_guarded_receipts"],1)
        self.assertFalse(result["native_specs_rewritten"])
        self.assertEqual(plan["operations"],self.previous["operations"])
        self.assertEqual(plan["native_runtime"],self.previous["native_runtime"])
        for key in ("native_guard","native_support","native_calibration","native_origin","fast_admission"):
            self.assertEqual(plan["dependencies"][key],self.previous["dependencies"][key])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.work.rglob("*") if p.is_file()})
        saved={name:sys.modules.get(name) for name in bootstrap.NAMES}
        with self.selected(path,plan):
            import native_resource_bindings as support
            import native_resource_admission as admission
            import native_batch_guard as selected_guard
            import self_profile_bindings as original
            actual=support.NativeBindings(original.SelfBindings(self.work,path,self.fx.fx.f.profile.contract))
            rel=plan["operations"][0]["operation"]
            self.assertEqual(json.loads(actual.receipt(rel,1).read_text())["thread_grant"],8)
            self.assertEqual(Path(selected_guard.__file__).resolve(),Path(guard.__file__).resolve())
            self.assertEqual(Path(admission.__file__).resolve(),self.bundle/"native_fair_admission.py")
            admission.SelfDispatcher(actual,lambda task:True,max_fast=2)
            rows=audit.native_rows(SimpleNamespace(selfs=actual,contract=actual.contract,work=self.work))
            self.assertEqual(rows[0]["thread_grant"],8)
            self.assertTrue(rows[0]["guard_execution_proven"])
        for name,value in saved.items():self.assertIs(sys.modules.get(name),value)
        self.assertEqual(receipt.read_bytes(),before[str(receipt)])

    def test_old_and_new_grants_share_specs_but_tampered_receipts_still_fail(self):
        receipt=self.publish_old_receipt(threads=8);path,plan,_=self.stage()
        with self.selected(path,plan):
            import native_resource_bindings as support
            import self_profile_bindings as original
            actual=support.NativeBindings(original.SelfBindings(self.work,path,self.fx.fx.f.profile.contract))
            rel=plan["operations"][0]["operation"]; row=json.loads(receipt.read_text())
            for grant in (1,2,8):
                row["thread_grant"]=grant;receipt.write_text(json.dumps(row))
                self.assertEqual(json.loads(actual.receipt(rel,1,required=True,threads=grant).read_text())["thread_grant"],grant)
            row["spec_sha256"]="changed";receipt.write_text(json.dumps(row))
            with self.assertRaises(ValueError):actual.receipt(rel,1)

    def test_changed_preserved_identity_and_reader_rejected(self):
        _,plan,_=self.stage()
        mutations=[lambda p:p["operations"][0]["native_specs"]["1"].update(sha256="changed"),
            lambda p:p["native_runtime"]["helper"].update(sha256="changed"),
            lambda p:p["dependencies"].update(native_guard=revision.record(self.pilot_guard)),
            lambda p:p["prior_launcher"].update(sha256="changed"),
            lambda p:p["resource_policy"].update(max_fast=4)]
        for change in mutations:
            damaged=copy.deepcopy(plan);change(damaged)
            with self.assertRaises(ValueError):self.stager.verify_transition(damaged,self.fx.origin)

    def test_changed_previous_plan_and_recursion_rejected_and_modules_restored(self):
        row=revision.record(self.previous_path)
        saved={name:sys.modules.get(name) for name in (*bootstrap.NAMES,"native_resource_bootstrap")}
        bad=copy.deepcopy(self.previous);bad["resource_policy"]["max_fast"]=4
        self.previous_path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            with bootstrap.previous_resources(row):pass
        with self.assertRaises(ValueError):
            with bootstrap.previous_resources(revision.record(self.previous_path)):pass
        bad=copy.deepcopy(self.previous);bad["dependencies"]["native_previous"]=row
        self.previous_path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"first-generation"):
            with bootstrap.previous_resources(revision.record(self.previous_path)):pass
        for name,value in saved.items():self.assertIs(sys.modules.get(name),value)

    def test_incomplete_thread_proof_rejected_before_staging_output(self):
        self.report["cases"][1]["identical"]["raw.paf"]=False
        self.proof.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,"incomplete"):self.stage()
        self.assertFalse(self.output.exists())

    def test_thread_calibration_fences_and_isolated_guard_identity(self):
        _,plan,_=self.stage()
        mutations=[lambda r:r.update(main_workspace_modified=True),
            lambda r:r.update(thread_counts_changed=False),lambda r:r.update(lanes=8),
            lambda r:r.update(baseline_thread_grants=[2,2]),
            lambda r:r["cases"][0]["native_resource_receipt"].update(status="pending"),
            lambda r:r["cases"][0]["native_resource_receipt"].update(thread_grant=8),
            lambda r:r["cases"][0]["native_resource_receipt"].update(scientific_parameters_changed=True),
            lambda r:r["cases"][0].update(source={}),
            lambda r:r["implementation"].update(sha256="changed")]
        for change in mutations:
            report=copy.deepcopy(self.report);change(report)
            self.proof.write_text(json.dumps(report))
            changed=copy.deepcopy(plan);changed["dependencies"]["native_thread_calibration"]=revision.record(self.proof)
            with self.assertRaises(ValueError):self.stager.verify_thread_calibration(changed)
        self.proof.write_text(json.dumps(self.report))
        plan["dependencies"]["native_thread_calibration"]=revision.record(self.proof)
        self.pilot_guard.write_text("changed isolated pilot guard")
        with self.assertRaises(ValueError):self.stager.verify_thread_calibration(plan)

    def test_reader_and_audit_roles_select_same_preserved_receipt_validator(self):
        receipt=self.publish_old_receipt();path,plan,_=self.stage()
        for role in ("native_reader","native_audit"):
            with self.new_bootstrap.installed(path,role=role,caller=plan["dependencies"][role]["path"]):
                import native_resource_bindings as selected
                import self_profile_bindings as original
                actual=selected.NativeBindings(original.SelfBindings(self.work,path,self.fx.fx.f.profile.contract))
                self.assertEqual(actual.receipt(plan["operations"][0]["operation"],1),receipt)
                self.assertEqual(Path(selected.__file__).resolve(),
                                 Path(self.previous["dependencies"]["native_support"]["path"]).resolve())

    def test_uninstalled_previous_reader_rejected_without_workspace_writes(self):
        (self.work/"prepare_q0_evidence.sh").write_text("unrelated reader")
        with self.assertRaisesRegex(ValueError,"previous native reader"):self.stage()
        self.assertFalse(self.output.exists())


if __name__=="__main__":unittest.main()
