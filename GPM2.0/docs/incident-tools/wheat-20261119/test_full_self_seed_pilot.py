import builtins
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
import self_alignment_batches as helper
import run_orchestration as contract
import full_self_seed_pilot as driver

PAF = "q\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\ttp:A:P\tcg:Z:10M\n"
END = "[M::worker_pipeline::1.0*1.0] mapped 1 sequences\n[M::main] Real time: 1 sec; CPU: 1 sec; Peak RSS: 1 GB\n"


class WholeSelfPilotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.work = self.root / "gpm_server"
        self.tools = self.work / ".prepare_lib/tools"; self.tools.mkdir(parents=True)
        self.cache = self.work / "cache"; self.cache.mkdir()
        self.batchdir = self.work / "batches/batch-00003"; self.batchdir.mkdir(parents=True)
        self.query = self.batchdir / "query.fa"; self.query.write_text(">q\nAAAAAAAAAA\n")
        for name in ("minimap2", "name_map", "restore"):
            (self.work / name).write_text(name)
        for name in ("self_alignment_batches.py", "minimap2_diagnostics.py", "run_orchestration.py"):
            (self.tools / name).write_text(name)
        for name in ("target.mmi", "index.stderr.log"):
            (self.cache / name).write_text(name)
        self.batch = {"entries": [{"name": "q", "length": 10}], "directory": str(self.batchdir),
            "query": str(self.query), "query_sha256": driver.digest(self.query), "key": "native-key"}
        self.manifest = {"version": 1, "preset": "asm10", "min_chain_score": 200, "minimizers": 100,
            "batches": [self.batch], "cache": str(self.cache), "target_lengths": {"t": 10},
            "name_map": str(self.work / "name_map"), "restore": str(self.work / "restore"),
            "identities": {"tool": driver.digest(self.work / "minimap2"), "target": "target-sha",
                "name_map": driver.digest(self.work / "name_map"), "restore": driver.digest(self.work / "restore")}}
        key = helper.identity({"tool": self.manifest["identities"]["tool"], "target": "target-sha",
            "preset": "asm10", "index_limit": "8G"})
        (self.cache / "complete.json").write_text(json.dumps({"key": key, "outputs": {
            name: driver.digest(self.cache / name) for name in ("target.mmi", "index.stderr.log")}}))
        self.native = [str(self.work / "minimap2"), "-c", "-x", "asm10", "-X", "--no-hash-name",
            "-m", "200", "-n", "100", "-t", "1", str(self.cache / "target.mmi"), str(self.query)]
        self.mp = self.work / "manifest.json"; self.mp.write_text(json.dumps(self.manifest))
        self.np = self.batchdir / "command.json"; self.np.write_text(json.dumps(self.native))
        self.output = self.root / "isolated"
        self.hp = self.tools / "self_alignment_batches.py"
        self.hs = driver.digest(self.hp)
        self.modules = {"self_alignment_batches": types.SimpleNamespace(__file__=str(self.hp),
            identity=helper.identity, fasta_lengths=helper.fasta_lengths, validate_raw=helper.validate_raw,
            atomic_json=helper.atomic_json), "run_orchestration": types.SimpleNamespace(
            __file__=str(self.tools / "run_orchestration.py"), validate_paf=contract.validate_paf)}

    def fake_child(self, command, raw, stderr, timeout, stdin=None):
        raw.write_text(PAF); stderr.write_text(END if stdin is None else "")
        return {"returncode": 0, "wall_seconds": 1}

    def execute(self, child=None):
        with patch.object(driver.importlib, "import_module", side_effect=self.modules.__getitem__), \
             patch.object(driver, "run_child", side_effect=child or self.fake_child), patch.object(builtins, "print"):
            driver.execute(self.work, self.mp, 0, self.np, self.output, self.hs)
        return json.loads((self.output / "pilot.json").read_text())

    def test_only_filter_changes_and_native_checkpoint_is_never_written(self):
        before = driver.identities([p for p in self.work.rglob("*") if p.is_file()])
        result = self.execute()
        self.assertEqual(result["command"], self.native[:-2] + ["-f", "0.005"] + self.native[-2:])
        self.assertEqual(result["status"], "candidate_complete_not_compared_not_adopted")
        self.assertFalse(result["candidate_adopted"])
        self.assertFalse((self.batchdir / "complete.json").exists())
        self.assertEqual(before, driver.identities([Path(p) for p in before]))

    def test_changed_self_flag_is_refused(self):
        self.native.remove("-X"); self.np.write_text(json.dumps(self.native))
        with self.assertRaisesRegex(ValueError, "native command"): self.execute()

    def test_corrupt_index_is_refused_without_rebuilding(self):
        (self.cache / "target.mmi").write_text("changed")
        with self.assertRaisesRegex(ValueError, "identity mismatch"): self.execute()
        self.assertEqual((self.cache / "target.mmi").read_text(), "changed")

    def test_source_change_during_mapping_is_refused(self):
        def child(*args, **kwargs):
            result = self.fake_child(*args, **kwargs); self.query.write_text(">q\nCC\n"); return result
        with self.assertRaisesRegex(ValueError, "source/index changed"): self.execute(child)
        self.assertEqual(json.loads((self.output / "pilot.json").read_text())["status"],
                         "failed_or_interrupted_not_adopted")

    def test_missing_traversal_is_not_success(self):
        def child(command, raw, stderr, timeout, stdin=None):
            result = self.fake_child(command, raw, stderr, timeout, stdin); stderr.write_text(""); return result
        with self.assertRaisesRegex(ValueError, "full query traversal"): self.execute(child)

    def test_failed_mapping_is_not_success(self):
        def child(*args, **kwargs):
            result = self.fake_child(*args, **kwargs); result["returncode"] = 124; return result
        with self.assertRaisesRegex(ValueError, "1800-second"): self.execute(child)

    def test_output_must_be_isolated_and_new(self):
        for bad in (self.work, self.work / "pilot", self.root):
            with self.assertRaises(ValueError): driver.require_isolated(self.work, bad)
        self.output.mkdir()
        with self.assertRaises(ValueError): driver.require_isolated(self.work, self.output)

    def test_multiple_records_are_not_silently_reduced(self):
        self.batch["entries"].append({"name": "q2", "length": 4})
        with self.assertRaisesRegex(ValueError, "single whole-record"):
            driver.candidate_command(self.manifest, self.batch, self.native)

    def test_child_is_killed_and_waited_on_timeout(self):
        proc = Mock(); proc.wait.side_effect = [subprocess.TimeoutExpired("test", 1), -9]
        with patch.object(driver.subprocess, "Popen", return_value=proc):
            result = driver.run_child(["test"], self.root / "out", self.root / "err", 1)
        self.assertEqual(result["returncode"], 124)
        proc.kill.assert_called_once(); self.assertEqual(proc.wait.call_count, 2)

    def test_child_is_killed_and_waited_on_interruption(self):
        proc = Mock(); proc.wait.side_effect = [KeyboardInterrupt(), -9]
        with patch.object(driver.subprocess, "Popen", return_value=proc):
            with self.assertRaises(KeyboardInterrupt):
                driver.run_child(["test"], self.root / "out", self.root / "err", 1)
        proc.kill.assert_called_once(); self.assertEqual(proc.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
