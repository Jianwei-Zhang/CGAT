"""Pure q0 evidence tests: source provenance and exact coordinate geometry."""
from dataclasses import asdict
from pathlib import Path
import random
import tempfile
import unittest

from server.tools.lgz_core.common import reverse_complement, sha256_bytes
from server.tools.lgz_core.q0_sources import (
    Interval, Q0EvidenceError, SourceKey, merged_intervals,
    split_source, subtract_intervals,
)
from server.tools.lgz_core.q0_alignments import (
    parse_paf_line, project_query_interval, project_target_interval, read_paf,
)


def paf(ops=((20, "M"),), *, strand="+", qs=10, ts=100, mapq=60, extra=()):
    qspan = sum(n for n, op in ops if op in "MI=X")
    tspan = sum(n for n, op in ops if op in "MDN=X")
    fields = ["q", qs + qspan + 7, qs, qs + qspan, strand, "chr1",
              ts + tspan + 9, ts, ts + tspan,
              sum(n for n, op in ops if op in "M="), sum(n for n, op in ops), mapq,
              "cg:Z:" + "".join(f"{n}{op}" for n, op in ops), *extra]
    return "\t".join(map(str, fields))


def hit(ops=((20, "M"),), **kwargs):
    return parse_paf_line(paf(ops, **kwargs), artifact="runs/evidence.paf", line_number=3)


class SourceIntervalTests(unittest.TestCase):
    def test_coordinate_conversion_and_reverse_roundtrip(self):
        interval = Interval(5, 13)
        self.assertEqual(interval.inclusive(), (6, 13))
        self.assertEqual(Interval.from_inclusive(*interval.inclusive()), interval)
        sequence = "ACGTRYSWKMBDHVNACGT"
        forward = sequence[interval.start:interval.end]
        self.assertEqual(reverse_complement(reverse_complement(forward)), forward)

    def test_invalid_coordinates_do_not_coerce(self):
        for start, end in [(-1, 3), (0, 0), (5, 3), (True, 3), (0, 3.0)]:
            with self.subTest(start=start, end=end), self.assertRaises(Q0EvidenceError):
                Interval(start, end)
        for start, end in [(0, 1), (True, 5), (1.0, 4), (4, 3)]:
            with self.subTest(start=start, end=end), self.assertRaises(Q0EvidenceError):
                Interval.from_inclusive(start, end)

    def test_coverage_is_union_not_sum_or_hull(self):
        intervals = [Interval(0, 10), Interval(3, 12), Interval(20, 25), Interval(25, 27)]
        self.assertEqual(merged_intervals(intervals), (Interval(0, 12), Interval(20, 27)))
        self.assertEqual(sum(i.length for i in merged_intervals(intervals)), 19)

    def test_unused_intervals_survive_overlapping_occupancy(self):
        occupied = [Interval(0, 15), Interval(12, 20), Interval(30, 35), Interval(45, 60)]
        self.assertEqual(subtract_intervals(Interval(10, 50), occupied),
                         (Interval(20, 30), Interval(35, 45)))
        self.assertEqual(subtract_intervals(Interval(10, 50), []), (Interval(10, 50),))
        self.assertEqual(subtract_intervals(Interval(10, 50), [Interval(0, 60)]), ())
        self.assertEqual(subtract_intervals(Interval(10, 50), [Interval(0, 10), Interval(50, 60)]),
                         (Interval(10, 50),))

    def test_long_n_split_keeps_original_coordinates_and_adjacency(self):
        sequence = "A" * 80 + "N" * 500 + "C" * 60
        index = split_source(SourceKey("dsA", "c1"), sequence)
        self.assertEqual([s.interval for s in index.segments], [Interval(0, 80), Interval(580, 640)])
        self.assertEqual(index.sequence_sha256, sha256_bytes(sequence.encode()))
        self.assertEqual(index.gaps[0].interval.length, 500)
        link = index.adjacencies[0]
        self.assertEqual(link.kind, "input_assembly_gap")
        self.assertEqual(link.left_segment_id, index.segments[0].segment_id)
        self.assertEqual(link.right_segment_id, index.segments[1].segment_id)
        self.assertEqual(link.gap_interval, Interval(80, 580))
        self.assertEqual(link.gap_id, index.gaps[0].gap_id)
        for part in index.segments:
            self.assertEqual(part.sequence_sha256, sha256_bytes(sequence[part.interval.start:part.interval.end].encode()))
        self.assertEqual(len(sequence), 640)  # indexing does not rewrite source

    def test_exact_threshold_and_short_n_quality_information(self):
        index = split_source(SourceKey("a", "c"), "A" + "N" * 99 + "C" + "N" * 100 + "G")
        self.assertEqual(len(index.segments), 2)
        self.assertEqual(index.segments[0].n_bp, 99)
        self.assertEqual(index.segments[1].n_bp, 0)
        self.assertEqual(len(index.adjacencies), 1)
        self.assertEqual(index.segments[0].left_boundary, "record_start")
        self.assertEqual(index.segments[0].right_boundary, "long_n")
        self.assertEqual(index.segments[1].right_boundary, "record_end")

    def test_terminal_and_all_n_runs_do_not_create_empty_nodes_or_links(self):
        index = split_source(SourceKey("a", "c"), "N" * 100 + "ACGT" + "N" * 101)
        self.assertEqual([s.interval for s in index.segments], [Interval(100, 104)])
        self.assertEqual(len(index.gaps), 2)
        self.assertEqual(index.adjacencies, ())
        self.assertFalse(any(gap.is_internal for gap in index.gaps))
        all_n = split_source(SourceKey("a", "n"), "N" * 100)
        self.assertEqual(all_n.segments, ())
        self.assertEqual(all_n.adjacencies, ())
        self.assertEqual(len(all_n.gaps), 1)
        self.assertIsNone(all_n.gaps[0].left_segment_id)
        self.assertIsNone(all_n.gaps[0].right_segment_id)

    def test_all_source_bases_are_indexed_once(self):
        rng = random.Random(718)
        for _ in range(50):
            sequence = "".join(rng.choice(["A", "CG", "NN", "N" * 100, "N" * 101]) for _ in range(15))
            index = split_source(SourceKey("ds", "ctg"), sequence)
            intervals = sorted([s.interval for s in index.segments] + [g.interval for g in index.gaps])
            cursor = 0
            for interval in intervals:
                self.assertEqual(interval.start, cursor)
                cursor = interval.end
            self.assertEqual(cursor, len(sequence))
            self.assertEqual(len(index.adjacencies), sum(g.is_internal for g in index.gaps))

    def test_source_ids_do_not_depend_on_input_order(self):
        inputs = [(SourceKey("b", "same"), "ACGT"), (SourceKey("a", "same"), "ACGT")]
        forward = {key: asdict(split_source(key, seq)) for key, seq in inputs}
        backward = {key: asdict(split_source(key, seq)) for key, seq in reversed(inputs)}
        self.assertEqual(forward, backward)
        self.assertNotEqual(forward[inputs[0][0]]["segments"][0]["segment_id"],
                            forward[inputs[1][0]]["segments"][0]["segment_id"])

    def test_lowercase_matches_existing_reader_semantics(self):
        self.assertEqual(split_source(SourceKey("a", "c"), "acgtnnn", min_gap=3),
                         split_source(SourceKey("a", "c"), "ACGTNNN", min_gap=3))

    def test_invalid_inputs_fail_not_silently_disappear(self):
        for sequence in ["", "ACGT!", "A C", "A\nC"]:
            with self.subTest(sequence=sequence), self.assertRaises(Q0EvidenceError):
                split_source(SourceKey("a", "c"), sequence)
        for minimum in [0, -1, True, 2.5]:
            with self.subTest(minimum=minimum), self.assertRaises(Q0EvidenceError):
                split_source(SourceKey("a", "c"), "ACGT", min_gap=minimum)
        for key in [("", "c"), ("a", ""), ("a", "c t")]:
            with self.subTest(key=key), self.assertRaises(Q0EvidenceError):
                SourceKey(*key)


class AlignmentEvidenceTests(unittest.TestCase):
    def test_evidence_identity_and_optional_tags_are_retained(self):
        alignment = hit(extra=("tp:A:S", "AS:i:20"))
        self.assertEqual(alignment.artifact, "runs/evidence.paf")
        self.assertEqual(alignment.line_number, 3)
        self.assertIn("tp:A:S", alignment.tags)
        self.assertEqual(alignment, hit(extra=("tp:A:S", "AS:i:20")))
        self.assertNotEqual(alignment.evidence_id, hit(extra=("tp:A:P", "AS:i:20")).evidence_id)

    def test_unknown_mapq_is_not_high_confidence(self):
        self.assertIsNone(hit(mapq=255).mapping_quality)
        self.assertEqual(hit(mapq=0).mapping_quality, 0)
        self.assertEqual(hit(mapq=60).mapping_quality, 60)

    def test_paf_requires_exactly_one_valid_cigar(self):
        base = paf()
        invalid = [base.rsplit("\t", 1)[0], base + "\tcg:Z:20M",
                   base.replace("20M", "0M"), base.replace("20M", "19M"),
                   base.replace("20M", "10S10M"), base.replace("20M", "020M"),
                   base.replace("20M", "20Mgarbage"), "q\t1\t0"]
        for text in invalid:
            with self.subTest(text=text), self.assertRaisesRegex(Q0EvidenceError, "evidence.paf:3"):
                parse_paf_line(text, artifact="evidence.paf", line_number=3)

    def test_invalid_fields_bounds_and_statistics_fail(self):
        for index, value in [(1, "nan"), (1, "20"), (2, "-1"), (3, "10"),
                             (4, "?"), (6, "119"), (7, "-1"), (8, "100"),
                             (9, "21"), (9, "-1"), (10, "0"), (11, "256"), (0, "q q")]:
            fields = paf().split("\t")
            fields[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(Q0EvidenceError):
                parse_paf_line("\t".join(fields), artifact="bad.paf", line_number=1)

    def test_both_strands_project_in_original_source_coordinates(self):
        for strand, expected in [("+", Interval(12, 18)), ("-", Interval(22, 28))]:
            alignment = hit(strand=strand)
            result = project_target_interval(alignment, Interval(102, 108))
            self.assertTrue(result.exact)
            self.assertEqual(result.interval, expected)
            self.assertEqual(result.aligned_bp, 6)
            self.assertEqual(project_query_interval(alignment, expected).interval, Interval(102, 108))

    def test_projection_uses_cigar_not_linear_scaling(self):
        alignment = hit(((5, "M"), (8, "I"), (10, "M")))
        self.assertEqual(project_target_interval(alignment, Interval(106, 110)).interval, Interval(24, 28))
        result = project_target_interval(alignment, Interval(102, 110))
        self.assertEqual(result.interval, Interval(12, 28))
        self.assertEqual(result.aligned_bp, 8)
        self.assertEqual(project_query_interval(alignment, result.interval).interval, Interval(102, 110))

    def test_insertion_boundary_is_not_arbitrarily_assigned_to_a_side(self):
        alignment = hit(((5, "M"), (8, "I"), (10, "M")))
        for interval in (Interval(100, 105), Interval(105, 110)):
            result = project_target_interval(alignment, interval)
            self.assertFalse(result.exact)
            self.assertIsNone(result.interval)
            self.assertEqual(result.status, "ambiguous_indel_boundary")
        result = project_query_interval(alignment, Interval(16, 26))
        self.assertEqual(result.status, "inside_alignment_gap")

    def test_deletion_boundary_and_unaligned_interiors_are_distinguished(self):
        alignment = hit(((5, "M"), (8, "D"), (10, "M")))
        self.assertEqual(project_query_interval(alignment, Interval(10, 15)).status,
                         "ambiguous_indel_boundary")
        self.assertEqual(project_target_interval(alignment, Interval(108, 120)).status,
                         "inside_alignment_gap")
        self.assertEqual(project_target_interval(alignment, Interval(105, 113)).status,
                         "no_paired_bases")
        result = project_target_interval(alignment, Interval(102, 120))
        self.assertTrue(result.exact)
        self.assertEqual(result.interval, Interval(12, 22))
        self.assertEqual(result.aligned_bp, 10)

    def test_target_skip_is_not_reported_as_continuous_coverage(self):
        alignment = hit(((5, "="), (100, "N"), (3, "X"), (7, "=")))
        blocks = list(alignment.aligned_blocks())
        self.assertEqual(sum(b.target.length for b in blocks), 15)
        result = project_target_interval(alignment, alignment.target)
        self.assertTrue(result.exact)  # coordinates only, not bridge authorization
        self.assertEqual(result.target_skip_bp, 100)
        self.assertEqual(result.aligned_bp, 15)
        self.assertEqual(result.interval, alignment.query)

    def test_outside_hit_does_not_extrapolate(self):
        for strand in ("+", "-"):
            alignment = hit(strand=strand)
            self.assertEqual(project_target_interval(alignment, Interval(90, 110)).status, "outside_alignment")
            self.assertEqual(project_query_interval(alignment, Interval(5, 15)).status, "outside_alignment")

    def test_terminal_indels_do_not_become_unique_cut_sites(self):
        for ops in [((3, "I"), (8, "M")), ((8, "M"), (3, "I"))]:
            alignment = hit(ops)
            self.assertEqual(project_target_interval(alignment, alignment.target).status, "ambiguous_indel_boundary")
        for ops in [((3, "D"), (8, "M")), ((8, "M"), (3, "D"))]:
            alignment = hit(ops)
            self.assertEqual(project_target_interval(alignment, alignment.target).status, "no_paired_boundary")

    def test_reader_keeps_all_reference_targets_and_secondary_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hits.paf"
            first = paf(extra=("tp:A:P",))
            second = paf(extra=("tp:A:S",)).replace("chr1", "chr2")
            path.write_text("# evidence\n\n" + first + "\n" + second + "\n")
            hits = list(read_paf(path, query_lengths={"q": 37}, target_lengths={"chr1": 129, "chr2": 129}))
            self.assertEqual([h.target_name for h in hits], ["chr1", "chr2"])
            self.assertEqual([h.line_number for h in hits], [3, 4])
            with self.assertRaisesRegex(Q0EvidenceError, "names/lengths"):
                list(read_paf(path, query_lengths={"q": 37}, target_lengths={"chr1": 129}))
            with self.assertRaisesRegex(Q0EvidenceError, "names/lengths"):
                list(read_paf(path, query_lengths={"q": 38}, target_lengths={"chr1": 129, "chr2": 129}))

    def test_empty_results_are_distinct_from_missing_or_unreadable_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hits.paf"
            with self.assertRaises(Q0EvidenceError):
                list(read_paf(path, query_lengths={}, target_lengths={}))
            path.write_text("")
            self.assertEqual(list(read_paf(path, query_lengths={}, target_lengths={})), [])
            path.write_bytes(b"\xff")
            with self.assertRaises(Q0EvidenceError):
                list(read_paf(path, query_lengths={}, target_lengths={}))

    def test_projection_matches_independent_per_base_path_oracle(self):
        # The implementation walks CIGAR runs; this small oracle walks every
        # grid step, including alternative cut positions across insertions.
        rng = random.Random(541)
        for case in range(35):
            ops = [(2, "M"), *[(rng.randint(1, 3), rng.choice("M=XIDN")) for _ in range(4)], (2, "M")]
            q, t = 0, 0
            points = {(q, t)}
            paired_points = set()
            for n, op in ops:
                for _ in range(n):
                    if op in "M=X":
                        paired_points.add((q, t))
                    q += int(op in "MI=X")
                    t += int(op in "MDN=X")
                    points.add((q, t))
                    if op in "M=X":
                        paired_points.add((q, t))
            for strand in ("+", "-"):
                alignment = hit(tuple(ops), strand=strand)
                for from_query, span in [(True, q), (False, t)]:
                    for start in range(span):
                        for end in range(start + 1, span + 1):
                            axis = 0 if from_query else 1
                            left = {p[1-axis] for p in points if p[axis] == start}
                            right = {p[1-axis] for p in points if p[axis] == end}
                            supported = all(any(p[axis] == v for p in paired_points) for v in (start, end))
                            exact = (supported and len(left) == len(right) == 1
                                     and next(iter(left)) < next(iter(right)))
                            if from_query:
                                region = (Interval(alignment.query.start + start, alignment.query.start + end)
                                          if strand == "+" else Interval(alignment.query.end - end, alignment.query.end - start))
                                result = project_query_interval(alignment, region)
                            else:
                                region = Interval(alignment.target.start + start, alignment.target.start + end)
                                result = project_target_interval(alignment, region)
                            with self.subTest(case=case, strand=strand, query=from_query, interval=region):
                                self.assertEqual(result.exact, exact)
                                if exact:
                                    lo, hi = next(iter(left)), next(iter(right))
                                    expected = (Interval(alignment.target.start + lo, alignment.target.start + hi)
                                                if from_query else
                                                (Interval(alignment.query.start + lo, alignment.query.start + hi)
                                                 if strand == "+" else Interval(alignment.query.end - hi, alignment.query.end - lo)))
                                    self.assertEqual(result.interval, expected)


if __name__ == "__main__":
    unittest.main()
