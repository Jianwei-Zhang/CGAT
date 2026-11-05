"""Internal, opportunistic original-part budget; never a customer config file.

The dispatcher must prove no concurrent/pending CGAT mapping siblings. A finite
cgroup envelope or single-task Slurm allocation can then bound this ONE group.
No host total/free RAM, QC option or per-process RLIMIT is treated as job RAM.
A grant is a conservative execution allowance, NOT a physical RAM reservation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re

ENV = "GPM_REFERENCE_DISPATCH"
GIB = 1024**3
MAX_READ = 1024**2
MAX_MEMORY = 2**60


def _read(path):
    with Path(path).open("rb") as stream:
        value = stream.read(MAX_READ + 1)
    if len(value) > MAX_READ:
        raise ValueError("oversized resource metadata")
    return value.decode("utf-8")


def _positive(value):
    if not isinstance(value, str) or len(value) > 20 or not value.isascii() or not value.isdecimal():
        raise ValueError("invalid resource integer")
    number = int(value)
    if not 0 < number < MAX_MEMORY:
        raise ValueError("resource integer outside supported range")
    return number


def _start(pid, proc):
    # comm may itself contain ')' and whitespace. Fields after the LAST ')' are
    # state (field 3), ..., starttime (field 22).
    return _read(proc / str(pid) / "stat").rsplit(")", 1)[1].split()[19]


def dispatch_context(run_dir, threads, *, environment=None, proc=Path("/proc"), parent_pid=None):
    env = os.environ if environment is None else environment
    disabled = {"enabled": False, "scope": "exclusive_current_CGAT_alignment_task_only"}
    try:
        raw = env.get(ENV, "")
        if not raw:
            return {**disabled, "reason": "no_dispatcher_exclusive_context"}
        if len(raw) > 16384:
            raise ValueError("oversized dispatcher context")
        context = json.loads(raw)
        if type(context) is not dict or context.get("schema") != 1:
            raise ValueError("invalid dispatcher context")
        if context.get("exclusive") is not True:
            return {**disabled, "reason": "other_CGAT_alignment_siblings_not_excluded"}
        pid = context.get("parent_pid")
        expected_parent = os.getppid() if parent_pid is None else parent_pid
        if (type(pid) is not int or pid < 1 or pid != expected_parent
                or context.get("parent_start") != _start(pid, proc)
                or context.get("command") != str(Path(run_dir).resolve() / "command.sh")
                or context.get("run_id") != env.get("GPM_REPORT_RUN_ID") or not context.get("run_id")
                or context.get("unit_id") != env.get("GPM_REPORT_UNIT_ID")
                or not str(context.get("unit_id", "")).startswith("ref:")
                or type(context.get("threads")) is not int or context["threads"] != threads):
            raise ValueError("dispatcher process/task binding differs")
        return {**context, "enabled": True, "scope": disabled["scope"],
                "reason": "live_parent_excludes_concurrent_CGAT_mapping_siblings"}
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return {**disabled, "reason": "invalid_or_stale_dispatcher_context"}


def _unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


def cgroup_envelopes(*, proc=Path("/proc")):
    """Read current membership plus every visible ancestor, not host MemAvailable.

    v1 huge unlimited sentinels are ignored. Missing non-root controller files
    decline this provider rather than guessing a tighter hidden ancestor away.
    Mount roots are honored; ambiguous namespace mappings decline the provider.
    """
    try:
        memberships = []
        for line in _read(proc / "self/cgroup").splitlines():
            _, controllers, member = line.split(":", 2)
            if controllers == "" or "memory" in controllers.split(","):
                memberships.append((2 if controllers == "" else 1, member))
        mounts = []
        for line in _read(proc / "self/mountinfo").splitlines():
            left, right = line.split(" - ", 1)
            fields, tail = left.split(), right.split()
            if tail[0] == "cgroup2" or tail[0] == "cgroup" and "memory" in tail[2].split(","):
                mounts.append((2 if tail[0] == "cgroup2" else 1,
                               _unescape(fields[3]), Path(_unescape(fields[4]))))
        found = []
        for version, member in memberships:
            for kind, mount_root, mount in mounts:
                if kind != version:
                    continue
                if ".." in PurePosixPath(member).parts or ".." in PurePosixPath(mount_root).parts:
                    raise ValueError("invalid cgroup path")
                if member == "/":
                    relative = PurePosixPath(".")
                else:
                    relative = PurePosixPath(member).relative_to(PurePosixPath(mount_root))
                directory = mount.joinpath(*relative.parts)
                if mount.resolve() != directory.resolve() and mount.resolve() not in directory.resolve().parents:
                    raise ValueError("cgroup membership escaped mounted root")
                limit_file, usage_file = (("memory.max", "memory.current") if version == 2
                                           else ("memory.limit_in_bytes", "memory.usage_in_bytes"))
                while True:
                    try:
                        text = _read(directory / limit_file).strip()
                    except FileNotFoundError:
                        if directory != mount:
                            raise
                        text = "max"  # Root has no configurable memory.max.
                    if text != "max":
                        if not text.isascii() or not text.isdecimal() or len(text) > 20:
                            raise ValueError("invalid cgroup memory limit")
                        limit = int(text)
                        if 0 <= limit < MAX_MEMORY:
                            usage_text = _read(directory / usage_file).strip()
                            if not usage_text.isascii() or not usage_text.isdecimal() or len(usage_text) > 20:
                                raise ValueError("invalid cgroup memory usage")
                            usage = int(usage_text)
                            found.append({"source": f"cgroup_v{version}", "path": str(directory),
                                          "limit_bytes": limit, "usage_bytes": usage,
                                          "available_bytes": max(0, limit - usage)})
                    if directory == mount:
                        break
                    directory = directory.parent
        return found, None if found else "no_visible_finite_cgroup_memory_limit"
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return [], "cgroup_memory_envelope_unavailable_or_ambiguous"


def slurm_envelopes(environment):
    """Optional allocation provider; cgroup/container use does not need Slurm.

    Multi-node/task scopes are deliberately not guessed into a per-reference
    budget. These are scheduler allocation bytes, not an observed free-RAM claim.
    """
    env = environment
    if not env.get("SLURM_JOB_ID"):
        return [], "not_a_slurm_allocation"
    try:
        if _positive(env.get("SLURM_JOB_NUM_NODES", "")) != 1 or _positive(env.get("SLURM_NTASKS", "1")) != 1:
            return [], "slurm_allocation_not_single_node_single_task"
        found = []
        if env.get("SLURM_MEM_PER_NODE"):
            found.append({"source": "slurm_memory_per_node", "limit_bytes": _positive(env["SLURM_MEM_PER_NODE"]) * 1024**2})
        if env.get("SLURM_MEM_PER_CPU"):
            found.append({"source": "slurm_memory_per_cpu", "limit_bytes":
                          _positive(env["SLURM_MEM_PER_CPU"]) * _positive(env.get("SLURM_CPUS_ON_NODE", "")) * 1024**2})
        for item in found:
            if not 0 < item["limit_bytes"] < MAX_MEMORY:
                raise ValueError("oversized scheduler memory envelope")
            item["available_bytes"] = item["limit_bytes"]
            item["free_memory_observed"] = False
        return found, None if found else "slurm_memory_allocation_unknown"
    except (ValueError, TypeError):
        return [], "slurm_memory_allocation_invalid"


def grant(context, *, environment=None, proc=Path("/proc")):
    disabled = {"enabled": False, "scope": "exclusive_current_CGAT_alignment_task_only",
                "budget_bytes": None, "host_ram_used": False, "qc_memory_used": False,
                "physical_memory_reservation": False}
    if not context or context.get("enabled") is not True:
        return {**disabled, "reason": (context or {}).get("reason", "no_dispatcher_exclusive_context")}
    env = os.environ if environment is None else environment
    # Revalidate parent ownership at the mapping boundary, AFTER index build.
    current = dispatch_context(Path(context["command"]).parent, context["threads"], environment=env, proc=proc)
    if current != context:
        return {**disabled, "reason": "dispatcher_context_changed_before_mapping"}
    cgroups, cgroup_reason = cgroup_envelopes(proc=proc)
    scheduler, scheduler_reason = slurm_envelopes(env)
    sources = cgroups + scheduler
    if (cgroup_reason == "cgroup_memory_envelope_unavailable_or_ambiguous"
            or scheduler_reason == "slurm_memory_allocation_invalid"):
        return {**disabled, "reason": "effective_memory_envelope_unverifiable",
                "provider_notes": [cgroup_reason, scheduler_reason]}
    if not sources:
        return {**disabled, "reason": "no_authoritative_job_or_container_memory_envelope",
                "provider_notes": [cgroup_reason, scheduler_reason]}
    available = min(item["available_bytes"] for item in sources)
    reserve = max(GIB, available // 10)
    budget = max(0, available - reserve)
    return {**disabled, "enabled": budget > 0, "budget_bytes": budget or None,
            "reason": "exclusive_dispatch_and_finite_memory_envelope" if budget else "memory_envelope_has_no_headroom",
            "sources": sources, "available_bytes": available, "boundary_reserve_bytes": reserve,
            "context": context, "provider_notes": [cgroup_reason, scheduler_reason]}


def resolve(args):
    """Resolve once per fresh native-argument object, immediately before mapping."""
    if not getattr(args, "ordinary_budget_resolved", False):
        context = getattr(args, "ordinary_resource_context", None)
        if context is not None and getattr(args, "ordinary_group_memory_bytes", None) is None:
            value = grant(context)
            args.ordinary_resource_grant = value
            args.ordinary_group_memory_bytes = value["budget_bytes"]
        args.ordinary_budget_resolved = True
    return getattr(args, "ordinary_group_memory_bytes", None)
