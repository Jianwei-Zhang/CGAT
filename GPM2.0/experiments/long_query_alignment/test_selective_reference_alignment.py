"""Deferred native-first branch-driver checks. Written, NOT run in this phase."""
from __future__ import annotations

import argparse
from contextlib import contextmanager,redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import selective_reference_alignment as sr
import windowed_alignment as wa

ASSERTION = b"minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs\x27 failed.\n"
MID_OCC = b"[M::mm_mapopt_update::118.735*2.42] mid_occ = 500\n"


def paf(query="short",length=8,mapq=60,cigar="8M",tags="\ttp:A:P\tAS:i:8"):
    return f"{query}\t{length}\t0\t{length}\t+\tt\t8\t0\t8\t8\t8\t{mapq}\tcg:Z:{cigar}{tags}\n".encode()


class SelectiveReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target,self.query = self.root/"target.fa",self.root/"query.fa"
        self.target.write_bytes(b">t\nACGTACGT\n")
        self.query.write_bytes(b">short description\r\nacgt\r\nACGT\r\n>long description\nACGTACGT\n")
        self.tool = self.root/"minimap2"
        self.tool.write_bytes(b"mock-only; never execute this file")

    def args(self,**updates):
        values = dict(target=self.target,query=self.query,out=self.root/"new experiment",
                      minimap2="minimap2",threads=2,timeout=60,memory_gib=0)
        values.update(updates)
        return argparse.Namespace(**values)

    @contextmanager
    def tools(self,run,*,version="2.31-r1302\n"):
        with patch.object(sr.shutil,"which",return_value=str(self.tool)), \
             patch.object(sr.subprocess,"check_output",return_value=version), \
             patch.object(wa,"run_command",side_effect=run) as command:
            yield command

    def execution(self,command,directory,name,*,rc=0,data=b"",stderr=MID_OCC):
        self.assertEqual(name,"native")
        Path(command[command.index("-o")+1]).write_bytes(data)
        (directory/f"{name}.stderr").write_bytes(stderr)
        return {"returncode":rc}

    def build_index(self,*args):
        index = self.root/"part.mmi"
        index.write_bytes(b"mock original part")
        return {"parts":[{"part_index":0,"path":str(index),"sha256":wa.sha256(index),
                          "records":[{"name":"t","length":8}]}],
                "index_policy":"original_default_no_I_override"}

    def assertion_run(self,command,directory,name,*args,**kwargs):
        self.assertTrue(kwargs["allow_failure"])
        names = [line[1:].split()[0] for line in Path(command[-1]).read_bytes().splitlines() if line.startswith(b">")]
        fail = b"long" in names
        return self.execution(command,directory,name,rc=-6 if fail else 0,
                              data=b"INVALID PARTIAL PAF; DO NOT REUSE" if fail else paf(),
                              stderr=MID_OCC+(ASSERTION if fail else b""))

    def test_recovered_row_span_and_unknown_confidence_guards(self):
        query,target = {"long":{"length":8}},{"t":{"length":8}}
        sr.validate_row(paf("long",mapq=255,cigar="8=",tags=""),query,target,{"long"},"risk")
        for raw in (paf("long"),paf("long",mapq=255,cigar="7=",tags=""),
                    paf("long",mapq=255,cigar="8=",tags="\tms:i:800"),
                    paf("long",mapq=255,cigar="8=",tags="\ttp:A:P")):
            with self.subTest(raw=raw),self.assertRaises(wa.ExperimentError):
                sr.validate_row(raw,query,target,{"long"},"risk")

    def test_plan_only_never_scans_creates_or_starts_program(self):
        output = self.root/"preview"
        argv = ["--target",str(self.target),"--query",str(self.query),"--out",str(output)]
        with patch.object(sr.nf,"RawFastaCatalog",side_effect=AssertionError("scan forbidden")), \
             patch.object(sr.subprocess,"check_output",side_effect=AssertionError("launch forbidden")), \
             redirect_stdout(io.StringIO()) as text:
            self.assertEqual(sr.main(argv),0)
        plan = json.loads(text.getvalue())
        self.assertEqual(plan["status"],"plan_only")
        self.assertTrue(plan["length_is_not_a_recovery_trigger"])
        self.assertFalse(output.exists())

    def test_native_success_preserves_entire_output_opaque_even_when_long_or_unpinned(self):
        native_data = b"native bytes are opaque here: no mandatory cg/AS rule\n"
        def mapping(command,directory,name,*args,**kwargs):
            self.assertEqual(command[1:5],["-c","-x","asm10","-t"])
            self.assertEqual(command[-2:],[str(self.target),str(self.query)])
            return self.execution(command,directory,name,data=native_data)
        with self.tools(mapping,version="future-native-version\n") as run, \
             patch.object(wa,"LIMIT",4), \
             patch.object(wa,"FastaStore",side_effect=AssertionError("native success needs no spool")), \
             patch.object(sr.nf,"RawFastaCatalog",side_effect=AssertionError("native success needs no catalog")), \
             patch.object(sr.ga,"experiment",side_effect=AssertionError("native success needs no windows")), \
             patch.object(sr.nst,"validate_bundle",side_effect=AssertionError("native success needs no companion")), \
             patch.object(sr,"build_default_index",side_effect=AssertionError("native success needs no saved MMI")):
            result = sr.experiment(self.args())
        self.assertEqual(run.call_count,1)
        self.assertEqual(result["routing_mode"],"native_complete_unchanged")
        self.assertFalse(result["companion_required"])
        self.assertEqual(result["native_evaluation"]["scope"],"unchanged_native_complete_output")
        self.assertEqual(Path(result["native_evaluation"]["path"]),self.args().out/"reference.candidate.experimental.paf")
        self.assertFalse((self.args().out/"reference.native-evaluated.experimental.paf").exists())
        self.assertEqual((self.args().out/"reference.candidate.experimental.paf").read_bytes(),native_data)
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["server_result_published"])
        self.assertFalse(any(self.args().out.glob("*.bases")))

    def test_empty_native_completed_output_does_not_turn_into_recovery(self):
        def mapping(command,directory,name,*args,**kwargs):
            return self.execution(command,directory,name,data=b"")
        with self.tools(mapping),patch.object(sr.nf,"RawFastaCatalog",side_effect=AssertionError("not recovery")):
            result = sr.experiment(self.args())
        self.assertEqual(result["status"],"experimental_candidate_only")
        self.assertEqual((self.args().out/"reference.candidate.experimental.paf").read_bytes(),b"")

    def test_oom_wrong_assertion_and_masked_zero_are_not_recovery_triggers(self):
        cases = [(-9,MID_OCC),(-6,MID_OCC+ASSERTION.replace(b"qoff ==",b"qoff !=")),(0,MID_OCC+ASSERTION)]
        for i,(rc,stderr) in enumerate(cases):
            def mapping(command,directory,name,*args,rc=rc,stderr=stderr,**kwargs):
                return self.execution(command,directory,name,rc=rc,data=b"partial",stderr=stderr)
            out = self.root/f"non-target-{i}"
            with self.subTest(rc=rc),self.tools(mapping) as run, \
                 patch.object(sr.nf,"RawFastaCatalog",side_effect=AssertionError("must not isolate")), \
                 patch.object(sr.nst,"validate_bundle",side_effect=AssertionError("must not recover")):
                with self.assertRaisesRegex(wa.ExperimentError,"outside the exact target assertion"):
                    sr.experiment(self.args(out=out))
            self.assertEqual(run.call_count,1)
            self.assertFalse((out/"reference.candidate.experimental.paf").exists())

    def test_recovery_rejects_unpinned_version_after_target_assertion(self):
        with self.tools(self.assertion_run,version="2.30-r1287\n") as run, \
             patch.object(sr.nf,"RawFastaCatalog",side_effect=AssertionError("wrong version must stop before catalog")):
            with self.assertRaisesRegex(wa.ExperimentError,"pinned to customer"):
                sr.experiment(self.args())
        self.assertEqual(run.call_count,1)

    def test_companion_lookup_occurs_only_after_actual_asserting_singleton(self):
        observed = []
        def companion(*args):
            observed.append(run.call_count)
            raise wa.ExperimentError("maintainer bundle required")
        with self.tools(self.assertion_run) as run,patch.object(sr,"build_default_index",side_effect=self.build_index), \
             patch.object(sr.nst,"validate_bundle",side_effect=companion), \
             patch.object(sr.ga,"experiment",side_effect=AssertionError("no helper; no recovery")):
            with self.assertRaisesRegex(wa.ExperimentError,"maintainer bundle"):
                sr.experiment(self.args())
        self.assertEqual(observed,[4])  # Original batch, part batch, short success, long assertion.
        self.assertFalse((self.args().out/"reference.candidate.experimental.paf").exists())
        self.assertTrue((self.args().out/"original-native"/"native.partial.paf").is_file())

    def test_isolated_native_and_recovery_results_combine_without_failed_partial_rows(self):
        common = "\tnn:i:0\tNM:i:0\tzg:i:1"
        recovered = paf("long",mapq=255,cigar="8=",tags=common+"\tzp:Z:experimental-native-selected-unknown-confidence")
        evaluated = paf("long",mapq=60,cigar="8=",tags=common+"\tzp:Z:experimental-native-evaluated\tcm:i:3\ts1:i:8\tms:i:8\trl:i:0\ttp:A:P\ts2:i:0")
        def guidance(options):
            options.out.mkdir()
            (options.out/"guided.experimental.paf").write_bytes(recovered)
            private = options.out/"native-evaluated.experimental.paf"
            private.write_bytes(evaluated)
            wa.write_json(options.out/"guidance.json",{"status":"mock for orchestration only"})
            return {"output_sha256":wa.sha256(options.out/"guided.experimental.paf"),
                    "native_recovery":{"native_evaluated_paf":str(private),"native_evaluated_sha256":wa.sha256(private)}}
        bundle = {"manifest_path":str(self.root/"mock-bundle"/"chain-state-helper.json")}
        with self.tools(self.assertion_run),patch.object(sr,"build_default_index",side_effect=self.build_index), \
             patch.object(sr.nst,"validate_bundle",return_value=bundle), \
             patch.object(sr.ga,"experiment",side_effect=guidance), \
             patch.object(sr.nf,"long_operation_witness",return_value={"status":"mocked witness; NOT alignment evidence"}):
            result = sr.experiment(self.args())
        self.assertEqual((self.args().out/"reference.candidate.experimental.paf").read_bytes(),paf()+recovered)
        self.assertEqual((self.args().out/"reference.native-evaluated.experimental.paf").read_bytes(),paf()+evaluated)
        self.assertTrue(result["native_evaluation"]["ordered_candidate_path_equal"])
        self.assertFalse(result["native_evaluation"]["whole_query_dp_equivalence_certified"])
        self.assertFalse(result["native_evaluation"]["native_confidence_promoted"])
        self.assertEqual(result["combination"]["native_cells"],1)
        self.assertEqual(result["combination"]["recovered_cells"],1)
        self.assertEqual(result["parts"][0]["assertion_leaves"],1)
        self.assertFalse(result["partial_PAF_reused"])
        self.assertFalse(result["global_mapq_restored"])
        self.assertFalse(result["production_ready"])

    def test_recovery_without_long_operation_evidence_cannot_publish_candidate(self):
        def guidance(options):
            options.out.mkdir()
            return {"status":"not sufficient"}
        bundle = {"manifest_path":str(self.root/"mock-bundle"/"chain-state-helper.json")}
        with self.tools(self.assertion_run),patch.object(sr,"build_default_index",side_effect=self.build_index), \
             patch.object(sr.nst,"validate_bundle",return_value=bundle), \
             patch.object(sr.ga,"experiment",side_effect=guidance), \
             patch.object(sr.nf,"long_operation_witness",side_effect=wa.ExperimentError("no overflow witness")):
            with self.assertRaisesRegex(wa.ExperimentError,"overflow witness"):
                sr.experiment(self.args())
        self.assertFalse((self.args().out/"reference.candidate.experimental.paf").exists())

    def test_nonreproducing_assertion_is_not_claimed_as_a_recovery(self):
        def mapping(command,directory,name,*args,**kwargs):
            failed = Path(command[-2])==self.target
            return self.execution(command,directory,name,rc=-6 if failed else 0,
                data=b"failed partial" if failed else paf()+paf("long"),stderr=MID_OCC+(ASSERTION if failed else b""))
        with self.tools(mapping),patch.object(sr,"build_default_index",side_effect=self.build_index), \
             patch.object(sr.nst,"validate_bundle",side_effect=AssertionError("no singleton failed")):
            with self.assertRaisesRegex(wa.ExperimentError,"did not reproduce"):
                sr.experiment(self.args())
        self.assertFalse((self.args().out/"reference.candidate.experimental.paf").exists())

    def test_input_mutation_after_native_success_is_not_published(self):
        def mapping(command,directory,name,*args,**kwargs):
            result = self.execution(command,directory,name,data=paf())
            self.query.write_bytes(self.query.read_bytes()+b"A\n")
            return result
        with self.tools(mapping),self.assertRaisesRegex(wa.ExperimentError,"changed"):
            sr.experiment(self.args())
        self.assertFalse((self.args().out/"reference.candidate.experimental.paf").exists())

    def test_default_index_builder_does_not_override_I_or_reference_order(self):
        target = argparse.Namespace(source=self.target,records={"t":{"length":8}},identity={"sha256":"r"*64})
        catalog = {"parts":[{"part_index":0,"path":"/parts/0.mmi","sha256":"p"*64,"records":[{"name":"t","length":8}]}]}
        with patch.object(wa,"run_command") as run,patch.object(sr.mic,"copy_parts",return_value=catalog):
            result = sr.build_default_index(str(self.tool),target,self.root,self.args(),"m"*64)
        command = run.call_args.args[0]
        self.assertNotIn("-I",command)
        self.assertEqual(command[-1],str(self.target))
        self.assertEqual(result["index_policy"],"original_default_no_I_override")
        self.assertEqual(result["parts"][0]["reference_sha256"],"r"*64)
        self.assertFalse(result["production_ready"])

    def test_shared_threshold_complete_pass_helper_is_retained_for_native_controls(self):
        log = self.root/"mapping.stderr"
        log.write_bytes(MID_OCC*2)
        self.assertEqual(sr.read_shared_mid_occ(log,2),500)
        log.write_bytes(MID_OCC+MID_OCC.replace(b"500",b"200"))
        with self.assertRaisesRegex(wa.ExperimentError,"inconsistent"):
            sr.read_shared_mid_occ(log,2)
        log.write_bytes(b"no threshold evidence\n")
        with self.assertRaises(wa.ExperimentError):
            sr.read_shared_mid_occ(log,1)

    def test_existing_or_prepared_workspace_is_not_overwritten(self):
        self.args().out.mkdir()
        with self.assertRaisesRegex(wa.ExperimentError,"fresh output"):
            sr.experiment(self.args())
        (self.root/"run_all.sh").write_text("existing workspace")
        with self.assertRaisesRegex(wa.ExperimentError,"prepared Server"):
            sr.experiment(self.args(out=self.root/"other"))


if __name__ == "__main__":
    unittest.main()
