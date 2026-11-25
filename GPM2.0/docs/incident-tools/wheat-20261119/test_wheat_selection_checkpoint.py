"""Exercise a real first-request rank, interruption, restore and evidence fences."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'server/tools'))
from lgz_core import q0_admission as adm
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_catalog import evidence_ref
from lgz_core.q0_paths import RequestPathResult, Slice, Join, _ScoredPath
from lgz_core.q0_sources import Interval, SourceKey, split_source, Q0EvidenceError
from wheat_selection_checkpoint import Store, PlacementSaved


def fixture():
    srcs, parts, refs, evidence = {}, {}, {}, {}
    lens = {'1A': 2000, '2A': 2000, '3B': 2000}
    for num, chrom in enumerate(('1A','3B')):
        key = SourceKey('asm', 'ctg'+chrom)
        srcs[key] = ''.join(random.Random(17+num).choices('ACGT',k=450))
        for p in split_source(key,srcs[key]).segments:parts[p.segment_id] = p
        raw = f'{key.contig}\t450\t0\t450\t+\t{chrom}\t2000\t5\t455\t450\t450\t60\tcg:Z:450M'
        hit=parse_paf_line(raw,artifact='ref.paf',line_number=num+1);refs[key]=[hit];evidence[hit.evidence_id]=evidence_ref(hit)
    return adm.EvidenceInput(srcs,parts,lens,refs,(),(),evidence,'fixture')


class CheckpointTests(TestCase):
    def test_interrupted_graph_resumes_prefix_including_no_path(self):
        data = fixture(); full = adm.select_request_paths(data)
        self.assertIsNone(full.paths['2A'].path); self.assertIsNotNone(full.paths['3B'].path)
        with TemporaryDirectory() as tmp:
            root=Path(tmp); binding=['one pinned run']; first=lambda:Store(root,binding,False)
            with self.assertRaises(PlacementSaved):adm.select_request_paths(data,checkpoint=Store(root,binding,True))
            self.assertFalse((root/'group-001.jsonl').exists())
            real=adm.PathGraph; calls=[]
            def graph(placements,*a,**kw):
                calls.append(placements[0].chromosome)
                if calls==['1A','3B']:raise InterruptedError('at 3B')
                return real(placements,*a,**kw)
            with patch.object(adm,'_admit_placements',side_effect=AssertionError('repeated placement')),patch.object(adm,'PathGraph',side_effect=graph):
                with self.assertRaises(InterruptedError):adm.select_request_paths(data,checkpoint=first())
                self.assertTrue((root/'group-002.jsonl').is_file()); self.assertFalse((root/'group-003.jsonl').exists())
                resumed=adm.select_request_paths(data,checkpoint=first());self.assertEqual(calls,['1A','3B','3B'])
                self.assertEqual(resumed,full);self.assertEqual(adm.select_request_paths(data,checkpoint=first()),full)
                self.assertEqual(len(calls),3)
            with self.assertRaisesRegex(ValueError,'wrong input'):Store(root,['different'],False).load_admission()
            p=root/'group-001.jsonl';raw=p.read_bytes(); p.write_bytes(raw[:-5])
            with self.assertRaises(ValueError):adm.select_request_paths(data,checkpoint=first())

    def test_restored_gap_still_reserves_original_source(self):
        data=fixture(); src=next(iter(data.sources))
        with TemporaryDirectory() as tmp:
            b=['same'];store=Store(Path(tmp),b,False)
            store.save_admission(adm.select_request_paths(data).admission)
            def make(c,slices,joins):return RequestPathResult(_ScoredPath(c,tuple(x.placement_id for x in slices),joins,slices,(9,)))
            a=Slice('left',src,Interval(0,5),'+'); b1=Slice('right',src,Interval(10,15),'+')
            join=Join('j','left','right','input_assembly_gap',5,10,5,('original',),'original',src,Interval(5,10))
            store.save_group(1,'1A',make('1A',(a,b1),(join,)));store.save_group(2,'2A',RequestPathResult(None))
            store.save_group(3,'3B',make('3B',(replace(a,interval=Interval(6,9)),),()))
            with self.assertRaisesRegex(Q0EvidenceError,'selected on multiple chromosomes'):
                adm.select_request_paths(data,checkpoint=Store(Path(tmp),b,False))

if __name__=='__main__':main()
