# Official reference-index and query-batch experiments (2026-10-16)

Status: **submitted, results pending**. The user explicitly authorized these three
component experiments, not a resumption of the deferred full test suite.

## Scope and provenance

- Repository source at submission: `af5e6c3`; the physically separated repair
  engines remain unvalidated. This harness imports neither engine and does not
  certify the refactor, downstream repair decisions, packaging, or a release.
- Harness: `grt_official_index_benchmark.py`, SHA-256
  `fe73cc0636e3e7c2de602825af8e67b7698b1d47a2a10cc506db8492a44373da`.
- SSH `180`, x86 port `18084`; dedicated Donau compute jobs, 8 CPUs each.
- Experiment root:
  `/share/home/xbzhang26/cgat-reads-debug/grt-official-index-20261016`.
- No changes to existing customer/historical runtimes, checkpoints or caches;
  original inputs are read-only. New outputs use a fresh experiment directory.
- No unrelated unit tests, frontend builds, full pipeline runs or code CI are
  requested by this experiment. Existing full workflow controls are untouched.

## 1. nucmer suffix-array reuse

Job **40587362**, sharing input/baseline work with experiment 2 below.

Two complete real Q1 query chromosomes and eight intact original reference
partitions from the previous bounded cold-component selection. The selection
includes the original largest target, 60,358,002 bp. Each selected partition has
one original record; multi-record partitions and all 489 partitions are outside
this initial experiment. Exact target FASTA bytes are checked against the saved
original partition hashes. Nucmer uses `-c1000 -l100 -t1`; filtering remains
`delta-filter -l10000`, `show-coords -r -l`.

Profiles:

1. Current `--batch=500000000` baseline.
2. No `--batch`, without saving/loading: isolate the compatibility prerequisite.
3. `--load` from independently built official `--save` indexes, no `--batch`.

A readable empty query file permits build-only timing with the official CLI;
there is no synthetic matching workload. Retain and hash the actual index file
set rather than assume a file extension. Count index build separately and in
cold totals. Warm load time is explicitly not a free first-build speedup.

Checks: every chromosome’s complete coordinate fields **in original partition
and within-query row order**, plus unordered rows as a separate diagnostic. A
failure of the ordered comparison is not rescued by an unordered pass. Compare
the new baseline with the previously frozen cold numerical coordinates too.

## 2. Batch query chromosomes per original donor partition

Same job **40587362**, same reference/query roles, exact record names, flags and
filtering. Query records are combined in **one** multi-record FASTA; reference
partitions are never merged. Two query worker threads per partition and four
concurrent partitions retain the same total 8-CPU budget as eight separate
single-thread nucmer calls. Test both current-batch and saved-index batch routes.

Outputs are split by original query name and restored to the original reference
partition aggregation order. Exact ordered coordinate comparisons are required.
No claim of final Q2/Q3/evidence equivalence follows from these raw-coordinate
checks alone. Two query chromosomes do not establish an eight-query speedup.

## 3. Step3 refill minimap2 index reuse / same-round batching

Job **40587363**. Both completed real refill rounds, eight chromosomes per round,
with exact original flank query bytes and the full actual donor target. Verify
target SHA-256 against the donor metadata, and ensure query names are unique.

Pinned runtime is minimap2 `2.30-r1287`; mapping remains `-x asm5 -c`. All
profiles use 8 mapping threads, with serial per-chromosome calls in the baseline:

1. FASTA target, separate chromosome calls (baseline).
2. Compatible `-x asm5` `.mmi`, separate chromosome calls.
3. FASTA target, one combined query FASTA per round.
4. Compatible `.mmi`, one combined query FASTA per round.

Build a fresh index for each round; no unverified cross-round index sharing.
Record build time, mapping time, cold total, index size, CPU time and per-command
peak RSS. Candidate order is reversed in round 2, with a fresh baseline first.

Checks: baseline against original evidence, then **all PAF fields and optional
tags**, including MAPQ, CIGAR, primary/secondary markers and per-query hit order.
Split combined PAF by original IDs and restore each chromosome’s query-record
order. Do not weaken the criterion to final FASTA equality or unordered hits.

## Measurement boundary

One initial pass per nucmer profile, two distinct real refill rounds. This is
correctness qualification and indicative component timing, not a statistically
stable performance estimate. File-system cache is not flushed, profile order can
affect timing, and index reuse and batching avoid overlapping work. Do not add or
multiply their reported speedups, or extrapolate them to whole-pipeline runtime.
The JSON report retains commands, logs, per-process timings and failure data.

## Step2 gap-screen: clarification of the evidence contract

The screen selects which original donor partitions receive full-query alignment.
Partitions excluded by the screen produce no full alignment/candidate trail.
That changes more than a rejected-candidate row count: candidate/rejection
records, evidence, donor-usage audit rows, and attempt/strategy statistics can
change. In particular, `usage.tsv` includes `candidate` and rejected outcomes as
well as `consumed`; its row count is **not** the count of actually used donors.

The previous customer test `40586902` found:

| Checked item | Full baseline | Anchor-safe Step2 screen |
| --- | ---: | ---: |
| Evidence rows | 117636 | 82004 |
| Usage audit rows | 15298 | 10516 |
| Q2 FASTA and 64 normalized source path segments | same | same |

Attempts/strategies also differ. The last row does not establish equality of all
accepted repair event fields, every reason/classification, all later stages or
unseen datasets. The screen remains **off by default**, outside the three
index/batching experiments. The user has asked for an explanation, not consented
to changing the GRT evidence/recall contract. Self-only accuracy relaxation is
not permission to relax GRT correctness.
