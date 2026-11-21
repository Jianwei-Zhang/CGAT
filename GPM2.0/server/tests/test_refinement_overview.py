"""All-failed denominator and overview integrity without native tool execution."""
import json
from pathlib import Path
import tempfile
import unittest

from server.tests.test_refinement_native import workspace
from server.tools import refinement_overview as overview
from server.tools import refinement_reports as reports
from server.tools.workspace_layout import WorkspaceLayout


class RefinementOverviewTests(unittest.TestCase):
    def test_all_failed_tools_keep_the_complete_lgz_gap_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            _, fasta, _ = workspace(root)
            # Same sequence, deliberately crossing line/chunk boundaries.
            fasta.write_text(">chr1\nAAAANN\n" + "N" * 98 + "CC\nCC\n")
            tools = {name: {"status": "failed", "phase": "native", "run_id": token * 32,
                            "error": "<script>not executed</script>"} for name, token in (("degap", "b"), ("tgsgapcloser", "c"))}
            batch = {"batch_id": "d" * 32, "status": "failed", "exit_code": 1, "tools": tools}
            for name, record in tools.items():
                record["report"] = reports.build_failure_report(root, name, record["run_id"], record["error"])
            result = overview.render_overview(root, batch, {})
            comparison = json.loads(Path(result["comparison"]).read_text())
            self.assertEqual(comparison["original_gap_count"], 1)
            self.assertEqual([row["status"] for row in comparison["tools"]], ["failed", "failed"])
            self.assertIn("tool_failed\ttool_failed", Path(result["gap_comparison"]).read_text())
            html = Path(result["report"]).read_text()
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertFalse((root / "05_final").exists())
            self.assertIsNone(comparison["best_tool"])
            gap = overview.baseline_gaps(WorkspaceLayout.detect(root))[0]
            self.assertEqual((gap["start"], gap["end"]), (4, 104))
            fasta.write_text(fasta.read_text().replace("AAAA", "TTTT"))
            with self.assertRaisesRegex(ValueError, "sequence changed"):
                overview.baseline_gaps(WorkspaceLayout.detect(root))

    def test_failed_report_retains_logs_without_fabricating_final_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            workspace(root)
            run_id = "a" * 32
            jobs = root / "04_refinement/01_degap/02_jobs" / run_id
            jobs.mkdir(parents=True)
            (jobs / "native.log").write_text("child exit 137\n")
            built = reports.build_failure_report(root, "degap", run_id, RuntimeError("child failed"))
            summary = json.loads((Path(built["directory"]) / "summary.json").read_text())
            self.assertFalse(summary["final_available"])
            self.assertEqual(summary["status"], "failed")
            self.assertTrue(any(path.read_text() == "child exit 137\n" for path in (Path(built["directory"]) / "assets").iterdir()))
            self.assertFalse((Path(built["directory"]) / "final_path.json").exists())
            self.assertFalse((root / "05_final").exists())


if __name__ == "__main__":
    unittest.main()
