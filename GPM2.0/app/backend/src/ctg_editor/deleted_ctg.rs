use std::path::Path;

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::refresh_chr_order_for_chr_names;
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeletedCtgItem {
    pub deleted_ctg_record_id: i64,
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
    pub anchor_start: Option<i64>,
    pub ref_orient: Option<String>,
    pub placement_mode: String,
    pub member_count: i64,
    pub total_length: i64,
    pub deleted_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RestoreDeletedCtgParams {
    pub deleted_ctg_record_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RestoreDeletedCtgSummary {
    pub project_id: i64,
    pub deleted_ctg_record_id: i64,
    pub assembly_ctg_id: i64,
    pub restored_member_count: i64,
    pub refreshed_chr_count: i64,
}

#[derive(Debug, Clone)]
struct DeletedCtgSnapshot {
    deleted_ctg_record_id: i64,
    assembly_ctg_id: i64,
    assembly_seq_id: i64,
    name: String,
    assigned_chr_name: Option<String>,
    chr_order: Option<i64>,
    anchor_start: Option<i64>,
    ref_orient: Option<String>,
    placement_mode: String,
    created_at: String,
    note: Option<String>,
}

pub fn list_deleted_ctgs(
    project_db_path: &Path,
    project_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<DeletedCtgItem>> {
    let conn = open_workspace_db(project_db_path)?;
    list_deleted_ctgs_with_connection(&conn, project_id, chr_name, dataset_id)
}

pub fn list_deleted_ctgs_with_connection(
    conn: &Connection,
    project_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<DeletedCtgItem>> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if let Some(dataset_id) = dataset_id
        && dataset_id <= 0
    {
        bail!("dataset_id must be > 0");
    }

    let mut sql = String::from(
        "SELECT
            d.id,
            d.project_id,
            d.assembly_ctg_id,
            d.name,
            d.assigned_chr_name,
            d.chr_order,
            d.anchor_start,
            d.ref_orient,
            d.placement_mode,
            CASE WHEN s.id IS NULL THEN 0 ELSE 1 END AS member_count,
            CASE
                WHEN s.hidden = 0 AND s.source_end >= s.source_start
                THEN (s.source_end - s.source_start + 1)
                ELSE 0
            END AS total_length,
            d.deleted_at
         FROM deleted_assembly_ctg d
         LEFT JOIN assembly_seq s
           ON s.id = d.assembly_seq_id
          AND s.project_id = d.project_id
         WHERE d.project_id = ?1",
    );
    if chr_name.is_some() {
        sql.push_str(" AND d.assigned_chr_name = ?2");
    }
    if dataset_id.is_some() {
        let dataset_placeholder = if chr_name.is_some() { "?3" } else { "?2" };
        sql.push_str(&format!(
            " AND EXISTS (
                SELECT 1
                FROM assembly_seq s2
                JOIN source_seq ss2
                  ON ss2.id = s2.source_seq_id
                WHERE s2.id = d.assembly_seq_id
                  AND s2.project_id = d.project_id
                  AND ss2.dataset_id = {dataset_placeholder}
            )"
        ));
    }
    sql.push_str(
        "
         GROUP BY
            d.id,
            d.project_id,
            d.assembly_ctg_id,
            d.name,
            d.assigned_chr_name,
            d.chr_order,
            d.anchor_start,
            d.ref_orient,
            d.placement_mode,
            d.deleted_at
         ORDER BY d.id DESC",
    );

    let mut stmt = conn
        .prepare(&sql)
        .context("failed to prepare list deleted ctgs query")?;
    let rows = match (chr_name, dataset_id) {
        (Some(chr), Some(dataset_id)) => stmt
            .query_map(params![project_id, chr, dataset_id], |row| {
                Ok(DeletedCtgItem {
                    deleted_ctg_record_id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_ctg_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    member_count: row.get(9)?,
                    total_length: row.get(10)?,
                    deleted_at: row.get(11)?,
                })
            })
            .context("failed to query deleted ctgs by chr and dataset")?
            .collect::<std::result::Result<Vec<_>, _>>()
            .context("failed to decode deleted ctgs by chr and dataset")?,
        (Some(chr), None) => stmt
            .query_map(params![project_id, chr], |row| {
                Ok(DeletedCtgItem {
                    deleted_ctg_record_id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_ctg_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    member_count: row.get(9)?,
                    total_length: row.get(10)?,
                    deleted_at: row.get(11)?,
                })
            })
            .context("failed to query deleted ctgs by chr")?
            .collect::<std::result::Result<Vec<_>, _>>()
            .context("failed to decode deleted ctgs by chr")?,
        (None, Some(dataset_id)) => stmt
            .query_map(params![project_id, dataset_id], |row| {
                Ok(DeletedCtgItem {
                    deleted_ctg_record_id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_ctg_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    member_count: row.get(9)?,
                    total_length: row.get(10)?,
                    deleted_at: row.get(11)?,
                })
            })
            .context("failed to query deleted ctgs by dataset")?
            .collect::<std::result::Result<Vec<_>, _>>()
            .context("failed to decode deleted ctgs by dataset")?,
        (None, None) => stmt
            .query_map(params![project_id], |row| {
                Ok(DeletedCtgItem {
                    deleted_ctg_record_id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_ctg_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    member_count: row.get(9)?,
                    total_length: row.get(10)?,
                    deleted_at: row.get(11)?,
                })
            })
            .context("failed to query deleted ctgs")?
            .collect::<std::result::Result<Vec<_>, _>>()
            .context("failed to decode deleted ctgs")?,
    };

    Ok(rows)
}

pub fn restore_deleted_ctg(
    project_db_path: &Path,
    project_id: i64,
    params: &RestoreDeletedCtgParams,
) -> Result<RestoreDeletedCtgSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    restore_deleted_ctg_with_connection(&mut conn, project_id, params)
}

pub fn restore_deleted_ctg_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &RestoreDeletedCtgParams,
) -> Result<RestoreDeletedCtgSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.deleted_ctg_record_id <= 0 {
        bail!("deleted_ctg_record_id must be > 0");
    }

    let tx = conn.transaction()?;

    let snapshot = tx
        .query_row(
            "SELECT
                id,
                assembly_ctg_id,
                assembly_seq_id,
                name,
                assigned_chr_name,
                chr_order,
                anchor_start,
                ref_orient,
                placement_mode,
                created_at,
                note
             FROM deleted_assembly_ctg
             WHERE id = ?1
               AND project_id = ?2",
            params![params.deleted_ctg_record_id, project_id],
            |row| {
                Ok(DeletedCtgSnapshot {
                    deleted_ctg_record_id: row.get(0)?,
                    assembly_ctg_id: row.get(1)?,
                    assembly_seq_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    created_at: row.get(9)?,
                    note: row.get(10)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "deleted_ctg_record_id {} does not exist in project_id {}",
                params.deleted_ctg_record_id,
                project_id
            )
        })?;

    let existing_ctg_id: Option<i64> = tx
        .query_row(
            "SELECT id FROM assembly_ctg WHERE id = ?1",
            params![snapshot.assembly_ctg_id],
            |row| row.get(0),
        )
        .optional()?;
    if existing_ctg_id.is_some() {
        bail!(
            "assembly_ctg_id {} already exists, cannot restore deleted_ctg_record_id {}",
            snapshot.assembly_ctg_id,
            snapshot.deleted_ctg_record_id
        );
    }

    let conflicting_name: Option<i64> = tx
        .query_row(
            "SELECT id
             FROM assembly_ctg
             WHERE project_id = ?1
               AND name = ?2",
            params![project_id, snapshot.name.as_str()],
            |row| row.get(0),
        )
        .optional()?;
    if conflicting_name.is_some() {
        bail!(
            "ctg name '{}' already exists in project_id {}, cannot restore deleted_ctg_record_id {}",
            snapshot.name,
            project_id,
            snapshot.deleted_ctg_record_id
        );
    }

    let seq_project_id: Option<i64> = tx
        .query_row(
            "SELECT project_id FROM assembly_seq WHERE id = ?1",
            params![snapshot.assembly_seq_id],
            |row| row.get(0),
        )
        .optional()?;
    if seq_project_id != Some(project_id) {
        bail!(
            "assembly_seq_id {} is missing or not in project_id {}",
            snapshot.assembly_seq_id,
            project_id
        );
    }

    tx.execute(
        "INSERT INTO assembly_ctg (
            id,
            project_id,
            assembly_seq_id,
            name,
            assigned_chr_name,
            chr_order,
            anchor_start,
            ref_orient,
            placement_mode,
            created_at,
            note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
        params![
            snapshot.assembly_ctg_id,
            project_id,
            snapshot.assembly_seq_id,
            snapshot.name.as_str(),
            snapshot.assigned_chr_name.as_deref(),
            snapshot.chr_order,
            snapshot.anchor_start,
            snapshot.ref_orient.as_deref(),
            snapshot.placement_mode.as_str(),
            snapshot.created_at.as_str(),
            snapshot.note.as_deref()
        ],
    )?;

    let mut refreshed_chr_count = 0_i64;
    if let Some(chr_name) = snapshot.assigned_chr_name.clone() {
        refreshed_chr_count = refresh_chr_order_for_chr_names(&tx, project_id, &[chr_name])?;
    }

    tx.execute(
        "DELETE FROM deleted_assembly_ctg
         WHERE id = ?1",
        params![snapshot.deleted_ctg_record_id],
    )?;

    tx.commit()?;

    Ok(RestoreDeletedCtgSummary {
        project_id,
        deleted_ctg_record_id: snapshot.deleted_ctg_record_id,
        assembly_ctg_id: snapshot.assembly_ctg_id,
        restored_member_count: 1,
        refreshed_chr_count,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        RestoreDeletedCtgParams, list_deleted_ctgs_with_connection,
        restore_deleted_ctg_with_connection,
    };
    use crate::ctg_editor::DeleteCtgParams;
    use crate::ctg_editor::common::test_utils::{
        insert_second_ctg, seed_workspace_with_two_member_ctg,
    };
    use crate::ctg_editor::delete_ctg_with_connection;
    use rusqlite::Connection;

    #[test]
    fn deleted_ctg_can_be_listed_and_restored() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        delete_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &DeleteCtgParams {
                assembly_ctg_id: seed.ctg_id,
            },
        )
        .unwrap();

        let deleted =
            list_deleted_ctgs_with_connection(&conn, seed.project_id, Some("Chr01"), None).unwrap();
        assert_eq!(deleted.len(), 1);
        assert_eq!(deleted[0].assembly_ctg_id, seed.ctg_id);
        assert_eq!(deleted[0].member_count, 1);

        let summary = restore_deleted_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &RestoreDeletedCtgParams {
                deleted_ctg_record_id: deleted[0].deleted_ctg_record_id,
            },
        )
        .unwrap();
        assert_eq!(summary.assembly_ctg_id, seed.ctg_id);
        assert_eq!(summary.restored_member_count, 1);

        let ctg_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM assembly_ctg WHERE id = ?1",
                [seed.ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(ctg_count, 1);

        let restored_seq_id: i64 = conn
            .query_row(
                "SELECT assembly_seq_id FROM assembly_ctg WHERE id = ?1",
                [seed.ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(restored_seq_id, seed.seq_a_id);

        let deleted_after =
            list_deleted_ctgs_with_connection(&conn, seed.project_id, None, None).unwrap();
        assert!(deleted_after.is_empty());
    }

    #[test]
    fn restore_deleted_ctg_rejects_name_conflict() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        delete_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &DeleteCtgParams {
                assembly_ctg_id: seed.ctg_id,
            },
        )
        .unwrap();
        insert_second_ctg(&conn, seed.project_id, 302, "Ctg1").unwrap();

        let deleted =
            list_deleted_ctgs_with_connection(&conn, seed.project_id, None, None).unwrap();
        let error = restore_deleted_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &RestoreDeletedCtgParams {
                deleted_ctg_record_id: deleted[0].deleted_ctg_record_id,
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("already exists"));
    }
}
