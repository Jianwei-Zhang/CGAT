"""Source-resolution/seed contracts, using real private FASTA indexes, no native engine."""
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import server_source_identity as sources
import degap_results
from workspace_layout import initialize_workspace, workspace_join


@unittest.skipUnless(shutil.which("samtools"), "private indexing requires samtools")
class SeedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.root = self.home / "server"
        initialize_workspace(self.root)
        self.fasta = workspace_join(self.root, "data/datasets/original.fa")
        self.fasta.parent.mkdir(parents=True)
        self.sequence = "ACGTRYSWKMBDHVNACGT"
        self.fasta.write_text(">read description\n" + "\n".join(self.sequence[i:i + 7] for i in range(0, len(self.sequence), 7)) + "\n")
        metadata = workspace_join(self.root, "metadata")
        metadata.mkdir(parents=True)
        (metadata / "source_seq_locator.tsv").write_text("dataset_name\tseq_name\tfasta_relpath\noriginal\tread\tdata/datasets/original.fa\n")

    def recipe(self, tag="job", **member_changes):
        member = {"dataset": "original", "name": "read", "length": len(self.sequence), "start": 5, "end": 14,
                  "fasta_sha256": sources.digest(self.fasta), "interval_sha256": hashlib.sha256(self.sequence[4:14].encode()).hexdigest()}
        member.update(member_changes)
        recipe = {"schema": "gpm.degap.export.v1", "token": hashlib.sha256(tag.encode()).hexdigest(), "project_id": 1,
                  "job_id": tag, "job_type": "gapfiller", "server_root": str(self.root), "target_chr": "chr1", "target_track": "original",
                  "out_path": str(self.home / tag), "seed_plans": {
                      "seqleft": {"members": [member], "start": 1, "end": 10},
                      "seqright": {"members": [member], "start": 10, "end": 1}}}
        degap_results.begin(recipe)
        return recipe

    def test_numbered_full_and_light_bindings_preserve_iupac_reverse_seed_and_native_receipt(self):
        recipe = self.recipe()
        for side in ("seqleft", "seqright"):
            sources.prepare_seed(recipe, side)
        out = Path(recipe["out_path"])
        read = lambda name: "".join((out / name).read_text().splitlines()[1:])
        self.assertEqual(read("seqleft.fa"), "RYSWKMBDHV")
        self.assertEqual(read("seqright.fa"), "BDHVKMWSRY")
        proof = json.loads((out / ".gpm_degap_source_proof.json").read_text())
        self.assertEqual(proof["labels"]["seqleft"]["binding"], "content")
        self.assertFalse(Path(str(self.fasta) + ".fai").exists())
        degap_results.seed(recipe)
        (out / "job.final.fa").write_text(">candidate\nACGT\n")
        degap_results.record(recipe)
        recorded = json.loads((out / ".gpm_degap_result.json").read_text())
        self.assertEqual(recorded["source_proof"], proof)
        self.assertEqual(set(recorded["seed_sha256"]), {"seqleft.fa", "seqright.fa"})

    def test_full_interval_proof_works_without_a_server_file_hint_but_unbound_numbered_input_is_refused(self):
        recipe = self.recipe("interval", fasta_sha256=None)
        sources.prepare_seed(recipe, "seqleft")
        proof = json.loads((Path(recipe["out_path"]) / ".gpm_degap_source_proof.json").read_text())
        self.assertEqual(proof["labels"]["seqleft"]["binding"], "interval_content")
        recipe = self.recipe("unbound", fasta_sha256=None, interval_sha256=None)
        with self.assertRaisesRegex(ValueError, "require source identities"):
            sources.prepare_seed(recipe, "seqleft")

    def test_wrong_content_or_length_and_changed_seed_do_not_reach_native_receipt(self):
        for tag, fields in (("wrong-file", {"fasta_sha256": "0" * 64}),
                            ("wrong-slice", {"interval_sha256": "0" * 64}),
                            ("wrong-length", {"length": 999})):
            recipe = self.recipe(tag, **fields)
            with self.assertRaisesRegex(ValueError, "no content-matching"):
                sources.prepare_seed(recipe, "seqleft")
            self.assertFalse((Path(recipe["out_path"]) / "seqleft.fa").exists())
        recipe = self.recipe("modified-seed")
        for label in recipe["seed_plans"]:
            sources.prepare_seed(recipe, label)
        (Path(recipe["out_path"]) / "seqleft.fa").write_text(">changed\nAAAA\n")
        with self.assertRaisesRegex(ValueError, "seed changed"):
            degap_results.seed(recipe)

    def test_manual_source_uses_the_bound_consumed_catalog_without_hashing_unrelated_genomes(self):
        import degap_manual_catalog as manual
        from run_all_runner import WorkspaceLock
        from unittest import mock
        staged = self.home / "manual-staging"
        initialize_workspace(staged)
        shutil.copytree(workspace_join(self.root, "metadata"), workspace_join(staged, "metadata"))
        source = workspace_join(staged, "data/derived_ctgs/manual.fa")
        source.parent.mkdir(parents=True)
        source.write_text(">manual\nACGTNNAC\n")
        table = workspace_join(staged, "metadata/source_seq_locator.tsv")
        with table.open("a") as stream:
            stream.write("derived_ctg\tmanual\tdata/derived_ctgs/manual.fa\n")
        pointer = manual.seal(self.root, staged, manual.new_path(self.root), manual.base_binding(self.root), {})
        archive = self.home / "controlled.zip"
        archive.write_bytes(b"transaction fixture only")
        lock = WorkspaceLock(self.root, "source-closure-fixture")
        lock.acquire()
        try:
            manual.publish(self.root, lock, pointer, archive, self.home / "degap_results.zip")
        finally:
            lock.release()
        catalog = manual.catalog_path(self.root, pointer["catalog"])
        (catalog / "unrelated-diagnostic.txt").write_text("not consumed by this source request")
        recipe = self.recipe("unused-owner")
        recipe["out_path"] = str(self.home / "manual-output")
        recipe["seed_plans"] = {"seqleft": {"members": [{"dataset": "derived_ctg", "name": "manual", "length": 8,
                                  "start": 1, "end": 8, "fasta_sha256": sources.digest(source), "interval_sha256": None}],
                                  "start": 1, "end": 8}}
        degap_results.begin(recipe)
        with mock.patch.object(manual, "inventory", side_effect=AssertionError("must validate only consumed sources")):
            target = sources.prepare_seed(recipe, "seqleft")
        self.assertEqual("".join(target.read_text().splitlines()[1:]), "ACGTNNAC")
        with self.assertRaisesRegex(ValueError, "catalog"):
            manual.current(self.root)
        locator = workspace_join(catalog, "metadata/source_seq_locator.tsv")
        locator.write_text(locator.read_text() + "forged\trow\tunknown.fa\n")
        with self.assertRaisesRegex(ValueError, "manual source locator changed"):
            sources.prepare_seed(recipe, "seqleft")

    def test_refined_source_identities_survive_portable_paths_and_light_projection(self):
        from server.tests.refinement_bundle_fixture import create
        from server.tools.refinement_bundle import read_table
        result, full, light = create(self.home / "refined")
        full_map = json.loads((full / sources.MAP).read_text())
        self.assertEqual(full_map, json.loads((light / sources.MAP).read_text()))
        rows = read_table(Path(result["staging"]) / "sources.tsv")[1]
        patch = next(row for row in rows if row["origin"].startswith("refinement:"))
        identity = next(row for row in full_map["sources"] if (row["dataset"], row["contig"]) == (patch["dataset"], patch["contig"]))
        recipe = self.recipe("refined-seed")
        recipe["server_root"] = str(self.home / "refined")
        member = {"dataset": patch["dataset"], "name": patch["contig"], "length": identity["length"],
                  "start": 1, "end": identity["length"], "fasta_sha256": identity["fasta_sha256"], "interval_sha256": None}
        recipe["out_path"] = str(self.home / "refined-output")
        recipe["seed_plans"] = {"seqleft": {"members": [member], "start": 1, "end": member["length"]}}
        degap_results.begin(recipe)
        target = sources.prepare_seed(recipe, "seqleft")
        self.assertEqual("".join(target.read_text().splitlines()[1:]), "GTNNAC")
        proof = json.loads((target.parent / ".gpm_degap_source_proof.json").read_text())
        self.assertTrue(proof["labels"]["seqleft"]["sources"][0]["origin"].startswith("completed_refinement:"))
        self.assertFalse((light / "data/refinement/final.fa").exists())


class RuntimeSelectionTests(unittest.TestCase):
    def test_actual_exported_runtime_template_handles_both_layouts_and_refuses_fallback_or_pending_migration(self):
        runtime_source = Path(__file__).resolve().parents[2] / "app/backend/src/degap_jobs/server_runtime.rs"
        template = re.search(r'r#"(.*?)"#', runtime_source.read_text(), re.S).group(1)
        with tempfile.TemporaryDirectory() as directory:
            for numbered in (False, True):
                root = Path(directory) / ("numbered" if numbered else "legacy")
                if numbered:
                    initialize_workspace(root)
                tools = workspace_join(root, ".prepare_lib/tools")
                tools.mkdir(parents=True)
                shutil.copy2(Path(sources.__file__).with_name("workspace_layout.py"), tools / "workspace_layout.py")
                for name in ("degap_results.py", "server_source_identity.py"):
                    (tools / name).write_text("# runtime selection fixture, not executed\n")
                script = template.replace("{server}", shlex.quote(str(root))) + 'printf "%s\\n" "$CGAT_RUNTIME"\n'
                environment = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
                result = subprocess.run(["bash", "-euc", script], capture_output=True, text=True, env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(tools))
                self.assertFalse(list(tools.rglob("__pycache__")))
                if numbered:
                    (tools / "server_source_identity.py").unlink()
                    old = root / ".prepare_lib/tools"
                    old.mkdir(parents=True)
                    (old / "server_source_identity.py").write_text("# must not fall back\n")
                    failed = subprocess.run(["bash", "-euc", script], capture_output=True, text=True, env=environment)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertIn("Matching Server runtime is missing", failed.stderr)
                    (tools / "server_source_identity.py").write_text("# restored declared runtime\n")
                    (root / ".runtime/migration.json").write_text(json.dumps({"schema": "cgat.workspace-migration", "id": "a" * 32,
                              "from_version": 1, "to_version": 2, "state": "applying"}))
                    failed = subprocess.run(["bash", "-euc", script], capture_output=True, text=True, env=environment)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertIn("migration is incomplete", failed.stderr)


if __name__ == "__main__":
    unittest.main()
