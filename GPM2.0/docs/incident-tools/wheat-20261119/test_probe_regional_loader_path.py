import os
from pathlib import Path
import unittest

from probe_regional_loader_path import MUMMER_PATH, candidate_envs, loader_dependencies


class LoaderPathTests(unittest.TestCase):
    def test_only_child_library_path_can_change(self):
        orig={'LD_LIBRARY_PATH':f'{MUMMER_PATH}:/opt/lib','PATH':'/bin','OTHER':'kept'}
        clear,prune=candidate_envs(orig)
        self.assertEqual(clear[1],{'PATH':'/bin','OTHER':'kept'})
        self.assertEqual(prune[1],{'LD_LIBRARY_PATH':'/opt/lib','PATH':'/bin','OTHER':'kept'})
        self.assertEqual(orig['LD_LIBRARY_PATH'],f'{MUMMER_PATH}:/opt/lib')

    def test_noop_has_no_candidate(self):
        self.assertEqual(candidate_envs({'PATH':'/bin'}),[])

    def test_loader_addresses_not_identity(self):
        path=Path('/bin/bash');self.assertTrue(path.is_file())
        output=lambda ptr:f'linux-vdso.so.1 ({ptr})\nlib.so => {path} ({ptr})\n{path} ({ptr})'
        self.assertEqual(loader_dependencies(output('0x001')),loader_dependencies(output('0xffe')))
        self.assertEqual(loader_dependencies(output('0x001'))['lib.so'],os.path.realpath(path))

    def test_missing_and_ambiguous_libraries_are_rejected(self):
        for line in ('libx => not found','libx => relative (0x2)','libx => /bin/bash\nlibx => /bin/bash',''):
            with self.subTest(line=line),self.assertRaises(ValueError):loader_dependencies(line)


if __name__=='__main__':unittest.main()
