//! Reference chromosome segments (N-free spans) materialized from the
//! reference FASTA, so page loads do not re-read the sequence on every visit.
use std::collections::{HashMap, HashSet};
use std::path::Path;

use anyhow::{Context, Result, anyhow};
use rusqlite::{Connection, params};

use crate::reference_segments::{MIN_GAP_RUN_BP, ReferenceSegment, detect_reference_segments};

/// Segments already stored for this chromosome.
pub(crate) fn persisted_reference_segments(
    conn: &Connection,
    reference_chr_id: i64,
) -> Result<Option<Vec<ReferenceSegment>>> {
    let mut stmt = conn
        .prepare(
            "SELECT segment_order, start_bp, end_bp, rc.chr_name
             FROM reference_chr_segment rcs
             JOIN reference_chr rc ON rc.id = rcs.reference_chr_id
             WHERE rcs.reference_chr_id = ?1
             ORDER BY rcs.segment_order, rcs.start_bp",
        )
        .context("failed to prepare reference segment query")?;
    let rows = stmt
        .query_map([reference_chr_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .context("failed to query reference segments")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode reference segments")?;
    if rows.is_empty() {
        return Ok(None);
    }
    Ok(Some(
        rows.into_iter()
            .map(
                |(segment_order, start_bp, end_bp, chr_name)| ReferenceSegment {
                    reference_chr_name: chr_name,
                    segment_order,
                    start_bp,
                    end_bp,
                },
            )
            .collect(),
    ))
}

/// Read one chromosome through the FASTA index and persist its segments.
/// Returns `None` for packages without FASTA payloads (Light / no_fasta).
pub(crate) fn materialize_reference_segments(
    conn: &Connection,
    reference_chr_id: i64,
    chr_name: &str,
    reference_fasta_path: &str,
) -> Result<Option<Vec<ReferenceSegment>>> {
    if reference_fasta_path.trim().is_empty() || !Path::new(reference_fasta_path).is_file() {
        return Ok(None);
    }
    let names = HashSet::from([chr_name.to_string()]);
    let Ok(mut sequences) =
        crate::exporter::load_named_sequences_from_fasta(Path::new(reference_fasta_path), &names)
    else {
        return Ok(None);
    };
    let Some(sequence) = sequences.remove(chr_name) else {
        return Ok(None);
    };
    let segments = detect_reference_segments(chr_name, &sequence, MIN_GAP_RUN_BP);
    store_reference_segments(conn, reference_chr_id, &segments)?;
    Ok(Some(segments))
}

/// Parse a server `metadata/reference_segments.tsv` into per-chromosome spans.
/// Chromosomes absent from the file are simply not described by it.
pub(crate) fn read_reference_segments_tsv(
    path: &Path,
) -> Result<HashMap<String, Vec<ReferenceSegment>>> {
    let file =
        std::fs::File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = std::io::BufReader::new(file);
    let mut lines = std::io::BufRead::lines(reader);
    let header_line = lines
        .next()
        .transpose()
        .with_context(|| format!("failed to read header from {}", path.display()))?
        .ok_or_else(|| anyhow!("missing header in {}", path.display()))?;
    let header = header_line.split('\t').collect::<Vec<_>>();
    let name_col = column_index(&header, "reference_chr_name", path)?;
    let order_col = column_index(&header, "segment_order", path)?;
    let start_col = column_index(&header, "segment_start_bp", path)?;
    let end_col = column_index(&header, "segment_end_bp", path)?;

    let mut result = HashMap::<String, Vec<ReferenceSegment>>::new();
    for (line_index, line) in lines.enumerate() {
        let line = line.with_context(|| {
            format!(
                "failed to read line {} from {}",
                line_index + 2,
                path.display()
            )
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let columns = line.split('\t').collect::<Vec<_>>();
        let chr_name = columns.get(name_col).copied().unwrap_or("").trim();
        if chr_name.is_empty() {
            continue;
        }
        let segment_order = parse_tsv_int(
            columns.get(order_col).copied(),
            "segment_order",
            path,
            line_index + 2,
        )?;
        let start_bp = parse_tsv_int(
            columns.get(start_col).copied(),
            "segment_start_bp",
            path,
            line_index + 2,
        )?;
        let end_bp = parse_tsv_int(
            columns.get(end_col).copied(),
            "segment_end_bp",
            path,
            line_index + 2,
        )?;
        if end_bp < start_bp {
            bail_tsv(path, line_index + 2, "segment_end_bp < segment_start_bp")?;
        }
        result
            .entry(chr_name.to_string())
            .or_default()
            .push(ReferenceSegment {
                reference_chr_name: chr_name.to_string(),
                segment_order,
                start_bp,
                end_bp,
            });
    }
    for segments in result.values_mut() {
        segments.sort_by_key(|segment| (segment.segment_order, segment.start_bp, segment.end_bp));
    }
    Ok(result)
}

fn column_index(header: &[&str], name: &str, path: &Path) -> Result<usize> {
    header
        .iter()
        .position(|field| field.trim() == name)
        .ok_or_else(|| anyhow!("{} is missing column {}", path.display(), name))
}

fn parse_tsv_int(value: Option<&str>, label: &str, path: &Path, line: usize) -> Result<i64> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| anyhow!("{} line {} is missing {}", path.display(), line, label))?
        .parse::<i64>()
        .with_context(|| format!("{} line {} has an invalid {}", path.display(), line, label))
}

fn bail_tsv(path: &Path, line: usize, reason: &str) -> Result<()> {
    Err(anyhow!("{} line {} has {}", path.display(), line, reason))
}

pub(crate) fn store_reference_segments(
    conn: &Connection,
    reference_chr_id: i64,
    segments: &[ReferenceSegment],
) -> Result<()> {
    conn.execute(
        "DELETE FROM reference_chr_segment WHERE reference_chr_id = ?1",
        [reference_chr_id],
    )
    .context("failed to clear reference segments")?;
    let mut stmt = conn
        .prepare(
            "INSERT OR REPLACE INTO reference_chr_segment (
                reference_chr_id, segment_order, start_bp, end_bp
             ) VALUES (?1, ?2, ?3, ?4)",
        )
        .context("failed to prepare reference segment insert")?;
    for segment in segments {
        stmt.execute(params![
            reference_chr_id,
            segment.segment_order,
            segment.start_bp,
            segment.end_bp
        ])
        .context("failed to insert reference segment")?;
    }
    Ok(())
}

/// Fill missing geometry for every chromosome of a reference genome. Used at
/// import time so interactive page loads never touch the FASTA.
pub(crate) fn materialize_reference_genome(
    conn: &Connection,
    reference_genome_id: i64,
    reference_fasta_path: &str,
    reference_segments_tsv: Option<&Path>,
) -> Result<usize> {
    let described = match reference_segments_tsv.filter(|path| path.is_file()) {
        Some(path) => read_reference_segments_tsv(path)?,
        None => HashMap::new(),
    };
    let mut stmt = conn
        .prepare(
            "SELECT rc.id, rc.chr_name FROM reference_chr rc
             WHERE rc.reference_genome_id = ?1
             ORDER BY rc.chr_order, rc.id",
        )
        .context("failed to prepare reference chromosome query")?;
    let chromosomes = stmt
        .query_map([reference_genome_id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .context("failed to query reference chromosomes")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode reference chromosomes")?;
    let mut stored = 0_usize;
    for (chr_id, chr_name) in chromosomes {
        // The server already derived the spans at packaging time; trust that
        // description and only fall back to scanning the FASTA when a
        // chromosome is not covered by it.
        if let Some(segments) = described.get(&chr_name) {
            if segments.is_empty() {
                continue;
            }
            store_reference_segments(conn, chr_id, segments)?;
            stored += segments.len();
            continue;
        }
        if let Some(segments) =
            materialize_reference_segments(conn, chr_id, &chr_name, reference_fasta_path)?
        {
            stored += segments.len();
        }
    }
    Ok(stored)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seed_reference(conn: &Connection, chr_name: &str, length: i64) -> i64 {
        crate::db::init_workspace_schema(conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', '', '')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, ?1, 1, ?2)",
            params![chr_name, length],
        )
        .unwrap();
        1
    }

    #[test]
    fn persisted_segments_round_trip_without_the_fasta() {
        let temp = tempfile::tempdir().unwrap();
        let conn = Connection::open(temp.path().join("project.sqlite")).unwrap();
        let chr_id = seed_reference(&conn, "chr1", 12);
        let sequence = format!(
            "{}ACGT{}TT{}",
            "N".repeat(100),
            "N".repeat(150),
            "N".repeat(100)
        );
        let fasta = temp.path().join("ref.fa");
        std::fs::write(&fasta, format!(">chr1\n{sequence}\n")).unwrap();

        let segments =
            materialize_reference_segments(&conn, chr_id, "chr1", &fasta.to_string_lossy())
                .unwrap()
                .expect("segments materialized");
        assert_eq!(segments.len(), 2);
        assert_eq!((segments[0].start_bp, segments[0].end_bp), (101, 104));
        assert_eq!((segments[1].start_bp, segments[1].end_bp), (255, 256));

        // Later visits read the table only: remove the FASTA payload and the
        // geometry must still resolve.
        std::fs::remove_file(&fasta).unwrap();
        let cached = persisted_reference_segments(&conn, chr_id)
            .unwrap()
            .expect("segments served from the database");
        assert_eq!(cached, segments);
    }

    #[test]
    fn packages_without_fasta_keep_the_fallback_path() {
        let temp = tempfile::tempdir().unwrap();
        let conn = Connection::open(temp.path().join("project.sqlite")).unwrap();
        let chr_id = seed_reference(&conn, "chr1", 40);
        let missing = temp.path().join("missing.fa");
        assert!(
            materialize_reference_segments(&conn, chr_id, "chr1", &missing.to_string_lossy())
                .unwrap()
                .is_none()
        );
        assert!(
            persisted_reference_segments(&conn, chr_id)
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn packaged_reference_segments_win_over_the_fasta_and_need_no_payload() {
        let temp = tempfile::tempdir().unwrap();
        let conn = Connection::open(temp.path().join("project.sqlite")).unwrap();
        let chr_id = seed_reference(&conn, "chr1", 20);
        let metadata = temp.path().join("reference_segments.tsv");
        std::fs::write(
            &metadata,
            "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n\
             chr1\t1\t1\t5\nchr1\t2\t11\t20\nchr2\t1\t1\t9\n",
        )
        .unwrap();
        let missing_fasta = temp.path().join("missing.fa");

        // No FASTA payload at all: the packaged description is authoritative.
        assert_eq!(
            materialize_reference_genome(
                &conn,
                1,
                &missing_fasta.to_string_lossy(),
                Some(&metadata),
            )
            .unwrap(),
            2
        );
        let stored = persisted_reference_segments(&conn, chr_id)
            .unwrap()
            .unwrap();
        assert_eq!(
            stored
                .iter()
                .map(|segment| (segment.start_bp, segment.end_bp))
                .collect::<Vec<_>>(),
            vec![(1, 5), (11, 20)]
        );
    }

    #[test]
    fn unlisted_chromosomes_still_fall_back_to_the_fasta() {
        let temp = tempfile::tempdir().unwrap();
        let conn = Connection::open(temp.path().join("project.sqlite")).unwrap();
        let chr_id = seed_reference(&conn, "chr9", 4);
        let fasta = temp.path().join("ref.fa");
        std::fs::write(&fasta, ">chr9\nACGT\n").unwrap();
        let metadata = temp.path().join("reference_segments.tsv");
        std::fs::write(
            &metadata,
            "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\nchr1\t1\t1\t5\n",
        )
        .unwrap();

        assert_eq!(
            materialize_reference_genome(&conn, 1, &fasta.to_string_lossy(), Some(&metadata))
                .unwrap(),
            1
        );
        assert_eq!(
            persisted_reference_segments(&conn, chr_id)
                .unwrap()
                .unwrap()[0]
                .end_bp,
            4
        );
    }

    #[test]
    fn genome_materialization_covers_every_chromosome() {
        let temp = tempfile::tempdir().unwrap();
        let conn = Connection::open(temp.path().join("project.sqlite")).unwrap();
        let chr_id = seed_reference(&conn, "chr1", 4);
        let fasta = temp.path().join("ref.fa");
        std::fs::write(&fasta, ">chr1\nACGT\n").unwrap();
        assert_eq!(
            materialize_reference_genome(&conn, 1, &fasta.to_string_lossy(), None).unwrap(),
            1
        );
        assert_eq!(
            persisted_reference_segments(&conn, chr_id)
                .unwrap()
                .unwrap()[0]
                .end_bp,
            4
        );
    }
}
