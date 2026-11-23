"""Exact pinned TGS shell driver, controlled native binaries; not engine acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import refinement_native_checkpoint as checkpoint
import refinement_native_units as units
import refinement_tgs_units as tgs
from refinement_path import PathError
from refinement_recipes import Invocation
from refinement_tools import load_lock,fingerprint
from refinement_reports import native_diagnostics, asset_plan
from workspace_layout import initialize_workspace

HELPER = r'''
import os,sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
def option(flag): return args[args.index(flag)+1]
if name in ('minimap2','racon'):
    target = Path(os.readlink('/proc/self/fd/1')).name
    with Path(os.environ['CGAT_TEST_TGS_CALLS']).open('a') as out:
        out.write(name+':'+target+'\n')
    gate = Path(os.environ['CGAT_TEST_TGS_FAIL'])
    if gate.exists() and gate.read_text().strip() == target:
        print('controlled native exit 7',file=sys.stderr); sys.exit(7)
    if name == 'minimap2':
        print('1\t4\t0\t4\t+\tr1\t10\t0\t4\t4\t4\t60')
    else:
        sys.stdout.buffer.write(Path(args[-1]).read_bytes())
    print('controlled '+name+' diagnostic',file=sys.stderr)
    sys.exit(0)
if name == 'tgsgapcandidate':
    for i in range(3): print('>r'+str(i)+'\nAAAAGTCCCC')
    sys.exit(0)
prefix = Path(option('--prefix'))
if name == 'tgsseqsplit':
    Path(str(prefix)+'.contig').write_text('>1\nAAAA\n>2\nCCCC\n')
    Path(str(prefix)+'.name_map').write_text('1\tchr1\n')
    Path(str(prefix)+'.orignial_scaff_infos').write_text('>scaffold 1\n1\t+\t100\t4\t1\t1\t1\n2\t+\t0\t4\t105\t2\t1\n')
elif name == 'tgsgapcloser':
    gate = Path(os.environ['CGAT_TEST_TGS_FAIL'])
    if gate.exists() and gate.read_text().strip() == 'gapcloser': sys.exit(7)
    Path(str(prefix)+'.updated_scaff_infos').write_text('>scaffold 1\n1\t+\t2\t4\t1\t1\t1\tONT_FILL=GT\n2\t+\t0\t4\t105\t2\t1\n')
elif name == 'tgsseqgen':
    Path(str(prefix)+'.scaff_seqs').write_text('>chr1\nAAAAGTCCCC\n')
    Path(str(prefix)+'.gap_fill_detail').write_text('>chr1\n1\t4\tS\t1\t4\n5\t6\tF\n7\t10\tS\t105\t108\n')
else: sys.exit(9)
'''


class TgsUnitFormatTests(unittest.TestCase):
    def test_stable_stream_validation_starts_after_both_descriptors_flush(self):
        trace = []
        def parse(kind, path):
            trace.append((kind, path))
            return {"outcome": "corrected_fasta"}
        with patch.object(tgs.os, "fsync", side_effect=trace.append), patch.object(tgs, "stream_result", side_effect=parse):
            output = Path("tgs.ont.0.0.racon.fasta")
            self.assertEqual(tgs.persisted_stream_result("racon", output), {"outcome": "corrected_fasta"})
            self.assertEqual(trace, [1, 2, ("racon", output)])
        with patch.object(tgs.os, "fsync", side_effect=OSError("flush failed")), patch.object(tgs, "stream_result") as parse:
            with self.assertRaisesRegex(OSError, "flush failed"):
                tgs.persisted_stream_result("racon", output)
            parse.assert_not_called()

    def test_owned_command_wrappers_are_server_only_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initialize_workspace(root)
            relative = "04_refinement/02_tgsgapcloser/02_jobs/"+"1"*32+"/native_commands/minimap2"
            wrapper = root/relative; wrapper.parent.mkdir(parents=True); wrapper.write_text("#!/bin/sh\nexit 0\n")
            row = asset_plan(root,{relative:units.digest(wrapper)})[0]
            self.assertEqual(row["availability"],"server_only_native_script")
            self.assertNotIn("report_path",row)

    def test_native_no_cigar_policy_does_not_weaken_quartet(self):
        with tempfile.TemporaryDirectory() as directory:
            paf = Path(directory)/"native.paf"
            paf.write_text("q\t4\t0\t4\t+\tr\t10\t0\t4\t4\t4\t60\n")
            self.assertEqual(tgs.stream_result("minimap2",paf)["records"],1)
            with self.assertRaises(PathError): units.validate_paf(paf,allow_empty=True)
            paf.write_text(paf.read_text()+"malformed\n")
            with self.assertRaises(PathError): tgs.stream_result("minimap2",paf)


@unittest.skipUnless(sys.platform.startswith("linux") and os.environ.get("CGAT_TEST_TGS_ARCHIVE"),
                     "opt-in exact pinned TGS package driver with controlled binaries")
class TgsUnitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)/"workspace"; initialize_workspace(self.root)
        self.bin = Path(tmp.name)/"controlled/bin"; self.bin.mkdir(parents=True)
        archive = Path(os.environ["CGAT_TEST_TGS_ARCHIVE"])
        definition = load_lock()["tools"]["tgsgapcloser"]
        self.assertIn(units.digest(archive),{row["sha256"] for row in definition["packages"].values()})
        with tarfile.open(archive) as package:
            source = package.extractfile("bin/tgsgapcloser").read()
        self.assertEqual(hashlib.sha256(source).hexdigest(),tgs.SOURCE_SHA)
        (self.bin/"tgsgapcloser").write_bytes(source)
        (self.bin/"python").symlink_to(sys.executable)
        (self.bin/"tgsgapcloserbin").mkdir()
        for name in ("minimap2","racon","tgsgapcloserbin/tgsseqsplit","tgsgapcloserbin/tgsgapcandidate",
                     "tgsgapcloserbin/tgsgapcloser","tgsgapcloserbin/tgsseqgen"):
            path = self.bin/name; path.write_text("#!"+sys.executable+"\n"+HELPER); path.chmod(0o755)
        self.reads = self.root/"reads.fa"; self.reads.write_text(">r1\nAAAAGTCCCC\n")
        self.calls,self.fail = self.root/"calls.txt",self.root/"fail"
        self.runtime = fingerprint({"source":tgs.SOURCE_SHA,"controlled_helper":HELPER})

    def execute(self, number, *, mode="ont", threads=2):
        run_id = str(number)*32
        base = self.root/"04_refinement/02_tgsgapcloser"
        paths = {name:base/name/run_id for name in ("01_inputs","02_jobs","03_native")}
        for name in ("01_inputs","02_jobs"): paths[name].mkdir(parents=True)
        baseline = paths["01_inputs"]/"baseline.fa"; baseline.write_text(">chr1\nAAAA"+"N"*100+"CCCC\n")
        command = ["/bin/bash",str(self.bin/"tgsgapcloser"),"--scaff",str(baseline),"--reads",str(self.reads),
                   "--output",str(paths["03_native"]/"tgs"),"--thread",str(threads),"--tgstype","pb" if mode=="hifi" else "ont",
                   "--minmap_arg"," -x asm20" if mode=="hifi" else " -x ava-ont"]
        command += ["--ne"] if mode=="hifi" else ["--racon",str(self.bin/"racon"),"--r_round","1"]
        env = dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],PYTHONDONTWRITEBYTECODE="1",
                   CGAT_TEST_TGS_CALLS=str(self.calls),CGAT_TEST_TGS_FAIL=str(self.fail))
        invocation = Invocation("tgsgapcloser",tuple(command),paths["03_native"],env,
            ("tgs.scaff_seqs","tgs.updated_scaff_infos","tgs.orignial_scaff_infos","tgs.name_map","tgs.gap_fill_detail"),
            {"name":"controlled-pinned-TGS-driver","threads":threads,"mode":mode})
        recipe = {"threads":threads,"runtime_sha256":self.runtime,"reads":[{"path":str(self.reads),"sha256":units.digest(self.reads)}],
                  "baseline_sha256":units.digest(baseline),"baseline_final_path_sha256":"controlled-final-path",
                  "baseline_source_files":{"controlled":"unchanged"}}
        self.last = invocation,paths
        return checkpoint.execute(self.root,invocation,recipe,paths,{"run_id":run_id,"threads":threads,"timing":{}},
                                  {},lambda:None,chromosomes=["chr1"],parameters={},
                                  input_hashes={str(path):units.digest(path) for path in (baseline,self.reads)},prepared_files=[str(self.reads)])

    def summary(self, number):
        jobs = self.root/"04_refinement/02_tgsgapcloser/02_jobs"/(str(number)*32)
        return jobs,units.checked_json(self.root,jobs/units.SUMMARY)

    def test_ont_chunk_commands_reuse_without_skipping_native_loops(self):
        self.fail.write_text("tgs.fill.paf")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1)
        jobs,first = self.summary(1)
        self.assertEqual(len(first["units"]),7)
        self.assertFalse((jobs/"native_complete.json").exists())
        original = {path:path.read_bytes() for row in first["units"] for path in [self.root/row["receipt"]]}
        diagnostics,_,_ = native_diagnostics(self.root,"tgsgapcloser","1"*32,{})
        self.assertIn(first["units"][0]["receipt"],diagnostics)
        self.fail.unlink()
        completed = self.execute(2)
        _,second = self.summary(2)
        self.assertEqual(len(second["units"]),8)
        self.assertEqual(sum(row["reused"] for row in second["units"]),7)
        self.assertEqual(len(self.calls.read_text().splitlines()),9)
        self.assertTrue(all(path.read_bytes()==raw for path,raw in original.items()))
        self.assertEqual(completed["execution"]["native_substeps"]["reused"],7)
        self.assertTrue((self.last[1]["03_native"]/"done_step_4.2_tag").exists())
        self.assertFalse((self.last[1]["03_native"]/"tgs.sub.paf").exists())
        before = self.calls.read_bytes()
        self.assertTrue(self.execute(3,threads=8)["reused"])
        self.assertEqual(before,self.calls.read_bytes())

    def test_hifi_empty_mapping_is_reused_after_later_native_failure(self):
        real = shutil.which("minimap2")
        if not real: self.skipTest("developer minimap2 required")
        mapper = self.bin/"minimap2"
        mapper.write_text("#!"+sys.executable+"\nimport os,sys\nfrom pathlib import Path\n"+
            "with Path(os.environ['CGAT_TEST_TGS_CALLS']).open('a') as out: out.write('actual-minimap2\\n')\n"+
            "os.execv("+repr(real)+",["+repr(real)+",*sys.argv[1:]])\n")
        self.runtime = fingerprint({"driver":tgs.SOURCE_SHA,"developer_minimap2":units.digest(Path(real))})
        self.fail.write_text("gapcloser")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1,mode="hifi")
        self.assertEqual(self.summary(1)[1]["units"][0]["result"]["outcome"],"empty_alignment")
        self.fail.unlink(); self.execute(2,mode="hifi")
        self.assertTrue(self.summary(2)[1]["units"][0]["reused"])
        self.assertEqual(self.calls.read_text().splitlines(),["actual-minimap2"])
        # A new consumer must never share a mutable inode with historical bytes.
        old = self.root/self.summary(1)[1]["units"][0]["receipt"]
        old_bytes = (old.parent/"stdout.paf").read_bytes()
        new = self.root/self.summary(2)[1]["units"][0]["receipt"]
        (new.parent/"stdout.paf").write_text("changed new consumer")
        self.assertEqual((old.parent/"stdout.paf").read_bytes(),old_bytes)

    def test_current_inputs_and_corrupted_streams_cannot_reuse(self):
        self.fail.write_text("gapcloser")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1,mode="hifi")
        receipt = self.root/self.summary(1)[1]["units"][0]["receipt"]
        (receipt.parent/"stdout.paf").write_text("corrupted")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(2,mode="hifi")
        self.assertFalse(self.summary(2)[1]["units"][0]["reused"])
        self.reads.write_text(">r1\nCCCCAAAA\n")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(3,mode="hifi")
        self.assertFalse(self.summary(3)[1]["units"][0]["reused"])
        with self.assertRaises(subprocess.CalledProcessError): self.execute(4,mode="hifi",threads=4)
        self.assertFalse(self.summary(4)[1]["units"][0]["reused"])

    def test_native_completion_requires_every_phase_and_unchanged_driver(self):
        self.execute(1)
        invocation,paths = self.last
        jobs,summary = self.summary(1)
        with self.assertRaisesRegex(PathError,"live attempt"):
            tgs.TgsUnits(units.checked_json(self.root,jobs/units.REQUEST)).live_owner()
        summary["units"].pop(); units.seal(jobs/units.SUMMARY,summary)
        with self.assertRaisesRegex(PathError,"every expected"):
            units.capture_units(self.root,"tgsgapcloser","1"*32,0,required=True)
        driver = jobs/"native_driver.sh"; driver.write_text(driver.read_text()+"\n# changed\n")
        with self.assertRaisesRegex(PathError,"driver/wrapper changed"):
            units.capture_units(self.root,"tgsgapcloser","1"*32,0,required=True)


if __name__ == "__main__": unittest.main()
