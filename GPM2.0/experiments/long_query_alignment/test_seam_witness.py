"""Deferred synthetic seam/provenance checks. Written only, NOT executed.

These construct PAF paths, not native DP oracles. Native small/large and downstream
acceptance must actually run before claiming equality or customer recovery.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import seam_witness as sw
import windowed_alignment as wa


class SeamWitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.counter = 0

    def store(self,name,sequence):
        path = self.root/(name+".fa")
        path.write_bytes(b">"+name.encode()+b"\n"+sequence+b"\n")
        store = wa.FastaStore(path,self.root/(name+".bases"))
        self.addCleanup(store.close)
        return store

    def setup_paths(self,*,strand="+",ops=((32,"="),),target_length=32):
        self.query = self.store("q",(b"A" if strand=="+" else b"T")*32)
        self.target = self.store("t",b"A"*target_length)
        self.windows = [wa.Window("left","q",32,0,20,0,16),wa.Window("right","q",32,12,32,16,32)]
        self.full = wa.Hit("q",32,0,32,strand,"t",target_length,0,target_length,0,0,255,ops)

    def raw_line(self,hit,window):
        matches,block,ambiguous = wa.checked_statistics(hit,self.query,self.target)
        local = replace(hit,query=window.alias,qlen=window.end-window.start,
                        qs=hit.qs-window.start,qe=hit.qe-window.start,matches=matches,block=block)
        return wa.paf_line(local,window,ambiguous).encode()

    def contextual(self,hit,window):
        context = wa.Window("context","q",32,0,32,window.start,window.end)
        return wa.clip_to_core(hit,context)

    def prepare(self,rows,*,crlf=False):
        self.raw,self.owned,self.proof = self.root/"raw.paf",self.root/"owned.paf",self.root/"owned.jsonl"
        data = b"".join(self.raw_line(hit,window) for hit,window in rows)
        self.raw.write_bytes(data.replace(b"\n",b"\r\n") if crlf else data)
        self.coverage = wa.recover(self.raw,self.owned,self.proof,self.windows,self.query,self.target)
        self.raw_hash,self.proof_hash = wa.sha256(self.raw),wa.sha256(self.proof)

    def stitch(self,*,witness=True):
        self.counter += 1
        output,audit = self.root/f"stitched-{self.counter}.paf",self.root/f"stitched-{self.counter}.jsonl"
        options = dict(raw_source=self.raw,owned_provenance=self.proof,raw_sha256=self.raw_hash,
                       owned_provenance_sha256=self.proof_hash) if witness else {}
        report = wa.stitch_owned(self.owned,output,audit,self.windows,self.query,self.target,**options)
        return output,audit,report

    def ordinary(self,*,strand="+"):
        self.setup_paths(strand=strand)
        self.prepare([(self.contextual(self.full,w),w) for w in self.windows])

    def test_matching_native_modeled_overlap_joins_both_strands_without_changing_path(self):
        for strand in ("+","-"):
            with self.subTest(strand=strand):
                # Separate source names/dirs avoid sharing state between strands.
                directory = self.root/strand
                directory.mkdir()
                previous = self.root
                self.root = directory
                self.ordinary(strand=strand)
                output,audit,report = self.stitch()
                self.assertEqual((report["stitched_rows"],report["exact_joins"]),(1,1))
                self.assertTrue(report["overlap_consistency_required"])
                self.assertEqual(report["compatible_edges"],1)
                self.assertFalse(report["whole_query_dp_equivalence_certified"])
                self.assertIn("cg:Z:32=",output.read_text())
                proof = json.loads(audit.read_text())
                self.assertEqual(sorted(proof["raw_overlap_witnesses"][0]["native_raw_rows"]),[1,2])
                self.assertEqual(proof["raw_overlap_witnesses"][0]["overlap_query"],[12,20])
                self.root = previous

    def test_indels_crossing_core_boundary_are_not_double_counted_or_normalized_again(self):
        cases = [(((14,"="),(4,"I"),(14,"=")),28,"14=4I14="),
                 (((16,"="),(4,"D"),(16,"=")),36,"16=4D16=")]
        for i,(ops,tlen,cigar) in enumerate(cases):
            for strand in ("+","-"):
                directory = self.root/f"indel-{i}-{strand}"
                directory.mkdir()
                previous = self.root
                self.root = directory
                self.setup_paths(strand=strand,ops=ops,target_length=tlen)
                self.prepare([(self.contextual(self.full,w),w) for w in self.windows])
                output,_,report = self.stitch()
                self.assertEqual(report["exact_joins"],1)
                self.assertIn("cg:Z:"+cigar,output.read_text())
                self.assertEqual(output.read_text().split("\t")[2:4],["0","32"])
                self.root = previous

    def conflicting_right(self):
        # Same endpoints as a 20= raw alignment, but a distinct local path.
        return wa.Hit("q",32,12,32,"+","t",32,12,32,0,0,255,((6,"="),(1,"I"),(1,"D"),(13,"=")))

    def test_equal_endpoints_with_conflicting_overlap_never_invent_a_join(self):
        self.setup_paths()
        left = self.contextual(self.full,self.windows[0])
        self.prepare([(left,self.windows[0]),(self.conflicting_right(),self.windows[1])])
        _,_,legacy = self.stitch(witness=False)
        output,audit,report = self.stitch()
        self.assertEqual(legacy["exact_joins"],1)
        self.assertEqual((report["stitched_rows"],report["exact_joins"]),(2,0))
        self.assertEqual(report["rejected_path_conflict"],1)
        self.assertEqual(len(output.read_text().splitlines()),2)
        self.assertEqual(sorted(i for r in map(json.loads,audit.read_text().splitlines()) for i in r["owned_rows"]),[1,2])

    def test_overlap_resolves_a_false_endpoint_fork_and_still_preserves_the_other_candidate(self):
        self.setup_paths()
        left,right = [self.contextual(self.full,w) for w in self.windows]
        self.prepare([(left,self.windows[0]),(self.conflicting_right(),self.windows[1]),(right,self.windows[1])])
        _,_,legacy = self.stitch(witness=False)
        output,audit,report = self.stitch()
        self.assertEqual((legacy["stitched_rows"],legacy["exact_joins"]),(3,0))
        self.assertEqual((report["stitched_rows"],report["exact_joins"]),(2,1))
        self.assertEqual(report["compatible_edges"],1)
        rows = list(map(json.loads,audit.read_text().splitlines()))
        self.assertEqual(rows[0]["owned_rows"],[1,3])
        self.assertEqual(rows[0]["raw_overlap_witnesses"][0]["native_raw_rows"],[1,3])
        self.assertEqual(sorted(i for r in rows for i in r["owned_rows"]),[1,2,3])
        self.assertIn("cg:Z:32=",output.read_text())
        self.assertEqual(len(output.read_text().splitlines()),2)

    def test_two_genuinely_supported_continuations_remain_a_fork_without_dropping_rows(self):
        self.setup_paths()
        left,right = [self.contextual(self.full,w) for w in self.windows]
        later_indel = wa.Hit("q",32,12,32,"+","t",32,12,32,0,0,255,((12,"="),(1,"I"),(1,"D"),(7,"=")))
        self.prepare([(left,self.windows[0]),(right,self.windows[1]),(later_indel,self.windows[1])])
        output,audit,report = self.stitch()
        self.assertEqual((report["stitched_rows"],report["exact_joins"]),(3,0))
        self.assertEqual(report["compatible_edges"],2)
        self.assertEqual(report["fork_endpoints_not_joined"],1)
        self.assertEqual(len(output.read_text().splitlines()),3)
        self.assertEqual(sorted(i for r in map(json.loads,audit.read_text().splitlines()) for i in r["owned_rows"]),[1,2,3])

    def test_duplicate_owned_core_keeps_all_raw_origins_not_only_the_first(self):
        self.setup_paths()
        # The first left source agrees inside its core but conflicts after it.
        bad_left = wa.Hit("q",32,0,20,"+","t",32,0,20,0,0,255,((18,"="),(1,"I"),(1,"D"),(1,"=")))
        left,right = [self.contextual(self.full,w) for w in self.windows]
        self.prepare([(bad_left,self.windows[0]),(left,self.windows[0]),(right,self.windows[1])])
        self.assertEqual(self.coverage["exact_duplicate_rows"],1)
        _,audit,report = self.stitch()
        self.assertEqual(report["exact_joins"],1)
        witness = json.loads(audit.read_text())["raw_overlap_witnesses"][0]
        self.assertEqual(witness["native_raw_rows"],[2,3])
        self.assertEqual(report["origin_pairs_checked"],2)

    def test_partial_raw_overlap_must_straddle_seam_but_need_not_fill_all_context(self):
        self.setup_paths()
        left = wa.Hit("q",32,0,17,"+","t",32,0,17,0,0,255,((17,"="),))
        right = wa.Hit("q",32,15,32,"+","t",32,15,32,0,0,255,((17,"="),))
        self.prepare([(left,self.windows[0]),(right,self.windows[1])])
        _,audit,report = self.stitch()
        self.assertEqual(report["exact_joins"],1)
        self.assertEqual(json.loads(audit.read_text())["raw_overlap_witnesses"][0]["overlap_query"],[15,17])

    def test_just_touching_raw_ends_do_not_prove_cross_seam_continuity(self):
        self.setup_paths()
        left = wa.Hit("q",32,0,16,"+","t",32,0,16,0,0,255,((16,"="),))
        right = wa.Hit("q",32,16,32,"+","t",32,16,32,0,0,255,((16,"="),))
        self.prepare([(left,self.windows[0]),(right,self.windows[1])])
        _,_,report = self.stitch()
        self.assertEqual((report["stitched_rows"],report["exact_joins"]),(2,0))
        self.assertEqual(report["rejected_no_crossing_overlap"],1)

    def test_raw_byte_offsets_and_hashes_survive_CRLF_without_text_tell_guessing(self):
        self.setup_paths()
        self.prepare([(self.contextual(self.full,w),w) for w in self.windows],crlf=True)
        proof = list(map(json.loads,self.proof.read_text().splitlines()))
        self.assertEqual(proof[0]["raw_byte_start"],0)
        self.assertEqual(proof[0]["raw_byte_end"],proof[1]["raw_byte_start"])
        self.assertEqual(proof[-1]["raw_byte_end"],self.raw.stat().st_size)
        _,_,report = self.stitch()
        self.assertEqual(report["exact_joins"],1)

    def test_changed_raw_or_provenance_never_publishes_a_stitched_result(self):
        self.ordinary()
        self.raw.write_bytes(self.raw.read_bytes().replace(b"\t255\t",b"\t254\t",1))
        with self.assertRaises(wa.ExperimentError):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_changed_owned_CIGAR_cannot_evade_source_checks_even_if_base_valid(self):
        self.ordinary()
        rows = self.owned.read_text().splitlines(keepends=True)
        fields = rows[0].rstrip("\n").split("\t")
        fields[9:11] = ["15","17"]
        fields = ["cg:Z:1I1D15=" if f.startswith("cg:Z:") else f for f in fields]
        self.owned.write_text("\t".join(fields)+"\n"+rows[1])
        with self.assertRaisesRegex(wa.ExperimentError,"no longer backs"):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_changed_provenance_cannot_replace_the_original_producer_hash(self):
        self.ordinary()
        rows = list(map(json.loads,self.proof.read_text().splitlines()))
        rows[0]["raw_mapq"] = 254
        self.proof.write_text("".join(json.dumps(r)+"\n" for r in rows))
        with self.assertRaises(wa.ExperimentError):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_semantically_forged_owned_origin_is_rejected_even_with_a_new_proof_hash(self):
        self.ordinary()
        rows = list(map(json.loads,self.proof.read_text().splitlines()))
        rows[0]["owned_row"] = 999
        self.proof.write_text("".join(json.dumps(r)+"\n" for r in rows))
        self.proof_hash = wa.sha256(self.proof)
        with self.assertRaises(wa.ExperimentError):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_changed_native_source_is_checked_even_if_the_owner_has_no_join(self):
        self.setup_paths()
        # One owner has no candidate edge; its source identity still matters.
        self.prepare([(self.contextual(self.full,self.windows[0]),self.windows[0])])
        self.raw.write_bytes(self.raw.read_bytes().replace(b"\t255\t",b"\t254\t",1))
        with self.assertRaisesRegex(wa.ExperimentError,"changed"):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_unread_context_only_raw_row_is_still_bound_by_the_whole_file_hash(self):
        self.setup_paths()
        first = self.contextual(self.full,self.windows[0])
        outside = wa.Hit("q",32,12,16,"+","t",32,12,16,0,0,255,((4,"="),))
        self.prepare([(first,self.windows[0]),(outside,self.windows[1])])
        self.assertEqual(self.coverage["context_only_rows"],1)
        rows = self.raw.read_bytes().splitlines(keepends=True)
        rows[1] = rows[1].replace(b"\t255\t",b"\t254\t",1)
        self.raw.write_bytes(b"".join(rows))
        with self.assertRaisesRegex(wa.ExperimentError,"evidence changed"):
            self.stitch()
        self.assertFalse((self.root/"stitched-1.paf").exists())

    def test_read_and_comparison_bounds_refuse_rather_than_skipping_candidates(self):
        self.ordinary()
        for key,limit in (("MAX_READ_BYTES",1),("MAX_COMPARISONS",0),("MAX_ROWS",1)):
            with self.subTest(key=key),patch.object(sw,key,limit),self.assertRaises(wa.ExperimentError):
                self.stitch()
            self.assertFalse((self.root/f"stitched-{self.counter}.paf").exists())

    def test_missing_source_or_proof_is_not_an_endpoint_only_escape_hatch(self):
        self.ordinary()
        with self.assertRaisesRegex(wa.ExperimentError,"required together"):
            wa.stitch_owned(self.owned,self.root/"bad.paf",self.root/"bad.jsonl",self.windows,self.query,self.target,
                            raw_source=self.raw)


if __name__ == "__main__":
    unittest.main()
