# Formal optimized GRT rollout (2026-10-16)

Status: local focused integration checks passed; remote complete-data comparisons
pending. This is not a released/fully accepted runtime yet.

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

- Five refill-focused checks: one batch, hit/query order/CIGAR preservation,
  actual cross-round index reuse, lazy chromosome-cache hits, corruption rebuild,
  failure/retry and duplicate IDs. PASS.
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
