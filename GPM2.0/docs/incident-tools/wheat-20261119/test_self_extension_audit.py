import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_composite_self_profile as fixtures
import composite_self_profile as composite
import extended_self_seed_profile as extended
import self_profile_bindings as bindings
import self_extension_audit as audit


class ExtensionAuditTests(unittest.TestCase):
    def setUp(self):
        self.fx=fx=fixtures.CompositeTests();fx.setUp();self.addCleanup(fx.doCleanups)
        f=fx.fx;extended.run_batch(fx.extension,1);profile=composite.Profile(fx.path);profile.merge()
        commands={};scripts={}
        for i,batch in enumerate(f.native['batches']):
            command=Path(batch['directory'])/'command.sh';command.write_text('native command')
            commands[str(i)]=f.profile.contract.file_identity(command,relative_to=f.work)
            script=f.root/('guard-'+str(i)+'.sh');script.write_text('guarded command')
            scripts[str(i)]=f.profile.contract.file_identity(script)
        task=f.op.parent/'q0_alignment_tasks.json'
        task.write_text(json.dumps({'tasks':[{'command':row['path']} for row in commands.values()]}))
        row={'operation':f.op.relative_to(f.work).as_posix(),'unit_id':'q0_chr:X','profile':f.row(fx.path),
            'scripts':scripts,'native_commands':commands,'task_manifest':f.row(task)}
        plan={'schema':bindings.SCHEMA,'workspace':str(f.work),
              'dependencies':{'support':f.row(Path(bindings.__file__))},'operations':[row]}
        path=f.root/'audit-plan.json';path.write_text(json.dumps(plan))
        with patch.object(bindings,'Profile',composite.Profile):
            actual=bindings.SelfBindings(f.work,path,f.profile.contract)
        self.ctx=SimpleNamespace(selfs=actual,contract=f.profile.contract,work=f.work,verify=actual.verify)

    def test_portable_audit_keeps_each_actual_execution_policy_and_key(self):
        rows=audit.self_rows(self.ctx);self.assertEqual(len(rows),1)
        batches=rows[0]['approximate_batches'];self.assertEqual(len(batches),2)
        self.assertEqual(batches[0]['execution_profile_sha256'],self.fx.fx.profile.sha)
        self.assertEqual(batches[1]['execution_profile_sha256'],self.fx.extension.sha)
        self.assertEqual(batches[0]['policy']['minimum_query_bases'],10)
        self.assertEqual(batches[1]['policy']['minimum_query_bases'],1)
        self.assertNotIn(str(self.fx.fx.root),json.dumps(rows))

    def test_corrupt_primary_receipt_blocks_composite_audit(self):
        path=self.fx.fx.directory/'self-profile-receipt.json';row=json.loads(path.read_text())
        row['native_key']='changed';path.write_text(json.dumps(row))
        with self.assertRaises(ValueError):audit.self_rows(self.ctx)


if __name__=='__main__':unittest.main()
