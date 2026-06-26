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

pub fn index_bundle_ref_alignment_hits_with_cancel<F, P>(
    conn: &mut Connection,
    bundle_root: &Path,
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

    let mut loaded_dataset_count = 0_i64;
    let mut loaded_hit_count = 0_i64;
    let mut skipped_dataset_count = 0_i64;

    for (dataset_id, dataset_name) in dataset_rows {
        if should_cancel() {
            bail!("import cancelled");
        }
        let run_name = format!("{}_vs_ref", dataset_name);
        let run_paf = bundle_root.join("runs").join(&run_name).join("result.paf");
        if !run_paf.exists() {
            skipped_dataset_count += 1;
            continue;
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

        loaded_dataset_count += 1;
        loaded_hit_count += inserted;
    }

    Ok(AlignmentCacheLoadSummary {
        project_id: 0,
        loaded_dataset_count,
        loaded_hit_count,
        skipped_dataset_count,
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
        dataset_id,
        RefHitClearScope::SourceSeq(source_seq_id),
        run_name,
        run_paf_path,
        &source_seq_by_name,
        &ref_chr_by_name,
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
        dataset_id,
        RefHitClearScope::Dataset(dataset_id),
        run_name,
        run_paf_path,
        source_seq_by_name,
        ref_chr_by_name,
        should_cancel,
    )
}

fn load_ref_paf_hits(
    conn: &Connection,
    dataset_id: i64,
    clear_scope: RefHitClearScope,
    run_name: &str,
    run_paf_path: &Path,
    source_seq_by_name: &HashMap<String, i64>,
    ref_chr_by_name: &HashMap<String, i64>,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<i64> {
    if should_cancel() {
        bail!("auto pipeline cancelled");
    }

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

    let file = File::open(run_paf_path)
        .with_context(|| format!("failed to open paf file {}", run_paf_path.display()))?;
    let reader = BufReader::new(file);

    let mut insert_stmt = conn.prepare(
        "INSERT INTO ref_alignment_hit (
            dataset_id, source_seq_id, reference_chr_id, strand,
            query_start, query_end, ref_start, ref_end,
            match_length, block_length, mapq, cg_tag, run_name, note
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, NULL)",
    )?;

    let mut inserted = 0_i64;
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

        insert_stmt.execute(params![
            dataset_id,
            source_seq_id,
            reference_chr_id,
            hit.strand,
            hit.query_start,
            hit.query_end,
            hit.ref_start,
            hit.ref_end,
            hit.match_length,
            hit.block_length,
            hit.mapq,
            hit.cg_tag,
            run_name
        ])?;
        inserted += 1;
    }

    Ok(inserted)
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

    use rusqlite::Connection;
    use tempfile::tempdir;

    use super::{load_ref_paf_hits_for_dataset, parse_paf_line};
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
}
