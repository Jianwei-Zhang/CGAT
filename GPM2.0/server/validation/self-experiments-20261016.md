# Self alignment scheduling and sensitivity experiments — 2026-10-16

## Scope and active jobs

User authorized testing dynamic resource allocation and lower self-alignment
sensitivity for speed, while hiding tuning flags (including existing -sm/-sn)
from user-facing documentation. No public new knob or new default was requested.

Root on SSH180: `~/cgat-reads-debug/self-experiments-20261016/`.
All computation through Donau x86; same existing minimap2 2.30 binary/environment.
Original customer inputs/runtime paths are read only. Outputs, scripts, PAFs,
logs and reports have new independent directories. No active job was restarted
or hot-edited. Existing m200/n100 defaults and GRT settings remain unchanged.

| Job | Experiment | CPUs | Initial state |
| --- | --- | ---: | --- |
| 40587709 | Current then adaptive scheduler on 24 real self tasks | 16 | RUNNING |
| 40587710 | Precision baseline: m200/n100 | 2 | RUNNING |
| 40587711 | Baseline plus --rmq-inner100 | 2 | RUNNING |
| 40587712 | Baseline plus --rmq-inner0 | 2 | RUNNING |
| 40587713 | Baseline plus -U50,100 | 2 | RUNNING |
| 40587714 | Compare completed precision profiles | 1 | Dependent on four successes |

These are official CLI controls with experimental values, not an official
recommended combined preset. Each precision job sequentially maps full chr01
hifiasm self query and full chr03 flye self query, using the exact immutable
self_target/query/name-map/restore script from the prepared customer workspace.
No target/query slicing, filtering of inputs or removal of CIGAR. Numerical
parameters other than each named experimental override stay fixed.

## Scheduling experiment

The production process runner has a private, keyword-only `dispatch` hook with
validated grants; the default path is unchanged. No public CLI/environment flag
activates it. Only the isolated harness injects the prototype dispatcher.

Both variants use the same 24 self tasks (8 chromosomes x 3 assemblies), pinned
m200/n100 and 16-thread total budget; largest-work-first ordering. The current
variant fills all slots like the existing allocator. The adaptive variant uses
query length skew as a heuristic serial fraction and stops increasing a task's
initial thread count once modeled marginal speedup is below 8%. This is NOT a
measured scaling law. It can correctly retain a 1-thread cap for a single-query
or extreme-skew task; blindly forcing every task multithreaded is not the goal.

Adaptive admission waits for the preferred allocation instead of starting a
large multi-query task at one thread just to fill a hole. Completed-task runtimes
update a pooled cost-rate estimate; short-work backfill is permitted only when
predicted to finish before the next resource release. This estimate is fallible.
At most eight adaptive index-bearing processes run concurrently as a conservative
memory limit, not measured dynamic memory sizing. Allocated threads stay reserved
until process completion: no live resizing, CPU-utilization-based overselling,
checkpoint slicing or single-contig windowing is implemented in this trial.

Current then adaptive execute serially within the same allocation/node. This
controls machine identity but does not remove order/OS-cache effects. The workload
excludes cross-assembly/telomere tasks and therefore is NOT a full workflow timing.
No production benefit is claimed before results; a negative result is retained.
Each variant has a 12-hour soft deadline using existing process-group cancellation.

Metrics: per-task allocation/wall time, overall stage makespan, reserved core-time
and below-half-reservation wall duration. Reservation utilization is explicitly
NOT measured CPU utilization. Each minimap2 process has `/usr/bin/time -v` resource
logs (CPU time/peak RSS); these supplement scheduler accounting. PAF validation
requires legal coordinate bounds and CIGAR, compares ordered hashes and separately
order-insensitive count/two cryptographic aggregate digests of all fields/tags.
An unordered match is recorded separately, not mislabeled byte equality or
Final Path equality. Strong-hit union query coverage is stratified by pair/strand.

## Sensitivity interpretation

The dependent comparator requires all four runs completed and identical input/tool
identities. It reports each profile's time, row count, merged query coverage for
>=5kb and >=90% identity matches, retained coverage and missing pairs/strands.
This is retention against the baseline, not ground-truth precision. Timings are
single-pass and may be on different/shared nodes; repeat a promising candidate
under controlled conditions before making a production claim. Biological
thresholds and GRT are not changed. Existing old m40/n3 runs are not restarted.

## Public interface and necessary checks

Removed long and short self m/n flags from both top-level and nested bilingual
READMEs and prepare/run help. Parsing remains for existing scripts/compatibility;
no new controls are exposed. Validation records are maintainer-only evidence.

Focused validation only: six process-runner tests passed, including allocation
recovery and rejection of oversubscription; adaptive admission/PAF sanity checks,
Python parsing and Bash syntax passed. SHA256 transfer verification passed and
actual remote START lines confirm jobs run. No broad frontend or unrelated tests.
Release assets are not refreshed while these experiments/whole-data gates remain
in flight; source/docs are not claimed publicly delivered.

## Other observed user bottlenecks

User's original global reference alignment critical path was ~68.7 minutes;
GRT Step23 was 19.4h. Late task admission is part of the scheduler issue, not a
separate additive cost. Saved stack samples include fine-grained DP alignment as
well as chaining, so seed/chain-only speedups are not assumed sufficient.
Original diagnostics show ample available memory and low I/O wait at the sampled
time, not evidence of persistent paging/I/O saturation. Evidence finalization,
validation and packaging take tens of minutes in our completed old run, but were
still pending at the user's 62h+ snapshot and cannot explain that elapsed time.
Cross-process repeated validation/data scans remain a follow-up profiling target,
not another measured multi-day bottleneck or already-adopted optimization.
