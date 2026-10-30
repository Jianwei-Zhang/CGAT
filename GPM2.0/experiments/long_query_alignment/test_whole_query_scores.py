"""Deferred whole-path score checks. NOT executed in implementation phase."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import whole_query_scores as ws
import windowed_alignment as wa


def score_path(*args,**kwargs):
    # An explicit synthetic part identity, NOT customer/native producer evidence.
    return ws.score_path(*args,**kwargs,index_sha256="d"*64)


class Store:
    def __init__(self,sequences):
        self.sequences = sequences
        self.records = {name:{"length":len(seq)} for name,seq in sequences.items()}
        self.identity = {"sha256":hashlib.sha256(b"".join(name.encode()+b":"+seq for name,seq in sequences.items())).hexdigest()}
        self.max_read = 0

    def fetch(self,name,start,end):
        if not 0 <= start <= end <= self.records[name]["length"]:
            raise wa.ExperimentError("fixture coordinate overflow")
        self.max_read = max(self.max_read,end-start)
        return self.sequences[name][start:end]


def checked_hit(query,target,ops,*,target_name="t",strand="+",qs=0,qe=None):
    if qe is None:
        qe = qs+sum(n for n,op in ops if op in wa.Q_OPS)
    span = sum(n for n,op in ops if op in wa.T_OPS)
    hit = wa.Hit("q",query.records["q"]["length"],qs,qe,strand,target_name,
                 target.records[target_name]["length"],0,span,0,0,255,tuple(ops))
    matches,block,_ = wa.checked_statistics(hit,query,target)
    return replace(hit,matches=matches,block=block)


def competing_paths():
    query = Store({"q":b"A"*1000})
    target = Store({"exact":b"A"*1000,"decoy":b"A"*900+b"C"*10+b"A"*90,
                    "deletion":b"A"*500+b"G"*10+b"A"*500})
    hits = [checked_hit(query,target,[(1000,"=")],target_name="exact"),
            checked_hit(query,target,[(900,"="),(10,"X"),(90,"=")],target_name="decoy"),
            checked_hit(query,target,[(500,"="),(10,"D"),(500,"=")],target_name="deletion")]
    return query,target,hits


class WholeQueryScoreTests(unittest.TestCase):
    def test_competing_paths_global_correction_does_not_inherit_window_ms(self):
        query,target,hits = competing_paths()
        scores = [score_path(h,query,target,key=h.target) for h in hits]
        result = ws.replay_native_rank_adjustment(scores,query_length=1000)
        self.assertTrue(result["rank_adjustment_applied"])
        self.assertEqual(result["mismatch_gap_factor"],25.0)
        self.assertEqual(result["scores"][0]["dp_max"],1000)
        self.assertEqual(result["scores"][1]["dp_max0"],900)
        self.assertEqual(result["scores"][1]["dp_max"],740)
        self.assertLess(result["scores"][2]["dp_max"],result["scores"][2]["dp_max0"])
        self.assertFalse(result["mapq_reconstructed"])
        self.assertFalse(result["candidate_completeness_certified"])

    def test_ambiguity_is_negative_score_and_excluded_from_mlen_blen(self):
        query = Store({"q":b"A"*300+b"NNNN"+b"A"*300})
        target = Store({"t":b"A"*300+b"NNNN"+b"A"*300})
        hit = checked_hit(query,target,[(604,"=")])
        score = score_path(hit,query,target,key="amb")
        self.assertEqual((score.matches,score.block_length,score.ambiguous),(600,600,4))
        self.assertEqual(score.dp_max0,596)
        self.assertEqual(score.mismatches_including_ambiguity,4)
        self.assertEqual(score.event_identity,600/604)

    def test_ambiguous_X_losses_and_local_reset(self):
        query = Store({"q":b"A"*250+b"N"+b"A"*30+b"A"*250})
        target = Store({"t":b"A"*250+b"C"+b"C"*30+b"A"*250})
        hit = checked_hit(query,target,[(250,"="),(31,"X"),(250,"=")])
        score = score_path(hit,query,target,key="reset")
        self.assertEqual(score.dp_max0,250)
        self.assertEqual(score.ambiguous,1)
        self.assertEqual(score.mismatches_including_ambiguity,31)

    def test_split_gap_and_chunk_boundaries_do_not_add_gap_openings(self):
        query = Store({"q":b"A"*300+b"C"*10+b"A"*300})
        target = Store({"t":b"A"*600})
        split = checked_hit(query,target,[(300,"="),(4,"I"),(6,"I"),(300,"=")])
        merged = replace(split,ops=((300,"="),(10,"I"),(300,"=")))
        results = []
        for chunk in (3,17,wa.CHUNK):
            with patch.object(wa,"CHUNK",chunk):
                results.append(score_path(split,query,target,key="same"))
                results.append(score_path(merged,query,target,key="same"))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(results[0].gap_lengths,(10,))
        self.assertEqual(results[0].gap_openings,1)
        self.assertEqual(results[0].dp_max0,int(600-16-2*ws.native_log2(11)+0.499))

    def test_reverse_path_uses_oriented_query_bases(self):
        oriented = b"ACGT"*75+b"CCC"+b"ACGT"*75
        query = Store({"q":oriented.translate(wa.RC)[::-1]})
        target = Store({"t":b"ACGT"*150})
        hit = checked_hit(query,target,[(300,"="),(3,"I"),(300,"=")],strand="-")
        score = score_path(hit,query,target,key="reverse")
        self.assertEqual(score.matches,600)
        self.assertEqual(score.gap_lengths,(3,))
        self.assertEqual(score.strand,"-")

    def test_long_exact_run_uses_bounded_fetch_and_no_native_cigar_encoding(self):
        length = wa.LIMIT+17
        class VirtualStore:
            def __init__(self,name):
                self.records = {name:{"length":length}}
                self.identity = {"sha256":"a"*64}
                self.max_read = 0
            def fetch(self,name,start,end):
                if not 0 <= start <= end <= length:
                    raise wa.ExperimentError("virtual bounds")
                self.max_read = max(self.max_read,end-start)
                return b"A"*(end-start)
        query,target = VirtualStore("q"),VirtualStore("t")
        hit = wa.Hit("q",length,0,length,"+","t",length,0,length,length,length,255,
                     ((wa.LIMIT,"="),(17,"=")))
        score = score_path(hit,query,target,key="long")
        self.assertEqual(score.dp_max0,length)
        self.assertEqual(score.matches,length)
        self.assertLessEqual(max(query.max_read,target.max_read),wa.CHUNK)
        self.assertEqual(score.gap_openings,0)

    def test_global_gate_ratio_and_source_identity_and_first_filter_are_explicit(self):
        query,target,hits = competing_paths()
        scores = [score_path(h,query,target,key=h.target) for h in hits]
        for field,value in (("query_sha256","bad"),("query","other"),("index_sha256","e"*64)):
            with self.subTest(field=field),self.assertRaises(wa.ExperimentError):
                ws.replay_native_rank_adjustment([scores[0],replace(scores[1],**{field:value})],query_length=1000)
        with self.assertRaisesRegex(wa.ExperimentError,"bound original index part"):
            ws.replay_native_rank_adjustment([replace(scores[0],index_sha256=None)],query_length=1000)
        with self.assertRaisesRegex(wa.ExperimentError,"first-filter"):
            ws.replay_native_rank_adjustment([replace(scores[0],dp_max0=199)],query_length=1000)
        far = ws.replay_native_rank_adjustment([scores[0],replace(scores[1],dp_max0=899)],query_length=1000)
        self.assertFalse(far["rank_adjustment_applied"])
        self.assertEqual(far["reason"],"runner_up_below_score_threshold")
        partial = ws.replay_native_rank_adjustment([replace(scores[0],query_end=899),scores[1]],query_length=1000)
        self.assertEqual(partial["reason"],"best_path_below_query_coverage_threshold")

    def test_bad_base_path_leading_gap_and_incomplete_consumption_refused(self):
        query = Store({"q":b"A"*500})
        target = Store({"t":b"A"*500})
        good = checked_hit(query,target,[(500,"=")])
        cases = [replace(good,ops=((500,"X"),)),replace(good,ops=((499,"="),)),
                 replace(good,ops=((1,"I"),(499,"="))),replace(good,matches=499)]
        for hit in cases:
            with self.subTest(hit=hit),self.assertRaises(wa.ExperimentError):
                score_path(hit,query,target,key="bad")

    def test_sidecar_is_bound_to_input_but_never_rewrites_PAF_or_claims_AS_MAPQ(self):
        query,target,hits = competing_paths()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source,output = root/"guided.paf",root/"path-scores.jsonl"
            hit = hits[0]
            window = wa.Window("q","q",1000,0,1000,0,1000)
            raw = wa.paf_line(hit,window,0).encode()
            source.write_bytes(raw)
            receipt = ws.write_guided_path_scores(source,output,query,target,index_sha256="d"*64)
            self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(receipt["rows"],1)
            self.assertEqual(receipt["source_sha256"],wa.sha256(source))
            self.assertEqual(json.loads(output.read_text())["dp_max0"],1000)
            self.assertFalse(receipt["AS_reconstructed"])
            self.assertFalse(receipt["mapq_reconstructed"])
            self.assertFalse(receipt["global_rank_adjustment_applied"])
            with self.assertRaisesRegex(wa.ExperimentError,"fresh"):
                ws.write_guided_path_scores(source,output,query,target,index_sha256="d"*64)


if __name__ == "__main__":
    unittest.main()
