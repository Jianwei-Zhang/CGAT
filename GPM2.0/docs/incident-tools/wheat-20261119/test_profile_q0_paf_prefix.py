import tempfile
from pathlib import Path
import unittest

from profile_q0_paf_prefix import consume_prefix
from lgz_core.q0_alignments import parse_paf_line

ROW = "q\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\tcg:Z:10M"


class PrefixProfileTests(unittest.TestCase):
    def run_prefix(self, text, *, records=10, byte_limit=4096, line_limit=1024, qlen=10):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"input.paf";path.write_bytes(text.encode())
            hits=[]
            report=consume_prefix(path,parse_paf_line,{"q":qlen},{"t":10},hits.append,
                artifact="stable/result.paf",max_records=records,max_bytes=byte_limit,max_line_bytes=line_limit)
            return report,hits

    def test_real_resource_dependency_is_loaded(self):
        import run_resources
        from lgz_core import stage_cache
        self.assertTrue(Path(run_resources.__file__).is_file())
        self.assertIs(stage_cache.execution_threads,run_resources.execution_threads)

    def test_record_limit_does_not_validate_tail(self):
        r,hits=self.run_prefix(ROW+"\nnot valid\n",records=1)
        self.assertEqual((r["records"],r["stop_reason"]),(1,"record_limit"))
        self.assertFalse(r["whole_cache_validated"])
        self.assertEqual(hits[0].artifact,"stable/result.paf")

    def test_blank_comment_newlines_preserve_real_line_numbers(self):
        r,hits=self.run_prefix("#comment\r\n\r"+ROW+"\r\n"+ROW+"\r")
        self.assertEqual([h.line_number for h in hits],[3,4])
        self.assertEqual(r["stop_reason"],"eof")
        self.assertFalse(r["whole_cache_validated"])

    def test_byte_cap_never_parses_partial_row(self):
        r,hits=self.run_prefix(ROW+"\n"+ROW+"\n",byte_limit=len(ROW)+3,line_limit=len(ROW)+3)
        self.assertEqual(r["records"],1)
        self.assertEqual(r["processed_bytes"],len(ROW)+1)
        self.assertEqual(r["stop_reason"],"byte_limit_before_record")

    def test_line_cap_never_parses_truncated_cigar(self):
        r,hits=self.run_prefix(ROW+"\n",line_limit=8)
        self.assertEqual((r["records"],len(hits)),(0,0))
        self.assertEqual(r["stop_reason"],"line_limit_before_record")

    def test_malformed_consumed_record_fails(self):
        with self.assertRaises(ValueError):self.run_prefix("not a PAF\n")
        with self.assertRaises(ValueError):self.run_prefix(ROW+"\n",qlen=9)

    def test_invalid_unbounded_limits_rejected(self):
        for kw in ({"records":0},{"records":20_001},{"byte_limit":64*1024**2+1}):
            with self.assertRaises(ValueError):self.run_prefix(ROW,**kw)

    def test_unterminated_last_line_is_valid_prefix_not_cache_proof(self):
        r,hits=self.run_prefix(ROW)
        self.assertEqual(r["records"],1)
        self.assertEqual(r["processed_bytes"],len(ROW))
        self.assertFalse(r["whole_cache_validated"])


if __name__=="__main__":unittest.main()
