"""Limited weak-seed policy: never mask native short-query/short-target work."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.tools.lgz_core.q0_cigar_policy import weak_global_seed_scope, WEAK_GLOBAL_SEED_POLICY
from server.tools.lgz_core.q0_regional_candidates import CompletedNativeScopes
from server.tools.lgz_core.q0_regional_mapping import BASE_FLAGS
from server.tools.lgz_core.q0_sources import Interval, SourceKey, split_source, Q0EvidenceError
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.common import stable_id, sha256_file
from server.tools.lgz_core import q0_preparation as prep


class WeakSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.parts={key:SimpleNamespace(interval=Interval(0,length),sequence_sha256='a'*64)
                    for key,length in {'long':50000,'short':702,'tiny_target':1000,'big_target':5_000_000_000}.items()}
        self.catalog=SimpleNamespace(parts=self.parts,reference_routable_parts={'big_target','tiny_target'})
        self.index=SimpleNamespace(part_order=tuple(sorted(self.parts)),
            part_ranks={key:i for i,key in enumerate(sorted(self.parts))},reference_lengths={'ref':5_000_000_000},verify_inputs=lambda:None)
        self.queries=['long','short'];self.targets=sorted(self.parts)

    def scope(self,**kwargs):
        options={'reference_bases':5_000_000_000,'preset':'asm10',**kwargs}
        return weak_global_seed_scope(self.parts,self.catalog.reference_routable_parts,self.queries,self.targets,**options)

    def task(self,queries,targets,fast=False):
        spec={'schema':'lgz_q0_mapping_v1','query_ids':sorted(queries),'target_ids':sorted(targets),
              'members':[[k,self.parts[k].sequence_sha256] for k in sorted(set(queries+targets))],
              'tool':{},'preset':'asm10','alignment_flags':[*BASE_FLAGS,*(['-m','2000'] if fast else [])]}
        key=stable_id('q0-map',spec);relative=f'grt/evidence/q0_prepare/tasks/{key}'
        directory=self.root/relative;directory.mkdir(parents=True,exist_ok=True)
        for name in prep.MAPPING_OUTPUT_FILES:(directory/name).write_text('')
        (directory/'success.json').write_text(json.dumps({'status':'success','spec':spec,
            'outputs':[prep.identity(self.root,relative+'/'+name) for name in prep.MAPPING_OUTPUT_FILES]}))
        return {'task_id':key,'kind':'candidate_unroutable_seed','query_ids':spec['query_ids'],'target_ids':spec['target_ids'],
                'paf':relative+'/result.paf','receipt':relative+'/success.json'}

    def planner(self,tasks=()):return CompletedNativeScopes(self.root,self.catalog,self.index,tasks,{},'asm10')

    def test_short_query_and_short_target_are_both_outside_approximate_scope(self):
        queries,targets=self.scope()
        self.assertEqual(queries,('long',));self.assertEqual(set(targets),{'long','big_target'})

    def test_large_reference_large_target_and_preset_are_required(self):
        self.assertEqual(self.scope(reference_bases=4_999_999_999),((),()))
        self.assertEqual(self.scope(preset='asm5'),((),()))
        self.targets=['long','short','tiny_target'];self.assertEqual(self.scope(),((),()))

    def test_qualified_or_unknown_reference_status_retains_native(self):
        self.catalog.reference_routable_parts.add('long');self.assertEqual(self.scope(),((),()))
        self.catalog.reference_routable_parts=None;self.assertEqual(self.scope(),((),()))

    def test_maximum_query_and_batch_limits_are_not_silently_widened(self):
        self.parts['long'].interval=Interval(0,1_000_001);self.assertEqual(self.scope(),((),()))
        self.parts['long'].interval=Interval(0,1_000_000)
        self.queries=[]
        for i in range(9):
            key=f'q{i}';self.parts[key]=SimpleNamespace(interval=Interval(0,1_000_000));self.queries.append(key)
        self.assertEqual(self.scope(),((),()))

    def test_empty_and_short_only_cohorts_do_not_enable_fast_mapping(self):
        self.queries=[];self.assertEqual(self.scope(),((),()))
        self.queries=['short'];self.assertEqual(self.scope()[0],())

    def test_exact_floor_is_eligible(self):
        self.parts['long'].interval=Interval(0,20000);self.assertEqual(self.scope()[0],('long',))
        self.parts['long'].interval=Interval(0,19999);self.assertEqual(self.scope()[0],())

    def test_fast_matrix_does_not_claim_short_negative_relationships(self):
        fast=self.task(self.queries,self.targets,True);scopes=self.planner([fast]);all_targets=scopes.mask(self.targets)
        self.assertEqual(set(scopes.keys(scopes.remaining_targets('long',all_targets))),{'short','tiny_target'})
        self.assertEqual(set(scopes.keys(scopes.remaining_targets('short',all_targets))),{'long','tiny_target','big_target'})
        self.assertEqual(scopes.approximate_scope_task_ids,[fast['task_id']])

    def test_native_short_queries_then_small_target_remainder_complete_all_edges(self):
        scopes=self.planner([self.task(self.queries,self.targets,True)])
        request=scopes.next_missing_seed(self.queries,self.targets)
        self.assertEqual(request['query_ids'],['short']);self.assertEqual(set(request['target_ids']),set(self.targets))
        scopes.add_complete_tasks([self.task(request['query_ids'],request['target_ids'])])
        request=scopes.next_missing_seed(self.queries,self.targets)
        self.assertEqual(request['query_ids'],['tiny_target']);self.assertEqual(request['target_ids'],['long'])
        self.assertTrue(request['native_short_targets_as_queries'])
        scopes.add_complete_tasks([self.task(request['query_ids'],request['target_ids'])])
        self.assertIsNone(scopes.next_missing_seed(self.queries,self.targets))

    def test_large_normal_query_is_not_added_for_a_batch_key(self):
        self.parts['long'].interval=Interval(0,10_000_000)
        request=self.planner().next_missing_seed(['long'],['tiny_target'])
        self.assertEqual(request['query_ids'],['tiny_target']);self.assertEqual(request['target_ids'],['long'])

    def test_unknown_profile_and_wrong_scope_kind_are_rejected(self):
        task=self.task(self.queries,self.targets,True);task['kind']='partial_source_discovery'
        with self.assertRaisesRegex(Q0EvidenceError,'profile'):self.planner([task])
        task['kind']='candidate_unroutable_seed';self.index.reference_lengths={'ref':1000}
        with self.assertRaisesRegex(Q0EvidenceError,'scope'):self.planner([task])

    def test_native_cache_wins_before_any_fast_selection(self):
        request={'kind':'candidate_unroutable_seed','query_ids':self.queries,'target_ids':self.targets}
        native={'task_id':'already-complete-native'}
        with patch.object(prep,'_supplement',return_value=native) as run:
            self.assertIs(prep._unroutable_seed(self.root,self.catalog,request,{},'asm10',32,reference_bases=5_000_000_000),native)
        self.assertEqual(run.call_count,1);self.assertTrue(run.call_args.kwargs['cache_only'])

    def test_automatic_selection_does_not_need_a_user_large_data_flag(self):
        request={'kind':'candidate_unroutable_seed','query_ids':self.queries,'target_ids':self.targets}
        with patch.object(prep,'_supplement',side_effect=[None,{'task_id':'fast'}]) as run:
            prep._unroutable_seed(self.root,self.catalog,request,{},'asm10',32,reference_bases=5_000_000_000)
        self.assertTrue(run.call_args.kwargs['weak_seed_fast'])
        self.assertTrue(all(c.kwargs['cache_only'] for c in run.call_args_list))
        request['query_ids']=['short']
        with patch.object(prep,'_supplement',side_effect=[None,{'task_id':'native'}]) as run:
            prep._unroutable_seed(self.root,self.catalog,request,{},'asm10',32,reference_bases=5_000_000_000)
        self.assertFalse(run.call_args.kwargs['weak_seed_fast'])


    def test_short_side_cold_completion_never_relanches_native_search(self):
        request={'kind':'candidate_unroutable_seed','query_ids':['tiny_target'],'target_ids':['long'],
                 'native_short_targets_as_queries':True}
        with patch.object(prep,'_supplement',return_value=None) as run:
            self.assertIsNone(prep._unroutable_seed(self.root,self.catalog,request,{},'asm10',32,reference_bases=5_000_000_000))
        self.assertEqual(run.call_count,1);self.assertTrue(run.call_args.kwargs['cache_only'])

    def test_cold_first_cohort_does_not_hide_a_later_verified_hit(self):
        first=self.task(['long'],['tiny_target'])
        warm=self.task(['long'],['big_target','long','short'])
        tasks=[first];calls=[]
        def probe(root,catalog,request,tool,preset,threads,**kwargs):
            pair=(tuple(request['query_ids']),tuple(request['target_ids']));calls.append(pair)
            if pair==(tuple(warm['query_ids']),tuple(warm['target_ids'])):return warm
            return None
        with patch.object(prep,'_unroutable_seed',side_effect=probe),patch.object(prep,'add_pairwise_candidates',return_value=set()):
            scopes=prep._complete_unroutable_seeds(self.root,self.catalog,self.index,self.queries,self.targets,
                tasks,set(),{},'asm10',32,reference_bases=5_000_000_000,skip_self=False)
        self.assertEqual(calls[0],(('short',),tuple(self.targets)))  # The highest priority cohort is cold.
        self.assertEqual(tasks,[first,warm]);self.assertEqual(len(calls),len(set(calls)))
        self.assertEqual(calls[1:],[(tuple(warm['query_ids']),tuple(warm['target_ids']))])  # No probe for absent shapes.
        self.assertEqual(scopes.keys(scopes.remaining_targets('short',scopes.mask(self.targets))),['big_target','tiny_target'])

    def test_all_cold_does_not_expand_every_absent_matrix_or_replan(self):
        first=self.task(['long'],['tiny_target']);scopes=self.planner([first]); before=list(scopes.scopes)
        with patch.object(scopes,'_seed_groups',wraps=scopes._seed_groups) as groups, \
             patch.object(scopes,'_cached_seed_shapes',wraps=scopes._cached_seed_shapes) as inventory, \
             patch.object(scopes,'_seed_request',wraps=scopes._seed_request) as expanded:
            rows=list(scopes.missing_seed_requests(self.queries,self.targets))
        self.assertEqual((groups.call_count,inventory.call_count,expanded.call_count),(1,1,1))
        self.assertEqual(len(rows),1);self.assertEqual(scopes.scopes,before)

    def test_cache_inventory_keeps_short_side_direction_and_skips_invalid_receipts(self):
        scopes=self.planner(); warm=self.task(['tiny_target'],['long']); target=scopes.mask(['tiny_target'])
        bad=self.root/'grt/evidence/q0_prepare/tasks'/('q0-map-'+'0'*24)
        bad.mkdir();(bad/'success.json').write_text('not JSON')
        with patch.object(scopes,'_seed_groups',return_value=[(('short',),target),(('long',),target)]):
            rows=list(scopes.missing_seed_requests(self.queries,self.targets))
        self.assertEqual(len(rows),2);self.assertTrue(rows[1]['native_short_targets_as_queries'])
        self.assertEqual((rows[1]['query_ids'],rows[1]['target_ids']),(warm['query_ids'],warm['target_ids']))
        self.assertFalse(scopes.scopes)  # A receipt shape alone has never admitted a matrix.

    def complete_cohort(self):
        tasks=[]
        def mapper(root,catalog,request,tool,preset,threads,**kwargs):
            queries,targets=weak_global_seed_scope(self.parts,self.catalog.reference_routable_parts,
                request['query_ids'],request['target_ids'],reference_bases=kwargs['reference_bases'],preset=preset)
            return self.task(request['query_ids'],request['target_ids'],bool(queries and targets))
        def consume(catalog,hits,*args,**kwargs):
            self.assertEqual(list(hits),[]);return set()
        with patch.object(prep,'_unroutable_seed',side_effect=mapper),patch.object(prep,'add_pairwise_candidates',side_effect=consume):
            scopes=prep._complete_unroutable_seeds(self.root,self.catalog,self.index,self.queries,self.targets,
                tasks,set(),{},'asm10',32,reference_bases=5_000_000_000,skip_self=False)
        return tasks,scopes

    def test_coordinator_completes_fast_short_query_and_short_target_work_without_repeat(self):
        tasks,scopes=self.complete_cohort()
        self.assertEqual(len(tasks),3)
        self.assertEqual(tasks[0]['query_ids'],['long','short'])
        self.assertEqual(tasks[1]['query_ids'],['short'])
        self.assertEqual(tasks[2]['query_ids'],['tiny_target']);self.assertEqual(tasks[2]['target_ids'],['long'])
        self.assertEqual(len(scopes.approximate_scope_task_ids),1)
        self.assertIsNone(scopes.next_missing_seed(self.queries,self.targets))

    def test_partial_report_does_not_relabel_approximate_reuse_as_native(self):
        from server.tools.lgz_core import q0_regional_discovery as partial
        from server.tools.lgz_core.q0_catalog import ObservedSourcePairs
        tasks,scopes=self.complete_cohort();observed=ObservedSourcePairs({})
        with patch.object(partial,'partial_source_intervals',return_value={'long':(Interval(0,50000),)}):
            result,fallback,report=partial.prepare_partial(self.root,self.catalog,self.index,observed,{},
                reference_lengths=self.index.reference_lengths,preset='asm10',threads=32,
                complete_tasks=tasks,required_target_ids=self.targets)
        self.assertEqual(result,[]);self.assertEqual(fallback,[])
        self.assertEqual(report['parents_satisfied_by_complete_native_matrices'],0)
        self.assertEqual(report['parents_satisfied_by_scoped_approximate_matrices'],1)
        self.assertEqual(observed.cross_coverage,{})


class RawProfileIdentityTests(unittest.TestCase):
    def test_actual_flags_have_distinct_keys_and_cannot_hit_the_native_cache(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=SourceKey('ds','q');target=SourceKey('other','t')
            sequences={source:'A'*50,target:'C'*60};parts={p.segment_id:p for key,seq in sequences.items() for p in split_source(key,seq).segments}
            query=next(k for k,p in parts.items() if p.source==source);other=next(k for k,p in parts.items() if p.source==target)
            catalog=CandidateCatalog({'candidates':[]},sequences,parts);catalog.reference_routable_parts=set()
            binary=root/'mapper';binary.write_text('fixture');tool={'command':'minimap2','resolved':str(binary),'sha256':sha256_file(binary)}
            request={'kind':'candidate_unroutable_seed','query_ids':[query],'target_ids':[other]}
            commands=[]
            def mapper(argv,**kwargs):
                commands.append(argv);Path(argv[argv.index('-o')+1]).write_text('');return SimpleNamespace(returncode=0)
            with patch.object(prep,'weak_global_seed_scope',return_value=((query,),(other,))),patch.object(prep.subprocess,'run',side_effect=mapper):
                fast=prep._supplement(root,catalog,request,tool,'asm10',2,weak_seed_fast=True,reference_bases=5_000_000_000)
                self.assertIsNone(prep._supplement(root,catalog,request,tool,'asm10',2,cache_only=True))
                native=prep._supplement(root,catalog,request,tool,'asm10',2)
                self.assertNotEqual(fast['task_id'],native['task_id'])
                self.assertEqual(prep._supplement(root,catalog,request,tool,'asm10',2,weak_seed_fast=True,reference_bases=5_000_000_000,cache_only=True),fast)
            self.assertEqual(len(commands),2)
            self.assertEqual(commands[0][commands[0].index('-m')+1],'2000');self.assertIn('-P',commands[0]);self.assertNotIn('-m',commands[1])
            self.assertEqual(json.loads((root/fast['receipt']).read_text())['spec']['alignment_flags'],[*BASE_FLAGS,'-m','2000'])


if __name__=='__main__':unittest.main()
