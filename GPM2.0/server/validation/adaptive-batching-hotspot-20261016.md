# Adaptive alignment scheduling and production self-query batching — 2026-10-16

## Accepted scope

The current acceptance policy is focused tests plus bounded real-data hotspot;
complete workflows and Final Path checks are deferred and do not block this
implementation. No public tuning option or README parameter is added. Step2
`gap-screen` remains disabled by default.

Production chromosome-local Minimap2 manifests now record query work and largest
record fraction. A non-preemptive dispatcher gives balanced, multi-record tasks
2–8 threads under the existing total CPU budget, admits new work immediately when
resources are released, and uses completed-task rates only for conservative short
backfill. Allocations never resize a running process or exceed its query-record cap.
Reference alignment manifests remain on the prior allocator; the adaptive policy
is activated only for profiled chromosome-local Minimap2 work.

Self alignment is compiled into contiguous whole-record batches (20 Mb target
size per batch, while a larger individual record remains whole). Each batch is an
outer scheduler task. All batches share one content/tool/preset-verified target
`.mmi`, validate query/target names, coordinates and CIGAR, restore original names,
and atomically publish checksum checkpoints. The last successful batch merges
restored PAFs in original query-batch order. Resume skips compatible batches;
corruption invalidates only the affected batch. A single giant query record is
not internally split and remains a residual serial-tail risk.

The generated manifest and batch inputs/scripts, batch runner, alignment compiler
and scheduler are included in outer checkpoint identities. Existing prepared
workspaces retain their pinned copied runtime and are not hot-edited.

## Final exact-source ARM hotspots

Source copies were SHA256-verified before submission. Both jobs used the isolated
ARM environment and the complete original chr03 flye self target.

### Adaptive scheduling: job 40588040, ARM 16 CPUs

The bounded fixture contains two heavy tasks, each with twelve copies of one real
250 kb hotspot window, and fourteen one-record tasks. Duplicate query aliases make
this scheduler-only evidence, not biological acceptance.

| Profile | Wall time | Heavy task allocations | Heavy task times |
|---|---:|---|---|
| Current | 89.62 s | 1, 1 | 87.22 s, 89.52 s |
| Adaptive | 62.93 s | 8, 8 | 14.68 s, 17.89 s |

Measured makespan speed ratio: **1.424x**. Ordered and order-insensitive PAF
comparisons both passed. An earlier equivalent dispatcher run measured 2.384x;
the final-source result is used for acceptance because short-task timing showed
node/load variance. The robust conclusion is not a fixed production speedup: the
mechanical one-thread heavy tail was removed and the bounded mixed workload stayed
faster without output change.

Long experiment 40587709 was cancelled after its partial current-only phase and
archived as superseded by this bounded hotspot. It is not recorded as a scientific
failure.

### Whole-record query batching: job 40588041, ARM 4 CPUs

Two distinct real 250 kb query windows were forced into separate whole-record
batches only to keep the test bounded.

| Stage | Time | Result |
|---|---:|---|
| Cold batching | 20.15 s | completed |
| Same-input unbatched baseline | 21.33 s | completed |
| Resume | 1.27 s | 2/2 cache hits |
| Corrupt one result and resume | 12.60 s | only batch 1 recomputed |

Merged and baseline PAF SHA256 values are identical; repaired output is also
identical. This accepts the production batching/checkpoint mechanism. It does not
claim that batching itself speeds a cold two-record job; its benefits are finer
scheduler admission, restart isolation and avoiding repeated target indexing.

## Focused local checks

- Eight scheduler tests pass, including profiled manifest round-trip, allocation
  recovery, oversubscription rejection and query-skew allocation.
- Production self-batch end-to-end test passes against an actual local minimap2:
  byte-identical unbatched output, cache hit, corruption detection and one-batch
  repair.
- Seven bounded query/hotspot helper tests pass; the prior process-reaping check
  was made race-safe when `/proc/<pid>` disappears between existence and read.
- Twelve run-all runner tests and six outer-checkpoint tests pass.

No broad frontend/browser tests and no complete workflow were run for this gate.
Official Release Server/skill assets are not refreshed at this stage.
