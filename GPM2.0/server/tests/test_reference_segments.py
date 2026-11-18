import importlib.util
import random
import re
from unittest import mock
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "reference_segments.py"
SPEC = importlib.util.spec_from_file_location("reference_segments", MODULE_PATH)
REFERENCE_SEGMENTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFERENCE_SEGMENTS)


class ReferenceSegmentsTests(unittest.TestCase):
    def scan(self, fasta_bytes, chunk_size=7):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_path = root / "reference.fa"
            output_path = root / "reference_segments.tsv"
            input_path.write_bytes(fasta_bytes)
            REFERENCE_SEGMENTS.write_reference_segments(
                input_path, output_path, chunk_size=chunk_size
            )
            return output_path.read_bytes()

    def test_scans_wrapped_crlf_and_edge_case_records(self):
        fasta = (
            b">Chr01 description\r\n"
            + b"AAA\r\n"
            + b"n" * 50
            + b"\r\n"
            + b"N" * 50
            + b"\r\nCC\r\n"
            + b">empty\r\n"
            + b">all_n\r\n"
            + b"N" * 100
            + b"\r\n"
            + b">short_n\r\nNNN\r\n"
            + b">lower_n\r\nA"
            + b"n" * 100
            + b"T\r\n"
            + b">no_final_newline\r\nGG"
        )
        self.assertEqual(
            self.scan(fasta),
            (
                b"reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n"
                b"Chr01\t1\t1\t3\n"
                b"Chr01\t2\t104\t105\n"
                b"all_n\t0\t0\t0\n"
                b"short_n\t1\t1\t3\n"
                b"lower_n\t1\t1\t1\n"
                b"lower_n\t2\t102\t102\n"
                b"no_final_newline\t1\t1\t2\n"
            ),
        )

    def test_scans_unwrapped_multi_megabase_sequence_in_fixed_chunks(self):
        left_length = 1_100_003
        right_length = 1_200_005
        fasta = (
            b">ChrLarge\n"
            + b"A" * left_length
            + b"N" * 100
            + b"C" * right_length
        )
        self.assertEqual(
            self.scan(fasta, chunk_size=4096),
            (
                b"reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n"
                + f"ChrLarge\t1\t1\t{left_length}\n".encode("ascii")
                + (
                    f"ChrLarge\t2\t{left_length + 101}\t"
                    f"{left_length + 100 + right_length}\n"
                ).encode("ascii")
            ),
        )

    def test_wrapping_and_chunk_boundaries_match_whole_record_oracle(self):
        rng = random.Random(20261118)
        records = [("first", "Nn" * 50 + "ACGT" + "n" * 99),
                   ("middle", "A" + "N" * 100 + "T" + "n" * 101),
                   ("all_n", "Nn" * 80), ("empty", ""),
                   ("random", "".join(rng.choices("ACGTNn", k=500))),
                   ("literal_gt", "A>CN"), ("last", "AC" + "N" * 100)]
        expected = REFERENCE_SEGMENTS.HEADER
        for name, sequence in records:
            start, order = 1, 0
            for match in re.finditer(r"[Nn]{100,}", sequence):
                if match.start() >= start:
                    order += 1
                    expected += f"{name}\t{order}\t{start}\t{match.start()}\n"
                start = match.end() + 1
            if start <= len(sequence):
                order += 1
                expected += f"{name}\t{order}\t{start}\t{len(sequence)}\n"
            if sequence and not order:
                expected += f"{name}\t0\t0\t0\n"
        for width in (1, 7, 60, 1000):
            # Keep a literal '>' inside a sequence line rather than at line start.
            parts = []
            for name, sequence in records:
                parts.append(f">{name} description\r\n".encode())
                if name == "literal_gt":
                    parts.append(sequence.encode() + b"\r\n")
                else:
                    parts.extend(sequence[i:i + width].encode() + b" \t\r\n"
                                 for i in range(0, len(sequence), width))
            fasta = b"".join(parts).rstrip(b"\n")
            for chunk_size in (1, 2, 3, 7, 59, 60, 61, 101, 4096):
                with self.subTest(width=width, chunk_size=chunk_size):
                    self.assertEqual(self.scan(fasta, chunk_size), expected.encode())

    def test_sequence_consumption_is_bounded_by_chunks_not_lines(self):
        fasta = b">chr\n" + b"A\n" * 100000
        sizes = []
        original = REFERENCE_SEGMENTS.ReferenceSegmentScanner.consume_sequence

        def record(scanner, block):
            sizes.append(len(block))
            return original(scanner, block)

        with mock.patch.object(REFERENCE_SEGMENTS.ReferenceSegmentScanner, "consume_sequence", record):
            result = self.scan(fasta, chunk_size=4096)
        self.assertIn(b"chr\t1\t1\t100000\n", result)
        self.assertLessEqual(len(sizes), len(fasta) // 4096 + 2)
        self.assertLessEqual(max(sizes), 4096)

    def test_preserves_existing_output_when_sequence_precedes_header(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_path = root / "invalid.fa"
            output_path = root / "reference_segments.tsv"
            input_path.write_bytes(b"ACGT\n>Chr01\nAAAA\n")
            output_path.write_bytes(b"previous successful output\n")

            with self.assertRaisesRegex(
                REFERENCE_SEGMENTS.ReferenceSegmentsError,
                "sequence data appears before the first FASTA header",
            ):
                REFERENCE_SEGMENTS.write_reference_segments(
                    input_path, output_path, chunk_size=2
                )

            self.assertEqual(output_path.read_bytes(), b"previous successful output\n")
            self.assertEqual(list(root.glob(".reference_segments.tsv.*")), [])

    def test_rejects_empty_record_names(self):
        for header in (b">\n", b"> description\n", b">\tname\n"):
            with self.subTest(header=header):
                with self.assertRaisesRegex(
                    REFERENCE_SEGMENTS.ReferenceSegmentsError,
                    "FASTA record has an empty name",
                ):
                    self.scan(header + b"ACGT\n", chunk_size=1)


if __name__ == "__main__":
    unittest.main()
