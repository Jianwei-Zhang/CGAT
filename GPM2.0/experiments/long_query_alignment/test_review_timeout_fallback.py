"""Timeout fallback tests; synthetic timeout evidence is not a timing claim."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import test_adaptive_ordinary_controller as fixtures
import adaptive_ordinary_controller as controller
import adaptive_ordinary_units as units
import native_first as nf
import proactive_resume as pr
import windowed_alignment as wa

class ReviewTimeoutTests(unittest.TestCase):
    setUpClass=classmethod(lambda cls:fixtures.ControllerTests.setUpClass())
    fixture=fixtures.ControllerTests.fixture
    execute=fixtures.ControllerTests.execute
    def run(self,result=None):
        original=units.pilot._verify_case
        def times(*args,**kwargs):
            value=original(*args,**kwargs);value["wall_seconds"]=10 if args[6] is None else 2;return value
        with patch.object(units.pilot,"_verify_case",side_effect=times):return super().run(result)

    def timeout_native(self):
        native=nf.attempt
        def timeout(*args,**kwargs):
            if "reviews" not in Path(args[3]).parts:return native(*args,**kwargs)
            root=Path(args[3]);options=args[4];root.mkdir()
            output=root/"native.partial.paf";output.write_bytes(b"incomplete native output\n")
            command=[args[0],"-c","-x","asm10",*units.mo.native_flags(options),"-t",str(options.threads),"-o",str(output),str(args[1]),str(args[2])]
            execution={"command":command,"returncode":-15,"interrupted":"TimeoutExpired","seconds":float(options.timeout)}
            wa.write_json(root/"native.command.json",command);wa.write_json(root/"native.execution.json",execution)
            (root/"native.stderr").write_text("bounded review timeout\n");(root/"native.stdout").write_bytes(b"")
            receipt={"status":"other_failure","execution":execution,"target_assertion_observed":False,"path":str(output),"paf_sha256":wa.sha256(output),"paf_usable":False,"partial_PAF_reused":False,"stderr_sha256":wa.sha256(root/"native.stderr")}
            wa.write_json(root/"native-attempt.json",receipt);return receipt
        return timeout

    def stopped(self,root):
        inputs=self.fixture(root,filtered=True,weak=(15,));target=root/"controller"
        with patch.object(nf,"attempt",side_effect=self.timeout_native()),patch.object(units,"review_timeout_proof",return_value=None):
            with self.assertRaisesRegex(wa.ExperimentError,"did not complete"):
                self.execute(target,inputs,primary_work=True,unit_seconds=None)
        return inputs,target

    def test_timeout_fallback_and_readonly_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root,filtered=True,weak=(15,));target=root/"controller"
            with patch.object(nf,"attempt",side_effect=self.timeout_native()) as calls:
                result=self.execute(target,inputs,primary_work=True,unit_seconds=None)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            self.assertEqual(result["reviews"]["q15"]["status"],"budget_exhausted")
            self.assertNotIn("q15",result["baseline_compared_queries"])
            self.assertEqual(result["budget_exhausted_review_queries"],["q15"])
            self.assertEqual(result["default_continuation"]["reason"],"review_timeout_budget_exhausted")
            self.assertFalse(result["default_continuation"]["whole_assembly_restart"])
            transition=[c for c in calls.call_args_list if "default-transition" in Path(c.args[3]).parts]
            self.assertEqual(len(transition),1);self.assertIsNone(transition[0].args[4].timeout);self.assertIsNone(transition[0].args[4].minimap_filter)
            selected=[s for s in result["composition"]["identity"]["selections"] if "q15" in s["queries"]]
            self.assertEqual(len(selected),1);self.assertIn("default-transition",selected[0]["source"]["directory"])
            failed=Path(result["reviews"]["q15"]["directory"])/"native/native.partial.paf"
            self.assertEqual(failed.read_bytes(),b"incomplete native output\n")
            snapshot=(target/controller.STATE).read_bytes()
            with patch.object(nf,"attempt",side_effect=AssertionError("completed fallback remapped")):
                replay=self.execute(target,inputs,primary_work=True,unit_seconds=None,readonly=True)
            self.assertEqual(replay["composition"]["sha256"],result["composition"]["sha256"])
            self.assertEqual((target/controller.STATE).read_bytes(),snapshot)

    def test_previous_failed_timeout_preserves_paid_units(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs,target=self.stopped(Path(directory));before={p:p.read_bytes() for p in (target/"units").glob("*/unit.json")};native=nf.attempt
            def resumed(*args,**kwargs):
                self.assertNotIn("reviews",Path(args[3]).parts)
                self.assertNotIn(Path(args[3]).parent,[p.parent for p in before])
                return native(*args,**kwargs)
            with patch.object(nf,"attempt",side_effect=resumed):result=self.execute(target,inputs,primary_work=True,unit_seconds=None)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            for p,content in before.items():self.assertEqual(p.read_bytes(),content)

    def test_cross_tool_timeout_retains_old_prefix_and_new_default_sources(self):
        from test_cross_tool_continuation import reviewed_pair
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root,filtered=True,weak=(15,));target=root/"controller"
            self.execute(target,inputs,unit_limit=1)
            marker=target/"units/unit-000000/unit.json";before=marker.read_bytes()
            with reviewed_pair(root,inputs[2]) as execution:
                with patch.object(nf,"attempt",side_effect=self.timeout_native()):
                    result=self.execute(target,inputs,execution_tool=execution,primary_work=True,unit_seconds=None)
                self.assertEqual(marker.read_bytes(),before)
                row=result["reviews"]["q15"]
                self.assertEqual(row["timeout_evidence"]["identity"]["tool_sha256"],execution["sha256"])
                with patch.object(nf,"attempt",side_effect=AssertionError("cross-tool timeout replay mapped")):
                    replay=self.execute(target,inputs,execution_tool=execution,primary_work=True,unit_seconds=None,readonly=True)
                self.assertEqual(replay["composition"],result["composition"])

    def test_interrupted_default_transition_resumes_only_primary_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root,filtered=True,weak=(15,));target=root/"controller"
            native=self.timeout_native()
            def interrupted(*args,**kwargs):
                if "default-transition" in Path(args[3]).parts:raise KeyboardInterrupt("primary fallback interrupted")
                return native(*args,**kwargs)
            with patch.object(nf,"attempt",side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):self.execute(target,inputs,primary_work=True,unit_seconds=None)
            state=pr.read_json(target/controller.STATE)
            self.assertEqual(state["reviews"]["q15"]["status"],"budget_exhausted")
            original=nf.attempt
            def resumed(*args,**kwargs):
                self.assertNotIn("reviews",Path(args[3]).parts)
                return original(*args,**kwargs)
            with patch.object(nf,"attempt",side_effect=resumed):
                result=self.execute(target,inputs,primary_work=True,unit_seconds=None)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")

    def test_tampering_and_cancellation_never_fallback(self):
        for tamper in ("partial","command","execution","timeout","tool","schema","cancel"):
            with self.subTest(tamper=tamper),tempfile.TemporaryDirectory() as directory:
                inputs,target=self.stopped(Path(directory));state=pr.read_json(target/controller.STATE);review=Path(state["reviews"]["q15"]["directory"]);native=review/"native"
                if tamper=="partial":(native/"native.partial.paf").write_bytes(b"changed")
                if tamper=="command":wa.write_json(native/"native.command.json",["changed"])
                if tamper=="execution":wa.write_json(native/"native.execution.json",{})
                if tamper=="timeout":
                    v=pr.read_json(review/"unit.json");v["resources"]["timeout_seconds"]+=1;wa.write_json(review/"unit.json",v)
                if tamper=="tool":
                    v=pr.read_json(review/"unit.json");v["identity"]["tool_sha256"]="0"*64;wa.write_json(review/"unit.json",v)
                if tamper=="schema":
                    v=pr.read_json(review/"unit.json");v["schema"]=True;wa.write_json(review/"unit.json",v)
                if tamper=="cancel":
                    v=pr.read_json(native/"native-attempt.json");v["execution"]["interrupted"]="KeyboardInterrupt";wa.write_json(native/"native-attempt.json",v)
                with patch.object(nf,"attempt",side_effect=AssertionError("invalid timeout mapped")):
                    if tamper=="cancel":
                        self.assertEqual(self.execute(target,inputs,primary_work=True,unit_seconds=None)["reason"],"review_failed_no_retry")
                    else:
                        with self.assertRaises(wa.ExperimentError):
                            self.execute(target,inputs,primary_work=True,unit_seconds=None)
                self.assertFalse((target/"default-transition").exists())
