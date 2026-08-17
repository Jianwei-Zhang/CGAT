use super::*;

#[derive(Debug, Clone)]
pub(super) struct PairwiseImportRun {
    run_name: String,
    paf_path: PathBuf,
    query_dataset_id: i64,
    target_dataset_id: i64,
}

pub(super) fn index_alignment_payloads_from_bundle<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let ref_run_count = count_bundle_ref_alignment_runs(&conn, bundle_root)?;
    let pairwise_runs = discover_pairwise_import_runs(&conn, bundle_root)?;
    recorder.reserve_remaining(1 + ref_run_count + 1 + pairwise_runs.len() + 2);
    conn.execute("DELETE FROM ref_alignment_hit", [])
        .context("failed to clear old ref alignment hits before import indexing")?;
    conn.execute("DELETE FROM pairwise_alignment_run", [])
        .context("failed to clear old pairwise alignment runs before import indexing")?;
    recorder.record(
        "index_alignment_reset",
        "cleared previous alignment indexes".to_string(),
    );
    let ref_summary = index_bundle_ref_alignment_hits_with_cancel(
        &mut conn,
        bundle_root,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    let mut indexed_run_count = 0_i64;
    let mut indexed_hit_count = 0_i64;
    for run in pairwise_runs {
        check_import_cancel(should_cancel)?;
        recorder.record(
            "index_pairwise_paf",
            format!(
                "{} ({})",
                run.run_name,
                path_relative_to(bundle_root, &run.paf_path)
            ),
        );
        let cache = ensure_pairwise_alignment_run_cache_cancel(
            &mut conn,
            run.query_dataset_id,
            run.target_dataset_id,
            &run.run_name,
            &run.paf_path,
            should_cancel,
        )?;
        indexed_run_count += 1;
        indexed_hit_count += cache.hit_count;
    }
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={}, indexed_hits={}",
            indexed_run_count, indexed_hit_count
        ),
    );
    Ok(())
}

pub(super) fn count_bundle_ref_alignment_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<usize> {
    let mut stmt = conn
        .prepare("SELECT name FROM dataset ORDER BY id")
        .context("failed to prepare dataset list for ref paf import progress")?;
    let dataset_names = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for ref paf import progress")?;
    Ok(dataset_names
        .iter()
        .filter(|dataset_name| {
            bundle_root
                .join("runs")
                .join(format!("{}_vs_ref", dataset_name))
                .join("result.paf")
                .exists()
        })
        .count())
}

pub(super) fn discover_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        run_orientation_by_name.insert(
            format!("{}_vs_self", target_name),
            (*target_dataset_id, *target_dataset_id),
        );
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}

pub(super) fn index_add_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    dataset_id: i64,
    dataset_name: &str,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs =
        discover_pairwise_import_runs_for_dataset(&conn, bundle_root, dataset_id, dataset_name)?;
    recorder.reserve_remaining(1 + pairwise_runs.len() + 2);
    let ref_summary = index_bundle_ref_alignment_hits_for_dataset_with_cancel(
        &mut conn,
        bundle_root,
        dataset_id,
        dataset_name,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    let mut indexed_run_count = 0_i64;
    let mut indexed_hit_count = 0_i64;
    for run in pairwise_runs {
        check_import_cancel(should_cancel)?;
        recorder.record(
            "index_pairwise_paf",
            format!(
                "{} ({})",
                run.run_name,
                path_relative_to(bundle_root, &run.paf_path)
            ),
        );
        let cache = ensure_pairwise_alignment_run_cache_cancel(
            &mut conn,
            run.query_dataset_id,
            run.target_dataset_id,
            &run.run_name,
            &run.paf_path,
            should_cancel,
        )?;
        indexed_run_count += 1;
        indexed_hit_count += cache.hit_count;
    }
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={}, indexed_hits={}",
            indexed_run_count, indexed_hit_count
        ),
    );
    Ok(())
}

pub(super) fn index_add_ctg_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    manifest: &AddCtgManifest,
    catalog: &AddCtgCatalogAppend,
    project_id: i64,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs = if manifest.skip_self {
        Vec::new()
    } else {
        discover_add_ctg_pairwise_import_runs(&conn, bundle_root, project_id, manifest)?
    };
    recorder.reserve_remaining(
        2 + if pairwise_runs.is_empty() {
            0
        } else {
            pairwise_runs.len() + 1
        },
    );
    let ref_run_name = format!("{}_vs_ref", manifest.ctg_name);
    let ref_paf_path = bundle_root
        .join("runs")
        .join("add_ctg")
        .join(&ref_run_name)
        .join("result.paf");
    recorder.record(
        "index_ref_paf",
        format!(
            "{} ({})",
            ref_run_name,
            path_relative_to(bundle_root, &ref_paf_path)
        ),
    );
    let loaded_ref_hits = index_ref_alignment_hits_for_source_seq_with_cancel(
        &mut conn,
        catalog.dataset_id,
        catalog.source_seq_id,
        &manifest.ctg_name,
        &ref_run_name,
        &ref_paf_path,
        should_cancel,
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!("loaded_datasets=1, loaded_hits={loaded_ref_hits}, skipped_datasets=0"),
    );

    if !pairwise_runs.is_empty() {
        let mut indexed_run_count = 0_i64;
        let mut indexed_hit_count = 0_i64;
        for run in pairwise_runs {
            check_import_cancel(should_cancel)?;
            recorder.record(
                "index_pairwise_paf",
                format!(
                    "{} ({})",
                    run.run_name,
                    path_relative_to(bundle_root, &run.paf_path)
                ),
            );
            let cache = ensure_pairwise_alignment_run_cache_cancel(
                &mut conn,
                catalog.dataset_id,
                run.target_dataset_id,
                &run.run_name,
                &run.paf_path,
                should_cancel,
            )?;
            indexed_run_count += 1;
            indexed_hit_count += cache.hit_count;
        }
        recorder.record(
            "index_pairwise_paf_complete",
            format!(
                "indexed_runs={}, indexed_hits={}",
                indexed_run_count, indexed_hit_count
            ),
        );
    }
    Ok(())
}

pub(super) fn discover_add_ctg_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = required_add_ctg_pairwise_datasets(conn, project_id, &manifest.target_chr)?;
    let mut runs = Vec::new();
    for (target_dataset_id, target_dataset_name) in datasets {
        let pair_run_name = format!("{}_vs_{}", target_dataset_name, manifest.ctg_name);
        let pair_paf_path = bundle_root
            .join("runs")
            .join(format!("chr_{}", manifest.target_chr))
            .join("add_ctg")
            .join(&pair_run_name)
            .join("result.paf");
        if !pair_paf_path.is_file() {
            bail!(
                "add_ctg payload is missing chr-group pairwise alignment payload: {}",
                pair_paf_path.display()
            );
        }
        runs.push(PairwiseImportRun {
            run_name: pair_run_name,
            paf_path: pair_paf_path,
            query_dataset_id: 0,
            target_dataset_id,
        });
    }
    runs.sort_by(|a, b| a.run_name.cmp(&b.run_name));
    Ok(runs)
}

pub(super) fn required_add_ctg_pairwise_datasets(
    conn: &rusqlite::Connection,
    project_id: i64,
    target_chr: &str,
) -> Result<Vec<(i64, String)>> {
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT d.id, d.name
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             JOIN source_seq ss ON ss.dataset_id = d.id
             JOIN imported_chr_assignment ica ON ica.source_seq_id = ss.id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             WHERE pd.project_id = ?1
               AND rc.chr_name = ?2
               AND d.name <> 'derived_ctg'
             ORDER BY d.id",
        )
        .context("failed to prepare add_ctg required pairwise dataset query")?;
    stmt.query_map(params![project_id, target_chr], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode add_ctg required pairwise datasets")
}

pub(super) fn discover_pairwise_import_runs_for_dataset(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    added_dataset_id: i64,
    added_dataset_name: &str,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for add-package pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for add-package pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        if *target_dataset_id == added_dataset_id {
            run_orientation_by_name.insert(
                format!("{}_vs_self", target_name),
                (*target_dataset_id, *target_dataset_id),
            );
        }
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            if *target_dataset_id != added_dataset_id && *query_dataset_id != added_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            if !run_name.contains(added_dataset_name) {
                continue;
            }
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}
