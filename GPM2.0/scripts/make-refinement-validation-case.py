#!/usr/bin/env python3
"""Reproducible synthetic bridge inputs for real refinement interoperability.

This does not run, mock or benchmark any scientific engine. Existing sample
files are verified, never overwritten. No customer data are read or modified.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random

CONFIG = {"schema": "cgat.refinement-native-synthetic-case", "schema_version": 1,
          "seed": 20261122, "contig": "chr1", "length": 500000,
          "gap_start": 249000, "gap_length": 2000,
          "hifi_reads": 320, "hifi_length": 50000, "hifi_substitution_rate": 0,
          "ont_reads": 200, "ont_length": 60000, "ont_substitution_rate": 0.005,
          "coordinates": "zero_based_half_open", "biological_accuracy_claim": False}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def fasta(path, sequence):
    with path.open("x") as stream:
        stream.write(">" + CONFIG["contig"] + "\n")
        for start in range(0, len(sequence), 80):
            stream.write(sequence[start:start + 80] + "\n")


def create(root):
    root = root.resolve()
    marker = root / "case.json"
    generator = digest(Path(__file__))
    if root.exists():
        value = json.loads(marker.read_text())
        if value.get("configuration") != CONFIG or value.get("generator_sha256") != generator:
            raise ValueError("existing sample has another configuration/generator; choose a new directory")
        for name, expected in value["files_sha256"].items():
            if digest(root / name) != expected:
                raise ValueError("existing validation sample changed: " + name)
        return value
    root.mkdir()
    rng = random.Random(CONFIG["seed"])
    truth = "".join(rng.choices("ACGT", k=CONFIG["length"]))
    start, end = CONFIG["gap_start"], CONFIG["gap_start"] + CONFIG["gap_length"]
    fasta(root / "reference.fa", truth)
    fasta(root / "assembly.fa", truth[:start] + "N" * (end - start) + truth[end:])
    paths = {name: root / name / "reads.fastq.gz" for name in ("hifi_a", "hifi_b", "ont")}
    streams, files = {}, []
    try:
        for name, path in paths.items():
            path.parent.mkdir()
            file = path.open("xb");files.append(file)
            streams[name] = gzip.GzipFile(filename="", fileobj=file, mode="wb", mtime=0)
        records = []
        for technology in ("hifi", "ont"):
            count, length = CONFIG[technology + "_reads"], CONFIG[technology + "_length"]
            rate = CONFIG[technology + "_substitution_rate"]
            errors = random.Random(CONFIG["seed"] + (1 if technology == "hifi" else 2))
            for index in range(count):
                left = index * (len(truth) - length) // (count - 1)
                sequence = list(truth[left:left + length])
                positions = errors.sample(range(length), round(rate * length))
                for position in positions:
                    sequence[position] = errors.choice("ACGT".replace(sequence[position], ""))
                sequence = "".join(sequence)
                strand = "+" if index % 2 == 0 else "-"
                if strand == "-":
                    sequence = sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]
                name = technology if technology == "ont" else ("hifi_a" if index % 2 == 0 else "hifi_b")
                record_id = "sim_" + technology + "_" + str(index + 1).zfill(6)
                quality = "I" if technology == "hifi" else "8"
                streams[name].write(("@" + record_id + "\n" + sequence + "\n+\n" + quality * length + "\n").encode())
                records.append({"file": paths[name].relative_to(root).as_posix(), "technology": technology,
                                "record_id": record_id, "truth_start": left, "truth_end": left + length,
                                "strand": strand, "substitutions": len(positions),
                                "spans_gap": left < start and left + length > end})
    finally:
        for stream in streams.values():stream.close()
        for file in files:file.close()
    names = ["reference.fa", "assembly.fa", *[p.relative_to(root).as_posix() for p in paths.values()]]
    value = {"configuration": CONFIG, "generator_sha256": generator,
             "files_sha256": {name: digest(root / name) for name in names}, "reads": records,
             "spanning_reads": {name: sum(row["file"] == path.relative_to(root).as_posix() and row["spans_gap"] for row in records)
                                for name,path in paths.items()}}
    if any(count < 10 for count in value["spanning_reads"].values()):
        raise ValueError("sample lacks the intended known-bridge read coverage")
    marker.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    value = create(args.out)
    print(json.dumps({"root":str(args.out.resolve()), "configuration":value["configuration"],
                      "files_sha256":value["files_sha256"], "spanning_reads":value["spanning_reads"]},indent=2))


if __name__ == "__main__":
    main()
