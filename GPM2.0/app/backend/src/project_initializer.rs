use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, Transaction, params};

use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectInitializerOptions {
    pub package_metadata: PackageMetadataOption,
    pub references: Vec<ReferenceOption>,
    pub datasets: Vec<DatasetOption>,
    pub existing_projects: Vec<ExistingProjectOption>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PackageMetadataOption {
    pub package_mode: String,
    pub sequence_layout: String,
    pub preassigned_chr: bool,
    pub chr_assignment_min_coverage_percent: f64,
    pub self_alignment_scope: String,
    pub cross_alignment_scope: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReferenceOption {
    pub id: i64,
    pub name: String,
    pub species_name: String,
    pub assembly_label: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DatasetOption {
    pub id: i64,
    pub name: String,
    pub assembler: String,
    pub assembler_version: Option<String>,
    pub contig_count: i64,
    pub total_length_bp: i64,
    pub fasta_available: bool,
    pub self_alignment_available: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExistingProjectOption {
    pub id: i64,
    pub name: String,
    pub version: i64,
    pub reference_genome_id: i64,
    pub reference_name: String,
    pub primary_dataset_id: i64,
    pub primary_dataset_name: String,
    pub support_dataset_ids: Vec<i64>,
    pub is_processed: bool,
    pub auto_pipeline_done: bool,
    pub auto_check_new_seq: bool,
    pub phased_assembly_enabled: bool,
    pub chr_assignment_min_coverage_percent: f64,
    pub description: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectInitializationRequest {
    pub project_name: String,
    pub reference_genome_id: i64,
    pub primary_dataset_id: i64,
    pub support_dataset_ids: Vec<i64>,
    pub auto_check_new_seq: bool,
    pub phased_assembly_enabled: Option<bool>,
    pub chr_assignment_min_coverage_percent: Option<f64>,
    pub description: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectInitializationSummary {
    pub project_id: i64,
    pub project_name: String,
    pub version: i64,
    pub reference_genome_id: i64,
    pub primary_dataset_id: i64,
    pub project_dataset_count: i64,
    pub phased_assembly_enabled: bool,
    pub chr_assignment_min_coverage_percent: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectUpdateRequest {
    pub project_id: i64,
    pub project_name: String,
    pub reference_genome_id: i64,
    pub primary_dataset_id: i64,
    pub support_dataset_ids: Vec<i64>,
    pub phased_assembly_enabled: Option<bool>,
    pub chr_assignment_min_coverage_percent: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectUpdateSummary {
    pub project_id: i64,
    pub project_name: String,
    pub reference_genome_id: i64,
    pub primary_dataset_id: i64,
    pub project_dataset_count: i64,
    pub phased_assembly_enabled: bool,
    pub chr_assignment_min_coverage_percent: f64,
    pub is_processed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AssemblyBootstrapSummary {
    pub project_id: i64,
    pub assembly_seq_count: i64,
    pub assembly_ctg_count: i64,
    pub assembly_member_count: i64,
}

#[derive(Debug, Clone)]
struct ValidatedRequest {
    project_name: String,
    reference_genome_id: i64,
    primary_dataset_id: i64,
    support_dataset_ids: Vec<i64>,
    auto_check_new_seq: bool,
    phased_assembly_enabled: bool,
    chr_assignment_min_coverage_percent: f64,
    description: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
struct WorkspacePackageMetadata {
    package_mode: String,
    sequence_layout: String,
    preassigned_chr: bool,
    chr_assignment_min_coverage_percent: f64,
    self_alignment_scope: String,
    cross_alignment_scope: String,
}

#[derive(Debug, Clone, PartialEq)]
struct ImportedChrAssignmentSeed {
    chr_name: String,
    support_bp: i64,
    support_percent: f64,
    anchor_start: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BootstrapSourceSeed {
    source_seq_id: i64,
    dataset_id: i64,
    dataset_name: String,
    seq_name: String,
    source_length: i64,
}

pub fn list_initializer_options(project_db_path: &Path) -> Result<ProjectInitializerOptions> {
    let conn = open_workspace_db(project_db_path)?;
    list_initializer_options_with_connection(&conn)
}

pub fn list_initializer_options_with_connection(
    conn: &Connection,
) -> Result<ProjectInitializerOptions> {
    let package_metadata = load_workspace_package_metadata(conn)?;
    let datasets = list_dataset_options(conn)?;
    Ok(ProjectInitializerOptions {
        package_metadata: PackageMetadataOption {
            package_mode: package_metadata.package_mode,
            sequence_layout: package_metadata.sequence_layout,
            preassigned_chr: package_metadata.preassigned_chr,
            chr_assignment_min_coverage_percent: package_metadata
                .chr_assignment_min_coverage_percent,
            self_alignment_scope: package_metadata.self_alignment_scope,
            cross_alignment_scope: package_metadata.cross_alignment_scope,
        },
        references: list_reference_options(conn)?,
        datasets,
        existing_projects: list_existing_projects(conn)?,
    })
}

pub fn initialize_project(
    project_db_path: &Path,
    request: &ProjectInitializationRequest,
) -> Result<ProjectInitializationSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    initialize_project_with_connection(&mut conn, request)
}

pub fn delete_project(project_db_path: &Path, project_id: i64) -> Result<()> {
    let mut conn = open_workspace_db(project_db_path)?;
    delete_project_with_connection(&mut conn, project_id)
}

pub fn update_project(
    project_db_path: &Path,
    request: &ProjectUpdateRequest,
) -> Result<ProjectUpdateSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    update_project_with_connection(&mut conn, request)
}

pub fn set_project_auto_pipeline_done(
    project_db_path: &Path,
    project_id: i64,
    done: bool,
) -> Result<()> {
    let mut conn = open_workspace_db(project_db_path)?;
    set_project_auto_pipeline_done_with_connection(&mut conn, project_id, done)
}

pub fn initialize_project_with_connection(
    conn: &mut Connection,
    request: &ProjectInitializationRequest,
) -> Result<ProjectInitializationSummary> {
    let validated = validate_request(conn, request)?;
    let tx = conn
        .transaction()
        .context("failed to start project initializer transaction")?;

    let next_version: i64 = tx
        .query_row(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM project WHERE primary_dataset_id = ?1",
            params![validated.primary_dataset_id],
            |row| row.get(0),
        )
        .context("failed to calculate next project version for primary dataset")?;

    let created_at = now_timestamp_string();
    tx.execute(
        "INSERT INTO project (
            name, version, reference_genome_id, primary_dataset_id,
            auto_check_new_seq, phased_assembly_enabled,
            chr_assignment_min_coverage_percent, description, created_at, note
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, NULL)",
        params![
            &validated.project_name,
            next_version,
            validated.reference_genome_id,
            validated.primary_dataset_id,
            if validated.auto_check_new_seq {
                1_i64
            } else {
                0_i64
            },
            if validated.phased_assembly_enabled {
                1_i64
            } else {
                0_i64
            },
            validated.chr_assignment_min_coverage_percent,
            validated.description.as_deref(),
            &created_at
        ],
    )
    .context("failed to insert project")?;
    let project_id = tx.last_insert_rowid();

    tx.execute(
        "INSERT INTO project_dataset (
            project_id, dataset_id, dataset_role, display_order
        ) VALUES (?1, ?2, 'primary', 1)",
        params![project_id, validated.primary_dataset_id],
    )
    .context("failed to insert primary dataset link")?;

    for (offset, dataset_id) in validated.support_dataset_ids.iter().copied().enumerate() {
        tx.execute(
            "INSERT INTO project_dataset (
                project_id, dataset_id, dataset_role, display_order
            ) VALUES (?1, ?2, 'support', ?3)",
            params![project_id, dataset_id, (offset as i64) + 2],
        )
        .with_context(|| format!("failed to insert support dataset link {}", dataset_id))?;
    }

    tx.commit()
        .context("failed to commit project initializer transaction")?;

    Ok(ProjectInitializationSummary {
        project_id,
        project_name: validated.project_name,
        version: next_version,
        reference_genome_id: validated.reference_genome_id,
        primary_dataset_id: validated.primary_dataset_id,
        project_dataset_count: validated.support_dataset_ids.len() as i64 + 1,
        phased_assembly_enabled: validated.phased_assembly_enabled,
        chr_assignment_min_coverage_percent: validated.chr_assignment_min_coverage_percent,
    })
}

pub fn delete_project_with_connection(conn: &mut Connection, project_id: i64) -> Result<()> {
    let tx = conn
        .transaction()
        .context("failed to start delete project transaction")?;
    tx.execute(
        "DELETE FROM pairwise_alignment_scope WHERE project_id = ?1",
        params![project_id],
    )
    .with_context(|| {
        format!("failed to delete pairwise scoped cache for project_id={project_id}")
    })?;
    let affected = tx
        .execute("DELETE FROM project WHERE id = ?1", params![project_id])
        .with_context(|| format!("failed to delete project_id={}", project_id))?;
    if affected == 0 {
        bail!("project_id {} does not exist", project_id);
    }
    tx.commit()
        .context("failed to commit delete project transaction")?;
    Ok(())
}

pub fn set_project_auto_pipeline_done_with_connection(
    conn: &mut Connection,
    project_id: i64,
    done: bool,
) -> Result<()> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    let tx = conn
        .transaction()
        .context("failed to start set auto pipeline done transaction")?;
    let affected = tx
        .execute(
            "UPDATE project
             SET auto_pipeline_done = ?1
             WHERE id = ?2",
            params![if done { 1_i64 } else { 0_i64 }, project_id],
        )
        .with_context(|| {
            format!(
                "failed to update auto_pipeline_done for project {}",
                project_id
            )
        })?;
    if affected == 0 {
        bail!("project_id {} does not exist", project_id);
    }
    tx.commit()
        .context("failed to commit set auto pipeline done transaction")?;
    Ok(())
}

pub fn update_project_with_connection(
    conn: &mut Connection,
    request: &ProjectUpdateRequest,
) -> Result<ProjectUpdateSummary> {
    if request.project_id <= 0 {
        bail!("project_id must be > 0");
    }
    let project_name = request.project_name.trim();
    if project_name.is_empty() {
        bail!("project_name must not be blank");
    }

    let existing_row: Option<(i64, i64, bool, f64)> = conn
        .query_row(
            "SELECT reference_genome_id, primary_dataset_id, phased_assembly_enabled, chr_assignment_min_coverage_percent
             FROM project
             WHERE id = ?1",
            params![request.project_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get::<_, i64>(2)? > 0, row.get(3)?)),
        )
        .optional()
        .context("failed to load existing project row before update")?;
    let Some((
        before_reference_genome_id,
        before_primary_dataset_id,
        before_phased_assembly_enabled,
        before_chr_assignment_min_coverage_percent,
    )) = existing_row
    else {
        bail!("project_id {} does not exist", request.project_id);
    };
    let is_processed = is_project_processed(conn, request.project_id)?;
    validate_project_name_uniqueness(conn, project_name, Some(request.project_id))?;

    let before_support_dataset_ids = load_project_support_dataset_ids(conn, request.project_id)?;
    let requested_support_dataset_ids = normalize_support_dataset_ids(
        conn,
        request.primary_dataset_id,
        &request.support_dataset_ids,
    )?;
    let phased_assembly_enabled = request
        .phased_assembly_enabled
        .unwrap_or(before_phased_assembly_enabled);
    let chr_assignment_min_coverage_percent = before_chr_assignment_min_coverage_percent;
    let (effective_support_dataset_ids, append_support_dataset_ids, phased_assembly_enabled) =
        if is_processed {
            validate_processed_project_update(
                request,
                before_reference_genome_id,
                before_primary_dataset_id,
                before_phased_assembly_enabled,
                before_chr_assignment_min_coverage_percent,
                &before_support_dataset_ids,
                &requested_support_dataset_ids,
                phased_assembly_enabled,
            )?
        } else {
            (
                requested_support_dataset_ids.clone(),
                Vec::new(),
                phased_assembly_enabled,
            )
        };
    let non_name_fields_changed = before_reference_genome_id != request.reference_genome_id
        || before_primary_dataset_id != request.primary_dataset_id
        || before_support_dataset_ids != effective_support_dataset_ids
        || before_phased_assembly_enabled != phased_assembly_enabled;
    let threshold_changed =
        (before_chr_assignment_min_coverage_percent - chr_assignment_min_coverage_percent).abs()
            > f64::EPSILON;

    validate_reference(conn, request.reference_genome_id)?;
    validate_dataset(conn, request.primary_dataset_id, "primary_dataset_id")?;

    let tx = conn
        .transaction()
        .context("failed to start update project transaction")?;
    tx.execute(
        "UPDATE project
         SET name = ?1,
             reference_genome_id = ?2,
             primary_dataset_id = ?3,
             phased_assembly_enabled = ?4,
             chr_assignment_min_coverage_percent = ?5
         WHERE id = ?6",
        params![
            project_name,
            request.reference_genome_id,
            request.primary_dataset_id,
            if phased_assembly_enabled {
                1_i64
            } else {
                0_i64
            },
            chr_assignment_min_coverage_percent,
            request.project_id
        ],
    )
    .with_context(|| format!("failed to update project {}", request.project_id))?;

    tx.execute(
        "DELETE FROM project_dataset WHERE project_id = ?1",
        params![request.project_id],
    )
    .with_context(|| {
        format!(
            "failed to clear project_dataset rows for project {}",
            request.project_id
        )
    })?;
    tx.execute(
        "INSERT INTO project_dataset (
            project_id, dataset_id, dataset_role, display_order
         ) VALUES (?1, ?2, 'primary', 1)",
        params![request.project_id, request.primary_dataset_id],
    )
    .context("failed to insert primary dataset link during project update")?;
    for (offset, dataset_id) in effective_support_dataset_ids.iter().copied().enumerate() {
        tx.execute(
            "INSERT INTO project_dataset (
                project_id, dataset_id, dataset_role, display_order
             ) VALUES (?1, ?2, 'support', ?3)",
            params![request.project_id, dataset_id, (offset as i64) + 2],
        )
        .with_context(|| {
            format!(
                "failed to insert support dataset {} during project update",
                dataset_id
            )
        })?;
    }
    for dataset_id in append_support_dataset_ids.iter().copied() {
        append_project_dataset_assembly_in_transaction(&tx, request.project_id, dataset_id)?;
    }
    if !is_processed && (non_name_fields_changed || threshold_changed) {
        tx.execute(
            "UPDATE project
             SET auto_pipeline_done = 0
             WHERE id = ?1",
            params![request.project_id],
        )
        .with_context(|| {
            format!(
                "failed to reset auto_pipeline_done for project {}",
                request.project_id
            )
        })?;
    }

    tx.commit()
        .context("failed to commit update project transaction")?;

    Ok(ProjectUpdateSummary {
        project_id: request.project_id,
        project_name: project_name.to_string(),
        reference_genome_id: request.reference_genome_id,
        primary_dataset_id: request.primary_dataset_id,
        project_dataset_count: effective_support_dataset_ids.len() as i64 + 1,
        phased_assembly_enabled,
        chr_assignment_min_coverage_percent,
        is_processed,
    })
}

fn validate_processed_project_update(
    request: &ProjectUpdateRequest,
    before_reference_genome_id: i64,
    before_primary_dataset_id: i64,
    before_phased_assembly_enabled: bool,
    before_chr_assignment_min_coverage_percent: f64,
    before_support_dataset_ids: &[i64],
    requested_support_dataset_ids: &[i64],
    requested_phased_assembly_enabled: bool,
) -> Result<(Vec<i64>, Vec<i64>, bool)> {
    if request.reference_genome_id != before_reference_genome_id {
        bail!("该项目已进入装配流程，禁止修改 reference_genome_id。");
    }
    if request.primary_dataset_id != before_primary_dataset_id {
        bail!("该项目已进入装配流程，禁止修改 primary_dataset_id。");
    }
    if let Some(requested_threshold) = request.chr_assignment_min_coverage_percent
        && (requested_threshold - before_chr_assignment_min_coverage_percent).abs() > f64::EPSILON
    {
        bail!("该项目已进入装配流程，禁止修改 chr_assignment_min_coverage_percent。");
    }
    for dataset_id in before_support_dataset_ids {
        if !requested_support_dataset_ids.contains(dataset_id) {
            bail!("该项目已进入装配流程，support_dataset_ids 只允许追加，不能移除。");
        }
    }
    if before_phased_assembly_enabled && !requested_phased_assembly_enabled {
        bail!("该项目已进入装配流程，phased_assembly_enabled 只允许开启，不能关闭。");
    }

    let mut effective_support_dataset_ids = before_support_dataset_ids.to_vec();
    let mut append_support_dataset_ids = Vec::new();
    let mut seen = effective_support_dataset_ids
        .iter()
        .copied()
        .collect::<HashSet<_>>();
    for dataset_id in requested_support_dataset_ids {
        if seen.insert(*dataset_id) {
            effective_support_dataset_ids.push(*dataset_id);
            append_support_dataset_ids.push(*dataset_id);
        }
    }

    Ok((
        effective_support_dataset_ids,
        append_support_dataset_ids,
        before_phased_assembly_enabled || requested_phased_assembly_enabled,
    ))
}

pub fn bootstrap_project_assembly(
    project_db_path: &Path,
    project_id: i64,
) -> Result<AssemblyBootstrapSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    bootstrap_project_assembly_with_connection(&mut conn, project_id)
}

pub fn bootstrap_project_assembly_cancel(
    project_db_path: &Path,
    project_id: i64,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<AssemblyBootstrapSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    bootstrap_project_assembly_with_connection_cancel(&mut conn, project_id, should_cancel)
}

pub fn bootstrap_project_assembly_with_connection(
    conn: &mut Connection,
    project_id: i64,
) -> Result<AssemblyBootstrapSummary> {
    let mut never_cancel = || false;
    bootstrap_project_assembly_with_connection_cancel(conn, project_id, &mut never_cancel)
}

pub fn append_project_dataset_assembly(
    project_db_path: &Path,
    project_id: i64,
    dataset_id: i64,
) -> Result<AssemblyBootstrapSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    append_project_dataset_assembly_with_connection(&mut conn, project_id, dataset_id)
}

pub fn append_project_dataset_assembly_with_connection(
    conn: &mut Connection,
    project_id: i64,
    dataset_id: i64,
) -> Result<AssemblyBootstrapSummary> {
    let mut never_cancel = || false;
    append_project_dataset_assembly_with_connection_cancel(
        conn,
        project_id,
        dataset_id,
        &mut never_cancel,
    )
}

pub fn append_project_dataset_assembly_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    dataset_id: i64,
    should_cancel: &mut F,
) -> Result<AssemblyBootstrapSummary>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let tx = conn
        .transaction()
        .context("failed to start assembly append transaction")?;
    let summary = append_project_dataset_assembly_in_transaction_cancel(
        &tx,
        project_id,
        dataset_id,
        should_cancel,
    )?;
    tx.commit()
        .context("failed to commit assembly append transaction")?;
    Ok(summary)
}

fn append_project_dataset_assembly_in_transaction(
    tx: &Transaction<'_>,
    project_id: i64,
    dataset_id: i64,
) -> Result<AssemblyBootstrapSummary> {
    let mut never_cancel = || false;
    append_project_dataset_assembly_in_transaction_cancel(
        tx,
        project_id,
        dataset_id,
        &mut never_cancel,
    )
}

fn append_project_dataset_assembly_in_transaction_cancel<F>(
    tx: &Transaction<'_>,
    project_id: i64,
    dataset_id: i64,
    should_cancel: &mut F,
) -> Result<AssemblyBootstrapSummary>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let linked_dataset_exists: Option<i64> = tx
        .query_row(
            "SELECT dataset_id
             FROM project_dataset
             WHERE project_id = ?1 AND dataset_id = ?2",
            params![project_id, dataset_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to validate project_dataset link before assembly append")?;
    if linked_dataset_exists.is_none() {
        bail!(
            "dataset_id {} is not linked to project_id {}",
            dataset_id,
            project_id
        );
    }
    let existing_dataset_assembly_seq_count: i64 = tx
        .query_row(
            "SELECT COUNT(*)
             FROM assembly_seq s
             JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE s.project_id = ?1
               AND ss.dataset_id = ?2",
            params![project_id, dataset_id],
            |row| row.get(0),
        )
        .context("failed to check existing assembly rows for dataset append")?;
    if existing_dataset_assembly_seq_count > 0 {
        bail!(
            "project_id {} already has assembly rows for dataset_id {}; append only supports datasets without assembly rows",
            project_id,
            dataset_id
        );
    }

    let seeds = load_bootstrap_source_seeds(tx, project_id)?;
    let append_seeds: Vec<_> = seeds
        .iter()
        .filter(|seed| seed.dataset_id == dataset_id)
        .cloned()
        .collect();
    if append_seeds.is_empty() {
        bail!(
            "project_id {} has no source_seq rows for dataset_id {}",
            project_id,
            dataset_id
        );
    }
    let imported_assignment_seeds = load_imported_chr_assignment_seeds(tx, project_id)?;
    let duplicate_seq_names = duplicate_bootstrap_seq_names(&seeds);
    let summary = insert_bootstrap_source_seeds(
        tx,
        project_id,
        &append_seeds,
        &imported_assignment_seeds,
        &duplicate_seq_names,
        should_cancel,
    )?;
    Ok(summary)
}

pub fn bootstrap_project_assembly_with_connection_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    should_cancel: &mut F,
) -> Result<AssemblyBootstrapSummary>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let project_exists: Option<i64> = conn
        .query_row(
            "SELECT id FROM project WHERE id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to validate project_id before assembly bootstrap")?;
    if project_exists.is_none() {
        bail!("project_id {} does not exist", project_id);
    }

    let existing_assembly_seq_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM assembly_seq WHERE project_id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .context("failed to check existing assembly_seq rows")?;
    if existing_assembly_seq_count > 0 {
        bail!(
            "project_id {} already has assembly_seq rows; bootstrap only supports empty assembly layer",
            project_id
        );
    }

    let tx = conn
        .transaction()
        .context("failed to start assembly bootstrap transaction")?;
    let seeds = load_bootstrap_source_seeds(&tx, project_id)?;
    if seeds.is_empty() {
        bail!(
            "project_id {} has no source_seq rows through project_dataset links",
            project_id
        );
    }
    let imported_assignment_seeds = load_imported_chr_assignment_seeds(&tx, project_id)?;
    let duplicate_seq_names = duplicate_bootstrap_seq_names(&seeds);
    let summary = insert_bootstrap_source_seeds(
        &tx,
        project_id,
        &seeds,
        &imported_assignment_seeds,
        &duplicate_seq_names,
        should_cancel,
    )?;

    tx.commit()
        .context("failed to commit assembly bootstrap transaction")?;

    Ok(summary)
}

fn load_workspace_package_metadata(conn: &Connection) -> Result<WorkspacePackageMetadata> {
    let row = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr, chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok(WorkspacePackageMetadata {
                    package_mode: row.get(0)?,
                    sequence_layout: row.get(1)?,
                    preassigned_chr: row.get::<_, i64>(2)? > 0,
                    chr_assignment_min_coverage_percent: row.get(3)?,
                    self_alignment_scope: row.get(4)?,
                    cross_alignment_scope: row.get(5)?,
                })
            },
        )
        .optional()
        .context("failed to load workspace_package_metadata")?;
    Ok(row.unwrap_or_else(default_workspace_package_metadata))
}

fn default_workspace_package_metadata() -> WorkspacePackageMetadata {
    WorkspacePackageMetadata {
        package_mode: "fast".to_string(),
        sequence_layout: "partitioned".to_string(),
        preassigned_chr: true,
        chr_assignment_min_coverage_percent: 60.0,
        self_alignment_scope: "chr_partition".to_string(),
        cross_alignment_scope: "chr_partition".to_string(),
    }
}

fn load_bootstrap_source_seeds(
    conn: &Connection,
    project_id: i64,
) -> Result<Vec<BootstrapSourceSeed>> {
    let mut seq_stmt = conn
        .prepare(
            "SELECT
                ss.id,
                d.id,
                d.name,
                ss.seq_name,
                ss.length
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             JOIN source_seq ss ON ss.dataset_id = pd.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY pd.display_order, ss.seq_order, ss.id",
        )
        .context("failed to prepare source_seq query for assembly bootstrap")?;
    seq_stmt
        .query_map(params![project_id], |row| {
            Ok(BootstrapSourceSeed {
                source_seq_id: row.get(0)?,
                dataset_id: row.get(1)?,
                dataset_name: row.get(2)?,
                seq_name: row.get(3)?,
                source_length: row.get(4)?,
            })
        })
        .context("failed to query source_seq rows for assembly bootstrap")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode source_seq rows for assembly bootstrap")
}

fn insert_bootstrap_source_seeds<F>(
    tx: &Transaction<'_>,
    project_id: i64,
    seeds: &[BootstrapSourceSeed],
    imported_assignment_seeds: &HashMap<i64, Vec<ImportedChrAssignmentSeed>>,
    duplicate_seq_names: &HashSet<String>,
    should_cancel: &mut F,
) -> Result<AssemblyBootstrapSummary>
where
    F: FnMut() -> bool,
{
    let created_at = now_timestamp_string();
    let mut assembly_seq_count = 0_i64;
    let mut assembly_ctg_count = 0_i64;
    let mut assembly_member_count = 0_i64;
    for source_seed in seeds {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }
        let ctg_base_name = bootstrap_ctg_base_name(source_seed, duplicate_seq_names);
        if let Some(imported_seeds) = imported_assignment_seeds.get(&source_seed.source_seq_id)
            && !imported_seeds.is_empty()
        {
            for seed in imported_seeds {
                insert_bootstrap_auto_seed(
                    tx,
                    project_id,
                    source_seed.source_seq_id,
                    &ctg_base_name,
                    source_seed.source_length,
                    seed,
                    &created_at,
                )?;
                assembly_seq_count += 1;
                assembly_ctg_count += 1;
                assembly_member_count += 1;
            }
            continue;
        }

        insert_bootstrap_unplaced_seed(
            tx,
            project_id,
            source_seed.source_seq_id,
            source_seed.source_length,
            &ctg_base_name,
            &created_at,
        )?;
        assembly_seq_count += 1;
        assembly_ctg_count += 1;
        assembly_member_count += 1;
    }

    Ok(AssemblyBootstrapSummary {
        project_id,
        assembly_seq_count,
        assembly_ctg_count,
        assembly_member_count,
    })
}

fn duplicate_bootstrap_seq_names(seeds: &[BootstrapSourceSeed]) -> HashSet<String> {
    let mut counts = HashMap::new();
    for seed in seeds {
        *counts.entry(seed.seq_name.as_str()).or_insert(0_usize) += 1;
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

fn bootstrap_ctg_base_name(
    seed: &BootstrapSourceSeed,
    duplicate_seq_names: &HashSet<String>,
) -> String {
    if duplicate_seq_names.contains(&seed.seq_name) {
        format!("{}:{}", seed.dataset_name, seed.seq_name)
    } else {
        seed.seq_name.clone()
    }
}

fn load_imported_chr_assignment_seeds(
    conn: &Connection,
    project_id: i64,
) -> Result<HashMap<i64, Vec<ImportedChrAssignmentSeed>>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                ica.source_seq_id,
                rc.chr_name,
                ica.support_bp,
                ica.support_percent,
                ica.anchor_start
             FROM imported_chr_assignment ica
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             JOIN source_seq ss ON ss.id = ica.source_seq_id
             JOIN project_dataset pd ON pd.dataset_id = ss.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY pd.display_order, ss.seq_order, rc.chr_order, rc.id",
        )
        .context("failed to prepare imported chr assignment query")?;
    let rows = stmt
        .query_map(params![project_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                ImportedChrAssignmentSeed {
                    chr_name: row.get(1)?,
                    support_bp: row.get(2)?,
                    support_percent: row.get(3)?,
                    anchor_start: row.get(4)?,
                },
            ))
        })
        .context("failed to query imported chr assignments")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode imported chr assignments")?;
    let mut map = HashMap::new();
    for (source_seq_id, seed) in rows {
        map.entry(source_seq_id).or_insert_with(Vec::new).push(seed);
    }
    Ok(map)
}

fn insert_bootstrap_unplaced_seed(
    tx: &Transaction<'_>,
    project_id: i64,
    source_seq_id: i64,
    source_length: i64,
    ctg_name: &str,
    created_at: &str,
) -> Result<()> {
    tx.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
        ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, NULL)",
        params![
            project_id,
            source_seq_id,
            format!("source:{}", source_seq_id),
            source_length,
            created_at
        ],
    )
    .with_context(|| {
        format!(
            "failed to insert bootstrap assembly_seq for source_seq_id={}",
            source_seq_id
        )
    })?;
    let assembly_seq_id = tx.last_insert_rowid();
    tx.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
            ref_orient, placement_mode, created_at, note
        ) VALUES (?1, ?2, ?3, NULL, NULL, NULL, NULL, 'none', ?4, NULL)",
        params![project_id, assembly_seq_id, ctg_name, created_at],
    )
    .context("failed to insert bootstrap assembly_ctg")?;
    Ok(())
}

fn insert_bootstrap_auto_seed(
    tx: &Transaction<'_>,
    project_id: i64,
    source_seq_id: i64,
    ctg_base_name: &str,
    source_length: i64,
    seed: &ImportedChrAssignmentSeed,
    created_at: &str,
) -> Result<()> {
    tx.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
        ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, NULL)",
        params![
            project_id,
            source_seq_id,
            format!("chr:{}", seed.chr_name),
            source_length,
            created_at
        ],
    )
    .with_context(|| {
        format!(
            "failed to insert imported auto assembly_seq for source_seq_id={}",
            source_seq_id
        )
    })?;
    let assembly_seq_id = tx.last_insert_rowid();
    let note = format!(
        "imported_assignment=1; support_bp={}; support_percent={:.3}",
        seed.support_bp, seed.support_percent
    );
    tx.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
            ref_orient, placement_mode, created_at, note
        ) VALUES (?1, ?2, ?3, ?4, NULL, ?5, NULL, 'auto', ?6, ?7)",
        params![
            project_id,
            assembly_seq_id,
            format!("{}@{}", ctg_base_name, seed.chr_name),
            seed.chr_name,
            seed.anchor_start,
            created_at,
            note
        ],
    )
    .context("failed to insert imported auto assembly_ctg")?;
    Ok(())
}

fn list_reference_options(conn: &Connection) -> Result<Vec<ReferenceOption>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, name, species_name, assembly_label
             FROM reference_genome
             ORDER BY id",
        )
        .context("failed to prepare reference option query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok(ReferenceOption {
                id: row.get(0)?,
                name: row.get(1)?,
                species_name: row.get(2)?,
                assembly_label: row.get(3)?,
            })
        })
        .context("failed to query reference options")?;

    rows.collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to read reference options")
}

fn list_dataset_options(conn: &Connection) -> Result<Vec<DatasetOption>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, name, assembler, assembler_version, contig_count, total_length_bp, self_alignment_available
             FROM dataset
             ORDER BY id",
        )
        .context("failed to prepare dataset option query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok(DatasetOption {
                id: row.get(0)?,
                name: row.get(1)?,
                assembler: row.get(2)?,
                assembler_version: row.get(3)?,
                contig_count: row.get(4)?,
                total_length_bp: row.get(5)?,
                fasta_available: dataset_fasta_available(conn, row.get(0)?)?,
                self_alignment_available: row.get::<_, i64>(6)? > 0,
            })
        })
        .context("failed to query dataset options")?;

    rows.collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to read dataset options")
}

fn dataset_fasta_available(conn: &Connection, dataset_id: i64) -> rusqlite::Result<bool> {
    let mut stmt = conn.prepare(
        "SELECT ssl.fasta_path
         FROM source_seq ss
         LEFT JOIN source_seq_locator ssl ON ssl.source_seq_id = ss.id
         WHERE ss.dataset_id = ?1
         ORDER BY ss.seq_order, ss.id",
    )?;
    let rows = stmt
        .query_map(params![dataset_id], |row| row.get::<_, Option<String>>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if rows.is_empty() {
        return Ok(false);
    }
    Ok(rows.iter().all(|path| {
        path.as_ref()
            .is_some_and(|value| Path::new(value).is_file())
    }))
}

fn list_existing_projects(conn: &Connection) -> Result<Vec<ExistingProjectOption>> {
    let mut stmt = conn
        .prepare(
            "SELECT
                p.id,
                p.name,
                p.version,
                p.reference_genome_id,
                rg.name,
                p.primary_dataset_id,
                d.name,
                p.auto_pipeline_done,
                p.auto_check_new_seq,
                p.phased_assembly_enabled,
                p.chr_assignment_min_coverage_percent,
                p.description,
                p.created_at
             FROM project p
             JOIN reference_genome rg ON rg.id = p.reference_genome_id
             JOIN dataset d ON d.id = p.primary_dataset_id
             ORDER BY p.created_at, p.id",
        )
        .context("failed to prepare existing project query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, i64>(5)?,
                row.get::<_, String>(6)?,
                row.get::<_, i64>(7)? > 0,
                row.get::<_, i64>(8)? > 0,
                row.get::<_, i64>(9)? > 0,
                row.get::<_, f64>(10)?,
                row.get::<_, Option<String>>(11)?,
                row.get::<_, String>(12)?,
            ))
        })
        .context("failed to query existing projects")?;
    let base_rows = rows
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to read existing projects")?;

    let mut projects = Vec::with_capacity(base_rows.len());
    for row in base_rows {
        let support_dataset_ids = load_project_support_dataset_ids(conn, row.0)?;
        let is_processed = is_project_processed(conn, row.0)?;
        projects.push(ExistingProjectOption {
            id: row.0,
            name: row.1,
            version: row.2,
            reference_genome_id: row.3,
            reference_name: row.4,
            primary_dataset_id: row.5,
            primary_dataset_name: row.6,
            support_dataset_ids,
            is_processed,
            auto_pipeline_done: row.7,
            auto_check_new_seq: row.8,
            phased_assembly_enabled: row.9,
            chr_assignment_min_coverage_percent: row.10,
            description: row.11,
            created_at: row.12,
        });
    }
    Ok(projects)
}

fn validate_request(
    conn: &Connection,
    request: &ProjectInitializationRequest,
) -> Result<ValidatedRequest> {
    let package_metadata = load_workspace_package_metadata(conn)?;
    let project_name = request.project_name.trim();
    if project_name.is_empty() {
        bail!("project_name must not be blank");
    }
    validate_project_name_uniqueness(conn, project_name, None)?;

    validate_reference(conn, request.reference_genome_id)?;
    validate_dataset(conn, request.primary_dataset_id, "primary_dataset_id")?;
    let support_dataset_ids = normalize_support_dataset_ids(
        conn,
        request.primary_dataset_id,
        &request.support_dataset_ids,
    )?;
    let chr_assignment_min_coverage_percent = package_metadata.chr_assignment_min_coverage_percent;

    Ok(ValidatedRequest {
        project_name: project_name.to_string(),
        reference_genome_id: request.reference_genome_id,
        primary_dataset_id: request.primary_dataset_id,
        support_dataset_ids,
        auto_check_new_seq: request.auto_check_new_seq,
        phased_assembly_enabled: request.phased_assembly_enabled.unwrap_or(false),
        chr_assignment_min_coverage_percent,
        description: request.description.as_ref().and_then(|value| {
            let trimmed = value.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        }),
    })
}

fn validate_project_name_uniqueness(
    conn: &Connection,
    project_name: &str,
    exclude_project_id: Option<i64>,
) -> Result<()> {
    let duplicated_project: Option<i64> = conn
        .query_row(
            "SELECT id
             FROM project
             WHERE lower(name) = lower(?1)
               AND (?2 IS NULL OR id != ?2)
             LIMIT 1",
            params![project_name, exclude_project_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to validate project_name uniqueness")?;
    if let Some(project_id) = duplicated_project {
        bail!(
            "project_name '{}' already exists (project_id={})",
            project_name,
            project_id
        );
    }
    Ok(())
}

fn normalize_support_dataset_ids(
    conn: &Connection,
    primary_dataset_id: i64,
    support_dataset_ids: &[i64],
) -> Result<Vec<i64>> {
    let mut seen = HashSet::new();
    seen.insert(primary_dataset_id);
    let mut normalized = Vec::with_capacity(support_dataset_ids.len());
    for dataset_id in support_dataset_ids.iter().copied() {
        if dataset_id == primary_dataset_id {
            bail!(
                "support_dataset_ids must not include primary_dataset_id {}",
                primary_dataset_id
            );
        }
        if !seen.insert(dataset_id) {
            bail!(
                "support_dataset_ids contains duplicate dataset_id {}",
                dataset_id
            );
        }
        validate_dataset(conn, dataset_id, "support_dataset_id")?;
        normalized.push(dataset_id);
    }
    Ok(normalized)
}

fn load_project_support_dataset_ids(conn: &Connection, project_id: i64) -> Result<Vec<i64>> {
    let mut stmt = conn
        .prepare(
            "SELECT dataset_id
             FROM project_dataset
             WHERE project_id = ?1
               AND dataset_role = 'support'
             ORDER BY display_order, id",
        )
        .context("failed to prepare support dataset query")?;
    let rows = stmt
        .query_map(params![project_id], |row| row.get::<_, i64>(0))
        .context("failed to query support dataset ids")?;
    rows.collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode support dataset ids")
}

fn is_project_processed(conn: &Connection, project_id: i64) -> Result<bool> {
    let has_assembly_seq: i64 = conn
        .query_row(
            "SELECT EXISTS(
                SELECT 1
                FROM assembly_seq
                WHERE project_id = ?1
                LIMIT 1
             )",
            params![project_id],
            |row| row.get(0),
        )
        .context("failed to detect project processed state")?;
    Ok(has_assembly_seq > 0)
}

fn validate_reference(conn: &Connection, reference_genome_id: i64) -> Result<()> {
    let row = conn
        .query_row(
            "SELECT
                rg.id,
                (SELECT COUNT(*) FROM reference_chr rc WHERE rc.reference_genome_id = rg.id)
             FROM reference_genome rg
             WHERE rg.id = ?1",
            params![reference_genome_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)),
        )
        .optional()
        .context("failed to validate reference_genome_id")?;
    let Some((_id, chr_count)) = row else {
        bail!("reference_genome_id {} does not exist", reference_genome_id);
    };
    if chr_count == 0 {
        bail!(
            "reference_genome_id {} has no reference_chr rows",
            reference_genome_id
        );
    }
    Ok(())
}

fn validate_dataset(conn: &Connection, dataset_id: i64, field_name: &str) -> Result<()> {
    let row = conn
        .query_row(
            "SELECT
                d.id,
                (SELECT COUNT(*) FROM source_seq ss WHERE ss.dataset_id = d.id)
             FROM dataset d
             WHERE d.id = ?1",
            params![dataset_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)),
        )
        .optional()
        .with_context(|| format!("failed to validate {}", field_name))?;
    let Some((_id, source_seq_count)) = row else {
        bail!("{} {} does not exist", field_name, dataset_id);
    };
    if source_seq_count == 0 {
        bail!("{} {} has no source_seq rows", field_name, dataset_id);
    }
    Ok(())
}

fn now_timestamp_string() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs())
        .unwrap_or(0);
    secs.to_string()
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;
    use crate::db::init_workspace_schema;

    #[test]
    fn initializes_project_with_v1_aligned_versioning_and_dataset_links() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        seed_dataset(&conn, 12, "support_a");
        seed_dataset(&conn, 13, "support_b");

        let first = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_alpha".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![13, 12],
                auto_check_new_seq: true,
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: None,
                description: Some("init one".to_string()),
            },
        )
        .unwrap();
        assert_eq!(first.version, 1);
        assert_eq!(first.project_dataset_count, 3);
        assert_eq!(first.chr_assignment_min_coverage_percent, 60.0);
        assert!(first.phased_assembly_enabled);
        let first_flags: (i64, i64, f64, Option<String>) = conn
            .query_row(
                "SELECT auto_check_new_seq, phased_assembly_enabled, chr_assignment_min_coverage_percent, description FROM project WHERE id = ?1",
                params![first.project_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert_eq!(first_flags, (1, 1, 60.0, Some("init one".to_string())));

        let second = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_alpha_retry".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();
        assert_eq!(second.version, 2);

        let links = query_project_dataset_rows(&conn, first.project_id);
        assert_eq!(
            links,
            vec![
                (11_i64, "primary".to_string(), 1_i64),
                (13_i64, "support".to_string(), 2_i64),
                (12_i64, "support".to_string(), 3_i64),
            ]
        );
    }

    #[test]
    fn lists_options_and_existing_projects() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");

        initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_alpha".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let options = list_initializer_options_with_connection(&conn).unwrap();
        assert_eq!(options.references.len(), 1);
        assert_eq!(options.datasets.len(), 1);
        assert_eq!(options.datasets[0].contig_count, 1);
        assert_eq!(options.datasets[0].total_length_bp, 1000);
        assert_eq!(options.existing_projects.len(), 1);
        assert_eq!(options.existing_projects[0].version, 1);
        assert!(!options.existing_projects[0].phased_assembly_enabled);
        assert_eq!(
            options.existing_projects[0].chr_assignment_min_coverage_percent,
            60.0
        );
    }

    #[test]
    fn rejects_invalid_requests() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");

        let blank = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: " ".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap_err();
        assert!(blank.to_string().contains("must not be blank"));

        let duplicate_support = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_alpha".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![11],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap_err();
        assert!(
            duplicate_support
                .to_string()
                .contains("must not include primary_dataset_id")
        );

        let first = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_alpha".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();
        assert_eq!(first.project_name, "project_alpha");

        let duplicated_name = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "Project_Alpha".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap_err();
        assert!(duplicated_name.to_string().contains("already exists"));

        let server_threshold = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_server_threshold".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: Some(101.0),
                description: None,
            },
        )
        .unwrap();
        assert_eq!(server_threshold.chr_assignment_min_coverage_percent, 60.0);
    }

    #[test]
    fn deletes_project_and_cascades_links() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        seed_dataset(&conn, 12, "support_a");

        let created = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_delete_me".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let before_links: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM project_dataset WHERE project_id = ?1",
                params![created.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(before_links, 2);
        conn.execute(
            "INSERT INTO pairwise_alignment_run (
                id, run_name, paf_path, query_dataset_id, target_dataset_id,
                paf_mtime_ms, paf_size_bytes, indexed_at
             ) VALUES (901, 'primary_vs_support_a', '/tmp/primary_vs_support_a.paf', 12, 11, 1, 1, '1')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO pairwise_alignment_scope (
                project_id, assigned_chr_name, run_id, query_dataset_id, target_dataset_id,
                scope_kind, source_set_hash, paf_mtime_ms, paf_size_bytes, built_at
             ) VALUES (?1, 'chr1', 901, 12, 11, 'chr_partition_v2', 'q:1|t:2', 1, 1, '1')",
            params![created.project_id],
        )
        .unwrap();
        let before_scope_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pairwise_alignment_scope WHERE project_id = ?1",
                params![created.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(before_scope_count, 1);

        delete_project_with_connection(&mut conn, created.project_id).unwrap();

        let project_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM project WHERE id = ?1",
                params![created.project_id],
                |row| row.get(0),
            )
            .unwrap();
        let after_links: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM project_dataset WHERE project_id = ?1",
                params![created.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(project_count, 0);
        assert_eq!(after_links, 0);
        let after_scope_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pairwise_alignment_scope WHERE project_id = ?1",
                params![created.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(after_scope_count, 0);
    }

    #[test]
    fn bootstraps_project_assembly_from_selected_datasets() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        seed_dataset(&conn, 12, "support_a");

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_bootstrap".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let summary =
            bootstrap_project_assembly_with_connection(&mut conn, project.project_id).unwrap();
        assert_eq!(summary.assembly_seq_count, 2);
        assert_eq!(summary.assembly_ctg_count, 2);
        assert_eq!(summary.assembly_member_count, 2);

        let assembly_ctg_columns = {
            let mut stmt = conn.prepare("PRAGMA table_info(assembly_ctg)").unwrap();
            stmt.query_map([], |row| row.get::<_, String>(1))
                .unwrap()
                .collect::<std::result::Result<Vec<_>, _>>()
                .unwrap()
        };
        assert!(assembly_ctg_columns.contains(&"assembly_seq_id".to_string()));

        let member_table_exists: i64 = conn
            .query_row(
                "SELECT COUNT(*)
                 FROM sqlite_master
                 WHERE type = 'table'
                   AND name IN ('assembly_ctg_member', 'deleted_assembly_ctg_member')",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(member_table_exists, 0);

        let ctg_seq_links = {
            let mut stmt = conn
                .prepare("SELECT id, assembly_seq_id FROM assembly_ctg WHERE project_id = ?1 ORDER BY id")
                .unwrap();
            stmt.query_map(params![project.project_id], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?))
            })
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap()
        };
        assert_eq!(ctg_seq_links.len(), 2);
        assert!(
            ctg_seq_links
                .iter()
                .all(|(_, assembly_seq_id)| *assembly_seq_id > 0)
        );

        let ctg_names = {
            let mut stmt = conn
                .prepare("SELECT name FROM assembly_ctg WHERE project_id = ?1 ORDER BY id")
                .unwrap();
            stmt.query_map(params![project.project_id], |row| row.get::<_, String>(0))
                .unwrap()
                .collect::<std::result::Result<Vec<_>, _>>()
                .unwrap()
        };
        assert_eq!(
            ctg_names,
            vec!["primary_ctg1".to_string(), "support_a_ctg1".to_string()]
        );
    }

    #[test]
    fn updates_unprocessed_project_with_full_field_changes() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_reference(&conn, 2, "ref_b");
        seed_dataset(&conn, 11, "primary_a");
        seed_dataset(&conn, 12, "support_a");
        seed_dataset(&conn, 13, "primary_b");
        seed_dataset(&conn, 14, "support_b");

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_editable".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let updated = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_editable_v2".to_string(),
                reference_genome_id: 2,
                primary_dataset_id: 13,
                support_dataset_ids: vec![14],
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: Some(72.5),
            },
        )
        .unwrap();
        assert_eq!(updated.project_name, "project_editable_v2");
        assert_eq!(updated.reference_genome_id, 2);
        assert_eq!(updated.primary_dataset_id, 13);
        assert_eq!(updated.project_dataset_count, 2);
        assert!(updated.phased_assembly_enabled);
        assert_eq!(updated.chr_assignment_min_coverage_percent, 60.0);
        assert!(!updated.is_processed);

        let row: (String, i64, i64, i64, f64) = conn
            .query_row(
                "SELECT name, reference_genome_id, primary_dataset_id, phased_assembly_enabled, chr_assignment_min_coverage_percent
                 FROM project
                 WHERE id = ?1",
                params![project.project_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?)),
            )
            .unwrap();
        assert_eq!(row, ("project_editable_v2".to_string(), 2, 13, 1, 60.0));
        assert_eq!(
            query_project_dataset_rows(&conn, project.project_id),
            vec![
                (13_i64, "primary".to_string(), 1_i64),
                (14_i64, "support".to_string(), 2_i64),
            ]
        );
    }

    #[test]
    fn processed_project_allows_safe_one_way_updates() {
        let temp = tempdir().unwrap();
        let db_path = temp.path().join("project.sqlite");
        let mut conn = Connection::open(&db_path).unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_reference(&conn, 2, "ref_b");
        seed_dataset(&conn, 11, "primary_a");
        seed_dataset(&conn, 12, "support_a");
        seed_dataset(&conn, 13, "primary_b");
        seed_dataset(&conn, 14, "support_b");

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "project_locked".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();
        bootstrap_project_assembly_with_connection(&mut conn, project.project_id).unwrap();

        let updated = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_locked_renamed".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12, 14],
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: None,
            },
        )
        .unwrap();
        assert_eq!(updated.project_name, "project_locked_renamed");
        assert_eq!(updated.reference_genome_id, 1);
        assert_eq!(updated.primary_dataset_id, 11);
        assert_eq!(updated.project_dataset_count, 3);
        assert!(updated.phased_assembly_enabled);
        assert!(updated.is_processed);
        assert_eq!(
            query_project_dataset_rows(&conn, project.project_id),
            vec![
                (11_i64, "primary".to_string(), 1_i64),
                (12_i64, "support".to_string(), 2_i64),
                (14_i64, "support".to_string(), 3_i64),
            ]
        );
        assert_eq!(
            query_assembly_seq_count_for_dataset(&conn, project.project_id, 14),
            1
        );

        let primary_locked_error = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_locked_renamed".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 13,
                support_dataset_ids: vec![12, 14],
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: None,
            },
        )
        .unwrap_err();
        assert!(
            primary_locked_error
                .to_string()
                .contains("primary_dataset_id")
        );

        let remove_support_error = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_locked_renamed".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: None,
            },
        )
        .unwrap_err();
        assert!(remove_support_error.to_string().contains("只允许追加"));

        let disable_phased_error = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_locked_renamed".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12, 14],
                phased_assembly_enabled: Some(false),
                chr_assignment_min_coverage_percent: None,
            },
        )
        .unwrap_err();
        assert!(disable_phased_error.to_string().contains("只允许开启"));

        let threshold_locked_error = update_project_with_connection(
            &mut conn,
            &ProjectUpdateRequest {
                project_id: project.project_id,
                project_name: "project_locked_renamed".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12, 14],
                phased_assembly_enabled: Some(true),
                chr_assignment_min_coverage_percent: Some(66.0),
            },
        )
        .unwrap_err();
        assert!(
            threshold_locked_error
                .to_string()
                .contains("chr_assignment_min_coverage_percent")
        );

        let (project_name, threshold, phased): (String, f64, i64) = conn
            .query_row(
                "SELECT name, chr_assignment_min_coverage_percent, phased_assembly_enabled FROM project WHERE id = ?1",
                params![project.project_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(project_name, "project_locked_renamed");
        assert_eq!(threshold, 60.0);
        assert_eq!(phased, 1);
    }

    #[test]
    fn server_package_metadata_is_exposed_and_locks_project_threshold_to_server_value() {
        let mut conn = Connection::open_in_memory().unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        seed_dataset(&conn, 12, "support_a");
        conn.execute(
            "INSERT INTO workspace_package_metadata (
                id, package_mode, sequence_layout, preassigned_chr,
                chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             ) VALUES (1, 'fast', 'partitioned', 1, 72.0, 'chr_partition', 'chr_partition')",
            [],
        )
        .unwrap();

        let summary = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "server_project".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: Some(35.0),
                description: None,
            },
        )
        .unwrap();
        assert_eq!(summary.chr_assignment_min_coverage_percent, 72.0);

        let options = list_initializer_options_with_connection(&conn).unwrap();
        assert_eq!(options.package_metadata.package_mode, "fast");
        assert!(options.package_metadata.preassigned_chr);
        assert_eq!(
            options.package_metadata.chr_assignment_min_coverage_percent,
            72.0
        );
        assert_eq!(
            options.existing_projects[0].chr_assignment_min_coverage_percent,
            72.0
        );
    }

    #[test]
    fn bootstrap_uses_imported_chr_assignments_for_server_preassigned_projects() {
        let mut conn = Connection::open_in_memory().unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        conn.execute(
            "INSERT INTO workspace_package_metadata (
                id, package_mode, sequence_layout, preassigned_chr,
                chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             ) VALUES (1, 'fast', 'partitioned', 1, 60.0, 'chr_partition', 'chr_partition')",
            [],
        )
        .unwrap();
        let source_seq_id: i64 = conn
            .query_row(
                "SELECT id FROM source_seq WHERE dataset_id = 11 AND seq_name = 'primary_ctg1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let reference_chr_id: i64 = conn
            .query_row(
                "SELECT id FROM reference_chr WHERE reference_genome_id = 1 AND chr_name = 'chr1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        conn.execute(
            "INSERT INTO imported_chr_assignment (
                source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start
             ) VALUES (?1, ?2, 1000, 100.0, 42)",
            params![source_seq_id, reference_chr_id],
        )
        .unwrap();

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "fast_bootstrap".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let summary =
            bootstrap_project_assembly_with_connection(&mut conn, project.project_id).unwrap();
        assert_eq!(summary.assembly_seq_count, 1);

        let row: (String, Option<String>, Option<i64>, String, String) = conn
            .query_row(
                "SELECT c.name, c.assigned_chr_name, c.anchor_start, c.placement_mode, s.instance_key
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.project_id = ?1",
                params![project.project_id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                    ))
                },
            )
            .unwrap();
        assert_eq!(
            row,
            (
                "primary_ctg1@chr1".to_string(),
                Some("chr1".to_string()),
                Some(42),
                "auto".to_string(),
                "chr:chr1".to_string(),
            )
        );
    }

    #[test]
    fn appends_project_assembly_rows_for_new_dataset_only() {
        let mut conn = Connection::open_in_memory().unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "primary");
        seed_dataset(&conn, 14, "ds4");

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "append_ds4".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();
        bootstrap_project_assembly_with_connection(&mut conn, project.project_id).unwrap();
        conn.execute(
            "UPDATE assembly_ctg SET ref_orient = '-' WHERE project_id = ?1",
            params![project.project_id],
        )
        .unwrap();

        let before_existing_rows =
            query_assembly_rows_for_non_dataset(&conn, project.project_id, 14);

        let ds4_source_seq_id: i64 = conn
            .query_row(
                "SELECT id FROM source_seq WHERE dataset_id = 14",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let reference_chr_id: i64 = conn
            .query_row(
                "SELECT id FROM reference_chr WHERE reference_genome_id = 1 AND chr_name = 'chr1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        conn.execute(
            "INSERT INTO imported_chr_assignment (
                source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start
             ) VALUES (?1, ?2, 1000, 100.0, 444)",
            params![ds4_source_seq_id, reference_chr_id],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, 14, 'support', 2)",
            params![project.project_id],
        )
        .unwrap();

        let summary =
            append_project_dataset_assembly_with_connection(&mut conn, project.project_id, 14)
                .unwrap();

        assert_eq!(summary.assembly_seq_count, 1);
        assert_eq!(summary.assembly_ctg_count, 1);
        assert_eq!(summary.assembly_member_count, 1);
        assert_eq!(
            query_assembly_rows_for_non_dataset(&conn, project.project_id, 14),
            before_existing_rows
        );

        let ds4_row: (String, Option<String>, Option<i64>, String, String) = conn
            .query_row(
                "SELECT c.name, c.assigned_chr_name, c.anchor_start, c.placement_mode, s.orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE c.project_id = ?1 AND ss.dataset_id = 14",
                params![project.project_id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                    ))
                },
            )
            .unwrap();
        assert_eq!(
            ds4_row,
            (
                "ds4_ctg1@chr1".to_string(),
                Some("chr1".to_string()),
                Some(444),
                "auto".to_string(),
                "+".to_string(),
            )
        );

        let repeated_error =
            append_project_dataset_assembly_with_connection(&mut conn, project.project_id, 14)
                .unwrap_err();
        assert!(
            repeated_error
                .to_string()
                .contains("already has assembly rows for dataset_id 14"),
            "{repeated_error:#}"
        );
        assert_eq!(
            query_assembly_seq_count_for_dataset(&conn, project.project_id, 14),
            1
        );
    }

    #[test]
    fn bootstrap_disambiguates_imported_ctg_names_when_datasets_share_seq_names() {
        let mut conn = Connection::open_in_memory().unwrap();
        init_workspace_schema(&conn).unwrap();
        seed_reference(&conn, 1, "ref_a");
        seed_dataset(&conn, 11, "hifiasm_ont");
        seed_dataset(&conn, 12, "hifiasm_hifi");
        conn.execute(
            "INSERT INTO workspace_package_metadata (
                id, package_mode, sequence_layout, preassigned_chr,
                chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             ) VALUES (1, 'fast', 'partitioned', 1, 60.0, 'chr_partition', 'chr_partition')",
            [],
        )
        .unwrap();
        conn.execute(
            "UPDATE source_seq SET seq_name = 'ctg1514' WHERE dataset_id IN (11, 12)",
            [],
        )
        .unwrap();
        let reference_chr_id: i64 = conn
            .query_row(
                "SELECT id FROM reference_chr WHERE reference_genome_id = 1 AND chr_name = 'chr1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        for (dataset_id, anchor_start) in [(11_i64, 100_i64), (12_i64, 200_i64)] {
            let source_seq_id: i64 = conn
                .query_row(
                    "SELECT id FROM source_seq WHERE dataset_id = ?1 AND seq_name = 'ctg1514'",
                    params![dataset_id],
                    |row| row.get(0),
                )
                .unwrap();
            conn.execute(
                "INSERT INTO imported_chr_assignment (
                    source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start
                 ) VALUES (?1, ?2, 1000, 100.0, ?3)",
                params![source_seq_id, reference_chr_id, anchor_start],
            )
            .unwrap();
        }

        let project = initialize_project_with_connection(
            &mut conn,
            &ProjectInitializationRequest {
                project_name: "duplicate_seq_names".to_string(),
                reference_genome_id: 1,
                primary_dataset_id: 11,
                support_dataset_ids: vec![12],
                auto_check_new_seq: false,
                phased_assembly_enabled: None,
                chr_assignment_min_coverage_percent: None,
                description: None,
            },
        )
        .unwrap();

        let summary =
            bootstrap_project_assembly_with_connection(&mut conn, project.project_id).unwrap();
        assert_eq!(summary.assembly_seq_count, 2);

        let rows = {
            let mut stmt = conn
                .prepare(
                    "SELECT name, assigned_chr_name, anchor_start
                     FROM assembly_ctg
                     WHERE project_id = ?1
                     ORDER BY id",
                )
                .unwrap();
            stmt.query_map(params![project.project_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<String>>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                ))
            })
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap()
        };
        assert_eq!(
            rows,
            vec![
                (
                    "hifiasm_ont:ctg1514@chr1".to_string(),
                    Some("chr1".to_string()),
                    Some(100),
                ),
                (
                    "hifiasm_hifi:ctg1514@chr1".to_string(),
                    Some("chr1".to_string()),
                    Some(200),
                ),
            ]
        );
    }

    fn seed_reference(conn: &Connection, reference_id: i64, name: &str) {
        conn.execute(
            "INSERT INTO reference_genome (
                id, name, species_name, assembly_label, fasta_path, fai_path
            ) VALUES (?1, ?2, 'unknown', ?2, '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            params![reference_id, name],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (
                reference_genome_id, chr_name, chr_order, length
            ) VALUES (?1, 'chr1', 1, 1000)",
            params![reference_id],
        )
        .unwrap();
    }

    fn seed_dataset(conn: &Connection, dataset_id: i64, name: &str) {
        conn.execute(
            "INSERT INTO dataset (
                id, name, assembler, assembler_version, fasta_path, fai_path,
                contig_count, total_length_bp
            ) VALUES (?1, ?2, ?2, NULL, '/tmp/ds.fa', '/tmp/ds.fa.fai', 1, 1000)",
            params![dataset_id, name],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (
                dataset_id, seq_name, seq_order, length
            ) VALUES (?1, ?2, 1, 1000)",
            params![dataset_id, format!("{}_ctg1", name)],
        )
        .unwrap();
    }

    fn query_project_dataset_rows(conn: &Connection, project_id: i64) -> Vec<(i64, String, i64)> {
        let mut stmt = conn
            .prepare(
                "SELECT dataset_id, dataset_role, display_order
                 FROM project_dataset
                 WHERE project_id = ?1
                 ORDER BY display_order",
            )
            .unwrap();
        stmt.query_map(params![project_id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
    }

    fn query_assembly_rows_for_non_dataset(
        conn: &Connection,
        project_id: i64,
        dataset_id: i64,
    ) -> Vec<(i64, String, String, Option<String>)> {
        let mut stmt = conn
            .prepare(
                "SELECT s.id, c.name, s.orient, c.ref_orient
                 FROM assembly_seq s
                 JOIN assembly_ctg c ON c.assembly_seq_id = s.id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE s.project_id = ?1 AND ss.dataset_id != ?2
                 ORDER BY s.id",
            )
            .unwrap();
        stmt.query_map(params![project_id, dataset_id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
        })
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
    }

    fn query_assembly_seq_count_for_dataset(
        conn: &Connection,
        project_id: i64,
        dataset_id: i64,
    ) -> i64 {
        conn.query_row(
            "SELECT COUNT(*)
             FROM assembly_seq s
             JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE s.project_id = ?1 AND ss.dataset_id = ?2",
            params![project_id, dataset_id],
            |row| row.get(0),
        )
        .unwrap()
    }
}
