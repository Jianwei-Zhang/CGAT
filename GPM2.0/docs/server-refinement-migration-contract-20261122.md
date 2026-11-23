# Legacy workspace migration contract

Date: 2026-11-22. Extends the approved design; migration is an explicit operation, never prepare/resume side effects.

## Public operation

The installed Server provides a migration entrypoint independent of the workspace's old launcher. Preview is read-only and binds the physical inventory, generated command changes, new runtime files and validated scientific baseline. Apply requires that exact approval digest and an exclusive legacy workspace lock. Local standalone work is checked too; foreign/unknown owners are not inferred idle. Resume/rollback operate on the recorded transaction, not a newly guessed plan.

## Completed LGZ baseline

A completed legacy workspace is certified only after the real LGZ contract validates its original proof, sources, q-stage hashes, evidence and Final Path. Migration preserves these scientific files and checkpoints byte-for-byte (except rebasing file symlinks to the same role). The new runtime must validate the same contract after physical movement, before committing the layout marker.

A dedicated migrated-baseline receipt records the original scientific producer-receipt identities, physical mapping and certified execution plan. Legacy runtime bytes observed at migration are snapshotted separately: an already-upgraded runtime is not falsely claimed to be the exact producer engine. The original stage receipts remain authoritative. Future append runs validate that receipt and its actual scientific files, then explicitly skip the certified prefix as **original-engine frozen LGZ**, not as a new-engine checkpoint/cache hit. Refinement and delivery run normally. Invalid/mutated baseline proof stops execution; it must never fall through to recomputing LGZ with a different engine. Changing LGZ science requires a new workspace; resource budgets and downstream reads/tools remain mutable.

Repository-owned launcher, packaging/export helpers and runtime are installed transactionally. Original overwritten code remains in the migration backup. Scientific commands that are no longer executable in frozen mode must explain that boundary rather than create legacy shadow trees. User notes and unrelated files are preserved.

## Transaction closure

The existing move/rewrite journal is extended with content-bound **additions** for runtime modules and new receipts absent from old installations. An addition may not overwrite an existing/known destination, traverse symlinks or overlap migration/lock state. It is staged before application, installed by same-filesystem atomic rename rather than a partial live copy, verified afterward, resumable and removed on rollback only when still byte-identical to the transaction's owned output. A changed destination is never deleted.

Destination scientific validation uses a narrowly scoped, lock-checked migration view while the journal is `validating`. Ordinary launchers, subprocesses and unrelated workspaces remain blocked until commit. This is not an early ready marker or a global Path monkeypatch.

## Scope and remaining acceptance

The physical migration adapter covers a fully validated completed LGZ baseline. The separate, content-reviewed original-engine continuation described below now precedes migration for unfinished LGZ work; it does not silently classify pending stages as complete, discard their caches or change engines. Unsupported historical engines remain ineligible until separately reviewed. Actual generated scripts from the reviewed historical engine, unfinished native continuation, live-owner refusal, interrupted move/validation recovery and post-migration refinement are recorded in the [native migration acceptance](server-refinement-final-acceptance-20261122.md#native-migration-from-a-genuinely-prepared-legacy-workspace). The evidence is specific to that engine, local process interruption points and workspace; it does not certify arbitrary scheduler/host ownership or historical versions.

## Completed-workspace commands

Run the **newly installed Server's** migration command, not the old workspace's runtime. Replace the two paths below with the actual installation and old workspace. Preview hashes the existing inventory and validates the LGZ proof; it does not run alignments, LGZ, refinement or install dependencies.

```bash
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server --preview
# Review the moves, original contract, replaced commands and added runtime files.
# Stop/verify active AND queued jobs on every relevant node before confirming idle.
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server \
  --apply --approve <approval_sha256-from-preview> --confirm-idle
# Once committed, append typed reads using the workspace's upgraded launcher.
bash /work/cgat_server/run_all.sh --hifi /reads/hifi.fq.gz [--ont /reads/ont.fq.gz]
```

The migration leaves a fence in the original `.run_all/lock` before publishing migration intent. This also blocks legacy launchers that do not recognize the migration journal. Only explicit `--resume` or `--rollback` can reclaim the fence on the recorded host and while no other controller holds it. Do not remove the lock manually. A rollback or committed migration releases the fence.

An interrupted transaction blocks ordinary launches. Use its recorded version/source to continue, or roll it back while its owned files are unchanged:

```bash
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server --resume --confirm-idle
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server --rollback --confirm-idle
```

The confirmation flag records the operator's scheduler/job check; it is **not** a substitute for the live/foreign-owner and local-process checks. The CLI does not guess an SSH target or assume that a missing local PID means another node is idle. A changed approval inventory is rejected. If staging was interrupted before all approved bytes existed, rollback/re-preview is the safe recovery; no unapproved code is generated during resume.

A completed migration preserves original source/checkpoint bytes and their old-engine provenance in the journal/backup. The execution report uses `frozen_original_lgz`, not `computed` or `cache_reused`; no fresh engine checkpoint is fabricated. Direct old scientific scripts explain that the baseline is frozen rather than recreating legacy paths. `--max-fill` and other LGZ science changes are not an append operation; start a separate new workspace for them.

## Unfinished legacy LGZ: original-engine continuation before physical migration

An unfinished workspace must not be renumbered and passed to a different LGZ
engine. The explicit continuation adapter first finishes only the scientific
prefix through `finalize_evidence`, in the original physical layout, using the
workspace's exact, reviewed historical engine. It never invokes the old DEGAP or
packaging tail and does not edit the persisted plan, scripts, prepare options,
reads, environment or runtime. Saved launch/output and generated literal root bindings must still resolve to this workspace; moved scripts pointing elsewhere are refused, not automatically rewritten or executed in another project. Custom/moved-root adaptation needs separate review. Once the original LGZ contract validates, the
existing completed-baseline transaction performs the numbered migration under
its own fresh approval. The temporary legacy layout is a continuation boundary,
not a set of shadow directories in a migrated workspace.

`--preview-lgz-continuation` is read-only. It binds the existing inventory,
original commands, original engine content manifest, current adapter and valid
completed checkpoints. Unknown/modified engines are ineligible; a version string
or success row alone is not sufficient. `--continue-lgz --approve <digest>
--confirm-idle` rechecks that approval under the original workspace lock. Known
completed outer units must pass their original input/output validator, and
existing q/stage receipts must still bind their actual output bytes. Corrupt or
stale completed work fails rather than becoming permission to recompute it.

The original runner receives an in-memory prefix only. Its normal scientific
commands, threads and internal partial caches remain authoritative. A disclosed
read-only cache fence in Python child processes stops at a reviewed cache-miss
boundary whenever an existing completed q0/donor/q-stage would otherwise be
invalidated. It does not make a failed cache lookup a hit or fabricate a stage
receipt. This protects valid completed stages when parameters/tools differ and
leaves interrupted, receipt-less work to the original engine's ordinary rules.
Engine files are content-checked before import and again at unit dispatch;
customer Python modules are never imported based only on a claimed version. Historical bytecode caches are neither trusted nor deleted; preview and continuation use a fresh non-writing bytecode namespace.

Each attempt records its approval, original-engine identity, observed reuse and
exit status separately under `.run_all/legacy_continuation/`. A failed or killed
attempt stays a legacy workspace and can receive a fresh read-only preview;
there is no automatic environment upgrade or layout commit. A successful attempt
returns a completed-migration preview, not an implicit approval to replace files.
This adapter is supported only for engine content manifests explicitly shipped
with the Server; other historical engines require another reviewed manifest.
The real pre-numbered plan places old DEGAP before evidence finalization; the
reviewed LGZ prefix still excludes it. Its reads receipt remains in the migrated
workspace but is not evidence for a DEGAP result and never prevents packaging
the separate `00_lgz` baseline.
