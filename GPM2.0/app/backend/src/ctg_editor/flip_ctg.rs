use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::common::{flip_orient, mark_ctg_manual, toggle_ref_orient};
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlipCtgParams {
    pub assembly_ctg_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlipCtgSummary {
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub member_count: i64,
    pub ref_orient: Option<String>,
}

#[derive(Debug, Clone)]
struct MemberRow {
    assembly_seq_id: i64,
    orient: String,
}

pub fn flip_ctg(
    project_db_path: &Path,
    project_id: i64,
    params: &FlipCtgParams,
) -> Result<FlipCtgSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    flip_ctg_with_connection(&mut conn, project_id, params)
}

pub fn flip_ctg_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &FlipCtgParams,
) -> Result<FlipCtgSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.assembly_ctg_id <= 0 {
        bail!("assembly_ctg_id must be > 0");
    }

    let tx = conn.transaction()?;

    let before_ref_orient: Option<String> = tx
        .query_row(
            "SELECT ref_orient
             FROM assembly_ctg
             WHERE project_id = ?1
               AND id = ?2",
            params![project_id, params.assembly_ctg_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_ctg_id {} does not exist in project_id {}",
                params.assembly_ctg_id,
                project_id
            )
        })?;

    let members = {
        let mut stmt = tx.prepare(
            "SELECT c.assembly_seq_id, s.orient
             FROM assembly_ctg c
             JOIN assembly_seq s
               ON s.id = c.assembly_seq_id
             WHERE c.id = ?1
               AND s.project_id = ?2
             ORDER BY c.id",
        )?;
        stmt.query_map(params![params.assembly_ctg_id, project_id], |row| {
            Ok(MemberRow {
                assembly_seq_id: row.get(0)?,
                orient: row.get(1)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?
    };

    for member in &members {
        let new_orient = flip_orient(&member.orient)?;
        tx.execute(
            "UPDATE assembly_seq
             SET orient = ?1,
                 left_end_type = right_end_type,
                 right_end_type = left_end_type
             WHERE id = ?2",
            params![new_orient, member.assembly_seq_id],
        )?;
    }

    let after_ref_orient = toggle_ref_orient(before_ref_orient.as_deref());
    tx.execute(
        "UPDATE assembly_ctg
         SET ref_orient = ?1
         WHERE id = ?2",
        params![after_ref_orient, params.assembly_ctg_id],
    )?;
    mark_ctg_manual(&tx, params.assembly_ctg_id)?;

    tx.commit()?;

    Ok(FlipCtgSummary {
        project_id,
        assembly_ctg_id: params.assembly_ctg_id,
        member_count: members.len() as i64,
        ref_orient: after_ref_orient,
    })
}

#[cfg(test)]
mod tests {
    use super::{FlipCtgParams, flip_ctg_with_connection};
    use crate::ctg_editor::common::test_utils::seed_workspace_with_two_member_ctg;
    use rusqlite::Connection;

    #[test]
    fn flips_ctg_structure_and_updates_ref_orient() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let summary = flip_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &FlipCtgParams {
                assembly_ctg_id: seed.ctg_id,
            },
        )
        .unwrap();
        assert_eq!(summary.member_count, 1);
        assert_eq!(summary.ref_orient.as_deref(), Some("-"));

        let seq_a_state: (String, String, String) = conn
            .query_row(
                "SELECT orient, left_end_type, right_end_type FROM assembly_seq WHERE id = ?1",
                [seed.seq_a_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(seq_a_state.0, "-");
        assert_eq!(seq_a_state.1, "gap");
        assert_eq!(seq_a_state.2, "normal");
    }
}
