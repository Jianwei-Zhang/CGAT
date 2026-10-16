import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.tools.grt_core import repair_mummer as engine
from server.tools.grt_core.repair_structural import _step3_anchor_pairs


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

    def run_alignment(self, stage="step2", source="source", threads=2, mummer_scope="full"):
        return engine.cached_mummer_chromosome(
            self.server, stage, "Chr01", source, self.query, [], self.donor_set,
            self.members, self.lengths, self.tools, threads, True,
            target_kind="correction",
            mummer_scope=mummer_scope,
        )

    def calls(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def parsed(self, directory):
        return engine.parse_mummer_coords(directory / "result.coords", "step2", "Chr01",
                                         len(self.query), self.members, self.lengths)

    def test_parallel_order_matches_serial_and_respects_budget(self):
        # Synchronize the first two workers: shared HPC filesystems can take
        # longer to launch a process than the fixture's short simulated work.
        first_started = self.root / "first-started"
        second_finished = self.root / "second-finished"
        path = Path(self.tools["nucmer"]["resolved"])
        source = path.read_text().replace(
            "time.sleep(0.4 if index == 1 else 0.05)",
            f"""if index in (1, 2):
    if index == 1:
        Path({str(first_started)!r}).touch()
    marker = Path({str(second_finished)!r} if index == 1 else {str(first_started)!r})
    deadline = time.monotonic() + 20
    while not marker.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('parallel fixture synchronization timed out')
        time.sleep(0.02)""",
        ).replace(
            "event('end')",
            f"event('end')\nif index == 2:\n    Path({str(second_finished)!r}).touch()",
        )
        path.write_text(source)
        self.tools["nucmer"] = self.identity(path)
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

    def test_step3_gap_screen_reruns_only_candidate_partitions_against_full_query(self):
        self.query = "C" * 600_000 + "N" * 100 + "C" * 600_000
        coords_tool = self.executable("screen-show-coords", '''import sys
from pathlib import Path
reference, query = Path(sys.argv[-1]).read_text().splitlines()
def read(path):
    lines = Path(path).read_text().splitlines()
    return lines[0][1:], len(''.join(lines[1:]))
name, length = read(reference)
qname, qlength = read(query)
print(reference + ' ' + query)
print('NUCMER')
if qname.startswith('screen_'):
    if name != 'donor-2':
        raise SystemExit(0)
    start = int(qname.split('_')[-2])
    local = 600001 - start + 1
    print(f'1 10000 | {local - 5000} {local + 4999} | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
else:
    print(f'1 10000 | 1 10000 | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
''')
        self.tools["show-coords"] = self.identity(coords_tool)

        result, wrapper_hit, _key = self.run_alignment(
            stage="step3", source="screened", threads=2, mummer_scope="gap-screen"
        )

        self.assertFalse(wrapper_hit)
        self.assertEqual([row["ref_record"] for row in self.parsed(result)], ["donor-2"])
        manifest = json.loads((result / "target_partitions.json").read_text())
        self.assertEqual(
            [row["partition"] for row in manifest if row["selected"]],
            [2],
        )
        screen_rows = (result / "screen_partitions.tsv").read_text().splitlines()
        self.assertEqual(sum("\ttrue\t" in row for row in screen_rows[1:]), 1)
        self.assertEqual(len([row for row in self.calls() if row[1] == "start"]), 4)
        reused, wrapper_hit, _key = self.run_alignment(
            stage="step3", source="screened", threads=2, mummer_scope="gap-screen"
        )
        self.assertTrue(wrapper_hit)
        self.assertEqual(reused, result)
        self.assertEqual(len([row for row in self.calls() if row[1] == "start"]), 4)

    def test_step2_gap_screen_reruns_only_candidate_partitions_against_full_query(self):
        self.query = "C" * 1_200_000 + "N" * 100 + "C" * 1_200_000
        coords_tool = self.executable("step2-screen-show-coords", '''import sys
from pathlib import Path
reference, query = Path(sys.argv[-1]).read_text().splitlines()
def read(path):
    lines = Path(path).read_text().splitlines()
    return lines[0][1:], len(''.join(lines[1:]))
name, length = read(reference)
qname, qlength = read(query)
print(reference + ' ' + query)
print('NUCMER')
if qname.startswith('screen_'):
    if name != 'donor-2':
        raise SystemExit(0)
    start = int(qname.split('_')[-2])
    local = 1200001 - start + 1
    print(f'1 10000 | {local - 20000} {local - 10001} | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
    print(f'20001 30000 | {local + 10001} {local + 20000} | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
else:
    print(f'1 10000 | 1 10000 | 10000 10000 | 99.00 | {length} {qlength} | {name} {qname}')
''')
        self.tools["show-coords"] = self.identity(coords_tool)

        result, wrapper_hit, _key = self.run_alignment(
            stage="step2", source="screened-step2", threads=2,
            mummer_scope="gap-screen",
        )

        self.assertFalse(wrapper_hit)
        self.assertEqual([row["ref_record"] for row in self.parsed(result)], ["donor-2"])
        manifest = json.loads((result / "target_partitions.json").read_text())
        self.assertEqual(
            [row["partition"] for row in manifest if row["selected"]],
            [2],
        )
        self.assertEqual(len([row for row in self.calls() if row[1] == "start"]), 4)

    def test_screen_preserves_one_sided_anchors_that_stop_window_expansion(self):
        gap_pos = 1_000_050
        gap = {"start0": 1_000_000, "end0": 1_000_100}
        def row(record, start, end):
            return {"ref_record": record, "query_min": start, "query_max": end,
                    "identity": 0.99, "query_aligned": end - start + 1}
        partitions = [
            [row("near-left-only", gap_pos - 60_000, gap_pos - 50_000)],
            [row("near-right-only", gap_pos + 50_000, gap_pos + 60_000)],
            [row("far-pair", gap_pos - 220_000, gap_pos - 200_000),
             row("far-pair", gap_pos + 200_000, gap_pos + 220_000)],
        ]
        original = [r for partition in partitions for r in partition]
        # Near anchors on different records stop the search at 100 kb; there
        # must not be an artificial 200 kb pair after screening them away.
        self.assertEqual(_step3_anchor_pairs(gap_pos, original), [])
        selected = [
            partition for partition in partitions
            if engine.step3_screen_partition_relevant([gap], partition)
        ]
        self.assertEqual(len(selected), 3)
        screened = [r for partition in selected for r in partition]
        self.assertEqual(_step3_anchor_pairs(gap_pos, screened), [])
        outside = [row("irrelevant", gap_pos + 600_000, gap_pos + 620_000)]
        self.assertFalse(engine.step3_screen_partition_relevant([gap], outside))

    def test_complete_raw_cache_requires_every_partition(self):
        self.run_alignment(stage="step2", source="cache-source", threads=2)
        partitions = engine.partition_mummer_targets(dict(self.records))
        self.assertTrue(
            engine.complete_raw_mummer_cache(
                self.server, "Chr01", self.query, partitions, self.tools
            )
        )
        raw_dirs = sorted((self.server / "grt/cache/step23/raw_mummer/v1").iterdir())
        shutil.rmtree(raw_dirs[0])
        self.assertFalse(
            engine.complete_raw_mummer_cache(
                self.server, "Chr01", self.query, partitions, self.tools
            )
        )

    def collect_unchanged_q2(self):
        q_dir = self.server / "grt/q"
        q_dir.mkdir(parents=True, exist_ok=True)
        (q_dir / "q1.fa").write_bytes(engine.fasta_bytes([("Chr01", self.query)]))
        temporary = self.server / "stage-artifacts"
        temporary.mkdir()
        members = [
            {**member, "fasta_record_name": name}
            for name, member in self.members.items()
        ]
        return engine.collect_mummer(
            self.server, temporary, "grt/evidence/step3", "step3", "source-q2",
            ["Chr01"], {"Chr01": self.query}, [], self.donor_set, members,
            self.tools, 2, target_kind="correction", mummer_scope="gap-screen",
        )

    def test_unchanged_q2_with_partial_raw_cache_still_screens(self):
        self.query = "C" * 20_000 + "N" * 100 + "C" * 20_000
        self.run_alignment(stage="step2")
        query_sha = engine.sha256_bytes(engine.fasta_bytes([("Chr01", self.query)]))
        _target, _payload, _fingerprint, cache_dir, _names = engine.raw_mummer_cache_identity(
            self.server, [self.records[1]], query_sha, self.tools,
        )
        shutil.rmtree(cache_dir)
        before = len([row for row in self.calls() if row[1] == "start"])
        with patch.object(engine, "screen_mummer_partitions", return_value=({2}, [], [])) as screen:
            alignments, _identities, _tasks = self.collect_unchanged_q2()
        screen.assert_called_once()
        self.assertEqual([row["ref_record"] for row in alignments], ["donor-2"])
        self.assertEqual(len([row for row in self.calls() if row[1] == "start"]), before + 1)

    def test_unchanged_q2_with_complete_raw_cache_never_launches_nucmer(self):
        self.query = "C" * 20_000 + "N" * 100 + "C" * 20_000
        self.run_alignment(stage="step2")
        before = self.calls()
        with patch.object(engine, "screen_mummer_partitions") as screen:
            alignments, _identities, _tasks = self.collect_unchanged_q2()
        screen.assert_not_called()
        self.assertEqual([row["ref_record"] for row in alignments], list(self.members))
        self.assertEqual(self.calls(), before)

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

    def collect_alignment(self, profile, *, scope="full", threads=2, label="collect"):
        temporary = self.server / label
        temporary.mkdir()
        query = "C" * 20000 + "N" * 100 + "C" * 20000
        return engine.collect_mummer(
            self.server, temporary, "grt/artifacts/step2/fixture", "step2", "source",
            ["Chr01", "Chr02"], {"Chr01": query, "Chr02": query}, [],
            self.donor_set, [dict(row, fasta_record_name=name) for name, row in self.members.items()],
            self.tools, threads, target_kind="correction", mummer_scope=scope,
            execution_profile=profile,
        )

    def test_shared_chromosomes_keep_order_and_do_not_multiply_worker_budget(self):
        # One target per chromosome: the former per-chromosome worker cap must
        # not accidentally serialize the shared executor to one worker.
        self.records = self.records[:1]
        self.members = {self.records[0][0]: self.members[self.records[0][0]]}
        self.lengths = {name: len(seq) for name, seq in self.records}
        self.update_target()
        # Synchronize the two real child processes; launch latency on a busy
        # runner/shared filesystem is not a concurrency oracle.
        path = Path(self.tools["nucmer"]["resolved"])
        source = path.read_text().replace(
            "time.sleep(0.4 if index == 1 else 0.05)",
            f"""qname = Path(query).read_text().splitlines()[0][1:]
Path({str(self.root)!r}, 'started-' + qname).touch()
other = 'Chr02' if qname == 'Chr01' else 'Chr01'
deadline = time.monotonic() + 20
while not Path({str(self.root)!r}, 'started-' + other).exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('shared chromosome synchronization timed out')
    time.sleep(0.01)""",
        )
        path.write_text(source)
        self.tools["nucmer"] = self.identity(path)
        with patch.object(engine, "read_fasta_allow_empty", wraps=engine.read_fasta_allow_empty) as reads:
            rows, identities, tasks = self.collect_alignment("optimized")
        self.assertEqual(reads.call_count, 1)
        self.assertEqual([row["chr"] for row in rows], ["Chr01", "Chr02"])
        self.assertEqual([row["chr"] for row in tasks], ["Chr01", "Chr02"])
        active = peak = 0
        for _name, event, _at in sorted(self.calls(), key=lambda row: row[2]):
            active += 1 if event == "start" else -1
            peak = max(peak, active)
        self.assertEqual(active, 0)
        self.assertEqual(peak, 2)
        paths = list((self.server / "grt/cache/step23/inputs/v1").glob("*.fa"))
        self.assertEqual(len(paths), 1)
        paths[0].write_text("corrupt\n")
        before = len(self.calls())
        self.collect_alignment("optimized", label="repaired-input")
        self.assertEqual(len(self.calls()), before)
        self.assertEqual(paths[0].read_bytes(), engine.fasta_bytes(self.records))

    def test_optimized_execution_matches_baseline_without_new_numerical_keys(self):
        baseline, _, _ = self.collect_alignment("baseline", label="baseline")
        starts = len([row for row in self.calls() if row[1] == "start"])
        self.assertEqual(starts, 6)
        # Remove wrappers only: optimized input reuse must retain raw-cache keys.
        shutil.rmtree(self.server / "grt/cache/step23/step2")
        with patch.object(engine, "parse_mummer_coords", wraps=engine.parse_mummer_coords) as parsed:
            optimized, _, _ = self.collect_alignment("optimized", label="optimized")
        self.assertEqual(optimized, baseline)
        self.assertEqual(len([row for row in self.calls() if row[1] == "start"]), starts)
        # Six raw validation parses and two merged parses; no third parse in collect.
        self.assertEqual(parsed.call_count, 8)

    def test_shared_screen_and_full_jobs_obey_one_global_budget(self):
        self.collect_alignment("optimized", scope="gap-screen")
        active = peak = 0
        for _name, event, _at in sorted(self.calls(), key=lambda row: row[2]):
            active += 1 if event == "start" else -1
            peak = max(peak, active)
        self.assertEqual(active, 0)
        self.assertLessEqual(peak, 2)
        self.assertGreaterEqual(peak, 1)

    def test_identical_screen_queries_share_one_build_and_repair_corruption(self):
        from threading import Barrier
        self.records = self.records[:1]
        self.members = {self.records[0][0]: self.members[self.records[0][0]]}
        self.lengths = {name: len(seq) for name, seq in self.records}
        self.update_target()
        original_worker = engine.cached_mummer_screen_partition
        original_valid = engine.valid_mummer_cache

        def run_pair(label):
            simultaneous = Barrier(2)
            def worker(*args, **kwargs):
                simultaneous.wait(timeout=20)
                return original_worker(*args, **kwargs)
            def validate(directory, *args):
                valid = original_valid(directory, *args)
                if not valid and "raw_mummer_screen" in str(directory):
                    # Without per-key locking both simultaneous callers would
                    # see a miss and build/publish the same directory.
                    time.sleep(0.1)
                return valid
            with patch.object(engine, "cached_mummer_screen_partition", side_effect=worker), \
                 patch.object(engine, "valid_mummer_cache", side_effect=validate):
                return self.collect_alignment("optimized", scope="gap-screen", label=label)

        first, _, _ = run_pair("same-window-first")
        starts = lambda: len([row for row in self.calls() if row[1] == "start"])
        # One shared screen, plus one full-query alignment for each chromosome.
        self.assertEqual(starts(), 3)
        screen = next((self.server / "grt/cache/step23/raw_mummer_screen/v1").iterdir())
        (screen / "result.coords").write_text("corrupt\n")
        shutil.rmtree(self.server / "grt/cache/step23/step2")
        repaired, _, _ = run_pair("same-window-repaired")
        self.assertEqual(starts(), 4)
        self.assertEqual(repaired, first)
        checkpoint = json.loads((screen / "cache.json").read_text())
        self.assertTrue(original_valid(screen, checkpoint["input_fingerprint"], list(checkpoint["output_hashes"])))

    def test_largest_partition_first_keeps_original_aggregation_order(self):
        partitions = [[("small", "A")], [("large", "A" * 20)], [("medium", "A" * 5)]]
        execution = engine.MummerExecution({}, partitions, [], {}, None, 2, engine.Event())
        self.assertEqual(execution.indices(), [2, 3, 1])
        self.assertEqual(execution.indices({1, 3}), [3, 1])

    def test_shared_failure_cancels_other_chromosomes_promptly(self):
        self.failure.touch()
        path = Path(self.tools["nucmer"]["resolved"])
        path.write_text(path.read_text().replace("0.4 if index == 1", "30 if index == 1"))
        self.tools["nucmer"] = self.identity(path)
        started = time.monotonic()
        with self.assertRaises(SystemExit):
            # Two chromosomes can occupy two slots with their slow first job;
            # a third slot guarantees the injected failure can start, regardless
            # of coordinator interleaving. The existing serial-chromosome test
            # separately verifies termination of an already active command.
            self.collect_alignment("optimized", threads=3)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(list((self.server / "grt/failed").iterdir()))
        self.assertFalse(list((self.server / "grt/cache/step23/step2").glob("*/**/cache.json")))

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
