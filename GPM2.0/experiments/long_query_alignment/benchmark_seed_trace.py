#!/usr/bin/env python3
"""Opt-in synthetic trace resource comparison, never a customer alignment.

Freezes the pre-streaming witness from a known repository commit, then measures
old/new collectors in separate equally capped Linux processes. No minimap2 runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import audit_post_dp as audit
import stream_seed_trace as st
import windowed_alignment as wa

BASELINE_REVISION = "2bb61fafa0063067b88310b7938267f8d469a134"
BASELINE_PATH = "GPM2.0/experiments/long_query_alignment/audit_post_dp.py"


def generate(root, name, seeds, extra_groups=0):
    path = root / (name + ".trace")
    length = 20 * seeds - 1
    split = seeds * 3 // 5
    coarse = {"query": "q", "query_length": length, "target": "decoy", "target_length": length,
              "strand": "+", "query_start": 0, "query_end": length, "target_start": 0,
              "target_end": length, "minimizers": seeds, "chain_score": 2 * seeds}
    fragments = [{**coarse, "query_end": 20*split-1, "target_end": 20*split-1},
                 {**coarse, "query_start": 20*split, "target_start": 20*split}]
    with path.open("x") as out:
        out.write(f"QR\tq\t0\t{length}\n")
        for group in range(extra_groups):
            out.write(f"CN\t{group}\tother\t1\t+\t1\t2\t0\n")
        for seed in range(seeds):
            end = 20 * seed + 18
            out.write(f"CN\t{extra_groups}\tdecoy\t{end}\t+\t{end}\t19\t0\n")
        out.write("QT\tq\t0\t0.1\n")
    meta = {"trace": str(path), "trace_sha256": wa.sha256(path), "trace_bytes": path.stat().st_size,
            "coarse": coarse, "fragments": fragments, "expected_counts": [split, seeds-split],
            "expected_scores": [2*split, 2*(seeds-split)], "extra_groups": extra_groups}
    metadata = root / (name + ".json")
    wa.write_json(metadata, meta)
    return metadata


def worker(meta_path, baseline_path, mode, memory_mib, read_buffer_kib):
    # Load both modules for equal interpreter/module baseline before the cap.
    spec = importlib.util.spec_from_file_location("frozen_audit", baseline_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    meta = json.loads(meta_path.read_text())
    cap = memory_mib * 1024**2
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    started = time.monotonic()
    result = None
    status = "success"
    try:
        reconstruct = old.reconstruct_split_scores if mode == "legacy" else audit.reconstruct_split_scores
        options = {} if mode == "legacy" else {"trace_budget": st.TraceBudget(read_buffer_bytes=read_buffer_kib * 1024 if read_buffer_kib else None)}
        result = reconstruct(Path(meta["trace"]), [meta["coarse"]], meta["fragments"], **options)
    except MemoryError:
        status = "memory_budget_exceeded"
    except Exception as exc:
        status = type(exc).__name__ + ": " + str(exc)
    output = {"mode": mode, "status": status, "memory_cap_mib": memory_mib,
              "read_buffer_kib": read_buffer_kib if mode == "stream" else None,
              "elapsed_seconds": round(time.monotonic()-started, 6),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "result": result}
    print(json.dumps(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--memory-mib", type=int, default=128)
    parser.add_argument("--large-seeds", type=int, default=1_000_000)
    parser.add_argument("--read-buffer-kib", type=int, choices=(0, 8, 64, 1024, 16384), default=0, help="0=budget-adaptive; otherwise explicit target buffer")
    parser.add_argument("--worker", choices=["legacy", "stream"])
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    if not 64 <= args.memory_mib <= 1024 or not 10_000 <= args.large_seeds <= 2_000_000:
        parser.error("require 64..1024 MiB and 10000..2000000 seeds")
    if args.worker:
        if args.metadata is None or args.baseline is None:
            parser.error("worker requires metadata and frozen baseline")
        worker(args.metadata, args.baseline, args.worker, args.memory_mib, args.read_buffer_kib)
        return
    if args.out is None:
        parser.error("--out is required")
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    baseline = root / "frozen_audit_post_dp.py"
    content = subprocess.check_output(["git", "show", BASELINE_REVISION + ":" + BASELINE_PATH],
                                      cwd=Path(__file__).resolve().parents[3])
    baseline.write_bytes(content)
    report = {"synthetic_trace_only": True, "production_ready": False, "customer_validated": False,
              "baseline_revision": BASELINE_REVISION, "baseline_sha256": hashlib.sha256(content).hexdigest(),
              "source_sha256": {Path(p).name: wa.sha256(Path(p)) for p in (__file__, audit.__file__, st.__file__, st.tm.__file__, wa.__file__)},
              "cases": []}
    wa.write_json(root / "benchmark.json", report)
    for name, seeds, groups in [("small", 10_000, 0), ("large", args.large_seeds, 0), ("many_groups", 5, 100_000)]:
        metadata = generate(root, name, seeds, groups)
        meta = json.loads(metadata.read_text())
        case = {"case": name, "trace_bytes": meta["trace_bytes"], "trace_sha256": meta["trace_sha256"],
                "selected_seeds": seeds, "extra_groups": groups, "runs": []}
        for mode in ("legacy", "stream"):
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
                       "--metadata", str(metadata), "--baseline", str(baseline), "--memory-mib", str(args.memory_mib),
                       "--read-buffer-kib", str(args.read_buffer_kib)]
            log = root / (name + "." + mode)
            with log.with_suffix(log.suffix + ".stdout").open("xb") as stdout, log.with_suffix(log.suffix + ".stderr").open("xb") as stderr:
                completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=180)
            stdout_path = log.with_suffix(log.suffix + ".stdout")
            if completed.returncode != 0:
                raise RuntimeError("benchmark worker failed; retained stdout/stderr")
            result = json.loads(stdout_path.read_text())
            if result["status"] == "success":
                for key, expected in [("fragment_anchor_counts", meta["expected_counts"]),
                                      ("reconstructed_chain_scores", meta["expected_scores"]),
                                      ("trace_sha256", meta["trace_sha256"])]:
                    if result["result"][key] != expected:
                        raise RuntimeError("benchmark semantic mismatch: " + key)
            elif mode == "stream" or result["status"] != "memory_budget_exceeded":
                raise RuntimeError("unexpected benchmark failure: " + result["status"])
            case["runs"].append({"command": command, **result})
        if all(run["status"] == "success" for run in case["runs"]):
            before, after = [dict(run["result"]) for run in case["runs"]]
            after.pop("trace_resources", None)
            if before != after:
                raise RuntimeError("full witness differs from frozen baseline")
        report["cases"].append(case)
        wa.write_json(root / "benchmark.json", report)
        print(json.dumps({"case": name, "runs": [{k: run[k] for k in ("mode", "status", "peak_rss_kib", "elapsed_seconds")} for run in case["runs"]]}), flush=True)
    report["status"] = "completed_resource_and_witness_audit_not_recovery"
    wa.write_json(root / "benchmark.json", report)


if __name__ == "__main__":
    main()
