"""Native checkpoint recovery with real indexing/reconstruction, fake producers.

These are not real tool/environment acceptance tests. Fake producer calls emit
known pinned-protocol fixtures; the actual adapter, checkpoints and reports run.
"""
import hashlib
import json
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest
from unittest import mock

import test_refinement_native as fixture
import test_refinement_degap as degap_fixture
import refinement_native as native
import refinement_degap as degap
import refinement_batch as batch
import refinement_native_checkpoint as checkpoints
from refinement_tools import load_lock, fingerprint
from refinement_reports import build_tool_report, asset_plan
from workspace_layout import TOOL_DIRECTORIES


@unittest.skipUnless(shutil.which("samtools"), "real indexing required")
class NativeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.real_run = subprocess.run
        self.helper = fixture.NativeStageTests()
        self.helper.real_run = self.real_run
        self.runtime = {"lock_sha256": fingerprint(load_lock())}
        for patcher in (mock.patch.object(checkpoints, "launch", side_effect=lambda root, invocation, *args: (invocation.command, None)),
                        mock.patch.object(native, "validate_runtime", return_value=self.runtime),
                        mock.patch.object(degap, "validate_runtime", return_value=self.runtime),
                        mock.patch.object(native, "materialize_native_driver", return_value=None),
                        mock.patch.object(degap, "check_environment")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def producer(self, tool, calls):
        def run(command, **kwargs):
            if Path(command[0]).name != "samtools":
                calls.append(command)
            return self.helper.fake(tool, command, **kwargs)
        return run

    def degap_producer(self, calls, *, failed_child=False):
        def run(command, **kwargs):
            if Path(command[0]).name == "samtools":
                return self.real_run(command, **kwargs)
            calls.append(command)
            output = Path(command[command.index("--output") + 1])
            folder = output / "03.gap_filling"
            folder.mkdir(parents=True)
            candidate = output / "candidate.fa"
            candidate.write_text(">candidate\nAAAAGTCCCC\n")
            row = {"chromosome": "chr1", "gap_id": 1, "gap_start": 5, "gap_end": 24, "gap_len": 20,
                   "left_flank_len": 4, "right_flank_len": 4, "replace_start": 1, "replace_end": 28,
                   "replace_len": 28, "filled": True, "final_sequence_file": str(candidate)}
            (folder / "gap_filling_results.json").write_text(json.dumps({"gaps": [row]}))
            final = output / "04.genome_integration/genome.filled.fasta"
            final.parent.mkdir()
            final.write_text(">chr1\nAAAAGTCCCC\n")
            config = {"jobs": [{"job_name": "chr1.left", "job_dir": str(folder / "chr1.left"), "chromosome": "chr1", "gap_id": 1, "direction": "left"}]}
            (folder / "job_manager_config.json").write_text(json.dumps(config))
            result = {"total_jobs": 1, "completed": 0 if failed_child else 1, "failed": 1 if failed_child else 0,
                      "skipped": 0, "skipped_jobs": [], "completed_jobs": [] if failed_child else [{"job_name": "chr1.left", "status": "success", "exit_code": 0}],
                      "failed_jobs": [{"job_name": "chr1.left", "status": "error", "exit_code": 7}] if failed_child else []}
            (output / "autogapfiller_summary.json").write_text(json.dumps({"steps": {"step3": {"result": result}}}))
            return subprocess.CompletedProcess(command, 0)
        return run

    def test_killed_producer_without_substep_summary_keeps_original_failure_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            def run(command, **kwargs):
                if Path(command[0]).name == "samtools":
                    return self.real_run(command, **kwargs)
                return subprocess.CompletedProcess(command, -signal.SIGTERM)
            with mock.patch.object(checkpoints, "launch", side_effect=lambda root, invocation, *args: (invocation.command, True)), \
                 mock.patch.object(native.subprocess, "run", side_effect=run):
                result = batch.execute_batch(root, groups, 2, tools="quartet")
            record = result["batch"]["tools"]["quartet"]
            self.assertNotEqual(result["exit_code"], 0)
            self.assertEqual(record["phase"], "native")
            self.assertIn("terminated by signal SIGTERM (return code -15)", record["error"])
            self.assertNotIn("native_substeps.json", record["error"])
            report = Path(record["report"]["report"])
            self.assertIn("terminated by signal SIGTERM", report.read_text())
            self.assertTrue(any(asset.read_text() == "" for asset in (report.parent / "assets").glob("*.txt")))
            self.assertFalse((root / "05_final/03_quartet").exists())

    def test_three_native_producers_are_not_rerun_after_admission_failure(self):
        for tool in ("tgsgapcloser", "quartet", "lrgapcloser"):
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "workspace"
                groups, _, _ = fixture.workspace(root)
                calls = []
                with mock.patch.object(native.subprocess, "run", side_effect=self.producer(tool, calls)):
                    with mock.patch.object(native, "prepare_publication", side_effect=RuntimeError("injected admission interruption")):
                        with self.assertRaisesRegex(RuntimeError, "admission"):
                            native.stage_refinement(root, tool, groups, 2, run_id="1" * 32)
                    code = TOOL_DIRECTORIES[tool]
                    origin = root / "04_refinement" / code
                    receipt = origin / "02_jobs" / ("1" * 32) / "native_complete.json"
                    raw = receipt.read_bytes()
                    native_files = {path: path.read_bytes() for path in (origin / "03_native" / ("1" * 32)).rglob("*") if path.is_file()}
                    result = native.stage_refinement(root, tool, groups, 8, run_id="2" * 32)
                self.assertEqual(len(calls), 1)
                execution = result["provenance"]["execution"]
                self.assertTrue(execution["native_reused"])
                self.assertFalse(execution["native_executed"])
                self.assertEqual(execution["native_origin"]["run_id"], "1" * 32)
                self.assertEqual(execution["threads"], 2)
                self.assertEqual(execution["requested_threads"], 8)
                self.assertEqual(execution["timing"]["native_seconds"], 0)
                self.assertEqual((Path(result["staging"]) / "assembly.fa").read_text(), ">chr1\nAAAAGTCCCC\n")
                self.assertFalse((origin / "03_native" / ("2" * 32)).exists())
                self.assertEqual(receipt.read_bytes(), raw)
                self.assertTrue(all(path.read_bytes() == content for path, content in native_files.items()))
                report = build_tool_report(root, result)
                html = Path(report["report"]).read_text()
                self.assertIn('<span class="t-zh">复用原生证据</span><span class="t-en">Reused native evidence</span>', html)
                self.assertIn('<span class="t-zh">来源 Run</span><span class="t-en">Origin run</span></dt>'
                              f'<dd><code>{execution["native_origin"]["run_id"]}</code></dd>', html)
                summary = json.loads((Path(report["directory"]) / "summary.json").read_text())
                self.assertEqual(summary["execution"]["native_origin"]["run_id"], "1" * 32)
                assets = {Path(row["workspace_path"]).name: row for row in summary["artifacts"]}
                required = {"tgsgapcloser": ["tgs.name_map", "tgs.updated_scaff_infos"],
                            "quartet": ["quartet.genome.filled.detail"], "lrgapcloser": ["info_filter2"]}[tool]
                for name in required:
                    self.assertEqual(assets[name]["availability"], "embedded")
                    self.assertTrue((Path(report["directory"]) / assets[name]["report_path"]).is_file())

    def test_new_completion_verifier_revalidates_sealed_bytes_without_rerunning_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            calls = []
            with mock.patch.object(native.subprocess, "run", side_effect=self.producer("tgsgapcloser", calls)):
                native.stage_refinement(root, "tgsgapcloser", groups, 2, run_id="5" * 32)
                receipt = root / "04_refinement/02_tgsgapcloser/02_jobs" / ("5" * 32) / "native_complete.json"
                raw = receipt.read_bytes()
                revision = json.loads(raw)["validator_revision"]
                real_digest = checkpoints.digest
                def changed_verifier(path):
                    return "f" * 64 if Path(path) == Path(checkpoints.__file__) else real_digest(path)
                with mock.patch.object(checkpoints, "digest", side_effect=changed_verifier):
                    result = native.stage_refinement(root, "tgsgapcloser", groups, 4, run_id="6" * 32)
            self.assertEqual(len(calls), 1)
            origin = result["provenance"]["execution"]["native_origin"]
            self.assertEqual(origin["validator_revision"], revision)
            self.assertEqual(origin["verified_by"], fingerprint({
                "refinement_native_checkpoint.py": "f" * 64,
                "refinement_native_units.py": real_digest(Path(checkpoints.__file__).with_name("refinement_native_units.py")),
                "refinement_degap_units.py": real_digest(Path(checkpoints.__file__).with_name("refinement_degap_units.py")),
                "refinement_tgs_units.py": real_digest(Path(checkpoints.__file__).with_name("refinement_tgs_units.py")),
                "refinement_lr_units.py": real_digest(Path(checkpoints.__file__).with_name("refinement_lr_units.py"))}))
            self.assertEqual(receipt.read_bytes(), raw)

    def test_degap_reuses_completed_child_jobs_and_reconstructs_sources_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, before_fasta, before_path = degap_fixture.DegapRefinedPublicationTests().make_workspace(root)
            calls = []
            with mock.patch.object(degap.subprocess, "run", side_effect=self.degap_producer(calls)):
                with mock.patch.object(degap, "prepare_publication", side_effect=RuntimeError("after native completion")):
                    with self.assertRaises(RuntimeError):
                        degap.stage_degap(root, groups, 2, run_id="a" * 32)
                result = degap.stage_degap(root, groups, 6, run_id="b" * 32)
            self.assertEqual(len(calls), 1)
            self.assertTrue(result["provenance"]["execution"]["native_reused"])
            self.assertEqual(result["provenance"]["execution"]["native_origin"]["run_id"], "a" * 32)
            self.assertEqual(result["provenance"]["counts"]["closed"], 1)
            self.assertEqual((Path(result["staging"]) / "assembly.fa").read_text(), ">chr1\nAAAAGTCCCC\n")
            report = build_tool_report(root, result)
            summary = json.loads((Path(report["directory"]) / "summary.json").read_text())
            self.assertEqual(len(summary["native_jobs"]), 1)
            self.assertEqual(summary["native_jobs"][0]["job_name"], "chr1.left")
            self.assertTrue(summary["native_gaps_by_original"])

    def test_changed_native_bytes_reads_or_receipt_never_count_as_a_hit(self):
        for changed in ("native", "reads", "receipt", "runtime"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "workspace"
                groups, _, _ = fixture.workspace(root)
                calls = []
                with mock.patch.object(native.subprocess, "run", side_effect=self.producer("tgsgapcloser", calls)):
                    first = native.stage_refinement(root, "tgsgapcloser", groups, 2, run_id="3" * 32)
                    base = root / "04_refinement/02_tgsgapcloser"
                    if changed == "native":
                        (base / "03_native" / ("3" * 32) / "tgs.scaff_seqs").write_text(">chr1\nAAAAGACCCC\n")
                    elif changed == "reads":
                        Path(groups["hifi"][0]).write_text("@new\nAAAAGACCCC\n+\nIIIIIIIIII\n")
                    elif changed == "receipt":
                        receipt = base / "02_jobs" / ("3" * 32) / "native_complete.json"
                        value = json.loads(receipt.read_text())
                        value["execution"]["threads"] = 999
                        receipt.write_text(json.dumps(value))
                    else:
                        self.runtime["controlled_runtime_revision"] = "changed"
                    second = native.stage_refinement(root, "tgsgapcloser", groups, 4, run_id="4" * 32)
                self.assertEqual(len(calls), 2)
                self.assertFalse(second["provenance"]["execution"]["native_reused"])
                self.assertTrue((base / "03_native" / ("3" * 32)).is_dir())
                self.runtime.pop("controlled_runtime_revision", None)

    def test_degap_no_remaining_gaps_does_not_hash_or_execute_unused_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = degap_fixture.DegapRefinedPublicationTests().make_workspace(root)
            layout = native.WorkspaceLayout.detect(root)
            sequence = "AAAAGTCCCC"
            layout.path("data/datasets/original.fa").write_text(">original\n" + sequence + "\n")
            layout.path("grt/q/q3.fa").write_text(">chr1\n" + sequence + "\n")
            path = layout.path("metadata/grt_final_path.json")
            value = json.loads(path.read_text())
            row = value["chromosomes"][0]
            row.update(q4_length=10, q4_sha256=hashlib.sha256(sequence.encode()).hexdigest())
            row["segments"][0]["length"] = 10
            row["segments"][0]["source"]["end"] = 10
            path.write_text(json.dumps(value))
            raw_read = Path(groups["hifi"][0])
            original_digest = degap.digest
            def guard(file):
                if Path(file) == raw_read:
                    raise AssertionError("unused reads must not be hashed")
                return original_digest(file)
            calls = []
            with mock.patch.object(degap, "digest", side_effect=guard), mock.patch.object(degap.subprocess, "run", side_effect=self.degap_producer(calls)):
                result = degap.stage_degap(root, groups, 2)
            self.assertEqual(calls, [])
            execution = result["provenance"]["execution"]
            self.assertFalse(execution["native_executed"])
            self.assertTrue(execution["recipe"]["reads"][0]["not_consumed"])

    def test_zero_parent_with_failed_degap_child_does_not_create_native_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = degap_fixture.DegapRefinedPublicationTests().make_workspace(root)
            calls = []
            with mock.patch.object(degap.subprocess, "run", side_effect=self.degap_producer(calls, failed_child=True)):
                with self.assertRaisesRegex(ValueError, "child processes failed"):
                    degap.stage_degap(root, groups, 2, run_id="c" * 32)
            jobs = root / "04_refinement/01_degap/02_jobs" / ("c" * 32)
            self.assertFalse((jobs / "native_complete.json").exists())
            self.assertEqual(json.loads((jobs / "invocation.json").read_text())["status"], "failed")

    def test_batch_reports_admission_failure_and_recovers_without_new_native_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            calls = []
            with mock.patch.object(native.subprocess, "run", side_effect=self.producer("tgsgapcloser", calls)):
                with mock.patch.object(native, "prepare_publication", side_effect=RuntimeError("admission failed after native")):
                    failed = batch.execute_batch(root, groups, 2, tools="tgsgapcloser")
                row = failed["batch"]["tools"]["tgsgapcloser"]
                self.assertEqual(row["phase"], "admission")
                self.assertEqual(row["native_status"], "success")
                failure = json.loads((Path(row["report"]["directory"]) / "summary.json").read_text())
                self.assertFalse(failure["final_available"])
                self.assertEqual(failure["native_status"], "success")
                with mock.patch.object(batch, "build_source_evidence", return_value=None):
                    completed = batch.execute_batch(root, groups, 8, tools="tgsgapcloser")
            self.assertEqual(completed["exit_code"], 0, completed)
            self.assertEqual(len(calls), 1)
            row = completed["batch"]["tools"]["tgsgapcloser"]
            self.assertTrue(row["native_reused"])
            self.assertEqual(row["native_origin"]["run_id"], failed["batch"]["tools"]["tgsgapcloser"]["run_id"])


class NativeReportAssetPolicyTests(unittest.TestCase):
    def test_native_wire_records_embed_but_driver_source_and_sequences_stay_server_side(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"native_driver.sh": "#!/bin/bash\nexit 0\n", "quartet.genome.filled.detail": "native record\n",
                     "native.fa": ">chr1\nACGT\n"}
            for name, contents in files.items():
                (root / name).write_text(contents)
            assets = {row["workspace_path"]: row for row in asset_plan(root, {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files})}
            self.assertEqual(assets["native_driver.sh"]["availability"], "server_only_native_script")
            self.assertEqual(assets["native.fa"]["availability"], "server_only_sequence_or_binary")
            self.assertEqual(assets["quartet.genome.filled.detail"]["availability"], "embedded")
            self.assertNotIn("report_path", assets["native_driver.sh"])


if __name__ == "__main__":
    unittest.main()
