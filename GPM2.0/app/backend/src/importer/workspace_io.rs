use super::*;

pub(super) fn path_relative_to(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

pub(super) fn step(stage: &'static str, detail: String) -> ImportProgress {
    ImportProgress {
        stage,
        detail,
        progress_index: None,
        progress_total: None,
        phase_index: None,
        phase_total: None,
    }
}

pub(super) fn current_unix_millis_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

pub(super) fn now_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

pub(super) fn count_zip_entries(zip_path: &Path) -> Result<usize> {
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    Ok(archive.len())
}

pub(super) fn check_import_cancel(should_cancel: &mut impl FnMut() -> bool) -> Result<()> {
    if should_cancel() {
        bail!("import cancelled");
    }
    Ok(())
}

const IMPORT_COPY_BUFFER_BYTES: usize = 64 * 1024;

fn copy_with_import_cancel(
    reader: &mut impl io::Read,
    writer: &mut impl Write,
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<u64> {
    let mut buffer = [0_u8; IMPORT_COPY_BUFFER_BYTES];
    let mut bytes_written = 0_u64;
    loop {
        check_import_cancel(should_cancel)?;
        let bytes_read = reader.read(&mut buffer)?;
        if bytes_read == 0 {
            return Ok(bytes_written);
        }
        writer.write_all(&buffer[..bytes_read])?;
        bytes_written += bytes_read as u64;
    }
}

pub(super) fn validate_zip_path(zip_path: &Path) -> Result<()> {
    if !zip_path.exists() {
        bail!("zip file does not exist: {}", zip_path.display());
    }

    if !zip_path.is_file() {
        bail!("zip path is not a file: {}", zip_path.display());
    }

    let extension = zip_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension != "zip" {
        bail!("expected a .zip file, got: {}", zip_path.display());
    }

    Ok(())
}

pub(super) fn ensure_workspace_root_can_be_created(workspace_root: &Path) -> Result<()> {
    if !workspace_root.exists() {
        return Ok(());
    }

    if !workspace_root.is_dir() {
        bail!(
            "workspace root path exists and is not a directory: {}",
            workspace_root.display()
        );
    }

    let mut entries = fs::read_dir(workspace_root).with_context(|| {
        format!(
            "failed to inspect existing workspace root {}",
            workspace_root.display()
        )
    })?;
    if entries.next().is_some() {
        bail!(
            "workspace root already exists and is not empty: {}",
            workspace_root.display()
        );
    }

    Ok(())
}

pub(super) fn unzip_delivery_to_root(
    zip_path: &Path,
    extract_root: &Path,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let mut archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    let archive_len = archive.len();

    for index in 0..archive_len {
        check_import_cancel(should_cancel)?;
        let mut entry = archive.by_index(index).with_context(|| {
            format!(
                "failed to read zip entry index {} from {}",
                index,
                zip_path.display()
            )
        })?;

        let enclosed = entry.enclosed_name().ok_or_else(|| {
            anyhow::anyhow!("zip entry contains unsafe path traversal: {}", entry.name())
        })?;

        let output_path = extract_root.join(enclosed);
        on_progress(step("extract_entry", entry.name().to_string()));
        if entry.name().ends_with('/') {
            fs::create_dir_all(&output_path).with_context(|| {
                format!(
                    "failed to create extracted directory {}",
                    output_path.display()
                )
            })?;
            continue;
        }

        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create extracted file parent {}",
                    parent.display()
                )
            })?;
        }

        let mut output = File::create(&output_path).with_context(|| {
            format!("failed to create extracted file {}", output_path.display())
        })?;
        copy_with_import_cancel(&mut entry, &mut output, should_cancel).with_context(|| {
            format!(
                "failed to extract zip entry {} to {}",
                entry.name(),
                output_path.display()
            )
        })?;
    }

    Ok(())
}

pub(super) fn promote_bundle_root_to_workspace_root(
    workspace_root: &Path,
    bundle_root: &Path,
) -> Result<()> {
    if bundle_root == workspace_root {
        return Ok(());
    }

    if bundle_root.parent() != Some(workspace_root) {
        bail!(
            "unsupported zip layout: bundle root {} is not a direct child of workspace root {}",
            bundle_root.display(),
            workspace_root.display()
        );
    }

    let entries = fs::read_dir(bundle_root)
        .with_context(|| format!("failed to read bundle root {}", bundle_root.display()))?;
    for entry in entries {
        let entry = entry.with_context(|| {
            format!(
                "failed to read bundle entry under {}",
                bundle_root.display()
            )
        })?;
        let source = entry.path();
        let target = workspace_root.join(entry.file_name());
        if target.exists() {
            bail!(
                "cannot promote bundle entry; target already exists: {}",
                target.display()
            );
        }
        fs::rename(&source, &target).with_context(|| {
            format!(
                "failed to move bundle entry {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }

    fs::remove_dir(bundle_root).with_context(|| {
        format!(
            "failed to remove now-empty promoted bundle root {}",
            bundle_root.display()
        )
    })?;

    Ok(())
}

pub(super) fn initialize_workspace_layout(workspace_root: &Path) -> Result<PathBuf> {
    fs::create_dir_all(workspace_root).with_context(|| {
        format!(
            "failed to create workspace root {}",
            workspace_root.display()
        )
    })?;
    fs::create_dir_all(workspace_root.join(EXPORTS_DIR)).with_context(|| {
        format!(
            "failed to create exports dir under {}",
            workspace_root.display()
        )
    })?;
    fs::create_dir_all(workspace_root.join(CACHE_DIR)).with_context(|| {
        format!(
            "failed to create cache dir under {}",
            workspace_root.display()
        )
    })?;

    let project_db_path = workspace_root.join(PROJECT_DB_NAME);
    if !project_db_path.exists() {
        File::create(&project_db_path).with_context(|| {
            format!(
                "failed to create project db placeholder at {}",
                project_db_path.display()
            )
        })?;
    }

    Ok(project_db_path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn cancellable_copy_stops_between_chunks() {
        let input = vec![7_u8; IMPORT_COPY_BUFFER_BYTES * 3];
        let mut reader = Cursor::new(input);
        let mut output = Vec::new();
        let mut checks = 0;

        let error = copy_with_import_cancel(&mut reader, &mut output, &mut || {
            checks += 1;
            checks > 1
        })
        .expect_err("the second chunk check should cancel the copy");

        assert_eq!(error.to_string(), "import cancelled");
        assert_eq!(checks, 2);
        assert_eq!(output.len(), IMPORT_COPY_BUFFER_BYTES);
    }

    #[test]
    fn cancellable_copy_preserves_complete_output_without_a_request() {
        let input = vec![3_u8; IMPORT_COPY_BUFFER_BYTES + 17];
        let mut reader = Cursor::new(input.clone());
        let mut output = Vec::new();

        let copied = copy_with_import_cancel(&mut reader, &mut output, &mut || false)
            .expect("copy should complete");

        assert_eq!(copied, input.len() as u64);
        assert_eq!(output, input);
    }
}
