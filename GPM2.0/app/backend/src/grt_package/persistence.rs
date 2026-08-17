use super::*;

pub(crate) fn persist_grt_package(
    tx: &Transaction<'_>,
    package: &ValidatedGrtPackage,
) -> Result<()> {
    clear_grt_tables(tx)?;
    let package_row = one_row(&package.tables, "metadata/package.tsv")?;
    let recipe = one_row(&package.tables, "metadata/grt_recipe.tsv")?;
    tx.execute(
        "INSERT INTO grt_package (
            id, workflow, schema_version, final_path_schema_version, recipe_id, primary_dataset,
            support_datasets_json, reads_qc_enabled, donor_set_id, tel_donor_set_id, q0_relpath,
            final_q_relpath, q0_artifact_sha256, q4_artifact_sha256, final_path_json
         ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        params![
            field(package_row, "workflow")?,
            field(package_row, "schema_version")?,
            field(package_row, "final_path_schema_version")?,
            field(recipe, "recipe_id")?,
            field(recipe, "primary_dataset")?,
            field(recipe, "support_datasets_json")?,
            if parse_bool(
                field(recipe, "reads_qc_enabled")?,
                "recipe.reads_qc_enabled"
            )? {
                1
            } else {
                0
            },
            field(recipe, "donor_set_id")?,
            field(recipe, "tel_donor_set_id")?,
            field(recipe, "q0_relpath")?,
            field(recipe, "final_q_relpath")?,
            package.q0_artifact_sha256,
            package.q4_artifact_sha256,
            serde_json::to_string(&package.final_path)?,
        ],
    )
    .context("failed to persist locked GRT package recipe")?;

    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_contig_roles.tsv")?,
        "grt_contig_role",
        &["dataset_name", "contig_name"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_sets.tsv")?,
        "grt_donor_set",
        &["donor_set_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_members.tsv")?,
        "grt_donor_member",
        &["donor_set_id", "member_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_q_segments.tsv")?,
        "grt_q_segment",
        &["segment_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_evidence_registry.tsv")?,
        "grt_evidence",
        &["evidence_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_usage.tsv")?,
        "grt_donor_usage",
        &["usage_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_used_contigs.tsv")?,
        "grt_source_card",
        &["source_card_key"],
    )?;
    for row in &table(&package.tables, "metadata/grt_gap_attempts.tsv")?.rows {
        let stage = field(row, "stage")?;
        tx.execute(
            "INSERT INTO grt_object_attempt (
                attempt_id, chr, object_id, object_kind, stage, status,
                accepted_event_id, row_json
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                field(row, "attempt_id")?,
                field(row, "chr")?,
                field(row, "object_id")?,
                if stage == "step4_telomere" {
                    "terminal"
                } else {
                    "gap"
                },
                stage,
                field(row, "status")?,
                field(row, "accepted_event_id")?,
                serde_json::to_string(row)?,
            ],
        )
        .context("failed to persist GRT gap/terminal object attempt")?;
    }
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_stage_status.tsv")?,
        "grt_stage_status",
        &["stage"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_tool_versions.tsv")?,
        "grt_tool_version",
        &["tool"],
    )?;

    for event in &package.events {
        let object = event.as_object().unwrap();
        tx.execute(
            "INSERT INTO grt_event (event_id, stage, chr, object_id, action, status, source_card_key, final_path_segment_id, event_json)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                json_str(object, "event_id", "event")?, json_str(object, "stage", "event")?,
                json_str(object, "chr", "event")?, json_str(object, "object_id", "event")?,
                json_str(object, "action", "event")?, json_str(object, "status", "event")?,
                object.get("source_card_key").and_then(Value::as_str).unwrap_or(""),
                object.get("final_path_segment_id").and_then(Value::as_str).unwrap_or(""),
                serde_json::to_string(event)?,
            ],
        ).context("failed to persist GRT event")?;
    }
    let chromosomes = package.final_path["chromosomes"].as_array().unwrap();
    for chromosome in chromosomes {
        let object = chromosome.as_object().unwrap();
        let chr_name = json_str(object, "chr", "Final Path chromosome")?;
        tx.execute(
            "INSERT INTO grt_final_path_chr (chr, q4_length, q4_sha256, chromosome_json) VALUES (?1, ?2, ?3, ?4)",
            params![chr_name, json_positive_i64(object, "q4_length", chr_name)?, json_str(object, "q4_sha256", chr_name)?, serde_json::to_string(chromosome)?],
        ).context("failed to persist GRT Final Path chromosome")?;
        for (offset, segment) in object["segments"].as_array().unwrap().iter().enumerate() {
            let segment_object = segment.as_object().unwrap();
            tx.execute(
                "INSERT INTO grt_final_path_segment (segment_id, chr, segment_order, kind, event_id, segment_json)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    json_str(segment_object, "segment_id", "segment")?, chr_name, (offset + 1) as i64,
                    json_str(segment_object, "kind", "segment")?, segment_object.get("event_id").and_then(Value::as_str),
                    serde_json::to_string(segment)?,
                ],
            ).context("failed to persist GRT Final Path segment")?;
        }
    }
    Ok(())
}

pub(super) fn persist_row_table(
    tx: &Transaction<'_>,
    table: &TsvTable,
    sql_table: &str,
    id_columns: &[&str],
) -> Result<()> {
    let placeholders = (1..=id_columns.len() + 1)
        .map(|index| format!("?{index}"))
        .collect::<Vec<_>>()
        .join(", ");
    let mut columns = id_columns.join(", ");
    if !columns.is_empty() {
        columns.push_str(", ");
    }
    columns.push_str("row_json");
    let sql = format!("INSERT INTO {sql_table} ({columns}) VALUES ({placeholders})");
    for row in &table.rows {
        let row_json = serde_json::to_string(row)?;
        let mut values = id_columns
            .iter()
            .map(|column| field(row, column).map(ToString::to_string))
            .collect::<Result<Vec<_>>>()?;
        values.push(row_json);
        tx.execute(&sql, rusqlite::params_from_iter(values.iter()))
            .with_context(|| format!("failed to persist {sql_table}"))?;
    }
    Ok(())
}

pub(super) fn clear_grt_tables(tx: &Transaction<'_>) -> Result<()> {
    for table in [
        "grt_final_path_segment",
        "grt_final_path_chr",
        "grt_event",
        "grt_object_attempt",
        "grt_source_card",
        "grt_donor_usage",
        "grt_evidence",
        "grt_q_segment",
        "grt_donor_member",
        "grt_donor_set",
        "grt_contig_role",
        "grt_stage_status",
        "grt_tool_version",
        "grt_package",
    ] {
        tx.execute(&format!("DELETE FROM {table}"), [])
            .with_context(|| format!("failed to clear {table}"))?;
    }
    Ok(())
}
