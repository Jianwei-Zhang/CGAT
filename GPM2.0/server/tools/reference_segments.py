#!/usr/bin/env python3

import argparse
import os
import re
import tempfile
from pathlib import Path


HEADER = (
    "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n"
)
DEFAULT_CHUNK_SIZE = 1024 * 1024
MIN_GAP_RUN_BP = 100
HEADER_WHITESPACE = re.compile(br"[ \t\r\v\f]")
SEQUENCE_WHITESPACE = b" \t\r\n\v\f"
N_RUN = re.compile(br"[Nn]+")


class ReferenceSegmentsError(ValueError):
    pass


class ReferenceSegmentScanner:
    def __init__(self, output_handle, min_gap_run_bp=MIN_GAP_RUN_BP):
        if min_gap_run_bp < 1:
            raise ValueError("min_gap_run_bp must be positive")
        self.output_handle = output_handle
        self.min_gap_run_bp = min_gap_run_bp
        self.current_name = None
        self.sequence_bp = 0
        self.segment_order = 0
        self.segment_start_bp = 1
        self.gap_start_bp = 0
        self.gap_run_length = 0

    def start_record(self, raw_header):
        self.finish_record()
        match = HEADER_WHITESPACE.search(raw_header)
        raw_name = raw_header[: match.start()] if match else raw_header
        if not raw_name:
            raise ReferenceSegmentsError("FASTA record has an empty name")
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReferenceSegmentsError(
                "FASTA record name is not valid UTF-8"
            ) from error
        self.current_name = name
        self.sequence_bp = 0
        self.segment_order = 0
        self.segment_start_bp = 1
        self.gap_start_bp = 0
        self.gap_run_length = 0

    def consume_sequence(self, raw_sequence):
        sequence = raw_sequence.translate(None, SEQUENCE_WHITESPACE)
        if not sequence:
            return
        if self.current_name is None:
            raise ReferenceSegmentsError("sequence data appears before the first FASTA header")

        cursor = 0
        for match in N_RUN.finditer(sequence):
            if match.start() > cursor:
                self.close_gap_if_needed(self.sequence_bp + 1)
                self.sequence_bp += match.start() - cursor
            if self.gap_run_length == 0:
                self.gap_start_bp = self.sequence_bp + 1
            run_length = match.end() - match.start()
            self.sequence_bp += run_length
            self.gap_run_length += run_length
            cursor = match.end()

        if cursor < len(sequence):
            self.close_gap_if_needed(self.sequence_bp + 1)
            self.sequence_bp += len(sequence) - cursor

    def close_gap_if_needed(self, next_bp):
        if self.gap_run_length >= self.min_gap_run_bp:
            self.emit_segment(self.gap_start_bp - 1)
            self.segment_start_bp = next_bp
        self.gap_start_bp = 0
        self.gap_run_length = 0

    def emit_segment(self, end_bp):
        if self.current_name is None or end_bp < self.segment_start_bp:
            return
        self.segment_order += 1
        self.output_handle.write(
            f"{self.current_name}\t{self.segment_order}\t"
            f"{self.segment_start_bp}\t{end_bp}\n"
        )

    def finish_record(self):
        if self.current_name is None:
            return
        if self.gap_run_length:
            self.close_gap_if_needed(self.sequence_bp + 1)
        self.emit_segment(self.sequence_bp)
        self.current_name = None


def scan_fasta(input_path, output_handle, chunk_size=DEFAULT_CHUNK_SIZE):
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    scanner = ReferenceSegmentScanner(output_handle)
    header_buffer = None
    at_line_start = True

    with input_path.open("rb") as input_handle:
        while True:
            chunk = input_handle.read(chunk_size)
            if not chunk:
                break
            offset = 0
            while offset < len(chunk):
                if header_buffer is not None:
                    newline = chunk.find(b"\n", offset)
                    if newline < 0:
                        header_buffer.extend(chunk[offset:])
                        offset = len(chunk)
                        continue
                    header_buffer.extend(chunk[offset:newline])
                    scanner.start_record(bytes(header_buffer))
                    header_buffer = None
                    offset = newline + 1
                    at_line_start = True
                    continue

                if at_line_start and chunk[offset] == ord(">"):
                    header_buffer = bytearray()
                    offset += 1
                    at_line_start = False
                    continue

                newline = chunk.find(b"\n", offset)
                if newline < 0:
                    scanner.consume_sequence(chunk[offset:])
                    offset = len(chunk)
                    at_line_start = False
                    continue
                scanner.consume_sequence(chunk[offset:newline])
                offset = newline + 1
                at_line_start = True

    if header_buffer is not None:
        scanner.start_record(bytes(header_buffer))
    scanner.finish_record()


def write_reference_segments(input_path, output_path, chunk_size=DEFAULT_CHUNK_SIZE):
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(HEADER)
            scan_fasta(input_path, handle, chunk_size=chunk_size)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output_path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Write reference segments split on N/n runs of at least 100 bp"
    )
    parser.add_argument("reference_fasta", type=Path)
    parser.add_argument("output_tsv", type=Path)
    args = parser.parse_args()
    try:
        write_reference_segments(args.reference_fasta, args.output_tsv)
    except (OSError, ReferenceSegmentsError) as error:
        raise SystemExit(f"ERROR: {error}") from error


if __name__ == "__main__":
    main()
