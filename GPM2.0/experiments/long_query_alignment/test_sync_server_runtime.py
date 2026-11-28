"""Generated production tree stays byte-bound to the tested canonical runtime."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import server_alignment as sa
import sync_server_runtime as sync
import windowed_alignment as wa


class ServerRuntimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = Path(self.tmp.name) / "server"
        official = Path(__file__).resolve().parents[2] / "server"
        for name in ("prepare.sh", "tools/server_run.py", "tools/run_outer_checkpoints.py"):
            target = self.server / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(official / name, target)
        self.bundle = official / "tools/long_cigar_recovery/native/linux-x86_64"
        self.runtime = self.server / "tools/long_cigar_recovery"

    def test_checked_in_production_copy_matches_canonical_runtime(self):
        official = Path(__file__).resolve().parents[2] / "server"
        self.assertEqual(sync.synchronize(official)["changed"], [])

    def test_both_platforms_select_the_companion_and_receipt_without_cross_execution(self):
        sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        for platform in ("linux-x86_64", "linux-aarch64"):
            with self.subTest(platform=platform), patch.object(sa.nst.build, "host_platform", return_value=platform):
                binding = sa.validate_runtime(self.runtime)
                actual = sa.publication_bundle(self.runtime, binding)
                self.assertEqual(platform, binding["native_companion_platform"])
                self.assertEqual(actual["sha256"], binding["native_companion_sha256"])
                self.assertEqual(actual["manifest_sha256"], binding["native_companion_binding"]["manifest_sha256"])
                # Even a well-formed but substituted build receipt must not publish.
                binding["native_companion_binding"]["manifest_sha256"] = "0" * 64
                with self.assertRaisesRegex(wa.ExperimentError, "package binding"):
                    sa.publication_bundle(self.runtime, binding)
        path = self.runtime / sa.MANIFEST
        data = json.loads(path.read_bytes())
        del data["native_companions"]["linux-aarch64"]
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wa.ExperimentError, "platform bindings"):
            sa.validate_runtime(self.runtime)

    def test_write_then_read_only_verification_and_stale_code_refusal(self):
        sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        self.assertEqual(sync.synchronize(self.server)["changed"], [])
        file = self.runtime / "windowed_alignment.py"
        file.write_bytes(file.read_bytes() + b"\n# drift\n")
        modified = file.read_bytes()
        with self.assertRaisesRegex(wa.ExperimentError, "stale"):
            sync.synchronize(self.server)
        self.assertEqual(file.read_bytes(), modified)
        sync.synchronize(self.server, write=True)
        self.assertEqual(sa.runtime_files(self.runtime), sa.runtime_files(Path(sa.__file__).parent))

    def test_current_server_tools_are_bound_for_safe_existing_workspace_handoff(self):
        sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        file = self.server / "tools/new_tool.py"
        file.write_text("# new production tool\n")
        with self.assertRaisesRegex(wa.ExperimentError, "resume-base.json"):
            sync.synchronize(self.server)
        sync.synchronize(self.server, write=True)
        self.assertEqual(sync.synchronize(self.server)["changed"], [])

    def test_unknown_file_and_symlink_refuse_without_deletion(self):
        sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        extra = self.runtime / "customer.txt"
        extra.write_text("must keep")
        with self.assertRaisesRegex(wa.ExperimentError, "unknown"):
            sync.synchronize(self.server, write=True)
        self.assertEqual(extra.read_text(), "must keep")
        extra.unlink()
        extra.symlink_to(self.server / "prepare.sh")
        with self.assertRaisesRegex(wa.ExperimentError, "symlink"):
            sync.synchronize(self.server, write=True)
        self.assertTrue(extra.is_symlink())

    def test_missing_hook_or_host_only_binary_cannot_be_marked_synchronized(self):
        with patch.object(sync.nst, "validate_bundle", return_value={"runtime_abi": {"legacy_2_17_checked": False}}):
            with self.assertRaisesRegex(wa.ExperimentError, "portable companion"):
                sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        self.assertFalse(self.runtime.exists())
        (self.server / "prepare.sh").write_text("# unreviewed generator\n")
        with self.assertRaisesRegex(wa.ExperimentError, "hook"):
            sync.synchronize(self.server, native_bundle=self.bundle, write=True)
        self.assertFalse(self.runtime.exists())


if __name__ == "__main__":
    unittest.main()
