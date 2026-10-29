"""Reverse CN query frames and split order must be independently witnessed."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import random
import shutil
import tempfile
import unittest

import audit_post_dp as audit
import stream_seed_trace as st
import windowed_alignment as wa


class ReverseSplitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.trace = self.root / "trace.stderr"
        self.coarse = {"query": "q", "query_length": 40, "query_start": 23, "query_end": 33,
                       "target": "decoy", "target_length": 200, "target_start": 80, "target_end": 90,
                       "strand": "-", "minimizers": 5, "chain_score": 100}
        self.parts = [{**self.coarse, "query_start": 27, "target_end": 86, "minimizers": 3,
                       "chain_score": 60, "alignment_score": 60},
                      {**self.coarse, "query_end": 27, "target_start": 86, "minimizers": 2,
                       "chain_score": 40, "alignment_score": 40}]
        self.raw = "QR\tq\t0\t40\n" + "".join(f"CN\t0\tdecoy\t{t}\t-\t{q}\t2\t0\n"
                                                    for t,q in zip((81,83,85,87,89),(8,10,12,14,16)))
        self.trace.write_text(self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def test_asymmetric_reverse_bounds_use_full_query_length_and_leave_inputs_unchanged(self):
        before = copy.deepcopy((self.coarse, self.parts))
        result = audit.split_score_witness(self.trace, [self.coarse], list(reversed(self.parts)))
        self.assertEqual(result["fragment_anchor_counts"], [3, 2])
        self.assertEqual(result["reconstructed_chain_scores"], [60, 40])
        self.assertEqual(st.oriented_query_interval(self.coarse), (7, 17))
        self.assertEqual((self.coarse, self.parts), before)
        self.assertFalse(result["mapq_reconstructed"])
        self.assertFalse(result["candidate_selection_reconstructed"])
        self.trace.write_text(self.raw.replace("\t8\t2", "\t31\t2", 1))
        with self.assertRaises(wa.ExperimentError):
            audit.reconstruct_split_scores(self.trace, [self.coarse], self.parts)

    def test_target_chain_order_controls_rounding_not_forward_query_order(self):
        coarse = {**self.coarse, "query_length": 10, "query_start": 4, "query_end": 10,
                  "target_start": 100, "target_end": 106, "minimizers": 2, "chain_score": 3}
        parts = [{**coarse, "query_start": 8, "target_end": 102, "minimizers": 1,
                  "chain_score": 2, "alignment_score": 2},
                 {**coarse, "query_end": 6, "target_start": 104, "minimizers": 1,
                  "chain_score": 1, "alignment_score": 2}]
        self.trace.write_text("QR\tq\t0\t10\nCN\t0\tdecoy\t101\t-\t1\t2\t0\nCN\t0\tdecoy\t105\t-\t5\t2\t0\n")
        # With score=3, equal seed halves allocate 2 to chain head and 1 to tail.
        result = audit.split_score_witness(self.trace, [coarse], sorted(parts, key=lambda row: row["query_start"]))
        self.assertEqual(result["reconstructed_chain_scores"], [2, 1])
        wrong = [{**parts[0], "chain_score": 1}, {**parts[1], "chain_score": 2}]
        with self.assertRaisesRegex(wa.ExperimentError, "scores do not match"):
            audit.split_score_witness(self.trace, [coarse], wrong)

    def test_mixed_strand_identity_and_more_than_two_fragments_fail_closed(self):
        for parts in [[{**self.parts[0], "strand": "+"}, self.parts[1]],
                      [{**self.parts[0], "query_length": 41}, self.parts[1]],
                      [{**self.parts[0], "target": "other"}, self.parts[1]],
                      [*self.parts, self.parts[0]],
                      [{**self.parts[0], "query_start": 20}, {**self.parts[1], "query_start": 28, "query_end": 35}]]:
            with self.subTest(parts=parts), self.assertRaises(wa.ExperimentError):
                audit.reconstruct_split_scores(self.trace, [self.coarse], parts)

    def test_buffer_budget_changes_storage_not_witness_values(self):
        reference = None
        for size in (8192, 65536, 1024**2, 16*1024**2):
            result = audit.reconstruct_split_scores(self.trace, [self.coarse], self.parts,
                                                   trace_budget=st.TraceBudget(read_buffer_bytes=size))
            resources = result.pop("trace_resources")
            self.assertEqual(resources["limits"]["read_buffer_bytes"], size)
            if reference is None:
                reference = result
            self.assertEqual(result, reference)
        for size in (0, 8191, 16*1024**2+1, True):
            with self.subTest(size=size), self.assertRaises(wa.ExperimentError):
                audit.reconstruct_split_scores(self.trace, [self.coarse], self.parts,
                                               trace_budget=st.TraceBudget(read_buffer_bytes=size))

    def test_randomized_reverse_ownership_in_forward_paf_coordinates(self):
        rng = random.Random(29102033)
        for _ in range(30):
            n = rng.randrange(6, 60)
            cut = rng.randrange(1, n)
            q, t = rng.randrange(10, 50), rng.randrange(80, 160)
            anchors = []
            for _ in range(n):
                span = rng.randrange(1, 20)
                q += span + rng.randrange(1, 20)
                t += span + rng.randrange(1, 20)
                anchors.append((t,q,span))
            length = q + rng.randrange(20, 100)
            first_t, first_q, first_span = anchors[0]
            coarse = {**self.coarse, "query_length": length, "query_start": length-q-1,
                      "query_end": length-(first_q+1-first_span), "target_start": first_t+1-first_span,
                      "target_end": t+1, "target_length": t+80, "minimizers": n}
            left = anchors[cut-1];right = anchors[cut]
            parts = [{**coarse, "query_start": length-left[1]-1, "target_end": left[0]+1},
                     {**coarse, "query_end": length-(right[1]+1-right[2]), "target_start": right[0]+1-right[2]}]
            self.trace.write_text(f"QR\tq\t0\t{length}\n" + "".join(f"CN\t0\tdecoy\t{t}\t-\t{q}\t{s}\t0\n" for t,q,s in anchors))
            # Independent oracle transforms each seed interval to forward query coordinates.
            counts = [sum(row["query_start"] <= length-q-1 and length-(q+1-s) <= row["query_end"]
                          and row["target_start"] <= t+1-s and t < row["target_end"] for t,q,s in anchors) for row in parts]
            self.assertEqual(counts, [cut, n-cut])
            self.assertEqual(audit.reconstruct_split_scores(self.trace, [coarse], parts)["fragment_anchor_counts"], counts)

    @unittest.skipUnless(shutil.which("minimap2"), "real minimap2 unavailable")
    def test_real_reverse_dp_and_window_pool_keep_original_refusal(self):
        result = audit.experiment(argparse.Namespace(out=self.root / "audit", minimap2=shutil.which("minimap2"),
                                                    query_orientation="reverse"))
        self.assertEqual(result["query_orientation"], "reverse")
        self.assertFalse(result["production_ready"])
        cases = {row["case"]:row for row in result["cases"]}
        self.assertTrue(cases["identity"]["guided_final_exists"])
        for name in ("split_decoy", "chain_score_not_alignment_score"):
            self.assertEqual(cases[name]["guidance_status"], "failed")
            self.assertFalse(cases[name]["guided_final_exists"])
        case = cases["chain_score_not_alignment_score"]
        witness = case["seed_trace_witness"]
        self.assertEqual(witness["reconstructed_chain_scores"], witness["reported_dp_chain_scores"])
        pool = case["window_pool_witness"]
        self.assertTrue(pool["pool_path_relations_equal"])
        self.assertTrue(pool["recovered_scores_equal_oracle"])
        self.assertFalse(pool["general_parent_selection_implemented"])
        self.assertFalse(pool["mapq_reconstructed"])
        self.assertTrue(all(row["strand"] == "-" and row["mapq"] == 255 for row in pool["rows"]))
        fragments = sorted([row for row in pool["rows"] if row["target"] == "decoy"], key=lambda row:row["target_start"])
        self.assertGreater(fragments[0]["query_start"], fragments[1]["query_start"])
        self.assertEqual([row["chain_score"] for row in fragments], witness["reconstructed_chain_scores"])


if __name__ == "__main__":
    unittest.main()
