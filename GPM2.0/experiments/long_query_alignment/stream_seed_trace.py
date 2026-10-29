"""Bounded CN evidence reader for the positive/two-fragment score witness.

Pinned diagnostic subset: one query, thread zero, increasing contiguous CN chain
IDs as emitted by minimap2 v2.31 map.c. No alignment, candidate selection or MAPQ.
One current-chain summary plus one matched summary; no per-seed/per-chain store.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import time

from windowed_alignment import ExperimentError


@dataclass(frozen=True)
class TraceBudget:
    max_bytes: int = 512 * 1024 * 1024
    max_lines: int = 10_000_000
    max_line_bytes: int = 64 * 1024
    timeout_seconds: float = 120.0

    def validate(self):
        if any(type(n) is not int or n <= 0 for n in
               (self.max_bytes, self.max_lines, self.max_line_bytes)):
            raise ExperimentError("trace byte/line budgets must be positive integers")
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ExperimentError("trace time budget must be positive and finite")


def stat_identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def collect_split_counts(path: Path, coarse: dict, fragments: list[dict],
                         budget: TraceBudget | None = None):
    """Caller validates positive-strand two-fragment geometry before entry.

    A bounded binary read/hash pass validates every CN row, including irrelevant
    chains. Ownership/monotonicity errors on a nonmatching chain are ignored just
    as in the previous collector; errors on the uniquely matching chain fail.
    A QR-only synthetic excerpt is accepted as before; QT, if present, is checked.
    The enclosing audit separately requires successful trace-producer execution.
    """
    budget = budget or TraceBudget()
    budget.validate()
    if len(fragments) != 2:
        raise ExperimentError("stream witness requires exactly two validated fragments")
    start = time.monotonic()
    deadline = start + budget.timeout_seconds
    digest = hashlib.sha256()
    byte_count = line_count = seed_count = group_count = 0
    query_seen = query_done = False
    current = None
    match = None

    def finish(group):
        nonlocal match
        if group is None or group["key"][1:] != (coarse["target"], "+"):
            return
        first_t, first_q, span = group["first"]
        last_t, last_q, _ = group["last"]
        bounds = (first_q + 1 - span, last_q + 1, first_t + 1 - span, last_t + 1)
        expected = tuple(coarse[k] for k in ("query_start", "query_end", "target_start", "target_end"))
        if group["count"] != coarse["minimizers"] or bounds != expected:
            return
        if match is not None:
            raise ExperimentError("no unique original seed chain matches coarse PAF")
        match = {"counts": list(group["counts"]), "count": group["count"],
                 "non_monotonic": group["non_monotonic"], "bad_ownership": group["bad_ownership"]}

    # NONBLOCK prevents a FIFO from hanging before we can reject nonregular input.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ExperimentError("trace must be a regular file")
        if before.st_size > budget.max_bytes:
            raise ExperimentError("trace exceeds byte budget")
        while True:
            if time.monotonic() > deadline:
                raise ExperimentError("trace processing time budget exceeded")
            raw = stream.readline(min(budget.max_line_bytes, budget.max_bytes - byte_count) + 1)
            if not raw:
                break
            byte_count += len(raw)
            line_count += 1
            if byte_count > budget.max_bytes:
                raise ExperimentError("trace exceeds byte budget")
            if line_count > budget.max_lines:
                raise ExperimentError("trace exceeds line-count budget")
            if len(raw) > budget.max_line_bytes:
                raise ExperimentError("trace exceeds line-length budget")
            if not raw.endswith(b"\n"):
                raise ExperimentError("trace has an incomplete trailing line")
            digest.update(raw)
            if not raw.startswith((b"QR\t", b"QT\t", b"CN\t")):
                if raw.startswith((b"QR", b"QT", b"CN")):
                    raise ExperimentError("unsupported CN/QR/QT record delimiter")
                continue
            try:
                fields = raw.rstrip(b"\r\n").decode("utf-8", errors="strict").split("\t")
                if fields[0] == "QR":
                    if query_seen or fields != ["QR", coarse["query"], "0", str(coarse["query_length"])]:
                        raise ExperimentError("trace/DP query identity or length does not match the coarse candidate")
                    query_seen = True
                    continue
                if fields[0] == "QT":
                    if (not query_seen or query_done or len(fields) != 4
                            or fields[1:3] != [coarse["query"], "0"]
                            or not math.isfinite(float(fields[3])) or float(fields[3]) < 0):
                        raise ExperimentError("unsupported QT trace identity or format")
                    query_done = True
                    continue
                if len(fields) != 8 or not query_seen or query_done:
                    raise ExperimentError("unsupported CN trace format or query scope")
                key = (int(fields[1]), fields[2], fields[4])
                t, q, span = int(fields[3]), int(fields[5]), int(fields[6])
                int(fields[7])  # diagnostic gap delta must still be an integer
            except ExperimentError:
                raise
            except (UnicodeError, ValueError) as exc:
                raise ExperimentError("unsupported numeric or text CN/QR/QT trace format") from exc
            if (not 0 <= key[0] <= 2147483647 or key[2] not in ("+", "-")
                    or not 1 <= span <= 255 or min(t, q) < span - 1
                    or max(t, q) > 2147483647 or q >= coarse["query_length"]):
                raise ExperimentError("invalid CN seed coordinates or chain identity")
            if current is None or current["key"] != key:
                if current is not None and key[0] <= current["key"][0]:
                    raise ExperimentError("non-contiguous or unordered CN chain IDs unsupported")
                finish(current)
                current = {"key": key, "first": (t, q, span), "last": None,
                           "count": 0, "counts": [0, 0], "non_monotonic": False, "bad_ownership": False}
                group_count += 1
            last = current["last"]
            if last and (t <= last[0] or q <= last[1]):
                current["non_monotonic"] = True
            current["last"] = (t, q, span)
            current["count"] += 1
            seed_count += 1
            if key[1:] == (coarse["target"], "+"):
                owner = None
                for i, row in enumerate(fragments):
                    if (row["query_start"] <= q + 1 - span and q < row["query_end"]
                            and row["target_start"] <= t + 1 - span and t < row["target_end"]):
                        if owner is not None:
                            current["bad_ownership"] = True
                        owner = i
                if owner is None:
                    current["bad_ownership"] = True
                else:
                    current["counts"][owner] += 1
        finish(current)
        after = os.fstat(stream.fileno())
        if stat_identity(before) != stat_identity(after) or stat_identity(before) != stat_identity(path.stat()):
            raise ExperimentError("trace changed during streaming scan")
        if byte_count != before.st_size:
            raise ExperimentError("trace length changed during streaming scan")
    if not query_seen:
        raise ExperimentError("trace/DP query identity or length does not match the coarse candidate")
    if match is None:
        raise ExperimentError("no unique original seed chain matches coarse PAF")
    if match["non_monotonic"]:
        raise ExperimentError("non-monotonic seed chain unsupported by witness")
    if match["bad_ownership"]:
        raise ExperimentError("seed missing from or shared by DP fragments")
    if time.monotonic() > deadline:
        raise ExperimentError("trace processing time budget exceeded")
    return {"fragment_anchor_counts": match["counts"], "original_anchor_count": match["count"],
            "trace_sha256": digest.hexdigest(),
            "resources": {"bytes_read": byte_count, "lines_read": line_count, "seed_rows": seed_count,
                          "chain_groups": group_count, "query_end_marker_observed": query_done,
                          "elapsed_seconds": round(time.monotonic() - start, 6), "limits": asdict(budget),
                          "storage": "one_chain_summary_plus_one_match; no seed arrays or chain dictionary"}}
