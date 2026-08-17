use super::*;

pub fn initialize_grt_project(
    project_db_path: &Path,
    project_name: &str,
) -> Result<GrtProjectInitializationSummary> {
    initialize_grt_project_with_options(project_db_path, project_name, false)
}

pub fn initialize_grt_project_with_options(
    project_db_path: &Path,
    project_name: &str,
    phased_assembly_enabled: bool,
) -> Result<GrtProjectInitializationSummary> {
    let recipe = load_grt_locked_recipe(project_db_path)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let options = list_initializer_options_with_connection(&conn)?;
    if options.references.len() != 1 {
        bail!(
            "GRT locked recipe requires exactly one imported reference, found {}",
            options.references.len()
        );
    }
    let reference_genome_id = options.references[0].id;
    let dataset_id_by_name = options
        .datasets
        .iter()
        .map(|dataset| (dataset.name.as_str(), dataset.id))
        .collect::<HashMap<_, _>>();
    let primary_dataset_id = dataset_id_by_name
        .get(recipe.primary_dataset.as_str())
        .copied()
        .ok_or_else(|| {
            anyhow!(
                "GRT locked primary dataset '{}' is not present in the workspace catalog",
                recipe.primary_dataset
            )
        })?;
    let support_dataset_ids =
        recipe
            .support_datasets
            .iter()
            .map(|name| {
                dataset_id_by_name.get(name.as_str()).copied().ok_or_else(|| {
                anyhow!(
                    "GRT locked support dataset '{}' is not present in the workspace catalog",
                    name
                )
            })
            })
            .collect::<Result<Vec<_>>>()?;

    let initialized = initialize_project_with_connection(
        &mut conn,
        &ProjectInitializationRequest {
            project_name: project_name.to_string(),
            reference_genome_id,
            primary_dataset_id,
            support_dataset_ids: support_dataset_ids.clone(),
            auto_check_new_seq: false,
            phased_assembly_enabled: Some(phased_assembly_enabled),
            chr_assignment_min_coverage_percent: None,
            description: Some(format!("locked GRT recipe {}", recipe.recipe_id)),
        },
    )?;
    let project_id = initialized.project_id;
    let completed = (|| {
        let assembly = bootstrap_project_assembly_with_connection(&mut conn, project_id)?;
        let materialized_source_card_count =
            materialize_grt_source_cards_with_connection(&mut conn, project_id)?;
        verify_project_assignment_orientation_projection(&conn, project_id)?;
        set_project_auto_pipeline_done_with_connection(&mut conn, project_id, true)?;
        Ok((assembly, materialized_source_card_count))
    })();
    let (assembly, materialized_source_card_count) = match completed {
        Ok(value) => value,
        Err(error) => {
            delete_project_with_connection(&mut conn, project_id).with_context(|| {
                format!("failed to clean up incomplete locked GRT project after: {error:#}")
            })?;
            return Err(error);
        }
    };

    Ok(GrtProjectInitializationSummary {
        project_id,
        project_name: initialized.project_name,
        version: initialized.version,
        reference_genome_id: initialized.reference_genome_id,
        primary_dataset_id: initialized.primary_dataset_id,
        support_dataset_ids,
        project_dataset_count: initialized.project_dataset_count,
        phased_assembly_enabled: initialized.phased_assembly_enabled,
        chr_assignment_min_coverage_percent: initialized.chr_assignment_min_coverage_percent,
        assembly_seq_count: assembly.assembly_seq_count + materialized_source_card_count as i64,
        assembly_ctg_count: assembly.assembly_ctg_count + materialized_source_card_count as i64,
        materialized_source_card_count,
    })
}

pub(super) fn materialize_grt_source_cards_with_connection(
    conn: &mut Connection,
    project_id: i64,
) -> Result<usize> {
    let source_cards = load_matching_json(
        conn,
        "SELECT row_json FROM grt_source_card ORDER BY source_card_key",
        |_| true,
    )?;
    let tx = conn
        .transaction()
        .context("failed to start GRT source-card materialization transaction")?;
    let created_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string();
    let mut inserted = 0_usize;
    for card in source_cards {
        let object = card
            .as_object()
            .ok_or_else(|| anyhow!("persisted GRT source card must be an object"))?;
        let placement_mode = json_nonempty_str(object, "placement_mode", "GRT source card")?;
        if placement_mode != "grt_promoted" && placement_mode != "cross_chr_grt_usage" {
            continue;
        }
        let source_card_key = json_nonempty_str(object, "source_card_key", "GRT source card")?;
        let dataset_name = json_nonempty_str(object, "dataset_name", "GRT source card")?;
        let contig_name = json_nonempty_str(object, "contig_name", "GRT source card")?;
        let target_chr = json_nonempty_str(object, "target_chr", "GRT source card")?;
        let anchor_start = parse_positive_i64(
            json_nonempty_str(object, "anchor_start", "GRT source card")?,
            "GRT source card.anchor_start",
        )?;
        let orient = orientation(
            json_nonempty_str(object, "orientation", "GRT source card")?,
            "GRT source card orientation",
        )?;
        let original_assignment =
            json_nonempty_str(object, "original_assignment", "GRT source card")?;
        let ref_alignment_status =
            json_nonempty_str(object, "ref_alignment_status", "GRT source card")?;
        let (source_seq_id, source_length): (i64, i64) = tx
            .query_row(
                "SELECT ss.id, ss.length
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 JOIN project_dataset pd ON pd.dataset_id = d.id
                 WHERE pd.project_id = ?1 AND d.name = ?2 AND ss.seq_name = ?3",
                params![project_id, dataset_name, contig_name],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .with_context(|| {
                format!(
                    "failed to resolve GRT source card {source_card_key} to a project source sequence"
                )
            })?;
        let already_visible: Option<(i64, String, Option<i64>, String)> = tx
            .query_row(
                "SELECT c.id, s.orient, c.anchor_start, c.placement_mode
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.project_id = ?1 AND s.source_seq_id = ?2 AND c.assigned_chr_name = ?3
                 LIMIT 1",
                params![project_id, source_seq_id, target_chr],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()
            .context("failed to check existing GRT source-card placement")?;
        if placement_mode == "normal" {
            let Some((_, existing_orient, existing_anchor, _)) = already_visible else {
                bail!("normal GRT source card {source_card_key} is absent from the main view");
            };
            if existing_orient != orient || existing_anchor != Some(anchor_start) {
                bail!(
                    "normal GRT source card {source_card_key} disagrees with the main-view source orientation or anchor"
                );
            }
            continue;
        }
        if let Some((_, existing_orient, existing_anchor, existing_mode)) = already_visible {
            if existing_orient != orient
                || existing_anchor != Some(anchor_start)
                || existing_mode != placement_mode
            {
                bail!(
                    "GRT source card {source_card_key} conflicts with an existing main-view placement"
                );
            }
            continue;
        }
        let assembly_seq_id = {
            tx.execute(
                "INSERT INTO assembly_seq (
                    project_id, source_seq_id, instance_key, orient, source_start, source_end,
                    left_end_type, right_end_type, hidden, created_at, note
                 ) VALUES (?1, ?2, ?3, ?4, 1, ?5, 'normal', 'normal', 0, ?6, ?7)",
                params![
                    project_id,
                    source_seq_id,
                    format!("grt:{source_card_key}"),
                    orient,
                    source_length,
                    created_at,
                    format!("grt_source_card_key={source_card_key}")
                ],
            )
            .with_context(|| format!("failed to materialize GRT source card {source_card_key}"))?;
            tx.last_insert_rowid()
        };
        let chr_order: i64 = tx
            .query_row(
                "SELECT COALESCE(MAX(chr_order), 0) + 1
                 FROM assembly_ctg
                 WHERE project_id = ?1 AND assigned_chr_name = ?2",
                params![project_id, target_chr],
                |row| row.get(0),
            )
            .context("failed to allocate GRT source-card chromosome order")?;
        let preferred_name = format!("{contig_name}@{target_chr}");
        let name_exists: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM assembly_ctg WHERE project_id = ?1 AND name = ?2)",
            params![project_id, preferred_name],
            |row| row.get::<_, i64>(0),
        )? > 0;
        let ctg_name = if name_exists {
            format!("{dataset_name}:{contig_name}@{target_chr}")
        } else {
            preferred_name
        };
        tx.execute(
            "INSERT INTO assembly_ctg (
                project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
                ref_orient, placement_mode, created_at, note
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                project_id,
                assembly_seq_id,
                ctg_name,
                target_chr,
                chr_order,
                anchor_start,
                orient,
                placement_mode,
                created_at,
                format!(
                    "grt_source_card_key={source_card_key}; original_assignment={original_assignment}; ref_alignment_status={ref_alignment_status}"
                )
            ],
        )
        .with_context(|| format!("failed to place GRT source card {source_card_key}"))?;
        inserted += 1;
    }
    tx.commit()
        .context("failed to commit GRT source-card materialization")?;
    Ok(inserted)
}

pub(super) fn verify_project_assignment_orientation_projection(
    conn: &Connection,
    project_id: i64,
) -> Result<()> {
    let mut baseline_stmt = conn
        .prepare(
            "SELECT
                ica.source_seq_id,
                d.name,
                ss.seq_name,
                rc.chr_name,
                ica.source_orientation,
                ica.orientation_source,
                ica.anchor_start
             FROM imported_chr_assignment ica
             JOIN source_seq ss ON ss.id = ica.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             JOIN project_dataset pd ON pd.dataset_id = ss.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY d.id, ss.id, rc.id",
        )
        .context("failed to prepare GRT assignment projection verification")?;
    let baselines = baseline_stmt
        .query_map(params![project_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, i64>(6)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut projected_stmt = conn
        .prepare(
            "SELECT s.orient, c.anchor_start
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.project_id = ?1
               AND s.source_seq_id = ?2
               AND c.assigned_chr_name = ?3",
        )
        .context("failed to prepare projected GRT assignment query")?;
    for (
        source_seq_id,
        dataset_name,
        seq_name,
        chr_name,
        source_orientation,
        orientation_source,
        anchor_start,
    ) in baselines
    {
        if orientation_source != "ref_alignment" {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} has unsupported orientation_source={orientation_source}"
            );
        }
        let projected = projected_stmt
            .query_map(params![project_id, source_seq_id, chr_name], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, Option<i64>>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        if projected.len() != 1 {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} projected {} main-view cards, expected 1",
                projected.len()
            );
        }
        let (projected_orientation, projected_anchor) = &projected[0];
        if projected_orientation != &source_orientation || *projected_anchor != Some(anchor_start) {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} disagrees with main-view source orientation or anchor"
            );
        }
    }
    Ok(())
}
