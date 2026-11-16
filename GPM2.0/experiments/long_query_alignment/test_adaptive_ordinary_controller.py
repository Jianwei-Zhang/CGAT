"""Actual native execution with scaled budgets; never performance evidence."""
import argparse
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adaptive_ordinary_controller as controller
import adaptive_ordinary_units as units
import automatic_ordinary_pilot as pilot
import native_first as nf
import proactive_reference_plan as pp
import proactive_resume as pr
import test_automatic_ordinary_pilot as fixtures
import windowed_alignment as wa


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.ActualNativeTests.setUpClass()

    def fixture(self, root, *, filtered=False, weak=()):
        plan, query, index, tool, args = fixtures.ActualNativeTests().fixture(root)
        source = root / "queries.fa"
        data = source.read_bytes()
        for number in weak:
            name = (">q%02d\n" % number).encode(); start = data.index(name) + len(name)
            data = data[:start] + b"N" * 90000 + data[start+90000:]
        source.write_bytes(data)
        budget = pilot.Budget(**plan["budget"])
        if filtered:budget = replace(budget, minimum_speedup=2.0)
        return pp.scan_query(source), index, tool, args, budget

    def run(self, result=None):
        # Real mappings with synthetic completed timings only to exercise the
        # selection branch deterministically. Never use these as speed evidence.
        original = pilot._verify_case
        def times(*args, **kwargs):
            value = original(*args, **kwargs)
            value["wall_seconds"] = 10 if args[6] is None else 2
            return value
        with patch.object(pilot, "_verify_case", side_effect=times):return super().run(result)

    def execute(self, target, inputs, **kwargs):
        cat, index, tool, args, budget = inputs
        return controller.execute(target, cat, index, tool, args, budget=budget, unit_bases=450000, **kwargs)

    def test_small_workload_and_explicit_user_filter_never_start_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root); cat,index,tool,args,budget=inputs
            with patch.object(nf,"attempt",side_effect=AssertionError("declined controller mapped")):
                declined=controller.execute(root/"small",cat,index,tool,args)
                self.assertEqual(declined["status"],"not_triggered")
                self.assertFalse((root/"small").exists())
                args.minimap_filter="0.01"
                explicit=self.execute(root/"explicit",inputs)
                self.assertEqual(explicit["plan"]["reason"],"explicit_filter_preserved")
                self.assertFalse((root/"explicit").exists())

    def test_default_continuation_is_exhaustive_and_resource_changed_resume_never_maps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root); target=root/"controller"
            result=self.execute(target,inputs)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            self.assertEqual(result["selected_filter"],"default")
            self.assertEqual(result["reviews"],{})
            self.assertFalse(result["output_published"])
            identity=result["composition"]["identity"]
            self.assertEqual(len([q for s in identity["selections"] for q in s["queries"]]),20)
            self.assertTrue(result["complete_default_pilot_preserved"])
            before=wa.sha256(Path(result["composition"]["path"]))
            cat,index,tool,args,budget=inputs
            changed=(cat,index,tool,argparse.Namespace(threads=1,memory_gib=1,minimap_batch="500M"),budget)
            with patch.object(nf,"attempt",side_effect=AssertionError("completed controller remapped")):
                resumed=self.execute(target,changed)
            self.assertEqual(resumed["composition"]["sha256"],before)

    def test_filtered_continuation_reviews_whole_nohit_record_and_keeps_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(15,)); target=root/"controller"
            result=self.execute(target,inputs)
            self.assertEqual(result["selected_filter"],"0.005")
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            self.assertEqual(list(result["reviews"]),["q15"])
            self.assertTrue(result["reviews"]["q15"]["complete_default_selected"])
            selections=result["composition"]["identity"]["selections"]
            selected=[s for s in selections if "q15" in s["queries"]]
            self.assertEqual(len(selected),1); self.assertEqual(selected[0]["queries"],["q15"])
            self.assertEqual(selected[0]["source"]["sha256"],result["reviews"]["q15"]["source_sha256"])
            with patch.object(nf,"attempt",side_effect=AssertionError("completed review remapped")):
                resumed=self.execute(target,inputs)
            self.assertEqual(resumed["composition"],result["composition"])

    def test_review_allowance_is_cumulative_and_no_partial_result_is_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(5,15)); target=root/"controller"
            result=self.execute(target,inputs)
            self.assertEqual(result["status"],"stopped_without_publication")
            self.assertEqual(result["reason"],"cumulative_review_count_or_bases_exceeded")
            self.assertEqual(list(result["reviews"]),["q05"])
            self.assertFalse((target/"composition/ordinary.selected.paf").exists())
            with patch.object(nf,"attempt",side_effect=AssertionError("stopped prefix remapped")):
                resumed=self.execute(target,inputs)
            self.assertEqual(resumed["status"],"stopped_without_publication")

    def test_cancelled_review_has_no_automatic_retry_or_partial_composition(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(15,)); target=root/"controller"
            native=nf.attempt
            def interrupt(*args,**kwargs):
                if "reviews" in Path(args[3]).parts:raise KeyboardInterrupt("review cancelled")
                return native(*args,**kwargs)
            with patch.object(nf,"attempt",side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):self.execute(target,inputs)
            with patch.object(nf,"attempt",side_effect=AssertionError("cancelled review retried")):
                result=self.execute(target,inputs)
            self.assertEqual(result["reason"],"review_failed_no_retry")
            self.assertFalse((target/"composition/ordinary.selected.paf").exists())

    def test_internal_checkpoint_resumes_only_missing_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root); target=root/"controller"
            first=self.execute(target,inputs,unit_limit=1)
            self.assertEqual(first["status"],"bounded_checkpoint")
            self.assertFalse((target/"composition").exists())
            self.assertEqual(len(list((target/"inputs").glob("*.fa"))),1)
            with patch.object(nf,"attempt",wraps=nf.attempt) as calls:
                final=self.execute(target,inputs)
            self.assertEqual(calls.call_count,3)
            self.assertTrue(all("calibration" not in Path(c.args[3]).parts for c in calls.call_args_list))
            self.assertEqual(final["status"],"complete_bounded_policy_candidate")

    def test_completed_review_survives_cancel_before_controller_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(15,)); target=root/"controller"
            unit_run=units.run_unit
            def interrupt(*args,**kwargs):
                result=unit_run(*args,**kwargs)
                if "reviews" in Path(args[0]).parts:raise KeyboardInterrupt("after complete review")
                return result
            with patch.object(units,"run_unit",side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):self.execute(target,inputs)
            with patch.object(nf,"attempt",wraps=nf.attempt) as calls:
                result=self.execute(target,inputs)
            self.assertEqual(calls.call_count,1)
            self.assertEqual(Path(calls.call_args.args[3]).parent.name,"unit-000003")
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            self.assertEqual(result["reviews"]["q15"]["charged_seconds"],25)

    def test_bare_review_reservation_cannot_start_a_new_native_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(15,)); target=root/"controller"
            self.execute(target,inputs)
            state=pr.read_json(target/controller.STATE); row=state["reviews"]["q15"]
            child=Path(row["directory"])/"native/native-attempt.json"
            child.rename(child.with_suffix(".retained"))
            row.update(status="reserved",charged_seconds=row["timeout_seconds"]+5)
            wa.write_json(target/controller.STATE,state)
            with patch.object(nf,"attempt",side_effect=AssertionError("bare reservation retried")):
                result=self.execute(target,inputs)
            self.assertEqual(result["reason"],"interrupted_review_no_automatic_retry")
            self.assertFalse(result["output_published"])

    def test_external_calibration_and_completed_unit_are_readonly_and_never_remapped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root); old=root/"old"; target=root/"continuation"
            self.execute(old,inputs,unit_limit=1)
            query=pr.read_json(old/"pilot.fa.json")
            unit_query=pr.read_json(old/"inputs/unit-000000.fa.json")
            markers=[old/"calibration"/pilot.STATE,old/"units/unit-000000/unit.json"]
            saved=[(p.read_bytes(),p.stat().st_mtime_ns) for p in markers]
            bindings={0:{"root":old/"units/unit-000000","query":unit_query}}
            with patch.object(nf,"attempt",side_effect=AssertionError("external completed prefix remapped")):
                prefix=self.execute(target,inputs,calibration_root=old/"calibration",calibration_query=query,
                                    completed_units=bindings,unit_limit=1)
            self.assertEqual(prefix["status"],"bounded_checkpoint")
            self.assertFalse((target/"inputs").exists())
            with patch.object(nf,"attempt",wraps=nf.attempt) as calls:
                result=self.execute(target,inputs,calibration_root=old/"calibration",calibration_query=query,
                                    completed_units=bindings)
            self.assertEqual(calls.call_count,3)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            self.assertEqual([(p.read_bytes(),p.stat().st_mtime_ns) for p in markers],saved)
            with patch.object(nf,"attempt",side_effect=AssertionError("missing external binding recalibrated")):
                with self.assertRaisesRegex(wa.ExperimentError,"before calibration"):
                    self.execute(target,inputs)

    def test_invalid_review_timeout_is_rejected_before_unit_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root,filtered=True,weak=(15,)); target=root/"controller"
            self.execute(target,inputs)
            state=pr.read_json(target/controller.STATE);state["reviews"]["q15"]["timeout_seconds"]=float("inf")
            wa.write_json(target/controller.STATE,state)
            with patch.object(nf,"attempt",side_effect=AssertionError("invalid budget mapped")):
                with self.assertRaisesRegex(wa.ExperimentError,"finite ordinary review ledger"):
                    self.execute(target,inputs)

    def test_review_time_allowance_is_not_reset_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=list(self.fixture(root,filtered=True,weak=(4,5,6)))
            inputs[-1]=replace(inputs[-1],total_seconds=20,review_fraction=.5)
            target=root/"controller"
            result=self.execute(target,inputs)
            self.assertEqual(result["reason"],"review_wall_budget_exhausted")
            self.assertEqual(list(result["reviews"]),["q04","q05"])
            self.assertEqual(sum(r["charged_seconds"] for r in result["reviews"].values()),20)
            with patch.object(nf,"attempt",side_effect=AssertionError("review time budget reset")):
                resumed=self.execute(target,inputs)
            self.assertEqual(resumed["reason"],"review_wall_budget_exhausted")

    def test_query_identifier_is_not_used_as_a_filesystem_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=list(self.fixture(root,filtered=True,weak=(15,)))
            source=root/"queries.fa";source.write_bytes(source.read_bytes().replace(b">q15\n",b">zz/../../escape\n"))
            inputs[0]=pp.scan_query(source)
            result=self.execute(root/"controller",inputs)
            self.assertEqual(result["status"],"complete_bounded_policy_candidate")
            review=Path(result["reviews"]["zz/../../escape"]["directory"])
            self.assertEqual(review.parent,root/"controller/reviews")
            self.assertEqual(len(review.name),64)
            self.assertFalse((root/"escape").exists())
