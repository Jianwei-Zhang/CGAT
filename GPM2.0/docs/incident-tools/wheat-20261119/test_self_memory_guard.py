import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import self_memory_guard as guard


@unittest.skipUnless(sys.platform.startswith('linux'),'requires Linux resource enforcement')
class GuardTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.script=self.root/'script.sh'

    def run_guard(self,body,*,limit=128*1024**2,sha=None,script=None):
        self.script.write_text('#!/bin/bash\nset -eu\n'+body+'\n')
        return subprocess.run([sys.executable,str(Path(guard.__file__).resolve()),'--script',str(script or self.script),
            '--sha256',sha or hashlib.sha256(self.script.read_bytes()).hexdigest(),'--limit-bytes',str(limit)],
            text=True,capture_output=True,timeout=15)

    def test_child_inherits_hard_and_soft_limit_across_exec(self):
        result=self.run_guard(f"{sys.executable} -c 'import resource; print(resource.getrlimit(resource.RLIMIT_AS))'")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str((128*1024**2,128*1024**2)),result.stdout)
        self.assertIn('SELF_RESOURCE_GUARD',result.stdout)

    def test_large_allocation_fails_inside_small_test_limit_not_host_oom(self):
        body=f'''{sys.executable} - <<'END'
import sys
try: bytearray(512*1024**2)
except MemoryError:
    print('EXPECTED_MEMORY_LIMIT')
    sys.exit(73)
sys.exit(0)
END'''
        result=self.run_guard(body)
        self.assertEqual(result.returncode,73,result.stderr)
        self.assertIn('EXPECTED_MEMORY_LIMIT',result.stdout)

    def test_bad_hash_does_not_execute_script(self):
        result=self.run_guard('echo SHOULD_NOT_RUN',sha='0'*64)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SHOULD_NOT_RUN',result.stdout)

    def test_link_and_invalid_limits_rejected(self):
        link=self.root/'link';link.symlink_to(self.script)
        result=self.run_guard('echo SHOULD_NOT_RUN',script=link)
        self.assertNotEqual(result.returncode,0)
        for limit in (0,-1,guard.MAX_LIMIT_BYTES+1):
            result=self.run_guard('echo SHOULD_NOT_RUN',limit=limit)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('SHOULD_NOT_RUN',result.stdout)

if __name__=='__main__':unittest.main()
