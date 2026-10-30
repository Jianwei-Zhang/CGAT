# Reverse split evidence and memory-budget adaptation — 2026-10-29

> Historical snapshot, not validation of the current branch. On 2026-10-30 the
> unknown-limit 128 MiB planning ceiling described below was removed: only a
> small read buffer is selected, while total budget/headroom remain unknown.
> Existing measurements and raw evidence are preserved unchanged; they do NOT
> validate that source correction or the current native recovery bridge. See
> `BRANCH_LONG_CIGAR_RECOVERY.md` for the unexecuted current implementation.

## Goal and scope

Adapt to different memory conditions, **not fill a particular customer's 500 GB**.
This phase implements a first, process-level planning layer for the experimental
trace reader, and extends the score witness to reverse-strand two-fragment cases.
It does not implement whole-job memory scheduling. No production Server, App,
minimap2 binary/source, customer isolation package or release asset was changed.

## Implemented process-budget policy

`trace_memory.py` reads current process virtual size from bounded Linux procfs
input and the process `RLIMIT_AS`. It combines an explicit trace-process budget,
when supplied, with the currently enforced (soft) address-space ceiling by taking the smaller value.
It subtracts current virtual size and a safety reserve (one eighth of the planning
budget, bounded to 2..32 MiB), then chooses a bounded read buffer:

- Auto: 8 KiB, 64 KiB or 1 MiB according to remaining process headroom.
- Explicit buffer target: up to 16 MiB, downshifted to a fitting tier when needed.
- Insufficient budget: fail explicitly before reading evidence; never omit seeds,
  lower alignment sensitivity, skip sequences or accept incomplete results.
- No known process ceiling: use a labelled **128 MiB conservative planning default**,
  not a claim about available hardware RAM. An already large embedding process may
  require an explicit budget; it is not allowed to assume the rest of the node.

The plan records sources, current virtual size, reserve, selected buffer and any
downshift. It does not change process limits, reserve memory or guarantee against
physical-memory pressure/concurrent allocations. `RLIMIT_AS` limits virtual address
space, not RSS or the aggregate job's RAM. Planning is a pre-allocation snapshot,
not a continuously rebalanced shared-memory scheduler.

**Not implemented:** discovery/accounting of shared Slurm/cgroup job memory,
other tasks' usage, aggregate pipeline reservations or adaptive minimap2 concurrency.
Those require a separate job-level integration. The reader intentionally does not
interpret node MemTotal or a Slurm environment variable as memory it owns.
A low process-memory footprint cannot prove a whole wheat alignment fits a small job.

The 512 MiB trace-file limit remains a separate workload guard, not a RAM budget.
Streaming can read more bytes than its resident footprint; file/time/line guards
must not be conflated with process memory. This audit still creates only small
synthetic biological fixtures; no full wheat collector is enabled.

## Different process limits: real measurements

Fresh opt-in Linux subprocess tests, CPython 3.12.3, same million-seed synthetic
trace and same scores/counts. The harness enforces each `RLIMIT_AS`; these are
**process address-space limits**, not tests on machines with that amount of RAM.

| Process address-space cap | Auto buffer | Streaming peak RSS | Result |
| --- | ---: | ---: | --- |
| 64 MiB | 64 KiB | 21.2 MiB | complete |
| 128 MiB | 64 KiB | 21.5 MiB | complete |
| 512 MiB | 1 MiB | 21.3 MiB | complete |

Under 64/128 MiB the frozen old collector runs out of its budget for the million
seeds; under 512 MiB both complete and full witness values match. Expected seed
counts remain 600000/400000 and scores 1200000/800000. 10,000-seed and
100,000-irrelevant-chain cases also retain the same semantics.

A 16 MiB explicit buffer at the 512 MiB cap raises reader peak RSS to 35.5 MiB;
this warm-cache run took 1.824 seconds versus 1.769 seconds for auto/1 MiB. This
single comparison does not establish a general speed difference; it supplies no
reason to automatically fill a large memory allocation with read buffers. It is
not a benchmark of the customer's filesystem or cold storage. File-cache memory
and other processes are outside this reader RSS measurement.

Pure policy and witness tests also cover 40 MiB, 4 GiB and 500 GiB planning budgets,
using a modelled current virtual size. **Those are simulated budget decisions, not
hardware or full-pipeline acceptance at those sizes.** A too-small budget is tested
to fail without modifying input or publishing partial evidence.

Reproduce real capped workers (new output directories):

```bash
python3 GPM2.0/experiments/long_query_alignment/benchmark_seed_trace.py \
  --out /tmp/new-adaptive-64 --memory-mib 64
python3 GPM2.0/experiments/long_query_alignment/benchmark_seed_trace.py \
  --out /tmp/new-adaptive-128 --memory-mib 128
python3 GPM2.0/experiments/long_query_alignment/benchmark_seed_trace.py \
  --out /tmp/new-adaptive-512 --memory-mib 512
```

`--read-buffer-kib 0` (default) selects auto. Explicit comparison targets are
8/64/1024/16384 KiB. The benchmark freezes the old witness from its recorded Git
revision and never runs minimap2 or reads customer FASTA.

## Reverse coordinate and score correctness

PAF query intervals are forward-coordinate half-open ranges. Reverse CN anchors
are in the query's aligned orientation: use `[query_length - qe, query_length - qs)`
for fragment matching. Target coordinates keep their ordinary orientation.
Use the **full query length**, not the aligned span, when transforming intervals.

Two-fragment score allocation follows increasing target/original-chain order,
not increasing forward-query coordinates. This matters even for integer rounding:
a controlled score=3, one-seed-per-fragment case must allocate 2 to chain head and
1 to tail. Reversing the association can assign those scores to the wrong fragments.
Tests explicitly reject that incorrect assignment and mismatched coordinate frames.

Fresh real minimap2 2.31-r1302 audit, original executable unchanged:

| Reverse decoy fragment | Forward query interval | Target interval | Seeds | Restored chain score |
| --- | --- | --- | ---: | ---: |
| Chain head | [14999, 199999) | [1, 185001) | 12927 | 146016 |
| Chain tail | [0, 13000) | [187000, 200000) | 1319 | 14899 |

The whole-query diagnostic oracle and independently recovered window fragments
agree on these seed counts and scores. Window CIGAR paths agree with the diagnostic
oracle; the AS-only false-positive counterexample remains visible. The exact case
passes its experimental guide, and both decoy cases still refuse incomplete
candidate recovery. Their final guided PAF is not created. General candidate
selection and MAPQ reconstruction remain false; recovered MAPQ remains unknown.

All previous forward PAF rows/tags, score hypotheses and refusal outcomes were
compared against the prior source-bound receipt and remain equal. No coordinate,
score, accepted mapping or raw PAF difference was hidden by normalizing metadata.

Reproduce the synthetic audit:

```bash
python3 GPM2.0/experiments/long_query_alignment/audit_post_dp.py \
  --minimap2 /absolute/path/to/minimap2 --query-orientation reverse \
  --trace-process-memory-mib 64 --out /tmp/new-reverse-score-audit
```

`--trace-process-memory-mib` only supplies a trace-reader process planning budget.
**It does not cap minimap2, the entire audit, or the Slurm job.** The surrounding
synthetic audit retains its separately specified minimap2 command limits.

## Tests and remaining gate

**85 tests pass on each of minimap2 2.26-r1175 and 2.31-r1302**: the prior 73 plus
six reverse tests and six memory-policy tests. New coverage includes asymmetric
reverse coordinates, target-order rounding, mixed-strand/identity rejection,
30 randomized reverse ownership fixtures, real reverse DP/window comparisons,
buffer-value equivalence, low/high budgets, lower hard-limit precedence, explicit
downshift, fallback provenance, measurable process size and insufficient budgets.

Receipts: `evidence/reverse-post-dp-audit.json` and
`evidence/reverse-adaptive-validation.json`. Raw runs remain under
`/tmp/cgat-adaptive-*-final-20261029`. Earlier receipts remain historical and intact.

Still unfinished: more than two fragments, general indel/join/repeat provenance,
complete parent/subalignment selection, MAPQ equivalence, job-level shared-memory
adaptation and customer acceptance. The customer is still using the unchanged
standalone isolation package; no new package or rerun is required by this patch.
