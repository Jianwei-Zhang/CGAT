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

The first adapter covers a fully validated completed LGZ baseline. Unfinished legacy stages still require a separate content/version-aware resume adapter: they are not silently treated as complete, discarded or rerun. This remaining requirement stays in the feature's acceptance matrix. Final acceptance must exercise actual generated scripts, interrupted apply/resume/rollback, live/foreign owners, immutable proof preservation and post-migration append without LGZ execution. Primitive/preview tests do not establish that full workflow.

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

An interrupted transaction blocks ordinary launches. Use its recorded version/source to continue, or roll it back while its owned files are unchanged:

```bash
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server --resume --confirm-idle
python3 -B /opt/cgat/server/tools/migrate_workspace.py --server-dir /work/cgat_server --rollback --confirm-idle
```

The confirmation flag records the operator's scheduler/job check; it is **not** a substitute for the live/foreign-owner and local-process checks. The CLI does not guess an SSH target or assume that a missing local PID means another node is idle. A changed approval inventory is rejected. If staging was interrupted before all approved bytes existed, rollback/re-preview is the safe recovery; no unapproved code is generated during resume.

A completed migration preserves original source/checkpoint bytes and their old-engine provenance in the journal/backup. The execution report uses `frozen_original_lgz`, not `computed` or `cache_reused`; no fresh engine checkpoint is fabricated. Direct old scientific scripts explain that the baseline is frozen rather than recreating legacy paths. `--max-fill` and other LGZ science changes are not an append operation; start a separate new workspace for them.
