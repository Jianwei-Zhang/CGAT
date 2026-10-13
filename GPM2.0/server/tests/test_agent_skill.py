"""Safety and reproducibility contracts for the distributed smoke-test helper."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "gpm-server"
SCRIPT = SKILL / "scripts" / "make_smoke_inputs.py"
spec = importlib.util.spec_from_file_location("make_smoke_inputs", SCRIPT)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def read_fasta(path):
    records = {}
    name = None
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            name = line[1:]
            if name in records:
                raise AssertionError("duplicate FASTA ID")
            records[name] = ""
        else:
            records[name] += line
    return records


class AgentSkillFixtureTests(unittest.TestCase):
    def test_deterministic_and_manifest_matches_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            manifest = fixture.generate(first)
            self.assertEqual(manifest, fixture.generate(second))
            self.assertEqual(manifest, json.loads((first / "manifest.json").read_text()))
            for item in manifest["inputs"]:
                payload = (first / item["file"]).read_bytes()
                self.assertEqual(payload, (second / item["file"]).read_bytes())
                self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
                records = read_fasta(first / item["file"])
                self.assertEqual(len(records), item["records"])
                self.assertEqual(sum(map(len, records.values())), item["bases"])
                self.assertEqual(sum(seq.count("N") for seq in records.values()), item["n_bases"])
                self.assertNotIn(b"\r", payload)

    def test_small_real_alignment_inputs_preserve_gap_flanks(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "tiny"
            fixture.generate(dest)
            ref = list(read_fasta(dest / "reference.fa").values())
            primary = list(read_fasta(dest / "primary.fa").values())
            support = list(read_fasta(dest / "support.fa").values())
            self.assertEqual(ref, support)
            self.assertEqual(len(ref), 2)
            self.assertNotEqual(ref[0], ref[1])
            for r, p in zip(ref, primary):
                self.assertEqual(len(r), 60_000)
                self.assertEqual(len(r), len(p))
                self.assertEqual(p[:25_000], r[:25_000])
                self.assertEqual(p[25_000:25_200], "N" * 200)
                self.assertEqual(p[25_200:], r[25_200:])
                self.assertLessEqual(set(r), set("ACGT"))
            self.assertLess(sum(p.stat().st_size for p in dest.iterdir()), 400_000)

    def test_refuses_existing_empty_or_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "existing"
            dest.mkdir()
            with self.assertRaises(FileExistsError):
                fixture.generate(dest)
            original = b"do not overwrite\n"
            (dest / "primary.fa").write_bytes(original)
            result = subprocess.run([sys.executable, str(SCRIPT), "--out", str(dest)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("ERROR", result.stderr)
            self.assertEqual((dest / "primary.fa").read_bytes(), original)
            self.assertFalse((dest / "manifest.json").exists())

    def test_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, link = Path(tmp) / "target", Path(tmp) / "link"
            target.mkdir()
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                fixture.generate(link)
            self.assertEqual(list(target.iterdir()), [])

    def test_copied_skill_works_without_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "installed skill"
            shutil.copytree(SKILL, copied)
            result = subprocess.run(
                [sys.executable, str(copied / "scripts" / "make_smoke_inputs.py"),
                 "--out", "tiny"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)["inputs"]), 3)
            for target in ("references/execution.md", "references/troubleshooting.md",
                           "references/smoke-test.md", "SKILL.md"):
                self.assertTrue((copied / target).is_file())

    def test_cli_success_in_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "task inputs" / "tiny"
            result = subprocess.run([sys.executable, str(SCRIPT), "--out", str(dest)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["reads_qc"], "not tested")
            self.assertTrue((dest / "support.fa").is_file())


if __name__ == "__main__":
    unittest.main()
