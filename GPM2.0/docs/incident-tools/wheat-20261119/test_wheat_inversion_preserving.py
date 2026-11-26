import unittest
from lgz_core.q0_sources import Interval,SourceKey,SourceSegment
from wheat_inversion_preserving_readonly import candidates,foreign_barriers,merge_frozen
from wheat_local_chain_primitives import chain
from test_wheat_continuous_dominant_admission import anchor

class InversionPreservingTests(unittest.TestCase):
    def fixture(self, terminal=False, foreign=False):
        length=20_000_000
        start,end=(0,1_000_000) if terminal else (8_000_000,9_000_000)
        main=[anchor(end,length,end)] if terminal else [anchor(0,start,0),anchor(end,length,end)]
        key=("2", "-") if foreign else ("1", "-")
        groups={("1","+"):main,key:[anchor(start,end,30_000_000)]}
        high={k:tuple(a.source for a in aa) for k,aa in groups.items()}
        part=SourceSegment("p",SourceKey("d","s"),Interval(0,length),"a"*64,0,"start","end")
        return part,groups,high
    def test_internal_inversion_is_carried_without_split(self):
        part,g,h=self.fixture();ps,audit=candidates(part,g,h,"1")
        self.assertTrue(ps);self.assertEqual({(p.interval,p.orientation) for p in ps},{(part.interval,"+")})
        self.assertEqual(audit["top10"]["foreign_barrier_count"],0)
    def test_terminal_inversion_is_not_flipped(self):
        part,g,h=self.fixture(True);ps,_=candidates(part,g,h,"1")
        self.assertEqual({(p.interval,p.orientation) for p in ps},{(part.interval,"+")})
    def test_large_cross_chromosome_chain_still_splits(self):
        part,g,h=self.fixture(foreign=True)
        barriers,_=foreign_barriers(g,h,("1","+"),chain(g[("1","+")],"+"),part.interval.length)
        self.assertEqual(barriers,(Interval(8_000_000,9_000_000),))
        ps,_=candidates(part,g,h,"1")
        self.assertTrue(ps);self.assertTrue(all(p.interval.intersection(barriers[0]) is None for p in ps))
    def test_reverse_whole_contig_keeps_reverse_orientation(self):
        part,g,h=self.fixture(True)
        g={(k[0],"-" if k[1]=="+" else "+"):v for k,v in g.items()}
        h={k:tuple(a.source for a in aa) for k,aa in g.items()}
        ps,_=candidates(part,g,h,"1")
        self.assertTrue(ps);self.assertEqual({p.orientation for p in ps},{"-"})
    def test_old_opposite_fragment_cannot_leak_back_into_union(self):
        from dataclasses import replace
        part,g,h=self.fixture();new,_=candidates(part,g,h,"1");p=new[0]
        opposite=replace(p,placement_id="opposite",orientation="-")
        ps,removed=merge_frozen([opposite],new)
        self.assertEqual(removed,["opposite"]);self.assertEqual({p.orientation for p in ps},{"+"})
    def test_unrelated_frozen_group_not_removed(self):
        from dataclasses import replace
        part,g,h=self.fixture();new,_=candidates(part,g,h,"1")
        other=replace(new[0],placement_id="other",chromosome="2",orientation="-")
        ps,removed=merge_frozen([other],new)
        self.assertFalse(removed);self.assertIn(other,ps)

if __name__=="__main__":unittest.main()
