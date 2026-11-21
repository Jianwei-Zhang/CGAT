"""Bounded fresh-process regional planning, sharing one run CPU/memory budget.

No fork of the multi-gigabase DNA heap, no mapper in a planning worker, and no
scientific fallback on infrastructure failure: replan exactly in the owner.
Unknown job memory retains the earlier serial-planner/four-mapper ceiling.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass
import multiprocessing
import hashlib
import json
import os
import re
import socket
from pathlib import Path
import pickle
try:
    import resource
except ImportError:  # Windows may inspect/import Server packages without POSIX guards.
    resource = None
from types import SimpleNamespace

from .q0_reference_index import ReferenceIndex, _signature
from .q0_sources import Q0EvidenceError

GIB = 1024**3
PLANNER_ADDRESS_SPACE = 8*GIB
MAPPER_ADDRESS_SPACE = 4*GIB
MAX_RESULT_BYTES = 64*1024**2
# One GiB per mapper reserves owner-side extraction/validation temporaries.
MAPPER_RESERVATION = MAPPER_ADDRESS_SPACE+GIB
# Serialized results are bounded; reserve 8x for one expanded result as well.
PLAN_RESERVATION = MAX_RESULT_BYTES*10


@dataclass(frozen=True)
class ExecutionBudget:
    planner_workers: int
    mapper_workers: int
    mapper_threads: int
    total_threads: int
    memory_limit_bytes: int | None
    parent_peak_bytes: int
    reserved_bytes: int
    reason: str

    def record(self):
        return {**asdict(self), "start_method": "spawn", "planner_address_space_bytes": PLANNER_ADDRESS_SPACE,
                "mapper_address_space_bytes": MAPPER_ADDRESS_SPACE, "result_limit_bytes": MAX_RESULT_BYTES}


def choose_budget(threads, memory_limit_bytes=None, parent_peak_bytes=0):
    """Memory is an allocation/cgroup bound, never node physical free memory."""
    if type(threads) is not int or threads < 1:
        raise Q0EvidenceError("regional thread budget must be a positive integer")
    if type(parent_peak_bytes) is not int or parent_peak_bytes < 0:
        raise Q0EvidenceError("invalid regional owner memory measurement")
    if memory_limit_bytes is not None and (type(memory_limit_bytes) is not int or memory_limit_bytes < 1):
        raise Q0EvidenceError("invalid regional allocation memory bound")
    mt = min(2, max(1, threads-1))
    conservative = max(1, min(4, (threads-1)//mt))
    # Headroom also covers the owner's index/cache growth after this sample.
    headroom = max(16*GIB, parent_peak_bytes//2)
    fixed = parent_peak_bytes+headroom
    if memory_limit_bytes is not None and threads >= 8:
        for planners in range(min(3, max(1, (threads-1)//8)), 0, -1):
            cpu_workers = (threads-1-planners)//mt
            available = memory_limit_bytes-fixed-planners*(PLANNER_ADDRESS_SPACE+2*PLAN_RESERVATION)
            workers = min(cpu_workers, available//MAPPER_RESERVATION)
            if workers >= 1:
                reserved = fixed+planners*(PLANNER_ADDRESS_SPACE+2*PLAN_RESERVATION)+workers*MAPPER_RESERVATION
                return ExecutionBudget(planners, workers, mt, threads, memory_limit_bytes,
                                       parent_peak_bytes, reserved, "verified_memory_parallel_planning")
    if memory_limit_bytes is not None:
        conservative = max(1, min(conservative, (memory_limit_bytes-fixed)//MAPPER_RESERVATION))
    return ExecutionBudget(0, conservative, mt, threads, memory_limit_bytes, parent_peak_bytes,
                           fixed+conservative*MAPPER_RESERVATION,
                           "unknown_memory_conservative" if memory_limit_bytes is None else "small_budget_conservative")


def cgroup_memory_limit(proc=Path("/proc"), cgroups=Path("/sys/fs/cgroup")):
    """Only finite limits on this process's cgroup ancestry; no /proc/meminfo.

    Nonstandard/unreadable mounts fail conservatively to serial planning. The
    scheduler-bound incident launcher may supply an independently verified
    budget to RegionalExecutor; an arbitrary environment value is not trusted.
    """
    limits = []
    try:
        for row in (proc/"self/cgroup").read_text().splitlines():
            _, controllers, relative = row.split(":", 2)
            if controllers == "":
                root, name = cgroups, "memory.max"
            elif "memory" in controllers.split(","):
                root, name = cgroups/"memory", "memory.limit_in_bytes"
            else:
                continue
            # Namespace traversal and unfamiliar cgroup layouts are not proof.
            if ".." in Path(relative).parts or not relative.startswith("/"):
                continue
            current = root/relative.lstrip("/")
            while True:
                value = (current/name).read_text().strip()
                if value.isascii() and value.isdecimal() and 0 < int(value) < 1 << 60:
                    limits.append(int(value))
                if current == root:
                    break
                current = current.parent
    except (OSError, ValueError):
        return None
    return min(limits) if limits else None


SCHEDULER_PROOF_ENV = "_GPM_Q0_SCHEDULER_PROOF"
SCHEDULER_SHA_ENV = "_GPM_Q0_SCHEDULER_SHA256"


def allocation_memory_limit(threads, *, environ=None, proc=Path("/proc"), host=None, user=None):
    """Read an internal resource-ready receipt bound to THIS Donau job.

    The incident gate supplies both path and digest after checking djob. A raw
    user-supplied memory number is never used. Host, account, single-node CPU,
    scheduler limit and the live process's job cgroup must all agree. This is a
    runtime-only resource proof, not a scientific cache or a resume shortcut.
    """
    env = os.environ if environ is None else environ
    path, expected = env.get(SCHEDULER_PROOF_ENV), env.get(SCHEDULER_SHA_ENV)
    if path is None and expected is None:
        return None
    try:
        import pwd
        proof = Path(path)
        if (not proof.is_absolute() or proof.is_symlink() or not proof.is_file()
                or not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None):
            raise ValueError("allocation proof is not a bound regular file")
        before = _signature(proof)
        if before[2] > 1024**2:
            raise ValueError("allocation proof is oversized")
        raw = proof.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected or _signature(proof) != before:
            raise ValueError("allocation proof changed")
        rows = json.loads(raw)["data"]["successData"]
        if len(rows) != 1:
            raise ValueError("allocation proof is not one job")
        job = rows[0]; groups = job["resGroups"]; job_id = str(job["jobId"])
        if (not job_id.isascii() or not job_id.isdecimal() or int(job_id) < 1
                or job["state"] != "RUNNING" or job["taskExecNodesCount"] != 1 or len(groups) != 1
                or job["taskExecNodes"] != (host or socket.gethostname())
                or job["user"] != (user or pwd.getpwuid(os.getuid()).pw_name)):
            raise ValueError("allocation proof is for a different running job")
        allocated, limited = groups[0]["resAlloc"], groups[0]["resLimit"]
        if (type(allocated["cpu"]) is not int or allocated["cpu"] < threads
                or any(type(n) is not int or n < 1 for n in (allocated["mem"], limited["mem"]))):
            raise ValueError("allocation proof lacks the requested CPU/memory bound")
        matches = False
        for row in (proc/"self/cgroup").read_text().splitlines():
            _, controllers, relative = row.split(":", 2)
            if (not controllers or set(controllers.split(",")) & {"memory", "cpu"}) and re.fullmatch(
                    r"/batch/container_"+job_id+r"_rg0_[A-Za-z0-9_]+(?:/.*)?", relative):
                matches = True
        if not matches:
            raise ValueError("allocation proof does not own this process's job cgroup")
        return min(allocated["mem"], limited["mem"])*1024**2
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        raise Q0EvidenceError("invalid current-job scheduler allocation proof") from exc


def execution_memory_limit(threads):
    cgroup = cgroup_memory_limit()
    allocation = allocation_memory_limit(threads)
    known = [n for n in (cgroup, allocation) if n is not None]
    return min(known) if known else None


@dataclass(frozen=True)
class ParentRequest:
    kind: str
    segment_id: str
    windows: tuple = ()
    chromosomes: tuple = ()
    regional_mask: int = 0
    native_mask: int = 0
    eligible_mask: int = 0
    # Cheap owner-only decisions need no index work, but retain stream order.
    ready: tuple | None = None


def plan_request(request, index):
    """The same scientific planner in owner and worker; no altered thresholds."""
    if request.ready is not None:
        return request.ready
    if request.kind == "partial":
        from .q0_regional_discovery import plan_parent
        plans, reason = plan_parent(SimpleNamespace(parts=index.parts), index, request.windows)
        return plans, 0, reason
    if request.kind != "candidate":
        raise Q0EvidenceError("unknown regional planning request")
    from .q0_regional_candidates import candidate_window_targets
    selection = index.target_selection(request.regional_mask)
    plans = []
    for query in request.windows:
        targets, reason = candidate_window_targets(index, request.segment_id, query, request.chromosomes, selection)
        if reason is not None:
            return [], request.eligible_mask, reason
        if targets:
            plans.append((query, targets))
    return plans, request.native_mask, "target_without_qualified_reference" if request.native_mask else None


_WORKER_INDEX = None
_WORKER_SNAPSHOT = None


def _initialize_reader(snapshot):
    global _WORKER_INDEX, _WORKER_SNAPSHOT
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = min([PLANNER_ADDRESS_SPACE, *(x for x in (soft, hard) if x != resource.RLIM_INFINITY)])
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    _WORKER_INDEX = ReferenceIndex.open_reader(snapshot)
    _WORKER_SNAPSHOT = snapshot


def _plan_in_worker(request):
    # Verify even when the record cache would avoid a new file read.
    _WORKER_SNAPSHOT.verify()
    try:
        result = plan_request(request, _WORKER_INDEX)
        payload = pickle.dumps(result, protocol=5)
        if len(payload) > MAX_RESULT_BYTES:
            return None
        _WORKER_SNAPSHOT.verify()
        return payload
    except MemoryError:
        return None  # Exact owner replan, never drop/approximate a parent.


class RegionalExecutor:
    def __init__(self, index, threads, *, budget=None):
        if type(threads) is not int or threads < 1:
            raise Q0EvidenceError("regional thread budget must be positive")
        self.index = index
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024 if resource else 0
        memory = execution_memory_limit(threads) if budget is None and resource and isinstance(index, ReferenceIndex) else None
        self.budget = budget or choose_budget(threads, memory, peak)
        b = self.budget
        if (b.total_threads != threads or b.planner_workers < 0 or b.mapper_workers < 0
                or b.mapper_threads < 0 or b.planner_workers+b.mapper_workers*b.mapper_threads+int(threads > 1) > threads
                or (b.planner_workers and (b.memory_limit_bytes is None or b.reserved_bytes > b.memory_limit_bytes))):
            raise Q0EvidenceError("regional executor budget exceeds allocation")
        self.report = {"execution_budget": self.budget.record(), "parallel_parents": 0,
                       "serial_parents": 0, "exact_owner_replans": 0, "pool_failure": None}
        self.pool = None; self.snapshot = None

    def __enter__(self):
        if self.budget.planner_workers:
            self.snapshot = self.index.reader_snapshot()
            try:
                self.pool = ProcessPoolExecutor(max_workers=self.budget.planner_workers,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=_initialize_reader, initargs=(self.snapshot,))
            except (OSError, MemoryError) as exc:
                self.report["pool_failure"] = type(exc).__name__
        return self

    def __exit__(self, *args):
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)
        if self.snapshot is not None:
            self.snapshot.verify()
        self.index.verify_inputs()

    def ordered(self, requests):
        """Bounded FIFO prefetch; whole-parent fallback precedes any mapping.

        Only this module's own spawned workers produce the pickle byte stream.
        No persistent pickle cache or customer-supplied pickle is read here.
        """
        pending = deque(); requests = iter(requests); exhausted = False
        limit = max(1, 2*self.budget.planner_workers)
        while pending or not exhausted:
            while not exhausted and len(pending) < limit:
                try:
                    request = next(requests)
                except StopIteration:
                    exhausted = True
                    break
                future = None
                if self.pool is not None and not self.report["pool_failure"] and request.ready is None:
                    try:
                        future = self.pool.submit(_plan_in_worker, request)
                    except (BrokenProcessPool, OSError, MemoryError) as exc:
                        self.report["pool_failure"] = type(exc).__name__
                pending.append((request, future))
            if not pending:
                continue
            request, future = pending.popleft()
            payload = None
            if future is not None:
                try:
                    payload = future.result()
                except (BrokenProcessPool, MemoryError) as exc:
                    self.report["pool_failure"] = type(exc).__name__
                if self.snapshot is not None:
                    self.snapshot.verify()
            if payload is not None:
                result = pickle.loads(payload)
                self.report["parallel_parents"] += 1
            else:
                if future is not None:
                    self.report["exact_owner_replans"] += 1
                result = plan_request(request, self.index)
                self.report["serial_parents"] += 1
            yield request, result
