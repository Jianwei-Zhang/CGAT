from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compare_wheat_local_only_paths import GROUPS,checkpoint
from lgz_core.q0_paths import Join,Placement,ReferenceAnchor,RequestPathResult,Slice,_ScoredPath
from lgz_core.q0_sources import Interval,SourceKey
from trace_wheat_local_evidence_use import Trace,sealed
from wheat_selection_checkpoint import Store


class EvidenceUseTests(unittest.TestCase):
    def test_real_checkpoint_fields_separate_admitted_selected_and_overlap_join_ids(self):
        trace=Trace({'a':1,'b':1,'c':2,'d':4,'not-listed':5});iv=Interval(0,100);placements=[]
        for n,ev in enumerate([('a','old'),('b',),('old',),('d',)]):
            src=SourceKey('dataset',str(n));placements.append(Placement(str(n),'s'+str(n),src,iv,'+','1A',(iv,),(iv,),ev,(ReferenceAnchor(iv,iv,'old'),)))
        nodes=tuple(p.placement_id for p in placements[:3]);slices=tuple(Slice(p.placement_id,p.source,iv,'+') for p in placements[:3]);joins=(
            Join('overlap','0','1','sequence_overlap',100,0,0,('c',)),Join('unknown','1','2','reference_unknown',100,0,100,('a','b')))
        winner=RequestPathResult(_ScoredPath('1A',nodes,joins,slices,(10,)))
        with TemporaryDirectory() as d,redirect_stdout(StringIO()):
            folder=Path(d);store=Store(folder,['bound'],False);store.save('admission.jsonl',None,placements)
            for i,g in enumerate(GROUPS,1):store.save_group(i,g,winner if g=='1A' else RequestPathResult(None))
            chain,_,paths=checkpoint(folder,['bound'],on_placement=trace.placement);self.assertEqual(chain,store.previous)
        result=trace.finish(paths);self.assertEqual(result['distinct_rows_cited'],4);self.assertEqual(result['rows_not_explicitly_cited'],1)
        self.assertEqual(result['distinct_rows_by_role'],dict(admitted_placement=3,selected_placement=2,selected_overlap_join=1,selected_other_join=2))
        self.assertEqual(result['records_by_group']['1A']['selected_other_join'],1);self.assertFalse(any(result['records_by_group']['Un'].values()))
        self.assertEqual(len(result['batches']),15);self.assertEqual(result['batches'][2],dict(batch=3,rows=0,cited=0))

    def test_comparison_must_have_one_exact_seal_before_any_attribution(self):
        with TemporaryDirectory() as d:
            p=Path(d);(p/'result.json').write_bytes(b'{}');pin=sha256(b'{}').hexdigest();log=p/'out';line=pin+'  result.json\n'
            ok='    JOB_ID:    123\n    EXIT_CODE:    0\n'
            for bad in (line, line+ok.replace('123','456'), line+ok.replace('CODE:    0','CODE:    1'),
                        ok, line+line+ok, '0'*64+'  result.json\n'+ok, pin+'  other.json\n'+ok):
                log.write_text(bad)
                with self.assertRaises(ValueError):sealed(p,'out','result.json',123)
            log.write_text(line+ok);self.assertEqual(sealed(p,'out','result.json',123),({},pin))
