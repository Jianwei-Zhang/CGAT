import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import server_run
from server.tests import test_run_all_runner as runner_fixture
from grt_core.stage_alignment import build_candidates


class ServerRunTests(unittest.TestCase):
    def test_prepare_once_failure_resume_and_reference_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = runner_fixture.RunAllRunnerTests()
            template_root = root / "template"
            template = fixture.make_workspace(template_root, [
                ("ref:ds", "printf 'run\\n' >> run-count.txt\nmkdir -p runs/ds_vs_ref\n"
                 "printf 'query\\t10\\t0\\t10\\t+\\ttarget\\t12\\t1\\t11\\t10\\t10\\t60\\tcg:Z:10M\\n' > runs/ds_vs_ref/result.paf\n"
                 "printf 'fixture\\n' > runs/ds_vs_ref/tool_version.txt"),
                ("last", "exit 7"),
            ])
            env = fixture.configure_reference_inputs(template, template_root, ["ds"])
            (template / "run_all.sh").write_text("# prepared execution entry\n")
            output = root / "result"
            ref = root / "ref.fa"
            ref.write_text(">r\nACGT\n")
            argv = ["--ref", str(ref), "--ds", str(ref), "-o", str(output)]
            def prepare(_script, _args, target):
                self.assertTrue((target / ".run_all/lock").is_dir())
                shutil.copytree(template, target, dirs_exist_ok=True)
                return 0
            with patch.dict(os.environ, env), patch.object(server_run, "prepare_workspace", side_effect=prepare) as preparation, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(server_run.execute(argv, root), 7)
                self.assertFalse((output / ".run_all/lock").exists())
                original_metadata = (output / "metadata/prepare_options.tsv").read_bytes()
                (output / "commands/last.sh").write_text("exit 0\n")
                self.assertEqual(server_run.execute(argv, root), 0)
                self.assertEqual(preparation.call_count, 1)
                self.assertEqual((output / "run-count.txt").read_text(), "run\n")
                self.assertEqual((output / "metadata/prepare_options.tsv").read_bytes(), original_metadata)
                self.assertIn("[SKIP_VALID] [ref:ds]", (output / "logs/run_all.log").read_text())
                self.assertEqual(server_run.execute(["-o", str(output)], root), 0)
                ref.write_text(">r\nACGTACGT\n")
                with self.assertRaisesRegex(server_run.RunnerError, "Input changed"):
                    server_run.execute(argv, root)
                self.assertEqual(preparation.call_count, 1)
                lock = server_run.WorkspaceLock(output, "other-run")
                lock.acquire()
                try:
                    with self.assertRaisesRegex(server_run.RunnerError, "already running"):
                        server_run.execute(["-o", str(output)], root)
                finally:
                    lock.release()

    def test_refill_limit_updates_command_without_repreparing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / ".prepare_lib/tools/grt_step23.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_text('# supports --max-fill\n')
            script = root / "run_grt_step23.sh"
            script.write_text("#!/usr/bin/env bash\nset -euo pipefail\npython3 '/path with spaces/grt_step23.py' --server-dir '/workspace with spaces' --max-fill 1000000\n")
            server_run.update_fill_limit(root, "2000000")
            self.assertIn("--max-fill 2000000", script.read_text())
            self.assertIn("'/workspace with spaces'", script.read_text())
            before = script.stat().st_mtime_ns
            server_run.update_fill_limit(root, "2000000")
            self.assertEqual(script.stat().st_mtime_ns, before)

    def test_large_refill_limit_preserves_other_candidate_checks(self):
        gap = {"object_id": "gap", "chr": "chr06", "start0": 10000, "end0": 10100}
        left = {"object_id": "gap", "chr": "chr06", "side": "L", "target": "donor", "strand": "+",
                "block_length": 10000, "identity": .99, "line_number": 1, "qlen": 10000,
                "qstart": 0, "qend": 10000, "tstart": 0, "tend": 10000, "mapq": 60}
        right = {**left, "side": "R", "line_number": 2, "tstart": 1510000, "tend": 1520000}
        member = {"member_id": "member", "dataset_name": "assembly", "contig_name": "contig_40",
                  "orientation": "+", "source_start": "1", "source_end": "1520000"}
        args = ("step3", [left, right], [gap], {"donor": member}, {"donor": "A" * 1520000})
        candidates, rejected = build_candidates(*args)
        self.assertFalse(candidates)
        self.assertEqual(rejected[0]["reason"], "fill_length_gt_1000000")
        candidates, rejected = build_candidates(*args, max_fill_length=2000000)
        self.assertFalse(rejected)
        self.assertEqual(candidates[0]["fill_length"], 1500000)
        right["strand"] = "-"
        candidates, rejected = build_candidates(*args, max_fill_length=2000000)
        self.assertFalse(candidates)
        self.assertEqual(rejected[0]["reason"], "anchor_strands_disagree")

    def test_invalid_limit_and_unknown_resume_options_fail(self):
        for value in ["0", "-1", "1.5", "nope"]:
            with self.assertRaises(server_run.RunnerError):
                server_run.parse_options(["--max-fill", value], Path.cwd())
        with self.assertRaises(server_run.RunnerError):
            server_run.parse_options(["--unknown", "value"], Path.cwd())
