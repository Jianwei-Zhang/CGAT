"""Focused refill batching/cache safety tests; real PAF equality runs on 180."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from server.tools.grt_core.common import sha256_file
from server.tools.grt_core.refill_batch import RefillBatchAlignment
from server.tools.grt_core.stage_cache import cached_chromosome_alignment, fasta_bytes


class RefillBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        target = self.root / "donor.fa"
        target.write_text(">donor\n" + "A" * 1000 + "\n")
        self.donor = {"donor_set_id": "d0-test", "fasta_relpath": "donor.fa",
                      "fasta_sha256": sha256_file(target)}
        self.tool = self.root / "minimap2"
        self.tool.write_text(r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
root = Path(__file__).parent
with (root / 'calls.log').open('a') as log: log.write(json.dumps(args) + '\n')
if '-d' in args: Path(args[args.index('-d')+1]).write_text('valid-test-index')
queries = []
for line in Path(args[-1]).read_text().splitlines():
 if line.startswith('>'): queries.append(line[1:].split()[0])
rows = []
pairs = [(name,offset,kind) for name in queries for offset,kind in [(0,'P'),(100,'S')]]
if os.environ.get('FAKE_SPLIT_INDEX'):
 pairs = [(name,offset,kind) for offset,kind in [(0,'P'),(100,'S')] for name in queries]
for name,offset,kind in pairs:
  rows.append(f'{name}\t100\t0\t100\t+\tdonor\t1000\t{offset}\t{offset+100}\t100\t100\t60\ttp:A:{kind}\tcg:Z:100M')
Path(args[args.index('-o')+1]).write_text('\n'.join(rows)+'\n')
''')
        self.tool.chmod(0o755)
        self.minimap = {"resolved": str(self.tool), "version": "test", "sha256": sha256_file(self.tool)}
        self.records = [(f"chr{chromosome}__{side}", "A" * 100)
                        for chromosome in (1, 2) for side in ("L", "R")]
        self.query_map = {name: ({"object_id": name.split("__")[0], "chr": name.split("__")[0]}, name[-1])
                          for name, _seq in self.records}

    def provider(self, label, records=None):
        return RefillBatchAlignment(self.root, f"step3_refill_{label}", self.donor,
                                   self.minimap, 2, records or self.records,
                                   self.query_map, {"donor": 1000}, self.root / f"artifact-{label}")

    def emit(self, provider, label, names):
        directory = self.root / label
        directory.mkdir()
        query = directory / "flanks.fa"
        query.write_bytes(fasta_bytes([(name, "A" * 100) for name in names]))
        provider(query, directory / "result.paf", directory)
        return (directory / "result.paf").read_text().splitlines()

    def calls(self):
        path = self.root / "calls.log"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_one_batch_restores_query_order_and_preserves_secondary_cigar(self):
        batch = self.provider("round1")
        first = self.emit(batch, "chr1", ["chr1__L", "chr1__R"])
        second = self.emit(batch, "chr2", ["chr2__L", "chr2__R"])
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual([row.split('\t')[0] for row in first], ["chr1__L"] * 2 + ["chr1__R"] * 2)
        self.assertEqual(len(second), 4)
        self.assertTrue(all("cg:Z:100M" in row for row in first + second))
        self.assertIn("tp:A:S", first[1])
        self.assertIn("-d", self.calls()[0])
        self.assertTrue((self.root / "artifact-round1/provenance.json").is_file())
        second_round = self.provider("round2")
        self.emit(second_round, "round2-chr1", ["chr1__L", "chr1__R"])
        self.assertNotIn("-d", self.calls()[1])
        self.assertTrue(self.calls()[1][-2].endswith("target.mmi"))
        self.assertTrue(second_round.provenance["index_cache_hit"])

    def test_multi_part_index_retains_part_then_query_order(self):
        with patch.dict(os.environ, {"FAKE_SPLIT_INDEX": "1"}):
            lines = self.emit(self.provider("multipart"), "multipart-output", ["chr1__L", "chr1__R"])
        self.assertEqual([row.split('\t')[0] for row in lines],
                         ["chr1__L", "chr1__R", "chr1__L", "chr1__R"])
        self.assertEqual(len(self.calls()), 1)

    def test_existing_chromosome_cache_does_not_trigger_a_batch(self):
        parameters = {"preset": "asm5", "cigar": True, "threads": 2}
        for number in (1, 2):
            batch = self.provider(f"cache-attempt-{number}")
            path, hit, _key = cached_chromosome_alignment(
                self.root, "step3_refill_stable", "chr1", "q-input", "q-chr", [],
                self.records[:2], {k: v for k, v in self.query_map.items() if k.startswith("chr1")},
                self.donor, True, {"donor": 1000}, self.minimap, parameters, 2,
                cache_scope="step23", alignment_runner=batch)
            self.assertEqual(hit, number == 2)
            self.assertTrue((path / "result.paf").is_file())
            if hit:
                self.assertIsNone(batch.rows)
        self.assertEqual(len(self.calls()), 1)

    def test_corrupt_index_is_rebuilt_for_a_new_batch(self):
        self.emit(self.provider("first"), "first-output", ["chr1__L"])
        index = next((self.root / "grt/cache/minimap_index/v1").glob("*/target.mmi"))
        index.write_text("corrupted")
        self.emit(self.provider("second"), "second-output", ["chr1__L"])
        self.assertIn("-d", self.calls()[1])
        self.assertEqual(index.read_text(), "valid-test-index")

    def test_failure_cannot_publish_success_and_retry_releases_locks(self):
        with patch("server.tools.grt_core.refill_batch.subprocess.run", side_effect=subprocess.CalledProcessError(1, "minimap2")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.emit(self.provider("failed"), "failed-output", ["chr1__L"])
        self.assertFalse(list((self.root / "grt/cache").rglob("cache.json")))
        self.assertTrue(list((self.root / "grt/failed").iterdir()))
        self.emit(self.provider("retry"), "retry-output", ["chr1__L"])
        self.assertEqual(len(self.calls()), 1)

    def test_duplicate_ids_fail_before_mapping(self):
        with self.assertRaises(SystemExit):
            self.emit(self.provider("duplicate", self.records + self.records[:1]), "duplicate-output", ["chr1__L"])
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
