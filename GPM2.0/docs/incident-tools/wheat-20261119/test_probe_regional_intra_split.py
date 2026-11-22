from pathlib import Path
import tempfile
import unittest

from probe_regional_intra_split import BASE, build_command, combine, split_fasta


class IntraSplitTests(unittest.TestCase):
    def test_same_records_and_order_in_both_scopes(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=[Path(d)/n for n in ('original.fa','inside.fa','between.fa')]
            a.write_bytes(b'>i1\nAC\n>c1\nG\n>i2\nCT\nT\n')
            split_fasta(a,b,c,{'i1':True,'i2':True,'c1':False},{'i1':2,'i2':3,'c1':1})
            self.assertEqual(b.read_bytes(),b'>i1\nAC\n>i2\nCT\nT\n')
            self.assertEqual(c.read_bytes(),b'>c1\nG\n')

    def test_cross_never_gets_cap_and_collision_refuses(self):
        a=['/tool','-c','-x','asm10',*BASE,'-m','2000','-t','2','old','query']
        self.assertEqual(build_command(a,'/tool','other','query','cross'),[*a[:-2],'other','query'])
        self.assertEqual(build_command(a,'/tool','intra','query','intra_cap'),[*a[:-2],'--cap-sw-mem','30m','intra','query'])
        with self.assertRaises(ValueError):build_command(a,'/tool','cross','query','both_cap')
        with self.assertRaises(ValueError):combine({'target':1},{'target':2})

    def test_incomplete_fasta_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=[Path(d)/n for n in ('original.fa','inside.fa','between.fa')]
            a.write_bytes(b'>i1\nA\n>c1\nC\n>i1\nG\n')
            with self.assertRaises(ValueError):split_fasta(a,b,c,{'i1':True,'c1':False},{'i1':1,'c1':1})


if __name__=='__main__':unittest.main()
