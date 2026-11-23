import io
from itertools import product
from types import SimpleNamespace
import unittest

from census_wheat_q0_fork import HEAD, MAGIC, measure, pack_context
from lgz_core.common import stable_id
from lgz_core.q0_frontier_scope import window_touches_frontier
from lgz_core.q0_sources import Interval, SourceKey


def fixture(other=1):
    def window(rank):
        row={'segment_id':str(rank),'segment_length':50,'start':10,'end':30}
        return dict(row,window_id=stable_id('q0-query-window' if not rank else 'q0-target-window',row))
    lookup={str(i):(i,50,str(i)*64) for i in range(3)}
    q,t=window(0),window(other)
    s={'schema':'lgz_q0_regional_context_v1','preset':'asm10','fasta_format':'wrap80_v1','members':[[x,lookup[x][2]] for x in ('0',str(other))],'query':q,'targets':[t]}
    return s,lookup


def pack(s,l): return pack_context(stable_id('q0-regional-context',s),s,l)


class CensusTest(unittest.TestCase):
    def test_interval_boundaries_and_either_axis_match_actual_selector(self):
        s,l=fixture(); block=pack(s,l); query,target=[SimpleNamespace(**r) for r in (s['query'],s['targets'][0])]
        parts={i:SimpleNamespace(source=SourceKey('dataset',i),interval=Interval(0,50)) for i in l}
        for a,b in product([None,(1,10),(9,11),(29,30),(30,32)],repeat=2):
            bits={i:[v] for i,v in enumerate([a,b]) if v}; frontier={parts[str(i)].source:[Interval(*spans[0])] for i,spans in bits.items()}; counts,_=measure(io.BytesIO(MAGIC+block),bits)
            self.assertEqual(bool(counts['retained_contexts']),window_touches_frontier(query,[target],parts,frontier))

    def test_same_query_two_target_contexts_is_not_two_unique_queries(self):
        block=MAGIC+pack(*fixture())+pack(*fixture(2)); counts,_=measure(io.BytesIO(block),{2:[(11,15)]})
        self.assertEqual((counts['retained_contexts'],counts['omitted_contexts'],counts['distinct_query_windows'],counts['queries_omitted_across_all_observed_target_sets']),(1,1,1,0))
        self.assertEqual(measure(io.BytesIO(block),None)[0]['axes_breakdown'],{'full_fallback':2}); self.assertEqual(measure(io.BytesIO(block),{})[0]['omitted_contexts'],2)

    def test_rejects_duplicate_truncated_or_mutated_geometry_and_source(self):
        s,l=fixture(); block=pack(s,l)
        for raw in (MAGIC+block+block,MAGIC+block[:-1],MAGIC+block[:HEAD.size-1]):
            with self.assertRaises(ValueError):measure(io.BytesIO(raw),{})
        key=stable_id('q0-regional-context',s); s['targets'][0]['end']=31
        with self.assertRaises(ValueError):pack_context(key,s,l)
        s['members'][0][1]='f'*64
        with self.assertRaises(ValueError):pack(s,l)


if __name__=='__main__': unittest.main()
