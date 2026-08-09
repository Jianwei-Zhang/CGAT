# Database Guidelines

> SQLite ownership, transaction, query, and migration contracts.

## Current System

- Every workspace owns `project.sqlite`.
- `app/backend/src/db.rs::open_workspace_db` opens the database, enables
  `PRAGMA foreign_keys = ON`, and invokes versioned schema migration.
- Rust uses `rusqlite`; values must be passed with `params!` or named parameters.
- `app/backend/src/db.rs::create_current_schema` owns the fresh-schema snapshot;
  `app/backend/src/db_migrations.rs` owns immutable upgrade history.
- Historical `ensure_column_exists` calls now exist only inside migration 1's
  unversioned-workspace baseline. They are not the pattern for future growth.

## Query and Transaction Patterns

- Use explicit column lists for reads and writes. Map rows into domain/read-model
  structs before returning them from persistence code.
- Never interpolate user values into SQL. Dynamic identifiers are allowed only
  from a closed, code-owned set and must be documented at the call site.
- A service operation that updates more than one related row owns one
  `Transaction<'_>` and passes `&Transaction` to helpers. Commit only after all
  database and required staged-file validation succeeds.
- Enable and test foreign keys on every connection path; do not rely on cascade
  behavior with the pragma disabled.
- JSON columns are compatibility/presentation state, not an excuse to bypass
  validation. Normalize the full JSON shape before persistence and on read.

## Naming Conventions

- Tables and columns use `snake_case`; primary keys are `id` unless the external
  contract provides a stable key such as `event_id`.
- Foreign keys use `<entity>_id`; indexes use `idx_<table>_<purpose>`.
- Boolean values stored as integers use `NOT NULL`, a deterministic default,
  and a `CHECK (... IN (0, 1))` where the table is created or migrated.
- Persisted timestamps remain strings only where the existing table contract
  requires them; a new timestamp field must document format and timezone.

## Scenario: Versioned Workspace Schema Migration

### 1. Scope / Trigger

- Trigger: adding, removing, renaming, indexing, or backfilling any
  `project.sqlite` table/column.
- Migration target: replace new `ensure_column_exists` growth with an ordered
  migration ledger while preserving every existing workspace.

### 2. Signatures

Target application entrypoint:

```rust
pub const CURRENT_SCHEMA_VERSION: i64 = 1;
pub fn migrate_workspace_schema(conn: &mut rusqlite::Connection) -> anyhow::Result<()>;
```

SQLite ledger: `PRAGMA user_version` is the integer version applied in strict
ascending order. The production open path is `open_workspace_db`; the retained
`init_workspace_schema(&Connection)` function is a compatibility entrypoint for
tests and adapters, not a second schema owner.

### 3. Contracts

- Each migration has one immutable version, descriptive name, forward SQL/code,
  and tests. Never edit an already released migration.
- Read `user_version`, reject a database newer than the application, then apply
  every missing migration in one transaction per version.
- A truly empty version-0 database creates the current schema snapshot and sets
  the current version in one transaction. A version-0 database with user tables
  is a historical workspace and must run migration 1 before later migrations.
- Every new schema version updates both owners: append one immutable migration
  for old workspaces and update `create_current_schema` for fresh workspaces.
  Fresh creation and stepwise upgrade must expose the same required schema.
- Set `user_version = N` only after migration N and its backfill succeed.
- A data backfill must be deterministic, restart-safe through rollback, and
  preserve existing rows not in its scope.
- Migration 1 is the only compatibility baseline allowed to inspect historical
  columns. It also restores imported assignment orientation from authoritative
  reference-hit `block_length` totals; reverse wins only when strictly greater,
  while positive and ties resolve to `+`.
- Run `PRAGMA foreign_key_check` before committing fresh initialization or an
  upgrade step. A violation fails and rolls back the current transaction.
- Schema initialization and normal application queries do not silently add
  columns after the migration framework lands.
- The application does not create an automatic backup. Before a manual upgrade
  of an irreplaceable workspace, close every process using it and copy the whole
  workspace directory. Never repair a failed upgrade by manually changing
  `PRAGMA user_version`.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Empty database at version 0 | Create the current snapshot transactionally; final version is `CURRENT_SCHEMA_VERSION`. |
| Unversioned database with user tables | Run migration 1, including historical columns/backfills, without replacing user rows. |
| Supported old workspace | Apply only missing versions and preserve user data. |
| Database version is newer than the binary | Reject before writes with `WORKSPACE_SCHEMA_FUTURE_VERSION` and current/observed versions. |
| A required version is absent from the registry | Reject with `WORKSPACE_SCHEMA_MIGRATION_MISSING`. |
| SQL, backfill, or foreign-key validation fails | Return `WORKSPACE_SCHEMA_MIGRATION_FAILED` with migration id/name, roll back that version, and leave `user_version` unchanged. |
| Migration is run again | No data duplication or additional schema change. |

### 5. Good/Base/Bad Cases

- Good: add migration 2 as a new registry entry and function, backfill from
  authoritative rows, validate constraints/indexes, then advance the version.
- Base: a fresh workspace uses the current snapshot; a historical version-0
  fixture uses migration 1 and reaches the same required tables and columns.
- Bad: append another unconditional `ensure_column_exists` call with no version,
  order, downgrade detection, or old-workspace regression test.
- Bad: edit migration 1 after release or set `user_version` before its backfill
  and foreign-key check complete.

### 6. Tests Required

- Fresh database schema and final `user_version` through the real open path.
- Upgrade fixtures for every supported historical version, including fully
  missing and partially existing historical columns.
- Failure injection proving DDL/data/version rollback and a multi-version test
  proving strict step order.
- Future-version rejection before schema writes.
- Idempotent reopen plus successful `PRAGMA foreign_key_check`.
- Read/write behavior test for the feature that required the migration.

### 7. Wrong vs Correct

#### Wrong

```rust
pub fn open_workspace_db(path: &Path) -> Result<Connection> {
    let conn = Connection::open(path)?;
    ensure_column_exists(&conn, "project", "new_flag", "INTEGER DEFAULT 0")?;
    Ok(conn)
}
```

#### Correct

```rust
const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "baseline_unversioned_workspace",
        apply: migrate_unversioned_workspace_to_v1,
    },
    Migration {
        version: 2,
        name: "add_project_new_flag",
        apply: migrate_project_new_flag,
    },
];
```

## Scenario: Processed Project Safe Settings Update

### 1. Scope / Trigger

- Trigger: changing `update_project` behavior for a project that has already entered assembly (`assembly_seq` rows exist / `is_processed` is true).
- Applies to `app/backend/src/project_initializer.rs` and any Tauri/CLI path that builds `ProjectUpdateRequest`.

### 2. Signatures

- Backend request: `ProjectUpdateRequest { project_id, project_name, reference_genome_id, primary_dataset_id, support_dataset_ids, phased_assembly_enabled, chr_assignment_min_coverage_percent }`.
- Backend response: `ProjectUpdateSummary { project_id, project_name, reference_genome_id, primary_dataset_id, project_dataset_count, phased_assembly_enabled, chr_assignment_min_coverage_percent, is_processed }`.
- DB tables touched: `project`, `project_dataset`, and, when appending support datasets post-entry, `assembly_seq` / `assembly_ctg` through `append_project_dataset_assembly_in_transaction`.

### 3. Contracts

- Unprocessed projects may still update the full editable project definition.
- Processed projects are not read-only. They support only these safe one-way edits:
  - rename `project.name`;
  - append new support dataset IDs while preserving every existing support dataset ID;
  - enable phased assembly (`false -> true`).
- Processed projects must keep `reference_genome_id`, `primary_dataset_id`, and `chr_assignment_min_coverage_percent` unchanged.
- For each newly appended support dataset on a processed project, create its assembly rows in the same transaction after the `project_dataset` link is inserted.
- Do not reset `auto_pipeline_done` for processed-project safe edits; the append path is responsible for making the dataset usable without rerunning bootstrap.
- UI-driven processed-project support appends must follow the assembly append with scoped auto-orientation for only the newly appended dataset IDs.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Processed project changes `reference_genome_id` | Reject before writing. |
| Processed project changes `primary_dataset_id` | Reject before writing. |
| Processed project changes `chr_assignment_min_coverage_percent` | Reject before writing. |
| Processed project omits an existing support dataset | Reject before writing; support edits are append-only. |
| Processed project has phased enabled and request disables it | Reject before writing; phased edits are one-way. |
| Processed project appends a support dataset that already has assembly rows | Reject from the append helper. |

### 5. Good/Base/Bad Cases

- Good: processed project `{support: [12], phased: false}` updated with `{name: "new", support: [12, 14], phased: true}`; project row updates and dataset 14 assembly rows are inserted.
- Base: unprocessed project updates reference, primary, support, and phased settings through the full update path.
- Bad: processed project updated by deleting and reinserting `project_dataset` rows without append-only validation, because it can silently remove assembly-backed support datasets.

### 6. Tests Required

- Backend unit test: processed project allows rename, append-only support dataset, and phased enablement.
- Backend unit test: processed project rejects primary/reference/threshold changes, support removals, and phased disablement.
- Check appended support dataset has `assembly_seq` rows and existing dataset assembly rows are not recreated.

### 7. Wrong vs Correct

#### Wrong

Treat `is_processed` as fully read-only and return before checking which fields changed.

#### Correct

Validate processed-project updates field-by-field, preserve locked fields, append new support dataset assembly rows in the same transaction, and reject unsafe changes.

## Recommended Pattern

Use the feature service to open a transaction, validate referenced IDs, perform
all related writes through small helpers, and return a typed summary only after
commit. Existing examples include append-only processed-project updates in
`project_initializer.rs`.

## Prohibited Patterns

- String-formatted SQL containing request values.
- Committing intermediate rows before semantic validation finishes.
- Catching a database error and continuing with a partially updated workspace.
- Treating an in-memory test database as sufficient when filesystem paths,
  reopen behavior, or workspace migration are part of the contract.

## Common Mistakes

- Forgetting that SQLite foreign keys are connection-local.
- Updating JSON defaults without canonicalizing old persisted values.
- Testing only a fresh database and missing upgrade order or backfill failures.

## Review Checklist

- [ ] Are values parameterized and row mappings explicit?
- [ ] Does one transaction cover the complete consistency boundary?
- [ ] Is the change an ordered immutable migration with old-workspace tests?
- [ ] Are foreign keys, uniqueness, defaults, and indexes intentional?
- [ ] Are failure and reopen/idempotence cases covered?
