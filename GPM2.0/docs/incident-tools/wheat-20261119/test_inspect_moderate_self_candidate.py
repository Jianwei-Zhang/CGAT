import copy
from pathlib import Path
import unittest
import inspect_moderate_self_candidate as inspection
import test_full_self_moderate_candidate as fixtures


class ModerateInspectionTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.ModerateCandidateTests();fixture.setUp()
        self.manifest,self.batch,self.native=fixture.manifest,{**fixture.batch,'key':'native-key'},fixture.native
        self.report={'scope':inspection.driver.SCOPE,'status':'moderate_candidate_complete_not_adopted',
            'candidate_adopted':False,'analysis_workspace_modified':False,'whole_records_preserved':True,
            'mapping':{'returncode':0},'restoration':{'returncode':0},'native_batch_key':'native-key',
            'seed_fraction':'0.002','native_command':self.native,
            'command':inspection.driver.moderate_command(self.manifest,self.batch,self.native,'0.002'),
            'code':inspection.pilot.identities([Path(inspection.driver.__file__)])}

    def test_complete_middle_contract(self):
        inspection.candidate_contract(self.report,self.manifest,self.batch)

    def test_complete_default_contract(self):
        report=copy.deepcopy(self.report);report['seed_fraction']='0.001'
        report['command']=inspection.driver.moderate_command(self.manifest,self.batch,self.native)
        inspection.candidate_contract(report,self.manifest,self.batch)

    def test_partial_timeout_wrong_fraction_or_key_rejected(self):
        for key,value in (('status','running'),('mapping',{'returncode':124}),('restoration',{'returncode':1}),
                          ('candidate_adopted',True),('analysis_workspace_modified',True),
                          ('whole_records_preserved',False),('native_batch_key','other'),('seed_fraction','0.005'),
                          ('scope','other')):
            with self.subTest(key=key),self.assertRaises(ValueError):
                inspection.candidate_contract({**self.report,key:value},self.manifest,self.batch)

    def test_fraction_label_cannot_disagree_with_executed_command(self):
        with self.assertRaisesRegex(ValueError,'actual command'):
            inspection.candidate_contract({**self.report,'seed_fraction':'0.001'},self.manifest,self.batch)

    def test_changed_flags_and_driver_rejected(self):
        report=copy.deepcopy(self.report);report['command'].remove('-X')
        with self.assertRaises(ValueError):inspection.candidate_contract(report,self.manifest,self.batch)
        report=copy.deepcopy(self.report);next(iter(report['code'].values()))['sha256']='changed'
        with self.assertRaises(ValueError):inspection.candidate_contract(report,self.manifest,self.batch)
        with self.assertRaises(ValueError):inspection.candidate_contract({**self.report,'code':{}},self.manifest,self.batch)

if __name__=='__main__':unittest.main()
