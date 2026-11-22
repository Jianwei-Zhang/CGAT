#!/usr/bin/env python3
"""Test-only faidx for nonempty, normally wrapped fixture FASTA files."""
from pathlib import Path
import sys


def index_records(path):
    with path.open("rb") as stream:
        name = None
        while raw := stream.readline():
            if raw.startswith(b">"):
                if name is not None:
                    yield name, length, offset, line_bases, line_width
                name = raw[1:].split()[0].decode("ascii")
                offset = stream.tell()
                length = line_bases = line_width = 0
            else:
                bases = len(raw.rstrip(b"\r\n"))
                if name is None or not bases:
                    raise ValueError("expected nonempty formatted fixture FASTA")
                if not length:
                    line_bases, line_width = bases, len(raw)
                length += bases
        if name is not None:
            yield name, length, offset, line_bases, line_width


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "faidx":
        raise SystemExit("fixture supports only samtools faidx <file>")
    fasta = Path(sys.argv[2])
    Path(str(fasta) + ".fai").write_text("".join("\t".join(map(str, row)) + "\n" for row in index_records(fasta)))
