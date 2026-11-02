"""Resource-only resume: preserve prepared/cache identity and use effective budgets."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import run_resources as resources
import server_run
from server.tests import test_run_all_runner as fixtures
from server.tools.lgz_core import stage_cache, repair_mummer
from delivery_archive import archive_options


class ResourceResumeTests(unittest.TestCase):
    def workspace(self, root):
        workspace = fixtures.RunAllRunnerTests().make_workspace(root, [
            ("only", 'printf "%s %s\\n" "$GPM_RUN_THREADS" "$GPM_RUN_QC_MEMORY_GB" > budgets.txt'),
        ])
        (workspace / "run_all.sh").write_text("# prepared\n")
        return workspace

    def test_only_resource_options_and_existing_refill_exception_are_mutable(self):
        for key in resources.RESOURCE_OPTIONS:
            server_run.check_resume_options({key: [["64"]]}, {key: [["10"]]}, {})
        for key in ("--archive-format", "--score", "--grt-kmer-size", "--reads-qc",
                    "--grt-execution-profile", "--grt-step3-mummer-scope", "--skip-self"):
            with self.subTest(key=key), self.assertRaisesRegex(server_run.RunnerError, "differs"):
                server_run.check_resume_options({key: [["changed"]]}, {}, {})
        for key in ("-t", "--threads", "--lgz-qc-memory-gb", "--grt-qc-memory-gb"):
            for invalid in ("0", "-1", "1.5", "nope"):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(server_run.RunnerError):
                    server_run.parse_options([key, invalid], Path.cwd())

    def test_legacy_prepared_workspace_persists_budget_without_rewriting_prepare_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = self.workspace(root)
            before = {p: p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
            args = ["-o", str(workspace), "-t", "64", "--lgz-qc-memory-gb", "120"]
            with patch.object(resources.os, "sched_getaffinity", return_value=set(range(64))), redirect_stdout(io.StringIO()):
                self.assertEqual(server_run.execute(args, root), 0)
                self.assertEqual((workspace / "budgets.txt").read_text(), "64 120\n")
                self.assertEqual(server_run.execute(["-o", str(workspace)], root), 0)
                self.assertEqual((workspace / "budgets.txt").read_text(), "64 120\n")
                self.assertEqual(server_run.execute(args, root), 0)
            for path, payload in before.items():
                self.assertEqual(path.read_bytes(), payload, str(path))
            state = resources.read_resources(workspace)
            self.assertEqual(state["effective"], {"threads": 64, "qc_memory_gb": 120})
            self.assertEqual(len(state["history"]), 1)
            report = json.loads((workspace / "report/manifest.json").read_text())
            self.assertEqual(report["execution_resources"], state)
            self.assertEqual(state["history"][0]["changes"]["threads"], {"from": 12, "to": 64})
            self.assertIn('"threads": 64', (workspace / "logs/run_all.log").read_text())
            direct = fixtures.RunAllRunnerTests().run_runner(workspace)
            self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
            self.assertEqual((workspace / "budgets.txt").read_text().split()[1], "120")

    def test_busy_workspace_cannot_change_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = self.workspace(root)
            lock = server_run.WorkspaceLock(workspace, "active-job")
            lock.acquire()
            try:
                with self.assertRaisesRegex(server_run.RunnerError, "already running"):
                    server_run.execute(["-o", str(workspace), "-t", "64"], root)
                self.assertFalse((workspace / ".run_all/resources.json").exists())
            finally:
                lock.release()

    def test_old_runtime_or_legacy_combined_stage_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            runtime = workspace / ".prepare_lib/tools"
            runtime.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "predates resource-only resume"):
                resources.update_resources(workspace, {"--threads": [["64"]]}, "old-runtime")
            self.assertFalse((workspace / ".run_all/resources.json").exists())
            (runtime / "run_resources.py").write_text("# staged helper\n")
            plan = workspace / ".run_all/plan.tsv"
            plan.write_text(plan.read_text().replace("only", "grt_step23"))
            with self.assertRaisesRegex(ValueError, "legacy combined"):
                resources.update_resources(workspace, {"--threads": [["64"]]}, "combined")
            self.assertFalse((workspace / ".run_all/resources.json").exists())

    def test_invalid_receipt_fails_closed_and_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = self.workspace(root)
            path = workspace / ".run_all/resources.json"
            for budget in (0, -1, True, "64", 1.5):
                path.write_text(json.dumps({"schema_version": 1, "effective": {"threads": budget}, "history": []}))
                with self.subTest(budget=budget), self.assertRaises(ValueError):
                    resources.read_resources(workspace)
            path.unlink()
            target = root / "external.json"
            target.write_text('{}')
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "regular file"):
                resources.read_resources(workspace)
            self.assertEqual(target.read_text(), '{}')

    def test_execution_boundary_clamps_cpu_and_preserves_raw_parameters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paf = root / "result.paf"
            paf.touch()
            with patch.dict(os.environ, {"GPM_RUN_THREADS": "64", "GPM_RUN_QC_MEMORY_GB": "120"}), patch.object(
                resources.os, "sched_getaffinity", return_value=set(range(32))
            ), patch.object(stage_cache.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                parameters = {"threads": 10, "preset": "asm10"}
                stage_cache.run_minimap("minimap2", parameters["threads"], root / "target.fa", root / "query.fa", paf, root)
                command = run.call_args.args[0]
                self.assertEqual(command[command.index("-t") + 1], "32")
                self.assertEqual(parameters["threads"], 10)
                self.assertEqual(resources.execution_qc_memory(80), 120)
                self.assertEqual(repair_mummer.mummer_partition_workers(10, [1000] * 80, 100,
                                 available_memory=1024**4), 32)
                self.assertEqual(repair_mummer.lgz_mummer_parameters(10)["nucmer"]["threads"], 1)
            with patch.dict(os.environ, {"GPM_RUN_THREADS": "2"}):
                self.assertEqual(resources.execution_threads(10), 2)

    def test_compression_uses_persisted_budget_without_changing_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            before = (workspace / "metadata/prepare_options.tsv").read_bytes()
            with redirect_stdout(io.StringIO()):
                resources.update_resources(workspace, {"--threads": [["64"]]}, "compress")
            with patch.object(resources.os, "sched_getaffinity", return_value=set(range(32))):
                self.assertEqual(archive_options(workspace), ("zip", 32))
            self.assertEqual((workspace / "metadata/prepare_options.tsv").read_bytes(), before)

    def test_internal_environment_does_not_override_persisted_contract(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GPM_RUN_THREADS": "999"}):
            self.assertNotIn("GPM_RUN_THREADS", resources.resource_environment(Path(temporary)))
