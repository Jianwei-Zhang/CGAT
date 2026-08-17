use super::*;

pub(super) fn validate_add_payload_files(
    conn: &rusqlite::Connection,
    workspace_root: &Path,
    payload_root: &Path,
    manifest: &AddDatasetManifest,
) -> Result<()> {
    let dataset_rows = read_dataset_rows(payload_root)?;
    if dataset_rows.len() != 1 || dataset_rows[0].name != manifest.dataset_name {
        bail!(
            "add dataset payload metadata/datasets.tsv must contain only dataset {}",
            manifest.dataset_name
        );
    }
    let chr_assignment_rows = read_imported_chr_assignment_rows(payload_root)?;
    if chr_assignment_rows.is_empty()
        || chr_assignment_rows
            .iter()
            .any(|row| row.dataset_name != manifest.dataset_name)
    {
        bail!(
            "add dataset payload metadata/chr_assignments.tsv is missing rows for {}",
            manifest.dataset_name
        );
    }
    let track_member_orders = read_imported_track_member_order_rows(payload_root)?;
    if track_member_orders.is_empty()
        || track_member_orders
            .iter()
            .any(|row| row.target_track != manifest.dataset_name)
    {
        bail!(
            "add dataset payload metadata/track_member_orders.tsv must contain only target track {}; regenerate the package with the current server scripts",
            manifest.dataset_name
        );
    }
    validate_track_member_orders_against_assignments(&track_member_orders, &chr_assignment_rows)?;
    let locator_rows = read_source_seq_locator_rows(payload_root)?;
    if locator_rows.is_empty()
        || locator_rows
            .iter()
            .any(|row| row.dataset_name != manifest.dataset_name)
    {
        bail!(
            "add dataset payload metadata/source_seq_locator.tsv is missing rows for {}",
            manifest.dataset_name
        );
    }
    let locator_source_names = locator_rows
        .iter()
        .map(|row| (row.dataset_name.clone(), row.seq_name.clone()))
        .collect::<HashSet<_>>();
    let dataset = &dataset_rows[0];
    if dataset.self_alignment_available != manifest.self_alignment_available {
        bail!(
            "add dataset self_alignment_available mismatch: manifest={} payload={}",
            manifest.self_alignment_available,
            dataset.self_alignment_available
        );
    }
    validate_add_payload_relpath("dataset fasta_relpath", &dataset.fasta_relpath)?;
    validate_add_payload_relpath("dataset fai_relpath", &dataset.fai_relpath)?;
    require_payload_file(payload_root, &dataset.fasta_relpath)?;
    require_payload_file(payload_root, &dataset.fai_relpath)?;
    require_payload_file(
        payload_root,
        &format!("runs/{}_vs_ref/result.paf", manifest.dataset_name),
    )?;
    for locator in &locator_rows {
        validate_add_payload_relpath("source_seq_locator fasta_relpath", &locator.fasta_relpath)?;
        require_payload_file(payload_root, &locator.fasta_relpath)?;
    }
    if manifest.tel_enabled && !payload_root.join("tel").exists() {
        bail!("add dataset payload is missing tel payload");
    }
    if manifest.cen_enabled && !payload_root.join("cen").exists() {
        bail!("add dataset payload is missing cen payload");
    }
    let telomere_rules = read_telomere_rule_rows(payload_root)?;
    let telomere_marks = read_telomere_mark_rows(payload_root)?;
    let centromere_marks = read_centromere_mark_rows(payload_root)?;
    let n_regions = read_source_seq_n_region_rows(payload_root)?;
    validate_add_n_region_payload(manifest, &locator_source_names, &n_regions)?;
    validate_add_telomere_payload(
        manifest,
        &locator_source_names,
        &telomere_rules,
        &telomere_marks,
    )?;
    validate_add_centromere_payload(manifest, &locator_source_names, &centromere_marks)?;
    validate_add_alignment_payloads(conn, payload_root, manifest, &chr_assignment_rows)?;
    validate_add_payload_merge_targets(payload_root, workspace_root, payload_root)?;
    Ok(())
}

pub(super) fn validate_add_ctg_payload_files(
    conn: &rusqlite::Connection,
    workspace_root: &Path,
    payload_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
    target_dataset_id: i64,
) -> Result<()> {
    let dataset_rows = read_dataset_rows(payload_root)?;
    if dataset_rows.len() != 1 || dataset_rows[0].name != manifest.derived_dataset {
        bail!(
            "add_ctg payload metadata/datasets.tsv must contain only dataset {}",
            manifest.derived_dataset
        );
    }
    let derived_rows = read_derived_ctg_rows(payload_root)?;
    if derived_rows.len() != 1
        || derived_rows[0].derived_dataset != manifest.derived_dataset
        || derived_rows[0].ctg_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/derived_ctgs.tsv must contain only ctg {}",
            manifest.ctg_name
        );
    }
    let member_rows = read_track_member_rows(payload_root)?;
    if member_rows.len() != 1
        || member_rows[0].member_dataset != manifest.derived_dataset
        || member_rows[0].member_ctg != manifest.ctg_name
        || member_rows[0].target_track != manifest.target_track
        || member_rows[0].target_chr != manifest.target_chr
    {
        bail!(
            "add_ctg payload metadata/track_members.tsv must bind {} to {}:{}",
            manifest.ctg_name,
            manifest.target_track,
            manifest.target_chr
        );
    }
    let chr_assignment = read_single_add_ctg_chr_assignment(payload_root, manifest)?;
    let locator = read_single_add_ctg_locator(payload_root, manifest)?;
    let locator_source_names =
        HashSet::from([(manifest.derived_dataset.clone(), manifest.ctg_name.clone())]);
    let n_regions = read_source_seq_n_region_rows(payload_root)?;
    validate_add_ctg_n_region_payload(manifest, &locator_source_names, &n_regions)?;

    validate_add_payload_relpath(
        "derived source_seq_locator fasta_relpath",
        &locator.fasta_relpath,
    )?;
    require_payload_file(payload_root, &locator.fasta_relpath)?;
    require_payload_file(payload_root, &format!("{}.fai", locator.fasta_relpath))?;
    require_payload_file(
        payload_root,
        &format!("runs/add_ctg/{}_vs_ref/result.paf", manifest.ctg_name),
    )?;
    require_payload_file(
        payload_root,
        &format!(
            "runs/chr_{}/datasets/{}.fa",
            manifest.target_chr, manifest.derived_dataset
        ),
    )?;
    if !manifest.skip_self {
        let required_pairwise_datasets =
            required_add_ctg_pairwise_datasets(conn, project_id, &manifest.target_chr)?;
        if !required_pairwise_datasets
            .iter()
            .any(|(dataset_id, _name)| *dataset_id == target_dataset_id)
        {
            bail!(
                "add_ctg target track {} has no ctgs on target chr {}",
                manifest.target_track,
                manifest.target_chr
            );
        }
        for (_dataset_id, dataset_name) in required_pairwise_datasets {
            require_payload_file(
                payload_root,
                &format!(
                    "runs/chr_{}/add_ctg/{}_vs_{}/result.paf",
                    manifest.target_chr, dataset_name, manifest.ctg_name
                ),
            )?;
        }
    }

    if chr_assignment.seq_length_bp <= 0 {
        bail!("add_ctg payload seq_length_bp must be > 0");
    }
    validate_add_ctg_payload_merge_targets(payload_root, workspace_root, payload_root)?;
    let target_dataset_exists = conn
        .query_row(
            "SELECT id FROM dataset WHERE id = ?1",
            params![target_dataset_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .context("failed to verify add_ctg target dataset")?;
    if target_dataset_exists.is_none() {
        bail!("add_ctg target dataset no longer exists");
    }
    Ok(())
}

pub(super) fn validate_add_ctg_n_region_payload(
    manifest: &AddCtgManifest,
    locator_source_names: &HashSet<(String, String)>,
    regions: &[SourceSeqNRegionRow],
) -> Result<()> {
    for region in regions {
        if region.dataset_name != manifest.derived_dataset || region.seq_name != manifest.ctg_name {
            bail!(
                "add_ctg n payload contains row for {}, expected {}:{}",
                region.seq_name,
                manifest.derived_dataset,
                manifest.ctg_name
            );
        }
        if !locator_source_names.contains(&(region.dataset_name.clone(), region.seq_name.clone())) {
            bail!(
                "add_ctg n payload contains row for unknown source {}:{}",
                region.dataset_name,
                region.seq_name
            );
        }
    }
    Ok(())
}

pub(super) fn validate_add_alignment_payloads(
    conn: &rusqlite::Connection,
    payload_root: &Path,
    manifest: &AddDatasetManifest,
    chr_assignment_rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    let assigned_chrs = chr_assignment_rows
        .iter()
        .map(|row| row.assigned_chr_name.clone())
        .collect::<HashSet<_>>();
    for chr_name in assigned_chrs {
        let chr_run_root = payload_root.join("runs").join(format!("chr_{}", chr_name));
        let self_paf = chr_run_root
            .join(format!("{}_vs_self", manifest.dataset_name))
            .join("result.paf");
        if manifest.skip_self {
            if self_paf.exists() {
                bail!(
                    "add dataset payload contains self alignment while skip_self=true: {}",
                    self_paf.display()
                );
            }
        } else if !self_paf.is_file() {
            bail!(
                "add dataset payload is missing self alignment payload for {} chr {}",
                manifest.dataset_name,
                chr_name
            );
        }

        let existing_dataset_names =
            existing_dataset_names_with_chr_assignment(conn, &chr_name, &manifest.dataset_name)?;
        for existing_name in existing_dataset_names {
            let existing_vs_added = chr_run_root
                .join(format!("{}_vs_{}", existing_name, manifest.dataset_name))
                .join("result.paf");
            let added_vs_existing = chr_run_root
                .join(format!("{}_vs_{}", manifest.dataset_name, existing_name))
                .join("result.paf");
            if !existing_vs_added.is_file() && !added_vs_existing.is_file() {
                bail!(
                    "add dataset payload is missing pairwise alignment payload for {} and {} chr {}",
                    manifest.dataset_name,
                    existing_name,
                    chr_name
                );
            }
        }
    }
    Ok(())
}

pub(super) fn existing_dataset_names_with_chr_assignment(
    conn: &rusqlite::Connection,
    chr_name: &str,
    added_dataset_name: &str,
) -> Result<Vec<String>> {
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT d.name
             FROM imported_chr_assignment ica
             JOIN source_seq ss ON ss.id = ica.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             WHERE rc.chr_name = ?1
               AND d.name <> ?2
             ORDER BY d.id",
        )
        .context("failed to prepare existing dataset chr-assignment lookup")?;
    stmt.query_map(params![chr_name, added_dataset_name], |row| row.get(0))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode existing dataset chr-assignment rows")
}

pub(super) fn validate_add_telomere_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    rules: &[TelomereRuleRow],
    marks: &[TelomereMarkRow],
) -> Result<()> {
    if !manifest.tel_enabled && (!rules.is_empty() || !marks.is_empty()) {
        bail!("add dataset tel payload is present but manifest tel_enabled=false");
    }
    for mark in marks {
        validate_add_marker_dataset_source(
            "tel",
            &manifest.dataset_name,
            locator_source_names,
            &mark.dataset_name,
            &mark.seq_name,
        )?;
    }
    Ok(())
}

pub(super) fn validate_add_centromere_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    marks: &[CentromereMarkRow],
) -> Result<()> {
    if !manifest.cen_enabled && !marks.is_empty() {
        bail!("add dataset cen payload is present but manifest cen_enabled=false");
    }
    for mark in marks {
        validate_add_marker_dataset_source(
            "cen",
            &manifest.dataset_name,
            locator_source_names,
            &mark.dataset_name,
            &mark.seq_name,
        )?;
    }
    Ok(())
}

pub(super) fn validate_add_marker_dataset_source(
    payload_name: &str,
    manifest_dataset_name: &str,
    locator_source_names: &HashSet<(String, String)>,
    dataset_name: &str,
    seq_name: &str,
) -> Result<()> {
    if dataset_name != manifest_dataset_name {
        bail!(
            "add dataset {payload_name} payload contains row for dataset {}, expected {}",
            dataset_name,
            manifest_dataset_name
        );
    }
    if !locator_source_names.contains(&(dataset_name.to_string(), seq_name.to_string())) {
        bail!(
            "add dataset {payload_name} payload contains row for unknown source {}:{}",
            dataset_name,
            seq_name
        );
    }
    Ok(())
}

pub(super) fn validate_add_n_region_payload(
    manifest: &AddDatasetManifest,
    locator_source_names: &HashSet<(String, String)>,
    regions: &[SourceSeqNRegionRow],
) -> Result<()> {
    for region in regions {
        validate_add_marker_dataset_source(
            "n",
            &manifest.dataset_name,
            locator_source_names,
            &region.dataset_name,
            &region.seq_name,
        )?;
    }
    Ok(())
}

pub(super) fn validate_add_payload_merge_targets(
    payload_root: &Path,
    workspace_root: &Path,
    path: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            validate_add_payload_merge_targets(payload_root, workspace_root, &source)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if !is_allowed_add_payload_file(&rel) {
            bail!("unexpected add dataset payload file: {}", rel);
        }
        if is_appendable_add_payload_tsv(&rel) || rel == "tel/rules.tsv" {
            continue;
        }
        let target = workspace_root.join(relpath);
        if target.exists() {
            bail!(
                "add dataset payload target already exists: {}",
                target.display()
            );
        }
    }
    Ok(())
}

pub(super) fn validate_add_ctg_payload_merge_targets(
    payload_root: &Path,
    workspace_root: &Path,
    path: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add_ctg payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            validate_add_ctg_payload_merge_targets(payload_root, workspace_root, &source)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!(
                "failed to relativize add_ctg payload path {}",
                source.display()
            )
        })?;
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if !is_allowed_add_ctg_payload_file(&rel) {
            bail!("unexpected add_ctg payload file: {}", rel);
        }
        if is_appendable_add_ctg_payload_tsv(&rel)
            || is_appendable_add_ctg_fasta(&rel)
            || is_appendable_add_ctg_fai(&rel)
            || rel == "metadata/track_member_orders.tsv"
            || rel == "metadata/datasets.tsv"
        {
            continue;
        }
        let target = workspace_root.join(relpath);
        if target.exists() {
            bail!(
                "add_ctg payload target already exists: {}",
                target.display()
            );
        }
    }
    Ok(())
}

pub(super) fn require_payload_file(payload_root: &Path, relpath: &str) -> Result<()> {
    validate_add_payload_relpath("payload file", relpath)?;
    if !payload_root.join(relpath).is_file() {
        bail!("add dataset payload is missing {}", relpath);
    }
    Ok(())
}

pub(super) fn validate_add_dataset_name(dataset_name: &str) -> Result<()> {
    if dataset_name.contains('/') || dataset_name.contains('\\') {
        bail!(
            "add dataset manifest dataset_name must not contain path separators: {}",
            dataset_name
        );
    }
    let name_path = Path::new(dataset_name);
    if name_path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!(
            "add dataset manifest dataset_name must be a plain name: {}",
            dataset_name
        );
    }
    Ok(())
}

pub(super) fn validate_add_payload_relpath(field_name: &str, relpath: &str) -> Result<()> {
    let path = Path::new(relpath);
    if relpath.trim().is_empty() || path.is_absolute() {
        bail!("add dataset payload {field_name} must be a relative path: {relpath}");
    }
    if relpath.contains('\\') {
        bail!("add dataset payload {field_name} contains unsafe path separator: {relpath}");
    }
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_) | Component::CurDir))
    {
        bail!("add dataset payload {field_name} contains unsafe path traversal: {relpath}");
    }
    Ok(())
}

pub(super) fn read_imported_chr_assignment_rows(
    bundle_root: &Path,
) -> Result<Vec<ImportedChrAssignmentRow>> {
    let path = bundle_root.join("metadata/chr_assignments.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/chr_assignments.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        let source_orientation = value_by_header(header, cols, "source_orientation")?;
        if source_orientation != "+" && source_orientation != "-" {
            bail!("invalid source_orientation: {source_orientation}");
        }
        let orientation_source = value_by_header(header, cols, "orientation_source")?;
        if orientation_source != "ref_alignment" {
            bail!("invalid orientation_source: {orientation_source}");
        }
        Ok(ImportedChrAssignmentRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            seq_length_bp: value_by_header(header, cols, "seq_length_bp")?
                .parse()
                .with_context(|| "invalid seq_length_bp".to_string())?,
            assigned_chr_name: value_by_header(header, cols, "assigned_chr_name")?,
            source_orientation,
            orientation_source,
            support_bp: value_by_header(header, cols, "support_bp")?
                .parse()
                .with_context(|| "invalid support_bp".to_string())?,
            support_percent: parse_f64_value(
                &value_by_header(header, cols, "support_percent")?,
                "support_percent",
            )?,
            anchor_start: value_by_header(header, cols, "anchor_start")?
                .parse()
                .with_context(|| "invalid anchor_start".to_string())?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_imported_track_member_order_rows(
    bundle_root: &Path,
) -> Result<Vec<ImportedTrackMemberOrderRow>> {
    let path = bundle_root.join("metadata/track_member_orders.tsv");
    if !path.exists() {
        bail!(
            "server delivery package requires metadata/track_member_orders.tsv; regenerate the package with the current server scripts"
        );
    }
    let expected_header = [
        "target_track",
        "target_chr",
        "member_dataset",
        "member_ctg",
        "member_order",
    ];
    let file = File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
    let header_line = BufReader::new(file)
        .lines()
        .next()
        .transpose()
        .with_context(|| format!("failed to read header from {}", path.display()))?
        .ok_or_else(|| anyhow::anyhow!("missing header in {}", path.display()))?;
    let header = header_line.split('\t').map(str::trim).collect::<Vec<_>>();
    if header != expected_header {
        bail!(
            "invalid metadata/track_member_orders.tsv header; regenerate the package with the current server scripts"
        );
    }
    let rows = read_tsv_rows(&path, |header, cols| {
        let member_order = value_by_header(header, cols, "member_order")?
            .parse::<i64>()
            .with_context(|| "invalid member_order".to_string())?;
        Ok(ImportedTrackMemberOrderRow {
            target_track: value_by_header(header, cols, "target_track")?,
            target_chr: value_by_header(header, cols, "target_chr")?,
            member_dataset: value_by_header(header, cols, "member_dataset")?,
            member_ctg: value_by_header(header, cols, "member_ctg")?,
            member_order,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))?;
    validate_imported_track_member_order_rows(&rows)?;
    Ok(rows)
}

pub(super) fn validate_imported_track_member_order_rows(
    rows: &[ImportedTrackMemberOrderRow],
) -> Result<()> {
    let mut groups: HashMap<(&str, &str), Vec<&ImportedTrackMemberOrderRow>> = HashMap::new();
    let mut members = HashSet::new();
    for row in rows {
        if row.target_track.is_empty()
            || row.target_chr.is_empty()
            || row.member_dataset.is_empty()
            || row.member_ctg.is_empty()
            || row.member_order < 1
        {
            bail!(
                "invalid metadata/track_member_orders.tsv row; regenerate the package with the current server scripts"
            );
        }
        let member_key = (
            row.target_track.as_str(),
            row.target_chr.as_str(),
            row.member_dataset.as_str(),
            row.member_ctg.as_str(),
        );
        if !members.insert(member_key) {
            bail!(
                "duplicate member in metadata/track_member_orders.tsv for {}:{} {}:{}",
                row.target_track,
                row.target_chr,
                row.member_dataset,
                row.member_ctg
            );
        }
        groups
            .entry((row.target_track.as_str(), row.target_chr.as_str()))
            .or_default()
            .push(row);
    }
    for ((target_track, target_chr), group) in groups {
        let mut orders = group.iter().map(|row| row.member_order).collect::<Vec<_>>();
        orders.sort_unstable();
        let expected = (1..=orders.len() as i64).collect::<Vec<_>>();
        if orders != expected {
            bail!(
                "member_order must be unique and contiguous from 1 for {}:{}; regenerate the package with the current server scripts",
                target_track,
                target_chr
            );
        }
    }
    Ok(())
}

pub(super) fn validate_track_member_orders_against_assignments(
    order_rows: &[ImportedTrackMemberOrderRow],
    assignment_rows: &[ImportedChrAssignmentRow],
) -> Result<()> {
    let assignments = assignment_rows
        .iter()
        .map(|row| {
            (
                row.dataset_name.as_str(),
                row.seq_name.as_str(),
                row.assigned_chr_name.as_str(),
            )
        })
        .collect::<HashSet<_>>();
    for row in order_rows {
        if !assignments.contains(&(
            row.member_dataset.as_str(),
            row.member_ctg.as_str(),
            row.target_chr.as_str(),
        )) {
            bail!(
                "track member order has no matching chr assignment: {}:{} on {}; regenerate the package with the current server scripts",
                row.member_dataset,
                row.member_ctg,
                row.target_chr
            );
        }
    }
    for assignment in assignment_rows {
        let matching = order_rows
            .iter()
            .filter(|row| {
                row.member_dataset == assignment.dataset_name
                    && row.member_ctg == assignment.seq_name
                    && row.target_chr == assignment.assigned_chr_name
            })
            .count();
        if matching != 1 {
            bail!(
                "chr assignment {}:{} on {} must have exactly one track member order; regenerate the package with the current server scripts",
                assignment.dataset_name,
                assignment.seq_name,
                assignment.assigned_chr_name
            );
        }
        if assignment.dataset_name != "derived_ctg"
            && !order_rows.iter().any(|row| {
                row.target_track == assignment.dataset_name
                    && row.target_chr == assignment.assigned_chr_name
                    && row.member_dataset == assignment.dataset_name
                    && row.member_ctg == assignment.seq_name
            })
        {
            bail!(
                "normal chr assignment {}:{} is ordered under the wrong target track; regenerate the package with the current server scripts",
                assignment.dataset_name,
                assignment.seq_name
            );
        }
    }
    Ok(())
}

pub(super) fn read_reference_chr_locator_rows(
    bundle_root: &Path,
) -> Result<Vec<ReferenceChrLocatorRow>> {
    let path = bundle_root.join("metadata/reference_chr_locator.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/reference_chr_locator.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(ReferenceChrLocatorRow {
            reference_chr_name: value_by_header(header, cols, "reference_chr_name")?,
            fasta_relpath: value_by_header(header, cols, "fasta_relpath")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_source_seq_locator_rows(bundle_root: &Path) -> Result<Vec<SourceSeqLocatorRow>> {
    let path = bundle_root.join("metadata/source_seq_locator.tsv");
    if !path.exists() {
        bail!("server delivery package requires metadata/source_seq_locator.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(SourceSeqLocatorRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            fasta_relpath: value_by_header(header, cols, "fasta_relpath")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_derived_ctg_rows(bundle_root: &Path) -> Result<Vec<DerivedCtgRow>> {
    let path = bundle_root.join("metadata/derived_ctgs.tsv");
    if !path.exists() {
        bail!("add_ctg package requires metadata/derived_ctgs.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(DerivedCtgRow {
            derived_dataset: value_by_header(header, cols, "derived_dataset")?,
            ctg_name: value_by_header(header, cols, "ctg_name")?,
            source: value_by_header(header, cols, "source")?,
            source_fasta_name: value_by_header(header, cols, "source_fasta_name")?,
            source_fasta_sha256: value_by_header(header, cols, "source_fasta_sha256")?,
            created_at: value_by_header(header, cols, "created_at")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_track_member_rows(bundle_root: &Path) -> Result<Vec<TrackMemberRow>> {
    let path = bundle_root.join("metadata/track_members.tsv");
    if !path.exists() {
        bail!("add_ctg package requires metadata/track_members.tsv");
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(TrackMemberRow {
            member_dataset: value_by_header(header, cols, "member_dataset")?,
            member_ctg: value_by_header(header, cols, "member_ctg")?,
            target_chr: value_by_header(header, cols, "target_chr")?,
            target_track: value_by_header(header, cols, "target_track")?,
            member_role: value_by_header(header, cols, "member_role")?,
            created_at: value_by_header(header, cols, "created_at")?,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_single_add_ctg_chr_assignment(
    payload_root: &Path,
    manifest: &AddCtgManifest,
) -> Result<ImportedChrAssignmentRow> {
    let rows = read_imported_chr_assignment_rows(payload_root)?;
    if rows.len() != 1
        || rows[0].dataset_name != manifest.derived_dataset
        || rows[0].seq_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/chr_assignments.tsv must contain only {}:{}",
            manifest.derived_dataset,
            manifest.ctg_name
        );
    }
    Ok(rows[0].clone())
}

pub(super) fn read_single_add_ctg_locator(
    payload_root: &Path,
    manifest: &AddCtgManifest,
) -> Result<SourceSeqLocatorRow> {
    let rows = read_source_seq_locator_rows(payload_root)?;
    if rows.len() != 1
        || rows[0].dataset_name != manifest.derived_dataset
        || rows[0].seq_name != manifest.ctg_name
    {
        bail!(
            "add_ctg payload metadata/source_seq_locator.tsv must contain only {}:{}",
            manifest.derived_dataset,
            manifest.ctg_name
        );
    }
    Ok(rows[0].clone())
}

pub(super) fn read_source_seq_n_region_rows(
    bundle_root: &Path,
) -> Result<Vec<SourceSeqNRegionRow>> {
    let path = bundle_root.join("metadata/source_seq_n_regions.tsv");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_tsv_rows(&path, |header, cols| {
        let start_bp = value_by_header(header, cols, "start_bp")?
            .parse()
            .with_context(|| "invalid n region start_bp".to_string())?;
        let end_bp = value_by_header(header, cols, "end_bp")?
            .parse()
            .with_context(|| "invalid n region end_bp".to_string())?;
        let length_bp = value_by_header(header, cols, "length_bp")?
            .parse()
            .with_context(|| "invalid n region length_bp".to_string())?;
        if start_bp < 1 || end_bp < start_bp || length_bp != end_bp - start_bp + 1 {
            bail!(
                "invalid n region coordinates start_bp={} end_bp={} length_bp={}",
                start_bp,
                end_bp,
                length_bp
            );
        }
        Ok(SourceSeqNRegionRow {
            dataset_name: value_by_header(header, cols, "dataset_name")?,
            seq_name: value_by_header(header, cols, "seq_name")?,
            start_bp,
            end_bp,
            length_bp,
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_telomere_rule_rows(bundle_root: &Path) -> Result<Vec<TelomereRuleRow>> {
    let path = bundle_root.join("tel/rules.tsv");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_tsv_rows(&path, |header, cols| {
        Ok(TelomereRuleRow {
            rule_id: value_by_header(header, cols, "rule_id")?,
            motif: value_by_header(header, cols, "motif")?,
            min_repeat: value_by_header(header, cols, "min_repeat")?
                .parse()
                .with_context(|| "invalid tel min_repeat".to_string())?,
            reverse_complement: optional_value_by_header(header, cols, "reverse_complement")
                .map(|value| parse_bool_flag(&value, "reverse_complement"))
                .transpose()?
                .unwrap_or(true),
        })
    })
    .with_context(|| format!("failed to parse {}", path.display()))
}

pub(super) fn read_telomere_mark_rows(bundle_root: &Path) -> Result<Vec<TelomereMarkRow>> {
    let tel_root = bundle_root.join("tel");
    if !tel_root.exists() {
        return Ok(Vec::new());
    }
    let mut rows = Vec::new();
    for entry in fs::read_dir(&tel_root)
        .with_context(|| format!("failed to read tel dir {}", tel_root.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read tel entry {}", tel_root.display()))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let dir_name = entry.file_name().to_string_lossy().to_string();
        if !dir_name.starts_with("chr_") {
            continue;
        }
        for mark_entry in fs::read_dir(&path)
            .with_context(|| format!("failed to read tel chr dir {}", path.display()))?
        {
            let mark_entry = mark_entry
                .with_context(|| format!("failed to read tel mark entry {}", path.display()))?;
            let mark_path = mark_entry.path();
            if mark_path.extension().and_then(|value| value.to_str()) != Some("tsv") {
                continue;
            }
            let mut file_rows = read_tsv_rows(&mark_path, |header, cols| {
                let strand = value_by_header(header, cols, "strand")?;
                if strand != "+" && strand != "-" {
                    bail!("invalid tel strand: {}", strand);
                }
                Ok(TelomereMarkRow {
                    rule_id: value_by_header(header, cols, "rule_id")?,
                    dataset_name: value_by_header(header, cols, "dataset_name")?,
                    seq_name: value_by_header(header, cols, "seq_name")?,
                    assigned_chr_name: value_by_header(header, cols, "assigned_chr_name")?,
                    motif: value_by_header(header, cols, "motif")?,
                    min_repeat: value_by_header(header, cols, "min_repeat")?
                        .parse()
                        .with_context(|| "invalid tel mark min_repeat".to_string())?,
                    repeat_count: value_by_header(header, cols, "repeat_count")?
                        .parse()
                        .with_context(|| "invalid tel repeat_count".to_string())?,
                    start_bp: value_by_header(header, cols, "start_bp")?
                        .parse()
                        .with_context(|| "invalid tel start_bp".to_string())?,
                    end_bp: value_by_header(header, cols, "end_bp")?
                        .parse()
                        .with_context(|| "invalid tel end_bp".to_string())?,
                    strand,
                })
            })
            .with_context(|| format!("failed to parse {}", mark_path.display()))?;
            rows.append(&mut file_rows);
        }
    }
    Ok(rows)
}

pub(super) fn read_centromere_mark_rows(bundle_root: &Path) -> Result<Vec<CentromereMarkRow>> {
    let cen_root = bundle_root.join("cen");
    if !cen_root.exists() {
        return Ok(Vec::new());
    }
    let mut rows = Vec::new();
    for entry in fs::read_dir(&cen_root)
        .with_context(|| format!("failed to read cen dir {}", cen_root.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read cen entry {}", cen_root.display()))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let dir_name = entry.file_name().to_string_lossy().to_string();
        if !dir_name.starts_with("chr_") {
            continue;
        }
        let mark_path = path.join("marks.tsv");
        if !mark_path.exists() {
            continue;
        }
        let mut file_rows = read_tsv_rows(&mark_path, |header, cols| {
            let strand = value_by_header(header, cols, "strand")?;
            if strand != "+" && strand != "-" {
                bail!("invalid cen strand: {}", strand);
            }
            Ok(CentromereMarkRow {
                cen_id: value_by_header(header, cols, "cen_id")?,
                assigned_chr_name: value_by_header(header, cols, "chr_name")?,
                query_name: value_by_header(header, cols, "query_name")?,
                dataset_name: value_by_header(header, cols, "dataset_name")?,
                seq_name: value_by_header(header, cols, "ctg_name")?,
                start_bp: value_by_header(header, cols, "ctg_start")?
                    .parse()
                    .with_context(|| "invalid cen ctg_start".to_string())?,
                end_bp: value_by_header(header, cols, "ctg_end")?
                    .parse()
                    .with_context(|| "invalid cen ctg_end".to_string())?,
                strand,
                align_length: value_by_header(header, cols, "align_length")?
                    .parse()
                    .with_context(|| "invalid cen align_length".to_string())?,
                identity: value_by_header(header, cols, "identity")?
                    .parse()
                    .with_context(|| "invalid cen identity".to_string())?,
                mapq: value_by_header(header, cols, "mapq")?
                    .parse()
                    .with_context(|| "invalid cen mapq".to_string())?,
            })
        })
        .with_context(|| format!("failed to parse {}", mark_path.display()))?;
        rows.append(&mut file_rows);
    }
    Ok(rows)
}
