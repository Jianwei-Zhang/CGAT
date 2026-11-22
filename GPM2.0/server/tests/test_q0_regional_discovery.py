import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from server.tools.lgz_core import q0_preparation as prep
from server.tools.lgz_core import q0_regional_discovery as regional
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_catalog import CandidateCatalog, ObservedSourcePairs, build_catalog
from server.tools.lgz_core.q0_reference_index import ReferenceIndex
from server.tools.lgz_core.q0_sources import SourceKey, Interval, split_source, Q0EvidenceError


class RegionalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.sources={SourceKey('a','q'):'A'*300000,SourceKey('b','t'):'C'*300000}
        self.parts={p.segment_id:p for key,seq in self.sources.items() for p in split_source(key,seq).segments}
        self.ids={p.source.contig:key for key,p in self.parts.items()}
        self.catalog=CandidateCatalog({'candidates':[]},self.sources,self.parts)
        self.observed=ObservedSourcePairs({key:len(seq) for key,seq in self.sources.items()})

    def test_internal_trigger_is_large_reference_and_calibrated_preset_only(self):
        self.assertFalse(regional.enabled({'c':4999999999},'asm10'))
        self.assertFalse(regional.enabled({'c':5000000000},'asm5'))
        self.assertTrue(regional.enabled({'c':5000000000},'asm10'))

    def test_native_cache_probe_never_launches_or_writes_incomplete_mapping(self):
        tool={'resolved':sys.executable,'sha256':prep.sha256_file(Path(sys.executable))}
        request={'kind':'partial_source_discovery','query_ids':[self.ids['q']],'target_ids':[self.ids['t']]}
        with mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('must not launch')):
            self.assertIsNone(prep._supplement(self.root,self.catalog,request,tool,'asm10',1,cache_only=True))
        self.assertFalse((self.root/'grt').exists())

    def test_completed_hit_observation_precedes_candidate_filter_and_tracks_both_sides(self):
        q,t=self.ids['q'],self.ids['t']
        hit=parse_paf_line(f'{q}\t300000\t100\t300\t-\t{t}\t300000\t200\t400\t200\t200\t0\tcg:Z:200M',artifact='done.paf',line_number=1)
        self.assertEqual(list(regional.observe_part_hits(self.catalog,[hit],self.observed)),[hit])
        self.assertEqual(tuple(self.observed.cross_coverage[SourceKey('a','q')]),(Interval(100,300),))
        self.assertEqual(tuple(self.observed.cross_coverage[SourceKey('b','t')]),(Interval(200,400),))

    def test_native_fallback_subsumes_parent_without_launching_earlier_window(self):
        index=mock.Mock();index.parts=self.parts;index.regions.return_value={'chr':(Interval(0,100),)}
        index.targets.side_effect=[{self.ids['t']:(Interval(0,1000),)},{}]
        holes={self.ids['q']:(Interval(0,300000),)}
        with mock.patch.object(regional,'partial_source_intervals',return_value=holes), \
             mock.patch.object(regional,'prepare_regional_mapping',side_effect=AssertionError('parent fallback must not map windows')):
            tasks,fallback,report=regional.prepare_partial(self.root,self.catalog,index,self.observed,{},reference_lengths={'chr':5_000_000_000},preset='asm10',threads=8)
        self.assertEqual(tasks,[]);self.assertEqual(fallback,[self.ids['q']])
        self.assertEqual(report['fallback_sources'][0]['reason'],'no_reference_targets')
        index.verify_inputs.assert_called_once()

    def test_pool_never_multiplies_run_thread_budget_and_keeps_order(self):
        index=mock.Mock();index.parts=self.parts;index.regions.return_value={'chr':(Interval(0,100),)}
        index.targets.return_value={self.ids['t']:(Interval(0,1000),)}
        holes={self.ids['q']:(Interval(0,300000),)}
        active=peak=0;lock=threading.Lock()
        def mapper(root,catalog,query,targets,tool,**kwargs):
            nonlocal active,peak
            with lock:active+=kwargs['threads'];peak=max(peak,active)
            time.sleep(.02)
            with lock:active-=kwargs['threads']
            return {'core':query.cores[0][0]}
        with mock.patch.object(regional,'partial_source_intervals',return_value=holes), \
             mock.patch.object(regional,'prepare_regional_mapping',side_effect=mapper):
            tasks,fallback,report=regional.prepare_partial(self.root,self.catalog,index,self.observed,{},reference_lengths={'chr':5_000_000_000},preset='asm10',threads=3,skip_self=True)
        self.assertLessEqual(peak,3);self.assertEqual(fallback,[])
        self.assertEqual([t['core'] for t in tasks],[0,100000,200000])
        self.assertEqual(report['completed_regional_tasks'],3)

    def test_ready_mapper_refills_pool_while_oldest_waits_and_output_stays_ordered(self):
        index=mock.Mock();index.parts=self.parts
        index.regions.return_value={'chr':(Interval(0,100),)}
        index.targets.return_value={self.ids['t']:(Interval(0,1000),)}
        third_started=threading.Event(); finished=[]; lock=threading.Lock()
        def mapper(root,catalog,query,targets,tool,**kwargs):
            core=query.cores[0][0]
            if core==0:self.assertTrue(third_started.wait(3),'ready second mapper must refill third slot')
            if core==200000:third_started.set()
            with lock:finished.append(core)
            return {'core':core}
        with mock.patch.object(regional,'partial_source_intervals',return_value={self.ids['q']:(Interval(0,300000),)}), \
             mock.patch.object(regional,'prepare_regional_mapping',side_effect=mapper):
            tasks,fallback,report=regional.prepare_partial(self.root,self.catalog,index,self.observed,{},
                reference_lengths={'chr':5_000_000_000},preset='asm10',threads=6)
        self.assertEqual(report['maximum_workers'],2)
        self.assertEqual(finished[0],100000)
        self.assertEqual([row['core'] for row in tasks],[0,100000,200000])
        self.assertEqual(fallback,[])

    def test_completion_parent_fallback_restores_original_report_order(self):
        index=mock.Mock();index.parts=self.parts
        holes={key:(Interval(0,100),) for key in self.parts}
        def reversed_plans(runner,requests):
            values=list(enumerate(requests))
            for ordinal,request in reversed(values):yield ordinal,request,([],0,'no_reference_targets')
        with mock.patch.object(regional,'partial_source_intervals',return_value=holes), \
             mock.patch.object(regional.RegionalExecutor,'completed',reversed_plans), \
             mock.patch.object(regional,'prepare_regional_mapping',side_effect=AssertionError('fallback cannot map')):
            tasks,fallback,report=regional.prepare_partial(self.root,self.catalog,index,self.observed,{},
                reference_lengths={'chr':5_000_000_000},preset='asm10',threads=6)
        self.assertEqual(tasks,[]);self.assertEqual(fallback,sorted(self.parts))
        self.assertEqual([row['segment_id'] for row in report['fallback_sources']],sorted(self.parts))

    def test_one_thread_never_overlaps_owner_planning_with_mapper(self):
        index=mock.Mock();index.parts=self.parts
        holes={self.ids['q']:(Interval(0,100),),self.ids['t']:(Interval(0,100),)}
        active=threading.Event();started=threading.Event();calls=0
        def plan(catalog,index,windows):
            nonlocal calls
            calls+=1
            if calls==2:
                self.assertTrue(started.wait(2))
                self.assertFalse(active.is_set(), 'one CPU cannot plan while mapper computes')
            query=next(iter(windows))
            return [(query,[])],None  # The fake mapper never reads DNA/targets.
        def mapper(*args,**kwargs):
            self.assertEqual(kwargs['threads'],1)
            active.set();started.set();time.sleep(.03);active.clear()
            return {'done':True}
        with mock.patch.object(regional,'partial_source_intervals',return_value=holes), \
             mock.patch.object(regional,'plan_parent',side_effect=plan), \
             mock.patch.object(regional,'prepare_regional_mapping',side_effect=mapper):
            tasks,fallback,report=regional.prepare_partial(self.root,self.catalog,index,self.observed,{},
                reference_lengths={'chr':5_000_000_000},preset='asm10',threads=1)
        self.assertEqual(len(tasks),2);self.assertEqual(fallback,[])
        self.assertEqual(report['maximum_workers'],1)

    def test_sealed_cache_is_local_content_bound_and_corruption_preserved(self):
        refs={'chr':1_000_000};paths=[]
        for source in self.sources:
            rel=f'runs/{source.dataset}_vs_ref/result.paf';p=self.root/rel;p.parent.mkdir(parents=True)
            p.write_text(f'{source.contig}\t300000\t0\t100\t+\tchr\t1000000\t0\t100\t100\t100\t60\tcg:Z:100M\n');paths.append(rel)
        inputs=[prep.identity(self.root,p) for p in paths]
        with regional.LocalReferenceCache(self.root,inputs) as cache:
            first=build_catalog(self.root,self.sources,refs,[],regional_factory=cache.factory)
            cache.publish();durable=cache.directory
            self.assertFalse(cache.path.is_relative_to(self.root));self.assertTrue((durable/'success.json').is_file())
        with regional.LocalReferenceCache(self.root,inputs) as cache:
            with mock.patch.object(ReferenceIndex,'observe_record',side_effect=AssertionError('sealed records must be reused')):
                second=build_catalog(self.root,self.sources,refs,[],regional_factory=cache.factory)
            cache.publish();self.assertTrue(cache.cached);self.assertEqual(first.payload,second.payload)
        (durable/'reference.sqlite').write_bytes(b'corrupted')
        with regional.LocalReferenceCache(self.root,inputs) as cache:
            build_catalog(self.root,self.sources,refs,[],regional_factory=cache.factory);cache.publish()
        archived=list(durable.parent.glob(durable.name+'.invalid-*'))
        self.assertEqual(len(archived),1);self.assertEqual((archived[0]/'reference.sqlite').read_bytes(),b'corrupted')

    def test_regional_utilities_import_without_outer_workflow_and_keep_injection_point(self):
        package=self.root/'package';(package/'lgz_core').mkdir(parents=True)
        tools=Path(prep.__file__).parent
        names=['common','q0_sources','q0_alignments','q0_catalog','q0_preparation','q0_reference_index',
               'q0_query_windows','q0_cigar_policy','q0_regional_mapping','q0_mapper_guard','q0_regional_discovery','q0_neighbor_requests','q0_regional_candidates','q0_regional_execution','q0_frontier_scope']
        (package/'lgz_core/__init__.py').write_text('')
        for name in names:shutil.copyfile(tools/f'{name}.py',package/f'lgz_core/{name}.py')
        shutil.copyfile(tools.parent/'run_orchestration.py',package/'run_orchestration.py')
        code="import sys;sys.path.insert(0,sys.argv[1]);from lgz_core import q0_preparation as p;assert callable(p.OuterCheckpointManager);assert 'run_outer_checkpoints' not in sys.modules"
        subprocess.run([sys.executable,'-I','-c',code,str(package)],check=True,capture_output=True,text=True)


if __name__=='__main__':unittest.main()
