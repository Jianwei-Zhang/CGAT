use super::*;

pub(super) fn read_fai_lengths(path: &Path, label: &str) -> Result<BTreeMap<String, usize>> {
    let text = fs::read_to_string(path)
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{label} FAI is not UTF-8: {error}")))?;
    let mut lengths = BTreeMap::new();
    for (offset, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let columns = line.trim_end_matches('\r').split('\t').collect::<Vec<_>>();
        if columns.len() < 2 || columns[0].is_empty() {
            return grt_err(
                "INVALID_TSV",
                format!("{label} FAI row {} is invalid", offset + 1),
            );
        }
        let length = columns[1].parse::<usize>().map_err(|_| {
            grt_anyhow(
                "INVALID_VALUE",
                format!("{label} FAI row {} has invalid length", offset + 1),
            )
        })?;
        if length == 0 || lengths.insert(columns[0].to_string(), length).is_some() {
            return grt_err(
                "DUPLICATE_ID",
                format!("{label} FAI has empty or duplicate sequence {}", columns[0]),
            );
        }
    }
    if lengths.is_empty() {
        return grt_err("INVALID_TSV", format!("{label} FAI contains no records"));
    }
    Ok(lengths)
}

pub(super) fn source_length_catalog(
    _bundle_root: &Path,
    table: &TsvTable,
    dataset_fai: &HashMap<String, BTreeMap<String, usize>>,
) -> Result<HashMap<(String, String), usize>> {
    let mut sources = HashMap::new();
    for row in &table.rows {
        let dataset = nonempty(row, "dataset_name", "source locator dataset")?.to_string();
        let contig = nonempty(row, "seq_name", "source locator sequence")?.to_string();
        let relpath = field(row, "fasta_relpath")?;
        validate_relpath(relpath, "source locator fasta_relpath")?;
        let records = if let Some(records) = dataset_fai.get(&dataset) {
            records
        } else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source locator references unknown dataset {dataset}"),
            );
        };
        let length = records.get(&contig).copied().ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("source locator {dataset}:{contig} is absent from its dataset FAI"),
            )
        })?;
        if sources
            .insert((dataset.clone(), contig.clone()), length)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate source locator for {dataset}:{contig}"),
            );
        }
    }
    Ok(sources)
}

pub(super) fn validate_app_source_cards(
    table: &TsvTable,
    sources: &HashMap<(String, String), usize>,
    assignment_baselines: &HashMap<(String, String, String), (String, i64)>,
    reference_records: &BTreeMap<String, usize>,
) -> Result<()> {
    let mut ids = HashSet::new();
    for row in &table.rows {
        let card = nonempty(row, "source_card_key", "source card key")?;
        if !ids.insert(card.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate source card {card}"));
        }
        let dataset = field(row, "dataset_name")?;
        let contig = field(row, "contig_name")?;
        let target_chr = nonempty(row, "target_chr", "source card target chromosome")?;
        if !reference_records.contains_key(target_chr) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown chromosome {target_chr}"),
            );
        }
        let key = (dataset.to_string(), contig.to_string());
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown source"),
            );
        }
        enum_value(
            field(row, "original_assignment")?,
            &["assigned", "unplaced", "cross_chr"],
            &format!("source card {card}.original_assignment"),
        )?;
        let placement = field(row, "placement_mode")?;
        enum_value(
            placement,
            &["normal", "grt_promoted", "cross_chr_grt_usage"],
            &format!("source card {card}.placement_mode"),
        )?;
        enum_value(
            field(row, "ref_alignment_status")?,
            &["hit", "weak_hit", "multi_hit", "other_chr_only", "no_hit"],
            &format!("source card {card}.ref_alignment_status"),
        )?;
        orientation(field(row, "orientation")?, &format!("source card {card}"))?;
        let anchor = parse_positive_i64(
            field(row, "anchor_start")?,
            &format!("source card {card}.anchor_start"),
        )?;
        let expected = format!("{}:{}:{}:{}", dataset, contig, target_chr, placement);
        if card != expected {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} is non-canonical"),
            );
        }
        if placement == "normal" {
            let baseline_key = (
                dataset.to_string(),
                contig.to_string(),
                target_chr.to_string(),
            );
            let Some((baseline_orientation, baseline_anchor)) =
                assignment_baselines.get(&baseline_key)
            else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} lacks assignment baseline"),
                );
            };
            if field(row, "orientation")? != baseline_orientation || anchor != *baseline_anchor {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} disagrees with assignment baseline"),
                );
            }
        }
        for trace_field in [
            "ref_evidence_ids_json",
            "accepted_event_ids_json",
            "final_path_segment_ids_json",
            "pairwise_evidence_ids_json",
        ] {
            let value = field(row, trace_field)?;
            if !value.is_empty() {
                let ids = json_string_list(value, &format!("source card {card}.{trace_field}"))?;
                if !ids.is_empty() {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("App source card {card} retains Server trace links"),
                    );
                }
            }
        }
    }
    Ok(())
}

pub(super) fn validate_app_final_path(
    bundle_root: &Path,
    final_path: &Value,
    reference_records: &BTreeMap<String, usize>,
    sources: &HashMap<(String, String), usize>,
    manifest: &Map<String, Value>,
    fasta_available: bool,
    source_sequences: Option<&HashMap<(String, String), String>>,
) -> Result<AppQ4Validation> {
    let object = final_path
        .as_object()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", "App Final Path must be an object"))?;
    if json_str(object, "workflow", "App Final Path")? != GRT_APP_WORKFLOW
        || json_str(object, "schema_version", "App Final Path")? != GRT_FINAL_PATH_SCHEMA_VERSION
        || json_str(object, "q4_relpath", "App Final Path")? != "grt/q/q4.fa"
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "App Final Path has unsupported workflow/schema",
        );
    }
    let chromosomes = object
        .get("chromosomes")
        .and_then(Value::as_array)
        .filter(|items| !items.is_empty())
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App Final Path chromosomes must be non-empty",
            )
        })?;
    let mut final_lengths = BTreeMap::new();
    let mut segment_ids = HashSet::new();
    for chromosome in chromosomes {
        let chr = chromosome.as_object().ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App Final Path chromosome must be an object",
            )
        })?;
        let chr_name = json_nonempty_str(chr, "chr", "App Final Path chromosome")?;
        if final_lengths
            .insert(
                chr_name.to_string(),
                json_positive_i64(chr, "q4_length", chr_name)? as usize,
            )
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate App Final Path chromosome {chr_name}"),
            );
        }
        if !reference_records.contains_key(chr_name) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("App Final Path references unknown chromosome {chr_name}"),
            );
        }
        validate_sha256(
            json_nonempty_str(chr, "q4_sha256", chr_name)?,
            &format!("App Final Path {chr_name}.q4_sha256"),
        )?;
        let segments = chr
            .get("segments")
            .and_then(Value::as_array)
            .filter(|items| !items.is_empty())
            .ok_or_else(|| {
                grt_anyhow(
                    "INVALID_JSON",
                    format!("App Final Path {chr_name}.segments must be non-empty"),
                )
            })?;
        let mut segment_total = 0_usize;
        for segment in segments {
            let segment = segment.as_object().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "App Final Path segment must be an object")
            })?;
            let id = json_nonempty_str(segment, "segment_id", "App Final Path segment")?;
            if !segment_ids.insert(id.to_string()) {
                return grt_err(
                    "DUPLICATE_ID",
                    format!("duplicate App Final Path segment {id}"),
                );
            }
            let length = json_positive_i64(segment, "length", id)? as usize;
            segment_total = segment_total.checked_add(length).ok_or_else(|| {
                grt_anyhow(
                    "INVALID_COORDINATE",
                    "App Final Path segment lengths overflow",
                )
            })?;
            let kind = json_str(segment, "kind", id)?;
            enum_value(
                kind,
                &["source", "patch", "correction", "telomere", "gap"],
                &format!("App segment {id}.kind"),
            )?;
            if kind == "gap" {
                continue;
            }
            let orient = orientation(
                json_str(segment, "orientation", id)?,
                &format!("App segment {id}"),
            )?;
            let source = segment
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("App segment {id}.source is invalid"),
                    )
                })?;
            let source_key = (
                json_nonempty_str(source, "dataset", id)?.to_string(),
                json_nonempty_str(source, "contig", id)?.to_string(),
            );
            let source_length = sources.get(&source_key).ok_or_else(|| {
                grt_anyhow(
                    "BROKEN_REFERENCE",
                    format!("App segment {id} references unknown source"),
                )
            })?;
            let start = json_positive_i64(source, "start", id)?;
            let end = json_positive_i64(source, "end", id)?;
            if end < start || end as usize > *source_length || (end - start + 1) as usize != length
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("App segment {id} source interval does not match length"),
                );
            }
            if orientation(
                json_str(source, "orientation", id)?,
                &format!("App segment {id}.source"),
            )? != orient
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("App segment {id} orientation differs from source"),
                );
            }
        }
        if segment_total != final_lengths[chr_name] {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("App Final Path segment lengths differ for {chr_name}"),
            );
        }
    }
    if final_lengths.keys().collect::<HashSet<_>>()
        != reference_records.keys().collect::<HashSet<_>>()
    {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "App Final Path chromosome set differs from reference FAI",
        );
    }
    let mut q4_records = None;
    let q4_path = bundle_root.join("grt/q/q4.fa");
    if fasta_available {
        let records = read_fasta(
            &required_bundle_file(bundle_root, "grt/q/q4.fa", "App q4 FASTA")?,
            "App q4 FASTA",
            false,
        )?;
        if sha256_file(&q4_path)?
            != json_nonempty_str(manifest, "q4_artifact_sha256", "App manifest")?
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                "App q4 artifact checksum differs from manifest",
            );
        }
        for chromosome in chromosomes {
            let chr = chromosome.as_object().unwrap();
            let name = json_str(chr, "chr", "App Final Path chromosome")?;
            let sequence = records.get(name).ok_or_else(|| {
                grt_anyhow(
                    "FINAL_PATH_MISMATCH",
                    format!("App q4 FASTA lacks chromosome {name}"),
                )
            })?;
            if sequence.len() != final_lengths[name]
                || sha256_bytes(sequence.as_bytes()) != json_str(chr, "q4_sha256", name)?
            {
                return grt_err(
                    "FINAL_PATH_MISMATCH",
                    format!("App q4 FASTA differs from Final Path for {name}"),
                );
            }
            if let Some(source_sequences) = source_sequences {
                let mut rebuilt = String::new();
                for segment in chr["segments"].as_array().unwrap() {
                    let segment = segment.as_object().unwrap();
                    let length = json_positive_i64(segment, "length", name)? as usize;
                    if segment.get("kind").and_then(Value::as_str) == Some("gap") {
                        rebuilt.push_str(&"N".repeat(length));
                        continue;
                    }
                    let source = segment["source"].as_object().unwrap();
                    let key = (
                        json_str(source, "dataset", name)?.to_string(),
                        json_str(source, "contig", name)?.to_string(),
                    );
                    let start = json_positive_i64(source, "start", name)?;
                    let end = json_positive_i64(source, "end", name)?;
                    let orient = orientation(json_str(source, "orientation", name)?, name)?;
                    let source_sequence = source_sequences.get(&key).ok_or_else(|| {
                        grt_anyhow(
                            "BROKEN_REFERENCE",
                            format!("App q4 source record is missing for {name}"),
                        )
                    })?;
                    rebuilt.push_str(&orient_sequence(
                        &source_sequence[(start - 1) as usize..end as usize],
                        orient,
                    ));
                }
                if rebuilt != *sequence {
                    return grt_err(
                        "FINAL_PATH_MISMATCH",
                        format!("App Final Path source reconstruction differs from q4 for {name}"),
                    );
                }
            }
        }
        q4_records = Some(records);
    } else if q4_path.exists() {
        return grt_err(
            "INVALID_VALUE",
            "no_fasta App package must not contain grt/q/q4.fa",
        );
    }
    Ok((final_lengths, q4_records))
}

pub(super) fn validate_stage_status(
    bundle_root: &Path,
    table: &TsvTable,
    q_hashes: &HashMap<String, String>,
    donor_sets: &HashMap<String, &TsvRow>,
) -> Result<()> {
    for (row, (stage, input, output)) in table.rows.iter().zip(STAGE_TRANSITIONS.iter()) {
        if field(row, "stage")? != *stage
            || field(row, "q_input_version")? != *input
            || field(row, "q_output_version")? != *output
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("stage transition must be {stage}:{input}->{output}"),
            );
        }
        if field(row, "status")? != "success"
            || q_hashes.get(*input).map(String::as_str) != Some(field(row, "q_input_sha256")?)
            || q_hashes.get(*output).map(String::as_str) != Some(field(row, "q_output_sha256")?)
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("stage {stage} q transition checksum mismatch"),
            );
        }
        let donor_set_id = field(row, "donor_set_id")?;
        if !donor_set_id.is_empty() && !donor_sets.contains_key(donor_set_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("stage {stage} references unknown donor set"),
            );
        }
        validate_artifact(
            bundle_root,
            field(row, "checkpoint_relpath")?,
            field(row, "checkpoint_sha256")?,
            &format!("stage {stage} checkpoint"),
        )?;
    }
    Ok(())
}

pub(super) fn validate_tool_versions(table: &TsvTable) -> Result<()> {
    let mut tools = HashSet::new();
    for row in &table.rows {
        let tool = nonempty(row, "tool", "tool version tool")?;
        nonempty(row, "version", "tool version")?;
        nonempty(row, "executable", "tool executable")?;
        if !tools.insert(tool.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate tool version {tool}"));
        }
    }
    Ok(())
}

pub(super) fn validate_source_cards(
    table: &TsvTable,
    sources: &HashMap<(String, String), String>,
    assignment_baselines: &HashMap<(String, String, String), (String, i64)>,
    evidence: &HashMap<String, &TsvRow>,
    events: &HashMap<String, &Value>,
    segments: &HashMap<String, (&Value, String)>,
) -> Result<()> {
    let mut card_ids = HashSet::new();
    for row in &table.rows {
        let card = nonempty(row, "source_card_key", "source card key")?;
        if !card_ids.insert(card.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate source card {card}"));
        }
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown source"),
            );
        }
        enum_value(
            field(row, "original_assignment")?,
            &["assigned", "unplaced", "cross_chr"],
            &format!("source card {card}.original_assignment"),
        )?;
        enum_value(
            field(row, "placement_mode")?,
            &["normal", "grt_promoted", "cross_chr_grt_usage"],
            &format!("source card {card}.placement_mode"),
        )?;
        enum_value(
            field(row, "ref_alignment_status")?,
            &["hit", "weak_hit", "multi_hit", "other_chr_only", "no_hit"],
            &format!("source card {card}.ref_alignment_status"),
        )?;
        let card_orientation =
            orientation(field(row, "orientation")?, &format!("source card {card}"))?;
        let card_anchor = parse_i64(
            field(row, "anchor_start")?,
            &format!("source card {card}.anchor_start"),
        )?;
        if field(row, "placement_mode")? == "normal" {
            let assignment_key = (
                key.0.clone(),
                key.1.clone(),
                field(row, "target_chr")?.to_string(),
            );
            let Some((baseline_orientation, baseline_anchor)) =
                assignment_baselines.get(&assignment_key)
            else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} lacks an assignment baseline"),
                );
            };
            if card_orientation != baseline_orientation || card_anchor != *baseline_anchor {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} disagrees with chr assignment baseline"),
                );
            }
        }
        let expected = format!(
            "{}:{}:{}:{}",
            key.0,
            key.1,
            field(row, "target_chr")?,
            field(row, "placement_mode")?
        );
        if card != expected {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} is non-canonical"),
            );
        }
        let refs = json_string_list(
            field(row, "ref_evidence_ids_json")?,
            &format!("source card {card}.ref evidence"),
        )?;
        let event_ids = json_string_list(
            field(row, "accepted_event_ids_json")?,
            &format!("source card {card}.events"),
        )?;
        let segment_ids = json_string_list(
            field(row, "final_path_segment_ids_json")?,
            &format!("source card {card}.segments"),
        )?;
        let pairwise = json_string_list(
            field(row, "pairwise_evidence_ids_json")?,
            &format!("source card {card}.pairwise evidence"),
        )?;
        if refs.is_empty() || event_ids.is_empty() || segment_ids.is_empty() || pairwise.is_empty()
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} has incomplete trace chain"),
            );
        }
        if refs.iter().any(|id| {
            evidence.get(id).is_none_or(|row| {
                field(row, "stage").ok() != Some("assignment")
                    || field(row, "status").ok() != Some("accepted")
            })
        }) || pairwise.iter().any(|id| {
            evidence.get(id).is_none_or(|row| {
                field(row, "stage").ok() != Some("display_pairwise")
                    || field(row, "status").ok() != Some("accepted")
            })
        }) || event_ids.iter().any(|id| {
            events
                .get(id)
                .is_none_or(|event| event.get("status").and_then(Value::as_str) != Some("accepted"))
        }) || segment_ids.iter().any(|id| !segments.contains_key(id))
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} contains an invalid trace link"),
            );
        }
        let expected_event_ids = events
            .iter()
            .filter_map(|(event_id, event)| {
                let action = event.get("action").and_then(Value::as_str).unwrap_or("");
                (event.get("status").and_then(Value::as_str) == Some("accepted")
                    && event.get("source_card_key").and_then(Value::as_str) == Some(card)
                    && matches!(
                        action,
                        "fill"
                            | "patch"
                            | "replace"
                            | "correct_boundary"
                            | "refill"
                            | "extend_telomere"
                    ))
                .then(|| event_id.clone())
            })
            .collect::<HashSet<_>>();
        if event_ids.iter().cloned().collect::<HashSet<_>>() != expected_event_ids {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} accepted-event set is not exact"),
            );
        }
        let expected_segment_ids = expected_event_ids
            .iter()
            .filter_map(|event_id| {
                events[event_id]
                    .get("final_path_segment_id")
                    .and_then(Value::as_str)
                    .filter(|value| !value.is_empty())
                    .map(ToString::to_string)
            })
            .collect::<HashSet<_>>();
        if segment_ids.iter().cloned().collect::<HashSet<_>>() != expected_segment_ids {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} Final Path segment set is not exact"),
            );
        }
        for evidence_id in refs.iter().chain(&pairwise) {
            let evidence_row = evidence[evidence_id];
            if field(evidence_row, "source_dataset")? != key.0.as_str()
                || field(evidence_row, "source_contig")? != key.1.as_str()
                || field(evidence_row, "source_start")? != "1"
                || parse_positive_i64(
                    field(evidence_row, "source_end")?,
                    &format!("source card {card} evidence end"),
                )? as usize
                    != sources[&key].len()
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} evidence is not full-source evidence"),
                );
            }
            let parameters = parse_json_object(
                field(evidence_row, "parameters_json")?,
                &format!("source card {card} evidence parameters"),
            )?;
            let role = parameters.get("role").and_then(Value::as_str);
            if refs.contains(evidence_id) && role != Some("source_ref_profile") {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} lacks source ref-profile role metadata"),
                );
            }
            if pairwise.contains(evidence_id) {
                if role != Some("display_pairwise") {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("source card {card} lacks display-pairwise role metadata"),
                    );
                }
                let expected_provenance = if field(row, "placement_mode")? == "normal" {
                    "existing_main_view"
                } else {
                    "grt_supplement"
                };
                if parameters.get("provenance").and_then(Value::as_str) != Some(expected_provenance)
                {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("source card {card} has invalid pairwise provenance"),
                    );
                }
            }
        }
        for event_id in &event_ids {
            if events[event_id]
                .get("source_card_key")
                .and_then(Value::as_str)
                != Some(card)
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} event link is not bidirectional"),
                );
            }
        }
        for segment_id in &segment_ids {
            let segment = segments[segment_id].0;
            let Some(source) = segment.get("source").and_then(Value::as_object) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} points to sourceless segment"),
                );
            };
            if source.get("dataset").and_then(Value::as_str) != Some(key.0.as_str())
                || source.get("contig").and_then(Value::as_str) != Some(key.1.as_str())
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} segment source differs"),
                );
            }
            let event_id = segment
                .get("event_id")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("source card {card} segment lacks event"),
                    )
                })?;
            let event_source = events[event_id]
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("source card {card} event lacks source"),
                    )
                })?;
            if source.get("start") != event_source.get("start")
                || source.get("end") != event_source.get("end")
                || source.get("orientation") != event_source.get("orientation")
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} event and segment source intervals differ"),
                );
            }
        }
    }
    Ok(())
}

pub(super) fn validate_gap_attempts(
    table: &TsvTable,
    events: &HashMap<String, &Value>,
) -> Result<()> {
    let mut ids = HashSet::new();
    for row in &table.rows {
        let id = nonempty(row, "attempt_id", "gap attempt id")?;
        if !ids.insert(id.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate gap attempt {id}"));
        }
        nonempty(row, "chr", &format!("gap attempt {id}.chr"))?;
        nonempty(row, "object_id", &format!("gap attempt {id}.object_id"))?;
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
            &format!("gap attempt {id}.stage"),
        )?;
        parse_nonnegative_i64(
            field(row, "candidate_count")?,
            &format!("gap attempt {id}.candidate_count"),
        )?;
        let event_id = field(row, "accepted_event_id")?;
        if !event_id.is_empty()
            && events
                .get(event_id)
                .is_none_or(|event| event.get("status").and_then(Value::as_str) != Some("accepted"))
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("gap attempt {id} references invalid accepted event"),
            );
        }
    }
    Ok(())
}

pub(super) fn source_catalog(
    bundle_root: &Path,
    table: &TsvTable,
) -> Result<HashMap<(String, String), String>> {
    let mut cache = HashMap::<String, BTreeMap<String, String>>::new();
    let mut sources = HashMap::new();
    for row in &table.rows {
        let dataset = nonempty(row, "dataset_name", "source locator dataset")?.to_string();
        let contig = nonempty(row, "seq_name", "source locator sequence")?.to_string();
        let relpath = field(row, "fasta_relpath")?.to_string();
        if !cache.contains_key(&relpath) {
            let path = required_bundle_file(
                bundle_root,
                &relpath,
                &format!("source locator {dataset}:{contig}"),
            )?;
            cache.insert(relpath.clone(), read_fasta(&path, &relpath, false)?);
        }
        let sequence = cache[&relpath].get(&contig).cloned().ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("source locator {dataset}:{contig} is absent from {relpath}"),
            )
        })?;
        if sources
            .insert((dataset.clone(), contig.clone()), sequence)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate source locator for {dataset}:{contig}"),
            );
        }
    }
    Ok(sources)
}
