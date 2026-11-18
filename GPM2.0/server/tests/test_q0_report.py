"""q0 decision/report facts, publication fencing, and standalone rendering."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# Report CLI modules use the installed tools directory as their import root.
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from server.tests.q0_delivery_fixture import materialize
from server.tests.test_q0_admission import EvidenceFixture, dna
from server.tests.test_q0_publication import complete_workspace, run_prepare
from server.tools.server_report import ReportSession
from server.tools.server_report_collect import inputs, collect_lgz_inputs, capture_final, final_summary
from server.tools.server_report_q0 import collect_q0_decisions, bounded_table, MODE
from server.tools.server_report_io import SCHEMA, write_json
from server.tools.render_server_report import render, outcome_summary_html, REPORT_PREVIEW_ROWS

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/grt_contract_v3/frozen_bridge_server.json"


class Q0ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "workspace"
        materialize(json.loads(FIXTURE.read_text()), self.root)

    def test_selected_sources_original_n_and_overlap_are_distinct(self):
        result = collect_q0_decisions(self.root)
        summary = result["summary"]
        self.assertEqual(summary["selected_chromosomes"], 2)
        self.assertEqual(summary["selected_datasets"], 4)
        self.assertEqual(summary["selected_source_bp"], 8600)
        self.assertEqual((summary["input_gap_joins"], summary["input_gap_n_bp"]), (1, 137))
        self.assertEqual((summary["unknown_joins"], summary["sequence_overlap_joins"]), (0, 2))
        self.assertEqual(summary["qc"], "not_measured")
        self.assertEqual(summary["unplaced_component_count"], 0)
        unused = result["tables"]["q0_unused_source_intervals"]["rows"]
        self.assertIn({"dataset": "c", "contig": "c", "start": 0, "end": 200,
                       "coordinate_system": "source_0_based_half_open"}, unused)
        self.assertTrue(result["tables"]["q0_candidate_admission"]["rows"])
        sources = result["tables"]["q0_source_composition"]["rows"]
        self.assertEqual({row["dataset_name"]: row["source_bp"] for row in sources if row["chr"] == "chr1"},
                         {"a": 2000, "b": 2200, "c": 800})
        original = next(row for row in result["tables"]["q0_retained_joins"]["rows"] if row["kind"] == "input_assembly_gap")
        self.assertEqual(original["source_interval"], {"start": 1700, "end": 1837})
        self.assertEqual(original["source"], {"dataset": "n_scaffold", "contig": "n_scaffold"})
        ranges = result["tables"]["q0_reference_unrepresented"]["rows"]
        self.assertEqual(ranges, [{"chr": "chr2", "start": 1700, "end": 5000, "coordinate_system": "ref_0_based_half_open"}])
        searches = result["tables"]["q0_search"]["rows"]
        self.assertTrue(all(row["global_optimality_claimed"] is False for row in searches))
        self.assertEqual(searches[0]["search_operation_counts"]["bridge_replacement"], 1)

    def test_schema3_inputs_do_not_rank_primary_dataset_as_q0_baseline(self):
        facts = inputs(self.root)
        self.assertEqual(facts["q0_mode"], MODE)
        self.assertEqual({row["role"] for row in facts["datasets"] if row["role"] != "reference"}, {"assembly_candidate"})
        self.assertIsNotNone(collect_lgz_inputs(self.root)["q0_construction"])

    def test_unknown_connection_and_unconstructed_chromosome_are_explicit(self):
        fixture = EvidenceFixture({"chr1": 6000, "chr2": 3000})
        a = fixture.source("a", dna(1500, 1101))
        b = fixture.source("b", dna(1600, 1102))
        fixture.ref(a, (0, 1500), (0, 1500))
        fixture.ref(b, (0, 1600), (2500, 4100))
        root = complete_workspace(fixture, self.directory / "partial")
        result = run_prepare(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = collect_q0_decisions(root)
        self.assertEqual(summary["summary"]["not_constructed_chromosomes"], 1)
        self.assertEqual(summary["summary"]["unknown_joins"], 1)
        self.assertEqual(summary["summary"]["unknown_join_n_bp"], 100)
        self.assertEqual(summary["summary"]["input_gap_joins"], 0)
        chr2 = next(row for row in summary["tables"]["q0_chromosomes"]["rows"] if row["chr"] == "chr2")
        self.assertEqual(chr2["status"], "not_constructed")
        self.assertEqual(chr2["source_bp_by_dataset"], {})
        self.assertIn({"chr": "chr1", "start": 1500, "end": 2500, "coordinate_system": "ref_0_based_half_open"},
                      summary["tables"]["q0_reference_unrepresented"]["rows"])
        session = ReportSession(root, [], "partial-report")
        relative = "steps/001.json"
        write_json(session.report / relative, {"schema_version": SCHEMA, "run_id": session.run_id,
            "stage_id": "grt_prepare", "title": "q0 构建", "status": "success", "facts": collect_lgz_inputs(root)})
        session.manifest["steps"] = [relative]
        session.save()
        write_json(session.report / "final_summary.json", final_summary(root, session.report))
        html = render(session.report).read_text()
        self.assertIn("q0 中有 1 个参考 chr 未构建", html)
        self.assertIn('id="q0-construction"', html)

    def test_corrupt_or_missing_selection_never_falls_back_to_primary(self):
        path = self.root / "metadata/grt_q0_selection.json"
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "differs from the published freeze"):
            collect_q0_decisions(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "requires the published selection"):
            collect_q0_decisions(self.root)

    def test_failed_prepare_does_not_report_previous_workspace_q0_as_this_run(self):
        session = ReportSession(self.root, [], "failed-current-run")
        self.assertTrue((self.root / "grt/q/q0.fa").exists())
        summary = final_summary(self.root, session.report)
        self.assertIsNone(summary["outcome_summary"]["starting_gap_count"])
        self.assertNotIn("q0", summary.get("sequence_versions", {}))
        self.assertFalse(summary.get("available", False))
        write_json(session.report / "final_summary.json", summary)
        text = render(session.report).read_text()
        self.assertIn("尚无成功发布的 q0 构建摘要", text)
        self.assertNotIn("原始主组装", text)

    def test_successful_snapshot_and_offline_render_do_not_reread_mutated_q0(self):
        session = ReportSession(self.root, [], "successful-current-run")
        write_json(session.report / "final_snapshot.json", {"schema_version": SCHEMA, "run_id": session.run_id,
                                                            **capture_final(self.root)})
        (self.root / "grt/q/q0.fa").write_text(">wrong\nAAAA\n")
        summary = final_summary(self.root, session.report)
        self.assertEqual(summary["sequence_versions"]["q0"]["length_bp"], 8737)
        self.assertEqual(summary["outcome_summary"]["gap_count_change"], 0)
        self.assertEqual(summary["outcome_summary"]["t2t_scope"], "emitted_sequences_only")
        write_json(session.report / "final_summary.json", summary)
        html = render(session.report).read_text()
        self.assertIn("多组装候选 → q0", html)
        self.assertIn("新增未知连接数", html)
        self.assertIn("参考未被选中锚点覆盖的范围", html)
        self.assertIn("Gap 数净变化", html)
        self.assertNotIn("原始主组装", html)
        portable = self.directory / "portable_report"
        shutil.copytree(session.report, portable)
        self.root.rename(self.directory / "workspace-hidden")
        result = subprocess.run([sys.executable, str(portable / "render_report.py")], cwd=self.directory,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((portable / "report.html").read_text(), html)

    def test_current_prepare_snapshot_survives_later_failure_without_old_q4(self):
        session = ReportSession(self.root, [], "prepare-complete-later-failed")
        facts = collect_lgz_inputs(self.root)
        relative = "steps/001.json"
        write_json(session.report / relative, {"schema_version": SCHEMA, "run_id": session.run_id,
                                               "stage_id": "grt_prepare", "status": "success", "facts": facts})
        session.manifest["steps"] = [relative]
        session.save()
        (self.root / "grt/q/q0.fa").write_text(">changed\nAAAA\n")
        summary = final_summary(self.root, session.report)
        self.assertEqual(summary["sequence_versions"]["q0"]["length_bp"], 8737)
        self.assertEqual(summary["outcome_summary"]["starting_gap_count"], 1)
        self.assertIsNone(summary["outcome_summary"]["remaining_gap_count"])
        self.assertFalse(summary.get("available", False))
        self.assertEqual(summary["q0_construction"]["summary"]["input_gap_n_bp"], 137)

    def test_successful_q0_snapshot_from_another_invocation_is_not_accepted(self):
        session = ReportSession(self.root, [], "current-run")
        relative = "steps/001.json"
        write_json(session.report / relative, {"schema_version": SCHEMA, "run_id": "previous-run",
                                               "stage_id": "grt_prepare", "status": "success", "facts": collect_lgz_inputs(self.root)})
        session.manifest["steps"] = [relative]
        session.save()
        with self.assertRaisesRegex(ValueError, "q0 snapshot belongs to another invocation"):
            final_summary(self.root, session.report)

    def test_preview_is_bounded_but_preserves_count_and_audit_origin(self):
        rows = [{"chr": str(index)} for index in range(1001)]
        result = bounded_table(rows)
        self.assertEqual(len(result["rows"]), REPORT_PREVIEW_ROWS)
        self.assertEqual(result["row_count"], 1001)
        self.assertEqual(len(rows), 1001)
        self.assertTrue(result["preview_only"])
        self.assertEqual(result["source"], "metadata/grt_q0_selection.json")

    def test_net_gap_increase_is_not_hidden_as_zero_closures(self):
        html = outcome_summary_html({"outcome_summary": {"starting_gap_count": 1, "remaining_gap_count": 3}})
        self.assertIn("+2", html)
        self.assertIn("Gap 数净变化", html)
        self.assertNotIn("关闭 Gap", html)
        self.assertIn("减少不等于真实缺失序列闭合", html)
