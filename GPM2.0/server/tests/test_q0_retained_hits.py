import unittest
from dataclasses import fields
from server.tools.lgz_core.q0_alignments import parse_paf_line, PafAlignment
from server.tools.lgz_core.q0_catalog import evidence_ref
from server.tools.lgz_core.q0_retained_hits import RetainedHit, EvidenceRows


class RetainedEvidenceTests(unittest.TestCase):
    def compare(self, strand, cigar, qlen, tlen):
        line=f'q\t{qlen}\t0\t{qlen}\t{strand}\tt\t{tlen}\t0\t{tlen}\t1\t{max(qlen,tlen)}\t255\txy:Z:α\tcg:Z:{cigar}\tzz:i:02'
        h=parse_paf_line(line,artifact='matrix',line_number=47); r=RetainedHit.from_validated(h,'q','t')
        for f in fields(PafAlignment): self.assertEqual(getattr(r,f.name),getattr(h,f.name),f.name)
        self.assertEqual(r.mapping_quality,h.mapping_quality)
        for _ in range(2):
            self.assertEqual(list(r.aligned_blocks()),list(h.aligned_blocks()))
            self.assertEqual(list(r.paired_query_intervals()),list(h.paired_query_intervals()))
        rows=EvidenceRows({r.evidence_id:r,'gap':{'kind':'input'}})
        self.assertEqual(dict(rows),{r.evidence_id:evidence_ref(h),'gap':{'kind':'input'}})
        with self.assertRaises(KeyError):_ = rows['unknown']
        with self.assertRaises(ValueError):RetainedHit.from_validated(h,'other','t')
        return r

    def test_exact_fields_and_replay_on_both_strands(self):
        for strand in '+-':self.assertIsInstance(self.compare(strand,'2M3I4D5N4=1X',10,16)._packed,bytes)

    def test_extremely_long_valid_single_operation_is_not_truncated(self):
        n=2**40;self.assertIsInstance(self.compare('-',f'{n}M',n,n)._packed,tuple)

    def test_selected_and_alternative_decisions_keep_the_exact_evidence_registry(self):
        from dataclasses import replace
        from server.tests.test_q0_admission import bridge_fixture
        from server.tools.lgz_core.q0_admission import construct_q0
        for reverse in (False,True):
            fixture,_=bridge_fixture(reverse=reverse); original=fixture.data(); entries=dict(original.evidence)
            def retained(h):
                r=RetainedHit.from_validated(h,h.query_name,h.target_name);entries[r.evidence_id]=r;return r
            refs={k:[retained(h) for h in v] for k,v in original.reference_hits.items()}
            links=tuple(replace(l,hit=retained(l.hit)) for l in original.pair_links)
            packed=replace(original,reference_hits=refs,pair_links=links,evidence=EvidenceRows(entries))
            self.assertEqual(construct_q0(original),construct_q0(packed))
