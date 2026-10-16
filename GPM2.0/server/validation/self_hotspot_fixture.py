#!/usr/bin/env python3
"""Bounded real-query calibration; full target retained, not production windowing."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from self_query_batches import FLAGS, INDEX_FLAGS, atomic_json, records, sha, validate_raw
from self_alignment_experiments import paf_summary
from self_precision_compare import overlap, span

PROFILES = {
    "original-default": ["-c", "-x", "asm10", "-X", "--no-hash-name"],
    "current-n100": FLAGS,
    "freq100": [*FLAGS, "-U", "50,100"],
}


def bounded(command, directory, seconds):
    """Kill/reap the entire subprocess group on timeout or parent interruption."""
    directory.mkdir(parents=True, exist_ok=False)
    atomic_json(directory / "command.json", command)
    start = time.monotonic()
    with (directory / "raw.paf").open("wb") as out, (directory / "stderr.log").open("wb") as err:
        proc = subprocess.Popen(
            ["/usr/bin/time", "-v", "-o", str(directory / "resource.txt"), *command],
            stdout=out, stderr=err, start_new_session=True,
        )
        try:
            rc = proc.wait(timeout=seconds)
            status = "COMPLETED" if rc == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
        finally:
            # Even if the group leader already exited, reap any remaining child.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    result = {"status": status, "seconds": time.monotonic() - start,
              "limit_seconds": seconds, "returncode": proc.returncode}
    atomic_json(directory / "status.json", result)
    return result


def windows(length):
    seen = set()
    for size in (250_000, 1_000_000):
        width = min(size, length)
        for position, start in (("start", 0), ("middle", (length-width)//2), ("end", length-width)):
            key = (start, start+width)
            if key not in seen:
                seen.add(key)
                yield f"{width}-{position}", key


def comparison(baseline, candidate):
    left = baseline["strong_query_coverage_by_pair_strand"]
    right = candidate["strong_query_coverage_by_pair_strand"]
    total = sum(span(v) for v in left.values())
    retained = sum(overlap(v, right.get(k, [])) for k, v in left.items())
    return {"ordered_equal": baseline["ordered_sha256"] == candidate["ordered_sha256"],
            "baseline_rows": baseline["rows"], "candidate_rows": candidate["rows"],
            "strong_coverage_retained": retained/total if total else None,
            "missing_pairs_or_strands": sorted(set(left)-set(right))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--query-name", help="Select a recorded alias explicitly; otherwise use longest")
    p.add_argument("--window-timeout", type=float, default=10)
    p.add_argument("--whole-timeout", type=float, default=45)
    a = p.parse_args()
    if min(a.window_timeout, a.whole_timeout) <= 0:
        p.error("Timeouts must be positive")
    a.root = a.root.resolve()
    a.root.mkdir(parents=True, exist_ok=False)
    report = {"status": "RUNNING", "phase": "prepare", "cases": [],
              "boundary": "Full original target; a selected real query, whole or sampled windows. Windows change query context and coordinates, never merged into production results. TIMEOUT is a censored lower bound, never a completed result. Single-pass shared-node timings are calibration only; no Final Path or ground-truth precision claim."}
    started = time.monotonic()
    def save():
        report["elapsed_seconds"] = time.monotonic() - started
        atomic_json(a.root / "report.json", report)
    def interrupt(signum, frame):
        raise InterruptedError(f"Received signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    save()
    try:
        mm = shutil.which("minimap2")
        if not mm:
            raise RuntimeError("minimap2 unavailable")
        target = a.source / "self_target.fa"
        query = a.source / "self_query.fa"
        report["source"] = {"directory": str(a.source), "target_sha256": sha(target), "query_sha256": sha(query)}
        report["tool"] = {"path": mm, "sha256": sha(mm)}
        report["profiles"] = PROFILES
        target_names = {h[1:].split()[0].decode(): sum(len(s.strip()) for s in b.splitlines()) for h, b in records(target)}
        if sum(target_names.values()) >= 8_000_000_000:
            raise ValueError("Multipart target unsupported")
        longest = None
        report["query_inventory"] = []
        for header, body in records(query):
            sequence = b"".join(body.split())
            alias = header[1:].split()[0].decode()
            report["query_inventory"].append({"name": alias, "length": len(sequence)})
            if a.query_name:
                if alias == a.query_name:
                    longest = (header, sequence)
            elif longest is None or len(sequence) > len(longest[1]):
                longest = (header, sequence)
        if longest is None:
            raise ValueError("No matching query record")
        header, sequence = longest
        name = header[1:].split()[0].decode()
        report["selected_query"] = {"name": name, "length": len(sequence), "selection": "explicit alias" if a.query_name else "longest, not proven slowest"}
        report["phase"] = "index"; save()
        index = a.root / "target.mmi"
        index_result = bounded([mm, *INDEX_FLAGS, "-t", "2", "-d", str(index), str(target)], a.root / "index-build", 60)
        report["index"] = index_result
        if index_result["status"] != "COMPLETED":
            raise RuntimeError("Index build did not complete in bounded time")
        if (a.root / "index-build/stderr.log").read_text().count("distinct minimizers:") != 1:
            raise ValueError("Multipart/unknown index rejected")
        report["index"]["sha256"] = sha(index)
        trials = list(windows(len(sequence))) + [("whole-query", (0, len(sequence)))]
        for ordinal, (label, (lo, hi)) in enumerate(trials):
            report["phase"] = label
            directory = a.root / label
            directory.mkdir()
            query_path = directory / "query.fa"
            with query_path.open("wb") as f:
                f.write(header)
                for pos in range(lo, hi, 80):
                    f.write(sequence[pos:min(pos+80, hi)] + b"\n")
            row = {"name": label, "original_query": name, "interval_0based_half_open": [lo, hi],
                   "query_sha256": sha(query_path), "profiles": {}, "comparisons": {}}
            report["cases"].append(row); save()
            profiles = list(PROFILES)
            profiles = profiles[ordinal % len(profiles):] + profiles[:ordinal % len(profiles)]
            row["profile_order"] = profiles
            for profile in profiles:
                dest = directory / profile
                limit = a.whole_timeout if label == "whole-query" else a.window_timeout
                result = bounded([mm, *PROFILES[profile], "-t", "1", str(index), str(query_path)], dest, limit)
                if result["status"] == "COMPLETED":
                    if (dest / "stderr.log").read_text().count("distinct minimizers:") != 1:
                        raise ValueError("Mapping index part count changed")
                    validate_raw(dest / "raw.paf", [{"name": name, "length": hi-lo}], target_names)
                    result["paf"] = paf_summary(dest / "raw.paf")
                row["profiles"][profile] = result; save()
            base = row["profiles"]["current-n100"]
            for profile, result in row["profiles"].items():
                if "paf" in base and "paf" in result:
                    row["comparisons"][profile] = comparison(base["paf"], result["paf"])
            save()
        # Candidates only: slow enough to measure but bounded enough to iterate.
        report["performance_candidates"] = [r["name"] for r in report["cases"]
            if r["name"] != "whole-query" and any(v["seconds"] >= 2 for v in r["profiles"].values())]
        report["status"] = "CALIBRATED" if report["performance_candidates"] else "NO_SLOW_WINDOW_FOUND"
        if any(v["status"] == "FAILED" for r in report["cases"] for v in r["profiles"].values()):
            raise RuntimeError("A profile failed; inspect logs")
        report["phase"] = "finished"; save()
        print(json.dumps({k:v for k,v in report.items() if k != "cases"}, indent=2))
    except BaseException as error:
        report["status"] = "FAILED"
        report["error"] = repr(error)
        save()
        raise


if __name__ == "__main__":
    main()
