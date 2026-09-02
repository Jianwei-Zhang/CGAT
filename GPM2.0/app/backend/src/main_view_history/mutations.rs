use std::collections::BTreeSet;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Map, Value, json};

use super::snapshot::{capture_snapshot, reconcile_project_view_layout, snapshot_scope};
use super::types::{
    AssemblyCtgRow, DeletedAssemblyCtgRow, MainViewDeleteImpact,
    MainViewHistoryOperationDescriptor, PreparedMutation, ProjectViewLayoutScope,
    ProjectViewMirrorKey, ProjectViewTrackOffsetKey, SnapshotScope,
};

const INVALID_ACTION_CODE: &str = "MAIN_VIEW_HISTORY_INVALID_ACTION";
const INELIGIBLE_TARGET_CODE: &str = "MAIN_VIEW_HISTORY_INELIGIBLE_TARGET";

pub(super) fn prepare_editor_mutation(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    action: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    match action {
        "rename-ctg" => prepare_rename_ctg(conn, project_id, chr_name, args),
        "flip-ctg" => prepare_flip_ctg(conn, project_id, chr_name, args),
        "flip-seq" => prepare_flip_seq(conn, project_id, chr_name, args),
        "hide-seq" => prepare_seq_visibility(conn, project_id, chr_name, args, true),
        "show-seq" => prepare_seq_visibility(conn, project_id, chr_name, args, false),
        "set-end-type" => prepare_set_end_type(conn, project_id, chr_name, args),
        "delete-ctg" => prepare_batch_delete(
            conn,
            project_id,
            chr_name,
            &[required_i64(args, "assemblyCtgId")?],
        ),
        "restore-deleted-ctg" => prepare_restore_deleted_ctg(
            conn,
            project_id,
            chr_name,
            required_i64(args, "deletedCtgRecordId")?,
        ),
        _ => bail!("{INVALID_ACTION_CODE}: unsupported main-view editor action '{action}'"),
    }
}

pub(super) fn prepare_layout_mutation(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    action: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    match action {
        "drag-ctg" => prepare_drag_ctg(conn, project_id, chr_name, args),
        "create-mirror" => prepare_mirror_change(conn, project_id, chr_name, args, true),
        "delete-mirror" => prepare_mirror_change(conn, project_id, chr_name, args, false),
        _ => bail!("{INVALID_ACTION_CODE}: unsupported main-view layout action '{action}'"),
    }
}

fn prepare_drag_ctg(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let track_role = required_string(args, "trackRole")?.to_ascii_lowercase();
    let ctg_id = required_i64(args, "assemblyCtgId")?;
    let offset_bp = required_f64(args, "offsetBp")?;
    let row = load_ctg_target(conn, project_id, chr_name, ctg_id)?;
    let dataset_id = optional_positive_i64(args, "datasetId")?;
    let phased_track_id = optional_positive_i64(args, "phasedTrackId")?;
    let phased_track_item_id = optional_positive_i64(args, "phasedTrackItemId")?;
    let key = ProjectViewTrackOffsetKey {
        track_role: track_role.clone(),
        assembly_ctg_id: ctg_id,
        dataset_id: (track_role == "support").then_some(dataset_id).flatten(),
        phased_track_id: (track_role == "phased")
            .then_some(phased_track_id)
            .flatten(),
        phased_track_item_id: (track_role == "phased")
            .then_some(phased_track_item_id)
            .flatten(),
    };
    validate_drag_target(conn, project_id, chr_name, &row, &key)?;
    let scope = SnapshotScope {
        ctg_ids: vec![ctg_id],
        phased_track_ids: key.phased_track_id.into_iter().collect(),
        layout_scope: ProjectViewLayoutScope {
            track_offset_keys: vec![key],
            ..ProjectViewLayoutScope::default()
        },
        ..SnapshotScope::default()
    };
    let before = capture_snapshot(conn, project_id, &scope)?;
    let mut desired_layout = before.layout_state.clone();
    desired_layout.scoped_track_drag_offsets.clear();
    if offset_bp.abs() >= 0.01 {
        desired_layout.scoped_track_drag_offsets.push(json!({
            "trackRole": track_role,
            "assemblyCtgId": ctg_id,
            "datasetId": dataset_id,
            "phasedTrackId": phased_track_id,
            "phasedTrackItemId": phased_track_item_id,
            "offsetBp": round_layout_metric(offset_bp),
        }));
        if let Some(object) = desired_layout
            .scoped_track_drag_offsets
            .first_mut()
            .and_then(Value::as_object_mut)
        {
            object.retain(|_, value| !value.is_null());
        }
    }
    reconcile_project_view_layout(conn, project_id, &before.layout_scope, &desired_layout)?;
    finish_simple_mutation(
        conn,
        project_id,
        before,
        "drag-ctg",
        Some(row.name),
        vec![ctg_id],
        vec![],
    )
}

fn prepare_mirror_change(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
    create: bool,
) -> Result<PreparedMutation> {
    let dataset_id = required_i64(args, "datasetId")?;
    let ctg_id = required_i64(args, "assemblyCtgId")?;
    let row = load_ctg_target(conn, project_id, chr_name, ctg_id)?;
    let source_orient = validate_support_target(conn, project_id, &row, dataset_id)?;
    let key = ProjectViewMirrorKey {
        dataset_id,
        assembly_ctg_id: ctg_id,
    };
    let scope = SnapshotScope {
        ctg_ids: vec![ctg_id],
        layout_scope: ProjectViewLayoutScope {
            mirror_keys: vec![key],
            ..ProjectViewLayoutScope::default()
        },
        ..SnapshotScope::default()
    };
    let before = capture_snapshot(conn, project_id, &scope)?;
    let mut desired_layout = before.layout_state.clone();
    desired_layout.scoped_support_mirrors.clear();
    if create {
        let mut mirror_entry = args
            .get("mirrorEntry")
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: mirrorEntry must be a JSON object")
            })?;
        if mirror_entry.get("datasetId").and_then(Value::as_i64) != Some(dataset_id)
            || mirror_entry.get("assemblyCtgId").and_then(Value::as_i64) != Some(ctg_id)
        {
            bail!(
                "MAIN_VIEW_HISTORY_INVALID_REQUEST: mirrorEntry identity does not match the requested support ctg"
            );
        }
        let entry_chr = mirror_entry
            .get("chrName")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or("");
        if !entry_chr.is_empty() && entry_chr != chr_name {
            bail!(
                "{INELIGIBLE_TARGET_CODE}: mirrorEntry does not belong to chromosome '{chr_name}'"
            );
        }
        mirror_entry.insert("chrName".to_string(), Value::String(chr_name.to_string()));
        mirror_entry.insert("orient".to_string(), Value::String(source_orient));
        desired_layout
            .scoped_support_mirrors
            .push(Value::Object(mirror_entry));
    }
    reconcile_project_view_layout(conn, project_id, &before.layout_scope, &desired_layout)?;
    finish_simple_mutation(
        conn,
        project_id,
        before,
        if create {
            "create-mirror"
        } else {
            "delete-mirror"
        },
        Some(row.name),
        vec![ctg_id],
        vec![],
    )
}

pub(super) fn prepare_batch_delete(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    assembly_ctg_ids: &[i64],
) -> Result<PreparedMutation> {
    let rows = load_ctg_targets(conn, project_id, chr_name, assembly_ctg_ids)?;
    let target_ids = rows.iter().map(|row| row.id).collect::<Vec<_>>();
    let seq_ids = rows
        .iter()
        .map(|row| row.assembly_seq_id)
        .collect::<Vec<_>>();
    let deleted_record_ids = allocate_deleted_record_ids(conn, rows.len())?;
    let scope = SnapshotScope {
        ctg_ids: target_ids.clone(),
        seq_ids: seq_ids.clone(),
        deleted_record_ids: deleted_record_ids.clone(),
        dependency_ctg_ids: target_ids.clone(),
        include_view_state: true,
        ..SnapshotScope::default()
    };
    let before = capture_snapshot(conn, project_id, &scope)?;
    let deleted_at = now_timestamp_string();

    mark_project_view_references_unavailable(conn, project_id, &target_ids)?;
    for ctg_id in &target_ids {
        conn.execute(
            "UPDATE export_record SET assembly_ctg_id = NULL
             WHERE project_id = ?1 AND assembly_ctg_id = ?2",
            params![project_id, ctg_id],
        )?;
        conn.execute(
            "DELETE FROM phased_chr_track_item WHERE assembly_ctg_id = ?1",
            params![ctg_id],
        )?;
    }
    for (row, deleted_record_id) in rows.iter().zip(&deleted_record_ids) {
        conn.execute(
            "INSERT INTO deleted_assembly_ctg (
                id, project_id, assembly_ctg_id, assembly_seq_id, name,
                assigned_chr_name, chr_order, anchor_start, ref_orient,
                placement_mode, created_at, note, deleted_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
            params![
                deleted_record_id,
                row.project_id,
                row.id,
                row.assembly_seq_id,
                row.name,
                row.assigned_chr_name,
                row.chr_order,
                row.anchor_start,
                row.ref_orient,
                row.placement_mode,
                row.created_at,
                row.note,
                deleted_at,
            ],
        )?;
        conn.execute("DELETE FROM assembly_ctg WHERE id = ?1", params![row.id])?;
    }

    let after = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
    let target_name = (rows.len() == 1).then(|| rows[0].name.clone());
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: "delete-ctg".to_string(),
            target_count: rows.len() as i64,
            target_name,
        },
        changed: before != after,
        before,
        after,
        affected_ctg_ids: target_ids,
        affected_seq_ids: seq_ids,
    })
}

pub(super) fn inspect_delete_impact(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    assembly_ctg_ids: &[i64],
) -> Result<MainViewDeleteImpact> {
    let rows = load_ctg_targets(conn, project_id, chr_name, assembly_ctg_ids)?;
    let target_ids = rows.iter().map(|row| row.id).collect::<Vec<_>>();
    let snapshot = capture_snapshot(
        conn,
        project_id,
        &SnapshotScope {
            dependency_ctg_ids: target_ids.clone(),
            include_view_state: true,
            ..SnapshotScope::default()
        },
    )?;
    let target_set = target_ids.into_iter().collect::<BTreeSet<_>>();
    let final_path_reference_count = snapshot
        .view_state
        .as_ref()
        .map(|row| count_json_references(&row.final_path_by_chr_json, &target_set))
        .transpose()?
        .unwrap_or(0);
    let degap_reference_count = snapshot
        .view_state
        .as_ref()
        .map(|row| count_json_references(&row.degap_project_state_json, &target_set))
        .transpose()?
        .unwrap_or(0);
    Ok(MainViewDeleteImpact {
        ctg_count: rows.len() as i64,
        phased_item_count: snapshot
            .phased_items
            .iter()
            .filter(|row| target_set.contains(&row.assembly_ctg_id))
            .count() as i64,
        export_record_count: snapshot
            .export_records
            .iter()
            .filter(|row| {
                row.assembly_ctg_id
                    .is_some_and(|id| target_set.contains(&id))
            })
            .count() as i64,
        final_path_reference_count,
        degap_reference_count,
    })
}

fn prepare_rename_ctg(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let ctg_id = required_i64(args, "assemblyCtgId")?;
    let new_name = required_string(args, "newName")?;
    let row = load_ctg_target(conn, project_id, chr_name, ctg_id)?;
    let scope = target_scope(&row);
    let before = capture_snapshot(conn, project_id, &scope)?;
    if row.name != new_name {
        let conflict = conn
            .query_row(
                "SELECT id FROM assembly_ctg
                 WHERE project_id = ?1 AND name = ?2 AND id <> ?3",
                params![project_id, new_name, ctg_id],
                |query_row| query_row.get::<_, i64>(0),
            )
            .optional()?;
        if conflict.is_some() {
            bail!("MAIN_VIEW_HISTORY_NAME_CONFLICT: ctg name '{new_name}' already exists");
        }
        conn.execute(
            "UPDATE assembly_ctg SET name = ?1 WHERE id = ?2",
            params![new_name, ctg_id],
        )?;
    }
    finish_simple_mutation(
        conn,
        project_id,
        before,
        "rename-ctg",
        Some(row.name),
        vec![ctg_id],
        vec![],
    )
}

fn prepare_flip_ctg(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let ctg_id = required_i64(args, "assemblyCtgId")?;
    let row = load_ctg_target(conn, project_id, chr_name, ctg_id)?;
    let scope = target_scope(&row);
    let before = capture_snapshot(conn, project_id, &scope)?;
    let seq = before
        .seqs
        .first()
        .ok_or_else(|| anyhow!("{INELIGIBLE_TARGET_CODE}: assembly seq is missing"))?;
    conn.execute(
        "UPDATE assembly_seq
         SET orient = ?1,
             left_end_type = ?2,
             right_end_type = ?3
         WHERE id = ?4",
        params![
            flip_orient(&seq.orient)?,
            seq.right_end_type,
            seq.left_end_type,
            seq.id,
        ],
    )?;
    conn.execute(
        "UPDATE assembly_ctg
         SET ref_orient = ?1, placement_mode = 'manual'
         WHERE id = ?2",
        params![toggle_ref_orient(row.ref_orient.as_deref()), ctg_id],
    )?;
    finish_simple_mutation(
        conn,
        project_id,
        before,
        "flip-ctg",
        Some(row.name),
        vec![ctg_id],
        vec![row.assembly_seq_id],
    )
}

fn prepare_flip_seq(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let seq_id = required_i64(args, "assemblySeqId")?;
    let row = load_seq_target_ctg(conn, project_id, chr_name, seq_id)?;
    let before = capture_snapshot(conn, project_id, &target_scope(&row))?;
    let seq = before
        .seqs
        .first()
        .ok_or_else(|| anyhow!("{INELIGIBLE_TARGET_CODE}: assembly seq is missing"))?;
    conn.execute(
        "UPDATE assembly_seq
         SET orient = ?1, left_end_type = ?2, right_end_type = ?3
         WHERE id = ?4",
        params![
            flip_orient(&seq.orient)?,
            seq.right_end_type,
            seq.left_end_type,
            seq_id,
        ],
    )?;
    mark_ctg_manual_and_clear_ref(conn, row.id)?;
    finish_simple_mutation(
        conn,
        project_id,
        before,
        "flip-seq",
        Some(row.name),
        vec![row.id],
        vec![seq_id],
    )
}

fn prepare_seq_visibility(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
    hidden: bool,
) -> Result<PreparedMutation> {
    let seq_id = required_i64(args, "assemblySeqId")?;
    let row = load_seq_target_ctg(conn, project_id, chr_name, seq_id)?;
    let before = capture_snapshot(conn, project_id, &target_scope(&row))?;
    let current_hidden = before
        .seqs
        .first()
        .map(|seq| seq.hidden != 0)
        .unwrap_or(false);
    if current_hidden != hidden {
        conn.execute(
            "UPDATE assembly_seq SET hidden = ?1 WHERE id = ?2",
            params![i64::from(hidden), seq_id],
        )?;
        mark_ctg_manual_and_clear_ref(conn, row.id)?;
    }
    finish_simple_mutation(
        conn,
        project_id,
        before,
        if hidden { "hide-seq" } else { "show-seq" },
        Some(row.name),
        vec![row.id],
        vec![seq_id],
    )
}

fn prepare_set_end_type(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let seq_id = required_i64(args, "assemblySeqId")?;
    let left_end_type = normalize_end_type(&required_string(args, "leftEndType")?)?;
    let right_end_type = normalize_end_type(&required_string(args, "rightEndType")?)?;
    let row = load_seq_target_ctg(conn, project_id, chr_name, seq_id)?;
    let before = capture_snapshot(conn, project_id, &target_scope(&row))?;
    let seq = before
        .seqs
        .first()
        .ok_or_else(|| anyhow!("{INELIGIBLE_TARGET_CODE}: assembly seq is missing"))?;
    if seq.left_end_type != left_end_type || seq.right_end_type != right_end_type {
        conn.execute(
            "UPDATE assembly_seq
             SET left_end_type = ?1, right_end_type = ?2
             WHERE id = ?3",
            params![left_end_type, right_end_type, seq_id],
        )?;
        mark_ctg_manual_and_clear_ref(conn, row.id)?;
    }
    finish_simple_mutation(
        conn,
        project_id,
        before,
        "set-end-type",
        Some(row.name),
        vec![row.id],
        vec![seq_id],
    )
}

fn prepare_restore_deleted_ctg(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    deleted_record_id: i64,
) -> Result<PreparedMutation> {
    let deleted = conn
        .query_row(
            "SELECT id, project_id, assembly_ctg_id, assembly_seq_id, name,
                    assigned_chr_name, chr_order, anchor_start, ref_orient,
                    placement_mode, created_at, note, deleted_at
             FROM deleted_assembly_ctg
             WHERE project_id = ?1 AND id = ?2",
            params![project_id, deleted_record_id],
            |row| {
                Ok(DeletedAssemblyCtgRow {
                    id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_ctg_id: row.get(2)?,
                    assembly_seq_id: row.get(3)?,
                    name: row.get(4)?,
                    assigned_chr_name: row.get(5)?,
                    chr_order: row.get(6)?,
                    anchor_start: row.get(7)?,
                    ref_orient: row.get(8)?,
                    placement_mode: row.get(9)?,
                    created_at: row.get(10)?,
                    note: row.get(11)?,
                    deleted_at: row.get(12)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| anyhow!("{INELIGIBLE_TARGET_CODE}: deleted ctg record does not exist"))?;
    if deleted.assigned_chr_name.as_deref() != Some(chr_name) {
        bail!("{INELIGIBLE_TARGET_CODE}: deleted ctg does not belong to chromosome '{chr_name}'");
    }
    let scope = SnapshotScope {
        ctg_ids: vec![deleted.assembly_ctg_id],
        seq_ids: vec![deleted.assembly_seq_id],
        deleted_record_ids: vec![deleted.id],
        dependency_ctg_ids: vec![deleted.assembly_ctg_id],
        include_view_state: true,
        ..SnapshotScope::default()
    };
    let before = capture_snapshot(conn, project_id, &scope)?;
    if !before.ctgs.is_empty() {
        bail!("MAIN_VIEW_HISTORY_RESTORE_CONFLICT: assembly ctg id already exists");
    }
    if before.seqs.len() != 1 {
        bail!("MAIN_VIEW_HISTORY_RESTORE_CONFLICT: assembly seq is missing");
    }
    let name_conflict = conn
        .query_row(
            "SELECT id FROM assembly_ctg WHERE project_id = ?1 AND name = ?2",
            params![project_id, deleted.name],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    if name_conflict.is_some() {
        bail!(
            "MAIN_VIEW_HISTORY_NAME_CONFLICT: ctg name '{}' already exists",
            deleted.name
        );
    }
    conn.execute(
        "INSERT INTO assembly_ctg (
            id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
            anchor_start, ref_orient, placement_mode, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
        params![
            deleted.assembly_ctg_id,
            deleted.project_id,
            deleted.assembly_seq_id,
            deleted.name,
            deleted.assigned_chr_name,
            deleted.chr_order,
            deleted.anchor_start,
            deleted.ref_orient,
            deleted.placement_mode,
            deleted.created_at,
            deleted.note,
        ],
    )?;
    conn.execute(
        "DELETE FROM deleted_assembly_ctg WHERE id = ?1",
        params![deleted.id],
    )?;
    let after = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: "restore-deleted-ctg".to_string(),
            target_count: 1,
            target_name: Some(deleted.name),
        },
        changed: before != after,
        before,
        after,
        affected_ctg_ids: vec![deleted.assembly_ctg_id],
        affected_seq_ids: vec![deleted.assembly_seq_id],
    })
}

fn validate_drag_target(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    row: &AssemblyCtgRow,
    key: &ProjectViewTrackOffsetKey,
) -> Result<()> {
    match key.track_role.as_str() {
        "primary" => {
            let (source_dataset_id, _): (i64, String) = load_ctg_dataset_and_orient(conn, row.id)?;
            let primary_dataset_id: i64 = conn.query_row(
                "SELECT primary_dataset_id FROM project WHERE id = ?1",
                params![project_id],
                |query_row| query_row.get(0),
            )?;
            if source_dataset_id != primary_dataset_id {
                bail!(
                    "{INELIGIBLE_TARGET_CODE}: assembly ctg id {} is not on the primary track",
                    row.id
                );
            }
            if key.dataset_id.is_some()
                || key.phased_track_id.is_some()
                || key.phased_track_item_id.is_some()
            {
                bail!(
                    "MAIN_VIEW_HISTORY_INVALID_REQUEST: primary drag does not accept support or phased identity fields"
                );
            }
        }
        "support" => {
            let dataset_id = key.dataset_id.ok_or_else(|| {
                anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: support drag requires datasetId")
            })?;
            validate_support_target(conn, project_id, row, dataset_id)?;
            if key.phased_track_id.is_some() || key.phased_track_item_id.is_some() {
                bail!(
                    "MAIN_VIEW_HISTORY_INVALID_REQUEST: support drag does not accept phased identity fields"
                );
            }
        }
        "phased" => {
            if key.dataset_id.is_some() {
                bail!("MAIN_VIEW_HISTORY_INVALID_REQUEST: phased drag does not accept datasetId");
            }
            let track_id = key.phased_track_id.ok_or_else(|| {
                anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: phased drag requires phasedTrackId")
            })?;
            let item_id = key.phased_track_item_id.ok_or_else(|| {
                anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: phased drag requires phasedTrackItemId")
            })?;
            let exists = conn
                .query_row(
                    "SELECT 1
                     FROM phased_chr_track t
                     JOIN phased_chr_track_item i ON i.phased_track_id = t.id
                     WHERE t.id = ?1
                       AND i.id = ?2
                       AND i.assembly_ctg_id = ?3
                       AND t.project_id = ?4
                       AND t.parent_chr_name = ?5",
                    params![track_id, item_id, row.id, project_id, chr_name],
                    |_| Ok(()),
                )
                .optional()?
                .is_some();
            if !exists {
                bail!(
                    "{INELIGIBLE_TARGET_CODE}: phased track item does not match the requested project, chromosome, and ctg"
                );
            }
        }
        _ => bail!(
            "MAIN_VIEW_HISTORY_INVALID_REQUEST: trackRole must be primary, support, or phased"
        ),
    }
    Ok(())
}

fn validate_support_target(
    conn: &Connection,
    project_id: i64,
    row: &AssemblyCtgRow,
    dataset_id: i64,
) -> Result<String> {
    let (source_dataset_id, orient) = load_ctg_dataset_and_orient(conn, row.id)?;
    let is_support = conn
        .query_row(
            "SELECT 1 FROM project_dataset
             WHERE project_id = ?1 AND dataset_id = ?2 AND dataset_role = 'support'",
            params![project_id, dataset_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if source_dataset_id != dataset_id || !is_support {
        bail!(
            "{INELIGIBLE_TARGET_CODE}: assembly ctg id {} does not belong to support dataset id {dataset_id}",
            row.id
        );
    }
    Ok(orient)
}

fn load_ctg_dataset_and_orient(conn: &Connection, ctg_id: i64) -> Result<(i64, String)> {
    conn.query_row(
        "SELECT source.dataset_id, seq.orient
         FROM assembly_ctg ctg
         JOIN assembly_seq seq ON seq.id = ctg.assembly_seq_id
         JOIN source_seq source ON source.id = seq.source_seq_id
         WHERE ctg.id = ?1",
        params![ctg_id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )
    .context("failed to resolve main-view layout target dataset")
}

fn finish_simple_mutation(
    conn: &Connection,
    project_id: i64,
    before: super::types::DatabaseSnapshot,
    kind: &str,
    target_name: Option<String>,
    affected_ctg_ids: Vec<i64>,
    affected_seq_ids: Vec<i64>,
) -> Result<PreparedMutation> {
    let after = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: kind.to_string(),
            target_count: 1,
            target_name,
        },
        changed: before != after,
        before,
        after,
        affected_ctg_ids,
        affected_seq_ids,
    })
}

fn target_scope(row: &AssemblyCtgRow) -> SnapshotScope {
    SnapshotScope {
        ctg_ids: vec![row.id],
        seq_ids: vec![row.assembly_seq_id],
        ..SnapshotScope::default()
    }
}

fn load_ctg_targets(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    assembly_ctg_ids: &[i64],
) -> Result<Vec<AssemblyCtgRow>> {
    let mut ids = assembly_ctg_ids
        .iter()
        .copied()
        .filter(|value| *value > 0)
        .collect::<Vec<_>>();
    ids.sort_unstable();
    ids.dedup();
    if ids.is_empty() {
        bail!("{INELIGIBLE_TARGET_CODE}: at least one assembly ctg id is required");
    }
    ids.into_iter()
        .map(|id| load_ctg_target(conn, project_id, chr_name, id))
        .collect()
}

fn load_ctg_target(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    ctg_id: i64,
) -> Result<AssemblyCtgRow> {
    let row = conn
        .query_row(
            "SELECT id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
                    anchor_start, ref_orient, placement_mode, created_at, note
             FROM assembly_ctg WHERE project_id = ?1 AND id = ?2",
            params![project_id, ctg_id],
            |row| {
                Ok(AssemblyCtgRow {
                    id: row.get(0)?,
                    project_id: row.get(1)?,
                    assembly_seq_id: row.get(2)?,
                    name: row.get(3)?,
                    assigned_chr_name: row.get(4)?,
                    chr_order: row.get(5)?,
                    anchor_start: row.get(6)?,
                    ref_orient: row.get(7)?,
                    placement_mode: row.get(8)?,
                    created_at: row.get(9)?,
                    note: row.get(10)?,
                })
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow!("{INELIGIBLE_TARGET_CODE}: assembly ctg id {ctg_id} does not exist")
        })?;
    if row.assigned_chr_name.as_deref() != Some(chr_name) {
        bail!(
            "{INELIGIBLE_TARGET_CODE}: assembly ctg id {ctg_id} does not belong to chromosome '{chr_name}'"
        );
    }
    Ok(row)
}

fn load_seq_target_ctg(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    seq_id: i64,
) -> Result<AssemblyCtgRow> {
    let ctg_id = conn
        .query_row(
            "SELECT id FROM assembly_ctg
             WHERE project_id = ?1 AND assembly_seq_id = ?2",
            params![project_id, seq_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?
        .ok_or_else(|| {
            anyhow!("{INELIGIBLE_TARGET_CODE}: assembly seq id {seq_id} is not in a ctg")
        })?;
    load_ctg_target(conn, project_id, chr_name, ctg_id)
}

fn allocate_deleted_record_ids(conn: &Connection, count: usize) -> Result<Vec<i64>> {
    let max_id: i64 = conn.query_row(
        "SELECT COALESCE(MAX(id), 0) FROM deleted_assembly_ctg",
        [],
        |row| row.get(0),
    )?;
    Ok((1..=count).map(|offset| max_id + offset as i64).collect())
}

fn mark_project_view_references_unavailable(
    conn: &Connection,
    project_id: i64,
    target_ids: &[i64],
) -> Result<()> {
    let Some((final_path_json, degap_json)) = conn
        .query_row(
            "SELECT final_path_by_chr_json, degap_project_state_json
             FROM project_assembly_view_state WHERE project_id = ?1",
            params![project_id],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()?
    else {
        return Ok(());
    };
    let targets = target_ids.iter().copied().collect::<BTreeSet<_>>();
    let mut final_path: Value = serde_json::from_str(&final_path_json).map_err(|error| {
        anyhow!("MAIN_VIEW_HISTORY_DEPENDENCY_INVALID: invalid Final Path state: {error}")
    })?;
    let mut degap: Value = serde_json::from_str(&degap_json).map_err(|error| {
        anyhow!("MAIN_VIEW_HISTORY_DEPENDENCY_INVALID: invalid DEGAP state: {error}")
    })?;
    let final_count = mark_json_references(&mut final_path, &targets);
    let degap_count = mark_json_references(&mut degap, &targets);
    if final_count == 0 && degap_count == 0 {
        return Ok(());
    }
    conn.execute(
        "UPDATE project_assembly_view_state
         SET final_path_by_chr_json = ?1,
             degap_project_state_json = ?2,
             updated_at = ?3
         WHERE project_id = ?4",
        params![
            serde_json::to_string(&final_path)?,
            serde_json::to_string(&degap)?,
            now_timestamp_string(),
            project_id,
        ],
    )?;
    Ok(())
}

fn count_json_references(raw: &str, targets: &BTreeSet<i64>) -> Result<i64> {
    let value: Value = serde_json::from_str(raw).map_err(|error| {
        anyhow!("MAIN_VIEW_HISTORY_DEPENDENCY_INVALID: invalid persisted JSON: {error}")
    })?;
    Ok(count_value_references(&value, targets))
}

fn count_value_references(value: &Value, targets: &BTreeSet<i64>) -> i64 {
    match value {
        Value::Array(items) => items
            .iter()
            .map(|item| count_value_references(item, targets))
            .sum(),
        Value::Object(object) => {
            let direct = ["assemblyCtgId", "assembly_ctg_id"]
                .iter()
                .filter_map(|key| object.get(*key).and_then(Value::as_i64))
                .filter(|id| targets.contains(id))
                .count() as i64;
            direct
                + object
                    .values()
                    .map(|item| count_value_references(item, targets))
                    .sum::<i64>()
        }
        _ => 0,
    }
}

fn mark_json_references(value: &mut Value, targets: &BTreeSet<i64>) -> i64 {
    match value {
        Value::Array(items) => items
            .iter_mut()
            .map(|item| mark_json_references(item, targets))
            .sum(),
        Value::Object(object) => mark_object_references(object, targets),
        _ => 0,
    }
}

fn mark_object_references(object: &mut Map<String, Value>, targets: &BTreeSet<i64>) -> i64 {
    let mut count = 0_i64;
    for (key, marker_key) in [
        ("assemblyCtgId", "historyDeletedAssemblyCtgId"),
        ("assembly_ctg_id", "history_deleted_assembly_ctg_id"),
    ] {
        let target = object.get(key).and_then(Value::as_i64);
        if let Some(target_id) = target.filter(|id| targets.contains(id)) {
            object.insert(key.to_string(), Value::Null);
            object.insert(marker_key.to_string(), Value::from(target_id));
            count += 1;
        }
    }
    let keys = object.keys().cloned().collect::<Vec<_>>();
    for key in keys {
        if key == "historyDeletedAssemblyCtgId" || key == "history_deleted_assembly_ctg_id" {
            continue;
        }
        if let Some(child) = object.get_mut(&key) {
            count += mark_json_references(child, targets);
        }
    }
    count
}

fn required_i64(args: &Value, field: &str) -> Result<i64> {
    let value = args
        .get(field)
        .and_then(Value::as_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: {field} must be a positive integer")
        })?;
    Ok(value)
}

fn optional_positive_i64(args: &Value, field: &str) -> Result<Option<i64>> {
    let Some(value) = args.get(field) else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(None);
    }
    value
        .as_i64()
        .filter(|value| *value > 0)
        .map(Some)
        .ok_or_else(|| {
            anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: {field} must be a positive integer")
        })
}

fn required_f64(args: &Value, field: &str) -> Result<f64> {
    args.get(field)
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: {field} must be a finite number")
        })
}

fn round_layout_metric(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn required_string(args: &Value, field: &str) -> Result<String> {
    let value = args
        .get(field)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| anyhow!("MAIN_VIEW_HISTORY_INVALID_REQUEST: {field} must not be blank"))?;
    Ok(value.to_string())
}

fn normalize_end_type(value: &str) -> Result<String> {
    let normalized = value.trim().to_ascii_lowercase();
    if ["normal", "gap", "telomere"].contains(&normalized.as_str()) {
        Ok(normalized)
    } else {
        bail!("MAIN_VIEW_HISTORY_INVALID_REQUEST: invalid end type '{value}'")
    }
}

fn flip_orient(value: &str) -> Result<&'static str> {
    match value {
        "+" => Ok("-"),
        "-" => Ok("+"),
        _ => bail!("MAIN_VIEW_HISTORY_STATE_INVALID: unsupported orient '{value}'"),
    }
}

fn toggle_ref_orient(value: Option<&str>) -> Option<&'static str> {
    match value {
        Some("+") => Some("-"),
        Some("-") => Some("+"),
        _ => None,
    }
}

fn mark_ctg_manual_and_clear_ref(conn: &Connection, ctg_id: i64) -> Result<()> {
    conn.execute(
        "UPDATE assembly_ctg
         SET ref_orient = NULL, placement_mode = 'manual'
         WHERE id = ?1",
        params![ctg_id],
    )?;
    Ok(())
}

fn now_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
        .to_string()
}
