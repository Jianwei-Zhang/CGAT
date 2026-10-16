# Query batching and bounded real-hotspot fixtures — 2026-10-16

Internal validation only. No production defaults, public options or Release assets
changed here. Existing full workflows and experiment runtimes remain untouched.
The accompanying JSON records job IDs, immutable source hashes and snapshots.

## Whole-record batching prototype

`self_query_batches.py` preserves full query records, original record names/order,
complete target content, preset and CIGAR output. It builds one single-part target
index per case, schedules contiguous query batches under CPU and estimated-memory
budgets, and merges PAF in original batch order. Multipart indexes fail closed.
One very large record remains a single indivisible work item: this implementation
is NOT internal parallelism or checkpoint/restart inside that record.

Each batch validates tool/input/index identities and output coordinates/names,
then atomically publishes a checksum-verified completion marker. Zero-hit records
are in the manifest; an empty PAF without successful completion is not a hit.
Resume only reuses compatible own checkpoints. Corruption invalidates the affected
batch. Index reuse is content/tool/preset validated; execution grants do not resize
already-running minimap2 processes. Memory admission uses a conservative estimate,
not an enforced RSS limit or measured live CPU utilization. The experiment's run
fingerprint also pins resource configuration; changing it requires a new root.

### Functional proof (40587717, x86, four requested CPUs)

Seed 2665 synthetic cases include imperfect repeats, inversions, unique flanks,
long gaps, record-length skew and many short records. Both task PAFs match their
same-tool, same-parameter unbatched baseline **byte for byte**, not merely counts.

| Stage | Total batches | Cache hits | Time |
|---|---:|---:|---:|
| Cold batching | 10 | 0 | 4.192 s |
| Resume | 10 | 10 | 0.128 s |
| Corrupt one output and resume | 10 | 9 | 2.915 s |

The entire scheduler job succeeded in 13 seconds. Baseline mapping took only
2.652 + 0.537 seconds: cold batching is not a speed win on this tiny workload.
This is functional/checkpoint evidence, NOT reproduction of the customer hotspot,
full-workload throughput evidence or Final Path acceptance. Actual mid-mapping
interruption/resume of a real batch remains a separate gate.

## Bounded real-data calibration

`self_hotspot_fixture.py` keeps the customer's **entire target** and uses a pinned
minimap2 2.30-r1287 binary. It samples 250 kb / 1 Mb start/middle/end windows from
one actual query plus that whole query. Cropped queries retain original aliases;
source intervals/hashes are recorded. Each profile maps with one thread, matching
the original per-query bottleneck setting; index building uses two threads.
The original command defaults, current m200/n100 and experimental U50,100 are
measured separately. Window runs have a 10-second deadline, whole-query probes
45 seconds, index build 60 seconds and the job a 600-second outer deadline.
Timeout handling kills/reaps the process group; unfinished output is never used
as a complete PAF or precision reference. Whole-query probes provide a lower
bound only, not proof of a historical multi-day time for that individual query.

These are diagnostic windows, **not a proposal to slice/merge production contigs**.
Cropping changes chaining/boundary context even while target frequencies remain
available. It cannot establish the same internal bottleneck without further
profiling, or prove original full-query biological equivalence. Index loading is
included in window wall time; same-node jobs share hardware, and timings are
exploratory. The longest query is not assumed to be the slowest.

Observed useful negative control: chr01 hifiasm's longest 74,747,777 bp query
produced zero PAF rows and finished in about 6–8 seconds across profiles. Its
windows were also fast. That is `NO_SLOW_WINDOW_FOUND`, not an optimization pass.
An explicit-alias follow-up probes chr01 query 1 rather than silently selecting
only successful examples.

Observed useful hotspot: chr03 flye query 19's first/middle 250 kb windows take
4.32 / 8.23 seconds at current m200/n100; original defaults exceed the 10-second
window cap. U50,100 takes 1.52 / 1.62 seconds but preserves only 43.05% / 45.52%
of strong pair/strand query coverage versus current-n100, and loses some pairs.
This is substantial sensitivity loss, not equivalent output or ground-truth
accuracy. It is not accepted as a new default merely because it is faster.

## Short follow-up sensitivity matrix

`self_hotspot_matrix.py` uses those two fixed real windows and immutable full
index; profiles current-n100, U50,100/500/1000 and rmq-inner100/0. Two rounds reverse
profile order on one node. Each mapping has a 15-second deadline; the whole job
has a 600-second outer deadline. This replaces hours of full inputs for early
candidate elimination, NOT the final full-data test. It reports raw PAF identity,
>=5kb / >=90% identity merged query coverage per pair/strand, and missing pairs.
Any promising setting still needs full-query and downstream validation.

## Coverage and remaining gates

- Seven focused local tests: whole-record boundaries/order, zero-hit completion,
  corruption rejection, duplicate-query rejection, CPU/memory admission, bounded
  window selection, timeout descendant cleanup and PAF comparison schema.
- Synthetic actual-minimap2 end-to-end: exact output, cache reuse and one-batch
  recomputation. Real-sequence short fixtures: speed/sensitivity discrimination.
- Still open: real full-record batching exactness, actual interrupted-batch resume,
  representative scheduling makespan benefit and downstream acceptance. Existing
  24-task scheduler / full-query sensitivity / full workflow runs remain parallel.
- Step2 gap-screen remains disabled by default. No new self tuning flags are
  exposed; existing hidden compatibility parsing is unchanged.

No broad frontend/CI/browser tests were run for this maintainer-only experiment.

## Completed calibration and short-matrix outcomes

- 40587719: longest chr01 negative control, succeeded, 48.3 seconds in harness.
- 40587720: chr03 real windows, succeeded, 274.0 seconds in harness.
- 40587727: chr01 explicit query 1 (56,839,171 bp), succeeded, 270.9 seconds.
  Its 250kb windows take 4.22–9.08 seconds at current-n100; original defaults
  exceeded 10 seconds. Both this whole query and chr03 query 19 exceeded the
  45-second cap in all three profiles. This confirms isolated-query cost on
  these probes, NOT the historical 39.7/46.2-hour per-process cost per query.
- 40587733: two-window, two-round six-profile matrix succeeded in 137.08 seconds.
  U50,500/1000 was byte-identical to current-n100 on these two windows but gave no
  convincing repeatable improvement. rmq-inner0/100 changed PAF, retained 100%
  strong coverage on the first window and about 98.32/98.33% on the middle one,
  without a convincing speed gain. U50,100 was clearly faster but again retained
  only 43.05/45.52%. No sensitivity candidate is approved from these measurements.

The older x86/16 full self-m200-n100 job 40550763 also succeeded at
2026-10-16 14:29:34 +08:00 (scheduler elapsed 16h58m41s); workflow success and
Full/Light archives were observed. This is the older pipeline, NOT a timing of
query batching or adaptive dispatch. The newer x86/ARM whole workflows and GRT
customer suffix trials were still running at the 14:39:51 snapshot.

User scheduling update: subsequent 180 tests prefer ARM. Existing x86 jobs remain
untouched. These just-completed x86 microbenchmarks were launched before that
update and pinned the same 2.30-r1287 tool as the original experiment. Future
cross-architecture/tool-version results must be kept separate from controlled
same-tool speed ratios.

## Production adoption after bounded hotspot

Whole-record query batching is now generated by `assign_chr_groups.py` and run by
`tools/self_alignment_batches.py`; it is no longer validation-only. Adaptive
profiled task admission is enabled for chromosome-local Minimap2 manifests. The
final exact-source ARM evidence and deferred-full-test boundary are recorded in
`adaptive-batching-hotspot-20261016.md` and its JSON ledger.
