"""Cache identity/integrity units and actual native group-resume controls."""
import argparse
from contextlib import ExitStack, redirect_stderr
import io
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import unittest
from unittest.mock import patch

import guided_alignment as ga
import native_evaluation as ne
import proactive_reference_plan as pp
import proactive_resume as pr
import recovery_publication as rp
import server_alignment as sa
import windowed_alignment as wa


class ResumeUnits(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_locator_reuses_only_same_key_and_keeps_changed_key_attempt(self):
        first,reused=pr.select_attempt(self.root,{"runtime":"a"})
        self.assertFalse(reused)
        (first/"selective").mkdir(); pr.Checkpoint(first/"selective",{"runtime":"a"})
        second,reused=pr.select_attempt(self.root,{"runtime":"a"})
        self.assertEqual(second,first); self.assertTrue(reused)
        for key in ({"runtime":"b"},{"runtime":"a","threads":2},{"runtime":"a","query":"changed"}):
            new,reused=pr.select_attempt(self.root,key)
            self.assertFalse(reused); self.assertNotEqual(first,new); self.assertTrue(first.exists())

    def test_foreign_locator_and_symlink_never_authorize_foreign_reuse(self):
        foreign=self.root/"foreign"; foreign.mkdir()
        run=self.root/"run"; run.mkdir()
        wa.write_json(run/pr.LOCATOR,{"schema":1,"key":{},"attempt":str(foreign)})
        attempt,reused=pr.select_attempt(run,{})
        self.assertFalse(reused); self.assertEqual(attempt.parent,run)
        saved=run/"saved.json"; (run/pr.LOCATOR).rename(saved)
        (run/pr.LOCATOR).symlink_to(saved)
        with self.assertRaisesRegex(wa.ExperimentError,"linked"): pr.select_attempt(run,{})
        self.assertTrue(saved.exists())

    def test_state_key_change_is_not_a_resume_override(self):
        pr.Checkpoint(self.root,{"identity":1})
        with self.assertRaisesRegex(wa.ExperimentError,"identity/schema"):
            pr.Checkpoint(self.root,{"identity":2})

    def test_spool_is_reopened_without_normalization_and_corruption_refuses(self):
        source=self.root/"input.fa"; source.write_bytes(b">a\nacgt\n>b\nNN\n")
        spool=self.root/"bases"
        cache=pr.Checkpoint(self.root,{"key":1}); store=cache.store(source,spool,"source")
        self.assertEqual(store.fetch("a",0,4),b"ACGT"); store.close()
        before=spool.stat().st_mtime_ns
        restored=pr.Checkpoint(self.root,{"key":1})
        with patch.object(wa.FastaStore,"__init__",side_effect=AssertionError("renormalized")):
            store=restored.store(source,spool,"source")
        self.assertEqual(store.fetch("b",0,2),b"NN"); store.close()
        self.assertEqual(spool.stat().st_mtime_ns,before)
        spool.write_bytes(b"TCGTNN")
        with self.assertRaisesRegex(wa.ExperimentError,"spool changed"):
            restored.store(source,spool,"source")

    def test_source_mutation_refuses_even_if_old_spool_remains_valid(self):
        source=self.root/"input.fa"; source.write_bytes(b">a\nACGT\n")
        cache=pr.Checkpoint(self.root,{}); cache.store(source,self.root/"bases","source").close()
        source.write_bytes(b">a\nTCGT\n")
        with self.assertRaisesRegex(wa.ExperimentError,"source changed"):
            cache.store(source,self.root/"bases","source")

    def test_corrupt_or_noncontiguous_store_metadata_refuses(self):
        source=self.root/"input.fa"; source.write_bytes(b">a\nACGT\n")
        cache=pr.Checkpoint(self.root,{}); cache.store(source,self.root/"bases","source").close()
        cache.data["stages"]["source"]["records"]["a"]["offset"]=1; cache.save()
        with self.assertRaisesRegex(wa.ExperimentError,"record layout"):
            pr.Checkpoint(self.root,{}).store(source,self.root/"bases","source")

    def test_partial_artifact_is_archived_not_read_or_deleted(self):
        partial=self.root/"partial"; partial.mkdir(); (partial/"failed.paf").write_bytes(b"partial")
        saved=pr.archive_partial(partial)
        self.assertFalse(partial.exists()); self.assertEqual((saved/"failed.paf").read_bytes(),b"partial")
        self.assertIsNone(pr.archive_partial(partial))


class RealResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY"); cls.bundle=os.environ.get("CGAT_NATIVE_CHAIN_STATE_BUNDLE")
        if not cls.mm or not cls.bundle: raise unittest.SkipTest("explicit pinned mapper/helper required")

    def fixture(self,root,*,all_long=False):
        runtime=root/"runtime"; runtime.mkdir()
        for name in sa.RUNTIME_FILES: shutil.copyfile(Path(sa.__file__).with_name(name),runtime/name)
        checked=sa.nst.validate_bundle(self.bundle)
        shutil.copytree(self.bundle,runtime/"native"/checked["platform"])
        wa.write_json(runtime/sa.MANIFEST,{"schema":1,"status":"source_checked_recovery_runtime",
            "scope":"initial_reference_asm10_only","recovered_output_admission":sa.pub.POLICY,
            "files_sha256":sa.runtime_files(runtime),"native_companion_sha256":checked["sha256"],
            "native_companion_platform":checked["platform"]})
        ws=root/"workspace"; (ws/".prepare_lib").mkdir(parents=True); (ws/"metadata").mkdir()
        run=ws/"runs/query_vs_ref"; run.mkdir(parents=True)
        rng=random.Random(2311302); sequence=bytes(rng.choices(b"ACGT",k=160000))
        target=root/"ref.fa"; query=root/"query.fa"
        target.write_bytes(b">ref\n"+sequence+b"\n")
        rows=[] if all_long else [(b"short",sequence[1000:5000])]
        rows += [(b"long1",sequence[10000:100000]),(b"long2",sequence[40000:130000].translate(wa.RC)[::-1])]
        query.write_bytes(b"".join(b">"+n+b"\n"+seq+b"\n" for n,seq in rows))
        args=argparse.Namespace(server_dir=ws,run_dir=run,target=target,query=query,threads=1,preset="asm10",result="result.paf")
        return runtime,args

    def controls(self):
        stack=ExitStack(); make_plan=pp.make_plan
        stack.enter_context(patch.dict(os.environ,{"PATH":str(Path(self.mm).parent)+os.pathsep+os.environ["PATH"]}))
        stack.enter_context(patch.object(pp,"MAX_OPERATION",64000))
        stack.enter_context(patch.object(rp,"PROACTIVE_QUERY_LIMIT",64000))
        stack.enter_context(patch.object(pp,"make_plan",side_effect=lambda catalog,policy=None:make_plan(catalog,policy or pp.WindowPolicy(20000,4000))))
        stack.enter_context(redirect_stderr(io.StringIO()))
        return stack

    def resume_after_second_cell_failure(self,*,all_long=False,cancelled=False):
        with tempfile.TemporaryDirectory(prefix="cgat-proactive-resume-") as tmp:
            root=Path(tmp); runtime,args=self.fixture(root,all_long=all_long)
            execute=ga.experiment; calls=[]
            def fail_second(options,**kwargs):
                calls.append(str(options.out))
                if len(calls)==2:
                    options.out.mkdir(); (options.out/"failed.partial.paf").write_bytes(b"NOT A COMPLETE PAF\n")
                    if cancelled: raise KeyboardInterrupt("injected cancellation")
                    raise wa.ExperimentError("injected second-cell failure")
                return execute(options,**kwargs)
            with self.controls(),patch.object(ga,"experiment",side_effect=fail_second):
                with self.assertRaises(KeyboardInterrupt if cancelled else wa.ExperimentError):
                    sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(len(calls),2); self.assertFalse((args.run_dir/"result.paf").exists())
            attempt=next(args.run_dir.glob('.long-cigar-attempt-*'))
            candidate=attempt/"selective"
            preserved={str(p): (wa.sha256(p),p.stat().st_mtime_ns) for p in
                [candidate/"target.default.mmi",candidate/"target.bases",Path(calls[0])/"guided.experimental.paf"]}
            if not all_long:
                p=candidate/"ordinary-native/native.complete.paf"; preserved[str(p)]=(wa.sha256(p),p.stat().st_mtime_ns)
            with self.controls(),patch.object(ga,"experiment",wraps=execute) as guided, \
                    patch.object(wa,"run_command",wraps=wa.run_command) as commands:
                result=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(result["attempt_reused"]); self.assertEqual(result["attempt"],str(attempt))
            self.assertEqual(guided.call_count,1); self.assertEqual(str(guided.call_args.args[0].out),calls[1])
            self.assertTrue(result["result_published"])
            self.assertEqual(result["cache_reused"]["index"],1)
            self.assertEqual(result["cache_reused"]["long_cells"],1)
            self.assertEqual(result["cache_reused"]["ordinary_group"],0 if all_long else 1)
            self.assertEqual(result["cache_reused"]["threshold_metadata"],1 if all_long else 0)
            self.assertEqual(result["cache_reused"]["sequence_stores"],2)
            self.assertTrue(all("-d" not in call.args[0] and call.args[2] not in ("native","metadata") for call in commands.call_args_list))
            for path,old in preserved.items():
                p=Path(path); self.assertEqual((wa.sha256(p),p.stat().st_mtime_ns),old)
            archived=list(Path(calls[1]).parent.glob(Path(calls[1]).name+".previous-*"))
            self.assertEqual(len(archived),1)
            self.assertEqual((archived[0]/"failed.partial.paf").read_bytes(),b"NOT A COMPLETE PAF\n")
            result_bytes=(args.run_dir/"result.paf").read_bytes()
            # A further same-input invocation does ZERO mapping/index/metadata
            # work, rechecks all cells and publishes from complete sources only.
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("unexpected rerun")):
                again=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(again["attempt_reused"]); self.assertEqual(again["cache_reused"]["long_cells"],2)
            self.assertEqual((args.run_dir/"result.paf").read_bytes(),result_bytes)
            self.assertEqual(Path(again["previous_result"]["path"]).read_bytes(),result_bytes)
            self.assertNotEqual(again["publication_evidence"],again["attempt"])
            self.assertEqual(len(list(args.run_dir.glob('.long-cigar-attempt-*'))),1)
            # Corrupt a cached complete ordinary/source PAF: no silent rebuild,
            # no mapper retry, and no stale success output.
            corrupt=(candidate/"ordinary-native/native.complete.paf") if not all_long else Path(calls[0])/"guided.experimental.paf"
            corrupt.write_bytes(corrupt.read_bytes()+b"corrupt\n")
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("unexpected retry")):
                with self.assertRaises(wa.ExperimentError): sa.run_reference(args,runtime_root=runtime)
            self.assertFalse((args.run_dir/"result.paf").exists())

    def test_input_change_selects_fresh_attempt_instead_of_reusing_old_cells(self):
        with tempfile.TemporaryDirectory(prefix="cgat-proactive-invalidation-") as tmp:
            root=Path(tmp); runtime,args=self.fixture(root)
            with self.controls(): first=sa.run_reference(args,runtime_root=runtime)
            original_attempt=Path(first["attempt"])
            old_report=(original_attempt/"server-alignment.json").read_bytes()
            with args.query.open("ab") as stream: stream.write(b">new_unmapped\n"+b"N"*3000+b"\n")
            with self.controls(),patch.object(wa,"run_command",wraps=wa.run_command) as commands:
                second=sa.run_reference(args,runtime_root=runtime)
            self.assertFalse(second["attempt_reused"])
            self.assertNotEqual(first["attempt"],second["attempt"])
            self.assertTrue(all(value==0 for value in second["cache_reused"].values()))
            self.assertEqual(sum("-d" in call.args[0] for call in commands.call_args_list),1)
            self.assertEqual((original_attempt/"server-alignment.json").read_bytes(),old_report)
            report=pr.read_json(Path(second["attempt"])/"selective/proactive-candidate.json")
            self.assertEqual(report["combination"]["original_cells"],4)
            self.assertEqual(report["combination"]["rows_by_query"]["new_unmapped"],0)

    def test_complete_unmapped_long_cell_is_reused_without_fake_native_status(self):
        with tempfile.TemporaryDirectory(prefix="cgat-proactive-empty-resume-") as tmp:
            root=Path(tmp); runtime,args=self.fixture(root,all_long=True)
            args.query.write_bytes(b">longN\n"+b"N"*90000+b"\n")
            with self.controls(): first=sa.run_reference(args,runtime_root=runtime)
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("empty cell was rerun")):
                second=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(second["attempt_reused"])
            self.assertEqual(second["cache_reused"]["long_cells"],1)
            self.assertEqual(second["cache_reused"]["threshold_metadata"],1)
            self.assertEqual((args.run_dir/"result.paf").read_bytes(),b"")
            self.assertEqual(second["status"],"proactive_complete_published")
            admission=pr.read_json(Path(second["attempt"])/"recovery-admission.json")
            self.assertEqual(admission["no_candidate_cells"],1)
            self.assertEqual(admission["recovered_cells"],0)

    def test_mixed_failure_reuses_index_ordinary_and_first_long_cell(self): self.resume_after_second_cell_failure()
    def test_all_long_failure_reuses_metadata_without_replaying_it(self): self.resume_after_second_cell_failure(all_long=True)
    def test_cancellation_keeps_successful_groups_for_next_invocation(self): self.resume_after_second_cell_failure(cancelled=True)


if __name__=="__main__": unittest.main()
