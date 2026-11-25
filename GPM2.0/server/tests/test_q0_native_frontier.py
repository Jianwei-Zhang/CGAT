"""Late native fallback: real decision PAFs, whole-matrix provenance and independent repair."""
from dataclasses import replace
import pickle
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
from server.tools.lgz_core.q0_native_frontier import FallbackGate, PHASES, descriptor, omitted, touches, validate_inventory
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError
from server.tools.lgz_core.q0_threshold_acceptance import ThresholdRepairRequired, audit
from server.tools.lgz_core.q0_threshold_questions import questions


class NativeFrontierTests(unittest.TestCase):
    def setUp(self):
        self.f,_=bridge_fixture(reverse=True); self.data=self.f.data(); self.parts=self.data.parts
        self.a,self.b,self.c = (next(p for p in self.parts.values() if p.source.contig==n) for n in 'abc')
        self.req={'kind':'partial_source_discovery','query_ids':[self.c.segment_id], 'target_ids':[self.b.segment_id,self.a.segment_id]}
        self.row=descriptor(PHASES[0],self.req['query_ids'],self.req['target_ids'])

    def test_completed_reverse_strand_bridges_refresh_real_selector_then_no_native(self):
        with TemporaryDirectory() as d:
            root=Path(d);f=self.f; parts=self.parts; seqs=self.data.sources
            for source in seqs:
                name=f'runs/{source.dataset}_vs_ref/result.paf'; p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text('\n'.join(f.raw.get(name,[]))+'\n')
            byname={p.source:p.segment_id for p in parts.values()};tasks=[]
            for i,link in enumerate(f.links):
                # A completed projected part PAF, not raw window coordinates or chaining.
                q,t=byname[link.query_source],byname[link.target_source];paf=f'grt/evidence/t{i}/result.paf';p=root/paf;p.parent.mkdir(parents=True)
                cols=f.raw[link.hit.artifact][link.hit.line_number-1].split('\t');cols[0]=q;cols[5]=t;p.write_text('\t'.join(cols)+'\n')
                tasks.append({'paf':paf,'query_ids':[q],'target_ids':[t]})
            initial,have=threshold.initial_questions(root,seqs,f.reference_lengths,[],[])
            self.assertTrue(initial and have); self.assertTrue(touches(self.row,parts,initial))
            catalog=CandidateCatalog({'original_connections':[]},seqs,parts)
            def refresh(completed):
                with patch.object(threshold,'split_source',side_effect=AssertionError('must reuse indexed sources')):
                    result=threshold.initial_questions(root,seqs,f.reference_lengths,[],[],existing_catalog=catalog,supplementary=completed)
                self.assertEqual(result,({},True)); return result
            gate=FallbackGate(parts,initial,Mock(side_effect=refresh));calls=[]
            def no_mapper(req,cache_only):
                calls.append((req,cache_only));self.assertTrue(cache_only);return None
            self.assertEqual(gate.dispatch(PHASES[0],[self.req],tasks,no_mapper),[])
            # Same artifact set in the following phase: do not redo graph selection.
            self.assertEqual(gate.dispatch(PHASES[1],[self.req],tasks,no_mapper),[])
            self.assertEqual(len(calls),2);gate.refresh.assert_called_once_with(tasks)
            self.assertEqual(gate.omissions[0],self.row)

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
            with patch.object(prep,'_prepare_evidence_pass',side_effect=AssertionError('valid new ready must be reusable')):
                self.assertEqual(prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='positive_threshold'),receipt)

            # Counterfactual control: full mode does execute this unchanged native matrix.
            # Compare delivered geometry/sequence, not file IDs from different inventories.
            with patch.object(prep,'regional_enabled',return_value=True), patch.object(prep,'partial_source_request',return_value=whole), \
                 patch.object(prep,'prepare_partial',side_effect=partial), patch.object(prep,'supplemental_groups',return_value=[]):
                full=prep.prepare_evidence(root,threads=1,minimap2=mapper,supplement_scope='full')
            fullcat=prep.json_file(root/full['catalog']);self.assertNotIn('supplement_scope',fullcat)
            natives=[t for t in fullcat['supplementary_alignments'] if t['kind']=='partial_source_discovery']
            self.assertEqual([(t['query_ids'],t['target_ids']) for t in natives],[([self.a.segment_id],all_targets)])
            control=adm.construct_q0(adm.load_evidence_input(root));self.assertEqual(control.records,result.records)
            geom=lambda x:[(v.source,v.interval,v.orientation) for v in x.paths['chr1'].path.slices]
            self.assertEqual(geom(control),geom(result))

    def test_target_only_full_matrix_and_forced_repair_never_shortlist(self):
        for need,have in (({self.a.source:(self.a.interval,)},True), (None,True), ({},False)):
            with self.subTest(need=need,have=have):
                gate=FallbackGate(self.parts,{},lambda _: (need,have)); call=Mock(side_effect=[None,{'paf':'completed'}])
                result=gate.dispatch(PHASES[0],[self.req],[{'paf':'real/project'}],call)
                self.assertEqual(result,[{'paf':'completed'}]); self.assertIs(call.call_args.args[0],self.req)
                self.assertFalse(call.call_args.args[1]); self.assertFalse(gate.omissions)
        forced=FallbackGate(self.parts,{},Mock(side_effect=AssertionError('forced original requires no draft')),forced=[self.row['id']]); call=Mock(side_effect=[None,{'paf':'fresh'}]);self.assertTrue(forced.dispatch(PHASES[0],[self.req],[],call))

    def test_cache_hits_precede_refresh_original_output_order_preserved(self):
        other={**self.req,'query_ids':[self.b.segment_id]}; hit={'paf':'warm'};fresh={'paf':'fresh'}
        refresh=Mock(return_value=(None,True));gate=FallbackGate(self.parts,{},refresh);fn=Mock(side_effect=[None,hit,fresh])
        self.assertEqual(gate.dispatch(PHASES[1],[self.req,other],[{'paf':'prior'}],fn),[fresh,hit]);refresh.assert_called_once_with([{'paf':'prior'},hit]);self.assertEqual([c.args[1] for c in fn.call_args_list],[True,True,False])
        refresh.reset_mock();self.assertEqual(gate.dispatch(PHASES[0],[self.req],[],Mock(return_value=hit)),[hit]);refresh.assert_not_called()

    def test_final_consumer_requires_only_newly_exposed_matrix_without_looping(self):
        data=replace(self.data,pair_links=()); need,_=questions(data,adm.select_q0_paths(data),[]);self.assertTrue(need)
        exposed=with_scope(data,need); report=exposed.catalog['supplement_scope'];report['deferred_native_matrices']=[self.row]
        exposed=replace(exposed,threshold_scope=replace(exposed.threshold_scope,report_identity=stable_id('threshold-search',report)))
        with self.assertRaisesRegex(ThresholdRepairRequired,'deferred native') as raised:audit(exposed,adm.select_q0_paths(exposed))
        self.assertEqual(pickle.loads(pickle.dumps(raised.exception)).native_ids,(self.row['id'],))
        class StopAfterRepair(Exception):pass
        with TemporaryDirectory() as d, patch.object(prep,'_readless_package'), patch.object(threshold,'initial_generation',return_value=('id',None,False,need)), patch.object(prep,'_prepare_evidence_pass',side_effect=[({'outputs':[]},None,None),StopAfterRepair]) as dispatch, patch.object(adm,'load_evidence_input',return_value=exposed), self.assertRaises(StopAfterRepair):
            threshold.prepare(Path(d),1,'unused')
        self.assertEqual(dispatch.call_args.kwargs['forced_native'],{self.row['id']});self.assertEqual(dispatch.call_args.kwargs['frontier_override'],need);self.assertIsNone(dispatch.call_args.kwargs['fallback_reason'])

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
