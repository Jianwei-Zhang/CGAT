"""Deferred paired-view checks. Only written; NOT executed or scientific evidence."""
from __future__ import annotations

from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from unittest.mock import patch

import compare_grt as cg
import native_evaluation as ne
import native_first as nf
import selective_reference_alignment as sr
import windowed_alignment as wa


def row(query="recovered",target="t",*,mapq=255,private=False):
    fields = [query,"1000","0","1000","+",target,"1000","0","1000","1000","1000",str(mapq)]
    tags = ["cg:Z:1000=","nn:i:0","NM:i:0","zg:i:1"]
    if private:
        tags += ["zp:Z:experimental-native-evaluated","cm:i:40","s1:i:980","ms:i:1000","rl:i:0","tp:A:P","s2:i:0"]
    else:
        tags += ["zp:Z:experimental-native-selected-unknown-confidence"]
    return ("\t".join(fields+tags)+"\n").encode()


class NativeEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.public,self.private = self.root/"public.paf",self.root/"private.paf"
        self.public.write_bytes(row())
        self.private.write_bytes(row(mapq=60,private=True))
        self.queries = {"recovered":{"length":1000},"native":{"length":1000}}
        self.targets = {"t":{"length":1000},"u":{"length":1000}}

    def validator(self,raw):
        return sr.validate_row(raw,self.queries,self.targets,{"recovered"},"risk")

    def pair(self,**updates):
        values = dict(public_sha256=wa.sha256(self.public),evaluated_sha256=wa.sha256(self.private),validator=self.validator)
        values.update(updates)
        return ne.validate_pair(self.public,self.private,**values)

    def merger(self):
        parts = [{"part_index":i,"records":[{"name":name,"length":1000}]} for i,name in enumerate(("t","u"))]
        merger = nf.CellMerger(self.root/"cells",self.queries,self.targets,parts)
        native = row("native",mapq=17).replace(b"\tzp:Z:experimental-native-selected-unknown-confidence",b"\tAS:i:971\ttp:A:P")
        first,second = self.root/"native-first.paf",self.root/"native-second.paf"
        first.write_bytes(native)
        second.write_bytes(native.replace(b"\tt\t",b"\tu\t"))
        for path,names,index in ((first,["native"],0),(second,["recovered","native"],1)):
            receipt = {"status":"native_success","paf_usable":True,"path":str(path),"paf_sha256":wa.sha256(path)}
            merger.add_native(receipt,names,part_index=index)
        return merger,native

    def register(self,merger,*,paired=True):
        options = {"native_evaluated":{"path":str(self.private),"sha256":wa.sha256(self.private)}} if paired else {}
        return merger.add_recovered(self.public,wa.sha256(self.public),"recovered",0,self.validator,**options)

    def test_pair_keeps_unknown_public_but_binds_known_private_metadata_without_promotion(self):
        result = self.pair()
        self.assertTrue(result["ordered_candidate_path_equal"])
        self.assertEqual(result["mapq_histogram"],{"60":1})
        self.assertFalse(result["AS_reconstructed"])
        self.assertFalse(result["whole_query_dp_equivalence_certified"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(self.public.read_bytes(),row())

    def test_different_candidate_core_CIGAR_statistics_chain_or_order_is_refused(self):
        original = self.private.read_bytes()
        changes = [(b"recovered\t",b"native\t"),(b"\t+\t",b"\t-\t"),(b"cg:Z:1000=",b"cg:Z:999=1X"),
                   (b"nn:i:0",b"nn:i:1"),(b"NM:i:0",b"NM:i:1"),(b"zg:i:1",b"zg:i:2")]
        for before,after in changes:
            self.private.write_bytes(original.replace(before,after))
            with self.subTest(change=before),self.assertRaises(wa.ExperimentError):
                self.pair()

    def test_private_AS_guess_extra_tags_or_unknown_confidence_is_refused(self):
        original = self.private.read_bytes()
        for changed in (original.rstrip(b"\n")+b"\tAS:i:1000\n",original.replace(b"\t60\t",b"\t255\t"),
                        original.rstrip(b"\n")+b"\tzz:Z:unknown\n",original.replace(b"\tms:i:1000",b"")):
            self.private.write_bytes(changed)
            with self.subTest(changed=changed[-50:]),self.assertRaises(wa.ExperimentError):
                self.pair()

    def test_private_primary_zero_and_secondary_zero_are_not_confused_with_unknown(self):
        original = self.private.read_bytes()
        self.private.write_bytes(original.replace(b"\t60\t",b"\t0\t"))
        self.assertEqual(self.pair()["mapq_histogram"],{"0":1})
        secondary = original.replace(b"\t60\t",b"\t0\t").replace(b"tp:A:P",b"tp:A:S").replace(b"\ts2:i:0",b"")
        self.private.write_bytes(secondary)
        self.assertEqual(self.pair()["mapq_histogram"],{"0":1})
        nonzero_fields = secondary.split(b"\t")
        nonzero_fields[11] = b"60"
        for bad in (b"\t".join(nonzero_fields),secondary.rstrip(b"\n")+b"\ts2:i:0\n",
                    original.replace(b"\ts2:i:0",b"")):
            self.private.write_bytes(bad)
            with self.assertRaises(wa.ExperimentError):
                self.pair()

    def test_duplicate_tags_invalid_counts_and_split_flags_are_refused(self):
        original = self.private.read_bytes()
        for bad in (original.rstrip(b"\n")+b"\tNM:i:0\n",original.replace(b"cm:i:40",b"cm:i:2"),
                    original.replace(b"rl:i:0",b"rl:i:1001"),original.replace(b"ms:i:1000",b"ms:i:-1"),
                    original.rstrip(b"\n")+b"\tzd:i:4\n",original.replace(b"cm:i:40",b"cm:i:"+b"9"*5000)):
            self.private.write_bytes(bad)
            with self.assertRaises(wa.ExperimentError):
                self.pair()

    def test_no_extra_missing_or_truncated_private_rows(self):
        original = self.private.read_bytes()
        for bad in (b"",original+original,original.rstrip(b"\n")):
            self.private.write_bytes(bad)
            with self.assertRaises(wa.ExperimentError):
                self.pair()

    def test_exact_producer_hashes_and_unchanged_files_are_required(self):
        with self.assertRaises(wa.ExperimentError):
            self.pair(evaluated_sha256="0"*64)
        with self.assertRaises(wa.ExperimentError):
            self.pair(public_sha256="missing")
        def mutate(raw):
            self.validator(raw)
            self.private.write_bytes(self.private.read_bytes()+b"changed")
        with self.assertRaises(wa.ExperimentError):
            self.pair(validator=mutate)

    def test_comparison_signature_includes_MAPQ_and_native_metadata_not_AS_claims(self):
        baseline = self.root/"baseline.paf"
        baseline.write_bytes(self.private.read_bytes().rstrip(b"\n")+b"\tAS:i:1000\n")
        self.assertEqual(ne.comparison_signature(baseline),ne.comparison_signature(self.private))
        baseline.write_bytes(self.private.read_bytes().replace(b"\t60\t",b"\t59\t"))
        self.assertNotEqual(ne.comparison_signature(baseline),ne.comparison_signature(self.private))
        baseline.write_bytes(self.private.read_bytes().replace(b"s1:i:980",b"s1:i:979"))
        self.assertNotEqual(ne.comparison_signature(baseline),ne.comparison_signature(self.private))

    def test_complete_private_view_reuses_native_shards_and_only_substitutes_recovered_cell(self):
        merger,native = self.merger()
        self.register(merger)
        shards = set((self.root/"cells").iterdir())
        public,private = self.root/"combined-public.paf",self.root/"combined-private.paf"
        public_report = merger.finish(public)
        private_report = merger.finish(private,native_evaluated=True)
        suffix = native+native.replace(b"\tt\t",b"\tu\t")
        self.assertEqual(public.read_bytes(),self.public.read_bytes()+suffix)
        self.assertEqual(private.read_bytes(),self.private.read_bytes()+suffix)
        self.assertEqual(set((self.root/"cells").iterdir()),shards)
        self.assertEqual(public_report["rows_by_query"],private_report["rows_by_query"])
        self.assertEqual(private_report["candidate_view"],"private_native_evaluation")
        self.assertEqual(len(private_report["evaluated_replacements"]),1)
        self.assertFalse(private_report["native_confidence_promoted"])

    def test_missing_pair_cannot_silently_reuse_unknown_public_confidence(self):
        merger,_ = self.merger()
        self.register(merger,paired=False)
        with self.assertRaisesRegex(wa.ExperimentError,"lacks a paired"):
            merger.finish(self.root/"must-not-complete.paf",native_evaluated=True)
        self.assertFalse((self.root/"must-not-complete.paf").exists())
        merger.finish(self.root/"public-only.paf")

    def test_private_file_mutation_after_pair_binding_is_rejected_at_final_assembly(self):
        merger,_ = self.merger()
        self.register(merger)
        self.private.write_bytes(self.private.read_bytes().replace(b"\t60\t",b"\t59\t"))
        with self.assertRaisesRegex(wa.ExperimentError,"shard changed"):
            merger.finish(self.root/"private.pending.paf",native_evaluated=True)
        with self.assertRaises(wa.ExperimentError):
            merger.finish(self.root/"must-not-retry.paf")

    def test_invalid_pair_invalidates_the_whole_assembly(self):
        merger,_ = self.merger()
        self.private.write_bytes(self.private.read_bytes().replace(b"\t60\t",b"\t255\t"))
        with self.assertRaises(wa.ExperimentError):
            self.register(merger)
        with self.assertRaises(wa.ExperimentError):
            merger.finish(self.root/"must-not-complete.paf")

    def downstream_bridge_case(self,*,native_has_hits):
        target,query,tool,log = self.root/"ref.fa",self.root/"query.fa",self.root/"minimap2",self.root/"baseline.stderr"
        target.write_bytes(b">t\n"+b"A"*1000+b"\n")
        query.write_bytes(b">recovered\n"+b"A"*1000+b"\n")
        tool.write_bytes(b"mock only; never execute")
        log.write_bytes(b"[M::mm_mapopt_update::1*1] mid_occ = 500\n")
        def index(*args):
            path = self.root/"part.mmi"
            path.write_bytes(b"mock original MMI part")
            return {"parts":[{"part_index":0,"path":str(path),"sha256":wa.sha256(path),"records":[{"name":"t","length":1000}]}]}
        def native(mm,target,query,directory,args,**kwargs):
            directory.mkdir()
            path = directory/"native.complete.paf"
            path.write_bytes(self.private.read_bytes() if native_has_hits else b"")
            return {"status":"native_success","paf_usable":True,"path":str(path),"paf_sha256":wa.sha256(path)}
        def guided(options):
            self.assertEqual(options.window_candidate_policy,"all_chains_pool")
            self.assertEqual(options.index_context["mid_occ"],500)
            options.out.mkdir()
            public,private = options.out/"guided.experimental.paf",options.out/"private.paf"
            public.write_bytes(self.public.read_bytes()); private.write_bytes(self.private.read_bytes())
            wa.write_json(options.out/"guidance.json",{"mock":True})
            return {"output_sha256":wa.sha256(public),"native_recovery":{
                "native_evaluated_paf":str(private),"native_evaluated_sha256":wa.sha256(private)}}
        with patch.object(cg.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(cg.sr,"build_default_index",side_effect=index), \
             patch.object(cg.nf,"attempt",side_effect=native),patch.object(cg.ga,"experiment",side_effect=guided) as recovery:
            result = cg.native_bridge_candidate(str(tool),target,query,self.root/"bridge",log,{"manifest_path":str(self.root/"bundle.json")})
        self.assertEqual(recovery.call_count,int(native_has_hits))
        self.assertEqual(Path(result["native_evaluated_paf"]).read_bytes(),self.private.read_bytes() if native_has_hits else b"")
        self.assertEqual(Path(result["public_paf"]).read_bytes(),self.public.read_bytes() if native_has_hits else b"")
        self.assertFalse(result["actual_assertion_recovery_tested"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["native_confidence_promoted"])

    def test_downstream_mode_forces_recovery_on_small_native_success_not_fast_path_only(self):
        self.downstream_bridge_case(native_has_hits=True)

    def test_downstream_mode_keeps_actual_native_completed_no_hit_without_fake_recovery(self):
        self.downstream_bridge_case(native_has_hits=False)

    def test_native_downstream_no_hit_fixture_is_separate_from_legacy_cases(self):
        legacy = cg.fixtures()
        native = cg.fixtures(include_no_hit=True)
        self.assertEqual(len(native),len(legacy)+1)
        self.assertEqual(native[:-1],legacy)
        self.assertEqual(native[-1][0],"unmapped_query_member")
        self.assertEqual(native[-1][2]["unmapped"],b"N"*2000)

    def native_cli_case(self,*,metadata_equal):
        server,tool = self.root/"server",self.root/"minimap2"
        (server/"tools").mkdir(parents=True)
        (server/"prepare.sh").write_text("mock only; never execute")
        tool.write_bytes(b"mock only; never execute")
        output = self.root/"cli-comparison"
        def mapping(command,*args,**kwargs):
            Path(command[command.index("-o")+1]).write_bytes(row(mapq=60,private=True))
            return {"returncode":0}
        def bridge(mm,target,query,directory,*args):
            directory.mkdir()
            public,private = directory/"public.paf",directory/"private.paf"
            public.write_bytes(row())
            private.write_bytes(row(mapq=60 if metadata_equal else 59,private=True))
            wa.write_json(directory/"native-bridge-downstream.json",{"mock":True,"production_ready":False})
            return {"public_paf":str(public),"native_evaluated_paf":str(private)}
        cases = [("mock_only_not_scientific_evidence",{"t":b"A"*1000},{"recovered":b"A"*1000},None)]
        argv = ["compare_grt.py","--native-bridge","--minimap2",str(tool),"--server-dir",str(server),"--out",str(output)]
        with patch("sys.argv",argv),patch.object(cg.nst,"validate_bundle",return_value={"mock":True}), \
             patch.object(cg.shutil,"which",return_value=str(tool)), \
             patch.object(cg.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(cg,"fixtures",return_value=cases),patch.object(cg.wa,"run_command",side_effect=mapping), \
             patch.object(cg,"native_bridge_candidate",side_effect=bridge),patch.object(cg,"run_grt",return_value="mock"), \
             patch.object(cg,"compare",return_value={"all_checks_equal":True,"checks":[]}),redirect_stdout(io.StringIO()):
            code = cg.main()
        receipt = json.loads((output/"comparison.json").read_text())
        self.assertEqual(receipt["cases"][0]["coordinate_and_downstream_equal"],True)
        self.assertEqual(receipt["native_bridge_requested_cases_equal"],metadata_equal)
        self.assertFalse(receipt["production_ready"])
        return code

    def test_native_cli_returns_nonzero_on_MAPQ_difference_despite_equal_geometry_and_GRT(self):
        self.assertEqual(self.native_cli_case(metadata_equal=False),1)

    def test_native_cli_zero_only_means_requested_comparisons_equal_not_production_ready(self):
        self.assertEqual(self.native_cli_case(metadata_equal=True),0)


if __name__ == "__main__":
    unittest.main()
