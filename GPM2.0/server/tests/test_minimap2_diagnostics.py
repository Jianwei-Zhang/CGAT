from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import minimap2_diagnostics as diagnostics

ASSERTION = "minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs' failed."


class Minimap2DiagnosticsTests(unittest.TestCase):
    def test_assertion_is_a_hypothesis_not_oom_or_confirmed_overflow(self):
        for text in (ASSERTION, ASSERTION.replace("mm_update_extra", "mm_fix_cigar")):
            hint = diagnostics.cigar_assertion_hint(text)
            self.assertIn("MINIMAP2_CIGAR_ASSERTION", hint)
            self.assertIn("one possible cause", hint)
            self.assertIn("not a confirmed diagnosis", hint)
            self.assertIn("do not remove -c", hint)
        for text in ("Killed", "oom-kill event", "Assertion x failed", "mm_update_extra unavailable"):
            self.assertEqual(diagnostics.cigar_assertion_hint(text), "")

    def test_only_changed_per_command_log_is_attributed(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "stderr.log"
            self.assertEqual(diagnostics.changed_log_hint(log, None), "")
            log.write_text(ASSERTION)
            before = diagnostics.log_identity(log)
            self.assertEqual(diagnostics.changed_log_hint(log, before), "")
            log.write_text("new attempt\n" + ASSERTION)
            self.assertIn("MINIMAP2_CIGAR_ASSERTION", diagnostics.changed_log_hint(log, before))
            log.write_text("unrelated failure")
            self.assertEqual(diagnostics.changed_log_hint(log, before), "")

    def test_long_fai_is_evidence_only_and_no_fasta_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fai = root / "ref.fa.fai"
            fai.write_text("normal\t268435455\t0\t80\t81\nlong\t268435456\t0\t80\t81\n"
                           "coordinate\t2147483648\t0\t80\t81\n")
            before = fai.read_bytes()
            result = diagnostics.input_summary(root, {"fai_relpath": fai.name, "fasta_relpath": "ref.fa"}, "reference")
            self.assertNotIn("error", result)
            self.assertEqual(result["record_count"], 3)
            self.assertEqual(result["over_cigar_operation_limit"], 2)
            self.assertEqual(result["over_int32_coordinate_limit"], 1)
            self.assertEqual(result["evidence"], "existing_fai_not_content_verified")
            self.assertEqual(fai.read_bytes(), before)
            self.assertFalse((root / "ref.fa").exists())

    def test_missing_invalid_and_escaping_fai_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.fai").write_text("invalid\n")
            (root / "escape.fai").symlink_to("/etc/passwd")
            for name in ("missing.fai", "bad.fai", "escape.fai", "../outside", "/etc/passwd", ""):
                result = diagnostics.input_summary(root, {"fai_relpath": name}, "dataset")
                self.assertIn("error", result, name)
                self.assertNotIn("record_count", result, name)

    def test_runtime_records_both_tool_resolutions_without_changing_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "metadata").mkdir()
            binary = root / "minimap2"
            binary.write_text("#!/bin/sh\necho 2.31-r1302\n")
            binary.chmod(0o755)
            configured = root / "other-minimap2"
            configured.write_text("#!/bin/sh\necho 2.28-r1209\n")
            configured.chmod(0o755)
            with patch.dict(os.environ, {"PATH": str(root)}):
                result = diagnostics.runtime_snapshot(root, {"grt_minimap2": str(configured)})
                self.assertEqual(os.environ["PATH"], str(root))
            self.assertFalse(result["parameters_changed"])
            self.assertFalse(result["automatic_retry"])
            self.assertEqual(result["tools"]["PATH"]["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())
            self.assertNotEqual(result["tools"]["PATH"]["path"], result["tools"]["configured_grt_minimap2"]["path"])
            self.assertTrue(all("error" in row for row in result["inputs"]))

    def test_grt_failure_hint_and_repeated_attempts_preserve_all_evidence(self):
        from grt_core.stage_cache import cached_chromosome_alignment, run_minimap
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "minimap2"
            binary.write_text("#!/bin/sh\necho 'minimap2: mm_update_extra: Assertion qoff and toff failed.' >&2\nexit 134\n")
            binary.chmod(0o755)
            stage = root / "single"
            stage.mkdir()
            with self.assertRaises(SystemExit) as caught:
                run_minimap(str(binary), 1, root / "donor.fa", root / "query.fa", stage / "result.paf", stage)
            self.assertIn("MINIMAP2_CIGAR_ASSERTION", str(caught.exception))

            def fail_alignment(query, paf, attempt):
                paf.write_text("partial")
                (attempt / "stderr.log").write_text(ASSERTION)
                raise RuntimeError("synthetic failure")

            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                    cached_chromosome_alignment(
                        root, "step1_round1", "chr1", "q", "qc", [], [("query", "ACGT")], {},
                        {"donor_set_id": "d", "fasta_sha256": "digest", "fasta_relpath": "donor.fa"},
                        True, {}, {"resolved": str(binary)}, {}, 1, alignment_runner=fail_alignment)
            attempts = list((root / "grt/failed").iterdir())
            self.assertEqual(len(attempts), 2)
            for attempt in attempts:
                self.assertEqual((attempt / "result.paf").read_text(), "partial")
                self.assertEqual((attempt / "stderr.log").read_text(), ASSERTION)
                self.assertFalse((attempt / "cache.json").exists())

    def test_probe_failure_is_diagnostic_not_fatal(self):
        with patch("minimap2_diagnostics.shutil.which", return_value=None):
            self.assertIn("error", diagnostics.tool_identity("minimap2"))
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "minimap2"
            binary.write_text("#!/bin/sh\nexit 2\n")
            binary.chmod(0o755)
            result = diagnostics.tool_identity(str(binary))
            self.assertEqual(result["version_exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
