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
from server.tools.grt_core.step2_engine import write_refill_projection
from server.tools.grt_core.stage_io import q_rows_for_paths
from server.tools.grt_telomere_finalize import build_final_path
from server.tests.test_grt_contract import VALID_BUNDLE, SCHEMA_PATH
from server.tools.grt_contract import validate_contract
from server.tools.grt_display_evidence import build_display_evidence


def make_retained_delivery_fixture(directory):
    # Historical packages are read-only fixtures. Do not rerun the newly
    # numbered algorithm and relabel its events as an old execution strategy.
    from server.tests.q0_delivery_fixture import materialize
    root = Path(directory) / "gpm_server"
    fixture = VALID_BUNDLE.parents[1] / "retained_source_bundle.json"
    materialize(json.loads(fixture.read_text()), root)
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
