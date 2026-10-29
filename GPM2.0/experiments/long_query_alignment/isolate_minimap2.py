#!/usr/bin/env python3
"""Opt-in, standalone query localization. Never a production alignment or retry.

Default: print a plan without creating files or starting minimap2. --execute is
required to scan FASTA and run one bounded diagnostic in a NEW directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import tarfile
import time

CHUNK = 1024 * 1024
DNA = b"ACGTRYSWKMBDHVN"
ASSERTION = "qoff == r->qe - r->qs && toff == r->re - r->rs"
CASES = {"locate": [], "eqx": ["--eqx"],
         "no-long-join": ["--no-long-join", "-r", "500,1000"]}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def identity(path):
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
            "ctime_ns": st.st_ctime_ns, "inode": st.st_ino}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def scan_fasta(path, deadline, selected=None, destination=None):
    """Bounded reads even for unwrapped chromosomes. Never trusts/writes .fai."""
    before = identity(path)
    digest = hashlib.sha256()
    records = {}
    current = None
    at_start = True
    output = destination.open("xb") if destination else None
    try:
        with path.open("rb") as stream:
            while raw := stream.readline(CHUNK):
                if time.monotonic() > deadline:
                    raise TimeoutError("FASTA scan exceeded overall time budget")
                digest.update(raw)
                header = at_start and raw.startswith(b">")
                at_start = raw.endswith(b"\n")
                if header:
                    if len(raw) > 4096:
                        raise ValueError("FASTA header exceeds 4096 bytes")
                    fields = raw[1:].split()
                    if not fields:
                        raise ValueError("empty FASTA ID")
                    current = fields[0].decode("ascii")
                    if any(ord(c) < 33 or ord(c) > 126 for c in current):
                        raise ValueError("unsupported FASTA ID")
                    if current in records:
                        raise ValueError("duplicate FASTA ID: " + current)
                    records[current] = 0
                    if output and current == selected:
                        output.write(b">" + current.encode("ascii") + b"\n")
                    continue
                seq = raw.rstrip(b"\r\n").upper()
                if not seq:
                    continue
                if current is None or seq.translate(None, DNA):
                    raise ValueError("plain IUPAC DNA FASTA required")
                records[current] += len(seq)
                if records[current] > 2147483647:
                    raise ValueError("record exceeds supported signed 32-bit coordinates")
                if output and current == selected:
                    output.write(seq + b"\n")
        if not records or any(n == 0 for n in records.values()):
            raise ValueError("empty FASTA/record")
        if selected is not None and selected not in records:
            raise ValueError("query ID not found: " + selected)
        if before != identity(path):
            raise ValueError("input changed during FASTA scan")
        return {"path": str(path), "stat": before, "sha256": digest.hexdigest(),
                "records": records, "total_bases": sum(records.values()),
                "max_length": max(records.values()), "content_scanned": True}
    finally:
        if output:
            output.close()


def parse_trace(path):
    """Only pair QR/QT emitted by minimap2 with a single mapping thread.

    A last printed name alone is NOT localization. Require an active unmatched
    QR, a matching assertion before its QT, and an otherwise well-formed trace.
    """
    active = None
    candidate = None
    malformed = False
    assertion = False
    completed = 0
    index_part = 0
    with path.open(errors="replace") as stream:
        for line in stream:
            if "loaded/built the index for" in line:
                index_part += 1
            fields = line.split()
            if fields and fields[0] == "QR":
                if active is not None or len(fields) != 4:
                    malformed = True
                    continue
                try:
                    active = {"query_id": fields[1], "thread_id": int(fields[2]), "length": int(fields[3]),
                              "target_index_part": index_part or None}
                    if active["length"] <= 0 or active["thread_id"] != 0:
                        malformed = True
                except ValueError:
                    malformed = True
            elif fields and fields[0] == "QT":
                if (active is None or len(fields) != 4 or fields[1] != active["query_id"]
                        or fields[2] != str(active["thread_id"])):
                    malformed = True
                active = None
                completed += 1
            elif "mm_update_extra" in line and ASSERTION in line:
                assertion = True
                if candidate is not None:
                    malformed = True
                candidate = dict(active) if active else None
    return {"same_assertion": assertion, "completed_query_events": completed,
            "index_parts_seen": index_part,
            "trace_well_formed": not malformed,
            "active_query_at_assertion": candidate if not malformed else None,
            "independent_replay_required": True}


def checked_plan(args):
    if min(args.timeout_seconds, args.memory_gib, args.max_file_gib, args.min_free_gib) <= 0:
        raise ValueError("resource limits must be positive")
    target, query, root = args.ref.resolve(), args.query.resolve(), args.out.resolve()
    if not target.is_file() or not query.is_file():
        raise ValueError("reference/query must be existing plain FASTA files")
    if args.out.exists() or args.out.is_symlink() or root.exists():
        raise ValueError("output must not exist; no evidence is overwritten")
    if not root.parent.is_dir():
        raise ValueError("output parent must already exist")
    for parent in (root.parent, *root.parent.parents):
        if (parent / "run_all.sh").exists() or (parent / ".prepare_lib").exists():
            raise ValueError("diagnostic output must be outside prepared Server workspace")
    mm = shutil.which(args.minimap2)
    if not mm:
        raise ValueError("minimap2 executable not found")
    mm = str(Path(mm).resolve())
    if args.case != "locate" and not args.query_id:
        raise ValueError("parameter contrasts require an explicitly selected query ID")
    if args.query_id is not None and (not args.query_id or any(ord(c) < 33 or ord(c) > 126 for c in args.query_id)):
        raise ValueError("query ID must be a printable ASCII token")
    mapped_query = root / "selected.query.fa" if args.query_id else query
    command = [mm, "-c", "-x", "asm10", "-t", "1", "--print-qname"] + CASES[args.case]
    command += ["-o", str(root / "alignment.diagnostic.partial.paf"), str(target), str(mapped_query)]
    return {"command": command, "reference": str(target), "query": str(query),
            "output": str(root), "query_id": args.query_id, "case": args.case,
            "timeout_seconds": args.timeout_seconds, "memory_gib": args.memory_gib,
            "max_file_gib": args.max_file_gib, "min_free_gib": args.min_free_gib,
            "expected_version": args.expected_version, "execute": args.execute,
            "production_ready": False, "automatic_retry": False,
            "note": "One mapping thread; original target FASTA/order and default index partitioning retained. No data skipping."}


def run_bounded(command, root, deadline, args):
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (args.memory_gib * 1024**3,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (args.max_file_gib * 1024**3,) * 2)
    process = None
    reason = None
    start = time.monotonic()
    try:
        with (root / "stdout.log").open("xb") as out, (root / "stderr.log").open("xb") as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, cwd=root,
                                       preexec_fn=limits, start_new_session=True)
            while process.poll() is None:
                if time.monotonic() > deadline:
                    reason = "timeout"
                    break
                if shutil.disk_usage(root).free < args.min_free_gib * 1024**3:
                    reason = "minimum_free_disk"
                    break
                time.sleep(0.2)
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return {"returncode": process.returncode, "stopped": reason,
            "elapsed_seconds": round(time.monotonic() - start, 3)}


def archive_report(root):
    # Deliberate allowlist: no sequence, PAF, binary, core or arbitrary directory.
    names = ["plan.json", "report.json", "inputs.json", "stdout.log", "stderr.log"]
    checksums = {}
    with tarfile.open(root / "diagnostics.tar.gz", "x:gz") as archive:
        for name in names:
            if (root / name).is_file():
                checksums[name] = sha256(root / name)
                archive.add(root / name, arcname=name, recursive=False)
    write_json(root / "checksums.json", checksums)
    return sha256(root / "diagnostics.tar.gz")


def execute(args, plan):
    root = Path(plan["output"])
    root.mkdir(mode=0o700, exist_ok=False)
    write_json(root / "plan.json", plan)
    started = time.monotonic()
    deadline = started + args.timeout_seconds
    report = {"status": "running", "production_ready": False, "customer_recovered": False,
              "harness_sha256": sha256(Path(__file__)), "plan": plan}
    write_json(root / "report.json", report)
    try:
        if shutil.disk_usage(root).free < args.min_free_gib * 1024**3:
            raise ValueError("insufficient free disk for diagnostic")
        mm = Path(plan["command"][0])
        version = subprocess.check_output([str(mm), "--version"], timeout=10, text=True).strip()
        report["tool"] = {"path": str(mm), "version": version, "sha256": sha256(mm)}
        if version != args.expected_version:
            raise ValueError("minimap2 version differs from explicit expected version")
        target, query = Path(plan["reference"]), Path(plan["query"])
        ref_info = scan_fasta(target, deadline)
        query_info = scan_fasta(query, deadline, args.query_id,
                                root / "selected.query.fa" if args.query_id else None)
        inputs = {"reference": ref_info, "query": query_info}
        if args.query_id:
            inputs["selected_query_sha256"] = sha256(root / "selected.query.fa")
        write_json(root / "inputs.json", inputs)
        if any(identity(p) != info["stat"] for p, info in [(target, ref_info), (query, query_info)]):
            raise ValueError("input changed before mapping")
        if time.monotonic() >= deadline:
            raise TimeoutError("no mapping time remains after input validation")
        report["execution"] = run_bounded(plan["command"], root, deadline, args)
        report["trace"] = parse_trace(root / "stderr.log")
        candidate = report["trace"]["active_query_at_assertion"]
        if candidate and (query_info["records"].get(candidate["query_id"]) != candidate["length"]
                          or (args.query_id and candidate["query_id"] != args.query_id)):
            report["trace"]["active_query_at_assertion"] = None
            report["trace"]["trace_well_formed"] = False
        unchanged = all(identity(p) == info["stat"] for p, info in [(target, ref_info), (query, query_info)])
        report["input_stats_unchanged"] = unchanged
        report["tool_unchanged"] = sha256(mm) == report["tool"]["sha256"]
        report["status"] = "diagnostic_completed"
        if not unchanged or not report["tool_unchanged"]:
            report["trace"]["active_query_at_assertion"] = None
            report["status"] = "input_or_tool_changed"
        report["alignment_exit_zero"] = report["execution"]["returncode"] == 0
        report["outcome"] = (report["execution"]["stopped"] or
                             ("alignment_assertion" if report["trace"]["same_assertion"] else
                              "exit_zero_unvalidated" if report["alignment_exit_zero"] else "other_failure"))
        # Even exit zero is not biological validity or a replacement PAF.
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="diagnostic_error", error=type(exc).__name__ + ": " + str(exc))
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_json(root / "report.json", report)
        digest = archive_report(root)
        print(json.dumps({"status": report["status"], "outcome": report.get("outcome"),
                          "execution": report.get("execution"), "trace": report.get("trace"),
                          "send_archive": str(root / "diagnostics.tar.gz"), "sha256": digest,
                          "warning": "DIAGNOSTIC ONLY. No production result or workaround accepted."}, indent=2))
    return 0 if report["status"] == "diagnostic_completed" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--expected-version", default="2.31-r1302")
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--memory-gib", type=int, required=True, help="address-space cap, not requested scheduler memory")
    parser.add_argument("--max-file-gib", type=int, default=8)
    parser.add_argument("--min-free-gib", type=int, default=16)
    parser.add_argument("--query-id")
    parser.add_argument("--case", choices=CASES, default="locate")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = checked_plan(args)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.execute:
        print(json.dumps(plan, indent=2))
        print("PLAN ONLY: no files created; no minimap2/job started.")
        return 0
    # Cluster termination should preserve metadata and stop our own process group.
    previous = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise InterruptedError("received SIGTERM")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        return execute(args, plan)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
