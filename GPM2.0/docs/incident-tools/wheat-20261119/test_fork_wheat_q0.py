import hashlib
import io
import json
import os
import random
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from fork_wheat_q0 import copy_bound, draft_stage_plan, draft_thread_options, freeze, member, sha, stage_and_draft, write


class IndependentForkTests(unittest.TestCase):
    def test_existing_run_budget_explicit_ceiling_and_frozen_reader(self):
        def legacy(): pass
        def current(*, threads=1): pass
        with patch.dict(os.environ, clear=True), patch('os.sched_getaffinity', return_value=set(range(8))):
            self.assertEqual(draft_thread_options(legacy), {})
            self.assertEqual(draft_thread_options(current, 32), {'threads': 8})
            os.environ['GPM_RUN_THREADS'] = '6'
            self.assertEqual(draft_thread_options(current), {'threads': 6})
            self.assertEqual(draft_thread_options(current, 4), {'threads': 4})
            self.assertEqual(draft_thread_options(legacy, 1), {})
            with self.assertRaisesRegex(ValueError, 'frozen threshold runtime'):
                draft_thread_options(legacy)
            with self.assertRaisesRegex(ValueError, 'positive'):
                draft_thread_options(current, 0)

    def test_staged_fork_delivers_budget_to_real_selector_without_changing_request(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = base/'source'; rng = random.Random(11)
            data = {'metadata/datasets.tsv': 'dataset_name\tfasta_relpath\nA\tdata/datasets/A.fa\nB\tdata/datasets/B.fa\n',
                    'metadata/reference.tsv': 'fasta_relpath\tfai_relpath\ndata/reference/R.fa\tdata/reference/R.fa.fai\n',
                    'metadata/chr_assignments.tsv': 'dataset_name\tseq_name\tassigned_chr_name\tseq_length_bp\nA\tx\tr1\t600\nB\ty\tr2\t600\n'}
            ref = ''
            for ds, name, chrom in [('A','x','r1'), ('B','y','r2')]:
                seq = ''.join(rng.choices('ACGT',k=600)); ref += f'>{chrom}\n{seq}\n'
                data[f'data/datasets/{ds}.fa'] = f'>{name}\n{seq}\n'
                data[f'runs/{ds}_vs_ref/result.paf'] = f'{name}\t600\t0\t600\t+\t{chrom}\t600\t0\t600\t600\t600\t60\tcg:Z:600M\n'
            data.update({'data/reference/R.fa':ref, 'data/reference/R.fa.fai':'r1\t600\t4\t600\t601\nr2\t600\t609\t600\t601\n'})
            rows = []
            for name, text in data.items():
                path = source/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(text.encode())
                rows.append({'path':name, 'size':len(text), 'sha256':sha(text.encode())})
            receipts = []
            for n in (1,4):
                ctrl = base/f'control-{n}'; prod=ctrl/'producer'; prod.mkdir(parents=True)
                for name in ['reader.json','plan.tsv']: (prod/name).write_bytes(b'fixture')
                snap = {'source':str(source), 'files':rows, 'total_bytes':sum(r['size'] for r in rows), 'source_run':'fixture',
                        'revision':'fixture', 'profile':'positive_threshold','producer_checkpoints':[], 'producer_reader_sha256':sha(b'fixture'),
                        'source_plan_sha256':sha(b'fixture'), 'alignments':[]}
                write(ctrl/'snapshot.json',snap); digest = sha((ctrl/'snapshot.json').read_bytes()); log = io.StringIO()
                with (tempfile.TemporaryDirectory(prefix='cgat-wheat-fork-test-', dir='/tmp') as scratch, redirect_stdout(log),
                      patch.dict(os.environ, {'GPM_RUN_THREADS':str(n)}), patch('os.sched_getaffinity', return_value=set(range(8))),
                      patch('shutil.disk_usage', return_value=SimpleNamespace(free=73*1024**3))):
                    root=Path(scratch); root.rmdir()  # entry point requires an unused private name
                    stage_and_draft(ctrl,digest,root,128)
                self.assertEqual(json.loads((ctrl/'started.json').read_text())['thread_budget'], n)
                if n == 4: self.assertIn('cpu_budget=4 lanes=1', log.getvalue())
                receipts.append(json.loads((ctrl/'global-first-request.json').read_text()))
            self.assertEqual(receipts[0],receipts[1]); self.assertTrue(receipts[0]['has_path'])
            self.assertEqual(receipts[0]['mapper_calls'], 0)

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
