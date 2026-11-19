import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import full_self_moderate_candidate as moderate


class ModerateCandidateTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"version": 1, "preset": "asm10", "min_chain_score": 200,
                         "minimizers": 100, "cache": "/cache"}
        self.batch = {"entries": [{"name": "q", "length": 289508469}], "query": "/whole.fa"}
        self.native = ["/bin/minimap2", "-c", "-x", "asm10", "-X", "--no-hash-name", "-m", "200",
                       "-n", "100", "-t", "1", "/cache/target.mmi", "/whole.fa"]

    def test_changes_only_seed_filter_and_preserves_whole_source(self):
        command = moderate.moderate_command(self.manifest, self.batch, self.native)
        self.assertEqual(command[-4:-2], ["-f", "0.001"])
        self.assertEqual(command[:-4] + command[-2:], self.native)
        self.assertEqual(self.native[-2:], ["/cache/target.mmi", "/whole.fa"])
        self.assertNotIn("-f", self.native)

    def test_small_or_multirecord_batches_are_not_silently_approximated(self):
        for entries in ([{"name": "q", "length": 99999999}], self.batch["entries"] * 2):
            with self.assertRaises(ValueError):
                moderate.moderate_command(self.manifest, {**self.batch, "entries": entries}, self.native)

    def test_changed_self_flags_index_or_query_are_rejected(self):
        for index, value in ((4, "-Y"), (5, "--different-name-hashing"), (12, "/other.mmi"), (13, "/fragment.fa")):
            native = copy.deepcopy(self.native); native[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                moderate.moderate_command(self.manifest, self.batch, native)

    def test_cli_does_not_reinvoke_original_native_driver(self):
        args = ["candidate", "--work", "/work", "--manifest", "/manifest", "--batch-index", "3",
                "--source-dir", "/source", "--output", "/output"]
        with patch.object(moderate.sys, "argv", args), patch.object(moderate, "execute") as execute, \
             patch.object(moderate.signal, "signal"), patch.object(moderate.pilot, "execute") as native:
            moderate.main()
        execute.assert_called_once_with(Path("/work"), Path("/manifest"), 3, Path("/source"), Path("/output"))
        native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
