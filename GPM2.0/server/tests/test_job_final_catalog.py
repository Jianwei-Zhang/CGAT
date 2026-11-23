"""On-disk publication/ownership tests for new jobs, not a simulation of tool accuracy."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from job_final_catalog import publish_catalog, record_early_failure, validate_catalog
from lgz_final import publish_baseline
from post_lgz_refinement import validate_completion
from refinement_batch import publish_batch
from refinement_bundle_fixture import FIXTURE, create
from refinement_commit import PublicationError
from refinement_reports import build_tool_report
from run_all_runner import WorkspaceLock
from run_orchestration import sha256_file
from workspace_layout import LayoutError, MANIFEST, WorkspaceLayout, initialize_workspace


class JobResultsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'col0'

    def lock(self):
        lock = WorkspaceLock(self.root, 'catalog-test')
        lock.acquire()
        self.addCleanup(lock.release)
        return lock

    def rows(self):
        with (self.root / '05_final/results.tsv').open(newline='') as stream:
            return {row['version']: row for row in csv.DictReader(stream, delimiter='\t')}

    def test_prefix_survives_move_legacy_layout_unchanged_and_malformed_marker_rejected(self):
        old = self.root.with_name('existing')
        self.assertIsNone(initialize_workspace(old).result_prefix)
        self.assertEqual(WorkspaceLayout.detect(old).relative('05_final/00_lgz'), '05_final/00_lgz')
        layout = initialize_workspace(self.root, job_outputs=True)
        self.assertEqual(layout.relative('05_final/00_lgz/assembly.fa'), '05_final/details/00_lgz/assembly.fa')
        moved = self.root.with_name('elsewhere')
        self.root.rename(moved)
        self.assertEqual(WorkspaceLayout.detect(moved).result_prefix, 'col0')
        for prefix in (None, '../bad', 'a/b', '', False, 'test\n'):
            (moved / MANIFEST).write_text(json.dumps({**layout.manifest(), 'result_prefix': prefix}))
            with self.assertRaises(LayoutError):
                WorkspaceLayout.detect(moved)

    def test_failed_before_baseline_records_status_but_no_fake_fasta(self):
        layout = initialize_workspace(self.root, job_outputs=True)
        lock = self.lock()
        self.assertEqual(record_early_failure(self.root, lock, 'first', 7), 7)
        self.assertEqual(self.rows()['lgz']['attempt_status'], 'failed_before_publication')
        self.assertEqual(self.rows()['lgz']['fasta'], '')
        self.assertEqual(list(layout.path('05_final').glob('*.fa')), [])
        tsv = layout.path('05_final/results.tsv')
        tsv.write_text('customer content')
        with self.assertRaisesRegex(PublicationError, 'unowned or modified'):
            record_early_failure(self.root, lock, 'second', 7)
        self.assertEqual(tsv.read_text(), 'customer content')

    @unittest.skipUnless(shutil.which('samtools'), 'real source indexing required')
    def test_public_worker_commits_a_direct_baseline_and_validates_catalog_on_resume(self):
        layout = initialize_workspace(self.root, job_outputs=True)
        for logical, contents in json.loads(FIXTURE.read_text())['files'].items():
            target = layout.path(logical)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
        layout.path('metadata/prepare_options.tsv').write_text('key\tvalue\nthreads\t1\n')
        run = subprocess.run([sys.executable, '-B', str(TOOLS/'post_lgz_refinement.py'), '--server-dir', str(self.root)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
        public = self.root / '05_final/col0.lgz.fa'
        self.assertIn(str(public), run.stdout)
        self.assertTrue(public.samefile(self.root/'05_final/details/00_lgz/assembly.fa'))
        self.assertFalse((self.root/'05_final/00_lgz').exists())
        row = self.rows()['lgz']
        self.assertEqual(row['fasta'],public.name)
        self.assertEqual(row['sha256'],sha256_file(public))
        self.assertTrue(validate_completion(self.root,row['attempt'])[0])
        tsv = layout.path('05_final/results.tsv')
        contents = tsv.read_bytes()
        tsv.write_text('wrong')
        self.assertFalse(validate_completion(self.root,row['attempt'])[0])
        tsv.write_bytes(contents)
        self.assertTrue(validate_completion(self.root,row['attempt'])[0])
        public.unlink()
        public.write_text('user file')
        self.assertFalse(validate_completion(self.root,row['attempt'])[0])
        with self.assertRaisesRegex(PublicationError, 'unowned or modified'):
            publish_catalog(self.root, self.lock(), 'next', {})
        self.assertEqual(public.read_text(),'user file')

    @unittest.skipUnless(all(shutil.which(tool) for tool in ('samtools','minimap2','zip')), 'indexing and delivery tools required')
    def test_real_tool_publication_and_later_failed_attempt_keep_distinct_identities(self):
        result, _, _ = create(self.root, with_source_evidence=True, job_outputs=True)
        lock = self.lock()
        publish_baseline(self.root, lock)
        report = build_tool_report(self.root, result)
        batch = {'batch_id':'b'*32,'status':'staged','exit_code':0,'tools':{'degap':{'status':'staged','run_id':result['run_id'],'report':report}}}
        outcome = publish_batch(self.root, lock, {'batch':batch,'staged_results':{'degap':result},'exit_code':0})
        self.assertEqual(outcome['exit_code'],0,outcome)
        layout = WorkspaceLayout.detect(self.root)
        # Interruption after installing the first FASTA but before committing the name.
        from job_final_catalog import durable_json
        def interrupt(path, value):
            if path.name == 'col0.lgz.fa.json' and 'previous' not in value:
                raise OSError('simulated interruption')
            durable_json(path,value)
        with mock.patch('job_final_catalog.durable_json',side_effect=interrupt), self.assertRaisesRegex(OSError,'interruption'):
            publish_catalog(self.root,lock,'one',batch['tools'])
        digest = publish_catalog(self.root,lock,'one',batch['tools'])
        validate_catalog(layout,digest)
        first = self.rows()['degap']
        self.assertEqual(first['publication'],batch['tools']['degap']['publication_transaction'])
        public = self.root/'05_final'/first['fasta']
        self.assertTrue(public.samefile(layout.path('05_final/01_degap/assembly.fa')))
        self.assertEqual(first['sha256'],sha256_file(Path(result['staging'])/'assembly.fa'))
        self.assertEqual(int(first['accepted_edits']),result['provenance']['accepted_edit_count'])
        publish_catalog(self.root,lock,'two',{'degap':{'status':'failed'},'quartet':{'status':'failed'}})
        rows = self.rows()
        self.assertEqual((rows['degap']['attempt'],rows['degap']['attempt_status']),('two','failed'))
        self.assertEqual(rows['degap']['publication'], first['publication'])
        self.assertEqual(rows['degap']['sha256'], first['sha256'])
        self.assertEqual(rows['quartet']['fasta'],'')
        self.assertFalse((self.root/'05_final/col0.quartet.fa').exists())
