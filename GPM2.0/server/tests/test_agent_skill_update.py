"""Behavioral filesystem contracts for user-state-preserving skill staging."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills/gpm-server"
spec = importlib.util.spec_from_file_location(
    "stage_skill_update", SKILL / "scripts/stage_skill_update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class SkillUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.old, self.out = (
            self.root / name for name in ("new source", "installed skill", "staged skill"))
        for path in (self.source, self.old):
            shutil.copytree(SKILL, path, ignore=shutil.ignore_patterns("__pycache__", "local"))
        (self.old / "SKILL.md").write_text("Old official core with a local customization\n")
        self.binding = b"/unavailable/Server tools; literal\n"
        (self.old / "server-tools.path").write_bytes(self.binding)

    def stage(self):
        return update.stage(self.source, self.old, self.out)

    def local_state(self):
        local = self.old / "local"
        local.mkdir()
        (local / "notes.md").write_text("已验证的本地记录；不是通用操作权限。\n")
        (local / "preferences.md").write_text("Mode: ask\n")
        (local / "nested").mkdir()
        (local / "nested/evidence-pointer.txt").write_bytes(b"local report path\n")
        return local

    def snapshot(self, root):
        return {p.relative_to(root): p.read_bytes()
                for p in root.rglob("*") if p.is_file()}

    def test_preserves_local_bytes_and_absolute_binding_without_mutating_inputs(self):
        local = self.local_state()
        old, source = self.snapshot(self.old), self.snapshot(self.source)
        self.stage()
        self.assertEqual(self.snapshot(self.out / "local"), self.snapshot(local))
        self.assertEqual((self.out / "server-tools.path").read_bytes(), self.binding)
        self.assertEqual((self.out / "SKILL.md").read_bytes(),
                         (self.source / "SKILL.md").read_bytes())
        self.assertEqual(self.snapshot(self.old), old)
        self.assertEqual(self.snapshot(self.source), source)
        if os.name == "posix":
            self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)

    def test_explicit_new_tools_binding_preserves_notes_and_old_binding(self):
        self.local_state()
        tools = self.root / "new Server"
        (tools / "tools/grt_core").mkdir(parents=True)
        for name in ("run.sh", "prepare.sh", "install.sh", "tools/server_run.py"):
            (tools / name).write_text("# not executed\n")
        update.stage(self.source, self.old, self.out, tools)
        self.assertEqual((self.out / "server-tools.path").read_text(), str(tools) + "\n")
        self.assertEqual((self.old / "server-tools.path").read_bytes(), self.binding)
        self.assertEqual((self.out / "local/notes.md").read_bytes(),
                         (self.old / "local/notes.md").read_bytes())

    def test_incomplete_or_relative_new_tools_never_changes_old_state(self):
        for tools in (Path("relative"), self.root / "missing"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                update.stage(self.source, self.old, self.out, tools)
            self.assertFalse(self.out.exists())
            self.assertEqual((self.old / "server-tools.path").read_bytes(), self.binding)

    def test_no_local_state_does_not_create_preferences_or_notes(self):
        self.stage()
        self.assertFalse((self.out / "local").exists())

    def test_does_not_import_source_local_state_caches_or_old_core_customizations(self):
        (self.source / "local").mkdir()
        (self.source / "local/notes.md").write_text("Another user's private notes")
        cache = self.source / "scripts/__pycache__"
        cache.mkdir()
        (cache / "example.pyc").write_bytes(b"not source")
        (self.old / "custom-command.sh").write_text("never migrate implicitly")
        self.stage()
        self.assertFalse((self.out / "local").exists())
        self.assertFalse((self.out / "scripts/__pycache__").exists())
        self.assertFalse((self.out / "custom-command.sh").exists())

    def test_relative_binding_retains_old_server_after_relocation(self):
        server = self.root / "Server tools"
        (server / "tools/grt_core").mkdir(parents=True)
        for name in ("run.sh", "prepare.sh", "install.sh", "tools/server_run.py"):
            (server / name).write_text("# existence fixture only\n")
        (self.old / "server-tools.path").write_text("../Server tools\n")
        self.stage()
        result = subprocess.run(
            ["bash", str(self.out / "scripts/server_tools_path.sh")],
            cwd="/", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), server)

    def test_unavailable_binding_is_preserved_not_repaired_or_replaced(self):
        self.stage()
        result = subprocess.run(
            ["bash", str(self.out / "scripts/server_tools_path.sh")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.out / "server-tools.path").read_bytes(), self.binding)

    def test_refuses_existing_even_empty_destination(self):
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            self.stage()
        self.assertEqual(list(self.out.iterdir()), [])
        marker = self.out / "keep"
        marker.write_bytes(b"unchanged")
        with self.assertRaises(FileExistsError):
            self.stage()
        self.assertEqual(marker.read_bytes(), b"unchanged")

    def test_refuses_all_overlapping_paths(self):
        for out in (self.old, self.old / "child", self.source / "child", self.root):
            with self.subTest(out=out), self.assertRaises(ValueError):
                update.stage(self.source, self.old, out)
        with self.assertRaises(ValueError):
            update.stage(self.old, self.old, self.out)
        self.assertFalse(self.out.exists())

    def test_invalid_and_missing_bindings_leave_no_output(self):
        record = self.old / "server-tools.path"
        for raw in (b"", b"\n", b"/one\n/two\n", b"/one\r\n", b"/bad\0path", b"\xff"):
            record.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.stage()
            self.assertFalse(self.out.exists())
            self.assertEqual(record.read_bytes(), raw)
        record.unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_refuses_symlinked_local_content_and_binding(self):
        local = self.local_state()
        link = local / "external"
        link.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            self.stage()
        link.unlink()
        record = self.old / "server-tools.path"
        record.unlink()
        record.symlink_to(self.source / "server-tools.path")
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_refuses_symlinked_roots_parents_and_official_files(self):
        link = self.root / "linked"
        link.symlink_to(self.old, target_is_directory=True)
        for installed, out in ((link, self.out), (self.old, link / "child")):
            with self.assertRaises(ValueError):
                update.stage(self.source, installed, out)
        reference = self.source / "references/local-learning.md"
        reference.unlink()
        reference.symlink_to(self.old / "references/local-learning.md")
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_refuses_non_directory_local_and_special_files(self):
        local = self.old / "local"
        local.write_text("not a directory")
        with self.assertRaises(ValueError):
            self.stage()
        local.unlink()
        if hasattr(os, "mkfifo"):
            local.mkdir()
            os.mkfifo(local / "pipe")
            with self.assertRaises(ValueError):
                self.stage()
        self.assertFalse(self.out.exists())

    def test_copy_failure_removes_only_own_partial_output(self):
        self.local_state()
        old = self.snapshot(self.old)
        with mock.patch.object(update.shutil, "copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.stage()
        self.assertFalse(self.out.exists())
        self.assertEqual(self.snapshot(self.old), old)

    @unittest.skipUnless(shutil.which("git"), "Git ignore integration needs git")
    def test_installed_ignore_rules_keep_local_notes_out_of_ordinary_git_adds(self):
        self.local_state()
        self.stage()
        result = subprocess.run(["git", "init", "--quiet", str(self.out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        checked = subprocess.run(
            ["git", "-C", str(self.out), "check-ignore", "local/notes.md", "local/preferences.md"],
            capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(set(checked.stdout.splitlines()),
                         {"local/notes.md", "local/preferences.md"})

    def test_never_executes_old_tools_locator_during_migration(self):
        marker = self.root / "unwanted-execution"
        (self.old / "scripts/server_tools_path.sh").write_text(
            f"#!/bin/bash\ntouch '{marker}'\nexit 1\n")
        self.stage()
        self.assertFalse(marker.exists())

    def test_missing_official_file_or_output_parent_leaves_no_partial_stage(self):
        original = (self.source / "SKILL.md").read_bytes()
        (self.source / "SKILL.md").unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse(self.out.exists())
        (self.source / "SKILL.md").write_bytes(original)
        with self.assertRaises(ValueError):
            update.stage(self.source, self.old, self.root / "absent/child")
        self.assertFalse((self.root / "absent").exists())

    def test_cli_copied_skill_needs_no_repo_and_reports_no_activation(self):
        self.local_state()
        command = [sys.executable, str(self.source / "scripts/stage_skill_update.py"),
                   "--installed", str(self.old), "--out", str(self.out)]
        result = subprocess.run(command, cwd="/", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Not activated", result.stdout)
        saved = self.snapshot(self.out)
        repeated = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(self.snapshot(self.out), saved)


if __name__ == "__main__":
    unittest.main()
