from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from measure_local_target_scope import project


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


if __name__=="__main__":unittest.main()
