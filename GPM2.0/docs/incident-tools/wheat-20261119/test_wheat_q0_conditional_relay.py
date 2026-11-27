import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wheat_q0_conditional_relay as gate


class GateTests(unittest.TestCase):
    def metrics(self):
        return {g: dict(has_path=True, slices=1, selected_reference_bp=400_000_000,
                        selected_source_bp=500_000_000) for g in gate.GROUPS}

    def conflict(self, lo=10, hi=20, category="other_chromosome"):
        return dict(source=["a", "contig"], current_group="1A", old_group="1B", current_orientation="+",
                    old_orientation="+", interval=[lo, hi], bp=hi-lo, category=category)

    def test_exact_11_gb_boundary_passes(self):
        self.assertEqual(gate.hard_gates(self.metrics(), [], [])["selected_source_bp"], 11_000_000_000)

    def test_one_base_below_threshold_holds(self):
        m = self.metrics(); m["Un"]["selected_source_bp"] -= 1
        with self.assertRaisesRegex(ValueError, "below 11 Gb"):
            gate.hard_gates(m, [], [])

    def test_missing_un_or_missing_main_anchor_holds(self):
        m = self.metrics(); m.pop("Un")
        with self.assertRaisesRegex(ValueError, "incomplete"): gate.hard_gates(m, [], [])
        m = self.metrics(); m["3D"]["selected_reference_bp"] = 0
        with self.assertRaisesRegex(ValueError, "trusted anchored"): gate.hard_gates(m, [], [])

    def test_source_occupancy_and_new_cross_conflicts_hold_independently(self):
        with self.assertRaisesRegex(ValueError, "duplicate"): gate.hard_gates(self.metrics(), [{}], [])
        with self.assertRaisesRegex(ValueError, "cross-chromosome"): gate.hard_gates(self.metrics(), [], [self.conflict()])

    def test_baseline_conflict_subtraction_is_coordinate_exact(self):
        self.assertFalse(gate.new_cross_conflicts([self.conflict()], [self.conflict(0, 30)]))
        result = gate.new_cross_conflicts([self.conflict(5, 25)], [self.conflict(10, 20)])
        self.assertEqual([r["interval"] for r in result], [[5, 10], [20, 25]])
        old = self.conflict(); old["source"] = ["other", "contig"]
        self.assertEqual(len(gate.new_cross_conflicts([self.conflict()], [old])), 1)

    def test_disjoint_baseline_intervals_and_orientation_only_warning(self):
        result = gate.new_cross_conflicts([self.conflict(0, 100)], [self.conflict(0, 40), self.conflict(60, 100)])
        self.assertEqual(result[0]["interval"], [40, 60])
        self.assertFalse(gate.new_cross_conflicts([self.conflict(category="opposite_orientation")], []))

    def test_failed_foreign_and_ambiguous_scheduler_results_hold(self):
        spec = dict(job_id=12, name="check", owner="/private")
        row = dict(jobId="12", jobName="check", execPath="/private", user="xbzhang26", queue="x86", state="SUCCEEDED")
        def call(rows):
            return patch.object(gate.subprocess, "check_output", return_value=json.dumps({"data": {"successData": rows}}).encode())
        with call([row]): self.assertEqual(gate.job(spec, "SUCCEEDED")[0], row)
        for changes in ({"state": "FAILED"}, {"execPath": "/other"}, {"jobId": "13"}):
            with call([{**row, **changes}]):
                with self.assertRaises(ValueError): gate.job(spec, "SUCCEEDED")
        with call([row, row]):
            with self.assertRaisesRegex(ValueError, "ambiguous"): gate.job(spec, "SUCCEEDED")

    def test_kit_tamper_and_single_write_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); f = root/"member.py"; f.write_text("original")
            (root/"kit.sha256").write_text(gate.digest(f) + "  member.py\n")
            gate.verify_kit(root); f.write_text("changed")
            with self.assertRaisesRegex(ValueError, "changed"): gate.verify_kit(root)
            gate.write_once(root/"intent.json", {"once": True})
            with self.assertRaises(FileExistsError): gate.write_once(root/"intent.json", {"twice": True})

    def test_engineering_relay_requires_the_qualified_installed_revision(self):
        config={"engine_revision":"2064", "runtime_revision":"new"}
        transition={"exact_engineering_change":{"schema":"q0_exact_pair_engineering_v1",
            "baseline_revision":"2064", "runtime_revision":"new", "qualification":{}}}
        report={"field_exact_equal":True,"real_worker_dispatch_verified":True,"baseline_revision":"2064",
                "candidate_output_sha256":"a"*64,"baseline_output_sha256":"a"*64,
                "mapper_calls":0,"formal_workspace_modified":False}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"report.json";p.write_text(json.dumps(report))
            with patch.object(gate,"bound",return_value=p):
                gate.verify_engineering_binding(config,transition,{"source_revision":"new"})
                with self.assertRaisesRegex(ValueError,"revision differs"):
                    gate.verify_engineering_binding(config,transition,{"source_revision":"old"})
                report["field_exact_equal"]=False;p.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError,"equivalence gate"):
                    gate.verify_engineering_binding(config,transition,{"source_revision":"new"})
        with self.assertRaisesRegex(ValueError,"unqualified"):
            gate.verify_engineering_binding(config,{}, {})
        gate.verify_engineering_binding({"engine_revision":"2064"},{},{})


    def test_validation_source_distinguishes_runtime_and_scientific_baseline(self):
        source={"engine_commit":"new","scientific_baseline_commit":"2064",
                "path_policy":{"reference_locus_padding_bp":100000}}
        config={"engine_revision":"2064","runtime_revision":"new"}
        gate.verify_validation_source(config,source)
        for wrong in ({"engine_revision":"2064"},{"engine_revision":"other","runtime_revision":"new"}):
            with self.assertRaises(ValueError):gate.verify_validation_source(wrong,source)
        source["path_policy"]["reference_locus_padding_bp"]=1000000
        with self.assertRaisesRegex(ValueError,"engine/padding"):gate.verify_validation_source(config,source)

    def test_source_boolean_is_not_a_length(self):
        m = self.metrics(); m["Un"]["selected_source_bp"] = True
        with self.assertRaisesRegex(ValueError, "invalid source"): gate.hard_gates(m, [], [])


if __name__ == "__main__":
    unittest.main()
