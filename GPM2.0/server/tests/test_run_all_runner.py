#!/usr/bin/env python3

from __future__ import annotations

import csv
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
