"""Small conversion/cache cases; no real long-read dataset conversion."""
import csv
import gzip
import io
from pathlib import Path
import tempfile
import unittest
from server.tools.refinement_reads import prepare_fasta, read_records
from server.tools.refinement_tools import ToolError


class RefinementReadsTests(unittest.TestCase):
    def test_wrapped_fastq_and_fasta_preserve_sequence_and_duplicate_original_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / "hifi.fastq.gz", root / "ont.fasta"
            with gzip.open(a, "wt") as stream:
                stream.write("@same\nacg\ntn\n+same\nIII\nII\n@same\nTG\n+\nII\n")
            b.write_text(">same\naac\nct\n")
            result = prepare_fasta([str(a), str(b)], root / "cache")
            with Path(result["fasta"]).open() as stream:
                records = list(read_records(stream))
            self.assertEqual([sequence for _, sequence in records], ["ACGTN", "TG", "AACCT"])
            self.assertEqual(len({name for name, _ in records}), 3)
            with gzip.open(Path(result["fasta"]).parent / "read_ids.tsv.gz", "rt") as stream:
                ids = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([row["original_id"] for row in ids], ["same", "same", "same"])
            self.assertEqual(result["reads"], 3)
            self.assertTrue(prepare_fasta([str(a), str(b)], root / "cache")["cache_hit"])

    def test_converted_file_names_cannot_collide_in_quartet_native_tmp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / "hifi.fq", root / "ont.fa"
            a.write_text("@r\nACG\n+\nIII\n")
            b.write_text(">r\nACG\n")
            first = prepare_fasta([str(a)], root / "cache")
            second = prepare_fasta([str(b)], root / "cache")
            self.assertNotEqual(Path(first["fasta"]).name, Path(second["fasta"]).name)

    def test_input_changes_create_new_conversion_and_tampered_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reads = root / "reads.fa"
            reads.write_text(">r\nAAA\n")
            first = prepare_fasta([str(reads)], root / "cache")
            Path(first["fasta"]).write_text(">fake\nCCC\n")
            with self.assertRaisesRegex(ToolError, "content changed"):
                prepare_fasta([str(reads)], root / "cache")
            reads.write_text(">r\nTTT\n")
            second = prepare_fasta([str(reads)], root / "cache")
            self.assertNotEqual(first["fasta"], second["fasta"])

    def test_invalid_fastq_is_not_silently_reinterpreted_as_fasta(self):
        for text in ("@r\nACG\n+\nII\n", "@r\nACG\n+different\nIII\n", "@r\nACG\n+\nIIII\n"):
            with self.assertRaises(ToolError):
                list(read_records(io.StringIO(text)))


if __name__ == "__main__":
    unittest.main()
