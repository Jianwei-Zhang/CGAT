import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import q0_science_handoff_gate as gate


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.work=self.root/'work';self.work.mkdir()
        transition=self.root/'transition.json';transition.write_text('{}')
        preflight=self.root/'preflight.json';preflight.write_text('{}')
        self.config={'workspace':str(self.work),'old_job':1,'protected_baseline':2,
            'transition':self.record(transition),'initial_preflight':self.record(preflight)}
        self.old={'jobId':'1','state':'FAILED','resGroups':[{'nodeResUsages':[{'pids':'-'}]}]}
        self.new={'jobId':'3','state':'RUNNING','queue':'x86','taskExecNodesCount':1,'taskExecNodes':'host',
            'resGroups':[{'resAlloc':{'cpu':32,'mem':327680},'resLimit':{'mem':327680}}]}
        self.release={'status':'old_job_terminal_and_normal_lock_released','old_job':1,'new_job':3,
            'protected_baseline':2,'transition_sha256':self.config['transition']['sha256'],'ready_sha256':'ready'}
        self.save_scheduler()

    def record(self,p):return {'path':str(p),'sha256':gate.digest(p)}
    def save_scheduler(self):
        for name,row in [('old',self.old),('new',self.new)]:
            path=self.root/(name+'.json');path.write_text(json.dumps({'data':{'successData':[row]}}))
            self.release[name+'_scheduler']=self.record(path)
    def validate(self):gate.validate_handoff(self.config,self.release,self.root,'ready','host')

    def test_exact_ready_allocation_terminal_previous_and_free_lock_pass(self):self.validate()
    def test_active_previous_or_surviving_child_fails(self):
        self.old['state']='RUNNING';self.save_scheduler()
        with self.assertRaisesRegex(ValueError,'terminal'):self.validate()
        self.old['state']='FAILED';self.old['resGroups'][0]['nodeResUsages'][0]['pids']='123';self.save_scheduler()
        with self.assertRaisesRegex(ValueError,'child'):self.validate()
    def test_wrong_node_or_insufficient_resources_fails(self):
        original=copy.deepcopy(self.new)
        for change in ('node','cpu','mem','limit','nodes'):
            self.new=copy.deepcopy(original)
            if change=='node':self.new['taskExecNodes']='another'
            if change=='cpu':self.new['resGroups'][0]['resAlloc']['cpu']=16
            if change=='mem':self.new['resGroups'][0]['resAlloc']['mem']=163840
            if change=='limit':self.new['resGroups'][0]['resLimit']['mem']=163840
            if change=='nodes':self.new['taskExecNodesCount']=2
            self.save_scheduler()
            with self.assertRaisesRegex(ValueError,'allocation'):self.validate()
    def test_lock_is_never_removed_by_gate(self):
        lock=self.work/'.run_all/lock';lock.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'lock'):self.validate()
        self.assertTrue(lock.is_dir())
    def test_completed_original_partial_requires_restaging(self):
        marker=self.work/'grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/success.json'
        marker.parent.mkdir(parents=True);marker.write_text('{}')
        with self.assertRaisesRegex(ValueError,'re-stage'):self.validate()
    def test_forged_ready_binding_and_changed_scheduler_bytes_fail(self):
        self.release['ready_sha256']='other'
        with self.assertRaisesRegex(ValueError,'identity'):self.validate()
        self.release['ready_sha256']='ready';(self.root/'old.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'dependency'):self.validate()


if __name__=='__main__':unittest.main()
