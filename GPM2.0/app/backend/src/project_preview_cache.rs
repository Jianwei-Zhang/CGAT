//! Derived Preview snapshots. Content revisions are changed by SQL triggers in
//! the same transaction as the source edit, never by viewport/cache writes.
use std::path::Path;

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde_json::{Value, json};

use crate::db::open_workspace_db;

pub(crate) fn create_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS project_preview_schema (
            id INTEGER PRIMARY KEY CHECK(id = 1), version INTEGER NOT NULL
         );
         CREATE TABLE IF NOT EXISTS project_preview_revision (
            project_id INTEGER PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
            identity TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
            revision INTEGER NOT NULL DEFAULT 0
         );
         CREATE TABLE IF NOT EXISTS project_preview_dirty (
            project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            chr_name TEXT NOT NULL,
            revision INTEGER NOT NULL,
            PRIMARY KEY(project_id, chr_name)
         );
         CREATE TABLE IF NOT EXISTS project_preview_cache (
            project_id INTEGER PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
            model_version INTEGER NOT NULL,
            identity TEXT NOT NULL,
            revision INTEGER NOT NULL,
            payload_json TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS project_preview_dependency (
            project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            chr_name TEXT NOT NULL,
            assembly_ctg_id INTEGER NOT NULL,
            PRIMARY KEY(project_id, chr_name, assembly_ctg_id)
         );
         CREATE TABLE IF NOT EXISTS project_preview_source_dependency (
            project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            chr_name TEXT NOT NULL, dataset_name TEXT NOT NULL, contig_name TEXT NOT NULL,
            PRIMARY KEY(project_id, chr_name, dataset_name, contig_name)
         );
         CREATE INDEX IF NOT EXISTS idx_preview_source_dependency
            ON project_preview_source_dependency(project_id, dataset_name, contig_name);
         CREATE INDEX IF NOT EXISTS idx_preview_dependency_ctg
            ON project_preview_dependency(project_id, assembly_ctg_id);",
    )?;

    // Only projects which have requested Preview have revision rows: initial
    // bulk import pays no per-row derived-cache maintenance for unused projects.
    install(
        conn,
        "assembly_ctg",
        &[
            "project_id",
            "assembly_seq_id",
            "name",
            "assigned_chr_name",
            "anchor_start",
            "ref_orient",
            "chr_order",
            "note",
        ],
        |row| {
            format!("SELECT {row}.project_id AS project_id, COALESCE(NULLIF({row}.assigned_chr_name, ''), '*') AS chr_name
                 UNION SELECT project_id, chr_name FROM project_preview_dependency
                 WHERE project_id = {row}.project_id AND assembly_ctg_id = {row}.id
                 UNION SELECT d.project_id, d.chr_name FROM project_preview_source_dependency d
                   JOIN assembly_seq a ON a.id = {row}.assembly_seq_id
                   JOIN source_seq ss ON ss.id = a.source_seq_id JOIN dataset ds ON ds.id = ss.dataset_id
                   WHERE d.project_id = {row}.project_id AND d.dataset_name = ds.name AND d.contig_name = ss.seq_name")
        },
    )?;
    install(
        conn,
        "assembly_seq",
        &[
            "project_id",
            "source_seq_id",
            "source_start",
            "source_end",
            "orient",
            "hidden",
            "instance_key",
        ],
        |row| {
            format!(
                "SELECT c.project_id, COALESCE(NULLIF(c.assigned_chr_name, ''), '*') AS chr_name
                 FROM assembly_ctg c WHERE c.assembly_seq_id = {row}.id
                 UNION SELECT d.project_id, d.chr_name FROM project_preview_dependency d
                 JOIN assembly_ctg c ON c.id = d.assembly_ctg_id AND c.project_id = d.project_id
                 WHERE c.assembly_seq_id = {row}.id
                 UNION SELECT d.project_id, d.chr_name FROM project_preview_source_dependency d
                   JOIN source_seq ss ON ss.id = {row}.source_seq_id JOIN dataset ds ON ds.id = ss.dataset_id
                   WHERE d.project_id = {row}.project_id AND d.dataset_name = ds.name AND d.contig_name = ss.seq_name"
            )
        },
    )?;
    if has_columns(
        conn,
        "project_assembly_view_state",
        &["project_id", "final_path_by_chr_json"],
    )? {
        let path_scopes = |row: &str| {
            // Both maps are visited on UPDATE, including removed/empty paths.
            // Bad legacy JSON cannot make source saves fail: conservatively dirty all.
            format!("SELECT {row}.project_id AS project_id,
                   COALESCE((SELECT parent_chr_name FROM phased_chr_track
                     WHERE project_id = {row}.project_id AND label = paths.key LIMIT 1), paths.key) AS chr_name
                 FROM json_each(CASE WHEN json_valid({row}.final_path_by_chr_json)
                   THEN {row}.final_path_by_chr_json ELSE '{{}}' END) paths
                 WHERE paths.type = 'object' AND (
                   CASE WHEN json_valid(OLD.final_path_by_chr_json) AND json_valid(NEW.final_path_by_chr_json)
                     THEN json_extract(json_remove(OLD.final_path_by_chr_json, '$.' || json_quote(paths.key) || '.updatedAt'), '$.' || json_quote(paths.key))
                       IS NOT json_extract(json_remove(NEW.final_path_by_chr_json, '$.' || json_quote(paths.key) || '.updatedAt'), '$.' || json_quote(paths.key))
                     ELSE 1 END)
                 UNION SELECT {row}.project_id, '*' WHERE NOT json_valid({row}.final_path_by_chr_json)")
        };
        install_event(
            conn,
            "project_assembly_view_state",
            "UPDATE",
            "OLD.final_path_by_chr_json IS NOT NEW.final_path_by_chr_json",
            &format!("{} UNION {}", path_scopes("OLD"), path_scopes("NEW")),
        )?;
        // First view-state insertion/removal is conservatively project-wide.
        for event in ["INSERT", "DELETE"] {
            let row = if event == "INSERT" { "NEW" } else { "OLD" };
            install_event(
                conn,
                "project_assembly_view_state",
                event,
                "1",
                &format!("SELECT {row}.project_id AS project_id, '*' AS chr_name"),
            )?;
        }
    }
    install(
        conn,
        "project",
        &[
            "reference_genome_id",
            "primary_dataset_id",
            "phased_assembly_enabled",
            "chr_assignment_min_coverage_percent",
        ],
        |row| format!("SELECT {row}.id AS project_id, '*' AS chr_name"),
    )?;
    install(
        conn,
        "project_dataset",
        &["project_id", "dataset_id", "dataset_role", "display_order"],
        project_scope,
    )?;
    install(
        conn,
        "derived_ctg_track_member",
        &[
            "project_id",
            "source_seq_id",
            "target_dataset_id",
            "target_chr_name",
        ],
        project_scope,
    )?;
    install(
        conn,
        "phased_chr_track",
        &[
            "project_id",
            "parent_chr_name",
            "label",
            "haplotype_key",
            "display_order",
        ],
        |row| format!("SELECT {row}.project_id AS project_id, {row}.parent_chr_name AS chr_name"),
    )?;
    install(
        conn,
        "phased_chr_track_item",
        &[
            "phased_track_id",
            "assembly_ctg_id",
            "display_order",
            "orient",
        ],
        |row| {
            format!(
                "SELECT project_id, parent_chr_name AS chr_name FROM phased_chr_track WHERE id = {row}.phased_track_id"
            )
        },
    )?;
    install(conn, "dataset", &["name", "display_name"], |row| {
        format!(
            "{} UNION SELECT project_id, '*' AS chr_name FROM project_preview_source_dependency WHERE dataset_name = {row}.name",
            dataset_scope(&format!("{row}.id"))
        )
    })?;
    install(
        conn,
        "source_seq",
        &["dataset_id", "seq_name", "length"],
        |row| dataset_scope(&format!("{row}.dataset_id")),
    )?;
    install(
        conn,
        "reference_chr",
        &["reference_genome_id", "chr_name", "chr_order", "length"],
        |row| {
            format!(
                "SELECT id AS project_id, '*' AS chr_name FROM project WHERE reference_genome_id = {row}.reference_genome_id"
            )
        },
    )?;
    for (table, columns) in [
        (
            "imported_chr_assignment",
            vec![
                "source_seq_id",
                "reference_chr_id",
                "source_orientation",
                "anchor_start",
                "support_bp",
                "support_percent",
            ],
        ),
        (
            "ref_alignment_hit",
            vec![
                "source_seq_id",
                "reference_chr_id",
                "ref_start",
                "ref_end",
                "strand",
                "query_start",
                "query_end",
                "match_length",
                "block_length",
                "mapq",
                "cg_tag",
            ],
        ),
        (
            "imported_track_member_order",
            vec![
                "source_seq_id",
                "target_dataset_id",
                "reference_chr_id",
                "member_order",
            ],
        ),
        ("derived_ctg", vec!["source_seq_id", "source"]),
        (
            "source_seq_n_region",
            vec!["source_seq_id", "start_bp", "end_bp", "length_bp"],
        ),
    ] {
        install(conn, table, &columns, |row| {
            dataset_scope(&format!(
                "(SELECT dataset_id FROM source_seq WHERE id = {row}.source_seq_id)"
            ))
        })?;
    }
    // Baseline content is shared by project views in the imported workspace.
    for (table, columns) in [
        (
            "grt_package",
            vec![
                "final_path_json",
                "primary_dataset",
                "support_datasets_json",
                "workflow",
                "schema_version",
                "final_path_schema_version",
            ],
        ),
        (
            "grt_final_path_chr",
            vec!["chr", "q4_length", "chromosome_json"],
        ),
        (
            "grt_final_path_segment",
            vec!["chr", "segment_order", "segment_json"],
        ),
    ] {
        install(conn, table, &columns, |_| {
            "SELECT project_id, '*' AS chr_name FROM project_preview_revision".to_owned()
        })?;
    }
    conn.execute(
        "INSERT OR REPLACE INTO project_preview_schema(id, version) VALUES (1, 3)",
        [],
    )?;
    Ok(())
}

fn project_scope(row: &str) -> String {
    format!("SELECT {row}.project_id AS project_id, '*' AS chr_name")
}

fn dataset_scope(dataset: &str) -> String {
    format!("SELECT p.id AS project_id, '*' AS chr_name FROM project p
             WHERE p.primary_dataset_id = {dataset} OR EXISTS
               (SELECT 1 FROM project_dataset d WHERE d.project_id = p.id AND d.dataset_id = {dataset})
             OR EXISTS (SELECT 1 FROM assembly_seq a JOIN source_seq s ON s.id = a.source_seq_id
               WHERE a.project_id = p.id AND s.dataset_id = {dataset})
             OR EXISTS (SELECT 1 FROM project_preview_source_dependency d
               WHERE d.project_id = p.id AND d.dataset_name = (SELECT name FROM dataset WHERE id = {dataset}))")
}

fn install<F>(conn: &Connection, table: &str, columns: &[&str], scopes: F) -> Result<()>
where
    F: Fn(&str) -> String,
{
    // Minimal legacy migration fixtures can lack feature tables/columns. Actual
    // workspaces have the complete source schema before optional cache installation.
    if !has_columns(conn, table, columns)? {
        return Ok(());
    }
    for event in ["INSERT", "UPDATE", "DELETE"] {
        let scope = match event {
            "INSERT" => scopes("NEW"),
            "DELETE" => scopes("OLD"),
            _ => format!("{} UNION {}", scopes("OLD"), scopes("NEW")),
        };
        let when = if event == "UPDATE" {
            columns
                .iter()
                .map(|c| format!("OLD.{c} IS NOT NEW.{c}"))
                .collect::<Vec<_>>()
                .join(" OR ")
        } else {
            "1".to_owned()
        };
        install_event(conn, table, event, &when, &scope)?;
    }
    Ok(())
}

fn has_columns(conn: &Connection, table: &str, columns: &[&str]) -> Result<bool> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let existing = stmt
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(columns
        .iter()
        .all(|column| existing.iter().any(|name| name.as_str() == *column)))
}

fn install_event(
    conn: &Connection,
    table: &str,
    event: &str,
    when: &str,
    scopes: &str,
) -> Result<()> {
    conn.execute_batch(&format!(
        "CREATE TRIGGER IF NOT EXISTS preview_v1_{table}_{event_name} AFTER {event} ON {table}
         WHEN {when}
         BEGIN
           UPDATE project_preview_revision SET revision = revision + 1
             WHERE project_id IN (SELECT project_id FROM ({scopes}))
               AND EXISTS(SELECT 1 FROM project p WHERE p.id = project_preview_revision.project_id);
           INSERT INTO project_preview_dirty(project_id, chr_name, revision)
             SELECT target.project_id, target.chr_name, r.revision FROM ({scopes}) target
             JOIN project_preview_revision r ON r.project_id = target.project_id
             JOIN project p ON p.id = r.project_id
             WHERE target.chr_name IS NOT NULL
             GROUP BY target.project_id, target.chr_name
             ON CONFLICT(project_id, chr_name) DO UPDATE SET revision = excluded.revision;
         END;",
        event_name = event.to_lowercase()
    ))
    .with_context(|| format!("failed to install Preview invalidation for {table}/{event}"))
}

fn ensure_cache_schema(conn: &Connection) -> Result<()> {
    let installed: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_preview_schema')",
        [], |row| row.get(0),
    )?;
    let version = if installed {
        conn.query_row(
            "SELECT version FROM project_preview_schema WHERE id = 1",
            [],
            |row| row.get::<_, i64>(0),
        )?
    } else {
        0
    };
    if version == 3 {
        return Ok(());
    }
    if !(0..=3).contains(&version) {
        bail!("unsupported derived Preview cache schema {version}");
    }
    // Optional derived-cache migration, independent of mandatory project reads.
    let tx = conn.unchecked_transaction()?;
    let legacy_tables: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_preview_revision')", [], |row| row.get(0))?;
    if version == 1 || version == 2 || (version == 0 && legacy_tables) {
        let names = {
            let mut stmt = tx.prepare("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'preview_v1_%'")?;
            stmt.query_map([], |row| row.get::<_, String>(0))?
                .collect::<rusqlite::Result<Vec<_>>>()?
        };
        for name in names {
            tx.execute_batch(&format!("DROP TRIGGER \"{}\";", name.replace('"', "\"\"")))?;
        }
        if has_columns(&tx, "project_preview_source_dependency", &["project_id"])? {
            tx.execute("DELETE FROM project_preview_source_dependency", [])?;
        }
        tx.execute_batch("DELETE FROM project_preview_cache;
            DELETE FROM project_preview_dependency;
            DELETE FROM project_preview_dirty;
            UPDATE project_preview_revision SET identity = lower(hex(randomblob(16))), revision = 0;")?;
    }
    create_schema(&tx)?;
    tx.commit()?;
    Ok(())
}

fn revision(conn: &Connection, project_id: i64) -> Result<(String, i64)> {
    let current = conn
        .query_row(
            "SELECT identity, revision FROM project_preview_revision WHERE project_id = ?1",
            [project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    if let Some(value) = current {
        return Ok(value);
    }
    let exists = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM project WHERE id = ?1)",
        [project_id],
        |row| row.get::<_, bool>(0),
    )?;
    if !exists {
        bail!("project_id {project_id} does not exist");
    }
    conn.execute(
        "INSERT OR IGNORE INTO project_preview_revision(project_id) VALUES (?1)",
        [project_id],
    )?;
    Ok(conn.query_row(
        "SELECT identity, revision FROM project_preview_revision WHERE project_id = ?1",
        [project_id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?)
}

pub fn get_project_preview_cache(
    db: &Path,
    project_id: i64,
    model_version: i64,
    expected_identity: Option<&str>,
    since_revision: Option<i64>,
) -> Result<Value> {
    let mut conn = open_workspace_db(db)?;
    ensure_cache_schema(&conn)?;
    let tx = conn.transaction()?;
    let (identity, current) = revision(&tx, project_id)?;
    let memory_valid =
        expected_identity == Some(identity.as_str()) && since_revision == Some(current);
    let cached: Option<(i64, String, i64, String)> = if memory_valid {
        None
    } else {
        tx.query_row("SELECT model_version, identity, revision, payload_json FROM project_preview_cache WHERE project_id = ?1",
            [project_id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))).optional()?
    };
    let snapshot = cached
        .as_ref()
        .filter(|(version, epoch, _, _)| *version == model_version && epoch == &identity)
        .and_then(|(_, _, _, payload)| serde_json::from_str::<Value>(payload).ok());
    let snapshot_revision = cached.as_ref().map(|(_, _, rev, _)| *rev);
    let since = if expected_identity == Some(identity.as_str()) {
        since_revision
    } else if snapshot.is_some() {
        snapshot_revision
    } else {
        None
    };
    let mut dirty = Vec::<String>::new();
    if !memory_valid {
        if let Some(since) = since.filter(|rev| *rev >= 0 && *rev <= current) {
            let mut stmt = tx.prepare("SELECT chr_name FROM project_preview_dirty WHERE project_id = ?1 AND revision > ?2 ORDER BY chr_name")?;
            dirty = stmt
                .query_map(params![project_id, since], |row| row.get(0))?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            if since != current && dirty.is_empty() {
                dirty.push("*".to_owned());
            }
        } else {
            dirty.push("*".to_owned());
        }
    }
    let valid = memory_valid || (snapshot.is_some() && snapshot_revision == Some(current));
    let source_metadata = if memory_valid {
        Value::Null
    } else {
        let project = tx.query_row(
            "SELECT primary_dataset_id, phased_assembly_enabled FROM project WHERE id = ?1",
            [project_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, bool>(1)?)),
        )?;
        let support_ids = {
            let mut stmt = tx.prepare("SELECT dataset_id FROM project_dataset WHERE project_id = ?1 AND dataset_role = 'support' ORDER BY display_order, id")?;
            stmt.query_map([project_id], |row| row.get::<_, i64>(0))?
                .collect::<rusqlite::Result<Vec<_>>>()?
        };
        let datasets = {
            let mut stmt = tx.prepare("SELECT id, name FROM dataset ORDER BY id")?;
            stmt.query_map([], |row| {
                Ok(json!({"datasetId": row.get::<_, i64>(0)?, "name": row.get::<_, String>(1)?}))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?
        };
        json!({"project": {"primaryDatasetId": project.0, "phasedAssemblyEnabled": project.1, "supportDatasetIds": support_ids}, "datasets": datasets})
    };
    tx.commit()?;
    Ok(
        json!({"available": true, "identity": identity, "revision": current,
        "trackingVersion": 3, "memoryValid": memory_valid, "valid": valid, "snapshot": snapshot,
        "snapshotRevision": snapshot_revision, "dirtyChrNames": dirty, "sourceMetadata": source_metadata}),
    )
}

pub fn put_project_preview_cache(
    db: &Path,
    project_id: i64,
    model_version: i64,
    expected_identity: &str,
    expected_revision: i64,
    payload: &Value,
) -> Result<Value> {
    if model_version < 1
        || !payload.get("cards").is_some_and(Value::is_array)
        || payload.get("modelVersion").and_then(Value::as_i64) != Some(model_version)
        || !payload
            .get("dependencies")
            .and_then(Value::as_array)
            .is_some_and(|rows| {
                rows.iter()
                    .all(|row| row.get("sourceNames").is_some_and(Value::is_array))
            })
    {
        bail!("invalid Preview cache payload/version");
    }
    let mut conn = open_workspace_db(db)?;
    ensure_cache_schema(&conn)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let (identity, current) = revision(&tx, project_id)?;
    if identity != expected_identity || current != expected_revision {
        return Ok(
            json!({"stored": false, "superseded": true, "identity": identity, "revision": current}),
        );
    }
    tx.execute("INSERT INTO project_preview_cache(project_id, model_version, identity, revision, payload_json)
        VALUES (?1, ?2, ?3, ?4, ?5) ON CONFLICT(project_id) DO UPDATE SET
        model_version = excluded.model_version, identity = excluded.identity,
        revision = excluded.revision, payload_json = excluded.payload_json",
        params![project_id, model_version, identity, current, serde_json::to_string(payload)?])?;
    tx.execute(
        "DELETE FROM project_preview_dependency WHERE project_id = ?1",
        [project_id],
    )?;
    tx.execute(
        "DELETE FROM project_preview_source_dependency WHERE project_id = ?1",
        [project_id],
    )?;
    if let Some(dependencies) = payload.get("dependencies").and_then(Value::as_array) {
        for dependency in dependencies {
            let Some(chr) = dependency.get("chrName").and_then(Value::as_str) else {
                continue;
            };
            if let Some(sources) = dependency.get("sourceNames").and_then(Value::as_array) {
                for source in sources {
                    if let (Some(dataset), Some(contig)) = (
                        source.get("datasetName").and_then(Value::as_str),
                        source.get("contigName").and_then(Value::as_str),
                    ) {
                        tx.execute("INSERT OR IGNORE INTO project_preview_source_dependency(project_id, chr_name, dataset_name, contig_name) VALUES (?1, ?2, ?3, ?4)", params![project_id, chr, dataset, contig])?;
                    }
                }
            }
            if let Some(ids) = dependency.get("ctgIds").and_then(Value::as_array) {
                for id in ids.iter().filter_map(Value::as_i64).filter(|id| *id > 0) {
                    tx.execute("INSERT OR IGNORE INTO project_preview_dependency(project_id, chr_name, assembly_ctg_id) VALUES (?1, ?2, ?3)",
                        params![project_id, chr, id])?;
                }
            }
        }
    }
    tx.commit()?;
    Ok(json!({"stored": true, "identity": identity, "revision": current}))
}

#[cfg(test)]
mod tests;
