from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace
import unittest

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from server.tests.test_q0_paths import placement, link
from lgz_core.q0_paths import Join, PathPolicy, Slice, qualify_pair_blocks
from freeze_q0_unseen_panels import choose
import freeze_q0_multisource_holdouts as post
from q0_threshold_questions import ends, questions, supported
from lgz_core.q0_sources import Interval
from run_q0_threshold_holdout import arm, construct


class ThresholdTests(unittest.TestCase):
    def test_supported_location_is_not_a_proven_bridge(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                f, _ = bridge_fixture(reverse); data=f.data()
                backed, stats = questions(data, construct(data), [])
                self.assertEqual(backed,{})
                self.assertEqual(stats['sequence_overlap_stop'],2)
                thin=replace(data,pair_links=()); requested, stats=questions(thin,construct(thin),[])
                self.assertGreater(stats['unproven_join'],0); self.assertTrue(requested)
                self.assertGreater(stats['positive_placement_stop'],0)

    def test_real_internal_rival_is_retained_but_does_not_trigger_mapping(self):
        f=EvidenceFixture({'chr':2000}); seq=dna(2000); root=f.source('root',seq); alt=f.source('alt',seq[850:1350]); f.ref(root,(0,2000),(0,2000),chromosome='chr'); f.pair(alt,root,(0,500),(850,1350))
        d=f.data(); draft=construct(d); self.assertTrue(draft.paths['chr'].alternatives)
        self.assertEqual(questions(d,draft,[])[0],{})

    def test_confirmed_competing_locus_does_not_request_another_mapping_or_allow_a_cut(self):
        for orient in ('+', '-'):
            a = placement('left', 0, 1000, offset=150)
            b = placement('right', 600, 1600, orientation=orient, offset=200)
            end_hit = link(a, b, (600, 1000), (0, 400), number=1)
            rival = link(a, b, (600, 1000), (500, 900), number=2)
            self.assertFalse(qualify_pair_blocks(a, b, [end_hit, rival], PathPolicy()))
            gap = Join('gap', a.placement_id, b.placement_id, 'reference_unknown', 1000, 0, 100,
                       a.evidence_ids+b.evidence_ids)
            path = SimpleNamespace(slices=[Slice(p.placement_id, p.source, p.interval, p.orientation) for p in (a,b)], joins=[gap])
            draft = SimpleNamespace(paths={'chr1': SimpleNamespace(path=path)}, admission=SimpleNamespace(placements=[a,b]))
            d = SimpleNamespace(sources={p.source: None for p in (a,b)}, parts={}, reference_lengths={}, pair_links=[rival,end_hit])
            need, stats = questions(d, draft, [])
            self.assertEqual(need, {}); self.assertEqual(stats['observed_facing_match_leave_gap'], 1)
            self.assertEqual(path.joins[0].kind, 'reference_unknown')
            d.pair_links = [rival]
            self.assertEqual(set(questions(d, draft, [])[0]), {a.source, b.source})

    def test_do_not_ignore_an_assigned_chromosome_with_no_backbone(self):
        f=EvidenceFixture({'A':2000,'B':2000}); s=f.source('root',dna(2000)); u=f.source('absent',dna(600)); f.ref(s,(0,2000),(0,2000),chromosome='A'); f.ref(u,(0,600),(250,850),chromosome='B'); d=f.data()
        draft=construct(d); draft.paths['B'].path=None  # A rooted chromosome can still lack a selected path.
        need,_=questions(d,draft,[{'dataset_name':u.dataset,'seq_name':u.contig,'assigned_chr_name':'B'}]); self.assertEqual({k:[(v.start,v.end) for v in vals] for k,vals in need.items()},{u:[(0,600)]})
        self.assertIsNone(questions(d,None,[])[0])

    def test_secondary_assignment_does_not_reopen_a_supported_slice_or_mask_its_neighbour(self):
        f = EvidenceFixture({'A':2000, 'B':2000}); r = f.source('root', dna(2000)); f.ref(r,(0,2000),(0,2000),chromosome='A')
        b=f.source('b',dna(700,seed=41)); f.ref(b,(0,700),(0,700),chromosome='B')
        data = f.data(); draft = construct(data); draft.paths['B'].path=None; extra = [{'dataset_name':r.dataset,'seq_name':r.contig,'assigned_chr_name':'B'}]
        need, stats = questions(data, draft, extra)
        self.assertFalse(need); self.assertEqual(stats['secondary_assignment_supported_bp_not_requested'],2000)
        # Only the retained slice, not the whole originally assigned source, has passed.
        row = draft.paths['A']; sl, = row.path.slices
        row.path = replace(row.path, slices=(replace(sl,interval=Interval(100,1700)),))
        need, stats = questions(data, draft, extra)
        self.assertEqual([(x.start,x.end) for x in need[r]],[(0,100),(1700,2000)])
        self.assertEqual(stats['secondary_assignment_supported_bp_not_requested'],1600)

    def test_reference_free_pair_chain_cannot_found_a_chromosome_but_can_extend_a_real_seed(self):
        f = EvidenceFixture({'A':3500,'B':3500}); seq=dna(2800)
        a=f.source('a',seq[:1500]); b=f.source('b',seq[1000:2200]); c=f.source('c',seq[1700:])
        f.pair(a,b,(1000,1500),(0,500)); f.pair(b,c,(700,1200),(0,500))
        rows=[{'dataset_name':s.dataset,'seq_name':s.contig,'assigned_chr_name':'B'} for s in (a,b,c)]
        no_roots=f.data(); self.assertIsNone(construct(no_roots))
        self.assertEqual(questions(no_roots,None,rows),({}, {'no_reference_seed_no_backbone':1}))
        f.ref(a,(0,1500),(0,1500),chromosome='A'); data=f.data(); full=construct(data)
        self.assertIsNotNone(full.paths['A'].path); self.assertIsNone(full.paths['B'].path)
        self.assertEqual({p.chromosome for p in full.admission.placements},{'A'})
        base=replace(data,pair_links=()); draft=construct(base); demand,stats=questions(base,draft,rows)
        self.assertEqual(demand,{}); self.assertEqual(stats['unbuilt_without_reference_seed'],1)
        # A real outstanding A junction must still be requested, including on a source
        # that also carries an assignment to the impossible chromosome B.
        f2,_=bridge_fixture(); weak=replace(f2.data(), pair_links=()); weak.reference_lengths['B']=3500
        both=[{'dataset_name':s.dataset,'seq_name':s.contig,'assigned_chr_name':'B'} for s in weak.sources]
        need,stats=questions(weak,construct(weak),both)
        self.assertTrue(need); self.assertGreater(stats['unproven_join'],0)

    def test_zero_mapper_budget_means_no_planner_for_both_stop_and_refusal(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        f, _ = bridge_fixture(); data=f.data()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)/'must-not-exist'
            _, rec = arm(None,{},data,[],None,root,None,4,True,forbid_mapping=True)
            self.assertEqual(rec['route'],'base_stop_no_planner'); self.assertFalse(rec['fresh_mapper_processes'])
            with self.assertRaisesRegex(ValueError,'zero-mapper budget'):
                arm(None,{},replace(data,pair_links=()),[],None,root,None,4,True,forbid_mapping=True)
            self.assertFalse(root.exists())

    def test_duplicate_or_one_sided_evidence_does_not_count_twice(self):
        l,r=ends(Interval(1000,2000),100); known=[Interval(1040,1140)]*4
        self.assertTrue(supported(l,known,100)); self.assertFalse(supported(r,known,100))

    def test_postrule_panel_requires_separated_high_support_sources_and_excludes_old_names(self):
        rows=[]
        for c in ('1A','2A','3A','4A'):
            for i in range(8):
                rows.append({'dataset_name':str(i%2), 'seq_name':c+str(i), 'anchor_start':str(30000*i+1),
                             'assigned_chr_name':c, 'seq_length_bp':'20000', 'support_percent':'85'})
        for r in rows[-8:]: r['support_percent']='51'
        with patch.object(post,'PANELS',()), patch.object(post,'choose',return_value=()), patch.object(post,'cohorts',return_value={('old',0):{('0','1A0'):1}}):
            self.assertEqual(post.select(rows,{'0','1'}),(('2A',0),('3A',0)))
            for r in rows: r['anchor_start']='1'
            with self.assertRaisesRegex(ValueError,'no additional disjoint'):
                post.select(rows,{'0','1'})

    def test_cohort_choice_is_order_independent_disjoint_and_rejects_shared_members(self):
        def block(c,m,n,prefix):
            return [{'dataset_name':str(i%2),'seq_name':prefix+str(i),'anchor_start':str(1+m*10**6),'assigned_chr_name':c,'seq_length_bp':'30000','support_percent':'30'} for i in range(n)]
        rows=block('1A',2,8,'A')+block('2A',4,16,'B')+block('3A',6,16,'C'); rows[8]['seq_name']='A0'
        self.assertEqual(choose(rows,{'0','1'},previous=(),sizes=(8,16)),(('1A',2),('3A',6)))
        self.assertEqual(choose(rows[::-1],{'0','1'},previous=(),sizes=(8,16)),(('1A',2),('3A',6)))
