"""Actual prepared Server dispatch/publication with explicitly scaled thresholds.

Native commands are real; patched timings test policy branches, not performance.
"""
from contextlib import ExitStack, redirect_stderr
import argparse
import io
import os
import random
import shutil
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adaptive_ordinary_controller as oc
import approximate_reference_cells as ap
import native_chain_state as nst
import native_first as nf
import proactive_publication as pub
import proactive_resume as pr
import server_alignment as sa
import proactive_reference_plan as pp
import recovery_publication as rp
import windowed_alignment as wa


class AutomaticOrdinaryServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY")
        if not cls.mm:raise unittest.SkipTest("explicit pinned mapper required; native companion is not needed")

    def fixture(self,root,*,mixed=False,weak=False):
        runtime=root/"runtime";runtime.mkdir()
        for name in sa.RUNTIME_FILES:shutil.copyfile(Path(sa.__file__).with_name(name),runtime/name)
        wa.write_json(runtime/sa.MANIFEST,{"schema":1,"status":"unvalidated_branch_runtime",
            "scope":"initial_reference_asm10_only","recovered_output_admission":"closed_pending_final_acceptance",
            "files_sha256":sa.runtime_files(runtime),"ordinary_output_admission":oc.POLICY,
            "approximate_output_admission":ap.POLICY})
        workspace=root/"workspace";(workspace/".prepare_lib").mkdir(parents=True);(workspace/"metadata").mkdir()
        run=workspace/"runs/query_vs_ref";run.mkdir(parents=True)
        rng=random.Random(2311302);sequence=bytes(rng.choices(b"ACGT",k=160000))
        target=root/"ref.fa";query=root/"query.fa";target.write_bytes(b">ref\n"+sequence+b"\n")
        rows=[b">q%02d\n"%n+(b"N"*30000 if (n==35 if weak is True else n in weak if weak else False) else sequence[n*100:n*100+30000])+b"\n" for n in range(40)]
        if mixed:
            rows.extend([b">long1\n"+sequence[10000:100000]+b"\n",
                         b">long2\n"+sequence[40000:130000].translate(wa.RC)[::-1]+b"\n"])
        query.write_bytes(b"".join(rows))
        args=argparse.Namespace(server_dir=workspace,run_dir=run,target=target,query=query,threads=1,preset="asm10",result="result.paf")
        return runtime,args

    def controls(self):
        stack=ExitStack();make_plan=pp.make_plan
        stack.enter_context(patch.dict(os.environ,{"PATH":str(Path(self.mm).parent)+os.pathsep+os.environ["PATH"]}))
        stack.enter_context(patch.object(pp,"MAX_OPERATION",64000))
        stack.enter_context(patch.object(rp,"PROACTIVE_QUERY_LIMIT",64000))
        stack.enter_context(patch.object(pp,"make_plan",side_effect=lambda catalog,policy=None:make_plan(catalog,policy or pp.WindowPolicy(20000,4000))))
        stack.enter_context(redirect_stderr(io.StringIO()))
        budget=oc.pilot.Budget(reference_bases=100000,workload_bases=1000000,long_ordinary_bases=20000,
            pilot_bases=128000,minimum_workload_multiple=4,case_seconds=20,total_seconds=120,minimum_speedup=2.0)
        stack.enter_context(patch.object(oc,"automatic_budget",return_value=budget))
        stack.enter_context(patch.object(ap,"MIN_REFERENCE_BASES",100000))
        stack.enter_context(patch.object(ap,"CORE_BASES",20000))
        stack.enter_context(patch.object(ap,"CONTEXT_BASES",4000))
        stack.enter_context(patch.object(nst,"validate_bundle",side_effect=AssertionError("automatic native/window path invoked companion")))
        original=oc.pilot._verify_case
        def timing(*args,**kwargs):
            result=original(*args,**kwargs);result["wall_seconds"]=10 if args[6] is None else 2;return result
        stack.enter_context(patch.object(oc.pilot,"_verify_case",side_effect=timing))
        return stack

    def test_prepared_ordinary_entry_filters_reviews_publishes_and_resumes_without_mapper(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory),weak=True)
            with self.controls():first=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(first["result_published"])
            self.assertEqual(first["initial_reference_policy"],oc.POLICY)
            self.assertEqual(first["ordinary_selected_filter"],"0.005")
            self.assertEqual(first["approximate_query_part_cells"],0)
            root=Path(first["attempt"])/"selective"
            report=pr.read_json(root/"proactive-candidate.json")
            self.assertEqual(report["routing_mode"],"adaptive_large_ordinary")
            self.assertEqual(list(report["ordinary_adaptive"]["reviews"]),["q35"])
            self.assertEqual(report["combination"]["original_cells"],40)
            self.assertEqual(report["combination"]["rows_by_query"]["q35"],0)
            self.assertFalse((root/"ordinary-native").exists())
            output=(args.run_dir/"result.paf").read_bytes()
            args.threads=2
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("complete automatic work remapped")):
                resumed=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(resumed["attempt_reused"])
            self.assertEqual((args.run_dir/"result.paf").read_bytes(),output)

    def test_mixed_ordinary_and_long_routes_keep_complete_matrix_and_default_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory),mixed=True)
            with self.controls():first=sa.run_reference(args,runtime_root=runtime)
            report=pr.read_json(Path(first["attempt"])/"selective/proactive-candidate.json")
            self.assertEqual(report["routing_mode"],"adaptive_large_reference")
            self.assertEqual(report["threshold_source"]["kind"],"completed_default_ordinary_pilot")
            self.assertEqual(first["ordinary_selected_filter"],"0.005")
            self.assertEqual(first["approximate_query_part_cells"],2)
            self.assertEqual(report["combination"]["original_cells"],42)
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("mixed complete sources remapped")):
                resumed=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(resumed["attempt_reused"])

    def test_small_ordinary_input_stays_on_original_native_fast_path(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory));args.query.write_bytes(b">small\n"+b"ACGT"*1000+b"\n")
            with self.controls(),patch.object(oc,"execute",side_effect=AssertionError("small input calibrated")):
                result=sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(result["status"],"native_complete_published")
            self.assertIsNone(result["ordinary_adaptive_policy"])
            self.assertFalse((Path(result["attempt"])/"selective/target.default.mmi").exists())

    def test_publication_rechecks_complete_controller_and_requires_runtime_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            with self.controls():result=sa.run_reference(args,runtime_root=runtime)
            attempt=Path(result["attempt"]);report=pr.read_json(attempt/"selective/proactive-candidate.json")
            closed=sa.validate_runtime(runtime);closed["ordinary_output_admission"]=None
            with self.controls(),patch.object(nf,"attempt",side_effect=AssertionError("publication mapped")):
                with self.assertRaisesRegex(wa.ExperimentError,"ordinary publication is not enabled"):
                    sa.publication_source(report,attempt,runtime=closed,runtime_root=runtime)
                marker=attempt/"selective/ordinary-adaptive/composition/composition.json"
                marker.rename(marker.with_suffix(".retained"))
                with self.assertRaisesRegex(wa.ExperimentError,"complete composition missing"):
                    sa.publication_source(report,attempt,runtime=sa.validate_runtime(runtime),runtime_root=runtime)
            self.assertFalse(marker.exists())

    def test_unfinished_controller_never_publishes_partial_paf(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            actual=oc.execute
            def partial(*a,**kw):return actual(*a,**kw,unit_limit=0)
            with self.controls(),patch.object(oc,"execute",side_effect=partial):
                with self.assertRaisesRegex(wa.ExperimentError,"ordinary continuation incomplete"):
                    sa.run_reference(args,runtime_root=runtime)
            self.assertFalse((args.run_dir/"result.paf").exists())
            with self.controls():finished=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(finished["attempt_reused"])
            self.assertTrue(finished["result_published"])

    def test_review_allowance_exhaustion_automatically_uses_default_complete_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory),weak=(34,35,36))
            with self.controls():result=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(result["result_published"])
            fallback=result["ordinary_default_continuation"]
            self.assertEqual(fallback["reason"],"cumulative_review_count_or_bases_exceeded")
            self.assertEqual(fallback["transition_queries"],["q34","q35","q36"])
            self.assertFalse(fallback["whole_assembly_restart"])
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("default transition remapped")):
                resumed=sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(resumed["ordinary_default_continuation"],fallback)

    def test_primary_server_work_keeps_native_batch_resources_while_calibration_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            with self.controls(),patch.object(nf,"attempt",wraps=nf.attempt) as commands:
                result=sa.run_reference(args,runtime_root=runtime)
            calibration=[c for c in commands.call_args_list if "calibration" in Path(c.args[3]).parts]
            primary=[c for c in commands.call_args_list if "units" in Path(c.args[3]).parts]
            self.assertTrue(calibration and primary)
            self.assertTrue(all(c.args[4].timeout<=20 and c.args[4].memory_gib==36 for c in calibration))
            self.assertTrue(all(c.args[4].timeout is None and c.args[4].memory_gib==0 and c.args[4].max_output_bytes is None for c in primary))
            state=pr.read_json(Path(result["attempt"])/"selective/ordinary-adaptive"/oc.STATE)
            self.assertEqual(state["identity"]["plan"]["unit_bases"],1000000000)

    def test_small_reference_declines_calibration_even_for_large_query_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory));args.target.write_bytes(args.target.read_bytes()[:80000]+b"\n")
            with self.controls(),patch.object(oc,"execute",side_effect=AssertionError("small reference calibrated")):
                result=sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(result["status"],"native_complete_published")
            self.assertFalse((Path(result["attempt"])/"selective/target.default.mmi").exists())

    def test_explicit_filter_is_preserved_without_automatic_parameter_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            (args.server_dir/"metadata/prepare_options.tsv").write_text("key\tvalue\nminimap_filter\t0.01\n")
            with self.controls(),patch.object(oc,"execute",side_effect=AssertionError("explicit filter replaced")):
                result=sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(result["status"],"native_complete_published")
            self.assertEqual(result["initial_reference_options"]["minimap_filter"],"0.01")

    def test_already_complete_default_native_group_is_not_discarded_to_calibrate(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            with self.controls(),patch.object(oc,"automatic_budget",return_value=oc.pilot.Budget()):
                first=sa.run_reference(args,runtime_root=runtime)
            self.assertEqual(first["status"],"native_complete_published")
            original=(args.run_dir/"result.paf").read_bytes()
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("completed native group remapped")),patch.object(oc,"execute",side_effect=AssertionError("completed native group recalibrated")):
                resumed=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(resumed["attempt_reused"])
            self.assertEqual((args.run_dir/"result.paf").read_bytes(),original)

    def test_complete_native_child_without_group_marker_is_adopted_not_recalibrated(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory))
            with self.controls(),patch.object(oc,"automatic_budget",return_value=oc.pilot.Budget()):
                first=sa.run_reference(args,runtime_root=runtime)
            marker=Path(first["attempt"])/"selective"/pr.STATE
            state=pr.read_json(marker);del state["stages"]["ordinary"];wa.write_json(marker,state)
            with self.controls(),patch.object(wa,"run_command",side_effect=AssertionError("complete native child remapped")):
                second=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(second["attempt_reused"])
            self.assertEqual(second["status"],"native_complete_published")
            self.assertIn("ordinary",pr.read_json(marker)["stages"])

    def test_existing_partition_checkpoint_takes_legacy_resume_path_not_new_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime,args=self.fixture(Path(directory));build=sa.pa.sr.build_default_index
            def with_partial(*a,**kw):
                index=build(*a,**kw);directory=a[2]/"ordinary-native";directory.mkdir()
                # Routing-only negative control: no native-success claim or PAF
                # is fabricated. The real partition verifier remains mandatory.
                wa.write_json(directory/sa.pa.opa.RECEIPT,{"schema":2,"kind":sa.pa.opa.KIND,"status":"failed_no_retry"})
                return index
            with self.controls(),patch.object(sa.pa.sr,"build_default_index",side_effect=with_partial),patch.object(oc,"execute",side_effect=AssertionError("partial native work recalibrated")),patch.object(sa.pa.opa,"attempt",side_effect=wa.ExperimentError("legacy-part-resume-reached")):
                with self.assertRaisesRegex(wa.ExperimentError,"legacy-part-resume-reached"):
                    sa.run_reference(args,runtime_root=runtime)
            self.assertFalse((args.run_dir/"result.paf").exists())
