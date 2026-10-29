"""Selection diagnostics must not become a guessed recovery/ranking algorithm."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import audit_post_dp as audit
import windowed_alignment as wa


class PostDpAuditTests(unittest.TestCase):
    def test_score_parser_requires_real_dp_and_chain_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.paf"
            row = "q\t10\t0\t10\t+\texact\t10\t0\t10\t10\t10\t60\ttp:A:P\ts1:i:10\tAS:i:10\tcm:i:1\tcg:Z:10=\n"
            path.write_text(row)
            self.assertEqual(audit.read_paf(path, True)[0]["alignment_score"], 10)
            for changed in (row.replace("\ts1:i:10", ""), row.replace("\tAS:i:10", ""),
                            row.replace("\tcg:Z:10=", ""), row.strip()+"\tAS:i:11\n", ""):
                path.write_text(changed)
                with self.assertRaises(wa.ExperimentError):
                    audit.read_paf(path, True)

    def test_seed_witness_refuses_missing_ambiguous_or_inconsistent_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.stderr"
            raw = "QR\tq\t0\t10\n" + "".join(f"CN\t1\tdecoy\t{i}\t+\t{i}\t2\t0\n" for i in (1, 3, 5, 7, 9))
            coarse = {"query": "q", "query_length": 10, "target": "decoy", "target_length": 10,
                      "strand": "+", "query_start": 0, "query_end": 10, "target_start": 0, "target_end": 10,
                      "minimizers": 5, "chain_score": 100}
            parts = [{**coarse, "query_end": 6, "target_end": 6, "minimizers": 3, "chain_score": 60, "alignment_score": 70},
                     {**coarse, "query_start": 6, "target_start": 6, "minimizers": 2, "chain_score": 40, "alignment_score": 50}]
            path.write_text(raw)
            result = audit.split_score_witness(path, [coarse], parts)
            self.assertEqual(result["reconstructed_chain_scores"], [60, 40])
            self.assertFalse(result["candidate_selection_reconstructed"])
            self.assertFalse(result["mapq_reconstructed"])
            for bad in (raw.replace("CN\t1\tdecoy\t5\t+\t5\t2\t0\n", ""),
                        raw+raw, raw.replace("QR\tq", "QR\tother"), raw+"CN\tbad\n"):
                path.write_text(bad)
                with self.assertRaises(wa.ExperimentError):
                    audit.split_score_witness(path, [coarse], parts)
            path.write_text(raw)
            wrong = copy.deepcopy(parts)
            wrong[0]["chain_score"] = 61
            with self.assertRaisesRegex(wa.ExperimentError, "scores do not match"):
                audit.split_score_witness(path, [coarse], wrong)
            wrong = copy.deepcopy(parts)
            wrong[0]["minimizers"] = 4
            with self.assertRaisesRegex(wa.ExperimentError, "seed counts"):
                audit.split_score_witness(path, [coarse], wrong)
            with self.assertRaises(wa.ExperimentError):
                audit.split_score_witness(path, [{**coarse, "strand": "-"}], parts)
            path.write_text(raw.replace("QR\tq\t0\t10", "QR\tq\t0\t9"))
            with self.assertRaisesRegex(wa.ExperimentError, "sequence bounds"):
                audit.split_score_witness(path, [{**coarse, "query_length": 9}], [{**r, "query_length": 9} for r in parts])

    @unittest.skipUnless(shutil.which("minimap2"), "real minimap2 unavailable")
    def test_real_as_only_counterexample_and_original_seed_split_score(self):
        with tempfile.TemporaryDirectory() as temp:
            args = argparse.Namespace(out=Path(temp) / "audit", minimap2=shutil.which("minimap2"))
            result = audit.experiment(args)
            self.assertFalse(result["new_candidate_filter_implemented"])
            self.assertFalse(result["production_ready"])
            cases = {c["case"]: c for c in result["cases"]}
            self.assertTrue(cases["identity"]["as_only_probe"]["matches_baseline"])
            self.assertTrue(cases["identity"]["guided_final_exists"])
            self.assertTrue(cases["split_decoy"]["as_only_probe"]["matches_baseline"])
            for name in ("split_decoy", "chain_score_not_alignment_score"):
                case = cases[name]
                self.assertEqual(case["guidance_status"], "failed")
                self.assertIn("not completely recovered", case["guidance_error"])
                self.assertFalse(case["guided_final_exists"])
            case = cases["chain_score_not_alignment_score"]
            self.assertTrue(any(r["target"] == "decoy" for r in case["runs"]["chains"]))
            probe = case["as_only_probe"]
            self.assertFalse(probe["matches_baseline"])
            self.assertTrue(probe["false_positives"])
            for row in probe["false_positives"]:
                self.assertEqual(row["target"], "decoy")
                self.assertGreaterEqual(row["alignment_score"], probe["as_threshold"])
                self.assertLess(row["chain_score"], probe["post_dp_chain_score_threshold_for_exact_parent"])
            witness = case["seed_trace_witness"]
            self.assertEqual(sum(witness["fragment_anchor_counts"]), witness["original_anchor_count"])
            self.assertEqual(witness["reconstructed_chain_scores"], witness["reported_dp_chain_scores"])
            pool = case["window_pool_witness"]
            self.assertTrue(pool["pool_path_relations_equal"])
            self.assertTrue(pool["recovered_scores_equal_oracle"])
            self.assertTrue(pool["threshold_illustration_matches_baseline"])
            self.assertFalse(pool["general_parent_selection_implemented"])
            self.assertFalse(pool["mapq_reconstructed"])
            self.assertTrue(all(r["mapq"] == 255 for r in pool["rows"]))
            with self.assertRaises(FileExistsError):
                audit.experiment(args)


if __name__ == "__main__":
    unittest.main()
