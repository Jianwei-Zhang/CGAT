use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension};

use super::{CURRENT_SCHEMA_VERSION, create_current_schema};

const FUTURE_VERSION_ERROR: &str = "WORKSPACE_SCHEMA_FUTURE_VERSION";
const MISSING_MIGRATION_ERROR: &str = "WORKSPACE_SCHEMA_MIGRATION_MISSING";
const MIGRATION_FAILED_ERROR: &str = "WORKSPACE_SCHEMA_MIGRATION_FAILED";
const FOREIGN_KEY_ERROR: &str = "WORKSPACE_SCHEMA_FOREIGN_KEY_CHECK_FAILED";

type MigrationFn = fn(&Connection) -> Result<()>;

#[derive(Clone, Copy)]
struct Migration {
    version: i64,
    name: &'static str,
    apply: MigrationFn,
}

#[derive(Clone, Copy)]
struct LegacyColumn {
    table: &'static str,
    name: &'static str,
    definition: &'static str,
}

const MIGRATIONS: &[Migration] = &[Migration {
    version: 1,
    name: "baseline_unversioned_workspace",
    apply: migrate_unversioned_workspace_to_v1,
}];

const LEGACY_COLUMNS: &[LegacyColumn] = &[
    LegacyColumn {
        table: "project",
        name: "auto_pipeline_done",
        definition: "INTEGER NOT NULL DEFAULT 0",
    },
    LegacyColumn {
        table: "project",
        name: "auto_check_new_seq",
        definition: "INTEGER NOT NULL DEFAULT 0",
    },
    LegacyColumn {
        table: "project",
        name: "phased_assembly_enabled",
        definition: "INTEGER NOT NULL DEFAULT 0",
    },
    LegacyColumn {
        table: "project",
        name: "chr_assignment_min_coverage_percent",
        definition: "REAL NOT NULL DEFAULT 60.0",
    },
    LegacyColumn {
        table: "project",
        name: "description",
        definition: "TEXT",
    },
    LegacyColumn {
        table: "runtime_settings",
        name: "degap_workspace_settings_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "runtime_settings",
        name: "updated_at",
        definition: "TEXT NOT NULL DEFAULT '0'",
    },
    LegacyColumn {
        table: "runtime_settings",
        name: "note",
        definition: "TEXT",
    },
    LegacyColumn {
        table: "dataset",
        name: "self_alignment_available",
        definition: "INTEGER NOT NULL DEFAULT 1",
    },
    LegacyColumn {
        table: "ref_alignment_hit",
        name: "cg_tag",
        definition: "TEXT",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "support_dataset_id",
        definition: "INTEGER",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "track_view_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "support_ds_ctg_len_rules_by_chr_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "track_scroll_state_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "subview_track_scroll_state_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "support_mirrored_ctgs_json",
        definition: "TEXT NOT NULL DEFAULT '[]'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "hidden_primary_ctg_ids_json",
        definition: "TEXT NOT NULL DEFAULT '[]'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "hidden_primary_ctg_ids_by_chr_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "track_drag_offsets_json",
        definition: "TEXT NOT NULL DEFAULT '[]'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "subview_track_drag_offsets_json",
        definition: "TEXT NOT NULL DEFAULT '[]'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "subview_anchor_state_by_key_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "final_path_view_mode",
        definition: "TEXT NOT NULL DEFAULT 'graph'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "final_path_by_chr_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "degap_project_state_json",
        definition: "TEXT NOT NULL DEFAULT '{}'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "updated_at",
        definition: "TEXT NOT NULL DEFAULT '0'",
    },
    LegacyColumn {
        table: "project_assembly_view_state",
        name: "note",
        definition: "TEXT",
    },
];

pub(super) fn migrate_workspace_schema(conn: &Connection) -> Result<()> {
    validate_migration_registry()?;

    let found_version = user_version(conn)?;
    if found_version > CURRENT_SCHEMA_VERSION {
        bail!(
            "{FUTURE_VERSION_ERROR}: workspace schema version {found_version} is newer than supported version {CURRENT_SCHEMA_VERSION}"
        );
    }
    if found_version == CURRENT_SCHEMA_VERSION {
        return Ok(());
    }

    if found_version == 0 && !database_has_user_tables(conn)? {
        initialize_fresh_schema(conn)?;
    } else {
        apply_pending_migrations(conn, found_version, MIGRATIONS, CURRENT_SCHEMA_VERSION)?;
    }

    let migrated_version = user_version(conn)?;
    if migrated_version != CURRENT_SCHEMA_VERSION {
        bail!(
            "{MISSING_MIGRATION_ERROR}: expected schema version {CURRENT_SCHEMA_VERSION} after migration, found {migrated_version}"
        );
    }
    Ok(())
}

fn validate_migration_registry() -> Result<()> {
    let mut expected_version = 1_i64;
    for migration in MIGRATIONS {
        if migration.version != expected_version {
            bail!(
                "{MISSING_MIGRATION_ERROR}: expected migration {expected_version}, found {} ({})",
                migration.version,
                migration.name
            );
        }
        expected_version += 1;
    }
    if expected_version - 1 != CURRENT_SCHEMA_VERSION {
        bail!(
            "{MISSING_MIGRATION_ERROR}: registry ends at version {}, current version is {CURRENT_SCHEMA_VERSION}",
            expected_version - 1
        );
    }
    Ok(())
}

fn initialize_fresh_schema(conn: &Connection) -> Result<()> {
    run_transaction(conn, "fresh schema initialization", |tx| {
        create_current_schema(tx)?;
        verify_foreign_key_integrity(tx)?;
        set_user_version(tx, CURRENT_SCHEMA_VERSION)
    })
}

fn apply_pending_migrations(
    conn: &Connection,
    from_version: i64,
    migrations: &[Migration],
    target_version: i64,
) -> Result<()> {
    let mut current_version = from_version;
    while current_version < target_version {
        let next_version = current_version + 1;
        let Some(migration) = migrations
            .iter()
            .find(|migration| migration.version == next_version)
        else {
            bail!("{MISSING_MIGRATION_ERROR}: no migration registered for version {next_version}");
        };
        let operation = format!("migration {} ({})", migration.version, migration.name);
        run_transaction(conn, &operation, |tx| {
            (migration.apply)(tx).with_context(|| {
                format!(
                    "failed to apply workspace schema migration {} ({})",
                    migration.version, migration.name
                )
            })?;
            verify_foreign_key_integrity(tx)?;
            set_user_version(tx, migration.version)
        })?;
        current_version = next_version;
    }
    Ok(())
}

fn run_transaction<F>(conn: &Connection, operation: &str, work: F) -> Result<()>
where
    F: FnOnce(&Connection) -> Result<()>,
{
    let transaction = conn
        .unchecked_transaction()
        .with_context(|| format!("failed to begin workspace schema {operation}"))?;
    if let Err(error) = work(&transaction) {
        transaction.rollback().with_context(|| {
            format!("failed to roll back workspace schema {operation} after error: {error:#}")
        })?;
        return Err(error).with_context(|| format!("{MIGRATION_FAILED_ERROR}: {operation}"));
    }
    transaction
        .commit()
        .with_context(|| format!("failed to commit workspace schema {operation}"))
}

fn migrate_unversioned_workspace_to_v1(conn: &Connection) -> Result<()> {
    create_current_schema(conn)?;
    for column in LEGACY_COLUMNS {
        ensure_column_exists(conn, *column)?;
    }
    let source_orientation_added = ensure_column_exists(
        conn,
        LegacyColumn {
            table: "imported_chr_assignment",
            name: "source_orientation",
            definition: "TEXT NOT NULL DEFAULT '+' CHECK(source_orientation IN ('+', '-'))",
        },
    )?;
    ensure_column_exists(
        conn,
        LegacyColumn {
            table: "imported_chr_assignment",
            name: "orientation_source",
            definition: "TEXT NOT NULL DEFAULT 'ref_alignment' CHECK(orientation_source = 'ref_alignment')",
        },
    )?;
    if source_orientation_added {
        backfill_imported_assignment_orientation(conn)?;
    }
    let orient_added = ensure_column_exists(
        conn,
        LegacyColumn {
            table: "phased_chr_track_item",
            name: "orient",
            definition: "TEXT NOT NULL DEFAULT '+' CHECK(orient IN ('+', '-'))",
        },
    )?;
    backfill_phased_track_item_orient(conn, orient_added)
}

fn backfill_imported_assignment_orientation(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "UPDATE imported_chr_assignment
         SET source_orientation = CASE
             WHEN COALESCE((
                 SELECT SUM(hit.block_length)
                 FROM ref_alignment_hit hit
                 WHERE hit.source_seq_id = imported_chr_assignment.source_seq_id
                   AND hit.reference_chr_id = imported_chr_assignment.reference_chr_id
                   AND hit.strand = '-'
             ), 0) > COALESCE((
                 SELECT SUM(hit.block_length)
                 FROM ref_alignment_hit hit
                 WHERE hit.source_seq_id = imported_chr_assignment.source_seq_id
                   AND hit.reference_chr_id = imported_chr_assignment.reference_chr_id
                   AND hit.strand = '+'
             ), 0)
             THEN '-'
             ELSE '+'
         END",
    )
    .context("failed to backfill imported assignment source orientation")?;
    Ok(())
}

fn ensure_column_exists(conn: &Connection, column: LegacyColumn) -> Result<bool> {
    let pragma_sql = format!("PRAGMA table_info({})", column.table);
    let mut statement = conn
        .prepare(&pragma_sql)
        .with_context(|| format!("failed to inspect table schema {}", column.table))?;
    let existing_columns = statement
        .query_map([], |row| row.get::<_, String>(1))
        .with_context(|| format!("failed to read table columns {}", column.table))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .with_context(|| format!("failed to collect table columns {}", column.table))?;
    if existing_columns
        .iter()
        .any(|existing| existing == column.name)
    {
        return Ok(false);
    }

    let alter_sql = format!(
        "ALTER TABLE {} ADD COLUMN {} {}",
        column.table, column.name, column.definition
    );
    conn.execute_batch(&alter_sql).with_context(|| {
        format!(
            "failed to add missing column {}.{}",
            column.table, column.name
        )
    })?;
    Ok(true)
}

fn backfill_phased_track_item_orient(conn: &Connection, orient_added: bool) -> Result<()> {
    let invalid_only = if orient_added {
        ""
    } else {
        "WHERE orient IS NULL OR TRIM(orient) NOT IN ('+', '-')"
    };
    conn.execute_batch(&format!(
        "UPDATE phased_chr_track_item
         SET orient = COALESCE((
             SELECT s.orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.id = phased_chr_track_item.assembly_ctg_id
               AND s.orient IN ('+', '-')
         ), '+')
         {invalid_only}"
    ))
    .context("failed to backfill phased track item orient")?;
    Ok(())
}

fn verify_foreign_key_integrity(conn: &Connection) -> Result<()> {
    let violation = conn
        .query_row("PRAGMA foreign_key_check", [], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<i64>>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .optional()
        .context("failed to run sqlite foreign key check")?;
    if let Some((table, row_id, parent, foreign_key_id)) = violation {
        bail!(
            "{FOREIGN_KEY_ERROR}: table={table}, row_id={row_id:?}, parent={parent}, foreign_key_id={foreign_key_id}"
        );
    }
    Ok(())
}

fn database_has_user_tables(conn: &Connection) -> Result<bool> {
    conn.query_row(
        "SELECT EXISTS(
             SELECT 1
             FROM sqlite_schema
             WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
         )",
        [],
        |row| row.get::<_, bool>(0),
    )
    .context("failed to inspect workspace sqlite tables")
}

fn user_version(conn: &Connection) -> Result<i64> {
    conn.query_row("PRAGMA user_version", [], |row| row.get(0))
        .context("failed to read workspace sqlite user_version")
}

fn set_user_version(conn: &Connection, version: i64) -> Result<()> {
    conn.pragma_update(None, "user_version", version)
        .with_context(|| format!("failed to set workspace sqlite user_version to {version}"))
}

#[cfg(test)]
#[path = "db_migrations/tests.rs"]
mod tests;
