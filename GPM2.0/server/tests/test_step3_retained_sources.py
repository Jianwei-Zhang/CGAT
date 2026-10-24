"""Partial Step2-patch retention must preserve replay and exact Final Path links."""

import copy
import csv
import json
import shutil
import hashlib
import tempfile
import unittest
from pathlib import Path

from server.tools.grt_core.stage_io import q_rows_for_paths, path_sequence
from server.tools.grt_core.stage_replay import replay_round_records
from server.tools.grt_core.step3_engine import reconcile_step2_events_with_step3
from server.tools.grt_telomere_finalize import (
    build_final_path, reconcile_terminal_supersession, verify_final_path,
)


class Step3RetainedSourceTests(unittest.TestCase):
    @staticmethod
    def fixture(orientation="+", retained=((104, 120),), cuts=((8, 13),)):
        sources = {("primary", "left"): "A" * 10,
                   ("primary", "right"): "G" * 10,
                   ("support", "patch"): "C" * 120}

        def segment(dataset, contig, start, end, evidence, strand="+"):
            return {"segment_kind": "source", "length": end - start + 1,
                    "dataset_name": dataset, "contig_name": contig,
                    "source_start": start, "source_end": end,
                    "orientation": strand,
                    "source_card_key": f"{dataset}:{contig}:Chr01:normal",
                    "evidence_ids": evidence}

        left = segment("primary", "left", 1, 10, ["assignment-left"])
        right = segment("primary", "right", 1, 10, ["assignment-right"])
        patch = segment("support", "patch", 101, 120, ["patch-evidence"], orientation)
        q2_paths = {"Chr01": [left, patch, right]}
        q2_records = {"Chr01": path_sequence(q2_paths["Chr01"], sources)}
        q3_paths = {"Chr01": [left, *(
            segment("support", "patch", start, end, ["patch-evidence"], orientation)
            for start, end in sorted(retained, reverse=orientation == "-")
        ), right]}
        q3_records = {"Chr01": path_sequence(q3_paths["Chr01"], sources)}
        source = {"dataset": "support", "contig": "patch", "start": 101,
                  "end": 120, "orientation": orientation,
                  "original_assignment": "assigned"}
        event = {
            "run_id": "test-run", "event_id": "step2-patch", "stage": "step2",
            "chr": "Chr01", "object_id": "gap-1", "action": "patch",
            "status": "accepted", "reason": "accepted_patch",
            "source": source, "source_card_key": patch["source_card_key"],
            "final_path_segment_id": "patch-segment",
            "q_before": {"version": "q1", "start": 11, "end": 110,
                         "sha256": "q1-hash"},
            "q_after": {"version": "q2", "start": 11, "end": 30,
                        "sha256": "q2-hash"},
            "edit": {"operation": "replace_interval", "replacement_kind": "source",
                     "input_start": 11, "input_end": 110,
                     "replacement_sequence_sha256": hashlib.sha256(
                         q2_records["Chr01"][10:30].encode("ascii")).hexdigest()},
            "evidence_ids": ["patch-evidence"], "usage_ids": ["patch-usage"],
        }
        usage = {"usage_id": "patch-usage", "donor_set_id": "d0", "member_id": "member",
                 "source_dataset": "support", "source_contig": "patch",
                 "source_start": 101, "source_end": 120, "stage": "step2",
                 "status": "consumed", "event_id": event["event_id"],
                 "final_path_segment_id": "patch-segment", "reason": "accepted_patch"}
        corrections = []
        for index, (start, end) in enumerate(cuts):
            corrections.append({
                "event_id": f"correction-{index}", "stage": "step3", "chr": "Chr01",
                "action": "delete", "status": "accepted", "source": None,
                "q_before": {"version": "q2", "start": start, "end": end,
                             "sha256": "q2-hash"},
                "edit": {"operation": "replace_interval", "input_start": start,
                         "input_end": end, "input_coordinate_space": "q2_1_based_closed"},
            })
        step2 = {"events": [event], "q_rows": q_rows_for_paths("q2", ["Chr01"], q2_paths),
                 "usage_rows": [usage],
                 "evidence_rows": [{"evidence_id": "patch-evidence", "status": "accepted"}]}
        step3 = {"events": corrections, "q_rows": q_rows_for_paths("q3", ["Chr01"], q3_paths),
                 "usage_rows": [], "q_input_version": "q2", "q_input_sha256": "q2-hash",
                 "q_output_version": "q3", "q_output_sha256": "q3-hash"}
        return step2, step3, sources, q2_records, q3_paths, q3_records

    def test_trimmed_patch_preserves_original_replay_and_exact_final_path(self):
        for strand, retained in (("+", ((104, 120),)), ("-", ((101, 117),))):
            with self.subTest(strand=strand):
                s2, s3, sources, q2, paths, q3 = self.fixture(strand, retained)
                original = copy.deepcopy(s2["events"][0])
                reconcile_step2_events_with_step3(s2, s3)
                parent = s2["events"][0]
                child = s3["events"][-1]
                self.assertEqual(parent["status"], "superseded")
                self.assertEqual(parent["source"], original["source"])
                self.assertEqual(parent["edit"], original["edit"])
                self.assertEqual(parent["q_after"], original["q_after"])
                self.assertEqual(parent["superseded_by_event_id"], child["event_id"])
                self.assertEqual(child["superseded_event_ids"], [parent["event_id"]])
                self.assertEqual(child["retained_after_event_ids"], ["correction-0"])
                self.assertNotIn("edit", child)
                self.assertEqual((child["source"]["start"], child["source"]["end"]), retained[0])
                self.assertEqual((child["q_before"]["start"], child["q_before"]["end"]), (14, 30))
                self.assertEqual(s2["usage_rows"][0]["status"], "superseded")
                self.assertEqual(s2["evidence_rows"][0]["status"], "accepted")
                usage = s3["usage_rows"][0]
                self.assertEqual(child["usage_ids"], [usage["usage_id"]])
                self.assertEqual(usage["event_id"], child["event_id"])
                self.assertEqual(usage["final_path_segment_id"], child["final_path_segment_id"])
                q1 = {"Chr01": "A" * 10 + "N" * 100 + "G" * 10}
                self.assertEqual(replay_round_records(q1, s2["events"], sources), q2)
                events = s2["events"] + s3["events"]
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "grt/q").mkdir(parents=True)
                    (root / "grt/q/q3.fa").write_text(">Chr01\n" + q3["Chr01"] + "\n")
                    reconcile_terminal_supersession(root, s3["q_rows"], paths, events,
                                                   s2["evidence_rows"], s2["usage_rows"] + s3["usage_rows"])
                final_path = build_final_path(["Chr01"], paths, q3, events)
                verify_final_path(final_path, q3, sources)
                self.assertEqual(final_path["chromosomes"][0]["segments"][1]["event_id"], child["event_id"])
                after = copy.deepcopy((s2, s3))
                reconcile_step2_events_with_step3(s2, s3)
                self.assertEqual((s2, s3), after)

    def test_reported_chr12_and_chr17_partial_patch_coordinates(self):
        cases = (
            ("Chr12", 260862, 290186, 20384737, 20060196, 91, 20371876),
            ("Chr17", 308759, 463277, 8574201, 8501127, 99, 8560222),
            ("Chr17", 1197230, 1240642, 10362471, 10275820, 98, 10348895),
        )
        for chromosome, start, end, q2_start, q3_start, trim, cut_start in cases:
            with self.subTest(chromosome=chromosome, source_start=start):
                s2, s3, *_ = self.fixture()
                parent = s2["events"][0]
                parent["chr"] = chromosome
                parent["source"].update(start=start, end=end)
                parent["q_after"].update(start=q2_start, end=q2_start + end - start)
                row = s2["q_rows"][1]
                row.update(chr=chromosome, q_start=q2_start, q_end=q2_start + end - start,
                           source_start=start, source_end=end)
                s3["q_rows"] = [{**row, "q_version": "q3", "segment_id": "retained",
                                  "source_start": start + trim, "q_start": q3_start,
                                  "q_end": q3_start + end - start - trim}]
                correction = s3["events"][0]
                correction["chr"] = chromosome
                correction["q_before"].update(start=cut_start, end=q2_start + trim - 1)
                correction["edit"].update(input_start=cut_start, input_end=q2_start + trim - 1)
                s2["usage_rows"][0].update(source_start=start, source_end=end)
                reconcile_step2_events_with_step3(s2, s3)
                child = s3["events"][-1]
                self.assertEqual(child["source"]["start"], start + trim)
                self.assertEqual(child["source"]["end"], end)
                self.assertEqual(child["q_after"]["end"] - child["q_after"]["start"] + 1,
                                 end - start + 1 - trim)

    def test_middle_edit_retains_two_exact_fragments(self):
        s2, s3, sources, _q2, paths, q3 = self.fixture(
            retained=((101, 108), (112, 120)), cuts=((19, 21),))
        reconcile_step2_events_with_step3(s2, s3)
        children = [e for e in s3["events"] if e.get("retained_from_event_id")]
        self.assertEqual(len(children), 2)
        self.assertEqual(len({e["event_id"] for e in children}), 2)
        self.assertEqual(len({e["final_path_segment_id"] for e in children}), 2)
        self.assertEqual(len(s3["usage_rows"]), 2)
        final_path = build_final_path(["Chr01"], paths, q3, s2["events"] + s3["events"])
        verify_final_path(final_path, q3, sources)

    def test_terminal_replacement_flattens_retained_event_history(self):
        s2, s3, _sources, _q2, paths, q3 = self.fixture()
        reconcile_step2_events_with_step3(s2, s3)
        child = s3["events"][-1]
        tel = {"event_id": "terminal", "stage": "step4_telomere", "chr": "Chr01",
               "status": "accepted", "action": "extend_telomere",
               "edit": {"terminal": "5prime", "q3_cut_after": 27}}
        events = s2["events"] + s3["events"] + [tel]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grt/q").mkdir(parents=True)
            (root / "grt/q/q3.fa").write_text(">Chr01\n" + q3["Chr01"] + "\n")
            reconcile_terminal_supersession(
                root, s3["q_rows"], {"Chr01": [paths["Chr01"][-1]]}, events,
                s2["evidence_rows"], s2["usage_rows"] + s3["usage_rows"])
        self.assertEqual(child["status"], "superseded")
        self.assertEqual(child["superseded_event_ids"], [])
        self.assertEqual(s2["events"][0]["superseded_by_event_id"], "terminal")
        self.assertEqual(tel["superseded_event_ids"], sorted(["step2-patch", child["event_id"]]))
        self.assertEqual(child["retained_from_event_id"], "step2-patch")

    def test_projected_bundle_passes_unchanged_contract(self):
        from server.tests.test_grt_contract import VALID_BUNDLE, SCHEMA_PATH
        from server.tools.grt_contract import validate_contract

        def read_table(root, name):
            with (root / "metadata" / name).open() as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                return reader.fieldnames, list(reader)

        def write_table(root, name, fields, rows):
            with (root / "metadata" / name).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            shutil.copytree(VALID_BUNDLE, root)
            parent = json.loads((root / "metadata/grt_events.jsonl").read_text())
            old_hash = parent["q_after"]["sha256"]
            new_fasta = b">Chr01\nAAAACCC\n"
            new_hash = hashlib.sha256(new_fasta).hexdigest()
            for version in ("q3", "q4"):
                (root / f"grt/q/{version}.fa").write_bytes(new_fasta)
            parent.update(stage="step2", action="patch")
            parent["q_before"].update(version="q1", start=5, end=8, sha256=old_hash)
            parent["q_after"].update(version="q2", start=5, end=8)
            _fields, usage = read_table(root, "grt_donor_usage.tsv")
            usage[0]["stage"] = "step2"
            _fields, evidence = read_table(root, "grt_evidence_registry.tsv")
            for row in evidence:
                if row["q_version"] in {"q3", "q4"}:
                    row["q_source_sha256"] = new_hash
            primary = {"segment_kind": "source", "length": 4, "dataset_name": "primary",
                       "contig_name": "primary1", "source_start": 1, "source_end": 4,
                       "orientation": "+", "source_card_key": "primary:primary1:Chr01:normal",
                       "evidence_ids": ["ev-ref-primary"]}
            patch = {**primary, "dataset_name": "support", "contig_name": "donor1",
                     "source_card_key": parent["source_card_key"],
                     "evidence_ids": parent["evidence_ids"]}
            q2_paths = {"Chr01": [primary, patch]}
            q3_paths = {"Chr01": [primary, {**patch, "source_start": 2, "length": 3}]}
            s2 = {"events": [parent], "q_rows": q_rows_for_paths("q2", ["Chr01"], q2_paths),
                  "usage_rows": usage, "evidence_rows": evidence}
            correction = {**copy.deepcopy(parent), "event_id": "trim-patch", "stage": "step3",
                          "action": "delete", "source": None, "source_card_key": "",
                          "final_path_segment_id": "", "evidence_ids": [], "usage_ids": [],
                          "q_before": {"version": "q2", "start": 5, "end": 5, "sha256": old_hash},
                          "q_after": {"version": "q3", "start": 5, "end": 5, "sha256": new_hash},
                          "edit": {"operation": "replace_interval", "input_start": 5,
                                   "input_end": 5, "input_coordinate_space": "q2_1_based_closed"}}
            s3 = {"events": [correction], "q_rows": q_rows_for_paths("q3", ["Chr01"], q3_paths),
                  "usage_rows": [], "q_input_version": "q2", "q_input_sha256": old_hash,
                  "q_output_version": "q3", "q_output_sha256": new_hash}
            reconcile_step2_events_with_step3(s2, s3)
            events = s2["events"] + s3["events"]
            (root / "metadata/grt_events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events))
            for name, rows in (("grt_donor_usage.tsv", s2["usage_rows"] + s3["usage_rows"]),
                               ("grt_evidence_registry.tsv", evidence)):
                fields, _old_rows = read_table(root, name)
                write_table(root, name, fields, rows)
            fields, rows = read_table(root, "grt_q_segments.tsv")
            write_table(root, "grt_q_segments.tsv", fields, rows + s2["q_rows"] + s3["q_rows"])
            fields, rows = read_table(root, "grt_stage_status.tsv")
            for row in rows:
                for side in ("input", "output"):
                    if row[f"q_{side}_version"] in {"q3", "q4"}:
                        row[f"q_{side}_sha256"] = new_hash
            write_table(root, "grt_stage_status.tsv", fields, rows)
            child = s3["events"][-1]
            fields, rows = read_table(root, "grt_used_contigs.tsv")
            rows[0]["accepted_event_ids_json"] = json.dumps([child["event_id"]])
            rows[0]["final_path_segment_ids_json"] = json.dumps([child["final_path_segment_id"]])
            write_table(root, "grt_used_contigs.tsv", fields, rows)
            final_path = build_final_path(["Chr01"], q3_paths, {"Chr01": "AAAACCC"}, events)
            (root / "metadata/grt_final_path.json").write_text(json.dumps(final_path))
            validate_contract(root, SCHEMA_PATH)
            # The original exact event/source guard still rejects a forged projection.
            child["source"]["start"] = 1
            (root / "metadata/grt_events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events))
            with self.assertRaisesRegex(Exception, "source intervals disagree"):
                validate_contract(root, SCHEMA_PATH)

    def test_complete_source_is_unchanged(self):
        s2, s3, *_ = self.fixture(retained=((101, 120),), cuts=())
        original = copy.deepcopy((s2, s3))
        reconcile_step2_events_with_step3(s2, s3)
        self.assertEqual((s2, s3), original)

    def test_superseded_correction_requires_accepted_refill(self):
        s2, s3, *_ = self.fixture()
        correction = s3["events"][0]
        correction["status"] = "superseded"
        correction["superseded_by_event_id"] = "refill"
        s3["events"].append({"event_id": "refill", "chr": "Chr01", "status": "accepted",
                             "edit": {"input_coordinate_space": "step3_corrected_1_based_closed"}})
        reconcile_step2_events_with_step3(s2, s3)
        self.assertEqual(s3["events"][-1]["retained_after_event_ids"], ["refill"])

    def test_unproven_or_invalid_projection_still_fails_closed(self):
        for mutation in ("no_edit", "wrong_space", "stale_hash", "stale_event_hash",
                         "partial_cut", "wrong_evidence", "overlap", "outside_source",
                         "wrong_length", "filter_only", "missing_q2", "rejected_edit"):
            with self.subTest(mutation=mutation):
                s2, s3, *_ = self.fixture()
                correction = s3["events"][0]
                row = s3["q_rows"][1]
                if mutation == "no_edit":
                    s3["events"] = []
                elif mutation == "wrong_space":
                    correction["edit"]["input_coordinate_space"] = "step3_corrected_1_based_closed"
                elif mutation == "stale_hash":
                    correction["q_before"]["sha256"] = "stale"
                elif mutation == "stale_event_hash":
                    s2["events"][0]["q_after"]["sha256"] = "stale"
                elif mutation == "partial_cut":
                    correction["q_before"]["end"] = correction["edit"]["input_end"] = 12
                elif mutation == "wrong_evidence":
                    # The event also carries other candidate evidence, but only
                    # the original q2 row proves the retained source identity.
                    s2["events"][0]["evidence_ids"].append("other-candidate")
                    row["evidence_ids_json"] = '["other-candidate"]'
                elif mutation == "overlap":
                    s3["q_rows"].append(copy.deepcopy(row))
                elif mutation == "outside_source":
                    row["source_end"] = 121
                elif mutation == "wrong_length":
                    row["q_end"] += 1
                elif mutation == "filter_only":
                    correction["action"] = "filter_component"
                    correction["edit"]["operation"] = "retain_components"
                elif mutation == "missing_q2":
                    s2["q_rows"] = []
                elif mutation == "rejected_edit":
                    correction["status"] = "rejected"
                with self.assertRaises(SystemExit):
                    reconcile_step2_events_with_step3(s2, s3)
                self.assertEqual(s2["events"][0]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
