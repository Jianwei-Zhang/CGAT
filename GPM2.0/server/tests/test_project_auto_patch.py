import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from project_auto_patch import INDEX, RECEIPT, publish_auto_patch, validate_auto_patch
from refinement_bundle_fixture import create
from refinement_bundle_validate import validate_payload
from refinement_commit import PublicationError, targets
from refinement_reports import build_tool_report
from refinement_batch import publish_batch
from lgz_final import publish_baseline
from run_all_runner import WorkspaceLock
from workspace_layout import WorkspaceLayout


@unittest.skipUnless(all(shutil.which(t) for t in ('samtools','minimap2','zip')), 'real closure indexing and delivery required')
class AutoVersionPatchTests(unittest.TestCase):
    def test_project_pair_replaces_baseline_generation_once_and_preserves_direct_results(self):
        from job_final_catalog import publish_catalog
        from project_delivery_publish import publish_current
        from run_orchestration import sha256_file
        from refinement_compact_plan import build_plan
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / 'job'
            result, _, _ = create(root, with_source_evidence=True, job_outputs=True,
                                  project_delivery=True, sequence='GTTTAC')
            layout = WorkspaceLayout.detect(root)
            # Fixed minimal public report for this archive/layout test, not visual acceptance.
            report = layout.path('report'); report.mkdir(parents=True, exist_ok=True)
            for name, value in [('manifest.json', '{}'), ('report.html', '<html></html>'), ('render_report.py', '# fixture')]:
                (report / name).write_text(value)
            lock = WorkspaceLock(root, 'controlled-project-pair'); lock.acquire()
            try:
                publish_baseline(root, lock)
                publish_catalog(root, lock, '1' * 32, {})
                publish_current(root, lock)
                delivery = root / '07_delivery'
                def digests():
                    return {f.name: sha256_file(f) for f in delivery.iterdir() if f.is_file()}
                before = digests()
                self.assertEqual(set(before), {'job.full.zip', 'job.light.zip'})
                baseline = sha256_file(root / '05_final/job.lgz.fa')
                tool = 'degap'
                batch = {'batch_id': '2' * 32, 'status': 'staged', 'exit_code': 0, 'tools': {
                    tool: {'status':'staged', 'run_id':result['run_id'], 'report':build_tool_report(root, result)}}}
                completed = publish_batch(root, lock, {'batch':batch, 'staged_results':{tool:result}, 'exit_code':0})
                self.assertEqual(completed['exit_code'], 0, batch)
                publish_catalog(root, lock, batch['batch_id'], batch['tools'])
                publish_current(root, lock)
                after = digests()
                self.assertEqual(set(after), set(before) | {'job.auto.patch.zip'})
                self.assertTrue(all(after[k] != v for k,v in before.items()))
                self.assertEqual(sha256_file(root / '05_final/job.lgz.fa'), baseline)
                self.assertNotEqual(sha256_file(root / '05_final/job.degap.fa'), baseline)
                publish_current(root, lock)
                self.assertEqual(digests(), after)
                # No native producer exists in this controlled fixture. Planning must still
                # resolve published measurement inputs after staging cleanup, and never unlink.
                self.assertEqual(build_plan(root, lock, {tool})['files'], [])
            finally:
                lock.release()

    def test_latest_patch_contains_both_independent_views_and_no_parent_fastas(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)/'col0'
            first, _, _ = create(root, with_source_evidence=True, job_outputs=True)
            lock = WorkspaceLock(root, 'automatic-patch-test')
            lock.acquire()
            self.addCleanup(lock.release)
            layout = WorkspaceLayout.detect(root)
            publish_baseline(root, lock)
            target = root/'07_delivery/col0.auto.patch.zip'
            self.assertIsNone(publish_auto_patch(root,lock))
            self.assertFalse(target.exists())
            for tool in ('degap','tgsgapcloser'):
                result = first if tool=='degap' else create(root,with_source_evidence=True,tool=tool,reuse_workspace=True)[0]
                batch = {'batch_id': ('1' if tool=='degap' else '2')*32,'status':'staged','exit_code':0,
                         'tools':{tool:{'status':'staged','run_id':result['run_id'],'report':build_tool_report(root,result)}}}
                outcome = publish_batch(root,lock,{'batch':batch,'staged_results':{tool:result},'exit_code':0})
                self.assertEqual(outcome['exit_code'],0,outcome)
                sha = publish_auto_patch(root,lock)
                validate_auto_patch(layout,sha)
                if tool == 'degap':
                    with zipfile.ZipFile(target) as archive:
                        self.assertEqual(set(json.loads(archive.read(INDEX))['variants']),{'degap'})
            stat = target.stat()
            with mock.patch('project_auto_patch._build', side_effect=AssertionError('unnecessary rebuild')):
                self.assertEqual(publish_auto_patch(root,lock),sha)
            self.assertEqual((stat.st_ino,stat.st_mtime_ns),(target.stat().st_ino,target.stat().st_mtime_ns))
            with zipfile.ZipFile(target) as archive:
                index = json.loads(archive.read(INDEX))
                self.assertEqual(set(index['variants']),{'degap','tgsgapcloser'})
                all_objects = set(archive.namelist()) - {INDEX}
                self.assertTrue(all(n.startswith('objects/') and hashlib.sha256(archive.read(n)).hexdigest()==n[8:] for n in all_objects))
                used = {index['baseline_app_path'], index['baseline']['final_path_sha256']}
                self.assertIn('chromosomes',json.loads(archive.read('objects/'+index['baseline_app_path'])))
                for tool,variant in index['variants'].items():
                    raw = archive.read('objects/'+variant['light_manifest']); lm=json.loads(raw)
                    self.assertEqual(lm['baseline'], index['baseline'])
                    light = Path(scratch)/('decoded-'+tool)
                    for name, digest in lm['files'].items():
                        f=light/name; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(archive.read('objects/'+digest))
                    (light/'metadata/refinement/manifest.json').write_bytes(raw)
                    self.assertEqual(validate_payload(light, full=False)['tool'], tool)
                    used.update(lm['files'].values()); used.add(variant['light_manifest']); used.update(variant['accepted_sequence_objects'])
                    self.assertEqual(len(variant['accepted_sequence_objects']),1)
                    self.assertEqual(archive.read('objects/'+variant['accepted_sequence_objects'][0]), b'>fixture-edit\nGTNNAC\n')
                    with (targets(layout,tool)['final']/'sources.tsv').open() as data:
                        for row in csv.DictReader(data,delimiter='\t'):
                            if row['origin']=='lgz': self.assertNotIn('objects/'+row['fasta_sha256'],all_objects)
                    final = targets(layout,tool)['final']/'assembly.fa'
                    self.assertNotIn('objects/'+hashlib.sha256(final.read_bytes()).hexdigest(),all_objects)
                self.assertEqual(all_objects,{'objects/'+s for s in used})
            # Even byte-identical output is not adopted without its ownership record.
            owner = layout.path(RECEIPT); original = owner.read_bytes(); owner.unlink()
            with self.assertRaisesRegex(PublicationError,'unowned or modified'): publish_auto_patch(root,lock)
            owner.write_bytes(original)
            target.write_bytes(b'user file')
            with self.assertRaisesRegex(PublicationError,'unowned or modified'): publish_auto_patch(root,lock)
            self.assertEqual(target.read_bytes(),b'user file')
