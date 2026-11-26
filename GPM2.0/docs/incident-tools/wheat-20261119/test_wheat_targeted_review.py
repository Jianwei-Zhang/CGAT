"""No impossible-flank proof is allowed to remove a real mapper request."""
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from lgz_core.q0_sources import SourceKey,Interval
from lgz_core.q0_paths import Placement,ReferenceAnchor,PathGraph,PairLink,PathPolicy
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_junction_review import possible_window
from screen_wheat_junction_flanks import screen_all,maybe_old_cut
from assess_wheat_shortlist_panel import read_arm,calls
from plan_wheat_indirect_panel import choose
from summarize_wheat_paired_outcomes import footprint,request_delta


def p(k,start,stop,orientation='+'):
    s=SourceKey('ds',k);span=Interval(0,stop-start);r=Interval(start,stop);return Placement(k,k,s,span,orientation,'chr',(r,),(span,),('r',),(ReferenceAnchor(span,r,'r'),))

def paf(a,b,qs,qe,ts,te,strand='+'):
    n=qe-qs;return f'{a.segment_id}\t{a.interval.length}\t{qs}\t{qe}\t{strand}\t{b.segment_id}\t{b.interval.length}\t{ts}\t{te}\t{n}\t{n}\t60\tcg:Z:{n}M\n'

class Targeted(unittest.TestCase):
    def test_missing_witness_and_retained_probe(self):
        left,alt,right=p('l',0,300),p('a',200,600),p('r',500,900);ref=SimpleNamespace(kind='reference_unknown')
        hit=PairLink(parse_paf_line(paf(left,alt,200,300,0,100),artifact='a',line_number=1),left.source,alt.source)
        self.assertTrue(any(j.kind=='sequence_overlap' for j in PathGraph((left,alt),(hit,),first_request=True).joins('l','a')))
        self.assertTrue(maybe_old_cut(left,alt,[hit],ref,PathPolicy()))
        # Only the right flank may request; the other side absolutely needs an old overlap.
        cases=[('chr','pid',alt,[(left,alt,ref,None),(alt,right,ref,possible_window(alt,right,100))])]
        self.assertEqual(screen_all(cases,[],['chr'])['eligible_upper'],0)
        self.assertEqual(screen_all(cases,[hit],['chr'])['eligible_upper'],1)
        witness=PairLink(parse_paf_line(paf(alt,right,300,400,0,100),artifact='b',line_number=1),alt.source,right.source)
        self.assertEqual(screen_all(cases,[hit,witness],['chr'])['eligible_upper'],0)

    def test_cut_on_real_paf_and_threshold_request_use_only_this_arm(self):
        a,b=p('q',0,300),p('t',200,500);z=PairLink(parse_paf_line(paf(a,b,200,300,0,100),artifact='arm',line_number=1),a.source,b.source)
        lookup={k:dict(length=300,original_assigned_chromosomes=['chr']) for k in ('q','t')}
        full,_,fullreq=calls([a,b],[z],'q','t',lookup);other,_,req=calls([a,b],[],'q','t',lookup)
        self.assertIn(['sequence_overlap',250,50],full);self.assertFalse(other)
        self.assertTrue(fullreq['assessable'] and req['assessable'])

    def test_indirect_panel_is_not_a_second_direct_demand_run(self):
        l,r=p('original',0,300),p('wanted',200,500,'-');slices=[SimpleNamespace(source=x.source,orientation=x.orientation,interval=x.interval) for x in (l,r)]
        path=SimpleNamespace(chromosome='chr',slices=slices,joins=[SimpleNamespace(kind='sequence_overlap',join_id='j')]);ids={x.segment_id:dict(dataset='ds',contig=x.segment_id,length=x.interval.length) for x in (l,r)}
        pending=[[{'dataset':'ds','contig':'wanted'},[[200,300]]]]; cases,retained,counts=choose([path],ids,pending,set())
        self.assertEqual((len(cases),retained,counts),(1,['wanted'],{'-':1}));self.assertEqual((cases[0]['q'],cases[0]['target_cut_distance_to_demand']),('original',0))
        self.assertFalse(choose([path],ids,pending,{'original'})[0]);self.assertFalse(choose([path],ids,pending+[[{'dataset':'ds','contig':'original'},[[0,100]]]],set())[0])

    def test_request_delta_is_source_qualified_and_unknown_is_not_empty(self):
        s={'dataset':'d','contig':'c'};o={'dataset':'e','contig':'c'}
        full=[[s,[[0,10],[30,31]]]]; reduced=[[s,[[4,12],[40,42]]],[o,[[7,9]]]]; original=footprint([[s,[[7,11],[29,33]]]])
        self.assertEqual(request_delta(full,reduced,original),dict(full_only_bp=5,reduced_only_bp=6,full_only_in_frozen_demand_bp=1,reduced_only_in_frozen_demand_bp=1,same=False))
        self.assertFalse(request_delta(None,[],original)['same']);self.assertTrue(request_delta(None,None,original)['same'])

    def test_screen_strand_and_wrong_arm_inventory(self):
        a,b=p('q',0,300),p('t',200,500);raw=paf(a,b,200,300,0,100).encode();lookup={k:dict(length=300,contig=k,dataset='ds') for k in ('q','t')}
        with TemporaryDirectory() as d:
            f=Path(d)/'matrix.paf';f.write_bytes(raw);pin=sha256(raw).hexdigest(); rows,geo,links=read_arm(f,pin,{'q'},{'t'},lookup,{frozenset(('q','t'))},True)
            self.assertEqual(rows['retained'],1);self.assertEqual(sum(geo.values()),1);self.assertEqual(sum(map(len,links.values())),1)
            with self.assertRaises(ValueError):read_arm(f,pin,{'q'},set(),lookup,set(),True)
            with self.assertRaises(ValueError):read_arm(f,'0'*64,{'q'},{'t'},lookup,set(),True)

if __name__=='__main__':unittest.main()
