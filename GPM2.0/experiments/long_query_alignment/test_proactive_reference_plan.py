"""No mapper needed: preflight routing, exact record partitioning and I/O bounds."""
from contextlib import redirect_stdout
from dataclasses import replace
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import proactive_reference_plan as p


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "queries.fa"
        self.limit = patch.object(p, "MAX_OPERATION", 64)
        self.limit.start(); self.addCleanup(self.limit.stop)
        self.policy = p.WindowPolicy(20, 3)

    def fixture(self, lengths=(12, 65, 9), compressed=False):
        raw = b"\r\n" + b"".join(b">q%d description \xe4\xb8\xad\r\n" % i + b"aCgTN"*(n//5)
                                + b"A"*(n%5) + b"\r\n" for i,n in enumerate(lengths))
        self.source.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
        return raw

    def prepare(self):
        catalog = p.scan_query(self.source)
        plan = p.make_plan(catalog, self.policy)
        result = p.materialize(catalog, plan, self.root / "groups")
        return catalog, plan, result

    def test_one_scan_combines_encoded_hash_lengths_offsets_and_record_hashes(self):
        raw = self.fixture()
        c = p.scan_query(self.source)
        self.assertEqual(c.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(c.physical_bytes_read, len(raw))
        self.assertEqual([r.length for r in c.records], [12,65,9])
        self.assertEqual(c.records[0].byte_start, 0)
        self.assertEqual(c.records[-1].byte_end, len(raw))
        for r in c.records:
            self.assertEqual(r.sha256, hashlib.sha256(raw[r.byte_start:r.byte_end]).hexdigest())

    def test_gzip_single_physical_scan_keeps_decoded_ranges_and_encoded_identity(self):
        raw = self.fixture(compressed=True)
        c = p.scan_query(self.source)
        self.assertEqual(c.encoding, "gzip")
        self.assertEqual(c.physical_bytes_read, self.source.stat().st_size)
        self.assertEqual(c.source_sha256, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(c.decoded_bytes, len(raw))
        for r in c.records:
            self.assertEqual(r.sha256, hashlib.sha256(raw[r.byte_start:r.byte_end]).hexdigest())

    def test_mixed_grouping_reads_source_one_more_time_not_per_long_record(self):
        raw = self.fixture((65,5,70,10,80))
        c,plan,result = self.prepare()
        self.assertEqual(plan["native_queries"], ["q1","q3"])
        self.assertEqual(plan["long_queries"], ["q0","q2","q4"])
        self.assertEqual(result["decoded_bytes_written"], len(raw))
        self.assertEqual(result["query_materialization_physical_bytes_read"], len(raw))
        self.assertEqual(len(result["groups"]), 4)
        for group in result["groups"]:
            expected = b"".join(raw[r.byte_start:r.byte_end] for r in c.records if r.name in group["queries"])
            self.assertEqual(Path(group["path"]).read_bytes(), expected)
            self.assertEqual(group["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertFalse(result["analysis_started"])
        self.assertFalse(result["result_published"])
        self.assertTrue(result["all_original_records_accounted"])

    def test_gzip_materialization_decompresses_once_for_all_groups(self):
        raw = self.fixture((65,5,70,10,80), compressed=True)
        c,plan,result = self.prepare()
        self.assertEqual(result["query_materialization_physical_bytes_read"], c.physical_bytes_read)
        self.assertEqual(result["decoded_bytes_written"], len(raw))
        for group in result["groups"]:
            expected = b"".join(raw[r.byte_start:r.byte_end] for r in c.records if r.name in group["queries"])
            self.assertEqual(Path(group["path"]).read_bytes(), expected)

    def test_normal_only_uses_original_compressed_input_without_a_second_read(self):
        self.fixture((10,20,64), compressed=True)
        c = p.scan_query(self.source);plan = p.make_plan(c, self.policy)
        with patch.object(p,"decoded_input",side_effect=AssertionError("no second source scan")):
            report=p.materialize(c,plan,self.root/"groups")
        self.assertEqual(report["groups"][0]["path"], str(self.source.resolve()))
        self.assertEqual(report["groups"][0]["encoding"], "gzip")
        self.assertEqual(report["decoded_bytes_written"], 0)
        self.assertEqual(report["query_materialization_physical_bytes_read"], 0)
        self.assertEqual(plan["additional_materialization_passes"], 0)
        self.assertFalse(plan["requires_shared_original_index_context"])

    def test_single_long_query_reuses_original_file_and_requires_metadata_only_context(self):
        self.fixture((65,))
        c,plan,result = self.prepare()
        self.assertEqual(result["groups"][0]["path"],str(self.source.resolve()))
        self.assertEqual(result["decoded_bytes_written"],0)
        self.assertEqual(plan["threshold_source_plan"],"first_index_part_metadata_only_no_query_alignment")
        self.assertEqual(plan["assertion_reproduction_alignments"],0)

    def test_single_long_gzip_is_decoded_once_for_the_plain_fasta_recovery_engine(self):
        raw=self.fixture((65,),compressed=True)
        c,plan,result=self.prepare()
        self.assertEqual(plan["additional_materialization_passes"],1)
        self.assertEqual(result["groups"][0]["encoding"],"plain")
        self.assertEqual(Path(result["groups"][0]["path"]).read_bytes(),raw)
        self.assertEqual(result["query_materialization_physical_bytes_read"],c.physical_bytes_read)

    def test_all_long_queries_no_empty_ordinary_group(self):
        self.fixture((65,80))
        c,plan,result = self.prepare()
        self.assertEqual(plan["ordinary_batch_count"],0)
        self.assertTrue(all(g["route"]=="long_query" for g in result["groups"]))
        self.assertEqual(len(result["groups"]),2)

    def test_exact_limit_is_native_and_next_base_routed(self):
        self.fixture((63,64,65))
        c,plan,result = self.prepare()
        self.assertEqual(plan["native_queries"],["q0","q1"])
        self.assertEqual(plan["long_queries"],["q2"])
        self.assertFalse(plan["all_failures_predicted"])
        self.assertIn("long_target_only_deletion",plan["scope_exclusions"])
        for field in ("whole_input_trial_alignments","bisection_alignments","assertion_reproduction_alignments"):
            self.assertEqual(plan[field],0)

    def test_window_work_accounts_for_context_without_owning_bases_twice(self):
        self.assertEqual(p.window_work(65,self.policy),{
            "windows":4,"core_bases":65,"context_overlap_bases":18,"window_query_bases":83})

    def test_long_unwrapped_line_is_streamed_with_bounded_reads(self):
        self.source.write_bytes(b">q0\n"+b"ACGT"*400000+b"\n")
        c=p.scan_query(self.source)
        self.assertEqual(c.records[0].length,1600000)
        self.assertEqual(c.physical_bytes_read,self.source.stat().st_size)

    def test_duplicate_empty_invalid_sequence_and_overlong_header_refused(self):
        for raw in (b"",b">q\n",b">q\nA\n>q\nC\n",b">q\nAC GT\n",b"ACGT\n",b">\nA\n",b">q\n>r\nA\n",b">"+b"q"*p.CHUNK+b"\nA\n"):
            with self.subTest(length=len(raw)):
                self.source.write_bytes(raw)
                with self.assertRaises(p.PlanError):p.scan_query(self.source)

    def test_truncated_gzip_refused(self):
        self.fixture(compressed=True)
        self.source.write_bytes(self.source.read_bytes()[:-5])
        with self.assertRaises((EOFError,OSError,p.PlanError)):p.scan_query(self.source)

    def test_record_count_and_coordinate_budget_checked(self):
        self.fixture((5,10))
        with patch.object(p,"MAX_RECORDS",1),self.assertRaisesRegex(p.PlanError,"budget"):
            p.scan_query(self.source)
        with patch.object(p,"MAX_COORDINATE",6),self.assertRaisesRegex(p.PlanError,"coordinates"):
            p.scan_query(self.source)

    def test_unknown_mutation_after_scan_is_refused_before_any_output(self):
        self.fixture();c=p.scan_query(self.source);plan=p.make_plan(c,self.policy)
        self.source.write_bytes(self.source.read_bytes()+b"A\n")
        with self.assertRaisesRegex(p.PlanError,"changed"):
            p.materialize(c,plan,self.root/"groups")
        self.assertFalse((self.root/"groups").exists())

    def test_tampered_plan_is_not_an_execution_switch(self):
        self.fixture();c=p.scan_query(self.source);plan=p.make_plan(c,self.policy)
        plan["long_queries"]=[]
        with self.assertRaisesRegex(p.PlanError,"plan changed"):
            p.materialize(c,plan,self.root/"groups")
        self.assertFalse((self.root/"groups").exists())

    def test_record_digest_corruption_never_marks_groups_complete(self):
        self.fixture();c=p.scan_query(self.source)
        c=replace(c,records=(replace(c.records[0],sha256="0"*64),*c.records[1:]))
        with self.assertRaisesRegex(p.PlanError,"record changed"):
            p.materialize(c,p.make_plan(c,self.policy),self.root/"groups")
        self.assertFalse((self.root/"groups/groups.json").exists())
        self.assertEqual(json.loads((self.root/"groups/failure.json").read_bytes())["status"],"refused_or_failed")

    def test_cancellation_leaves_no_completion_marker(self):
        self.fixture();c=p.scan_query(self.source);plan=p.make_plan(c,self.policy)
        with patch.object(p,"decoded_input",side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            p.materialize(c,plan,self.root/"groups")
        self.assertFalse((self.root/"groups/groups.json").exists())
        self.assertTrue((self.root/"groups/failure.json").exists())

    def test_existing_output_and_symlink_preserved(self):
        self.fixture();c=p.scan_query(self.source);plan=p.make_plan(c,self.policy)
        dest=self.root/"groups";dest.symlink_to(self.source)
        with self.assertRaisesRegex(p.PlanError,"fresh"):
            p.materialize(c,plan,dest)
        self.assertTrue(dest.is_symlink())

    def test_prepared_workspace_is_not_a_prototype_output(self):
        self.fixture();c=p.scan_query(self.source);plan=p.make_plan(c,self.policy)
        (self.root/".prepare_lib").mkdir()
        with self.assertRaisesRegex(p.PlanError,"prepared workspace"):
            p.materialize(c,plan,self.root/"groups")

    def test_invalid_window_policy(self):
        self.fixture();c=p.scan_query(self.source)
        for policy in (p.WindowPolicy(0,0),p.WindowPolicy(20,20),p.WindowPolicy(64,1)):
            with self.assertRaises(p.PlanError):p.make_plan(c,policy)

    def test_default_cli_does_not_read_query_or_create_output(self):
        with patch.object(p,"scan_query",side_effect=AssertionError("not executed")),redirect_stdout(io.StringIO()) as text:
            code=p.main(["--query","/missing-query.fa","--out",str(self.root/"missing-output")])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
        self.assertFalse((self.root/"missing-output").exists())


if __name__ == "__main__":unittest.main()
