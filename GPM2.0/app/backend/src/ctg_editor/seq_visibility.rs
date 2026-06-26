use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::mark_ctg_manual;
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HideSeqParams {
    pub assembly_seq_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShowSeqParams {
    pub assembly_seq_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeqVisibilitySummary {
    pub project_id: i64,
    pub assembly_seq_id: i64,
    pub assembly_ctg_id: i64,
    pub hidden: bool,
    pub ref_orient: Option<String>,
    pub changed: bool,
}

#[derive(Debug, Clone)]
struct SeqVisibilityState {
    assembly_seq_id: i64,
    assembly_ctg_id: i64,
    hidden: i64,
    ctg_ref_orient: Option<String>,
}

pub fn hide_seq(
    project_db_path: &Path,
    project_id: i64,
    params: &HideSeqParams,
) -> Result<SeqVisibilitySummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    hide_seq_with_connection(&mut conn, project_id, params)
}

pub fn show_seq(
    project_db_path: &Path,
    project_id: i64,
    params: &ShowSeqParams,
) -> Result<SeqVisibilitySummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    show_seq_with_connection(&mut conn, project_id, params)
}

pub fn hide_seq_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &HideSeqParams,
) -> Result<SeqVisibilitySummary> {
    set_seq_visibility_with_connection(conn, project_id, params.assembly_seq_id, true)
}

pub fn show_seq_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &ShowSeqParams,
) -> Result<SeqVisibilitySummary> {
    set_seq_visibility_with_connection(conn, project_id, params.assembly_seq_id, false)
}

fn set_seq_visibility_with_connection(
    conn: &mut Connection,
    project_id: i64,
    assembly_seq_id: i64,
    hidden: bool,
) -> Result<SeqVisibilitySummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if assembly_seq_id <= 0 {
        bail!("assembly_seq_id must be > 0");
    }

    let target_hidden = if hidden { 1 } else { 0 };

    let tx = conn.transaction()?;
    let before = tx
        .query_row(
            "SELECT s.id,
                    c.id,
                    s.hidden,
                    c.ref_orient
             FROM assembly_seq s
             JOIN assembly_ctg c
               ON c.assembly_seq_id = s.id
             WHERE s.project_id = ?1
               AND c.project_id = ?1
               AND s.id = ?2",
            params![project_id, assembly_seq_id],
            |row| {
                Ok(SeqVisibilityState {
                    assembly_seq_id: row.get(0)?,
                    assembly_ctg_id: row.get(1)?,
                    hidden: row.get(2)?,
                    ctg_ref_orient: row.get(3)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_seq_id {} does not exist in project_id {}",
                assembly_seq_id,
                project_id
            )
        })?;

    let changed = before.hidden != target_hidden;
    let mut ref_orient_after = before.ctg_ref_orient.clone();
    if changed {
        tx.execute(
            "UPDATE assembly_seq
             SET hidden = ?1
             WHERE id = ?2",
            params![target_hidden, before.assembly_seq_id],
        )?;
        tx.execute(
            "UPDATE assembly_ctg
             SET ref_orient = NULL
             WHERE id = ?1",
            params![before.assembly_ctg_id],
        )?;
        mark_ctg_manual(&tx, before.assembly_ctg_id)?;
        ref_orient_after = None;
    }

    tx.commit()?;

    Ok(SeqVisibilitySummary {
        project_id,
        assembly_seq_id: before.assembly_seq_id,
        assembly_ctg_id: before.assembly_ctg_id,
        hidden,
        ref_orient: ref_orient_after,
        changed,
    })
}

#[cfg(test)]
mod tests {
    use super::{HideSeqParams, ShowSeqParams, hide_seq_with_connection, show_seq_with_connection};
    use crate::ctg_editor::common::test_utils::seed_workspace_with_two_member_ctg;
    use rusqlite::Connection;

    #[test]
    fn hide_then_show_seq() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let hidden = hide_seq_with_connection(
            &mut conn,
            seed.project_id,
            &HideSeqParams {
                assembly_seq_id: seed.seq_a_id,
            },
        )
        .unwrap();
        assert!(hidden.hidden);
        assert_eq!(hidden.ref_orient, None);

        let shown = show_seq_with_connection(
            &mut conn,
            seed.project_id,
            &ShowSeqParams {
                assembly_seq_id: seed.seq_a_id,
            },
        )
        .unwrap();
        assert!(!shown.hidden);

        let final_hidden: i64 = conn
            .query_row(
                "SELECT hidden FROM assembly_seq WHERE id = ?1",
                [seed.seq_a_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(final_hidden, 0);
    }
}
