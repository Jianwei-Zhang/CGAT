use super::*;

pub(super) fn read_add_dataset_manifest(extract_root: &Path) -> Result<AddDatasetManifest> {
    let path = extract_root.join("add_package/manifest.tsv");
    if !path.exists() {
        bail!("add dataset package requires add_package/manifest.tsv");
    }
    let values = read_key_value_tsv(&path)
        .with_context(|| format!("failed to parse add manifest {}", path.display()))?;
    let package_type = required_key_value(&values, "package_type")?;
    if package_type != "add_dataset" {
        bail!(
            "add dataset package requires package_type=add_dataset, got {}",
            package_type
        );
    }
    let dataset_name = required_key_value(&values, "dataset_name")?;
    if dataset_name.trim().is_empty() {
        bail!("add dataset manifest requires dataset_name");
    }
    validate_add_dataset_name(&dataset_name)?;
    let reference_name = required_key_value(&values, "reference_name")?;
    let sequence_layout = required_key_value(&values, "sequence_layout")?;
    let preassigned_chr = parse_bool_flag(
        &required_key_value(&values, "preassigned_chr")?,
        "preassigned_chr",
    )?;
    let chr_assignment_min_coverage_percent = parse_f64_value(
        &required_key_value(&values, "chr_assignment_min_coverage_percent")?,
        "chr_assignment_min_coverage_percent",
    )?;
    let alignment_engine = values
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    let minimap_preset = values
        .get("minimap_preset")
        .cloned()
        .unwrap_or_else(|| "asm10".to_string());
    let blastn_task = values
        .get("blastn_task")
        .cloned()
        .unwrap_or_else(|| "blastn".to_string());
    let blastn_evalue = values
        .get("blastn_evalue")
        .cloned()
        .unwrap_or_else(|| "1e-10".to_string());
    let blastn_dust = values
        .get("blastn_dust")
        .cloned()
        .unwrap_or_else(|| "no".to_string());
    let winnowmap_preset = values
        .get("winnowmap_preset")
        .cloned()
        .unwrap_or_else(|| "asm20".to_string());
    let winnowmap_kmer = values
        .get("winnowmap_kmer")
        .cloned()
        .unwrap_or_else(|| "19".to_string());
    let winnowmap_repeat_fraction = values
        .get("winnowmap_repeat_fraction")
        .cloned()
        .unwrap_or_else(|| "0.9998".to_string());
    let skip_self = parse_bool_flag(&required_key_value(&values, "skip_self")?, "skip_self")?;
    let self_alignment_available = parse_bool_flag(
        &required_key_value(&values, "self_alignment_available")?,
        "self_alignment_available",
    )?;
    let tel_enabled = parse_bool_flag(&required_key_value(&values, "tel_enabled")?, "tel_enabled")?;
    let cen_enabled = parse_bool_flag(&required_key_value(&values, "cen_enabled")?, "cen_enabled")?;
    Ok(AddDatasetManifest {
        dataset_name,
        reference_name,
        sequence_layout,
        preassigned_chr,
        chr_assignment_min_coverage_percent,
        alignment_engine,
        minimap_preset,
        blastn_task,
        blastn_evalue,
        blastn_dust,
        winnowmap_preset,
        winnowmap_kmer,
        winnowmap_repeat_fraction,
        skip_self,
        self_alignment_available,
        tel_enabled,
        cen_enabled,
    })
}

pub(super) fn read_add_ctg_manifest(extract_root: &Path) -> Result<AddCtgManifest> {
    let path = extract_root.join("add_ctg/manifest.tsv");
    if !path.exists() {
        bail!("add_ctg package requires add_ctg/manifest.tsv");
    }
    let values = read_key_value_tsv(&path)
        .with_context(|| format!("failed to parse add_ctg manifest {}", path.display()))?;
    let package_type = required_key_value(&values, "package_type")?;
    if package_type != "add_ctg" {
        bail!(
            "add_ctg package requires package_type=add_ctg, got {}",
            package_type
        );
    }
    let ctg_name = required_key_value(&values, "ctg_name")?;
    if ctg_name.trim().is_empty() {
        bail!("add_ctg manifest requires ctg_name");
    }
    validate_add_dataset_name(&ctg_name)?;
    let derived_dataset = values
        .get("derived_dataset")
        .cloned()
        .unwrap_or_else(|| "derived_ctg".to_string());
    if derived_dataset != "derived_ctg" {
        bail!(
            "add_ctg manifest derived_dataset must be derived_ctg, got {}",
            derived_dataset
        );
    }
    let target_chr = required_key_value(&values, "target_chr")?;
    validate_add_dataset_name(&target_chr)?;
    let target_track = required_key_value(&values, "target_track")?;
    validate_add_dataset_name(&target_track)?;
    let source = values.get("source").cloned().unwrap_or_default();
    if source.contains('\t') || source.contains('\n') || source.contains('\r') {
        bail!("add_ctg manifest source must not contain tabs or newlines");
    }
    let reference_name = required_key_value(&values, "reference_name")?;
    let alignment_engine = values
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    let minimap_preset = values
        .get("minimap_preset")
        .cloned()
        .unwrap_or_else(|| "asm10".to_string());
    let blastn_task = values
        .get("blastn_task")
        .cloned()
        .unwrap_or_else(|| "blastn".to_string());
    let blastn_evalue = values
        .get("blastn_evalue")
        .cloned()
        .unwrap_or_else(|| "1e-10".to_string());
    let blastn_dust = values
        .get("blastn_dust")
        .cloned()
        .unwrap_or_else(|| "no".to_string());
    let winnowmap_preset = values
        .get("winnowmap_preset")
        .cloned()
        .unwrap_or_else(|| "asm20".to_string());
    let winnowmap_kmer = values
        .get("winnowmap_kmer")
        .cloned()
        .unwrap_or_else(|| "19".to_string());
    let winnowmap_repeat_fraction = values
        .get("winnowmap_repeat_fraction")
        .cloned()
        .unwrap_or_else(|| "0.9998".to_string());
    let skip_self = parse_bool_flag(&required_key_value(&values, "skip_self")?, "skip_self")?;
    let self_alignment_scope = values
        .get("self_alignment_scope")
        .cloned()
        .unwrap_or_default();
    let cross_alignment_scope = values
        .get("cross_alignment_scope")
        .cloned()
        .unwrap_or_default();
    let sequence_layout = required_key_value(&values, "sequence_layout")?;
    let preassigned_chr = parse_bool_flag(
        &required_key_value(&values, "preassigned_chr")?,
        "preassigned_chr",
    )?;
    let contains_fasta = values
        .get("contains_fasta")
        .map(|value| parse_bool_flag(value, "contains_fasta"))
        .transpose()?
        .unwrap_or(true);
    Ok(AddCtgManifest {
        ctg_name,
        derived_dataset,
        target_chr,
        target_track,
        source,
        reference_name,
        alignment_engine,
        minimap_preset,
        blastn_task,
        blastn_evalue,
        blastn_dust,
        winnowmap_preset,
        winnowmap_kmer,
        winnowmap_repeat_fraction,
        skip_self,
        self_alignment_scope,
        cross_alignment_scope,
        sequence_layout,
        preassigned_chr,
        contains_fasta,
    })
}

pub(super) fn validate_add_dataset_package(
    project_db_path: &Path,
    workspace_root: &Path,
    project_id: Option<i64>,
    manifest: &AddDatasetManifest,
    payload_root: &Path,
) -> Result<()> {
    if !payload_root.is_dir() {
        bail!("add dataset package is missing gpm_server payload");
    }
    let conn = open_workspace_db(project_db_path)?;
    let existing_dataset_id = conn
        .query_row(
            "SELECT id FROM dataset WHERE name = ?1",
            params![manifest.dataset_name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to check existing dataset names")?;
    if existing_dataset_id.is_some() {
        bail!(
            "dataset {} already exists in workspace",
            manifest.dataset_name
        );
    }

    let workspace_reference_name: String = match project_id {
        Some(project_id) => conn
            .query_row(
                "SELECT rg.name
                 FROM project p
                 JOIN reference_genome rg ON rg.id = p.reference_genome_id
                 WHERE p.id = ?1",
                params![project_id],
                |row| row.get(0),
            )
            .with_context(|| format!("failed to resolve project {project_id} reference"))?,
        None => conn
            .query_row(
                "SELECT name FROM reference_genome WHERE name = ?1",
                params![manifest.reference_name],
                |row| row.get(0),
            )
            .optional()
            .context("failed to resolve workspace reference")?
            .with_context(|| {
                format!(
                    "add dataset reference mismatch: manifest reference={} is not present in workspace",
                    manifest.reference_name
                )
            })?,
    };
    if workspace_reference_name != manifest.reference_name {
        bail!(
            "add dataset reference mismatch: manifest reference={} workspace reference={}",
            manifest.reference_name,
            workspace_reference_name
        );
    }

    let package: PackageRow = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr,
                    chr_assignment_min_coverage_percent, self_alignment_scope,
                    cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok(PackageRow {
                    package_mode: row.get(0)?,
                    sequence_layout: row.get(1)?,
                    preassigned_chr: row.get::<_, i64>(2)? != 0,
                    chr_assignment_min_coverage_percent: row.get(3)?,
                    self_alignment_scope: row.get(4)?,
                    cross_alignment_scope: row.get(5)?,
                })
            },
        )
        .context("failed to load workspace package metadata")?;
    if package.sequence_layout != manifest.sequence_layout {
        bail!(
            "add dataset sequence_layout mismatch: manifest={} workspace={}",
            manifest.sequence_layout,
            package.sequence_layout
        );
    }
    if package.preassigned_chr != manifest.preassigned_chr {
        bail!("add dataset preassigned_chr mismatch");
    }
    if (package.chr_assignment_min_coverage_percent - manifest.chr_assignment_min_coverage_percent)
        .abs()
        > f64::EPSILON
    {
        bail!(
            "add dataset chr_assignment_min_coverage_percent mismatch: manifest={} workspace={}",
            manifest.chr_assignment_min_coverage_percent,
            package.chr_assignment_min_coverage_percent
        );
    }
    let workspace_skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    if workspace_skip_self != manifest.skip_self {
        bail!(
            "add dataset skip_self mismatch: manifest={} workspace={}",
            manifest.skip_self,
            workspace_skip_self
        );
    }
    if manifest.self_alignment_available == manifest.skip_self {
        bail!("add dataset self_alignment_available conflicts with skip_self in manifest");
    }

    let prepare_options = read_workspace_prepare_options_for_add(workspace_root, &package)?;
    validate_add_dataset_alignment_engine(&prepare_options, manifest)?;
    if let Some(workspace_skip_self_value) = prepare_options.get("skip_self") {
        let prepare_skip_self = parse_bool_flag(workspace_skip_self_value, "skip_self")?;
        if prepare_skip_self != manifest.skip_self {
            bail!(
                "add dataset skip_self mismatch: manifest={} prepare_options={}",
                manifest.skip_self,
                prepare_skip_self
            );
        }
    }
    validate_prepare_bool_matches(&prepare_options, "tel_enabled", manifest.tel_enabled)?;
    validate_prepare_bool_matches(&prepare_options, "cen_enabled", manifest.cen_enabled)?;

    validate_add_payload_files(&conn, workspace_root, payload_root, manifest)?;
    Ok(())
}

pub(super) fn validate_add_ctg_package(
    project_db_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    payload_root: &Path,
) -> Result<ValidatedAddCtgPackage> {
    if !payload_root.is_dir() {
        bail!("add_ctg package is missing gpm_server payload");
    }
    if !manifest.contains_fasta {
        bail!("add_ctg import requires contains_fasta=true");
    }

    let conn = open_workspace_db(project_db_path)?;
    let duplicate = conn
        .query_row(
            "SELECT d.name
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE ss.seq_name = ?1
             LIMIT 1",
            params![manifest.ctg_name],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .context("failed to check duplicate add_ctg source names")?;
    if let Some(dataset_name) = duplicate {
        bail!(
            "ctg name already exists: {} (dataset/track: {}). Please choose a different --ctg name.",
            manifest.ctg_name,
            dataset_name
        );
    }

    let (workspace_reference_name, reference_genome_id): (String, i64) = conn
        .query_row(
            "SELECT rg.name, rg.id
             FROM project p
             JOIN reference_genome rg ON rg.id = p.reference_genome_id
             WHERE p.id = ?1",
            params![project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .with_context(|| format!("failed to resolve project {project_id} reference"))?;
    if workspace_reference_name != manifest.reference_name {
        bail!(
            "add_ctg reference mismatch: manifest reference={} workspace reference={}",
            manifest.reference_name,
            workspace_reference_name
        );
    }

    let (target_dataset_id, target_project_count): (i64, i64) = conn
        .query_row(
            "SELECT d.id,
                    COUNT(pd.id)
             FROM dataset d
             LEFT JOIN project_dataset pd
               ON pd.dataset_id = d.id
              AND pd.project_id = ?2
             WHERE d.name = ?1
             GROUP BY d.id",
            params![manifest.target_track, project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .context("failed to resolve add_ctg target track")?
        .with_context(|| {
            format!(
                "add_ctg target track does not exist: {}",
                manifest.target_track
            )
        })?;
    if target_project_count == 0 {
        bail!(
            "add_ctg target track {} is not part of project_id {}",
            manifest.target_track,
            project_id
        );
    }

    let target_reference_chr_id: i64 = conn
        .query_row(
            "SELECT id
             FROM reference_chr
             WHERE reference_genome_id = ?1
               AND chr_name = ?2",
            params![reference_genome_id, manifest.target_chr],
            |row| row.get(0),
        )
        .optional()
        .context("failed to resolve add_ctg target chr")?
        .with_context(|| format!("add_ctg target chr does not exist: {}", manifest.target_chr))?;

    let package: PackageRow = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr,
                    chr_assignment_min_coverage_percent, self_alignment_scope,
                    cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok(PackageRow {
                    package_mode: row.get(0)?,
                    sequence_layout: row.get(1)?,
                    preassigned_chr: row.get::<_, i64>(2)? != 0,
                    chr_assignment_min_coverage_percent: row.get(3)?,
                    self_alignment_scope: row.get(4)?,
                    cross_alignment_scope: row.get(5)?,
                })
            },
        )
        .context("failed to load workspace package metadata")?;
    if package.sequence_layout != manifest.sequence_layout {
        bail!(
            "add_ctg sequence_layout mismatch: manifest={} workspace={}",
            manifest.sequence_layout,
            package.sequence_layout
        );
    }
    if package.preassigned_chr != manifest.preassigned_chr {
        bail!("add_ctg preassigned_chr mismatch");
    }
    if !manifest.self_alignment_scope.is_empty()
        && package.self_alignment_scope != manifest.self_alignment_scope
    {
        bail!(
            "add_ctg self_alignment_scope mismatch: manifest={} workspace={}",
            manifest.self_alignment_scope,
            package.self_alignment_scope
        );
    }
    if !manifest.cross_alignment_scope.is_empty()
        && package.cross_alignment_scope != manifest.cross_alignment_scope
    {
        bail!(
            "add_ctg cross_alignment_scope mismatch: manifest={} workspace={}",
            manifest.cross_alignment_scope,
            package.cross_alignment_scope
        );
    }
    let workspace_skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    if workspace_skip_self != manifest.skip_self {
        bail!(
            "add_ctg skip_self mismatch: manifest={} workspace={}",
            manifest.skip_self,
            workspace_skip_self
        );
    }
    let prepare_options = read_workspace_prepare_options_for_add(workspace_root, &package)?;
    validate_add_ctg_alignment_engine(&prepare_options, manifest)?;
    if let Some(workspace_skip_self_value) = prepare_options.get("skip_self") {
        let prepare_skip_self = parse_bool_flag(workspace_skip_self_value, "skip_self")?;
        if prepare_skip_self != manifest.skip_self {
            bail!(
                "add_ctg skip_self mismatch: manifest={} prepare_options={}",
                manifest.skip_self,
                prepare_skip_self
            );
        }
    }

    validate_add_ctg_payload_files(
        &conn,
        workspace_root,
        payload_root,
        project_id,
        manifest,
        target_dataset_id,
    )?;
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    if chr_assignment.assigned_chr_name != manifest.target_chr {
        bail!(
            "add_ctg chr assignment mismatch: manifest={} payload={}",
            manifest.target_chr,
            chr_assignment.assigned_chr_name
        );
    }
    let track_member_orders = read_imported_track_member_order_rows(payload_root)?;
    validate_add_ctg_track_member_order_snapshot(
        &conn,
        manifest,
        target_dataset_id,
        target_reference_chr_id,
        &track_member_orders,
    )?;
    let derived_row = read_derived_ctg_rows(payload_root)?
        .into_iter()
        .next()
        .context("add_ctg payload is missing derived_ctgs row")?;
    if derived_row.source != manifest.source {
        bail!(
            "add_ctg source mismatch: manifest={} payload={}",
            manifest.source,
            derived_row.source
        );
    }
    read_single_add_ctg_locator(payload_root, manifest)?;
    Ok(ValidatedAddCtgPackage {
        target_dataset_id,
        source_length: chr_assignment.seq_length_bp,
        anchor_start: chr_assignment.anchor_start,
        track_member_orders,
    })
}

pub(super) fn validate_add_ctg_track_member_order_snapshot(
    conn: &rusqlite::Connection,
    manifest: &AddCtgManifest,
    target_dataset_id: i64,
    reference_chr_id: i64,
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    if rows.is_empty()
        || rows.iter().any(|row| {
            row.target_track != manifest.target_track || row.target_chr != manifest.target_chr
        })
    {
        bail!(
            "add_ctg metadata/track_member_orders.tsv must be a full snapshot for {}:{}; regenerate the package with the current server scripts",
            manifest.target_track,
            manifest.target_chr
        );
    }
    let new_member_count = rows
        .iter()
        .filter(|row| {
            row.member_dataset == manifest.derived_dataset && row.member_ctg == manifest.ctg_name
        })
        .count();
    if new_member_count != 1 {
        bail!(
            "add_ctg track order snapshot must contain the new member {} exactly once",
            manifest.ctg_name
        );
    }

    let mut stmt = conn
        .prepare(
            "SELECT member_d.name, member_ss.seq_name
             FROM imported_track_member_order ilmo
             JOIN source_seq member_ss ON member_ss.id = ilmo.source_seq_id
             JOIN dataset member_d ON member_d.id = member_ss.dataset_id
             WHERE ilmo.target_dataset_id = ?1
               AND ilmo.reference_chr_id = ?2
             ORDER BY ilmo.member_order",
        )
        .context("failed to prepare existing track member order lookup")?;
    let existing_members = stmt
        .query_map(params![target_dataset_id, reference_chr_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .context("failed to query existing track member orders")?
        .collect::<std::result::Result<HashSet<_>, _>>()
        .context("failed to decode existing track member orders")?;
    if existing_members.is_empty() {
        bail!(
            "workspace has no authoritative order for {}:{}; reimport a package generated with the current server scripts",
            manifest.target_track,
            manifest.target_chr
        );
    }
    let mut expected_members = existing_members;
    expected_members.insert((manifest.derived_dataset.clone(), manifest.ctg_name.clone()));
    let payload_members = rows
        .iter()
        .map(|row| (row.member_dataset.clone(), row.member_ctg.clone()))
        .collect::<HashSet<_>>();
    if payload_members != expected_members {
        bail!(
            "add_ctg track order snapshot is incomplete for {}:{}; regenerate the package from the matching server workspace",
            manifest.target_track,
            manifest.target_chr
        );
    }
    Ok(())
}

pub(super) fn validate_add_dataset_alignment_engine(
    prepare_options: &HashMap<String, String>,
    manifest: &AddDatasetManifest,
) -> Result<()> {
    let workspace_engine = prepare_options
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    if workspace_engine != manifest.alignment_engine {
        bail!(
            "add dataset alignment_engine mismatch: manifest={} workspace={}",
            manifest.alignment_engine,
            workspace_engine
        );
    }

    match workspace_engine.as_str() {
        "minimap2" => validate_prepare_string_matches(
            prepare_options,
            "minimap_preset",
            &manifest.minimap_preset,
            "asm10",
        ),
        "blastn" => {
            validate_prepare_string_matches(
                prepare_options,
                "blastn_task",
                &manifest.blastn_task,
                "blastn",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "blastn_evalue",
                &manifest.blastn_evalue,
                "1e-10",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "blastn_dust",
                &manifest.blastn_dust,
                "no",
            )
        }
        "winnowmap" => {
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_preset",
                &manifest.winnowmap_preset,
                "asm20",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_kmer",
                &manifest.winnowmap_kmer,
                "19",
            )?;
            validate_prepare_string_matches(
                prepare_options,
                "winnowmap_repeat_fraction",
                &manifest.winnowmap_repeat_fraction,
                "0.9998",
            )
        }
        other => bail!("unsupported workspace alignment_engine: {other}"),
    }
}

pub(super) fn validate_add_ctg_alignment_engine(
    prepare_options: &HashMap<String, String>,
    manifest: &AddCtgManifest,
) -> Result<()> {
    let workspace_engine = prepare_options
        .get("alignment_engine")
        .cloned()
        .unwrap_or_else(|| "minimap2".to_string());
    if workspace_engine != manifest.alignment_engine {
        bail!(
            "add_ctg alignment_engine mismatch: manifest={} workspace={}",
            manifest.alignment_engine,
            workspace_engine
        );
    }

    match workspace_engine.as_str() {
        "minimap2" => validate_prepare_string_matches_for_package(
            "add_ctg",
            prepare_options,
            "minimap_preset",
            &manifest.minimap_preset,
            "asm10",
        ),
        "blastn" => {
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_task",
                &manifest.blastn_task,
                "blastn",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_evalue",
                &manifest.blastn_evalue,
                "1e-10",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "blastn_dust",
                &manifest.blastn_dust,
                "no",
            )
        }
        "winnowmap" => {
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_preset",
                &manifest.winnowmap_preset,
                "asm20",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_kmer",
                &manifest.winnowmap_kmer,
                "19",
            )?;
            validate_prepare_string_matches_for_package(
                "add_ctg",
                prepare_options,
                "winnowmap_repeat_fraction",
                &manifest.winnowmap_repeat_fraction,
                "0.9998",
            )
        }
        other => bail!("unsupported workspace alignment_engine: {other}"),
    }
}

pub(super) fn read_workspace_prepare_options_for_add(
    workspace_root: &Path,
    package: &PackageRow,
) -> Result<HashMap<String, String>> {
    let prepare_options_path = workspace_root.join("metadata/prepare_options.tsv");
    if prepare_options_path.exists() {
        return read_key_value_tsv(&prepare_options_path).with_context(|| {
            format!(
                "failed to parse workspace prepare options {}",
                prepare_options_path.display()
            )
        });
    }

    let skip_self = package.self_alignment_scope.eq_ignore_ascii_case("none");
    let mut values = HashMap::new();
    values.insert("alignment_engine".to_string(), "minimap2".to_string());
    values.insert("minimap_preset".to_string(), "asm10".to_string());
    values.insert("blastn_task".to_string(), "blastn".to_string());
    values.insert("blastn_evalue".to_string(), "1e-10".to_string());
    values.insert("blastn_dust".to_string(), "no".to_string());
    values.insert("winnowmap_preset".to_string(), "asm20".to_string());
    values.insert("winnowmap_kmer".to_string(), "19".to_string());
    values.insert(
        "winnowmap_repeat_fraction".to_string(),
        "0.9998".to_string(),
    );
    values.insert("skip_self".to_string(), skip_self.to_string());
    values.insert(
        "self_alignment_scope".to_string(),
        package.self_alignment_scope.clone(),
    );
    values.insert("tel_enabled".to_string(), "false".to_string());
    values.insert("cen_enabled".to_string(), "false".to_string());
    Ok(values)
}

pub(super) fn validate_prepare_string_matches(
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: &str,
    default_value: &str,
) -> Result<()> {
    let prepare_value = prepare_options
        .get(key)
        .map(String::as_str)
        .unwrap_or(default_value);
    if prepare_value != manifest_value {
        bail!(
            "add dataset {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}

pub(super) fn validate_prepare_string_matches_for_package(
    package_label: &str,
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: &str,
    default_value: &str,
) -> Result<()> {
    let prepare_value = prepare_options
        .get(key)
        .map(String::as_str)
        .unwrap_or(default_value);
    if prepare_value != manifest_value {
        bail!(
            "{package_label} {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}

pub(super) fn validate_prepare_bool_matches(
    prepare_options: &HashMap<String, String>,
    key: &str,
    manifest_value: bool,
) -> Result<()> {
    let prepare_value = parse_bool_flag(&required_key_value(prepare_options, key)?, key)?;
    if prepare_value != manifest_value {
        bail!(
            "add dataset {key} mismatch: manifest={} prepare_options={}",
            manifest_value,
            prepare_value
        );
    }
    Ok(())
}
