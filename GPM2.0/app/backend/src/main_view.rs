use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, ToSql, params, params_from_iter};

use crate::db::open_workspace_db;
use crate::exporter::load_named_sequences_from_fasta;
use crate::reference_segments::{
    ReferenceGapInterval, ReferenceSegment, SplitReferenceBlock, detect_reference_gap_intervals,
    detect_reference_segments, map_paf_query_interval_to_ref_span, split_paf_hit_by_reference_gaps,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectChromosomeItem {
    pub chr_name: String,
    pub chr_order: i64,
    pub chr_length: i64,
    pub ctg_count: i64,
    pub placed_bp: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectChromosomes {
    pub project_id: i64,
    pub reference_genome_id: i64,
    pub items: Vec<ProjectChromosomeItem>,
    pub unplaced_ctg_count: i64,
    pub unplaced_bp: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChrViewCtgItem {
    pub assembly_ctg_id: i64,
    pub name: String,
    pub origin_id: Option<String>,
    pub origin_source_seq_id: Option<i64>,
    pub co_assigned_chr_names: Vec<String>,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
    pub anchor_start: Option<i64>,
    pub ref_orient: Option<String>,
    pub orient: Option<String>,
    pub placement_mode: String,
    pub member_count: i64,
    pub total_length: i64,
    pub dataset_id: Option<i64>,
    pub dataset_name: Option<String>,
    pub derived_source: Option<String>,
    pub derived_target_dataset_id: Option<i64>,
    pub derived_target_dataset_name: Option<String>,
    pub hits: Vec<ChrViewHitItem>,
    pub n_regions: Vec<ChrViewNRegionItem>,
    pub telomere_marks: Vec<ChrViewTelomereMarkItem>,
    pub centromere_marks: Vec<ChrViewCentromereMarkItem>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChrViewNRegionItem {
    pub start_bp: i64,
    pub end_bp: i64,
    pub length_bp: i64,
    pub ctg_start: i64,
    pub ctg_end: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChrViewTelomereMarkItem {
    pub rule_id: String,
    pub motif: String,
    pub min_repeat: i64,
    pub repeat_count: i64,
    pub start_bp: i64,
    pub end_bp: i64,
    pub strand: String,
    pub ctg_start: i64,
    pub ctg_end: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChrViewCentromereMarkItem {
    pub cen_id: String,
    pub query_name: String,
    pub start_bp: i64,
    pub end_bp: i64,
    pub strand: String,
    pub align_length: i64,
    pub identity: f64,
    pub mapq: i64,
    pub ctg_start: i64,
    pub ctg_end: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChrViewHitItem {
    pub hit_id: i64,
    pub assembly_ctg_member_id: i64,
    pub assembly_seq_id: i64,
    pub source_seq_id: i64,
    pub strand: String,
    pub query_start: i64,
    pub query_end: i64,
    pub ref_start: i64,
    pub ref_end: i64,
    pub match_length: i64,
    pub block_length: i64,
    pub mapq: i64,
    pub ctg_start: i64,
    pub ctg_end: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReferenceTrackMemberItem {
    pub source_kind: String,
    pub reference_chr_id: i64,
    pub reference_chr_name: String,
    pub segment_order: i64,
    pub segment_start_bp: i64,
    pub segment_end_bp: i64,
    pub name: String,
    pub anchor_start: i64,
    pub total_length: i64,
    pub ref_orient: String,
    pub hits: Vec<ReferenceTrackHitItem>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReferenceTrackHitItem {
    pub hit_id: i64,
    pub dataset_id: i64,
    pub source_seq_id: i64,
    pub strand: String,
    pub query_start: i64,
    pub query_end: i64,
    pub ref_start: i64,
    pub ref_end: i64,
    pub match_length: i64,
    pub block_length: i64,
    pub mapq: i64,
    pub ctg_start: i64,
    pub ctg_end: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CtgDetail {
    pub assembly_ctg_id: i64,
    pub project_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
    pub anchor_start: Option<i64>,
    pub ref_orient: Option<String>,
    pub placement_mode: String,
    pub members: Vec<CtgDetailMember>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CtgDetailMember {
    pub assembly_ctg_member_id: i64,
    pub assembly_seq_id: i64,
    pub dataset_name: String,
    pub seq_name: String,
    pub seq_length: i64,
    pub orient: String,
    pub source_start: i64,
    pub source_end: i64,
    pub left_end_type: String,
    pub right_end_type: String,
    pub hidden: bool,
    pub member_order: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CtgEditCandidates {
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub move_target_ctgs: Vec<MoveTargetCtg>,
    pub add_seq_candidates: Vec<AddSeqCandidate>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MoveTargetCtg {
    pub assembly_ctg_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddSeqCandidate {
    pub assembly_seq_id: i64,
    pub dataset_name: String,
    pub seq_name: String,
    pub seq_length: i64,
    pub hidden: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectNewSequenceItem {
    pub assembly_seq_id: i64,
    pub dataset_name: String,
    pub seq_name: String,
    pub seq_length: i64,
    pub hidden: bool,
}

pub fn list_project_chromosomes(
    project_db_path: &Path,
    project_id: i64,
) -> Result<ProjectChromosomes> {
    let conn = open_workspace_db(project_db_path)?;
    list_project_chromosomes_with_connection(&conn, project_id)
}

pub fn list_project_chromosomes_with_connection(
    conn: &Connection,
    project_id: i64,
) -> Result<ProjectChromosomes> {
    let (reference_genome_id, primary_dataset_id): (i64, i64) = conn
        .query_row(
            "SELECT reference_genome_id, primary_dataset_id
             FROM project
             WHERE id = ?1",
            params![project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .with_context(|| format!("project_id {} does not exist", project_id))?;

    let mut chr_stmt = conn
        .prepare(
            "SELECT chr_name, chr_order, length
             FROM reference_chr
             WHERE reference_genome_id = ?1
             ORDER BY chr_order, id",
        )
        .context("failed to prepare reference chr query")?;
    let chr_rows = chr_stmt
        .query_map(params![reference_genome_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .context("failed to query reference chr rows")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to read reference chr rows")?;

    let mut items = Vec::with_capacity(chr_rows.len());
    for (chr_name, chr_order, chr_length) in chr_rows {
        let (ctg_count, placed_bp): (i64, i64) = conn
            .query_row(
                "SELECT
                    COUNT(DISTINCT c.id),
                    COALESCE(
                        SUM(
                            CASE
                                WHEN s.hidden = 0 AND s.source_end >= s.source_start
                                THEN (s.source_end - s.source_start + 1)
                                ELSE 0
                            END
                        ),
                        0
                    )
                 FROM assembly_ctg c
                 LEFT JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 LEFT JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE c.project_id = ?1
                   AND c.assigned_chr_name = ?2
                   AND s.hidden = 0
                   AND ss.dataset_id = ?3",
                params![project_id, chr_name, primary_dataset_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .with_context(|| format!("failed to query chr summary for chr={}", chr_name))?;
        items.push(ProjectChromosomeItem {
            chr_name,
            chr_order,
            chr_length,
            ctg_count,
            placed_bp,
        });
    }

    let (unplaced_ctg_count, unplaced_bp): (i64, i64) = conn
        .query_row(
            "SELECT
                COUNT(DISTINCT c.id),
                COALESCE(
                    SUM(
                        CASE
                            WHEN s.hidden = 0 AND s.source_end >= s.source_start
                            THEN (s.source_end - s.source_start + 1)
                            ELSE 0
                        END
                    ),
                    0
                )
             FROM assembly_ctg c
             LEFT JOIN assembly_seq s ON s.id = c.assembly_seq_id
             LEFT JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE c.project_id = ?1
               AND (c.assigned_chr_name IS NULL OR c.assigned_chr_name = '')
               AND s.hidden = 0
               AND ss.dataset_id = ?2",
            params![project_id, primary_dataset_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .context("failed to query unplaced summary")?;

    Ok(ProjectChromosomes {
        project_id,
        reference_genome_id,
        items,
        unplaced_ctg_count,
        unplaced_bp,
    })
}

pub fn list_chr_view_ctgs(
    project_db_path: &Path,
    project_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<ChrViewCtgItem>> {
    let conn = open_workspace_db(project_db_path)?;
    list_chr_view_ctgs_with_connection(&conn, project_id, chr_name, dataset_id)
}

pub fn list_chr_view_ctgs_with_connection(
    conn: &Connection,
    project_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<ChrViewCtgItem>> {
    let chr_param = chr_name.map(ToOwned::to_owned);
    let dataset_param = dataset_id;
    let primary_dataset_id: i64 = conn
        .query_row(
            "SELECT primary_dataset_id FROM project WHERE id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .with_context(|| format!("project_id {} does not exist", project_id))?;
    let mut sql = String::from(
        "
        SELECT
            c.id,
            c.name,
            CASE
                WHEN COUNT(DISTINCT CASE WHEN s.hidden = 0 THEN ss.seq_name END) = 1
                THEN MAX(CASE WHEN s.hidden = 0 THEN ss.seq_name END)
                ELSE NULL
            END AS origin_id,
            CASE
                WHEN COUNT(DISTINCT CASE WHEN s.hidden = 0 THEN ss.id END) = 1
                THEN MAX(CASE WHEN s.hidden = 0 THEN ss.id END)
                ELSE NULL
            END AS origin_source_seq_id,
            c.assigned_chr_name,
            c.chr_order,
            c.anchor_start,
            c.ref_orient,
            CASE
                WHEN COUNT(DISTINCT CASE WHEN s.hidden = 0 THEN s.orient END) = 1
                THEN MAX(CASE WHEN s.hidden = 0 THEN s.orient END)
                ELSE NULL
            END AS orient,
            c.placement_mode,
            COUNT(s.id) AS member_count,
            COALESCE(
                SUM(
                    CASE
                        WHEN s.hidden = 0 AND s.source_end >= s.source_start
                        THEN (s.source_end - s.source_start + 1)
                        ELSE 0
                    END
                ),
                0
            ) AS total_length,
            CASE
                WHEN COUNT(DISTINCT CASE WHEN s.hidden = 0 THEN ss.dataset_id END) = 1
                THEN MAX(CASE WHEN s.hidden = 0 THEN ss.dataset_id END)
                ELSE NULL
            END AS dataset_id,
            CASE
                WHEN COUNT(DISTINCT CASE WHEN s.hidden = 0 THEN ss.dataset_id END) = 1
                THEN MAX(CASE WHEN s.hidden = 0 THEN d.name END)
                ELSE NULL
            END AS dataset_name,
            MAX(dc.source) AS derived_source,
            MAX(dtm.target_dataset_id) AS derived_target_dataset_id,
            MAX(target_d.name) AS derived_target_dataset_name
        FROM assembly_ctg c
        LEFT JOIN assembly_seq s ON s.id = c.assembly_seq_id
        LEFT JOIN source_seq ss ON ss.id = s.source_seq_id
        LEFT JOIN dataset d ON d.id = ss.dataset_id
        LEFT JOIN derived_ctg dc ON dc.source_seq_id = ss.id
        LEFT JOIN derived_ctg_track_member dtm
          ON dtm.project_id = c.project_id
         AND dtm.source_seq_id = ss.id
        LEFT JOIN dataset target_d ON target_d.id = dtm.target_dataset_id
        WHERE c.project_id = ?",
    );
    let mut bind_values: Vec<&dyn ToSql> = vec![&project_id];
    if let Some(chr_name) = chr_param.as_ref() {
        sql.push_str(" AND c.assigned_chr_name = ?");
        bind_values.push(chr_name);
    }
    if let Some(dataset_id) = dataset_param.as_ref() {
        sql.push_str(
            " AND s.hidden = 0
              AND (ss.dataset_id = ? OR dtm.target_dataset_id = ?)",
        );
        bind_values.push(dataset_id);
        bind_values.push(dataset_id);
        if *dataset_id != primary_dataset_id {
            sql.push_str(
                " AND NOT (
                    s.hidden = 0
                    AND ss.dataset_id = ?
                )",
            );
            bind_values.push(&primary_dataset_id);
        }
    }
    sql.push_str(
        "
         GROUP BY c.id, c.name, c.assigned_chr_name, c.chr_order, c.anchor_start, c.ref_orient, c.placement_mode
         ORDER BY
            CASE WHEN c.assigned_chr_name IS NULL OR c.assigned_chr_name = '' THEN 1 ELSE 0 END,
            c.assigned_chr_name,
            c.chr_order,
            c.anchor_start,
            c.id",
    );
    let mut stmt = conn
        .prepare(&sql)
        .context("failed to prepare chr view ctg query")?;
    let mapped = stmt
        .query_map(params_from_iter(bind_values), decode_chr_view_row)
        .context("failed to query chr view ctgs")?;
    let mut ctgs = mapped
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode chr view ctgs")?;

    if ctgs.is_empty() {
        return Ok(ctgs);
    }

    populate_co_assigned_chr_names(conn, project_id, &mut ctgs)?;

    let reference_genome_id: i64 = conn
        .query_row(
            "SELECT reference_genome_id FROM project WHERE id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .with_context(|| format!("project_id {} does not exist", project_id))?;

    for ctg in &mut ctgs {
        let hit_dataset_filter = if dataset_param == Some(primary_dataset_id) {
            None
        } else if ctg.derived_target_dataset_id == dataset_param {
            None
        } else {
            dataset_param
        };
        ctg.hits = list_chr_view_hits_with_connection(
            conn,
            project_id,
            reference_genome_id,
            ctg.assembly_ctg_id,
            chr_name,
            hit_dataset_filter,
        )?;
        ctg.n_regions =
            list_chr_view_n_regions_with_connection(conn, project_id, ctg.assembly_ctg_id)?;
        if ctg.dataset_id == Some(primary_dataset_id) {
            ctg.telomere_marks = list_chr_view_telomere_marks_with_connection(
                conn,
                project_id,
                ctg.assembly_ctg_id,
            )?;
            ctg.centromere_marks = list_chr_view_centromere_marks_with_connection(
                conn,
                project_id,
                ctg.assembly_ctg_id,
            )?;
        }
    }

    Ok(ctgs)
}

pub fn list_project_new_sequences(
    project_db_path: &Path,
    project_id: i64,
) -> Result<Vec<ProjectNewSequenceItem>> {
    let conn = open_workspace_db(project_db_path)?;
    list_project_new_sequences_with_connection(&conn, project_id)
}

pub fn list_project_new_sequences_with_connection(
    conn: &Connection,
    project_id: i64,
) -> Result<Vec<ProjectNewSequenceItem>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                s.id,
                d.name,
                ss.seq_name,
                ss.length,
                s.hidden
             FROM assembly_seq s
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE s.project_id = ?1
               AND NOT EXISTS (
                    SELECT 1
                    FROM assembly_ctg c
                    WHERE c.assembly_seq_id = s.id
               )
             ORDER BY d.name, ss.seq_name, s.id",
        )
        .context("failed to prepare new sequence query")?;
    stmt.query_map(params![project_id], |row| {
        Ok(ProjectNewSequenceItem {
            assembly_seq_id: row.get(0)?,
            dataset_name: row.get(1)?,
            seq_name: row.get(2)?,
            seq_length: row.get(3)?,
            hidden: row.get::<_, i64>(4)? > 0,
        })
    })
    .context("failed to query new sequences")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode new sequences")
}

fn decode_chr_view_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ChrViewCtgItem> {
    Ok(ChrViewCtgItem {
        assembly_ctg_id: row.get(0)?,
        name: row.get(1)?,
        origin_id: row.get(2)?,
        origin_source_seq_id: row.get(3)?,
        co_assigned_chr_names: Vec::new(),
        assigned_chr_name: row.get(4)?,
        chr_order: row.get(5)?,
        anchor_start: row.get(6)?,
        ref_orient: row.get(7)?,
        orient: row.get(8)?,
        placement_mode: row.get(9)?,
        member_count: row.get(10)?,
        total_length: row.get(11)?,
        dataset_id: row.get(12)?,
        dataset_name: row.get(13)?,
        derived_source: row.get(14)?,
        derived_target_dataset_id: row.get(15)?,
        derived_target_dataset_name: row.get(16)?,
        hits: Vec::new(),
        n_regions: Vec::new(),
        telomere_marks: Vec::new(),
        centromere_marks: Vec::new(),
    })
}

fn populate_co_assigned_chr_names(
    conn: &Connection,
    project_id: i64,
    ctgs: &mut [ChrViewCtgItem],
) -> Result<()> {
    let mut source_seq_ids = ctgs
        .iter()
        .filter_map(|ctg| ctg.origin_source_seq_id)
        .collect::<Vec<_>>();
    source_seq_ids.sort_unstable();
    source_seq_ids.dedup();
    if source_seq_ids.is_empty() {
        return Ok(());
    }

    let placeholders = vec!["?"; source_seq_ids.len()].join(", ");
    let sql = format!(
        "SELECT s.source_seq_id, c.assigned_chr_name
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         WHERE c.project_id = ?
           AND s.hidden = 0
           AND s.source_seq_id IN ({})
           AND c.assigned_chr_name IS NOT NULL
           AND c.assigned_chr_name <> ''
         GROUP BY s.source_seq_id, c.assigned_chr_name
         ORDER BY s.source_seq_id, c.assigned_chr_name",
        placeholders
    );
    let mut bind_values: Vec<&dyn ToSql> = vec![&project_id];
    for source_seq_id in &source_seq_ids {
        bind_values.push(source_seq_id);
    }
    let mut stmt = conn
        .prepare(&sql)
        .context("failed to prepare co-assigned chr query")?;
    let rows = stmt
        .query_map(params_from_iter(bind_values), |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .context("failed to query co-assigned chr names")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode co-assigned chr names")?;

    let mut chr_names_by_source_seq_id: HashMap<i64, Vec<String>> = HashMap::new();
    for (source_seq_id, chr_name) in rows {
        chr_names_by_source_seq_id
            .entry(source_seq_id)
            .or_default()
            .push(chr_name);
    }

    for ctg in ctgs {
        let Some(source_seq_id) = ctg.origin_source_seq_id else {
            continue;
        };
        let current_chr = ctg.assigned_chr_name.as_deref();
        ctg.co_assigned_chr_names = chr_names_by_source_seq_id
            .get(&source_seq_id)
            .map(|chr_names| {
                chr_names
                    .iter()
                    .filter(|chr_name| Some(chr_name.as_str()) != current_chr)
                    .cloned()
                    .collect()
            })
            .unwrap_or_default();
    }
    Ok(())
}

#[derive(Debug, Clone)]
struct ChrViewMemberLayout {
    assembly_ctg_member_id: i64,
    source_seq_id: i64,
    source_start: i64,
    source_end: i64,
    orient: String,
    ctg_offset: i64,
}

#[derive(Debug, Clone)]
struct ChrViewHitRow {
    assembly_ctg_member_id: i64,
    assembly_seq_id: i64,
    source_seq_id: i64,
    hit_id: i64,
    strand: String,
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    ref_end: i64,
    match_length: i64,
    block_length: i64,
    mapq: i64,
    cg_tag: Option<String>,
}

#[derive(Debug, Clone)]
struct ChrViewNRegionRow {
    source_seq_id: i64,
    start_bp: i64,
    end_bp: i64,
}

#[derive(Debug, Clone)]
struct ChrViewTelomereMarkRow {
    rule_id: String,
    motif: String,
    min_repeat: i64,
    repeat_count: i64,
    start_bp: i64,
    end_bp: i64,
    strand: String,
}

#[derive(Debug, Clone)]
struct ChrViewCentromereMarkRow {
    cen_id: String,
    query_name: String,
    start_bp: i64,
    end_bp: i64,
    strand: String,
    align_length: i64,
    identity: f64,
    mapq: i64,
}

#[derive(Debug, Clone)]
struct ReferenceTrackHitRow {
    hit_id: i64,
    dataset_id: i64,
    source_seq_id: i64,
    strand: String,
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    ref_end: i64,
    match_length: i64,
    block_length: i64,
    mapq: i64,
    cg_tag: Option<String>,
}

fn list_chr_view_n_regions_with_connection(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewNRegionItem>> {
    let member_layouts = load_chr_view_member_layouts(conn, project_id, assembly_ctg_id)?;
    if member_layouts.is_empty() {
        return Ok(Vec::new());
    }
    let n_rows = load_chr_view_n_region_rows(conn, project_id, assembly_ctg_id)?;
    if n_rows.is_empty() {
        return Ok(Vec::new());
    }

    let mut rows_by_source_seq_id: HashMap<i64, Vec<ChrViewNRegionRow>> = HashMap::new();
    for row in n_rows {
        rows_by_source_seq_id
            .entry(row.source_seq_id)
            .or_default()
            .push(row);
    }

    let mut regions = Vec::new();
    for layout in &member_layouts {
        let Some(rows) = rows_by_source_seq_id.get(&layout.source_seq_id) else {
            continue;
        };
        for row in rows {
            let clipped_start = row.start_bp.max(layout.source_start);
            let clipped_end = row.end_bp.min(layout.source_end);
            if clipped_start > clipped_end {
                continue;
            }
            let (ctg_start, ctg_end) =
                project_source_interval_to_ctg(layout, clipped_start, clipped_end);
            regions.push(ChrViewNRegionItem {
                start_bp: clipped_start,
                end_bp: clipped_end,
                length_bp: clipped_end - clipped_start + 1,
                ctg_start,
                ctg_end,
            });
        }
    }
    regions.sort_by_key(|region| (region.ctg_start, region.ctg_end));
    Ok(regions)
}

fn load_chr_view_n_region_rows(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewNRegionRow>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                nr.source_seq_id,
                nr.start_bp,
                nr.end_bp
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN source_seq_n_region nr ON nr.source_seq_id = ss.id
             WHERE c.id = ?1
               AND c.project_id = ?2
               AND s.hidden = 0
             ORDER BY nr.source_seq_id, nr.start_bp, nr.end_bp",
        )
        .context("failed to prepare chr view n region query")?;
    stmt.query_map(params![assembly_ctg_id, project_id], |row| {
        Ok(ChrViewNRegionRow {
            source_seq_id: row.get(0)?,
            start_bp: row.get(1)?,
            end_bp: row.get(2)?,
        })
    })
    .context("failed to query chr view n regions")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode chr view n regions")
}

fn list_chr_view_telomere_marks_with_connection(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewTelomereMarkItem>> {
    let member_layouts = load_chr_view_member_layouts(conn, project_id, assembly_ctg_id)?;
    if member_layouts.is_empty() {
        return Ok(Vec::new());
    }
    let Some(layout) = member_layouts.first() else {
        return Ok(Vec::new());
    };
    let mark_rows = load_chr_view_telomere_mark_rows(conn, project_id, assembly_ctg_id)?;
    let mut marks = Vec::with_capacity(mark_rows.len());
    for row in mark_rows {
        let clipped_start = row.start_bp.max(layout.source_start);
        let clipped_end = row.end_bp.min(layout.source_end);
        if clipped_start > clipped_end {
            continue;
        }
        let (ctg_start, ctg_end) = if layout.orient == "-" {
            (
                layout.ctg_offset + (layout.source_end - clipped_end + 1),
                layout.ctg_offset + (layout.source_end - clipped_start + 1),
            )
        } else {
            (
                layout.ctg_offset + (clipped_start - layout.source_start + 1),
                layout.ctg_offset + (clipped_end - layout.source_start + 1),
            )
        };
        marks.push(ChrViewTelomereMarkItem {
            rule_id: row.rule_id,
            motif: row.motif,
            min_repeat: row.min_repeat,
            repeat_count: row.repeat_count,
            start_bp: clipped_start,
            end_bp: clipped_end,
            strand: row.strand,
            ctg_start,
            ctg_end,
        });
    }
    marks.sort_by_key(|mark| (mark.ctg_start, mark.ctg_end, mark.rule_id.clone()));
    Ok(marks)
}

fn list_chr_view_centromere_marks_with_connection(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewCentromereMarkItem>> {
    let member_layouts = load_chr_view_member_layouts(conn, project_id, assembly_ctg_id)?;
    if member_layouts.is_empty() {
        return Ok(Vec::new());
    }
    let Some(layout) = member_layouts.first() else {
        return Ok(Vec::new());
    };
    let mark_rows = load_chr_view_centromere_mark_rows(conn, project_id, assembly_ctg_id)?;
    let mut marks = Vec::with_capacity(mark_rows.len());
    for row in mark_rows {
        let clipped_start = row.start_bp.max(layout.source_start);
        let clipped_end = row.end_bp.min(layout.source_end);
        if clipped_start > clipped_end {
            continue;
        }
        let (ctg_start, ctg_end) = if layout.orient == "-" {
            (
                layout.ctg_offset + (layout.source_end - clipped_end + 1),
                layout.ctg_offset + (layout.source_end - clipped_start + 1),
            )
        } else {
            (
                layout.ctg_offset + (clipped_start - layout.source_start + 1),
                layout.ctg_offset + (clipped_end - layout.source_start + 1),
            )
        };
        marks.push(ChrViewCentromereMarkItem {
            cen_id: row.cen_id,
            query_name: row.query_name,
            start_bp: clipped_start,
            end_bp: clipped_end,
            strand: row.strand,
            align_length: row.align_length,
            identity: row.identity,
            mapq: row.mapq,
            ctg_start,
            ctg_end,
        });
    }
    marks.sort_by(|left, right| {
        (left.ctg_start, left.ctg_end, &left.cen_id).cmp(&(
            right.ctg_start,
            right.ctg_end,
            &right.cen_id,
        ))
    });
    Ok(marks)
}

fn load_chr_view_centromere_mark_rows(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewCentromereMarkRow>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                cm.cen_id,
                cm.query_name,
                cm.start_bp,
                cm.end_bp,
                cm.strand,
                cm.align_length,
                cm.identity,
                cm.mapq
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN source_seq_centromere_mark cm ON cm.source_seq_id = ss.id
             WHERE c.id = ?1
               AND c.project_id = ?2
               AND s.hidden = 0
               AND cm.assigned_chr_name = c.assigned_chr_name
             ORDER BY cm.start_bp, cm.end_bp, cm.cen_id",
        )
        .context("failed to prepare chr view centromere mark query")?;
    stmt.query_map(params![assembly_ctg_id, project_id], |row| {
        Ok(ChrViewCentromereMarkRow {
            cen_id: row.get(0)?,
            query_name: row.get(1)?,
            start_bp: row.get(2)?,
            end_bp: row.get(3)?,
            strand: row.get(4)?,
            align_length: row.get(5)?,
            identity: row.get(6)?,
            mapq: row.get(7)?,
        })
    })
    .context("failed to query chr view centromere marks")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode chr view centromere marks")
}

fn load_chr_view_telomere_mark_rows(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewTelomereMarkRow>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                tm.rule_id,
                tm.motif,
                tm.min_repeat,
                tm.repeat_count,
                tm.start_bp,
                tm.end_bp,
                tm.strand
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN source_seq_telomere_mark tm ON tm.source_seq_id = ss.id
             WHERE c.id = ?1
               AND c.project_id = ?2
               AND s.hidden = 0
               AND tm.assigned_chr_name = c.assigned_chr_name
             ORDER BY tm.start_bp, tm.end_bp, tm.rule_id",
        )
        .context("failed to prepare chr view telomere mark query")?;
    stmt.query_map(params![assembly_ctg_id, project_id], |row| {
        Ok(ChrViewTelomereMarkRow {
            rule_id: row.get(0)?,
            motif: row.get(1)?,
            min_repeat: row.get(2)?,
            repeat_count: row.get(3)?,
            start_bp: row.get(4)?,
            end_bp: row.get(5)?,
            strand: row.get(6)?,
        })
    })
    .context("failed to query chr view telomere marks")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode chr view telomere marks")
}

fn list_chr_view_hits_with_connection(
    conn: &Connection,
    project_id: i64,
    reference_genome_id: i64,
    assembly_ctg_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<ChrViewHitItem>> {
    let member_layouts = load_chr_view_member_layouts(conn, project_id, assembly_ctg_id)?;
    if member_layouts.is_empty() {
        return Ok(Vec::new());
    }

    let hit_rows = load_chr_view_hit_rows(
        conn,
        assembly_ctg_id,
        project_id,
        reference_genome_id,
        chr_name,
        dataset_id,
    )?;
    if hit_rows.is_empty() {
        return Ok(Vec::new());
    }

    let layout_by_member_id = member_layouts
        .into_iter()
        .map(|layout| (layout.assembly_ctg_member_id, layout))
        .collect::<HashMap<_, _>>();
    let source_seq_ids = hit_rows
        .iter()
        .map(|row| row.source_seq_id)
        .collect::<HashSet<_>>();
    let n_regions_by_source_seq_id = load_n_regions_by_source_seq_id(conn, &source_seq_ids)?;

    let mut hits = Vec::with_capacity(hit_rows.len());
    for row in hit_rows {
        let Some(layout) = layout_by_member_id.get(&row.assembly_ctg_member_id) else {
            continue;
        };

        let clipped_start = row.query_start.max(layout.source_start);
        let clipped_end = row.query_end.min(layout.source_end);
        if clipped_start > clipped_end {
            continue;
        }

        let member_length = (layout.source_end - layout.source_start + 1).max(0);
        if member_length <= 0 {
            continue;
        }

        let segments = split_hit_around_n_regions(
            &row,
            clipped_start,
            clipped_end,
            n_regions_by_source_seq_id
                .get(&row.source_seq_id)
                .map(Vec::as_slice)
                .unwrap_or(&[]),
        );
        for segment in segments {
            let (ctg_start, ctg_end) =
                project_source_interval_to_ctg(layout, segment.query_start, segment.query_end);
            let segment_length = segment.query_end - segment.query_start + 1;
            hits.push(ChrViewHitItem {
                hit_id: row.hit_id,
                assembly_ctg_member_id: row.assembly_ctg_member_id,
                assembly_seq_id: row.assembly_seq_id,
                source_seq_id: row.source_seq_id,
                strand: row.strand.clone(),
                query_start: segment.query_start,
                query_end: segment.query_end,
                ref_start: segment.ref_start,
                ref_end: segment.ref_end,
                match_length: row.match_length.min(segment_length),
                block_length: row.block_length.min(segment_length),
                mapq: row.mapq,
                ctg_start,
                ctg_end,
            });
        }
    }

    Ok(hits)
}

fn load_chr_view_member_layouts(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<Vec<ChrViewMemberLayout>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                c.id,
                s.source_seq_id,
                s.source_start,
                s.source_end,
                s.orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE c.id = ?1
               AND s.project_id = ?2
               AND s.hidden = 0
             ORDER BY c.id",
        )
        .context("failed to prepare chr view member layout query")?;
    let rows = stmt
        .query_map(params![assembly_ctg_id, project_id], |row| {
            Ok(ChrViewMemberLayout {
                assembly_ctg_member_id: row.get(0)?,
                source_seq_id: row.get(1)?,
                source_start: row.get(2)?,
                source_end: row.get(3)?,
                orient: row.get(4)?,
                ctg_offset: 0,
            })
        })
        .context("failed to query chr view member layouts")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode chr view member layouts")?;

    let mut ctg_offset = 0_i64;
    let mut layouts = Vec::with_capacity(rows.len());
    for mut layout in rows {
        let member_length = (layout.source_end - layout.source_start + 1).max(0);
        layout.ctg_offset = ctg_offset;
        ctg_offset += member_length;
        layouts.push(layout);
    }

    Ok(layouts)
}

fn load_chr_view_hit_rows(
    conn: &Connection,
    assembly_ctg_id: i64,
    project_id: i64,
    reference_genome_id: i64,
    chr_name: Option<&str>,
    dataset_id: Option<i64>,
) -> Result<Vec<ChrViewHitRow>> {
    let base_sql = "
        SELECT
            c.id,
            s.id,
            ss.id,
            h.id,
            h.strand,
            h.query_start,
            h.query_end,
            h.ref_start,
            h.ref_end,
            h.match_length,
            h.block_length,
            h.mapq,
            h.cg_tag
        FROM assembly_ctg c
        JOIN assembly_seq s ON s.id = c.assembly_seq_id
        JOIN source_seq ss ON ss.id = s.source_seq_id
        JOIN ref_alignment_hit h ON h.source_seq_id = ss.id
        JOIN reference_chr rc ON rc.id = h.reference_chr_id
        WHERE c.id = ?1
          AND s.project_id = ?2
          AND s.hidden = 0
          AND rc.reference_genome_id = ?3";

    let sql = match (chr_name, dataset_id) {
        (Some(_), Some(_)) => format!(
            "{} AND rc.chr_name = ?4
             AND ss.dataset_id = ?5
             ORDER BY c.id, h.id",
            base_sql
        ),
        (Some(_), None) => format!(
            "{} AND rc.chr_name = ?4
             ORDER BY c.id, h.id",
            base_sql
        ),
        (None, Some(_)) => format!(
            "{} AND ss.dataset_id = ?4
             ORDER BY c.id, h.id",
            base_sql
        ),
        (None, None) => format!("{} ORDER BY c.id, h.id", base_sql),
    };

    let mut stmt = conn
        .prepare(&sql)
        .context("failed to prepare chr view hit query")?;
    let rows = match (chr_name, dataset_id) {
        (Some(chr), Some(dataset)) => {
            let mapped = stmt
                .query_map(
                    params![
                        assembly_ctg_id,
                        project_id,
                        reference_genome_id,
                        chr,
                        dataset
                    ],
                    decode_chr_view_hit_row,
                )
                .context("failed to query chr view hit rows")?;
            mapped
                .collect::<std::result::Result<Vec<_>, _>>()
                .context("failed to decode chr view hit rows")?
        }
        (Some(chr), None) => {
            let mapped = stmt
                .query_map(
                    params![assembly_ctg_id, project_id, reference_genome_id, chr],
                    decode_chr_view_hit_row,
                )
                .context("failed to query chr view hit rows")?;
            mapped
                .collect::<std::result::Result<Vec<_>, _>>()
                .context("failed to decode chr view hit rows")?
        }
        (None, Some(dataset)) => {
            let mapped = stmt
                .query_map(
                    params![assembly_ctg_id, project_id, reference_genome_id, dataset],
                    decode_chr_view_hit_row,
                )
                .context("failed to query chr view hit rows")?;
            mapped
                .collect::<std::result::Result<Vec<_>, _>>()
                .context("failed to decode chr view hit rows")?
        }
        (None, None) => {
            let mapped = stmt
                .query_map(
                    params![assembly_ctg_id, project_id, reference_genome_id],
                    decode_chr_view_hit_row,
                )
                .context("failed to query chr view hit rows")?;
            mapped
                .collect::<std::result::Result<Vec<_>, _>>()
                .context("failed to decode chr view hit rows")?
        }
    };

    Ok(rows)
}

fn project_source_interval_to_ctg(
    layout: &ChrViewMemberLayout,
    source_start: i64,
    source_end: i64,
) -> (i64, i64) {
    if layout.orient == "-" {
        (
            layout.ctg_offset + (layout.source_end - source_end + 1),
            layout.ctg_offset + (layout.source_end - source_start + 1),
        )
    } else {
        (
            layout.ctg_offset + (source_start - layout.source_start + 1),
            layout.ctg_offset + (source_end - layout.source_start + 1),
        )
    }
}

#[derive(Debug, Clone, Copy)]
struct ChrViewHitSegment {
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    ref_end: i64,
}

fn load_n_regions_by_source_seq_id(
    conn: &Connection,
    source_seq_ids: &HashSet<i64>,
) -> Result<HashMap<i64, Vec<ChrViewNRegionRow>>> {
    if source_seq_ids.is_empty() {
        return Ok(HashMap::new());
    }

    let mut result = HashMap::<i64, Vec<ChrViewNRegionRow>>::new();
    for source_seq_id in source_seq_ids {
        let mut stmt = conn
            .prepare(
                "SELECT source_seq_id, start_bp, end_bp
                 FROM source_seq_n_region
                 WHERE source_seq_id = ?1
                 ORDER BY start_bp, end_bp",
            )
            .context("failed to prepare source seq n region query")?;
        let rows = stmt
            .query_map(params![source_seq_id], |row| {
                Ok(ChrViewNRegionRow {
                    source_seq_id: row.get(0)?,
                    start_bp: row.get(1)?,
                    end_bp: row.get(2)?,
                })
            })
            .context("failed to query source seq n regions")?
            .collect::<std::result::Result<Vec<_>, _>>()
            .context("failed to decode source seq n regions")?;
        if !rows.is_empty() {
            result.insert(*source_seq_id, rows);
        }
    }
    Ok(result)
}

fn split_hit_around_n_regions(
    row: &ChrViewHitRow,
    clipped_start: i64,
    clipped_end: i64,
    n_regions: &[ChrViewNRegionRow],
) -> Vec<ChrViewHitSegment> {
    let mut segments = Vec::new();
    let mut cursor = clipped_start;
    for region in n_regions {
        if region.end_bp < cursor {
            continue;
        }
        if region.start_bp > clipped_end {
            break;
        }
        if region.start_bp > cursor {
            if let Some(segment) = map_query_segment_to_ref(row, cursor, region.start_bp - 1) {
                segments.push(segment);
            }
        }
        cursor = cursor.max(region.end_bp + 1);
        if cursor > clipped_end {
            break;
        }
    }
    if cursor <= clipped_end
        && let Some(segment) = map_query_segment_to_ref(row, cursor, clipped_end)
    {
        segments.push(segment);
    }
    segments
}

fn map_query_segment_to_ref(
    row: &ChrViewHitRow,
    query_start: i64,
    query_end: i64,
) -> Option<ChrViewHitSegment> {
    let cg_tag = row.cg_tag.as_deref().unwrap_or("").trim();
    if !cg_tag.is_empty()
        && let Ok(Some(block)) = map_paf_query_interval_to_ref_span(
            row.query_start,
            row.query_end,
            row.ref_start,
            row.ref_end,
            &row.strand,
            cg_tag,
            query_start,
            query_end,
        )
    {
        return Some(ChrViewHitSegment {
            query_start: block.query_start_bp,
            query_end: block.query_end_bp,
            ref_start: block.ref_start_bp,
            ref_end: block.ref_end_bp,
        });
    }

    if query_start < 1 || query_end < query_start {
        return None;
    }
    let query_span = row.query_end - row.query_start + 1;
    let ref_span = row.ref_end - row.ref_start + 1;
    if query_span <= 0 || ref_span <= 0 {
        return None;
    }

    let (left_offset, right_offset_exclusive) = if row.strand == "-" {
        (row.query_end - query_end, row.query_end - query_start + 1)
    } else {
        (
            query_start - row.query_start,
            query_end - row.query_start + 1,
        )
    };
    if left_offset < 0 || right_offset_exclusive <= left_offset {
        return None;
    }

    let ref_start = row.ref_start + (left_offset * ref_span) / query_span;
    let ref_end =
        row.ref_start + ((right_offset_exclusive * ref_span + query_span - 1) / query_span) - 1;
    let ref_start = ref_start.max(row.ref_start).min(row.ref_end);
    let ref_end = ref_end.max(ref_start).min(row.ref_end);

    Some(ChrViewHitSegment {
        query_start,
        query_end,
        ref_start,
        ref_end,
    })
}

fn decode_chr_view_hit_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ChrViewHitRow> {
    Ok(ChrViewHitRow {
        assembly_ctg_member_id: row.get(0)?,
        assembly_seq_id: row.get(1)?,
        source_seq_id: row.get(2)?,
        hit_id: row.get(3)?,
        strand: row.get(4)?,
        query_start: row.get(5)?,
        query_end: row.get(6)?,
        ref_start: row.get(7)?,
        ref_end: row.get(8)?,
        match_length: row.get(9)?,
        block_length: row.get(10)?,
        mapq: row.get(11)?,
        cg_tag: row.get(12)?,
    })
}

pub fn list_reference_track_members(
    project_db_path: &Path,
    project_id: i64,
    chr_name: &str,
) -> Result<Vec<ReferenceTrackMemberItem>> {
    let conn = open_workspace_db(project_db_path)?;
    let workspace_root = project_db_path.parent().ok_or_else(|| {
        anyhow!(
            "project db path has no parent: {}",
            project_db_path.display()
        )
    })?;
    list_reference_track_members_with_workspace_root(
        &conn,
        Some(workspace_root),
        project_id,
        chr_name,
    )
}

pub fn list_reference_track_members_with_connection(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
) -> Result<Vec<ReferenceTrackMemberItem>> {
    list_reference_track_members_with_workspace_root(conn, None, project_id, chr_name)
}

fn list_reference_track_members_with_workspace_root(
    conn: &Connection,
    workspace_root: Option<&Path>,
    project_id: i64,
    chr_name: &str,
) -> Result<Vec<ReferenceTrackMemberItem>> {
    let normalized_chr_name = chr_name.trim();
    if normalized_chr_name.is_empty() {
        bail!("chr_name is required");
    }

    let (reference_fasta_path, reference_chr_id, reference_chr_length): (String, i64, i64) = conn
        .query_row(
            "SELECT rg.fasta_path, rc.id, rc.length
             FROM project p
             JOIN reference_genome rg ON rg.id = p.reference_genome_id
             JOIN reference_chr rc ON rc.reference_genome_id = rg.id
             WHERE p.id = ?1
               AND rc.chr_name = ?2",
            params![project_id, normalized_chr_name],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .context("failed to resolve reference chromosome for track members")?
        .ok_or_else(|| {
            anyhow!(
                "chr_name {} does not belong to project {}",
                normalized_chr_name,
                project_id
            )
        })?;

    let (segments, reference_gaps) = resolve_reference_track_segments(
        workspace_root,
        &reference_fasta_path,
        normalized_chr_name,
        reference_chr_length,
    )?;
    let mut items = segments
        .iter()
        .map(|segment| ReferenceTrackMemberItem {
            source_kind: "ref_segment".to_string(),
            reference_chr_id,
            reference_chr_name: normalized_chr_name.to_string(),
            segment_order: segment.segment_order,
            segment_start_bp: segment.start_bp,
            segment_end_bp: segment.end_bp,
            name: format!(
                "ref_{}:{}-{}",
                normalized_chr_name, segment.start_bp, segment.end_bp
            ),
            anchor_start: segment.start_bp,
            total_length: segment.end_bp - segment.start_bp + 1,
            ref_orient: "+".to_string(),
            hits: Vec::new(),
        })
        .collect::<Vec<_>>();

    if items.is_empty() {
        return Ok(items);
    }

    let hit_rows = load_reference_track_hit_rows(conn, project_id, reference_chr_id)?;
    for row in hit_rows {
        let split_blocks = split_reference_hit_row_into_blocks(&row, &reference_gaps)
            .with_context(|| format!("failed to split reference hit {}", row.hit_id))?;
        for block in split_blocks {
            if let Some(segment) = items.iter_mut().find(|item| {
                block.ref_start_bp >= item.segment_start_bp
                    && block.ref_end_bp <= item.segment_end_bp
            }) {
                let segment_start_bp = segment.segment_start_bp;
                let block_length = block.ref_end_bp - block.ref_start_bp + 1;
                let effective_match_length = block_length.min(row.match_length);
                let effective_block_length = block_length.min(row.block_length);
                segment.hits.push(ReferenceTrackHitItem {
                    hit_id: row.hit_id,
                    dataset_id: row.dataset_id,
                    source_seq_id: row.source_seq_id,
                    strand: row.strand.clone(),
                    query_start: block.query_start_bp,
                    query_end: block.query_end_bp,
                    ref_start: block.ref_start_bp,
                    ref_end: block.ref_end_bp,
                    match_length: effective_match_length,
                    block_length: effective_block_length,
                    mapq: row.mapq,
                    ctg_start: block.ref_start_bp - segment_start_bp + 1,
                    ctg_end: block.ref_end_bp - segment_start_bp + 1,
                });
            }
        }
    }

    for item in &mut items {
        item.hits
            .sort_by_key(|hit| (hit.ref_start, hit.ref_end, hit.hit_id));
    }

    Ok(items)
}

fn resolve_reference_track_segments(
    workspace_root: Option<&Path>,
    reference_fasta_path: &str,
    chr_name: &str,
    chr_length: i64,
) -> Result<(Vec<ReferenceSegment>, Vec<ReferenceGapInterval>)> {
    if let Some(root) = workspace_root
        && let Some(segments) = read_reference_segments_metadata(root, chr_name)?
    {
        let gaps = derive_reference_gaps_from_segments(&segments, chr_length);
        return Ok((segments, gaps));
    }

    let needed_names = HashSet::from([chr_name.to_string()]);
    if let Ok(mut reference_sequences) =
        load_named_sequences_from_fasta(Path::new(reference_fasta_path), &needed_names)
        && let Some(reference_sequence) = reference_sequences.remove(chr_name)
    {
        let gaps = detect_reference_gap_intervals(&reference_sequence, 100);
        let segments = detect_reference_segments(chr_name, &reference_sequence, 100);
        return Ok((segments, gaps));
    }

    if chr_length < 1 {
        return Ok((Vec::new(), Vec::new()));
    }

    Ok((
        vec![ReferenceSegment {
            reference_chr_name: chr_name.to_string(),
            segment_order: 1,
            start_bp: 1,
            end_bp: chr_length,
        }],
        Vec::new(),
    ))
}

fn read_reference_segments_metadata(
    workspace_root: &Path,
    chr_name: &str,
) -> Result<Option<Vec<ReferenceSegment>>> {
    let path = workspace_root.join("metadata/reference_segments.tsv");
    if !path.exists() {
        return Ok(None);
    }

    let file = File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut lines = reader.lines();
    let header_line = lines
        .next()
        .transpose()
        .with_context(|| format!("failed to read header from {}", path.display()))?
        .ok_or_else(|| anyhow!("missing header in {}", path.display()))?;
    let header: Vec<&str> = header_line.split('\t').collect();
    let chr_name_col = find_tsv_column(&header, "reference_chr_name", &path)?;
    let order_col = find_tsv_column(&header, "segment_order", &path)?;
    let start_col = find_tsv_column(&header, "segment_start_bp", &path)?;
    let end_col = find_tsv_column(&header, "segment_end_bp", &path)?;

    let mut segments = Vec::new();
    for (line_index, line) in lines.enumerate() {
        let line = line.with_context(|| {
            format!(
                "failed to read line {} from {}",
                line_index + 2,
                path.display()
            )
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let cols: Vec<&str> = line.split('\t').collect();
        if cols.get(chr_name_col).copied().unwrap_or("").trim() != chr_name {
            continue;
        }
        let segment_order = parse_reference_segment_int(
            cols.get(order_col).copied().unwrap_or(""),
            "segment_order",
            &path,
            line_index + 2,
        )?;
        let start_bp = parse_reference_segment_int(
            cols.get(start_col).copied().unwrap_or(""),
            "segment_start_bp",
            &path,
            line_index + 2,
        )?;
        let end_bp = parse_reference_segment_int(
            cols.get(end_col).copied().unwrap_or(""),
            "segment_end_bp",
            &path,
            line_index + 2,
        )?;
        if end_bp < start_bp {
            bail!(
                "{} line {} has segment_end_bp < segment_start_bp",
                path.display(),
                line_index + 2
            );
        }
        segments.push(ReferenceSegment {
            reference_chr_name: chr_name.to_string(),
            segment_order,
            start_bp,
            end_bp,
        });
    }

    segments.sort_by_key(|segment| (segment.segment_order, segment.start_bp, segment.end_bp));
    Ok(Some(segments))
}

fn find_tsv_column(header: &[&str], expected: &str, path: &Path) -> Result<usize> {
    header
        .iter()
        .position(|value| value.trim() == expected)
        .ok_or_else(|| anyhow!("{} missing required column {}", path.display(), expected))
}

fn parse_reference_segment_int(
    value: &str,
    label: &str,
    path: &Path,
    line_number: usize,
) -> Result<i64> {
    value.trim().parse::<i64>().with_context(|| {
        format!(
            "failed to parse {} on line {} from {}",
            label,
            line_number,
            path.display()
        )
    })
}

fn derive_reference_gaps_from_segments(
    segments: &[ReferenceSegment],
    chr_length: i64,
) -> Vec<ReferenceGapInterval> {
    let mut gaps = Vec::new();
    let mut next_start = 1_i64;
    for segment in segments {
        if segment.start_bp > next_start {
            gaps.push(ReferenceGapInterval {
                start_bp: next_start,
                end_bp: segment.start_bp - 1,
            });
        }
        next_start = segment.end_bp + 1;
    }
    if next_start <= chr_length {
        gaps.push(ReferenceGapInterval {
            start_bp: next_start,
            end_bp: chr_length,
        });
    }
    gaps
}

fn load_reference_track_hit_rows(
    conn: &Connection,
    project_id: i64,
    reference_chr_id: i64,
) -> Result<Vec<ReferenceTrackHitRow>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                h.id,
                h.dataset_id,
                h.source_seq_id,
                h.strand,
                h.query_start,
                h.query_end,
                h.ref_start,
                h.ref_end,
                h.match_length,
                h.block_length,
                h.mapq,
                h.cg_tag
             FROM ref_alignment_hit h
             JOIN project_dataset pd ON pd.dataset_id = h.dataset_id
             WHERE pd.project_id = ?1
               AND h.reference_chr_id = ?2
             ORDER BY h.id",
        )
        .context("failed to prepare reference track hit query")?;
    stmt.query_map(params![project_id, reference_chr_id], |row| {
        Ok(ReferenceTrackHitRow {
            hit_id: row.get(0)?,
            dataset_id: row.get(1)?,
            source_seq_id: row.get(2)?,
            strand: row.get(3)?,
            query_start: row.get(4)?,
            query_end: row.get(5)?,
            ref_start: row.get(6)?,
            ref_end: row.get(7)?,
            match_length: row.get(8)?,
            block_length: row.get(9)?,
            mapq: row.get(10)?,
            cg_tag: row.get(11)?,
        })
    })
    .context("failed to query reference track hit rows")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode reference track hit rows")
}

fn split_reference_hit_row_into_blocks(
    row: &ReferenceTrackHitRow,
    reference_gaps: &[ReferenceGapInterval],
) -> Result<Vec<SplitReferenceBlock>> {
    let cg_tag = row.cg_tag.as_deref().unwrap_or("").trim();
    if cg_tag.is_empty() {
        return Ok(vec![SplitReferenceBlock {
            query_start_bp: row.query_start,
            query_end_bp: row.query_end,
            ref_start_bp: row.ref_start,
            ref_end_bp: row.ref_end,
        }]);
    }

    split_paf_hit_by_reference_gaps(
        row.query_start,
        row.query_end,
        row.ref_start,
        row.ref_end,
        &row.strand,
        cg_tag,
        reference_gaps,
    )
}

pub fn get_ctg_detail(
    project_db_path: &Path,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<CtgDetail> {
    let conn = open_workspace_db(project_db_path)?;
    get_ctg_detail_with_connection(&conn, project_id, assembly_ctg_id)
}

pub fn get_ctg_detail_with_connection(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<CtgDetail> {
    let head = conn
        .query_row(
            "SELECT
                id, project_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode
             FROM assembly_ctg
             WHERE id = ?1",
            params![assembly_ctg_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?,
                    row.get::<_, Option<i64>>(4)?,
                    row.get::<_, Option<i64>>(5)?,
                    row.get::<_, Option<String>>(6)?,
                    row.get::<_, String>(7)?,
                ))
            },
        )
        .optional()
        .context("failed to query assembly_ctg header")?;
    let Some(head) = head else {
        bail!("assembly_ctg_id {} does not exist", assembly_ctg_id);
    };
    if head.1 != project_id {
        bail!(
            "assembly_ctg_id {} does not belong to project_id {}",
            assembly_ctg_id,
            project_id
        );
    }

    let mut member_stmt = conn
        .prepare(
            "SELECT
                c.id,
                s.id,
                d.name,
                ss.seq_name,
                ss.length,
                s.orient,
                s.source_start,
                s.source_end,
                s.left_end_type,
                s.right_end_type,
                s.hidden,
                1 AS member_order
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE c.id = ?1
             ORDER BY c.id",
        )
        .context("failed to prepare assembly_ctg member detail query")?;
    let members = member_stmt
        .query_map(params![assembly_ctg_id], |row| {
            Ok(CtgDetailMember {
                assembly_ctg_member_id: row.get(0)?,
                assembly_seq_id: row.get(1)?,
                dataset_name: row.get(2)?,
                seq_name: row.get(3)?,
                seq_length: row.get(4)?,
                orient: row.get(5)?,
                source_start: row.get(6)?,
                source_end: row.get(7)?,
                left_end_type: row.get(8)?,
                right_end_type: row.get(9)?,
                hidden: row.get::<_, i64>(10)? > 0,
                member_order: row.get(11)?,
            })
        })
        .context("failed to query assembly_ctg detail members")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode assembly_ctg detail members")?;

    Ok(CtgDetail {
        assembly_ctg_id: head.0,
        project_id: head.1,
        name: head.2,
        assigned_chr_name: head.3,
        chr_order: head.4,
        anchor_start: head.5,
        ref_orient: head.6,
        placement_mode: head.7,
        members,
    })
}

pub fn list_ctg_edit_candidates(
    project_db_path: &Path,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<CtgEditCandidates> {
    let conn = open_workspace_db(project_db_path)?;
    list_ctg_edit_candidates_with_connection(&conn, project_id, assembly_ctg_id)
}

pub fn list_ctg_edit_candidates_with_connection(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<CtgEditCandidates> {
    let exists: Option<i64> = conn
        .query_row(
            "SELECT id FROM assembly_ctg WHERE id = ?1 AND project_id = ?2",
            params![assembly_ctg_id, project_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to check assembly_ctg existence for edit candidates")?;
    if exists.is_none() {
        bail!(
            "assembly_ctg_id {} does not belong to project_id {}",
            assembly_ctg_id,
            project_id
        );
    }

    let mut move_stmt = conn
        .prepare(
            "SELECT id, name, assigned_chr_name, chr_order
             FROM assembly_ctg
             WHERE project_id = ?1 AND id != ?2
             ORDER BY
                CASE WHEN assigned_chr_name IS NULL OR assigned_chr_name = '' THEN 1 ELSE 0 END,
                assigned_chr_name, chr_order, id",
        )
        .context("failed to prepare move target ctg query")?;
    let move_target_ctgs = move_stmt
        .query_map(params![project_id, assembly_ctg_id], |row| {
            Ok(MoveTargetCtg {
                assembly_ctg_id: row.get(0)?,
                name: row.get(1)?,
                assigned_chr_name: row.get(2)?,
                chr_order: row.get(3)?,
            })
        })
        .context("failed to query move target ctgs")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode move target ctgs")?;

    let mut seq_stmt = conn
        .prepare(
            "SELECT
                s.id,
                d.name,
                ss.seq_name,
                ss.length,
                s.hidden
             FROM assembly_seq s
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE s.project_id = ?1
               AND 0 = ?2
             ORDER BY d.name, ss.seq_name, s.id",
        )
        .context("failed to prepare add seq candidate query")?;
    let add_seq_candidates = seq_stmt
        .query_map(params![project_id, assembly_ctg_id], |row| {
            Ok(AddSeqCandidate {
                assembly_seq_id: row.get(0)?,
                dataset_name: row.get(1)?,
                seq_name: row.get(2)?,
                seq_length: row.get(3)?,
                hidden: row.get::<_, i64>(4)? > 0,
            })
        })
        .context("failed to query add seq candidates")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode add seq candidates")?;

    Ok(CtgEditCandidates {
        project_id,
        assembly_ctg_id,
        move_target_ctgs,
        add_seq_candidates,
    })
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;
    use crate::db::init_workspace_schema;

    #[test]
    fn queries_chr_and_ctg_views() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);

        let chromosomes = list_project_chromosomes_with_connection(&conn, 1).unwrap();
        assert_eq!(chromosomes.items.len(), 2);
        assert_eq!(chromosomes.items[0].chr_name, "chr1");
        assert_eq!(chromosomes.items[0].ctg_count, 1);
        assert_eq!(chromosomes.unplaced_ctg_count, 1);

        let chr1_ctgs = list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), None).unwrap();
        assert_eq!(chr1_ctgs.len(), 1);
        assert_eq!(chr1_ctgs[0].name, "ctg_A");
        assert_eq!(chr1_ctgs[0].origin_id.as_deref(), Some("seq_1"));
        assert_eq!(chr1_ctgs[0].dataset_id, Some(1));
        assert_eq!(chr1_ctgs[0].dataset_name.as_deref(), Some("ds_a"));
        assert_eq!(chr1_ctgs[0].hits.len(), 1);
        assert_eq!(chr1_ctgs[0].hits[0].hit_id, 1);
        assert_eq!(chr1_ctgs[0].hits[0].assembly_ctg_member_id, 1);
        assert_eq!(chr1_ctgs[0].hits[0].assembly_seq_id, 1);
        assert_eq!(chr1_ctgs[0].hits[0].source_seq_id, 1);
        assert_eq!(chr1_ctgs[0].hits[0].query_start, 10);
        assert_eq!(chr1_ctgs[0].hits[0].query_end, 40);
        assert_eq!(chr1_ctgs[0].hits[0].ctg_start, 10);
        assert_eq!(chr1_ctgs[0].hits[0].ctg_end, 40);

        let all_ctgs = list_chr_view_ctgs_with_connection(&conn, 1, None, None).unwrap();
        assert_eq!(all_ctgs.len(), 2);
        let ctg_a = all_ctgs.iter().find(|item| item.name == "ctg_A").unwrap();
        assert_eq!(ctg_a.total_length, 100);
        assert_eq!(ctg_a.origin_id.as_deref(), Some("seq_1"));
        assert_eq!(ctg_a.dataset_id, Some(1));
        assert_eq!(ctg_a.dataset_name.as_deref(), Some("ds_a"));
        assert_eq!(ctg_a.hits.len(), 2);
        assert_eq!(ctg_a.hits[1].hit_id, 2);
        assert_eq!(ctg_a.hits[1].query_start, 80);
        assert_eq!(ctg_a.hits[1].query_end, 100);
        assert_eq!(ctg_a.hits[1].ctg_start, 80);
        assert_eq!(ctg_a.hits[1].ctg_end, 100);
        assert!(ctg_a.hits.iter().all(|hit| hit.assembly_seq_id == 1));
        let ctg_b = all_ctgs.iter().find(|item| item.name == "ctg_B").unwrap();
        assert_eq!(ctg_b.total_length, 200);
        assert_eq!(ctg_b.origin_id.as_deref(), Some("seq_2"));
        assert_eq!(ctg_b.dataset_id, Some(1));
        assert_eq!(ctg_b.dataset_name.as_deref(), Some("ds_a"));
        assert_eq!(ctg_b.hits.len(), 1);
        assert_eq!(ctg_b.hits[0].source_seq_id, 2);

        let ds1_ctgs = list_chr_view_ctgs_with_connection(&conn, 1, None, Some(1)).unwrap();
        assert_eq!(ds1_ctgs.len(), 2);
        let ds1_ctg_b = ds1_ctgs.iter().find(|item| item.name == "ctg_B").unwrap();
        assert_eq!(ds1_ctg_b.total_length, 200);
        assert_eq!(ds1_ctg_b.hits.len(), 1);
        assert_eq!(ds1_ctg_b.hits[0].source_seq_id, 2);

        let ds2_ctgs = list_chr_view_ctgs_with_connection(&conn, 1, None, Some(2)).unwrap();
        assert!(ds2_ctgs.is_empty());
    }

    #[test]
    fn chr_view_marks_ctgs_assigned_to_multiple_chr_groups() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);

        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, instance_key, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (8, 1, 1, 'chr:chr2', '+', 1, 100, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (8, 1, 8, 'ctg_A_chr2', 'chr2', 1, 500, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();

        let chr1_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), Some(1)).unwrap();
        let ctg_a = chr1_ctgs.iter().find(|item| item.name == "ctg_A").unwrap();
        assert_eq!(ctg_a.origin_source_seq_id, Some(1));
        assert_eq!(ctg_a.co_assigned_chr_names, vec!["chr2"]);

        let chr2_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr2"), Some(1)).unwrap();
        let ctg_a_chr2 = chr2_ctgs
            .iter()
            .find(|item| item.name == "ctg_A_chr2")
            .unwrap();
        assert_eq!(ctg_a_chr2.origin_source_seq_id, Some(1));
        assert_eq!(ctg_a_chr2.co_assigned_chr_names, vec!["chr1"]);

        let all_ctgs = list_chr_view_ctgs_with_connection(&conn, 1, None, Some(1)).unwrap();
        let ctg_b = all_ctgs.iter().find(|item| item.name == "ctg_B").unwrap();
        assert!(ctg_b.co_assigned_chr_names.is_empty());
    }

    #[test]
    fn project_chromosome_summary_only_counts_primary_dataset_ctgs() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);

        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (6, 2, 'seq_6', 3, 400), (7, 2, 'seq_7', 4, 500)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES
                (6, 1, 6, '+', 1, 400, 'normal', 'normal', 0, '1', NULL),
                (7, 1, 7, '+', 1, 500, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES
                (3, 1, 6, 'ctg_support_chr2', 'chr2', 1, 120, '+', 'auto', '1', NULL),
                (4, 1, 7, 'ctg_support_unplaced', NULL, NULL, NULL, NULL, 'none', '1', NULL)",
            [],
        )
        .unwrap();

        let chromosomes = list_project_chromosomes_with_connection(&conn, 1).unwrap();

        let chr2 = chromosomes
            .items
            .iter()
            .find(|item| item.chr_name == "chr2")
            .expect("chr2 exists");
        assert_eq!(chr2.ctg_count, 0);
        assert_eq!(chr2.placed_bp, 0);
        assert_eq!(chromosomes.unplaced_ctg_count, 1);
        assert_eq!(chromosomes.unplaced_bp, 200);
    }

    #[test]
    fn chr_view_total_length_and_chr_summary_use_visible_member_ranges() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);

        conn.execute(
            "UPDATE assembly_seq
             SET source_start = 51, source_end = 120
             WHERE id = 2",
            [],
        )
        .unwrap();
        conn.execute(
            "UPDATE assembly_seq
             SET source_start = 30, source_end = 180
             WHERE id = 3",
            [],
        )
        .unwrap();

        let ctgs = list_chr_view_ctgs_with_connection(&conn, 1, None, None).unwrap();
        let ctg_b = ctgs
            .iter()
            .find(|item| item.name == "ctg_B")
            .expect("ctg_B exists");
        assert_eq!(ctg_b.total_length, 70);

        let chromosomes = list_project_chromosomes_with_connection(&conn, 1).unwrap();
        assert_eq!(chromosomes.unplaced_bp, 70);
    }

    #[test]
    fn queries_ctg_detail_and_edit_candidates() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);

        let detail = get_ctg_detail_with_connection(&conn, 1, 1).unwrap();
        assert_eq!(detail.name, "ctg_A");
        assert_eq!(detail.members.len(), 1);
        assert_eq!(detail.members[0].seq_name, "seq_1");

        let candidates = list_ctg_edit_candidates_with_connection(&conn, 1, 1).unwrap();
        assert_eq!(candidates.move_target_ctgs.len(), 1);
        assert_eq!(candidates.add_seq_candidates.len(), 0);
    }

    #[test]
    fn lists_project_new_sequences_excluding_linked_members() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (4, 2, 'seq_0', 2, 150)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES
                (4, 1, 4, '+', 1, 150, 'normal', 'normal', 1, '1', NULL)",
            [],
        )
        .unwrap();

        let items = list_project_new_sequences_with_connection(&conn, 1).unwrap();

        assert_eq!(
            items,
            vec![
                ProjectNewSequenceItem {
                    assembly_seq_id: 4,
                    dataset_name: "ds_b".to_string(),
                    seq_name: "seq_0".to_string(),
                    seq_length: 150,
                    hidden: true,
                },
                ProjectNewSequenceItem {
                    assembly_seq_id: 3,
                    dataset_name: "ds_b".to_string(),
                    seq_name: "seq_3".to_string(),
                    seq_length: 300,
                    hidden: false,
                },
                ProjectNewSequenceItem {
                    assembly_seq_id: 5,
                    dataset_name: "ds_b".to_string(),
                    seq_name: "seq_5".to_string(),
                    seq_length: 150,
                    hidden: true,
                },
            ]
        );
    }

    #[test]
    fn dataset_filtered_chr_view_keeps_support_source_but_hides_mixed_target() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'unknown', 'ref', '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'chr1', 1, 1000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES
                (1, 'ds_primary', 'a', NULL, '/tmp/a.fa', '/tmp/a.fa.fai'),
                (2, 'ds_support', 'b', NULL, '/tmp/b.fa', '/tmp/b.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES
                (1, 1, 'seq_primary', 1, 100),
                (2, 2, 'seq_support', 1, 300)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (1, 'p1', 1, 1, 1, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES
                (1, 1, 1, '+', 1, 100, 'normal', 'normal', 0, '1', NULL),
                (2, 1, 2, '+', 1, 300, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES
                (1, 1, 1, 'ctg_target', 'chr1', 1, 100, '+', 'auto', '1', NULL),
                (2, 1, 2, 'ctg_source', 'chr1', 2, 500, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note
            ) VALUES
                (1, 1, 1, 1, '+', 10, 20, 100, 110, 11, 11, 60, 'run1', NULL),
                (2, 2, 2, 1, '+', 20, 40, 200, 220, 21, 21, 55, 'run2', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO telomere_rule (rule_id, motif, min_repeat, reverse_complement)
             VALUES ('tel1', 'TTAGGG', 20, 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq_telomere_mark (
                source_seq_id, rule_id, assigned_chr_name, motif, min_repeat,
                repeat_count, start_bp, end_bp, strand
            ) VALUES
                (1, 'tel1', 'chr1', 'TTAGGG', 20, 21, 5, 80, '+'),
                (2, 'tel1', 'chr1', 'TTAGGG', 20, 22, 10, 90, '+')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq_centromere_mark (
                source_seq_id, cen_id, assigned_chr_name, query_name,
                start_bp, end_bp, strand, align_length, identity, mapq
            ) VALUES
                (1, 'cen', 'chr1', 'chr1_centromere', 15, 70, '+', 56, 96.5, 60),
                (2, 'cen', 'chr1', 'chr1_centromere', 20, 90, '+', 71, 95.0, 60)",
            [],
        )
        .unwrap();

        let primary_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), Some(1)).unwrap();
        assert_eq!(primary_ctgs.len(), 1);
        assert_eq!(primary_ctgs[0].name, "ctg_target");
        assert_eq!(primary_ctgs[0].total_length, 100);
        assert_eq!(primary_ctgs[0].hits.len(), 1);
        let primary_hit_source_ids = primary_ctgs[0]
            .hits
            .iter()
            .map(|hit| hit.source_seq_id)
            .collect::<Vec<_>>();
        assert_eq!(primary_hit_source_ids, vec![1]);
        assert_eq!(primary_ctgs[0].telomere_marks.len(), 1);
        assert_eq!(primary_ctgs[0].telomere_marks[0].rule_id, "tel1");
        assert_eq!(primary_ctgs[0].telomere_marks[0].ctg_start, 5);
        assert_eq!(primary_ctgs[0].telomere_marks[0].ctg_end, 80);
        assert_eq!(primary_ctgs[0].centromere_marks.len(), 1);
        assert_eq!(primary_ctgs[0].centromere_marks[0].cen_id, "cen");
        assert_eq!(
            primary_ctgs[0].centromere_marks[0].query_name,
            "chr1_centromere"
        );
        assert_eq!(primary_ctgs[0].centromere_marks[0].ctg_start, 15);
        assert_eq!(primary_ctgs[0].centromere_marks[0].ctg_end, 70);
        assert_eq!(primary_ctgs[0].centromere_marks[0].identity, 96.5);

        let support_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), Some(2)).unwrap();
        assert_eq!(support_ctgs.len(), 1);
        assert_eq!(support_ctgs[0].name, "ctg_source");
        assert_eq!(support_ctgs[0].total_length, 300);
        assert_eq!(support_ctgs[0].hits.len(), 1);
        assert_eq!(support_ctgs[0].hits[0].source_seq_id, 2);
        assert!(support_ctgs[0].telomere_marks.is_empty());
        assert!(support_ctgs[0].centromere_marks.is_empty());
    }

    #[test]
    fn chr_view_maps_n_regions_and_splits_hit_bands_around_them() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);
        conn.execute(
            "INSERT INTO source_seq_n_region (source_seq_id, start_bp, end_bp, length_bp)
             VALUES (1, 25, 30, 6)",
            [],
        )
        .unwrap();

        let chr1_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), Some(1)).unwrap();
        let ctg_a = chr1_ctgs.iter().find(|item| item.name == "ctg_A").unwrap();

        assert_eq!(ctg_a.n_regions.len(), 1);
        assert_eq!(ctg_a.n_regions[0].ctg_start, 25);
        assert_eq!(ctg_a.n_regions[0].ctg_end, 30);
        assert_eq!(ctg_a.n_regions[0].length_bp, 6);
        assert_eq!(ctg_a.hits.len(), 2);
        assert_eq!(
            (ctg_a.hits[0].query_start, ctg_a.hits[0].query_end),
            (10, 24)
        );
        assert_eq!((ctg_a.hits[0].ref_start, ctg_a.hits[0].ref_end), (100, 114));
        assert_eq!(
            (ctg_a.hits[1].query_start, ctg_a.hits[1].query_end),
            (31, 40)
        );
        assert_eq!((ctg_a.hits[1].ref_start, ctg_a.hits[1].ref_end), (121, 130));
    }

    #[test]
    fn chr_view_uses_cg_tag_to_map_n_split_hit_ref_coordinates() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_basic_data(&conn);
        conn.execute(
            "INSERT INTO source_seq_n_region (source_seq_id, start_bp, end_bp, length_bp)
             VALUES (1, 25, 30, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "UPDATE ref_alignment_hit
             SET ref_end = 129,
                 block_length = 30,
                 cg_tag = '10M3I5M2D13M'
             WHERE id = 1",
            [],
        )
        .unwrap();

        let chr1_ctgs =
            list_chr_view_ctgs_with_connection(&conn, 1, Some("chr1"), Some(1)).unwrap();
        let ctg_a = chr1_ctgs.iter().find(|item| item.name == "ctg_A").unwrap();

        assert_eq!(ctg_a.hits.len(), 2);
        assert_eq!(
            (ctg_a.hits[0].query_start, ctg_a.hits[0].query_end),
            (10, 24)
        );
        assert_eq!((ctg_a.hits[0].ref_start, ctg_a.hits[0].ref_end), (100, 111));
        assert_eq!(
            (ctg_a.hits[1].query_start, ctg_a.hits[1].query_end),
            (31, 40)
        );
        assert_eq!((ctg_a.hits[1].ref_start, ctg_a.hits[1].ref_end), (120, 129));
    }

    #[test]
    fn list_reference_track_members_splits_gap_reference_and_maps_split_hits() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let reference_fasta = temp.path().join("ref.fa");
        std::fs::write(
            &reference_fasta,
            format!(
                ">Chr01\n{}{}{}\n",
                "A".repeat(5000),
                "N".repeat(100),
                "C".repeat(5000)
            ),
        )
        .unwrap();
        std::fs::write(temp.path().join("ref.fa.fai"), "").unwrap();

        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (?1, 'ref', 'unknown', 'ref', ?2, ?3)",
            params![
                1_i64,
                reference_fasta.to_string_lossy().to_string(),
                temp.path().join("ref.fa.fai").to_string_lossy().to_string()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 10100)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'ds1', 'asm', NULL, '/tmp/ds1.fa', '/tmp/ds1.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (7, 'projA', 1, 1, 11, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig1', 1, 10000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note, cg_tag
            ) VALUES (
                1, 11, 101, 1, '+',
                1, 10000, 1, 10100,
                10000, 10100, 60, 'ds1_vs_ref', NULL, '5000M100D5000M'
            )",
            [],
        )
        .unwrap();

        let items = list_reference_track_members_with_connection(&conn, 7, "Chr01").unwrap();
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].source_kind, "ref_segment");
        assert_eq!(items[0].name, "ref_Chr01:1-5000");
        assert_eq!(
            (items[0].segment_start_bp, items[0].segment_end_bp),
            (1, 5000)
        );
        assert_eq!(
            (items[1].segment_start_bp, items[1].segment_end_bp),
            (5101, 10100)
        );
        assert_eq!(items[0].hits.len(), 1);
        assert_eq!(items[1].hits.len(), 1);
        assert_eq!(
            (
                items[0].hits[0].ctg_start,
                items[0].hits[0].ctg_end,
                items[0].hits[0].ref_start,
                items[0].hits[0].ref_end
            ),
            (1, 5000, 1, 5000)
        );
        assert_eq!(
            (
                items[1].hits[0].ctg_start,
                items[1].hits[0].ctg_end,
                items[1].hits[0].ref_start,
                items[1].hits[0].ref_end
            ),
            (1, 5000, 5101, 10100)
        );
    }

    #[test]
    fn list_reference_track_members_keeps_single_member_reference_without_cg_tag() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let reference_fasta = temp.path().join("ref.fa");
        std::fs::write(&reference_fasta, ">Chr01\nACGTACGTACGT\n").unwrap();
        std::fs::write(temp.path().join("ref.fa.fai"), "").unwrap();

        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (?1, 'ref', 'unknown', 'ref', ?2, ?3)",
            params![
                1_i64,
                reference_fasta.to_string_lossy().to_string(),
                temp.path().join("ref.fa.fai").to_string_lossy().to_string()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 12)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'ds1', 'asm', NULL, '/tmp/ds1.fa', '/tmp/ds1.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (7, 'projA', 1, 1, 11, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig1', 1, 12)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note
            ) VALUES (
                1, 11, 101, 1, '+',
                2, 9, 3, 10,
                8, 8, 60, 'ds1_vs_ref', NULL
            )",
            [],
        )
        .unwrap();

        let items = list_reference_track_members_with_connection(&conn, 7, "Chr01").unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].name, "ref_Chr01:1-12");
        assert_eq!(items[0].hits.len(), 1);
        assert_eq!(
            (
                items[0].hits[0].query_start,
                items[0].hits[0].query_end,
                items[0].hits[0].ctg_start,
                items[0].hits[0].ctg_end
            ),
            (2, 9, 3, 10)
        );
    }

    #[test]
    fn list_reference_track_members_reads_segment_metadata_without_reference_fasta() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path();
        std::fs::create_dir_all(workspace_root.join("metadata")).unwrap();
        std::fs::write(
            workspace_root.join("metadata/reference_segments.tsv"),
            concat!(
                "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n",
                "Chr01\t1\t1\t5000\n",
                "Chr01\t2\t5101\t10100\n",
            ),
        )
        .unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (?1, 'ref', 'unknown', 'ref', ?2, ?3)",
            params![
                1_i64,
                workspace_root.join("data/reference/ref.fa").to_string_lossy().to_string(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
                    .to_string()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 10100)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'ds1', 'asm', NULL, '/tmp/ds1.fa', '/tmp/ds1.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (7, 'projA', 1, 1, 11, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig1', 1, 10000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note, cg_tag
            ) VALUES (
                1, 11, 101, 1, '+',
                1, 10000, 1, 10100,
                10000, 10100, 60, 'ds1_vs_ref', NULL, '5000M100D5000M'
            )",
            [],
        )
        .unwrap();

        let items = list_reference_track_members(&db_path, 7, "Chr01").unwrap();
        assert_eq!(items.len(), 2);
        assert_eq!(
            (items[0].segment_start_bp, items[0].segment_end_bp),
            (1, 5000)
        );
        assert_eq!(
            (items[1].segment_start_bp, items[1].segment_end_bp),
            (5101, 10100)
        );
        assert_eq!(items[0].hits.len(), 1);
        assert_eq!(items[1].hits.len(), 1);
    }

    #[test]
    fn list_reference_track_members_falls_back_to_single_member_without_metadata_or_fasta() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'unknown', 'ref', '/missing/ref.fa', '/missing/ref.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 10100)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'ds1', 'asm', NULL, '/tmp/ds1.fa', '/tmp/ds1.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (7, 'projA', 1, 1, 11, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig1', 1, 8)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note
            ) VALUES (
                1, 11, 101, 1, '+',
                2, 9, 3, 10,
                8, 8, 60, 'ds1_vs_ref', NULL
            )",
            [],
        )
        .unwrap();

        let items = list_reference_track_members(&db_path, 7, "Chr01").unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].name, "ref_Chr01:1-10100");
        assert_eq!(items[0].hits.len(), 1);
        assert_eq!(
            (
                items[0].hits[0].query_start,
                items[0].hits[0].query_end,
                items[0].hits[0].ctg_start,
                items[0].hits[0].ctg_end
            ),
            (2, 9, 3, 10)
        );
    }

    fn seed_basic_data(conn: &Connection) {
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'unknown', 'ref', '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 'chr1', 1, 1000), (1, 'chr2', 2, 2000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds_a', 'a', NULL, '/tmp/a.fa', '/tmp/a.fa.fai'),
                    (2, 'ds_b', 'b', NULL, '/tmp/b.fa', '/tmp/b.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (1, 1, 'seq_1', 1, 100),
                    (2, 1, 'seq_2', 2, 200),
                    (3, 2, 'seq_3', 1, 300),
                    (5, 2, 'seq_5', 2, 150)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (1, 'p1', 1, 1, 1, 0, NULL, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES
                (1, 1, 1, '+', 1, 100, 'normal', 'normal', 0, '1', NULL),
                (2, 1, 2, '+', 1, 200, 'normal', 'normal', 0, '1', NULL),
                (3, 1, 3, '-', 1, 300, 'normal', 'normal', 0, '1', NULL),
                (5, 1, 5, '+', 1, 150, 'normal', 'normal', 1, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES
                (1, 1, 1, 'ctg_A', 'chr1', 1, 100, '+', 'auto', '1', NULL),
                (2, 1, 2, 'ctg_B', NULL, NULL, NULL, NULL, 'none', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ref_alignment_hit (
                id, dataset_id, source_seq_id, reference_chr_id, strand,
                query_start, query_end, ref_start, ref_end,
                match_length, block_length, mapq, run_name, note
            ) VALUES
                (1, 1, 1, 1, '+', 10, 40, 100, 130, 30, 30, 60, 'run1', NULL),
                (2, 1, 1, 2, '+', 80, 120, 200, 240, 41, 21, 50, 'run2', NULL),
                (3, 1, 2, 1, '-', 30, 60, 500, 530, 31, 31, 55, 'run3', NULL),
                (4, 2, 3, 1, '+', 20, 40, 700, 720, 21, 21, 40, 'run4', NULL),
                (5, 2, 3, 2, '-', 250, 310, 900, 960, 61, 61, 42, 'run5', NULL),
                (6, 2, 5, 1, '+', 1, 50, 1000, 1049, 50, 50, 10, 'run6', NULL)",
            [],
        )
        .unwrap();
    }
}
