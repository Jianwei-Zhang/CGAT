import unittest

from server.tools import grt_step23 as engine


class GapOriginTests(unittest.TestCase):
    @staticmethod
    def source_segment(sequence, orientation="+"):
        return {
            "segment_kind": "source",
            "length": len(sequence),
            "dataset_name": "assembly",
            "contig_name": "contig",
            "source_start": 1,
            "source_end": len(sequence),
            "orientation": orientation,
            "source_card_key": "assembly:contig:chr01:normal",
            "evidence_ids": [],
        }

    def trace_through_filter(self, sequence, path, sources):
        original = engine.gap_objects("chr01", "q2", sequence)
        paths, records, _, origins = engine.apply_corrections(
            ["chr01"], {"chr01": path}, {"chr01": sequence}, original, [], sources
        )
        corrected = engine.gap_objects("chr01", "corrected", sequence)
        engine.attach_gap_origins(corrected, origins)
        engine.annotate_gap_path_origins(paths, corrected)
        self.assertEqual(engine.path_sequence(paths["chr01"], sources), sequence)
        paths, records, _, _, _ = engine.apply_round(
            "run", "step3", "q2", "q3", ["chr01"], paths, records,
            corrected, [], {}, "input-sha", sources, action="refill",
        )
        paths, records, _ = engine.filter_paths(["chr01"], paths, records, sources)
        filtered = engine.gap_objects("chr01", "filtered", records["chr01"])
        engine.attach_gap_origins_from_paths(paths, filtered, original)
        return original, filtered, paths, records

    def test_source_internal_gaps_survive_filter_and_coalesce_origins(self):
        sequence = "A" * 100_000 + "N" * 100 + "C" * 20_000 + "N" * 100 + "G" * 100_000
        sources = {("assembly", "contig"): sequence}
        original, filtered, _, records = self.trace_through_filter(
            sequence, [self.source_segment(sequence)], sources
        )
        self.assertEqual(records["chr01"], "A" * 100_000 + "N" * 100 + "G" * 100_000)
        self.assertEqual(len(filtered), 1)
        origin = filtered[0]["origin"]
        self.assertEqual(
            {origin["object_id"], *origin["coalesced_object_ids"]},
            {gap["object_id"] for gap in original},
        )

    def test_internal_gap_keeps_source_coordinates_on_both_strands(self):
        sequence = "A" * 100_000 + "N" * 150 + "G" * 120_000
        for orientation in ("+", "-"):
            with self.subTest(orientation=orientation):
                source = sequence if orientation == "+" else engine.reverse_complement(sequence)
                sources = {("assembly", "contig"): source}
                original, filtered, paths, records = self.trace_through_filter(
                    sequence, [self.source_segment(sequence, orientation)], sources
                )
                self.assertEqual(records["chr01"], sequence)
                self.assertEqual(filtered[0]["origin"]["object_id"], original[0]["object_id"])
                self.assertTrue(all(segment["segment_kind"] == "source" for segment in paths["chr01"]))
                self.assertEqual(engine.path_sequence(paths["chr01"], sources), sequence)

    def test_gap_spanning_source_and_explicit_gap_segments_retains_origin(self):
        source = "A" * 100_000 + "N" * 50 + "G" * 100_000
        segment = self.source_segment(source)
        explicit_gap = {
            **segment, "segment_kind": "gap", "length": 100,
            "dataset_name": "", "contig_name": "", "source_start": None,
            "source_end": None, "orientation": "", "source_card_key": "",
        }
        path = [engine.slice_segment(segment, 0, 100_050), explicit_gap,
                engine.slice_segment(segment, 100_050, len(source))]
        sequence = "A" * 100_000 + "N" * 150 + "G" * 100_000
        original, filtered, _, records = self.trace_through_filter(
            sequence, path, {("assembly", "contig"): source}
        )
        self.assertEqual(records["chr01"], sequence)
        self.assertEqual(filtered[0]["origin"]["object_id"], original[0]["object_id"])

    def test_missing_gap_origin_still_fails(self):
        sequence = "A" * 10 + "N" * 100 + "G" * 10
        gaps = engine.gap_objects("chr01", "q2", sequence)
        with self.assertRaisesRegex(SystemExit, "cannot map filtered Step3 gap"):
            engine.attach_gap_origins_from_paths(
                {"chr01": [self.source_segment(sequence)]}, gaps, gaps
            )
