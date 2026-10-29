"""Deferred validation for conditional sequential multi-fragment accounting.

No test in this file was executed during implementation per user instruction.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import sequential_split_witness as sw
import stream_seed_trace as st
import windowed_alignment as wa


def fixture(strand="+"):
    coarse = {"query":"q", "query_length":12, "query_start":0, "query_end":12,
              "strand":strand, "target":"t", "target_length":12,
              "target_start":0, "target_end":12, "minimizers":6, "chain_score":100}
    if strand == "+":
        query_bounds = ((0,4),(4,8),(8,12))
    else:
        query_bounds = ((8,12),(4,8),(0,4))
    fragments = [{**coarse, "query_start":qs, "query_end":qe,
                  "target_start":i*4, "target_end":i*4+4}
                 for i,(qs,qe) in enumerate(query_bounds)]
    raw = "QR\tq\t0\t12\n" + "".join(
        f"CN\t0\tt\t{n}\t{strand}\t{n}\t2\t0\n" for n in (1,3,5,7,9,11)) + "QT\tq\t0\t0.1\n"
    return raw, coarse, fragments


class SequentialSplitWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trace = Path(self.temp.name)/"trace.stderr"

    def test_binary32_sequential_tail_rounding_not_all_at_once(self):
        result = sw.sequential_scores(4, [1,1,1])
        self.assertEqual(result["reconstructed_chain_scores"], [1,2,1])
        self.assertEqual(sum(result["reconstructed_chain_scores"]), 4)
        self.assertEqual([step["parent_score"] for step in result["split_steps"]], [4,3])
        self.assertFalse(result["execution_validated"])

    def test_three_fragment_forward_and_reverse_provenance(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                raw, coarse, fragments = fixture(strand)
                self.trace.write_text(raw)
                before = copy.deepcopy((coarse, fragments))
                result = sw.reconstruct_sequential_splits(self.trace, coarse, fragments)
                self.assertEqual(result["fragment_anchor_counts"], [2,2,2])
                self.assertEqual(result["reconstructed_chain_scores"], [33,34,33])
                self.assertEqual((coarse, fragments), before)
                self.assertFalse(result["candidate_selection_reconstructed"])
                self.assertFalse(result["mapq_reconstructed"])
                self.assertFalse(result["producer_exit_validated_here"])
                self.assertFalse(result["customer_validated"])

    def test_fragment_reported_scores_are_not_inputs_to_reconstruction(self):
        raw, coarse, fragments = fixture()
        self.trace.write_text(raw)
        poisoned = [{**row, "minimizers":"untrusted", "chain_score":"untrusted",
                     "alignment_score":10**9, "mapq":60} for row in fragments]
        result = sw.reconstruct_sequential_splits(self.trace, coarse, poisoned)
        self.assertEqual(result["reconstructed_chain_scores"], [33,34,33])
        self.assertFalse(result["oracle_scores_compared"])

    def test_oracle_comparison_is_separate_and_exact(self):
        raw, coarse, fragments = fixture()
        self.trace.write_text(raw)
        oracle = [{**row, "minimizers":2, "chain_score":score}
                  for row,score in zip(fragments,(33,34,33))]
        result = sw.compare_sequential_oracle(self.trace, coarse, oracle)
        self.assertTrue(result["oracle_scores_compared"])
        wrong = copy.deepcopy(oracle)
        wrong[1]["chain_score"] = 33
        with self.assertRaisesRegex(wa.ExperimentError, "scores disagree"):
            sw.compare_sequential_oracle(self.trace, coarse, wrong)

    def test_missing_qt_shared_missing_or_nonmonotonic_seed_fails_closed(self):
        raw, coarse, fragments = fixture()
        cases = [raw.rsplit("QT",1)[0],
                 raw.replace("CN\t0\tt\t5\t+\t5", "CN\t0\tt\t5\t+\t3"),
                 raw.replace("CN\t0\tt\t5\t+\t5\t2", "CN\t0\tt\t4\t+\t4\t2")]
        gap = copy.deepcopy(fragments)
        gap[1]["query_start"] = 5
        for index, text in enumerate(cases):
            self.trace.write_text(text)
            with self.subTest(index=index), self.assertRaises(wa.ExperimentError):
                sw.reconstruct_sequential_splits(self.trace, coarse, fragments)
        self.trace.write_text(raw)
        with self.assertRaises(wa.ExperimentError):
            sw.reconstruct_sequential_splits(self.trace, coarse, gap)

    def test_identity_strand_geometry_and_fragment_bounds_are_strict(self):
        raw, coarse, fragments = fixture()
        self.trace.write_text(raw)
        mutations = []
        for key, value in (("query","other"),("target","other"),("query_length",13),
                           ("target_length",13),("strand","-")):
            changed = copy.deepcopy(fragments)
            changed[1][key] = value
            mutations.append(changed)
        changed = copy.deepcopy(fragments)
        changed[1]["target_start"] = changed[0]["target_start"]
        mutations.append(changed)
        for rows in mutations:
            with self.subTest(rows=rows), self.assertRaises(wa.ExperimentError):
                sw.reconstruct_sequential_splits(self.trace, coarse, rows)

    def test_count_score_and_fragment_limits_are_bounded(self):
        for score, counts in ((-1,[1,1]), (2**31,[1,1]), (1,[0,1]), (1,[1]),
                              (1,[1]*65), (1,[2**31,1]), (True,[1,1])):
            with self.subTest(score=score, count=len(counts)), self.assertRaises(wa.ExperimentError):
                sw.sequential_scores(score, counts)
        raw, coarse, fragments = fixture()
        self.trace.write_text(raw)
        with self.assertRaises(wa.ExperimentError):
            sw.reconstruct_sequential_splits(self.trace, coarse, fragments, max_fragments=2)

    def test_legacy_two_fragment_default_remains_explicit(self):
        raw, coarse, fragments = fixture()
        self.trace.write_text(raw)
        two = [{**fragments[0], "query_end":6, "target_end":6},
               {**fragments[2], "query_start":6, "target_start":6}]
        result = st.collect_split_counts(self.trace, coarse, two)
        self.assertEqual(result["fragment_anchor_counts"], [3,3])
        with self.assertRaisesRegex(wa.ExperimentError, "two fragments"):
            st.collect_split_counts(self.trace, coarse, fragments)


if __name__ == "__main__":
    unittest.main()
