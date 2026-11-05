"""Read-only batch reconstruction and opt-in performance experiment safeguards."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ordinary_batch_performance as batch


class BatchPerformanceTests(unittest.TestCase):
    def test_record_boundaries_cross_threshold_without_splitting(self):
        rows = [{"name": str(i), "length": n} for i, n in enumerate([4, 7, 2, 9, 1])]
        parts = batch.partition(rows, 10)
        self.assertEqual([[r["length"] for r in p] for p in parts], [[4, 7], [2, 9], [1]])
        self.assertEqual([id(r) for p in parts for r in p], [id(r) for r in rows])

    def test_single_record_larger_than_K_is_never_split(self):
        rows = [{"length": n} for n in [11, 12]]
        self.assertEqual([len(p) for p in batch.partition(rows, 10)], [1, 1])

    def test_invalid_batch_and_record_lengths_refused(self):
        for value in [0, -1, True, 1.0]:
            with self.assertRaises(ValueError):
                batch.partition([], value)
        for value in [0, -1, True, 1.0]:
            with self.assertRaises(ValueError):
                batch.partition([{"length": value}], 10)

    def log(self, counts=(2, 1), parts=2):
        text = ""
        for p in range(parts):
            text += f"[M::main::1.0*1.00] loaded/built the index for {p+1} target sequence(s)\n"
            text += "".join(f"[M::worker_pipeline::{i+2}.0*1.50] mapped {count} sequences\n" for i, count in enumerate(counts))
        return text + "[M::main] Real time: 100.0 sec; CPU: 175.0 sec; Peak RSS: 2.5 GB\n"

    def fixture(self):
        catalog = {"records": [{"name": name, "length": 250_000_000} for name in ("q1", "q2", "q3", "long")]}
        return catalog, {"native_queries": ["q1", "q2", "q3"]}

    def test_complete_multipart_resource_summary(self):
        got = batch.parse_log(self.log())
        self.assertEqual(got["average_cpu_core_equivalents"], 1.75)
        self.assertEqual([p["target_records"] for p in got["parts"]], [1, 2])
        self.assertEqual([[b["records"] for b in p["batches"]] for p in got["parts"]], [[2, 1], [2, 1]])

    def test_missing_or_duplicate_final_summary_refused(self):
        for text in [self.log().split("[M::main] Real time:")[0], self.log() + self.log()]:
            with self.assertRaises(ValueError):
                batch.parse_log(text)

    def test_batch_before_index_refused(self):
        with self.assertRaises(ValueError):
            batch.parse_log("[M::worker_pipeline::2.0*1.0] mapped 1 sequences\n" + self.log())

    def test_analysis_matches_every_part_and_never_claims_prediction_measured(self):
        catalog, plan = self.fixture()
        got = batch.analyze(catalog, plan, self.log(), 64, [500_000_000, 1_000_000_000])
        self.assertEqual(got["ordinary_records"], 3)
        self.assertEqual(got["ordinary_bases"], 750_000_000)
        self.assertEqual(got["average_cpu_fraction_of_requested_threads"], 1.75 / 64)
        self.assertEqual([p["record_counts"] for p in got["candidate_batch_predictions"]], [[2, 1], [3]])
        self.assertTrue(all(not p["performance_measured"] and not p["output_equivalence_validated"] for p in got["candidate_batch_predictions"]))

    def test_observed_batch_mismatch_refuses_default_K_assumption(self):
        catalog, plan = self.fixture()
        with self.assertRaises(ValueError):
            batch.analyze(catalog, plan, self.log((3,)), 64, [1_000_000_000])

    def test_missing_duplicate_reordered_queries_refused(self):
        catalog, plan = self.fixture()
        for names in [["q1", "missing"], ["q1", "q1"], ["q2", "q1"], []]:
            with self.assertRaises(ValueError):
                batch.analyze(catalog, {"native_queries": names}, self.log(), 64, [1_000_000_000])

    def test_benchmark_default_creates_no_files_and_runs_no_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(batch, "benchmark") as execute, contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(batch.main(["benchmark", "--out", str(root / "out")]), 0)
            execute.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])
            self.assertFalse(json.loads(stdout.getvalue())["mapper_started"])

    def test_analysis_cli_is_read_only_without_output(self):
        catalog, plan = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, data in [("catalog.json", json.dumps(catalog)), ("plan.json", json.dumps(plan)), ("native.stderr", self.log())]:
                (root / name).write_text(data)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.object(batch.subprocess, "Popen") as child, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(["analyze", "--catalog", str(root / "catalog.json"),
                    "--plan", str(root / "plan.json"), "--native-log", str(root / "native.stderr"), "--threads", "64"]), 0)
            child.assert_not_called()
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_analysis_output_refuses_to_overwrite_existing_file(self):
        catalog, plan = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "catalog.json").write_text(json.dumps(catalog))
            (root / "plan.json").write_text(json.dumps(plan))
            (root / "native.stderr").write_text(self.log())
            output = root / "keep.json"
            output.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                batch.main(["analyze", "--catalog", str(root / "catalog.json"), "--plan", str(root / "plan.json"),
                            "--native-log", str(root / "native.stderr"), "--threads", "64", "--output", str(output)])
            self.assertEqual(output.read_bytes(), b"original")

    def test_invalid_resources_never_execute(self):
        with patch.object(batch, "benchmark") as execute, contextlib.redirect_stderr(io.StringIO()):
            for flags in [["--threads", "0"], ["--batch-bases", "1", "1"], ["--batch-bases", "0", "1"],
                          ["--records", "1024", "--query-bases", "100000000"]]:
                with self.assertRaises(SystemExit):
                    batch.main(["benchmark", "--out", "/must-not-exist", "--execute", *flags])
        execute.assert_not_called()

    def test_control_inputs_deterministic_and_multiple_named_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "a", Path(temporary) / "b"
            first.mkdir(); second.mkdir()
            paths_a, paths_b = batch.generate(first, 18, 1000), batch.generate(second, 18, 1000)
            self.assertEqual([p.read_bytes() for p in paths_a], [p.read_bytes() for p in paths_b])
            queries = paths_a[1].read_bytes()
            self.assertEqual(queries.count(b">q"), 18)
            self.assertIn(b"\n" + b"N" * 1000 + b"\n", queries)


if __name__ == "__main__":
    unittest.main()
