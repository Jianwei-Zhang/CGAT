"""Filesystem/rollback contracts for updating tools plus an existing runtime."""
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from server.tools import update_workspace_runtime as updater


class WorkspaceRuntimeUpdateTests(unittest.TestCase):
    REVISION = "a" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "new source"
        self.tools = self.root / "installed tools"
        self.workspace = self.root / "project"
        payload = {name: b"new code\n" for name in updater.ENTRYPOINTS}
        payload.update({"run.sh": b"#!/bin/sh\nexit 0\n", "prepare.sh": b"new prepare\n",
                        "install.sh": b"new install\n", "tools/server_run.py": b"new runner\n",
                        "tools/grt_core/__init__.py": b"new core\n",
                        "tools/grt_core/sub/module.py": b"new module\n",
                        "skills/gpm-server/server-tools.path": b"../..\n",
                        "README.md": b"new documentation\n"})
        for name, data in payload.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755 if name.endswith(".sh") else 0o644)
        self.manifest = {name: {"sha256": updater.digest(data),
                               "mode": stat.S_IMODE((self.source / name).stat().st_mode)}
                         for name, data in payload.items()}
        (self.source / "SOURCE.json").write_text(json.dumps({"git_revision": self.REVISION, "files": self.manifest}))
        shutil.copytree(self.source, self.tools)
        for name in payload:
            (self.tools / name).write_bytes(b"old tool " + name.encode())
        (self.tools / "SOURCE.json").write_text('{"git_revision":"old"}')
        (self.tools / updater.BINDING).write_text("/user/custom/binding\n")
        (self.tools / "run_gpm_v2.log").write_bytes(b"original user log")
        (self.tools / "GPM_Server_2.0.12_source.tar.gz").write_bytes(b"original archive")
        for name in updater.ENTRYPOINTS | {"tools/grt_core/__init__.py", "tools/grt_core/sub/module.py"}:
            path = self.workspace / ".prepare_lib" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old runtime " + name.encode())
        for name in ("run_all.sh", "run_grt_step2.sh", "run_grt_step3.sh"):
            (self.workspace / name).write_bytes(b"generated command; do not execute")
        for name, data in {"metadata/package.tsv": b"workflow\tschema_version\ngpm_grt_precomputed_v2\t2\n",
                           "data/input.fa": b">input\nACGT\n", "grt/q/q3.fa": b">q3\nACGT\n",
                           "grt/cache/raw/result.coords": b"original alignment",
                           "grt/checkpoints/step3.json": b"original checkpoint",
                           ".prepare_lib/lib/user-state.sh": b"original generated library"}.items():
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in root.rglob("*") if p.is_file() and ".run_all" not in p.relative_to(root).parts}

    def update(self, apply=True):
        return updater.update(self.source, self.workspace, self.tools, self.REVISION, apply=apply)

    def test_engine_fingerprint_matches_production_identity(self):
        from server.tools.grt_core.repair_common import repair_engine_sha256
        tools = Path(updater.__file__).resolve().parent
        self.assertEqual(updater.engine_hash(tools), repair_engine_sha256(tools / "grt_core"))

    def test_dry_run_is_read_only(self):
        before = tuple(self.snapshot(p) for p in (self.source, self.tools, self.workspace))
        result = self.update(apply=False)
        self.assertEqual(result["status"], "verified_dry_run")
        self.assertFalse(result["analysis_started"])
        self.assertEqual(before, tuple(self.snapshot(p) for p in (self.source, self.tools, self.workspace)))
        self.assertFalse((self.workspace / ".run_all").exists())

    def test_updates_both_roots_preserves_inputs_logs_binding_and_supports_rollback(self):
        source_before, tools_before, workspace_before = (self.snapshot(p) for p in
                                                         (self.source, self.tools, self.workspace))
        result = self.update()
        self.assertEqual(result["status"], "updated")
        self.assertFalse(result["analysis_started"])
        self.assertEqual(result["engine_sha256"], updater.engine_hash(self.source / "tools"))
        self.assertEqual(result["engine_sha256"], updater.engine_hash(self.tools / "tools"))
        self.assertEqual(result["engine_sha256"], updater.engine_hash(self.workspace / ".prepare_lib/tools"))
        for name in ("data/input.fa", "grt/q/q3.fa", "grt/cache/raw/result.coords",
                     "grt/checkpoints/step3.json", "run_all.sh", ".prepare_lib/lib/user-state.sh"):
            self.assertEqual(self.snapshot(self.workspace)[name], workspace_before[name])
        for name in (updater.BINDING, "run_gpm_v2.log", "GPM_Server_2.0.12_source.tar.gz"):
            self.assertEqual(self.snapshot(self.tools)[name], tools_before[name])
        self.assertEqual(self.snapshot(self.source), source_before)
        backup = Path(result["backup"])
        self.assertTrue((backup / "journal.json").is_file())
        updater.rollback(backup)
        self.assertEqual(self.snapshot(self.tools), tools_before)
        self.assertEqual(self.snapshot(self.workspace), workspace_before)
        self.assertFalse((self.workspace / ".run_all/lock").exists())
        self.assertFalse((self.tools / ".run_all/lock").exists())

    def test_evidence_and_logging_tools_update_both_roots_and_restore_on_rollback(self):
        paths = []
        for relative in ("tools/grt_evidence_package.py", "tools/grt_display_evidence.py",
                         "tools/run_all_runner.py", "tools/run_progress.py", "tools/view_run_log.py"):
            self.assertIn(relative, updater.ENTRYPOINTS)
            runtime_file = self.workspace / ".prepare_lib" / relative
            tool_file = self.tools / relative
            paths.append((relative, runtime_file, tool_file, runtime_file.read_bytes(), tool_file.read_bytes()))
        result = self.update()
        for relative, runtime_file, tool_file, _, _ in paths:
            expected = (self.source / relative).read_bytes()
            self.assertEqual(runtime_file.read_bytes(), expected)
            self.assertEqual(tool_file.read_bytes(), expected)
        updater.rollback(Path(result["backup"]))
        for _, runtime_file, tool_file, old_runtime, old_tool in paths:
            self.assertEqual(runtime_file.read_bytes(), old_runtime)
            self.assertEqual(tool_file.read_bytes(), old_tool)

    def test_logging_modules_added_to_old_runtime_are_removed_on_rollback(self):
        added = []
        for root in (self.tools, self.workspace / ".prepare_lib"):
            for name in ("tools/run_progress.py", "tools/view_run_log.py"):
                path = root / name
                path.unlink()
                added.append(path)
        before_tools = self.snapshot(self.tools)
        before_workspace = self.snapshot(self.workspace)
        result = self.update()
        self.assertTrue(all(path.is_file() for path in added))
        updater.rollback(Path(result["backup"]))
        self.assertTrue(all(not path.exists() for path in added))
        self.assertEqual(self.snapshot(self.tools), before_tools)
        self.assertEqual(self.snapshot(self.workspace), before_workspace)

    def test_corrupt_source_or_wrong_revision_is_rejected_before_writes(self):
        before = self.snapshot(self.tools), self.snapshot(self.workspace)
        with self.assertRaisesRegex(ValueError, "revision"):
            updater.update(self.source, self.workspace, self.tools, "b" * 40, apply=True)
        (self.source / "prepare.sh").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.update()
        self.assertEqual(before, (self.snapshot(self.tools), self.snapshot(self.workspace)))

    def test_live_workspace_lock_is_not_stolen(self):
        lock = updater.workspace_lock(self.workspace)
        lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, "already running"):
                self.update()
            owner = json.loads((self.workspace / ".run_all/lock/owner.json").read_text())
            self.assertEqual(owner["run_id"], lock.run_id)
        finally:
            lock.release()
        self.assertFalse((self.tools / ".run_all/lock").exists())

    def test_foreign_host_lock_is_not_stolen(self):
        lock_dir = self.workspace / ".run_all/lock"
        lock_dir.mkdir(parents=True)
        owner = {"workspace": str(self.workspace), "hostname": "another-login-node",
                 "pid": 1234, "run_id": "foreign-job"}
        (lock_dir / "owner.json").write_text(json.dumps(owner))
        with self.assertRaisesRegex(RuntimeError, "already running"):
            self.update()
        self.assertEqual(json.loads((lock_dir / "owner.json").read_text()), owner)

    def test_standalone_grt_process_is_detected(self):
        for relative in (".prepare_lib/tools/grt_step2.py",
                         ".prepare_lib/tools/grt_evidence_package.py",
                         "finalize_grt_evidence.sh"):
            with self.subTest(process=relative):
                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                          str(self.workspace / relative)])
                try:
                    with self.assertRaisesRegex(ValueError, "active Server process"):
                        self.update()
                finally:
                    child.terminate()
                    child.wait(timeout=5)

    def start_script(self, path, argument, cwd):
        ready = self.root / "child-ready"
        ready.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from pathlib import Path\nimport time\n"
            f"Path({str(ready)!r}).write_text('ready')\ntime.sleep(60)\n")
        child = subprocess.Popen([sys.executable, argument], cwd=cwd)
        self.addCleanup(lambda: (child.terminate(), child.wait(timeout=5)) if child.poll() is None else None)
        deadline = time.monotonic() + 5
        while not ready.is_file() and time.monotonic() < deadline:
            self.assertIsNone(child.poll())
            time.sleep(.01)
        self.assertTrue(ready.is_file())
        return child

    def test_relative_and_aliased_standalone_processes_are_detected_before_writes(self):
        alias = self.root / "project-alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        relative = ".prepare_lib/tools/grt_evidence_package.py"
        cases = [
            (self.workspace / relative, relative, self.workspace),
            (self.workspace / relative, "./" + relative, self.workspace),
            (self.workspace / relative, "grt_evidence_package.py", self.workspace / ".prepare_lib/tools"),
            (self.workspace / relative, str(alias / relative), self.root),
            (self.workspace / "finalize_grt_evidence.sh", "finalize_grt_evidence.sh", self.workspace),
            (self.tools / "tools/grt_evidence_package.py", "tools/grt_evidence_package.py", self.tools),
        ]
        for path, argument, cwd in cases:
            with self.subTest(argument=argument):
                child = self.start_script(path, argument, cwd)
                before = self.snapshot(self.workspace), self.snapshot(self.tools)
                try:
                    for apply in (False, True):
                        with self.assertRaisesRegex(ValueError, "active Server process"):
                            self.update(apply=apply)
                    self.assertEqual(before, (self.snapshot(self.workspace), self.snapshot(self.tools)))
                finally:
                    child.terminate()
                    child.wait(timeout=5)

    def test_unrelated_relative_script_does_not_block_this_workspace(self):
        unrelated = self.root / "unrelated"
        relative = ".prepare_lib/tools/grt_evidence_package.py"
        child = self.start_script(unrelated / relative, relative, unrelated)
        try:
            self.assertEqual(self.update(apply=False)["status"], "verified_dry_run")
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_rollback_refuses_an_active_relative_script(self):
        result = self.update()
        relative = ".prepare_lib/tools/grt_evidence_package.py"
        child = self.start_script(self.workspace / relative, relative, self.workspace)
        try:
            with self.assertRaisesRegex(ValueError, "active Server process"):
                updater.rollback(Path(result["backup"]))
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_symlinks_and_unknown_core_modules_are_refused(self):
        path = self.workspace / ".prepare_lib/tools/grt_step2.py"
        path.unlink()
        path.symlink_to(self.source / "tools/grt_step2.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.update()
        path.unlink()
        path.write_text("old")
        (self.workspace / ".prepare_lib/tools/grt_core/legacy.py").write_text("unknown")
        with self.assertRaisesRegex(ValueError, "unexpected old core"):
            self.update()

    def test_symlinked_lock_state_is_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.workspace / ".run_all").symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked lock state"):
            self.update()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_file_created_after_planning_is_not_overwritten(self):
        path = self.tools / "README.md"
        path.unlink()
        real_lock = updater.workspace_lock

        def lock_with_race(root):
            lock = real_lock(root)
            if root == self.workspace:
                acquire = lock.acquire

                def create_then_acquire():
                    path.write_text("new user file after planning")
                    acquire()

                lock.acquire = create_then_acquire
            return lock

        with mock.patch.object(updater, "workspace_lock", side_effect=lock_with_race):
            with self.assertRaisesRegex(ValueError, "appeared/disappeared"):
                self.update()
        self.assertEqual(path.read_text(), "new user file after planning")
        self.assertEqual((self.tools / "SOURCE.json").read_text(), '{"git_revision":"old"}')

    def test_write_failure_restores_both_targets(self):
        before = self.snapshot(self.tools), self.snapshot(self.workspace)
        real_write = updater.write_atomic
        failed = False

        def fail_once(path, data, mode=0o644):
            nonlocal failed
            if path == self.tools / "prepare.sh" and not failed:
                failed = True
                raise OSError("simulated interrupted write")
            return real_write(path, data, mode)

        with mock.patch.object(updater, "write_atomic", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.update()
        self.assertTrue(failed)
        self.assertEqual(before, (self.snapshot(self.tools), self.snapshot(self.workspace)))
        journals = list((self.workspace / ".run_all").glob("runtime-update-*/journal.json"))
        self.assertEqual(len(journals), 1)
        self.assertEqual(json.loads(journals[0].read_text())["status"], "rolled_back_after_failure")

    def test_rollback_refuses_new_user_edits_or_corrupt_backup_before_writes(self):
        result = self.update()
        backup = Path(result["backup"])
        (self.tools / "prepare.sh").write_text("new user edit")
        before = self.snapshot(self.tools), self.snapshot(self.workspace)
        with self.assertRaisesRegex(ValueError, "changed after update"):
            updater.rollback(backup)
        self.assertEqual(before, (self.snapshot(self.tools), self.snapshot(self.workspace)))
        (self.tools / "prepare.sh").write_bytes((self.source / "prepare.sh").read_bytes())
        (backup / "original/tools/prepare.sh").write_text("corrupt backup")
        before = self.snapshot(self.tools), self.snapshot(self.workspace)
        with self.assertRaisesRegex(ValueError, "backup integrity"):
            updater.rollback(backup)
        self.assertEqual(before, (self.snapshot(self.tools), self.snapshot(self.workspace)))
