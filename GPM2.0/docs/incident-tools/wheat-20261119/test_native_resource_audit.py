import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import native_resource_audit as audit
import test_native_resource_bindings as fixtures
import native_batch_guard as guard


class ResourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.NativeBindingTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.ctx=SimpleNamespace(selfs=self.fx.bindings,contract=self.fx.bindings.contract,work=self.fx.bindings.work)

    def test_guarded_rows_are_portable_and_preserve_actual_grant(self):
        self.fx.base.invoke(self.fx.mapper)
        rows=audit.native_rows(self.ctx)
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]["guard_execution_proven"])
        self.assertEqual(rows[0]["thread_grant"],1)
        self.assertNotIn(str(self.fx.base.fx.root),json.dumps(rows))

    def test_legacy_native_has_no_retroactive_guard_claim(self):
        self.fx.base.fx.publish_native_small()
        rows=audit.native_rows(self.ctx)
        self.assertFalse(rows[0]["guard_execution_proven"])
        self.assertNotIn("policy",rows[0]);self.assertNotIn("runtime_sha256",rows[0])

    def test_incomplete_or_tampered_native_cannot_export(self):
        with self.assertRaises(ValueError):audit.native_rows(self.ctx)
        path=self.fx.publish();proof=json.loads(path.read_text());proof["thread_grant"]=32
        path.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):audit.native_rows(self.ctx)


if __name__=="__main__":unittest.main()
