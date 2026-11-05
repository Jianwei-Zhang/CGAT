"""Read-only resource envelopes, live dispatcher binding, no customer config."""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import ordinary_partition_alignment as opa
import ordinary_resource_grant as org


class GrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.proc=self.root/'proc';self.mount=self.root/'cgroup'
        (self.proc/'self').mkdir(parents=True);self.mount.mkdir();self.run=self.root/'run';self.run.mkdir()
        self.pid=os.getppid();(self.proc/str(self.pid)).mkdir()
        (self.proc/str(self.pid)/'stat').write_text(f'{self.pid} (a tricky ) process) '+' '.join(['S']+['0']*18+['42'])+'\n')
        self.raw={'schema':1,'parent_pid':self.pid,'parent_start':'42','command':str(self.run/'command.sh'),
                  'threads':8,'run_id':'test-run','unit_id':'ref:q','exclusive':True}
        self.env={'GPM_REPORT_RUN_ID':'test-run','GPM_REPORT_UNIT_ID':'ref:q',org.ENV:json.dumps(self.raw)}

    def context(self):
        return org.dispatch_context(self.run,8,environment=self.env,proc=self.proc)

    def mount_tree(self,*,version=2,member='/job/step',mount_root='/',limits=None):
        kind='cgroup2' if version==2 else 'cgroup'
        controllers='' if version==2 else 'cpu,memory'
        (self.proc/'self/cgroup').write_text(f'0:{controllers}:{member}\n')
        mount=str(self.mount).replace(' ','\\040')
        options='rw' if version==2 else 'rw,memory'
        (self.proc/'self/mountinfo').write_text(f'30 20 0:30 {mount_root} {mount} rw - {kind} cgroup {options}\n')
        name,usage=(('memory.max','memory.current') if version==2 else ('memory.limit_in_bytes','memory.usage_in_bytes'))
        for path,(limit,used) in (limits or {'':('max',0),'job':(64*org.GIB,8*org.GIB),'job/step':(32*org.GIB,4*org.GIB)}).items():
            directory=self.mount/path;directory.mkdir(parents=True,exist_ok=True)
            (directory/name).write_text(str(limit));(directory/usage).write_text(str(used))

    def test_live_context_requires_parent_start_run_unit_command_threads_and_exclusivity(self):
        self.assertTrue(self.context()['enabled'])
        for field,value in (('parent_pid',self.pid+1),('parent_start','changed'),('command','/other/command.sh'),
                            ('threads',4),('unit_id','chr:q'),('run_id','old'),('exclusive',False)):
            with self.subTest(field=field):
                raw={**self.raw,field:value};self.env[org.ENV]=json.dumps(raw)
                self.assertFalse(self.context()['enabled'])
        self.env[org.ENV]='not-json';self.assertFalse(self.context()['enabled'])
        self.env[org.ENV]='x'*20000;self.assertFalse(self.context()['enabled'])

    def test_v2_uses_tightest_ancestor_headroom_not_leaf_limit(self):
        self.mount_tree(limits={'':('max',0),'job':(40*org.GIB,36*org.GIB),'job/step':(32*org.GIB,4*org.GIB)})
        value=org.grant(self.context(),environment=self.env,proc=self.proc)
        self.assertTrue(value['enabled']);self.assertEqual(value['available_bytes'],4*org.GIB)
        self.assertEqual(value['budget_bytes'],3*org.GIB)
        self.assertFalse(value['physical_memory_reservation']);self.assertFalse(value['host_ram_used']);self.assertFalse(value['qc_memory_used'])
        self.assertEqual(len(value['sources']),2)

    def test_v1_unlimited_sentinel_and_finite_parent_are_distinguished(self):
        self.mount_tree(version=1,limits={'':(9223372036854771712,0),'job':(20*org.GIB,3*org.GIB),'job/step':(10*org.GIB,2*org.GIB)})
        rows,reason=org.cgroup_envelopes(proc=self.proc)
        self.assertIsNone(reason);self.assertEqual(len(rows),2)
        self.assertEqual(min(r['available_bytes'] for r in rows),8*org.GIB)
        self.assertTrue(all(r['source']=='cgroup_v1' for r in rows))

    def test_mount_root_and_escaped_mount_paths_are_honored(self):
        self.mount=self.root/'cgroup with spaces';self.mount.mkdir()
        self.mount_tree(member='/slurm/job/step',mount_root='/slurm/job',limits={'':('max',0),'step':(10*org.GIB,2*org.GIB)})
        rows,reason=org.cgroup_envelopes(proc=self.proc)
        self.assertIsNone(reason);self.assertEqual(rows[0]['available_bytes'],8*org.GIB)
        self.assertEqual(rows[0]['path'],str(self.mount/'step'))

    def test_cgroup_namespace_root_maps_to_mounted_root(self):
        self.mount_tree(member='/',mount_root='/slurm/job',limits={'':(10*org.GIB,2*org.GIB)})
        rows,reason=org.cgroup_envelopes(proc=self.proc)
        self.assertIsNone(reason);self.assertEqual(rows[0]['available_bytes'],8*org.GIB)

    def test_missing_nonroot_or_ambiguous_membership_declines_extra_parallelism(self):
        for bad in ('missing','ambiguous','parent_walk'):
            with self.subTest(bad=bad):
                self.mount_tree()
                if bad=='missing':(self.mount/'job/memory.max').unlink()
                elif bad=='ambiguous':(self.proc/'self/mountinfo').write_text(f'30 20 0:30 /other {self.mount} rw - cgroup2 cgroup rw\n')
                else:(self.proc/'self/cgroup').write_text('0::/../../job/step\n')
                env={**self.env,'SLURM_JOB_ID':'123','SLURM_JOB_NUM_NODES':'1','SLURM_MEM_PER_NODE':'512000'}
                value=org.grant(self.context(),environment=env,proc=self.proc)
                self.assertFalse(value['enabled']);self.assertEqual(value['reason'],'effective_memory_envelope_unverifiable')

    def test_root_without_memory_max_is_not_mistaken_for_unreadable_hidden_ancestor(self):
        self.mount_tree(member='/',limits={'':('max',0)})
        (self.mount/'memory.max').unlink()
        env={**self.env,'SLURM_JOB_ID':'123','SLURM_JOB_NUM_NODES':'1','SLURM_MEM_PER_NODE':'512000'}
        value=org.grant(self.context(),environment=env,proc=self.proc)
        self.assertTrue(value['enabled']);self.assertEqual(value['available_bytes'],512000*1024**2)
        self.assertEqual(value['sources'][0]['source'],'slurm_memory_per_node')
        self.assertFalse(value['sources'][0]['free_memory_observed'])

    def test_zero_limit_or_over_limit_usage_never_admits_memory(self):
        for limit,used in ((0,0),(org.GIB,2*org.GIB)):
            self.mount_tree(member='/',limits={'':(limit,used)})
            value=org.grant(self.context(),environment=self.env,proc=self.proc)
            self.assertFalse(value['enabled']);self.assertIsNone(value['budget_bytes'])

    def test_single_task_scheduler_units_cpu_counts_and_cgroup_intersection(self):
        self.mount_tree(member='/',limits={'':(100*org.GIB,20*org.GIB)})
        env={**self.env,'SLURM_JOB_ID':'123','SLURM_JOB_NUM_NODES':'1','SLURM_NTASKS':'1',
             'SLURM_MEM_PER_CPU':'2048','SLURM_CPUS_ON_NODE':'16'}
        value=org.grant(self.context(),environment=env,proc=self.proc)
        self.assertTrue(value['enabled']);self.assertEqual(value['available_bytes'],32*org.GIB)
        env['SLURM_MEM_PER_NODE']='16384'
        self.assertEqual(org.grant(self.context(),environment=env,proc=self.proc)['available_bytes'],16*org.GIB)

    def test_ambiguous_scheduler_values_do_not_use_host_ram_or_qc(self):
        for values in ({'SLURM_JOB_NUM_NODES':'2'},{'SLURM_NTASKS':'4'},{'SLURM_MEM_PER_NODE':'0'},
                       {'SLURM_MEM_PER_NODE':'500G'},{'SLURM_MEM_PER_CPU':'2048','SLURM_CPUS_ON_NODE':'bad'}):
            env={'SLURM_JOB_ID':'123','SLURM_JOB_NUM_NODES':'1','SLURM_MEM_PER_NODE':'512000',**values}
            rows,reason=org.slurm_envelopes(env)
            self.assertFalse(rows);self.assertIsNotNone(reason)
        self.mount_tree(member='/',limits={'':('max',0)})
        env={**self.env,'GPM_RUN_QC_MEMORY_GB':'999999','MEMORY_GB':'999999'}
        value=org.grant(self.context(),environment=env,proc=self.proc)
        self.assertFalse(value['enabled']);self.assertIsNone(value['budget_bytes'])

    def test_parent_lease_is_revalidated_at_mapping_boundary(self):
        self.mount_tree();context=self.context()
        (self.proc/str(self.pid)/'stat').write_text('invalid')
        value=org.grant(context,environment=self.env,proc=self.proc)
        self.assertFalse(value['enabled']);self.assertEqual(value['reason'],'dispatcher_context_changed_before_mapping')

    def test_resolution_is_once_per_invocation_and_private_budget_remains_explicit(self):
        args=argparse.Namespace(ordinary_resource_context={'enabled':True})
        with patch.object(org,'grant',return_value={'budget_bytes':8*org.GIB}) as discover:
            self.assertEqual(org.resolve(args),8*org.GIB);self.assertEqual(org.resolve(args),8*org.GIB)
            self.assertEqual(discover.call_count,1)
        args=argparse.Namespace(ordinary_resource_context={'enabled':False},ordinary_group_memory_bytes=4*org.GIB)
        with patch.object(org,'grant',side_effect=AssertionError('private audited grant is already explicit')):
            self.assertEqual(org.resolve(args),4*org.GIB)

    def test_low_or_unknown_envelope_does_not_start_parallel_worker(self):
        args=argparse.Namespace(threads=8,minimap_batch='100K',ordinary_resource_context={'enabled':False})
        parts=[{'start':0,'end':1},{'start':1,'end':2}];rows=[{'length':200000}]
        with patch.object(opa.subprocess,'Popen',side_effect=AssertionError('planning must not map')):
            self.assertFalse(opa.plan(args,parts,rows)['enabled'])
            args=argparse.Namespace(threads=8,minimap_batch='100K',ordinary_resource_context={'enabled':True})
            with patch.object(org,'grant',return_value={'budget_bytes':org.GIB}):
                self.assertFalse(opa.plan(args,parts,rows)['enabled'])


class RealDispatchGrantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get('CGAT_MINIMAP2_BINARY');cls.bundle=os.environ.get('CGAT_NATIVE_CHAIN_STATE_BUNDLE')
        if not cls.mm or not cls.bundle:raise unittest.SkipTest('explicit pinned mapper/helper required')

    def prepared(self,root,*,ordinary=False,split=True):
        import test_proactive_resume as fixtures
        import test_ordinary_partition_alignment as inputs
        owner=fixtures.RealResumeTests();owner.mm=self.mm;owner.bundle=self.bundle
        service=root/'service';service.mkdir();runtime,args=owner.fixture(service)
        data=root/'data';data.mkdir();factory=inputs.RealPartitionExecutionTests();factory.mm=self.mm;factory.bundle=self.bundle;mapping=factory.fixture(data)
        args.target=mapping.target;args.query=mapping.query;args.threads=4
        if ordinary:
            raw=args.query.read_bytes().split(b'>long\n')[0];args.query.write_bytes(raw)
        (args.server_dir/'metadata/prepare_options.tsv').write_text('key\tvalue\nminimap_batch\t100K\n')
        mount=root/'resource-fixture';mount.mkdir()
        (mount/'memory.max').write_text(str(8*org.GIB));(mount/'memory.current').write_text(str(org.GIB))
        membership=root/'cgroup.txt';membership.write_text('0::/\n')
        mounts=root/'mountinfo.txt';mounts.write_text(f'30 20 0:30 / {mount} rw - cgroup2 cgroup rw\n')
        worker=root/'worker.py'
        spec={'runtime':str(runtime),'server_dir':str(args.server_dir),'run_dir':str(args.run_dir),
              'target':str(args.target),'query':str(args.query),'membership':str(membership),'mounts':str(mounts),'split_index':split}
        worker.write_text("""import argparse,json,sys
from pathlib import Path
from unittest.mock import patch
spec=SPEC
sys.path.insert(0,spec['runtime'])
import server_alignment as sa
import ordinary_resource_grant as org
import proactive_reference_plan as pp
import recovery_publication as rp
import windowed_alignment as wa
# QA-only mounted-resource metadata and reduced-size multipart/long controls.
# Parent PID/start ownership and every mapper/receipt are real. No private
# ordinary_group_memory_bytes argument or provider result is injected.
read=org._read;calls=[]
def resource_read(path):
    path=Path(path)
    if str(path)=='/proc/self/cgroup':calls.append('cgroup');return Path(spec['membership']).read_text()
    if str(path)=='/proc/self/mountinfo':calls.append('mountinfo');return Path(spec['mounts']).read_text()
    return read(path)
org._read=resource_read
execute=wa.run_command;make_plan=pp.make_plan
def command(cmd,*a,**kw):
    cmd=list(cmd)
    if '-d' in cmd and spec['split_index']:cmd[1:1]=['-I','100000']
    return execute(cmd,*a,**kw)
args=argparse.Namespace(server_dir=Path(spec['server_dir']),run_dir=Path(spec['run_dir']),
    target=Path(spec['target']),query=Path(spec['query']),threads=int(__import__('os').environ['GPM_TASK_THREADS']),preset='asm10',result='result.paf')
with patch.object(pp,'MAX_OPERATION',64000),patch.object(rp,'PROACTIVE_QUERY_LIMIT',64000),patch.object(pp,'make_plan',side_effect=lambda catalog,policy=None:make_plan(catalog,policy or pp.WindowPolicy(20000,4000))),patch.object(wa,'run_command',side_effect=command):
    result=sa.run_reference(args,runtime_root=Path(spec['runtime']))
print('QA_GRANT_RESULT '+json.dumps({'result':result,'resource_reads':calls}),flush=True)
""".replace('SPEC',repr(spec),1))
        script=args.run_dir/'command.sh';script.write_text(f'exec "{sys.executable}" "{worker}"\n')
        return args,script

    def test_actual_dispatcher_to_server_grant_to_native_parts_and_normal_fallbacks(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/tools'))
        from alignment_tasks import AlignmentTask,run_tasks
        for mode in ('mixed_exclusive','mixed_siblings','mixed_single_part','ordinary_exclusive'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);count=2 if mode=='mixed_siblings' else 1;prepared=[]
                for i in range(count):
                    child=root/str(i);child.mkdir();prepared.append(self.prepared(child,ordinary=mode=='ordinary_exclusive',split=mode!='mixed_single_part'))
                tasks=[AlignmentTask('ref:'+str(i),script,4) for i,(args,script) in enumerate(prepared)]
                lines=[];env={**os.environ,'PATH':str(Path(self.mm).parent)+os.pathsep+os.environ['PATH'],
                              'GPM_REPORT_RUN_ID':'real-dispatch-grant','GPM_REFERENCE_DISPATCH':'stale'}
                # Ignore ambient scheduler settings in this mounted-container QA
                # control; no real scheduler allocation is being claimed here.
                env={k:v for k,v in env.items() if not k.startswith('SLURM_')}
                code=run_tasks(tasks,4*count,{},lambda:None,lambda *_:None,
                    lambda task,line:lines.append((task.unit_id,line)),lambda *_:None,env)
                self.assertEqual(code,0,'\n'.join(line for _,line in lines)[-12000:])
                results={unit:json.loads(line.removeprefix('QA_GRANT_RESULT ')) for unit,line in lines if line.startswith('QA_GRANT_RESULT ')}
                self.assertEqual(len(results),count)
                for i,(args,script) in enumerate(prepared):
                    value=results['ref:'+str(i)];receipt=value['result'];self.assertTrue(receipt['result_published'])
                    candidate=Path(receipt['attempt'])/'selective'
                    report=json.loads((candidate/'proactive-candidate.json').read_text())
                    if mode=='ordinary_exclusive':
                        self.assertEqual(report['routing_mode'],'native_complete_unchanged')
                        self.assertFalse((candidate/'target.default.mmi').exists());self.assertEqual(value['resource_reads'],[])
                        self.assertEqual(report['native']['execution']['command'][-2:], [str(args.target),str(args.query)])
                    elif mode in ('mixed_siblings','mixed_single_part'):
                        self.assertEqual(report['ordinary_native']['status'],'native_success')
                        self.assertFalse(report['ordinary_schedule_plan']['enabled']);self.assertEqual(value['resource_reads'],[])
                        if mode=='mixed_siblings':self.assertIn('siblings',receipt['ordinary_resource_context']['reason'])
                        else:self.assertIn('single_original_index_part',report['ordinary_schedule_plan']['reason'])
                    else:
                        plan=report['ordinary_schedule_plan'];self.assertTrue(plan['enabled'])
                        grant=plan['resource_grant'];self.assertTrue(grant['enabled'])
                        self.assertEqual(grant['budget_bytes'],6*org.GIB)
                        self.assertEqual(value['resource_reads'],['cgroup','mountinfo'])
                        self.assertTrue(receipt['ordinary_resource_context']['enabled'])
                        self.assertEqual(report['ordinary_native']['kind'],opa.KIND)
                        self.assertEqual(report['ordinary_native']['admission']['group_budget_bytes'],6*org.GIB)
                        self.assertEqual([p['threads'] for p in report['ordinary_native']['parts']],[2,2])
                    if mode!='ordinary_exclusive':
                        admission=json.loads((Path(receipt['attempt'])/'recovery-admission.json').read_text())
                        self.assertEqual(admission['status'],'proactive_recovery_admitted')


if __name__=='__main__':unittest.main()
