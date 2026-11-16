import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalog_adaptive_inputs as cat
import prepare_adaptive_subset as subset


class SubsetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = b">a description\nacGT\n>b\nAAAA\nCCCC\n>c\nTNNN"
        self.source = self.root / "source.fa.gz"
        self.source.write_bytes(gzip.compress(self.raw))
        self.catalogue = self.root / "catalogue.json"
        self.data = {"status": "complete", **cat.catalogue(self.source)}
        self.catalogue.write_text(json.dumps(self.data))
        self.out = self.root / "subset"

    def test_whole_reference_byte_identity(self):
        r = subset.prepare(self.catalogue, self.out)
        self.assertEqual((self.out / "input.fa").read_bytes(), self.raw)
        self.assertEqual(r["output_sha256"], self.data["decompressed_sha256"])

    def test_selected_records_preserve_source_order_and_bytes(self):
        r = subset.prepare(self.catalogue, self.out, ["c", "a"])
        self.assertEqual((self.out / "input.fa").read_bytes(), b">a description\nacGT\n>c\nTNNN")
        self.assertEqual([x["name"] for x in r["records"]], ["a", "c"])
        self.assertEqual(r["selected_bases"], 8)

    def test_missing_or_duplicate_selection_creates_no_output(self):
        for names in (["unknown"], ["a", "a"], []):
            with self.assertRaises(ValueError):
                subset.prepare(self.catalogue, self.out, names)
            self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        subset.prepare(self.catalogue, self.out, ["a"])
        with self.assertRaises(FileExistsError):
            subset.prepare(self.catalogue, self.out, ["b"])

    def test_incomplete_catalogue_rejected(self):
        self.catalogue.write_text('{"status":"running"}')
        with self.assertRaises(ValueError):
            subset.prepare(self.catalogue, self.out)

    def test_changed_source_rejected_by_content_before_publication(self):
        self.source.write_bytes(gzip.compress(self.raw + b"A"))
        with self.assertRaises(ValueError):
            subset.prepare(self.catalogue, self.out)
        self.assertFalse((self.out / "input.fa").exists())

    def test_cross_node_device_change_uses_content_not_metadata(self):
        self.data["source_identity"]["device"] += 100
        self.data["source_identity"]["ctime_ns"] += 100
        self.catalogue.write_text(json.dumps(self.data))
        r = subset.prepare(self.catalogue, self.out, ["a"])
        self.assertEqual(r["status"], "complete")
        self.assertEqual(set(r["source_metadata_changes"]), {"device", "ctime_ns"})
        self.assertEqual(r["source_decompressed_sha256"], self.data["decompressed_sha256"])

    def test_same_length_changed_content_is_rejected(self):
        self.source.write_bytes(gzip.compress(self.raw.replace(b"acGT", b"TCGA")))
        with self.assertRaises(ValueError):
            subset.prepare(self.catalogue, self.out, ["b"])
        self.assertFalse((self.out / "input.fa").exists())

    def test_change_during_read_is_still_rejected(self):
        before = cat.identity(self.source)
        after = {**before, "mtime_ns": before["mtime_ns"] + 1}
        with patch.object(cat, "identity", side_effect=[before, after]):
            with self.assertRaises(ValueError):
                subset.prepare(self.catalogue, self.out)
        self.assertFalse((self.out / "input.fa").exists())

    def test_forged_selected_hash_never_publishes(self):
        self.data["records"][0]["sequence_sha256"] = "0" * 64
        self.catalogue.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):
            subset.prepare(self.catalogue, self.out, ["a"])
        self.assertFalse((self.out / "input.fa").exists())
        self.assertEqual(json.loads((self.out / "subset.json").read_text())["status"], "failed")

    def test_full_stream_hash_checked_even_for_unselected_records(self):
        self.data["decompressed_sha256"] = "0" * 64
        self.catalogue.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):
            subset.prepare(self.catalogue, self.out, ["a"])
        self.assertFalse((self.out / "input.fa").exists())


if __name__ == "__main__":
    unittest.main()
