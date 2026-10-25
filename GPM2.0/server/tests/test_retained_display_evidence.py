"""Retained children keep historical evidence in the original working coordinates."""
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import unittest

from server.tests import test_grt_app_package as app_fixture
from server.tests import test_grt_prepare_inputs as tables
from server.tools.grt_core.stage_cache import fasta_bytes
from server.tools.grt_core.step3_engine import write_refill_projection, retain_source_fragments
from server.tools.grt_core.stage_io import q_rows_for_paths
from server.tools.grt_telomere_finalize import build_final_path
from server.tests.test_grt_contract import VALID_BUNDLE, SCHEMA_PATH
from server.tools.grt_contract import validate_contract
from server.tools.grt_display_evidence import build_display_evidence


def make_retained_delivery_fixture(directory):
    root = Path(directory) / "gpm_server"
    shutil.copytree(VALID_BUNDLE, root)
    metadata = root / "metadata"
    parent = json.loads((metadata / "grt_events.jsonl").read_text())
    old_hash = parent["q_after"]["sha256"]
    new_fasta = b">Chr01\nAAAACCC\n"
    new_hash = hashlib.sha256(new_fasta).hexdigest()
    for version in ("q3", "q4"):
        (root / f"grt/q/{version}.fa").write_bytes(new_fasta)
    parent.update(stage="step3", action="refill")
    parent["q_before"].update(version="q2", start=5, end=8, sha256=old_hash)
    parent["q_after"].update(version="q2", start=5, end=8)
    usage = tables.read_tsv(metadata / "grt_donor_usage.tsv")
    usage[0]["stage"] = "step3"
    evidence = tables.read_tsv(metadata / "grt_evidence_registry.tsv")
    primary = {"segment_kind": "source", "length": 4, "dataset_name": "primary",
               "contig_name": "primary1", "source_start": 1, "source_end": 4,
               "orientation": "+", "source_card_key": "primary:primary1:Chr01:normal",
               "evidence_ids": ["ev-ref-primary"]}
    patch = {**primary, "dataset_name": "support", "contig_name": "donor1",
             "source_card_key": parent["source_card_key"], "evidence_ids": parent["evidence_ids"]}
    before = {"Chr01": [primary, patch]}
    after = {"Chr01": [primary, {**patch, "source_end": 1, "length": 1},
                        {**patch, "source_start": 3, "length": 2}]}
    history = {"events": [parent], "usage_rows": usage, "evidence_rows": evidence}
    correction = {**copy.deepcopy(parent), "event_id": "trim-refill", "action": "delete",
                  "source": None, "source_card_key": "", "final_path_segment_id": "",
                  "evidence_ids": [], "usage_ids": [],
                  "q_before": {"version": "q2", "start": 6, "end": 6, "sha256": old_hash},
                  "q_after": {"version": "q3", "start": 6, "end": 6, "sha256": new_hash},
                  "edit": {"operation": "replace_interval", "input_start": 6, "input_end": 6,
                           "input_coordinate_space": "q2_1_based_closed"}}
    output = {"events": [correction], "q_rows": q_rows_for_paths("q3", ["Chr01"], after),
              "usage_rows": [], "q_input_version": "q2", "q_input_sha256": old_hash,
              "q_output_version": "q3", "q_output_sha256": new_hash}
    assert retain_source_fragments(parent, q_rows_for_paths("q2", ["Chr01"], before), history, output)
    children = [event for event in output["events"] if event.get("retained_from_event_id")]
    events = [parent, *output["events"]]
    (metadata / "grt_events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
    tables.write_tsv(metadata / "grt_donor_usage.tsv", list(usage[0]), [*usage, *output["usage_rows"]])
    stages = tables.read_tsv(metadata / "grt_stage_status.tsv")
    for row in stages:
        for side in ("input", "output"):
            if row[f"q_{side}_version"] in {"q3", "q4"}: row[f"q_{side}_sha256"] = new_hash
    tables.write_tsv(metadata / "grt_stage_status.tsv", list(stages[0]), stages)
    cards = tables.read_tsv(metadata / "grt_used_contigs.tsv")
    cards[0]["accepted_event_ids_json"] = json.dumps([event["event_id"] for event in children])
    cards[0]["final_path_segment_ids_json"] = json.dumps([event["final_path_segment_id"] for event in children])
    tables.write_tsv(metadata / "grt_used_contigs.tsv", list(cards[0]), cards)
    final = build_final_path(["Chr01"], after, {"Chr01": "AAAACCC"}, events)
    (metadata / "grt_final_path.json").write_text(json.dumps(final))

    artifact = root / "grt/evidence/step3/refill/round1"
    artifact.mkdir(parents=True)
    flanks = [("flank__gap-1__L", "AA"), ("flank__gap-1__R", "AA")]
    (artifact / "flanks.fa").write_bytes(fasta_bytes(flanks))
    (artifact / "result.paf").write_text(
        "flank__gap-1__L\t2\t0\t2\t+\td0__support__donor1__1_4\t4\t0\t2\t2\t2\t60\n"
        "flank__gap-1__R\t2\t0\t2\t+\td0__support__donor1__1_4\t4\t2\t4\t2\t2\t60\n")
    # Use the actual donor-member record name from the frozen source registry.
    member = tables.read_tsv(metadata / "grt_donor_members.tsv")[0]
    paf = artifact / "result.paf"
    paf.write_text(paf.read_text().replace("d0__support__donor1__1_4", member["fasta_record_name"]))
    gap = {"chr": "Chr01", "start0": 2, "end0": 4}
    working = q_rows_for_paths("q2_corrected_round1", ["Chr01"], {"Chr01": [
        {**primary, "length": 2, "source_end": 2},
        {"segment_kind": "gap", "length": 2, "dataset_name": "", "contig_name": "",
         "source_start": None, "source_end": None, "orientation": "", "source_card_key": "", "evidence_ids": []},
        {**primary, "length": 2, "source_start": 3}]})
    projection = write_refill_projection(artifact, "Chr01", "AANNAA", working, flanks,
                                        {name: (gap, name[-1]) for name, _ in flanks})
    profile = next(row for row in evidence if row["evidence_id"] == parent["evidence_ids"][0])
    profile.update(stage="step3", evidence_type="corrected_gap_flank_refill",
                   q_version="q2", q_source_sha256=old_hash,
                   query_artifact_relpath=(artifact / "flanks.fa").relative_to(root).as_posix(),
                   query_sha256=hashlib.sha256((artifact / "flanks.fa").read_bytes()).hexdigest(),
                   raw_artifact_relpath=paf.relative_to(root).as_posix(),
                   raw_artifact_sha256=hashlib.sha256(paf.read_bytes()).hexdigest(),
                   parameters_json=json.dumps({"flank_projection_relpath": projection.relative_to(root).as_posix(),
                                               "flank_projection_sha256": hashlib.sha256(projection.read_bytes()).hexdigest()}))
    tables.write_tsv(metadata / "grt_evidence_registry.tsv", list(evidence[0]), evidence)
    fields = ["candidate_id", "event_id", "stage", "chr", "object_id", "member_id",
              "source_dataset", "source_contig", "outcome", "left_line", "right_line"]
    candidate = dict(zip(fields, ["refill-original", parent["event_id"], "step3", "Chr01", "gap-1",
                                 member["member_id"], "support", "donor1", "accepted", "1", "2"]))
    tables.write_tsv(root / "grt/evidence/step3/refill_candidates.tsv", fields, [candidate])
    validate_contract(root, SCHEMA_PATH)
    return root


class RetainedDisplayEvidenceTests(unittest.TestCase):
    def fixture(self, *, split=False, source_orientation="+", alignment_orientation="+"):
        helper = app_fixture.GrtAppPackageTests()
        helper.setUp()
        self.addCleanup(helper.tearDown)
        args = list(helper._write_display_evidence_fixture())
        root, final_path, _, _ = args
        metadata = root / "metadata"
        artifact = root / "grt/evidence/step3/refill/round1"
        # The historical q path differs deliberately from q2 and final neighbours.
        sequence = "A" * 320 + "N" * 80 + "A" * 600
        q_rows = [
            {"chr": "Chr01", "segment_kind": "source", "q_start": 1, "q_end": 320,
             "dataset_name": "primary", "contig_name": "primary1", "source_start": 1,
             "source_end": 320, "orientation": source_orientation},
            {"chr": "Chr01", "segment_kind": "gap", "q_start": 321, "q_end": 400},
            {"chr": "Chr01", "segment_kind": "source", "q_start": 401, "q_end": 1000,
             "dataset_name": "primary", "contig_name": "primary1", "source_start": 401,
             "source_end": 1000, "orientation": "+"},
        ]
        gap = {"chr": "Chr01", "start0": 320, "end0": 400}
        flanks = [("flank__gap-1__L", "A" * 100), ("flank__gap-1__R", "A" * 100)]
        query_map = {name: (gap, name[-1]) for name, _ in flanks}
        (artifact / "flanks.fa").write_bytes(fasta_bytes(flanks))
        projection_path = write_refill_projection(artifact, "Chr01", sequence, q_rows, flanks, query_map)
        evidence = tables.read_tsv(metadata / "grt_evidence_registry.tsv")
        for row in evidence:
            row.update(parameters_json="{}", query_sha256="", query_artifact_relpath="", raw_artifact_sha256="")
        profile = next(row for row in evidence if row["evidence_id"] == "ev-local")
        profile.update(
            query_sha256=hashlib.sha256((artifact / "flanks.fa").read_bytes()).hexdigest(),
            query_artifact_relpath=(artifact / "flanks.fa").relative_to(root).as_posix(),
            parameters_json=json.dumps({
                "flank_projection_relpath": projection_path.relative_to(root).as_posix(),
                "flank_projection_sha256": hashlib.sha256(projection_path.read_bytes()).hexdigest(),
            }),
        )
        tables.write_tsv(metadata / "grt_evidence_registry.tsv", list(evidence[0]), evidence)
        paf = artifact / "result.paf"
        paf.write_text(paf.read_text().replace("\t+\t", f"\t{alignment_orientation}\t"))
        profile["raw_artifact_sha256"] = hashlib.sha256(paf.read_bytes()).hexdigest()
        tables.write_tsv(metadata / "grt_evidence_registry.tsv", list(evidence[0]), evidence)
        path = metadata / "grt_events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        parent = next(e for e in events if e["event_id"] == "event-final")
        old_segment = final_path["chromosomes"][0]["segments"][1]
        parent.update(source=copy.deepcopy(old_segment["source"]),
                      source_card_key="support:donor1:Chr01:normal",
                      status="superseded", retained_event_ids=[])
        segments = []
        for index, (start, end) in enumerate(((502, 504), (508, 510)) if split else ((502, 510),)):
            child_id = f"retained-{index}"
            child = {**copy.deepcopy(parent), "event_id": child_id, "status": "accepted",
                     "action": "patch", "retained_from_event_id": parent["event_id"],
                     "superseded_event_ids": [parent["event_id"], "event-precursor"] if not index else []}
            child.pop("retained_event_ids")
            child["source"].update(start=start, end=end)
            parent["retained_event_ids"].append(child_id)
            events.append(child)
            segment = copy.deepcopy(old_segment)
            segment.update(event_id=child_id, segment_id=f"retained-segment-{index}", source=child["source"])
            segments.append(segment)
        parent["superseded_by_event_id"] = "retained-0"
        path.write_text("".join(json.dumps(e) + "\n" for e in events))
        left, _, right = final_path["chromosomes"][0]["segments"]
        left["source"].update(start=801, end=900)
        right["source"].update(start=901, end=1000)
        final_path["chromosomes"][0]["segments"] = [left, *segments, right]
        return args, projection_path

    def test_all_split_children_keep_refill_precursors_without_using_current_neighbours(self):
        args, _ = self.fixture(split=True)
        evidence = build_display_evidence(*args)["Chr01"]
        local = [row for row in evidence if row["tool"] == "minimap2"]
        self.assertEqual(len(local), 4)
        for index in range(2):
            child_rows = [row for row in local if row["event_id"] == f"retained-{index}"]
            self.assertEqual(len(child_rows), 2)
            self.assertTrue(all(row["association"] == "supporting_precursor" for row in child_rows))
            self.assertTrue(all(row["supporting_event_id"] == "event-final" for row in child_rows))
            left = next(row for row in child_rows if row["role"] == "left_anchor")
            right = next(row for row in child_rows if row["role"] == "right_anchor")
            self.assertEqual((left["target"]["start"], left["target"]["end"]), (241, 320))
            self.assertEqual((right["target"]["start"], right["target"]["end"]), (401, 490))
        self.assertEqual(evidence, build_display_evidence(*args)["Chr01"])
        self.assertEqual(len({row["evidence_id"] for row in evidence}), len(evidence))

    def test_historical_source_and_alignment_directions_are_composed(self):
        for source_orientation in ("+", "-"):
            for alignment_orientation in ("+", "-"):
                with self.subTest(source=source_orientation, alignment=alignment_orientation):
                    args, _ = self.fixture(source_orientation=source_orientation,
                                           alignment_orientation=alignment_orientation)
                    left = next(row for row in build_display_evidence(*args)["Chr01"]
                                if row["tool"] == "minimap2" and row["role"] == "left_anchor")
                    self.assertEqual((left["target"]["start"], left["target"]["end"]),
                                     (241, 320) if source_orientation == "+" else (1, 80))
                    self.assertEqual(left["target"]["orientation"],
                                     "+" if source_orientation == alignment_orientation else "-")

    def test_refill_projection_does_not_use_public_q2_coordinates(self):
        args, _ = self.fixture()
        path = args[0] / "metadata/grt_q_segments.tsv"
        rows = tables.read_tsv(path)
        rows[0]["orientation"] = "-"
        tables.write_tsv(path, list(rows[0]), rows)
        left = next(row for row in build_display_evidence(*args)["Chr01"]
                    if row["tool"] == "minimap2" and row["role"] == "left_anchor")
        self.assertEqual(left["target"]["orientation"], "+")
        self.assertEqual((left["target"]["start"], left["target"]["end"]), (241, 320))

    def test_changed_paf_or_flank_fasta_is_not_projected(self):
        for name in ("result.paf", "flanks.fa"):
            with self.subTest(artifact=name):
                args, _ = self.fixture()
                path = args[0] / "grt/evidence/step3/refill/round1" / name
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    build_display_evidence(*args)

    def test_nested_retention_is_resolved_to_the_original_refill_once(self):
        args, _ = self.fixture()
        path = args[0] / "metadata/grt_events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        middle = next(row for row in events if row["event_id"] == "retained-0")
        child = copy.deepcopy(middle)
        child.update(event_id="retained-final", retained_from_event_id="retained-0")
        middle.update(status="superseded", retained_event_ids=["retained-final"])
        events.append(child)
        path.write_text("".join(json.dumps(row) + "\n" for row in events))
        args[1]["chromosomes"][0]["segments"][1]["event_id"] = "retained-final"
        local = [row for row in build_display_evidence(*args)["Chr01"] if row["tool"] == "minimap2"]
        self.assertEqual(len(local), 2)
        self.assertTrue(all(row["supporting_event_id"] == "event-final" for row in local))

    def test_missing_legacy_projection_is_explicit_not_silently_dropped(self):
        args, _ = self.fixture()
        path = args[0] / "metadata/grt_evidence_registry.tsv"
        rows = tables.read_tsv(path)
        next(row for row in rows if row["evidence_id"] == "ev-local")["parameters_json"] = "{}"
        tables.write_tsv(path, list(rows[0]), rows)
        with self.assertRaisesRegex(ValueError, "regenerate Step3"):
            build_display_evidence(*args)

    def test_tampered_projection_and_wrong_query_binding_are_rejected(self):
        for corruption in ("checksum", "query", "path", "chr"):
            with self.subTest(corruption=corruption):
                args, path = self.fixture()
                payload = json.loads(path.read_text())
                if corruption == "query": payload["query_sha256"] = "0" * 64
                if corruption == "path": payload["working_q_rows"][0]["q_start"] = 2
                if corruption == "chr": payload["chr"] = "Chr02"
                path.write_text(json.dumps(payload) + " ")
                if corruption != "checksum":
                    registry = args[0] / "metadata/grt_evidence_registry.tsv"
                    rows = tables.read_tsv(registry)
                    row = next(row for row in rows if row["evidence_id"] == "ev-local")
                    params = json.loads(row["parameters_json"])
                    params["flank_projection_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    row["parameters_json"] = json.dumps(params)
                    tables.write_tsv(registry, list(rows[0]), rows)
                with self.assertRaises(ValueError):
                    build_display_evidence(*args)

    def test_retained_server_to_full_and_light_app_delivery_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_retained_delivery_fixture(directory)
            for include_fasta in (True, False):
                stage = Path(directory) / ("app-full" if include_fasta else "app-light")
                app_fixture.grt_app_package.build(root, stage, include_fasta=include_fasta)
                final = json.loads((stage / "metadata/grt_final_path.json").read_text())
                evidence = final["chromosomes"][0]["display_evidence"]
                self.assertEqual(len(evidence), 4)
                self.assertTrue(all(row["association"] == "supporting_precursor" for row in evidence))
                self.assertEqual(len({row["event_id"] for row in evidence}), 2)
                self.assertEqual(final["chromosomes"][0]["q4_length"], 7)

    def test_contract_rejects_corrupt_projection_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_retained_delivery_fixture(directory)
            (root / "grt/evidence/step3/refill/round1/flank_projection.json").write_text("{}")
            with self.assertRaisesRegex(Exception, "CHECKSUM_MISMATCH"):
                validate_contract(root, SCHEMA_PATH)

    def test_invalid_retained_lineage_fails_closed(self):
        for corruption in ("missing", "cycle", "source", "interval", "reverse_link"):
            with self.subTest(corruption=corruption):
                args, _ = self.fixture()
                path = args[0] / "metadata/grt_events.jsonl"
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                child = next(row for row in rows if row["event_id"] == "retained-0")
                if corruption == "missing": child["retained_from_event_id"] = "absent"
                if corruption == "cycle": child["retained_from_event_id"] = child["event_id"]
                if corruption == "source": child["source"]["contig"] = "another"
                if corruption == "interval": child["source"]["start"] = 1
                if corruption == "reverse_link": next(row for row in rows if row["event_id"] == "event-final")["retained_event_ids"] = []
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                with self.assertRaises(ValueError):
                    build_display_evidence(*args)


if __name__ == "__main__":
    unittest.main()
