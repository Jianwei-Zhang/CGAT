import tempfile, unittest
from types import SimpleNamespace as S
from lgz_core.q0_sources import Interval
from run_wheat_local_only_batches import FaiDNA
from assess_wheat_local_only_batches import local_contacts,counts

class RegionalBatchTests(unittest.TestCase):
    def test_indexed_source_slice_on_all_wrap_boundaries(self):
        for nl in (b'\n',b'\r\n'):
            dna=b'AcGtaCtCAAG';head=b'>part'+nl
            with tempfile.TemporaryFile() as f:
                f.write(head+nl.join([dna[:4],dna[4:8],dna[8:]])+nl);f.flush(); source=FaiDNA(f.fileno(),(len(dna),len(head),4,4+len(nl)))
                for a in range(len(dna)+1):
                    for b in range(a,len(dna)+1):self.assertEqual(source[a:b],dna[a:b].decode('ascii'))
    def test_require_actual_pair_run_inside_shoulder_not_a_deletion_hull(self):
        blocks=[S(operation='M',target=Interval(0,100)),S(operation='X',target=Interval(100,200)),S(operation='=',target=Interval(300,405))]
        hit=S(target=Interval(0,405),matches=400,block_length=410,aligned_blocks=lambda:blocks)
        self.assertEqual(local_contacts(hit,[(1,0,Interval(0,150)),(1,1,Interval(110,240)),(2,0,Interval(289,400)),(3,0,Interval(310,405))]),{(1,0),(2,0)})
    def test_distinct_parents_and_windows_do_not_invent_one_bridge(self):
        rows=[{'kind':'unproven_join'} for _ in range(3)];s={0:{0:{('a','w1')},1:{('b','w2')}},1:{0:{('a','w1')},1:{('a','w2')}},2:{0:{('a','w2')},1:{('a','w2')}}}; r=counts(rows,s)
        self.assertEqual((r['joins_hit_on_both_ends_by_same_parent'],r['joins_hit_on_both_ends_in_same_query_window']),(2,1))
