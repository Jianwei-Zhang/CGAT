from pathlib import Path
import unittest

from probe_regional_index_reuse import reuse_commands


class TestIndexReuse(unittest.TestCase):
    def setUp(self):
        shared=['-x','asm10','-D','-P','--dual=yes','--no-long-join']
        self.coarse=['tool',*shared,'-t','2','T','Q']
        self.exact=['tool','-c',*shared,'-m','2000','-t','2','T','Q']

    def test_keeps_archived_options_and_expected_stdout(self):
        a,b=reuse_commands([('coarse',self.coarse,'a'),('exact',self.exact,'b')],Path('/tmp/I'))
        self.assertEqual(a,('coarse',[*self.coarse[:-2],'-d','/tmp/I','T','Q'],'a'))
        self.assertEqual(b,('exact',[*self.exact[:-2],'/tmp/I','Q'],'b'))
        self.assertEqual(self.coarse[-2:],['T','Q'])

    def test_rejects_different_target_and_nonstandard_preset(self):
        with self.assertRaises(ValueError):
            reuse_commands([('coarse',self.coarse,'a'),('exact',[*self.exact[:-2],'other','Q'],'b')],Path('/tmp/I'))
        with self.assertRaises(ValueError):
            reuse_commands([('coarse',self.coarse,'a'),('exact',[*self.exact[:-2],'-f','.01','T','Q'],'b')],Path('/tmp/I'))
