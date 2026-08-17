use super::*;

#[cfg(test)]
pub(crate) fn validate_grt_package(bundle_root: &Path) -> Result<ValidatedGrtPackage> {
    validate_grt_package_with_progress(bundle_root, &mut |_, _| {})
}

pub(crate) fn validate_grt_package_with_progress<P>(
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
        "validate_grt_required_files",
        "checking required GRT package files",
    );
    for relpath in REQUIRED_FILES {
        required_bundle_file(bundle_root, relpath, relpath)?;
    }

    on_progress(
        "validate_grt_metadata_tables",
        "parsing GRT metadata tables",
    );
    let mut tables = HashMap::new();
    for (relpath, header, minimum, maximum) in TABLE_SPECS {
        tables.insert(
            *relpath,
            read_tsv(bundle_root, relpath, header, *minimum, *maximum)?,
        );
    }

    let package = one_row(&tables, "metadata/package.tsv")?;
    if field(package, "workflow")? != GRT_WORKFLOW
        || field(package, "schema_version")? != GRT_SCHEMA_VERSION
        || field(package, "final_path_schema_version")? != GRT_FINAL_PATH_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "expected gpm_grt_precomputed_v2 schema 2 / Final Path schema 1",
        );
    }
    if !parse_bool(
        field(package, "grt_precompute_enabled")?,
        "package.grt_precompute_enabled",
    )? || !parse_bool(field(package, "recipe_locked")?, "package.recipe_locked")?
    {
        return grt_err(
            "INVALID_VALUE",
            "GRT precompute and locked recipe must both be true",
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
            "GRT package requires partitioned, preassigned chromosome data",
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

    on_progress(
        "validate_grt_source_fastas",
        "validating reference and dataset FASTA/FAI",
    );
    let dataset_rows = table(&tables, "metadata/datasets.tsv")?;
    let mut dataset_names = HashSet::new();
    for row in &dataset_rows.rows {
        let name = nonempty(row, "dataset_name", "dataset")?;
        if !dataset_names.insert(name.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate dataset_name={name}"));
        }
        let fasta_path = required_bundle_file(
            bundle_root,
            field(row, "fasta_relpath")?,
            &format!("dataset {name} FASTA"),
        )?;
        let fai_path = required_bundle_file(
            bundle_root,
            field(row, "fai_relpath")?,
            &format!("dataset {name} FAI"),
        )?;
        validate_fasta_fai_pair(&fasta_path, &fai_path, &format!("dataset {name}"))?;
        parse_bool(
            field(row, "self_alignment_available")?,
            &format!("dataset {name}.self_alignment_available"),
        )?;
    }

    let reference = one_row(&tables, "metadata/reference.tsv")?;
    let reference_fasta = required_bundle_file(
        bundle_root,
        field(reference, "fasta_relpath")?,
        "reference FASTA",
    )?;
    let reference_fai = required_bundle_file(
        bundle_root,
        field(reference, "fai_relpath")?,
        "reference FAI",
    )?;
    let reference_records = read_fasta(&reference_fasta, "reference FASTA", false)?;
    validate_fasta_fai_records(&reference_records, &reference_fai, "reference")?;
    let sources = source_catalog(
        bundle_root,
        table(&tables, "metadata/source_seq_locator.tsv")?,
    )?;

    let mut assignments: HashMap<(String, String), HashSet<String>> = HashMap::new();
    let mut assignment_baselines: HashMap<(String, String, String), (String, i64)> = HashMap::new();
    let mut assignment_ids = HashSet::new();
    for row in &table(&tables, "metadata/chr_assignments.tsv")?.rows {
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "seq_name")?.to_string(),
        );
        let chromosome = nonempty(row, "assigned_chr_name", "chr assignment chromosome")?;
        let Some(sequence) = sources.get(&key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!(
                    "chr assignment references unknown source {}:{}",
                    key.0, key.1
                ),
            );
        };
        if !reference_records.contains_key(chromosome) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown chromosome {chromosome}"),
            );
        }
        if !assignment_ids.insert((key.clone(), chromosome.to_string())) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate chr assignment {}:{}:{chromosome}", key.0, key.1),
            );
        }
        let source_orientation = orientation(
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
            != sequence.len()
        {
            return grt_err(
                "COUNT_MISMATCH",
                format!(
                    "chr assignment source length differs for {}:{}",
                    key.0, key.1
                ),
            );
        }
        let support = parse_positive_i64(field(row, "support_bp")?, "chr assignment support_bp")?;
        if support as usize > sequence.len() {
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
        let anchor_start = parse_i64(field(row, "anchor_start")?, "chr assignment anchor_start")?;
        assignment_baselines.insert(
            (key.0.clone(), key.1.clone(), chromosome.to_string()),
            (source_orientation.to_string(), anchor_start),
        );
        assignments
            .entry(key)
            .or_default()
            .insert(chromosome.to_string());
    }

    on_progress("validate_grt_recipe", "validating the locked GRT recipe");
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
    if field(recipe, "q0_relpath")? != "grt/q/q0.fa"
        || field(recipe, "final_q_relpath")? != "grt/q/q4.fa"
    {
        return grt_err(
            "INVALID_VALUE",
            "recipe q paths must identify q0.fa and q4.fa",
        );
    }

    let mut recipe_datasets = support_datasets.iter().cloned().collect::<HashSet<_>>();
    recipe_datasets.insert(primary_dataset.to_string());
    let mut role_keys = HashSet::new();
    for row in &table(&tables, "metadata/grt_contig_roles.tsv")?.rows {
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("contig role references unknown source {}:{}", key.0, key.1),
            );
        }
        if !role_keys.insert(key) {
            return grt_err("DUPLICATE_ID", "duplicate GRT contig role");
        }
        for name in ["q_eligible", "donor_eligible", "tel_donor_eligible"] {
            parse_bool(field(row, name)?, &format!("contig role {name}"))?;
        }
    }
    let expected_role_keys = sources
        .keys()
        .filter(|(dataset, _)| recipe_datasets.contains(dataset))
        .cloned()
        .collect::<HashSet<_>>();
    if role_keys != expected_role_keys {
        return grt_err(
            "BROKEN_REFERENCE",
            "contig roles must cover the locked recipe source catalog exactly once",
        );
    }

    on_progress(
        "validate_grt_q_artifacts",
        "validating q0-q4 artifacts and segment reconstruction",
    );
    let mut q_records = HashMap::<String, BTreeMap<String, String>>::new();
    let mut q_artifact_hashes = HashMap::<String, String>::new();
    for q_version in ["q0", "q0r1", "q0f", "q1", "q2", "q3", "q4"] {
        let relpath = format!("grt/q/{q_version}.fa");
        let path = required_bundle_file(bundle_root, &relpath, &relpath)?;
        q_artifact_hashes.insert(q_version.to_string(), sha256_file(&path)?);
        q_records.insert(q_version.to_string(), read_fasta(&path, &relpath, false)?);
    }

    let mut q_segment_ids = HashSet::new();
    let mut q_segment_evidence = HashMap::<String, Vec<String>>::new();
    let mut q_segments_by_record =
        HashMap::<(String, String), Vec<(i64, i64, String, String)>>::new();
    for row in &table(&tables, "metadata/grt_q_segments.tsv")?.rows {
        let q_version = nonempty(row, "q_version", "q segment q_version")?;
        let chr_name = nonempty(row, "chr", "q segment chr")?;
        let segment_id = nonempty(row, "segment_id", "q segment id")?;
        if !q_records.contains_key(q_version) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segment {segment_id} references unknown q version"),
            );
        }
        if !q_segment_ids.insert(segment_id.to_string()) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate q segment_id={segment_id}"),
            );
        }
        let (q_start, q_end) = interval(
            row,
            "q_start",
            "q_end",
            &format!("q segment {segment_id}.q"),
        )?;
        let evidence_ids = json_string_list(
            field(row, "evidence_ids_json")?,
            &format!("q segment {segment_id}.evidence"),
        )?;
        let sequence = match field(row, "segment_kind")? {
            "gap" => {
                if [
                    "dataset_name",
                    "contig_name",
                    "source_start",
                    "source_end",
                    "orientation",
                    "source_card_key",
                ]
                .iter()
                .any(|key| !field(row, key).unwrap_or("").is_empty())
                    || !evidence_ids.is_empty()
                {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("q gap segment {segment_id} cannot carry source/evidence"),
                    );
                }
                "N".repeat((q_end - q_start + 1) as usize)
            }
            "source" => {
                let key = (
                    field(row, "dataset_name")?.to_string(),
                    field(row, "contig_name")?.to_string(),
                );
                let Some(source) = sources.get(&key) else {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("q segment {segment_id} references unknown source"),
                    );
                };
                let (start, end) = interval(
                    row,
                    "source_start",
                    "source_end",
                    &format!("q segment {segment_id}.source"),
                )?;
                if end as usize > source.len() || q_end - q_start != end - start {
                    return grt_err(
                        "INVALID_COORDINATE",
                        format!("q segment {segment_id} q/source lengths differ"),
                    );
                }
                let orientation = orientation(
                    field(row, "orientation")?,
                    &format!("q segment {segment_id}"),
                )?;
                if field(row, "source_card_key")?.is_empty() || evidence_ids.is_empty() {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("q segment {segment_id} lacks source card/evidence"),
                    );
                }
                if q_version == "q0" {
                    if !assignments
                        .get(&key)
                        .is_some_and(|chrs| chrs.contains(chr_name))
                    {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} source is not assigned to {chr_name}"),
                        );
                    }
                    let Some(baseline) = assignment_baselines.get(&(
                        key.0.clone(),
                        key.1.clone(),
                        chr_name.to_string(),
                    )) else {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} lacks an assignment baseline"),
                        );
                    };
                    if orientation != baseline.0.as_str() {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!(
                                "q0 segment {segment_id} orientation disagrees with chr_assignments.tsv"
                            ),
                        );
                    }
                    let expected = format!("{}:{}:{chr_name}:normal", key.0, key.1);
                    if field(row, "source_card_key")? != expected {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} has non-canonical source card key"),
                        );
                    }
                }
                orient_sequence(&source[(start - 1) as usize..end as usize], orientation)
            }
            other => {
                return grt_err(
                    "INVALID_VALUE",
                    format!("q segment {segment_id} has invalid segment_kind={other}"),
                );
            }
        };
        q_segment_evidence.insert(segment_id.to_string(), evidence_ids);
        q_segments_by_record
            .entry((q_version.to_string(), chr_name.to_string()))
            .or_default()
            .push((q_start, q_end, sequence, segment_id.to_string()));
    }
    for ((q_version, chr_name), segments) in &mut q_segments_by_record {
        let Some(expected) = q_records
            .get(q_version)
            .and_then(|records| records.get(chr_name))
        else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segments reference missing {q_version}:{chr_name}"),
            );
        };
        segments.sort_by_key(|value| value.0);
        let mut next = 1_i64;
        let mut rebuilt = String::new();
        for (start, end, sequence, segment_id) in segments {
            if *start != next {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("q segment {segment_id} is not contiguous"),
                );
            }
            next = *end + 1;
            rebuilt.push_str(sequence);
        }
        if &rebuilt != expected {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("q segments do not reconstruct {q_version}:{chr_name}"),
            );
        }
    }
    let q0_segment_records = q_segments_by_record
        .keys()
        .filter(|(version, _)| version == "q0")
        .map(|(_, chr)| chr.clone())
        .collect::<HashSet<_>>();
    let q0_record_names = q_records["q0"].keys().cloned().collect::<HashSet<_>>();
    if q0_segment_records != q0_record_names {
        return grt_err(
            "BROKEN_REFERENCE",
            "q0 segment mapping does not cover every q0 record",
        );
    }

    on_progress(
        "validate_grt_donor_artifacts",
        "validating D0/Dtel donor artifacts and member manifests",
    );
    let donor_sets_table = table(&tables, "metadata/grt_donor_sets.tsv")?;
    let mut donor_sets = HashMap::<String, &TsvRow>::new();
    let mut donor_kind_count = HashMap::<String, usize>::new();
    let mut donor_fastas = HashMap::<String, BTreeMap<String, String>>::new();
    for row in &donor_sets_table.rows {
        let id = nonempty(row, "donor_set_id", "donor set id")?;
        if donor_sets.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate donor_set_id={id}"));
        }
        let kind = field(row, "donor_kind")?;
        if !matches!(kind, "ordinary" | "telomere") {
            return grt_err("INVALID_VALUE", format!("unknown donor_kind={kind}"));
        }
        *donor_kind_count.entry(kind.to_string()).or_default() += 1;
        parse_nonnegative_i64(
            field(row, "member_count")?,
            &format!("donor set {id}.member_count"),
        )?;
        let fasta_path = validate_artifact(
            bundle_root,
            field(row, "fasta_relpath")?,
            field(row, "fasta_sha256")?,
            &format!("donor set {id} FASTA"),
        )?;
        donor_fastas.insert(
            id.to_string(),
            read_fasta(&fasta_path, &format!("donor set {id} FASTA"), true)?,
        );
        required_bundle_file(
            bundle_root,
            field(row, "manifest_relpath")?,
            &format!("donor set {id} manifest"),
        )?;
    }
    if donor_kind_count.get("ordinary") != Some(&1)
        || donor_kind_count.get("telomere") != Some(&1)
        || donor_sets.len() != 2
    {
        return grt_err(
            "INVALID_VALUE",
            "contract requires exactly one ordinary and one telomere donor set",
        );
    }
    for (field_name, kind) in [
        ("donor_set_id", "ordinary"),
        ("tel_donor_set_id", "telomere"),
    ] {
        let id = field(recipe, field_name)?;
        if donor_sets
            .get(id)
            .and_then(|row| row.get("donor_kind"))
            .map(String::as_str)
            != Some(kind)
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("recipe {field_name} must reference the {kind} donor set"),
            );
        }
    }

    let mut members = HashMap::<(String, String), &TsvRow>::new();
    let mut member_rows_by_set = HashMap::<String, Vec<&TsvRow>>::new();
    for row in &table(&tables, "metadata/grt_donor_members.tsv")?.rows {
        let set_id = field(row, "donor_set_id")?.to_string();
        let member_id = nonempty(row, "member_id", "donor member id")?.to_string();
        if !donor_sets.contains_key(&set_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("donor member references unknown donor_set_id={set_id}"),
            );
        }
        if members
            .insert((set_id.clone(), member_id.clone()), row)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate donor member {set_id}:{member_id}"),
            );
        }
        let source_key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        let Some(source) = sources.get(&source_key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!(
                    "donor member references unknown source {}:{}",
                    source_key.0, source_key.1
                ),
            );
        };
        let (start, end) = interval(
            row,
            "source_start",
            "source_end",
            &format!("donor member {member_id}"),
        )?;
        if end as usize > source.len() {
            return grt_err(
                "INVALID_COORDINATE",
                format!("donor member {member_id} exceeds source length"),
            );
        }
        let orient = orientation(
            field(row, "orientation")?,
            &format!("donor member {member_id}"),
        )?;
        let sequence = orient_sequence(&source[(start - 1) as usize..end as usize], orient);
        let sequence_sha = field(row, "sequence_sha256")?;
        validate_sha256(
            sequence_sha,
            &format!("donor member {member_id}.sequence_sha256"),
        )?;
        if sha256_bytes(sequence.as_bytes()) != sequence_sha {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("donor member {member_id} sequence hash differs from source slice"),
            );
        }
        let fasta_name = field(row, "fasta_record_name")?;
        if donor_fastas
            .get(&set_id)
            .and_then(|records| records.get(fasta_name))
            != Some(&sequence)
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("donor member {member_id} FASTA differs from source slice"),
            );
        }
        member_rows_by_set.entry(set_id).or_default().push(row);
    }
    for (set_id, donor_set) in &donor_sets {
        let expected =
            parse_nonnegative_i64(field(donor_set, "member_count")?, "donor member count")?
                as usize;
        let rows = member_rows_by_set.get(set_id).cloned().unwrap_or_default();
        if rows.len() != expected || donor_fastas.get(set_id).map(BTreeMap::len) != Some(expected) {
            return grt_err(
                "COUNT_MISMATCH",
                format!("donor set {set_id} member_count differs from registry/FASTA"),
            );
        }
        let manifest = read_tsv(
            bundle_root,
            field(donor_set, "manifest_relpath")?,
            DONOR_MEMBERS_HEADER,
            0,
            None,
        )?;
        if manifest.rows != rows.into_iter().cloned().collect::<Vec<_>>() {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("donor set {set_id} manifest differs from member registry"),
            );
        }
    }

    on_progress(
        "validate_grt_evidence",
        "validating evidence, usage, and event links",
    );
    let evidence_table = table(&tables, "metadata/grt_evidence_registry.tsv")?;
    let mut evidence = HashMap::<String, &TsvRow>::new();
    for row in &evidence_table.rows {
        let id = nonempty(row, "evidence_id", "evidence id")?;
        if evidence.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate evidence_id={id}"));
        }
        enum_value(
            field(row, "stage")?,
            &[
                "assignment",
                "step1_round1",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
                "candidate_validation",
                "display_pairwise",
            ],
            &format!("evidence {id}.stage"),
        )?;
        enum_value(
            field(row, "status")?,
            &[
                "candidate",
                "accepted",
                "superseded",
                "rejected",
                "conflicted",
                "background",
            ],
            &format!("evidence {id}.status"),
        )?;
        enum_value(
            field(row, "coordinate_system")?,
            &[
                "paf_0_based_half_open",
                "mummer_1_based_closed",
                "app_1_based_closed",
            ],
            &format!("evidence {id}.coordinate_system"),
        )?;
        enum_value(
            field(row, "projection_status")?,
            &["native", "projected"],
            &format!("evidence {id}.projection_status"),
        )?;
        parse_json_object(
            field(row, "parameters_json")?,
            &format!("evidence {id}.parameters_json"),
        )?;
        let source_values = [
            field(row, "source_dataset")?,
            field(row, "source_contig")?,
            field(row, "source_start")?,
            field(row, "source_end")?,
        ];
        if source_values.iter().any(|value| !value.is_empty()) {
            if source_values.iter().any(|value| value.is_empty()) {
                return grt_err(
                    "INVALID_VALUE",
                    format!("evidence {id} has partial source identity"),
                );
            }
            let key = (source_values[0].to_string(), source_values[1].to_string());
            let Some(source) = sources.get(&key) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("evidence {id} references unknown source"),
                );
            };
            let (_start, end) = interval(
                row,
                "source_start",
                "source_end",
                &format!("evidence {id}.source"),
            )?;
            if end as usize > source.len() {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("evidence {id} source exceeds source length"),
                );
            }
            orientation(field(row, "orientation")?, &format!("evidence {id}"))?;
        }
        let target_start = field(row, "target_start")?;
        let target_end = field(row, "target_end")?;
        if !target_start.is_empty() || !target_end.is_empty() {
            if target_start.is_empty()
                || target_end.is_empty()
                || field(row, "target_chr")?.is_empty()
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("evidence {id} has partial target interval"),
                );
            }
            interval(
                row,
                "target_start",
                "target_end",
                &format!("evidence {id}.target"),
            )?;
        }
        for (path_field, hash_field) in [
            ("query_artifact_relpath", "query_sha256"),
            ("target_artifact_relpath", "target_sha256"),
        ] {
            let relpath = field(row, path_field)?;
            let hash = field(row, hash_field)?;
            if !relpath.is_empty() || !hash.is_empty() {
                if relpath.is_empty() || hash.is_empty() {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("evidence {id} has partial artifact identity"),
                    );
                }
                validate_artifact(
                    bundle_root,
                    relpath,
                    hash,
                    &format!("evidence {id}.{path_field}"),
                )?;
            }
        }
        validate_artifact(
            bundle_root,
            field(row, "raw_artifact_relpath")?,
            field(row, "raw_artifact_sha256")?,
            &format!("evidence {id}.raw_artifact"),
        )?;
        let q_version = field(row, "q_version")?;
        if !q_version.is_empty() {
            if q_artifact_hashes.get(q_version).map(String::as_str)
                != Some(field(row, "q_source_sha256")?)
            {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("evidence {id} q source hash mismatch"),
                );
            }
        } else if !field(row, "q_source_sha256")?.is_empty() {
            return grt_err(
                "INVALID_VALUE",
                format!("evidence {id} has q hash without q_version"),
            );
        }
        let donor_set_id = field(row, "donor_set_id")?;
        if !donor_set_id.is_empty() {
            let Some(donor_set) = donor_sets.get(donor_set_id) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("evidence {id} references unknown donor set"),
                );
            };
            if field(row, "target_sha256")? != field(donor_set, "fasta_sha256")? {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("evidence {id} target hash differs from donor set"),
                );
            }
        }
    }
    for (segment_id, ids) in &q_segment_evidence {
        if ids.iter().any(|id| !evidence.contains_key(id)) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segment {segment_id} references unknown evidence"),
            );
        }
    }

    let usage_table = table(&tables, "metadata/grt_donor_usage.tsv")?;
    let mut usage = HashMap::<String, &TsvRow>::new();
    for row in &usage_table.rows {
        let id = nonempty(row, "usage_id", "usage id")?;
        if usage.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate usage_id={id}"));
        }
        let member_key = (
            field(row, "donor_set_id")?.to_string(),
            field(row, "member_id")?.to_string(),
        );
        let Some(member) = members.get(&member_key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} references unknown donor member"),
            );
        };
        enum_value(
            field(row, "status")?,
            &[
                "available",
                "candidate",
                "accepted",
                "consumed",
                "superseded",
                "rejected",
                "conflicted",
            ],
            &format!("usage {id}.status"),
        )?;
        enum_value(
            field(row, "stage")?,
            &[
                "step1_round1",
                "step1_filter",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
            ],
            &format!("usage {id}.stage"),
        )?;
        let (start, end) = interval(
            row,
            "source_start",
            "source_end",
            &format!("usage {id}.source"),
        )?;
        if field(row, "source_dataset")? != field(member, "dataset_name")?
            || field(row, "source_contig")? != field(member, "contig_name")?
            || start < parse_positive_i64(field(member, "source_start")?, "member start")?
            || end > parse_positive_i64(field(member, "source_end")?, "member end")?
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} source differs from donor member"),
            );
        }
        if matches!(field(row, "status")?, "accepted" | "consumed")
            && field(row, "event_id")?.is_empty()
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} accepted/consumed row lacks event"),
            );
        }
    }

    let events = read_jsonl(bundle_root, "metadata/grt_events.jsonl")?;
    let mut event_index = HashMap::<String, &Value>::new();
    for event in &events {
        let object = event
            .as_object()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "GRT event must be an object"))?;
        for field_name in [
            "run_id",
            "event_id",
            "stage",
            "chr",
            "object_id",
            "action",
            "status",
            "reason",
            "q_before",
            "q_after",
            "source",
            "evidence_ids",
            "usage_ids",
            "source_card_key",
            "final_path_segment_id",
        ] {
            if !object.contains_key(field_name) {
                return grt_err(
                    "INVALID_JSON",
                    format!("event is missing required field {field_name}"),
                );
            }
        }
        let id = json_nonempty_str(object, "event_id", "event")?;
        if event_index.insert(id.to_string(), event).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate event_id={id}"));
        }
        enum_value(
            json_str(object, "stage", id)?,
            &[
                "step1_round1",
                "step1_filter",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
            ],
            &format!("event {id}.stage"),
        )?;
        enum_value(
            json_str(object, "status", id)?,
            &[
                "accepted",
                "superseded",
                "rejected",
                "conflicted",
                "unresolved",
            ],
            &format!("event {id}.status"),
        )?;
        enum_value(
            json_str(object, "action", id)?,
            &[
                "fill",
                "filter_component",
                "patch",
                "delete",
                "replace",
                "correct_boundary",
                "refill",
                "extend_telomere",
            ],
            &format!("event {id}.action"),
        )?;
        for link_field in ["evidence_ids", "usage_ids"] {
            let ids = json_value_string_list(
                object.get(link_field).unwrap(),
                &format!("event {id}.{link_field}"),
            )?;
            let known = if link_field == "evidence_ids" {
                ids.iter().all(|item| evidence.contains_key(item))
            } else {
                ids.iter().all(|item| usage.contains_key(item))
            };
            if !known {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {id} references unknown {link_field}"),
                );
            }
        }
        for q_field in ["q_before", "q_after"] {
            let q = object
                .get(q_field)
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("event {id}.{q_field} has invalid shape"),
                    )
                })?;
            let version = json_nonempty_str(q, "version", &format!("event {id}.{q_field}"))?;
            let start = json_positive_i64(q, "start", &format!("event {id}.{q_field}"))?;
            let end = json_positive_i64(q, "end", &format!("event {id}.{q_field}"))?;
            if start > end {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("event {id}.{q_field} has reversed interval"),
                );
            }
            let hash = json_nonempty_str(q, "sha256", &format!("event {id}.{q_field}"))?;
            validate_sha256(hash, &format!("event {id}.{q_field}.sha256"))?;
            if q_artifact_hashes.get(version).map(String::as_str) != Some(hash) {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("event {id}.{q_field} q hash mismatch"),
                );
            }
            let chr_name = json_str(object, "chr", id)?;
            if q_records
                .get(version)
                .and_then(|records| records.get(chr_name))
                .map(String::len)
                .is_none_or(|length| end as usize > length)
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("event {id}.{q_field} exceeds q chromosome"),
                );
            }
        }
        if let Some(source) = object.get("source").and_then(Value::as_object) {
            if !source.is_empty() {
                let key = (
                    json_nonempty_str(source, "dataset", id)?.to_string(),
                    json_nonempty_str(source, "contig", id)?.to_string(),
                );
                let Some(sequence) = sources.get(&key) else {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("event {id} references unknown source"),
                    );
                };
                let start = json_positive_i64(source, "start", id)?;
                let end = json_positive_i64(source, "end", id)?;
                if start > end || end as usize > sequence.len() {
                    return grt_err(
                        "INVALID_COORDINATE",
                        format!("event {id} has invalid source interval"),
                    );
                }
                orientation(
                    json_str(source, "orientation", id)?,
                    &format!("event {id}.source"),
                )?;
                enum_value(
                    json_str(source, "original_assignment", id)?,
                    &["assigned", "unplaced", "cross_chr"],
                    &format!("event {id}.source.original_assignment"),
                )?;
            }
        } else if object.get("source") != Some(&Value::Null) {
            return grt_err(
                "INVALID_JSON",
                format!("event {id}.source has invalid shape"),
            );
        }
    }
    for (usage_id, row) in &usage {
        let event_id = field(row, "event_id")?;
        if !event_id.is_empty() && !event_index.contains_key(event_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {usage_id} references unknown event {event_id}"),
            );
        }
    }

    on_progress(
        "validate_grt_final_path",
        "rebuilding and validating the Final Path",
    );
    validate_stage_status(
        bundle_root,
        table(&tables, "metadata/grt_stage_status.tsv")?,
        &q_artifact_hashes,
        &donor_sets,
    )?;
    validate_tool_versions(table(&tables, "metadata/grt_tool_versions.tsv")?)?;

    let final_path = read_json(bundle_root, "metadata/grt_final_path.json")?;
    let final_object = final_path
        .as_object()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", "grt_final_path.json must contain an object"))?;
    if json_str(final_object, "workflow", "Final Path")? != GRT_WORKFLOW
        || json_str(final_object, "schema_version", "Final Path")? != GRT_FINAL_PATH_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "grt_final_path.json has unsupported workflow/schema",
        );
    }
    if json_str(final_object, "q4_relpath", "Final Path")? != field(recipe, "final_q_relpath")? {
        return grt_err(
            "BROKEN_REFERENCE",
            "Final Path q4_relpath differs from recipe",
        );
    }
    let chromosomes = final_object
        .get("chromosomes")
        .and_then(Value::as_array)
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "Final Path chromosomes must be a non-empty array",
            )
        })?;
    let mut final_chr_names = HashSet::new();
    let mut final_segments = HashMap::<String, (&Value, String)>::new();
    for chromosome in chromosomes {
        let chr = chromosome
            .as_object()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path chromosome must be an object"))?;
        let chr_name = json_nonempty_str(chr, "chr", "Final Path chromosome")?;
        if !final_chr_names.insert(chr_name.to_string()) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate Final Path chromosome {chr_name}"),
            );
        }
        let expected_q4 = q_records["q4"].get(chr_name).ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("Final Path references unknown q4 chromosome {chr_name}"),
            )
        })?;
        if json_positive_i64(chr, "q4_length", chr_name)? as usize != expected_q4.len() {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("Final Path {chr_name} q4 length mismatch"),
            );
        }
        if json_nonempty_str(chr, "q4_sha256", chr_name)? != sha256_bytes(expected_q4.as_bytes()) {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("Final Path {chr_name} q4 sequence hash mismatch"),
            );
        }
        let segments = chr
            .get("segments")
            .and_then(Value::as_array)
            .filter(|rows| !rows.is_empty())
            .ok_or_else(|| {
                grt_anyhow(
                    "INVALID_JSON",
                    format!("Final Path {chr_name}.segments must be non-empty"),
                )
            })?;
        let mut rebuilt = String::new();
        for segment in segments {
            let segment_object = segment.as_object().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "Final Path segment must be an object")
            })?;
            let segment_id = json_nonempty_str(segment_object, "segment_id", "Final Path segment")?;
            if final_segments
                .insert(segment_id.to_string(), (segment, chr_name.to_string()))
                .is_some()
            {
                return grt_err(
                    "DUPLICATE_ID",
                    format!("duplicate Final Path segment_id={segment_id}"),
                );
            }
            let kind = json_str(segment_object, "kind", segment_id)?;
            enum_value(
                kind,
                &["source", "patch", "correction", "telomere", "gap"],
                &format!("segment {segment_id}.kind"),
            )?;
            let length = json_positive_i64(segment_object, "length", segment_id)? as usize;
            let evidence_ids = json_value_string_list(
                segment_object.get("evidence_ids").ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("segment {segment_id} lacks evidence_ids"),
                    )
                })?,
                &format!("segment {segment_id}.evidence_ids"),
            )?;
            if evidence_ids.iter().any(|id| !evidence.contains_key(id)) {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("segment {segment_id} references unknown evidence"),
                );
            }
            if kind == "gap" {
                if segment_object
                    .get("source")
                    .is_some_and(|value| !value.is_null())
                    || segment_object
                        .get("event_id")
                        .is_some_and(|value| !value.is_null())
                {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("gap segment {segment_id} cannot have source/event"),
                    );
                }
                rebuilt.push_str(&"N".repeat(length));
                continue;
            }
            let orient = orientation(
                json_str(segment_object, "orientation", segment_id)?,
                &format!("segment {segment_id}"),
            )?;
            let source = segment_object
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("segment {segment_id}.source has invalid shape"),
                    )
                })?;
            let key = (
                json_nonempty_str(source, "dataset", segment_id)?.to_string(),
                json_nonempty_str(source, "contig", segment_id)?.to_string(),
            );
            let Some(source_sequence) = sources.get(&key) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("segment {segment_id} references unknown source"),
                );
            };
            let start = json_positive_i64(source, "start", segment_id)?;
            let end = json_positive_i64(source, "end", segment_id)?;
            if start > end
                || end as usize > source_sequence.len()
                || end - start + 1 != length as i64
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("segment {segment_id} source interval does not match length"),
                );
            }
            if orientation(
                json_str(source, "orientation", segment_id)?,
                &format!("segment {segment_id}.source"),
            )? != orient
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("segment {segment_id} orientation differs from source"),
                );
            }
            let event_id = segment_object
                .get("event_id")
                .and_then(Value::as_str)
                .unwrap_or("");
            if !event_id.is_empty() {
                let event = event_index.get(event_id).ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("segment {segment_id} references unknown event"),
                    )
                })?;
                if event.get("status").and_then(Value::as_str) != Some("accepted") {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("segment {segment_id} references non-accepted event"),
                    );
                }
            } else if matches!(kind, "patch" | "correction" | "telomere") {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("GRT segment {segment_id} lacks accepted event"),
                );
            }
            rebuilt.push_str(&orient_sequence(
                &source_sequence[(start - 1) as usize..end as usize],
                orient,
            ));
        }
        if &rebuilt != expected_q4 {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("Final Path segments do not reconstruct q4 chromosome {chr_name}"),
            );
        }
    }
    if final_chr_names != q_records["q4"].keys().cloned().collect::<HashSet<_>>() {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "Final Path chromosome set differs from q4 FASTA",
        );
    }

    for (event_id, event) in &event_index {
        let status = event.get("status").and_then(Value::as_str).unwrap_or("");
        let action = event.get("action").and_then(Value::as_str).unwrap_or("");
        let segment_id = event
            .get("final_path_segment_id")
            .and_then(Value::as_str)
            .unwrap_or("");
        let path_producing = status == "accepted"
            && matches!(
                action,
                "fill" | "patch" | "replace" | "correct_boundary" | "refill" | "extend_telomere"
            );
        if path_producing && segment_id.is_empty() {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("accepted path-producing event {event_id} lacks Final Path segment"),
            );
        }
        if !segment_id.is_empty() {
            let Some((segment, _)) = final_segments.get(segment_id) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {event_id} references unknown Final Path segment"),
                );
            };
            if segment.get("event_id").and_then(Value::as_str) != Some(event_id) {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {event_id} and Final Path segment are not bidirectional"),
                );
            }
        }
    }
    for (usage_id, row) in &usage {
        let segment_id = field(row, "final_path_segment_id")?;
        if !segment_id.is_empty() && !final_segments.contains_key(segment_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {usage_id} references unknown Final Path segment"),
            );
        }
    }

    on_progress(
        "validate_grt_trace_integrity",
        "validating source-card trace integrity",
    );
    validate_source_cards(
        table(&tables, "metadata/grt_used_contigs.tsv")?,
        &sources,
        &assignment_baselines,
        &evidence,
        &event_index,
        &final_segments,
    )?;
    validate_gap_attempts(
        table(&tables, "metadata/grt_gap_attempts.tsv")?,
        &event_index,
    )?;

    Ok(ValidatedGrtPackage {
        tables,
        events,
        final_path,
        q0_artifact_sha256: q_artifact_hashes.remove("q0").unwrap(),
        q4_artifact_sha256: q_artifact_hashes.remove("q4").unwrap(),
    })
}
