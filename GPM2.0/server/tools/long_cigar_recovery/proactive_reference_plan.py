#!/usr/bin/env python3
"""Pre-execution query routing prototype; no mapping, retry or publication.

A bounded, single physical scan records lengths, original record order/ranges
and hashes together. Normal-only input is reused without copying. Mixed input
is materialized in ONE subsequent streaming pass, not once per risk record.
All sequences retain their original IDs, headers, case and wrapping. gzip is
read as a stream, with both compressed identity and decoded record identities.

This is NOT a Server entrypoint. Query length is a conservative query-consuming
CIGAR risk indicator, not proof of failure or proof that short queries cannot
hit other bugs/long target deletions. The existing scientific recovery engine
and its per-result checks still need a separately tested proactive integration.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile

MAX_OPERATION = (1 << 28) - 1
MAX_COORDINATE = (1 << 31) - 1
CHUNK = 1024 * 1024
MAX_RECORDS = 1_000_000
DNA = b"ACGTRYSWKMBDHVNacgtryswkmbdhvn"


class PlanError(ValueError):
    pass


def fingerprint(path):
    value = Path(path).stat()
    if not stat.S_ISREG(value.st_mode):
        raise PlanError("query must be a regular file")
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class HashedReader(io.RawIOBase):
    """Hash bytes as gzip/plain readers consume them; never reread for a hash."""
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        size = self.source.readinto(buffer)
        if size:
            self.digest.update(memoryview(buffer)[:size])
            self.bytes_read += size
        return size


@contextmanager
def decoded_input(source):
    with Path(source).open("rb", buffering=0) as raw:
        hashed = HashedReader(raw)
        with io.BufferedReader(hashed, buffer_size=CHUNK) as buffered:
            if buffered.peek(2)[:2] == b"\x1f\x8b":
                with gzip.GzipFile(fileobj=buffered, mode="rb") as decoded:
                    yield decoded, hashed, "gzip"
            else:
                yield buffered, hashed, "plain"


@dataclass(frozen=True)
class Record:
    ordinal: int
    name: str
    length: int
    byte_start: int
    byte_end: int
    sha256: str


@dataclass(frozen=True)
class Catalog:
    source: str
    identity: tuple
    source_sha256: str
    encoding: str
    decoded_bytes: int
    physical_bytes_read: int
    records: tuple[Record, ...]

    def require_unchanged(self):
        if fingerprint(self.source) != self.identity:
            raise PlanError("original query changed; discard this plan rather than reuse stale offsets")


def scan_query(source):
    """Single bounded-memory pass; offsets refer to decoded FASTA bytes."""
    source = Path(source).resolve(strict=True)
    before = fingerprint(source)
    records, names = [], set()
    offset = start = length = 0
    current = None
    line_start = True
    record_hash = hashlib.sha256()

    def finish(end):
        if current is None or not length:
            raise PlanError("empty FASTA or empty sequence record")
        records.append(Record(len(records), current, length, start, end, record_hash.hexdigest()))

    with decoded_input(source) as (stream, hashed, encoding):
        while raw := stream.readline(CHUNK):
            if line_start and raw.startswith(b">"):
                if len(raw) == CHUNK and not raw.endswith(b"\n"):
                    raise PlanError("FASTA header exceeds bounded scanner size")
                fields = raw[1:].split(maxsplit=1)
                if not fields:
                    raise PlanError("empty FASTA identifier")
                try:
                    name = fields[0].decode("ascii")
                except UnicodeDecodeError as exc:
                    raise PlanError("recovery planning requires ASCII sequence identifiers") from exc
                if name in names or any(not 33 <= ord(char) <= 126 for char in name):
                    raise PlanError("duplicate or unsupported FASTA identifier")
                if len(names) >= MAX_RECORDS:
                    raise PlanError("record catalog exceeds its bounded metadata budget")
                if current is not None:
                    finish(offset)
                    record_hash = hashlib.sha256()
                    start = offset
                # Initial blank lines belong to the first record, not discarded.
                names.add(name)
                current, length = name, 0
            else:
                sequence = raw.rstrip(b"\r\n")
                if sequence:
                    if current is None or sequence.translate(None, DNA):
                        raise PlanError("plain/gzip IUPAC DNA FASTA required for this prototype")
                    length += len(sequence)
                    if length > MAX_COORDINATE:
                        raise PlanError("sequence exceeds supported signed 32-bit coordinates")
            record_hash.update(raw)
            offset += len(raw)
            line_start = raw.endswith(b"\n")
        finish(offset)
        if fingerprint(source) != before or hashed.bytes_read != before[2]:
            raise PlanError("query changed or scanner did not consume the complete physical source")
        return Catalog(str(source), before, hashed.digest.hexdigest(), encoding,
                       offset, hashed.bytes_read, tuple(records))


@dataclass(frozen=True)
class WindowPolicy:
    core_bases: int = 50_000_000
    context_bases: int = 100_000

    def validate(self):
        if (type(self.core_bases) is not int or type(self.context_bases) is not int
                or not 0 <= self.context_bases < self.core_bases
                or self.core_bases + 2 * self.context_bases > MAX_OPERATION):
            raise PlanError("window core/context outside supported operation bounds")


def window_work(length, policy):
    count = (length + policy.core_bases - 1) // policy.core_bases
    processed = sum(min(length, start + policy.core_bases + policy.context_bases)
                    - max(0, start - policy.context_bases)
                    for start in range(0, length, policy.core_bases))
    return {"windows": count, "core_bases": length, "context_overlap_bases": processed - length,
            "window_query_bases": processed}


def make_plan(catalog, policy=WindowPolicy()):
    """Internal policy only; no customer threshold/configuration parameter."""
    catalog.require_unchanged()
    policy.validate()
    rows = []
    for record in catalog.records:
        special = record.length > MAX_OPERATION
        rows.append({"ordinal": record.ordinal, "query": record.name, "length": record.length,
                     "route": "long_query" if special else "native",
                     "work": window_work(record.length, policy) if special else
                             {"windows": 0, "core_bases": record.length, "context_overlap_bases": 0}})
    native = [row["query"] for row in rows if row["route"] == "native"]
    long_queries = [row["query"] for row in rows if row["route"] == "long_query"]
    shared = bool(long_queries)
    needs_materialization = shared and (len(catalog.records) > 1 or catalog.encoding == "gzip")
    # No crash/bisection/singleton-replay node exists in this plan.
    return {"schema": 1, "status": "planned_not_executed", "production_ready": False,
            "source": catalog.source, "source_sha256": catalog.source_sha256,
            "source_identity": list(catalog.identity), "encoding": catalog.encoding,
            "records": rows, "native_queries": native, "long_queries": long_queries,
            "window_policy": asdict(policy), "risk_rule": "query_length_exceeds_packed_operation_limit",
            "risk_threshold": MAX_OPERATION, "all_failures_predicted": False,
            "scope_exclusions": ["long_target_only_deletion", "non_target_minimap2_failures"],
            "normal_only_original_input_reused": not shared,
            "ordinary_batch_count": int(bool(native)),
            "special_sequence_count": len(long_queries),
            "requires_shared_original_index_context": shared,
            "index_build_budget": int(shared),
            "index_policy": "unchanged_default_partitioning_no_I_override",
            "threshold_source_plan": ("ordinary_batch_original_index_log" if native else
                                      "first_index_part_metadata_only_no_query_alignment") if shared else None,
            "whole_input_trial_alignments": 0, "bisection_alignments": 0,
            "assertion_reproduction_alignments": 0,
            "query_catalog_physical_bytes_read": catalog.physical_bytes_read,
            "additional_materialization_passes": int(needs_materialization),
            "materialization_decoded_bytes": catalog.decoded_bytes if needs_materialization else 0,
            "failed_PAF_reuse": False, "result_published": False}


def check_prepared_scope(destination, prepared_workspace=None, *, leaf="selective"):
    """Internal adapter-only exception to the standalone prepared-workspace ban.

    Only runs/<name>_vs_ref/.long-cigar-attempt-*/selective[/inputs] is writable.
    No CLI option exposes this permission, and no data/cache/runtime path qualifies.
    """
    destination = Path(destination).absolute()
    workspace = Path(prepared_workspace).resolve() if prepared_workspace is not None else None
    if workspace is not None:
        try:
            relative = destination.resolve().relative_to(workspace).parts
        except ValueError as exc:
            raise PlanError("managed proactive output escaped its prepared workspace") from exc
        suffix = ("selective",) if leaf == "selective" else ("selective", "inputs")
        if (destination != destination.resolve() or len(relative) != 3 + len(suffix)
                or relative[0] != "runs" or not relative[1].endswith("_vs_ref")
                or not relative[2].startswith(".long-cigar-attempt-") or relative[3:] != suffix
                or not (workspace / ".prepare_lib").is_dir() or not (workspace / "metadata").is_dir()):
            raise PlanError("managed proactive output requires an adapter-owned private attempt")
    for parent in (destination.parent, *destination.parent.parents):
        if ((parent / ".prepare_lib").exists() or (parent / "run_all.sh").exists()) and parent != workspace:
            raise PlanError("prototype output cannot be inside a prepared workspace")


def materialize(catalog, plan, destination, *, prepared_workspace=None):
    """Only whole-record partitioning, never base/window splitting or mapping.

    At most two output handles (ordinary group + current long record). All output
    and per-record hashes are computed while writing; ordinary records are never
    extracted once per long sequence. Failed partial files remain under a private
    attempt directory and no completed-group marker is emitted.
    """
    catalog.require_unchanged()
    if type(plan) is not dict or type(plan.get("window_policy")) is not dict:
        raise PlanError("invalid internal plan")
    try:
        expected = make_plan(catalog, WindowPolicy(**plan["window_policy"]))
    except (TypeError, ValueError) as exc:
        raise PlanError("invalid internal window policy") from exc
    if plan != expected:
        raise PlanError("plan changed or no longer matches the original catalog")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise PlanError("fresh private materialization directory required")
    check_prepared_scope(destination, prepared_workspace, leaf="inputs")
    # Only metadata is created on a one-route one-original-input fast path.
    destination.mkdir(mode=0o700)
    report = {"status": "materializing", "analysis_started": False, "result_published": False,
              "source_sha256": catalog.source_sha256, "groups": [],
              "query_materialization_physical_bytes_read": 0, "decoded_bytes_written": 0,
              "original_sequence_order": [r.name for r in catalog.records]}
    try:
        if not plan["long_queries"] or (len(catalog.records) == 1 and catalog.encoding == "plain"):
            route = "long_query" if plan["long_queries"] else "native"
            report["groups"] = [{"route": route, "queries": report["original_sequence_order"],
                                  "path": catalog.source, "sha256": catalog.source_sha256,
                                  "encoding": catalog.encoding, "original_input_reused": True}]
        else:
            staging = Path(tempfile.mkdtemp(prefix=".input-attempt-", dir=destination))
            native_set = set(plan["native_queries"])
            native_path = staging/"native.fa"
            native_handle = native_path.open("xb") if native_set else None
            native_hash = hashlib.sha256()
            source_offset = 0
            try:
                with decoded_input(catalog.source) as (stream, hashed, encoding):
                    if encoding != catalog.encoding:
                        raise PlanError("source encoding changed")
                    for record in catalog.records:
                        if record.byte_start != source_offset:
                            raise PlanError("catalog skipped or duplicated original bytes")
                        ordinary = record.name in native_set
                        path = native_path if ordinary else staging/f"long-{record.ordinal:06d}.fa"
                        output = native_handle if ordinary else path.open("xb")
                        digest = hashlib.sha256()
                        remaining = record.byte_end - record.byte_start
                        try:
                            while remaining:
                                raw = stream.read(min(CHUNK, remaining))
                                if not raw:
                                    raise PlanError("source truncated during materialization")
                                output.write(raw)
                                digest.update(raw)
                                if ordinary:
                                    native_hash.update(raw)
                                remaining -= len(raw)
                                source_offset += len(raw)
                                report["decoded_bytes_written"] += len(raw)
                        finally:
                            if not ordinary:
                                output.close()
                        if digest.hexdigest() != record.sha256:
                            raise PlanError("record changed after planning")
                        if not ordinary:
                            report["groups"].append({"route": "long_query", "queries": [record.name],
                                "path": str(path), "sha256": digest.hexdigest(), "encoding": "plain",
                                "original_input_reused": False})
                    if stream.read(1) or source_offset != catalog.decoded_bytes:
                        raise PlanError("source gained bytes or plan omitted records")
                    if hashed.digest.hexdigest() != catalog.source_sha256 or hashed.bytes_read != catalog.physical_bytes_read:
                        raise PlanError("complete source identity changed during materialization")
                    report["query_materialization_physical_bytes_read"] = hashed.bytes_read
            finally:
                if native_handle is not None:
                    native_handle.close()
            if native_set:
                report["groups"].insert(0, {"route": "native", "queries": plan["native_queries"],
                    "path": str(native_path), "sha256": native_hash.hexdigest(), "encoding": "plain",
                    "original_input_reused": False})
        catalog.require_unchanged()
        accounted = [name for group in report["groups"] for name in group["queries"]]
        if len(accounted) != len(catalog.records) or set(accounted) != {r.name for r in catalog.records}:
            raise PlanError("incomplete or duplicate original query coverage")
        report.update(status="complete_inputs_only", all_original_records_accounted=True)
        temporary = destination/"groups.pending.json"
        temporary.write_text(json.dumps(report, indent=2)+"\n")
        temporary.rename(destination/"groups.json")
    except BaseException as exc:
        report.update(status="refused_or_failed", error=f"{type(exc).__name__}: {exc}")
        (destination/"failure.json").write_text(json.dumps(report, indent=2)+"\n")
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Scan/prepare only; starts no aligner")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "plan_only", "no_files_or_commands_started": True,
                          "production_ready": False})); return 0
    if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
        parser.error("fresh output directory under an existing parent required")
    try:
        catalog = scan_query(args.query)
        plan = make_plan(catalog)
        groups = materialize(catalog, plan, args.out)
        (args.out/"plan.json").write_text(json.dumps(plan, indent=2)+"\n")
        print(json.dumps({"status": groups["status"], "ordinary_queries": len(plan["native_queries"]),
                          "long_queries": len(plan["long_queries"]), "analysis_started": False,
                          "result_published": False})); return 0
    except (OSError, ValueError, EOFError) as exc:
        print(json.dumps({"status": "refused_or_failed", "error": str(exc)})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
