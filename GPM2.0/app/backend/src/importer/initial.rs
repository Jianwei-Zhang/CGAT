use super::*;

pub fn import_from_extracted_bundle(path: &Path) -> Result<(ImportOutcome, Vec<ImportProgress>)> {
    import_from_extracted_bundle_with_hooks(path, &mut |_| {}, &mut || false)
}

pub fn import_from_extracted_bundle_with_hooks<P, C>(
    path: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(ImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut recorder = ImportProgressWriter::new(on_progress);
    recorder.set_phase(1, EXTRACTED_IMPORT_PHASE_TOTAL);
    recorder.record("validate_input", format!("extract_path={}", path.display()));
    recorder.reserve_remaining(6);

    let resolved = resolve_extracted_bundle_workspace(path)?;
    check_import_cancel(should_cancel)?;
    recorder.record(
        "resolve_bundle_root",
        format!(
            "bundle_root={}, workspace_root={}",
            resolved.bundle_root.display(),
            resolved.workspace_root.display()
        ),
    );

    recorder.set_phase(2, EXTRACTED_IMPORT_PHASE_TOTAL);
    recorder.record(
        "validate_grt_contract_start",
        "starting delivery GRT contract validation".to_string(),
    );
    let grt_package = validate_grt_delivery_package_with_progress(
        &resolved.bundle_root,
        &mut |stage, detail| recorder.record(stage, detail.to_string()),
    )?;
    recorder.record(
        "validate_grt_contract",
        "delivery GRT contract validated".to_string(),
    );
    recorder.set_phase(3, EXTRACTED_IMPORT_PHASE_TOTAL);
    let project_db_path = initialize_workspace_layout(&resolved.workspace_root)?;
    recorder.enable_log(&resolved.workspace_root)?;
    check_import_cancel(should_cancel)?;
    sync_catalog_from_bundle(&project_db_path, &resolved.bundle_root, &grt_package)?;
    recorder.record(
        "prepare_workspace",
        format!(
            "workspace prepared: project_db={}",
            project_db_path.display()
        ),
    );

    recorder.set_phase(4, EXTRACTED_IMPORT_PHASE_TOTAL);
    index_alignment_payloads_from_bundle(
        &project_db_path,
        &resolved.bundle_root,
        &mut recorder,
        should_cancel,
    )?;

    recorder.set_phase(5, EXTRACTED_IMPORT_PHASE_TOTAL);
    recorder.record(
        "complete",
        "import mode=extracted_bundle completed".to_string(),
    );

    Ok((
        ImportOutcome {
            mode: ImportMode::ExtractedBundle,
            bundle_root: resolved.bundle_root,
            workspace_root: resolved.workspace_root,
            project_db_path,
        },
        recorder.into_progress(),
    ))
}

pub fn import_from_zip(
    zip_path: &Path,
    workspace_root: &Path,
) -> Result<(ImportOutcome, Vec<ImportProgress>)> {
    import_from_zip_with_hooks(zip_path, workspace_root, &mut |_| {}, &mut || false)
}

pub fn import_from_zip_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(ImportOutcome, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut recorder = ImportProgressWriter::new(on_progress);
    recorder.set_phase(1, ZIP_IMPORT_PHASE_TOTAL);
    recorder.record(
        "validate_input",
        format!(
            "zip_path={}, workspace_root={}",
            zip_path.display(),
            workspace_root.display(),
        ),
    );

    validate_zip_path(zip_path)?;
    let archive_entry_count = count_zip_entries(zip_path)?;
    recorder.reserve_remaining(archive_entry_count + 5);

    recorder.set_phase(2, ZIP_IMPORT_PHASE_TOTAL);
    ensure_workspace_root_can_be_created(workspace_root)?;
    fs::create_dir_all(workspace_root).with_context(|| {
        format!(
            "failed to create workspace root at {}",
            workspace_root.display()
        )
    })?;
    if let Err(error) = recorder.enable_log(workspace_root) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }
    recorder.record(
        "prepare_workspace_root",
        format!("workspace_root={}", workspace_root.display()),
    );

    if let Err(error) = unzip_delivery_to_root(
        zip_path,
        workspace_root,
        &mut |step| recorder.record_step(step),
        should_cancel,
    ) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }
    recorder.record(
        "extract_bundle",
        format!("zip extracted to {}", workspace_root.display()),
    );

    recorder.set_phase(3, ZIP_IMPORT_PHASE_TOTAL);
    let detected_bundle_root = match resolve_bundle_root_dir(workspace_root) {
        Ok(path) => path,
        Err(error) => {
            remove_failed_zip_workspace(workspace_root, &error)?;
            return Err(error);
        }
    };
    if let Err(error) = check_import_cancel(should_cancel) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }
    recorder.record(
        "resolve_bundle_root",
        format!("bundle_root={}", detected_bundle_root.display()),
    );

    if detected_bundle_root != workspace_root {
        if let Err(error) =
            promote_bundle_root_to_workspace_root(workspace_root, &detected_bundle_root)
        {
            remove_failed_zip_workspace(workspace_root, &error)?;
            return Err(error);
        }
        recorder.record(
            "normalize_workspace_layout",
            format!(
                "promoted {} into {}",
                detected_bundle_root.display(),
                workspace_root.display()
            ),
        );
    }

    recorder.set_phase(4, ZIP_IMPORT_PHASE_TOTAL);
    recorder.record(
        "validate_grt_contract_start",
        "starting delivery GRT contract validation".to_string(),
    );
    let grt_package =
        match validate_grt_delivery_package_with_progress(workspace_root, &mut |stage, detail| {
            recorder.record(stage, detail.to_string())
        }) {
            Ok(package) => package,
            Err(error) => {
                remove_failed_zip_workspace(workspace_root, &error)?;
                return Err(error);
            }
        };
    recorder.record(
        "validate_grt_contract",
        "delivery GRT contract validated".to_string(),
    );

    recorder.set_phase(5, ZIP_IMPORT_PHASE_TOTAL);
    let project_db_path = match initialize_workspace_layout(workspace_root) {
        Ok(path) => path,
        Err(error) => {
            remove_failed_zip_workspace(workspace_root, &error)?;
            return Err(error);
        }
    };
    if let Err(error) = check_import_cancel(should_cancel) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }
    if let Err(error) = sync_catalog_from_bundle(&project_db_path, workspace_root, &grt_package) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }
    recorder.record(
        "prepare_workspace",
        format!(
            "workspace prepared: project_db={}",
            project_db_path.display()
        ),
    );

    recorder.set_phase(6, ZIP_IMPORT_PHASE_TOTAL);
    if let Err(error) = index_alignment_payloads_from_bundle(
        &project_db_path,
        workspace_root,
        &mut recorder,
        should_cancel,
    ) {
        remove_failed_zip_workspace(workspace_root, &error)?;
        return Err(error);
    }

    recorder.set_phase(7, ZIP_IMPORT_PHASE_TOTAL);
    recorder.record("complete", "import mode=zip_delivery completed".to_string());

    Ok((
        ImportOutcome {
            mode: ImportMode::ZipDelivery,
            bundle_root: workspace_root.to_path_buf(),
            workspace_root: workspace_root.to_path_buf(),
            project_db_path,
        },
        recorder.into_progress(),
    ))
}

pub(super) fn remove_failed_zip_workspace(
    workspace_root: &Path,
    import_error: &anyhow::Error,
) -> Result<()> {
    fs::remove_dir_all(workspace_root).with_context(|| {
        format!(
            "failed to remove rejected GRT workspace {} after: {import_error:#}",
            workspace_root.display()
        )
    })
}
