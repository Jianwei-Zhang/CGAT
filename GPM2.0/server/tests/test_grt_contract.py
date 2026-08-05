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
