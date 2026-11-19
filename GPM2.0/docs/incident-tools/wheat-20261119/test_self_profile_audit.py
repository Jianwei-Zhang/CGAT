import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_self_profile_bindings as fixtures
import self_profile_audit as audit


class PortableSelfAuditTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SelfBindingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.ctx=SimpleNamespace(work=self.f.fx.work,selfs=self.f.bindings,
            contract=fixtures.contract,verify=self.f.bindings.verify)

    def test_complete_outputs_bind_actual_policy_without_private_absolute_paths(self):
        self.f.invoke(self.f.mapper)
        rows=audit.self_rows(self.ctx)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['approximate_batch_count'],1)
        self.assertEqual(rows[0]['ordinary_batch_count'],1)
        self.assertEqual(rows[0]['approximate_batches'][0]['queries'],[{'name':'ctg1','length':12}])
        self.assertEqual(rows[0]['approximate_batches'][0]['policy']['seed_fraction'],'0.001')
        self.assertNotIn(str(self.f.fx.root),json.dumps(rows))

    def test_incomplete_group_cannot_be_exported(self):
        with self.assertRaises((OSError,ValueError)):audit.self_rows(self.ctx)

    def test_modified_result_or_receipt_cannot_be_exported(self):
        self.f.invoke(self.f.mapper)
        result=self.f.fx.op/'result.paf';original=result.read_bytes();result.write_bytes(b'changed')
        with self.assertRaises(ValueError):audit.self_rows(self.ctx)
        result.write_bytes(original)
        (self.f.fx.directory/audit.RECEIPT).write_text('{}')
        with self.assertRaises(ValueError):audit.self_rows(self.ctx)

if __name__=='__main__':unittest.main()
