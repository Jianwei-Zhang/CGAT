"""Real migration/installed collector, controlled old alignments, no native tool."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import degap_results as manual
import degap_legacy_cache as legacy_cache
from workspace_layout import WorkspaceLayout, initialize_workspace, MIGRATION
from migrate_workspace import preview, apply
from migrated_lgz import verified_baseline
from lgz_contract import validate_contract
import test_completed_workspace_migration as completed
from manual_source_bridge import controlled_aligner


class LegacyManualCacheTests(unittest.TestCase):
    def test_unmarked_leftover_cache_is_not_authority_for_a_new_numbered_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = initialize_workspace(root / "server")
            token = "a" * 64
            cache = layout.path(".run_all/degap_packages/" + token + ".json")
            cache.parent.mkdir(parents=True)
            cache.write_text("{}")
            with self.assertRaisesRegex(ValueError, "not bound.*migration"):
                legacy_cache.lookup(layout.root, {"token": token}, root / "unused", {})

    @unittest.skipUnless(shutil.which("samtools"), "real migrated scientific fixture needs source indexing")
    def test_migrated_cache_reuses_original_package_without_native_or_alignment_and_preserves_unknown_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            server = home / "legacy"
            completed.CompletedWorkspaceMigrationTests().legacy(server)
            export = home / "original-export"
            (export / "degap_jobs").mkdir(parents=True)
            out = export / "native"
            out.mkdir()
            token = "a" * 64
            recipe = {"schema": "gpm.degap.export.v1", "token": token, "project_id": 1,
                      "job_id": "old-gap", "job_type": "gapfiller", "out_path": str(out),
                      "server_root": str(server), "target_chr": "chr1", "target_track": "a", "endpoint_end": "R"}
            (export / "degap_jobs/old.json").write_text(json.dumps(recipe))
            jobs = export / "jobs.tsv"
            jobs.write_text("job_id\tscript_path\tout_path\nold-gap\tdegap_jobs/old.sh\t" + str(out) + "\n")
            for name in ("seqleft.fa", "seqright.fa"):
                (out / name).write_text(">seed\nACGT\n")
            manual.begin(recipe)
            manual.seed(recipe)
            (out / "native.final.fa").write_text(">candidate\nACGT\n")
            manual.record(recipe)
            receipt = json.loads((out / ".gpm_degap_result.json").read_text())
            candidate = out / receipt["fasta"]
            controlled_bin = home / "controlled-bin"
            controlled_bin.mkdir()
            controlled_aligner(controlled_bin)
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                           "PATH": str(controlled_bin) + os.pathsep + os.environ["PATH"]}
            with mock.patch.dict(os.environ, environment):
                old_output = manual.collect(jobs)
            old_zip = old_output.read_bytes()
            old_cache = server / ".run_all/degap_packages" / token
            old_archive = old_cache.with_suffix(".zip").read_bytes()
            original_cache = {suffix: (old_cache.with_suffix(suffix).stat().st_mtime_ns, old_cache.with_suffix(suffix).read_bytes())
                              for suffix in (".zip", ".json")}
            prepared = preview(server, TOOLS.parent)
            apply(server, TOOLS.parent, prepared.digest, confirm_idle=True)
            layout = WorkspaceLayout.detect(server)
            baseline = verified_baseline(server)
            contract = validate_contract(server)
            scientific = {layout.path(row["destination"]): layout.path(row["destination"]).read_bytes()
                          for row in baseline["scientific_files"]}
            native = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in out.iterdir() if path.is_file()}
            # Presence alone never permits replacing an external historical ZIP.
            with self.assertRaisesRegex(ValueError, "unowned.*ZIP"):
                manual.collect(jobs)
            self.assertEqual(old_output.read_bytes(), old_zip)
            self.assertFalse(layout.path(manual.manual_catalog.POINTER).exists())
            adoption = legacy_cache.lookup(server, recipe, candidate, receipt)
            self.assertEqual(adoption.evidence["migration_id"], json.loads(layout.path(MIGRATION).read_text())["id"])
            with self.assertRaisesRegex(ValueError, "original task/native receipt"):
                legacy_cache.lookup(server, {**recipe, "job_id": "not-original"}, candidate, receipt)
            cached_info = layout.path(".run_all/degap_packages/" + token + ".json")
            original_info = cached_info.read_bytes()
            cached_info.write_bytes(original_info + b"\n")
            with self.assertRaisesRegex(ValueError, "changed during adoption"):
                adoption.verify()
            with self.assertRaisesRegex(ValueError, "migrated manual cache/source changed"):
                legacy_cache.lookup(server, recipe, candidate, receipt)
            cached_info.write_bytes(original_info)
            unknown_token = "b" * 64
            unknown_info = layout.path(".run_all/degap_packages/" + unknown_token + ".json")
            unknown_info.write_bytes(original_info)
            with self.assertRaisesRegex(ValueError, "absent.*migration inventory"):
                legacy_cache.lookup(server, {**recipe, "token": unknown_token}, candidate, receipt)
            unknown_info.unlink()
            # A new outer export destination retains the SAME original token,
            # recipes and native outputs. No user final path or task is reset.
            fresh = home / "fresh-export"
            fresh.mkdir()
            shutil.copy2(jobs, fresh / "jobs.tsv")
            shutil.copytree(export / "degap_jobs", fresh / "degap_jobs")
            sentinel = home / "unexpected-alignment"
            (controlled_bin / "minimap2").write_text("#!/bin/bash\necho should-not-run > '" + str(sentinel) + "'\nexit 93\n")
            command = [sys.executable, "-B", str(layout.path(".prepare_lib/tools/degap_results.py")),
                       "collect", "--jobs", str(fresh / "jobs.tsv")]
            result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(sentinel.exists())
            catalog, manifest, _ = manual.manual_catalog.current(server)
            self.assertEqual(set(manifest["packages"]), {token})
            registered = manifest["packages"][token]
            self.assertEqual(registered["adopted_from"], adoption.evidence)
            archive, info = manual.manual_catalog.package_paths(server, registered)
            self.assertEqual(archive.read_bytes(), old_archive)
            self.assertEqual(info.read_bytes(), original_info)
            with zipfile.ZipFile(fresh / "degap_results.zip") as package:
                metadata = json.loads(package.read("degap_results.json"))
                self.assertEqual(metadata["results"][0]["recipe"], recipe)
                self.assertEqual(package.read(metadata["results"][0]["package"]), old_archive)
            self.assertEqual(old_output.read_bytes(), old_zip)
            for suffix, (mtime, payload) in original_cache.items():
                path = layout.path(".run_all/degap_packages/" + token + suffix)
                self.assertEqual(path.read_bytes(), payload)
                # The negative tamper probe deliberately rewrote .json; its
                # bytes remain exact but only the untouched ZIP retains mtime.
                if suffix == ".zip":
                    self.assertEqual(path.stat().st_mtime_ns, mtime)
            for path, expected in native.items():
                self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), expected)
            self.assertEqual(verified_baseline(server), baseline)
            self.assertEqual(validate_contract(server), contract)
            for path, expected in scientific.items():
                self.assertEqual(path.read_bytes(), expected, str(path))
            # Later collection uses the immutable registry, not historical cache.
            result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
