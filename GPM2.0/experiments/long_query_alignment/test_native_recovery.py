"""Deferred bridge/ownership/selector checks. None run in implementation."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import batch_seed_ownership as bo
import native_recovery as nr
import native_selection as ns
import post_dp_selection as ps
import windowed_alignment as wa
from test_post_dp_selection import state


def source_plan(strand="+",split=True):
    coarse = {"query":"q","query_length":40,"query_start":0,"query_end":40,"strand":strand,
              "target":"t","target_length":50,"target_start":0,"target_end":40,"minimizers":9}
    intervals = [(0,6),(20,26),(34,40)] if split else [(0,40)]
    rows = []
    for i,(start,end) in enumerate(intervals):
        qs,qe = (start,end) if strand=="+" else (40-end,40-start)
        rows.append({**coarse,"id":i+1,"query_start":qs,"query_end":qe,
                     "target_start":start,"target_end":end,"ops":((end-start,"="),)})
    trace = "QR\tq\t0\t40\n"+"".join(f"CN\t0\tt\t{n}\t{strand}\t{n}\t2\t0\n"
        for n in (1,3,5,21,23,25,35,37,39))+"QT\tq\t0\t0.1\n"
    return {7:{"coarse":coarse,"fragments":rows}},trace


class NativeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def ownership(self,plans,trace):
        path = self.root/"trace.stderr"
        path.write_text(trace)
        return bo.collect(path,plans,query_name="q",query_length=40,target_lengths={"t":50},
                          expected_sha256=hashlib.sha256(trace.encode()).hexdigest())

    def test_single_and_three_fragment_ownership_forward_reverse_without_canonical_fill(self):
        for strand in ("+","-"):
            for split in (False,True):
                with self.subTest(strand=strand,split=split):
                    plans,trace = source_plan(strand,split)
                    result = self.ownership(plans,trace)
                    self.assertEqual(result["source_scans"],1)
                    self.assertEqual(result["chains"][7]["anchor_counts"],[3,3,3] if split else [9])
                    self.assertEqual(result["chains"][7]["exact_path_anchor_counts"],[3,3,3] if split else [9])
                    self.assertFalse(result["native_dp_split_events_certified"])

    def test_nearby_overlapping_window_alternative_requires_real_seed_diagonal(self):
        plans,trace = source_plan(split=False)
        original = plans[7]["fragments"][0]
        plans[7]["fragments"].append({**original,"id":99,"target_start":1,"target_end":41})
        result = self.ownership(plans,trace)
        self.assertEqual(result["chains"][7]["fragment_ids"],[1])
        self.assertEqual(result["chains"][7]["unseeded_fragment_ids"],[99])

    def test_shared_missing_duplicate_original_scope_or_partial_trace_refuses(self):
        for mode in ("shared","missing","duplicate_original","partial"):
            plans,trace = source_plan(split=False)
            original = plans[7]["fragments"][0]
            if mode=="shared":
                plans[7]["fragments"].append({**original,"id":2})
            elif mode=="missing":
                plans[7]["fragments"][0] = {**original,"query_start":8,"query_end":16,
                                             "target_start":8,"target_end":16,"ops":((8,"="),)}
            elif mode=="duplicate_original":
                plans[8] = plans[7]
            else:
                trace = trace.split("QT")[0]
            with self.subTest(mode=mode),self.assertRaises(wa.ExperimentError):
                self.ownership(plans,trace)

    def test_unsplit_count_retains_original_trimmed_anchors_not_only_path_coverage(self):
        plans,trace = source_plan(split=False)
        row = plans[7]["fragments"][0]
        plans[7]["fragments"][0] = {**row,"query_end":26,"target_end":26,"ops":((26,"="),)}
        result = self.ownership(plans,trace)["chains"][7]
        self.assertEqual(result["anchor_counts"],[9])
        self.assertEqual(result["exact_path_anchor_counts"],[6])
        self.assertEqual(result["source_anchors_after_last_path"],3)

    def test_native_output_parser_checks_parent_replay_and_no_window_MAPQ_255(self):
        states = [state("p"),state("s",target_id=1,dp_max=9000)]
        replay = ps.replay_post_dp_selection(states,query_length=1000)
        rows = replay["retained_candidates"]
        indexes = {r.key:i for i,r in enumerate(states)}
        text = "S\tcgat-post-dp\t1\t2.31-r1302\tasm10\t1000\t0\t2\t2\n"
        for row in rows:
            values = [indexes[row["state"]["key"]],row["id"],row["parent"],row["subscore"],row["subcount"],
                      row["dp_max2"],60 if row["id"]==row["parent"] else 0,int(row["sam_primary"])]
            text += "R\t"+"\t".join(map(str,values))+"\n"
        text += "END\t2\n"
        path = self.root/"selection.stdout"
        path.write_text(text)
        selected = ns.parse_output(path,states,replay,query_length=1000,repetitive_length=0)
        self.assertEqual([r["mapq"] for r in selected],[60,0])
        path.write_text(text.replace("\t60\t","\t255\t"))
        with self.assertRaises(wa.ExperimentError):
            ns.parse_output(path,states,replay,query_length=1000,repetitive_length=0)

    def test_native_input_requires_every_original_field_and_full_path_scores(self):
        path = self.root/"state.tsv"
        row = state("only")
        with self.assertRaises(wa.ExperimentError):
            ns.write_input(path,[asdict(row)],{"only":1000},query_length=1000,repetitive_length=0)
        with self.assertRaises(wa.ExperimentError):
            ns.write_input(path,[row],{},query_length=1000,repetitive_length=0)
        self.assertFalse(path.exists())
        ns.write_input(path,[row],{"only":1000},query_length=1000,repetitive_length=0)
        self.assertIn("CGAT_POST_DP_V1 1000 0 1",path.read_text())

    def test_split_is_observed_in_distinct_native_rows_not_just_window_gap(self):
        windows = self.root/"windows.json"
        windows.write_text(json.dumps([asdict(wa.Window("w","q",20,0,20,0,20))]))
        raw = self.root/"raw.paf"
        hits = {1:wa.Hit("q",20,0,8,"+","t",20,0,8,8,8,255,((8,"="),)),
                2:wa.Hit("q",20,12,20,"+","t",20,12,20,8,8,255,((8,"="),))}
        text = ("w\t20\t0\t8\t+\tt\t20\t0\t8\t8\t8\t60\tcg:Z:8=\tzd:i:1\n"
                "w\t20\t12\t20\t+\tt\t20\t12\t20\t8\t8\t60\tcg:Z:8=\tzd:i:2\n")
        raw.write_text(text)
        target = SimpleNamespace(records={"t":{"length":20}})
        proof = nr._split_observations(raw,windows,hits,{(1,2)},target)
        self.assertEqual(proof[0]["observations"][0]["window"],"w")
        with self.assertRaisesRegex(wa.ExperimentError,"unrepresented"):
            nr._split_observations(raw,windows,hits,set(),target,forbidden_heads={1})
        raw.write_text(text.replace("\tzd:i:1","").replace("\tzd:i:2",""))
        with self.assertRaisesRegex(wa.ExperimentError,"lacks an observed"):
            nr._split_observations(raw,windows,hits,{(1,2)},target)
        raw.write_text(text.replace("\tzd:i:1","\ttp:A:I\tzd:i:1"))
        with self.assertRaisesRegex(wa.ExperimentError,"inversion"):
            nr._split_observations(raw,windows,hits,set(),target)

    def test_native_anchor_prefilter_does_not_reject_cancelling_indels_by_diagonal(self):
        hit = wa.Hit("q",20000,0,20000,"+","t",20000,0,20000,18000,22000,255,
                     ((8000,"="),(2000,"I"),(4000,"="),(2000,"D"),(6000,"=")))
        chain = SimpleNamespace(query="q",target="t",strand="+",qs=0,qe=20000,ts=0,te=20000)
        self.assertTrue(nr._candidate(hit,chain))

    def test_public_experimental_PAF_withholds_computed_native_confidence_and_scores(self):
        hit = wa.Hit("q",1000,0,1000,"+","t",1000,0,1000,1000,1000,255,((1000,"="),))
        score = SimpleNamespace(ambiguous=0,dp_max0=1000)
        selected = {"id":0,"parent":0,"mapq":60,"subscore":0}
        kwargs = dict(chain_row=1,state=state("x"),selected=selected,split_flag=0,repetitive_length=0)
        public = nr._paf(hit,score,with_native_metadata=False,**kwargs)
        private = nr._paf(hit,score,with_native_metadata=True,**kwargs)
        self.assertEqual(public.split("\t")[11],"255")
        self.assertEqual(private.split("\t")[11],"60")
        self.assertNotIn("\tAS:i:",private)
        self.assertTrue(all(tag not in public for tag in ("\tms:i:","\ts1:i:","\ttp:A:")))


if __name__ == "__main__":
    unittest.main()
