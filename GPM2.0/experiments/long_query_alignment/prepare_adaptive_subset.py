#!/usr/bin/env python3
"""Materialize an audited full reference or COMPLETE query records, read-only source.

Source gzip/FASTA is streamed to EOF and checked against the catalogue content
hash. Selection preserves original bytes/order. Failure retains partial evidence
but never emits a complete manifest; existing directories are never overwritten.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import catalog_adaptive_inputs as cat


def prepare(catalogue_path, out, names=None):
    raw_catalogue = catalogue_path.read_bytes()
    catalogue = json.loads(raw_catalogue)
    if catalogue.get("status") != "complete":
        raise ValueError("completed catalogue required")
    source = Path(catalogue["source"]).resolve(strict=True)
    records = catalogue["records"]
    by_name = {r["name"]: r for r in records}
    if len(by_name) != len(records):
        raise ValueError("duplicate catalogue records")
    selected = set(by_name) if names is None else set(names)
    if not selected or not selected <= by_name.keys() or names is not None and len(selected) != len(names):
        raise ValueError("unique existing record names required")
    before = cat.identity(source)
    # Device IDs are local to each cluster node; ctime/inode may also change
    # without content changes. Cross-run authority is the FULL content digest,
    # while before/after identity still detects mutation during this read.
    metadata_changes = {k: {"catalogue": catalogue["source_identity"].get(k), "current": v}
                        for k, v in before.items() if catalogue["source_identity"].get(k) != v}
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "source": str(source), "source_identity": before,
              "catalogue_sha256": hashlib.sha256(raw_catalogue).hexdigest(),
              "source_metadata_changes": metadata_changes,
              "selection": "all_records" if names is None else "complete_records",
              "records": [r for r in records if r["name"] in selected]}
    receipt = out / "subset.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    pending, output = out / "input.partial.fa", out / "input.fa"
    source_hash, output_hash = hashlib.sha256(), hashlib.sha256()
    seen = []
    keep, line_start, name = False, True, None
    length, seq_hash = 0, None
    def check_selected():
        if keep:
            expected = by_name[name]
            if length != expected["length"] or seq_hash.hexdigest() != expected["sequence_sha256"]:
                raise ValueError("selected record length/content differs from catalogue: " + name)
    try:
        opener = gzip.open if source.suffix.lower() == ".gz" else open
        with opener(source, "rb") as inp, pending.open("xb") as dst:
            while True:
                raw = inp.readline(cat.BLOCK)
                if not raw:
                    break
                source_hash.update(raw)
                if line_start and raw.startswith(b">"):
                    check_selected()
                    if len(raw) >= cat.BLOCK:
                        raise ValueError("oversized FASTA header")
                    words = raw[1:].split()
                    if not words:
                        raise ValueError("empty FASTA name")
                    name = words[0].decode("ascii")
                    keep = name in selected
                    length, seq_hash = 0, hashlib.sha256()
                    if keep:
                        seen.append(name)
                elif keep:
                    sequence = raw.rstrip(b"\r\n")
                    length += len(sequence)
                    seq_hash.update(sequence.upper())
                if keep:
                    dst.write(raw)
                    output_hash.update(raw)
                line_start = raw.endswith(b"\n")
        check_selected()
        if source_hash.hexdigest() != catalogue["decompressed_sha256"] or cat.identity(source) != before:
            raise ValueError("source content changed")
        if seen != [r["name"] for r in report["records"]]:
            raise ValueError("selected records missing, duplicated or reordered")
        pending.rename(output)
        report.update(status="complete", path=str(output), output_sha256=output_hash.hexdigest(),
                      source_decompressed_sha256=source_hash.hexdigest(), source_unchanged=True,
                      selected_bases=sum(r["length"] for r in report["records"]))
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        temporary = receipt.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(receipt)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalogue", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--all-records", action="store_true")
    group.add_argument("--records", nargs="+")
    a = p.parse_args(argv)
    r = prepare(a.catalogue, a.out, a.records)
    print(json.dumps({k: r[k] for k in ("status", "path", "selected_bases", "output_sha256")}))


if __name__ == "__main__":
    main()
