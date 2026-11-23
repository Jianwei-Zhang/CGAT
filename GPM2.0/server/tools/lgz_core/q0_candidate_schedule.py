"""Schedule independent whole-target candidate maps; never split FASTAs or change mapper flags."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from . import q0_regional_execution as resources

GIB = 1024**3


@dataclass(frozen=True)
class MapWork:
    key: str
    query_bp: int
    target_bp: int

    @property
    def cost(self):
        # Scheduling hint only. Prefer starting large remaining requests first.
        return self.query_bp * self.target_bp

    @property
    def reservation(self):
        # Whole assemblies, NOT the bounded regional mapper. Allow for indexing,
        # repeats, alignment buffers and PAF parsing. This is admission headroom,
        # not an assertion that every input (especially repetitive DNA) fits.
        return 2 * GIB + 80 * (self.query_bp + self.target_bp)


def _live_donau_allocation(proc=Path('/proc')):
    # Some Donau sites disallow reading cgroup limits. Identify the running
    # job from the kernel, not its environment or a user-specified byte count.
    try:
        match = re.search(r'^\d+:memory:/batch/container_([0-9]+)_rg0_[A-Za-z0-9_]+(?:/[^\n]*)?$',
                          (proc/'self/cgroup').read_text(), re.MULTILINE)
        if not match or not (tool := shutil.which('djob')):
            return None
        job_id = match.group(1)
        result = subprocess.run([tool, '-L', '-J', job_id], capture_output=True, timeout=5, check=True)
        if len(result.stdout) > 1024**2:
            return None
        rows = json.loads(result.stdout)['data']['successData']
        if len(rows) == 1 and str(rows[0]['jobId']) == job_id:
            return resources.checked_job_allocation(rows[0], proc=proc)
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError):
        pass  # No usable scheduler proof: retain the serial fallback.
    return None


def available_budget(threads):
    if hasattr(os, 'sched_getaffinity'):
        threads = min(threads, len(os.sched_getaffinity(0)))
    if threads <= 1 or sys.platform != 'linux' or not resources.resource:
        return threads, None
    limit = resources.execution_memory_limit(threads)
    if limit is None:
        grant = _live_donau_allocation()
        if grant is None:
            return threads, None
        cpus, limit = grant
        threads = min(threads, cpus)
    owner = resources.resource.getrusage(resources.resource.RUSAGE_SELF).ru_maxrss * 1024
    return threads, max(0, limit - owner - max(2 * GIB, limit // 5))


def run_pending(work, threads, memory, execute):
    """Grant mapper -t slots at dispatch, backfill free slots, drain on failure.

    Unknown memory or a map too large for the concurrency estimate retains the
    old single-mapper path. The estimate never causes a scientific omission.
    Only the owner mutates this queue; each key has a single producer.
    """
    if threads < 1 or len({job.key for job in work}) != len(work):
        raise ValueError('invalid Q0 candidate schedule')
    pending = sorted(work, key=lambda job: -job.cost)  # stable tie order
    results, active = {}, {}
    available = threads
    free = memory or 0
    with ThreadPoolExecutor(max_workers=min(threads, max(1, len(pending)))) as pool:
        while pending or active:
            launch = []
            for job in pending:
                if len(launch) == available:
                    break
                if memory is not None and job.reservation <= free:
                    launch.append(job)
                    free -= job.reservation
            # An oversized task runs alone after all smaller work drains.
            if pending and not launch and not active:
                launch = [pending[0]]
                free -= launch[0].reservation
            if launch:
                share, remainder = divmod(available, len(launch))
                for i, job in enumerate(launch):
                    grant = share + int(i < remainder)
                    pending.remove(job)
                    print(f'LGZ q0 candidate start: {job.key} threads={grant} '
                          f'reserved_bytes={job.reservation} active={len(active)+1}', flush=True)
                    active[pool.submit(execute, job.key, grant)] = job, grant, time.monotonic()
                    available -= grant
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                job, grant, start = active.pop(future)
                results[job.key] = future.result()  # do not dispatch further work on error
                free += job.reservation
                available += grant
                print(f'LGZ q0 candidate done: {job.key} elapsed_s={time.monotonic()-start:.2f}', flush=True)
    return results
