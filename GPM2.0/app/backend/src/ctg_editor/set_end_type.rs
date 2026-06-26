use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::{mark_ctg_manual, normalize_end_type};
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SetEndTypeParams {
    pub assembly_seq_id: i64,
    pub left_end_type: String,
    pub right_end_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SetEndTypeSummary {
    pub project_id: i64,
    pub assembly_seq_id: i64,
    pub assembly_ctg_id: i64,
    pub left_end_type: String,
    pub right_end_type: String,
    pub ref_orient: Option<String>,
    pub changed: bool,
}

#[derive(Debug, Clone)]
struct EndTypeState {
    assembly_seq_id: i64,
    assembly_ctg_id: i64,
    left_end_type: String,
    right_end_type: String,
    ctg_ref_orient: Option<String>,
}

pub fn set_end_type(
    project_db_path: &Path,
    project_id: i64,
    params: &SetEndTypeParams,
) -> Result<SetEndTypeSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    set_end_type_with_connection(&mut conn, project_id, params)
}

pub fn set_end_type_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &SetEndTypeParams,
) -> Result<SetEndTypeSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.assembly_seq_id <= 0 {
        bail!("assembly_seq_id must be > 0");
    }
    let left_end_type = normalize_end_type("left_end_type", &params.left_end_type)?;
    let right_end_type = normalize_end_type("right_end_type", &params.right_end_type)?;

    let tx = conn.transaction()?;
    let before = tx
        .query_row(
            "SELECT s.id,
                    c.id,
                    s.left_end_type,
                    s.right_end_type,
                    c.ref_orient
             FROM assembly_seq s
             JOIN assembly_ctg c
               ON c.assembly_seq_id = s.id
             WHERE s.project_id = ?1
               AND c.project_id = ?1
               AND s.id = ?2",
            params![project_id, params.assembly_seq_id],
            |row| {
                Ok(EndTypeState {
                    assembly_seq_id: row.get(0)?,
                    assembly_ctg_id: row.get(1)?,
                    left_end_type: row.get(2)?,
                    right_end_type: row.get(3)?,
                    ctg_ref_orient: row.get(4)?,
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

    let changed = before.left_end_type != left_end_type || before.right_end_type != right_end_type;
    let mut ref_orient_after = before.ctg_ref_orient.clone();
    if changed {
        tx.execute(
            "UPDATE assembly_seq
             SET left_end_type = ?1,
                 right_end_type = ?2
             WHERE id = ?3",
            params![left_end_type, right_end_type, before.assembly_seq_id],
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

    Ok(SetEndTypeSummary {
        project_id,
        assembly_seq_id: before.assembly_seq_id,
        assembly_ctg_id: before.assembly_ctg_id,
        left_end_type: params.left_end_type.trim().to_ascii_lowercase(),
        right_end_type: params.right_end_type.trim().to_ascii_lowercase(),
        ref_orient: ref_orient_after,
        changed,
    })
}

#[cfg(test)]
mod tests {
    use super::{SetEndTypeParams, set_end_type_with_connection};
    use crate::ctg_editor::common::test_utils::seed_workspace_with_two_member_ctg;
    use rusqlite::Connection;

    #[test]
    fn updates_end_types_and_clears_ref_orient() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let summary = set_end_type_with_connection(
            &mut conn,
            seed.project_id,
            &SetEndTypeParams {
                assembly_seq_id: seed.seq_a_id,
                left_end_type: "telomere".to_string(),
                right_end_type: "normal".to_string(),
            },
        )
        .unwrap();
        assert!(summary.changed);
        assert_eq!(summary.ref_orient, None);

        let state: (String, String, Option<String>) = conn
            .query_row(
                "SELECT s.left_end_type, s.right_end_type, c.ref_orient
                 FROM assembly_seq s
                 JOIN assembly_ctg c ON c.assembly_seq_id = s.id
                 WHERE s.id = ?1",
                [seed.seq_a_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(state.0, "telomere");
        assert_eq!(state.1, "normal");
        assert_eq!(state.2, None);
    }
}
