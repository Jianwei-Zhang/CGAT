#!/usr/bin/env python3
"""Real-window hotspot for production whole-record self batching."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_assign_functions(tools: Path):
    source = (tools / "assign_chr_groups.py").read_text(encoding="utf-8")
    prefix, marker, _rest = source.partition(
        '\nwork_root = Path(os.environ["GPM_FAST_WORK_ROOT"])'
    )
    if not marker:
        raise RuntimeError("cannot isolate assignment compiler functions")
    namespace = {}
    sys.path.insert(0, str(tools))
    exec(compile(prefix, "assign_chr_groups.py", "exec"), namespace)
    namespace["SELF_BATCH_BASES"] = 250_000
    namespace["threads"] = "4"
    return namespace


def selected_records(path: Path, names: list[str], width: int) -> list[tuple[str, bytes]]:
    wanted = set(names)
    result = []
    current = None
    sequence = []
    def flush():
        if current in wanted:
            value = b"".join(sequence)
            start = max(0, (len(value) - width) // 2)
            if len(value[start:start + width]) != width:
                raise ValueError(f"query is shorter than hotspot window: {current}")
            result.append((current, value[start:start + width]))
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b">"):
                flush()
                current = line[1:].split()[0].decode()
                sequence = []
            else:
                sequence.append(line.strip())
    flush()
    if [name for name, _sequence in result] != names:
        raise ValueError("requested query aliases are unavailable or reordered")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tools", required=True, type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=False)
    functions = load_assign_functions(args.tools)
    run_dir = args.root / "operation"
    run_dir.mkdir()
    target = args.source / "self_target.fa"
    query = run_dir / "self_query.fa"
    names = ["gpm_pair_000000019b", "gpm_pair_000000020b"]
    records = selected_records(args.source / "self_query.fa", names, 250_000)
    with query.open("wb") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n".encode())
            for offset in range(0, len(sequence), 80):
                handle.write(sequence[offset:offset + 80] + b"\n")
    name_map = run_dir / "self_name_map.tsv"
    restore = run_dir / "restore_self_paf.py"
    name_map.write_bytes((args.source / "self_name_map.tsv").read_bytes())
    restore.write_bytes((args.source / "restore_self_paf.py").read_bytes())
    master, tasks = functions["write_self_batch_scripts"](
        run_dir, target, query, name_map, restore,
        args.tools / "self_alignment_batches.py",
        threads="4", minimap_preset="asm10",
        self_min_chain_score=200, self_minimizers=100,
    )
    if len(tasks) != 2:
        raise ValueError(f"expected two hotspot batches, got {len(tasks)}")
    report = {
        "status": "RUNNING",
        "boundary": "Two 250kb windows from distinct real chr03 flye query records, complete original target, same ARM binary/flags. Forced one whole record per batch only to keep the hotspot bounded; no contig splitting or biological acceptance claim.",
        "inputs": {"target_sha256": sha256(target), "query_sha256": sha256(query)},
        "stages": [],
    }
    (args.root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    environment = {**os.environ, "GPM_TASK_THREADS": "2"}
    started = time.monotonic()
    subprocess.run(["bash", str(master)], check=True, env=environment)
    report["stages"].append({"name": "cold", "seconds": time.monotonic() - started})

    minimap2 = str(Path(subprocess.check_output(["bash", "-lc", "command -v minimap2"], text=True).strip()))
    baseline_raw = run_dir / "baseline.raw.paf"
    started = time.monotonic()
    with baseline_raw.open("wb") as output:
        subprocess.run(
            [minimap2, "-c", "-x", "asm10", "-X", "--no-hash-name",
             "-m", "200", "-n", "100", "-t", "2", str(target), str(query)],
            check=True, stdout=output, stderr=subprocess.DEVNULL,
        )
    baseline = subprocess.run(
        [sys.executable, str(restore), str(name_map)], check=True,
        input=baseline_raw.read_bytes(), capture_output=True,
    ).stdout
    report["stages"].append({"name": "baseline", "seconds": time.monotonic() - started})
    output = run_dir / "result.paf"
    report["ordered_equal"] = output.read_bytes() == baseline
    report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()
    report["batched_sha256"] = sha256(output)

    started = time.monotonic()
    cache_logs = []
    for command, *_rest in tasks:
        result = subprocess.run(["bash", str(command)], check=True, env=environment,
                                capture_output=True, text=True)
        cache_logs.append(result.stdout.strip())
    report["stages"].append({"name": "resume", "seconds": time.monotonic() - started,
                             "logs": cache_logs})
    first_dir = tasks[0][0].parent
    (first_dir / "result.paf").write_text("corrupt\n", encoding="utf-8")
    started = time.monotonic()
    repaired = subprocess.run(["bash", str(tasks[0][0])], check=True, env=environment,
                              capture_output=True, text=True)
    report["stages"].append({"name": "corrupt-one", "seconds": time.monotonic() - started,
                             "log": repaired.stdout.strip()})
    report["repaired_equal"] = output.read_bytes() == baseline
    report["status"] = "PASS" if report["ordered_equal"] and report["repaired_equal"] else "DIFFERENT"
    (args.root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
