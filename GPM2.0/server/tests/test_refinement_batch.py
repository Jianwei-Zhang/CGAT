"""Failure isolation and completed-content reuse, without real native aligners."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_batch as batch
import refinement_cache as cache
import refinement_native as native
from refinement_tools import fingerprint, load_lock
from server.tests import test_refinement_native as fixture


class RefinementBatchTests(unittest.TestCase):
    def setUp(self):
        # These fixtures simulate the producer, not subprocess resource collection.
        self.enterContext(mock.patch(
            "refinement_native_checkpoint._run_native",
            side_effect=lambda *args, **kwargs: (subprocess.run(*args, **kwargs).returncode, None),
        ))
        # This class isolates native/batch policy. Actual source measurement,
        # commands, receipts and serialization have their own focused tests.
        patch = mock.patch.object(batch, "build_source_evidence", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def result(self, root, tool, run_id):
        return {"tool": tool, "run_id": run_id, "staging": str(root / ".runtime" / tool / run_id / "final"),
                "provenance": {"execution": {"recipe": {"reads": []}}}}

    def test_failed_tool_does_not_prevent_other_selected_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            calls = []
            def stage(root, tool, groups, threads, *, run_id):
                calls.append((tool, threads))
                if tool == "degap":
                    raise RuntimeError("controlled native failure")
                return self.result(root, tool, run_id)
            with mock.patch.object(batch, "stage_refinement", side_effect=stage), mock.patch.object(batch, "build_tool_report", return_value={"fixture": "report"}), mock.patch.object(batch, "render_overview", return_value={"fixture": "overview"}):
                result = batch.execute_batch(root, groups, 3, tools="degap,tgsgapcloser,quartet")
            self.assertEqual(calls, [("degap", 3), ("tgsgapcloser", 3), ("quartet", 3)])
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["batch"]["status"], "partial_failure")
            self.assertEqual(set(result["staged_results"]), {"tgsgapcloser", "quartet"})
            self.assertFalse((root / "05_final").exists())

    def test_invalid_preset_does_not_stop_the_other_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            with (mock.patch.object(batch, "sync_workspace", side_effect=ValueError("invalid gapfill.toml")),
                  mock.patch.object(batch, "stage_refinement", side_effect=lambda root, tool, groups, threads, *, run_id: self.result(root, tool, run_id)) as stage,
                  mock.patch.object(batch, "build_tool_report", return_value={}),
                  mock.patch.object(batch, "build_failure_report", return_value={}),
                  mock.patch.object(batch, "render_overview", return_value={})):
                result = batch.execute_batch(root, groups, 2, tools="degap,tgsgapcloser")
            self.assertEqual(stage.call_count, 1)
            self.assertEqual(set(result["staged_results"]), {"tgsgapcloser"})
            self.assertIn("invalid gapfill.toml", result["batch"]["tools"]["degap"]["error"])

    def test_baseline_mutation_invalidates_the_group_instead_of_mixing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, genome, _ = fixture.workspace(root)
            calls = []
            def stage(root, tool, groups, threads, *, run_id):
                calls.append(tool)
                genome.write_text(genome.read_text().replace("AAAA", "TTTT", 1))
                return self.result(root, tool, run_id)
            with mock.patch.object(batch, "stage_refinement", side_effect=stage), mock.patch.object(batch, "build_tool_report", return_value={"fixture": "report"}), mock.patch.object(batch, "render_overview", return_value={"fixture": "overview"}):
                result = batch.execute_batch(root, groups, 2, tools="degap,tgsgapcloser")
            self.assertEqual(calls, ["degap"])
            self.assertEqual(result["batch"]["status"], "invalidated")
            self.assertFalse(result["staged_results"])

    def test_source_evidence_failure_keeps_native_result_and_isolates_other_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            def stage(root, tool, groups, threads, *, run_id):
                return self.result(root, tool, run_id)
            def measure(root, result, threads):
                if result["tool"] == "degap":
                    raise RuntimeError("controlled source measurement failure")
                return {"fixture": "completed measurements"}
            with mock.patch.object(batch, "stage_refinement", side_effect=stage), mock.patch.object(batch, "build_source_evidence", side_effect=measure), mock.patch.object(batch, "build_tool_report", return_value={"fixture": "report"}), mock.patch.object(batch, "render_overview", return_value={"fixture": "overview"}):
                result = batch.execute_batch(root, groups, 2, tools="degap,tgsgapcloser")
            self.assertEqual(result["batch"]["status"], "partial_failure")
            self.assertEqual(result["batch"]["tools"]["degap"]["phase"], "source_evidence")
            self.assertEqual(result["batch"]["tools"]["tgsgapcloser"]["status"], "staged")
            self.assertIn("degap", result["staged_results"])
            self.assertEqual(result["exit_code"], 1)

    @unittest.skipUnless(shutil.which("samtools"), "real indexing required for the cache boundary")
    def test_complete_reuse_requires_current_admission_and_untampered_report(self):
        helper = fixture.NativeStageTests("test_tgs_zero_exit_without_native_artifacts_is_failure")
        helper.real_run = subprocess.run
        runtime = {"lock_sha256": fingerprint(load_lock())}
        calls = []
        def command(argv, **kwargs):
            if Path(argv[0]).name != "samtools":
                calls.append(argv)
            return helper.fake("tgsgapcloser", argv, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = fixture.workspace(root)
            with mock.patch("refinement_native_checkpoint.launch", side_effect=lambda root, invocation, *args: (invocation.command, None)), mock.patch.object(native, "validate_runtime", return_value=runtime), mock.patch.object(cache, "validate_runtime", return_value=runtime), mock.patch.object(native.subprocess, "run", side_effect=command):
                first = batch.execute_batch(root, groups, 2, tools="tgsgapcloser")
                second = batch.execute_batch(root, groups, 8, tools="tgsgapcloser")
                self.assertEqual(first["exit_code"], 0)
                self.assertEqual(second["exit_code"], 0)
                self.assertEqual(len(calls), 1)
                result = second["staged_results"]["tgsgapcloser"]
                self.assertTrue(result["cache_hit"])
                self.assertEqual(result["provenance"]["execution"]["threads"], 2)
                # Changing only the admission code must invalidate a sealed Final
                # Path cache hit; the native producer has its own binding.
                real_digest = cache.digest
                adapter = Path(cache.__file__).with_name("refinement_native_trace.py")
                with mock.patch.object(cache, "digest", side_effect=lambda path: "f" * 64 if Path(path) == adapter else real_digest(path)):
                    self.assertIsNone(cache.find_completed(root, "tgsgapcloser", groups))
                self.assertIsNotNone(cache.find_completed(root, "tgsgapcloser", groups))
                record = Path(result["staging"]) / "provenance.json"
                value = json.loads(record.read_text())
                value["counts"]["closed"] = 999
                record.write_text(json.dumps(value))
                self.assertIsNone(cache.find_completed(root, "tgsgapcloser", groups))


if __name__ == "__main__":
    unittest.main()
