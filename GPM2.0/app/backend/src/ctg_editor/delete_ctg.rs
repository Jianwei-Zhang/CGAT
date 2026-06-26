use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::{load_ctg_members, refresh_chr_order_for_chr_names};
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeleteCtgParams {
    pub assembly_ctg_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeleteCtgSummary {
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub released_assembly_seq_ids: Vec<i64>,
    pub released_assembly_seq_count: i64,
    pub refreshed_chr_count: i64,
}

#[derive(Debug, Clone)]
struct CtgState {
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

pub fn delete_ctg(
    project_db_path: &Path,
    project_id: i64,
    params: &DeleteCtgParams,
) -> Result<DeleteCtgSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    delete_ctg_with_connection(&mut conn, project_id, params)
}

pub fn delete_ctg_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &DeleteCtgParams,
) -> Result<DeleteCtgSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.assembly_ctg_id <= 0 {
        bail!("assembly_ctg_id must be > 0");
    }

    let tx = conn.transaction()?;
    let ctg = tx
        .query_row(
            "SELECT
                id,
                assembly_seq_id,
                name,
                assigned_chr_name,
                chr_order,
                anchor_start,
                ref_orient,
                placement_mode,
                created_at,
                note
             FROM assembly_ctg
             WHERE project_id = ?1
               AND id = ?2",
            params![project_id, params.assembly_ctg_id],
            |row| {
                Ok(CtgState {
                    assembly_ctg_id: row.get(0)?,
                    assembly_seq_id: row.get(1)?,
                    name: row.get(2)?,
                    assigned_chr_name: row.get(3)?,
                    chr_order: row.get(4)?,
                    anchor_start: row.get(5)?,
                    ref_orient: row.get(6)?,
                    placement_mode: row.get(7)?,
                    created_at: row.get(8)?,
                    note: row.get(9)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_ctg_id {} does not exist in project_id {}",
                params.assembly_ctg_id,
                project_id
            )
        })?;

    let released_assembly_seq_ids = load_ctg_members(&tx, ctg.assembly_ctg_id)?
        .into_iter()
        .map(|member| member.assembly_seq_id)
        .collect::<Vec<_>>();

    tx.execute(
        "INSERT INTO deleted_assembly_ctg (
            project_id,
            assembly_ctg_id,
            assembly_seq_id,
            name,
            assigned_chr_name,
            chr_order,
            anchor_start,
            ref_orient,
            placement_mode,
            created_at,
            note,
            deleted_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, strftime('%s','now'))",
        params![
            project_id,
            ctg.assembly_ctg_id,
            ctg.assembly_seq_id,
            ctg.name.as_str(),
            ctg.assigned_chr_name.as_deref(),
            ctg.chr_order,
            ctg.anchor_start,
            ctg.ref_orient.as_deref(),
            ctg.placement_mode.as_str(),
            ctg.created_at.as_str(),
            ctg.note.as_deref()
        ],
    )?;
    tx.execute(
        "DELETE FROM assembly_ctg
         WHERE id = ?1",
        params![ctg.assembly_ctg_id],
    )?;

    let mut refreshed_chr_count = 0_i64;
    if let Some(chr_name) = ctg.assigned_chr_name.clone() {
        refreshed_chr_count = refresh_chr_order_for_chr_names(&tx, project_id, &[chr_name])?;
    }

    tx.commit()?;

    Ok(DeleteCtgSummary {
        project_id,
        assembly_ctg_id: ctg.assembly_ctg_id,
        released_assembly_seq_count: released_assembly_seq_ids.len() as i64,
        released_assembly_seq_ids,
        refreshed_chr_count,
    })
}

#[cfg(test)]
mod tests {
    use super::{DeleteCtgParams, delete_ctg_with_connection};
    use crate::ctg_editor::common::test_utils::seed_workspace_with_two_member_ctg;
    use rusqlite::Connection;

    #[test]
    fn deletes_ctg_and_releases_members() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let summary = delete_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &DeleteCtgParams {
                assembly_ctg_id: seed.ctg_id,
            },
        )
        .unwrap();
        assert_eq!(summary.released_assembly_seq_count, 1);
        assert_eq!(summary.released_assembly_seq_ids, vec![seed.seq_a_id]);

        let ctg_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM assembly_ctg WHERE id = ?1",
                [seed.ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(ctg_count, 0);

        let deleted_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM deleted_assembly_ctg WHERE project_id = ?1",
                [seed.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(deleted_count, 1);

        let deleted_seq_id: i64 = conn
            .query_row(
                "SELECT assembly_seq_id FROM deleted_assembly_ctg WHERE project_id = ?1",
                [seed.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(deleted_seq_id, seed.seq_a_id);
    }
}
