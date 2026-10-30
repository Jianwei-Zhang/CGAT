"""Adapter publication/lifecycle units; real acceptance has separate receipts."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import server_alignment as sa
import windowed_alignment as wa


class ServerAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root/"workspace"
        (self.workspace/".prepare_lib").mkdir(parents=True)
        (self.workspace/"metadata").mkdir()
        self.run = self.workspace/"runs"/"assembly_vs_ref"
        self.run.mkdir(parents=True)
        self.runtime = self.root/"runtime"
        self.runtime.mkdir()
        for name in sa.RUNTIME_FILES:
            (self.runtime/name).write_bytes(b"mock runtime receipt file; not imported or executed\n")
        self.manifest = {"schema":1,"status":"unvalidated_branch_runtime","scope":"initial_reference_asm10_only",
                         "recovered_output_admission":"closed_pending_final_acceptance",
                         "files_sha256":sa.runtime_files(self.runtime)}
        wa.write_json(self.runtime/sa.MANIFEST,self.manifest)
        self.target,self.query = self.root/"target.fa",self.root/"query.fa"
        self.target.write_bytes(b">t\nACGT\n"); self.query.write_bytes(b">q\nACGT\n")
        self.args = argparse.Namespace(server_dir=self.workspace,run_dir=self.run,target=self.target,query=self.query,
                                       result="result.paf",preset="asm10",threads=3)

    def native(self,options,*,prepared_workspace):
        self.assertEqual(prepared_workspace,self.workspace)
        self.assertEqual(options.threads,3)
        self.assertEqual(options.memory_gib,0)
        self.assertIsNone(options.native_state_bundle)
        options.out.mkdir()
        data = b"opaque complete native PAF bytes\n"
        (options.out/"reference.candidate.experimental.paf").write_bytes(data)
        report = {"status":"experimental_candidate_only","routing_mode":"native_complete_unchanged",
                  "original_inputs_unchanged":True,"partial_PAF_reused":False,"recovered_query_part_cells":0,
                  "native_confidence_unchanged":True,"output_sha256":wa.sha256(options.out/"reference.candidate.experimental.paf")}
        wa.write_json(options.out/"selective-reference.json",report)
        return report

    def execute(self,side_effect=None):
        with patch.object(sa.sr,"experiment",side_effect=side_effect or self.native),redirect_stderr(io.StringIO()):
            return sa.run_reference(self.args,runtime_root=self.runtime)

    def test_native_complete_output_publishes_without_rewriting_or_recovery(self):
        result = self.execute()
        self.assertEqual((self.run/"result.paf").read_bytes(),b"opaque complete native PAF bytes\n")
        self.assertEqual(result["status"],"native_complete_published")
        self.assertTrue(result["result_published"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["customer_configuration_required"])
        self.assertEqual(result["publication"]["sha256"],wa.sha256(self.run/"result.paf"))
        self.assertTrue((Path(result["attempt"])/"publication.complete.paf").is_file())

    def test_source_checked_native_success_stays_opaque_without_recovery_lookup(self):
        self.manifest.update(status="source_checked_recovery_runtime",recovered_output_admission=sa.rp.POLICY,
                             native_companion_sha256="a"*64,native_companion_platform="linux-x86_64")
        wa.write_json(self.runtime/sa.MANIFEST,self.manifest)
        with patch.object(sa.nst,"validate_bundle",side_effect=AssertionError("normal native output must stay lazy")):
            report = self.execute()
        self.assertEqual(report["status"],"native_complete_published")
        self.assertFalse(report["recovered_native_confidence_published"])
        self.assertEqual((self.run/"result.paf").read_bytes(),b"opaque complete native PAF bytes\n")

    def test_original_source_change_after_mapping_prevents_publication(self):
        tool=self.root/"mock-tool";tool.write_bytes(b"mock identity only")
        def changed(options,**kwargs):
            report=self.native(options,**kwargs)
            report.update(reference=sa.nf.source_identity(self.target),query=sa.nf.source_identity(self.query),
                          tool={"path":str(tool),**sa.nf.source_identity(tool)})
            self.query.write_bytes(b">q\nTTTT\n")
            wa.write_json(options.out/"selective-reference.json",report)
            return report
        with self.assertRaisesRegex(wa.ExperimentError,"input/tool changed"):
            self.execute(changed)
        self.assertFalse((self.run/"result.paf").exists())

    def test_source_guard_is_rechecked_after_copy_before_the_atomic_link(self):
        attempt=self.run/"guarded-attempt";attempt.mkdir()
        source=attempt/"source.paf";source.write_bytes(b"complete bytes")
        calls=[]
        def guard():
            calls.append(True)
            if len(calls)==2:
                raise wa.ExperimentError("source changed during copy")
        with self.assertRaisesRegex(wa.ExperimentError,"source changed during copy"):
            sa.publish_atomic(source,wa.sha256(source),self.run/"result.paf",attempt,check_unchanged=guard)
        self.assertEqual(len(calls),2)
        self.assertFalse((self.run/"result.paf").exists())
        self.assertTrue((attempt/"publication.complete.paf").exists())

    def test_policy_label_alone_cannot_enable_an_unvalidated_runtime(self):
        self.manifest["recovered_output_admission"]=sa.rp.POLICY
        wa.write_json(self.runtime/sa.MANIFEST,self.manifest)
        with self.assertRaisesRegex(wa.ExperimentError,"source/contract"):
            self.execute()

    def test_previous_output_is_quarantined_not_destroyed_or_reused(self):
        (self.run/"result.paf").write_bytes(b"prior complete result")
        result = self.execute()
        self.assertEqual(Path(result["previous_result"]["path"]).read_bytes(),b"prior complete result")
        self.assertFalse(result["previous_result"]["restored_automatically"])
        self.assertNotEqual((self.run/"result.paf").read_bytes(),b"prior complete result")

    def test_actual_recovery_stays_nonzero_and_cannot_publish_unknown_or_private_confidence(self):
        (self.run/"result.paf").write_bytes(b"prior result must not look current")
        def recovered(options,**kwargs):
            report = self.native(options,**kwargs)
            report.update(routing_mode="exact_assertion_whole_record_isolation",recovered_query_part_cells=1)
            (options.out/"reference.native-evaluated.experimental.paf").write_bytes(b"private candidate")
            wa.write_json(options.out/"selective-reference.json",report)
            return report
        with self.assertRaisesRegex(wa.ExperimentError,"admission is CLOSED"):
            self.execute(recovered)
        self.assertFalse((self.run/"result.paf").exists())
        attempt = next(self.run.glob(".long-cigar-attempt-*"))
        self.assertEqual((attempt/"prior-result.paf").read_bytes(),b"prior result must not look current")
        self.assertTrue((attempt/"selective"/"reference.native-evaluated.experimental.paf").exists())
        report = json.loads((attempt/"server-alignment.json").read_text())
        self.assertFalse(report["result_published"])
        self.assertEqual(report["status"],"refused_or_failed")

    def test_other_failure_and_cancellation_never_restore_stale_success(self):
        for i,error in enumerate((wa.ExperimentError("other native failure"),KeyboardInterrupt("cancelled"))):
            (self.run/"result.paf").write_bytes(f"previous-{i}".encode())
            with self.subTest(error=type(error).__name__),self.assertRaises(type(error)):
                self.execute(lambda *args,**kwargs:(_ for _ in ()).throw(error))
            self.assertFalse((self.run/"result.paf").exists())

    def test_runtime_change_or_manually_enabled_manifest_is_refused(self):
        self.manifest["recovered_output_admission"] = "enabled"
        wa.write_json(self.runtime/sa.MANIFEST,self.manifest)
        with self.assertRaisesRegex(wa.ExperimentError,"contract mismatch"):
            self.execute()
        self.assertFalse(list(self.run.glob(".long-cigar-attempt-*")))

    def test_runtime_change_during_mapping_prevents_publication(self):
        def changed(options,**kwargs):
            report = self.native(options,**kwargs)
            (self.runtime/"native_first.py").write_bytes(b"changed source")
            return report
        with self.assertRaisesRegex(wa.ExperimentError,"mismatch"):
            self.execute(changed)
        self.assertFalse((self.run/"result.paf").exists())

    def test_live_task_lock_not_a_leftover_file_guards_concurrent_attempts(self):
        lock = self.run/".long-cigar-alignment.lock"
        lock.write_bytes(b"a leftover file is not a live process")
        with sa.task_lock(self.run):
            with self.assertRaisesRegex(wa.ExperimentError,"another initial-reference"):
                self.execute()
        self.execute()

    def test_existing_result_symlink_is_preserved_and_no_mapper_started(self):
        destination = self.root/"protected-result"
        destination.write_bytes(b"untouched")
        (self.run/"result.paf").symlink_to(destination)
        with patch.object(sa.sr,"experiment") as mapping,redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(wa.ExperimentError,"not a regular file"):
                sa.run_reference(self.args,runtime_root=self.runtime)
        mapping.assert_not_called()
        self.assertTrue((self.run/"result.paf").is_symlink())
        self.assertEqual(destination.read_bytes(),b"untouched")

    def test_atomic_publication_is_no_clobber_even_if_output_appears_at_link(self):
        attempt = self.run/"attempt"
        attempt.mkdir()
        source = attempt/"source.paf"
        source.write_bytes(b"new complete native bytes")
        output = self.run/"result.paf"
        link = sa.os.link
        def race(*args,**kwargs):
            output.write_bytes(b"another complete writer")
            return link(*args,**kwargs)
        with patch.object(sa.os,"link",side_effect=race),self.assertRaises(FileExistsError):
            sa.publish_atomic(source,wa.sha256(source),output,attempt)
        self.assertEqual(output.read_bytes(),b"another complete writer")

    def test_wrong_publication_hash_leaves_only_attempt_evidence(self):
        attempt = self.run/"attempt"
        attempt.mkdir()
        source = attempt/"source.paf"
        source.write_bytes(b"native source")
        with self.assertRaisesRegex(wa.ExperimentError,"changed"):
            sa.publish_atomic(source,"0"*64,self.run/"result.paf",attempt)
        self.assertFalse((self.run/"result.paf").exists())

    def test_termination_uses_existing_child_cancellation_path_and_restores_handlers(self):
        previous = {n:signal.getsignal(n) for n in (signal.SIGTERM,signal.SIGHUP)}
        with sa.cancellation_scope():
            for n in previous:
                handler = signal.getsignal(n)
                self.assertTrue(callable(handler))
                with self.assertRaises(KeyboardInterrupt):
                    handler(n,None)  # No signal or process is actually sent/launched.
        self.assertEqual({n:signal.getsignal(n) for n in previous},previous)

    def test_no_self_local_preset_or_foreign_workspace_route_is_enabled(self):
        for key,value in (("preset","asm5"),("result","other.paf"),("run_dir",self.root)):
            old = getattr(self.args,key)
            setattr(self.args,key,value)
            with self.subTest(key=key),self.assertRaisesRegex(wa.ExperimentError,"initial-reference"):
                self.execute()
            setattr(self.args,key,old)
        self.assertFalse(list(self.run.glob(".long-cigar-attempt-*")))


if __name__=="__main__":
    unittest.main()
