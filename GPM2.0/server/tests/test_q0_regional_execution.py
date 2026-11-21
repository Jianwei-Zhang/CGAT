import os
import copy
import hashlib
import json
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest import mock

from server.tools.lgz_core import q0_regional_execution as execution
from server.tools.lgz_core.q0_alignments import read_paf
from server.tools.lgz_core.q0_query_windows import QueryWindow
from server.tools.lgz_core.q0_reference_index import ReferenceIndex, _identity
from server.tools.lgz_core.q0_sources import SourceKey, split_source, Q0EvidenceError


def reader_probe():
    return {"pid": os.getpid(), "limit": execution.resource.getrlimit(execution.resource.RLIMIT_AS),
            "parts": len(execution._WORKER_INDEX.parts),
            "has_sequences": hasattr(execution._WORKER_INDEX, "sequences")}


class BudgetTests(unittest.TestCase):
    def test_total_budget_and_memory_bound_for_large_allocation(self):
        budget = execution.choose_budget(32, 320*execution.GIB, 34*execution.GIB)
        self.assertEqual((budget.planner_workers, budget.mapper_workers, budget.mapper_threads), (3, 14, 2))
        self.assertLessEqual(1+budget.planner_workers+budget.mapper_workers*budget.mapper_threads, 32)
        self.assertLessEqual(budget.reserved_bytes, 320*execution.GIB)
        for threads in (1, 3, 8, 16, 32, 64, 128):
            for memory in (None, 8, 48, 80, 320):
                b = execution.choose_budget(threads, memory*execution.GIB if memory else None, 8*execution.GIB)
                self.assertLessEqual(b.mapper_threads*b.mapper_workers+b.planner_workers+int(threads > 1), threads)
                if b.planner_workers:
                    self.assertLessEqual(b.reserved_bytes, b.memory_limit_bytes)
                if memory is None:
                    self.assertEqual(b.planner_workers, 0)
                    self.assertLessEqual(b.mapper_workers, 4)

    def test_invalid_budgets_rejected(self):
        for args in ((True,), (0,), (8, True), (8, -1), (8, None, -1)):
            with self.subTest(args=args), self.assertRaises(Q0EvidenceError):
                execution.choose_budget(*args)

    def test_cgroup_ancestry_not_physical_memory_or_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); proc = root/'proc'; cg = root/'cgroup'
            (proc/'self').mkdir(parents=True); (cg/'job/step').mkdir(parents=True)
            (proc/'self/cgroup').write_text('0::/job/step\n')
            (cg/'memory.max').write_text('max')
            (cg/'job/memory.max').write_text(str(64*execution.GIB))
            (cg/'job/step/memory.max').write_text(str(80*execution.GIB))
            self.assertEqual(execution.cgroup_memory_limit(proc, cg), 64*execution.GIB)
            (cg/'job/memory.max').write_text('max'); (cg/'job/step/memory.max').write_text('max')
            self.assertIsNone(execution.cgroup_memory_limit(proc, cg))
            (proc/'self/cgroup').write_text('0::/../../outside\n')
            self.assertIsNone(execution.cgroup_memory_limit(proc, cg))


class AllocationProofTests(unittest.TestCase):
    def test_current_job_proof_and_every_identity_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'self').mkdir();proof=root/'allocation.json'
            cgroups=root/'self/cgroup';cgroups.write_text('10:memory:/batch/container_123_rg0_00000000_e01\n')
            base={'jobId':'123','state':'RUNNING','taskExecNodesCount':1,'taskExecNodes':'host','user':'user',
                  'resGroups':[{'resAlloc':{'cpu':32,'mem':327680},'resLimit':{'mem':327680}}]}
            env={execution.SCHEDULER_PROOF_ENV:str(proof)}
            def write(row):
                proof.write_text(json.dumps({'data':{'successData':[row]}}))
                env[execution.SCHEDULER_SHA_ENV]=hashlib.sha256(proof.read_bytes()).hexdigest()
            def check():return execution.allocation_memory_limit(32,environ=env,proc=root,host='host',user='user')
            write(base)
            self.assertEqual(check(),320*execution.GIB)
            reduced=copy.deepcopy(base);reduced['resGroups'][0]['resLimit']['mem']=163840;write(reduced)
            self.assertEqual(check(),160*execution.GIB)
            for name,value in (('jobId','124'),('state','FAILED'),('taskExecNodesCount',2),
                               ('taskExecNodes','other'),('user','other')):
                row=copy.deepcopy(base);row[name]=value;write(row)
                with self.subTest(name=name),self.assertRaises(Q0EvidenceError):check()
            for name,value in (('cpu',16),('mem',True),('mem',0)):
                row=copy.deepcopy(base);row['resGroups'][0]['resAlloc'][name]=value;write(row)
                with self.subTest(name=name,value=value),self.assertRaises(Q0EvidenceError):check()
            write(base);env[execution.SCHEDULER_SHA_ENV]='0'*64
            with self.assertRaises(Q0EvidenceError):check()
            write(base);cgroups.write_text('10:memory:/batch/container_1234_rg0_00000000_e01\n')
            with self.assertRaises(Q0EvidenceError):check()
            self.assertIsNone(execution.allocation_memory_limit(32,environ={}))
            with self.assertRaises(Q0EvidenceError):execution.allocation_memory_limit(32,environ={execution.SCHEDULER_SHA_ENV:'0'*64})


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        sources = {SourceKey('ds', name): 'A'*1000 for name in ('a', 'b', 'c')}
        self.parts = {p.segment_id:p for key, seq in sources.items() for p in split_source(key, seq).segments}
        self.ids = {p.source.contig:key for key, p in self.parts.items()}
        self.refs = {'chr':10000}; self.paf = self.root/'ref.paf'
        self.paf.write_text(''.join(f'{name}\t1000\t100\t900\t+\tchr\t10000\t1000\t1800\t800\t800\t60\tcg:Z:800M\n' for name in ('a','b','c')))
        index = ReferenceIndex.create(self.root/'reference.sqlite', self.root, self.parts, self.refs)
        list(read_paf(self.paf, query_lengths={name:1000 for name in ('a','b','c')}, target_lengths=self.refs,
                      artifact='ref.paf', record_observer=lambda hit,off,size:index.observe_record('ds',hit,off,size)))
        index.seal(); index.close()
        (self.root/'mirrors').mkdir()
        self.index = ReferenceIndex.open(self.root/'reference.sqlite', self.root, self.parts, self.refs, local_paf_directory=self.root/'mirrors')
        self.addCleanup(lambda:self.index.close())
        self.budget = execution.choose_budget(16, 160*execution.GIB, 2*execution.GIB)

    def requests(self):
        ids = self.ids; all_mask = (1 << len(self.parts))-1
        window = QueryWindow(ids['a'], 1000, 100, 900, ((100,900),))
        return [execution.ParentRequest('partial', ids['a'], (window,)),
                execution.ParentRequest('candidate', ids['a'], (window,), ('chr',), all_mask, 0, all_mask),
                execution.ParentRequest('candidate', ids['a'], (window, QueryWindow(ids['a'], 1000, 0, 50, ((0,50),))), ('chr',), all_mask, 2, all_mask),
                execution.ParentRequest('candidate', ids['b'], ready=([], 2, 'query_without_qualified_reference'))]

    def test_snapshot_is_small_metadata_no_source_dna_and_no_repeated_paf_hash(self):
        snapshot = self.index.reader_snapshot()
        self.assertLess(len(pickle.dumps(snapshot)), 6000)
        self.assertFalse(hasattr(snapshot, 'sequences'))
        with mock.patch('server.tools.lgz_core.q0_reference_index._identity', wraps=_identity) as identity:
            reader = ReferenceIndex.open_reader(snapshot)
            try:
                actual = [execution.plan_request(r, reader) for r in self.requests()]
            finally:
                reader.close()
            self.assertEqual([call.args[0] for call in identity.call_args_list], [snapshot.path])
        expected = [execution.plan_request(r, self.index) for r in self.requests()]
        self.assertEqual(actual, expected)
        with self.assertRaises(Q0EvidenceError):
            ReferenceIndex.open_reader({})

    @unittest.skipIf(execution.resource is None, 'POSIX resource guard required')
    def test_spawned_plans_equal_owner_order_and_fallback_with_hard_guard(self):
        requests = self.requests()*3
        expected = [execution.plan_request(r, self.index) for r in requests]
        with execution.RegionalExecutor(self.index, 16, budget=self.budget) as pool:
            state = pool.pool.submit(reader_probe).result(timeout=30)
            actual = list(pool.ordered(requests))
        self.assertNotEqual(state['pid'], os.getpid())
        self.assertEqual(state['limit'], (execution.PLANNER_ADDRESS_SPACE,)*2)
        self.assertFalse(state['has_sequences'])
        self.assertEqual([r for r, _ in actual], requests)
        self.assertEqual([value for _, value in actual], expected)
        self.assertEqual(pool.report['parallel_parents'], 9)
        self.assertEqual(pool.report['serial_parents'], 3)
        self.assertIsNone(pool.report['pool_failure'])

    def test_paf_mirror_and_database_drift_fail_closed(self):
        for which in ('original', 'mirror', 'database'):
            with self.subTest(which=which):
                snapshot = self.index.reader_snapshot()
                path = {'original':self.paf, 'mirror':next(iter(self.index.mirrors.values())), 'database':self.index.path}[which]
                stat = path.stat()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns+1_000_000))
                with self.assertRaises(Q0EvidenceError):
                    ReferenceIndex.open_reader(snapshot)
                # Restore a valid owner by reopening with normal full checks.
                self.index.close()
                self.index = ReferenceIndex.open(self.root/'reference.sqlite', self.root, self.parts, self.refs, local_paf_directory=self.root/'mirrors')

    def test_owner_database_drift_cannot_become_a_new_snapshot(self):
        self.index.targets({'chr':()})
        st = self.index.path.stat()
        os.utime(self.index.path, ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
        with self.assertRaisesRegex(Q0EvidenceError, 'database changed'):
            self.index.reader_snapshot()
        with self.assertRaisesRegex(Q0EvidenceError, 'database changed'):
            self.index.targets({'chr':()})

    def test_pool_failure_and_oversized_results_replan_exactly_no_parent_lost(self):
        requests = self.requests()*3
        expected = [execution.plan_request(r, self.index) for r in requests]
        for failure in (execution.BrokenProcessPool('resource test'), MemoryError('resource test'), None):
            with self.subTest(failure=type(failure).__name__):
                pool = mock.Mock()
                if failure is None:
                    pool.submit.return_value.result.return_value = None  # result cap / worker MemoryError
                else:
                    pool.submit.return_value.result.side_effect = failure
                with mock.patch.object(execution, 'ProcessPoolExecutor', return_value=pool):
                    with execution.RegionalExecutor(self.index, 16, budget=self.budget) as runner:
                        actual = list(runner.ordered(requests))
                self.assertEqual([value for _, value in actual], expected)
                self.assertEqual([r for r, _ in actual], requests)
                self.assertEqual(runner.report['serial_parents'], len(requests))
                self.assertGreater(runner.report['exact_owner_replans'], 0)

    def test_integrity_failure_is_not_infrastructure_fallback(self):
        pool = mock.Mock(); pool.submit.return_value.result.side_effect = Q0EvidenceError('bad record')
        with mock.patch.object(execution, 'ProcessPoolExecutor', return_value=pool):
            with execution.RegionalExecutor(self.index, 16, budget=self.budget) as runner:
                with self.assertRaisesRegex(Q0EvidenceError, 'bad record'):
                    list(runner.ordered(self.requests()))
        self.assertEqual(runner.report['exact_owner_replans'], 0)

    def test_prefetch_is_bounded_while_preserving_order(self):
        requests = self.requests()*5; active = peak = 0
        class Future:
            def __init__(self, request): self.request = request
            def result(future):
                nonlocal active
                active -= 1
                return pickle.dumps(execution.plan_request(future.request, self.index))
        def submit(fn, request):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            return Future(request)
        pool = mock.Mock(); pool.submit.side_effect = submit
        with mock.patch.object(execution, 'ProcessPoolExecutor', return_value=pool):
            with execution.RegionalExecutor(self.index, 16, budget=self.budget) as runner:
                actual = list(runner.ordered(requests))
        self.assertEqual(active, 0)
        self.assertLessEqual(peak, 2*self.budget.planner_workers)
        self.assertEqual([r for r, _ in actual], requests)


if __name__ == '__main__':
    unittest.main()
