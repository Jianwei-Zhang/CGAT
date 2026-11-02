use super::*;
use gpm_next_backend::project_preview_cache::{
    get_project_preview_cache as backend_get_preview_cache,
    put_project_preview_cache as backend_put_preview_cache,
};

#[tauri::command]
#[allow(non_snake_case)]
pub async fn get_project_preview_cache(
    workspaceRoot: String,
    projectId: i64,
    modelVersion: i64,
    expectedIdentity: Option<String>,
    sinceRevision: Option<i64>,
) -> CommandResult<Value> {
    run_blocking_command("get_project_preview_cache", move || {
        backend_get_preview_cache(
            &project_db_path(&workspaceRoot),
            projectId,
            modelVersion,
            expectedIdentity.as_deref(),
            sinceRevision,
        )
        .map_err(format_error)
    })
    .await
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PutProjectPreviewCacheRequest {
    workspace_root: String,
    project_id: i64,
    model_version: i64,
    expected_identity: String,
    expected_revision: i64,
    payload: Value,
}

#[tauri::command]
pub async fn put_project_preview_cache(
    request: PutProjectPreviewCacheRequest,
) -> CommandResult<Value> {
    run_blocking_command("put_project_preview_cache", move || {
        backend_put_preview_cache(
            &project_db_path(&request.workspace_root),
            request.project_id,
            request.model_version,
            &request.expected_identity,
            request.expected_revision,
            &request.payload,
        )
        .map_err(format_error)
    })
    .await
}
