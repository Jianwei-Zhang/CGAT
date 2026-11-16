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


### Exact base-check I/O optimization and real old-runtime resume (22:10 update)

The corrected profile `41872603` SUCCEEDED on ARM-12, 21:14:47–21:24:32.
It reconstructed the completed ordinary part-0 owned and stitched PAFs byte for
byte without executing a mapper. Fresh reference normalization took 288.33 s;
recovery/stitching took 145.31 / 109.43 s under cProfile. There were 5,655,910
`BufferedReader.read` calls, consuming 223.36 s of profiler-attributed own time.
This identifies a concrete small-read problem, especially on reverse CIGAR
traversal; it does not justify removing any nucleotide checks.

`windowed_alignment.checked_statistics` now uses at most 1-MiB sequential slabs
per sequence cursor, normalizes/orients each slab once, and still checks EVERY
`=` and `X` and recounts ambiguity in `= / X / I / D`. No CIGAR, coordinate,
placement selection or confidence policy changes. The implementation is embedded
in the existing runtime file: no additional production module dependency.
The independent scalar oracle was retained in tests, with 600 randomized
both-strand/indel/IUPAC cases across five buffer capacities, invalid-base and
truncated-store controls, and a logical operation above 2^28 with bounded reads.

Unprofiled paired replay `41885245` SUCCEEDED on ARM-20,
21:38:32–21:53:31 (1 CPU / 4 GiB). It reused source stores only after fresh
source/spool checks and processed exactly the same completed ordinary part-0
raw PAF in order scalar / buffered / buffered / scalar:

| Implementation | Wall seconds | CPU seconds |
| --- | ---: | ---: |
| Scalar first | 249.624 | 54.246 |
| Buffered first | 204.778 | 8.498 |
| Buffered second | 172.575 | 8.687 |
| Scalar second | 235.135 | 52.234 |

Paired wall improvements are **1.219x / 1.363x**, NOT a whole-pipeline speedup.
Both owned and stitched outputs are byte-identical in all four runs. Shared-file
I/O still dominates wall time; the larger CPU reduction is not a wall-time claim.
Preparation with validated reusable stores was 31.58 s and is reported separately.

- Report: `buffered-postprocess-replay-v1/replay.json` under the same ARM root.
- Immutable payload SHA-256:
  `28f616592d153f75d57c3620b928c2f7cceb34fc281314748a009954862a31f5`.
- Owned PAF SHA-256:
  `8027c260c61fd46f33ec7b58c8a11fbea45a474dca5f0aae7a631ad612c0f5d1`.
- Stitched PAF SHA-256:
  `5a119f2bc31501958b1857ef2ec7cd1e1a886efcdd6fac8cdea30b08865c199e`.
- Embedded canonical cursor/function ASTs match the frozen ARM prototype after
  removing type annotations/docstring (the experiment used a standalone helper).

Resume admission is deliberately narrow: the reviewed full-runtime profile pair
AND the exact old/new `windowed_alignment.py` hashes must match. Other recovery
kernel changes are still rejected. Eligible old payloads must still pass their
normal content/output integrity checks; migration does not bless receipts alone.

A real three-process local lifecycle used the pinned minimap2 2.31 and native
companion, not just relabeled new-source artifacts. All 29 old runtime files
were read from commit `7b2a302`, profile
`aa0bb89f9812cd64ad2d02c8e835369b8ba39eba0f021f90bea8390e70149b01`.
The OLD code completed ordinary mapping, the index, source stores and one long
cell, then an injected interruption stopped the second cell. Only runtime sources
and the reviewed manifest pair were updated. A NEW process using profile
`dccfca050f54e57cc769559ae227dfd2863d532ea55b64f08557a7e6c38a18db`
ran only the missing long cell; old index/store/ordinary PAF/first-cell PAF kept
both SHA-256 and nanosecond mtime. A third process did ZERO mapper/index calls,
reused both cells and reproduced identical final PAF bytes. Evidence:
`/tmp/cgat-buffered-real-migration-halqt841/{old,new,again}.json`.
The five new metadata migration controls also passed (33 metadata tests total).

### Complete long-record budget outcome; do not discard completed mapping

The earlier 16-CPU pending job `41847059` was verified unstarted with no output
root, cancelled and confirmed terminal before replacement. Its scripts and
scheduler receipts remain preserved; this was resource replanning, not a timeout
retry. Replacement `41876085` requested 8 CPUs / 40 GiB on ARM, retaining the
36-GiB mapper cap, 5-Mb windows, default filter, both original index parts and a
2,700-s process-wide budget. It ran on ARM-25, 21:23:44–22:08:48, and correctly
terminated FAILED at the total wall budget. Frozen payload SHA-256:
`7aed4d3b25520847ed76fa80cac056726d69e520ace04163fda879bb9c225405`.

Both original-part mapper calls actually completed with exit 0 and all 58
windows: 244.515 s / 323.159 s. Part 0 completed base checks/stitching in 332.38 s,
with 285,474,364 / 289,508,469 bases covered (coverage, NOT baseline retention).
Part 1 mapping finished at 21:40:39; its scalar base-check/ownership stage finished
at 22:03:14, then stitching was interrupted. The experiment uses the OLD scalar
verifier; live payloads were not mutated. Fresh preparation cost 343.78 s.

There is NO complete two-part final result and NO accepted long-record speedup.
A later postprocessing-only continuation may admit the SUCCESSFUL mapping
substage after explicit command/tool/index/window/input/traversal/integrity checks;
it must not read the partial stitched PAF or treat the failed parent as success.
No full assembly rerun or new filter sweep is warranted by this timeout.
Automatic production routing, bounded review/escalation, mixed-policy provenance,
per-unit resume and end-to-end acceptance remain unfinished.

Canonical/runtime synchronization completed (34 files checked; only the two
runtime sources and their manifests changed). Full alignment experiment discovery
completed **669 tests in 179.73 s, OK, one explicit skip**: the separate post-DP
native-source oracle was not configured with an unmodified source checkout.
Pinned-tool/companion resume controls ran, rather than being skipped. This is
controlled regression evidence, not customer or release acceptance. Official
published Server/App artifacts were not changed.


### Complete 289.5-Mb projection, without repeating either mapper (22:43 audit)

Postprocessing continuation `41901666` SUCCEEDED on ARM-38,
22:14:38–22:40:34, with 1 CPU / 4 GiB and a 2,700-s process budget. It admitted
the two SUCCESSFUL mapper substages independently (exit 0, exact native commands,
all 58 windows, original index part hashes, regenerated window FASTA equality,
source identities and complete PAF geometry), not the failed parent as a whole.
It reused the already completed part-0 output and reconstructed part 1 from its
complete raw PAF. The previous partial stitched PAF was NEVER consumed. The
reference sequence store was reopened with fresh content checks; no mapper ran.

Measured continuation stages:

| Stage | Wall seconds | CPU seconds |
| --- | ---: | ---: |
| Source/substage admission | 113.552 | not separately recorded |
| Part-1 raw checks + ownership | 710.962 | 59.472 |
| Part-1 stitching + checks | 677.576 | 38.708 |
| Entire continuation, including final checks | 1553.684 | not separately recorded |

These are **postprocessing continuation timings**, not a cold complete invocation
or a paired speedup over the original KN9204 six-day task. Original mapping on
this IWGSC reference had already completed in 244.515 + 323.159 s. Shared-file I/O
still dominates postprocessing; simply requesting more CPU cores will not remove
that measured bottleneck.

Final report: `full-postprocess-continuation-v1/continuation.json`.
Final PAF: `full-postprocess-continuation-v1/reference.approximate.experimental.paf`.
SHA-256: `e188be167d498a14467bca393a1712a1070d3d11b513da1b86f00a907e1ecce6`.
It contains 29,324 rows, original query ID/length 289,508,469, unknown MAPQ255,
and no inherited AS/ms/s1/s2/cm/tp tags. Both original reference parts are present.
Independent downloaded-output geometry/hash/profile checks passed.

Union query coverage is 287,355,731 bp (**99.2564% of input length**, NOT retention
against a complete native baseline). Current assignment is 3D, positive strand,
anchor 115,382,288, with 285,133,649 qualified supporting bases (98.489%).
Candidate-only screening finds no obvious assignment risk; no complete full-query
native accuracy baseline exists. Whole-query native confidence was not restored.

As an additional cheap check, the UNMODIFIED assignment compiler's actual AST
region (candidate aggregation and assignment generation, with its real interval
union/weighted-median functions) was executed over the downloaded PAF. Sequence
objects supplied only lengths because that region reads no bases. It reproduced
the same 3D/positive/anchor/support result. This is actual consumer-core evidence,
NOT execution of the full FASTA-partitioning/prepared-workspace pipeline.
Consumer source SHA-256:
`b80dce79100195f98c1a8f69c8afd4e3f0d4751b0cb2f4ff8efddb682ba2a0ae`.
Downloaded evidence and audits:
`/tmp/cgat-jm19-complete-results-7s_ky9qh/`.

### Automatic bounded native-source selection now produces a complete pilot PAF

`adaptive_complete_sources.py` implements the next executable boundary:

- Trigger evaluation uses the FULL workload catalogue, not the small pilot's
  longest record. The 19,960,671-bp pilot record alone would incorrectly appear
  below the provisional 20-Mb shape threshold; the full wheat workload contains
  the 289.5-Mb record. A size trigger still requests calibration, not sensitivity
  reduction by itself.
- Prefer the weaker filter only when BOTH complete repeated measurements meet
  the existing 2x candidate speed floor, repeated outputs agree, and complete
  record fallback passes the measured loss/assignment/direction checks.
- Bound fallback to 32 records AND 5% of pilot query bases. This is an internal
  provisional calibration budget, not a user-facing knob or a proof of future
  review cost. If the budget or speed condition fails, select complete default
  native output instead. A timeout speed lower bound cannot authorize selection.
- Materialize exactly ONE verified full source per query, preserving within-query
  row order, all selected chromosomes/strands and native row bytes. Never append
  baseline rows to candidate rows for the same query. Explicitly record complete
  no-hit queries, source row numbers, per-record hashes and the selected policy.
- Recheck actual pilot/reference input bytes and record-level sequence digests
  against the original workload. Nested subset extraction is valid when content
  matches; an intermediate catalogue's different metadata link is not a veto.
- An available completed second baseline may be used when the first timed out;
  the timed-out PAF is not read. Source mutation, receipt read/hash races, unknown
  sources and failed output checks cannot publish a final experimental PAF.

Initial frozen job `41906610` completed the ordinary selection, then refused the
micro subset because it had been extracted from the ordinary subset rather than
directly from the full catalogue. This exposed an unnecessary direct-parent
metadata restriction, not bad sequence data. That restriction was replaced with
fresh complete-record sequence membership checks (with negative content-change
controls), while preserving the first job's output and all original artifacts.

Corrected job `41908564` SUCCEEDED on ARM-35, 22:40:08–22:40:31, using 1 CPU /
2 GiB and a 600-s process budget. It executed NO mapper and completed in 18.935 s:

| Completed pilot | Internal choice | Actual selected sources | Rows |
| --- | --- | --- | ---: |
| Four ordinary records, 33.46 Mb | f=0.01 | first three filtered; weak short record entirely default | 7308 |
| Two-record micro control, 3.49 Mb | default | both complete default records | 721 |

The weaker f=0.005 did not meet the paired speed floor on the ordinary pilot;
the micro pilot had no sufficient candidate speedup. These choices were computed
internally, not passed as filter arguments. The resulting PAFs passed output and
baseline-relative quality checks. Source fallback is already completed in these
controls; **hybrid runtime speedup and future review overhead are NOT measured**.
Full original workload data is NOT claimed revalidated by this bounded finalizer.

Ordinary selected output SHA-256:
`c6ffd43d617713c26f9ae159072936ce2f5747747ef0a9154afafde3e3fcf0f5`.
Micro/default output SHA-256:
`e5c02c176e70dcfd3b3e58926d3ddb61b67af68ccadcf0d2c8bab5abbc98b8f3`.
The actual assignment compiler core retained all three ordinary chromosome/
orientation assignments; anchor changes were +272 / -49 / 0 bp. Qualified
assignment support changed even where total union coverage improved: approximately
+0.635 / -0.801 / -0.605 percentage points of the respective query lengths.
Thus this is not a zero-loss or unchanged-support claim.

The auditor is now `adaptive-screening-v3`: it explicitly reports qualified
support deltas and also applies the existing 2% per-query loss cap to a retained
assignment's supporting bases. Unqualified short hits can no longer conceal a
large support loss while leaving the raw union and chromosome name unchanged.
A negative control preserves 100% raw union and the same chromosome but drops
qualified support from 100% to 70%; it is rejected and selects the complete
baseline. The existing global 0.5% budget still refers to raw positive query
coverage losses, not a sum of potentially overlapping multi-chromosome supports.
Selection identities include the quality-policy version.

### Remaining production closure (not replaced by the successful controls)

The new source selector is not yet the default Server executor. Remaining work:

1. Pre-execution workload routing and pilot-cost amortization: do not spend a
   multi-condition pilot on a small job merely because one record is long.
   Separate packed-CIGAR correctness routing from ordinary throughput calibration;
   honor existing explicit run settings without making users choose the trigger.
2. Execute bounded ordinary units and limited review, measuring COMPLETE hybrid
   cost. Preserve already completed compatible ordinary/exact-recovery work.
3. Write successful mapping-substage receipts with output hashes BEFORE expensive
   postprocessing, then resume only missing units. Cancellation/resources and
   failed partial-output exclusion must cover the new path, not only the old one.
4. Admit complete all-part approximate projections via a distinct publication
   contract with unknown confidence; do not smuggle them through the existing
   native-confidence reconstruction verifier. Preserve full original identities,
   per-query/per-cell policy provenance and honest unresolved-risk handling.
5. Validate the actual automatic prepared-workspace path and downstream outputs
   on bounded representative cases before full customer-scale execution/release.

No full assembly parameter sweep or new full assembly mapping was launched.


Final v3 source-selection replay `41912289` SUCCEEDED on ARM-40,
22:54:44–22:55:03, in 16.385 s. Both internal choices and both final PAF hashes
were unchanged from v2; the ordinary receipt now exposes qualified-support
changes of +63,593 / -159,811 / -18,078 bp. All are inside the declared per-query
support budget. The micro result reports no support change. No mapper executed.
Payload `automatic-source-tools-v3` SHA-256:
`926a7a07612f424081b3049fdba227bc6f77831fe7cea695dcd43b11159320e1`.
Reports: `automatic-complete-sources-v3/automatic-selection.json` and each
case's `selected-sources.json`. This payload contains the final selector/auditor
sources, including repeat-1 baseline fallback and receipt-snapshot checks.

Validation: 19 new source-selector/publication tests, two new qualified-support
controls, and the complete related adaptive/audit/catalogue/extraction group:
**96 passed, zero skips**, including pinned-minimap2 projection controls.
A broader discovery before the two final v3 policy controls passed 688 tests
with one explicitly unavailable native-source oracle skipped. Generated Server
runtime sources remain synchronized and unchanged by this experimental selector.
Production admission/default execution and release closure remain outstanding.


## Automatic Server long-record integration (2026-11-17)

The generated Server source now contains the separate
`bounded_native_window_projection_v1` admission contract. This is source-tree
integration, not a published release or complete wheat acceptance. Ordinary
filter calibration remains experimental and is not silently enabled by this work.

### Internal trigger and finite work

- Only the prepared initial-reference `asm10` path opts in through its packaged
  runtime contract. No customer size decision or new CLI option is required.
- Preserve ordinary native mapping. The approximate branch applies to records
  already routed as over the packed-operation limit (268,435,455 bp), when the
  normalized reference is at least 5 Gb. A 20-Mb ordinary record alone does not
  trigger this long-record branch. Smaller-reference exact recovery is unchanged.
- Use 5-Mb owned cores with 100-kb context, ordinary native window candidate
  selection, and each ORIGINAL serialized index part's inherited occurrence
  threshold. This does not substitute `-P` enumeration, a target subset, or a new
  global f=0.01 default. Every original query/part cell, including empty cells,
  must complete before a full-record projection can be admitted.
- Per-cell mapper budget: 900 s; full cell invocation: 2700 s; raw PAF ceiling:
  64 MiB; mapper address-space ceiling: 36 GiB, or a lower explicit limit.
  Completed raw mapping and ownership stages are sealed before later work.
  A later interruption reuses those stages rather than repeating the mapper.
- Screen ALL parts of a query together. Low support, ambiguous assignments or
  orientation, near-threshold support, and dispersed same-target anchors request
  one complete-query native review, capped at 600 s each / 1200 s aggregate per
  invocation. A failed review is not retried automatically and its partial output
  is never published. A completed review REPLACES all candidate cells of that
  query; baseline and candidate rows are not concatenated for the same query.
- Projected rows have MAPQ 255 and no fabricated AS/ms/s1/s2/cm/tp values. The
  separate geometry/base-check contract cannot be relabeled as native-confidence
  recovery. No native C-API helper is needed for fresh approximate cells. Legacy
  completed exact cells retain their existing native-evaluated output and proof.

### Anchor-coherence screen and measured cases

`adaptive-screening-v4` adds block-weighted 10th/90th anchor positions for each
orientation. For each assigned target, the dominant orientation's span divided
by the full query length must not exceed 0.20; missing evidence requests review.
This is a provisional risk screen, NOT a proof of native global-candidate recall.
Minority-orientation rearrangements do not alone trigger this dispersion rule.

Two actual pinned-minimap2 controls expose failures that union coverage misses:
(1) many separate local competitors preserve 100% union but lose the global
chromosome assignment; (2) local repeats on ONE target preserve 100% union and
one orientation but yield incoherent placements. Both automatically trigger the
bounded native review and publish its complete bytes instead of the projection.
The positive, reverse-strand, multipart/empty-part, input mutation, failed review,
cancellation, closed-native-contract and zero-remapping resume controls also pass.
The focused suite has 13 actual-tool Server tests and 52 policy/runner tests.

Re-auditing the completed 289,508,469-bp wheat projection (same final PAF SHA-256
`e188be167d498a14467bca393a1712a1070d3d11b513da1b86f00a907e1ecce6`)
under v4 gives target 3D, query union 0.9925641623 and dominant anchor span
fraction 0.0067711871. It has no newly detected assignment risk. There is still
NO complete native baseline for that record, so this is not an accuracy estimate
or a customer end-to-end speedup claim.

### Prepared entry and source-upgrade continuity

An isolated real `prepare.sh` workspace executed its generated `command.sh`
(only fixture routing thresholds scaled down), then the actual generated
`assign_chr_groups.sh`. The outputs assign the 4-kb short record and two 90-kb
forward/reverse records correctly, including assignment FASTA partitioning.
This is not validation of the entire downstream LGZ/final archive workflow.

Real separate-process source migration executed the old buffered runtime
`dccfca050f54e57cc769559ae227dfd2863d532ea55b64f08557a7e6c38a18db`,
interrupted after one exact long cell, and then ran the new source. It retained
ordinary output, index, sequence stores and the completed exact cell unchanged,
executing exactly ONE mapper for the missing approximate cell. A subsequent
process ran zero mapper/index/guidance commands and preserved the final PAF.

A further real upgrade from the initial automatic-window source profile
`4d9244c3be38d5df7796d2917b73738859ab502b367a1c70fcf939b1d610bfab` to
`88e14005c9a1786dc257662106552cb6c20b898e0a943bd3b5088d1ed6e9ba89`
recomputed the v4 screening, executed ZERO external commands, and preserved the
published bytes. The reviewed migration pairs are exact file profiles, not a
blanket module whitelist. The v4 quality screen is not bypassed by an older
cached screening decision.

Still open: ordinary automatic pilot execution/amortization and measured complete
hybrid cost; real large-reference execution through this Server entry with normal
thresholds; downstream customer-scale validation; published Server release closure.


ARM Server-entry smoke `41981280` SUCCEEDED on agent-ARM-06 on November 17,
01:02:16–01:02:22 CST, requesting 1 CPU (5-GiB queue limit). The actual adapter
plus zero-remapping resume took 2.236 s on the small fixture. All 31 runtime file
hashes match the reviewed `88e14005...` profile. The fresh ARM route required NO
native C-API companion: its package explicitly kept the old confidence-recovery
contract closed while enabling the separate approximate geometry contract.
The run used the same pinned ARM minimap2 2.31-r1302 as the wheat experiments,
SHA-256 `03f361d0b8dba343adb6067fbdc109719196ef0e2619ba02c5295826dcec56dc`;
the installed module version differs and was not substituted in this control.
Output SHA-256: `f2adf1c9b13e21c13c7dcaf38490988f14cf1cc792786cd2cf7b51e56b72baa1`.
Scripts, payload checksums and receipt are preserved under
`server-automatic-smoke-v4/` in the existing remote experiment root. The fixture
uses reduced routing/window thresholds, so this proves ARM entry/resume execution,
NOT real large-reference workload completion or a speedup measurement.

The complete long-query discovery at this source profile passed **710 tests** in
179.456 s, with one explicitly unavailable native-source oracle skipped. Pinned
minimap2 and the audited portable x86 companion were present, so the actual-tool
Server and native-bridge controls ran. An earlier full run observed one transient
native trace query-end mismatch; the unchanged check passed in an isolated repeat
and subsequent complete discoveries. Its cause is not established. Failure-tail
diagnostics were added to preserve future evidence, not to waive that check.


Real-size adapter job `41996964` was submitted and confirmed RUNNING on
agent-ARM-20 at 01:10 CST (start 01:09:04, November 17). It uses the complete
14.55-Gb IWGSC reference and ONLY the original 289.5-Mb query, with NO routing or
window threshold overrides. Its 8-CPU allocation is needed for the 36-GiB mapper
address-space ceiling within the ARM queue's 5-GiB/core limit; total shell budget
is 7500 s. No full-assembly run or parameter sweep is involved.

The harness imports only verified reference preprocessing: fresh source/spool,
whole-index and original-part hashes; original index build command/receipt;
current MMI record/extents validation. It hardlinks these read-only contents into
a fresh private attempt and records `preprocessing-adoption.json`. It does NOT
import/relabel old mapping receipts or claim that a new index build executed.
Mapping, ownership, stitching, admission and zero-mapper resume are exercised by
the actual new Server adapter. This job is NOT yet a completed result at this
checkpoint. Artifacts: `server-full-long-v4/` under the existing remote root.


## Ordinary automatic pilot executor (2026-11-17, subsequent work)

Server integration commit `dd9f25da2045aef3e577be7e143ca4cc6e3bb6df` passed
quality run `43915822136` (Windows app and Linux server). The separate local
Server gate passed 472 Python tests with one skip and all eight shell tests;
its explicit LGZ-to-App E2E opt-out was NOT treated as full acceptance. CI ran
the canonical gate without that local opt-out.

`automatic_ordinary_pilot.py` now performs the actual finite native calibration
that the older completed-source selector did not execute. It is not yet wired
into the default ordinary Server mapping path. This distinction matters: a
successful pilot is not permission to launch or accept a whole assembly.

### Trigger and cost control

- Keep packed-operation-limit routing separate: ordinary records exclude those
  above 268,435,455 bp. An explicit filter is honored, not replaced by calibration.
- The ordinary experiment requires an actual reference >=5 Gb, >=1 Gb of ordinary
  queries, and at least one ordinary record >=20 Mb. These are internal defaults.
- Choose the base-weighted median complete ordinary record, then short/mid-size
  sentinels near 0.5 / 3 / 20 Mb, all in original source order. Total pilot cap:
  128 Mb. Do not replace an oversized dominant representative with a convenient
  tiny record, or slice it into synthetic windows to satisfy the cap.
- Require ordinary workload bases >=64 times pilot bases. This is a conservative
  size-amortization gate, NOT a forecast of runtime or proof of representativeness.
- At most six native cases; 1200-s per mapper invocation and 4800-s cumulative
  calibration budget, with actual verification/cleanup costs accounted in the
  ledger. Child PAF cap is 64 MiB; address-space ceiling is 36 GiB or a lower
  explicit limit. Original full-index mapping and first-part threshold semantics
  are preserved; no extra index build or reference-subset mapping is introduced.
- Try the weaker filter first. A first completed case that misses the 2x floor
  or exceeds the complete-record loss/review budget does not get another repeat.
  A promising case must have two completed speed comparisons and byte-repeatable
  outputs before selection. A slow/timed-out case cannot become a speed proof.
  Once the weaker candidate passes, do not execute the stronger candidate.

Actual hifiasm size distribution confirms why a tiny-only pilot is inadequate:
ordinary records above 20 Mb account for 9,971,444,644 bp; total ordinary sequence
is 14,296,624,798 bp. The automatic selection from the full audited catalogue is:

| Complete query | Bases |
| --- | ---: |
| ptg000045l (base-weighted representative) | 42,677,883 |
| ptg000159l | 19,960,671 |
| ptg000321l | 2,987,303 |
| ptg001708l | 500,479 |
| Total | 66,126,336 |

This is 0.4625% of ordinary query bases (216.2x workload/pilot ratio), not an
assertion that all contig lengths will have the same speed or loss characteristics.

### Preserve useful work and never mix partial sources

Complete native cases retain their original command, completion/traversal proof,
PAF hash and measured time. Resumption revalidates these receipts rather than
rerunning the mapper. An interrupted/failed case is not automatically retried;
a hard-killed unsealed case conservatively consumes its reserved budget. If the
native receipt actually completed before the interruption, resume can validate
it without executing another mapper. A corrupt completion is rejected, not
silently remapped or promoted from a partial PAF.

Input materialization retains original whole-record bytes, including headers,
case, wrapping and order. Plain FASTA units use verified catalogue byte extents;
gzip extraction verifies the complete decoded source. Completed units are reused.

Selection writes exactly one whole source per original pilot record, including
explicit complete no-hit records, with source hashes and per-query row hashes.
Default and candidate rows are never appended together for the same query.
Current quality profiles are recomputed from completed PAFs rather than trusted
from a stale decision cache. No synthetic full-native receipt is manufactured
for the selected composite.

Validation: 22 targeted controls pass, including actual pinned-tool completion,
zero-remapping resume, cancellation, source mutation, incomplete native timeout,
hard-kill receipt recovery and complete no-hit accounting. Two decision/composition
controls use explicitly SYNTHETIC times/profiles over actual PAFs; they are not
performance measurements. Final related discovery passed 731 tests in 177.768 s with one
unavailable native-source oracle skipped. The input-copy path avoids rebuilding
the selected-name set for every catalogue record; all 22 focused tests also pass
on this final source.

Still required: real automatic calibration result; bounded future ordinary units
and finite review of those units; measured complete hybrid cost; default Server
integration/admission with existing completed ordinary work preserved. No pilot
result here is claimed to prove whole-customer scientific acceptance.


Additional final controls require the complete query count WITHIN EACH original
index part: an equal grand total cannot hide a missing second part. An entirely
uninformative completed baseline now retains its no-hit sources without spending
any filter trials. These checks do not change mapper inputs or reinterpret failed
PAF bodies as evidence.

Real automatic ordinary calibration job `42029896` started on agent-ARM-33 at
01:35:18 CST, November 17. At 01:40 it was confirmed RUNNING in native calibration;
input/index verification and complete-record extraction took 106.697 s. It uses
8 CPUs for the 36-GiB mapper ceiling (40-GiB queue limit), with a 7500-s outer
budget, and the automatically chosen four-record 66.13-Mb pilot. The original
hifiasm gzip content and completed catalogue are checked, not just their mtimes.
No full assembly mapping or index rebuild is executed. Artifacts are under
`ordinary-automatic-executor-v1/` in the same remote experiment root.

The live producer was frozen before the final stricter per-part traversal and
uninformative-baseline checks above. Do not modify its sources while it runs.
Its completed receipts must ALSO pass the final verifier before accepting the
calibration evidence; this is a read-only/reuse audit, not a reason to rerun the
mapper. The final mapper recipe and input/parameter identities are unchanged.

At the same 01:40 observation, real Server long-record job `41996964` was still
RUNNING: original part 0 was completely base-checked and stitched; both original
parts had completed native window mapping (246.342 / 323.488 s). Part 1 was still
in postprocessing. Those mapper times are not full-task completion or speedup.

Frozen ordinary producer module SHA-256:
`7326be58c9333981d99755a93dc084def58a93b6d485d7f1488212cf10daee41`.
Final local verifier/executor SHA-256:
`fac14e97cdbfe419e07c75f83f4b6743e2687919581712787b18e10ae195cd12`.

A final checkpoint boundary control additionally verifies that preflight and
validation time is sealed BEFORE starting a native child. A hard kill cannot
erase that already-spent cost before the reserved child slice is charged on
resume. This adds one focused test after the 731-test complete discovery; it
changes no mapper arguments or successful source bytes.


## Real automatic Server long-record completion (2026-11-17)

Job `41996964` SUCCEEDED on ARM-20, 01:09:04–01:58:44 CST. It executed the actual
Server adapter with the FULL 14,547,261,565-bp IWGSC reference and the complete
289,508,469-bp ptg000049l query. No routing/window threshold override, native C-API
companion, whole-assembly run, or new reference index build was involved.

- Verified preprocessing adoption: 534.773 s. This includes fresh checks of the
  existing reference store and original index files, not a claimed new build.
- First adapter result, excluding adoption: 2368.206 s (39.470 min).
- First result including adoption: 2902.979 s (48.383 min).
- Same-source resume: 74.929 s, ZERO mapper/index commands, both complete cells
  and their sequence stores / original threshold metadata reused.
- Total harness elapsed including that explicit resume check: 2977.914 s
  (49.632 min), not a whole-customer pipeline runtime.

The adapter published exactly the previously base-audited PAF bytes:
`e188be167d498a14467bca393a1712a1070d3d11b513da1b86f00a907e1ecce6`.
The current remote result was downloaded and freshly hashed locally, not merely
inferred from a success JSON. All 31 runtime source hashes match the reviewed
`88e14005...` profile. The separate approximate contract was recorded; native
confidence reconstruction remained false. Complete query union is 99.2564%,
assignment 3D, dominant anchor spread fraction 0.00677119. These values remain
coverage/placement observations, NOT accuracy or native-equivalence estimates.
The uploaded IWGSC reference still differs from the original KN9204 incident;
there is no six-day-versus-49-minute speedup claim.

## Completed ordinary calibration and subsequent unit primitives

Job `42029896` SUCCEEDED on ARM-33, 01:35:18–02:18:04 CST. The internal policy
selected the WEAKER f=0.005 and therefore did NOT execute f=0.01. It used the
four complete automatically selected records (66,126,336 bp), not a manually
chosen sequence slice or a reference subset.

| Actual complete native case | Wall seconds |
| --- | ---: |
| Default baseline 0 | 885.965 |
| f=0.005 repeat 0 | 331.777 |
| f=0.005 repeat 1 | 342.192 |
| Default baseline 1 | 869.416 |

The two paired mapper ratios are 2.67036x / 2.54073x. Preparation/extraction cost
106.697 s; the COMPLETE calibration plus source selection and zero-remapping
resume cost 2563.445 s (42.724 min). Those four pilot executions are real startup
cost, not omitted from an invented whole-workload speedup.

The weakest short record lost 20,005 covered bases (3.9972%) under f=0.005, so the
selector retained its COMPLETE default source. The other three use the filtered
source. This is one source per query, not concatenated candidate/default hits.
Selected PAF SHA-256:
`1e528e748b7dd3439d0360ae9b378daac40dcc5e4a5b90022dfe4bc50f586fee`.
Qualified support differences remain visible: +536,794 bp for ptg000045l / 4A,
-36,218 bp for ptg000159l / 7D and +4,205 bp for ptg000321l / 1B; the 7D anchor
shift is -49 bp. No query/chr/orientation assignment was lost in the paired
pilot. This is still not a genome-wide accuracy guarantee.

A fresh, single-CPU read-only audit (`42054284`) was submitted after the producer
terminated. It uses the final per-part traversal verifier and reconstructs the
selected-source composition in original part/query order, requiring exactly the
same multiset of native rows and unchanged original producer receipts. Donau confirms SUCCEEDED on ARM-20 (2026-11-17 02:19:56--02:21:42 CST).
The audit itself took 102.091 s and passed without running a mapper. Its frozen
source hashes match the locally uploaded payload, and its original producer
ledger stayed byte-identical. A fresh download of the reordered selected PAF is
3,439,358 bytes with SHA-256
`8ab4453b0420d2948313d5fa9587df38cb79de81c4cf918d3516f99a442b5cb4`.
The hash differs from the producer selection because order is restored; the
audit requires the SAME multiset of native rows, and baseline-relative loss
checks pass. This is not additional calibration or whole-workload acceptance.

`adaptive_ordinary_units.py` adds the actual continuation primitives:

- Whole-record units target 128 Mb and at most 4096 records. An indivisible
  ordinary record may exceed that target; it is never silently split or omitted.
  Already completed pilot records are excluded from future units.
- Cohorts retain original within-cohort order. Plain FASTA uses catalogue byte
  extents; gzip is decoded at most ONCE to materialize all missing unit inputs,
  with at most two simultaneous output handles. It is not decompressed once per
  unit. Existing complete inputs are verified/reused rather than copied again.
- Native command completion is sealed BEFORE post-map verification. A cancelled
  verification resumes from the completed native receipt without remapping.
  Corrupt completed data refuses publication instead of triggering recomputation.
- New threads/K/memory requests do not invalidate completed native units; their
  original execution resources and native row bytes remain attached to them.
  Incomplete ordinary units can retry on a subsequent explicit invocation;
  bounded quality-review calls can forbid automatic retry. Attempt costs/history
  are retained instead of overwritten with only the last successful runtime.
- Composition requires disjoint, exhaustive complete-query ownership and the
  full original part/query matrix, including no-hit cells. It restores original
  part/query order and emits a separate source-composition contract, never a
  fabricated one-command native-success receipt or a quality approval.

Ordinary full-query review is deliberately distinct from approximate-window
review. The real 42.68-Mb native baseline itself has broad 4A anchors, while its
paired filtered result retains the chromosome, orientation and anchor. A window-
local coherence veto must not force that COMPLETE native-query result to rerun.
Ordinary risk screening retains low/absent support, orientation ambiguity and
both sides of the assignment threshold; it preserves multiple valid assignments.
The stricter window coherence rule is unchanged on the approximate-window path.
Review count/base reservations are cumulative over the original ordinary workload;
exceeding them stops filtered continuation rather than blessing unresolved data.

Still open: execute and validate bounded future units, actually perform limited
review/fallback on those units, integrate the complete ordinary controller into
the default prepared Server path, and measure complete hybrid cost. These new
primitives do not by themselves claim whole-assembly or downstream acceptance.


### Whole-unit checkpoint (2026-11-17)

Completed calibration adoption validates original full-record content, including
nested extracted catalogues, then retains the ALREADY PAID complete DEFAULT
pilot data for production continuation. The automatically chosen filter applies
to future units only; throwing away a complete default pilot source cannot save
any additional mapping time. Read-only adoption and completed unit audits must
not create a mapping command or rewrite the original ledger. Resource changes
are allowed only for future work and do not invalidate complete native units.

Bounded real continuation job `42066647` was submitted and observed RUNNING on
ARM-07 at 02:56:29 CST. It selects original-order unit zero, not a convenient
hand-picked record: ptg000001l (12,721,647 bp), ptg000002l (5,305,754 bp), and
ptg000003l (85,437,144 bp), totaling 103,464,545 bp. It uses f=0.005, the full
original IWGSC index, 8 requested CPUs, a 36-GiB address-space limit, and a
2400-second native command bound (3600-second outer job bound). It does NOT
map the remaining assembly. Frozen payload SHA-256:
`9f565fc49a4161a576affd087eb44695ffe91063ba41ad850dd7c05cf3b74ff0`.
At submission checkpoint no completed timing, quality review or final acceptance
is claimed. Its driver checks resource-change resume without new mapping.

Local validation: 752 tests passed (one optional source-oracle test skipped),
237.051 s. The preceding 750-test run exposed an intermittent existing native
projection log parsing error; five isolated reruns and the final full suite
passed. The exact cause is NOT established. The control now retains the real
stderr tail in assertion diagnostics, without relaxing any completion checks.
The generated Server runtime has not changed in this checkpoint: these ordinary
primitives are not yet the default production controller or a published release.


### Automatic ordinary controller (2026-11-17, experimental integration layer)

`adaptive_ordinary_controller.py` now connects internal size admission, finite
calibration, whole-record unit execution, limited native-default review and
complete-source composition. It is not yet called by the production Server
adapter; that hook and its publication contract remain an explicit next gate.

- Ordinary inputs below the admission thresholds and an explicitly supplied
  filter do not start calibration. Size alone never changes sensitivity.
- A completed external calibration and completed externally executed units can
  be adopted read-only by original complete-record content. Omitting/changing
  their bindings on resume is rejected BEFORE a new calibration command.
- Default-cohort units do not undergo filtered-result review. Each screened
  filtered query needing review gets ONE complete-record default run against
  the full original index. Once paid, that COMPLETE default source is retained
  regardless of whether the relative-loss report would also permit the filtered
  source; the two sources are never combined within a query.
- Review reservations are cumulative: at most the configured count/base fraction
  (defaults 32 records / 5% of the original ordinary bases), plus a separate
  finite review-time allowance. Reservation metadata is saved before launching
  work. Interrupted unsealed reviews are not automatically repeated; a genuinely
  completed native review survives cancellation before controller sealing.
- Exhausted allowances stop continuation WITHOUT publishing a partial result or
  launching an unrestricted whole-assembly baseline. This is a deliberate bounded
  experimental stop, not a complete production fallback policy yet.
- Complete-source composition happens only after every original ordinary query
  and index part is covered, including explicit complete no-hit records. Long
  queries remain owned by the separate long-record route.
- Resource changes reuse completed pilot/unit/review data. Original receipts are
  verified, not rewritten. Query identifiers are not used as filesystem paths.

Twelve focused tests use REAL pinned native commands on a small synthetic
fixture, with explicitly synthetic completed timing values only to exercise the
filter-selection branch deterministically. They verify complete/no-hit/default
ownership, cumulative count/base/time stopping, cancellation, read-only external
adoption, source binding checks before mapping, resource-only resume and bounded
prefix continuation. These fixtures are NOT performance measurements and NOT
customer scientific acceptance. The first real 103.46-Mb unit remains a separate
frozen job; the new controller is not injected into that running process.


Validation at this checkpoint: 764 tests completed in 239.879 seconds with one
optional source-oracle skip. After the final state-report cleanup, all 12
controller tests passed again in 10.580 seconds. The previously pushed primitive
commit `a23e6a7` also passed both Linux Server and Windows App Quality CI
(`43934576378`). No published Server package/runtime has been replaced by this
experimental controller.
