# Formal optimized GRT rollout (2026-10-16)

Status (12:51 CST): production refill passed; three default full-scope cases
passed metadata-semantic review; three Step2 gap-screen cases have core/Final
Path equality but audit differences. Four other case runs remain pending.
Raw comparison failures remain retained. This is not released/full acceptance.

## Authorized boundary

- New prepare/run defaults: optimized execution, **full Step2**, anchor-safe
  gap-screen Step3, batched Step3 refill with content-verified `.mmi` reuse.
- The original five exact execution optimizations are enabled by optimized mode.
- Step2 gap-screen stays experimental and is not enabled by this rollout.
- Both run.sh and prepare.sh expose rollback for **new** workspaces:
  `--grt-execution-profile baseline --grt-step3-mummer-scope full`.
- Existing workspaces/running jobs and published Release assets are unchanged.
- User explicitly requested **no old baseline reruns**; use retained artifacts.

## Refill production integration

Same-round queries keep their original IDs and per-query hit order. Numerical
chromosome-cache hits remain usable; a lazily constructed batch runs only on a
miss. Split PAFs, logs and batch provenance are validated/published by the normal
chromosome-cache path. A cold `minimap2 -x asm5 -c -d ...` call maps and saves its
index together; later rounds can reuse the exact target/preset/binary index.
Target content, executable hash/version and preset identify the index. Content
hash checks, POSIX locks and atomic publication prevent partial/corrupt reuse.
No alignment threshold, reference/query role or donor partition boundary changes.

## Necessary local checks (not the whole test suite)

- Six refill-focused checks: one batch, hit/query order/CIGAR preservation,
  actual cross-round index reuse, lazy chromosome-cache hits, corruption rebuild,
  failure/retry, duplicate IDs and multi-part-index stream ordering. PASS.
- Seven repair-stage integration checks (including exact cold fixture profile
  comparison, actual split entries, engine identity, resume and invalidation).
  PASS. These exercise the newly split modules, not only the previous revision.
- prepare_metadata_test.sh: PASS; production generation includes optimized/full
  Step2 and optimized/gap-screen Step3, with metadata and rollback options.
- No unrelated Windows/frontend build, browser or broad code CI was requested.

## Remote tests: only new execution, old results read-only

1. First run the new production refill helper on the **complete real customer
   refill queries in both rounds**, comparing every byte of each split PAF with
   the previously saved reference. This also qualifies simultaneous -d/mapping.
2. Complete-data cases: 10g without reads, 10g with reads, test8 fixed, zebrafish,
   and customer 2665. No chromosome or donor subsampling.
3. Reuse verified unchanged upstream assignment/reads-QC/Step1 inputs. Run only
   the affected **new GRT Step2 -> Step3 -> Step4/finalize** via real production
   stage generators and run_all_runner. This is a complete-data GRT suffix test,
   NOT a new full vs_ref/self/reads-QC/packaging workflow benchmark.
4. Numerical caches start empty in isolated workspaces; metadata/runtime/FAI
   are independent copies, only immutable FASTA inputs may be linked.
5. Compare against retained old stage results plus the original complete Final
   Path: Q2/Q3/Q4 SHA-256, ordered source paths, accepted events, diagnostics,
   candidate/rejection order for full Step2, classifications, complete semantic
   Final Path (source/interval/orientation/order/kind/length/DNA), and actual
   Final Path FASTA export after explicitly recording case normalization.
6. Engine-derived trace IDs and workspace-dependent raw-artifact hashes are not
   scientific equality targets; decision reasons, source/coordinate fields and
   classifications are. No DNA mismatch is waived as a trace-ID difference.
7. Record new stage wall times, but do not assert a strict speedup ratio against
   old timings with different cache/resource conditions. No old engine is run.

Final source-asset refresh remains gated on remote results and delivery closure.

## 11:56 CST checkpoint

Runtime pinned to `7ba84ea`, archive SHA-256
`74c8860a4ac20d48e4932576cfbcbf20e5794d270a211f99a012914fde715579`;
verified on 180 before extraction. Production refill job **40587487** succeeded:
all 16 chromosome/round PAF files are byte-identical to retained old artifacts,
and actual second-round index reuse passes (17 checks). New production wall
times including cache publication were 42.745s and 10.884s, not whole-GRT times.

Five NEW-only complete-data suffix jobs were submitted and started at 11:55 CST:

| Dataset | Job | CPUs | Last observed state |
| --- | ---: | ---: | --- |
| 10g no reads | 40587489 | 8 | RUNNING; three input/cache-identity gates pass |
| 10g with reads | 40587490 | 8 | RUNNING; three input/cache-identity gates pass |
| test8 fixed | 40587491 | 8 | RUNNING; three input/cache-identity gates pass |
| zebrafish | 40587492 | 8 | RUNNING; three input/cache-identity gates pass |
| customer 2665 | 40587493 | 16 | RUNNING; three input/cache-identity gates pass |

Final result/Final Path equality is still pending for all five. The preserved
old engines were not launched. Full detail: `grt-formal-optimized-results-20261016.json`.

## 12:00 CST correction and Step2 screen supplement

The first five full-data submissions 40587489-40587493 **failed at launcher
startup**: the validation generator extracted the production stage functions but
omitted their `shell_quote` helper, producing empty command arguments. They did
not execute nucmer/minimap2. Their earlier RUNNING snapshot is historical, not a
current successful alignment claim. The real production refill PASS is unaffected.

The corrected validation launcher extracts the quoting helper too and validates
the resulting argument vector and Bash syntax before starting any stage. Both
full and experimental gap-screen scripts, including paths containing spaces,
pass a targeted generation check. Production prepare defaults remain unchanged.

Full-scope NEW runs resume only these failed, still-numerical-cold test workspaces;
old engines and original two full producers are not touched. Five additional
NEW-only Step2 gap-screen cases use independent empty caches, matching inputs,
thread budgets, runtime, Step3 scope and refill mode. Each records Stage2 and
GRT-suffix wall times; matching full-group timing is joined when available.

Core/Final Path equality is recorded separately from audit equality. Core checks
include Q2/Q3/Q4 hashes and ordered paths, accepted events/consumed donor usage,
applied strategy, accepted classifications, final accepted repairs and complete
semantic Final Path plus exported DNA. Audit differences retain their failed
checks and previews; `CORE_PASS_AUDIT_DIFFERENT` is not strict equivalence or
permission to enable Step2 screening by default. Any core change remains FAIL.

## 12:04 CST resubmission

Corrected launcher `b2c124b` SHA-256
`f61be124a45fb6e956927dfb2bcd6e850261e4ec7a621fd17b09e54e44a8f95c`
was verified on 180. Runtime remains pinned to `7ba84ea`; no aligner algorithm
or production default was changed for the experimental group.

| Dataset | New optimized full Step2 retry | New optimized gap-screen Step2 |
| --- | ---: | ---: |
| 10g no reads | 40587500 | 40587501 |
| 10g with reads | 40587502 | 40587503 |
| test8 fixed | 40587504 | 40587505 |
| zebrafish | 40587506 | 40587507 |
| customer 2665 | 40587508 | 40587509 |

All ten were observed RUNNING after submission; scientific output comparisons
remain pending. Old long-running producers 40550762/40550763 remain untouched.
The full retries append to the earlier failed launcher log; only the new attempt
and new timings are relevant. Earlier five startup failures are retained.

## 12:11 CST: approved customer-pair CPU increase

At the user's approval, only customer validation jobs **40587508/40587509** were
terminated and superseded. The scheduler reports them FAILED after the requested
termination; this is not an aligner correctness failure. Their outputs/logs remain
untouched for history and are excluded from the primary cold-timing comparison.

Fresh isolated customer cases, both requesting **32 CPUs** and `--threads 32`:

| Step2 scope | Replacement job | Initial observed state |
| --- | ---: | --- |
| full | 40587512 | PENDING |
| gap-screen | 40587513 | PENDING |

Root: `grt-formal-optimized-20261016/cases-customer32/{full,gap}` on SSH 180.
Neither case borrows any numerical caches from the prior 16-CPU attempts. The
runtime/launcher remain 7ba84ea/b2c124b; gap/full inputs and thread budgets match.
More allocated CPUs do not promise linear speedup, and queue delay is additional.

The four smaller dataset pairs retain 8 CPUs and are not restarted. Original
whole-workflow producers **40550762/40550763** are unchanged. No production default
or released source asset changes accompany this resource adjustment.

## 12:23 CST: 16-CPU recovery and ARM assessment

The 32-CPU customer jobs **40587512/40587513** were explicitly cancelled while
pending at 12:14:56, without running computation. Following the user's request
not to wait for a long queue, the customer pair resumed their **own** existing
16-CPU workspaces/caches (not the historical baseline cache):

| Scope | Current job | Observed state | Node |
| --- | ---: | --- | --- |
| full | 40587514 | RUNNING, Step2 alignment | agent-X86-38 |
| gap-screen | 40587519 | RUNNING, input gates passed | agent-X86-33 |

The first gap resume **40587515** failed at startup because the terminated
40587509 left a workspace lock owned by another node. The runner conservatively
refuses cross-node takeover. Recovery job **40587518** ran on the original
agent-X86-27: the original PID/start identity was absent and no same-user command
referenced this workspace. It archived (did not delete) the unchanged lock and
recorded owner/provenance in remote `gap-lock-recovery.json`, then succeeded.
The failed report and old logs remain retained; only gap was resubmitted.
No live locks were bypassed, no production lock policy or active runtime changed.

The validation launcher now requires explicit `--resume --reuse-own-cache` to
resume numerical work. Reports label this `own-cache-resume`: remaining wall
time is **not cold timing**, and no cold full/gap speed ratio is emitted for
these resumed customer cases. Correctness/Final Path gates remain unchanged.
Only scoped source/diff validation is required for this launcher-only change;
no unrelated regression suite or frontend tests are run.

All eight small-case tasks **40587500–40587507** are still RUNNING. Partial
8-CPU Step2 observations (different nodes, single measurements):

| Dataset | Full Step2 | Gap-screen Step2 | Current boundary |
| --- | ---: | ---: | --- |
| 10g no reads | 1073.758 s | 788.853 s | Stage2 wall reduction about 26.5%; Final Path pending |
| zebrafish | 518.102 s | 506.729 s | Stage2 wall reduction about 2.2%; Final Path pending |
| 10g with reads | running | 855.783 s | Not a completed pair |
| test8 fixed | 641.820 s | running | Not a completed pair |

These are NOT overall workflow speedups and NOT proof of Final Path equality.
Step2 gap-screen remains experimental/default-off.

ARM login via port18081 was verified as cli-ARM-01/aarch64. At this checkpoint,
ARM-07/08/14/21 each had 128 free CPUs and ARM-18 had 96. Stock ARM modules load,
but minimap2 **2.28-r1209** and MUMmer **4.0.0rc1** differ from the pinned x86
**2.30-r1287 / 4.0.1** comparison. No version-mixed ARM benchmark is submitted,
and already-running x86 tests are not restarted just to change architecture.
Future ARM comparisons need matching pinned versions and their own validated
cache/tool identity; cross-architecture timing must be reported separately.

Original whole-workflow producers **40550762/40550763** remain RUNNING and
untouched, past GRT finalize and into per-chromosome leaf alignment. The full
suite's Final Path acceptance remains pending; official Release assets unchanged.

## 12:51 CST: completed comparisons and trace-reference review

The numerical Step2/3/finalize stages and Final Path export completed successfully
for six cases. Their scheduler jobs report **FAILED** because the strict raw
comparison exit was nonzero, NOT because an alignment or stage crashed. Original
`report.json`/logs and scheduler states remain unchanged.

| Dataset | Default full Step2 | Experimental gap-screen Step2 |
| --- | --- | --- |
| 10g no reads | semantic PASS | CORE_PASS_AUDIT_DIFFERENT |
| 10g with reads | semantic PASS | CORE_PASS_AUDIT_DIFFERENT |
| test8 fixed | semantic PASS | CORE_PASS_AUDIT_DIFFERENT |
| zebrafish | finalize running | finalize running |
| customer2665 | Step2 running, own-cache resume | Step2 running, own-cache resume |

Every completed case passed Q2/Q3/Q4 DNA, ordered source paths, semantic Final
Path and actual exported sequence checks. A metadata-only sidecar review
`grt_semantic_review.py` resolves **actual references**, without running old/new
aligners or modifying an active runtime:

- Component-filter object IDs are generated from run_id. Their complete retained
  event semantics (including kept/removed intervals) match across runs.
- Gap-screen changes alignment line indices and derived candidate IDs. Donor
  reuse references resolve to candidate objects with identical source/target
  coordinates, orientation, scores and decisions; no reference is simply dropped.
- Attempt reasons embed event IDs. These resolve to the same semantic event.
  Finalized event IDs are resolved against final metadata, separately from the
  stage snapshot IDs, since their run IDs can differ.
- Missing/cyclic references fail, coordinate changes remain failures. Focused
  negative controls verify changed coordinates and dangling references fail.
- All unreviewed original core checks must still pass. Sidecar reports preserve
  raw result identity/script hashes and do not overwrite original failed reports.

Default full-scope cases have no remaining semantic audit differences after this
review. Gap-screen retains differences in evidence/usage/attempt/strategy and
ordered candidate/rejection diagnostics; these have NOT all been proven limited
to rejected-count changes. Thus Step2 screening remains experimental/default-off.

| Dataset | Full Step2 | Gap Step2 | Stage2 wall change | Full suffix | Gap suffix |
| --- | ---: | ---: | --- | ---: | ---: |
| 10g no reads | 1073.758s | 788.853s | 26.5% reduction | 1738.955s | 1333.204s |
| 10g with reads | 1115.755s | 855.783s | 23.3% reduction | 1802.764s | 1418.656s |
| test8 fixed | 641.820s | 1165.282s | 81.6% increase | 1752.080s | 2662.857s |

These are observed new-full vs new-gap timings, one pass with eight CPUs on
different/shared nodes, not a same-node isolated causal measurement. Test8
shows no measured benefit in this round; do not report a universal speedup.
No strict old-vs-new full-workflow speed ratio is established by these suffix runs.

Original skip-self **40550762** is at finalize_evidence after all chromosome
alignments; self-m200/n100 **40550763** remains in chromosome alignment. Customer
optimized full/gap jobs **40587514/40587519** remain in Step2. They were not
modified for the ARM installer test. ARM installer/synthetic workflow evidence
is documented separately in `arm-install-20261016.md`.

## 2026-10-17 customer completion and semantic review

The two resumed complete-customer GRT suffix jobs reached terminal results:

| Step2 scope | Job | Analysis pipeline | Raw comparison | Semantic review | Remaining boundary |
| --- | ---: | --- | --- | --- | --- |
| full (default) | 40587514 | SUCCESS | core PASS; two raw Step3 audit differences | **PASS** | none |
| gap-screen (experimental) | 40587519 | SUCCESS | core PASS; eight audit differences | CORE_PASS_AUDIT_DIFFERENT | Step2/Step3 diagnostics remain different |

Job 40587514 is retained as scheduler `FAILED` because its strict raw postcheck
returned nonzero after the analysis pipeline completed. A new metadata-only
review, job 40590173, resolved the Step3 generated-ID references and passed every
full-scope core and audit semantic check. It did not rerun an aligner, alter the
original report or waive DNA/coordinate differences.

Observed own-cache-resume suffix times were 35,774.911 s for default full Step2
and 23,073.966 s for experimental gap-screen. They are remaining resumed times,
not cold or same-node causal speedup measurements. Gap-screen still differs in
Step2 evidence, usage, attempts, strategies and ordered candidate/rejection
diagnostics; it therefore remains experimental and default-off.

The release gate is the independent latest complete workflow 40588179: complete
fresh customer inputs, production batching/adaptive scheduling, Full/Light
packages and 17/17 retained-golden checks passed. See
`full-latest-2665-arm32-20261017.md`.
