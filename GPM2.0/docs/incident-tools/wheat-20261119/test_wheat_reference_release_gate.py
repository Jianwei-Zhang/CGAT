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


class CarrierSliceTests(unittest.TestCase):
    def audit(self, n, pieces, support=(0,0), lower_reference=False):
        from wheat_reference_release_gate import carrier_group, assess_carriers
        def metric(rows):
            return dict(has_path=True, selected_source_bp=sum(r[4]-r[3] for r in rows),
                        slices=len(rows), source_slice_n50=100000, selected_reference_bp=100000)
        a=('asm','s','+',0,n); retained=('asm','backbone','+',0,200000)
        before=[a,retained]; after=[*pieces,retained]; m=metric(after)
        if lower_reference:m['selected_reference_bp']-=1
        group=carrier_group(before,after,metric(before),m,300000)
        def measure(base, pending, record):
            for p in pending:
                self.assertEqual((p['source'],p['interval']),(['asm','s'],[0,n]))
                def read(group, strand):
                    self.assertEqual(group,'1A'); return support['+-'.index(strand)]
                record(p,read)
        return assess_carriers(None,{'1A':group},measure=measure), group

    def test_cutoff_is_inclusive_and_no_union_or_opposite_strand_substitutes(self):
        for pieces in [[('asm','s','+',0,50000),('asm','s','+',50000,100000)],
                       [('asm','s','-',0,100000)]]:
            passed,g=self.audit(100000,pieces);self.assertFalse(passed);self.assertEqual(len(g['missing_carriers']),1)
        self.assertTrue(self.audit(100000,[('asm','s','+',0,100001)])[0])

    def test_missing_short_must_have_zero_screened_bp_on_both_strands(self):
        pieces=[('asm','new','+',0,99999)]
        passed,g=self.audit(99999,pieces);self.assertTrue(passed)
        self.assertEqual(g['short_slices'][0]['local_high_mapq_chain_bp'],{'+':0,'-':0})
        for evidence in [(1,0),(0,1)]:self.assertFalse(self.audit(99999,pieces,evidence)[0])
        self.assertFalse(self.audit(99999,pieces,lower_reference=True)[0])
        self.assertFalse(self.audit(99999,[])[0])
        self.assertTrue(self.audit(99,[('asm','s','+',0,99)])[1]['short_slices'][0]['intact'])
