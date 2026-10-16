#!/usr/bin/env python3
"""Bounded real-window current-vs-adaptive scheduler hotspot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
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


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fasta_record(path: Path, name: str) -> bytes:
    current = None
    chunks = []
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b">"):
                if current == name:
                    break
                current = line[1:].split()[0].decode()
                chunks = []
            elif current == name:
                chunks.append(line.strip())
    if current != name:
        raise ValueError(f"query alias is missing: {name}")
    return b"".join(chunks)


def paf_digest(path: Path) -> dict[str, object]:
    rows = 0
    total = 0
    square = 0
    modulus = 1 << 256
    ordered = hashlib.sha256()
    with path.open("rb") as handle:
        for line in handle:
            ordered.update(line)
            fields = line.rstrip(b"\n").split(b"\t")
            if len(fields) < 12 or not any(value.startswith(b"cg:Z:") for value in fields[12:]):
                raise ValueError(f"incomplete PAF: {path}")
            digest = int.from_bytes(hashlib.sha256(line.rstrip(b"\n")).digest(), "big")
            rows += 1
            total = (total + digest) % modulus
            square = (square + digest * digest) % modulus
    return {"rows": rows, "ordered_sha256": ordered.hexdigest(),
            "unordered_sum": hex(total), "unordered_square_sum": hex(square)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tools", required=True, type=Path)
    parser.add_argument("--query-name", default="gpm_pair_000000019b")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.tools))
    from alignment_tasks import AdaptiveDispatcher, AlignmentTask, run_tasks

    minimap2 = Path(shutil.which("minimap2") or "")
    if not minimap2.is_file():
        raise RuntimeError("minimap2 unavailable")
    target = args.source / "self_target.fa"
    source_query = args.source / "self_query.fa"
    sequence = fasta_record(source_query, args.query_name)
    width = 250_000
    start = max(0, (len(sequence) - width) // 2)
    window = sequence[start:start + width]
    if len(window) != width:
        raise ValueError("selected query is shorter than hotspot window")

    report = {
        "status": "RUNNING",
        "boundary": "Two heavy tasks each repeat one real 250kb window as 12 query records; 14 short one-record tasks fill the 16-task current scheduler. Complete original target, same binary/flags/node, current then adaptive. Duplicate aliases make this a scheduler fixture only, not biological acceptance.",
        "source": {"target": str(target), "target_sha256": sha256(target),
                   "query": str(source_query), "query_sha256": sha256(source_query),
                   "query_name": args.query_name, "interval": [start, start + width]},
        "tool": {"path": str(minimap2.resolve()), "sha256": sha256(minimap2)},
        "runs": {},
    }
    atomic_json(args.root / "report.json", report)
    index = args.root / "target.mmi"
    with (args.root / "index.stderr.log").open("wb") as stderr:
        subprocess.run(
            [str(minimap2), "-x", "asm10", "-I", "8G", "-t", "2", "-d", str(index), str(target)],
            check=True, stdout=subprocess.DEVNULL, stderr=stderr,
        )
    if (args.root / "index.stderr.log").read_text(errors="replace").count("distinct minimizers:") != 1:
        raise ValueError("fixture requires one target index part")

    query_root = args.root / "queries"
    query_root.mkdir()
    definitions = [("heavy-1", 12), ("heavy-2", 12)] + [
        (f"short-{index:02d}", 1) for index in range(14)
    ]
    queries = {}
    for name, records in definitions:
        path = query_root / f"{name}.fa"
        with path.open("wb") as handle:
            for _ in range(records):
                handle.write(f">{args.query_name}\n".encode())
                for offset in range(0, len(window), 80):
                    handle.write(window[offset:offset + 80] + b"\n")
        queries[name] = (path, records)

    profiles = ("current", "adaptive")
    for profile in profiles:
        directory = args.root / profile
        directory.mkdir()
        tasks = []
        for name, records in definitions:
            task_dir = directory / name
            task_dir.mkdir()
            query, _ = queries[name]
            command = [
                str(minimap2), "-c", "-x", "asm10", "-X", "--no-hash-name",
                "-m", "200", "-n", "100", "-t",
            ]
            script = task_dir / "command.sh"
            script.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\nexec "
                + shlex.join(command)
                + ' "$GPM_TASK_THREADS" '
                + shlex.join([str(index), str(query)])
                + " > result.paf 2> stderr.log\n",
                encoding="utf-8",
            )
            bases = width * records
            tasks.append(
                AlignmentTask(
                    name, script, min(16, records), bases, None,
                    bases * target.stat().st_size, 1 / records,
                )
            )
        dispatcher = AdaptiveDispatcher()
        active = {}
        rows = []
        started = time.monotonic()
        def begin(task, threads):
            active[task.command] = (threads, time.monotonic())
            print(profile, "START", task.unit_id, "threads", threads, flush=True)
        def finish(task, code, cancelled):
            threads, task_started = active.pop(task.command)
            seconds = time.monotonic() - task_started
            if code == 0:
                dispatcher.complete(task, threads, seconds)
            rows.append({"task": task.unit_id, "threads": threads, "seconds": seconds,
                         "exit": code, "cancelled": cancelled})
            print(profile, "END", task.unit_id, "seconds", seconds, flush=True)
        code = run_tasks(
            tasks, 16, {}, lambda: 15 if time.monotonic() - started > 300 else None,
            begin, lambda *_: None, finish, os.environ.copy(),
            dispatch=dispatcher if profile == "adaptive" else None,
        )
        summaries = {task.unit_id: paf_digest(task.command.parent / "result.paf") for task in tasks} if code == 0 else {}
        report["runs"][profile] = {"exit": code, "seconds": time.monotonic() - started,
                                   "tasks": rows, "paf": summaries}
        atomic_json(args.root / "report.json", report)
        if code:
            raise SystemExit(code)
    current = report["runs"]["current"]
    adaptive = report["runs"]["adaptive"]
    report["content_equal"] = all(
        all(current["paf"][name][field] == adaptive["paf"][name][field]
            for field in ("rows", "unordered_sum", "unordered_square_sum"))
        for name in current["paf"]
    )
    report["ordered_equal"] = all(
        current["paf"][name]["ordered_sha256"] == adaptive["paf"][name]["ordered_sha256"]
        for name in current["paf"]
    )
    report["speed_ratio"] = current["seconds"] / adaptive["seconds"]
    report["status"] = "PASS" if report["content_equal"] else "DIFFERENT"
    atomic_json(args.root / "report.json", report)
    print("SCHEDULE_FIXTURE", report["status"], "speed_ratio", report["speed_ratio"], flush=True)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
