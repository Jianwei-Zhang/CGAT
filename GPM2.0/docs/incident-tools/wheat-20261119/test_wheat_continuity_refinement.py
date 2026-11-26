"""Small deterministic admission/cut invariants, not genome-level acceptance."""
import unittest
from dataclasses import replace
from wheat_continuity_result_audit import check_cut
from lgz_core import q0_paths as paths
from lgz_core.q0_admission import _placement
from lgz_core.q0_sources import SourceSegment,SourceKey,Interval
from lgz_core.q0_alignments import parse_paf_line
from wheat_continuity_hull_replay_readonly import hull_candidates,original,adm
from wheat_continuity_path_refinement_readonly import (
    common_anchor_joins,splice_choices,refine,refs,selected_risk,monotone_better)


def a(lo,hi,ref=None,eid='ref'):
    ref=lo if ref is None else ref
    return paths.ReferenceAnchor(Interval(lo,hi),Interval(ref,ref+hi-lo),eid)


def fixture(internal=True,links=True):
    parts=[SourceSegment(k,SourceKey('test',k),Interval(0,1000),'a'*64,0,'start','end') for k in ('a','b')]
    ra=(a(500,800,500,'a-ref'),)
    rb=(a(200,500,500,'b-ref'),) if internal else (a(0,1000,1000,'b-ref'),)
    ps=[_placement(part,'1A','+',part.interval,(x.source for x in anchors),anchors,
                   (x.evidence_id for x in anchors),kind='reference') for part,anchors in zip(parts,(ra,rb))]
    raw='a\t1000\t500\t800\t+\tb\t1000\t200\t500\t300\t300\t60\tcg:Z:300='
    hit=parse_paf_line(raw,artifact='synthetic',line_number=1)
    pair=[paths.PairLink(hit,parts[0].source,parts[1].source)] if links else []
    graph=paths.PathGraph(ps,pair,(),paths.PathPolicy(),first_request=True)
    base=graph._score_candidate((ps[0].placement_id,),())
    return graph,ps,base


class HullTests(unittest.TestCase):
    def test_original_style_low_density_hull_does_not_require_20_percent_again(self):
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,10_000_000),'a'*64,0,'start','end')
        anchors=(a(1_000_000,1_100_000),a(8_000_000,8_100_000))
        groups={('1A','+'):anchors};high={('1A','+'):tuple(x.source for x in anchors)}
        strict,_=original.continuous_candidates(part,groups,high)
        self.assertFalse(any(strict.values()))
        hull,_,detail=hull_candidates(part,groups,high)
        self.assertEqual(hull['90'][0].interval,Interval(1_000_000,8_100_000))
        self.assertEqual(adm._size(hull['90'][0].anchor_intervals),200_000)
        self.assertLess(detail[0]['support_fraction_in_hull'],.2)

    def test_full_region_passing_fraction_is_identical(self):
        part=SourceSegment('p',SourceKey('d','c'),Interval(0,1_000_000),'a'*64,0,'start','end')
        anchors=(a(100_000,900_000),);groups={('1A','+'):anchors};high={('1A','+'):(anchors[0].source,)}
        strict,_=original.continuous_candidates(part,groups,high)
        hull,_,detail=hull_candidates(part,groups,high)
        self.assertEqual(strict,hull);self.assertFalse(detail)


class CutTests(unittest.TestCase):
    def test_internal_common_anchor_and_exact_lower_bound(self):
        graph,ps,base=fixture()
        self.assertFalse(graph.joins(ps[0].placement_id,ps[1].placement_id))
        with common_anchor_joins(graph):
            edges=graph.joins(ps[0].placement_id,ps[1].placement_id)
            self.assertEqual(len(edges),1)
            self.assertEqual(edges[0].kind,'sequence_overlap')
            self.assertTrue(check_cut(graph,edges[0]))
            self.assertFalse(check_cut(graph,replace(edges[0],right_start=edges[0].right_start+1)))
            final,diagnostics=refine(graph,base,progress=lambda s:None)
            self.assertEqual(len(final.nodes),2)
            self.assertGreater(final.score,base.score)
            self.assertEqual(sum(v.length for v in refs(final,graph)),300)
            self.assertEqual(graph._score_candidate(final.nodes,final.joins),final)
            self.assertFalse(selected_risk(final,graph,{})['conflict_flags'])
            self.assertFalse(diagnostics['whole_path_join_product_enumerated'])

    def test_no_pair_evidence_cannot_fabricate_overlap_join(self):
        graph,ps,base=fixture(links=False)
        with common_anchor_joins(graph):
            self.assertFalse(graph.joins(ps[0].placement_id,ps[1].placement_id))
            final,_=refine(graph,base,progress=lambda s:None)
            self.assertEqual(final,base)

    def test_existing_legal_join_and_winner_cannot_be_crowded_out(self):
        graph,ps,base=fixture(internal=False,links=False)
        prior=graph.joins(ps[0].placement_id,ps[1].placement_id)
        self.assertTrue(prior)
        winner=graph._score_candidate(tuple(p.placement_id for p in ps),(prior[0],))
        with common_anchor_joins(graph):
            self.assertTrue(set(prior)<=set(graph.joins(ps[0].placement_id,ps[1].placement_id)))
            self.assertEqual(graph._score_candidate(winner.nodes,winner.joins),winner)
            self.assertFalse(monotone_better(base,winner,graph))

    def test_splice_boundary_dimensions_and_source_conflict_without_reference(self):
        graph,ps,base=fixture()
        with common_anchor_joins(graph):
            for start,stop in ((0,0),(0,1),(1,1)):
                for path in splice_choices(graph,base,ps[1].placement_id,start,stop):
                    if path:self.assertEqual(len(path.joins),len(path.nodes)-1)
        audit=selected_risk(base,graph,{ps[0].source:[(Interval(0,100),'1B','+')]})
        self.assertEqual(audit['source_union_bp']['other_chromosome'],100)
        self.assertEqual(audit['reference_union_bp']['other_chromosome'],0)
        self.assertTrue(audit['conflict_flags'])


if __name__=='__main__':unittest.main()
