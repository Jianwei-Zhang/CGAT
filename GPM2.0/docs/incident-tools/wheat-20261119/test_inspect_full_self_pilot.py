import copy
import json
from pathlib import Path
import tempfile
import unittest

import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection


class SelfInspectionProofTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.batch = {"entries": [{"name": "q", "length": 10}], "query": str(self.root / "query.fa"), "key": "key"}
        self.manifest = {"version": 1, "preset": "asm10", "min_chain_score": 200,
            "minimizers": 100, "cache": str(self.root / "cache")}
        native = ["minimap2", "-c", "-x", "asm10", "-X", "--no-hash-name", "-m", "200",
                  "-n", "100", "-t", "1", str(self.root / "cache/target.mmi"), self.batch["query"]]
        self.report = {"status": "candidate_complete_not_compared_not_adopted", "candidate_adopted": False,
            "analysis_workspace_modified": False, "mapping": {"returncode": 0}, "native_batch_key": "key",
            "native_command": native, "command": pilot.candidate_command(self.manifest, self.batch, native),
            "driver_sha256": pilot.digest(Path(pilot.__file__))}
        self.marker = {"key": "key", "outputs": {}}
        for name in inspection.OUTPUT_NAMES:
            p = self.root / name; p.write_text(name)
            self.marker["outputs"][name] = pilot.digest(p)

    def write_marker(self):
        (self.root / "complete.json").write_text(json.dumps(self.marker))

    def test_completed_native_marker_binds_every_output(self):
        self.write_marker()
        proof = inspection.native_commit(self.root, "key")
        self.assertEqual(set(proof["outputs"]), {str(self.root / name) for name in inspection.OUTPUT_NAMES})
        self.assertIn(str(self.root / "complete.json"), proof["marker"])

    def test_temporary_paf_without_marker_is_never_a_baseline(self):
        with self.assertRaisesRegex(ValueError, "not committed"):
            inspection.native_commit(self.root, "key")

    def test_different_batch_key_is_rejected(self):
        self.write_marker()
        with self.assertRaisesRegex(ValueError, "does not match"):
            inspection.native_commit(self.root, "other-key")

    def test_incomplete_output_inventory_is_rejected(self):
        del self.marker["outputs"]["stderr.log"]; self.write_marker()
        with self.assertRaises(ValueError): inspection.native_commit(self.root, "key")

    def test_corrupt_committed_output_is_rejected(self):
        self.write_marker(); (self.root / "raw.paf").write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "output hash changed"):
            inspection.native_commit(self.root, "key")

    def test_full_candidate_contract_is_accepted(self):
        inspection.candidate_contract(self.report, self.manifest, self.batch)

    def test_failed_adopted_changed_or_unbound_candidate_is_rejected(self):
        for key, value in (("status", "running"), ("candidate_adopted", True),
                           ("analysis_workspace_modified", True), ("mapping", {"returncode": 124}),
                           ("native_batch_key", "other"), ("driver_sha256", "changed")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                inspection.candidate_contract({**self.report, key: value}, self.manifest, self.batch)

    def test_changed_candidate_flags_are_rejected(self):
        report = copy.deepcopy(self.report); report["command"].remove("-X")
        with self.assertRaisesRegex(ValueError, "one-flag"):
            inspection.candidate_contract(report, self.manifest, self.batch)

    def test_same_size_source_corruption_is_rejected(self):
        p = self.root / "source"; p.write_text("AAA")
        proof = pilot.identities([p]); p.write_text("TTT")
        with self.assertRaisesRegex(ValueError, "identity changed"): inspection.checked_files(proof)


if __name__ == "__main__":
    unittest.main()
