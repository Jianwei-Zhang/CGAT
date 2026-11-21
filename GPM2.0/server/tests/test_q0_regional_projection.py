from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from server.tools.lgz_core.common import write_fasta
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_query_windows import QueryWindow, TargetWindow, project_regional_paf
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError


class RegionalProjectionTests(unittest.TestCase):
    def setUp(self):
        self.query=QueryWindow("qpart",1000,100,160,((110,130),))
        self.target=TargetWindow("tpart",2000,500,700)

    def line(self,strand="+",target=None):
        target=target or self.target
        return f"{self.query.window_id}\t60\t0\t40\t{strand}\t{target.window_id}\t{target.length}\t20\t60\t40\t40\t60\tcg:Z:40M\ttp:A:P\ts1:i:40"

    def project(self,line,target=None):
        target=target or self.target
        return project_regional_paf(line,{self.query.window_id:self.query},{target.window_id:target},artifact="raw.paf",line_number=1)

    def test_both_forward_coordinate_offsets_and_unknown_confidence(self):
        for strand in ("+","-"):
            result=self.project(self.line(strand))
            hit=parse_paf_line(result,artifact="projected",line_number=1)
            self.assertEqual((hit.query_name,hit.query_length,hit.query),("qpart",1000,Interval(100,140)))
            self.assertEqual((hit.target_name,hit.target_length,hit.target),("tpart",2000,Interval(520,560)))
            self.assertEqual(hit.strand,strand);self.assertIsNone(hit.mapping_quality)
            self.assertEqual({t.split(":")[0] for t in hit.tags},{"cg","qw","tw"})

    def test_original_self_and_context_only_excluded_but_malformed_rejected(self):
        own=TargetWindow("qpart",1000,500,700)
        self.assertIsNone(self.project(self.line(target=own),target=own))
        raw=self.line().replace("\t0\t40\t+","\t0\t5\t+").replace("\t20\t60\t40\t40\t","\t20\t25\t5\t5\t").replace("40M","5M")
        self.assertIsNone(self.project(raw))
        for raw in (self.line()+"\ttw:Z:already",self.line().replace("40M","41M"),self.line().replace("\t200\t20","\t201\t20")):
            with self.assertRaises(Q0EvidenceError):self.project(raw)
        with self.assertRaises(Q0EvidenceError):TargetWindow("bad",100,99,101)

    def test_real_mapper_dual_windows_keep_controlled_paired_coordinates(self):
        mapper=shutil.which("minimap2")
        if mapper is None:self.skipTest("requires minimap2")
        rng=random.Random(2112026);source="".join(rng.choices("ACGT",k=30000))
        prefix="".join(rng.choices("ACGT",k=500));suffix="".join(rng.choices("ACGT",k=500))
        q=QueryWindow("q",len(source),8500,12500,((9000,12000),))
        for strand in ("+","-"):
            middle=source[8500:12500]
            if strand=="-":middle=middle.translate(str.maketrans("ACGT","TGCA"))[::-1]
            target=prefix+middle+suffix;t=TargetWindow("t",len(target),400,4600)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                write_fasta(root/"wholeq.fa",[("q",source)]);write_fasta(root/"wholet.fa",[("t",target)])
                write_fasta(root/"q.fa",[(q.window_id,source[q.start:q.end])]);write_fasta(root/"t.fa",[(t.window_id,target[t.start:t.end])])
                controls=None
                for mode,flags in [("whole",["-P"]),("window-all",["-P"]),("window-ranked",["-p","0","-N","100"])]:
                    whole=mode=="whole";qp=root/("wholeq.fa" if whole else "q.fa");tp=root/("wholet.fa" if whole else "t.fa")
                    result=subprocess.run([mapper,"-c","-x","asm10","-D",*flags,"--dual=yes","--no-long-join","-t","1",str(tp),str(qp)],capture_output=True,text=True,check=True)
                    pairs=set()
                    for i,line in enumerate(result.stdout.splitlines(),1):
                        projected=line if whole else project_regional_paf(line,{q.window_id:q},{t.window_id:t},artifact=mode,line_number=i)
                        if projected is None:continue
                        hit=parse_paf_line(projected,artifact=mode,line_number=i)
                        for block in hit.aligned_blocks():
                            for position in range(max(9000,block.query.start),min(12000,block.query.end)):
                                dest=block.target.start+position-block.query.start if strand=="+" else block.target.start+block.query.end-position-1
                                pairs.add((position,dest))
                    if whole:controls=pairs;self.assertEqual(len(controls),3000)
                    else:self.assertEqual(pairs,controls)


if __name__=="__main__":unittest.main()
