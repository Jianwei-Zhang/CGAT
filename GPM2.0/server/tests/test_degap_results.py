"""Result recognition, immutable receipts, staged publication and rollback."""
import csv
import json
from pathlib import Path
import sys
import shlex
import subprocess
import zipfile
import io
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import degap_results as results


class DegapResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "job"
        self.out.mkdir()
        self.recipe = {"schema":"gpm.degap.export.v1", "token":"a" * 64,
                       "project_id":1, "job_id":"gap", "job_type":"gapfiller",
                       "out_path":str(self.out), "server_root":str(self.root / "server"),
                       "target_chr":"Chr01", "target_track":"primary", "endpoint_end":"R"}
        for name in ("seqleft.fa", "seqright.fa", "endpoint.ctg.fa"):
            (self.out / name).write_text(">endpoint\nACGT\n")

    def test_gap_candidate_snapshot_and_stale_run_rejected(self):
        results.begin(self.recipe)
        final = self.out / "job.final.fa"
        results.seed(self.recipe)
        final.write_text(">partial_extension\nACGTN\n")
        results.record(self.recipe)
        receipt = json.loads((self.out / ".gpm_degap_result.json").read_text())
        self.assertEqual(receipt["status"], "candidate")  # not a claim of gap closure
        self.assertEqual(receipt["sha256"], results.digest(self.out / receipt["fasta"]))
        self.assertEqual(set(receipt["seed_sha256"]), {"seqleft.fa", "seqright.fa"})
        with self.assertRaisesRegex(ValueError, "different inputs"):
            results.begin({**self.recipe, "job_id":"changed"})
        results.begin(self.recipe)
        self.assertFalse((self.out / ".gpm_degap_result.json").exists())

    def test_old_candidate_cannot_be_admitted_as_a_new_run(self):
        results.begin(self.recipe)
        (self.out / "job.final.fa").write_text(">old\nACGT\n")
        results.seed(self.recipe)
        with self.assertRaisesRegex(ValueError, "stale FASTA"):
            results.record(self.recipe)
        self.assertFalse((self.out / ".gpm_degap_result.json").exists())

    def test_ambiguous_outputs_and_arbitrary_fasta_are_not_guessed(self):
        (self.out / "random.fa").write_text(">x\nACGT\n")
        with self.assertRaisesRegex(ValueError, "found 0"):
            results.candidate(self.recipe)
        for name in ("job.final.fa", "job.direct.final.fa"):
            (self.out / name).write_text(">x\nACGT\n")
        with self.assertRaisesRegex(ValueError, "found 2"):
            results.candidate(self.recipe)

    def test_telseeker_failed_status_never_imports_leftover_success(self):
        recipe = {**self.recipe, "job_type":"telseeker_ctg"}
        results.begin(recipe)
        status = self.out / "result/status.tsv"
        status.parent.mkdir()
        status.write_text("ctg_id\tend\tstatus\tstop_reason\nendpoint\tR\tfailed\tconnection_not_found\n")
        results.seed(recipe)
        results.record(recipe)
        receipt = json.loads((self.out / ".gpm_degap_result.json").read_text())
        self.assertEqual(receipt["status"], "connection_not_found")
        self.assertNotIn("fasta", receipt)
        status.write_text("ctg_id\tend\tstatus\nendpoint\tL\tsuccess\n")
        with self.assertRaisesRegex(ValueError, "requested endpoint"):
            results.seed(recipe)
            results.record(recipe)

    def test_untracked_old_results_and_path_escape_refused(self):
        (self.out / "job.final.fa").write_text(">x\nACGT\n")
        with self.assertRaisesRegex(ValueError, "no matching GPM provenance"):
            results.begin(self.recipe)
        for path in ("../other", "/tmp/other"):
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                results.safe_path(self.root, path)

    def test_collect_two_jobs_builds_nested_packages_and_recollects_idempotently(self):
        server = Path(self.recipe["server_root"])
        metadata = server / "metadata"
        metadata.mkdir(parents=True)
        files = {
            "prepare_options.tsv": "key\tvalue\nalignment_engine\tminimap2\nminimap_preset\tasm5\nskip_self\tfalse\nsequence_layout\tpartitioned\npreassigned_chr\ttrue\nself_alignment_scope\tchr_partition\ncross_alignment_scope\tchr_partition\n",
            "datasets.tsv": "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nprimary\tprimary\t\tdata/p.fa\tdata/p.fa.fai\ttrue\n",
            "reference.tsv": "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref\tunknown\tref\tdata/ref.fa\tdata/ref.fa.fai\n",
            "reference_chr_locator.tsv": "reference_chr_name\tfasta_relpath\nChr01\tdata/ref.fa\n",
            "source_seq_locator.tsv": "dataset_name\tseq_name\tfasta_relpath\nprimary\tseed\truns/chr_Chr01/datasets/primary.fa\n",
            "source_seq_n_regions.tsv": "dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\n",
            "chr_assignments.tsv": "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nprimary\tseed\t4\tChr01\t+\tref_alignment\t4\t100.000\t1\n",
            "track_member_orders.tsv": "target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nprimary\tChr01\tprimary\tseed\t1\n",
        }
        for name, content in files.items():
            (metadata / name).write_text(content)
        for name, seq in (("data/ref.fa", "Chr01"), ("runs/chr_Chr01/datasets/primary.fa", "seed")):
            path = server / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f">{seq}\nACGT\n")
        scripts = self.root / "degap_jobs"; scripts.mkdir()
        jobs = self.root / "jobs.tsv"
        rows = ["job_id\tscript_path\tout_path"]
        for index in range(2):
            out = self.root / f"job{index}"; out.mkdir()
            recipe = {**self.recipe, "token":str(index + 1) * 64, "job_id":f"gap{index}", "out_path":str(out)}
            (scripts / f"job{index}.json").write_text(json.dumps(recipe))
            for seed in ("seqleft.fa", "seqright.fa"):
                (out / seed).write_text(">seed\nACGT\n")
            results.begin(recipe)
            results.seed(recipe)
            (out / f"job{index}.final.fa").write_text(">result\nACGT\n")
            results.record(recipe)
            rows.append(f"gap{index}\tdegap_jobs/job{index}.sh\t{out}")
        jobs.write_text("\n".join(rows) + "\n")
        def align(args, **kwargs):
            command = Path(args[1])
            line = next(line for line in command.read_text().splitlines() if line.startswith("minimap2 "))
            words = shlex.split(line.split(" > ")[0])
            query = Path(words[-1]); target = Path(words[-2])
            query_id = results.stage.read_fasta_records(query)[0][0]
            target_id = results.stage.read_fasta_records(target)[0][0]
            (command.parent / "result.paf").write_text(f"{query_id}\t4\t0\t4\t+\t{target_id}\t4\t0\t4\t4\t4\t60\tcg:Z:4M\n")
            return subprocess.CompletedProcess(args, 0)
        with mock.patch.object(results.subprocess, "run", side_effect=align) as runner:
            output = results.collect(jobs)
            self.assertEqual(runner.call_count, 4)
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read("degap_results.json"))
            self.assertEqual(len(manifest["results"]), 2)
            for entry in manifest["results"]:
                payload = archive.read(entry["package"])
                self.assertEqual(results.hashlib.sha256(payload).hexdigest(), entry["sha256"])
                with zipfile.ZipFile(io.BytesIO(payload)) as nested:
                    self.assertIn("gpm_server/metadata/track_member_orders.tsv", nested.namelist())
        with mock.patch.object(results.subprocess, "run", side_effect=AssertionError("must reuse verified packages")):
            results.collect(jobs)
        locators = results.stage.read_tsv(metadata / "source_seq_locator.tsv")[0]
        self.assertEqual(len(locators), 3)
        self.assertEqual((server / "runs/chr_Chr01/datasets/primary.fa").read_text(), ">seed\nACGT\n")

    def test_publication_failure_restores_existing_bytes_and_removes_new_files(self):
        server, stage = self.root / "server", self.root / "stage"
        (server / ".run_all").mkdir(parents=True)
        for root, text in ((server, "old"), (stage, "new")):
            (root / "metadata").mkdir(parents=True)
            (root / "metadata/state.tsv").write_text(text)
        (stage / "metadata/new.tsv").write_text("new")
        temp_zip, output = self.root / "new.zip", self.root / "result.zip"
        temp_zip.write_bytes(b"new result"); output.write_bytes(b"old result")
        original = results.os.replace
        def fail_result(src, dest):
            if Path(dest) == output:
                raise OSError("injected publish failure")
            return original(src, dest)
        with mock.patch.object(results.os, "replace", side_effect=fail_result):
            with self.assertRaisesRegex(OSError, "injected"):
                results.publish(stage, server, [], temp_zip, output)
        self.assertEqual((server / "metadata/state.tsv").read_text(), "old")
        self.assertFalse((server / "metadata/new.tsv").exists())
        self.assertEqual(output.read_bytes(), b"old result")


if __name__ == "__main__":
    unittest.main()
