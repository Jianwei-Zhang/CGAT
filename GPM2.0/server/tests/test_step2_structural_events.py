"""Regression coverage for Step2 events after gap-preserving and gapless edits."""

import hashlib
import unittest

from server.tools.grt_core.repair_common import (
    DOMINATED_COMPONENT_POLICY,
    PRIMARY_OVERLAP_POLICY,
)
from server.tools.grt_core.repair_structural import apply_corrections
from server.tools.grt_core.stage_io import q_rows_for_paths
from server.tools.grt_core.step2_engine import build_step2_structural_events
from server.tools.grt_core.step3_engine import reconcile_step2_events_with_step3, replay_step3


class Step2StructuralEventsTests(unittest.TestCase):
    @staticmethod
    def fixture(policy=PRIMARY_OVERLAP_POLICY, *, coalesced=False):
        sources = {("primary", "left"): "A" * 40,
                   ("primary", "middle"): "C" * 20,
                   ("primary", "right"): "T" * 30}
        paths = []
        for index, (contig, length) in enumerate((("left", 40), ("middle", 20), ("right", 30))):
            if index:
                paths.append({"segment_kind": "gap", "length": 100,
                              "evidence_ids": []})
            paths.append({
                "segment_kind": "source", "length": length,
                "dataset_name": "primary", "contig_name": contig,
                "source_start": 1, "source_end": length, "orientation": "+",
                "source_card_key": f"primary:{contig}:Chr01:normal",
                "evidence_ids": [f"assignment-{contig}"],
            })
        gaps = [{"chr": "Chr01", "object_id": "gap-1", "start0": 40, "end0": 140},
                {"chr": "Chr01", "object_id": "gap-2", "start0": 160, "end0": 260}]
        candidate = {
            "candidate_id": "correction-1", "chr": "Chr01", "object_id": "gap-1",
            "covered_object_ids": ["gap-1", "gap-2"] if coalesced else ["gap-1"],
            "outcome": "accepted", "action": "delete" if policy else "replace",
            "classification_reason": "structural_repair", "input_start": 41,
            "input_end": 260 if coalesced else 150,
            "fill_length": 0 if policy else 100,
            "evidence_ids": ["evidence-1"], "junction_policy": policy,
            "trim_left": 0, "trim_right": 10, "direct_overlap_bp": 10,
            "primary_left_dataset": "primary", "primary_left_contig": "left",
            "primary_left_orientation": "+", "primary_right_dataset": "primary",
            "primary_right_contig": "middle", "primary_right_orientation": "+",
            "dominated_side": "left",
        }
        records = {"Chr01": "A" * 40 + "N" * 100 + "C" * 20 + "N" * 100 + "T" * 30}
        return sources, {"Chr01": paths}, records, gaps, candidate

    def build_events(self, fixture):
        sources, paths, records, gaps, candidate = fixture
        output_paths, output_records, prototypes, origins = apply_corrections(
            ["Chr01"], paths, records, gaps, [candidate], sources,
        )
        q1_hash = hashlib.sha256(records["Chr01"].encode("ascii")).hexdigest()
        q2_hash = hashlib.sha256(output_records["Chr01"].encode("ascii")).hexdigest()
        events, attempts = build_step2_structural_events(
            "run-test", q1_hash, q2_hash, gaps, [candidate], prototypes, origins,
        )
        for event in events:
            after = event["q_after"]
            self.assertEqual(after["version"], "q2")
            self.assertEqual(after["sha256"], q2_hash)
            self.assertGreaterEqual(after["start"], 1)
            self.assertLessEqual(after["start"], after["end"])
            self.assertLessEqual(after["end"], len(output_records["Chr01"]))
        edits = [event for event in events if event["status"] == "accepted"]
        self.assertEqual(replay_step3(records, edits, [], sources), output_records)
        return events, attempts, output_paths, output_records

    def test_gapless_junction_uses_prototype_and_preserves_following_gap(self):
        for policy in (PRIMARY_OVERLAP_POLICY, DOMINATED_COMPONENT_POLICY):
            with self.subTest(policy=policy):
                events, attempts, _, records = self.build_events(self.fixture(policy))
                accepted, unresolved = events
                self.assertEqual(accepted["status"], "accepted")
                self.assertEqual((accepted["q_after"]["start"], accepted["q_after"]["end"]), (41, 41))
                self.assertEqual(accepted["edit"]["replacement_kind"], "none")
                self.assertEqual(accepted["edit"]["replacement_length"], 0)
                self.assertEqual(accepted["edit"]["replacement_sequence_sha256"], hashlib.sha256(b"").hexdigest())
                self.assertEqual(accepted["junction"]["policy"], policy)
                self.assertFalse(accepted["junction"]["support_sequence_inserted"])
                self.assertEqual(unresolved["status"], "unresolved")
                self.assertEqual((unresolved["q_after"]["start"], unresolved["q_after"]["end"]), (51, 150))
                self.assertEqual([row["status"] for row in attempts], ["accepted", "unresolved"])
                self.assertEqual(records["Chr01"], "A" * 40 + "C" * 10 + "N" * 100 + "T" * 30)

    def test_gapless_coalesced_objects_share_junction_and_supersession(self):
        for policy in (PRIMARY_OVERLAP_POLICY, DOMINATED_COMPONENT_POLICY):
            with self.subTest(policy=policy):
                events, attempts, paths, records = self.build_events(self.fixture(policy, coalesced=True))
                primary, absorbed = events
                self.assertEqual([event["status"] for event in events], ["accepted", "superseded"])
                self.assertEqual(absorbed["superseded_by_event_id"], primary["event_id"])
                self.assertEqual(primary["superseded_event_ids"], [absorbed["event_id"]])
                self.assertEqual(absorbed["q_after"], primary["q_after"])
                self.assertEqual([row["status"] for row in attempts], ["accepted", "superseded"])
                self.assertEqual(records["Chr01"], "A" * 40 + "T" * 30)
                self.assertFalse(any(segment["segment_kind"] == "gap" for segment in paths["Chr01"]))
                q2_rows = q_rows_for_paths("q2", ["Chr01"], paths)
                q3_rows = q_rows_for_paths("q3", ["Chr01"], paths)
                reconcile_step2_events_with_step3(
                    {"events": events, "q_rows": q2_rows, "usage_rows": [], "evidence_rows": []},
                    {"events": [], "q_rows": q3_rows},
                )
                self.assertEqual(primary["status"], "accepted")

    def test_terminal_component_deletions_anchor_to_a_retained_base(self):
        for side, start, end, expected, junction in (
            ("left", 1, 140, "C" * 20 + "N" * 100 + "T" * 30, 1),
            ("right", 161, 290, "A" * 40 + "N" * 100 + "C" * 20, 160),
        ):
            with self.subTest(side=side):
                sources, paths, records, gaps, candidate = self.fixture(DOMINATED_COMPONENT_POLICY)
                candidate.update({
                    "dominated_side": side, "input_start": start, "input_end": end,
                    "object_id": f"gap-{1 if side == 'left' else 2}",
                    "covered_object_ids": [f"gap-{1 if side == 'left' else 2}"],
                })
                events, _, _, output = self.build_events((sources, paths, records, gaps, candidate))
                event = next(row for row in events if row["status"] == "accepted")
                self.assertEqual(output["Chr01"], expected)
                self.assertEqual((event["q_after"]["start"], event["q_after"]["end"]), (junction, junction))
                self.assertEqual(event["junction"]["dominated_side"], side)

    def test_normalized_gap_edit_and_coalesced_origins_are_unchanged(self):
        events, _, _, records = self.build_events(self.fixture(None, coalesced=True))
        primary, absorbed = events
        self.assertEqual(primary["edit"]["replacement_kind"], "gap")
        self.assertEqual(primary["edit"]["replacement_length"], 100)
        self.assertEqual(primary["edit"]["replacement_sequence_sha256"], hashlib.sha256(b"N" * 100).hexdigest())
        self.assertEqual((primary["q_after"]["start"], primary["q_after"]["end"]), (41, 140))
        self.assertEqual(primary["q_after"], absorbed["q_after"])
        self.assertNotIn("junction", primary)
        self.assertEqual(records["Chr01"], "A" * 40 + "N" * 100 + "T" * 30)

    def test_unaccepted_gaps_keep_original_coordinates_and_status(self):
        for outcome, status in (("rejected", "unresolved"), ("conflicted", "conflicted")):
            with self.subTest(outcome=outcome):
                fixture = self.fixture()
                fixture[-1]["outcome"] = outcome
                events, _, _, records = self.build_events(fixture)
                self.assertEqual(events[0]["status"], status)
                self.assertEqual((events[0]["q_after"]["start"], events[0]["q_after"]["end"]), (41, 140))
                self.assertEqual(records, fixture[2])

    def test_missing_unresolved_origin_fails_explicitly(self):
        gap = {"chr": "Chr01", "object_id": "missing-gap", "start0": 40, "end0": 140}
        with self.assertRaisesRegex(SystemExit, "Step2.*output.*missing-gap"):
            build_step2_structural_events("run-test", "q1", "q2", [gap], [], [], {})

    def test_missing_accepted_prototype_fails_explicitly(self):
        _, _, _, gaps, candidate = self.fixture()
        with self.assertRaisesRegex(SystemExit, "Step2.*prototype.*correction-1"):
            build_step2_structural_events("run-test", "q1", "q2", gaps[:1], [candidate], [], {})

    def test_missing_normalized_gap_origin_is_not_replaced_by_prototype(self):
        sources, paths, records, gaps, candidate = self.fixture(None)
        _, _, prototypes, _ = apply_corrections(
            ["Chr01"], paths, records, gaps, [candidate], sources,
        )
        with self.assertRaisesRegex(SystemExit, "Step2.*output.*gap-1"):
            build_step2_structural_events("run-test", "q1", "q2", gaps[:1], [candidate], prototypes, {})

    def test_gapless_deletion_cannot_remove_entire_chromosome(self):
        sources, paths, records, gaps, candidate = self.fixture()
        candidate.update({"input_start": 1, "input_end": 290,
                          "covered_object_ids": ["gap-1", "gap-2"]})
        with self.assertRaisesRegex(SystemExit, "remove the entire chromosome.*correction-1"):
            apply_corrections(["Chr01"], paths, records, gaps, [candidate], sources)

    def test_gapless_prototype_must_have_zero_replacement_length(self):
        sources, paths, records, gaps, candidate = self.fixture()
        _, _, prototypes, origins = apply_corrections(
            ["Chr01"], paths, records, gaps, [candidate], sources,
        )
        prototypes[0]["replacement_length"] = 100
        with self.assertRaisesRegex(SystemExit, "Step2.*gapless.*correction-1"):
            build_step2_structural_events("run-test", "q1", "q2", gaps, [candidate], prototypes, origins)


if __name__ == "__main__":
    unittest.main()
