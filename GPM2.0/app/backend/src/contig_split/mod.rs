//! Non-destructive source-coordinate splitting. Preview never writes to the workspace.
//! All coordinates are 1-based inclusive; a cut at k partitions [a,k], [k+1,b].
mod paths;
#[cfg(test)]
mod tests;

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OpenFlags, params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub(crate) use paths::count_path_references;
pub(crate) use paths::rewrite_final_paths;

const MIN_RECOMMENDED_FRAGMENT_BP: i64 = 10_000;
const MIN_RECOMMENDED_COVERAGE: f64 = 60.0;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SplitPreviewParams {
    pub assembly_ctg_id: i64,
    #[serde(default)]
    pub cut_after: Vec<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SplitCommitParams {
    pub assembly_ctg_id: i64,
    pub cut_after: Vec<i64>,
    pub assignments: Vec<Option<String>>,
    pub preview_token: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitSource {
    pub assembly_ctg_id: i64,
    pub assembly_seq_id: i64,
    pub source_seq_id: i64,
    pub name: String,
    pub dataset_name: String,
    pub contig_name: String,
    pub source_start: i64,
    pub source_end: i64,
    pub source_length: i64,
    pub orient: String,
    pub assigned_chr_name: Option<String>,
    pub anchor_start: Option<i64>,
    pub instance_key: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitHit {
    pub id: i64,
    pub chr_name: String,
    pub strand: String,
    pub query_start: i64,
    pub query_end: i64,
    pub ref_start: i64,
    pub ref_end: i64,
    pub match_length: i64,
    pub block_length: i64,
    pub mapq: i64,
    // Retained for exact clipping, not transferred to the WebView.
    #[serde(skip)]
    pub cigar: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitCandidate {
    pub chr_name: String,
    pub coverage_bp: i64,
    pub coverage_percent: f64,
    pub high_quality_coverage_percent: f64,
    /// Weighted whole-hit identity, not a claim of per-base identity for the clipped interval.
    pub identity_percent: f64,
    pub min_mapq: i64,
    pub hit_count: usize,
    pub orient: String,
    pub anchor_start: i64,
    pub ref_start: i64,
    pub ref_end: i64,
    pub approximate: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitPart {
    pub source_start: i64,
    pub source_end: i64,
    pub length: i64,
    pub candidates: Vec<SplitCandidate>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitRecommendation {
    pub cut_after: Vec<i64>,
    pub region_start: i64,
    pub region_end: i64,
    pub kind: String,
    pub left_chr: String,
    pub right_chr: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitPreview {
    pub source: SplitSource,
    pub hits: Vec<SplitHit>,
    pub cut_after: Vec<i64>,
    pub parts: Vec<SplitPart>,
    pub recommendations: Vec<SplitRecommendation>,
    pub final_path_reference_count: usize,
    pub preview_token: String,
}

pub fn preview_contig_split(
    project_db: &Path,
    project_id: i64,
    params: &SplitPreviewParams,
) -> Result<SplitPreview> {
    let mut conn = Connection::open_with_flags(project_db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let tx = conn.transaction()?;
    let result = preview_with_connection(&tx, project_id, params)?;
    tx.commit()?;
    Ok(result)
}

pub(crate) fn preview_with_connection(
    conn: &Connection,
    project_id: i64,
    request: &SplitPreviewParams,
) -> Result<SplitPreview> {
    let source = load_split_source(conn, project_id, request.assembly_ctg_id)?;
    let cuts = validate_cuts(&source, &request.cut_after)?;
    let hits = load_source_hits(conn, project_id, &source)?;
    let parts = partition(&source, &cuts)
        .into_iter()
        .map(|(a, b)| {
            Ok(SplitPart {
                source_start: a,
                source_end: b,
                length: b - a + 1,
                candidates: rank_candidates(&hits, a, b)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let recommendations = recommend(&source, &hits)?;
    let final_path_reference_count = count_path_references(conn, project_id, &source)?;
    // Includes persisted dependencies so a dialog cannot overwrite edits made while it is open.
    let dependency: Vec<(String, String)> = {
        let mut q = conn.prepare("SELECT final_path_by_chr_json,degap_project_state_json FROM project_assembly_view_state WHERE project_id=?1")?;
        q.query_map([project_id], |r| Ok((r.get(0)?, r.get(1)?)))?
            .collect::<rusqlite::Result<_>>()?
    };
    let mut hash = Sha256::new();
    hash.update(serde_json::to_vec(&(&source, &hits, &cuts, &dependency))?);
    for hit in &hits {
        hash.update(hit.cigar.as_deref().unwrap_or(""));
    }
    let preview_token = format!("{:x}", hash.finalize());
    Ok(SplitPreview {
        source,
        hits,
        cut_after: cuts,
        parts,
        recommendations,
        final_path_reference_count,
        preview_token,
    })
}

pub(crate) fn load_source_hits(
    conn: &Connection,
    project_id: i64,
    source: &SplitSource,
) -> Result<Vec<SplitHit>> {
    let mut stmt = conn.prepare(
        "SELECT h.id,r.chr_name,h.strand,h.query_start,h.query_end,h.ref_start,h.ref_end,
                h.match_length,h.block_length,h.mapq,h.cg_tag
         FROM ref_alignment_hit h JOIN reference_chr r ON r.id=h.reference_chr_id
         JOIN project p ON p.reference_genome_id=r.reference_genome_id
         WHERE p.id=?1 AND h.source_seq_id=?2 AND h.query_end>=?3 AND h.query_start<=?4
         ORDER BY h.query_start,h.query_end,h.id",
    )?;
    let hits = stmt
        .query_map(
            params![
                project_id,
                source.source_seq_id,
                source.source_start,
                source.source_end
            ],
            |r| {
                Ok(SplitHit {
                    id: r.get(0)?,
                    chr_name: r.get(1)?,
                    strand: r.get(2)?,
                    query_start: r.get(3)?,
                    query_end: r.get(4)?,
                    ref_start: r.get(5)?,
                    ref_end: r.get(6)?,
                    match_length: r.get(7)?,
                    block_length: r.get(8)?,
                    mapq: r.get(9)?,
                    cigar: r.get(10)?,
                })
            },
        )?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(hits)
}

fn validate_cuts(source: &SplitSource, cuts: &[i64]) -> Result<Vec<i64>> {
    if cuts.len() > 32 {
        bail!("CTG_SPLIT_INVALID_CUT: at most 32 cuts per operation");
    }
    let mut sorted = cuts.to_vec();
    sorted.sort_unstable();
    sorted.dedup();
    if sorted.len() != cuts.len()
        || sorted
            .iter()
            .any(|k| *k < source.source_start || *k >= source.source_end)
    {
        bail!("CTG_SPLIT_INVALID_CUT: distinct cuts must lie inside the source interval");
    }
    Ok(sorted)
}

pub(crate) fn partition(source: &SplitSource, cuts: &[i64]) -> Vec<(i64, i64)> {
    let mut a = source.source_start;
    cuts.iter()
        .copied()
        .chain([source.source_end])
        .map(|b| {
            let part = (a, b);
            a = b + 1;
            part
        })
        .collect()
}

fn union_coverage(mut intervals: Vec<(i64, i64)>) -> i64 {
    intervals.sort_unstable();
    let mut total = 0;
    let mut end = 0;
    for (a, b) in intervals {
        let start = a.max(end + 1);
        if b >= start {
            total += b - start + 1;
        }
        end = end.max(b);
    }
    total
}

pub(crate) fn rank_candidates(
    hits: &[SplitHit],
    start: i64,
    end: i64,
) -> Result<Vec<SplitCandidate>> {
    type ClippedHit<'a> = (&'a SplitHit, i64, i64, i64, i64);
    let mut by_chr: BTreeMap<&str, Vec<ClippedHit<'_>>> = BTreeMap::new();
    for hit in hits {
        if hit.query_end < start || hit.query_start > end {
            continue;
        }
        for slice in crate::source_fragments::clip_alignment(
            hit.query_start,
            hit.query_end,
            hit.ref_start,
            hit.ref_end,
            &hit.strand,
            hit.cigar.as_deref(),
            (start, end),
            (hit.ref_start, hit.ref_end),
        )? {
            by_chr.entry(&hit.chr_name).or_default().push((
                hit,
                slice.query_start,
                slice.query_end,
                slice.target_start,
                slice.target_end,
            ));
        }
    }
    let length = (end - start + 1) as f64;
    let mut result = Vec::new();
    for (chr, rows) in by_chr {
        let coverage_bp = union_coverage(rows.iter().map(|r| (r.1, r.2)).collect());
        let hq = union_coverage(
            rows.iter()
                .filter(|r| r.0.mapq >= 20)
                .map(|r| (r.1, r.2))
                .collect(),
        );
        let plus = union_coverage(
            rows.iter()
                .filter(|r| r.0.strand == "+")
                .map(|r| (r.1, r.2))
                .collect(),
        );
        let minus = union_coverage(
            rows.iter()
                .filter(|r| r.0.strand == "-")
                .map(|r| (r.1, r.2))
                .collect(),
        );
        let orient = if minus > plus { "-" } else { "+" };
        let mut anchors: Vec<(i64, i64)> = rows
            .iter()
            .filter(|r| r.0.strand == orient)
            .map(|r| {
                let anchor = if orient == "+" {
                    r.3 - (r.1 - start)
                } else {
                    r.3 - (end - r.2)
                };
                (anchor, r.2 - r.1 + 1)
            })
            .collect();
        anchors.sort_unstable();
        let half = (anchors.iter().map(|r| r.1).sum::<i64>() + 1) / 2;
        let mut accum = 0;
        let anchor = anchors
            .iter()
            .find(|r| {
                accum += r.1;
                accum >= half
            })
            .map(|r| r.0)
            .unwrap_or(0);
        let weight = rows.iter().map(|r| (r.2 - r.1 + 1) as f64).sum::<f64>();
        let identity = rows
            .iter()
            .map(|r| {
                (r.2 - r.1 + 1) as f64 * r.0.match_length as f64 / r.0.block_length.max(1) as f64
            })
            .sum::<f64>()
            / weight.max(1.0)
            * 100.0;
        result.push(SplitCandidate {
            chr_name: chr.to_string(),
            coverage_bp,
            coverage_percent: coverage_bp as f64 / length * 100.0,
            high_quality_coverage_percent: hq as f64 / length * 100.0,
            identity_percent: identity,
            min_mapq: rows.iter().map(|r| r.0.mapq).min().unwrap_or(0),
            hit_count: rows.iter().map(|r| r.0.id).collect::<BTreeSet<_>>().len(),
            orient: orient.to_string(),
            anchor_start: anchor,
            ref_start: rows.iter().map(|r| r.3).min().unwrap_or(0),
            ref_end: rows.iter().map(|r| r.4).max().unwrap_or(0),
            approximate: rows.iter().any(|r| r.0.cigar.is_none()),
        });
    }
    result.sort_by(|a, b| {
        b.high_quality_coverage_percent
            .total_cmp(&a.high_quality_coverage_percent)
            .then(b.coverage_bp.cmp(&a.coverage_bp))
            .then(a.chr_name.cmp(&b.chr_name))
    });
    Ok(result)
}

fn recommend(source: &SplitSource, hits: &[SplitHit]) -> Result<Vec<SplitRecommendation>> {
    let strong: Vec<_> = hits
        .iter()
        .filter(|h| h.mapq >= 20 && h.query_end - h.query_start + 1 >= MIN_RECOMMENDED_FRAGMENT_BP)
        .collect();
    let mut recommendations = Vec::new();
    let mut seen = BTreeSet::new();
    for pair in strong.windows(2) {
        let (left, right) = (pair[0], pair[1]);
        if left.chr_name == right.chr_name || right.query_end <= left.query_end {
            continue;
        }
        let a = left.query_end.min(source.source_end - 1);
        let b = (right.query_start - 1).max(source.source_start);
        let kind = if a > b {
            "overlap"
        } else if a < b {
            "unaligned"
        } else {
            "boundary"
        };
        for cuts in [vec![a], vec![b], vec![a.min(b), a.max(b)]] {
            if cuts.len() == 2 && (kind != "unaligned" || a == b) {
                continue;
            }
            if validate_cuts(source, &cuts).is_err() || !seen.insert(cuts.clone()) {
                continue;
            }
            let intervals = partition(source, &cuts);
            let first = intervals[0];
            let last = *intervals.last().expect("partition nonempty");
            if first.1 - first.0 + 1 < MIN_RECOMMENDED_FRAGMENT_BP
                || last.1 - last.0 + 1 < MIN_RECOMMENDED_FRAGMENT_BP
            {
                continue;
            }
            let l = rank_candidates(hits, first.0, first.1)?;
            let r = rank_candidates(hits, last.0, last.1)?;
            let ambiguous = |candidates: &[SplitCandidate]| {
                candidates.len() > 1
                    && candidates[0].high_quality_coverage_percent
                        - candidates[1].high_quality_coverage_percent
                        < 10.0
            };
            if ambiguous(&l) || ambiguous(&r) {
                continue;
            }
            let (Some(l), Some(r)) = (l.first(), r.first()) else {
                continue;
            };
            if l.chr_name == r.chr_name
                || l.high_quality_coverage_percent < MIN_RECOMMENDED_COVERAGE
                || r.high_quality_coverage_percent < MIN_RECOMMENDED_COVERAGE
            {
                continue;
            }
            recommendations.push(SplitRecommendation {
                cut_after: cuts,
                region_start: a.min(b) + 1,
                region_end: a.max(b).max(a.min(b) + 1),
                kind: kind.to_string(),
                left_chr: l.chr_name.clone(),
                right_chr: r.chr_name.clone(),
            });
        }
    }
    Ok(recommendations)
}

pub(crate) fn load_split_source(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<SplitSource> {
    load_contig_source(conn, project_id, assembly_ctg_id, true)
}

// Cross-chromosome inspection/addition also supports auxiliary-dataset contigs;
// splitting retains its existing primary-only contract.
pub(crate) fn load_chr_alignment_source(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
) -> Result<SplitSource> {
    load_contig_source(conn, project_id, assembly_ctg_id, false)
}

fn load_contig_source(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
    primary_only: bool,
) -> Result<SplitSource> {
    conn.query_row(
        "SELECT c.id,s.id,s.source_seq_id,c.name,d.name,q.seq_name,s.source_start,s.source_end,
                q.length,s.orient,c.assigned_chr_name,c.anchor_start,s.instance_key
         FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id
         JOIN source_seq q ON q.id=s.source_seq_id JOIN dataset d ON d.id=q.dataset_id
         JOIN project p ON p.id=c.project_id
         WHERE c.id=?1 AND c.project_id=?2 AND s.project_id=?2 AND s.hidden=0
           AND (?3=0 OR q.dataset_id=p.primary_dataset_id)",
        params![assembly_ctg_id, project_id, primary_only],
        |r| {
            Ok(SplitSource {
                assembly_ctg_id: r.get(0)?,
                assembly_seq_id: r.get(1)?,
                source_seq_id: r.get(2)?,
                name: r.get(3)?,
                dataset_name: r.get(4)?,
                contig_name: r.get(5)?,
                source_start: r.get(6)?,
                source_end: r.get(7)?,
                source_length: r.get(8)?,
                orient: r.get(9)?,
                assigned_chr_name: r.get(10)?,
                anchor_start: r.get(11)?,
                instance_key: r.get(12)?,
            })
        },
    )
    .context("CTG_SPLIT_INVALID_TARGET: select a visible contig with an eligible source")
}
