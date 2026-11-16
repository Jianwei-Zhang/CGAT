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

## Real-input catalogue and bounded pilot — 2026-11-16

All three catalogue jobs succeeded. Hifiasm has 2,377 records / 14,586,133,267 bp;
Flye has 35,890 records / 17,119,989,222 bp. Both **decompressed-file SHA-256s
exactly match the original JM19 incident report**, not merely sequence counts.
IWGSC has 22 records / 14,547,261,565 bp and is a different reference from KN9204.

`prepare_adaptive_subset.py` preserves original record bytes/order and reads the
source to EOF, verifying the complete decompressed-file digest plus selected
record hashes before publishing a new FASTA. Cross-node stat fields are audit
metadata, not content identity: shared filesystem device numbers differed (50 on
the catalogue node, 59 on the login node). Initial preparation jobs `41753592` /
`41753594` failed before writing data because the first helper compared those
numbers across nodes. Frozen v1 logs remain; v2 uses content validation and still
rejects changes during a read. Eleven local tests cover these contracts.

Successful preparations:
- Full original IWGSC reference: `41756953`, `derived/reference-v1/`.
- Four COMPLETE ordinary contigs: `41765306`, `derived/ordinary-v2/`.
  Source order: `ptg000126l` (10,007,359 bp), `ptg000159l` (19,960,671 bp),
  `ptg000321l` (2,987,303 bp), `ptg001708l` (500,479 bp). Total 33,455,812 bp.
  These are length-stratified controls, not yet demonstrated hotspot selections.
- Complete 289,508,469-bp `ptg000049l`: `41765309`, `derived/long-v2/`.

Ordinary filtering pilot `41767856` was submitted with successful-preparation
job dependencies. It uses the **full** IWGSC reference, fixed K1G and 16 mapping
threads in each arm, 32 allocated CPUs for the 128 GiB address-space cap under
Donau's memory-per-core rules, and default / f0.005 / f0.01 in both orders. The
index/mapping budget is 2,400 s total, 600 s per command. Catalogue and integrity
I/O overhead is outside that deadline and must not be hidden in throughput claims.
This is not a full assembly alignment or production policy enablement.

`benchmark_adaptive_windows.py` adds the second diagnostic: identical original
query span, 50/10/5 Mb cores with contextual overlaps, and one **whole original
reference index part**, copied byte-for-byte from the pilot index. It inherits a
measured fixed seed threshold for every size and preserves all-chain pooling to
isolate window-size effects. Coverage is counted only inside each disjoint core;
context overlap cannot inflate it. Six local tests cover ownership, edges, raw
base extraction and flank-only hits. A timed-out baseline gives only a wall-budget
lower bound, excluding cancellation cleanup time. Mapping coverage is NOT final
whole-query chain/CIGAR/confidence or biological acceptance; full recovery remains
an explicit later gate. Frozen ordinary-pilot v1 uses the preceding auditor version;
its timeout lower-bound timing must be interpreted with that cleanup caveat.

### Queue/resource adjustment and window smoke

At 18:29 the scheduler explicitly reported that `41767856` lacked a node with
32 available CPUs, with both preparation dependencies already satisfied. At
18:34, while still PENDING, the SAME job was modified (not cancelled/requeued):
`reqCPU=16`, `reqMem=65536 MB`, `limitMem=65536 MB`. Mapper commands still request
16 threads, with the unchanged 128 GiB **virtual address-space** cap; the scheduler
physical-memory limit is now 64 GiB. All paired comparisons will share that same
allocation. Resource failures remain failures, never automatic sensitivity changes.
The frozen script's original 32-CPU header is superseded by the scheduler receipt
and `ordinary-pilot-{memory-limit,resource}-adjustment.log`; do not infer allocation
from the script alone.

Window-probe ARM smoke job `41778683` uses a generated 6 Mb query with a complete
synthetic reference, exercising actual 1/1/2-window maps under 50/10/5 Mb cores.
It is separate from the customer workload and cannot prove wheat speedup. Local
adaptive/subset/catalogue/window suite currently has 47 passing tests, no skips.

### Policy v2: actual assignment-consumer risk and offline re-audit

The diagnostic's single-best-target heuristic is NOT the Server assignment
contract. `server/tools/assign_chr_groups.py` retains **every** chromosome reaching
60% coverage (the current fixture threshold), using only blocks >=1000 bp or >=25%
of the query. Orientation uses summed qualifying block lengths, with ties choosing
`+`; anchor placement is a weighted median. Consequently, deleting overlapping
negative-strand hits can flip downstream orientation while per-strand union
coverage remains identical. Policy v2 now records these actual projections and
flags removed assignments, newly added assignments for already assigned queries,
and changed downstream orientations. Anchor shifts are reported quantitatively;
no unmeasured universal anchor-distance accuracy threshold is asserted.

`test_adaptive_assignment_contract.py` executes the real Server interval/median
helpers and PAF-to-assignment loops on tiny controlled fixtures, without launching
the full assignment script. It cross-checks multi-chromosome retention, short-hit
qualification, the 60% boundary, block-weighted direction changes and anchors.
Coverage gained by previously weak/unassigned queries is not mislabeled as hidden
ambiguity. These are eligibility/review gates for further tests, not biological
accuracy guarantees.

`audit_adaptive_pilot.py` rechecks terminal pilot PAF hashes and geometry under the
current policy without invoking a mapper or rewriting the original report. Old
frozen job payloads remain unchanged. Old v1 candidate eligibility must be
re-audited before promotion; incomplete/partial PAF is never used as a baseline.
The auditor does not claim to revalidate the present-day source FASTA files.

Window smoke `41778683` SUCCEEDED on `agent-ARM-33` (34 s job wall). The three
window mapping calls took approximately 3.43 / 3.43 / 3.38 s and all retained the
same 6 Mb core coverage. This is a harness success and **not a demonstrated
performance improvement**. Its six completed filtering-control PAFs and report
were downloaded with SHA-256 checks and successfully re-audited with policy v2;
no filtering strategy was selected because effective thresholds were unchanged.
Local adaptive tests: 68 passed, no skips.

A separate cheap-probe calibration job `41813859` was submitted: two COMPLETE
ordinary records (`ptg000321l`, `ptg001708l`, total 3,487,782 bp), full unchanged
IWGSC reference, 8 CPUs / 32 GiB requested memory, 32 GiB address-space cap, and
1,800 s total index/mapping budget. Input extraction reuses the verified 33.46 Mb
subset rather than rescanning the whole hifiasm gzip. This evaluates future
preflight cost and does **not** replace the original larger pilot `41767856` or
the required full long-query validation. A separate index build in this calibration
must be counted as experiment overhead; no shared-index or end-to-end speedup is
claimed. Both pilot jobs remain authoritative handles to inspect, not reasons to
submit duplicate work while the ARM queue is busy.

At 19:09 the authoritative scheduler showed micro pilot `41813859` RUNNING on
`agent-ARM-20` (started 19:06:44); its 49 packaged unit/regression tests passed.
The larger `41767856` remained PENDING. These are not yet performance results:
the benchmark first scans and verifies the full reference before starting its
bounded mapping/index clock. Do not interpret the absence of an early mapping
receipt as a stalled or missing job and do not resubmit either handle.

### First real wheat micro-pilot results and next bounded long-window probe

Job `41813859` SUCCEEDED on ARM-20 at 19:20:48 on 2026-11-16 (started
19:06:44). The full default index built in 197.53 s; peak index RSS was about
26.08 GB. The two complete query records total 3,487,782 bp. All six mapping
calls completed against both original IWGSC index parts; same-policy PAF hashes
were repeatable across the forward/reverse run order.

| Filtering | First map (s) | Reverse-order repeat (s) | Effective mid_occ |
| --- | ---: | ---: | ---: |
| default | 75.70 | 74.99 | 500 |
| `-f 0.005` | 51.91 | 50.91 | 73 |
| `-f 0.01` | 48.75 | 52.11 | 50 |

Paired mapping speedups are only 1.44–1.55x, below the experimental 2x gate.
`ptg001708l` loses 20,005 / 23,706 covered bases (4.00% / 4.74% of its length),
although the other record gains coverage. Positive loss must not be cancelled
out by gains elsewhere: the corresponding positive-loss fractions of total
query bases are 0.5736% / 0.6797%. Neither candidate passes current experimental
loss limits. No projected downstream assignment, orientation or anchor change
was detected in these two records; that is not full scientific acceptance.
The report and all six PAFs were downloaded and their recorded hashes checked;
current-policy offline re-audit also selects no candidate. Do not loosen limits
merely to label this experiment successful.

The 14m04s scheduler duration includes full-source verification, indexing,
six maps and tests. It is NOT an acceptable universal preflight overhead for
small ordinary jobs. Future automatic admission must use original input shape
and measured task cost, reuse verified existing indexes, and avoid applying
expensive probes indiscriminately. This micro result does not establish the
behavior of the 289.5 Mb record or resolve the original long-window bottleneck.

Real-window diagnostic job `41824802` was submitted at 19:24 on ARM, with
8 CPUs / 40 GiB requested memory and a 36 GiB child address-space cap. It reuses
the completed micro pilot index, checks its SHA-256, and copies the original
serialized index partitions without repartitioning or rebuilding. It compares
50 / 10 / 5 Mb cores over the SAME first 50 Mb span of `ptg000049l`, against
original index part 0, with unchanged default filtering and `-P`. Each mapping
has a 600 s cap; the mapping/threshold budget is 2,000 s, excluding preparation.
Memory failure remains a resource result, not permission to reduce sensitivity.

Frozen payload: `real-window-tools-v2`, SHA-256
`55bafc8b4b0ccc074d76e8e8e369c1203319b66c78b2ec8575fd3d20d93818b5`.
Output: `real-window-default-part0-v2/windows.json` under the same private root.
This is ONE original reference part and ONE query span, not whole-query recovery
or end-to-end acceptance. The larger ordinary job `41767856` remained PENDING
at 19:23 and was not duplicated or cancelled. No production automatic sensitivity
policy has been enabled by these experimental changes.

### Complete-record native feasibility, and verified runtime insertion points

A second, distinct long-query hypothesis is now being tested: exceeding the
packed-operation length route is NOT evidence that this particular record must
fail native alignment against IWGSC. Job `41827114` was submitted at 19:30,
using the complete original `ptg000049l` (289,508,469 bp) and the already verified
22-record, two-part index. It runs default / f0.005 / f0.01 once each, fixed K1G,
8 threads, 600 s per invocation and 1,850 s total mapping budget. Request: ARM,
8 CPUs / 40 GiB; child virtual-address cap: 36 GiB. Preparation/hash time is
outside the mapping budget. It is not a whole-assembly CGAT run.

Frozen one-off experiment: `native-long-tools-v1/probe.py`; payload SHA-256
`fcfb0eba20d831361d4152ab09eb53d3039d51516be24c8ab1470bba4dfe6189`.
Report: `complete-long-native-v1/native-probe.json`. The script reuses reviewed
bounded-child execution, exact-assertion classification, PAF/CIGAR validation,
and assignment projection. Success requires complete traversal of BOTH original
index parts (12 + 10 target records), the full query in each, and unchanged index,
query, mapper and helper hashes. Partial/failed PAF is never usable. Source FASTA
is not re-read: the actual reused MMI content is verified against the completed
pilot receipt. A resource failure does not authorize a production filter change.
No repeated-pair validation or scientific/production approval is claimed here.

Current source inspection identifies the insertion points and constraints:

- `server_alignment.run_reference` obtains prepared explicit options and the
  live dispatcher resource context before calling `proactive_reference_alignment`.
  An explicit user filter must remain authoritative, not be silently escalated.
- `proactive_reference_alignment.experiment` currently binds one GLOBAL filter
  and window policy to the checkpoint. Ordinary-only inputs go straight to native
  mapping without reference normalization, index preprocessing or a companion.
  A universal eager-reference scan/probe here would regress the ordinary path.
- Mixed inputs build one original index, then complete the entire ordinary group
  BEFORE any long-query cells. Therefore a performance gate placed only inside
  the long-cell loop is too late to prevent the observed 66.94-hour ordinary cost.
- `proactive_publication.admit` currently requires the length-based native/long
  split, one inherited seed threshold, uniform window policy and an exact cell
  matrix. Adaptive native successes, per-record filters or different window sizes
  cannot be smuggled through the existing receipt by relabeling them. Their actual
  execution identities and admission rules must be extended together.
- Resume currently binds the global window policy. Merely changing the default
  core size would reject otherwise compatible completed ordinary work. The future
  migration must preserve completed native records and explicitly account for old
  completed long cells; no cache deletion or rerun of the whole dataset.

The micro-pilot logs also explain why its end-to-end speed ratio is not a direct
measure of alignment-kernel improvement. In the first run, sums of wall intervals
from each part's `mm_idx_stat` completion to its `mapped 2 sequences` event are
39.406 s (default), 15.750 s (f0.005), and 14.744 s (f0.01). These are observed
pipeline intervals, NOT per-query time or a function-level CPU profile. The rest
of each invocation includes index loading/setup/cleanup. Report the measured total
1.44–1.55x speedup, not the ~2.5x interval ratio as a customer/end-to-end result.
This supports amortizing setup and gating the cost of calibration, not enabling
a blanket filter after a short-record microbenchmark.

### Local-review feasibility from completed real PAFs (no extra mapper runs)

The micro loss needs its biological context reported accurately. Under default
mapping `ptg001708l` has 40,757 covered bases out of 500,479 (8.1436%) and no
qualifying chromosome assignment. Filtering reduces this to 20,752 / 17,051 bp.
The 2,987,303-bp `ptg000321l` has 2,851,437 covered bp under default and gains
coverage under both candidates. All three policies assign it to 1B, minus strand,
anchor 657330534. This does NOT prove the lost short-record hits are spurious;
it shows why a single aggregate loss percentage is not a sufficient decision.

An offline complete-record substitution was constructed for each candidate:
retain candidate rows for `ptg000321l`, retain default rows for `ptg001708l`,
and retain exactly ONE policy for each complete query across BOTH original index
parts. No fast/default rows were stacked for the same record, so duplicate hits
cannot artificially change coverage or block-weighted direction. Rows preserve
selected-source bytes within each original-part/query cell, ordered by original
index-part then original query order. Every selected source PAF hash was checked.

Both composite diagnostic PAFs pass native geometry/CIGAR checks and the current
coverage/assignment comparison against the default baseline. f0.005 composite:
885 rows; f0.01 composite: 901 rows. Reports and PAFs are stored privately at
`offline-record-review-v1/`, with `REVIEW_SHA256SUMS` verified after upload.
These are diagnostic artifacts only, never a published CGAT result. No mapper
was executed, source FASTA was not revalidated, and no hybrid runtime/speedup has
been measured. The result supports reusing a COMPLETED baseline for local review
instead of rerunning or rejecting every safe record; it does not justify a
production threshold, universal filter, or unbounded fallback computation.

A further runtime trap identified in source: prepared-workspace ordinary calls
explicitly set `native_args.timeout=None` to preserve old native behavior. A new
internal preflight budget must therefore be independent and explicitly enforced;
passing a timeout into the existing adapter alone would not bound ordinary work.

The review choice is now automated in `plan_completed_record_review`, invoked by
`audit_adaptive_pilot` only with completed, hash-verified, repeatable paired PAFs.
It first resolves per-record coverage/assignment/strand risks, then enforces the
positive-loss budget over the whole set without incorrectly imposing that global
limit on each record. If additional replacement is needed, greatest lost bases
are restored first with original-record-order tie breaking. This is a quality
ordering over already completed artifacts, not a remapping-time prediction.
Each query has exactly one selected source and its reason; source PAF digests are
bound into the report. Missing, failed, partial or nonrepeatable pairs cannot seed
this plan. A wholly unmapped baseline cannot establish its quality.

The automated plan reproduces the real offline result for BOTH fractions:
`ptg000321l -> candidate`, `ptg001708l -> baseline`, with no additional mapping.
It does not alter the pure-filter recommendation (still null), does not publish
a mixed-policy CGAT output, and does not claim a hybrid speedup. Production cache,
admission and execution integration remain outstanding. Local adaptive suite:
79 tests passed, including 11 added review-plan and paired-source regressions.

Scheduler update at 19:46: original larger ordinary pilot `41767856` is now
RUNNING on `agent-ARM-23`, started 19:45:16, with the previously adjusted
16-CPU / 64-GiB grant. The real-window job remains PENDING; its explicit scheduler
reason is insufficient available CPUs on a node, not a failed dependency or
mapping failure. Existing job handles remain in use; none was duplicated.

### Completed larger ordinary pilot, full-native feasibility and window policy control

The 33,455,812-bp ordinary pilot `41767856` SUCCEEDED on ARM-23, 19:45:16–20:12:06.
Every condition completed against both original IWGSC parts and same-policy PAFs
were repeatable. All six PAF hashes were checked after download and the frozen
v1 receipt was re-audited under the CURRENT assignment-aware policy.

| Ordinary filtering | Forward-order map (s) | Reverse-order map (s) | Paired speedups |
| --- | ---: | ---: | ---: |
| default | 294.94 | 292.69 | baseline |
| f0.005 | 147.83 | 155.84 | 2.00x / 1.88x |
| f0.01 | 138.10 | 139.41 | 2.14x / 2.10x |

The same short `ptg001708l` is the only record with net union-coverage loss.
The automatic completed-record review chooses its default result and the candidate
result for the other three records. This removes measured net coverage loss and
retains chromosome assignments/directions. Anchor changes are +272 bp on 6D for
`ptg000126l` and -49 bp on 7D for `ptg000159l`, under both filters; these are actual
reported differences, not an asserted universal accuracy tolerance. A hybrid runtime
has not been measured, and filtering alone remains insufficient for the long record.

Complete-record native diagnostic `41827114` SUCCEEDED as a DIAGNOSTIC at 20:10:02,
not as an alignment. Default aborted after 29.69 s with `[morecore] insufficient
memory`, return 134, under the 36-GiB virtual-address cap (peak RSS ~15.19 GiB).
This is allocation-failure evidence, not the targeted CIGAR assertion and not proof
that physical RAM demand equals the address-space limit. Both f0.005 and f0.01 hit
600-s caps. f0.01 logged completion of the first original index part, but the whole
invocation did not complete: NO partial PAF from any of these runs is usable.

All-chain window job `41824802` completed its DIAGNOSTIC at 20:18:16: ALL three
50/10/5-Mb-core invocations hit their 600-s cap. The aggregate scheduler evidence
shows 8,182 s user CPU plus 94 s system CPU over 1,912 s job wall, so this was not
merely idle queue time. It is not a function-level profile or per-window CPU timing.

A one-factor candidate-policy control, `41839608`, SUCCEEDED on ARM-21 at 20:02:27.
It keeps the same first 50-Mb query span, 5-Mb cores, 100-kb context, original part 0,
default mid_occ=500, mapper, 8 threads and 36-GiB address cap, but uses normal native
window candidate selection instead of `-P` all-chain retention. Its mapping completed
in 73.1467 s, CPU 299.18 s, peak RSS 24,558,588 KiB. All 10 windows completed;
546 raw rows cover 49,175,135 / 50,000,000 owned bases (98.35027%), on 3D, plus strand.

The paired reports were downloaded and checked: exact same window FASTA SHA-256
`a9e65fa51d3f00cdfd9bc19177a951798f06309eda0894049bbfa83d46b9b475`, original-part SHA-256
`8abbf954284f2ce3ec9fbc14007eb0ad1c261aab6a8fe4085fb5c23dea676c6a`, window boundaries,
query source, index receipt and all command options except `-P` (output/input file
locations differ). The observed budget ratio is >8.20x. This is ONE paired experiment
on different ARM nodes, not a repeated full-workflow speedup. The timed-out baseline
cannot establish a quality-loss rate; 98.35% is coverage of INPUT, not retention of
baseline alignments. No full native confidence or customer acceptance is inferred.

Frozen control payload `window-selection-tools-v1` SHA-256:
`b5e238cba0021db9359323ea55d99d0006e7fbb0a648612df37b148d3c363900`.
Verified comparison and ordinary re-audit: `completed-pilot-audit-v1/`.
The benchmark now supports a single controlled core size and candidate policy;
default behavior remains the original all-chain 50/10/5-Mb sweep. These are
maintainer experiment controls, NOT user-facing performance decisions.

### Complete approximate route: explicit scope, not fabricated native confidence

The user's approved sensitivity/speed trade permits a separate approximate
initial-reference route. It is NOT legitimate to call a fast window result the
old confidence-preserving recovery result. This alternative must complete ALL
windows of every original query across ALL original reference parts, base-check
CIGARs, clip overlapping context, restore full-record coordinates and lengths,
and audit actual downstream assignments. It deliberately does not reconstruct
whole-query chain state, native ranking or MAPQ. The existing exact-recovery
contract is not weakened or relabeled; if used, its companion/recovery gates still
apply. Full long-record and downstream acceptance remain mandatory either way.

The existing `windowed_alignment` native-selection route already emits unknown
MAPQ 255 and strips non-transferable native score/primary tags after coordinate
projection. Source inspection found an actual downstream issue: reference-evidence
anchor selection ranked 255 numerically above known MAPQ. A narrow correction now
ranks unknown below known values only AFTER the existing block-length/match keys,
without changing raw PAF or deleting hits. Its regression first failed on all
four known-0/known-60/order variants, then all six evidence-package tests passed.
The source fix is `3409eb2`; no release artifact or deployed customer tool was
replaced. The upstream minimap2 manual defines 255 as missing quality and `-P` as
retaining chains without primary selection. Normal small/native paths are unchanged.

Complete 289,508,469-bp projection job `41847059` was submitted at 20:15:
16 CPUs / 64 GiB physical limit, 48-GiB mapper address cap, 900 s per original part,
and a 2,700-s process-wide alarm including preparation and base checks. It reuses
both existing part files, verifies that their concatenated bytes hash to the
original full MMI, and does NOT rebuild or copy the 22-GB index. It uses default
filtering and 5-Mb native-selected windows, checks against original bases, and
combines outputs only after BOTH parts succeed. This path does not require running
an x86 helper on ARM; it executes no native-chain-state companion at all.

Payload `full-projection-tools-v1` SHA-256:
`5145b45cbc08313aeab9a5d650c6f1db0beee7dc8850916186ad105f3d2b37ee`.
Report: `full-window-projection-default-v1/projection.json`. It was still PENDING
at 20:21; no result or full-record speedup is claimed.

A separate quality control `41853392` was submitted at 20:29: apply the same
complete base-checked projection to the already verified FOUR ordinary records,
then compare to their completed default native PAF (no baseline remapping). It uses
8 CPUs / 40 GiB, 36-GiB mapper cap, 600 s per part and a 1,800-s process-wide alarm.
Every original part and every generated window must be logged complete. This
control provides an attainable complete native quality baseline; it does not
substitute for the full 289.5-Mb validation. Fresh normalization/base-check costs
must be counted separately from mapper-only timings, especially for small jobs.

Payload `ordinary-projection-tools-v1` SHA-256:
`c7d64935bb7e1660ad4ad7449e8c6777215e3dc932447f91ea191a32003feafb`.
Report: `ordinary-window-projection-default-v1/projection.json`.
Production automatic admission, finite escalation/review, resume/mixed-policy
publication and release closure are STILL NOT COMPLETE. No full assembly parameter
search has been launched.

### Full ordinary projection outcome, hidden ambiguity control, and overhead profiling

Job `41853392` SUCCEEDED on ARM-26 (20:30:38–20:42:40). Source/index hashes and
both completed part/window traversals were verified after downloading its report,
final PAF, leaf reports, mapping logs and manifests. Preparation took 363.50 s;
part processing took 264.24 / 91.79 s, while actual mapper calls took only
59.562 / 46.065 s. Total measured script wall was 720.77 s. Therefore it is NOT
a demonstrated faster replacement for the ~293–295 s ordinary native maps:
normalization/index validation/base checks can erase the mapper-only benefit.
Different threads/nodes and setup scope also prevent a clean paired speed claim.

All four projected records passed current baseline-relative coverage, assignment
and strand checks: no net query coverage loss or changed chromosome/direction.
Anchor shifts were -424 bp on 6D (`ptg000126l`) and -49 bp on 7D (`ptg000159l`).
All output MAPQs are unknown, not reconstructed. Candidate-only screening flags
only the weak/unassigned short contig for bounded review; absence of a risk is
explicitly NOT scientific approval. Local evidence directory:
`/tmp/cgat-jm19-ordinary-projection-result-ojhbtuqs/`.

Two new REAL minimap2 2.31 controls run the complete base-check/projection route,
including explicit original multipart layouts, forward/reverse coordinates,
full-length query identity and removal of non-transferable confidence tags.
The ambiguity fixture has one near-perfect global placement plus 64 perfect local
competitors per window (asm10's actual secondary limit is 50). Native mapping
assigns the full record to `global`; window-native selection has 100% union
coverage but NO chromosome assignment. The audit rejects this via
`assignment_lost` / `downstream_assignment_removed` and selects the completed
baseline. This is direct evidence that coverage alone cannot approve the new route.

`screen_candidate_projection` now automatically flags covered-but-unassigned,
low-support, multiple-target, near-threshold and direction-ambiguous results for
bounded review. It requires full-record assignment/strand evidence, preserves
multiple assignments, and never claims a clean-looking candidate is proven safe.
Current adaptive suite: 90 passed, no skips, with the pinned local mapper enabled.
No production runtime threshold was enabled by these screening additions.

A 1-CPU/4-GiB postprocessing-only profile reuses the completed ordinary part-0 PAF;
mapper calls are explicitly forbidden. It measures index catalogue/hash, original
sequence-store preparation, context validation, then cProfile of base-check,
ownership and stitching, requiring byte-identical reconstructed PAFs. Initial job
`41871765` was stopped after a detected launcher filename collision (`profile.py`
shadowed Python's standard `profile` module); scheduler confirmed FAILED at
21:14:20 after termination. No baseline mapping was repeated. Corrected job
`41872603` uses `replay_postprocess.py`, a separate immutable payload/output root,
and an 1,800-s process alarm. Import isolation was checked before submission.

Corrected payload `postprocess-profile-tools-v2` SHA-256:
`c558f0e7eefe9e3d8aa7e95fe7e9dac8b20df21988ab93e1c7f72952a1190057`.
Report: `postprocess-profile-v2/profile.json`. Completed normalized stores are
checkpointed for later compute-only replay if profiling supports an optimization.
The full long-record job `41847059` remains a separate live scheduler handle;
it was PENDING at 21:13. Do not replace it merely because observations expire.
