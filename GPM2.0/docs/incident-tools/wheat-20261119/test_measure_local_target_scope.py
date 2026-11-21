from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from measure_local_target_scope import project, require_residual_core, collect_nearest, flank_search_regions


class ProjectionTests(unittest.TestCase):
    def test_plus_minus_partial_overlap_and_roundtrip(self):
        block=(100,200,1000,1100)
        self.assertEqual(project(block,"+",120,140,True),[1020,1040])
        self.assertEqual(project(block,"-",120,140,True),[1060,1080])
        for strand in ("+","-"):
            for start in range(80,220,7):
                region=project(block,strand,start,start+23,True)
                if region:
                    self.assertEqual(project(block,strand,*region),[max(start,100),min(start+23,200)])
        self.assertIsNone(project(block,"+",1100,1200))
        self.assertIsNone(project(block,"-",0,100,True))

    def test_residual_core_must_fit_one_hole_not_its_hull(self):
        rows=[{"dataset":"a","contig":"q","uncovered":[[100,300],[400,600]]}]
        require_residual_core(rows,"a","q",100,300)
        for start,end in [(0,100),(250,450),(300,400),(100,601)]:
            with self.assertRaises(ValueError):require_residual_core(rows,"a","q",start,end)
        with self.assertRaises(ValueError):require_residual_core(rows,"b","q",100,200)

    def test_nearest_flanks_keep_ties_and_do_not_bridge_discordant_loci(self):
        flanks={};query=(500,600)
        collect_nearest(flanks,"chr","+",(100,200,1000,1100),query,1000,10)
        collect_nearest(flanks,"chr","+",(300,400,1200,1300),query,1000,10)
        collect_nearest(flanks,"chr","+",(300,400,999000,999100),query,1000,10)
        collect_nearest(flanks,"chr","+",(700,800,1600,1700),query,1000,10)
        self.assertEqual(flanks["chr","+","left"],(100,{(1290,1300),(999090,999100)}))
        regions,good,bad=flank_search_regions(flanks,100,1000)
        self.assertEqual((good,bad),(1,1))
        self.assertIn((1290,1610),regions["chr"])
        self.assertNotIn((1600,999100),regions["chr"])


if __name__=="__main__":unittest.main()
