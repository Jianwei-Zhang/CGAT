"""Content-backed metadata tolerance and narrowly reviewed cache migration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import guided_alignment as ga
import native_first as nf
import proactive_reference_plan as pp
import proactive_resume as pr
import server_alignment as sa
import windowed_alignment as wa
import test_proactive_resume as resume_controls

LEGACY = json.loads((Path(__file__).parent / 'test_data/pre_metadata_fix_runtime.json').read_text())


class MetadataValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.fa'
        self.source.write_bytes(b'>a\nACGTACGT\n')
        wa._VERIFIED_DIGESTS.clear()

    def store(self):
        store = wa.FastaStore(self.source, self.root / 'input.bases')
        self.addCleanup(store.close)
        return store

    def chmod(self, path):
        path.chmod(0o400 if path.stat().st_mode & 0o200 else 0o600)

    def corrupt_preserving_mtime(self, path):
        before = path.stat()
        path.chmod(0o600)
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'A', b'T', 1))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    def test_ctime_source_and_spool_pass_only_after_hash_match_once(self):
        store = self.store()
        original_source = dict(store.identity)
        self.chmod(self.source)
        self.chmod(store.spool)
        with patch.object(wa, 'sha256', wraps=wa.sha256) as hashes:
            for _ in range(5):
                store.check_binding(self.source)
                self.assertTrue(store.unchanged())
            self.assertEqual(hashes.call_count, 2)
        self.assertEqual(store.identity, original_source)
        self.assertEqual(store.fetch('a', 0, 8), b'ACGTACGT')

    def test_same_size_content_mutation_with_restored_mtime_refuses(self):
        store = self.store()
        self.corrupt_preserving_mtime(self.source)
        with self.assertRaisesRegex(wa.ExperimentError, 'source identity or content'):
            store.check_binding(self.source)
        self.assertFalse(store.unchanged())

    def test_same_size_spool_mutation_with_restored_mtime_refuses(self):
        store = self.store()
        self.corrupt_preserving_mtime(store.spool)
        with self.assertRaisesRegex(wa.ExperimentError, 'private spool identity or content'):
            store.check_binding(self.source)

    def test_spool_replacement_closed_handle_and_wrong_source_still_refuse(self):
        store = self.store()
        other = self.root / 'other';other.write_bytes(b'ACGTACGT')
        with self.assertRaisesRegex(wa.ExperimentError, 'another source'):
            store.check_binding(other)
        other.replace(store.spool)
        with self.assertRaises(wa.ExperimentError):store.check_binding(self.source)
        store.close()
        with self.assertRaisesRegex(wa.ExperimentError, 'handle is closed'):
            store.check_binding(self.source)

    def test_ctime_change_without_a_recorded_digest_is_not_accepted(self):
        identity = wa.fingerprint(self.source)
        self.chmod(self.source)
        self.assertFalse(wa.identity_matches(self.source, identity))

    def test_concurrent_change_while_hashing_never_seeds_a_digest(self):
        store = self.store()
        self.chmod(self.source)
        real = wa.sha256
        def changing(path):
            digest = real(path)
            self.chmod(path)
            return digest
        with patch.object(wa, 'sha256', side_effect=changing):
            with self.assertRaisesRegex(wa.ExperimentError, 'changed while recording'):
                store.check_binding(self.source)
        self.assertTrue(store.unchanged())

    def test_catalog_and_native_boundary_allow_only_verified_ctime_changes(self):
        catalog = pp.scan_query(self.source)
        identity = nf.source_identity(self.source)
        self.chmod(self.source)
        catalog.require_unchanged()
        self.assertTrue(nf.identity_unchanged(self.source, identity))
        self.corrupt_preserving_mtime(self.source)
        with self.assertRaises(pp.PlanError):catalog.require_unchanged()
        self.assertFalse(nf.identity_unchanged(self.source, identity))

    def test_reopened_store_uses_original_content_proof_not_metadata_equality(self):
        cache = pr.Checkpoint(self.root, {'key':1})
        store = cache.store(self.source, self.root / 'bases', 'target-store')
        store.close()
        self.chmod(self.source);self.chmod(self.root / 'bases')
        with cache.store(self.source, self.root / 'bases', 'target-store').handle as handle:
            self.assertEqual(handle.read(), b'ACGTACGT')
        self.assertEqual(cache.reused['sequence_stores'], 1)
        self.corrupt_preserving_mtime(self.source)
        with self.assertRaises(wa.ExperimentError):
            cache.store(self.source, self.root / 'bases', 'target-store')

    def test_hash_memo_is_bounded_and_metadata_change_invalidates_it(self):
        self.assertEqual(wa.verified_sha256(self.source), wa.sha256(self.source))
        with patch.object(wa, '_MAX_VERIFIED_DIGESTS', 2):
            for i in range(4):
                path = self.root / str(i);path.write_bytes(str(i).encode())
                wa.verified_sha256(path)
            self.assertLessEqual(len(wa._VERIFIED_DIGESTS), 2)
        before = wa.verified_sha256(self.source)
        self.corrupt_preserving_mtime(self.source)
        self.assertNotEqual(wa.verified_sha256(self.source), before)

    def test_repeated_part_validation_hashes_bytes_once_until_metadata_changes(self):
        import minimap_index_context as mic
        from test_minimap_index_context import index_part
        path = self.root/'part.mmi'
        path.write_bytes(index_part([('chr1',8)]))
        row = mic.read_catalog(path)['parts'][0]
        context = {**row, 'path':str(path), 'sha256':wa.sha256(path),
                   'reference_sha256':'a'*64,'tool_sha256':'b'*64,'preset':'asm10','mid_occ':500}
        kwargs = dict(reference_sha256='a'*64,tool_sha256='b'*64,preset='asm10',
                      target_records={'chr1':{'length':8}})
        with patch.object(wa,'sha256',wraps=wa.sha256) as hashes:
            for _ in range(3):mic.validate_part_context(context,**kwargs)
            self.assertEqual(hashes.call_count,1)
            self.chmod(path)
            mic.validate_part_context(context,**kwargs)
            self.assertEqual(hashes.call_count,2)

    def test_part_corruption_with_restored_mtime_invalidates_the_hash_memo(self):
        import minimap_index_context as mic
        from test_minimap_index_context import index_part
        path = self.root/'part.mmi';path.write_bytes(index_part([('chr1',8)]))
        row = mic.read_catalog(path)['parts'][0]
        context = {**row,'path':str(path),'sha256':wa.sha256(path),
                   'reference_sha256':'a'*64,'tool_sha256':'b'*64,'preset':'asm10','mid_occ':500}
        kwargs = dict(reference_sha256='a'*64,tool_sha256='b'*64,preset='asm10',
                      target_records={'chr1':{'length':8}})
        mic.validate_part_context(context,**kwargs)
        before = path.stat();raw=path.read_bytes();path.write_bytes(raw[:-1]+b'X')
        os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        with self.assertRaises(mic.IndexContextError):mic.validate_part_context(context,**kwargs)


class KeyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 't.fa';self.query = self.root / 'q.fa'
        self.target.write_bytes(b'>t\nACGT\n');self.query.write_bytes(b'>q\nACGT\n')
        self.tool = self.root / 'tool';self.tool.write_bytes(b'unchanged mapper')
        self.run = self.root / 'run';self.run.mkdir()
        self.old_runtime = {'sha256':'a'*64,'files_sha256':LEGACY,
            'native_companion_sha256':'b'*64,'native_companion_platform':'linux-x86_64',
            'recovered_output_admission':sa.pub.POLICY}
        self.runtime = {**self.old_runtime,'sha256':'c'*64,
                        'files_sha256':sa.runtime_files(Path(sa.__file__).parent)}
        profile = hashlib.sha256(json.dumps(self.runtime['files_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.runtime['native_resume_source_profiles'] = [[pr._REVIEWED_LEGACY_RUNTIME,profile]]
        self.key = self.make_key(self.old_runtime['sha256'])
        self.attempt, _ = pr.select_attempt(self.run, self.key)
        (self.attempt / 'selective').mkdir()
        self.cache = pr.Checkpoint(self.attempt / 'selective', self.key)
        for n,p in [('reference',self.target),('query',self.query)]:
            self.cache.bind(n, nf.source_identity(p))
        for n in ('groups','target-store','index','ordinary'):self.cache.mark(n, {'test_only':True})
        wa.write_json(self.attempt / 'server-alignment.json', {'runtime':self.old_runtime})

    def make_key(self, runtime):
        return {'schema':1,'runtime_sha256':runtime,'threads':1,'preset':'asm10',
            'target':{'path':str(self.target),**wa.fingerprint(self.target)},
            'query':{'path':str(self.query),**wa.fingerprint(self.query)},
            'tool':nf.source_identity(self.tool)}

    def test_legacy_full_profile_is_frozen_and_matches_the_approved_digest(self):
        digest = hashlib.sha256(json.dumps(LEGACY,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest, pr._REVIEWED_LEGACY_RUNTIME)
        self.assertEqual(set(LEGACY),set(sa.RUNTIME_FILES) - {"minimap_options.py", "ordinary_partition_alignment.py"})

    def test_reviewed_runtime_and_ctime_transition_retains_old_controls(self):
        self.target.chmod(0o400);self.query.chmod(0o400)
        new = self.make_key(self.runtime['sha256'])
        attempt, reused = pr.select_attempt(self.run, new, runtime=self.runtime)
        self.assertTrue(reused);self.assertEqual(attempt,self.attempt)
        state = pr.read_json(attempt/'selective'/pr.STATE)
        self.assertEqual(state['key'],new)
        self.assertEqual(len(state['key_transitions']),1)
        self.assertEqual(len(list((attempt/'selective').glob(pr.STATE+'.previous-*'))),1)
        self.assertEqual(len(list(self.run.glob(pr.LOCATOR+'.previous-*'))),1)

    def test_previous_master_runtime_retains_verified_ordinary_and_index(self):
        files = json.loads(Path(__file__).with_name('test_data').joinpath('post_metadata_fix_runtime.json').read_text())
        self.assertEqual(hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),pr._REVIEWED_METADATA_RUNTIME)
        previous = {**self.old_runtime,'files_sha256':files}
        runtime = {**self.runtime,'native_resume_source_profiles':[[pr._REVIEWED_METADATA_RUNTIME,
            hashlib.sha256(json.dumps(self.runtime['files_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest()]]}
        wa.write_json(self.attempt/'server-alignment.json',{'runtime':previous})
        attempt,reused = pr.select_attempt(self.run,self.make_key(runtime['sha256']),runtime=runtime)
        self.assertTrue(reused);self.assertEqual(attempt,self.attempt)
        self.assertIn('ordinary',pr.read_json(attempt/'selective'/pr.STATE)['stages'])

    def test_previous_parameter_runtime_preserves_existing_native_completion(self):
        files = json.loads(Path(__file__).with_name('test_data').joinpath('pre_partition_runtime.json').read_text())
        self.assertEqual(hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),pr._REVIEWED_PARAMETER_RUNTIME)
        previous = {**self.old_runtime,'files_sha256':files}
        runtime = {**self.runtime,'native_resume_source_profiles':[[pr._REVIEWED_PARAMETER_RUNTIME,
            hashlib.sha256(json.dumps(self.runtime['files_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest()]]}
        wa.write_json(self.attempt/'server-alignment.json',{'runtime':previous})
        attempt,reused = pr.select_attempt(self.run,self.make_key(runtime['sha256']),runtime=runtime)
        self.assertTrue(reused);self.assertEqual(attempt,self.attempt)

    def test_pure_ordinary_previous_runtime_retains_native_completion_without_index(self):
        self.cache.data['stages'] = {name:self.cache.data['stages'][name] for name in ('groups','ordinary')}
        self.cache.save()
        attempt,reused = pr.select_attempt(self.run,self.make_key(self.runtime['sha256']),runtime=self.runtime)
        self.assertTrue(reused);self.assertEqual(attempt,self.attempt)

    def test_explicit_filter_is_not_migrated_from_old_default_analysis(self):
        key=self.make_key(self.runtime['sha256']);key['minimap_filter']='0.01'
        attempt,reused = pr.select_attempt(self.run,key,runtime=self.runtime)
        self.assertFalse(reused);self.assertNotEqual(attempt,self.attempt)

    def test_actual_source_mutation_fails_before_any_control_receipt_is_rekeyed(self):
        before = self.target.stat();self.target.write_bytes(b'>t\nTCGT\n')
        os.utime(self.target, ns=(before.st_atime_ns,before.st_mtime_ns))
        state = (self.attempt/'selective'/pr.STATE).read_bytes()
        with self.assertRaisesRegex(wa.ExperimentError,'original target content/identity'):
            pr.select_attempt(self.run,self.make_key(self.runtime['sha256']),runtime=self.runtime)
        self.assertEqual((self.attempt/'selective'/pr.STATE).read_bytes(),state)
        self.assertEqual(pr.read_json(self.run/pr.LOCATOR)['key'],self.key)

    def test_unknown_runtime_or_changed_mapping_code_gets_fresh_attempt(self):
        for field in ('profile','scientific_module','future_validation_module','missing_review_policy','helper','cached_long_cell'):
            runtime = {**self.runtime,'files_sha256':dict(self.runtime['files_sha256'])}
            old = {**self.old_runtime,'files_sha256':dict(LEGACY)}
            if field == 'profile':old['files_sha256']['server_alignment.py']='0'*64
            elif field == 'scientific_module':runtime['files_sha256']['native_selection.py']='0'*64
            elif field == 'future_validation_module':runtime['files_sha256']['server_alignment.py']='0'*64
            elif field == 'missing_review_policy':runtime.pop('native_resume_source_profiles')
            elif field == 'helper':runtime['native_companion_sha256']='0'*64
            else:self.cache.mark('cell:0:long',{'not_eligible':True})
            wa.write_json(self.attempt/'server-alignment.json',{'runtime':old})
            wa.write_json(self.run/pr.LOCATOR,{'schema':1,'key':self.key,'attempt':str(self.attempt)})
            attempt,reused = pr.select_attempt(self.run,self.make_key(runtime['sha256']),runtime=runtime)
            self.assertFalse(reused,field);self.assertNotEqual(attempt,self.attempt)
            self.assertTrue(self.attempt.is_dir())

    def test_transition_write_failure_restores_both_controls(self):
        state_path = self.attempt/'selective'/pr.STATE;locator = self.run/pr.LOCATOR
        state_before, locator_before = state_path.read_bytes(),locator.read_bytes()
        write = wa.write_json
        def fail_locator(path,value):
            if path == locator:raise OSError('injected locator write failure')
            return write(path,value)
        with patch.object(wa,'write_json',side_effect=fail_locator):
            with self.assertRaisesRegex(OSError,'injected'):
                pr.select_attempt(self.run,self.make_key(self.runtime['sha256']),runtime=self.runtime)
        self.assertEqual(state_path.read_bytes(),state_before)
        self.assertEqual(locator.read_bytes(),locator_before)


class RealMetadataResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resume_controls.RealResumeTests.setUpClass.__func__(cls)

    def fixture(self,root):return resume_controls.RealResumeTests.fixture(self,root)
    def controls(self):return resume_controls.RealResumeTests.controls(self)

    def run_metadata_failure(self,root,*,legacy=False):
        runtime,args = self.fixture(root)
        manifest = pr.read_json(runtime/sa.MANIFEST)
        profile = hashlib.sha256(json.dumps(manifest['files_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        manifest['native_resume_source_profiles'] = [[pr._REVIEWED_LEGACY_RUNTIME,profile]]
        wa.write_json(runtime/sa.MANIFEST,manifest)
        def fail_before_window(options,*,shared_target,shared_query):
            self.assertIsNone(options.timeout)  # Scheduler, not the diagnostic 6h default.
            args.target.chmod(0o400);args.query.chmod(0o400)
            shared_target.spool.chmod(0o400)
            raise wa.ExperimentError('injected pre-window metadata failure')
        with self.controls(),patch.object(ga,'experiment',side_effect=fail_before_window):
            with self.assertRaises(wa.ExperimentError):sa.run_reference(args,runtime_root=runtime)
        attempt = next(args.run_dir.glob('.long-cigar-attempt-*'))
        if legacy:
            previous = pr.read_json(attempt/'server-alignment.json')
            previous['runtime'].update(sha256='a'*64,files_sha256=LEGACY)
            wa.write_json(attempt/'server-alignment.json',previous)
            for path in [args.run_dir/pr.LOCATOR,attempt/'selective'/pr.STATE]:
                value = pr.read_json(path);value['key']['runtime_sha256']='a'*64;wa.write_json(path,value)
        return runtime,args,attempt

    def test_reviewed_legacy_failure_reuses_real_ordinary_result_and_index(self):
        self.resume_completed_ordinary(legacy=True)

    def test_same_runtime_ctime_failure_reuses_real_ordinary_result_and_index(self):
        self.resume_completed_ordinary(legacy=False)

    def resume_completed_ordinary(self,*,legacy):
        with tempfile.TemporaryDirectory(prefix='cgat-metadata-real-') as tmp:
            runtime,args,attempt = self.run_metadata_failure(Path(tmp),legacy=legacy)
            ordinary = attempt/'selective/ordinary-native/native.complete.paf'
            old_bytes = ordinary.read_bytes();old_mtime = ordinary.stat().st_mtime_ns
            run = wa.run_command
            def guard(command,directory,name,*a,**kw):
                if name in ('native','default-index'):
                    raise AssertionError('completed ordinary/index work was repeated')
                return run(command,directory,name,*a,**kw)
            with self.controls(),patch.object(wa,'run_command',side_effect=guard):
                result = sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(result['result_published']);self.assertTrue(result['attempt_reused'])
            self.assertEqual(result['attempt'],str(attempt))
            self.assertEqual(result['cache_reused']['ordinary_group'],1)
            self.assertEqual(result['cache_reused']['index'],1)
            self.assertEqual(ordinary.read_bytes(),old_bytes);self.assertEqual(ordinary.stat().st_mtime_ns,old_mtime)
            final = (args.run_dir/'result.paf').read_bytes()
            self.assertEqual(b''.join(row for row in final.splitlines(keepends=True) if row.startswith(b'short\t')),old_bytes)
            with self.controls(),patch.object(wa,'run_command',side_effect=AssertionError('unexpected extra mapping')):
                again = sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(again['result_published'])
            self.assertEqual((args.run_dir/'result.paf').read_bytes(),final)

    def test_live_metadata_changes_complete_without_a_failure_retry(self):
        with tempfile.TemporaryDirectory(prefix='cgat-metadata-live-') as tmp:
            root = Path(tmp)
            baseline_root = root/'baseline';baseline_root.mkdir()
            runtime,args = self.fixture(baseline_root)
            with self.controls():sa.run_reference(args,runtime_root=runtime)
            expected = (args.run_dir/'result.paf').read_bytes()
            live_root = root/'live';live_root.mkdir()
            runtime,args = self.fixture(live_root)
            execute = ga.experiment
            changed = []
            def metadata_only(options,**kwargs):
                if not changed:
                    args.target.chmod(0o400);args.query.chmod(0o400)
                    kwargs['shared_target'].spool.chmod(0o400)
                    changed.append(True)
                return execute(options,**kwargs)
            with self.controls(),patch.object(ga,'experiment',side_effect=metadata_only):
                result = sa.run_reference(args,runtime_root=runtime)
            self.assertFalse(result['attempt_reused'])
            self.assertTrue(result['result_published'])
            self.assertEqual((args.run_dir/'result.paf').read_bytes(),expected)

    def test_corrupt_completed_paf_is_refused_without_native_retry(self):
        with tempfile.TemporaryDirectory(prefix='cgat-metadata-corrupt-') as tmp:
            runtime,args,attempt = self.run_metadata_failure(Path(tmp),legacy=True)
            path = attempt/'selective/ordinary-native/native.complete.paf'
            path.write_bytes(path.read_bytes()+b'bad\n')
            with self.controls(),patch.object(wa,'run_command',side_effect=AssertionError('unexpected retry')):
                with self.assertRaises(wa.ExperimentError):sa.run_reference(args,runtime_root=runtime)
            self.assertFalse((args.run_dir/'result.paf').exists())


if __name__ == '__main__':unittest.main()
