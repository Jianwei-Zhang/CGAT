import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.tools import grt_step23 as engine


class MummerParallelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server = self.root / "gpm_server"
        self.server.mkdir()
        self.events = self.root / "events.jsonl"
        self.failure = self.root / "fail"
        self.query = "C" * 20_000
        self.records = [(f"donor-{index}", "A" * 1_000_000) for index in range(1, 4)]
        self.members = {
            name: {"member_id": name, "dataset_name": "support", "contig_name": name}
            for name, _seq in self.records
        }
        self.lengths = {name: len(seq) for name, seq in self.records}
        self.target = self.server / "target.fa"
        self.update_target()
        nucmer = self.executable("nucmer", f'''import json, sys, time
from pathlib import Path
args = sys.argv[1:]
prefix = args[args.index('-p') + 1]
reference, query = args[-2:]
name = Path(reference).read_text().splitlines()[0][1:]
index = int(name.split('-')[1])
def event(action):
    with open({str(self.events)!r}, 'a') as handle:
        handle.write(json.dumps([name, action, time.monotonic()]) + '\\n')
event('start')
if index == 2 and Path({str(self.failure)!r}).exists():
    print('injected partition failure', file=sys.stderr)
    raise SystemExit(9)
time.sleep(0.4 if index == 1 else 0.05)
Path(prefix + '.delta').write_text(reference + '\\n' + query + '\\n')
event('end')
''')
        filter_tool = self.executable("delta-filter", "import sys\nprint(open(sys.argv[-1]).read(), end='')\n")
        coords_tool = self.executable("show-coords", '''import sys
from pathlib import Path
reference, query = Path(sys.argv[-1]).read_text().splitlines()
def read(path):
    lines = Path(path).read_text().splitlines()
    return lines[0][1:], len(''.join(lines[1:]))
name, length = read(reference)
qname, qlength = read(query)
print(reference + ' ' + query)
print('NUCMER')
print(f'1 10000 | 1 10000 | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
''')
        self.tools = {name: self.identity(path) for name, path in [
            ("nucmer", nucmer), ("delta-filter", filter_tool), ("show-coords", coords_tool)
        ]}
        self.memory = patch.object(engine, "mummer_available_memory", return_value=16 * 1024**3)
        self.memory.start()
        self.addCleanup(self.memory.stop)
        self.cpu = patch.object(engine.os, "sched_getaffinity", return_value=set(range(8)), create=True)
        self.cpu.start()
        self.addCleanup(self.cpu.stop)

    def executable(self, name, source):
        path = self.root / name
        path.write_text("#!/usr/bin/env python3\n" + source)
        path.chmod(0o755)
        return path

    @staticmethod
    def identity(path):
        return {"resolved": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "version": "fixture"}

    def update_target(self):
        self.target.write_bytes(engine.fasta_bytes(self.records))
        self.donor_set = {"donor_set_id": "target", "fasta_relpath": "target.fa",
                          "fasta_sha256": hashlib.sha256(self.target.read_bytes()).hexdigest()}

    def run_alignment(self, stage="step2", source="source", threads=2):
        return engine.cached_mummer_chromosome(
            self.server, stage, "Chr01", source, self.query, [], self.donor_set,
            self.members, self.lengths, self.tools, threads, True,
            target_kind="correction",
        )

    def calls(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def parsed(self, directory):
        return engine.parse_mummer_coords(directory / "result.coords", "step2", "Chr01",
                                         len(self.query), self.members, self.lengths)

    def test_parallel_order_matches_serial_and_respects_budget(self):
        parallel, _hit, _key = self.run_alignment()
        rows = self.parsed(parallel)
        self.assertEqual([row["ref_record"] for row in rows], list(self.members))
        calls = sorted(self.calls(), key=lambda row: row[2])
        active = peak = 0
        for _name, event, _at in calls:
            active += 1 if event == "start" else -1
            peak = max(peak, active)
        self.assertEqual(active, 0)
        self.assertEqual(peak, 2)
        self.assertEqual(next(name for name, event, _at in calls if event == "end"), "donor-2")
        shutil.rmtree(self.server / "grt/cache/step23/raw_mummer")
        serial, _hit, _key = self.run_alignment(source="serial", threads=1)
        self.assertEqual(self.parsed(serial), rows)

    def test_cross_stage_cache_invalidation_and_provenance(self):
        first, _, _ = self.run_alignment()
        starts = lambda: len([row for row in self.calls() if row[1] == "start"])
        self.assertEqual(starts(), 3)
        reused, wrapper_hit, _ = self.run_alignment(stage="step3", source="new-whole-q")
        self.assertFalse(wrapper_hit)
        self.assertNotEqual(first, reused)
        self.assertEqual(starts(), 3)
        checkpoint = json.loads((reused / "cache.json").read_text())
        self.assertEqual(checkpoint["fingerprint_payload"]["stage"], "step3")
        self.assertEqual(checkpoint["fingerprint_payload"]["q_source_sha256"], "new-whole-q")

        raw = next((self.server / "grt/cache/step23/raw_mummer/v1").iterdir())
        (raw / "result.coords").write_text("corrupt\n")
        self.run_alignment(source="verify-corruption")
        self.assertEqual(starts(), 4)
        self.records[0] = ("donor-1", "G" + self.records[0][1][1:])
        self.update_target()
        self.run_alignment(source="target-changed")
        self.assertEqual(starts(), 5)
        self.query = "T" + self.query[1:]
        self.run_alignment(source="query-changed")
        self.assertEqual(starts(), 8)
        path = Path(self.tools["nucmer"]["resolved"])
        path.write_text(path.read_text() + "\n# new tool identity\n")
        self.tools["nucmer"] = self.identity(path)
        self.run_alignment(source="tool-changed")
        self.assertEqual(starts(), 11)
        with patch.object(engine, "MUMMER_MIN_ALIGNMENT", 11_000):
            changed, _, _ = self.run_alignment(source="threshold-changed")
        self.assertEqual(starts(), 14)
        self.assertIn(" -l 11000 ", (changed / "delta_filter.command.txt").read_text())

    def test_failure_keeps_completed_partitions_and_cancels_workers(self):
        self.failure.touch()
        with self.assertRaisesRegex(SystemExit, "injected partition failure.*failed_artifacts="):
            self.run_alignment(threads=1)
        raw = self.server / "grt/cache/step23/raw_mummer/v1"
        self.assertEqual(len(list(raw.iterdir())), 1)
        failed = list((self.server / "grt/failed").glob("step2-mummer-*"))
        self.assertEqual(len(failed), 1)
        self.assertTrue((failed[0] / "part-0002/nucmer.stderr.log").is_file())
        before = self.calls()
        self.failure.unlink()
        result, _hit, _key = self.run_alignment(threads=2)
        self.assertEqual(len(self.parsed(result)), 3)
        self.assertEqual([row for row in self.calls() if row[:2] == ["donor-1", "start"]],
                         [row for row in before if row[:2] == ["donor-1", "start"]])
        self.assertEqual(len(list(raw.iterdir())), 3)

    def test_worker_admission_limits(self):
        workers = engine.mummer_partition_workers
        self.assertEqual(workers(10, [1_000_000] * 30, 30_000_000, available_memory=16 * 1024**3), 8)
        self.assertEqual(workers(2, [1_000_000] * 30, 30_000_000, available_memory=16 * 1024**3), 2)
        self.assertEqual(workers(10, [1_000_000] * 30, 30_000_000, available_memory=1024**3), 1)
        self.assertEqual(workers(10, [1_000_000] * 30, 30_000_000, available_memory=0), 1)
        self.assertEqual(workers(0, [], 0, available_memory=0), 1)

    def test_parallel_failure_terminates_an_active_command(self):
        pid_path = self.root / "active.pid"
        path = Path(self.tools["nucmer"]["resolved"])
        source = path.read_text().replace(
            "event('start')",
            f"event('start')\nif index == 1:\n    Path({str(pid_path)!r}).write_text(str(__import__('os').getpid()))",
        ).replace(
            "print('injected partition failure', file=sys.stderr)",
            f"deadline = time.monotonic() + 2\n    while not Path({str(pid_path)!r}).exists() and time.monotonic() < deadline:\n        time.sleep(0.01)\n    print('injected partition failure', file=sys.stderr)",
        ).replace("0.4 if index == 1", "30 if index == 1")
        path.write_text(source)
        self.tools["nucmer"] = self.identity(path)
        self.failure.touch()
        started = time.monotonic()
        with self.assertRaisesRegex(SystemExit, "injected partition failure"):
            self.run_alignment(threads=2)
        self.assertLess(time.monotonic() - started, 5)
        pid = int(pid_path.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
