use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::{flip_orient, mark_ctg_manual};
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlipSeqParams {
    pub assembly_seq_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlipSeqSummary {
    pub project_id: i64,
    pub assembly_seq_id: i64,
    pub assembly_ctg_id: i64,
    pub orient: String,
    pub left_end_type: String,
    pub right_end_type: String,
    pub ref_orient: Option<String>,
}

#[derive(Debug, Clone)]
struct SeqRow {
    assembly_seq_id: i64,
    assembly_ctg_id: i64,
    orient: String,
    left_end_type: String,
    right_end_type: String,
}

pub fn flip_seq(
    project_db_path: &Path,
    project_id: i64,
    params: &FlipSeqParams,
) -> Result<FlipSeqSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    flip_seq_with_connection(&mut conn, project_id, params)
}

pub fn flip_seq_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &FlipSeqParams,
) -> Result<FlipSeqSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.assembly_seq_id <= 0 {
        bail!("assembly_seq_id must be > 0");
    }

    let tx = conn.transaction()?;
    let before = tx
        .query_row(
            "SELECT s.id, c.id, s.orient, s.left_end_type, s.right_end_type
             FROM assembly_seq s
             JOIN assembly_ctg c
               ON c.assembly_seq_id = s.id
             WHERE s.project_id = ?1
               AND c.project_id = ?1
               AND s.id = ?2",
            params![project_id, params.assembly_seq_id],
            |row| {
                Ok(SeqRow {
                    assembly_seq_id: row.get(0)?,
                    assembly_ctg_id: row.get(1)?,
                    orient: row.get(2)?,
                    left_end_type: row.get(3)?,
                    right_end_type: row.get(4)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_seq_id {} does not exist in project_id {}",
                params.assembly_seq_id,
                project_id
            )
        })?;

    let new_orient = flip_orient(&before.orient)?;
    tx.execute(
        "UPDATE assembly_seq
         SET orient = ?1,
             left_end_type = ?2,
             right_end_type = ?3
         WHERE id = ?4",
        params![
            new_orient,
            before.right_end_type,
            before.left_end_type,
            before.assembly_seq_id
        ],
    )?;
    tx.execute(
        "UPDATE assembly_ctg
         SET ref_orient = NULL
         WHERE id = ?1",
        params![before.assembly_ctg_id],
    )?;
    mark_ctg_manual(&tx, before.assembly_ctg_id)?;

    let after: (String, String, String, Option<String>) = tx.query_row(
        "SELECT s.orient, s.left_end_type, s.right_end_type, c.ref_orient
         FROM assembly_seq s
         JOIN assembly_ctg c
           ON c.assembly_seq_id = s.id
         WHERE s.id = ?1",
        params![before.assembly_seq_id],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
    )?;

    tx.commit()?;

    Ok(FlipSeqSummary {
        project_id,
        assembly_seq_id: before.assembly_seq_id,
        assembly_ctg_id: before.assembly_ctg_id,
        orient: after.0,
        left_end_type: after.1,
        right_end_type: after.2,
        ref_orient: after.3,
    })
}

#[cfg(test)]
mod tests {
    use super::{FlipSeqParams, flip_seq_with_connection};
    use crate::ctg_editor::common::test_utils::seed_workspace_with_two_member_ctg;
    use rusqlite::Connection;

    #[test]
    fn flips_single_seq_and_clears_ctg_ref_orient() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let summary = flip_seq_with_connection(
            &mut conn,
            seed.project_id,
            &FlipSeqParams {
                assembly_seq_id: seed.seq_a_id,
            },
        )
        .unwrap();
        assert_eq!(summary.orient, "-");
        assert_eq!(summary.left_end_type, "gap");
        assert_eq!(summary.right_end_type, "normal");
        assert_eq!(summary.ref_orient, None);

        let mode: String = conn
            .query_row(
                "SELECT placement_mode FROM assembly_ctg WHERE id = ?1",
                [seed.ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(mode, "manual");
    }
}
