import tempfile
import unittest
from pathlib import Path

from server.tools.promote_server_stage import promote
from server.tools.workspace_layout import initialize_workspace


class PromoteServerStageTests(unittest.TestCase):
    def test_promotes_allowlisted_entries_and_rewrites_shell_paths(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            stage = root / "stage"
            server = root / "server"
            (stage / "metadata").mkdir(parents=True)
            (stage / "metadata/value.tsv").write_text("new\n", encoding="utf-8")
            (stage / "add_dataset.sh").write_text(
                f'#!/usr/bin/env bash\nserver={stage}\n',
                encoding="utf-8",
                newline="",
            )
            (stage / "add_ctg.sh").write_text(
                f'#!/usr/bin/env bash\nserver={stage}\n',
                encoding="utf-8",
                newline="",
            )
            (server / "metadata").mkdir(parents=True)
            (server / "metadata/value.tsv").write_text("old\n", encoding="utf-8")

            promote(stage, server, ["add_ctg.sh"])

            self.assertEqual(
                (server / "metadata/value.tsv").read_text(encoding="utf-8"),
                "new\n",
            )
            self.assertIn(
                str(server),
                (server / "add_dataset.sh").read_text(encoding="utf-8"),
            )
            self.assertTrue((server / "add_ctg.sh").is_file())

    def test_promotes_numbered_stage_without_removing_runtime_or_unrelated_outputs(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            stage = initialize_workspace(root / "stage")
            server = initialize_workspace(root / "server")
            for layout, value in ((stage, "new"), (server, "existing")):
                for name in ("metadata/value.tsv", ".prepare_lib/tools/workspace_layout.py", "run_all.sh", "add_ctg.sh",
                             "data/datasets/derived_ctg.fa", "data/derived_ctgs/added.fa", "data/reference/ref.fa"):
                    file = layout.path(name)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text(f"{value} {layout.root}\n")
            final = server.path("05_final/01_degap/assembly.fa")
            final.parent.mkdir(parents=True)
            final.write_text(">untouched\nACGT\n")
            promote(stage.root, server.root, ["add_ctg.sh"])
            self.assertTrue(server.path("metadata/value.tsv").read_text().startswith("new "))
            self.assertTrue(server.path(".prepare_lib/tools/workspace_layout.py").is_file())
            self.assertTrue(server.path("data/datasets/derived_ctg.fa").read_text().startswith("new "))
            self.assertTrue(server.path("data/derived_ctgs/added.fa").read_text().startswith("new "))
            self.assertTrue(server.path("data/reference/ref.fa").read_text().startswith("existing "))
            self.assertIn(str(server.root), server.path("add_ctg.sh").read_text())
            self.assertFalse((server.root / ".prepare_lib").exists())
            self.assertEqual(final.read_text(), ">untouched\nACGT\n")

    def test_rejects_layout_mismatch_without_touching_existing_entries(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = initialize_workspace(root / "server")
            data = server.path("metadata/value.tsv")
            data.parent.mkdir(parents=True)
            data.write_text("keep\n")
            (root / "stage").mkdir()
            with self.assertRaisesRegex(ValueError, "different layouts"):
                promote(root / "stage", server.root, [])
            self.assertEqual(data.read_text(), "keep\n")

    def test_rejects_non_allowlisted_entry(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            with self.assertRaisesRegex(ValueError, "unsupported promotion entries"):
                promote(root / "stage", root / "server", ["secrets.txt"])


if __name__ == "__main__":
    unittest.main()
