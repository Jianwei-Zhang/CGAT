//! Interval-scoped edits requested by Local View. All partitions, dependency
//! updates and tombstones belong to ONE transaction and ONE main history entry.
use std::collections::BTreeSet;

use anyhow::{Context, Result, bail};
use rusqlite::Connection;
use serde::Deserialize;
use serde_json::Value;

use super::snapshot::{capture_snapshot, reconcile_project_view_layout, snapshot_scope};
use super::types::{
    MainViewHistoryOperationDescriptor, PreparedMutation, ProjectViewLayoutScope,
    ProjectViewTrackOffsetKey, SnapshotScope,
};
use crate::contig_split::{
    SplitCommitParams, SplitPart, SplitPreview, SplitSource, load_split_source, partition,
};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Target {
    assembly_ctg_id: i64,
    source_start: i64,
    source_end: i64,
    orient: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    action: String,
    source_start: i64,
    source_end: i64,
    cut_after: Option<i64>,
    targets: Vec<Target>,
}

struct Plan {
    source: SplitSource,
    cuts: Vec<i64>,
    ranges: Vec<(i64, i64)>,
    child_ids: Vec<i64>,
}

fn instance_group(source: &SplitSource) -> &str {
    if source.instance_key.starts_with("manual-fragment:")
        || source.instance_key.starts_with("n-fragment:")
    {
        source
            .instance_key
            .rsplit_once(':')
            .map(|(group, _)| group)
            .unwrap_or(&source.instance_key)
    } else {
        &source.instance_key
    }
}

pub(super) fn prepare(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let request: Request =
        serde_json::from_value(args.clone()).context("LOCAL_FRAGMENT_INVALID_REQUEST")?;
    let deleting = request.action == "delete";
    if !["split", "delete"].contains(&request.action.as_str())
        || request.source_start < 1
        || request.source_end < request.source_start
        || request.targets.is_empty()
        || request.targets.len() > 1024
        || (deleting && request.cut_after.is_some())
        || (!deleting
            && !request
                .cut_after
                .is_some_and(|cut| cut >= request.source_start && cut < request.source_end))
    {
        bail!("LOCAL_FRAGMENT_INVALID_REQUEST: invalid inclusive interval or cut");
    }

    let mut ids = BTreeSet::new();
    let mut sources = Vec::new();
    for target in &request.targets {
        if !ids.insert(target.assembly_ctg_id) {
            bail!("LOCAL_FRAGMENT_INVALID_REQUEST: duplicate target");
        }
        let source = load_split_source(conn, project_id, target.assembly_ctg_id)?;
        if source.assigned_chr_name.as_deref() != Some(chr_name)
            || source.source_start != target.source_start
            || source.source_end != target.source_end
            || source.orient != target.orient
        {
            bail!("LOCAL_FRAGMENT_STALE_SOURCE: Main View entity changed; reopen Local View");
        }
        if source.source_end < request.source_start || source.source_start > request.source_end {
            bail!("LOCAL_FRAGMENT_INVALID_REQUEST: target does not overlap the requested interval");
        }
        sources.push(source);
    }
    sources.sort_by_key(|source| source.source_start);
    let first = &sources[0];
    for source in &sources {
        if source.source_seq_id != first.source_seq_id
            || instance_group(source) != instance_group(first)
        {
            bail!("LOCAL_FRAGMENT_INCOMPATIBLE_SOURCE: targets are not one source instance");
        }
    }
    let mut next_base = request.source_start;
    let mut previous_end = 0;
    for source in &sources {
        let start = source.source_start.max(request.source_start);
        let end = source.source_end.min(request.source_end);
        if start > next_base || source.source_start <= previous_end {
            bail!("LOCAL_FRAGMENT_INCOMPATIBLE_SOURCE: missing or overlapping source bases");
        }
        next_base = end + 1;
        previous_end = source.source_end;
    }
    if next_base <= request.source_end {
        bail!("LOCAL_FRAGMENT_INCOMPATIBLE_SOURCE: incomplete interval coverage");
    }

    let name = (sources.len() == 1).then(|| sources[0].name.clone());
    let target_count = sources.len() as i64;
    let mut next_ctg = super::split::next_id(conn, "assembly_ctg")?;
    let mut next_seq = super::split::next_id(conn, "assembly_seq")?;
    let mut all_ctgs: Vec<_> = sources
        .iter()
        .map(|source| source.assembly_ctg_id)
        .collect();
    let mut all_seqs: Vec<_> = sources
        .iter()
        .map(|source| source.assembly_seq_id)
        .collect();
    let mut plans = Vec::new();
    let mut removed_ids = Vec::new();
    for source in sources {
        let mut cuts: Vec<_> = [
            Some(request.source_start - 1),
            Some(request.source_end),
            request.cut_after,
        ]
        .into_iter()
        .flatten()
        .filter(|cut| *cut >= source.source_start && *cut < source.source_end)
        .collect();
        cuts.sort_unstable();
        cuts.dedup();
        let ranges = partition(&source, &cuts);
        let children = if cuts.is_empty() {
            vec![source.assembly_ctg_id]
        } else {
            let ctgs: Vec<_> = (0..ranges.len())
                .map(|index| next_ctg + index as i64)
                .collect();
            let seqs: Vec<_> = (0..ranges.len())
                .map(|index| next_seq + index as i64)
                .collect();
            next_ctg += ranges.len() as i64;
            next_seq += ranges.len() as i64;
            all_ctgs.extend(&ctgs);
            all_seqs.extend(seqs);
            ctgs
        };
        if deleting {
            removed_ids.extend(
                ranges
                    .iter()
                    .zip(&children)
                    .filter_map(|((start, end), id)| {
                        (*start >= request.source_start && *end <= request.source_end)
                            .then_some(*id)
                    }),
            );
        }
        plans.push(Plan {
            source,
            cuts,
            ranges,
            child_ids: children,
        });
    }
    let deleted_record_ids =
        super::mutations::allocate_deleted_record_ids(conn, removed_ids.len())?;
    let has_view: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM project_assembly_view_state WHERE project_id=?1)",
        [project_id],
        |row| row.get(0),
    )?;
    let offset_keys = all_ctgs
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
            deleted_record_ids,
            dependency_ctg_ids: all_ctgs.clone(),
            include_view_state: true,
            layout_scope: if has_view {
                ProjectViewLayoutScope {
                    track_offset_keys: offset_keys,
                    ..Default::default()
                }
            } else {
                Default::default()
            },
            ..Default::default()
        },
    )?;
    for plan in plans {
        if plan.cuts.is_empty() {
            continue;
        }
        let parts = plan
            .ranges
            .into_iter()
            .map(|(start, end)| SplitPart {
                source_start: start,
                source_end: end,
                length: end - start + 1,
                candidates: vec![],
            })
            .collect();
        let assignments = vec![plan.source.assigned_chr_name.clone(); plan.child_ids.len()];
        let commit = SplitCommitParams {
            assembly_ctg_id: plan.source.assembly_ctg_id,
            cut_after: plan.cuts.clone(),
            assignments,
            preview_token: String::new(),
            reason: "manual".into(),
        };
        let preview = SplitPreview {
            source: plan.source,
            parts,
            cut_after: plan.cuts,
            hits: vec![],
            recommendations: vec![],
            final_path_reference_count: 0,
            preview_token: String::new(),
        };
        super::split::apply_split(conn, project_id, commit, preview, true)?;
    }
    if !removed_ids.is_empty() {
        super::mutations::prepare_batch_delete(conn, project_id, chr_name, &removed_ids)?;
        let current = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
        let removed: BTreeSet<_> = removed_ids.into_iter().collect();
        let mut layout = current.layout_state;
        layout.scoped_track_drag_offsets.retain(|entry| {
            !entry
                .get("assemblyCtgId")
                .and_then(Value::as_i64)
                .is_some_and(|id| removed.contains(&id))
        });
        if has_view {
            reconcile_project_view_layout(conn, project_id, &before.layout_scope, &layout)?;
        }
    }
    let after = capture_snapshot(conn, project_id, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: if deleting {
                "delete-local-fragment"
            } else {
                "split-local-fragment"
            }
            .into(),
            target_count,
            target_name: name,
        },
        changed: before != after,
        before,
        after,
        affected_ctg_ids: all_ctgs,
        affected_seq_ids: all_seqs,
    })
}
