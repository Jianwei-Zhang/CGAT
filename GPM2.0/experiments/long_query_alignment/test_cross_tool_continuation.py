"""Real native mappings under test-only binary pairs; not speed/ARM evidence."""
import argparse
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adaptive_ordinary_units as units
import adaptive_ordinary_controller as controller
import automatic_ordinary_pilot as pilot
import native_first as nf
import ordinary_tool_transition as ott
import proactive_resume as pr
import windowed_alignment as wa
import test_adaptive_ordinary_units as unit_controls
import test_adaptive_ordinary_controller as controller_controls
import test_automatic_ordinary_pilot as controls
import test_automatic_ordinary_server as server_controls
import server_alignment as sa


@contextmanager
def reviewed_pair(root, origin):
    # Both run on the native test host; append inert bytes to distinguish identity.
    path=root/'new-minimap2'
    path.write_bytes(Path(origin['path']).read_bytes()+b'CGAT TEST EXECUTOR IDENTITY\n')
    path.chmod(0o755)
    execution={'path':str(path),'sha256':wa.sha256(path)}
    inventory={origin['sha256']:(62,'x86_64'),execution['sha256']:(62,'x86_64')}
    with patch.object(ott,'_REVIEWED',inventory),patch.object(ott,'_PAIRS',{(origin['sha256'],execution['sha256'])}):
        yield execution


class CrossToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):controls.ActualNativeTests.setUpClass()

    def test_complete_unit_retains_old_receipt_and_never_maps(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=unit_controls.ActualUnitTests().fixture(root);out=root/'unit'
            first=units.run_unit(out,*inputs,timeout=30)
            marker=(out/'unit.json').read_bytes();paf=Path(first['source']['path']).read_bytes()
            with reviewed_pair(root,inputs[3]) as execution,patch.object(nf,'attempt',side_effect=AssertionError('paid work remapped')):
                for readonly in (False,True):
                    result=units.run_unit(out,*inputs,timeout=30,execution_tool=execution,readonly=readonly)
                    self.assertTrue(result['reused']);self.assertEqual(result['identity']['tool_sha256'],inputs[3]['sha256'])
            self.assertEqual((out/'unit.json').read_bytes(),marker)
            self.assertEqual(Path(first['source']['path']).read_bytes(),paf)

    def test_incomplete_unit_archived_then_only_new_tool_executes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=unit_controls.ActualUnitTests().fixture(root);out=root/'unit'
            with patch.object(nf,'attempt',side_effect=KeyboardInterrupt('controlled interruption')):
                with self.assertRaises(KeyboardInterrupt):units.run_unit(out,*inputs,timeout=30,primary_work=True)
            old=(out/'unit.json').read_bytes()
            with reviewed_pair(root,inputs[3]) as execution:
                with patch.object(nf,'attempt',wraps=nf.attempt) as mapping:
                    result=units.run_unit(out,*inputs,timeout=30,primary_work=True,execution_tool=execution)
                self.assertEqual(mapping.call_count,1);self.assertEqual(mapping.call_args.args[0],execution['path'])
                self.assertEqual(result['identity']['tool_sha256'],execution['sha256'])
                state=pr.read_json(out/'unit.json');archive=Path(state['previous_execution']['directory'])
                self.assertEqual((archive/'unit.json').read_bytes(),old)
                with patch.object(nf,'attempt',side_effect=AssertionError('repeat resume mapped')):
                    repeated=units.run_unit(out,*inputs,timeout=30,primary_work=True,execution_tool=execution,readonly=True)
                    self.assertTrue(repeated['reused'])
                    with self.assertRaises(wa.ExperimentError):units.run_unit(out,*inputs,timeout=30,readonly=True)
                state['execution_tool_transition']['historical_commands_rewritten']=True;wa.write_json(out/'unit.json',state)
                with self.assertRaisesRegex(wa.ExperimentError,'provenance'):
                    units.run_unit(out,*inputs,timeout=30,execution_tool=execution,readonly=True)

    def test_complete_native_pending_validation_not_reexecuted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=unit_controls.ActualUnitTests().fixture(root);out=root/'unit'
            with patch.object(pilot,'_verify_case',side_effect=KeyboardInterrupt('validation interrupted')):
                with self.assertRaises(KeyboardInterrupt):units.run_unit(out,*inputs,timeout=30)
            with reviewed_pair(root,inputs[3]) as execution,patch.object(nf,'attempt',side_effect=AssertionError('native completion rerun')):
                result=units.run_unit(out,*inputs,timeout=30,execution_tool=execution)
                self.assertTrue(result['reused']);self.assertEqual(result['identity']['tool_sha256'],inputs[3]['sha256'])

    def test_corrupt_completed_source_never_archived_or_remapped(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=unit_controls.ActualUnitTests().fixture(root);out=root/'unit'
            result=units.run_unit(out,*inputs,timeout=30);paf=Path(result['source']['path'])
            paf.write_bytes(paf.read_bytes()+b'corrupt\n');before=(out/'unit.json').read_bytes()
            with reviewed_pair(root,inputs[3]) as execution,patch.object(nf,'attempt',side_effect=AssertionError('corruption remapped')):
                with self.assertRaises(wa.ExperimentError):units.run_unit(out,*inputs,timeout=30,execution_tool=execution,primary_work=True)
            self.assertEqual((out/'unit.json').read_bytes(),before)
            self.assertTrue(paf.read_bytes().endswith(b'corrupt\n'))

    def test_controller_reuses_prefix_and_audits_mixed_tools(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);control=controller_controls.ControllerTests();inputs=control.fixture(root);out=root/'controller'
            control.execute(out,inputs,unit_limit=1)
            first=out/'units/unit-000000/unit.json';before=first.read_bytes()
            with reviewed_pair(root,inputs[2]) as execution:
                with patch.object(nf,'attempt',wraps=nf.attempt) as mapping:
                    result=control.execute(out,inputs,execution_tool=execution,primary_work=True,unit_seconds=None)
                self.assertGreater(mapping.call_count,0)
                self.assertTrue(all(call.args[0]==execution['path'] for call in mapping.call_args_list))
                self.assertEqual(first.read_bytes(),before)
                self.assertEqual(result['status'],'complete_bounded_policy_candidate')
                with patch.object(nf,'attempt',side_effect=AssertionError('mixed completed controller mapped')):
                    again=control.execute(out,inputs,execution_tool=execution,primary_work=True,unit_seconds=None,readonly=True)
                    self.assertEqual(again['composition'],result['composition'])
                    with self.assertRaises(wa.ExperimentError):control.execute(out,inputs,readonly=True)

    def test_existing_default_fallback_keeps_old_units_and_continues_new_tool(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);control=controller_controls.ControllerTests()
            inputs=control.fixture(root,filtered=True,weak=(5,15));out=root/'controller'
            real_verify=pilot._verify_case
            def controlled_times(*a,**kw):
                value=real_verify(*a,**kw);value['wall_seconds']=10 if a[6] is None else 2;return value
            with patch.object(pilot,'_verify_case',side_effect=controlled_times):
                cat,index,tool,args,budget=inputs
                def execute(**kw):return controller.execute(out,cat,index,tool,args,budget=budget,unit_bases=90000,**kw)
                first=execute(unit_limit=15)
                self.assertIsNotNone(first['default_continuation'])
                marker=out/'units/unit-000014/unit.json';before=marker.read_bytes()
                self.assertIsNone(pr.read_json(marker)['identity']['fraction'])
                with reviewed_pair(root,inputs[2]) as execution:
                    with patch.object(nf,'attempt',wraps=nf.attempt) as calls:
                        result=execute(execution_tool=execution,primary_work=True,unit_seconds=None)
                    self.assertEqual(marker.read_bytes(),before)
                    self.assertEqual(result['default_continuation'],first['default_continuation'])
                    self.assertTrue(all(call.args[0]==execution['path'] for call in calls.call_args_list))
                    self.assertGreater(calls.call_count,0)
                    with patch.object(nf,'attempt',side_effect=AssertionError('fallback replay mapped')):
                        again=execute(execution_tool=execution,primary_work=True,unit_seconds=None,readonly=True)
                    self.assertEqual(again['composition'],result['composition'])

    def test_prepared_adapter_resumes_same_attempt_and_publishes_mixed_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);server_controls.AutomaticOrdinaryServerTests.setUpClass()
            control=server_controls.AutomaticOrdinaryServerTests();runtime,args=control.fixture(root,weak=True,mixed=True)
            origin={'path':control.mm,'sha256':wa.sha256(Path(control.mm))}
            real_execute=controller.execute;real_native=nf.attempt
            def small_units(*a,**kw):
                kw['unit_bases']=300000
                return real_execute(*a,**kw)
            def interrupt_second(*a,**kw):
                if 'units/unit-000001' in str(a[3]):raise KeyboardInterrupt('controlled second unit stop')
                return real_native(*a,**kw)
            with control.controls(),patch.object(controller,'execute',side_effect=small_units),patch.object(nf,'attempt',side_effect=interrupt_second):
                with self.assertRaises(KeyboardInterrupt):sa.run_reference(args,runtime_root=runtime)
            attempt=Path(pr.read_json(args.run_dir/pr.LOCATOR)['attempt'])
            first=attempt/'selective/ordinary-adaptive/units/unit-000000/unit.json'
            before=first.read_bytes()
            real_which=pr.shutil.which
            with reviewed_pair(root,origin) as execution,control.controls(),patch.object(controller,'execute',side_effect=small_units),patch.object(pr.shutil,'which',side_effect=lambda name:execution['path'] if name=='minimap2' else real_which(name)):
                unexpected_long=attempt/'selective/long-unreviewed'
                unexpected_long.mkdir()
                with patch.object(nf,'attempt',side_effect=AssertionError('legacy long work remapped')):
                    with self.assertRaisesRegex(wa.ExperimentError,'previously started long-query'):
                        sa.run_reference(args,runtime_root=runtime)
                unexpected_long.rmdir()
                locator_before=(args.run_dir/pr.LOCATOR).read_bytes()
                checkpoint_before=(attempt/'selective'/pr.STATE).read_bytes()
                with patch.object(pr,'_compatible_runtime',return_value=False),patch.object(nf,'attempt',side_effect=AssertionError('unreviewed runtime restarted')):
                    with self.assertRaisesRegex(wa.ExperimentError,'without restart'):
                        sa.run_reference(args,runtime_root=runtime)
                self.assertEqual((args.run_dir/pr.LOCATOR).read_bytes(),locator_before)
                self.assertEqual((attempt/'selective'/pr.STATE).read_bytes(),checkpoint_before)
                with patch.object(nf,'attempt',wraps=real_native) as mapping:
                    result=sa.run_reference(args,runtime_root=runtime)
                self.assertTrue(result['attempt_reused']);self.assertEqual(Path(result['attempt']),attempt)
                self.assertTrue((args.run_dir/'result.paf').is_file())
                policy=pr.read_json(args.run_dir/'result.alignment.json')
                self.assertEqual({source['tool_sha256'] for source in policy['native_sources']},{origin['sha256'],execution['sha256']})
                self.assertEqual(policy['execution_tool_transition']['execution']['sha256'],execution['sha256'])
                self.assertEqual(set(policy['long_queries']),{'long1','long2'})
                self.assertTrue(policy['window_sources'])
                self.assertTrue(all(row['tool_sha256']==execution['sha256'] for row in policy['window_sources']))
                self.assertNotIn(str(root),json.dumps(policy))
                self.assertEqual(first.read_bytes(),before)
                self.assertGreater(mapping.call_count,0)
                self.assertTrue(all(call.args[0]==execution['path'] for call in mapping.call_args_list))
                report=pr.read_json(attempt/'selective/proactive-candidate.json')
                self.assertTrue(report['ordinary_adaptive']['reviews'])
                self.assertEqual(report['tool']['sha256'],origin['sha256'])
                self.assertEqual(report['execution_tool_transition']['execution']['sha256'],execution['sha256'])
                with patch.object(nf,'attempt',side_effect=AssertionError('published sources remapped')):
                    repeated=sa.run_reference(args,runtime_root=runtime)
                self.assertTrue(repeated['attempt_reused'])
                with patch.object(nf,'attempt',side_effect=AssertionError('invalid provenance remapped')):
                    altered=copy.deepcopy(report)
                    altered['execution_tool_transition']['origin']['sha256']='0'*64
                    with self.assertRaises(wa.ExperimentError):sa.pub.admit(altered,attempt/'selective',bundle=None)
                    altered=copy.deepcopy(report);altered.pop('execution_tool_transition')
                    with self.assertRaises(wa.ExperimentError):sa.pub.admit(altered,attempt/'selective',bundle=None)
                    altered=copy.deepcopy(report);altered['routing_mode']='proactive_query_length'
                    with self.assertRaises(wa.ExperimentError):sa.pub.admit(altered,attempt/'selective',bundle=None)


if __name__=='__main__':unittest.main()
