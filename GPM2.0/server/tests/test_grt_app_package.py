from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_TOOLS = REPO_ROOT / "server/tools"
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/grt_contract_v2/valid/gpm_server"
sys.path.insert(0, str(SERVER_TOOLS))

import grt_app_package  # noqa: E402


class GrtAppPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source"
        shutil.copytree(FIXTURE_ROOT, self.source)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_build_emits_display_contract_schema_two(self) -> None:
        staging = self.root / "staging"

        grt_app_package.build(self.source, staging, include_fasta=True)

        with (staging / "metadata/package.tsv").open(newline="", encoding="utf-8") as handle:
            package = next(csv.DictReader(handle, delimiter="\t"))
        final_path = json.loads((staging / "metadata/grt_final_path.json").read_text(encoding="utf-8"))
        self.assertEqual(package["final_path_schema_version"], "2")
        self.assertEqual(final_path["schema_version"], "2")
        self.assertEqual(final_path["workflow"], "gpm_grt_app_precomputed_v2")
        self.assertNotIn("event_id", final_path["chromosomes"][0]["segments"][0])

    def test_build_rejects_final_path_source_without_display_card(self) -> None:
        assignments = self.source / "metadata/chr_assignments.tsv"
        with assignments.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = [row for row in reader if row["dataset_name"] != "primary"]
            fieldnames = list(reader.fieldnames or [])
        with assignments.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

        with self.assertRaisesRegex(ValueError, "no App display source card for primary:primary1:Chr01"):
            grt_app_package.build(self.source, self.root / "staging", include_fasta=False)

    def test_build_rejects_invalid_display_source_interval(self) -> None:
        final_path_file = self.source / "metadata/grt_final_path.json"
        payload = json.loads(final_path_file.read_text(encoding="utf-8"))
        payload["chromosomes"][0]["segments"][0]["source"]["end"] = 5
        final_path_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )

        with self.assertRaisesRegex(ValueError, "invalid App source interval"):
            grt_app_package.build(self.source, self.root / "staging", include_fasta=False)


if __name__ == "__main__":
    unittest.main()
