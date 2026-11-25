from io import BytesIO
import unittest
from pilot_exact_group_windows import window_dna


class Windows(unittest.TestCase):
    def test_exact_half_open_fai_offsets_across_lf_crlf_and_final_short_line(self):
        for eol in (b"\n",b"\r\n"):
            parts=[b"acgT",b"ttAg",b"a"]; seq=b"".join(parts).decode().upper(); raw=b">s"+eol+eol.join(parts)+eol
            for a in range(len(seq)):
                for b in range(a+1,len(seq)+1):
                    self.assertEqual(window_dna(BytesIO(raw),(len(seq),2+len(eol),4,4+len(eol)),dict(start=a,end=b,segment_length=len(seq))),seq[a:b])
    def test_bad_fai_or_truncated_fasta_rejected(self):
        for n,body in [(4,b"ACGT"),(5,b"AC")]:
            with self.assertRaises(ValueError):window_dna(BytesIO(body),(n,0,4,5),dict(start=0,end=5,segment_length=5))
