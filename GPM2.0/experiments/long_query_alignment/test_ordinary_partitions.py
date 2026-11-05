"""Original partition scheduling: budgets, inherited thresholds, ordering, cleanup."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark_ordinary_partitions as parts
import ordinary_partition_fixture as fixture
import ordinary_batch_performance as perf


class PartitionTests(unittest.TestCase):
    def test_fixed_worker_budgets_never_oversubscribe(self):
        for threads in (2, 3, 7, 64):
            for requested in (1, 2):
                plan = parts.admission(threads, 4096, requested, 3)
                self.assertEqual(sum(plan['thread_shares']), threads)
                self.assertGreaterEqual(min(plan['thread_shares']), 1)
                self.assertLessEqual(plan['sum_worker_address_space_mib'] + plan['reserved_mib'], 4096)

    def test_invalid_or_insufficient_budgets_refused(self):
        for values in [(1, 4096, 2, 2), (64, 1024, 2, 2), (64, 4096, 2, 1), (65, 4096, 2, 2)]:
            with self.assertRaises(ValueError):
                parts.admission(*values)

    def test_partial_threshold_log_line_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'log'
            p.write_bytes(b'[M::mm_mapopt_update::0.1*1.0] mid_occ = 5')
            self.assertEqual(parts.thresholds(p), [])
            with p.open('ab') as f:
                f.write(b'00\n')
            self.assertEqual(parts.thresholds(p), [500])

    def test_threshold_overflow_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'log';p.write_bytes(b'[M::mm_mapopt_update::0.1] mid_occ = 9999999999999\n')
            with self.assertRaises(ValueError):parts.thresholds(p)

    def test_only_following_parts_get_explicit_inherited_threshold(self):
        first = parts.command('mm','idx','q','out',32,500000000)
        following = parts.command('mm','idx','q','out',32,500000000,500)
        self.assertNotIn('-f',first)
        self.assertEqual(following[following.index('-f')+1], '500')
        self.assertNotIn('-I',following)
        self.assertNotIn('--secondary=no',following)

    def test_paf_coordinates_cigar_and_part_membership(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'out.paf'
            good='q\t10\t0\t10\t+\tt\t20\t0\t10\t10\t10\t60\tcg:Z:10M\n'
            p.write_text(good)
            q,t=[{'name':'q','length':10}],[{'name':'t','length':20}]
            self.assertEqual(parts.validate_paf(p,q,t),1)
            for bad in [good.replace('10M','9M'),good.replace('\tt\t','\tother\t'),
                        good.replace('\t60\t','\t256\t'),good.replace('\t0\t10\t+','\t0\t11\t+')]:
                p.write_text(bad)
                with self.assertRaises(ValueError):parts.validate_paf(p,q,t)

    def test_empty_part_allowed_but_empty_aggregate_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'empty';p.touch()
            self.assertEqual(parts.validate_paf(p,[],[],allow_empty=True),0)
            with self.assertRaises(ValueError):parts.validate_paf(p,[],[])

    def test_merge_uses_original_part_order_not_finish_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for i in (1,0):
                (root/f'part-{i:04d}.paf').write_text(str(i)+'\n')
            with patch.object(parts,'validate_paf'),patch.object(parts,'check_native_log'):
                parts.merge_parts([{'part_index':0,'records':[]},{'part_index':1,'records':[]}],
                                  root,root/'complete',[],500000000)
            self.assertEqual((root/'complete').read_text(),'0\n1\n')

    def fake_mapper(self, root, behavior='normal'):
        p=root/'mapper'
        p.write_text('''#!/usr/bin/env python3
import pathlib,subprocess,sys,time
args=sys.argv[1:]
index=int(pathlib.Path(args[-2]).read_text())
output=pathlib.Path(args[args.index('-o')+1])
behavior=BEHAVIOR
if index==0:
    if behavior=='missing':
        sys.exit(0)
    if behavior=='fail':
        sys.exit(3)
    if behavior=='fail_later':
        pass
    if behavior=='timeout':
        subprocess.Popen([sys.executable,'-c',"import time,pathlib;time.sleep(1.0);pathlib.Path("+repr(str(output.parent/'orphan'))+").touch()"])
        time.sleep(2)
    sys.stderr.write('[M::mm_mapopt_update::0.1*1.0] mid_occ = 5');sys.stderr.flush()
    time.sleep(0.15)
    sys.stderr.write('00\\n');sys.stderr.flush()
    time.sleep(0.25)
else:
    if behavior=='fail_later':
        sys.exit(4)
    assert args[args.index('-f')+1]=='500'
    sys.stderr.write('[M::mm_mapopt_update::0.1*1.0] mid_occ = 500\\n');sys.stderr.flush()
    time.sleep(0.02)
output.write_text(str(index))
'''.replace('BEHAVIOR',repr(behavior)))
        p.chmod(0o700)
        return str(p)

    def run_fake(self,root,behavior='normal',timeout=5,count=2):
        mm=self.fake_mapper(root,behavior)
        catalog=[]
        for i in range(count):
            p=root/f'idx{i}';p.write_text(str(i))
            catalog.append({'part_index':i,'path':str(p)})
        return parts.map_parts(mm,catalog,'q',root,
             SimpleNamespace(threads=4,memory_mib=2048,timeout=timeout,batch_bases=500000000),2)

    def test_threshold_handoff_is_live_and_no_extra_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=self.run_fake(root)
            self.assertEqual(r['mid_occ'],500)
            starts=[e for e in r['events'] if e['event']=='start']
            self.assertEqual([e['part_index'] for e in starts],[0,1])
            self.assertGreaterEqual(starts[1]['after_seconds']-starts[0]['after_seconds'],0.15)
            self.assertLess(starts[1]['after_seconds'],[e['after_seconds'] for e in r['events'] if e['event']=='complete' and e['part_index']==0][0])
            self.assertEqual([e['part_index'] for e in r['events'] if e['event']=='complete'],[1,0])
            self.assertEqual([x['command'][-2] for x in r['parts']],[str(root/'idx0'),str(root/'idx1')])
            self.assertEqual(len(r['parts']),2)

    def test_queued_third_part_reuses_free_slot_without_oversubscribing(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.run_fake(Path(d),count=3)
            self.assertEqual(len(r['parts']),3)
            active={}
            for event in r['events']:
                if event['event']=='start':
                    active[event['part_index']]=event['threads']
                    self.assertLessEqual(sum(active.values()),4)
                    if event['part_index']>0:self.assertEqual(event['mid_occ'],500)
                elif event['event']=='complete':
                    del active[event['part_index']]
            self.assertEqual(active,{})
            starts={e['part_index']:e['after_seconds'] for e in r['events'] if e['event']=='start'}
            ends={e['part_index']:e['after_seconds'] for e in r['events'] if e['event']=='complete'}
            self.assertGreaterEqual(starts[2],ends[1])
            self.assertLess(starts[2],ends[0])

    def test_missing_threshold_refuses_to_start_other_parts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'without a complete mid_occ'):
                self.run_fake(root,'missing')
            schedule=json.loads((root/'schedule.json').read_text())
            self.assertEqual(schedule['launched_parts'],1)
            self.assertFalse((root/'part-0001.paf').exists())

    def test_failed_first_part_does_not_publish_or_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'failed; no retry'):
                self.run_fake(root,'fail')
            self.assertEqual(json.loads((root/'schedule.json').read_text())['launched_parts'],1)
            self.assertFalse((root/'complete.paf').exists())

    def test_failed_later_part_aborts_live_first_part(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'failed; no retry'):
                self.run_fake(root,'fail_later')
            self.assertFalse((root/'part-0000.paf').exists())
            self.assertEqual(json.loads((root/'schedule.json').read_text())['launched_parts'],2)

    def test_timeout_kills_descendants_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(subprocess.TimeoutExpired):self.run_fake(root,'timeout',timeout=0.2)
            time.sleep(1.1)
            self.assertFalse((root/'orphan').exists())
            self.assertEqual(json.loads((root/'schedule.json').read_text())['launched_parts'],1)

    def test_plan_only_needs_no_input_files_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(parts,'execute') as execute,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(parts.main(['--target','/missing','--query','/absent','--out',d+'/out']),0)
            execute.assert_not_called()
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_control_partition_override_is_explicit_not_default(self):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            parts.main(['--target','/missing','--query','/absent','--out','/nothing'])
        self.assertIsNone(json.loads(stream.getvalue())['plan']['control_index_bases'])

    def test_fixture_names_hashes_and_n_only_record(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'fixture'
            manifest=fixture.generate(root,seed_bases=5000,padding_records=0,query_records=4,query_bases=2000)
            self.assertEqual(perf.sha256(root/'target.fa'),manifest['target_sha256'])
            self.assertEqual(perf.sha256(root/'queries.fa'),manifest['query_sha256'])
            self.assertFalse(manifest['original_default_index_policy_expected'])
            self.assertIn(b'>q003\n'+b'N'*2000,(root/'queries.fa').read_bytes())
            self.assertTrue(manifest['synthetic_control_only'])

    def test_index_reader_is_existing_hash_guarded_source(self):
        reader,path=parts.index_reader()
        self.assertEqual(path.name,'minimap_index_context.py')
        self.assertTrue(callable(reader.copy_parts))


if __name__=='__main__':unittest.main()
