import json
import types
import unittest
from unittest.mock import patch

import test_routing_resume_support as fixtures
import routing_resume_support as support
import routing_q0_evidence_reader as driver
from lgz_core import q0_preparation as q0


class RoutingReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.BindingTests(methodName="runTest")
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f
        f.receipt()
        self.native, self.writer = f.checkpoint_fixture()
        self.prepared = self.writer.prepare(f.task.unit_id, f.rel)
        self.writer.commit(self.prepared)
        self.bindings = f.bindings()
        self.reader = driver.reader_class(type(self.native), self.bindings,
            lambda task, assigned: f.inputs, {}, support)
        self.declaration = {"schema": "test-reader", "routing_plan_sha256": self.bindings.plan_hash}
        (f.work / "metadata").mkdir()
        (f.work / driver.LAUNCHER).write_text("original science, explicit routed reader")
        self.original_inputs = lambda root: (None, None, None, None, ["source.fa"], [], set())
        self.module = types.SimpleNamespace(OuterCheckpointManager=type(self.native),
            _initial_inputs=self.original_inputs, builder_identity=q0.builder_identity,
            load_verified_evidence=q0.load_verified_evidence, prepare_evidence=self.prepare_fixture)

    def prepare_fixture(self, root, *, threads, minimap2):
        # Reproduce the actual q0 reader boundary with a real Outer validate:
        # native reader rejects the routed key; adapted reader must validate it.
        manager = self.module.OuterCheckpointManager(root)
        prepared = manager.prepare(self.f.task.unit_id, self.f.rel)
        valid, reason = manager.validate(prepared)
        if not valid: raise ValueError(reason)
        paths = self.module._initial_inputs(root)[4]
        catalog = "catalog.json"
        (root / catalog).write_text(json.dumps({"schema": q0.CATALOG_SCHEMA,
            "base_alignments": [], "supplementary_alignments": [], "evidence": {}}))
        inputs = [q0.identity(root, path) for path in paths]
        result = {"schema": q0.SCHEMA, "status": "success", "policy": q0.POLICY,
            "builder": self.module.builder_identity(), "inputs": inputs,
            "outputs": [q0.identity(root, catalog)], "catalog": catalog, "tool": {"fixture": True}}
        result["input_fingerprint"] = q0.stable_id("q0-evidence-input", {"inputs": inputs,
            "tool": result["tool"], "policy": q0.POLICY, "builder": result["builder"]})
        (root / q0.MANIFEST).write_text(json.dumps(result))
        return result

    def execute(self):
        return driver.prepare_with_reader(self.module, self.f.work, self.reader,
            self.bindings, self.declaration, threads=1, minimap2="unused-fixture")

    def test_native_rejection_is_reproduced_then_explicit_reader_passes(self):
        native_prepared = self.native.prepare(self.f.task.unit_id, self.f.rel)
        self.assertFalse(self.native.validate(native_prepared)[0])
        self.assertTrue(self.reader(self.f.work).validate(
            self.reader(self.f.work).prepare(self.f.task.unit_id, self.f.rel))[0])

    def test_unchanged_downstream_consumer_accepts_explicit_bound_provenance(self):
        before = self.prepared.path.read_bytes()
        result = self.execute()
        self.assertEqual(q0.load_verified_evidence(self.f.work), result)
        self.assertTrue({driver.RECEIPT, driver.LAUNCHER} <= {r["path"] for r in result["inputs"]})
        self.assertEqual(result["builder"], q0.builder_identity())
        self.assertEqual(self.prepared.path.read_bytes(), before)
        self.assertIs(self.module.OuterCheckpointManager, type(self.native))
        self.assertIs(self.module._initial_inputs, self.original_inputs)

    def test_corrupt_paf_is_rejected_not_relabelled(self):
        (self.f.command.parent / "result.paf").write_text("corrupt")
        with self.assertRaises((ValueError, fixtures.contract.OrchestrationContractError)):
            self.execute()
        self.assertFalse((self.f.work / q0.MANIFEST).exists())

    def test_missing_routing_receipt_is_rejected(self):
        (self.f.command.parent / "routing-receipt.json").unlink()
        with self.assertRaisesRegex(ValueError, "checkpoint validation failed"): self.execute()
        self.assertIs(self.module.OuterCheckpointManager, type(self.native))

    def test_changed_plan_is_rejected(self):
        self.f.path.write_text("{}")
        with self.assertRaises(support.OverrideError): self.execute()

    def test_reader_is_read_only(self):
        with self.assertRaisesRegex(support.OverrideError, "cannot publish"):
            self.reader(self.f.work).commit(self.prepared)

    def test_changed_reader_declaration_is_not_overwritten(self):
        self.execute()
        p = self.f.work / driver.RECEIPT; p.write_text("{}")
        with self.assertRaisesRegex(ValueError, "explicit migration"): self.execute()
        self.assertEqual(p.read_text(), "{}")

    def test_downstream_rejects_later_launcher_or_declaration_change(self):
        self.execute()
        for rel in (driver.LAUNCHER, driver.RECEIPT):
            p = self.f.work / rel; original = p.read_bytes(); p.write_text("changed")
            with self.assertRaises(q0.Q0EvidenceError): q0.load_verified_evidence(self.f.work)
            p.write_bytes(original)

    def test_routing_dependency_change_is_rejected_before_publication(self):
        def changed_inputs(root):
            values = self.original_inputs(root)
            self.f.code.write_text("changed dependency")
            return values
        self.module._initial_inputs = changed_inputs
        with self.assertRaises(support.OverrideError): self.execute()
        self.assertFalse((self.f.work / q0.MANIFEST).exists())
        self.assertIs(self.module.builder_identity, q0.builder_identity)

    def test_reader_restored_after_builder_error(self):
        with patch.object(self.module, "prepare_evidence", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError): self.execute()
        self.assertIs(self.module.OuterCheckpointManager, type(self.native))
        self.assertIs(self.module._initial_inputs, self.original_inputs)


if __name__ == "__main__":
    unittest.main()
