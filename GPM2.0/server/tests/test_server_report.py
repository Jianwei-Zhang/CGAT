from __future__ import annotations

import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT / "server/tools"
sys.path.insert(0, str(TOOLS))

from server_report import ReportSession, prepare_finish, prepare_start, record_grt_result
from server_report_collect import capture_final, final_summary, paf_summary
from server_report_io import SCHEMA, digest, fasta_stats, read_json, write_json
from render_server_report import render
import test_run_all_runner as runner_fixture


class ServerReportTests(unittest.TestCase):
    def test_fasta_gap_boundaries_n50_and_paf_union(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fasta = root / "input.fa"
            fasta.write_text(">a\nAA" + "N" * 60 + "\n" + "n" * 40 + "C\n>b\n" + "N" * 99 + "\n")
            value = fasta_stats(fasta)
            self.assertEqual((value["sequence_count"], value["length_bp"], value["n50_bp"]), (2, 202, 103))
            self.assertEqual((value["n_bp"], value["gap_count"], value["gap_bp"]), (199, 1, 100))
            paf = root / "x.paf"
            paf.write_text("a\t103\t0\t70\t+\tref\t200\t0\t70\t70\t70\t60\n"
                           "a\t103\t30\t100\t+\tref\t200\t30\t100\t70\t70\t60\n")
            self.assertEqual(paf_summary(paf)["queries"][0]["aligned_bp"], 100)
            self.assertFalse(paf_summary(root / "missing.paf")["available"])

    def test_failure_preserves_error_pending_stages_and_isolates_prior_results(self):
        helper = runner_fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = helper.make_workspace(root, [("first", "echo 'specific failure' >&2; exit 17"), ("last", "true")])
            (server / "metadata/grt_final_path.json").write_text('{"chromosomes":[{"chr":"STALE"}]}')
            result = helper.run_runner(server)
            self.assertEqual(result.returncode, 17, result.stderr)
            manifest = read_json(server / "report/manifest.json")
            self.assertEqual(manifest["status"], "failed")
            records = [read_json(server / "report" / path) for path in manifest["steps"]]
            self.assertEqual([r["status"] for r in records], ["failed", "pending"])
            self.assertIn("specific failure", records[0]["output_tail"])
            html = (server / "report/report.html").read_text()
            self.assertNotIn("STALE", html)
            self.assertFalse((root / "gpm_server.report.zip").exists())
            self.assertFalse((root / "gpm_server.report.html").exists())
            self.assertIn("No delivery package is declared final for this run.", result.stdout)

    def test_outer_cache_and_independent_regeneration(self):
        helper = runner_fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = helper.make_workspace(root, [("ref:ds", "mkdir -p runs/ds_vs_ref\n"
                "printf 'query\\t10\\t0\\t10\\t+\\ttarget\\t12\\t1\\t11\\t10\\t10\\t60\\tcg:Z:10M\\n' > runs/ds_vs_ref/result.paf\n"
                "echo fixture > runs/ds_vs_ref/tool_version.txt")])
            environment = helper.configure_reference_inputs(server, root, ["ds"])
            self.assertEqual(helper.run_runner(server, env=environment).returncode, 0)
            first_id = read_json(server / "report/manifest.json")["run_id"]
            again = helper.run_runner(server, env=environment)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(read_json(server / "report/steps/001.json")["execution"], "cache_reused")
            self.assertNotEqual(first_id, read_json(server / "report/manifest.json")["run_id"])
            self.assertTrue(list((server / ".report_history").glob(first_id + "*")))
            copied = root / "standalone"
            shutil.copytree(server / "report", copied)
            expected = (copied / "report.html").read_bytes()
            shutil.rmtree(server)
            (copied / "report.html").unlink()
            result = subprocess.run([sys.executable, "-I", str(copied / "render_report.py")],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(expected, (copied / "report.html").read_bytes())

    def test_renderer_escapes_input_and_rejects_mixed_run_and_external_paths(self):
        helper = runner_fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = helper.make_workspace(root, [("one", "true")])
            self.assertEqual(helper.run_runner(server).returncode, 0)
            report = server / "report"
            data = read_json(report / "inputs.json")
            attack = '</script><script>window.injected=1</script><img src="https://example.org/x">'
            data["sources"] = [{"name": attack}]
            write_json(report / "inputs.json", data)
            render(report)
            html = (report / "report.html").read_text()
            self.assertNotIn(attack, html)
            self.assertNotRegex(html, r'<(?:script|link|img)\b[^>]*(?:src|href)="https?://')
            embedded = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
            self.assertEqual(json.loads(embedded[1])["payload"]["inputs"]["sources"][0]["name"], attack)
            manifest = read_json(report / "manifest.json")
            record = read_json(report / manifest["steps"][0])
            record["run_id"] = "other"
            write_json(report / manifest["steps"][0], record)
            with self.assertRaisesRegex(ValueError, "mixed invocation"):
                render(report)
            manifest["steps"] = ["../metadata/report_inputs.json"]
            write_json(report / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "escapes"):
                render(report)

    def test_preparation_failure_invalidates_old_input_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "metadata/report_inputs.json", {"facts": {"old": True}})
            prepare_start(root, ["--ref", "ref", "missing.fa"])
            prepare_finish(root, 3)
            snapshot = read_json(root / "metadata/report_inputs.json")
            self.assertEqual(snapshot["status"], "failed")
            self.assertEqual(snapshot["facts"], {})
            self.assertEqual(read_json(root / "report/manifest.json")["status"], "failed")

    def test_delivery_archives_embed_final_portable_report(self):
        helper = runner_fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = helper.make_workspace(root, [("package_full", "true"), ("package_light", "true")])
            (root / "gpm_server.report.zip").write_text("legacy report ZIP", encoding="utf-8")
            (root / "gpm_server.report.html").write_text("legacy report HTML", encoding="utf-8")
            shutil.copytree(PROJECT / "tests/fixtures/grt_contract_v2/valid/gpm_server", server, dirs_exist_ok=True)
            shutil.copytree(TOOLS, server / ".prepare_lib/tools", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(PROJECT / "server/contracts", server / ".prepare_lib/contracts")
            for unit, name in [("package_full", "package_full_zip.sh"), ("package_light", "package_light_zip.sh")]:
                shutil.copyfile(PROJECT / "server/templates" / name, server / name)
                (server / "commands" / (unit + ".sh")).write_text("#!/bin/bash\nexec bash " + shlex.quote(str(server / name)) + "\n")
            result = helper.run_runner(server)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for filename in ("001.json", "002.json"):
                record = read_json(server / "report/steps" / filename)
                artifact = record["facts"]["outputs"][0]
                path = root / artifact["file"]
                self.assertNotEqual(artifact["payload_archive_sha256"], digest(path))
                self.assertLess(artifact["payload_archive_size_bytes"], path.stat().st_size)
                self.assertIn("before the finalized report", artifact["checksum_scope"])
                with zipfile.ZipFile(path) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn("gpm_server/report/manifest.json", archive.namelist())
                    self.assertIn("gpm_server/report/report.html", archive.namelist())
                    self.assertIn("gpm_server/report/render_report.py", archive.namelist())
            self.assertFalse((root / "gpm_server.report.zip").exists())
            self.assertFalse((root / "gpm_server.report.html").exists())
            self.assertIn("Final delivery packages:", result.stdout)
            self.assertIn("Full package (FASTA + report)", result.stdout)
            self.assertIn("Light package (report included, FASTA omitted)", result.stdout)
            self.assertIn("Light 轻量包交付", (server / "report/report.html").read_text())
            self.assertIn("SHA-256:", result.stdout)
            self.assertIn("Final delivery packages:", (server / "logs/run_all.log").read_text())
            repeated = helper.run_runner(server)
            self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
            for path in (root / "gpm_server.zip", root / "gpm_server.light.zip"):
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(archive.namelist().count("gpm_server/report/manifest.json"), 1)
            standalone = root / "unpacked"
            with zipfile.ZipFile(root / "gpm_server.zip") as archive:
                archive.extractall(standalone)
            shutil.rmtree(server)
            embedded_report = standalone / "gpm_server/report"
            (embedded_report / "report.html").unlink()
            result = subprocess.run([sys.executable, "-I", str(embedded_report / "render_report.py")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((embedded_report / "report.html").is_file())

    def test_process_event_is_immutable_and_final_state_is_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ReportSession(root, [], "run-test")
            result = {"stage": "step2", "q_input_version": "q1", "q_output_version": "q2",
                      "events": [{"event_id": "e1", "stage": "step2", "chr": "Chr1",
                                  "status": "accepted", "action": "fill", "reason": "supported"}]}
            with patch.dict(os.environ, {"GPM_REPORT_RUN_ID": "run-test", "GPM_REPORT_UNIT_ID": "grt_step23"}):
                record_grt_result(root, result)
                changed = copy.deepcopy(result)
                changed["events"][0].update(status="superseded", reason="replaced_later")
                record_grt_result(root, changed)
            write_json(root / "report/final_snapshot.json", {"schema_version": SCHEMA, "run_id": "run-test",
                                                             "available": True, "events": changed["events"]})
            summary = final_summary(root, session.report)
            row = summary["event_reconciliation"][0]
            self.assertEqual((row["process_status"], row["final_status"]), ("accepted", "superseded"))

    def test_result_first_summary_and_final_path_annotations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "metadata/grt_final_path.json", {
                "chromosomes": [{"chr": "Chr1", "q4_length": 1000, "segments": [{
                    "segment_id": "s1", "kind": "source", "length": 1000,
                    "source": {"dataset": "primary", "contig": "ctg1", "start": 1,
                               "end": 1000, "orientation": "+"},
                }]}],
            })
            (root / "metadata/grt_q_segments.tsv").write_text(
                "q_version\tsegment_kind\tdataset_name\tq_start\tq_end\n", encoding="utf-8")
            (root / "grt/q").mkdir(parents=True)
            (root / "grt/q/q0.fa").write_text(">Chr1\n" + "A" * 450 + "N" * 100 + "C" * 450 + "\n")
            (root / "grt/q/q4.fa").write_text(">Chr1\n" + "A" * 1000 + "\n")
            (root / "tel").mkdir()
            (root / "tel/rules.tsv").write_text(
                "rule_id\tmotif\tmin_repeat\treverse_complement\nrule-1\tTTAGGG\t5\ttrue\n")
            (root / "cen/chr_Chr1").mkdir(parents=True)
            (root / "cen/reference.tsv").write_text("chr_name\nChr1\n")
            (root / "cen/chr_Chr1/marks.tsv").write_text(
                "cen_id\tchr_name\tquery_name\tdataset_name\tctg_name\tctg_start\tctg_end\tstrand\talign_length\tidentity\tmapq\n"
                "cen\tChr1\tChr1_centromere\tprimary\tctg1\t400\t600\t+\t201\t99.5\t60\n")
            write_json(root / "grt/evidence/step4_telomere/result.json", {
                "terminal_rows": [
                    {"chr": "Chr1", "terminal": "5prime", "final_status": "already_present"},
                    {"chr": "Chr1", "terminal": "3prime", "final_status": "recovered"},
                ],
            })

            captured = capture_final(root)
            self.assertTrue(captured["annotations"]["telomere"]["configured"])
            marker = captured["annotations"]["centromere"]["markers"][0]
            self.assertEqual((marker["q4_start"], marker["q4_end"]), (400, 600))

            report = root / "report"
            write_json(report / "manifest.json", {
                "schema_version": SCHEMA, "run_id": "run-summary", "workspace_name": "sample",
                "status": "success", "started_at": "start", "ended_at": "end", "steps": [], "errors": [],
            })
            write_json(report / "inputs.json", {
                "schema_version": SCHEMA, "run_id": "run-summary", "status": "success",
                "facts": {"datasets": [], "parameters": {}},
            })
            write_json(report / "final_snapshot.json", {
                "schema_version": SCHEMA, "run_id": "run-summary", **captured,
            })
            summary = final_summary(root, report)
            write_json(report / "final_summary.json", summary)
            self.assertEqual(summary["outcome_summary"]["closed_gap_count"], 1)
            self.assertEqual(summary["outcome_summary"]["remaining_gap_count"], 0)
            self.assertEqual(summary["outcome_summary"]["t2t_status"], "achieved")

            with_unresolved_n = copy.deepcopy(captured)
            with_unresolved_n["sequence_versions"]["q4"]["n_bp"] = 1
            write_json(report / "final_snapshot.json", {
                "schema_version": SCHEMA, "run_id": "run-summary", **with_unresolved_n,
            })
            self.assertEqual(final_summary(root, report)["outcome_summary"]["t2t_status"], "not_achieved")
            write_json(report / "final_summary.json", summary)

            render(report)
            html = (report / "report.html").read_text()
            self.assertLess(html.index('id="summary"'), html.index('id="results"'))
            self.assertLess(html.index('id="results"'), html.index('id="workflow"'))
            self.assertIn("关闭 Gap", html)
            self.assertIn("已达到", html)
            self.assertIn('path-marker telomere left complete', html)
            self.assertIn('path-marker centromere', html)


def make_grt_report_fixture(root: Path) -> tuple[Path, dict]:
    """Actual GRT implementations with deterministic external-tool fixtures."""
    from server.tests.test_grt_step23 import GrtStep23Tests
    from server.tests.test_grt_telomere_finalize import GrtTelomereFinalizeTests
    from server.tests.test_grt_evidence_package import GrtEvidencePackageTests

    tel = GrtTelomereFinalizeTests()
    step = GrtStep23Tests()
    evidence = GrtEvidencePackageTests()
    server = tel.make_server(root)
    step_tools, tel_tools = step.make_tools(root), tel.make_tools(root)
    evidence.write_existing_main_view_results(server)
    minimap = evidence.make_minimap(root)
    runtime = server / ".prepare_lib/tools"
    shutil.copytree(TOOLS, runtime, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PROJECT / "server/contracts", server / ".prepare_lib/contracts")
    environment = os.environ.copy()
    for key in ("FAKE_GRT_MINIMAP_LOG", "FAKE_GRT_MUMMER_LOG", "FAKE_TEL_MUMMER_LOG",
                "FAKE_TEL_MINIMAP_LOG", "FAKE_DISPLAY_MINIMAP_LOG"):
        environment[key] = str(root / (key + ".log"))
    commands = []
    for unit, tool, external in [
        ("grt_prepare", "grt_prepare_inputs.py", {}),
        ("grt_step1", "grt_step1.py", {"minimap2": step_tools["minimap2"]}),
        ("grt_step23", "grt_step23.py", step_tools),
        ("grt_telomere_finalize", "grt_telomere_finalize.py", tel_tools),
        ("finalize_evidence", "grt_evidence_package.py", {"minimap2": minimap}),
    ]:
        argv = [sys.executable, str(runtime / tool), "--server-dir", str(server)]
        if unit != "grt_prepare":
            argv.extend(["--threads", "2"])
        for flag in ("minimap2", "nucmer", "delta_filter", "show_coords"):
            if flag in external:
                argv.extend(["--" + flag.replace("_", "-"), str(external[flag])])
        path = server / f"{unit}.sh"
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + shlex.join(argv) + "\n")
        commands.append((unit, path.name))
    (server / ".run_all").mkdir(exist_ok=True)
    (server / ".run_all/plan.tsv").write_text("unit_id\tcommand_relpath\tdetail_log_relpath\n" + "".join(
        f"{unit}\t{path}\tlogs/run_all.log\n" for unit, path in commands))
    return server, environment


class GrtReportIntegrationTests(unittest.TestCase):
    def test_actual_grt_publication_cache_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server, environment = make_grt_report_fixture(root)
            helper = runner_fixture.RunAllRunnerTests()
            result = helper.run_runner(server, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = server / "report"
            stage_files = list((report / "steps").glob("grt-*.json"))
            self.assertEqual(len(stage_files), 6)
            stage1 = read_json(report / "steps/grt-step1_round1.json")
            self.assertEqual(stage1["facts"]["parameters"]["execution_mode"], "upstream_external_contigs_stage1_identity")
            self.assertEqual(stage1["facts"]["result"]["q_input_sha256"], stage1["facts"]["result"]["q_output_sha256"])
            final = read_json(report / "final_summary.json")
            self.assertTrue(final["available"])
            actual = fasta_stats(server / "grt/q/q4.fa")
            self.assertEqual(final["sequence_versions"]["q4"], actual)
            self.assertIn("q4", final["explicit_connector_segments"])
            self.assertIn("primary", final["source_contribution_bp"])
            self.assertTrue(any(row["final_path_segment_ids"] for row in final["event_reconciliation"]))
            html = (report / "report.html").read_text()
            self.assertIn('id="workflow"', html)
            self.assertIn('class="pipeline-map"', html)
            self.assertIn('class="io-flow"', html)
            self.assertIn('id="grt-flow"', html)
            self.assertIn('id="grt-final-path"', html)
            self.assertIn('class="path-segment', html)
            self.assertLess(html.index('id="grt-step1_round1"'), html.index('id="grt-step1_filter"'))
            self.assertLess(html.index('id="grt-step1_filter"'), html.index('id="grt-step1_round2"'))
            self.assertFalse((root / f"{server.name}.report.zip").exists())
            self.assertFalse((root / f"{server.name}.report.html").exists())
            second = helper.run_runner(server, env=environment)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            records = [read_json(path) for path in (report / "steps").glob("[0-9]*.json")]
            self.assertTrue(any(row["execution"] == "cache_reused" for row in records))
            self.assertEqual(read_json(report / "steps/grt-step1_round1.json")["execution"], "cache_reused")
            (server / "grt_step23.sh").write_text("#!/bin/bash\necho deliberate-failure >&2\nexit 19\n")
            failed = helper.run_runner(server, env=environment)
            self.assertEqual(failed.returncode, 19, failed.stdout + failed.stderr)
            self.assertTrue((server / "grt/q/q4.fa").is_file())
            self.assertFalse(read_json(report / "final_summary.json").get("available", False))
            self.assertEqual(len(list((report / "steps").glob("grt-*.json"))), 3)


if __name__ == "__main__":
    unittest.main()
