import hashlib
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from fork_wheat_q0 import copy_bound, draft_stage_plan, freeze, member


class IndependentForkTests(unittest.TestCase):
    def test_only_defer_raw_reference_in_draft_without_reading_its_bases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ref='data/reference/R.fa'; meta='metadata/reference.tsv'
            contents={meta:f'fasta_relpath\tfai_relpath\n{ref}\t{ref}.fai\n'.encode(), ref:b'>chr\nACGT\n',
                      ref+'.fai':b'chr\t4\t5\t4\t5\n', 'data/datasets/D.fa':b'>x\nAAA\n'}
            rows=[]
            for name, data in contents.items():
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                rows.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
            s={'files':rows,'total_bytes':sum(r['size'] for r in rows)}
            opened=[]; original=Path.open
            def guarded(p,*args,**kw):
                self.assertNotEqual(p,root/ref);opened.append(p);return original(p,*args,**kw)
            with patch.object(Path,'open',guarded): staged,deferred=draft_stage_plan(root,s)
            self.assertEqual(opened,[root/meta]);self.assertEqual({v['path'] for v in staged},set(contents)-{ref});self.assertEqual(deferred,rows[1])
            (root/meta).write_text('changed')
            with self.assertRaisesRegex(ValueError,'declaration differs'):draft_stage_plan(root,s)

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
