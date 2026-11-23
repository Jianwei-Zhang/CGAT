from dataclasses import replace
from types import SimpleNamespace
import unittest

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from server.tests.test_q0_paths import placement, link
from lgz_core.q0_paths import Join, PathPolicy, Slice, qualify_pair_blocks
from freeze_q0_unseen_panels import choose
from q0_threshold_questions import ends, questions, supported
from lgz_core.q0_sources import Interval
from run_q0_threshold_holdout import construct


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
        f=EvidenceFixture({'A':2000,'B':2000}); s=f.source('root',dna(2000)); u=f.source('absent',dna(600)); f.ref(s,(0,2000),(0,2000),chromosome='A'); d=f.data()
        need,_=questions(d,construct(d),[{'dataset_name':u.dataset,'seq_name':u.contig,'assigned_chr_name':'B'}]); self.assertEqual({k:[(v.start,v.end) for v in vals] for k,vals in need.items()},{u:[(0,600)]})
        self.assertIsNone(questions(d,None,[])[0])

    def test_duplicate_or_one_sided_evidence_does_not_count_twice(self):
        l,r=ends(Interval(1000,2000),100); known=[Interval(1040,1140)]*4
        self.assertTrue(supported(l,known,100)); self.assertFalse(supported(r,known,100))

    def test_cohort_choice_is_order_independent_disjoint_and_rejects_shared_members(self):
        def block(c,m,n,prefix):
            return [{'dataset_name':str(i%2),'seq_name':prefix+str(i),'anchor_start':str(1+m*10**6),'assigned_chr_name':c,'seq_length_bp':'30000','support_percent':'30'} for i in range(n)]
        rows=block('1A',2,8,'A')+block('2A',4,16,'B')+block('3A',6,16,'C'); rows[8]['seq_name']='A0'
        self.assertEqual(choose(rows,{'0','1'},previous=(),sizes=(8,16)),(('1A',2),('3A',6)))
        self.assertEqual(choose(rows[::-1],{'0','1'},previous=(),sizes=(8,16)),(('1A',2),('3A',6)))
