from pathlib import Path
import shutil
import tempfile
import unittest

from probe_regional_guard_startup import LIMIT, argv_for, run_one, validate_child


class GuardStartupTests(unittest.TestCase):
    def test_all_variants_keep_byte_exact_hard_and_soft_cap(self):
        guard=Path('/shared/guard.py'); local=Path('/tmp/guard.py')
        self.assertEqual(argv_for('current',guard,local,'/python','/prlimit')[1:5],
                         [str(guard),'--address-space-bytes',str(LIMIT),'--'])
        self.assertEqual(argv_for('no_site',guard,local,'/python','/prlimit')[1:3],['-S',str(guard)])
        self.assertEqual(argv_for('local_guard',guard,local,'/python','/prlimit')[1],str(local))
        self.assertEqual(argv_for('prlimit',guard,local,'/python','/prlimit')[1],f'--as={LIMIT}:{LIMIT}')

    def test_missing_limit_or_changed_group_fails_closed(self):
        expected=LIMIT//1024
        validate_child(f'3\n4\n{expected}\n{expected}\n',3,4)
        for value in (f'5\n4\n{expected}\n{expected}',f'3\n6\n{expected}\n{expected}',f'3\n4\n1\n{expected}'):
            with self.assertRaises(ValueError): validate_child(value,3,4)

    def test_real_launches_keep_pid_group_and_bounds(self):
        guard=Path(__file__).resolve().parents[3]/'server/tools/lgz_core/q0_mapper_guard.py'
        if not guard.is_file():
            self.skipTest('repository guard is not included in this isolated test packet')
        modes=['current','no_site','local_guard']+(['prlimit'] if shutil.which('prlimit') else [])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); local=root/'local';local.mkdir()
            for i,m in enumerate(modes):
                result=run_one(root,local,guard,m,i,Path(shutil.which('prlimit') or '/missing'))
                self.assertGreater(result['total_seconds'],0)


if __name__=='__main__': unittest.main()
