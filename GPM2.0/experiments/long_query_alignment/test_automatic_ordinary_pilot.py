"""Ordinary automatic pilot gates, immutable input units and real native resume."""
import argparse
from dataclasses import replace
import gzip
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import automatic_ordinary_pilot as pilot
import minimap_index_context as mic
import native_first as nf
import proactive_reference_plan as pp
import windowed_alignment as wa


class PlanningTests(unittest.TestCase):
    def records(self):
        return ([{"name": "long-%03d" % n, "length": 80000000} for n in range(160)]
                + [{"name": "medium", "length": 20000000}, {"name": "small", "length": 3000000},
                   {"name": "weak", "length": 500000}, {"name": "ultralong", "length": 300000000}])

    def test_base_weighted_representative_and_complete_record_amortization(self):
        r = pilot.plan(14500000000, self.records())
        self.assertTrue(r["enabled"])
        self.assertEqual([x["length"] for x in r["pilot_records"]], [80000000, 20000000, 3000000, 500000])
        self.assertGreaterEqual(r["workload_to_pilot_bases"], 64)
        self.assertNotIn("ultralong", [x["name"] for x in r["ordinary_records"]])
        self.assertFalse(r["sensitivity_changed"])
        self.assertFalse(r["whole_workload_performance_predicted"])

    def test_large_reference_alone_does_not_spend_a_pilot(self):
        r = pilot.plan(14500000000, self.records()[-4:-1])
        self.assertFalse(r["enabled"])
        self.assertEqual(r["reason"], "insufficient_large_ordinary_workload")

    def test_explicit_filter_is_not_overridden(self):
        r = pilot.plan(14500000000, self.records(), explicit_filter="0.02")
        self.assertEqual(r["reason"], "explicit_filter_preserved")
        self.assertFalse(r["enabled"])

    def test_size_threshold_does_not_override_amortization(self):
        r = pilot.plan(14500000000, self.records()[:20])
        self.assertFalse(r["enabled"])
        self.assertEqual(r["reason"], "pilot_cost_not_amortizable_by_workload_size")

    def test_dominant_record_cannot_be_replaced_with_convenient_small_records(self):
        records = [{"name": str(n), "length": 200000000} for n in range(100)] + self.records()[-4:-1]
        r = pilot.plan(14500000000, records)
        self.assertEqual(r["reason"], "representative_complete_record_exceeds_pilot_cap")

    def test_invalid_budgets_and_duplicate_inputs_fail(self):
        for budget in (replace(pilot.Budget(), total_seconds=0), replace(pilot.Budget(), minimum_speedup=float("nan")),
                       replace(pilot.Budget(), review_fraction=2)):
            with self.assertRaises(ValueError):pilot.plan(1, self.records(), budget=budget)
        with self.assertRaises(ValueError):pilot.plan(1, [{"name": "q", "length": 2}] * 2)


class CompleteTraversalTests(unittest.TestCase):
    def test_equal_grand_total_cannot_hide_an_omitted_second_part(self):
        text = ("loaded/built the index for 12 target sequence(s)\n"
                "[M::worker_pipeline::1.2*2] mapped 8 sequences\n"
                "loaded/built the index for 10 target sequence(s)\n")
        with self.assertRaisesRegex(wa.ExperimentError, "part/query traversal"):
            pilot._complete_traversal(text, [12, 10], 4)

    def test_multiple_batches_are_counted_within_each_original_part(self):
        text = ("loaded/built the index for 12 target sequence(s)\n"
                "[M::worker_pipeline::1.2*2] mapped 1 sequences\n"
                "[M::worker_pipeline::1.5*2] mapped 3 sequences\n"
                "loaded/built the index for 10 target sequence(s)\n"
                "[M::worker_pipeline::2.0*2] mapped 4 sequences\n")
        pilot._complete_traversal(text, [12, 10], 4)
        with self.assertRaisesRegex(wa.ExperimentError, "precedes"):
            pilot._complete_traversal("[M::worker_pipeline::1*1] mapped 4 sequences", [12], 4)


class CompleteInputTests(unittest.TestCase):
    def test_plain_and_gzip_preserve_original_complete_bytes_and_reuse(self):
        raw = b">a description\naCgT\n>second\nAAAA\nTT\n>third\nGGGG\n"
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / "input.fa"
                source.write_bytes(gzip.compress(raw) if compressed else raw)
                catalog = pp.scan_query(source)
                output = root / "unit.fa"
                first = pilot.materialize(catalog, ["a", "third"], output)
                self.assertEqual(output.read_bytes(), b">a description\naCgT\n>third\nGGGG\n")
                before = output.stat().st_mtime_ns
                again = pilot.materialize(catalog, ["a", "third"], output)
                self.assertEqual(first, again); self.assertEqual(output.stat().st_mtime_ns, before)
                output.write_bytes(output.read_bytes().replace(b"GGGG", b"TTTT"))
                with self.assertRaisesRegex(wa.ExperimentError, "unit changed"):
                    pilot.materialize(catalog, ["a", "third"], output)

    def test_reordered_or_mutated_input_is_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "input.fa"; source.write_bytes(b">a\nAAAA\n>b\nCCCC\n")
            catalog = pp.scan_query(source)
            with self.assertRaises(ValueError):pilot.materialize(catalog, ["b", "a"], root / "unit.fa")
            source.write_bytes(b">a\nTTTT\n>b\nCCCC\n")
            with self.assertRaises(pp.PlanError):pilot.materialize(catalog, ["a"], root / "unit.fa")


class ActualNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm = os.environ.get("CGAT_MINIMAP2_BINARY")
        if not cls.mm:raise unittest.SkipTest("explicit pinned minimap2 required")

    def fixture(self, root, *, nohit=False):
        rng = random.Random(2311302); sequence = bytes(rng.choices(b"ACGT", k=160000))
        ref = root / "ref.fa"; ref.write_bytes(b">ref\n" + sequence + b"\n")
        query = root / "queries.fa"
        query.write_bytes(b"".join((">q%02d\n" % n).encode() + (b"N" * 90000 if nohit == "all" or nohit and n == 2 else sequence[n*100:n*100+90000]) + b"\n" for n in range(20)))
        catalog = pp.scan_query(query)
        budget = pilot.Budget(reference_bases=100000, workload_bases=1000000, long_ordinary_bases=20000,
                              pilot_bases=400000, minimum_workload_multiple=4, minimum_speedup=1e6,
                              case_seconds=20, total_seconds=120)
        plan = pilot.plan(160000, [{"name": r.name, "length": r.length} for r in catalog.records], budget=budget)
        self.assertTrue(plan["enabled"])
        unit = pilot.materialize(catalog, [r["name"] for r in plan["pilot_records"]], root / "pilot.fa")
        target = root / "target.mmi"
        wa.run_command([self.mm, "-x", "asm10", "-t", "2", "-d", str(target), str(ref)], root, "index", 30, 2)
        index = {**mic.read_catalog(target), "path": str(target), "sha256": wa.sha256(target)}
        tool = {"path": self.mm, "sha256": wa.sha256(Path(self.mm))}
        args = argparse.Namespace(threads=2, memory_gib=2)
        return plan, unit, index, tool, args

    def test_actual_completed_sources_resume_without_remapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            with patch.object(nf, "attempt", wraps=nf.attempt) as commands:first = pilot.execute(out, *inputs)
            self.assertEqual(first["selected_filter"], "default"); self.assertEqual(commands.call_count, 3)
            selected = pilot.materialize_selection(out, first, inputs[0]["pilot_records"])
            self.assertEqual(len(selected["queries"]), 4)
            self.assertTrue(all(r["source"] == "baseline" for r in selected["queries"]))
            before = [(p, p.stat().st_mtime_ns) for p in out.glob("*/native.complete.paf")]
            # Stale cheap profiles are not an admission cache.
            state = json.loads((out / pilot.STATE).read_text()); state["cases"]["baseline-0"]["profile"] = {"stale": True}
            wa.write_json(out / pilot.STATE, state)
            with patch.object(nf, "attempt", side_effect=AssertionError("completed native source remapped")):
                again = pilot.execute(out, *inputs)
            self.assertEqual(again, first)
            self.assertEqual(pilot.materialize_selection(out, again, inputs[0]["pilot_records"]), selected)
            self.assertTrue(all(p.stat().st_mtime_ns == stamp for p, stamp in before))

    def test_cancelled_pilot_preserves_baseline_and_does_not_retry_failed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            native = nf.attempt
            def cancel(*args, **kwargs):
                if args[4].minimap_filter == "0.005":raise KeyboardInterrupt("controlled cancellation")
                return native(*args, **kwargs)
            with patch.object(nf, "attempt", side_effect=cancel):
                with self.assertRaises(KeyboardInterrupt):pilot.execute(out, *inputs)
            baseline = out / "baseline-0/native.complete.paf"; saved = wa.sha256(baseline)
            with patch.object(nf, "attempt", wraps=nf.attempt) as commands:result = pilot.execute(out, *inputs)
            self.assertEqual(commands.call_count, 1)
            self.assertEqual(commands.call_args.args[4].minimap_filter, "0.01")
            self.assertEqual(wa.sha256(baseline), saved)
            self.assertEqual(result["selected_filter"], "default")

    def test_changed_completed_paf_is_rejected_without_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            pilot.execute(out, *inputs)
            path = out / "baseline-0/native.complete.paf"; path.write_bytes(path.read_bytes() + b"BAD\n")
            with patch.object(nf, "attempt", side_effect=AssertionError("unexpected remapping")):
                with self.assertRaisesRegex(wa.ExperimentError, "bytes changed"):pilot.execute(out, *inputs)

    def test_hard_kill_after_native_completion_recovers_receipt_without_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            first = pilot.execute(out, *inputs)
            state = json.loads((out / pilot.STATE).read_text()); old_spent = state["spent_seconds"]
            state["cases"]["baseline-0"]["status"] = "started"
            wa.write_json(out / pilot.STATE, state)
            with patch.object(nf, "attempt", side_effect=AssertionError("hard-kill recovery remapped")):
                again = pilot.execute(out, *inputs)
            self.assertEqual(first, again)
            changed = json.loads((out / pilot.STATE).read_text())
            self.assertGreaterEqual(changed["spent_seconds"], old_spent + 25)

    def test_controlled_timing_pair_selects_weakest_candidate_without_stronger_trials(self):
        # Actual PAFs/commands, SYNTHETIC times: this is decision coverage, not a
        # scientific performance measurement or a claimed real speedup.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = list(self.fixture(root)); out = root / "calibration"
            budget = pilot.Budget(**inputs[0]["budget"])
            inputs[0] = pilot.plan(160000, inputs[0]["ordinary_records"], budget=replace(budget, minimum_speedup=2.0))
            verify = pilot._verify_case
            def timing(*args, **kwargs):
                result = verify(*args, **kwargs)
                result["wall_seconds"] = 10 if args[6] is None else 2
                return result
            with patch.object(pilot, "_verify_case", side_effect=timing), patch.object(nf, "attempt", wraps=nf.attempt) as commands:
                result = pilot.execute(out, *inputs)
            self.assertEqual(result["selected_filter"], "0.005")
            self.assertEqual(commands.call_count, 4)
            self.assertTrue(all(c.args[4].minimap_filter != "0.01" for c in commands.call_args_list))
            selected = pilot.materialize_selection(out, result, inputs[0]["pilot_records"])
            self.assertTrue(all(r["source"] == "candidate" for r in selected["queries"]))
            self.assertFalse(selected["whole_workload_approved"])

    def test_complete_no_hit_query_is_explicit_in_selected_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root, nohit=True); out = root / "calibration"
            result = pilot.execute(out, *inputs)
            selected = pilot.materialize_selection(out, result, inputs[0]["pilot_records"])
            row = next(r for r in selected["queries"] if r["query"] == "q02")
            self.assertEqual(row["rows"], 0); self.assertTrue(row["complete_no_hit"])

    def test_input_mutation_after_decision_blocks_selected_source_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            result = pilot.execute(out, *inputs)
            source = Path(inputs[1]["path"]); source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(wa.ExperimentError, "pilot input changed"):
                pilot.materialize_selection(out, result, inputs[0]["pilot_records"])
            self.assertFalse((out / "pilot.selected.paf").exists())

    def test_controlled_review_uses_one_whole_source_not_baseline_plus_candidate(self):
        # Synthetic time/profile controls test source composition, not real loss.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = list(self.fixture(root)); out = root / "calibration"
            budget = replace(pilot.Budget(**inputs[0]["budget"]), minimum_speedup=2.0, review_fraction=.3)
            inputs[0] = pilot.plan(160000, inputs[0]["ordinary_records"], budget=budget)
            verify = pilot._verify_case
            def controlled(*args, **kwargs):
                result = verify(*args, **kwargs)
                result["wall_seconds"] = 10 if args[6] is None else 2
                if args[6] is not None:
                    row = result["profile"]["q00"]
                    row.update(covered=0, targets={}, target_strands={}, assignment_candidates={})
                return result
            with patch.object(pilot, "_verify_case", side_effect=controlled):result = pilot.execute(out, *inputs)
            self.assertEqual(result["selected_filter"], "0.005")
            selected = pilot.materialize_selection(out, result, inputs[0]["pilot_records"])
            decisions = {r["query"]: r["source"] for r in selected["queries"]}
            self.assertEqual(decisions, {"q00": "baseline", "q01": "candidate", "q02": "candidate", "q09": "candidate"})
            expected = b""
            for query, name in decisions.items():
                expected += b"".join(line for line in Path(result[name]["path"]).read_bytes().splitlines(keepends=True)
                                     if line.split(b"\t", 1)[0].decode() == query)
            self.assertEqual(Path(selected["path"]).read_bytes(), expected)

    def test_negative_resume_budget_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root); out = root / "calibration"
            pilot.execute(out, *inputs)
            state = json.loads((out / pilot.STATE).read_text()); state["spent_seconds"] = -1
            wa.write_json(out / pilot.STATE, state)
            with patch.object(nf, "attempt", side_effect=AssertionError("invalid budget remapped")):
                with self.assertRaisesRegex(wa.ExperimentError, "budget ledger changed"):pilot.execute(out, *inputs)

    def test_actual_timeout_preserves_partial_without_profile_or_automatic_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = list(self.fixture(root)); out = root / "calibration"
            budget = replace(pilot.Budget(**inputs[0]["budget"]), case_seconds=1)
            inputs[0] = pilot.plan(160000, inputs[0]["ordinary_records"], budget=budget)
            fake = root / "fake-mm-for-timeout.sh"
            fake.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo 2.31-r1302; exit 0; fi\nwhile [ "$#" -gt 0 ]; do if [ "$1" = "-o" ]; then shift; printf partial > "$1"; fi; shift; done\nsleep 10\n')
            fake.chmod(0o755); inputs[3] = {"path": str(fake), "sha256": wa.sha256(fake)}
            result = pilot.execute(out, *inputs)
            self.assertEqual(result["status"], "incomplete_no_baseline")
            self.assertEqual((out / "baseline-0/native.partial.paf").read_bytes(), b"partial")
            self.assertIsNone(json.loads((out / pilot.STATE).read_text())["decision"])
            with patch.object(nf, "attempt", side_effect=AssertionError("failed pilot rerun")):
                again = pilot.execute(out, *inputs)
            self.assertEqual(again["status"], "incomplete_no_baseline")
            with self.assertRaisesRegex(wa.ExperimentError, "current verified decision"):
                pilot.materialize_selection(out, again, inputs[0]["pilot_records"])

    def test_uninformative_complete_baseline_does_not_spend_filter_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = self.fixture(root, nohit="all"); out = root / "calibration"
            with patch.object(nf, "attempt", wraps=nf.attempt) as commands:result = pilot.execute(out, *inputs)
            self.assertEqual(commands.call_count, 1)
            self.assertEqual(result["reason"], "baseline_uninformative_no_filter_trials")
            selected = pilot.materialize_selection(out, result, inputs[0]["pilot_records"])
            self.assertTrue(all(row["complete_no_hit"] for row in selected["queries"]))
