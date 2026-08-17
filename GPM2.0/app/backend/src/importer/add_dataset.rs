use super::*;

pub fn import_add_dataset_package(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)> {
    import_add_dataset_package_internal(
        zip_path,
        workspace_root,
        Some(project_id),
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_workspace_add_dataset_package(
    zip_path: &Path,
    workspace_root: &Path,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)> {
    import_workspace_add_dataset_package_with_hooks(
        zip_path,
        workspace_root,
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_add_dataset_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_dataset_package_internal(
        zip_path,
        workspace_root,
        Some(project_id),
        on_progress,
        should_cancel,
    )
}

pub fn import_workspace_add_dataset_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_dataset_package_internal(zip_path, workspace_root, None, on_progress, should_cancel)
}

pub(super) fn import_add_dataset_package_internal<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: Option<i64>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddDatasetImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    validate_zip_path(zip_path)?;
    if !workspace_root.is_dir() {
        bail!(
            "workspace root does not exist for add package import: {}",
            workspace_root.display()
        );
    }
    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.is_file() {
        bail!(
            "workspace is missing project db for add package import: {}",
            project_db_path.display()
        );
    }

    let mut recorder = ImportProgressWriter::new(on_progress);
    let archive_entry_count = count_zip_entries(zip_path)?;
    recorder.reserve_remaining(archive_entry_count + 8);
    recorder.enable_log(workspace_root)?;
    recorder.record(
        "validate_input",
        format!(
            "add_zip_path={}, workspace_root={}, project_id={}",
            zip_path.display(),
            workspace_root.display(),
            project_id
                .map(|id| id.to_string())
                .unwrap_or_else(|| "-".to_string()),
        ),
    );

    let extract_root = workspace_root
        .join(CACHE_DIR)
        .join(format!("add_import_{}", current_unix_millis_string()));
    fs::create_dir_all(&extract_root).with_context(|| {
        format!(
            "failed to create add package extraction dir {}",
            extract_root.display()
        )
    })?;
    unzip_delivery_to_root(
        zip_path,
        &extract_root,
        &mut |step| recorder.record_step(step),
        should_cancel,
    )?;
    recorder.record(
        "extract_add_package",
        format!("zip extracted to {}", extract_root.display()),
    );

    let manifest = read_add_dataset_manifest(&extract_root)?;
    let payload_root = extract_root.join("gpm_server");
    validate_add_dataset_package(
        &project_db_path,
        workspace_root,
        project_id,
        &manifest,
        &payload_root,
    )?;
    recorder.record(
        "validate_add_manifest",
        format!("dataset_name={}", manifest.dataset_name),
    );
    let should_update_assembly = match project_id {
        Some(project_id) => project_has_assembly_rows(&project_db_path, project_id)?,
        None => false,
    };

    let mut rollback = AddImportRollback::capture(workspace_root, &project_db_path, &payload_root)?;
    let import_result = (|| -> Result<i64> {
        copy_add_payload_into_workspace(&payload_root, workspace_root)?;
        recorder.record(
            "merge_add_payload",
            format!("payload merged into {}", workspace_root.display()),
        );

        let dataset_id = append_catalog_from_add_payload(
            &project_db_path,
            workspace_root,
            &payload_root,
            project_id,
            &manifest,
        )?;
        recorder.record(
            "sync_add_catalog",
            format!(
                "dataset_name={}, dataset_id={dataset_id}",
                manifest.dataset_name
            ),
        );

        if let Some(project_id) = project_id.filter(|_| should_update_assembly) {
            let assembly_summary = crate::project_initializer::append_project_dataset_assembly(
                &project_db_path,
                project_id,
                dataset_id,
            )?;
            recorder.record(
                "append_assembly",
                format!(
                    "dataset_name={}, assembly_seq_count={}, assembly_ctg_count={}",
                    manifest.dataset_name,
                    assembly_summary.assembly_seq_count,
                    assembly_summary.assembly_ctg_count
                ),
            );
        }

        index_add_alignment_payloads(
            &project_db_path,
            workspace_root,
            dataset_id,
            &manifest.dataset_name,
            &mut recorder,
            should_cancel,
        )?;

        if let Some(project_id) = project_id.filter(|_| should_update_assembly) {
            let orient_summary = crate::auto_orientation::auto_orient_contigs_for_dataset(
                &project_db_path,
                project_id,
                dataset_id,
                &crate::auto_orientation::AutoOrientContigsParams::default(),
            )?;
            recorder.record(
                "auto_orient_dataset",
                format!(
                    "dataset_name={}, processed_ctg_count={}, oriented_ctg_count={}, flipped_ctg_count={}",
                    manifest.dataset_name,
                    orient_summary.processed_ctg_count,
                    orient_summary.oriented_ctg_count,
                    orient_summary.flipped_ctg_count
                ),
            );
        }
        Ok(dataset_id)
    })();
    let dataset_id = match import_result {
        Ok(dataset_id) => {
            rollback.disarm()?;
            dataset_id
        }
        Err(error) => {
            if let Err(rollback_error) = rollback.rollback() {
                bail!(
                    "add dataset import failed and rollback failed: {error}; rollback error: {rollback_error}"
                );
            }
            let _ = fs::remove_dir_all(&extract_root);
            return Err(error);
        }
    };
    recorder.record(
        "complete",
        format!(
            "import mode=add_dataset completed dataset={}",
            manifest.dataset_name
        ),
    );

    let _ = fs::remove_dir_all(&extract_root);
    Ok((
        AddDatasetImportOutcome {
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path,
            project_id,
            dataset_id,
            dataset_name: manifest.dataset_name,
        },
        recorder.into_progress(),
    ))
}
