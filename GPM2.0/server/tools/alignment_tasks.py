"""Schedule independent alignment commands within one CPU budget."""

from __future__ import annotations

import argparse
import codecs
import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


MANIFEST = "alignment_tasks.json"


@dataclass(frozen=True)
class AlignmentTask:
    unit_id: str
    command: Path
    max_threads: int
    priority: int = 0
    max_concurrent: int | None = None


def query_threads(fasta: Path, engine: str, budget: int) -> int:
    if engine != "minimap2":
        return budget
    # Minimap2 distributes query records, not pieces of a single chromosome.
    with fasta.open("rb") as handle:
        count = sum(line.startswith(b">") for line in handle)
    return max(1, min(budget, count))


def alignment_concurrency(engine: str, blastn_task: str = "blastn") -> int | None:
    """Return a conservative leaf-process limit for multithreaded aligners."""
    if engine == "winnowmap":
        return 2
    if engine == "blastn":
        return 1 if blastn_task == "blastn" else 2
    return None


def write_manifest(
    path: Path,
    root: Path,
    tasks: list[tuple[Path, int, int]],
    max_concurrent: int | None = None,
) -> None:
    payload = {"version": 2, "tasks": [
        {
            "command": command.relative_to(root).as_posix(),
            "max_threads": cap,
            "priority": priority,
        }
        for command, cap, priority in tasks
    ]}
    if max_concurrent is not None:
        payload["max_concurrent"] = max_concurrent
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_tasks(root: Path, unit_id: str, command: str) -> list[AlignmentTask] | None:
    manifest = (root / command).parent / MANIFEST
    if not manifest.is_file():
        return None  # Older prepared workspaces retain their sequential contract.
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
        raise ValueError(f"invalid alignment task manifest: {manifest}")
    max_concurrent = payload.get("max_concurrent")
    if max_concurrent is not None and (type(max_concurrent) is not int or max_concurrent < 1):
        raise ValueError(f"invalid alignment concurrency: {manifest}")
    rows = payload.get("tasks")
    if not isinstance(rows, list):
        raise ValueError(f"invalid alignment task list: {manifest}")
    tasks = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"invalid alignment task: {manifest}")
        relative, cap = row.get("command"), row.get("max_threads")
        priority = row.get("priority", 0)
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError(f"invalid alignment task command: {manifest}")
        path = (root / relative).resolve()
        path.relative_to(root.resolve())
        if (not path.is_file() or path in seen or type(cap) is not int or cap < 1
                or type(priority) is not int or priority < 0):
            raise ValueError(f"invalid or duplicate alignment task: {manifest}")
        seen.add(path)
        tasks.append(AlignmentTask(unit_id, path, cap, priority, max_concurrent))
    return tasks


def allocate_threads(caps: list[int], budget: int) -> list[int]:
    """Fairly share available cores, returning unused capacity from small jobs."""
    allocations = [0] * min(len(caps), budget)
    while budget:
        changed = False
        for index in range(len(allocations)):
            if allocations[index] < caps[index] and budget:
                allocations[index] += 1
                budget -= 1
                changed = True
        if not changed:
            break
    return allocations


def run_tasks(tasks, budget, children, cancel_signal, on_start, on_line, on_finish, environment):
    """All callbacks run on the caller thread; each command owns a process group."""
    pending = sorted(tasks, key=lambda task: task.priority, reverse=True)
    limits = [task.max_concurrent for task in tasks if task.max_concurrent is not None]
    max_concurrent = min(limits) if limits else None
    active = {}
    selector = selectors.DefaultSelector()
    failure = 0
    failed_pid = None
    stopped_at = None

    def stop_all(sig):
        for child in list(children.values()):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass

    try:
        while pending or active:
            requested = cancel_signal()
            if requested and not failure:
                failure = 128 + requested
            if failure and stopped_at is None:
                stopped_at = time.monotonic()
                stop_all(requested or signal.SIGTERM)
            if stopped_at is not None and time.monotonic() - stopped_at > 2:
                stop_all(signal.SIGKILL)
            if not failure:
                available = budget - sum(item["threads"] for item in active.values())
                slots = len(pending)
                if max_concurrent is not None:
                    slots = max(0, max_concurrent - len(active))
                allocations = allocate_threads(
                    [task.max_threads for task in pending[:slots]], available
                )
                for threads in allocations:
                    task = pending.pop(0)
                    on_start(task, threads)
                    child = subprocess.Popen(
                        ["bash", str(task.command)], cwd=task.command.parent,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        start_new_session=True,
                        env={**environment, "GPM_REPORT_UNIT_ID": task.unit_id,
                             "GPM_TASK_THREADS": str(threads), "OMP_NUM_THREADS": str(threads),
                             "OPENBLAS_NUM_THREADS": str(threads)},
                    )
                    children[child.pid] = child
                    assert child.stdout is not None
                    os.set_blocking(child.stdout.fileno(), False)
                    item = {"task": task, "child": child, "threads": threads,
                            "decoder": codecs.getincrementaldecoder("utf-8")("replace"),
                            "buffer": "", "eof": False}
                    active[child.pid] = item
                    selector.register(child.stdout, selectors.EVENT_READ, item)
            for key, _ in selector.select(timeout=0.1):
                item = key.data
                data = os.read(key.fd, 65536)
                item["buffer"] += item["decoder"].decode(data, final=not data)
                while "\n" in item["buffer"]:
                    line, item["buffer"] = item["buffer"].split("\n", 1)
                    on_line(item["task"], line.rstrip("\r"))
                if not data:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    item["eof"] = True
                    if item["buffer"]:
                        on_line(item["task"], item["buffer"])
            for pid, item in list(active.items()):
                code = item["child"].poll()
                if code not in {None, 0} and not failure:
                    failure = 128 - code if code < 0 else code
                    failed_pid = pid
                    # A failed shell may leave a descendant holding its output
                    # pipe open. Cancel its process group before waiting for EOF.
                    stopped_at = time.monotonic()
                    stop_all(signal.SIGTERM)
                if code is None or not item["eof"]:
                    continue
                del active[pid]
                del children[pid]
                code = 128 - code if code < 0 else code
                # Finishing a valid sibling is still useful after another task fails.
                on_finish(item["task"], code, bool(failure and pid != failed_pid))
            if failure and not active:
                break
        return failure
    finally:
        stop_all(signal.SIGTERM)
        for child in list(children.values()):
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                stop_all(signal.SIGKILL)
                child.wait()
            if child.stdout is not None:
                child.stdout.close()
        children.clear()
        selector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--command", required=True, type=Path)
    parser.add_argument("--query", required=True, type=Path)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--blastn-task", default="blastn")
    parser.add_argument("--threads", required=True, type=int)
    args = parser.parse_args()
    write_manifest(
        args.command.parent / MANIFEST,
        args.root,
        [(args.command, query_threads(args.query, args.engine, args.threads), args.query.stat().st_size)],
        alignment_concurrency(args.engine, args.blastn_task),
    )


if __name__ == "__main__":
    main()
