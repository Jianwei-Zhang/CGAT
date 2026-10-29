#!/usr/bin/env python3
"""Read-only review of a returned isolation archive. NEVER execute its commands.

Development status: implemented, execution tests deferred by user instruction.
The archive SHA must come from the operator through a separate trusted channel.
A checksum establishes transport consistency, not authenticity or a proven fix.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import time

MIB = 1024**2
MAX_COMPRESSED = 256*MIB
MAX_EXPANDED = 64*MIB
MAX_JSON = 4*MIB
MAX_LOG = 32*MIB
MAX_LINE = 64*1024
MEMBER_ORDER = ("plan.json", "report.json", "inputs.json", "stdout.log", "stderr.log")
ALLOWED = set(MEMBER_ORDER)
ASSERTION = "qoff == r->qe - r->qs && toff == r->re - r->rs"
CASES = {"locate": [], "eqx": ["--eqx"], "no-long-join": ["--no-long-join", "-r", "500,1000"]}


class ReviewError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def is_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def check_deadline(deadline):
    if time.monotonic() > deadline:
        raise ReviewError("archive review exceeded its bounded time budget")


def fingerprint(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


class BoundedDecodedStream:
    """Bounds decompressed TAR metadata too, before tarfile processes PAX headers."""
    def __init__(self, stream, deadline):
        self.stream, self.deadline, self.used = stream, deadline, 0

    def read(self, size):
        check_deadline(self.deadline)
        require(0 <= size <= MIB, "unbounded TAR stream read requested")
        # At the exact ceiling permit an EOF probe, but never another payload byte.
        raw = self.stream.read(min(size, MAX_EXPANDED - self.used + 1))
        self.used += len(raw)
        require(self.used <= MAX_EXPANDED, "expanded archive exceeds review budget")
        return raw


class TraceReview:
    """Independent bounded QR/QT pairing, not last-PAF-line attribution."""
    def __init__(self):
        self.active = self.candidate = None
        self.malformed = self.assertion = False
        self.completed = self.index_parts = self.assertions = 0
        self.records, self.selected = None, None

    def consume(self, raw):
        require(len(raw) <= MAX_LINE, "diagnostic log line exceeds review budget")
        if not raw.endswith(b"\n"):
            self.malformed = True
        line = raw.decode("utf-8", errors="strict")
        if "loaded/built the index for" in line:
            self.index_parts += 1
        fields = line.split()
        if fields and fields[0] == "QR":
            if self.active is not None or self.assertion or len(fields) != 4:
                self.malformed = True
                return
            try:
                thread, length = int(fields[2]), int(fields[3])
                if (thread != 0 or not 0 < length <= 2147483647 or
                        self.records is not None and self.records.get(fields[1]) != length or
                        self.selected is not None and self.selected != fields[1]):
                    raise ValueError
                self.active = {"query_id": fields[1], "thread_id": thread,
                               "length": length, "target_index_part": self.index_parts or None}
            except ValueError:
                self.malformed = True
        elif fields and fields[0] == "QT":
            valid = (self.active is not None and len(fields) == 4 and
                     fields[1] == self.active["query_id"] and fields[2] == "0" and not self.assertion)
            try:
                elapsed = float(fields[3]) if len(fields) == 4 else float("nan")
                valid = valid and math.isfinite(elapsed) and elapsed >= 0
            except ValueError:
                valid = False
            self.malformed |= not valid
            self.active = None
            self.completed += 1
        elif "mm_update_extra" in line and ASSERTION in line:
            self.assertion = True
            self.assertions += 1
            if self.assertions != 1:
                self.malformed = True
            self.candidate = dict(self.active) if self.active is not None else None

    def result(self):
        return {"same_assertion": self.assertion, "completed_query_events": self.completed,
                "index_parts_seen": self.index_parts, "trace_well_formed": not self.malformed,
                "active_query_at_assertion": self.candidate if not self.malformed else None,
                "independent_replay_required": True}


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(raw):
    raise ReviewError("non-finite JSON number")


def decode_json(raw):
    value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    require(type(value) is dict, "JSON metadata root must be an object")
    return value


def read_archive(path, expected_sha256, deadline):
    require(is_hash(expected_sha256), "expected archive SHA-256 must be 64 lowercase hex digits")
    path = Path(path)
    initial = path.lstat()
    require(stat.S_ISREG(initial.st_mode), "archive must be a regular file, not a symlink/device")
    require(initial.st_size <= MAX_COMPRESSED, "compressed archive exceeds review budget")
    metadata, digests, trace = {}, {}, TraceReview()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as raw:
        require(fingerprint(os.fstat(raw.fileno())) == fingerprint(initial), "archive changed before review")
        digest = hashlib.sha256()
        read_bytes = 0
        while block := raw.read(MIB):
            check_deadline(deadline)
            read_bytes += len(block)
            require(read_bytes <= MAX_COMPRESSED, "archive grew beyond review budget")
            digest.update(block)
        require(digest.hexdigest() == expected_sha256, "archive SHA-256 mismatch")
        raw.seek(0)
        with gzip.GzipFile(fileobj=raw, mode="rb") as decoded:
            bounded = BoundedDecodedStream(decoded, deadline)
            # No extract/extractall, no filesystem output. ignore_zeros forces
            # inspection of any appended TAR members as well as the first set.
            with tarfile.open(fileobj=bounded, mode="r|", ignore_zeros=True) as archive:
                last_member = -1
                for member in archive:
                    check_deadline(deadline)
                    require(member.name in ALLOWED and member.name not in digests,
                            "unexpected or duplicate archive member")
                    order = MEMBER_ORDER.index(member.name)
                    require(order > last_member, "archive member order differs from isolation producer")
                    last_member = order
                    require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE) and not member.sparse and
                            not any(k.startswith("GNU.sparse") for k in member.pax_headers),
                            "links, directories, sparse and special files are not reviewable")
                    cap = MAX_JSON if member.name.endswith(".json") else MAX_LOG
                    require(0 <= member.size <= cap, "archive member exceeds review budget")
                    stream = archive.extractfile(member)
                    require(stream is not None, "archive member cannot be read")
                    h = hashlib.sha256()
                    consumed = 0
                    if member.name.endswith(".json"):
                        payload = stream.read(cap + 1)
                        consumed = len(payload)
                        h.update(payload)
                        metadata[member.name] = decode_json(payload)
                    else:
                        if member.name == "stderr.log":
                            require("inputs.json" in metadata and "plan.json" in metadata,
                                    "stderr lacks preceding input provenance")
                            validate_input(metadata["inputs.json"].get("query"), metadata["plan.json"].get("query"))
                            trace.records = metadata["inputs.json"]["query"]["records"]
                            trace.selected = metadata["plan.json"].get("query_id")
                        while line := stream.readline(MAX_LINE + 1):
                            check_deadline(deadline)
                            require(len(line) <= MAX_LINE, "diagnostic log line exceeds review budget")
                            consumed += len(line)
                            h.update(line)
                            if member.name == "stderr.log":
                                trace.consume(line)
                    require(consumed == member.size, "incomplete archive member")
                    digests[member.name] = h.hexdigest()
            # Complete gzip CRC/length verification, still under decoded/time cap.
            while bounded.read(10240):
                pass
        require(fingerprint(os.fstat(raw.fileno())) == fingerprint(initial) and
                fingerprint(path.lstat()) == fingerprint(initial), "archive changed during review")
    require({"plan.json", "report.json"} <= metadata.keys(), "required diagnostic metadata is missing")
    return metadata, digests, trace.result()


def validate_input(info, expected_path):
    require(type(info) is dict and info.get("path") == expected_path and info.get("content_scanned") is True,
            "input scan identity is missing or inconsistent")
    require(is_hash(info.get("sha256")), "input SHA-256 is missing")
    records = info.get("records")
    require(type(records) is dict and bool(records), "input record lengths are missing")
    require(all(isinstance(name, str) and name and all(33 <= ord(c) <= 126 for c in name)
                and type(size) is int and 0 < size <= 2147483647 for name, size in records.items()),
            "invalid input record identity or length")
    require(type(info.get("total_bases")) is int and sum(records.values()) == info["total_bases"] and
            type(info.get("max_length")) is int and max(records.values()) == info["max_length"],
            "input length summary disagrees with records")


def review_archive(path, expected_sha256, *, expected_tool_sha256=None, expected_harness_sha256=None):
    deadline = time.monotonic() + 60
    metadata, digests, observed_trace = read_archive(path, expected_sha256, deadline)
    plan, report = metadata["plan.json"], metadata["report.json"]
    require(report.get("plan") == plan, "plan.json disagrees with report plan")
    require(plan.get("production_ready") is False and plan.get("automatic_retry") is False and
            plan.get("execute") is True and report.get("production_ready") is False and
            report.get("customer_recovered") is False, "diagnostic-only contract missing")
    if expected_harness_sha256 is None:
        expected_harness_sha256 = hashlib.sha256(Path(__file__).with_name("isolate_minimap2.py").read_bytes()).hexdigest()
    require(is_hash(expected_harness_sha256) and report.get("harness_sha256") == expected_harness_sha256,
            "isolation harness differs from explicitly expected source")
    if expected_tool_sha256 is not None:
        require(is_hash(expected_tool_sha256), "invalid expected tool hash")
    result = {"schema": 1, "archive_sha256": expected_sha256, "member_sha256": digests,
              "status": "unclassified", "reported_status": report.get("status"),
              "production_ready": False, "customer_recovered": False,
              "repair_accepted": False, "commands_executed": False, "files_extracted": False,
              "transport_hash_verified": True, "archive_authenticity_proven": False,
              "customer_fasta_rehashed_by_reviewer": False, "harness_sha256": expected_harness_sha256,
              "candidate_query": None, "independent_replay_required": True,
              "scope": "returned diagnostic evidence only; not scientific acceptance",
              "reviewer_execution_tests": "deferred_by_user"}
    if report.get("status") == "diagnostic_error":
        result.update(status="diagnostic_incomplete", next_step="review operator diagnostics; no repair conclusion")
        return result
    if report.get("status") == "input_or_tool_changed":
        result.update(status="identity_changed", next_step="establish stable inputs/tool before replay")
        return result
    require(report.get("status") == "diagnostic_completed", "unknown or incomplete report status")
    require(report.get("input_stats_unchanged") is True and report.get("tool_unchanged") is True,
            "completed report lacks stable input/tool metadata")
    require({"inputs.json", "stdout.log", "stderr.log"} <= digests.keys(), "completed report lacks evidence files")
    tool = report.get("tool")
    require(type(tool) is dict and is_hash(tool.get("sha256")) and
            tool.get("version") == plan.get("expected_version"), "tool identity is inconsistent")
    if expected_tool_sha256 is not None:
        require(tool["sha256"] == expected_tool_sha256, "tool hash differs from operator expectation")
    case, selected = plan.get("case"), plan.get("query_id")
    require(isinstance(case, str) and case in CASES, "unsupported diagnostic case")
    require(selected is None or isinstance(selected, str) and bool(selected) and
            all(33 <= ord(c) <= 126 for c in selected), "invalid selected query ID")
    require(case == "locate" or selected is not None, "parameter contrast lacks a selected query")
    for key in ("reference", "query", "output"):
        require(isinstance(plan.get(key), str) and PurePosixPath(plan[key]).is_absolute(), "invalid planned path")
    output = PurePosixPath(plan["output"])
    expected_command = [tool.get("path"), "-c", "-x", "asm10", "-t", "1", "--print-qname"] + CASES[case]
    expected_command += ["-o", str(output / "alignment.diagnostic.partial.paf"), plan["reference"],
                         str(output / "selected.query.fa") if selected is not None else plan["query"]]
    require(isinstance(tool.get("path"), str) and plan.get("command") == expected_command,
            "command differs from the supported single-thread CIGAR diagnostic")
    inputs = metadata["inputs.json"]
    for key in ("reference", "query"):
        validate_input(inputs.get(key), plan[key])
    if selected is not None:
        require(selected in inputs["query"]["records"] and is_hash(inputs.get("selected_query_sha256")),
                "selected-record provenance missing")
    require(report.get("trace") == observed_trace, "report attribution disagrees with independently parsed stderr")
    execution = report.get("execution")
    require(type(execution) is dict and type(execution.get("returncode")) is int and
            execution.get("stopped") in (None, "timeout", "minimum_free_disk"), "invalid execution metadata")
    exit_zero = execution["returncode"] == 0
    require(report.get("alignment_exit_zero") is exit_zero, "exit status metadata disagrees")
    expected_outcome = execution["stopped"] or ("alignment_assertion" if observed_trace["same_assertion"] else
                                                "exit_zero_unvalidated" if exit_zero else "other_failure")
    require(report.get("outcome") == expected_outcome, "outcome metadata disagrees with trace/exit")
    require(not (exit_zero and observed_trace["same_assertion"]), "assertion trace with zero exit cannot be accepted")
    candidate = observed_trace["active_query_at_assertion"]
    if candidate is not None:
        require(inputs["query"]["records"].get(candidate["query_id"]) == candidate["length"] and
                (selected is None or selected == candidate["query_id"]), "assertion candidate disagrees with scanned input")
    result.update(case=case, selected_query_id=selected, trace=observed_trace,
                  execution=execution, tool={"sha256":tool["sha256"], "version":tool["version"]},
                  tool_hash_matches_operator_expectation=expected_tool_sha256 is not None,
                  inputs={key:{"sha256":inputs[key]["sha256"], "total_bases":inputs[key]["total_bases"]}
                          for key in ("reference", "query")},
                  selected_query_sha256=inputs.get("selected_query_sha256"))
    if execution["stopped"]:
        result.update(status="resource_guard_stopped", next_step="review resource limit; not a fix or complete localization")
    elif observed_trace["same_assertion"]:
        result.update(status="assertion_candidate_localized" if candidate else "assertion_not_localized",
                      candidate_query=candidate,
                      next_step="independent whole-record replay with original target/order; no automatic launch")
    elif exit_zero:
        result.update(status="exit_zero_unvalidated", next_step="validate completeness, CIGAR/coordinates and downstream outputs; exit zero is not repair acceptance")
    else:
        result.update(status="other_failure", next_step="inspect failure evidence; do not label every nonzero exit as OOM")
    return result


def compare_reviews(baseline, current):
    """Compare independently reviewed receipts; never promote a parameter fix."""
    require(baseline.get("status") == "assertion_candidate_localized" and baseline.get("case") == "locate",
            "baseline must localize the original assertion without parameter changes")
    expected = baseline["candidate_query"]["query_id"]
    require(current.get("selected_query_id") == expected, "replay/contrast must select the baseline query")
    require(current.get("tool") == baseline.get("tool") and current.get("inputs") == baseline.get("inputs"),
            "reference/query content or tool identity changed between diagnostics")
    if current.get("case") in ("eqx", "no-long-join"):
        require(baseline.get("selected_query_id") == expected,
                "parameter comparison requires an independently failing selected-record baseline first")
    if baseline.get("selected_query_sha256") is not None:
        require(current.get("selected_query_sha256") == baseline["selected_query_sha256"], "selected-record bytes differ")
    if current.get("case") == "locate" and current.get("status") == "assertion_candidate_localized":
        conclusion = "same_assertion_on_selected_record; customer mechanism still needs investigation"
    elif current.get("case") in ("eqx", "no-long-join") and current.get("status") == "exit_zero_unvalidated":
        conclusion = "parameter_contrast_exited_zero_only; no PAF or scientific acceptance in this archive"
    else:
        conclusion = "no_verified_repair; inspect reviewed outcome"
    return {"conclusion":conclusion, "query_id":expected, "identity_metadata_consistent":True,
            "repair_accepted":False, "customer_recovered":False, "commands_executed":False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-tool-sha256")
    parser.add_argument("--expected-harness-sha256")
    parser.add_argument("--baseline-archive", type=Path)
    parser.add_argument("--baseline-sha256")
    args = parser.parse_args(argv)
    try:
        require(bool(args.baseline_archive) == bool(args.baseline_sha256), "baseline archive and SHA must be supplied together")
        kwargs = {"expected_tool_sha256":args.expected_tool_sha256,
                  "expected_harness_sha256":args.expected_harness_sha256}
        result = review_archive(args.archive, args.expected_sha256, **kwargs)
        if args.baseline_archive is not None:
            baseline = review_archive(args.baseline_archive, args.baseline_sha256, **kwargs)
            result["comparison"] = compare_reviews(baseline, result)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (OSError, EOFError, ValueError, TypeError, KeyError, RecursionError, tarfile.TarError) as exc:
        print(json.dumps({"status":"review_rejected", "error":str(exc), "repair_accepted":False,
                          "customer_recovered":False, "commands_executed":False, "files_extracted":False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
