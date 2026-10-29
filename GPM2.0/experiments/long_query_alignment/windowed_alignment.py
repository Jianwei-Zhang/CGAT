#!/usr/bin/env python3
"""EXPERIMENT ONLY: overlapping query windows with checked PAF coordinate recovery.

No Server integration, self-alignment mode, automatic retry or biological acceptance.
Writes only a NEW experiment directory. Never changes minimap2, its defaults in
CGAT, the original inputs, or an existing workspace. See README.md for limitations.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

LIMIT = (1 << 28) - 1
INT32_MAX = (1 << 31) - 1
CHUNK = 1024 * 1024
ALPHABET = b"ACGTRYSWKMBDHVN"
NT = bytes(byte if byte in b"ACGT" else ord("N") for byte in range(256))
RC = bytes.maketrans(b"ACGTN", b"TGCAN")
OP_RE = re.compile(r"([1-9][0-9]*)([=XID])")
Q_OPS = "=XI"
T_OPS = "=XD"


class ExperimentError(ValueError):
    pass


def fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns, "inode": stat.st_ino}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    os.replace(temporary, path)


class FastaStore:
    """Validated plain FASTA -> private unwrapped spool; never writes next to input.

    Arbitrarily wrapped DNA and bounded fragments of a single long line work.
    Original letters are preserved (uppercased); NT encoding is ONLY for checking
    minimap2's CIGAR. Duplicate IDs, empty records and non-DNA text fail closed.
    """
    def __init__(self, source: Path, spool: Path):
        self.source = source.resolve()
        before = fingerprint(self.source)
        self.records: dict[str, dict] = {}
        raw_hash = hashlib.sha256()
        current = None
        offset = 0
        at_start = True
        with self.source.open("rb") as inp, spool.open("xb") as out:
            while raw := inp.readline(CHUNK):
                raw_hash.update(raw)
                header = at_start and raw.startswith(b">")
                at_start = raw.endswith(b"\n")
                if header:
                    if not at_start and len(raw) == CHUNK:
                        raise ExperimentError("FASTA header exceeds 1 MiB")
                    fields = raw[1:].split()
                    if not fields:
                        raise ExperimentError("empty FASTA identifier")
                    name = fields[0].decode("ascii")
                    if any(ord(char) < 33 or ord(char) > 126 for char in name):
                        raise ExperimentError("FASTA identifier contains unsupported characters")
                    if name in self.records:
                        raise ExperimentError(f"duplicate FASTA identifier: {name}")
                    current = {"offset": offset, "length": 0}
                    self.records[name] = current
                    continue
                sequence = raw.rstrip(b"\r\n").upper()
                if not sequence:
                    continue
                if current is None:
                    raise ExperimentError("sequence before FASTA header (plain FASTA required)")
                if sequence.translate(None, ALPHABET):
                    raise ExperimentError("non-IUPAC DNA or whitespace within sequence")
                out.write(sequence)
                offset += len(sequence)
                current["length"] += len(sequence)
                if current["length"] > INT32_MAX:
                    raise ExperimentError("single record exceeds signed 32-bit coordinate range; unsupported")
        if not self.records or any(record["length"] == 0 for record in self.records.values()):
            raise ExperimentError("empty FASTA or zero-length record")
        if fingerprint(self.source) != before:
            raise ExperimentError("FASTA changed during scan")
        self.identity = {"source": str(self.source), **before, "sha256": raw_hash.hexdigest()}
        self.handle = spool.open("rb")

    def fetch(self, name: str, start: int, end: int) -> bytes:
        record = self.records[name]
        if not 0 <= start <= end <= record["length"]:
            raise ExperimentError(f"invalid sequence interval: {name}:{start}-{end}")
        self.handle.seek(record["offset"] + start)
        sequence = self.handle.read(end - start)
        if len(sequence) != end - start:
            raise ExperimentError("truncated private sequence spool")
        return sequence

    def close(self):
        self.handle.close()

    def unchanged(self):
        return all(fingerprint(self.source)[key] == self.identity[key]
                   for key in ("size", "mtime_ns", "ctime_ns", "inode")) and sha256(self.source) == self.identity["sha256"]


@dataclass(frozen=True)
class Window:
    alias: str
    query: str
    length: int
    start: int
    end: int
    core_start: int
    core_end: int


def make_windows(records: dict, core_bases: int, context_bases: int) -> list[Window]:
    if core_bases < 1 or context_bases < 0 or context_bases >= core_bases:
        raise ExperimentError("require core > context >= 0")
    if core_bases + 2 * context_bases > LIMIT:
        raise ExperimentError("query window including context exceeds CIGAR operation limit")
    windows = []
    for name, record in records.items():
        length = record["length"]
        for start in range(0, length, core_bases):
            end = min(length, start + core_bases)
            windows.append(Window(f"gpm_window_{len(windows):08d}", name, length,
                                  max(0, start - context_bases), min(length, end + context_bases), start, end))
    return windows


def write_windows(path: Path, store: FastaStore, windows: list[Window]):
    with path.open("xb") as output:
        for window in windows:
            output.write(f">{window.alias}\n".encode())
            for start in range(window.start, window.end, CHUNK):
                output.write(store.fetch(window.query, start, min(window.end, start + CHUNK)) + b"\n")


@dataclass(frozen=True)
class Hit:
    query: str
    qlen: int
    qs: int
    qe: int
    strand: str
    target: str
    tlen: int
    ts: int
    te: int
    matches: int
    block: int
    mapq: int
    ops: tuple[tuple[int, str], ...]


def parse_hit(line: str, windows: dict[str, Window], targets: dict) -> Hit:
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) < 13:
        raise ExperimentError("PAF requires core columns and an explicit =/X CIGAR")
    if fields[0] not in windows or fields[5] not in targets:
        raise ExperimentError("PAF contains an unknown query window or target")
    tags = [tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")]
    if len(tags) != 1:
        raise ExperimentError("exactly one CIGAR tag is required")
    ops = tuple((int(length), op) for length, op in OP_RE.findall(tags[0]))
    if not ops or "".join(f"{length}{op}" for length, op in ops) != tags[0]:
        raise ExperimentError("unsupported or invalid CIGAR; --eqx and assembly =XID required")
    if any(length > LIMIT for length, _ in ops):
        raise ExperimentError("CIGAR operation exceeds supported internal length")
    try:
        hit = Hit(fields[0], int(fields[1]), int(fields[2]), int(fields[3]), fields[4], fields[5],
                  int(fields[6]), int(fields[7]), int(fields[8]), int(fields[9]), int(fields[10]), int(fields[11]), ops)
    except ValueError as exc:
        raise ExperimentError("non-integer PAF fields") from exc
    window = windows[hit.query]
    if hit.qlen != window.end - window.start or hit.tlen != targets[hit.target]["length"]:
        raise ExperimentError("PAF length differs from input manifest")
    if not (0 <= hit.qs < hit.qe <= hit.qlen and 0 <= hit.ts < hit.te <= hit.tlen
            and hit.strand in ("+", "-") and 0 <= hit.matches <= hit.block and 0 <= hit.mapq <= 255):
        raise ExperimentError("invalid PAF coordinates, strand or statistics")
    if sum(n for n, op in ops if op in Q_OPS) != hit.qe - hit.qs or sum(n for n, op in ops if op in T_OPS) != hit.te - hit.ts:
        raise ExperimentError("CIGAR span mismatch")
    return hit


def lift(hit: Hit, window: Window) -> Hit:
    return replace(hit, query=window.query, qlen=window.length, qs=hit.qs + window.start, qe=hit.qe + window.start)


def clip_to_core(hit: Hit, window: Window) -> Hit | None:
    """Clip in target-forward CIGAR traversal, but own cores in query-forward space.

    A deletion at a core boundary belongs to the core on the higher-query side,
    on BOTH strands. The final query-end deletion belongs to the final core.
    No stitching, invented bases or heuristic placement selection is performed.
    """
    qs, qe = max(hit.qs, window.core_start), min(hit.qe, window.core_end)
    if qs >= qe:
        return None
    lo, hi = ((qs - hit.qs, qe - hit.qs) if hit.strand == "+" else (hit.qe - qe, hit.qe - qs))
    q, t = 0, hit.ts
    selected: list[tuple[int, str]] = []
    first_t = last_t = None

    def append(n, op, ts, te):
        nonlocal first_t, last_t
        if first_t is None:
            first_t = ts
        elif last_t != ts:
            raise ExperimentError("noncontiguous target after clipping")
        last_t = te
        if selected and selected[-1][1] == op:
            old, _ = selected[-1]
            if old + n > LIMIT:
                raise ExperimentError("clipped operation exceeds limit")
            selected[-1] = (old + n, op)
        else:
            selected.append((n, op))

    for n, op in hit.ops:
        if op in Q_OPS:
            start, end = max(lo, q), min(hi, q + n)
            if start < end:
                ts = t + (start - q if op in T_OPS else 0)
                append(end - start, op, ts, ts + (end - start if op in T_OPS else 0))
        else:
            boundary = hit.qs + q if hit.strand == "+" else hit.qe - q
            owned = window.core_start <= boundary < window.core_end or boundary == window.length == window.core_end
            if owned and lo <= q <= hi:
                append(n, op, t, t + n)
        q += n if op in Q_OPS else 0
        t += n if op in T_OPS else 0
    if first_t is None or last_t is None or last_t <= first_t:
        raise ExperimentError("owned core contains insertion-only alignment; cannot silently omit it")
    ops = tuple(selected)
    if sum(n for n, op in ops if op in Q_OPS) != qe - qs or sum(n for n, op in ops if op in T_OPS) != last_t - first_t:
        raise ExperimentError("clipped CIGAR consumption differs from recovered coordinates")
    return replace(hit, qs=qs, qe=qe, ts=first_t, te=last_t, ops=ops, matches=0, block=0, mapq=255)


def checked_statistics(hit: Hit, query: FastaStore, target: FastaStore) -> tuple[int, int, int]:
    """Check =/X against original bases and recompute stats, excluding ambiguity.

    Mapping quality, chaining scores and primary/secondary labels CANNOT be
    inherited after windowing. Those are deliberately absent/unknown in output.
    """
    q, t = 0, hit.ts
    matches = block = ambiguous = 0
    for size, op in hit.ops:
        for offset in range(0, size, CHUNK):
            n = min(CHUNK, size - offset)
            qb = tb = b""
            if op in Q_OPS:
                if hit.strand == "+":
                    qb = query.fetch(hit.query, hit.qs + q + offset, hit.qs + q + offset + n).translate(NT)
                else:
                    qb = query.fetch(hit.query, hit.qe - q - offset - n, hit.qe - q - offset).translate(NT).translate(RC)[::-1]
            if op in T_OPS:
                tb = target.fetch(hit.target, t + offset, t + offset + n).translate(NT)
            if op == "=":
                if qb != tb:
                    raise ExperimentError("= operation disagrees with original input bases")
                amb = qb.count(b"N")
                matches += n - amb
            elif op == "X":
                if any(a == b for a, b in zip(qb, tb)):
                    raise ExperimentError("X operation disagrees with original input bases")
                amb = qb.count(b"N") + tb.count(b"N")  # Both N would violate X.
            else:
                amb = (qb if op == "I" else tb).count(b"N")
            ambiguous += amb
            block += n - amb
        q += size if op in Q_OPS else 0
        t += size if op in T_OPS else 0
    return matches, block, ambiguous


def paf_line(hit: Hit, window: Window, ambiguous: int) -> str:
    columns = [hit.query, hit.qlen, hit.qs, hit.qe, hit.strand, hit.target, hit.tlen,
               hit.ts, hit.te, hit.matches, hit.block, 255]
    cigar = "".join(f"{size}{op}" for size, op in hit.ops)
    edit_distance = hit.block - hit.matches + ambiguous
    tags = [f"cg:Z:{cigar}", f"NM:i:{edit_distance}", f"nn:i:{ambiguous}", f"zw:Z:{window.alias}", "zp:Z:experimental-owned"]
    return "\t".join(map(str, columns + tags)) + "\n"


def coverage(intervals: list[tuple[int, int]]) -> dict:
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return {"covered_bases": sum(end - start for start, end in merged), "intervals": merged}


def recover(raw: Path, output: Path, provenance: Path, windows: list[Window], query: FastaStore, target: FastaStore, *, allow_empty_original_part=False) -> dict:
    by_alias = {window.alias: window for window in windows}
    query_intervals = defaultdict(list)
    target_intervals = defaultdict(list)
    seen = {}
    seen_windows = set()
    counts = {"raw_rows": 0, "owned_rows": 0, "context_only_rows": 0, "exact_duplicate_rows": 0}
    temporary = output.with_suffix(".paf.partial")
    with raw.open() as source, temporary.open("x") as out, provenance.open("x") as audit:
        for number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ExperimentError("incomplete last PAF line")
            raw_hit = parse_hit(line, by_alias, target.records)
            window = by_alias[raw_hit.query]
            seen_windows.add(window.alias)
            hit = lift(raw_hit, window)
            # Validate the entire raw alignment, not only the retained core.
            matches, block, _ = checked_statistics(hit, query, target)
            if (matches, block) != (raw_hit.matches, raw_hit.block):
                raise ExperimentError("raw PAF match/block counts disagree with original bases")
            counts["raw_rows"] += 1
            record = {"raw_line": number, "window": asdict(window), "raw_mapq": raw_hit.mapq,
                      "lifted": [hit.qs, hit.qe, hit.strand, hit.target, hit.ts, hit.te]}
            clipped = clip_to_core(hit, window)
            if clipped is None:
                counts["context_only_rows"] += 1
                record["status"] = "outside_owned_core"
            else:
                matches, block, ambiguous = checked_statistics(clipped, query, target)
                clipped = replace(clipped, matches=matches, block=block)
                if not block:
                    raise ExperimentError("owned alignment has no canonical-base support")
                key = (clipped.query, clipped.qs, clipped.qe, clipped.strand, clipped.target, clipped.ts, clipped.te, clipped.ops)
                if key in seen:
                    counts["exact_duplicate_rows"] += 1
                    record.update(status="exact_duplicate", owned_row=seen[key])
                else:
                    counts["owned_rows"] += 1
                    seen[key] = counts["owned_rows"]
                    out.write(paf_line(clipped, window, ambiguous))
                    record.update(status="retained", owned_row=counts["owned_rows"],
                                  owned=[clipped.qs, clipped.qe, clipped.ts, clipped.te],
                                  matches=matches, block=block)
                    query_intervals[clipped.query].append((clipped.qs, clipped.qe))
                    target_intervals[clipped.target].append((clipped.ts, clipped.te))
            audit.write(json.dumps(record) + "\n")
    if not counts["owned_rows"] and not (allow_empty_original_part and counts["raw_rows"] == 0):
        raise ExperimentError("no owned alignments: empty output is not a successful workaround")
    summary = {**counts, "windows": len(windows), "windows_without_raw_hits": sorted(set(by_alias) - seen_windows),
               "queries": {name: {"length": record["length"], **coverage(query_intervals[name])}
                           for name, record in query.records.items()},
               "targets": {name: {"length": record["length"], **coverage(target_intervals[name])}
                           for name, record in target.records.items()}}
    os.replace(temporary, output)
    return summary


def join_operations(operations) -> tuple[tuple[int, str], ...]:
    """Keep each numeric operation <= 28-bit even in an externally joined PAF.

    PAF is text; retaining adjacent same-type chunks avoids recreating an
    over-limit encoded operation. Their aggregate logical span may be longer.
    """
    result = []
    for length, op in operations:
        if length < 1:
            raise ExperimentError("nonpositive operation while stitching")
        if result and result[-1][1] == op and result[-1][0] < LIMIT:
            take = min(length, LIMIT - result[-1][0])
            result[-1] = (result[-1][0] + take, op)
            length -= take
        while length:
            take = min(length, LIMIT)
            result.append((take, op))
            length -= take
    return tuple(result)


def stitch_owned(source: Path, output: Path, provenance: Path, windows: list[Window], query: FastaStore, target: FastaStore, *, allow_empty_original_part=False) -> dict:
    """Reciprocal-unique EXACT adjacency only; no gap filling or placement choice.

    Chains may cross adjacent owned cores, never an original within-window split.
    Forks and disjoint/reversed paths remain separate. This recovers simple row
    continuity, not minimap2's whole-contig scoring/ranking semantics.
    """
    by_alias = {w.alias: w for w in windows}
    records = []
    entries, exits = defaultdict(list), defaultdict(list)
    for number, line in enumerate(source.read_text().splitlines(), 1):
        fields = line.split("\t")
        original = fields[0]
        length = query.records[original]["length"]
        whole = Window(original, original, length, 0, length, 0, length)
        hit = parse_hit(line, {original: whole}, target.records)
        tags = [tag[5:] for tag in fields[12:] if tag.startswith("zw:Z:")]
        if len(tags) != 1 or tags[0] not in by_alias:
            raise ExperimentError("missing window provenance during stitching")
        w = by_alias[tags[0]]
        if hit.query != w.query or not w.core_start <= hit.qs < hit.qe <= w.core_end:
            raise ExperimentError("owned row escaped its original core")
        startq, endq = (hit.qs, hit.qe) if hit.strand == "+" else (hit.qe, hit.qs)
        base = (hit.query, hit.target, hit.strand)
        entry, exit_key = (*base, startq, hit.ts), (*base, endq, hit.te)
        records.append((hit, w, entry, exit_key))
        entries[entry].append(number - 1)
        exits[exit_key].append(number - 1)
    following, preceding = {}, {}
    forks = 0
    for index, (hit, w, _entry, end) in enumerate(records):
        next_rows = entries.get(end, [])
        if len(next_rows) != 1 or len(exits[end]) != 1:
            forks += bool(next_rows)
            continue
        successor = next_rows[0]
        other, other_window, *_ = records[successor]
        adjacent = w.core_end == other_window.core_start if hit.strand == "+" else w.core_start == other_window.core_end
        if adjacent and hit.qlen == other.qlen and hit.tlen == other.tlen:
            following[index] = successor
            preceding[successor] = index
    emitted = set()
    temporary = output.with_suffix(".paf.partial")
    chain_count = joined_count = 0
    with temporary.open("x") as handle, provenance.open("x") as audit:
        for root in range(len(records)):
            if root in preceding:
                continue
            chain = [root]
            while chain[-1] in following:
                following_index = following[chain[-1]]
                if following_index in chain:
                    raise ExperimentError("cycle in candidate stitch graph")
                chain.append(following_index)
            if emitted.intersection(chain):
                raise ExperimentError("owned row used in multiple stitched chains")
            emitted.update(chain)
            hits = [records[i][0] for i in chain]
            combined = replace(hits[0], qs=min(h.qs for h in hits), qe=max(h.qe for h in hits),
                               te=hits[-1].te, ops=join_operations(op for h in hits for op in h.ops), mapq=255)
            if (sum(n for n, op in combined.ops if op in Q_OPS) != combined.qe - combined.qs
                    or sum(n for n, op in combined.ops if op in T_OPS) != combined.te - combined.ts):
                raise ExperimentError("stitched CIGAR does not match combined span")
            matches, block, ambiguous = checked_statistics(combined, query, target)
            if matches != sum(h.matches for h in hits) or block != sum(h.block for h in hits):
                raise ExperimentError("stitched counts changed")
            combined = replace(combined, matches=matches, block=block)
            text = paf_line(combined, records[root][1], ambiguous).rstrip("\n")
            text = text.replace("zp:Z:experimental-owned", "zp:Z:experimental-stitched")
            handle.write(text + f"\tzc:i:{len(chain)}\n")
            chain_count += 1
            joined_count += len(chain) - 1
            audit.write(json.dumps({"stitched_row": chain_count, "owned_rows": [i+1 for i in chain],
                                    "windows": [records[i][1].alias for i in chain],
                                    "join_rule": "reciprocal_unique_exact_query_and_target_adjacency"}) + "\n")
    if len(emitted) != len(records) or (not records and not allow_empty_original_part):
        raise ExperimentError("not all owned rows were represented by stitch chains")
    os.replace(temporary, output)
    return {"input_owned_rows": len(records), "stitched_rows": chain_count, "exact_joins": joined_count,
            "fork_endpoints_not_joined": forks, "ranking_reconstructed": False}


def run_command(command: list[str], directory: Path, name: str, timeout: int, memory_gib: int, *, max_file_bytes=None) -> dict:
    if max_file_bytes is not None and (type(max_file_bytes) is not int or max_file_bytes < 1):
        raise ExperimentError("child file-size limit must be a positive integer")
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if max_file_bytes is not None:
            soft,hard = resource.getrlimit(resource.RLIMIT_FSIZE)
            finite = [n for n in (soft,hard) if n != resource.RLIM_INFINITY]
            cap = min([max_file_bytes,*finite])
            resource.setrlimit(resource.RLIMIT_FSIZE, (cap, hard))
        if memory_gib:
            cap = memory_gib * 1024**3
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    write_json(directory / f"{name}.command.json", command)
    started = time.monotonic()
    report = {"command": command}
    with (directory / f"{name}.stdout").open("xb") as stdout, (directory / f"{name}.stderr").open("xb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True, preexec_fn=limits)
        try:
            report["returncode"] = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            report.update(returncode=process.returncode, interrupted=type(exc).__name__)
        report["seconds"] = round(time.monotonic() - started, 3)
    write_json(directory / f"{name}.execution.json", report)
    if report["returncode"] or "interrupted" in report:
        raise ExperimentError(f"{name} failed; evidence retained in {directory}")
    return report


def experiment(args) -> dict:
    if not args.target.is_file() or not args.query.is_file():
        raise ExperimentError("target/query input missing")
    if args.threads < 1 or args.timeout < 1 or args.memory_gib < 0:
        raise ExperimentError("invalid resource limits")
    make_windows({}, args.core_bases, args.context_bases)  # Validate before writing.
    candidate_policy = getattr(args, "window_candidate_policy", "native_window_selection")
    if candidate_policy not in ("native_window_selection", "all_chains_pool"):
        raise ExperimentError("unsupported experimental window candidate policy")
    executable = shutil.which(args.minimap2)
    if not executable:
        raise ExperimentError("minimap2 unavailable")
    executable = str(Path(executable).resolve())
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)  # Explicit new experiment only.
    report = {"schema_version": 1, "status": "running", "experimental_only": True,
              "production_ready": False, "customer_validated": False,
              "not_supported": ["self-alignment", "whole-contig ranking equivalence", "automatic Server integration"],
              "parameters": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}}
    write_json(root / "experiment.json", report)
    stores = []
    try:
        target = FastaStore(args.target, root / "target.bases")
        stores.append(target)
        query = FastaStore(args.query, root / "query.bases")
        stores.append(query)
        binary_hash = sha256(Path(executable))
        version = subprocess.check_output([executable, "--version"], text=True, timeout=5).strip()
        report.update(tool={"path": executable, "version": version, "sha256": binary_hash},
                      target=target.identity, query=query.identity)
        write_json(root / "experiment.json", report)
        windows = make_windows(query.records, args.core_bases, args.context_bases)
        write_json(root / "windows.json", [asdict(window) for window in windows])
        write_json(root / "input_records.json", {"target": target.records, "query": query.records})
        write_windows(root / "windows.fa", query, windows)
        window_manifest_hash = sha256(root/"windows.json")
        window_fasta_hash = sha256(root/"windows.fa")
        index_context = getattr(args,"index_context",None)
        if index_context is None:
            index = root / "target.mmi"
            # Legacy standalone experiment: one FULL-target index.
            index_bases = max(8_000_000_000, sum(record["length"] for record in target.records.values()) + 1)
            run_command([executable, "-x", args.preset, "-I", str(index_bases), "-t", str(args.threads),
                         "-d", str(index), str(target.source)], root, "index", args.timeout, args.memory_gib)
            if (root / "index.stderr").read_text(errors="replace").count("distinct minimizers:") != 1:
                raise ExperimentError("expected exactly one full-target index; cannot trust multipart ranking")
        else:
            # Branch-internal context: an ORIGINAL serialized index part, not a
            # freshly re-indexed subset or an unverified foreign cache.
            import minimap_index_context as mic
            try:
                index = mic.validate_part_context(index_context,reference_sha256=target.identity["sha256"],
                    tool_sha256=binary_hash,preset=args.preset,target_records=target.records)
            except mic.IndexContextError as exc:
                raise ExperimentError(str(exc)) from exc
        index_hash = sha256(index)
        mapping_flags = ["-f",str(index_context["mid_occ"])] if index_context is not None else []
        report.update(index_path=str(index),index_sha256=index_hash,
                      index_scope="original_default_part" if index_context is not None else "full_target_single_part",
                      original_part_index=index_context["part_index"] if index_context is not None else None,
                      inherited_mid_occ=index_context["mid_occ"] if index_context is not None else None)
        # Branch-only pool: avoid losing a whole-query competitor solely to a
        # window-local best_n/primary decision. -P is NOT a final output policy:
        # every row still undergoes base checks, core clipping, deduplication,
        # stitching and the unchanged guided refusal controls. It cannot prove
        # that local chaining/DP generated the entire native full-query universe.
        pool_flags = ["-P"] if candidate_policy == "all_chains_pool" else []
        report.update(window_candidate_policy=candidate_policy,
                      window_primary_selection_disabled=bool(pool_flags),
                      whole_query_candidate_completeness_certified=False)
        raw = root / "raw.windows.paf"
        run_command([executable, "-c", "--eqx", "-x", args.preset, *mapping_flags, *pool_flags, "-t", str(args.threads),
                     "-o", str(raw), str(index), str(root / "windows.fa")], root, "map", args.timeout, args.memory_gib)
        raw_hash = sha256(raw)
        candidate = root / "owned.pending.paf"
        allow_empty_part = index_context is not None and getattr(args,"allow_empty_index_part",False)
        summary = recover(raw, candidate, root / "provenance.jsonl", windows, query, target,
                          allow_empty_original_part=allow_empty_part)
        report["coverage"] = summary
        stitched = root / "stitched.pending.paf"
        report["stitching"] = stitch_owned(candidate, stitched, root / "stitch-provenance.jsonl", windows, query, target,
                                          allow_empty_original_part=allow_empty_part)
        if args.require_full_query_coverage and any(row["covered_bases"] != row["length"] for row in summary["queries"].values()):
            raise ExperimentError("full-query-coverage acceptance failed; do not treat partial mappings as complete")
        if (not all(store.unchanged() for store in stores) or sha256(Path(executable)) != binary_hash
                or sha256(index) != index_hash or sha256(raw) != raw_hash
                or sha256(root/"windows.json") != window_manifest_hash or sha256(root/"windows.fa") != window_fasta_hash):
            raise ExperimentError("input, window evidence, index or minimap2 binary changed during experiment")
        final_candidate = root / "owned.experimental.paf"
        os.replace(candidate, final_candidate)
        final_stitched = root / "stitched.experimental.paf"
        os.replace(stitched, final_stitched)
        report.update(status="validated_experimental_candidate", output_sha256=sha256(final_candidate), stitched_sha256=sha256(final_stitched),
                      raw_sha256=raw_hash,windows_manifest_sha256=window_manifest_hash,windows_fasta_sha256=window_fasta_hash,
                      original_inputs_unchanged=True,
                      caveat="Coordinate/CIGAR checks passed, NOT whole-contig alignment or downstream biological equivalence. "
                             "MAPQ is unknown (255), score/tp tags are not inherited; distinct placements are retained.")
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        for store in stores:
            store.close()
        write_json(root / "experiment.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New directory, must not exist")
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--preset", choices=("asm10", "asm5"), default="asm10")
    parser.add_argument("--core-bases", type=int, default=50_000_000)
    parser.add_argument("--context-bases", type=int, default=100_000, help="Each side, not total overlap")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600, help="Per minimap2 command, seconds")
    parser.add_argument("--memory-gib", type=int, default=10, help="Address-space cap, 0 disables")
    parser.add_argument("--require-full-query-coverage", action="store_true", help="Synthetic acceptance only, not a biological assumption")
    try:
        report = experiment(parser.parse_args())
    except (ExperimentError, OSError, subprocess.SubprocessError, UnicodeError) as exc:
        print(f"EXPERIMENT FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: report[key] for key in ("status", "experimental_only", "production_ready", "coverage")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
