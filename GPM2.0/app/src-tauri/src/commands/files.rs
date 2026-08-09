use super::*;

#[tauri::command]
pub fn pick_zip_file_path() -> CommandResult<Option<String>> {
    let selected = FileDialog::new()
        .add_filter("zip", &["zip"])
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
