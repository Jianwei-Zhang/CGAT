use super::*;

pub(super) fn sync_workspace_package_metadata(
    tx: &Transaction<'_>,
    package: &PackageRow,
) -> Result<()> {
    tx.execute(
        "INSERT INTO workspace_package_metadata (
            id, package_mode, sequence_layout, preassigned_chr,
            chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
         ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(id) DO UPDATE SET
            package_mode = excluded.package_mode,
            sequence_layout = excluded.sequence_layout,
            preassigned_chr = excluded.preassigned_chr,
            chr_assignment_min_coverage_percent = excluded.chr_assignment_min_coverage_percent,
            self_alignment_scope = excluded.self_alignment_scope,
            cross_alignment_scope = excluded.cross_alignment_scope",
        params![
            package.package_mode,
            package.sequence_layout,
            if package.preassigned_chr {
                1_i64
            } else {
                0_i64
            },
            package.chr_assignment_min_coverage_percent,
            package.self_alignment_scope,
            package.cross_alignment_scope,
        ],
    )
    .context("failed to sync workspace_package_metadata")?;
    Ok(())
}

pub(super) fn sync_imported_chr_assignment_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    tx.execute("DELETE FROM imported_chr_assignment", [])
        .context("failed to clear imported_chr_assignment rows")?;

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

pub(super) fn sync_imported_track_member_order_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    tx.execute("DELETE FROM imported_track_member_order", [])
        .context("failed to clear imported_track_member_order rows")?;
    insert_imported_track_member_order_rows(tx, rows)
}

pub(super) fn append_imported_track_member_order_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    insert_imported_track_member_order_rows(tx, rows)
}

pub(super) fn replace_imported_track_member_order_groups(
    tx: &Transaction<'_>,
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    let groups = rows
        .iter()
        .map(|row| (row.target_track.as_str(), row.target_chr.as_str()))
        .collect::<HashSet<_>>();
    for (target_track, target_chr) in groups {
        let target_dataset_id: i64 = tx
            .query_row(
                "SELECT id FROM dataset WHERE name = ?1",
                params![target_track],
                |row| row.get(0),
            )
            .with_context(|| format!("failed to resolve ordered target track {target_track}"))?;
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![target_chr],
                |row| row.get(0),
            )
            .with_context(|| format!("failed to resolve ordered target chr {target_chr}"))?;
        tx.execute(
            "DELETE FROM imported_track_member_order
             WHERE target_dataset_id = ?1 AND reference_chr_id = ?2",
            params![target_dataset_id, reference_chr_id],
        )
        .with_context(|| {
            format!("failed to replace imported track member order for {target_track}:{target_chr}")
        })?;
    }
    insert_imported_track_member_order_rows(tx, rows)
}

pub(super) fn insert_imported_track_member_order_rows(
    tx: &Transaction<'_>,
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    for row in rows {
        let target_dataset_id: i64 = tx
            .query_row(
                "SELECT id FROM dataset WHERE name = ?1",
                params![row.target_track],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve ordered target track {}",
                    row.target_track
                )
            })?;
        let source_seq_id: i64 = tx
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = ?1 AND ss.seq_name = ?2",
                params![row.member_dataset, row.member_ctg],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve ordered track member {}:{}",
                    row.member_dataset, row.member_ctg
                )
            })?;
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.target_chr],
                |query_row| query_row.get(0),
            )
            .with_context(|| format!("failed to resolve ordered target chr {}", row.target_chr))?;
        tx.execute(
            "INSERT INTO imported_track_member_order (
                target_dataset_id, reference_chr_id, source_seq_id, member_order
             ) VALUES (?1, ?2, ?3, ?4)",
            params![
                target_dataset_id,
                reference_chr_id,
                source_seq_id,
                row.member_order
            ],
        )
        .with_context(|| {
            format!(
                "failed to insert track member order {}:{} {}:{} -> {}",
                row.target_track,
                row.target_chr,
                row.member_dataset,
                row.member_ctg,
                row.member_order
            )
        })?;
    }
    Ok(())
}

pub(super) fn sync_reference_chr_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[ReferenceChrLocatorRow],
) -> Result<()> {
    tx.execute("DELETE FROM reference_chr_locator", [])
        .context("failed to clear reference_chr_locator rows")?;

    for row in rows {
        let reference_chr_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_chr WHERE chr_name = ?1",
                params![row.reference_chr_name],
                |query_row| query_row.get(0),
            )
            .with_context(|| {
                format!(
                    "failed to resolve reference_chr for locator {}",
                    row.reference_chr_name
                )
            })?;
        let fasta_path = bundle_root.join(&row.fasta_relpath);
        tx.execute(
            "INSERT INTO reference_chr_locator (reference_chr_id, fasta_path)
             VALUES (?1, ?2)
             ON CONFLICT(reference_chr_id) DO UPDATE SET
                fasta_path = excluded.fasta_path",
            params![reference_chr_id, path_to_string(&fasta_path)?],
        )
        .with_context(|| {
            format!(
                "failed to insert reference chr locator for {}",
                row.reference_chr_name
            )
        })?;
    }
    Ok(())
}

pub(super) fn sync_source_seq_locator_rows(
    tx: &Transaction<'_>,
    bundle_root: &Path,
    rows: &[SourceSeqLocatorRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_locator", [])
        .context("failed to clear source_seq_locator rows")?;

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

pub(super) fn sync_source_seq_n_region_rows(
    tx: &Transaction<'_>,
    rows: &[SourceSeqNRegionRow],
) -> Result<()> {
    tx.execute("DELETE FROM source_seq_n_region", [])
        .context("failed to clear source_seq_n_region rows")?;

    for row in rows {
        insert_source_seq_n_region_row(tx, row)?;
    }
    Ok(())
}
