"""Small, standard-library-only primitives for portable server reports."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "cgat_server_report_v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_tsv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"report data path escapes its directory: {relative}")
    return path


def fasta_stats(path: Path) -> dict | None:
    """Stream FASTA; N runs span physical lines. Never retain whole sequences."""
    if not path.is_file():
        return None
    records = []
    current = None
    n_run = 0

    def finish_gap():
        nonlocal n_run
        if current is not None and n_run >= 100:
            current["gap_count"] += 1
            current["gap_bp"] += n_run
        n_run = 0

    with path.open(encoding="ascii") as handle:
        for raw in handle:
            if raw.startswith(">"):
                finish_gap()
                name = raw[1:].split()[0]
                current = {"sequence": name, "length_bp": 0, "n_bp": 0,
                           "gap_count": 0, "gap_bp": 0}
                records.append(current)
                continue
            sequence = "".join(raw.split()).upper()
            if not sequence:
                continue
            if current is None:
                raise ValueError(f"FASTA sequence has no header: {path}")
            current["length_bp"] += len(sequence)
            current["n_bp"] += sequence.count("N")
            for match in re.finditer(r"N+|[^N]+", sequence):
                if match[0][0] == "N":
                    n_run += len(match[0])
                else:
                    finish_gap()
    finish_gap()
    lengths = sorted((row["length_bp"] for row in records), reverse=True)
    total = sum(lengths)
    cumulative = 0
    n50 = 0
    for length in lengths:
        cumulative += length
        if cumulative * 2 >= total:
            n50 = length
            break
    return {"sequence_count": len(records), "length_bp": total,
            "n_bp": sum(row["n_bp"] for row in records),
            "gap_count": sum(row["gap_count"] for row in records),
            "gap_bp": sum(row["gap_bp"] for row in records), "n50_bp": n50,
            "gap_definition": "maximal consecutive N/n runs of at least 100 bp",
            "sha256": digest(path), "sequences": records}
