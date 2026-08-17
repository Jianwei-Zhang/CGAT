import tempfile
import unittest
from pathlib import Path

from server.tools.promote_server_stage import promote


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

    def test_rejects_non_allowlisted_entry(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            with self.assertRaisesRegex(ValueError, "unsupported promotion entries"):
                promote(root / "stage", root / "server", ["secrets.txt"])


if __name__ == "__main__":
    unittest.main()
