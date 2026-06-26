use std::collections::{BTreeSet, HashMap};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params, params_from_iter, types::Value};

use crate::db::open_workspace_db;

const DERIVED_CTG_DATASET_NAME: &str = "derived_ctg";

#[derive(Debug, Clone, PartialEq)]
pub struct GetJunctionInspectionParams {
    pub project_id: i64,
    pub left_assembly_ctg_id: i64,
    pub right_assembly_ctg_id: i64,
    pub min_align_length: Option<i64>,
    pub min_mapq: Option<i64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct GetTrackPairwiseEvidenceParams {
    pub project_id: i64,
    pub top_assembly_ctg_ids: Vec<i64>,
    pub bottom_assembly_ctg_ids: Vec<i64>,
    pub min_align_length: Option<i64>,
    pub min_mapq: Option<i64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct JunctionInspectionReport {
    pub project_id: i64,
    pub assigned_chr_name: String,
    pub left: JunctionCtgContext,
    pub right: JunctionCtgContext,
    pub placement_relation: String,
    pub overlap_bp: Option<i64>,
    pub gap_bp: Option<i64>,
    pub same_dataset: bool,
    pub evidence_source: String,
    pub evidence_hit_count: i64,
    pub hits: Vec<JunctionEvidenceHit>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TrackPairwiseEvidenceReport {
    pub project_id: i64,
    pub assigned_chr_name: String,
    pub same_dataset: bool,
    pub evidence_source: String,
    pub evidence_hit_count: i64,
    pub top_assembly_ctg_ids: Vec<i64>,
    pub bottom_assembly_ctg_ids: Vec<i64>,
    pub hits: Vec<JunctionEvidenceHit>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct JunctionCtgContext {
    pub assembly_ctg_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub anchor_start: Option<i64>,
    pub anchor_end: Option<i64>,
    pub span_length: i64,
    pub placement_mode: String,
    pub member_count: i64,
    pub visible_member_count: i64,
    pub dataset_ids: Vec<i64>,
    pub dataset_names: Vec<String>,
    pub members: Vec<JunctionCtgMember>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct JunctionCtgMember {
    pub assembly_ctg_member_id: i64,
    pub assembly_seq_id: i64,
    pub member_order: i64,
    pub source_seq_id: i64,
    pub source_seq_name: String,
    pub source_seq_length: i64,
    pub dataset_id: i64,
    pub dataset_name: String,
    pub orient: String,
    pub source_start: i64,
    pub source_end: i64,
    pub used_length: i64,
    pub hidden: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct JunctionEvidenceHit {
    pub query_assembly_ctg_id: i64,
    pub query_source_seq_id: i64,
    pub query_source_seq_name: String,
    pub subject_assembly_ctg_id: i64,
    pub subject_source_seq_id: i64,
    pub subject_source_seq_name: String,
    pub strand: String,
    pub query_start: i64,
    pub query_end: i64,
    pub subject_start: i64,
    pub subject_end: i64,
    pub mapq: i64,
    pub identity_pct: f64,
    pub align_length: i64,
    pub mismatch_count: Option<i64>,
    pub gap_open_count: Option<i64>,
    pub evalue: Option<f64>,
    pub bit_score: Option<f64>,
    pub evidence_origin: String,
}

pub fn get_junction_inspection(
    project_db_path: &Path,
    params: &GetJunctionInspectionParams,
) -> Result<JunctionInspectionReport> {
    let mut conn = open_workspace_db(project_db_path)?;
    get_junction_inspection_with_connection(&mut conn, project_db_path, params)
}

pub fn get_track_pairwise_evidence(
    project_db_path: &Path,
    params: &GetTrackPairwiseEvidenceParams,
) -> Result<TrackPairwiseEvidenceReport> {
    let mut conn = open_workspace_db(project_db_path)?;
    get_track_pairwise_evidence_with_connection(&mut conn, project_db_path, params)
}

fn get_junction_inspection_with_connection(
    conn: &mut Connection,
    _project_db_path: &Path,
    params: &GetJunctionInspectionParams,
) -> Result<JunctionInspectionReport> {
    if params.left_assembly_ctg_id == params.right_assembly_ctg_id {
        bail!("junction inspection requires two different assembly_ctg ids");
    }

    let left_raw = load_ctg_context(conn, params.project_id, params.left_assembly_ctg_id)?;
    let right_raw = load_ctg_context(conn, params.project_id, params.right_assembly_ctg_id)?;
    let (left, right) = normalize_left_right(left_raw, right_raw);

    let left_chr = left
        .assigned_chr_name
        .clone()
        .ok_or_else(|| anyhow::anyhow!("left ctg is not assigned to chromosome"))?;
    let right_chr = right
        .assigned_chr_name
        .clone()
        .ok_or_else(|| anyhow::anyhow!("right ctg is not assigned to chromosome"))?;
    if left_chr != right_chr {
        bail!(
            "left/right ctg are on different chromosomes: {} vs {}",
            left_chr,
            right_chr
        );
    }

    let (placement_relation, overlap_bp, gap_bp) = placement_relation(
        left.anchor_start,
        left.anchor_end,
        right.anchor_start,
        right.anchor_end,
    );

    let left_visible = left
        .members
        .iter()
        .filter(|member| !member.hidden)
        .cloned()
        .collect::<Vec<_>>();
    let right_visible = right
        .members
        .iter()
        .filter(|member| !member.hidden)
        .cloned()
        .collect::<Vec<_>>();
    if left_visible.is_empty() || right_visible.is_empty() {
        bail!("junction inspection requires both contigs to have visible members");
    }
    let left_dataset_ids = left_visible
        .iter()
        .map(|member| member.dataset_id)
        .collect::<BTreeSet<_>>();
    let right_dataset_ids = right_visible
        .iter()
        .map(|member| member.dataset_id)
        .collect::<BTreeSet<_>>();
    let same_dataset = left_dataset_ids.len() == 1
        && right_dataset_ids.len() == 1
        && left_dataset_ids == right_dataset_ids;
    let min_align_length = params.min_align_length.unwrap_or(0).max(0);
    let min_mapq = params.min_mapq.unwrap_or(0).max(0);

    let (evidence_source, hits) = if same_dataset {
        let dataset_id = *left_dataset_ids
            .iter()
            .next()
            .ok_or_else(|| anyhow::anyhow!("failed to infer dataset for same-dataset pair"))?;
        let (dataset_name, dataset_fasta_path) = conn
            .query_row(
                "SELECT name, fasta_path FROM dataset WHERE id = ?1",
                params![dataset_id],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            )
            .with_context(|| format!("dataset_id {} does not exist", dataset_id))?;

        let run_name = format!("{}_vs_self", dataset_name);
        let bundle_root = derive_bundle_root_from_dataset_fasta(Path::new(&dataset_fasta_path))
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "failed to derive bundle root from dataset fasta path {}",
                    dataset_fasta_path
                )
            })?;
        let run_dir = bundle_root
            .join("runs")
            .join(format!("chr_{}", left_chr))
            .join(&run_name);
        let paf_path = run_dir.join("result.paf");
        if !paf_path.exists() {
            bail!("self evidence file does not exist: {}", paf_path.display());
        }
        let left_name_map = evidence_name_map_for_ctg(left.assembly_ctg_id, &left_visible);
        let right_name_map = evidence_name_map_for_ctg(right.assembly_ctg_id, &right_visible);
        let left_source_seq_ids = source_ids_from_evidence_name_map(&left_name_map);
        let right_source_seq_ids = source_ids_from_evidence_name_map(&right_name_map);
        let run_cache = ensure_pairwise_alignment_run_cache(
            conn, dataset_id, dataset_id, &run_name, &paf_path,
        )?;
        let cached_hits = query_pairwise_cached_hits(
            conn,
            run_cache.id,
            &left_source_seq_ids,
            &right_source_seq_ids,
            min_align_length,
            min_mapq,
            "self_paf",
        )?;
        let left_source_map = source_id_mapping_from_evidence_name_map(&left_name_map);
        let right_source_map = source_id_mapping_from_evidence_name_map(&right_name_map);
        let mut sorted_hits = assign_cached_pairwise_hit_assembly_ids(
            cached_hits,
            &left_source_map,
            &right_source_map,
        );
        sorted_hits.sort_by(|a, b| {
            b.align_length
                .cmp(&a.align_length)
                .then_with(|| b.identity_pct.total_cmp(&a.identity_pct))
                .then_with(|| a.query_source_seq_id.cmp(&b.query_source_seq_id))
                .then_with(|| a.subject_source_seq_id.cmp(&b.subject_source_seq_id))
        });
        ("self_paf".to_string(), sorted_hits)
    } else {
        let mut hits = read_cross_dataset_server_hits(
            conn,
            params.project_id,
            &left_chr,
            left.assembly_ctg_id,
            &left_visible,
            right.assembly_ctg_id,
            &right_visible,
            min_align_length,
            min_mapq,
        )?;
        hits.sort_by(|a, b| {
            b.align_length
                .cmp(&a.align_length)
                .then_with(|| b.identity_pct.total_cmp(&a.identity_pct))
                .then_with(|| a.query_source_seq_id.cmp(&b.query_source_seq_id))
                .then_with(|| a.subject_source_seq_id.cmp(&b.subject_source_seq_id))
        });
        ("ds_ds_paf".to_string(), hits)
    };

    Ok(JunctionInspectionReport {
        project_id: params.project_id,
        assigned_chr_name: left_chr,
        left,
        right,
        placement_relation,
        overlap_bp,
        gap_bp,
        same_dataset,
        evidence_source,
        evidence_hit_count: hits.len() as i64,
        hits,
    })
}

#[derive(Debug, Clone)]
struct EvidenceNameMapping {
    assembly_ctg_id: i64,
    source_seq_id: i64,
    orient: String,
    source_start: i64,
    source_end: i64,
    ctg_offset: i64,
}

fn normalize_requested_ctg_ids(values: &[i64]) -> Vec<i64> {
    values
        .iter()
        .copied()
        .filter(|value| *value > 0)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>()
}

fn load_ctg_contexts(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_ids: &[i64],
) -> Result<Vec<JunctionCtgContext>> {
    normalize_requested_ctg_ids(assembly_ctg_ids)
        .into_iter()
        .map(|assembly_ctg_id| load_ctg_context(conn, project_id, assembly_ctg_id))
        .collect::<Result<Vec<_>>>()
}

fn visible_members_by_ctg(
    contexts: &[JunctionCtgContext],
) -> Result<Vec<(i64, Vec<JunctionCtgMember>)>> {
    contexts
        .iter()
        .map(|context| {
            let visible = context
                .members
                .iter()
                .filter(|member| !member.hidden)
                .cloned()
                .collect::<Vec<_>>();
            if visible.is_empty() {
                bail!(
                    "track pairwise evidence requires visible members for assembly_ctg_id {}",
                    context.assembly_ctg_id
                );
            }
            Ok((context.assembly_ctg_id, visible))
        })
        .collect::<Result<Vec<_>>>()
}

fn require_same_assigned_chr(
    top_contexts: &[JunctionCtgContext],
    bottom_contexts: &[JunctionCtgContext],
) -> Result<String> {
    let chr_names = top_contexts
        .iter()
        .chain(bottom_contexts.iter())
        .map(|context| context.assigned_chr_name.clone())
        .collect::<BTreeSet<_>>();
    if chr_names.len() != 1 {
        bail!("track pairwise evidence requires all contigs to stay on the same chromosome");
    }
    chr_names.into_iter().next().flatten().ok_or_else(|| {
        anyhow::anyhow!("track pairwise evidence requires assigned chromosome names")
    })
}

fn evidence_name_map_by_dataset(
    contexts_with_members: &[(i64, Vec<JunctionCtgMember>)],
) -> HashMap<i64, HashMap<String, Vec<EvidenceNameMapping>>> {
    let mut by_dataset = HashMap::<i64, HashMap<String, Vec<EvidenceNameMapping>>>::new();
    for (assembly_ctg_id, members) in contexts_with_members {
        let mut ctg_offset = 0_i64;
        let mut sorted_members = members.iter().collect::<Vec<_>>();
        sorted_members.sort_by(|left, right| {
            left.member_order.cmp(&right.member_order).then_with(|| {
                left.assembly_ctg_member_id
                    .cmp(&right.assembly_ctg_member_id)
            })
        });
        for member in sorted_members {
            by_dataset
                .entry(member.dataset_id)
                .or_default()
                .entry(member.source_seq_name.clone())
                .or_default()
                .push(EvidenceNameMapping {
                    assembly_ctg_id: *assembly_ctg_id,
                    source_seq_id: member.source_seq_id,
                    orient: member.orient.clone(),
                    source_start: member.source_start,
                    source_end: member.source_end,
                    ctg_offset,
                });
            ctg_offset += member.used_length.max(0);
        }
    }
    by_dataset
}

fn evidence_name_map_for_ctg(
    assembly_ctg_id: i64,
    members: &[JunctionCtgMember],
) -> HashMap<String, Vec<EvidenceNameMapping>> {
    evidence_name_map_by_dataset(&[(assembly_ctg_id, members.to_vec())])
        .into_values()
        .next()
        .unwrap_or_default()
}

fn source_ids_from_evidence_name_map(
    name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
) -> Vec<i64> {
    name_map
        .values()
        .flat_map(|items| items.iter().map(|item| item.source_seq_id))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn source_id_mapping_from_evidence_name_map(
    name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
) -> HashMap<i64, Vec<EvidenceNameMapping>> {
    let mut source_map = HashMap::<i64, Vec<EvidenceNameMapping>>::new();
    for mappings in name_map.values() {
        for mapping in mappings {
            source_map
                .entry(mapping.source_seq_id)
                .or_default()
                .push(mapping.clone());
        }
    }
    source_map
}

fn assign_cached_pairwise_hit_assembly_ids(
    hits: Vec<JunctionEvidenceHit>,
    query_source_map: &HashMap<i64, Vec<EvidenceNameMapping>>,
    subject_source_map: &HashMap<i64, Vec<EvidenceNameMapping>>,
) -> Vec<JunctionEvidenceHit> {
    let mut assigned = Vec::new();
    for hit in hits {
        let Some(query_mappings) = query_source_map.get(&hit.query_source_seq_id) else {
            continue;
        };
        let Some(subject_mappings) = subject_source_map.get(&hit.subject_source_seq_id) else {
            continue;
        };
        for query in query_mappings {
            for subject in subject_mappings {
                if query.assembly_ctg_id == subject.assembly_ctg_id {
                    continue;
                }
                let Some((query_start, query_end)) =
                    transform_source_interval_to_ctg_display(query, hit.query_start, hit.query_end)
                else {
                    continue;
                };
                let Some((subject_start, subject_end)) = transform_source_interval_to_ctg_display(
                    subject,
                    hit.subject_start,
                    hit.subject_end,
                ) else {
                    continue;
                };
                let mut next = hit.clone();
                next.query_assembly_ctg_id = query.assembly_ctg_id;
                next.subject_assembly_ctg_id = subject.assembly_ctg_id;
                next.query_start = query_start;
                next.query_end = query_end;
                next.subject_start = subject_start;
                next.subject_end = subject_end;
                next.strand = transform_pairwise_strand_to_ctg_display(
                    &hit.strand,
                    &query.orient,
                    &subject.orient,
                );
                assigned.push(next);
            }
        }
    }
    assigned
}

fn transform_source_interval_to_ctg_display(
    mapping: &EvidenceNameMapping,
    start: i64,
    end: i64,
) -> Option<(i64, i64)> {
    let source_start = mapping.source_start.min(mapping.source_end);
    let source_end = mapping.source_start.max(mapping.source_end);
    let hit_start = start.min(end);
    let hit_end = start.max(end);
    let clipped_start = hit_start.max(source_start);
    let clipped_end = hit_end.min(source_end);
    if clipped_start > clipped_end {
        return None;
    }
    let ctg_offset = mapping.ctg_offset.max(0);
    if mapping.orient.trim() == "-" {
        Some((
            ctg_offset + source_end - clipped_end + 1,
            ctg_offset + source_end - clipped_start + 1,
        ))
    } else {
        Some((
            ctg_offset + clipped_start - source_start + 1,
            ctg_offset + clipped_end - source_start + 1,
        ))
    }
}

fn transform_pairwise_strand_to_ctg_display(
    strand: &str,
    query_orient: &str,
    subject_orient: &str,
) -> String {
    let normalized = if strand.trim() == "-" { "-" } else { "+" };
    let query_reversed = query_orient.trim() == "-";
    let subject_reversed = subject_orient.trim() == "-";
    if query_reversed ^ subject_reversed {
        if normalized == "+" {
            "-".to_string()
        } else {
            "+".to_string()
        }
    } else {
        normalized.to_string()
    }
}

fn get_track_pairwise_evidence_with_connection(
    conn: &mut Connection,
    _project_db_path: &Path,
    params: &GetTrackPairwiseEvidenceParams,
) -> Result<TrackPairwiseEvidenceReport> {
    let top_contexts = load_ctg_contexts(conn, params.project_id, &params.top_assembly_ctg_ids)?;
    let bottom_contexts =
        load_ctg_contexts(conn, params.project_id, &params.bottom_assembly_ctg_ids)?;
    if top_contexts.is_empty() || bottom_contexts.is_empty() {
        bail!("track pairwise evidence requires non-empty top/bottom contig sets");
    }

    let assigned_chr_name = require_same_assigned_chr(&top_contexts, &bottom_contexts)?;
    let top_visible = visible_members_by_ctg(&top_contexts)?;
    let bottom_visible = visible_members_by_ctg(&bottom_contexts)?;
    let top_name_map_by_dataset = evidence_name_map_by_dataset(&top_visible);
    let bottom_name_map_by_dataset = evidence_name_map_by_dataset(&bottom_visible);
    let top_dataset_ids = top_name_map_by_dataset
        .keys()
        .copied()
        .collect::<BTreeSet<_>>();
    let bottom_dataset_ids = bottom_name_map_by_dataset
        .keys()
        .copied()
        .collect::<BTreeSet<_>>();
    let same_dataset = top_dataset_ids.len() == 1
        && bottom_dataset_ids.len() == 1
        && top_dataset_ids == bottom_dataset_ids;
    let min_align_length = params.min_align_length.unwrap_or(0).max(0);
    let min_mapq = params.min_mapq.unwrap_or(0).max(0);

    let (evidence_source, mut hits) = if same_dataset {
        let dataset_id = *top_dataset_ids.iter().next().ok_or_else(|| {
            anyhow::anyhow!("failed to infer dataset for track-pair self evidence")
        })?;
        let (dataset_name, dataset_fasta_path) = conn
            .query_row(
                "SELECT name, fasta_path FROM dataset WHERE id = ?1",
                params![dataset_id],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            )
            .with_context(|| format!("dataset_id {} does not exist", dataset_id))?;
        let run_name = format!("{}_vs_self", dataset_name);
        let bundle_root = derive_bundle_root_from_dataset_fasta(Path::new(&dataset_fasta_path))
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "failed to derive bundle root from dataset fasta path {}",
                    dataset_fasta_path
                )
            })?;
        let run_dir = bundle_root
            .join("runs")
            .join(format!("chr_{}", assigned_chr_name))
            .join(&run_name);
        let paf_path = run_dir.join("result.paf");
        if !paf_path.exists() {
            bail!("self evidence file does not exist: {}", paf_path.display());
        }
        let top_name_map = top_name_map_by_dataset
            .get(&dataset_id)
            .cloned()
            .unwrap_or_default();
        let bottom_name_map = bottom_name_map_by_dataset
            .get(&dataset_id)
            .cloned()
            .unwrap_or_default();
        let top_source_seq_ids = source_ids_from_evidence_name_map(&top_name_map);
        let bottom_source_seq_ids = source_ids_from_evidence_name_map(&bottom_name_map);
        let run_cache = ensure_pairwise_alignment_run_cache(
            conn, dataset_id, dataset_id, &run_name, &paf_path,
        )?;
        let cached_hits = query_pairwise_cached_hits(
            conn,
            run_cache.id,
            &top_source_seq_ids,
            &bottom_source_seq_ids,
            min_align_length,
            min_mapq,
            "self_paf",
        )?;
        let top_source_map = source_id_mapping_from_evidence_name_map(&top_name_map);
        let bottom_source_map = source_id_mapping_from_evidence_name_map(&bottom_name_map);
        (
            "self_paf".to_string(),
            assign_cached_pairwise_hit_assembly_ids(
                cached_hits,
                &top_source_map,
                &bottom_source_map,
            ),
        )
    } else {
        let dataset_ids = top_name_map_by_dataset
            .keys()
            .chain(bottom_name_map_by_dataset.keys())
            .copied()
            .collect::<BTreeSet<_>>();
        let mut dataset_run_info_by_id = HashMap::<i64, DatasetRunInfo>::new();
        for dataset_id in dataset_ids {
            let (dataset_name, dataset_fasta_path) = conn
                .query_row(
                    "SELECT name, fasta_path FROM dataset WHERE id = ?1",
                    params![dataset_id],
                    |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
                )
                .with_context(|| format!("dataset_id {} does not exist", dataset_id))?;
            let bundle_root = derive_bundle_root_from_dataset_fasta(Path::new(&dataset_fasta_path))
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "failed to derive bundle root from dataset fasta path {}",
                        dataset_fasta_path
                    )
                })?;
            dataset_run_info_by_id.insert(
                dataset_id,
                DatasetRunInfo {
                    dataset_name,
                    bundle_root,
                },
            );
        }

        let mut hits = Vec::<JunctionEvidenceHit>::new();
        let mut missing_pairs = Vec::<String>::new();
        for (top_dataset_id, top_name_map) in &top_name_map_by_dataset {
            for (bottom_dataset_id, bottom_name_map) in &bottom_name_map_by_dataset {
                let top_info = dataset_run_info_by_id.get(top_dataset_id).ok_or_else(|| {
                    anyhow::anyhow!("missing dataset info for id {}", top_dataset_id)
                })?;
                let bottom_info =
                    dataset_run_info_by_id
                        .get(bottom_dataset_id)
                        .ok_or_else(|| {
                            anyhow::anyhow!("missing dataset info for id {}", bottom_dataset_id)
                        })?;
                let run_paths = resolve_cross_dataset_pair_run_paths(
                    &assigned_chr_name,
                    *top_dataset_id,
                    top_info,
                    top_name_map,
                    *bottom_dataset_id,
                    bottom_info,
                    bottom_name_map,
                );
                if run_paths.is_empty() {
                    missing_pairs.push(format!(
                        "{}_vs_{}",
                        top_info.dataset_name, bottom_info.dataset_name
                    ));
                    continue;
                };
                let top_source_seq_ids = source_ids_from_evidence_name_map(top_name_map);
                let bottom_source_seq_ids = source_ids_from_evidence_name_map(bottom_name_map);
                let top_source_map = source_id_mapping_from_evidence_name_map(top_name_map);
                let bottom_source_map = source_id_mapping_from_evidence_name_map(bottom_name_map);
                for run_path in run_paths {
                    let run_cache = ensure_pairwise_alignment_run_cache(
                        conn,
                        run_path.query_dataset_id,
                        run_path.target_dataset_id,
                        &run_path.run_name,
                        &run_path.paf_path,
                    )
                    .with_context(|| {
                        format!("failed to cache pair paf {}", run_path.paf_path.display())
                    })?;
                    let cached_hits = query_pairwise_cached_hits(
                        conn,
                        run_cache.id,
                        &top_source_seq_ids,
                        &bottom_source_seq_ids,
                        min_align_length,
                        min_mapq,
                        "ds_ds_paf",
                    )?;
                    hits.extend(assign_cached_pairwise_hit_assembly_ids(
                        cached_hits,
                        &top_source_map,
                        &bottom_source_map,
                    ));
                }
            }
        }
        if hits.is_empty() && !missing_pairs.is_empty() {
            missing_pairs.sort();
            missing_pairs.dedup();
            bail!(
                "cross-dataset evidence file does not exist for required dataset pair(s): {}",
                missing_pairs.join(", ")
            );
        }
        ("ds_ds_paf".to_string(), hits)
    };

    hits.sort_by(|a, b| {
        b.align_length
            .cmp(&a.align_length)
            .then_with(|| b.identity_pct.total_cmp(&a.identity_pct))
            .then_with(|| a.query_assembly_ctg_id.cmp(&b.query_assembly_ctg_id))
            .then_with(|| a.subject_assembly_ctg_id.cmp(&b.subject_assembly_ctg_id))
            .then_with(|| a.query_start.cmp(&b.query_start))
            .then_with(|| a.subject_start.cmp(&b.subject_start))
    });

    Ok(TrackPairwiseEvidenceReport {
        project_id: params.project_id,
        assigned_chr_name,
        same_dataset,
        evidence_source,
        evidence_hit_count: hits.len() as i64,
        top_assembly_ctg_ids: normalize_requested_ctg_ids(&params.top_assembly_ctg_ids),
        bottom_assembly_ctg_ids: normalize_requested_ctg_ids(&params.bottom_assembly_ctg_ids),
        hits,
    })
}

fn load_ctg_context(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<JunctionCtgContext> {
    let head = conn
        .query_row(
            "SELECT id, project_id, name, assigned_chr_name, anchor_start, placement_mode
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
                    row.get::<_, String>(5)?,
                ))
            },
        )
        .optional()
        .context("failed to query assembly_ctg header")?;
    let Some((id, row_project_id, name, assigned_chr_name, anchor_start, placement_mode)) = head
    else {
        bail!("assembly_ctg_id {} does not exist", assembly_ctg_id);
    };
    if row_project_id != project_id {
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
                c.assembly_seq_id,
                1 AS member_order,
                s.source_seq_id,
                ss.seq_name,
                ss.length,
                ss.dataset_id,
                d.name,
                s.orient,
                s.source_start,
                s.source_end,
                s.hidden
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE c.id = ?1
             ORDER BY c.id",
        )
        .context("failed to prepare assembly_ctg member query")?;
    let members = member_stmt
        .query_map(params![assembly_ctg_id], |row| {
            let source_start: i64 = row.get(9)?;
            let source_end: i64 = row.get(10)?;
            Ok(JunctionCtgMember {
                assembly_ctg_member_id: row.get(0)?,
                assembly_seq_id: row.get(1)?,
                member_order: row.get(2)?,
                source_seq_id: row.get(3)?,
                source_seq_name: row.get(4)?,
                source_seq_length: row.get(5)?,
                dataset_id: row.get(6)?,
                dataset_name: row.get(7)?,
                orient: row.get(8)?,
                source_start,
                source_end,
                used_length: (source_end - source_start + 1).max(0),
                hidden: row.get::<_, i64>(11)? > 0,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode assembly_ctg members")?;

    let member_count = members.len() as i64;
    let visible_members = members
        .iter()
        .filter(|member| !member.hidden)
        .cloned()
        .collect::<Vec<_>>();
    let visible_member_count = visible_members.len() as i64;
    let span_length = estimate_ctg_visible_span(&visible_members);
    let anchor_end = anchor_start.and_then(|start| {
        if span_length > 0 {
            Some(start + span_length - 1)
        } else {
            None
        }
    });
    let dataset_ids = members
        .iter()
        .map(|member| member.dataset_id)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let dataset_names = members
        .iter()
        .map(|member| member.dataset_name.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();

    Ok(JunctionCtgContext {
        assembly_ctg_id: id,
        name,
        assigned_chr_name,
        anchor_start,
        anchor_end,
        span_length,
        placement_mode,
        member_count,
        visible_member_count,
        dataset_ids,
        dataset_names,
        members,
    })
}

fn estimate_ctg_visible_span(members: &[JunctionCtgMember]) -> i64 {
    members.iter().map(|member| member.used_length.max(0)).sum()
}

fn normalize_left_right(
    left: JunctionCtgContext,
    right: JunctionCtgContext,
) -> (JunctionCtgContext, JunctionCtgContext) {
    let left_key = (left.anchor_start.unwrap_or(i64::MAX), left.assembly_ctg_id);
    let right_key = (
        right.anchor_start.unwrap_or(i64::MAX),
        right.assembly_ctg_id,
    );
    if left_key <= right_key {
        (left, right)
    } else {
        (right, left)
    }
}

fn placement_relation(
    left_anchor_start: Option<i64>,
    left_anchor_end: Option<i64>,
    right_anchor_start: Option<i64>,
    right_anchor_end: Option<i64>,
) -> (String, Option<i64>, Option<i64>) {
    let (Some(_left_start), Some(left_end), Some(right_start), Some(_right_end)) = (
        left_anchor_start,
        left_anchor_end,
        right_anchor_start,
        right_anchor_end,
    ) else {
        return ("unknown".to_string(), None, None);
    };
    if left_end >= right_start {
        return (
            "overlap".to_string(),
            Some(left_end - right_start + 1),
            None,
        );
    }
    if right_start > left_end + 1 {
        return ("gap".to_string(), None, Some(right_start - left_end - 1));
    }
    ("adjacent".to_string(), None, Some(0))
}

#[derive(Debug, Clone)]
struct ParsedSelfPafHit {
    query_name: String,
    target_name: String,
    strand: String,
    query_start: i64,
    query_end: i64,
    subject_start: i64,
    subject_end: i64,
    match_length: i64,
    mapq: i64,
    identity_pct: f64,
    align_length: i64,
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct PairwiseRunCache {
    pub(crate) id: i64,
    pub(crate) hit_count: i64,
}

fn ensure_pairwise_alignment_run_cache(
    conn: &mut Connection,
    query_dataset_id: i64,
    target_dataset_id: i64,
    run_name: &str,
    paf_path: &Path,
) -> Result<PairwiseRunCache> {
    ensure_pairwise_alignment_run_cache_cancel(
        conn,
        query_dataset_id,
        target_dataset_id,
        run_name,
        paf_path,
        &mut || false,
    )
}

pub(crate) fn ensure_pairwise_alignment_run_cache_cancel<F>(
    conn: &mut Connection,
    query_dataset_id: i64,
    target_dataset_id: i64,
    run_name: &str,
    paf_path: &Path,
    should_cancel: &mut F,
) -> Result<PairwiseRunCache>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("import cancelled");
    }
    let metadata = std::fs::metadata(paf_path)
        .with_context(|| format!("failed to stat pairwise paf {}", paf_path.display()))?;
    let paf_size_bytes = i64::try_from(metadata.len()).unwrap_or(i64::MAX);
    let paf_mtime_ms = metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| i64::try_from(duration.as_millis()).unwrap_or(i64::MAX))
        .unwrap_or(0);
    let paf_path_text = paf_path.to_string_lossy().to_string();
    let existing = conn
        .query_row(
            "SELECT id, paf_mtime_ms, paf_size_bytes, run_name, query_dataset_id, target_dataset_id
             FROM pairwise_alignment_run
             WHERE paf_path = ?1",
            params![paf_path_text],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, i64>(5)?,
                ))
            },
        )
        .optional()
        .context("failed to query pairwise_alignment_run")?;
    if let Some((
        id,
        cached_mtime_ms,
        cached_size_bytes,
        cached_run_name,
        cached_query_dataset_id,
        cached_target_dataset_id,
    )) = existing
    {
        let orientation_matches = cached_run_name == run_name
            && cached_query_dataset_id == query_dataset_id
            && cached_target_dataset_id == target_dataset_id;
        if cached_mtime_ms == paf_mtime_ms
            && cached_size_bytes == paf_size_bytes
            && orientation_matches
        {
            let hit_count = conn
                .query_row(
                    "SELECT COUNT(*) FROM pairwise_alignment_hit WHERE run_id = ?1",
                    params![id],
                    |row| row.get::<_, i64>(0),
                )
                .context("failed to count cached pairwise hits")?;
            return Ok(PairwiseRunCache { id, hit_count });
        }
        let tx = conn
            .transaction()
            .context("failed to begin pairwise cache rebuild")?;
        tx.execute(
            "DELETE FROM pairwise_alignment_hit WHERE run_id = ?1",
            params![id],
        )
        .context("failed to clear stale pairwise hits")?;
        tx.execute(
            "UPDATE pairwise_alignment_run
             SET run_name = ?1,
                 query_dataset_id = ?2,
                 target_dataset_id = ?3,
                 paf_mtime_ms = ?4,
                 paf_size_bytes = ?5,
                 indexed_at = ?6
             WHERE id = ?7",
            params![
                run_name,
                query_dataset_id,
                target_dataset_id,
                paf_mtime_ms,
                paf_size_bytes,
                current_unix_millis_text(),
                id
            ],
        )
        .context("failed to update pairwise run cache metadata")?;
        let hit_count = insert_pairwise_alignment_hits(
            &tx,
            id,
            query_dataset_id,
            target_dataset_id,
            paf_path,
            should_cancel,
        )?;
        tx.commit()
            .context("failed to commit pairwise cache rebuild")?;
        return Ok(PairwiseRunCache { id, hit_count });
    }

    let tx = conn
        .transaction()
        .context("failed to begin pairwise cache build")?;
    tx.execute(
        "INSERT INTO pairwise_alignment_run (
            run_name, paf_path, query_dataset_id, target_dataset_id,
            paf_mtime_ms, paf_size_bytes, indexed_at
         )
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            run_name,
            paf_path_text,
            query_dataset_id,
            target_dataset_id,
            paf_mtime_ms,
            paf_size_bytes,
            current_unix_millis_text()
        ],
    )
    .context("failed to insert pairwise run cache metadata")?;
    let run_id = tx.last_insert_rowid();
    let hit_count = insert_pairwise_alignment_hits(
        &tx,
        run_id,
        query_dataset_id,
        target_dataset_id,
        paf_path,
        should_cancel,
    )?;
    tx.commit()
        .context("failed to commit pairwise cache build")?;
    Ok(PairwiseRunCache {
        id: run_id,
        hit_count,
    })
}

fn current_unix_millis_text() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

fn source_seq_name_map_for_dataset(
    conn: &Connection,
    dataset_id: i64,
) -> Result<HashMap<String, i64>> {
    let mut stmt = conn
        .prepare("SELECT seq_name, id FROM source_seq WHERE dataset_id = ?1")
        .context("failed to prepare source_seq map query")?;
    let rows = stmt
        .query_map(params![dataset_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode source_seq map")?;
    Ok(rows.into_iter().collect())
}

fn insert_pairwise_alignment_hits(
    conn: &Connection,
    run_id: i64,
    query_dataset_id: i64,
    target_dataset_id: i64,
    paf_path: &Path,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<i64> {
    let query_name_map = source_seq_name_map_for_dataset(conn, query_dataset_id)?;
    let target_name_map = source_seq_name_map_for_dataset(conn, target_dataset_id)?;
    let file = File::open(paf_path)
        .with_context(|| format!("failed to open pairwise paf {}", paf_path.display()))?;
    let reader = BufReader::new(file);
    let mut insert_stmt = conn
        .prepare(
            "INSERT INTO pairwise_alignment_hit (
                run_id, query_source_seq_id, target_source_seq_id, strand,
                query_start, query_end, target_start, target_end,
                match_length, align_length, mapq, identity_pct
             )
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
        )
        .context("failed to prepare pairwise hit insert")?;
    let mut inserted = 0_i64;
    for line in reader.lines() {
        if should_cancel() {
            bail!("import cancelled");
        }
        let line = line.with_context(|| format!("failed to read {}", paf_path.display()))?;
        let Some(hit) = parse_self_paf_line(&line) else {
            continue;
        };
        let Some(query_source_seq_id) = query_name_map.get(&hit.query_name).copied() else {
            continue;
        };
        let Some(target_source_seq_id) = target_name_map.get(&hit.target_name).copied() else {
            continue;
        };
        // Self-run same-contig rows are skipped at import time to keep the cache lean.
        if query_dataset_id == target_dataset_id && query_source_seq_id == target_source_seq_id {
            continue;
        }
        insert_stmt
            .execute(params![
                run_id,
                query_source_seq_id,
                target_source_seq_id,
                hit.strand,
                hit.query_start,
                hit.query_end,
                hit.subject_start,
                hit.subject_end,
                hit.match_length,
                hit.align_length,
                hit.mapq,
                hit.identity_pct,
            ])
            .context("failed to insert pairwise alignment hit")?;
        inserted += 1;
    }
    Ok(inserted)
}

fn query_pairwise_cached_hits(
    conn: &Connection,
    run_id: i64,
    query_source_seq_ids: &[i64],
    target_source_seq_ids: &[i64],
    min_align_length: i64,
    min_mapq: i64,
    evidence_origin: &str,
) -> Result<Vec<JunctionEvidenceHit>> {
    if query_source_seq_ids.is_empty() || target_source_seq_ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut hits = query_pairwise_cached_hits_direction(
        conn,
        run_id,
        query_source_seq_ids,
        target_source_seq_ids,
        min_align_length,
        min_mapq,
        evidence_origin,
        false,
    )?;
    hits.extend(query_pairwise_cached_hits_direction(
        conn,
        run_id,
        query_source_seq_ids,
        target_source_seq_ids,
        min_align_length,
        min_mapq,
        evidence_origin,
        true,
    )?);
    Ok(hits)
}

#[allow(clippy::too_many_arguments)]
fn query_pairwise_cached_hits_direction(
    conn: &Connection,
    run_id: i64,
    query_source_seq_ids: &[i64],
    target_source_seq_ids: &[i64],
    min_align_length: i64,
    min_mapq: i64,
    evidence_origin: &str,
    swapped: bool,
) -> Result<Vec<JunctionEvidenceHit>> {
    let query_placeholders = std::iter::repeat_n("?", query_source_seq_ids.len())
        .collect::<Vec<_>>()
        .join(", ");
    let target_placeholders = std::iter::repeat_n("?", target_source_seq_ids.len())
        .collect::<Vec<_>>()
        .join(", ");
    let (query_filter_column, target_filter_column) = if swapped {
        ("h.target_source_seq_id", "h.query_source_seq_id")
    } else {
        ("h.query_source_seq_id", "h.target_source_seq_id")
    };
    let sql = format!(
        "SELECT
            h.query_source_seq_id,
            query_seq.seq_name,
            h.target_source_seq_id,
            target_seq.seq_name,
            h.strand,
            h.query_start,
            h.query_end,
            h.target_start,
            h.target_end,
            h.mapq,
            h.identity_pct,
            h.align_length
         FROM pairwise_alignment_hit h
         JOIN source_seq query_seq ON query_seq.id = h.query_source_seq_id
         JOIN source_seq target_seq ON target_seq.id = h.target_source_seq_id
         WHERE h.run_id = ?1
           AND h.align_length >= ?2
           AND h.mapq >= ?3
           AND {query_filter_column} IN ({query_placeholders})
           AND {target_filter_column} IN ({target_placeholders})"
    );
    let mut values = vec![
        Value::Integer(run_id),
        Value::Integer(min_align_length),
        Value::Integer(min_mapq),
    ];
    values.extend(query_source_seq_ids.iter().copied().map(Value::Integer));
    values.extend(target_source_seq_ids.iter().copied().map(Value::Integer));
    let mut stmt = conn
        .prepare(&sql)
        .context("failed to prepare pairwise cache query")?;
    let rows = stmt
        .query_map(params_from_iter(values), |row| {
            let stored_query_source_seq_id: i64 = row.get(0)?;
            let stored_query_source_seq_name: String = row.get(1)?;
            let stored_target_source_seq_id: i64 = row.get(2)?;
            let stored_target_source_seq_name: String = row.get(3)?;
            let strand: String = row.get(4)?;
            let stored_query_start: i64 = row.get(5)?;
            let stored_query_end: i64 = row.get(6)?;
            let stored_target_start: i64 = row.get(7)?;
            let stored_target_end: i64 = row.get(8)?;
            let mapq: i64 = row.get(9)?;
            let identity_pct: f64 = row.get(10)?;
            let align_length: i64 = row.get(11)?;
            let (
                query_source_seq_id,
                query_source_seq_name,
                query_start,
                query_end,
                subject_source_seq_id,
                subject_source_seq_name,
                subject_start,
                subject_end,
            ) = if swapped {
                (
                    stored_target_source_seq_id,
                    stored_target_source_seq_name,
                    stored_target_start,
                    stored_target_end,
                    stored_query_source_seq_id,
                    stored_query_source_seq_name,
                    stored_query_start,
                    stored_query_end,
                )
            } else {
                (
                    stored_query_source_seq_id,
                    stored_query_source_seq_name,
                    stored_query_start,
                    stored_query_end,
                    stored_target_source_seq_id,
                    stored_target_source_seq_name,
                    stored_target_start,
                    stored_target_end,
                )
            };
            Ok(JunctionEvidenceHit {
                query_assembly_ctg_id: 0,
                query_source_seq_id,
                query_source_seq_name,
                subject_assembly_ctg_id: 0,
                subject_source_seq_id,
                subject_source_seq_name,
                strand,
                query_start,
                query_end,
                subject_start,
                subject_end,
                mapq,
                identity_pct,
                align_length,
                mismatch_count: None,
                gap_open_count: None,
                evalue: None,
                bit_score: None,
                evidence_origin: evidence_origin.to_string(),
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode pairwise cache query rows")?;
    Ok(rows)
}

fn parse_self_paf_line(line: &str) -> Option<ParsedSelfPafHit> {
    let mut fields = line.split('\t');
    let query_name = fields.next()?.to_string();
    let _query_length = fields.next()?.parse::<i64>().ok()?;
    let query_start_0 = fields.next()?.parse::<i64>().ok()?;
    let query_end_0 = fields.next()?.parse::<i64>().ok()?;
    let strand = fields.next()?.to_string();
    if strand != "+" && strand != "-" {
        return None;
    }
    let target_name = fields.next()?.to_string();
    let _target_length = fields.next()?.parse::<i64>().ok()?;
    let subject_start_0 = fields.next()?.parse::<i64>().ok()?;
    let subject_end_0 = fields.next()?.parse::<i64>().ok()?;
    let match_length = fields.next()?.parse::<i64>().ok()?;
    let align_length = fields.next()?.parse::<i64>().ok()?;
    let mapq = fields.next()?.parse::<i64>().ok()?;
    if align_length <= 0 {
        return None;
    }
    let identity_pct = (match_length as f64) * 100.0 / (align_length as f64);
    let query_start = query_start_0 + 1;
    let query_end = query_end_0;
    let subject_start = subject_start_0 + 1;
    let subject_end = subject_end_0;
    if query_start < 1 || query_end < query_start {
        return None;
    }
    if subject_start < 1 || subject_end < subject_start {
        return None;
    }
    Some(ParsedSelfPafHit {
        query_name,
        target_name,
        strand,
        query_start,
        query_end,
        subject_start,
        subject_end,
        match_length,
        mapq,
        identity_pct,
        align_length,
    })
}

#[derive(Debug, Clone)]
struct DatasetRunInfo {
    dataset_name: String,
    bundle_root: PathBuf,
}

#[derive(Debug, Clone)]
struct PairwiseRunPath {
    run_name: String,
    paf_path: PathBuf,
    query_dataset_id: i64,
    target_dataset_id: i64,
}

#[allow(clippy::too_many_arguments)]
fn read_cross_dataset_server_hits(
    conn: &mut Connection,
    _project_id: i64,
    assigned_chr_name: &str,
    left_assembly_ctg_id: i64,
    left_members: &[JunctionCtgMember],
    right_assembly_ctg_id: i64,
    right_members: &[JunctionCtgMember],
    min_align_length: i64,
    min_mapq: i64,
) -> Result<Vec<JunctionEvidenceHit>> {
    let left_name_map_by_dataset =
        evidence_name_map_by_dataset(&[(left_assembly_ctg_id, left_members.to_vec())]);
    let right_name_map_by_dataset =
        evidence_name_map_by_dataset(&[(right_assembly_ctg_id, right_members.to_vec())]);
    let dataset_ids = left_name_map_by_dataset
        .keys()
        .chain(right_name_map_by_dataset.keys())
        .copied()
        .collect::<BTreeSet<_>>();
    let mut dataset_run_info_by_id = HashMap::<i64, DatasetRunInfo>::new();
    for dataset_id in dataset_ids {
        let (dataset_name, dataset_fasta_path) = conn
            .query_row(
                "SELECT name, fasta_path FROM dataset WHERE id = ?1",
                params![dataset_id],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            )
            .with_context(|| format!("dataset_id {} does not exist", dataset_id))?;
        let bundle_root = derive_bundle_root_from_dataset_fasta(Path::new(&dataset_fasta_path))
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "failed to derive bundle root from dataset fasta path {}",
                    dataset_fasta_path
                )
            })?;
        dataset_run_info_by_id.insert(
            dataset_id,
            DatasetRunInfo {
                dataset_name,
                bundle_root,
            },
        );
    }

    let mut hits = Vec::<JunctionEvidenceHit>::new();
    let mut missing_pairs = Vec::<String>::new();

    for (left_dataset_id, left_name_map) in &left_name_map_by_dataset {
        for (right_dataset_id, right_name_map) in &right_name_map_by_dataset {
            let left_info = dataset_run_info_by_id.get(left_dataset_id).ok_or_else(|| {
                anyhow::anyhow!("missing dataset info for id {}", left_dataset_id)
            })?;
            let right_info = dataset_run_info_by_id
                .get(right_dataset_id)
                .ok_or_else(|| {
                    anyhow::anyhow!("missing dataset info for id {}", right_dataset_id)
                })?;
            let run_paths = resolve_cross_dataset_pair_run_paths(
                assigned_chr_name,
                *left_dataset_id,
                left_info,
                left_name_map,
                *right_dataset_id,
                right_info,
                right_name_map,
            );
            if run_paths.is_empty() {
                missing_pairs.push(format!(
                    "{}_vs_{}",
                    left_info.dataset_name, right_info.dataset_name
                ));
                continue;
            };
            let left_source_seq_ids = source_ids_from_evidence_name_map(left_name_map);
            let right_source_seq_ids = source_ids_from_evidence_name_map(right_name_map);
            let left_source_map = source_id_mapping_from_evidence_name_map(left_name_map);
            let right_source_map = source_id_mapping_from_evidence_name_map(right_name_map);
            for run_path in run_paths {
                let run_cache = ensure_pairwise_alignment_run_cache(
                    conn,
                    run_path.query_dataset_id,
                    run_path.target_dataset_id,
                    &run_path.run_name,
                    &run_path.paf_path,
                )
                .with_context(|| format!("failed to cache pair paf {}", run_path.paf_path.display()))?;
                let pair_hits = query_pairwise_cached_hits(
                    conn,
                    run_cache.id,
                    &left_source_seq_ids,
                    &right_source_seq_ids,
                    min_align_length,
                    min_mapq,
                    "ds_ds_paf",
                )?;
                hits.extend(assign_cached_pairwise_hit_assembly_ids(
                    pair_hits,
                    &left_source_map,
                    &right_source_map,
                ));
            }
        }
    }

    if hits.is_empty() && !missing_pairs.is_empty() {
        missing_pairs.sort();
        missing_pairs.dedup();
        bail!(
            "cross-dataset evidence file does not exist for required dataset pair(s): {}",
            missing_pairs.join(", ")
        );
    }

    Ok(hits)
}

fn resolve_cross_dataset_pair_run_path(
    assigned_chr_name: &str,
    left_dataset_id: i64,
    left: &DatasetRunInfo,
    right_dataset_id: i64,
    right: &DatasetRunInfo,
) -> Option<PairwiseRunPath> {
    let mut roots = vec![left.bundle_root.clone()];
    if right.bundle_root != left.bundle_root {
        roots.push(right.bundle_root.clone());
    }

    let run_candidates = if left.dataset_name == right.dataset_name {
        vec![(
            format!("{}_vs_self", left.dataset_name),
            left_dataset_id,
            right_dataset_id,
        )]
    } else {
        vec![
            (
                format!("{}_vs_{}", left.dataset_name, right.dataset_name),
                right_dataset_id,
                left_dataset_id,
            ),
            (
                format!("{}_vs_{}", right.dataset_name, left.dataset_name),
                left_dataset_id,
                right_dataset_id,
            ),
        ]
    };

    for root in roots {
        for (run_name, query_dataset_id, target_dataset_id) in &run_candidates {
            let paf_path = root
                .join("runs")
                .join(format!("chr_{}", assigned_chr_name))
                .join(run_name)
                .join("result.paf");
            if paf_path.exists() {
                return Some(PairwiseRunPath {
                    run_name: run_name.clone(),
                    paf_path,
                    query_dataset_id: *query_dataset_id,
                    target_dataset_id: *target_dataset_id,
                });
            }
        }
    }
    None
}

fn resolve_cross_dataset_pair_run_paths(
    assigned_chr_name: &str,
    left_dataset_id: i64,
    left: &DatasetRunInfo,
    left_name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
    right_dataset_id: i64,
    right: &DatasetRunInfo,
    right_name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
) -> Vec<PairwiseRunPath> {
    let mut paths = Vec::<PairwiseRunPath>::new();
    let mut seen = BTreeSet::<PathBuf>::new();
    if let Some(run_path) = resolve_cross_dataset_pair_run_path(
        assigned_chr_name,
        left_dataset_id,
        left,
        right_dataset_id,
        right,
    ) {
        seen.insert(run_path.paf_path.clone());
        paths.push(run_path);
    }
    extend_add_ctg_pair_run_paths(
        &mut paths,
        &mut seen,
        assigned_chr_name,
        left_dataset_id,
        left,
        left_name_map,
        right_dataset_id,
        right,
        right_name_map,
    );
    paths
}

#[allow(clippy::too_many_arguments)]
fn extend_add_ctg_pair_run_paths(
    paths: &mut Vec<PairwiseRunPath>,
    seen: &mut BTreeSet<PathBuf>,
    assigned_chr_name: &str,
    left_dataset_id: i64,
    left: &DatasetRunInfo,
    left_name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
    right_dataset_id: i64,
    right: &DatasetRunInfo,
    right_name_map: &HashMap<String, Vec<EvidenceNameMapping>>,
) {
    let mut roots = vec![left.bundle_root.clone()];
    if right.bundle_root != left.bundle_root {
        roots.push(right.bundle_root.clone());
    }
    if left.dataset_name == DERIVED_CTG_DATASET_NAME
        && right.dataset_name != DERIVED_CTG_DATASET_NAME
    {
        for derived_ctg_name in sorted_evidence_names(left_name_map) {
            let run_name = format!("{}_vs_{}", right.dataset_name, derived_ctg_name);
            push_add_ctg_pair_run_path(
                paths,
                seen,
                &roots,
                assigned_chr_name,
                run_name,
                left_dataset_id,
                right_dataset_id,
            );
        }
    }
    if right.dataset_name == DERIVED_CTG_DATASET_NAME
        && left.dataset_name != DERIVED_CTG_DATASET_NAME
    {
        for derived_ctg_name in sorted_evidence_names(right_name_map) {
            let run_name = format!("{}_vs_{}", left.dataset_name, derived_ctg_name);
            push_add_ctg_pair_run_path(
                paths,
                seen,
                &roots,
                assigned_chr_name,
                run_name,
                right_dataset_id,
                left_dataset_id,
            );
        }
    }
}

fn sorted_evidence_names(name_map: &HashMap<String, Vec<EvidenceNameMapping>>) -> Vec<&str> {
    name_map
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn push_add_ctg_pair_run_path(
    paths: &mut Vec<PairwiseRunPath>,
    seen: &mut BTreeSet<PathBuf>,
    roots: &[PathBuf],
    assigned_chr_name: &str,
    run_name: String,
    query_dataset_id: i64,
    target_dataset_id: i64,
) {
    for root in roots {
        let paf_path = root
            .join("runs")
            .join(format!("chr_{}", assigned_chr_name))
            .join("add_ctg")
            .join(&run_name)
            .join("result.paf");
        if paf_path.exists() && seen.insert(paf_path.clone()) {
            paths.push(PairwiseRunPath {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
            return;
        }
    }
}

fn derive_bundle_root_from_dataset_fasta(fasta_path: &Path) -> Option<PathBuf> {
    let datasets_dir = fasta_path.parent()?;
    if datasets_dir
        .file_name()?
        .to_string_lossy()
        .to_ascii_lowercase()
        != "datasets"
    {
        return None;
    }
    let data_dir = datasets_dir.parent()?;
    if data_dir.file_name()?.to_string_lossy().to_ascii_lowercase() != "data" {
        return None;
    }
    Some(data_dir.parent()?.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::init_workspace_schema;
    use rusqlite::{Connection, params};
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn reads_same_dataset_self_paf_with_index() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join(".gpm_next_workspace");
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/chr_Chr01/ds1_vs_self")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/chr_Chr02/ds1_vs_self")).unwrap();

        fs::write(
            workspace_root.join("data/datasets/ds1.fa"),
            ">tigA\nACGT\n>tigB\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/datasets/ds1.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();

        let paf = "tigA\t1000\t0\t500\t+\ttigB\t1000\t100\t600\t450\t500\t60\n\
                   tigA\t1000\t10\t120\t+\ttigB\t1000\t200\t310\t100\t110\t60\n\
                   tigA\t1000\t20\t120\t+\ttigA\t1000\t300\t400\t90\t100\t60\n";
        fs::write(
            workspace_root.join("runs/chr_Chr01/ds1_vs_self/result.paf"),
            paf,
        )
        .unwrap();
        let idx = format!(
            "# gpm_next_self_paf_index\tv1\n# columns\tquery_seq_id\tquery_name\toffset\tlength\tline_count\n1\ttigA\t0\t{}\t3\n",
            paf.len()
        );
        fs::write(
            workspace_root.join("runs/chr_Chr01/ds1_vs_self/result.paf.idx.tsv"),
            idx,
        )
        .unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root.join("data/reference/ref.fa.fai").to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/ds1.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds1.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 1000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (102, 1, 'tigB', 2, 1000)",
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
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 1, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (201, 1, 101, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (202, 1, 102, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (302, 1, 202, 'Ctg2', 'Chr01', 2, 900, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        drop(conn);

        let report = get_junction_inspection(
            &db_path,
            &GetJunctionInspectionParams {
                project_id: 1,
                left_assembly_ctg_id: 301,
                right_assembly_ctg_id: 302,
                min_align_length: Some(300),
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(report.evidence_source, "self_paf");
        assert_eq!(report.evidence_hit_count, 1);
        assert_eq!(report.hits[0].query_source_seq_name, "tigA");
        assert_eq!(report.hits[0].subject_source_seq_name, "tigB");
        assert_eq!(report.hits[0].query_start, 1);
        assert_eq!(report.hits[0].query_end, 500);
        assert_eq!(report.hits[0].subject_start, 101);
        assert_eq!(report.hits[0].subject_end, 600);

        let conn = Connection::open(&db_path).unwrap();
        let cached_run_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM pairwise_alignment_run", [], |row| {
                row.get(0)
            })
            .unwrap();
        let cached_hit_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM pairwise_alignment_hit", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(cached_run_count, 1);
        assert_eq!(cached_hit_count, 2);
        drop(conn);

        let track_report = get_track_pairwise_evidence(
            &db_path,
            &GetTrackPairwiseEvidenceParams {
                project_id: 1,
                top_assembly_ctg_ids: vec![301],
                bottom_assembly_ctg_ids: vec![302],
                min_align_length: Some(300),
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(track_report.assigned_chr_name, "Chr01");
        assert_eq!(track_report.evidence_source, "self_paf");
        assert!(track_report.same_dataset);
        assert_eq!(track_report.evidence_hit_count, 1);
        assert_eq!(track_report.top_assembly_ctg_ids, vec![301]);
        assert_eq!(track_report.bottom_assembly_ctg_ids, vec![302]);
        assert_eq!(track_report.hits[0].query_assembly_ctg_id, 301);
        assert_eq!(track_report.hits[0].subject_assembly_ctg_id, 302);
        assert_eq!(track_report.hits[0].query_start, 1);
        assert_eq!(track_report.hits[0].query_end, 500);
        assert_eq!(track_report.hits[0].subject_start, 101);
        assert_eq!(track_report.hits[0].subject_end, 600);
    }

    #[test]
    fn junction_and_track_pairwise_use_pairwise_cache_bidirectionally() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(&workspace_root).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/chr_Chr01/ds2_vs_ds1")).unwrap();

        fs::write(workspace_root.join("data/datasets/ds1.fa"), ">tigA\nACGT\n").unwrap();
        fs::write(workspace_root.join("data/datasets/ds1.fa.fai"), "").unwrap();
        fs::write(workspace_root.join("data/datasets/ds2.fa"), ">tigB\nACGT\n").unwrap();
        fs::write(workspace_root.join("data/datasets/ds2.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("runs/chr_Chr01/ds2_vs_ds1/result.paf"),
            "tigA\t1000\t100\t300\t+\ttigB\t900\t0\t200\t180\t200\t60\n",
        )
        .unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root.join("data/reference/ref.fa.fai").to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/ds1.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds1.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (2, 'ds2', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/ds2.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds2.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 1000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (201, 2, 'tigB', 1, 900)",
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
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 1, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 2, 'support', 2)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (301, 1, 101, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (302, 1, 201, '+', 1, 900, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (401, 1, 301, 'Ctg1', 'Chr01', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (402, 1, 302, 'Ctg2', 'Chr01', 2, 900, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        drop(conn);

        let report = get_junction_inspection(
            &db_path,
            &GetJunctionInspectionParams {
                project_id: 1,
                left_assembly_ctg_id: 401,
                right_assembly_ctg_id: 402,
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(report.evidence_source, "ds_ds_paf");
        assert_eq!(report.evidence_hit_count, 1);
        assert_eq!(report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(report.hits[0].query_source_seq_name, "tigA");
        assert_eq!(report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(report.hits[0].subject_source_seq_name, "tigB");
        assert_eq!(report.hits[0].query_start, 101);
        assert_eq!(report.hits[0].query_end, 300);
        assert_eq!(report.hits[0].subject_start, 1);
        assert_eq!(report.hits[0].subject_end, 200);

        let conn = Connection::open(&db_path).unwrap();
        let cached_run_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM pairwise_alignment_run", [], |row| {
                row.get(0)
            })
            .unwrap();
        let cached_hit_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM pairwise_alignment_hit", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(cached_run_count, 1);
        assert_eq!(cached_hit_count, 1);
        drop(conn);

        let track_report = get_track_pairwise_evidence(
            &db_path,
            &GetTrackPairwiseEvidenceParams {
                project_id: 1,
                top_assembly_ctg_ids: vec![401],
                bottom_assembly_ctg_ids: vec![402],
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(track_report.evidence_source, "ds_ds_paf");
        assert_eq!(track_report.evidence_hit_count, 1);
        assert_eq!(track_report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(track_report.hits[0].query_source_seq_name, "tigA");
        assert_eq!(track_report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(track_report.hits[0].subject_source_seq_name, "tigB");
        assert_eq!(track_report.hits[0].query_start, 101);
        assert_eq!(track_report.hits[0].query_end, 300);
        assert_eq!(track_report.hits[0].subject_start, 1);
        assert_eq!(track_report.hits[0].subject_end, 200);
    }

    #[test]
    fn subview_pairwise_uses_add_ctg_run_for_derived_ctg_members() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(&workspace_root).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/chr_Chr01/add_ctg/flye_vs_gapfiller-t1"))
            .unwrap();

        fs::write(
            workspace_root.join("data/datasets/flye.fa"),
            ">ptg00002l\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/datasets/flye.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/datasets/derived_ctg.fa"),
            ">gapfiller-t1\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/datasets/derived_ctg.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("runs/chr_Chr01/add_ctg/flye_vs_gapfiller-t1/result.paf"),
            "gapfiller-t1\t1000\t10\t510\t+\tptg00002l\t1200\t100\t600\t490\t500\t60\n",
        )
        .unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root.join("data/reference/ref.fa.fai").to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'flye', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/flye.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/flye.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (2, 'derived_ctg', 'derived_ctg', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/derived_ctg.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/derived_ctg.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'ptg00002l', 1, 1200)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (201, 2, 'gapfiller-t1', 1, 1000)",
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
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 1, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (301, 1, 101, '+', 1, 1200, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (302, 1, 201, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (401, 1, 301, 'ptg00002l', 'Chr01', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (402, 1, 302, 'gapfiller-t1', 'Chr01', 2, 900, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        drop(conn);

        let junction_report = get_junction_inspection(
            &db_path,
            &GetJunctionInspectionParams {
                project_id: 1,
                left_assembly_ctg_id: 401,
                right_assembly_ctg_id: 402,
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(junction_report.evidence_source, "ds_ds_paf");
        assert_eq!(junction_report.evidence_hit_count, 1);
        assert_eq!(junction_report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(junction_report.hits[0].query_source_seq_name, "ptg00002l");
        assert_eq!(junction_report.hits[0].query_start, 101);
        assert_eq!(junction_report.hits[0].query_end, 600);
        assert_eq!(junction_report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(junction_report.hits[0].subject_source_seq_name, "gapfiller-t1");
        assert_eq!(junction_report.hits[0].subject_start, 11);
        assert_eq!(junction_report.hits[0].subject_end, 510);

        let track_report = get_track_pairwise_evidence(
            &db_path,
            &GetTrackPairwiseEvidenceParams {
                project_id: 1,
                top_assembly_ctg_ids: vec![401],
                bottom_assembly_ctg_ids: vec![402],
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(track_report.evidence_source, "ds_ds_paf");
        assert_eq!(track_report.evidence_hit_count, 1);
        assert_eq!(track_report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(track_report.hits[0].query_source_seq_name, "ptg00002l");
        assert_eq!(track_report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(track_report.hits[0].subject_source_seq_name, "gapfiller-t1");

        let reversed_track_report = get_track_pairwise_evidence(
            &db_path,
            &GetTrackPairwiseEvidenceParams {
                project_id: 1,
                top_assembly_ctg_ids: vec![402],
                bottom_assembly_ctg_ids: vec![401],
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(reversed_track_report.evidence_hit_count, 1);
        assert_eq!(reversed_track_report.hits[0].query_assembly_ctg_id, 402);
        assert_eq!(
            reversed_track_report.hits[0].query_source_seq_name,
            "gapfiller-t1"
        );
        assert_eq!(reversed_track_report.hits[0].subject_assembly_ctg_id, 401);
        assert_eq!(
            reversed_track_report.hits[0].subject_source_seq_name,
            "ptg00002l"
        );
    }

    #[test]
    fn junction_and_track_pairwise_evidence_use_display_coordinates_for_oriented_ctgs() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(&workspace_root).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/chr_Chr01/ds2_vs_ds1")).unwrap();

        fs::write(workspace_root.join("data/datasets/ds1.fa"), ">tigA\nACGT\n").unwrap();
        fs::write(workspace_root.join("data/datasets/ds1.fa.fai"), "").unwrap();
        fs::write(workspace_root.join("data/datasets/ds2.fa"), ">tigB\nACGT\n").unwrap();
        fs::write(workspace_root.join("data/datasets/ds2.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("runs/chr_Chr01/ds2_vs_ds1/result.paf"),
            "tigA\t1000\t100\t300\t+\ttigB\t1000\t400\t600\t190\t200\t60\n",
        )
        .unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root.join("data/reference/ref.fa.fai").to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/ds1.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds1.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (2, 'ds2', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/ds2.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds2.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 1000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (201, 2, 'tigB', 1, 1000)",
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
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 1, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (1, 2, 'support', 2)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (301, 1, 101, '-', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (302, 1, 201, '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (401, 1, 301, 'Ctg1', 'Chr01', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (402, 1, 302, 'Ctg2', 'Chr01', 2, 900, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        drop(conn);

        let junction_report = get_junction_inspection(
            &db_path,
            &GetJunctionInspectionParams {
                project_id: 1,
                left_assembly_ctg_id: 401,
                right_assembly_ctg_id: 402,
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();
        assert_eq!(junction_report.evidence_hit_count, 1);
        assert_eq!(junction_report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(junction_report.hits[0].query_start, 701);
        assert_eq!(junction_report.hits[0].query_end, 900);
        assert_eq!(junction_report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(junction_report.hits[0].subject_start, 401);
        assert_eq!(junction_report.hits[0].subject_end, 600);
        assert_eq!(junction_report.hits[0].strand, "-");

        let track_report = get_track_pairwise_evidence(
            &db_path,
            &GetTrackPairwiseEvidenceParams {
                project_id: 1,
                top_assembly_ctg_ids: vec![401],
                bottom_assembly_ctg_ids: vec![402],
                min_align_length: None,
                min_mapq: None,
            },
        )
        .unwrap();

        assert_eq!(track_report.evidence_hit_count, 1);
        assert_eq!(track_report.hits[0].query_assembly_ctg_id, 401);
        assert_eq!(track_report.hits[0].query_start, 701);
        assert_eq!(track_report.hits[0].query_end, 900);
        assert_eq!(track_report.hits[0].subject_assembly_ctg_id, 402);
        assert_eq!(track_report.hits[0].subject_start, 401);
        assert_eq!(track_report.hits[0].subject_end, 600);
        assert_eq!(track_report.hits[0].strand, "-");
    }

    #[test]
    fn pairwise_cache_reuses_indexed_hits_without_reparsing_missing_direction() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("runs/ds1_vs_ds2")).unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, 'ds1.fa', 'ds1.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (2, 'ds2', 'asm', NULL, 'ds2.fa', 'ds2.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (10, 1, 'ds1_a', 1, 1000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (20, 2, 'ds2_b', 1, 900)",
            [],
        )
        .unwrap();
        let paf_path = workspace_root.join("runs/ds1_vs_ds2/result.paf");
        fs::write(
            &paf_path,
            "ds1_a\t1000\t99\t399\t+\tds2_b\t900\t9\t309\t290\t300\t60\n",
        )
        .unwrap();

        let run =
            ensure_pairwise_alignment_run_cache(&mut conn, 1, 2, "ds1_vs_ds2", &paf_path).unwrap();
        let hits =
            query_pairwise_cached_hits(&conn, run.id, &[20], &[10], 100, 0, "ds_ds_paf").unwrap();

        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].query_source_seq_id, 20);
        assert_eq!(hits[0].query_source_seq_name, "ds2_b");
        assert_eq!(hits[0].query_start, 10);
        assert_eq!(hits[0].query_end, 309);
        assert_eq!(hits[0].subject_source_seq_id, 10);
        assert_eq!(hits[0].subject_source_seq_name, "ds1_a");
        assert_eq!(hits[0].subject_start, 100);
        assert_eq!(hits[0].subject_end, 399);
    }
}
