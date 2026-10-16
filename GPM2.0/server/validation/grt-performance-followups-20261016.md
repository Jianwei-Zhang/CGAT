# Remaining performance opportunities (2026-10-16)

Status: **three official-index/query-batching component experiments authorized
and submitted; results pending**. See `grt-official-index-20261016.md`. The user
still defers nonessential code tests and broad integration/regression runs. These
are candidates, not implemented/validated production speedups. The physical
Step2/Step3 refactor remains untested; the standalone benchmark does not import
or certify it.

## Why the current headline improvement is small

- The 3912-task Step2 fixed-duration schedule simulation removes about 6.53% of
  modeled time, not the actual alignment workload. The 1.89x measured warm GRT
  execution improvement does not certify cold whole-pipeline speedup.
- Each of 8 query chromosomes is aligned against the same 489 original donor
  partitions in full Step2. Existing optimizations cache numerical coordinates,
  input FASTA, and parsed/indexed coordinates. They do **not** persist nucmer's
  reference suffix-array index (`--save`/`--load` are not in current commands).
- In the checked customer manifest, D0 targets total 2,370,944,571 bp and the
  largest individual target partition is 60,358,002 bp. Counts alone conceal the
  amount of sequence retained by a screen.

### Customer Step3 screen metadata

Read from already completed engine-080 artifacts on SSH 180, not a new run.
Query FASTA hashes for chromosomes 1 and 8 are unchanged between Q1 and Q2; the
validated full-query numerical caches can be reused there. Other chromosomes:

| Chromosome | Selected original partitions | Selected target bp |
| --- | ---: | ---: |
| BSWB01000002.1 | 226 / 489 | 1,707,871,713 |
| BSWB01000003.1 | 198 / 489 | 1,609,452,625 |
| BSWB01000004.1 | 231 / 489 | 1,728,695,691 |
| BSWB01000005.1 | 230 / 489 | 1,677,903,806 |
| BSWB01000006.1 | 218 / 489 | 1,688,887,586 |
| BSWB01000007.1 | 42 / 489 | 320,710,063 |

Across changed chromosomes, 39.03% of partitions but 61.39% of target bases remain.
For chromosomes 2-6, about 45.11% of partitions still contain 70.97% of target
bases. Base counts are **not CPU cost estimates**, but demonstrate why removing
half the partitions does not imply halving runtime. Screening also has its own
alignment/index cost before selected full-query alignments run.

## Priority 1: genuine reference-index reuse and multi-query nucmer work

### A. Same reference partition, multiple query records in one job

Keep the original 489 reference partitions, record order, flags and reference/query
roles. Instead of independently rebuilding the same reference index for each
chromosome, place query chromosomes in one multi-record FASTA for that partition.
The pinned nucmer 4.0.1 CLI supports multiple query **records**, parallelized by
`-t`. Do not pass multiple query file arguments for delta output: its CLI accepts
multiple query *files* only with SAM output.

This could reduce reference index construction/process startup from up to eight
per target partition per stage to one. It does not make eight query alignments
free or establish 8x speedup. Screened runs need grouping by selected query set;
query/window IDs must be unique and mapped back to original chromosome contexts.

Equivalence obligations for the unified test phase:

- Do not combine reference partitions or swap reference/query: default reference-
  unique seed selection depends on that reference scope.
- Split delta/coords by original query, restore original partition aggregation and
  row/tie order, and compare all candidates/rejections and Q outputs.
- Account for aggregate query memory and total threads rather than multiplying a
  per-chromosome CPU budget. Keep independent numerical-cache identities valid.

### B. Official `nucmer --save` / `--load`

Persist the reference suffix-array index by exact target FASTA content, nucmer
binary/version and index-affecting options. It can survive query changes between
Q1 and Q2, unlike an alignment-result cache, and can be shared by screen/full-query
work using the same reference.

Important: nucmer 4.0.1 declares `--batch` incompatible with `--save` and `--load`.
Current commands use `--batch=500000000`; simply appending a load flag is invalid.
The observed original partitions are all below 500 Mb, so a non-batched index
path is worth validating, not silently assuming equivalent. Reference-record
concatenation, coordinate offsets and default match uniqueness must remain intact.

Batching and saved-index reuse overlap in the work they avoid; do not multiply
or sum their estimated gains. Need index-build/load versus matching/extension
wall times and peak RSS in the later unified tests before estimating benefit.
No unverified `--time` flag is assumed for the pinned CLI.

## Priority 2: stop rebuilding the same minimap2 target for each refill chromosome

`step3_engine.run_refill_alignment` constructs all chromosome flanks, then calls
`stage_alignment.cached_chromosome_alignment` separately per chromosome. Within a
round the target donor FASTA is the same, but a cold miss invokes minimap2 on that
FASTA again. No `.mmi`/`-d` target-index cache exists in this path.

Two candidates, preserving the original mapping thresholds:

1. A content-validated `.mmi` cache, keyed by target bytes, minimap2 binary/version,
   and indexing options (`-k`, `-w`, homopolymer compression, split-index policy).
2. Map a round's chromosome flanks together, then restore per-chromosome PAF,
   query ordering and artifact provenance. This can build/load the target once
   rather than up to eight times and exposes more independent query records.

Round 1 and round 2 can have different consumed-donor subsets. Reuse is legal only
when exact target contents and options match; never assume one donor index for
both rounds. `.mmi` indexing options override later command-line requests, so
reusing an incompatible preset silently is unacceptable. The same mechanism may
help unchanged leaf/display targets, but their total runtime share is unmeasured.

## Priority 3: self-alignment needs an earlier complexity control than -m/-n

The inspected test runtime is minimap2 **2.30-r1287**, not an assumed newer release.
`-m`/`-n` are chain acceptance thresholds. They are not a bound on all seed or
chaining work performed before acceptance; a higher `-n` is not proportional
acceleration. The 2.30 assembly presets enable RMQ chaining, which also has an
inner dynamic-programming search controlled by `--rmq-inner`.

For self alignment only (the user approved an accuracy tradeoff), investigate:

- High-frequency minimizer filters: `-f`, `-U`, `--q-occ-frac`.
- Smaller/disabled RMQ inner DP via official `--rmq-inner`, checking the actual
  2.30 implementation and preserving legal PAF/CIGAR, not inventing alignments.
- Sparsifying seeds with self-only `-k`/`-w` only if needed; distinguish their index
  identity from reference/cross-dataset mapping presets.

These are not currently implemented or recommended numeric defaults. Leave
reference, cross-dataset and GRT parameters unchanged. `-N` is ineffective under
`-X`; `--secondary=no` is incompatible with `-X`/`-P`, so neither is a valid
shortcut for the current self command. Query-window parallelism
is a later fallback: it requires overlap, coordinate/CIGAR restoration and
repeat-hit deduplication, and may lose cross-window chains. More `-t` alone does
not split a single giant query record; the current scheduler already caps the
thread assignment by the number of query records.

## Optional higher-gain path requiring explicit acceptance of a different audit scope

Step2 gap-screen currently fails strict rejected-diagnostic equality, despite
matching Q2 and source paths on the tested customer/history cases. It is **not**
a validated strict-equivalent replacement and remains disabled by default.

The difference can include evidence/usage audit rows and attempt/strategy
statistics, not just a rejected-candidate count. `usage.tsv` records candidates
and rejected outcomes too; fewer rows do not mean fewer actually consumed donors.
Matching Q2 and source paths on tested inputs is not a proof that every accepted
event field, decision reason or unseen repair outcome is unchanged.

If the intended contract is exact final Q2/Q3/Q4, source paths and accepted repair
semantics, while the number of *unaccepted diagnostic candidates* may differ, a
separate fast mode can be revisited. This needs explicit user approval and full
accepted-event/classification/path validation, not just a FASTA hash. Do not
reinterpret the user's self-only accuracy permission as permission to change GRT.

## Deferred validation boundary

Following explicit user authorization, isolated official-tool benchmarks were
submitted as jobs 40587362 (nucmer index reuse and query batching) and 40587363
(refill minimap2 indexing/batching). No self-alignment-parameter experiment or
broad regression was added. No existing running job, cache, runtime or original
historical input was changed. Existing controls and prior result ledgers still
certify only their pinned source. Full repair/event/evidence equivalence and the
physical refactor remain for the later unified validation phase.

Primary upstream source references for the pinned versions:

- MUMmer 4.0.1: `src/umd/nucmer_cmdline.yaggo`, `src/umd/nucmer_main.cc` in
  `mummer4/mummer` (query records/threads, saved index, batch incompatibility).
- Minimap2 2.30: `minimap2.1`, `options.c`, `lchain.c` in `lh3/minimap2`
  (index options, occurrence filters, RMQ inner search and chain acceptance).
