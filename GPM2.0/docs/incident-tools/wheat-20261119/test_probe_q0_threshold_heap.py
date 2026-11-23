import tempfile
from pathlib import Path
import unittest

from probe_q0_threshold_heap import arm, lines, slabs


class HeapDiagnosticTests(unittest.TestCase):
    def test_disjoint_cap_and_ends(self):
        for n in range(0,150):
            spans=slabs(n,width=8)
            if n:
                self.assertEqual(spans[0][0],0);self.assertEqual(sum(spans[-1]),n)
            self.assertLessEqual(sum(w for _,w in spans),32)
            self.assertTrue(all(p+w<=q for (p,w),(q,v) in zip(spans,spans[1:])))

    def test_partial_lines_never_used(self):
        self.assertEqual(list(lines(b'junk\r\na\nlast',aligned=False,at_end=False)),[b'a\n'])
        self.assertEqual(list(lines(b'part',aligned=False,at_end=True)),[])
        self.assertEqual(list(lines(b'a\r\nb',aligned=True,at_end=True)),[b'a\r\n',b'b'])

    def test_real_parser_counts_and_rejects_wrong_lengths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); record=b'q\t5\t0\t5\t+\tq\t5\t0\t5\t5\t5\t60\tcg:Z:5M\n';(root/'x').write_bytes(record)
            args=('self',root,[('self','D','D','x')],{'D':{'q':5}})
            r=arm(args);self.assertEqual(r['totals'],{'records':1,'same_source_records':1,'cigar_ops':1,'parsed_bytes':len(record),'sample_bytes':len(record)})
            with self.assertRaisesRegex(ValueError,'lengths differ'):arm((*args[:3],{'D':{'q':6}}))
