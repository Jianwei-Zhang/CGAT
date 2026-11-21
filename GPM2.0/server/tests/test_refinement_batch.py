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
            with mock.patch.object(batch, "stage_refinement", side_effect=stage):
                result = batch.execute_batch(root, groups, 3, tools="degap,tgsgapcloser,quartet")
            self.assertEqual(calls, [("degap", 3), ("tgsgapcloser", 3), ("quartet", 3)])
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["batch"]["status"], "partial_failure")
            self.assertEqual(set(result["staged_results"]), {"tgsgapcloser", "quartet"})
            self.assertFalse((root / "05_final").exists())

    def test_baseline_mutation_invalidates_the_group_instead_of_mixing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, genome, _ = fixture.workspace(root)
            calls = []
            def stage(root, tool, groups, threads, *, run_id):
                calls.append(tool)
                genome.write_text(genome.read_text().replace("AAAA", "TTTT", 1))
                return self.result(root, tool, run_id)
            with mock.patch.object(batch, "stage_refinement", side_effect=stage):
                result = batch.execute_batch(root, groups, 2, tools="degap,tgsgapcloser")
            self.assertEqual(calls, ["degap"])
            self.assertEqual(result["batch"]["status"], "invalidated")
            self.assertFalse(result["staged_results"])

    @unittest.skipUnless(shutil.which("samtools"), "real indexing required for the cache boundary")
    def test_complete_result_reuses_content_and_tampered_report_is_not_a_hit(self):
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
            with mock.patch.object(native, "validate_runtime", return_value=runtime), mock.patch.object(cache, "validate_runtime", return_value=runtime), mock.patch.object(native.subprocess, "run", side_effect=command):
                first = batch.execute_batch(root, groups, 2, tools="tgsgapcloser")
                second = batch.execute_batch(root, groups, 8, tools="tgsgapcloser")
                self.assertEqual(first["exit_code"], 0)
                self.assertEqual(second["exit_code"], 0)
                self.assertEqual(len(calls), 1)
                result = second["staged_results"]["tgsgapcloser"]
                self.assertTrue(result["cache_hit"])
                self.assertEqual(result["provenance"]["execution"]["threads"], 2)
                record = Path(result["staging"]) / "provenance.json"
                value = json.loads(record.read_text())
                value["counts"]["closed"] = 999
                record.write_text(json.dumps(value))
                self.assertIsNone(cache.find_completed(root, "tgsgapcloser", groups))


if __name__ == "__main__":
    unittest.main()
