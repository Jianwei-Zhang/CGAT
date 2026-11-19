import copy
import dataclasses
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_self_seed_profile as profile_tests
import self_seed_profile as runtime
import self_profile_bindings as support
import run_orchestration as contract
from run_outer_checkpoints import PreparedOuterCheckpoint
from alignment_tasks import AlignmentTask


class SelfBindingTests(unittest.TestCase):
    def setUp(self):
        self.fx = profile_tests.SelfSeedProfileTests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        f = self.fx
        self.tasks = []
        commands = {}
        for i, batch in enumerate(f.native['batches']):
            path = Path(batch['directory']) / 'command.sh'; path.write_text('native-' + str(i))
            commands[str(i)] = contract.file_identity(path, relative_to=f.work)
            self.tasks.append(AlignmentTask('q0_chr:X', path, 1))
        self.script = f.root / 'override.sh'; self.script.write_text('profile-execution')
        self.task_manifest = f.op.parent / 'q0_alignment_tasks.json'
        self.task_manifest.write_text(json.dumps({'tasks': [{'command': t.command.relative_to(f.work).as_posix()} for t in self.tasks]}))
        self.plan_path = f.root / 'dispatch.json'
        self.row = {'operation': f.op.relative_to(f.work).as_posix(), 'unit_id': 'q0_chr:X',
            'profile': f.row(f.path), 'task_manifest': f.row(self.task_manifest),
            'native_commands': commands, 'scripts': {'0': contract.file_identity(self.script)}}
        self.plan = {'schema': support.SCHEMA, 'workspace': str(f.work),
                     'dependencies': {'support': f.row(Path(support.__file__))}, 'operations': [self.row]}
        self.plan_path.write_text(json.dumps(self.plan))
        self.bindings = support.SelfBindings(f.work, self.plan_path, contract)

    def invoke(self, original, tasks=None, final=None):
        events = []
        def finish(task, code, cancelling):
            events.append(('finish', task.command, code, (self.fx.op / 'result.paf').exists()))
            if final: final(task, code, cancelling)
        result = self.bindings.dispatch(original)(
            self.tasks if tasks is None else tasks, 16, {}, lambda: None,
            lambda t, n: events.append(('start', t.command, n)),
            lambda t, line: events.append(('line', t.command, line)), finish,
            {'frozen': 'environment'}, dispatch='dispatch-sentinel')
        return result, events

    def mapper(self, tasks, budget, children, signal, start, line, finish, environment, *, dispatch=None):
        self.assertEqual((budget, environment, dispatch), (16, {'frozen': 'environment'}, 'dispatch-sentinel'))
        for task in tasks:
            start(task, 1)
            if task.command == self.script:
                runtime.run_batch(self.bindings.profiles[self.row['operation']], 0)
            elif task.command == self.tasks[1].command:
                self.fx.publish_native_small()
            else:
                self.fail('unexpected command: ' + str(task.command))
            line(task, 'child log'); finish(task, 0, False)
        return 'dispatcher-result'

    def test_dispatch_only_selected_command_and_merge_before_last_native_callback(self):
        result, events = self.invoke(self.mapper)
        self.assertEqual(result, 'dispatcher-result')
        ends = [e for e in events if e[0] == 'finish']
        self.assertEqual(ends, [('finish', self.tasks[0].command, 0, False), ('finish', self.tasks[1].command, 0, True)])
        self.assertTrue(all(e[1] != self.script for e in events))

    def test_merge_also_when_profile_finishes_last(self):
        def reverse(tasks, *args, **kwargs): return self.mapper(list(reversed(tasks)), *args, **kwargs)
        _, events = self.invoke(reverse)
        self.assertEqual([e[3] for e in events if e[0] == 'finish'], [False, True])

    def test_complete_group_reused_without_mapper_index_build_or_per_batch_merge(self):
        self.fx.run_profile(); self.fx.publish_native_small()
        profile = self.bindings.profiles[self.row['operation']]
        with patch.object(profile, 'merge', wraps=profile.merge) as merge, \
             patch.object(profile.helper, 'ensure_index', side_effect=AssertionError('index reread')), \
             patch.object(runtime.pilot, 'run_child', side_effect=AssertionError('cache recomputed')):
            def original(tasks, *args, **kwargs):
                self.assertEqual(tasks, []); return 'no-work'
            result, events = self.invoke(original)
        self.assertEqual(result, 'no-work'); self.assertEqual(merge.call_count, 1)
        self.assertEqual(len([e for e in events if e[0] == 'finish']), 2)

    def test_partial_native_cache_reused_then_profile_completes(self):
        self.fx.publish_native_small()
        def original(tasks, *args, **kwargs):
            self.assertEqual([t.command for t in tasks], [self.script])
            return self.mapper(tasks, *args, **kwargs)
        _, events = self.invoke(original)
        self.assertEqual([e[1] for e in events if e[0] == 'finish'], [self.tasks[1].command, self.tasks[0].command])
        self.assertTrue((self.fx.op / 'result.paf').exists())

    def test_failure_or_cancellation_never_merges(self):
        for code, cancelling in ((1, False), (0, True)):
            def failure(tasks, budget, children, signal, start, line, finish, env, **kwargs):
                start(tasks[0], 1); finish(tasks[0], code, cancelling)
            profile = self.bindings.profiles[self.row['operation']]
            with patch.object(profile, 'merge', side_effect=AssertionError('failed group merged')):
                self.invoke(failure)

    def test_partial_duplicate_and_wrong_unit_task_sets_rejected(self):
        for tasks in (self.tasks[:1], [self.tasks[0], self.tasks[0]],
                      [dataclasses.replace(self.tasks[0], unit_id='q0_chr:Y'), self.tasks[1]]):
            with self.assertRaises(ValueError): self.invoke(self.mapper, tasks=tasks)

    def test_changed_native_command_script_or_task_manifest_rejected(self):
        for path in (self.tasks[0].command, self.script, self.task_manifest):
            before = path.read_bytes(); path.write_bytes(before + b'changed')
            with self.assertRaises(ValueError): self.bindings.verify(full=True)
            path.write_bytes(before)

    def test_reference_keys_untouched_and_existing_cross_fields_preserved(self):
        root = self.fx.root
        ref = PreparedOuterCheckpoint('ref:a', 'reference_alignment', root/'cp', {'a': 1}, 'original')
        self.assertIs(self.bindings.bind_prepared(ref), ref)
        before = PreparedOuterCheckpoint('q0_chr:X', 'q0_chromosome_alignments', root/'cp',
            {'command_relpath': 'q0.sh', 'incident_execution_overrides': ['cross-proof']}, 'before')
        after = self.bindings.bind_prepared(before)
        self.assertEqual(after.input_payload['incident_execution_overrides'], ['cross-proof'])
        self.assertIn('incident_self_execution', after.input_payload)
        self.assertNotEqual(after.input_fingerprint, before.input_fingerprint)

    def test_merged_output_and_selected_receipts_are_outer_outputs(self):
        self.invoke(self.mapper)
        rows = self.bindings.output_identities('q0_chr:X')
        self.assertEqual(len(rows), 3)
        self.assertTrue(any(r['path'].endswith(runtime.RECEIPT) for r in rows))
        (self.fx.op/'result.paf').write_text('corrupt')
        with self.assertRaises(ValueError): self.bindings.output_identities('q0_chr:X')

    def test_completed_cache_source_corruption_is_not_ignored(self):
        self.fx.run_profile(); self.fx.publish_native_small()
        self.bindings.verify_cached_sources(self.bindings.profiles[self.row['operation']], 0)
        query = Path(self.fx.native['batches'][0]['query'])
        query.write_bytes(query.read_bytes().replace(b'A', b'T'))
        with self.assertRaisesRegex(ValueError, 'source/tool changed'):
            self.invoke(self.mapper)

    def test_composed_outer_commit_retains_fresh_input_guard(self):
        self.invoke(self.mapper)
        root = self.fx.root
        class CrossBoundBase:
            changed = False
            def __init__(self, server_dir): self.server_dir = server_dir
            def prepare(self, unit_id, command_relpath):
                payload = {'command_relpath': command_relpath, 'incident_execution_overrides': ['cross-proof'],
                           'native_source': 'changed' if self.changed else 'original'}
                return PreparedOuterCheckpoint(unit_id, 'q0_chromosome_alignments', root/'outer.json',
                                               payload, contract.fingerprint(payload))
            def _output_identities(self, prepared): return [{'path': 'cross-receipt', 'sha256': 'cross-proof'}]
        cls = support.checkpoint_class(CrossBoundBase, self.bindings)
        writer = cls(self.fx.work); prepared = writer.prepare('q0_chr:X', 'q0.sh')
        writer.commit(prepared)
        record = json.loads(prepared.path.read_text())
        self.assertEqual(record['input_payload']['incident_execution_overrides'], ['cross-proof'])
        self.assertIn('incident_self_execution', record['input_payload'])
        self.assertEqual(len(record['outputs']), 4)
        CrossBoundBase.changed = True
        with self.assertRaisesRegex(ValueError, 'inputs changed'): writer.commit(prepared)


if __name__ == '__main__':
    unittest.main()
