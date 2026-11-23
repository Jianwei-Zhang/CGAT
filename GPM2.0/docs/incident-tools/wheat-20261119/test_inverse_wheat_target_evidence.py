from pathlib import Path
from tempfile import TemporaryDirectory
import random
import unittest
from lgz_core.q0_alignments import read_paf
from lgz_core.q0_reference_index import ReferenceIndex
from lgz_core.q0_sources import Interval,SourceKey,split_source
from inverse_wheat_target_evidence import TargetSpans,invert,target_hit

class InverseTests(unittest.TestCase):
    def test_other_owner_and_touching_end_against_brute_force(self):
        rng=random.Random(819);rows=[(i:=rng.randrange(150),i+rng.randrange(1,40),str(rng.randrange(4))) for _ in range(120)];idx=TargetSpans(rows)
        for start in range(190):
            for owner in '01234':
                v=Interval(start,start+1);self.assertEqual(idx.intersects(v,owner),any(k!=owner and a<v.end and v.start<b for a,b,k in rows))
    def test_reverse_indels_split_parts_and_own_part_exclusion(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); src=SourceKey('d','a'); s='A'*100+'N'*20+'A'*80;parts={p.segment_id:p for p in split_source(src,s,min_gap=10).segments};self.assertEqual(len(parts),2)
            refs={'c':500}; p=root/'ref.paf';p.write_text('a\t200\t70\t150\t-\tc\t500\t201\t281\t76\t82\t60\tcg:Z:20M2I10M2D2X46M\n');idx=ReferenceIndex.create(root/'index',root,parts,refs)
            try:
                list(read_paf(p,artifact='ref.paf',query_lengths={'a':200},target_lengths=refs,record_observer=lambda hit,off,n:idx.observe_record('d',hit,off,n)));idx.seal();self.assertEqual(idx.count,1); verdicts=set()
                for start in (67,88,99,100,110,119,120,130,145,150):
                    frontier={src:[Interval(start,start+2)]}
                    for context in (0,3,11):
                        mask=invert(idx,frontier,context=context)
                        for x in range(192,288,3):
                            regions={'c':(Interval(x,x+1),)}
                            for ex in [*parts,None]:
                                rows=idx.targets(regions,context=context,exclude=[ex] if ex else []); actual=any(Interval(v.start+parts[k].interval.start,v.end+parts[k].interval.start).intersection(frontier[src][0]) for k,vs in rows.items() for v in vs);verdicts.add(actual);self.assertEqual(target_hit(mask,regions,ex),actual)
                self.assertEqual(verdicts,{True,False})
            finally:idx.close()
