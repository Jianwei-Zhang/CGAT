use super::*;

#[tauri::command]
pub fn pick_zip_file_path() -> CommandResult<Option<String>> {
    let selected = FileDialog::new()
        .add_filter("GPM archives (ZIP, tar.gz)", &["zip", "gz", "tgz"])
        .pick_file()
        .map(|path| path_to_string(&path));
    Ok(selected)
}

#[tauri::command]
pub fn pick_directory_path() -> CommandResult<Option<String>> {
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
) -> CommandResult<Option<String>> {
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
pub fn write_final_path_export_text_file(outputPath: String, text: String) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
pub fn export_final_path_agp(
    workspaceRoot: String,
    projectId: i64,
    chrName: String,
    finalPathEntry: Value,
    outputPath: String,
) -> CommandResult<Value> {
    (|| {
        let summary = backend_export_final_path_agp(
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
pub fn export_project_final_path_agp(
    workspaceRoot: String,
    projectId: i64,
    finalPathByChr: Value,
    outputPath: String,
) -> CommandResult<Value> {
    (|| {
        let summary = backend_export_project_final_path_agp(
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
pub async fn export_manual_refinement(
    workspaceRoot: String,
    projectId: i64,
    outputPath: String,
    request: gpm_next_backend::degap_jobs::ManualRefinementRequest,
) -> CommandResult<Value> {
    run_blocking_command("export_manual_refinement", move || {
        let summary = gpm_next_backend::degap_jobs::export_manual_refinement(
            Path::new(&workspaceRoot),
            projectId,
            Path::new(&outputPath),
            &request,
        )
        .map_err(format_error)?;
        Ok(json!({
            "batch_sha256": summary.batch_sha256,
            "loci": summary.loci,
            "tasks": summary.tasks,
        }))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_manual_refinement_results(
    workspaceRoot: String,
    projectId: i64,
    zipPath: String,
) -> CommandResult<Value> {
    run_blocking_command("import_manual_refinement_results", move || {
        if let Some(automatic) = gpm_next_backend::grt_package::import_auto_patch_if_recognized(
            Path::new(&workspaceRoot), projectId, Path::new(&zipPath),
        ).map_err(format_error)? {
            return Ok(automatic);
        }
        let result = gpm_next_backend::degap_jobs::import_manual_refinement_results(
            Path::new(&workspaceRoot),
            projectId,
            Path::new(&zipPath),
        )
        .map_err(format_error)?;
        Ok(json!(result))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn list_manual_refinement_results(
    workspaceRoot: String,
    projectId: i64,
) -> CommandResult<Value> {
    run_blocking_command("list_manual_refinement_results", move || {
        let results = gpm_next_backend::degap_jobs::list_manual_refinement_results(
            Path::new(&workspaceRoot),
            projectId,
        )
        .map_err(format_error)?;
        Ok(json!(results))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn list_manual_refinement_exports(
    workspaceRoot: String,
    projectId: i64,
) -> CommandResult<Value> {
    run_blocking_command("list_manual_refinement_exports", move || {
        let exports = gpm_next_backend::degap_jobs::list_manual_refinement_exports(
            Path::new(&workspaceRoot),
            projectId,
        )
        .map_err(format_error)?;
        Ok(json!(exports))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn undo_manual_refinement_locus(
    workspaceRoot: String,
    projectId: i64,
    locusId: String,
    expectedRevision: u64,
) -> CommandResult<Value> {
    run_blocking_command("undo_manual_refinement_locus", move || {
        let action = gpm_next_backend::degap_jobs::undo_manual_refinement_locus(
            Path::new(&workspaceRoot),
            projectId,
            &locusId,
            expectedRevision,
        )
        .map_err(format_error)?;
        Ok(json!(action))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn switch_manual_refinement_locus(
    workspaceRoot: String,
    projectId: i64,
    locusId: String,
    expectedRevision: u64,
    resultSha256: String,
    tool: String,
) -> CommandResult<Value> {
    run_blocking_command("switch_manual_refinement_locus", move || {
        let action = gpm_next_backend::degap_jobs::switch_manual_refinement_locus(
            Path::new(&workspaceRoot),
            projectId,
            &locusId,
            expectedRevision,
            &resultSha256,
            &tool,
        )
        .map_err(format_error)?;
        Ok(json!(action))
    })
    .await
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn export_degap_jobs(
    workspaceRoot: String,
    projectId: i64,
    outputDir: String,
    settings: Value,
    jobs: Value,
) -> CommandResult<Value> {
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
            "runScriptPath": summary.output_dir.join("run_degap_jobs.sh").to_string_lossy(),
            "collectScriptPath": summary.output_dir.join("collect_degap_results.sh").to_string_lossy(),
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
