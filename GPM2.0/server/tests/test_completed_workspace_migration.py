"""Real completed-LGZ migration; no native alignment/refinement is executed."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from migrate_workspace import preview, apply
from migrated_lgz import verified_baseline, PROOF
from workspace_layout import WorkspaceLayout, LayoutError
from lgz_contract import validate_contract
from refinement_bundle_fixture import FIXTURE


@unittest.skipUnless(shutil.which("samtools"), "real source indexing requires samtools")
class CompletedWorkspaceMigrationTests(unittest.TestCase):
    def legacy(self, root):
        root.mkdir()
        for name, content in json.loads(FIXTURE.read_text())["files"].items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (root / "metadata/prepare_options.tsv").write_text("key\tvalue\nthreads\t1\narchive_format\tzip\n")
        (root / ".run_all").mkdir(exist_ok=True)
        with (root / "metadata/datasets.tsv").open() as stream:
            dataset = next(csv.DictReader(stream, delimiter="\t"))["dataset_name"]
        rows = [("ref:" + dataset, f"runs/{dataset}_vs_ref/command.sh"), ("grt_step3", "run_grt_step3.sh"),
                ("finalize_evidence", "finalize_grt_evidence.sh"), ("package_full", "package_full_zip.sh"),
                ("package_light", "package_light_zip.sh")]
        for unit, name in rows:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/bin/bash\necho SHOULD-NOT-EXECUTE-OLD-" + unit + " >&2\nexit 91\n")
            target.chmod(0o755)
        (root / "run_all.sh").write_text("#!/bin/bash\necho OLD-LAUNCHER >&2\nexit 92\n")
        (root / ".run_all/plan.tsv").write_text("unit_id\tcommand_relpath\tdetail_log_relpath\n" + "".join(f"{unit}\t{name}\tlogs/run_all.log\n" for unit, name in rows))
        original_runtime = root / ".prepare_lib/tools/lgz_step1.py"
        original_runtime.parent.mkdir(parents=True)
        original_runtime.write_text("# controlled historical code; never imported or executed\nraise RuntimeError('must not run historical engine')\n")
        return rows

    def test_manual_candidate_catalog_does_not_invalidate_the_original_migrated_lgz_proof(self):
        import degap_results as manual
        from workspace_layout import workspace_join
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy-project"
            self.legacy(root)
            prepared = preview(root, TOOLS.parent)
            apply(root, TOOLS.parent, prepared.digest, confirm_idle=True)
            proof = verified_baseline(root)
            contract = validate_contract(root)
            scientific = {str(WorkspaceLayout.detect(root).path(row["destination"])):
                          WorkspaceLayout.detect(root).path(row["destination"]).read_bytes()
                          for row in proof["scientific_files"]
                          if WorkspaceLayout.detect(root).path(row["destination"]).is_file()}
            export = Path(directory) / "export"
            (export / "degap_jobs").mkdir(parents=True)
            out = export / "native-job"
            out.mkdir()
            recipe = {"schema": "gpm.degap.export.v1", "token": "a" * 64, "project_id": 1,
                      "job_id": "gap", "job_type": "gapfiller", "out_path": str(out),
                      "server_root": str(root), "target_chr": "chr1", "target_track": "a", "endpoint_end": "R"}
            (export / "degap_jobs/gap.json").write_text(json.dumps(recipe))
            (export / "jobs.tsv").write_text("job_id\tscript_path\tout_path\ngap\tdegap_jobs/gap.sh\t" + str(out) + "\n")
            for name in ("seqleft.fa", "seqright.fa"):
                (out / name).write_text(">seed\nACGT\n")
            manual.begin(recipe)
            manual.seed(recipe)
            (out / "native-job.final.fa").write_text(">candidate\nACGT\n")
            manual.record(recipe)
            # Exercise the installed collector and dependency closure, with a
            # controlled PAF producer rather than a native alignment acceptance.
            fake_bin = Path(directory) / "controlled-bin"
            fake_bin.mkdir()
            minimap = fake_bin / "minimap2"
            minimap.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\n"
                               "query = Path(sys.argv[-1])\n"
                               "name = next(line[1:].split()[0] for line in query.read_text().splitlines() if line.startswith('>'))\n"
                               "Path(sys.argv[sys.argv.index('-o') + 1]).write_text(f'{name}\\t4\\t0\\t4\\t+\\tchr1\\t5000\\t0\\t4\\t4\\t4\\t60\\tcg:Z:4M\\n')\n")
            minimap.chmod(0o755)
            layout = WorkspaceLayout.detect(root)
            self.assertEqual(layout.path(".prepare_lib/tools/degap_manual_catalog.py").read_bytes(),
                             (TOOLS / "degap_manual_catalog.py").read_bytes())
            executed = subprocess.run([sys.executable, "-B", str(layout.path(".prepare_lib/tools/degap_results.py")),
                                       "collect", "--jobs", str(export / "jobs.tsv")], capture_output=True, text=True,
                                      env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
                                           "PYTHONDONTWRITEBYTECODE": "1"}, timeout=45)
            self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
            self.assertEqual(verified_baseline(root), proof)
            self.assertEqual(validate_contract(root), contract)
            for path, content in scientific.items():
                self.assertEqual(Path(path).read_bytes(), content, path)
            catalog, _, _ = manual.manual_catalog.current(root)
            new_rows = manual.stage.read_tsv(workspace_join(catalog, "metadata/source_seq_locator.tsv"))[0]
            self.assertTrue(any(row["dataset_name"] == "derived_ctg" for row in new_rows))
            old_rows = manual.stage.read_tsv(workspace_join(root, "metadata/source_seq_locator.tsv"))[0]
            self.assertFalse(any(row["dataset_name"] == "derived_ctg" for row in old_rows))

    def test_preview_apply_public_resume_preserve_original_proof_and_never_execute_lgz(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy-project"
            self.legacy(root)
            # A skipped historical DEGAP may still have the original typed
            # reads receipt, which must not block either unrefined LGZ archive.
            reads = Path(directory) / "hifi.fq"
            reads.write_text("@sample\nACGT\n+\nIIII\n")
            (root / "metadata/degap_inputs.json").write_text(json.dumps({
                "purpose": "post_lgz_degap_v1", "schema_version": 2,
                "hifi": [str(reads)], "ont": [],
            }))
            contract = validate_contract(root)
            before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            inspected = subprocess.run([sys.executable, "-B", str(TOOLS / "migrate_workspace.py"),
                                        "--server-dir", str(root), "--preview"], capture_output=True, text=True, timeout=30)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            prepared = preview(root, TOOLS.parent)
            self.assertEqual(json.loads(inspected.stdout)["approval_sha256"], prepared.digest)
            self.assertTrue(prepared.summary()["eligible"])
            self.assertFalse((root / ".runtime").exists())
            self.assertTrue(all((root / name).read_bytes() == content for name, content in before.items()))
            with self.assertRaisesRegex(LayoutError, "confirm"):
                apply(root, TOOLS.parent, prepared.digest)
            applied = subprocess.run([sys.executable, "-B", str(TOOLS / "migrate_workspace.py"),
                                      "--server-dir", str(root), "--apply", "--approve", prepared.digest,
                                      "--confirm-idle"], capture_output=True, text=True, timeout=60)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            result = json.loads(applied.stdout)
            self.assertEqual(result["status"], "committed")
            layout = WorkspaceLayout.detect(root)
            self.assertEqual(layout.version, 2)
            self.assertFalse((root / ".run_all").exists())
            self.assertEqual(validate_contract(root), contract)
            proof = verified_baseline(root)
            self.assertEqual(proof["contract"], contract)
            for name, content in before.items():
                if name.startswith(("data/", "metadata/", "grt/")):
                    self.assertEqual(layout.path(name).read_bytes(), content, name)
            engine_backup = root / ".runtime/migrations" / result["migration_id"] / "originals/.prepare_lib/tools/lgz_step1.py"
            self.assertEqual(engine_backup.read_bytes(), before[".prepare_lib/tools/lgz_step1.py"])
            command = ["bash", str(root / "run_all.sh"), "--gapfill-tools", "none"]
            # A checkout has no installed release binding; this exercises the
            # actual newly installed public launcher and runner, not a mock.
            self.assertEqual(layout.path(".prepare_lib/server-tools.path").read_text().strip(), "")
            launched = subprocess.run(command, capture_output=True, text=True, timeout=90,
                                      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(launched.returncode, 0, launched.stdout[-4000:] + launched.stderr[-4000:])
            self.assertIn("SKIP_MIGRATED_LGZ", launched.stdout)
            self.assertNotIn("SHOULD-NOT-EXECUTE-OLD", launched.stdout + launched.stderr)
            self.assertNotIn("REFERENCE HANDOFF", launched.stdout)
            self.assertTrue((root / "05_final/00_lgz/assembly.fa").is_file())
            archives = list((root / "07_delivery/00_lgz").glob("*.zip"))
            self.assertEqual(len(archives), 2)
            for archive in archives:
                with zipfile.ZipFile(archive) as bundle:
                    self.assertFalse(any("/data/degap/" in name or "/metadata/degap_" in name
                                         for name in bundle.namelist()))
            self.assertFalse((root / "05_final/01_degap").exists())
            records = [json.loads(path.read_text()) for path in layout.path("report/steps").glob("*.json")]
            frozen = [row for row in records if row.get("execution") == "frozen_original_lgz"]
            self.assertGreaterEqual(len(frozen), 3)
            # No new-engine checkpoint is manufactured for the old prefix.
            self.assertFalse(list(layout.path(".run_all/checkpoints").glob("ref-*.json")))
            for name, content in before.items():
                if name.startswith(("data/", "metadata/", "grt/")):
                    self.assertEqual(layout.path(name).read_bytes(), content, name)
            plan = layout.path(".run_all/plan.tsv")
            plan_bytes = plan.read_bytes()
            plan.write_bytes(plan_bytes + b"grt_step1\t.runtime/commands/run_grt_step1.sh\t.runtime/logs/run_all.log\n")
            with self.assertRaisesRegex(LayoutError, "plan changed"):
                verified_baseline(root)
            plan.write_bytes(plan_bytes)
            self.assertIsNotNone(verified_baseline(root))
            receipt = root / PROOF
            raw = receipt.read_bytes()
            mode = receipt.stat().st_mode & 0o777
            receipt.unlink()
            with self.assertRaisesRegex(LayoutError, "receipt is missing"):
                verified_baseline(root)
            receipt.write_bytes(raw)
            receipt.chmod(mode)
            self.assertIsNotNone(verified_baseline(root))
            fasta = layout.path("grt/q/q4.fa")
            fasta.write_bytes(fasta.read_bytes() + b"\n")
            with self.assertRaisesRegex(LayoutError, "refusing to recompute"):
                verified_baseline(root)


if __name__ == "__main__":
    unittest.main()
