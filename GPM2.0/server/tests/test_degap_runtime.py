"""Bundled-runtime integrity and runtime-copy/update contracts (no downloads)."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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

    @unittest.skipUnless(shutil.which("seqkit"), "native shared preparation uses seqkit")
    def test_shared_prepare_seals_reads_without_adopting_legacy_or_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reads = root / "reads.fa"
            reads.write_text(">r\nAGTC\n")
            prepared = root / "shared" / "processed_reads"
            base = [sys.executable, "-B", SERVER / "tools/degap.py", "prepare-shared-reads",
                    "--out", prepared.parent, "--hifi", reads]
            subprocess.run(base, check=True, capture_output=True)
            receipt = json.loads((prepared / "manifest.json").read_text())
            self.assertEqual(receipt["contract"]["sources"]["hifi"], [
                {"path": str(reads), "sha256": hashlib.sha256(reads.read_bytes()).hexdigest()}])
            cached = prepared / "hifi_reads.fa"
            before = cached.stat().st_mtime_ns
            subprocess.run(base, check=True, capture_output=True)
            self.assertEqual(cached.stat().st_mtime_ns, before)
            reads.write_text(">r\nGGGG\n")
            rejected = subprocess.run(base, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("Original read inputs or converter changed", rejected.stderr)
            self.assertEqual(cached.stat().st_mtime_ns, before)
            legacy = root / "legacy" / "processed_reads"
            legacy.mkdir(parents=True)
            shutil.copyfile(cached, legacy / "hifi_reads.fa")
            old_command = [*base[:4], "--out", legacy.parent, "--hifi", reads]
            rejected = subprocess.run(old_command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("lack an input manifest", rejected.stderr)
            self.assertFalse((legacy / "manifest.json").exists())

    def test_updater_includes_nested_code_and_source_provenance(self):
        for name in ("tools/degap.py", "tools/degap_core/bin/DEGAP.py", "tools/degap_core/SOURCE.json", "tools/degap_core/environment.yml"):
            self.assertTrue(update_server.runtime_file(name), name)

    def test_both_architectures_share_the_complete_environment(self):
        specs = [set((SERVER / name).read_text().splitlines()) for name in
                 ("cgat-server.conda-spec.txt", "cgat-server.linux-aarch64.conda-spec.txt")]
        required = {"python", "samtools", "minimap2", "biopython", "pysam", "numpy", "matplotlib-base",
                    "scipy", "hifiasm", "seqkit", "parallel", "ripgrep"}
        lock = json.loads((SERVER / "contracts/refinement-tools.lock.json").read_text())
        pinned = {f'{name}={lock["dependencies"][name]["version"]}' for name in required}
        for spec in specs:
            self.assertEqual({line.split("=")[0] for line in spec if line and not line.startswith("#")} & required,
                             required)
            self.assertFalse(pinned - spec, f"Missing shared pins: {sorted(pinned - spec)}")


if __name__ == "__main__":
    unittest.main()
