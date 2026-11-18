"""Python and Windows Rust consume the same frozen package-3 fixture."""
import json
from pathlib import Path
import tempfile
import sys
import unittest

from server.tests.q0_delivery_fixture import materialize
from server.tools.lgz_core.contract.validator import validate_contract
from server.tools.lgz_core.contract.errors import ContractError
from server.tools.lgz_core.q0_publication import validate_prepared_q0, FREEZE, SELECTION
from server.tools.lgz_core.q0_sources import Q0EvidenceError
from server.tools.lgz_core.common import sha256_file

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/grt_contract_v3/frozen_server.json"


class FrozenQ0ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        materialize(json.loads(FIXTURE.read_text()), self.root)

    def edit_json(self, relative, edit):
        path = self.root / relative
        data = json.loads(path.read_text())
        edit(data)
        path.write_text(json.dumps(data))

    def test_historical_package_is_readable_without_installed_selector_identity(self):
        summary = validate_contract(self.root)
        self.assertEqual(summary["schema_version"], "3")
        validate_prepared_q0(self.root)

    def test_later_dataset_is_not_added_to_locked_q0_or_donors(self):
        fixture = json.loads((FIXTURE.parent / "post_freeze_dataset.json").read_text())
        frozen_bytes = (self.root / FREEZE).read_bytes()
        for relative, text in fixture["append"].items():
            path = self.root / relative
            path.write_text(path.read_text() + text)
        materialize(fixture, self.root)
        self.assertEqual(validate_contract(self.root)["datasets"], 2)
        self.assertEqual((self.root / FREEZE).read_bytes(), frozen_bytes)
        # Project addition is legal; silently enlisting it in the old q0 is not.
        self.edit_json(FREEZE, lambda value: value["source_fastas"].update(later="data/datasets/later.fa"))
        with self.assertRaisesRegex(Q0EvidenceError, "locked recipe datasets"):
            validate_prepared_q0(self.root)

    def test_missing_frozen_artifact_binding_is_not_an_optional_check(self):
        self.edit_json(FREEZE, lambda data: data["artifacts"].pop("metadata/grt_contig_quality.tsv"))
        with self.assertRaisesRegex(Q0EvidenceError, "incomplete frozen artifact inventory"):
            validate_prepared_q0(self.root)

    def test_missing_raw_evidence_binding_is_rejected_even_after_rehash(self):
        self.edit_json(SELECTION, lambda data: data["artifact_hashes"].pop(next(iter(data["artifact_hashes"]))))
        digest = sha256_file(self.root / SELECTION)
        def update(data):
            data["selection_sha256"] = digest
            data["artifacts"][SELECTION] = digest
        self.edit_json(FREEZE, update)
        with self.assertRaisesRegex(Q0EvidenceError, "incomplete q0 raw evidence inventory"):
            validate_prepared_q0(self.root)

    def test_changed_source_availability_is_rejected(self):
        self.edit_json(FREEZE, lambda data: data["sources"][0].update(available=[{"start": 0, "end": 2000}]))
        with self.assertRaisesRegex(ContractError, "availability"):
            validate_contract(self.root)

    def test_missing_q0_source_card_is_rejected(self):
        path = self.root / "metadata/grt_used_contigs.tsv"
        path.write_text(path.read_text().splitlines()[0] + "\n")
        with self.assertRaisesRegex(ContractError, "used-contig cards do not exactly match"):
            validate_contract(self.root)

    def test_final_path_root_evidence_must_match_q4(self):
        self.edit_json("metadata/grt_final_path.json", lambda data: data["chromosomes"][0]["segments"][0].update(evidence_ids=[]))
        with self.assertRaisesRegex(ContractError, "q4 source mapping"):
            validate_contract(self.root)


    def test_schema3_app_projection_matches_shared_full_and_no_fasta_fixtures(self):
        tools = str(Path(__file__).parents[1] / "tools")
        sys.path.insert(0, tools)
        try:
            from lgz_app_package import build
            for full, name in ((True, "frozen_app_full.json"), (False, "frozen_app_no_fasta.json")):
                with self.subTest(full=full):
                    staging = self.root / ("app_full" if full else "app_no_fasta")
                    build(self.root, staging, full)
                    expected = json.loads((FIXTURE.parent / name).read_text())["files"]
                    actual = {p.relative_to(staging).as_posix(): p.read_text() for p in staging.rglob("*") if p.is_file()}
                    self.assertEqual(actual, expected)
                    self.assertFalse((staging / FREEZE).exists())
                    self.assertEqual(json.loads((staging / "metadata/grt_app_manifest.json").read_text())["schema_version"], "3")
        finally:
            sys.path.remove(tools)

    def test_bad_server_freeze_cannot_replace_existing_app_projection(self):
        tools = str(Path(__file__).parents[1] / "tools")
        sys.path.insert(0, tools)
        try:
            from lgz_app_package import build
            staging = self.root / "app"
            staging.mkdir()
            (staging / "preserve.txt").write_text("previous verified output")
            self.edit_json(FREEZE, lambda data: data["artifacts"].clear())
            with self.assertRaisesRegex(Exception, "incomplete frozen artifact inventory"):
                build(self.root, staging, True)
            self.assertEqual((staging / "preserve.txt").read_text(), "previous verified output")
        finally:
            sys.path.remove(tools)

    def test_multi_dataset_reverse_and_n_adjacency_fixture_also_passes_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(json.loads((FIXTURE.parent / "frozen_bridge_server.json").read_text()), root)
            self.assertEqual(validate_contract(root)["schema_version"], "3")

    def test_source_free_event_cannot_be_forged_into_an_accepted_source_edit(self):
        path = self.root / "metadata/grt_events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        event = next(event for event in events if event["source"] is None)
        event["action"] = "fill"
        event["status"] = "accepted"
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
        with self.assertRaisesRegex(ContractError, "requires source provenance"):
            validate_contract(self.root)
