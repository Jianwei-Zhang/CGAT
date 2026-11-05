"""Real child receipts, complete matrices, bounded slots and legacy native reuse."""
import argparse
from contextlib import redirect_stderr
import copy
import io
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import minimap_index_context as mic
import native_first as nf
import ordinary_partition_alignment as opa
import proactive_reference_alignment as pa
import proactive_reference_plan as pp
import proactive_resume as pr
import recovery_publication as rp
import windowed_alignment as wa


class PartitionExecutionTests(unittest.TestCase):
    def args(self, **kw):
        values=dict(threads=7,timeout=10,minimap_batch='100K',minimap_filter=None,
                    ordinary_group_memory_bytes=8*1024**3)
        values.update(kw);return argparse.Namespace(**values)

    def fixture(self, root, count=3, behavior='normal'):
        parts=[]
        for i in range(count):
            p=root/f'part{i}.mmi';p.write_text(str(i))
            parts.append(dict(part_index=i,path=str(p),sha256=wa.sha256(p),start=0,end=1,
                              records=[{'name':f't{i}','length':1000}]))
        query=root/'query.fa';query.write_bytes(b'>q\n'+b'A'*200000+b'\n')
        mm=root/'mapper'
        mm.write_text('''#!/usr/bin/env python3
import pathlib,subprocess,sys,time
args=sys.argv[1:];i=int(pathlib.Path(args[-2]).read_text());mode=BEHAVIOR
output=pathlib.Path(args[args.index('-o')+1]);output.write_bytes(b'')
print('[M::main::0.01*1.0] loaded/built the index for 1 target sequence(s)',file=sys.stderr,flush=True)
if i==0:
    sys.stderr.write('[M::mm_mapopt_update::0.01*1.0] mid_occ = 5');sys.stderr.flush()
    time.sleep(0.1)
    sys.stderr.write('00\\n');sys.stderr.flush()
else:
    assert args[args.index('-f')+1]=='500'
    print('[M::mm_mapopt_update::0.01*1.0] mid_occ = 500',file=sys.stderr,flush=True)
if mode=='timeout' and i==0:
    subprocess.Popen([sys.executable,'-c',"import time,pathlib;time.sleep(2);pathlib.Path("+repr(str(output.parent.parent/'orphan'))+").touch()"])
    time.sleep(10)
if mode=='fail' and i==1:sys.exit(7)
time.sleep(0.2 if i==0 else 0.02)
print('[M::worker_pipeline::0.25*1.0] mapped 1 sequences',file=sys.stderr,flush=True)
output.write_text('q\\t200000\\t0\\t10\\t+\\tt'+str(i)+'\\t1000\\t0\\t10\\t10\\t10\\t60\\tcg:Z:10M\\n')
'''.replace('BEHAVIOR',repr(behavior)))
        mm.chmod(0o755)
        return str(mm),parts,query,[{'name':'q','length':200000}]

    def test_unknown_budget_single_part_small_work_and_low_budget_remain_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root)
            for args,selected,rows,reason in (
                (self.args(ordinary_group_memory_bytes=None),parts,records,'budget_unknown'),
                (self.args(),parts[:1],records,'single_original'),
                (self.args(),parts,[{'name':'q','length':100}],'too_little'),
                (self.args(threads=1),parts,records,'threads'),
                (self.args(ordinary_group_memory_bytes=1024),parts,records,'insufficient_budget')):
                plan=opa.plan(args,selected,rows);self.assertFalse(plan['enabled']);self.assertIn(reason,plan['reason'])
            with self.assertRaises(wa.ExperimentError):opa.plan(self.args(ordinary_group_memory_bytes=True),parts,records)

    def test_live_partial_threshold_third_part_queue_and_exact_native_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root);args=self.args()
            admission=opa.plan(args,parts,records)
            report=opa.attempt(mm,parts,q,root/'group',args,records,admission)
            self.assertEqual(report,json.loads((root/'group'/opa.RECEIPT).read_text()))
            self.assertNotIn('execution',report)
            self.assertFalse((root/'group/native.complete.paf').exists())
            self.assertEqual(len(list((root/'group').glob('part-*/native-attempt.json'))),3)
            starts=[e for e in report['events'] if e['event']=='start']
            self.assertEqual([e['part_index'] for e in starts],[0,1,2])
            self.assertEqual(starts[0]['mid_occ'],None)
            self.assertEqual([e['mid_occ'] for e in starts[1:]],[500,500])
            self.assertEqual(report['admission']['thread_shares'],[4,3])
            ends=[e['part_index'] for e in report['events'] if e['event']=='complete']
            self.assertLess(ends.index(1),ends.index(0))
            self.assertEqual(opa.verify(root/'group',mm,q,parts,records),report)
            for i,row in enumerate(report['parts']):
                command=row['native']['execution']['command']
                self.assertEqual(command[-2:], [parts[i]['path'],str(q)])
                self.assertEqual(command.count('-f'),0 if i==0 else 1)

    def test_bad_threshold_fragment_never_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'stderr';p.write_bytes(b'[M::mm_mapopt_update::0.1*1.0] mid_occ = 5')
            reader=opa.ThresholdReader(p);self.assertIsNone(reader.poll())
            with p.open('ab') as stream:stream.write(b'00\n')
            self.assertEqual(reader.poll(),500)

    def test_source_receipt_budget_and_schedule_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2);args=self.args()
            report=opa.attempt(mm,parts,q,root/'group',args,records,opa.plan(args,parts,records))
            mutations=[lambda d:d['parts'].pop(),lambda d:d['index_parts'].reverse(),
                lambda d:d.update(filter='0.01'),lambda d:d['admission'].update(group_budget_bytes=1024),
                lambda d:d['events'].insert(0,{'event':'start','part_index':1,'threads':3,'mid_occ':500,'after_seconds':0}),
                lambda d:d.update(aggregate_native_command_fabricated=True)]
            for mutate in mutations:
                changed=copy.deepcopy(report);mutate(changed);wa.write_json(root/'group'/opa.RECEIPT,changed)
                with self.assertRaises(wa.ExperimentError):opa.verify(root/'group',mm,q,parts,records)
            wa.write_json(root/'group'/opa.RECEIPT,report)
            path=root/'group/part-0000/native.complete.paf';path.write_bytes(path.read_bytes()+b'corrupt')
            with self.assertRaises(wa.ExperimentError):opa.verify(root/'group',mm,q,parts,records)

    def test_native_batch_count_rejects_missing_or_extra_query_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2);args=self.args()
            report=opa.attempt(mm,parts,q,root/'group',args,records,opa.plan(args,parts,records))
            # Rebind all native hashes so rejection is specifically the complete
            # query-count proof, not a generic stale-file/hash mismatch.
            for count in (0,2):
                changed=copy.deepcopy(report)
                stderr=root/'group/part-0001/native.stderr'
                original=stderr.read_bytes()
                stderr.write_bytes(original.replace(b'mapped 1 sequences',f'mapped {count} sequences'.encode()))
                native=changed['parts'][1]['native'];native['stderr_sha256']=wa.sha256(stderr)
                receipt=stderr.parent/'native-attempt.json';wa.write_json(receipt,native)
                changed['parts'][1]['receipt_sha256']=wa.sha256(receipt)
                wa.write_json(root/'group'/opa.RECEIPT,changed)
                with self.assertRaisesRegex(wa.ExperimentError,'complete ordinary query group'):
                    opa.verify(root/'group',mm,q,parts,records)
                stderr.write_bytes(original)

    def test_failed_part_never_retried_or_marked_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2,behavior='fail');args=self.args()
            with self.assertRaisesRegex(wa.ExperimentError,'no retry'):
                opa.attempt(mm,parts,q,root/'group',args,records,opa.plan(args,parts,records))
            report=json.loads((root/'group'/opa.RECEIPT).read_text());self.assertEqual(report['status'],'failed_no_retry')
            self.assertEqual(len([e for e in report['events'] if e['event']=='start']),2)
            self.assertFalse((root/'group/native.complete.paf').exists())
            with self.assertRaises(wa.ExperimentError):opa.verify(root/'group',mm,q,parts,records)

    def test_timeout_terminates_mapper_descendants_without_automatic_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2,behavior='timeout');args=self.args(timeout=0.2)
            with self.assertRaises(subprocess.TimeoutExpired):
                opa.attempt(mm,parts,q,root/'group',args,records,opa.plan(args,parts,records))
            time.sleep(2.1)
            self.assertFalse((root/'group/orphan').exists())
            self.assertEqual(json.loads((root/'group'/opa.RECEIPT).read_text())['status'],'failed_no_retry')

    def test_sigterm_cancels_all_native_children_and_keeps_failed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2,behavior='timeout')
            marker=root/'group'
            code="""import argparse, pathlib
import ordinary_partition_alignment as opa
import windowed_alignment as wa
root=pathlib.Path(ROOT)
parts=PARTS
args=argparse.Namespace(threads=4,timeout=20,minimap_batch='100K',minimap_filter=None,ordinary_group_memory_bytes=8*1024**3)
opa.attempt(MM,parts,root/'query.fa',root/'group',args,[{'name':'q','length':200000}],opa.plan(args,parts,[{'name':'q','length':200000}]))
""".replace('ROOT',repr(str(root))).replace('PARTS',repr(parts)).replace('MM',repr(mm))
            process=subprocess.Popen([os.sys.executable,'-B','-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+10
                while not (marker/'part-0000/native.stderr').is_file():
                    if process.poll() is not None or time.monotonic()>deadline:self.fail('controller failed before cancellation fixture')
                    time.sleep(0.02)
                time.sleep(0.25)
                process.send_signal(signal.SIGTERM);process.wait(timeout=10)
                self.assertNotEqual(process.returncode,0)
                self.assertEqual(json.loads((marker/opa.RECEIPT).read_text())['status'],'failed_no_retry')
                time.sleep(2.1);self.assertFalse((marker/'orphan').exists())
            finally:
                if process.poll() is None:process.kill();process.wait()

    def test_invalid_admission_is_rejected_before_any_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2);args=self.args()
            plan=opa.plan(args,parts,records);plan['group_budget_bytes']*=2
            with patch.object(opa.subprocess,'Popen',side_effect=AssertionError('must not launch')),self.assertRaises(wa.ExperimentError):
                opa.attempt(mm,parts,q,root/'group',args,records,plan)

    def test_checkpoint_reuses_real_part_receipts_without_new_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mm,parts,q,records=self.fixture(root,count=2);args=self.args()
            report=opa.attempt(mm,parts,q,root/'ordinary-native',args,records,opa.plan(args,parts,records))
            cache=pr.Checkpoint(root,{'same-input':'fixed'});cache.save_ordinary(partitioned=True)
            with patch.object(opa.subprocess,'Popen',side_effect=AssertionError('no retry')):
                self.assertEqual(cache.ordinary(mm,root/'full.mmi',q,parts=parts,records=records),report)
            with self.assertRaises(wa.ExperimentError):cache.ordinary(mm,root/'full.mmi',q)


class RealPartitionExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get('CGAT_MINIMAP2_BINARY');cls.bundle=os.environ.get('CGAT_NATIVE_CHAIN_STATE_BUNDLE')
        if not cls.mm or not cls.bundle:raise unittest.SkipTest('explicit pinned mapper/companion required')

    def fixture(self,root):
        rng=random.Random(2311302);seq=bytes(rng.choices(b'ACGT',k=120000))
        target=root/'target.fa';target.write_bytes(b'>chr1\n'+seq+b'\n>chr2\n'+bytes(rng.choices(b'ACGT',k=120000))+b'\n')
        rows=[(f'q{i}',seq[1000+i*100:41000+i*100]) for i in range(6)]
        rows.append(('long',seq[10000:100000]))
        query=root/'query.fa';query.write_bytes(b''.join(b'>'+n.encode()+b'\n'+s+b'\n' for n,s in rows))
        args=argparse.Namespace(target=target,query=query,out=root/'candidate',minimap2=self.mm,
            native_state_bundle=Path(self.bundle),threads=4,timeout=60,memory_gib=0,
            minimap_batch='100K',ordinary_group_memory_bytes=8*1024**3)
        return args

    def controls(self):
        from contextlib import ExitStack
        stack=ExitStack();make_plan=pp.make_plan;execute=wa.run_command
        stack.enter_context(patch.object(pp,'MAX_OPERATION',64000))
        stack.enter_context(patch.object(rp,'PROACTIVE_QUERY_LIMIT',64000))
        stack.enter_context(patch.object(pp,'make_plan',side_effect=lambda catalog,policy=None:make_plan(catalog,policy or pp.WindowPolicy(20000,4000))))
        def command(cmd,*a,**kw):
            cmd=list(cmd)
            if '-d' in cmd:cmd[1:1]=['-I','100000'] # TEST ONLY: same MMI used for all comparison commands.
            return execute(cmd,*a,**kw)
        stack.enter_context(patch.object(wa,'run_command',side_effect=command))
        stack.enter_context(redirect_stderr(io.StringIO()))
        return stack

    def test_mixed_pipeline_admits_real_leaf_receipts_and_resume_runs_zero_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=self.fixture(root)
            with self.controls():result=pa.experiment(args,resume_identity={'scope':'same-test-input'})
            self.assertTrue(result['ordinary_schedule_plan']['enabled'])
            native=result['ordinary_native'];self.assertEqual(native['kind'],opa.KIND)
            self.assertEqual(len(native['parts']),2)
            # Independent original full-MMI native QA baseline, not a product retry.
            ordinary=args.out/'ordinary-native'
            q=native['query']['path'];baseline=root/'baseline'
            original=nf.attempt(self.mm,args.out/'target.default.mmi',q,baseline,args)
            outputs=b''.join(Path(r['native']['path']).read_bytes() for r in native['parts'])
            self.assertEqual(outputs,Path(original['path']).read_bytes())
            self.assertEqual(result['admission']['status'],'proactive_recovery_admitted')
            old=Path(result['output_path']).read_bytes()
            # Budget now unknown still reuses an already-complete group, not
            # fall back by repeating its original whole query group.
            args.ordinary_group_memory_bytes=None
            with self.controls(),patch.object(pa.subprocess,'check_output',return_value='2.31-r1302\n'),patch.object(opa.subprocess,'Popen',side_effect=AssertionError('no new native mapping process')):
                again=pa.experiment(args,resume_identity={'scope':'same-test-input'})
            self.assertEqual(again['cache_reused']['ordinary_group'],1)
            self.assertEqual(Path(again['output_path']).read_bytes(),old)

    def test_explicit_fast_fraction_first_part_is_inherited_without_conflicting_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=self.fixture(root);args.minimap_filter='0.01'
            with self.controls():result=pa.experiment(args)
            native=result['ordinary_native'];self.assertEqual(native['kind'],opa.KIND)
            first,second=[row['native']['execution']['command'] for row in native['parts']]
            self.assertEqual(first[first.index('-f')+1],'0.01')
            self.assertEqual(second[second.index('-f')+1],str(native['mid_occ']))
            self.assertEqual(first.count('-f'),1);self.assertEqual(second.count('-f'),1)
            baseline=nf.attempt(self.mm,args.out/'target.default.mmi',native['query']['path'],root/'independent-QA-baseline',args)
            self.assertEqual(b''.join(Path(row['native']['path']).read_bytes() for row in native['parts']),Path(baseline['path']).read_bytes())

    def test_performance_source_upgrade_retains_completed_native_and_long_cells(self):
        import test_proactive_resume as fixtures
        import server_alignment as sa
        for source_file in ('pre_partition_runtime.json', 'post_metadata_fix_runtime.json'):
            with self.subTest(source_file=source_file), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);owner=fixtures.RealResumeTests();owner.mm=self.mm;owner.bundle=self.bundle
                runtime,args=owner.fixture(root)
                manifest=json.loads((runtime/sa.MANIFEST).read_text())
                files=json.loads(Path(__file__).with_name('test_data').joinpath(source_file).read_text())
                digest=lambda v:__import__('hashlib').sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                manifest['native_resume_source_profiles']=[[digest(files),digest(manifest['files_sha256'])]]
                wa.write_json(runtime/sa.MANIFEST,manifest)
                with owner.controls():first=sa.run_reference(args,runtime_root=runtime)
                attempt=Path(first['attempt']);control=pr.read_json(attempt/'server-alignment.json')
                old_runtime={**control['runtime'],'sha256':'d'*64,'files_sha256':files}
                control['runtime']=old_runtime;wa.write_json(attempt/'server-alignment.json',control)
                locator=pr.read_json(args.run_dir/pr.LOCATOR);locator['key']['runtime_sha256']='d'*64
                state=pr.read_json(attempt/'selective'/pr.STATE);state['key']=locator['key']
                wa.write_json(args.run_dir/pr.LOCATOR,locator);wa.write_json(attempt/'selective'/pr.STATE,state)
                output=(args.run_dir/'result.paf').read_bytes()
                with owner.controls(),patch.object(wa,'run_command',side_effect=AssertionError('performance upgrade must not repeat completed work')):
                    again=sa.run_reference(args,runtime_root=runtime)
                self.assertTrue(again['attempt_reused']);self.assertEqual(again['cache_reused']['ordinary_group'],1)
                self.assertEqual(again['cache_reused']['long_cells'],2)
                self.assertEqual((args.run_dir/'result.paf').read_bytes(),output)

    def test_unknown_budget_keeps_old_single_native_command_even_with_two_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=self.fixture(root);args.ordinary_group_memory_bytes=None
            with self.controls(),patch.object(opa,'attempt',side_effect=AssertionError('unknown budget must not parallelize')):
                result=pa.experiment(args)
            self.assertFalse(result['ordinary_schedule_plan']['enabled'])
            self.assertEqual(result['ordinary_native']['status'],'native_success')
            self.assertEqual(len(result['ordinary_native']['index_sequence_counts']),2)
