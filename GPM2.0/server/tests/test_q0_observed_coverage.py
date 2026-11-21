import unittest
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_catalog import CandidateCatalog, ObservedSourcePairs, partial_source_intervals
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, SourceSegment


class ObservedCoverageTests(unittest.TestCase):
    def setUp(self):
        self.q=SourceKey("a","q");self.t=SourceKey("b","t")
        self.pairs=ObservedSourcePairs({self.q:10000,self.t:10000})

    def hit(self,strand="+",matches=4000,cigar="1000M100I100D3000M",mapq=255):
        return parse_paf_line(f"q\t4100\t0\t4100\t{strand}\tt\t4100\t0\t4100\t{matches}\t4200\t{mapq}\tcg:Z:{cigar}",artifact="complete.paf",line_number=1)

    def catalog(self):
        part=SourceSegment("q",self.q,Interval(2000,6100),"0"*64,0,"gap","end")
        return CandidateCatalog({"candidates":[{"segment_id":"q","placement_kind":"reference","discovery_query_intervals":[]}]},
                                {self.q:"A"*10000},{"q":part})

    def test_both_sides_exact_gaps_offsets_and_reverse_coordinates(self):
        self.pairs.observe_alignment(self.hit("-"),self.q,self.t,query_offset=2000,target_offset=1000)
        self.assertEqual(self.pairs,{(self.q,self.t)})
        self.assertEqual(tuple(self.pairs.cross_coverage[self.q]),(Interval(2000,5000),Interval(5100,6100)))
        self.assertEqual(tuple(self.pairs.cross_coverage[self.t]),(Interval(1000,2000),Interval(2100,5100)))
        catalog=self.catalog()
        self.assertEqual(partial_source_intervals(catalog),{"q":(Interval(0,4100),)})
        self.assertEqual(partial_source_intervals(catalog,observed=self.pairs),{"q":(Interval(3000,3100),)})
        self.assertEqual(catalog.payload["candidates"][0]["discovery_query_intervals"],[])

    def test_within_and_low_identity_keep_pairs_without_hiding_missing_bases(self):
        self.pairs.observe_alignment(self.hit(matches=3900),self.q,self.t)
        self.assertEqual(self.pairs.cross_coverage,{})
        within=SourceKey("a","t");pairs=ObservedSourcePairs({self.q:10000,within:10000})
        pairs.observe_alignment(self.hit(),self.q,within)
        self.assertTrue(pairs);self.assertEqual(pairs.cross_coverage,{})

    def test_short_paired_hits_and_gap_only_are_not_cross_coverage(self):
        for cigar,qlen,tlen,matches,span,paired in [("99M",99,99,99,99,True),("100I100D",100,100,0,200,False),("100X",100,100,0,100,True)]:
            with self.subTest(cigar=cigar):
                pairs=ObservedSourcePairs({self.q:10000,self.t:10000})
                hit=parse_paf_line(f"q\t{qlen}\t0\t{qlen}\t+\tt\t{tlen}\t0\t{tlen}\t{matches}\t{span}\t0\tcg:Z:{cigar}",artifact="complete",line_number=1)
                pairs.observe_alignment(hit,self.q,self.t)
                self.assertEqual(bool(pairs),paired);self.assertEqual(pairs.cross_coverage,{})

    def test_reference_and_cross_coverage_combine_without_hulls(self):
        self.pairs.observe_alignment(self.hit("-"),self.q,self.t,query_offset=2000)
        catalog=self.catalog();catalog.payload["candidates"][0]["discovery_query_intervals"]=[[5000,5050]]
        self.assertEqual(partial_source_intervals(catalog,observed=self.pairs,minimum_uncovered_bp=1),{"q":(Interval(3050,3100),)})
        self.assertEqual(partial_source_intervals(catalog,observed=self.pairs),{})
        with self.assertRaises(Q0EvidenceError):partial_source_intervals(catalog,minimum_uncovered_bp=0)

    def test_bad_source_frame_fails_before_recording_relation(self):
        for offset in [-1,6000]:
            with self.assertRaises(Q0EvidenceError):self.pairs.observe_alignment(self.hit(),self.q,self.t,query_offset=offset)
        self.assertEqual(self.pairs,set())


if __name__=="__main__":unittest.main()
