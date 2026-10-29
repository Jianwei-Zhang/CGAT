"""Streaming changes storage, not the two-fragment score witness's meaning."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import random
import tempfile
import time
import tracemalloc
import unittest
from unittest.mock import patch

import audit_post_dp as audit
import stream_seed_trace as st
import windowed_alignment as wa


def small_case():
    raw = "QR\tq\t0\t10\n" + "".join(f"CN\t1\tdecoy\t{i}\t+\t{i}\t2\t0\n" for i in (1, 3, 5, 7, 9))
    coarse = {"query": "q", "query_length": 10, "target": "decoy", "target_length": 10,
              "strand": "+", "query_start": 0, "query_end": 10, "target_start": 0, "target_end": 10,
              "minimizers": 5, "chain_score": 100}
    parts = [{**coarse, "query_end": 6, "target_end": 6},
             {**coarse, "query_start": 6, "target_start": 6}]
    return raw, coarse, parts


class StreamingTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "trace.stderr"
        self.raw, self.coarse, self.parts = small_case()
        self.path.write_text(self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, budget=None):
        return st.collect_split_counts(self.path, self.coarse, self.parts, budget)

    def test_streaming_hash_counts_and_unchanged_scores_without_eager_read(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("no whole trace text")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("no whole trace bytes")):
            result = audit.reconstruct_split_scores(self.path, [self.coarse], self.parts)
        self.assertEqual(result["trace_sha256"], hashlib.sha256(self.raw.encode()).hexdigest())
        self.assertEqual(result["fragment_anchor_counts"], [3, 2])
        self.assertEqual(result["reconstructed_chain_scores"], [60, 40])
        self.assertEqual(result["trace_resources"]["chain_groups"], 1)
        self.assertFalse(result["candidate_selection_reconstructed"])
        self.assertFalse(result["mapq_reconstructed"])
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_all_byte_line_and_time_budgets_fail_closed(self):
        budget = st.TraceBudget()
        for limits, message in [(replace(budget, max_bytes=len(self.raw)-1), "byte budget"),
                                (replace(budget, max_lines=5), "line-count"),
                                (replace(budget, max_line_bytes=10), "line-length")]:
            with self.subTest(limits=limits), self.assertRaisesRegex(wa.ExperimentError, message):
                self.collect(limits)
        with patch.object(st.time, "monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(wa.ExperimentError, "time budget"):
                self.collect()
        for bad in [replace(budget, max_bytes=0), replace(budget, max_lines=True),
                    replace(budget, max_line_bytes=1.5), replace(budget, timeout_seconds=float("inf")),
                    replace(budget, timeout_seconds=float("nan")), replace(budget, timeout_seconds=0)]:
            with self.subTest(bad=bad), self.assertRaises(wa.ExperimentError):
                self.collect(bad)
        # Exact limits are accepted, including EOF at the byte budget.
        self.assertEqual(self.collect(replace(budget, max_bytes=len(self.raw), max_lines=6))["fragment_anchor_counts"], [3, 2])

    def test_oversized_single_line_is_rejected_without_whole_line_allocation(self):
        with self.path.open("wb") as out:
            out.truncate(32 * 1024 * 1024)
        tracemalloc.start()
        try:
            with self.assertRaisesRegex(wa.ExperimentError, "line-length"):
                self.collect()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 2 * 1024 * 1024)

    def test_duplicate_matches_noncontiguous_or_unordered_chains_refused(self):
        cn = self.raw.split("\n", 1)[1]
        bad_traces = [self.raw + cn.replace("CN\t1\t", "CN\t2\t"),
                      self.raw + "CN\t2\tother\t1\t+\t1\t2\t0\n" + cn,
                      self.raw + "CN\t0\tother\t1\t+\t1\t2\t0\n",
                      self.raw + "CN\t1\tother\t1\t+\t1\t2\t0\n"]
        for raw in bad_traces:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(wa.ExperimentError):
                    self.collect()

    def test_nonmatching_chains_do_not_poison_the_matching_chain(self):
        # Old reader only checks monotonicity/ownership on the matched chain.
        before = "CN\t0\tother\t3\t+\t3\t2\t0\nCN\t0\tother\t1\t+\t1\t2\t0\n"
        after = "CN\t2\tdecoy\t5\t-\t5\t2\t0\n"
        raw = self.raw.replace("CN\t1", before + "CN\t1", 1) + after
        self.path.write_text(raw)
        result = self.collect()
        self.assertEqual(result["fragment_anchor_counts"], [3, 2])
        self.assertEqual(result["resources"]["chain_groups"], 3)
        # Invalid seed syntax/coordinates are still rejected even on irrelevant chains.
        self.path.write_text(raw.replace("CN\t2\tdecoy\t5", "CN\t2\tdecoy\t-1"))
        with self.assertRaisesRegex(wa.ExperimentError, "invalid CN"):
            self.collect()

    def test_selected_chain_monotonicity_and_fragment_ownership_refusals(self):
        self.path.write_text(self.raw.replace("CN\t1\tdecoy\t5\t+\t5", "CN\t1\tdecoy\t2\t+\t2"))
        with self.assertRaisesRegex(wa.ExperimentError, "non-monotonic"):
            self.collect()
        self.path.write_text(self.raw)
        for parts in [[{**self.parts[0], "query_end": 4}, self.parts[1]],
                      [self.parts[0], {**self.parts[1], "query_start": 4, "target_start": 4}]]:
            with self.subTest(parts=parts), self.assertRaisesRegex(wa.ExperimentError, "missing from or shared"):
                st.collect_split_counts(self.path, self.coarse, parts)
        with self.assertRaises(wa.ExperimentError):
            audit.reconstruct_split_scores(self.path, [{**self.coarse, "strand": "-"}], self.parts)

    def test_query_scope_unknown_format_truncated_line_and_qt(self):
        for raw in [self.raw + self.raw, self.raw.replace("QR\tq", "QR\tother"),
                    self.raw.replace("QR\tq\t0", "QR\tq\t1"), self.raw.rstrip("\n"),
                    self.raw.replace("\t2\t0", "\t2\tbad", 1),
                    self.raw + "QT\tq\t1\t0.01\n", self.raw + "QT\tq\t0\tnan\n",
                    self.raw + "QT\tq\t0\t0.01\nCN\t2\tother\t1\t+\t1\t2\t0\n",
                    self.raw.replace("CN\t1", "CN\tbad", 1), self.raw + "CN bad\n"]:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(wa.ExperimentError):
                    self.collect()
        self.path.write_text(self.raw + "QT\tq\t0\t0.01\n")
        self.assertTrue(self.collect()["resources"]["query_end_marker_observed"])
        self.path.write_bytes(self.raw.encode() + b"CN\t2\t\xff\t1\t+\t1\t2\t0\n")
        with self.assertRaisesRegex(wa.ExperimentError, "text CN"):
            self.collect()

    def test_input_mutation_and_nonregular_input_refused(self):
        original = st.stat_identity
        calls = 0
        def altered(st_value):
            nonlocal calls
            calls += 1
            value = original(st_value)
            return value if calls != 2 else value[:-1] + (value[-1] + 1,)
        with patch.object(st, "stat_identity", side_effect=altered):
            with self.assertRaisesRegex(wa.ExperimentError, "changed"):
                self.collect()
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        start = time.monotonic()
        with self.assertRaisesRegex(wa.ExperimentError, "regular file"):
            st.collect_split_counts(fifo, self.coarse, self.parts)
        self.assertLess(time.monotonic()-start, 1)

    def test_randomized_anchor_ownership_matches_independent_list_reference(self):
        rng = random.Random(29102032)
        for _ in range(30):
            n = rng.randrange(8, 150)
            split = rng.randrange(1, n)
            q = t = 0
            anchors = []
            for i in range(n):
                span = rng.randrange(1, 20)
                q += span + rng.randrange(1, 20)
                t += span + rng.randrange(1, 20)
                anchors.append((t, q, span))
            first_t, first_q, first_span = anchors[0]
            coarse = {**self.coarse, "query_length": q+1, "target_length": t+1,
                      "query_start": first_q+1-first_span, "target_start": first_t+1-first_span,
                      "query_end": q+1, "target_end": t+1, "minimizers": n}
            parts = [{**coarse, "query_end": anchors[split-1][1]+1, "target_end": anchors[split-1][0]+1},
                     {**coarse, "query_start": anchors[split][1]+1-anchors[split][2],
                      "target_start": anchors[split][0]+1-anchors[split][2]}]
            self.path.write_text(f"QR\tq\t0\t{q+1}\n" + "".join(f"CN\t0\tdecoy\t{t}\t+\t{q}\t{s}\t0\n" for t,q,s in anchors))
            expected = [sum(row["query_start"] <= q+1-s and q < row["query_end"]
                            and row["target_start"] <= t+1-s and t < row["target_end"] for t,q,s in anchors) for row in parts]
            self.assertEqual(expected, [split, n-split])
            self.assertEqual(st.collect_split_counts(self.path, coarse, parts)["fragment_anchor_counts"], expected)


if __name__ == "__main__":
    unittest.main()
