"""Bounded pure sequence/provenance checks, without invoking any native tools."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server.tools import refinement_path as rp


class MemoryCatalog:
    def __init__(self, values):
        self.values = {key: value.encode() for key, value in values.items()}
        self.max_read = 0

    def length(self, dataset, contig):
        return len(self.values[dataset, contig])

    def fetch(self, dataset, contig, start, end):
        self.max_read = max(self.max_read, end - start)
        return self.values[dataset, contig][start:end]


def source(dataset, contig, start, end, orientation="+"):
    return dict(dataset=dataset, contig=contig, start=start, end=end, orientation=orientation)


def segment(sid, src=None, length=None):
    return {"segment_id": sid, "kind": "source" if src else "gap",
            "length": src["end"] - src["start"] + 1 if src else length,
            **({"source": src, "orientation": src["orientation"], "evidence_ids": ["original-proof"]} if src else {})}


def baseline(catalog, segments):
    sequence = b"".join(block for row in segments for block in rp.segment_blocks(row, catalog))
    return {"workflow": "gpm_grt_precomputed_v2", "schema_version": "1", "q4_relpath": "grt/q/q4.fa",
            "chromosomes": [{"chr": "chr1", "q4_length": len(sequence),
                              "q4_sha256": hashlib.sha256(sequence).hexdigest(), "segments": segments}]}


def build(base, catalog, edits):
    return rp.build_final_path(base, catalog, edits, tool="degap", recipe_sha256="a" * 64,
                               baseline_artifact_sha256="b" * 64)


def sequence(final, catalog):
    return b"".join(block for row in final["chromosomes"][0]["segments"] for block in rp.segment_blocks(row, catalog))


class RefinementPathTests(unittest.TestCase):
    def setUp(self):
        self.catalog = MemoryCatalog({("old", "left"): "AACC", ("old", "right"): "ACGTAA",
                                      ("degap", "candidate"): "GGNNT", ("degap", "joint"): "CAT"})
        self.base = baseline(self.catalog, [segment("left", source("old", "left", 1, 4)),
                                           segment("gap", length=4),
                                           segment("minus", source("old", "right", 1, 6, "-"))])
        self.gaps = rp.inspect_baseline(self.base, self.catalog)[0]

    def edit(self, start=4, end=8, replacement=None, edit_id="job-1", gap_ids=None):
        return rp.Edit(edit_id=edit_id, tool="degap", chromosome="chr1", start=start, end=end,
                       replacement=replacement, gap_ids=gap_ids or (self.gaps[0].gap_id,),
                       native_job="native/job-1", evidence={"anchor_validation": "test-fixture"})

    def test_partial_fill_is_sourced_and_final_fasta_is_reconstructed(self):
        original = copy.deepcopy(self.base)
        result = build(self.base, self.catalog, [self.edit(replacement=source("degap", "candidate", 1, 5))])
        self.assertEqual(sequence(result, self.catalog), b"AACCGGNNTTTACGT")
        rows = result["chromosomes"][0]["segments"]
        self.assertEqual([row["kind"] for row in rows], ["source", "patch", "gap", "patch", "source"])
        self.assertEqual(rows[2]["refinement_source"]["start"], 3)
        self.assertEqual(rows[-1]["source"], self.base["chromosomes"][0]["segments"][-1]["source"])
        self.assertEqual(rows[-1]["output_start"], 9)
        self.assertEqual(self.base, original)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assembly.fa"
            rp.write_assembly(result, self.catalog, output)
            self.assertEqual(output.read_bytes(), b">chr1\nAACCGGNNTTTACGT\n")
            with self.assertRaises(FileExistsError):
                rp.write_assembly(result, self.catalog, output)

    def test_overlap_closure_slices_negative_source_without_fake_patch(self):
        result = build(self.base, self.catalog, [self.edit(end=10)])
        self.assertEqual(sequence(result, self.catalog), b"AACCACGT")
        last = result["chromosomes"][0]["segments"][-1]
        self.assertEqual(last["source"], source("old", "right", 1, 4, "-"))
        self.assertEqual(last["parent_segment_id"], "minus")
        self.assertEqual(last["evidence_ids"], ["original-proof"])
        self.assertEqual(result["edits"][0]["replacement_segment_ids"], [])
        self.assertEqual(result["edits"][0]["output_start"], result["edits"][0]["output_end"])

    def test_joint_edit_binds_both_original_gaps(self):
        base = baseline(self.catalog, [segment("a", source("old", "left", 1, 2)), segment("g1", length=2),
                                       segment("b", source("old", "left", 3, 4)), segment("g2", length=3),
                                       segment("c", source("old", "right", 1, 4))])
        gaps, _ = rp.inspect_baseline(base, self.catalog)
        edit = self.edit(start=2, end=9, replacement=source("degap", "joint", 1, 3),
                         gap_ids=tuple(row.gap_id for row in gaps))
        result = build(base, self.catalog, [edit])
        self.assertEqual(sequence(result, self.catalog), b"AACATACGT")
        self.assertEqual(len(result["original_gaps"]), 2)
        self.assertEqual(len(result["edits"][0]["gap_ids"]), 2)
        with self.assertRaisesRegex(rp.PathError, "every original gap"):
            build(base, self.catalog, [self.edit(start=2, end=9, gap_ids=(gaps[0].gap_id,))])

    def test_zero_edits_preserves_sequence_but_is_not_success_receipt(self):
        result = build(self.base, self.catalog, [])
        self.assertEqual(sequence(result, self.catalog), b"AACCNNNNTTACGT")
        self.assertNotIn("status", result)
        self.assertEqual([s["segment_id"] for s in result["chromosomes"][0]["segments"]], ["left", "gap", "minus"])

    def test_writer_reports_same_n_runs_across_blocks_and_segments_without_reread(self):
        cat = MemoryCatalog({("old", "s"): "ACNN", ("old", "t"): "NNGTNN"})
        base = baseline(cat, [segment("first", source("old", "s", 1, 4)), segment("literal", length=2),
                              segment("second", source("old", "t", 1, 6))])
        final = build(base, cat, [])
        with tempfile.TemporaryDirectory() as d, patch.object(rp, "BLOCK", 2), patch.object(cat, "fetch", wraps=cat.fetch) as fetch:
            rp.write_assembly(final, cat, Path(d) / "without.fa")
            calls = fetch.call_count
            fetch.reset_mock()
            residual = []
            rp.write_assembly(final, cat, Path(d) / "with.fa", remaining=residual)
            self.assertEqual(fetch.call_count, calls)
            self.assertEqual((Path(d) / "with.fa").read_bytes(), (Path(d) / "without.fa").read_bytes())
            self.assertEqual([(r["start"], r["end"]) for r in residual], [(2, 8), (10, 12)])
            self.assertEqual(residual, rp.remaining_gaps(final, cat))

    def test_conflicting_or_non_gap_edits_are_not_silently_chosen(self):
        with self.assertRaisesRegex(rp.PathError, "overlapping"):
            build(self.base, self.catalog, [self.edit(), self.edit(start=5, end=7, edit_id="job-2")])
        with self.assertRaisesRegex(rp.PathError, "every original gap"):
            build(self.base, self.catalog, [self.edit(start=0, end=2)])

    def test_forged_baseline_or_changed_sources_fail(self):
        forged = copy.deepcopy(self.base)
        forged["chromosomes"][0]["q4_sha256"] = "0" * 64
        with self.assertRaisesRegex(rp.PathError, "baseline source reconstruction"):
            build(forged, self.catalog, [])
        result = build(self.base, self.catalog, [])
        self.catalog.values["old", "left"] = b"TTTT"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(rp.PathError, "changed during reconstruction"):
                rp.write_assembly(result, self.catalog, Path(directory) / "output.fa")

    def test_streaming_gap_scan_and_reverse_complement_cross_block_boundaries(self):
        with patch.object(rp, "BLOCK", 2):
            catalog = MemoryCatalog({("d", "s"): "AANNN", ("d", "t"): "NNACGT"})
            base = baseline(catalog, [segment("a", source("d", "s", 1, 5)),
                                      segment("g", length=3), segment("b", source("d", "t", 1, 6))])
            gaps, _ = rp.inspect_baseline(base, catalog)
            self.assertEqual([(g.start, g.end) for g in gaps], [(2, 10)])
            self.assertEqual(b"".join(rp.source_blocks(source("d", "t", 1, 6, "-"), catalog)), b"ACGTNN")
            self.assertLessEqual(catalog.max_read, 2)


if __name__ == "__main__":
    unittest.main()
