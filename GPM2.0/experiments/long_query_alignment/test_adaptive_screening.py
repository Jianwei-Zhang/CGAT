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


def row(covered=100, targets=None, length=100):
    return {"length": length, "covered": covered, "targets": {"chr1": covered} if targets is None else targets}


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


if __name__ == "__main__":
    unittest.main()
