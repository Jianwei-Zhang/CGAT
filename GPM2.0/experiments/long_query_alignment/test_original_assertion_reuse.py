"""Deferred source definitions ONLY; not run during implementation.

All attempts here are mocks. These definitions do not supply native/long-query
receipts, prove the customer mechanism or permit recovered-output publication.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare_long_identity as comparison
import native_first as nf
import windowed_alignment as wa

ASSERTION = b"minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs\x27 failed.\n"
LOAD = b"[M::main::114.971*2.46] loaded/built the index for 1 target sequence(s)\n"
MID_OCC = b"[M::mm_mapopt_update::118.735*2.42] mid_occ = 500\n"


class OriginalAssertionReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.tool = self.root/"mock-minimap2"
        self.tool.write_bytes(b"nonexecutable mock tool; NEVER launched")
        target,query,index = (self.root/name for name in ("target.fa","query.fa","part.mmi"))
        target.write_bytes(b">t1\nACGTACGT\n>t2\nACGTACGT\n")
        query.write_bytes(b">a first\nacgtACGT\n>b\nACGTACGT\n>c\nACGTACGT\n")
        index.write_bytes(b"mock first index part; not a real index")
        self.target,self.query = nf.RawFastaCatalog(target),nf.RawFastaCatalog(query)
        self.args = argparse.Namespace(threads=2,timeout=60,memory_gib=0)
        self.part = {"part_index":0,"path":str(index),"mid_occ":500,"sha256":wa.sha256(index),
            "records":[{"name":"t1","length":8}],"preset":"asm10",
            "reference_sha256":self.target.identity["sha256"],"tool_sha256":wa.sha256(self.tool)}
        self.directory = self.root/"original-native"
        self.context = nf.OriginalAttemptContext(self.directory,self.target)

    def original(self,*,log=LOAD+MID_OCC+ASSERTION,returncode=-6,change_command=None):
        self.directory.mkdir(exist_ok=True)
        stderr = self.directory/"native.stderr"
        stderr.write_bytes(log)
        partial = self.directory/"native.partial.paf"
        partial.write_bytes(b"incomplete/malformed PAF: must not be read or reused")
        command = [str(self.tool),"-c","-x","asm10","-t",str(self.args.threads),"-o",
                   str(partial),str(self.target.source),str(self.query.source)]
        if change_command is not None:
            change_command(command)
        execution = {"command":command,"returncode":returncode}
        receipt = {"status":"target_assertion","execution":execution,**nf.inspect_stderr(stderr),
            "path":str(partial),"paf_sha256":None,"paf_usable":False,"partial_PAF_reused":False,
            "stderr_sha256":wa.sha256(stderr)}
        wa.write_json(self.directory/"native.command.json",command)
        wa.write_json(self.directory/"native.execution.json",execution)
        wa.write_json(self.directory/"native-attempt.json",receipt)
        return receipt

    def seed(self,*,part=None,query=None,context=None):
        return nf._reuse_original_first_part(str(self.tool),self.part if part is None else part,
            self.query if query is None else query,self.context if context is None else context,self.args)

    def isolate(self,name,attempt,*,on_native=None,on_assertion=None):
        with patch.object(nf,"attempt",side_effect=attempt):
            return nf.isolate_part(str(self.tool),self.part,self.query,self.root/name,self.args,
                on_native=on_native or (lambda *args:None),on_assertion=on_assertion or (lambda *args:None),
                initial_assertion=self.context)

    def test_two_index_loads_are_not_one_part_even_when_mid_occ_prints_only_once(self):
        self.original(log=LOAD+MID_OCC+LOAD+ASSERTION)
        parsed = nf.inspect_stderr(self.directory/"native.stderr")
        self.assertEqual(parsed["index_sequence_counts"],[1,1])
        self.assertEqual(parsed["mid_occ_updates"],[500])
        self.assertTrue(parsed["index_metadata_complete"])
        self.assertIsNone(self.seed())

    def test_incomplete_malformed_and_oversized_log_metadata_declines_reuse(self):
        logs = [MID_OCC+ASSERTION,LOAD.replace(b"for 1",b"for 0")+MID_OCC+ASSERTION,
                LOAD.replace(b"for 1",b"for 2147483648")+MID_OCC+ASSERTION,
                LOAD+MID_OCC+ASSERTION.rstrip(b"\n"),
                b"x"*(nf.MAX_LOG_LINE+1)+b"\n"+LOAD+MID_OCC+ASSERTION]
        for log in logs:
            with self.subTest(log=log[:80]):
                self.original(log=log)
                self.assertIsNone(self.seed())

    def test_bounded_index_event_count_marks_metadata_ineligible(self):
        self.original(log=LOAD*3+MID_OCC+ASSERTION)
        with patch.object(nf,"MAX_MID_OCC_UPDATES",2):
            parsed = nf.inspect_stderr(self.directory/"native.stderr")
            self.assertEqual(parsed["index_sequence_counts"],[1,1])
            self.assertFalse(parsed["index_metadata_complete"])

    def test_only_root_is_reused_and_singleton_still_executes_before_recovery(self):
        self.original()
        attempted,native,leaves = [],[],[]
        def run(mm,target,query,root,args,**kwargs):
            names = list(nf.RawFastaCatalog(query).records)
            attempted.append(names)
            self.assertEqual(kwargs["mid_occ"],500)
            return {"status":"target_assertion" if "b" in names else "native_success"}
        real_hash = wa.sha256
        def hash_without_partial(path):
            self.assertNotEqual(Path(path),self.directory/"native.partial.paf")
            return real_hash(path)
        with patch.object(wa,"sha256",side_effect=hash_without_partial):
            report = self.isolate("isolated",run,on_native=lambda receipt,names,part:native.append(names),
                on_assertion=lambda name,*args:leaves.append(name))
        self.assertEqual(attempted,[["a"],["b","c"],["b"],["c"]])
        self.assertEqual(native,[["a"],["c"]])
        self.assertEqual(leaves,["b"])
        self.assertEqual(report["status"],"all_groups_completed")
        self.assertTrue(report["original_root_assertion_reused"])
        self.assertEqual(report["native_attempts_started"],4)
        self.assertEqual(len(report["attempts"]),5)
        self.assertEqual([r["reused_original_assertion"] for r in report["attempts"]],[True,False,False,False,False])
        self.assertEqual(report["attempts"][0]["attempt_receipt"],str(self.directory/"native-attempt.json"))
        self.assertFalse((self.root/"isolated/group-000000/native").exists())
        self.assertTrue((self.root/"isolated/group-000000/reused-original-assertion.json").is_file())
        self.assertFalse(report["partial_PAF_reused"])

    def test_no_recovery_is_inferred_if_both_child_groups_succeed(self):
        self.original()
        attempted = []
        def run(mm,target,query,*args,**kwargs):
            attempted.append(list(nf.RawFastaCatalog(query).records))
            return {"status":"native_success"}
        report = self.isolate("no-singleton-failure",run,
            on_assertion=lambda *args:self.fail("original group failure is not a singleton failure"))
        self.assertEqual(attempted,[["a"],["b","c"]])
        self.assertEqual(report["assertion_leaves"],0)
        # The selective caller separately refuses an original failure with no
        # actual asserting singleton; this report cannot certify recovery.

    def test_non_target_child_failure_stops_without_recovery(self):
        self.original()
        with self.assertRaisesRegex(wa.ExperimentError,"non-target failure"):
            self.isolate("other-failure",lambda *args,**kwargs:{"status":"other_failure"},
                on_assertion=lambda *args:self.fail("non-target failure must not recover"))
        report = json.loads((self.root/"other-failure/isolation.json").read_text())
        self.assertEqual(report["native_attempts_started"],1)
        self.assertEqual(report["status"],"refused_or_failed")

    def test_nonfirst_part_singleton_and_missing_files_never_seed_recovery(self):
        self.original()
        self.assertIsNone(self.seed(part={**self.part,"part_index":1}))
        singleton = self.root/"singleton.fa";singleton.write_bytes(b">b\nACGTACGT\n")
        self.assertIsNone(self.seed(query=nf.RawFastaCatalog(singleton)))
        (self.directory/"native.execution.json").unlink()
        attempted = []
        def run(mm,target,query,*args,**kwargs):
            attempted.append(list(nf.RawFastaCatalog(query).records))
            return {"status":"native_success"}
        report = self.isolate("missing-file-fallback",run)
        self.assertEqual(attempted,[["a","b","c"]])
        self.assertFalse(report["original_root_assertion_reused"])
        self.assertEqual(report["native_attempts_started"],1)

    def test_uncertain_part_count_or_threshold_runs_normal_root_instead(self):
        for i,log in enumerate((MID_OCC+ASSERTION,LOAD+MID_OCC+LOAD+ASSERTION,
                                LOAD+MID_OCC.replace(b"500",b"600")+ASSERTION)):
            with self.subTest(i=i):
                self.original(log=log)
                attempted = []
                def run(mm,target,query,*args,**kwargs):
                    attempted.append(list(nf.RawFastaCatalog(query).records))
                    return {"status":"native_success"}
                report = self.isolate(f"fallback-{i}",run)
                self.assertEqual(attempted,[["a","b","c"]])
                self.assertFalse(report["original_root_assertion_reused"])

    def test_altered_original_command_is_rejected_not_used_as_a_seed(self):
        changes = [lambda c:c.__setitem__(1,"-a"),lambda c:c.__setitem__(3,"asm5"),
                   lambda c:c.__setitem__(5,"1"),lambda c:c.__setitem__(-1,"another-query"),
                   lambda c:c.insert(1,"--print-qname")]
        for change in changes:
            with self.subTest(change=change):
                self.original(change_command=change)
                with self.assertRaisesRegex(wa.ExperimentError,"command/exit/log"):
                    self.seed()

    def test_abort_assertion_and_unusable_partial_flags_are_all_required(self):
        for rc in (0,-9,1,None,True):
            with self.subTest(rc=rc):
                self.original(returncode=rc)
                with self.assertRaisesRegex(wa.ExperimentError,"command/exit/log"):
                    self.seed()
        self.original(log=LOAD+MID_OCC+ASSERTION.replace(b"qoff ==",b"qoff !="))
        with self.assertRaisesRegex(wa.ExperimentError,"command/exit/log"):
            self.seed()
        for key,value in (("paf_usable",True),("partial_PAF_reused",True),("status","native_success")):
            with self.subTest(key=key):
                receipt = self.original();receipt[key] = value
                wa.write_json(self.directory/"native-attempt.json",receipt)
                with self.assertRaisesRegex(wa.ExperimentError,"command/exit/log"):
                    self.seed()

    def test_source_tool_and_original_prefix_bindings_are_mandatory(self):
        self.original()
        bad_parts = [{**self.part,"preset":"asm5"},{**self.part,"reference_sha256":"0"*64},
                     {**self.part,"tool_sha256":"0"*64},
                     {**self.part,"records":[{"name":"t2","length":8}]}]
        for part in bad_parts:
            with self.subTest(part=part),self.assertRaisesRegex(wa.ExperimentError,"reference/query/tool/index"):
                self.seed(part=part)
        with self.assertRaisesRegex(wa.ExperimentError,"internal original-run context"):
            self.seed(context={"status":"target_assertion"})

    def test_modified_log_receipt_is_not_trusted(self):
        receipt = self.original()
        receipt["index_sequence_counts"] = [2]
        wa.write_json(self.directory/"native-attempt.json",receipt)
        with self.assertRaisesRegex(wa.ExperimentError,"command/exit/log"):
            self.seed()

    def test_changed_original_evidence_stops_before_child_output_acceptance(self):
        self.original()
        def run(*args,**kwargs):
            with (self.directory/"native.stderr").open("ab") as out:
                out.write(b"changed after seed verification\n")
            return {"status":"native_success"}
        with self.assertRaisesRegex(wa.ExperimentError,"evidence or input changed"):
            self.isolate("mutated",run,on_native=lambda *args:self.fail("changed evidence accepted"))
        report = json.loads((self.root/"mutated/isolation.json").read_text())
        self.assertEqual(report["status"],"refused_or_failed")

    def test_each_original_evidence_file_is_guarded_after_capture(self):
        for name in ("native-attempt.json","native.command.json","native.execution.json","native.stderr"):
            with self.subTest(name=name):
                self.original();seed = self.seed()
                with (self.directory/name).open("ab") as out:
                    out.write(b" ")
                with self.assertRaisesRegex(wa.ExperimentError,"evidence or input changed"):
                    nf._check_original_assertion(seed,self.query)

    def test_final_evidence_hash_is_rechecked_not_only_cached_fingerprint(self):
        self.original();seed = self.seed()
        path = self.directory/"native.stderr"
        saved = wa.fingerprint(path)
        with path.open("ab") as out:
            out.write(b"different content\n")
        real_fingerprint = wa.fingerprint
        with patch.object(wa,"fingerprint",side_effect=lambda p:saved if Path(p)==path else real_fingerprint(p)):
            with self.assertRaisesRegex(wa.ExperimentError,"evidence or input changed"):
                nf._check_original_assertion(seed,self.query,rehash=True)


class RootReuseAcceptanceDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        original = self.root/"original-native";original.mkdir()
        for name in ("native-attempt.json","native.command.json","native.execution.json"):
            (original/name).write_text("mock evidence ONLY\n")
        (original/"native.stderr").write_bytes(LOAD+MID_OCC+ASSERTION)
        proof = {"rule":"verified_original_first_part_whole_group_assertion_only","part_index":0,
            "attempt_receipt":str(original/"native-attempt.json"),"failed_PAF_reused":False,
            "singleton_replay_still_required":True,"index_sequence_counts":[1],"mid_occ":500,
            "evidence_files_sha256":{p.name:wa.sha256(p) for p in original.iterdir()}}
        path = self.root/"part-0000/group-000000/reused-original-assertion.json"
        path.parent.mkdir(parents=True);wa.write_json(path,proof)
        attempts = [{"group":0,"parent_group":None,"queries":list(comparison.QUERY_ORDER),
            "status":"target_assertion","reused_original_assertion":True,
            "attempt_receipt":proof["attempt_receipt"]}]
        for i in range(1,7):
            attempts.append({"group":i,"reused_original_assertion":False,
                "attempt_receipt":str(self.root/f"part-0000/group-{i:06d}/native/native-attempt.json")})
        self.report = {"part_index":0,"original_root_assertion_reused":True,"attempts":attempts,
                       "native_attempts_started":6,"initial_assertion_evidence":proof}

    def test_structure_can_be_audited_without_running_or_accepting_a_mapper(self):
        result = comparison.audit_original_root_reuse(self.report,self.root)
        self.assertEqual(result["redundant_root_attempts_avoided"],1)
        self.assertTrue(result["singleton_replay_still_required"])
        # This only checks reuse structure. audit_selective still verifies all
        # real executions, asserting singletons and their complete paired paths.

    def test_child_reuse_missing_attempt_or_inconsistent_counter_is_refused(self):
        reports = []
        changed = deepcopy(self.report);changed["attempts"][1]["reused_original_assertion"] = True;reports.append(changed)
        changed = deepcopy(self.report);changed["attempts"].pop();reports.append(changed)
        changed = deepcopy(self.report);changed["native_attempts_started"] = 7;reports.append(changed)
        changed = deepcopy(self.report);changed["attempts"][1]["attempt_receipt"] = changed["attempts"][0]["attempt_receipt"];reports.append(changed)
        changed = deepcopy(self.report);changed["attempts"][0]["queries"].reverse();reports.append(changed)
        for report in reports:
            with self.subTest(report=report),self.assertRaises(wa.ExperimentError):
                comparison.audit_original_root_reuse(report,self.root)

    def test_changed_original_evidence_and_duplicate_root_directory_are_refused(self):
        stderr = self.root/"original-native/native.stderr"
        stderr.write_bytes(LOAD+MID_OCC+LOAD+ASSERTION)
        with self.assertRaises(wa.ExperimentError):
            comparison.audit_original_root_reuse(self.report,self.root)
        stderr.write_bytes(LOAD+MID_OCC+ASSERTION)
        (self.root/"part-0000/group-000000/native").mkdir()
        with self.assertRaisesRegex(wa.ExperimentError,"duplicate root execution"):
            comparison.audit_original_root_reuse(self.report,self.root)


if __name__=="__main__":
    unittest.main()
