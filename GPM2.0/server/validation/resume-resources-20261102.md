# Resume resources and startup update diagnostics

Decision approved on 2026-11-02. This is an internal implementation record,
not a new public parameter catalogue.

- First scope: `run.sh` may change the existing thread and reads-QC memory
  budgets after the previous job has stopped. Other analysis settings remain
  locked; the existing Step3 refill-limit exception is unchanged. Archive-format
  changes are outside this patch. Do not expose previously internal options in
  README or expand their support status.
- Keep original launch settings, prepared scripts, and preparation metadata
  immutable for resource-only resumes. Store effective resources and change
  history separately under `.run_all/`, protected by the workspace lock.
  Record the actual budget in run logs and retain the resource receipt in the
  portable report manifest. Omitted budgets retain the last value.
- Apply overrides only at execution/scheduling boundaries, not to scientific
  cache identities. Historical resource fields in cache fingerprints remain
  preparation identities; never relabel an old checkpoint as a new run.
  Integrity, tool identity, input identity, and normal code-update invalidation
  remain enforced. Interrupted work resumes at existing validated checkpoint
  granularity; no in-place resizing of a live process is promised.
- `run_all.sh` inherits persisted budgets; it gains no new CLI options.
  Legacy workspaces without a `run.sh` launch manifest may change only these
  resources when their preparation metadata and updated resource-aware runtime
  are available. Legacy monolithic Step2/3 runtimes remain unsupported and fail
  explicitly rather than silently ignoring budgets.
- On startup, buffer per-source update diagnostics and retain them in
  `.run_all/update-check.log`. Network-only failures get a concise unreachable-
  sources notice. Metadata/archive failures get an incomplete-check notice.
  Mention `.prepare_lib` alignment only after verified local alignment succeeds.
  Corrupt local code, failed alignment, apply, or rollback still stops execution.
  Explicit `update.sh` failures retain actionable diagnostics.
- Do not claim online freshness from offline integrity/alignment checks.

## Validation

- Server unittest discovery: 424 tests passed (259.141 s).
- Initial affected-module regression: 121 tests passed; after the final portable-
  report resource-receipt and log-order changes, a further 54 launcher, runner,
  resource, report and LGZ compatibility tests passed (74.873 s).
- Shell preparation metadata and full preparation fixtures both passed.
- Tracked LF, release guide versions, modified Python syntax, and diff whitespace
  checks passed. The maintained long-query runtime synchronizer verified all
  31 generated files with no pending differences; only the two source-inventory
  receipts were regenerated, not recovery algorithms or native companions.
- A README flag-set comparison across the four English/Chinese READMEs found
  no newly exposed parameter names. Existing internal settings remain locked.
- Controlled fixtures cover 10-to-64 resume, completed reference-checkpoint
  reuse, unchanged preparation/launch identities, persisted and CPU-affinity-
  bounded execution budgets, QC/Step1 cache hits, live-lock refusal, legacy
  unsupported-runtime refusal, concise DNS failure diagnostics, non-network
  classification, and continued refusal of damaged local runtime/code.
- Existing ResourceWarning messages for unclosed test subprocess streams were
  observed; no unrelated process-lifecycle refactor was included.

## Delivery boundary

This validates local source behavior and fixtures, not a customer-data rerun,
real scheduler allocation, native scientific 10/64-core equivalence, or desktop
acceptance. The source commit/push does not itself refresh official Server
attachments or formally deployed documentation. On 2026-11-02, the user explicitly deferred replacing the current Release
assets and deploying formal docs: ship these changes together with the next
version instead of a same-version refresh. Existing release/deployment gates
still apply at that time. No public assets, live customer workspaces, scheduler
jobs or App installers were changed.
