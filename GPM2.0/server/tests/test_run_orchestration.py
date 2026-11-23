#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


# Import normally: replacing the CLI module in sys.modules during discovery
# splits its live cache from hash functions already imported by other tools.
from server.tools import run_orchestration


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
                "q0_chr:Chr01",
                "q0_chr:Chr02",
                "q0_evidence",
                "lgz_prepare",
                "grt_step1",
                "grt_step2",
                "grt_step3",
                "chr:Chr01",
                "chr:Chr02",
                "finalize_evidence",
                "package_full",
                "package_light",
            ],
        )
        self.assertEqual(plan[2].dependencies, ("ref:hifiasm", "ref:flye"))
        by_id = {item.unit_id: item for item in plan}
        self.assertEqual(by_id["q0_chr:Chr01"].dependencies, ("assign",))
        self.assertEqual(by_id["q0_chr:Chr02"].dependencies, ("assign",))
        self.assertEqual(by_id["q0_evidence"].dependencies, ("q0_chr:Chr01", "q0_chr:Chr02"))
        self.assertEqual(by_id["lgz_prepare"].dependencies, ("q0_evidence",))
        self.assertEqual(by_id["grt_step1"].dependencies, ("lgz_prepare",))
        self.assertEqual(by_id["chr:Chr01"].dependencies, ("grt_step3",))
        self.assertEqual(by_id["finalize_evidence"].dependencies, ("chr:Chr01", "chr:Chr02"))

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

    def test_file_identity_resolves_twice_and_uses_a_real_hash_only_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "artifact.txt"
            content = b"bound artifact\n"
            path.write_bytes(content)
            expected = {"path": "artifact.txt", "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            with (patch.object(run_orchestration, "file_signature", wraps=run_orchestration.file_signature) as signatures,
                  patch.object(run_orchestration, "_sha256_read", wraps=run_orchestration._sha256_read) as read):
                for n in range(2):
                    self.assertEqual(run_orchestration.file_identity(path, relative_to=root), expected)
                    self.assertEqual(signatures.call_count, 2 * (n + 1))
                    self.assertEqual(read.call_count, 1)

    def test_file_identity_rejects_a_path_retargeted_during_a_cache_hit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second, alias = (root / name for name in ("first", "second", "alias"))
            first.write_bytes(b"aaa")
            second.write_bytes(b"bbb")
            try:
                alias.symlink_to(first)
            except OSError:
                self.skipTest("symlink support required")
            run_orchestration.file_identity(alias)
            original = run_orchestration.file_signature
            def retarget(path):
                observed = original(path)
                if alias.readlink() == first:
                    alias.unlink()
                    alias.symlink_to(second)
                return observed
            with patch.object(run_orchestration, "file_signature", side_effect=retarget):
                with self.assertRaisesRegex(run_orchestration.OrchestrationContractError, "changed during hash reuse"):
                    run_orchestration.file_identity(alias)
            self.assertEqual(run_orchestration.file_identity(alias)["sha256"], hashlib.sha256(b"bbb").hexdigest())

    def test_file_identity_cold_hash_rejects_replacement_after_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact"
            path.write_bytes(b"old")
            original = run_orchestration._sha256_read
            def replace(signature):
                digest = original(signature)
                new = path.with_suffix(".replacement")
                new.write_bytes(b"new")
                new.replace(path)
                return digest
            with patch.object(run_orchestration, "_sha256_read", side_effect=replace):
                with self.assertRaisesRegex(run_orchestration.OrchestrationContractError, "changed while hashing"):
                    run_orchestration.file_identity(path)
            self.assertEqual(run_orchestration.file_identity(path)["sha256"], hashlib.sha256(b"new").hexdigest())

    def test_paf_identity_hashes_actual_bytes_in_the_geometry_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paf = root / "alignment.paf"
            payload = ("#小麦备注\r\nq\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\tcg:Z:10M\r".encode("utf-8") * 25000)
            paf.write_bytes(payload)
            with patch.object(run_orchestration, "_sha256_read", side_effect=AssertionError("second raw pass")):
                first = run_orchestration.paf_file_identity(paf, relative_to=root, require_cigar=True)
                warm = run_orchestration.file_identity(paf, relative_to=root)
            self.assertEqual(first, {"path":"alignment.paf", "size":len(payload),
                                     "sha256":hashlib.sha256(payload).hexdigest()})
            self.assertEqual(first, warm)

    def test_paf_identity_does_not_publish_if_bytes_are_replaced_after_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paf = root / "alignment.paf"
            paf.write_text("# old\n", encoding="utf-8")
            original = run_orchestration._validate_paf_lines
            def replace(handle, path, require_cigar):
                summary = original(handle, path, require_cigar)
                new = paf.with_suffix(".tmp")
                new.write_text("# new\n", encoding="utf-8")
                new.replace(paf)
                return summary
            with patch.object(run_orchestration, "_validate_paf_lines", side_effect=replace):
                with self.assertRaisesRegex(run_orchestration.OrchestrationContractError, "PAF output changed"):
                    run_orchestration.paf_file_identity(paf, relative_to=root, require_cigar=True)
            self.assertEqual(run_orchestration.file_identity(paf, relative_to=root)["sha256"],
                             hashlib.sha256(b"# new\n").hexdigest())

    def test_warm_generic_digest_does_not_replace_paf_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paf = root / "malformed.paf"
            paf.write_text("not a record\n", encoding="utf-8")
            run_orchestration.file_identity(paf, relative_to=root)
            with self.assertRaisesRegex(run_orchestration.OrchestrationContractError, "PAF line 1"):
                run_orchestration.paf_file_identity(paf, relative_to=root, require_cigar=True)

    def test_buffered_paf_lines_match_text_iteration_at_read_boundaries(self):
        # UTF-8 scalar and CRLF across the text decoder's old 8 KiB refill,
        # a record across a binary read-ahead block, and an unterminated tail.
        payload = (b"x"*8191 + "麦\r\n\r#next\n".encode("utf-8") + b"z"*(1024*1024) +
                   "\r\nname\x85not-an-eol\u2028still-one\r\nunterminated tail".encode("utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "read_boundaries.paf"
            for newline in (None, ""):
                for suffix in (b"", b"\r", b"\r\n"):
                    path.write_bytes(payload+suffix)
                    with self.subTest(newline=newline, suffix=suffix):
                        with path.open(encoding="utf-8", newline=newline) as f:
                            old = list(f)
                        with run_orchestration.open_paf_text(path, newline=newline) as f:
                            self.assertEqual(list(f), old)

    def test_buffered_paf_parser_keeps_long_cigar_and_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "boundary.paf"
            path.write_bytes(b"#skip\r\n\r" + b"q\t12000\t0\t12000\t+\tt\t12000\t0\t12000\t12000\t12000\t60\tcg:Z:" + b"1M"*12000)
            self.assertEqual(run_orchestration.validate_paf(path, require_cigar=True).record_count, 1)
            with path.open("ab") as f:
                f.write(b"\r\nbad line")
            with self.assertRaisesRegex(run_orchestration.OrchestrationContractError, "PAF line 4"):
                run_orchestration.validate_paf(path, require_cigar=True)

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
