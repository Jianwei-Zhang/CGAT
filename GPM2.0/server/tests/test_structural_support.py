from __future__ import annotations

import copy
import unittest

from server.tests.test_q0_admission import dna
from server.tests.test_source_intervals import segment, gap
from server.tools.lgz_core.common import reverse_complement
from server.tools.lgz_core.q0_sources import SourceKey
from server.tools.lgz_core.repair_structural import (
    apply_corrections, build_correction_candidates, promote_direct_source_overlap_merges,
)
from server.tools.lgz_core.step2_engine import build_step2_structural_fallback_candidates
from server.tools.lgz_core.structural_support import OverlapSupport, ReferenceSupport, self_context_lines


def fixture(reverse=False, same_dataset=False):
    left_key = SourceKey("left", "same_name")
    right_key = SourceKey("left" if same_dataset else "right", "other_name" if same_dataset else "same_name")
    common, before, after = dna(12000, 232), dna(2000, 233), dna(3000, 234)
    left, right, guide = before + common, common + after, before + common + after
    orientation = "-" if reverse else "+"
    sources = {(key.dataset, key.contig): reverse_complement(text) if reverse else text
               for key, text in ((left_key, left), (right_key, right))}
    sources[("guide", "bridge")] = guide
    paths = {"chr1": [segment(left_key, 0, len(left), orientation), gap(), segment(right_key, 0, len(right), orientation)]}
    origin = {"chr": "chr1", "object_id": "gap", "start0": len(left), "end0": len(left) + 100}
    candidate = {"candidate_id": "type5", "chr": "chr1", "object_id": "gap", "outcome": "candidate",
                 "error_type": "type5", "source_dataset": "guide", "source_contig": "bridge",
                 "source_start": 1, "source_end": len(guide), "orientation": "+"}
    return sources, paths, origin, candidate, (before, common, after)


def placement(key, size, start, *, orientation="+", chromosome="chr1", evidence="ref"):
    return {"source": {"dataset": key.dataset, "contig": key.contig}, "chromosome": chromosome,
            "orientation": orientation, "reference_blocks": [
                {"source": {"start": 0, "end": size}, "reference": {"start": start, "end": start + size}, "evidence_id": evidence}]}


def row(line, query_start, query_end, ref_start, ref_end, *, record="guide", orientation="+", query_length=29100):
    return {"chr": "chr1", "line_number": line, "ref_record": record,
            "ref_min": ref_start, "ref_max": ref_end, "query_min": query_start, "query_max": query_end,
            "query_length": query_length, "query_aligned": query_end-query_start+1,
            "ref_length": 200000, "ref_aligned": ref_end-ref_start+1, "identity": 1.0, "orientation": orientation}


def member(dataset="guide", contig="bridge", size=200000):
    return {"member_id": "member-"+dataset, "dataset_name": dataset, "contig_name": contig,
            "orientation": "+", "source_start": 1, "source_end": size}


class SourceOverlapTests(unittest.TestCase):
    def promote(self, sources, paths, origin, candidate, *, reference=None):
        promote_direct_source_overlap_merges([origin], [candidate], paths, sources,
                                              support=OverlapSupport(sources, reference))
        return candidate

    def test_cross_dataset_same_contig_name_joins_with_actual_sequence_guide(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                sources, paths, origin, candidate, (before, common, after) = fixture(reverse)
                self.promote(sources, paths, origin, candidate)
                self.assertEqual(candidate["source_overlap_support"]["status"], "supported")
                self.assertEqual((candidate["trim_left"], candidate["trim_right"], candidate["fill_length"]), (0, len(common), 0))
                candidate["outcome"] = "accepted"
                _, records, _, _ = apply_corrections(["chr1"], paths,
                    {"chr1": before + common + "N"*100 + common + after}, [origin], [candidate], sources)
                self.assertEqual(records["chr1"], before + common + after)

    def test_reverse_guide_support_uses_original_source_coordinates(self):
        sources, paths, origin, candidate, parts = fixture()
        guide = sources[("guide", "bridge")]
        sources[("guide", "bridge")] = reverse_complement(guide)
        candidate["orientation"] = "-"
        self.promote(sources, paths, origin, candidate)
        proof = candidate["source_overlap_support"]
        self.assertEqual(proof["status"], "supported")
        self.assertEqual(proof["guide_interval"], {"start": 2900, "end": 15100})

    def test_original_n_split_fragments_can_merge_with_an_independent_guide(self):
        sources, paths, origin, candidate, (before, common, after) = fixture()
        source = SourceKey("assembly", "scaffold")
        original = before + common + "N" * 137 + common + after
        sources = {("assembly", "scaffold"): original, ("guide", "bridge"): before + common + after}
        paths = {"chr1": [segment(source, 0, 14000), gap(137), segment(source, 14137, 29137)]}
        origin.update(start0=14000, end0=14137)
        self.promote(sources, paths, origin, candidate)
        self.assertEqual(candidate["source_overlap_support"]["status"], "supported")
        candidate["outcome"] = "accepted"
        output, records, _, _ = apply_corrections(["chr1"], paths, {"chr1": original}, [origin], [candidate], sources)
        self.assertEqual(records["chr1"], before + common + after)
        self.assertEqual(output["chr1"][-1]["source_start"], 26138)

    def test_tandem_repeat_cannot_supply_overlap_identity(self):
        sources, paths, origin, candidate, (before, _, after) = fixture()
        common = "ACGT" * 3000
        sources[("left", "same_name")] = before + common
        sources[("right", "same_name")] = common + after
        sources[("guide", "bridge")] = before + common + after
        self.promote(sources, paths, origin, candidate)
        self.assertEqual(candidate["outcome"], "rejected")
        self.assertEqual(candidate["source_overlap_support"]["reason"], "low_complexity_overlap_or_flank")

    def test_reference_blocks_must_name_the_same_locus_for_shared_bases(self):
        for reverse in (False, True):
            for shift, chromosome, accepted in ((0, "chr1", True), (1, "chr1", False), (0, "chr2", False)):
                with self.subTest(reverse=reverse, shift=shift, chromosome=chromosome):
                    sources, paths, origin, candidate, parts = fixture(reverse)
                    left, right = paths["chr1"][0], paths["chr1"][2]
                    placements = [placement(SourceKey("left", "same_name"), left["length"], 0, orientation=left["orientation"], evidence="left-ref"),
                                  placement(SourceKey("right", "same_name"), right["length"], 2000 + shift,
                                            orientation=right["orientation"], chromosome=chromosome, evidence="right-ref")]
                    self.promote(sources, paths, origin, candidate, reference=ReferenceSupport(placements))
                    proof = candidate["source_overlap_support"]
                    self.assertEqual(proof["status"] == "supported", accepted)
                    self.assertEqual(proof["reference_evidence_ids"], ["left-ref", "right-ref"])
                    if not accepted:
                        self.assertEqual(candidate["outcome"], "rejected")
                        self.assertEqual(proof["reason"], "different_reference_loci")

    def test_repeated_original_source_not_just_selected_slice_is_rejected(self):
        sources, paths, origin, candidate, (before, common, after) = fixture()
        sources[("left", "same_name")] += dna(200, 600) + common
        self.promote(sources, paths, origin, candidate)
        self.assertEqual(candidate["source_overlap_support"]["reason"], "repeated_overlap_in_original_source")
        self.assertEqual(candidate["outcome"], "rejected")

    def test_low_complexity_and_repeated_guide_flanks_cannot_prove_junction(self):
        for mode in ("repeat_flank", "guide_gap", "wrong_spacing", "absent_guide", "wrong_scope"):
            with self.subTest(mode=mode):
                sources, paths, origin, candidate, (before, common, after) = fixture()
                if mode == "repeat_flank":
                    sources[("guide", "bridge")] += before[-100:]
                elif mode == "guide_gap":
                    sources[("guide", "bridge")] = before + "N" * len(common) + after
                elif mode == "wrong_spacing":
                    sources[("guide", "bridge")] = before + common + "A" + after
                elif mode == "absent_guide":
                    del sources[("guide", "bridge")]
                else:
                    candidate["source_start"] = 2001
                self.promote(sources, paths, origin, candidate)
                self.assertEqual(candidate["outcome"], "rejected")
                self.assertNotIn("junction_policy", candidate)

    def test_nonflush_overlap_never_drops_unproven_left_tail(self):
        sources, paths, origin, candidate, parts = fixture()
        sources[("left", "same_name")] += "TTT"
        paths["chr1"][0]["length"] += 3
        paths["chr1"][0]["source_end"] += 3
        origin["start0"] += 3; origin["end0"] += 3
        self.promote(sources, paths, origin, candidate)
        self.assertIn("nonflush_overlap", candidate["reason"])
        self.assertEqual(candidate["outcome"], "rejected")

    def test_each_candidate_requires_its_own_guide_not_previous_candidates_proof(self):
        sources, paths, origin, first, parts = fixture()
        second = {**first, "candidate_id": "different-guide", "source_contig": "missing"}
        promote_direct_source_overlap_merges([origin], [first, second], paths, sources)
        self.assertEqual(first["source_overlap_support"]["status"], "supported")
        self.assertEqual(second["outcome"], "rejected")

    def test_step2_structural_fallback_uses_same_cross_dataset_proof(self):
        sources, paths, origin, _, parts = fixture()
        rows = [row(1, 1, 14000, 1, 14000), row(2, 14101, 29100, 2001, 17000)]
        candidates = build_step2_structural_fallback_candidates([origin], rows, {"guide": member(size=17000)},
                                                              input_paths=paths, sources=sources)
        accepted = [candidate for candidate in candidates if candidate["outcome"] == "accepted"]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["source_overlap_support"]["status"], "supported")
        self.assertEqual(accepted[0]["trim_right"], 12000)


class SelfContextTests(unittest.TestCase):
    def test_forward_and_reverse_geometry_preserve_original_n_adjacency(self):
        for orientation in ("+", "-"):
            source = SourceKey("assembly", "ctg")
            pieces = [segment(source, 0, 1200, orientation), gap(137), segment(source, 1337, 2837, orientation)]
            if orientation == "-": pieces.reverse()
            paths = {"chr1": pieces}
            rows = [row(1, 1, 2837, 1, 2837, orientation=orientation, query_length=2837)]
            members = {"guide": member("assembly", "ctg", 2837)}
            self.assertEqual(self_context_lines(rows, paths, members), {("chr1", 1)})
            origins = [{"chr": "chr1", "object_id": "gap", "start0": pieces[0]["length"], "end0": pieces[0]["length"]+137}]
            candidates = build_correction_candidates(origins, rows, members, input_paths=paths)
            self.assertTrue(candidates)
            self.assertTrue(all(c["outcome"] == "rejected" and "self_context" in c["reason"] for c in candidates))
            fallback = build_step2_structural_fallback_candidates(origins, rows, members, input_paths=paths)
            self.assertTrue(all(c["outcome"] == "rejected" for c in fallback))

    def test_self_crossing_cannot_hide_an_independent_guides_flanks(self):
        source = SourceKey("assembly", "ctg")
        paths = {"chr1": [segment(source, 0, 1200), gap(137), segment(source, 1337, 2837)]}
        rows = [row(1, 1, 2837, 1, 2837, record="self", query_length=2837),
                row(2, 1, 1200, 1, 1200, query_length=2837), row(3, 1338, 2837, 1301, 2800, query_length=2837)]
        members = {"self": member("assembly", "ctg", 2837), "guide": member(size=2800)}
        origins = [{"chr": "chr1", "object_id": "gap", "start0": 1200, "end0": 1337}]
        candidates = build_correction_candidates(origins, rows, members, input_paths=paths)
        self.assertTrue(any(c["source_dataset"] == "assembly" and c["outcome"] == "rejected" for c in candidates))
        self.assertTrue(any(c["source_dataset"] == "guide" and c["outcome"] == "candidate" for c in candidates))

    def test_other_repeat_of_same_source_is_not_independent_structural_support(self):
        source = SourceKey("assembly", "ctg")
        paths = {"chr1": [segment(source, 100, 700), gap(100), segment(source, 700, 1300)]}
        rows = [row(1, 1, 1300, 1, 1300, query_length=1300)]
        members = {"guide": member("assembly", "ctg", 2000)}
        self.assertEqual(self_context_lines(rows, paths, members), set())
        origins = [{"chr": "chr1", "object_id": "gap", "start0": 600, "end0": 700}]
        candidates = build_correction_candidates(origins, rows, members, input_paths=paths)
        self.assertTrue(all(c["outcome"] == "rejected" and "self_context" in c["reason"] for c in candidates))

    def test_renamed_equivalent_assembly_does_not_gain_structural_edit_authority(self):
        source = SourceKey("assembly", "ctg")
        first, last = dna(1200, 910), dna(1500, 911)
        original = first + "N" * 137 + last
        paths = {"chr1": [segment(source, 0, 1200), gap(137), segment(source, 1337, 2837)]}
        origins = [{"chr": "chr1", "object_id": "gap", "start0": 1200, "end0": 1337}]
        for middle, equivalent in (("N" * 137, True), ("N" * 100, True), (dna(137, 912), False)):
            with self.subTest(equivalent=equivalent, length=len(middle)):
                guide = first + middle + last
                rows = [row(1, 1, len(original), 1, len(guide), query_length=len(original))]
                candidates = build_correction_candidates(origins, rows, {"guide": member(size=len(guide))},
                    input_paths=paths, sources={(source.dataset, source.contig): original, ("guide", "bridge"): guide},
                    input_records={"chr1": original})
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0]["source_structural_support"]["equivalent_sequence_context"], equivalent)
                self.assertEqual(candidates[0]["outcome"], "rejected" if equivalent else "candidate")
                if equivalent:
                    self.assertEqual(candidates[0]["reason"], "guide_confirms_existing_sequence_context")

    def test_equivalent_crossing_copy_does_not_hide_independent_anchor_pair(self):
        source = SourceKey("assembly", "ctg")
        first, last = dna(1200, 920), dna(1500, 921)
        original, guide = first + "N"*137 + last, first + dna(1000, 922) + last
        paths = {"chr1": [segment(source, 0, 1200), gap(137), segment(source, 1337, 2837)]}
        origins = [{"chr": "chr1", "object_id": "gap", "start0": 1200, "end0": 1337}]
        rows = [row(1, 1, 2837, 1, 2837, record="clone", query_length=2837),
                row(2, 1, 1200, 1, 1200, query_length=2837), row(3, 1338, 2837, 2201, 3700, query_length=2837)]
        members = {"clone": member("clone", "clone", 2837), "guide": member(size=3700)}
        sources = {(source.dataset, source.contig): original, ("clone", "clone"): original, ("guide", "bridge"): guide}
        candidates = build_correction_candidates(origins, rows, members, input_paths=paths, sources=sources,
                                                  input_records={"chr1": original})
        self.assertTrue(any(c["source_dataset"] == "clone" and c["reason"] == "guide_confirms_existing_sequence_context" for c in candidates))
        self.assertTrue(any(c["source_dataset"] == "guide" and c["outcome"] == "candidate" for c in candidates))

    def test_equal_hulls_with_different_source_offsets_are_not_self_identity(self):
        paths = {"chr1": [segment(SourceKey("assembly", "ctg"), 100, 1300)]}
        rows = [row(1, 1, 1200, 1, 1200, query_length=1200)]
        self.assertEqual(self_context_lines(rows, paths, {"guide": member("assembly", "ctg", 1300)}), set())
        rows[0]["ref_min"], rows[0]["ref_max"] = 101, 1300
        self.assertEqual(self_context_lines(rows, paths, {"guide": member("assembly", "ctg", 1300)}), {("chr1", 1)})


if __name__ == "__main__":
    unittest.main()
