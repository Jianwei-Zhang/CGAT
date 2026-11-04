"""Short-repeat candidate policy, separate from real-MUMmer acceptance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from cen_scan import merge_hits, parse_coords


class CentromereCandidateTests(unittest.TestCase):
    def entries(self):
        return {name: {"cen_id": name, "provenance": json.dumps([
            {"source": "official", "id": name, "sha256": "0" * 64, "note": "evidence"}])}
                for name in ("a", "b")}

    def hit(self, start, end, query="a", contig="ctg", strand="+"):
        return {"start": start, "end": end, "query": query, "contig": contig,
                "strand": strand, "identity": 95.0, "weight": end-start+1}

    def test_short_hits_merge_across_entries_and_strands(self):
        rows = merge_hits([self.hit(1, 155), self.hit(156, 310, "b", strand="-")],
                          self.entries(), "chr1", "assembly", 300)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["align_length"], 310)
        self.assertEqual(len(json.loads(rows[0]["provenance"])), 2)
        self.assertEqual(rows[0]["mapq"], 0)

    def test_overlap_and_bridging_gap_do_not_inflate_support(self):
        hits = [self.hit(1, 155), self.hit(1, 155, "b"), self.hit(350, 500)]
        self.assertEqual(merge_hits(hits, self.entries(), "chr1", "asm", 307), [])
        rows = merge_hits(hits, self.entries(), "chr1", "asm", 300)
        self.assertEqual(rows[0]["align_length"], 306)
        self.assertEqual(rows[0]["region_length"], 500)

    def test_far_apart_or_different_contigs_never_merge(self):
        hits = [self.hit(1, 155), self.hit(1000, 1155), self.hit(156, 310, contig="other")]
        self.assertEqual(merge_hits(hits, self.entries(), "chr1", "asm", 200), [])

    def test_coords_are_query_coordinates_and_identity_filters_individual_hits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "coords"
            path.write_text("1\t155\t500\t346\t155\t155\t95.0\t155\t1000\t100.0\t15.5\ta\tctg\n"
                            "1\t155\t600\t754\t155\t155\t60.0\t155\t1000\t100.0\t15.5\ta\tctg\n")
            hits = parse_coords(path, self.entries(), 80)
            self.assertEqual(len(hits), 1)
            self.assertEqual((hits[0]["start"], hits[0]["end"], hits[0]["strand"]), (346, 500, "-"))


if __name__ == "__main__":
    unittest.main()
