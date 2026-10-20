//! Add a source slice to another chromosome without moving it or editing Final Path.
use super::snapshot::{capture_snapshot, reconcile_project_view_layout, snapshot_scope};
use super::types::{
    MainViewHistoryOperationDescriptor, PreparedMutation, PrimaryVisibilityKey,
    ProjectViewLayoutScope, SnapshotScope,
};
use crate::contig_chr_alignments::{ChrAlignmentParams, preview_with_connection};
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, params};
use serde::Deserialize;
use serde_json::{Value, json};
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    assembly_ctg_id: i64,
    source_seq_id: i64,
    source_start: i64,
    source_end: i64,
    orient: String,
    target_chr_name: String,
    min_alignment_length: i64,
    min_identity_pct: f64,
    #[serde(default)]
    allow_overlap: bool,
    #[serde(default)]
    reveal_contained: bool,
}
pub(super) fn prepare_add(
    conn: &Connection,
    project: i64,
    chr: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let r: Request = serde_json::from_value(args.clone()).context("CTG_CHR_INVALID_REQUEST")?;
    let preview = preview_with_connection(
        conn,
        project,
        &ChrAlignmentParams {
            assembly_ctg_id: r.assembly_ctg_id,
            min_alignment_length: r.min_alignment_length,
            min_identity_pct: r.min_identity_pct,
        },
    )?;
    let source = &preview.source;
    if source.source_seq_id != r.source_seq_id
        || source.assigned_chr_name.as_deref() != Some(chr)
        || source.source_start != r.source_start
        || source.source_end != r.source_end
        || source.orient != r.orient
    {
        bail!("CTG_CHR_STALE_SOURCE: reopen the chromosome alignment panel");
    }
    let item = preview
        .items
        .iter()
        .find(|i| i.candidate.chr_name == r.target_chr_name)
        .context("CTG_CHR_NO_EVIDENCE: no alignment for this fragment and target chromosome")?;
    if item.presence == "contained" && !r.reveal_contained {
        bail!("CTG_CHR_CONTAINED: target already contains this source interval");
    }
    if item.presence == "overlap" && !r.allow_overlap {
        bail!("CTG_CHR_OVERLAP: confirm overlapping source intervals before adding");
    }
    let existing = ["existing", "hidden", "contained"].contains(&item.presence.as_str());
    let ctg_id = if existing {
        item.existing_ctg_id.context("missing existing contig")?
    } else {
        super::split::next_id(conn, "assembly_ctg")?
    };
    let seq_id = if existing {
        conn.query_row(
            "SELECT assembly_seq_id FROM assembly_ctg WHERE id=?1",
            [ctg_id],
            |q| q.get(0),
        )?
    } else {
        super::split::next_id(conn, "assembly_seq")?
    };
    let scope = SnapshotScope {
        ctg_ids: vec![ctg_id],
        seq_ids: vec![seq_id],
        dependency_ctg_ids: if !existing { vec![ctg_id] } else { vec![] },
        include_view_state: !existing,
        layout_scope: if existing && item.existing_hidden {
            ProjectViewLayoutScope {
                primary_visibility_keys: vec![PrimaryVisibilityKey {
                    chr_name: r.target_chr_name.clone(),
                    assembly_ctg_id: ctg_id,
                }],
                ..Default::default()
            }
        } else {
            Default::default()
        },
        ..Default::default()
    };
    let before = capture_snapshot(conn, project, &scope)?;
    if existing && item.existing_hidden {
        conn.execute("UPDATE assembly_seq SET hidden=0 WHERE id=?1", [seq_id])?;
        let mut desired = before.layout_state.clone();
        for flag in &mut desired.primary_visibility {
            flag.in_list = false;
            flag.in_chr = false;
            flag.in_path = false;
        }
        reconcile_project_view_layout(conn, project, &before.layout_scope, &desired)?;
    } else if !existing {
        let (mut left, mut right): (String, String) = conn.query_row(
            "SELECT left_end_type,right_end_type FROM assembly_seq WHERE id=?1",
            [source.assembly_seq_id],
            |q| Ok((q.get(0)?, q.get(1)?)),
        )?;
        if item.candidate.orient != source.orient {
            std::mem::swap(&mut left, &mut right);
        }
        let now = super::now_timestamp_string();
        let key = format!(
            "manual-fragment:chr-add:{}:{}:{}-{}",
            source.source_seq_id, seq_id, source.source_start, source.source_end
        );
        let note =
            json!({"chrAdd":{"sourceCtgId":source.assembly_ctg_id,"sourceChr":chr}}).to_string();
        conn.execute("INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,left_end_type,right_end_type,hidden,created_at,note) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,0,?10,?11)",params![seq_id,project,source.source_seq_id,key,item.candidate.orient,source.source_start,source.source_end,left,right,now,note])?;
        let base = source
            .name
            .rsplit_once('@')
            .map(|p| p.0)
            .unwrap_or(&source.name);
        let stem = format!("{base}@{}", r.target_chr_name);
        let mut name = stem.clone();
        let mut n = 2;
        while conn.query_row(
            "SELECT EXISTS(SELECT 1 FROM assembly_ctg WHERE project_id=?1 AND name=?2)",
            params![project, name],
            |q| q.get::<_, bool>(0),
        )? {
            name = format!("{stem}_{n}");
            n += 1;
        }
        let order:i64=conn.query_row("SELECT COALESCE(MAX(chr_order),0)+1 FROM assembly_ctg WHERE project_id=?1 AND assigned_chr_name=?2",params![project,r.target_chr_name],|q|q.get(0))?;
        conn.execute("INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at,note) VALUES(?1,?2,?3,?4,?5,?6,?7,NULL,'manual',?8,?9)",params![ctg_id,project,seq_id,name,r.target_chr_name,order,item.candidate.anchor_start,now,note])?;
    }
    let after = capture_snapshot(conn, project, &snapshot_scope(&before))?;
    Ok(PreparedMutation {
        descriptor: MainViewHistoryOperationDescriptor {
            kind: "add-contig-to-chr".into(),
            target_count: 1,
            target_name: Some(format!("{} → {}", source.name, r.target_chr_name)),
        },
        before,
        after,
        affected_ctg_ids: vec![ctg_id],
        affected_seq_ids: vec![seq_id],
        changed: !existing || item.existing_hidden,
    })
}
