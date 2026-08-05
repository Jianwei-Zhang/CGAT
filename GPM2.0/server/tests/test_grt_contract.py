import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
MODULE_PATH = REPO_ROOT / "server" / "tools" / "grt_contract.py"
SCHEMA_PATH = REPO_ROOT / "server" / "contracts" / "grt_precomputed_v1.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "grt_contract_v1"
VALID_BUNDLE = FIXTURE_ROOT / "valid" / "gpm_server"

SPEC = importlib.util.spec_from_file_location("grt_contract", MODULE_PATH)
GRT_CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRT_CONTRACT)


def apply_operation(bundle_root, operation):
    path = bundle_root / operation["path"]
    if operation["type"] == "remove":
        path.unlink()
        return
    if operation["type"] == "replace_text":
        content = path.read_text(encoding="utf-8")
        old = operation["old"]
        count = content.count(old)
        if count != 1:
            raise AssertionError(
                f"mutation expected one occurrence of {old!r} in {path}, found {count}"
            )
        path.write_text(content.replace(old, operation["new"], 1), encoding="utf-8", newline="")
        return
    raise AssertionError(f"unsupported fixture operation: {operation['type']}")


class GrtContractTests(unittest.TestCase):
    def test_valid_fixture_passes_and_reconstructs_q4(self):
        summary = GRT_CONTRACT.validate_contract(VALID_BUNDLE, SCHEMA_PATH)

        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v1")
        self.assertEqual(summary["schema_version"], "1")
        self.assertEqual(summary["donor_sets"], 2)
        self.assertEqual(summary["events"], 1)
        self.assertEqual(summary["segments"], 2)

    def test_invalid_fixture_cases_return_stable_error_codes(self):
        cases = json.loads((FIXTURE_ROOT / "invalid_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 12)

        for case in cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as temporary_dir:
                bundle_root = Path(temporary_dir) / "gpm_server"
                shutil.copytree(VALID_BUNDLE, bundle_root)
                apply_operation(bundle_root, case["operation"])

                with self.assertRaises(GRT_CONTRACT.ContractError) as raised:
                    GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)
                self.assertEqual(raised.exception.code, case["expected_code"])

    def test_cli_reports_machine_readable_summary(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--bundle",
                str(VALID_BUNDLE),
                "--schema",
                str(SCHEMA_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v1")

    def test_empty_telomere_donor_set_is_valid(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            members_path = bundle_root / "metadata/grt_donor_members.tsv"
            members_lines = members_path.read_text(encoding="utf-8").splitlines()
            members_path.write_text(
                "\n".join(line for line in members_lines if not line.startswith("dtel-test\t"))
                + "\n",
                encoding="utf-8",
                newline="",
            )
            manifest_path = bundle_root / "grt/donor/dtel.manifest.tsv"
            manifest_path.write_text(members_lines[0] + "\n", encoding="utf-8", newline="")
            fasta_path = bundle_root / "grt/donor/dtel.fa"
            fasta_path.write_text("", encoding="utf-8", newline="")
            donor_sets_path = bundle_root / "metadata/grt_donor_sets.tsv"
            donor_sets_path.write_text(
                donor_sets_path.read_text(encoding="utf-8").replace(
                    "624d9151605bd17d8f3619eaadf025bb3347e9a336548ec8556463287ba03b33\t1",
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\t0",
                ),
                encoding="utf-8",
                newline="",
            )

            summary = GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)

        self.assertEqual(summary["donor_sets"], 2)

    def test_post_recipe_dataset_does_not_require_retroactive_grt_roles(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            datasets_path = bundle_root / "metadata/datasets.tsv"
            with datasets_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(
                    "later\tlater\t\tdata/datasets/later.fa\t"
                    "data/datasets/later.fa.fai\ttrue\n"
                )
            locator_path = bundle_root / "metadata/source_seq_locator.tsv"
            with locator_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write("later\tlater1\tdata/datasets/later.fa\n")
            later_fasta = bundle_root / "data/datasets/later.fa"
            later_fasta.write_text(">later1\nACGT\n", encoding="utf-8", newline="")
            (bundle_root / "data/datasets/later.fa.fai").write_text(
                "later1\t4\t0\t4\t5\n", encoding="utf-8", newline=""
            )

            summary = GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)

        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v1")

    def test_accepted_filter_event_does_not_require_a_final_path_segment(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            events_path = bundle_root / "metadata/grt_events.jsonl"
            with events_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(
                    json.dumps(
                        {
                            "run_id": "run-test",
                            "event_id": "evt-step1-filter",
                            "stage": "step1_filter",
                            "chr": "Chr01",
                            "object_id": "component-filter-1",
                            "action": "filter_component",
                            "status": "accepted",
                            "reason": "removed_isolated_component",
                            "q_before": {
                                "version": "q0r1",
                                "start": 1,
                                "end": 8,
                                "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                            },
                            "q_after": {
                                "version": "q0f",
                                "start": 1,
                                "end": 8,
                                "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                            },
                            "source": None,
                            "evidence_ids": [],
                            "usage_ids": [],
                            "source_card_key": "",
                            "final_path_segment_id": "",
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )

            summary = GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)

        self.assertEqual(summary["events"], 2)

    def test_accepted_gap_correction_usage_does_not_require_a_final_path_segment(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            events_path = bundle_root / "metadata/grt_events.jsonl"
            with events_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(
                    json.dumps(
                        {
                            "run_id": "run-test",
                            "event_id": "evt-step3-correction",
                            "stage": "step3",
                            "chr": "Chr01",
                            "object_id": "gap-step3-1",
                            "action": "replace",
                            "status": "accepted",
                            "reason": "crossing_alignment_error_region",
                            "q_before": {
                                "version": "q2",
                                "start": 1,
                                "end": 4,
                                "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                            },
                            "q_after": {
                                "version": "q3",
                                "start": 1,
                                "end": 4,
                                "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                            },
                            "source": {
                                "dataset": "support",
                                "contig": "donor1",
                                "start": 1,
                                "end": 4,
                                "orientation": "+",
                                "original_assignment": "unplaced",
                            },
                            "evidence_ids": [],
                            "usage_ids": ["use-step3-correction"],
                            "source_card_key": "",
                            "final_path_segment_id": "",
                            "edit": {
                                "operation": "replace_interval",
                                "replacement_kind": "gap",
                            },
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            usage_path = bundle_root / "metadata/grt_donor_usage.tsv"
            with usage_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(
                    "use-step3-correction\td0-test\td0-donor1-1-4\tsupport\tdonor1\t"
                    "1\t4\tstep3\taccepted\tevt-step3-correction\t\tstructural_evidence\n"
                )

            summary = GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)

        self.assertEqual(summary["events"], 2)

    def test_cli_rejects_legacy_package(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            package_path = bundle_root / "metadata" / "package.tsv"
            package_path.write_text(
                package_path.read_text(encoding="utf-8").replace(
                    "gpm_grt_precomputed_v1", "gpm_legacy", 1
                ),
                encoding="utf-8",
                newline="",
            )

            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--bundle", str(bundle_root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("ERROR UNSUPPORTED_SCHEMA:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
