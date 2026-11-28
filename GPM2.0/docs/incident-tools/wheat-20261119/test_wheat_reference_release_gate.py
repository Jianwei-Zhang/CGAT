import unittest
from wheat_reference_release_gate import classify, control_group, ng50


class CalibratedGateTests(unittest.TestCase):
    def test_coordinate_evidence_and_ratio_are_both_required(self):
        row = dict(current_group="4A", old_group="7B", bp=200000)
        for a,b,expected in [(100000,10000,True),(100000,10001,False),(99999,0,False),(0,0,False)]:
            self.assertEqual(classify(row,a,b)=="locally_supported_split", expected)
        self.assertEqual(classify(dict(row,old_group="Un"),None,None),"unplaced_comparator")
        with self.assertRaises(ValueError):classify(dict(row,old_group="unknown"),200000,0)
        with self.assertRaises(ValueError):classify(row,200001,0)

    def test_ng50_uses_chromosome_length_and_exact_integer_half(self):
        self.assertEqual(ng50([50,7],101),7)
        self.assertEqual(ng50([50],101),0)
        self.assertEqual(ng50([50],100),50)

    def test_each_old_oriented_slice_must_still_exist_in_one_piece(self):
        o=("assembly","contig","+",10,60)
        def run(others):
            def metrics(rows):return dict(selected_source_bp=sum(y-x for *_,x,y in rows),selected_reference_bp=49,slices=len(rows),source_slice_n50=50,has_path=True)
            return control_group([o],others,metrics([o]),metrics(others),100)
        self.assertTrue(run([o,("asm2","new","+",0,5)])["passed"])
        self.assertTrue(run([(*o[:3],0,80)])["passed"])
        self.assertFalse(run([(*o[:3],10,35),(*o[:3],35,60)])["passed"])
        for swapped in [("other",*o[1:]),(*o[:2],"-",*o[3:])]:self.assertFalse(run([swapped])["passed"])
