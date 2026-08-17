use super::*;

pub(super) fn append_catalog_from_add_payload(
    project_db_path: &Path,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: Option<i64>,
    manifest: &AddDatasetManifest,
) -> Result<i64> {
    let mut datasets = read_dataset_rows(payload_root)?;
    if datasets.len() != 1 {
        bail!("add dataset payload must contain exactly one dataset row");
    }
    let dataset = datasets.remove(0);
    if dataset.name != manifest.dataset_name {
        bail!(
            "add dataset payload dataset mismatch: manifest={} payload={}",
            manifest.dataset_name,
            dataset.name
        );
    }
    let chr_assignments = read_imported_chr_assignment_rows(payload_root)?;
    let track_member_orders = read_imported_track_member_order_rows(payload_root)?;
    let source_seq_locators = read_source_seq_locator_rows(payload_root)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(payload_root)?;
    let telomere_rules = read_telomere_rule_rows(payload_root)?;
    let telomere_marks = read_telomere_mark_rows(payload_root)?;
    let centromere_marks = read_centromere_mark_rows(payload_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start add catalog sync transaction")?;
    let fasta_path = workspace_root.join(&dataset.fasta_relpath);
    let fai_path = workspace_root.join(&dataset.fai_relpath);
    tx.execute(
        "INSERT INTO dataset (
            name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            dataset.name,
            dataset.assembler,
            dataset.assembler_version,
            path_to_string(&fasta_path)?,
            path_to_string(&fai_path)?,
            if dataset.self_alignment_available {
                1_i64
            } else {
                0_i64
            }
        ],
    )
    .with_context(|| format!("failed to insert add dataset {}", manifest.dataset_name))?;
    let dataset_id = tx.last_insert_rowid();
    sync_source_seq_rows(&tx, dataset_id, &fai_path)?;
    append_imported_chr_assignment_rows(&tx, &chr_assignments)?;
    append_imported_track_member_order_rows(&tx, &track_member_orders)?;
    append_source_seq_locator_rows(&tx, workspace_root, &source_seq_locators)?;
    append_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    append_telomere_rows(&tx, &telomere_rules, &telomere_marks)?;
    append_centromere_rows(&tx, &centromere_marks)?;
    if let Some(project_id) = project_id {
        append_project_dataset_link(&tx, project_id, dataset_id)?;
    }
    tx.commit()
        .context("failed to commit add catalog sync transaction")?;
    Ok(dataset_id)
}

pub(super) fn append_catalog_from_add_ctg_payload(
    project_db_path: &Path,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    validated: &ValidatedAddCtgPackage,
) -> Result<AddCtgCatalogAppend> {
    let mut datasets = read_dataset_rows(payload_root)?;
    if datasets.len() != 1 || datasets[0].name != manifest.derived_dataset {
        bail!("add_ctg payload must contain exactly one derived dataset row");
    }
    let dataset = datasets.remove(0);
    let derived_row = read_derived_ctg_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing derived_ctgs row")?;
    let track_row = read_track_member_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing track_members row")?;
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    let locator = read_single_add_ctg_locator(payload_root, manifest)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(payload_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start add_ctg catalog sync transaction")?;
    let dataset_id = ensure_derived_dataset_in_transaction(&tx, workspace_root, &dataset)?;
    let source_seq_id = append_derived_source_seq_in_transaction(
        &tx,
        dataset_id,
        &manifest.ctg_name,
        validated.source_length,
    )?;
    append_imported_chr_assignment_rows(&tx, &[chr_assignment])?;
    replace_imported_track_member_order_groups(&tx, &validated.track_member_orders)?;
    append_source_seq_locator_rows(&tx, workspace_root, &[locator])?;
    append_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    insert_derived_ctg_row(&tx, source_seq_id, &derived_row)?;
    insert_derived_ctg_track_member_row(
        &tx,
        project_id,
        source_seq_id,
        validated.target_dataset_id,
        &track_row,
    )?;
    tx.commit()
        .context("failed to commit add_ctg catalog sync transaction")?;
    Ok(AddCtgCatalogAppend {
        dataset_id,
        source_seq_id,
    })
}

pub(super) fn ensure_derived_dataset_in_transaction(
    tx: &Transaction<'_>,
    workspace_root: &Path,
    dataset: &DatasetRow,
) -> Result<i64> {
    if dataset.name != "derived_ctg" {
        bail!("derived dataset row must be named derived_ctg");
    }
    let existing_id = tx
        .query_row(
            "SELECT id FROM dataset WHERE name = ?1",
            params![dataset.name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to resolve existing derived_ctg dataset")?;
    if let Some(dataset_id) = existing_id {
        return Ok(dataset_id);
    }
    let fasta_path = workspace_root.join(&dataset.fasta_relpath);
    let fai_path = workspace_root.join(&dataset.fai_relpath);
    tx.execute(
        "INSERT INTO dataset (
            name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            dataset.name,
            dataset.assembler,
            dataset.assembler_version,
            path_to_string(&fasta_path)?,
            path_to_string(&fai_path)?,
            if dataset.self_alignment_available {
                1_i64
            } else {
                0_i64
            }
        ],
    )
    .context("failed to insert derived_ctg dataset")?;
    Ok(tx.last_insert_rowid())
}

pub(super) fn append_derived_source_seq_in_transaction(
    tx: &Transaction<'_>,
    dataset_id: i64,
    ctg_name: &str,
    source_length: i64,
) -> Result<i64> {
    let duplicate = tx
        .query_row(
            "SELECT id FROM source_seq WHERE dataset_id = ?1 AND seq_name = ?2",
            params![dataset_id, ctg_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check duplicate derived source_seq")?;
    if duplicate.is_some() {
        bail!("ctg name already exists: {ctg_name}. Please choose a different --ctg name.");
    }
    let seq_order: i64 = tx
        .query_row(
            "SELECT COALESCE(MAX(seq_order), 0) + 1 FROM source_seq WHERE dataset_id = ?1",
            params![dataset_id],
            |row| row.get(0),
        )
        .context("failed to compute derived_ctg seq_order")?;
    tx.execute(
        "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
         VALUES (?1, ?2, ?3, ?4)",
        params![dataset_id, ctg_name, seq_order, source_length],
    )
    .with_context(|| format!("failed to insert derived source_seq {ctg_name}"))?;
    let source_seq_id = tx.last_insert_rowid();
    tx.execute(
        "UPDATE dataset
         SET contig_count = (
             SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1
         ),
         total_length_bp = (
             SELECT COALESCE(SUM(length), 0) FROM source_seq WHERE dataset_id = ?1
         )
         WHERE id = ?1",
        params![dataset_id],
    )
    .context("failed to update derived_ctg dataset stats")?;
    Ok(source_seq_id)
}

pub(super) fn insert_derived_ctg_row(
    tx: &Transaction<'_>,
    source_seq_id: i64,
    row: &DerivedCtgRow,
) -> Result<()> {
    tx.execute(
        "INSERT INTO derived_ctg (
            source_seq_id, source, source_fasta_name, source_fasta_sha256, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5)",
        params![
            source_seq_id,
            row.source,
            row.source_fasta_name,
            row.source_fasta_sha256,
            row.created_at
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg row for {}", row.ctg_name))?;
    Ok(())
}

pub(super) fn insert_derived_ctg_track_member_row(
    tx: &Transaction<'_>,
    project_id: i64,
    source_seq_id: i64,
    target_dataset_id: i64,
    row: &TrackMemberRow,
) -> Result<()> {
    tx.execute(
        "INSERT INTO derived_ctg_track_member (
            project_id, source_seq_id, target_dataset_id, target_chr_name, member_role, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            project_id,
            source_seq_id,
            target_dataset_id,
            row.target_chr,
            row.member_role,
            row.created_at
        ],
    )
    .with_context(|| {
        format!(
            "failed to insert derived_ctg track member for {}",
            row.member_ctg
        )
    })?;
    Ok(())
}

pub(super) fn append_imported_chr_assignment_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for imported chr assignment {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.assigned_chr_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve reference_chr for imported chr assignment {}",
                    row.assigned_chr_name
                )
            })?;
        tx.execute(
            "INSERT INTO imported_chr_assignment (
                source_seq_id, reference_chr_id, source_orientation, orientation_source,
                support_bp, support_percent, anchor_start
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                source_seq_id,
                reference_chr_id,
                row.source_orientation,
                row.orientation_source,
                row.support_bp,
                row.support_percent,
                row.anchor_start
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert imported chr assignment {}:{} -> {}",
                row.dataset_name, row.seq_name, row.assigned_chr_name
            )
        })?;
    }
    Ok(())
}

pub(super) fn append_source_seq_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[SourceSeqLocatorRow],
) -> Result<()> {
    for row in rows {
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1
                   AND ss.seq_name = ?2",
                params![row.dataset_name, row.seq_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve source_seq for locator {}:{}",
                    row.dataset_name, row.seq_name
                )
            })?;
        let fasta_path = bundle_root.join(&row.fasta_relpath);
        tx.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (?1, ?2)
             ON CONFLICT(source_seq_id) DO UPDATE SET
                fasta_path = excluded.fasta_path",
            params![source_seq_id, path_to_string(&fasta_path)?],
        )
        .with_context(|| {
            format!(
                "failed to insert source seq locator for {}:{}",
                row.dataset_name, row.seq_name
            )
        })?;
    }
    Ok(())
}

pub(super) fn append_source_seq_n_region_rows(
    tx: &Transaction<'_>,
    rows: &[SourceSeqNRegionRow],
) -> Result<()> {
    for row in rows {
        insert_source_seq_n_region_row(tx, row)?;
    }
    Ok(())
}

pub(super) fn insert_source_seq_n_region_row(
    tx: &Transaction<'_>,
    row: &SourceSeqNRegionRow,
) -> Result<()> {
    let source_seq_id: i64 = tx
        .query_row(
            "SELECT ss.id
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE d.name = ?1
               AND ss.seq_name = ?2",
            params![row.dataset_name, row.seq_name],
            |query_row| query_row.get(0),
        )
        .with_context(|| {
            format!(
                "failed to resolve source_seq for n region {}:{}",
                row.dataset_name, row.seq_name
            )
        })?;
    tx.execute(
        "INSERT INTO source_seq_n_region (
            source_seq_id, start_bp, end_bp, length_bp
         ) VALUES (?1, ?2, ?3, ?4)",
        params![source_seq_id, row.start_bp, row.end_bp, row.length_bp],
    )
    .with_context(|| {
        format!(
            "failed to insert n region {}:{} {}-{}",
            row.dataset_name, row.seq_name, row.start_bp, row.end_bp
        )
    })?;
    Ok(())
}

pub(super) fn append_telomere_rows(
    tx: &Transaction<'_>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    for rule in rules {
        tx.execute(
            "INSERT INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(rule_id) DO UPDATE SET
                motif = excluded.motif,
                min_repeat = excluded.min_repeat,
                reverse_complement = excluded.reverse_complement",
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
        .with_context(|| format!("failed to upsert telomere rule {}", rule.rule_id))?;
    }
    for mark in marks {
        tx.execute(
            "INSERT OR IGNORE INTO telomere_rule (
                rule_id, motif, min_repeat, reverse_complement
             ) VALUES (?1, ?2, ?3, 1)",
            params![mark.rule_id, mark.motif, mark.min_repeat],
        )
        .with_context(|| format!("failed to insert telomere rule {}", mark.rule_id))?;
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

pub(super) fn append_centromere_rows(
    tx: &Transaction<'_>,
    marks: &[CentromereMarkRow],
) -> Result<()> {
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

pub(super) fn append_project_dataset_link(
    tx: &Transaction<'_>,
    project_id: i64,
    dataset_id: i64,
) -> Result<()> {
    let next_display_order: i64 = tx
        .query_row(
            "SELECT COALESCE(MAX(display_order), 0) + 1
             FROM project_dataset
             WHERE project_id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to compute project {project_id} display order"))?;
    tx.execute(
        "INSERT INTO project_dataset (
            project_id, dataset_id, dataset_role, display_order
         ) VALUES (?1, ?2, 'support', ?3)",
        params![project_id, dataset_id, next_display_order],
    )
    .with_context(|| {
        format!(
            "failed to insert add dataset support link project_id={} dataset_id={}",
            project_id, dataset_id
        )
    })?;
    Ok(())
}

pub(super) fn project_has_assembly_rows(project_db_path: &Path, project_id: i64) -> Result<bool> {
    let conn = open_workspace_db(project_db_path)?;
    let has_rows: i64 = conn
        .query_row(
            "SELECT EXISTS(
                SELECT 1
                FROM assembly_seq
                WHERE project_id = ?1
                LIMIT 1
             )",
            params![project_id],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to detect assembly rows for project_id={project_id}"))?;
    Ok(has_rows > 0)
}

pub(super) fn append_project_derived_ctg_assembly(
    project_db_path: &Path,
    project_id: i64,
    source_seq_id: i64,
    ctg_name: &str,
    target_chr: &str,
    anchor_start: i64,
    track_member_orders: &[ImportedTrackMemberOrderRow],
) -> Result<i64> {
    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start derived_ctg assembly append transaction")?;
    let source_length: i64 = tx
        .query_row(
            "SELECT length FROM source_seq WHERE id = ?1",
            params![source_seq_id],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to resolve source_seq_id {source_seq_id} length"))?;
    let existing_assembly = tx
        .query_row(
            "SELECT id FROM assembly_seq WHERE project_id = ?1 AND source_seq_id = ?2",
            params![project_id, source_seq_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check existing derived_ctg assembly_seq")?;
    if existing_assembly.is_some() {
        bail!(
            "project_id {} already has assembly rows for derived ctg {}",
            project_id,
            ctg_name
        );
    }
    let existing_name = tx
        .query_row(
            "SELECT id FROM assembly_ctg WHERE project_id = ?1 AND name = ?2",
            params![project_id, ctg_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check duplicate derived_ctg assembly name")?;
    if existing_name.is_some() {
        bail!(
            "assembly_ctg name '{}' already exists in project_id {}",
            ctg_name,
            project_id
        );
    }
    let created_at = now_timestamp_string();
    let new_chr_order = track_member_orders
        .iter()
        .find(|row| row.member_dataset == "derived_ctg" && row.member_ctg == ctg_name)
        .map(|row| row.member_order)
        .with_context(|| {
            format!("track member order snapshot is missing derived ctg {ctg_name}")
        })?;
    tx.execute(
        "INSERT INTO assembly_seq (
            project_id, source_seq_id, instance_key, orient, source_start, source_end,
            left_end_type, right_end_type, hidden, created_at, note
         ) VALUES (?1, ?2, ?3, '+', 1, ?4, 'normal', 'normal', 0, ?5, ?6)",
        params![
            project_id,
            source_seq_id,
            format!("source:{}", source_seq_id),
            source_length,
            created_at,
            "derived_ctg"
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg assembly_seq for {ctg_name}"))?;
    let assembly_seq_id = tx.last_insert_rowid();
    tx.execute(
        "INSERT INTO assembly_ctg (
            project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
            anchor_start, ref_orient, placement_mode, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, '+', 'auto', ?7, ?8)",
        params![
            project_id,
            assembly_seq_id,
            ctg_name,
            target_chr,
            new_chr_order,
            anchor_start,
            created_at,
            "derived_ctg"
        ],
    )
    .with_context(|| format!("failed to insert derived_ctg assembly_ctg for {ctg_name}"))?;
    let assembly_ctg_id = tx.last_insert_rowid();
    for order_row in track_member_orders {
        let updated = tx
            .execute(
                "UPDATE assembly_ctg
                 SET chr_order = ?1
                 WHERE project_id = ?2
                   AND assigned_chr_name = ?3
                   AND assembly_seq_id IN (
                       SELECT assembly_seq.id
                       FROM assembly_seq
                       JOIN source_seq ON source_seq.id = assembly_seq.source_seq_id
                       JOIN dataset ON dataset.id = source_seq.dataset_id
                       WHERE assembly_seq.project_id = ?2
                         AND dataset.name = ?4
                         AND source_seq.seq_name = ?5
                   )",
                params![
                    order_row.member_order,
                    project_id,
                    order_row.target_chr,
                    order_row.member_dataset,
                    order_row.member_ctg
                ],
            )
            .with_context(|| {
                format!(
                    "failed to apply track member order for {}:{}",
                    order_row.member_dataset, order_row.member_ctg
                )
            })?;
        let is_new_member =
            order_row.member_dataset == "derived_ctg" && order_row.member_ctg == ctg_name;
        if (is_new_member && updated != 1) || updated > 1 {
            bail!(
                "track member order snapshot member {}:{} resolved to {} assembly rows in project_id {}",
                order_row.member_dataset,
                order_row.member_ctg,
                updated,
                project_id
            );
        }
    }
    tx.commit()
        .context("failed to commit derived_ctg assembly append transaction")?;
    Ok(assembly_ctg_id)
}
