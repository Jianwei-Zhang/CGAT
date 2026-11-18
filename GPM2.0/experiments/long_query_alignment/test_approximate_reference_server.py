"""Actual pinned-tool automatic Server entry and substage-resume controls."""
import json
import os
import random
import signal
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import approximate_reference_cells as ap
import native_chain_state as nst
import native_first as nf
import server_alignment as sa
import selective_reference_alignment as sr
import test_proactive_resume as old
import windowed_alignment as wa


class AutomaticServerTests(old.RealResumeTests):
    # Reuse only fixture/controls, not inherited test methods: this class is
    # collected below with explicit locally declared tests.
    def automatic_fixture(self, root):
        runtime, args = self.fixture(root)
        manifest = json.loads((runtime / sa.MANIFEST).read_text())
        manifest["approximate_output_admission"] = ap.POLICY
        wa.write_json(runtime / sa.MANIFEST, manifest)
        return runtime, args

    def automatic_controls(self):
        stack = self.controls()
        stack.enter_context(patch.object(ap, "MIN_REFERENCE_BASES", 100000))
        stack.enter_context(patch.object(ap, "CORE_BASES", 20000))
        stack.enter_context(patch.object(ap, "CONTEXT_BASES", 4000))
        stack.enter_context(patch.object(nst, "validate_bundle", side_effect=AssertionError("approximation must not invoke native companion")))
        return stack

    def test_automatic_entry_publishes_unknown_confidence_and_resumes_without_mapper(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            with self.automatic_controls():
                first = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(first["result_published"])
            self.assertEqual(first["initial_reference_policy"], ap.POLICY)
            self.assertEqual(first["approximate_query_part_cells"], 2)
            self.assertFalse(first["recovered_native_confidence_published"])
            data = (args.run_dir / "result.paf").read_bytes()
            for line in data.decode().splitlines():
                fields = line.split("\t")
                if fields[0].startswith("long"):
                    self.assertEqual(fields[1], "90000"); self.assertEqual(fields[11], "255")
                    self.assertFalse({tag.split(":", 1)[0] for tag in fields[12:]} & {"AS","ms","s1","s2","cm","tp"})
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=AssertionError("unexpected mapper rerun")):
                resumed = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(resumed["attempt_reused"])
            self.assertEqual(resumed["cache_reused"]["ordinary_group"], 1)
            self.assertEqual(resumed["cache_reused"]["long_cells"], 2)
            self.assertEqual((args.run_dir / "result.paf").read_bytes(), data)

    def interrupted(self, stage):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            with self.automatic_controls(), patch.object(wa, stage, side_effect=KeyboardInterrupt("controlled postprocessing cancellation")):
                with self.assertRaises(KeyboardInterrupt):sa.run_reference(args, runtime_root=runtime)
            self.assertFalse((args.run_dir / "result.paf").exists())
            attempt = next(args.run_dir.glob(".long-cigar-attempt-*"))
            cell = next((attempt / "selective").glob("**/" + ap.MANIFEST))
            state = json.loads(cell.read_text()); self.assertIn("raw", state)
            if stage == "stitch_owned":self.assertIn("owned", state)
            raw = cell.parent / "raw.windows.paf"; before = (wa.sha256(raw), raw.stat().st_mtime_ns)
            run = wa.run_command; mapped = []
            def commands(command, *a, **kw):
                if "-o" in command and command[command.index("-o") + 1] == str(raw):
                    raise AssertionError("completed raw mapping was repeated")
                mapped.append(command); return run(command, *a, **kw)
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=commands):
                result = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(result["result_published"])
            self.assertEqual((wa.sha256(raw), raw.stat().st_mtime_ns), before)
            self.assertEqual(len(mapped), 1)  # only the second missing long cell
            updated = json.loads(cell.read_text())
            self.assertTrue(updated["last_invocation"]["reused"]["mapping"])
            self.assertEqual(updated["last_invocation"]["reused"]["ownership"], stage == "stitch_owned")

    def test_raw_mapping_survives_recovery_cancellation(self):self.interrupted("recover")
    def test_owned_output_survives_stitch_cancellation(self):self.interrupted("stitch_owned")

    def test_corrupted_complete_cell_is_refused_without_mapping_or_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            with self.automatic_controls():first = sa.run_reference(args, runtime_root=runtime)
            cell = next((Path(first["attempt"]) / "selective").glob("**/" + ap.MANIFEST))
            raw = cell.parent / "raw.windows.paf"; raw.write_bytes(raw.read_bytes() + b"CORRUPT\n")
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=AssertionError("no corrupt-source rebuild")):
                with self.assertRaises(wa.ExperimentError):sa.run_reference(args, runtime_root=runtime)
            self.assertFalse((args.run_dir / "result.paf").exists())
            self.assertTrue(raw.read_bytes().endswith(b"CORRUPT\n"))

    def test_bounded_native_review_replaces_whole_record_and_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            screen = ap.screen_group
            def request_review(root, name, *a, **kw):
                result = screen(root, name, *a, **kw)
                if name == "long1":result["approved"] = False
                return result
            with self.automatic_controls(), patch.object(ap, "screen_group", side_effect=request_review):
                first = sa.run_reference(args, runtime_root=runtime)
            report = json.loads((Path(first["attempt"]) / "selective/proactive-candidate.json").read_text())
            self.assertEqual([r["query"] for r in report["native_reviews"]], ["long1"])
            self.assertEqual(first["approximate_query_part_cells"], 1)
            final = (args.run_dir / "result.paf").read_bytes()
            review = Path(report["native_reviews"][0]["native"]["path"]).read_bytes()
            self.assertEqual(b"".join(line for line in final.splitlines(keepends=True) if line.startswith(b"long1\t")), review)
            # Completed authoritative review takes priority even over a damaged,
            # now-unused approximate candidate. No mapper or companion is needed.
            discarded = next(r for r in report["parts"] if r["query"] == "long1")
            Path(discarded["path"]).write_bytes(b"unused candidate changed\n")
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=AssertionError("completed review was repeated")):
                second = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(second["result_published"])
            self.assertEqual((args.run_dir / "result.paf").read_bytes(), final)

    def test_primary_windows_and_required_review_ignore_exploratory_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            screen, command, native = ap.screen_group, wa.run_command, nf.attempt
            maps, reviews = [], []
            def request_review(root, name, *a, **kw):
                result = screen(root, name, *a, **kw)
                if name == "long1":result["approved"] = False
                return result
            def mapped(argv, folder, name, timeout, memory, **kw):
                if name == "map":maps.append((timeout, memory, kw.get("max_file_bytes")))
                return command(argv, folder, name, timeout, memory, **kw)
            def reviewed(mm, target, query, root, options, **kw):
                if root.name == "native-quality-review":
                    reviews.append((options.timeout, options.memory_gib, options.max_output_bytes))
                return native(mm, target, query, root, options, **kw)
            with self.automatic_controls(), patch.object(ap, "screen_group", side_effect=request_review), \
                 patch.object(ap, "MAP_SECONDS", 1), patch.object(ap, "MAX_PAF_BYTES", 1), \
                 patch.object(ap, "REVIEW_SECONDS", 1), patch.object(ap, "TOTAL_REVIEW_SECONDS", 0), \
                 patch.object(ap, "deadline", side_effect=AssertionError("production used exploratory deadline")), \
                 patch.object(wa, "run_command", side_effect=mapped), patch.object(nf, "attempt", side_effect=reviewed):
                result = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(result["result_published"])
            self.assertEqual(maps, [(None, 0, None), (None, 0, None)])
            self.assertEqual(reviews, [(None, 0, None)])
            states = list((Path(result["attempt"])/"selective").glob("long-*/part-*/" + ap.MANIFEST))
            self.assertEqual(len(states), 2)
            for path in states:
                resources = json.loads(path.read_text())["last_invocation"]
                self.assertTrue(resources["primary_work"])
                self.assertIsNone(resources["cell_budget_seconds"])
                self.assertIsNone(resources["mapper_output_limit_bytes"])

    def test_experimental_review_stays_bounded_and_primary_respects_explicit_limits(self):
        from types import SimpleNamespace
        from contextlib import nullcontext
        for primary in (False, True):
            with self.subTest(primary=primary), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); calls=[]
                args=SimpleNamespace(timeout=75,memory_gib=48,minimap_filter=None)
                group={"sha256":"a"*64,"path":str(root/"q.fa"),"queries":["q"]}
                index={"sha256":"b"*64,"path":str(root/"r.mmi")};tool={"sha256":"c"*64,"path":"fixture-only"}
                def failed(mm,target,query,destination,options):
                    calls.append((options.timeout,options.memory_gib,options.max_output_bytes))
                    return {"status":"other_failure"}
                with patch.object(nf,"attempt",side_effect=failed), patch.object(ap,"deadline",side_effect=lambda seconds:nullcontext()) as clock:
                    with self.assertRaisesRegex(wa.ExperimentError,"did not complete"):
                        ap.native_review(root,group,index,tool,args,seconds=25,primary_work=primary)
                self.assertEqual(calls, [(75,48,None)] if primary else [(25,36,ap.MAX_PAF_BYTES)])
                self.assertEqual(clock.call_count, 0 if primary else 1)
                with patch.object(nf,"attempt",side_effect=AssertionError("failed work retried")):
                    with self.assertRaisesRegex(wa.ExperimentError,"already failed"):
                        ap.native_review(root,group,index,tool,args,seconds=25,primary_work=primary)

    def test_failed_quality_review_never_publishes_partial_or_retries_it(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            screen = ap.screen_group; native = nf.attempt; attempts = []
            def request_review(root, name, *a, **kw):
                result = screen(root, name, *a, **kw); result["approved"] = False; return result
            def fail_review(mm, target, query, root, options, **kw):
                if root.name == "native-quality-review":
                    attempts.append(root); root.mkdir(); (root / "native.partial.paf").write_bytes(b"NOT COMPLETE\n")
                    return {"status": "other_failure"}
                return native(mm, target, query, root, options, **kw)
            with self.automatic_controls(), patch.object(ap, "screen_group", side_effect=request_review), patch.object(nf, "attempt", side_effect=fail_review):
                with self.assertRaisesRegex(wa.ExperimentError, "review did not complete"):
                    sa.run_reference(args, runtime_root=runtime)
            self.assertEqual(len(attempts), 1)
            self.assertFalse((args.run_dir / "result.paf").exists())
            with self.automatic_controls(), patch.object(ap, "screen_group", side_effect=request_review), patch.object(wa, "run_command", side_effect=AssertionError("failed review silently retried")):
                with self.assertRaisesRegex(wa.ExperimentError, "already failed"):
                    sa.run_reference(args, runtime_root=runtime)
            self.assertEqual((attempts[0] / "native.partial.paf").read_bytes(), b"NOT COMPLETE\n")
            self.assertFalse((args.run_dir / "result.paf").exists())

    def test_cell_deadline_restores_handler_and_stops_postprocessing(self):
        before = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(KeyboardInterrupt):
            with ap.deadline(.02):time.sleep(.1)
        self.assertEqual(signal.getsignal(signal.SIGALRM), before)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    def test_real_hidden_global_assignment_triggers_native_review_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime, args = self.automatic_fixture(root)
            rng = random.Random(2311302); sequence = bytes(rng.choices(b"ACGT", k=120000))
            query = sequence[10000:90000]; mutated = bytearray(sequence)
            change = dict(zip(b"ACGT", b"CGTA"))
            for i in range(0, len(mutated), 97):mutated[i] = change[mutated[i]]
            targets = [b">global\n" + bytes(mutated) + b"\n"]
            for start in range(0, len(query), 5000):
                piece = query[max(0, start-1000):min(len(query), start+6000)]
                targets.extend((">decoy_%d_%d\n" % (start, i)).encode() + piece + b"\n" for i in range(64))
            args.target.write_bytes(b"".join(targets)); args.query.write_bytes(b">forward\n" + query + b"\n")
            with self.automatic_controls(), patch.object(ap, "CORE_BASES", 5000), patch.object(ap, "CONTEXT_BASES", 1000):
                result = sa.run_reference(args, runtime_root=runtime)
            report = json.loads((Path(result["attempt"]) / "selective/proactive-candidate.json").read_text())
            self.assertEqual([r["query"] for r in report["native_reviews"]], ["forward"])
            risk = report["discarded_projection_screening"][0]
            self.assertEqual(risk["profile"]["forward"]["covered"], 80000)
            self.assertIn("covered_but_unassigned", risk["screening"]["queries"][0]["reasons"])
            self.assertEqual((args.run_dir / "result.paf").read_bytes(), Path(report["native_reviews"][0]["native"]["path"]).read_bytes())
            self.assertEqual(result["approximate_query_part_cells"], 0)
            self.assertTrue(result["result_published"])

    def test_real_same_target_local_repeats_trigger_native_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime, args = self.automatic_fixture(root)
            rng = random.Random(2311302); sequence = bytes(rng.choices(b"ACGT", k=120000))
            query = sequence[10000:90000]; mutated = bytearray(sequence)
            change = dict(zip(b"ACGT", b"CGTA"))
            for i in range(0, len(mutated), 97):mutated[i] = change[mutated[i]]
            pieces = []
            for start in range(0, len(query), 5000):
                piece = query[max(0, start-1000):min(len(query), start+6000)]
                pieces.extend([piece + b"N" * 1000] * 64)
            args.target.write_bytes(b">global\n" + bytes(mutated) + b"\n>local_repeats\n" + b"".join(pieces) + b"\n")
            args.query.write_bytes(b">forward\n" + query + b"\n")
            with self.automatic_controls(), patch.object(ap, "CORE_BASES", 5000), patch.object(ap, "CONTEXT_BASES", 1000):
                result = sa.run_reference(args, runtime_root=runtime)
            report = json.loads((Path(result["attempt"]) / "selective/proactive-candidate.json").read_text())
            self.assertEqual([r["query"] for r in report["native_reviews"]], ["forward"])
            risk = report["discarded_projection_screening"][0]
            self.assertEqual(risk["profile"]["forward"]["covered"], 80000)
            self.assertIn("non_collinear_target_support", risk["screening"]["queries"][0]["reasons"])
            self.assertEqual((args.run_dir / "result.paf").read_bytes(), Path(report["native_reviews"][0]["native"]["path"]).read_bytes())
            self.assertEqual(result["approximate_query_part_cells"], 0)
            self.assertTrue(result["result_published"])

    def test_real_multiple_original_parts_include_complete_empty_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime, args = self.automatic_fixture(root)
            rng = random.Random(93)
            with args.target.open("ab") as out:out.write(b">decoy\n" + bytes(rng.choices(b"ACGT", k=160000)) + b"\n")
            command = wa.run_command
            def fixture_layout(argv, folder, name, *a, **kw):
                # Fixture-only original MMI: both the native baseline and every
                # window consume these same serialized parts, not reindexed subsets.
                if name == "default-index":argv = [argv[0], "-I", "100K", *argv[1:]]
                return command(argv, folder, name, *a, **kw)
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=fixture_layout):
                result = sa.run_reference(args, runtime_root=runtime)
            report = json.loads((Path(result["attempt"]) / "selective/proactive-candidate.json").read_text())
            self.assertEqual(report["index_part_count"], 2)
            self.assertEqual(result["approximate_query_part_cells"], 4)
            self.assertEqual(report["combination"]["original_cells"], 6)
            self.assertEqual([r["rows"] for r in report["parts"] if r["part_index"] == 1], [0, 0])
            self.assertTrue(result["result_published"])

    def test_package_contract_cannot_relabel_approximate_output_as_native_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            with self.automatic_controls():result = sa.run_reference(args, runtime_root=runtime)
            attempt = Path(result["attempt"])
            report = json.loads((attempt / "selective/proactive-candidate.json").read_text())
            closed = sa.validate_runtime(runtime); closed["approximate_output_admission"] = None
            with self.assertRaisesRegex(wa.ExperimentError, "not enabled"):
                sa.publication_source(report, attempt, runtime=closed, runtime_root=runtime)

    def test_window_input_mutation_during_mapping_is_not_sealed_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            run = wa.run_command
            def changed(command, folder, name, *a, **kw):
                result = run(command, folder, name, *a, **kw)
                if name == "map":
                    path = folder / "windows.fa"; path.write_bytes(path.read_bytes() + b"\n")
                return result
            with self.automatic_controls(), patch.object(wa, "run_command", side_effect=changed):
                with self.assertRaisesRegex(wa.ExperimentError, "evidence changed"):
                    sa.run_reference(args, runtime_root=runtime)
            attempt = next(args.run_dir.glob(".long-cigar-attempt-*"))
            state = json.loads(next((attempt / "selective").glob("**/" + ap.MANIFEST)).read_text())
            self.assertNotIn("raw", state)
            self.assertFalse((args.run_dir / "result.paf").exists())

    def test_approximate_contract_is_independent_of_closed_native_confidence_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, args = self.automatic_fixture(Path(directory))
            manifest = json.loads((runtime / sa.MANIFEST).read_text())
            manifest.update(status="unvalidated_branch_runtime", recovered_output_admission="closed_pending_final_acceptance",
                            native_companion_sha256=None, native_companion_platform=None)
            wa.write_json(runtime / sa.MANIFEST, manifest)
            with self.automatic_controls():result = sa.run_reference(args, runtime_root=runtime)
            self.assertTrue(result["result_published"])
            self.assertEqual(result["initial_reference_policy"], ap.POLICY)
            self.assertFalse(result["recovered_native_confidence_published"])


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(AutomaticServerTests(name) for name in AutomaticServerTests.__dict__ if name.startswith("test_"))
