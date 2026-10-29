# Pre-feedback work and final-validation queue — 2026-10-30

## Current instruction

Continue useful implementation before the customer's diagnostic returns. Since
2026-10-30 the user has explicitly deferred test execution to a unified closing
phase. Do not run unit/integration tests, synthetic experiments or new CI test
jobs during this development phase. Static source/diff review and documentation
are allowed. No cleanup test is currently necessary. Commits use `[skip ci]` to
avoid automatically starting push-triggered CI. This is not evidence of passing CI.

## Completed work, with distinct evidence boundaries

| Work | Implementation status | Evidence boundary |
| --- | --- | --- |
| Bounded localization and independent-record replay tool | Previously delivered; customer running its existing ZIP | Customer result still pending; do not replace live package |
| Controlled long-query reproduction and parameter audit | Previously performed | No established universal parameter-only fix; do not rerun or relabel old evidence |
| Forward/reverse restricted split-score witnesses | Implemented | Prior limited fixtures validated; not general post-DP selection |
| Bounded streaming seed evidence and process buffer planning | Implemented | Prior 64/128/512 MiB process-cap experiments; not whole wheat job RAM acceptance |
| Job budget discovery and pure admission proposal | Implemented, not production integrated | 24 targeted / 109 full tests completed BEFORE test deferral; 2.31 run not started |
| Returned isolation archive reviewer and comparison gates | Implemented, source review only | All execution validation deferred; not yet customer delivery-ready |

## Final-validation queue (run only after the user opens that phase)

1. Review all implementation diffs accumulated since the last tested revision.
2. Execute the full experimental Python suite using both unchanged minimap2
   versions 2.26-r1175 and 2.31-r1302; isolate failures and retain raw logs.
3. Validate the new reviewer on synthetic success/failure/malformed/bounded archive
   fixtures. Check no subprocess, extraction, archive mutation or customer-data
   disclosure. Then apply it read-only to the actual returned isolation archive.
4. Validate Slurm/cgroup discovery on representative actual allocations, including
   parent limits and usage, mounts/namespaces, per-CPU usable counts and unknown
   budgets. Current v1/per-GPU modes explicitly refuse; they are not silently
   inferred from node RAM. No new cluster run is currently authorized or launched.
5. Preserve existing guided/streaming/reverse negative fixtures, whole-query/DP
   score evidence, coordinate/CIGAR integrity and downstream comparisons.
6. Only after those checks decide whether to deliver an additional customer tool;
   do not retroactively change the provenance of the package already running.

## Open implementation/research gates (not merely waiting for an archive)

- General post-DP candidate retention/ranking and MAPQ reconstruction remain
  unimplemented. Coarse chaining and an AS threshold are not established substitutes.
- More-than-two splits, joins, complex indels/repeats and scientific equivalence
  require explicit contracts and counterexample validation before any recovery
  mode can be promoted. The existing recovery remains restricted and fail-closed.
- The memory proposal is not a scheduler: no verified peak estimator, exclusive
  reservation ownership, serialized admission, cache-pressure strategy or actual
  production concurrency changes are implemented. No promise of arbitrary-small
  memory support is made.

## Customer-dependent gates

1. Receive the actual isolation archive and its separately recorded SHA-256.
2. Establish a well-formed assertion/query association and stable data/tool identity.
3. Independently reproduce using that complete query and original target/order.
4. Evaluate a parameter-only workaround if the evidence supports one; never patch
   minimap2, remove CIGAR, skip long records or label missing output a fix.
5. Validate complete alignment output and downstream scientific results, then
   finish the original CGAT workflow on the customer's data.

Receiving the diagnostic does **not** close gates 3–5. Existing experiments are
stage evidence, not full customer recovery. This ledger records outstanding work;
it does not claim the user's overall goal is complete.
