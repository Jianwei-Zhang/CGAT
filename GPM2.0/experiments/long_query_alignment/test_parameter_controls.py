"""Deferred static-contract cases for normal-input parameter comparison.

Not executed during implementation per user instruction.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import compare_parameter_controls as pc
import windowed_alignment as wa


def paf(mapq=60,tp="P",cigar="4=1X3=",target="t",strand="+"):
    tag=f"\ttp:A:{tp}" if tp is not None else ""
    return f"q\t8\t0\t8\t{strand}\t{target}\t8\t0\t8\t7\t8\t{mapq}\tcg:Z:{cigar}{tag}\n"


class ParameterControlContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"x.paf"

    def summary(self,text):
        self.path.write_text(text)
        return pc.paf_summary(self.path)

    def test_summary_retains_relations_multiplicity_confidence_and_type(self):
        result=self.summary(paf()+paf(mapq=0,tp="S",target="u"))
        self.assertEqual(result["rows"],2)
        self.assertEqual(result["mapq_histogram"],{0:1,60:1})
        self.assertEqual(result["type_histogram"],{"P":1,"S":1})
        self.assertFalse(result["empty"])
        self.assertEqual(len(result["pair_strand_rows"]),2)

    def test_empty_output_is_explicit_not_success(self):
        result=self.summary("")
        self.assertTrue(result["empty"])
        baseline={"status":"success","summary":self.summary(paf()),"relations":{"x":[]}}
        candidate={"status":"success","summary":result,"relations":{}}
        comparison=pc.compare_contract(baseline,candidate)
        self.assertFalse(comparison["all_equal"])
        self.assertTrue(comparison["candidate_empty"])
        self.assertFalse(comparison["parameter_workaround_accepted"])

    def test_mapq_type_pair_or_cigar_difference_is_not_equal(self):
        baseline={"status":"success","summary":self.summary(paf()),"relations":{"same":1}}
        variants=(paf(mapq=255),paf(tp="S"),paf(target="u"),paf(cigar="3=1X4="))
        for raw in variants:
            candidate={"status":"success","summary":self.summary(raw),"relations":{"same":1}}
            with self.subTest(raw=raw):
                self.assertFalse(pc.compare_contract(baseline,candidate)["all_equal"])

    def test_execution_failure_cannot_become_parameter_candidate(self):
        baseline={"status":"success","summary":self.summary(paf()),"relations":{}}
        result=pc.compare_contract(baseline,{"status":"execution_or_parse_failure","error":"assertion"})
        self.assertFalse(result["all_equal"])
        self.assertFalse(result["parameter_workaround_accepted"])

    def test_malformed_coordinates_tags_and_cigar_fail_closed(self):
        cases=(paf().replace("\t0\t8\t+", "\t8\t0\t+"),
               paf()+"truncated", paf().replace("cg:Z:4=1X3=", "cg:Z:8M"),
               paf().replace("\ttp:A:P", "\tcg:Z:1=\ttp:A:P"))
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(wa.ExperimentError):
                    pc.paf_summary(self.path)


if __name__=="__main__":
    unittest.main()
