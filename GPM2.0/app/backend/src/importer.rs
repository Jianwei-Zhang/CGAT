use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, Transaction, params};
use zip::ZipArchive;

use crate::alignment_cache::{
    index_bundle_ref_alignment_hits_for_dataset_with_cancel,
    index_bundle_ref_alignment_hits_with_cancel,
    index_ref_alignment_hits_for_source_seq_with_cancel,
};
use crate::db::open_workspace_db;
use crate::junction_inspection::ensure_pairwise_alignment_run_cache_cancel;
use crate::workspace::{resolve_bundle_root_dir, resolve_extracted_bundle_workspace};

pub const EXPORTS_DIR: &str = "exports";
pub const CACHE_DIR: &str = "cache";
pub const PROJECT_DB_NAME: &str = "project.sqlite";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImportMode {
    ExtractedBundle,
    ZipDelivery,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportProgress {
    pub stage: &'static str,
    pub detail: String,
    pub progress_index: Option<usize>,
    pub progress_total: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportOutcome {
    pub mode: ImportMode,
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddDatasetImportOutcome {
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
    pub project_id: Option<i64>,
    pub dataset_id: i64,
    pub dataset_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddCtgImportOutcome {
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
    pub project_id: i64,
    pub dataset_id: i64,
    pub source_seq_id: i64,
    pub assembly_ctg_id: Option<i64>,
    pub ctg_name: String,
    pub target_track: String,
    pub target_chr: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AddCtgImportTarget {
    pub target_chr: String,
    pub target_track: String,
}

#[derive(Debug)]
struct ReferenceRow {
    name: String,
    species_name: String,
    assembly_label: String,
    fasta_relpath: String,
    fai_relpath: String,
}

#[derive(Debug)]
struct DatasetRow {
    name: String,
    assembler: String,
    assembler_version: Option<String>,
    fasta_relpath: String,
    fai_relpath: String,
    self_alignment_available: bool,
}

#[derive(Debug, Clone)]
struct PackageRow {
    package_mode: String,
    sequence_layout: String,
    preassigned_chr: bool,
    chr_assignment_min_coverage_percent: f64,
    self_alignment_scope: String,
    cross_alignment_scope: String,
}

#[derive(Debug, Clone)]
struct AddDatasetManifest {
    dataset_name: String,
    reference_name: String,
    sequence_layout: String,
    preassigned_chr: bool,
    chr_assignment_min_coverage_percent: f64,
    alignment_engine: String,
    minimap_preset: String,
    blastn_task: String,
    blastn_evalue: String,
    blastn_dust: String,
    winnowmap_preset: String,
    winnowmap_kmer: String,
    winnowmap_repeat_fraction: String,
    skip_self: bool,
    self_alignment_available: bool,
    tel_enabled: bool,
    cen_enabled: bool,
}

#[derive(Debug, Clone)]
struct AddCtgManifest {
    ctg_name: String,
    derived_dataset: String,
    target_chr: String,
    target_track: String,
    source: String,
    reference_name: String,
    alignment_engine: String,
    minimap_preset: String,
    blastn_task: String,
    blastn_evalue: String,
    blastn_dust: String,
    winnowmap_preset: String,
    winnowmap_kmer: String,
    winnowmap_repeat_fraction: String,
    skip_self: bool,
    self_alignment_scope: String,
    cross_alignment_scope: String,
    sequence_layout: String,
    preassigned_chr: bool,
    contains_fasta: bool,
}

#[derive(Debug, Clone)]
struct DerivedCtgRow {
    derived_dataset: String,
    ctg_name: String,
    source: String,
    source_fasta_name: String,
    source_fasta_sha256: String,
    created_at: String,
}

#[derive(Debug, Clone)]
struct TrackMemberRow {
    member_dataset: String,
    member_ctg: String,
    target_chr: String,
    target_track: String,
    member_role: String,
    created_at: String,
}

#[derive(Debug, Clone)]
struct ValidatedAddCtgPackage {
    target_dataset_id: i64,
    chr_order: i64,
    source_length: i64,
    anchor_start: i64,
}

#[derive(Debug, Clone)]
struct AddCtgCatalogAppend {
    dataset_id: i64,
    source_seq_id: i64,
}

#[derive(Debug, Clone)]
struct ImportedChrAssignmentRow {
    dataset_name: String,
    seq_name: String,
    seq_length_bp: i64,
    assigned_chr_name: String,
    support_bp: i64,
    support_percent: f64,
    anchor_start: i64,
}

#[derive(Debug, Clone)]
struct ReferenceChrLocatorRow {
    reference_chr_name: String,
    fasta_relpath: String,
}

#[derive(Debug, Clone)]
struct SourceSeqLocatorRow {
    dataset_name: String,
    seq_name: String,
    fasta_relpath: String,
}

#[derive(Debug, Clone)]
struct SourceSeqNRegionRow {
    dataset_name: String,
    seq_name: String,
    start_bp: i64,
    end_bp: i64,
    length_bp: i64,
}

#[derive(Debug, Clone)]
struct TelomereRuleRow {
    rule_id: String,
    motif: String,
    min_repeat: i64,
    reverse_complement: bool,
}

#[derive(Debug, Clone)]
struct TelomereMarkRow {
    rule_id: String,
    dataset_name: String,
    seq_name: String,
    assigned_chr_name: String,
    motif: String,
    min_repeat: i64,
    repeat_count: i64,
    start_bp: i64,
    end_bp: i64,
    strand: String,
}

#[derive(Debug, Clone)]
struct CentromereMarkRow {
    cen_id: String,
    assigned_chr_name: String,
    query_name: String,
    dataset_name: String,
    seq_name: String,
    start_bp: i64,
    end_bp: i64,
    strand: String,
    align_length: i64,
    identity: f64,
    mapq: i64,
}

#[derive(Debug, Clone)]
struct FaiRow {
    seq_name: String,
    length: i64,
    seq_order: i64,
}

struct ImportProgressWriter<'a, P>
where
    P: FnMut(ImportProgress),
{
    progress: Vec<ImportProgress>,
    on_progress: &'a mut P,
    log_path: Option<PathBuf>,
    emitted_count: usize,
    expected_total: Option<usize>,
}

pub fn import_from_extracted_bundle(path: &Path) -> Result<(ImportOutcome, Vec<ImportProgress>)> {
    import_from_extracted_bundle_with_hooks(path, &mut |_| {}, &mut || false)
}

pub fn import_from_extracted_bundle_with_hooks<P, C>(
    path: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(ImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut recorder = ImportProgressWriter::new(on_progress);
    recorder.record("validate_input", format!("extract_path={}", path.display()));
    recorder.reserve_remaining(6);

    let resolved = resolve_extracted_bundle_workspace(path)?;
    check_import_cancel(should_cancel)?;
    recorder.record(
        "resolve_bundle_root",
        format!(
            "bundle_root={}, workspace_root={}",
            resolved.bundle_root.display(),
            resolved.workspace_root.display()
        ),
    );

    let project_db_path = initialize_workspace_layout(&resolved.workspace_root)?;
    recorder.enable_log(&resolved.workspace_root)?;
    check_import_cancel(should_cancel)?;
    sync_catalog_from_bundle(&project_db_path, &resolved.bundle_root)?;
    recorder.record(
        "prepare_workspace",
        format!(
            "workspace prepared: project_db={}",
            project_db_path.display()
        ),
    );

    index_alignment_payloads_from_bundle(
        &project_db_path,
        &resolved.bundle_root,
        &mut recorder,
        should_cancel,
    )?;

    recorder.record(
        "complete",
        "import mode=extracted_bundle completed".to_string(),
    );

    Ok((
        ImportOutcome {
            mode: ImportMode::ExtractedBundle,
            bundle_root: resolved.bundle_root,
            workspace_root: resolved.workspace_root,
            project_db_path,
        },
        recorder.into_progress(),
    ))
}

pub fn import_from_zip(
    zip_path: &Path,
    workspace_root: &Path,
) -> Result<(ImportOutcome, Vec<ImportProgress>)> {
    import_from_zip_with_hooks(zip_path, workspace_root, &mut |_| {}, &mut || false)
}

pub fn import_from_zip_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(ImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut recorder = ImportProgressWriter::new(on_progress);
    recorder.record(
        "validate_input",
        format!(
            "zip_path={}, workspace_root={}",
            zip_path.display(),
            workspace_root.display(),
        ),
    );

    validate_zip_path(zip_path)?;
    let archive_entry_count = count_zip_entries(zip_path)?;
    recorder.reserve_remaining(archive_entry_count + 5);

    ensure_workspace_root_can_be_created(workspace_root)?;
    fs::create_dir_all(workspace_root).with_context(|| {
        format!(
            "failed to create workspace root at {}",
            workspace_root.display()
        )
    })?;
    recorder.enable_log(workspace_root)?;
    recorder.record(
        "prepare_workspace_root",
        format!("workspace_root={}", workspace_root.display()),
    );

    unzip_delivery_to_root(
        zip_path,
        workspace_root,
        &mut |step| recorder.record_step(step),
        should_cancel,
    )?;
    recorder.record(
        "extract_bundle",
        format!("zip extracted to {}", workspace_root.display()),
    );

    let detected_bundle_root = resolve_bundle_root_dir(workspace_root)?;
    check_import_cancel(should_cancel)?;
    recorder.record(
        "resolve_bundle_root",
        format!("bundle_root={}", detected_bundle_root.display()),
    );

    if detected_bundle_root != workspace_root {
        promote_bundle_root_to_workspace_root(workspace_root, &detected_bundle_root)?;
        recorder.record(
            "normalize_workspace_layout",
            format!(
                "promoted {} into {}",
                detected_bundle_root.display(),
                workspace_root.display()
            ),
        );
    }

    let project_db_path = initialize_workspace_layout(workspace_root)?;
    check_import_cancel(should_cancel)?;
    sync_catalog_from_bundle(&project_db_path, workspace_root)?;
    recorder.record(
        "prepare_workspace",
        format!(
            "workspace prepared: project_db={}",
            project_db_path.display()
        ),
    );

    index_alignment_payloads_from_bundle(
        &project_db_path,
        workspace_root,
        &mut recorder,
        should_cancel,
    )?;

    recorder.record("complete", "import mode=zip_delivery completed".to_string());

    Ok((
        ImportOutcome {
            mode: ImportMode::ZipDelivery,
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path,
        },
        recorder.into_progress(),
    ))
}

pub fn import_add_dataset_package(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)> {
    import_add_dataset_package_internal(
        zip_path,
        workspace_root,
        Some(project_id),
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_workspace_add_dataset_package(
    zip_path: &Path,
    workspace_root: &Path,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)> {
    import_workspace_add_dataset_package_with_hooks(
        zip_path,
        workspace_root,
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_add_dataset_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_dataset_package_internal(
        zip_path,
        workspace_root,
        Some(project_id),
        on_progress,
        should_cancel,
    )
}

pub fn import_workspace_add_dataset_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_dataset_package_internal(zip_path, workspace_root, None, on_progress, should_cancel)
}

pub fn import_add_ctg_package(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)> {
    import_add_ctg_package_with_hooks(
        zip_path,
        workspace_root,
        project_id,
        None,
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_add_ctg_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    expected_target: Option<AddCtgImportTarget>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_ctg_package_internal(
        zip_path,
        workspace_root,
        project_id,
        expected_target,
        on_progress,
        should_cancel,
    )
}

fn import_add_dataset_package_internal<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: Option<i64>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    validate_zip_path(zip_path)?;
    if !workspace_root.is_dir() {
        bail!(
            "workspace root does not exist for add package import: {}",
            workspace_root.display()
        );
    }
    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.is_file() {
        bail!(
            "workspace is missing project db for add package import: {}",
            project_db_path.display()
        );
    }

    let mut recorder = ImportProgressWriter::new(on_progress);
    let archive_entry_count = count_zip_entries(zip_path)?;
    recorder.reserve_remaining(archive_entry_count + 8);
    recorder.enable_log(workspace_root)?;
    recorder.record(
        "validate_input",
        format!(
            "add_zip_path={}, workspace_root={}, project_id={}",
            zip_path.display(),
            workspace_root.display(),
            project_id
                .map(|id| id.to_string())
                .unwrap_or_else(|| "-".to_string()),
        ),
    );

    let extract_root = workspace_root
        .join(CACHE_DIR)
        .join(format!("add_import_{}", current_unix_millis_string()));
    fs::create_dir_all(&extract_root).with_context(|| {
        format!(
            "failed to create add package extraction dir {}",
            extract_root.display()
        )
    })?;
    unzip_delivery_to_root(
        zip_path,
        &extract_root,
        &mut |step| recorder.record_step(step),
        should_cancel,
    )?;
    recorder.record(
        "extract_add_package",
        format!("zip extracted to {}", extract_root.display()),
    );

    let manifest = read_add_dataset_manifest(&extract_root)?;
    let payload_root = extract_root.join("gpm_server");
    validate_add_dataset_package(
        &project_db_path,
        workspace_root,
        project_id,
        &manifest,
        &payload_root,
    )?;
    recorder.record(
        "validate_add_manifest",
        format!("dataset_name={}", manifest.dataset_name),
    );
    let should_update_assembly = match project_id {
        Some(project_id) => project_has_assembly_rows(&project_db_path, project_id)?,
        None => false,
    };

    let mut rollback = AddImportRollback::capture(workspace_root, &project_db_path, &payload_root)?;
    let import_result = (|| -> Result<i64> {
        copy_add_payload_into_workspace(&payload_root, workspace_root)?;
        recorder.record(
            "merge_add_payload",
            format!("payload merged into {}", workspace_root.display()),
        );

        let dataset_id = append_catalog_from_add_payload(
            &project_db_path,
            workspace_root,
            &payload_root,
            project_id,
            &manifest,
        )?;
        recorder.record(
            "sync_add_catalog",
            format!(
                "dataset_name={}, dataset_id={dataset_id}",
                manifest.dataset_name
            ),
        );

        if let Some(project_id) = project_id.filter(|_| should_update_assembly) {
            let assembly_summary = crate::project_initializer::append_project_dataset_assembly(
                &project_db_path,
                project_id,
                dataset_id,
            )?;
            recorder.record(
                "append_assembly",
                format!(
                    "dataset_name={}, assembly_seq_count={}, assembly_ctg_count={}",
                    manifest.dataset_name,
                    assembly_summary.assembly_seq_count,
                    assembly_summary.assembly_ctg_count
                ),
            );
        }

        index_add_alignment_payloads(
            &project_db_path,
            workspace_root,
            dataset_id,
            &manifest.dataset_name,
            &mut recorder,
            should_cancel,
        )?;

        if let Some(project_id) = project_id.filter(|_| should_update_assembly) {
            let orient_summary = crate::auto_orientation::auto_orient_contigs_for_dataset(
                &project_db_path,
                project_id,
                dataset_id,
                &crate::auto_orientation::AutoOrientContigsParams::default(),
            )?;
            recorder.record(
                "auto_orient_dataset",
                format!(
                    "dataset_name={}, processed_ctg_count={}, oriented_ctg_count={}, flipped_ctg_count={}",
                    manifest.dataset_name,
                    orient_summary.processed_ctg_count,
                    orient_summary.oriented_ctg_count,
                    orient_summary.flipped_ctg_count
                ),
            );
        }
        Ok(dataset_id)
    })();
    let dataset_id = match import_result {
        Ok(dataset_id) => {
            rollback.disarm()?;
            dataset_id
        }
        Err(error) => {
            if let Err(rollback_error) = rollback.rollback() {
                bail!(
                    "add dataset import failed and rollback failed: {error}; rollback error: {rollback_error}"
                );
            }
            let _ = fs::remove_dir_all(&extract_root);
            return Err(error);
        }
    };
    recorder.record(
        "complete",
        format!(
            "import mode=add_dataset completed dataset={}",
            manifest.dataset_name
        ),
    );

    let _ = fs::remove_dir_all(&extract_root);
    Ok((
        AddDatasetImportOutcome {
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path,
            project_id,
            dataset_id,
            dataset_name: manifest.dataset_name,
        },
        recorder.into_progress(),
    ))
}

fn import_add_ctg_package_internal<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    expected_target: Option<AddCtgImportTarget>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    validate_zip_path(zip_path)?;
    if !workspace_root.is_dir() {
        bail!(
            "workspace root does not exist for add_ctg import: {}",
            workspace_root.display()
        );
    }
    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.is_file() {
        bail!(
            "workspace is missing project db for add_ctg import: {}",
            project_db_path.display()
        );
    }

    let mut recorder = ImportProgressWriter::new(on_progress);
    let archive_entry_count = count_zip_entries(zip_path)?;
    recorder.reserve_remaining(archive_entry_count + 8);
    recorder.enable_log(workspace_root)?;
    recorder.record(
        "validate_input",
        format!(
            "add_ctg_zip_path={}, workspace_root={}, project_id={project_id}",
            zip_path.display(),
            workspace_root.display(),
        ),
    );

    let extract_root = workspace_root
        .join(CACHE_DIR)
        .join(format!("add_ctg_import_{}", current_unix_millis_string()));
    fs::create_dir_all(&extract_root).with_context(|| {
        format!(
            "failed to create add_ctg package extraction dir {}",
            extract_root.display()
        )
    })?;
    unzip_delivery_to_root(
        zip_path,
        &extract_root,
        &mut |step| recorder.record_step(step),
        should_cancel,
    )?;
    recorder.record(
        "extract_add_ctg_package",
        format!("zip extracted to {}", extract_root.display()),
    );

    let manifest = read_add_ctg_manifest(&extract_root)?;
    validate_expected_add_ctg_target(&manifest, expected_target.as_ref())?;
    let payload_root = extract_root.join("gpm_server");
    let validated = validate_add_ctg_package(
        &project_db_path,
        workspace_root,
        project_id,
        &manifest,
        &payload_root,
    )?;
    recorder.record(
        "validate_add_ctg_manifest",
        format!(
            "ctg_name={}, target_track={}, target_chr={}",
            manifest.ctg_name, manifest.target_track, manifest.target_chr
        ),
    );
    let should_update_assembly = project_has_assembly_rows(&project_db_path, project_id)?;

    let mut rollback = AddImportRollback::capture(workspace_root, &project_db_path, &payload_root)?;
    let import_result = (|| -> Result<AddCtgImportOutcome> {
        copy_add_ctg_payload_into_workspace(&payload_root, workspace_root)?;
        recorder.record(
            "merge_add_ctg_payload",
            format!("payload merged into {}", workspace_root.display()),
        );

        let catalog = append_catalog_from_add_ctg_payload(
            &project_db_path,
            workspace_root,
            &payload_root,
            project_id,
            &manifest,
            &validated,
        )?;
        recorder.record(
            "sync_add_ctg_catalog",
            format!(
                "ctg_name={}, source_seq_id={}, dataset_id={}",
                manifest.ctg_name, catalog.source_seq_id, catalog.dataset_id
            ),
        );

        let assembly_ctg_id = if should_update_assembly {
            let assembly_ctg_id = append_project_derived_ctg_assembly(
                &project_db_path,
                project_id,
                catalog.source_seq_id,
                &manifest.ctg_name,
                &manifest.target_chr,
                validated.chr_order,
                validated.anchor_start,
            )?;
            recorder.record(
                "append_derived_ctg_assembly",
                format!(
                    "ctg_name={}, assembly_ctg_id={assembly_ctg_id}",
                    manifest.ctg_name
                ),
            );
            Some(assembly_ctg_id)
        } else {
            None
        };

        index_add_ctg_alignment_payloads(
            &project_db_path,
            workspace_root,
            &payload_root,
            &manifest,
            &validated,
            &catalog,
            project_id,
            &mut recorder,
            should_cancel,
        )?;

        Ok(AddCtgImportOutcome {
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path: project_db_path.clone(),
            project_id,
            dataset_id: catalog.dataset_id,
            source_seq_id: catalog.source_seq_id,
            assembly_ctg_id,
            ctg_name: manifest.ctg_name.clone(),
            target_track: manifest.target_track.clone(),
            target_chr: manifest.target_chr.clone(),
        })
    })();
    let outcome = match import_result {
        Ok(outcome) => {
            rollback.disarm()?;
            outcome
        }
        Err(error) => {
            if let Err(rollback_error) = rollback.rollback() {
                bail!(
                    "add_ctg import failed and rollback failed: {error}; rollback error: {rollback_error}"
                );
            }
            let _ = fs::remove_dir_all(&extract_root);
            return Err(error);
        }
    };

    recorder.record(
        "complete",
        format!("import mode=add_ctg completed ctg={}", manifest.ctg_name),
    );
    let _ = fs::remove_dir_all(&extract_root);
    Ok((outcome, recorder.into_progress()))
}

fn validate_expected_add_ctg_target(
    manifest: &AddCtgManifest,
    expected_target: Option<&AddCtgImportTarget>,
) -> Result<()> {
    let Some(expected) = expected_target else {
        return Ok(());
    };
    let expected_chr = expected.target_chr.trim();
    let expected_track = expected.target_track.trim();
    if expected_chr.is_empty() && expected_track.is_empty() {
        return Ok(());
    }
    if manifest.target_chr != expected_chr || manifest.target_track != expected_track {
        bail!(
            "该 add_ctg 包属于 {} / {} 轨道，不能导入到当前 {} / {} 轨道。",
            manifest.target_chr,
            manifest.target_track,
            if expected_chr.is_empty() { "-" } else { expected_chr },
            if expected_track.is_empty() { "-" } else { expected_track }
        );
    }
    Ok(())
}

impl<'a, P> ImportProgressWriter<'a, P>
where
    P: FnMut(ImportProgress),
{
    fn new(on_progress: &'a mut P) -> Self {
        Self {
            progress: Vec::new(),
            on_progress,
            log_path: None,
            emitted_count: 0,
            expected_total: None,
        }
    }

    fn reserve_remaining(&mut self, remaining_count: usize) {
        self.set_expected_total(self.progress.len() + remaining_count);
    }

    fn set_expected_total(&mut self, total: usize) {
        let normalized = total.max(self.progress.len());
        self.expected_total = Some(normalized);
    }

    fn enable_log(&mut self, workspace_root: &Path) -> Result<()> {
        let cache_dir = workspace_root.join(CACHE_DIR);
        fs::create_dir_all(&cache_dir).with_context(|| {
            format!(
                "failed to create import log cache dir under {}",
                workspace_root.display()
            )
        })?;
        let log_path = cache_dir.join("import.log");
        append_import_log_line(
            &log_path,
            &format!(
                "# import_session\t{}",
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|duration| duration.as_millis().to_string())
                    .unwrap_or_else(|_| "0".to_string())
            ),
        )?;
        for step in &self.progress {
            append_import_log_step(&log_path, step)?;
        }
        self.log_path = Some(log_path);
        Ok(())
    }

    fn record(&mut self, stage: &'static str, detail: String) {
        self.record_step(step(stage, detail));
    }

    fn record_step(&mut self, mut item: ImportProgress) {
        self.emitted_count += 1;
        let progress_index = self.emitted_count;
        let progress_total = self
            .expected_total
            .unwrap_or(progress_index)
            .max(progress_index);
        item.progress_index = Some(progress_index);
        item.progress_total = Some(progress_total);
        (self.on_progress)(item.clone());
        if let Some(log_path) = self.log_path.as_deref() {
            let _ = append_import_log_step(log_path, &item);
        }
        self.progress.push(item);
    }

    fn into_progress(mut self) -> Vec<ImportProgress> {
        let final_total = self
            .expected_total
            .unwrap_or(self.progress.len())
            .max(self.progress.len());
        for (index, step) in self.progress.iter_mut().enumerate() {
            step.progress_index = Some(index + 1);
            step.progress_total = Some(final_total);
        }
        self.progress
    }
}

fn append_import_log_step(path: &Path, step: &ImportProgress) -> Result<()> {
    append_import_log_line(path, &format!("{}\t{}", step.stage, step.detail))
}

fn append_import_log_line(path: &Path, line: &str) -> Result<()> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open import log {}", path.display()))?;
    writeln!(file, "{line}")
        .with_context(|| format!("failed to write import log {}", path.display()))?;
    Ok(())
}

#[derive(Debug, Clone)]
struct PairwiseImportRun {
    run_name: String,
    paf_path: PathBuf,
    query_dataset_id: i64,
    target_dataset_id: i64,
}

fn index_alignment_payloads_from_bundle<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let ref_run_count = count_bundle_ref_alignment_runs(&conn, bundle_root)?;
    let pairwise_runs = discover_pairwise_import_runs(&conn, bundle_root)?;
    recorder.reserve_remaining(1 + ref_run_count + 1 + pairwise_runs.len() + 2);
    conn.execute("DELETE FROM ref_alignment_hit", [])
        .context("failed to clear old ref alignment hits before import indexing")?;
    conn.execute("DELETE FROM pairwise_alignment_run", [])
        .context("failed to clear old pairwise alignment runs before import indexing")?;
    recorder.record(
        "index_alignment_reset",
        "cleared previous alignment indexes".to_string(),
    );
    let ref_summary = index_bundle_ref_alignment_hits_with_cancel(
        &mut conn,
        bundle_root,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    let mut indexed_run_count = 0_i64;
    let mut indexed_hit_count = 0_i64;
    for run in pairwise_runs {
        check_import_cancel(should_cancel)?;
        recorder.record(
            "index_pairwise_paf",
            format!(
                "{} ({})",
                run.run_name,
                path_relative_to(bundle_root, &run.paf_path)
            ),
        );
        let cache = ensure_pairwise_alignment_run_cache_cancel(
            &mut conn,
            run.query_dataset_id,
            run.target_dataset_id,
            &run.run_name,
            &run.paf_path,
            should_cancel,
        )?;
        indexed_run_count += 1;
        indexed_hit_count += cache.hit_count;
    }
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={}, indexed_hits={}",
            indexed_run_count, indexed_hit_count
        ),
    );
    Ok(())
}

fn count_bundle_ref_alignment_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<usize> {
    let mut stmt = conn
        .prepare("SELECT name FROM dataset ORDER BY id")
        .context("failed to prepare dataset list for ref paf import progress")?;
    let dataset_names = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for ref paf import progress")?;
    Ok(dataset_names
        .iter()
        .filter(|dataset_name| {
            bundle_root
                .join("runs")
                .join(format!("{}_vs_ref", dataset_name))
                .join("result.paf")
                .exists()
        })
        .count())
}

fn discover_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        run_orientation_by_name.insert(
            format!("{}_vs_self", target_name),
            (*target_dataset_id, *target_dataset_id),
        );
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}

fn index_add_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    dataset_id: i64,
    dataset_name: &str,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs =
        discover_pairwise_import_runs_for_dataset(&conn, bundle_root, dataset_id, dataset_name)?;
    recorder.reserve_remaining(1 + pairwise_runs.len() + 2);
    let ref_summary = index_bundle_ref_alignment_hits_for_dataset_with_cancel(
        &mut conn,
        bundle_root,
        dataset_id,
        dataset_name,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    let mut indexed_run_count = 0_i64;
    let mut indexed_hit_count = 0_i64;
    for run in pairwise_runs {
        check_import_cancel(should_cancel)?;
        recorder.record(
            "index_pairwise_paf",
            format!(
                "{} ({})",
                run.run_name,
                path_relative_to(bundle_root, &run.paf_path)
            ),
        );
        let cache = ensure_pairwise_alignment_run_cache_cancel(
            &mut conn,
            run.query_dataset_id,
            run.target_dataset_id,
            &run.run_name,
            &run.paf_path,
            should_cancel,
        )?;
        indexed_run_count += 1;
        indexed_hit_count += cache.hit_count;
    }
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={}, indexed_hits={}",
            indexed_run_count, indexed_hit_count
        ),
    );
    Ok(())
}

fn index_add_ctg_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    _payload_root: &Path,
    manifest: &AddCtgManifest,
    _validated: &ValidatedAddCtgPackage,
    catalog: &AddCtgCatalogAppend,
    project_id: i64,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs = if manifest.skip_self {
        Vec::new()
    } else {
        discover_add_ctg_pairwise_import_runs(&conn, bundle_root, project_id, manifest)?
    };
    recorder.reserve_remaining(2 + if pairwise_runs.is_empty() { 0 } else { pairwise_runs.len() + 1 });
    let ref_run_name = format!("{}_vs_ref", manifest.ctg_name);
    let ref_paf_path = bundle_root
        .join("runs")
        .join("add_ctg")
        .join(&ref_run_name)
        .join("result.paf");
    recorder.record(
        "index_ref_paf",
        format!("{} ({})", ref_run_name, path_relative_to(bundle_root, &ref_paf_path)),
    );
    let loaded_ref_hits = index_ref_alignment_hits_for_source_seq_with_cancel(
        &mut conn,
        catalog.dataset_id,
        catalog.source_seq_id,
        &manifest.ctg_name,
        &ref_run_name,
        &ref_paf_path,
        should_cancel,
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!("loaded_datasets=1, loaded_hits={loaded_ref_hits}, skipped_datasets=0"),
    );

    if !pairwise_runs.is_empty() {
        let mut indexed_run_count = 0_i64;
        let mut indexed_hit_count = 0_i64;
        for run in pairwise_runs {
            check_import_cancel(should_cancel)?;
            recorder.record(
                "index_pairwise_paf",
                format!(
                    "{} ({})",
                    run.run_name,
                    path_relative_to(bundle_root, &run.paf_path)
                ),
            );
            let cache = ensure_pairwise_alignment_run_cache_cancel(
                &mut conn,
                catalog.dataset_id,
                run.target_dataset_id,
                &run.run_name,
                &run.paf_path,
                should_cancel,
            )?;
            indexed_run_count += 1;
            indexed_hit_count += cache.hit_count;
        }
        recorder.record(
            "index_pairwise_paf_complete",
            format!(
                "indexed_runs={}, indexed_hits={}",
                indexed_run_count, indexed_hit_count
            ),
        );
    }
    Ok(())
}

fn discover_add_ctg_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = required_add_ctg_pairwise_datasets(conn, project_id, &manifest.target_chr)?;
    let mut runs = Vec::new();
    for (target_dataset_id, target_dataset_name) in datasets {
        let pair_run_name = format!("{}_vs_{}", target_dataset_name, manifest.ctg_name);
        let pair_paf_path = bundle_root
            .join("runs")
            .join(format!("chr_{}", manifest.target_chr))
            .join("add_ctg")
            .join(&pair_run_name)
            .join("result.paf");
        if !pair_paf_path.is_file() {
            bail!(
                "add_ctg payload is missing chr-group pairwise alignment payload: {}",
                pair_paf_path.display()
            );
        }
        runs.push(PairwiseImportRun {
            run_name: pair_run_name,
            paf_path: pair_paf_path,
            query_dataset_id: 0,
            target_dataset_id,
        });
    }
    runs.sort_by(|a, b| a.run_name.cmp(&b.run_name));
    Ok(runs)
}

fn required_add_ctg_pairwise_datasets(
    conn: &rusqlite::Connection,
    project_id: i64,
    target_chr: &str,
) -> Result<Vec<(i64, String)>> {
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT d.id, d.name
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             JOIN source_seq ss ON ss.dataset_id = d.id
             JOIN imported_chr_assignment ica ON ica.source_seq_id = ss.id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             WHERE pd.project_id = ?1
               AND rc.chr_name = ?2
               AND d.name <> 'derived_ctg'
             ORDER BY d.id",
        )
        .context("failed to prepare add_ctg required pairwise dataset query")?;
    stmt.query_map(params![project_id, target_chr], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode add_ctg required pairwise datasets")
}

fn discover_pairwise_import_runs_for_dataset(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    added_dataset_id: i64,
    added_dataset_name: &str,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for add-package pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for add-package pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        if *target_dataset_id == added_dataset_id {
            run_orientation_by_name.insert(
                format!("{}_vs_self", target_name),
                (*target_dataset_id, *target_dataset_id),
            );
        }
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            if *target_dataset_id != added_dataset_id && *query_dataset_id != added_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            if !run_name.contains(added_dataset_name) {
                continue;
            }
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}

fn path_relative_to(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn step(stage: &'static str, detail: String) -> ImportProgress {
    ImportProgress {
        stage,
        detail,
        progress_index: None,
        progress_total: None,
    }
}

fn current_unix_millis_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

fn now_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

fn count_zip_entries(zip_path: &Path) -> Result<usize> {
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    Ok(archive.len())
}

fn check_import_cancel(should_cancel: &mut impl FnMut() -> bool) -> Result<()> {
    if should_cancel() {
        bail!("import cancelled");
    }
    Ok(())
}

fn validate_zip_path(zip_path: &Path) -> Result<()> {
    if !zip_path.exists() {
        bail!("zip file does not exist: {}", zip_path.display());
    }

    if !zip_path.is_file() {
        bail!("zip path is not a file: {}", zip_path.display());
    }

    let extension = zip_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension != "zip" {
        bail!("expected a .zip file, got: {}", zip_path.display());
    }

    Ok(())
}

fn ensure_workspace_root_can_be_created(workspace_root: &Path) -> Result<()> {
    if !workspace_root.exists() {
        return Ok(());
    }

    if !workspace_root.is_dir() {
        bail!(
            "workspace root path exists and is not a directory: {}",
            workspace_root.display()
        );
    }

    let mut entries = fs::read_dir(workspace_root).with_context(|| {
        format!(
            "failed to inspect existing workspace root {}",
            workspace_root.display()
        )
    })?;
    if entries.next().is_some() {
        bail!(
            "workspace root already exists and is not empty: {}",
            workspace_root.display()
        );
    }

    Ok(())
}

fn unzip_delivery_to_root(
    zip_path: &Path,
    extract_root: &Path,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let mut archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    let archive_len = archive.len();

    for index in 0..archive_len {
        check_import_cancel(should_cancel)?;
        let mut entry = archive.by_index(index).with_context(|| {
            format!(
                "failed to read zip entry index {} from {}",
                index,
                zip_path.display()
            )
        })?;

        let enclosed = entry.enclosed_name().ok_or_else(|| {
            anyhow::anyhow!("zip entry contains unsafe path traversal: {}", entry.name())
        })?;

        let output_path = extract_root.join(enclosed);
        on_progress(step("extract_entry", entry.name().to_string()));
        if entry.name().ends_with('/') {
            fs::create_dir_all(&output_path).with_context(|| {
                format!(
                    "failed to create extracted directory {}",
                    output_path.display()
                )
            })?;
            continue;
        }

        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create extracted file parent {}",
                    parent.display()
                )
            })?;
        }

        let mut output = File::create(&output_path).with_context(|| {
            format!("failed to create extracted file {}", output_path.display())
        })?;
        io::copy(&mut entry, &mut output).with_context(|| {
            format!(
                "failed to extract zip entry {} to {}",
                entry.name(),
                output_path.display()
            )
        })?;
    }

    Ok(())
}

fn promote_bundle_root_to_workspace_root(workspace_root: &Path, bundle_root: &Path) -> Result<()> {
    if bundle_root == workspace_root {
        return Ok(());
    }

    if bundle_root.parent() != Some(workspace_root) {
        bail!(
            "unsupported zip layout: bundle root {} is not a direct child of workspace root {}",
            bundle_root.display(),
            workspace_root.display()
        );
    }

    let entries = fs::read_dir(bundle_root)
        .with_context(|| format!("failed to read bundle root {}", bundle_root.display()))?;
    for entry in entries {
        let entry = entry.with_context(|| {
            format!(
                "failed to read bundle entry under {}",
                bundle_root.display()
            )
        })?;
        let source = entry.path();
        let target = workspace_root.join(entry.file_name());
        if target.exists() {
            bail!(
                "cannot promote bundle entry; target already exists: {}",
                target.display()
            );
        }
        fs::rename(&source, &target).with_context(|| {
            format!(
                "failed to move bundle entry {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }

    fs::remove_dir(bundle_root).with_context(|| {
        format!(
            "failed to remove now-empty promoted bundle root {}",
            bundle_root.display()
        )
    })?;

    Ok(())
}

fn initialize_workspace_layout(workspace_root: &Path) -> Result<PathBuf> {
    fs::create_dir_all(workspace_root).with_context(|| {
        format!(
            "failed to create workspace root {}",
            workspace_root.display()
        )
    })?;
    fs::create_dir_all(workspace_root.join(EXPORTS_DIR)).with_context(|| {
        format!(
            "failed to create exports dir under {}",
            workspace_root.display()
        )
    })?;
    fs::create_dir_all(workspace_root.join(CACHE_DIR)).with_context(|| {
        format!(
            "failed to create cache dir under {}",
            workspace_root.display()
        )
    })?;

    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.exists() {
        File::create(&project_db_path).with_context(|| {
            format!(
                "failed to create project db placeholder at {}",
                project_db_path.display()
            )
        })?;
    }

    Ok(project_db_path)
}

fn sync_catalog_from_bundle(project_db_path: &Path, bundle_root: &Path) -> Result<()> {
    let references = read_reference_rows(bundle_root)?;
    if references.is_empty() {
        bail!("metadata/reference.tsv contains no reference rows");
    }

    let datasets = read_dataset_rows(bundle_root)?;
    if datasets.is_empty() {
        bail!("metadata/datasets.tsv contains no dataset rows");
    }
    let package = read_package_row(bundle_root)?;
    let chr_assignments = read_imported_chr_assignment_rows(bundle_root)?;
    let reference_chr_locators = read_reference_chr_locator_rows(bundle_root)?;
    let source_seq_locators = read_source_seq_locator_rows(bundle_root)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(bundle_root)?;
    let telomere_rules = read_telomere_rule_rows(bundle_root)?;
    let telomere_marks = read_telomere_mark_rows(bundle_root)?;
    let centromere_marks = read_centromere_mark_rows(bundle_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start catalog sync transaction")?;

    for reference in references {
        let fasta_path = bundle_root.join(&reference.fasta_relpath);
        let fai_path = bundle_root.join(&reference.fai_relpath);
        tx.execute(
            "INSERT INTO reference_genome (
                name, species_name, assembly_label, fasta_path, fai_path
            ) VALUES (?1, ?2, ?3, ?4, ?5)
            ON CONFLICT(name) DO UPDATE SET
                species_name = excluded.species_name,
                assembly_label = excluded.assembly_label,
                fasta_path = excluded.fasta_path,
                fai_path = excluded.fai_path",
            params![
                reference.name,
                reference.species_name,
                reference.assembly_label,
                path_to_string(&fasta_path)?,
                path_to_string(&fai_path)?
            ],
        )
        .context("failed to upsert reference_genome row from metadata/reference.tsv")?;

        let reference_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_genome WHERE name = ?1",
                params![reference.name],
                |row| row.get(0),
            )
            .context("failed to resolve reference_genome id after upsert")?;
        sync_reference_chr_rows(&tx, reference_id, &fai_path)?;
    }

    for dataset in datasets {
        let fasta_path = bundle_root.join(&dataset.fasta_relpath);
        let fai_path = bundle_root.join(&dataset.fai_relpath);
        tx.execute(
            "INSERT INTO dataset (
                name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT(name) DO UPDATE SET
                assembler = excluded.assembler,
                assembler_version = excluded.assembler_version,
                fasta_path = excluded.fasta_path,
                fai_path = excluded.fai_path,
                self_alignment_available = excluded.self_alignment_available",
            params![
                dataset.name,
                dataset.assembler,
                dataset.assembler_version,
                path_to_string(&fasta_path)?,
                path_to_string(&fai_path)?,
                if dataset.self_alignment_available {
                    1_i64
                } else {
                    0_i64
                }
            ],
        )
        .context("failed to upsert dataset row from metadata/datasets.tsv")?;

        let dataset_id: i64 = tx
            .query_row(
                "SELECT id FROM dataset WHERE name = ?1",
                params![dataset.name],
                |row| row.get(0),
            )
            .context("failed to resolve dataset id after upsert")?;
        sync_source_seq_rows(&tx, dataset_id, &fai_path)?;
    }

    sync_workspace_package_metadata(&tx, &package)?;
    sync_imported_chr_assignment_rows(&tx, &chr_assignments)?;
    sync_reference_chr_locator_rows(&tx, bundle_root, &reference_chr_locators)?;
    sync_source_seq_locator_rows(&tx, bundle_root, &source_seq_locators)?;
    sync_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    sync_telomere_rows(&tx, &telomere_rules, &telomere_marks)?;
    sync_centromere_rows(&tx, &centromere_marks)?;

    tx.commit().context("failed to commit catalog sync")?;
    Ok(())
}

fn read_reference_rows(bundle_root: &Path) -> Result<Vec<ReferenceRow>> {
    let path = bundle_root.join("metadata/reference.tsv");
    read_tsv_rows(&path, |header, cols| {
        let reference_name = value_by_header(header, cols, "reference_name")?;
        let species_name = value_by_header(header, cols, "species_name")?;
        let assembly_label = value_by_header(header, cols, "assembly_label")?;
        let fasta_relpath = value_by_header(header, cols, "fasta_relpath")?;
        let fai_relpath = value_by_header(header, cols, "fai_relpath")?;
        Ok(ReferenceRow {
            name: reference_name,
            species_name,
            assembly_label,
            fasta_relpath,
            fai_relpath,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_dataset_rows(bundle_root: &Path) -> Result<Vec<DatasetRow>> {
    let path = bundle_root.join("metadata/datasets.tsv");
    read_tsv_rows(&path, |header, cols| {
        let dataset_name = value_by_header(header, cols, "dataset_name")?;
        let assembler = value_by_header(header, cols, "assembler")?;
        let assembler_version_raw = value_by_header(header, cols, "assembler_version")?;
        let fasta_relpath = value_by_header(header, cols, "fasta_relpath")?;
        let fai_relpath = value_by_header(header, cols, "fai_relpath")?;
        let self_alignment_available =
            optional_value_by_header(header, cols, "self_alignment_available")
                .map(|value| parse_bool_flag(&value, "self_alignment_available"))
                .transpose()?
                .unwrap_or(true);
        Ok(DatasetRow {
            name: dataset_name,
            assembler,
            assembler_version: if assembler_version_raw.trim().is_empty() {
                None
            } else {
                Some(assembler_version_raw)
            },
            fasta_relpath,
            fai_relpath,
            self_alignment_available,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_package_row(bundle_root: &Path) -> Result<PackageRow> {
    let path = bundle_root.join("metadata/package.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/package.tsv");
    }
    let mut rows = read_tsv_rows(&path, |header, cols| {
        Ok(PackageRow {
            package_mode: optional_value_by_header(header, cols, "package_mode")
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "fast".to_string()),
            sequence_layout: optional_value_by_header(header, cols, "sequence_layout")
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "partitioned".to_string()),
            preassigned_chr: optional_value_by_header(header, cols, "preassigned_chr")
                .map(|value| parse_bool_flag(&value, "preassigned_chr"))
                .transpose()?
                .unwrap_or(true),
            chr_assignment_min_coverage_percent: optional_value_by_header(
                header,
                cols,
                "chr_assignment_min_coverage_percent",
            )
            .map(|value| parse_f64_value(&value, "chr_assignment_min_coverage_percent"))
            .transpose()?
            .unwrap_or(60.0),
            self_alignment_scope: optional_value_by_header(header, cols, "self_alignment_scope")
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "chr_partition".to_string()),
            cross_alignment_scope: optional_value_by_header(header, cols, "cross_alignment_scope")
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "chr_partition".to_string()),
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))?;
    if rows.is_empty() {
        bail!("metadata/package.tsv must contain exactly one data row");
    }
    if rows.len() != 1 {
        bail!("metadata/package.tsv must contain exactly one data row");
    }
    let package = rows.remove(0);
    if !package.sequence_layout.eq_ignore_ascii_case("partitioned") {
        bail!(
            "server delivery package requires sequence_layout=partitioned in metadata/package.tsv"
        );
    }
    if !package.preassigned_chr {
        bail!("server delivery package requires preassigned_chr=true in metadata/package.tsv");
    }
    if !package
        .cross_alignment_scope
        .eq_ignore_ascii_case("chr_partition")
    {
        bail!(
            "server delivery package requires cross_alignment_scope=chr_partition in metadata/package.tsv"
        );
    }
    if !package
        .self_alignment_scope
        .eq_ignore_ascii_case("chr_partition")
        && !package.self_alignment_scope.eq_ignore_ascii_case("none")
    {
        bail!(
            "server delivery package requires self_alignment_scope=chr_partition or none in metadata/package.tsv"
        );
    }
    Ok(package)
}

fn read_add_dataset_manifest(extract_root: &Path) -> Result<AddDatasetManifest> {
    let path = extract_root.join("add_package/manifest.tsv");
    if !path.exists() {
        bail!("add dataset package requires add_package/manifest.tsv");
    }
    let values = read_key_value_tsv(&path)
        .with_context(|| format!("failed to parse add manifest {}", path.display()))?;
    let package_type = required_key_value(&values, "package_type")?;
    if package_type != "add_dataset" {
        bail!(
            "add dataset package requires package_type=add_dataset, got {}",
            package_type
        );
    }
    let dataset_name = required_key_value(&values, "dataset_name")?;
    if dataset_name.trim().is_empty() {
        bail!("add dataset manifest requires dataset_name");
    }
    validate_add_dataset_name(&dataset_name)?;
    let reference_name = required_key_value(&values, "reference_name")?;
    let sequence_layout = required_key_value(&values, "sequence_layout")?;
    let preassigned_chr = parse_bool_flag(
        &required_key_value(&values, "preassigned_chr")?,
        "preassigned_chr",
    )?;
    let chr_assignment_min_coverage_percent = parse_f64_value(
        &required_key_value(&values, "chr_assignment_min_coverage_percent")?,
        "chr_assignment_min_coverage_percent",
    )?;
    let alignment_engine = values
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    let minimap_preset = values
        .get("minimap_preset")
        .cloned()
        .unwrap_or_else(|| "asm10".to_string());
    let blastn_task = values
        .get("blastn_task")
        .cloned()
        .unwrap_or_else(|| "blastn".to_string());
    let blastn_evalue = values
        .get("blastn_evalue")
        .cloned()
        .unwrap_or_else(|| "1e-10".to_string());
    let blastn_dust = values
        .get("blastn_dust")
        .cloned()
        .unwrap_or_else(|| "no".to_string());
    let winnowmap_preset = values
        .get("winnowmap_preset")
        .cloned()
        .unwrap_or_else(|| "asm20".to_string());
    let winnowmap_kmer = values
        .get("winnowmap_kmer")
        .cloned()
        .unwrap_or_else(|| "19".to_string());
    let winnowmap_repeat_fraction = values
        .get("winnowmap_repeat_fraction")
        .cloned()
        .unwrap_or_else(|| "0.9998".to_string());
    let skip_self = parse_bool_flag(&required_key_value(&values, "skip_self")?, "skip_self")?;
    let self_alignment_available = parse_bool_flag(
        &required_key_value(&values, "self_alignment_available")?,
        "self_alignment_available",
    )?;
    let tel_enabled = parse_bool_flag(&required_key_value(&values, "tel_enabled")?, "tel_enabled")?;
    let cen_enabled = parse_bool_flag(&required_key_value(&values, "cen_enabled")?, "cen_enabled")?;
    Ok(AddDatasetManifest {
        dataset_name,
        reference_name,
        sequence_layout,
        preassigned_chr,
        chr_assignment_min_coverage_percent,
        alignment_engine,
        minimap_preset,
        blastn_task,
        blastn_evalue,
        blastn_dust,
        winnowmap_preset,
        winnowmap_kmer,
        winnowmap_repeat_fraction,
        skip_self,
        self_alignment_available,
        tel_enabled,
        cen_enabled,
    })
}

fn read_add_ctg_manifest(extract_root: &Path) -> Result<AddCtgManifest> {
    let path = extract_root.join("add_ctg/manifest.tsv");
    if !path.exists() {
        bail!("add_ctg package requires add_ctg/manifest.tsv");
    }
    let values = read_key_value_tsv(&path)
        .with_context(|| format!("failed to parse add_ctg manifest {}", path.display()))?;
    let package_type = required_key_value(&values, "package_type")?;
    if package_type != "add_ctg" {
        bail!(
            "add_ctg package requires package_type=add_ctg, got {}",
            package_type
        );
    }
    let ctg_name = required_key_value(&values, "ctg_name")?;
    if ctg_name.trim().is_empty() {
        bail!("add_ctg manifest requires ctg_name");
    }
    validate_add_dataset_name(&ctg_name)?;
    let derived_dataset = values
        .get("derived_dataset")
        .cloned()
        .unwrap_or_else(|| "derived_ctg".to_string());
    if derived_dataset != "derived_ctg" {
        bail!(
            "add_ctg manifest derived_dataset must be derived_ctg, got {}",
            derived_dataset
        );
    }
    let target_chr = required_key_value(&values, "target_chr")?;
    validate_add_dataset_name(&target_chr)?;
    let target_track = required_key_value(&values, "target_track")?;
    validate_add_dataset_name(&target_track)?;
    let source = values.get("source").cloned().unwrap_or_default();
    if source.contains('\t') || source.contains('\n') || source.contains('\r') {
        bail!("add_ctg manifest source must not contain tabs or newlines");
    }
    let reference_name = required_key_value(&values, "reference_name")?;
    let alignment_engine = values
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    let minimap_preset = values
        .get("minimap_preset")
        .cloned()
        .unwrap_or_else(|| "asm10".to_string());
    let blastn_task = values
        .get("blastn_task")
        .cloned()
        .unwrap_or_else(|| "blastn".to_string());
    let blastn_evalue = values
        .get("blastn_evalue")
        .cloned()
        .unwrap_or_else(|| "1e-10".to_string());
    let blastn_dust = values
        .get("blastn_dust")
        .cloned()
        .unwrap_or_else(|| "no".to_string());
    let winnowmap_preset = values
        .get("winnowmap_preset")
        .cloned()
        .unwrap_or_else(|| "asm20".to_string());
    let winnowmap_kmer = values
        .get("winnowmap_kmer")
        .cloned()
        .unwrap_or_else(|| "19".to_string());
    let winnowmap_repeat_fraction = values
        .get("winnowmap_repeat_fraction")
        .cloned()
        .unwrap_or_else(|| "0.9998".to_string());
    let skip_self = parse_bool_flag(&required_key_value(&values, "skip_self")?, "skip_self")?;
    let self_alignment_scope = values.get("self_alignment_scope").cloned().unwrap_or_default();
    let cross_alignment_scope = values.get("cross_alignment_scope").cloned().unwrap_or_default();
    let sequence_layout = required_key_value(&values, "sequence_layout")?;
    let preassigned_chr = parse_bool_flag(
        &required_key_value(&values, "preassigned_chr")?,
        "preassigned_chr",
    )?;
    let contains_fasta = values
        .get("contains_fasta")
        .map(|value| parse_bool_flag(value, "contains_fasta"))
        .transpose()?
        .unwrap_or(true);
    Ok(AddCtgManifest {
        ctg_name,
        derived_dataset,
        target_chr,
        target_track,
        source,
        reference_name,
        alignment_engine,
        minimap_preset,
        blastn_task,
        blastn_evalue,
        blastn_dust,
        winnowmap_preset,
        winnowmap_kmer,
        winnowmap_repeat_fraction,
        skip_self,
        self_alignment_scope,
        cross_alignment_scope,
        sequence_layout,
        preassigned_chr,
        contains_fasta,
    })
}

fn validate_add_dataset_package(
    project_db_path: &Path,
    workspace_root: &Path,
    project_id: Option<i64>,
    manifest: &AddDatasetManifest,
    payload_root: &Path,
) -> Result<()> {
    if !payload_root.is_dir() {
        bail!("add dataset package is missing gpm_server payload");
    }
    let conn = open_workspace_db(project_db_path)?;
    let existing_dataset_id = conn
        .query_row(
            "SELECT id FROM dataset WHERE name = ?1",
            params![manifest.dataset_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check existing dataset names")?;
    if existing_dataset_id.is_some() {
        bail!(
            "dataset {} already exists in workspace",
            manifest.dataset_name
        );
    }

    let workspace_reference_name: String = match project_id {
        Some(project_id) => conn
            .query_row(
                "SELECT rg.name
                 FROM project p
                 JOIN reference_genome rg ON rg.id = p.reference_genome_id
                 WHERE p.id = ?1",
                params![project_id],
                |row| row.get(0),
            )
            .with_context(|| format!("failed to resolve project {project_id} reference"))?,
        None => conn
            .query_row(
                "SELECT name FROM reference_genome WHERE name = ?1",
                params![manifest.reference_name],
                |row| row.get(0),
            )
            .optional()
            .context("failed to resolve workspace reference")?
            .with_context(|| {
                format!(
                    "add dataset reference mismatch: manifest reference={} is not present in workspace",
                    manifest.reference_name
                )
            })?,
    };
    if workspace_reference_name != manifest.reference_name {
        bail!(
            "add dataset reference mismatch: manifest reference={} workspace reference={}",
            manifest.reference_name,
            workspace_reference_name
        );
    }

    let package: PackageRow = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr,
                    chr_assignment_min_coverage_percent, self_alignment_scope,
                    cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok(PackageRow {
                    package_mode: row.get(0)?,
                    sequence_layout: row.get(1)?,
                    preassigned_chr: row.get::<_, i64>(2)? != 0,
                    chr_assignment_min_coverage_percent: row.get(3)?,
                    self_alignment_scope: row.get(4)?,
                    cross_alignment_scope: row.get(5)?,
                })
            },
        )
        .context("failed to load workspace package metadata")?;
    if package.sequence_layout != manifest.sequence_layout {
        bail!(
            "add dataset sequence_layout mismatch: manifest={} workspace={}",
            manifest.sequence_layout,
            package.sequence_layout
        );
    }
    if package.preassigned_chr != manifest.preassigned_chr {
        bail!("add dataset preassigned_chr mismatch");
    }
    if (package.chr_assignment_min_coverage_percent - manifest.chr_assignment_min_coverage_percent)
        .abs()
        > f64::EPSILON
    {
        bail!(
            "add dataset chr_assignment_min_coverage_percent mismatch: manifest={} workspace={}",
            manifest.chr_assignment_min_coverage_percent,
            package.chr_assignment_min_coverage_percent
        );
    }
    let workspace_skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    if workspace_skip_self != manifest.skip_self {
        bail!(
            "add dataset skip_self mismatch: manifest={} workspace={}",
            manifest.skip_self,
            workspace_skip_self
        );
    }
    if manifest.self_alignment_available == manifest.skip_self {
        bail!("add dataset self_alignment_available conflicts with skip_self in manifest");
    }

    let prepare_options = read_workspace_prepare_options_for_add(workspace_root, &package)?;
    validate_add_dataset_alignment_engine(&prepare_options, manifest)?;
    if let Some(workspace_skip_self_value) = prepare_options.get("skip_self") {
        let prepare_skip_self = parse_bool_flag(workspace_skip_self_value, "skip_self")?;
        if prepare_skip_self != manifest.skip_self {
            bail!(
                "add dataset skip_self mismatch: manifest={} prepare_options={}",
                manifest.skip_self,
                prepare_skip_self
            );
        }
    }
    validate_prepare_bool_matches(&prepare_options, "tel_enabled", manifest.tel_enabled)?;
    validate_prepare_bool_matches(&prepare_options, "cen_enabled", manifest.cen_enabled)?;

    validate_add_payload_files(&conn, workspace_root, payload_root, manifest)?;
    Ok(())
}

fn validate_add_ctg_package(
    project_db_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    payload_root: &Path,
) -> Result<ValidatedAddCtgPackage> {
    if !payload_root.is_dir() {
        bail!("add_ctg package is missing gpm_server payload");
    }
    if !manifest.contains_fasta {
        bail!("add_ctg import requires contains_fasta=true");
    }

    let conn = open_workspace_db(project_db_path)?;
    let duplicate = conn
        .query_row(
            "SELECT d.name
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE ss.seq_name = ?1
             LIMIT 1",
            params![manifest.ctg_name],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .context("failed to check duplicate add_ctg source names")?;
    if let Some(dataset_name) = duplicate {
        bail!(
            "ctg name already exists: {} (dataset/track: {}). Please choose a different --ctg name.",
            manifest.ctg_name,
            dataset_name
        );
    }

    let (workspace_reference_name, reference_genome_id): (String, i64) = conn
        .query_row(
            "SELECT rg.name, rg.id
             FROM project p
             JOIN reference_genome rg ON rg.id = p.reference_genome_id
             WHERE p.id = ?1",
            params![project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .with_context(|| format!("failed to resolve project {project_id} reference"))?;
    if workspace_reference_name != manifest.reference_name {
        bail!(
            "add_ctg reference mismatch: manifest reference={} workspace reference={}",
            manifest.reference_name,
            workspace_reference_name
        );
    }

    let (target_dataset_id, target_project_count): (i64, i64) = conn
        .query_row(
            "SELECT d.id,
                    COUNT(pd.id)
             FROM dataset d
             LEFT JOIN project_dataset pd
               ON pd.dataset_id = d.id
              AND pd.project_id = ?2
             WHERE d.name = ?1
             GROUP BY d.id",
            params![manifest.target_track, project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .context("failed to resolve add_ctg target track")?
        .with_context(|| format!("add_ctg target track does not exist: {}", manifest.target_track))?;
    if target_project_count == 0 {
        bail!(
            "add_ctg target track {} is not part of project_id {}",
            manifest.target_track,
            project_id
        );
    }

    let (_target_reference_chr_id, chr_order): (i64, i64) = conn
        .query_row(
            "SELECT id, chr_order
             FROM reference_chr
             WHERE reference_genome_id = ?1
               AND chr_name = ?2",
            params![reference_genome_id, manifest.target_chr],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .context("failed to resolve add_ctg target chr")?
        .with_context(|| format!("add_ctg target chr does not exist: {}", manifest.target_chr))?;

    let package: PackageRow = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr,
                    chr_assignment_min_coverage_percent, self_alignment_scope,
                    cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok(PackageRow {
                    package_mode: row.get(0)?,
                    sequence_layout: row.get(1)?,
                    preassigned_chr: row.get::<_, i64>(2)? != 0,
                    chr_assignment_min_coverage_percent: row.get(3)?,
                    self_alignment_scope: row.get(4)?,
                    cross_alignment_scope: row.get(5)?,
                })
            },
        )
        .context("failed to load workspace package metadata")?;
    if package.sequence_layout != manifest.sequence_layout {
        bail!(
            "add_ctg sequence_layout mismatch: manifest={} workspace={}",
            manifest.sequence_layout,
            package.sequence_layout
        );
    }
    if package.preassigned_chr != manifest.preassigned_chr {
        bail!("add_ctg preassigned_chr mismatch");
    }
    if !manifest.self_alignment_scope.is_empty()
        && package.self_alignment_scope != manifest.self_alignment_scope
    {
        bail!(
            "add_ctg self_alignment_scope mismatch: manifest={} workspace={}",
            manifest.self_alignment_scope,
            package.self_alignment_scope
        );
    }
    if !manifest.cross_alignment_scope.is_empty()
        && package.cross_alignment_scope != manifest.cross_alignment_scope
    {
        bail!(
            "add_ctg cross_alignment_scope mismatch: manifest={} workspace={}",
            manifest.cross_alignment_scope,
            package.cross_alignment_scope
        );
    }
    let workspace_skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    if workspace_skip_self != manifest.skip_self {
        bail!(
            "add_ctg skip_self mismatch: manifest={} workspace={}",
            manifest.skip_self,
            workspace_skip_self
        );
    }
    let prepare_options = read_workspace_prepare_options_for_add(workspace_root, &package)?;
    validate_add_ctg_alignment_engine(&prepare_options, manifest)?;
    if let Some(workspace_skip_self_value) = prepare_options.get("skip_self") {
        let prepare_skip_self = parse_bool_flag(workspace_skip_self_value, "skip_self")?;
        if prepare_skip_self != manifest.skip_self {
            bail!(
                "add_ctg skip_self mismatch: manifest={} prepare_options={}",
                manifest.skip_self,
                prepare_skip_self
            );
        }
    }

    validate_add_ctg_payload_files(
        &conn,
        workspace_root,
        payload_root,
        project_id,
        manifest,
        target_dataset_id,
    )?;
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    if chr_assignment.assigned_chr_name != manifest.target_chr {
        bail!(
            "add_ctg chr assignment mismatch: manifest={} payload={}",
            manifest.target_chr,
            chr_assignment.assigned_chr_name
        );
    }
    let derived_row = read_derived_ctg_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing derived_ctgs row")?;
    if derived_row.source != manifest.source {
        bail!(
            "add_ctg source mismatch: manifest={} payload={}",
            manifest.source,
            derived_row.source
        );
    }
    read_single_add_ctg_locator(payload_root, manifest)?;
    Ok(ValidatedAddCtgPackage {
        target_dataset_id,
        chr_order,
        source_length: chr_assignment.seq_length_bp,
        anchor_start: chr_assignment.anchor_start,
    })
}

fn validate_add_dataset_alignment_engine(
    prepare_options: &HashMap<String, String>,
    manifest: &AddDatasetManifest,
) -> Result<()> {
    let workspace_engine = prepare_options
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    if workspace_engine != manifest.alignment_engine {
        bail!(
            "add dataset alignment_engine mismatch: manifest={} workspace={}",
            manifest.alignment_engine,
            workspace_engine
        );
    }

    match workspace_engine.as_str() {
        "minimap2" => validate_prepare_string_matches(
            prepare_options,
            "minimap_preset",
            &manifest.minimap_preset,
            "asm10",
        ),
        "blastn" => {
            validate_prepare_string_matches(
                prepare_options,
                "blastn_task",
                &manifest.blastn_task,
                "blastn",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "blastn_evalue",
                &manifest.blastn_evalue,
                "1e-10",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "blastn_dust",
                &manifest.blastn_dust,
                "no",
            )
        }
        "winnowmap" => {
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_preset",
                &manifest.winnowmap_preset,
                "asm20",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_kmer",
                &manifest.winnowmap_kmer,
                "19",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_repeat_fraction",
                &manifest.winnowmap_repeat_fraction,
                "0.9998",
            )
        }
        other => bail!("unsupported workspace alignment_engine: {other}"),
    }
}

fn validate_add_ctg_alignment_engine(
    prepare_options: &HashMap<String, String>,
    manifest: &AddCtgManifest,
) -> Result<()> {
    let workspace_engine = prepare_options
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    if workspace_engine != manifest.alignment_engine {
        bail!(
            "add_ctg alignment_engine mismatch: manifest={} workspace={}",
            manifest.alignment_engine,
            workspace_engine
        );
    }

    match workspace_engine.as_str() {
        "minimap2" => validate_prepare_string_matches_for_package(
            "add_ctg",
            prepare_options,
            "minimap_preset",
            &manifest.minimap_preset,
            "asm10",
        ),
        "blastn" => {
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_task",
                &manifest.blastn_task,
                "blastn",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_evalue",
                &manifest.blastn_evalue,
                "1e-10",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_dust",
                &manifest.blastn_dust,
                "no",
            )
        }
        "winnowmap" => {
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_preset",
                &manifest.winnowmap_preset,
                "asm20",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_kmer",
                &manifest.winnowmap_kmer,
                "19",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_repeat_fraction",
                &manifest.winnowmap_repeat_fraction,
                "0.9998",
            )
        }
        other => bail!("unsupported workspace alignment_engine: {other}"),
    }
}

fn read_workspace_prepare_options_for_add(
    workspace_root: &Path,
    package: &PackageRow,
) -> Result<HashMap<String, String>> {
    let prepare_options_path = workspace_root.join("metadata/prepare_options.tsv");
    if prepare_options_path.exists() {
        return read_key_value_tsv(&prepare_options_path).with_context(|| {
            format!(
                "failed to parse workspace prepare options {}",
                prepare_options_path.display()
            )
        });
    }

    let skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    let mut values = HashMap::new();
    values.insert("alignment_engine".to_string(), "minimap2".to_string());
    values.insert("minimap_preset".to_string(), "asm10".to_string());
    values.insert("blastn_task".to_string(), "blastn".to_string());
    values.insert("blastn_evalue".to_string(), "1e-10".to_string());
    values.insert("blastn_dust".to_string(), "no".to_string());
    values.insert("winnowmap_preset".to_string(), "asm20".to_string());
    values.insert("winnowmap_kmer".to_string(), "19".to_string());
    values.insert("winnowmap_repeat_fraction".to_string(), "0.9998".to_string());
    values.insert("skip_self".to_string(), skip_self.to_string());
    values.insert(
        "self_alignment_scope".to_string(),
        package.self_alignment_scope.clone(),
    );
    values.insert("tel_enabled".to_string(), "false".to_string());
    values.insert("cen_enabled".to_string(), "false".to_string());
    Ok(values)
}

fn validate_prepare_string_matches(
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: &str,
    default_value: &str,
) -> Result<()> {
    let prepare_value = prepare_options
        .get(key)
        .map(String::as_str)
        .unwrap_or(default_value);
    if prepare_value != manifest_value {
        bail!(
            "add dataset {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}

fn validate_prepare_string_matches_for_package(
    package_label: &str,
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: &str,
    default_value: &str,
) -> Result<()> {
    let prepare_value = prepare_options
        .get(key)
        .map(String::as_str)
        .unwrap_or(default_value);
    if prepare_value != manifest_value {
        bail!(
            "{package_label} {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}

fn validate_prepare_bool_matches(
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: bool,
) -> Result<()> {
    let prepare_value = parse_bool_flag(&required_key_value(prepare_options, key)?, key)?;
    if prepare_value != manifest_value {
        bail!(
            "add dataset {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}

fn validate_add_payload_files(
    conn: &rusqlite::Connection,
    workspace_root: &Path,
    payload_root: &Path,
    manifest: &AddDatasetManifest,
) -> Result<()> {
    let dataset_rows = read_dataset_rows(payload_root)?;
    if dataset_rows.len() != 1 || dataset_rows[0].name != manifest.dataset_name {
        bail!(
            "add dataset payload metadata/datasets.tsv must contain only dataset {}",
            manifest.dataset_name
        );
    }
    let chr_assignment_rows = read_imported_chr_assignment_rows(payload_root)?;
    if chr_assignment_rows.is_empty()
        || chr_assignment_rows
            .iter()
            .any(|row| row.dataset_name != manifest.dataset_name)
    {
        bail!(
            "add dataset payload metadata/chr_assignments.tsv is missing rows for {}",
            manifest.dataset_name
        );
    }
    let locator_rows = read_source_seq_locator_rows(payload_root)?;
    if locator_rows.is_empty()
        || locator_rows
            .iter()
            .any(|row| row.dataset_name != manifest.dataset_name)
    {
        bail!(
            "add dataset payload metadata/source_seq_locator.tsv is missing rows for {}",
            manifest.dataset_name
        );
    }
    let locator_source_names = locator_rows
        .iter()
        .map(|row| (row.dataset_name.clone(), row.seq_name.clone()))
        .collect::<HashSet<_>>();
    let dataset = &dataset_rows[0];
    if dataset.self_alignment_available != manifest.self_alignment_available {
        bail!(
            "add dataset self_alignment_available mismatch: manifest={} payload={}",
            manifest.self_alignment_available,
            dataset.self_alignment_available
        );
    }
    validate_add_payload_relpath("dataset fasta_relpath", &dataset.fasta_relpath)?;
    validate_add_payload_relpath("dataset fai_relpath", &dataset.fai_relpath)?;
    require_payload_file(payload_root, &dataset.fasta_relpath)?;
    require_payload_file(payload_root, &dataset.fai_relpath)?;
    require_payload_file(
        payload_root,
        &format!("runs/{}_vs_ref/result.paf", manifest.dataset_name),
    )?;
    for locator in &locator_rows {
        validate_add_payload_relpath("source_seq_locator fasta_relpath", &locator.fasta_relpath)?;
        require_payload_file(payload_root, &locator.fasta_relpath)?;
    }
    if manifest.tel_enabled && !payload_root.join("tel").exists() {
        bail!("add dataset payload is missing tel payload");
    }
    if manifest.cen_enabled && !payload_root.join("cen").exists() {
        bail!("add dataset payload is missing cen payload");
    }
    let telomere_rules = read_telomere_rule_rows(payload_root)?;
    let telomere_marks = read_telomere_mark_rows(payload_root)?;
    let centromere_marks = read_centromere_mark_rows(payload_root)?;
    let n_regions = read_source_seq_n_region_rows(payload_root)?;
    validate_add_n_region_payload(manifest, &locator_source_names, &n_regions)?;
    validate_add_telomere_payload(
        manifest,
        &locator_source_names,
        &telomere_rules,
        &telomere_marks,
    )?;
    validate_add_centromere_payload(manifest, &locator_source_names, &centromere_marks)?;
    validate_add_alignment_payloads(conn, payload_root, manifest, &chr_assignment_rows)?;
    validate_add_payload_merge_targets(payload_root, workspace_root, payload_root)?;
    Ok(())
}

fn validate_add_ctg_payload_files(
    conn: &rusqlite::Connection,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    target_dataset_id: i64,
) -> Result<()> {
    let dataset_rows = read_dataset_rows(payload_root)?;
    if dataset_rows.len() != 1 || dataset_rows[0].name != manifest.derived_dataset {
        bail!(
            "add_ctg payload metadata/datasets.tsv must contain only dataset {}",
            manifest.derived_dataset
        );
    }
    let derived_rows = read_derived_ctg_rows(payload_root)?;
    if derived_rows.len() != 1
        || derived_rows[0].derived_dataset != manifest.derived_dataset
        || derived_rows[0].ctg_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/derived_ctgs.tsv must contain only ctg {}",
            manifest.ctg_name
        );
    }
    let member_rows = read_track_member_rows(payload_root)?;
    if member_rows.len() != 1
        || member_rows[0].member_dataset != manifest.derived_dataset
        || member_rows[0].member_ctg != manifest.ctg_name
        || member_rows[0].target_track != manifest.target_track
        || member_rows[0].target_chr != manifest.target_chr
    {
        bail!(
            "add_ctg payload metadata/track_members.tsv must bind {} to {}:{}",
            manifest.ctg_name,
            manifest.target_track,
            manifest.target_chr
        );
    }
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    let locator = read_single_add_ctg_locator(payload_root, manifest)?;
    let locator_source_names = HashSet::from([(
        manifest.derived_dataset.clone(),
        manifest.ctg_name.clone(),
    )]);
    let n_regions = read_source_seq_n_region_rows(payload_root)?;
    validate_add_ctg_n_region_payload(manifest, &locator_source_names, &n_regions)?;

    validate_add_payload_relpath("derived source_seq_locator fasta_relpath", &locator.fasta_relpath)?;
    require_payload_file(payload_root, &locator.fasta_relpath)?;
    require_payload_file(payload_root, &format!("{}.fai", locator.fasta_relpath))?;
    require_payload_file(
        payload_root,
        &format!("runs/add_ctg/{}_vs_ref/result.paf", manifest.ctg_name),
    )?;
    require_payload_file(
        payload_root,
        &format!(
            "runs/chr_{}/datasets/{}.fa",
            manifest.target_chr, manifest.derived_dataset
        ),
    )?;
    if !manifest.skip_self {
        let required_pairwise_datasets =
            required_add_ctg_pairwise_datasets(conn, project_id, &manifest.target_chr)?;
        if !required_pairwise_datasets
            .iter()
            .any(|(dataset_id, _name)| *dataset_id == target_dataset_id)
        {
            bail!(
                "add_ctg target track {} has no ctgs on target chr {}",
                manifest.target_track,
                manifest.target_chr
            );
        }
        for (_dataset_id, dataset_name) in required_pairwise_datasets {
            require_payload_file(
                payload_root,
                &format!(
                    "runs/chr_{}/add_ctg/{}_vs_{}/result.paf",
                    manifest.target_chr, dataset_name, manifest.ctg_name
                ),
            )?;
        }
    }

    if chr_assignment.seq_length_bp <= 0 {
        bail!("add_ctg payload seq_length_bp must be > 0");
    }
    validate_add_ctg_payload_merge_targets(payload_root, workspace_root, payload_root)?;
    let target_dataset_exists = conn
        .query_row(
            "SELECT id FROM dataset WHERE id = ?1",
            params![target_dataset_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to verify add_ctg target dataset")?;
    if target_dataset_exists.is_none() {
        bail!("add_ctg target dataset no longer exists");
    }
    Ok(())
}

fn validate_add_ctg_n_region_payload(
    manifest: &AddCtgManifest,
    locator_source_names: &HashSet<(String, String)>,
    regions: &[SourceSeqNRegionRow],
) -> Result<()> {
    for region in regions {
        if region.dataset_name != manifest.derived_dataset || region.seq_name != manifest.ctg_name {
            bail!(
                "add_ctg n payload contains row for {}, expected {}:{}",
                region.seq_name,
                manifest.derived_dataset,
                manifest.ctg_name
            );
        }
        if !locator_source_names.contains(&(region.dataset_name.clone(), region.seq_name.clone())) {
            bail!(
                "add_ctg n payload contains row for unknown source {}:{}",
                region.dataset_name,
                region.seq_name
            );
        }
    }
    Ok(())
}

fn validate_add_alignment_payloads(
    conn: &rusqlite::Connection,
    payload_root: &Path,
    manifest: &AddDatasetManifest,
    chr_assignment_rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    let assigned_chrs = chr_assignment_rows
        .iter()
        .map(|row| row.assigned_chr_name.clone())
        .collect::<HashSet<_>>();
    for chr_name in assigned_chrs {
        let chr_run_root = payload_root.join("runs").join(format!("chr_{}", chr_name));
        let self_paf = chr_run_root
            .join(format!("{}_vs_self", manifest.dataset_name))
            .join("result.paf");
        if manifest.skip_self {
            if self_paf.exists() {
                bail!(
                    "add dataset payload contains self alignment while skip_self=true: {}",
                    self_paf.display()
                );
            }
        } else if !self_paf.is_file() {
            bail!(
                "add dataset payload is missing self alignment payload for {} chr {}",
                manifest.dataset_name,
                chr_name
            );
        }

        let existing_dataset_names =
            existing_dataset_names_with_chr_assignment(conn, &chr_name, &manifest.dataset_name)?;
        for existing_name in existing_dataset_names {
            let existing_vs_added = chr_run_root
                .join(format!("{}_vs_{}", existing_name, manifest.dataset_name))
                .join("result.paf");
            let added_vs_existing = chr_run_root
                .join(format!("{}_vs_{}", manifest.dataset_name, existing_name))
                .join("result.paf");
            if !existing_vs_added.is_file() && !added_vs_existing.is_file() {
                bail!(
                    "add dataset payload is missing pairwise alignment payload for {} and {} chr {}",
                    manifest.dataset_name,
                    existing_name,
                    chr_name
                );
            }
        }
    }
    Ok(())
}

fn existing_dataset_names_with_chr_assignment(
    conn: &rusqlite::Connection,
    chr_name: &str,
    added_dataset_name: &str,
) -> Result<Vec<String>> {
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT d.name
             FROM imported_chr_assignment ica
             JOIN source_seq ss ON ss.id = ica.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             WHERE rc.chr_name = ?1
               AND d.name <> ?2
             ORDER BY d.id",
        )
        .context("failed to prepare existing dataset chr-assignment lookup")?;
    stmt.query_map(params![chr_name, added_dataset_name], |row| row.get(0))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode existing dataset chr-assignment rows")
}

fn validate_add_telomere_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    if !manifest.tel_enabled && (!rules.is_empty() || !marks.is_empty()) {
        bail!("add dataset tel payload is present but manifest tel_enabled=false");
    }
    for mark in marks {
        validate_add_marker_dataset_source(
            "tel",
            &manifest.dataset_name,
            locator_source_names,
            &mark.dataset_name,
            &mark.seq_name,
        )?;
    }
    Ok(())
}

fn validate_add_centromere_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    marks: &[CentromereMarkRow],
) -> Result<()> {
    if !manifest.cen_enabled && !marks.is_empty() {
        bail!("add dataset cen payload is present but manifest cen_enabled=false");
    }
    for mark in marks {
        validate_add_marker_dataset_source(
            "cen",
            &manifest.dataset_name,
            locator_source_names,
            &mark.dataset_name,
            &mark.seq_name,
        )?;
    }
    Ok(())
}

fn validate_add_marker_dataset_source(
    payload_name: &str,
    manifest_dataset_name: &str,
    locator_source_names: &HashSet<(String, String)>,
    dataset_name: &str,
    seq_name: &str,
) -> Result<()> {
    if dataset_name != manifest_dataset_name {
        bail!(
            "add dataset {payload_name} payload contains row for dataset {}, expected {}",
            dataset_name,
            manifest_dataset_name
        );
    }
    if !locator_source_names.contains(&(dataset_name.to_string(), seq_name.to_string())) {
        bail!(
            "add dataset {payload_name} payload contains row for unknown source {}:{}",
            dataset_name,
            seq_name
        );
    }
    Ok(())
}

fn validate_add_n_region_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    regions: &[SourceSeqNRegionRow],
) -> Result<()> {
    for region in regions {
        validate_add_marker_dataset_source(
            "n",
            &manifest.dataset_name,
            locator_source_names,
            &region.dataset_name,
            &region.seq_name,
        )?;
    }
    Ok(())
}

fn validate_add_payload_merge_targets(
    payload_root: &Path,
    workspace_root: &Path,
    path: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            validate_add_payload_merge_targets(payload_root, workspace_root, &source)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if !is_allowed_add_payload_file(&rel) {
            bail!("unexpected add dataset payload file: {}", rel);
        }
        if is_appendable_add_payload_tsv(&rel) || rel == "tel/rules.tsv" {
            continue;
        }
        let target = workspace_root.join(relpath);
        if target.exists() {
            bail!(
                "add dataset payload target already exists: {}",
                target.display()
            );
        }
    }
    Ok(())
}

fn validate_add_ctg_payload_merge_targets(
    payload_root: &Path,
    workspace_root: &Path,
    path: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add_ctg payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            validate_add_ctg_payload_merge_targets(payload_root, workspace_root, &source)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add_ctg payload path {}", source.display())
        })?;
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if !is_allowed_add_ctg_payload_file(&rel) {
            bail!("unexpected add_ctg payload file: {}", rel);
        }
        if is_appendable_add_ctg_payload_tsv(&rel)
            || is_appendable_add_ctg_fasta(&rel)
            || is_appendable_add_ctg_fai(&rel)
            || rel == "metadata/datasets.tsv"
        {
            continue;
        }
        let target = workspace_root.join(relpath);
        if target.exists() {
            bail!("add_ctg payload target already exists: {}", target.display());
        }
    }
    Ok(())
}

fn require_payload_file(payload_root: &Path, relpath: &str) -> Result<()> {
    validate_add_payload_relpath("payload file", relpath)?;
    if !payload_root.join(relpath).is_file() {
        bail!("add dataset payload is missing {}", relpath);
    }
    Ok(())
}

fn validate_add_dataset_name(dataset_name: &str) -> Result<()> {
    if dataset_name.contains('/') || dataset_name.contains('\\') {
        bail!(
            "add dataset manifest dataset_name must not contain path separators: {}",
            dataset_name
        );
    }
    let name_path = Path::new(dataset_name);
    if name_path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!(
            "add dataset manifest dataset_name must be a plain name: {}",
            dataset_name
        );
    }
    Ok(())
}

fn validate_add_payload_relpath(field_name: &str, relpath: &str) -> Result<()> {
    let path = Path::new(relpath);
    if relpath.trim().is_empty() || path.is_absolute() {
        bail!("add dataset payload {field_name} must be a relative path: {relpath}");
    }
    if relpath.contains('\\') {
        bail!("add dataset payload {field_name} contains unsafe path separator: {relpath}");
    }
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_) | Component::CurDir))
    {
        bail!("add dataset payload {field_name} contains unsafe path traversal: {relpath}");
    }
    Ok(())
}

fn read_imported_chr_assignment_rows(bundle_root: &Path) -> Result<Vec<ImportedChrAssignmentRow>> {
    let path = bundle_root.join("metadata/chr_assignments.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/chr_assignments.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(ImportedChrAssignmentRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            seq_length_bp: value_by_header(header, cols, "seq_length_bp")?
                .parse()
                .with_context(|| "invalid seq_length_bp".to_string())?,
            assigned_chr_name: value_by_header(header, cols, "assigned_chr_name")?,
            support_bp: value_by_header(header, cols, "support_bp")?
                .parse()
                .with_context(|| "invalid support_bp".to_string())?,
            support_percent: parse_f64_value(
                &value_by_header(header, cols, "support_percent")?,
                "support_percent",
            )?,
            anchor_start: value_by_header(header, cols, "anchor_start")?
                .parse()
                .with_context(|| "invalid anchor_start".to_string())?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_reference_chr_locator_rows(bundle_root: &Path) -> Result<Vec<ReferenceChrLocatorRow>> {
    let path = bundle_root.join("metadata/reference_chr_locator.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/reference_chr_locator.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(ReferenceChrLocatorRow {
            reference_chr_name: value_by_header(header, cols, "reference_chr_name")?,
            fasta_relpath: value_by_header(header, cols, "fasta_relpath")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_source_seq_locator_rows(bundle_root: &Path) -> Result<Vec<SourceSeqLocatorRow>> {
    let path = bundle_root.join("metadata/source_seq_locator.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/source_seq_locator.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(SourceSeqLocatorRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            fasta_relpath: value_by_header(header, cols, "fasta_relpath")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_derived_ctg_rows(bundle_root: &Path) -> Result<Vec<DerivedCtgRow>> {
    let path = bundle_root.join("metadata/derived_ctgs.tsv");
    if !path.exists() {
        bail!("add_ctg package requires metadata/derived_ctgs.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(DerivedCtgRow {
            derived_dataset: value_by_header(header, cols, "derived_dataset")?,
            ctg_name: value_by_header(header, cols, "ctg_name")?,
            source: value_by_header(header, cols, "source")?,
            source_fasta_name: value_by_header(header, cols, "source_fasta_name")?,
            source_fasta_sha256: value_by_header(header, cols, "source_fasta_sha256")?,
            created_at: value_by_header(header, cols, "created_at")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_track_member_rows(bundle_root: &Path) -> Result<Vec<TrackMemberRow>> {
    let path = bundle_root.join("metadata/track_members.tsv");
    if !path.exists() {
        bail!("add_ctg package requires metadata/track_members.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(TrackMemberRow {
            member_dataset: value_by_header(header, cols, "member_dataset")?,
            member_ctg: value_by_header(header, cols, "member_ctg")?,
            target_chr: value_by_header(header, cols, "target_chr")?,
            target_track: value_by_header(header, cols, "target_track")?,
            member_role: value_by_header(header, cols, "member_role")?,
            created_at: value_by_header(header, cols, "created_at")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_single_add_ctg_chr_assignment(
    payload_root: &Path,
    manifest: &AddCtgManifest,
) -> Result<ImportedChrAssignmentRow> {
    let rows = read_imported_chr_assignment_rows(payload_root)?;
    if rows.len() != 1
        || rows[0].dataset_name != manifest.derived_dataset
        || rows[0].seq_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/chr_assignments.tsv must contain only {}:{}",
            manifest.derived_dataset,
            manifest.ctg_name
        );
    }
    Ok(rows[0].clone())
}

fn read_single_add_ctg_locator(
    payload_root: &Path,
    manifest: &AddCtgManifest,
) -> Result<SourceSeqLocatorRow> {
    let rows = read_source_seq_locator_rows(payload_root)?;
    if rows.len() != 1
        || rows[0].dataset_name != manifest.derived_dataset
        || rows[0].seq_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/source_seq_locator.tsv must contain only {}:{}",
            manifest.derived_dataset,
            manifest.ctg_name
        );
    }
    Ok(rows[0].clone())
}

fn read_source_seq_n_region_rows(bundle_root: &Path) -> Result<Vec<SourceSeqNRegionRow>> {
    let path = bundle_root.join("metadata/source_seq_n_regions.tsv");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_tsv_rows(&path, |header, cols| {
        let start_bp = value_by_header(header, cols, "start_bp")?
            .parse()
            .with_context(|| "invalid n region start_bp".to_string())?;
        let end_bp = value_by_header(header, cols, "end_bp")?
            .parse()
            .with_context(|| "invalid n region end_bp".to_string())?;
        let length_bp = value_by_header(header, cols, "length_bp")?
            .parse()
            .with_context(|| "invalid n region length_bp".to_string())?;
        if start_bp < 1 || end_bp < start_bp || length_bp != end_bp - start_bp + 1 {
            bail!(
                "invalid n region coordinates start_bp={} end_bp={} length_bp={}",
                start_bp,
                end_bp,
                length_bp
            );
        }
        Ok(SourceSeqNRegionRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            start_bp,
            end_bp,
            length_bp,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_telomere_rule_rows(bundle_root: &Path) -> Result<Vec<TelomereRuleRow>> {
    let path = bundle_root.join("tel/rules.tsv");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(TelomereRuleRow {
            rule_id: value_by_header(header, cols, "rule_id")?,
            motif: value_by_header(header, cols, "motif")?,
            min_repeat: value_by_header(header, cols, "min_repeat")?
                .parse()
                .with_context(|| "invalid tel min_repeat".to_string())?,
            reverse_complement: optional_value_by_header(header, cols, "reverse_complement")
                .map(|value| parse_bool_flag(&value, "reverse_complement"))
                .transpose()?
                .unwrap_or(true),
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

fn read_telomere_mark_rows(bundle_root: &Path) -> Result<Vec<TelomereMarkRow>> {
    let tel_root = bundle_root.join("tel");
    if !tel_root.exists() {
        return Ok(Vec::new());
    }
    let mut rows = Vec::new();
    for entry in fs::read_dir(&tel_root)
        .with_context(|| format!("failed to read tel dir {}", tel_root.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read tel entry {}", tel_root.display()))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let dir_name = entry.file_name().to_string_lossy().to_string();
        if !dir_name.starts_with("chr_") {
            continue;
        }
        for mark_entry in fs::read_dir(&path)
            .with_context(|| format!("failed to read tel chr dir {}", path.display()))?
        {
            let mark_entry = mark_entry
                .with_context(|| format!("failed to read tel mark entry {}", path.display()))?;
            let mark_path = mark_entry.path();
            if mark_path.extension().and_then(|value| value.to_str()) != Some("tsv") {
                continue;
            }
            let mut file_rows = read_tsv_rows(&mark_path, |header, cols| {
                let strand = value_by_header(header, cols, "strand")?;
                if strand != "+" && strand != "-" {
                    bail!("invalid tel strand: {}", strand);
                }
                Ok(TelomereMarkRow {
                    rule_id: value_by_header(header, cols, "rule_id")?,
                    dataset_name: value_by_header(header, cols, "dataset_name")?,
                    seq_name: value_by_header(header, cols, "seq_name")?,
                    assigned_chr_name: value_by_header(header, cols, "assigned_chr_name")?,
                    motif: value_by_header(header, cols, "motif")?,
                    min_repeat: value_by_header(header, cols, "min_repeat")?
                        .parse()
                        .with_context(|| "invalid tel mark min_repeat".to_string())?,
                    repeat_count: value_by_header(header, cols, "repeat_count")?
                        .parse()
                        .with_context(|| "invalid tel repeat_count".to_string())?,
                    start_bp: value_by_header(header, cols, "start_bp")?
                        .parse()
                        .with_context(|| "invalid tel start_bp".to_string())?,
                    end_bp: value_by_header(header, cols, "end_bp")?
                        .parse()
                        .with_context(|| "invalid tel end_bp".to_string())?,
                    strand,
                })
            })
            .with_context(|| format!("failed to parse {}", mark_path.display()))?;
            rows.append(&mut file_rows);
        }
    }
    Ok(rows)
}

fn read_centromere_mark_rows(bundle_root: &Path) -> Result<Vec<CentromereMarkRow>> {
    let cen_root = bundle_root.join("cen");
    if !cen_root.exists() {
        return Ok(Vec::new());
    }
    let mut rows = Vec::new();
    for entry in fs::read_dir(&cen_root)
        .with_context(|| format!("failed to read cen dir {}", cen_root.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read cen entry {}", cen_root.display()))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let dir_name = entry.file_name().to_string_lossy().to_string();
        if !dir_name.starts_with("chr_") {
            continue;
        }
        let mark_path = path.join("marks.tsv");
        if !mark_path.exists() {
            continue;
        }
        let mut file_rows = read_tsv_rows(&mark_path, |header, cols| {
            let strand = value_by_header(header, cols, "strand")?;
            if strand != "+" && strand != "-" {
                bail!("invalid cen strand: {}", strand);
            }
            Ok(CentromereMarkRow {
                cen_id: value_by_header(header, cols, "cen_id")?,
                assigned_chr_name: value_by_header(header, cols, "chr_name")?,
                query_name: value_by_header(header, cols, "query_name")?,
                dataset_name: value_by_header(header, cols, "dataset_name")?,
                seq_name: value_by_header(header, cols, "ctg_name")?,
                start_bp: value_by_header(header, cols, "ctg_start")?
                    .parse()
                    .with_context(|| "invalid cen ctg_start".to_string())?,
                end_bp: value_by_header(header, cols, "ctg_end")?
                    .parse()
                    .with_context(|| "invalid cen ctg_end".to_string())?,
                strand,
                align_length: value_by_header(header, cols, "align_length")?
                    .parse()
                    .with_context(|| "invalid cen align_length".to_string())?,
                identity: value_by_header(header, cols, "identity")?
                    .parse()
                    .with_context(|| "invalid cen identity".to_string())?,
                mapq: value_by_header(header, cols, "mapq")?
                    .parse()
                    .with_context(|| "invalid cen mapq".to_string())?,
            })
        })
        .with_context(|| format!("failed to parse {}", mark_path.display()))?;
        rows.append(&mut file_rows);
    }
    Ok(rows)
}

fn read_tsv_rows<T, F>(path: &Path, mut mapper: F) -> Result<Vec<T>>
where
    F: FnMut(&[String], &[String]) -> Result<T>,
{
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut lines = reader.lines();

    let header_line = lines
        .next()
        .transpose()
        .with_context(|| format!("failed to read header from {}", path.display()))?
        .ok_or_else(|| anyhow::anyhow!("missing header in {}", path.display()))?;
    let header: Vec<String> = header_line
        .split('\t')
        .map(|value| value.trim().to_string())
        .collect();

    let mut rows = Vec::new();
    for (index, line) in lines.enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 2, path.display())
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let cols: Vec<String> = line.split('\t').map(ToString::to_string).collect();
        let row = mapper(&header, &cols).with_context(|| {
            format!(
                "failed to decode line {} from {}",
                index + 2,
                path.display()
            )
        })?;
        rows.push(row);
    }

    Ok(rows)
}

fn read_key_value_tsv(path: &Path) -> Result<HashMap<String, String>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut values = HashMap::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 1, path.display())
        })?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let cols = trimmed.split('\t').collect::<Vec<_>>();
        if index == 0 && cols == ["key", "value"] {
            continue;
        }
        if cols.len() != 2 {
            bail!(
                "invalid key/value row at {}:{} => {}",
                path.display(),
                index + 1,
                line
            );
        }
        values.insert(cols[0].trim().to_string(), cols[1].trim().to_string());
    }
    Ok(values)
}

fn required_key_value(values: &HashMap<String, String>, key: &str) -> Result<String> {
    values
        .get(key)
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("missing required key '{}'", key))
}

fn value_by_header(header: &[String], cols: &[String], expected: &str) -> Result<String> {
    let index = header
        .iter()
        .position(|value| value == expected)
        .ok_or_else(|| anyhow::anyhow!("missing required header '{}'", expected))?;
    let value = cols
        .get(index)
        .ok_or_else(|| anyhow::anyhow!("missing value for column '{}'", expected))?;
    Ok(value.trim().to_string())
}

fn optional_value_by_header(header: &[String], cols: &[String], expected: &str) -> Option<String> {
    let index = header.iter().position(|value| value == expected)?;
    cols.get(index).map(|value| value.trim().to_string())
}

fn parse_bool_flag(value: &str, column_name: &str) -> Result<bool> {
    match value.trim().to_ascii_lowercase().as_str() {
        "" | "1" | "true" | "yes" => Ok(true),
        "0" | "false" | "no" => Ok(false),
        other => bail!(
            "invalid boolean value for column '{}': {}",
            column_name,
            other
        ),
    }
}

fn parse_f64_value(value: &str, column_name: &str) -> Result<f64> {
    value.trim().parse::<f64>().with_context(|| {
        format!(
            "invalid numeric value for column '{}': {}",
            column_name, value
        )
    })
}

fn path_to_string(path: &Path) -> Result<String> {
    path.to_str()
        .map(ToString::to_string)
        .ok_or_else(|| anyhow::anyhow!("path contains non-utf8 characters: {}", path.display()))
}

fn sync_workspace_package_metadata(tx: &Transaction<'_>, package: &PackageRow) -> Result<()> {
    tx.execute(
        "INSERT INTO workspace_package_metadata (
            id, package_mode, sequence_layout, preassigned_chr,
            chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
         ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(id) DO UPDATE SET
            package_mode = excluded.package_mode,
            sequence_layout = excluded.sequence_layout,
            preassigned_chr = excluded.preassigned_chr,
            chr_assignment_min_coverage_percent = excluded.chr_assignment_min_coverage_percent,
            self_alignment_scope = excluded.self_alignment_scope,
            cross_alignment_scope = excluded.cross_alignment_scope",
        params![
            package.package_mode,
            package.sequence_layout,
            if package.preassigned_chr {
                1_i64
            } else {
                0_i64
            },
            package.chr_assignment_min_coverage_percent,
            package.self_alignment_scope,
            package.cross_alignment_scope,
        ],
    )
    .context("failed to sync workspace_package_metadata")?;
    Ok(())
}

fn sync_imported_chr_assignment_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    tx.execute("DELETE FROM imported_chr_assignment", [])
        .context("failed to clear imported_chr_assignment rows")?;

    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for imported chr assignment {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.assigned_chr_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve reference_chr for imported chr assignment {}",
                    row.assigned_chr_name
                )
            })?;
        tx.execute(
            "INSERT INTO imported_chr_assignment (
                source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start
             ) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                source_seq_id,
                reference_chr_id,
                row.support_bp,
                row.support_percent,
                row.anchor_start
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert imported chr assignment {}:{} -> {}",
                row.dataset_name, row.seq_name, row.assigned_chr_name
            )
        })?;
    }
    Ok(())
}

fn sync_reference_chr_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[ReferenceChrLocatorRow],
) -> Result<()> {
    tx.execute("DELETE FROM reference_chr_locator", [])
        .context("failed to clear reference_chr_locator rows")?;

    for row in rows {
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.reference_chr_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve reference_chr for locator {}",
                    row.reference_chr_name
                )
            })?;
        let fasta_path = bundle_root.join(&row.fasta_relpath);
        tx.execute(
            "INSERT INTO reference_chr_locator (reference_chr_id, fasta_path)
             VALUES (?1, ?2)
             ON CONFLICT(reference_chr_id) DO UPDATE SET
                fasta_path = excluded.fasta_path",
            params![reference_chr_id, path_to_string(&fasta_path)?],
        )
        .with_context(|| {
            format!(
                "failed to insert reference chr locator for {}",
                row.reference_chr_name
            )
        })?;
    }
    Ok(())
}

fn sync_source_seq_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[SourceSeqLocatorRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_locator", [])
        .context("failed to clear source_seq_locator rows")?;

    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for locator {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let fasta_path = bundle_root.join(&row.fasta_relpath);
        tx.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (?1, ?2)
             ON CONFLICT(source_seq_id) DO UPDATE SET
                fasta_path = excluded.fasta_path",
            params![source_seq_id, path_to_string(&fasta_path)?],
        )
        .with_context(|| {
            format!(
                "failed to insert source seq locator for {}:{}",
                row.dataset_name, row.seq_name
            )
        })?;
    }
    Ok(())
}

fn sync_source_seq_n_region_rows(
    tx: &Transaction<'_>,
    rows: &[SourceSeqNRegionRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_n_region", [])
        .context("failed to clear source_seq_n_region rows")?;

    for row in rows {
        insert_source_seq_n_region_row(tx, row)?;
    }
    Ok(())
}

#[derive(Debug)]
struct AddImportRollback {
    active: bool,
    project_db_path: PathBuf,
    project_db_backup_path: PathBuf,
    file_targets: Vec<(PathBuf, Option<PathBuf>)>,
    created_dirs: Vec<PathBuf>,
    backup_root: PathBuf,
}

impl AddImportRollback {
    fn capture(workspace_root: &Path, project_db_path: &Path, payload_root: &Path) -> Result<Self> {
        let backup_root = workspace_root.join(CACHE_DIR).join(format!(
            "add_import_rollback_{}",
            current_unix_millis_string()
        ));
        fs::create_dir_all(&backup_root).with_context(|| {
            format!(
                "failed to create add import rollback dir {}",
                backup_root.display()
            )
        })?;
        let project_db_backup_path = backup_root.join(PROJECT_DB_NAME);
        fs::copy(project_db_path, &project_db_backup_path).with_context(|| {
            format!(
                "failed to back up project db {} to {}",
                project_db_path.display(),
                project_db_backup_path.display()
            )
        })?;

        let mut targets = Vec::new();
        let mut created_dirs = HashSet::new();
        collect_add_payload_rollback_targets(
            payload_root,
            payload_root,
            workspace_root,
            &backup_root,
            &mut targets,
            &mut created_dirs,
        )?;
        let mut created_dirs = created_dirs.into_iter().collect::<Vec<_>>();
        created_dirs.sort_by_key(|path| std::cmp::Reverse(path.components().count()));

        Ok(Self {
            active: true,
            project_db_path: project_db_path.to_path_buf(),
            project_db_backup_path,
            file_targets: targets,
            created_dirs,
            backup_root,
        })
    }

    fn disarm(&mut self) -> Result<()> {
        self.active = false;
        if self.backup_root.exists() {
            fs::remove_dir_all(&self.backup_root).with_context(|| {
                format!(
                    "failed to remove add import rollback dir {}",
                    self.backup_root.display()
                )
            })?;
        }
        Ok(())
    }

    fn rollback(&mut self) -> Result<()> {
        self.rollback_in_place()
    }

    fn rollback_in_place(&mut self) -> Result<()> {
        if !self.active {
            return Ok(());
        }
        let mut first_error: Option<anyhow::Error> = None;

        for (target, backup) in self.file_targets.iter().rev() {
            let result = if let Some(backup_path) = backup {
                if let Some(parent) = target.parent() {
                    fs::create_dir_all(parent).with_context(|| {
                        format!(
                            "failed to recreate rollback target dir {}",
                            parent.display()
                        )
                    })?;
                }
                fs::copy(backup_path, target).map(|_| ()).with_context(|| {
                    format!(
                        "failed to restore add import file {} from {}",
                        target.display(),
                        backup_path.display()
                    )
                })
            } else if target.exists() {
                fs::remove_file(target).with_context(|| {
                    format!("failed to remove add import file {}", target.display())
                })
            } else {
                Ok(())
            };
            if first_error.is_none() {
                first_error = result.err();
            }
        }

        let db_restore_result = fs::copy(&self.project_db_backup_path, &self.project_db_path)
            .map(|_| ())
            .with_context(|| {
                format!(
                    "failed to restore project db {} from {}",
                    self.project_db_path.display(),
                    self.project_db_backup_path.display()
                )
            });
        if first_error.is_none() {
            first_error = db_restore_result.err();
        }

        for dir in &self.created_dirs {
            if dir.exists() {
                let _ = fs::remove_dir(dir);
            }
        }
        let _ = fs::remove_dir_all(&self.backup_root);
        self.active = false;

        if let Some(error) = first_error {
            Err(error)
        } else {
            Ok(())
        }
    }
}

impl Drop for AddImportRollback {
    fn drop(&mut self) {
        let _ = self.rollback_in_place();
    }
}

fn collect_add_payload_rollback_targets(
    payload_root: &Path,
    path: &Path,
    workspace_root: &Path,
    backup_root: &Path,
    targets: &mut Vec<(PathBuf, Option<PathBuf>)>,
    created_dirs: &mut HashSet<PathBuf>,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            collect_add_payload_rollback_targets(
                payload_root,
                &source,
                workspace_root,
                backup_root,
                targets,
                created_dirs,
            )?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let target = workspace_root.join(relpath);
        record_missing_parent_dirs(workspace_root, &target, created_dirs);
        if target.exists() {
            let backup_path = backup_root.join(format!("file_{}.bak", targets.len()));
            fs::copy(&target, &backup_path).with_context(|| {
                format!(
                    "failed to back up add import target {} to {}",
                    target.display(),
                    backup_path.display()
                )
            })?;
            targets.push((target, Some(backup_path)));
        } else {
            targets.push((target, None));
        }
    }
    Ok(())
}

fn record_missing_parent_dirs(
    workspace_root: &Path,
    target: &Path,
    created_dirs: &mut HashSet<PathBuf>,
) {
    let mut current = target.parent();
    while let Some(dir) = current {
        if dir == workspace_root {
            break;
        }
        if dir.exists() {
            break;
        }
        created_dirs.insert(dir.to_path_buf());
        current = dir.parent();
    }
}

fn copy_add_payload_into_workspace(payload_root: &Path, workspace_root: &Path) -> Result<()> {
    copy_add_payload_entry(payload_root, payload_root, workspace_root)
}

fn copy_add_ctg_payload_into_workspace(payload_root: &Path, workspace_root: &Path) -> Result<()> {
    copy_add_ctg_payload_entry(payload_root, payload_root, workspace_root)
}

fn copy_add_payload_entry(payload_root: &Path, path: &Path, workspace_root: &Path) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            copy_add_payload_entry(payload_root, &source, workspace_root)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let target = workspace_root.join(relpath);
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if is_appendable_add_payload_tsv(&rel) {
            append_tsv_payload_rows(&source, &target)?;
            continue;
        }
        if rel == "tel/rules.tsv" && target.exists() {
            validate_tsv_payload_header(&source, &target)?;
            continue;
        }
        if target.exists() {
            bail!(
                "add dataset payload target already exists: {}",
                target.display()
            );
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create add payload target dir {}",
                    parent.display()
                )
            })?;
        }
        fs::copy(&source, &target).with_context(|| {
            format!(
                "failed to copy add payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }
    Ok(())
}

fn copy_add_ctg_payload_entry(
    payload_root: &Path,
    path: &Path,
    workspace_root: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add_ctg payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            copy_add_ctg_payload_entry(payload_root, &source, workspace_root)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add_ctg payload path {}", source.display())
        })?;
        let target = workspace_root.join(relpath);
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if rel == "metadata/datasets.tsv" {
            append_dataset_tsv_if_new(&source, &target, "derived_ctg")?;
            continue;
        }
        if is_appendable_add_ctg_payload_tsv(&rel) {
            append_tsv_payload_rows(&source, &target)?;
            continue;
        }
        if is_appendable_add_ctg_fasta(&rel) {
            append_fasta_payload_records(&source, &target)?;
            continue;
        }
        if is_appendable_add_ctg_fai(&rel) {
            append_plain_payload_lines(&source, &target)?;
            continue;
        }
        if target.exists() {
            bail!("add_ctg payload target already exists: {}", target.display());
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg payload target dir {}", parent.display())
            })?;
        }
        fs::copy(&source, &target).with_context(|| {
            format!(
                "failed to copy add_ctg payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }
    Ok(())
}

fn is_allowed_add_payload_file(rel: &str) -> bool {
    is_appendable_add_payload_tsv(rel)
        || rel == "tel/rules.tsv"
        || rel.starts_with("data/datasets/")
        || rel.starts_with("data/partitions/")
        || rel.starts_with("runs/")
}

fn is_allowed_add_ctg_payload_file(rel: &str) -> bool {
    rel == "metadata/datasets.tsv"
        || is_appendable_add_ctg_payload_tsv(rel)
        || rel.starts_with("data/derived_ctgs/")
        || rel == "data/datasets/derived_ctg.fa"
        || rel == "data/datasets/derived_ctg.fa.fai"
        || rel.starts_with("runs/add_ctg/")
        || rel.starts_with("runs/chr_")
}

fn is_appendable_add_payload_tsv(rel: &str) -> bool {
    rel == "metadata/datasets.tsv"
        || rel == "metadata/chr_assignments.tsv"
        || rel == "metadata/source_seq_locator.tsv"
        || rel == "metadata/source_seq_n_regions.tsv"
        || (rel.starts_with("tel/chr_") && rel.ends_with(".tsv"))
        || (rel.starts_with("cen/chr_") && rel.ends_with("/marks.tsv"))
}

fn is_appendable_add_ctg_payload_tsv(rel: &str) -> bool {
    rel == "metadata/chr_assignments.tsv"
        || rel == "metadata/source_seq_locator.tsv"
        || rel == "metadata/source_seq_n_regions.tsv"
        || rel == "metadata/derived_ctgs.tsv"
        || rel == "metadata/track_members.tsv"
}

fn is_appendable_add_ctg_fasta(rel: &str) -> bool {
    rel == "data/datasets/derived_ctg.fa"
        || (rel.starts_with("runs/chr_") && rel.ends_with("/datasets/derived_ctg.fa"))
}

fn is_appendable_add_ctg_fai(rel: &str) -> bool {
    rel == "data/datasets/derived_ctg.fa.fai"
}

fn append_tsv_payload_rows(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add payload tsv {}", source.display()))?;
    let mut source_lines = source_text.lines();
    let Some(source_header) = source_lines.next() else {
        bail!("add payload tsv is empty: {}", source.display());
    };
    let rows = source_lines
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if rows.is_empty() {
        return Ok(());
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add payload tsv dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add payload tsv {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }

    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if target_header != source_header {
        bail!("add payload tsv header mismatch for {}", target.display());
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace tsv {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    for row in rows {
        writeln!(file, "{row}")
            .with_context(|| format!("failed to append row to {}", target.display()))?;
    }
    Ok(())
}

fn append_dataset_tsv_if_new(source: &Path, target: &Path, dataset_name: &str) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg dataset tsv {}", source.display()))?;
    let mut source_lines = source_text.lines();
    let Some(source_header) = source_lines.next() else {
        bail!("add_ctg dataset tsv is empty: {}", source.display());
    };
    let source_rows = source_lines
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if source_rows.is_empty() {
        return Ok(());
    }
    if source_rows.len() != 1 || !source_rows[0].starts_with(&format!("{dataset_name}\t")) {
        bail!("add_ctg dataset payload must contain only dataset {dataset_name}");
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg dataset tsv dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg dataset tsv {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }

    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace dataset tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if target_header != source_header {
        bail!("add_ctg dataset tsv header mismatch for {}", target.display());
    }
    let already_present = target_text
        .lines()
        .skip(1)
        .any(|line| line.split('\t').next() == Some(dataset_name));
    if already_present {
        return Ok(());
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace dataset tsv {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    writeln!(file, "{}", source_rows[0])
        .with_context(|| format!("failed to append dataset row to {}", target.display()))?;
    Ok(())
}

fn append_fasta_payload_records(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg fasta {}", source.display()))?;
    if !source_text.lines().any(|line| line.starts_with('>')) {
        bail!("add_ctg fasta payload has no FASTA header: {}", source.display());
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg fasta dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg fasta {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace fasta {}", target.display()))?;
    let source_headers = source_text
        .lines()
        .filter_map(|line| line.strip_prefix('>'))
        .map(|line| line.split_whitespace().next().unwrap_or_default().to_string())
        .collect::<Vec<_>>();
    for header in &source_headers {
        if target_text
            .lines()
            .filter_map(|line| line.strip_prefix('>'))
            .any(|line| line.split_whitespace().next() == Some(header.as_str()))
        {
            bail!("add_ctg fasta target already contains record: {header}");
        }
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace fasta {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    write!(file, "{source_text}")
        .with_context(|| format!("failed to append fasta record to {}", target.display()))?;
    if !source_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to terminate fasta {}", target.display()))?;
    }
    Ok(())
}

fn append_plain_payload_lines(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg payload {}", source.display()))?;
    let rows = source_text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if rows.is_empty() {
        return Ok(());
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg payload dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace payload {}", target.display()))?;
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace payload {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    for row in rows {
        writeln!(file, "{row}")
            .with_context(|| format!("failed to append row to {}", target.display()))?;
    }
    Ok(())
}

fn validate_tsv_payload_header(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add payload tsv {}", source.display()))?;
    let source_header = source_text.lines().next().unwrap_or_default();
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if source_header != target_header {
        bail!("add payload tsv header mismatch for {}", target.display());
    }
    Ok(())
}

fn append_catalog_from_add_payload(
    project_db_path: &Path,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: Option<i64>,
    manifest: &AddDatasetManifest,
) -> Result<i64> {
    let mut datasets = read_dataset_rows(payload_root)?;
    if datasets.len() != 1 {
        bail!("add dataset payload must contain exactly one dataset row");
    }
    let dataset = datasets.remove(0);
    if dataset.name != manifest.dataset_name {
        bail!(
            "add dataset payload dataset mismatch: manifest={} payload={}",
            manifest.dataset_name,
            dataset.name
        );
    }
    let chr_assignments = read_imported_chr_assignment_rows(payload_root)?;
    let source_seq_locators = read_source_seq_locator_rows(payload_root)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(payload_root)?;
    let telomere_rules = read_telomere_rule_rows(payload_root)?;
    let telomere_marks = read_telomere_mark_rows(payload_root)?;
    let centromere_marks = read_centromere_mark_rows(payload_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start add catalog sync transaction")?;
    let fasta_path = workspace_root.join(&dataset.fasta_relpath);
    let fai_path = workspace_root.join(&dataset.fai_relpath);
    tx.execute(
        "INSERT INTO dataset (
            name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            dataset.name,
            dataset.assembler,
            dataset.assembler_version,
            path_to_string(&fasta_path)?,
            path_to_string(&fai_path)?,
            if dataset.self_alignment_available {
                1_i64
            } else {
                0_i64
            }
        ],
    )
    .with_context(|| format!("failed to insert add dataset {}", manifest.dataset_name))?;
    let dataset_id = tx.last_insert_rowid();
    sync_source_seq_rows(&tx, dataset_id, &fai_path)?;
    append_imported_chr_assignment_rows(&tx, &chr_assignments)?;
    append_source_seq_locator_rows(&tx, workspace_root, &source_seq_locators)?;
    append_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    append_telomere_rows(&tx, &telomere_rules, &telomere_marks)?;
    append_centromere_rows(&tx, &centromere_marks)?;
    if let Some(project_id) = project_id {
        append_project_dataset_link(&tx, project_id, dataset_id)?;
    }
    tx.commit()
        .context("failed to commit add catalog sync transaction")?;
    Ok(dataset_id)
}

fn append_catalog_from_add_ctg_payload(
    project_db_path: &Path,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    validated: &ValidatedAddCtgPackage,
) -> Result<AddCtgCatalogAppend> {
    let mut datasets = read_dataset_rows(payload_root)?;
    if datasets.len() != 1 || datasets[0].name != manifest.derived_dataset {
        bail!("add_ctg payload must contain exactly one derived dataset row");
    }
    let dataset = datasets.remove(0);
    let derived_row = read_derived_ctg_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing derived_ctgs row")?;
    let track_row = read_track_member_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing track_members row")?;
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    let locator = read_single_add_ctg_locator(payload_root, manifest)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(payload_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start add_ctg catalog sync transaction")?;
    let dataset_id = ensure_derived_dataset_in_transaction(&tx, workspace_root, &dataset)?;
    let source_seq_id = append_derived_source_seq_in_transaction(
        &tx,
        dataset_id,
        &manifest.ctg_name,
        validated.source_length,
    )?;
    append_imported_chr_assignment_rows(&tx, &[chr_assignment])?;
    append_source_seq_locator_rows(&tx, workspace_root, &[locator])?;
    append_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    insert_derived_ctg_row(&tx, source_seq_id, &derived_row)?;
    insert_derived_ctg_track_member_row(
        &tx,
        project_id,
        source_seq_id,
        validated.target_dataset_id,
        &track_row,
    )?;
    tx.commit()
        .context("failed to commit add_ctg catalog sync transaction")?;
    Ok(AddCtgCatalogAppend {
        dataset_id,
        source_seq_id,
    })
}

fn ensure_derived_dataset_in_transaction(
    tx: &Transaction<'_>,
    workspace_root: &Path,
    dataset: &DatasetRow,
) -> Result<i64> {
    if dataset.name != "derived_ctg" {
        bail!("derived dataset row must be named derived_ctg");
    }
    let existing_id = tx
        .query_row(
            "SELECT id FROM dataset WHERE name = ?1",
            params![dataset.name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to resolve existing derived_ctg dataset")?;
    if let Some(dataset_id) = existing_id {
        return Ok(dataset_id);
    }
    let fasta_path = workspace_root.join(&dataset.fasta_relpath);
    let fai_path = workspace_root.join(&dataset.fai_relpath);
    tx.execute(
        "INSERT INTO dataset (
            name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            dataset.name,
            dataset.assembler,
            dataset.assembler_version,
            path_to_string(&fasta_path)?,
            path_to_string(&fai_path)?,
            if dataset.self_alignment_available { 1_i64 } else { 0_i64 }
        ],
    )
    .context("failed to insert derived_ctg dataset")?;
    Ok(tx.last_insert_rowid())
}

fn append_derived_source_seq_in_transaction(
    tx: &Transaction<'_>,
    dataset_id: i64,
    ctg_name: &str,
    source_length: i64,
) -> Result<i64> {
    let duplicate = tx
        .query_row(
            "SELECT id FROM source_seq WHERE dataset_id = ?1 AND seq_name = ?2",
            params![dataset_id, ctg_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check duplicate derived source_seq")?;
    if duplicate.is_some() {
        bail!("ctg name already exists: {ctg_name}. Please choose a different --ctg name.");
    }
    let seq_order: i64 = tx
        .query_row(
            "SELECT COALESCE(MAX(seq_order), 0) + 1 FROM source_seq WHERE dataset_id = ?1",
            params![dataset_id],
            |row| row.get(0),
        )
        .context("failed to compute derived_ctg seq_order")?;
    tx.execute(
        "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
         VALUES (?1, ?2, ?3, ?4)",
        params![dataset_id, ctg_name, seq_order, source_length],
    )
    .with_context(|| format!("failed to insert derived source_seq {ctg_name}"))?;
    let source_seq_id = tx.last_insert_rowid();
    tx.execute(
        "UPDATE dataset
         SET contig_count = (
             SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1
         ),
         total_length_bp = (
             SELECT COALESCE(SUM(length), 0) FROM source_seq WHERE dataset_id = ?1
         )
         WHERE id = ?1",
        params![dataset_id],
    )
    .context("failed to update derived_ctg dataset stats")?;
    Ok(source_seq_id)
}

fn insert_derived_ctg_row(
    tx: &Transaction<'_>,
    source_seq_id: i64,
    row: &DerivedCtgRow,
) -> Result<()> {
    tx.execute(
        "INSERT INTO derived_ctg (
            source_seq_id, source, source_fasta_name, source_fasta_sha256, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5)",
        params![
            source_seq_id,
            row.source,
            row.source_fasta_name,
            row.source_fasta_sha256,
            row.created_at
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg row for {}", row.ctg_name))?;
    Ok(())
}

fn insert_derived_ctg_track_member_row(
    tx: &Transaction<'_>,
    project_id: i64,
    source_seq_id: i64,
    target_dataset_id: i64,
    row: &TrackMemberRow,
) -> Result<()> {
    tx.execute(
        "INSERT INTO derived_ctg_track_member (
            project_id, source_seq_id, target_dataset_id, target_chr_name, member_role, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            project_id,
            source_seq_id,
            target_dataset_id,
            row.target_chr,
            row.member_role,
            row.created_at
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg track member for {}", row.member_ctg))?;
    Ok(())
}

fn append_imported_chr_assignment_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for imported chr assignment {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.assigned_chr_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve reference_chr for imported chr assignment {}",
                    row.assigned_chr_name
                )
            })?;
        tx.execute(
            "INSERT INTO imported_chr_assignment (
                source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start
             ) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                source_seq_id,
                reference_chr_id,
                row.support_bp,
                row.support_percent,
                row.anchor_start
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert imported chr assignment {}:{} -> {}",
                row.dataset_name, row.seq_name, row.assigned_chr_name
            )
        })?;
    }
    Ok(())
}

fn append_source_seq_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[SourceSeqLocatorRow],
) -> Result<()> {
    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for locator {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let fasta_path = bundle_root.join(&row.fasta_relpath);
        tx.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (?1, ?2)
             ON CONFLICT(source_seq_id) DO UPDATE SET
                fasta_path = excluded.fasta_path",
            params![source_seq_id, path_to_string(&fasta_path)?],
        )
        .with_context(|| {
            format!(
                "failed to insert source seq locator for {}:{}",
                row.dataset_name, row.seq_name
            )
        })?;
    }
    Ok(())
}

fn append_source_seq_n_region_rows(
    tx: &Transaction<'_>,
    rows: &[SourceSeqNRegionRow],
) -> Result<()> {
    for row in rows {
        insert_source_seq_n_region_row(tx, row)?;
    }
    Ok(())
}

fn insert_source_seq_n_region_row(
    tx: &Transaction<'_>,
    row: &SourceSeqNRegionRow,
) -> Result<()> {
    let source_seq_id: i64 = tx
        .query_row(
            "SELECT ss.id
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE d.name = ?1
               AND ss.seq_name = ?2",
            params![row.dataset_name, row.seq_name],
            |query_row| query_row.get(0),
        )
        .with_context(|| {
            format!(
                "failed to resolve source_seq for n region {}:{}",
                row.dataset_name, row.seq_name
            )
        })?;
    tx.execute(
        "INSERT INTO source_seq_n_region (
            source_seq_id, start_bp, end_bp, length_bp
         ) VALUES (?1, ?2, ?3, ?4)",
        params![source_seq_id, row.start_bp, row.end_bp, row.length_bp],
    )
    .with_context(|| {
        format!(
            "failed to insert n region {}:{} {}-{}",
            row.dataset_name, row.seq_name, row.start_bp, row.end_bp
        )
    })?;
    Ok(())
}

fn append_telomere_rows(
    tx: &Transaction<'_>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    for rule in rules {
        tx.execute(
            "INSERT INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(rule_id) DO UPDATE SET
                motif = excluded.motif,
                min_repeat = excluded.min_repeat,
                reverse_complement = excluded.reverse_complement",
            params![
                rule.rule_id,
                rule.motif,
                rule.min_repeat,
                if rule.reverse_complement {
                    1_i64
                } else {
                    0_i64
                }
            ],
        )
        .with_context(|| format!("failed to upsert telomere rule {}", rule.rule_id))?;
    }
    for mark in marks {
        tx.execute(
            "INSERT OR IGNORE INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, 1)",
            params![mark.rule_id, mark.motif, mark.min_repeat],
        )
        .with_context(|| format!("failed to insert telomere rule {}", mark.rule_id))?;
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for telomere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_telomere_mark (
                source_seq_id, rule_id, assigned_chr_name, motif, min_repeat,
                repeat_count, start_bp, end_bp, strand
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                source_seq_id,
                mark.rule_id,
                mark.assigned_chr_name,
                mark.motif,
                mark.min_repeat,
                mark.repeat_count,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert telomere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.rule_id
            )
        })?;
    }
    Ok(())
}

fn append_centromere_rows(tx: &Transaction<'_>, marks: &[CentromereMarkRow]) -> Result<()> {
    for mark in marks {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for centromere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_centromere_mark (
                source_seq_id, cen_id, assigned_chr_name, query_name,
                start_bp, end_bp, strand, align_length, identity, mapq
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                source_seq_id,
                mark.cen_id,
                mark.assigned_chr_name,
                mark.query_name,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
                mark.align_length,
                mark.identity,
                mark.mapq,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert centromere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.cen_id
            )
        })?;
    }
    Ok(())
}

fn append_project_dataset_link(
    tx: &Transaction<'_>,
    project_id: i64,
    dataset_id: i64,
) -> Result<()> {
    let next_display_order: i64 = tx
        .query_row(
            "SELECT COALESCE(MAX(display_order), 0) + 1
             FROM project_dataset
             WHERE project_id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to compute project {project_id} display order"))?;
    tx.execute(
        "INSERT INTO project_dataset (
            project_id, dataset_id, dataset_role, display_order
         ) VALUES (?1, ?2, 'support', ?3)",
        params![project_id, dataset_id, next_display_order],
    )
    .with_context(|| {
        format!(
            "failed to insert add dataset support link project_id={} dataset_id={}",
            project_id, dataset_id
        )
    })?;
    Ok(())
}

fn project_has_assembly_rows(project_db_path: &Path, project_id: i64) -> Result<bool> {
    let conn = open_workspace_db(project_db_path)?;
    let has_rows: i64 = conn
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
        .with_context(|| format!("failed to detect assembly rows for project_id={project_id}"))?;
    Ok(has_rows > 0)
}

fn append_project_derived_ctg_assembly(
    project_db_path: &Path,
    project_id: i64,
    source_seq_id: i64,
    ctg_name: &str,
    target_chr: &str,
    chr_order: i64,
    anchor_start: i64,
) -> Result<i64> {
    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start derived_ctg assembly append transaction")?;
    let source_length: i64 = tx
        .query_row(
            "SELECT length FROM source_seq WHERE id = ?1",
            params![source_seq_id],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to resolve source_seq_id {source_seq_id} length"))?;
    let existing_assembly = tx
        .query_row(
            "SELECT id FROM assembly_seq WHERE project_id = ?1 AND source_seq_id = ?2",
            params![project_id, source_seq_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check existing derived_ctg assembly_seq")?;
    if existing_assembly.is_some() {
        bail!(
            "project_id {} already has assembly rows for derived ctg {}",
            project_id,
            ctg_name
        );
    }
    let existing_name = tx
        .query_row(
            "SELECT id FROM assembly_ctg WHERE project_id = ?1 AND name = ?2",
            params![project_id, ctg_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check duplicate derived_ctg assembly name")?;
    if existing_name.is_some() {
        bail!(
            "assembly_ctg name '{}' already exists in project_id {}",
            ctg_name,
            project_id
        );
    }
    let created_at = now_timestamp_string();
    tx.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
         ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, ?6)",
        params![
            project_id,
            source_seq_id,
            format!("source:{}", source_seq_id),
            source_length,
            created_at,
            "derived_ctg"
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg assembly_seq for {ctg_name}"))?;
    let assembly_seq_id = tx.last_insert_rowid();
    tx.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
            anchor_start, ref_orient, placement_mode, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, '+', 'auto', ?7, ?8)",
        params![
            project_id,
            assembly_seq_id,
            ctg_name,
            target_chr,
            chr_order,
            anchor_start,
            created_at,
            "derived_ctg"
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg assembly_ctg for {ctg_name}"))?;
    let assembly_ctg_id = tx.last_insert_rowid();
    tx.commit()
        .context("failed to commit derived_ctg assembly append transaction")?;
    Ok(assembly_ctg_id)
}

fn sync_telomere_rows(
    tx: &Transaction<'_>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_telomere_mark", [])
        .context("failed to clear source_seq_telomere_mark rows")?;
    tx.execute("DELETE FROM telomere_rule", [])
        .context("failed to clear telomere_rule rows")?;

    if rules.is_empty() && marks.is_empty() {
        return Ok(());
    }

    for rule in rules {
        tx.execute(
            "INSERT INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, ?4)",
            params![
                rule.rule_id,
                rule.motif,
                rule.min_repeat,
                if rule.reverse_complement {
                    1_i64
                } else {
                    0_i64
                }
            ],
        )
        .with_context(|| format!("failed to insert telomere rule {}", rule.rule_id))?;
    }

    for mark in marks {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for telomere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_telomere_mark (
                source_seq_id, rule_id, assigned_chr_name, motif, min_repeat,
                repeat_count, start_bp, end_bp, strand
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                source_seq_id,
                mark.rule_id,
                mark.assigned_chr_name,
                mark.motif,
                mark.min_repeat,
                mark.repeat_count,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert telomere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.rule_id
            )
        })?;
    }
    Ok(())
}

fn sync_centromere_rows(tx: &Transaction<'_>, marks: &[CentromereMarkRow]) -> Result<()> {
    tx.execute("DELETE FROM source_seq_centromere_mark", [])
        .context("failed to clear source_seq_centromere_mark rows")?;

    for mark in marks {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for centromere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_centromere_mark (
                source_seq_id, cen_id, assigned_chr_name, query_name,
                start_bp, end_bp, strand, align_length, identity, mapq
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                source_seq_id,
                mark.cen_id,
                mark.assigned_chr_name,
                mark.query_name,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
                mark.align_length,
                mark.identity,
                mark.mapq,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert centromere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.cen_id
            )
        })?;
    }
    Ok(())
}

fn sync_reference_chr_rows(
    tx: &Transaction<'_>,
    reference_genome_id: i64,
    fai_path: &Path,
) -> Result<()> {
    let rows = parse_fai_rows(fai_path)?;
    if rows.is_empty() {
        bail!("reference fai has no rows: {}", fai_path.display());
    }

    tx.execute(
        "DELETE FROM reference_chr WHERE reference_genome_id = ?1",
        params![reference_genome_id],
    )
    .with_context(|| {
        format!(
            "failed to clear reference_chr rows for reference_genome_id={}",
            reference_genome_id
        )
    })?;

    for row in rows {
        tx.execute(
            "INSERT INTO reference_chr (
                reference_genome_id, chr_name, chr_order, length
            ) VALUES (?1, ?2, ?3, ?4)",
            params![reference_genome_id, row.seq_name, row.seq_order, row.length],
        )
        .with_context(|| {
            format!(
                "failed to insert reference_chr row for reference_genome_id={}",
                reference_genome_id
            )
        })?;
    }
    Ok(())
}

fn sync_source_seq_rows(tx: &Transaction<'_>, dataset_id: i64, fai_path: &Path) -> Result<()> {
    let rows = parse_fai_rows(fai_path)?;
    if rows.is_empty() {
        bail!("dataset fai has no rows: {}", fai_path.display());
    }
    let contig_count = rows.len() as i64;
    let total_length_bp = rows.iter().map(|row| row.length).sum::<i64>();

    tx.execute(
        "DELETE FROM source_seq WHERE dataset_id = ?1",
        params![dataset_id],
    )
    .with_context(|| {
        format!(
            "failed to clear source_seq rows for dataset_id={}",
            dataset_id
        )
    })?;

    for row in rows {
        tx.execute(
            "INSERT INTO source_seq (
                dataset_id, seq_name, seq_order, length
            ) VALUES (?1, ?2, ?3, ?4)",
            params![dataset_id, row.seq_name, row.seq_order, row.length],
        )
        .with_context(|| {
            format!(
                "failed to insert source_seq row for dataset_id={}",
                dataset_id
            )
        })?;
    }
    tx.execute(
        "UPDATE dataset
         SET contig_count = ?2, total_length_bp = ?3
         WHERE id = ?1",
        params![dataset_id, contig_count, total_length_bp],
    )
    .with_context(|| {
        format!(
            "failed to update dataset stats for dataset_id={}",
            dataset_id
        )
    })?;
    Ok(())
}

fn parse_fai_rows(path: &Path) -> Result<Vec<FaiRow>> {
    let file =
        File::open(path).with_context(|| format!("failed to open fai {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut rows = Vec::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 1, path.display())
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() < 2 {
            bail!(
                "invalid fai row at {}:{} => {}",
                path.display(),
                index + 1,
                line
            );
        }
        let length: i64 = parts[1].parse().with_context(|| {
            format!(
                "invalid fai length at {}:{} => {}",
                path.display(),
                index + 1,
                parts[1]
            )
        })?;
        rows.push(FaiRow {
            seq_name: parts[0].to_string(),
            length,
            seq_order: (index as i64) + 1,
        });
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use rusqlite::{Connection, params};
    use tempfile::tempdir;
    use zip::CompressionMethod;
    use zip::write::FileOptions;

    use super::*;
    use crate::workspace::looks_like_bundle_root;

    #[test]
    fn imports_extracted_bundle_and_prepares_workspace_in_bundle_root() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);

        let (outcome, progress) = import_from_extracted_bundle(&bundle_root).unwrap();

        assert_eq!(outcome.mode, ImportMode::ExtractedBundle);
        assert_eq!(outcome.bundle_root, bundle_root);
        assert_eq!(outcome.workspace_root, outcome.bundle_root);
        assert!(outcome.project_db_path.exists());
        assert!(outcome.workspace_root.join(EXPORTS_DIR).exists());
        assert!(outcome.workspace_root.join(CACHE_DIR).exists());
        assert_eq!(count_rows(&outcome.project_db_path, "reference_genome"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "reference_chr"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
        assert_eq!(
            dataset_stats(&outcome.project_db_path, "ds_a"),
            Some((1, 2))
        );
        assert_eq!(progress.last().unwrap().stage, "complete");
    }

    #[test]
    fn imports_zip_delivery_and_prepares_named_workspace() {
        let temp = tempdir().unwrap();
        let zip_path = temp.path().join("delivery.zip");
        write_bundle_zip(&zip_path);

        let workspace_root = temp.path().join("workspaces").join("project_alpha");
        let (outcome, progress) = import_from_zip(&zip_path, &workspace_root).unwrap();

        assert_eq!(outcome.mode, ImportMode::ZipDelivery);
        assert_eq!(outcome.bundle_root, workspace_root);
        assert_eq!(outcome.workspace_root, workspace_root);
        assert!(outcome.project_db_path.exists());
        assert!(outcome.workspace_root.join(EXPORTS_DIR).exists());
        assert!(outcome.workspace_root.join(CACHE_DIR).exists());
        assert!(looks_like_bundle_root(&outcome.bundle_root));
        assert!(!outcome.workspace_root.join("gpm_server").exists());
        assert_eq!(count_rows(&outcome.project_db_path, "reference_genome"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "reference_chr"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
        assert_eq!(
            dataset_stats(&outcome.project_db_path, "ds_a"),
            Some((1, 4))
        );
        assert_eq!(progress.last().unwrap().stage, "complete");
        assert!(progress.iter().all(|item| item.progress_index.is_some()
            && item.progress_total == progress.last().unwrap().progress_total));
        assert!(
            progress
                .iter()
                .filter(|item| item.stage == "extract_entry")
                .all(|item| !item.detail.contains(" (") && !item.detail.ends_with(')'))
        );
        assert!(
            progress
                .last()
                .unwrap()
                .progress_total
                .is_some_and(|total| total > 0)
        );
    }

    #[test]
    fn imports_zip_delivery_without_fasta_and_marks_dataset_unavailable_for_fasta_export() {
        let temp = tempdir().unwrap();
        let zip_path = temp.path().join("delivery-light.zip");
        write_bundle_zip_without_fasta(&zip_path);

        let workspace_root = temp.path().join("workspaces").join("project_alpha");
        let (outcome, _progress) = import_from_zip(&zip_path, &workspace_root).unwrap();
        let options =
            crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();

        assert_eq!(count_rows(&outcome.project_db_path, "reference_genome"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "reference_chr"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
        assert!(
            !outcome
                .workspace_root
                .join("data/reference/ref.fa")
                .exists()
        );
        assert!(!outcome.workspace_root.join("data/datasets/ds.fa").exists());
        assert_eq!(
            options
                .datasets
                .first()
                .map(|dataset| dataset.fasta_available),
            Some(false)
        );
    }

    #[test]
    fn imports_zip_delivery_with_skipped_self_alignment_capability() {
        let temp = tempdir().unwrap();
        let zip_path = temp.path().join("delivery-no-self.zip");
        write_bundle_zip_with_self_alignment_flag(&zip_path, false);

        let workspace_root = temp.path().join("workspaces").join("project_alpha");
        let (outcome, _progress) = import_from_zip(&zip_path, &workspace_root).unwrap();
        let options =
            crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();

        assert_eq!(
            options
                .datasets
                .first()
                .map(|dataset| dataset.self_alignment_available),
            Some(false)
        );
    }

    #[test]
    fn imports_server_package_metadata_and_chr_assignments() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);
        fs::write(
            bundle_root.join("metadata/package.tsv"),
            concat!(
                "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
                "fast\tpartitioned\ttrue\t72\tchr_partition\tchr_partition\n",
            ),
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/chr_assignments.tsv"),
            concat!(
                "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\n",
                "ds_a\td\t2\tr\t2\t100.000\t9\n",
            ),
        )
        .unwrap();

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();

        let metadata_row: (String, String, i64, f64, String, String) = conn
            .query_row(
                "SELECT package_mode, sequence_layout, preassigned_chr, chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
                 FROM workspace_package_metadata
                 WHERE id = 1",
                [],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                    ))
                },
            )
            .unwrap();
        assert_eq!(
            metadata_row,
            (
                "fast".to_string(),
                "partitioned".to_string(),
                1,
                72.0,
                "chr_partition".to_string(),
                "chr_partition".to_string(),
            )
        );

        let imported_rows = conn
            .query_row("SELECT COUNT(*) FROM imported_chr_assignment", [], |row| {
                row.get::<_, i64>(0)
            })
            .unwrap();
        assert_eq!(imported_rows, 1);
    }

    #[test]
    fn imports_optional_telomere_rules_and_marks() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);
        fs::create_dir_all(bundle_root.join("tel/chr_r")).unwrap();
        fs::write(
            bundle_root.join("tel/rules.tsv"),
            "rule_id\tmotif\tmin_repeat\treverse_complement\ntel1\tTTAGGG\t20\ttrue\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("tel/chr_r/ds_a.tsv"),
            concat!(
                "rule_id\tdataset_name\tseq_name\tassigned_chr_name\tmotif\tmin_repeat\trepeat_count\tstart_bp\tend_bp\tstrand\n",
                "tel1\tds_a\td\tr\tTTAGGG\t20\t21\t3\t128\t+\n",
            ),
        )
        .unwrap();

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();

        let rule_row: (String, String, i64, i64) = conn
            .query_row(
                "SELECT rule_id, motif, min_repeat, reverse_complement FROM telomere_rule WHERE rule_id = 'tel1'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert_eq!(rule_row, ("tel1".to_string(), "TTAGGG".to_string(), 20, 1));

        let mark_row: (String, String, String, i64, i64, i64, i64, String) = conn
            .query_row(
                "SELECT tr.rule_id, tr.motif, tm.assigned_chr_name, tm.min_repeat, tm.repeat_count, tm.start_bp, tm.end_bp, tm.strand
                 FROM source_seq_telomere_mark tm
                 JOIN telomere_rule tr ON tr.rule_id = tm.rule_id
                 JOIN source_seq ss ON ss.id = tm.source_seq_id
                 WHERE ss.seq_name = 'd'",
                [],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                        row.get(7)?,
                    ))
                },
            )
            .unwrap();
        assert_eq!(
            mark_row,
            (
                "tel1".to_string(),
                "TTAGGG".to_string(),
                "r".to_string(),
                20,
                21,
                3,
                128,
                "+".to_string(),
            )
        );
    }

    #[test]
    fn imports_optional_centromere_marks() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);
        fs::create_dir_all(bundle_root.join("cen/chr_r")).unwrap();
        fs::write(
            bundle_root.join("cen/reference.tsv"),
            "cen_id\tchr_name\tsequence_name\tfasta_relpath\tmin_len\tmin_identity\ncen\tr\tr_centromere\tdata/centromere/ref_cen.fa\t10000\t80\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("cen/chr_r/marks.tsv"),
            concat!(
                "cen_id\tchr_name\tquery_name\tdataset_name\tctg_name\tctg_start\tctg_end\tstrand\talign_length\tidentity\tmapq\n",
                "cen\tr\tr_centromere\tds_a\td\t3\t128\t+\t126\t96.500\t60\n",
            ),
        )
        .unwrap();

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();

        let mark_row: (String, String, String, i64, i64, String, i64, f64, i64) = conn
            .query_row(
                "SELECT cm.cen_id, cm.assigned_chr_name, cm.query_name, cm.start_bp, cm.end_bp, cm.strand, cm.align_length, cm.identity, cm.mapq
                 FROM source_seq_centromere_mark cm
                 JOIN source_seq ss ON ss.id = cm.source_seq_id
                 WHERE ss.seq_name = 'd'",
                [],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                        row.get(7)?,
                        row.get(8)?,
                    ))
                },
            )
            .unwrap();
        assert_eq!(
            mark_row,
            (
                "cen".to_string(),
                "r".to_string(),
                "r_centromere".to_string(),
                3,
                128,
                "+".to_string(),
                126,
                96.5,
                60,
            )
        );
    }

    #[test]
    fn imports_source_seq_n_regions() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);
        fs::write(
            bundle_root.join("metadata/source_seq_n_regions.tsv"),
            "dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\nds_a\td\t2\t2\t1\n",
        )
        .unwrap();

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();

        let region_row: (String, i64, i64, i64) = conn
            .query_row(
                "SELECT ss.seq_name, nr.start_bp, nr.end_bp, nr.length_bp
                 FROM source_seq_n_region nr
                 JOIN source_seq ss ON ss.id = nr.source_seq_id",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert_eq!(region_row, ("d".to_string(), 2, 2, 1));
    }

    #[test]
    fn rejects_non_partitioned_package_metadata() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);
        fs::write(
            bundle_root.join("metadata/package.tsv"),
            concat!(
                "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
                "legacy\tmonolithic\tfalse\t60\tnone\tchr_partition\n",
            ),
        )
        .unwrap();

        let error = import_from_extracted_bundle(&bundle_root).unwrap_err();
        assert!(error.to_string().contains("partitioned"));
    }

    #[test]
    fn imports_partitioned_fast_locators_and_reports_fasta_available_when_payload_exists() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();

        let metadata_row: (String, String, i64) = conn
            .query_row(
                "SELECT package_mode, sequence_layout, preassigned_chr
                 FROM workspace_package_metadata
                 WHERE id = 1",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(
            metadata_row,
            ("fast".to_string(), "partitioned".to_string(), 1)
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "reference_chr_locator"),
            1
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "source_seq_locator"),
            1
        );

        let dataset_locator_path: String = conn
            .query_row(
                "SELECT ssl.fasta_path
                 FROM source_seq_locator ssl
                 JOIN source_seq ss ON ss.id = ssl.source_seq_id
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = 'ds_a' AND ss.seq_name = 'd'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(dataset_locator_path.ends_with("data/partitions/chr/r/ds_a.fa"));

        let options =
            crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();
        assert_eq!(
            options
                .datasets
                .first()
                .map(|dataset| dataset.fasta_available),
            Some(true)
        );
    }

    #[test]
    fn imports_partitioned_fast_light_without_fasta_payload_and_marks_unavailable() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, false);

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        assert_eq!(
            count_rows(&outcome.project_db_path, "reference_chr_locator"),
            1
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "source_seq_locator"),
            1
        );
        assert!(
            !outcome
                .workspace_root
                .join("data/reference/ref.fa")
                .exists()
        );
        assert!(!outcome.workspace_root.join("data/datasets/ds.fa").exists());

        let options =
            crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();
        assert_eq!(
            options
                .datasets
                .first()
                .map(|dataset| dataset.fasta_available),
            Some(false)
        );
    }

    #[test]
    fn imports_partitioned_alignment_pafs_into_global_hit_tables() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        fs::create_dir_all(bundle_root.join("runs/ds_a_vs_ref")).unwrap();
        fs::create_dir_all(bundle_root.join("runs/chr_r/ds_a_vs_self")).unwrap();
        fs::write(
            bundle_root.join("runs/ds_a_vs_ref/result.paf"),
            "d\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("runs/chr_r/ds_a_vs_self/result.paf"),
            "d\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();

        let (outcome, progress) = import_from_extracted_bundle(&bundle_root).unwrap();

        assert_eq!(count_rows(&outcome.project_db_path, "ref_alignment_hit"), 1);
        assert_eq!(
            count_rows(&outcome.project_db_path, "pairwise_alignment_run"),
            1
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "pairwise_alignment_hit"),
            0
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "pairwise_alignment_scope"),
            0
        );
        assert!(
            progress
                .iter()
                .any(|item| item.stage == "index_ref_paf" && item.detail.contains("ds_a_vs_ref"))
        );
        assert!(
            progress
                .iter()
                .any(|item| item.stage == "index_pairwise_paf"
                    && item.detail.contains("chr_r/ds_a_vs_self"))
        );
        let log_text = fs::read_to_string(outcome.workspace_root.join("cache/import.log")).unwrap();
        assert!(log_text.contains("index_ref_paf"));
        assert!(log_text.contains("index_pairwise_paf"));
    }

    #[test]
    fn imports_add_dataset_package_append_only_into_existing_project() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        write_prepare_options(&bundle_root, "asm10", false);
        fs::create_dir_all(bundle_root.join("runs/ds_a_vs_ref")).unwrap();
        fs::create_dir_all(bundle_root.join("runs/chr_r/ds_a_vs_self")).unwrap();
        fs::write(
            bundle_root.join("runs/ds_a_vs_ref/result.paf"),
            "d\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("runs/chr_r/ds_a_vs_self/result.paf"),
            "d\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();

        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let project_id = insert_existing_project(&outcome.project_db_path);
        crate::project_initializer::bootstrap_project_assembly(
            &outcome.project_db_path,
            project_id,
        )
        .unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        let existing_dataset_count = count_rows(&outcome.project_db_path, "dataset");
        let existing_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
        let existing_chr_assignment_count =
            count_rows(&outcome.project_db_path, "imported_chr_assignment");
        let existing_ref_hit_count = count_rows(&outcome.project_db_path, "ref_alignment_hit");
        let existing_pairwise_run_ids = query_pairwise_run_ids_for_dataset_names(&conn, &["ds_a"]);
        let existing_assembly_rows = query_project_assembly_rows(&conn, project_id);
        drop(conn);

        let add_zip_path = temp.path().join("add_ds4.zip");
        write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

        let (add_outcome, progress) =
            import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap();

        assert_eq!(add_outcome.dataset_name, "ds4");
        assert_eq!(add_outcome.project_id, Some(project_id));
        assert_eq!(add_outcome.bundle_root, outcome.workspace_root);
        assert!(progress.iter().any(|item| item.stage == "index_ref_paf"));
        assert!(
            progress
                .iter()
                .any(|item| item.stage == "index_pairwise_paf")
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "dataset"),
            existing_dataset_count + 1
        );
        assert_eq!(dataset_stats(&outcome.project_db_path, "ds4"), Some((1, 4)));

        let conn = Connection::open(&outcome.project_db_path).unwrap();
        let ds4_id: i64 = conn
            .query_row("SELECT id FROM dataset WHERE name = 'ds4'", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM project_dataset WHERE project_id = ?1 AND dataset_id = ?2 AND dataset_role = 'support'",
                params![project_id, ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1",
                params![ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            query_project_assembly_rows_excluding_dataset(&conn, project_id, ds4_id),
            existing_assembly_rows
        );
        let ds4_assembly_row: (String, String, Option<String>) = conn
            .query_row(
                "SELECT c.name, s.orient, c.ref_orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE c.project_id = ?1 AND ss.dataset_id = ?2",
                params![project_id, ds4_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(
            ds4_assembly_row,
            ("x@r".to_string(), "+".to_string(), Some("+".to_string()))
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "source_seq_locator"),
            existing_locator_count + 1
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "imported_chr_assignment"),
            existing_chr_assignment_count + 1
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM ref_alignment_hit WHERE dataset_id = ?1",
                params![ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "ref_alignment_hit"),
            existing_ref_hit_count + 1
        );
        for run_id in existing_pairwise_run_ids {
            let still_present: i64 = conn
                .query_row(
                    "SELECT COUNT(*) FROM pairwise_alignment_run WHERE id = ?1",
                    params![run_id],
                    |row| row.get(0),
                )
                .unwrap();
            assert_eq!(still_present, 1);
        }
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*)
                 FROM pairwise_alignment_run
                 WHERE query_dataset_id = ?1 OR target_dataset_id = ?1",
                params![ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            2
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*)
                 FROM pairwise_alignment_hit h
                 JOIN pairwise_alignment_run r ON r.id = h.run_id
                 WHERE r.query_dataset_id = ?1 OR r.target_dataset_id = ?1",
                params![ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert!(
            fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv"))
                .unwrap()
                .contains("\nds4\t")
        );
        assert!(outcome.workspace_root.join("data/datasets/ds4.fa").exists());
        assert!(
            outcome
                .workspace_root
                .join("runs/chr_r/ds_a_vs_ds4/result.paf")
                .exists()
        );
    }

    #[test]
    fn imports_add_ctg_package_into_target_track() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        add_second_chr_dataset_to_bundle_root(&bundle_root, true);
        write_prepare_options(&bundle_root, "asm10", false);
        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let project_id = insert_existing_project(&outcome.project_db_path);
        insert_support_project_dataset(&outcome.project_db_path, project_id, "ds_b", 2);
        crate::project_initializer::bootstrap_project_assembly(
            &outcome.project_db_path,
            project_id,
        )
        .unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        let target_dataset_id: i64 = conn
            .query_row("SELECT id FROM dataset WHERE name = 'ds_a'", [], |row| {
                row.get(0)
            })
            .unwrap();
        drop(conn);

        let add_zip_path = temp.path().join("add_gap_filled.zip");
        write_add_ctg_zip(&add_zip_path);

        let (add_outcome, progress) =
            import_add_ctg_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap();

        assert_eq!(add_outcome.ctg_name, "gap_filled");
        assert_eq!(add_outcome.target_track, "ds_a");
        assert_eq!(add_outcome.target_chr, "r");
        assert!(add_outcome.assembly_ctg_id.is_some());
        assert!(progress.iter().any(|item| item.stage == "index_ref_paf"));
        assert!(
            progress
                .iter()
                .any(|item| item.stage == "index_pairwise_paf")
        );
        assert!(progress.iter().any(|item| {
            item.stage == "index_pairwise_paf_complete"
                && item.detail.contains("indexed_runs=2")
        }));

        let conn = Connection::open(&outcome.project_db_path).unwrap();
        let derived_dataset_id: i64 = conn
            .query_row(
                "SELECT id FROM dataset WHERE name = 'derived_ctg'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(add_outcome.dataset_id, derived_dataset_id);
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1 AND seq_name = 'gap_filled'",
                params![derived_dataset_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*)
                 FROM derived_ctg_track_member
                 WHERE project_id = ?1
                   AND source_seq_id = ?2
                   AND target_dataset_id = ?3
                   AND target_chr_name = 'r'",
                params![project_id, add_outcome.source_seq_id, target_dataset_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM ref_alignment_hit WHERE source_seq_id = ?1",
                params![add_outcome.source_seq_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            1
        );
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*)
                 FROM pairwise_alignment_run
                 WHERE run_name IN ('ds_a_vs_gap_filled', 'ds_b_vs_gap_filled')",
                [],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            2
        );
        drop(conn);

        let target_track_ctgs = crate::main_view::list_chr_view_ctgs(
            &outcome.project_db_path,
            project_id,
            Some("r"),
            Some(target_dataset_id),
        )
        .unwrap();
        let derived_item = target_track_ctgs
            .iter()
            .find(|item| item.name == "gap_filled")
            .expect("derived ctg should appear in target track view");
        assert_eq!(derived_item.derived_source.as_deref(), Some("gapfiller"));
        assert_eq!(
            derived_item.derived_target_dataset_id,
            Some(target_dataset_id)
        );
        assert_eq!(derived_item.hits.len(), 2);
    }

    #[test]
    fn rejects_add_ctg_package_for_different_clicked_track() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        write_prepare_options(&bundle_root, "asm10", false);
        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let project_id = insert_existing_project(&outcome.project_db_path);
        let add_zip_path = temp.path().join("add_gap_filled.zip");
        write_add_ctg_zip(&add_zip_path);

        let error = import_add_ctg_package_with_hooks(
            &add_zip_path,
            &outcome.workspace_root,
            project_id,
            Some(AddCtgImportTarget {
                target_chr: "r".to_string(),
                target_track: "ds_b".to_string(),
            }),
            &mut |_| {},
            &mut || false,
        )
        .unwrap_err();
        assert!(
            error.to_string().contains("该 add_ctg 包属于 r / ds_a 轨道"),
            "unexpected error: {error}"
        );
    }

    #[test]
    fn imports_add_dataset_package_into_workspace_without_project_link() {
        let temp = tempdir().unwrap();
        let (outcome, project_id) = import_workspace_with_project(temp.path());
        let original_project_dataset_count =
            count_rows(&outcome.project_db_path, "project_dataset");
        let original_assembly_rows = {
            let conn = Connection::open(&outcome.project_db_path).unwrap();
            query_project_assembly_rows(&conn, project_id)
        };
        let add_zip_path = temp.path().join("add_ds4_workspace.zip");
        write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

        let (add_outcome, _progress) =
            import_workspace_add_dataset_package(&add_zip_path, &outcome.workspace_root).unwrap();

        assert_eq!(add_outcome.dataset_name, "ds4");
        assert_eq!(add_outcome.project_id, None);
        assert_eq!(
            count_rows(&outcome.project_db_path, "dataset"),
            2,
            "workspace catalog should include the new dataset"
        );
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        let ds4_id: i64 = conn
            .query_row("SELECT id FROM dataset WHERE name = 'ds4'", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM project_dataset WHERE dataset_id = ?1",
                params![ds4_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
            0,
            "workspace-level add must not inject the dataset into a project"
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "project_dataset"),
            original_project_dataset_count
        );
        assert_eq!(
            query_project_assembly_rows(&conn, project_id),
            original_assembly_rows,
            "workspace-level add must not append project assembly rows"
        );
    }

    #[test]
    fn imports_add_dataset_package_into_legacy_workspace_without_prepare_options() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        fs::create_dir_all(bundle_root.join("runs/ds_a_vs_ref")).unwrap();
        fs::create_dir_all(bundle_root.join("runs/chr_r/ds_a_vs_self")).unwrap();
        fs::write(
            bundle_root.join("runs/ds_a_vs_ref/result.paf"),
            "d\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("runs/chr_r/ds_a_vs_self/result.paf"),
            "d\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n",
        )
        .unwrap();
        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        assert!(
            !outcome
                .workspace_root
                .join("metadata/prepare_options.tsv")
                .exists(),
            "fixture should simulate older packages without prepare_options.tsv"
        );
        let add_zip_path = temp.path().join("add_ds4_legacy_workspace.zip");
        write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

        let (add_outcome, _progress) =
            import_workspace_add_dataset_package(&add_zip_path, &outcome.workspace_root).unwrap();

        assert_eq!(add_outcome.dataset_name, "ds4");
        assert_eq!(dataset_stats(&outcome.project_db_path, "ds4"), Some((1, 4)));
    }

    #[test]
    fn rejects_invalid_add_dataset_packages_without_mutating_existing_workspace() {
        let cases = [
            (
                "wrong package type",
                AddZipOptions {
                    package_type: "full".to_string(),
                    ..AddZipOptions::default()
                },
                "package_type",
            ),
            (
                "duplicate dataset",
                AddZipOptions {
                    dataset_name: "ds_a".to_string(),
                    ..AddZipOptions::default()
                },
                "already exists",
            ),
            (
                "reference mismatch",
                AddZipOptions {
                    reference_name: "other_ref".to_string(),
                    ..AddZipOptions::default()
                },
                "reference",
            ),
            (
                "score mismatch",
                AddZipOptions {
                    chr_assignment_min_coverage_percent: "61".to_string(),
                    ..AddZipOptions::default()
                },
                "chr_assignment_min_coverage_percent",
            ),
            (
                "layout mismatch",
                AddZipOptions {
                    sequence_layout: "monolithic".to_string(),
                    ..AddZipOptions::default()
                },
                "sequence_layout",
            ),
            (
                "skip self mismatch",
                AddZipOptions {
                    skip_self: true,
                    self_alignment_available: false,
                    ..AddZipOptions::default()
                },
                "skip_self",
            ),
            (
                "alignment engine mismatch",
                AddZipOptions {
                    alignment_engine: "blastn".to_string(),
                    ..AddZipOptions::default()
                },
                "alignment_engine mismatch",
            ),
            (
                "minimap preset mismatch",
                AddZipOptions {
                    minimap_preset: "asm5".to_string(),
                    ..AddZipOptions::default()
                },
                "minimap_preset mismatch",
            ),
            (
                "missing payload",
                AddZipOptions {
                    include_ref_paf: false,
                    ..AddZipOptions::default()
                },
                "payload",
            ),
            (
                "missing self alignment payload",
                AddZipOptions {
                    include_self_paf: false,
                    ..AddZipOptions::default()
                },
                "self alignment payload",
            ),
            (
                "missing pairwise alignment payload",
                AddZipOptions {
                    include_pairwise_paf: false,
                    ..AddZipOptions::default()
                },
                "pairwise alignment payload",
            ),
            (
                "unsafe dataset fasta path",
                AddZipOptions {
                    dataset_fasta_relpath: "../outside.fa".to_string(),
                    ..AddZipOptions::default()
                },
                "unsafe path traversal",
            ),
            (
                "unsafe locator path",
                AddZipOptions {
                    locator_fasta_relpath: "../outside_partition.fa".to_string(),
                    ..AddZipOptions::default()
                },
                "unsafe path traversal",
            ),
            (
                "unsafe windows locator path",
                AddZipOptions {
                    locator_fasta_relpath: r"..\outside_partition.fa".to_string(),
                    ..AddZipOptions::default()
                },
                "unsafe path separator",
            ),
            (
                "unexpected tel payload",
                AddZipOptions {
                    include_tel_payload: true,
                    ..AddZipOptions::default()
                },
                "tel_enabled=false",
            ),
            (
                "unexpected cen payload",
                AddZipOptions {
                    include_cen_payload: true,
                    ..AddZipOptions::default()
                },
                "cen_enabled=false",
            ),
            (
                "tel flag mismatch",
                AddZipOptions {
                    tel_enabled: true,
                    include_tel_payload: true,
                    ..AddZipOptions::default()
                },
                "tel_enabled mismatch",
            ),
            (
                "unexpected payload file",
                AddZipOptions {
                    include_extra_payload_file: true,
                    ..AddZipOptions::default()
                },
                "unexpected add dataset payload file",
            ),
            (
                "locator row for unknown source rolls back copied payload",
                AddZipOptions {
                    locator_seq_name: Some("missing_seq".to_string()),
                    ..AddZipOptions::default()
                },
                "failed to resolve source_seq",
            ),
        ];

        for (name, options, expected_error) in cases {
            let temp = tempdir().unwrap();
            let (outcome, project_id) = import_workspace_with_project(temp.path());
            let original_dataset_count = count_rows(&outcome.project_db_path, "dataset");
            let original_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
            let original_datasets_tsv =
                fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap();
            let add_zip_path = temp.path().join(format!("{}.zip", name.replace(' ', "_")));
            write_add_dataset_zip(&add_zip_path, options);

            let error =
                import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id)
                    .unwrap_err();

            assert!(
                error.to_string().contains(expected_error),
                "{name}: {error}"
            );
            assert_eq!(
                count_rows(&outcome.project_db_path, "dataset"),
                original_dataset_count,
                "{name} mutated dataset rows"
            );
            assert_eq!(
                count_rows(&outcome.project_db_path, "source_seq_locator"),
                original_locator_count,
                "{name} mutated locator rows"
            );
            assert_eq!(
                fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap(),
                original_datasets_tsv,
                "{name} mutated metadata/datasets.tsv"
            );
            assert!(
                !outcome.workspace_root.join("data/datasets/ds4.fa").exists(),
                "{name} left copied dataset fasta behind"
            );
        }
    }

    #[test]
    fn add_dataset_import_rolls_back_when_assembly_append_fails() {
        let temp = tempdir().unwrap();
        let (outcome, project_id) = import_workspace_with_project(temp.path());
        crate::project_initializer::bootstrap_project_assembly(
            &outcome.project_db_path,
            project_id,
        )
        .unwrap();
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        conn.execute(
            "UPDATE assembly_seq SET orient = '-' WHERE project_id = ?1",
            params![project_id],
        )
        .unwrap();
        conn.execute(
            "UPDATE assembly_ctg
             SET name = 'x@r',
                 ref_orient = '-'
             WHERE project_id = ?1",
            params![project_id],
        )
        .unwrap();
        let original_dataset_count = count_rows(&outcome.project_db_path, "dataset");
        let original_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
        let original_assembly_rows = query_project_assembly_rows(&conn, project_id);
        let original_datasets_tsv =
            fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap();
        drop(conn);

        let add_zip_path = temp.path().join("add_ds4_conflict.zip");
        write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

        let error = import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id)
            .unwrap_err();

        assert!(
            error
                .to_string()
                .contains("failed to insert imported auto assembly_ctg"),
            "{error:#}"
        );
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        assert_eq!(
            count_rows(&outcome.project_db_path, "dataset"),
            original_dataset_count
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "source_seq_locator"),
            original_locator_count
        );
        assert_eq!(
            query_project_assembly_rows(&conn, project_id),
            original_assembly_rows
        );
        assert_eq!(
            fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap(),
            original_datasets_tsv
        );
        assert!(!outcome.workspace_root.join("data/datasets/ds4.fa").exists());
    }

    #[test]
    fn rejects_non_zip_input_file() {
        let temp = tempdir().unwrap();
        let bad_path = temp.path().join("delivery.txt");
        fs::write(&bad_path, "not zip").unwrap();
        let workspace_root = temp.path().join("workspaces").join("project_alpha");

        let error = import_from_zip(&bad_path, &workspace_root).unwrap_err();
        assert!(error.to_string().contains("expected a .zip file"));
    }

    fn create_bundle_root(bundle_root: &Path) {
        fs::create_dir_all(bundle_root.join("metadata")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
        fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference/chrs")).unwrap();
        fs::create_dir_all(bundle_root.join("data/partitions/chr/r")).unwrap();
        fs::create_dir_all(bundle_root.join("runs")).unwrap();
        fs::write(
            bundle_root.join("metadata/reference.tsv"),
            "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/datasets.tsv"),
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/package.tsv"),
            concat!(
                "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
                "fast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
            ),
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/chr_assignments.tsv"),
            "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\nds_a\td\t2\tr\t2\t100.000\t1\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/reference_chr_locator.tsv"),
            "reference_chr_name\tfasta_relpath\nr\tdata/reference/chrs/r.fa\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/source_seq_locator.tsv"),
            "dataset_name\tseq_name\tfasta_relpath\nds_a\td\tdata/partitions/chr/r/ds_a.fa\n",
        )
        .unwrap();
        fs::write(bundle_root.join("data/reference/ref.fa"), ">r\nAT\n").unwrap();
        fs::write(
            bundle_root.join("data/reference/ref.fa.fai"),
            "r\t2\t0\t2\t3\n",
        )
        .unwrap();
        fs::write(bundle_root.join("data/datasets/ds.fa"), ">d\nAT\n").unwrap();
        fs::write(
            bundle_root.join("data/datasets/ds.fa.fai"),
            "d\t2\t0\t2\t3\n",
        )
        .unwrap();
        fs::write(bundle_root.join("data/reference/chrs/r.fa"), ">r\nAT\n").unwrap();
        fs::write(
            bundle_root.join("data/partitions/chr/r/ds_a.fa"),
            ">d\nAT\n",
        )
        .unwrap();
    }

    fn create_partitioned_fast_bundle_root(bundle_root: &Path, include_fasta_payload: bool) {
        fs::create_dir_all(bundle_root.join("metadata")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
        fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference/chrs")).unwrap();
        fs::create_dir_all(bundle_root.join("data/partitions/chr/r")).unwrap();
        fs::create_dir_all(bundle_root.join("runs")).unwrap();
        fs::write(
            bundle_root.join("metadata/reference.tsv"),
            "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/datasets.tsv"),
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\ttrue\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/package.tsv"),
            concat!(
                "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
                "fast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
            ),
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/chr_assignments.tsv"),
            "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\nds_a\td\t4\tr\t4\t100.000\t1\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/reference_chr_locator.tsv"),
            "reference_chr_name\tfasta_relpath\nr\tdata/reference/chrs/r.fa\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("metadata/source_seq_locator.tsv"),
            "dataset_name\tseq_name\tfasta_relpath\nds_a\td\tdata/partitions/chr/r/ds_a.fa\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("data/reference/ref.fa.fai"),
            "r\t4\t0\t4\t5\n",
        )
        .unwrap();
        fs::write(
            bundle_root.join("data/datasets/ds.fa.fai"),
            "d\t4\t0\t4\t5\n",
        )
        .unwrap();
        if include_fasta_payload {
            fs::write(bundle_root.join("data/reference/chrs/r.fa"), ">r\nACGT\n").unwrap();
            fs::write(
                bundle_root.join("data/partitions/chr/r/ds_a.fa"),
                ">d\nACGT\n",
            )
            .unwrap();
        }
    }

    fn add_second_chr_dataset_to_bundle_root(bundle_root: &Path, include_fasta_payload: bool) {
        append_text(
            &bundle_root.join("metadata/datasets.tsv"),
            "ds_b\tassembler_b\t\tdata/datasets/ds_b.fa\tdata/datasets/ds_b.fa.fai\ttrue\n",
        );
        append_text(
            &bundle_root.join("metadata/chr_assignments.tsv"),
            "ds_b\te\t4\tr\t4\t100.000\t1\n",
        );
        append_text(
            &bundle_root.join("metadata/source_seq_locator.tsv"),
            "ds_b\te\tdata/partitions/chr/r/ds_b.fa\n",
        );
        fs::write(
            bundle_root.join("data/datasets/ds_b.fa.fai"),
            "e\t4\t0\t4\t5\n",
        )
        .unwrap();
        if include_fasta_payload {
            fs::write(
                bundle_root.join("data/partitions/chr/r/ds_b.fa"),
                ">e\nACGT\n",
            )
            .unwrap();
        }
    }

    fn append_text(path: &Path, text: &str) {
        use std::io::Write;

        let mut file = fs::OpenOptions::new().append(true).open(path).unwrap();
        file.write_all(text.as_bytes()).unwrap();
    }

    #[derive(Debug, Clone)]
    struct AddZipOptions {
        package_type: String,
        dataset_name: String,
        reference_name: String,
        sequence_layout: String,
        chr_assignment_min_coverage_percent: String,
        alignment_engine: String,
        minimap_preset: String,
        blastn_task: String,
        blastn_evalue: String,
        blastn_dust: String,
        winnowmap_preset: String,
        winnowmap_kmer: String,
        winnowmap_repeat_fraction: String,
        skip_self: bool,
        self_alignment_available: bool,
        include_ref_paf: bool,
        include_self_paf: bool,
        include_pairwise_paf: bool,
        dataset_fasta_relpath: String,
        dataset_fai_relpath: String,
        locator_fasta_relpath: String,
        locator_seq_name: Option<String>,
        tel_enabled: bool,
        cen_enabled: bool,
        include_tel_payload: bool,
        include_cen_payload: bool,
        include_extra_payload_file: bool,
    }

    impl Default for AddZipOptions {
        fn default() -> Self {
            Self {
                package_type: "add_dataset".to_string(),
                dataset_name: "ds4".to_string(),
                reference_name: "ref_a".to_string(),
                sequence_layout: "partitioned".to_string(),
                chr_assignment_min_coverage_percent: "60".to_string(),
                alignment_engine: "minimap2".to_string(),
                minimap_preset: "asm10".to_string(),
                blastn_task: "blastn".to_string(),
                blastn_evalue: "1e-10".to_string(),
                blastn_dust: "no".to_string(),
                winnowmap_preset: "asm20".to_string(),
                winnowmap_kmer: "19".to_string(),
                winnowmap_repeat_fraction: "0.9998".to_string(),
                skip_self: false,
                self_alignment_available: true,
                include_ref_paf: true,
                include_self_paf: true,
                include_pairwise_paf: true,
                dataset_fasta_relpath: "data/datasets/ds4.fa".to_string(),
                dataset_fai_relpath: "data/datasets/ds4.fa.fai".to_string(),
                locator_fasta_relpath: "data/partitions/chr/r/ds4.fa".to_string(),
                locator_seq_name: None,
                tel_enabled: false,
                cen_enabled: false,
                include_tel_payload: false,
                include_cen_payload: false,
                include_extra_payload_file: false,
            }
        }
    }

    fn import_workspace_with_project(root: &Path) -> (ImportOutcome, i64) {
        let bundle_root = root.join("gpm_server");
        create_partitioned_fast_bundle_root(&bundle_root, true);
        write_prepare_options(&bundle_root, "asm10", false);
        let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
        let project_id = insert_existing_project(&outcome.project_db_path);
        (outcome, project_id)
    }

    fn write_prepare_options(bundle_root: &Path, minimap_preset: &str, skip_self: bool) {
        fs::write(
            bundle_root.join("metadata/prepare_options.tsv"),
            format!(
                concat!(
                    "key\tvalue\n",
                    "chr_assignment_min_coverage_percent\t60\n",
                    "alignment_engine\tminimap2\n",
                    "minimap_preset\t{}\n",
                    "blastn_task\tblastn\n",
                    "blastn_evalue\t1e-10\n",
                    "blastn_dust\tno\n",
                    "winnowmap_preset\tasm20\n",
                    "winnowmap_kmer\t19\n",
                    "winnowmap_repeat_fraction\t0.9998\n",
                    "threads\t10\n",
                    "skip_self\t{}\n",
                    "self_alignment_scope\t{}\n",
                    "tel_enabled\tfalse\n",
                    "cen_enabled\tfalse\n",
                    "cen_min_len\t10000\n",
                    "cen_min_identity\t80\n",
                ),
                minimap_preset,
                if skip_self { "true" } else { "false" },
                if skip_self { "none" } else { "chr_partition" }
            ),
        )
        .unwrap();
    }

    fn insert_existing_project(project_db_path: &Path) -> i64 {
        let conn = Connection::open(project_db_path).unwrap();
        let reference_id: i64 = conn
            .query_row(
                "SELECT id FROM reference_genome WHERE name = 'ref_a'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let primary_dataset_id: i64 = conn
            .query_row("SELECT id FROM dataset WHERE name = 'ds_a'", [], |row| {
                row.get(0)
            })
            .unwrap();
        conn.execute(
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id,
                chr_assignment_min_coverage_percent, created_at
             ) VALUES ('existing', 1, ?1, ?2, 60, 'now')",
            params![reference_id, primary_dataset_id],
        )
        .unwrap();
        let project_id = conn.last_insert_rowid();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, ?2, 'primary', 1)",
            params![project_id, primary_dataset_id],
        )
        .unwrap();
        project_id
    }

    fn insert_support_project_dataset(
        project_db_path: &Path,
        project_id: i64,
        dataset_name: &str,
        display_order: i64,
    ) {
        let conn = Connection::open(project_db_path).unwrap();
        let dataset_id: i64 = conn
            .query_row(
                "SELECT id FROM dataset WHERE name = ?1",
                params![dataset_name],
                |row| row.get(0),
            )
            .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (?1, ?2, 'support', ?3)",
            params![project_id, dataset_id, display_order],
        )
        .unwrap();
    }

    fn query_pairwise_run_ids_for_dataset_names(
        conn: &Connection,
        dataset_names: &[&str],
    ) -> Vec<i64> {
        let placeholders = dataset_names
            .iter()
            .map(|_| "?")
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT DISTINCT r.id
             FROM pairwise_alignment_run r
             JOIN dataset q ON q.id = r.query_dataset_id
             JOIN dataset t ON t.id = r.target_dataset_id
             WHERE q.name IN ({placeholders}) OR t.name IN ({placeholders})
             ORDER BY r.id"
        );
        let params = dataset_names
            .iter()
            .chain(dataset_names.iter())
            .map(|value| rusqlite::types::Value::Text((*value).to_string()))
            .collect::<Vec<_>>();
        let mut stmt = conn.prepare(&sql).unwrap();
        stmt.query_map(rusqlite::params_from_iter(params), |row| row.get(0))
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap()
    }

    fn query_project_assembly_rows(
        conn: &Connection,
        project_id: i64,
    ) -> Vec<(String, String, Option<String>)> {
        let mut stmt = conn
            .prepare(
                "SELECT c.name, s.orient, c.ref_orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.project_id = ?1
                 ORDER BY c.id",
            )
            .unwrap();
        stmt.query_map(params![project_id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
    }

    fn query_project_assembly_rows_excluding_dataset(
        conn: &Connection,
        project_id: i64,
        dataset_id: i64,
    ) -> Vec<(String, String, Option<String>)> {
        let mut stmt = conn
            .prepare(
                "SELECT c.name, s.orient, c.ref_orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 WHERE c.project_id = ?1 AND ss.dataset_id != ?2
                 ORDER BY c.id",
            )
            .unwrap();
        stmt.query_map(params![project_id, dataset_id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
    }

    fn write_add_ctg_zip(zip_path: &Path) {
        let file = File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let options = FileOptions::default().compression_method(CompressionMethod::Stored);

        zip.start_file("add_ctg/manifest.tsv", options).unwrap();
        zip.write_all(
            concat!(
                "package_type\tadd_ctg\n",
                "ctg_name\tgap_filled\n",
                "derived_dataset\tderived_ctg\n",
                "target_chr\tr\n",
                "target_track\tds_a\n",
                "source\tgapfiller\n",
                "reference_name\tref_a\n",
                "alignment_engine\tminimap2\n",
                "minimap_preset\tasm10\n",
                "blastn_task\tblastn\n",
                "blastn_evalue\t1e-10\n",
                "blastn_dust\tno\n",
                "winnowmap_preset\tasm20\n",
                "winnowmap_kmer\t19\n",
                "winnowmap_repeat_fraction\t0.9998\n",
                "skip_self\tfalse\n",
                "self_alignment_scope\tchr_partition\n",
                "cross_alignment_scope\tchr_partition\n",
                "sequence_layout\tpartitioned\n",
                "preassigned_chr\ttrue\n",
                "contains_fasta\ttrue\n",
                "created_at\t1\n",
            )
            .as_bytes(),
        )
        .unwrap();

        zip.start_file("gpm_server/metadata/datasets.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n\
derived_ctg\tderived_ctg\t\tdata/datasets/derived_ctg.fa\tdata/datasets/derived_ctg.fa.fai\ttrue\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/derived_ctgs.tsv", options)
            .unwrap();
        zip.write_all(
            b"derived_dataset\tctg_name\tsource\tsource_fasta_name\tsource_fasta_sha256\tcreated_at\n\
derived_ctg\tgap_filled\tgapfiller\tfinal.fa\tsha\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/track_members.tsv", options)
            .unwrap();
        zip.write_all(
            b"member_dataset\tmember_ctg\ttarget_chr\ttarget_track\tmember_role\tcreated_at\n\
derived_ctg\tgap_filled\tr\tds_a\tderived\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\n\
derived_ctg\tgap_filled\t4\tr\t4\t100.000\t2\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tfasta_relpath\n\
derived_ctg\tgap_filled\tdata/derived_ctgs/gap_filled.fa\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_n_regions.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\n\
derived_ctg\tgap_filled\t2\t2\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/data/derived_ctgs/gap_filled.fa", options)
            .unwrap();
        zip.write_all(b">gap_filled\nANCG\n").unwrap();
        zip.start_file("gpm_server/data/derived_ctgs/gap_filled.fa.fai", options)
            .unwrap();
        zip.write_all(b"gap_filled\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/datasets/derived_ctg.fa", options)
            .unwrap();
        zip.write_all(b">gap_filled\nANCG\n").unwrap();
        zip.start_file("gpm_server/data/datasets/derived_ctg.fa.fai", options)
            .unwrap();
        zip.write_all(b"gap_filled\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/runs/chr_r/datasets/derived_ctg.fa", options)
            .unwrap();
        zip.write_all(b">gap_filled\nANCG\n").unwrap();
        zip.start_file("gpm_server/runs/add_ctg/gap_filled_vs_ref/result.paf", options)
            .unwrap();
        zip.write_all(b"gap_filled\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n")
            .unwrap();
        zip.start_file(
            "gpm_server/runs/chr_r/add_ctg/ds_a_vs_gap_filled/result.paf",
            options,
        )
        .unwrap();
        zip.write_all(b"gap_filled\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n")
            .unwrap();
        zip.start_file(
            "gpm_server/runs/chr_r/add_ctg/ds_b_vs_gap_filled/result.paf",
            options,
        )
        .unwrap();
        zip.write_all(b"gap_filled\t4\t0\t4\t+\te\t4\t0\t4\t4\t4\t60\n")
            .unwrap();
        zip.finish().unwrap();
    }

    fn write_add_dataset_zip(zip_path: &Path, options: AddZipOptions) {
        let file = File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let zip_options = FileOptions::default().compression_method(CompressionMethod::Stored);
        let dataset_name = options.dataset_name.as_str();
        let seq_name = if dataset_name == "ds_a" { "d" } else { "x" };
        let locator_seq_name = options.locator_seq_name.as_deref().unwrap_or(seq_name);
        let dataset_fasta_relpath = options.dataset_fasta_relpath.replace("ds4", dataset_name);
        let dataset_fai_relpath = options.dataset_fai_relpath.replace("ds4", dataset_name);
        let locator_fasta_relpath = options.locator_fasta_relpath.replace("ds4", dataset_name);

        zip.start_file("add_package/manifest.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                concat!(
                    "package_type\t{}\n",
                    "dataset_name\t{}\n",
                    "reference_name\t{}\n",
                    "sequence_layout\t{}\n",
                    "preassigned_chr\ttrue\n",
                    "chr_assignment_min_coverage_percent\t{}\n",
                    "alignment_engine\t{}\n",
                    "minimap_preset\t{}\n",
                    "blastn_task\t{}\n",
                    "blastn_evalue\t{}\n",
                    "blastn_dust\t{}\n",
                    "winnowmap_preset\t{}\n",
                    "winnowmap_kmer\t{}\n",
                    "winnowmap_repeat_fraction\t{}\n",
                    "skip_self\t{}\n",
                    "self_alignment_available\t{}\n",
                    "tel_enabled\t{}\n",
                    "cen_enabled\t{}\n",
                ),
                options.package_type,
                dataset_name,
                options.reference_name,
                options.sequence_layout,
                options.chr_assignment_min_coverage_percent,
                options.alignment_engine,
                options.minimap_preset,
                options.blastn_task,
                options.blastn_evalue,
                options.blastn_dust,
                options.winnowmap_preset,
                options.winnowmap_kmer,
                options.winnowmap_repeat_fraction,
                if options.skip_self { "true" } else { "false" },
                if options.self_alignment_available {
                    "true"
                } else {
                    "false"
                },
                if options.tel_enabled { "true" } else { "false" },
                if options.cen_enabled { "true" } else { "false" }
            )
            .as_bytes(),
        )
        .unwrap();

        zip.start_file("gpm_server/metadata/datasets.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n{dataset_name}\tassembler_4\t\t{dataset_fasta_relpath}\t{dataset_fai_relpath}\t{}\n",
                if options.self_alignment_available { "true" } else { "false" }
            )
            .as_bytes(),
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/chr_assignments.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\n{dataset_name}\t{seq_name}\t4\tr\t4\t100.000\t2\n"
            )
            .as_bytes(),
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_locator.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "dataset_name\tseq_name\tfasta_relpath\n{dataset_name}\t{locator_seq_name}\t{locator_fasta_relpath}\n"
            )
            .as_bytes(),
        )
        .unwrap();
        zip.start_file(
            format!("gpm_server/data/datasets/{dataset_name}.fa"),
            zip_options,
        )
        .unwrap();
        zip.write_all(format!(">{seq_name}\nTGCA\n").as_bytes())
            .unwrap();
        zip.start_file(
            format!("gpm_server/data/datasets/{dataset_name}.fa.fai"),
            zip_options,
        )
        .unwrap();
        zip.write_all(format!("{seq_name}\t4\t0\t4\t5\n").as_bytes())
            .unwrap();
        zip.start_file(
            format!("gpm_server/data/partitions/chr/r/{dataset_name}.fa"),
            zip_options,
        )
        .unwrap();
        zip.write_all(format!(">{seq_name}\nTGCA\n").as_bytes())
            .unwrap();
        if options.include_ref_paf {
            zip.start_file(
                format!("gpm_server/runs/{dataset_name}_vs_ref/result.paf"),
                zip_options,
            )
            .unwrap();
            zip.write_all(format!("{seq_name}\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n").as_bytes())
                .unwrap();
        }
        if options.include_self_paf {
            zip.start_file(
                format!("gpm_server/runs/chr_r/{dataset_name}_vs_self/result.paf"),
                zip_options,
            )
            .unwrap();
            zip.write_all(
                format!("{seq_name}\t4\t0\t4\t+\t{seq_name}\t4\t0\t4\t4\t4\t60\n").as_bytes(),
            )
            .unwrap();
        }
        if options.include_pairwise_paf {
            zip.start_file(
                format!("gpm_server/runs/chr_r/ds_a_vs_{dataset_name}/result.paf"),
                zip_options,
            )
            .unwrap();
            zip.write_all(format!("{seq_name}\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n").as_bytes())
                .unwrap();
        }
        if options.include_tel_payload {
            zip.start_file("gpm_server/tel/rules.tsv", zip_options)
                .unwrap();
            zip.write_all(
                b"rule_id\tmotif\tmin_repeat\treverse_complement\ntel_fwd\tTTAGGG\t2\tfalse\n",
            )
            .unwrap();
            zip.start_file("gpm_server/tel/chr_r/marks.tsv", zip_options)
                .unwrap();
            zip.write_all(
                format!(
                    "rule_id\tdataset_name\tseq_name\tassigned_chr_name\tmotif\tmin_repeat\trepeat_count\tstart_bp\tend_bp\tstrand\ntel_fwd\t{dataset_name}\t{seq_name}\tr\tTTAGGG\t2\t2\t1\t12\t+\n"
                )
                .as_bytes(),
            )
            .unwrap();
        }
        if options.include_cen_payload {
            zip.start_file("gpm_server/cen/chr_r/marks.tsv", zip_options)
                .unwrap();
            zip.write_all(
                format!(
                    "cen_id\tchr_name\tquery_name\tdataset_name\tctg_name\tctg_start\tctg_end\tstrand\talign_length\tidentity\tmapq\ncen1\tr\tcen_query\t{dataset_name}\t{seq_name}\t1\t4\t+\t4\t99.0\t60\n"
                )
                .as_bytes(),
            )
            .unwrap();
        }
        if options.include_extra_payload_file {
            zip.start_file("gpm_server/notes/evil.txt", zip_options)
                .unwrap();
            zip.write_all(b"unexpected").unwrap();
        }

        zip.finish().unwrap();
    }

    fn write_bundle_zip(zip_path: &Path) {
        let file = File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let options = FileOptions::default().compression_method(CompressionMethod::Stored);

        zip.add_directory("gpm_server/metadata/", options).unwrap();
        zip.add_directory("gpm_server/data/reference/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/datasets/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/reference/chrs/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
            .unwrap();
        zip.add_directory("gpm_server/runs/", options).unwrap();

        zip.start_file("gpm_server/metadata/reference.tsv", options)
            .unwrap();
        zip.write_all(
            b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/datasets.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/package.tsv", options)
            .unwrap();
        zip.write_all(
            b"package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t4\t100.000\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
            .unwrap();
        zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
            .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
        )
        .unwrap();
        zip.start_file("gpm_server/data/reference/ref.fa", options)
            .unwrap();
        zip.write_all(b">ref\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
            .unwrap();
        zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/datasets/ds.fa", options)
            .unwrap();
        zip.write_all(b">ds\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
            .unwrap();
        zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/reference/chrs/ref.fa", options)
            .unwrap();
        zip.write_all(b">ref\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/partitions/chr/ref/ds_a.fa", options)
            .unwrap();
        zip.write_all(b">ds\nACGT\n").unwrap();
        zip.start_file("gpm_server/runs/.keep", options).unwrap();
        zip.write_all(b"").unwrap();

        zip.finish().unwrap();
    }

    fn write_bundle_zip_without_fasta(zip_path: &Path) {
        let file = File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let options = FileOptions::default().compression_method(CompressionMethod::Stored);

        zip.add_directory("gpm_server/metadata/", options).unwrap();
        zip.add_directory("gpm_server/data/reference/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/datasets/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/reference/chrs/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
            .unwrap();
        zip.add_directory("gpm_server/runs/", options).unwrap();

        zip.start_file("gpm_server/metadata/reference.tsv", options)
            .unwrap();
        zip.write_all(
            b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/datasets.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/package.tsv", options)
            .unwrap();
        zip.write_all(
            b"package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t4\t100.000\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
            .unwrap();
        zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
            .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
        )
        .unwrap();
        zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
            .unwrap();
        zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
            .unwrap();
        zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/runs/.keep", options).unwrap();
        zip.write_all(b"").unwrap();

        zip.finish().unwrap();
    }

    fn write_bundle_zip_with_self_alignment_flag(zip_path: &Path, available: bool) {
        let file = File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let options = FileOptions::default().compression_method(CompressionMethod::Stored);
        let availability = if available { "true" } else { "false" };
        let self_scope = if available { "chr_partition" } else { "none" };

        zip.add_directory("gpm_server/metadata/", options).unwrap();
        zip.add_directory("gpm_server/data/reference/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/datasets/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/reference/chrs/", options)
            .unwrap();
        zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
            .unwrap();
        zip.add_directory("gpm_server/runs/", options).unwrap();

        zip.start_file("gpm_server/metadata/reference.tsv", options)
            .unwrap();
        zip.write_all(
            b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/datasets.tsv", options)
            .unwrap();
        zip.write_all(
            format!(
                "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\t{}\n",
                availability
            )
            .as_bytes(),
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/package.tsv", options)
            .unwrap();
        zip.write_all(
            format!(
                "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\t{}\tchr_partition\n",
                self_scope
            )
            .as_bytes(),
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t4\t100.000\t1\n",
        )
        .unwrap();
        zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
            .unwrap();
        zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
            .unwrap();
        zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
            .unwrap();
        zip.write_all(
            b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
        )
        .unwrap();
        zip.start_file("gpm_server/data/reference/ref.fa", options)
            .unwrap();
        zip.write_all(b">ref\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
            .unwrap();
        zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/datasets/ds.fa", options)
            .unwrap();
        zip.write_all(b">ds\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
            .unwrap();
        zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
        zip.start_file("gpm_server/data/reference/chrs/ref.fa", options)
            .unwrap();
        zip.write_all(b">ref\nACGT\n").unwrap();
        zip.start_file("gpm_server/data/partitions/chr/ref/ds_a.fa", options)
            .unwrap();
        zip.write_all(b">ds\nACGT\n").unwrap();

        zip.finish().unwrap();
    }

    fn count_rows(project_db_path: &Path, table: &str) -> i64 {
        let conn = Connection::open(project_db_path).unwrap();
        let sql = format!("SELECT COUNT(*) FROM {}", table);
        conn.query_row(&sql, [], |row| row.get(0)).unwrap()
    }

    fn dataset_stats(project_db_path: &Path, name: &str) -> Option<(i64, i64)> {
        let conn = Connection::open(project_db_path).unwrap();
        conn.query_row(
            "SELECT contig_count, total_length_bp FROM dataset WHERE name = ?1",
            params![name],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .ok()
    }
}
