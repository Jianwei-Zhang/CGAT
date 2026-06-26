use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use crate::db::open_workspace_db;

const DEFAULT_CHR_GAP_BP: i64 = 100;
const DEFAULT_END_GAP_BP: i64 = 100;
const FASTA_WRAP_WIDTH: usize = 80;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportCtgFastaParams {
    pub chr_name: Option<String>,
    pub assembly_ctg_id: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportChrFastaParams {
    pub chr_name: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportCtgAgpParams {
    pub chr_name: Option<String>,
    pub assembly_ctg_id: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportChrAgpParams {
    pub chr_name: Option<String>,
    pub element: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ListExportRecordsParams {
    pub limit: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FinalPathExportSegment {
    Ctg {
        assembly_ctg_id: i64,
        start: i64,
        end: i64,
    },
    RefSegment {
        reference_chr_name: String,
        member_start_bp: i64,
        member_end_bp: i64,
        start: i64,
        end: i64,
    },
    Gap {
        gap_size_bp: i64,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportFinalPathFastaParams {
    pub chr_name: String,
    pub output_path: PathBuf,
    pub final_path_segments: Vec<FinalPathExportSegment>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FinalPathFastaRecord {
    pub chr_name: String,
    pub final_path_segments: Vec<FinalPathExportSegment>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportProjectFinalPathFastaParams {
    pub output_path: PathBuf,
    pub records: Vec<FinalPathFastaRecord>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FinalPathExportSummary {
    pub output_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportSummary {
    pub project_id: i64,
    pub export_type: String,
    pub output_path: PathBuf,
    pub record_id: i64,
    pub record_count: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportRecordItem {
    pub id: i64,
    pub project_id: i64,
    pub export_type: String,
    pub reference_chr_id: Option<i64>,
    pub assembly_ctg_id: Option<i64>,
    pub output_path: String,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CtgExportModel {
    id: i64,
    name: String,
    assigned_chr_name: Option<String>,
    chr_order: Option<i64>,
    anchor_start: Option<i64>,
    ref_orient: Option<String>,
    members: Vec<CtgMemberModel>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CtgMemberModel {
    member_order: i64,
    source_seq_id: i64,
    source_seq_name: String,
    orient: String,
    source_start: i64,
    source_end: i64,
    hidden: bool,
    left_end_type: String,
    right_end_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum CtgChunk {
    Gap {
        length: i64,
        gap_type: &'static str,
    },
    Sequence {
        component_id: String,
        component_start: i64,
        component_end: i64,
        orient: String,
        sequence: String,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ChrAgpElement {
    Seq,
    Ctg,
}

impl ChrAgpElement {
    fn parse(input: &str) -> Result<Self> {
        match input.trim().to_ascii_lowercase().as_str() {
            "seq" => Ok(Self::Seq),
            "ctg" => Ok(Self::Ctg),
            other => bail!("unsupported chr agp element: {}", other),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Seq => "seq",
            Self::Ctg => "ctg",
        }
    }
}

pub fn export_ctg_fasta(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportCtgFastaParams,
) -> Result<ExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_ctg_fasta_with_connection(&mut conn, project_db_path, project_id, params)
}

pub fn export_chr_fasta(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportChrFastaParams,
) -> Result<ExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_chr_fasta_with_connection(&mut conn, project_db_path, project_id, params)
}

pub fn export_ctg_agp(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportCtgAgpParams,
) -> Result<ExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_ctg_agp_with_connection(&mut conn, project_db_path, project_id, params)
}

pub fn export_chr_agp(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportChrAgpParams,
) -> Result<ExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_chr_agp_with_connection(&mut conn, project_db_path, project_id, params)
}

pub fn list_export_records(
    project_db_path: &Path,
    project_id: i64,
    params: &ListExportRecordsParams,
) -> Result<Vec<ExportRecordItem>> {
    let conn = open_workspace_db(project_db_path)?;
    list_export_records_with_connection(&conn, project_id, params)
}

pub fn export_final_path_fasta(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportFinalPathFastaParams,
) -> Result<FinalPathExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_final_path_fasta_with_connection(&mut conn, project_db_path, project_id, params)
}

pub fn export_project_final_path_fasta(
    project_db_path: &Path,
    project_id: i64,
    params: &ExportProjectFinalPathFastaParams,
) -> Result<FinalPathExportSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    export_project_final_path_fasta_with_connection(&mut conn, project_db_path, project_id, params)
}

fn export_ctg_fasta_with_connection(
    conn: &mut Connection,
    project_db_path: &Path,
    project_id: i64,
    params: &ExportCtgFastaParams,
) -> Result<ExportSummary> {
    validate_project_exists(conn, project_id)?;
    let ctgs = load_ctg_models(
        conn,
        project_id,
        params.chr_name.as_deref(),
        params.assembly_ctg_id,
        false,
    )?;
    if ctgs.is_empty() {
        bail!("no contigs matched export scope");
    }

    let source_sequences = load_required_source_sequences(conn, &ctgs)?;
    let mut records = Vec::<(String, String)>::new();
    for ctg in &ctgs {
        let chunks = build_ctg_chunks(ctg, &source_sequences)?;
        if chunks.is_empty() {
            continue;
        }
        let sequence = chunks_to_sequence(&chunks);
        if sequence.is_empty() {
            continue;
        }
        records.push((ctg.name.clone(), sequence));
    }
    if records.is_empty() {
        bail!("no non-empty contig sequence found in export scope");
    }

    let project_name = load_project_name(conn, project_id)?;
    let preferred_file_name =
        if params.assembly_ctg_id.is_some() && records.len() == 1 && ctgs.len() == 1 {
            format!("assemblyCtg{}.{}.seq", ctgs[0].id, ctgs[0].name)
        } else {
            format!(
                "assembly{}.{}.{}.ctg.seq",
                project_id,
                project_name,
                params.chr_name.as_deref().unwrap_or("all")
            )
        };
    let output_path =
        build_export_output_path_named(project_db_path, project_id, &preferred_file_name)?;
    write_fasta_records(&output_path, &records)?;
    let record_id = insert_export_record(
        conn,
        project_id,
        "ctg_fasta",
        resolve_reference_chr_id(conn, project_id, params.chr_name.as_deref())?,
        params.assembly_ctg_id,
        &output_path,
        None,
    )?;

    Ok(ExportSummary {
        project_id,
        export_type: "ctg_fasta".to_string(),
        output_path,
        record_id,
        record_count: records.len() as i64,
    })
}

fn export_chr_fasta_with_connection(
    conn: &mut Connection,
    project_db_path: &Path,
    project_id: i64,
    params: &ExportChrFastaParams,
) -> Result<ExportSummary> {
    validate_project_exists(conn, project_id)?;
    let ctgs = load_ctg_models(conn, project_id, params.chr_name.as_deref(), None, false)?;
    if ctgs.is_empty() {
        bail!("no contigs matched export scope");
    }

    let source_sequences = load_required_source_sequences(conn, &ctgs)?;
    let (chr_groups, unplaced_ctgs) = split_ctgs_by_placement(ctgs);
    let mut records = Vec::<(String, String)>::new();
    for (chr_name, chr_ctgs) in chr_groups {
        let merged_chunks = merge_ctg_chunks_for_chr(&chr_ctgs, &source_sequences)?;
        let chr_sequence = chunks_to_sequence(&merged_chunks);
        if !chr_sequence.is_empty() {
            records.push((chr_name, chr_sequence));
        }
    }
    if params.chr_name.is_none() {
        for ctg in unplaced_ctgs {
            let chunks = build_ctg_chunks(&ctg, &source_sequences)?;
            let seq = chunks_to_sequence(&chunks);
            if seq.is_empty() {
                continue;
            }
            records.push((chr_un_object_name(&ctg), seq));
        }
    }
    if records.is_empty() {
        bail!("no chromosome sequence generated");
    }

    let project_name = load_project_name(conn, project_id)?;
    let preferred_file_name = format!(
        "assembly{}.{}.{}.chr.seq",
        project_id,
        project_name,
        params.chr_name.as_deref().unwrap_or("all")
    );
    let output_path =
        build_export_output_path_named(project_db_path, project_id, &preferred_file_name)?;
    write_fasta_records(&output_path, &records)?;
    let record_id = insert_export_record(
        conn,
        project_id,
        "chr_fasta",
        resolve_reference_chr_id(conn, project_id, params.chr_name.as_deref())?,
        None,
        &output_path,
        None,
    )?;

    Ok(ExportSummary {
        project_id,
        export_type: "chr_fasta".to_string(),
        output_path,
        record_id,
        record_count: records.len() as i64,
    })
}

fn export_final_path_fasta_with_connection(
    conn: &mut Connection,
    _project_db_path: &Path,
    project_id: i64,
    params: &ExportFinalPathFastaParams,
) -> Result<FinalPathExportSummary> {
    validate_project_exists(conn, project_id)?;
    let chr_name = params.chr_name.trim();
    if chr_name.is_empty() {
        bail!("chr_name is required for final-path fasta export");
    }
    let output_path = params.output_path.clone();
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    let records = build_final_path_fasta_records(
        conn,
        project_id,
        &[FinalPathFastaRecord {
            chr_name: chr_name.to_string(),
            final_path_segments: params.final_path_segments.clone(),
        }],
    )?;

    write_fasta_records(&output_path, &records)?;
    Ok(FinalPathExportSummary { output_path })
}

fn export_project_final_path_fasta_with_connection(
    conn: &mut Connection,
    _project_db_path: &Path,
    project_id: i64,
    params: &ExportProjectFinalPathFastaParams,
) -> Result<FinalPathExportSummary> {
    validate_project_exists(conn, project_id)?;
    if params.records.is_empty() {
        bail!("at least one final-path fasta record is required");
    }
    let mut seen_chr_names = BTreeSet::<String>::new();
    for record in &params.records {
        let chr_name = record.chr_name.trim();
        if chr_name.is_empty() {
            bail!("chr_name is required for project final-path fasta export");
        }
        if !seen_chr_names.insert(chr_name.to_string()) {
            bail!(
                "duplicate chr_name {} in project final-path fasta export",
                chr_name
            );
        }
    }
    let output_path = params.output_path.clone();
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    let records = build_final_path_fasta_records(conn, project_id, &params.records)?;
    write_fasta_records(&output_path, &records)?;
    Ok(FinalPathExportSummary { output_path })
}

fn build_final_path_fasta_records(
    conn: &Connection,
    project_id: i64,
    records: &[FinalPathFastaRecord],
) -> Result<Vec<(String, String)>> {
    let mut required_ctg_ids = BTreeSet::<i64>::new();
    let mut required_reference_chr_names = BTreeSet::<String>::new();
    for record in records {
        for segment in &record.final_path_segments {
            match segment {
                FinalPathExportSegment::Ctg {
                    assembly_ctg_id, ..
                } if *assembly_ctg_id > 0 => {
                    required_ctg_ids.insert(*assembly_ctg_id);
                }
                FinalPathExportSegment::RefSegment {
                    reference_chr_name, ..
                } if !reference_chr_name.trim().is_empty() => {
                    required_reference_chr_names.insert(reference_chr_name.trim().to_string());
                }
                _ => {}
            }
        }
    }
    let ctg_models = load_ctg_models(conn, project_id, None, None, false)?;
    let required_ctgs = ctg_models
        .iter()
        .filter(|ctg| required_ctg_ids.contains(&ctg.id))
        .cloned()
        .collect::<Vec<_>>();
    let ctg_by_id = required_ctgs
        .iter()
        .map(|ctg| (ctg.id, ctg.clone()))
        .collect::<HashMap<_, _>>();
    let source_sequences = load_required_source_sequences(conn, &required_ctgs)?;
    let reference_sequences =
        load_required_reference_sequences(conn, project_id, &required_reference_chr_names)?;

    records
        .iter()
        .map(|record| {
            Ok((
                record.chr_name.trim().to_string(),
                build_final_path_sequence(
                    &record.final_path_segments,
                    &ctg_by_id,
                    &source_sequences,
                    &reference_sequences,
                )?,
            ))
        })
        .collect()
}

fn build_final_path_sequence(
    segments: &[FinalPathExportSegment],
    ctg_by_id: &HashMap<i64, CtgExportModel>,
    source_sequences: &HashMap<i64, String>,
    reference_sequences: &HashMap<String, String>,
) -> Result<String> {
    let mut final_sequence = String::new();
    for segment in segments {
        match segment {
            FinalPathExportSegment::Gap { gap_size_bp } => {
                if *gap_size_bp > 0 {
                    final_sequence.push_str(&"N".repeat(*gap_size_bp as usize));
                }
            }
            FinalPathExportSegment::Ctg {
                assembly_ctg_id,
                start,
                end,
            } => {
                let ctg = ctg_by_id.get(assembly_ctg_id).ok_or_else(|| {
                    anyhow::anyhow!("assembly_ctg_id {} not found", assembly_ctg_id)
                })?;
                let source_aligned = build_final_path_ctg_source_sequence(ctg, source_sequences)?;
                if source_aligned.is_empty() {
                    continue;
                }
                let normalized_start = (*start).min(*end);
                let normalized_end = (*start).max(*end);
                if normalized_start <= 0 || normalized_end <= 0 {
                    bail!(
                        "final-path contig range must be positive for assembly_ctg_id {}",
                        assembly_ctg_id
                    );
                }
                if normalized_end as usize > source_aligned.len() {
                    bail!(
                        "final-path contig range {}..{} exceeds ctg {} length {}",
                        start,
                        end,
                        assembly_ctg_id,
                        source_aligned.len()
                    );
                }
                let slice =
                    &source_aligned[(normalized_start as usize - 1)..(normalized_end as usize)];
                if start <= end {
                    final_sequence.push_str(slice);
                } else {
                    final_sequence.push_str(&reverse_complement(slice));
                }
            }
            FinalPathExportSegment::RefSegment {
                reference_chr_name,
                member_start_bp,
                member_end_bp,
                start,
                end,
            } => {
                let reference_sequence = reference_sequences
                    .get(reference_chr_name.trim())
                    .ok_or_else(|| {
                        anyhow::anyhow!("reference chr {} not found", reference_chr_name)
                    })?;
                if *member_start_bp <= 0 || *member_end_bp <= 0 || member_end_bp < member_start_bp {
                    bail!(
                        "final-path ref segment member range must be positive: {}..{}",
                        member_start_bp,
                        member_end_bp
                    );
                }
                if *member_end_bp as usize > reference_sequence.len() {
                    bail!(
                        "final-path ref segment member range {}..{} exceeds reference chr {} length {}",
                        member_start_bp,
                        member_end_bp,
                        reference_chr_name,
                        reference_sequence.len()
                    );
                }
                let member_len = member_end_bp - member_start_bp + 1;
                let normalized_start = (*start).min(*end);
                let normalized_end = (*start).max(*end);
                if normalized_start <= 0 || normalized_end <= 0 {
                    bail!(
                        "final-path ref segment range must be positive for {}",
                        reference_chr_name
                    );
                }
                if normalized_end > member_len {
                    bail!(
                        "final-path ref segment range {}..{} exceeds member length {} for {}",
                        start,
                        end,
                        member_len,
                        reference_chr_name
                    );
                }
                let absolute_start = member_start_bp + normalized_start - 1;
                let absolute_end = member_start_bp + normalized_end - 1;
                let slice =
                    &reference_sequence[(absolute_start as usize - 1)..(absolute_end as usize)];
                if start <= end {
                    final_sequence.push_str(slice);
                } else {
                    final_sequence.push_str(&reverse_complement(slice));
                }
            }
        }
    }
    Ok(final_sequence)
}

fn build_final_path_ctg_source_sequence(
    ctg: &CtgExportModel,
    source_sequences: &HashMap<i64, String>,
) -> Result<String> {
    let mut sequence = String::new();
    for member in ctg.members.iter().filter(|member| !member.hidden) {
        let source = source_sequences
            .get(&member.source_seq_id)
            .ok_or_else(|| anyhow::anyhow!("missing source sequence {}", member.source_seq_id))?;
        // Final path row orientation is relative to the original source sequence.
        sequence.push_str(&slice_and_orient(
            source,
            member.source_start,
            member.source_end,
            "+",
        )?);
    }
    Ok(sequence)
}

fn export_ctg_agp_with_connection(
    conn: &mut Connection,
    project_db_path: &Path,
    project_id: i64,
    params: &ExportCtgAgpParams,
) -> Result<ExportSummary> {
    validate_project_exists(conn, project_id)?;
    let ctgs = load_ctg_models(
        conn,
        project_id,
        params.chr_name.as_deref(),
        params.assembly_ctg_id,
        false,
    )?;
    if ctgs.is_empty() {
        bail!("no contigs matched export scope");
    }
    let source_sequences = load_required_source_sequences(conn, &ctgs)?;

    let mut lines = vec!["##agp-version 2.0".to_string()];
    let mut object_count = 0_i64;
    for ctg in &ctgs {
        let chunks = build_ctg_chunks(ctg, &source_sequences)?;
        let rows = chunks_to_agp_rows(&ctg.name, &chunks);
        if rows.is_empty() {
            continue;
        }
        lines.extend(rows);
        object_count += 1;
    }
    if object_count == 0 {
        bail!("no contig agp rows generated");
    }

    let project_name = load_project_name(conn, project_id)?;
    let preferred_file_name =
        if params.assembly_ctg_id.is_some() && object_count == 1 && ctgs.len() == 1 {
            format!("{}.agp", ctgs[0].name)
        } else {
            format!(
                "assembly{}.{}.{}.ctg-seq.agp",
                project_id,
                project_name,
                params.chr_name.as_deref().unwrap_or("all")
            )
        };
    let output_path =
        build_export_output_path_named(project_db_path, project_id, &preferred_file_name)?;
    fs::write(&output_path, format!("{}\n", lines.join("\n")))
        .with_context(|| format!("failed to write {}", output_path.display()))?;
    let record_id = insert_export_record(
        conn,
        project_id,
        "ctg_agp",
        resolve_reference_chr_id(conn, project_id, params.chr_name.as_deref())?,
        params.assembly_ctg_id,
        &output_path,
        None,
    )?;

    Ok(ExportSummary {
        project_id,
        export_type: "ctg_agp".to_string(),
        output_path,
        record_id,
        record_count: object_count,
    })
}

fn export_chr_agp_with_connection(
    conn: &mut Connection,
    project_db_path: &Path,
    project_id: i64,
    params: &ExportChrAgpParams,
) -> Result<ExportSummary> {
    validate_project_exists(conn, project_id)?;
    let element = ChrAgpElement::parse(&params.element)?;
    let ctgs = load_ctg_models(conn, project_id, params.chr_name.as_deref(), None, false)?;
    if ctgs.is_empty() {
        bail!("no contigs matched export scope");
    }
    let source_sequences = load_required_source_sequences(conn, &ctgs)?;
    let (chr_groups, unplaced_ctgs) = split_ctgs_by_placement(ctgs);

    let mut lines = vec!["##agp-version 2.0".to_string()];
    let mut object_count = 0_i64;
    match element {
        ChrAgpElement::Ctg => {
            for (chr_name, chr_ctgs) in chr_groups {
                let mut begin = 1_i64;
                let mut part = 1_i64;
                let mut has_component = false;
                for (index, ctg) in chr_ctgs.iter().enumerate() {
                    let chunks = build_ctg_chunks(ctg, &source_sequences)?;
                    let ctg_len = chunks_total_length(&chunks);
                    if ctg_len <= 0 {
                        continue;
                    }
                    if index > 0 && has_component {
                        lines.push(format!(
                            "{}\t{}\t{}\t{}\tU\t{}\tcontig\tno\tna",
                            chr_name,
                            begin,
                            begin + DEFAULT_CHR_GAP_BP - 1,
                            part,
                            DEFAULT_CHR_GAP_BP
                        ));
                        begin += DEFAULT_CHR_GAP_BP;
                        part += 1;
                    }
                    let orient = ctg
                        .ref_orient
                        .as_deref()
                        .filter(|value| *value == "+" || *value == "-")
                        .unwrap_or("+");
                    lines.push(format!(
                        "{}\t{}\t{}\t{}\tW\t{}\t1\t{}\t{}",
                        chr_name,
                        begin,
                        begin + ctg_len - 1,
                        part,
                        ctg.name,
                        ctg_len,
                        orient
                    ));
                    begin += ctg_len;
                    part += 1;
                    has_component = true;
                }
                if has_component {
                    object_count += 1;
                }
            }
            if params.chr_name.is_none() {
                for ctg in unplaced_ctgs {
                    let chunks = build_ctg_chunks(&ctg, &source_sequences)?;
                    let ctg_len = chunks_total_length(&chunks);
                    if ctg_len <= 0 {
                        continue;
                    }
                    let orient = ctg
                        .ref_orient
                        .as_deref()
                        .filter(|value| *value == "+" || *value == "-")
                        .unwrap_or("+");
                    lines.push(format!(
                        "{}\t1\t{}\t1\tW\t{}\t1\t{}\t{}",
                        chr_un_object_name(&ctg),
                        ctg_len,
                        ctg.name,
                        ctg_len,
                        orient
                    ));
                    object_count += 1;
                }
            }
        }
        ChrAgpElement::Seq => {
            for (chr_name, chr_ctgs) in chr_groups {
                let merged_chunks = merge_ctg_chunks_for_chr(&chr_ctgs, &source_sequences)?;
                let rows = chunks_to_agp_rows(&chr_name, &merged_chunks);
                if rows.is_empty() {
                    continue;
                }
                lines.extend(rows);
                object_count += 1;
            }
            if params.chr_name.is_none() {
                for ctg in unplaced_ctgs {
                    let chunks = build_ctg_chunks(&ctg, &source_sequences)?;
                    let rows = chunks_to_agp_rows(&chr_un_object_name(&ctg), &chunks);
                    if rows.is_empty() {
                        continue;
                    }
                    lines.extend(rows);
                    object_count += 1;
                }
            }
        }
    }
    if object_count == 0 {
        bail!("no chromosome agp rows generated");
    }

    let project_name = load_project_name(conn, project_id)?;
    let preferred_file_name = format!(
        "assembly{}.{}.{}.chr-{}.agp",
        project_id,
        project_name,
        params.chr_name.as_deref().unwrap_or("all"),
        element.as_str()
    );
    let output_path =
        build_export_output_path_named(project_db_path, project_id, &preferred_file_name)?;
    fs::write(&output_path, format!("{}\n", lines.join("\n")))
        .with_context(|| format!("failed to write {}", output_path.display()))?;
    let record_id = insert_export_record(
        conn,
        project_id,
        "chr_agp",
        resolve_reference_chr_id(conn, project_id, params.chr_name.as_deref())?,
        None,
        &output_path,
        None,
    )?;

    Ok(ExportSummary {
        project_id,
        export_type: "chr_agp".to_string(),
        output_path,
        record_id,
        record_count: object_count,
    })
}

fn list_export_records_with_connection(
    conn: &Connection,
    project_id: i64,
    params: &ListExportRecordsParams,
) -> Result<Vec<ExportRecordItem>> {
    if params.limit <= 0 {
        bail!("limit must be > 0");
    }
    let mut stmt = conn.prepare(
        "SELECT
            id,
            project_id,
            export_type,
            reference_chr_id,
            assembly_ctg_id,
            output_path,
            created_at,
            note
         FROM export_record
         WHERE project_id = ?1
         ORDER BY id DESC
         LIMIT ?2",
    )?;
    let rows = stmt
        .query_map(params![project_id, params.limit], |row| {
            Ok(ExportRecordItem {
                id: row.get(0)?,
                project_id: row.get(1)?,
                export_type: row.get(2)?,
                reference_chr_id: row.get(3)?,
                assembly_ctg_id: row.get(4)?,
                output_path: row.get(5)?,
                created_at: row.get(6)?,
                note: row.get(7)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(rows)
}

fn validate_project_exists(conn: &Connection, project_id: i64) -> Result<()> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    conn.query_row(
        "SELECT id FROM project WHERE id = ?1",
        params![project_id],
        |_| Ok(()),
    )
    .optional()?
    .ok_or_else(|| anyhow::anyhow!("project_id {} does not exist", project_id))?;
    Ok(())
}

fn load_ctg_models(
    conn: &Connection,
    project_id: i64,
    chr_name: Option<&str>,
    assembly_ctg_id: Option<i64>,
    only_placed: bool,
) -> Result<Vec<CtgExportModel>> {
    if let Some(value) = assembly_ctg_id
        && value <= 0
    {
        bail!("assembly_ctg_id must be > 0");
    }
    let mut sql = String::from(
        "SELECT id, name, assigned_chr_name, chr_order, anchor_start, ref_orient
         FROM assembly_ctg
         WHERE project_id = ?1",
    );
    if only_placed {
        sql.push_str(" AND assigned_chr_name IS NOT NULL AND assigned_chr_name != ''");
    }
    if chr_name.is_some() {
        sql.push_str(" AND assigned_chr_name = ?2");
    }
    match (chr_name, assembly_ctg_id) {
        (Some(_), Some(_)) => sql.push_str(" AND id = ?3"),
        (None, Some(_)) => sql.push_str(" AND id = ?2"),
        _ => {}
    }
    sql.push_str(
        " ORDER BY
            CASE WHEN assigned_chr_name IS NULL OR assigned_chr_name = '' THEN 1 ELSE 0 END,
            assigned_chr_name,
            chr_order,
            anchor_start,
            id",
    );
    let mut stmt = conn.prepare(&sql)?;
    let heads = match (chr_name, assembly_ctg_id) {
        (Some(chr), Some(ctg_id)) => {
            stmt.query_map(params![project_id, chr, ctg_id], decode_ctg_head_row)
        }
        (Some(chr), None) => stmt.query_map(params![project_id, chr], decode_ctg_head_row),
        (None, Some(ctg_id)) => stmt.query_map(params![project_id, ctg_id], decode_ctg_head_row),
        (None, None) => stmt.query_map(params![project_id], decode_ctg_head_row),
    }?
    .collect::<std::result::Result<Vec<_>, _>>()?;

    let mut ctgs = heads;
    let mut member_stmt = conn.prepare(
        "SELECT
            1 AS member_order,
            s.source_seq_id,
            ss.seq_name,
            s.orient,
            s.source_start,
            s.source_end,
            s.hidden,
            s.left_end_type,
            s.right_end_type
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         JOIN source_seq ss ON ss.id = s.source_seq_id
         WHERE c.id = ?1
         ORDER BY c.id",
    )?;
    for ctg in &mut ctgs {
        let members = member_stmt
            .query_map(params![ctg.id], |row| {
                Ok(CtgMemberModel {
                    member_order: row.get(0)?,
                    source_seq_id: row.get(1)?,
                    source_seq_name: row.get(2)?,
                    orient: row.get(3)?,
                    source_start: row.get(4)?,
                    source_end: row.get(5)?,
                    hidden: row.get::<_, i64>(6)? > 0,
                    left_end_type: row.get(7)?,
                    right_end_type: row.get(8)?,
                })
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        ctg.members = members;
    }

    Ok(ctgs)
}

fn decode_ctg_head_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<CtgExportModel> {
    Ok(CtgExportModel {
        id: row.get(0)?,
        name: row.get(1)?,
        assigned_chr_name: row.get(2)?,
        chr_order: row.get(3)?,
        anchor_start: row.get(4)?,
        ref_orient: row.get(5)?,
        members: Vec::new(),
    })
}

fn load_required_source_sequences(
    conn: &Connection,
    ctgs: &[CtgExportModel],
) -> Result<HashMap<i64, String>> {
    let needed_source_ids = ctgs
        .iter()
        .flat_map(|ctg| ctg.members.iter())
        .filter(|member| !member.hidden)
        .map(|member| member.source_seq_id)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    if needed_source_ids.is_empty() {
        return Ok(HashMap::new());
    }
    let mut meta_stmt = conn.prepare(
        "SELECT ss.id, ss.seq_name, ssl.fasta_path
         FROM source_seq ss
         LEFT JOIN source_seq_locator ssl ON ssl.source_seq_id = ss.id
         WHERE ss.id = ?1",
    )?;
    let mut path_to_name_to_id = BTreeMap::<String, HashMap<String, i64>>::new();
    for source_seq_id in needed_source_ids {
        let (source_id, seq_name, locator_fasta_path): (i64, String, Option<String>) = meta_stmt
            .query_row(params![source_seq_id], |row| {
                Ok((row.get(0)?, row.get(1)?, row.get(2)?))
            })
            .with_context(|| format!("source_seq_id {} does not exist", source_seq_id))?;
        let fasta_path = locator_fasta_path.ok_or_else(|| {
            anyhow::anyhow!("missing source sequence locator for {}", source_seq_id)
        })?;
        path_to_name_to_id
            .entry(fasta_path)
            .or_default()
            .insert(seq_name, source_id);
    }

    let mut source_sequences = HashMap::<i64, String>::new();
    for (fasta_path, name_to_id) in path_to_name_to_id {
        let names = name_to_id.keys().cloned().collect::<HashSet<_>>();
        let loaded = load_named_sequences_from_fasta(Path::new(&fasta_path), &names)?;
        for (name, sequence) in loaded {
            if let Some(source_id) = name_to_id.get(&name).copied() {
                source_sequences.insert(source_id, sequence);
            }
        }
    }
    Ok(source_sequences)
}

fn load_required_reference_sequences(
    conn: &Connection,
    project_id: i64,
    chr_names: &BTreeSet<String>,
) -> Result<HashMap<String, String>> {
    if chr_names.is_empty() {
        return Ok(HashMap::new());
    }
    let mut stmt = conn.prepare(
        "SELECT rc.chr_name, rcl.fasta_path
         FROM project p
         JOIN reference_chr rc ON rc.reference_genome_id = p.reference_genome_id
         LEFT JOIN reference_chr_locator rcl ON rcl.reference_chr_id = rc.id
         WHERE p.id = ?1
           AND rc.chr_name = ?2",
    )?;
    let mut path_to_names = BTreeMap::<String, HashSet<String>>::new();
    for chr_name in chr_names {
        let (resolved_chr_name, locator_fasta_path): (String, Option<String>) = stmt
            .query_row(params![project_id, chr_name], |row| {
                Ok((row.get(0)?, row.get(1)?))
            })
            .with_context(|| {
                format!(
                    "project_id {} is missing reference chr {}",
                    project_id, chr_name
                )
            })?;
        let fasta_path = locator_fasta_path.ok_or_else(|| {
            anyhow::anyhow!("missing reference chr locator for {}", resolved_chr_name)
        })?;
        path_to_names
            .entry(fasta_path)
            .or_default()
            .insert(resolved_chr_name);
    }

    let mut reference_sequences = HashMap::<String, String>::new();
    for (fasta_path, names) in path_to_names {
        let loaded = load_named_sequences_from_fasta(Path::new(&fasta_path), &names)?;
        for (name, sequence) in loaded {
            reference_sequences.insert(name, sequence);
        }
    }
    Ok(reference_sequences)
}

fn build_ctg_chunks(
    ctg: &CtgExportModel,
    source_sequences: &HashMap<i64, String>,
) -> Result<Vec<CtgChunk>> {
    let visible = ctg
        .members
        .iter()
        .filter(|member| !member.hidden)
        .collect::<Vec<_>>();
    if visible.is_empty() {
        return Ok(Vec::new());
    }

    let mut chunks = Vec::<CtgChunk>::new();
    if let Some(gap_type) = end_type_to_gap_type(&visible[0].left_end_type) {
        chunks.push(CtgChunk::Gap {
            length: DEFAULT_END_GAP_BP,
            gap_type,
        });
    }
    for member in visible.iter() {
        let source = source_sequences
            .get(&member.source_seq_id)
            .ok_or_else(|| anyhow::anyhow!("missing source sequence {}", member.source_seq_id))?;
        let seq = slice_and_orient(
            source,
            member.source_start,
            member.source_end,
            &member.orient,
        )?;
        chunks.push(CtgChunk::Sequence {
            component_id: member.source_seq_name.clone(),
            component_start: member.source_start,
            component_end: member.source_end,
            orient: member.orient.clone(),
            sequence: seq,
        });
    }
    if let Some(last) = visible.last()
        && let Some(gap_type) = end_type_to_gap_type(&last.right_end_type)
    {
        chunks.push(CtgChunk::Gap {
            length: DEFAULT_END_GAP_BP,
            gap_type,
        });
    }
    Ok(chunks)
}

fn end_type_to_gap_type(end_type: &str) -> Option<&'static str> {
    match end_type.trim().to_ascii_lowercase().as_str() {
        "gap" => Some("contig"),
        "telomere" => Some("telomere"),
        _ => None,
    }
}

fn slice_and_orient(source: &str, start: i64, end: i64, orient: &str) -> Result<String> {
    if start <= 0 || end <= 0 {
        bail!("source range must be positive: {}..{}", start, end);
    }
    if end < start {
        bail!("source range is invalid: {}..{}", start, end);
    }
    let bytes = source.as_bytes();
    if end as usize > bytes.len() {
        bail!(
            "source range {}..{} exceeds source length {}",
            start,
            end,
            bytes.len()
        );
    }
    let sub = &source[(start as usize - 1)..(end as usize)];
    match orient {
        "+" => Ok(sub.to_string()),
        "-" => Ok(reverse_complement(sub)),
        _ => bail!("unsupported orient {}", orient),
    }
}

fn reverse_complement(input: &str) -> String {
    input
        .chars()
        .rev()
        .map(|ch| match ch.to_ascii_uppercase() {
            'A' => 'T',
            'T' => 'A',
            'C' => 'G',
            'G' => 'C',
            'N' => 'N',
            other => other,
        })
        .collect::<String>()
}

fn chunks_to_sequence(chunks: &[CtgChunk]) -> String {
    let mut seq = String::new();
    for chunk in chunks {
        match chunk {
            CtgChunk::Gap { length, .. } => {
                if *length > 0 {
                    seq.push_str(&"N".repeat(*length as usize));
                }
            }
            CtgChunk::Sequence { sequence, .. } => seq.push_str(sequence),
        }
    }
    seq
}

fn chunks_total_length(chunks: &[CtgChunk]) -> i64 {
    chunks
        .iter()
        .map(|chunk| match chunk {
            CtgChunk::Gap { length, .. } => (*length).max(0),
            CtgChunk::Sequence { sequence, .. } => sequence.len() as i64,
        })
        .sum::<i64>()
}

fn chunks_to_agp_rows(object_name: &str, chunks: &[CtgChunk]) -> Vec<String> {
    let mut rows = Vec::<String>::new();
    let mut begin = 1_i64;
    let mut part = 1_i64;
    for chunk in chunks {
        match chunk {
            CtgChunk::Gap { length, gap_type } => {
                if *length <= 0 {
                    continue;
                }
                rows.push(format!(
                    "{}\t{}\t{}\t{}\tU\t{}\t{}\tno\tna",
                    object_name,
                    begin,
                    begin + *length - 1,
                    part,
                    length,
                    gap_type
                ));
                begin += *length;
            }
            CtgChunk::Sequence {
                component_id,
                component_start,
                component_end,
                orient,
                sequence,
            } => {
                let length = sequence.len() as i64;
                if length <= 0 {
                    continue;
                }
                rows.push(format!(
                    "{}\t{}\t{}\t{}\tW\t{}\t{}\t{}\t{}",
                    object_name,
                    begin,
                    begin + length - 1,
                    part,
                    component_id,
                    component_start,
                    component_end,
                    orient
                ));
                begin += length;
            }
        }
        part += 1;
    }
    rows
}

fn split_ctgs_by_placement(
    ctgs: Vec<CtgExportModel>,
) -> (BTreeMap<String, Vec<CtgExportModel>>, Vec<CtgExportModel>) {
    let mut groups = BTreeMap::<String, Vec<CtgExportModel>>::new();
    let mut unplaced = Vec::<CtgExportModel>::new();
    for ctg in ctgs {
        match ctg.assigned_chr_name.as_deref() {
            Some(chr_name) if !chr_name.trim().is_empty() => {
                groups.entry(chr_name.to_string()).or_default().push(ctg);
            }
            _ => unplaced.push(ctg),
        }
    }
    for items in groups.values_mut() {
        sort_ctg_models(items);
    }
    sort_ctg_models(&mut unplaced);
    (groups, unplaced)
}

fn sort_ctg_models(ctgs: &mut [CtgExportModel]) {
    ctgs.sort_by(|a, b| {
        a.chr_order
            .unwrap_or(i64::MAX)
            .cmp(&b.chr_order.unwrap_or(i64::MAX))
            .then_with(|| {
                a.anchor_start
                    .unwrap_or(i64::MAX)
                    .cmp(&b.anchor_start.unwrap_or(i64::MAX))
            })
            .then_with(|| a.id.cmp(&b.id))
    });
}

fn merge_ctg_chunks_for_chr(
    chr_ctgs: &[CtgExportModel],
    source_sequences: &HashMap<i64, String>,
) -> Result<Vec<CtgChunk>> {
    let mut merged = Vec::<CtgChunk>::new();
    let mut has_output = false;
    let mut last_component_is_gap = false;
    for ctg in chr_ctgs {
        let chunks = build_ctg_chunks(ctg, source_sequences)?;
        if chunks.is_empty() {
            continue;
        }
        if has_output && !last_component_is_gap {
            merged.push(CtgChunk::Gap {
                length: DEFAULT_CHR_GAP_BP,
                gap_type: "contig",
            });
            last_component_is_gap = true;
        }
        let start_index = if last_component_is_gap {
            chunks
                .iter()
                .take_while(|chunk| matches!(chunk, CtgChunk::Gap { .. }))
                .count()
        } else {
            0
        };
        for chunk in chunks.into_iter().skip(start_index) {
            last_component_is_gap = matches!(chunk, CtgChunk::Gap { .. });
            merged.push(chunk);
        }
        has_output = !merged.is_empty();
    }
    Ok(merged)
}

fn chr_un_object_name(ctg: &CtgExportModel) -> String {
    format!("ChrUN-{}", ctg.name)
}

fn write_fasta_records(output_path: &Path, records: &[(String, String)]) -> Result<()> {
    let mut file = File::create(output_path)
        .with_context(|| format!("failed to create {}", output_path.display()))?;
    for (header, sequence) in records {
        writeln!(file, ">{}", header)?;
        write_wrapped_sequence(&mut file, sequence, FASTA_WRAP_WIDTH)?;
    }
    Ok(())
}

fn write_wrapped_sequence(file: &mut File, sequence: &str, width: usize) -> Result<()> {
    if sequence.is_empty() {
        writeln!(file)?;
        return Ok(());
    }
    let mut offset = 0_usize;
    while offset < sequence.len() {
        let end = (offset + width).min(sequence.len());
        writeln!(file, "{}", &sequence[offset..end])?;
        offset = end;
    }
    Ok(())
}

fn build_export_output_path_named(
    project_db_path: &Path,
    project_id: i64,
    preferred_file_name: &str,
) -> Result<PathBuf> {
    let workspace_root = project_db_path.parent().ok_or_else(|| {
        anyhow::anyhow!(
            "failed to resolve workspace root from {}",
            project_db_path.display()
        )
    })?;
    let export_root = workspace_root
        .join("exports")
        .join(format!("project_{}", project_id));
    fs::create_dir_all(&export_root)
        .with_context(|| format!("failed to create {}", export_root.display()))?;
    let sanitized = sanitize_file_name(preferred_file_name);
    let mut candidate = export_root.join(&sanitized);
    if candidate.exists() {
        let timestamp = now_timestamp_string();
        let path = Path::new(&sanitized);
        let stem = path
            .file_stem()
            .and_then(|v| v.to_str())
            .unwrap_or("export");
        let ext = path
            .extension()
            .and_then(|v| v.to_str())
            .unwrap_or_default();
        let fallback_name = if ext.is_empty() {
            format!("{}_{}", stem, timestamp)
        } else {
            format!("{}_{}.{}", stem, timestamp, ext)
        };
        candidate = export_root.join(fallback_name);
    }
    Ok(candidate)
}

fn sanitize_file_name(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
}

fn load_project_name(conn: &Connection, project_id: i64) -> Result<String> {
    let project_name = conn.query_row(
        "SELECT name FROM project WHERE id = ?1",
        params![project_id],
        |row| row.get::<_, String>(0),
    )?;
    Ok(sanitize_file_name(&project_name))
}

fn insert_export_record(
    conn: &Connection,
    project_id: i64,
    export_type: &str,
    reference_chr_id: Option<i64>,
    assembly_ctg_id: Option<i64>,
    output_path: &Path,
    note: Option<&str>,
) -> Result<i64> {
    conn.execute(
        "INSERT INTO export_record (
            project_id,
            export_type,
            reference_chr_id,
            assembly_ctg_id,
            output_path,
            created_at,
            note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            project_id,
            export_type,
            reference_chr_id,
            assembly_ctg_id,
            output_path.to_string_lossy().to_string(),
            now_timestamp_string(),
            note.map(|value| value.to_string()),
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

fn resolve_reference_chr_id(
    conn: &Connection,
    project_id: i64,
    chr_name: Option<&str>,
) -> Result<Option<i64>> {
    let Some(chr_name) = chr_name else {
        return Ok(None);
    };
    let value = conn
        .query_row(
            "SELECT rc.id
             FROM project p
             JOIN reference_chr rc ON rc.reference_genome_id = p.reference_genome_id
             WHERE p.id = ?1
               AND rc.chr_name = ?2",
            params![project_id, chr_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    Ok(value)
}

fn now_timestamp_string() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    secs.to_string()
}

pub(crate) fn load_named_sequences_from_fasta(
    fasta_path: &Path,
    needed_names: &HashSet<String>,
) -> Result<HashMap<String, String>> {
    let file = File::open(fasta_path)
        .with_context(|| format!("failed to open fasta {}", fasta_path.display()))?;
    let reader = BufReader::new(file);

    let mut found = HashMap::<String, String>::new();
    let mut current_name: Option<String> = None;
    let mut current_seq = String::new();

    for line in reader.lines() {
        let line = line.with_context(|| format!("failed to read {}", fasta_path.display()))?;
        if let Some(rest) = line.strip_prefix('>') {
            if let Some(name) = current_name.take() {
                if needed_names.contains(&name) {
                    found.insert(name, std::mem::take(&mut current_seq));
                } else {
                    current_seq.clear();
                }
            }
            let seq_name = rest
                .split_whitespace()
                .next()
                .unwrap_or_default()
                .to_string();
            if needed_names.contains(&seq_name) {
                current_name = Some(seq_name);
            } else {
                current_name = None;
            }
            continue;
        }
        if current_name.is_some() {
            current_seq.push_str(line.trim());
        }
    }
    if let Some(name) = current_name.take()
        && needed_names.contains(&name)
    {
        found.insert(name, current_seq);
    }

    let missing = needed_names
        .iter()
        .filter(|name| !found.contains_key(*name))
        .cloned()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        bail!(
            "failed to find {} sequence(s) in fasta {}: {}",
            missing.len(),
            fasta_path.display(),
            missing.join(", ")
        );
    }
    Ok(found)
}

#[cfg(test)]
mod tests {
    use super::{
        ExportChrAgpParams, ExportChrFastaParams, ExportCtgAgpParams, ExportCtgFastaParams,
        ExportFinalPathFastaParams, ExportProjectFinalPathFastaParams, FinalPathExportSegment,
        FinalPathFastaRecord, ListExportRecordsParams, export_chr_agp_with_connection,
        export_chr_fasta_with_connection, export_ctg_agp_with_connection,
        export_ctg_fasta_with_connection, export_final_path_fasta_with_connection,
        export_project_final_path_fasta_with_connection, list_export_records_with_connection,
    };
    use crate::db::init_workspace_schema;
    use rusqlite::{Connection, params};
    use std::{
        fs,
        path::{Path, PathBuf},
    };
    use tempfile::tempdir;

    #[test]
    fn exports_fasta_agp_and_records_history() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();

        let ds_fa = workspace_root.join("data/datasets/ds.fa");
        fs::write(
            &ds_fa,
            ">tigA\nAAAAAA\n>tigB\nCCCCCC\n>tigC\nGGGGGG\n>tigD\nTTTTTT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/datasets/ds.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
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
             VALUES (1, 'ds', 'asm', NULL, ?1, ?2)",
            params![
                ds_fa.to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (101, 1, 'tigA', 1, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (102, 1, 'tigB', 2, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (103, 1, 'tigC', 3, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (104, 1, 'tigD', 4, 6)",
            [],
        )
        .unwrap();
        seed_source_seq_locators(&conn, &[101, 102, 103, 104], &ds_fa);
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
             VALUES (201, 1, 101, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (202, 1, 102, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (203, 1, 103, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (204, 1, 104, '-', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();

        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (302, 1, 202, 'Ctg2', 'Chr01', 2, 200, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (303, 1, 204, 'CtgUN1', NULL, NULL, NULL, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();

        let ctg_fa = export_ctg_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportCtgFastaParams {
                chr_name: Some("Chr01".to_string()),
                assembly_ctg_id: None,
            },
        )
        .unwrap();
        let ctg_fa_text = fs::read_to_string(&ctg_fa.output_path).unwrap();
        assert!(ctg_fa_text.contains(">Ctg1"));
        assert!(ctg_fa_text.contains("AAAA"));
        assert!(ctg_fa_text.contains("CCCC"));
        assert!(ctg_fa.output_path.to_string_lossy().ends_with(".ctg.seq"));

        let chr_fa = export_chr_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportChrFastaParams {
                chr_name: Some("Chr01".to_string()),
            },
        )
        .unwrap();
        let chr_fa_text = fs::read_to_string(&chr_fa.output_path).unwrap();
        assert!(chr_fa_text.contains(">Chr01"));
        let chr_fa_sequence = chr_fa_text
            .lines()
            .filter(|line| !line.starts_with('>'))
            .collect::<String>();
        assert!(chr_fa_sequence.contains(&"N".repeat(100)));
        assert!(chr_fa.output_path.to_string_lossy().ends_with(".chr.seq"));

        let chr_fa_all = export_chr_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportChrFastaParams { chr_name: None },
        )
        .unwrap();
        let chr_fa_all_text = fs::read_to_string(&chr_fa_all.output_path).unwrap();
        assert!(chr_fa_all_text.contains(">ChrUN-CtgUN1"));

        let ctg_agp = export_ctg_agp_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportCtgAgpParams {
                chr_name: Some("Chr01".to_string()),
                assembly_ctg_id: None,
            },
        )
        .unwrap();
        let ctg_agp_text = fs::read_to_string(&ctg_agp.output_path).unwrap();
        assert!(ctg_agp_text.contains("##agp-version 2.0"));
        assert!(!ctg_agp_text.contains("\tU\t2\tcontig\tno\tna"));
        assert!(
            ctg_agp
                .output_path
                .to_string_lossy()
                .ends_with(".ctg-seq.agp")
        );

        let chr_agp_ctg = export_chr_agp_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportChrAgpParams {
                chr_name: None,
                element: "ctg".to_string(),
            },
        )
        .unwrap();
        let chr_agp_ctg_text = fs::read_to_string(&chr_agp_ctg.output_path).unwrap();
        assert!(chr_agp_ctg_text.contains("##agp-version 2.0"));
        assert!(chr_agp_ctg_text.contains("\tW\tCtg1\t1\t4\t+"));
        assert!(chr_agp_ctg_text.contains("\tU\t100\tcontig\tno\tna"));
        assert!(chr_agp_ctg_text.contains("\tW\tCtg2\t1\t4\t+"));
        assert!(chr_agp_ctg_text.contains("ChrUN-CtgUN1\t1\t4\t1\tW\tCtgUN1\t1\t4\t+"));
        assert!(
            chr_agp_ctg
                .output_path
                .to_string_lossy()
                .ends_with(".chr-ctg.agp")
        );

        let chr_agp_seq = export_chr_agp_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportChrAgpParams {
                chr_name: None,
                element: "seq".to_string(),
            },
        )
        .unwrap();
        let chr_agp_seq_text = fs::read_to_string(&chr_agp_seq.output_path).unwrap();
        assert!(chr_agp_seq_text.contains("##agp-version 2.0"));
        assert!(chr_agp_seq_text.contains("\tW\ttigA\t1\t4\t+"));
        assert!(chr_agp_seq_text.contains("\tW\ttigB\t1\t4\t+"));
        assert!(chr_agp_seq_text.contains("\tU\t100\tcontig\tno\tna"));
        assert!(chr_agp_seq_text.contains("ChrUN-CtgUN1\t1\t4\t1\tW\ttigD\t1\t4\t-"));
        assert!(
            chr_agp_seq
                .output_path
                .to_string_lossy()
                .ends_with(".chr-seq.agp")
        );

        let records =
            list_export_records_with_connection(&conn, 1, &ListExportRecordsParams { limit: 20 })
                .unwrap();
        assert_eq!(records.len(), 6);
        assert!(records.iter().any(|row| row.export_type == "ctg_fasta"));
        assert!(records.iter().any(|row| row.export_type == "chr_fasta"));
        assert!(records.iter().any(|row| row.export_type == "ctg_agp"));
        assert!(records.iter().any(|row| row.export_type == "chr_agp"));
    }

    #[test]
    fn export_final_path_fasta_uses_current_segment_order_orientation_and_gap_ns() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();

        let ds_fa = workspace_root.join("data/datasets/ds.fa");
        fs::write(
            &ds_fa,
            ">tigA\nAAAAAA\n>tigB\nACGAAC\n>tigC\nGGGGGG\n>tigD\nTTTTTT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/datasets/ds.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nACGT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
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
             VALUES (1, 'ds', 'asm', NULL, ?1, ?2)",
            params![
                ds_fa.to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (101, 1, 'tigA', 1, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (102, 1, 'tigB', 2, 6)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length) VALUES (103, 1, 'tigC', 3, 6)",
            [],
        )
        .unwrap();
        seed_source_seq_locators(&conn, &[101, 102, 103], &ds_fa);
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
             VALUES (201, 1, 101, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (202, 1, 102, '-', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (203, 1, 103, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (302, 1, 202, 'Ctg2', 'Chr01', 2, 200, '-', 'manual', '1', NULL)",
            [],
        )
        .unwrap();

        let output_path = workspace_root.join("exports/final-path.fasta");
        fs::create_dir_all(output_path.parent().unwrap()).unwrap();
        let summary = export_final_path_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportFinalPathFastaParams {
                chr_name: "Chr01".to_string(),
                output_path: output_path.clone(),
                final_path_segments: vec![
                    FinalPathExportSegment::Ctg {
                        assembly_ctg_id: 301,
                        start: 1,
                        end: 4,
                    },
                    FinalPathExportSegment::Gap { gap_size_bp: 3 },
                    FinalPathExportSegment::Ctg {
                        assembly_ctg_id: 302,
                        start: 1,
                        end: 4,
                    },
                    FinalPathExportSegment::Ctg {
                        assembly_ctg_id: 302,
                        start: 4,
                        end: 1,
                    },
                ],
            },
        )
        .unwrap();

        let text = fs::read_to_string(&summary.output_path).unwrap();
        let sequence = text
            .lines()
            .filter(|line| !line.starts_with('>'))
            .collect::<String>();
        assert!(text.contains(">Chr01"));
        assert_eq!(sequence, "AAAANNNACGATCGT");
        assert_eq!(summary.output_path, output_path);

        let project_output_path = workspace_root.join("exports/project-final-path.fasta");
        let project_summary = export_project_final_path_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportProjectFinalPathFastaParams {
                output_path: project_output_path.clone(),
                records: vec![
                    FinalPathFastaRecord {
                        chr_name: "Chr01".to_string(),
                        final_path_segments: vec![
                            FinalPathExportSegment::Ctg {
                                assembly_ctg_id: 301,
                                start: 1,
                                end: 4,
                            },
                            FinalPathExportSegment::Gap { gap_size_bp: 3 },
                            FinalPathExportSegment::Ctg {
                                assembly_ctg_id: 302,
                                start: 1,
                                end: 4,
                            },
                            FinalPathExportSegment::Ctg {
                                assembly_ctg_id: 302,
                                start: 4,
                                end: 1,
                            },
                        ],
                    },
                    FinalPathFastaRecord {
                        chr_name: "Chr02".to_string(),
                        final_path_segments: vec![FinalPathExportSegment::Ctg {
                            assembly_ctg_id: 301,
                            start: 2,
                            end: 3,
                        }],
                    },
                ],
            },
        )
        .unwrap();

        let project_text = fs::read_to_string(&project_summary.output_path).unwrap();
        assert!(project_text.contains(">Chr01\nAAAANNNACGATCGT\n"));
        assert!(project_text.contains(">Chr02\nAA\n"));
        assert_eq!(project_summary.output_path, project_output_path);
    }

    #[test]
    fn export_final_path_fasta_supports_reference_segments() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();

        let ds_fa = workspace_root.join("data/datasets/ds.fa");
        fs::write(&ds_fa, ">tigA\nAAAAAA\n").unwrap();
        fs::write(workspace_root.join("data/datasets/ds.fa.fai"), "").unwrap();
        fs::write(
            workspace_root.join("data/reference/ref.fa"),
            ">Chr01\nAAAACCCCGGGGTTTT\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 16)",
            [],
        )
        .unwrap();
        seed_reference_chr_locator(&conn, 1, workspace_root.join("data/reference/ref.fa"));
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds', 'asm', NULL, ?1, ?2)",
            params![
                ds_fa.to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds.fa.fai")
                    .to_string_lossy()
            ],
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

        let output_path = workspace_root.join("exports/final-path-ref.fasta");
        fs::create_dir_all(output_path.parent().unwrap()).unwrap();
        let summary = export_final_path_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportFinalPathFastaParams {
                chr_name: "Chr01".to_string(),
                output_path: output_path.clone(),
                final_path_segments: vec![
                    FinalPathExportSegment::RefSegment {
                        reference_chr_name: "Chr01".to_string(),
                        member_start_bp: 5,
                        member_end_bp: 12,
                        start: 2,
                        end: 5,
                    },
                    FinalPathExportSegment::Gap { gap_size_bp: 2 },
                    FinalPathExportSegment::RefSegment {
                        reference_chr_name: "Chr01".to_string(),
                        member_start_bp: 5,
                        member_end_bp: 12,
                        start: 8,
                        end: 6,
                    },
                ],
            },
        )
        .unwrap();

        let text = fs::read_to_string(&summary.output_path).unwrap();
        let sequence = text
            .lines()
            .filter(|line| !line.starts_with('>'))
            .collect::<String>();
        assert!(text.contains(">Chr01"));
        assert_eq!(sequence, "CCCGNNCCC");
        assert_eq!(summary.output_path, output_path);
    }

    #[test]
    fn export_final_path_fasta_resolves_partitioned_dataset_and_reference_locators() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference/chrs")).unwrap();
        fs::create_dir_all(workspace_root.join("data/partitions/chr/Chr01")).unwrap();

        fs::write(
            workspace_root.join("data/reference/chrs/Chr01.fa"),
            ">Chr01\nAAAACCCCGGGGTTTT\n",
        )
        .unwrap();
        fs::write(
            workspace_root.join("data/partitions/chr/Chr01/ds.fa"),
            ">tigA\nTTGGAACC\n",
        )
        .unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();
        fs::write(workspace_root.join("data/datasets/ds.fa.fai"), "").unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO workspace_package_metadata (
                id, package_mode, sequence_layout, preassigned_chr,
                chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             ) VALUES (1, 'fast', 'partitioned', 1, 60.0, 'chr_partition', 'chr_partition')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 16)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr_locator (reference_chr_id, fasta_path)
             VALUES (1, ?1)",
            params![
                workspace_root
                    .join("data/reference/chrs/Chr01.fa")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root.join("data/datasets/ds.fa").to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 8)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (101, ?1)",
            params![
                workspace_root
                    .join("data/partitions/chr/Chr01/ds.fa")
                    .to_string_lossy()
            ],
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
             VALUES (201, 1, 101, '+', 2, 6, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();

        let output_path = workspace_root.join("exports/final-path-partitioned.fasta");
        fs::create_dir_all(output_path.parent().unwrap()).unwrap();
        let summary = export_final_path_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportFinalPathFastaParams {
                chr_name: "Chr01".to_string(),
                output_path: output_path.clone(),
                final_path_segments: vec![
                    FinalPathExportSegment::Ctg {
                        assembly_ctg_id: 301,
                        start: 1,
                        end: 5,
                    },
                    FinalPathExportSegment::Gap { gap_size_bp: 2 },
                    FinalPathExportSegment::RefSegment {
                        reference_chr_name: "Chr01".to_string(),
                        member_start_bp: 5,
                        member_end_bp: 12,
                        start: 2,
                        end: 5,
                    },
                ],
            },
        )
        .unwrap();

        let text = fs::read_to_string(&summary.output_path).unwrap();
        let sequence = text
            .lines()
            .filter(|line| !line.starts_with('>'))
            .collect::<String>();
        assert_eq!(sequence, "TGGAANNCCCG");
    }

    #[test]
    fn export_final_path_fasta_partitioned_light_reports_missing_locator_payload() {
        let temp = tempdir().unwrap();
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets")).unwrap();
        fs::write(workspace_root.join("data/reference/ref.fa.fai"), "").unwrap();
        fs::write(workspace_root.join("data/datasets/ds.fa.fai"), "").unwrap();

        let db_path = workspace_root.join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();

        conn.execute(
            "INSERT INTO workspace_package_metadata (
                id, package_mode, sequence_layout, preassigned_chr,
                chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             ) VALUES (1, 'fast', 'partitioned', 1, 60.0, 'chr_partition', 'chr_partition')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root
                    .join("data/reference/ref.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 16)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds', 'asm', NULL, ?1, ?2)",
            params![
                workspace_root.join("data/datasets/ds.fa").to_string_lossy(),
                workspace_root
                    .join("data/datasets/ds.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 8)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (101, ?1)",
            params![
                workspace_root
                    .join("data/partitions/chr/Chr01/ds.fa")
                    .to_string_lossy()
            ],
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
             VALUES (201, 1, 101, '+', 1, 4, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'manual', '1', NULL)",
            [],
        )
        .unwrap();

        let output_path = workspace_root.join("exports/final-path-partitioned-light.fasta");
        fs::create_dir_all(output_path.parent().unwrap()).unwrap();
        let error = export_final_path_fasta_with_connection(
            &mut conn,
            &db_path,
            1,
            &ExportFinalPathFastaParams {
                chr_name: "Chr01".to_string(),
                output_path,
                final_path_segments: vec![FinalPathExportSegment::Ctg {
                    assembly_ctg_id: 301,
                    start: 1,
                    end: 4,
                }],
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("failed to open fasta"));
    }

    fn seed_source_seq_locators(conn: &Connection, source_seq_ids: &[i64], fasta_path: &Path) {
        for source_seq_id in source_seq_ids {
            conn.execute(
                "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
                 VALUES (?1, ?2)",
                params![source_seq_id, fasta_path.to_string_lossy()],
            )
            .unwrap();
        }
    }

    fn seed_reference_chr_locator(conn: &Connection, reference_chr_id: i64, fasta_path: PathBuf) {
        conn.execute(
            "INSERT INTO reference_chr_locator (reference_chr_id, fasta_path)
             VALUES (?1, ?2)",
            params![reference_chr_id, fasta_path.to_string_lossy()],
        )
        .unwrap();
    }
}
