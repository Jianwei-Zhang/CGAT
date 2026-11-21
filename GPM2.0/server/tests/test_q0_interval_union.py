import random
from pathlib import Path
import tempfile
import unittest

from server.tools.lgz_core.q0_catalog import (_IntervalUnion, CandidateCatalog,
    add_pairwise_candidates, build_catalog)
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_sources import Interval, SourceKey, merged_intervals, split_source


class IntervalUnionTests(unittest.TestCase):
    def test_repeated_unsorted_geometry_matches_full_union_without_filling_gaps(self):
        rng = random.Random(20261121)
        rows = [Interval(x, x + rng.randrange(1, 100)) for x in rng.choices(range(10000), k=20000)]
        acc = _IntervalUnion()
        for start in range(0, len(rows), 333):
            acc.extend(rows[start:start+333])
            if start % 999 == 0:
                self.assertEqual(tuple(acc), merged_intervals(rows[:start+333]))
        self.assertEqual(tuple(acc), merged_intervals(rows))
        self.assertEqual(tuple(acc), tuple(acc))
        gaps = _IntervalUnion(); gaps.extend([Interval(11, 20), Interval(0, 10)] * 2000)
        self.assertEqual(tuple(gaps), (Interval(0, 10), Interval(11, 20)))
        self.assertLess(len(gaps._pending), 1024)

    def test_already_represented_intervals_do_not_reenter_the_sort_buffer(self):
        acc = _IntervalUnion(); acc.extend([Interval(0, 10000)] * 1024)
        self.assertEqual(tuple(acc), (Interval(0, 10000),))
        for start in range(5000): acc.append(Interval(start, start + 5))
        self.assertEqual(acc._pending, [])
        # A new interval crossing a real gap must still fill only its own span.
        acc = _IntervalUnion(); acc.extend([Interval(0, 10), Interval(20, 30)])
        tuple(acc)
        acc.append(Interval(5, 25))
        self.assertEqual(tuple(acc), (Interval(0, 30),))

    def test_disjoint_geometry_scales_compaction_not_repeated_full_rescans(self):
        class CountingUnion(_IntervalUnion):
            def __init__(self): super().__init__(); self.compactions = 0
            def _compact(self):
                self.compactions += 1
                super()._compact()
        acc = CountingUnion()
        for x in range(100000): acc.append(Interval(3*x, 3*x+1))
        self.assertLess(acc.compactions, 20)
        self.assertEqual(len(tuple(acc)), 100000)
        self.assertEqual(tuple(acc)[-1], Interval(299997, 299998))

    def test_compaction_retains_all_pairwise_evidence_and_true_query_gaps(self):
        sources = {SourceKey("ds", key): "A" * 100 for key in ("q", "t")}
        parts = {p.segment_id: p for key, seq in sources.items() for p in split_source(key, seq).segments}
        ids = {p.source.contig: p.segment_id for p in parts.values()}
        catalog = CandidateCatalog({"candidates": [{"candidate_id": "anchor", "segment_id": ids["t"],
            "chromosome": "chr", "orientation": "+"}], "evidence": {}}, sources, parts)
        def hits():
            for i in range(1500):
                yield parse_paf_line(f"{ids['q']}\t100\t0\t100\t+\t{ids['t']}\t100\t0\t100\t90\t110\t60\tcg:Z:40M10I10D50M",
                                     artifact="repeated.paf", line_number=i+1)
        known = set()
        added = add_pairwise_candidates(catalog, hits(), {ids["q"]}, {ids["t"]}, known_pairs=known)
        self.assertEqual(added, {ids["q"]})
        derived = next(row for row in catalog.payload["candidates"] if row["candidate_id"] != "anchor")
        self.assertEqual(derived["query_intervals"], [[0, 40], [50, 100]])
        self.assertEqual(len(derived["pairwise_evidence_ids"]), 1500)
        self.assertEqual(len(catalog.payload["evidence"]), 1500)
        self.assertEqual(known, {tuple(sorted(sources))})

    def test_mapq_max_retains_unavailable_vs_zero_distinction(self):
        for mapqs, maximum in [([255], None), ([0, 255], 0), ([20, 60, 0, 255], 60)]:
            with self.subTest(mapqs=mapqs), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root / "runs/ds_vs_ref/result.paf"; path.parent.mkdir(parents=True)
                path.write_text("".join(f"q\t100\t0\t100\t+\tchr\t200\t0\t100\t100\t100\t{mq}\tcg:Z:100M\n" for mq in mapqs))
                catalog = build_catalog(root, {SourceKey("ds", "q"): "A" * 100}, {"chr": 200}, [])
                row = catalog.payload["candidates"][0]
                self.assertEqual(row["maximum_available_mapq"], maximum)
                self.assertEqual(len(row["reference_evidence_ids"]), len(mapqs))
                self.assertEqual(row["discovery_query_intervals"], [[0,100]] if maximum and maximum >= 20 else [])


if __name__ == "__main__": unittest.main()
