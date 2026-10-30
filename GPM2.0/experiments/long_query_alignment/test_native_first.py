"""Deferred native-first routing checks. Written only; NOT executed in this phase."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import native_first as nf
import selective_reference_alignment as sr
import windowed_alignment as wa

ASSERTION = b"minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs\x27 failed.\n"
MID_OCC = b"[M::mm_mapopt_update::118.735*2.42] mid_occ = 500\n"


def paf(name="a",target="t1",*,mapq=60,cigar=None,qlen=8,tlen=8,matches=8,block=8):
    tags = f"\tcg:Z:{cigar}" if cigar else "\ttp:A:P\tAS:i:8\tzz:Z:native-opaque"
    return f"{name}\t{qlen}\t0\t{qlen}\t+\t{target}\t{tlen}\t0\t{tlen}\t{matches}\t{block}\t{mapq}{tags}\n".encode()


class NativeFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.query = self.root/"query.fa"
        self.query.write_bytes(b">a description\r\nacgt\r\nACGT\r\n>b second\nACGTACGT\n>c\nACGTACGT")
        self.args = argparse.Namespace(threads=2,timeout=60,memory_gib=0)

    def receipt(self,path,data):
        path.write_bytes(data)
        return {"status":"native_success","paf_usable":True,"path":str(path),"paf_sha256":wa.sha256(path)}

    def part(self):
        index = self.root/"part.mmi"
        index.write_bytes(b"unchanged test index")
        return {"part_index":0,"path":str(index),"mid_occ":500,"records":[{"name":"t1","length":8}]}

    def merger(self):
        return nf.CellMerger(self.root/"cells",{n:{"length":8} for n in ("a","b","c")},
            {n:{"length":8} for n in ("t1","t2")},
            [{"part_index":i,"records":[{"name":n,"length":8}]} for i,n in enumerate(("t1","t2"))])

    def test_assertion_requires_exact_predicate_and_abort_exit(self):
        log = self.root/"stderr"
        log.write_bytes(MID_OCC+ASSERTION)
        parsed = nf.inspect_stderr(log)
        self.assertTrue(parsed["target_assertion_observed"])
        self.assertEqual(parsed["mid_occ_updates"],[500])
        for rc,expected in ((-signal.SIGABRT,"target_assertion"),(134,"target_assertion"),
                            (-signal.SIGKILL,"other_failure"),(1,"other_failure"),
                            (0,"masked_assertion_failure")):
            with self.subTest(rc=rc):
                self.assertEqual(nf.classify({"returncode":rc},parsed),expected)
        self.assertEqual(nf.classify({"returncode":-6,"interrupted":"TimeoutExpired"},parsed),"other_failure")
        log.write_bytes(MID_OCC+ASSERTION.replace(b"qoff ==",b"qoff !="))
        self.assertEqual(nf.classify({"returncode":-6},nf.inspect_stderr(log)),"other_failure")

    def test_threshold_can_come_from_failed_first_part_not_all_parts(self):
        failed = {"status":"target_assertion","mid_occ_updates":[500],"threshold_metadata_complete":True}
        self.assertEqual(nf.shared_mid_occ(failed,2),500)
        for updates in ([],[500,100],[500,500,500]):
            with self.subTest(updates=updates),self.assertRaises(wa.ExperimentError):
                nf.shared_mid_occ({**failed,"mid_occ_updates":updates},2)
        with self.assertRaises(wa.ExperimentError):
            nf.shared_mid_occ({**failed,"threshold_metadata_complete":False},2)

    def test_oversized_stderr_is_streamed_not_a_native_success_restriction(self):
        log = self.root/"stderr"
        with log.open("wb") as out:
            out.write(b"x"*(nf.MAX_LOG_LINE+100))
            out.write(b"\n"+MID_OCC)
        parsed = nf.inspect_stderr(log)
        self.assertEqual(nf.classify({"returncode":0},parsed),"native_success")
        self.assertFalse(parsed["threshold_metadata_complete"])

    def test_assertion_across_log_chunk_boundary_is_found(self):
        log = self.root/"stderr"
        log.write_bytes(b"x"*(nf.MAX_LOG_LINE-25)+b" "+ASSERTION)
        self.assertTrue(nf.inspect_stderr(log)["target_assertion_observed"])

    def test_raw_catalog_preserves_full_record_bytes_case_comments_and_order(self):
        before = self.query.read_bytes()
        catalog = nf.RawFastaCatalog(self.query)
        self.assertEqual([r["length"] for r in catalog.records.values()],[8,8,8])
        self.assertEqual(catalog.identity,nf.source_identity(self.query))
        output = self.root/"group.fa"
        result = catalog.copy_group(["a","c"],output)
        self.assertEqual(output.read_bytes(),b">a description\r\nacgt\r\nACGT\r\n>c\nACGTACGT")
        self.assertEqual(result["sha256"],wa.sha256(output))
        self.assertEqual(self.query.read_bytes(),before)
        self.assertFalse(any(self.root.glob("*.bases")))
        for names in (["c","a"],["a","a"],["missing"],[]):
            with self.subTest(names=names),self.assertRaises(wa.ExperimentError):
                catalog.copy_group(names,self.root/"not-created.fa")

    def test_unwrapped_sequence_chunks_are_not_new_records(self):
        raw = b">a\n"+b"ACGT"*70+b"\n>b comment\nACGT\n"
        self.query.write_bytes(raw)
        with patch.object(wa,"CHUNK",64):
            catalog = nf.RawFastaCatalog(self.query)
            self.assertEqual(catalog.records["a"]["length"],280)
            catalog.copy_group(["a","b"],self.root/"copied.fa")
        self.assertEqual((self.root/"copied.fa").read_bytes(),raw)

    def test_raw_catalog_rejects_duplicate_empty_or_non_dna_after_failure(self):
        for i,data in enumerate((b">a\nA\n>a\nC\n",b">a\n>b\nA\n",b">a\nA-C\n")):
            path = self.root/f"invalid-{i}.fa"
            path.write_bytes(data)
            with self.subTest(i=i),self.assertRaises(wa.ExperimentError):
                nf.RawFastaCatalog(path)

    def test_native_attempt_exposes_failure_without_reusing_partial_paf(self):
        def run(command,directory,name,*args,**kwargs):
            self.assertTrue(kwargs["allow_failure"])
            Path(command[command.index("-o")+1]).write_bytes(b"incomplete/unusable")
            (directory/f"{name}.stderr").write_bytes(MID_OCC+ASSERTION)
            return {"returncode":-6}
        with patch.object(wa,"run_command",side_effect=run):
            receipt = nf.attempt("minimap2","target",self.query,self.root/"attempt",self.args)
        self.assertEqual(receipt["status"],"target_assertion")
        self.assertFalse(receipt["paf_usable"])
        self.assertFalse(receipt["partial_PAF_reused"])
        self.assertTrue(Path(receipt["path"]).is_file())
        self.assertFalse((self.root/"attempt"/"native.complete.paf").exists())

    def test_bisection_is_bounded_and_recovers_only_actual_singleton_even_if_short(self):
        catalog,part = nf.RawFastaCatalog(self.query),self.part()
        native,leaves,attempted = [],[],[]
        def attempt(mm,target,query,root,args,**kwargs):
            names = list(nf.RawFastaCatalog(query).records)
            attempted.append(names)
            self.assertEqual(kwargs["mid_occ"],500)
            return {"status":"target_assertion" if "b" in names else "native_success"}
        with patch.object(nf,"attempt",side_effect=attempt):
            result = nf.isolate_part("minimap2",part,catalog,self.root/"isolate",self.args,
                on_native=lambda receipt,names,part:native.append(names),
                on_assertion=lambda name,*args:leaves.append(name))
        self.assertEqual(attempted,[["a","b","c"],["a"],["b","c"],["b"],["c"]])
        self.assertEqual(native,[["a"],["c"]])
        self.assertEqual(leaves,["b"])
        self.assertEqual(result["attempt_bound"],5)
        self.assertEqual(result["assertion_leaves"],1)
        self.assertTrue(result["length_is_not_a_recovery_trigger"])

    def test_non_target_failure_never_causes_bisection_or_recovery(self):
        for i,status in enumerate(("other_failure","masked_assertion_failure")):
            with self.subTest(status=status),patch.object(nf,"attempt",return_value={"status":status}) as run:
                with self.assertRaisesRegex(wa.ExperimentError,"non-target failure"):
                    nf.isolate_part("minimap2",self.part(),nf.RawFastaCatalog(self.query),
                        self.root/f"failure-{i}",self.args,
                        on_native=lambda *args:self.fail("must not accept"),
                        on_assertion=lambda *args:self.fail("must not recover"))
                self.assertEqual(run.call_count,1)

    def test_query_or_index_mutation_stops_isolation_before_acceptance(self):
        part = self.part()
        def mutate(*args,**kwargs):
            Path(part["path"]).write_bytes(b"changed index")
            return {"status":"native_success"}
        with patch.object(nf,"attempt",side_effect=mutate),self.assertRaisesRegex(wa.ExperimentError,"changed"):
            nf.isolate_part("minimap2",part,nf.RawFastaCatalog(self.query),self.root/"isolate",self.args,
                on_native=lambda *args:self.fail("changed index accepted"),on_assertion=lambda *args:None)

    def test_global_input_guard_runs_even_on_an_asserting_non_singleton(self):
        seen = []
        def guard():
            seen.append("checked")
            if len(seen)==2:
                raise wa.ExperimentError("tool changed after failed non-singleton")
        with patch.object(nf,"attempt",return_value={"status":"target_assertion"}) as run:
            with self.assertRaisesRegex(wa.ExperimentError,"tool changed"):
                nf.isolate_part("minimap2",self.part(),nf.RawFastaCatalog(self.query),self.root/"guard",self.args,
                    on_native=lambda *args:self.fail("must not accept"),
                    on_assertion=lambda *args:self.fail("must not recover"),check_unchanged=guard)
        self.assertEqual(run.call_count,1)

    def test_mixed_cells_preserve_native_tags_bytes_and_original_part_query_order(self):
        merger = self.merger()
        a1,b1,a2,b2 = paf(),paf("b",mapq=255,cigar="8="),paf(target="t2"),paf("b","t2")
        merger.add_native(self.receipt(self.root/"first.paf",a1),["a","c"],part_index=0)
        recovered = self.root/"recovered.paf"
        recovered.write_bytes(b1)
        validator = lambda raw:sr.validate_row(raw,merger.queries,merger.targets,{"b"},"risk")
        merger.add_recovered(recovered,wa.sha256(recovered),"b",0,validator)
        merger.add_native(self.receipt(self.root/"second.paf",b2+a2),["a","b","c"],part_index=1)
        output = self.root/"complete.paf"
        report = merger.finish(output)
        self.assertEqual(output.read_bytes(),a1+b1+a2+b2)
        self.assertEqual(report["native_cells"],5)
        self.assertEqual(report["recovered_cells"],1)
        self.assertEqual(report["rows_by_query"],{"a":2,"b":2,"c":0})

    def test_native_optional_body_is_opaque_and_has_no_32mib_recovery_line_limit(self):
        merger = self.merger()
        source = self.root/"large-native.paf"
        with source.open("wb") as out:
            out.write(paf().rstrip(b"\n")+b"\tzz:Z:")
            for _ in range(33):
                out.write(b"x"*1024**2)
            out.write(b"\n")
        merger.add_native({"status":"native_success","paf_usable":True,"path":str(source),"paf_sha256":wa.sha256(source)},
                         ["a","b","c"])
        output = self.root/"large-combined.paf"
        merger.finish(output)
        self.assertEqual(wa.sha256(output),wa.sha256(source))

    def test_complete_zero_row_native_cells_are_not_missing_cells(self):
        merger = self.merger()
        merger.add_native(self.receipt(self.root/"empty.paf",b""),["a","b","c"])
        output = self.root/"empty-complete.paf"
        report = merger.finish(output)
        self.assertEqual(output.read_bytes(),b"")
        self.assertTrue(report["all_cells_completed"])
        self.assertEqual(report["native_cells"],6)

    def test_missing_duplicate_and_failed_native_cells_are_refused(self):
        merger = self.merger()
        receipt = self.receipt(self.root/"source.paf",paf())
        with self.assertRaisesRegex(wa.ExperimentError,"failed or partial"):
            merger.add_native({**receipt,"status":"target_assertion"},["a"])
        merger.add_native(receipt,["a"],part_index=0)
        with self.assertRaises(wa.ExperimentError):
            merger.finish(self.root/"missing.paf")
        with self.assertRaisesRegex(wa.ExperimentError,"overlap"):
            merger.add_native(receipt,["a"],part_index=0)
        with self.assertRaises(wa.ExperimentError):
            merger.finish(self.root/"invalidated.paf")

    def test_empty_recovery_is_not_a_native_completed_no_hit(self):
        merger = self.merger()
        source = self.root/"empty-recovery.paf"
        source.write_bytes(b"")
        with self.assertRaisesRegex(wa.ExperimentError,"empty no-hit cell"):
            merger.add_recovered(source,wa.sha256(source),"b",0,lambda raw:None)
        with self.assertRaises(wa.ExperimentError):
            merger.finish(self.root/"must-not-publish.paf")

    def test_wrong_part_or_changed_paf_cannot_poison_a_later_success(self):
        for i,kind in enumerate(("part","hash","trailing")):
            merger = nf.CellMerger(self.root/f"cells-{i}",{"a":{"length":8}},
                {"t1":{"length":8},"t2":{"length":8}},
                [{"part_index":j,"records":[{"name":n,"length":8}]} for j,n in enumerate(("t1","t2"))])
            receipt = self.receipt(self.root/f"bad-{i}.paf",paf(target="t2" if kind=="part" else "t1"))
            if kind=="hash":
                receipt["paf_sha256"] = "0"*64
            if kind=="trailing":
                Path(receipt["path"]).write_bytes(paf().rstrip(b"\n"))
                receipt["paf_sha256"] = wa.sha256(Path(receipt["path"]))
            with self.subTest(kind=kind),self.assertRaises(wa.ExperimentError):
                merger.add_native(receipt,["a"],part_index=0)
            with self.assertRaises(wa.ExperimentError):
                merger.finish(self.root/f"must-not-complete-{i}.paf")

    def test_changed_completed_shard_is_refused_before_output_promotion(self):
        merger = self.merger()
        merger.add_native(self.receipt(self.root/"source.paf",paf()),["a","b","c"])
        (self.root/"cells"/"0000-00000000.paf").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(wa.ExperimentError,"shard changed"):
            merger.finish(self.root/"tampered.pending.paf")

    def witness(self,raw,*,qlen,tlen,fragment=1):
        directory = self.root/"recovery"
        (directory/"native-recovery").mkdir(parents=True)
        source = directory/"stitched.paf"
        source.write_bytes(raw)
        ledger = directory/"native-recovery"/"recovered-states-000000.jsonl"
        ledger.write_text(json.dumps({"fragment_id":fragment,"chain_row":7,"anchor_count":3,
            "first_filter_status":"min_dp_max","path_score":{"query":"a"}})+"\n")
        result = {"unfiltered_paf":str(source),"unfiltered_sha256":wa.sha256(source),
                  "native_recovery":{"queries":[{"query":"a","recovered_states_sha256":wa.sha256(ledger)}]}}
        validator = lambda row:sr.validate_row(row,{"a":{"length":qlen}},{"t1":{"length":tlen}},{"a"},"risk")
        return directory,result,validator

    def test_witness_coalesces_eqx_into_native_M_and_keeps_filtered_candidates(self):
        length = wa.LIMIT+1
        raw = paf(mapq=255,cigar="100000000=1X168435455=",qlen=length,tlen=length,matches=length-1,block=length)
        directory,result,validator = self.witness(raw,qlen=length,tlen=length)
        witness = nf.long_operation_witness(directory,result,"a",validator)
        self.assertEqual(witness["first_overflow_witness"]["operation"],"M")
        self.assertEqual(witness["first_overflow_witness"]["logical_length"],length)
        self.assertEqual(witness["first_overflow_witness"]["original_chain_rows"],[7])
        self.assertFalse(witness["customer_root_cause_confirmed"])

    def test_short_query_can_supply_a_target_only_long_D_witness(self):
        tlen = wa.LIMIT+81
        raw = paf(mapq=255,cigar=f"40={wa.LIMIT}D1D40=",qlen=80,tlen=tlen,matches=80,block=tlen)
        directory,result,validator = self.witness(raw,qlen=80,tlen=tlen)
        witness = nf.long_operation_witness(directory,result,"a",validator)
        self.assertEqual(witness["first_overflow_witness"]["operation"],"D")
        self.assertEqual(witness["first_overflow_witness"]["logical_length"],wa.LIMIT+1)

    def test_long_query_without_overlong_supported_operation_is_not_recovery_evidence(self):
        qlen,tlen = 300000001,300000000
        raw = paf(mapq=255,cigar="200000000=1I100000000=",qlen=qlen,tlen=tlen,matches=tlen,block=qlen)
        directory,result,validator = self.witness(raw,qlen=qlen,tlen=tlen)
        with self.assertRaisesRegex(wa.ExperimentError,"lacks a supported overlong"):
            nf.long_operation_witness(directory,result,"a",validator)

    def test_overlong_path_without_original_chain_support_is_refused(self):
        length = wa.LIMIT+1
        raw = paf(mapq=255,cigar=f"{wa.LIMIT}=1=",qlen=length,tlen=length,matches=length,block=length)
        directory,result,validator = self.witness(raw,qlen=length,tlen=length,fragment=2)
        with self.assertRaisesRegex(wa.ExperimentError,"lacks a supported overlong"):
            nf.long_operation_witness(directory,result,"a",validator)

    def test_witness_ledger_mutation_is_not_hidden_by_initial_hash(self):
        length = wa.LIMIT+1
        raw = paf(mapq=255,cigar=f"{wa.LIMIT}=1=",qlen=length,tlen=length,matches=length,block=length)
        directory,result,validate = self.witness(raw,qlen=length,tlen=length)
        def mutate(row):
            validate(row)
            (directory/"native-recovery"/"recovered-states-000000.jsonl").write_text("changed\n")
        with self.assertRaisesRegex(wa.ExperimentError,"ledger changed during"):
            nf.long_operation_witness(directory,result,"a",mutate)


if __name__ == "__main__":
    unittest.main()
