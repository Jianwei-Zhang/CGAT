"""Compare two single-node mapper thread splits on archived, complete wheat windows.

Both arms run the frozen coarse and CIGAR commands with the same guard, target
inventory, and analytical flags. Only -t and concurrent slots change. No DNA
reconstruction, production work or receipts are written. This is native-only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from benchmark_regional_mapper_dispatch import digest, read_json, within

GIB = 1024**3
GUARD_SHA = "b87e4a3f604127319789cc27503fa145acc4a1397549ae5b821eb94ba3002780"
SUMMARY_SHA = "8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901"
TOOL_SHA = "cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3"
BASE = ["-D", "-P", "--dual=yes", "--no-long-join"]


@dataclass(frozen=True)
class Stage:
    kind: str
    argv: tuple
    expected_sha256: str


@dataclass(frozen=True)
class Case:
    receipt: str
    historical_seconds: float
    stages: tuple


def stamp(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def remember(path, expected, signatures):
    before = stamp(path)
    if before[2] != expected["size"] or digest(path) != expected["sha256"] or stamp(path) != before:
        raise ValueError("archived bytes or file identity differ: " + str(path))
    signatures[path] = before


def scope_rows(summary, workspace, count):
    # Stratify by historical raw time among completed, guarded, two-stage jobs;
    # choose before seeing any new result. Both arms get the same order.
    rows = [r for r in summary["cases"] if (within(workspace, r["raw_receipt"]).parent.parent
                                             / "chaining/success.json").is_file()]
    rows.sort(key=lambda r: (r["historical_real_seconds"], r["raw_receipt"]))
    if len(rows) < count or len({r["raw_receipt"] for r in rows}) != len(rows):
        raise ValueError("not enough distinct complete two-stage controls")
    return [rows[(2*i+1)*len(rows)//(2*count)] for i in range(count)]


def checked_argv(command, tool, preset, flags, original_files, archived_files, mapper_threads):
    expected = [tool, "-x", preset, *flags, "-t", "2", *map(str, original_files)]
    if (preset != "asm10" or flags not in (BASE, ["-c", *BASE], ["-c", *BASE, "-m", "2000"])
            or command["argv"] != expected or command["address_space_bytes"] != 4*GIB
            or command["guard_sha256"] != GUARD_SHA or command["wall_clock_limit_added"] is not False
            or mapper_threads not in (1, 2)):
        raise ValueError("not the calibrated guarded regional command")
    return (*expected[:-3], str(mapper_threads), *map(str, archived_files))


def load_cases(work, archive, count):
    summary_path = within(archive, "summary.json")
    if digest(summary_path) != SUMMARY_SHA:
        raise ValueError("unexpected native archive")
    summary = read_json(summary_path, maximum=2*1024**2)
    if summary["status"] != "native_mapper_dispatch_abba_equal_original_stdout":
        raise ValueError("archive has no complete control")
    signatures, cases, source_bytes = {}, [], 0
    for row in scope_rows(summary, work, count):
        rel = row["raw_receipt"]
        raw_path = within(work, rel)
        if not re.fullmatch(r"grt/evidence/q0_prepare/regional/q0-regional-context-[0-9a-f]{24}/q0-regional-raw-[0-9a-f]{24}/success.json", rel):
            raise ValueError("not a complete original regional window")
        remember(raw_path, {"size": raw_path.stat().st_size, "sha256": row["receipt_sha256"]}, signatures)
        raw = read_json(raw_path, maximum=2*1024**2)
        identity = raw["spec"]["context"]
        context_path = within(work, identity["path"])
        if context_path != raw_path.parent.parent / "context.json":
            raise ValueError("regional context is not bound to the receipt")
        remember(context_path, identity, signatures)
        context = read_json(context_path, maximum=2*1024**2)
        spec = context["spec"]
        tool = spec["tool"]["resolved"]
        tool_path = Path(tool).resolve(strict=True)
        if str(tool_path) != tool or spec["tool"]["sha256"] != TOOL_SHA:
            raise ValueError("unexpected mapper version/path")
        if tool_path not in signatures:
            remember(tool_path, {"size": tool_path.stat().st_size, "sha256": TOOL_SHA}, signatures)
        input_rows = {x["path"]: x for x in context["inputs"]}
        original_files, archived_files = [], []
        for name in ("target.fa", "query.fa"):
            p = (context_path.parent / name).relative_to(work).as_posix()
            expected = input_rows[p]
            source_bytes += expected["size"]
            if expected["size"] > 110*1024**2 or source_bytes > GIB:
                raise ValueError("archived input extent exceeds bounded control")
            original_files.append(work/p)  # removable original generated FASTA may be absent
            stored = within(archive/"artifacts", p)
            remember(stored, expected, signatures)
            archived_files.append(stored)
        stages = []
        for kind, directory, rr in (
            ("chaining", context_path.parent/"chaining", None), ("precise", raw_path.parent, raw),
        ):
            directory = within(work, directory.relative_to(work))
            if rr is None:
                rr = read_json(directory/"success.json", maximum=2*1024**2)
            if (rr["status"] != "success" or rr["spec"]["context"] != identity or
                    rr["spec"]["schema"] != ("lgz_q0_regional_chaining_v1" if kind == "chaining" else "lgz_q0_regional_raw_v1")):
                raise ValueError("unexpected original stage receipt")
            expected_paths = {str((directory/n).relative_to(work)) for n in ("guard.py", "command.json", "result.paf")}
            inventory = {x["path"]:x for x in rr["outputs"]}
            if len(rr["outputs"]) != 3 or set(inventory) != expected_paths:
                raise ValueError("unexpected original mapper output inventory")
            for name in ("guard.py", "command.json", "result.paf"):
                path = within(work, (directory/name).relative_to(work))
                remember(path, inventory[str(path.relative_to(work))], signatures)
            command = read_json(directory/"command.json", maximum=2*1024**2)
            sha = inventory[str((directory/"result.paf").relative_to(work))]["sha256"]
            guard = inventory[str((directory/"guard.py").relative_to(work))]["sha256"]
            if (guard != GUARD_SHA or (kind == "chaining" and rr["spec"]["flags"] != BASE)
                    or (kind == "precise" and (sha != row["paf_sha256"] or rr["spec"]["flags"][:1] != ["-c"]))):
                raise ValueError("stage differs from complete original")
            both = tuple(checked_argv(command, tool, spec["preset"], rr["spec"]["flags"],
                                      original_files, archived_files, n) for n in (1, 2))
            stages.append(Stage(kind, both, sha))
        cases.append(Case(rel, row["historical_real_seconds"], tuple(stages)))
    return cases, signatures, source_bytes


def run_phase(out, cases, guard, mapper_threads, workers):
    out.mkdir()
    started = time.monotonic()

    def run(i, case):
        case_dir = out/str(i)
        case_dir.mkdir()
        rows = []
        for stage in case.stages:
            argv = [sys.executable, str(guard), "--address-space-bytes", str(4*GIB), "--",
                    *stage.argv[mapper_threads-1]]
            t = time.monotonic()
            with (case_dir/(stage.kind+".paf")).open("xb") as stdout, (case_dir/(stage.kind+".err")).open("xb") as stderr:
                subprocess.run(argv, cwd=case_dir, stdout=stdout, stderr=stderr, check=True)
            sha = digest(case_dir/(stage.kind+".paf"))
            if sha != stage.expected_sha256:
                raise ValueError(f"{stage.kind} {i}: full PAF differs from original")
            rows.append({"stage":stage.kind, "seconds":time.monotonic()-t, "sha256":sha})
        return i, rows

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="q0-thread-split") as pool:
        jobs = [pool.submit(run, i, case) for i,case in enumerate(cases)]
        rows = [future.result() for future in as_completed(jobs)]
    return {"threads_per_mapper":mapper_threads, "workers":workers, "seconds":time.monotonic()-started,
            "rows": sorted(rows)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "archive", "output", "package"):
        p.add_argument("--"+name, required=True, type=Path)
    args = p.parse_args()
    work, archive, out, package = (x.resolve() for x in (args.workspace, args.archive, args.output, args.package))
    if any(out == p or out.is_relative_to(p) or p.is_relative_to(out) for p in (work, archive, package)):
        raise ValueError("diagnostic artifacts must be isolated")
    guard = within(package, "lgz_core/q0_mapper_guard.py")
    if digest(guard) != GUARD_SHA:
        raise ValueError("guard differs from original")
    sys.path.insert(0, str(package))
    from lgz_core.q0_regional_execution import allocation_memory_limit
    memory = allocation_memory_limit(16)
    if memory is None or memory < 72*GIB or len(os.sched_getaffinity(0)) < 16:
        raise ValueError("requires genuine single-node 16-CPU, >=72GiB allocation")
    cases, signatures, nbytes = load_cases(work, archive, 28)
    signatures[guard] = stamp(guard)
    out.mkdir()
    print(json.dumps({"phase":"inputs_verified", "n":len(cases), "bytes":nbytes}), flush=True)
    report = []
    for i,(threads,workers) in enumerate(((2,7),(1,14),(1,14),(2,7))):
        if not all(stamp(p) == before for p,before in signatures.items()):
            raise ValueError("bound input changed between phases")
        result = run_phase(out/f"phase-{i}", cases, guard, threads, workers)
        report.append(result)
        print(json.dumps({k:v for k,v in result.items() if k != "rows"}, sort_keys=True), flush=True)
    if not all(stamp(p) == before for p,before in signatures.items()):
        raise ValueError("bound input changed during benchmarking")
    a = sum(r["seconds"] for r in report if r["threads_per_mapper"] == 2)
    b = sum(r["seconds"] for r in report if r["threads_per_mapper"] == 1)
    result = {"status":"complete_guarded_thread_split_abba", "node": socket.gethostname(), "memory":memory,
              "native_stdout_all_matches_original":True, "windows":len(cases), "input_bytes":nbytes,
              "native_only_gain":a/b, "cohort":[(c.receipt,c.historical_seconds) for c in cases],
              "phases":report, "production_modified":False}
    with (out/"report.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in {"cohort","phases"}}), flush=True)


if __name__ == "__main__":
    main()
