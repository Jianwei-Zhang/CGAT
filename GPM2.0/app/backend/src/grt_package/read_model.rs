use super::*;

pub fn load_grt_locked_recipe(project_db_path: &Path) -> Result<GrtLockedRecipe> {
    let conn = open_workspace_db(project_db_path)?;
    conn.query_row(
        "SELECT workflow, schema_version, final_path_schema_version, recipe_id, primary_dataset,
                support_datasets_json, reads_qc_enabled, donor_set_id, tel_donor_set_id,
                q0_relpath, final_q_relpath, q0_artifact_sha256, q4_artifact_sha256
         FROM grt_package WHERE id = 1",
        [],
        |row| {
            let support_json: String = row.get(5)?;
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                support_json,
                row.get::<_, i64>(6)? > 0,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
                row.get::<_, String>(9)?,
                row.get::<_, String>(10)?,
                row.get::<_, String>(11)?,
                row.get::<_, String>(12)?,
            ))
        },
    )
    .optional()
    .context("failed to query locked GRT recipe")?
    .ok_or_else(|| anyhow!("GRT package recipe is not available"))
    .and_then(|row| {
        Ok(GrtLockedRecipe {
            workflow: row.0,
            schema_version: row.1,
            final_path_schema_version: row.2,
            recipe_id: row.3,
            primary_dataset: row.4,
            support_datasets: serde_json::from_str(&row.5)
                .context("persisted GRT support dataset JSON is invalid")?,
            reads_qc_enabled: row.6,
            donor_set_id: row.7,
            tel_donor_set_id: row.8,
            q0_relpath: row.9,
            final_q_relpath: row.10,
            q0_artifact_sha256: row.11,
            q4_artifact_sha256: row.12,
        })
    })
}

pub fn load_grt_final_path(project_db_path: &Path) -> Result<Value> {
    let conn = open_workspace_db(project_db_path)?;
    let json: String = conn
        .query_row(
            "SELECT final_path_json FROM grt_package WHERE id = 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .context("failed to query precomputed GRT Final Path")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    serde_json::from_str(&json).context("persisted GRT Final Path JSON is invalid")
}

pub fn load_grt_final_path_by_chr(project_db_path: &Path) -> Result<BTreeMap<String, Value>> {
    let conn = open_workspace_db(project_db_path)?;
    let source_lengths = load_persisted_source_lengths(&conn)?;
    let mut stmt = conn
        .prepare("SELECT chr, chromosome_json FROM grt_final_path_chr ORDER BY chr")
        .context("failed to prepare precomputed GRT Final Path chromosome query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    rows.into_iter()
        .map(|(chr_name, json)| {
            let chromosome: Value = serde_json::from_str(&json)
                .context("persisted GRT Final Path chromosome JSON is invalid")?;
            let projected =
                project_grt_final_path_chromosome(chromosome, &chr_name, &source_lengths)?;
            Ok((chr_name, projected))
        })
        .collect()
}

pub(super) fn load_persisted_source_lengths(
    conn: &Connection,
) -> Result<HashMap<(String, String), i64>> {
    let mut stmt = conn
        .prepare(
            "SELECT d.name, ss.seq_name, ss.length
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             ORDER BY d.name, ss.seq_name",
        )
        .context("failed to prepare persisted source length query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut source_lengths = HashMap::with_capacity(rows.len());
    for (dataset_name, contig_name, source_length) in rows {
        if source_length < 1 {
            bail!("persisted source length must be positive for {dataset_name}:{contig_name}");
        }
        if source_lengths
            .insert((dataset_name.clone(), contig_name.clone()), source_length)
            .is_some()
        {
            bail!("duplicate persisted source identity {dataset_name}:{contig_name}");
        }
    }
    Ok(source_lengths)
}

pub(super) fn project_grt_final_path_chromosome(
    mut chromosome: Value,
    chr_name: &str,
    source_lengths: &HashMap<(String, String), i64>,
) -> Result<Value> {
    let object = chromosome
        .as_object_mut()
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome JSON is invalid"))?;
    let segments = object
        .get_mut("segments")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome segments are invalid"))?;
    for (index, segment) in segments.iter_mut().enumerate() {
        let segment_object = segment
            .as_object_mut()
            .ok_or_else(|| anyhow!("persisted GRT Final Path segment JSON is invalid"))?;
        let label = format!("persisted GRT Final Path {chr_name} segment {}", index + 1);
        let kind = segment_object
            .get("kind")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("{label}.kind must be a string"))?;
        if kind != "gap" {
            let source = segment_object
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| anyhow!("{label}.source must be an object"))?;
            let dataset_name = source
                .get("dataset")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| anyhow!("{label}.source.dataset must be a non-empty string"))?;
            let contig_name = source
                .get("contig")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| anyhow!("{label}.source.contig must be a non-empty string"))?;
            let start = source
                .get("start")
                .and_then(Value::as_i64)
                .filter(|value| *value > 0)
                .ok_or_else(|| anyhow!("{label}.source.start must be a positive integer"))?;
            let end = source
                .get("end")
                .and_then(Value::as_i64)
                .filter(|value| *value > 0)
                .ok_or_else(|| anyhow!("{label}.source.end must be a positive integer"))?;
            let source_length = source_lengths
                .get(&(dataset_name.to_string(), contig_name.to_string()))
                .copied()
                .ok_or_else(|| {
                    anyhow!("{label} references missing source {dataset_name}:{contig_name}")
                })?;
            if start > source_length || end > source_length {
                bail!(
                    "{label} interval {start}-{end} exceeds source length {source_length} for {dataset_name}:{contig_name}"
                );
            }
            segment_object.insert("source_length".to_string(), Value::from(source_length));
        }
        for key in [
            "event_id",
            "eventId",
            "evidence_ids",
            "evidenceIds",
            "source_card_key",
            "sourceCardKey",
        ] {
            segment_object.remove(key);
        }
    }
    Ok(chromosome)
}

pub fn load_grt_object_attempts(project_db_path: &Path) -> Result<Vec<Value>> {
    let conn = open_workspace_db(project_db_path)?;
    let mut stmt = conn
        .prepare(
            "SELECT object_kind, row_json
             FROM grt_object_attempt
             ORDER BY chr, object_kind, object_id, stage, attempt_id",
        )
        .context("failed to prepare GRT object attempt query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    rows.into_iter()
        .map(|(object_kind, json)| {
            let mut value: Value = serde_json::from_str(&json)
                .context("persisted GRT object attempt JSON is invalid")?;
            value
                .as_object_mut()
                .ok_or_else(|| anyhow!("persisted GRT object attempt must be an object"))?
                .insert("object_kind".to_string(), Value::String(object_kind));
            Ok(value)
        })
        .collect()
}

pub fn load_grt_source_cards(project_db_path: &Path) -> Result<Vec<Value>> {
    let conn = open_workspace_db(project_db_path)?;
    load_matching_json(
        &conn,
        "SELECT row_json FROM grt_source_card ORDER BY source_card_key",
        |_| true,
    )
}

pub fn load_grt_source_card_statuses(project_db_path: &Path) -> Result<Vec<GrtSourceCardStatus>> {
    load_grt_source_cards(project_db_path)?
        .into_iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| anyhow!("persisted GRT source card JSON is invalid"))?;
            Ok(GrtSourceCardStatus {
                source_card_key: object
                    .get("source_card_key")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                dataset_name: object
                    .get("dataset_name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                contig_name: object
                    .get("contig_name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                target_chr: object
                    .get("target_chr")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                placement_mode: object
                    .get("placement_mode")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                ref_alignment_status: object
                    .get("ref_alignment_status")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            })
        })
        .collect()
}

pub fn load_grt_project_view(project_db_path: &Path) -> Result<GrtProjectView> {
    Ok(GrtProjectView {
        recipe: load_grt_locked_recipe(project_db_path)?,
        final_path_by_chr: load_grt_final_path_by_chr(project_db_path)?,
        source_cards: load_grt_source_card_statuses(project_db_path)?,
        verification: load_persisted_grt_final_path_verification(project_db_path)?,
    })
}

pub fn load_persisted_grt_final_path_verification(
    project_db_path: &Path,
) -> Result<GrtFinalPathVerification> {
    let conn = open_workspace_db(project_db_path)?;
    let (chromosome_count, segment_count, q4_artifact_sha256): (i64, i64, String) = conn
        .query_row(
            "SELECT
                (SELECT COUNT(*) FROM grt_final_path_chr),
                (SELECT COUNT(*) FROM grt_final_path_segment),
                q4_artifact_sha256
             FROM grt_package
             WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .context("failed to load persisted GRT Final Path verification summary")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    Ok(GrtFinalPathVerification {
        chromosome_count: usize::try_from(chromosome_count)
            .context("persisted GRT chromosome count is invalid")?,
        segment_count: usize::try_from(segment_count)
            .context("persisted GRT segment count is invalid")?,
        q4_artifact_sha256,
    })
}
