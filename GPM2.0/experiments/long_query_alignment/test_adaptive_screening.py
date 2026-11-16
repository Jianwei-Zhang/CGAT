from pathlib import Path
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import adaptive_screening as policy
import benchmark_adaptive_screening as bench


def row(covered=100, targets=None, length=100, strand="+"):
    targets = {"chr1": covered} if targets is None else targets
    return {"length": length, "covered": covered, "targets": targets,
            "target_strands": {t: {strand: n} for t, n in targets.items()},
            "assignment_candidates": {t: {"covered": n, "strand_weights": {"+": n if strand == "+" else 0,
                "-": n if strand == "-" else 0}, "anchor_start": 1} for t, n in targets.items()}}


def measurement(outcome="completed", wall=100, mid=500):
    return {"outcome": outcome, "wall_seconds": wall, "mid_occ": mid}


class AdaptiveScreeningTests(unittest.TestCase):
    def test_size_only_requests_pilot_not_lower_sensitivity(self):
        r = policy.screening_gate(14_467_938_249, [{"name": "q", "length": 289_508_469}])
        self.assertEqual(r["action"], "bounded_pilot")
        self.assertEqual(r["long_queries"], ["q"])
        self.assertFalse(r["automatic_sensitivity_change"])
        self.assertFalse(r["thresholds_calibrated"])

    def test_large_fragmented_input_does_not_trigger_lossy_mapping(self):
        r = policy.screening_gate(15_000_000_000, [{"name": str(i), "length": 10000} for i in range(100)])
        self.assertEqual(r["action"], "standard")

    def test_length_boundary_separate_from_performance_gate(self):
        for length, expected in ((policy.LONG_QUERY_LIMIT, []), (policy.LONG_QUERY_LIMIT + 1, ["q"])):
            r = policy.screening_gate(1_000_000, [{"name": "q", "length": length}])
            self.assertEqual(r["long_queries"], expected)

    def test_invalid_or_duplicate_records_rejected(self):
        for records in ([], [{"name": "q", "length": 0}], [{"name": "q", "length": 1}] * 2):
            with self.assertRaises(ValueError):
                policy.screening_gate(100, records)

    def test_positive_loss_cannot_be_hidden_by_gain_elsewhere(self):
        before = {"a": row(100), "b": row(80)}
        after = {"a": row(80), "b": row(100)}
        loss = policy.assess_loss(before, after)
        self.assertFalse(loss["passed"])
        self.assertEqual(loss["positive_loss_fraction"], .1)

    def test_single_query_loss_not_hidden_by_large_easy_record(self):
        before = {"hard": row(), "easy": row(100000, length=100000)}
        after = {"hard": row(90), "easy": row(100000, length=100000)}
        loss = policy.assess_loss(before, after)
        self.assertLess(loss["positive_loss_fraction"], .005)
        self.assertIn("per_query_coverage_loss", loss["reasons"])

    def test_chromosome_flip_not_hidden_by_equal_coverage(self):
        loss = policy.assess_loss({"q": row()}, {"q": row(targets={"chr2": 100})})
        self.assertIn("assignment_flip", loss["reasons"])

    def test_multiple_downstream_assignments_are_not_reduced_to_winner(self):
        before = row(targets={"chr1": 100, "chr2": 65})
        loss = policy.assess_loss({"q": before}, {"q": row()})
        self.assertIn("downstream_assignment_removed", loss["reasons"])
        self.assertEqual(loss["downstream_assignments_removed"], [{"query": "q", "target": "chr2"}])

    def test_block_weight_orientation_flip_is_not_hidden_by_unchanged_unions(self):
        before, after = row(), row()
        before["target_strands"] = after["target_strands"] = {"chr1": {"+": 100, "-": 60}}
        before["assignment_candidates"]["chr1"]["strand_weights"] = {"+": 100, "-": 120}
        after["assignment_candidates"]["chr1"]["strand_weights"] = {"+": 100, "-": 60}
        loss = policy.assess_loss({"q": before}, {"q": after})
        self.assertIn("downstream_orientation_changed", loss["reasons"])

    def test_anchor_shift_is_reported_without_inventing_an_accuracy_threshold(self):
        before, after = row(), row()
        after["assignment_candidates"]["chr1"]["anchor_start"] = 11
        loss = policy.assess_loss({"q": before}, {"q": after})
        self.assertEqual(loss["downstream_anchor_shifts"][0]["delta_bp"], 10)

    def test_strand_flip_not_hidden_by_same_target_and_coverage(self):
        loss = policy.assess_loss({"q": row()}, {"q": row(strand="-")})
        self.assertIn("strand_flip", loss["reasons"])
        self.assertEqual(loss["strand_flips"], ["q"])

    def test_strand_ambiguity_cannot_be_hidden_by_filtering(self):
        before = row()
        before["target_strands"] = {"chr1": {"+": 100, "-": 95}}
        loss = policy.assess_loss({"q": before}, {"q": row()})
        self.assertIn("strand_ambiguity_hidden", loss["reasons"])

    def test_losing_majority_direction_is_explicit(self):
        after = row()
        after["target_strands"] = {"chr1": {"+": 55, "-": 45}}
        loss = policy.assess_loss({"q": row()}, {"q": after})
        self.assertIn("strand_assignment_lost", loss["reasons"])

    def test_legacy_directionless_profile_needs_reaudit(self):
        old = row(); del old["target_strands"]
        self.assertIn("strand_evidence_missing", policy.assess_loss({"q": old}, {"q": row()})["reasons"])

    def test_malformed_strand_coverages_are_rejected(self):
        for values in ({"chr1": {"?": 100}}, {"chr1": {"+": 110}}, {"chr2": {"+": 100}}, {"chr1": {"+": 50}}):
            bad = row(); bad["target_strands"] = values
            with self.assertRaises(ValueError):
                policy.assess_loss({"q": row()}, {"q": bad})

    def test_improved_low_coverage_is_not_hidden_target_ambiguity(self):
        before = row(50, {"chr1": 30, "chr2": 20})
        loss = policy.assess_loss({"q": before}, {"q": row()})
        self.assertTrue(loss["passed"], loss)

    def test_removed_competitor_cannot_look_more_certain(self):
        loss = policy.assess_loss({"q": row(targets={"chr1": 100, "chr2": 95})}, {"q": row()})
        self.assertIn("ambiguity_hidden", loss["reasons"])

    def test_missing_records_are_not_zero_coverage(self):
        with self.assertRaises(ValueError):
            policy.assess_loss({"a": row(), "b": row()}, {"a": row()})

    def test_unmapped_in_both_is_not_a_new_loss(self):
        self.assertTrue(policy.assess_loss({"q": row(0, {})}, {"q": row(0, {})})["passed"])

    def test_loss_of_mapped_query_is_explicit(self):
        loss = policy.assess_loss({"q": row(1)}, {"q": row(0, {})})
        self.assertEqual(loss["lost_queries"], ["q"])

    def test_same_mid_occ_is_not_filtering_evidence(self):
        r = policy.compare(measurement(), measurement(wall=10))
        self.assertEqual(r["reason"], "filter_threshold_unchanged")

    def test_baseline_timeout_only_gives_lower_bound(self):
        r = policy.compare(measurement("timeout", wall=600), measurement(wall=100, mid=50))
        self.assertEqual(r["speedup_lower_bound"], 6)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["reason"], "baseline_quality_unavailable")

    def test_timeout_cleanup_is_not_counted_as_speedup(self):
        baseline = {**measurement("timeout", wall=603), "wall_budget_seconds": 600}
        r = policy.compare(baseline, measurement(wall=100, mid=50))
        self.assertEqual(r["speedup_lower_bound"], 6)

    def test_failed_candidate_never_selected(self):
        for status in ("timeout", "tool_failure", "audit_failure", "cancelled"):
            self.assertFalse(policy.compare(measurement(), measurement(status, wall=1, mid=50))["eligible"])

    def test_fast_candidate_still_needs_quality_evidence(self):
        r = policy.compare(measurement(), measurement(wall=1, mid=50))
        self.assertFalse(r["eligible"])

    def test_speed_and_loss_both_required(self):
        before = {"q": row()}
        self.assertFalse(policy.compare(measurement(), measurement(wall=80, mid=50), before, before)["eligible"])
        self.assertFalse(policy.compare(measurement(), measurement(wall=10, mid=50), before, {"q": row(80)})["eligible"])
        r = policy.compare(measurement(), measurement(wall=10, mid=50), before, before)
        self.assertTrue(r["eligible"])
        self.assertFalse(r["production_approved"])

    def test_all_unmapped_baseline_cannot_qualify_fast_strategy(self):
        empty = {"q": row(0, {})}
        r = policy.compare(measurement(), measurement(wall=10, mid=50), empty, empty)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["reason"], "baseline_has_no_mapped_evidence")

    def test_profile_counts_union_and_retains_zero_hit_records(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.paf"
            p.write_text("q\t100\t0\t50\t+\tt\t100\t0\t50\t50\t50\t60\n"
                         "q\t100\t20\t80\t+\tt\t100\t20\t80\t60\t60\t60\n")
            r = policy.coverage_profile(p, [{"name": "q", "length": 100}, {"name": "zero", "length": 10}])
            self.assertEqual(r["q"]["covered"], 80)
            self.assertEqual(r["q"]["targets"], {"t": 80})
            self.assertEqual(r["zero"]["covered"], 0)

    def test_different_policy_has_different_result_identity(self):
        a = policy.receipt_identity({"query": "abc"}, {"fraction": None})
        b = policy.receipt_identity({"query": "abc"}, {"fraction": "0.01"})
        self.assertNotEqual(a, b)


@unittest.skipUnless(Path("/usr/bin/time").is_file() and os.name == "posix", "POSIX GNU time required")
class BoundedRunnerTests(unittest.TestCase):
    def test_success_and_failure_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            for code in (0, 7):
                r = bench.run_bounded([sys.executable, "-c", f"raise SystemExit({code})"], Path(d), str(code), 2, 256)
                self.assertEqual(r["outcome"], "completed" if code == 0 else "tool_failure")
                self.assertEqual(json.loads((Path(d) / f"{code}.execution.json").read_text()), r)
                self.assertIn("peak_rss_kib", r)

    def test_timeout_retains_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            r = bench.run_bounded([sys.executable, "-c", "import time; time.sleep(10)"], Path(d), "timeout", .1, 256)
            self.assertEqual(r["outcome"], "timeout")
            self.assertLess(r["wall_seconds"], 5)
            self.assertEqual(json.loads((Path(d) / "timeout.execution.json").read_text())["outcome"], "timeout")

    def test_timeout_stops_grandchild_even_if_it_ignores_term(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            marker = root / "should-not-exist"
            body = f"import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(1); pathlib.Path({str(marker)!r}).write_text('orphan')"
            parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{body!r}]); time.sleep(10)"
            r = bench.run_bounded([sys.executable, "-c", parent], root, "tree", .3, 256)
            self.assertEqual(r["outcome"], "timeout")
            time.sleep(1.1)
            self.assertFalse(marker.exists())

    def test_missing_time_tool_is_recorded_launch_failure(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bench.subprocess, "Popen", side_effect=FileNotFoundError("missing")):
            r = bench.run_bounded(["no-tool"], Path(d), "missing", 1, 256)
            self.assertEqual(r["outcome"], "launch_failure")




class CandidateProjectionScreenTests(unittest.TestCase):
    def test_full_union_coverage_without_chromosome_support_requests_review(self):
        result = policy.screen_candidate_projection({"q": row(100, {"a":50,"b":50})})
        self.assertEqual(result["queries"][0]["reasons"], ["covered_but_unassigned"])
        self.assertEqual(result["queries"][0]["action"], "bounded_review")

    def test_no_obvious_risk_is_never_a_quality_approval(self):
        result = policy.screen_candidate_projection({"q": row()})
        self.assertEqual(result["queries"][0]["action"], "no_obvious_assignment_risk")
        self.assertFalse(result["production_approved"])
        self.assertFalse(result["baseline_comparison_performed"])
        self.assertFalse(result["scientific_accuracy_proven"])

    def test_multiple_assignments_are_retained_not_reduced_to_one(self):
        result = policy.screen_candidate_projection({"q": row(100, {"a":100,"b":90})})
        self.assertEqual(result["queries"][0]["assigned_targets"], ["a","b"])
        self.assertIn("multiple_chromosome_assignments", result["queries"][0]["reasons"])

    def test_near_threshold_and_mixed_orientation_are_review_signals(self):
        uncertain = row(65)
        uncertain["target_strands"] = {"chr1": {"+":34,"-":31}}
        uncertain["assignment_candidates"]["chr1"]["strand_weights"] = {"+":34,"-":31}
        result = policy.screen_candidate_projection({"q": uncertain})
        self.assertEqual(result["queries"][0]["reasons"], ["near_assignment_threshold","orientation_ambiguous"])

    def test_unmapped_and_missing_evidence_are_not_confused(self):
        result = policy.screen_candidate_projection({"q": row(0, targets={})})
        self.assertEqual(result["queries"][0]["reasons"], ["low_reference_support"])
        missing = row(); del missing["assignment_candidates"]
        with self.assertRaises(ValueError):policy.screen_candidate_projection({"q": missing})


class CompletedRecordReviewTests(unittest.TestCase):
    def test_only_lossy_short_record_returns_to_completed_baseline(self):
        before = {"main": row(950, length=1000), "short": row(40, length=500)}
        after = {"main": row(960, length=1000), "short": row(20, length=500)}
        saved = json.dumps([before, after], sort_keys=True)
        result = policy.plan_completed_record_review(before, after)
        self.assertEqual([(r["query"], r["source"]) for r in result["queries"]],
                         [("main", "candidate"), ("short", "baseline")])
        self.assertTrue(result["reviewed_loss"]["passed"])
        self.assertFalse(result["speedup_measured"])
        self.assertFalse(result["production_approved"])
        self.assertFalse(result["per_query_sources_combined"])
        self.assertEqual(result["new_mapping_commands"], 0)
        self.assertEqual(json.dumps([before, after], sort_keys=True), saved)

    def test_global_budget_is_not_incorrectly_applied_per_record(self):
        before = {"q": row(10000, length=10000), "large": row(100000, length=100000)}
        after = {"q": row(9900, length=10000), "large": before["large"]}
        result = policy.plan_completed_record_review(before, after)
        self.assertEqual(result["selection"], "candidate")
        self.assertTrue(result["reviewed_loss"]["passed"])

    def test_global_review_ties_keep_original_record_order(self):
        before = {"z": row(1000, length=1000), "a": row(1000, length=1000)}
        after = {q: row(990, length=1000) for q in before}
        result = policy.plan_completed_record_review(before, after)
        self.assertEqual([r["source"] for r in result["queries"]], ["baseline", "candidate"])
        self.assertEqual(result["queries"][0]["reasons"], ["global_positive_coverage_loss"])
        self.assertEqual(result["reviewed_loss"]["positive_loss_fraction"], .005)

    def test_gain_cannot_pay_for_loss_elsewhere(self):
        before = {"q": row(1000, length=1000), "gain": row(500, length=1000)}
        after = {"q": row(980, length=1000), "gain": row(1000, length=1000)}
        result = policy.plan_completed_record_review(before, after)
        self.assertEqual([r["source"] for r in result["queries"]], ["baseline", "candidate"])

    def test_orientation_change_returns_complete_query_to_baseline(self):
        result = policy.plan_completed_record_review({"q": row()}, {"q": row(strand="-")})
        self.assertEqual(result["selection"], "baseline")
        self.assertIn("downstream_orientation_changed", result["queries"][0]["reasons"])

    def test_missing_baseline_evidence_cannot_authorize_a_review(self):
        original = row(); del original["assignment_candidates"]
        result = policy.plan_completed_record_review({"q": original}, {"q": row()})
        self.assertEqual(result["status"], "baseline_evidence_incomplete")
        self.assertEqual(result["queries"], [])

    def test_unmapped_baseline_does_not_prove_quality(self):
        result = policy.plan_completed_record_review({"q": row(0, targets={})}, {"q": row()})
        self.assertEqual(result["status"], "baseline_evidence_incomplete")

    def test_incomplete_query_matrix_refused(self):
        with self.assertRaises(ValueError):
            policy.plan_completed_record_review({"q": row()}, {"other": row()})


if __name__ == "__main__":
    unittest.main()
