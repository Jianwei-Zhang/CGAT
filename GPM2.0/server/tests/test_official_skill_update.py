"""Offline behavioral contracts for official update identities and safe staging."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills/gpm-server"
spec = importlib.util.spec_from_file_location("official_update", SKILL / "scripts/official_update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


def make_tar(items):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data, kind in items:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data) if kind == tarfile.REGTYPE else 0
            member.linkname = "../../outside" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
            archive.addfile(member, io.BytesIO(data) if member.isfile() else None)
    return gzip.compress(stream.getvalue(), mtime=0)


class OfficialUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.installed, self.output = self.root / "current skill", self.root / "new update"
        shutil.copytree(SKILL, self.installed, ignore=shutil.ignore_patterns("__pycache__", "local"))
        (self.installed / "server-tools.path").write_text("/old/missing/Server\n")
        local = self.installed / "local"
        local.mkdir()
        (local / "notes.md").write_text("已验证的本站经验；不要作为通用参数。\n")
        (local / "preferences.md").write_text("Legacy user restriction: do not upload notes\n")
        self.commit, self.tree = "a" * 40, "b" * 40
        self.blobs = {
            ".gitignore": b"/local/\n",
            "SKILL.md": b'---\nname: gpm-server\nmetadata:\n  skill-version: "3"\n---\n',
            "server-tools.path": b"../..\n",
            "agents/openai.yaml": b"interface: {}\n",
            "references/execution.md": b"Official execution reference\n",
            "scripts/server_tools_path.sh": b"exit 99 # downloaded code must not run\n",
            "scripts/stage_skill_update.py": b"raise RuntimeError('do not execute downloaded code')\n",
        }
        self.files = [{"path": update.SKILL_PATH + "/" + name, "type": "blob", "mode": "100644",
                       "size": len(data), "sha": update.blob_sha(data)}
                      for name, data in sorted(self.blobs.items())]
        self.archive = make_tar([
            ("GPM_Server/", b"", tarfile.DIRTYPE),
            ("GPM_Server/tools/", b"", tarfile.DIRTYPE),
            ("GPM_Server/tools/grt_core/", b"", tarfile.DIRTYPE),
            *[("GPM_Server/" + name, b"# never executed\n", tarfile.REGTYPE)
              for name in ("run.sh", "prepare.sh", "install.sh", "tools/server_run.py")],
        ])
        self.release = {"tag_name": "v2.0.10", "draft": False, "prerelease": False, "assets": [{
            "name": "GPM_Server_2.0.10_source.tar.gz", "id": 123, "size": len(self.archive),
            "digest": "sha256:" + hashlib.sha256(self.archive).hexdigest(),
            "browser_download_url": "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.10/GPM_Server_2.0.10_source.tar.gz"}]}
        self.api_calls, self.downloads = [], []
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(update, "api_json", side_effect=self.api).start()
        mock.patch.object(update, "read_url", side_effect=self.download).start()

    def api(self, endpoint):
        self.api_calls.append(endpoint)
        if endpoint == "releases/latest" or endpoint == "releases/tags/v2.0.10":
            return copy.deepcopy(self.release)
        if endpoint.startswith("commits?"):
            return [{"sha": self.commit}]
        if endpoint == "git/commits/" + self.commit:
            return {"sha": self.commit, "tree": {"sha": self.tree}}
        if endpoint == "git/trees/" + self.tree + "?recursive=1":
            return {"sha": self.tree, "truncated": False, "tree": copy.deepcopy(self.files)}
        raise AssertionError("Unexpected/non-pinned API call: " + endpoint)

    def download(self, url, limit=update.MAX_METADATA):
        self.downloads.append(url)
        if url == self.release["assets"][0]["browser_download_url"]:
            return self.archive
        prefix = f"https://raw.githubusercontent.com/{update.REPOSITORY}/{self.commit}/{update.SKILL_PATH}/"
        self.assertTrue(url.startswith(prefix), url)
        return self.blobs[url[len(prefix):]]

    def plan(self):
        return update.check(self.installed)

    def snapshot(self):
        return {p.relative_to(self.installed): p.read_bytes()
                for p in self.installed.rglob("*") if p.is_file()}

    def test_cli_help_does_not_write_import_bytecode_in_installed_skill(self):
        original = self.snapshot()
        result = subprocess.run([sys.executable, str(self.installed / "scripts/official_update.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), original)
        self.assertEqual(list(self.installed.rglob("__pycache__")), [])

    def test_check_is_read_only_and_separates_stable_tools_from_repository_skill(self):
        original = self.snapshot()
        plan = self.plan()
        self.assertEqual(plan["server"]["tag"], "v2.0.10")
        self.assertEqual(plan["skill"]["channel"], "official-repository")
        self.assertEqual(plan["skill"]["version"], "3")
        self.assertEqual(plan["skill"]["commit"], self.commit)
        self.assertFalse(plan["installed"]["skill_matches_official_files"])
        self.assertIn("ask-first", plan["installed"]["recorded_server_tools"])
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.output.exists())
        self.assertEqual(set(self.downloads), {
            f"https://raw.githubusercontent.com/{update.REPOSITORY}/{self.commit}/{update.SKILL_PATH}/SKILL.md"})

    def test_stage_preserves_experience_and_binds_new_tools_without_activating(self):
        original = self.snapshot()
        plan = self.plan()
        report = update.stage(plan, self.installed, self.output)
        self.assertEqual(report["state"], "staged-not-activated")
        candidate = self.output / "gpm-server"
        for name in ("notes.md", "preferences.md"):
            self.assertEqual((candidate / "local" / name).read_bytes(),
                             (self.installed / "local" / name).read_bytes())
        self.assertEqual((candidate / "server-tools.path").read_text(),
                         str(self.output / "GPM_Server") + "\n")
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(report["environment_or_agent_config_changed"])
        self.assertEqual(json.loads((self.output / "update-report.json").read_text())["state"],
                         "staged-not-activated")
        self.assertTrue((candidate / "official-source.json").is_file())
        self.assertNotIn("releases/latest", self.api_calls[-3:])

    def test_missing_local_state_does_not_create_modes_or_notes(self):
        shutil.rmtree(self.installed / "local")
        update.stage(self.plan(), self.installed, self.output)
        self.assertFalse((self.output / "gpm-server/local").exists())

    def test_same_version_replaced_asset_requires_fresh_plan(self):
        plan = self.plan()
        self.release["assets"][0]["id"] += 1
        with self.assertRaisesRegex(ValueError, "changed since check"):
            update.stage(plan, self.installed, self.output)
        self.assertFalse(self.output.exists())

    def test_modified_skill_plan_is_refused(self):
        plan = self.plan()
        plan["skill"]["files"][0]["sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "plan was modified"):
            update.stage(plan, self.installed, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_digest_foreign_origin_drafts_and_missing_assets_are_refused(self):
        for field, value in (("digest", None), ("browser_download_url", "https://example.com/tools.tar.gz"),
                             ("size", update.MAX_ARCHIVE + 1)):
            release = copy.deepcopy(self.release)
            release["assets"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                update.release_info(release)
        for changed in ({"draft": True}, {"prerelease": True}, {"assets": []}):
            release = dict(self.release, **changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                update.release_info(release)

    def test_invalid_pins_and_foreign_plan_are_refused_before_writes(self):
        plan = self.plan()
        for field, value in (("repository", "other/repo"), ("website", "https://example.com")):
            changed = copy.deepcopy(plan)
            changed[field] = value
            with self.assertRaises(ValueError):
                update.stage(changed, self.installed, self.output)
        with self.assertRaises(ValueError):
            update.skill_info("master")
        self.assertFalse(self.output.exists())

    def test_skill_symlink_submodule_or_local_state_is_refused(self):
        for changed in ({"mode": "120000"}, {"type": "commit", "mode": "160000"},
                        {"path": update.SKILL_PATH + "/local/notes.md"}):
            original = copy.deepcopy(self.files)
            self.files[0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.plan()
            self.files = original

    def test_incomplete_tree_or_missing_entrypoint_is_refused(self):
        with mock.patch.object(update, "api_json", return_value={"sha": self.commit, "tree": {"sha": self.tree},
                                                               "truncated": True}):
            with self.assertRaises(ValueError):
                update.skill_info(self.commit)
        self.files = [f for f in self.files if not f["path"].endswith("/SKILL.md")]
        with self.assertRaises(ValueError):
            self.plan()

    def test_archive_hash_failure_cleans_only_new_output(self):
        plan = self.plan()
        original = self.snapshot()
        self.archive = b"bad download"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            update.stage(plan, self.installed, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.snapshot(), original)

    def test_skill_blob_tampering_cleans_only_new_output(self):
        plan = self.plan()
        original = self.snapshot()
        self.blobs["references/execution.md"] = b"tampered"
        with self.assertRaisesRegex(ValueError, "blob identity"):
            update.stage(plan, self.installed, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.snapshot(), original)

    def test_incomplete_server_is_not_bound_and_old_state_is_retained(self):
        self.archive = make_tar([("GPM_Server/run.sh", b"# incomplete", tarfile.REGTYPE)])
        self.release["assets"][0].update(size=len(self.archive),
            digest="sha256:" + hashlib.sha256(self.archive).hexdigest())
        original = self.snapshot()
        with self.assertRaises(FileNotFoundError):
            update.stage(self.plan(), self.installed, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.snapshot(), original)

    def test_existing_overlapping_or_symlinked_output_is_refused(self):
        plan = self.plan()
        self.output.mkdir()
        (self.output / "keep").write_text("unchanged")
        for out in (self.output, self.installed, self.installed / "child", self.root):
            with self.subTest(out=out), self.assertRaises(ValueError):
                update.stage(plan, self.installed, out)
        self.assertEqual((self.output / "keep").read_text(), "unchanged")
        link = self.root / "link"
        link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises(ValueError):
            update.stage(plan, self.installed, link)

    def test_unsafe_archives_reject_paths_links_devices_duplicates_and_other_roots(self):
        unsafe = [("GPM_Server/../../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                  ("other/file", tarfile.REGTYPE), ("GPM_Server/link", tarfile.SYMTYPE),
                  ("GPM_Server/hardlink", tarfile.LNKTYPE), ("GPM_Server/fifo", tarfile.FIFOTYPE),
                  ("GPM_Server/a\\b", tarfile.REGTYPE)]
        for name, kind in unsafe:
            with self.subTest(name=name), self.assertRaises(ValueError):
                update.unpack_server(make_tar([(name, b"data", kind)]), self.root)
        with self.assertRaises(ValueError):
            update.unpack_server(make_tar([("GPM_Server/repeated", b"a", tarfile.REGTYPE)] * 2), self.root)
        self.assertFalse((self.root / "escape").exists())

    def test_oversized_unpacked_content_and_member_count_are_bounded(self):
        with mock.patch.object(update, "MAX_UNPACKED", 8):
            with self.assertRaises(ValueError):
                update.unpack_server(self.archive, self.root)
        with mock.patch.object(update, "MAX_FILES", 1):
            with self.assertRaises(ValueError):
                update.unpack_server(self.archive, self.root)

    def test_https_origin_checks_include_redirects_and_reject_credentials(self):
        for url in ("http://github.com/file", "https://example.com/file", "file:///tmp/file",
                    "https://user:pass@github.com/file", "https://github.com:8443/file"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                update.check_url(url)
        for host in update.HOSTS:
            update.check_url("https://" + host + "/file")
        redirect = update.OfficialRedirect()
        with self.assertRaises(ValueError):
            redirect.redirect_request(None, None, 302, "", {}, "http://example.com")

    def test_network_failure_does_not_modify_installation_or_create_output(self):
        original = self.snapshot()
        with mock.patch.object(update, "api_json", side_effect=OSError("network unavailable")):
            with self.assertRaises(OSError):
                self.plan()
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
