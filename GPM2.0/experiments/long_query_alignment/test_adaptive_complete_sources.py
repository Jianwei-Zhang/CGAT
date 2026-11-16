import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adaptive_complete_sources as complete
import adaptive_screening as policy
import audit_adaptive_pilot as audit


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CompleteSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.query = self.root / "query.fa"; self.target = self.root / "target.fa"
        self.query.write_bytes(b">main\n" + b"A" * 1000 + b"\n>weak\n" + b"A" * 10 + b"\n")
        self.target.write_bytes(b">chr1\n" + b"A" * 2000 + b"\n")
        self.records = [{"name": "main", "length": 1000}, {"name": "weak", "length": 10}]
        self.workload = [*self.records, {"name": "ultralong", "length": policy.LONG_QUERY_LIMIT + 1}]
        self.report = self.root / "screening.json"
        self.catalogue = self.root / "catalogue.json"
        self.subset = self.root / "subset.json"
        # Source workload is not reread by the pilot finalizer; this unit fixture
        # explicitly models the complete catalogue + extraction content link.
        records = [{**r, "sequence_sha256": sha(b"A" * r["length"]), "n_bases": 0} for r in self.records]
        all_records = [*records, {**self.workload[-1], "sequence_sha256": "a" * 64, "n_bases": 0}]
        self.catalogue.write_text(json.dumps({"status": "complete", "decompressed_sha256": "b" * 64,
                                             "records": all_records}))
        self.subset.write_text(json.dumps({"status": "complete", "source_unchanged": True,
            "catalogue_sha256": sha(self.catalogue.read_bytes()), "source_decompressed_sha256": "b" * 64,
            "records": records, "output_sha256": sha(self.query.read_bytes())}))
        self.main = b"main\t1000\t0\t1000\t+\tchr1\t2000\t0\t1000\t1000\t1000\t60\tcg:Z:1000M\n"
        self.weak = b"weak\t10\t0\t10\t+\tchr1\t2000\t0\t10\t10\t10\t60\tcg:Z:10M\n"
        self.fixture()

    def fixture(self, speeds=(4, 5), *, fallback=True, repeats=2):
        runs = []
        for repeat in range(repeats):
            for fraction, speed in (("default", 1), ("0.005", speeds[0]), ("0.01", speeds[1])):
                data = self.main + (self.weak if fraction == "default" or not fallback else b"")
                path = self.root / f"r{repeat}-f{fraction}.paf"; path.write_bytes(data)
                runs.append({"repeat": repeat, "fraction": fraction, "outcome": "completed",
                    "wall_seconds": 100 / speed, "mid_occ": 500 if fraction == "default" else 50,
                    "paf_sha256": sha(data)})
        r = {"status": "screening_completed_not_production_acceptance", "input_content_unchanged": True,
             "policy": policy.POLICY, "runs": runs, "sources": {
                "query": {"source": str(self.query), "sha256": sha(self.query.read_bytes()), "records": self.records},
                "reference": {"source": str(self.target), "sha256": sha(self.target.read_bytes()),
                              "records": [{"name": "chr1", "length": 2000}]}}}
        self.report.write_text(json.dumps(r)); return r

    def decision(self, workload=None, **kwargs):
        return complete.choose(2000, self.workload if workload is None else workload,
                               self.records, audit.audit(self.report), **kwargs)

    def test_small_pilot_must_not_replace_the_full_workload_gate(self):
        self.assertEqual(policy.screening_gate(2000, self.records)["action"], "standard")
        result = self.decision()
        self.assertEqual(result["workload_gate"]["action"], "bounded_pilot")
        self.assertEqual(result["selected_filter"], "0.005")
        self.assertEqual([q["source"] for q in result["queries"]], ["candidate", "baseline"])
        self.assertFalse(result["hybrid_speedup_measured"])
        self.assertFalse(result["production_approved"])

    def test_normal_workload_keeps_standard_even_with_fast_pilot_candidate(self):
        result = self.decision(self.records)
        self.assertEqual(result["selected_filter"], "default")
        self.assertTrue(all(q["source"] == "baseline" for q in result["queries"]))

    def test_weaker_filter_is_preferred_not_the_fastest_filter(self):
        self.fixture(speeds=(2.1, 8), fallback=False)
        self.assertEqual(self.decision()["selected_filter"], "0.005")
        self.fixture(speeds=(1.99, 2.01))
        self.assertEqual(self.decision()["selected_filter"], "0.01")

    def test_one_fast_repeat_or_timeout_baseline_cannot_select(self):
        self.fixture(repeats=1)
        self.assertEqual(self.decision()["selected_filter"], "default")
        report = self.fixture()
        for row in report["runs"]:
            if row["fraction"] == "default":
                row.update(outcome="timeout", wall_budget_seconds=100)
                (self.root / f"r{row['repeat']}-fdefault.paf").write_bytes(b"BAD PARTIAL\n")
        self.report.write_text(json.dumps(report))
        self.assertEqual(self.decision()["selected_filter"], "default")
        with self.assertRaises((ValueError, KeyError)):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertFalse((self.root / "out/reference.selected.experimental.paf").exists())

    def test_review_is_bounded_by_both_count_and_positive_bases(self):
        for budget in (complete.ReviewBudget(0, 1), complete.ReviewBudget(32, 0.001)):
            with self.subTest(budget=budget):
                result = self.decision(budget=budget)
                self.assertEqual(result["selected_filter"], "default")
                self.assertTrue(all(c["reason"] == "finite_review_budget_exceeded" for c in result["candidates"]))

    def test_changed_repeat_does_not_seed_local_review(self):
        report = json.loads(self.report.read_text())
        for row in report["runs"]:
            if row["repeat"] == 1 and row["fraction"] != "default":
                path = self.root / f"r1-f{row['fraction']}.paf"
                path.write_bytes(self.main.replace(b"\t60\t", b"\t59\t"))
                row["paf_sha256"] = sha(path.read_bytes())
        self.report.write_text(json.dumps(report))
        self.assertEqual(self.decision()["selected_filter"], "default")

    def test_foreign_or_duplicate_pilot_records_are_rejected(self):
        with self.assertRaises(ValueError):self.decision([{"name": "foreign", "length": 1000}])
        with self.assertRaises(ValueError):
            complete.choose(2000, self.workload, self.records * 2, audit.audit(self.report))

    def test_threshold_edges_select_pilot_not_automatic_sensitivity(self):
        for ref, size, action in ((4999999999, 20000000, "standard"),
                                  (5000000000, 20000000, "bounded_pilot"),
                                  (2000, policy.LONG_QUERY_LIMIT, "standard"),
                                  (2000, policy.LONG_QUERY_LIMIT + 1, "bounded_pilot")):
            gate = policy.screening_gate(ref, [{"name": "q", "length": size}])
            self.assertEqual(gate["action"], action)
            self.assertFalse(gate["automatic_sensitivity_change"])

    def test_materialization_selects_exactly_one_whole_source_and_keeps_inputs(self):
        originals = {p: p.read_bytes() for p in self.root.glob("*") if p.is_file()}
        with patch("subprocess.Popen", side_effect=AssertionError("must not map")):
            result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.main + self.weak)
        self.assertEqual(result["decision"]["selected_filter"], "0.005")
        self.assertEqual([q["filter"] for q in result["queries"]], ["0.005", "default"])
        self.assertEqual([q["source_rows"] for q in result["queries"]], [[1], [2]])
        self.assertEqual(result["output_rows"], 2)
        self.assertTrue(result["quality"]["passed"])
        self.assertFalse(result["per_query_sources_combined"])
        self.assertFalse(result["whole_workload_source_revalidated"])
        for p, data in originals.items():self.assertEqual(p.read_bytes(), data)
        self.assertFalse((self.root / "out/result.paf").exists())
        with self.assertRaises(FileExistsError):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")

    def test_changed_source_or_subset_link_refuses_without_final_output(self):
        original = self.query.read_bytes()
        self.query.write_bytes(original.replace(b"A", b"C", 1))
        with self.assertRaisesRegex(ValueError, "source content changed"):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "changed")
        self.assertFalse((self.root / "changed/reference.selected.experimental.paf").exists())
        self.query.write_bytes(original)
        subset = json.loads(self.subset.read_text()); subset["source_decompressed_sha256"] = "0" * 64
        self.subset.write_text(json.dumps(subset))
        with self.assertRaisesRegex(ValueError, "contradicts"):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "foreign")

    def test_completed_but_corrupted_paf_is_not_silently_rebuilt(self):
        path = self.root / "r0-f0.005.paf"; path.write_bytes(b"corrupt\n")
        with patch("subprocess.Popen", side_effect=AssertionError("no retry")), self.assertRaises(ValueError):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(path.read_bytes(), b"corrupt\n")
        self.assertFalse((self.root / "out/reference.selected.experimental.paf").exists())

    def test_source_mutation_during_output_cannot_publish(self):
        validate = complete.validator.validate_paf
        def mutate(path, *args, **kwargs):
            result = validate(path, *args, **kwargs)
            if Path(path).name == "reference.selected.pending.paf":
                self.query.write_bytes(self.query.read_bytes() + b"\n")
            return result
        with patch.object(complete.validator, "validate_paf", side_effect=mutate), self.assertRaises(ValueError):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertFalse((self.root / "out/reference.selected.experimental.paf").exists())

    def test_multiple_rows_and_strands_keep_their_source_order(self):
        extra = self.main.replace(b"\t+\t", b"\t-\t").replace(b"\t0\t1000\t1000\t1000\t", b"\t1000\t2000\t1000\t1000\t")
        report = self.fixture(fallback=False)
        for row in report["runs"]:
            path = self.root / f"r{row['repeat']}-f{row['fraction']}.paf"
            # Interleaved source query order deliberately differs from catalogue.
            path.write_bytes(extra + self.weak + self.main)
            row["paf_sha256"] = sha(path.read_bytes())
        self.report.write_text(json.dumps(report))
        result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(Path(result["output_path"]).read_bytes(), extra + self.main + self.weak)
        self.assertEqual(result["queries"][0]["source_rows"], [1, 3])
        self.assertEqual(result["output_rows"], 3)

    def test_partial_candidate_is_ignored_without_losing_completed_alternative(self):
        report = self.fixture()
        for row in report["runs"]:
            if row["fraction"] == "0.005":
                row.update(outcome="timeout", wall_budget_seconds=100)
                (self.root / ("r%d-f0.005.paf" % row["repeat"])).write_bytes(b"BAD PARTIAL\n")
        self.report.write_text(json.dumps(report))
        result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(result["decision"]["selected_filter"], "0.01")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.main + self.weak)
        self.assertNotIn("r0-f0.005.paf", {Path(p).name for p in result["guarded_sources_sha256"]})

    def test_completed_no_hit_record_remains_explicit_without_invented_rows(self):
        report = self.fixture(fallback=False)
        for row in report["runs"]:
            path = self.root / ("r%d-f%s.paf" % (row["repeat"], row["fraction"]))
            path.write_bytes(self.main); row["paf_sha256"] = sha(self.main)
        self.report.write_text(json.dumps(report))
        result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.main)
        self.assertEqual(result["queries"][1]["query"], "weak")
        self.assertEqual(result["queries"][1]["output_rows"], 0)
        self.assertEqual(result["queries"][1]["record_output_sha256"], sha(b""))

    def test_receipt_read_and_hash_cannot_bind_different_snapshots(self):
        read = complete._json
        def changed_after_read(path, *args, **kwargs):
            result = read(path, *args, **kwargs)
            if path == self.report:
                value = json.loads(path.read_text()); value["changed_after_parse"] = True
                path.write_text(json.dumps(value))
            return result
        with patch.object(complete, "_json", side_effect=changed_after_read), self.assertRaisesRegex(ValueError, "between parsing"):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertFalse((self.root / "out/reference.selected.experimental.paf").exists())

    def test_nested_subset_uses_content_membership_not_incidental_parent_link(self):
        subset = json.loads(self.subset.read_text())
        subset.update(catalogue_sha256="c" * 64, source_decompressed_sha256="d" * 64)
        self.subset.write_text(json.dumps(subset))
        result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertFalse(result["direct_catalogue_link_matches"])
        self.assertEqual(result["workload_membership_verified_by"], "fresh_complete_record_sequence_digests")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.main + self.weak)

    def test_forged_matching_lengths_and_file_hashes_cannot_replace_sequence_content(self):
        self.query.write_bytes(self.query.read_bytes().replace(b"A", b"C", 1))
        report = json.loads(self.report.read_text())
        report["sources"]["query"]["sha256"] = sha(self.query.read_bytes())
        self.report.write_text(json.dumps(report))
        subset = json.loads(self.subset.read_text()); subset["output_sha256"] = sha(self.query.read_bytes())
        self.subset.write_text(json.dumps(subset))
        with self.assertRaisesRegex(ValueError, "sequence content"):
            complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertFalse((self.root / "out/reference.selected.experimental.paf").exists())

    def test_completed_second_baseline_survives_first_baseline_timeout(self):
        report = self.fixture()
        for row in report["runs"]:
            if row["fraction"] == "default" and row["repeat"] == 0:
                row.update(outcome="timeout", wall_budget_seconds=100)
                (self.root / "r0-fdefault.paf").write_bytes(b"BAD PARTIAL\n")
        self.report.write_text(json.dumps(report))
        result = complete.materialize(self.report, self.catalogue, self.subset, self.root / "out")
        self.assertEqual(result["decision"]["selected_filter"], "default")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.main + self.weak)
        self.assertTrue(all(Path(q["source_path"]).name == "r1-fdefault.paf" for q in result["queries"]))
        self.assertNotIn("r0-fdefault.paf", {Path(p).name for p in result["guarded_sources_sha256"]})


if __name__ == "__main__":unittest.main()
