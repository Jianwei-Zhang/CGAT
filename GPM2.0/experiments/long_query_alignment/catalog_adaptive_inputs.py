#!/usr/bin/env python3
"""Read-only streaming FASTA/gzip catalogue for adaptive mapping experiments.

Run large catalogues as a compute job. No whole sequence is kept in memory; gzip
CRC is checked by reading to EOF. Per-record sequence hashes ignore wrapping and
case, while the decompressed-file hash retains exact bytes. No input is rewritten.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

ALPHABET = b"ACGTNRYKMSWBDHVacgtnrykmswbdhv"
BLOCK = 1024**2


def identity(path):
    s = path.stat()
    return {"bytes": s.st_size, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
            "inode": s.st_ino, "device": s.st_dev}


def catalogue(path):
    path = path.resolve(strict=True)
    before = identity(path)
    started = time.monotonic()
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    records, seen, file_hash = [], set(), hashlib.sha256()
    current = None
    sequence_hash = None
    line_start = True
    def finish():
        if current is not None:
            if not current["length"]:
                raise ValueError("empty sequence: " + current["name"])
            current["sequence_sha256"] = sequence_hash.hexdigest()
            records.append(current)
    with opener(path, "rb") as stream:
        while True:
            raw = stream.readline(BLOCK)
            if not raw:
                break
            file_hash.update(raw)
            if line_start and raw.startswith(b">"):
                if len(raw) >= BLOCK:
                    raise ValueError("FASTA header exceeds catalogue bound")
                finish()
                words = raw[1:].split()
                if not words:
                    raise ValueError("empty FASTA name")
                name = words[0].decode("ascii")
                if name in seen:
                    raise ValueError("duplicate FASTA name: " + name)
                seen.add(name)
                current = {"name": name, "length": 0, "n_bases": 0}
                sequence_hash = hashlib.sha256()
            else:
                sequence = raw.rstrip(b"\r\n")
                if sequence:
                    if current is None or sequence.translate(None, ALPHABET):
                        raise ValueError("non-IUPAC sequence or missing FASTA header")
                    upper = sequence.upper()
                    current["length"] += len(upper)
                    current["n_bases"] += upper.count(b"N")
                    sequence_hash.update(upper)
            line_start = raw.endswith(b"\n")
    finish()
    if not records or identity(path) != before:
        raise ValueError("empty or changing input")
    lengths = sorted((r["length"] for r in records), reverse=True)
    total, cumulative, n50 = sum(lengths), 0, 0
    for length in lengths:
        cumulative += length
        if cumulative * 2 >= total:
            n50 = length
            break
    return {"source": str(path), "source_identity": before,
            "decompressed_sha256": file_hash.hexdigest(), "records": records,
            "record_count": len(records), "total_bases": total, "n50_bases": n50,
            "max_record_bases": lengths[0], "n_bases": sum(r["n_bases"] for r in records),
            "long_record_counts": {str(threshold): sum(n >= threshold for n in lengths)
                                   for threshold in (20_000_000, 50_000_000, 100_000_000, 268_435_456)},
            "gzip_integrity": "verified_to_EOF" if path.suffix.lower() == ".gz" else "not_gzip",
            "elapsed_seconds": time.monotonic() - started, "source_unchanged": True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    # Reserve a new evidence file before scanning, refusing an existing output.
    with args.output.open("x") as stream:
        stream.write(json.dumps({"status": "running", "source": str(args.input)}) + "\n")
    try:
        result = {"status": "complete", **catalogue(args.input)}
    except BaseException as exc:
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        raise
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("source", "record_count", "total_bases", "n50_bases", "max_record_bases", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
