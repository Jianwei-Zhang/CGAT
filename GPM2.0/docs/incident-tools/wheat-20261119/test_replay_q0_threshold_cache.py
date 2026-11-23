import hashlib
from pathlib import Path
import tempfile
import unittest
from replay_q0_threshold_cache import contexts, freeze


class MigrationReplayTests(unittest.TestCase):
    def test_choose_unique_median_and_high_completed_cases(self):
        raw=[{'raw_receipt':str(i),'paf_bytes':i} for i in range(20)]
        trace={'raw_markers':raw,'new_projects':[{'raw':str(i)} for i in range(20)]}
        self.assertEqual([r['paf_bytes'] for r,_ in contexts(trace)],[10,11,12,13,16,17,18,19])
        with self.assertRaises(ValueError):contexts({'raw_markers':raw[:6],'new_projects':trace['new_projects']})

    def test_copy_content_checked_and_non_destructive(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';dest=Path(d)/'scratch';n='grt/evidence/q0_prepare/regional/example/result.paf'
            p=src/n;p.parent.mkdir(parents=True);p.write_bytes(b'abc');row={'path':n,'size':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
            freeze(src,dest,row);freeze(src,dest,row);self.assertEqual((dest/n).read_bytes(),b'abc')
            p.write_bytes(b'abd')
            with self.assertRaisesRegex(ValueError,'bytes differ'):freeze(src,dest,row)
            self.assertEqual((dest/n).read_bytes(),b'abc')
