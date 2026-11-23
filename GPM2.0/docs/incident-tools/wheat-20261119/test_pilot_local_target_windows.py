from pathlib import Path
import sys
import tempfile
import unittest
from collections import defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pilot_local_target_windows import fetch, add_geometry, intersection, mapper_command


class RegionalPilotTests(unittest.TestCase):
    def test_fai_reads_line_boundaries_crlf_and_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"source.fa";p.write_bytes(b">seq\r\nacgtn\r\nrYsWk\r\nmbd\r\n")
            for start in range(13):
                for end in range(start+1,14):
                    self.assertEqual(fetch(p,(13,6,5,7),start,end),b"ACGTNRYSWKMBD"[start:end])
            with self.assertRaises(ValueError):fetch(p,(13,6,5,7),0,14)

    def test_exact_coordinate_retention_rejects_other_repeat_location(self):
        for strand in ("+","-"):
            raw=f"q 500 0 200 {strand} t 500 10 210 200 200 255 cg:Z:200M".split()
            original=defaultdict(list);candidate=defaultdict(list);wrong=defaultdict(list)
            add_geometry(original,raw,"target",1000,2000,(1050,1250))
            add_geometry(candidate,raw,"target",1000,2000,(1050,1250))
            add_geometry(wrong,raw,"target",1000,2001,(1050,1250))
            self.assertEqual(sum(intersection(v,candidate.get(k,[])) for k,v in original.items()),150)
            self.assertEqual(sum(intersection(v,wrong.get(k,[])) for k,v in original.items()),0)

    def test_secondary_profile_really_removes_all_chain_flag(self):
        native=mapper_command("mapper","target","query",2)
        bounded=mapper_command("mapper","target","query",2,100)
        self.assertIn("-P",native);self.assertNotIn("-P",bounded)
        self.assertEqual(bounded[bounded.index("-p")+1],"0")
        self.assertEqual(bounded[bounded.index("-N")+1],"100")
        self.assertNotIn("-f",bounded)
        filtered=mapper_command("mapper","target","query",2,min_chain_score=2000)
        self.assertIn("-P",filtered);self.assertNotIn("-N",filtered)
        self.assertEqual(filtered[filtered.index("-m")+1],"2000")
        with self.assertRaises(ValueError):mapper_command("mapper","target","query",2,min_chain_score=0)
        with self.assertRaises(ValueError):mapper_command("mapper","target","query",2,0)


if __name__=="__main__":unittest.main()
