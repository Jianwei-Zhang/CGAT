#!/usr/bin/env python3
"""Maintainer-only ordinary-query batch audit and opt-in real-minimap2 comparison.

Never edits Server runtime, input FASTA or failed-task caches. Analysis is read-only
unless --output is given. Benchmark is PLAN ONLY unless --execute is explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import resource
import shutil
import signal
import statistics
import subprocess
import time

VERSION = "2.31-r1302"
DEFAULT_K = 500_000_000
PART = re.compile(r"loaded/built the index for ([0-9]+) target sequence\(s\)")
BATCH = re.compile(r"\[M::worker_pipeline::([0-9.]+)\*([0-9.]+)\] mapped ([0-9]+) sequences")
FINAL = re.compile(r"Real time: ([0-9.]+) sec; CPU: ([0-9.]+) sec; Peak RSS: ([0-9.]+) GB")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def partition(records, batch_bases):
    """Mirror single-record FASTA minibatch boundaries, not paired-read grouping."""
    if type(batch_bases) is not int or batch_bases < 1:
        raise ValueError("positive integer minibatch required")
    result, batch, bases = [], [], 0
    for record in records:
        if type(record.get("length")) is not int or record["length"] < 1:
            raise ValueError("positive record lengths required")
        batch.append(record)
        bases += record["length"]
        if bases >= batch_bases:
            result.append(batch)
            batch, bases = [], 0
    if batch:
        result.append(batch)
    return result


def parse_log(text):
    parts, current = [], None
    for line in text.splitlines():
        match = PART.search(line)
        if match:
            current = {"target_records": int(match[1]), "batches": []}
            parts.append(current)
        match = BATCH.search(line)
        if match:
            if current is None:
                raise ValueError("batch appeared before index-part load")
            current["batches"].append({"at_seconds": float(match[1]),
                "cumulative_cpu_ratio_rounded": float(match[2]), "records": int(match[3])})
    finals = FINAL.findall(text)
    if len(finals) != 1 or not parts:
        raise ValueError("one complete native mapper run is required")
    wall, cpu, rss = map(float, finals[0])
    if wall <= 0 or cpu < 0 or rss < 0:
        raise ValueError("invalid native resource summary")
    return {"wall_seconds": wall, "cpu_seconds": cpu, "peak_rss_gb": rss,
            "average_cpu_core_equivalents": cpu / wall, "parts": parts}


def analyze(catalog, plan, native_log, threads, candidates):
    if type(threads) is not int or threads < 1:
        raise ValueError("positive thread count required")
    selected = plan["native_queries"]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("unique, nonempty native query list required")
    selected_set = set(selected)
    records = [r for r in catalog["records"] if r["name"] in selected_set]
    if [r["name"] for r in records] != selected:
        raise ValueError("native records missing, duplicated or reordered")
    native = parse_log(native_log)
    baseline = partition(records, DEFAULT_K)
    expected = [len(b) for b in baseline]
    if any([b["records"] for b in p["batches"]] != expected for p in native["parts"]):
        raise ValueError("observed native batches do not match default 500M record boundaries")
    predictions = []
    for size in candidates:
        batches = partition(records, size)
        counts = [len(b) for b in batches]
        predictions.append({"batch_bases": size, "record_counts": counts,
            "nonfinal_batch_record_minimum": min(counts[:-1] or counts),
            "largest_query_fraction_by_batch": [max(r["length"] for r in b) / sum(r["length"] for r in b) for b in batches],
            "performance_measured": False, "output_equivalence_validated": False,
            "memory_required_not_estimated": True})
    return {"scope": "ordinary_queries_only_no_long_recovery_or_runtime_change",
            "status": "observed_batch_boundaries_verified_not_a_speedup_measurement",
            "ordinary_records": len(records), "ordinary_bases": sum(r["length"] for r in records),
            "largest_ordinary_record": max(r["length"] for r in records), "requested_threads": threads,
            "average_cpu_fraction_of_requested_threads": native["average_cpu_core_equivalents"] / threads,
            "allocated_cpus_or_quota_not_proven_by_t_flag": True, "observed": native,
            "candidate_batch_predictions": predictions,
            "cautions": ["A larger K can increase concurrent expensive queries and exceed available RAM.",
                         "Fewer batches cannot establish a runtime speedup or PAF equivalence.",
                         "Single-query tails, I/O waits and scheduler CPU restrictions remain possible."]}


def generate(root, records, query_bases):
    """Bounded deterministic mixed controls: both strands, indels, repeats and N-only."""
    rng = random.Random(2311302)
    sequence = rng.randbytes(query_bases + query_bases // 2).translate(bytes.maketrans(bytes(range(256)), b"ACGT" * 64))
    target, query = root / "target.fa", root / "queries.fa"
    split = len(sequence) // 2
    target.write_bytes(b">chr1\n" + sequence + b"\n>chr2\n" + sequence[:split] + sequence[split:].translate(bytes.maketrans(b"ACGT", b"TGCA")) + b"\n")
    with query.open("xb") as stream:
        for i in range(records):
            start = (i * 7919) % (len(sequence) - query_bases + 1)
            body = bytearray(sequence[start:start + query_bases])
            for offset in range(101 + i % 100, len(body), 997):
                body[offset] = b"ACGT"[(b"ACGT".index(body[offset]) + 1) % 4]
            if i % 5 == 0:
                body = body[:query_bases // 2] + b"ACGTACG" + body[query_bases // 2 + 3:]
            if i % 3 == 0:
                body = body.translate(bytes.maketrans(b"ACGT", b"TGCA"))[::-1]
            if i % 17 == 16:
                body = b"N" * len(body)
            stream.write(f">q{i:06d} comment preserved\n".encode() + body + b"\n")
    return target, query


def run(command, directory, stem, timeout, memory_mib):
    if not Path("/usr/bin/time").is_file():
        raise ValueError("GNU /usr/bin/time required for independent per-child resource measurement")
    stats, stdout, stderr = [directory / (stem + suffix) for suffix in (".resources", ".stdout", ".stderr")]
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024**2,) * 2)
    wrapped = ["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(stats), *command]
    started = time.monotonic()
    with stdout.open("xb") as out, stderr.open("xb") as err:
        child = subprocess.Popen(wrapped, stdout=out, stderr=err, start_new_session=True,
                                 preexec_fn=limits, env={**os.environ, "LC_ALL": "C"})
        try:
            code = child.wait(timeout=timeout)
        except BaseException:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise
    result = {"command": command, "returncode": code, "observed_wall_seconds": time.monotonic() - started}
    write_json(directory / (stem + ".execution.json"), result)
    if code:
        raise ValueError("benchmark child failed; no retry; inspect " + str(stderr))
    fields = stats.read_text().split()
    if len(fields) != 4:
        raise ValueError("invalid GNU time resource summary")
    wall, user, system, rss = map(float, fields)
    result.update(wall_seconds=wall, cpu_seconds=user + system, peak_rss_kib=int(rss))
    return result


def benchmark(args):
    executable = shutil.which(args.minimap2)
    if not executable:
        raise ValueError("explicit minimap2 executable unavailable")
    executable = str(Path(executable).resolve())
    if subprocess.check_output([executable, "--version"], text=True, timeout=10).strip() != VERSION:
        raise ValueError("requires pinned minimap2 " + VERSION)
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "production_runtime_modified": False, "customer_original_data": False,
              "mapper_version": VERSION, "mapper_sha256": sha256(executable), "threads": args.threads,
              "harness_sha256": sha256(__file__), "host_visible_cpus": os.cpu_count(),
              "process_cpu_affinity": sorted(os.sched_getaffinity(0)),
              "index_flags_changed_between_comparisons": False, "sensitivity_flags_changed": False,
              "mini_batch_bases": args.batch_bases, "runs": []}
    write_json(root / "benchmark.json", report)
    try:
        target, query = generate(root, args.records, args.query_bases)
        report["inputs"] = {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in (target, query)}
        for index_kind in ("single", "multipart"):
            directory = root / index_kind
            directory.mkdir()
            index = directory / "target.mmi"
            # A small forced partition is TEST ONLY. All comparison runs use identical MMI bytes.
            flags = ["-I", str(args.query_bases)] if index_kind == "multipart" else []
            report[index_kind + "_index"] = run([executable, "-x", "asm10", *flags, "-t", str(args.threads),
                "-d", str(index), str(target)], directory, "index", args.timeout, args.memory_mib)
            index_sha = sha256(index)
            baseline = None
            for repeat in range(args.repeats):
                sizes = args.batch_bases if repeat % 2 == 0 else list(reversed(args.batch_bases))
                for size in sizes:
                    stem = f"r{repeat:02d}-K{size}"
                    paf = directory / (stem + ".paf")
                    result = run([executable, "-c", "-x", "asm10", "-t", str(args.threads), "-K", str(size),
                                  "-o", str(paf), str(index), str(query)], directory, stem, args.timeout, args.memory_mib)
                    if not paf.is_file() or paf.stat().st_size == 0:
                        raise ValueError("empty benchmark PAF cannot establish output equivalence")
                    digest = sha256(paf)
                    if baseline is None:
                        baseline = digest
                    if digest != baseline:
                        raise ValueError("PAF changed with minibatch size; refuse performance recommendation")
                    if sha256(index) != index_sha:
                        raise ValueError("MMI changed during benchmark")
                    actual_parts = len(PART.findall((directory / (stem + ".stderr")).read_text()))
                    if actual_parts != (1 if index_kind == "single" else 2):
                        raise ValueError("actual index partition count does not match benchmark label")
                    result.update(actual_index_parts=actual_parts, index_kind=index_kind, repeat=repeat, batch_bases=size,
                                  paf_sha256=digest, paf_bytes=paf.stat().st_size, exact_ordered_paf_equal=True)
                    report["runs"].append(result)
                    write_json(root / "benchmark.json", report)
                    print(json.dumps({k: result[k] for k in ("index_kind", "repeat", "batch_bases", "wall_seconds", "peak_rss_kib", "exact_ordered_paf_equal")}), flush=True)
        for name, before in report["inputs"].items():
            if sha256(root / name) != before["sha256"]:
                raise ValueError("benchmark inputs changed")
        if sha256(__file__) != report["harness_sha256"]:
            raise ValueError("benchmark harness changed during execution")
        report["summary"] = []
        for kind in ("single", "multipart"):
            for size in args.batch_bases:
                runs = [r for r in report["runs"] if r["index_kind"] == kind and r["batch_bases"] == size]
                report["summary"].append({"index_kind": kind, "batch_bases": size,
                    "median_wall_seconds": statistics.median(r["wall_seconds"] for r in runs),
                    "maximum_peak_rss_kib": max(r["peak_rss_kib"] for r in runs)})
        report["status"] = "synthetic_control_completed_not_customer_performance_acceptance"
    except BaseException as error:
        report.update(status="failed_no_recommendation", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(root / "benchmark.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    audit = sub.add_parser("analyze")
    audit.add_argument("--catalog", type=Path, required=True)
    audit.add_argument("--plan", type=Path, required=True)
    audit.add_argument("--native-log", type=Path, required=True)
    audit.add_argument("--threads", type=int, required=True)
    audit.add_argument("--batch-bases", type=int, nargs="+", default=[DEFAULT_K, 1_000_000_000, 2_000_000_000, 5_000_000_000])
    audit.add_argument("--output", type=Path)
    compare = sub.add_parser("benchmark")
    compare.add_argument("--out", type=Path, required=True)
    compare.add_argument("--minimap2", default="minimap2")
    compare.add_argument("--threads", type=int, default=8)
    compare.add_argument("--records", type=int, default=64)
    compare.add_argument("--query-bases", type=int, default=1_000_000)
    compare.add_argument("--batch-bases", type=int, nargs="+", default=[2_000_000, 8_000_000, 32_000_000])
    compare.add_argument("--repeats", type=int, default=3)
    compare.add_argument("--timeout", type=int, default=600)
    compare.add_argument("--memory-mib", type=int, default=6144)
    compare.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "analyze":
        result = analyze(json.loads(args.catalog.read_text()), json.loads(args.plan.read_text()),
                         args.native_log.read_text(), args.threads, args.batch_bases)
        if args.output:
            with args.output.open("x") as stream:
                stream.write(json.dumps(result, indent=2) + "\n")
    else:
        if not (1 <= args.threads <= 64 and 2 <= args.records <= 1024 and 1000 <= args.query_bases <= 100_000_000
                and 1 <= args.repeats <= 10 and args.timeout > 0 and 256 <= args.memory_mib <= 65536
                and all(0 < k <= 5_000_000_000 for k in args.batch_bases)
                and args.records * args.query_bases <= 4 * 1024**3
                and len(args.batch_bases) >= 2 and len(set(args.batch_bases)) == len(args.batch_bases)):
            parser.error("bounded positive benchmark resources and at least two distinct K values required")
        if not args.execute:
            result = {"execute": False, "files_created": False, "mapper_started": False,
                      "plan": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
        else:
            result = benchmark(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
