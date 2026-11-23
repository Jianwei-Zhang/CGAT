import random
import unittest
from unittest import mock

from server.tools.lgz_core import q0_catalog as catalog
from server.tools.lgz_core.q0_alignments import parse_paf_line, PafAlignment
from server.tools.lgz_core.q0_sources import Interval, SourceKey, Q0EvidenceError


def reference_observe(observed,hit,query,target,query_offset=0,target_offset=0):
    """Previous geometry path, deliberately retaining every block projection."""
    qualify=(query.dataset!=target.dataset and hit.matches/hit.block_length>=.95
             and sum(n for n,op in hit.cigar if op in 'M=')>=100)
    paired=False
    for block in hit.aligned_blocks():
        paired=True
        if qualify and block.operation!='X':
            for source,interval,offset in ((query,block.query,query_offset),(target,block.target,target_offset)):
                union=observed.cross_coverage.setdefault(source,catalog._IntervalUnion())
                union.append(Interval(interval.start+offset,interval.end+offset))
    if paired:observed.add(tuple(sorted((query,target))))


def alignment(cigar,strand='+'):
    q=sum(n for n,op in cigar if op in 'MI=X');t=sum(n for n,op in cigar if op in 'MDN=X')
    matches=sum(n for n,op in cigar if op in 'M=');span=sum(n for n,op in cigar)
    text=''.join(str(n)+op for n,op in cigar)
    return parse_paf_line(f'q\t{q+50}\t17\t{q+17}\t{strand}\tt\t{t+70}\t29\t{t+29}\t{matches}\t{span}\t60\tcg:Z:{text}',artifact='actual.paf',line_number=1)


class QueryOnlyGeometryTests(unittest.TestCase):
    def test_all_operations_offsets_and_both_strands_equal_paired_blocks(self):
        rng=random.Random(29851)
        cases=[[(100,'M')],[(100,'X')],[(50,'I'),(50,'D')],[(999,'M'),(1,'I'),(1,'D')],
               [(80,'='),(5,'X'),(12,'N'),(3,'D'),(7,'I'),(90,'M')]]
        cases.extend([(1,'M')]+[(rng.randrange(1,100),rng.choice('MIDN=X')) for _ in range(rng.randrange(1,70))]
                      for _ in range(500))
        for cigar in cases:
            for strand in ('+','-'):
                hit=alignment(cigar,strand)
                self.assertEqual(tuple(hit.paired_query_intervals()),tuple(b.query for b in hit.aligned_blocks()))
                for same_dataset in (False,True):
                    q=SourceKey('a','q');t=SourceKey('a' if same_dataset else 'b','t')
                    lengths={q:hit.query_length+13,t:hit.target_length+31}
                    before=catalog.ObservedSourcePairs(lengths);after=catalog.ObservedSourcePairs(lengths)
                    reference_observe(before,hit,q,t,13,31)
                    after.observe_alignment(hit,SourceKey(q.dataset,q.contig),SourceKey(t.dataset,t.contig),query_offset=13,target_offset=31)
                    self.assertEqual(before,after)
                    self.assertEqual({k:tuple(v) for k,v in before.cross_coverage.items()},
                                     {k:tuple(v) for k,v in after.cross_coverage.items()})

    def test_nonqualifying_relations_need_no_geometry_but_still_validate_bounds(self):
        hit=alignment([(1000,'M')]);q=SourceKey('same','q');t=SourceKey('same','t')
        observed=catalog.ObservedSourcePairs({q:hit.query_length,t:hit.target_length})
        with mock.patch.object(PafAlignment,'aligned_blocks',side_effect=AssertionError('unneeded target geometry')):
            observed.observe_alignment(hit,q,t)
            self.assertEqual(observed,{tuple(sorted((q,t)))})
            with self.assertRaises(Q0EvidenceError):observed.observe_alignment(hit,q,t,query_offset=1)
        self.assertEqual(observed.cross_coverage,{})

    def test_relation_keys_are_shared_without_removing_any_edges(self):
        sources=[SourceKey('same',f'ctg{i}') for i in range(64)]
        hit=alignment([(100,'M')]);lengths={key:max(hit.query_length,hit.target_length) for key in sources}
        before=catalog.ObservedSourcePairs(lengths);after=catalog.ObservedSourcePairs(lengths)
        for i,q in enumerate(sources):
            for t in sources[i+1:]:
                reference_observe(before,hit,SourceKey(q.dataset,str(q.contig)),SourceKey(t.dataset,str(t.contig)))
                after.observe_alignment(hit,SourceKey(q.dataset,str(q.contig)),SourceKey(t.dataset,str(t.contig)))
        self.assertEqual(len(after),2016);self.assertEqual(before,after)
        self.assertEqual(len({id(key) for pair in before for key in pair}),4032)
        self.assertEqual(len({id(key) for pair in after for key in pair}),64)
        originals={key:key for key in sources}
        self.assertTrue(all(key is originals[key] for pair in after for key in pair))


if __name__=='__main__':unittest.main()
