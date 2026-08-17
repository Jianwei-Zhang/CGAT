use super::*;

pub(super) fn sync_catalog_from_bundle(
    project_db_path: &Path,
    bundle_root: &Path,
    grt_package: &ValidatedGrtPackage,
) -> Result<()> {
    let references = read_reference_rows(bundle_root)?;
    if references.is_empty() {
        bail!("metadata/reference.tsv contains no reference rows");
    }

    let datasets = read_dataset_rows(bundle_root)?;
    if datasets.is_empty() {
        bail!("metadata/datasets.tsv contains no dataset rows");
    }
    let package = read_package_row(bundle_root)?;
    let chr_assignments = read_imported_chr_assignment_rows(bundle_root)?;
    let track_member_orders = read_imported_track_member_order_rows(bundle_root)?;
    validate_track_member_orders_against_assignments(&track_member_orders, &chr_assignments)?;
    let reference_chr_locators = read_reference_chr_locator_rows(bundle_root)?;
    let source_seq_locators = read_source_seq_locator_rows(bundle_root)?;
    let source_seq_n_regions = read_source_seq_n_region_rows(bundle_root)?;
    let telomere_rules = read_telomere_rule_rows(bundle_root)?;
    let telomere_marks = read_telomere_mark_rows(bundle_root)?;
    let centromere_marks = read_centromere_mark_rows(bundle_root)?;

    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn
        .transaction()
        .context("failed to start catalog sync transaction")?;

    for reference in references {
        let fasta_path = bundle_root.join(&reference.fasta_relpath);
        let fai_path = bundle_root.join(&reference.fai_relpath);
        tx.execute(
            "INSERT INTO reference_genome (
                name, species_name, assembly_label, fasta_path, fai_path
            ) VALUES (?1, ?2, ?3, ?4, ?5)
            ON CONFLICT(name) DO UPDATE SET
                species_name = excluded.species_name,
                assembly_label = excluded.assembly_label,
                fasta_path = excluded.fasta_path,
                fai_path = excluded.fai_path",
            params![
                reference.name,
                reference.species_name,
                reference.assembly_label,
                path_to_string(&fasta_path)?,
                path_to_string(&fai_path)?
            ],
        )
        .context("failed to upsert reference_genome row from metadata/reference.tsv")?;

        let reference_id: i64 = tx
            .query_row(
                "SELECT id FROM reference_genome WHERE name = ?1",
                params![reference.name],
                |row| row.get(0),
            )
            .context("failed to resolve reference_genome id after upsert")?;
        sync_reference_chr_rows(&tx, reference_id, &fai_path)?;
    }

    for dataset in datasets {
        let fasta_path = bundle_root.join(&dataset.fasta_relpath);
        let fai_path = bundle_root.join(&dataset.fai_relpath);
        tx.execute(
            "INSERT INTO dataset (
                name, assembler, assembler_version, fasta_path, fai_path, self_alignment_available
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT(name) DO UPDATE SET
                assembler = excluded.assembler,
                assembler_version = excluded.assembler_version,
                fasta_path = excluded.fasta_path,
                fai_path = excluded.fai_path,
                self_alignment_available = excluded.self_alignment_available",
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
        .context("failed to upsert dataset row from metadata/datasets.tsv")?;

        let dataset_id: i64 = tx
            .query_row(
                "SELECT id FROM dataset WHERE name = ?1",
                params![dataset.name],
                |row| row.get(0),
            )
            .context("failed to resolve dataset id after upsert")?;
        sync_source_seq_rows(&tx, dataset_id, &fai_path)?;
    }

    sync_workspace_package_metadata(&tx, &package)?;
    sync_imported_chr_assignment_rows(&tx, &chr_assignments)?;
    sync_imported_track_member_order_rows(&tx, &track_member_orders)?;
    sync_reference_chr_locator_rows(&tx, bundle_root, &reference_chr_locators)?;
    sync_source_seq_locator_rows(&tx, bundle_root, &source_seq_locators)?;
    sync_source_seq_n_region_rows(&tx, &source_seq_n_regions)?;
    sync_telomere_rows(&tx, &telomere_rules, &telomere_marks)?;
    sync_centromere_rows(&tx, &centromere_marks)?;
    persist_grt_package(&tx, grt_package)?;

    tx.commit().context("failed to commit catalog sync")?;
    Ok(())
}

pub(super) fn read_reference_rows(bundle_root: &Path) -> Result<Vec<ReferenceRow>> {
    let path = bundle_root.join("metadata/reference.tsv");
    read_tsv_rows(&path, |header, cols| {
        let reference_name = value_by_header(header, cols, "reference_name")?;
        let species_name = value_by_header(header, cols, "species_name")?;
        let assembly_label = value_by_header(header, cols, "assembly_label")?;
        let fasta_relpath = value_by_header(header, cols, "fasta_relpath")?;
        let fai_relpath = value_by_header(header, cols, "fai_relpath")?;
        Ok(ReferenceRow {
            name: reference_name,
            species_name,
            assembly_label,
            fasta_relpath,
            fai_relpath,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_dataset_rows(bundle_root: &Path) -> Result<Vec<DatasetRow>> {
    let path = bundle_root.join("metadata/datasets.tsv");
    read_tsv_rows(&path, |header, cols| {
        let dataset_name = value_by_header(header, cols, "dataset_name")?;
        let assembler = value_by_header(header, cols, "assembler")?;
        let assembler_version_raw = value_by_header(header, cols, "assembler_version")?;
        let fasta_relpath = value_by_header(header, cols, "fasta_relpath")?;
        let fai_relpath = value_by_header(header, cols, "fai_relpath")?;
        let self_alignment_available = parse_bool_flag(
            &value_by_header(header, cols, "self_alignment_available")?,
            "self_alignment_available",
        )?;
        Ok(DatasetRow {
            name: dataset_name,
            assembler,
            assembler_version: if assembler_version_raw.trim().is_empty() {
                None
            } else {
                Some(assembler_version_raw)
            },
            fasta_relpath,
            fai_relpath,
            self_alignment_available,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_package_row(bundle_root: &Path) -> Result<PackageRow> {
    let path = bundle_root.join("metadata/package.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/package.tsv");
    }
    let mut rows = read_tsv_rows(&path, |header, cols| {
        Ok(PackageRow {
            package_mode: value_by_header(header, cols, "package_mode")?,
            sequence_layout: value_by_header(header, cols, "sequence_layout")?,
            preassigned_chr: parse_bool_flag(
                &value_by_header(header, cols, "preassigned_chr")?,
                "preassigned_chr",
            )?,
            chr_assignment_min_coverage_percent: parse_f64_value(
                &value_by_header(header, cols, "chr_assignment_min_coverage_percent")?,
                "chr_assignment_min_coverage_percent",
            )?,
            self_alignment_scope: value_by_header(header, cols, "self_alignment_scope")?,
            cross_alignment_scope: value_by_header(header, cols, "cross_alignment_scope")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))?;
    if rows.is_empty() {
        bail!("metadata/package.tsv must contain exactly one data row");
    }
    if rows.len() != 1 {
        bail!("metadata/package.tsv must contain exactly one data row");
    }
    let package = rows.remove(0);
    if !package.sequence_layout.eq_ignore_ascii_case("partitioned") {
        bail!(
            "server delivery package requires sequence_layout=partitioned in metadata/package.tsv"
        );
    }
    if !package.preassigned_chr {
        bail!("server delivery package requires preassigned_chr=true in metadata/package.tsv");
    }
    if !package
        .cross_alignment_scope
        .eq_ignore_ascii_case("chr_partition")
    {
        bail!(
            "server delivery package requires cross_alignment_scope=chr_partition in metadata/package.tsv"
        );
    }
    if !package
        .self_alignment_scope
        .eq_ignore_ascii_case("chr_partition")
        && !package.self_alignment_scope.eq_ignore_ascii_case("none")
    {
        bail!(
            "server delivery package requires self_alignment_scope=chr_partition or none in metadata/package.tsv"
        );
    }
    Ok(package)
}
