"""Late native fallback: real decision PAFs, whole-matrix provenance and independent repair."""
from dataclasses import replace
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from server.tests.test_q0_admission import bridge_fixture
from server.tests.test_q0_threshold_acceptance import with_scope
from server.tools.lgz_core import q0_admission as adm, q0_preparation as prep
from server.tools.lgz_core import q0_threshold_prepare as threshold
from server.tools.lgz_core.common import stable_id
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.q0_native_frontier import CACHE_ONLY, RegionalFallbackCache, prefer_cached_whole, PHASES, descriptor, omitted, touches, validate_inventory
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals
from server.tools.lgz_core.q0_threshold_acceptance import audit
from server.tools.lgz_core.q0_threshold_questions import questions


class NativeFrontierTests(unittest.TestCase):
    def setUp(self):
        self.f,_=bridge_fixture(reverse=True); self.data=self.f.data(); self.parts=self.data.parts
        self.a,self.b,self.c = (next(p for p in self.parts.values() if p.source.contig==n) for n in 'abc')
        self.req={'kind':'partial_source_discovery','query_ids':[self.c.segment_id], 'target_ids':[self.b.segment_id,self.a.segment_id]}
        self.row=descriptor(PHASES[0],self.req['query_ids'],self.req['target_ids'])

    def test_cache_only_dispatch_keeps_verified_hits_never_executes_a_miss(self):
        other={**self.req,'query_ids':[self.b.segment_id]}; hit={'paf':'existing'}
        for phase in PHASES:
            gate=RegionalFallbackCache(bounded=True); probe=Mock(side_effect=[None,hit])
            self.assertEqual(gate.dispatch(phase,[self.req,other],probe),[hit]);self.assertEqual(probe.call_count,2)
            self.assertEqual(gate.omissions,[descriptor(phase,self.req['query_ids'],self.req['target_ids'])])
            strict=RegionalFallbackCache(bounded=False)
            with self.assertRaisesRegex(Q0EvidenceError,'automatic whole-source regional fallback is disabled'):
                strict.dispatch(phase,[self.req],Mock(return_value=None))

    def test_routable_siblings_are_only_superseded_by_complete_matching_native_scope(self):
        rows=[dict(query_ids=['a'],target_ids=[t]) for t in ('t','u')]; report={}
        whole=[dict(query_ids=['a','b'],target_ids=['t'])]
        self.assertEqual(prefer_cached_whole(rows,whole,report),[rows[1],*whole]);self.assertEqual(report['completed_regional_tasks'],1)
        self.assertIs(prefer_cached_whole(rows,[],{}),rows)

    @unittest.skipUnless(shutil.which('minimap2'), 'requires minimap2')
    def test_verified_regional_cache_repairs_draft_before_native_and_ready_reloads(self):
        from server.tools.lgz_core import q0_regional_mapping as m
        from server.tools.lgz_core.q0_query_windows import QueryWindow, TargetWindow
        mapper=shutil.which('minimap2'); f,truth=bridge_fixture(reverse=True)
        f.links.clear();f.raw={k:v for k,v in f.raw.items() if '_vs_ref/' in k}
        with TemporaryDirectory() as d:
            root=f.workspace(d); (root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n')
            from server.tools.run_outer_checkpoints import OuterCheckpointManager
            outer=OuterCheckpointManager(root);outer.commit(outer.prepare('q0_chr:chr1','runs/chr_chr1/q0_command.sh'))
            data=f.data(); cat=CandidateCatalog({'original_connections':[]},data.sources,data.parts); tool=prep.executable_identity(mapper)
            q=self.c;query=QueryWindow(q.segment_id,q.interval.length,0,q.interval.length,((0,q.interval.length),))
            def regions(catalog):
                return [m.prepare_regional_mapping(root,catalog,query,[TargetWindow(p.segment_id,p.interval.length,0,p.interval.length)],tool,
                            reference_bases=5000,threads=1) for p in (self.a,self.b)]
            cached=regions(cat); self.assertTrue(all((root/t['paf']).stat().st_size for t in cached))
            all_targets=sorted(data.parts); whole=dict(kind='partial_source_discovery',query_ids=all_targets,target_ids=all_targets,minimum_uncovered_bp=100)
            def partial(root_,catalog,*args,**kwargs):
                self.assertEqual(kwargs['required_target_ids'],all_targets)
                with patch.object(m.subprocess,'Popen',side_effect=AssertionError('cached regional work must not respawn')):
                    tasks=regions(catalog)
                self.assertEqual(tasks,cached)
                return tasks,[self.a.segment_id],dict(frontier_scope=kwargs['regional_frontier'] is not None,frontier_omitted_windows=0,completed_regional_tasks=2,
                         fallback_sources=[{'segment_id':self.a.segment_id,'reason':'regional_target_budget'}])
            native=prep._supplement;checks=[]
            def intercept(r,catalog,request,*args,**kwargs):
                if request['kind']=='partial_source_discovery':
                    self.assertTrue(kwargs.get('cache_only'), 'unexpected native mapper');checks.append(tuple(request['query_ids']))
                return native(r,catalog,request,*args,**kwargs)
            with patch.object(prep,'regional_enabled',return_value=True), patch.object(prep,'partial_source_request',return_value=whole), \
                 patch.object(prep,'prepare_partial',side_effect=partial), patch.object(prep,'supplemental_groups',return_value=[]), \
                 patch.object(prep,'_supplement',side_effect=intercept):
                receipt=prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='positive_threshold')
            self.assertEqual(checks,[tuple(all_targets),(self.a.segment_id,)])
            self.assertEqual(prep.load_verified_evidence(root),receipt); result=adm.construct_q0(adm.load_evidence_input(root))
            self.assertEqual(result.records['chr1'],truth)
            out=prep.json_file(root/receipt['catalog']);self.assertEqual(out['supplementary_alignments'],cached)
            self.assertEqual(out['supplement_scope']['deferred_native_matrices'],[descriptor(PHASES[0],[self.a.segment_id],all_targets)])
            self.assertEqual(out['supplement_scope']['native_fallback_policy'],CACHE_ONLY)
            self.assertFalse((root/'grt/evidence/q0_prepare/native_decisions').exists())  # No second draft just to decide whether to search.
            with patch.object(prep,'_prepare_evidence_pass',side_effect=AssertionError('valid new ready must be reusable')):
                self.assertEqual(prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='positive_threshold'),receipt)

            # A strict request may not publish a false full result or launch the mapper.
            with patch.object(prep,'regional_enabled',return_value=True), patch.object(prep,'partial_source_request',return_value=whole), \
                 patch.object(prep,'prepare_partial',side_effect=partial), patch.object(prep,'supplemental_groups',return_value=[]), \
                 patch.object(prep,'_supplement',side_effect=intercept), self.assertRaisesRegex(Q0EvidenceError,'whole-source regional fallback is disabled'):
                prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='full')
            self.assertEqual(prep.load_verified_evidence(root),receipt)

    def test_cold_whole_matrix_can_publish_a_bounded_q0_with_its_real_gap_left_open(self):
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        f,_=bridge_fixture(reverse=True);f.links.clear();f.raw={k:v for k,v in f.raw.items() if '_vs_ref/' in k}
        with TemporaryDirectory() as d:
            root=f.workspace(d);(root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n')
            outer=OuterCheckpointManager(root);outer.commit(outer.prepare('q0_chr:chr1','runs/chr_chr1/q0_command.sh'))
            all_ids=sorted(self.parts); request=dict(kind='partial_source_discovery',query_ids=all_ids,target_ids=all_ids,minimum_uncovered_bp=100)
            def partial(*args,**kwargs):
                return [],[self.a.segment_id],dict(frontier_scope=kwargs['regional_frontier'] is not None,
                    frontier_omitted_windows=0,completed_regional_tasks=0,fallback_sources=[{'segment_id':self.a.segment_id,'reason':'no_reference_targets'}])
            actual=prep._supplement
            def only_cache(*args,**kwargs):
                self.assertTrue(kwargs.get('cache_only'), 'attempted cold native alignment')
                return actual(*args,**kwargs)
            tool=str(Path(d)/'q0-fixture-bin/minimap2')
            with patch.object(prep,'regional_enabled',return_value=True),patch.object(prep,'partial_source_request',return_value=request), \
                 patch.object(prep,'prepare_partial',side_effect=partial),patch.object(prep,'supplemental_groups',return_value=[]), \
                 patch.object(prep,'_supplement',side_effect=only_cache):
                receipt=prep.prepare_evidence(root,threads=1,minimap2=tool,supplement_scope='positive_threshold')
            self.assertEqual(prep.load_verified_evidence(root),receipt)
            result=adm.construct_q0(adm.load_evidence_input(root)); acceptance=result.decisions['supplement_acceptance']
            self.assertFalse(acceptance['alternatives_exhaustive']);self.assertGreater(acceptance['decision_counts']['unproven_join'],0)
            self.assertEqual(acceptance['decision_counts']['unsearched_whole_source_matrices'],1)
            self.assertIn('N',result.records['chr1']);self.assertEqual(prep.json_file(root/receipt['catalog'])['supplementary_alignments'],[])

    def test_remaining_gaps_stay_unproven_without_forcing_a_native_matrix(self):
        data=replace(self.data,pair_links=()); selection=adm.select_q0_paths(data); need,expected=questions(data,selection,[])
        exposed=with_scope(data,need); report=exposed.catalog['supplement_scope'];report.update(deferred_native_matrices=[self.row],native_fallback_policy=CACHE_ONLY)
        exposed=replace(exposed,threshold_scope=replace(exposed.threshold_scope,report_identity=stable_id('threshold-search',report)))
        counts=audit(exposed,selection);self.assertEqual(counts['unproven_join'],expected['unproven_join']);self.assertGreater(counts['unproven_join'],0)
        self.assertEqual(counts['unsearched_whole_source_matrices'],1)
        def missing(*args,issue_sink,**kwargs):
            issue_sink({'kind':'missing_chromosome_part','spans':[[self.a.source.dataset,self.a.source.contig,0,3]]})
            return {self.a.source:(self.a.interval,)},{}
        with patch('server.tools.lgz_core.q0_threshold_questions.questions',side_effect=missing),self.assertRaisesRegex(Q0EvidenceError,'required Q0 chromosome'):
            audit(exposed,selection)
        del report['native_fallback_policy'];bare=replace(exposed,threshold_scope=replace(exposed.threshold_scope,report_identity=stable_id('threshold-search',report)))
        with self.assertRaisesRegex(Q0EvidenceError,'unbound deferred'):audit(bare,selection)

    def test_optional_issue_list_reproduces_unresolved_intervals_without_changing_decisions(self):
        data=replace(self.data,pair_links=()); chosen=adm.select_q0_paths(data); original=questions(data,chosen,[])
        rows=[]; self.assertEqual(questions(data,chosen,[],issue_sink=rows.append),original)
        self.assertTrue(any(r['kind']=='unproven_join' and len(r['placement_ids'])==2 for r in rows))
        by_source={}
        for row in rows:
            self.assertEqual(row['groups'],['chr1']);self.assertTrue(row['id'])
            for ds,contig,lo,hi in row['spans']: by_source.setdefault(SourceKey(ds,contig),[]).append(Interval(lo,hi))
        self.assertEqual({k:merged_intervals(v) for k,v in by_source.items()},original[0])

    def test_augmented_inputs_cannot_reuse_a_base_selection_checkpoint(self):
        with self.assertRaisesRegex(Q0EvidenceError,'base-only selection checkpoint'):
            threshold.initial_questions(Path('/unused'),{}, {},[],[],supplementary=[{'paf':'new'}],selection_checkpoint=object())

    def test_phase_conservation_and_part_frame_boundaries(self):
        k=self.a.segment_id; split=replace(self.a,interval=Interval(50,100));row=descriptor(PHASES[0],[k],[k]);self.assertFalse(touches(row,{k:split},{split.source:(Interval(0,50),)}));self.assertTrue(touches(row,{k:split},{split.source:(Interval(49,51),)}))
        s={'effective':'decision_frontier','deferred_native_matrices':[self.row]};phase={'fallback_sources':[{'segment_id':self.c.segment_id}], 'native_fallback_matrix_ids':[self.row['id']]}
        cat={'segments':[{'segment_id':k} for k in self.parts], 'supplement_scope':s, PHASES[0]:phase, 'supplementary_alignments':[]};validate_inventory(cat)
        for bad in ([{**self.row,'target_ids':[]}],[{**self.row,'target_ids':self.row['target_ids'][:1]}],[self.row,self.row]):
            with self.assertRaises(Q0EvidenceError):omitted({**s,'deferred_native_matrices':bad},self.parts)
        with self.assertRaises(Q0EvidenceError):validate_inventory({**cat,'supplement_scope':{'effective':'decision_frontier'}})
        with self.assertRaises(Q0EvidenceError):validate_inventory({**cat,'supplementary_alignments':[self.req]})
        with self.assertRaises(Q0EvidenceError):omitted({**s,'effective':'full'},self.parts)


if __name__=='__main__':unittest.main()
