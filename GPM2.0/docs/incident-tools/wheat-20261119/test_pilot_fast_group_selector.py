from pathlib import Path
import random
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from lgz_core import q0_admission as adm
from lgz_core.common import reverse_complement
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PairLink,ReferenceAnchor
from lgz_core.q0_sources import Interval, SourceKey, split_source
from pilot_fast_group_selector import build,choose,skeleton
from pilot_fast_group_run import save_layout


def fixture(strand='+',offset=1600):
    r=random.Random(62); genome=''.join(r.choices('ACGT',k=8000)); parts=[];seqs={}
    for name,a,o in [('a',0,'+'),('b',offset,strand)]:
        s=SourceKey(name,name); text=genome[a:a+2000]; seqs[s]=text if o=='+' else reverse_complement(text)
        p,=split_source(s,seqs[s],min_gap=100).segments; iv=p.interval
        parts.append(adm._placement(p,'4D',o,iv,(iv,),(ReferenceAnchor(iv,Interval(a,a+2000),name),),(name,),kind='reference'))
    return parts,SimpleNamespace(sources=seqs,original_adjacencies=())


class Tests(unittest.TestCase):
    def test_existing_and_refined_with_both_orientations(self):
        for orientation in ('+','-'):
            p,data=fixture(orientation); l,r=p; self.assertEqual(skeleton(p[::-1]),p)
            b,unresolved,_=build(p,[],data); self.assertEqual([len(x.nodes) for x in b],[1,1]); self.assertEqual(choose(unresolved,[]),([(l,r)],1))
            t0=0 if orientation=='+' else 1600
            h=parse_paf_line(f'a\t2000\t1600\t2000\t{orientation}\tb\t2000\t{t0}\t{t0+400}\t400\t400\t60\tcg:Z:400=',artifact='fixture.paf',line_number=1)
            link=PairLink(h,l.source,r.source)
            for existing,added in [([link],[]),([],[link])]:
                paths,u,_=build(p,existing,data,added);self.assertEqual(u,[]); self.assertEqual(len(paths),1);self.assertEqual(paths[0].joins[0].kind,'sequence_overlap')
                with TemporaryDirectory() as d: summary=save_layout(Path(d),'T',paths,data)
                self.assertEqual((summary['sequence_bp'],summary['source_bp_used']),(3600,3600))
    def test_disjoint_reference_without_pair_evidence_not_joined(self):
        p,data=fixture(offset=2500); paths,u,_=build(p,[],data); self.assertEqual(len(paths),2); self.assertEqual(choose(u,[]),([],0))
    def test_repetitive_cut_not_accepted(self):
        p,data=fixture(); l,r=p; data.sources[l.source]='A'*2000;data.sources[r.source]='A'*2000
        h=parse_paf_line('a\t2000\t1600\t2000\t+\tb\t2000\t0\t400\t400\t400\t60\tcg:Z:400=',artifact='repeat.paf',line_number=1)
        paths,_,_=build(p,[PairLink(h,l.source,r.source)],data);self.assertFalse(any(j.kind=='sequence_overlap' for x in paths for j in x.joins))

    @unittest.skipUnless(__import__('shutil').which('minimap2'), 'optional real local mapper')
    def test_real_mapper_on_offset_reverse_ends(self):
        from shutil import which
        from pilot_fast_group_selector import map_batch
        dna=''.join(random.Random(93).choices('ACGT',k=86000)); seqs={};ps=[]
        for name,text,start,strand in [('l',dna[:45000],0,'+'),('r',reverse_complement(dna[41000:]),41000,'-')]:
            s=SourceKey('sample',name);seqs[s]=text;part,=split_source(s,text).segments;v=part.interval
            ps.append(adm._placement(part,'4D',strand,v,[v],[ReferenceAnchor(v,Interval(start,start+v.length),name)],[name],kind='reference'))
        data=SimpleNamespace(sources=seqs,original_adjacencies=());paths,u,_=build(ps,[],data);self.assertEqual(len(paths),2)
        with TemporaryDirectory() as tmp:
            links,receipts=map_batch(data,choose(u,[])[0],Path(tmp),Path(which('minimap2')))
            self.assertEqual(len(receipts),1);self.assertTrue(links);self.assertTrue(all(x.query_offset>0 and x.target_offset>0 for x in links))
            paths,_,_=build(ps,[],data,links);self.assertEqual(len(paths),1)
            self.assertEqual(save_layout(Path(tmp),'R',paths,data)['record_hashes'],[__import__('hashlib').sha256(dna.encode()).hexdigest()])
