"""Actual pinned DEGAP job scheduler/analyzer; controlled preprocessing/children.

This exercises real fork workers and child shells, not biological engine or
managed dependency/environment acceptance.
"""
from pathlib import Path
import json
import importlib.util
import multiprocessing
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_native_checkpoint as checkpoint
import refinement_native_units as units
from refinement_degap_units import NO_FILL, input_binding
from refinement_path import PathError
from refinement_recipes import Invocation
from refinement_reports import native_diagnostics
from refinement_tools import fingerprint, load_lock
from workspace_layout import initialize_workspace

CHILD = r'''
import argparse, os, sys
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--out'); parser.add_argument('--flag')
args, _ = parser.parse_known_args()
out = Path(args.out)
with Path(os.environ['CGAT_TEST_CALLS']).open('a') as stream:
    stream.write(out.name + '\n')
if '.2.' in out.name and Path(os.environ['CGAT_TEST_FAIL']).exists():
    print('controlled exit 7', file=sys.stderr)
    sys.exit(7)
if '.1.left' in out.name and Path(os.environ['CGAT_TEST_UNRESOLVED']).exists():
    (out/'process.log').write_text('ExtensionRound 1\nNo supporting reads.\n')
    sys.exit(0)
(out/'process.log').write_text('ExtensionRound 1\nGAP can be closed!\ntotalExtensionLength: 2\n')
(out/'child.final.fa').write_text('>candidate\n' + ('AAAAGTCCCC' if '.1.' in out.name else 'CCCCTTGGGG') + '\n')
'''
PARENT = r'''
import argparse, json
from pathlib import Path
from Bio import SeqIO
from AutoGapfillerPart3 import JobManager, JobExecutor
parser = argparse.ArgumentParser()
for name in ('genome','output','thread','work'):
    parser.add_argument('--'+name)
parser.add_argument('--hifi', nargs='+')
args = parser.parse_args()
root = Path(args.output); root.mkdir(parents=True)
prep = root/'01.reads_preprocessor'; (prep/'processed_reads').mkdir(parents=True)
fasta = prep/'processed_reads/hifi_reads.fa'
fasta.write_bytes(Path(args.hifi[0]).read_bytes())
index = SeqIO.index_db(str(prep/'hifi_reads.idx'), str(fasta), 'fasta'); index.close()
(prep/'HiFi.reads.stat').write_text('Number\t1\nTolalLenth\t10\n')
(prep/'preprocessing_config.json').write_text(json.dumps({'hifi_fasta':str(fasta)}))
detection = root/'02.gap_detection'; data = detection/'gapData'; data.mkdir(parents=True)
gaps = []
for i, (start,left,right) in enumerate(((4,'AAAA','CCCC'),(28,'CCCC','GGGG')),1):
    gaps.append({'id':i,'start':start,'end':start+19,'gap_len':20,'left_len':4,'right_len':4})
    (data/f'chr1.{i}.left.fasta').write_text('>left\n'+left+'\n')
    (data/f'chr1.{i}.right.fasta').write_text('>right\n'+right+'\n')
(detection/'gap_detection_config.json').write_text(json.dumps({'gap_data_dir':str(data),
    'gaps_by_chromosome':{'chr1':{'count':2,'gaps':gaps}}}))
JobManager(root, {'hifi':args.hifi, 'thread':args.thread}).setup_jobs()
result = JobExecutor(root, workers=int(args.work)).execute_jobs()
(root/'autogapfiller_summary.json').write_text(json.dumps({'steps':{'step3':{'result':result}}}))
final = root/'04.genome_integration/genome.filled.fasta'; final.parent.mkdir()
final.write_text('>chr1\nAAAAGTCCCCTTGGGG\n')
'''


@unittest.skipUnless(multiprocessing.get_start_method() == "fork" and importlib.util.find_spec("Bio"),
                     "requires Linux fork and BioPython for controlled prepared-read indices")
class DegapUnitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/"workspace"
        initialize_workspace(self.root)
        runtime = Path(temporary.name)/"controlled"
        runtime.mkdir()
        native = Path(checkpoint.__file__).parent/"degap_core/bin/AutoGapfillerPart3.py"
        manifest_path = native.parent.parent / "SOURCE.json"
        self.assertEqual(units.digest(manifest_path),load_lock()["tools"]["degap"]["manifest_sha256"])
        self.assertEqual(units.digest(native),json.loads(manifest_path.read_text())["files"]["bin/AutoGapfillerPart3.py"])
        shutil.copyfile(native, runtime/native.name)
        self.assertEqual(units.digest(native), units.digest(runtime/native.name))
        self.entrypoint = runtime/"AutoGapfiller.py"; self.entrypoint.write_text(PARENT)
        (runtime/"DEGAP.py").write_text(CHILD)
        bin_dir = runtime/"bin"; bin_dir.mkdir(); (bin_dir/"python").symlink_to(sys.executable)
        self.bin = bin_dir
        self.reads = self.root/"reads.fa"; self.reads.write_text(">r\nAAAAGTCCCC\n")
        self.calls, self.fail, self.unresolved = (self.root/name for name in ("calls.txt","fail","unresolved"))
        self.runtime_sha = fingerprint({"pinned_part3":units.digest(native), "parent":units.digest(self.entrypoint),
                                        "controlled_child":units.digest(runtime/"DEGAP.py")})

    def execute(self, number, *, threads=2):
        run_id = str(number)*32
        base = self.root/"04_refinement/01_degap"
        paths = {name:base/name/run_id for name in ("01_inputs","02_jobs","03_native")}
        for name in ("01_inputs","02_jobs"):
            paths[name].mkdir(parents=True)
        baseline = paths["01_inputs"]/"baseline.fa"
        baseline.write_text(">chr1\nAAAA"+"N"*20+"CCCC"+"N"*20+"GGGG\n")
        command = (sys.executable,"-B",str(self.entrypoint),"--genome",str(baseline),"--output",str(paths["03_native"]),
                   "--work","1","--thread",str(threads),"--hifi",str(self.reads))
        environment = dict(os.environ, PATH=str(self.bin)+os.pathsep+os.environ['PATH'], PYTHONDONTWRITEBYTECODE="1",
                           CGAT_TEST_CALLS=str(self.calls),CGAT_TEST_FAIL=str(self.fail),CGAT_TEST_UNRESOLVED=str(self.unresolved))
        invocation = Invocation("degap",command,paths["03_native"].parent,environment,
            ("03.gap_filling/gap_filling_results.json","04.genome_integration/genome.filled.fasta"),{"threads":threads,"name":"controlled-pinned-scheduler"})
        recipe = {"threads":threads,"runtime_sha256":self.runtime_sha,
                  "reads":[{"path":str(self.reads),"sha256":units.digest(self.reads)}],
                  "baseline_sha256":units.digest(baseline),"baseline_final_path_sha256":"controlled-final-path",
                  "baseline_source_files":{"controlled":"unchanged"}}
        self.last = (invocation, paths)
        return checkpoint.execute(self.root,invocation,recipe,paths,{"run_id":run_id,"threads":threads,"timing":{}},
                                  {},lambda:None,chromosomes=["chr1"],parameters={},
                                  input_hashes={str(path):units.digest(path) for path in (baseline,self.reads)},prepared_files=[])

    def summary(self, number):
        jobs = self.root/"04_refinement/01_degap/02_jobs"/(str(number)*32)
        return jobs, units.checked_json(self.root,jobs/units.SUMMARY)

    def test_generated_input_binding_preserves_unicode_and_absent_native_flanks(self):
        native = self.root / "04_refinement/01_degap/03_native" / ("1"*32)
        (native/"01.reads_preprocessor").mkdir(parents=True)
        name = "染色体:1.1.left"
        directory = native/"03.gap_filling"/name
        directory.mkdir(parents=True)
        (directory/"seqright.fasta").write_text(">right\nCCCC\n")
        argv = ["python",str(self.entrypoint.with_name("DEGAP.py")),"--mode","gapfiller","--out",str(directory),
                "--seqleft",str(directory/"seqleft.fasta"),"--seqright",str(directory/"seqright.fasta"),"--flag","left"]
        script = directory/"run.sh"
        script.write_text("#!/bin/bash\n"+" ".join(argv)+"\n")
        job = {"job_name":name,"job_dir":str(directory),"direction":"left"}
        _, _, facts, _ = input_binding(self.root,native,job)
        self.assertEqual(facts["flanks/seqleft.fasta"],{"missing":True})
        self.assertEqual(facts["flanks/seqright.fasta"]["sha256"],units.digest(directory/"seqright.fasta"))
        script.write_text(script.read_text()+"echo unexpected second command\n")
        with self.assertRaisesRegex(PathError,"exactly one"):
            input_binding(self.root,native,job)
        script.write_text("#!/bin/bash\n"+" ".join(argv)+"\n")
        target = self.root/"unexpected_prepared_target"; target.mkdir()
        (native/"01.reads_preprocessor/input_alias").symlink_to(target,target_is_directory=True)
        (directory/"input_alias").symlink_to(target,target_is_directory=True)
        with self.assertRaisesRegex(PathError,"symlink"):
            input_binding(self.root,native,job)

    def test_completed_left_is_reused_and_still_present_in_native_summary(self):
        self.fail.touch()
        with self.assertRaisesRegex(PathError,"child processes failed"):
            self.execute(1)
        jobs, first = self.summary(1)
        self.assertEqual([row["unit"]["job_name"] for row in first["units"]],["chr1.1.left"])
        self.assertFalse((jobs/"native_complete.json").exists())
        original = self.root/first["units"][0]["receipt"]
        raw = original.read_bytes()
        diagnostics, _, _ = native_diagnostics(self.root,"degap","1"*32,{})
        self.assertIn(first["units"][0]["receipt"],diagnostics)
        self.fail.unlink()
        completed = self.execute(2)
        _, second = self.summary(2)
        by_job = {row["unit"]["job_name"]:row for row in second["units"]}
        self.assertTrue(by_job["chr1.1.left"]["reused"])
        self.assertFalse(by_job["chr1.2.left"]["reused"])
        self.assertEqual(self.calls.read_text().splitlines(),["chr1.1.left","chr1.2.left","chr1.2.right","chr1.2.left"])
        jobs = {row["job_name"]:row for row in completed["result"]["native_jobs"]["jobs"]}
        self.assertEqual(len(jobs),4)
        self.assertEqual(jobs["chr1.1.left"]["status"],"success")
        self.assertTrue(jobs["chr1.1.left"]["cgat_native_unit"]["reused"])
        self.assertEqual(jobs["chr1.1.right"]["status"],"skipped")
        self.assertEqual(jobs["chr1.2.right"]["status"],"skipped")
        self.assertEqual(raw,original.read_bytes())
        count = self.calls.read_text()
        whole = self.execute(3,threads=8)
        self.assertTrue(whole["reused"])
        self.assertEqual(whole["run_id"],"2"*32)
        self.assertEqual(count,self.calls.read_text())

    def test_zero_exit_unresolved_left_remains_unresolved_and_schedules_right(self):
        self.unresolved.touch(); self.fail.touch()
        with self.assertRaisesRegex(PathError,"child processes failed"):
            self.execute(1)
        self.fail.unlink()
        completed = self.execute(2)
        second = self.summary(2)[1]
        by_job = {row["unit"]["job_name"]:row for row in second["units"]}
        self.assertTrue(by_job["chr1.1.left"]["reused"])
        self.assertTrue(by_job["chr1.1.right"]["reused"])
        self.assertEqual(by_job["chr1.1.left"]["result"]["outcome"],"completed_without_native_fill")
        jobs = {row["job_name"]:row for row in completed["result"]["native_jobs"]["jobs"]}
        self.assertEqual(jobs["chr1.1.left"]["status"],"failed")
        self.assertEqual(jobs["chr1.1.left"]["error"],NO_FILL)
        self.assertEqual(jobs["chr1.1.right"]["status"],"success")
        self.assertEqual(self.calls.read_text().splitlines().count("chr1.1.left"),1)
        self.assertEqual(self.calls.read_text().splitlines().count("chr1.1.right"),1)

    def test_changed_reads_threads_or_corrupted_producer_do_not_reuse(self):
        self.fail.touch()
        with self.assertRaises(PathError):
            self.execute(1)
        receipt = self.root/self.summary(1)[1]["units"][0]["receipt"]
        (receipt.parent/"outputs/process.log").write_text("tampered\n")
        with self.assertRaises(PathError):
            self.execute(2)
        self.assertFalse(self.summary(2)[1]["units"][0]["reused"])
        with self.assertRaises(PathError):
            self.execute(3,threads=4)
        self.assertFalse(self.summary(3)[1]["units"][0]["reused"])
        self.reads.write_text(">r\nCCCCAAAA\n")
        with self.assertRaises(PathError):
            self.execute(4)
        self.assertFalse(self.summary(4)[1]["units"][0]["reused"])

    def test_ambiguous_native_final_choice_is_retained_but_not_partially_reused(self):
        child = self.entrypoint.with_name("DEGAP.py")
        child.write_text(child.read_text() + "\n(out/'alternative.final.fa').write_text('>alternative\\nAAAAGGCCCC\\n')\n")
        self.runtime_sha = fingerprint({"controlled_multiple_final_child":units.digest(child),"runtime":self.runtime_sha})
        self.fail.touch()
        with self.assertRaisesRegex(PathError,"child processes failed"):
            self.execute(1)
        first = self.summary(1)[1]
        self.assertFalse(first["units"][0]["result"]["recoverable"])
        self.fail.unlink()
        completed = self.execute(2)
        self.assertEqual(completed["result"]["native_jobs"]["hard_failures"],[])
        self.assertTrue(all(not row["reused"] for row in self.summary(2)[1]["units"]))
        self.assertEqual(self.calls.read_text().splitlines().count("chr1.1.left"),2)

    def test_completion_requires_all_executed_children_and_consumed_files(self):
        self.execute(1)
        invocation, paths = self.last
        jobs, summary = self.summary(1)
        native_summary = paths["03_native"] / "autogapfiller_summary.json"
        raw = native_summary.read_bytes()
        changed = json.loads(raw)
        changed["steps"]["step3"]["result"]["skipped_jobs"][0]["reason"] = "unknown skip"
        native_summary.write_text(json.dumps(changed))
        with self.assertRaisesRegex(PathError,"skipped child"):
            checkpoint.capture(self.root,"degap","1"*32,paths["03_native"],invocation,0,jobs/"native.log",["chr1"],{},[],None)
        native_summary.write_bytes(raw)
        config = paths["03_native"] / "03.gap_filling/job_manager_config.json"
        config_raw = config.read_bytes()
        changed = json.loads(config_raw)
        changed["jobs"][0]["gap_info"]["start"] += 1
        config.write_text(json.dumps(changed))
        with self.assertRaisesRegex(PathError,"geometry"):
            checkpoint.capture(self.root,"degap","1"*32,paths["03_native"],invocation,0,jobs/"native.log",["chr1"],{},[],None)
        config.write_bytes(config_raw)
        summary["units"].pop()
        units.seal(jobs/units.SUMMARY,summary)
        with self.assertRaisesRegex(PathError,"every attempted"):
            checkpoint.capture(self.root,"degap","1"*32,paths["03_native"],invocation,0,jobs/"native.log",["chr1"],{},[],None)
        receipt = self.root/summary["units"][0]["receipt"]
        value = units.checked_json(self.root,receipt)
        (self.root/value["consumed_job"]/"process.log").write_text("changed after consumer\n")
        with self.assertRaisesRegex(PathError,"consumed"):
            units.capture_units(self.root,"degap","1"*32,0,required=True)


if __name__ == "__main__":
    unittest.main()
