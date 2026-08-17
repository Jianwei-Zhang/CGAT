import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
MODULE_PATH = REPO_ROOT / "server" / "tools" / "grt_contract.py"
SCHEMA_PATH = REPO_ROOT / "server" / "contracts" / "grt_precomputed_v2.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "grt_contract_v2"
VALID_BUNDLE = FIXTURE_ROOT / "valid" / "gpm_server"

from server.tools import grt_contract as GRT_CONTRACT


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
    def test_required_server_strategy_classification_and_fragment_tables_are_validated(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle_root = Path(temporary_dir) / "gpm_server"
            shutil.copytree(VALID_BUNDLE, bundle_root)
            metadata = bundle_root / "metadata"

            def write_table(name, fields, rows):
                with (metadata / name).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(rows)

            write_table(
                "grt_donor_fragments.tsv",
                [
                    "donor_set_id", "member_id", "fragment_id", "fasta_record_name",
                    "fragment_start", "fragment_end", "fragment_length", "sequence_sha256",
                    "left_boundary", "right_boundary",
                ],
                [{
                    "donor_set_id": "d0-test",
                    "member_id": "d0-donor1-1-4",
                    "fragment_id": "d0-fragment-test",
                    "fasta_record_name": "d0__support__donor1__1_4",
                    "fragment_start": 1,
                    "fragment_end": 4,
                    "fragment_length": 4,
                    "sequence_sha256": "90b4853e06e722c63b4270463cf558684d7a1e77605d3ad36489d6146e42ab87",
                    "left_boundary": "true",
                    "right_boundary": "true",
                }],
            )
            write_table(
                "grt_step2_strategies.tsv",
                [
                    "chr", "strategy", "strategy_applied", "gap_count",
                    "patch_candidate_count", "validated_patch_count", "accepted_patch_count",
                    "fallback_candidate_count", "accepted_fallback_count", "reason",
                ],
                [{
                    "chr": "Chr01",
                    "strategy": "partial_success_no_fixer",
                    "strategy_applied": "patcher_result",
                    "gap_count": 1,
                    "patch_candidate_count": 1,
                    "validated_patch_count": 1,
                    "accepted_patch_count": 1,
                    "fallback_candidate_count": 0,
                    "accepted_fallback_count": 0,
                    "reason": "fixture",
                }],
            )
            event = {
                "run_id": "run-test",
                "event_id": "evt-step3-classification",
                "stage": "step3",
                "chr": "Chr01",
                "object_id": "gap-step3-classification",
                "action": "correct_boundary",
                "status": "unresolved",
                "reason": "fixture_classification",
                "q_before": {
                    "version": "q2", "start": 1, "end": 4,
                    "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                },
                "q_after": {
                    "version": "q3", "start": 1, "end": 4,
                    "sha256": "312928223060ab1febdcedd56532d45eab299979a64b219df997979212c81481",
                },
                "source": None,
                "evidence_ids": [],
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "classification": {
                    "error_type": "type2",
                    "error_subtype": "direction_conflict",
                    "features": ["direction_conflict"],
                    "confidence": "high",
                    "confidence_score": 0.8,
                    "gap_in_error_region": True,
                },
                "repair_mode": "aggressive",
                "fragment_id": "d0-fragment-test",
            }
            events_path = metadata / "grt_events.jsonl"
            with events_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
            write_table(
                "grt_step3_classifications.tsv",
                [
                    "chr", "object_id", "candidate_id", "error_type", "error_subtype",
                    "error_features_json", "confidence", "confidence_score",
                    "gap_in_error_region", "repair_mode", "repair_reason", "outcome",
                    "event_id", "fragment_id", "donor_reuse", "donor_reuse_of",
                ],
                [{
                    "chr": "Chr01",
                    "object_id": "gap-step3-classification",
                    "candidate_id": "candidate-step3-classification",
                    "error_type": "type2",
                    "error_subtype": "direction_conflict",
                    "error_features_json": json.dumps(["direction_conflict"]),
                    "confidence": "high",
                    "confidence_score": 0.8,
                    "gap_in_error_region": "true",
                    "repair_mode": "aggressive",
                    "repair_reason": "fixture",
                    "outcome": "rejected",
                    "event_id": "evt-step3-classification",
                    "fragment_id": "d0-fragment-test",
                    "donor_reuse": "false",
                    "donor_reuse_of": "",
                }],
            )

            summary = GRT_CONTRACT.validate_contract(bundle_root, SCHEMA_PATH)

        self.assertEqual(summary["events"], 2)

    def test_valid_fixture_passes_and_reconstructs_q4(self):
        summary = GRT_CONTRACT.validate_contract(VALID_BUNDLE, SCHEMA_PATH)

        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v2")
        self.assertEqual(summary["schema_version"], "2")
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
        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v2")

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

        self.assertEqual(summary["workflow"], "gpm_grt_precomputed_v2")

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
                    "gpm_grt_precomputed_v2", "gpm_grt_precomputed_v1", 1
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
