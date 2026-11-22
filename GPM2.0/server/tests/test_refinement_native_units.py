"""Real launcher/checkpoint/cache, controlled upstream helper (not engine acceptance)."""
import os
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_native_checkpoint as checkpoint
import refinement_native_units as units
from refinement_path import PathError
from refinement_recipes import Invocation
from refinement_tools import WRAPPER, install_source, load_lock, source_location, source_receipt, fingerprint
from workspace_layout import initialize_workspace
from refinement_reports import native_diagnostics

CONTROLLED_UTIL = r'''
from pathlib import Path
import os

def minimap(reffasta, qryfasta, prefix, suffix, options, plot, overwrite, aligner, allow_empty=False):
    with Path(os.environ["CGAT_CONTROLLED_CALLS"]).open("a") as stream:
        stream.write(Path(reffasta).name + "\n")
    if Path(reffasta).name == "b.fa" and Path(os.environ["CGAT_CONTROLLED_FAIL"]).exists():
        raise RuntimeError("controlled second input failure")
    output = Path("tmp") / (prefix + "." + suffix + ".paf")
    output.write_text("")
    return str(output)
'''
CONTROLLED_MAIN = r'''
from pathlib import Path
import sys
from . import util

def main():
    args = sys.argv
    paths = args[args.index("-g") + 1:args.index("-t")]
    Path("tmp").mkdir()
    query = Path("tmp/flanks.fa")
    query.write_text(">flank\nAAAA\n")
    for path in paths:
        util.minimap(path, str(query), "quartet", "flank_map_" + Path(path).name,
                     "-x asm5", False, False, "minimap2", allow_empty=True)
    print("[INFO] All files processed.", flush=True)
    print("[ERROR] No gap can be closed.", flush=True)
    sys.exit(1)
'''


class NativeUnitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "workspace"
        initialize_workspace(self.root)
        runtime = Path(temporary.name) / "controlled_runtime"
        source = runtime / "source/quartet"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("")
        (source / "util.py").write_text(CONTROLLED_UTIL)
        (source / "main.py").write_text(CONTROLLED_MAIN)
        self.entrypoint = runtime / "quartet_runner.py"
        self.entrypoint.write_bytes(WRAPPER)
        self.reads = [self.root / name for name in ("a.fa", "b.fa")]
        for i, path in enumerate(self.reads):
            path.write_text(">read\n" + ("ACGT" if i else "AAAA") + "\n")
        self.calls = self.root / "controlled_calls.txt"
        self.fail = self.root / "controlled_fail"

    def execute(self, number, *, threads=2, runtime="controlled-runtime"):
        run_id = str(number) * 32
        base = self.root / "04_refinement/03_quartet"
        paths = {name: base / name / run_id for name in ("01_inputs", "02_jobs", "03_native")}
        paths["01_inputs"].mkdir(parents=True)
        paths["02_jobs"].mkdir(parents=True)
        baseline = paths["01_inputs"] / "native_baseline.fa"
        baseline.write_text(">chr1\nAAAA" + "N" * 100 + "CCCC\n")
        command = (sys.executable, "-I", "-B", str(self.entrypoint), "GapFiller", "-d", str(baseline),
                   "-g", *(str(path) for path in self.reads), "-t", str(threads))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CGAT_CONTROLLED_CALLS=str(self.calls), CGAT_CONTROLLED_FAIL=str(self.fail))
        recipe = {"threads": threads, "runtime_sha256": runtime, "reads": [{"path": str(path), "sha256": units.digest(path)} for path in self.reads],
                  "baseline_sha256": units.digest(baseline), "baseline_final_path_sha256": "controlled-final-path",
                  "baseline_source_files": {"controlled": "unchanged"}}
        invocation = Invocation("quartet", command, paths["03_native"], env, ("filled.fasta",),
                                {"threads": threads, "reads": {}, "name": "controlled"})
        record = {"run_id": run_id, "threads": threads, "timing": {}}
        dependencies = {str(path): units.digest(path) for path in (baseline, *self.reads)}
        return checkpoint.execute(self.root, invocation, recipe, paths, record, {}, lambda: None,
                                  chromosomes=["chr1"], parameters={}, input_hashes=dependencies,
                                  prepared_files=[str(path) for path in self.reads])

    def summary(self, number):
        jobs = self.root / "04_refinement/03_quartet/02_jobs" / (str(number) * 32)
        return jobs, units.checked_json(self.root, jobs / units.SUMMARY)

    def test_failed_second_input_keeps_first_empty_unit_and_retry_reuses_it(self):
        self.fail.touch()
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(1)
        jobs, first = self.summary(1)
        self.assertEqual(len(first["units"]), 1)
        self.assertEqual(first["units"][0]["result"]["outcome"], "empty_alignment")
        self.assertFalse((jobs / "native_complete.json").exists())
        diagnostics, _, _ = native_diagnostics(self.root, "quartet", "1" * 32, {})
        self.assertIn(first["units"][0]["receipt"], diagnostics)
        self.assertIn((jobs / units.SUMMARY).relative_to(self.root).as_posix(), diagnostics)
        original_receipt = self.root / first["units"][0]["receipt"]
        original_bytes = original_receipt.read_bytes()
        self.fail.unlink()
        second = self.execute(2)
        _, summary = self.summary(2)
        self.assertEqual([row["reused"] for row in summary["units"]], [True, False])
        self.assertEqual(self.calls.read_text().splitlines(), ["a.fa", "b.fa", "b.fa"])
        self.assertEqual(second["execution"]["native_substeps"], {
            "producer_run_id": "2" * 32, "completed": 2, "computed": 1, "reused": 1, "summary": "04_refinement/03_quartet/02_jobs/" + "2" * 32 + "/native_substeps.json"})
        self.assertEqual(original_bytes, original_receipt.read_bytes())
        self.assertTrue(any(path.endswith("producer.json") for path in second["result"]["artifacts"]))
        # Entire native success/no-candidate phase still takes priority on retry,
        # even with a different requested budget: no launcher or child reruns.
        third = self.execute(3, threads=8)
        self.assertTrue(third["reused"])
        self.assertEqual(third["run_id"], "2" * 32)
        self.assertEqual(third["execution"]["threads"], 2)
        self.assertEqual(self.calls.read_text().splitlines(), ["a.fa", "b.fa", "b.fa"])
        # Even resealing all current unit/summary hashes cannot turn a failed
        # original producer snapshot into a completed native unit.
        current_receipt = self.root / summary["units"][0]["receipt"]
        current = units.checked_json(self.root, current_receipt)
        producer_path = current_receipt.parent / "producer.json"
        producer = units.checked_json(self.root, producer_path)
        producer["status"] = "failed"
        units.seal(producer_path, producer)
        sha = units.digest(producer_path)
        current["artifacts"]["producer.json"] = sha
        current["origin"]["receipt_sha256"] = sha
        units.seal(current_receipt, current)
        summary["units"][0]["receipt_sha256"] = units.digest(current_receipt)
        summary["units"][0]["origin"] = current["origin"]
        units.seal(self.summary(2)[0] / units.SUMMARY, summary)
        with self.assertRaisesRegex(PathError, "original producer"):
            units.capture_units(self.root, "quartet", "2" * 32, 1, required=True)
        self.assertEqual(original_bytes, original_receipt.read_bytes())

    def test_nonempty_paf_is_restored_without_relabeling_native_no_candidate(self):
        source = self.entrypoint.parent / "source/quartet/util.py"
        paf = "flank\t4\t0\t4\t+\tread\t4\t0\t4\t4\t4\t60\tcg:Z:4M\n"
        source.write_text(source.read_text().replace('output.write_text("")', "output.write_text(" + repr(paf) + ")"))
        self.fail.touch()
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(1)
        self.fail.unlink()
        result = self.execute(2)
        summary = self.summary(2)[1]
        self.assertEqual([row["reused"] for row in summary["units"]], [True, False])
        self.assertEqual(summary["units"][0]["result"], {"records": 1, "outcome": "aligned"})
        self.assertEqual(result["result"]["outcome"], "no_candidates")

    def test_changed_input_runtime_and_threads_do_not_reuse_partial_units(self):
        self.fail.touch()
        for number, options in ((1, {}), (2, {"threads": 4}), (3, {"runtime": "changed-runtime"})):
            with self.assertRaises(subprocess.CalledProcessError):
                self.execute(number, **options)
            self.assertFalse(self.summary(number)[1]["units"][0]["reused"])
        self.reads[0].write_text(">read\nCCCC\n")
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(4)
        self.assertFalse(self.summary(4)[1]["units"][0]["reused"])
        self.assertEqual(self.calls.read_text().splitlines().count("a.fa"), 4)

    def test_tampered_or_symlinked_cache_is_not_adopted(self):
        self.fail.touch()
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(1)
        receipt = self.root / self.summary(1)[1]["units"][0]["receipt"]
        output = receipt.parent / "output.paf"
        output.write_text("partial or corrupted\n")
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(2)
        self.assertFalse(self.summary(2)[1]["units"][0]["reused"])
        receipt2 = self.root / self.summary(2)[1]["units"][0]["receipt"]
        outside = self.root / "outside.paf"
        shutil.copyfile(receipt2.parent / "output.paf", outside)
        (receipt2.parent / "output.paf").unlink()
        (receipt2.parent / "output.paf").symlink_to(outside)
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(3)
        self.assertFalse(self.summary(3)[1]["units"][0]["reused"])
        self.assertEqual(self.calls.read_text().splitlines().count("a.fa"), 3)

    def test_native_completion_rechecks_consumed_output_and_unit_closure(self):
        completed = self.execute(1)
        jobs, summary = self.summary(1)
        artifacts = units.capture_units(self.root, "quartet", "1" * 32, 1, required=True)
        self.assertTrue(artifacts)
        receipt = self.root / summary["units"][0]["receipt"]
        value = units.checked_json(self.root, receipt)
        consumed = self.root / value["consumed_output"]
        consumed.write_text("not the consumed PAF\n")
        with self.assertRaisesRegex(PathError, "consumer"):
            units.capture_units(self.root, "quartet", "1" * 32, 1, required=True)
        self.assertIn((jobs / units.SUMMARY).relative_to(self.root).as_posix(), completed["result"]["artifacts"])

    def test_resealed_summary_cannot_hide_a_selected_input(self):
        result = self.execute(1)
        jobs, summary = self.summary(1)
        summary["units"].pop()
        units.seal(jobs / units.SUMMARY, summary)
        invocation = Invocation("quartet", tuple(summary["native_command"]),
                                self.root / "04_refinement/03_quartet/03_native" / ("1" * 32),
                                {}, ("filled.fasta",), {})
        with self.assertRaisesRegex(PathError, "every selected"):
            checkpoint.capture(self.root, "quartet", "1" * 32, invocation.cwd, invocation, 1,
                               jobs / "native.log", ["chr1"], {}, [str(path) for path in self.reads], None)
        self.assertEqual(result["result"]["outcome"], "no_candidates")

    def test_paf_validation_distinguishes_empty_and_malformed_completion(self):
        paf = self.root / "format.paf"
        paf.write_text("")
        self.assertEqual(units.validate_paf(paf, allow_empty=True)["outcome"], "empty_alignment")
        with self.assertRaises(PathError):
            units.validate_paf(paf, allow_empty=False)
        paf.write_text("query\t4\t0\t4\t+\tref\t8\t2\t6\t4\t4\t60\tcg:Z:4M\n")
        self.assertEqual(units.validate_paf(paf, allow_empty=True)["records"], 1)
        paf.write_text(paf.read_text().replace("cg:Z:4M", "cg:Z:3M"))
        with self.assertRaises(PathError):
            units.validate_paf(paf, allow_empty=True)

    @unittest.skipUnless(os.environ.get("CGAT_TEST_QUARTET_ARCHIVE") and shutil.which("minimap2"),
                         "opt-in pinned source/developer aligner smoke")
    def test_pinned_source_with_developer_aligner_smoke(self):
        # Isolated source installation only. This does not upgrade/create an env
        # and is explicitly not conda/architecture/biological engine acceptance.
        prefix = self.root.parent / "isolated_source"
        definition = load_lock()["tools"]["quartet"]
        install_source(prefix, definition, Path(os.environ["CGAT_TEST_QUARTET_ARCHIVE"]))
        source = source_receipt(prefix, definition)
        self.entrypoint = source_location(prefix, definition) / "quartet_runner.py"
        bin_dir = prefix / "bin"
        bin_dir.mkdir()
        real = shutil.which("minimap2")
        shim = bin_dir / "minimap2"
        shim.write_text("#!" + sys.executable + "\n" +
                        "import os, sys\nfrom pathlib import Path\n" +
                        "if '-o' in sys.argv:\n" +
                        "    reference = Path(sys.argv[-2]).name\n" +
                        "    with Path(os.environ['CGAT_CONTROLLED_CALLS']).open('a') as stream:\n" +
                        "        stream.write(reference + '\\n')\n" +
                        "    if reference == 'b.fa' and Path(os.environ['CGAT_CONTROLLED_FAIL']).exists():\n" +
                        "        sys.exit(7)\n" +
                        "os.execv(" + repr(real) + ", [" + repr(real) + ", *sys.argv[1:]])\n")
        shim.chmod(0o755)
        constructor = Invocation
        def invocation(*args):
            value = constructor(*args)
            return replace(value, command=(*value.command, "-p", "quartet", "--noplot"),
                           environment={**value.environment, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        runtime = fingerprint({"source": source, "developer_aligner": units.digest(Path(real))})
        with mock.patch(__name__ + ".Invocation", side_effect=invocation):
            self.fail.touch()
            with self.assertRaises(subprocess.CalledProcessError):
                self.execute(1, runtime=runtime)
            self.fail.unlink()
            result = self.execute(2, runtime=runtime)
            summary = self.summary(2)[1]
            self.assertEqual([row["reused"] for row in summary["units"]], [True, False])
            self.assertEqual(self.calls.read_text().splitlines(), ["a.fa", "b.fa", "b.fa"])
            self.assertEqual(result["result"]["outcome"], "no_candidates")
            self.assertTrue(self.execute(3, threads=8, runtime=runtime)["reused"])
            self.assertEqual(self.calls.read_text().splitlines(), ["a.fa", "b.fa", "b.fa"])

    def test_malformed_receipt_shapes_are_cache_misses(self):
        jobs = self.root / "04_refinement/03_quartet/02_jobs" / ("2" * 32)
        jobs.mkdir(parents=True)
        store = units.UnitStore(self.root, "quartet", "2" * 32, {}, [])
        key, binding = "a" * 64, {"controlled": True}
        receipt = jobs.parent / ("1" * 32) / "native_units" / key / units.RECEIPT
        receipt.parent.mkdir(parents=True)
        receipt.write_text("[]")
        self.assertIsNone(store.find(key, binding, lambda path: {}))
        units.seal(receipt, {"schema": units.SCHEMA, "schema_version": 1, "status": "completed",
                             "tool": "quartet", "run_id": "1" * 32, "key": key,
                             "binding": binding, "origin": None, "execution": None})
        self.assertIsNone(store.find(key, binding, lambda path: {}))

    def test_input_mutation_during_execution_has_no_completion_receipt(self):
        run_id = "1" * 32
        jobs = self.root / "04_refinement/03_quartet/02_jobs" / run_id
        jobs.mkdir(parents=True)
        store = units.UnitStore(self.root, "quartet", run_id, {"controlled": True}, [])
        source = self.reads[0]
        output = jobs / "generated.paf"
        def producer():
            output.write_text("")
            source.write_text(">changed\nCCCC\n")
            return output
        with self.assertRaisesRegex(PathError, "input changed"):
            store.run({"suffix": "controlled"}, {"reference": source}, producer, lambda path: path,
                      lambda path: units.validate_paf(path, allow_empty=True))
        self.assertEqual(list((jobs / "native_units").glob("*/unit_complete.json")), [])


if __name__ == "__main__":
    unittest.main()
