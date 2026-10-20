//! Read-only, fragment-scoped cross-chromosome evidence and semantic presence checks.
use crate::contig_split::{
    SplitCandidate, SplitHit, SplitSource, load_source_hits, load_split_source, rank_candidates,
};
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ChrAlignmentParams {
    pub assembly_ctg_id: i64,
    pub min_alignment_length: i64,
    pub min_identity_pct: f64,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChrAlignmentPreview {
    pub source: SplitSource,
    pub items: Vec<ChrAlignmentItem>,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChrAlignmentItem {
    #[serde(flatten)]
    pub candidate: SplitCandidate,
    pub ref_length: i64,
    pub presence: String,
    pub existing_ctg_id: Option<i64>,
    pub existing_hidden: bool,
    pub hits: Vec<SplitHit>,
}

pub fn get_contig_chr_alignments(
    db: &Path,
    project_id: i64,
    request: &ChrAlignmentParams,
) -> Result<ChrAlignmentPreview> {
    let mut conn = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let tx = conn.transaction()?;
    let result = preview_with_connection(&tx, project_id, request)?;
    tx.commit()?;
    Ok(result)
}

pub(crate) fn preview_with_connection(
    conn: &Connection,
    project_id: i64,
    request: &ChrAlignmentParams,
) -> Result<ChrAlignmentPreview> {
    if request.min_alignment_length < 0
        || !request.min_identity_pct.is_finite()
        || !(0.0..=100.0).contains(&request.min_identity_pct)
    {
        bail!("CTG_CHR_INVALID_FILTER: invalid alignment filters");
    }
    let source = load_split_source(conn, project_id, request.assembly_ctg_id)?;
    let raw = load_source_hits(conn, project_id, &source)?
        .into_iter()
        .map(|h| (h.id, h))
        .collect::<std::collections::HashMap<_, _>>();
    let mut approximate = std::collections::HashSet::new();
    let mut hits = Vec::new();
    for projected in
        crate::main_view::project_contig_hits_to_all_chr(conn, project_id, source.assembly_ctg_id)?
    {
        if projected.block_length < request.min_alignment_length
            || projected.identity_pct < request.min_identity_pct
        {
            continue;
        }
        let Some(original) = raw.get(&projected.hit_id) else {
            continue;
        };
        if projected.reference_projection_approximate {
            approximate.insert(original.chr_name.clone());
        }
        let mut h = original.clone();
        h.query_start = projected.query_start;
        h.query_end = projected.query_end;
        h.ref_start = projected.ref_start;
        h.ref_end = projected.ref_end;
        // The coordinates are already projected/clipped. Do not apply the raw
        // full-hit CIGAR to these shorter bounds. Keep raw match/block identity.
        h.cigar = None;
        hits.push(h);
    }
    let visibility = visibility_json(conn, project_id)?;
    let mut items = Vec::new();
    for mut candidate in rank_candidates(&hits, source.source_start, source.source_end)? {
        if source.assigned_chr_name.as_deref() == Some(&candidate.chr_name) {
            continue;
        }
        let (presence, existing_ctg_id, existing_hidden) = presence_for(
            conn,
            project_id,
            &source,
            &candidate.chr_name,
            visibility.as_ref(),
        )?;
        let ref_length=conn.query_row("SELECT r.length FROM reference_chr r JOIN project p ON p.reference_genome_id=r.reference_genome_id WHERE p.id=?1 AND r.chr_name=?2",params![project_id,candidate.chr_name],|r|r.get(0))?;
        candidate.approximate = approximate.contains(&candidate.chr_name);
        let clipped = hits
            .iter()
            .filter(|h| h.chr_name == candidate.chr_name)
            .cloned()
            .collect();
        items.push(ChrAlignmentItem {
            candidate,
            ref_length,
            presence,
            existing_ctg_id,
            existing_hidden,
            hits: clipped,
        });
    }
    items.sort_by(|a, b| {
        b.candidate
            .coverage_bp
            .cmp(&a.candidate.coverage_bp)
            .then(
                b.candidate
                    .identity_percent
                    .total_cmp(&a.candidate.identity_percent),
            )
            .then(a.candidate.chr_name.cmp(&b.candidate.chr_name))
    });
    Ok(ChrAlignmentPreview { source, items })
}

// Orientation and display names are deliberately NOT identity. SourceSeq includes dataset identity.
fn presence_for(
    conn: &Connection,
    project_id: i64,
    source: &SplitSource,
    chr: &str,
    visibility: Option<&(Value, Value, Value)>,
) -> Result<(String, Option<i64>, bool)> {
    let mut stmt=conn.prepare("SELECT c.id,s.source_start,s.source_end,s.hidden FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.project_id=?1 AND s.project_id=?1 AND s.source_seq_id=?2 AND c.assigned_chr_name=?3 AND s.source_start<=?4 AND s.source_end>=?5 ORDER BY c.id")?;
    let rows = stmt
        .query_map(
            params![
                project_id,
                source.source_seq_id,
                chr,
                source.source_end,
                source.source_start
            ],
            |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, i64>(2)?,
                    r.get::<_, bool>(3)?,
                ))
            },
        )?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let mut matches = Vec::new();
    for (id, a, b, hidden) in rows {
        let (in_list, in_chr, in_path) = flags_from_json(visibility, chr, id);
        let hidden = hidden || in_list || in_chr || in_path;
        let rank = if a == source.source_start && b == source.source_end {
            if hidden { 1 } else { 0 }
        } else if a <= source.source_start && b >= source.source_end {
            2
        } else {
            3
        };
        matches.push((rank, hidden, id));
    }
    matches.sort();
    Ok(match matches.first() {
        Some((0, _, id)) => ("existing".into(), Some(*id), false),
        Some((1, _, id)) => ("hidden".into(), Some(*id), true),
        Some((2, hidden, id)) => ("contained".into(), Some(*id), *hidden),
        Some((_, hidden, id)) => ("overlap".into(), Some(*id), *hidden),
        None => ("missing".into(), None, false),
    })
}

pub(crate) fn hidden_flags(
    conn: &Connection,
    project: i64,
    chr: &str,
    id: i64,
) -> Result<(bool, bool, bool)> {
    Ok(flags_from_json(
        visibility_json(conn, project)?.as_ref(),
        chr,
        id,
    ))
}
fn flags_from_json(
    visibility: Option<&(Value, Value, Value)>,
    chr: &str,
    id: i64,
) -> (bool, bool, bool) {
    let Some((list, map, paths)) = visibility else {
        return (false, false, false);
    };
    let contains = |v: Option<&Value>| {
        v.and_then(Value::as_array)
            .is_some_and(|a| a.iter().any(|v| v.as_i64() == Some(id)))
    };
    (
        contains(Some(list)),
        contains(map.get(chr)),
        contains(paths.get(chr).and_then(|p| p.get("hiddenPrimaryCtgIds"))),
    )
}

fn visibility_json(conn: &Connection, project: i64) -> Result<Option<(Value, Value, Value)>> {
    let row=conn.query_row("SELECT hidden_primary_ctg_ids_json,hidden_primary_ctg_ids_by_chr_json,final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",[project],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?))).optional()?;
    row.map(|(a, b, c)| {
        let list: Value = serde_json::from_str(&a)?;
        let map: Value = serde_json::from_str(&b)?;
        let paths: Value = serde_json::from_str(&c)?;
        if !list.is_array()
            || !map.is_object()
            || !paths.is_object()
            || map
                .as_object()
                .is_some_and(|m| m.values().any(|v| !v.is_array()))
        {
            bail!("CTG_CHR_INVALID_VISIBILITY");
        }
        Ok((list, map, paths))
    })
    .transpose()
}
pub(crate) fn set_hidden_flags(
    conn: &Connection,
    project: i64,
    chr: &str,
    id: i64,
    in_list: bool,
    in_chr: bool,
    in_path: bool,
) -> Result<()> {
    let (mut list, mut map, mut paths) =
        visibility_json(conn, project)?.unwrap_or((json!([]), json!({}), json!({})));
    let values = list.as_array_mut().context("CTG_CHR_INVALID_VISIBILITY")?;
    values.retain(|v| v.as_i64() != Some(id));
    if in_list {
        values.push(json!(id));
    }
    let object = map.as_object_mut().context("CTG_CHR_INVALID_VISIBILITY")?;
    let mut values = object
        .get(chr)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    values.retain(|v| v.as_i64() != Some(id));
    if in_chr {
        values.push(json!(id));
    }
    if values.is_empty() {
        object.remove(chr);
    } else {
        object.insert(chr.into(), json!(values));
    }
    // Older projects also persist visibility in Final Path metadata. Patch only
    // this one ID, never segments, biological coordinates, or other chr metadata.
    let mut path_changed = false;
    if let Some(path) = paths.get_mut(chr).and_then(Value::as_object_mut) {
        let mut ids = path
            .get("hiddenPrimaryCtgIds")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let was = ids.iter().any(|v| v.as_i64() == Some(id));
        if was != in_path {
            ids.retain(|v| v.as_i64() != Some(id));
            if in_path {
                ids.push(json!(id));
            }
            if ids.is_empty() {
                path.remove("hiddenPrimaryCtgIds");
            } else {
                path.insert("hiddenPrimaryCtgIds".into(), json!(ids));
            }
            path_changed = true;
        }
    }
    conn.execute("INSERT INTO project_assembly_view_state(project_id,updated_at) VALUES(?1,'0') ON CONFLICT(project_id) DO NOTHING",[project])?;
    conn.execute("UPDATE project_assembly_view_state SET hidden_primary_ctg_ids_json=?1,hidden_primary_ctg_ids_by_chr_json=?2 WHERE project_id=?3",params![list.to_string(),map.to_string(),project])?;
    if path_changed {
        conn.execute(
            "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1 WHERE project_id=?2",
            params![paths.to_string(), project],
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests;
