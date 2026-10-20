//! A single current-Ref envelope cut. No reassignment, recommendation or UI dialog.
use super::types::PreparedMutation;
use crate::contig_split::{
    SplitCommitParams, SplitPart, SplitPreview, load_split_source, partition,
};
use anyhow::{Context, Result, bail};
use rusqlite::Connection;
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    assembly_ctg_id: i64,
    side: String,
    cut_after: i64,
    min_alignment_length: i64,
    min_identity_pct: f64,
}

pub(super) fn prepare_ref_split(
    conn: &Connection,
    project_id: i64,
    chr_name: &str,
    args: &Value,
) -> Result<PreparedMutation> {
    let request: Request =
        serde_json::from_value(args.clone()).context("CTG_SPLIT_INVALID_REQUEST")?;
    if !["left", "right"].contains(&request.side.as_str())
        || request.min_alignment_length < 1
        || !request.min_identity_pct.is_finite()
        || !(0.0..=100.0).contains(&request.min_identity_pct)
    {
        bail!("CTG_SPLIT_INVALID_REQUEST: invalid side or display filters");
    }
    let source = load_split_source(conn, project_id, request.assembly_ctg_id)?;
    if source.assigned_chr_name.as_deref() != Some(chr_name) {
        bail!("CTG_SPLIT_INVALID_TARGET: current chromosome changed");
    }
    let items = crate::main_view::list_chr_view_ctgs_with_connection(
        conn,
        project_id,
        Some(chr_name),
        None,
    )?;
    let ctg = items
        .iter()
        .find(|c| c.assembly_ctg_id == source.assembly_ctg_id)
        .context("CTG_SPLIT_INVALID_TARGET")?;
    let hits: Vec<_> = ctg
        .hits
        .iter()
        .filter(|h| {
            h.block_length >= request.min_alignment_length
                && h.identity_pct >= request.min_identity_pct
        })
        .collect();
    let low = hits
        .iter()
        .map(|h| h.query_start)
        .min()
        .context("CTG_SPLIT_NO_ALIGNMENT: no visible reference alignments")?;
    let high = hits
        .iter()
        .map(|h| h.query_end)
        .max()
        .context("CTG_SPLIT_NO_ALIGNMENT")?;
    let low_side = (request.side == "left") != (source.orient == "-");
    let cut = if low_side { low - 1 } else { high };
    if cut < source.source_start || cut >= source.source_end || cut != request.cut_after {
        bail!(
            "CTG_SPLIT_STALE_BOUNDARY: reopen the menu; the displayed boundary is no longer splittable"
        );
    }
    let parts = partition(&source, &[cut])
        .into_iter()
        .map(|(a, b)| SplitPart {
            source_start: a,
            source_end: b,
            length: b - a + 1,
            candidates: vec![],
        })
        .collect();
    let commit = SplitCommitParams {
        assembly_ctg_id: source.assembly_ctg_id,
        cut_after: vec![cut],
        assignments: vec![source.assigned_chr_name.clone(); 2],
        preview_token: String::new(),
        reason: "alignment-boundary".into(),
    };
    let preview = SplitPreview {
        source,
        parts,
        cut_after: vec![cut],
        hits: vec![],
        recommendations: vec![],
        final_path_reference_count: 0,
        preview_token: String::new(),
    };
    super::split::apply_split(conn, project_id, commit, preview, true)
}
