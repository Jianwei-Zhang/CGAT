//! Assembly instances are non-N source intervals. The immutable source sequence
//! and source_seq_n_region rows retain every gap, including terminal/all-N runs.
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, params};

#[cfg(test)]
pub(crate) mod tests;

pub(crate) fn non_n_intervals(start: i64, end: i64, gaps: &[(i64, i64)]) -> Vec<(i64, i64)> {
    let mut result = Vec::new();
    let mut cursor = start;
    for &(left, right) in gaps {
        if right < cursor {
            continue;
        }
        if left > end {
            break;
        }
        if left > cursor {
            result.push((cursor, left - 1));
        }
        cursor = cursor.max(right.saturating_add(1));
        if cursor > end {
            break;
        }
    }
    if cursor <= end {
        result.push((cursor, end));
    }
    result
}

pub(crate) fn source_gaps(conn: &Connection, source_id: i64) -> Result<Vec<(i64, i64)>> {
    let mut stmt = conn.prepare(
        "SELECT start_bp, end_bp FROM source_seq_n_region WHERE source_seq_id = ?1 ORDER BY start_bp, end_bp",
    )?;
    Ok(stmt
        .query_map([source_id], |row| Ok((row.get(0)?, row.get(1)?)))?
        .collect::<std::result::Result<Vec<_>, _>>()?)
}

/// Called only while creating new assembly instances, inside the caller's
/// transaction. Existing edited projects are never repartitioned on open.
pub(crate) fn split_new_source_instances(
    conn: &Connection,
    project_id: i64,
    after_seq_id: i64,
) -> Result<()> {
    let mut stmt = conn.prepare(
        "SELECT c.id, s.id, s.source_seq_id, s.source_start, s.source_end,
                s.orient, s.instance_key, c.name, c.anchor_start
         FROM assembly_ctg c JOIN assembly_seq s ON s.id = c.assembly_seq_id
         WHERE c.project_id = ?1 AND s.hidden = 0 AND s.id > ?2
           AND s.instance_key NOT LIKE 'n-fragment:%'
           AND EXISTS (SELECT 1 FROM source_seq_n_region n
                       WHERE n.source_seq_id = s.source_seq_id
                         AND n.start_bp <= s.source_end AND n.end_bp >= s.source_start)
         ORDER BY c.id",
    )?;
    let rows = stmt
        .query_map([project_id, after_seq_id], |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, i64>(4)?,
                r.get::<_, String>(5)?,
                r.get::<_, String>(6)?,
                r.get::<_, String>(7)?,
                r.get::<_, Option<i64>>(8)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (ctg_id, seq_id, source_id, start, end, orient, key, name, anchor) in rows {
        let gaps = source_gaps(conn, source_id)?;
        let mut parts = non_n_intervals(start, end, &gaps);
        if orient == "-" {
            parts.reverse();
        }
        // Clone before updating the first instance so all original placement
        // and source metadata remain available to every sibling.
        for (index, &(left, right)) in parts
            .iter()
            .enumerate()
            .skip(1)
            .chain(parts.iter().enumerate().take(1))
        {
            let fragment_key = format!("n-fragment:{key}:{left}-{right}");
            let fragment_name = if let Some((base, chr)) = name.rsplit_once('@') {
                format!("{base}[{left}-{right}]@{chr}")
            } else {
                format!("{name}[{left}-{right}]")
            };
            let offset = if orient == "-" {
                end - right
            } else {
                left - start
            };
            let fragment_anchor = anchor.map(|value| value.saturating_add(offset));
            if index == 0 {
                conn.execute("UPDATE assembly_seq SET source_start=?1, source_end=?2, instance_key=?3 WHERE id=?4",
                    params![left, right, fragment_key, seq_id])?;
                conn.execute(
                    "UPDATE assembly_ctg SET name=?1, anchor_start=?2 WHERE id=?3",
                    params![fragment_name, fragment_anchor, ctg_id],
                )?;
            } else {
                conn.execute(
                    "INSERT INTO assembly_seq (project_id, source_seq_id, instance_key, orient,
                       source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
                     SELECT project_id, source_seq_id, ?1, orient, ?2, ?3,
                       'normal', 'normal', hidden, created_at, note FROM assembly_seq WHERE id=?4",
                    params![fragment_key, left, right, seq_id])?;
                let child_seq_id = conn.last_insert_rowid();
                conn.execute(
                    "INSERT INTO assembly_ctg (project_id, assembly_seq_id, name, assigned_chr_name,
                       chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
                     SELECT project_id, ?1, ?2, assigned_chr_name, chr_order, ?3,
                       ref_orient, placement_mode, created_at, note FROM assembly_ctg WHERE id=?4",
                    params![child_seq_id, fragment_name, fragment_anchor, ctg_id])?;
            }
        }
        if parts.is_empty() {
            // The source catalog (and any source-based Final Path) still owns
            // this all-N sequence. It is not an empty editable contig.
            conn.execute("DELETE FROM assembly_ctg WHERE id=?1", [ctg_id])?;
            conn.execute("DELETE FROM assembly_seq WHERE id=?1", [seq_id])?;
        }
    }
    Ok(())
}

/// Keep both ends of a clipped interval coupled. A CIGAR is preferred; legacy
/// endpoint-only evidence is explicitly approximate, never a Cartesian product
/// of independently clipped query and target intervals.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AlignmentSlice {
    pub query_start: i64,
    pub query_end: i64,
    pub target_start: i64,
    pub target_end: i64,
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn clip_alignment(
    qs: i64,
    qe: i64,
    ts: i64,
    te: i64,
    strand: &str,
    cigar: Option<&str>,
    query: (i64, i64),
    target: (i64, i64),
) -> Result<Vec<AlignmentSlice>> {
    if qs < 1 || qe < qs || ts < 1 || te < ts {
        bail!("invalid alignment interval");
    }
    let reversed = strand == "-";
    if let Some(cigar) = cigar.filter(|s| !s.is_empty()) {
        let mut q = if reversed { qe } else { qs };
        let mut t = ts;
        let mut n = 0_i64;
        let mut blocks: Vec<AlignmentSlice> = Vec::new();
        for ch in cigar.chars() {
            if let Some(d) = ch.to_digit(10) {
                n = n
                    .checked_mul(10)
                    .and_then(|n| n.checked_add(i64::from(d)))
                    .context("CIGAR length overflow")?;
                continue;
            }
            if n <= 0 {
                bail!("invalid CIGAR {cigar}");
            }
            match ch {
                'M' | '=' | 'X' => {
                    let (lo, hi) = if reversed {
                        (
                            (q - query.1).max(target.0 - t).max(0),
                            (q - query.0).min(target.1 - t).min(n - 1),
                        )
                    } else {
                        (
                            (query.0 - q).max(target.0 - t).max(0),
                            (query.1 - q).min(target.1 - t).min(n - 1),
                        )
                    };
                    if lo <= hi {
                        let block = AlignmentSlice {
                            query_start: if reversed { q - hi } else { q + lo },
                            query_end: if reversed { q - lo } else { q + hi },
                            target_start: t + lo,
                            target_end: t + hi,
                        };
                        blocks.push(block);
                    }
                    q += if reversed { -n } else { n };
                    t += n;
                }
                'I' => q += if reversed { -n } else { n },
                'D' | 'N' => t += n,
                _ => bail!("unsupported PAF CIGAR operation {ch}"),
            }
            n = 0;
        }
        if n != 0 || t != te + 1 || q != if reversed { qs - 1 } else { qe + 1 } {
            bail!("CIGAR does not match alignment endpoints");
        }
        // A single band can span ordinary indels within this pair of N-free
        // fragments. Its endpoints still come from the alignment path.
        return Ok(match (blocks.first(), blocks.last()) {
            (Some(first), Some(last)) => vec![AlignmentSlice {
                query_start: first.query_start.min(last.query_start),
                query_end: first.query_end.max(last.query_end),
                target_start: first.target_start,
                target_end: last.target_end,
            }],
            _ => Vec::new(),
        });
    }
    let qlen = (qe - qs + 1) as f64;
    let tlen = (te - ts + 1) as f64;
    let (qlo, qhi) = if reversed {
        (
            (qe - query.1) as f64 / qlen,
            (qe - query.0 + 1) as f64 / qlen,
        )
    } else {
        (
            (query.0 - qs) as f64 / qlen,
            (query.1 - qs + 1) as f64 / qlen,
        )
    };
    let lo = qlo.max((target.0 - ts) as f64 / tlen).max(0.0);
    let hi = qhi.min((target.1 - ts + 1) as f64 / tlen).min(1.0);
    if hi <= lo {
        return Ok(Vec::new());
    }
    let (left, right) = if reversed {
        (
            qe - (hi * qlen).ceil() as i64 + 1,
            qe - (lo * qlen).floor() as i64,
        )
    } else {
        (
            qs + (lo * qlen).floor() as i64,
            qs + (hi * qlen).ceil() as i64 - 1,
        )
    };
    Ok(vec![AlignmentSlice {
        query_start: left.max(query.0).max(qs),
        query_end: right.min(query.1).min(qe),
        target_start: (ts + (lo * tlen).floor() as i64).max(target.0).max(ts),
        target_end: (ts + (hi * tlen).ceil() as i64 - 1).min(target.1).min(te),
    }])
}
