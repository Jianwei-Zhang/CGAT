use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, params};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AlignmentCacheLoadSummary {
    pub project_id: i64,
    pub loaded_dataset_count: i64,
    pub loaded_hit_count: i64,
    pub skipped_dataset_count: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ParsedPafHit {
    query_name: String,
    target_name: String,
    strand: String,
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    ref_end: i64,
    match_length: i64,
    block_length: i64,
    mapq: i64,
    cg_tag: Option<String>,
}

enum RefHitClearScope {
    Dataset(i64),
    SourceSeq(i64),
}

struct RefPafLoadParams<'a> {
    dataset_id: i64,
    clear_scope: RefHitClearScope,
    run_name: &'a str,
    run_paf_path: &'a Path,
    source_seq_by_name: &'a HashMap<String, i64>,
    ref_chr_by_name: &'a HashMap<String, i64>,
}

pub fn ensure_project_ref_alignment_hits(
    conn: &mut Connection,
    project_id: i64,
) -> Result<AlignmentCacheLoadSummary> {
    let mut never_cancel = || false;
    ensure_project_ref_alignment_hits_with_cancel(conn, project_id, &mut never_cancel)
}

pub fn ensure_project_ref_alignment_hits_with_cancel<F>(
    conn: &mut Connection,
    project_id: i64,
    should_cancel: &mut F,
) -> Result<AlignmentCacheLoadSummary>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    let reference_genome_id: i64 = conn.query_row(
        "SELECT reference_genome_id FROM project WHERE id = ?1",
        params![project_id],
        |row| row.get(0),
    )?;

    let chr_rows = {
        let mut chr_stmt = conn.prepare(
            "SELECT id, chr_name
             FROM reference_chr
             WHERE reference_genome_id = ?1",
        )?;
        chr_stmt
            .query_map(params![reference_genome_id], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let mut ref_chr_by_name = HashMap::new();
    for (chr_id, chr_name) in chr_rows {
        ref_chr_by_name.insert(chr_name, chr_id);
    }

    let dataset_rows = {
        let mut dataset_stmt = conn.prepare(
            "SELECT d.id, d.name, d.fasta_path
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY pd.display_order, d.id",
        )?;
        dataset_stmt
            .query_map(params![project_id], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };

    let mut loaded_dataset_count = 0_i64;
    let mut loaded_hit_count = 0_i64;
    let mut skipped_dataset_count = 0_i64;

    for (dataset_id, dataset_name, fasta_path) in dataset_rows {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }

        let existing_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ref_alignment_hit WHERE dataset_id = ?1",
            params![dataset_id],
            |row| row.get(0),
        )?;
        if existing_count > 0 {
            skipped_dataset_count += 1;
            continue;
        }

        let Some(bundle_root) = derive_bundle_root_from_dataset_fasta(Path::new(&fasta_path))
        else {
            skipped_dataset_count += 1;
            continue;
        };
        let run_name = format!("{}_vs_ref", dataset_name);
        let run_paf = bundle_root.join("runs").join(&run_name).join("result.paf");
        if !run_paf.exists() {
            skipped_dataset_count += 1;
            continue;
        }

        let source_rows = {
            let mut source_stmt = conn.prepare(
                "SELECT id, seq_name
                 FROM source_seq
                 WHERE dataset_id = ?1",
            )?;
            source_stmt
                .query_map(params![dataset_id], |row| {
                    Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()?
        };
        let mut source_seq_by_name = HashMap::new();
        for (source_seq_id, seq_name) in source_rows {
            source_seq_by_name.insert(seq_name, source_seq_id);
        }

        let tx = conn.transaction()?;
        let inserted = load_ref_paf_hits_for_dataset(
            &tx,
            dataset_id,
            &run_name,
            &run_paf,
            &source_seq_by_name,
            &ref_chr_by_name,
            should_cancel,
        )?;
        tx.commit()?;

        loaded_dataset_count += 1;
        loaded_hit_count += inserted;
    }

    Ok(AlignmentCacheLoadSummary {
        project_id,
        loaded_dataset_count,
        loaded_hit_count,
        skipped_dataset_count,
    })
}

const REF_PAF_PARALLEL_PARSE_MAX_BYTES: u64 = 32 * 1024 * 1024;
const REF_PAF_CANCEL_POLL: std::time::Duration = std::time::Duration::from_millis(20);

pub fn index_bundle_ref_alignment_hits_with_cancel<F, P>(
    conn: &mut Connection,
    bundle_root: &Path,
    workers: usize,
    should_cancel: &mut F,
    on_dataset: &mut P,
) -> Result<AlignmentCacheLoadSummary>
where
    F: FnMut() -> bool,
    P: FnMut(&str, &Path),
{
    if should_cancel() {
        bail!("import cancelled");
    }

    let chr_rows = {
        let mut chr_stmt = conn.prepare(
            "SELECT rc.id, rc.chr_name
             FROM reference_chr rc
             JOIN reference_genome rg ON rg.id = rc.reference_genome_id
             ORDER BY rg.id, rc.chr_order",
        )?;
        chr_stmt
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let mut ref_chr_by_name = HashMap::new();
    for (chr_id, chr_name) in chr_rows {
        ref_chr_by_name.insert(chr_name, chr_id);
    }

    let dataset_rows = {
        let mut dataset_stmt = conn.prepare(
            "SELECT id, name
             FROM dataset
             ORDER BY id",
        )?;
        dataset_stmt
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };

    let mut jobs = Vec::new();
    let mut skipped_dataset_count = 0_i64;
    for (dataset_id, dataset_name) in dataset_rows {
        let run_name = format!("{}_vs_ref", dataset_name);
        let run_paf = bundle_root.join("runs").join(&run_name).join("result.paf");
        if !run_paf.exists() {
            skipped_dataset_count += 1;
            continue;
        }

        let source_rows = {
            let mut source_stmt = conn.prepare(
                "SELECT id, seq_name
                 FROM source_seq
                 WHERE dataset_id = ?1",
            )?;
            source_stmt
                .query_map(params![dataset_id], |row| {
                    Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()?
        };
        let mut source_seq_by_name = HashMap::new();
        for (source_seq_id, seq_name) in source_rows {
            source_seq_by_name.insert(seq_name, source_seq_id);
        }

        jobs.push(RefPafDatasetJob {
            dataset_id,
            run_name,
            run_paf,
            source_seq_by_name,
        });
    }

    let worker_count = workers.max(1);
    let mut loaded_dataset_count = 0_i64;
    let mut loaded_hit_count = 0_i64;
    for chunk in jobs.chunks(worker_count) {
        if should_cancel() {
            bail!("import cancelled");
        }
        // One progress step per dataset keeps the caller-facing order identical
        // to the sequential walk, even when the chunk is parsed in parallel.
        for job in chunk {
            on_dataset(&job.run_name, &job.run_paf);
        }
        let parsed = parse_ref_paf_chunk(chunk, &ref_chr_by_name, worker_count, should_cancel);
        for (job, rows) in chunk.iter().zip(parsed) {
            let rows = rows?;
            if should_cancel() {
                bail!("import cancelled");
            }
            // SQLite has a single writer, so every chunk is still committed on
            // the caller thread and in dataset order.
            let tx = conn.transaction()?;
            tx.execute(
                "DELETE FROM ref_alignment_hit WHERE dataset_id = ?1",
                params![job.dataset_id],
            )
            .context("failed to clear old ref_alignment_hit rows for dataset")?;
            let inserted = insert_ref_paf_hit_rows(&tx, job.dataset_id, &job.run_name, &rows)?;
            tx.commit()?;
            loaded_dataset_count += 1;
            loaded_hit_count += inserted;
        }
    }

    Ok(AlignmentCacheLoadSummary {
        project_id: 0,
        loaded_dataset_count,
        loaded_hit_count,
        skipped_dataset_count,
    })
}

/// Parses one worker-sized chunk of datasets. Large PAFs are parsed on the
/// caller thread because buffering every row of a huge file per worker would
/// otherwise scale memory with the worker budget.
fn parse_ref_paf_chunk<F>(
    jobs: &[RefPafDatasetJob],
    ref_chr_by_name: &HashMap<String, i64>,
    worker_count: usize,
    should_cancel: &mut F,
) -> Vec<Result<Vec<RefPafHitRow>>>
where
    F: FnMut() -> bool,
{
    let parallel_safe = worker_count > 1
        && jobs.len() > 1
        && jobs.iter().all(|job| {
            std::fs::metadata(&job.run_paf)
                .map(|metadata| metadata.len() <= REF_PAF_PARALLEL_PARSE_MAX_BYTES)
                .unwrap_or(false)
        });
    if !parallel_safe {
        return jobs
            .iter()
            .map(|job| {
                parse_ref_paf_hits(
                    &job.run_paf,
                    &job.source_seq_by_name,
                    ref_chr_by_name,
                    should_cancel,
                )
            })
            .collect();
    }
    parse_ref_paf_jobs_in_parallel(jobs, ref_chr_by_name, should_cancel)
}

fn parse_ref_paf_jobs_in_parallel<F>(
    jobs: &[RefPafDatasetJob],
    ref_chr_by_name: &HashMap<String, i64>,
    should_cancel: &mut F,
) -> Vec<Result<Vec<RefPafHitRow>>>
where
    F: FnMut() -> bool,
{
    use std::sync::atomic::{AtomicBool, Ordering};

    let cancelled = AtomicBool::new(false);
    std::thread::scope(|scope| {
        let handles = jobs
            .iter()
            .map(|job| {
                let cancelled = &cancelled;
                scope.spawn(move || {
                    let mut worker_cancel = || cancelled.load(Ordering::Acquire);
                    parse_ref_paf_hits(
                        &job.run_paf,
                        &job.source_seq_by_name,
                        ref_chr_by_name,
                        &mut worker_cancel,
                    )
                })
            })
            .collect::<Vec<_>>();
        while !handles.iter().all(|handle| handle.is_finished()) {
            if should_cancel() {
                cancelled.store(true, Ordering::Release);
            }
            std::thread::sleep(REF_PAF_CANCEL_POLL);
        }
        handles
            .into_iter()
            .map(|handle| {
                handle
                    .join()
                    .unwrap_or_else(|_| Err(anyhow::anyhow!("reference PAF parser panicked")))
            })
            .collect()
    })
}

pub fn index_bundle_ref_alignment_hits_for_dataset_with_cancel<F, P>(
    conn: &mut Connection,
    bundle_root: &Path,
    dataset_id: i64,
    dataset_name: &str,
    should_cancel: &mut F,
    on_dataset: &mut P,
) -> Result<AlignmentCacheLoadSummary>
where
    F: FnMut() -> bool,
    P: FnMut(&str, &Path),
{
    if should_cancel() {
        bail!("import cancelled");
    }

    let chr_rows = {
        let mut chr_stmt = conn.prepare(
            "SELECT rc.id, rc.chr_name
             FROM reference_chr rc
             JOIN reference_genome rg ON rg.id = rc.reference_genome_id
             ORDER BY rg.id, rc.chr_order",
        )?;
        chr_stmt
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let mut ref_chr_by_name = HashMap::new();
    for (chr_id, chr_name) in chr_rows {
        ref_chr_by_name.insert(chr_name, chr_id);
    }

    let run_name = format!("{}_vs_ref", dataset_name);
    let run_paf = bundle_root.join("runs").join(&run_name).join("result.paf");
    if !run_paf.exists() {
        return Ok(AlignmentCacheLoadSummary {
            project_id: 0,
            loaded_dataset_count: 0,
            loaded_hit_count: 0,
            skipped_dataset_count: 1,
        });
    }
    on_dataset(&run_name, &run_paf);

    let source_rows = {
        let mut source_stmt = conn.prepare(
            "SELECT id, seq_name
             FROM source_seq
             WHERE dataset_id = ?1",
        )?;
        source_stmt
            .query_map(params![dataset_id], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let mut source_seq_by_name = HashMap::new();
    for (source_seq_id, seq_name) in source_rows {
        source_seq_by_name.insert(seq_name, source_seq_id);
    }

    let tx = conn.transaction()?;
    let inserted = load_ref_paf_hits_for_dataset(
        &tx,
        dataset_id,
        &run_name,
        &run_paf,
        &source_seq_by_name,
        &ref_chr_by_name,
        should_cancel,
    )?;
    tx.commit()?;

    Ok(AlignmentCacheLoadSummary {
        project_id: 0,
        loaded_dataset_count: 1,
        loaded_hit_count: inserted,
        skipped_dataset_count: 0,
    })
}

pub fn index_ref_alignment_hits_for_source_seq_with_cancel<F>(
    conn: &mut Connection,
    dataset_id: i64,
    source_seq_id: i64,
    seq_name: &str,
    run_name: &str,
    run_paf_path: &Path,
    should_cancel: &mut F,
) -> Result<i64>
where
    F: FnMut() -> bool,
{
    if should_cancel() {
        bail!("import cancelled");
    }

    let chr_rows = {
        let mut chr_stmt = conn.prepare(
            "SELECT rc.id, rc.chr_name
             FROM reference_chr rc
             JOIN reference_genome rg ON rg.id = rc.reference_genome_id
             ORDER BY rg.id, rc.chr_order",
        )?;
        chr_stmt
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?
    };
    let mut ref_chr_by_name = HashMap::new();
    for (chr_id, chr_name) in chr_rows {
        ref_chr_by_name.insert(chr_name, chr_id);
    }

    let mut source_seq_by_name = HashMap::new();
    source_seq_by_name.insert(seq_name.to_string(), source_seq_id);
    load_ref_paf_hits(
        conn,
        RefPafLoadParams {
            dataset_id,
            clear_scope: RefHitClearScope::SourceSeq(source_seq_id),
            run_name,
            run_paf_path,
            source_seq_by_name: &source_seq_by_name,
            ref_chr_by_name: &ref_chr_by_name,
        },
        should_cancel,
    )
}

fn derive_bundle_root_from_dataset_fasta(fasta_path: &Path) -> Option<PathBuf> {
    let datasets_dir = fasta_path.parent()?;
    if datasets_dir
        .file_name()?
        .to_string_lossy()
        .to_ascii_lowercase()
        != "datasets"
    {
        return None;
    }
    let data_dir = datasets_dir.parent()?;
    if data_dir.file_name()?.to_string_lossy().to_ascii_lowercase() != "data" {
        return None;
    }
    Some(data_dir.parent()?.to_path_buf())
}

fn load_ref_paf_hits_for_dataset(
    conn: &Connection,
    dataset_id: i64,
    run_name: &str,
    run_paf_path: &Path,
    source_seq_by_name: &HashMap<String, i64>,
    ref_chr_by_name: &HashMap<String, i64>,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<i64> {
    load_ref_paf_hits(
        conn,
        RefPafLoadParams {
            dataset_id,
            clear_scope: RefHitClearScope::Dataset(dataset_id),
            run_name,
            run_paf_path,
            source_seq_by_name,
            ref_chr_by_name,
        },
        should_cancel,
    )
}

/// One parsed reference alignment row, independent of any database handle so
/// that PAF text can be parsed on a worker thread before it is written.
#[derive(Debug)]
struct RefPafHitRow {
    source_seq_id: i64,
    reference_chr_id: i64,
    strand: String,
    query_start: i64,
    query_end: i64,
    ref_start: i64,
    ref_end: i64,
    match_length: i64,
    block_length: i64,
    mapq: i64,
    cg_tag: Option<String>,
}

/// One dataset that still has to be loaded, prepared on the caller thread so
/// workers only ever read files and never touch the connection.
struct RefPafDatasetJob {
    dataset_id: i64,
    run_name: String,
    run_paf: PathBuf,
    source_seq_by_name: HashMap<String, i64>,
}

fn clear_ref_alignment_hits(conn: &Connection, clear_scope: RefHitClearScope) -> Result<()> {
    match clear_scope {
        RefHitClearScope::Dataset(clear_dataset_id) => {
            conn.execute(
                "DELETE FROM ref_alignment_hit WHERE dataset_id = ?1",
                params![clear_dataset_id],
            )
            .context("failed to clear old ref_alignment_hit rows for dataset")?;
        }
        RefHitClearScope::SourceSeq(clear_source_seq_id) => {
            conn.execute(
                "DELETE FROM ref_alignment_hit WHERE source_seq_id = ?1",
                params![clear_source_seq_id],
            )
            .context("failed to clear old ref_alignment_hit rows for source_seq")?;
        }
    }
    Ok(())
}

fn parse_ref_paf_hits<C>(
    run_paf_path: &Path,
    source_seq_by_name: &HashMap<String, i64>,
    ref_chr_by_name: &HashMap<String, i64>,
    should_cancel: &mut C,
) -> Result<Vec<RefPafHitRow>>
where
    C: FnMut() -> bool,
{
    let file = File::open(run_paf_path)
        .with_context(|| format!("failed to open paf file {}", run_paf_path.display()))?;
    let reader = BufReader::new(file);
    let mut rows = Vec::new();
    for line in reader.lines() {
        if should_cancel() {
            bail!("auto pipeline cancelled");
        }

        let line = line.with_context(|| {
            format!(
                "failed to read paf line from {}",
                run_paf_path.as_os_str().to_string_lossy()
            )
        })?;
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some(hit) = parse_paf_line(trimmed) else {
            continue;
        };
        let Some(source_seq_id) = source_seq_by_name.get(&hit.query_name) else {
            continue;
        };
        let Some(reference_chr_id) = ref_chr_by_name.get(&hit.target_name) else {
            continue;
        };

        rows.push(RefPafHitRow {
            source_seq_id: *source_seq_id,
            reference_chr_id: *reference_chr_id,
            strand: hit.strand,
            query_start: hit.query_start,
            query_end: hit.query_end,
            ref_start: hit.ref_start,
            ref_end: hit.ref_end,
            match_length: hit.match_length,
            block_length: hit.block_length,
            mapq: hit.mapq,
            cg_tag: hit.cg_tag,
        });
    }
    Ok(rows)
}

fn insert_ref_paf_hit_rows(
    conn: &Connection,
    dataset_id: i64,
    run_name: &str,
    rows: &[RefPafHitRow],
) -> Result<i64> {
    if rows.is_empty() {
        return Ok(0);
    }
    let mut insert_stmt = conn.prepare(
        "INSERT INTO ref_alignment_hit (
            dataset_id, source_seq_id, reference_chr_id, strand,
            query_start, query_end, ref_start, ref_end,
            match_length, block_length, mapq, cg_tag, run_name, note
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, NULL)",
    )?;
    for row in rows {
        insert_stmt.execute(params![
            dataset_id,
            row.source_seq_id,
            row.reference_chr_id,
            &row.strand,
            row.query_start,
            row.query_end,
            row.ref_start,
            row.ref_end,
            row.match_length,
            row.block_length,
            row.mapq,
            row.cg_tag.as_deref(),
            run_name
        ])?;
    }
    Ok(rows.len() as i64)
}

fn load_ref_paf_hits(
    conn: &Connection,
    params: RefPafLoadParams<'_>,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<i64> {
    let RefPafLoadParams {
        dataset_id,
        clear_scope,
        run_name,
        run_paf_path,
        source_seq_by_name,
        ref_chr_by_name,
    } = params;
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

    clear_ref_alignment_hits(conn, clear_scope)?;
    let rows = parse_ref_paf_hits(
        run_paf_path,
        source_seq_by_name,
        ref_chr_by_name,
        should_cancel,
    )?;
    insert_ref_paf_hit_rows(conn, dataset_id, run_name, &rows)
}

fn parse_paf_line(line: &str) -> Option<ParsedPafHit> {
    let mut fields = line.split('\t');
    let query_name = fields.next()?.to_string();
    let _query_length = fields.next()?.parse::<i64>().ok()?;
    let query_start_0 = fields.next()?.parse::<i64>().ok()?;
    let query_end_0 = fields.next()?.parse::<i64>().ok()?;
    let strand = fields.next()?.to_string();
    if strand != "+" && strand != "-" {
        return None;
    }
    let target_name = fields.next()?.to_string();
    let _target_length = fields.next()?.parse::<i64>().ok()?;
    let ref_start_0 = fields.next()?.parse::<i64>().ok()?;
    let ref_end_0 = fields.next()?.parse::<i64>().ok()?;
    let match_length = fields.next()?.parse::<i64>().ok()?;
    let block_length = fields.next()?.parse::<i64>().ok()?;
    let mapq = fields.next()?.parse::<i64>().ok()?;
    let cg_tag =
        fields.find_map(|field| field.strip_prefix("cg:Z:").map(|value| value.to_string()));

    let query_start = query_start_0 + 1;
    let query_end = query_end_0;
    let ref_start = ref_start_0 + 1;
    let ref_end = ref_end_0;
    if query_start < 1 || query_end < query_start || ref_start < 1 || ref_end < ref_start {
        return None;
    }

    Some(ParsedPafHit {
        query_name,
        target_name,
        strand,
        query_start,
        query_end,
        ref_start,
        ref_end,
        match_length,
        block_length,
        mapq,
        cg_tag,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::fs;
    use std::path::{Path, PathBuf};

    use rusqlite::{Connection, params};
    use tempfile::tempdir;

    use super::{
        index_bundle_ref_alignment_hits_with_cancel, load_ref_paf_hits_for_dataset, parse_paf_line,
    };
    use crate::db::init_workspace_schema;

    #[test]
    fn parses_paf_and_normalizes_to_one_based_closed() {
        let line = "tig0001\t1000\t0\t500\t+\tChr01\t100000\t99\t599\t480\t500\t60";
        let hit = parse_paf_line(line).expect("should parse paf");
        assert_eq!(hit.query_name, "tig0001");
        assert_eq!(hit.target_name, "Chr01");
        assert_eq!(hit.query_start, 1);
        assert_eq!(hit.query_end, 500);
        assert_eq!(hit.ref_start, 100);
        assert_eq!(hit.ref_end, 599);
        assert_eq!(hit.block_length, 500);
        assert_eq!(hit.cg_tag, None);
    }

    #[test]
    fn parses_paf_and_captures_optional_cg_tag() {
        let line =
            "tig0001\t1000\t0\t500\t+\tChr01\t100000\t99\t599\t480\t500\t60\tcg:Z:200M10D290M";
        let hit = parse_paf_line(line).expect("should parse paf");
        assert_eq!(hit.cg_tag.as_deref(), Some("200M10D290M"));
    }

    #[test]
    fn load_ref_paf_hits_for_dataset_persists_cg_tag_when_present() {
        let temp = tempdir().expect("tempdir");
        let paf_path = temp.path().join("result.paf");
        fs::write(
            &paf_path,
            "tig0001\t1000\t0\t500\t+\tChr01\t100000\t99\t609\t490\t510\t60\tcg:Z:200M10D300M\n",
        )
        .expect("write paf");

        let conn = Connection::open(temp.path().join("project.sqlite")).expect("open db");
        init_workspace_schema(&conn).expect("init schema");
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds1', 'asm', NULL, '/tmp/ds1.fa', '/tmp/ds1.fa.fai')",
            [],
        )
        .expect("insert dataset");
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (1, 1, 'tig0001', 1, 1000)",
            [],
        )
        .expect("insert source_seq");
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'asm', '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .expect("insert chr");

        let source_seq_by_name = HashMap::from([("tig0001".to_string(), 1_i64)]);
        let ref_chr_by_name = HashMap::from([("Chr01".to_string(), 1_i64)]);
        let inserted = load_ref_paf_hits_for_dataset(
            &conn,
            1,
            "ds1_vs_ref",
            &paf_path,
            &source_seq_by_name,
            &ref_chr_by_name,
            &mut || false,
        )
        .expect("load hits");
        assert_eq!(inserted, 1);

        let stored_cg = conn
            .query_row(
                "SELECT cg_tag FROM ref_alignment_hit WHERE id = 1",
                [],
                |row| row.get::<_, Option<String>>(0),
            )
            .expect("query cg_tag");
        assert_eq!(stored_cg.as_deref(), Some("200M10D300M"));
    }

    type StoredRefHit = (
        i64,
        i64,
        i64,
        String,
        i64,
        i64,
        i64,
        i64,
        i64,
        i64,
        i64,
        String,
    );

    fn seed_ref_alignment_bundle(
        root: &Path,
        dataset_count: i64,
        hits_per_dataset: usize,
    ) -> (Connection, PathBuf) {
        let conn = Connection::open(root.join("project.sqlite")).expect("open db");
        init_workspace_schema(&conn).expect("init schema");
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'asm', '/tmp/ref.fa', '/tmp/ref.fa.fai')",
            [],
        )
        .expect("insert ref");
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 100000)",
            [],
        )
        .expect("insert chr");

        let bundle_root = root.join("bundle");
        for dataset_index in 1..=dataset_count {
            conn.execute(
                "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
                 VALUES (?1, ?2, 'asm', NULL, '/tmp/ds.fa', '/tmp/ds.fa.fai')",
                params![dataset_index, format!("ds{dataset_index}")],
            )
            .expect("insert dataset");
            conn.execute(
                "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
                 VALUES (?1, ?1, ?2, 1, 1000)",
                params![dataset_index, format!("tig{dataset_index}")],
            )
            .expect("insert source_seq");

            let run_dir = bundle_root
                .join("runs")
                .join(format!("ds{dataset_index}_vs_ref"));
            fs::create_dir_all(&run_dir).expect("create run dir");
            let mut paf = String::new();
            for hit_index in 0..hits_per_dataset {
                let start = hit_index * 10;
                paf.push_str(&format!(
                    "tig{dataset_index}\t1000\t{start}\t{}\t+\tChr01\t100000\t{start}\t{}\t50\t50\t60\n",
                    start + 50,
                    start + 50
                ));
            }
            fs::write(run_dir.join("result.paf"), paf).expect("write paf");
        }
        (conn, bundle_root)
    }

    fn stored_ref_hits(conn: &Connection) -> Vec<StoredRefHit> {
        let mut stmt = conn
            .prepare(
                "SELECT dataset_id, source_seq_id, reference_chr_id, strand,
                        query_start, query_end, ref_start, ref_end,
                        match_length, block_length, mapq, run_name
                 FROM ref_alignment_hit
                 ORDER BY dataset_id, ref_start, source_seq_id",
            )
            .expect("prepare");
        stmt.query_map([], |row| {
            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
                row.get(7)?,
                row.get(8)?,
                row.get(9)?,
                row.get(10)?,
                row.get(11)?,
            ))
        })
        .expect("query")
        .collect::<std::result::Result<Vec<_>, _>>()
        .expect("collect")
    }

    #[test]
    fn index_bundle_ref_alignment_hits_matches_the_sequential_worker_budget() {
        let parallel_temp = tempdir().expect("tempdir");
        let (mut parallel_conn, parallel_bundle) =
            seed_ref_alignment_bundle(parallel_temp.path(), 6, 3);
        let mut steps = Vec::new();
        let parallel_summary = index_bundle_ref_alignment_hits_with_cancel(
            &mut parallel_conn,
            &parallel_bundle,
            4,
            &mut || false,
            &mut |run_name, _| steps.push(run_name.to_string()),
        )
        .expect("parallel index");
        assert_eq!(parallel_summary.loaded_dataset_count, 6);
        assert_eq!(parallel_summary.loaded_hit_count, 18);
        assert_eq!(
            steps,
            (1..=6)
                .map(|index| format!("ds{index}_vs_ref"))
                .collect::<Vec<_>>()
        );

        let sequential_temp = tempdir().expect("tempdir");
        let (mut sequential_conn, sequential_bundle) =
            seed_ref_alignment_bundle(sequential_temp.path(), 6, 3);
        let sequential_summary = index_bundle_ref_alignment_hits_with_cancel(
            &mut sequential_conn,
            &sequential_bundle,
            1,
            &mut || false,
            &mut |_, _| {},
        )
        .expect("sequential index");
        assert_eq!(sequential_summary.loaded_dataset_count, 6);
        assert_eq!(sequential_summary.loaded_hit_count, 18);
        assert_eq!(
            stored_ref_hits(&parallel_conn),
            stored_ref_hits(&sequential_conn)
        );
    }

    #[test]
    fn index_bundle_ref_alignment_hits_stops_before_committing_after_cancel() {
        let temp = tempdir().expect("tempdir");
        let (mut conn, bundle_root) = seed_ref_alignment_bundle(temp.path(), 6, 3);
        let cancel = std::cell::Cell::new(false);
        let mut progress_events = 0_usize;
        let error = index_bundle_ref_alignment_hits_with_cancel(
            &mut conn,
            &bundle_root,
            2,
            &mut || cancel.get(),
            &mut |_, _| {
                progress_events += 1;
                if progress_events >= 2 {
                    cancel.set(true);
                }
            },
        )
        .expect_err("cancel must stop the batch");
        assert!(error.to_string().contains("cancelled"), "got {error}");
        assert!(
            stored_ref_hits(&conn).len() < 18,
            "a cancelled batch must not commit every dataset"
        );
    }
}
