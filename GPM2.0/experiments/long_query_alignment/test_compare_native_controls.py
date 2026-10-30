"""Deferred reporter/control definitions. Written only, NOT executed this phase."""
from __future__ import annotations

import argparse
from contextlib import contextmanager,redirect_stdout
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import compare_native_controls as comparison
import native_controls as controls
import native_evaluation as ne
import windowed_alignment as wa


def signature(mapq="60",target="exact",cigar="1000="):
    core = ("query","1000","0","1000","+",target,"1000","0","1000","1000","1000",mapq)
    tags = {"cg":"cg:Z:"+cigar,"NM":"NM:i:0","nn":"nn:i:0","ms":"ms:i:1000","cm":"cm:i:40",
            "s1":"s1:i:980","s2":"s2:i:0","tp":"tp:A:P","rl":"rl:i:0"}
    return core,tuple(tags.get(key) for key in ne.COMPARISON_TAGS)


class NativeControlReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tool,self.helper,self.manifest = self.root/"minimap2",self.root/"helper",self.root/"helper.json"
        self.tool.write_bytes(b"mock tool bytes; NEVER execute")
        self.helper.write_bytes(b"mock helper bytes; NEVER execute")
        self.manifest.write_text('{"mock":"not a native build receipt"}\n')
        self.bundle = {"path":str(self.helper),"sha256":wa.sha256(self.helper),
                       "manifest_path":str(self.manifest),"manifest_sha256":wa.sha256(self.manifest)}

    def args(self,cases=None):
        return argparse.Namespace(out=self.root/"new comparisons",minimap2=str(self.tool),native_state_bundle=self.root,
                                  case=cases,threads=2,timeout=180,memory_gib=0)

    @contextmanager
    def mocked_execution(self,run_case):
        fixtures = [(name,{"exact":b"ACGT"},b"ACGT") for name in controls.CASE_NAMES]
        with patch.object(comparison.shutil,"which",return_value=str(self.tool)), \
             patch.object(comparison.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(comparison.nst,"validate_bundle",return_value=self.bundle), \
             patch.object(comparison.controls,"fixtures",return_value=fixtures), \
             patch.object(comparison,"run_case",side_effect=run_case),redirect_stdout(io.StringIO()):
            yield

    def equal_case(self,name,targets,query,root,*args):
        root.mkdir()
        row = {"case":name,"status":"equal_on_compared_contract",
               "comparison":comparison.compare_signatures([signature()],[signature()])}
        wa.write_json(root/"comparison.json",row)
        return row

    def test_plan_only_never_creates_scans_fixture_data_or_starts_native_tools(self):
        out = self.root/"preview"
        with patch.object(comparison.shutil,"which",side_effect=AssertionError("tool discovery forbidden")), \
             patch.object(comparison.controls,"fixtures",side_effect=AssertionError("data generation forbidden")), \
             patch.object(comparison.nst,"validate_bundle",side_effect=AssertionError("binary access forbidden")), \
             redirect_stdout(io.StringIO()) as text:
            self.assertEqual(comparison.main(["--out",str(out)]),0)
        self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
        self.assertFalse(out.exists())

    def test_MAPQ_CIGAR_target_row_order_and_multiplicity_are_part_of_equality(self):
        original = [signature(),signature(target="other")]
        changes = [[signature(mapq="59"),original[1]],[signature(cigar="999=1X"),original[1]],
                   [signature(target="wrong"),original[1]],list(reversed(original)),original[:1],original+[original[1]]]
        for candidate in changes:
            with self.subTest(candidate=candidate):
                result = comparison.compare_signatures(original,candidate)
                self.assertFalse(result["equal"])
                self.assertGreater(result["different_rows"],0)
        self.assertTrue(comparison.compare_signatures(original,original)["equal"])
        self.assertIn("mapq",comparison.compare_signatures([signature()],[signature(mapq="59")])["differences"][0]["fields"])
        self.assertIn("tag:cg",comparison.compare_signatures([signature()],[signature(cigar="999=1X")])["differences"][0]["fields"])

    def test_native_tags_and_missing_signature_fields_cannot_be_ignored(self):
        original = signature()
        for index,name in enumerate(ne.COMPARISON_TAGS):
            candidate = (original[0],tuple("changed-tag" if i==index else value for i,value in enumerate(original[1])))
            result = comparison.compare_signatures([original],[candidate])
            self.assertFalse(result["equal"],name)
            self.assertIn("tag:"+name,result["differences"][0]["fields"])
        with self.assertRaisesRegex(wa.ExperimentError,"omitted required"):
            comparison.compare_signatures([original],[(original[0][:-1],original[1])])

    def test_difference_report_limit_never_turns_unreported_rows_into_equal(self):
        count = comparison.MAX_DIFFERENCES+5
        result = comparison.compare_signatures([signature()]*count,[signature(mapq="59")]*count)
        self.assertFalse(result["equal"])
        self.assertEqual(result["different_rows"],count)
        self.assertEqual(len(result["differences"]),comparison.MAX_DIFFERENCES)
        self.assertEqual(result["additional_differences_omitted"],5)
        self.assertFalse(result["AS_compared"])

    def test_subset_success_never_claims_the_full_native_matrix_or_production_acceptance(self):
        with self.mocked_execution(self.equal_case):
            result = comparison.experiment(self.args(["identity"]))
        self.assertTrue(result["requested_cases_equal"])
        self.assertFalse(result["full_native_matrix_covered"])
        self.assertFalse(result["full_native_matrix_equal"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["whole_query_dp_equivalence_certified"])
        self.assertTrue((self.args().out/"cases/identity/comparison.json").is_file())

    def test_complete_mock_matrix_keeps_all_named_case_receipts_but_does_not_promote_confidence(self):
        with self.mocked_execution(self.equal_case):
            result = comparison.experiment(self.args())
        self.assertTrue(result["full_native_matrix_equal"])
        self.assertEqual([row["case"] for row in result["cases"]],list(controls.CASE_NAMES))
        self.assertFalse(result["native_confidence_promoted"])
        self.assertFalse(result["actual_assertion_recovery_tested"])
        self.assertTrue(all((self.args().out/"cases"/name/"comparison.json").exists() for name in controls.CASE_NAMES))

    def test_refused_case_keeps_its_evidence_and_other_requested_cases_are_not_silently_skipped(self):
        seen = []
        def refused(name,targets,query,root,*args):
            seen.append(name)
            if name=="identity":
                root.mkdir()
                (root/"original.native.paf").write_bytes(b"retained mock failed-case evidence")
                wa.write_json(root/"comparison.json",{"case":name,"status":"refused_or_failed","error":"fixture refusal"})
                raise wa.ExperimentError("fixture refusal")
            return self.equal_case(name,targets,query,root,*args)
        with self.mocked_execution(refused):
            result = comparison.experiment(self.args(["identity","split_decoy"]))
        self.assertEqual(seen,["identity","split_decoy"])
        self.assertFalse(result["requested_cases_equal"])
        self.assertTrue((self.args().out/"cases/identity/original.native.paf").exists())
        self.assertFalse(result["production_ready"])

    def test_changed_tool_invalidates_attribution_instead_of_counting_a_mock_case_as_passed(self):
        def changed(*args):
            row = self.equal_case(*args)
            self.tool.write_bytes(b"changed mock executable")
            return row
        with self.mocked_execution(changed),self.assertRaisesRegex(wa.ExperimentError,"attribution invalidated"):
            comparison.experiment(self.args(["identity"]))
        result = json.loads((self.args().out/"native-controls.json").read_text())
        self.assertEqual(result["status"],"refused_or_failed")
        self.assertFalse(result["requested_cases_equal"])

    def test_cancelled_child_is_not_automatically_followed_by_the_next_case(self):
        seen = []
        def interrupted(name,targets,query,root,*args):
            seen.append(name)
            root.mkdir()
            try:
                signal.getsignal(signal.SIGINT)(signal.SIGINT,None)  # No actual signal/process.
            except KeyboardInterrupt:
                pass  # Models run_command retaining its interrupted-child receipt.
            wa.write_json(root/"comparison.json",{"case":name,"status":"refused_or_failed","error":"mock cancellation"})
            raise wa.ExperimentError("mock cancelled child")
        with self.mocked_execution(interrupted),self.assertRaises(KeyboardInterrupt):
            comparison.experiment(self.args(["identity","split_decoy"]))
        self.assertEqual(seen,["identity"])
        self.assertEqual(json.loads((self.args().out/"native-controls.json").read_text())["status"],"interrupted")

    def test_real_fixture_registry_preserves_the_eight_prior_controls_and_adds_a_large_pool(self):
        fixtures = controls.fixtures()
        self.assertEqual(tuple(row[0] for row in fixtures),controls.CASE_NAMES)
        self.assertEqual(len(fixtures),9)
        name,targets,query = fixtures[-1]
        self.assertEqual(name,"many_equal_split_targets")
        self.assertEqual(len(targets),70)
        self.assertEqual(len(query),200000)
        self.assertEqual(len({value for value in targets.values()}),1)
        self.assertNotEqual(next(iter(targets.values())),query)


if __name__=="__main__":
    unittest.main()
