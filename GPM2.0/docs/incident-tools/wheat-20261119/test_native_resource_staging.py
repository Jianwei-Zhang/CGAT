"""Resource metadata integration; synthetic calibration is not mapper acceptance."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_self_extension_staging as fixtures
import self_seed_profile as primary
import stage_self_extension as extension
import native_batch_guard as guard
import native_resource_bootstrap as bootstrap
import stage_native_resources as staging
import native_resource_bindings as bindings
import native_resource_admission as admission


class ResourceStagingTests(unittest.TestCase):
    def setUp(self):
        self.fx=fx=fixtures.ExtensionStagingTests();fx.setUp();self.addCleanup(fx.doCleanups)
        f=fx.f;self.work=f.work;self.output=f.root/"native-plan"
        self.origin=copy.deepcopy(fx.parent)
        self.origin["extension_schema"]="incident_self_extension_plan_v1"
        here=Path(staging.__file__).parent
        self.origin["dependencies"].update({k:staging.record(here/v) for k,v in extension.MODULES.items()})
        self.origin["dependencies"].update(extension_parent=staging.record(fx.parent_path),
            extension_calibration=staging.record(fx.candidate),launcher=staging.record(f.work/"prepare_q0_evidence.sh"))
        self.origin_path=f.root/"original-extension.json"
        self.origin_path.write_text(json.dumps(self.origin))
        self.calibration=f.root/"native-pilot.json"
        self.calibration.write_text(json.dumps({"status":"guarded_native_replays_byte_identical",
            "main_workspace_modified":False,"native_resource_policy":guard.POLICY,"lanes":8,"thread_grants":[1]*8,
            "cases":[{"identical":{"raw.paf":True,"result.paf":True},"native_resource_receipt":{
                "runtime":{"adapter":{"sha256":staging.record(guard.__file__)["sha256"]}}}} for _ in range(8)]}))
        # Keep the tiny patched primary class at its genuine source identity.
        alias=patch.dict(sys.modules,{"tiny_authentic_primary":primary});alias.start();self.addCleanup(alias.stop)

    def stage(self):
        result=staging.stage(self.origin_path,self.output,self.calibration)
        path=self.output/"self-plan.json"
        return path,json.loads(path.read_text()),result

    def test_stages_only_resources_without_rekey_or_workspace_write(self):
        before={str(p):staging.digest(p) for p in self.work.rglob("*") if p.is_file()}
        path,plan,result=self.stage()
        self.assertEqual(result["eligible_native_batches"],1)
        self.assertFalse(result["workspace_modified"])
        self.assertEqual(before,{str(p):staging.digest(p) for p in self.work.rglob("*") if p.is_file()})
        self.assertEqual(plan["operations"][0]["profile"],self.origin["operations"][0]["profile"])
        self.assertEqual(plan["operations"][0]["native_commands"],self.origin["operations"][0]["native_commands"])
        self.assertEqual(plan["resource_policy"]["reservation_policy"],admission.POLICY)
        spec=json.loads(Path(plan["operations"][0]["native_specs"]["1"]["path"]).read_text())
        self.assertEqual(spec["native_key"],self.fx.f.native["batches"][1]["key"])
        staging.verify_transition(plan,self.origin)

    def test_installed_modules_are_authentic_and_restored(self):
        path,plan,_=self.stage();old={name:sys.modules.get(name) for name in bootstrap.NAMES}
        with bootstrap.installed(path,role="native_entry",caller=plan["dependencies"]["native_entry"]["path"]):
            import self_profile_context as context
            import self_profile_bindings as support
            import native_resource_bindings as selected
            self.assertEqual(Path(context.__file__).resolve(),Path(plan["dependencies"]["native_context"]["path"]))
            actual=selected.NativeBindings(support.SelfBindings(self.work,path,self.fx.f.profile.contract))
            self.assertEqual(len(actual.native_tasks),1)
            import self_profile_admission as dispatcher
            dispatcher.SelfDispatcher(actual,lambda task:True,max_fast=2)
        for name,previous in old.items():self.assertIs(sys.modules.get(name),previous)

    def test_completed_native_is_retained_and_not_removed_from_inventory(self):
        self.fx.f.publish_native_small()
        directory=Path(self.fx.f.native["batches"][1]["directory"])
        before={p.name:p.read_bytes() for p in directory.iterdir() if p.is_file()}
        _,plan,result=self.stage()
        self.assertEqual(result["eligible_native_batches"],1)
        self.assertEqual(before,{p.name:p.read_bytes() for p in directory.iterdir() if p.is_file()})
        self.assertFalse((directory/guard.RECEIPT).exists())

    def test_changed_science_or_fast_policy_rejected(self):
        _,plan,_=self.stage()
        mutations=[lambda x:x["operations"][0]["profile"].update(sha256="changed"),
                   lambda x:x["resource_guard"].update(limit_bytes=1),
                   lambda x:x["dependencies"]["runtime"].update(sha256="changed"),
                   lambda x:x["resource_policy"].update(max_fast=4),
                   lambda x:x["operations"].clear()]
        for mutation in mutations:
            changed=copy.deepcopy(plan);mutation(changed)
            with self.assertRaises(ValueError):staging.verify_transition(changed,self.origin)

    def test_old_verifier_rejects_changed_origin_not_bypassed(self):
        self.origin["resource_policy"]["max_fast"]=4
        self.origin_path.write_text(json.dumps(self.origin))
        with self.assertRaisesRegex(ValueError,"two-lane"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_wrong_caller_and_unbound_wrapper_rejected(self):
        path,plan,_=self.stage()
        with self.assertRaisesRegex(ValueError,"entry"):
            with bootstrap.installed(path,role="native_entry",caller=__file__):pass
        script=Path(plan["operations"][0]["native_scripts"]["1"]["path"])
        script.write_text("exit 0")
        with bootstrap.installed(path,role="native_entry",caller=plan["dependencies"]["native_entry"]["path"]):
            import self_profile_bindings as support
            import native_resource_bindings as selected
            with self.assertRaises(ValueError):selected.NativeBindings(support.SelfBindings(self.work,path,self.fx.f.profile.contract))

    def test_bad_calibration_cannot_authorize_new_resource_policy(self):
        original=json.loads(self.calibration.read_text())
        for changes in ({"lanes":4},{"thread_grants":[8]*8},{"main_workspace_modified":True}):
            self.calibration.write_text(json.dumps({**original,**changes}))
            # Isolated partial staging remains diagnostic, never installed.
            self.output=self.fx.f.root/("invalid-"+next(iter(changes)))
            with self.assertRaisesRegex(ValueError,"eight-lane"):self.stage()
            self.assertFalse((self.output/"self-plan.json").exists())


if __name__=="__main__":unittest.main()
