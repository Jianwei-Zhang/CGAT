use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, params};

use crate::alignment_cache::ensure_project_ref_alignment_hits_with_cancel;
use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq)]
pub struct AutoAssignChrParams {
    pub alignment_block_size: i64,
    pub alignment_coverage_percent: f64,
    pub assign_unplaced: bool,
    pub reposition_anchored: bool,
    pub skip_manual: bool,
}

impl Default for AutoAssignChrParams {
    fn default() -> Self {
        Self {
            alignment_block_size: 1_000,
            alignment_coverage_percent: 25.0,
            assign_unplaced: true,
            reposition_anchored: false,
            skip_manual: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutoAssignChrSummary {
    pub project_id: i64,
    pub processed_ctg_count: i64,
    pub assigned_count: i64,
    pub repositioned_count: i64,
    pub cleared_count: i64,
    pub skipped_manual_count: i64,
    pub no_evidence_count: i64,
    pub refreshed_chr_count: i64,
    pub loaded_alignment_dataset_count: i64,
    pub loaded_alignment_hit_count: i64,
}

#[derive(Debug, Clone)]
struct SourceSeqPlacementCandidate {
    source_seq_id: i64,
    dataset_name: String,
    seq_name: String,
    ctg_base_name: String,
    seq_length: i64,
    dataset_id: i64,
}

#[derive(Debug, Clone)]
struct ReusableSourceInstance {
    assembly_ctg_id: i64,
    assembly_seq_id: i64,
}

#[derive(Debug, Clone)]
struct ChrAssignmentCandidate {
    chr_name: String,
    support_bp: i64,
    support_percent: f64,
    anchor_start: i64,
}

#[derive(Debug, Clone)]
struct RefHit {
    chr_name: String,
    strand: String,
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    block_length: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct WeightedPosition {
    position: i64,
    weight: i64,
}

pub fn auto_assign_chr(
    project_db_path: &Path,
    project_id: i64,
    params: &AutoAssignChrParams,
) -> Result<AutoAssignChrSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_assign_chr_with_connection(&mut conn, project_id, params)
}

pub fn auto_assign_chr_cancel(
    project_db_path: &Path,
    project_id: i64,
    params: &AutoAssignChrParams,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<AutoAssignChrSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    auto_assign_chr_with_connection_cancel(&mut conn, project_id, params, should_cancel)
}

pub fn auto_assign_chr_with_connection(
    conn: &mut Connection,
    project_id: i64,
    params: &AutoAssignChrParams,
) -> Result<AutoAssignChrSummary> {
    let mut never_cancel = || false;
    auto_assign_chr_with_connection_cancel(conn, project_id, params, &mut never_cancel)
}

pub fn auto_assign_chr_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    params: &AutoAssignChrParams,
    should_cancel: &mut F,
) -> Result<AutoAssignChrSummary>
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

    let (reference_genome_id, min_coverage_percent): (i64, f64) = conn.query_row(
        "SELECT reference_genome_id, chr_assignment_min_coverage_percent
         FROM project
         WHERE id = ?1",
        params![project_id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;

    let cache_summary =
        ensure_project_ref_alignment_hits_with_cancel(conn, project_id, should_cancel)?;

    let mut source_rows = {
        let mut stmt = conn.prepare(
            "SELECT ss.id, d.name, ss.seq_name, ss.length, ss.dataset_id
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             JOIN source_seq ss ON ss.dataset_id = pd.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY pd.display_order, ss.seq_order, ss.id",
        )?;
        stmt.query_map(params![project_id], |row| {
            Ok(SourceSeqPlacementCandidate {
                source_seq_id: row.get(0)?,
                dataset_name: row.get(1)?,
                seq_name: row.get(2)?,
                ctg_base_name: String::new(),
                seq_length: row.get(3)?,
                dataset_id: row.get(4)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let duplicate_seq_names = duplicate_source_seq_names(&source_rows);
    for source in &mut source_rows {
        source.ctg_base_name = source_ctg_base_name(source, &duplicate_seq_names);
    }

    let tx = conn.transaction()?;

    let manual_source_seq_ids = if params.skip_manual {
        load_manual_source_seq_ids(&tx, project_id)?
    } else {
        BTreeSet::new()
    };
    let old_auto_chr_names = list_auto_chr_names(&tx, project_id)?;
    tx.execute(
        "DELETE FROM assembly_ctg
         WHERE project_id = ?1
           AND placement_mode = 'auto'",
        params![project_id],
    )?;
    tx.execute(
        "DELETE FROM assembly_seq
         WHERE project_id = ?1
           AND instance_key LIKE 'chr:%'
           AND id NOT IN (
                SELECT assembly_seq_id
                FROM assembly_ctg
                WHERE project_id = ?1
           )",
        params![project_id],
    )?;
    let mut reusable_instances = load_reusable_source_instances(&tx, project_id)?;

    let mut processed_ctg_count = 0_i64;
    let mut assigned_count = 0_i64;
    let repositioned_count = 0_i64;
    let cleared_count = 0_i64;
    let mut skipped_manual_count = 0_i64;
    let mut no_evidence_count = 0_i64;
    let mut affected_chrs = old_auto_chr_names;

    for source in source_rows {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }

        processed_ctg_count += 1;

        let reusable_instance = reusable_instances.remove(&source.source_seq_id);

        if manual_source_seq_ids.contains(&source.source_seq_id) {
            skipped_manual_count += 1;
            continue;
        }

        let chr_candidates = collect_source_chr_candidates(
            &tx,
            reference_genome_id,
            source.source_seq_id,
            source.seq_length,
            params,
            min_coverage_percent,
            should_cancel,
        )?;
        if chr_candidates.is_empty() {
            no_evidence_count += 1;
            ensure_unplaced_source_instance(&tx, project_id, &source, reusable_instance)?;
            continue;
        }
        if !params.assign_unplaced {
            ensure_unplaced_source_instance(&tx, project_id, &source, reusable_instance)?;
            continue;
        }

        let mut candidates = chr_candidates.into_iter();
        if let Some(first_candidate) = candidates.next() {
            if let Some(instance) = reusable_instance {
                repurpose_source_instance_as_auto(&tx, &instance, &source, &first_candidate)?;
            } else {
                create_auto_chr_instance(&tx, project_id, &source, &first_candidate)?;
            }
            affected_chrs.insert(first_candidate.chr_name.clone());
            assigned_count += 1;
        }

        for candidate in candidates {
            create_auto_chr_instance(&tx, project_id, &source, &candidate)?;
            affected_chrs.insert(candidate.chr_name.clone());
            assigned_count += 1;
        }
    }

    let mut refreshed_chr_count = 0_i64;
    for chr_name in &affected_chrs {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }
        refresh_chr_order_for_chr(&tx, project_id, chr_name)?;
        refreshed_chr_count += 1;
    }

    tx.commit()?;

    Ok(AutoAssignChrSummary {
        project_id,
        processed_ctg_count,
        assigned_count,
        repositioned_count,
        cleared_count,
        skipped_manual_count,
        no_evidence_count,
        refreshed_chr_count,
        loaded_alignment_dataset_count: cache_summary.loaded_dataset_count,
        loaded_alignment_hit_count: cache_summary.loaded_hit_count,
    })
}

fn load_manual_source_seq_ids(conn: &Connection, project_id: i64) -> Result<BTreeSet<i64>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT s.source_seq_id
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         WHERE c.project_id = ?1
           AND c.placement_mode = 'manual'",
    )?;
    Ok(stmt
        .query_map(params![project_id], |row| row.get::<_, i64>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?
        .into_iter()
        .collect::<BTreeSet<_>>())
}

fn list_auto_chr_names(conn: &Connection, project_id: i64) -> Result<BTreeSet<String>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT assigned_chr_name
         FROM assembly_ctg
         WHERE project_id = ?1
           AND placement_mode = 'auto'
           AND assigned_chr_name IS NOT NULL
           AND assigned_chr_name != ''",
    )?;
    Ok(stmt
        .query_map(params![project_id], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?
        .into_iter()
        .collect::<BTreeSet<_>>())
}

fn load_reusable_source_instances(
    conn: &Connection,
    project_id: i64,
) -> Result<HashMap<i64, ReusableSourceInstance>> {
    let mut stmt = conn.prepare(
        "SELECT s.source_seq_id, c.id, s.id
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         WHERE c.project_id = ?1
           AND c.placement_mode != 'manual'
         ORDER BY s.source_seq_id, c.id",
    )?;
    let rows = stmt
        .query_map(params![project_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                ReusableSourceInstance {
                    assembly_ctg_id: row.get(1)?,
                    assembly_seq_id: row.get(2)?,
                },
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut map = HashMap::new();
    for (source_seq_id, instance) in rows {
        map.entry(source_seq_id).or_insert(instance);
    }
    Ok(map)
}

fn duplicate_source_seq_names(sources: &[SourceSeqPlacementCandidate]) -> HashSet<String> {
    let mut counts = HashMap::new();
    for source in sources {
        *counts.entry(source.seq_name.as_str()).or_insert(0_usize) += 1;
    }
    counts
        .into_iter()
        .filter_map(|(seq_name, count)| {
            if count > 1 {
                Some(seq_name.to_string())
            } else {
                None
            }
        })
        .collect()
}

fn source_ctg_base_name(
    source: &SourceSeqPlacementCandidate,
    duplicate_seq_names: &HashSet<String>,
) -> String {
    if duplicate_seq_names.contains(&source.seq_name) {
        format!("{}:{}", source.dataset_name, source.seq_name)
    } else {
        source.seq_name.clone()
    }
}

fn collect_source_chr_candidates(
    conn: &Connection,
    reference_genome_id: i64,
    source_seq_id: i64,
    source_seq_length: i64,
    params: &AutoAssignChrParams,
    min_coverage_percent: f64,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<Vec<ChrAssignmentCandidate>> {
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let source_seq_length = source_seq_length.max(1);
    let hits = list_reference_hits_for_source_seq(conn, reference_genome_id, source_seq_id)?;
    let mut chr_intervals: HashMap<String, Vec<(i64, i64)>> = HashMap::new();
    let mut chr_positions: HashMap<String, Vec<WeightedPosition>> = HashMap::new();

    for hit in hits {
        let qualified = hit.block_length >= params.alignment_block_size
            || ((hit.block_length as f64) * 100.0 / (source_seq_length as f64))
                >= params.alignment_coverage_percent;
        if !qualified {
            continue;
        }

        let candidate_anchor = if hit.strand == "+" {
            hit.ref_start - hit.query_start + 1
        } else {
            hit.ref_start - source_seq_length + hit.query_end
        };

        chr_intervals
            .entry(hit.chr_name.clone())
            .or_default()
            .push((hit.query_start, hit.query_end));
        chr_positions
            .entry(hit.chr_name)
            .or_default()
            .push(WeightedPosition {
                position: candidate_anchor,
                weight: hit.block_length,
            });
    }

    let mut candidates = Vec::new();
    for (chr_name, intervals) in chr_intervals {
        let support_bp = merged_interval_coverage(&intervals);
        let support_percent = (support_bp as f64) * 100.0 / (source_seq_length as f64);
        if support_percent < min_coverage_percent {
            continue;
        }
        let Some(positions) = chr_positions.get(&chr_name) else {
            continue;
        };
        candidates.push(ChrAssignmentCandidate {
            chr_name,
            support_bp,
            support_percent,
            anchor_start: weighted_median_of_positions(positions),
        });
    }
    candidates.sort_by(|left, right| {
        left.chr_name
            .cmp(&right.chr_name)
            .then_with(|| right.support_bp.cmp(&left.support_bp))
    });
    Ok(candidates)
}

fn list_reference_hits_for_source_seq(
    conn: &Connection,
    reference_genome_id: i64,
    source_seq_id: i64,
) -> Result<Vec<RefHit>> {
    let mut stmt = conn.prepare(
        "SELECT
            rc.chr_name,
            h.strand,
            h.query_start,
            h.query_end,
            h.ref_start,
            h.block_length
         FROM ref_alignment_hit h
         JOIN reference_chr rc ON rc.id = h.reference_chr_id
         WHERE h.source_seq_id = ?1
           AND rc.reference_genome_id = ?2",
    )?;
    let rows = stmt
        .query_map(params![source_seq_id, reference_genome_id], |row| {
            Ok(RefHit {
                chr_name: row.get(0)?,
                strand: row.get(1)?,
                query_start: row.get(2)?,
                query_end: row.get(3)?,
                ref_start: row.get(4)?,
                block_length: row.get(5)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(rows)
}

fn merged_interval_coverage(intervals: &[(i64, i64)]) -> i64 {
    if intervals.is_empty() {
        return 0;
    }

    let mut sorted = intervals.to_vec();
    sorted.sort_unstable_by(|left, right| left.0.cmp(&right.0).then(left.1.cmp(&right.1)));

    let mut total = 0_i64;
    let mut current = sorted[0];
    for &(start, end) in &sorted[1..] {
        if start <= current.1 + 1 {
            current.1 = current.1.max(end);
            continue;
        }
        total += current.1 - current.0 + 1;
        current = (start, end);
    }
    total + (current.1 - current.0 + 1)
}

fn weighted_median_of_positions(values: &[WeightedPosition]) -> i64 {
    let mut sorted = values.to_vec();
    sorted.sort_unstable_by(|left, right| left.position.cmp(&right.position));
    let total_weight = sorted.iter().map(|value| value.weight.max(0)).sum::<i64>();
    if total_weight <= 0 {
        let mid = sorted.len() / 2;
        return sorted[mid].position;
    }

    let threshold = (total_weight / 2) + 1;
    let mut cumulative = 0_i64;
    for value in &sorted {
        cumulative += value.weight.max(0);
        if cumulative >= threshold {
            return value.position;
        }
    }

    sorted[sorted.len() - 1].position
}

fn ensure_unplaced_source_instance(
    conn: &Connection,
    project_id: i64,
    source: &SourceSeqPlacementCandidate,
    reusable_instance: Option<ReusableSourceInstance>,
) -> Result<()> {
    if let Some(instance) = reusable_instance {
        conn.execute(
            "UPDATE assembly_seq
             SET instance_key = ?1,
                 orient = '+',
                 source_start = 1,
                 source_end = ?2,
                 left_end_type = 'normal',
                 right_end_type = 'normal',
                 hidden = 0
             WHERE id = ?3",
            params![
                format!("source:{}", source.source_seq_id),
                source.seq_length,
                instance.assembly_seq_id
            ],
        )?;
        conn.execute(
            "UPDATE assembly_ctg
             SET name = ?1,
                 assigned_chr_name = NULL,
                 chr_order = NULL,
                 anchor_start = NULL,
                 ref_orient = NULL,
                 placement_mode = 'none',
                 note = NULL
             WHERE id = ?2",
            params![source.ctg_base_name, instance.assembly_ctg_id],
        )?;
        return Ok(());
    }

    let created_at = "1";
    conn.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
         ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, NULL)",
        params![
            project_id,
            source.source_seq_id,
            format!("source:{}", source.source_seq_id),
            source.seq_length,
            created_at
        ],
    )?;
    let assembly_seq_id = conn.last_insert_rowid();
    conn.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
            ref_orient, placement_mode, created_at, note
         ) VALUES (?1, ?2, ?3, NULL, NULL, NULL, NULL, 'none', ?4, NULL)",
        params![
            project_id,
            assembly_seq_id,
            source.ctg_base_name,
            created_at
        ],
    )?;
    Ok(())
}

fn repurpose_source_instance_as_auto(
    conn: &Connection,
    instance: &ReusableSourceInstance,
    source: &SourceSeqPlacementCandidate,
    candidate: &ChrAssignmentCandidate,
) -> Result<()> {
    conn.execute(
        "UPDATE assembly_seq
         SET instance_key = ?1,
             orient = '+',
             source_start = 1,
             source_end = ?2,
             left_end_type = 'normal',
             right_end_type = 'normal',
             hidden = 0
         WHERE id = ?3",
        params![
            format!("chr:{}", candidate.chr_name),
            source.seq_length,
            instance.assembly_seq_id
        ],
    )?;
    let note = format!(
        "dataset_id={}; support_bp={}; support_percent={:.3}",
        source.dataset_id, candidate.support_bp, candidate.support_percent
    );
    conn.execute(
        "UPDATE assembly_ctg
         SET name = ?1,
             assigned_chr_name = ?2,
             chr_order = NULL,
             anchor_start = ?3,
             ref_orient = NULL,
             placement_mode = 'auto',
             note = ?4
         WHERE id = ?5",
        params![
            format!("{}@{}", source.ctg_base_name, candidate.chr_name),
            candidate.chr_name,
            candidate.anchor_start,
            note,
            instance.assembly_ctg_id
        ],
    )?;
    Ok(())
}

fn create_auto_chr_instance(
    conn: &Connection,
    project_id: i64,
    source: &SourceSeqPlacementCandidate,
    candidate: &ChrAssignmentCandidate,
) -> Result<()> {
    let created_at = "1";
    conn.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
         ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, NULL)",
        params![
            project_id,
            source.source_seq_id,
            format!("chr:{}", candidate.chr_name),
            source.seq_length,
            created_at
        ],
    )?;
    let assembly_seq_id = conn.last_insert_rowid();
    let note = format!(
        "dataset_id={}; support_bp={}; support_percent={:.3}",
        source.dataset_id, candidate.support_bp, candidate.support_percent
    );
    conn.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
            ref_orient, placement_mode, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, NULL, ?5, NULL, 'auto', ?6, ?7)",
        params![
            project_id,
            assembly_seq_id,
            format!("{}@{}", source.ctg_base_name, candidate.chr_name),
            candidate.chr_name,
            candidate.anchor_start,
            created_at,
            note
        ],
    )?;
    Ok(())
}

fn refresh_chr_order_for_chr(conn: &Connection, project_id: i64, chr_name: &str) -> Result<()> {
    let mut stmt = conn.prepare(
        "SELECT id
         FROM assembly_ctg
         WHERE project_id = ?1
           AND assigned_chr_name = ?2
         ORDER BY
            CASE WHEN anchor_start IS NULL THEN 1 ELSE 0 END,
            anchor_start,
            id",
    )?;
    let ctg_ids = stmt
        .query_map(params![project_id, chr_name], |row| row.get::<_, i64>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (index, ctg_id) in ctg_ids.into_iter().enumerate() {
        conn.execute(
            "UPDATE assembly_ctg SET chr_order = ?1 WHERE id = ?2",
            params![(index as i64) + 1, ctg_id],
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{AutoAssignChrParams, auto_assign_chr_with_connection};
    use crate::db::init_workspace_schema;
    use rusqlite::{Connection, params};

    struct SeededProject {
        project_id: i64,
        dataset_id: i64,
        source_seq_id: i64,
    }

    fn seed_project_with_single_source_seq(
        conn: &Connection,
        source_length: i64,
        chr_assignment_min_coverage_percent: f64,
    ) -> SeededProject {
        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/data/ref.fa', 'D:/data/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 1000000)",
            params![reference_id],
        )
        .expect("insert chr1");
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr02', 2, 1000000)",
            params![reference_id],
        )
        .expect("insert chr2");

        conn.execute(
            "INSERT INTO dataset (name, assembler, assembler_version, fasta_path, fai_path)
             VALUES ('ds1', 'asm', NULL, 'D:/bundle/data/datasets/ds1.fa', 'D:/bundle/data/datasets/ds1.fa.fai')",
            [],
        )
        .expect("insert dataset");
        let dataset_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (?1, 'tig1', 1, ?2)",
            params![dataset_id, source_length],
        )
        .expect("insert source_seq");
        let source_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, chr_assignment_min_coverage_percent,
                description, created_at, note
             ) VALUES ('p', 1, ?1, ?2, 0, ?3, NULL, '1', NULL)",
            params![
                reference_id,
                dataset_id,
                chr_assignment_min_coverage_percent
            ],
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
            "INSERT INTO assembly_seq (
                project_id, source_seq_id, instance_key, orient, source_start, source_end,
                left_end_type, right_end_type, hidden, created_at, note
             ) VALUES (?1, ?2, 'source:1', '+', 1, ?3, 'normal', 'normal', 0, '1', NULL)",
            params![project_id, source_seq_id, source_length],
        )
        .expect("insert assembly_seq");
        let assembly_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO assembly_ctg (
                project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
                ref_orient, placement_mode, created_at, note
             ) VALUES (?1, ?2, 'tig1', NULL, NULL, NULL, NULL, 'none', '1', NULL)",
            params![project_id, assembly_seq_id],
        )
        .expect("insert ctg");

        SeededProject {
            project_id,
            dataset_id,
            source_seq_id,
        }
    }

    fn reference_chr_id(conn: &Connection, chr_name: &str) -> i64 {
        conn.query_row(
            "SELECT id FROM reference_chr WHERE chr_name = ?1",
            params![chr_name],
            |row| row.get(0),
        )
        .expect("query chr id")
    }

    fn insert_ref_hit(
        conn: &Connection,
        dataset_id: i64,
        source_seq_id: i64,
        chr_name: &str,
        query_start: i64,
        query_end: i64,
        ref_start: i64,
    ) {
        let chr_id = reference_chr_id(conn, chr_name);
        let block_length = query_end - query_start + 1;
        let ref_end = ref_start + block_length - 1;
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end,
                ref_start, ref_end, match_length, block_length, mapq, run_name, note
             ) VALUES (?1, ?2, ?3, '+', ?4, ?5, ?6, ?7, ?8, ?8, 60, 'ds1_vs_ref', NULL)",
            params![
                dataset_id,
                source_seq_id,
                chr_id,
                query_start,
                query_end,
                ref_start,
                ref_end,
                block_length
            ],
        )
        .expect("insert ref hit");
    }

    #[test]
    fn assigns_chr_for_unplaced_ctg_from_cached_hits() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");

        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/data/ref.fa', 'D:/data/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 1000000)",
            params![reference_id],
        )
        .expect("insert chr1");
        let chr1_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr02', 2, 1000000)",
            params![reference_id],
        )
        .expect("insert chr2");
        let chr2_id = conn.last_insert_rowid();

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
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, chr_assignment_min_coverage_percent,
                description, created_at, note
             ) VALUES ('p', 1, ?1, ?2, 0, 20.0, NULL, '1', NULL)",
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
             VALUES (?1, ?2, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            params![project_id, source_seq_id],
        )
        .expect("insert assembly_seq");
        let assembly_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO assembly_ctg (project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (?1, ?2, 'Ctg1', NULL, NULL, NULL, NULL, 'none', '1', NULL)",
            params![project_id, assembly_seq_id],
        )
        .expect("insert ctg");
        let ctg_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '+', 10, 210, 5000, 5200, 200, 201, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr1_id],
        )
        .expect("insert hit chr1");
        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '+', 20, 80, 8000, 8060, 60, 61, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr2_id],
        )
        .expect("insert hit chr2");

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            project_id,
            &AutoAssignChrParams {
                alignment_block_size: 50,
                alignment_coverage_percent: 20.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 1);
        let placed = conn
            .query_row(
                "SELECT assigned_chr_name, anchor_start, placement_mode FROM assembly_ctg WHERE id = ?1",
                params![ctg_id],
                |row| {
                    Ok((
                        row.get::<_, Option<String>>(0)?,
                        row.get::<_, Option<i64>>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                },
            )
            .expect("query placed ctg");
        assert_eq!(placed.0.as_deref(), Some("Chr01"));
        assert_eq!(placed.1, Some(4991));
        assert_eq!(placed.2, "auto");
    }

    #[test]
    fn assigns_chr_using_deduplicated_support_per_member_and_chr() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");

        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/data/ref.fa', 'D:/data/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 1000000)",
            params![reference_id],
        )
        .expect("insert chr1");
        let chr1_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr02', 2, 1000000)",
            params![reference_id],
        )
        .expect("insert chr2");
        let chr2_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO dataset (name, assembler, assembler_version, fasta_path, fai_path)
             VALUES ('ds1', 'asm', NULL, 'D:/bundle/data/datasets/ds1.fa', 'D:/bundle/data/datasets/ds1.fa.fai')",
            [],
        )
        .expect("insert dataset");
        let dataset_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (?1, 'tig1', 1, 10000)",
            params![dataset_id],
        )
        .expect("insert source_seq");
        let source_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, chr_assignment_min_coverage_percent,
                description, created_at, note
             ) VALUES ('p', 1, ?1, ?2, 0, 70.0, NULL, '1', NULL)",
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
             VALUES (?1, ?2, '+', 1, 10000, 'normal', 'normal', 0, '1', NULL)",
            params![project_id, source_seq_id],
        )
        .expect("insert assembly_seq");
        let assembly_seq_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO assembly_ctg (project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (?1, ?2, 'Ctg1', NULL, NULL, NULL, NULL, 'none', '1', NULL)",
            params![project_id, assembly_seq_id],
        )
        .expect("insert ctg");
        let ctg_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '+', 1, 8000, 5000, 12999, 8000, 8000, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr1_id],
        )
        .expect("insert hit chr1");
        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '+', 1, 5001, 2000, 7000, 5001, 5001, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr2_id],
        )
        .expect("insert first overlapping hit chr2");
        conn.execute(
            "INSERT INTO ref_alignment_hit (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end, ref_start, ref_end, match_length, block_length, mapq, run_name, note)
             VALUES (?1, ?2, ?3, '+', 1001, 6001, 12000, 17000, 5001, 5001, 60, 'ds1_vs_ref', NULL)",
            params![dataset_id, source_seq_id, chr2_id],
        )
        .expect("insert second overlapping hit chr2");

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 1);
        let assigned_chr = conn
            .query_row(
                "SELECT assigned_chr_name FROM assembly_ctg WHERE id = ?1",
                params![ctg_id],
                |row| row.get::<_, Option<String>>(0),
            )
            .expect("query placed ctg");
        assert_eq!(assigned_chr.as_deref(), Some("Chr01"));
    }

    #[test]
    fn weights_anchor_start_by_hit_block_length() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");
        let seeded = seed_project_with_single_source_seq(&conn, 10_000, 10.0);

        for (query_start, ref_start) in [
            (1, 1_000),
            (11, 2_000),
            (21, 3_000),
            (31, 4_000),
            (41, 5_000),
        ] {
            insert_ref_hit(
                &conn,
                seeded.dataset_id,
                seeded.source_seq_id,
                "Chr01",
                query_start,
                query_start + 9,
                ref_start,
            );
        }
        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr01",
            1_001,
            9_000,
            51_000,
        );

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            seeded.project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 1);
        let anchor_start = conn
            .query_row(
                "SELECT anchor_start
                 FROM assembly_ctg
                 WHERE project_id = ?1
                   AND assigned_chr_name = 'Chr01'",
                params![seeded.project_id],
                |row| row.get::<_, Option<i64>>(0),
            )
            .expect("query weighted anchor");
        assert_eq!(anchor_start, Some(50_000));
    }

    #[test]
    fn creates_independent_chr_instances_for_each_passing_source_seq_support() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");
        let seeded = seed_project_with_single_source_seq(&conn, 10_000, 60.0);

        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr01",
            1,
            6_100,
            5_000,
        );
        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr02",
            1,
            6_000,
            15_000,
        );

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            seeded.project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1_000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 2);
        let rows = {
            let mut stmt = conn
                .prepare(
                    "SELECT c.name, c.assigned_chr_name, s.source_seq_id, s.instance_key
                     FROM assembly_ctg c
                     JOIN assembly_seq s ON s.id = c.assembly_seq_id
                     WHERE c.project_id = ?1
                     ORDER BY c.name",
                )
                .expect("prepare query");
            stmt.query_map(params![seeded.project_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<String>>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                ))
            })
            .expect("query rows")
            .collect::<std::result::Result<Vec<_>, _>>()
            .expect("collect rows")
        };
        assert_eq!(
            rows,
            vec![
                (
                    "tig1@Chr01".to_string(),
                    Some("Chr01".to_string()),
                    seeded.source_seq_id,
                    "chr:Chr01".to_string(),
                ),
                (
                    "tig1@Chr02".to_string(),
                    Some("Chr02".to_string()),
                    seeded.source_seq_id,
                    "chr:Chr02".to_string(),
                ),
            ]
        );
    }

    #[test]
    fn auto_assign_disambiguates_duplicate_source_names_across_project_datasets() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");

        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'sp', 'v1', 'D:/data/ref.fa', 'D:/data/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        let reference_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (?1, 'Chr01', 1, 1000000)",
            params![reference_id],
        )
        .expect("insert chr1");
        let chr1_id = conn.last_insert_rowid();

        let mut source_seq_ids = Vec::new();
        for (dataset_id, dataset_name, display_order) in [
            (11_i64, "hifiasm_ont", 1_i64),
            (12_i64, "hifiasm_hifi", 2_i64),
        ] {
            conn.execute(
                "INSERT INTO dataset (
                    id, name, assembler, assembler_version, fasta_path, fai_path
                 ) VALUES (?1, ?2, ?2, NULL, 'D:/bundle/data/datasets/ds.fa', 'D:/bundle/data/datasets/ds.fa.fai')",
                params![dataset_id, dataset_name],
            )
            .expect("insert dataset");
            conn.execute(
                "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
                 VALUES (?1, 'ctg1514', 1, 10000)",
                params![dataset_id],
            )
            .expect("insert source_seq");
            let source_seq_id = conn.last_insert_rowid();
            source_seq_ids.push((dataset_id, source_seq_id, display_order));
        }

        conn.execute(
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, chr_assignment_min_coverage_percent,
                description, created_at, note
             ) VALUES ('p', 1, ?1, 11, 0, 60.0, NULL, '1', NULL)",
            params![reference_id],
        )
        .expect("insert project");
        let project_id = conn.last_insert_rowid();
        for (dataset_id, source_seq_id, display_order) in source_seq_ids {
            let role = if dataset_id == 11 {
                "primary"
            } else {
                "support"
            };
            conn.execute(
                "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
                 VALUES (?1, ?2, ?3, ?4)",
                params![project_id, dataset_id, role, display_order],
            )
            .expect("insert project_dataset");
            conn.execute(
                "INSERT INTO ref_alignment_hit (
                    dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end,
                    ref_start, ref_end, match_length, block_length, mapq, run_name, note
                 ) VALUES (?1, ?2, ?3, '+', 1, 7000, 5000, 11999, 7000, 7000, 60, 'ds_vs_ref', NULL)",
                params![dataset_id, source_seq_id, chr1_id],
            )
            .expect("insert ref hit");
        }

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1_000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 2);
        let rows = {
            let mut stmt = conn
                .prepare(
                    "SELECT c.name, c.assigned_chr_name
                     FROM assembly_ctg c
                     WHERE c.project_id = ?1
                     ORDER BY c.name",
                )
                .expect("prepare query");
            stmt.query_map(params![project_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, Option<String>>(1)?))
            })
            .expect("query rows")
            .collect::<std::result::Result<Vec<_>, _>>()
            .expect("collect rows")
        };
        assert_eq!(
            rows,
            vec![
                (
                    "hifiasm_hifi:ctg1514@Chr01".to_string(),
                    Some("Chr01".to_string()),
                ),
                (
                    "hifiasm_ont:ctg1514@Chr01".to_string(),
                    Some("Chr01".to_string()),
                ),
            ]
        );
    }

    #[test]
    fn does_not_assign_best_chr_when_source_support_is_below_project_threshold() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");
        let seeded = seed_project_with_single_source_seq(&conn, 10_000, 60.0);

        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr01",
            1,
            5_900,
            5_000,
        );

        let summary = auto_assign_chr_with_connection(
            &mut conn,
            seeded.project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1_000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("auto assign");

        assert_eq!(summary.assigned_count, 0);
        let auto_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM assembly_ctg
                 WHERE project_id = ?1
                   AND placement_mode = 'auto'",
                params![seeded.project_id],
                |row| row.get(0),
            )
            .expect("query auto count");
        assert_eq!(auto_count, 0);
    }

    #[test]
    fn rebuilds_auto_instances_when_threshold_changes() {
        let mut conn = Connection::open_in_memory().expect("in-memory sqlite");
        init_workspace_schema(&conn).expect("init schema");
        let seeded = seed_project_with_single_source_seq(&conn, 10_000, 60.0);

        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr01",
            1,
            7_100,
            5_000,
        );
        insert_ref_hit(
            &conn,
            seeded.dataset_id,
            seeded.source_seq_id,
            "Chr02",
            1,
            6_000,
            15_000,
        );

        let first = auto_assign_chr_with_connection(
            &mut conn,
            seeded.project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1_000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("first auto assign");
        assert_eq!(first.assigned_count, 2);

        conn.execute(
            "UPDATE project
             SET chr_assignment_min_coverage_percent = 70.0
             WHERE id = ?1",
            params![seeded.project_id],
        )
        .expect("update threshold");

        let second = auto_assign_chr_with_connection(
            &mut conn,
            seeded.project_id,
            &AutoAssignChrParams {
                alignment_block_size: 1_000,
                alignment_coverage_percent: 25.0,
                assign_unplaced: true,
                reposition_anchored: false,
                skip_manual: true,
            },
        )
        .expect("second auto assign");

        assert_eq!(second.assigned_count, 1);
        let rows = {
            let mut stmt = conn
                .prepare(
                    "SELECT c.name, s.instance_key
                     FROM assembly_ctg c
                     JOIN assembly_seq s ON s.id = c.assembly_seq_id
                     WHERE c.project_id = ?1
                     ORDER BY c.name",
                )
                .expect("prepare query");
            stmt.query_map(params![seeded.project_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
            .expect("query rows")
            .collect::<std::result::Result<Vec<_>, _>>()
            .expect("collect rows")
        };
        assert_eq!(
            rows,
            vec![("tig1@Chr01".to_string(), "chr:Chr01".to_string())]
        );
    }
}
