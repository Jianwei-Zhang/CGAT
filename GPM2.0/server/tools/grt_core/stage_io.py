from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .common import *
from .stage_schema import *

def read_single(path: Path, header: list[str] | None = None) -> dict[str, str]:
    rows = read_tsv(path, header)
    if len(rows) != 1:
        fail(f"{path} must contain exactly one row")
    return rows[0]

def read_fasta_allow_empty(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        fail(f"FASTA is missing: {path}")
    if path.stat().st_size == 0:
        return []
    return read_fasta(path)

def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

def atomic_write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    write_tsv(temporary, fields, rows)
    os.replace(temporary, path)

def atomic_write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    write_jsonl(temporary, rows)
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: object, *, pretty: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    temporary.write_text(payload + "\n", encoding="utf-8", newline="")
    os.replace(temporary, path)


def json_hash(value: object) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))

def source_catalog(server_dir: Path) -> dict[tuple[str, str], str]:
    datasets = read_tsv(
        server_dir / "metadata/datasets.tsv",
        [
            "dataset_name",
            "assembler",
            "assembler_version",
            "fasta_relpath",
            "fai_relpath",
            "self_alignment_available",
        ],
    )
    sources: dict[tuple[str, str], str] = {}
    for dataset in datasets:
        for name, sequence in read_fasta(server_dir / dataset["fasta_relpath"]):
            key = (dataset["dataset_name"], name)
            if key in sources:
                fail(f"duplicate source identity: {key[0]}:{key[1]}")
            sources[key] = sequence
    locator_keys = {
        (row["dataset_name"], row["seq_name"])
        for row in read_tsv(
            server_dir / "metadata/source_seq_locator.tsv",
            ["dataset_name", "seq_name", "fasta_relpath"],
        )
    }
    if locator_keys != set(sources):
        fail("source_seq_locator.tsv does not match the initial source catalog")
    return sources


def assignment_map(server_dir: Path) -> dict[tuple[str, str], set[str]]:
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in read_tsv(
        server_dir / "metadata/chr_assignments.tsv",
        CHR_ASSIGNMENT_FIELDS,
    ):
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    return assignments

def sequence_from_segment(segment: dict[str, object], sources: dict[tuple[str, str], str]) -> str:
    if segment["segment_kind"] == "gap":
        return "N" * int(segment["length"])
    key = (str(segment["dataset_name"]), str(segment["contig_name"]))
    sequence = sources[key][int(segment["source_start"]) - 1 : int(segment["source_end"])]
    return sequence if segment["orientation"] == "+" else reverse_complement(sequence)

def load_q_paths(
    server_dir: Path,
    q_version: str,
    q_rows: list[dict[str, str]],
    sources: dict[tuple[str, str], str],
) -> tuple[list[str], dict[str, list[dict[str, object]]], dict[str, str]]:
    q_records = read_fasta(server_dir / f"grt/q/{q_version}.fa")
    record_order = [name for name, _sequence in q_records]
    record_map = dict(q_records)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in q_rows:
        if row["q_version"] == q_version:
            grouped[row["chr"]].append(row)
    if set(grouped) != set(record_map):
        fail(f"q segment mapping does not cover every {q_version} record")
    paths: dict[str, list[dict[str, object]]] = {}
    for chromosome in record_order:
        expected_start = 1
        segments: list[dict[str, object]] = []
        for row in sorted(grouped[chromosome], key=lambda value: int(value["q_start"])):
            start = int(row["q_start"])
            end = int(row["q_end"])
            if start != expected_start or end < start:
                fail(f"non-contiguous {q_version} mapping for {chromosome}")
            evidence_ids = json.loads(row["evidence_ids_json"])
            if not isinstance(evidence_ids, list):
                fail(f"invalid evidence list for q segment {row['segment_id']}")
            segment: dict[str, object] = {
                "segment_kind": row["segment_kind"],
                "length": end - start + 1,
                "dataset_name": row["dataset_name"],
                "contig_name": row["contig_name"],
                "source_start": int(row["source_start"]) if row["source_start"] else None,
                "source_end": int(row["source_end"]) if row["source_end"] else None,
                "orientation": row["orientation"],
                "source_card_key": row["source_card_key"],
                "evidence_ids": evidence_ids,
            }
            expected = record_map[chromosome][start - 1 : end]
            if sequence_from_segment(segment, sources) != expected:
                fail(f"q segment {row['segment_id']} does not reconstruct {q_version}:{chromosome}")
            segments.append(segment)
            expected_start = end + 1
        if expected_start != len(record_map[chromosome]) + 1:
            fail(f"q segment mapping ends early for {q_version}:{chromosome}")
        paths[chromosome] = segments
    return record_order, paths, record_map

def slice_segment(segment: dict[str, object], left: int, right: int) -> dict[str, object]:
    length = int(segment["length"])
    if left < 0 or right > length or left >= right:
        fail("invalid q segment slice")
    result = dict(segment)
    result["evidence_ids"] = list(segment["evidence_ids"])
    result["length"] = right - left
    if segment["segment_kind"] == "source":
        if segment["orientation"] == "+":
            result["source_start"] = int(segment["source_start"]) + left
            result["source_end"] = int(segment["source_start"]) + right - 1
        else:
            result["source_start"] = int(segment["source_end"]) - right + 1
            result["source_end"] = int(segment["source_end"]) - left
    return result

def slice_path(path: list[dict[str, object]], start: int, end: int) -> list[dict[str, object]]:
    if start < 0 or end < start:
        fail("invalid q path interval")
    result: list[dict[str, object]] = []
    cursor = 0
    for segment in path:
        segment_end = cursor + int(segment["length"])
        overlap_start = max(start, cursor)
        overlap_end = min(end, segment_end)
        if overlap_start < overlap_end:
            result.append(slice_segment(segment, overlap_start - cursor, overlap_end - cursor))
        cursor = segment_end
    if end > cursor:
        fail("q path slice exceeds chromosome")
    return result

def path_sequence(path: list[dict[str, object]], sources: dict[tuple[str, str], str]) -> str:
    return "".join(sequence_from_segment(segment, sources) for segment in path)

def q_rows_for_paths(
    q_version: str,
    chromosome_order: list[str],
    paths: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        position = 1
        for index, segment in enumerate(paths[chromosome], start=1):
            length = int(segment["length"])
            identity = {
                "q_version": q_version,
                "chr": chromosome,
                "index": index,
                "kind": segment["segment_kind"],
                "length": length,
                "dataset": segment["dataset_name"],
                "contig": segment["contig_name"],
                "source_start": segment["source_start"],
                "source_end": segment["source_end"],
                "orientation": segment["orientation"],
                "evidence": segment["evidence_ids"],
            }
            rows.append(
                {
                    "q_version": q_version,
                    "chr": chromosome,
                    "segment_id": stable_id(f"{q_version}-segment", identity, 20),
                    "segment_kind": segment["segment_kind"],
                    "q_start": position,
                    "q_end": position + length - 1,
                    "dataset_name": segment["dataset_name"],
                    "contig_name": segment["contig_name"],
                    "source_start": "" if segment["source_start"] is None else segment["source_start"],
                    "source_end": "" if segment["source_end"] is None else segment["source_end"],
                    "orientation": segment["orientation"],
                    "source_card_key": segment["source_card_key"],
                    "evidence_ids_json": canonical_json(segment["evidence_ids"]),
                }
            )
            position += length
    return rows

def gap_objects(chromosome: str, q_version: str, sequence: str) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for index, match in enumerate(re.finditer(r"N{100,}", sequence), start=1):
        identity = {
            "q_version": q_version,
            "chr": chromosome,
            "index": index,
            "start": match.start() + 1,
            "end": match.end(),
            "sequence_sha256": sha256_bytes(match.group().encode("ascii")),
        }
        objects.append(
            {
                "chr": chromosome,
                "object_id": stable_id("gap", identity, 20),
                "start0": match.start(),
                "end0": match.end(),
                "index": index,
            }
        )
    return objects
