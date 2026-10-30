"""Deferred branch overlay/package definitions. NOT executed in implementation."""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import prepare_branch_server_package as package
import server_alignment as sa
import windowed_alignment as wa


class BranchServerPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/"source"
        (self.source/"tools").mkdir(parents=True)
        (self.source/"lib").mkdir()
        official = Path(__file__).resolve().parents[2]/"server"
        (self.source/"prepare.sh").write_bytes((official/"prepare.sh").read_bytes())
        (self.source/"tools/run_outer_checkpoints.py").write_bytes((official/"tools/run_outer_checkpoints.py").read_bytes())
        (self.source/"run.sh").write_bytes(b"#!/bin/bash\n# never execute test file\n")
        (self.source/"tools/server_run.py").write_bytes((official/"tools/server_run.py").read_bytes())
        (self.source/"lib/incremental_common.sh").write_text("# mock only\n")
        (self.source/"SOURCE.json").write_text('{"baseline":"preserve me"}\n')
        self.inventory = sorted(p.relative_to(self.source).as_posix() for p in self.source.rglob("*") if p.is_file())
        self.before = {name:wa.sha256(self.source/name) for name in self.inventory}
        self.bundle = self.root/"bundle"
        self.bundle.mkdir()
        (self.bundle/package.build.BINARY).write_bytes(b"mock binary; never executed")
        (self.bundle/package.build.BINARY).chmod(0o755)
        (self.bundle/package.build.MANIFEST).write_text('{"mock":"NOT a valid compiled companion receipt"}\n')
        self.native = {"platform":"linux-x86_64","manifest_path":str(self.bundle/package.build.MANIFEST),
            "sha256":wa.sha256(self.bundle/package.build.BINARY),"manifest_sha256":wa.sha256(self.bundle/package.build.MANIFEST)}
        self.args = argparse.Namespace(out=self.root/"new package",server_source=self.source,native_state_bundle=self.bundle)

    def prepare(self):
        with patch.object(package.nst,"validate_bundle",return_value=self.native), \
             patch.object(package,"source_inventory",return_value=(self.inventory,{"mock":True})):
            return package.prepare_package(self.args)

    def test_plan_only_requires_no_companion_read_source_scan_or_file_creation(self):
        with patch.object(package.nst,"validate_bundle",side_effect=AssertionError("must not inspect companion")), \
             patch.object(package,"source_inventory",side_effect=AssertionError("must not inspect source")), \
             redirect_stdout(io.StringIO()) as text:
            code = package.main(["--out",str(self.args.out)])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
        self.assertFalse(self.args.out.exists())

    def test_only_named_initial_reference_and_runtime_copy_sites_are_overlaid(self):
        original = (self.source/"prepare.sh").read_text()
        patched = package.overlay_prepare(original)
        self.assertEqual(patched.count("long_cigar_recovery/server_alignment.py"),1)
        self.assertIn('if [[ "$MINIMAP_PRESET" == "asm10" ]]',patched)
        self.assertIn('"\\${GPM_TASK_THREADS:-${THREADS}}',patched)
        restored = patched.replace(package.REF_OVERLAY,"").replace(package.COPY_OVERLAY,"")
        self.assertEqual(restored,original)
        for label in ("write_self_command_script()", "write_pair_command_script()"):
            # These helpers stay byte-identical; no branch adapter for self/pairs.
            if label in original:
                self.assertEqual(original[original.index(label):],restored[restored.index(label):])
        self.assertNotIn("--native-state-bundle",package.REF_OVERLAY)
        self.assertNotIn("--execute",package.REF_OVERLAY)

    def test_generator_drift_duplicate_or_wrong_function_refuses_instead_of_guessing(self):
        original = (self.source/"prepare.sh").read_text()
        for text in (original.replace(package.REF_ANCHOR,""),original+package.REF_ANCHOR,
                     original.replace("write_ref_command_script() {","renamed_function() {"),package.overlay_prepare(original)):
            with self.assertRaises(wa.ExperimentError):
                package.overlay_prepare(text)

    def test_checkpoint_overlay_binds_runtime_and_only_reference_inputs(self):
        original = (self.source/"tools/run_outer_checkpoints.py").read_text()
        patched = package.overlay_checkpoint(original)
        ast.parse(patched)  # Deferred syntax check only, no execution of Server code.
        self.assertEqual(patched.replace(package.CHECKPOINT_OVERLAY,""),original)
        self.assertIn("__pycache__",package.CHECKPOINT_OVERLAY)
        self.assertIn(".prepare_lib/tools/long_cigar_recovery",patched)
        for text in (original.replace(package.CHECKPOINT_ANCHOR,""),original+package.CHECKPOINT_ANCHOR,
                     original.replace("def _reference_inputs(","def _another_unit("),patched):
            with self.assertRaises(wa.ExperimentError):
                package.overlay_checkpoint(text)

    def test_existing_workspace_hook_is_inside_the_original_lock_and_does_not_replace_run_sh(self):
        original = (self.source/"tools/server_run.py").read_text()
        patched = package.overlay_server_run(original)
        ast.parse(patched)
        self.assertEqual(patched.replace(package.RUN_OVERLAY,""),original)
        self.assertLess(patched.index("lock.acquire()"),patched.index("handoff_report = handoff"))
        self.assertLess(patched.index("handoff_report = handoff"),patched.index("return Runner(root, units, run_id).run()"))
        for text in (original.replace(package.RUN_ANCHOR,""),patched):
            with self.assertRaises(wa.ExperimentError):
                package.overlay_server_run(text)

    def test_maintainer_prior_profile_uses_immutable_git_bytes_with_the_same_original_recipe(self):
        (self.source/"tools/alignment_tasks.py").write_bytes(b"# fixture task schema\n")
        revision = "d"*40
        def git(command,**kwargs):
            if "--show-toplevel" in command:
                return "/readonly-repository\n"
            if "--show-prefix" in command:
                return "GPM2.0/server/\n"
            if "rev-parse" in command:
                return revision+"\n"
            if "show" in command:
                name = command[-1].split(":",1)[1].removeprefix("GPM2.0/server/")
                return (self.source/name).read_bytes()
            return b"GPM2.0/server/tools/server_run.py\0GPM2.0/server/tools/run_outer_checkpoints.py\0GPM2.0/server/tools/alignment_tasks.py\0"
        with patch.object(package.subprocess,"check_output",side_effect=git):
            profile = package.resume_source_profile(self.source,revision)
        self.assertEqual(profile["revision"],revision)
        self.assertTrue(profile["reference_launch_checkpoint_recipe_equal"])
        self.assertEqual(profile["base_tools_files_sha256"]["tools/server_run.py"],wa.sha256(self.source/"tools/server_run.py"))
        with self.assertRaisesRegex(wa.ExperimentError,"full immutable"):
            package.resume_source_profile(self.source,"latest")
        def changed(command,**kwargs):
            if "show" in command and command[-1].endswith(":GPM2.0/server/prepare.sh"):
                return b"different generated reference recipe"
            return git(command,**kwargs)
        with patch.object(package.subprocess,"check_output",side_effect=changed),self.assertRaisesRegex(wa.ExperimentError,"different reference"):
            package.resume_source_profile(self.source,revision)

    def test_runtime_import_closure_is_packaged_including_lazy_native_and_seam_imports(self):
        root = Path(sa.__file__).resolve().parent
        available = {p.stem for p in root.glob("*.py")}
        shipped = {Path(name).stem for name in sa.RUNTIME_FILES if name.endswith(".py")}
        for name in sa.RUNTIME_FILES:
            if not name.endswith(".py"):
                continue
            for node in ast.walk(ast.parse((root/name).read_text())):
                imports = [x.name for x in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
                for item in imports:
                    local = item.split(".",1)[0]
                    if local in available:
                        self.assertIn(local,shipped,(name,local))
        self.assertIn("native_chain_state.c",sa.RUNTIME_FILES)
        self.assertIn("MINIMAP2_LICENSE.txt",sa.RUNTIME_FILES)
        self.assertFalse(any(name.startswith("test_") for name in sa.RUNTIME_FILES))

    def test_development_archive_is_complete_hashed_and_not_marked_customer_deliverable(self):
        # An unrelated user data directory in the source root is NOT inventory.
        (self.source/"private-data").mkdir()
        (self.source/"private-data/genome.fa").write_bytes(b"do not package user data")
        report = self.prepare()
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["customer_deliverable"])
        self.assertEqual(report["recovered_output_admission"],"closed_pending_final_acceptance")
        self.assertFalse(report["tests_executed"])
        self.assertFalse(report["compilation_performed"])
        server = self.args.out/"GPM_Server"
        self.assertEqual((server/"run.sh").read_bytes(),(self.source/"run.sh").read_bytes())
        self.assertEqual((server/"SOURCE.base.json").read_bytes(),(self.source/"SOURCE.json").read_bytes())
        self.assertFalse((server/"private-data").exists())
        self.assertEqual(sa.validate_runtime(server/"tools/long_cigar_recovery")["recovered_output_admission"],"closed_pending_final_acceptance")
        with tarfile.open(report["archive"],"r:gz") as archive:
            self.assertTrue(all(m.isfile() for m in archive.getmembers()))
            self.assertEqual({m.name.removeprefix("GPM_Server/") for m in archive.getmembers()},set(report["packaged_files_sha256"]))
            for member in archive.getmembers():
                digest = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                self.assertEqual(digest,report["packaged_files_sha256"][member.name.removeprefix("GPM_Server/")])
        self.assertEqual(wa.sha256(Path(report["archive"])),report["archive_sha256"])
        self.assertEqual({name:wa.sha256(self.source/name) for name in self.inventory},self.before)
        self.assertIn("NOT A CUSTOMER REPAIR RELEASE",(server/"BRANCH_README.txt").read_text())

    def test_static_zlib_license_is_preserved_in_customer_platform_bundle(self):
        license_path = self.bundle/"ZLIB_LICENSE_AND_HEADER.txt"
        license_path.write_text("fixture license only\n")
        self.native["third_party_licenses_sha256"] = {license_path.name:wa.sha256(license_path)}
        report = self.prepare()
        relative = "tools/long_cigar_recovery/native/linux-x86_64/"+license_path.name
        self.assertEqual(report["packaged_files_sha256"][relative],wa.sha256(license_path))
        self.assertEqual((self.args.out/"GPM_Server"/relative).read_bytes(),license_path.read_bytes())

    def test_missing_prebuilt_companion_does_not_create_an_artifact_or_compile(self):
        self.args.native_state_bundle = None
        with patch.object(package.subprocess,"Popen",side_effect=AssertionError("no compiler allowed")), \
             self.assertRaisesRegex(wa.ExperimentError,"maintainer must build"):
            package.prepare_package(self.args)
        self.assertFalse(self.args.out.exists())

    def test_original_source_symlink_or_missing_inventory_member_is_not_silently_copied(self):
        for index,names in enumerate((["not-present.py"],["alias.py"])):
            (self.source/"alias.py").unlink(missing_ok=True)
            (self.source/"alias.py").symlink_to(self.source/"tools/server_run.py")
            with self.assertRaises(wa.ExperimentError):
                package.copy_regular_tree(self.source,self.root/f"copy-{index}",names)

    def test_output_inside_a_prepared_workspace_is_refused_before_packaging(self):
        workspace = self.root/"customer"
        (workspace/".prepare_lib").mkdir(parents=True)
        self.args.out = workspace/"new-package"
        with self.assertRaisesRegex(wa.ExperimentError,"outside prepared"):
            self.prepare()
        self.assertFalse(self.args.out.exists())

    def test_tracked_inventory_excludes_tests_and_rejects_foreign_paths_without_using_absolute_alias_case(self):
        def git(command,**kwargs):
            if "--show-prefix" in command:
                return "GPM2.0/server/\n"
            if "ls-files" in command:
                return b"GPM2.0/server/run.sh\0GPM2.0/server/tests/test_one.py\0GPM2.0/server/tools/server_run.py\0"
            return "a"*40+"\n"
        with patch.object(package.subprocess,"check_output",side_effect=git):
            names,revision = package.source_inventory(self.source)
        self.assertEqual(names,["run.sh","tools/server_run.py"])
        self.assertTrue(revision["commit_is_baseline_only"])
        with patch.object(package.subprocess,"check_output",side_effect=["GPM2.0/server/\n",b"elsewhere/private.fa\0"]):
            with self.assertRaisesRegex(wa.ExperimentError,"escaped"):
                package.source_inventory(self.source)


if __name__=="__main__":
    unittest.main()
