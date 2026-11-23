import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from server.tools.lgz_core.q0_catalog import build_catalog
from server.tools.lgz_core.q0_sources import SourceKey,Q0EvidenceError,Interval
from server.tools.lgz_core.q0_reference_index import ReferenceIndex
from server.tools.lgz_core.q0_regional_candidates import CandidatePlan,prepare_candidates
from server.tools.lgz_core import q0_regional_candidates as candidates
from server.tools.lgz_core.q0_regional_execution import ParentRequest
from server.tools.lgz_core.q0_query_windows import QueryWindow
from server.tools.lgz_core.q0_regional_mapping import BASE_FLAGS
from server.tools.lgz_core.common import stable_id
from server.tools.lgz_core import q0_preparation as prep


class RegionalCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.sources={SourceKey('ds',key):'A'*10000 for key in ('a','b','c')}
        self.refs={'chr1':100000,'chr2':100000}
        p=self.root/'runs/ds_vs_ref/result.paf';p.parent.mkdir(parents=True)
        p.write_text(''.join(f'{q}\t10000\t{qs}\t{qs+1000}\t+\t{chrom}\t100000\t{ts}\t{ts+1000}\t1000\t1000\t60\tcg:Z:1000M\n'
                            for q,qs,chrom,ts in [('a',0,'chr1',100),('a',0,'chr2',100),('b',1000,'chr1',100),('b',1000,'chr2',100),('c',7000,'chr1',50000)]))
        self.catalog=build_catalog(self.root,self.sources,self.refs,[],regional_factory=lambda parts,refs:ReferenceIndex.create(self.root/'index.sqlite',self.root,parts,refs))
        self.index=ReferenceIndex.open(self.root/'index.sqlite',self.root,self.catalog.parts,self.refs);self.addCleanup(self.index.close)
        self.ids={part.source.contig:key for key,part in self.catalog.parts.items()}
        self.requests=[{'kind':'candidate_chr','chromosome':chrom,'query_ids':[self.ids['a']],'target_ids':sorted(self.ids.values())} for chrom in self.refs]

    def plan(self,observed=(),tasks=(),requests=None):
        return CandidatePlan(self.root,self.catalog,self.index,self.requests if requests is None else requests,observed,tasks,{},'asm10')

    def native_task(self,query,target):
        spec={'schema':'lgz_q0_mapping_v1','query_ids':sorted(query),'target_ids':sorted(target),
              'members':[[key,self.catalog.parts[key].sequence_sha256] for key in sorted(set(query+target))],
              'tool':{},'preset':'asm10','alignment_flags':BASE_FLAGS}
        key=stable_id('q0-map',spec);rel=f'grt/evidence/q0_prepare/tasks/{key}';directory=self.root/rel;directory.mkdir(parents=True)
        for name in ('query.fa','target.fa','result.paf','command.json'):(directory/name).write_text('')
        receipt={'status':'success','spec':spec,'outputs':[prep.identity(self.root,rel+'/'+name) for name in ('query.fa','target.fa','result.paf','command.json')]}
        (directory/'success.json').write_text(json.dumps(receipt))
        return {'task_id':key,'kind':'unplaced_discovery','query_ids':sorted(query),'target_ids':sorted(target),'paf':rel+'/result.paf','receipt':rel+'/success.json'}

    def test_chromosome_duplicates_unite_actual_query_context_once(self):
        plan=self.plan();_,eligible=plan.eligible(self.ids['a']);windows,native,reason=plan.plan_parent(self.ids['a'],eligible)
        self.assertEqual(len(windows),1);self.assertEqual(native,0);self.assertIsNone(reason)
        query,targets=windows[0];self.assertEqual(query.cores,((0,1000),))
        self.assertEqual({t.segment_id for t in targets},{self.ids['b']})

    def test_known_sources_are_excluded_before_paf_decode_and_no_local_targets_is_not_failure(self):
        known={(SourceKey('ds','a'),SourceKey('ds','b'))};plan=self.plan(known)
        _,eligible=plan.eligible(self.ids['a']);original=self.index._hit
        def hit(row):
            self.assertNotEqual(self.index.sources[row[1]],SourceKey('ds','b'))
            return original(row)
        with mock.patch.object(self.index,'_hit',side_effect=hit):
            windows,native,reason=plan.plan_parent(self.ids['a'],eligible)
        self.assertEqual(windows,[]);self.assertEqual(native,0)

    def test_complete_native_matrix_is_reused_without_inventing_a_hit(self):
        task=self.native_task([self.ids['b']],[self.ids['a']])
        plan=self.plan(tasks=[task]);_,eligible=plan.eligible(self.ids['a'])
        self.assertEqual(plan.keys(eligible),[self.ids['c']])
        path=self.root/task['receipt'];receipt=json.loads(path.read_text());receipt['outputs']=[];path.write_text(json.dumps(receipt))
        with self.assertRaises(Q0EvidenceError):self.plan(tasks=[task])

    def test_unroutable_query_or_target_retains_full_native_fallback(self):
        self.catalog.reference_routable_parts=frozenset([self.ids['a'],self.ids['b']])
        plan=self.plan();_,eligible=plan.eligible(self.ids['a']);windows,native,reason=plan.plan_parent(self.ids['a'],eligible)
        self.assertEqual(plan.keys(native),[self.ids['c']]);self.assertEqual(len(windows),1)
        self.catalog.reference_routable_parts=frozenset([self.ids['b'],self.ids['c']])
        plan=self.plan();_,eligible=plan.eligible(self.ids['a']);windows,native,reason=plan.plan_parent(self.ids['a'],eligible)
        self.assertEqual(windows,[]);self.assertEqual(native,eligible)

    def test_weak_only_alternative_keeps_evidence_without_whole_source_expansion(self):
        before=list(self.catalog.payload['candidates'])
        self.catalog.reference_routable_footprints={(key,chr):rows for (key,chr),rows in self.catalog.reference_routable_footprints.items() if not(key==self.ids['a'] and chr=='chr2')}
        plan=self.plan(requests=[self.requests[1]]);_,eligible=plan.eligible(self.ids['a'])
        windows,native,reason=plan.plan_parent(self.ids['a'],eligible)
        self.assertEqual(windows,[]);self.assertEqual(native,0)
        self.assertEqual(reason,'weak_reference_only_alternatives_not_expanded')
        self.assertEqual(self.catalog.payload['candidates'],before)

    def test_whole_source_hit_does_not_suppress_new_split_part_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources={SourceKey("ds","a"):"A"*1000+"N"*100+"C"*1900,SourceKey("ds","b"):"G"*2000}
            path=root/"runs/ds_vs_ref/result.paf";path.parent.mkdir(parents=True)
            path.write_text("a\t3000\t0\t3000\t+\tchr\t100000\t0\t2900\t2900\t3000\t60\tcg:Z:1000M100I1900M\n"
                            "b\t2000\t0\t2000\t+\tchr\t100000\t0\t2000\t2000\t2000\t60\tcg:Z:2000M\n")
            refs={"chr":100000};catalog=build_catalog(root,sources,refs,[],regional_factory=lambda parts,refs:ReferenceIndex.create(root/"index.sqlite",root,parts,refs))
            index=ReferenceIndex.open(root/"index.sqlite",root,catalog.parts,refs)
            try:
                second=next(k for k,p in catalog.parts.items() if p.source.contig=="a" and p.interval.start==1100)
                target=next(k for k,p in catalog.parts.items() if p.source.contig=="b")
                requests=[{"kind":"candidate_chr","chromosome":"chr","query_ids":[second],"target_ids":sorted(catalog.parts)}]
                plan=CandidatePlan(root,catalog,index,requests,{(SourceKey("ds","a"),SourceKey("ds","b"))},[],{},"asm10")
                _,eligible=plan.eligible(second);self.assertIn(target,plan.keys(eligible))
                self.assertEqual(plan.windows(second)[0].cores,((0,1900),))
                selected=index.target_selection(plan.mask([target]))
                rows=index.targets({"chr":[Interval(0,2900)]},selection=selected)
                self.assertEqual(set(rows),{target})
            finally:index.close()

    def test_unroutable_seed_queries_small_side_once_then_removes_normal_fallback(self):
        self.catalog.reference_routable_parts=frozenset([self.ids["a"],self.ids["b"]])
        plan=self.plan();request=plan.next_unroutable_seed()
        self.assertEqual(request["query_ids"],[self.ids["c"]])
        self.assertEqual(set(request["target_ids"]),set(self.ids.values()))
        task=self.native_task(request["query_ids"],request["target_ids"])
        plan.add_complete_tasks([task]);self.assertIsNone(plan.next_unroutable_seed())
        _,eligible=plan.eligible(self.ids["a"])
        self.assertNotIn(self.ids["c"],plan.keys(eligible))

    def test_seed_batches_recompute_missing_matrix_after_each_completion(self):
        self.catalog.reference_routable_parts=frozenset([self.ids["a"]])
        # b -> a was completed. c -> (a,b,c) is the largest new matrix and
        # its completion removes b-c too; there must not be another b task.
        first=self.native_task([self.ids["b"]],[self.ids["a"]])
        plan=self.plan(tasks=[first]);request=plan.next_unroutable_seed()
        self.assertEqual(request["query_ids"],[self.ids["c"]])
        task=self.native_task(request["query_ids"],request["target_ids"])
        plan.add_complete_tasks([task]);self.assertIsNone(plan.next_unroutable_seed())

    def test_invalid_scope_does_not_poison_retry_deduplication(self):
        task=self.native_task([self.ids["b"]],[self.ids["a"]]);path=self.root/task["receipt"]
        original=path.read_text();row=json.loads(original);row["outputs"]=[];path.write_text(json.dumps(row))
        plan=self.plan()
        with self.assertRaises(Q0EvidenceError):plan.add_complete_tasks([task])
        path.write_text(original);plan.add_complete_tasks([task]);self.assertEqual(len(plan.scopes),1)

    def test_partial_phase_reuses_complete_negative_matrices_without_fake_coverage(self):
        from server.tools.lgz_core import q0_regional_discovery as partial
        from server.tools.lgz_core.q0_catalog import ObservedSourcePairs
        observed=ObservedSourcePairs({key:len(sequence) for key,sequence in self.catalog.sequences.items()})
        task=self.native_task([self.ids["a"]],[self.ids["b"],self.ids["c"]])
        with mock.patch.object(partial,"partial_source_intervals",return_value={self.ids["a"]:(Interval(0,10000),)}), \
             mock.patch.object(self.index,"regions",side_effect=AssertionError("complete matrix must not be remapped")):
            tasks,fallback,report=partial.prepare_partial(self.root,self.catalog,self.index,observed,{},reference_lengths=self.refs,preset="asm10",threads=4,
                complete_tasks=[task],required_target_ids=list(self.ids.values()))
        self.assertEqual(tasks,[]);self.assertEqual(fallback,[])
        self.assertEqual(report["parents_satisfied_by_complete_native_matrices"],1)
        self.assertEqual(observed.cross_coverage,{})

    def test_foreign_selection_and_unknown_bits_are_rejected(self):
        with self.assertRaises(Q0EvidenceError):self.index.target_selection(1<<len(self.index.parts))
        other=ReferenceIndex.open(self.root/'index.sqlite',self.root,self.catalog.parts,self.refs)
        try:
            with self.assertRaises(Q0EvidenceError):self.index.targets({'chr1':[Interval(0,1000)]},selection=other.target_selection(1))
        finally:other.close()

    def test_coordinator_maps_only_local_remaining_work(self):
        def mapper(root,catalog,query,targets,tool,**kwargs):return {'query':query.segment_id,'targets':sorted({t.segment_id for t in targets})}
        with mock.patch('server.tools.lgz_core.q0_regional_candidates.prepare_regional_mapping',side_effect=mapper) as run:
            tasks,native,report=prepare_candidates(self.root,self.catalog,self.index,self.requests,set(),[],{},reference_lengths=self.refs,preset='asm10',threads=4)
        self.assertEqual(run.call_count,1);self.assertEqual(native,[]);self.assertEqual(tasks[0]['targets'],[self.ids['b']])
        self.assertEqual(report['regional_windows'],1)


    def test_completion_parent_order_restores_tasks_and_interleaved_native_groups(self):
        keys=sorted(self.ids.values()); requests=[]
        for ordinal,key in enumerate(keys):
            query=QueryWindow(key,10000,0,1000,((0,1000),))
            native=1 if ordinal in (0,2) else 2
            requests.append(ParentRequest('candidate',key,ready=([(query,[])],native,
                'weak_reference_only_alternatives_not_expanded')))
        planner=SimpleNamespace(root=self.root,catalog=self.catalog,index=self.index,tool={},preset='asm10',
            query_chromosomes=dict.fromkeys(keys),scope_task_ids=[],approximate_scope_task_ids=[],
            next_unroutable_seed=lambda:None,eligible=lambda key:(7,7),
            planning_request=lambda key,eligible:requests[keys.index(key)],
            keys=lambda mask:[keys[0]] if mask==1 else [keys[1]])
        def completed(runner,items):
            values=list(items)
            for ordinal in (1,2,0):yield ordinal,values[ordinal],values[ordinal].ready
        with mock.patch.object(candidates.RegionalExecutor,'completed',completed), \
             mock.patch.object(candidates,'prepare_regional_mapping',side_effect=lambda *args,**kwargs:{'query':args[2].segment_id}):
            tasks,native,report=prepare_candidates(self.root,self.catalog,self.index,[],set(),[],{},
                reference_lengths=self.refs,preset='asm10',threads=6,planner=planner)
        self.assertEqual([row['query'] for row in tasks],keys)
        self.assertEqual([row['query_ids'] for row in native],[[keys[0],keys[2]],[keys[1]]])
        self.assertEqual([row['target_ids'] for row in native],[[keys[0]],[keys[1]]])
        self.assertEqual([[r['query'] for r in row['regional_fallback']] for row in native],
            [[keys[0],keys[2]],[keys[1]]])
        self.assertEqual(report['weak_only_parent_ids'],keys)
        self.assertEqual(report['requested_part_pairs'],9)
        self.assertEqual(report['reused_part_pairs'],0)
        self.assertEqual(report['regional_windows'],3)
        self.assertEqual(report['fallback_parents'],3)


if __name__=='__main__':unittest.main()
