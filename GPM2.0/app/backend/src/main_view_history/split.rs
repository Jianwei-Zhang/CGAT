use super::snapshot::{capture_snapshot, reconcile_project_view_layout, snapshot_scope};
use super::types::{
    MainViewHistoryOperationDescriptor, PreparedMutation, ProjectViewLayoutScope,
    ProjectViewTrackOffsetKey, SnapshotScope,
};
use crate::contig_split::{
    SplitCommitParams, SplitPreview, SplitPreviewParams, preview_with_connection,
    rewrite_final_paths,
};
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, params};
use serde_json::{Value, json};

pub(super) fn prepare_split(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let request: SplitCommitParams =
        serde_json::from_value(args.clone()).context("CTG_SPLIT_INVALID_REQUEST")?;
    if request.cut_after.is_empty()
        || !["manual", "alignment-boundary", "recommended"].contains(&request.reason.as_str())
    {
        bail!("CTG_SPLIT_INVALID_REQUEST: provide cuts and a recognized reason");
    }
    let preview = preview_with_connection(
        conn,
        project_id,
        &SplitPreviewParams {
            assembly_ctg_id: request.assembly_ctg_id,
            cut_after: request.cut_after.clone(),
        },
    )?;
    let source = &preview.source;
    if source.assigned_chr_name.as_deref() != Some(chr_name) {
        bail!("CTG_SPLIT_INVALID_TARGET: contig is not in the current chromosome");
    }
    if preview.preview_token != request.preview_token {
        bail!("CTG_SPLIT_STALE_PREVIEW: refresh the split preview before confirming");
    }
    apply_split(conn, project_id, request, preview, false)
}

pub(super) fn apply_split(
    conn: &Connection,
    project_id: i64,
    request: SplitCommitParams,
    preview: SplitPreview,
    keep_placement: bool,
) -> Result<PreparedMutation> {
    let source = &preview.source;
    if request.assignments.len() != preview.parts.len() {
        bail!("CTG_SPLIT_INVALID_REQUEST: choose a group for every fragment");
    }
    let mut placements = Vec::new();
    for (part, assignment) in preview.parts.iter().zip(&request.assignments) {
        let candidate = assignment
            .as_ref()
            .and_then(|chr| part.candidates.iter().find(|c| &c.chr_name == chr));
        if assignment.is_some() && candidate.is_none() && assignment != &source.assigned_chr_name {
            bail!(
                "CTG_SPLIT_UNSUPPORTED_ASSIGNMENT: selected chromosome has no evidence for this fragment"
            );
        }
        let candidate = if keep_placement { None } else { candidate };
        let orient = candidate
            .map(|c| c.orient.clone())
            .unwrap_or_else(|| source.orient.clone());
        let offset = if source.orient == "-" {
            source.source_end - part.source_end
        } else {
            part.source_start - source.source_start
        };
        let anchor = if assignment.is_none() {
            None
        } else {
            candidate
                .map(|c| c.anchor_start)
                .or(source.anchor_start.map(|a| a + offset))
        };
        placements.push((assignment.clone(), orient, anchor));
    }
    let next_ctg = next_id(conn, "assembly_ctg")?;
    let next_seq = next_id(conn, "assembly_seq")?;
    let child_ids: Vec<i64> = (0..preview.parts.len())
        .map(|i| next_ctg + i as i64)
        .collect();
    let seq_ids: Vec<i64> = (0..preview.parts.len())
        .map(|i| next_seq + i as i64)
        .collect();
    let mut all_ctgs = vec![source.assembly_ctg_id];
    all_ctgs.extend(&child_ids);
    let mut all_seqs = vec![source.assembly_seq_id];
    all_seqs.extend(&seq_ids);
    let has_view: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM project_assembly_view_state WHERE project_id=?1)",
        [project_id],
        |r| r.get(0),
    )?;
    let offset_keys: Vec<ProjectViewTrackOffsetKey> = all_ctgs
        .iter()
        .map(|id| ProjectViewTrackOffsetKey {
            track_role: "primary".into(),
            assembly_ctg_id: *id,
            dataset_id: None,
            phased_track_id: None,
            phased_track_item_id: None,
        })
        .collect();
    let before = capture_snapshot(
        conn,
        project_id,
        &SnapshotScope {
            ctg_ids: all_ctgs.clone(),
            seq_ids: all_seqs.clone(),
            dependency_ctg_ids: all_ctgs.clone(),
            include_view_state: true,
            layout_scope: if keep_placement && has_view {
                ProjectViewLayoutScope {
                    track_offset_keys: offset_keys,
                    ..Default::default()
                }
            } else {
                Default::default()
            },
            ..SnapshotScope::default()
        },
    )?;
    let parent = before
        .seqs
        .iter()
        .find(|s| s.id == source.assembly_seq_id)
        .context("missing split source")?;
    let note=json!({"manualSplit":{"parentCtgId":source.assembly_ctg_id,"parentSourceStart":source.source_start,
        "parentSourceEnd":source.source_end,"cutAfter":preview.cut_after,"reason":request.reason}}).to_string();
    let original_ctg = before
        .ctgs
        .iter()
        .find(|c| c.id == source.assembly_ctg_id)
        .context("missing split contig")?;
    let now = super::now_timestamp_string();
    for (i, part) in preview.parts.iter().enumerate() {
        let (chr, orient, anchor) = &placements[i];
        let group = if keep_placement && source.instance_key.starts_with("manual-fragment:") {
            source
                .instance_key
                .rsplit_once(':')
                .map(|p| p.0.to_string())
                .unwrap_or_default()
        } else {
            format!("manual-fragment:{}", source.assembly_ctg_id)
        };
        let key = format!("{group}:{}-{}", part.source_start, part.source_end);
        // End types are display-oriented; only original exterior ends are inherited.
        let low_type = if source.orient == "-" {
            &parent.right_end_type
        } else {
            &parent.left_end_type
        };
        let high_type = if source.orient == "-" {
            &parent.left_end_type
        } else {
            &parent.right_end_type
        };
        let low = if part.source_start == source.source_start {
            low_type.as_str()
        } else {
            "normal"
        };
        let high = if part.source_end == source.source_end {
            high_type.as_str()
        } else {
            "normal"
        };
        let (left, right) = if orient == "-" {
            (high, low)
        } else {
            (low, high)
        };
        conn.execute("INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,left_end_type,right_end_type,hidden,created_at,note)
            VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,0,?10,?11)",
            params![seq_ids[i],project_id,source.source_seq_id,key,orient,part.source_start,part.source_end,left,right,now,note])?;
        let name = if keep_placement {
            let base = source
                .name
                .rsplit_once('@')
                .map(|p| p.0)
                .unwrap_or(&source.name);
            let display_index = if source.orient == "-" {
                preview.parts.len() - i
            } else {
                i + 1
            };
            let stem = format!("{base}.{display_index}");
            let mut name = stem.clone();
            let mut suffix = 2;
            while conn.query_row(
                "SELECT EXISTS(SELECT 1 FROM assembly_ctg WHERE project_id=?1 AND name=?2)",
                params![project_id, name],
                |r| r.get::<_, bool>(0),
            )? {
                name = format!("{stem}_{suffix}");
                suffix += 1;
            }
            name
        } else {
            format!(
                "{}[{}-{}]#{}{}",
                source.contig_name,
                part.source_start,
                part.source_end,
                child_ids[i],
                chr.as_ref().map(|c| format!("@{c}")).unwrap_or_default()
            )
        };
        let order = if keep_placement {
            original_ctg.chr_order
        } else {
            None
        };
        let ref_orient = if keep_placement {
            original_ctg.ref_orient.as_deref()
        } else {
            None
        };
        conn.execute("INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at,note)
            VALUES(?1,?2,?3,?4,?5,?6,?7,?8,'manual',?9,?10)",
            params![child_ids[i],project_id,seq_ids[i],name,chr,order,anchor,ref_orient,now,note])?;
    }
    // Replace phase-track references only with children that remain in that chromosome.
    for track in &before.phased_tracks {
        let items: Vec<_> = before
            .phased_items
            .iter()
            .filter(|item| item.phased_track_id == track.id)
            .collect();
        conn.execute(
            "DELETE FROM phased_chr_track_item WHERE phased_track_id=?1",
            [track.id],
        )?;
        let mut order = 0;
        for item in items {
            if item.assembly_ctg_id == source.assembly_ctg_id {
                let mut indices: Vec<_> = (0..child_ids.len()).collect();
                if item.orient == "-" {
                    indices.reverse();
                }
                for i in indices {
                    if placements[i].0.as_deref() != Some(&track.parent_chr_name) {
                        continue;
                    }
                    order += 1;
                    conn.execute("INSERT INTO phased_chr_track_item(phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at,note) VALUES(?1,?2,?3,0,?4,?5,?6)",params![track.id,child_ids[i],order,item.orient,now,note])?;
                }
            } else {
                order += 1;
                conn.execute("INSERT INTO phased_chr_track_item(id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at,note) VALUES(?1,?2,?3,?4,?5,?6,?7,?8)",params![item.id,track.id,item.assembly_ctg_id,order,item.gap_before_px,item.orient,item.created_at,item.note])?;
            }
        }
    }
    if let Some(view) = &before.view_state {
        let mut paths: Value = serde_json::from_str(&view.final_path_by_chr_json)?;
        let children: Vec<_> = preview
            .parts
            .iter()
            .zip(&child_ids)
            .map(|(p, id)| (*id, p.source_start, p.source_end))
            .collect();
        rewrite_final_paths(&mut paths, source, &preview.cut_after, &children)?;
        let mut degap: Value = serde_json::from_str(&view.degap_project_state_json)?;
        super::mutations::mark_json_references(
            &mut degap,
            &[source.assembly_ctg_id].into_iter().collect(),
        );
        conn.execute("UPDATE project_assembly_view_state SET final_path_by_chr_json=?1,degap_project_state_json=?2,updated_at=?3 WHERE project_id=?4",params![paths.to_string(),degap.to_string(),now,project_id])?;
    }
    conn.execute(
        "UPDATE export_record SET assembly_ctg_id=NULL WHERE project_id=?1 AND assembly_ctg_id=?2",
        params![project_id, source.assembly_ctg_id],
    )?;
    conn.execute(
        "DELETE FROM assembly_ctg WHERE id=?1",
        [source.assembly_ctg_id],
    )?;
    conn.execute(
        "UPDATE assembly_seq SET hidden=1 WHERE id=?1",
        [source.assembly_seq_id],
    )?;
    if keep_placement && before.view_state.is_some() {
        let mut layout = before.layout_state.clone();
        let original = layout
            .scoped_track_drag_offsets
            .iter()
            .find(|v| {
                v.get("assemblyCtgId").and_then(Value::as_i64) == Some(source.assembly_ctg_id)
            })
            .cloned();
        layout.scoped_track_drag_offsets.clear();
        if let Some(original) = original {
            for id in &child_ids {
                let mut offset = original.clone();
                offset["assemblyCtgId"] = json!(id);
                layout.scoped_track_drag_offsets.push(offset);
            }
        }
        reconcile_project_view_layout(conn, project_id, &before.layout_scope, &layout)?;
    }
    let after = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: if keep_placement && request.reason == "manual" {
                "split-manual-contig"
            } else if keep_placement {
                "split-ref-boundary"
            } else {
                "split-source-ctg"
            }
            .into(),
            target_count: 1,
            target_name: Some(source.name.clone()),
        },
        before,
        after,
        affected_ctg_ids: all_ctgs,
        affected_seq_ids: all_seqs,
        changed: true,
    })
}

pub(super) fn next_id(conn: &Connection, table: &str) -> Result<i64> {
    // table is always a compile-time identifier from the two callers above.
    Ok(conn.query_row(&format!("SELECT MAX(COALESCE((SELECT MAX(id) FROM {table}),0),COALESCE((SELECT seq FROM sqlite_sequence WHERE name=?1),0))+1"),[table],|r|r.get(0))?)
}
