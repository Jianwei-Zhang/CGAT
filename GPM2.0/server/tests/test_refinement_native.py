"""Controlled native format/execution boundaries; not real reads-engine benchmarks."""
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
import refinement_native as native
from refinement_tools import fingerprint, load_lock
from workspace_layout import initialize_workspace, TOOL_DIRECTORIES


def workspace(root, *, gap=100, name="chr1"):
    layout = initialize_workspace(root)
    sequence = "AAAA" + "N" * gap + "CCCC"
    source = layout.path("data/datasets/original.fa")
    source.parent.mkdir(parents=True)
    source.write_text(">original\n" + sequence + "\n")
    genome = layout.path("grt/q/q3.fa")
    genome.parent.mkdir(parents=True)
    genome.write_text(">" + name + "\n" + sequence + "\n")
    payload = {"workflow": "gpm_grt_precomputed_v2", "schema_version": "1", "q4_relpath": "grt/q/q3.fa",
               "chromosomes": [{"chr": name, "q4_length": len(sequence), "q4_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                                "segments": [{"segment_id": "old", "kind": "source", "length": len(sequence), "orientation": "+",
                                              "source": {"dataset": "old", "contig": "original", "start": 1, "end": len(sequence), "orientation": "+"}}]}]}
    metadata = layout.path("metadata/grt_final_path.json")
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps(payload))
    layout.path("metadata/source_seq_locator.tsv").write_text("dataset_name\tseq_name\tfasta_relpath\nold\toriginal\tdata/datasets/original.fa\n")
    reads = root / "hifi.fq"
    reads.write_text("@r\nAAAAGTCCCC\n+\nIIIIIIIIII\n")
    return {"hifi": [str(reads)], "ont": []}, genome, metadata


@unittest.skipUnless(shutil.which("samtools"), "real samtools indexing required")
class NativeStageTests(unittest.TestCase):
    def setUp(self):
        self.runtime = mock.patch.object(native, "validate_runtime", return_value={"lock_sha256": fingerprint(load_lock())})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        driver = mock.patch.object(native, "materialize_native_driver", return_value=None)
        driver.start()
        self.addCleanup(driver.stop)
        self.real_run = subprocess.run

    def fake(self, tool, command, **kwargs):
        if Path(command[0]).name == "samtools":
            return self.real_run(command, **kwargs)
        if tool == "tgsgapcloser":
            output = Path(command[command.index("--output") + 1]).parent
            (output / "tgs.scaff_seqs").write_text(">chr1\nAAAAGTCCCC\n")
            (output / "tgs.name_map").write_text("1\tchr1\n")
            first, second = "1\t+\t100\t4\t1\t1\t1\n", "2\t+\t0\t4\t105\t2\t1\n"
            (output / "tgs.orignial_scaff_infos").write_text(">scaffold 1\n" + first + second)
            (output / "tgs.updated_scaff_infos").write_text(">scaffold 1\n1\t+\t2\t4\t1\t1\t1\tONT_FILL=GT\n" + second)
            (output / "tgs.gap_fill_detail").write_text(">chr1\n1\t4\tS\t1\t4\n5\t6\tF\n7\t10\tS\t105\t108\n")
        elif tool == "quartet":
            output = Path(kwargs["cwd"])
            reads = Path(command[command.index("-g") + 1])
            rid = reads.read_text().splitlines()[0][1:]
            src = str(reads) + "@" + rid
            (output / "quartet.genome.filled.fasta").write_text(">chr1\nAAAAGTCCCC\n")
            (output / "quartet.genome.filled.detail").write_text("# native detail\nchr1\t1\tClosed\t" + src + "\t5-6\t2\t+\t1.0\n")
            (output / "quartet.genome.filled.modified.agp").write_text(
                "chr1\t1\t4\t1\tP\tchr1\t1\t4\t+\n" +
                "chr1\t5\t6\t2\tW\t" + src + "\t5\t6\t+\n" +
                "chr1\t7\t10\t3\tP\tchr1\t105\t108\t+\n")
        else:
            output = Path(command[max(i for i, value in enumerate(command) if value == "-o") + 1])
            input_fasta = Path(command[command.index("-i") + 1])
            name = input_fasta.read_text().splitlines()[0][1:]
            folder = output / "iteration-1/tmp"
            folder.mkdir(parents=True)
            (output / "iteration-1/gapclosed.fasta").write_text(">" + name + "\nAAAAGTCCCC\n")
            (folder / "info_filter2").write_text(f"{name}(:5-104\tLR1(:5-6(:+\t{name}(:5-104\n")
        return subprocess.CompletedProcess(command, 0)

    def test_all_three_native_formats_build_real_refined_paths(self):
        for tool in ("tgsgapcloser", "quartet", "lrgapcloser"):
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "workspace"
                groups, genome, path = workspace(root)
                original = (genome.read_bytes(), path.read_bytes())
                with mock.patch.object(native.subprocess, "run", side_effect=lambda command, **kwargs: self.fake(tool, command, **kwargs)):
                    result = native.stage_refinement(root, tool, groups, 2)
                staged = Path(result["staging"])
                self.assertEqual((staged / "assembly.fa").read_text(), ">chr1\nAAAAGTCCCC\n")
                final = json.loads((staged / "final_path.json").read_text())
                self.assertEqual(final["tool"], tool)
                self.assertEqual(final["chromosomes"][0]["segments"][-1]["source"]["start"], 105)
                self.assertEqual(result["provenance"]["counts"]["closed"], 1)
                self.assertTrue(result["provenance"]["trace_sources"])
                self.assertEqual(original, (genome.read_bytes(), path.read_bytes()))
                self.assertFalse((root / "05_final").exists())

    def test_lr_unsafe_chromosome_names_are_aliased_not_rejected_or_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = workspace(root, name="chr-1(:source")
            with mock.patch.object(native.subprocess, "run", side_effect=lambda command, **kwargs: self.fake("lrgapcloser", command, **kwargs)):
                result = native.stage_refinement(root, "lrgapcloser", groups, 2)
            self.assertTrue((Path(result["staging"]) / "assembly.fa").read_text().startswith(">chr-1(:source\n"))
            self.assertEqual(result["provenance"]["execution"]["recipe"]["chromosome_names"], {"chr-1(:source": "cgat_chr_000001"})

    def test_tgs_zero_exit_without_native_artifacts_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = workspace(root)
            def empty(command, **kwargs):
                return self.real_run(command, **kwargs) if Path(command[0]).name == "samtools" else subprocess.CompletedProcess(command, 0)
            run_id = "b" * 32
            with mock.patch.object(native.subprocess, "run", side_effect=empty):
                with self.assertRaisesRegex(ValueError, "missing artifact"):
                    native.stage_refinement(root, "tgsgapcloser", groups, 1, run_id=run_id)
            receipt = root / "04_refinement/02_tgsgapcloser/02_jobs" / run_id / "invocation.json"
            self.assertEqual(json.loads(receipt.read_text())["status"], "failed")
            self.assertFalse((root / ".runtime/refinement/02_tgsgapcloser" / run_id / "final").exists())

    def test_quartet_explicit_no_candidate_is_not_an_arbitrary_failure_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, genome, _ = workspace(root)
            def empty(command, **kwargs):
                if Path(command[0]).name == "samtools":
                    return self.real_run(command, **kwargs)
                reads = Path(command[command.index("-g") + 1])
                (Path(kwargs["cwd"]) / ("quartet.flank_map_" + reads.name + ".paf")).write_text("")
                kwargs["stdout"].write(b"[INFO] All files processed.\n[ERROR] No gap can be closed.\n")
                return subprocess.CompletedProcess(command, 1)
            with mock.patch.object(native.subprocess, "run", side_effect=empty):
                result = native.stage_refinement(root, "quartet", groups, 1)
            self.assertEqual(result["provenance"]["status"], "native_no_candidates")
            # Final FASTA is deliberately wrapped at 60 bp; wrapping is not
            # a biological change and must not invalidate the no-fill outcome.
            actual = (Path(result["staging"]) / "assembly.fa").read_text().splitlines()
            expected = genome.read_text().splitlines()
            self.assertEqual(actual[0], expected[0])
            self.assertEqual("".join(actual[1:]), "".join(expected[1:]))
            self.assertEqual(result["provenance"]["execution"]["native_returncode"], 1)

    def test_quartet_no_eligible_gaps_does_not_convert_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            groups, _, _ = workspace(root, gap=20)
            with mock.patch.object(native, "prepare_native_reads", side_effect=AssertionError("unnecessary conversion")):
                result = native.stage_refinement(root, "quartet", groups, 1)
            self.assertEqual(result["provenance"]["status"], "native_no_eligible_gaps")
            self.assertFalse(result["provenance"]["execution"]["native_executed"])
            self.assertFalse((root / "01_inputs/03_reads/converted").exists())


if __name__ == "__main__":
    unittest.main()
