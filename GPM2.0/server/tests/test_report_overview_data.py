"""Report lifecycle, portability and scientific denominators. No aligner/native tool needed."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_scenarios_fixture import workspace, text, RUN, BID, PRIVATE
from regenerate_reports import regenerate
from report_overview_data import build_overview_view_model
from render_server_report import render, bounded_id_projection
from run_all_runner import PlanUnit, Runner, WorkspaceLock
from refinement_jobs_index import refresh_after_delivery, write_automatic_index
from refine_report import automatic_overview_digest, _with_manual_section
from post_lgz_refinement import validate_completion
from server_report import prepare_start, prepare_finish
from server_report_io import write_json
from server_report_collect import collect_unit
from delivery_archive import delivery_staging_path
from workspace_layout import initialize_workspace, WorkspaceLayout


class ReportOverviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.root = self.parent / "work"

    def test_large_denominator_and_order(self):
        vm = workspace(self.root, "large")
        ref = vm["refinement_summary"]
        rows = ref["by_chromosome"]
        matrix = ref["gap_matrix"]
        self.assertEqual(
            (matrix["total_gap_count"], matrix["preview_count"], len(matrix["rows"]), matrix["truncated"]),
            (336, 200, 200, True),
        )
        self.assertEqual(len(rows), 21)
        self.assertEqual(vm["lgz_summary"]["funnel"]["reference_aligned_contigs"], 21)
        self.assertEqual(
            [r["chromosome"] for r in rows], [r["chromosome"] for r in vm["lgz_summary"]["chromosomes"]]
        )
        self.assertTrue(matrix["full_tsv_href"].endswith("gap_comparison.tsv"))
        for row in rows:
            for c in row["tools"].values():
                self.assertEqual(
                    (c["original_gap_count"], sum(c[k] for k in ("closed", "rejected", "partial", "unfilled"))),
                    (16, 16),
                )
        self.assertNotIn(PRIVATE, json.dumps(vm))
        self.assertIsNone(ref["best_tool"])
        self.assertIs(ref["biological_accuracy_validated"], False)

    def test_zero_is_not_failed(self):
        vm = workspace(self.root, "partial")
        a, b = vm["refinement_summary"]["tools"]
        self.assertEqual((a["accepted_edit_count"], a["retained_flank_count"], a["status"]), (0, 1, "published"))
        self.assertEqual((b["counts"], b["status"]), (None, "failed"))
        for c in vm["refinement_summary"]["by_chromosome"]:
            self.assertEqual(c["tools"]["tgsgapcloser"]["not_evaluated"], c["original_gap_count"])

    def test_four_layouts_and_safe_links(self):
        for case, first, project, jobs, schema in [
            ("success", "01_inputs", True, False, "cgat.workspace.job-outputs.v2"),
            ("v2_job", "01_inputs", False, True, "cgat.workspace.job-outputs.v1"),
            ("v2_legacy", "01_inputs", False, True, "cgat.workspace"),
            ("legacy_v1", "data", False, False, "cgat.workspace"),
        ]:
            root = self.parent / case
            model = workspace(root, case)
            layout = model["meta"]["workspace_layout"]
            dirs = {r["path"]: r for r in model["result_paths"]["directory_tree"]}
            self.assertIn(first, dirs)
            self.assertEqual("08_refinement_jobs" in dirs, jobs)
            self.assertEqual((layout["schema"], layout["project_delivery"]), (schema, project))
            self.assertTrue(dirs[".runtime" if layout["version"] == 2 else ".run_all"]["protected"])
        root = self.parent / "success"
        target = root / "07_delivery/success.auto.patch.zip"
        target.unlink()
        target.symlink_to(self.parent / "legacy_v1/report/report.html")
        vm = build_overview_view_model(root)
        row = next(r for r in vm["result_paths"]["quick_pickup"] if r["label_key"] == "auto")
        self.assertIsNone(row["href"])
        self.assertFalse(row["publication_verified"])

    def test_detached_no_source_changes_no_fasta_reads_and_no_outside_links(self):
        def snapshot():
            return {
                p.relative_to(self.root): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).digest())
                for p in self.root.rglob("*")
                if p.is_file()
            }

        workspace(self.root, "success")
        before = snapshot()
        orig = Path.open

        def guard(p, *args, **kwargs):
            if p.is_relative_to(self.root) and p.suffix in (".fa", ".fasta", ".fq", ".zip", ".gz"):
                self.fail("opened a source genome/reads/archive: " + str(p))
            return orig(p, *args, **kwargs)

        out = self.parent / "external"
        with patch.object(Path, "open", guard):
            regenerate(self.root, out)
        self.assertEqual(snapshot(), before)
        for f in (
            "report.html",
            "overview_view_model.json",
            "01_lgz/render_report.py",
            "01_lgz/report.html",
            "02_refinement/01_degap/native.html",
            "02_refinement/01_degap/gaps/000001.html",
            "02_refinement/01_degap/native_visualization/index.html",
            f"03_comparison/{BID}/gap_comparison.tsv",
        ):
            self.assertTrue((out / f).is_file(), f)
        vm = json.loads((out / "overview_view_model.json").read_text())
        self.assertTrue(all(not r["href"] for r in vm["result_paths"]["quick_pickup"]))
        self.assertIn("02_refinement/01_degap/report.html", (out / "report.html").read_text())
        self.assertNotIn("../07_delivery", (out / "report.html").read_text())
        with self.assertRaises(ValueError):
            regenerate(self.root, self.root / "newreport")
        with self.assertRaises(ValueError):
            regenerate(self.root, out)
        self.assertEqual(snapshot(), before)

    def test_manual_private_snapshots_and_overlay(self):
        vm = workspace(self.root, "manual")
        self.assertEqual(vm["meta"]["mode"], "manual_only")
        self.assertEqual(
            {r["report_status"] for r in vm["manual_summary"]["batches"]}, {"pending_app_import", "no_patch"}
        )
        out = self.parent / "out"
        regenerate(self.root, out)
        self.assertEqual(len(list((out / "manual").glob("*/report.html"))), 2)
        self.assertNotIn(PRIVATE, json.dumps(vm))
        self.assertFalse(any(PRIVATE.encode() in p.read_bytes() for p in out.rglob("*") if p.is_file()))
        page = out / "report.html"
        before = automatic_overview_digest(page)
        text(page, _with_manual_section(page.read_text(), "new manual rows"))
        self.assertEqual(automatic_overview_digest(page), before)

    def test_tool_report_omits_private_reads_from_command_and_log(self):
        from test_refinement_reports import fixture
        from refinement_reports import build_tool_report

        result = fixture(self.root)
        p = Path(result["staging"]) / "provenance.json"
        data = json.loads(p.read_text())
        data["execution"]["recipe"]["reads"] = [dict(technology="hifi", sha256="f" * 64, path=PRIVATE)]
        data["execution"]["command"] = ["native", PRIVATE]
        write_json(p, data)
        jobs = self.root / "04_refinement/01_degap/02_jobs" / result["run_id"]
        marker = jobs / "invocation.json"
        data = json.loads(marker.read_text())
        data["provenance_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        write_json(marker, data)
        text(jobs / "native.log", "command reads " + PRIVATE)
        site = Path(build_tool_report(self.root, result)["directory"])
        self.assertFalse(any(PRIVATE.encode() in f.read_bytes() for f in site.rglob("*") if f.is_file()))
        summary = json.loads((site / "summary.json").read_text())
        self.assertEqual(summary["execution"]["recipe"]["reads"], [dict(technology="hifi", sha256="f" * 64)])
        self.assertEqual(
            next(r["availability"] for r in summary["artifacts"] if r["workspace_path"].endswith("native.log")),
            "server_only_private_reads",
        )

    def test_old_event_arrays_bounded_only_in_html_and_mixed_snapshots(self):
        workspace(self.root, "lgz_only")
        folder = self.root / "06_report/01_lgz"
        f = folder / "final_summary.json"
        data = json.loads(f.read_text())
        event = {
            "event_id": "e",
            "status": "rejected",
            "evidence_ids": ["e-" + str(i) + "x" * 38 for i in range(10206)],
            "usage_ids": ["u-" + str(i) + "y" * 38 for i in range(20412)],
        }
        data.update(events=[event], event_reconciliation=[{"final_event": event}])
        write_json(f, data)
        before = f.read_bytes()
        render(folder)
        self.assertLess((folder / "report.html").stat().st_size, 350000)
        self.assertEqual(before, f.read_bytes())
        self.assertEqual(bounded_id_projection(event)["usage_ids"]["count"], 20412)
        vm = build_overview_view_model(self.root)
        self.assertFalse(
            any(
                k in json.dumps(vm)
                for k in ('"evidence_ids"', '"usage_ids"', '"events"', '"event_reconciliation"')
            )
        )
        data["run_id"] = "older"
        write_json(f, data)
        vm = build_overview_view_model(self.root)
        self.assertFalse(vm["lgz_summary"]["chromosomes"])
        self.assertIn("final_summary.json: missing_or_invalid", vm["lgz_summary"]["diagnostics"])

    def test_delivery_refresh_reseals_only_verified_receipt(self):
        workspace(self.root, "lgz_only")
        l = WorkspaceLayout.detect(self.root)
        self.assertTrue(validate_completion(self.root, RUN)[0])
        completion = l.path(f".runtime/refinement/completions/{RUN}.json")
        before = json.loads(completion.read_text())
        page = l.path("06_report/report.html")
        # Old renderer sealed a pre-delivery overview. The published catalog and artifacts already exist.
        text(page, "<main>before project commit</main>")
        before["overview_files"]["06_report/report.html"] = automatic_overview_digest(page)
        write_json(completion, before)
        lock = WorkspaceLock(self.root, "test-owner")
        lock.acquire()
        self.addCleanup(lock.release)
        refresh_after_delivery(self.root, RUN, lock)
        self.assertTrue(validate_completion(self.root, RUN)[0])
        self.assertIsNone(write_automatic_index(l, completion))
        self.assertIn("work.light.zip", page.read_text())
        self.assertFalse((self.root / "06_report/03_comparison").exists())
        after = json.loads(completion.read_text())
        self.assertEqual(after.pop("overview_files")["06_report/report.html"], automatic_overview_digest(page))
        before.pop("overview_files")
        self.assertEqual(after, before)
        text(page, "tampered")
        old = completion.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            refresh_after_delivery(self.root, RUN, lock)
        self.assertEqual(completion.read_bytes(), old)

    def test_full_refresh_real_multi_tool_index_and_auto_patch(self):
        workspace(self.root, "success")
        l = WorkspaceLayout.detect(self.root)
        lock = WorkspaceLock(self.root, RUN)
        lock.acquire()
        self.addCleanup(lock.release)
        completion = l.path(f".runtime/refinement/completions/{RUN}.json")
        self.assertTrue(validate_completion(self.root, RUN)[0])
        index = refresh_after_delivery(self.root, RUN, lock)
        self.assertTrue(index.is_file())
        self.assertEqual(write_automatic_index(l, completion), index)
        self.assertTrue(validate_completion(self.root, RUN)[0])
        self.assertIn("work.auto.patch.zip", l.path("06_report/report.html").read_text())
        for job in json.loads(index.read_text())["jobs"]:
            self.assertEqual(json.loads(l.path(job).read_text())["delivery_state"], "committed")

    def test_in_place_recovers_between_html_and_completion_replacements(self):
        import refinement_jobs_index as jobs
        from regenerate_reports import main

        workspace(self.root, "lgz_only")
        l = WorkspaceLayout.detect(self.root)
        completion = l.path(f".runtime/refinement/completions/{RUN}.json")
        page = l.path("06_report/report.html")
        text(page, "<main>old sealed page</main>")
        receipt = json.loads(completion.read_text())
        receipt["overview_files"]["06_report/report.html"] = automatic_overview_digest(page)
        write_json(completion, receipt)
        durable = jobs.durable_json

        def interrupted(path, payload):
            if path == completion:
                raise OSError("injected receipt write interruption")
            return durable(path, payload)

        with (
            patch.object(jobs, "durable_json", side_effect=interrupted),
            self.assertRaisesRegex(OSError, "injected"),
        ):
            main(["--server-dir", str(self.root), "--in-place"])
        self.assertFalse(validate_completion(self.root, RUN)[0])
        main(["--server-dir", str(self.root), "--in-place"])
        self.assertTrue(validate_completion(self.root, RUN)[0])
        self.assertFalse(l.path(f".runtime/refinement/overview-refresh/{RUN}.json").exists())

    def test_failure_interrupt_not_prepare_and_package_boundary(self):
        for i, script in enumerate(("exit 17", 'kill -TERM "$PPID"; sleep 1')):
            root = self.parent / f"case{i}"
            l = initialize_workspace(root, job_outputs=True, project_delivery=True)
            prepare_start(root, ["--hifi", PRIVATE])
            prepare_finish(root, 0)
            page = l.path("06_report/report.html")
            self.assertFalse(page.exists())
            self.assertNotIn(PRIVATE, l.path("report/inputs.json").read_text())
            text(root / "stage.sh", "#!/bin/bash\n" + script + "\n")
            runner = Runner(root, [PlanUnit("diagnostic", "stage.sh", "logs/run_all.log")], RUN)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(runner.run(), 0)
            self.assertIn("diagnostic", page.read_text())
            self.assertIn("01_lgz/report.html", page.read_text())
            manifest = json.loads(l.path("report/manifest.json").read_text())
            self.assertEqual(manifest["workspace_layout"]["schema"], "cgat.workspace.job-outputs.v2")
            self.assertIn(manifest["stage_timing_summary"]["units"][0]["status"], ("failed", "interrupted"))
            for mode in ("full", "light"):
                text(delivery_staging_path(root, mode) / "data", "x")
                facts = collect_unit(root, "package_" + mode, {})
                self.assertEqual(facts["summary"]["payload_file_count"], 1)
                self.assertEqual(facts["outputs"][0]["status"], "payload_staged")
                self.assertIsNone(facts["outputs"][0]["sha256"])
