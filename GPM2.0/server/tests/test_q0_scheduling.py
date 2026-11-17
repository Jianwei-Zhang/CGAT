"""Early q0 evidence tasks and late annotation tasks must not share receipts."""
from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from server.tests import test_run_all_runner as runner_fixtures
from server.tests import test_run_outer_checkpoints as checkpoint_fixtures
from server.tools.run_outer_checkpoints import OuterCheckpointManager
from server.tools.run_orchestration import OrchestrationContractError
from server.tools.alignment_tasks import load_tasks
from server.tools import lgz_evidence_package

TOOLS = Path(__file__).resolve().parents[1] / "tools"
PAF = checkpoint_fixtures.PAF_LINE


class Q0SchedulingTests(unittest.TestCase):
    def make_pipeline(self, root, *, alignment_body=None):
        helper = runner_fixtures.RunAllRunnerTests()
        server = helper.make_workspace(root, [("q0_chr:Chr1", "exit 99"),
                                              ("q0_witness", "touch q0_started"),
                                              ("chr:Chr1", "exit 99")])
        environment = helper.configure_chromosome_inputs(server, root, ["Chr1"])
        run_dir = server / "runs/chr_Chr1"
        operation = run_dir / "ds_vs_self/command.sh"
        body = alignment_body if alignment_body is not None else (
            f"printf %s {shlex.quote(PAF)} > result.paf\n"
            f"echo alignment >> {shlex.quote(str(server / 'order'))}\n")
        operation.write_text("#!/bin/bash\nset -euo pipefail\n" + body)
        # The real prepare wrapper executes its raw operation in that operation's
        # working directory. Mirror it here for manual and no-task execution.
        (run_dir / "q0_generated_command.sh").write_text(
            f"#!/bin/bash\nset -euo pipefail\ncd {shlex.quote(str(operation.parent))}\nbash ./command.sh\n")
        (run_dir / "q0_command.sh").write_text(
            f"#!/bin/bash\nset -euo pipefail\ncd {shlex.quote(str(run_dir))}\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(TOOLS / 'run_outer_checkpoints.py'))} "
            f"--server-dir {shlex.quote(str(server))} --run-q0-chr Chr1\n")
        scan = run_dir / "tel_scan/command.sh"
        scan.parent.mkdir()
        scan.write_text("#!/bin/bash\nset -euo pipefail\n"
                        f"test -f {shlex.quote(str(server / 'q0_started'))}\n"
                        f"mkdir -p {shlex.quote(str(server / 'tel/chr_Chr1'))}\n"
                        f"printf 'header\n' > {shlex.quote(str(server / 'tel/chr_Chr1/ds.tsv'))}\n"
                        f"echo scan >> {shlex.quote(str(server / 'order'))}\n")
        (run_dir / "generated_command.sh").write_text(f"bash {shlex.quote(str(scan))}\n")
        (run_dir / "command.sh").write_text("exit 99\n")
        for name, commands in [("q0_alignment_tasks.json", [operation]), ("alignment_tasks.json", [scan])]:
            (run_dir / name).write_text(json.dumps({"version": 3, "tasks": [
                {"command": command.relative_to(server).as_posix(), "max_threads": 1,
                 "priority": 0} for command in commands]}))
        (server / "commands/q0_witness.sh").write_text(
            "#!/bin/bash\nset -euo pipefail\n"
            f"test -f {shlex.quote(str(operation.parent / 'result.paf'))}\n"
            f"touch {shlex.quote(str(server / 'q0_started'))}\n"
            f"echo q0 >> {shlex.quote(str(server / 'order'))}\n")
        (server / ".run_all/plan.tsv").write_text(
            "unit_id\tcommand_relpath\tdetail_log_relpath\n"
            "q0_chr:Chr1\truns/chr_Chr1/q0_command.sh\tlogs/run_all.log\n"
            "q0_witness\tcommands/q0_witness.sh\tlogs/run_all.log\n"
            "chr:Chr1\truns/chr_Chr1/command.sh\tlogs/run_all.log\n")
        return helper, server, environment

    def test_alignment_then_q0_then_scan_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            result = helper.run_runner(server, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((server / "order").read_text().splitlines(), ["alignment", "q0", "scan"])
            early = json.loads((server / "report/steps/001.json").read_text())
            late = json.loads((server / "report/steps/003.json").read_text())
            self.assertEqual(early["facts"]["summary"]["alignment_task_count"], 1)
            self.assertEqual(late["facts"]["summary"]["alignment_task_count"], 0)
            result = helper.run_runner(server, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[SKIP_VALID] [q0_chr:Chr1]", result.stdout)
            self.assertIn("[SKIP_VALID] [chr:Chr1]", result.stdout)
            self.assertEqual((server / "order").read_text().splitlines(), ["alignment", "q0", "scan", "q0"])

    def test_two_q0_chromosomes_run_within_budget_before_the_q0_barrier(self):
        helper = runner_fixtures.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ("Chr1", "Chr2")
            server = helper.make_workspace(root, [(f"q0_chr:{name}", "exit 99") for name in names]
                                            + [("q0_witness", "touch reached_q0")])
            environment = helper.configure_chromosome_inputs(server, root, list(names))
            options = server / "metadata/prepare_options.tsv"
            options.write_text(options.read_text().replace("threads\t12", "threads\t2"))
            worker = root / "worker.py"
            worker.write_text("import os, time\nfrom pathlib import Path\n"
                              f"root = Path({str(server)!r})\n"
                              "name = os.environ['GPM_REPORT_UNIT_ID'].split(':')[1]\n"
                              "assert os.environ['GPM_TASK_THREADS'] == '1'\n"
                              "(root / (name + '.ready')).touch()\n"
                              "deadline = time.monotonic() + 10\n"
                              "while not all((root / (n + '.ready')).exists() for n in ('Chr1', 'Chr2')):\n"
                              "    if time.monotonic() > deadline: raise RuntimeError('q0 tasks serialized')\n"
                              "    time.sleep(.01)\n"
                              f"Path('result.paf').write_text({PAF!r})\n")
            rows = ["unit_id\tcommand_relpath\tdetail_log_relpath"]
            for name in names:
                run_dir = server / f"runs/chr_{name}"
                leaf = run_dir / "ds_vs_self/command.sh"
                leaf.write_text(f"{shlex.quote(sys.executable)} {shlex.quote(str(worker))}\n")
                (run_dir / "q0_command.sh").write_text("exit 99\n")
                (run_dir / "q0_generated_command.sh").write_text("# generated q0 fixture\n")
                (run_dir / "q0_alignment_tasks.json").write_text(json.dumps({"version": 3, "tasks": [
                    {"command": leaf.relative_to(server).as_posix(), "max_threads": 1, "priority": 0}]}))
                rows.append(f"q0_chr:{name}\truns/chr_{name}/q0_command.sh\tlogs/run_all.log")
            witness = server / "commands/q0_witness.sh"
            witness.write_text("set -euo pipefail\n" + "".join(
                f"test -s {shlex.quote(str(server / f'runs/chr_{name}/ds_vs_self/result.paf'))}\n"
                for name in names) + f"touch {shlex.quote(str(server / 'reached_q0'))}\n")
            rows.append("q0_witness\tcommands/q0_witness.sh\tlogs/run_all.log")
            (server / ".run_all/plan.tsv").write_text("\n".join(rows) + "\n")
            result = helper.run_runner(server, env=environment, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("alignment_tasks=2 thread_budget=2", result.stdout)
            self.assertTrue((server / "reached_q0").is_file())

    def test_failed_or_malformed_alignment_never_reaches_q0(self):
        for body in ("exit 17\n", "printf 'malformed\n' > result.paf\n"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                helper, server, environment = self.make_pipeline(Path(directory), alignment_body=body)
                result = helper.run_runner(server, env=environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((server / "q0_started").exists())
                self.assertFalse((server / "tel/chr_Chr1/ds.tsv").exists())
                checkpoints = list((server / ".run_all/checkpoints").glob("*.json"))
                self.assertEqual(checkpoints, [])

    def test_completed_empty_alignment_is_a_valid_result(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory), alignment_body=": > result.paf\n")
            result = helper.run_runner(server, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((server / "q0_started").is_file())
            self.assertEqual((server / "runs/chr_Chr1/ds_vs_self/result.paf").read_bytes(), b"")

    def test_no_alignment_tasks_still_publish_a_successful_empty_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            run_dir = server / "runs/chr_Chr1"
            shutil.rmtree(run_dir / "ds_vs_self")
            (run_dir / "q0_alignment_tasks.json").write_text('{"version": 3, "tasks": []}')
            (run_dir / "q0_generated_command.sh").write_text("# no contig pair in this chr\n")
            (server / "commands/q0_witness.sh").write_text(
                f"touch {shlex.quote(str(server / 'q0_started'))}\n")
            result = helper.run_runner(server, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with mock.patch.dict(os.environ, environment):
                manager = OuterCheckpointManager(server)
                prepared = manager.prepare("q0_chr:Chr1", "runs/chr_Chr1/q0_command.sh")
                valid, reason = manager.validate(prepared)
                self.assertTrue(valid, reason)
                self.assertEqual(json.loads(prepared.path.read_text())["outputs"], [])

    def test_q0_manifest_is_required_and_not_replaced_with_scan_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            (server / "runs/chr_Chr1/q0_alignment_tasks.json").unlink()
            with self.assertRaisesRegex(ValueError, "required q0"):
                load_tasks(server, "q0_chr:Chr1", "runs/chr_Chr1/q0_command.sh")
            result = helper.run_runner(server, env=environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((server / "q0_started").exists())

    def test_late_scan_changes_do_not_invalidate_early_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            first = helper.run_runner(server, env=environment)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            scan = server / "runs/chr_Chr1/tel_scan/command.sh"
            scan.write_text(scan.read_text() + "# changed scan only\n")
            second = helper.run_runner(server, env=environment)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("[SKIP_VALID] [q0_chr:Chr1]", second.stdout)
            self.assertNotIn("[SKIP_VALID] [chr:Chr1]", second.stdout)
            self.assertEqual((server / "order").read_text().splitlines().count("alignment"), 1)
            self.assertEqual((server / "order").read_text().splitlines().count("scan"), 2)

    def test_corrupt_alignment_output_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            first = helper.run_runner(server, env=environment)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            (server / "runs/chr_Chr1/ds_vs_self/result.paf").write_text("corrupt\n")
            second = helper.run_runner(server, env=environment)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertNotIn("[SKIP_VALID] [q0_chr:Chr1]", second.stdout)
            self.assertEqual((server / "order").read_text().splitlines().count("alignment"), 2)

    def test_manual_q0_command_records_the_same_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory))
            result = subprocess.run(["bash", str(server / "runs/chr_Chr1/q0_command.sh")],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with mock.patch.dict(os.environ, environment):
                manager = OuterCheckpointManager(server)
                prepared = manager.prepare("q0_chr:Chr1", "runs/chr_Chr1/q0_command.sh")
                valid, reason = manager.validate(prepared)
                self.assertTrue(valid, reason)

    def test_manual_failure_does_not_publish_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            helper, server, environment = self.make_pipeline(Path(directory), alignment_body="exit 17\n")
            result = subprocess.run(["bash", str(server / "runs/chr_Chr1/q0_command.sh")],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 17)
            self.assertFalse((server / ".run_all/checkpoints").exists())

    def test_input_changes_during_execution_never_receive_a_success_receipt(self):
        for manual in (False, True):
            with self.subTest(manual=manual), tempfile.TemporaryDirectory() as directory:
                helper, server, environment = self.make_pipeline(Path(directory))
                operation = server / "runs/chr_Chr1/ds_vs_self/command.sh"
                operation.write_text(operation.read_text()
                                     + f"echo T >> {shlex.quote(str(server / 'runs/chr_Chr1/datasets/ds.fa'))}\n")
                if manual:
                    result = subprocess.run(["bash", str(server / "runs/chr_Chr1/q0_command.sh")],
                                            env=environment, capture_output=True, text=True)
                else:
                    result = helper.run_runner(server, env=environment)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("q0 alignment inputs changed during execution", result.stdout + result.stderr)
                self.assertFalse((server / "q0_started").exists())
                self.assertEqual(list((server / ".run_all/checkpoints").glob("*.json")), [])

    def test_display_evidence_uses_actual_pair_direction_not_ds_order(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse), tempfile.TemporaryDirectory() as directory:
                server = Path(directory)
                chr_dir = server / "runs/chr_Chr1"
                (chr_dir / "datasets").mkdir(parents=True)
                for name in ("a", "b"):
                    (chr_dir / f"datasets/{name}.fa").write_text(">ctg\nAAAAAAAAAA\n")
                run = chr_dir / ("b_vs_a" if reverse else "a_vs_b")
                run.mkdir()
                (run / "result.paf").write_text(PAF)
                card = {"dataset_name": "b", "contig_name": "ctg", "target_chr": "Chr1",
                        "source_card_key": "b:ctg:Chr1:normal", "orientation": "+"}
                with mock.patch.object(lgz_evidence_package, "alignment_profile",
                                       return_value=("minimap2", "fixture", "asm10")):
                    first = lgz_evidence_package.existing_display_evidence(
                        server, card, "A" * 10, [{"dataset_name": "b"}, {"dataset_name": "a"}])
                    second = lgz_evidence_package.existing_display_evidence(
                        server, card, "A" * 10, [{"dataset_name": "a"}, {"dataset_name": "b"}])
                self.assertEqual(first, second)
                self.assertEqual(len(first), 1)
                row = first[0]
                self.assertEqual(row["raw_artifact_relpath"], (run / "result.paf").relative_to(server).as_posix())
                self.assertEqual(json.loads(row["parameters_json"])["source_paf_role"], "target" if reverse else "query")
                self.assertTrue(row["query_artifact_relpath"].endswith("/a.fa" if reverse else "/b.fa"))

    def test_q0_checkpoint_does_not_require_future_scan_outputs(self):
        helper = checkpoint_fixtures.OuterCheckpointTests()
        with tempfile.TemporaryDirectory() as directory:
            server, fake_bin = helper.make_server(Path(directory))
            run_dir = server / "runs/chr_Chr1"
            for name in ("q0_command.sh", "q0_generated_command.sh"):
                (run_dir / name).write_text("# q0\n")
            (run_dir / "q0_alignment_tasks.json").write_text('{"version": 3, "tasks": []}')
            scan = run_dir / "tel_scan"
            scan.mkdir()
            (scan / "command.sh").write_text("# not run yet\n")
            with mock.patch.dict(os.environ, helper.path_environment(fake_bin)):
                manager = OuterCheckpointManager(server)
                prepared = manager.prepare("q0_chr:Chr1", "runs/chr_Chr1/q0_command.sh")
                manager.commit(prepared)
                valid, reason = manager.validate(prepared)
                self.assertTrue(valid, reason)
                (run_dir / "ds_vs_self/result.paf").unlink()
                with self.assertRaises(OrchestrationContractError):
                    manager.commit(prepared)


if __name__ == "__main__":
    unittest.main()
