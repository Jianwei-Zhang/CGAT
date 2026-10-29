# Job memory discovery and admission planning — 2026-10-30

## Scope

`job_memory.py` adds an **experimental, read-only** current-node budget snapshot
and a pure FIFO admission proposal. It does not start jobs, reserve RAM, adjust
running tasks, change minimap2 options or integrate with production scheduling.
It also does not modify the customer isolation package currently in flight.

The earlier `trace_memory.py` remains a separate **process address-space/buffer**
planner. A cgroup/Slurm allocation must not be passed to it as if the reader owned
all of that RAM. This phase does not connect these two APIs automatically.

## Implemented policy

- Read bounded `/proc/self/cgroup` and `/proc/self/mountinfo`; resolve a v2
  membership through the widest unambiguous visible mount, including escaped
  mount points. Inspect the leaf **and every visible ancestor**, not just the leaf.
- Read `memory.max` and `memory.current`, including interfaces at a visible mount
  root when present. `max` is not a finite owned budget. Detect changed membership,
  mounts or a limit changing during its read. These observations are not atomic.
- Take the minimum finite cgroup/Slurm/explicit ceiling. Observe the tightest
  `limit - current` across constrained ancestors separately: the tightest ceiling
  and tightest remaining headroom can come from different ancestors.
- Read numeric Slurm memory values as MiB only in an identified job context.
  Per-node allocation is not multiplied by node count. Zero/all-node allocation
  is not converted into guessed RAM. No node-wide `MemTotal` fallback.
- Per-CPU allocation requires an **operator-confirmed local usable CPU count**.
  Do not assume `SLURM_CPUS_ON_NODE`, per-task CPUs or a multi-node CPU list is that
  count. Slurm's usable-CPU memory semantics can differ from allocated hardware
  threads. Conflicting/invalid metadata, unsupported per-GPU memory, cgroup v1
  memory controllers and unresolvable/ambiguous mounts explicitly block planning.
- Hidden namespace ancestors cannot be certified; this is reported, not silently
  treated as full host visibility. Missing/unreadable child interfaces block.

The pure `plan_admission` API requires explicit CPU budget, baseline memory,
reserve and task peak estimates. Unknown peaks defer work, not invent an estimate
from FASTA size or a previous sampled MaxRSS. It subtracts full active peak
reservations from both modeled budget and observed headroom, deliberately double
counting resident active tasks conservatively. Cache is included in observed
usage; **no cache reclaim is assumed**, so pressure may defer new work even if
some memory could be reclaimed. Existing tasks are never killed or changed.

Proposals preserve FIFO order and consume only modeled remaining CPU/RAM.
A five-second default snapshot age guard prevents stale proposals; it is not a
race-free reservation. `eligible_under_snapshot_only` is **not launch permission**:
all plans have `launch_allowed: false` and `reservations_committed: false`.
Actual scheduling still needs serialized reservation/accounting, verified peak
estimates, fresh pressure checks and integration with the existing CPU dispatcher.
With no finite cgroup ceiling, any explicit/Slurm-only cap is a modeled allocation,
not measured exclusive free memory; caller estimates must cover its owned workload.

## Read-only interface

From this directory (future operator use; do not change the customer's live job):

```bash
python3 job_memory.py
# Optional, operator-confirmed planning ceiling, not a memory reservation:
python3 job_memory.py --budget-mib 4096
```

Writes only JSON to stdout; creates no report directories, FASTA, PAF or jobs.
Exit 2 means the budget was unknown or discovery encountered a blocking problem.
Run inside the intended allocation when eventually validating Slurm behavior;
login-node observations cannot establish a compute job's memory allocation.

## Evidence completed BEFORE deferred-testing instruction

The user subsequently requested no further test execution during implementation.
The following results were already completed before that instruction:

- **24 new resource-policy tests** passed using temporary synthetic proc/cgroup
  fixtures; no host/job memory controls were modified.
- Full experiment suite: **109 tests passed with minimap2 2.26-r1175**.
- One read-only live local probe found no finite cgroup ceiling and returned 2,
  explicitly declining to substitute host RAM. This is not Slurm acceptance.
- Simulated 128 MiB / 512 MiB / 4 GiB / 500 GiB caps yielded respectively
  0 / 3 / 4 / 4 eligible proposals for four modeled 128 MiB, two-CPU tasks under
  an eight-CPU budget, 20 MiB observed usage, 16 MiB baseline and 32 MiB reserve.
  These are **policy fixtures, not workloads run on machines of those sizes**.

Tests cover parent pressure, stricter leaf limits, limit changes, stale snapshots,
namespace/mount ambiguity, path traversal, malformed/oversized/missing metadata,
Slurm usable-CPU confirmation, unlimited/zero limits, unknown peaks, existing
reservations, CPU bounds, FIFO deferral, input immutability and read-only behavior.
Source/log hashes are in `evidence/job-memory-planning-20261030.json`.

## Deferred final validation (DO NOT execute during this development phase)

1. Re-run the full experimental suite on both original minimap2 binaries,
   particularly 2.31-r1302, after the user opens final validation.
2. Validate resource discovery inside representative actual Slurm/cgroup v2
   allocations, including ancestor pressure and namespace layouts. No such
   cluster integration was performed here.
3. Review/support cgroup v1 or per-GPU allocation only as a separately implemented
   contract; current behavior intentionally refuses them.
4. Before production integration: verified task peaks, reservation ownership,
   admission serialization, memory-pressure/cache strategy, fairness, cancellation
   and preserving existing CPU scheduling and scientific outputs.

## Customer acceptance remains separate

A returned `locate` archive can identify a likely failing query in a well-formed
single-thread trace. It does not establish a parameter workaround or production
recovery. Independent whole-record replay, a candidate repair preserving CIGAR
and data, full original CGAT flow, and downstream biological/output acceptance
remain required. General post-DP candidate selection and MAPQ restoration are
still open. None of this phase resolves the assertion by merely reducing RAM use.

## Primary technical references consulted

These are specifications for the implementation, not evidence of customer success:

- Linux kernel cgroup v2 documentation: `https://docs.kernel.org/admin-guide/cgroup-v2.html`
- Slurm sbatch memory/usable-CPU and environment-variable documentation:
  `https://slurm.schedmd.com/sbatch.html`
