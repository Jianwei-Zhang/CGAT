"""An unchanged locked run reuses its own check; standalone or changed inputs never do."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from refinement_bundle_fixture import FIXTURE
from lgz_contract import ContractError, validate_contract
from lgz_core.contract import tables
from lgz_core.contract.validation_pass import CHANNEL_ENV, DEFER_ENV, READY, ValidationPass, can_reuse_validation
from lgz_core.q0_publication import SELECTION
from lgz_core.stage_io import atomic_write_json as write_evidence_summary
from run_all_runner import PlanUnit, Runner, WorkspaceLock
from run_outer_checkpoints import OuterCheckpointManager
from workspace_layout import MANIFEST, MIGRATION, initialize_workspace


class EvidenceHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "workspace"
        self.channel = Path(tmp.name) / "handoff.json"
        self.layout = initialize_workspace(self.root)
        for name, contents in json.loads(FIXTURE.read_text())["files"].items():
            target = self.layout.path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
        self.manager = OuterCheckpointManager(self.root)

    def publish(self):
        valid, reason = self.manager.publish_validated_evidence(self.channel, "owner")
        self.assertTrue(valid, reason)
        self.assertTrue(can_reuse_validation(self.channel, self.root, "owner"))

    def test_same_runner_can_skip_but_independent_or_changed_input_requires_real_validation(self):
        lock = WorkspaceLock(self.root, "owner")
        lock.acquire()
        self.addCleanup(lock.release)
        self.publish()
        summary = json.loads(self.layout.path("metadata/grt_contract_summary.json").read_text())
        public = validate_contract(self.root)
        self.assertEqual({k: v for k, v in summary.items() if k not in {"used_contigs", "supplemented_contigs"}}, public)
        self.assertEqual(summary["used_contigs"], 4)
        comparison = self.root.parent / "standalone-summary.json"
        write_evidence_summary(comparison, summary)
        self.assertEqual(self.layout.path("metadata/grt_contract_summary.json").read_bytes(), comparison.read_bytes())
        # A real child verifies its parent's live lock; stop after the validation
        # decision, before unrelated baseline/index/tool work. Count full checks.
        child = '''
import sys
from pathlib import Path
from unittest.mock import patch
from lgz_contract import validate_contract
from post_lgz_refinement import run, ParentLock
root = Path(sys.argv[1])
lock = ParentLock(root, "owner") if sys.argv[2] == "managed" else object()
with patch("lgz_contract.validate_contract", wraps=validate_contract) as check, patch("post_lgz_refinement.publish_baseline", side_effect=StopIteration):
    try:
        run(root, lock, {"run_id": "owner"})
    except StopIteration:
        pass
    assert check.call_count == int(sys.argv[3]), check.call_count
'''
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "tools"),
               CHANNEL_ENV: str(self.channel), "GPM_REPORT_RUN_ID": "owner", "GPM_REPORT_UNIT_ID": "refinement"}
        def worker(kind, checks):
            result = subprocess.run([sys.executable, "-B", "-c", child, str(self.root), kind, str(checks)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        worker("managed", 0)
        worker("standalone", 1)
        self.assertFalse(can_reuse_validation(self.channel, self.root, "next-run"))
        # Change inode but preserve content, size and mtime; full validation
        # still succeeds and the child must actually call it, not trust the old check.
        raw = next(iter(json.loads(self.layout.path(SELECTION).read_text())["artifact_hashes"]))
        path = self.layout.path(raw)
        self.assertIn(str(path.relative_to(self.root)), json.loads(self.channel.read_text())["files"])
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        st = path.stat()
        os.utime(replacement, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(replacement, path)
        worker("managed", 1)
        path.write_bytes(b"corrupt")
        other = self.channel.with_name("new-handoff")
        self.assertFalse(self.manager.publish_validated_evidence(other, "owner")[0])
        self.assertFalse(other.exists())

    def test_runner_not_a_child_ready_line_authorizes_publication(self):
        from refinement_config import save_request
        self.layout.path("metadata/prepare_options.tsv").write_text("key\tvalue\nthreads\t1\n")
        script = self.layout.path("finalize_lgz_evidence.sh")
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(f'#!/bin/bash\nset -eu\n[[ "${{{DEFER_ENV}}}" == 1 && -z "${{{CHANNEL_ENV}:-}}" ]]\necho "{READY}"\n')
        unit = PlanUnit("finalize_evidence", script.relative_to(self.root).as_posix(), ".runtime/logs/run_all.log")
        for valid in (True, False):
            run_id = f"run-{valid}"
            channel = self.channel.with_name(run_id)
            if not valid:
                self.layout.path("metadata/grt_stage_status.tsv").write_text("corrupt\n")
            save_request(self.root, {}, run_id)
            lock = WorkspaceLock(self.root, run_id)
            lock.acquire()
            try:
                runner = Runner(self.root, [unit], run_id, color="never")
                runner.contract_channel = channel
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), mock.patch(
                    "run_outer_checkpoints.validate_contract", wraps=validate_contract
                ) as check:
                    self.assertEqual(runner.run(), 0 if valid else 2)
                    self.assertEqual(check.call_count, 1)
            finally:
                lock.release()
            self.assertEqual(channel.exists(), valid)
            self.assertEqual(can_reuse_validation(channel, self.root, run_id), valid)

    def test_missing_malformed_or_stale_inputs_fall_back(self):
        self.assertFalse(can_reuse_validation(self.channel, self.root, "owner"))
        self.publish()
        proof = self.channel.read_text()
        for name in (MANIFEST, MIGRATION, str(self.layout.path("metadata/grt_contract_summary.json").relative_to(self.root))):
            data = json.loads(proof)
            del data["files"][name]
            self.channel.write_text(json.dumps(data))
            self.assertFalse(can_reuse_validation(self.channel, self.root, "owner"), name)
        self.channel.write_text("{partial")
        self.assertFalse(can_reuse_validation(self.channel, self.root, "owner"))
        self.channel.write_text(proof)
        (self.root / MIGRATION).write_text("{}")
        self.assertFalse(can_reuse_validation(self.channel, self.root, "owner"))
        (self.root / MIGRATION).unlink()
        self.layout.path("metadata/grt_contract_summary.json").write_text("{}")
        self.assertFalse(can_reuse_validation(self.channel, self.root, "owner"))

    def test_repeated_reference_checks_path_once_but_rejects_changes_and_escape(self):
        relative = "metadata/package.tsv"
        path = self.layout.path(relative)
        with self.assertRaisesRegex(ContractError, "INPUT_CHANGED"), ValidationPass(self.root).checking():
            with mock.patch.object(tables, "workspace_join", wraps=tables.workspace_join) as joins:
                for i in range(1000):
                    self.assertEqual(tables.bundle_path(self.root, relative, f"row {i}"), path)
                self.assertEqual(joins.call_count, 1)
            path.rename(self.root.parent / "outside")
            path.symlink_to(self.root.parent / "outside")
        with ValidationPass(self.root).checking(), self.assertRaisesRegex(ContractError, "escapes bundle root"):
            tables.bundle_path(self.root, relative, "changed")
