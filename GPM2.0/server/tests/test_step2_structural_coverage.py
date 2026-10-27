"""Backward/forward GAP provenance regressions from the two customer failures."""

import unittest

from server.tests import test_step2_structural_events as fixtures
from server.tools.grt_core.repair_common import PRIMARY_OVERLAP_POLICY
from server.tools.grt_core.repair_structural import apply_corrections
from server.tools.grt_core.step2_engine import (
    arbitrate_structural_candidates,
    build_step2_structural_events,
)
from server.tools.grt_core.step3_engine import (
    reconcile_step2_events_with_step3,
    reject_candidates_spanning_other_gaps,
)
from server.tools.grt_core.stage_io import q_rows_for_paths


class StructuralCoverageTests(unittest.TestCase):
    @staticmethod
    def fixture(policy=None, *, forward=False):
        sources, paths, records, gaps, candidate = fixtures.Step2StructuralEventsTests.fixture(policy)
        if forward:
            sources[("primary", "tail")] = "G" * 20
            paths["Chr01"].extend([
                {"segment_kind": "gap", "length": 100, "evidence_ids": []},
                {**paths["Chr01"][-1], "length": 20, "contig_name": "tail",
                 "source_end": 20, "source_card_key": "primary:tail:Chr01:normal"},
            ])
            records["Chr01"] += "N" * 100 + "G" * 20
            gaps.append({"chr": "Chr01", "object_id": "gap-3", "start0": 290, "end0": 390})
        candidate.update(
            object_id="gap-2", covered_object_ids=["gap-2"], input_start=41,
            input_end=390 if forward else 260, target_start=161,
            outcome="candidate", identity=0.99, aligned_length=20_000,
        )
        return sources, paths, records, gaps, candidate

    def test_backward_and_bidirectional_absorption_replay_and_reconcile(self):
        for policy in (None, PRIMARY_OVERLAP_POLICY):
            for forward in (False, True):
                with self.subTest(policy=policy, forward=forward):
                    fixture = self.fixture(policy, forward=forward)
                    sources, paths, records, gaps, candidate = fixture
                    rejected = {**candidate, "candidate_id": "earlier-rejected", "object_id": "gap-1",
                                "outcome": "rejected", "reason": "repair_mode_conditions_not_met"}
                    rows = arbitrate_structural_candidates([rejected, candidate], list(reversed(gaps)))
                    self.assertEqual(candidate["covered_object_ids"], ["gap-2", "gap-1"] + (["gap-3"] if forward else []))
                    self.assertEqual(rejected["outcome"], "rejected")
                    events, _, output_paths, _ = fixtures.Step2StructuralEventsTests().build_events(fixture)
                    by_object = {row["object_id"]: row for row in events}
                    primary = by_object["gap-2"]
                    self.assertEqual(primary["status"], "accepted")
                    for gap in gaps:
                        if gap["object_id"] == "gap-2":
                            continue
                        absorbed = by_object[gap["object_id"]]
                        self.assertEqual(absorbed["status"], "superseded")
                        self.assertEqual(absorbed["superseded_by_event_id"], primary["event_id"])
                        self.assertIn(absorbed["event_id"], primary["superseded_event_ids"])
                        self.assertEqual(absorbed["q_after"], primary["q_after"])
                    q2_rows = q_rows_for_paths("q2", ["Chr01"], output_paths)
                    q2_hash = primary["q_after"]["sha256"]
                    # Real Step3 explicitly projects each unresolved q2 GAP
                    # onto q3; an empty event list is not a valid normal-gap run.
                    step3_events = [{
                        "event_id": "step3-gap", "chr": row["chr"],
                        "status": "unresolved", "action": "correct_boundary",
                        "q_before": {"version": "q2", "sha256": q2_hash,
                                     "start": row["q_start"], "end": row["q_end"]},
                        "q_after": {"version": "q3", "sha256": "q3-hash",
                                    "start": row["q_start"], "end": row["q_end"]},
                        "q_after_projection": "surviving_origin_gap",
                    } for row in q2_rows if row["segment_kind"] == "gap"]
                    reconcile_step2_events_with_step3(
                        {"events": events, "q_rows": q2_rows,
                         "usage_rows": [], "evidence_rows": []},
                        {"events": step3_events, "q_rows": q_rows_for_paths("q3", ["Chr01"], output_paths),
                         "q_input_version": "q2", "q_input_sha256": q2_hash,
                         "q_output_version": "q3", "q_output_sha256": "q3-hash"},
                    )
                    self.assertEqual(primary["status"], "accepted")
                    self.assertEqual(len(rows), 2)

    def test_exact_customer_interval_coverage(self):
        cases = (
            ("CM054994.1", [(16400304, 16400404), (16432219, 16432319)], 16518606),
            ("CP144746.1", [(46202454, 46202554), (46215981, 46216081), (46237039, 46237139)], 46309689),
        )
        for chromosome, intervals, end in cases:
            with self.subTest(chromosome=chromosome):
                gaps = [{"chr": chromosome, "object_id": f"gap-{i}", "start0": start, "end0": stop}
                        for i, (start, stop) in enumerate(intervals, 1)]
                candidate = {"candidate_id": "customer", "object_id": "gap-2", "chr": chromosome,
                             "target_start": intervals[1][0]+1, "input_start": intervals[0][0]+1,
                             "input_end": end, "identity": .99, "aligned_length": 20_000,
                             "outcome": "candidate"}
                arbitrate_structural_candidates([candidate], gaps)
                self.assertEqual(candidate["covered_object_ids"], ["gap-2", "gap-1"] + (["gap-3"] if len(gaps) == 3 else []))

    def test_coverage_is_chromosome_scoped(self):
        _, _, _, gaps, candidate = self.fixture()
        gaps.append({**gaps[0], "chr": "Chr02", "object_id": "other-chromosome"})
        arbitrate_structural_candidates([candidate], gaps)
        self.assertEqual(candidate["covered_object_ids"], ["gap-2", "gap-1"])

    def test_prior_accepted_edit_still_blocks_backward_overlap(self):
        _, _, _, gaps, candidate = self.fixture()
        prior = {**candidate, "candidate_id": "prior", "object_id": "gap-1",
                 "target_start": 41, "input_start": 41, "input_end": 140}
        arbitrate_structural_candidates([candidate, prior], gaps)
        self.assertEqual(prior["outcome"], "accepted")
        self.assertEqual(candidate["outcome"], "conflicted")

    def test_partially_overlapped_gap_is_rejected_not_sliced(self):
        for start, end in ((91, 260), (41, 210)):
            with self.subTest(start=start, end=end):
                _, _, _, gaps, candidate = self.fixture()
                candidate.update(input_start=start, input_end=end,
                                 object_id="gap-2" if start == 91 else "gap-1")
                arbitrate_structural_candidates([candidate], gaps)
                self.assertEqual(candidate["outcome"], "rejected")
                self.assertIn("partially_overlaps_gap", candidate["reason"])

    def test_partial_candidate_does_not_hide_safe_alternative(self):
        _, _, _, gaps, candidate = self.fixture()
        candidate.update(input_start=91)
        safe = {**candidate, "candidate_id": "safe", "input_start": 161, "identity": .98}
        arbitrate_structural_candidates([candidate, safe], gaps)
        self.assertEqual(safe["outcome"], "accepted")
        self.assertEqual(candidate["outcome"], "rejected")

    def test_apply_rejects_incomplete_unknown_or_duplicate_coverage(self):
        for declared in (["gap-2"], ["gap-2", "unknown"], ["gap-1"], ["gap-2", "gap-1", "gap-1"]):
            with self.subTest(declared=declared):
                sources, paths, records, gaps, candidate = self.fixture()
                candidate.update(outcome="accepted", covered_object_ids=declared)
                with self.assertRaisesRegex(SystemExit, "gap coverage"):
                    apply_corrections(["Chr01"], paths, records, gaps, [candidate], sources)

    def test_apply_preserves_primary_origin_when_coverage_is_not_primary_first(self):
        sources, paths, records, gaps, candidate = self.fixture()
        candidate.update(outcome="accepted", covered_object_ids=["gap-1", "gap-2"])
        _, _, prototypes, origins = apply_corrections(["Chr01"], paths, records, gaps, [candidate], sources)
        origin = next(iter(origins.values()))
        self.assertEqual(origin["object_id"], "gap-2")
        self.assertEqual(origin["coalesced_object_ids"], ["gap-1"])
        events, _ = build_step2_structural_events("run", "q1", "q2", gaps, [candidate], prototypes, origins)
        self.assertEqual([r["status"] for r in events], ["superseded", "accepted"])

    def test_apply_rejects_partial_gap_edit_even_if_declared(self):
        sources, paths, records, gaps, candidate = self.fixture()
        candidate.update(outcome="accepted", input_start=91, covered_object_ids=["gap-2", "gap-1"])
        with self.assertRaisesRegex(SystemExit, "partially overlaps.*gap"):
            apply_corrections(["Chr01"], paths, records, gaps, [candidate], sources)

    def test_following_gap_shift_uses_emitted_replacement_not_fill_hint(self):
        for policy in (None, PRIMARY_OVERLAP_POLICY):
            with self.subTest(policy=policy):
                fixture = fixtures.Step2StructuralEventsTests.fixture(policy)
                fixture[-1]["fill_length"] = 37
                events, _, _, _ = fixtures.Step2StructuralEventsTests().build_events(fixture)
                expected = (151, 250) if policy is None else (51, 150)
                self.assertEqual((events[1]["q_after"]["start"], events[1]["q_after"]["end"]), expected)

    def test_event_serializer_rejects_ambiguous_origin_mapping(self):
        gap = {"chr": "Chr01", "object_id": "gap-1", "start0": 40, "end0": 140}
        origins = {("Chr01", 40, 140): {"object_id": "gap-1"},
                   ("Chr01", 150, 250): {"object_id": "gap-1"}}
        with self.assertRaisesRegex(SystemExit, "ambiguous.*gap.*origin"):
            build_step2_structural_events("run", "q1", "q2", [gap], [], [], origins)

    def test_event_serializer_rejects_duplicate_accepted_owners(self):
        sources, paths, records, gaps, candidate = self.fixture()
        candidate.update(outcome="accepted", covered_object_ids=["gap-2", "gap-1"])
        other = {**candidate, "candidate_id": "duplicate-owner"}
        with self.assertRaisesRegex(SystemExit, "multiple.*accepted.*gap"):
            build_step2_structural_events("run", "q1", "q2", gaps, [candidate, other], [], {})

    def test_step3_already_rejects_forward_backward_and_partial_multigap_edits(self):
        for start, end in ((41, 260), (91, 260)):
            with self.subTest(start=start, end=end):
                _, _, _, gaps, candidate = self.fixture()
                candidate.update(input_start=start, input_end=end)
                reject_candidates_spanning_other_gaps([candidate], gaps)
                self.assertEqual(candidate["outcome"], "rejected")
                self.assertIn("spans_other_gap", candidate["reason"])


if __name__ == "__main__":
    unittest.main()
