use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenameCtgParams {
    pub assembly_ctg_id: i64,
    pub new_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenameCtgSummary {
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub old_name: String,
    pub new_name: String,
    pub changed: bool,
}

pub fn rename_ctg(
    project_db_path: &Path,
    project_id: i64,
    params: &RenameCtgParams,
) -> Result<RenameCtgSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    rename_ctg_with_connection(&mut conn, project_id, params)
}

pub fn rename_ctg_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &RenameCtgParams,
) -> Result<RenameCtgSummary> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    if params.assembly_ctg_id <= 0 {
        bail!("assembly_ctg_id must be > 0");
    }

    let new_name = params.new_name.trim();
    if new_name.is_empty() {
        bail!("new_name must not be blank");
    }

    let tx = conn.transaction()?;
    let old_name: String = tx
        .query_row(
            "SELECT name
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

    let changed = old_name != new_name;
    if changed {
        let duplicate_id: Option<i64> = tx
            .query_row(
                "SELECT id
                 FROM assembly_ctg
                 WHERE project_id = ?1
                   AND name = ?2
                   AND id <> ?3",
                params![project_id, new_name, params.assembly_ctg_id],
                |row| row.get(0),
            )
            .optional()?;
        if duplicate_id.is_some() {
            bail!(
                "assembly_ctg name '{}' already exists in project_id {}",
                new_name,
                project_id
            );
        }

        tx.execute(
            "UPDATE assembly_ctg
             SET name = ?1
             WHERE id = ?2",
            params![new_name, params.assembly_ctg_id],
        )?;
    }

    tx.commit()?;

    Ok(RenameCtgSummary {
        project_id,
        assembly_ctg_id: params.assembly_ctg_id,
        old_name,
        new_name: new_name.to_string(),
        changed,
    })
}

#[cfg(test)]
mod tests {
    use super::{RenameCtgParams, rename_ctg_with_connection};
    use crate::ctg_editor::common::test_utils::{
        insert_second_ctg, seed_workspace_with_two_member_ctg,
    };
    use rusqlite::Connection;

    #[test]
    fn renames_ctg_name() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();

        let summary = rename_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &RenameCtgParams {
                assembly_ctg_id: seed.ctg_id,
                new_name: "Ctg_Renamed".to_string(),
            },
        )
        .unwrap();
        assert!(summary.changed);
        assert_eq!(summary.old_name, "Ctg1");
        assert_eq!(summary.new_name, "Ctg_Renamed");

        let current_name: String = conn
            .query_row(
                "SELECT name FROM assembly_ctg WHERE id = ?1",
                [seed.ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(current_name, "Ctg_Renamed");
    }

    #[test]
    fn rejects_duplicate_name() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_workspace_with_two_member_ctg(&conn).unwrap();
        insert_second_ctg(&conn, seed.project_id, 302, "Ctg2").unwrap();

        let error = rename_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &RenameCtgParams {
                assembly_ctg_id: seed.ctg_id,
                new_name: "Ctg2".to_string(),
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("already exists"));
    }
}
