import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

import audit_wheat_pair_capacity as stride
import measure_wheat_window_witnesses as broad
from lgz_core.common import stable_id


class InputAndWitnessTests(unittest.TestCase):
    def test_stride_fasta_rejects_duplicate_or_unbound_bytes(self):
        self.assertEqual(stride.fasta(b'>a\nAC\nGT\n>b\nTTA\n'), {'a':b'ACGT','b':b'TTA'})
        for raw in (b'',b'ATG',b'>a\nA\n>a\nT\n',b'>a\n>b\nG\n'):
            with self.assertRaises(ValueError): stride.fasta(raw)
        with TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'f').write_bytes(b'abc'); h=hashlib.sha256(b'abc').hexdigest()
            self.assertEqual(stride.checked(p,'f',h,3),b'abc')
            for args in [('f',h,2),('f','x',3),('../other',h,3)]:
                with self.assertRaises(ValueError): stride.checked(p,*args)

    def test_no_unbound_or_repeated_core_projection_may_substitute_for_another_window(self):
        raw=[{'raw_receipt':'r'}]; item={'project':'p','raw':'r'}
        for projects in ([],[item,item],[{'project':'p','raw':'s'}]):
            with self.assertRaises(ValueError): broad.join_trace({'raw_markers':raw,'new_projects':projects})
        self.assertEqual(broad.join_trace({'raw_markers':raw,'new_projects':[item]}),[(raw[0],item)])
        with TemporaryDirectory() as tmp:
            root=Path(tmp); r={'raw_receipt':'r','raw_receipt_sha256':'raw-hash'}
            spec={'query':{'cores':[[0,100]]},'raw_receipt':{'path':'r','sha256':'raw-hash'}}
            name=stable_id('q0-regional-project',spec); (root/name).mkdir(); rel=name+'/success.json'; (root/rel).write_text(json.dumps({'spec':spec,'status':'success'}))
            self.assertEqual(broad.verify_project(root,r,{'project':rel,'query':spec['query']}),spec)
            with self.assertRaises(ValueError): broad.verify_project(root,r,{'project':rel,'query':{'cores':[[10,100]]}})

    def test_first_witness_cannot_be_just_short_high_identity_or_long_low_identity(self):
        short=Row(matches=99,block_length=100,cigar=((99,'='),(1,'X')))
        low=Row(matches=94,block_length=100,cigar=((100,'M'),))
        yes=Row(matches=95,block_length=100,cigar=((100,'M'),))
        for rows,expected in (([],'no_projected_rows'),([short,low],'only_subthreshold_projection'),
                              ([short,low,yes],'has_threshold_witness')):
            with patch.object(broad,'projected',return_value=rows):
                self.assertEqual(broad.witness(None,None,None,None),expected)
