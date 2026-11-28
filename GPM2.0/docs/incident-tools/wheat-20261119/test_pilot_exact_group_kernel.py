from collections import Counter
from dataclasses import replace
import random
from types import SimpleNamespace
import unittest

from lgz_core import q0_paths as paths
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import Interval
from pilot_exact_group_kernel import AxesCache, exact_kernel
from test_pilot_fast_group_selector import fixture


class ExactGroup(unittest.TestCase):
    def test_envelopes_against_original_both_axes_and_offsets(self):
        rng=random.Random(93); old=paths.pair_blocks
        with exact_kernel() as counts:
            for strand in ("+","-"):
                (l,r),_=fixture(strand)
                hit=parse_paf_line(f"a\t110\t8\t98\t{strand}\tb\t110\t9\t99\t84\t92\t60\tcg:Z:30=2I4X2D54=",artifact="p",line_number=1)
                for same in (False,True):
                    for swap in (False,True):
                        q,t=(l.source,l.source if same else r.source); link=paths.PairLink(hit,q,t,700,980)
                        for _ in range(150):
                            ll,rr=(l,l if same else r) if not swap else (l if same else r,l)
                            def piece(p):
                                a=rng.randint(640,1110);return replace(p,interval=Interval(a,a+rng.randint(1,255)),reference_blocks=(),reference_intervals=(),anchor_intervals=(),seed_eligible=False,localization_kind="input_adjacency",orientation=rng.choice(("+","-")))
                            left,right=piece(ll),piece(rr)
                            self.assertEqual(old(link,left,right),paths.pair_blocks(link,left,right))
            self.assertGreater(counts["pair_blocks_original"],0);self.assertGreater(counts["pair_blocks_proven_empty"],0)

    def test_cache_retains_all_competitors_and_invalidates(self):
        class Axis:
            starts=()
        calls=[]
        def actual(rows,l,r,m): calls.append((rows,l,r,m));return (Axis(),Axis())
        stats=Counter();cached=AxesCache(actual,stats,slots=1,max_units=3)
        a,b,c=(object() for _ in range(3)); first=cached([a,b],1,2,10)
        self.assertIs(cached((a,b),1,2,10),first)
        for rows,l,r,m in [([a],1,2,10),([a,c],1,2,10),([c,a],1,2,10),([c,a],2,1,10),([c,a],2,1,11),([a,b],1,2,10)]:
            self.assertIsNot(cached(rows,l,r,m),first)
        self.assertEqual((len(calls),stats["axis_builds_avoided"]),(7,1))
        large=[a,b,c,c];self.assertIsNot(cached(large,1,2,10),cached(large,1,2,10))

    def test_integer_runs_preserve_competing_axes_and_clipped_coordinates(self):
        from pilot_exact_group_runs import axes,clipped,source_runs
        from lgz_core.q0_retained_hits import RetainedHit
        rng=random.Random(151)
        for strand in ("+","-"):
            (l,r),_=fixture(strand);links=[]
            for i in range(20):
                ops=[(rng.randint(1,35),rng.choice("MIDN=X")) for _ in range(28)]+[(31,"=")]
                q=sum(n for n,op in ops if op in "MI=X"); t=sum(n for n,op in ops if op in "MDN=X"); m=sum(n for n,op in ops if op in "M=")
                h=parse_paf_line(f"a\t2000\t23\t{q+23}\t{strand}\tb\t2000\t72\t{t+72}\t{m}\t{sum(n for n,_ in ops)}\t60\tcg:Z:"+"".join(f"{n}{op}" for n,op in ops),artifact="p",line_number=i+1)
                if i%2:h=RetainedHit.from_validated(h,"a","b")
                link=paths.PairLink(h,l.source,r.source if i%3 else l.source,120,385);links.append(link)
                self.assertEqual(list(source_runs(link)),[(a.start,a.end,b.start,b.end) for a,b in link.source_blocks()])
                for _ in range(25):
                    def v(s):
                        a=rng.randrange(60,795);return SimpleNamespace(source=s,interval=Interval(a,a+rng.randrange(1,510)),orientation=rng.choice("+-"),local=None)
                    left=v(link.query_source);right=v(link.target_source)
                    if rng.choice((0,1)):left,right=right,left
                    for item in (left,right): item.local=lambda iv,item=item:paths.Placement.local(item,iv)
                    self.assertEqual(clipped(link,left,right),paths.pair_blocks(link,left,right))
            for m in (1,13,31,55):
                for a,b in [(l.source,r.source),(r.source,l.source),(l.source,l.source)]:
                    for old,new in zip(paths._competing_axes(links,a,b,m),axes(links,a,b,m)):
                        self.assertEqual((old.starts,old.by_prefix),(new.starts,new.by_prefix))

    def test_sparse_panel_keeps_nonlocal_competitor_and_filtered_epoch(self):
        from pilot_fast_group_sparse import sparse_graph
        (l,r),_=fixture("+",offset=1600)
        def link(a,b,t,n):
            h=parse_paf_line(f"a\t2000\t{a}\t{a+n}\t+\tb\t3000\t{b}\t{b+n}\t{n}\t{n}\t60\tcg:Z:{n}=",artifact="observed",line_number=t)
            return paths.PairLink(h,l.source,r.source)
        primary=link(1600,0,1,400);outside=link(1600,2500,2,400)
        def get():
            g=paths.PathGraph((l,r),[primary,outside],first_request=True); rejected=g.homologous_blocks(l,r)
            g.ambiguous_equivalence_ids={outside.hit.evidence_id};g._blocks.clear()
            return rejected,g.homologous_blocks(l,r)
        ref=get();self.assertFalse(ref[0]);self.assertTrue(ref[1])
        with sparse_graph() as stats:
            self.assertEqual(get(),ref);self.assertLess(stats["candidate_link_visits"],stats["potential_link_visits"])
