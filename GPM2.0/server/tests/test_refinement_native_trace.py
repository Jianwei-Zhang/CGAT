"""Pure native trace composition, independent of aligners or installed runtimes."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from server.tools import refinement_path as paths
from server.tools.refinement_native_trace import retained, inserted, normalized_edits, verify_trace, trace_slice, TraceError
from server.tools import refinement_native_formats as native_formats
from server.tools.refinement_native_formats import ReadLookup, parse_lr_rows, apply_lr_round, parse_quartet
from server.tools.refinement_reads import prepare_fasta
from server.tests.test_refinement_path import MemoryCatalog, source, segment, baseline


class Genome:
    def __init__(self, sequence):
        self.sequence = sequence.encode()
        self.records = {"chr1": (len(sequence),)}

    def fetch(self, name, a, b):
        assert name == "chr1"
        return self.sequence[a:b]

    def blocks(self, name, a, b):
        for offset in range(a, b, paths.BLOCK):
            yield self.fetch(name, offset, min(b, offset + paths.BLOCK))


class Store:
    def __init__(self, catalog):
        self.catalog = catalog

    def add(self, name, sequence):
        cid = paths.identity(name)
        self.catalog.values["candidate", cid] = sequence
        return source("candidate", cid, 1, len(sequence))


class NativeTraceTests(unittest.TestCase):
    def setup_case(self, old, new):
        catalog = MemoryCatalog({("old", "original"): old, ("native", "chr1"): new})
        payload = baseline(catalog, [segment("old", source("old", "original", 1, len(old)))])
        gaps, _ = paths.inspect_baseline(payload, catalog)
        return catalog, payload, gaps, Genome(old), Genome(new)

    def project(self, catalog, payload, gaps, old, new, trace):
        verify_trace(trace, "chr1", old, catalog, new)
        edits, rejected = normalized_edits("lrgapcloser", {"chr1": trace}, old, new, gaps,
                                          native_dataset="native", native_names={"chr1": "chr1"}, job="native/job")
        final = paths.build_final_path(payload, catalog, edits, tool="lrgapcloser", recipe_sha256="a" * 64, baseline_artifact_sha256="b" * 64)
        actual = b"".join(block for row in final["chromosomes"][0]["segments"] for block in paths.segment_blocks(row, catalog))
        self.assertEqual(actual, new.sequence)
        self.assertFalse(rejected)
        return edits, final

    def test_joint_native_edit_retains_a_unique_unchanged_internal_island(self):
        data = self.setup_case("AANNCCNNGG", "AATCCAGG")
        trace = [retained(0, 2), inserted(source("native", "chr1", 3, 6), {"native": "joint"}), retained(8, 10)]
        edits, final = self.project(*data, trace)
        self.assertEqual(len(edits), 2)
        retained_sources = [s["source"] for s in final["chromosomes"][0]["segments"] if s.get("source", {}).get("dataset") == "old"]
        self.assertIn(source("old", "original", 5, 6), retained_sources)
        self.assertEqual(len({gid for edit in edits for gid in edit.gap_ids}), 2)

    def test_overlap_closure_can_delete_without_a_positive_bridge(self):
        data = self.setup_case("AACCNNCCGG", "AACCGG")
        edits, _ = self.project(*data, [retained(0, 2), retained(6, 10)])
        self.assertEqual((edits[0].start, edits[0].end, edits[0].replacement), (2, 6, None))

    def test_partial_insertion_before_remaining_n_preserves_original_gap_identity(self):
        data = self.setup_case("AANNGG", "AATNNGG")
        edits, final = self.project(*data, [retained(0, 2), inserted(source("native", "chr1", 3, 3), {"native": "partial"}), retained(2, 6)])
        self.assertEqual((edits[0].start, edits[0].end), (2, 3))
        self.assertEqual(paths.remaining_gaps(final, data[0])[0]["original_gap_ids"], [data[2][0].gap_id])

    def test_degap_merged_job_keeps_original_internal_source_island(self):
        try:
            from refinement_admission import preserve_joint_sources
        except ModuleNotFoundError:
            from server.tools.refinement_admission import preserve_joint_sources
        data = self.setup_case("AANNCCNNGG", "AATCCAGG")
        catalog, payload, gaps, original, native = data
        edit = paths.Edit("native-job", "degap", "chr1", 2, 8, source("native", "chr1", 3, 6),
                          tuple(g.gap_id for g in gaps), "native/merged", {"anchors": "validated"})
        edits, rejected = preserve_joint_sources([edit], original, catalog, gaps)
        self.assertFalse(rejected)
        self.assertEqual([(e.start, e.end) for e in edits], [(2, 4), (6, 8)])
        final = paths.build_final_path(payload, catalog, edits, tool="degap", recipe_sha256="a" * 64, baseline_artifact_sha256="b" * 64)
        reconstructed = b"".join(block for row in final["chromosomes"][0]["segments"] for block in paths.segment_blocks(row, catalog))
        self.assertEqual(reconstructed, native.sequence)

    def test_negative_read_source_slicing_retains_direction_and_interval(self):
        catalog = MemoryCatalog({("read", "r"): "AAGC"})
        piece = inserted(source("read", "r", 1, 4, "-"), {"native": "read"})
        sliced = trace_slice([retained(0, 2), piece], 3, 5)
        self.assertEqual(sliced[0]["source"], source("read", "r", 2, 3, "-"))
        self.assertEqual(b"".join(paths.source_blocks(sliced[0]["source"], catalog)), b"CT")

    def test_unexplained_native_change_cannot_be_treated_as_retained_sequence(self):
        data = self.setup_case("AANNGG", "TANNGG")
        with self.assertRaisesRegex(TraceError, "does not reconstruct"):
            verify_trace([retained(0, 6)], "chr1", data[3], data[0], data[4])

    def test_lr_partial_pair_then_second_iteration_composes_to_original_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "reads.fa"
            raw.write_text(">a\nTT\n>b\nCC\n>c\nAG\n")
            converted = Path(prepare_fasta([str(raw)], root / "cache")["fasta"])
            first, second = root / "first.tsv", root / "second.tsv"
            first.write_text("chr1(:3-6\tLR1(:1-2(:+\tchr1(:3-4\nchr1(:3-6\tLR2(:1-2(:+\tchr1(:5-6\n")
            second.write_text("chr1(:5-104\tLR3(:1-2(:+\tchr1(:5-104\n")
            rounds, lookup = parse_lr_rows([first, second], {"chr1": "chr1"}, converted)
            data = self.setup_case("AANNNNGG", "AATTAGCCGG")
            catalog, _, _, original, final_native = data
            store = Store(catalog)
            trace = {"chr1": [retained(0, 8)]}
            trace = apply_lr_round(trace, rounds[0], original, original, {}, lookup, store, 1)
            intermediate = Genome("AATT" + "N" * 100 + "CCGG")
            verify_trace(trace["chr1"], "chr1", original, catalog, intermediate)
            trace = apply_lr_round(trace, rounds[1], original, intermediate, {}, lookup, store, 2)
            edits, final = self.project(*data, trace["chr1"])
            self.assertEqual((edits[0].start, edits[0].end), (2, 6))
            self.assertEqual(len(final["original_gaps"]), 1)

    def test_quartet_small_gap_numbering_mismatch_is_not_silently_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "reads.fa"
            raw.write_text(">r\nAAAAGTCCCC\n")
            converted = Path(prepare_fasta([str(raw)], root / "cache")["fasta"])
            rid = converted.read_text().splitlines()[0][1:]
            src = str(converted) + "@" + rid
            data = self.setup_case("AANNCC" + "N" * 100 + "GG", "AANNCCGTGG")
            (root / "quartet.genome.filled.detail").write_text(f"chr1\t1\tClosed\t{src}\t5-6\t2\t+\t1.0\nchr1\t2\tNot_closed\n")
            (root / "quartet.genome.filled.modified.agp").write_text(
                f"chr1\t1\t6\t1\tP\tchr1\t1\t6\t+\nchr1\t7\t8\t2\tW\t{src}\t5\t6\t+\nchr1\t9\t10\t3\tP\tchr1\t107\t108\t+\n")
            with self.assertRaisesRegex(native_formats.TraceError, "gap/detail identity"):
                parse_quartet(root, data[3], data[2], {"chr1": "chr1"}, [str(converted)], Store(data[0]))


if __name__ == "__main__":
    unittest.main()
