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
