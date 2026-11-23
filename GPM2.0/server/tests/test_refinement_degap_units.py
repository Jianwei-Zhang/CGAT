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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_native_checkpoint as checkpoint
import refinement_native_units as units
import refinement_degap_units as degap_units
from refinement_degap_units import input_binding
from run_orchestration import OrchestrationContractError
from refinement_path import PathError
from refinement_recipes import Invocation
from refinement_reports import native_diagnostics
from refinement_tools import fingerprint, load_lock
from workspace_layout import initialize_workspace

CHILD = r'''
import argparse, hashlib, json, os, sys
from pathlib import Path
parser = argparse.ArgumentParser(); parser.add_argument('--out')
args, _ = parser.parse_known_args(); out = Path(args.out)
with Path(os.environ['CGAT_TEST_CALLS']).open('a') as stream:
    stream.write(out.name + '\n')
if '.2.' in out.name and Path(os.environ['CGAT_TEST_FAIL']).exists():
    print('controlled exit 7', file=sys.stderr)
    sys.exit(7)
closed = not ('.1.' in out.name and Path(os.environ['CGAT_TEST_UNRESOLVED']).exists())
seq = 'AAAAGTCCCC' if '.1.' in out.name else 'CCCCTTGGGG'
final = out.name + '.final.fa'
outputs = {final: '>candidate\n'+seq+'\n', 'family-components.fa': '>flank\nAAAA\n',
    'process.agp': '# controlled\n', 'process.log': 'controlled family search\n', 'process.summary': 'controlled\n',
    'family-report.html': '<html>controlled</html>', 'connection-diagnostics.json': '[]\n'}
for name, text in outputs.items():
    (out/name).write_text(text)
value = {'schema':'degap-family-result-v1', 'status':'closed' if closed else 'exhausted',
    'winner': {} if closed else None, 'final_sequence':final, 'total_rounds':1, 'gap_length':2 if closed else 0,
    'families': [{'key':'L','stop_reason': None}, {'key':'R','stop_reason': None}],
    'artifacts':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in outputs}}
value['payload_sha256'] = hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
(out/'family-result.json').write_text(json.dumps(value))

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
for i, (start,left,right) in enumerate(((5,'AAAA','CCCC'),(29,'CCCC','GGGG')),1):
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
class PreparedIndexTest(unittest.TestCase):
    def test_retries_only_unstable_hash_and_requires_a_stable_result(self):
        error = OrchestrationContractError("file changed while hashing: hifi_reads.idx")
        stable = ({"sha256": "a" * 64, "bytes": 20}, (1, 2, 20, 3, 4))
        with patch.object(degap_units.time, "sleep"), patch.object(degap_units, "file_fact", side_effect=[error, stable]) as read:
            self.assertEqual(degap_units.prepared_index_fact(Path("hifi_reads.idx")), stable)
            self.assertEqual(read.call_count, 2)
        with patch.object(degap_units.time, "sleep"), patch.object(degap_units, "file_fact", side_effect=error) as read:
            with self.assertRaisesRegex(OrchestrationContractError, "changed while hashing"):
                degap_units.prepared_index_fact(Path("ont_reads.idx"))
            self.assertEqual(read.call_count, 4)
        with patch.object(degap_units, "file_fact", side_effect=PermissionError) as read:
            with self.assertRaises(PermissionError):
                degap_units.prepared_index_fact(Path("ont_reads.idx"))
            self.assertEqual(read.call_count, 1)


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
        shutil.copytree(native.parent, runtime, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        self.assertEqual(units.digest(native), units.digest(runtime/native.name))
        self.entrypoint = runtime/"AutoGapfiller.py"; self.entrypoint.write_text(PARENT)
        (runtime/"DEGAP.py").write_text(CHILD)
        bin_dir = runtime/"bin"; bin_dir.mkdir(); (bin_dir/"python").symlink_to(sys.executable)
        self.bin = bin_dir
        self.reads = self.root/"reads.fa"; self.reads.write_text(">r\nAAAAGTCCCC\n")
        self.calls, self.fail_marker, self.unresolved = (self.root/name for name in ("calls.txt","fail","unresolved"))
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
                           CGAT_TEST_CALLS=str(self.calls),CGAT_TEST_FAIL=str(self.fail_marker),CGAT_TEST_UNRESOLVED=str(self.unresolved))
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

    def test_completed_family_is_reused_and_still_present_in_native_summary(self):
        self.fail_marker.touch()
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(1)
        jobs, first = self.summary(1)
        self.assertEqual([row["unit"]["job_name"] for row in first["units"]], ["chr1.1.bidirectional"])
        self.assertFalse((jobs/"native_complete.json").exists())
        original = self.root/first["units"][0]["receipt"]
        raw = original.read_bytes()
        diagnostics, _, _ = native_diagnostics(self.root, "degap", "1"*32, {})
        self.assertIn(first["units"][0]["receipt"], diagnostics)
        self.fail_marker.unlink()
        completed = self.execute(2)
        by_job = {row["unit"]["job_name"]: row for row in self.summary(2)[1]["units"]}
        self.assertTrue(by_job["chr1.1.bidirectional"]["reused"])
        self.assertFalse(by_job["chr1.2.bidirectional"]["reused"])
        self.assertEqual(self.calls.read_text().splitlines(), ["chr1.1.bidirectional", "chr1.2.bidirectional", "chr1.2.bidirectional"])
        by_job = {row["job_name"]: row for row in completed["result"]["native_jobs"]["jobs"]}
        self.assertEqual(len(by_job), 2)
        self.assertTrue(by_job["chr1.1.bidirectional"]["cgat_native_unit"]["reused"])
        self.assertEqual(raw,original.read_bytes())
        self.assertTrue(self.execute(3,threads=8)["reused"])

    def test_zero_exit_exhausted_family_is_reusable_not_a_candidate_or_a_second_job(self):
        self.unresolved.touch(); self.fail_marker.touch()
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(1)
        self.fail_marker.unlink()
        completed = self.execute(2)
        by_job = {row["unit"]["job_name"]:row for row in self.summary(2)[1]["units"]}
        row = by_job["chr1.1.bidirectional"]
        self.assertTrue(row["reused"])
        self.assertEqual(row["result"]["outcome"], "completed_without_native_fill")
        jobs = {row["job_name"]:row for row in completed["result"]["native_jobs"]["jobs"]}
        self.assertEqual(jobs["chr1.1.bidirectional"]["error"], "Family search ended: exhausted")
        self.assertEqual(self.calls.read_text().splitlines().count("chr1.1.bidirectional"), 1)

    def test_changed_reads_threads_or_corrupted_producer_do_not_reuse(self):
        self.fail_marker.touch()
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(1)
        receipt = self.root/self.summary(1)[1]["units"][0]["receipt"]
        (receipt.parent/"outputs/process.log").write_text("tampered\n")
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(2)
        self.assertFalse(self.summary(2)[1]["units"][0]["reused"])
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(3,threads=4)
        self.assertFalse(self.summary(3)[1]["units"][0]["reused"])
        self.reads.write_text(">r\nCCCCAAAA\n")
        with self.assertRaises(checkpoint.NativeProcessError):
            self.execute(4)
        self.assertFalse(self.summary(4)[1]["units"][0]["reused"])

    def test_tampered_family_manifest_and_consumer_are_refused(self):
        self.execute(1)
        run = "1"*32
        first = self.summary(1)[1]["units"][0]
        receipt = units.checked_json(self.root,self.root/first["receipt"])
        source = self.root/receipt["consumed_job"]/"family-result.json"
        source.write_text("{}")
        with self.assertRaises(PathError):
            units.capture_units(self.root,"degap",run,0,required=True)

    def test_completion_requires_all_executed_children_and_consumed_files(self):
        self.execute(1)
        invocation, paths = self.last
        jobs, summary = self.summary(1)
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
