use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64_STANDARD};
use gpm_next_backend::auto_orientation::{
    AutoOrientContigsParams, auto_orient_contigs_cancel as backend_auto_orient_contigs_cancel,
    auto_orient_contigs_for_dataset_cancel as backend_auto_orient_contigs_for_dataset_cancel,
};
use gpm_next_backend::auto_placement::{
    AutoAssignChrParams, auto_assign_chr_cancel as backend_auto_assign_chr_cancel,
};
use gpm_next_backend::ctg_editor::{
    DeleteCtgParams, FlipCtgParams, FlipSeqParams, HideSeqParams, RenameCtgParams,
    RestoreDeletedCtgParams, SetEndTypeParams, ShowSeqParams, delete_ctg, flip_ctg, flip_seq,
    hide_seq, list_deleted_ctgs as backend_list_deleted_ctgs, rename_ctg,
    restore_deleted_ctg as backend_restore_deleted_ctg, set_end_type, show_seq,
};
use gpm_next_backend::degap_jobs::{
    ExportDegapJobsParams, export_degap_jobs as backend_export_degap_jobs, parse_degap_export_jobs,
    parse_degap_export_settings,
};
use gpm_next_backend::exporter::{
    ExportFinalPathFastaParams, ExportProjectFinalPathFastaParams, FinalPathExportSegment,
    FinalPathFastaRecord, ListExportRecordsParams,
    export_final_path_fasta as backend_export_final_path_fasta,
    export_project_final_path_fasta as backend_export_project_final_path_fasta,
    list_export_records as backend_list_export_records,
};
use gpm_next_backend::grt_package::{
    GrtLockedRecipe,
    initialize_grt_project_with_options as backend_initialize_grt_project_with_options,
    load_grt_locked_recipe as backend_load_grt_locked_recipe,
    load_grt_project_view as backend_load_grt_project_view,
};
use gpm_next_backend::importer::{
    AddCtgImportTarget, ImportProgress, import_add_ctg_package_with_hooks,
    import_from_extracted_bundle_with_hooks, import_from_zip_with_hooks,
    import_workspace_add_dataset_package_with_hooks,
};
use gpm_next_backend::junction_inspection::{
    GetJunctionInspectionParams, GetTrackPairwiseEvidenceParams,
    get_junction_inspection as backend_get_junction_inspection,
    get_track_pairwise_evidence as backend_get_track_pairwise_evidence,
};
use gpm_next_backend::main_view::{
    get_ctg_detail as backend_get_ctg_detail, list_chr_view_ctgs as backend_list_chr_view_ctgs,
    list_ctg_edit_candidates as backend_list_ctg_edit_candidates,
    list_project_chromosomes as backend_list_project_chromosomes,
    list_project_new_sequences as backend_list_project_new_sequences,
    list_reference_track_members as backend_list_reference_track_members,
};
use gpm_next_backend::phased_assembly::{
    PhasedChrTrack, PhasedChrTrackItem,
    add_ctg_to_phased_chr_track as backend_add_ctg_to_phased_chr_track,
    create_phased_chr_track as backend_create_phased_chr_track,
    delete_phased_chr_track as backend_delete_phased_chr_track,
    flip_phased_chr_track_item as backend_flip_phased_chr_track_item,
    list_phased_chr_tracks as backend_list_phased_chr_tracks,
    remove_phased_chr_track_item as backend_remove_phased_chr_track_item,
    reorder_phased_chr_track_items as backend_reorder_phased_chr_track_items,
};
use gpm_next_backend::project_initializer::{
    ProjectUpdateRequest,
    bootstrap_project_assembly_cancel as backend_bootstrap_project_assembly_cancel,
    delete_project as backend_delete_project,
    list_initializer_options as backend_list_initializer_options,
    set_project_auto_pipeline_done as backend_set_project_auto_pipeline_done,
    update_project as backend_update_project,
};
use gpm_next_backend::runtime_persistence::{
    AppendEditAuditLogParams, ListEditAuditLogsParams, UpdateProjectAssemblyViewStateParams,
    UpdateRuntimeSettingsParams, append_edit_audit_log as backend_append_edit_audit_log,
    clear_edit_audit_logs as backend_clear_edit_audit_logs,
    get_project_assembly_view_state as backend_get_project_assembly_view_state,
    get_runtime_settings as backend_get_runtime_settings,
    list_edit_audit_logs as backend_list_edit_audit_logs,
    update_project_assembly_view_state as backend_update_project_assembly_view_state,
    update_runtime_settings as backend_update_runtime_settings,
};
use gpm_next_backend::workspace::looks_like_bundle_root;
use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tauri::{AppHandle, Emitter};

use crate::auto_pipeline_cancel;
use crate::import_cancel;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InitializeProjectCommandRequest {
    workspace_root: String,
    project_name: String,
    phased_assembly_enabled: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateProjectCommandRequest {
    workspace_root: String,
    project_id: i64,
    project_name: String,
    reference_genome_id: i64,
    primary_dataset_id: i64,
    support_dataset_ids: Option<Vec<i64>>,
    chr_assignment_min_coverage_percent: Option<f64>,
    phased_assembly_enabled: Option<bool>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateProjectAssemblyViewStateCommandRequest {
    workspace_root: String,
    project_id: i64,
    support_dataset_id: Option<i64>,
    track_view: Value,
    support_ds_ctg_len_rules_by_chr: Value,
    track_scroll_state: Value,
    subview_track_scroll_state: Value,
    support_mirrored_ctgs: Value,
    hidden_primary_ctg_ids: Value,
    hidden_primary_ctg_ids_by_chr: Value,
    track_drag_offsets: Value,
    subview_track_drag_offsets: Value,
    subview_anchor_state_by_key: Value,
    final_path_view_mode: String,
    final_path_by_chr: Value,
    degap_project_state: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandError {
    code: String,
    message: String,
    operation: String,
    data: Value,
}

type CommandResult<T> = std::result::Result<T, CommandError>;

impl CommandError {
    fn backend(error: anyhow::Error) -> Self {
        let message = format!("{error:#}");
        Self {
            code: classify_command_error_code(&message).to_string(),
            message,
            operation: String::new(),
            data: Value::Null,
        }
    }

    fn runtime(message: impl Into<String>) -> Self {
        Self {
            code: "RUNTIME_ERROR".to_string(),
            message: message.into(),
            operation: String::new(),
            data: Value::Null,
        }
    }
}

impl From<String> for CommandError {
    fn from(message: String) -> Self {
        Self::runtime(message)
    }
}

fn classify_command_error_code(message: &str) -> &str {
    if let Some(code) = message.split_whitespace().find_map(|token| {
        let candidate = token.trim_end_matches(':');
        (token.ends_with(':')
            && candidate.contains('_')
            && candidate.chars().all(|character| {
                character.is_ascii_uppercase() || character.is_ascii_digit() || character == '_'
            }))
        .then_some(candidate)
    }) {
        return code;
    }

    let normalized = message.to_ascii_lowercase();
    if normalized.contains("does not exist") || normalized.contains("not found") {
        return "NOT_FOUND";
    }
    if normalized.contains("already")
        || normalized.contains("conflict")
        || normalized.contains("cannot")
        || normalized.contains("only allow")
        || normalized.contains("entered assembly")
    {
        return "STATE_CONFLICT";
    }
    if normalized.contains("invalid")
        || normalized.contains("missing")
        || normalized.contains("must ")
        || normalized.contains("required")
    {
        return "INVALID_REQUEST";
    }
    "BACKEND_ERROR"
}

fn project_db_path(workspace_root: &str) -> PathBuf {
    Path::new(workspace_root).join("project.sqlite")
}

fn map_grt_recipe(recipe: &GrtLockedRecipe) -> Value {
    json!({
        "workflow": recipe.workflow,
        "schemaVersion": recipe.schema_version,
        "finalPathSchemaVersion": recipe.final_path_schema_version,
        "recipeId": recipe.recipe_id,
        "primaryDataset": recipe.primary_dataset,
        "supportDatasets": recipe.support_datasets,
        "readsQcEnabled": recipe.reads_qc_enabled,
        "donorSetId": recipe.donor_set_id,
        "telDonorSetId": recipe.tel_donor_set_id,
        "q0Relpath": recipe.q0_relpath,
        "finalQRelpath": recipe.final_q_relpath,
        "q0ArtifactSha256": recipe.q0_artifact_sha256,
        "q4ArtifactSha256": recipe.q4_artifact_sha256,
    })
}

fn ensure_existing_workspace_db(workspace_root: &str) -> Result<PathBuf> {
    let root = Path::new(workspace_root);
    if !root.exists() {
        bail!("workspace root does not exist: {}", root.display());
    }
    if !root.is_dir() {
        bail!("workspace root is not a directory: {}", root.display());
    }

    let project_db = project_db_path(workspace_root);
    if !project_db.exists() {
        bail!("workspace missing project.sqlite: {}", project_db.display());
    }
    if !project_db.is_file() {
        bail!(
            "workspace project.sqlite path is not a file: {}",
            project_db.display()
        );
    }
    Ok(project_db)
}

fn directory_has_entries(path: &Path) -> Result<bool> {
    if !path.exists() || !path.is_dir() {
        return Ok(false);
    }
    let mut entries = fs::read_dir(path)
        .with_context(|| format!("failed to read directory {}", path.display()))?;
    Ok(entries.next().is_some())
}

fn count_named_files_recursive(root: &Path, file_name: &str) -> Result<usize> {
    if !root.exists() || !root.is_dir() {
        return Ok(0);
    }
    let mut total = 0usize;
    let entries = fs::read_dir(root)
        .with_context(|| format!("failed to read directory {}", root.display()))?;
    for entry in entries {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", root.display()))?;
        let path = entry.path();
        let metadata = entry
            .metadata()
            .with_context(|| format!("failed to read metadata for {}", path.display()))?;
        if metadata.is_dir() {
            total += count_named_files_recursive(&path, file_name)?;
            continue;
        }
        if metadata.is_file() && entry.file_name().to_string_lossy() == file_name {
            total += 1;
        }
    }
    Ok(total)
}

fn looks_like_deletable_workspace_root(path: &Path) -> bool {
    if !path.exists() || !path.is_dir() {
        return false;
    }
    if path.join("project.sqlite").is_file() {
        return true;
    }
    if looks_like_bundle_root(path) {
        return true;
    }
    let embedded_workspace = path.join(".gpm_next_workspace");
    embedded_workspace.join("project.sqlite").is_file()
}

fn read_initializer_options(workspace_root: &str, strict_existing: bool) -> Result<Value> {
    let project_db = if strict_existing {
        ensure_existing_workspace_db(workspace_root)?
    } else {
        project_db_path(workspace_root)
    };
    let options = backend_list_initializer_options(&project_db)?;
    let grt_recipe = backend_load_grt_locked_recipe(&project_db)?;
    let references = options
        .references
        .into_iter()
        .map(|reference| {
            json!({
                "referenceGenomeId": reference.id,
                "name": reference.name,
                "speciesName": reference.species_name,
                "assemblyLabel": reference.assembly_label,
                "label": reference.name
            })
        })
        .collect::<Vec<_>>();
    let datasets = options
        .datasets
        .into_iter()
        .map(|dataset| {
            json!({
                "datasetId": dataset.id,
                "name": dataset.name,
                "assembler": dataset.assembler,
                "assemblerVersion": dataset.assembler_version,
                "contigCount": dataset.contig_count,
                "totalLengthBp": dataset.total_length_bp,
                "fastaAvailable": dataset.fasta_available,
                "selfAlignmentAvailable": dataset.self_alignment_available,
                "label": dataset.name
            })
        })
        .collect::<Vec<_>>();
    let package_metadata = json!({
        "packageMode": options.package_metadata.package_mode,
        "sequenceLayout": options.package_metadata.sequence_layout,
        "preassignedChr": options.package_metadata.preassigned_chr,
        "chrAssignmentMinCoveragePercent": options.package_metadata.chr_assignment_min_coverage_percent,
        "selfAlignmentScope": options.package_metadata.self_alignment_scope,
        "crossAlignmentScope": options.package_metadata.cross_alignment_scope
    });
    let existing_projects = map_existing_projects(options.existing_projects);
    Ok(json!({
        "workspaceRoot": workspace_root,
        "packageMetadata": package_metadata,
        "grtRecipe": map_grt_recipe(&grt_recipe),
        "references": references,
        "datasets": datasets,
        "existingProjects": existing_projects
    }))
}

fn map_existing_projects(
    items: Vec<gpm_next_backend::project_initializer::ExistingProjectOption>,
) -> Vec<Value> {
    items
        .into_iter()
        .map(|project| {
            json!({
                "projectId": project.id,
                "projectName": project.name,
                "version": project.version,
                "referenceGenomeId": project.reference_genome_id,
                "referenceName": project.reference_name,
                "primaryDatasetId": project.primary_dataset_id,
                "primaryDatasetName": project.primary_dataset_name,
                "supportDatasetIds": project.support_dataset_ids,
                "isProcessed": project.is_processed,
                "autoPipelineDone": project.auto_pipeline_done,
                "autoCheckNewSeq": project.auto_check_new_seq,
                "phasedAssemblyEnabled": project.phased_assembly_enabled,
                "chrAssignmentMinCoveragePercent": project.chr_assignment_min_coverage_percent,
                "description": project.description,
                "createdAt": project.created_at
            })
        })
        .collect::<Vec<_>>()
}

fn map_phased_track_item(item: PhasedChrTrackItem) -> Value {
    json!({
        "itemId": item.id,
        "phasedTrackId": item.phased_track_id,
        "assemblyCtgId": item.assembly_ctg_id,
        "displayOrder": item.display_order,
        "gapBeforePx": item.gap_before_px,
        "orient": item.orient
    })
}

fn map_phased_track(track: PhasedChrTrack) -> Value {
    let items = track
        .items
        .into_iter()
        .map(map_phased_track_item)
        .collect::<Vec<_>>();
    json!({
        "phasedTrackId": track.id,
        "projectId": track.project_id,
        "parentChrName": track.parent_chr_name,
        "haplotypeKey": track.haplotype_key,
        "label": track.label,
        "displayOrder": track.display_order,
        "items": items
    })
}

fn format_error(error: anyhow::Error) -> CommandError {
    CommandError::backend(error)
}

fn is_auto_pipeline_cancelled(workspace_root: &str, project_id: i64, run_id: Option<&str>) -> bool {
    let Some(run_id) = run_id else {
        return false;
    };
    auto_pipeline_cancel::is_cancelled(workspace_root, project_id, run_id)
}

fn clear_auto_pipeline_cancel(workspace_root: &str, project_id: i64, run_id: Option<&str>) {
    if let Some(run_id) = run_id {
        let _ = auto_pipeline_cancel::clear_cancel(workspace_root, project_id, run_id);
    }
}

fn normalize_optional_run_id(run_id: Option<String>) -> Option<String> {
    run_id
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn format_import_stage(step: &ImportProgress) -> String {
    let label = format!("{}：{}", step.stage, step.detail);
    match (step.progress_index, step.progress_total) {
        (Some(index), Some(total)) => format!("{label} ({index}/{total})"),
        _ => label,
    }
}

fn emit_import_progress(app: &AppHandle, run_id: Option<&str>, step: ImportProgress) {
    let Some(run_id) = run_id else {
        return;
    };
    let _ = app.emit(
        "gpm-next://import-progress",
        import_progress_payload(run_id, &step),
    );
}

fn import_progress_payload(run_id: &str, step: &ImportProgress) -> Value {
    json!({
        "runId": run_id,
        "stage": step.stage,
        "detail": step.detail,
        "label": format!("{}：{}", step.stage, step.detail),
        "text": format_import_stage(step),
        "progressIndex": step.progress_index,
        "progressTotal": step.progress_total,
        "phaseIndex": step.phase_index,
        "phaseTotal": step.phase_total
    })
}

fn path_to_string(path: &Path) -> String {
    path.to_string_lossy().to_string()
}

fn get_required_value<'a>(args: &'a Value, key: &str) -> Result<&'a Value> {
    let object = args
        .as_object()
        .ok_or_else(|| anyhow!("args must be a JSON object"))?;
    object
        .get(key)
        .ok_or_else(|| anyhow!("missing required args.{key}"))
}

fn value_to_i64(value: &Value, key: &str) -> Result<i64> {
    if let Some(number) = value.as_i64() {
        return Ok(number);
    }
    if let Some(text) = value.as_str() {
        return text
            .trim()
            .parse::<i64>()
            .with_context(|| format!("args.{key} is not a valid integer"));
    }
    bail!("args.{key} is not a valid integer");
}

fn get_required_i64(args: &Value, key: &str) -> Result<i64> {
    let value = get_required_value(args, key)?;
    value_to_i64(value, key)
}

fn apply_item_limit<T>(items: Vec<T>, limit: Option<i64>) -> Vec<T> {
    let Some(limit) = limit else {
        return items;
    };
    if limit < 0 {
        return items;
    }
    items.into_iter().take(limit as usize).collect()
}

fn get_required_string(args: &Value, key: &str) -> Result<String> {
    let value = get_required_value(args, key)?;
    let text = value
        .as_str()
        .ok_or_else(|| anyhow!("args.{key} must be a string"))?
        .trim()
        .to_string();
    if text.is_empty() {
        bail!("args.{key} must not be blank");
    }
    Ok(text)
}

fn normalize_final_path_export_segments(
    final_path_entry: &Value,
) -> Result<Vec<FinalPathExportSegment>> {
    let segments = final_path_entry
        .get("segments")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("finalPathEntry.segments must be an array"))?;
    segments
        .iter()
        .enumerate()
        .map(|(index, segment)| {
            let segment_type = segment
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("ctg")
                .trim()
                .to_ascii_lowercase();
            if segment_type == "gap" {
                let gap_size_bp = segment
                    .get("gapSizeBp")
                    .map(|value| {
                        value_to_i64(value, "finalPathEntry.segments[].gapSizeBp").with_context(
                            || format!("finalPathEntry.segments[{index}] invalid gapSizeBp"),
                        )
                    })
                    .transpose()?
                    .unwrap_or(100);
                return Ok(FinalPathExportSegment::Gap { gap_size_bp });
            }
            let source_kind = segment
                .get("sourceKind")
                .and_then(Value::as_str)
                .unwrap_or("assembly_ctg")
                .trim()
                .to_ascii_lowercase();
            let start = segment
                .get("start")
                .ok_or_else(|| anyhow!("finalPathEntry.segments[{index}] missing start"))
                .and_then(|value| value_to_i64(value, "finalPathEntry.segments[].start"))?;
            let end = segment
                .get("end")
                .ok_or_else(|| anyhow!("finalPathEntry.segments[{index}] missing end"))
                .and_then(|value| value_to_i64(value, "finalPathEntry.segments[].end"))?;
            if source_kind == "ref_segment" {
                let reference_chr_name = segment
                    .get("referenceChrName")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| {
                        anyhow!("finalPathEntry.segments[{index}] missing referenceChrName")
                    })?
                    .to_string();
                let member_start_bp = segment
                    .get("memberStartBp")
                    .ok_or_else(|| {
                        anyhow!("finalPathEntry.segments[{index}] missing memberStartBp")
                    })
                    .and_then(|value| {
                        value_to_i64(value, "finalPathEntry.segments[].memberStartBp")
                    })?;
                let member_end_bp = segment
                    .get("memberEndBp")
                    .ok_or_else(|| anyhow!("finalPathEntry.segments[{index}] missing memberEndBp"))
                    .and_then(|value| {
                        value_to_i64(value, "finalPathEntry.segments[].memberEndBp")
                    })?;
                return Ok(FinalPathExportSegment::RefSegment {
                    reference_chr_name,
                    member_start_bp,
                    member_end_bp,
                    start,
                    end,
                });
            }
            let assembly_ctg_id = segment
                .get("assemblyCtgId")
                .ok_or_else(|| anyhow!("finalPathEntry.segments[{index}] missing assemblyCtgId"))
                .and_then(|value| value_to_i64(value, "finalPathEntry.segments[].assemblyCtgId"))?;
            Ok(FinalPathExportSegment::Ctg {
                assembly_ctg_id,
                start,
                end,
            })
        })
        .collect()
}

fn normalize_project_final_path_fasta_records(
    final_path_by_chr: &Value,
) -> Result<Vec<FinalPathFastaRecord>> {
    let entries = final_path_by_chr
        .as_object()
        .ok_or_else(|| anyhow!("finalPathByChr must be an object"))?;
    let mut records = Vec::<FinalPathFastaRecord>::new();
    for (key, entry) in entries {
        let chr_name = entry
            .get("chrName")
            .and_then(Value::as_str)
            .unwrap_or(key)
            .trim()
            .to_string();
        if chr_name.is_empty() {
            bail!("finalPathByChr entry has a blank chrName");
        }
        let segments = normalize_final_path_export_segments(entry)
            .with_context(|| format!("finalPathByChr.{chr_name} is invalid"))?;
        if segments.is_empty() {
            continue;
        }
        records.push(FinalPathFastaRecord {
            chr_name,
            final_path_segments: segments,
        });
    }
    if records.is_empty() {
        bail!("finalPathByChr must include at least one non-empty final path");
    }
    Ok(records)
}

fn apply_dialog_filters(mut dialog: FileDialog, filters: &Value) -> FileDialog {
    let Some(items) = filters.as_array() else {
        return dialog;
    };
    for item in items {
        let Some(name) = item.get("name").and_then(Value::as_str) else {
            continue;
        };
        let extensions = item
            .get("extensions")
            .and_then(Value::as_array)
            .map(|values| values.iter().filter_map(Value::as_str).collect::<Vec<_>>())
            .unwrap_or_default();
        if extensions.is_empty() {
            continue;
        }
        dialog = dialog.add_filter(name, &extensions);
    }
    dialog
}

mod assembly;
mod files;
mod imports;
mod persistence;
mod workspace;

pub use assembly::*;
pub use files::*;
pub use imports::*;
pub use persistence::*;
pub use workspace::*;

#[cfg(test)]
mod tests {
    use super::*;
    use gpm_next_backend::db::{init_workspace_schema, open_workspace_db};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn create_test_workspace_root() -> PathBuf {
        let unique = format!(
            "gpm-next-desktop-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock before unix epoch")
                .as_nanos()
        );
        let path = std::env::temp_dir().join(unique);
        fs::create_dir_all(&path).expect("create temp workspace root");
        path
    }

    #[test]
    fn import_progress_payload_includes_phase_metadata() {
        let payload = import_progress_payload(
            "run-1",
            &ImportProgress {
                stage: "validate_grt_source_fastas",
                detail: "validating reference and dataset FASTA/FAI".to_string(),
                progress_index: Some(673),
                progress_total: Some(674),
                phase_index: Some(4),
                phase_total: Some(7),
            },
        );

        assert_eq!(payload["runId"], "run-1");
        assert_eq!(payload["stage"], "validate_grt_source_fastas");
        assert_eq!(payload["progressIndex"], 673);
        assert_eq!(payload["progressTotal"], 674);
        assert_eq!(payload["phaseIndex"], 4);
        assert_eq!(payload["phaseTotal"], 7);
    }

    #[test]
    fn validate_workspace_integrity_accepts_app_delivery_without_server_scripts() {
        let workspace_root = create_test_workspace_root();
        fs::create_dir_all(workspace_root.join("metadata")).expect("create metadata directory");
        fs::create_dir_all(workspace_root.join("data/reference"))
            .expect("create reference directory");
        fs::create_dir_all(workspace_root.join("data/datasets"))
            .expect("create datasets directory");
        fs::create_dir_all(workspace_root.join("runs/primary_vs_ref"))
            .expect("create alignment run directory");
        fs::write(workspace_root.join("project.sqlite"), b"").expect("write project database");
        fs::write(workspace_root.join("metadata/reference.tsv"), b"")
            .expect("write reference metadata");
        fs::write(workspace_root.join("metadata/datasets.tsv"), b"")
            .expect("write dataset metadata");
        fs::write(
            workspace_root.join("data/reference/ref.fa.fai"),
            b"Chr01\t100\n",
        )
        .expect("write reference index");
        fs::write(
            workspace_root.join("data/datasets/primary.fa.fai"),
            b"ctg1\t100\n",
        )
        .expect("write dataset index");
        fs::write(
            workspace_root.join("runs/primary_vs_ref/result.paf"),
            b"ctg1\t100\t0\t100\t+\tChr01\t100\t0\t100\t100\t100\t60\n",
        )
        .expect("write alignment result");

        assert!(!workspace_root.join("run_all.sh").exists());
        let result = validate_workspace_integrity(workspace_root.to_string_lossy().into_owned())
            .expect("validate imported App workspace");

        assert_eq!(result["ok"].as_bool(), Some(true));
        assert_eq!(result["missing"].as_array().map(Vec::len), Some(0));
        assert_eq!(result["resultPafCount"].as_u64(), Some(1));

        fs::remove_dir_all(workspace_root).expect("remove temp workspace root");
    }

    #[test]
    fn command_requests_decode_nested_camel_case_fields() {
        let initialize_request: InitializeProjectCommandRequest = serde_json::from_value(json!({
            "workspaceRoot": "D:\\Desktop\\GPM\\ws1",
            "projectName": "phased-project",
            "phasedAssemblyEnabled": true,
        }))
        .expect("decode initialize-project request");
        assert_eq!(initialize_request.project_name, "phased-project");
        assert!(initialize_request.phased_assembly_enabled);

        let project_request: UpdateProjectCommandRequest = serde_json::from_value(json!({
            "workspaceRoot": "D:\\Desktop\\GPM\\ws1",
            "projectId": 7,
            "projectName": "project-7",
            "referenceGenomeId": 1,
            "primaryDatasetId": 2,
            "supportDatasetIds": [3],
            "chrAssignmentMinCoveragePercent": 60,
            "phasedAssemblyEnabled": true,
        }))
        .expect("decode update-project request");
        assert_eq!(project_request.project_id, 7);
        assert_eq!(project_request.project_name, "project-7");
        assert_eq!(project_request.support_dataset_ids, Some(vec![3]));

        let view_state_request: UpdateProjectAssemblyViewStateCommandRequest =
            serde_json::from_value(json!({
                "workspaceRoot": "D:\\Desktop\\GPM\\ws1",
                "projectId": 9,
                "supportDatasetId": null,
                "trackView": {},
                "supportDsCtgLenRulesByChr": {},
                "trackScrollState": {},
                "subviewTrackScrollState": {},
                "supportMirroredCtgs": [],
                "hiddenPrimaryCtgIds": [],
                "hiddenPrimaryCtgIdsByChr": {},
                "trackDragOffsets": [],
                "subviewTrackDragOffsets": [],
                "subviewAnchorStateByKey": {},
                "finalPathViewMode": "table",
                "finalPathByChr": {},
                "degapProjectState": {},
            }))
            .expect("decode assembly-view request");
        assert_eq!(view_state_request.project_id, 9);
        assert_eq!(view_state_request.final_path_view_mode, "table");
        assert!(view_state_request.track_view.is_object());
    }

    #[test]
    fn list_chr_view_ctgs_includes_origin_id_in_tauri_json() {
        let workspace_root = create_test_workspace_root();
        let project_db = workspace_root.join("project.sqlite");
        let conn = open_workspace_db(&project_db).expect("open temp db");
        init_workspace_schema(&conn).expect("init workspace schema");

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'unknown', 'ref', '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            [],
        )
        .expect("insert reference genome");
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 50000000)",
            [],
        )
        .expect("insert reference chr");
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'hifiasm', 'asm', NULL, '/tmp/a.fa', '/tmp/a.fa.fai')",
            [],
        )
        .expect("insert dataset");
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, created_at)
             VALUES (7, 'projA', 1, 1, 11, '2026-04-13T00:00:00Z')",
            [],
        )
        .expect("insert project");
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig4-001122l', 1, 43726252)",
            [],
        )
        .expect("insert source seq");
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, created_at)
             VALUES (201, 7, 101, '-', 1, 43726252, '2026-04-13T00:00:00Z')",
            [],
        )
        .expect("insert assembly seq");
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at)
             VALUES (301, 7, 201, 'Ctg2', 'Chr01', 1, 1, '+', 'manual', '2026-04-13T00:00:00Z')",
            [],
        )
        .expect("insert assembly ctg");

        let result = list_chr_view_ctgs(
            workspace_root.to_string_lossy().into_owned(),
            7,
            Some("Chr01".to_string()),
            Some(11),
        )
        .expect("list chr view ctgs");

        assert_eq!(
            result["items"][0]["originId"].as_str(),
            Some("utig4-001122l")
        );
        assert_eq!(result["items"][0]["orient"].as_str(), Some("-"));
        assert_eq!(result["items"][0]["refOrient"].as_str(), Some("+"));

        drop(conn);
        fs::remove_dir_all(workspace_root).expect("remove temp workspace root");
    }

    #[test]
    fn list_reference_track_members_in_tauri_json() {
        let workspace_root = create_test_workspace_root();
        let project_db = workspace_root.join("project.sqlite");
        let reference_fasta = workspace_root.join("ref.fa");
        fs::write(
            &reference_fasta,
            format!(
                ">Chr01\n{}{}{}\n",
                "A".repeat(5000),
                "N".repeat(100),
                "C".repeat(5000)
            ),
        )
        .expect("write ref fasta");
        fs::write(workspace_root.join("ref.fa.fai"), "").expect("write ref fai");

        let conn = open_workspace_db(&project_db).expect("open temp db");
        init_workspace_schema(&conn).expect("init workspace schema");

        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (?1, 'ref', 'unknown', 'ref', ?2, ?3)",
            (
                1_i64,
                reference_fasta.to_string_lossy().to_string(),
                workspace_root.join("ref.fa.fai").to_string_lossy().to_string(),
            ),
        )
        .expect("insert reference genome");
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 10100)",
            [],
        )
        .expect("insert reference chr");
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'hifiasm', 'asm', NULL, '/tmp/a.fa', '/tmp/a.fa.fai')",
            [],
        )
        .expect("insert dataset");
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, created_at)
             VALUES (7, 'projA', 1, 1, 11, '2026-04-13T00:00:00Z')",
            [],
        )
        .expect("insert project");
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .expect("insert project dataset");
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 11, 'utig1', 1, 10000)",
            [],
        )
        .expect("insert source seq");
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
        .expect("insert ref hit");

        let result = list_reference_track_members(
            workspace_root.to_string_lossy().into_owned(),
            7,
            "Chr01".to_string(),
        )
        .expect("list reference track members");

        assert_eq!(result["items"].as_array().map(|items| items.len()), Some(2));
        assert_eq!(
            result["items"][0]["sourceKind"].as_str(),
            Some("ref_segment")
        );
        assert_eq!(
            result["items"][0]["name"].as_str(),
            Some("ref_Chr01:1-5000")
        );
        assert_eq!(result["items"][1]["segmentStartBp"].as_i64(), Some(5101));
        assert_eq!(result["items"][1]["hits"][0]["ctgStart"].as_i64(), Some(1));
        assert_eq!(result["items"][1]["hits"][0]["ctgEnd"].as_i64(), Some(5000));

        drop(conn);
        fs::remove_dir_all(workspace_root).expect("remove temp workspace root");
    }

    #[test]
    fn normalize_final_path_export_segments_accepts_ref_segments() {
        let segments = normalize_final_path_export_segments(&json!({
            "segments": [
                {
                    "segmentId": "seg-1",
                    "type": "ctg",
                    "sourceKind": "ref_segment",
                    "referenceChrName": "Chr01",
                    "memberStartBp": 5101,
                    "memberEndBp": 10100,
                    "start": 101,
                    "end": 500
                }
            ]
        }))
        .expect("normalize ref final-path segment");

        assert_eq!(
            segments,
            vec![FinalPathExportSegment::RefSegment {
                reference_chr_name: "Chr01".to_string(),
                member_start_bp: 5101,
                member_end_bp: 10100,
                start: 101,
                end: 500,
            }]
        );
    }

    #[test]
    fn normalize_project_final_path_fasta_records_accepts_multiple_chr_entries() {
        let records = normalize_project_final_path_fasta_records(&json!({
            "Chr01": {
                "chrName": "Chr01",
                "segments": [
                    {
                        "segmentId": "seg-1",
                        "type": "ctg",
                        "sourceKind": "assembly_ctg",
                        "assemblyCtgId": 301,
                        "start": 1,
                        "end": 100
                    }
                ]
            },
            "Chr02": {
                "segments": [
                    {
                        "segmentId": "seg-2",
                        "type": "gap",
                        "gapSizeBp": 50
                    }
                ]
            }
        }))
        .expect("normalize project final-path fasta records");

        assert_eq!(records.len(), 2);
        assert_eq!(records[0].chr_name, "Chr01");
        assert_eq!(records[1].chr_name, "Chr02");
        assert_eq!(
            records[0].final_path_segments,
            vec![FinalPathExportSegment::Ctg {
                assembly_ctg_id: 301,
                start: 1,
                end: 100,
            }]
        );
        assert_eq!(
            records[1].final_path_segments,
            vec![FinalPathExportSegment::Gap { gap_size_bp: 50 }]
        );
    }

    #[test]
    fn command_errors_preserve_stable_codes_and_structured_envelope() {
        let prefixed = CommandError::backend(anyhow!(
            "validation failed: GRT_IMPORT_INVALID_JSON: malformed recipe"
        ));
        let not_found = CommandError::backend(anyhow!("project_id 42 does not exist"));
        let invalid = CommandError::backend(anyhow!("projectId must be a positive integer"));
        let conflict = CommandError::backend(anyhow!("project name already exists"));
        let runtime = CommandError::runtime("join task failed");

        assert_eq!(prefixed.code, "GRT_IMPORT_INVALID_JSON");
        assert_eq!(not_found.code, "NOT_FOUND");
        assert_eq!(invalid.code, "INVALID_REQUEST");
        assert_eq!(conflict.code, "STATE_CONFLICT");
        assert_eq!(runtime.code, "RUNTIME_ERROR");
        assert_eq!(
            serde_json::to_value(&not_found).expect("serialize command error"),
            json!({
                "code": "NOT_FOUND",
                "message": "project_id 42 does not exist",
                "operation": "",
                "data": null
            })
        );
    }
}
