from types import SimpleNamespace
import unittest
from regional_chain_recovery_gate import recovery_decision, validated_core_coverage


class RecoveryTests(unittest.TestCase):
    def test_large_core_never_hides_an_empty_small_core(self):
        result=recovery_decision(((0,10000),(10000,10010)),'self',{'cross'},{'cross':[(0,10000)]})
        self.assertTrue(result['native_recovery_required'])
        self.assertEqual(result['cores'][-1]['covered_bases'],0)
    def test_each_dataset_must_supply_its_own_coverage(self):
        result=recovery_decision(((0,100),),'self',{'a','b'},{'a':[(0,100)],'b':[]})
        self.assertTrue(result['native_recovery_required'])
    def test_integer_threshold_boundary_and_looser_intra(self):
        for count,expected in [(97,True),(98,False)]:
            result=recovery_decision(((0,100),),'self',{'self','cross'},{'self':[(0,90)],'cross':[(0,count)]})
            self.assertIs(result['native_recovery_required'],expected)
        self.assertTrue(recovery_decision(((0,100),),'self',{'self'},{'self':[(0,89)]})['native_recovery_required'])
    def test_overlap_does_not_double_count(self):
        result=recovery_decision(((0,100),),'self',{'cross'},{'cross':[(0,50),(0,50)]})
        self.assertTrue(result['native_recovery_required']);self.assertEqual(result['cores'][0]['covered_bases'],50)
    def test_bad_frames_or_missing_datasets_fail_closed(self):
        for cores,targets,cov in [(((0,0),),{'x'},{'x':[]}),(((0,100),(90,110)),{'x'},{'x':[]}),(((0,100),),{'x'},{}),(((0,100),),set(),{})]:
            with self.assertRaises(ValueError):recovery_decision(cores,'self',targets,cov)
    def test_only_quality_paired_blocks_count_with_source_offsets(self):
        q=SimpleNamespace(window_id='q',length=100,start=1000,cores=((1010,1050),))
        block=lambda op,a,b:SimpleNamespace(operation=op,query=SimpleNamespace(start=a,end=b,length=b-a))
        valid=SimpleNamespace(matches=95,block_length=100,target_name='t',aligned_blocks=lambda:[block('M',0,30),block('X',30,50),block('M',50,100)])
        invalid=SimpleNamespace(matches=94,block_length=100,target_name='t',aligned_blocks=lambda:[block('M',0,100)])
        case={'query':q,'lengths':{'t':100},'td':{'t':'cross'},'qd':'self'}
        self.assertEqual(validated_core_coverage(None,case,lambda *a,**k:[valid,invalid]),{'cross':[(1010,1030)]})


if __name__=='__main__':unittest.main()
