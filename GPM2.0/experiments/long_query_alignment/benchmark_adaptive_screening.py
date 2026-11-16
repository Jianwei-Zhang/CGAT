#!/usr/bin/env python3
"""Bounded real-data filtering pilot for internal automatic strategy selection.

No production defaults, full CGAT launch, input mutation or timeout-as-success.
Use a small set of COMPLETE ordinary query records and the FULL original target.
The paired reverse-order repeat must pass before an expanded experiment is eligible.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

import adaptive_screening as policy
import benchmark_ordinary_existing as existing
import benchmark_ordinary_filtering as filtering
import benchmark_ordinary_partitions as parts
import ordinary_batch_performance as perf


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def run_bounded(command, root, stem, seconds, memory_mib):
    """Always retain terminal evidence; kill the whole child group on timeout."""
    if seconds <= 0 or memory_mib < 64:
        raise ValueError("positive wall budget and at least 64 MiB required")
    receipt = root / (stem + ".execution.json")
    stats = root / (stem + ".resources")
    wrapped = ["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(stats), *command]
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024**2,) * 2)
    result = {"outcome": "starting", "command": command, "wall_budget_seconds": seconds,
              "address_space_limit_mib": memory_mib}
    atomic_json(receipt, result)
    started = time.monotonic()
    child = None
    interrupted = None
    try:
        with (root / (stem + ".stdout")).open("xb") as out, (root / (stem + ".stderr")).open("xb") as err:
            child = subprocess.Popen(wrapped, stdout=out, stderr=err, start_new_session=True,
                                     preexec_fn=limits, env={**os.environ, "LC_ALL": "C"})
            result["pid"] = child.pid
            atomic_json(receipt, {**result, "outcome": "running"})
            try:
                code = child.wait(timeout=seconds)
                result.update(outcome="completed" if code == 0 else "tool_failure", returncode=code)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                result["outcome"] = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "cancelled"
                if isinstance(exc, KeyboardInterrupt):
                    interrupted = exc
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                # A group leader can exit before grandchildren do.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                result["returncode"] = child.wait()
    except OSError as exc:
        result.update(outcome="launch_failure", error=str(exc))
    finally:
        result["wall_seconds"] = time.monotonic() - started
        if stats.exists():
            lines = stats.read_text().splitlines()
            fields = lines[-1].split() if lines else []
            if len(fields) == 4:
                try:
                    wall, user, system, rss = map(float, fields)
                    result.update(cpu_seconds=user + system, peak_rss_kib=int(rss), gnu_time_wall_seconds=wall)
                except ValueError:
                    pass
        atomic_json(receipt, result)
    if interrupted is not None:
        raise interrupted
    return result


def execute(args):
    if args.query.stat().st_size > 2 * args.max_query_bases + 1024**2:
        raise ValueError("query file too large for bounded pilot; select complete representative records first")
    mm = shutil.which(args.minimap2)
    if not mm or subprocess.check_output([mm, "--version"], text=True, timeout=5).strip() != perf.VERSION:
        raise ValueError("pinned minimap2 " + perf.VERSION + " required")
    sources = {"query": existing.catalog(args.query, ordinary_query=True), "reference": existing.catalog(args.target)}
    if sources["query"]["total_bases"] > args.max_query_bases:
        raise ValueError("query bases exceed pilot budget")
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    modules = (policy, existing, filtering, parts, perf)
    guarded = {"mapper": str(Path(mm).resolve()), "harness": str(Path(__file__).resolve()),
               **{m.__name__: str(Path(m.__file__).resolve()) for m in modules}}
    hashes = {k: perf.sha256(v) for k, v in guarded.items()}
    result = {"status": "running", "policy": policy.POLICY, "production_approved": False,
              "sources": sources, "runs": [], "comparisons": [], "code_sha256": hashes,
              "resources": existing.resource_snapshot(), "budget_seconds": args.total_seconds,
              "shape_gate": policy.screening_gate(sources["reference"]["total_bases"], sources["query"]["records"])}
    result["identity"] = policy.receipt_identity({k: s["sha256"] for k, s in sources.items()},
        {"threads": args.threads, "batch_bases": 1_000_000_000, "fractions": ["default", "0.005", "0.01"],
         "code_sha256": hashes, "limits": result["shape_gate"]["limits"]})
    report = root / "screening.json"
    atomic_json(report, result)
    deadline = time.monotonic() + args.total_seconds
    profiles = {}
    expected = {}
    try:
        index = root / "target.default.mmi"
        result["index"] = run_bounded([mm, "-x", "asm10", "-t", str(args.threads), "-d", str(index), sources["reference"]["source"]],
            root, "index", min(args.case_seconds, max(0.01, deadline - time.monotonic())), args.memory_mib)
        if result["index"]["outcome"] != "completed":
            result["status"] = "index_incomplete"
            return result
        result["index_sha256"] = perf.sha256(index)
        for rep, cases in enumerate((("default", "0.005", "0.01"), ("0.01", "0.005", "default"))):
            for fraction in cases:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result["status"] = "budget_exhausted"
                    break
                stem = f"r{rep}-f{fraction}"
                output = root / (stem + ".paf")
                flags = [] if fraction == "default" else ["-f", fraction]
                command = [mm, "-c", "-x", "asm10", *flags, "-K", "1G", "-t", str(args.threads),
                           "-o", str(output), str(index), sources["query"]["source"]]
                run = run_bounded(command, root, stem, min(args.case_seconds, remaining), args.memory_mib)
                run.update(fraction=fraction, repeat=rep)
                result["runs"].append(run)
                if run["outcome"] == "completed":
                    try:
                        rows = parts.validate_paf(output, sources["query"]["records"], sources["reference"]["records"], allow_empty=True)
                        parsed = perf.parse_log((root / (stem + ".stderr")).read_text())
                        counts = [len(b) for b in perf.partition(sources["query"]["records"], 1_000_000_000)]
                        if (sum(p["target_records"] for p in parsed["parts"]) != len(sources["reference"]["records"])
                                or any([b["records"] for b in p["batches"]] != counts for p in parsed["parts"])):
                            raise ValueError("incomplete query/index traversal")
                        mid = parts.thresholds(root / (stem + ".stderr"))
                        if len(mid) != len(parsed["parts"]) or len(set(mid)) != 1:
                            raise ValueError("original threshold inheritance changed")
                        digest = perf.sha256(output)
                        if fraction in expected and expected[fraction] != digest:
                            raise ValueError("same-policy repeat changed output")
                        expected[fraction] = digest
                        profiles[rep, fraction] = policy.coverage_profile(output, sources["query"]["records"])
                        run.update(mid_occ=mid[0], paf_sha256=digest, paf_rows=rows)
                    except (OSError, ValueError, KeyError) as exc:
                        run.update(outcome="audit_failure", error=str(exc))
                atomic_json(report, result)
                print(json.dumps({k: run.get(k) for k in ("repeat", "fraction", "outcome", "wall_seconds", "mid_occ")}), flush=True)
            if result["status"] == "budget_exhausted":
                break
        for rep in range(2):
            batch = {r["fraction"]: r for r in result["runs"] if r["repeat"] == rep}
            if "default" not in batch:
                continue
            for fraction in ("0.005", "0.01"):
                if fraction in batch:
                    comparison = policy.compare(batch["default"], batch[fraction], profiles.get((rep, "default")), profiles.get((rep, fraction)))
                    if batch["default"]["outcome"] == batch[fraction]["outcome"] == "completed":
                        comparison["alignment_differences"] = filtering.differences(
                            filtering.profile(root / f"r{rep}-fdefault.paf"),
                            filtering.profile(root / f"r{rep}-f{fraction}.paf"))
                    result["comparisons"].append({"repeat": rep, "fraction": fraction, **comparison})
        for key, path in guarded.items():
            if perf.sha256(path) != hashes[key]:
                raise ValueError("code/tool changed: " + key)
        for source in sources.values():
            if existing.identity(Path(source["source"])) != {k: source[k] for k in ("size", "mtime_ns", "ctime_ns", "inode")} or perf.sha256(source["source"]) != source["sha256"]:
                raise ValueError("input changed")
        if perf.sha256(index) != result["index_sha256"]:
            raise ValueError("index changed")
        eligible = []
        for fraction in ("0.005", "0.01"):
            comparisons = [c for c in result["comparisons"] if c["fraction"] == fraction]
            if len(comparisons) == 2 and all(c["eligible"] for c in comparisons):
                eligible.append(fraction)
        # Prefer the less aggressive eligible filter, not simply the fastest run.
        result.update(eligible_for_expanded_validation=eligible,
                      selected_for_next_experiment=eligible[0] if eligible else None,
                      input_content_unchanged=True)
        if result["status"] == "running":
            result["status"] = "screening_completed_not_production_acceptance"
    except BaseException as exc:
        result.update(status="failed_no_recommendation", error=f"{type(exc).__name__}: {exc}")
        result.pop("selected_for_next_experiment", None)
        raise
    finally:
        atomic_json(report, result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "query", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--minimap2", default="minimap2")
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--memory-mib", type=int, default=131072)
    p.add_argument("--case-seconds", type=int, default=600)
    p.add_argument("--total-seconds", type=int, default=2400)
    p.add_argument("--max-query-bases", type=int, default=350_000_000)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args(argv)
    if not (1 <= a.threads <= 64 and 256 <= a.memory_mib <= 524288
            and 1 <= a.case_seconds <= 1200 and a.case_seconds <= a.total_seconds <= 7200
            and 1 <= a.max_query_bases <= 350_000_000):
        p.error("bounded pilot resources/inputs required")
    if not a.execute:
        print(json.dumps({"execute": False, "cases": ["default", "0.005", "0.01"], "repeats": 2,
                          "total_mapping_and_index_budget_seconds": a.total_seconds, "production_approved": False}))
        return
    def interrupted(number, frame):
        raise KeyboardInterrupt(f"pilot cancelled by signal {number}")
    previous = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for number in previous:
            signal.signal(number, interrupted)
        execute(a)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    main()
