import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
import self_alignment_batches as helper
import run_orchestration as contract
import self_seed_profile as runtime


class SelfSeedProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.work = self.root / "work"; self.work.mkdir()
        tools = self.work / ".prepare_lib"; tools.mkdir()
        (tools / "tools").symlink_to(Path(helper.__file__).resolve().parent, target_is_directory=True)
        self.op = self.work / "runs/chr_X/assembly_vs_self"; self.op.mkdir(parents=True)
        # Tiny deterministic fixture; production remains >=100 Mb.
        small = patch.dict(runtime.POLICY, minimum_query_bases=10)
        small.start(); self.addCleanup(small.stop)
        self.tool = self.root / "minimap2"
        self.raw = "q1b\t12\t0\t12\t+\tq2a\t12\t0\t12\t12\t12\t60\ttp:A:P\tcg:Z:12M\n"
        self.restored = self.raw.replace("q1b", "ctg1").replace("q2a", "ctg2")
        stderr = "[M::worker_pipeline::0] mapped 1 sequences\n[M::main] Real time: 0.1 sec\n"
        self.tool.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write(" + repr(self.raw) + ")\nsys.stderr.write(" + repr(stderr) + ")\n")
        self.tool.chmod(0o755)
        name_map = self.op / "self_name_map.tsv"
        name_map.write_text("q1b\tctg1\nq2a\tctg2\nq3b\tctg3\n")
        restore = self.op / "restore_self_paf.py"
        restore.write_text("import sys\nsys.stdout.write(sys.stdin.read().replace('q1b', 'ctg1').replace('q2a', 'ctg2'))\n")
        self.cache = self.op / ".cache"; self.cache.mkdir()
        self.index = self.cache / "target.mmi"; self.index.write_bytes(b"frozen-test-index")
        target = self.op / "self_target.fa"; target.write_text(">q2a\nAAAAAAAAAAAA\n")
        all_query = self.op / "self_query.fa"; all_query.write_text(">q1b\nAAAAAAAAAAAA\n>q3b\nAAA\n")
        batches = []
        for i, (name, length) in enumerate((("q1b", 12), ("q3b", 3))):
            directory = self.op / "batches" / ("batch-%05d" % i); directory.mkdir(parents=True)
            query = directory / "query.fa"; query.write_text(">" + name + "\n" + "A" * length + "\n")
            batches.append({"directory": str(directory), "query": str(query), "query_sha256": runtime.pilot.digest(query),
                            "entries": [{"name": name, "length": length}], "key": "native-" + str(i)})
        self.native = {"version": 1, "preset": "asm10", "min_chain_score": 200, "minimizers": 100,
            "target": str(target), "query": str(all_query), "cache": str(self.cache),
            "name_map": str(name_map), "restore": str(restore), "output": str(self.op / "result.paf"),
            "target_lengths": {"q2a": 12}, "batches": batches,
            "identities": {"tool": runtime.pilot.digest(self.tool), "name_map": runtime.pilot.digest(name_map),
                           "restore": runtime.pilot.digest(restore), "target": runtime.pilot.digest(target)}}
        (self.cache / "index.stderr.log").write_text("synthetic index")
        helper.publish(self.cache, runtime.index_key(self.native), ("target.mmi", "index.stderr.log"))
        self.source = self.op / "self_batch_manifest.json"; self.source.write_text(json.dumps(self.native))
        self.spec = {"schema": runtime.SCHEMA, "policy": copy.deepcopy(runtime.POLICY), "workspace": str(self.work),
            "selected_batches": [0], "native_manifest": self.row(self.source),
            "dependencies": {"runtime": self.row(Path(runtime.__file__)), "helper": self.row(Path(helper.__file__)),
                             "contract": self.row(Path(contract.__file__)), "pilot": self.row(Path(runtime.pilot.__file__))}}
        self.path = self.root / "profile.json"; self.path.write_text(json.dumps(self.spec))
        self.profile = runtime.Profile(self.path)
        self.directory = Path(batches[0]["directory"])
        which = patch.object(runtime.shutil, "which", return_value=str(self.tool))
        which.start(); self.addCleanup(which.stop)
        index = patch.object(helper, "ensure_index", return_value=self.index)
        index.start(); self.addCleanup(index.stop)

    def row(self, path):
        return {"path": str(path.resolve()), "sha256": runtime.pilot.digest(path)}

    def run_profile(self):
        runtime.run_batch(self.profile, 0)

    def publish_native_small(self):
        directory = Path(self.native["batches"][1]["directory"])
        text = "ctg3\t3\t0\t3\t+\tctg2\t12\t0\t3\t3\t3\t60\tcg:Z:3M\n"
        for name, content in (("raw.paf", text), ("result.paf", text), ("stderr.log", "native success")):
            (directory / name).write_text(content)
        helper.publish(directory, "native-1", runtime.OUTPUTS)
        return text

    def test_keys_change_only_selected_batches(self):
        before = self.source.read_bytes()
        self.assertNotEqual(self.profile.manifest["batches"][0]["key"], "native-0")
        self.assertEqual(self.profile.manifest["batches"][1], self.native["batches"][1])
        self.assertEqual(self.profile.native, self.native)
        self.assertEqual(before, self.source.read_bytes())
        other = runtime.effective_manifest(self.native, [0], "other-profile")
        self.assertNotEqual(other["batches"][0]["key"], self.profile.manifest["batches"][0]["key"])

    def test_invalid_selections_rejected(self):
        for selected in ([1], [0, 0], [-1], [2], [False]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                runtime.effective_manifest(self.native, selected, "profile")
        native = copy.deepcopy(self.native); native["batches"][0]["entries"] *= 2
        with self.assertRaises(ValueError): runtime.effective_manifest(native, [0], "profile")

    def test_native_only_group_retains_original_keys_and_merge_identity(self):
        self.spec["selected_batches"] = []
        self.path.write_text(json.dumps(self.spec)); self.profile = runtime.Profile(self.path)
        self.assertEqual(self.profile.manifest, self.native)
        for name, text in (("raw.paf", self.raw), ("result.paf", self.restored), ("stderr.log", "native")):
            (self.directory / name).write_text(text)
        helper.publish(self.directory, "native-0", runtime.OUTPUTS)
        self.publish_native_small()
        self.assertTrue(helper.merge_if_complete(self.source, self.native))
        before = (self.op / "result.paf").stat()
        self.assertTrue(self.profile.merge())
        after = (self.op / "result.paf").stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
        self.assertEqual(json.loads((self.op / "self_batch_result.json").read_text())["manifest_sha256"],
                         runtime.pilot.digest(self.source))

    def test_run_restore_and_distinct_receipt(self):
        self.run_profile()
        self.assertEqual((self.directory / "result.paf").read_text(), self.restored)
        self.assertTrue(self.profile.validate_batch(0))
        self.assertFalse(helper.valid_outputs(self.directory, "native-0", runtime.OUTPUTS))
        receipt = json.loads((self.directory / runtime.RECEIPT).read_text())
        self.assertEqual(receipt["command"][-4:-2], ["-f", "0.001"])
        self.assertEqual(receipt["native_key"], "native-0")
        self.assertIsNone(receipt["adoption"])

    def test_resume_without_mapper(self):
        self.run_profile()
        with patch.object(runtime.pilot, "run_child", side_effect=AssertionError("duplicate mapper")):
            self.run_profile()

    def test_ordinary_batch_not_routed(self):
        with self.assertRaisesRegex(ValueError, "ordinary"): runtime.run_batch(self.profile, 1)

    def test_existing_native_marker_preserved(self):
        for name in runtime.OUTPUTS: (self.directory / name).write_text("native artifact")
        helper.publish(self.directory, "native-0", runtime.OUTPUTS)
        before = runtime.pilot.identities(list(self.directory.iterdir()))
        with patch.object(runtime.pilot, "run_child", side_effect=AssertionError("native overwrite")), \
             self.assertRaisesRegex(ValueError, "preserve existing"):
            self.run_profile()
        for path, value in before.items():
            self.assertEqual(runtime.pilot.identities([Path(path)])[path], value)

    def test_merge_when_native_finishes_last(self):
        self.run_profile()
        self.assertFalse(self.profile.merge())
        tail = self.publish_native_small()
        self.assertFalse(helper.merge_if_complete(self.source, self.native))
        self.assertTrue(self.profile.merge())
        self.assertEqual((self.op / "result.paf").read_text(), self.restored + tail)
        marker = json.loads((self.op / "self_batch_result.json").read_text())
        self.assertEqual(marker["manifest_sha256"], self.profile.sha)
        self.assertTrue(self.profile.merge())

    def test_changed_source_and_policy_rejected(self):
        self.source.write_text(self.source.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "dependency changed"): self.profile.verify()
        spec = copy.deepcopy(self.spec); spec["policy"]["seed_fraction"] = "0.005"
        self.path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError, "unsupported"): runtime.Profile(self.path)

    def test_bad_receipt_command_inputs_returncode_rejected(self):
        self.run_profile(); path = self.directory / runtime.RECEIPT
        original = json.loads(path.read_text())
        for kind in ("command", "inputs", "returncode", "index"):
            receipt = copy.deepcopy(original)
            if kind == "command": receipt["command"][-3] = "0.005"
            elif kind == "inputs": receipt["inputs"][self.native["batches"][0]["query"]]["sha256"] = "changed"
            elif kind == "returncode": receipt["mapping"]["returncode"] = 124
            else: receipt["index_proof"]["outputs"]["target.mmi"] = "changed"
            path.write_text(json.dumps(receipt))
            self.assertFalse(self.profile.validate_batch(0))
        self.publish_native_small()
        with self.assertRaisesRegex(ValueError, "receipt/output mismatch"): self.profile.merge()

    def test_corrupt_output_or_missing_receipt_rejected(self):
        self.run_profile()
        receipt = self.directory / runtime.RECEIPT; saved = receipt.read_bytes(); receipt.unlink()
        self.assertFalse(self.profile.validate_batch(0)); receipt.write_bytes(saved)
        output = self.directory / "result.paf"
        self.assertTrue(self.profile.validate_batch(0))  # Prime the real scoped digest memo.
        stat = output.stat()
        output.write_bytes(output.read_bytes().replace(b"ctg1", b"ctg9"))
        os.utime(output, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertFalse(self.profile.validate_batch(0))  # Same size/mtime is not acceptance.

    def candidate(self):
        directory = self.root / "candidate"; directory.mkdir()
        for name, value in (("raw.paf", self.raw), ("result.paf", self.restored),
                            ("stderr.log", "[M::worker_pipeline::0] mapped 1 sequences\nReal time: 0.1\n"), ("restore.stderr.log", "")):
            (directory / name).write_text(value)
        command = runtime.mapping_command(self.native, self.native["batches"][0], self.tool, self.index)
        inputs = runtime.pilot.identities([Path(self.native["batches"][0]["query"]), self.tool, self.index,
                                          Path(self.native["name_map"]), Path(self.native["restore"])])
        source = {"scope": "one_complete_self_query_moderate_candidate_only", "status": "moderate_candidate_complete_not_adopted",
            "candidate_adopted": False, "analysis_workspace_modified": False, "whole_records_preserved": True,
            "mapping": {"returncode": 0}, "restoration": {"returncode": 0}, "seed_fraction": "0.001",
            "native_batch_key": "native-0", "command": command, "inputs": inputs,
            "outputs": runtime.pilot.identities([directory / n for n in (*runtime.OUTPUTS, "restore.stderr.log")])}
        path = directory / "candidate.json"; path.write_text(json.dumps(source))
        self.spec["adoptions"] = {"0": self.row(path)}
        self.path.write_text(json.dumps(self.spec)); self.profile = runtime.Profile(self.path)
        return path, source

    def test_reuses_whole_candidate_without_child_process(self):
        path, source = self.candidate()
        before = runtime.pilot.identities([path, *[Path(p) for p in source["outputs"]]])
        with patch.object(runtime.pilot, "run_child", side_effect=AssertionError("candidate recomputed")):
            self.run_profile()
        self.assertTrue(self.profile.validate_batch(0))
        receipt = json.loads((self.directory / runtime.RECEIPT).read_text())
        self.assertFalse(receipt["adoption"]["mapping_rerun"])
        self.assertEqual(before, runtime.pilot.identities([Path(p) for p in before]))

    def test_changed_adoption_origin_is_not_a_cache_hit(self):
        self.candidate(); self.run_profile()
        path = self.directory / runtime.RECEIPT
        original = json.loads(path.read_text())
        for adoption in (None, {**original["adoption"], "mapping_rerun": True},
                         {**original["adoption"], "report": {"path": "different", "sha256": "different"}}):
            path.write_text(json.dumps({**original, "adoption": adoption}))
            self.assertFalse(self.profile.validate_batch(0))

    def test_candidate_corruption_refuses_publication(self):
        path, source = self.candidate()
        (path.parent / "result.paf").write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "output changed"): self.run_profile()
        self.assertFalse((self.directory / "complete.json").exists())

    def test_mapper_failure_cannot_publish(self):
        with patch.object(runtime.pilot, "run_child", return_value={"returncode": 124}), \
             self.assertRaisesRegex(ValueError, "failed or timed out"):
            self.run_profile()
        self.assertFalse((self.directory / "complete.json").exists())


if __name__ == "__main__":
    unittest.main()
