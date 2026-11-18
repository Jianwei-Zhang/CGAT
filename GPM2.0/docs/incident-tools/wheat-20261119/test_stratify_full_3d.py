import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
import stratify_full_3d as stratify


def rows(mapq):
    return "".join(f"{name}\t{length}\t0\t10\t+\tt\t100\t0\t10\t10\t10\t{mapq}\ttp:A:P\tcg:Z:10M\n"
                   for name, length in (("long", 100_000_000), ("short", 99_999_999)))


class StratificationTests(unittest.TestCase):
    def evaluate(self, native_quality, candidate_quality):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root / "work"
            here = root / "seed-filter-full-3D-pilot-20261119"
            native = work / "native/result.paf"; candidate = here / "f0005/result.paf"
            native.parent.mkdir(parents=True); candidate.parent.mkdir(parents=True)
            native.write_text(rows(native_quality)); candidate.write_text(rows(candidate_quality))
            marker = root / "native-checkpoint.json"
            marker.write_text(json.dumps({"outputs": [{"path": "native/result.paf", "sha256": hashlib.sha256(native.read_bytes()).hexdigest()}]}))
            (here / "result.json").write_text(json.dumps({"status": "candidate_and_native_compared_not_adopted",
                "native_leaf_checkpoint": str(marker), "outputs": [{"path": "f0005/result.paf",
                "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}]}))
            with patch.multiple(stratify, ROOT=root, WORK=work), patch("builtins.print"):
                stratify.main()
            return {(row["group"], row["minimum_baseline_mapq"]): row
                    for row in json.loads((here / "stratified-comparisons.json").read_text())}

    def test_length_boundary_partitions_queries_and_lower_candidate_mapq_keeps_geometry(self):
        rows = self.evaluate(60, 0)
        self.assertEqual(rows[("long_query_ge100M", 0)]["baseline_anchor_count"], 1)
        self.assertEqual(rows[("short_query_lt100M", 0)]["baseline_anchor_count"], 1)
        self.assertEqual(rows[("all", 60)]["baseline_anchors_supported_within_0bp"], 2)

    def test_no_high_quality_baseline_is_reported_as_no_evidence(self):
        rows = self.evaluate(0, 60)
        self.assertEqual(rows[("all", 60)]["baseline_anchor_count"], 0)
        self.assertEqual(rows[("all", 60)]["candidate_anchor_count"], 2)
        self.assertEqual(rows[("all", 60)]["baseline_anchors_supported_within_0bp"], 0)


if __name__ == "__main__":
    unittest.main()
