"""Pilot plumbing tests; dummy helper is not biological/concurrency acceptance."""
import copy
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_concurrency_pilot as pilot
import self_memory_guard

HELPER = """import argparse,hashlib,json,os,resource,time
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--manifest'); p.add_argument('--batch-index'); a=p.parse_args()
assert resource.getrlimit(resource.RLIMIT_AS)==(32*1024**3,32*1024**3)
assert os.environ['GPM_TASK_THREADS']=='8'
m=json.loads(Path(a.manifest).read_text()); b=m['batches'][0]; d=Path(b['directory']); d.mkdir()
time.sleep(.2)
outputs={'raw.paf':b'raw\\n','result.paf':b'restored\\n','stderr.log':b'pilot\\n'}
for n,v in outputs.items(): (d/n).write_bytes(v)
(d/'complete.json').write_text(json.dumps({'key':b['key'],'outputs':{n:hashlib.sha256(v).hexdigest() for n,v in outputs.items()}}))
Path(m['output']).write_bytes(outputs['result.paf'])
"""


class NativePilotTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root = Path(t.name); self.work = self.root / "work"; self.work.mkdir()
        self.tool = self.root / "minimap2"; self.tool.write_text("frozen test tool")
        self.tool.chmod(0o700)
        self.helper = self.work / "helper.py"; self.helper.write_text(HELPER)
        target = self.work / "target.fa"; target.write_text(">t\nAAAA\n")
        query = self.work / "query.fa"; query.write_text(">q\nAAAA\n")
        names = self.work / "names.json"; names.write_text("{}")
        restore = self.work / "restore.py"; restore.write_text("# dummy unit fixture")
        self.cache = self.work / "cache"; self.cache.mkdir()
        for name in ("target.mmi", "index.stderr.log"): (self.cache/name).write_text(name)
        identities = {k:pilot.digest(v) for k,v in {"tool":self.tool,"target":target,"name_map":names,"restore":restore}.items()}
        cache_key = pilot.identity({"tool":identities['tool'],"target":identities['target'],"preset":"asm10","index_limit":"8G"})
        (self.cache/'complete.json').write_text(json.dumps({'key':cache_key,'outputs':{n:pilot.digest(self.cache/n) for n in ('target.mmi','index.stderr.log')}}))
        self.cases=[]
        for i in range(4):
            d=self.work/str(i); d.mkdir()
            for n,v in {'raw.paf':b'raw\n','result.paf':b'restored\n','stderr.log':b'baseline\n'}.items(): (d/n).write_bytes(v)
            key='native-'+str(i)
            (d/'complete.json').write_text(json.dumps({'key':key,'outputs':{n:pilot.digest(d/n) for n in pilot.OUTPUTS}}))
            b={'directory':str(d),'query':str(query),'query_sha256':pilot.digest(query),'key':key,
               'entries':[{'name':str(j),'length':4} for j in range(8)]}
            m={'version':1,'target':str(target),'query':str(query),'name_map':str(names),'restore':str(restore),
               'output':str(d/'original-self.paf'),'cache':str(self.cache),'identities':identities,'target_lengths':{'t':4},
               'preset':'asm10','min_chain_score':200,'minimizers':100,'batches':[b]}
            mp=d/'manifest.json'; mp.write_text(json.dumps(m))
            cmd=d/'original-command.json'; cmd.write_text(json.dumps(pilot.expected_command(m,b,self.tool)))
            self.cases.append({'manifest':pilot.record(mp),'batch_index':0,'complete_sha256':pilot.digest(d/'complete.json'),'command':pilot.record(cmd)})
        self.config=self.root/'config.json'
        self.data={'workspace':str(self.work),'runtime':{'tool':pilot.record(self.tool),'helper':pilot.record(self.helper),
                   'guard':pilot.record(Path(self_memory_guard.__file__).resolve())},'cases':self.cases}
        self.save()
        self.original={str(p):pilot.digest(p) for p in self.work.rglob('*') if p.is_file()}

    def save(self): self.config.write_text(json.dumps(self.data))

    def run_pilot(self, output=None):
        with patch('shutil.which',return_value=str(self.tool)):
            return pilot.execute(self.config,output or self.root/'output',10)

    def test_four_guarded_dummy_helpers_preserve_originals_and_compare_both_pafs(self):
        result=self.run_pilot()
        self.assertEqual(result['status'],'four_native_replays_byte_identical')
        self.assertEqual(len(result['cases']),4)
        self.assertTrue(all(all(x['identical'].values()) for x in result['cases']))
        self.assertEqual(self.original,{str(p):pilot.digest(p) for p in self.work.rglob('*') if p.is_file()})

    def test_clone_rewrites_only_writable_paths_without_mutating_source(self):
        m=json.loads(Path(self.cases[0]['manifest']['path']).read_text()); before=copy.deepcopy(m)
        cloned=pilot.isolated_manifest(m,0,self.root/'case',self.root/'index')
        self.assertEqual(m,before)
        self.assertEqual(cloned['batches'][0]['query'],m['batches'][0]['query'])
        self.assertEqual(cloned['batches'][0]['key'],m['batches'][0]['key'])
        self.assertEqual(cloned['batches'][0]['directory'],str(self.root/'case/batch'))
        self.assertEqual(cloned['output'],str(self.root/'case/isolated-self.paf'))

    def test_refuses_output_in_or_above_workspace(self):
        for out in (self.work,self.work/'child',self.root):
            with self.assertRaises(ValueError):self.run_pilot(out)

    def test_rejects_duplicate_sources(self):
        self.data['cases'][3]=self.data['cases'][0]; self.save()
        with self.assertRaises(ValueError):self.run_pilot()

    def test_rejects_source_change(self):
        (self.work/'0/raw.paf').write_text('tampered')
        with self.assertRaises(ValueError):self.run_pilot()
        self.assertFalse((self.root/'output/pilot.json').exists())

    def test_rejects_fast_baseline(self):
        (self.work/'0/self-profile-receipt.json').write_text('{}')
        with self.assertRaises(ValueError):self.run_pilot()

    def test_rejects_changed_scientific_or_thread_parameters(self):
        p=Path(self.cases[0]['command']['path']); cmd=json.loads(p.read_text());cmd[cmd.index('-t')+1]='4'
        p.write_text(json.dumps(cmd));self.cases[0]['command']=pilot.record(p);self.save()
        with self.assertRaises(ValueError):self.run_pilot()

    def test_cpu_budget_and_each_grant_are_bounded(self):
        for budget, grant in ((16,8),(33,8),(32,9),(32,True),(0,1)):
            self.data['cpu_budget']=budget
            self.cases[0]['threads']=grant
            self.save()
            with self.assertRaises(ValueError): self.run_pilot()

    def test_extra_lanes_require_the_split_limit_adapter(self):
        self.data['lanes']=8; self.save()
        with self.assertRaises(ValueError): self.run_pilot()
        self.data['lanes']=17; self.save()
        with self.assertRaises(ValueError): self.run_pilot()

    def test_single_record_replay_requires_one_thread_not_eight(self):
        m=json.loads(Path(self.cases[0]['manifest']['path']).read_text())
        b=m['batches'][0]; b['entries']=[{'name':'q','length':4}]
        pilot.check_bounds(m,b,threads=1)
        with self.assertRaises(ValueError): pilot.check_bounds(m,b,threads=8)

    def test_thread_change_requires_explicit_opt_in_and_split_guard(self):
        self.cases[0].update(threads=2,baseline_threads=8);self.save()
        with self.assertRaisesRegex(ValueError,"rebudgeting"):self.run_pilot()
        self.data['allow_thread_rebudget']=True;self.save()
        with self.assertRaisesRegex(ValueError,"rebudgeting"):self.run_pilot()

    def test_invalid_baseline_thread_grant_is_rejected(self):
        self.cases[0]['baseline_threads']=True;self.save()
        with self.assertRaisesRegex(ValueError,"baseline thread"):self.run_pilot()

    def test_opt_in_rebudget_binds_original_command_and_both_outputs(self):
        import native_batch_guard
        self.tool.write_text('#!'+sys.executable+'\nimport resource,sys\nassert resource.getrlimit(resource.RLIMIT_AS)==(16*1024**3,)*2\nassert sys.argv[sys.argv.index("-t")+1]=="2"\nsys.stdout.write("raw\\n")\n')
        self.tool.chmod(0o700)
        restore=self.work/'restore.py'
        restore.write_text('import sys\nsys.stdout.write(sys.stdin.read().replace("raw","restored"))\n')
        self.helper.write_text("""import hashlib,json,os,resource,shutil,subprocess,sys
from pathlib import Path
def run_batch(path,index):
    assert resource.getrlimit(resource.RLIMIT_AS)==(2*1024**3,16*1024**3)
    m=json.loads(path.read_text());b=m['batches'][index];d=Path(b['directory']);d.mkdir()
    command=[shutil.which('minimap2'),'-c','-x',m['preset'],'-X','--no-hash-name',
        '-m',str(m['min_chain_score']),'-n',str(m['minimizers']),'-t',os.environ['GPM_TASK_THREADS'],
        str(Path(m['cache'])/'target.mmi'),b['query']]
    with (d/'raw.paf').open('wb') as out:subprocess.run(command,stdout=out,check=True)
    with (d/'raw.paf').open('rb') as src,(d/'result.paf').open('wb') as out:
        subprocess.run([sys.executable,m['restore'],m['name_map']],stdin=src,stdout=out,check=True)
    (d/'stderr.log').write_text('dummy rebudget success')
    outputs={n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in ('raw.paf','result.paf','stderr.log')}
    (d/'complete.json').write_text(json.dumps({'key':b['key'],'outputs':outputs}))
    Path(m['output']).write_bytes((d/'result.paf').read_bytes())
""")
        diag=self.root/'diagnostics.py';diag.write_text('# synthetic diagnostics\n')
        self.data['runtime'].update(tool=pilot.record(self.tool),helper=pilot.record(self.helper),
            native_adapter=pilot.record(Path(native_batch_guard.__file__).resolve()),minimap_diagnostics=pilot.record(diag))
        for case in self.cases:
            mp=Path(case['manifest']['path']);m=json.loads(mp.read_text())
            m['identities'].update(tool=pilot.digest(self.tool),restore=pilot.digest(restore))
            mp.write_text(json.dumps(m));case['manifest']=pilot.record(mp)
            case.update(threads=2,baseline_threads=8)
        cm=self.cache/'complete.json';value=json.loads(cm.read_text())
        value['key']=pilot.identity({'tool':pilot.digest(self.tool),'target':m['identities']['target'],'preset':'asm10','index_limit':'8G'})
        cm.write_text(json.dumps(value))
        self.data.update(allow_thread_rebudget=True,cpu_budget=8);self.save()
        before={str(p):pilot.digest(p) for p in self.work.rglob('*') if p.is_file()}
        with patch.dict(os.environ,PATH=str(self.root)+os.pathsep+os.environ['PATH']):result=self.run_pilot()
        self.assertEqual(result['implementation'],pilot.record(Path(pilot.__file__).resolve()))
        self.assertTrue(result['thread_counts_changed'])
        self.assertEqual(result['baseline_thread_grants'],[8]*4)
        self.assertEqual(result['thread_grants'],[2]*4)
        self.assertTrue(all(all(c['identical'].values()) for c in result['cases']))
        self.assertEqual(before,{str(p):pilot.digest(p) for p in self.work.rglob('*') if p.is_file()})

    def test_rejects_wrong_native_key(self):
        p=self.work/'0/complete.json'; d=json.loads(p.read_text());d['key']='approximate';p.write_text(json.dumps(d))
        self.cases[0]['complete_sha256']=pilot.digest(p);self.save()
        with self.assertRaises(ValueError):self.run_pilot()

    def test_failure_never_publishes_pilot_success(self):
        self.helper.write_text('raise SystemExit(7)\n');self.data['runtime']['helper']=pilot.record(self.helper);self.save()
        with self.assertRaises(RuntimeError):self.run_pilot()
        self.assertFalse((self.root/'output/pilot.json').exists())

    def test_rejects_out_of_envelope_and_underthreaded_batch(self):
        m=json.loads(Path(self.cases[0]['manifest']['path']).read_text()); b=m['batches'][0]
        m['target_lengths']={'t':1_000_000_001}
        with self.assertRaises(ValueError):pilot.check_bounds(m,b)
        m['target_lengths']={'t':4};b['entries'][0]['length']=20_000_000
        with self.assertRaises(ValueError):pilot.check_bounds(m,b)
        b['entries']=[{'name':'q','length':4}]
        with self.assertRaises(ValueError):pilot.check_bounds(m,b)


if __name__=='__main__':unittest.main()
