#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "tools/run_all_runner.py"


def read_status(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class RunAllRunnerTests(unittest.TestCase):
    def make_workspace(
        self,
        root: Path,
        scripts: list[tuple[str, str]],
    ) -> Path:
        server = root / "gpm_server"
        (server / ".run_all").mkdir(parents=True)
        (server / "metadata").mkdir()
        (server / "metadata/prepare_options.tsv").write_text(
            "key\tvalue\nthreads\t12\n", encoding="utf-8"
        )
        rows = ["unit_id\tcommand_relpath\tdetail_log_relpath"]
        for unit_id, body in scripts:
            command_relpath = f"commands/{unit_id}.sh"
            command = server / command_relpath
            command.parent.mkdir(parents=True, exist_ok=True)
            command.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n",
                encoding="utf-8",
            )
            rows.append(f"{unit_id}\t{command_relpath}\tlogs/run_all.log")
        (server / ".run_all/plan.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        return server

    def run_runner(self, server: Path, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(RUNNER), "--server-dir", str(server)],
            text=True,
            capture_output=True,
            check=False,
            **kwargs,
        )

    def test_success_streams_output_and_writes_atomic_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            order = root / "order.txt"
            server = self.make_workspace(
                root,
                [
                    ("first", f"echo first-child; echo first >> {order}"),
                    ("second", f"echo second-child >&2; echo second >> {order}"),
                ],
            )
            result = self.run_runner(server)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(order.read_text(encoding="utf-8"), "first\nsecond\n")
            log = (server / "logs/run_all.log").read_text(encoding="utf-8")
            self.assertIn(" FRESH ", log)
            self.assertIn("[START] [first]", log)
            self.assertIn("[CHILD] [first] first-child", log)
            self.assertIn("[CHILD] [second] second-child", log)
            self.assertIn("[SUCCESS] [run_all] pipeline completed", log)
            rows = read_status(server / "logs/status.tsv")
            self.assertEqual([row["state"] for row in rows], ["success", "success"])
            self.assertEqual([row["attempt"] for row in rows], ["1", "1"])
            self.assertFalse(any((server / "logs").glob(".status.tsv.tmp.*")))
            self.assertFalse((server / ".run_all/lock").exists())

            repeat = self.run_runner(server)
            self.assertEqual(repeat.returncode, 0, repeat.stderr)
            repeat_log = (server / "logs/run_all.log").read_text(encoding="utf-8")
            self.assertIn("[RESUME] [run_all] rechecking the prepared execution plan", repeat_log)

    def test_outer_checkpoint_skips_valid_ref_and_reruns_corrupt_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = self.make_workspace(
                root,
                [
                    (
                        "ref:ds",
                        "printf 'run\\n' >> run-count.txt\n"
                        "mkdir -p runs/ds_vs_ref\n"
                        "printf 'query\\t10\\t0\\t10\\t+\\ttarget\\t12\\t1\\t11\\t10\\t10\\t60\\n' "
                        "> runs/ds_vs_ref/result.paf\n"
                        "printf 'fixture\\n' > runs/ds_vs_ref/tool_version.txt",
                    )
                ],
            )
            (server / "metadata/prepare_options.tsv").write_text(
                "key\tvalue\nalignment_engine\tminimap2\nthreads\t12\nminimap_preset\tasm10\n",
                encoding="utf-8",
            )
            (server / "metadata/reference.tsv").write_text(
                "reference_name\tfasta_relpath\tfai_relpath\n"
                "ref\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
                encoding="utf-8",
            )
            (server / "metadata/datasets.tsv").write_text(
                "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n"
                "ds\tds\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\ttrue\n",
                encoding="utf-8",
            )
            for relpath, content in [
                ("data/reference/ref.fa", ">target\nAAAAAAAAAAAA\n"),
                ("data/reference/ref.fa.fai", "target\t12\t8\t12\t13\n"),
                ("data/datasets/ds.fa", ">query\nAAAAAAAAAA\n"),
                ("data/datasets/ds.fa.fai", "query\t10\t7\t10\t11\n"),
            ]:
                path = server / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            minimap2 = fake_bin / "minimap2"
            minimap2.write_text("#!/usr/bin/env bash\necho fixture\n", encoding="utf-8")
            minimap2.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

            first = self.run_runner(server, env=environment)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual((server / "run-count.txt").read_text(encoding="utf-8"), "run\n")
            self.assertEqual(len(list((server / ".run_all/checkpoints").glob("*.json"))), 1)

            second = self.run_runner(server, env=environment)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("[SKIP_VALID] [ref:ds]", second.stdout)
            self.assertEqual((server / "run-count.txt").read_text(encoding="utf-8"), "run\n")
            self.assertEqual(read_status(server / "logs/status.tsv")[0]["attempt"], "1")

            (server / "runs/ds_vs_ref/result.paf").write_text(
                "malformed\n", encoding="utf-8"
            )
            third = self.run_runner(server, env=environment)
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertIn("[STALE] [ref:ds]", third.stdout)
            self.assertEqual(
                (server / "run-count.txt").read_text(encoding="utf-8"), "run\nrun\n"
            )
            self.assertEqual(read_status(server / "logs/status.tsv")[0]["attempt"], "2")

    def test_failure_stops_downstream_and_is_actionable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "should-not-exist"
            server = self.make_workspace(
                root,
                [
                    ("first", "echo first"),
                    ("broken", "echo broken-output; exit 17"),
                    ("last", f"touch {marker}"),
                ],
            )
            result = self.run_runner(server)
            self.assertEqual(result.returncode, 17)
            self.assertFalse(marker.exists())
            rows = read_status(server / "logs/status.tsv")
            self.assertEqual([row["state"] for row in rows], ["success", "failed", "pending"])
            self.assertEqual(rows[1]["exit_code"], "17")
            log = (server / "logs/run_all.log").read_text(encoding="utf-8")
            self.assertIn("[FAILED] [broken] exit_code=17", log)
            self.assertIn("detail=logs/run_all.log", log)
            self.assertIn("rerun='bash", log)

    def test_grt_cache_hit_requires_valid_authoritative_checkpoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = self.make_workspace(
                root,
                [
                    (
                        "grt_step1",
                        "echo 'GRT step1_round1 cache hit: fixture'\n"
                        "echo 'GRT step1_filter cache hit: fixture'\n"
                        "echo 'GRT step1_round2 cache hit: fixture'",
                    )
                ],
            )
            fields = [
                "stage",
                "q_input_version",
                "q_input_sha256",
                "q_output_version",
                "q_output_sha256",
                "donor_set_id",
                "status",
                "checkpoint_relpath",
                "checkpoint_sha256",
            ]
            rows = []
            for stage in ("step1_round1", "step1_filter", "step1_round2"):
                output_relpath = f"grt/evidence/{stage}/result.txt"
                output = server / output_relpath
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(f"{stage}\n", encoding="utf-8")
                checkpoint_relpath = f"grt/checkpoints/{stage}.json"
                checkpoint = server / checkpoint_relpath
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(
                    json.dumps(
                        {
                            "workflow": "gpm_grt_precomputed_v2",
                            "stage": stage,
                            "status": "success",
                            "input_fingerprint": f"input-{stage}",
                            "output_hashes": {
                                output_relpath: hashlib.sha256(output.read_bytes()).hexdigest()
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                rows.append(
                    {
                        "stage": stage,
                        "q_input_version": "q0",
                        "q_input_sha256": "a" * 64,
                        "q_output_version": "q1",
                        "q_output_sha256": "b" * 64,
                        "donor_set_id": "donor",
                        "status": "success",
                        "checkpoint_relpath": checkpoint_relpath,
                        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                    }
                )
            with (server / "metadata/grt_stage_status.tsv").open(
                "w", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)

            result = self.run_runner(server)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[CACHE_HIT] [grt_step1]", result.stdout)

            (server / "commands/grt_step1.sh").write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                "echo 'GRT step1_round1 cache hit: fixture'\n"
                "echo 'GRT step1_filter complete: recomputed'\n",
                encoding="utf-8",
            )
            partial = self.run_runner(server)
            self.assertEqual(partial.returncode, 0, partial.stderr)
            self.assertNotIn("[CACHE_HIT] [grt_step1]", partial.stdout)

            (server / "grt/evidence/step1_filter/result.txt").write_text(
                "corrupt\n", encoding="utf-8"
            )
            failed = self.run_runner(server)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("terminal validation failed", failed.stdout)
            self.assertEqual(read_status(server / "logs/status.tsv")[0]["state"], "failed")

    def test_concurrent_runner_is_rejected_without_disturbing_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ready = root / "ready"
            server = self.make_workspace(
                root,
                [("waiting", f"touch {ready}; sleep 30")],
            )
            owner = subprocess.Popen(
                ["python3", str(RUNNER), "--server-dir", str(server)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                for _ in range(200):
                    if ready.exists() and (server / ".run_all/lock/owner.json").is_file():
                        break
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                contender = self.run_runner(server)
                self.assertEqual(contender.returncode, 2)
                self.assertIn("workspace is already running", contender.stderr)
                self.assertIsNone(owner.poll())
            finally:
                owner.send_signal(signal.SIGTERM)
                owner.communicate(timeout=5)
            rows = read_status(server / "logs/status.tsv")
            self.assertEqual(rows[0]["state"], "interrupted")
            self.assertFalse((server / ".run_all/lock").exists())

    def test_stale_lock_and_abandoned_running_status_are_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = self.make_workspace(root, [("only", "echo recovered")])
            lock = server / ".run_all/lock"
            lock.mkdir()
            (lock / "owner.json").write_text(
                json.dumps(
                    {
                        "workspace": str(server.resolve()),
                        "hostname": socket.gethostname(),
                        "pid": 999999999,
                        "process_start": "missing",
                        "run_id": "abandoned",
                    }
                ),
                encoding="utf-8",
            )
            (server / "logs").mkdir()
            (server / "logs/status.tsv").write_text(
                "unit_id\tphase_index\tphase_total\tstate\tattempt\tstarted_at\tended_at\t"
                "elapsed_seconds\texit_code\tdetail_log_relpath\n"
                "only\t1\t1\trunning\t1\t2026-08-08T00:00:00+00:00\t\t\t\tlogs/run_all.log\n",
                encoding="utf-8",
            )
            result = self.run_runner(server)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = read_status(server / "logs/status.tsv")
            self.assertEqual(rows[0]["state"], "success")
            self.assertEqual(rows[0]["attempt"], "2")
            log = (server / "logs/run_all.log").read_text(encoding="utf-8")
            self.assertIn(" RESUME ", log)
            self.assertIn("[INTERRUPTED] [only] recovered abandoned running state", log)

    def test_signal_marks_active_unit_interrupted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ready = root / "ready"
            server = self.make_workspace(
                root,
                [("waiting", f"touch {ready}; sleep 30")],
            )
            process = subprocess.Popen(
                ["python3", str(RUNNER), "--server-dir", str(server)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(200):
                if ready.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 128 + signal.SIGTERM, stderr)
            self.assertIn("[INTERRUPTED] [waiting]", stdout)
            rows = read_status(server / "logs/status.tsv")
            self.assertEqual(rows[0]["state"], "interrupted")
            self.assertFalse((server / ".run_all/lock").exists())


if __name__ == "__main__":
    unittest.main()
