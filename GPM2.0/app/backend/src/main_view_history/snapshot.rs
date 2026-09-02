use std::collections::BTreeSet;

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::Value;

use super::now_timestamp_string;
use super::types::{
    AssemblyCtgRow, AssemblySeqRow, DatabaseSnapshot, DeletedAssemblyCtgRow, ExportRecordRow,
    PhasedTrackItemRow, PhasedTrackRow, ProjectViewDependencyRow, ProjectViewLayoutScope,
    ProjectViewLayoutSnapshot, ProjectViewMirrorKey, ProjectViewTrackOffsetKey, SnapshotScope,
};

pub(super) const HISTORY_CONFLICT_CODE: &str = "MAIN_VIEW_HISTORY_CONFLICT";

pub(super) fn is_history_conflict(error: &anyhow::Error) -> bool {
    format!("{error:#}").contains(HISTORY_CONFLICT_CODE)
}

pub(super) fn snapshot_scope(snapshot: &DatabaseSnapshot) -> SnapshotScope {
    SnapshotScope {
        ctg_ids: snapshot.ctg_ids.clone(),
        seq_ids: snapshot.seq_ids.clone(),
        deleted_record_ids: snapshot.deleted_record_ids.clone(),
        dependency_ctg_ids: snapshot.dependency_ctg_ids.clone(),
        phased_track_ids: snapshot.phased_track_ids.clone(),
        export_record_ids: snapshot.export_record_ids.clone(),
        include_view_state: snapshot.include_view_state,
        layout_scope: snapshot.layout_scope.clone(),
    }
}

pub(super) fn merge_snapshot_scopes<'a>(
    snapshots: impl IntoIterator<Item = &'a DatabaseSnapshot>,
) -> SnapshotScope {
    let mut scope = SnapshotScope::default();
    for snapshot in snapshots {
        scope.ctg_ids.extend(snapshot.ctg_ids.iter().copied());
        scope.seq_ids.extend(snapshot.seq_ids.iter().copied());
        scope
            .deleted_record_ids
            .extend(snapshot.deleted_record_ids.iter().copied());
        scope
            .dependency_ctg_ids
            .extend(snapshot.dependency_ctg_ids.iter().copied());
        scope
            .phased_track_ids
            .extend(snapshot.phased_track_ids.iter().copied());
        scope
            .export_record_ids
            .extend(snapshot.export_record_ids.iter().copied());
        scope.include_view_state |= snapshot.include_view_state;
        scope
            .layout_scope
            .track_offset_keys
            .extend(snapshot.layout_scope.track_offset_keys.iter().cloned());
        scope
            .layout_scope
            .mirror_keys
            .extend(snapshot.layout_scope.mirror_keys.iter().cloned());
    }
    normalize_scope(&mut scope);
    scope
}

pub(super) fn capture_snapshot(
    conn: &Connection,
    project_id: i64,
    scope: &SnapshotScope,
) -> Result<DatabaseSnapshot> {
    let mut resolved_scope = scope.clone();
    normalize_scope(&mut resolved_scope);
    discover_dependency_scopes(conn, project_id, &mut resolved_scope)?;

    let mut ctgs = Vec::new();
    for id in &resolved_scope.ctg_ids {
        if let Some(row) = load_ctg(conn, project_id, *id)? {
            ctgs.push(row);
        }
    }

    let mut seqs = Vec::new();
    for id in &resolved_scope.seq_ids {
        if let Some(row) = load_seq(conn, project_id, *id)? {
            seqs.push(row);
        }
    }

    let mut deleted_ctgs = Vec::new();
    for id in &resolved_scope.deleted_record_ids {
        if let Some(row) = load_deleted_ctg(conn, project_id, *id)? {
            deleted_ctgs.push(row);
        }
    }

    let mut phased_tracks = Vec::new();
    let mut phased_items = Vec::new();
    for id in &resolved_scope.phased_track_ids {
        if let Some(row) = load_phased_track(conn, project_id, *id)? {
            phased_tracks.push(row);
        }
        phased_items.extend(load_phased_track_items(conn, *id)?);
    }

    let mut export_records = Vec::new();
    for id in &resolved_scope.export_record_ids {
        if let Some(row) = load_export_record(conn, project_id, *id)? {
            export_records.push(row);
        }
    }

    let view_state = if resolved_scope.include_view_state {
        load_project_view_dependency(conn, project_id)?
    } else {
        None
    };
    let layout_state = capture_project_view_layout(conn, project_id, &resolved_scope.layout_scope)?;

    Ok(DatabaseSnapshot {
        ctg_ids: resolved_scope.ctg_ids,
        ctgs,
        seq_ids: resolved_scope.seq_ids,
        seqs,
        deleted_record_ids: resolved_scope.deleted_record_ids,
        deleted_ctgs,
        dependency_ctg_ids: resolved_scope.dependency_ctg_ids,
        phased_track_ids: resolved_scope.phased_track_ids,
        phased_tracks,
        phased_items,
        export_record_ids: resolved_scope.export_record_ids,
        export_records,
        include_view_state: resolved_scope.include_view_state,
        view_state,
        layout_scope: resolved_scope.layout_scope,
        layout_state,
    })
}

pub(super) fn validate_snapshot(
    conn: &Connection,
    project_id: i64,
    expected: &DatabaseSnapshot,
) -> Result<()> {
    let actual = capture_snapshot(conn, project_id, &snapshot_scope(expected))?;
    if actual != *expected {
        bail!(
            "{HISTORY_CONFLICT_CODE}: current database state no longer matches the recorded history precondition"
        );
    }
    Ok(())
}

pub(super) fn apply_snapshot(
    conn: &Connection,
    project_id: i64,
    expected: &DatabaseSnapshot,
    desired: &DatabaseSnapshot,
) -> Result<()> {
    validate_snapshot(conn, project_id, expected)?;
    validate_desired_names(conn, project_id, desired)?;

    for row in &desired.seqs {
        let updated = conn.execute(
            "UPDATE assembly_seq
             SET project_id = ?1,
                 source_seq_id = ?2,
                 instance_key = ?3,
                 orient = ?4,
                 source_start = ?5,
                 source_end = ?6,
                 left_end_type = ?7,
                 right_end_type = ?8,
                 hidden = ?9,
                 created_at = ?10,
                 note = ?11
             WHERE id = ?12",
            params![
                row.project_id,
                row.source_seq_id,
                row.instance_key,
                row.orient,
                row.source_start,
                row.source_end,
                row.left_end_type,
                row.right_end_type,
                row.hidden,
                row.created_at,
                row.note,
                row.id,
            ],
        )?;
        if updated != 1 {
            bail!(
                "{HISTORY_CONFLICT_CODE}: assembly_seq_id {} cannot be restored",
                row.id
            );
        }
    }

    for track_id in &expected.phased_track_ids {
        conn.execute(
            "DELETE FROM phased_chr_track_item WHERE phased_track_id = ?1",
            params![track_id],
        )?;
    }
    for record in &expected.export_records {
        conn.execute(
            "UPDATE export_record SET assembly_ctg_id = NULL WHERE id = ?1",
            params![record.id],
        )?;
    }

    let desired_ctg_ids = desired
        .ctgs
        .iter()
        .map(|row| row.id)
        .collect::<BTreeSet<_>>();
    for row in &expected.ctgs {
        if desired_ctg_ids.contains(&row.id) {
            let temporary_name = resolve_temporary_name(conn, project_id, row.id)?;
            conn.execute(
                "UPDATE assembly_ctg SET name = ?1 WHERE id = ?2",
                params![temporary_name, row.id],
            )?;
        }
    }
    for ctg_id in &desired.ctg_ids {
        if !desired_ctg_ids.contains(ctg_id) {
            conn.execute("DELETE FROM assembly_ctg WHERE id = ?1", params![ctg_id])?;
        }
    }
    for row in &desired.ctgs {
        let exists = conn
            .query_row(
                "SELECT 1 FROM assembly_ctg WHERE id = ?1",
                params![row.id],
                |_| Ok(()),
            )
            .optional()?
            .is_some();
        if exists {
            conn.execute(
                "UPDATE assembly_ctg
                 SET project_id = ?1,
                     assembly_seq_id = ?2,
                     name = ?3,
                     assigned_chr_name = ?4,
                     chr_order = ?5,
                     anchor_start = ?6,
                     ref_orient = ?7,
                     placement_mode = ?8,
                     created_at = ?9,
                     note = ?10
                 WHERE id = ?11",
                params![
                    row.project_id,
                    row.assembly_seq_id,
                    row.name,
                    row.assigned_chr_name,
                    row.chr_order,
                    row.anchor_start,
                    row.ref_orient,
                    row.placement_mode,
                    row.created_at,
                    row.note,
                    row.id,
                ],
            )?;
        } else {
            conn.execute(
                "INSERT INTO assembly_ctg (
                    id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
                    anchor_start, ref_orient, placement_mode, created_at, note
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
                params![
                    row.id,
                    row.project_id,
                    row.assembly_seq_id,
                    row.name,
                    row.assigned_chr_name,
                    row.chr_order,
                    row.anchor_start,
                    row.ref_orient,
                    row.placement_mode,
                    row.created_at,
                    row.note,
                ],
            )?;
        }
    }

    for record_id in &desired.deleted_record_ids {
        conn.execute(
            "DELETE FROM deleted_assembly_ctg WHERE id = ?1",
            params![record_id],
        )?;
    }
    for row in &desired.deleted_ctgs {
        conn.execute(
            "INSERT INTO deleted_assembly_ctg (
                id, project_id, assembly_ctg_id, assembly_seq_id, name,
                assigned_chr_name, chr_order, anchor_start, ref_orient,
                placement_mode, created_at, note, deleted_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
            params![
                row.id,
                row.project_id,
                row.assembly_ctg_id,
                row.assembly_seq_id,
                row.name,
                row.assigned_chr_name,
                row.chr_order,
                row.anchor_start,
                row.ref_orient,
                row.placement_mode,
                row.created_at,
                row.note,
                row.deleted_at,
            ],
        )?;
    }

    for row in &desired.export_records {
        conn.execute(
            "UPDATE export_record SET assembly_ctg_id = ?1 WHERE id = ?2",
            params![row.assembly_ctg_id, row.id],
        )?;
    }
    for row in &desired.phased_items {
        conn.execute(
            "INSERT INTO phased_chr_track_item (
                id, phased_track_id, assembly_ctg_id, display_order,
                gap_before_px, orient, created_at, note
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                row.id,
                row.phased_track_id,
                row.assembly_ctg_id,
                row.display_order,
                row.gap_before_px,
                row.orient,
                row.created_at,
                row.note,
            ],
        )?;
    }

    if desired.include_view_state {
        reconcile_project_view_dependency(conn, project_id, desired.view_state.as_ref())?;
    }
    if !desired.layout_scope.track_offset_keys.is_empty()
        || !desired.layout_scope.mirror_keys.is_empty()
    {
        reconcile_project_view_layout(
            conn,
            project_id,
            &desired.layout_scope,
            &desired.layout_state,
        )?;
    }
    Ok(())
}

fn normalize_scope(scope: &mut SnapshotScope) {
    normalize_ids(&mut scope.ctg_ids);
    normalize_ids(&mut scope.seq_ids);
    normalize_ids(&mut scope.deleted_record_ids);
    normalize_ids(&mut scope.dependency_ctg_ids);
    normalize_ids(&mut scope.phased_track_ids);
    normalize_ids(&mut scope.export_record_ids);
    scope.layout_scope.track_offset_keys.sort();
    scope.layout_scope.track_offset_keys.dedup();
    scope.layout_scope.mirror_keys.sort();
    scope.layout_scope.mirror_keys.dedup();
}

fn normalize_ids(ids: &mut Vec<i64>) {
    ids.retain(|value| *value > 0);
    ids.sort_unstable();
    ids.dedup();
}

fn discover_dependency_scopes(
    conn: &Connection,
    project_id: i64,
    scope: &mut SnapshotScope,
) -> Result<()> {
    for ctg_id in &scope.dependency_ctg_ids {
        let mut stmt = conn.prepare(
            "SELECT DISTINCT t.id
             FROM phased_chr_track t
             JOIN phased_chr_track_item i ON i.phased_track_id = t.id
             WHERE t.project_id = ?1 AND i.assembly_ctg_id = ?2",
        )?;
        scope.phased_track_ids.extend(
            stmt.query_map(params![project_id, ctg_id], |row| row.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?,
        );

        let mut export_stmt = conn.prepare(
            "SELECT id FROM export_record WHERE project_id = ?1 AND assembly_ctg_id = ?2",
        )?;
        scope.export_record_ids.extend(
            export_stmt
                .query_map(params![project_id, ctg_id], |row| row.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?,
        );
    }
    normalize_ids(&mut scope.phased_track_ids);
    normalize_ids(&mut scope.export_record_ids);
    Ok(())
}

fn load_ctg(conn: &Connection, project_id: i64, id: i64) -> Result<Option<AssemblyCtgRow>> {
    conn.query_row(
        "SELECT id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
                anchor_start, ref_orient, placement_mode, created_at, note
         FROM assembly_ctg WHERE project_id = ?1 AND id = ?2",
        params![project_id, id],
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
    .optional()
    .context("failed to capture assembly ctg history state")
}

fn load_seq(conn: &Connection, project_id: i64, id: i64) -> Result<Option<AssemblySeqRow>> {
    conn.query_row(
        "SELECT id, project_id, source_seq_id, instance_key, orient, source_start,
                source_end, left_end_type, right_end_type, hidden, created_at, note
         FROM assembly_seq WHERE project_id = ?1 AND id = ?2",
        params![project_id, id],
        |row| {
            Ok(AssemblySeqRow {
                id: row.get(0)?,
                project_id: row.get(1)?,
                source_seq_id: row.get(2)?,
                instance_key: row.get(3)?,
                orient: row.get(4)?,
                source_start: row.get(5)?,
                source_end: row.get(6)?,
                left_end_type: row.get(7)?,
                right_end_type: row.get(8)?,
                hidden: row.get(9)?,
                created_at: row.get(10)?,
                note: row.get(11)?,
            })
        },
    )
    .optional()
    .context("failed to capture assembly seq history state")
}

fn load_deleted_ctg(
    conn: &Connection,
    project_id: i64,
    id: i64,
) -> Result<Option<DeletedAssemblyCtgRow>> {
    conn.query_row(
        "SELECT id, project_id, assembly_ctg_id, assembly_seq_id, name,
                assigned_chr_name, chr_order, anchor_start, ref_orient,
                placement_mode, created_at, note, deleted_at
         FROM deleted_assembly_ctg WHERE project_id = ?1 AND id = ?2",
        params![project_id, id],
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
    .optional()
    .context("failed to capture deleted ctg history state")
}

fn load_phased_track(
    conn: &Connection,
    project_id: i64,
    id: i64,
) -> Result<Option<PhasedTrackRow>> {
    conn.query_row(
        "SELECT id, project_id, parent_chr_name, haplotype_key, label,
                display_order, created_at, note
         FROM phased_chr_track WHERE project_id = ?1 AND id = ?2",
        params![project_id, id],
        |row| {
            Ok(PhasedTrackRow {
                id: row.get(0)?,
                project_id: row.get(1)?,
                parent_chr_name: row.get(2)?,
                haplotype_key: row.get(3)?,
                label: row.get(4)?,
                display_order: row.get(5)?,
                created_at: row.get(6)?,
                note: row.get(7)?,
            })
        },
    )
    .optional()
    .context("failed to capture phased track history state")
}

fn load_phased_track_items(conn: &Connection, track_id: i64) -> Result<Vec<PhasedTrackItemRow>> {
    let mut stmt = conn.prepare(
        "SELECT id, phased_track_id, assembly_ctg_id, display_order,
                gap_before_px, orient, created_at, note
         FROM phased_chr_track_item
         WHERE phased_track_id = ?1
         ORDER BY id",
    )?;
    stmt.query_map(params![track_id], |row| {
        Ok(PhasedTrackItemRow {
            id: row.get(0)?,
            phased_track_id: row.get(1)?,
            assembly_ctg_id: row.get(2)?,
            display_order: row.get(3)?,
            gap_before_px: row.get(4)?,
            orient: row.get(5)?,
            created_at: row.get(6)?,
            note: row.get(7)?,
        })
    })?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to capture phased track item history state")
}

fn load_export_record(
    conn: &Connection,
    project_id: i64,
    id: i64,
) -> Result<Option<ExportRecordRow>> {
    conn.query_row(
        "SELECT id, project_id, export_type, reference_chr_id, assembly_ctg_id,
                output_path, created_at, note
         FROM export_record WHERE project_id = ?1 AND id = ?2",
        params![project_id, id],
        |row| {
            Ok(ExportRecordRow {
                id: row.get(0)?,
                project_id: row.get(1)?,
                export_type: row.get(2)?,
                reference_chr_id: row.get(3)?,
                assembly_ctg_id: row.get(4)?,
                output_path: row.get(5)?,
                created_at: row.get(6)?,
                note: row.get(7)?,
            })
        },
    )
    .optional()
    .context("failed to capture export record history state")
}

fn load_project_view_dependency(
    conn: &Connection,
    project_id: i64,
) -> Result<Option<ProjectViewDependencyRow>> {
    conn.query_row(
        "SELECT project_id, final_path_by_chr_json, degap_project_state_json
         FROM project_assembly_view_state WHERE project_id = ?1",
        params![project_id],
        |row| {
            Ok(ProjectViewDependencyRow {
                project_id: row.get(0)?,
                final_path_by_chr_json: row.get(1)?,
                degap_project_state_json: row.get(2)?,
            })
        },
    )
    .optional()
    .context("failed to capture project view dependency history state")
}

fn capture_project_view_layout(
    conn: &Connection,
    project_id: i64,
    scope: &ProjectViewLayoutScope,
) -> Result<ProjectViewLayoutSnapshot> {
    if scope.track_offset_keys.is_empty() && scope.mirror_keys.is_empty() {
        return Ok(ProjectViewLayoutSnapshot::default());
    }
    let row = conn
        .query_row(
            "SELECT track_drag_offsets_json, support_mirrored_ctgs_json
             FROM project_assembly_view_state WHERE project_id = ?1",
            params![project_id],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()
        .context("failed to capture project view layout history state")?;
    let Some((track_offsets_json, mirrors_json)) = row else {
        return Ok(ProjectViewLayoutSnapshot::default());
    };
    let track_offsets = parse_layout_array(&track_offsets_json, "track_drag_offsets_json")?;
    let mirrors = parse_layout_array(&mirrors_json, "support_mirrored_ctgs_json")?;
    Ok(ProjectViewLayoutSnapshot {
        scoped_track_drag_offsets: track_offsets
            .into_iter()
            .filter(|entry| {
                scope
                    .track_offset_keys
                    .iter()
                    .any(|key| track_offset_matches_key(entry, key))
            })
            .collect(),
        scoped_support_mirrors: mirrors
            .into_iter()
            .filter(|entry| {
                scope
                    .mirror_keys
                    .iter()
                    .any(|key| mirror_matches_key(entry, key))
            })
            .collect(),
    })
}

pub(super) fn reconcile_project_view_layout(
    conn: &Connection,
    project_id: i64,
    scope: &ProjectViewLayoutScope,
    desired: &ProjectViewLayoutSnapshot,
) -> Result<()> {
    if desired.scoped_track_drag_offsets.iter().any(|entry| {
        !scope
            .track_offset_keys
            .iter()
            .any(|key| track_offset_matches_key(entry, key))
    }) || desired.scoped_support_mirrors.iter().any(|entry| {
        !scope
            .mirror_keys
            .iter()
            .any(|key| mirror_matches_key(entry, key))
    }) {
        bail!("{HISTORY_CONFLICT_CODE}: recorded layout state is outside its target scope");
    }
    conn.execute(
        "INSERT INTO project_assembly_view_state (project_id, updated_at)
         VALUES (?1, ?2)
         ON CONFLICT(project_id) DO NOTHING",
        params![project_id, now_timestamp_string()],
    )?;
    let (track_offsets_json, mirrors_json): (String, String) = conn.query_row(
        "SELECT track_drag_offsets_json, support_mirrored_ctgs_json
         FROM project_assembly_view_state WHERE project_id = ?1",
        params![project_id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    let mut track_offsets = parse_layout_array(&track_offsets_json, "track_drag_offsets_json")?;
    let mut mirrors = parse_layout_array(&mirrors_json, "support_mirrored_ctgs_json")?;
    track_offsets.retain(|entry| {
        !scope
            .track_offset_keys
            .iter()
            .any(|key| track_offset_matches_key(entry, key))
    });
    mirrors.retain(|entry| {
        !scope
            .mirror_keys
            .iter()
            .any(|key| mirror_matches_key(entry, key))
    });
    track_offsets.extend(desired.scoped_track_drag_offsets.iter().cloned());
    mirrors.extend(desired.scoped_support_mirrors.iter().cloned());
    let updated = conn.execute(
        "UPDATE project_assembly_view_state
         SET track_drag_offsets_json = ?1,
             support_mirrored_ctgs_json = ?2,
             updated_at = ?3
         WHERE project_id = ?4",
        params![
            serde_json::to_string(&track_offsets)?,
            serde_json::to_string(&mirrors)?,
            now_timestamp_string(),
            project_id,
        ],
    )?;
    if updated != 1 {
        bail!("{HISTORY_CONFLICT_CODE}: project view layout row is missing");
    }
    Ok(())
}

fn parse_layout_array(raw: &str, column: &str) -> Result<Vec<Value>> {
    let value: Value = serde_json::from_str(raw)
        .with_context(|| format!("MAIN_VIEW_HISTORY_LAYOUT_INVALID: invalid persisted {column}"))?;
    value.as_array().cloned().ok_or_else(|| {
        anyhow::anyhow!("MAIN_VIEW_HISTORY_LAYOUT_INVALID: persisted {column} must be a JSON array")
    })
}

fn track_offset_matches_key(entry: &Value, key: &ProjectViewTrackOffsetKey) -> bool {
    let role = entry.get("trackRole").and_then(Value::as_str);
    let ctg_id = entry.get("assemblyCtgId").and_then(Value::as_i64);
    if role != Some(key.track_role.as_str()) || ctg_id != Some(key.assembly_ctg_id) {
        return false;
    }
    match key.track_role.as_str() {
        "support" => entry
            .get("datasetId")
            .and_then(Value::as_i64)
            .is_none_or(|dataset_id| Some(dataset_id) == key.dataset_id),
        "phased" => {
            if let Some(item_id) = key.phased_track_item_id {
                entry.get("phasedTrackItemId").and_then(Value::as_i64) == Some(item_id)
            } else {
                entry.get("phasedTrackId").and_then(Value::as_i64) == key.phased_track_id
            }
        }
        _ => true,
    }
}

fn mirror_matches_key(entry: &Value, key: &ProjectViewMirrorKey) -> bool {
    entry.get("datasetId").and_then(Value::as_i64) == Some(key.dataset_id)
        && entry.get("assemblyCtgId").and_then(Value::as_i64) == Some(key.assembly_ctg_id)
}

fn validate_desired_names(
    conn: &Connection,
    project_id: i64,
    desired: &DatabaseSnapshot,
) -> Result<()> {
    let desired_ids = desired
        .ctgs
        .iter()
        .map(|row| row.id)
        .collect::<BTreeSet<_>>();
    let mut desired_names = BTreeSet::new();
    for row in &desired.ctgs {
        if !desired_names.insert(row.name.clone()) {
            bail!(
                "{HISTORY_CONFLICT_CODE}: recorded ctg name '{}' is duplicated",
                row.name
            );
        }
        let conflict: Option<i64> = conn
            .query_row(
                "SELECT id FROM assembly_ctg
                 WHERE project_id = ?1 AND name = ?2 AND id <> ?3",
                params![project_id, row.name, row.id],
                |query_row| query_row.get(0),
            )
            .optional()?;
        if conflict.is_some_and(|id| !desired_ids.contains(&id)) {
            bail!(
                "{HISTORY_CONFLICT_CODE}: ctg name '{}' is now used by another object",
                row.name
            );
        }
    }
    Ok(())
}

fn resolve_temporary_name(conn: &Connection, project_id: i64, ctg_id: i64) -> Result<String> {
    let mut candidate = format!("__gpm_main_history_tmp_{ctg_id}");
    loop {
        let conflict = conn
            .query_row(
                "SELECT 1 FROM assembly_ctg WHERE project_id = ?1 AND name = ?2 AND id <> ?3",
                params![project_id, candidate, ctg_id],
                |_| Ok(()),
            )
            .optional()?
            .is_some();
        if !conflict {
            return Ok(candidate);
        }
        candidate.push('_');
    }
}

fn reconcile_project_view_dependency(
    conn: &Connection,
    project_id: i64,
    desired: Option<&ProjectViewDependencyRow>,
) -> Result<()> {
    match desired {
        Some(row) => {
            let updated = conn.execute(
                "UPDATE project_assembly_view_state
                 SET final_path_by_chr_json = ?1,
                     degap_project_state_json = ?2,
                     updated_at = ?3
                 WHERE project_id = ?4",
                params![
                    row.final_path_by_chr_json,
                    row.degap_project_state_json,
                    now_timestamp_string(),
                    project_id,
                ],
            )?;
            if updated != 1 {
                bail!("{HISTORY_CONFLICT_CODE}: project view dependency row is missing");
            }
        }
        None => {
            conn.execute(
                "DELETE FROM project_assembly_view_state WHERE project_id = ?1",
                params![project_id],
            )?;
        }
    }
    Ok(())
}
