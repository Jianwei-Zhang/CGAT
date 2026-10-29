"""Process-budget adaptation for experimental trace reading, not a job scheduler.

Only explicit process budgets and RLIMIT_AS are used. Never treat host RAM or a
shared Slurm/cgroup job allocation as memory exclusively available to this reader.
The plan is a pre-allocation snapshot, not a reservation or a physical-RAM limit.
"""
from __future__ import annotations

import os
from pathlib import Path
import resource

from windowed_alignment import ExperimentError

MIB = 1024**2
BUFFERS = (8192, 65536, MIB, 16*MIB)


def choose_buffer(virtual_bytes, address_space_limit=None, explicit_bytes=None, requested_bytes=None):
    """Pure policy; small budgets downshift cache, never omit scientific data."""
    if type(virtual_bytes) is not int or virtual_bytes <= 0:
        raise ExperimentError("current process memory size is unavailable")
    limits = []
    if explicit_bytes is not None:
        if type(explicit_bytes) is not int or explicit_bytes <= 0:
            raise ExperimentError("trace process budget must be a positive integer")
        limits.append(("explicit_process_budget", explicit_bytes))
    if address_space_limit is not None:
        if type(address_space_limit) is not int or address_space_limit <= 0:
            raise ExperimentError("invalid process address-space limit")
        limits.append(("RLIMIT_AS", address_space_limit))
    fallback = not limits
    if fallback:
        limits.append(("conservative_process_planning_default", 128*MIB))
    budget = min(limit for _, limit in limits)
    reserve = max(2*MIB, min(32*MIB, budget//8))
    headroom = budget - virtual_bytes - reserve
    if headroom < BUFFERS[0]:
        raise ExperimentError("trace process budget insufficient after current virtual size and safety reserve; no data skipped")
    if requested_bytes is not None and (type(requested_bytes) is not int or not 8192 <= requested_bytes <= 16*MIB):
        raise ExperimentError("trace read buffer must be 8 KiB..16 MiB")
    if requested_bytes is None:
        # Auto remains conservative: no evidence justifies huge buffers merely
        # because a machine/job is large. Explicit requests may go up to16 MiB.
        preferred = MIB if headroom >= 128*MIB else 65536 if headroom >= 16*MIB else 8192
    else:
        preferred = requested_bytes
    fitting = [size for size in BUFFERS if size <= min(preferred, headroom)]
    selected = max(fitting)
    return {"scope": "trace_reader_process_planning_only", "sources": dict(limits),
            "process_virtual_bytes": virtual_bytes, "effective_budget_bytes": budget,
            "reserve_bytes": reserve, "allocation_headroom_bytes": headroom,
            "requested_buffer_bytes": requested_bytes, "selected_buffer_bytes": selected,
            "buffer_downshifted": selected < preferred, "fallback_used": fallback,
            "hard_limit_changed": False, "job_memory_reserved": False,
            "slurm_cgroup_allocation_discovery_implemented": False}


def current_virtual_bytes():
    # Bounded procfs read, not an estimate inferred from node-wide MemTotal.
    try:
        with Path("/proc/self/statm").open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("oversized statm")
        return int(raw.split()[0]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError) as exc:
        raise ExperimentError("cannot determine current process memory for trace budget") from exc


def process_plan(explicit_bytes=None, requested_bytes=None):
    soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    limit = None if soft == resource.RLIM_INFINITY else soft
    return choose_buffer(current_virtual_bytes(), limit, explicit_bytes, requested_bytes)
