use super::*;

#[tauri::command]
#[allow(non_snake_case)]
pub async fn import_zip(
    app: AppHandle,
    zipPath: String,
    workspaceRoot: String,
    runId: Option<String>,
) -> CommandResult<Value> {
    let zip_path = zipPath;
    let workspace_root = workspaceRoot;
    let run_id = normalize_optional_run_id(runId);
    // Preserve a request submitted after the dialog opens but before this worker starts.
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
) -> CommandResult<Value> {
    let extracted_path = extractedPath;
    let run_id = normalize_optional_run_id(runId);
    // Preserve a request submitted after the dialog opens but before this worker starts.
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
) -> CommandResult<Value> {
    let workspace_root = workspaceRoot;
    let zip_path = zipPath;
    let run_id = normalize_optional_run_id(runId);
    // Preserve a request submitted after the dialog opens but before this worker starts.
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
) -> CommandResult<Value> {
    let workspace_root = workspaceRoot;
    let zip_path = zipPath;
    let expected_target = AddCtgImportTarget {
        target_chr: expectedTargetChr.unwrap_or_default(),
        target_track: expectedTargetTrack.unwrap_or_default(),
    };
    let run_id = normalize_optional_run_id(runId);
    // Preserve a request submitted after the dialog opens but before this worker starts.
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
pub fn request_import_cancel(runId: String) -> CommandResult<Value> {
    let registered = import_cancel::request_cancel(&runId);
    Ok(json!({
        "runId": runId,
        "cancelRequested": registered
    }))
}
