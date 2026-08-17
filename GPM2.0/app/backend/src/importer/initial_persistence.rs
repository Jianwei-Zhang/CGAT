use super::*;

pub(super) fn sync_telomere_rows(
    tx: &Transaction<'_>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_telomere_mark", [])
        .context("failed to clear source_seq_telomere_mark rows")?;
    tx.execute("DELETE FROM telomere_rule", [])
        .context("failed to clear telomere_rule rows")?;

    if rules.is_empty() && marks.is_empty() {
        return Ok(());
    }

    for rule in rules {
        tx.execute(
            "INSERT INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, ?4)",
            params![
                rule.rule_id,
                rule.motif,
                rule.min_repeat,
                if rule.reverse_complement {
                    1_i64
                } else {
                    0_i64
                }
            ],
        )
        .with_context(|| format!("failed to insert telomere rule {}", rule.rule_id))?;
    }

    for mark in marks {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for telomere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_telomere_mark (
                source_seq_id, rule_id, assigned_chr_name, motif, min_repeat,
                repeat_count, start_bp, end_bp, strand
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                source_seq_id,
                mark.rule_id,
                mark.assigned_chr_name,
                mark.motif,
                mark.min_repeat,
                mark.repeat_count,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert telomere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.rule_id
            )
        })?;
    }
    Ok(())
}

pub(super) fn sync_centromere_rows(
    tx: &Transaction<'_>,
    marks: &[CentromereMarkRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_centromere_mark", [])
        .context("failed to clear source_seq_centromere_mark rows")?;

    for mark in marks {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![mark.dataset_name, mark.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for centromere mark {}:{}",
                    mark.dataset_name, mark.seq_name
                )
            })?;
        tx.execute(
            "INSERT INTO source_seq_centromere_mark (
                source_seq_id, cen_id, assigned_chr_name, query_name,
                start_bp, end_bp, strand, align_length, identity, mapq
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                source_seq_id,
                mark.cen_id,
                mark.assigned_chr_name,
                mark.query_name,
                mark.start_bp,
                mark.end_bp,
                mark.strand,
                mark.align_length,
                mark.identity,
                mark.mapq,
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert centromere mark {}:{} {}",
                mark.dataset_name, mark.seq_name, mark.cen_id
            )
        })?;
    }
    Ok(())
}

pub(super) fn sync_reference_chr_rows(
    tx: &Transaction<'_>,
    reference_genome_id: i64,
    fai_path: &Path,
) -> Result<()> {
    let rows = parse_fai_rows(fai_path)?;
    if rows.is_empty() {
        bail!("reference fai has no rows: {}", fai_path.display());
    }

    tx.execute(
        "DELETE FROM reference_chr WHERE reference_genome_id = ?1",
        params![reference_genome_id],
    )
    .with_context(|| {
        format!(
            "failed to clear reference_chr rows for reference_genome_id={}",
            reference_genome_id
        )
    })?;

    for row in rows {
        tx.execute(
            "INSERT INTO reference_chr (
                reference_genome_id, chr_name, chr_order, length
            ) VALUES (?1, ?2, ?3, ?4)",
            params![reference_genome_id, row.seq_name, row.seq_order, row.length],
        )
        .with_context(|| {
            format!(
                "failed to insert reference_chr row for reference_genome_id={}",
                reference_genome_id
            )
        })?;
    }
    Ok(())
}

pub(super) fn sync_source_seq_rows(
    tx: &Transaction<'_>,
    dataset_id: i64,
    fai_path: &Path,
) -> Result<()> {
    let rows = parse_fai_rows(fai_path)?;
    if rows.is_empty() {
        bail!("dataset fai has no rows: {}", fai_path.display());
    }
    let contig_count = rows.len() as i64;
    let total_length_bp = rows.iter().map(|row| row.length).sum::<i64>();

    tx.execute(
        "DELETE FROM source_seq WHERE dataset_id = ?1",
        params![dataset_id],
    )
    .with_context(|| {
        format!(
            "failed to clear source_seq rows for dataset_id={}",
            dataset_id
        )
    })?;

    for row in rows {
        tx.execute(
            "INSERT INTO source_seq (
                dataset_id, seq_name, seq_order, length
            ) VALUES (?1, ?2, ?3, ?4)",
            params![dataset_id, row.seq_name, row.seq_order, row.length],
        )
        .with_context(|| {
            format!(
                "failed to insert source_seq row for dataset_id={}",
                dataset_id
            )
        })?;
    }
    tx.execute(
        "UPDATE dataset
         SET contig_count = ?2, total_length_bp = ?3
         WHERE id = ?1",
        params![dataset_id, contig_count, total_length_bp],
    )
    .with_context(|| {
        format!(
            "failed to update dataset stats for dataset_id={}",
            dataset_id
        )
    })?;
    Ok(())
}

pub(super) fn parse_fai_rows(path: &Path) -> Result<Vec<FaiRow>> {
    let file =
        File::open(path).with_context(|| format!("failed to open fai {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut rows = Vec::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 1, path.display())
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() < 2 {
            bail!(
                "invalid fai row at {}:{} => {}",
                path.display(),
                index + 1,
                line
            );
        }
        let length: i64 = parts[1].parse().with_context(|| {
            format!(
                "invalid fai length at {}:{} => {}",
                path.display(),
                index + 1,
                parts[1]
            )
        })?;
        rows.push(FaiRow {
            seq_name: parts[0].to_string(),
            length,
            seq_order: (index as i64) + 1,
        });
    }
    Ok(rows)
}
