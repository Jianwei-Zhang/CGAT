# Formal optimized GRT rollout (2026-10-16)

Status: local focused integration checks and real production refill passed;
five remote complete-data comparisons running. This is not a released/fully
accepted runtime yet.

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
