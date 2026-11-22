"""Project job input and discovery controls, without native tools."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

SERVER = Path(__file__).resolve().parents[1]
TOOLS = SERVER / "tools"
sys.path.insert(0, str(TOOLS))
from refine import MANIFEST, SCHEMA, prepare_batch, read_tasks
from refine_report import SECTION_START, SECTION_END, automatic_overview_digest, merge_manual_overview
from refine_run import MANIFEST as RESULTS_MANIFEST, publish_results
from refinement_jobs_index import write_automatic_index
from workspace_layout import MANIFEST as WORKSPACE_MARKER, TOOL_DIRECTORIES, WorkspaceLayout, initialize_workspace
from run_orchestration import sha256_file


def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


class RefineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.layout = initialize_workspace(self.home / "workspace")
        self.origin = self.write("03_lgz/04_step3/q4.fa", ">chr1\nGGGNNNTTT\n")
        self.write("metadata/grt_final_path.json", json.dumps({"q4_relpath": "grt/q/q4.fa"}))
        self.source = self.write("data/datasets/src.fa", ">left\nCAGG\n>right\nACTT\n")
        self.write("metadata/source_seq_locator.tsv",
                   "dataset_name\tseq_name\tfasta_relpath\n"
                   "ds\tleft\tdata/datasets/src.fa\n"
                   "ds\tright\tdata/datasets/src.fa\n")

    def write(self, relative, content):
        path = self.layout.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def locus(self, chr_name, segment, *, missing=False):
        left, right = "left", "missing" if missing else "right"
        result = {"chr": chr_name, "kind": "gap", "id": hash_text(json.dumps([chr_name, "gap", segment], separators=(",", ":"))),
                  "target": segment, "gap_bp": 5, "tools": ["degap", "lrgapcloser", "quartet"],
                  "witnesses": {"target": {"segment_id": segment, "kind": "gap", "gap_bp": 5}}, "seed_plans": {}}
        for label, contig, start, end in (("seqleft", left, 4, 2), ("seqright", right, 1, 2)):
            result["witnesses"][label] = {"kind": "ctg", "segment_id": label + segment,
                                          "dataset": "ds", "contig": contig, "start": start, "end": end}
            result["seed_plans"][label] = {"members": [{"dataset": "ds", "name": contig, "length": 4,
                                                        "start": min(start, end), "end": max(start, end),
                                                        "fasta_sha256": sha256_file(self.source), "interval_sha256": None}],
                                           "start": 3 if start > end else 1,
                                           "end": 1 if start > end else 2}
        return result

    def archive(self, loci, *, origin=None, extra=None):
        manifest = {"schema": SCHEMA, "export_id": "a" * 64, "origin_fasta_sha256": origin or sha256_file(self.origin),
                    "reads": {"hifi": [], "ont": []}, "loci": loci}
        archive = self.home / "tasks.zip"
        with ZipFile(archive, "w") as zipped:
            zipped.writestr(MANIFEST, json.dumps(manifest))
            if extra:
                zipped.writestr(extra, "invalid")
        return archive

    def test_prepares_selected_orientation_and_n_length_under_08_without_changing_lgz(self):
        gap = self.locus("chr1", "gap-1")
        archive = self.archive([gap, self.locus("chr2", "gap-2", missing=True)])
        origin = sha256_file(self.origin)
        outcome = prepare_batch(self.layout.root, archive)
        self.assertEqual([row["status"] for row in outcome["loci"]], ["prepared", "input_unavailable"])
        receipt = self.layout.root / outcome["loci"][0]["receipt"]
        self.assertTrue(receipt.is_relative_to(self.layout.root / "08_refinement_jobs/02_manual"))
        self.assertEqual(sha256_file(receipt.parent.parent / MANIFEST), outcome["batch_sha256"])
        genome = receipt.with_name("local.fa")
        self.assertEqual(genome.read_text(), ">locus\nCCTNNNNNAC\n")
        self.assertEqual(sha256_file(self.origin), origin)
        first_mtime = genome.stat().st_mtime_ns
        self.assertEqual(prepare_batch(self.layout.root, archive), outcome)
        self.assertEqual(genome.stat().st_mtime_ns, first_mtime)
        genome.write_text(">locus\nAAAA\n")
        self.assertEqual(prepare_batch(self.layout.root, archive)["loci"][0]["status"], "input_unavailable")

    def test_rejects_wrong_project_source_and_unexpected_archive_entry(self):
        gap = self.locus("chr1", "gap-1")
        with self.assertRaisesRegex(ValueError, "does not match"):
            prepare_batch(self.layout.root, self.archive([gap], origin="b" * 64))
        self.assertFalse(self.layout.path("08_refinement_jobs").exists())
        with self.assertRaisesRegex(ValueError, "unexpected"):
            read_tasks(self.archive([gap], extra="run.sh"))
        # Equal interval length and orientation do not authorize another source.
        gap["witnesses"]["seqleft"]["contig"] = "right"
        with self.assertRaisesRegex(ValueError, "source witness"):
            read_tasks(self.archive([gap]))

    def test_publication_keeps_automatic_proof_and_preserves_manual_section_on_regeneration(self):
        original = "<html><main><h1>automatic report</h1></main></html>"
        overview = self.write("06_report/report.html", original)
        sealed = sha256_file(overview)
        gap = self.locus("chr1", "gap-1")
        archive = self.archive([gap])
        preparation = prepare_batch(self.layout.root, archive)
        with ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read(MANIFEST))
        batch = preparation["batch_sha256"]
        directory = self.layout.path(f"08_refinement_jobs/02_manual/{batch}")
        patch_file = self.write("patch.seq", "ACGT")
        patch_name = f"patches/{gap['id']}.degap.seq"
        row = {"locus_id": gap["id"], "tool": "degap", "status": "closed", "reason": None,
               "version": "2.0", "revision": "r1", "attempt_id": "attempt-1",
               "patch": {"operation": "replace_gap", "original_length": 5, "original_sha256": hash_text("NNNNN"),
                         "path": patch_name, "length": 4, "sha256": hash_text("ACGT")}}
        reads = {"degap": [{"technology": "hifi", "path": "/reads/a&b.fq.gz", "sha256": "f" * 64}]}

        outputs = publish_results(self.layout, directory, batch, [row], {patch_name: patch_file}, manifest=manifest, reads=reads)
        report = Path(outputs["batch_report"]).read_text()
        self.assertIn("HIFI", report.upper())
        self.assertEqual(json.loads(Path(outputs["report"]).read_text())["reads"], reads)
        self.assertIn("Pending App import", overview.read_text())
        self.assertIn("automatic report", overview.read_text())
        self.assertEqual(automatic_overview_digest(overview), sealed)
        with ZipFile(outputs["delivery"]) as zipped:
            self.assertEqual(zipped.read(patch_name), b"ACGT")
            self.assertEqual(json.loads(zipped.read(RESULTS_MANIFEST))["batch_sha256"], batch)
        summary = json.loads(Path(outputs["report"]).read_text())
        self.assertEqual(summary["delivery_sha256"], sha256_file(Path(outputs["delivery"])))
        html = overview.read_bytes()
        self.assertEqual(html.count(SECTION_START.encode()), 1)
        self.assertEqual(html.count(SECTION_END.encode()), 1)
        publish_results(self.layout, directory, batch, [row], {patch_name: patch_file}, manifest=manifest, reads=reads)
        self.assertEqual(overview.read_bytes(), html)
        regenerated = merge_manual_overview(self.layout, original.replace("automatic report", "fresh automatic report"))
        self.assertIn("fresh automatic report", regenerated)
        self.assertIn(batch, regenerated)
        overview.write_text(regenerated, encoding="utf-8")
        self.assertNotEqual(automatic_overview_digest(overview), sealed)

    def _install_refine(self):
        tools = self.layout.path(".lib/tools")
        shutil.copytree(TOOLS, tools, ignore=shutil.ignore_patterns("__pycache__", "degap_core"))
        shutil.copytree(SERVER / "contracts", tools.parent / "contracts")
        return tools / "refine.py"

    def test_installed_and_global_refine_cli_use_workspace_runtime(self):
        marker = self.layout.path(WORKSPACE_MARKER)
        marker.write_text(json.dumps({**self.layout.manifest(), "prepared_runtime": ".lib"}), encoding="utf-8")
        self.layout = WorkspaceLayout.detect(self.layout.root)
        installed = self._install_refine()
        self.assertEqual(installed, self.layout.root / ".lib/tools/refine.py")
        self.write("metadata/prepare_options.tsv", "key\tvalue\nthreads\t1\n")
        archive = self.archive([self.locus("chr1", "gap-1")])
        relative_archive = "../" + archive.name
        global_entry = self.home / "bin/refine.py"
        global_entry.parent.mkdir()
        shutil.copyfile(installed, global_entry)
        checked = subprocess.run([sys.executable, str(global_entry), relative_archive, "--prepare-only"],
                                 cwd=self.layout.root, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        batch = json.loads(checked.stdout)["batch_sha256"]
        self.assertFalse(self.layout.path("06_report/report.html").exists())
        executed = subprocess.run([sys.executable, str(installed), relative_archive], cwd=self.layout.root,
                                  capture_output=True, text=True)
        self.assertEqual(executed.returncode, 1, executed.stderr)
        result = json.loads(executed.stdout)
        self.assertEqual({r["status"] for r in result["results"]}, {"missing_reads"})
        with ZipFile(result["delivery"]) as zipped:
            self.assertEqual(zipped.namelist(), [RESULTS_MANIFEST])
            self.assertEqual(json.loads(zipped.read(RESULTS_MANIFEST))["batch_sha256"], batch)
        overview = Path(result["overview"]).read_text()
        self.assertIn("尚无自动总报告", overview)
        self.assertIn("无可导回补丁", overview)
        self.assertNotIn("Pending App import", overview)
        self.assertIn("Missing reads", Path(result["batch_report"]).read_text())
        self.assertFalse(self.layout.path("05_final").exists())

    def test_global_refine_accepts_numbered_runtime_without_new_marker(self):
        installed = self._install_refine()
        self.assertIn(".runtime/prepared", installed.as_posix())
        archive = self.archive([self.locus("chr1", "gap-1")])
        checked = subprocess.run([sys.executable, str(TOOLS / "refine.py"), str(archive), "--prepare-only"],
                                 cwd=self.layout.root, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["loci"][0]["status"], "prepared")

    def test_automatic_index_does_not_link_bare_or_unmatched_publication(self):
        batch_id = "a" * 32
        batch = self.write(f".runtime/refinement/batches/{batch_id}.json", json.dumps({
            "schema": "cgat.refinement-batch", "schema_version": 1, "batch_id": batch_id, "status": "partial_failure", "tools": {
                "degap": {"status": "published", "run_id": "run", "publication_transaction": "old"},
                "quartet": {"status": "failed", "error": "no environment"},
            },
        }))
        overview = self.write("06_report/report.html", "overview")
        completion = self.write(".runtime/refinement/completions/run.json", json.dumps({
            "schema": "cgat.refinement-invocation", "batch_id": batch_id, "batch_sha256": sha256_file(batch),
            "overview_files": {"06_report/report.html": sha256_file(overview)},
        }))
        self.write("07_delivery/01_degap/example.zip", "not a committed archive")
        with patch("refinement_jobs_index.current_publication", return_value=None):
            index = write_automatic_index(self.layout, completion)
        items = json.loads(index.read_text())["jobs"]
        rows = {row["tool"]: row for row in (json.loads(self.layout.path(entry).read_text()) for entry in items)}
        self.assertEqual(rows["degap"]["status"], "publication_unverified")
        self.assertFalse(rows["degap"]["delivery"])
        self.assertEqual(rows["quartet"]["reason"], "no environment")
        batch.write_text("{}")
        with self.assertRaisesRegex(ValueError, "batch differs"):
            write_automatic_index(self.layout, completion)

    def test_automatic_index_links_existing_manifest_bound_artifacts(self):
        tool = "degap"
        code = TOOL_DIRECTORIES[tool]
        batch_id = "c" * 32
        report_rel = f"06_report/02_refinement/{code}/report.html"
        report = self.write(report_rel, "tool report")
        overview = self.write("06_report/report.html", "overview")
        full = self.write(f"07_delivery/{code}/demo.zip", "full")
        light = self.write(f"07_delivery/{code}/demo.light.zip", "light")
        archives = {mode: {"file": path.name, "sha256": sha256_file(path)} for mode, path in (("full", full), ("light", light))}
        manifest = self.write(f"07_delivery/{code}/delivery.json", json.dumps({"archives": archives}))
        publication = {"transaction": "tx", "run_id": "native", "areas": {
            "report": {"new": {"files": {"report.html": sha256_file(report)}}},
            "delivery": {"new": {"files": {"delivery.json": sha256_file(manifest),
                                           **{row["file"]: row["sha256"] for row in archives.values()}}}},
        }}
        batch = self.write(f".runtime/refinement/batches/{batch_id}.json", json.dumps({
            "schema": "cgat.refinement-batch", "schema_version": 1, "batch_id": batch_id, "status": "published", "tools": {
                tool: {"status": "published", "run_id": "native", "publication_transaction": "tx"}},
        }))
        completion = self.write(".runtime/refinement/completions/run.json", json.dumps({
            "schema": "cgat.refinement-invocation", "batch_id": batch_id, "batch_sha256": sha256_file(batch),
            "overview_files": {"06_report/report.html": sha256_file(overview)},
        }))
        with patch("refinement_jobs_index.current_publication", return_value=publication):
            index = write_automatic_index(self.layout, completion)
        row = json.loads(self.layout.path(json.loads(index.read_text())["jobs"][0]).read_text())
        self.assertEqual(row["report"], report_rel)
        self.assertEqual(row["delivery"], {"full": f"07_delivery/{code}/demo.zip", "light": f"07_delivery/{code}/demo.light.zip"})
        self.assertFalse(list(index.parent.glob("**/*.zip")))


if __name__ == "__main__":
    unittest.main()
