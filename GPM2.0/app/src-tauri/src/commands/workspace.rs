use super::*;

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_project_initializer_options(workspaceRoot: String) -> CommandResult<Value> {
    read_initializer_options(&workspaceRoot, false).map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn open_workspace(workspaceRoot: String) -> CommandResult<Value> {
    read_initializer_options(&workspaceRoot, true).map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn validate_workspace_integrity(workspaceRoot: String) -> CommandResult<Value> {
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
pub fn delete_workspace_directory(workspaceRoot: String) -> CommandResult<Value> {
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
pub fn initialize_project(request: InitializeProjectCommandRequest) -> CommandResult<Value> {
    let InitializeProjectCommandRequest {
        workspace_root,
        project_name,
        phased_assembly_enabled,
    } = request;
    (|| {
        let project_db = project_db_path(&workspace_root);
        let summary = backend_initialize_grt_project_with_options(
            &project_db,
            &project_name,
            phased_assembly_enabled,
        )?;
        let options = backend_list_initializer_options(&project_db)?;
        let existing_projects = map_existing_projects(options.existing_projects);
        let grt_project_view = backend_load_grt_project_view(&project_db)?;
        Ok(json!({
            "projectId": summary.project_id,
            "projectName": summary.project_name,
            "version": summary.version,
            "referenceGenomeId": summary.reference_genome_id,
            "primaryDatasetId": summary.primary_dataset_id,
            "supportDatasetIds": summary.support_dataset_ids,
            "projectDatasetCount": summary.project_dataset_count,
            "phasedAssemblyEnabled": summary.phased_assembly_enabled,
            "chrAssignmentMinCoveragePercent": summary.chr_assignment_min_coverage_percent,
            "assemblySeqCount": summary.assembly_seq_count,
            "assemblyCtgCount": summary.assembly_ctg_count,
            "materializedSourceCardCount": summary.materialized_source_card_count,
            "grtProjectView": serde_json::to_value(grt_project_view)?,
            "existingProjects": existing_projects
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn get_grt_project_view(workspaceRoot: String, projectId: i64) -> CommandResult<Value> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let options = backend_list_initializer_options(&project_db)?;
        if !options
            .existing_projects
            .iter()
            .any(|project| project.id == projectId)
        {
            bail!("project_id {projectId} does not exist");
        }
        Ok(serde_json::to_value(backend_load_grt_project_view(
            &project_db,
        )?)?)
    })()
    .map_err(format_error)
}

#[tauri::command]
pub fn update_project(request: UpdateProjectCommandRequest) -> CommandResult<Value> {
    let UpdateProjectCommandRequest {
        workspace_root,
        project_id,
        project_name,
        reference_genome_id,
        primary_dataset_id,
        support_dataset_ids,
        chr_assignment_min_coverage_percent,
        phased_assembly_enabled,
    } = request;
    (|| {
        let project_db = project_db_path(&workspace_root);
        let summary = backend_update_project(
            &project_db,
            &ProjectUpdateRequest {
                project_id,
                project_name,
                reference_genome_id,
                primary_dataset_id,
                support_dataset_ids: support_dataset_ids.unwrap_or_default(),
                phased_assembly_enabled,
                chr_assignment_min_coverage_percent,
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
pub async fn delete_project(workspaceRoot: String, projectId: i64) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
    let requested = auto_pipeline_cancel::request_cancel(&workspaceRoot, projectId, &runId);
    Ok(json!({
        "workspaceRoot": workspaceRoot,
        "projectId": projectId,
        "runId": runId,
        "requested": requested
    }))
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn set_project_auto_pipeline_done(
    workspaceRoot: String,
    projectId: i64,
    done: Option<bool>,
) -> CommandResult<Value> {
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
pub fn list_project_chromosomes(workspaceRoot: String, projectId: i64) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
