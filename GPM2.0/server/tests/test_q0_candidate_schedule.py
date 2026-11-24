"""CPU/memory grants and reproducibility of non-regional whole-target Q0 maps."""
from pathlib import Path
from threading import Barrier, Event, Lock
import json
import getpass
import socket
from types import SimpleNamespace
import random
import shutil
import tempfile
import unittest
from unittest.mock import patch

from server.tools.lgz_core import q0_candidate_schedule as schedule, q0_preparation as prep
from server.tools.lgz_core.common import executable_identity
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.q0_sources import SourceKey, split_source


class GrantTests(unittest.TestCase):
    def test_live_donau_requires_kernel_job_and_matching_running_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp); (proc/'self').mkdir(); cg = proc/'self/cgroup'
            row = dict(jobId='123', state='RUNNING', taskExecNodes=socket.gethostname(), user=getpass.getuser(),
                       taskExecNodesCount=1, resGroups=[dict(resAlloc=dict(cpu=16, mem=81920), resLimit=dict(mem=81920))])
            def reply(*args, **kwargs):
                return SimpleNamespace(stdout=json.dumps({'data':{'successData':[row]}}).encode())
            with patch.object(schedule.shutil, 'which', return_value='/site/djob'), patch.object(schedule.subprocess, 'run', side_effect=reply) as run:
                cg.write_text('0::/ordinary-job\n'); self.assertIsNone(schedule._live_donau_allocation(proc)); run.assert_not_called()
                cg.write_text('5:memory:/batch/container_123_rg0_00000000_e01\n')
                self.assertEqual(schedule._live_donau_allocation(proc), (16, 80*schedule.GIB))
                self.assertEqual(run.call_args.args[0], ['/site/djob', '-L', '-J', '123'])
                for field, wrong in [('jobId','124'), ('taskExecNodes','wrong'), ('state','PENDING'), ('user','other')]:
                    with patch.dict(row, {field:wrong}):
                        self.assertIsNone(schedule._live_donau_allocation(proc))
                row['resGroups'][0]['resAlloc']['mem'] = 128
                self.assertEqual(schedule._live_donau_allocation(proc)[1], 128*1024**2)

    def test_free_worker_is_refilled_before_the_slow_peer_finishes(self):
        work = [schedule.MapWork(k, n, 100) for k, n in [('small', 1), ('large', 4), ('medium', 3)]]
        memory = sum(sorted(j.reservation for j in work)[1:])  # two jobs, not three
        first_pair = Barrier(2, timeout=5)
        small = Event(); lock = Lock(); used = {}; grants = {}
        def run(k, cpu):
            with lock:
                used[k] = cpu; grants[k] = cpu
                self.assertLessEqual(sum(used.values()), 7)
                self.assertLessEqual(sum(j.reservation for j in work if j.key in used), memory)
            if k in ('large', 'medium'):
                first_pair.wait()
            if k == 'large':
                self.assertTrue(small.wait(5))
            elif k == 'small':
                small.set()
            with lock:
                used.pop(k)
            return k
        self.assertEqual(schedule.run_pending(work, 7, memory, run), {k:k for k in ('large','small','medium')})
        self.assertEqual(grants, {'large':4, 'medium':3, 'small':3})

    def test_unknown_or_insufficient_memory_serializes_without_omitting(self):
        jobs = [schedule.MapWork(k, 10, 20) for k in 'abc']
        for budget, memory in [(11, None), (7, 1), (1, 100*schedule.GIB)]:
            calls = []
            schedule.run_pending(jobs, budget, memory, lambda k, t: calls.append((k,t)))
            self.assertEqual(calls, [(k, budget) for k in 'abc'])
        with self.assertRaises(ValueError):
            schedule.run_pending(jobs*2, 16, None, None)

    def test_failure_drains_started_peer_without_launching_next_batch(self):
        jobs = [schedule.MapWork(k, 1, 1) for k in 'abc']
        started = Barrier(2, timeout=5); called = []
        def run(k, cpu):
            called.append(k)
            started.wait()
            raise RuntimeError('failed mapping')
        with self.assertRaisesRegex(RuntimeError, 'failed mapping'):
            schedule.run_pending(jobs, 8, 2*jobs[0].reservation, run)
        self.assertCountEqual(called, ['a','b'])


@unittest.skipUnless(shutil.which('minimap2'), 'requires actual minimap2')
class CandidateMappingTests(unittest.TestCase):
    def test_real_maps_match_serial_keep_aliases_and_resume_only_missing_or_damaged(self):
        rng = random.Random(22); seq = ''.join(rng.choices('ACGT', k=16000))
        sources = {SourceKey('ds', str(i)): seq[i:i+10000] for i in (0, 2000, 4000)}
        parts = {p.segment_id:p for key, bases in sources.items() for p in split_source(key, bases).segments}
        catalog = CandidateCatalog({'candidates':[]}, sources, parts); ids = sorted(parts)
        requests = [dict(kind='candidate_chr', chromosome=c, query_ids=[ids[i]], target_ids=ids)
                    for c,i in [('chrA',0), ('chrB',1), ('chrC',0), ('chrD',2)]]
        tool = executable_identity(shutil.which('minimap2'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(schedule, 'available_budget', return_value=(5, 100*schedule.GIB)):
            serial, candidate = Path(tmp)/'baseline', Path(tmp)/'candidate'
            serial.mkdir(); candidate.mkdir()
            expected = [prep._supplement(serial, catalog, r, tool, 'asm10', 5) for r in requests]
            def run():
                return prep._native_candidates(candidate, catalog, requests, tool, 'asm10', 5, skip_self=False)
            real = prep._supplement; failing = requests[1]; calls = []
            def fail_one(*args, **kwargs):
                if args[2] == failing and not kwargs.get('cache_only'):
                    raise RuntimeError('controlled worker failure')
                return real(*args, **kwargs)
            with patch.object(prep, '_supplement', side_effect=fail_one), self.assertRaisesRegex(RuntimeError,'controlled'):
                run()
            def record(*args, **kwargs):
                if not kwargs.get('cache_only'):
                    calls.append(args[2]['chromosome'])
                return real(*args, **kwargs)
            with patch.object(prep, '_supplement', side_effect=record):
                actual = run()
                self.assertEqual(actual, expected)  # original order, one result row per request
                self.assertEqual(calls, ['chrB'])
                calls.clear(); self.assertEqual(run(), expected); self.assertEqual(calls, [])
                for t in actual:
                    output = candidate/t['paf']; self.assertGreater(output.stat().st_size, 0)
                    self.assertEqual(output.read_bytes(), (serial/t['paf']).read_bytes())
                self.assertEqual(actual[0]['task_id'], actual[2]['task_id'])
                self.assertEqual(len(list(candidate.rglob('success.json'))), 3)
                (candidate/actual[0]['paf']).write_bytes(b'corrupted\n')
                self.assertEqual(run(), expected); self.assertEqual(calls, ['chrA'])
                self.assertEqual((serial/actual[0]['paf']).read_bytes(), (candidate/actual[0]['paf']).read_bytes())
