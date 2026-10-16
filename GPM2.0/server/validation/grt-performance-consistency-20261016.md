# GRT performance and consistency validation (2026-10-16)

## Current acceptance summary (08:16 CST)

- Cache-lock engine `080599a3` at `d9deccf`: **10/10 historical dataset/scope
  pairs, 210 checks passed again**. The earlier `a6e85bd6` snapshot is retained
  below for chronology, not used to certify the fixed concurrent cache path.
- Customer-wide exact execution: **46 checks passed**, including full Step2
  Q2/source paths, original unreconciled candidate/rejection tables, complete
  baseline/optimized ordered diagnostics, gap-screen Step3 Q3/source paths,
  Step4 Q4, the complete Final Path document and exported DNA.
- Export boundary: baseline/optimized exports are byte-identical. Export versus
  Q4 differs only in preserved input letter case in chromosome 6; chromosome
  names/order, lengths and case-normalized DNA hashes all match. Production
  export case preservation is unchanged; this is not byte equality with Q4.
- Customer numerical-cold component benchmark (`a6e85bd6`): **4/4 passed**, mean
  22.67% wall reduction with identical 1212-row alignment streams. Not a
  full-pipeline ETA. The complete 3912-task Step2 fixed-duration schedule model
  suggests only 6.53% scheduling savings; a model, not a new benchmark.
- Customer Step2 gap-screen is **not strict-equivalent**; DNA/source paths match
  but diagnostic evidence/usage/attempt counts differ. Keep Step2 scope `full`.
- Local: **228 Server tests**, 19 focused tests, all 8 canonical shell groups,
  LF/syntax/whitespace checks passed. Quality run **38813019659** is green for
  Linux Server and Windows App. Defaults remain `full` + `baseline`.
- Remaining: original full-data skip-self/n100 cold workflows; completed-leaf
  customer delivery/report/archive closure; final CI/public source-asset refresh.

Machine-readable evidence: [grt-execution-results-20261016.json](grt-execution-results-20261016.json).
The chronological notes below retain failed variants and test boundaries.


Status: in progress; no performance-mode default change is approved by this record.

## Scope and acceptance

- Separate generated GRT Step2 and Step3 scheduler units, preserving the legacy
  combined Python entrypoint and legacy workspace refill-limit updates.
- Experimental `--step2-mummer-scope gap-screen` and
  `--step3-mummer-scope gap-screen` select donor partitions using local gap
  windows; selected partitions are rerun against the complete chromosome with
  the established nucmer/delta-filter/show-coords parameters.
- Default scope remains `full` pending consistency results. Recall of previously
  accepted evidence alone is not a complete equivalence check.
- Full-query raw-cache reuse requires all partition fingerprints and output
  hashes to validate, not merely the existence of the raw-cache directory.
- Check sequence SHA-256, path segments, events, evidence, donor usage, gap
  attempts, Step2 strategy branches and Step3 classifications. Compare omitted
  rejection diagnostics separately and report differences rather than hiding them.
- Historical input directories are read-only. Tests use isolated cloned
  workspaces under the existing campus test root, never the originals.

## Remote matrix

Host: SSH alias `180`, x86 login port 18084; compute jobs use Donau x86.
Artifacts: `~/cgat-reads-debug/` on 180.

| Dataset / task | Donau job | State at submission |
| --- | --- | --- |
| Customer 2665 Step3 frozen-Q2 equivalence | 40550897 | running |
| Customer 2665 Step2 frozen-Q1 equivalence | 40570141 | running |
| Small two-chromosome skill fixture, full/gap Step2+3 | 40566296 | PASS |
| 10g no reads, full/gap Step2+3 | 40568138 | running |
| 10g with reads, full/gap Step2+3 | 40568140 | running |
| test8 fixed, full/gap Step2+3 | 40568142 | running |
| Zebrafish, full/gap Step2+3 | 40568144 | running |
| Full customer pipeline, skip-self | 40550762 | running |
| Full customer pipeline, self m200/n100 | 40550763 | running |

The two skill fixtures have identical Q1/Q2/Q3 hashes; the newer fixture is the
representative test. The two test8 historical directories have identical hashes;
`test8-fixed-0408829` is the representative rather than duplicating the same input.
The no-reads and with-reads 10g packages are both included because their historical
Q3 outputs differ. Zebrafish covers a 1.4 Gb input with unchanged Q1/Q2.

## Test-snapshot boundary

The customer diagnostic export includes sequence/metadata baselines but omits
`grt/checkpoints` and raw Step2 artifacts. A test-only adapter verifies exported
FASTA hashes, donor manifest/registry/fragment consistency, and Q1 reconstruction;
it does not fabricate a donor-freeze checkpoint or weaken production validation.
The initial jobs 40565234 and 40567816 failed during harness preflight because
those exported artifacts were absent; neither produced a scientific comparison.
Raw candidate/rejection equality requires a same-engine full/gap run with full
artifacts; it cannot be claimed from an export that lacks those baselines.

## Local regression coverage

- Separate Step2/Step3 entrypoints reproduce combined-entrypoint Q2/Q3 hashes.
- Missing/changed Step2 checkpoint outputs are rejected before Step3 reuse.
- Incomplete unchanged-Q2 caches still use gap-screen; complete caches reuse every
  partition without launching nucmer.
- Both Step2 and Step3 screens rerun only selected partitions against full Q.
- Legacy combined-workspace `--max-fill` updates remain supported.

Results and final default decisions will be recorded after all remote gates end.

## Findings from the first expanded matrix

- All four historical real-input cases produced matching Q2/Q3 sequence hashes
  and source path segments. Their Step2 rejected evidence, usage diagnostics,
  attempt candidate counts or strategy counts did **not** all match; those jobs
  are recorded as failed strict comparisons, not promoted to full equivalence.
- The initial customer Step3 screen produced Q3 `e1bef525441915ed40a288216017afffeef687f2e1e9c6091613f510fa84796a`
  instead of the frozen baseline
  `a3899e8701f646acd4e07cec2489bce7902119f131c36ce09f9539e8bc7089f0`.
  The initial print bug was separate; checkpoint-only verification confirmed the
  real hash mismatch. This variant must not become the default.
- Root cause found in `_step3_anchor_pairs`: expansion stops when any left and
  any right anchor exist, before same-record pairing. Discarding a partition
  with only a nearby single-sided anchor can incorrectly expose a more distant
  pair. The revised selector retains all crossing or window-affecting anchors.
- A regression test reproduces different-record near anchors blocking a farther
  same-record pair; the screen must preserve that stop condition.

Anchor-safe engine: `4a427f8844a4c8c426bd49884897c33cd80e5a745fe74951227e4f6bec4b761b`.
New customer Step3 job: 40586881. Historical Step3-only full/gap jobs on identical
full-Step2 Q2: 40586882 (tiny), 40586883 (10g no reads), 40586884 (10g with reads),
40586885 (test8), 40586886 (zebrafish). These reuse numerical caches and are
consistency tests, not cold-runtime measurements. Split fresh/resume/fill-limit/
contract/package integration: 40586887.

Job 40586880 was cancelled during clone/cache setup before replacing any linked
runtime files; source runtime SHA-256 and modification times were checked
unchanged. Its replacement imports the pinned external engine without copying
over hard-linked runtime files. No original data directory is modified.

## 02:08 CST checkpoint

- The five anchor-safe Step3-only historical jobs all succeeded. Every checked
  Q3 hash, source segment, event, evidence, usage row, attempt and classification
  matched the full path. Their stage inputs are identical full-Step2 Q2 outputs.
- Real split integration 40586887 succeeded: 13 independent units for the two
  dataset/two-chromosome fixture, first run + resume + refill-limit update,
  unchanged Q2/Q3/Q4 hashes, contract validation and full/light archive checks.
- Full local Server suite: **219 tests passed** (91.795 seconds).
- The customer source snapshot and both full pipeline workspaces have identical
  Q1 SHA-256 `a7d85c35f42e1c4c6b386c29317c45efa663eef577dc83ea18d9cec5934e5970`
  and frozen D0 SHA-256
  `77fea663243cf4e58e68b5598c06300b2721703f37ae34df7523ca92aa6653de`.
  Their stage outputs can therefore be compared without treating different
  biological inputs as equivalent. Current customer tests remain running.

## 02:40 CST checkpoint

Customer Step2 job 40570141 finished its numerical work in 1h44m49s. Q2 SHA-256
matches the frozen baseline; normalized source path segments also match. Strict
metadata comparison fails: the baseline has 117636 evidence rows versus 24588
in this screen, and strategy/attempt counts and some unresolved reasons differ.
The exported baseline metadata has already undergone Step3 reconciliation, so
standalone Step2 event status differences also require that context to interpret.
The absent raw Step2 export cannot be used to claim raw rejection equivalence.

A revised Step2 test (40586902) uses the same anchor-safe selector as current
source, keeping the numerical caches from the initial test and compatible
completed raw entries from the full runs. It is a warm consistency test, not a
second cold speed measurement. Step2 remains `full` by default.

## Exact-execution optimization experiment (03:36 CST)

The user resumed the goal and approved feasibility verification/testing of five
additional execution-only opportunities. Both MUMmer scopes still default to
`full`; generated workflows keep `--execution-profile baseline` (implicit).

Experimental `--execution-profile optimized` implements:

1. One globally CPU/memory-bounded nucmer pool across chromosome coordinators.
   Screen and full-query tasks share the same pool, not one budget per chromosome.
2. Larger original target partitions first, without changing partition boundaries
   or original-order coordinate aggregation and candidate tie-breaking.
3. Exact Step2 top-two stable anchor lookups and Step3 coordinate/endpoint indexes;
   preserve the near one-sided anchor expansion-stop rule.
4. Content-addressed donor-partition FASTA inputs, validated before reuse, with
   ordinary donor manifest sidecars. No mutable workspace hard links are added.
5. Reuse the chromosome wrapper's already-validated coordinate parse. Directory
   copying remains unchanged and is timed separately; no unmeasured hard-link
   optimization or weaker artifact integrity check is introduced.

Pinned engine: `a6e85bd653222d530ee6959e6ac875c489059ad6378c1f1fff4ac21f4047c450`.
Exact-index helper: `2c7c6cb1f834245bcd8c64703cee2dffa2e9c99336bf42c7b06a38c9877b3bb1`.
Archive SHA-256: `f72ee31e1c1159c57326044db544cf6df86a168773a52b830d322db234dacb18`;
verified after transfer and before extraction. Engine/helper hashes also verified.

Local Server suite: **227 passed** (127.875 seconds). A separate cold fixture and
standalone comparison-harness smoke test passed Q2/Q3 file hashes, complete source
segments/events/usage/attempts/classifications, exact candidate/rejection table
order and evidence semantics. Only stage execution fingerprints and evidence raw
artifact hashes containing workspace-dependent coordinate headers are excluded.
Raw numerical-cache keys remain compatible. New focused tests cover global
concurrency (including one partition per chromosome), shared screen/full budget,
corrupt input repair, deterministic largest-first execution, cancellation and
randomized stable index equivalence with duplicate endpoints/identity ties.

Remote tests (all under `~/cgat-reads-debug/grt-execution-equivalence/`):

- **40586980**, 4 CPU: skill-v3, 10g without reads, 10g with reads, test8.
  Compare baseline/optimized execution separately for full and gap-screen modes.
- **40586981**, 4 CPU: zebrafish, same comparisons.
- **40586982**, 8 CPU: two customer chromosomes / eight intact original large
  donor partitions; four fresh numerical-cache runs in alternating profile order.
  Sampling is bounded to partitions whose observed baseline task time was <=180s.
  This is a component benchmark, not a full repair/pipeline speedup estimate.

The historical jobs also record a separate latest-selector full-versus-screen
semantic comparison. Differences there do not count as exact-profile equality
and do not authorize switching the scope default away from full.

Existing customer/full-pipeline jobs continue unchanged. Their outputs will be
reused for subsequent customer-wide exact-execution and delivery-chain checks.
Thirty-minute observation resumed; no existing compute job was restarted.

### Local integration follow-up (03:42 CST)

All eight canonical Server shell groups passed: fake command control, environment,
package templates, prepare metadata, full prepare, Final Path, add dataset, and
add contig. The first passes exposed stale shell expectations for the old combined
Step23 unit and pre-`m200/n100` self command; those assertions were updated to the
new independent units and actual accepted self-only defaults, then rerun. Legacy
combined Python entrypoint checks remain. A final focused regression pass ran
**19 tests in 14.537 seconds** after the last code changes. Tracked LF validation
(635 files), shell syntax and `git diff --check` passed. No browser/native GUI
acceptance or public source-asset refresh is claimed by these local checks.

## 04:22 CST remote checkpoint

Exact-execution job 40586982 succeeded. Each of four fresh numerical-cache runs
produced the same **1212 alignment rows**, SHA-256
`5190773abb02d212a331e0734ba0169a20369f2d1ce8e38d32ba740bfef181c4`.

| Round | Baseline seconds | Optimized seconds | Wall-time reduction |
| --- | ---: | ---: | ---: |
| 1 (baseline then optimized) | 293.787 | 237.352 | 19.21% |
| 2 (optimized then baseline) | 325.289 | 241.388 | 25.79% |

Mean wall time was 309.538 -> 239.370 seconds (22.67% reduction, 1.293x).
These are bounded component results on 8 CPUs, NOT full-pipeline savings; OS/shared
filesystem cache effects and node load remain possible. The faster first baseline
also used fewer child CPU-seconds, so no total-compute reduction is claimed.

Job 40586981 succeeded: zebrafish full and gap-screen each passed complete
baseline-versus-optimized stage results and ordered TSV comparisons, including
candidate/rejection diagnostics. Both profiles use the SAME scope within a pair.
The independent full-versus-screen comparison still reports Step2 diagnostic
changes, so scope defaults remain full.

Job 40586980 remains running. Completed exact-profile pairs at this checkpoint:
skill-v3 full + gap-screen, 10g-no-reads full + gap-screen, 10g-with-reads full.
All passed. Their times are cache-assisted comparisons only.

### Customer Step3 test-context recovery

Job 40586881 finished numerical work in 2h19m40s and verified the exact expected
Q3 SHA-256 `a3899e8701f646acd4e07cec2489bce7902119f131c36ce09f9539e8bc7089f0`.
Its harness then failed events equality: all eight differences were generated
`filter_component` object IDs. Both sides have 76 events with identical
(action,status) counts. The exported metadata contains stage-specific run IDs;
the harness selected Step1's run ID instead of the expected Step3 run ID.
Component-filter IDs intentionally include run ID (stage_replay.py), explaining
that mismatch without treating it as scientific equality yet.

Recovery **40586983** uses the same immutable anchor-safe engine, frozen inputs
and existing numerical caches. The test-only runner selects the unique expected
Step3 run ID, invalidates only the test clone's completed stage checkpoint when
that context differs, and explicitly forbids launching any new alignment.
Four CPUs cover parsing/validation/republication; 16 is retained solely in the
historical cache fingerprint. Await the full metadata checks before marking the
customer Step3 gate passed. No production validation or selector was weakened.

## 04:53 CST acceptance update

Customer Step3 cache-only recovery **40586983 succeeded** (04:28:34–04:37:33).
No new alignment was allowed. The expected Step3 run identity was used for the
test adapter, avoiding the unrelated Step1-generated component IDs. Passed:

- actual Q3 file SHA-256 matches the frozen baseline;
- 76 events, 142 evidence rows, 40 usage rows, 63 Q3 source path segments;
- independent metadata-only supplement: all component-filter edit intervals and
  input/output Q provenance, every non-ID classification field, attempt/candidate
  counts, and stage input/output SHA-256.

Supplement: `step3_anchor_safe_semantic_postcheck.json` in the customer Step3 test
workspace. This passes semantic/evidence gates; it does not assert byte-identical
cross-version trace IDs or a cold-runtime benchmark.

Customer Step2 **40586902 failed strict diagnostic equality**, as expected for a
scope reduction. Q2 SHA-256 and all 64 normalized Q2 source segments match.
The anchor-safe selector improves recall/context retention but still yields
82004 vs 117636 evidence rows and 10516 vs 15298 usage rows; attempts/strategies
also differ. Q2 remains `ec331115c6daf91d1f2a1ccde94637a6aca9b0f58625dd45b7412f5d21ec2db0`.
Its numerical work finished in 1h53m29s using borrowed caches; this is not cold
performance. Do not promote Step2 gap-screen to a strict-evidence default.

Exact-profile history job 40586980 has additionally passed 10g-with-reads
`gap-screen` and test8 `full`; test8 `gap-screen` remains in progress. Existing
full pipeline jobs are both still in full Step2, chromosome 7, with no restarts.

## CI-discovered identical-window cache publication race

Quality run **38810533625** on `4111b67` passed Windows app checks but failed
Linux Server: two chromosome screens with byte-identical query windows computed
the same raw numerical-cache key and raced `rmtree` / `os.replace`, producing
`Directory not empty`. The original corpus pairs passed but did not expose this
scheduling case; `a6e85bd6` must not be promoted without this fix.

The revised shared execution context has per-cache-key thread locks around
check/build/publish. Different keys remain parallel. The waiting caller validates
and parses the winning numerical result in its own chromosome/window context;
no shared mutable parsed rows or cross-chromosome provenance are introduced.
This is within one stage collection; it does not replace the workspace runner's
existing process-level exclusion contract.

A synchronized duplicate-window regression asserts one screen build, two distinct
full-query builds, and one rebuild (not two) after corrupting the shared screen
cache. Additional test synchronization removes dependence on child startup
latency, and the failure test reserves a slot for its injected failure regardless
of coordinator interleaving.

Revised engine SHA-256:
`080599a354a4caf75e123d7d507348e3a43c2c0358749ed830b5a69cde6f9318`.
**228 Server tests passed in 99.887 seconds**; 19 focused index/concurrency tests
passed in 12.821 seconds. The alignment parameters, scopes, cache fingerprints
and biological selection logic are unchanged. Repeat corpus/cache-assisted checks
and a real-DNA identical-window positive control are the next gates. Formal source
asset refresh remains blocked on final gates; all defaults remain baseline/full.


## Cache-lock revision revalidation and genuine customer suffix

Quality run **38813019659** on `d9deccf75b2a74c1eb48ab72ac039fab30167790`
passed both Linux Server and Windows App. Source/runtime hashes are pinned in
`cache_lock_revalidation` of the machine-readable record.

Jobs **40587003** (four historical datasets) and **40587004** (zebrafish) both
succeeded. All five datasets were tested with `full` and `gap-screen`; each
baseline/optimized pair uses the same scope and passes 21 exact-result/ordered
TSV checks, 210 in total. Reusing validated numerical caches makes this a
correctness/cache-assisted execution test, not a cold end-to-end benchmark.
The independent full-versus-screen comparisons still expose Step2 diagnostic
changes, so they do not authorize a scope-default change.

Real-DNA positive control **40587005** passed using a 2,200,100 bp window from
customer chromosome 1: identical screen windows publish one numerical build,
while distinct full-query headers retain two full builds and independent parsed
contexts. Both copies yield the same two coordinate rows in original publication
order. This tests the real aligner/cache collision path, not repair accuracy.

Freeze job **40587006** captured genuine upstream donor-freeze and Step1
checkpoints from the running cold producer, before Step3/4 reconciliation could
change metadata. Independent metadata/FAI copies and immutable FASTA links were
used; no success certificate was synthesized. Q1/D0 hashes match the diagnostic
baseline. The genuine upstream source paths (64), donor members (3139), and
Step1 consumed intervals (zero) also match.

Customer core job **40587007** passed 33 Step2/Step3 checks. Full Step2 preserves
both golden Q2/source paths and the cold producer's original, unreconciled
`candidates.tsv`/`rejections.tsv`; only cross-engine trace identifiers are excluded
from that historical-table comparison. Within the current-engine profile pair,
complete stage results and ordered TSVs are compared, including trace fields.
Only wrapper input fingerprints and evidence raw-artifact hashes whose headers
embed workspace paths are excluded from the stage-result comparison.
Step3 uses the previously tested gap-screen scope in both profiles and preserves
the golden Q3. The job forbids launching any new large MUMmer alignment and
fails on an incompatible/missing numerical cache, rather than silently duplicating
hours of computation.

Its first Q4 export assertion failed because it compared case-sensitive sequence
hashes. Diagnostic job **40587016** found equal chromosome names/order and lengths
for all eight records, exact sequence equality on seven records, and only input
letter-case differences on chromosome 6. At Q4 position 84,731,680 (1-based), the
source is `nextdenovo:ctg007740`, source position 146,727. The exporter uses the
original source FASTA and preserves lowercase; GRT FASTA readers uppercase input.
This is an existing representation difference, not an optimized-engine base change.
Do not uppercase production exports merely to satisfy the harness.

Recovery **40587017** retains all 33 completed checks and adds actual production
Step4/finalize, golden Q4/source paths and genuine success checkpoints for each
profile. It compares exported DNA after case normalization, retains the raw-case
mismatch explicitly, and additionally requires byte-identical baseline/optimized
Q4 and export files plus the complete Final Path JSON document. **46 checks pass**.
The status is deliberately `CORE_PASS_DELIVERY_PENDING`, not whole-workflow PASS.
The two resumed Step4 invocations can reuse valid caches; their timings are not
performance claims.

Cache-assisted Step2 wall time was 627.530 -> 301.164 seconds; Step3 was
804.118 -> 455.173 seconds. Both use borrowed validated numerical caches and
fresh stage execution, so these reductions cannot be transferred to cold nucmer
work or used as a complete workflow ETA.

## Complete Step2 scheduling analysis boundary

Job **40587009** succeeded after analysis-only job 40587008 failed under the
system Python (the environment-loading line was missing). No production engine
or compute workflow was restarted. The model reads all **3912** completed raw
partition records (8 chromosomes x 489 unchanged target partitions), their
observed task wall durations and original 16-worker budget. Actual alignment
log window: 26,017 seconds. Fixed-duration simulations:

| Schedule model | Seconds |
| --- | ---: |
| Per-chromosome FIFO | 25,810.927 |
| Per-chromosome largest target first | 24,429.227 |
| Shared queue, largest-target-first chromosome blocks | 24,126.432 |
| Oracle all-task duration LPT | 24,118.434 |

The modeled shared-queue reduction is **6.526%**, not the small cold subset's
22.67%. Observed task wall duration is **not CPU time**: the fixed-duration
schedule bound (24,097.215 seconds) is not a physical CPU/runtime lower bound.
Real coordinator order, memory pressure, IO and node contention can change task
durations. No total-compute reduction, full-workflow time, or measured speedup is
claimed from this model. It explains why improving scheduling alone cannot remove
the bulk of full-scope MUMmer work while preserving every diagnostic alignment.
