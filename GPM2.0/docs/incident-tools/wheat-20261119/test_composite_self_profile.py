import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import test_self_seed_profile as fixtures
import self_seed_profile as primary_runtime
import extended_self_seed_profile as extension_runtime
import composite_self_profile as composite


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.fx = f = fixtures.SelfSeedProfileTests()
        f.setUp(); self.addCleanup(f.doCleanups)
        tiny = patch.dict(extension_runtime.POLICY, minimum_query_bases=1)
        tiny.start(); self.addCleanup(tiny.stop)
        text = ('#!/usr/bin/env python3\nimport sys\n'
                'q="q3b" if "batch-00001" in sys.argv[-1] else "q1b"\n'
                'n=3 if q=="q3b" else 12\n'
                'print(f"{q}\\t{n}\\t0\\t{n}\\t+\\tq2a\\t12\\t0\\t{n}\\t{n}\\t{n}\\t60\\tcg:Z:{n}M")\n'
                'sys.stderr.write("[M::worker_pipeline::0] mapped 1 sequences\\n[M::main] Real time: 0.1 sec\\n")\n')
        f.tool.write_text(text)
        restore = Path(f.native['restore'])
        restore.write_text("import sys\nsys.stdout.write(sys.stdin.read().replace('q1b','ctg1').replace('q2a','ctg2').replace('q3b','ctg3'))\n")
        f.native['identities']['tool'] = primary_runtime.pilot.digest(f.tool)
        f.native['identities']['restore'] = primary_runtime.pilot.digest(restore)
        f.source.write_text(json.dumps(f.native))
        f.spec['policy']['seed_fraction'] = '0.005'
        f.spec['native_manifest'] = f.row(f.source)
        f.path.write_text(json.dumps(f.spec))
        f.profile = primary_runtime.Profile(f.path)
        f.profile.helper.publish(f.cache, primary_runtime.index_key(f.native), ('target.mmi','index.stderr.log'))
        f.run_profile()
        self.before = {name: (f.directory/name).read_bytes() for name in (*primary_runtime.OUTPUTS, primary_runtime.RECEIPT, 'complete.json')}
        spec = copy.deepcopy(f.spec)
        spec.update(schema=extension_runtime.SCHEMA, policy=copy.deepcopy(extension_runtime.POLICY), selected_batches=[1])
        spec['dependencies']['runtime'] = f.row(Path(extension_runtime.__file__))
        self.extension_path = f.root/'extension.json'; self.extension_path.write_text(json.dumps(spec))
        self.extension = extension_runtime.Profile(self.extension_path)
        self.spec = {'schema':composite.SCHEMA, 'workspace':str(f.work),
            'native_manifest':f.row(f.source), 'primary_profile':f.row(f.path),
            'extension_profile':f.row(self.extension_path), 'runtime':f.row(Path(composite.__file__))}
        self.path = f.root/'composite.json'; self.write()

    def write(self):
        self.path.write_text(json.dumps(self.spec))

    def test_preserves_completed_primary_bytes_keys_and_combines_new_result(self):
        f = self.fx; profile = composite.Profile(self.path)
        self.assertEqual(profile.manifest['batches'][0], f.profile.manifest['batches'][0])
        self.assertEqual(profile.selected, [0,1]); self.assertTrue(profile.validate_batch(0))
        self.assertFalse(profile.merge())
        extension_runtime.run_batch(self.extension, 1)
        self.assertTrue(profile.validate_batch(1)); self.assertTrue(profile.merge())
        self.assertEqual(self.before, {name:(f.directory/name).read_bytes() for name in self.before})
        self.assertIn('ctg1', Path(f.native['output']).read_text())
        self.assertIn('ctg3', Path(f.native['output']).read_text())
        self.assertNotEqual(profile.manifest['batches'][1]['key'], f.native['batches'][1]['key'])
        self.assertEqual(profile.owner(0).sha, f.profile.sha)
        self.assertEqual(profile.owner(1).sha, self.extension.sha)

    def test_complete_isolated_full_candidate_is_adopted_without_any_child(self):
        f=self.fx; candidate=f.root/'candidate';candidate.mkdir()
        raw="q3b\t3\t0\t3\t+\tq2a\t12\t0\t3\t3\t3\t60\tcg:Z:3M\n"
        for name,text in [('raw.paf',raw),('result.paf',raw.replace('q3b','ctg3').replace('q2a','ctg2')),
                ('stderr.log','[M::worker_pipeline::0] mapped 1 sequences\n[M::main] Real time: 0.1 sec\n'),
                ('restore.stderr.log','')]:
            (candidate/name).write_text(text)
        batch=f.native['batches'][1]
        command=extension_runtime.mapping_command(f.native,batch,f.tool,f.index,extension_runtime.POLICY)
        native=command[:-4]+command[-2:]
        paths=[Path(batch['query']),f.tool,f.index,Path(f.native['name_map']),Path(f.native['restore'])]
        report={'scope':'one_complete_self_query_candidate_only','status':'candidate_complete_not_compared_not_adopted',
            'candidate_adopted':False,'analysis_workspace_modified':False,'mapping':{'returncode':0,'wall_seconds':0.1},
            'driver_sha256':extension_runtime.pilot.digest(Path(extension_runtime.pilot.__file__)),
            'native_batch_key':batch['key'],'native_command':native,'command':command,
            'inputs':extension_runtime.pilot.identities(paths),
            'outputs':extension_runtime.pilot.identities([candidate/name for name in (*extension_runtime.OUTPUTS,'restore.stderr.log')])}
        report_path=candidate/'pilot.json';report_path.write_text(json.dumps(report))
        spec=json.loads(self.extension_path.read_text());spec['adoptions']={'1':f.row(report_path)}
        self.extension_path.write_text(json.dumps(spec));leaf=extension_runtime.Profile(self.extension_path)
        with patch.object(extension_runtime.pilot,'run_child',side_effect=AssertionError('candidate rerun')):
            extension_runtime.run_batch(leaf,1)
        self.assertTrue(leaf.validate_batch(1))
        receipt=json.loads((Path(batch['directory'])/extension_runtime.RECEIPT).read_text())
        self.assertFalse(receipt['adoption']['mapping_rerun'])
        self.assertEqual(receipt['adoption']['restoration']['verification'],'bound_full_pilot_complete_status')

    def test_leaf_cli_binds_original_pilot_path_from_a_new_bundle(self):
        f=self.fx;batch=f.native['batches'][1];length=10_000_000
        query=Path(batch['query']);query.write_text('>q3b\n'+'A'*length+'\n')
        batch['entries'][0]['length']=length;batch['query_sha256']=extension_runtime.pilot.digest(query)
        raw='q3b\t10000000\t0\t3\t+\tq2a\t12\t0\t3\t3\t3\t60\tcg:Z:3M\n'
        stderr='[M::worker_pipeline::0] mapped 1 sequences\n[M::main] Real time: 0.1 sec\n'
        f.tool.write_text('#!/usr/bin/env python3\nimport sys\nsys.stdout.write('+repr(raw)+')\nsys.stderr.write('+repr(stderr)+')\n')
        f.native['identities']['tool']=extension_runtime.pilot.digest(f.tool)
        f.source.write_text(json.dumps(f.native))
        f.profile.helper.publish(f.cache,extension_runtime.index_key(f.native),('target.mmi','index.stderr.log'))
        frozen=f.root/'original-frozen';frozen.mkdir()
        pilot=frozen/'full_self_seed_pilot.py';shutil.copyfile(extension_runtime.pilot.__file__,pilot)
        spec=json.loads(self.extension_path.read_text());spec['policy']['minimum_query_bases']=length
        spec['native_manifest']=f.row(f.source);spec['dependencies']['pilot']=f.row(pilot)
        spec['dependencies']['runtime']=f.row(Path(extension_runtime.__file__))
        self.extension_path.write_text(json.dumps(spec))
        environment={**os.environ,'PATH':str(f.root)+os.pathsep+os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-B',extension_runtime.__file__,'--profile',str(self.extension_path),
            '--batch-index','1'],env=environment,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((Path(batch['directory'])/'complete.json').is_file())

    def test_changed_primary_profile_or_output_is_not_reused(self):
        profile=composite.Profile(self.path)
        (self.fx.directory/'result.paf').write_text('changed')
        self.assertFalse(profile.validate_batch(0))
        self.fx.path.write_text('{}')
        with self.assertRaises(ValueError):profile.verify()

    def test_overlapping_selection_rejected(self):
        spec=json.loads(self.extension_path.read_text());spec['selected_batches']=[0]
        self.extension_path.write_text(json.dumps(spec))
        self.spec['extension_profile']=self.fx.row(self.extension_path);self.write()
        with self.assertRaisesRegex(ValueError,'overlapping'):composite.Profile(self.path)

    def test_nested_or_self_references_rejected(self):
        self.spec['primary_profile']=self.fx.row(self.path);self.write()
        with self.assertRaises(ValueError):composite.Profile(self.path)

    def test_unbound_runtime_rejected(self):
        self.spec['runtime']=self.fx.row(Path(extension_runtime.__file__));self.write()
        with self.assertRaisesRegex(ValueError,'unbound'):composite.Profile(self.path)

    def test_legacy_factory_keeps_the_original_execution_profile(self):
        profile=composite.Profile(self.fx.path)
        self.assertEqual(profile.sha,self.fx.profile.sha)
        self.assertTrue(profile.validate_batch(0))


if __name__=='__main__':unittest.main()
