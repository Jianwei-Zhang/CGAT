"""Offline updater publishing contract: no keys, network or real installers."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("feed", HERE / "app-update-feed.py")
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        for platform in feed.TARGETS.values():
            extension = "setup.exe" if platform.startswith("win") else "app.tar.gz"
            path = self.assets / f"GPM_2.0.12_20261023_{platform}_{extension}"
            path.write_bytes(b"fixture artifact " + platform.encode())
            # Structural fixture only: never a valid production signature.
            Path(str(path) + ".sig").write_text(base64.b64encode(b"trusted comment: timestamp:1\tversion:2.0.12\n").decode())
        self.manifest = feed.build("2.0.12", self.assets, self.assets)
        self.public = self.root / "public"

    def test_macos_build_includes_both_manual_and_updater_targets(self):
        import shlex
        workflow = (feed.ROOT / ".github/workflows/release-installers.yml").read_text()
        macos = workflow.split("  build-macos:\n", 1)[1].split("  update-feed:\n", 1)[0]
        command = next(line.strip().removeprefix("run: ") for line in macos.splitlines()
                       if "run: tauri build " in line)
        args = shlex.split(command)
        bundles = args[args.index("--bundles") + 1].split(",")
        self.assertEqual(set(bundles), {"app", "dmg"})

    def test_dispatched_builds_checkout_the_immutable_release_tag(self):
        workflow = (feed.ROOT / ".github/workflows/release-installers.yml").read_text()
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 4)
        self.assertEqual(workflow.count("ref: ${{ inputs.tag || github.ref }}"), 4)

    def test_installer_builds_supply_public_key_to_the_tauri_bundler(self):
        workflow = (feed.ROOT / ".github/workflows/release-installers.yml").read_text()
        self.assertEqual(workflow.count("- name: Prepare updater signing config"), 2)
        self.assertEqual(workflow.count("pubkey: process.env.GPM_UPDATER_PUBLIC_KEY"), 2)
        self.assertEqual(workflow.count("fs.writeFileSync('tauri.updater.build.conf.json'"), 2)
        self.assertIn("--config tauri.updater.build.conf.json --bundles nsis", workflow)
        self.assertIn("--config tauri.updater.build.conf.json --bundles app,dmg", workflow)
        for block in workflow.split("- name: Prepare updater signing config")[1:]:
            config_step = block.split("\n      - name: ", 1)[0]
            self.assertNotIn("PRIVATE_KEY", config_step)
            self.assertIn("if (!process.env.GPM_UPDATER_PUBLIC_KEY)", config_step)

    def test_internal_update_assets_are_removed_only_after_docs_bundle_is_ready(self):
        spec = importlib.util.spec_from_file_location(
            "cleanup_assets", HERE / "cleanup-updater-assets.py")
        cleanup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cleanup)
        names = {path.name for path in self.assets.iterdir()}
        changed = copy.deepcopy(self.manifest)
        raw = b"ED" + b"\0" * 72

        def signature(version):
            return base64.b64encode(
                b"untrusted comment: fixture\n" + base64.b64encode(raw) +
                b"\ntrusted comment: timestamp:1\tversion:" + version.encode() +
                b"\n" + base64.b64encode(b"x" * 64)
            ).decode()

        for package in changed["platforms"].values():
            package["signature"] = signature("2.0.12")
        signatures = cleanup.embedded_signatures(changed, names, "v2.0.12")
        self.assertEqual(signatures, {name for name in names if name.endswith(".sig")})
        internal = cleanup.internal_asset_names(changed, names, "v2.0.12")
        self.assertEqual(len(internal), 9)
        self.assertTrue(any(name.endswith("_win-x86_setup.exe") for name in names - internal))
        self.assertTrue(any(name.endswith("_win-arm64_setup.exe") for name in names - internal))
        bad = next(iter(changed["platforms"].values()))
        bad["signature"] = signature("2.0.11")
        with self.assertRaises((AssertionError, ValueError)):
            cleanup.embedded_signatures(changed, names, "v2.0.12")
        workflow = (feed.ROOT / ".github/workflows/release-installers.yml").read_text()
        upload = workflow.index("gh release upload \"$TAG_NAME\" update-feed/GPM_*_notes_*.txt update-feed/latest.json")
        artifact = workflow.index("name: Retain updater files for docs staging", upload)
        remove = workflow.index("cleanup-updater-assets.py", artifact)
        self.assertLess(upload, artifact)
        self.assertLess(artifact, remove)
        self.assertIn("path: update-bundle/*", workflow)

    def test_build_requires_all_four_signatures_to_verify_before_writing_feed(self):
        verified = []
        def verifier(path, signature):
            verified.append(path.name)
            raise ValueError("signature mismatch")
        output = self.root / "rejected-feed"
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            feed.build("2.0.12", self.assets, output, verifier=verifier)
        self.assertEqual(len(verified), 1)
        self.assertFalse((output / "latest.json").exists())

    def test_signature_verifier_uses_public_key_and_propagates_rejection(self):
        path = next(self.assets.glob("*.exe"))
        key = base64.b64encode(b"public fixture").decode()
        signature = base64.b64encode(b"signature fixture").decode()
        def verify_command(command, **options):
            self.assertEqual(command[:3], ["minisign", "-Vm", str(path)])
            self.assertEqual(Path(command[4]).read_bytes(), b"public fixture")
            self.assertEqual(Path(command[6]).read_bytes(), b"signature fixture")
            self.assertTrue(options["check"])
            raise subprocess.CalledProcessError(1, command)
        with patch.object(feed.subprocess, "run", side_effect=verify_command):
            with self.assertRaises(subprocess.CalledProcessError):
                feed.verify_signature(path, signature, key)
        with self.assertRaises(ValueError): feed.verify_signature(path, signature, "")

    def test_all_four_architectures_and_matching_urls(self):
        self.assertEqual(set(self.manifest["platforms"]), set(feed.TARGETS))
        for info in self.manifest["platforms"].values():
            self.assertEqual(info["url"].split("/")[-1], info["mirror_url"].split("/")[-1])
            self.assertEqual(len(info["sha256"]), 64)

    def test_notes_are_localized_and_app_first(self):
        en = (self.assets / "GPM_2.0.12_notes_en.txt").read_text(encoding="utf-8")
        zh = (self.assets / "GPM_2.0.12_notes_zh.txt").read_text(encoding="utf-8")
        for text in (en, zh):
            self.assertTrue(text.startswith("App\n"))
            self.assertGreater(text.index("Server\n"), text.index("App\n"))
            self.assertNotIn("### Downloads", text)
            self.assertNotIn("### macOS", text)
        self.assertNotEqual(en, zh)

    def test_mirror_promotes_exact_feed_after_all_files(self):
        feed.stage(self.assets, self.public)
        self.assertEqual((self.public / "downloads/updates/latest.json").read_bytes(), (self.assets / "latest.json").read_bytes())
        for info in [*self.manifest["platforms"].values(), *self.manifest["release_notes"].values()]:
            self.assertTrue((self.public / "downloads/v2.0.12" / info["url"].split("/")[-1]).is_file())

    def test_bad_asset_leaves_previous_feed_untouched(self):
        feed.stage(self.assets, self.public)
        previous = (self.public / "downloads/updates/latest.json").read_bytes()
        name = next(iter(self.manifest["platforms"].values()))["url"].split("/")[-1]
        (self.assets / name).write_bytes(b"corrupt")
        with self.assertRaises(ValueError): feed.stage(self.assets, self.public)
        self.assertEqual(previous, (self.public / "downloads/updates/latest.json").read_bytes())

    def test_missing_asset_never_creates_latest(self):
        (self.assets / "GPM_2.0.12_notes_zh.txt").unlink()
        with self.assertRaises(FileNotFoundError): feed.stage(self.assets, self.public)
        self.assertFalse((self.public / "downloads/updates/latest.json").exists())

    def test_unsigned_or_unbound_version_is_rejected(self):
        path = next(self.assets.glob("*.sig"))
        path.write_text(base64.b64encode(b"trusted comment: timestamp:1\tversion:9.0.0").decode())
        with self.assertRaisesRegex(ValueError, "signed version"):
            feed.build("2.0.12", self.assets, self.assets)

    def test_filename_containing_version_does_not_bind_signed_version(self):
        signature = next(self.assets.glob("*.sig"))
        signature.write_text(base64.b64encode(b"trusted comment: timestamp:1\tfile:app-version:2.0.12\n").decode())
        with self.assertRaisesRegex(ValueError, "signed version"):
            feed.build("2.0.12", self.assets, self.assets)

    def test_duplicate_architecture_and_prerelease_rejected(self):
        path = next(self.assets.glob("*win-x86_setup.exe"))
        (self.assets / path.name.replace("20261023", "20261024")).write_bytes(path.read_bytes())
        with self.assertRaises(ValueError): feed.build("2.0.12", self.assets, self.assets)
        with self.assertRaises(ValueError): feed.check_version("2.0.13-beta")

    def test_wrong_mirror_url_and_path_traversal_rejected(self):
        for url in ("https://evil.example/payload", "https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/../evil"):
            manifest = json.loads(json.dumps(self.manifest))
            manifest["release_notes"]["en"]["mirror_url"] = url
            (self.assets / "latest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): feed.stage(self.assets, self.public)

    def test_docs_feed_cannot_be_downgraded(self):
        latest = self.public / "downloads/updates/latest.json"
        latest.parent.mkdir(parents=True)
        latest.write_text('{"version":"2.0.13"}')
        with self.assertRaisesRegex(ValueError, "downgrade"): feed.stage(self.assets, self.public)


if __name__ == "__main__":
    unittest.main()
