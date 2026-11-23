"""Pinned LR driver/loop/early stop with controlled BWA and Perl helpers.

These are execution/recovery tests, not real LR/binary/biological acceptance.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import refinement_native_checkpoint as checkpoint
import refinement_native_units as units
import refinement_lr_units as lr
from refinement_path import PathError
from refinement_recipes import Invocation,materialize_native_driver
from refinement_tools import load_lock,fingerprint
from refinement_reports import native_diagnostics
from workspace_layout import initialize_workspace

PERL = r'''
use strict; use warnings;
use File::Basename qw(basename);
my $name=basename($0);
sub contents {my ($p)=@_; open(my $f,'<',$p) or die "read $p: $!"; local $/; return <$f>;}
sub save {my ($p,$s)=@_; open(my $f,'>',$p) or die "write $p: $!"; print $f $s; close($f);}
my ($iter)=(join(' ',@ARGV)=~/iteration-(\d+)/); $iter ||= 0;
my $gate=(-e $ENV{CGAT_TEST_LR_FAIL}) ? contents($ENV{CGAT_TEST_LR_FAIL}) : '';
chomp($gate);
if ($name eq 'format_fa.pl') {
  save("$ARGV[1]/LR.fasta",">LR1\nAAAAGTCCCC\n") unless $gate eq 'missing_reads';
  save("$ARGV[1]/LR_length","LR1\t10\n");
} elsif ($name eq 'change_case_fasta.pl') {print contents($ARGV[0]);
} elsif ($name eq 'tag_generator.pl') {print ">LR1_tag\n",('ACGT' x 100),"\n";
} elsif ($name eq 'coverage_calculator.pl') {
  exit 7 if $gate eq "coverage$iter";
  save($ARGV[1],"coverage\n");
} elsif ($name eq 'gap_finder.pl') {
  my $genome=contents($ARGV[0]); print "chr1(:5-104\n" if $genome =~ /N+/;
} elsif ($name eq 'find_sequnce_file.pl') {print contents($ARGV[1]);
} elsif ($name eq 'tag_distance_filter_classify.pl') {
  save("$ARGV[2]/classify_complete.txt",''); save("$ARGV[2]/classify_partial.txt",'');
} elsif ($name eq 'group_partial.pl') {
  for my $file ('group_close_1.txt','group_close_2.txt','group_open.txt') {save("$ARGV[1]/$file",'');}
} elsif ($name eq 'retriever_backfill.pl') {
  save("$ARGV[2]/retrieve_ccomplete.out",''); save("$ARGV[2]/retrieve_cclose1.out",'');
} elsif ($name eq 'info_pacify.pl') {
  print "chr1(:5-104\tLR1(:5-6(:+\tchr1(:5-104\n" if $iter > 1;
} elsif ($name eq 'form_sequence.pl') {
  open(my $calls,'>>',$ENV{CGAT_TEST_LR_CALLS}) or die $!; print $calls "form:$iter\n"; close($calls);
  exit 7 if $gate eq "$iter";
  print $iter==1 ? contents($ARGV[2]) : ">chr1\nAAAAGTCCCC\n";
}
'''
BWA = r'''
import os,sys
from pathlib import Path
args=sys.argv[1:]
if args[0]=='index':
    prefix=Path(args[args.index('-p')+1]); iteration=prefix.parent.parent.name
    for suffix in ('amb','ann','bwt','pac','sa'): Path(str(prefix)+'.'+suffix).write_bytes(Path(args[-1]).read_bytes())
else:
    iteration=Path(args[-2]).parent.parent.name
    print('@HD\tVN:1.6\n@SQ\tSN:chr1\tLN:108')
with Path(os.environ['CGAT_TEST_LR_CALLS']).open('a') as out: out.write(args[0]+':'+iteration+'\n')
'''


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("perl") and os.environ.get("CGAT_TEST_LR_DRIVER"),
                     "opt-in pinned LR shell driver with controlled binaries")
class LrUnitTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)/"workspace"; initialize_workspace(self.root)
        self.bin=Path(temporary.name)/"controlled/bin"; self.bin.mkdir(parents=True)
        self.patch=load_lock()["tools"]["lrgapcloser"]["driver_patch"]
        source=Path(os.environ["CGAT_TEST_LR_DRIVER"])
        self.assertEqual(units.digest(source),self.patch["before_sha256"])
        self.driver=source.read_bytes(); (self.bin/"LR_Gapcloser.sh").write_bytes(self.driver)
        (self.bin/"python").symlink_to(sys.executable)
        bwa=self.bin/"bwa"; bwa.write_text("#!"+sys.executable+"\n"+BWA); bwa.chmod(0o755)
        for name in set(re.findall(rb"\$program/([A-Za-z0-9_.-]+\.pl)",self.driver)):
            (self.bin/name.decode()).write_text(PERL)
        self.reads=self.root/"reads.fa"; self.reads.write_text(">raw\nAAAAGTCCCC\n")
        self.calls,self.fail=self.root/"calls.txt",self.root/"fail"
        self.runtime=fingerprint({"driver":self.patch,"controlled_bwa":BWA,"controlled_perl":PERL})

    def execute(self,number,*,threads=2):
        run_id=str(number)*32; base=self.root/"04_refinement/04_lrgapcloser"
        paths={name:base/name/run_id for name in ("01_inputs","02_jobs","03_native")}
        for name in ("01_inputs","02_jobs"): paths[name].mkdir(parents=True)
        baseline=paths["01_inputs"]/"baseline.fa"; baseline.write_text(">chr1\nAAAA"+"N"*100+"CCCC\n")
        driver=paths["02_jobs"]/"native_driver.sh"
        command=("/bin/bash","-e","-o","pipefail",str(driver),"-i",str(baseline),"-l",str(self.reads),"-s","p",
                 "-t",str(threads),"-n","1","-r","3","-o",str(paths["03_native"]/"output"))
        env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],PYTHONDONTWRITEBYTECODE="1",
                 CGAT_LR_PROGRAM_DIR=str(self.bin),CGAT_TEST_LR_CALLS=str(self.calls),CGAT_TEST_LR_FAIL=str(self.fail))
        invocation=Invocation("lrgapcloser",command,paths["03_native"],env,("iteration-1/gapclosed.fasta",),
                              {"name":"controlled-pinned-LR-driver","threads":threads,"driver_patch":self.patch})
        recipe={"threads":threads,"runtime_sha256":self.runtime,"reads":[{"path":str(self.reads),"sha256":units.digest(self.reads)}],
                "baseline_sha256":units.digest(baseline),"baseline_final_path_sha256":"controlled-final-path",
                "baseline_source_files":{"controlled":"unchanged"},"chromosome_names":{"chr1":"chr1"}}
        self.last=invocation,paths
        return checkpoint.execute(self.root,invocation,recipe,paths,{"run_id":run_id,"threads":threads,"timing":{}},
                                  {},lambda:None,chromosomes=["chr1"],parameters={"iterations":3},
                                  input_hashes={str(path):units.digest(path) for path in (baseline,self.reads)},prepared_files=[str(self.reads)],
                                  driver_factory=materialize_native_driver)

    def summary(self,number):
        jobs=self.root/"04_refinement/04_lrgapcloser/02_jobs"/(str(number)*32)
        return jobs,units.checked_json(self.root,jobs/units.SUMMARY)

    def test_completed_iteration_replays_and_native_early_stop_still_runs(self):
        self.fail.write_text("2")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1)
        jobs,first=self.summary(1)
        self.assertEqual([row["unit"]["iteration"] for row in first["units"]],[1])
        self.assertFalse((jobs/"native_complete.json").exists())
        original=self.root/first["units"][0]["receipt"]; before=original.read_bytes()
        diagnostics,_,_=native_diagnostics(self.root,"lrgapcloser","1"*32,{})
        self.assertIn(first["units"][0]["receipt"],diagnostics)
        self.fail.unlink(); complete=self.execute(2)
        _,second=self.summary(2)
        self.assertEqual([row["unit"]["iteration"] for row in second["units"]],[1,2])
        self.assertEqual([row["reused"] for row in second["units"]],[True,False])
        native=self.last[1]["03_native"]/"output"
        self.assertFalse((native/"iteration-3").exists())
        self.assertFalse((native/"LR.fasta").exists())
        self.assertFalse((native/"genome_uc.fasta").exists())
        self.assertEqual((native/"iteration-2/gapclosed.fasta").read_text(),">chr1\nAAAAGTCCCC\n")
        calls=self.calls.read_text().splitlines()
        self.assertEqual(calls.count("mem:iteration-1"),1)
        self.assertEqual(calls.count("index:iteration-1"),2) # fresh initial setup, not claimed reused.
        self.assertEqual(calls.count("form:1"),1)
        self.assertEqual(calls.count("form:2"),2)
        self.assertEqual(before,original.read_bytes())
        self.assertFalse(os.path.samefile(original.parent/"gapclosed.fasta",native/"iteration-1/gapclosed.fasta"))
        self.assertEqual(complete["execution"]["native_substeps"]["reused"],1)
        source_calls=self.calls.read_bytes()
        self.assertTrue(self.execute(3,threads=8)["reused"])
        self.assertEqual(self.calls.read_bytes(),source_calls)

    def test_restore_protocol_error_does_not_run_an_unproved_native_block(self):
        self.fail.write_text("missing_reads")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1)
        self.assertEqual(self.summary(1)[1]["units"],[])
        self.assertNotIn("mem:iteration-1",self.calls.read_text())
        self.assertNotIn("form:1",self.calls.read_text())

    def test_background_failure_is_not_hidden_by_native_bare_wait(self):
        self.fail.write_text("coverage1")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1)
        jobs,summary=self.summary(1)
        self.assertEqual(summary["units"],[])
        self.assertFalse((jobs/"native_complete.json").exists())
        self.assertNotIn("form:1",self.calls.read_text())

    def test_corrupt_outputs_changed_reads_and_threads_do_not_reuse(self):
        self.fail.write_text("2")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(1)
        receipt=self.root/self.summary(1)[1]["units"][0]["receipt"]
        (receipt.parent/"info_filter2").write_text("corrupt\n")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(2)
        self.assertFalse(self.summary(2)[1]["units"][0]["reused"])
        self.reads.write_text(">raw\nGGGGCCCC\n")
        with self.assertRaises(subprocess.CalledProcessError): self.execute(3)
        self.assertFalse(self.summary(3)[1]["units"][0]["reused"])
        with self.assertRaises(subprocess.CalledProcessError): self.execute(4,threads=4)
        self.assertFalse(self.summary(4)[1]["units"][0]["reused"])

    def test_native_completion_requires_every_iteration_and_consumed_bytes(self):
        self.execute(1); jobs,summary=self.summary(1)
        with self.assertRaisesRegex(PathError,"live native attempt"):
            lr.LrUnits(units.checked_json(self.root,jobs/units.REQUEST)).live_owner()
        summary["units"].pop(); units.seal(jobs/units.SUMMARY,summary)
        with self.assertRaisesRegex(PathError,"every completed"):
            units.capture_units(self.root,"lrgapcloser","1"*32,0,required=True)
        receipt=self.root/summary["units"][0]["receipt"]
        value=units.checked_json(self.root,receipt)
        native=self.last[1]["03_native"]/"output/iteration-1/gapclosed.fasta"
        native.write_text(">chr1\nCCCC\n")
        with self.assertRaisesRegex(PathError,"artifact changed|consumed"):
            units.capture_units(self.root,"lrgapcloser","1"*32,0,required=True)


if __name__ == "__main__": unittest.main()
