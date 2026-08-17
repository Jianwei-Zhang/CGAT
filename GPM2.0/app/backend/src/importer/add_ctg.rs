use super::*;

pub fn import_add_ctg_package(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)> {
    import_add_ctg_package_with_hooks(
        zip_path,
        workspace_root,
        project_id,
        None,
        &mut |_| {},
        &mut || false,
    )
}

pub fn import_add_ctg_package_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    expected_target: Option<AddCtgImportTarget>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    import_add_ctg_package_internal(
        zip_path,
        workspace_root,
        project_id,
        expected_target,
        on_progress,
        should_cancel,
    )
}

pub(super) fn import_add_ctg_package_internal<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    expected_target: Option<AddCtgImportTarget>,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(AddCtgImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    validate_zip_path(zip_path)?;
    if !workspace_root.is_dir() {
        bail!(
            "workspace root does not exist for add_ctg import: {}",
            workspace_root.display()
        );
    }
    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.is_file() {
        bail!(
            "workspace is missing project db for add_ctg import: {}",
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
            "add_ctg_zip_path={}, workspace_root={}, project_id={project_id}",
            zip_path.display(),
            workspace_root.display(),
        ),
    );

    let extract_root = workspace_root
        .join(CACHE_DIR)
        .join(format!("add_ctg_import_{}", current_unix_millis_string()));
    fs::create_dir_all(&extract_root).with_context(|| {
        format!(
            "failed to create add_ctg package extraction dir {}",
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
        "extract_add_ctg_package",
        format!("zip extracted to {}", extract_root.display()),
    );

    let manifest = read_add_ctg_manifest(&extract_root)?;
    validate_expected_add_ctg_target(&manifest, expected_target.as_ref())?;
    let payload_root = extract_root.join("gpm_server");
    let validated = validate_add_ctg_package(
        &project_db_path,
        workspace_root,
        project_id,
        &manifest,
        &payload_root,
    )?;
    recorder.record(
        "validate_add_ctg_manifest",
        format!(
            "ctg_name={}, target_track={}, target_chr={}",
            manifest.ctg_name, manifest.target_track, manifest.target_chr
        ),
    );
    let should_update_assembly = project_has_assembly_rows(&project_db_path, project_id)?;

    let mut rollback = AddImportRollback::capture(workspace_root, &project_db_path, &payload_root)?;
    let import_result = (|| -> Result<AddCtgImportOutcome> {
        copy_add_ctg_payload_into_workspace(&payload_root, workspace_root)?;
        recorder.record(
            "merge_add_ctg_payload",
            format!("payload merged into {}", workspace_root.display()),
        );

        let catalog = append_catalog_from_add_ctg_payload(
            &project_db_path,
            workspace_root,
            &payload_root,
            project_id,
            &manifest,
            &validated,
        )?;
        recorder.record(
            "sync_add_ctg_catalog",
            format!(
                "ctg_name={}, source_seq_id={}, dataset_id={}",
                manifest.ctg_name, catalog.source_seq_id, catalog.dataset_id
            ),
        );

        let assembly_ctg_id = if should_update_assembly {
            let assembly_ctg_id = append_project_derived_ctg_assembly(
                &project_db_path,
                project_id,
                catalog.source_seq_id,
                &manifest.ctg_name,
                &manifest.target_chr,
                validated.anchor_start,
                &validated.track_member_orders,
            )?;
            recorder.record(
                "append_derived_ctg_assembly",
                format!(
                    "ctg_name={}, assembly_ctg_id={assembly_ctg_id}",
                    manifest.ctg_name
                ),
            );
            Some(assembly_ctg_id)
        } else {
            None
        };

        index_add_ctg_alignment_payloads(
            &project_db_path,
            workspace_root,
            &manifest,
            &catalog,
            project_id,
            &mut recorder,
            should_cancel,
        )?;

        Ok(AddCtgImportOutcome {
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path: project_db_path.clone(),
            project_id,
            dataset_id: catalog.dataset_id,
            source_seq_id: catalog.source_seq_id,
            assembly_ctg_id,
            ctg_name: manifest.ctg_name.clone(),
            target_track: manifest.target_track.clone(),
            target_chr: manifest.target_chr.clone(),
        })
    })();
    let outcome = match import_result {
        Ok(outcome) => {
            rollback.disarm()?;
            outcome
        }
        Err(error) => {
            if let Err(rollback_error) = rollback.rollback() {
                bail!(
                    "add_ctg import failed and rollback failed: {error}; rollback error: {rollback_error}"
                );
            }
            let _ = fs::remove_dir_all(&extract_root);
            return Err(error);
        }
    };

    recorder.record(
        "complete",
        format!("import mode=add_ctg completed ctg={}", manifest.ctg_name),
    );
    let _ = fs::remove_dir_all(&extract_root);
    Ok((outcome, recorder.into_progress()))
}

pub(super) fn validate_expected_add_ctg_target(
    manifest: &AddCtgManifest,
    expected_target: Option<&AddCtgImportTarget>,
) -> Result<()> {
    let Some(expected) = expected_target else {
        return Ok(());
    };
    let expected_chr = expected.target_chr.trim();
    let expected_track = expected.target_track.trim();
    if expected_chr.is_empty() && expected_track.is_empty() {
        return Ok(());
    }
    if manifest.target_chr != expected_chr || manifest.target_track != expected_track {
        bail!(
            "该 add_ctg 包属于 {} / {} 轨道，不能导入到当前 {} / {} 轨道。",
            manifest.target_chr,
            manifest.target_track,
            if expected_chr.is_empty() {
                "-"
            } else {
                expected_chr
            },
            if expected_track.is_empty() {
                "-"
            } else {
                expected_track
            }
        );
    }
    Ok(())
}
