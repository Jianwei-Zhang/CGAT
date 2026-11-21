"""Real serializer/source validation over a frozen LGZ scientific fixture."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from server.tests.refinement_bundle_fixture import create
from refinement_bundle_validate import validate_payload
from refinement_bundle import seal_manifest, MANIFEST, read_table


@unittest.skipUnless(shutil.which("samtools"), "fixture admission requires FASTA indexing")
class RefinedBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name) / "workspace"
        cls.result, cls.full, cls.light = create(cls.root)

    def test_both_modes_keep_the_refined_path_and_real_bridge_sources(self):
        full = validate_payload(self.full, full=True)
        light = validate_payload(self.light, full=False)
        self.assertEqual(full["assemblies"], light["assemblies"])
        self.assertEqual((self.full / "metadata/refinement/final_path.json").read_bytes(),
                         (Path(self.result["staging"]) / "final_path.json").read_bytes())
        projected = json.loads((self.full / "metadata/grt_final_path.json").read_text())
        self.assertEqual(projected["schema_version"], "4")
        frozen = json.loads((Path(__file__).resolve().parents[2] / "tests/fixtures/grt_contract_v3/frozen_bridge_server.json").read_text())["files"]
        for name in ("grt_q0_freeze.json", "grt_q0_selection.json"):
            self.assertEqual((self.root / ".runtime/metadata" / name).read_text(), frozen["metadata/" + name])
        self.assertTrue(any(segment.get("refinement_source") for chromosome in projected["chromosomes"] for segment in chromosome["segments"]))
        cards = read_table(self.full / "metadata/grt_used_contigs.tsv")[1]
        patches = [row for row in cards if row["placement_mode"] == "refinement"]
        self.assertTrue(patches)
        self.assertTrue(all(row["ref_alignment_status"] == "not_measured" for row in patches))
        assigned = read_table(self.full / "metadata/chr_assignments.tsv")[1]
        self.assertFalse(any(row["dataset_name"].startswith("cgat_refinement_") for row in assigned))
        self.assertFalse(any(p.suffix in {".fa", ".fasta"} for p in self.light.rglob("*")))
        locators = read_table(self.full / "metadata/source_seq_locator.tsv")[1]
        self.assertTrue(any(row["fasta_relpath"].startswith("data/partitions/") for row in locators))
        self.assertTrue(all(not row["fasta_relpath"].startswith("01_inputs/") for row in locators))
        self.assertTrue(all((self.light / (row["fasta_relpath"] + ".fai")).is_file() for row in locators))
        self.assertFalse(any(p.is_file() for p in (self.full / "data/degap").rglob("*")))
        self.assertNotEqual((self.full / "data/refinement/final.fa").read_bytes(),
                            next(self.root.glob("03_lgz/*/q4.fa")).read_bytes())

    def test_resealed_wrong_source_still_fails_sequence_reconstruction(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "payload"
            shutil.copytree(self.full, copy)
            patch = next((copy / "data/refinement/sources").glob("*.fa"))
            patch.write_text(patch.read_text().replace("GTNNAC", "TTNNAC"))
            manifest = json.loads((copy / MANIFEST).read_text())
            seal_manifest(copy, manifest)
            with self.assertRaisesRegex(ValueError, "reconstruction differs"):
                validate_payload(copy)

    def test_changed_projection_is_not_accepted_even_after_manifest_reseal(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "payload"
            shutil.copytree(self.light, copy)
            path = copy / "metadata/grt_final_path.json"
            data = json.loads(path.read_text())
            data["chromosomes"][0]["segments"][0]["source"]["orientation"] = "+"
            data["chromosomes"][0]["segments"][0]["length"] += 1
            path.write_text(json.dumps(data))
            seal_manifest(copy, json.loads((copy / MANIFEST).read_text()))
            with self.assertRaisesRegex(ValueError, "differs from the authoritative"):
                validate_payload(copy)


if __name__ == "__main__":
    unittest.main()
