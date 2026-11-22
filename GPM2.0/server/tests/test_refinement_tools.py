"""Small installer/recipe checks, without solving or changing a real environment."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import subprocess
import tempfile
import unittest
from unittest import mock

from server.tools import refinement_tools as tools
from server.tools.refinement_recipes import ToolError as RecipeError, select_tools, select_reads, make_invocation, materialize_native_driver


class LockedToolTests(unittest.TestCase):
    def test_conda_content_and_archive_build_are_both_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "conda-meta").mkdir()
            binary = root / "bin/bwa"
            binary.write_bytes(b"fixture bwa")
            pin = {"name": "bwa", "version": "0.7.19", "build": "fixture_1", "sha256": "a" * 64}
            record = {**pin, "paths_data": {"paths": [{"_path": "bin/bwa", "path_type": "hardlink", "sha256_in_prefix": tools.digest(binary)}]}}
            metadata = root / "conda-meta/bwa-0.7.19-fixture_1.json"
            metadata.write_text(json.dumps(record))
            definition = {"packages": {"linux-64": pin}}
            receipt = tools.package_receipt(root, "bwa", definition, "linux-64")
            self.assertEqual(receipt["archive_sha256"], "a" * 64)
            binary.write_bytes(b"different bwa")
            with self.assertRaisesRegex(tools.ToolError, "content changed"):
                tools.package_receipt(root, "bwa", definition, "linux-64")
            record["sha256"] = "b" * 64
            metadata.write_text(json.dumps(record))
            with self.assertRaisesRegex(tools.ToolError, "build/archive"):
                tools.package_receipt(root, "bwa", definition, "linux-64")

    def test_directory_softlink_is_structurally_bound_without_dropping_file_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "conda-meta").mkdir()
            library = root / "lib/python3.11"
            library.mkdir(parents=True)
            source = library / "os.py"
            source.write_text("# controlled pinned standard-library member\n")
            alias = root / "lib/python3.1"
            alias.symlink_to("python3.11", target_is_directory=True)
            record = {"name":"python", "version":"3.11.14", "build":"controlled", "sha256":"a" * 64,
                      "paths_data":{"paths":[{"_path":"lib/python3.11/os.py", "path_type":"hardlink", "sha256_in_prefix":tools.digest(source)},
                                               {"_path":"lib/python3.1", "path_type":"softlink", "sha256_in_prefix":hashlib.sha256(b"").hexdigest()}]}}
            (root / "conda-meta/python-3.11.14-controlled.json").write_text(json.dumps(record))
            receipt = tools.package_receipt(root, "python", {"version":"3.11.14"}, "linux-64")
            self.assertNotIn("lib/python3.1", receipt["files_sha256"])
            self.assertEqual(receipt["directory_links"]["lib/python3.1"], {"target":"python3.11", "resolved_directory":"lib/python3.11"})
            runtime = {"dependencies":{"python":receipt}}
            tools.verify_directory_links(runtime, root)
            (library / "__pycache__").mkdir()
            tools.verify_directory_links(runtime, root)  # Directory mtime is not source content.
            source.write_text("# changed source\n")
            with self.assertRaisesRegex(tools.ToolError, "content changed"):
                tools.package_receipt(root, "python", {"version":"3.11.14"}, "linux-64")

    def test_directory_link_retargeting_escape_and_type_changes_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "prefix"
            (root / "lib/python3.11").mkdir(parents=True)
            alias = root / "lib/python3.1"
            alias.symlink_to("python3.11", target_is_directory=True)
            runtime = {"dependencies":{"python":{"directory_links":{"lib/python3.1":tools.directory_link(root,"lib/python3.1")}}}}
            (root / "lib/other").mkdir()
            alias.unlink();alias.symlink_to("other", target_is_directory=True)
            with self.assertRaisesRegex(tools.ToolError, "directory link changed"):
                tools.verify_directory_links(runtime, root)
            alias.unlink();alias.symlink_to(Path(directory), target_is_directory=True)
            with self.assertRaisesRegex(tools.ToolError, "outside its installation"):
                tools.verify_directory_links(runtime, root)
            alias.unlink();alias.mkdir()
            with self.assertRaisesRegex(tools.ToolError, "changed or disappeared"):
                tools.verify_directory_links(runtime, root)

    def test_offline_source_install_applies_only_hash_bound_packaging_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            before, after = b"version = 'before'\n", b"version = 'after'\n"
            with tarfile.open(archive, "w:gz") as stream:
                member = tarfile.TarInfo("upstream/quartet/main.py")
                member.size = len(before)
                stream.addfile(member, io.BytesIO(before))
            definition = {"version": "fixture", "revision": "a" * 40, "archive": {"sha256": tools.digest(archive)},
                          "patches": [{"file": "quartet/main.py", "before_sha256": hashlib.sha256(before).hexdigest(),
                                       "after_sha256": hashlib.sha256(after).hexdigest(), "old": "before", "new": "after"}]}
            tools.install_source(root, definition, archive)
            receipt = tools.source_receipt(root, definition)
            self.assertEqual(receipt["files_sha256"]["quartet/main.py"], hashlib.sha256(after).hexdigest())
            installed = tools.source_location(root, definition) / "source/quartet/main.py"
            installed.write_text("tampered")
            with self.assertRaisesRegex(tools.ToolError, "content changed"):
                tools.source_receipt(root, definition)

    def test_archive_traversal_is_refused_even_for_a_fixture_with_known_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                member = tarfile.TarInfo("upstream/../../outside")
                member.size = 1
                stream.addfile(member, io.BytesIO(b"x"))
            definition = {"version": "fixture", "revision": "a" * 40, "archive": {"sha256": tools.digest(archive)}}
            with self.assertRaises(tools.ToolError):
                tools.install_source(root, definition, archive)
            self.assertFalse((root / "outside").exists())

    def test_one_tool_runtime_does_not_validate_unrelated_native_engines(self):
        lock = tools.load_lock()
        calls = []
        def package(prefix, name, definition, architecture):
            calls.append(name)
            return {"name": name, "version": "fixture"}
        with mock.patch.object(tools, "package_receipt", side_effect=package), \
                mock.patch.object(tools, "bundled_receipt", side_effect=AssertionError("unrelated DEGAP check")), \
                mock.patch.object(tools, "source_receipt", side_effect=AssertionError("unrelated quarTeT check")):
            receipt = tools.collect_receipt(Path("/fixture"), lock, tool="tgsgapcloser")
        self.assertEqual(set(receipt["tools"]), {"tgsgapcloser"})
        self.assertEqual(set(calls), {"tgsgapcloser", "python", "samtools", "minimap2", "racon"})

    def test_both_platform_specs_match_exact_locked_packages(self):
        lock = tools.load_lock()
        server = Path(__file__).resolve().parents[1]
        for architecture, filename in (("linux-64", "cgat-server.conda-spec.txt"),
                                        ("linux-aarch64", "cgat-server.linux-aarch64.conda-spec.txt")):
            spec = (server / filename).read_text().splitlines()
            for definition in [lock["tools"][name] for name in ("tgsgapcloser", "lrgapcloser")] + [lock["dependencies"][name] for name in ("bwa", "racon")]:
                pin = tools.package_pin(definition, architecture)
                self.assertIn(f"{pin['name']}={pin['version']}={pin['build']}", spec)
                self.assertEqual(len(pin["sha256"]), 64)


class NativeRecipeTests(unittest.TestCase):
    def setUp(self):
        self.lock = tools.load_lock()
        self.runtime = {"lock_sha256": tools.fingerprint(self.lock)}
        self.reads = {"hifi": ["/reads/hifi.fa"], "ont": ["/reads/ont.fa"]}

    def invocation(self, name, groups=None):
        return make_invocation(name, Path("/work/baseline.fa"), groups or self.reads, Path("/work/native/attempt"), 4,
                               prefix=Path("/env"), runtime=self.runtime, lock=self.lock)

    def test_defaults_and_fixed_order_require_no_final_tool_parameter(self):
        self.assertEqual(select_tools(None, has_reads=False), ())
        self.assertEqual(select_tools(None, has_reads=True), ("degap",))
        self.assertEqual(select_tools("none", has_reads=True), ())
        self.assertEqual(select_tools("quartet,degap", has_reads=True), ("degap", "quartet"))
        for value in ("none,degap", "degap,degap", "unknown"):
            with self.assertRaises(RecipeError):
                select_tools(value, has_reads=True)

    def test_supported_inputs_are_selected_once_and_unused_reads_reported(self):
        for name in ("degap", "quartet"):
            self.assertEqual(select_reads(name, self.reads)["mode"], "mixed")
        for name in ("tgsgapcloser", "lrgapcloser"):
            selected = select_reads(name, self.reads)
            self.assertEqual(selected["mode"], "hifi")
            self.assertEqual(selected["unused"]["ont"], ["/reads/ont.fa"])

    def test_tgs_hifi_and_ont_have_explicit_distinct_native_correction_recipes(self):
        hifi = self.invocation("tgsgapcloser")
        self.assertIn("--ne", hifi.command)
        self.assertIn(" -x asm20", hifi.command)
        self.assertNotIn("--racon", hifi.command)
        ont = self.invocation("tgsgapcloser", {"hifi": [], "ont": ["/reads/ont.fa"]})
        self.assertIn("--racon", ont.command)
        self.assertIn("/env/bin/racon", ont.command)
        self.assertNotIn("--ne", ont.command)

    def test_lr_driver_patch_is_content_bound_and_not_confused_by_255_log_path(self):
        with tempfile.TemporaryDirectory(prefix="cgat255-") as directory:
            prefix = Path(directory) / "env"
            (prefix / "bin").mkdir(parents=True)
            jobs = Path(directory) / "jobs"
            jobs.mkdir()
            patch = self.lock["tools"]["lrgapcloser"]["driver_patch"]
            before = ("#!/bin/bash\n" + patch["old"] + '\nprintf "%s" "$program"\n').encode()
            after = before.replace(patch["old"].encode(), patch["new"].encode())
            patch.update(before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(after).hexdigest())
            original = prefix / "bin/LR_Gapcloser.sh"
            original.write_bytes(before)
            invocation = make_invocation("lrgapcloser", Path("/baseline.fa"), self.reads,
                                         Path(directory) / "native", 1, prefix=prefix,
                                         runtime={"lock_sha256": tools.fingerprint(self.lock)},
                                         lock=self.lock, jobs_dir=jobs)
            driver = materialize_native_driver(invocation)
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(driver.read_bytes(), after)
            with (jobs / "native255.log").open("wb") as output:
                subprocess.run(invocation.command, env=invocation.environment, stdout=output, check=True)
            self.assertEqual((jobs / "native255.log").read_text(), str(prefix / "bin"))
            original.write_bytes(before + b"# changed\n")
            with self.assertRaisesRegex(RecipeError, "pinned packaging patch input"):
                materialize_native_driver(invocation)

    def test_quartet_and_lr_use_one_task_and_safe_native_file_namespaces(self):
        quartet = self.invocation("quartet")
        self.assertIn("/reads/hifi.fa", quartet.command)
        self.assertIn("/reads/ont.fa", quartet.command)
        self.assertNotIn("--enablejoin", quartet.command)
        with self.assertRaisesRegex(RecipeError, "basenames"):
            self.invocation("quartet", {"hifi": ["/hifi/reads.fa"], "ont": ["/ont/reads.fa"]})
        lr = self.invocation("lrgapcloser")
        self.assertEqual(lr.command[lr.command.index("-n") + 1], "1")
        self.assertEqual(lr.command[lr.command.index("-r") + 1], "3")
        self.assertNotIn("/reads/ont.fa", lr.command)


if __name__ == "__main__":
    unittest.main()
