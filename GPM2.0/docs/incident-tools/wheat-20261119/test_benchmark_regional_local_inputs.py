import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

from benchmark_regional_local_inputs import run_arm, stage_inputs, stamp
from benchmark_regional_thread_split import Case, Stage


class LocalInputsTests(unittest.TestCase):
    def test_stage_exact_bytes_and_refuse_changed_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'query.fa'
            source.write_bytes(b'>query\r\nACGT\r\n')
            signatures = {source:stamp(source)}
            digests = {source:hashlib.sha256(source.read_bytes()).hexdigest()}
            before = root/'before'; before.mkdir()
            copy, = stage_inputs((source,), before, signatures, digests)
            self.assertEqual(copy.read_bytes(), source.read_bytes())
            source.write_bytes(b'>query\r\nAGGT\r\n')
            after = root/'after'; after.mkdir()
            # Some shared filesystems return unchanged cached metadata after a
            # same-size edit. Simulate that explicitly; the content must fail.
            signatures[source] = stamp(source)
            with self.assertRaisesRegex(ValueError, 'input changed'):
                stage_inputs((source,), after, signatures, digests)

    def test_both_arms_bind_both_full_stdouts(self):
        guard = Path(__file__).resolve().parents[3]/'server/tools/lgz_core/q0_mapper_guard.py'
        if not guard.is_file():
            guard = Path(os.environ.get('TEST_GPM_TOOLS','not-configured'))/'lgz_core/q0_mapper_guard.py'
        if not guard.is_file():
            self.fail('guard required for native arm test')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = (root/'target.fa',root/'query.fa')
            payloads = (b'>t\nAAC\n', b'>q\nCGT\n')
            for p, data in zip(inputs,payloads):
                p.write_bytes(data)
            signatures = {p:stamp(p) for p in inputs}
            digests = {p:hashlib.sha256(data).hexdigest() for p,data in zip(inputs,payloads)}
            program = 'import pathlib,sys; sys.stdout.buffer.write(b"".join(pathlib.Path(p).read_bytes() for p in sys.argv[1:]))'
            argv = (sys.executable,'-c',program,*map(str,inputs))
            good = hashlib.sha256(b''.join(payloads)).hexdigest()
            c = Case('control',0.0,(Stage('chaining',(argv,argv),good), Stage('precise',(argv,argv),good)))
            a = run_arm(root/'shared', (c,), signatures, digests, guard)
            b = run_arm(root/'local', (c,), signatures, digests, guard, scratch=root)
            for arm in (a,b):
                self.assertEqual([x['sha256'] for x in arm['cases'][0]['stages']], [good, good])
                self.assertEqual(arm['cases'][0]['input_bytes'], len(b''.join(payloads)))
            self.assertFalse(list(root.glob('window-*')))
            bad = Case('bad',0.0,(c.stages[0],Stage('precise',(argv,argv),'wrong')))
            with self.assertRaisesRegex(ValueError, 'precise.*full PAF differs'):
                run_arm(root/'bad', (bad,), signatures, digests, guard, scratch=root)
            self.assertEqual((root/'bad/0/precise.paf').read_bytes(), b''.join(payloads))


if __name__ == '__main__':
    unittest.main()
