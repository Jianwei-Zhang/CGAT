use anyhow::{Result, bail};
use rusqlite::{Connection, params};
use std::collections::BTreeSet;

pub(super) const VALID_END_TYPES: [&str; 3] = ["normal", "gap", "telomere"];

#[derive(Debug, Clone)]
pub(super) struct MemberState {
    pub assembly_seq_id: i64,
}

pub(super) fn flip_orient(current: &str) -> Result<&'static str> {
    match current {
        "+" => Ok("-"),
        "-" => Ok("+"),
        _ => bail!("unsupported orient value: {}", current),
    }
}

pub(super) fn toggle_ref_orient(value: Option<&str>) -> Option<String> {
    match value {
        Some("+") => Some("-".to_string()),
        Some("-") => Some("+".to_string()),
        _ => None,
    }
}

pub(super) fn normalize_end_type(field_name: &str, value: &str) -> Result<String> {
    let normalized = value.trim().to_ascii_lowercase();
    if VALID_END_TYPES.contains(&normalized.as_str()) {
        Ok(normalized)
    } else {
        bail!(
            "{} must be one of: {}",
            field_name,
            VALID_END_TYPES.join(", ")
        )
    }
}

pub(super) fn mark_ctg_manual(conn: &Connection, assembly_ctg_id: i64) -> Result<()> {
    conn.execute(
        "UPDATE assembly_ctg
         SET placement_mode = 'manual'
         WHERE id = ?1",
        params![assembly_ctg_id],
    )?;
    Ok(())
}

pub(super) fn load_ctg_members(
    conn: &Connection,
    assembly_ctg_id: i64,
) -> Result<Vec<MemberState>> {
    let mut stmt = conn.prepare(
        "SELECT c.assembly_seq_id
         FROM assembly_ctg c
         JOIN assembly_seq s
           ON s.id = c.assembly_seq_id
         WHERE c.id = ?1",
    )?;
    let members = stmt
        .query_map(params![assembly_ctg_id], |row| {
            Ok(MemberState {
                assembly_seq_id: row.get(0)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(members)
}

pub(super) fn refresh_chr_order_for_chr_names(
    conn: &Connection,
    project_id: i64,
    chr_names: &[String],
) -> Result<i64> {
    conn.execute(
        "UPDATE assembly_ctg
         SET chr_order = NULL
         WHERE project_id = ?1
           AND (assigned_chr_name IS NULL OR anchor_start IS NULL)",
        params![project_id],
    )?;

    let unique_chr_names = chr_names
        .iter()
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();

    let mut list_stmt = conn.prepare(
        "SELECT id
         FROM assembly_ctg
         WHERE project_id = ?1
           AND assigned_chr_name = ?2
           AND anchor_start IS NOT NULL
         ORDER BY anchor_start, id",
    )?;
    let mut update_stmt = conn.prepare("UPDATE assembly_ctg SET chr_order = ?1 WHERE id = ?2")?;

    for chr_name in &unique_chr_names {
        conn.execute(
            "UPDATE assembly_ctg
             SET chr_order = NULL
             WHERE project_id = ?1
               AND assigned_chr_name = ?2",
            params![project_id, chr_name],
        )?;

        let ctg_ids = list_stmt
            .query_map(params![project_id, chr_name], |row| row.get::<_, i64>(0))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        for (index, ctg_id) in ctg_ids.into_iter().enumerate() {
            update_stmt.execute(params![index as i64 + 1, ctg_id])?;
        }
    }

    Ok(unique_chr_names.len() as i64)
}

#[cfg(test)]
pub(super) mod test_utils {
    use anyhow::Result;
    use rusqlite::{Connection, params};

    use crate::db::init_workspace_schema;

    #[derive(Debug, Clone)]
    pub struct SeedData {
        pub project_id: i64,
        pub ctg_id: i64,
        pub seq_a_id: i64,
    }

    pub fn seed_workspace_with_two_member_ctg(conn: &Connection) -> Result<SeedData> {
        init_workspace_schema(conn)?;

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', 'D:/bundle/data/reference/ref.fa', 'D:/bundle/data/reference/ref.fa.fai')",
            [],
        )?;
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000000)",
            [],
        )?;
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, 'D:/bundle/data/datasets/ds1.fa', 'D:/bundle/data/datasets/ds1.fa.fai')",
            [],
        )?;
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 1000)",
            [],
        )?;
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (102, 1, 'tigB', 2, 800)",
            [],
        )?;
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (1, 'p1', 1, 1, 1, 0, NULL, '1', NULL)",
            [],
        )?;
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 1, 'primary', 1)",
            [],
        )?;

        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, instance_key, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (201, 1, 101, 'source:101', '+', 1, 1000, 'normal', 'gap', 0, '1', NULL)",
            [],
        )?;
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, instance_key, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (202, 1, 102, 'source:102', '-', 1, 800, 'telomere', 'normal', 0, '1', NULL)",
            [],
        )?;
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 1000, '+', 'auto', '1', NULL)",
            [],
        )?;

        Ok(SeedData {
            project_id: 1,
            ctg_id: 301,
            seq_a_id: 201,
        })
    }

    pub fn insert_second_ctg(
        conn: &Connection,
        project_id: i64,
        ctg_id: i64,
        name: &str,
    ) -> Result<()> {
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (?1, ?2, 202, ?3, 'Chr01', 2, 2000, NULL, 'none', '1', NULL)",
            params![ctg_id, project_id, name],
        )?;
        Ok(())
    }
}
