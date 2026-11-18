"""Resume statistics reuse is content-bound, not a replacement for validation."""
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_orchestration as contract
import server_report_collect as collect
import server_report_io as report_io
from server_report import fresh_directory

class ResumeReportCacheTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fasta = self.root / 'input.fa'
        self.fasta.write_bytes(b'>a\nAA' + b'N' * 100 + b'CC\n>b\nACGT\n')
        contract._SHA256_CACHE.clear()

    def cache(self):
        return next((self.root / '.run_all/report-statistics').glob('*.json'))

    def bump_ctime(self, previous):
        deadline = time.monotonic() + 3
        while self.fasta.stat().st_ctime_ns == previous and time.monotonic() < deadline:
            time.sleep(0.02)
            self.fasta.chmod(self.fasta.stat().st_mode ^ stat.S_IXUSR)
        self.assertNotEqual(self.fasta.stat().st_ctime_ns, previous)

    def test_statistics_survive_report_rotation_but_new_process_reads_content(self):
        fresh_directory(self.root)
        first = collect.sequence_stats(self.root, self.fasta)
        report_io.write_json(self.root / 'report/manifest.json', {'run_id': 'first'})
        fresh_directory(self.root)
        contract._SHA256_CACHE.clear()
        with patch.object(collect, 'fasta_stats', side_effect=AssertionError('unchanged input reparsed')), patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            second = collect.sequence_stats(self.root, self.fasta)
        self.assertEqual(first, second)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(len(list((self.root / '.report_history').glob('first-*'))), 1)

    def test_legacy_cache_is_adopted_from_history_only_after_content_check(self):
        fresh_directory(self.root)
        value = report_io.fasta_stats(self.fasta)
        st = self.fasta.stat()
        key = hashlib.sha256(f'input.fa:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}'.encode()).hexdigest()
        legacy = self.root / 'report/statistics' / (key + '.json')
        report_io.write_json(legacy, value)
        original = legacy.read_bytes()
        fresh_directory(self.root)
        contract._SHA256_CACHE.clear()
        with patch.object(collect, 'fasta_stats', side_effect=AssertionError('legacy source rescanned')), patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            self.assertEqual(collect.sequence_stats(self.root, self.fasta), value)
        self.assertEqual(reads.call_count, 1)
        archived = next((self.root / '.report_history').glob('*/statistics/*.json'))
        self.assertEqual(archived.read_bytes(), original)
        self.assertTrue(self.cache().is_file())

    def test_bad_legacy_statistics_or_new_algorithm_are_not_adopted(self):
        for invalid in ('counts', 'algorithm'):
            with self.subTest(invalid=invalid):
                root = self.root / invalid
                root.mkdir()
                fasta = root / 'input.fa'
                fasta.write_bytes(self.fasta.read_bytes())
                value = report_io.fasta_stats(fasta)
                st = fasta.stat()
                key = hashlib.sha256(f'input.fa:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}'.encode()).hexdigest()
                if invalid == 'counts':
                    value['length_bp'] += 1
                report_io.write_json(root / 'report/statistics' / (key + '.json'), value)
                algorithm = 'future-contract' if invalid == 'algorithm' else collect.STATISTICS_ALGORITHM
                with patch.object(collect, 'STATISTICS_ALGORITHM', algorithm), patch.object(collect, 'fasta_stats', wraps=collect.fasta_stats) as parse:
                    result = collect.sequence_stats(root, fasta)
                self.assertEqual(parse.call_count, 1)
                self.assertEqual(result['length_bp'], 108)

    def test_metadata_only_change_rehashes_without_recomputing_statistics(self):
        before = collect.sequence_stats(self.root, self.fasta)
        st = self.fasta.stat()
        os.utime(self.fasta, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000))
        self.bump_ctime(st.st_ctime_ns)
        with patch.object(collect, 'fasta_stats', side_effect=AssertionError('content-equal source reparsed')), patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            self.assertEqual(collect.sequence_stats(self.root, self.fasta), before)
        self.assertEqual(reads.call_count, 1)

    def test_changed_bytes_with_restored_size_and_mtime_invalidate_both_caches(self):
        first = collect.sequence_stats(self.root, self.fasta)
        st = self.fasta.stat()
        self.fasta.write_bytes(self.fasta.read_bytes().replace(b'N', b'A'))
        os.utime(self.fasta, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.bump_ctime(st.st_ctime_ns)
        with patch.object(collect, 'fasta_stats', wraps=collect.fasta_stats) as parse:
            second = collect.sequence_stats(self.root, self.fasta)
        self.assertEqual(parse.call_count, 1)
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertEqual(second['gap_count'], 0)
        self.assertEqual(first['length_bp'], second['length_bp'])

    def test_bad_checksum_schema_or_algorithm_is_only_a_cache_miss(self):
        expected = collect.sequence_stats(self.root, self.fasta)
        cache = self.cache()
        original = cache.read_bytes()
        for kind in ('json', 'checksum', 'schema', 'algorithm', 'source'):
            with self.subTest(kind=kind):
                value = json.loads(original)
                if kind == 'checksum':
                    value['stats']['n_bp'] += 1
                if kind == 'schema':
                    value['schema'] = 999
                if kind == 'algorithm':
                    value['algorithm'] = 'different-algorithm'
                if kind == 'source':
                    value['source']['sha256'] = '0' * 64
                cache.write_bytes(b'{' if kind == 'json' else json.dumps(value).encode())
                with patch.object(collect, 'fasta_stats', wraps=collect.fasta_stats) as parse:
                    self.assertEqual(collect.sequence_stats(self.root, self.fasta), expected)
                self.assertEqual(parse.call_count, 1)

    def test_changing_source_during_statistics_does_not_publish_cache(self):
        real = collect.fasta_stats

        def changing(path):
            value = real(path)
            path.write_bytes(path.read_bytes() + b'A\n')
            return value
        with patch.object(collect, 'fasta_stats', side_effect=changing), self.assertRaisesRegex(ValueError, 'changed'):
            collect.sequence_stats(self.root, self.fasta)
        self.assertEqual(list((self.root / '.run_all/report-statistics').glob('*.json')), [])

    def test_report_and_checkpoint_share_one_real_hash_read(self):
        with patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            identity = contract.file_identity(self.fasta)
            self.assertEqual(report_io.digest(self.fasta), identity['sha256'])
            self.assertEqual(collect.sequence_stats(self.root, self.fasta)['sha256'], identity['sha256'])
        self.assertEqual(reads.call_count, 1)

    def test_checkpoint_sweep_keeps_hashes_after_hundreds_of_batch_files(self):
        # A chromosome-batched workspace exceeds the historical 256-entry memo.
        # Each phase must still stat every file, but unchanged bytes need one read.
        paths = [self.fasta]
        for i in range(600):
            path = self.root / f'batch-{i:04d}.sh'
            path.write_text(f'echo {i}\n')
            paths.append(path)
        with patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            first = [contract.file_identity(path) for path in paths]
            second = [contract.file_identity(path) for path in paths]
        self.assertEqual(first, second)
        self.assertEqual(reads.call_count, len(paths))
        self.assertLessEqual(len(contract._SHA256_CACHE), contract._SHA256_CACHE_LIMIT)

    def test_replacement_inode_and_bounded_hash_memo(self):
        first = contract.sha256_file(self.fasta)
        st = self.fasta.stat()
        replacement = self.root / 'replacement'
        replacement.write_bytes(self.fasta.read_bytes())
        os.utime(replacement, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(replacement, self.fasta)
        with patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
            self.assertEqual(contract.sha256_file(self.fasta), first)
        self.assertEqual(reads.call_count, 1)
        with patch.object(contract, '_SHA256_CACHE_LIMIT', 3):
            for i in range(5):
                p = self.root / str(i)
                p.write_text(str(i))
                contract.sha256_file(p)
            self.assertLessEqual(len(contract._SHA256_CACHE), 3)
            with patch.object(contract, '_sha256_read', wraps=contract._sha256_read) as reads:
                self.assertEqual(contract.sha256_file(self.root / '0'), hashlib.sha256(b'0').hexdigest())
            self.assertEqual(reads.call_count, 1)  # Evicted entries retain the full-read fallback.

    def test_shared_hash_memo_is_safe_for_concurrent_readers(self):
        from concurrent.futures import ThreadPoolExecutor
        expected = hashlib.sha256(self.fasta.read_bytes()).hexdigest()
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(contract.sha256_file, [self.fasta] * 40))
        self.assertEqual(values, [expected] * 40)

    def test_missing_or_non_regular_identity_keeps_contract_error(self):
        for path in (self.root / 'missing', self.root):
            with self.subTest(path=path), self.assertRaises(contract.OrchestrationContractError):
                contract.file_identity(path)

    def test_persistent_cache_cannot_escape_workspace_through_parent_link(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / '.run_all').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                collect.sequence_stats(self.root, self.fasta)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_hash_race_is_refused_and_not_memoized(self):
        real = contract._sha256_read

        def changed(signature):
            value = real(signature)
            self.fasta.write_bytes(b'>changed\nA\n')
            return value
        with patch.object(contract, '_sha256_read', side_effect=changed), self.assertRaisesRegex(ValueError, 'changed'):
            contract.sha256_file(self.fasta)
        self.assertEqual(len(contract._SHA256_CACHE), 0)
if __name__ == '__main__':
    unittest.main()
