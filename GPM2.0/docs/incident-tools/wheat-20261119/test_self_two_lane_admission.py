from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'server/tools'))
from alignment_tasks import AlignmentTask
import self_two_lane_admission as admission


class TwoLaneTests(unittest.TestCase):
    def setUp(self):
        scripts={str(i):{'path':f'/guarded/fast-{i}.sh','sha256':str(i)} for i in range(4)}
        self.profile=SimpleNamespace(native={'target_lengths':{'t':731_737_596},
            'batches':[{'directory':f'/work/batch-{i}','entries':[{'length':220_255_611}]} for i in range(4)]},
            policy={'seed_fraction':'0.005'},selected=list(range(4)))
        guard={'scope':'per_process_virtual_address_space','limit_bytes':64*1024**3,
            'scripts':{s['path']:{'guarded_script_sha256':s['sha256']} for s in scripts.values()}}
        self.bindings=SimpleNamespace(plan={'resource_guard':guard},profiles={'op':self.profile},rows={'op':{'scripts':scripts}})
        self.tasks=[AlignmentTask('fast',Path(scripts[str(i)]['path']),1,work=100-i,largest_fraction=1) for i in range(4)]
        self.native=AlignmentTask('native',Path('/native/small.sh'),1,work=10)
        self.cross=AlignmentTask('native',Path('/work/a_vs_b/command.sh'),1,work=1000)

    def dispatcher(self,**kw):return admission.SelfDispatcher(self.bindings,lambda t:t.unit_id=='unknown',max_fast=kw.get('max_fast',2))

    def test_only_two_fast_and_cpu_slots_are_respected(self):
        d=self.dispatcher();self.assertEqual(len(d(self.tasks,16,16,[],16)),2)
        self.assertEqual(len(d(self.tasks,1,16,[],16)),1)
        self.assertEqual(len(d(self.tasks,16,16,[],1)),1)
        active=[{'task':self.tasks[0],'threads':1,'started':0}]
        self.assertEqual(len(d(self.tasks[1:],15,16,active,16)),1)
        active.append({'task':self.tasks[1],'threads':1,'started':0})
        self.assertEqual(d(self.tasks[2:],14,16,active,16),[])

    def test_fast_native_pools_are_not_mixed(self):
        d=self.dispatcher()
        self.assertEqual(d([self.native],15,16,[{'task':self.tasks[0]}],16),[])
        self.assertEqual(d(self.tasks,15,16,[{'task':self.native}],16),[])

    def test_active_pool_fills_free_lane_past_other_pool_queue_head(self):
        d=self.dispatcher()
        waiting_native=AlignmentTask('native',Path('/native/larger.sh'),1,work=200)
        # An incompatible queue head must not block ready work in the active
        # pool. It remains pending; this does not permit mixing the pools.
        selected=d([waiting_native,self.tasks[1]],15,16,[{'task':self.tasks[0]}],16)
        self.assertEqual([task for task,_threads in selected],[self.tasks[1]])
        selected=d([self.tasks[0],self.native],15,16,[{'task':waiting_native}],16)
        self.assertEqual([task for task,_threads in selected],[self.native])

    def test_cross_unknown_and_unmeasured_profiles_stay_exclusive(self):
        d=self.dispatcher()
        for task in (self.cross,AlignmentTask('unknown',Path('/unknown'),1,work=1000)):
            self.assertEqual([t for t,_ in d([task]+self.tasks,16,16,[],16)],[task])
            self.assertEqual(d(self.tasks,15,16,[{'task':task}],16),[])
        for field,value in (('fraction','0.001'),('target',800_000_001),('query',300_000_001)):
            self.setUp()
            if field=='fraction':self.profile.policy['seed_fraction']=value
            elif field=='target':self.profile.native['target_lengths']['t']=value
            else:self.profile.native['batches'][0]['entries'][0]['length']=value
            d=self.dispatcher();self.assertEqual(d.kind(self.tasks[0]),'exclusive')

    def test_native_small_keeps_existing_one_gigabase_target_envelope(self):
        self.profile.native['target_lengths']['t']=900_000_000
        native=AlignmentTask('native',Path('/work/batch-0/command.sh'),1,work=10)
        self.assertEqual(self.dispatcher().kind(native),'native')
        self.profile.native['target_lengths']['t']=1_000_000_001
        self.assertEqual(self.dispatcher().kind(native),'exclusive')

    def test_missing_or_changed_guard_is_rejected(self):
        with self.assertRaises(ValueError):self.dispatcher(max_fast=4)
        self.bindings.plan['resource_guard']['limit_bytes']=128*1024**3
        with self.assertRaises(ValueError):self.dispatcher()
        self.bindings.plan['resource_guard']['limit_bytes']=64*1024**3
        self.bindings.plan['resource_guard']['scripts']['/guarded/fast-0.sh']['guarded_script_sha256']='changed'
        with self.assertRaises(ValueError):self.dispatcher()

if __name__=='__main__':unittest.main()
