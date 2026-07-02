use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use crate::db::open_workspace_db;

#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeSettings {
    pub updated_at: String,
    pub degap_workspace_settings_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct UpdateRuntimeSettingsParams {
    pub degap_workspace_settings_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectAssemblyViewState {
    pub project_id: i64,
    pub support_dataset_id: Option<i64>,
    pub track_view_json: String,
    pub support_ds_ctg_len_rules_by_chr_json: String,
    pub track_scroll_state_json: String,
    pub subview_track_scroll_state_json: String,
    pub support_mirrored_ctgs_json: String,
    pub hidden_primary_ctg_ids_json: String,
    pub hidden_primary_ctg_ids_by_chr_json: String,
    pub track_drag_offsets_json: String,
    pub subview_track_drag_offsets_json: String,
    pub subview_anchor_state_by_key_json: String,
    pub final_path_view_mode: String,
    pub final_path_by_chr_json: String,
    pub degap_project_state_json: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateProjectAssemblyViewStateParams {
    pub project_id: i64,
    pub support_dataset_id: Option<i64>,
    pub track_view_json: String,
    pub support_ds_ctg_len_rules_by_chr_json: String,
    pub track_scroll_state_json: String,
    pub subview_track_scroll_state_json: String,
    pub support_mirrored_ctgs_json: String,
    pub hidden_primary_ctg_ids_json: String,
    pub hidden_primary_ctg_ids_by_chr_json: String,
    pub track_drag_offsets_json: String,
    pub subview_track_drag_offsets_json: String,
    pub subview_anchor_state_by_key_json: String,
    pub final_path_view_mode: String,
    pub final_path_by_chr_json: String,
    pub degap_project_state_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppendEditAuditLogParams {
    pub project_id: i64,
    pub category: String,
    pub action: String,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ListEditAuditLogsParams {
    pub project_id: i64,
    pub limit: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EditAuditLogItem {
    pub id: i64,
    pub project_id: i64,
    pub category: String,
    pub action: String,
    pub detail: Option<String>,
    pub created_at: String,
}

pub fn get_runtime_settings(project_db_path: &Path) -> Result<RuntimeSettings> {
    let mut conn = open_workspace_db(project_db_path)?;
    get_runtime_settings_with_connection(&mut conn)
}

pub fn update_runtime_settings(
    project_db_path: &Path,
    params: &UpdateRuntimeSettingsParams,
) -> Result<RuntimeSettings> {
    let mut conn = open_workspace_db(project_db_path)?;
    update_runtime_settings_with_connection(&mut conn, params)
}

pub fn get_project_assembly_view_state(
    project_db_path: &Path,
    project_id: i64,
) -> Result<ProjectAssemblyViewState> {
    let mut conn = open_workspace_db(project_db_path)?;
    get_project_assembly_view_state_with_connection(&mut conn, project_id)
}

pub fn update_project_assembly_view_state(
    project_db_path: &Path,
    params: &UpdateProjectAssemblyViewStateParams,
) -> Result<ProjectAssemblyViewState> {
    let mut conn = open_workspace_db(project_db_path)?;
    update_project_assembly_view_state_with_connection(&mut conn, params)
}

pub fn append_edit_audit_log(
    project_db_path: &Path,
    params: &AppendEditAuditLogParams,
) -> Result<EditAuditLogItem> {
    let mut conn = open_workspace_db(project_db_path)?;
    append_edit_audit_log_with_connection(&mut conn, params)
}

pub fn list_edit_audit_logs(
    project_db_path: &Path,
    params: &ListEditAuditLogsParams,
) -> Result<Vec<EditAuditLogItem>> {
    let conn = open_workspace_db(project_db_path)?;
    list_edit_audit_logs_with_connection(&conn, params)
}

pub fn clear_edit_audit_logs(project_db_path: &Path, project_id: i64) -> Result<i64> {
    let mut conn = open_workspace_db(project_db_path)?;
    clear_edit_audit_logs_with_connection(&mut conn, project_id)
}

fn get_runtime_settings_with_connection(conn: &mut Connection) -> Result<RuntimeSettings> {
    ensure_runtime_settings_row(conn)?;
    let row = conn
        .query_row(
            "SELECT updated_at,
                    degap_workspace_settings_json
             FROM runtime_settings
             WHERE id = 1",
            [],
            decode_runtime_settings_row,
        )
        .context("failed to load runtime settings row")?;
    Ok(row)
}

fn update_runtime_settings_with_connection(
    conn: &mut Connection,
    params: &UpdateRuntimeSettingsParams,
) -> Result<RuntimeSettings> {
    let mut current = get_runtime_settings_with_connection(conn)?;
    current.updated_at = now_timestamp_string();
    current.degap_workspace_settings_json =
        normalize_project_assembly_map_json(&params.degap_workspace_settings_json).to_string();
    conn.execute(
        "UPDATE runtime_settings
         SET updated_at = ?1,
             degap_workspace_settings_json = ?2
         WHERE id = 1",
        params![current.updated_at, current.degap_workspace_settings_json],
    )
    .context("failed to update runtime settings")?;

    Ok(current)
}

fn get_project_assembly_view_state_with_connection(
    conn: &mut Connection,
    project_id: i64,
) -> Result<ProjectAssemblyViewState> {
    ensure_project_exists(conn, project_id)?;
    ensure_project_assembly_view_state_row(conn, project_id)?;
    let row = conn
        .query_row(
            "SELECT project_id,
                    support_dataset_id,
                    track_view_json,
                    support_ds_ctg_len_rules_by_chr_json,
                    track_scroll_state_json,
                    subview_track_scroll_state_json,
                    support_mirrored_ctgs_json,
                    hidden_primary_ctg_ids_json,
                    hidden_primary_ctg_ids_by_chr_json,
                    track_drag_offsets_json,
                    subview_track_drag_offsets_json,
                    subview_anchor_state_by_key_json,
                    final_path_view_mode,
                    final_path_by_chr_json,
                    degap_project_state_json,
                    updated_at
             FROM project_assembly_view_state
             WHERE project_id = ?1",
            params![project_id],
            |row| {
                Ok(ProjectAssemblyViewState {
                    project_id: row.get(0)?,
                    support_dataset_id: row.get(1)?,
                    track_view_json: row.get(2)?,
                    support_ds_ctg_len_rules_by_chr_json: row.get(3)?,
                    track_scroll_state_json: row.get(4)?,
                    subview_track_scroll_state_json: row.get(5)?,
                    support_mirrored_ctgs_json: row.get(6)?,
                    hidden_primary_ctg_ids_json: row.get(7)?,
                    hidden_primary_ctg_ids_by_chr_json: row.get(8)?,
                    track_drag_offsets_json: row.get(9)?,
                    subview_track_drag_offsets_json: row.get(10)?,
                    subview_anchor_state_by_key_json: row.get(11)?,
                    final_path_view_mode: row.get(12)?,
                    final_path_by_chr_json: row.get(13)?,
                    degap_project_state_json: row.get(14)?,
                    updated_at: row.get(15)?,
                })
            },
        )
        .context("failed to load project assembly view state row")?;
    Ok(row)
}

fn normalize_project_assembly_view_state_json(value: &str) -> &str {
    match value.trim() {
        "" => "[]",
        normalized => normalized,
    }
}

fn normalize_project_assembly_track_view_json(value: &str) -> &str {
    match value.trim() {
        "" => "{}",
        normalized => normalized,
    }
}

fn normalize_project_assembly_scroll_state_json(value: &str) -> &str {
    match value.trim() {
        "" => "{}",
        normalized => normalized,
    }
}

fn normalize_project_assembly_map_json(value: &str) -> &str {
    match value.trim() {
        "" => "{}",
        normalized => normalized,
    }
}

fn normalize_project_assembly_view_mode(value: &str) -> &str {
    match value.trim() {
        "log" => "log",
        "degap" => "degap",
        "table" => "table",
        _ => "graph",
    }
}

fn update_project_assembly_view_state_with_connection(
    conn: &mut Connection,
    params: &UpdateProjectAssemblyViewStateParams,
) -> Result<ProjectAssemblyViewState> {
    ensure_project_exists(conn, params.project_id)?;
    ensure_project_assembly_view_state_row(conn, params.project_id)?;
    let updated_at = now_timestamp_string();
    conn.execute(
        "UPDATE project_assembly_view_state
         SET support_dataset_id = ?2,
             track_view_json = ?3,
             support_ds_ctg_len_rules_by_chr_json = ?4,
             track_scroll_state_json = ?5,
             subview_track_scroll_state_json = ?6,
             support_mirrored_ctgs_json = ?7,
             hidden_primary_ctg_ids_json = ?8,
             hidden_primary_ctg_ids_by_chr_json = ?9,
             track_drag_offsets_json = ?10,
             subview_track_drag_offsets_json = ?11,
             subview_anchor_state_by_key_json = ?12,
             final_path_view_mode = ?13,
             final_path_by_chr_json = ?14,
             degap_project_state_json = ?15,
             updated_at = ?16
         WHERE project_id = ?1",
        params![
            params.project_id,
            params.support_dataset_id,
            normalize_project_assembly_track_view_json(&params.track_view_json),
            normalize_project_assembly_map_json(&params.support_ds_ctg_len_rules_by_chr_json),
            normalize_project_assembly_scroll_state_json(&params.track_scroll_state_json),
            normalize_project_assembly_scroll_state_json(&params.subview_track_scroll_state_json),
            normalize_project_assembly_view_state_json(&params.support_mirrored_ctgs_json),
            normalize_project_assembly_view_state_json(&params.hidden_primary_ctg_ids_json),
            normalize_project_assembly_map_json(&params.hidden_primary_ctg_ids_by_chr_json),
            normalize_project_assembly_view_state_json(&params.track_drag_offsets_json),
            normalize_project_assembly_view_state_json(&params.subview_track_drag_offsets_json),
            normalize_project_assembly_map_json(&params.subview_anchor_state_by_key_json),
            normalize_project_assembly_view_mode(&params.final_path_view_mode),
            normalize_project_assembly_map_json(&params.final_path_by_chr_json),
            normalize_project_assembly_map_json(&params.degap_project_state_json),
            updated_at,
        ],
    )
    .context("failed to update project assembly view state")?;
    get_project_assembly_view_state_with_connection(conn, params.project_id)
}

fn append_edit_audit_log_with_connection(
    conn: &mut Connection,
    params: &AppendEditAuditLogParams,
) -> Result<EditAuditLogItem> {
    ensure_project_exists(conn, params.project_id)?;
    let category = normalize_audit_category(&params.category)?;
    let action = params.action.trim();
    if action.is_empty() {
        bail!("action is required");
    }
    let detail = params
        .detail
        .as_ref()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
        .map(|value| value.to_string());
    let created_at = now_timestamp_string();
    conn.execute(
        "INSERT INTO edit_audit_log (
            project_id,
            category,
            action,
            detail,
            created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5)",
        params![params.project_id, category, action, detail, created_at],
    )
    .context("failed to insert edit audit log")?;
    let id = conn.last_insert_rowid();
    Ok(EditAuditLogItem {
        id,
        project_id: params.project_id,
        category,
        action: action.to_string(),
        detail,
        created_at,
    })
}

fn list_edit_audit_logs_with_connection(
    conn: &Connection,
    params: &ListEditAuditLogsParams,
) -> Result<Vec<EditAuditLogItem>> {
    ensure_project_exists(conn, params.project_id)?;
    let limit = params.limit.clamp(1, 1000);
    let mut stmt = conn
        .prepare(
            "SELECT id, project_id, category, action, detail, created_at
             FROM edit_audit_log
             WHERE project_id = ?1
             ORDER BY created_at DESC, id DESC
             LIMIT ?2",
        )
        .context("failed to prepare list edit audit logs statement")?;
    let rows = stmt
        .query_map(params![params.project_id, limit], |row| {
            Ok(EditAuditLogItem {
                id: row.get(0)?,
                project_id: row.get(1)?,
                category: row.get(2)?,
                action: row.get(3)?,
                detail: row.get(4)?,
                created_at: row.get(5)?,
            })
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode edit audit logs")?;
    Ok(rows)
}

fn clear_edit_audit_logs_with_connection(conn: &mut Connection, project_id: i64) -> Result<i64> {
    ensure_project_exists(conn, project_id)?;
    let deleted = conn
        .execute(
            "DELETE FROM edit_audit_log WHERE project_id = ?1",
            params![project_id],
        )
        .context("failed to clear edit audit logs")?;
    Ok(deleted as i64)
}

fn ensure_runtime_settings_row(conn: &Connection) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO runtime_settings (
            id,
            updated_at,
            degap_workspace_settings_json
         ) VALUES (
            1,
            ?1,
            '{}'
         )",
        params![now_timestamp_string()],
    )
    .context("failed to ensure runtime settings row")?;
    Ok(())
}

fn ensure_project_assembly_view_state_row(conn: &Connection, project_id: i64) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO project_assembly_view_state (
            project_id,
            support_dataset_id,
            track_view_json,
            support_ds_ctg_len_rules_by_chr_json,
            track_scroll_state_json,
            subview_track_scroll_state_json,
            support_mirrored_ctgs_json,
            hidden_primary_ctg_ids_json,
            hidden_primary_ctg_ids_by_chr_json,
            track_drag_offsets_json,
            subview_track_drag_offsets_json,
            subview_anchor_state_by_key_json,
            final_path_view_mode,
            final_path_by_chr_json,
            degap_project_state_json,
            updated_at
         ) VALUES (
            ?1,
            NULL,
            '{}',
            '{}',
            '{}',
            '{}',
            '[]',
            '[]',
            '{}',
            '[]',
            '[]',
            '{}',
            'graph',
            '{}',
            '{}',
            ?2
         )",
        params![project_id, now_timestamp_string()],
    )
    .context("failed to ensure project assembly view state row")?;
    Ok(())
}

fn ensure_project_exists(conn: &Connection, project_id: i64) -> Result<()> {
    let exists = conn
        .query_row(
            "SELECT 1 FROM project WHERE id = ?1",
            params![project_id],
            |_| Ok(true),
        )
        .optional()?
        .unwrap_or(false);
    if !exists {
        bail!("project {} not found", project_id);
    }
    Ok(())
}

fn normalize_audit_category(category: &str) -> Result<String> {
    let normalized = category.trim().to_ascii_lowercase();
    match normalized.as_str() {
        "editor" | "junction" | "settings" | "session" => Ok(normalized),
        _ => bail!("unsupported audit category: {}", category),
    }
}

fn decode_runtime_settings_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RuntimeSettings> {
    Ok(RuntimeSettings {
        updated_at: row.get(0)?,
        degap_workspace_settings_json: row.get(1)?,
    })
}

fn now_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string()
}

#[cfg(test)]
mod tests {
    use anyhow::Result;
    use rusqlite::{Connection, params};

    use super::{
        AppendEditAuditLogParams, ListEditAuditLogsParams, UpdateProjectAssemblyViewStateParams,
        UpdateRuntimeSettingsParams, append_edit_audit_log_with_connection,
        clear_edit_audit_logs_with_connection, get_project_assembly_view_state_with_connection,
        get_runtime_settings_with_connection, list_edit_audit_logs_with_connection,
        update_project_assembly_view_state_with_connection,
        update_runtime_settings_with_connection,
    };
    use crate::db::init_workspace_schema;

    #[test]
    fn runtime_settings_support_defaults_and_update() -> Result<()> {
        let mut conn = Connection::open_in_memory()?;
        init_workspace_schema(&conn)?;

        let initial = get_runtime_settings_with_connection(&mut conn)?;
        assert!(!initial.updated_at.is_empty());

        let updated = update_runtime_settings_with_connection(
            &mut conn,
            &UpdateRuntimeSettingsParams {
                degap_workspace_settings_json: r#"{"hifiReads":["/reads/a.fq"]}"#.to_string(),
            },
        )?;
        assert!(!updated.updated_at.is_empty());
        assert_eq!(
            updated.degap_workspace_settings_json,
            r#"{"hifiReads":["/reads/a.fq"]}"#
        );

        let reloaded = get_runtime_settings_with_connection(&mut conn)?;
        assert_eq!(reloaded, updated);
        Ok(())
    }

    #[test]
    fn edit_audit_logs_support_append_list_and_clear() -> Result<()> {
        let mut conn = Connection::open_in_memory()?;
        init_workspace_schema(&conn)?;
        seed_project(&conn, 1)?;

        let first = append_edit_audit_log_with_connection(
            &mut conn,
            &AppendEditAuditLogParams {
                project_id: 1,
                category: "editor".to_string(),
                action: "rename-ctg".to_string(),
                detail: Some("ctg=10 -> Ctg10_new".to_string()),
            },
        )?;
        let second = append_edit_audit_log_with_connection(
            &mut conn,
            &AppendEditAuditLogParams {
                project_id: 1,
                category: "settings".to_string(),
                action: "update-runtime-settings".to_string(),
                detail: None,
            },
        )?;

        let listed = list_edit_audit_logs_with_connection(
            &conn,
            &ListEditAuditLogsParams {
                project_id: 1,
                limit: 20,
            },
        )?;
        assert_eq!(listed.len(), 2);
        assert_eq!(listed[0].id, second.id);
        assert_eq!(listed[1].id, first.id);

        let deleted = clear_edit_audit_logs_with_connection(&mut conn, 1)?;
        assert_eq!(deleted, 2);
        let empty = list_edit_audit_logs_with_connection(
            &conn,
            &ListEditAuditLogsParams {
                project_id: 1,
                limit: 20,
            },
        )?;
        assert!(empty.is_empty());
        Ok(())
    }

    #[test]
    fn project_assembly_view_state_persists_mirror_entries_per_project() -> Result<()> {
        let mut conn = Connection::open_in_memory()?;
        init_workspace_schema(&conn)?;
        seed_project(&conn, 1)?;
        seed_project(&conn, 2)?;

        let initial = get_project_assembly_view_state_with_connection(&mut conn, 1)?;
        assert_eq!(initial.project_id, 1);
        assert_eq!(initial.support_dataset_id, None);
        assert_eq!(initial.track_view_json, "{}");
        assert_eq!(initial.track_scroll_state_json, "{}");
        assert_eq!(initial.subview_track_scroll_state_json, "{}");
        assert_eq!(initial.support_mirrored_ctgs_json, "[]");
        assert_eq!(initial.hidden_primary_ctg_ids_json, "[]");
        assert_eq!(initial.hidden_primary_ctg_ids_by_chr_json, "{}");
        assert_eq!(initial.track_drag_offsets_json, "[]");
        assert_eq!(initial.subview_track_drag_offsets_json, "[]");
        assert_eq!(initial.subview_anchor_state_by_key_json, "{}");
        assert_eq!(initial.support_ds_ctg_len_rules_by_chr_json, "{}");
        assert_eq!(initial.final_path_view_mode, "graph");
        assert_eq!(initial.final_path_by_chr_json, "{}");
        assert_eq!(initial.degap_project_state_json, "{}");

        let updated = update_project_assembly_view_state_with_connection(
            &mut conn,
            &UpdateProjectAssemblyViewStateParams {
                project_id: 1,
                support_dataset_id: Some(22),
                track_view_json: r#"{"supportDsCtgLen":10000,"minTickUnitKb":250,"maxTickCount":15,"alignmentLength":10000,"mapq":30}"#.to_string(),
                support_ds_ctg_len_rules_by_chr_json:
                    r#"{"Chr01":[{"startBp":1,"endBp":5000000,"supportDsCtgLen":100000}]}"#
                        .to_string(),
                track_scroll_state_json:
                    r#"{"viewportKey":"1:chr1:1909:22:10000:250:15:10000:30","scrollLeft":320}"#
                        .to_string(),
                subview_track_scroll_state_json:
                    r#"{"viewportKey":"1:chr1:primary:1909:support:1910","scrollLeft":180}"#
                        .to_string(),
                support_mirrored_ctgs_json:
                    r#"[{"datasetId":22,"assemblyCtgId":1909,"name":"Ctg1909"}]"#.to_string(),
                hidden_primary_ctg_ids_json: r#"[1909,1910]"#.to_string(),
                hidden_primary_ctg_ids_by_chr_json:
                    r#"{"Chr01":[1909],"Chr02":[1910]}"#.to_string(),
                track_drag_offsets_json:
                    r#"[{"trackRole":"primary","assemblyCtgId":1909,"offsetBp":120}]"#.to_string(),
                subview_track_drag_offsets_json:
                    r#"[{"slot":"top","contigId":1909,"offsetBp":80}]"#.to_string(),
                subview_anchor_state_by_key_json:
                    r#"{"2-contig|chr:Chr01|a|b":{"activeAnchors":[{"hitKey":"h1","edge":"left"}],"manualAnchors":[]}}"#
                        .to_string(),
                final_path_view_mode: "degap".to_string(),
                final_path_by_chr_json: "{}".to_string(),
                degap_project_state_json: r#"{"jobs":[{"jobId":"a"}]}"#.to_string(),
            },
        )?;
        assert_eq!(updated.project_id, 1);
        assert_eq!(updated.support_dataset_id, Some(22));
        assert_eq!(
            updated.track_view_json,
            r#"{"supportDsCtgLen":10000,"minTickUnitKb":250,"maxTickCount":15,"alignmentLength":10000,"mapq":30}"#,
        );
        assert_eq!(
            updated.support_ds_ctg_len_rules_by_chr_json,
            r#"{"Chr01":[{"startBp":1,"endBp":5000000,"supportDsCtgLen":100000}]}"#,
        );
        assert_eq!(
            updated.track_scroll_state_json,
            r#"{"viewportKey":"1:chr1:1909:22:10000:250:15:10000:30","scrollLeft":320}"#,
        );
        assert_eq!(
            updated.subview_track_scroll_state_json,
            r#"{"viewportKey":"1:chr1:primary:1909:support:1910","scrollLeft":180}"#,
        );
        assert_eq!(
            updated.support_mirrored_ctgs_json,
            r#"[{"datasetId":22,"assemblyCtgId":1909,"name":"Ctg1909"}]"#,
        );
        assert_eq!(
            updated.degap_project_state_json,
            r#"{"jobs":[{"jobId":"a"}]}"#
        );
        assert_eq!(updated.hidden_primary_ctg_ids_json, r#"[1909,1910]"#);
        assert_eq!(
            updated.hidden_primary_ctg_ids_by_chr_json,
            r#"{"Chr01":[1909],"Chr02":[1910]}"#,
        );
        assert_eq!(
            updated.track_drag_offsets_json,
            r#"[{"trackRole":"primary","assemblyCtgId":1909,"offsetBp":120}]"#,
        );
        assert_eq!(
            updated.subview_track_drag_offsets_json,
            r#"[{"slot":"top","contigId":1909,"offsetBp":80}]"#,
        );
        assert_eq!(
            updated.subview_anchor_state_by_key_json,
            r#"{"2-contig|chr:Chr01|a|b":{"activeAnchors":[{"hitKey":"h1","edge":"left"}],"manualAnchors":[]}}"#,
        );
        assert_eq!(updated.final_path_view_mode, "degap");
        assert_eq!(updated.final_path_by_chr_json, "{}");

        let reloaded_project_one = get_project_assembly_view_state_with_connection(&mut conn, 1)?;
        assert_eq!(reloaded_project_one.support_dataset_id, Some(22));
        assert_eq!(
            reloaded_project_one.track_view_json,
            r#"{"supportDsCtgLen":10000,"minTickUnitKb":250,"maxTickCount":15,"alignmentLength":10000,"mapq":30}"#,
        );
        assert_eq!(
            reloaded_project_one.track_scroll_state_json,
            r#"{"viewportKey":"1:chr1:1909:22:10000:250:15:10000:30","scrollLeft":320}"#,
        );
        assert_eq!(
            reloaded_project_one.subview_track_scroll_state_json,
            r#"{"viewportKey":"1:chr1:primary:1909:support:1910","scrollLeft":180}"#,
        );
        assert_eq!(
            reloaded_project_one.support_mirrored_ctgs_json,
            r#"[{"datasetId":22,"assemblyCtgId":1909,"name":"Ctg1909"}]"#,
        );
        assert_eq!(
            reloaded_project_one.hidden_primary_ctg_ids_json,
            r#"[1909,1910]"#
        );
        assert_eq!(
            reloaded_project_one.hidden_primary_ctg_ids_by_chr_json,
            r#"{"Chr01":[1909],"Chr02":[1910]}"#
        );
        assert_eq!(
            reloaded_project_one.track_drag_offsets_json,
            r#"[{"trackRole":"primary","assemblyCtgId":1909,"offsetBp":120}]"#,
        );
        assert_eq!(
            reloaded_project_one.subview_track_drag_offsets_json,
            r#"[{"slot":"top","contigId":1909,"offsetBp":80}]"#,
        );
        assert_eq!(
            reloaded_project_one.subview_anchor_state_by_key_json,
            r#"{"2-contig|chr:Chr01|a|b":{"activeAnchors":[{"hitKey":"h1","edge":"left"}],"manualAnchors":[]}}"#,
        );
        assert_eq!(reloaded_project_one.final_path_view_mode, "degap");
        assert_eq!(reloaded_project_one.final_path_by_chr_json, "{}");

        let untouched_project_two = get_project_assembly_view_state_with_connection(&mut conn, 2)?;
        assert_eq!(untouched_project_two.project_id, 2);
        assert_eq!(untouched_project_two.support_dataset_id, None);
        assert_eq!(untouched_project_two.track_view_json, "{}");
        assert_eq!(untouched_project_two.track_scroll_state_json, "{}");
        assert_eq!(untouched_project_two.subview_track_scroll_state_json, "{}");
        assert_eq!(untouched_project_two.support_mirrored_ctgs_json, "[]");
        assert_eq!(untouched_project_two.hidden_primary_ctg_ids_json, "[]");
        assert_eq!(
            untouched_project_two.hidden_primary_ctg_ids_by_chr_json,
            "{}"
        );
        assert_eq!(untouched_project_two.track_drag_offsets_json, "[]");
        assert_eq!(untouched_project_two.subview_track_drag_offsets_json, "[]");
        assert_eq!(untouched_project_two.subview_anchor_state_by_key_json, "{}");
        assert_eq!(untouched_project_two.final_path_view_mode, "graph");
        assert_eq!(untouched_project_two.final_path_by_chr_json, "{}");
        Ok(())
    }

    #[test]
    fn project_assembly_view_state_persists_final_path_by_chr_per_project() -> Result<()> {
        let mut conn = Connection::open_in_memory()?;
        init_workspace_schema(&conn)?;
        seed_project(&conn, 1)?;
        seed_project(&conn, 2)?;

        let updated = update_project_assembly_view_state_with_connection(
            &mut conn,
            &UpdateProjectAssemblyViewStateParams {
                project_id: 1,
                support_dataset_id: None,
                track_view_json: "{}".to_string(),
                support_ds_ctg_len_rules_by_chr_json: "{}".to_string(),
                track_scroll_state_json: "{}".to_string(),
                subview_track_scroll_state_json: "{}".to_string(),
                support_mirrored_ctgs_json: "[]".to_string(),
                hidden_primary_ctg_ids_json: "[]".to_string(),
                hidden_primary_ctg_ids_by_chr_json: "{}".to_string(),
                track_drag_offsets_json: "[]".to_string(),
                subview_track_drag_offsets_json: "[]".to_string(),
                subview_anchor_state_by_key_json: "{}".to_string(),
                final_path_view_mode: "log".to_string(),
                final_path_by_chr_json: r#"{"Chr01":{"mode":"direct-ctg","chrName":"Chr01","assemblyCtgId":19,"ctgName":"flye_ctg19","totalLength":1800,"updatedAt":"1"}}"#.to_string(),
                degap_project_state_json: "{}".to_string(),
            },
        )?;

        assert_eq!(updated.final_path_view_mode, "log");
        assert_eq!(
            updated.final_path_by_chr_json,
            r#"{"Chr01":{"mode":"direct-ctg","chrName":"Chr01","assemblyCtgId":19,"ctgName":"flye_ctg19","totalLength":1800,"updatedAt":"1"}}"#,
        );

        let reloaded = get_project_assembly_view_state_with_connection(&mut conn, 1)?;
        assert_eq!(reloaded.final_path_view_mode, "log");
        assert_eq!(
            reloaded.final_path_by_chr_json,
            r#"{"Chr01":{"mode":"direct-ctg","chrName":"Chr01","assemblyCtgId":19,"ctgName":"flye_ctg19","totalLength":1800,"updatedAt":"1"}}"#,
        );

        let untouched = get_project_assembly_view_state_with_connection(&mut conn, 2)?;
        assert_eq!(untouched.final_path_view_mode, "graph");
        assert_eq!(untouched.final_path_by_chr_json, "{}");
        Ok(())
    }

    fn seed_project(conn: &Connection, project_id: i64) -> Result<()> {
        conn.execute(
            "INSERT INTO reference_genome (
                id, name, species_name, assembly_label, fasta_path, fai_path
            ) VALUES (?1, ?2, 'sp', 'v1', ?3, ?4)",
            params![
                project_id,
                format!("ref-{}", project_id),
                format!("ref-{}.fa", project_id),
                format!("ref-{}.fa.fai", project_id),
            ],
        )?;
        conn.execute(
            "INSERT INTO dataset (
                id, name, assembler, assembler_version, fasta_path, fai_path
            ) VALUES (?1, ?2, 'asm', NULL, ?3, ?4)",
            params![
                project_id,
                format!("ds-{}", project_id),
                format!("ds-{}.fa", project_id),
                format!("ds-{}.fa.fai", project_id),
            ],
        )?;
        conn.execute(
            "INSERT INTO project (
                id, name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, description, created_at, note
            ) VALUES (?1, ?2, 1, ?1, ?1, 0, NULL, '1', NULL)",
            params![project_id, format!("p{}", project_id)],
        )?;
        Ok(())
    }
}
