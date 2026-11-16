import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_adaptive_pilot as audit


class PilotReauditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = self.root / "screening.json"
        self.row = "q\t100\t0\t100\t+\tt\t100\t0\t100\t100\t100\t60\tcg:Z:100M\n"

    def fixture(self, reverse=False, repeats=2):
        runs = []
        for rep in range(repeats):
            for fraction in ("default", "0.005"):
                text = self.row.replace("\t+\t", "\t-\t") if reverse and fraction != "default" else self.row
                paf = self.root / f"r{rep}-f{fraction}.paf"
                paf.write_text(text)
                runs.append({"repeat": rep, "fraction": fraction, "outcome": "completed",
                             "wall_seconds": 100 if fraction == "default" else 10,
                             "mid_occ": 500 if fraction == "default" else 50,
                             "paf_sha256": hashlib.sha256(text.encode()).hexdigest()})
        report = {"status": "screening_completed_not_production_acceptance", "policy": "adaptive-screening-v1",
                  "input_content_unchanged": True, "runs": runs,
                  "sources": {"query": {"records": [{"name": "q", "length": 100}]},
                              "reference": {"records": [{"name": "t", "length": 100}]}}}
        self.report.write_text(json.dumps(report))
        return report

    def test_reaudit_selects_without_running_mapper_or_mutating_report(self):
        self.fixture()
        before = self.report.read_bytes()
        with patch("subprocess.Popen", side_effect=AssertionError("must not map")):
            result = audit.audit(self.report)
        self.assertEqual(result["selected_for_next_experiment"], "0.005")
        self.assertFalse(result["mapper_executed"])
        self.assertFalse(result["production_approved"])
        self.assertEqual(self.report.read_bytes(), before)

    def test_old_coverage_only_candidate_is_rejected_for_strand_flip(self):
        self.fixture(reverse=True)
        result = audit.audit(self.report)
        self.assertIsNone(result["selected_for_next_experiment"])
        self.assertTrue(all("strand_flip" in c["loss"]["reasons"] for c in result["comparisons"]))

    def test_changed_completed_paf_is_rejected(self):
        self.fixture()
        (self.root / "r0-f0.005.paf").write_text("")
        with self.assertRaises(ValueError):audit.audit(self.report)

    def test_missing_repeat_never_authorizes_selection(self):
        self.fixture(repeats=1)
        self.assertIsNone(audit.audit(self.report)["selected_for_next_experiment"])

    def test_running_receipt_rejected(self):
        r = self.fixture(); r["status"] = "running"
        self.report.write_text(json.dumps(r))
        with self.assertRaises(ValueError):audit.audit(self.report)

    def test_duplicate_condition_rejected(self):
        r = self.fixture(); r["runs"].append(r["runs"][0])
        self.report.write_text(json.dumps(r))
        with self.assertRaises(ValueError):audit.audit(self.report)

    def test_partial_paf_for_timeout_is_never_read(self):
        r = self.fixture()
        for run in r["runs"]:
            if run["fraction"] == "default":
                run.update(outcome="timeout", wall_budget_seconds=100)
                (self.root / f'r{run["repeat"]}-fdefault.paf').write_text("invalid partial PAF")
        self.report.write_text(json.dumps(r))
        result = audit.audit(self.report)
        self.assertIsNone(result["selected_for_next_experiment"])
        self.assertEqual(len(result["paf_sha256"]), 2)
        self.assertEqual(result["completed_record_review_plans"], [])


    def test_local_review_plan_binds_completed_sources_without_promoting_filter(self):
        self.fixture(reverse=True)
        with patch("subprocess.Popen", side_effect=AssertionError("must not map")):
            result = audit.audit(self.report)
        self.assertIsNone(result["selected_for_next_experiment"])
        plan = result["completed_record_review_plans"][0]
        self.assertEqual(plan["selection"], "baseline")
        self.assertTrue(plan["completed_source_hashes_verified"])
        self.assertFalse(plan["speedup_measured"])
        self.assertNotEqual(plan["baseline_paf_sha256"], plan["candidate_paf_sha256"])

    def test_review_requires_completed_repeat_pair(self):
        self.fixture(repeats=1)
        self.assertEqual(audit.audit(self.report)["completed_record_review_plans"], [])

    def test_nonrepeatable_rejected_candidate_cannot_seed_local_review(self):
        report = self.fixture(reverse=True)
        path = self.root / "r1-f0.005.paf"
        path.write_text(self.row)
        report["runs"][-1]["paf_sha256"] = hashlib.sha256(self.row.encode()).hexdigest()
        self.report.write_text(json.dumps(report))
        result = audit.audit(self.report)
        self.assertIsNone(result["selected_for_next_experiment"])
        self.assertEqual(result["completed_record_review_plans"], [])


if __name__ == "__main__":unittest.main()
