from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from calibrate_wheat_index_parts import target_groups, reference_blocks
from trial_wheat_native_index_parts import stage


class NativePartsTest(unittest.TestCase):
    def setUp(self):
        d=TemporaryDirectory();self.addCleanup(d.cleanup);self.root=Path(d.name)
        self.lookup={k:dict(length=len(v),sequence_sha256=sha256(v).hexdigest()) for k,v in [('a',b'ATG'),('z',b'CC')]}
        self.bounds=[dict(targets=1,bases=n) for n in [3,2]]; self.groups=target_groups(self.lookup,self.bounds)
        self.paf=self.root/'ref';self.row=lambda k,n:f'a\t3\t0\t2\t+\t{k}\t{n}\t0\t2\t2\t2\t60\n'.encode()
    def test_exact_native_order_and_query_bytes(self):
        original=self.root/'full';original.write_bytes(b'>a\nAT\nG\n>z\nCC\n'); shards=[self.root/'one',self.root/'two']; q=self.root/'q'
        stage(original,shards,q,self.groups,{'z'},self.lookup)
        self.assertEqual(b''.join(f.read_bytes() for f in shards),original.read_bytes());self.assertEqual(q.read_bytes(),b'>z\nCC\n')
        lines=[self.row('a',3),self.row('z',2)]; data=b''.join(lines);self.paf.write_bytes(data)
        blocks=reference_blocks(self.paf,self.lookup,self.groups,{'a'},{'paf_sha256':sha256(data).hexdigest(),'bytes':len(data)})
        self.assertEqual([b['paf_sha256'] for b in blocks],[sha256(v).hexdigest() for v in lines])
    def test_reject_reordered_even_with_matching_checksum(self):
        data=self.row('z',2)+self.row('a',3);self.paf.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'order'):reference_blocks(self.paf,self.lookup,self.groups,{'a'},{'paf_sha256':sha256(data).hexdigest(),'bytes':len(data)})
    def test_reject_omitted_or_changed_partition(self):
        for bad in [self.bounds[:1],[dict(targets=1,bases=2),self.bounds[1]]]:
            with self.assertRaises(ValueError):target_groups(self.lookup,bad)
    def test_reject_sequence_change_with_same_length(self):
        f=self.root/'full';f.write_bytes(b'>a\nATC\n>z\nCC\n')
        with self.assertRaisesRegex(ValueError,'DNA'):stage(f,[self.root/'s1',self.root/'s2'],self.root/'q',self.groups,{'a'},self.lookup)
