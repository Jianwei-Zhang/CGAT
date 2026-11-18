import json
from pathlib import Path
import unittest

from export_routing_provenance import build_audit, compact_decisions, publish
from routing_resume_support import OverrideError
import test_routing_resume_support as fixtures
contract = fixtures.contract


class AuditTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.BindingTests(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        self.f=f
        f.plan['policy']['long_bases']=60;f.write_plan()
        self.bindings=f.bindings()
        self.receipt_path,self.receipt=f.receipt()
        paf=f.command.parent/'result.paf'
        paf.write_text('short\t20\t0\t20\t+\tt\t1000\t0\t20\t20\t20\t60\tcg:Z:20M\n'
                       'long\t80\t0\t80\t+\tt\t1000\t0\t80\t80\t80\t60\tcg:Z:80M\n')
        def group(names,fraction):
            identity={'phase':'whole_records','queries':names,'filter':fraction,'preset':'asm10',
                      'target_sha256':'target','tool_sha256':'tool'}
            return {'status':'success','exit_code':0,'identity':identity,'cache_key':contract.fingerprint(identity)}
        ordinary=group({'short':20},None); fast=group({'long':80},.005)
        self.receipt.update(query_count=2,query_bases=100,output=contract.file_identity(paf),
            decisions=[{'query':'short','length':20,'filter':None,'reason':'ordinary_query_or_target_size'},
                       {'query':'long','length':80,'filter':.005,'reason':'bounded_calibration_admitted',
                        'calibration_scope':'three_fixed_windows_only','cases':[{'filter':.005,'passed':True,
                         'positions':{'baseline_anchor_count':3},'error':'private /home/user/attempt'}]}],
            group_evidence=[ordinary,fast],effective_sources={'short':ordinary['cache_key'],'long':fast['cache_key']})
        for name in ('stdout.log','stderr.log'):(f.command.parent/name).write_text('')
        self.markers=f.root/'markers';self.markers.mkdir()
        self.marker_path=self.markers/(contract.fingerprint(f.rel)+'.json')
        self.commit_fixture()

    def commit_fixture(self):
        f=self.f
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.marker={'status':'success','command':f.rel,'inputs':self.bindings.bind_inputs(f.task,f.inputs),
                     'outputs':[contract.file_identity(f.command.parent/name,relative_to=f.work)
                                for name in ('result.paf','stderr.log','stdout.log','routing-receipt.json')]}
        self.marker_path.write_text(json.dumps(self.marker))

    def audit(self):
        return build_audit(self.bindings,self.markers,contract)

    def test_portable_audit_is_output_bound_and_scoped(self):
        report=self.audit(); row=report['alignments'][0]
        self.assertTrue(report['complete_within_scope']);self.assertFalse(report['certifies_whole_workflow'])
        self.assertFalse(report['initial_reference_policy']);self.assertFalse(report['self_alignment_policy'])
        self.assertEqual(row['records']['approximate_record_count'],1)
        self.assertEqual(row['records']['ordinary_record_count'],1)
        self.assertEqual(row['result_paf']['sha256'],self.receipt['output']['sha256'])
        serialized=json.dumps(report)
        self.assertNotIn(str(self.f.root),serialized)
        self.assertNotIn('private /home/user',serialized)
        self.assertEqual(row['target'],{'sha256':'target'})

    def test_missing_or_partial_leaf_cannot_produce_complete_audit(self):
        self.marker['status']='partial';self.marker_path.write_text(json.dumps(self.marker))
        with self.assertRaises(OverrideError):self.audit()
        self.marker_path.unlink()
        with self.assertRaises(FileNotFoundError):self.audit()

    def test_native_identity_cannot_masquerade_as_routed(self):
        del self.marker['inputs']['execution_override'];self.marker_path.write_text(json.dumps(self.marker))
        with self.assertRaisesRegex(OverrideError,'execution override'):self.audit()

    def test_changed_completed_output_is_rejected(self):
        (self.f.command.parent/'stdout.log').write_text('changed')
        with self.assertRaisesRegex(OverrideError,'output manifest'):self.audit()

    def test_receipt_inventory_omission_is_rejected_even_if_manifest_is_updated(self):
        self.receipt['decisions'].pop();self.commit_fixture()
        with self.assertRaisesRegex(OverrideError,'inventory'):self.audit()

    def test_probe_group_cannot_become_final_evidence(self):
        self.receipt['group_evidence'][1]['identity']['phase']='calibration';self.commit_fixture()
        with self.assertRaisesRegex(OverrideError,'whole mapping'):self.audit()

    def test_paf_names_must_match_the_receipt(self):
        paf=self.f.command.parent/'result.paf'
        paf.write_text(paf.read_text().replace('short\t','unexpected\t'))
        self.receipt['output']=contract.file_identity(paf);self.commit_fixture()
        with self.assertRaisesRegex(OverrideError,'PAF query inventory'):self.audit()

    def test_coverage_fallback_is_reported_as_ordinary_not_approximate(self):
        row=self.receipt['decisions'][1];row.update(effective_filter=None,fallback_reason='full_query_coverage_guard',candidate_coverage=.5)
        source=self.receipt['group_evidence'][1]
        source['identity']['filter']=None;source['cache_key']=contract.fingerprint(source['identity'])
        self.receipt['effective_sources']['long']=source['cache_key'];self.commit_fixture()
        records=self.audit()['alignments'][0]['records']
        self.assertEqual(records['approximate_record_count'],0)
        self.assertEqual(records['long_or_approximate_records'][0]['fallback_reason'],'full_query_coverage_guard')

    def test_publishing_is_idempotent_but_never_overwrites_other_evidence(self):
        output=self.f.root/'comparison-audit/q0-routing-provenance.json';report=self.audit()
        publish(report,output,contract);publish(report,output,contract)
        with self.assertRaises(OverrideError):publish({**report,'scope':'changed'},output,contract)
        self.assertEqual(json.loads(output.read_text()),report)


if __name__=='__main__':unittest.main()
