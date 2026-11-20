"""Resource adapter tests; synthetic output is not scientific acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import native_batch_guard as guard

HELPER = """import hashlib,json,resource,subprocess,sys
from pathlib import Path

def run_batch(path,index):
    m=json.loads(path.read_text()); b=m['batches'][index]; d=Path(b['directory'])
    if (d/'complete.json').exists():return
    d.mkdir(exist_ok=True)
    (d/'parent-limits.json').write_text(json.dumps(resource.getrlimit(resource.RLIMIT_AS)))
    subprocess.run([m['mapper_path'],'-c',str(d/'raw.paf')],check=True)
    with (d/'raw.paf').open('rb') as src,(d/'result.paf').open('wb') as out:
        subprocess.run([sys.executable,m['restore'],m['name_map']],stdin=src,stdout=out,check=True)
    (d/'stderr.log').write_text('synthetic helper success')
    names=['raw.paf','result.paf','stderr.log']
    (d/'complete.json').write_text(json.dumps({'key':b['key'],'outputs':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in names}}))
"""


class NativeGuardTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.mapper=self.root/'minimap2'
        self.mapper.write_text('#!'+sys.executable+'\nimport json,resource,sys\nfrom pathlib import Path\np=Path(sys.argv[-1]);p.write_text("raw")\np.with_name("child-limits.json").write_text(json.dumps(resource.getrlimit(resource.RLIMIT_AS)))\n')
        self.mapper.chmod(0o700)
        self.restore=self.root/'restore.py'
        self.restore.write_text('import json,resource,sys\nfrom pathlib import Path\nPath(sys.argv[1]).with_name("restore-limits.json").write_text(json.dumps(resource.getrlimit(resource.RLIMIT_AS)))\nsys.stdout.write(sys.stdin.read())\n')
        self.helper=self.root/'helper.py';self.helper.write_text(HELPER)
        self.diag=self.root/'diagnostics.py';self.diag.write_text('# verified synthetic dependency\n')
        self.names=self.root/'names';self.names.write_text('{}')
        self.batch=self.root/'batch'
        self.manifest=self.root/'manifest.json'
        self.m={'version':1,'target_lengths':{'t':4},'mapper_path':str(self.mapper),'restore':str(self.restore),'name_map':str(self.names),
                'identities':{'tool':guard.digest(self.mapper),'restore':guard.digest(self.restore)},
                'batches':[{'directory':str(self.batch),'key':'native-key','entries':[{'name':'q','length':4}]}]}
        self.manifest.write_text(json.dumps(self.m))
        record=lambda p:{'path':str(p),'sha256':guard.digest(p)}
        self.spec={'schema':guard.SCHEMA,'policy':guard.POLICY,'manifest':record(self.manifest),'batch_index':0,'native_key':'native-key',
                   'runtime':{k:record(v) for k,v in {'adapter':Path(guard.__file__).resolve(),'helper':self.helper,'mapper':self.mapper,
                                                     'restore':self.restore,'diagnostics':self.diag}.items()}}
        self.sp=self.root/'spec.json';self.save()

    def save(self):self.sp.write_text(json.dumps(self.spec))

    def run_guard(self):
        env=dict(os.environ,PATH=str(self.root)+os.pathsep+os.environ['PATH'],GPM_TASK_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable,'-B',str(Path(guard.__file__).resolve()),'--spec',str(self.sp)],env=env,text=True,capture_output=True,timeout=15)

    def test_split_limits_and_receipt_without_scientific_parameter_changes(self):
        result=self.run_guard();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads((self.batch/'parent-limits.json').read_text()),[2*guard.GIB,16*guard.GIB])
        self.assertEqual(json.loads((self.batch/'child-limits.json').read_text()),[16*guard.GIB,16*guard.GIB])
        self.assertEqual(json.loads((self.root/'restore-limits.json').read_text()),[2*guard.GIB,2*guard.GIB])
        receipt=json.loads((self.batch/guard.RECEIPT).read_text())
        self.assertEqual([x['kind'] for x in receipt['children']],['mapping','restore'])
        self.assertFalse(receipt['scientific_parameters_changed'])
        self.assertEqual(receipt['native_key'],'native-key')
        self.assertEqual(guard.digest(self.manifest),self.spec['manifest']['sha256'])

    def test_cached_batch_does_not_claim_a_new_guarded_mapper_or_replace_receipt(self):
        first=self.run_guard();self.assertEqual(first.returncode,0,first.stderr)
        before=guard.digest(self.batch/guard.RECEIPT)
        again=self.run_guard();self.assertEqual(again.returncode,0,again.stderr)
        self.assertIn('NATIVE_RESOURCE_CACHE_ONLY',again.stdout)
        self.assertEqual(guard.digest(self.batch/guard.RECEIPT),before)

    def test_changed_bound_helper_fails_before_execution(self):
        self.helper.write_text('raise RuntimeError("must not load")')
        result=self.run_guard();self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.batch.exists())

    def test_child_failure_does_not_publish_success_or_resource_receipt(self):
        self.mapper.write_text('#!'+sys.executable+'\nraise SystemExit(23)\n')
        sha=guard.digest(self.mapper);self.spec['runtime']['mapper']['sha256']=sha;self.m['identities']['tool']=sha
        self.manifest.write_text(json.dumps(self.m));self.spec['manifest']['sha256']=guard.digest(self.manifest);self.save()
        result=self.run_guard();self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.batch/'complete.json').exists());self.assertFalse((self.batch/guard.RECEIPT).exists())

    def test_fast_baseline_and_native_key_mismatch_are_rejected(self):
        self.spec['native_key']='another';self.save();self.assertNotEqual(self.run_guard().returncode,0)
        self.spec['native_key']='native-key';self.save();self.batch.mkdir();(self.batch/'self-profile-receipt.json').write_text('{}')
        self.assertNotEqual(self.run_guard().returncode,0)

    def test_oversized_query_does_not_enter_guarded_small_pool(self):
        self.m['batches'][0]['entries'][0]['length']=20_000_001
        self.manifest.write_text(json.dumps(self.m));self.spec['manifest']['sha256']=guard.digest(self.manifest);self.save()
        self.assertNotEqual(self.run_guard().returncode,0)
        self.assertFalse(self.batch.exists())

    def test_parent_limits_are_not_changed_by_scoped_child_launcher(self):
        import resource
        old=resource.getrlimit(resource.RLIMIT_AS)
        proxy=guard.ScopedSubprocess(sys.executable,self.restore,self.names)
        result=proxy.run([sys.executable,'-c','import resource;print(resource.getrlimit(resource.RLIMIT_AS))'],capture_output=True,text=True,check=True)
        self.assertIn(str((16*guard.GIB,16*guard.GIB)),result.stdout)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS),old)
        self.assertIs(guard.subprocess,subprocess)

    def test_unexpected_child_or_shell_is_rejected(self):
        proxy=guard.ScopedSubprocess(self.mapper,self.restore,self.names)
        for command,kwargs in [(['/bin/sh','-c','true'],{}),([str(self.mapper),'-c'],{'shell':True}),([str(self.mapper),'-c'],{'preexec_fn':lambda:None})]:
            with self.assertRaises(ValueError):proxy.run(command,**kwargs)

    def test_memory_reservation_covers_helper_plus_one_mapper_not_only_rss(self):
        self.assertEqual(guard.POLICY['reservation_bytes'],guard.POLICY['helper_soft_as_bytes']+guard.POLICY['mapper_as_bytes'])
        self.assertEqual(16*guard.POLICY['reservation_bytes'],288*guard.GIB)


if __name__=='__main__':unittest.main()
