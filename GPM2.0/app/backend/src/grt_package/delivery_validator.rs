use super::*;

/// Validate the delivery contract selected by metadata/package.tsv. Server
/// workdirs keep using the exhaustive GRT closure validator; App delivery
/// archives use the projected contract and therefore do not need Server-only
/// q-stage, donor, evidence, cache, or checkpoint artifacts.
pub(crate) fn validate_grt_delivery_package_with_progress<P>(
    bundle_root: &Path,
    on_progress: &mut P,
) -> Result<ValidatedGrtPackage>
where
    P: FnMut(&'static str, &'static str),
{
    let workflow = fs::read_to_string(bundle_root.join("metadata/package.tsv"))
        .ok()
        .and_then(|text| {
            let mut lines = text.lines();
            let header = lines.next()?.split('\t').collect::<Vec<_>>();
            let workflow_index = header.iter().position(|column| *column == "workflow")?;
            let row = lines
                .find(|line| !line.trim().is_empty())?
                .split('\t')
                .collect::<Vec<_>>();
            row.get(workflow_index).map(|value| value.to_string())
        });
    if workflow
        .as_deref()
        .is_some_and(|value| value.starts_with("gpm_grt_app_"))
    {
        validate_grt_app_package_with_progress(bundle_root, on_progress)
    } else {
        validate_grt_package_with_progress(bundle_root, on_progress)
    }
}

pub(super) fn validate_grt_app_package_with_progress<P>(
    bundle_root: &Path,
    on_progress: &mut P,
) -> Result<ValidatedGrtPackage>
where
    P: FnMut(&'static str, &'static str),
{
    if !bundle_root.is_dir() {
        return grt_err(
            "MISSING_BUNDLE",
            format!("bundle directory does not exist: {}", bundle_root.display()),
        );
    }
    on_progress(
        "validate_grt_app_required_files",
        "checking minimal App delivery files",
    );
    let core_specs: &[(&str, &[&str], usize, Option<usize>)] = &[
        ("metadata/package.tsv", PACKAGE_HEADER, 1, Some(1)),
        ("metadata/reference.tsv", REFERENCE_HEADER, 1, Some(1)),
        ("metadata/datasets.tsv", DATASETS_HEADER, 1, None),
        (
            "metadata/source_seq_locator.tsv",
            SOURCE_LOCATOR_HEADER,
            1,
            None,
        ),
        (
            "metadata/chr_assignments.tsv",
            CHR_ASSIGNMENTS_HEADER,
            1,
            None,
        ),
        (
            "metadata/track_member_orders.tsv",
            TRACK_MEMBER_ORDERS_HEADER,
            1,
            None,
        ),
        (
            "metadata/reference_chr_locator.tsv",
            REFERENCE_CHR_LOCATOR_HEADER,
            1,
            None,
        ),
        (
            "metadata/source_seq_n_regions.tsv",
            SOURCE_N_REGIONS_HEADER,
            0,
            None,
        ),
        ("metadata/grt_recipe.tsv", RECIPE_HEADER, 1, Some(1)),
        (
            "metadata/grt_used_contigs.tsv",
            USED_CONTIGS_HEADER,
            0,
            None,
        ),
    ];
    let mut tables = HashMap::new();
    for (relpath, header, minimum, maximum) in core_specs {
        tables.insert(
            *relpath,
            read_tsv(bundle_root, relpath, header, *minimum, *maximum)?,
        );
    }
    let package = one_row(&tables, "metadata/package.tsv")?;
    if field(package, "workflow")? != GRT_APP_WORKFLOW
        || field(package, "schema_version")? != GRT_SCHEMA_VERSION
        || field(package, "final_path_schema_version")? != GRT_FINAL_PATH_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "expected gpm_grt_app_precomputed_v2 schema 2 / Final Path schema 1",
        );
    }
    if !parse_bool(
        field(package, "grt_precompute_enabled")?,
        "package.grt_precompute_enabled",
    )? || !parse_bool(field(package, "recipe_locked")?, "package.recipe_locked")?
    {
        return grt_err(
            "INVALID_VALUE",
            "App package must retain a precomputed and locked GRT result",
        );
    }
    if field(package, "sequence_layout")? != "partitioned"
        || !parse_bool(
            field(package, "preassigned_chr")?,
            "package.preassigned_chr",
        )?
    {
        return grt_err(
            "INVALID_VALUE",
            "App package requires partitioned, preassigned chromosome data",
        );
    }
    let package_mode = field(package, "package_mode")?;
    if !matches!(package_mode, "full" | "no_fasta") {
        return grt_err(
            "INVALID_VALUE",
            format!("unsupported App package_mode={package_mode}"),
        );
    }
    let threshold = parse_f64(
        field(package, "chr_assignment_min_coverage_percent")?,
        "package threshold",
    )?;
    if !(0.0..=100.0).contains(&threshold) {
        return grt_err(
            "INVALID_VALUE",
            "package threshold must be between 0 and 100",
        );
    }
    let reads_qc = parse_bool(
        field(package, "reads_qc_enabled")?,
        "package.reads_qc_enabled",
    )?;

    let manifest = read_json(bundle_root, "metadata/grt_app_manifest.json")?;
    let manifest_object = manifest.as_object().ok_or_else(|| {
        grt_anyhow(
            "INVALID_JSON",
            "metadata/grt_app_manifest.json must be an object",
        )
    })?;
    if json_str(manifest_object, "workflow", "App manifest")? != GRT_APP_WORKFLOW
        || json_str(manifest_object, "schema_version", "App manifest")? != GRT_SCHEMA_VERSION
        || json_str(manifest_object, "package_kind", "App manifest")? != package_mode
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "App manifest and package metadata disagree",
        );
    }
    let fasta_available = manifest_object
        .get("fasta_available")
        .and_then(Value::as_bool)
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App manifest.fasta_available must be boolean",
            )
        })?;
    if fasta_available != (package_mode == "full") {
        return grt_err(
            "INVALID_VALUE",
            "App manifest FASTA mode disagrees with package mode",
        );
    }
    let q4_relpath = json_str(manifest_object, "q4_relpath", "App manifest")?;
    if q4_relpath != "grt/q/q4.fa" {
        return grt_err(
            "INVALID_PATH",
            "App manifest q4_relpath must be grt/q/q4.fa",
        );
    }
    let q4_artifact_sha256 =
        json_nonempty_str(manifest_object, "q4_artifact_sha256", "App manifest")?;
    validate_sha256(q4_artifact_sha256, "App manifest.q4_artifact_sha256")?;
    validate_sha256(
        json_nonempty_str(manifest_object, "final_path_sha256", "App manifest")?,
        "App manifest.final_path_sha256",
    )?;

    on_progress(
        "validate_grt_app_fai",
        "validating source and reference FAI lengths",
    );
    let datasets = table(&tables, "metadata/datasets.tsv")?;
    let mut dataset_names = HashSet::new();
    let mut dataset_fai = HashMap::<String, BTreeMap<String, usize>>::new();
    for row in &datasets.rows {
        let dataset = nonempty(row, "dataset_name", "dataset")?;
        if !dataset_names.insert(dataset.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate dataset_name={dataset}"));
        }
        let fai_path = required_bundle_file(
            bundle_root,
            field(row, "fai_relpath")?,
            &format!("dataset {dataset} FAI"),
        )?;
        dataset_fai.insert(
            dataset.to_string(),
            read_fai_lengths(&fai_path, &format!("dataset {dataset}"))?,
        );
        parse_bool(
            field(row, "self_alignment_available")?,
            &format!("dataset {dataset}.self_alignment_available"),
        )?;
    }
    let reference = one_row(&tables, "metadata/reference.tsv")?;
    let reference_fai = required_bundle_file(
        bundle_root,
        field(reference, "fai_relpath")?,
        "reference FAI",
    )?;
    let reference_records = read_fai_lengths(&reference_fai, "reference")?;
    let sources = source_length_catalog(
        bundle_root,
        table(&tables, "metadata/source_seq_locator.tsv")?,
        &dataset_fai,
    )?;

    let mut assignment_baselines = HashMap::<(String, String, String), (String, i64)>::new();
    let mut assignment_ids = HashSet::new();
    for row in &table(&tables, "metadata/chr_assignments.tsv")?.rows {
        let dataset = field(row, "dataset_name")?.to_string();
        let seq = field(row, "seq_name")?.to_string();
        let key = (dataset.clone(), seq.clone());
        let source_length = sources.get(&key).ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown source {dataset}:{seq}"),
            )
        })?;
        let chr = nonempty(row, "assigned_chr_name", "chr assignment chromosome")?;
        if !reference_records.contains_key(chr) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown chromosome {chr}"),
            );
        }
        if !assignment_ids.insert((key.clone(), chr.to_string())) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate chr assignment {dataset}:{seq}:{chr}"),
            );
        }
        let orient = orientation(
            field(row, "source_orientation")?,
            "chr assignment source_orientation",
        )?;
        if field(row, "orientation_source")? != "ref_alignment" {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment orientation_source must be ref_alignment",
            );
        }
        if parse_positive_i64(field(row, "seq_length_bp")?, "chr assignment seq_length_bp")?
            as usize
            != *source_length
        {
            return grt_err(
                "COUNT_MISMATCH",
                format!("chr assignment source length differs for {dataset}:{seq}"),
            );
        }
        let support =
            parse_positive_i64(field(row, "support_bp")?, "chr assignment support_bp")? as usize;
        if support > *source_length {
            return grt_err(
                "INVALID_COORDINATE",
                "chr assignment support exceeds source length",
            );
        }
        let support_percent = parse_f64(
            field(row, "support_percent")?,
            "chr assignment support_percent",
        )?;
        if !(0.0..=100.0).contains(&support_percent) {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment support_percent must be between 0 and 100",
            );
        }
        assignment_baselines.insert(
            (dataset, seq, chr.to_string()),
            (
                orient.to_string(),
                parse_i64(field(row, "anchor_start")?, "chr assignment anchor_start")?,
            ),
        );
    }

    let recipe = one_row(&tables, "metadata/grt_recipe.tsv")?;
    let primary_dataset = nonempty(recipe, "primary_dataset", "recipe primary dataset")?;
    if !dataset_names.contains(primary_dataset) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe primary_dataset is absent from datasets.tsv",
        );
    }
    let support_datasets = json_string_list(
        field(recipe, "support_datasets_json")?,
        "recipe.support_datasets_json",
    )?;
    let mut support_seen = HashSet::new();
    if support_datasets.iter().any(|name| {
        name == primary_dataset
            || !dataset_names.contains(name)
            || !support_seen.insert(name.clone())
    }) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe support datasets must be unique, known, and exclude primary",
        );
    }
    if parse_bool(
        field(recipe, "reads_qc_enabled")?,
        "recipe.reads_qc_enabled",
    )? != reads_qc
    {
        return grt_err(
            "INVALID_VALUE",
            "recipe and package reads_qc_enabled disagree",
        );
    }
    if field(recipe, "final_q_relpath")? != q4_relpath {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe final_q_relpath differs from App manifest",
        );
    }

    validate_app_source_cards(
        table(&tables, "metadata/grt_used_contigs.tsv")?,
        &sources,
        &assignment_baselines,
        &reference_records,
    )?;
    let source_sequences = if fasta_available {
        Some(source_catalog(
            bundle_root,
            table(&tables, "metadata/source_seq_locator.tsv")?,
        )?)
    } else {
        None
    };
    let final_path = read_json(bundle_root, "metadata/grt_final_path.json")?;
    let (q4_lengths, _q4_records) = validate_app_final_path(
        bundle_root,
        &final_path,
        &reference_records,
        &sources,
        manifest_object,
        fasta_available,
        source_sequences.as_ref(),
    )?;
    if let Some(expected_lengths) = manifest_object
        .get("q4_chromosome_lengths")
        .and_then(Value::as_object)
    {
        for (chr, expected) in expected_lengths {
            let value = expected.as_u64().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "App manifest chromosome length is invalid")
            })?;
            if q4_lengths.get(chr).copied() != Some(value as usize) {
                return grt_err(
                    "FINAL_PATH_MISMATCH",
                    format!("App manifest q4 length differs for {chr}"),
                );
            }
        }
    }
    let expected_total =
        json_positive_i64(manifest_object, "q4_length_bp", "App manifest")? as usize;
    if expected_total != q4_lengths.values().sum::<usize>() {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "App manifest q4_length_bp differs from chromosome lengths",
        );
    }

    // The catalog persistence layer intentionally keeps the Server-shaped
    // tables, but App packages do not carry those trace tables.  Empty tables
    // make the absence explicit without retaining any Server audit payload.
    for (relpath, header, _, _) in TABLE_SPECS {
        tables
            .entry(*relpath)
            .or_insert_with(|| TsvTable { rows: Vec::new() });
        let _ = header;
    }
    Ok(ValidatedGrtPackage {
        tables,
        events: Vec::new(),
        final_path,
        q0_artifact_sha256: String::new(),
        q4_artifact_sha256: q4_artifact_sha256.to_string(),
    })
}
