import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

from routing_resume_support import RoutingBindings, OverrideError, checkpoint_class
TOOLS = Path(os.environ.get("CGAT_ROUTER_TEST_TOOLS", str(Path(__file__).resolve().parents[3] / "server/tools")))
sys.path.insert(0, str(TOOLS))
import run_orchestration as contract
from alignment_tasks import AlignmentTask, run_tasks
from run_outer_checkpoints import PreparedOuterCheckpoint, OuterCheckpointManager


class BindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.work = self.root / 'work'; self.work.mkdir()
        self.rel = 'runs/chr_4D/left_vs_right/command.sh'
        self.command = self.work / self.rel; self.command.parent.mkdir(parents=True)
        self.command.write_text('native command unchanged\n')
        self.script = self.root / 'route.sh'; self.script.write_text('explicit execution override\n')
        self.code = self.root / 'code.py'; self.code.write_text('frozen code\n')
        self.task = AlignmentTask('q0_chr:4D', self.command, 3)
        self.path = self.root / 'plan.json'
        self.plan = {'schema': 'incident_q0_routing_v1', 'workspace': str(self.work),
                     'preset': 'asm10', 'policy': {'version': 'fixture'},
                     'router_dependency_names': ['router', 'positions'],
                     'dependencies': {k: {'path': str(self.code), 'sha256': contract.sha256_file(self.code)}
                                      for k in ('router', 'positions')},
                     'overrides': [{'unit_id': 'q0_chr:4D', 'native_command': self.rel,
                        'native_command_sha256': contract.sha256_file(self.command),
                        'script': contract.file_identity(self.script),
                        'receipt': str(self.command.parent / 'routing-receipt.json')}]}
        self.inputs = {'files': [{'sha256': 'command'}, {'sha256': 'target'}, {'sha256': 'query'}],
                       'tool': {'sha256': 'tool'}}
        self.write_plan()

    def write_plan(self):
        self.path.write_text(json.dumps(self.plan))

    def bindings(self):
        return RoutingBindings(self.work, self.path, contract)

    def receipt(self):
        paf = self.command.parent / 'result.paf'
        paf.write_text('q\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\tcg:Z:10M\n')
        row = {'status': 'complete', 'scope': 'q0_cross_only', 'whole_records_preserved': True,
               'target_sha256': 'target', 'query_sha256': 'query', 'tool_sha256': 'tool',
               'preset': 'asm10', 'policy': self.plan['policy'],
               'dependencies': {k:v['sha256'] for k,v in self.plan['dependencies'].items()},
               'router_sha256': contract.sha256_file(self.code),
               'metrics_sha256': contract.sha256_file(self.code), 'output': contract.file_identity(paf)}
        path = Path(self.plan['overrides'][0]['receipt']); path.write_text(json.dumps(row))
        return path, row

    def test_native_commands_and_reference_keys_are_unchanged(self):
        bindings = self.bindings()
        other = dataclasses.replace(self.task, unit_id='ref:other', command=self.work / 'reference.sh')
        self.assertIs(bindings.bind_inputs(other, self.inputs), self.inputs)
        before = PreparedOuterCheckpoint('ref:other', 'reference_alignment', self.root/'cp', {'a':1}, 'old')
        self.assertIs(bindings.bind_prepared(before), before)
        self.assertEqual(self.command.read_text(), 'native command unchanged\n')

    def test_routed_leaf_and_outer_checkpoint_both_bind_override(self):
        bindings = self.bindings(); bound = bindings.bind_inputs(self.task, self.inputs)
        self.assertIn('execution_override', bound)
        self.assertNotIn('execution_override', self.inputs)
        before = PreparedOuterCheckpoint(self.task.unit_id, 'q0_chromosome_alignments', self.root/'cp', {'a':1}, 'old')
        after = bindings.bind_prepared(before)
        self.assertNotEqual(after.input_fingerprint, before.input_fingerprint)
        self.assertEqual(after.input_payload['incident_execution_overrides'], [bound['execution_override']])

    def test_script_or_dependency_mutation_is_rejected(self):
        for path in (self.script, self.code, self.command, self.path):
            original = path.read_bytes(); bindings = self.bindings(); path.write_bytes(original + b'changed')
            with self.assertRaises(OverrideError): bindings.verify()
            path.write_bytes(original)

    def test_self_alignment_and_duplicate_routes_are_rejected(self):
        for value in ('runs/chr_4D/left_vs_self/command.sh', 'runs/ref/command.sh', '../outside/command.sh'):
            with self.subTest(value=value):
                self.plan['overrides'][0]['native_command'] = value; self.write_plan()
                with self.assertRaises(OverrideError): self.bindings()
        self.plan['overrides'][0]['native_command'] = self.rel
        self.plan['overrides'].append(dict(self.plan['overrides'][0])); self.write_plan()
        with self.assertRaises(OverrideError): self.bindings()

    def test_wrong_workspace_or_task_unit_is_rejected(self):
        bindings = self.bindings()
        with self.assertRaises(OverrideError): bindings.bind_inputs(dataclasses.replace(self.task, unit_id='q0_chr:1A'), self.inputs)
        self.plan['workspace'] = str(self.root); self.write_plan()
        with self.assertRaises(OverrideError): self.bindings()

    def test_dispatch_preserves_callbacks_budget_and_native_tasks(self):
        bindings = self.bindings(); seen=[]
        other = dataclasses.replace(self.task, command=self.work/'untouched.sh')
        environment={'GPM_RUN_THREADS':'16'}
        def original(tasks, budget, children, cancel_signal, on_start, on_line, on_finish, env, *, dispatch):
            self.assertEqual(tasks[0].command, self.script)
            self.assertIs(tasks[1], other); self.assertEqual(budget, 16); self.assertIs(env, environment)
            self.assertEqual(dispatch, 'dispatcher')
            on_start(tasks[0], 3); on_line(tasks[0], 'line'); on_finish(tasks[0], 17, False)
            return 'result'
        result = bindings.dispatch(original)([self.task, other], 16, None, None,
            lambda task,n: seen.append((task,n)), lambda task,line: seen.append((task,line)),
            lambda task,code,cancel: seen.append((task,code,cancel)), environment, dispatch='dispatcher')
        self.assertEqual(result, 'result')
        self.assertTrue(seen[1][1].startswith('ROUTE_EXECUTION_OVERRIDE'))
        self.assertEqual([seen[0], *seen[2:]], [(self.task,3),(self.task,'line'),(self.task,17,False)])

    def test_valid_receipt_is_an_additional_bound_output(self):
        path,_ = self.receipt()
        identity = self.bindings().receipt_identity(self.task, self.inputs)
        self.assertEqual(identity, contract.file_identity(path, relative_to=self.work))

    def test_wrong_preset_policy_source_or_output_receipt_is_rejected(self):
        path,row = self.receipt(); bindings=self.bindings()
        for field,value in [('preset','asm20'),('status','partial'),('query_sha256','wrong'),('policy',{}),('dependencies',{})]:
            path.write_text(json.dumps({**row,field:value}))
            with self.assertRaises(OverrideError): bindings.receipt_identity(self.task,self.inputs)
        path.write_text(json.dumps(row))
        (self.command.parent/'result.paf').write_text('q\t10\t0\t5\t+\tt\t10\t0\t5\t5\t5\t60\tcg:Z:5M\n')
        with self.assertRaisesRegex(OverrideError, 'PAF differs'): bindings.receipt_identity(self.task,self.inputs)

    def test_missing_receipt_is_not_a_success(self):
        with self.assertRaises(FileNotFoundError): self.bindings().receipt_identity(self.task,self.inputs)

    def test_checkpoint_other_kind_is_not_rebound(self):
        before=PreparedOuterCheckpoint(self.task.unit_id,'assignment',self.root/'cp',{},'old')
        with self.assertRaises(OverrideError): self.bindings().bind_prepared(before)

    def checkpoint_fixture(self):
        work, command, task, inputs = self.work, self.command, self.task, self.inputs
        source = work / 'source.fa'; source.write_text('original source')
        class FixtureBase(OuterCheckpointManager):
            def prepare(self, unit_id, command_relpath):
                payload = {'command_relpath': command_relpath,
                           'inputs': [contract.file_identity(command, relative_to=work),
                                      contract.file_identity(source, relative_to=work)]}
                return PreparedOuterCheckpoint(unit_id, 'q0_chromosome_alignments', work/'checkpoint.json',
                                               payload, contract.fingerprint(payload))
            def _output_identities(self, prepared):
                return [contract.file_identity(command.parent/'result.paf', relative_to=work)]
        bound = checkpoint_class(FixtureBase, self.bindings(), lambda task, assignment: inputs, {})
        return FixtureBase(self.work), bound(self.work)

    def test_outer_commit_refreshes_bound_inputs_and_rejects_native_reuse(self):
        self.receipt(); native, manager = self.checkpoint_fixture()
        prepared = manager.prepare(self.task.unit_id, self.rel)
        manager.commit(prepared)
        self.assertTrue(manager.validate(prepared)[0])
        self.assertFalse(native.validate(native.prepare(self.task.unit_id, self.rel))[0])
        saved=json.loads(prepared.path.read_text())
        self.assertIn('incident_execution_overrides', saved['input_payload'])
        self.assertEqual(len(saved['outputs']), 2)

    def test_outer_commit_refuses_changed_source_without_publishing(self):
        self.receipt(); _, manager = self.checkpoint_fixture()
        prepared = manager.prepare(self.task.unit_id, self.rel)
        changed = dataclasses.replace(prepared,
            input_payload={**prepared.input_payload, 'injected': True})
        with self.assertRaises(OverrideError): manager.commit(changed)
        self.assertFalse(prepared.path.exists())

    def test_outer_validation_rechecks_receipt_after_commit(self):
        receipt, _ = self.receipt(); _, manager = self.checkpoint_fixture()
        prepared = manager.prepare(self.task.unit_id, self.rel); manager.commit(prepared)
        data=json.loads(receipt.read_text());data['preset']='asm20';receipt.write_text(json.dumps(data))
        with self.assertRaises(OverrideError): manager.validate(prepared)

    def test_actual_scheduler_executes_only_the_isolated_script(self):
        self.script.write_text('printf "routed\\n"\nexit 17\n')
        self.plan['overrides'][0]['script'] = contract.file_identity(self.script); self.write_plan()
        seen=[]; children={}
        code=self.bindings().dispatch(run_tasks)([self.task],2,children,lambda:None,
            lambda task,n: seen.append(('start',task,n)),lambda task,line: seen.append(('line',task,line)),
            lambda task,code,cancel: seen.append(('finish',task,code)),{})
        self.assertEqual(code,17)
        self.assertIn(('line',self.task,'routed'),seen)
        self.assertTrue(all(row[1] is self.task for row in seen))
        self.assertEqual(children,{})

    def test_fresh_outer_check_detects_non_command_input_changes(self):
        self.receipt(); _, manager=self.checkpoint_fixture()
        prepared=manager.prepare(self.task.unit_id,self.rel)
        (self.work/'source.fa').write_text('changed scientific input')
        with self.assertRaisesRegex(OverrideError,'inputs changed'):
            manager.commit(prepared)
        self.assertFalse(prepared.path.exists())


if __name__ == '__main__':
    unittest.main()
