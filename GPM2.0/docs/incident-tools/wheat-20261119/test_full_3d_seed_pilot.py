import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
from run_orchestration import file_identity, fingerprint, sha256_file
import full_3d_seed_pilot as driver

PAF = "q\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\ttp:A:P\tcg:Z:10M\n"


class FullCandidateProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work, self.here = self.root / "gpm_server", self.root / "pilot"
        self.command = self.work / driver.COMMAND
        names = [driver.COMMAND, "runs/chr_3D/datasets/JM19_flye_ABD.fa",
                 "runs/chr_3D/datasets/JM19_hifiasm.fa"]
        for name in names:
            p = self.work / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("echo baseline\n" if name.endswith(".sh") else ">q\nACGTACGTAC\n")
        self.inputs = [file_identity(self.work / name, relative_to=self.work) for name in names]
        cp = self.work / ".run_all/checkpoints/assign.80a737d469c64759.json"
        cp.parent.mkdir(parents=True); cp.write_text(json.dumps({"outputs": self.inputs}))
        self.tool = str(Path(sys.executable).resolve())
        self.tool_hash = sha256_file(Path(self.tool))
        proof = self.root / "memory-resume-20261118/reference.before.json"
        proof.parent.mkdir(); proof.write_text(json.dumps({"input_payload": {"tools": [
            {"command": "minimap2", "sha256": self.tool_hash}]}}))
        self.candidate = self.here / "f0005/result.paf"
        self.candidate.parent.mkdir(parents=True)
        for name in ("result.paf", "stdout.log", "stderr.log"):
            (self.candidate.parent / name).write_text(PAF if name.endswith(".paf") else "")
            (self.command.parent / name).write_text(PAF if name.endswith(".paf") else "")
        self.report = self.here / "result.json"
        self.report.write_text(json.dumps({"status": "candidate_complete_native_comparison_pending",
            "mapping": {"returncode": 0}, "inputs": self.inputs, "tool_sha256": self.tool_hash,
            "candidate_adopted": False, "outputs": [file_identity(self.candidate.parent / name,
            relative_to=self.here) for name in ("result.paf", "stdout.log", "stderr.log")]}))

    def execute(self):
        with patch.multiple(driver, ROOT=self.root, WORK=self.work, HERE=self.here), \
             patch.object(driver.shutil, "which", return_value=self.tool), \
             patch.object(sys, "argv", ["pilot", "--compare-only"]), patch("builtins.print"):
            driver.main()
        return json.loads(self.report.read_text())

    def test_paf_existence_without_native_checkpoint_does_not_enable_comparison(self):
        report = self.execute()
        self.assertEqual(report["status"], "candidate_complete_native_comparison_pending")
        self.assertNotIn("native_metrics", report)
        self.assertFalse(report["candidate_adopted"])

    def test_verified_native_leaf_can_be_compared_but_is_not_replaced(self):
        directory = self.root / "memory-resume-20261118/cross-leaf-checkpoints"
        directory.mkdir()
        marker = directory / (fingerprint(driver.COMMAND) + ".json")
        marker.write_text(json.dumps({"status": "success", "command": driver.COMMAND,
            "inputs": {"files": self.inputs, "tool": {"sha256": self.tool_hash}},
            "outputs": [file_identity(self.command.parent / name, relative_to=self.work)
                        for name in ("result.paf", "stdout.log", "stderr.log")], "origin": "test-run"}))
        report = self.execute()
        self.assertEqual(report["status"], "candidate_and_native_compared_not_adopted")
        self.assertEqual(report["cigar_anchor_comparison"]["baseline_anchors_supported_within_0bp"], 1)
        self.assertFalse(report["candidate_adopted"])
        self.assertEqual((self.command.parent / "result.paf").read_text(), PAF)

    def test_corrupt_candidate_output_is_refused(self):
        self.candidate.write_text("corrupt\n")
        with self.assertRaises(AssertionError): self.execute()

    def test_changed_input_is_refused(self):
        (self.work / self.inputs[1]["path"]).write_text(">changed\nA\n")
        with self.assertRaises(AssertionError): self.execute()


if __name__ == "__main__":
    unittest.main()
