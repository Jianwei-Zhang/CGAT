#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_orchestration.py"
SPEC = importlib.util.spec_from_file_location("run_orchestration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_orchestration = importlib.util.module_from_spec(SPEC)
sys.modules["run_orchestration"] = run_orchestration
SPEC.loader.exec_module(run_orchestration)


class RunOrchestrationContractTests(unittest.TestCase):
    def test_build_unit_plan_has_stable_dependencies(self):
        plan = run_orchestration.build_unit_plan(
            ["hifiasm", "flye"],
            ["Chr01", "Chr02"],
        )
        self.assertEqual(
            [item.unit_id for item in plan],
            [
                "ref:hifiasm",
                "ref:flye",
                "assign",
                "grt_prepare",
                "grt_step1",
                "grt_step23",
                "grt_telomere_finalize",
                "chr:Chr01",
                "chr:Chr02",
                "finalize_evidence",
                "package_full",
                "package_light",
            ],
        )
        self.assertEqual(plan[2].dependencies, ("ref:hifiasm", "ref:flye"))
        self.assertEqual(plan[9].dependencies, ("chr:Chr01", "chr:Chr02"))

    def test_unit_ids_validate_names_and_preserve_pair_direction(self):
        self.assertEqual(
            run_orchestration.chromosome_self_unit_id("Chr01", "hifiasm"),
            "chr:Chr01:self:hifiasm",
        )
        self.assertEqual(
            run_orchestration.chromosome_pair_unit_id("Chr01", "hifiasm", "flye"),
            "chr:Chr01:pair:hifiasm:flye",
        )
        self.assertEqual(
            run_orchestration.chromosome_scan_unit_id("Chr01", "telomere"),
            "chr:Chr01:telomere_scan",
        )
        with self.assertRaises(run_orchestration.OrchestrationContractError):
            run_orchestration.reference_unit_id("bad/name")
        with self.assertRaises(run_orchestration.OrchestrationContractError):
            run_orchestration.chromosome_pair_unit_id("Chr01", "same", "same")

    def test_plan_rejects_empty_or_duplicate_domains(self):
        with self.assertRaises(run_orchestration.OrchestrationContractError):
            run_orchestration.build_unit_plan([], ["Chr01"])
        with self.assertRaises(run_orchestration.OrchestrationContractError):
            run_orchestration.build_unit_plan(["ds", "ds"], ["Chr01"])
        with self.assertRaises(run_orchestration.OrchestrationContractError):
            run_orchestration.build_unit_plan(["ds"], [])

    def test_fingerprint_is_canonical(self):
        left = run_orchestration.fingerprint({"b": 2, "a": [1, 3]})
        right = run_orchestration.fingerprint({"a": [1, 3], "b": 2})
        self.assertEqual(left, right)

    def test_file_identity_and_atomic_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("content\n", encoding="utf-8")
            identity = run_orchestration.file_identity(source, relative_to=root)
            self.assertEqual(identity["path"], "source.txt")
            self.assertEqual(identity["size"], len(b"content\n"))
            output = root / "state/checkpoint.json"
            run_orchestration.atomic_write_json(output, {"identity": identity})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["identity"], identity)
            self.assertEqual(list(output.parent.glob(".*.tmp.*")), [])

    def test_validate_paf_accepts_empty_and_valid_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty = root / "empty.paf"
            empty.write_text("", encoding="utf-8")
            self.assertEqual(run_orchestration.validate_paf(empty).record_count, 0)

            valid = root / "valid.paf"
            valid.write_text(
                "# generated fixture\n"
                "query\t100\t0\t80\t+\ttarget\t120\t5\t85\t75\t80\t60\ttp:A:P\n",
                encoding="utf-8",
            )
            self.assertEqual(run_orchestration.validate_paf(valid).record_count, 1)

    def test_validate_paf_rejects_malformed_records(self):
        invalid_rows = [
            "query\t100\t0\t80\t+\ttarget\t120\t5\t85\t75\t80\n",
            "query\t100\t0\t101\t+\ttarget\t120\t5\t85\t75\t80\t60\n",
            "query\t100\t0\t80\t?\ttarget\t120\t5\t85\t75\t80\t60\n",
            "query\t100\t0\t80\t+\ttarget\t120\t5\t85\t81\t80\t60\n",
            "query\t100\t0\t80\t+\ttarget\t120\t5\t85\t75\t80\t256\n",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.paf"
            for row in invalid_rows:
                path.write_text(row, encoding="utf-8")
                with self.subTest(row=row):
                    with self.assertRaises(run_orchestration.OrchestrationContractError):
                        run_orchestration.validate_paf(path)

    def test_validate_paf_rejects_invalid_utf8_as_contract_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid-utf8.paf"
            path.write_bytes(b"\xff\n")
            with self.assertRaises(run_orchestration.OrchestrationContractError):
                run_orchestration.validate_paf(path)


if __name__ == "__main__":
    unittest.main()
