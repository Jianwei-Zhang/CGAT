"""Full-contig display orientation is independent of retained path slices."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from server.tests import test_grt_prepare_inputs as tables
from server.tests.test_grt_contract import SCHEMA_PATH, VALID_BUNDLE
from server.tools.grt_contract import ContractError, validate_contract
from server.tools.grt_evidence_package import accepted_source_cards


class SourceCardOrientationTests(unittest.TestCase):
    def events(self, assignment="assigned", placement="normal"):
        # The lexically first event is deliberately NOT the first path slice.
        return [
            {"event_id": event_id, "stage": "step3", "action": "refill",
             "status": "accepted", "chr": "Chr15",
             "source_card_key": f"nd.asm:ctg023590:Chr15:{placement}",
             "final_path_segment_id": segment_id,
             "source": {"dataset": "nd.asm", "contig": "ctg023590",
                        "start": start, "end": end, "orientation": orientation,
                        "original_assignment": assignment}}
            for event_id, segment_id, start, end, orientation in (
                ("a-opposite", "second", 1791344, 1791348, "+"),
                ("z-first", "first", 623124, 624431, "-"),
            )
        ]

    def cards(self, events, assignments=None, baselines=None):
        return accepted_source_cards(
            events,
            assignments if assignments is not None else {("nd.asm", "ctg023590"): {"Chr15"}},
            {"first": ("Chr15", 100), "second": ("Chr15", 10000)},
            baselines if baselines is not None else {("nd.asm", "ctg023590", "Chr15"): ("-", -42)},
        )

    def test_normal_mixed_slices_keep_assignment_orientation_and_all_trace_links(self):
        events = self.events()
        sources_before = copy.deepcopy([event["source"] for event in events])
        card, = self.cards(events)
        self.assertEqual(card["orientation"], "-")
        self.assertEqual(card["event_ids"], ["a-opposite", "z-first"])
        self.assertEqual(set(card["segment_ids"]), {"first", "second"})
        self.assertEqual(card["grt_anchor"], 100)
        self.assertEqual([event["source"] for event in events], sources_before)

    def test_normal_single_opposite_slice_still_uses_assignment_not_slice_direction(self):
        card, = self.cards(self.events()[:1])
        self.assertEqual(card["orientation"], "-")
        self.assertEqual(card["event_ids"], ["a-opposite"])

    def test_promoted_and_cross_chr_mixed_slices_use_first_path_slice_deterministically(self):
        for assignment, placement, assigned in (
            ("unplaced", "grt_promoted", set()),
            ("cross_chr", "cross_chr_grt_usage", {"Chr01"}),
        ):
            with self.subTest(placement=placement):
                events = self.events(assignment, placement)
                first = self.cards(copy.deepcopy(events), {("nd.asm", "ctg023590"): assigned}, {})
                second = self.cards(list(reversed(events)), {("nd.asm", "ctg023590"): assigned}, {})
                self.assertEqual(first, second)
                self.assertEqual(first[0]["orientation"], "-")
                self.assertEqual(first[0]["grt_anchor"], 100)

    def test_missing_normal_baseline_or_invalid_source_orientation_still_fails(self):
        with self.assertRaisesRegex(SystemExit, "lacks an assignment baseline"):
            self.cards(self.events(), baselines={})
        for orientation in ("mixed", "", None):
            with self.subTest(orientation=orientation):
                events = self.events()
                events[0]["source"]["orientation"] = orientation
                with self.assertRaisesRegex(SystemExit, "invalid source orientation"):
                    self.cards(events)

    def test_noncanonical_card_stale_assignment_and_wrong_segment_chr_still_fail(self):
        for field, value, message in (
            ("source_card_key", "wrong", "non-canonical"),
            ("chr", "Chr16", "stale original_assignment"),
            ("final_path_segment_id", "absent", "lacks its Final Path segment"),
        ):
            with self.subTest(field=field):
                events = self.events()
                events[0][field] = value
                with self.assertRaisesRegex(SystemExit, message):
                    self.cards(events)

    def make_mixed_bundle(self, directory, *, normal=False):
        bundle = Path(directory) / "gpm_server"
        shutil.copytree(VALID_BUNDLE, bundle)
        metadata = bundle / "metadata"
        event = json.loads((metadata / "grt_events.jsonl").read_text())
        final = json.loads((metadata / "grt_final_path.json").read_text())
        original_segment = final["chromosomes"][0]["segments"][1]
        usage = tables.read_tsv(metadata / "grt_donor_usage.tsv")[0]
        events, segments, usages = [], [], []
        for index, (start, end, orientation) in enumerate(((1, 2, "+"), (3, 4, "-"))):
            child = copy.deepcopy(event)
            child["event_id"] += f"-{index}"
            child["source"].update(start=start, end=end, orientation=orientation)
            child["final_path_segment_id"] += f"-{index}"
            child["usage_ids"] = [f"use-slice-{index}"]
            child["q_after"].update(start=5 + index * 2, end=6 + index * 2)
            segment = copy.deepcopy(original_segment)
            segment.update(segment_id=child["final_path_segment_id"], length=2,
                           orientation=orientation, event_id=child["event_id"])
            segment["source"].update(start=start, end=end, orientation=orientation)
            usage_row = dict(usage, usage_id=child["usage_ids"][0],
                             source_start=str(start), source_end=str(end),
                             event_id=child["event_id"],
                             final_path_segment_id=child["final_path_segment_id"])
            events.append(child)
            segments.append(segment)
            usages.append(usage_row)
        # All post-fill snapshots really contain CC followed by reverse-complement
        # GG. This checks source -> Final Path -> FASTA, not just card aggregation.
        old_digest = hashlib.sha256((bundle / "grt/q/q4.fa").read_bytes()).hexdigest()
        for path in (bundle / "grt/q").glob("*.fa"):
            if path.name != "q0.fa":
                path.write_text(">Chr01\nAAAACCGG\n", encoding="utf-8", newline="")
        new_digest = hashlib.sha256((bundle / "grt/q/q4.fa").read_bytes()).hexdigest()
        for child in events:
            child["q_after"]["sha256"] = new_digest
        stages = metadata / "grt_stage_status.tsv"
        stages.write_text(stages.read_text().replace(old_digest, new_digest), encoding="utf-8", newline="")
        final["chromosomes"][0]["segments"] = [final["chromosomes"][0]["segments"][0], *segments]
        final["chromosomes"][0]["q4_sha256"] = hashlib.sha256(b"AAAACCGG").hexdigest()
        (metadata / "grt_final_path.json").write_text(json.dumps(final), encoding="utf-8")
        (metadata / "grt_events.jsonl").write_text(
            "".join(json.dumps(child) + "\n" for child in events), encoding="utf-8")
        tables.write_tsv(metadata / "grt_donor_usage.tsv", list(usage), usages)
        attempts = tables.read_tsv(metadata / "grt_gap_attempts.tsv")
        attempts[0]["accepted_event_id"] = events[0]["event_id"]
        tables.write_tsv(metadata / "grt_gap_attempts.tsv", list(attempts[0]), attempts)
        cards = tables.read_tsv(metadata / "grt_used_contigs.tsv")
        # The full-contig display can face either direction. Individual source
        # slices, reverse links and exact q4 bases do not change with this choice.
        cards[0]["orientation"] = "-"
        cards[0]["accepted_event_ids_json"] = json.dumps([child["event_id"] for child in events])
        cards[0]["final_path_segment_ids_json"] = json.dumps([segment["segment_id"] for segment in segments])
        tables.write_tsv(metadata / "grt_used_contigs.tsv", list(cards[0]), cards)
        if normal:
            assignments = tables.read_tsv(metadata / "chr_assignments.tsv")
            assignments.append(dict(assignments[0], dataset_name="support", seq_name="donor1",
                                    source_orientation="+", anchor_start="-42"))
            tables.write_tsv(metadata / "chr_assignments.tsv", list(assignments[0]), assignments)
            orders_path = metadata / "track_member_orders.tsv"
            orders = tables.read_tsv(orders_path)
            orders.append(dict(orders[0], target_track="support", member_dataset="support",
                               member_ctg="donor1"))
            tables.write_tsv(orders_path, list(orders[0]), orders)
            for child in events:
                child["source"]["original_assignment"] = "assigned"
                child["source_card_key"] = "support:donor1:Chr01:normal"
            (metadata / "grt_events.jsonl").write_text(
                "".join(json.dumps(child) + "\n" for child in events), encoding="utf-8")
            cards[0].update(source_card_key="support:donor1:Chr01:normal",
                            original_assignment="assigned", placement_mode="normal",
                            orientation="+", anchor_start="-42")
            tables.write_tsv(metadata / "grt_used_contigs.tsv", list(cards[0]), cards)
            evidence_path = metadata / "grt_evidence_registry.tsv"
            evidence = tables.read_tsv(evidence_path)
            pairwise = next(row for row in evidence if row["evidence_id"] == "ev-display-donor1")
            pairwise["parameters_json"] = json.dumps({
                "provenance": "existing_main_view", "role": "display_pairwise",
                "source_paf_role": "query", "target_dataset": "primary"})
            for field, relative in (
                ("query_artifact_relpath", "runs/chr_Chr01/datasets/support.fa"),
                ("target_artifact_relpath", "runs/chr_Chr01/datasets/primary.fa"),
                ("raw_artifact_relpath", "runs/chr_Chr01/primary_vs_support/result.paf"),
            ):
                target = bundle / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(bundle / pairwise[field], target)
                pairwise[field] = relative
            tables.write_tsv(evidence_path, list(evidence[0]), evidence)
        return bundle

    def test_mixed_fragment_directions_validate_against_real_source_and_q4(self):
        for normal in (False, True):
            with self.subTest(normal=normal), tempfile.TemporaryDirectory() as temporary:
                bundle = self.make_mixed_bundle(temporary, normal=normal)
                summary = validate_contract(bundle, SCHEMA_PATH)
                self.assertEqual(summary["events"], 2)
                self.assertEqual(summary["segments"], 3)

    def test_normal_display_direction_must_still_match_assignment_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self.make_mixed_bundle(temporary, normal=True)
            path = bundle / "metadata/grt_used_contigs.tsv"
            cards = tables.read_tsv(path)
            cards[0]["orientation"] = "-"
            tables.write_tsv(path, list(cards[0]), cards)
            with self.assertRaisesRegex(ContractError, "orientation disagrees with chr_assignments"):
                validate_contract(bundle, SCHEMA_PATH)

    def test_wrong_event_slice_direction_and_corrupt_q4_are_not_hidden_by_display_direction(self):
        for corruption in ("event_orientation", "q4"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temporary:
                bundle = self.make_mixed_bundle(temporary)
                if corruption == "event_orientation":
                    path = bundle / "metadata/grt_events.jsonl"
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    events[1]["source"]["orientation"] = "+"
                    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
                else:
                    (bundle / "grt/q/q4.fa").write_text(">Chr01\nAAAACCCC\n", encoding="utf-8")
                with self.assertRaises(ContractError):
                    validate_contract(bundle, SCHEMA_PATH)


if __name__ == "__main__":
    unittest.main()
