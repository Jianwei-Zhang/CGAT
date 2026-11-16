# Internal adaptive mapping: JM19 evidence and implementation gates

## Objective

Automatically identify expensive initial-reference alignments and trade bounded
sensitivity for useful throughput. Users must not have to choose filters, window
sizes, or determine when to switch. This supersedes the earlier explicit-only
filtering product direction; it does **not** justify deploying unmeasured defaults.
Keep ordinary/small workloads cheap, all input records accounted for, completed
work reusable where scientifically compatible, and every effective policy visible
in the report. First validate small real workloads on SSH 180 ARM; do not launch
full CGAT as a parameter search.

## Evidence from this incident

The supplied JM19 report and `cgat_bugreport_327664.tar.gz` identify two separate
costs: ordinary mapping completed in 240983.989 s (66.94 h, CPU/wall 3.11, peak RSS
224.668 GB); the following long-query window pass did not complete before user
cancellation. `-K 1G` was already active. Ordinary-part parallelism was declined
because other reference-mapping siblings were not excluded. The long record is
289508469 bp; the existing core=50 Mb, context=100 kb policy makes six windows.
The 8.27 Gb / 12-record index in the stalled log is the first original reference
part, not the entire 14.47 Gb / 22-record reference.

No raw performance sampling identifies the expensive minimap2 function yet.
README observations of zero output and CPU consumption locate a long calculation,
not a proof of deadlock or of a particular chaining/DP cause. Do not infer per-query
times from batch completion log intervals. Uploaded data readiness is not proven by
unchanged file size alone: obtain a completed source inventory and verify SHA-256
on transfer, preserving the source read-only.

## Trigger placement

1. Input catalogue: separate the existing packed-operation length route from
   performance classification. Large reference plus long query records requests
   a bounded assessment; size alone never chooses stronger filtering.
2. Before expensive ordinary mapping: use the original index and calibrated
   workload evidence to choose the effective policy. Repeat-heavy load and measured
   cost matter; species/filename and nominal requested threads do not decide it.
3. Runtime: an unfinished unit may escalate within a finite budget only with
   compute-tail evidence. I/O waits, OOM, malformed input and quiet PAF output alone
   must not trigger sensitivity reduction. Completed units are not replayed.
4. Results: questionable coverage, target attribution and structural evidence get
   bounded local review; sample apparently confident results too, because pruning
   competitors can make ambiguity disappear.

The initial implementation below is the **calibration milestone**, not yet wired
into Server execution. Production classification thresholds, bounded escalation,
local review, mixed-policy publication and migration remain required work.

## Calibration components

- `adaptive_screening.py`: deterministic pilot gate, per-query coverage/target
  risk checks, speed/quality comparison and policy-aware receipt identity.
- `benchmark_adaptive_screening.py`: small COMPLETE ordinary records against the
  FULL original reference; one default index; fixed K1G; default / f0.005 / f0.01
  followed by reverse order. Same-policy repetitions must have identical PAFs.
- `test_adaptive_screening.py`: trigger separation, hidden losses/ambiguity,
  timeouts, cancellation of subprocess descendants, and evidence requirements.
- `catalog_adaptive_inputs.py`: read-only streaming plain/gzip FASTA inventory;
  validates gzip to EOF, counts records/lengths/N bases, and records per-sequence
  and decompressed-file SHA-256 without loading whole chromosomes in memory.
  Run it on allocated compute resources, after transfer integrity verification.
  Six local tests cover gzip/plain parity, truncation, long unwrapped lines,
  invalid/duplicate records, no-final-newline inputs and output overwrite refusal.

The internal gate's 5 Gb reference / 20 Mb longest-record boundaries are explicit
**provisional experiment values**, not validated runtime defaults. The experiment
may be invoked on small controls even when the shape gate returns `standard`.
Do not extrapolate its timing to wheat or use its gate as a sensitivity change.
The calibration command is a maintainer tool, not a new user-facing option.

Example (inside the allocated ARM job, on a selected ordinary-query subset):

```bash
python3 -B benchmark_adaptive_screening.py \
  --target /verified/full-reference.fa --query /verified/ordinary-subset.fa \
  --out /new/experiment-directory --minimap2 /pinned/2.31/minimap2 \
  --threads 8 --memory-mib 131072 \
  --case-seconds 600 --total-seconds 2400 --execute
```

Memory is an explicit per-process address-space cap, not reserved RAM. Request
sufficient scheduler memory/CPU before running (Donau arm has a per-core memory
limit); do not assume eight requested CPUs grant 128 GiB. ARM smoke uses four CPUs
and an 8 GiB cap. The total deadline bounds index/mapping subprocesses, not input
cataloguing, hashes or output auditing; report those overheads separately before
claiming end-to-end speed. Candidate output >64 MiB is an explicit audit failure,
not truncated accepted evidence. Whole input files are never modified.

## Evidence rules

- `timeout`, `tool_failure`, `launch_failure`, `audit_failure`, and `cancelled` are
  not mapping success. A timed-out baseline provides only a speed lower bound;
  it cannot approve candidate quality. Partial PAF is never assessed as complete.
- An unchanged effective `mid_occ` cannot establish a filtering improvement.
- Count POSITIVE per-query coverage losses; gains elsewhere must not cancel them.
- Retain zero-hit queries and inspect per-query losses, lost mappings, confident
  target flips, lost assignments and ambiguity hidden by removing alternatives.
- Preserve full-row, CIGAR, geometry, target/strand and MAPQ difference summaries.
  Coverage stability does not certify biological accuracy or downstream safety.
- Provisional expanded-test gate: >=2x per paired run, <=0.5 percentage points of
  summed positive coverage loss over all input bases, <=2 percentage points on
  each query, and no flagged assignment/mapped-query/ambiguity risk. Both orderings
  must pass. Prefer the less aggressive eligible filter. These thresholds are
  experimental budgets, not established accuracy guarantees.
- All-unmapped baselines and missing repeat evidence never authorize selection.
- The receipt includes policy, input content, tool/code hashes and effective
  options. A different scientific policy cannot silently reuse a previous output.

## Required next gates (not complete)

1. Confirm upload completion and authentication on the actual upload endpoint;
   copy to an isolated 180 input root with source/destination SHA-256 evidence.
2. Catalogue actual files; do not assume `wheat3contigs` describes record count.
   Build source-coordinate manifests for representative difficult/easy controls.
3. Run bounded ordinary filtering pilots and long-window 50/10/5 Mb comparisons
   on SAME query spans and original reference parts; hold other factors fixed.
4. Include the complete long-record route: window mapping, whole-query chains,
   native chain-state collection, recovery and final selection. Faster windows
   alone are not acceptance. Verify architecture-matched native companions.
5. Calibrate automatic classification; integrate before costly mapping. Add
   finite runtime escalation, result-risk review and per-unit scientific identity.
6. Verify new inputs, interrupted/resumed tasks and old completed ordinary outputs;
   preserve valid completed work without mixing incompatible filtering policies.
7. Verify targeted ordinary sets plus the complete 289.51 Mb record before full
   reference alignment; only then consider full CGAT.
8. Once production implementation passes scientific/performance gates, synchronize
   generated Server runtime, run required tests/CI and close Server-only publication
   under RELEASING.md. This experiment-only milestone does not refresh a release.

## Validation checkpoint — 2026-11-16

- Local adaptive tests: 23 passed, including real subprocess timeout and orphan
  cleanup checks. Existing ordinary suite: 80 tests, 77 passed / 3 skipped because
  local pinned-tool prerequisites are unavailable; skips are not acceptance.
- ARM job `41728533`, node `agent-ARM-35`: SUCCEEDED, exit 0. Remote adaptive plus
  existing filtering tests: 32 passed. Six real minimap2 2.31-r1302 mappings on
  deterministic synthetic inputs completed. Every effective mid_occ was 50;
  all four comparisons correctly refused to select a stronger filtering policy.
  This validates the harness, not a wheat speedup or the proposed size thresholds.
- Remote evidence: `~/cgat-reads-debug/adaptive-screening-20261116-v1/`, including
  `SHA256SUMS`, `smoke/screening.json`, `tests.log`, `smoke_41728533.out`, `job.exit`.
  Uploaded payload archive SHA-256:
  `0ee449aa0169542df9d4ad88e34df84a5817c2fc2209b2c34bc97aa5f5dfca72`.
- User confirmed upload completion on SSH alias `142`. Inventory contains three
  gzip FASTAs, totaling 13222366280 compressed bytes. The uploaded reference is
  `Triticum_aestivum.IWGSC.dna.toplevel.fa.gz`, **not the KN9204 reference from the
  six-day incident**. New strategy comparisons must use the same uploaded reference
  for both arms and must not be reported as replay of the original KN9204 run.
  Transfer completed at 2026-11-16 17:59:35 +08:00. All three destination
  SHA-256 values match the source inventory; source metadata remained unchanged.
  Verified input root on 180:
  `~/cgat-reads-debug/jm19-adaptive-20261116/inputs/wheat3contigs/`.
  `TRANSFER_VERIFIED.json` in the parent experiment root records the content
  verification; that root is owner-only. SHA verification does not by itself prove
  gzip/FASTA validity or that this is the original KN9204 incident input.
- Read-only gzip/FASTA catalogue jobs submitted on ARM (2 CPUs each; 1800 s cap):
  hifiasm `41741137`, flye `41741141`, reference `41741147`. Submission is not
  completion. Record counts/content matching and real-data calibration remain
  pending. No full CGAT or full reference alignment has been started.
