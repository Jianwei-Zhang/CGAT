import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

import catalog_adaptive_inputs as c


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_wrapping_case_and_gzip_identity(self):
        plain, zipped = self.root / "a.fa", self.root / "a.fa.gz"
        plain.write_bytes(b">q description\nacgT\nNN\n>r\nAC\n")
        zipped.write_bytes(gzip.compress(plain.read_bytes()))
        a, b = c.catalogue(plain), c.catalogue(zipped)
        self.assertEqual(a["records"], b["records"])
        self.assertEqual(b["gzip_integrity"], "verified_to_EOF")
        self.assertEqual(b["decompressed_sha256"], hashlib.sha256(plain.read_bytes()).hexdigest())
        self.assertEqual(a["records"][0]["sequence_sha256"], hashlib.sha256(b"ACGTNN").hexdigest())
        self.assertEqual((a["total_bases"], a["n_bases"], a["n50_bases"]), (8, 2, 6))

    def test_unwrapped_line_larger_than_buffer(self):
        p = self.root / "a.fa"
        p.write_bytes(b">q\n" + b"A" * (c.BLOCK + 7) + b"\n")
        self.assertEqual(c.catalogue(p)["total_bases"], c.BLOCK + 7)

    def test_truncated_gzip_is_not_complete(self):
        p = self.root / "a.fa.gz"
        p.write_bytes(gzip.compress(b">q\nACGT\n")[:-5])
        with self.assertRaises((EOFError, OSError)):
            c.catalogue(p)

    def test_duplicate_empty_invalid_sequences_rejected(self):
        p = self.root / "a.fa"
        for raw in (b">q\nA\n>q\nA\n", b">q\n", b">q\nAX\n", b"ACGT\n", b""):
            p.write_bytes(raw)
            with self.assertRaises(ValueError):
                c.catalogue(p)

    def test_no_trailing_newline(self):
        p = self.root / "a.fa"
        p.write_bytes(b">q\nACGT")
        self.assertEqual(c.catalogue(p)["total_bases"], 4)

    def test_output_cannot_overwrite_input_or_prior_receipt(self):
        p = self.root / "a.fa"
        p.write_bytes(b">q\nACGT\n")
        with self.assertRaises(FileExistsError):
            c.main(["--input", str(p), "--output", str(p)])
        self.assertEqual(p.read_bytes(), b">q\nACGT\n")


if __name__ == "__main__":
    unittest.main()
