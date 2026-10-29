"""Read-only job-budget snapshots and conservative FIFO admission experiments.

No scheduler, reservation, minimap2 parameter change or data skipping. cgroup v2
visible ancestors and Slurm node allocations are separate constraints. Neither
node RAM nor a shared allocation is memory exclusively owned by this process.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

MIB = 1024**2
MAX_METADATA_BYTES = 1024**2


class BudgetError(ValueError):
    pass


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise BudgetError(f"{name} must be an integer >= {minimum}")
    return value


def decimal(raw, name):
    if not re.fullmatch(r"[0-9]{1,20}", raw):
        raise BudgetError(f"invalid {name}: expected a bounded decimal integer")
    return int(raw)


def read_text(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise BudgetError("oversized resource metadata")
    return raw.decode("utf-8", errors="strict")


def absolute_path(raw, mount_field=False):
    if mount_field:
        raw = re.sub(r"\\(040|011|012|134)", lambda m: chr(int(m[1], 8)), raw)
    path = PurePosixPath(raw)
    if not raw.startswith("/") or raw.startswith("//") or ".." in path.parts:
        raise BudgetError("unsafe or namespace-unresolvable cgroup path")
    return path


def slurm_limits(env, usable_cpus, warnings):
    keys = ("SLURM_MEM_PER_NODE", "SLURM_MEM_PER_CPU", "SLURM_MEM_PER_GPU")
    if not (env.get("SLURM_JOB_ID") or env.get("SLURM_JOBID")):
        if any(k in env for k in keys):
            warnings.append("Slurm memory variables ignored outside an identified job")
        return []
    present = [k for k in keys if k in env]
    if len(present) > 1:
        raise BudgetError("conflicting Slurm memory modes; allocation needs confirmation")
    if not present:
        warnings.append("Slurm job has no supported memory-allocation metadata")
        return []
    key = present[0]
    value = decimal(env[key], key)
    if value == 0:
        warnings.append("Slurm zero/all-node memory is not a finite byte allocation")
        return []
    if key == "SLURM_MEM_PER_GPU":
        raise BudgetError("per-GPU Slurm memory is not supported by this experiment")
    if key == "SLURM_MEM_PER_CPU":
        # Allocated hardware threads need not all be usable for --mem-per-cpu.
        # Do not multiply by CPUS_ON_NODE, CPUS_PER_TASK or a multi-node CPU list.
        if usable_cpus is None:
            raise BudgetError("per-CPU memory requires operator-confirmed local usable CPU count")
        integer(usable_cpus, "Slurm usable CPUs", 1)
        if "SLURM_CPUS_ON_NODE" in env and usable_cpus > decimal(env["SLURM_CPUS_ON_NODE"], "SLURM_CPUS_ON_NODE"):
            raise BudgetError("usable CPU count exceeds local allocated CPUs")
        value *= usable_cpus
    return [{"source": key, "limit_bytes": value * MIB, "current_bytes": None,
             "scope": "Slurm current-node allocation; advisory, not a reservation"}]


def cgroup_limits(proc_root, warnings):
    membership_path = Path(proc_root) / "self/cgroup"
    mountinfo_path = Path(proc_root) / "self/mountinfo"
    membership, mountinfo = read_text(membership_path), read_text(mountinfo_path)
    unified = []
    for line in membership.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            raise BudgetError("malformed cgroup membership")
        if "memory" in parts[1].split(","):
            raise BudgetError("cgroup v1 memory accounting is not supported; no v2 fallback")
        if parts[:2] == ["0", ""]:
            unified.append(absolute_path(parts[2]))
    if len(unified) != 1:
        raise BudgetError("expected one resolvable cgroup v2 membership")
    group = unified[0]
    mounts = []
    for line in mountinfo.splitlines():
        try:
            before, after = line.split(" - ", 1)
            fields, fs = before.split(), after.split()
            if fs[0] != "cgroup2":
                continue
            root, mount = absolute_path(fields[3], True), absolute_path(fields[4], True)
        except (ValueError, IndexError) as exc:
            raise BudgetError("malformed mountinfo") from exc
        if group.is_relative_to(root):
            mounts.append((root, mount))
    if not mounts:
        raise BudgetError("cgroup membership cannot be mapped to a visible v2 mount")
    # Prefer the widest visible hierarchy; choosing a leaf bind mount may hide a
    # tighter parent. Ambiguous equally-wide mounts fail closed instead of guessing.
    depth = min(len(root.parts) for root, _ in mounts)
    widest = list(set((root, mount) for root, mount in mounts if len(root.parts) == depth))
    if len(widest) != 1:
        raise BudgetError("ambiguous cgroup v2 mounts")
    root, mount = widest[0]
    leaf = Path(mount / group.relative_to(root))
    mount = Path(mount)
    warnings.append("only visible ancestors checked; hidden namespace ancestors cannot be certified")
    limits, observations = [], []
    node = leaf
    levels = 0
    while True:
        levels += 1
        if levels > 256:
            raise BudgetError("cgroup hierarchy exceeds bounded depth")
        max_path, current_path = node / "memory.max", node / "memory.current"
        # The genuine v2 hierarchy root has no memory interface files. A bind /
        # namespace root can have them; read them whenever present. Missing files
        # below the visible mount are not interpreted as unlimited.
        if node == mount and root == PurePosixPath("/") and not max_path.exists() and not current_path.exists():
            warnings.append("visible root has no memory interface; no root ceiling inferred")
        else:
            raw_max = read_text(max_path).strip()
            current = decimal(read_text(current_path).strip(), "memory.current")
            cap = None if raw_max == "max" else decimal(raw_max, "memory.max")
            if read_text(max_path).strip() != raw_max:
                raise BudgetError("cgroup memory limit changed during snapshot")
            row = {"source": "cgroup_v2", "path": str(node), "limit_bytes": cap,
                   "current_bytes": current, "scope": "cgroup and descendants, including file cache"}
            observations.append(row)
            if cap is not None:
                limits.append(row)
        if node == mount:
            break
        node = node.parent
    if read_text(membership_path) != membership or read_text(mountinfo_path) != mountinfo:
        raise BudgetError("cgroup membership/mounts changed during snapshot")
    return limits, observations


def discover_budget(*, proc_root=Path("/proc"), environ=None, explicit_bytes=None, slurm_usable_cpus=None):
    """Take a bounded read-only snapshot. Errors remain visible and block planning."""
    started = time.monotonic_ns()
    env = dict(os.environ if environ is None else environ)
    warnings, errors, limits, observations = [], [], [], []
    if explicit_bytes is not None:
        integer(explicit_bytes, "explicit job budget", 1)
        limits.append({"source": "explicit_job_budget", "limit_bytes": explicit_bytes,
                       "current_bytes": None, "scope": "operator-supplied planning ceiling"})
    try:
        limits.extend(slurm_limits(env, slurm_usable_cpus, warnings))
    except BudgetError as exc:
        errors.append(str(exc))
    try:
        cg_limits, observations = cgroup_limits(proc_root, warnings)
        limits.extend(cg_limits)
    except (OSError, UnicodeError, BudgetError) as exc:
        errors.append(f"cgroup snapshot unavailable: {exc}")
    caps = [row["limit_bytes"] for row in limits]
    heads = [max(0, row["limit_bytes"] - row["current_bytes"]) for row in limits if row["current_bytes"] is not None]
    if not caps:
        warnings.append("no finite job ceiling; node MemTotal is deliberately not used")
    return {"schema": 1, "scope": "experimental_current_node_job_planning",
            "observed_at_monotonic_ns": started, "limits": limits,
            "cgroup_observations": observations, "errors": errors, "warnings": warnings,
            "effective_limit_bytes": min(caps) if caps else None,
            "observed_headroom_bytes": min(heads) if heads else None,
            "production_ready": False, "job_memory_reserved": False,
            "host_memory_used_as_budget": False, "limits_changed": False}


@dataclass(frozen=True)
class Demand:
    task_id: str
    threads: int
    peak_bytes: int | None


def plan_admission(snapshot, pending, *, cpu_budget, baseline_bytes, reserve_bytes,
                   active=(), max_age_seconds=5, now_ns=None):
    """Pure FIFO proposal, never permission to launch. Estimates are caller inputs.

    Full active peak reservations are subtracted even from observed cgroup
    headroom (which already includes resident active tasks): conservative double
    accounting avoids assuming any ownership/reclaimability of shared usage.
    """
    integer(cpu_budget, "CPU budget", 1)
    integer(baseline_bytes, "baseline bytes")
    integer(reserve_bytes, "reserve bytes", 1)
    integer(max_age_seconds, "snapshot max age", 1)
    pending, active = tuple(pending), tuple(active)
    ids = set()
    for demand in (*active, *pending):
        if not isinstance(demand.task_id, str) or not demand.task_id or demand.task_id in ids:
            raise BudgetError("task IDs must be nonempty and unique")
        ids.add(demand.task_id)
        integer(demand.threads, "task threads", 1)
        if demand.peak_bytes is not None:
            integer(demand.peak_bytes, "task peak bytes", 1)
    now = time.monotonic_ns() if now_ns is None else integer(now_ns, "current monotonic timestamp")
    age = now - integer(snapshot["observed_at_monotonic_ns"], "snapshot timestamp")
    reasons = list(snapshot["errors"])
    if age < 0 or age > max_age_seconds * 10**9:
        reasons.append("stale or incompatible-clock snapshot; refresh before planning")
    cap = snapshot["effective_limit_bytes"]
    observed = snapshot["observed_headroom_bytes"]
    if cap is None:
        reasons.append("no finite job budget")
    else:
        integer(cap, "effective job limit")
    if observed is not None:
        integer(observed, "observed cgroup headroom")
    if any(d.peak_bytes is None for d in active):
        reasons.append("active task has unknown peak reservation")
    used_cpus = sum(d.threads for d in active)
    if used_cpus > cpu_budget:
        reasons.append("active threads already exceed CPU budget")
    available_cpu = max(0, cpu_budget - used_cpus)
    held = baseline_bytes + reserve_bytes + sum(d.peak_bytes or 0 for d in active)
    available_memory = max(0, min(cap, observed if observed is not None else cap) - held) if cap is not None else 0
    initial_memory, decisions = available_memory, []
    blocked = bool(reasons)
    for demand in pending:
        reason = None
        if blocked:
            reason = "snapshot blocked" if reasons else "FIFO predecessor deferred"
        elif demand.peak_bytes is None:
            reason = "unknown task peak; estimate/measure before admission"
        elif demand.threads > available_cpu:
            reason = "insufficient remaining CPU budget"
        elif demand.peak_bytes > available_memory:
            reason = "insufficient conservative memory headroom"
        if reason is None:
            available_cpu -= demand.threads
            available_memory -= demand.peak_bytes
        else:
            blocked = True
        decisions.append({"task_id": demand.task_id, "threads": demand.threads,
                          "peak_bytes": demand.peak_bytes,
                          "decision": "defer" if reason else "eligible_under_snapshot_only", "reason": reason})
    return {"scope": "experimental_FIFO_proposal_only", "blocking_reasons": reasons,
            "decisions": decisions, "initial_memory_headroom_bytes": initial_memory,
            "remaining_memory_bytes": available_memory, "remaining_cpus": available_cpu,
            "baseline_bytes": baseline_bytes, "reserve_bytes": reserve_bytes,
            "active_peak_double_accounting": True, "cache_reclaim_assumed": False,
            "production_ready": False, "launch_allowed": False, "reservations_committed": False,
            "running_tasks_changed": False, "data_skipped": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-mib", type=int, help="explicit job planning ceiling, not a reservation")
    parser.add_argument("--slurm-usable-cpus", type=int, help="confirmed local usable allocation for per-CPU memory")
    args = parser.parse_args()
    try:
        result = discover_budget(explicit_bytes=None if args.budget_mib is None else args.budget_mib*MIB,
                                 slurm_usable_cpus=args.slurm_usable_cpus)
    except BudgetError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 2 if result["errors"] or result["effective_limit_bytes"] is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
