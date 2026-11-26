"""Missing resource measurements must not become measured zero-duration work."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from report_overview_data import _manual_tool_timing
from render_overview_summary import _expand_refinement_units, _runtime_bar_html


class RuntimeTimingTests(unittest.TestCase):
    def receipts(self, timings):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        batch = root / "batch"
        for index, timing in enumerate(timings):
            path = batch / "02_jobs" / str(index) / "completion.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"row": {"tool": "degap"}, "timing": timing}))
        return _manual_tool_timing(root, batch)

    def test_rss_only_receipts_and_tool_rows_keep_unknown_duration(self):
        manual = self.receipts([{"peak_rss_mb": 64}])
        self.assertIsNone(manual["degap"]["elapsed_seconds"])
        vm = {
            "refinement_summary": {"tools": [
                {"tool": "degap", "timing": {"peak_rss_mb": 128,
                    "started_at": "2026-11-26T01:00:00Z", "ended_at": "2026-11-26T01:01:00Z"}},
            ]},
            "manual_summary": {"batches": [{"tool_timing": manual}]},
            "lgz_summary": {"timing": {"units": [
                {"unit": "q0", "stage": "q0", "elapsed_seconds": 10},
            ]}},
        }
        rows = _expand_refinement_units(vm, [])
        self.assertEqual([r["elapsed_seconds"] for r in rows], [None, None])
        self.assertEqual([r["peak_rss_mb"] for r in rows], [128, 64])
        html = _runtime_bar_html(vm)
        self.assertIn("<title>refine:DEGAP: — (offset", html)
        for unit in ("refine:DEGAP", "manual:DEGAP"):
            row = html.split(f"<code>{unit}</code>", 1)[1].split("</tr>", 1)[0]
            self.assertIn('<td class="numeric">—</td>', row)
            self.assertNotIn('<td class="numeric">0s</td>', row)

    def test_partial_attempt_or_batch_timings_do_not_claim_a_complete_total(self):
        for timings in ([{}, {"elapsed_seconds": 5}], [{"elapsed_seconds": 5}, {}]):
            with self.subTest(timings=timings):
                summary = self.receipts(timings)
                self.assertIsNone(summary["degap"]["elapsed_seconds"])
                self.assertEqual(summary["degap"]["attempt_count"], 2)
        for durations in ([None, 5], [5, None]):
            vm = {"manual_summary": {"batches": [
                {"tool_timing": {"degap": {"elapsed_seconds": n, "peak_rss_mb": 64}}}
                for n in durations
            ]}}
            self.assertIsNone(_expand_refinement_units(vm, [])[0]["elapsed_seconds"])

    def test_known_zero_and_complete_totals_remain_measurements(self):
        summary = self.receipts([{"elapsed_seconds": 0}, {"elapsed_seconds": 5}])
        self.assertEqual(summary["degap"]["elapsed_seconds"], 5)
        vm = {"refinement_summary": {"tools": [
            {"tool": "degap", "timing": {"elapsed_seconds": 0}},
            {"tool": "quartet", "timing": {"native_seconds": 5}},
        ]}}
        self.assertEqual([r["elapsed_seconds"] for r in _expand_refinement_units(vm, [])], [0, 5])

    def test_incomplete_tool_breakdown_preserves_measured_parent_total(self):
        vm = {"refinement_summary": {"tools": [
            {"tool": "degap", "timing": {"peak_rss_mb": 64}},
            {"tool": "quartet", "timing": {"elapsed_seconds": 5}},
        ]}}
        parent = {"unit": "refinement", "stage": "refinement", "elapsed_seconds": 100}
        self.assertEqual(_expand_refinement_units(vm, [parent]), [parent])


if __name__ == "__main__":
    unittest.main()
