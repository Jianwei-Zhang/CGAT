//! Remove one display-side split boundary while preserving immutable path intervals.
use super::snapshot::{capture_snapshot, reconcile_project_view_layout, snapshot_scope};
use super::types::{
    MainViewHistoryOperationDescriptor, PreparedMutation, PrimaryVisibilityKey,
    ProjectViewLayoutScope, ProjectViewTrackOffsetKey, SnapshotScope,
};
use crate::contig_split::{SplitSource, load_split_source};
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, params};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    assembly_ctg_id: i64,
    neighbor_ctg_id: i64,
    side: String,
    source_start: i64,
    source_end: i64,
    orient: String,
    neighbor_source_start: i64,
    neighbor_source_end: i64,
}

fn group(source: &SplitSource) -> &str {
    source
        .instance_key
        .rsplit_once(':')
        .map(|p| p.0)
        .unwrap_or("")
}

pub(super) fn prepare_unsplit(
    conn: &Connection,
    project: i64,
    chr: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let r: Request = serde_json::from_value(args.clone()).context("CTG_UNSPLIT_INVALID_REQUEST")?;
    if !["left", "right"].contains(&r.side.as_str()) || r.assembly_ctg_id == r.neighbor_ctg_id {
        bail!("CTG_UNSPLIT_INVALID_REQUEST: choose one split boundary");
    }
    let source = load_split_source(conn, project, r.assembly_ctg_id)?;
    let neighbor = load_split_source(conn, project, r.neighbor_ctg_id)?;
    let low_side = (r.side == "left") != (source.orient == "-");
    if source.assigned_chr_name.as_deref() != Some(chr)
        || neighbor.assigned_chr_name.as_deref() != Some(chr)
        || source.source_seq_id != neighbor.source_seq_id
        || !group(&source).starts_with("manual-fragment:")
        || group(&source) != group(&neighbor)
        || source.orient != neighbor.orient
        || source.orient != r.orient
        || source.source_start != r.source_start
        || source.source_end != r.source_end
        || neighbor.source_start != r.neighbor_source_start
        || neighbor.source_end != r.neighbor_source_end
        || if low_side {
            neighbor.source_end.checked_add(1) != Some(source.source_start)
        } else {
            source.source_end.checked_add(1) != Some(neighbor.source_start)
        }
    {
        bail!(
            "CTG_UNSPLIT_STALE_SOURCE: reopen the menu; fragments must be adjacent, same-source, same-group and same-orientation"
        );
    }
    let ctg_ids = vec![source.assembly_ctg_id, neighbor.assembly_ctg_id];
    let seq_ids = vec![source.assembly_seq_id, neighbor.assembly_seq_id];
    let has_view: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM project_assembly_view_state WHERE project_id=?1)",
        [project],
        |r| r.get(0),
    )?;
    let before = capture_snapshot(
        conn,
        project,
        &SnapshotScope {
            ctg_ids: ctg_ids.clone(),
            seq_ids: seq_ids.clone(),
            dependency_ctg_ids: ctg_ids.clone(),
            include_view_state: true,
            layout_scope: if has_view {
                ProjectViewLayoutScope {
                    track_offset_keys: ctg_ids
                        .iter()
                        .map(|id| ProjectViewTrackOffsetKey {
                            track_role: "primary".into(),
                            assembly_ctg_id: *id,
                            dataset_id: None,
                            phased_track_id: None,
                            phased_track_item_id: None,
                        })
                        .collect(),
                    primary_visibility_keys: ctg_ids
                        .iter()
                        .map(|id| PrimaryVisibilityKey {
                            chr_name: chr.into(),
                            assembly_ctg_id: *id,
                        })
                        .collect(),
                    ..Default::default()
                }
            } else {
                Default::default()
            },
            ..Default::default()
        },
    )?;
    if before.seqs.iter().any(|s| s.hidden != 0)
        || before
            .layout_state
            .primary_visibility
            .iter()
            .any(|s| s.in_list || s.in_chr || s.in_path)
    {
        bail!("CTG_UNSPLIT_HIDDEN: reveal both fragments before removing a split boundary");
    }
    // A linked DEGap job still describes the old intervals. Do not silently retarget it.
    let mut degap: Value = serde_json::from_str(
        before
            .view_state
            .as_ref()
            .map(|v| v.degap_project_state_json.as_str())
            .unwrap_or("{}"),
    )?;
    if super::mutations::mark_json_references(&mut degap, &ctg_ids.iter().copied().collect()) > 0 {
        bail!("CTG_UNSPLIT_DEPENDENCY: remove linked DEGap references before merging fragments");
    }
    // Phased tracks may contain the pair only as adjacent, consistently oriented items.
    // A partial adoption or an explicit internal gap cannot be extended without changing DNA.
    for track in &before.phased_tracks {
        let items: Vec<_> = before
            .phased_items
            .iter()
            .filter(|i| i.phased_track_id == track.id)
            .collect();
        let pair: Vec<_> = items
            .iter()
            .enumerate()
            .filter(|(_, i)| ctg_ids.contains(&i.assembly_ctg_id))
            .collect();
        if pair.len() != 2
            || pair[1].0 != pair[0].0 + 1
            || pair[0].1.orient != pair[1].1.orient
            || pair[1].1.gap_before_px != 0
        {
            bail!(
                "CTG_UNSPLIT_DEPENDENCY: phased-track fragments must be consecutive with no internal gap"
            );
        }
        let low_id = if low_side {
            neighbor.assembly_ctg_id
        } else {
            source.assembly_ctg_id
        };
        let expected_first = if pair[0].1.orient == "-" {
            if low_id == source.assembly_ctg_id {
                neighbor.assembly_ctg_id
            } else {
                source.assembly_ctg_id
            }
        } else {
            low_id
        };
        if pair[0].1.assembly_ctg_id != expected_first {
            bail!("CTG_UNSPLIT_DEPENDENCY: phased-track source order changed");
        }
        conn.execute(
            "DELETE FROM phased_chr_track_item WHERE id=?1",
            [pair[1].1.id],
        )?;
        conn.execute(
            "UPDATE phased_chr_track_item SET assembly_ctg_id=?1 WHERE id=?2",
            params![source.assembly_ctg_id, pair[0].1.id],
        )?;
    }
    if let Some(view) = &before.view_state {
        let mut paths: Value = serde_json::from_str(&view.final_path_by_chr_json)?;
        preserve_paths(&mut paths, &source, &neighbor)?;
        conn.execute("UPDATE project_assembly_view_state SET final_path_by_chr_json=?1,updated_at=?2 WHERE project_id=?3",
            params![paths.to_string(), super::now_timestamp_string(), project])?;
    }
    let start = source.source_start.min(neighbor.source_start);
    let end = source.source_end.max(neighbor.source_end);
    let anchor = source.anchor_start.map(|a| {
        a - if source.orient == "-" {
            end - source.source_end
        } else {
            source.source_start - start
        }
    });
    let left_id = if r.side == "left" {
        neighbor.assembly_seq_id
    } else {
        source.assembly_seq_id
    };
    let right_id = if r.side == "right" {
        neighbor.assembly_seq_id
    } else {
        source.assembly_seq_id
    };
    let left = &before
        .seqs
        .iter()
        .find(|s| s.id == left_id)
        .context("missing left fragment")?
        .left_end_type;
    let right = &before
        .seqs
        .iter()
        .find(|s| s.id == right_id)
        .context("missing right fragment")?
        .right_end_type;
    // The suffix is not identity: source coordinates and the unchanged group are authoritative.
    // Include the retained sequence ID so a retired parent cannot cause a unique-key collision.
    let key = format!(
        "{}:{start}-{end}~{}",
        group(&source),
        source.assembly_seq_id
    );
    conn.execute("UPDATE assembly_seq SET source_start=?1,source_end=?2,instance_key=?3,left_end_type=?4,right_end_type=?5 WHERE id=?6",
        params![start, end, key, left, right, source.assembly_seq_id])?;
    conn.execute(
        "UPDATE assembly_ctg SET anchor_start=?1,placement_mode='manual' WHERE id=?2",
        params![anchor, source.assembly_ctg_id],
    )?;
    // Preserve export artifacts but detach their obsolete fragment identity.
    conn.execute("UPDATE export_record SET assembly_ctg_id=NULL WHERE project_id=?1 AND assembly_ctg_id IN (?2,?3)",
        params![project, source.assembly_ctg_id, neighbor.assembly_ctg_id])?;
    conn.execute(
        "DELETE FROM assembly_ctg WHERE id=?1",
        [neighbor.assembly_ctg_id],
    )?;
    conn.execute(
        "UPDATE assembly_seq SET hidden=1 WHERE id=?1",
        [neighbor.assembly_seq_id],
    )?;
    let mut layout = before.layout_state.clone();
    layout.scoped_track_drag_offsets.retain(|v| {
        v.get("assemblyCtgId").and_then(Value::as_i64) != Some(neighbor.assembly_ctg_id)
    });
    for entry in &mut layout.primary_visibility {
        if entry.key.assembly_ctg_id == neighbor.assembly_ctg_id {
            entry.in_list = false;
            entry.in_chr = false;
            entry.in_path = false;
        }
    }
    if has_view {
        reconcile_project_view_layout(conn, project, &before.layout_scope, &layout)?;
    }
    let after = capture_snapshot(conn, project, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: "undo-contig-split".into(),
            target_count: 1,
            target_name: Some(source.name),
        },
        before,
        after,
        affected_ctg_ids: ctg_ids,
        affected_seq_ids: seq_ids,
        changed: true,
    })
}

fn preserve_paths(paths: &mut Value, source: &SplitSource, neighbor: &SplitSource) -> Result<()> {
    let entries = paths.as_object_mut().context("CTG_UNSPLIT_INVALID_PATH")?;
    for entry in entries.values_mut() {
        let Some(segments) = entry.get_mut("segments").and_then(Value::as_array_mut) else {
            continue;
        };
        for segment in segments {
            if segment.get("type").and_then(Value::as_str) == Some("gap") {
                continue;
            }
            let owner = segment
                .get("assemblyCtgId")
                .and_then(Value::as_i64)
                .and_then(|id| {
                    [source, neighbor]
                        .into_iter()
                        .find(|s| s.assembly_ctg_id == id)
                });
            if let Some(owner) = owner {
                let mut a = segment
                    .get("start")
                    .and_then(Value::as_i64)
                    .context("CTG_UNSPLIT_INVALID_PATH: missing start")?;
                let mut b = segment
                    .get("end")
                    .and_then(Value::as_i64)
                    .context("CTG_UNSPLIT_INVALID_PATH: missing end")?;
                if segment.get("source").is_none_or(Value::is_null) {
                    let length = owner.source_end - owner.source_start + 1;
                    if a < 1 || b < 1 || a > length || b > length {
                        bail!("CTG_UNSPLIT_INVALID_PATH: interval out of bounds");
                    }
                    a += owner.source_start - 1;
                    b += owner.source_start - 1;
                } else if segment.pointer("/source/dataset").and_then(Value::as_str)
                    != Some(&owner.dataset_name)
                    || segment.pointer("/source/contig").and_then(Value::as_str)
                        != Some(&owner.contig_name)
                {
                    bail!("CTG_UNSPLIT_INVALID_PATH: source identity changed");
                }
                if a < 1 || b < 1 || a > owner.source_length || b > owner.source_length {
                    bail!("CTG_UNSPLIT_INVALID_PATH: source interval out of bounds");
                }
                segment["assemblyCtgId"] = Value::Null;
                segment["start"] = json!(a);
                segment["end"] = json!(b);
                segment["source"] = json!({"dataset":owner.dataset_name,"contig":owner.contig_name,"start":a.min(b),"end":a.max(b),"orientation":if a > b {"-"} else {"+"}});
                segment["overallLen"] = json!(owner.source_length);
                segment["splitFragmentCtgId"] = json!(source.assembly_ctg_id);
            } else if segment.get("splitFragmentCtgId").and_then(Value::as_i64)
                == Some(neighbor.assembly_ctg_id)
            {
                segment["splitFragmentCtgId"] = json!(source.assembly_ctg_id);
            }
        }
    }
    Ok(())
}
