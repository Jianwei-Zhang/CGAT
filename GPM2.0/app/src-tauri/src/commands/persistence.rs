use super::*;

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_export_records(
    workspaceRoot: String,
    projectId: i64,
    limit: Option<i64>,
) -> CommandResult<Value> {
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
pub fn get_runtime_settings(workspaceRoot: String) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
            "subviewHistoryByKey": serde_json::from_str::<Value>(&state.subview_history_by_key_json)
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
pub fn update_project_assembly_view_state(
    request: UpdateProjectAssemblyViewStateCommandRequest,
) -> CommandResult<Value> {
    let UpdateProjectAssemblyViewStateCommandRequest {
        workspace_root,
        project_id,
        support_dataset_id,
        track_view,
        support_ds_ctg_len_rules_by_chr,
        track_scroll_state,
        subview_track_scroll_state,
        support_mirrored_ctgs,
        hidden_primary_ctg_ids,
        hidden_primary_ctg_ids_by_chr,
        track_drag_offsets,
        subview_track_drag_offsets,
        subview_anchor_state_by_key,
        subview_history_by_key,
        final_path_view_mode,
        final_path_by_chr,
        degap_project_state,
    } = request;
    (|| {
        let normalized_support_mirrored_ctgs = if support_mirrored_ctgs.is_array() {
            support_mirrored_ctgs
        } else {
            json!([])
        };
        let normalized_track_view = if track_view.is_object() {
            track_view
        } else {
            json!({})
        };
        let normalized_support_ds_ctg_len_rules_by_chr = if support_ds_ctg_len_rules_by_chr.is_object()
        {
            support_ds_ctg_len_rules_by_chr
        } else {
            json!({})
        };
        let normalized_track_scroll_state = if track_scroll_state.is_object() {
            track_scroll_state
        } else {
            json!({})
        };
        let normalized_subview_track_scroll_state = if subview_track_scroll_state.is_object() {
            subview_track_scroll_state
        } else {
            json!({})
        };
        let normalized_hidden_primary_ctg_ids = if hidden_primary_ctg_ids.is_array() {
            hidden_primary_ctg_ids
        } else {
            json!([])
        };
        let normalized_hidden_primary_ctg_ids_by_chr = if hidden_primary_ctg_ids_by_chr.is_object() {
            hidden_primary_ctg_ids_by_chr
        } else {
            json!({})
        };
        let normalized_track_drag_offsets = if track_drag_offsets.is_array() {
            track_drag_offsets
        } else {
            json!([])
        };
        let normalized_subview_track_drag_offsets = if subview_track_drag_offsets.is_array() {
            subview_track_drag_offsets
        } else {
            json!([])
        };
        let normalized_subview_anchor_state_by_key = if subview_anchor_state_by_key.is_object() {
            subview_anchor_state_by_key
        } else {
            json!({})
        };
        let normalized_subview_history_by_key = if subview_history_by_key.is_object() {
            subview_history_by_key
        } else {
            json!({})
        };
        let normalized_final_path_by_chr = if final_path_by_chr.is_object() {
            final_path_by_chr
        } else {
            json!({})
        };
        let normalized_degap_project_state = if degap_project_state.is_object() {
            degap_project_state
        } else {
            json!({})
        };
        let normalized_final_path_view_mode = match final_path_view_mode.trim() {
            "log" => "log".to_string(),
            "degap" => "degap".to_string(),
            "table" => "table".to_string(),
            _ => "graph".to_string(),
        };
        let state = backend_update_project_assembly_view_state(
            &project_db_path(&workspace_root),
            &UpdateProjectAssemblyViewStateParams {
                project_id,
                support_dataset_id: support_dataset_id.filter(|value| *value > 0),
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
                subview_history_by_key_json: serde_json::to_string(
                    &normalized_subview_history_by_key,
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
            "subviewHistoryByKey": serde_json::from_str::<Value>(&state.subview_history_by_key_json)
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
) -> CommandResult<Value> {
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
) -> CommandResult<Value> {
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
pub fn clear_edit_audit_logs(workspaceRoot: String, projectId: i64) -> CommandResult<Value> {
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
