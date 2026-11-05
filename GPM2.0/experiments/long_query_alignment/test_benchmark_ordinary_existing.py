"""Read-only real-input benchmark contract and fail-closed controls."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark_ordinary_existing as existing


class ExistingOrdinaryTests(unittest.TestCase):
    def test_catalog_wrapped_lowercase_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.fa"
            raw = b">first comment\r\nacgtn\r\nRY\r\n>second\nACGT\n"
            path.write_bytes(raw)
            got = existing.catalog(path, ordinary_query=True)
            self.assertEqual(got["records"], [{"name": "first", "length": 7}, {"name": "second", "length": 4}])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_invalid_fasta_is_not_benchmarked(self):
        for data in [b"", b">q\n", b">q\nACG T\n", b">q\nAC\n>q\nGT\n", b"ACGT\n"]:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "input.fa"; path.write_bytes(data)
                with self.assertRaises(ValueError):
                    existing.catalog(path, ordinary_query=True)

    def test_oversized_query_is_not_sent_to_mapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.fa"; path.write_bytes(b">q\nACGT\n")
            with patch.object(existing, "QUERY_LIMIT", 3), self.assertRaises(ValueError):
                existing.catalog(path, ordinary_query=True)

    def test_reference_is_not_subject_to_query_length_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.fa"; path.write_bytes(b">q\nACGT\n")
            with patch.object(existing, "QUERY_LIMIT", 3):
                self.assertEqual(existing.catalog(path)["total_bases"], 4)

    def test_resource_snapshot_reads_actual_v1_job_leaf_not_only_root(self):
        files = {
            "/proc/self/cgroup": "4:cpu,cpuacct:/batch/job123\n2:memory:/batch/job123\n",
            "/proc/self/status": "Name:\tpython\nCpus_allowed_list:\t0-127\nThreads:\t1\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            "/sys/fs/cgroup/cpu/batch/job123/cpu.cfs_quota_us": "6400000\n",
            "/sys/fs/cgroup/cpu/batch/job123/cpu.cfs_period_us": "100000\n",
            "/sys/fs/cgroup/memory/batch/job123/memory.limit_in_bytes": "343597383680\n",
        }
        with patch.object(existing.Path, "is_file", lambda path: str(path) in files), \
                patch.object(existing.Path, "read_text", lambda path: files[str(path)]):
            got = existing.resource_snapshot()["quota_and_cpuset_observations"]
        self.assertEqual(got["/sys/fs/cgroup/cpu/batch/job123/cpu.cfs_quota_us"], "6400000\n")
        self.assertEqual(got["/sys/fs/cgroup/cpu/cpu.cfs_quota_us"], "-1\n")
        self.assertNotIn("Name:", got["/proc/self/status"])

    def test_resource_snapshot_supports_v2_leaf(self):
        files = {"/proc/self/cgroup": "0::/work/job456\n",
                 "/sys/fs/cgroup/work/job456/cpu.max": "6400000 100000\n",
                 "/sys/fs/cgroup/work/job456/memory.max": "343597383680\n"}
        with patch.object(existing.Path, "is_file", lambda path: str(path) in files), \
                patch.object(existing.Path, "read_text", lambda path: files[str(path)]):
            got = existing.resource_snapshot()["quota_and_cpuset_observations"]
        self.assertEqual(got["/sys/fs/cgroup/work/job456/cpu.max"], "6400000 100000\n")

    def test_plan_only_does_not_require_inputs_or_start_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(existing, "execute") as execute, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(existing.main(["--target", str(root / "missing.fa"), "--query", str(root / "other.fa"), "--out", str(root / "out")]), 0)
            execute.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_bounds_and_duplicate_K_never_execute(self):
        with patch.object(existing, "execute") as execute, contextlib.redirect_stderr(io.StringIO()):
            for flags in [["--threads", "0"], ["--batch-bases", "1", "1"], ["--memory-mib", "0"], ["--timeout", "7201"]]:
                with self.assertRaises(SystemExit):
                    existing.main(["--target", "/missing", "--query", "/other", "--out", "/out", "--execute", *flags])
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
