"""Retained-source regression coverage for corrected-space refill trims."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from server.tools.grt_core.common import reverse_complement
from server.tools.grt_core.stage_io import path_sequence, q_rows_for_paths
from server.tools.grt_core.stage_replay import apply_round, apply_filter, flatten_event_supersession
from server.tools.grt_core.step3_engine import (
    finalize_refill_origins, finalize_step3_public_coordinates,
    reconcile_refill_rounds, reconcile_step2_events_with_step3, replay_step3,
)
from server.tools.grt_telomere_finalize import (
    build_final_path, reconcile_terminal_supersession, verify_final_path,
)


class RefillLineageTests(unittest.TestCase):
    @staticmethod
    def fixture(strand="+", *, old_length=20000, trim=30, prefix_component=0):
        sources = {("primary", "left"): "A" * 200000,
                   ("primary", "middle"): "C" * 10,
                   ("primary", "right"): "G" * 200000,
                   ("support", "old"): "T" * old_length,
                   ("support", "new"): "C" * 10000}

        def segment(ds, ctg):
            length = len(sources[(ds, ctg)])
            return {"segment_kind": "source", "length": length,
                    "dataset_name": ds, "contig_name": ctg, "source_start": 1,
                    "source_end": length, "orientation": "+",
                    "source_card_key": f"{ds}:{ctg}:Chr01:normal",
                    "evidence_ids": [f"assignment-{ctg}"]}

        gap = {"segment_kind": "gap", "length": 100, "dataset_name": "", "contig_name": "",
               "source_start": None, "source_end": None, "orientation": "",
               "source_card_key": "", "evidence_ids": []}
        paths = {"Chr01": [segment("primary", "left"), copy.deepcopy(gap),
                           segment("primary", "middle"), copy.deepcopy(gap),
                           segment("primary", "right")]}
        offset = 0
        if prefix_component:
            sources[("primary", "prefix")] = "A" * prefix_component
            paths["Chr01"][:0] = [segment("primary", "prefix"), copy.deepcopy(gap)]
            offset = prefix_component + 100
        records = {"Chr01": path_sequence(paths["Chr01"], sources)}
        gaps = [{"chr": "Chr01", "object_id": "first-gap", "start0": 200000 + offset, "end0": 200100 + offset},
                {"chr": "Chr01", "object_id": "second-gap", "start0": 200110 + offset, "end0": 200210 + offset}]
        assignments = {key: "Chr01" for key in sources}

        def candidate(name, object_id, trim_left):
            raw = sources[("support", name)]
            orientation = strand if name == "old" else "+"
            seq = raw if orientation == "+" else reverse_complement(raw)
            return {"candidate_id": name, "chr": "Chr01", "object_id": object_id,
                    "outcome": "accepted", "reason": "validated_fixture",
                    "trim_left": trim_left, "trim_right": 0,
                    "source_dataset": "support", "source_contig": name, "source_start": 1,
                    "source_end": len(seq), "orientation": orientation, "fill_length": len(seq),
                    "fill_sequence": seq, "member_id": f"member-{name}",
                    "evidence_ids": [f"evidence-{name}"]}

        r1paths, r1records, r1events, r1usage, _ = apply_round(
            "lineage-test", "step3", "q2", "q3", ["Chr01"], paths, records, gaps,
            [candidate("old", "first-gap", 0)], assignments, "q2-hash", sources, action="refill")
        filtered, filtered_records, filter_events = apply_filter(
            "lineage-test", ["Chr01"], r1paths, r1records, "q2-hash", sources,
            stage="step3", q_input_version="q2", q_output_version="q3")
        assert (filtered_records != r1records) == bool(prefix_component)
        second_gap = {"chr": "Chr01", "object_id": "round2-gap",
                      "start0": 200010 + old_length, "end0": 200110 + old_length}
        output, output_records, r2events, r2usage, _ = apply_round(
            "lineage-test", "step3", "q2", "q3", ["Chr01"], filtered, filtered_records,
            [second_gap], [candidate("new", "round2-gap", trim)], assignments,
            "q2-hash", sources, action="refill")
        evidence = [{"evidence_id": "evidence-old", "status": "accepted"}]
        return dict(sources=sources, paths=paths, records=records, gaps=gaps,
                    r1paths=r1paths, r1records=r1records, r1events=r1events, r1usage=r1usage,
                    filter_events=filter_events, r2gap=second_gap, r2events=r2events,
                    r2usage=r2usage, output=output, output_records=output_records,
                    evidence=evidence, old_length=old_length, offset=offset)

    def finalize_round2_origins(self, case, *, pure=False):
        gap = case["r2gap"]
        start = int(gap["start0"]) + 1 if pure else 200111 + case["offset"]
        end = int(gap["end0"]) if pure else 200210 + case["offset"]
        finalize_refill_origins(case["r2events"], [{**gap, "origin": {
            "object_id": "second-gap", "q2_start": start, "q2_end": end}}])

    def assert_exact_path(self, case, events):
        with patch("server.tools.grt_telomere_finalize.read_fasta",
                   return_value=list(case["output_records"].items())):
            reconcile_terminal_supersession(
                Path("unused"), q_rows_for_paths("q3", ["Chr01"], case["output"]),
                case["output"], events, case["evidence"], case["r1usage"] + case["r2usage"])
        final_path = build_final_path(["Chr01"], case["output"], case["output_records"], events)
        verify_final_path(final_path, case["output_records"], case["sources"])
        return final_path

    def test_second_refill_trims_first_in_both_orientations(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                case = self.fixture(strand)
                parent = next(e for e in case["r1events"] if e["status"] == "accepted")
                original = copy.deepcopy(parent)
                self.finalize_round2_origins(case)
                children = reconcile_refill_rounds(
                    ["Chr01"], case["r1paths"], case["output"], "q3-hash",
                    case["r1events"], case["r1usage"], case["evidence"],
                    case["r2events"], case["r2usage"])
                self.assertEqual(len(children), 1)
                child = children[0]
                self.assertEqual(parent["status"], "superseded")
                self.assertEqual(parent["source"], original["source"])
                self.assertEqual(parent["edit"], original["edit"])
                self.assertEqual(child["q_before"], original["q_before"])
                self.assertNotIn("edit", child)
                expected = (1, 19980) if strand == "+" else (21, 20000)
                self.assertEqual((child["source"]["start"], child["source"]["end"]), expected)
                self.assertEqual(replay_step3(
                    case["records"], [], case["r1events"], case["sources"],
                    case["filter_events"], case["r2events"]), case["output_records"])
                events = case["r1events"] + case["filter_events"] + case["r2events"] + children
                flatten_event_supersession(events)
                finalize_step3_public_coordinates(
                    events, case["records"], case["output_records"], "q2-hash", "q3-hash", case["output"])
                self.assert_exact_path(case, events)
                self.assertTrue(any(u["event_id"] == child["event_id"] and u["status"] == "consumed"
                                    for u in case["r2usage"]))

    def test_second_round_after_filter_coordinate_shift(self):
        case = self.fixture(prefix_component=50000)
        self.finalize_round2_origins(case)
        children = reconcile_refill_rounds(
            ["Chr01"], case["r1paths"], case["output"], "q3-hash", case["r1events"],
            case["r1usage"], case["evidence"], case["r2events"], case["r2usage"])
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["q_before"]["start"], 250101)
        self.assertEqual(children[0]["q_after"]["start"], 200001)
        self.assertEqual(children[0]["source"]["end"], 19980)
        self.assertEqual(replay_step3(
            case["records"], [], case["r1events"], case["sources"],
            case["filter_events"], case["r2events"]), case["output_records"])
        events = case["r1events"] + case["filter_events"] + case["r2events"] + children
        flatten_event_supersession(events)
        finalize_step3_public_coordinates(
            events, case["records"], case["output_records"], "q2-hash", "q3-hash", case["output"])
        self.assert_exact_path(case, events)

    def test_pure_refill_trims_step2_without_structural_correction(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                case = self.fixture(strand)
                parent = copy.deepcopy(next(e for e in case["r1events"] if e["status"] == "accepted"))
                parent.update(stage="step2", action="patch")
                parent["q_after"].update(version="q2", sha256="q2-hash")
                parent["q_before"]["version"] = "q1"
                original = copy.deepcopy(parent)
                self.finalize_round2_origins(case, pure=True)
                s2 = {"events": [parent], "q_rows": q_rows_for_paths("q2", ["Chr01"], case["r1paths"]),
                      "usage_rows": case["r1usage"], "evidence_rows": case["evidence"]}
                s3 = {"events": case["r2events"], "q_rows": q_rows_for_paths("q3", ["Chr01"], case["output"]),
                      "usage_rows": case["r2usage"], "q_input_version": "q2", "q_input_sha256": "q2-hash",
                      "q_output_version": "q3", "q_output_sha256": "q3-hash"}
                reconcile_step2_events_with_step3(s2, s3)
                self.assertEqual(parent["status"], "superseded")
                self.assertEqual(parent["source"], original["source"])
                self.assertEqual(parent["edit"], original["edit"])
                child = s3["events"][-1]
                self.assertEqual(child["retained_from_event_id"], parent["event_id"])
                self.assert_exact_path(case, s2["events"] + s3["events"])
                frozen = copy.deepcopy((s2, s3))
                reconcile_step2_events_with_step3(s2, s3)
                self.assertEqual((s2, s3), frozen)

    def test_removed_source_trace_is_exact_and_does_not_mutate_input(self):
        case = self.fixture()
        trace = case["r2events"][0]["edit"]["replaced_source_segments"]
        self.assertEqual([(x["contig_name"], x["source_start"], x["source_end"]) for x in trace],
                         [("old", 19981, 20000), ("middle", 1, 10)])
        self.assertEqual(next(x for x in case["r1paths"]["Chr01"] if x["contig_name"] == "old")["source_end"], 20000)
        self.assertEqual(trace[0]["evidence_ids"], ["evidence-old"])
        json.dumps(case["r2events"])

    def test_full_replacement_supersedes_without_an_invented_retained_fragment(self):
        case = self.fixture(old_length=2000, trim=2010)
        self.finalize_round2_origins(case)
        parent = next(e for e in case["r1events"] if e["status"] == "accepted")
        children = reconcile_refill_rounds(
            ["Chr01"], case["r1paths"], case["output"], "q3-hash", case["r1events"],
            case["r1usage"], case["evidence"], case["r2events"], case["r2usage"])
        self.assertEqual(children, [])
        self.assertEqual(parent["status"], "superseded")
        self.assertEqual(parent["superseded_by_event_id"], case["r2events"][0]["event_id"])
        self.assertEqual(case["evidence"][0]["status"], "superseded")
        events = case["r1events"] + case["filter_events"] + case["r2events"]
        flatten_event_supersession(events)
        self.assert_exact_path(case, events)
        self.assertEqual(replay_step3(case["records"], [], case["r1events"], case["sources"],
                                     case["filter_events"], case["r2events"]), case["output_records"])

    def test_wrong_or_missing_removed_source_trace_still_fails_closed(self):
        for field, value in (("contig_name", "unrelated"), ("orientation", "-"),
                             ("source_card_key", "unrelated"), ("evidence_ids", ["unrelated"]),
                             ("length", 1), ("source_end", 20001), ("missing", None)):
            with self.subTest(field=field):
                case = self.fixture()
                trace = case["r2events"][0]["edit"]["replaced_source_segments"]
                if field == "missing":
                    trace.clear()
                else:
                    trace[0][field] = value
                self.finalize_round2_origins(case)
                with self.assertRaises(SystemExit):
                    reconcile_refill_rounds(
                        ["Chr01"], case["r1paths"], case["output"], "q3-hash", case["r1events"],
                        case["r1usage"], case["evidence"], case["r2events"], case["r2usage"])

    def test_fresh_replays_produce_identical_lineage_ids(self):
        results = []
        for _ in range(2):
            case = self.fixture()
            self.finalize_round2_origins(case)
            results.append(reconcile_refill_rounds(
                ["Chr01"], case["r1paths"], case["output"], "q3-hash", case["r1events"],
                case["r1usage"], case["evidence"], case["r2events"], case["r2usage"]))
        self.assertEqual(results[0], results[1])
