"""Offline end-to-end contracts for the shared installer/update entrypoints."""
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
import os
import sys
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from server.tools import update_server as update

paths = update.paths
downloads = update.downloads


class DownloadTests(unittest.TestCase):
    def record(self, origin="GitHub Release", payload=b"archive"):
        return {"tag": "v2.0.12", "asset": "GPM_Server_2.0.12_source.tar.gz", "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(), "origin": origin,
                "url": "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.12/GPM_Server_2.0.12_source.tar.gz",
                "download_url": downloads.SITE + "downloads/v2.0.12/GPM_Server_2.0.12_source.tar.gz" if origin == "CGAT docs" else "https://github.com/archive"}

    def test_docs_success_never_contacts_github_metadata(self):
        with mock.patch.object(downloads, "github_release") as github, mock.patch.object(downloads, "docs_release", return_value=self.record("CGAT docs")):
            result = downloads.discover(log=lambda _: None)
        github.assert_not_called()
        self.assertEqual(result["origin"], "CGAT docs")

    def test_docs_failure_falls_back_and_both_fail_is_not_latest(self):
        with mock.patch.object(downloads, "github_release", return_value=self.record()) as github, mock.patch.object(downloads, "docs_release", side_effect=OSError("down")):
            self.assertEqual(downloads.discover(log=lambda _: None)["origin"], "GitHub Release")
            github.assert_called_once()
        with mock.patch.object(downloads, "github_release", side_effect=OSError("blocked")), mock.patch.object(downloads, "docs_release", side_effect=OSError("down")):
            with self.assertRaisesRegex(ValueError, "freshness is unknown"):
                downloads.discover(log=lambda _: None)

    def test_docs_download_success_never_contacts_github(self):
        record = self.record()
        with mock.patch.object(downloads, "read_url", return_value=b"archive") as read:
            self.assertEqual(downloads.download(record, log=lambda _: None), b"archive")
        read.assert_called_once()
        self.assertTrue(read.call_args.args[0].startswith(downloads.SITE))

    def test_corruption_or_http_failure_falls_back_with_same_digest(self):
        record = self.record()
        for broken in (b"corrupt", OSError("HTTP 502")):
            with self.subTest(broken=broken), mock.patch.object(downloads, "read_url", side_effect=[broken, b"archive"]) as read:
                self.assertEqual(downloads.download(record, log=lambda _: None), b"archive")
                self.assertTrue(read.call_args_list[0].args[0].startswith(downloads.SITE))
                self.assertEqual(read.call_args_list[1].args[0], record["url"])
        with mock.patch.object(downloads, "read_url", return_value=b"corrupt"):
            with self.assertRaisesRegex(ValueError, "Both archive"):
                downloads.download(record, log=lambda _: None)

    def test_docs_manifest_validation_and_official_origin_boundary(self):
        record = self.record()
        manifest = {"repository": "Jianwei-Zhang/CGAT", "tag": record["tag"], "assets": [{
            "name": record["asset"], "bytes": record["size"], "sha256": record["sha256"],
            "path": "/downloads/v2.0.12/" + record["asset"], "upstream": record["url"]}]}
        info = {"releaseAssetManifest": "downloads/v2.0.12/release.json"}
        with mock.patch.object(downloads, "read_url", side_effect=[json.dumps(info).encode(), json.dumps(manifest).encode()]):
            self.assertEqual(downloads.docs_release()["sha256"], record["sha256"])
        for relative in ("https://evil.test/a", "../private", "downloads/v2.0.12/../../secret"):
            with mock.patch.object(downloads, "read_url", return_value=json.dumps({"releaseAssetManifest": relative}).encode()):
                with self.assertRaises(ValueError):
                    downloads.docs_release()
        for url in ("http://riceome.hzau.edu.cn/cgat/a", "https://evil.test/a", "https://riceome.hzau.edu.cn/private", "https://user@github.com/a"):
            with self.assertRaises(ValueError):
                downloads.check_url(url)

    def test_malformed_docs_objects_are_errors_not_crashes(self):
        for info in ([], None, "html", {"releaseAssetManifest": "downloads/v2.0.12/release.json"}):
            replies = [json.dumps(info).encode(), b'[]']
            with self.subTest(info=info), mock.patch.object(downloads, "read_url", side_effect=replies):
                with self.assertRaises(ValueError):
                    downloads.docs_release()



class CoordinatedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tools, self.source, self.work, self.skill = [self.root / n for n in ("tools", "source", "project", "agent skill")]
        data = {name: b"old code\n" for name in update.core.ENTRYPOINTS}
        data.update({"run.sh": b"#!/bin/sh\nexit 0\n", "prepare.sh": b"prepare\n", "install.sh": b"install\n",
            "tools/server_run.py": b"runner\n", "tools/grt_core/__init__.py": b"core\n",
            "lib/incremental_common.sh": b"old lib\n", "contracts/test.json": b"{}\n",
            "skills/gpm-server/SKILL.md": b"skill v3\n", "skills/gpm-server/server-tools.path": b"../..\n",
            "skills/gpm-server/scripts/example.py": b"script\n", "README.md": b"old readme\n"})
        for name, payload in data.items():
            file = self.tools / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(payload)
            file.chmod(0o755 if name.endswith(".sh") else 0o644)
        self.make_manifest(self.tools, "a" * 40, "2026-10-25T00:00:00+00:00")
        self.work.mkdir()
        for name in ("run_all.sh", "run_grt_step2.sh", "run_grt_step3.sh"):
            (self.work / name).write_text("keep generated script\n")
        (self.work / "metadata").mkdir()
        (self.work / "metadata/package.tsv").write_text("workflow\tschema_version\ngpm_grt_precomputed_v2\t2\n")
        for name in data:
            if update.runtime_file(name):
                target = self.work / ".prepare_lib" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.tools / name, target)
        shutil.copy2(self.tools / "SOURCE.json", self.work / ".prepare_lib/SOURCE.json")
        (self.work / ".prepare_lib/server-tools.path").write_text(str(self.tools) + "\n")
        shutil.copytree(self.tools, self.source)
        (self.source / "lib/incremental_common.sh").write_text("new lib\n")
        (self.source / "tools/grt_step2.py").write_text("new step2\n")
        (self.source / "skills/gpm-server/SKILL.md").write_text("skill v4\n")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        shutil.copytree(self.tools / "skills/gpm-server", self.skill)
        old = json.loads((self.tools / "SOURCE.json").read_text())
        sf = {n[len(update.SKILL_PREFIX):]: r for n, r in old["files"].items() if n.startswith(update.SKILL_PREFIX)}
        (self.skill / "official-source.json").write_text(json.dumps({"files": sf}))
        paths.bind(self.skill, self.tools)
        for root in (self.skill, self.tools / "skills/gpm-server"):
            (root / "local").mkdir()
            (root / "local/notes.md").write_bytes("本站经验\n".encode())
            (root / "local/custom.txt").write_bytes(b"custom local state")
        for name in ("logs/run.log", "cache/mummer", "result.fasta"):
            target = self.work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("preserve\n")
        self.release = {"tag": "v2.0.12"}
        self.environment = mock.patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("GPM_SERVER_SKILL_DIR", None)

    def make_manifest(self, root, revision, date):
        files = {p.relative_to(root).as_posix(): {"sha256": update.core.digest(p.read_bytes()), "mode": p.stat().st_mode & 0o777}
                 for p in root.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
        (root / "SOURCE.json").write_text(json.dumps({"release": "v2.0.12", "git_revision": revision, "built_at": date, "files": files}, indent=2) + "\n")

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mode & 0o777)
                for p in root.rglob("*") if p.is_file() and ".run_all" not in p.parts}

    def plan(self, workspace=True):
        return update.prepare(self.source, self.tools, self.work if workspace else None, self.release)

    def test_aligns_full_runtime_and_registered_skills_preserves_local_and_rolls_back(self):
        before = [self.snapshot(root) for root in (self.tools, self.work, self.skill)]
        plan = self.plan()
        self.assertEqual([self.snapshot(root) for root in (self.tools, self.work, self.skill)], before)
        backup = update.apply(plan)
        self.assertEqual((self.work / ".prepare_lib/lib/incremental_common.sh").read_text(), "new lib\n")
        self.assertEqual((self.skill / "SKILL.md").read_text(), "skill v4\n")
        self.assertEqual((self.skill / "local/notes.md").read_bytes(), before[2]["local/notes.md"][0])
        self.assertEqual((self.work / "run_all.sh").read_bytes(), before[1]["run_all.sh"][0])
        self.assertFalse(self.plan()["files"])
        update.rollback(backup)
        self.assertEqual([self.snapshot(root) for root in (self.tools, self.work, self.skill)], before)

    def test_tool_only_update_leaves_project_unchanged_then_project_only_alignment(self):
        before = self.snapshot(self.work)
        update.apply(self.plan(workspace=False))
        self.assertEqual(self.snapshot(self.work), before)
        plan = self.plan()
        self.assertTrue(plan["files"])
        self.assertEqual({p["kind"] for p in plan["files"]}, {"runtime"})
        update.apply(plan)
        self.assertFalse(self.plan()["files"])

    def test_legacy_project_records_binding_after_planning_only(self):
        binding = self.work / ".prepare_lib/server-tools.path"
        binding.unlink()
        plan = self.plan()
        self.assertFalse(binding.exists())
        update.apply(plan)
        self.assertEqual(binding.read_text().strip(), str(self.tools))

    def test_conflicting_project_binding_refused(self):
        (self.work / ".prepare_lib/server-tools.path").write_text("/other/Server\n")
        with self.assertRaisesRegex(ValueError, "binding conflicts"):
            self.plan()

    def test_project_detection_from_child_and_no_scan_of_siblings(self):
        child = self.work / "logs/subdir"
        child.mkdir()
        self.assertEqual(update.project_at(child), self.work)
        self.assertIsNone(update.project_at(self.root))

    def test_custom_official_edit_refused_and_unlisted_user_file_kept(self):
        (self.tools / "README.md").write_text("my customization")
        (self.source / "README.md").write_text("new docs")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "Locally modified"):
            self.plan()

    def test_failed_write_rolls_back_every_root(self):
        before = [self.snapshot(root) for root in (self.tools, self.work, self.skill)]
        real = update.core.write_atomic
        failed = False
        def write(path, data, mode=0o644):
            nonlocal failed
            if path == self.work / ".prepare_lib/tools/grt_step2.py" and not failed:
                failed = True
                raise OSError("simulated disk failure")
            real(path, data, mode)
        with mock.patch.object(update.core, "write_atomic", side_effect=write):
            with self.assertRaisesRegex(OSError, "simulated"):
                update.apply(self.plan())
        self.assertTrue(failed)
        self.assertEqual([self.snapshot(root) for root in (self.tools, self.work, self.skill)], before)

    def test_changed_after_planning_refused(self):
        plan = self.plan()
        (self.tools / "tools/grt_step2.py").write_text("concurrent write")
        with self.assertRaisesRegex(ValueError, "after planning"):
            update.apply(plan)

    def test_active_process_guard_prevents_any_write(self):
        plan = self.plan()
        before = self.snapshot(self.tools)
        with mock.patch.object(update.core, "check_direct_processes", side_effect=ValueError("active process")):
            with self.assertRaisesRegex(ValueError, "active process"):
                update.apply(plan)
        self.assertEqual(self.snapshot(self.tools), before)

    def test_source_corruption_and_stale_mirror_refused(self):
        file = self.source / "README.md"
        file.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.plan()
        self.make_manifest(self.source, "b" * 40, "2026-10-24T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "predates"):
            self.plan()

    def test_symlink_target_refused(self):
        file = self.tools / "README.md"
        file.unlink()
        file.symlink_to(self.root / "outside")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.plan()

    def test_registered_skill_rebound_elsewhere_is_not_updated(self):
        elsewhere = self.root / "other tools"
        shutil.copytree(self.tools, elsewhere)
        paths.bind(self.skill, elsewhere)
        plan = self.plan()
        self.assertNotIn(str(self.skill), plan["roots"].values())

    def test_no_update_does_not_prompt_or_modify_installation(self):
        update.apply(self.plan())
        before = self.snapshot(self.tools)
        with mock.patch.object(downloads, "discover", return_value=self.release), mock.patch.object(downloads, "extract", return_value=self.source), mock.patch.object(update, "project_at", return_value=self.work), mock.patch("builtins.input", side_effect=AssertionError("must not prompt")) as confirm, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(update.run(self.tools), 0)
            confirm.assert_not_called()
            self.assertIn("Already up to date", output.getvalue())
        self.assertEqual(self.snapshot(self.tools), before)

    def test_noninteractive_update_applies_without_prompt_and_preserves_data(self):
        with mock.patch.object(downloads, "discover", return_value=self.release), mock.patch.object(downloads, "extract", return_value=self.source), mock.patch.object(update, "project_at", return_value=self.work), mock.patch("builtins.input", side_effect=AssertionError("must not prompt")), mock.patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(update.run(self.tools), 0)
        self.assertFalse(self.plan()["files"])
        self.assertEqual((self.work / "result.fasta").read_text(), "preserve\n")
        self.assertEqual(len(list((self.work / ".run_all").glob("server-update-*/journal.json"))), 1)

    def test_manifest_retired_files_removed_and_restored(self):
        (self.source / "README.md").unlink()
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        before = (self.tools / "README.md").read_bytes()
        backup = update.apply(self.plan())
        self.assertFalse((self.tools / "README.md").exists())
        update.rollback(backup)
        self.assertEqual((self.tools / "README.md").read_bytes(), before)


    def test_installer_default_and_custom_path_bind_without_environment_execution(self):
        import install_tools
        destination = self.root / "custom destination"
        def extract(release, output):
            candidate = output / "GPM_Server"
            shutil.copytree(self.source, candidate)
            return candidate
        with mock.patch.object(downloads, "extract", side_effect=extract), mock.patch.object(install_tools.subprocess, "run") as run:
            self.assertEqual(install_tools.install(self.skill, destination, self.release), destination)
            run.assert_not_called()
        self.assertEqual(paths.DEFAULT_TOOLS, "~/bin/GPM_Server")
        self.assertEqual(paths.resolve(self.skill), destination)
        self.assertIn(self.skill, paths.registered(destination))
        self.assertEqual((self.skill / "local/notes.md").read_text(), "本站经验\n")
        with self.assertRaisesRegex(ValueError, "already exists"):
            install_tools.install(self.skill, destination, self.release)

    def test_dependency_change_and_unrecognized_core_refused(self):
        for root in (self.tools, self.source):
            (root / "cgat-server.conda-spec.txt").write_text("old" if root == self.tools else "new")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "Dependency specification"):
            self.plan()
        (self.tools / "cgat-server.conda-spec.txt").write_text("new")
        (self.work / ".prepare_lib/tools/grt_core/unknown.py").write_text("unknown")
        with self.assertRaisesRegex(ValueError, "Unrecognized old core"):
            self.plan()

    def test_corrupt_backup_and_post_update_edit_refuse_rollback(self):
        backup = update.apply(self.plan())
        target = self.tools / "tools/grt_step2.py"
        target.write_text("user edit after update")
        with self.assertRaisesRegex(ValueError, "changed after update"):
            update.rollback(backup)
        self.assertEqual(target.read_text(), "user edit after update")

    def test_skill_only_update_does_not_force_runtime_changes(self):
        update.apply(self.plan())
        # Simulate a registered older skill from the previous release.
        (self.skill / "SKILL.md").write_text("skill v3\n")
        old = json.loads((self.skill / "official-source.json").read_text())
        old["files"]["SKILL.md"]["sha256"] = update.core.digest(b"skill v3\n")
        (self.skill / "official-source.json").write_text(json.dumps(old))
        plan = self.plan()
        self.assertTrue(plan["files"])
        self.assertTrue(all(item["kind"].startswith("skill-") for item in plan["files"]))
        update.apply(plan)
        self.assertFalse(self.plan()["files"])

    def test_nested_legacy_project_updates_without_touching_outputs(self):
        nested = self.tools / "gpm_server"
        shutil.move(self.work, nested)
        self.work = nested
        before = (self.work / "result.fasta").read_bytes()
        backup = update.apply(self.plan())
        self.assertEqual((self.work / "result.fasta").read_bytes(), before)
        self.assertFalse(self.plan()["files"])
        update.rollback(backup)
        self.assertEqual((self.work / "result.fasta").read_bytes(), before)

    def test_nested_project_cannot_overlap_managed_tools(self):
        nested = self.tools / "tools/project"
        shutil.move(self.work, nested)
        self.work = nested
        with self.assertRaisesRegex(ValueError, "overlaps managed"):
            self.plan()

    def test_unchanged_file_and_binding_changes_invalidate_waiting_plan(self):
        for file in (self.tools / "run.sh", self.skill / "server-tools.path", self.tools / paths.REGISTRY):
            before = file.read_bytes()
            plan = self.plan()
            file.write_bytes(before + b"changed\n")
            with self.subTest(file=file), self.assertRaisesRegex(ValueError, "after planning"):
                update.apply(plan)
            file.write_bytes(before)

    def test_runtime_root_symlink_after_planning_refused(self):
        plan = self.plan()
        runtime = self.work / ".prepare_lib"
        moved = self.root / "outside"
        runtime.rename(moved)
        runtime.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            update.apply(plan)

    def test_binding_captures_known_skill_baseline_but_not_customized_files(self):
        record = self.skill / "official-source.json"
        record.unlink()
        paths.bind(self.skill, self.tools)
        self.assertIn("SKILL.md", json.loads(record.read_text())["files"])
        record.unlink()
        (self.skill / "SKILL.md").write_text("custom skill")
        paths.bind(self.skill, self.tools)
        self.assertFalse(record.exists())

    def test_real_closed_stdin_updates_all_roots(self):
        harness = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0,{str(update.ROOT / 'tools')!r}); "
            "import update_server as u; "
            f"u.downloads.discover=lambda: {self.release!r}; "
            f"u.downloads.extract=lambda release,tmp: Path({str(self.source)!r}); "
            f"sys.exit(u.run(Path({str(self.tools)!r})))"
        )
        child = subprocess.run([sys.executable, "-B", "-c", harness], cwd=self.work / "logs",
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        self.assertNotIn("[y/N]", child.stdout)
        self.assertIn("Updated successfully", child.stdout)
        self.assertFalse(self.plan()["files"])
        self.assertEqual((self.work / "result.fasta").read_text(), "preserve\n")

    def test_real_startup_updates_and_executes_new_runner_without_pid_exemptions(self):
        (self.tools / "tools/server_run.py").write_text("raise RuntimeError('OLD RUNNER MUST NOT EXECUTE')\n")
        info = json.loads((self.tools / "SOURCE.json").read_text())
        info["files"]["tools/server_run.py"]["sha256"] = update.core.digest((self.tools / "tools/server_run.py").read_bytes())
        (self.tools / "SOURCE.json").write_text(json.dumps(info))
        (self.source / "tools/server_run.py").write_text("import sys; print('FRESH RUNNER', repr(sys.argv[1:]))\n")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        harness = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0,{str(update.ROOT / 'tools')!r}); "
            "import update_server as u; "
            f"u.downloads.discover=lambda: {self.release!r}; "
            f"u.downloads.extract=lambda release,tmp: Path({str(self.source)!r}); "
            f"u.launch(Path({str(self.tools)!r}), '--launch-run', ['-o', {str(self.work)!r}])"
        )
        child = subprocess.run([sys.executable, "-B", "-c", harness], cwd=self.work / "logs",
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        self.assertIn("Updated successfully", child.stdout)
        self.assertIn("FRESH RUNNER", child.stdout)
        self.assertNotIn("OLD RUNNER", child.stdout + child.stderr)
        self.assertFalse(self.plan()["files"])

    def test_nested_alignment_runtime_and_companion_update_and_rollback(self):
        names = ("tools/long_cigar_recovery/server_alignment.py", "tools/long_cigar_recovery/branch-runtime.json",
                 "tools/long_cigar_recovery/native/linux-x86_64/native-chain-state", "tools/long_cigar_recovery/native/linux-x86_64/MINIMAP2_LICENSE.txt")
        for name in names:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"new runtime")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        backup = update.apply(self.plan())
        for root in (self.tools, self.work / ".prepare_lib"):
            for name in names:
                self.assertEqual((root / name).read_bytes(), b"new runtime")
        update.rollback(backup)
        self.assertTrue(all(not (root / name).exists() for root in (self.tools, self.work / ".prepare_lib") for name in names))

    def test_only_known_generated_launcher_is_upgraded_and_rollback_restores_it(self):
        name = "lib/run_all_launcher.sh"
        (self.source / name).write_bytes((update.ROOT / name).read_bytes())
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        launcher = self.work / "run_all.sh"
        custom = launcher.read_bytes()
        plan = self.plan()
        self.assertFalse(any(p["kind"] == "workspace" for p in plan["files"]))
        self.assertEqual(launcher.read_bytes(), custom)
        launcher.write_bytes(update.LEGACY_RUN_ALL)
        backup = update.apply(self.plan())
        self.assertEqual(launcher.read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
        update.rollback(backup)
        self.assertEqual(launcher.read_bytes(), update.LEGACY_RUN_ALL)

    def test_startup_failure_before_mutation_keeps_installed_code(self):
        before = [self.snapshot(root) for root in (self.tools, self.work)]
        with mock.patch.object(downloads, "discover", side_effect=OSError("offline")), mock.patch.object(update, "apply") as apply:
            self.assertEqual(update.run(self.tools, startup=True, workspace=self.work), 0)
            apply.assert_not_called()
        self.assertEqual([self.snapshot(root) for root in (self.tools, self.work)], before)

    def test_startup_repairs_missing_nested_runtime_left_by_older_updater(self):
        name = "tools/long_cigar_recovery/server_alignment.py"
        path = self.source / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"new nested runtime")
        self.make_manifest(self.source, "b" * 40, "2026-10-26T00:00:00+00:00")
        # Simulate old runtime_file selection: newest SOURCE, no nested module.
        for root in (self.tools, self.work / ".prepare_lib"):
            (root / "SOURCE.json").write_bytes((self.source / "SOURCE.json").read_bytes())
            for rel in ("lib/incremental_common.sh", "tools/grt_step2.py"):
                (root / rel).write_bytes((self.source / rel).read_bytes())
        (self.tools / "skills/gpm-server/SKILL.md").write_bytes((self.source / "skills/gpm-server/SKILL.md").read_bytes())
        with mock.patch.object(downloads, "discover", return_value=self.release), mock.patch.object(downloads, "extract", return_value=self.source), mock.patch.object(update.os, "execv") as exe:
            update.launch(self.tools, "--launch-run", ["-o", str(self.work)])
            exe.assert_called_once()
        self.assertEqual((self.work / ".prepare_lib" / name).read_bytes(), b"new nested runtime")

    def test_offline_startup_never_executes_corrupted_installed_code(self):
        (self.tools / "tools/server_run.py").write_bytes(b"damaged")
        with mock.patch.object(downloads, "discover", side_effect=OSError("offline")), mock.patch.object(update.os, "execv") as exe:
            with self.assertRaisesRegex(ValueError, "integrity"):
                update.launch(self.tools, "--launch-run", ["-o", str(self.work)])
            exe.assert_not_called()

    def test_startup_never_swallows_apply_or_rollback_failure(self):
        with mock.patch.object(downloads, "discover", return_value=self.release), mock.patch.object(downloads, "extract", return_value=self.source), mock.patch.object(update, "apply", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(OSError, "write failed"):
                update.run(self.tools, startup=True, workspace=self.work)

    def test_launch_updates_then_verifies_then_execs_fresh_code(self):
        calls = []
        with mock.patch.object(update, "verify_installed", side_effect=lambda *a: calls.append("verify")), mock.patch.object(update, "run", side_effect=lambda *a, **kw: calls.append(("update", kw))), mock.patch.object(update.os, "execv", side_effect=lambda *a: calls.append(("exec", a))):
            update.launch(self.tools, "--launch-run", ["-o", str(self.work)])
        self.assertEqual(calls[0], ("update", {"startup": True, "workspace": self.work}))
        self.assertEqual(calls[1], "verify")
        self.assertEqual(calls[2][1][1][2:], [str(self.tools / "tools/server_run.py"), "-o", str(self.work)])

    def test_workspace_launch_preserves_runner_arguments_and_rejects_foreign_binding(self):
        with mock.patch.object(update, "verify_installed"), mock.patch.object(update, "run") as run, mock.patch.object(update.os, "execv") as exe:
            update.launch(self.tools, "--launch-workspace", [str(self.work), "--log-style", "detailed"])
            self.assertEqual(exe.call_args.args[1][2:], [str(self.work / ".prepare_lib/tools/run_all_runner.py"), "--server-dir", str(self.work), "--log-style", "detailed"])
            run.assert_called_once_with(self.tools, startup=True, workspace=self.work)
            (self.work / ".prepare_lib/server-tools.path").write_text(str(self.source)+"\n")
            with self.assertRaisesRegex(ValueError, "different Server"):
                update.launch(self.tools, "--launch-workspace", [str(self.work)])

    def test_help_and_development_launch_do_not_contact_network(self):
        for mode, argv in (("--launch-run", ["--help"]), ("--launch-workspace", [str(self.work), "--help"])):
            with mock.patch.object(update, "run") as run, mock.patch.object(update.os, "execv"):
                update.launch(self.tools, mode, argv)
                run.assert_not_called()
        (self.tools / "SOURCE.json").write_text('{"official_release": false}')
        with mock.patch.object(update, "run") as run, mock.patch.object(update.os, "execv"):
            update.launch(self.tools, "--launch-run", ["-o", str(self.work)])
            run.assert_not_called()

    def test_verify_installed_detects_modified_tools_and_runtime(self):
        update.verify_installed(self.tools, self.work)
        runtime = self.work / ".prepare_lib/tools/grt_step2.py"
        before = runtime.read_bytes()
        runtime.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "runtime integrity"):
            update.verify_installed(self.tools, self.work)
        runtime.write_bytes(before)
        (self.tools / "tools/server_run.py").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source integrity"):
            update.verify_installed(self.tools, self.work)


class InteractionTests(unittest.TestCase):
    def test_public_update_rejects_flags_before_network(self):
        for script in (update.ROOT / "update.sh", update.ROOT / "skills/gpm-server/scripts/update.sh"):
            for flag in ("--check", "--yes"):
                result = subprocess.run(["bash", str(script), flag], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("no arguments", result.stderr)


if __name__ == "__main__":
    unittest.main()
