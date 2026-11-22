from pathlib import Path
import hashlib
import os
import sys
import tempfile
import unittest

from benchmark_regional_thread_split import BASE, Case, GIB, GUARD_SHA, Stage, checked_argv, run_phase


class ThreadSplitTests(unittest.TestCase):
    def test_only_threads_and_archived_paths_change(self):
        prefix = ['/mapper', '-x', 'asm10', '-c', *BASE, '-m', '2000', '-t']
        flags = ['-c', *BASE, '-m', '2000']
        command = {'argv': [*prefix, '2', '/original/target.fa', '/original/query.fa'],
                   'address_space_bytes': 4*GIB, 'guard_sha256': GUARD_SHA, 'wall_clock_limit_added': False}
        args = ('/mapper', 'asm10', flags, ['/original/target.fa', '/original/query.fa'],
                ['/archive/target.fa', '/archive/query.fa'])
        self.assertEqual(checked_argv(command, *args, 1), (*prefix, '1', '/archive/target.fa', '/archive/query.fa'))
        self.assertEqual(checked_argv(command, *args, 2), (*prefix, '2', '/archive/target.fa', '/archive/query.fa'))
        for bad in ({**command, 'address_space_bytes': 16*GIB},
                    {**command, 'argv': [*command['argv'][:-2], 'other.fa', 'contigs.fa']},
                    {**command, 'wall_clock_limit_added': True}):
            with self.assertRaises(ValueError):
                checked_argv(bad, *args, 1)
        with self.assertRaises(ValueError):
            checked_argv(command, *args, 3)

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX exec')
    def test_phase_rejects_altered_stdout_and_retains_pair(self):
        guard = Path(__file__).resolve().parents[3] / 'server/tools/lgz_core/q0_mapper_guard.py'
        if not guard.is_file():
            guard = Path(os.environ.get('TEST_GPM_TOOLS', 'not-configured'))/'lgz_core/q0_mapper_guard.py'
        if not guard.is_file():
            self.skipTest('requires actual mapper guard')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = hashlib.sha256(b'preserved\n').hexdigest()
            original = (sys.executable, '-c', 'print("preserved")')
            changed = (sys.executable, '-c', 'print("changed")')
            stage = Stage('chaining', (original, original), expected)
            cases = [Case('first', 0.7, (stage, Stage('precise', (original, original), expected)))]
            result = run_phase(root/'good', cases, guard, 1, 1)
            self.assertEqual([x['sha256'] for x in result['rows'][0][1]], [expected, expected])
            cases = [Case('first', 0.7, (stage, Stage('precise', (changed, original), expected)))]
            with self.assertRaisesRegex(ValueError, 'full PAF differs'):
                run_phase(root/'bad', cases, guard, 1, 1)
            self.assertEqual((root/'bad/0/precise.paf').read_bytes(), b'changed\n')


if __name__ == '__main__':
    unittest.main()
