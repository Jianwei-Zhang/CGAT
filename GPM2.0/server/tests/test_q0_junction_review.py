"""Known replacement at an unresolved join, not another pass over all supported loci."""
from dataclasses import replace
from pathlib import Path
from random import Random
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.tests.test_q0_paths import placement, link
from server.tools.lgz_core import q0_junction_review as review, q0_regional_mapping as mapping
from server.tools.lgz_core.common import executable_identity, reverse_complement
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.q0_paths import PathGraph, ReferenceAnchor, search_paths
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, split_source
from server.tools.lgz_core.q0_threshold_prepare import _supplement_links
from server.tools.lgz_core.q0_retained_hits import retained_geometry_cache


class JunctionReviewTests(unittest.TestCase):
    def setUp(self):
        self.left=placement('L',0,3000);self.win=placement('W',3000,7000)
        self.right=placement('R',7000,10000);self.alt=placement('A',2400,7600,orientation='-')
        self.ps=(self.left,self.win,self.right,self.alt)
        self.left_hit=link(self.left,self.alt,(2400,3000),(0,600))
        self.right_hit=link(self.alt,self.right,(4600,5200),(0,600),number=2)

    def plan(self, ps=None, links=()):
        graph=PathGraph(ps or self.ps,links);nodes=('L','W','R')
        joins=tuple(graph.joins(a,b)[0] for a,b in zip(nodes,nodes[1:]));path=graph._score_candidate(nodes,joins)
        self.assertIsNotNone(path);r=review.Review();r.observe(graph,path);sel=SimpleNamespace(paths={'chr1':SimpleNamespace(path=path)})
        return r, sel, graph

    def test_two_sides_cached_or_missing_and_reverse_frame(self):
        p=lambda r,s:[(k.query,k.query_span,k.target,k.target_span)for k in r.windows(s)]
        r,s,g=self.plan();missing=p(r,s);self.assertEqual(set(missing),{('L',Interval(1000,3000),'A',Interval(3200,5200)),('A',Interval(0,2000),'R',Interval(0,2000))})
        r,s,g=self.plan(links=[self.left_hit]);self.assertEqual(p(r,s),[('A',Interval(0,2000),'R',Interval(0,2000))]);self.assertFalse(g.joins('A','R'))
        r,s,g=self.plan(links=[self.right_hit,self.left_hit]);self.assertFalse(p(r,s));self.assertEqual(r.counts['both_flanks_already_supported'],1)
        k=missing[0]; parts={k[0]:SimpleNamespace(interval=Interval(700,7700)),k[2]:SimpleNamespace(interval=Interval(300,8300))}
        win=review.PairWindow(k[0],Interval(1200,1400),k[2],Interval(600,900)); q,t=win.windows(parts);self.assertEqual((q.start,q.end,q.cores,t.start,t.end),(500,700,((500,700),),300,600))

    def test_reject_hull_only_short_overlap_and_other_chromosome_occupancy(self):
        a=self.alt; ev='ref'; blocks=(ReferenceAnchor(Interval(0,500),Interval(7500,8000),ev),ReferenceAnchor(Interval(4700,5200),Interval(2000,2500),ev));alt=replace(a,reference_blocks=blocks,reference_intervals=(Interval(2000,2500),Interval(7500,8000)))
        r,s,_=self.plan(self.ps[:3]+(alt,));self.assertFalse(r.windows(s))
        r,s,_=self.plan();dup=replace(s.paths['chr1'].path.slices[0],source=a.source,interval=Interval(1,2));s.paths['chr2']=SimpleNamespace(path=SimpleNamespace(slices=[dup],joins=[]));self.assertFalse(r.windows(s))
        short=placement('A',3000,7099);r,s,_=self.plan(self.ps[:3]+(short,));self.assertFalse(r.windows(s)) # absent left flank and only 99 bp on right

    def test_colocation_without_a_physical_probe_skips_both_edge_lookups(self):
        _,sel,graph=self.plan(self.ps[:3]+(placement('A',3000,7000),))
        r=review.Review()
        with patch.object(graph,'joins',side_effect=AssertionError('expensive edge lookup')):
            r.observe(graph,sel.paths['chr1'].path)
        self.assertEqual(r.counts['two_end_candidates'],1); self.assertFalse(r.windows(sel))

    def test_no_unproven_join_does_not_dispatch(self):
        r,s,g=self.plan();p=s.paths['chr1'].path;settled=replace(p,joins=tuple(replace(j,kind='sequence_overlap') for j in p.joins));r=review.Review();r.observe(g,settled);self.assertFalse(r.windows(s));self.assertFalse(r.counts)

    def test_local_ids_not_counted_as_normal_regional_coverage(self):
        def task(k):return dict(kind='regional_discovery',task_id=k,paf=k+'.paf',query_ids=['q'],target_ids=['t'])
        tasks=[task('a')];scope={'effective':'decision_frontier'}; self.assertEqual(review.append_new_tasks(tasks,scope,[task('a'),task('b'),task('b')]),[task('b')]); cat={'supplementary_alignments':tasks,'supplement_scope':scope};self.assertEqual(review.extra_count(cat),1)
        with self.assertRaises(Q0EvidenceError):review.extra_count(dict(cat,supplementary_alignments=tasks[::-1]))
        with self.assertRaises(Q0EvidenceError):review.verify_windows({'query':{'start':0,'end':2001,'cores':[[0,2001]]},'targets':[{'start':0,'end':400}]})

    @unittest.skipUnless(shutil.which('minimap2'),'requires real minimap2')
    def test_real_missing_flank_cache_and_selector_with_reverse_alt(self):
        rng=Random(123);truth=''.join(rng.choices('ACGT',k=10000)); seqs={p.source:(reverse_complement(truth[2400:7600]) if p==self.alt else truth[p.reference_intervals[0].start:p.reference_intervals[0].end]) for p in self.ps};parts={}
        by_source={}
        for k,seq in seqs.items():
            part,=split_source(k,seq).segments;parts[part.segment_id]=part;by_source[k]=part.segment_id
        ps=tuple(replace(p,segment_id=by_source[p.source]) for p in self.ps);r,s,g=self.plan(ps,links=[self.left_hit]);self.assertEqual(len(r.windows(s)),1)
        tool=executable_identity(shutil.which('minimap2'));cat=CandidateCatalog({},seqs,parts)
        with TemporaryDirectory() as d:
            root=Path(d);new=review.dispatch(r,s,root,cat,[],tool,'asm10',1,len(truth));self.assertEqual(len(new),1);receipt=mapping.verify_regional_task(root,new[0],members=parts);review.verify_windows(receipt['spec']); links=list(_supplement_links(root,parts,new,retained_geometry_cache(),1));self.assertTrue(links)
            aug=PathGraph(ps,[self.left_hit,*links]);self.assertTrue(any(j.kind=='sequence_overlap' for j in aug.joins('A','R')));self.assertIn('A',search_paths(aug).path.nodes)
            with patch.object(mapping,'_execute',side_effect=AssertionError('existing raw must not remap')):
                self.assertEqual(review.dispatch(r,s,root,cat,new,tool,'asm10',1,len(truth)),[])

    @unittest.skipUnless(shutil.which('minimap2'),'requires real minimap2')
    def test_full_preparation_adds_only_the_missing_local_flank_and_reloads(self):
        self._workspace_case(False)

    @unittest.skipUnless(shutil.which('minimap2'),'requires real minimap2')
    def test_review_precedes_cold_native_decision_and_accounts_for_its_projection(self):
        self._workspace_case(True)

    def _workspace_case(self, cold):
        from contextlib import ExitStack
        from server.tests.test_q0_admission import EvidenceFixture
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        from server.tools.lgz_core import q0_preparation as prep, q0_admission as admission
        from server.tools.lgz_core.q0_query_windows import QueryWindow, TargetWindow
        truth=''.join(Random(123).choices('ACGT',k=10000));f=EvidenceFixture({'chr1':len(truth)})
        for p in self.ps:
            ref,=p.reference_intervals;seq=truth[ref.start:ref.end];f.source(p.source.contig,seq if p.orientation=='+' else reverse_complement(seq));f.ref(p.source,(0,len(seq)),(ref.start,ref.end),strand=p.orientation)
        mapper=shutil.which('minimap2');tool=executable_identity(mapper)
        with TemporaryDirectory() as d:
            root=f.workspace(d);(root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n');outer=OuterCheckpointManager(root);outer.commit(outer.prepare('q0_chr:chr1','runs/chr_chr1/q0_command.sh'))
            data=f.data();parts={p.source.contig:p for p in data.parts.values()};c=CandidateCatalog({},data.sources,data.parts)
            a=parts['A'];l=parts['L'];q=QueryWindow(l.segment_id,3000,1000,3000,((1000,3000),));t=TargetWindow(a.segment_id,5200,3200,5200)
            known=mapping.prepare_regional_mapping(root,c,q,[t],tool,reference_bases=len(truth),threads=1)
            whole=dict(kind='partial_source_discovery',query_ids=sorted(data.parts),target_ids=sorted(data.parts),minimum_uncovered_bp=100)
            fallback=[a.segment_id] if cold else []
            def partial(*args,**kwargs):return [known], fallback, dict(frontier_scope=True,frontier_omitted_windows=0,completed_regional_tasks=1,fallback_sources=[{'segment_id':k} for k in fallback])
            native=prep._supplement
            def only_warm(*args,**kw):
                if args[2]['kind']=='partial_source_discovery':self.assertTrue(kw.get('cache_only'),'restarted native')
                return native(*args,**kw)
            with ExitStack() as patches:
                for k,opts in [('regional_enabled',{'return_value':True}),('partial_source_request',{'return_value':whole}),('prepare_partial',{'side_effect':partial}),('supplemental_groups',{'return_value':[]}),('_supplement',{'side_effect':only_warm})]:patches.enter_context(patch.object(prep,k,**opts))
                with patch.object(mapping,'_execute',wraps=mapping._execute) as spawn:
                    receipt=prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='positive_threshold');self.assertEqual(spawn.call_count,1)
            self.assertEqual(prep.load_verified_evidence(root),receipt);actual=admission.load_evidence_input(root);scope=actual.catalog['supplement_scope'];self.assertEqual(review.extra_count(actual.catalog),1);self.assertEqual(len(actual.catalog['supplementary_alignments']),2);self.assertEqual(bool(scope.get('deferred_native_matrices')),cold)
            result=admission.construct_q0(actual);self.assertEqual(result.records['chr1'],truth);self.assertEqual([j.kind for j in result.paths['chr1'].path.joins],['sequence_overlap','sequence_overlap']);self.assertIn(a.source,[s.source for s in result.paths['chr1'].path.slices]);
            with patch.object(mapping,'_execute',side_effect=AssertionError('warm resume launched a mapper')):self.assertEqual(prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='positive_threshold'),receipt)
