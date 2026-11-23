import hashlib
from pathlib import Path
import tempfile
import unittest

from fork_wheat_q0 import copy_bound, freeze, member


class IndependentForkTests(unittest.TestCase):
    def test_no_alias_to_the_running_workspace_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); src=root/'old'; new=root/'new'; src.mkdir(); new.mkdir()
            (src/'done').write_bytes(b'complete')
            (new/'alias').symlink_to(src,target_is_directory=True)
            for rel in ('../old/done','alias/done','/tmp/a'):
                with self.assertRaises(ValueError):member(new,rel)
            row={'size':8,'sha256':hashlib.sha256(b'complete').hexdigest(),'path':'done'}
            copy_bound(src/'done',new/'done',row)
            self.assertNotEqual((src/'done').stat().st_ino,(new/'done').stat().st_ino)
            with self.assertRaises(ValueError):copy_bound(src/'done',new/'done',row)
            self.assertEqual((src/'done').read_bytes(),b'complete')

    def test_bad_source_hash_does_not_publish_completed_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            r=Path(directory);p=r/'source';dest=r/'fork/input';p.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'SHA mismatch'):
                copy_bound(p,dest,{'size':3,'sha256':hashlib.sha256(b'old').hexdigest(),'path':'input'})
            self.assertFalse(dest.exists());self.assertEqual(p.read_bytes(),b'new')

    def test_freeze_refuses_source_with_unconfirmed_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            r=Path(directory);source=r/'source';lock=source/'.run_all/lock';lock.mkdir(parents=True)
            (lock/'owner.json').write_text('{"run_id":"other"}');out=r/'control'
            with self.assertRaisesRegex(ValueError,'producer generation'):
                freeze(source,r/'log','expected',out,'a'*40)
            self.assertFalse(out.exists())
