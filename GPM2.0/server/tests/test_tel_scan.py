"""Shared literal-motif scanner; both physical layouts and frozen rules."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from workspace_layout import initialize_workspace, WorkspaceLayout
from tel_scan import scan


class TelScanTests(unittest.TestCase):
    def test_both_layouts_preserve_literal_repeat_strands_coordinates_and_provenance(self):
        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "workspace"
                root.mkdir()
                layout = initialize_workspace(root) if version == 2 else WorkspaceLayout(root, 1)
                values = {"tel/rules.tsv": "rule_id\tmotif\tmin_repeat\tprovenance\nknown\tAG\t2\t[]\n",
                          "cen/reference.tsv": "chr_name\n", "cen/library.fa": ""}
                for name, value in values.items():
                    path = layout.path(name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(value)
                snapshot = layout.path("metadata/annotation_library_snapshot.json")
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_text(json.dumps({"schema_version": 1, "files": {
                    name: hashlib.sha256(value.encode()).hexdigest() for name, value in values.items()}}))
                fasta = root / "new.fa"
                fasta.write_text(">p\nAGAGNNCTCT\n>negative\nACGTTGCA\n")
                before = {layout.path(name): layout.path(name).read_bytes() for name in values}
                chromosome, dataset = ("Chr1", "patch") if version == 1 else ("染色体一", "样本")
                result = subprocess.run([sys.executable, "-B", str(TOOLS / "tel_scan.py"), "--root", str(root),
                                         "--chr", chromosome, "--dataset", dataset + "=" + str(fasta)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = layout.path("tel/chr_" + chromosome + "/" + dataset + ".tsv")
                with output.open() as stream:
                    rows = list(csv.DictReader(stream, delimiter="\t"))
                self.assertEqual([(r["start_bp"], r["end_bp"], r["strand"]) for r in rows],
                                 [("1", "4", "+"), ("7", "10", "-")])
                self.assertTrue(all(r["provenance"] == "[]" and r["seq_name"] == "p" for r in rows))
                for path, value in before.items():
                    self.assertEqual(path.read_bytes(), value)
                if version == 2:
                    self.assertFalse((root / "tel").exists())
                    self.assertFalse((root / "metadata").exists())
                rules = layout.path("tel/rules.tsv")
                rules.write_bytes(rules.read_bytes().replace(b"AG", b"AC"))
                with self.assertRaisesRegex(ValueError, "prepared annotation input changed"):
                    scan(root, chromosome, [dataset + "=" + str(fasta)])
                self.assertEqual(output.read_text().count("known\t"), 2)

    def test_actual_generated_command_executes_the_matching_numbered_runtime(self):
        from test_self_alignment_parameters import load_command_writer
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            layout = initialize_workspace(root, prepared_runtime=".lib")
            runtime = layout.path(".lib/tools")
            runtime.mkdir(parents=True)
            for name in ("tel_scan.py", "workspace_layout.py", "annotation_library.py"):
                shutil.copy2(TOOLS / name, runtime / name)
            rules = layout.path("tel/rules.tsv")
            rules.parent.mkdir(parents=True)
            rules.write_text("rule_id\tmotif\tmin_repeat\nx\tAG\t2\n")
            fasta = root / "patch.fa"
            fasta.write_text(">p\nAGAGNNCTCT\n")
            run = layout.path("runs/chr_chr/tel_scan")
            run.mkdir(parents=True)
            script = run / "command.sh"
            namespace = load_command_writer()
            namespace["write_tel_scan_command_script"](script, run, root, "-chr", [("-ds", fasta)])
            self.assertIn("/.lib/tools/tel_scan.py", script.read_text())
            completed = subprocess.run(["bash", str(script)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(layout.path("tel/chr_-chr/-ds.tsv").is_file())
            self.assertFalse((root / "tel").exists())

    def test_unmarked_legacy_rules_keep_legacy_header_and_reject_path_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tel").mkdir()
            (root / "tel/rules.tsv").write_text("rule_id\tmotif\tmin_repeat\nx\tA\t3\n")
            fasta = root / "source.fa"
            fasta.write_text(">u\nCCCAAAA\n")
            scan(root, "chr", ["ds=" + str(fasta)])
            self.assertNotIn("provenance", (root / "tel/chr_chr/ds.tsv").read_text())
            with self.assertRaisesRegex(ValueError, "unsafe"):
                scan(root, "chr", ["../escape=" + str(fasta)])


if __name__ == "__main__":
    unittest.main()
