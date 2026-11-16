"""Bounded whole-record inputs and real native unit continuation controls."""
import argparse
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adaptive_ordinary_units as units
import automatic_ordinary_pilot as pilot
import native_first as nf
import proactive_reference_plan as pp
import test_automatic_ordinary_pilot as controls
import windowed_alignment as wa


class UnitPlanTests(unittest.TestCase):
    def test_indivisible_records_and_cohort_order_no_missing_or_duplicate_inputs(self):
        records = [{"name": "a", "length": 8}, {"name": "b", "length": 2}, {"name": "c", "length": 30},
                   {"name": "d", "length": 2}, {"name": "pilot", "length": 10}, {"name": "long", "length": 300000000}]
        plan = units.plan_units(records, ["pilot"], "0.005", default_below=2, unit_bases=10)
        self.assertEqual([[r["name"] for r in u["records"]] for u in plan["units"]], [["a"], ["b", "d"], ["c"]])
        self.assertEqual([u["fraction"] for u in plan["units"]], ["0.005", None, "0.005"])
        self.assertEqual(plan["units"][2]["bases"], 30)
        self.assertFalse(plan["records_split"])

    def test_standard_mode_and_record_cap(self):
        records = [{"name": str(i), "length": 1} for i in range(8)]
        plan = units.plan_units(records, ["0"], "default", unit_bases=100, max_records=3)
        self.assertEqual([len(u["records"]) for u in plan["units"]], [3,3,1])
        self.assertTrue(all(u["fraction"] is None for u in plan["units"]))

    def test_all_input_units_from_gzip_use_one_decoding_pass_and_preserve_raw_bytes(self):
        raw = b">a detail\naCgTacGT\n>b\nAC\n>c\n" + b"T" * 30 + b"\n>d\nGG\n>pilot\n" + b"A" * 10 + b"\n"
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); source=root/"input.fa"
                source.write_bytes(gzip.compress(raw) if compressed else raw); catalog=pp.scan_query(source)
                records=[{"name":r.name,"length":r.length} for r in catalog.records]
                plan=units.plan_units(records,["pilot"],"0.005",default_below=2,unit_bases=10)
                with patch.object(pp,"decoded_input",wraps=pp.decoded_input) as streams:
                    result=units.materialize_units(catalog,plan,root/"units")
                self.assertEqual(streams.call_count,1 if compressed else 0)
                self.assertEqual([Path(r["path"]).read_bytes() for r in result],
                    [b">a detail\naCgTacGT\n",b">b\nAC\n>d\nGG\n",b">c\n"+b"T"*30+b"\n"])
                before=[(Path(r["path"]).stat().st_mtime_ns,r["sha256"]) for r in result]
                with patch.object(pp,"decoded_input",side_effect=AssertionError("completed inputs rescanned")):
                    again=units.materialize_units(catalog,plan,root/"units")
                self.assertEqual(again,result)
                self.assertEqual([(Path(r["path"]).stat().st_mtime_ns,r["sha256"]) for r in again],before)
                Path(result[0]["path"]).write_bytes(b"changed")
                with self.assertRaises(wa.ExperimentError):units.materialize_units(catalog,plan,root/"units")

    def test_forged_unit_plan_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"input.fa";source.write_bytes(b">a\nAAAA\n>b\nCCCC\n")
            catalog=pp.scan_query(source)
            plan=units.plan_units([{"name":r.name,"length":r.length} for r in catalog.records],[],"default")
            plan["units"][0]["records"].pop()
            with self.assertRaisesRegex(wa.ExperimentError,"plan changed"):
                units.materialize_units(catalog,plan,root/"units")
            self.assertFalse((root/"units").exists())


class ActualUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        controls.ActualNativeTests.setUpClass()

    def fixture(self,root):
        control=controls.ActualNativeTests();inputs=control.fixture(root)
        plan,query,index,tool,args=inputs
        unit={"ordinal":0,"records":plan["pilot_records"],"fraction":"0.005"}
        return unit,query,index,tool,args

    def test_completed_unit_reuses_original_resources_after_new_thread_and_batch_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self.fixture(root); target=root/"work"
            first=units.run_unit(target,*inputs,timeout=30)
            path=Path(first["source"]["path"]);before=(wa.sha256(path),path.stat().st_mtime_ns)
            changed=argparse.Namespace(threads=1,memory_gib=1,minimap_batch="500M")
            with patch.object(nf,"attempt",side_effect=AssertionError("resource-only update remapped")):
                again=units.run_unit(target,*inputs[:-1],changed,timeout=60)
            self.assertTrue(again["reused"]);self.assertEqual(again["resources"],first["resources"])
            self.assertEqual((wa.sha256(path),path.stat().st_mtime_ns),before)

    def test_native_completion_survives_validation_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root);target=root/"work"
            with patch.object(pilot,"_verify_case",side_effect=KeyboardInterrupt("controlled audit cancellation")):
                with self.assertRaises(KeyboardInterrupt):units.run_unit(target,*inputs,timeout=30)
            state=json.loads((target/"unit.json").read_text())
            self.assertEqual(state["status"],"native_complete_pending_validation")
            with patch.object(nf,"attempt",side_effect=AssertionError("completed native command repeated")):
                resumed=units.run_unit(target,*inputs,timeout=30)
            self.assertTrue(resumed["reused"])

    def test_corrupt_complete_paf_does_not_trigger_remapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root);target=root/"work"
            first=units.run_unit(target,*inputs,timeout=30)
            path=Path(first["source"]["path"]);path.write_bytes(path.read_bytes()+b"bad\n")
            with patch.object(nf,"attempt",side_effect=AssertionError("corrupt completion remapped")):
                with self.assertRaisesRegex(wa.ExperimentError,"bytes changed"):units.run_unit(target,*inputs,timeout=30)

    def test_interrupted_missing_unit_retries_only_on_a_new_explicit_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root);target=root/"work"
            with patch.object(nf,"attempt",side_effect=KeyboardInterrupt("controlled before-child cancellation")):
                with self.assertRaises(KeyboardInterrupt):units.run_unit(target,*inputs,timeout=30)
            with patch.object(nf,"attempt",side_effect=AssertionError("review automatically retried")):
                with self.assertRaisesRegex(wa.ExperimentError,"no automatic retry"):
                    units.run_unit(target,*inputs,timeout=30,retry_incomplete=False)
            with patch.object(nf,"attempt",wraps=nf.attempt) as calls:
                resumed=units.run_unit(target,*inputs,timeout=30)
            self.assertEqual(calls.call_count,1);self.assertFalse(resumed["reused"])
            state=json.loads((target/"unit.json").read_text());self.assertEqual(state["attempts"],2)
            self.assertEqual(len(state["attempt_history"]),2)

    def test_filter_change_is_not_a_resource_only_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=list(self.fixture(root));target=root/"work"
            units.run_unit(target,*inputs,timeout=30);inputs[0]={**inputs[0],"fraction":None}
            with patch.object(nf,"attempt",side_effect=AssertionError("changed policy remapped")):
                with self.assertRaisesRegex(wa.ExperimentError,"source/filter identity changed"):
                    units.run_unit(target,*inputs,timeout=30)

    def test_complete_source_composition_restores_original_query_order_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root)
            first=units.run_unit(root/"first",*inputs,timeout=30)
            records=inputs[0]["records"]; names=[r["name"] for r in records]
            # Deliberately interleaved cohorts from the same verified native file.
            selections=[{"queries":names[1::2],"source":first["source"]},
                        {"queries":names[::2],"source":first["source"]}]
            with patch.object(nf,"attempt",side_effect=AssertionError("composition called mapper")):
                result=units.compose_completed(root/"compose",records,inputs[2],selections)
            self.assertEqual(Path(result["path"]).read_bytes(),Path(first["source"]["path"]).read_bytes())
            self.assertEqual(result["combination"]["original_cells"],len(records)*len(inputs[2]["parts"]))
            self.assertTrue(result["combination"]["all_cells_completed"])
            self.assertFalse(result["fake_native_receipt_created"])
            self.assertFalse(result["whole_workload_quality_approved"])
            before=Path(result["path"]).stat().st_mtime_ns
            again=units.compose_completed(root/"compose",records,inputs[2],selections)
            self.assertEqual(result,again);self.assertEqual(Path(result["path"]).stat().st_mtime_ns,before)
            changed_profiles=[{**row,"source":{**row["source"],"profile":{"derived_layout_changed":True}}} for row in selections]
            self.assertEqual(units.compose_completed(root/"compose",records,inputs[2],changed_profiles),result)
            bad=[{"queries":names,"source":first["source"]},{"queries":[names[0]],"source":first["source"]}]
            with self.assertRaisesRegex(wa.ExperimentError,"omits/duplicates"):
                units.compose_completed(root/"duplicate",records,inputs[2],bad)
            missing=[{"queries":names[:-1],"source":first["source"]}]
            with self.assertRaisesRegex(wa.ExperimentError,"omits/duplicates"):
                units.compose_completed(root/"missing",records,inputs[2],missing)

    def test_readonly_completed_unit_does_not_modify_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root);target=root/"work"
            first=units.run_unit(target,*inputs,timeout=30)
            marker=target/"unit.json";before=(marker.read_bytes(),marker.stat().st_mtime_ns)
            with patch.object(nf,"attempt",side_effect=AssertionError("read-only audit called mapper")):
                audited=units.run_unit(target,*inputs,timeout=30,readonly=True)
            self.assertEqual(audited["source"],first["source"])
            self.assertEqual((marker.read_bytes(),marker.stat().st_mtime_ns),before)
            with self.assertRaisesRegex(wa.ExperimentError,"completed ordinary unit required"):
                units.run_unit(root/"absent",*inputs,timeout=30,readonly=True)
            self.assertFalse((root/"absent").exists())

    def test_calibration_handoff_keeps_complete_default_data_without_new_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);control=controls.ActualNativeTests();plan,query,index,tool,args=control.fixture(root)
            decision=pilot.execute(root/"calibration",plan,query,index,tool,args)
            catalog=pp.scan_query(root/"queries.fa")
            ledger=root/"calibration"/pilot.STATE;before=ledger.read_bytes()
            with patch.object(nf,"attempt",side_effect=AssertionError("handoff remapped pilot")):
                adopted=units.adopt_calibration(root/"calibration",catalog,query,index,tool)
            self.assertTrue(adopted["complete_default_pilot_preserved"])
            self.assertEqual(adopted["selections"],[{"queries":[r["name"] for r in plan["pilot_records"]],"source":decision["baseline"]}])
            self.assertEqual(ledger.read_bytes(),before)
            nested_catalog=pp.scan_query(query["path"])
            nested={**query,"identity":{"source_sha256":nested_catalog.source_sha256,
                    "records":[pp.asdict(r) for r in nested_catalog.records]}}
            self.assertNotEqual(nested["identity"]["source_sha256"],catalog.source_sha256)
            self.assertEqual(units.adopt_calibration(root/"calibration",catalog,nested,index,tool)["selections"],adopted["selections"])
            # Sequence membership, not an incidental catalogue parent path,
            # controls whether completed pilot results can be reused.
            original=(root/"queries.fa").read_bytes()
            (root/"queries.fa").write_bytes(original.replace(b"A",b"C",1))
            changed=pp.scan_query(root/"queries.fa")
            with self.assertRaisesRegex(wa.ExperimentError,"record content"):
                units.adopt_calibration(root/"calibration",changed,query,index,tool)

    def test_readonly_unit_rejects_linked_metadata_before_snapshot_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=self.fixture(root);target=root/"work";target.mkdir()
            external=root/"unrelated.json";external.write_text("{}")
            (target/"unit.json").symlink_to(external)
            with patch.object(Path,"read_bytes",side_effect=AssertionError("linked state was read")):
                with self.assertRaisesRegex(wa.ExperimentError,"private resume metadata"):
                    units.run_unit(target,*inputs,timeout=30,readonly=True)


class ReviewAllowanceTests(unittest.TestCase):
    def profile(self, name, length, covered):
        import test_adaptive_screening as fixtures
        row=fixtures.row(covered, {"chr1":covered} if covered else {}, length=length)
        return {name:row}

    def test_prior_reviews_count_against_same_whole_workload_allowance(self):
        records=[{"name":str(i),"length":100} for i in range(100)]
        result=units.review_plan(self.profile("5",100,0),records,previously_reviewed=[str(i) for i in range(5)])
        self.assertEqual(result["action"],"stop_filtered_continuation")
        self.assertEqual(result["cumulative_review_bases"],600)
        self.assertFalse(result["whole_workload_quality_approved"])

    def test_no_double_charge_when_revalidating_a_previously_reviewed_query(self):
        records=[{"name":str(i),"length":100} for i in range(100)]
        result=units.review_plan(self.profile("0",100,0),records,previously_reviewed=["0"])
        self.assertEqual(result["cumulative_review_records"],1)
        self.assertEqual(result["new_review_queries"],[])
        self.assertEqual(result["action"],"bounded_full_record_review")

    def test_coverage_without_assignment_requires_review_not_quality_approval(self):
        import test_adaptive_screening as fixtures
        profile={"0":fixtures.row(100,{"a":50,"b":50})}
        records=[{"name":str(i),"length":100} for i in range(100)]
        result=units.review_plan(profile,records)
        self.assertEqual(result["review_queries"],["0"])
        self.assertEqual(result["action"],"bounded_full_record_review")
        self.assertFalse(result["native_baseline_compared"])

    def test_window_specific_dispersion_is_not_used_to_reject_complete_native_chains(self):
        import test_adaptive_screening as fixtures
        row=fixtures.row(100,{"a":100,"b":90})
        row["assignment_candidates"]["a"]["anchor_spans"]["+"]=[0,1000]
        profile={"0":row};records=[{"name":str(i),"length":100} for i in range(100)]
        result=units.review_plan(profile,records)
        self.assertEqual(result["action"],"no_obvious_assignment_risk")
        self.assertEqual(result["screen"]["queries"][0]["assigned_targets"],["a","b"])
        self.assertFalse(result["screen"]["window_coherence_rule_applied"])
        # Do not weaken the actual approximate-window guard.
        window=pilot.quality.screen_candidate_projection(profile)
        self.assertIn("non_collinear_target_support",window["queries"][0]["reasons"])

    def test_secondary_target_just_below_assignment_threshold_requests_review(self):
        import test_adaptive_screening as fixtures
        profile={"0":fixtures.row(100,{"a":100,"b":55})}
        records=[{"name":str(i),"length":100} for i in range(100)]
        result=units.review_plan(profile,records)
        self.assertEqual(result["review_queries"],["0"])
        self.assertIn("near_assignment_threshold",result["screen"]["queries"][0]["reasons"])
