"""One tiny staged native-adapter contract, not a reads benchmark or tool smoke."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_degap as adapter
from workspace_layout import initialize_workspace
from refinement_tools import load_lock, fingerprint


@unittest.skipUnless(shutil.which("samtools"), "samtools required for indexed sequence boundary")
class DegapRefinedPublicationTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(adapter, "validate_runtime", return_value={"lock_sha256": fingerprint(load_lock())})
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_workspace(self, root):
        layout = initialize_workspace(root)
        sequence = "AAAA" + "N" * 20 + "CCCC"
        source = layout.path("data/datasets/original.fa")
        source.parent.mkdir(parents=True)
        source.write_text(">original\n" + sequence + "\n")
        baseline = layout.path("grt/q/q3.fa")
        baseline.parent.mkdir(parents=True)
        baseline.write_text(">chr1\n" + sequence + "\n")
        path = {"workflow": "gpm_grt_precomputed_v2", "schema_version": "1", "q4_relpath": "grt/q/q3.fa",
                "chromosomes": [{"chr": "chr1", "q4_length": len(sequence), "q4_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                                 "segments": [{"segment_id": "original-segment", "kind": "source", "length": len(sequence), "orientation": "+",
                                               "source": {"dataset": "old", "contig": "original", "start": 1, "end": len(sequence), "orientation": "+"}}]}]}
        path_file = layout.path("metadata/grt_final_path.json")
        path_file.parent.mkdir(parents=True)
        path_file.write_text(json.dumps(path))
        layout.path("metadata/source_seq_locator.tsv").write_text("dataset_name\tseq_name\tfasta_relpath\nold\toriginal\tdata/datasets/original.fa\n")
        reads = root / "reads.fa"
        reads.write_text(">read1\nAAAAGTCCCC\n")
        return {"hifi": [str(reads)], "ont": []}, baseline.read_bytes(), path_file.read_bytes()

    def test_native_candidate_changes_final_path_and_reconstructed_fasta(self):
        real_run = subprocess.run
        commands = []
        def native(command, **kwargs):
            if command[0] == "samtools":
                return real_run(command, **kwargs)
            commands.append(command)
            output = Path(command[command.index("--output") + 1])
            report = output / "03.gap_filling/gap_filling_results.json"
            report.parent.mkdir(parents=True)
            candidate = output / "candidate.fa"
            candidate.write_text(">native\nAAAAGTCCCC\n")
            row = {"chromosome": "chr1", "gap_id": 1, "gap_start": 4, "gap_end": 23, "gap_len": 20,
                   "left_flank_len": 4, "right_flank_len": 4, "replace_start": 0, "replace_end": 27,
                   "replace_len": 28, "filled": True, "final_sequence_file": str(candidate)}
            report.write_text(json.dumps({"gaps": [row]}))
            final = output / "04.genome_integration/genome.filled.fasta"
            final.parent.mkdir()
            final.write_text(">chr1\nAAAAGTCCCC\n")
            config = {"jobs": [{"job_name": "chr1.1." + direction, "job_dir": str(report.parent / ("chr1.1." + direction)),
                                "chromosome": "chr1", "gap_id": 1, "direction": direction} for direction in ("left", "right")]}
            (output / "03.gap_filling/job_manager_config.json").write_text(json.dumps(config))
            summary = {"steps": {"step3": {"result": {"total_jobs": 2, "completed": 1, "failed": 0, "skipped": 1,
                       "completed_jobs": [{"job_name": "chr1.1.left", "status": "success"}], "failed_jobs": [],
                       "skipped_jobs": [{"job_name": "chr1.1.right", "status": "skipped"}]}}}}
            (output / "autogapfiller_summary.json").write_text(json.dumps(summary))
            return subprocess.CompletedProcess(command, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, fasta_before, path_before = self.make_workspace(root)
            with mock.patch.object(adapter, "check_environment"), mock.patch.object(adapter.subprocess, "run", side_effect=native):
                result = adapter.stage_degap(root, groups, 2)
            staging = Path(result["staging"])
            self.assertEqual((staging / "assembly.fa").read_text(), ">chr1\nAAAAGTCCCC\n")
            final = json.loads((staging / "final_path.json").read_text())
            self.assertEqual([s["kind"] for s in final["chromosomes"][0]["segments"]], ["source", "patch", "source"])
            self.assertEqual(final["chromosomes"][0]["segments"][-1]["source"]["start"], 25)
            self.assertEqual(final["chromosomes"][0]["segments"][-1]["output_start"], 6)
            self.assertEqual(result["provenance"]["counts"]["closed"], 1)
            self.assertEqual(result["provenance"]["accepted_edit_count"], 1)
            self.assertEqual((root / "03_lgz/04_step3/q3.fa").read_bytes(), fasta_before)
            self.assertEqual((root / ".runtime/metadata/grt_final_path.json").read_bytes(), path_before)
            self.assertFalse((root / "05_final").exists(), "staging alone is not an atomic final publication")
            self.assertEqual(len(commands), 1)

    def test_zero_exit_with_missing_native_assembly_is_incomplete(self):
        real_run = subprocess.run
        def native(command, **kwargs):
            if command[0] == "samtools":
                return real_run(command, **kwargs)
            output = Path(command[command.index("--output") + 1])
            report = output / "03.gap_filling/gap_filling_results.json"
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({"gaps": []}))
            return subprocess.CompletedProcess(command, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = self.make_workspace(root)
            run_id = "b" * 32
            with mock.patch.object(adapter, "check_environment"), mock.patch.object(adapter.subprocess, "run", side_effect=native):
                with self.assertRaises(OSError):
                    adapter.stage_degap(root, groups, 2, run_id=run_id)
            self.assertFalse((root / ".runtime/refinement/01_degap" / run_id / "final").exists())
            invocation = json.loads((root / "04_refinement/01_degap/02_jobs" / run_id / "invocation.json").read_text())
            self.assertEqual(invocation["status"], "failed")

    def test_native_zero_exit_unfilled_is_distinct_from_child_process_failure(self):
        config = {"jobs": [{"job_name": "gap.left"}]}
        native = {"total_jobs": 1, "completed": 0, "failed": 1, "skipped": 0,
                  "completed_jobs": [], "skipped_jobs": [], "failed_jobs": [{"job_name": "gap.left", "status": "failed",
                  "error": "Job execution completed but did not produce expected results"}]}
        payload = {"steps": {"step3": {"result": native}}}
        result = adapter.validate_native_job_summary(payload, config)
        self.assertFalse(result["hard_failures"])
        self.assertEqual(result["jobs"][0]["cgat_execution_outcome"], "completed_without_native_fill")
        native["failed_jobs"][0]["exit_code"] = 137
        self.assertEqual(adapter.validate_native_job_summary(payload, config)["hard_failures"], ["gap.left"])
        native["failed_jobs"] = []
        with self.assertRaisesRegex(ValueError, "incomplete"):
            adapter.validate_native_job_summary(payload, config)

    def test_failed_native_never_stages_a_successful_lgz_copy(self):
        real_run = subprocess.run
        def native(command, **kwargs):
            return real_run(command, **kwargs) if command[0] == "samtools" else subprocess.CompletedProcess(command, 9)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = self.make_workspace(root)
            run_id = "a" * 32
            with mock.patch.object(adapter, "check_environment"), mock.patch.object(adapter.subprocess, "run", side_effect=native):
                with self.assertRaises(subprocess.CalledProcessError):
                    adapter.stage_degap(root, groups, 2, run_id=run_id)
            invocation = json.loads((root / "04_refinement/01_degap/02_jobs" / run_id / "invocation.json").read_text())
            self.assertEqual(invocation["status"], "failed")
            self.assertFalse((root / ".runtime/refinement/01_degap" / run_id / "final").exists())
            self.assertFalse((root / "05_final").exists())


if __name__ == "__main__":
    unittest.main()
