"""Deferred checks for branch-only selective long-query mapping. Not run yet."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import selective_reference_alignment as sr
import windowed_alignment as wa


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

    def args(self,**updates):
        values = dict(target=self.target,query=self.query,out=self.root/"new experiment",
                      minimap2="minimap2",threads=2,timeout=60,memory_gib=0)
        values.update(updates)
        return argparse.Namespace(**values)

    def test_routing_threshold_is_strict_and_keeps_input_order(self):
        records = {"small":{"length":1},"boundary":{"length":wa.LIMIT},
                   "risk":{"length":wa.LIMIT+1},"tail":{"length":3}}
        ordinary,risk = sr.partition_records(records)
        self.assertEqual(ordinary,["small","boundary","tail"])
        self.assertEqual(risk,["risk"])
        self.assertEqual(records["boundary"]["length"],wa.LIMIT)
        for length in (0,-1,True,wa.INT32_MAX+1):
            with self.subTest(length=length),self.assertRaises(wa.ExperimentError):
                sr.partition_records({"q":{"length":length}})

    def test_raw_subsets_preserve_case_headers_wrapping_and_source(self):
        before = self.query.read_bytes()
        records = {"short":{"length":8},"long":{"length":8}}
        paths = sr.split_record_files(self.query,records,["short"],["long"],self.root,hashlib.sha256(before).hexdigest())
        self.assertEqual(paths["ordinary"].read_bytes(),b">short description\r\nacgt\r\nACGT\r\n")
        self.assertEqual(paths["risk"].read_bytes(),b">long description\nACGTACGT\n")
        self.assertEqual(self.query.read_bytes(),before)

    def test_invalid_partition_or_changed_query_is_not_accepted(self):
        records = {"short":{"length":8},"long":{"length":8}}
        for ordinary,risk in ((["short"],["short","long"]),(["short"],[])):
            with self.subTest(ordinary=ordinary),self.assertRaises(wa.ExperimentError):
                sr.split_record_files(self.query,records,ordinary,risk,self.root,"0"*64)
        with self.assertRaisesRegex(wa.ExperimentError,"bytes/order changed"):
            sr.split_record_files(self.query,records,["short"],["long"],self.root,"0"*64)

    def test_combination_preserves_normal_tags_and_does_not_fake_missing_coverage(self):
        ordinary,risk = self.root/"normal.paf",self.root/"risk.paf"
        normal = paf()
        recovered = paf(query="long",mapq=255,cigar="8=",tags="\tzp:Z:experimental-chain-guided")
        ordinary.write_bytes(normal); risk.write_bytes(recovered)
        records = {"long":{"length":8},"short":{"length":8},"unaligned":{"length":8}}
        output,report = sr.combine_candidates(self.root,records,{"t":{"length":8}},
                                              ["short","unaligned"],["long"],{"ordinary":ordinary,"risk":risk})
        self.assertEqual(output.read_bytes(),recovered+normal)
        self.assertEqual(report["queries_without_alignment"],["unaligned"])
        self.assertFalse(report["full_query_coverage_claimed"])
        self.assertFalse((self.root/"result.paf").exists())

    def test_row_route_span_and_risk_confidence_guards(self):
        query = {"short":{"length":8},"long":{"length":8}}
        target = {"t":{"length":8}}
        with self.assertRaises(wa.ExperimentError):
            sr.validate_row(paf(),query,target,{"long"},"risk")
        for row in (paf(query="long",mapq=60,cigar="8=",tags=""),
                    paf(query="long",mapq=255,cigar="8=",tags="\ts1:i:8"),
                    paf(query="long",mapq=255,cigar="7=",tags=""),
                    paf(query="long",mapq=255,cigar="8=",tags="")[:-1]):
            with self.subTest(row=row),self.assertRaises(wa.ExperimentError):
                sr.validate_row(row,query,target,{"long"},"risk")

    def test_plan_only_never_scans_creates_or_starts_program(self):
        output = self.root/"preview"
        argv = ["--target",str(self.target),"--query",str(self.query),"--out",str(output)]
        with patch.object(wa,"FastaStore",side_effect=AssertionError("scan forbidden")), \
             patch.object(sr.subprocess,"check_output",side_effect=AssertionError("launch forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as text:
            self.assertEqual(sr.main(argv),0)
        self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
        self.assertFalse(output.exists())

    def test_all_ordinary_route_uses_original_query_and_no_windowing(self):
        real_hash = wa.sha256
        def tool_or_file_hash(path):
            return "a"*64 if str(path) == "/tool/minimap2" else real_hash(path)
        def mapping(command,*args):
            self.assertEqual(command[1:5],["-c","-x","asm10","-t"])
            self.assertEqual(command[-2:],[str(self.target),str(self.query)])
            Path(command[command.index("-o")+1]).write_bytes(paf())
            return {"returncode":0}
        with patch.object(sr.shutil,"which",return_value="/tool/minimap2"), \
             patch.object(sr.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(wa,"sha256",side_effect=tool_or_file_hash), \
             patch.object(wa,"run_command",side_effect=mapping), \
             patch.object(sr.ga,"experiment",side_effect=AssertionError("no windows for ordinary records")):
            result = sr.experiment(self.args())
        self.assertEqual(result["status"],"experimental_candidate_only")
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["server_result_published"])

    def test_multipart_reference_is_not_silently_reindexed(self):
        class Store:
            def __init__(inner,source,spool):
                inner.identity = {"sha256":"a"*64}
                inner.records = {"t":{"length":sr.DEFAULT_INDEX_BASES+1}} if source == self.target else {"long":{"length":wa.LIMIT+1}}
            def close(inner): pass
        with patch.object(wa,"FastaStore",Store), \
             patch.object(sr.shutil,"which",return_value="/tool/minimap2"), \
             patch.object(sr.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(wa,"sha256",return_value="a"*64), \
             patch.object(wa,"run_command",side_effect=AssertionError("mapping must not start")), \
             patch.object(sr.ga,"experiment",side_effect=AssertionError("single-index prototype must not start")):
            with self.assertRaisesRegex(wa.ExperimentError,"multipart-reference"):
                sr.experiment(self.args())
        report = json.loads((self.args().out/"selective-reference.json").read_text())
        self.assertEqual(report["status"],"refused_or_failed")
        self.assertFalse((self.args().out/"reference.candidate.experimental.paf").exists())

    def test_existing_or_prepared_workspace_is_not_overwritten(self):
        self.args().out.mkdir()
        with self.assertRaisesRegex(wa.ExperimentError,"fresh output"):
            sr.experiment(self.args())
        (self.root/"run_all.sh").write_text("existing workspace")
        with self.assertRaisesRegex(wa.ExperimentError,"prepared Server"):
            sr.experiment(self.args(out=self.root/"other"))


if __name__ == "__main__":
    unittest.main()
