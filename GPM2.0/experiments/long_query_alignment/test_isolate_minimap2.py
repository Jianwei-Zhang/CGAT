from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest

import isolate_minimap2 as diag


class IsolateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="isolate tests ")
        self.root = Path(self.temp.name)
        self.ref = self.root / "ref.fa"
        self.query = self.root / "query.fa"
        self.ref.write_text(">ref\nACGTN\n")
        self.query.write_text(">first description\nacgt\n>second\nNNAC\n")
        self.tool = self.root / "fake minimap2"
        self.tool.write_text("#!/usr/bin/env python3\nimport sys\nif '--version' in sys.argv: print('2.31-r1302'); sys.exit(0)\n"
                             "print('QR\\tsecond\\t0\\t4'.encode().decode('unicode_escape'), file=sys.stderr)\n"
                             "print(\"minimap2: align.c:301: mm_update_extra: Assertion `" + diag.ASSERTION + "' failed.\", file=sys.stderr)\n"
                             "sys.exit(134)\n")
        self.tool.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **updates):
        data = dict(ref=self.ref, query=self.query, out=self.root / "new run",
                    minimap2=str(self.tool), timeout_seconds=30, memory_gib=2,
                    max_file_gib=1, min_free_gib=1, expected_version="2.31-r1302",
                    query_id=None, case="locate", execute=True)
        data.update(updates)
        return argparse.Namespace(**data)

    def run_case(self, **updates):
        args = self.args(**updates)
        with contextlib.redirect_stdout(io.StringIO()):
            code = diag.execute(args, diag.checked_plan(args))
        return code, json.loads((args.out / "report.json").read_text())

    def test_default_plan_never_creates_directory_or_starts_tool(self):
        self.tool.write_text("#!/bin/sh\nexit 99\n")
        argv = ["--ref", str(self.ref), "--query", str(self.query), "--out", str(self.root / "plan"),
                "--minimap2", str(self.tool), "--timeout-seconds", "60", "--memory-gib", "2"]
        with contextlib.redirect_stdout(io.StringIO()) as text:
            self.assertEqual(diag.main(argv), 0)
        self.assertIn("PLAN ONLY", text.getvalue())
        self.assertFalse((self.root / "plan").exists())

    def test_scan_unwrapped_iupac_and_exact_selected_record(self):
        bases = b"aCgTRyN" * (diag.CHUNK // 7 + 30)
        self.query.write_bytes(b">long note\r\n" + bases + b"\r\n>tail\nATGC")
        dest = self.root / "selected.fa"
        info = diag.scan_fasta(self.query, time.monotonic() + 10, "long", dest)
        self.assertEqual(info["records"], {"long": len(bases), "tail": 4})
        self.assertEqual(info["sha256"], hashlib.sha256(self.query.read_bytes()).hexdigest())
        self.assertEqual(b"".join(dest.read_bytes().splitlines()[1:]), bases.upper())
        self.assertFalse(self.query.with_suffix(".fa.fai").exists())

    def test_invalid_fasta_and_unknown_id_fail_closed(self):
        for raw in [b">dup\nA\n>dup\nC\n", b">empty\n>ok\nA\n", b"A\n", b">x\nAC GT\n", b">\nA\n", b">x\nAZ\n"]:
            with self.subTest(raw=raw):
                self.query.write_bytes(raw)
                with self.assertRaises(ValueError):
                    diag.scan_fasta(self.query, time.monotonic() + 5)
        self.query.write_bytes(b">ok\nA\n")
        with self.assertRaisesRegex(ValueError, "not found"):
            diag.scan_fasta(self.query, time.monotonic() + 5, "absent", self.root / "absent.fa")
        with self.assertRaises(TimeoutError):
            diag.scan_fasta(self.query, time.monotonic() - 1)

    def test_existing_output_workspace_and_unscoped_contrast_refused(self):
        cases = [self.args(out=self.root), self.args(case="eqx"), self.args(timeout_seconds=0),
                 self.args(query_id="bad id")]
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "run_all.sh").touch()
        nested = workspace / "nested"
        nested.mkdir()
        cases.append(self.args(out=nested / "run"))
        symlink = self.root / "dangling"
        symlink.symlink_to(self.root / "absent")
        cases.append(self.args(out=symlink))
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                diag.checked_plan(args)

    def test_trace_requires_live_query_not_last_completed_or_interleaved(self):
        error = "minimap2: mm_update_extra: Assertion `" + diag.ASSERTION + "' failed.\n"
        trace = self.root / "trace.log"
        trace.write_text("QR\tfirst\t0\t4\nQT\tfirst\t0\t1.23\nQR\tsecond\t0\t4\n" + error)
        self.assertEqual(diag.parse_trace(trace)["active_query_at_assertion"]["query_id"], "second")
        for text in ["QR\tfirst\t0\t4\nQT\tfirst\t0\t1.2\n" + error,
                     "QR\tfirst\t0\t4\nQR\tsecond\t0\t4\n" + error,
                     "QR\tfirst\tbad\t4\n" + error, error,
                     "QR\tfirst\t1\t4\n" + error,
                     "QR\tfirst\t0\t4\nKilled\n"]:
            trace.write_text(text)
            self.assertIsNone(diag.parse_trace(trace)["active_query_at_assertion"])

    def test_fake_assertion_archives_logs_not_sequences_and_preserves_inputs(self):
        before = [self.ref.read_bytes(), self.query.read_bytes()]
        code, report = self.run_case()
        self.assertEqual(code, 0)  # successful diagnostic collection, not successful alignment
        self.assertEqual((self.root / "new run").stat().st_mode & 0o777, 0o700)
        self.assertEqual(report["execution"]["returncode"], 134)
        self.assertFalse(report["alignment_exit_zero"])
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["trace"]["active_query_at_assertion"]["query_id"], "second")
        self.assertEqual(before, [self.ref.read_bytes(), self.query.read_bytes()])
        with tarfile.open(self.root / "new run/diagnostics.tar.gz") as archive:
            self.assertEqual(set(archive.getnames()), {"plan.json", "report.json", "inputs.json", "stdout.log", "stderr.log"})
        self.assertFalse(list(self.root.glob("*.fai")))

    def test_version_mismatch_and_query_identity_mismatch(self):
        code, report = self.run_case(expected_version="not-installed")
        self.assertEqual(code, 2)
        self.assertIn("version differs", report["error"])
        self.assertFalse((self.root / "new run/stderr.log").exists())
        code, report = self.run_case(out=self.root / "selected", query_id="first")
        self.assertEqual(code, 0)
        self.assertIsNone(report["trace"]["active_query_at_assertion"])
        self.assertEqual((self.root / "selected/selected.query.fa").read_text(), ">first\nACGT\n")

    def test_timeout_kills_only_diagnostic_process_and_retains_report(self):
        self.tool.write_text("#!/usr/bin/env python3\nimport sys,time\nif '--version' in sys.argv: print('2.31-r1302'); sys.exit(0)\ntime.sleep(30)\n")
        start = time.monotonic()
        code, report = self.run_case(timeout_seconds=1)
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - start, 6)
        self.assertEqual(report["execution"]["stopped"], "timeout")
        self.assertIsNone(report["trace"]["active_query_at_assertion"])
        self.assertTrue((self.root / "new run/diagnostics.tar.gz").is_file())

    def test_mutation_during_mapping_invalidates_localization(self):
        original = self.tool.read_text()
        self.tool.write_text(original.replace("sys.exit(134)",
            "from pathlib import Path\nPath(" + repr(str(self.query)) + ").write_text('>changed\\nA\\n')\nsys.exit(134)"))
        code, report = self.run_case()
        self.assertEqual(code, 2)
        self.assertFalse(report["input_stats_unchanged"])
        self.assertEqual(report["status"], "input_or_tool_changed")
        self.assertIsNone(report["trace"]["active_query_at_assertion"])

    def test_exit_zero_without_alignment_is_not_a_workaround(self):
        self.tool.write_text("#!/usr/bin/env python3\nimport sys\nif '--version' in sys.argv: print('2.31-r1302')\n")
        code, report = self.run_case()
        self.assertEqual(code, 0)
        self.assertEqual(report["outcome"], "exit_zero_unvalidated")
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["customer_recovered"])
        self.assertIsNone(report["trace"]["active_query_at_assertion"])

    def test_real_minimap2_small_control(self):
        mm = shutil.which("minimap2")
        if not mm:
            self.skipTest("real minimap2 unavailable")
        import random
        rng = random.Random(29102026)
        seq = "".join(rng.choices("ACGT", k=20000))
        self.ref.write_text(">target\n" + seq + "\n")
        self.query.write_text(">whole\n" + seq + "\n>other\n" + seq[:2000] + "\n")
        version = subprocess.check_output([mm, "--version"], text=True).strip()
        code, report = self.run_case(minimap2=mm, expected_version=version, query_id="whole")
        self.assertEqual(code, 0)
        self.assertTrue(report["alignment_exit_zero"])
        self.assertFalse(report["trace"]["same_assertion"])
        self.assertTrue(report["trace"]["trace_well_formed"])
        self.assertEqual(report["trace"]["completed_query_events"], 1)
        self.assertIn("cg:Z:20000M", (self.root / "new run/alignment.diagnostic.partial.paf").read_text())
        self.assertFalse(report["production_ready"])


if __name__ == "__main__":
    unittest.main()
