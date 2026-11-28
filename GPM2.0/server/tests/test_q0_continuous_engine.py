"""Focused regression for continuous admission and reference-locus equivalence."""
from collections import defaultdict
from dataclasses import replace
import random
import unittest
from unittest.mock import patch
from server.tools.lgz_core import q0_admission as admission
from server.tools.lgz_core.q0_collinear import ContinuousAdmissionPolicy, continuous_candidates, chain, foreign_barriers
from server.tools.lgz_core.q0_interval_index import IntervalIndex
from server.tools.lgz_core.q0_reference_locus import ReferenceDomains
from server.tools.lgz_core.q0_coverage import CoverageModel, Equivalence
from server.tools.lgz_core.q0_paths import PathGraph, PathPolicy, Placement, ReferenceAnchor, Block, _anchor_supported, _incident_placement_pairs, qualify_pair_blocks, search_paths
from server.tools.lgz_core.q0_sources import Interval, SourceKey, SourceSegment, merged_intervals, Q0EvidenceError
from server.tests.test_q0_paths import placement, link


def anchor(start, end, ref):
    return ReferenceAnchor(Interval(start,end),Interval(ref,ref+end-start),f'e-{start}-{ref}')


class ContinuousAdmissionTests(unittest.TestCase):
    def fixture(self, terminal=False, foreign=False):
        length=20_000_000
        start,end=(0,1_000_000) if terminal else (8_000_000,9_000_000)
        main=[anchor(end,length,end)] if terminal else [anchor(0,start,0),anchor(end,length,end)]
        groups={('1','+'):main,('2' if foreign else '1','-'):[anchor(start,end,30_000_000)]}
        high={k:tuple(a.source for a in aa) for k,aa in groups.items()}
        part=SourceSegment('p',SourceKey('d','s'),Interval(0,length),'a'*64,0,'start','end')
        return part,groups,high

    def candidates(self,part,groups,high):
        return continuous_candidates(part,groups,high,admission.AdmissionPolicy(),admission._placement)[0]

    def test_asymmetric_barriers_keep_only_exclusive_carried_arms(self):
        # Observed ptg000571l geometry (synthetic anchor contents). The real
        # checkpoint replay also checks the original main-chain blocks verbatim.
        part=SourceSegment('part',SourceKey('asm','ptg000571l'),Interval(0,16202389),'a'*64,0,'start','end')
        g={('2A','+'): [anchor(349,811857,100)], ('7A','-'): [anchor(1079989,1089989,17000000), anchor(1250000,16202386,100)]}
        high={k:[a.source for a in rows] for k,rows in g.items()}
        def barriers(groups, high, key, *args, **kwargs):
            return ((Interval(1200585,part.interval.end),) if key[0]=='2A' else (Interval(0,1048919),)), []
        with patch('server.tools.lgz_core.q0_collinear.foreign_barriers',side_effect=barriers):
            ps=self.candidates(part,g,high)
        self.assertEqual({p.chromosome:p.interval for p in ps},
                         {'2A':Interval(0,811857),'7A':Interval(1079989,16202389)})
        admission.validate_admission_occupancy(ps)

    def test_overlapping_chain_hulls_reject_both_and_keep_disjoint_arm(self):
        from server.tools.lgz_core.q0_collinear import exclusive_carriers
        rows=[('A',Interval(0,120),Interval(5,70)), ('B',Interval(50,185),Interval(65,175)),
              ('D',Interval(185,220),Interval(190,215))]
        self.assertEqual(exclusive_carriers(rows),(None,None,rows[2][1]))
        self.assertEqual(exclusive_carriers(rows[::-1]),(rows[2][1],None,None))

    def test_unique_reference_seed_is_not_also_emitted_as_continuous(self):
        from server.tests.test_q0_admission import EvidenceFixture,dna
        f=EvidenceFixture();src=f.source('a',dna(2000));f.ref(src,(0,1700),(0,1700))
        with patch.object(admission,'continuous_candidates',side_effect=AssertionError('redundant seed')):
            ps=admission.admit_placements(f.data()).placements
        self.assertEqual([p.localization_kind for p in ps],['reference'])

    def test_admission_guard_checks_physical_source_across_segment_ids(self):
        from types import SimpleNamespace as Row
        s=SourceKey('a','x'); a=Row(source=s,interval=Interval(0,100),chromosome='2A',placement_id='first',segment_id='one')
        b=Row(source=s,interval=Interval(99,103),chromosome='7A',placement_id='second',segment_id='two')
        with self.assertRaisesRegex(Q0EvidenceError, '2A.*first.*7A.*second'):
            admission.validate_admission_occupancy([b,a])
        b.interval=Interval(100,103); admission.validate_admission_occupancy([b,a])

    def test_internal_and_terminal_inversions_preserve_whole_source(self):
        for terminal in (False,True):
            part,g,h=self.fixture(terminal);ps=self.candidates(part,g,h)
            self.assertEqual({(p.interval,p.orientation,p.chromosome) for p in ps},{(part.interval,'+','1')})

    def test_large_cross_chromosome_chain_still_splits(self):
        part,g,h=self.fixture(foreign=True)
        cuts,_=foreign_barriers(g,h,('1','+'),chain(g[('1','+')],'+'),part.interval.length,minimum_anchor_bp=100)
        self.assertEqual(cuts,(Interval(8_000_000,9_000_000),))
        main=[p for p in self.candidates(part,g,h) if p.chromosome=='1']
        self.assertTrue(main)
        self.assertTrue(all(p.interval.intersection(cuts[0]) is None for p in main))

    def scattered_fixture(self):
        main=[anchor(i*150000,i*150000+100000,i*150000) for i in range(10)]
        part=SourceSegment('p',SourceKey('d','s'),Interval(0,1500000),'a'*64,0,'start','end')
        return part,{('1','+'):main}
    def test_top10_does_not_sum_unrelated_foreign_groups(self):
        part,g=self.scattered_fixture()
        for i in range(10):
            for j in range(4):
                lo=i*150000+100000+j*10000
                g[(f'foreign-{i}-{j}','+')]=[anchor(lo,lo+10000,1000000+lo)]
        h={k:tuple(a.source for a in aa) for k,aa in g.items()}
        ps,audit=continuous_candidates(part,g,h,admission.AdmissionPolicy(),admission._placement)
        self.assertEqual(len(ps),1)
        self.assertFalse(audit[0]['legacy_dominance_passed'])
        self.assertTrue(audit[0]['top_chain_passed'])
    def test_single_group_scattered_support_guard_remains(self):
        part,g=self.scattered_fixture()
        g[('2','+')]=[anchor(i*150000+100000,i*150000+140000,2000000-i*100000) for i in range(10)]
        h={k:tuple(a.source for a in aa) for k,aa in g.items()}
        self.assertFalse(self.candidates(part,g,h))

    def test_strong_competitor_is_not_silently_ignored(self):
        part,g,h=self.fixture()
        # Overlap the main source anchors: it is a competitor, not an independent barrier.
        g[('2','+')]=[anchor(0,8_000_000,40_000_000)]
        h={k:tuple(a.source for a in aa) for k,aa in g.items()}
        # Legacy 75% rule is independently eligible here. Disable just that
        # control to test the Top10 competitor rule itself.
        policy=ContinuousAdmissionPolicy(legacy_dominance_fraction=1.0)
        ps,_=continuous_candidates(part,g,h,admission.AdmissionPolicy(),admission._placement,policy)
        self.assertFalse(ps)

    def test_production_adapter_consumes_interval_high_mapq(self):
        from server.tests.test_q0_admission import EvidenceFixture,dna
        f=EvidenceFixture({'chr1':30000});src=f.source('a',dna(20000));data=f.data();part=next(iter(data.parts.values()))
        g={('chr1','+'):(anchor(0,8000,0),anchor(9000,20000,9000)),('chr1','-'):(anchor(8000,9000,25000),)}
        h={k:tuple(a.source for a in aa) for k,aa in g.items()}
        policy=replace(admission.AdmissionPolicy(),continuous=ContinuousAdmissionPolicy(minimum_main_chain_bp=100,minimum_new_chain_bp=500))
        with patch.object(admission,'_reference_groups',return_value=(g,h,())) as screen:
            result=admission.admit_placements(data,policy=policy)
        self.assertTrue(screen.call_args.kwargs['high_intervals'])
        self.assertEqual({(p.interval,p.orientation) for p in result.placements},{(part.interval,'+')})
        self.assertTrue(all(p.localization_kind=='continuous_reference' for p in result.placements))

    def test_continuous_carrier_skips_legacy_small_cross_chr_tail_split(self):
        from server.tests.test_q0_admission import EvidenceFixture, dna
        f = EvidenceFixture({'chr1': 30000, 'chr2': 30000})
        a, b = f.source('a', dna(20000)), f.source('b', dna(2000, 42))
        f.pair(a, b, (19400, 20000), (0, 600))
        data = f.data()
        def screen(data, part, policy):
            groups = ({('chr1', '+'): (anchor(0, 1000, 0), anchor(1200, 19400, 1200)),
                       ('chr1', '-'): (anchor(1000, 1200, 25000),)} if part.source == a else
                      {('chr2', '+'): (anchor(0, 2000, 0),)})
            return groups, {k: tuple(x.source for x in aa) for k, aa in groups.items()}, (), ()
        policy = replace(admission.AdmissionPolicy(), continuous=ContinuousAdmissionPolicy(
            minimum_main_chain_bp=100, minimum_new_chain_bp=500))
        with patch.object(admission, '_reference_screen', side_effect=screen):
            result = admission.admit_placements(data, policy=policy)
        carriers = [p for p in result.placements if p.source == a]
        self.assertEqual(len(carriers), 1)
        self.assertEqual(carriers[0].interval, Interval(0, 20000))
        self.assertEqual(carriers[0].localization_kind, 'continuous_reference')
        self.assertFalse(any(r.get('reason') == 'independently_anchored_cross_chr_tail'
                             for r in result.records))

    def test_continuous_reference_is_a_real_root_for_supplement_questions(self):
        from types import SimpleNamespace as NS
        from server.tools.lgz_core.q0_threshold_questions import questions
        from server.tools.lgz_core.q0_paths import RequestPathResult
        p=replace(placement('a',0,1000),localization_kind='continuous_reference')
        direct=admission.RequestAdmission((p,))
        missing,stats=questions(None,NS(paths={},admission=direct),[])
        self.assertIsNone(missing)
        self.assertEqual(stats,{'rooted_no_path_full_fallback':1})
        graph=PathGraph([p],(),())
        path=graph._score_candidate((p.placement_id,),())
        data=NS(sources={p.source:'A'*1000},reference_lengths={'chr1':1000},pair_links=())
        needed,stats=questions(data,NS(paths={'chr1':RequestPathResult(path)},admission=direct),[])
        self.assertFalse(needed)
        self.assertEqual(stats['positive_placement_stop'],1)

    def test_selector_identity_includes_all_new_scientific_modules(self):
        names=[]
        with patch.object(admission,'sha256_file',side_effect=lambda p:names.append(p.name) or 'a'):
            admission.selector_identity()
        for name in ('q0_collinear.py','q0_reference_locus.py','q0_interval_index.py','q0_backbone.py'):
            self.assertIn(name,names)


class LocusTests(unittest.TestCase):
    def p(self,name,ref=None,reverse=False,anchors=None):
        a=placement(name,ref or 0,(ref or 0)+100,orientation='-' if reverse else '+')
        if ref is None:return replace(a,reference_intervals=(),reference_blocks=(),anchor_intervals=(),seed_eligible=False,localization_kind='input_adjacency')
        if anchors is not None:return replace(a,reference_intervals=merged_intervals(x.reference for x in anchors),reference_blocks=anchors,anchor_intervals=tuple(x.source for x in anchors))
        return a
    def model(self,ps,edges,tolerance=100000):
        return CoverageModel({p.source:(p.interval,) for p in ps},edges,reference_domains=ReferenceDomains(ps,tolerance))
    def relation(self,a,b,reverse=False):
        return Equivalence(a.source,a.interval,b.source,b.interval,reverse,a.placement_id+b.placement_id)
    def test_same_locus_duplicate_and_reverse_duplicate_remain(self):
        for reverse in (False,True):
            a,b=self.p('a',10000),self.p('b',10000,reverse)
            model=self.model([a,b],[self.relation(a,b,reverse)])
            self.assertIsNone(model.unique_selected_bp([(p.source,p.interval) for p in (a,b)]))
    def test_distant_loci_and_unknown_bridge(self):
        a,b,c=self.p('a',10000),self.p('b'),self.p('c',10000000)
        model=self.model([a,b,c],[self.relation(a,b),self.relation(b,c)])
        self.assertEqual(model.unique_selected_bp([(p.source,p.interval) for p in (a,c)]),200)
        self.assertEqual(model.locus_audit['rejected_unions'],1)
    def test_unknown_and_conflicting_anchor_frames_do_not_erase_homology(self):
        a,b=self.p('a'),self.p('b')
        self.assertIsNone(self.model([a,b],[self.relation(a,b)]).unique_selected_bp([(p.source,p.interval) for p in (a,b)]))
        a=self.p('a',0,anchors=(anchor(0,40,0),anchor(60,100,10000000)))
        model=self.model([a,b],[self.relation(a,b)],0)
        self.assertIsNone(model.unique_selected_bp([(p.source,p.interval) for p in (a,b)]))
    def test_internal_anchors_use_same_atom_start(self):
        a=self.p('a',10000,anchors=(anchor(0,20,10000),));b=self.p('b',10000,anchors=(anchor(80,100,10080),))
        self.assertIsNone(self.model([a,b],[self.relation(a,b)],0).unique_selected_bp([(p.source,p.interval) for p in (a,b)]))
    def test_bad_policy_and_multichromosome_context_rejected(self):
        for value in (-1,True,1.5):
            with self.assertRaises(Q0EvidenceError):ReferenceDomains([],value)
        a=self.p('a',0);b=replace(self.p('b',0),chromosome='other')
        with self.assertRaises(Q0EvidenceError):ReferenceDomains([a,b])


class IndexAndBackboneTests(unittest.TestCase):
    def test_interval_index_matches_exhaustive_overlaps(self):
        rng=random.Random(651)
        rows=[Interval(a,a+rng.randrange(1,100)) for a in rng.choices(range(200),k=200)]
        index=IntervalIndex(rows,lambda x:x)
        for start in range(250):
            query=Interval(start,start+3)
            self.assertEqual({i for i,_ in index.overlapping(query)},{i for i,iv in enumerate(rows) if iv.intersection(query)})
    def test_anchor_support_matches_nested_loop(self):
        rng=random.Random(92)
        for orientation in ('+','-'):
            for _ in range(20):
                a=placement('a',0,100,orientation=orientation);b=placement('b',0,100)
                def intervals():return tuple(Interval(x,x+10) for x in rng.choices(range(90),k=8))
                a=replace(a,anchor_intervals=intervals());b=replace(b,anchor_intervals=intervals())
                block=Block(Interval(20,80),Interval(10,70));expected=[]
                for x in a.anchor_intervals:
                    clipped=block.clip_left(a.local(x))
                    if clipped:
                        for y in b.anchor_intervals:
                            ov=clipped.right.intersection(b.local(y))
                            if ov:
                                start=clipped.left.start+ov.start-clipped.right.start;expected.append(Interval(start,start+ov.length))
                self.assertEqual(merged_intervals(_anchor_supported(block,a,b)),merged_intervals(expected))
    def test_sparse_pairs_match_qualified_cartesian_geometry(self):
        a,b=placement('a',0,1000),placement('b',0,1000)
        links=(link(a,b,(0,1000),(0,1000)),)
        lefts=[replace(a,placement_id=f'a{i}',interval=Interval(i,i+100),anchor_intervals=(Interval(i,i+100),),reference_blocks=(anchor(i,i+100,i),),reference_intervals=(Interval(i,i+100),)) for i in (0,300,900)]
        rights=[replace(b,placement_id=f'b{i}',interval=Interval(i,i+100),anchor_intervals=(Interval(i,i+100),),reference_blocks=(anchor(i,i+100,i),),reference_intervals=(Interval(i,i+100),)) for i in (0,100,300,700)]
        policy=PathPolicy(minimum_anchor_bp=10)
        want={(x.placement_id,y.placement_id) for x in lefts for y in rights if qualify_pair_blocks(x,y,links,policy)}
        got={(x.placement_id,y.placement_id) for x,y in _incident_placement_pairs(lefts,rights,links) if qualify_pair_blocks(x,y,links,policy)}
        self.assertEqual(got,want)
    def test_continuous_backbone_uses_exact_gate_without_fragment_refinement(self):
        ps=[replace(placement(str(i),i*200,(i*200)+100),localization_kind='continuous_reference') for i in range(4)]
        graph=PathGraph(ps,(),())
        result=search_paths(graph)
        self.assertEqual(len(result.path.slices),4)
        self.assertEqual(result.diagnostics['strategy'],'reference_backbone')
        self.assertEqual(result.diagnostics['rounds'],0)
        self.assertFalse(graph.coverage.assess((s.source,s.interval) for s in result.path.slices)[1])
    def test_draft_and_formal_use_identical_locus_atoms_and_winner(self):
        a,b=placement('a',0,1000),placement('b',500,1500)
        a=replace(a,localization_kind='continuous_reference')
        b=replace(b,localization_kind='continuous_reference')
        links=(link(a,b,(500,750),(0,250),number=1),link(a,b,(750,1000),(250,500),number=2))
        full=PathGraph([a,b],links,(),first_request=False)
        draft=PathGraph([a,b],links,(),first_request=True)
        self.assertEqual(full.coverage.atoms,draft.coverage.atoms)
        self.assertEqual(full.coverage.units,draft.coverage.units)
        from server.tools.lgz_core.q0_paths import search_request_path
        self.assertEqual(search_paths(full).path.slices,search_request_path(draft).path.slices)

    def test_indexed_graph_can_roundtrip_a_private_cache(self):
        import pickle
        a,b=placement('a',0,1000),placement('b',500,1500)
        graph=PathGraph([a,b],(link(a,b,(500,1000),(0,500)),),())
        expected=search_paths(graph).path
        restored=pickle.loads(pickle.dumps(graph))
        self.assertEqual(restored.coverage.units,graph.coverage.units)
        self.assertEqual(search_paths(restored).path,expected)

    def test_failed_backbone_proposal_retains_legacy_search(self):
        p=replace(placement('a',0,100),localization_kind='continuous_reference')
        graph=PathGraph([p],(),())
        with patch('server.tools.lgz_core.q0_backbone.reference_spine',return_value=(None,{})):
            result=search_paths(graph)
        self.assertEqual(result.path.nodes,('a',))

class BackboneJoinTests(unittest.TestCase):
    def gap_graph(self):
        from server.tests.test_q0_paths import bridge_fixture
        _, (a, b, _), _, _, original = bridge_fixture(original_gap=True)
        return PathGraph([a, b], (), original), a, b

    def test_input_assembly_gap_precedes_unknown_in_full_proposal(self):
        from server.tools.lgz_core.q0_backbone import reference_spine
        graph, a, b = self.gap_graph()
        self.assertEqual([j.kind for j in graph.joins(a.placement_id, b.placement_id)],
                         ['input_assembly_gap', 'reference_unknown'])
        result, report = reference_spine(graph)
        self.assertTrue(report['full_proposal_passed'])
        self.assertEqual(result.joins[0].kind, 'input_assembly_gap')
        self.assertEqual(result.joins[0].n_bp, 137)

    def test_exact_overlap_precedes_longer_unknown_join(self):
        from server.tools.lgz_core.q0_backbone import reference_spine
        a, b = placement('a', 0, 1000), placement('b', 1100, 2100)
        graph = PathGraph([a, b], (), ())
        # Isolate join selection from pair-map qualification. Both candidates
        # pass the real scorer; the unknown join carries more source bases.
        overlap = graph._join(a, b, 'sequence_overlap', 900, 100, 0, ('pair',))
        unknown = graph.joins('a', 'b')[0]
        with patch.object(graph, 'joins', return_value=(overlap, unknown)):
            result, report = reference_spine(graph)
        self.assertTrue(report['full_proposal_passed'])
        self.assertEqual(result.joins, (overlap,))

    def test_invalid_exact_join_falls_back_through_original_score_gate(self):
        from server.tools.lgz_core.q0_backbone import reference_spine
        graph, a, b = self.gap_graph()
        score = graph._score_candidate
        def reject_exact(nodes, joins):
            if any(j.kind == 'input_assembly_gap' for j in joins):
                return None  # fault injection at the exact path/duplicate gate
            return score(nodes, joins)
        with patch.object(graph, '_score_candidate', side_effect=reject_exact):
            result, report = reference_spine(graph)
        self.assertFalse(report['full_proposal_passed'])
        self.assertEqual(result.nodes, (a.placement_id, b.placement_id))
        self.assertEqual(result.joins[0].kind, 'reference_unknown')
        self.assertIsNotNone(score(result.nodes, result.joins))

    def test_prefix_recovery_also_keeps_first_valid_evidence_join(self):
        from server.tools.lgz_core.q0_backbone import reference_spine
        graph, a, b = self.gap_graph()
        score = graph._score_candidate
        calls = 0
        def reject_full_once(nodes, joins):
            nonlocal calls
            calls += 1
            return None if calls == 1 else score(nodes, joins)
        with patch.object(graph, '_score_candidate', side_effect=reject_full_once):
            result, report = reference_spine(graph)
        self.assertFalse(report['full_proposal_passed'])
        self.assertEqual(result.joins[0].kind, 'input_assembly_gap')

if __name__=='__main__':unittest.main()

class LocalEnvelopeIncidentTests(unittest.TestCase):
    @staticmethod
    def sparse(name, size, events):
        p = placement(name, 0, size)
        anchors = tuple(anchor(*args) for args in events)
        return replace(p, reference_blocks=anchors, reference_intervals=merged_intervals(a.reference for a in anchors),
                       anchor_intervals=merged_intervals(a.source for a in anchors))

    def test_4a_distal_114bp_does_not_merge_two_source_slices(self):
        # Frozen three source/partner atom pairs; reduced surrounding reference anchors.
        a = self.sparse("ptg000036l",220255611,[(0,100,0),(130000000,130000100,200000000),(175000000,175000100,245000000)])
        b = self.sparse("ptg000015l",30000000,[(0,100,0),(25000000,25000100,25000000),(29999900,30000000,245000000)])
        spans = [(139394745,4306115,8),(139394688,4306123,57),(166195495,23503207,49)]
        edges = [Equivalence(a.source,Interval(x,x+n),b.source,Interval(y,y+n),True,str(i)) for i,(x,y,n) in enumerate(spans)]
        pools = {p.source:(p.interval,) for p in (a,b)}; selected = [(p.source,p.interval) for p in (a,b)]
        domain = ReferenceDomains([a,b]); model = CoverageModel(pools,edges,reference_domains=domain)
        self.assertEqual(model.unique_selected_bp(selected), a.interval.length+b.interval.length)
        with patch.object(ReferenceDomains,"local_bounds",lambda d,p,iv:d.bounds[p.placement_id]):
            self.assertIsNone(CoverageModel(pools,edges,reference_domains=ReferenceDomains([a,b])).unique_selected_bp(selected))

    def test_6a_same_locus_212bp_via_unselected_bridge_still_rejected(self):
        a = self.sparse("JM19flyeA_contig_5353",37818089,[(0,100,0),(37799000,37799100,1000000)])
        b = self.sparse("JM19flyeD_contig_16054",30000,[(27813,28025,1000950)])
        c = placement("bridge",0,212)
        c = replace(c,reference_intervals=(),reference_blocks=(),anchor_intervals=(),seed_eligible=False,localization_kind="input_adjacency")
        edges = []
        for x,y,z,n in [(37799926,0,27813,200),(37799914,200,28013,12)]:
            iv=Interval(y,y+n)
            edges.extend([Equivalence(a.source,Interval(x,x+n),c.source,iv,True,"a"),
                          Equivalence(c.source,iv,b.source,Interval(z,z+n),False,"b")])
        model=CoverageModel({p.source:(p.interval,) for p in (a,b,c)},edges,reference_domains=ReferenceDomains([a,b,c]))
        self.assertIsNone(model.unique_selected_bp([(p.source,p.interval) for p in (a,b)]))

    def test_un_labels_configurable_and_real_foreign_barrier_remains(self):
        f=ContinuousAdmissionTests();part,gs,hi=f.fixture(foreign=True); k=("scaffolds","-")
        gs[k]=gs.pop(("2","-"));hi[k]=hi.pop(("2","-")); main=("1","+")
        args=(gs,hi,main,gs[main],part.interval.length)
        self.assertTrue(foreign_barriers(*args,minimum_anchor_bp=100)[0])
        cuts,audit=foreign_barriers(*args,minimum_anchor_bp=100,policy=ContinuousAdmissionPolicy(unplaced_reference_groups="scaffolds"))
        self.assertFalse(cuts); self.assertTrue(any(r.get("reason")=="internal_un_preserve_main_chain" for r in audit))
