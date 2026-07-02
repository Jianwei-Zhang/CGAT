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
    ProjectInitializationRequest, ProjectUpdateRequest,
    bootstrap_project_assembly_cancel as backend_bootstrap_project_assembly_cancel,
    delete_project as backend_delete_project, initialize_project as backend_initialize_project,
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
use serde_json::{Value, json};
use tauri::{AppHandle, Emitter};

use crate::auto_pipeline_cancel;
use crate::import_cancel;

fn project_db_path(workspace_root: &str) -> PathBuf {
    Path::new(workspace_root).join("project.sqlite")
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

fn format_error(error: anyhow::Error) -> String {
    format!("{error:#}")
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
        json!({
            "runId": run_id,
            "stage": step.stage,
            "detail": step.detail,
            "label": format!("{}：{}", step.stage, step.detail),
            "text": format_import_stage(&step),
            "progressIndex": step.progress_index,
            "progressTotal": step.progress_total
        }),
    );
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

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_zip(
    app: AppHandle,
    zipPath: String,
    workspaceRoot: String,
    runId: Option<String>,
) -> Result<Value, String> {
    let zip_path = zipPath;
    let workspace_root = workspaceRoot;
    let run_id = normalize_optional_run_id(runId);
    if let Some(run_id) = run_id.as_deref() {
        let _ = import_cancel::clear_cancel(run_id);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let progress_run_id = run_id.clone();
        let app_for_progress = app.clone();
        let cancel_run_id = run_id.clone();
        let mut on_progress = move |step: ImportProgress| {
            emit_import_progress(&app_for_progress, progress_run_id.as_deref(), step);
        };
        let mut should_cancel = move || {
            cancel_run_id
                .as_deref()
                .is_some_and(import_cancel::is_cancelled)
        };
        let result = import_from_zip_with_hooks(
            Path::new(&zip_path),
            Path::new(&workspace_root),
            &mut on_progress,
            &mut should_cancel,
        );
        if let Some(run_id) = run_id.as_deref() {
            let _ = import_cancel::clear_cancel(run_id);
        }
        let (outcome, progress) = result?;
        let stages = progress
            .into_iter()
            .map(|step| format_import_stage(&step))
            .collect::<Vec<_>>();
        Ok(json!({
            "workspaceRoot": path_to_string(&outcome.workspace_root),
            "bundleRoot": path_to_string(&outcome.bundle_root),
            "projectDbPath": path_to_string(&outcome.project_db_path),
            "stages": stages,
            "message": "导入完成（Tauri invoke）。"
        }))
    })
    .await
    .map_err(|join_error| format!("import_zip join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_extracted(
    app: AppHandle,
    extractedPath: String,
    runId: Option<String>,
) -> Result<Value, String> {
    let extracted_path = extractedPath;
    let run_id = normalize_optional_run_id(runId);
    if let Some(run_id) = run_id.as_deref() {
        let _ = import_cancel::clear_cancel(run_id);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let progress_run_id = run_id.clone();
        let app_for_progress = app.clone();
        let cancel_run_id = run_id.clone();
        let mut on_progress = move |step: ImportProgress| {
            emit_import_progress(&app_for_progress, progress_run_id.as_deref(), step);
        };
        let mut should_cancel = move || {
            cancel_run_id
                .as_deref()
                .is_some_and(import_cancel::is_cancelled)
        };
        let result = import_from_extracted_bundle_with_hooks(
            Path::new(&extracted_path),
            &mut on_progress,
            &mut should_cancel,
        );
        if let Some(run_id) = run_id.as_deref() {
            let _ = import_cancel::clear_cancel(run_id);
        }
        let (outcome, progress) = result?;
        let stages = progress
            .into_iter()
            .map(|step| format_import_stage(&step))
            .collect::<Vec<_>>();
        Ok(json!({
            "workspaceRoot": path_to_string(&outcome.workspace_root),
            "bundleRoot": path_to_string(&outcome.bundle_root),
            "projectDbPath": path_to_string(&outcome.project_db_path),
            "stages": stages,
            "message": "已导入解压目录（Tauri invoke）。"
        }))
    })
    .await
    .map_err(|join_error| format!("import_extracted join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_add_dataset_package(
    app: AppHandle,
    workspaceRoot: String,
    zipPath: String,
    runId: Option<String>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    let zip_path = zipPath;
    let run_id = normalize_optional_run_id(runId);
    if let Some(run_id) = run_id.as_deref() {
        let _ = import_cancel::clear_cancel(run_id);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let progress_run_id = run_id.clone();
        let app_for_progress = app.clone();
        let cancel_run_id = run_id.clone();
        let mut on_progress = move |step: ImportProgress| {
            emit_import_progress(&app_for_progress, progress_run_id.as_deref(), step);
        };
        let mut should_cancel = move || {
            cancel_run_id
                .as_deref()
                .is_some_and(import_cancel::is_cancelled)
        };
        let result = import_workspace_add_dataset_package_with_hooks(
            Path::new(&zip_path),
            Path::new(&workspace_root),
            &mut on_progress,
            &mut should_cancel,
        );
        if let Some(run_id) = run_id.as_deref() {
            let _ = import_cancel::clear_cancel(run_id);
        }
        let (outcome, progress) = result?;
        let stages = progress
            .into_iter()
            .map(|step| format_import_stage(&step))
            .collect::<Vec<_>>();
        let mut response = read_initializer_options(&workspace_root, true)?;
        if let Some(object) = response.as_object_mut() {
            object.insert("datasetId".to_string(), json!(outcome.dataset_id));
            object.insert("datasetName".to_string(), json!(outcome.dataset_name));
            object.insert("projectId".to_string(), json!(outcome.project_id));
            object.insert(
                "bundleRoot".to_string(),
                json!(path_to_string(&outcome.bundle_root)),
            );
            object.insert(
                "projectDbPath".to_string(),
                json!(path_to_string(&outcome.project_db_path)),
            );
            object.insert("stages".to_string(), json!(stages));
            object.insert(
                "message".to_string(),
                json!("数据集追加包导入完成（Tauri invoke）。"),
            );
        }
        Ok(response)
    })
    .await
    .map_err(|join_error| format!("import_add_dataset_package join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_add_ctg_package(
    app: AppHandle,
    workspaceRoot: String,
    projectId: i64,
    zipPath: String,
    expectedTargetChr: Option<String>,
    expectedTargetTrack: Option<String>,
    runId: Option<String>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    let zip_path = zipPath;
    let expected_target = AddCtgImportTarget {
        target_chr: expectedTargetChr.unwrap_or_default(),
        target_track: expectedTargetTrack.unwrap_or_default(),
    };
    let run_id = normalize_optional_run_id(runId);
    if let Some(run_id) = run_id.as_deref() {
        let _ = import_cancel::clear_cancel(run_id);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let progress_run_id = run_id.clone();
        let app_for_progress = app.clone();
        let cancel_run_id = run_id.clone();
        let mut on_progress = move |step: ImportProgress| {
            emit_import_progress(&app_for_progress, progress_run_id.as_deref(), step);
        };
        let mut should_cancel = move || {
            cancel_run_id
                .as_deref()
                .is_some_and(import_cancel::is_cancelled)
        };
        let result = import_add_ctg_package_with_hooks(
            Path::new(&zip_path),
            Path::new(&workspace_root),
            projectId,
            Some(expected_target),
            &mut on_progress,
            &mut should_cancel,
        );
        if let Some(run_id) = run_id.as_deref() {
            let _ = import_cancel::clear_cancel(run_id);
        }
        let (outcome, progress) = result?;
        let stages = progress
            .into_iter()
            .map(|step| format_import_stage(&step))
            .collect::<Vec<_>>();
        let mut response = read_initializer_options(&workspace_root, true)?;
        if let Some(object) = response.as_object_mut() {
            object.insert("datasetId".to_string(), json!(outcome.dataset_id));
            object.insert("sourceSeqId".to_string(), json!(outcome.source_seq_id));
            object.insert("assemblyCtgId".to_string(), json!(outcome.assembly_ctg_id));
            object.insert("ctgName".to_string(), json!(outcome.ctg_name));
            object.insert("targetTrack".to_string(), json!(outcome.target_track));
            object.insert("targetChr".to_string(), json!(outcome.target_chr));
            object.insert("projectId".to_string(), json!(outcome.project_id));
            object.insert(
                "bundleRoot".to_string(),
                json!(path_to_string(&outcome.bundle_root)),
            );
            object.insert(
                "projectDbPath".to_string(),
                json!(path_to_string(&outcome.project_db_path)),
            );
            object.insert("stages".to_string(), json!(stages));
            object.insert(
                "message".to_string(),
                json!("ctg追加包导入完成（Tauri invoke）。"),
            );
        }
        Ok(response)
    })
    .await
    .map_err(|join_error| format!("import_add_ctg_package join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn request_import_cancel(runId: String) -> Result<Value, String> {
    let registered = import_cancel::request_cancel(&runId);
    Ok(json!({
        "runId": runId,
        "cancelRequested": registered
    }))
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_project_initializer_options(workspaceRoot: String) -> Result<Value, String> {
    (|| read_initializer_options(&workspaceRoot, false))().map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn open_workspace(workspaceRoot: String) -> Result<Value, String> {
    (|| read_initializer_options(&workspaceRoot, true))().map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn validate_workspace_integrity(workspaceRoot: String) -> Result<Value, String> {
    (|| {
        let workspace_root = Path::new(&workspaceRoot);
        if !workspace_root.exists() {
            bail!(
                "workspace root does not exist: {}",
                workspace_root.display()
            );
        }
        if !workspace_root.is_dir() {
            bail!(
                "workspace root is not a directory: {}",
                workspace_root.display()
            );
        }

        let project_db = workspace_root.join("project.sqlite");
        let metadata_reference = workspace_root.join("metadata/reference.tsv");
        let metadata_datasets = workspace_root.join("metadata/datasets.tsv");
        let data_reference_dir = workspace_root.join("data/reference");
        let data_datasets_dir = workspace_root.join("data/datasets");
        let runs_dir = workspace_root.join("runs");
        let run_all = workspace_root.join("run_all.sh");

        let mut missing = Vec::new();
        if !project_db.exists() || !project_db.is_file() {
            missing.push("project.sqlite".to_string());
        }
        if !metadata_reference.exists() || !metadata_reference.is_file() {
            missing.push("metadata/reference.tsv".to_string());
        }
        if !metadata_datasets.exists() || !metadata_datasets.is_file() {
            missing.push("metadata/datasets.tsv".to_string());
        }
        if !data_reference_dir.exists() || !data_reference_dir.is_dir() {
            missing.push("data/reference".to_string());
        } else if !directory_has_entries(&data_reference_dir)? {
            missing.push("data/reference/*".to_string());
        }
        if !data_datasets_dir.exists() || !data_datasets_dir.is_dir() {
            missing.push("data/datasets".to_string());
        } else if !directory_has_entries(&data_datasets_dir)? {
            missing.push("data/datasets/*".to_string());
        }
        if !runs_dir.exists() || !runs_dir.is_dir() {
            missing.push("runs".to_string());
        }
        if !run_all.exists() || !run_all.is_file() {
            missing.push("run_all.sh".to_string());
        }

        let result_paf_count = count_named_files_recursive(&runs_dir, "result.paf")?;
        if result_paf_count == 0 {
            missing.push("runs/*/result.paf".to_string());
        }

        Ok(json!({
            "workspaceRoot": workspaceRoot,
            "ok": missing.is_empty(),
            "missing": missing,
            "resultPafCount": result_paf_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn delete_workspace_directory(workspaceRoot: String) -> Result<Value, String> {
    (|| {
        let workspace_root = Path::new(&workspaceRoot);
        if !workspace_root.exists() {
            return Ok(json!({
                "workspaceRoot": workspaceRoot,
                "deleted": false,
                "reason": "not_found"
            }));
        }
        if !workspace_root.is_dir() {
            bail!(
                "workspace root is not a directory: {}",
                workspace_root.display()
            );
        }
        if !looks_like_deletable_workspace_root(workspace_root) {
            bail!(
                "refuse to delete non-workspace directory (not recognized as workspace/bundle root): {}",
                workspace_root.display()
            );
        }
        fs::remove_dir_all(workspace_root).with_context(|| {
            format!(
                "failed to delete workspace directory {}",
                workspace_root.display()
            )
        })?;
        Ok(json!({
            "workspaceRoot": workspaceRoot,
            "deleted": true
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn initialize_project(
    workspaceRoot: String,
    projectName: String,
    referenceGenomeId: i64,
    primaryDatasetId: i64,
    supportDatasetIds: Option<Vec<i64>>,
    chrAssignmentMinCoveragePercent: Option<f64>,
    phasedAssemblyEnabled: Option<bool>,
) -> Result<Value, String> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let summary = backend_initialize_project(
            &project_db,
            &ProjectInitializationRequest {
                project_name: projectName.clone(),
                reference_genome_id: referenceGenomeId,
                primary_dataset_id: primaryDatasetId,
                support_dataset_ids: supportDatasetIds.unwrap_or_default(),
                auto_check_new_seq: false,
                phased_assembly_enabled: phasedAssemblyEnabled,
                chr_assignment_min_coverage_percent: chrAssignmentMinCoveragePercent,
                description: None,
            },
        )?;
        let options = backend_list_initializer_options(&project_db)?;
        let existing_projects = map_existing_projects(options.existing_projects);
        Ok(json!({
            "projectId": summary.project_id,
            "projectName": summary.project_name,
            "version": summary.version,
            "referenceGenomeId": summary.reference_genome_id,
            "primaryDatasetId": summary.primary_dataset_id,
            "projectDatasetCount": summary.project_dataset_count,
            "phasedAssemblyEnabled": summary.phased_assembly_enabled,
            "chrAssignmentMinCoveragePercent": summary.chr_assignment_min_coverage_percent,
            "existingProjects": existing_projects
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn update_project(
    workspaceRoot: String,
    projectId: i64,
    projectName: String,
    referenceGenomeId: i64,
    primaryDatasetId: i64,
    supportDatasetIds: Option<Vec<i64>>,
    chrAssignmentMinCoveragePercent: Option<f64>,
    phasedAssemblyEnabled: Option<bool>,
) -> Result<Value, String> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let summary = backend_update_project(
            &project_db,
            &ProjectUpdateRequest {
                project_id: projectId,
                project_name: projectName.clone(),
                reference_genome_id: referenceGenomeId,
                primary_dataset_id: primaryDatasetId,
                support_dataset_ids: supportDatasetIds.unwrap_or_default(),
                phased_assembly_enabled: phasedAssemblyEnabled,
                chr_assignment_min_coverage_percent: chrAssignmentMinCoveragePercent,
            },
        )?;
        let options = backend_list_initializer_options(&project_db)?;
        let existing_projects = map_existing_projects(options.existing_projects);
        Ok(json!({
            "projectId": summary.project_id,
            "projectName": summary.project_name,
            "referenceGenomeId": summary.reference_genome_id,
            "primaryDatasetId": summary.primary_dataset_id,
            "projectDatasetCount": summary.project_dataset_count,
            "phasedAssemblyEnabled": summary.phased_assembly_enabled,
            "chrAssignmentMinCoveragePercent": summary.chr_assignment_min_coverage_percent,
            "isProcessed": summary.is_processed,
            "existingProjects": existing_projects
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn delete_project(workspaceRoot: String, projectId: i64) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        (|| {
            let project_db = project_db_path(&workspaceRoot);
            backend_delete_project(&project_db, projectId)?;
            Ok(json!({
                "projectId": projectId,
                "deleted": true
            }))
        })()
        .map_err(format_error)
    })
    .await
    .map_err(|error| format!("failed to join delete_project task: {error}"))?
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn bootstrap_project_assembly(
    workspaceRoot: String,
    projectId: i64,
    runId: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        (|| {
            let run_id = runId.as_deref();
            let project_db = project_db_path(&workspaceRoot);
            let mut should_cancel =
                || is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id);
            let summary = backend_bootstrap_project_assembly_cancel(
                &project_db,
                projectId,
                &mut should_cancel,
            );
            if summary
                .as_ref()
                .err()
                .is_some_and(|_| is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id))
            {
                clear_auto_pipeline_cancel(&workspaceRoot, projectId, run_id);
            }
            let summary = summary?;
            Ok(json!({
                "projectId": summary.project_id,
                "assemblySeqCount": summary.assembly_seq_count,
                "assemblyCtgCount": summary.assembly_ctg_count,
                "assemblyMemberCount": summary.assembly_member_count
            }))
        })()
        .map_err(format_error)
    })
    .await
    .map_err(|error| format!("failed to join bootstrap_project_assembly task: {error}"))?
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn auto_assign_chr(
    workspaceRoot: String,
    projectId: i64,
    runId: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        (|| {
            let run_id = runId.as_deref();
            let project_db = project_db_path(&workspaceRoot);
            let mut should_cancel =
                || is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id);
            let summary = backend_auto_assign_chr_cancel(
                &project_db,
                projectId,
                &AutoAssignChrParams {
                    alignment_block_size: 1000,
                    alignment_coverage_percent: 25.0,
                    assign_unplaced: true,
                    reposition_anchored: false,
                    skip_manual: true,
                },
                &mut should_cancel,
            );
            if summary
                .as_ref()
                .err()
                .is_some_and(|_| is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id))
            {
                clear_auto_pipeline_cancel(&workspaceRoot, projectId, run_id);
            }
            let summary = summary?;
            Ok(json!({
                "projectId": summary.project_id,
                "processedCtgCount": summary.processed_ctg_count,
                "assignedCount": summary.assigned_count,
                "repositionedCount": summary.repositioned_count,
                "clearedCount": summary.cleared_count,
                "skippedManualCount": summary.skipped_manual_count,
                "noEvidenceCount": summary.no_evidence_count,
                "refreshedChrCount": summary.refreshed_chr_count
            }))
        })()
        .map_err(format_error)
    })
    .await
    .map_err(|error| format!("failed to join auto_assign_chr task: {error}"))?
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn auto_orient_contigs(
    workspaceRoot: String,
    projectId: i64,
    runId: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        (|| {
            let run_id = runId.as_deref();
            let mut should_cancel =
                || is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id);
            let summary = backend_auto_orient_contigs_cancel(
                &project_db_path(&workspaceRoot),
                projectId,
                &AutoOrientContigsParams {
                    alignment_block_size: 1000,
                    alignment_coverage_percent: 25.0,
                    skip_manual: true,
                },
                &mut should_cancel,
            );
            if summary
                .as_ref()
                .err()
                .is_some_and(|_| is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id))
            {
                clear_auto_pipeline_cancel(&workspaceRoot, projectId, run_id);
            }
            let summary = summary?;
            Ok(json!({
                "projectId": summary.project_id,
                "processedCtgCount": summary.processed_ctg_count,
                "orientedCtgCount": summary.oriented_ctg_count,
                "flippedCtgCount": summary.flipped_ctg_count,
                "noEvidenceCount": summary.no_evidence_count,
                "skippedManualCount": summary.skipped_manual_count
            }))
        })()
        .map_err(format_error)
    })
    .await
    .map_err(|error| format!("failed to join auto_orient_contigs task: {error}"))?
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn auto_orient_contigs_for_dataset(
    workspaceRoot: String,
    projectId: i64,
    datasetId: i64,
    runId: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        (|| {
            let run_id = runId.as_deref();
            let mut should_cancel =
                || is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id);
            let summary = backend_auto_orient_contigs_for_dataset_cancel(
                &project_db_path(&workspaceRoot),
                projectId,
                datasetId,
                &AutoOrientContigsParams {
                    alignment_block_size: 1000,
                    alignment_coverage_percent: 25.0,
                    skip_manual: true,
                },
                &mut should_cancel,
            );
            if summary
                .as_ref()
                .err()
                .is_some_and(|_| is_auto_pipeline_cancelled(&workspaceRoot, projectId, run_id))
            {
                clear_auto_pipeline_cancel(&workspaceRoot, projectId, run_id);
            }
            let summary = summary?;
            Ok(json!({
                "projectId": summary.project_id,
                "datasetId": datasetId,
                "processedCtgCount": summary.processed_ctg_count,
                "orientedCtgCount": summary.oriented_ctg_count,
                "flippedCtgCount": summary.flipped_ctg_count,
                "noEvidenceCount": summary.no_evidence_count,
                "skippedManualCount": summary.skipped_manual_count
            }))
        })()
        .map_err(format_error)
    })
    .await
    .map_err(|error| format!("failed to join auto_orient_contigs_for_dataset task: {error}"))?
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn request_auto_pipeline_cancel(
    workspaceRoot: String,
    projectId: i64,
    runId: String,
) -> Result<Value, String> {
    (|| {
        let requested = auto_pipeline_cancel::request_cancel(&workspaceRoot, projectId, &runId);
        Ok(json!({
            "workspaceRoot": workspaceRoot,
            "projectId": projectId,
            "runId": runId,
            "requested": requested
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn set_project_auto_pipeline_done(
    workspaceRoot: String,
    projectId: i64,
    done: Option<bool>,
) -> Result<Value, String> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let done = done.unwrap_or(true);
        backend_set_project_auto_pipeline_done(&project_db, projectId, done)?;
        let options = backend_list_initializer_options(&project_db)?;
        let existing_projects = map_existing_projects(options.existing_projects);
        Ok(json!({
            "projectId": projectId,
            "autoPipelineDone": done,
            "existingProjects": existing_projects
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_project_chromosomes(workspaceRoot: String, projectId: i64) -> Result<Value, String> {
    (|| {
        let chromosomes =
            backend_list_project_chromosomes(&project_db_path(&workspaceRoot), projectId)?;
        let items = chromosomes
            .items
            .into_iter()
            .map(|item| {
                json!({
                    "chrName": item.chr_name,
                    "chrOrder": item.chr_order,
                    "chrLength": item.chr_length,
                    "ctgCount": item.ctg_count,
                    "placedBp": item.placed_bp
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": chromosomes.project_id,
            "referenceGenomeId": chromosomes.reference_genome_id,
            "unplacedCtgCount": chromosomes.unplaced_ctg_count,
            "unplacedBp": chromosomes.unplaced_bp,
            "items": items
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_new_sequences(
    workspaceRoot: String,
    projectId: i64,
    limit: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = apply_item_limit(
            backend_list_project_new_sequences(&project_db_path(&workspaceRoot), projectId)?,
            limit,
        );
        let mapped = items
            .into_iter()
            .map(|item| {
                json!({
                    "assemblySeqId": item.assembly_seq_id,
                    "datasetName": item.dataset_name,
                    "seqName": item.seq_name,
                    "seqLength": item.seq_length,
                    "hidden": item.hidden
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_chr_view_ctgs(
    workspaceRoot: String,
    projectId: i64,
    chrName: Option<String>,
    datasetId: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_chr_view_ctgs(
            &project_db_path(&workspaceRoot),
            projectId,
            chrName.as_deref(),
            datasetId,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                let hits = item
                    .hits
                    .into_iter()
                    .map(|hit| {
                        json!({
                            "hitId": hit.hit_id,
                            "assemblyCtgMemberId": hit.assembly_ctg_member_id,
                            "assemblySeqId": hit.assembly_seq_id,
                            "sourceSeqId": hit.source_seq_id,
                            "strand": hit.strand,
                            "queryStart": hit.query_start,
                            "queryEnd": hit.query_end,
                            "refStart": hit.ref_start,
                            "refEnd": hit.ref_end,
                            "matchLength": hit.match_length,
                            "blockLength": hit.block_length,
                            "mapq": hit.mapq,
                            "ctgStart": hit.ctg_start,
                            "ctgEnd": hit.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let n_regions = item
                    .n_regions
                    .into_iter()
                    .map(|region| {
                        json!({
                            "startBp": region.start_bp,
                            "endBp": region.end_bp,
                            "lengthBp": region.length_bp,
                            "ctgStart": region.ctg_start,
                            "ctgEnd": region.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let telomere_marks = item
                    .telomere_marks
                    .into_iter()
                    .map(|mark| {
                        json!({
                            "ruleId": mark.rule_id,
                            "motif": mark.motif,
                            "minRepeat": mark.min_repeat,
                            "repeatCount": mark.repeat_count,
                            "startBp": mark.start_bp,
                            "endBp": mark.end_bp,
                            "strand": mark.strand,
                            "ctgStart": mark.ctg_start,
                            "ctgEnd": mark.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let centromere_marks = item
                    .centromere_marks
                    .into_iter()
                    .map(|mark| {
                        json!({
                            "cenId": mark.cen_id,
                            "queryName": mark.query_name,
                            "startBp": mark.start_bp,
                            "endBp": mark.end_bp,
                            "strand": mark.strand,
                            "alignLength": mark.align_length,
                            "identity": mark.identity,
                            "mapq": mark.mapq,
                            "ctgStart": mark.ctg_start,
                            "ctgEnd": mark.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                json!({
                    "assemblyCtgId": item.assembly_ctg_id,
                    "name": item.name,
                    "originId": item.origin_id,
                    "coAssignedChrNames": item.co_assigned_chr_names,
                    "assignedChrName": item.assigned_chr_name,
                    "chrOrder": item.chr_order,
                    "anchorStart": item.anchor_start,
                    "refOrient": item.ref_orient,
                    "orient": item.orient,
                    "placementMode": item.placement_mode,
                    "memberCount": item.member_count,
                    "totalLength": item.total_length,
                    "datasetId": item.dataset_id,
                    "datasetName": item.dataset_name,
                    "derivedSource": item.derived_source,
                    "derivedTargetDatasetId": item.derived_target_dataset_id,
                    "derivedTargetDatasetName": item.derived_target_dataset_name,
                    "hits": hits,
                    "nRegions": n_regions,
                    "telomereMarks": telomere_marks,
                    "centromereMarks": centromere_marks
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_deleted_ctgs(
    workspaceRoot: String,
    projectId: i64,
    chrName: Option<String>,
    datasetId: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_deleted_ctgs(
            &project_db_path(&workspaceRoot),
            projectId,
            chrName.as_deref(),
            datasetId,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                json!({
                    "deletedCtgRecordId": item.deleted_ctg_record_id,
                    "projectId": item.project_id,
                    "assemblyCtgId": item.assembly_ctg_id,
                    "name": item.name,
                    "assignedChrName": item.assigned_chr_name,
                    "chrOrder": item.chr_order,
                    "anchorStart": item.anchor_start,
                    "refOrient": item.ref_orient,
                    "placementMode": item.placement_mode,
                    "memberCount": item.member_count,
                    "totalLength": item.total_length,
                    "deletedAt": item.deleted_at
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_reference_track_members(
    workspaceRoot: String,
    projectId: i64,
    chrName: String,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_reference_track_members(
            &project_db_path(&workspaceRoot),
            projectId,
            &chrName,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                let hits = item
                    .hits
                    .into_iter()
                    .map(|hit| {
                        json!({
                            "hitId": hit.hit_id,
                            "datasetId": hit.dataset_id,
                            "sourceSeqId": hit.source_seq_id,
                            "strand": hit.strand,
                            "queryStart": hit.query_start,
                            "queryEnd": hit.query_end,
                            "refStart": hit.ref_start,
                            "refEnd": hit.ref_end,
                            "matchLength": hit.match_length,
                            "blockLength": hit.block_length,
                            "mapq": hit.mapq,
                            "ctgStart": hit.ctg_start,
                            "ctgEnd": hit.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                json!({
                    "sourceKind": item.source_kind,
                    "referenceChrId": item.reference_chr_id,
                    "referenceChrName": item.reference_chr_name,
                    "segmentOrder": item.segment_order,
                    "segmentStartBp": item.segment_start_bp,
                    "segmentEndBp": item.segment_end_bp,
                    "name": item.name,
                    "anchorStart": item.anchor_start,
                    "totalLength": item.total_length,
                    "refOrient": item.ref_orient,
                    "hits": hits
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_phased_chr_tracks(
    workspaceRoot: String,
    projectId: i64,
    parentChrName: String,
) -> Result<Value, String> {
    (|| {
        let result = backend_list_phased_chr_tracks(
            &project_db_path(&workspaceRoot),
            projectId,
            &parentChrName,
        )?;
        let tracks = result
            .tracks
            .into_iter()
            .map(map_phased_track)
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": result.project_id,
            "parentChrName": result.parent_chr_name,
            "tracks": tracks
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn create_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    parentChrName: String,
) -> Result<Value, String> {
    (|| {
        let summary = backend_create_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            &parentChrName,
        )?;
        Ok(json!({ "track": map_phased_track(summary.track) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn delete_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_delete_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "parentChrName": summary.parent_chr_name,
            "haplotypeKey": summary.haplotype_key,
            "label": summary.label,
            "deleted": summary.deleted
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn add_ctg_to_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_add_ctg_to_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
            assemblyCtgId,
        )?;
        Ok(json!({ "item": map_phased_track_item(summary.item) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn remove_phased_chr_track_item(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackItemId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_remove_phased_chr_track_item(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackItemId,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "phasedTrackItemId": summary.phased_track_item_id,
            "removed": summary.removed
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn reorder_phased_chr_track_items(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
    itemIds: Vec<i64>,
) -> Result<Value, String> {
    (|| {
        let summary = backend_reorder_phased_chr_track_items(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
            &itemIds,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "itemCount": summary.item_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn get_ctg_detail(
    workspaceRoot: String,
    projectId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let detail =
            backend_get_ctg_detail(&project_db_path(&workspaceRoot), projectId, assemblyCtgId)?;
        let members = detail
            .members
            .into_iter()
            .map(|member| {
                json!({
                    "assemblyCtgMemberId": member.assembly_ctg_member_id,
                    "memberOrder": member.member_order,
                    "assemblySeqId": member.assembly_seq_id,
                    "datasetName": member.dataset_name,
                    "seqName": member.seq_name,
                    "seqLength": member.seq_length,
                    "orient": member.orient,
                    "sourceStart": member.source_start,
                    "sourceEnd": member.source_end,
                    "leftEndType": member.left_end_type,
                    "rightEndType": member.right_end_type,
                    "hidden": member.hidden
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "assemblyCtgId": detail.assembly_ctg_id,
            "projectId": detail.project_id,
            "name": detail.name,
            "assignedChrName": detail.assigned_chr_name,
            "chrOrder": detail.chr_order,
            "anchorStart": detail.anchor_start,
            "refOrient": detail.ref_orient,
            "placementMode": detail.placement_mode,
            "members": members
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_ctg_edit_candidates(
    workspaceRoot: String,
    projectId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let candidates = backend_list_ctg_edit_candidates(
            &project_db_path(&workspaceRoot),
            projectId,
            assemblyCtgId,
        )?;
        let move_targets = candidates
            .move_target_ctgs
            .into_iter()
            .map(|ctg| {
                json!({
                    "assemblyCtgId": ctg.assembly_ctg_id,
                    "name": ctg.name,
                    "assignedChrName": ctg.assigned_chr_name,
                    "chrOrder": ctg.chr_order
                })
            })
            .collect::<Vec<_>>();
        let add_seq_candidates = candidates
            .add_seq_candidates
            .into_iter()
            .map(|seq| {
                json!({
                    "assemblySeqId": seq.assembly_seq_id,
                    "datasetName": seq.dataset_name,
                    "seqName": seq.seq_name,
                    "seqLength": seq.seq_length,
                    "hidden": seq.hidden
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": candidates.project_id,
            "assemblyCtgId": candidates.assembly_ctg_id,
            "moveTargetCtgs": move_targets,
            "addSeqCandidates": add_seq_candidates
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn restore_deleted_ctg(
    workspaceRoot: String,
    projectId: i64,
    deletedCtgRecordId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_restore_deleted_ctg(
            &project_db_path(&workspaceRoot),
            projectId,
            &RestoreDeletedCtgParams {
                deleted_ctg_record_id: deletedCtgRecordId,
            },
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "deletedCtgRecordId": summary.deleted_ctg_record_id,
            "assemblyCtgId": summary.assembly_ctg_id,
            "restoredMemberCount": summary.restored_member_count,
            "refreshedChrCount": summary.refreshed_chr_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn run_ctg_editor_action(
    workspaceRoot: String,
    projectId: i64,
    action: String,
    args: Value,
) -> Result<Value, String> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let normalized = action.trim().to_ascii_lowercase();
        let changed = match normalized.as_str() {
            "rename-ctg" => {
                rename_ctg(
                    &project_db,
                    projectId,
                    &RenameCtgParams {
                        assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                        new_name: get_required_string(&args, "newName")?,
                    },
                )?
                .changed
            }
            "flip-ctg" => {
                let phased_track_item_id = match args.get("phasedTrackItemId") {
                    Some(value) if !value.is_null() => {
                        let parsed = value_to_i64(value, "phasedTrackItemId")?;
                        (parsed > 0).then_some(parsed)
                    }
                    _ => None,
                };
                if let Some(phased_track_item_id) = phased_track_item_id {
                    backend_flip_phased_chr_track_item(
                        &project_db,
                        projectId,
                        phased_track_item_id,
                    )?;
                } else {
                    flip_ctg(
                        &project_db,
                        projectId,
                        &FlipCtgParams {
                            assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                        },
                    )?;
                }
                true
            }
            "delete-ctg" => {
                delete_ctg(
                    &project_db,
                    projectId,
                    &DeleteCtgParams {
                        assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                    },
                )?;
                true
            }
            "restore-deleted-ctg" => {
                backend_restore_deleted_ctg(
                    &project_db,
                    projectId,
                    &RestoreDeletedCtgParams {
                        deleted_ctg_record_id: get_required_i64(&args, "deletedCtgRecordId")?,
                    },
                )?;
                true
            }
            "flip-seq" => {
                flip_seq(
                    &project_db,
                    projectId,
                    &FlipSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?;
                true
            }
            "hide-seq" => {
                hide_seq(
                    &project_db,
                    projectId,
                    &HideSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?
                .changed
            }
            "show-seq" => {
                show_seq(
                    &project_db,
                    projectId,
                    &ShowSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?
                .changed
            }
            "set-end-type" => {
                set_end_type(
                    &project_db,
                    projectId,
                    &SetEndTypeParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                        left_end_type: get_required_string(&args, "leftEndType")?,
                        right_end_type: get_required_string(&args, "rightEndType")?,
                    },
                )?
                .changed
            }
            _ => bail!("unsupported ctg editor action: {}", normalized),
        };
        Ok(json!({
            "action": normalized,
            "changed": changed
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn get_junction_inspection(
    workspaceRoot: String,
    projectId: i64,
    leftAssemblyCtgId: i64,
    rightAssemblyCtgId: i64,
    minAlignmentLength: Option<i64>,
    minMapq: Option<i64>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    tauri::async_runtime::spawn_blocking(move || {
        let params = GetJunctionInspectionParams {
            project_id: projectId,
            left_assembly_ctg_id: leftAssemblyCtgId,
            right_assembly_ctg_id: rightAssemblyCtgId,
            min_align_length: minAlignmentLength,
            min_mapq: minMapq,
        };
        let report = backend_get_junction_inspection(&project_db_path(&workspace_root), &params)?;
        let hits = report
            .hits
            .into_iter()
            .map(|hit| {
                json!({
                    "queryAssemblyCtgId": hit.query_assembly_ctg_id,
                    "querySourceSeqId": hit.query_source_seq_id,
                    "querySourceSeqName": hit.query_source_seq_name,
                    "subjectAssemblyCtgId": hit.subject_assembly_ctg_id,
                    "subjectSourceSeqId": hit.subject_source_seq_id,
                    "subjectSourceSeqName": hit.subject_source_seq_name,
                    "strand": hit.strand,
                    "queryStart": hit.query_start,
                    "queryEnd": hit.query_end,
                    "subjectStart": hit.subject_start,
                    "subjectEnd": hit.subject_end,
                    "mapq": hit.mapq,
                    "identityPct": hit.identity_pct,
                    "alignLength": hit.align_length,
                    "mismatchCount": hit.mismatch_count,
                    "gapOpenCount": hit.gap_open_count,
                    "evalue": hit.evalue,
                    "bitScore": hit.bit_score,
                    "evidenceOrigin": hit.evidence_origin
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": report.project_id,
            "assignedChrName": report.assigned_chr_name,
            "placementRelation": report.placement_relation,
            "overlapBp": report.overlap_bp,
            "gapBp": report.gap_bp,
            "sameDataset": report.same_dataset,
            "evidenceSource": report.evidence_source,
            "evidenceHitCount": report.evidence_hit_count,
            "left": {
                "assemblyCtgId": report.left.assembly_ctg_id,
                "name": report.left.name,
                "assignedChrName": report.left.assigned_chr_name,
                "anchorStart": report.left.anchor_start,
                "anchorEnd": report.left.anchor_end,
                "spanLength": report.left.span_length,
                "placementMode": report.left.placement_mode,
                "memberCount": report.left.member_count,
                "visibleMemberCount": report.left.visible_member_count,
                "datasetIds": report.left.dataset_ids,
                "datasetNames": report.left.dataset_names
            },
            "right": {
                "assemblyCtgId": report.right.assembly_ctg_id,
                "name": report.right.name,
                "assignedChrName": report.right.assigned_chr_name,
                "anchorStart": report.right.anchor_start,
                "anchorEnd": report.right.anchor_end,
                "spanLength": report.right.span_length,
                "placementMode": report.right.placement_mode,
                "memberCount": report.right.member_count,
                "visibleMemberCount": report.right.visible_member_count,
                "datasetIds": report.right.dataset_ids,
                "datasetNames": report.right.dataset_names
            },
            "hits": hits
        }))
    })
    .await
    .map_err(|join_error| format!("get_junction_inspection join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn get_track_pairwise_evidence(
    workspaceRoot: String,
    projectId: i64,
    topAssemblyCtgIds: Vec<i64>,
    bottomAssemblyCtgIds: Vec<i64>,
    minAlignmentLength: Option<i64>,
    minMapq: Option<i64>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    tauri::async_runtime::spawn_blocking(move || {
        let params = GetTrackPairwiseEvidenceParams {
            project_id: projectId,
            top_assembly_ctg_ids: topAssemblyCtgIds,
            bottom_assembly_ctg_ids: bottomAssemblyCtgIds,
            min_align_length: minAlignmentLength,
            min_mapq: minMapq,
        };
        let report =
            backend_get_track_pairwise_evidence(&project_db_path(&workspace_root), &params)?;
        let hits = report
            .hits
            .into_iter()
            .map(|hit| {
                json!({
                    "queryAssemblyCtgId": hit.query_assembly_ctg_id,
                    "querySourceSeqId": hit.query_source_seq_id,
                    "querySourceSeqName": hit.query_source_seq_name,
                    "subjectAssemblyCtgId": hit.subject_assembly_ctg_id,
                    "subjectSourceSeqId": hit.subject_source_seq_id,
                    "subjectSourceSeqName": hit.subject_source_seq_name,
                    "strand": hit.strand,
                    "queryStart": hit.query_start,
                    "queryEnd": hit.query_end,
                    "subjectStart": hit.subject_start,
                    "subjectEnd": hit.subject_end,
                    "mapq": hit.mapq,
                    "identityPct": hit.identity_pct,
                    "alignLength": hit.align_length,
                    "mismatchCount": hit.mismatch_count,
                    "gapOpenCount": hit.gap_open_count,
                    "evalue": hit.evalue,
                    "bitScore": hit.bit_score,
                    "evidenceOrigin": hit.evidence_origin
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": report.project_id,
            "assignedChrName": report.assigned_chr_name,
            "sameDataset": report.same_dataset,
            "evidenceSource": report.evidence_source,
            "evidenceHitCount": report.evidence_hit_count,
            "topAssemblyCtgIds": report.top_assembly_ctg_ids,
            "bottomAssemblyCtgIds": report.bottom_assembly_ctg_ids,
            "hits": hits
        }))
    })
    .await
    .map_err(|join_error| format!("get_track_pairwise_evidence join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_export_records(
    workspaceRoot: String,
    projectId: i64,
    limit: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_export_records(
            &project_db_path(&workspaceRoot),
            projectId,
            &ListExportRecordsParams {
                limit: limit.unwrap_or(50),
            },
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                json!({
                    "id": item.id,
                    "projectId": item.project_id,
                    "exportType": item.export_type,
                    "referenceChrId": item.reference_chr_id,
                    "assemblyCtgId": item.assembly_ctg_id,
                    "outputPath": item.output_path,
                    "createdAt": item.created_at,
                    "note": item.note
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn get_runtime_settings(workspaceRoot: String) -> Result<Value, String> {
    (|| {
        let runtime = backend_get_runtime_settings(&project_db_path(&workspaceRoot))?;
        Ok(json!({
            "updatedAt": runtime.updated_at,
            "degapWorkspaceSettings": serde_json::from_str::<Value>(&runtime.degap_workspace_settings_json)
                .unwrap_or_else(|_| json!({})),
            "source": "workspace_db"
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn update_runtime_settings(
    workspaceRoot: String,
    degapWorkspaceSettings: Option<Value>,
) -> Result<Value, String> {
    (|| {
        let normalized_degap_workspace_settings = degapWorkspaceSettings
            .filter(Value::is_object)
            .unwrap_or_else(|| json!({}));
        let runtime = backend_update_runtime_settings(
            &project_db_path(&workspaceRoot),
            &UpdateRuntimeSettingsParams {
                degap_workspace_settings_json: serde_json::to_string(
                    &normalized_degap_workspace_settings,
                )?,
            },
        )?;
        Ok(json!({
            "updatedAt": runtime.updated_at,
            "degapWorkspaceSettings": serde_json::from_str::<Value>(&runtime.degap_workspace_settings_json)
                .unwrap_or_else(|_| json!({})),
            "source": "workspace_db"
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn get_project_assembly_view_state(
    workspaceRoot: String,
    projectId: i64,
) -> Result<Value, String> {
    (|| {
        let state =
            backend_get_project_assembly_view_state(&project_db_path(&workspaceRoot), projectId)?;
        let support_mirrored_ctgs =
            serde_json::from_str::<Value>(&state.support_mirrored_ctgs_json)
                .unwrap_or_else(|_| json!([]));
        let final_path_by_chr = serde_json::from_str::<Value>(&state.final_path_by_chr_json)
            .unwrap_or_else(|_| json!({}));
        Ok(json!({
            "projectId": state.project_id,
            "supportDatasetId": state.support_dataset_id,
            "trackView": serde_json::from_str::<Value>(&state.track_view_json)
                .unwrap_or_else(|_| json!({})),
            "supportDsCtgLenRulesByChr": serde_json::from_str::<Value>(&state.support_ds_ctg_len_rules_by_chr_json)
                .unwrap_or_else(|_| json!({})),
            "trackScrollState": serde_json::from_str::<Value>(&state.track_scroll_state_json)
                .unwrap_or_else(|_| json!({})),
            "subviewTrackScrollState": serde_json::from_str::<Value>(&state.subview_track_scroll_state_json)
                .unwrap_or_else(|_| json!({})),
            "supportMirroredCtgs": support_mirrored_ctgs,
            "hiddenPrimaryCtgIds": serde_json::from_str::<Value>(&state.hidden_primary_ctg_ids_json)
                .unwrap_or_else(|_| json!([])),
            "hiddenPrimaryCtgIdsByChr": serde_json::from_str::<Value>(&state.hidden_primary_ctg_ids_by_chr_json)
                .unwrap_or_else(|_| json!({})),
            "trackDragOffsets": serde_json::from_str::<Value>(&state.track_drag_offsets_json)
                .unwrap_or_else(|_| json!([])),
            "subviewTrackDragOffsets": serde_json::from_str::<Value>(&state.subview_track_drag_offsets_json)
                .unwrap_or_else(|_| json!([])),
            "subviewAnchorStateByKey": serde_json::from_str::<Value>(&state.subview_anchor_state_by_key_json)
                .unwrap_or_else(|_| json!({})),
            "finalPathViewMode": state.final_path_view_mode,
            "finalPathByChr": final_path_by_chr,
            "degapProjectState": serde_json::from_str::<Value>(&state.degap_project_state_json)
                .unwrap_or_else(|_| json!({})),
            "updatedAt": state.updated_at,
            "source": "workspace_db"
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn update_project_assembly_view_state(
    workspaceRoot: String,
    projectId: i64,
    supportDatasetId: Option<i64>,
    trackView: Value,
    supportDsCtgLenRulesByChr: Value,
    trackScrollState: Value,
    subviewTrackScrollState: Value,
    supportMirroredCtgs: Value,
    hiddenPrimaryCtgIds: Value,
    hiddenPrimaryCtgIdsByChr: Value,
    trackDragOffsets: Value,
    subviewTrackDragOffsets: Value,
    subviewAnchorStateByKey: Value,
    finalPathViewMode: String,
    finalPathByChr: Value,
    degapProjectState: Value,
) -> Result<Value, String> {
    (|| {
        let normalized_support_mirrored_ctgs = if supportMirroredCtgs.is_array() {
            supportMirroredCtgs
        } else {
            json!([])
        };
        let normalized_track_view = if trackView.is_object() {
            trackView
        } else {
            json!({})
        };
        let normalized_support_ds_ctg_len_rules_by_chr = if supportDsCtgLenRulesByChr.is_object() {
            supportDsCtgLenRulesByChr
        } else {
            json!({})
        };
        let normalized_track_scroll_state = if trackScrollState.is_object() {
            trackScrollState
        } else {
            json!({})
        };
        let normalized_subview_track_scroll_state = if subviewTrackScrollState.is_object() {
            subviewTrackScrollState
        } else {
            json!({})
        };
        let normalized_hidden_primary_ctg_ids = if hiddenPrimaryCtgIds.is_array() {
            hiddenPrimaryCtgIds
        } else {
            json!([])
        };
        let normalized_hidden_primary_ctg_ids_by_chr = if hiddenPrimaryCtgIdsByChr.is_object() {
            hiddenPrimaryCtgIdsByChr
        } else {
            json!({})
        };
        let normalized_track_drag_offsets = if trackDragOffsets.is_array() {
            trackDragOffsets
        } else {
            json!([])
        };
        let normalized_subview_track_drag_offsets = if subviewTrackDragOffsets.is_array() {
            subviewTrackDragOffsets
        } else {
            json!([])
        };
        let normalized_subview_anchor_state_by_key = if subviewAnchorStateByKey.is_object() {
            subviewAnchorStateByKey
        } else {
            json!({})
        };
        let normalized_final_path_by_chr = if finalPathByChr.is_object() {
            finalPathByChr
        } else {
            json!({})
        };
        let normalized_degap_project_state = if degapProjectState.is_object() {
            degapProjectState
        } else {
            json!({})
        };
        let normalized_final_path_view_mode = match finalPathViewMode.trim() {
            "log" => "log".to_string(),
            "degap" => "degap".to_string(),
            "table" => "table".to_string(),
            _ => "graph".to_string(),
        };
        let state = backend_update_project_assembly_view_state(
            &project_db_path(&workspaceRoot),
            &UpdateProjectAssemblyViewStateParams {
                project_id: projectId,
                support_dataset_id: supportDatasetId.filter(|value| *value > 0),
                track_view_json: serde_json::to_string(&normalized_track_view)?,
                support_ds_ctg_len_rules_by_chr_json: serde_json::to_string(
                    &normalized_support_ds_ctg_len_rules_by_chr,
                )?,
                track_scroll_state_json: serde_json::to_string(&normalized_track_scroll_state)?,
                subview_track_scroll_state_json: serde_json::to_string(
                    &normalized_subview_track_scroll_state,
                )?,
                support_mirrored_ctgs_json: serde_json::to_string(
                    &normalized_support_mirrored_ctgs,
                )?,
                hidden_primary_ctg_ids_json: serde_json::to_string(
                    &normalized_hidden_primary_ctg_ids,
                )?,
                hidden_primary_ctg_ids_by_chr_json: serde_json::to_string(
                    &normalized_hidden_primary_ctg_ids_by_chr,
                )?,
                track_drag_offsets_json: serde_json::to_string(&normalized_track_drag_offsets)?,
                subview_track_drag_offsets_json: serde_json::to_string(
                    &normalized_subview_track_drag_offsets,
                )?,
                subview_anchor_state_by_key_json: serde_json::to_string(
                    &normalized_subview_anchor_state_by_key,
                )?,
                final_path_view_mode: normalized_final_path_view_mode,
                final_path_by_chr_json: serde_json::to_string(&normalized_final_path_by_chr)?,
                degap_project_state_json: serde_json::to_string(&normalized_degap_project_state)?,
            },
        )?;
        let support_mirrored_ctgs =
            serde_json::from_str::<Value>(&state.support_mirrored_ctgs_json)
                .unwrap_or_else(|_| json!([]));
        let final_path_by_chr = serde_json::from_str::<Value>(&state.final_path_by_chr_json)
            .unwrap_or_else(|_| json!({}));
        Ok(json!({
            "projectId": state.project_id,
            "supportDatasetId": state.support_dataset_id,
            "trackView": serde_json::from_str::<Value>(&state.track_view_json)
                .unwrap_or_else(|_| json!({})),
            "supportDsCtgLenRulesByChr": serde_json::from_str::<Value>(&state.support_ds_ctg_len_rules_by_chr_json)
                .unwrap_or_else(|_| json!({})),
            "trackScrollState": serde_json::from_str::<Value>(&state.track_scroll_state_json)
                .unwrap_or_else(|_| json!({})),
            "subviewTrackScrollState": serde_json::from_str::<Value>(&state.subview_track_scroll_state_json)
                .unwrap_or_else(|_| json!({})),
            "supportMirroredCtgs": support_mirrored_ctgs,
            "hiddenPrimaryCtgIds": serde_json::from_str::<Value>(&state.hidden_primary_ctg_ids_json)
                .unwrap_or_else(|_| json!([])),
            "hiddenPrimaryCtgIdsByChr": serde_json::from_str::<Value>(&state.hidden_primary_ctg_ids_by_chr_json)
                .unwrap_or_else(|_| json!({})),
            "trackDragOffsets": serde_json::from_str::<Value>(&state.track_drag_offsets_json)
                .unwrap_or_else(|_| json!([])),
            "subviewTrackDragOffsets": serde_json::from_str::<Value>(&state.subview_track_drag_offsets_json)
                .unwrap_or_else(|_| json!([])),
            "subviewAnchorStateByKey": serde_json::from_str::<Value>(&state.subview_anchor_state_by_key_json)
                .unwrap_or_else(|_| json!({})),
            "finalPathViewMode": state.final_path_view_mode,
            "finalPathByChr": final_path_by_chr,
            "degapProjectState": serde_json::from_str::<Value>(&state.degap_project_state_json)
                .unwrap_or_else(|_| json!({})),
            "updatedAt": state.updated_at,
            "source": "workspace_db"
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn append_edit_audit_log(
    workspaceRoot: String,
    projectId: i64,
    category: String,
    action: String,
    detail: Option<String>,
) -> Result<Value, String> {
    (|| {
        let item = backend_append_edit_audit_log(
            &project_db_path(&workspaceRoot),
            &AppendEditAuditLogParams {
                project_id: projectId,
                category,
                action,
                detail,
            },
        )?;
        Ok(json!({
            "id": item.id,
            "projectId": item.project_id,
            "category": item.category,
            "action": item.action,
            "detail": item.detail,
            "createdAt": item.created_at
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_edit_audit_logs(
    workspaceRoot: String,
    projectId: i64,
    limit: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_edit_audit_logs(
            &project_db_path(&workspaceRoot),
            &ListEditAuditLogsParams {
                project_id: projectId,
                limit: limit.unwrap_or(200),
            },
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                json!({
                    "id": item.id,
                    "projectId": item.project_id,
                    "category": item.category,
                    "action": item.action,
                    "detail": item.detail,
                    "createdAt": item.created_at
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn clear_edit_audit_logs(workspaceRoot: String, projectId: i64) -> Result<Value, String> {
    (|| {
        let deleted_count =
            backend_clear_edit_audit_logs(&project_db_path(&workspaceRoot), projectId)?;
        Ok(json!({
            "projectId": projectId,
            "deletedCount": deleted_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
pub fn pick_zip_file_path() -> Result<Option<String>, String> {
    let selected = FileDialog::new()
        .add_filter("zip", &["zip"])
        .pick_file()
        .map(|path| path_to_string(&path));
    Ok(selected)
}

#[tauri::command]
pub fn pick_directory_path() -> Result<Option<String>, String> {
    let selected = FileDialog::new()
        .pick_folder()
        .map(|path| path_to_string(&path));
    Ok(selected)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn pick_save_file_path(
    defaultPath: Option<String>,
    filters: Value,
) -> Result<Option<String>, String> {
    let mut dialog = FileDialog::new();
    if let Some(file_name) = defaultPath
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        dialog = dialog.set_file_name(file_name);
    }
    let selected = apply_dialog_filters(dialog, &filters)
        .save_file()
        .map(|path| path_to_string(&path));
    Ok(selected)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn write_final_path_export_text_file(
    outputPath: String,
    text: String,
) -> Result<Value, String> {
    (|| {
        let output_path = PathBuf::from(outputPath.trim());
        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }
        fs::write(&output_path, text)
            .with_context(|| format!("failed to write {}", output_path.display()))?;
        Ok(json!({ "outputPath": path_to_string(&output_path) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn write_final_path_export_binary_file(
    outputPath: String,
    bytesBase64: String,
) -> Result<Value, String> {
    (|| {
        let output_path = PathBuf::from(outputPath.trim());
        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }
        let bytes = BASE64_STANDARD
            .decode(bytesBase64.trim())
            .context("failed to decode base64 PNG bytes")?;
        fs::write(&output_path, bytes)
            .with_context(|| format!("failed to write {}", output_path.display()))?;
        Ok(json!({ "outputPath": path_to_string(&output_path) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn export_final_path_fasta(
    workspaceRoot: String,
    projectId: i64,
    chrName: String,
    finalPathEntry: Value,
    outputPath: String,
) -> Result<Value, String> {
    (|| {
        let summary = backend_export_final_path_fasta(
            &project_db_path(&workspaceRoot),
            projectId,
            &ExportFinalPathFastaParams {
                chr_name: chrName.trim().to_string(),
                output_path: PathBuf::from(outputPath.trim()),
                final_path_segments: normalize_final_path_export_segments(&finalPathEntry)?,
            },
        )?;
        Ok(json!({ "outputPath": path_to_string(&summary.output_path) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn export_project_final_path_fasta(
    workspaceRoot: String,
    projectId: i64,
    finalPathByChr: Value,
    outputPath: String,
) -> Result<Value, String> {
    (|| {
        let summary = backend_export_project_final_path_fasta(
            &project_db_path(&workspaceRoot),
            projectId,
            &ExportProjectFinalPathFastaParams {
                output_path: PathBuf::from(outputPath.trim()),
                records: normalize_project_final_path_fasta_records(&finalPathByChr)?,
            },
        )?;
        Ok(json!({ "outputPath": path_to_string(&summary.output_path) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn export_degap_jobs(
    workspaceRoot: String,
    projectId: i64,
    outputDir: String,
    settings: Value,
    jobs: Value,
) -> Result<Value, String> {
    (|| {
        let params = ExportDegapJobsParams {
            output_dir: PathBuf::from(outputDir),
            settings: parse_degap_export_settings(&settings)?,
            jobs: parse_degap_export_jobs(&jobs)?,
        };
        let summary = backend_export_degap_jobs(
            &project_db_path(&workspaceRoot),
            Path::new(&workspaceRoot),
            projectId,
            &params,
        )?;
        Ok(json!({
            "outputDir": summary.output_dir.to_string_lossy(),
            "manifestPath": summary.manifest_path.to_string_lossy(),
            "prepareScriptPath": summary.prepare_script_path.to_string_lossy(),
            "scripts": summary.scripts.into_iter().map(|script| json!({
                "jobId": script.job_id,
                "scriptPath": script.script_path.to_string_lossy(),
                "outPath": script.out_path,
                "seqleftPath": script.seqleft_path,
                "seqrightPath": script.seqright_path,
                "ctgPath": script.ctg_path,
            })).collect::<Vec<_>>(),
        }))
    })()
    .map_err(format_error)
}

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
}
