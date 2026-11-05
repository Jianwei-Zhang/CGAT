#!/usr/bin/env python3
"""Opt-in ordinary native mapping comparison on existing READ-ONLY FASTA inputs.

Only K changes between runs. One original default MMI, complete records in their
original order, no index repartitioning, sensitivity changes, windows or recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess

import ordinary_batch_performance as perf

ALPHABET = b"ACGTNRYKMSWBDHVacgtnrykmswbdhv"
QUERY_LIMIT = 268_435_455


def identity(path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "ctime_ns": stat.st_ctime_ns,
            "inode": stat.st_ino}


def catalog(path, *, ordinary_query=False):
    path = path.resolve()
    before, digest = identity(path), hashlib.sha256()
    records, current, line_start = [], None, True
    names = set()
    with path.open("rb") as stream:
        for raw in iter(lambda: stream.readline(1024**2), b""):
            digest.update(raw)
            if line_start and raw.startswith(b">"):
                if len(raw) >= 1024**2 and not raw.endswith(b"\n"):
                    raise ValueError("FASTA header too long")
                words = raw[1:].split()
                if not words:
                    raise ValueError("empty FASTA identifier")
                name = words[0].decode("ascii")
                if name in names or any(not 33 <= ord(c) <= 126 for c in name):
                    raise ValueError("duplicate or invalid FASTA identifier")
                names.add(name)
                current = {"name": name, "length": 0}
                records.append(current)
            else:
                sequence = raw.rstrip(b"\r\n")
                if sequence:
                    if current is None or sequence.translate(None, ALPHABET):
                        raise ValueError("plain IUPAC DNA FASTA required")
                    current["length"] += len(sequence)
                    if ordinary_query and current["length"] > QUERY_LIMIT:
                        raise ValueError("ordinary-only comparison refuses an oversized query")
            line_start = raw.endswith(b"\n")
    if not records or any(r["length"] < 1 for r in records) or identity(path) != before:
        raise ValueError("empty or changed FASTA input")
    return {"source": str(path), **before, "sha256": digest.hexdigest(), "records": records,
            "total_bases": sum(r["length"] for r in records)}


def resource_snapshot():
    report = {"hostname": os.uname().nodename, "architecture": os.uname().machine,
              "visible_cpus": os.cpu_count(), "affinity": sorted(os.sched_getaffinity(0)),
              "quota_and_cpuset_observations": {}}
    paths = {Path("/proc/self/cgroup"), Path("/proc/self/status"),
             Path("/sys/fs/cgroup/cpu.max"), Path("/sys/fs/cgroup/memory.max"),
             Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"), Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")}
    membership = Path("/proc/self/cgroup")
    if membership.is_file():
        for line in membership.read_text().splitlines():
            fields = line.split(":", 2)
            if len(fields) != 3 or ".." in Path(fields[2]).parts:
                continue
            _, controllers, relative = fields
            relative = relative.lstrip("/")
            if not controllers:
                leaf = Path("/sys/fs/cgroup") / relative
                paths.update(leaf / name for name in ("cpu.max", "memory.max", "cpuset.cpus.effective"))
            for controller in controllers.split(","):
                names = {"cpu": ("cpu.cfs_quota_us", "cpu.cfs_period_us", "cpu.shares"),
                         "memory": ("memory.limit_in_bytes",), "cpuset": ("cpuset.cpus",)}.get(controller, ())
                for mount in (controller, controllers):
                    leaf = Path("/sys/fs/cgroup") / mount / relative
                    paths.update(leaf / name for name in names)
    for path in sorted(paths):
        try:
            if not path.is_file():
                continue
            text = path.read_text()
            if path.name == "status":
                text = "\n".join(line for line in text.splitlines() if line.startswith(("Cpus_allowed", "Mems_allowed", "Threads:")))
            report["quota_and_cpuset_observations"][str(path)] = text[:65536]
        except OSError as error:
            report["quota_and_cpuset_observations"][str(path)] = {"read_error": str(error)}
    return report


def execute(args):
    executable = shutil.which(args.minimap2)
    if not executable:
        raise ValueError("minimap2 unavailable")
    executable = str(Path(executable).resolve())
    if subprocess.check_output([executable, "--version"], text=True, timeout=10).strip() != perf.VERSION:
        raise ValueError("requires minimap2 " + perf.VERSION)
    target, query = args.target.resolve(), args.query.resolve()
    root = args.out.resolve()
    if target == query or root == target or root == query:
        raise ValueError("separate original reference, query and fresh output required")
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "scope": "ordinary_reference_alignment_only",
              "customer_wheat_data": False, "existing_inputs_read_only": True,
              "mapper_version": perf.VERSION, "mapper_sha256": perf.sha256(executable),
              "resource_snapshot": resource_snapshot(), "threads": args.threads, "runs": [],
              "harness_sha256": perf.sha256(__file__), "runner_sha256": perf.sha256(perf.__file__)}
    perf.write_json(root / "benchmark.json", report)
    try:
        sources = {"reference": catalog(target), "query": catalog(query, ordinary_query=True)}
        report["sources"] = sources
        perf.write_json(root / "benchmark.json", report)
        index = root / "target.default.mmi"
        report["index_build"] = perf.run([executable, "-x", "asm10", "-t", str(args.threads),
            "-d", str(index), str(target)], root, "index", args.timeout, args.memory_mib)
        index_sha = perf.sha256(index)
        expected_digest = None
        for repeat in range(args.repeats):
            sizes = args.batch_bases if repeat % 2 == 0 else list(reversed(args.batch_bases))
            for size in sizes:
                stem = f"r{repeat:02d}-K{size}"
                output = root / (stem + ".paf")
                result = perf.run([executable, "-c", "-x", "asm10", "-t", str(args.threads), "-K", str(size),
                    "-o", str(output), str(index), str(query)], root, stem, args.timeout, args.memory_mib)
                if not output.is_file() or output.stat().st_size == 0:
                    raise ValueError("empty PAF is not a successful real-assembly comparison")
                digest = perf.sha256(output)
                if expected_digest is None:
                    expected_digest = digest
                if digest != expected_digest:
                    raise ValueError("ordered PAF changed; no performance recommendation")
                native = perf.parse_log((root / (stem + ".stderr")).read_text())
                counts = [len(batch) for batch in perf.partition(sources["query"]["records"], size)]
                if any([batch["records"] for batch in part["batches"]] != counts for part in native["parts"]):
                    raise ValueError("observed query minibatch boundaries differ from prediction")
                if perf.sha256(executable) != report["mapper_sha256"]:
                    raise ValueError("minimap2 binary changed during comparison")
                if perf.sha256(index) != index_sha:
                    raise ValueError("original index changed")
                for source in sources.values():
                    if identity(Path(source["source"])) != {key: source[key] for key in ("size", "mtime_ns", "ctime_ns", "inode")}:
                        raise ValueError("original FASTA metadata changed")
                result.update(repeat=repeat, batch_bases=size, paf_sha256=digest, paf_bytes=output.stat().st_size,
                    exact_ordered_paf_equal=True, actual_index_parts=len(native["parts"]),
                    actual_record_counts_by_batch=counts, mapper_resources=native)
                report["runs"].append(result)
                perf.write_json(root / "benchmark.json", report)
                print(json.dumps({key: result[key] for key in ("repeat", "batch_bases", "wall_seconds", "peak_rss_kib", "exact_ordered_paf_equal")}), flush=True)
        for source in sources.values():
            if perf.sha256(source["source"]) != source["sha256"]:
                raise ValueError("original source content changed")
        if perf.sha256(__file__) != report["harness_sha256"] or perf.sha256(perf.__file__) != report["runner_sha256"]:
            raise ValueError("benchmark harness changed during execution")
        report["summary"] = [{"batch_bases": size,
            "median_wall_seconds": statistics.median(r["wall_seconds"] for r in report["runs"] if r["batch_bases"] == size),
            "maximum_peak_rss_kib": max(r["peak_rss_kib"] for r in report["runs"] if r["batch_bases"] == size)} for size in args.batch_bases]
        report.update(status="completed_same_inputs_exact_PAF_comparison", index_sha256=index_sha,
                      sensitivity_flags_changed=False, input_content_unchanged=True,
                      index_partitioning_changed_between_runs=False, production_runtime_modified=False)
    except BaseException as error:
        report.update(status="failed_no_recommendation", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        perf.write_json(root / "benchmark.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "query", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=64)
    parser.add_argument("--batch-bases", type=int, nargs="+", default=[500_000_000, 1_000_000_000, 2_000_000_000])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--memory-mib", type=int, default=196608)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not (1 <= args.threads <= 64 and 1 <= args.repeats <= 10 and 0 < args.timeout <= 7200
            and 256 <= args.memory_mib <= 262144 and len(set(args.batch_bases)) == len(args.batch_bases)
            and len(args.batch_bases) >= 2 and all(0 < size <= 5_000_000_000 for size in args.batch_bases)):
        parser.error("bounded resources and at least two distinct positive K values required")
    if not args.execute:
        result = {"execute": False, "files_created": False, "mapper_started": False,
                  "plan": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}}
    else:
        result = execute(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
