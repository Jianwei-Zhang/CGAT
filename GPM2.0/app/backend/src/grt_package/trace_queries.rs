use super::*;

pub fn load_grt_evidence(project_db_path: &Path, evidence_id: &str) -> Result<Value> {
    load_row_json(
        project_db_path,
        "grt_evidence",
        "evidence_id",
        evidence_id,
        "GRT evidence",
    )
}

pub fn verify_persisted_grt_final_path(project_db_path: &Path) -> Result<GrtFinalPathVerification> {
    let conn = open_workspace_db(project_db_path)?;
    let (final_path_json, final_q_relpath, expected_artifact_sha): (String, String, String) = conn
        .query_row(
            "SELECT final_path_json, final_q_relpath, q4_artifact_sha256
             FROM grt_package WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .context("failed to load persisted GRT Final Path verification inputs")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    let final_path: Value = serde_json::from_str(&final_path_json)
        .context("persisted GRT Final Path JSON is invalid")?;
    let chromosomes = final_path["chromosomes"]
        .as_array()
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosomes are invalid"))?;
    let mut fasta_cache = HashMap::<String, BTreeMap<String, String>>::new();
    let mut rebuilt_records = BTreeMap::<String, String>::new();
    let mut segment_count = 0_usize;
    for chromosome in chromosomes {
        let object = chromosome
            .as_object()
            .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome is invalid"))?;
        let chr_name = json_nonempty_str(object, "chr", "persisted Final Path chromosome")?;
        let segments = object["segments"]
            .as_array()
            .ok_or_else(|| anyhow!("persisted Final Path {chr_name} segments are invalid"))?;
        let mut rebuilt = String::new();
        for segment in segments {
            segment_count += 1;
            let segment_object = segment
                .as_object()
                .ok_or_else(|| anyhow!("persisted Final Path segment is invalid"))?;
            let length = json_positive_i64(segment_object, "length", "persisted segment")?;
            if segment_object.get("kind").and_then(Value::as_str) == Some("gap") {
                rebuilt.push_str(&"N".repeat(length as usize));
                continue;
            }
            let source = segment_object["source"]
                .as_object()
                .ok_or_else(|| anyhow!("persisted Final Path source is invalid"))?;
            let dataset = json_nonempty_str(source, "dataset", "persisted segment source")?;
            let contig = json_nonempty_str(source, "contig", "persisted segment source")?;
            let fasta_path: String = conn
                .query_row(
                    "SELECT ssl.fasta_path
                     FROM source_seq_locator ssl
                     JOIN source_seq ss ON ss.id = ssl.source_seq_id
                     JOIN dataset d ON d.id = ss.dataset_id
                     WHERE d.name = ?1 AND ss.seq_name = ?2",
                    params![dataset, contig],
                    |row| row.get(0),
                )
                .with_context(|| format!("failed to locate persisted source {dataset}:{contig}"))?;
            if !fasta_cache.contains_key(&fasta_path) {
                fasta_cache.insert(
                    fasta_path.clone(),
                    read_fasta(Path::new(&fasta_path), &fasta_path, false)?,
                );
            }
            let source_sequence = fasta_cache[&fasta_path].get(contig).ok_or_else(|| {
                anyhow!("persisted source {dataset}:{contig} is absent from its FASTA")
            })?;
            let start = json_positive_i64(source, "start", "persisted segment source")?;
            let end = json_positive_i64(source, "end", "persisted segment source")?;
            if start > end || end as usize > source_sequence.len() || end - start + 1 != length {
                return Err(anyhow!(
                    "persisted Final Path source interval is invalid for {dataset}:{contig}"
                ));
            }
            let orient = orientation(
                json_str(source, "orientation", "persisted segment source")?,
                "persisted segment source",
            )?;
            rebuilt.push_str(&orient_sequence(
                &source_sequence[(start - 1) as usize..end as usize],
                orient,
            ));
        }
        if rebuilt.len() != json_positive_i64(object, "q4_length", chr_name)? as usize
            || sha256_bytes(rebuilt.as_bytes()) != json_nonempty_str(object, "q4_sha256", chr_name)?
        {
            return Err(anyhow!(
                "persisted Final Path does not reconstruct q4 checksum for {chr_name}"
            ));
        }
        rebuilt_records.insert(chr_name.to_string(), rebuilt);
    }
    let workspace_root = project_db_path
        .parent()
        .ok_or_else(|| anyhow!("workspace database has no parent directory"))?;
    let q4_path = workspace_root.join(final_q_relpath);
    let actual_artifact_sha = sha256_file(&q4_path)?;
    if actual_artifact_sha != expected_artifact_sha {
        return Err(anyhow!("persisted q4 artifact checksum mismatch"));
    }
    let q4_records = read_fasta(&q4_path, "persisted q4 FASTA", false)?;
    if q4_records != rebuilt_records {
        return Err(anyhow!(
            "persisted Final Path sequences differ from q4 FASTA"
        ));
    }
    Ok(GrtFinalPathVerification {
        chromosome_count: chromosomes.len(),
        segment_count,
        q4_artifact_sha256: actual_artifact_sha,
    })
}

pub fn load_grt_source_card_trace(
    project_db_path: &Path,
    source_card_key: &str,
) -> Result<GrtSourceCardTrace> {
    let conn = open_workspace_db(project_db_path)?;
    let source_card = load_row_json_with_conn(
        &conn,
        "grt_source_card",
        "source_card_key",
        source_card_key,
        "GRT source card",
    )?;
    let card = source_card
        .as_object()
        .ok_or_else(|| anyhow!("persisted GRT source card JSON is invalid"))?;
    let event_ids = stored_string_list(card, "accepted_event_ids_json")?;
    let segment_ids = stored_string_list(card, "final_path_segment_ids_json")?;
    let ref_ids = stored_string_list(card, "ref_evidence_ids_json")?;
    let pairwise_ids = stored_string_list(card, "pairwise_evidence_ids_json")?;
    let donor_usage = load_matching_json(
        &conn,
        "SELECT row_json FROM grt_donor_usage ORDER BY usage_id",
        |value| {
            value
                .get("event_id")
                .and_then(Value::as_str)
                .is_some_and(|id| event_ids.iter().any(|candidate| candidate == id))
        },
    )?;
    let member_keys = donor_usage
        .iter()
        .filter_map(|value| {
            Some((
                value.get("donor_set_id")?.as_str()?.to_string(),
                value.get("member_id")?.as_str()?.to_string(),
            ))
        })
        .collect::<HashSet<_>>();
    let donor_set_ids = member_keys
        .iter()
        .map(|(donor_set_id, _)| donor_set_id.clone())
        .collect::<HashSet<_>>();
    let donor_members = load_matching_json(
        &conn,
        "SELECT row_json FROM grt_donor_member ORDER BY donor_set_id, member_id",
        |value| {
            value
                .get("donor_set_id")
                .and_then(Value::as_str)
                .zip(value.get("member_id").and_then(Value::as_str))
                .is_some_and(|(donor_set_id, member_id)| {
                    member_keys.contains(&(donor_set_id.to_string(), member_id.to_string()))
                })
        },
    )?;
    Ok(GrtSourceCardTrace {
        source_card,
        accepted_events: load_many_json(&conn, "grt_event", "event_id", "event_json", &event_ids)?,
        final_path_segments: load_many_json(
            &conn,
            "grt_final_path_segment",
            "segment_id",
            "segment_json",
            &segment_ids,
        )?,
        ref_evidence: load_many_json(&conn, "grt_evidence", "evidence_id", "row_json", &ref_ids)?,
        pairwise_evidence: load_many_json(
            &conn,
            "grt_evidence",
            "evidence_id",
            "row_json",
            &pairwise_ids,
        )?,
        donor_usage,
        donor_members,
        donor_sets: load_matching_json(
            &conn,
            "SELECT row_json FROM grt_donor_set ORDER BY donor_set_id",
            |value| {
                value
                    .get("donor_set_id")
                    .and_then(Value::as_str)
                    .is_some_and(|id| donor_set_ids.contains(id))
            },
        )?,
    })
}

pub fn load_grt_event_trace(project_db_path: &Path, event_id: &str) -> Result<GrtEventTrace> {
    let conn = open_workspace_db(project_db_path)?;
    let event = load_json_column_with_conn(
        &conn,
        "grt_event",
        "event_id",
        event_id,
        "event_json",
        "GRT event",
    )?;
    let object = event
        .as_object()
        .ok_or_else(|| anyhow!("persisted GRT event JSON is invalid"))?;
    let evidence_ids = object
        .get("evidence_ids")
        .map(|value| json_value_string_list(value, "event evidence_ids"))
        .transpose()?
        .unwrap_or_default();
    let usage_ids = object
        .get("usage_ids")
        .map(|value| json_value_string_list(value, "event usage_ids"))
        .transpose()?
        .unwrap_or_default();
    let segment_id = object
        .get("final_path_segment_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let source_card_key = object
        .get("source_card_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    Ok(GrtEventTrace {
        event,
        evidence: load_many_json(
            &conn,
            "grt_evidence",
            "evidence_id",
            "row_json",
            &evidence_ids,
        )?,
        donor_usage: load_many_json(&conn, "grt_donor_usage", "usage_id", "row_json", &usage_ids)?,
        final_path_segment: if segment_id.is_empty() {
            None
        } else {
            Some(load_json_column_with_conn(
                &conn,
                "grt_final_path_segment",
                "segment_id",
                &segment_id,
                "segment_json",
                "GRT Final Path segment",
            )?)
        },
        source_card: if source_card_key.is_empty() {
            None
        } else {
            Some(load_row_json_with_conn(
                &conn,
                "grt_source_card",
                "source_card_key",
                &source_card_key,
                "GRT source card",
            )?)
        },
    })
}

pub(super) fn load_row_json(
    project_db_path: &Path,
    table: &str,
    key_column: &str,
    key: &str,
    label: &str,
) -> Result<Value> {
    let conn = open_workspace_db(project_db_path)?;
    load_row_json_with_conn(&conn, table, key_column, key, label)
}
pub(super) fn load_row_json_with_conn(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    key: &str,
    label: &str,
) -> Result<Value> {
    load_json_column_with_conn(conn, table, key_column, key, "row_json", label)
}
pub(super) fn load_json_column_with_conn(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    key: &str,
    json_column: &str,
    label: &str,
) -> Result<Value> {
    let sql = format!("SELECT {json_column} FROM {table} WHERE {key_column} = ?1");
    let json: String = conn
        .query_row(&sql, params![key], |row| row.get(0))
        .optional()
        .with_context(|| format!("failed to query {label}"))?
        .ok_or_else(|| anyhow!("{label} does not exist: {key}"))?;
    serde_json::from_str(&json).with_context(|| format!("persisted {label} JSON is invalid"))
}
pub(super) fn load_many_json(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    json_column: &str,
    ids: &[String],
) -> Result<Vec<Value>> {
    ids.iter()
        .map(|id| load_json_column_with_conn(conn, table, key_column, id, json_column, table))
        .collect()
}
pub(super) fn load_matching_json(
    conn: &rusqlite::Connection,
    sql: &str,
    predicate: impl Fn(&Value) -> bool,
) -> Result<Vec<Value>> {
    let mut stmt = conn.prepare(sql)?;
    let values = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    values
        .into_iter()
        .map(|json| serde_json::from_str(&json).context("persisted GRT row JSON is invalid"))
        .filter_map(|result| match result {
            Ok(value) if predicate(&value) => Some(Ok(value)),
            Ok(_) => None,
            Err(error) => Some(Err(error)),
        })
        .collect()
}
pub(super) fn stored_string_list(object: &Map<String, Value>, key: &str) -> Result<Vec<String>> {
    let encoded = object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("persisted GRT source card lacks {key}"))?;
    serde_json::from_str(encoded)
        .with_context(|| format!("persisted GRT source card {key} is invalid"))
}
