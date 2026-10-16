#!/usr/bin/env python3
"""Isolated, real-input official-tool benchmarks; never updates a Server workspace.

Run only on a compute node with pinned nucmer 4.0.1/minimap2 2.30 on PATH.
The nucmer mode keeps the original eight selected target partitions. The refill
mode uses both real refill rounds and their exact target/query bytes. This is a
component experiment, not a repair-engine or whole-pipeline acceptance test.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import traceback


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fasta(path: Path):
    name, pieces = None, []
    with path.open() as handle:
        for line in handle:
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(pieces)
                name, pieces = line[1:].split()[0], []
            else:
                pieces.append(line.strip())
    if name is not None:
        yield name, "".join(pieces)


def save_fasta(path: Path, records) -> None:
    with path.open("w") as handle:
        for name, seq in records:
            handle.write(f">{name}\n")
            for start in range(0, len(seq), 80):
                handle.write(seq[start:start + 80] + "\n")


def run(command: list[str], directory: Path, label: str, stdout: Path | None = None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{label}.command.txt").write_text(shlex.join(command) + "\n")
    clock = directory / f"{label}.time.txt"
    started = time.monotonic()
    with (stdout or directory / f"{label}.stdout.log").open("wb") as out, (
        directory / f"{label}.stderr.log"
    ).open("wb") as err:
        subprocess.run(
            ["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(clock), *command],
            stdout=out, stderr=err, check=True, timeout=2400,
        )
    values = clock.read_text().strip().splitlines()[-1].split()
    return {"wall_seconds": time.monotonic() - started,
            "user_seconds": float(values[1]), "system_seconds": float(values[2]),
            "max_rss_kib": int(values[3])}


class Report:
    def __init__(self, output: Path, mode: str, threads: int):
        self.path = output / "report.json"
        self.data = {"status": "RUNNING", "mode": mode, "threads": threads,
                     "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     "checks": [], "measurements": [],
                     "boundary": "Official-tool component comparison, not complete repair-engine or pipeline acceptance; OS page cache is not flushed."}
        self.flush()

    def flush(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def check(self, name: str, actual, expected):
        passed = actual == expected
        row = {"name": name, "status": "PASS" if passed else "FAIL",
               "actual_sha256": digest(actual), "expected_sha256": digest(expected)}
        if hasattr(actual, "__len__"):
            row.update(actual_count=len(actual), expected_count=len(expected))
        if not passed:
            (self.path.parent / f"failure-{len(self.data[checks]):03d}.json").write_text(
                json.dumps({"name": name, "actual": actual, "expected": expected}, indent=2) + "\n")
        self.data["checks"].append(row)
        self.flush()
        print(json.dumps(row), flush=True)

    def measurement(self, row):
        self.data["measurements"].append(row)
        self.flush()
        print("MEASUREMENT " + json.dumps(row, sort_keys=True), flush=True)


def numeric_coords(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if fields and fields[0].isdigit():
            rows.append([item for item in fields if item != "|"])
    return rows


def group(rows, column):
    result = {}
    for row in rows:
        result.setdefault(row[column], []).append(row)
    return result


def nucmer_test(args, report):
    cold = args.base / "cold-component-a6e85bd6"
    old = cold / "round-1-baseline"
    selection = json.loads((cold / "selection.json").read_text())
    wanted = {row[2]: row for row in selection["partitions"]}
    data = args.output / "inputs"
    data.mkdir()
    targets = []
    for name, sequence in fasta(old / "data/targets.fa"):
        original = wanted[name]
        path = data / f"partition-{original[1]:04d}.fa"
        save_fasta(path, [(name, sequence)])
        report.check(f"target bytes original-partition-{original[1]}", sha(path), original[3])
        targets.append((original[1], name, path, len(sequence)))
    targets.sort()
    assert len(targets) == 8
    queries = []
    golden = {}
    for source in sorted((old / "artifact/mummer/by_chr").glob("*/query.fa")):
        records = list(fasta(source))
        assert len(records) == 1
        name = records[0][0]
        path = data / f"{name}.fa"
        os.link(source, path)
        queries.append((name, path))
        golden[name] = numeric_coords(source.parent / "result.coords")
    assert len(queries) == 2
    combined = data / "queries.fa"
    with combined.open("wb") as handle:
        for _name, path in queries:
            handle.write(path.read_bytes())
    empty = data / "empty-query.fa"
    empty.write_bytes(b"")
    report.data["inputs"] = {"selection": selection,
        "targets": [{"original_partition": idx, "name": name, "bp": bp,
                     "sha256": sha(path)} for idx, name, path, bp in targets],
        "queries": [{"name": name, "sha256": sha(path)} for name, path in queries]}
    tools = {name: shutil.which(name) for name in ("nucmer", "delta-filter", "show-coords")}
    assert all(tools.values())
    report.data["nucmer_version"] = subprocess.check_output([tools["nucmer"], "--version"], text=True).strip()
    report.data["tools"] = {name: {"path": path, "sha256": sha(Path(path))}
                            for name, path in tools.items()}
    report.flush()

    # Build-only: a real readable empty query file preserves CLI arity, but
    # contributes no matching work. Every saved-index file is retained/hashed.
    def build(target):
        idx, _name, path, _bp = target
        directory = args.output / "suffix-index" / f"part-{idx:04d}"
        prefix = directory / "reference"
        timing = run([tools["nucmer"], "-c", "1000", "-l", "100", "-t", "1",
                      "--save", str(prefix), "-p", str(directory / "build"),
                      str(path), str(empty)], directory, "build")
        files = sorted(directory.glob("reference*"))
        assert files, "nucmer did not publish an index"
        manifest = {item.name: {"bytes": item.stat().st_size, "sha256": sha(item)} for item in files}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return {"partition": idx, "timing": timing, "files": manifest}

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        builds = list(pool.map(build, targets))
    build_wall = time.monotonic() - started
    report.measurement({"profile": "suffix_index_build_only", "seconds": build_wall,
                        "partitions": builds})
    baseline = None
    profiles = ("baseline", "no_batch", "suffix_load", "query_batch", "suffix_load_query_batch")
    for profile in profiles:
        batched = "query_batch" in profile
        inner_threads = min(len(queries), args.threads) if batched else 1
        workers = max(1, args.threads // inner_threads)
        jobs = [(target, None if batched else query) for target in targets
                for query in ([None] if batched else queries)]

        def align(job):
            target, query = job
            idx, _name, target_path, _bp = target
            query_name, query_path = ("all", combined) if batched else query
            directory = args.output / profile / f"part-{idx:04d}" / query_name
            command = [tools["nucmer"], "-c", "1000", "-l", "100", "-t", str(inner_threads)]
            if "suffix_load" in profile:
                command += ["--load", str(args.output / "suffix-index" / f"part-{idx:04d}" / "reference")]
            elif profile != "no_batch":
                command += ["--batch=500000000"]
            command += ["-p", str(directory / "result"), str(target_path), str(query_path)]
            timings = {"nucmer": run(command, directory, "nucmer")}
            delta = directory / "result.delta"
            # MUMmer 4.0.1 delta-filter rejects an otherwise valid header-only
            # zero-hit delta. Preserve production handling instead of masking errors.
            if not any(line.startswith(">") for line in delta.read_text().splitlines()):
                (directory / "result.coords").write_text("")
                (directory / "zero-hit.txt").write_text("header-only delta; filtering skipped\n")
            else:
                filtered = directory / "filtered.delta"
                timings["delta-filter"] = run([tools["delta-filter"], "-l", "10000", str(delta)],
                                               directory, "delta-filter", filtered)
                timings["show-coords"] = run([tools["show-coords"], "-r", "-l", str(filtered)],
                                              directory, "show-coords", directory / "result.coords")
            return idx, group(numeric_coords(directory / "result.coords"), -1), timings

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(align, jobs))
        seconds = time.monotonic() - started
        by_query = {name: [] for name, _path in queries}
        for _idx, groups, _timings in sorted(results, key=lambda row: row[0]):
            assert not set(groups) - set(by_query), f"unexpected query names: {set(groups) - set(by_query)}"
            for name, rows in groups.items():
                by_query[name].extend(rows)
        if baseline is None:
            baseline = by_query
            # Cold golden artifacts aggregate in selected target order, which is
            # the same sequence order as inputs/data/targets.fa, not original ID.
            # Compare per-target ordered rows, restoring original partition order.
            wanted_names = {target[1] for target in targets}
            for name, rows in by_query.items():
                gold = group(golden[name], -2)
                restored = [row for _idx, target_name, _path, _bp in targets
                            for row in gold.get(target_name, [])]
                assert set(gold) <= wanted_names
                report.check(f"baseline cold golden ordered coords {name}", rows, restored)
        for name, rows in by_query.items():
            report.check(f"{profile} exact ordered coords {name}", rows, baseline[name])
            report.check(f"{profile} unordered coords {name}", sorted(rows), sorted(baseline[name]))
        report.measurement({"profile": profile, "seconds": seconds, "jobs": len(jobs),
            "workers": workers, "threads_per_job": inner_threads,
            "cold_including_index_build_seconds": seconds + build_wall if "suffix_load" in profile else seconds,
            "warm_index_reuse_seconds": seconds if "suffix_load" in profile else None,
            "rows": {name: len(rows) for name, rows in by_query.items()},
            "tools": [{"partition": idx, "timings": timings} for idx, _rows, timings in results]})


def paf(path: Path):
    return [line.split("\t") for line in path.read_text().splitlines() if line]


def refill_test(args, report):
    workspace = args.base / "customer-core-080599a3/baseline"
    refill = workspace / "grt/evidence/step3/refill"
    tool = shutil.which("minimap2")
    assert tool
    report.data["tools"] = {"minimap2": {"path": tool, "sha256": sha(Path(tool)),
                                               "version": subprocess.check_output([tool, "--version"], text=True).strip()}}
    for number, round_name in enumerate(("round1", "round2")):
        inputs = args.output / round_name / "inputs"
        inputs.mkdir(parents=True)
        sources = sorted((refill / round_name / "by_chr").glob("*/flanks.fa"))
        assert len(sources) == 8
        query_paths, query_names, original = {}, {}, {}
        target = None
        for source in sources:
            key = source.parent.name
            command = shlex.split((source.parent / "command.txt").read_text())
            assert command[1:3] == ["-x", "asm5"] and "-c" in command
            this_target = workspace / "grt/donors" / Path(command[-2]).name
            assert this_target.is_file()
            assert target is None or this_target == target, "different targets inside one round"
            target = this_target
            query_path = inputs / f"{key}.fa"
            os.link(source, query_path)
            query_paths[key] = query_path
            query_names[key] = [name for name, _seq in fasta(source)]
            original[key] = paf(source.parent / "result.paf")
        all_names = [name for key in query_names for name in query_names[key]]
        assert len(all_names) == len(set(all_names)), "query IDs are not globally unique"
        combined = inputs / "all-flanks.fa"
        with combined.open("wb") as handle:
            for path in query_paths.values():
                handle.write(path.read_bytes())
        target_sha = sha(target)
        with (workspace / "metadata/grt_donor_sets.tsv").open() as handle:
            donor = next(row for row in csv.DictReader(handle, delimiter="\t")
                         if Path(row["fasta_relpath"]).name == target.name)
        report.check(f"{round_name} exact donor target", target_sha, donor["fasta_sha256"])
        report.data.setdefault("inputs", {})[round_name] = {
            "target": str(target), "target_sha256": target_sha,
            "query_sha256": {key: sha(path) for key, path in query_paths.items()},
            "query_records": {key: len(names) for key, names in query_names.items()}}
        index = args.output / round_name / "target.mmi"
        build_timing = run([tool, "-x", "asm5", "-t", str(args.threads), "-d", str(index), str(target)],
                           index.parent / "index-build", "minimap2")
        report.measurement({"round": round_name, "profile": "mmi_index_build_only",
                            "seconds": build_timing["wall_seconds"], "timing": build_timing,
                            "index_bytes": index.stat().st_size, "index_sha256": sha(index)})
        baseline = None
        # Reverse candidate order in round2; keep a fresh baseline first so exact
        # comparisons remain independent of the prior round and original evidence.
        candidates = ("indexed", "batch", "indexed_batch")
        if number:
            candidates = tuple(reversed(candidates))
        for profile in ("baseline", *candidates):
            indexed, batched = "indexed" in profile, "batch" in profile
            mapping_target = index if indexed else target
            tasks = [("all", combined)] if batched else list(query_paths.items())
            started = time.monotonic()
            rows_by_key, timings = {}, []
            for key, query in tasks:
                directory = args.output / round_name / profile / key
                output = directory / "result.paf"
                timing = run([tool, "-x", "asm5", "-t", str(args.threads), "-c", "-o", str(output),
                              str(mapping_target), str(query)], directory, "minimap2")
                timings.append({"key": key, **timing})
                rows_by_key[key] = paf(output)
            seconds = time.monotonic() - started
            if batched:
                grouped = group(rows_by_key["all"], 0)
                assert not set(grouped) - set(all_names), "unexpected query IDs"
                rows_by_key = {key: [row for name in names for row in grouped.get(name, [])]
                               for key, names in query_names.items()}
                for key, rows in rows_by_key.items():
                    split = args.output / round_name / profile / "restored" / f"{key}.paf"
                    split.parent.mkdir(parents=True, exist_ok=True)
                    split.write_text("".join("\t".join(row) + "\n" for row in rows))
            if baseline is None:
                baseline = rows_by_key
                for key, rows in baseline.items():
                    report.check(f"{round_name} baseline exact original PAF {key}", rows, original[key])
            for key, rows in rows_by_key.items():
                report.check(f"{round_name} {profile} exact full PAF {key}", rows, baseline[key])
            report.measurement({"round": round_name, "profile": profile, "seconds": seconds,
                "cold_including_index_build_seconds": seconds + build_timing["wall_seconds"] if indexed else seconds,
                "warm_index_reuse_seconds": seconds if indexed else None,
                "calls": len(tasks), "rows": {key: len(rows) for key, rows in rows_by_key.items()},
                "timings": timings})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("nucmer", "refill"))
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    args.base, args.output = args.base.resolve(), args.output.resolve()
    assert 1 <= args.threads <= 32
    args.output.mkdir(parents=True, exist_ok=False)
    report = Report(args.output, args.mode, args.threads)
    try:
        (nucmer_test if args.mode == "nucmer" else refill_test)(args, report)
        report.data["status"] = "PASS" if all(row["status"] == "PASS" for row in report.data["checks"]) else "FAIL"
    except Exception:
        report.data["status"] = "ERROR"
        report.data["exception"] = traceback.format_exc()
        raise
    finally:
        report.data["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report.flush()
    if report.data["status"] != "PASS":
        raise SystemExit("Component equivalence failed; retain artifacts and do not adopt.")


if __name__ == "__main__":
    main()
