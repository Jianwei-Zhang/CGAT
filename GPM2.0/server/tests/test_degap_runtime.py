"""Bundled-runtime integrity and runtime-copy/update contracts (no downloads)."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from server.tools import degap, update_server

SERVER = Path(__file__).resolve().parents[1]


class DegapRuntimeTests(unittest.TestCase):
    def test_snapshot_integrity_and_completeness(self):
        root = SERVER / "tools/degap_core"
        info = json.loads((root / "SOURCE.json").read_text())
        self.assertEqual(len(info["revision"]), 40)
        self.assertIn("bin/DEGAP.py", info["files"])
        repo = SERVER.parents[1]
        if (repo / ".git").exists():
            gitlink = subprocess.check_output(["git", "ls-files", "--stage", "DEGAP2.0"], cwd=repo, text=True).split()
            self.assertEqual(info["revision"], gitlink[1])
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.name != "SOURCE.json"}
        self.assertEqual(actual, set(info["files"]))
        for name, digest in info["files"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)

    def test_launcher_uses_same_python_and_preserves_arguments(self):
        with mock.patch.object(sys, "argv", ["degap.py", "--out", "/path with space", "--help"]), mock.patch.object(degap.os, "execv") as execute:
            degap.main()
        execute.assert_called_once_with(sys.executable, [sys.executable, "-B",
            str(SERVER / "tools/degap_core/bin/DEGAP.py"), "--out", "/path with space", "--help"])

    def test_output_trailing_slash_does_not_break_upstream_result_names(self):
        with mock.patch.object(sys, "argv", ["degap.py", "--out", "/path/job/"]), mock.patch.object(degap.os, "execv") as execute:
            degap.main()
        self.assertEqual(execute.call_args.args[1][-1], "/path/job")

    def test_zero_round_gapfiller_is_actionable_without_changing_upstream(self):
        with mock.patch.object(sys, "argv", ["degap.py", "--mode", "gapfiller", "--MaximumExtensionRound", "0"]), mock.patch.object(degap.os, "execv") as execute:
            with self.assertRaisesRegex(SystemExit, "requires.*>= 1"):
                degap.main()
        execute.assert_not_called()

    def test_updater_includes_nested_code_and_source_provenance(self):
        for name in ("tools/degap.py", "tools/degap_core/bin/DEGAP.py", "tools/degap_core/SOURCE.json", "tools/degap_core/environment.yml"):
            self.assertTrue(update_server.runtime_file(name), name)

    def test_both_architectures_share_the_complete_environment(self):
        specs = [set((SERVER / name).read_text().splitlines()) for name in
                 ("cgat-server.conda-spec.txt", "cgat-server.linux-aarch64.conda-spec.txt")]
        required = {"python=3.11.14", "samtools=1.23.1", "minimap2=2.31", "biopython", "pysam",
                    "numpy", "matplotlib-base", "scipy", "hifiasm=0.25.0", "seqkit=2.8.0", "parallel", "ripgrep=15.1.0"}
        for spec in specs:
            self.assertTrue(required <= spec)


if __name__ == "__main__":
    unittest.main()
