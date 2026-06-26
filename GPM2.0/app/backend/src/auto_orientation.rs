use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, params};

use crate::alignment_cache::ensure_project_ref_alignment_hits_with_cancel;
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq)]
pub struct AutoOrientContigsParams {
    pub alignment_block_size: i64,
    pub alignment_coverage_percent: f64,
    pub skip_manual: bool,
}

impl Default for AutoOrientContigsParams {
    fn default() -> Self {
        Self {
            alignment_block_size: 1_000,
            alignment_coverage_percent: 25.0,
            skip_manual: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutoOrientContigsSummary {
    pub project_id: i64,
    pub processed_ctg_count: i64,
    pub oriented_ctg_count: i64,
    pub flipped_ctg_count: i64,
    pub no_evidence_count: i64,
    pub skipped_manual_count: i64,
    pub loaded_alignment_dataset_count: i64,
    pub loaded_alignment_hit_count: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AutoOrientContigsScope {
    FullProject,
    Dataset(i64),
    AssemblyCtg(i64),
}

#[derive(Debug, Clone)]
struct CtgMember {
    assembly_seq_id: i64,
    source_seq_id: i64,
    source_start: i64,
    source_end: i64,
    orient: String,
}

#[derive(Debug, Clone)]
struct RefHit {
    strand: String,
    block_length: i64,
}

pub fn auto_orient_contigs(
    project_db_path: &Path,
    project_id: i64,
    params: &AutoOrientContigsParams,
) -> Result<AutoOrientContigsSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_orient_contigs_with_connection(&mut conn, project_id, params)
}

pub fn auto_orient_contigs_cancel(
    project_db_path: &Path,
    project_id: i64,
    params: &AutoOrientContigsParams,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<AutoOrientContigsSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_orient_contigs_with_connection_cancel(&mut conn, project_id, params, should_cancel)
}

pub fn auto_orient_contigs_for_dataset(
    project_db_path: &Path,
    project_id: i64,
    dataset_id: i64,
    params: &AutoOrientContigsParams,
) -> Result<AutoOrientContigsSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_orient_contigs_for_dataset_with_connection(&mut conn, project_id, dataset_id, params)
}

pub fn auto_orient_contigs_for_dataset_cancel(
    project_db_path: &Path,
    project_id: i64,
    dataset_id: i64,
    params: &AutoOrientContigsParams,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<AutoOrientContigsSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_orient_contigs_for_dataset_with_connection_cancel(
        &mut conn,
        project_id,
        dataset_id,
        params,
        should_cancel,
    )
}

pub fn auto_orient_contigs_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &AutoOrientContigsParams,
) -> Result<AutoOrientContigsSummary> {
    let mut never_cancel = || false;
    auto_orient_contigs_with_connection_cancel(conn, project_id, params, &mut never_cancel)
}

pub fn auto_orient_contigs_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    params: &AutoOrientContigsParams,
    should_cancel: &mut F,
) -> Result<AutoOrientContigsSummary>
where
    F: FnMut() -> bool,
{
    auto_orient_contigs_scoped_with_connection_cancel(
        conn,
        project_id,
        params,
        AutoOrientContigsScope::FullProject,
        should_cancel,
    )
}

pub fn auto_orient_contigs_for_dataset_with_connection(
    conn: &mut Connection,
    project_id: i64,
    dataset_id: i64,
    params: &AutoOrientContigsParams,
) -> Result<AutoOrientContigsSummary> {
    let mut never_cancel = || false;
    auto_orient_contigs_for_dataset_with_connection_cancel(
        conn,
        project_id,
        dataset_id,
        params,
        &mut never_cancel,
    )
}

pub fn auto_orient_contigs_for_dataset_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    dataset_id: i64,
    params: &AutoOrientContigsParams,
    should_cancel: &mut F,
) -> Result<AutoOrientContigsSummary>
where
    F: FnMut() -> bool,
{
    auto_orient_contigs_scoped_with_connection_cancel(
        conn,
        project_id,
        params,
        AutoOrientContigsScope::Dataset(dataset_id),
        should_cancel,
    )
}

fn auto_orient_contigs_scoped_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    params: &AutoOrientContigsParams,
    scope: AutoOrientContigsScope,
    should_cancel: &mut F,
) -> Result<AutoOrientContigsSummary>
where
    F: FnMut() -> bool,
{
    if params.alignment_block_size < 0 {
        bail!("alignment_block_size must be >= 0");
    }
    if !(0.0..=100.0).contains(&params.alignment_coverage_percent) {
        bail!("alignment_coverage_percent must be between 0 and 100");
    }
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let reference_genome_id: i64 = conn.query_row(
        "SELECT reference_genome_id FROM project WHERE id = ?1",
        params![project_id],
        |row| row.get(0),
    )?;

    let cache_summary =
        ensure_project_ref_alignment_hits_with_cancel(conn, project_id, should_cancel)?;

    let ctg_rows = list_ctg_rows_for_scope(conn, project_id, scope)?;
    let is_scoped = !matches!(scope, AutoOrientContigsScope::FullProject);

    let tx = conn.transaction()?;
    let mut processed_ctg_count = 0_i64;
    let mut oriented_ctg_count = 0_i64;
    let mut flipped_ctg_count = 0_i64;
    let mut no_evidence_count = 0_i64;
    let mut skipped_manual_count = 0_i64;

    for (assembly_ctg_id, assigned_chr_name, placement_mode) in ctg_rows {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }
        if is_scoped && placement_mode == "manual" && params.skip_manual {
            skipped_manual_count += 1;
            continue;
        }
        let Some(chr_name) = assigned_chr_name else {
            clear_ctg_ref_orient(&tx, assembly_ctg_id)?;
            continue;
        };
        if placement_mode == "manual" && params.skip_manual {
            skipped_manual_count += 1;
            continue;
        }
        processed_ctg_count += 1;

        let members = list_all_ctg_members(&tx, assembly_ctg_id)?;
        if members.is_empty() {
            clear_ctg_ref_orient(&tx, assembly_ctg_id)?;
            no_evidence_count += 1;
            continue;
        }

        let mut flip_score = 0_i64;
        let mut evidence_count = 0_i64;
        for member in &members {
            if should_cancel() {
                bail!("auto pipeline cancelled");
            }
            let member_length = (member.source_end - member.source_start + 1).max(1);
            let hits = list_reference_hits_for_source_seq_on_chr(
                &tx,
                reference_genome_id,
                member.source_seq_id,
                &chr_name,
            )?;
            for hit in hits {
                if should_cancel() {
                    bail!("auto pipeline cancelled");
                }
                let qualified = hit.block_length >= params.alignment_block_size
                    || ((hit.block_length as f64) * 100.0 / (member_length as f64))
                        >= params.alignment_coverage_percent;
                if !qualified {
                    continue;
                }
                evidence_count += 1;
                let should_flip = (member.orient == "+" && hit.strand == "-")
                    || (member.orient == "-" && hit.strand == "+");
                if should_flip {
                    flip_score += hit.block_length;
                } else {
                    flip_score -= hit.block_length;
                }
            }
        }

        if evidence_count == 0 {
            clear_ctg_ref_orient(&tx, assembly_ctg_id)?;
            no_evidence_count += 1;
            continue;
        }

        if flip_score > 0 {
            flip_ctg_structure(&tx, &members)?;
            flipped_ctg_count += 1;
        }
        tx.execute(
            "UPDATE assembly_ctg SET ref_orient = '+' WHERE id = ?1",
            params![assembly_ctg_id],
        )?;
        oriented_ctg_count += 1;
    }

    tx.commit()?;

    Ok(AutoOrientContigsSummary {
        project_id,
        processed_ctg_count,
        oriented_ctg_count,
        flipped_ctg_count,
        no_evidence_count,
        skipped_manual_count,
        loaded_alignment_dataset_count: cache_summary.loaded_dataset_count,
        loaded_alignment_hit_count: cache_summary.loaded_hit_count,
    })
}

fn list_ctg_rows_for_scope(
    conn: &Connection,
    project_id: i64,
    scope: AutoOrientContigsScope,
) -> Result<Vec<(i64, Option<String>, String)>> {
    match scope {
        AutoOrientContigsScope::FullProject => {
            let mut ctg_stmt = conn.prepare(
                "SELECT id, assigned_chr_name, placement_mode
                 FROM assembly_ctg
                 WHERE project_id = ?1
                 ORDER BY id",
            )?;
            ctg_stmt
                .query_map(params![project_id], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, Option<String>>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()
                .map_err(Into::into)
        }
        AutoOrientContigsScope::Dataset(dataset_id) => {
            let mut ctg_stmt = conn.prepare(
                "SELECT c.id, c.assigned_chr_name, c.placement_mode
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE c.project_id = ?1
                   AND ss.dataset_id = ?2
                 ORDER BY c.id",
            )?;
            ctg_stmt
                .query_map(params![project_id, dataset_id], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, Option<String>>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()
                .map_err(Into::into)
        }
        AutoOrientContigsScope::AssemblyCtg(assembly_ctg_id) => {
            let mut ctg_stmt = conn.prepare(
                "SELECT id, assigned_chr_name, placement_mode
                 FROM assembly_ctg
                 WHERE project_id = ?1
                   AND id = ?2
                 ORDER BY id",
            )?;
            ctg_stmt
                .query_map(params![project_id, assembly_ctg_id], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, Option<String>>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()
                .map_err(Into::into)
        }
    }
}

fn list_all_ctg_members(conn: &Connection, assembly_ctg_id: i64) -> Result<Vec<CtgMember>> {
    let mut stmt = conn.prepare(
        "SELECT
            c.assembly_seq_id,
            s.source_seq_id,
            s.source_start,
            s.source_end,
            s.orient,
            s.hidden
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         WHERE c.id = ?1
         ORDER BY c.id",
    )?;
    let rows = stmt
        .query_map(params![assembly_ctg_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;

    let mut members = Vec::new();
    for (assembly_seq_id, source_seq_id, source_start, source_end, orient, hidden) in rows {
        if hidden != 0 {
            continue;
        }
        members.push(CtgMember {
            assembly_seq_id,
            source_seq_id,
            source_start,
            source_end,
            orient,
        });
    }
    Ok(members)
}

fn list_reference_hits_for_source_seq_on_chr(
    conn: &Connection,
    reference_genome_id: i64,
    source_seq_id: i64,
    chr_name: &str,
) -> Result<Vec<RefHit>> {
    let mut stmt = conn.prepare(
        "SELECT h.strand, h.block_length
         FROM ref_alignment_hit h
         JOIN reference_chr rc ON rc.id = h.reference_chr_id
         WHERE h.source_seq_id = ?1
           AND rc.reference_genome_id = ?2
           AND rc.chr_name = ?3",
    )?;
    let rows = stmt
        .query_map(
            params![source_seq_id, reference_genome_id, chr_name],
            |row| {
                Ok(RefHit {
                    strand: row.get(0)?,
                    block_length: row.get(1)?,
                })
            },
        )?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(rows)
}

fn flip_ctg_structure(conn: &Connection, members: &[CtgMember]) -> Result<()> {
    for member in members {
        let new_orient = flip_orient(&member.orient)?;
        conn.execute(
            "UPDATE assembly_seq
             SET orient = ?1,
                 left_end_type = right_end_type,
                 right_end_type = left_end_type
             WHERE id = ?2",
            params![new_orient, member.assembly_seq_id],
        )?;
    }
    Ok(())
}

fn flip_orient(current: &str) -> Result<&'static str> {
    match current {
        "+" => Ok("-"),
        "-" => Ok("+"),
        _ => bail!("unsupported assembly_seq.orient value: {}", current),
    }
}

fn clear_ctg_ref_orient(conn: &Connection, assembly_ctg_id: i64) -> Result<()> {
    conn.execute(
        "UPDATE assembly_ctg SET ref_orient = NULL WHERE id = ?1",
        params![assembly_ctg_id],
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        AutoOrientContigsParams, auto_orient_contigs_for_dataset_with_connection,
        auto_orient_contigs_with_connection,
    };
    use crate::db::init_workspace_schema;
    use rusqlite::{Connection, params};

    #[test]
    fn flips_ctg_when_score_requires_flip() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");

        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/bundle/data/reference/ref.fa', 'D:/bundle/data/reference/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 100000)",
            params![reference_id],
        )
        .expect("insert chr");
        let chr_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO dataset (name, assembler, assembler_version, fasta_path, fai_path)
             VALUES ('ds1', 'asm', NULL, 'D:/bundle/data/datasets/ds1.fa', 'D:/bundle/data/datasets/ds1.fa.fai')",
            [],
        )
        .expect("insert dataset");
        let dataset_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (?1, 'tig1', 1, 1000)",
            params![dataset_id],
        )
        .expect("insert source_seq");
        let source_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO project (name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES ('p', 1, ?1, ?2, 0, NULL, '1', NULL)",
            params![reference_id, dataset_id],
        )
        .expect("insert project");
        let project_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, ?2, 'primary', 1)",
            params![project_id, dataset_id],
        )
        .expect("insert project_dataset");

        conn.execute(
            "INSERT INTO assembly_seq (project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (?1, ?2, '+', 1, 1000, 'gap', 'telomere', 0, '1', NULL)",
            params![project_id, source_seq_id],
        )
        .expect("insert assembly_seq");
        let assembly_seq_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO assembly_ctg (project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (?1, ?2, 'Ctg1', 'Chr01', 1, 1000, NULL, 'auto', '1', NULL)",
            params![project_id, assembly_seq_id],
        )
        .expect("insert ctg");
        let ctg_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '-', 10, 309, 5000, 5299, 300, 300, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr_id],
        )
        .expect("insert reverse hit");

        let summary = auto_orient_contigs_with_connection(
            &mut conn,
            project_id,
            &AutoOrientContigsParams::default(),
        )
        .expect("auto orient");
        assert_eq!(summary.processed_ctg_count, 1);
        assert_eq!(summary.flipped_ctg_count, 1);
        assert_eq!(summary.oriented_ctg_count, 1);

        let state = conn
            .query_row(
                "SELECT s.orient, s.left_end_type, s.right_end_type, c.ref_orient
                 FROM assembly_seq s
                 JOIN assembly_ctg c ON c.assembly_seq_id = s.id
                 WHERE c.id = ?1",
                params![ctg_id],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, Option<String>>(3)?,
                    ))
                },
            )
            .expect("read state");
        assert_eq!(state.0, "-");
        assert_eq!(state.1, "telomere");
        assert_eq!(state.2, "gap");
        assert_eq!(state.3.as_deref(), Some("+"));
    }

    #[test]
    fn scoped_orientation_flips_only_requested_dataset() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");

        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/bundle/data/reference/ref.fa', 'D:/bundle/data/reference/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 100000)",
            params![reference_id],
        )
        .expect("insert chr");
        let chr_id = conn.last_insert_rowid();

        let ds1_id = insert_dataset_with_ctg(&conn, "ds1", "tig1");
        let ds4_id = insert_dataset_with_ctg(&conn, "ds4", "tig4");
        let ds1_source_seq_id = source_seq_id(&conn, ds1_id);
        let ds4_source_seq_id = source_seq_id(&conn, ds4_id);
        let ds4_manual_source_seq_id = insert_source_seq(&conn, ds4_id, "tig4_manual", 2);

        conn.execute(
            "INSERT INTO project (name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES ('p', 1, ?1, ?2, 0, NULL, '1', NULL)",
            params![reference_id, ds1_id],
        )
        .expect("insert project");
        let project_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, ?2, 'primary', 1)",
            params![project_id, ds1_id],
        )
        .expect("insert ds1 project_dataset");
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, ?2, 'support', 2)",
            params![project_id, ds4_id],
        )
        .expect("insert ds4 project_dataset");

        let ds1_ctg_id =
            insert_assembly_ctg(&conn, project_id, ds1_source_seq_id, "Existing", Some("-"));
        let ds4_ctg_id = insert_assembly_ctg(&conn, project_id, ds4_source_seq_id, "Ds4", None);
        let ds4_manual_ctg_id = insert_assembly_ctg(
            &conn,
            project_id,
            ds4_manual_source_seq_id,
            "ManualDs4",
            Some("-"),
        );
        conn.execute(
            "UPDATE assembly_ctg
             SET assigned_chr_name = NULL,
                 chr_order = NULL,
                 anchor_start = NULL,
                 placement_mode = 'manual'
             WHERE id = ?1",
            params![ds4_manual_ctg_id],
        )
        .expect("make ds4 manual ctg unassigned");

        for (dataset_id, source_seq_id, run_name) in [
            (ds1_id, ds1_source_seq_id, "ds1_vs_ref"),
            (ds4_id, ds4_source_seq_id, "ds4_vs_ref"),
        ] {
            conn.execute(
                "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
                 VALUES (?1, ?2, ?3, '-', 10, 309, 5000, 5299, 300, 300, 60, ?4, NULL)",
                params![dataset_id, source_seq_id, chr_id, run_name],
            )
            .expect("insert reverse hit");
        }

        let summary = auto_orient_contigs_for_dataset_with_connection(
            &mut conn,
            project_id,
            ds4_id,
            &AutoOrientContigsParams::default(),
        )
        .expect("scoped auto orient");
        assert_eq!(summary.processed_ctg_count, 1);
        assert_eq!(summary.flipped_ctg_count, 1);
        assert_eq!(summary.oriented_ctg_count, 1);
        assert_eq!(summary.skipped_manual_count, 1);

        let existing_state = ctg_state(&conn, ds1_ctg_id);
        assert_eq!(existing_state.0, "+");
        assert_eq!(existing_state.1.as_deref(), Some("-"));

        let ds4_state = ctg_state(&conn, ds4_ctg_id);
        assert_eq!(ds4_state.0, "-");
        assert_eq!(ds4_state.1.as_deref(), Some("+"));
        assert_eq!(ds4_state.2, ds4_ctg_id);

        let ds4_manual_state = ctg_state(&conn, ds4_manual_ctg_id);
        assert_eq!(ds4_manual_state.0, "+");
        assert_eq!(ds4_manual_state.1.as_deref(), Some("-"));
        assert_eq!(ds4_manual_state.2, ds4_manual_ctg_id);
    }

    fn insert_dataset_with_ctg(conn: &Connection, dataset_name: &str, seq_name: &str) -> i64 {
        conn.execute(
            "INSERT INTO dataset (name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (?1, 'asm', NULL, ?2, ?3)",
            params![
                dataset_name,
                format!("D:/bundle/data/datasets/{dataset_name}.fa"),
                format!("D:/bundle/data/datasets/{dataset_name}.fa.fai")
            ],
        )
        .expect("insert dataset");
        let dataset_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (?1, ?2, 1, 1000)",
            params![dataset_id, seq_name],
        )
        .expect("insert source_seq");
        dataset_id
    }

    fn insert_source_seq(
        conn: &Connection,
        dataset_id: i64,
        seq_name: &str,
        seq_order: i64,
    ) -> i64 {
        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (?1, ?2, ?3, 1000)",
            params![dataset_id, seq_name, seq_order],
        )
        .expect("insert extra source_seq");
        conn.last_insert_rowid()
    }

    fn source_seq_id(conn: &Connection, dataset_id: i64) -> i64 {
        conn.query_row(
            "SELECT id FROM source_seq WHERE dataset_id = ?1",
            params![dataset_id],
            |row| row.get(0),
        )
        .expect("read source_seq id")
    }

    fn insert_assembly_ctg(
        conn: &Connection,
        project_id: i64,
        source_seq_id: i64,
        name: &str,
        ref_orient: Option<&str>,
    ) -> i64 {
        conn.execute(
            "INSERT INTO assembly_seq (project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (?1, ?2, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            params![project_id, source_seq_id],
        )
        .expect("insert assembly_seq");
        let assembly_seq_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO assembly_ctg (project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (?1, ?2, ?3, 'Chr01', 1, 1000, ?4, 'auto', '1', NULL)",
            params![project_id, assembly_seq_id, name, ref_orient],
        )
        .expect("insert ctg");
        conn.last_insert_rowid()
    }

    fn ctg_state(conn: &Connection, assembly_ctg_id: i64) -> (String, Option<String>, i64) {
        conn.query_row(
            "SELECT s.orient, c.ref_orient, c.id
             FROM assembly_seq s
             JOIN assembly_ctg c ON c.assembly_seq_id = s.id
             WHERE c.id = ?1",
            params![assembly_ctg_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .expect("read ctg state")
    }
}
