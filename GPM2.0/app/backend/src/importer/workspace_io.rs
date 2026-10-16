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
        pairwise: None,
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

fn is_tar_gz(path: &Path) -> bool {
    let name = path.to_string_lossy().to_ascii_lowercase();
    name.ends_with(".tar.gz") || name.ends_with(".tgz")
}

pub(super) fn count_archive_entries(zip_path: &Path) -> Result<Option<usize>> {
    // A tar stream has no central directory. Do not decompress it twice just
    // to count entries; extraction reports progress as entries arrive.
    if is_tar_gz(zip_path) {
        return Ok(None);
    }
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    Ok(Some(archive.len()))
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

pub(super) fn validate_archive_path(zip_path: &Path) -> Result<()> {
    if !zip_path.exists() {
        bail!("archive file does not exist: {}", zip_path.display());
    }

    if !zip_path.is_file() {
        bail!("archive path is not a file: {}", zip_path.display());
    }

    let extension = zip_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension != "zip" && !is_tar_gz(zip_path) {
        bail!(
            "expected a .zip, .tar.gz or .tgz file, got: {}",
            zip_path.display()
        );
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

pub(super) fn extract_delivery_to_root(
    zip_path: &Path,
    extract_root: &Path,
    workers: usize,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    if is_tar_gz(zip_path) {
        if extract_tar_gz_with_system_tar(zip_path, extract_root, on_progress, should_cancel)? {
            return Ok(());
        }
        return extract_tar_gz_to_root(zip_path, extract_root, on_progress, should_cancel);
    }
    extract_zip_to_root(zip_path, extract_root, workers, on_progress, should_cancel)
}
const ZIP_EXTRACT_POLL_INTERVAL: std::time::Duration = std::time::Duration::from_millis(50);
const ZIP_EXTRACT_PROGRESS_QUEUE: usize = 64;

/// One regular-file entry that still has to be written to disk. Directories are
/// created up front by the planner, so workers only ever write disjoint files.
struct PlannedZipEntry {
    archive_index: usize,
    name: String,
    output: PathBuf,
}

enum ZipWorkerEvent {
    Extracted(String),
    /// The failure message itself is carried by the shared error slot so that
    /// the first real error wins instead of whichever event arrives last.
    Failed,
}

fn plan_zip_extraction(zip_path: &Path, extract_root: &Path) -> Result<Vec<PlannedZipEntry>> {
    let file = File::open(zip_path)
        .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
    let mut archive = ZipArchive::new(file)
        .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
    let archive_len = archive.len();
    let mut entries = Vec::new();
    let mut last_claim = HashMap::new();
    for archive_index in 0..archive_len {
        let entry = archive.by_index(archive_index).with_context(|| {
            format!(
                "failed to read zip entry index {} from {}",
                archive_index,
                zip_path.display()
            )
        })?;
        let name = entry.name().to_string();
        let enclosed = entry
            .enclosed_name()
            .ok_or_else(|| anyhow::anyhow!("zip entry contains unsafe path traversal: {name}"))?;
        let output = extract_root.join(enclosed);
        if name.ends_with('/') {
            fs::create_dir_all(&output).with_context(|| {
                format!("failed to create extracted directory {}", output.display())
            })?;
            continue;
        }
        last_claim.insert(output.clone(), entries.len());
        entries.push(PlannedZipEntry {
            archive_index,
            name,
            output,
        });
    }
    // A zip may legally carry several entries for one path. Sequential
    // extraction kept the last one, so only that claimant may be planned:
    // leaving two of them in place would let parallel workers race on the same
    // output file instead of overwriting it in archive order.
    let mut planned = Vec::with_capacity(entries.len());
    for (position, entry) in entries.into_iter().enumerate() {
        if last_claim.get(&entry.output) == Some(&position) {
            planned.push(entry);
        }
    }
    Ok(planned)
}

fn extract_one_zip_entry<C>(
    archive: &mut ZipArchive<File>,
    entry: &PlannedZipEntry,
    should_cancel: &mut C,
) -> Result<()>
where
    C: FnMut() -> bool,
{
    let mut source = archive
        .by_index(entry.archive_index)
        .with_context(|| format!("failed to read zip entry {}", entry.name))?;
    if source.name() != entry.name {
        bail!(
            "zip archive changed while extracting: expected entry {} at index {}",
            entry.name,
            entry.archive_index
        );
    }
    if let Some(parent) = entry.output.parent() {
        fs::create_dir_all(parent).with_context(|| {
            format!(
                "failed to create extracted file parent {}",
                parent.display()
            )
        })?;
    }
    let mut output = File::create(&entry.output)
        .with_context(|| format!("failed to create extracted file {}", entry.output.display()))?;
    copy_with_import_cancel(&mut source, &mut output, should_cancel).with_context(|| {
        format!(
            "failed to extract zip entry {} to {}",
            entry.name,
            entry.output.display()
        )
    })?;
    Ok(())
}

fn extract_zip_to_root(
    zip_path: &Path,
    extract_root: &Path,
    workers: usize,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    let planned = plan_zip_extraction(zip_path, extract_root)?;
    if planned.is_empty() {
        return Ok(());
    }
    check_import_cancel(should_cancel)?;
    let worker_count = workers.min(planned.len());
    if worker_count <= 1 {
        let file = File::open(zip_path)
            .with_context(|| format!("failed to open zip: {}", zip_path.display()))?;
        let mut archive = ZipArchive::new(file)
            .with_context(|| format!("failed to read zip archive: {}", zip_path.display()))?;
        for entry in &planned {
            check_import_cancel(should_cancel)?;
            on_progress(step("extract_entry", entry.name.clone()));
            extract_one_zip_entry(&mut archive, entry, should_cancel)?;
        }
        return Ok(());
    }
    extract_zip_entries_in_parallel(
        zip_path,
        planned,
        worker_count,
        ZIP_EXTRACT_POLL_INTERVAL,
        on_progress,
        should_cancel,
    )
}

fn extract_zip_entries_in_parallel(
    zip_path: &Path,
    planned: Vec<PlannedZipEntry>,
    worker_count: usize,
    poll_interval: std::time::Duration,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    use std::sync::atomic::Ordering;
    use std::sync::{Arc, Mutex};

    let planned = Arc::new(planned);
    let next = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let cancelled = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let first_error = Arc::new(Mutex::new(None::<String>));
    let (sender, receiver) =
        std::sync::mpsc::sync_channel::<ZipWorkerEvent>(ZIP_EXTRACT_PROGRESS_QUEUE);
    let mut handles = Vec::with_capacity(worker_count);
    for worker_index in 0..worker_count {
        let planned = Arc::clone(&planned);
        let next = Arc::clone(&next);
        let cancelled = Arc::clone(&cancelled);
        let first_error = Arc::clone(&first_error);
        let sender = sender.clone();
        let zip_path = zip_path.to_path_buf();
        handles.push(
            std::thread::Builder::new()
                .name(format!("zip-extract-{}", worker_index + 1))
                .spawn(move || {
                    let run = || -> Result<()> {
                        let file = File::open(&zip_path)?;
                        let mut archive = ZipArchive::new(file)?;
                        loop {
                            if cancelled.load(Ordering::Acquire) {
                                return Ok(());
                            }
                            let index = next.fetch_add(1, Ordering::AcqRel);
                            if index >= planned.len() {
                                return Ok(());
                            }
                            let entry = &planned[index];
                            extract_one_zip_entry(&mut archive, entry, &mut || {
                                cancelled.load(Ordering::Acquire)
                            })?;
                            if sender
                                .send(ZipWorkerEvent::Extracted(entry.name.clone()))
                                .is_err()
                            {
                                return Ok(());
                            }
                        }
                    };
                    if let Err(error) = run() {
                        // The first failing worker owns the reported error. A
                        // sibling that only stops because this worker already
                        // cancelled the batch must not mask the root cause with
                        // its own "import cancelled" noise.
                        if !cancelled.swap(true, Ordering::AcqRel) {
                            let message = format!("{error:#}");
                            if let Ok(mut slot) = first_error.lock() {
                                *slot = Some(message);
                            }
                            let _ = sender.send(ZipWorkerEvent::Failed);
                        }
                    }
                })
                .context("failed to spawn zip extraction worker")?,
        );
    }
    drop(sender);

    loop {
        // A quiet period only means "no entry finished yet": treating it like a
        // closed channel would end the batch early and silently drop the
        // entries that are still being written.
        match receiver.recv_timeout(poll_interval) {
            Ok(ZipWorkerEvent::Extracted(name)) => on_progress(step("extract_entry", name)),
            Ok(ZipWorkerEvent::Failed) => cancelled.store(true, Ordering::Release),
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
        }
        if should_cancel() {
            cancelled.store(true, Ordering::Release);
        }
    }
    cancelled.store(true, Ordering::Release);

    for handle in handles {
        if handle.join().is_err() {
            let mut slot = first_error.lock().expect("zip worker error slot");
            if slot.is_none() {
                *slot = Some("zip extraction worker panicked".to_string());
            }
        }
    }
    if let Some(message) = first_error.lock().expect("zip worker error slot").take() {
        return Err(anyhow::anyhow!("{message}"));
    }
    check_import_cancel(should_cancel)?;
    Ok(())
}

const NATIVE_TAR_POLL_INTERVAL: std::time::Duration = std::time::Duration::from_millis(50);
const NATIVE_TAR_STDERR_LIMIT: usize = 64 * 1024;

fn native_tar_executable() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        let root = std::env::var_os("SystemRoot")?;
        let path = PathBuf::from(root).join("System32").join("tar.exe");
        return path.is_file().then_some(path);
    }
    #[cfg(target_os = "macos")]
    {
        let path = PathBuf::from("/usr/bin/tar");
        return path.is_file().then_some(path);
    }
    #[allow(unreachable_code)]
    None
}

fn configure_native_tar_command(_command: &mut std::process::Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        _command.creation_flags(CREATE_NO_WINDOW);
    }
}

fn validate_native_extracted_tree(root: &Path) -> Result<()> {
    let canonical_root = root
        .canonicalize()
        .with_context(|| format!("failed to resolve extracted root {}", root.display()))?;
    let mut pending = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(&directory).with_context(|| {
            format!(
                "failed to inspect extracted directory {}",
                directory.display()
            )
        })? {
            let entry = entry?;
            let path = entry.path();
            let relative = path.strip_prefix(root).unwrap_or(&path);
            if relative.components().any(|component| match component {
                Component::Normal(name) => {
                    let name = name.to_string_lossy();
                    name.contains('\\') || name.contains(':')
                }
                Component::CurDir => false,
                _ => true,
            }) {
                bail!("system tar produced an unsafe path: {}", relative.display());
            }
            let metadata = fs::symlink_metadata(&path)?;
            let file_type = metadata.file_type();
            if file_type.is_symlink() || (!file_type.is_file() && !file_type.is_dir()) {
                bail!(
                    "system tar produced an unsupported entry type: {}",
                    relative.display()
                );
            }
            let canonical = path
                .canonicalize()
                .with_context(|| format!("failed to resolve extracted path {}", path.display()))?;
            if !canonical.starts_with(&canonical_root) {
                bail!(
                    "system tar extracted outside the workspace: {}",
                    path.display()
                );
            }
            if file_type.is_dir() {
                pending.push(path);
            }
        }
    }
    Ok(())
}

const NATIVE_TAR_ENTRY_QUEUE: usize = 64;

/// GNU tar prints one bare path per processed entry on stdout.
fn native_tar_entry_label(line: &str) -> Option<String> {
    let trimmed = line.trim_end_matches(['\r', '\n']).trim();
    if trimmed.is_empty() {
        return None;
    }
    let name = trimmed
        .strip_prefix("x ")
        .or_else(|| trimmed.strip_prefix("a "))
        .unwrap_or(trimmed)
        .trim();
    (!name.is_empty()).then(|| name.to_string())
}

/// bsdtar reports verbose extraction on stderr, prefixed with its operation
/// marker. Only marked lines are entries; everything else is a diagnostic.
fn native_tar_marked_entry_label(line: &str) -> Option<String> {
    let trimmed = line.trim_end_matches(['\r', '\n']).trim();
    let name = trimmed
        .strip_prefix("x ")
        .or_else(|| trimmed.strip_prefix("a "))?;
    let name = name.trim();
    (!name.is_empty()).then(|| name.to_string())
}

/// Reads entry names from stdout and splits stderr into entry names plus a
/// bounded diagnostic tail, so the caller can report per-entry progress while
/// still surfacing extractor errors.
fn spawn_native_tar_readers(
    stdout: Option<std::process::ChildStdout>,
    stderr: Option<std::process::ChildStderr>,
    entry_sender: std::sync::mpsc::SyncSender<String>,
) -> (
    std::thread::JoinHandle<()>,
    std::thread::JoinHandle<Vec<u8>>,
) {
    let stdout_entries = entry_sender.clone();
    let stdout_handle = std::thread::spawn(move || {
        let Some(stdout) = stdout else {
            return;
        };
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else {
                break;
            };
            let Some(label) = native_tar_entry_label(&line) else {
                continue;
            };
            if stdout_entries.send(label).is_err() {
                break;
            }
        }
    });
    let stderr_handle = std::thread::spawn(move || {
        let mut diagnostics = Vec::new();
        let Some(stderr) = stderr else {
            return diagnostics;
        };
        let mut reader = BufReader::new(stderr);
        let mut buffer = Vec::new();
        loop {
            buffer.clear();
            match reader.read_until(b'\n', &mut buffer) {
                Ok(0) => break,
                Ok(_) => {}
                Err(_) => break,
            }
            let text = String::from_utf8_lossy(&buffer);
            if let Some(label) = native_tar_marked_entry_label(&text) {
                if entry_sender.send(label).is_err() {
                    break;
                }
                continue;
            }
            let remaining = NATIVE_TAR_STDERR_LIMIT.saturating_sub(diagnostics.len());
            if remaining == 0 {
                continue;
            }
            diagnostics.extend_from_slice(&text.as_bytes()[..text.len().min(remaining)]);
        }
        diagnostics
    });
    (stdout_handle, stderr_handle)
}

/// Drain progress while polling cancellation and exit on every iteration.
/// Keep draining after process exit so bounded reader queues cannot block joins.
fn wait_for_native_tar_entries(
    entries: &std::sync::mpsc::Receiver<String>,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
    mut poll_exit: impl FnMut() -> io::Result<bool>,
) -> Result<()> {
    let mut exited = false;
    loop {
        let disconnected = match entries.recv_timeout(NATIVE_TAR_POLL_INTERVAL) {
            Ok(label) => {
                on_progress(step("extract_entry", label));
                false
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => false,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => true,
        };
        check_import_cancel(should_cancel)?;
        if !exited {
            exited = poll_exit().context("failed to poll system tar extractor")?;
        }
        if exited && disconnected {
            return Ok(());
        }
        if disconnected {
            // A process may close both pipes before it actually exits.
            std::thread::sleep(NATIVE_TAR_POLL_INTERVAL);
        }
    }
}

fn extract_tar_gz_with_system_tar(
    path: &Path,
    extract_root: &Path,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<bool> {
    let Some(executable) = native_tar_executable() else {
        return Ok(false);
    };
    check_import_cancel(should_cancel)?;
    on_progress(step(
        "extract_native_archive",
        format!("extractor={}", executable.display()),
    ));
    let mut command = std::process::Command::new(&executable);
    command
        .arg("-x")
        .arg("-k")
        .arg("-m")
        .arg("-f")
        .arg(path)
        .arg("-C")
        .arg(extract_root)
        // Verbose extraction reports every entry on stdout, which is how the
        // dialog keeps entry level feedback while the system tar works.
        .arg("-v")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    configure_native_tar_command(&mut command);
    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(error) => {
            return Err(error).with_context(|| {
                format!(
                    "failed to start system tar extractor {}",
                    executable.display()
                )
            });
        }
    };
    let (entry_sender, entry_receiver) =
        std::sync::mpsc::sync_channel::<String>(NATIVE_TAR_ENTRY_QUEUE);
    let (entry_reader, stderr_handle) =
        spawn_native_tar_readers(child.stdout.take(), child.stderr.take(), entry_sender);
    let mut status = None;
    let result = wait_for_native_tar_entries(&entry_receiver, on_progress, should_cancel, || {
        status = child.try_wait()?;
        Ok(status.is_some())
    });
    // On cancellation/error, unblock any reader waiting on a full progress
    // queue before joining it. On success the queue has already been drained.
    drop(entry_receiver);
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    let _ = entry_reader.join();
    let stderr = stderr_handle.join().unwrap_or_default();
    result?;
    let status = status.context("system tar exited without an exit status")?;
    if !status.success() {
        let detail = String::from_utf8_lossy(&stderr).trim().to_string();
        bail!(
            "system tar extraction failed with status {}{}",
            status,
            if detail.is_empty() {
                String::new()
            } else {
                format!(": {detail}")
            }
        );
    }
    check_import_cancel(should_cancel)?;
    validate_native_extracted_tree(extract_root)?;
    Ok(true)
}

fn extract_tar_gz_to_root(
    path: &Path,
    extract_root: &Path,
    on_progress: &mut impl FnMut(ImportProgress),
    should_cancel: &mut impl FnMut() -> bool,
) -> Result<()> {
    let file =
        File::open(path).with_context(|| format!("failed to open archive: {}", path.display()))?;
    let mut archive = tar::Archive::new(flate2::read::MultiGzDecoder::new(file));
    let mut seen = HashSet::new();
    for entry in archive.entries()? {
        check_import_cancel(should_cancel)?;
        let mut entry = entry.context("failed to read tar entry")?;
        let relative = entry.path()?.into_owned();
        if relative.as_os_str().is_empty()
            || relative.components().any(|component| match component {
                Component::Normal(name) => {
                    let name = name.to_string_lossy();
                    name.contains('\\') || name.contains(':')
                }
                Component::CurDir => false,
                _ => true,
            })
        {
            bail!(
                "tar entry contains unsafe path traversal: {}",
                relative.display()
            );
        }
        if !seen.insert(relative.clone()) {
            bail!("duplicate tar entry: {}", relative.display());
        }
        let kind = entry.header().entry_type();
        if !kind.is_dir() && !kind.is_file() {
            bail!("unsupported tar entry type: {}", relative.display());
        }
        let output = extract_root.join(&relative);
        on_progress(step(
            "extract_entry",
            relative.to_string_lossy().into_owned(),
        ));
        if kind.is_dir() {
            fs::create_dir_all(&output)?;
        } else {
            if let Some(parent) = output.parent() {
                fs::create_dir_all(parent)?;
            }
            let mut writer = File::create(&output)?;
            copy_with_import_cancel(&mut entry, &mut writer, should_cancel)?;
        }
    }
    // Consume padding and the gzip trailer so truncation/CRC errors cannot
    // produce an apparently successful imported workspace.
    let mut stream = archive.into_inner();
    copy_with_import_cancel(&mut stream, &mut io::sink(), should_cancel)?;
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
            "unsupported archive layout: bundle root {} is not a direct child of workspace root {}",
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

    fn write_test_zip(path: &Path, entries: &[(&str, &[u8])]) {
        let mut zip = zip::ZipWriter::new(File::create(path).unwrap());
        let options =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, bytes) in entries {
            if name.ends_with('/') {
                zip.add_directory(*name, options).unwrap();
                continue;
            }
            zip.start_file(*name, options).unwrap();
            zip.write_all(bytes).unwrap();
        }
        zip.finish().unwrap();
    }

    fn synthetic_entries(count: usize) -> Vec<(String, Vec<u8>)> {
        (0..count)
            .map(|index| {
                let bytes = if index == 0 {
                    Vec::new()
                } else {
                    let mut bytes = vec![0_u8; index * 4096];
                    for (offset, byte) in bytes.iter_mut().enumerate() {
                        *byte = (offset as u8).wrapping_mul(31).wrapping_add(index as u8);
                    }
                    bytes
                };
                (
                    format!("gpm_server/data/partitions/chr/ref/part_{index:03}.fa"),
                    bytes,
                )
            })
            .collect()
    }

    fn extract_zip_fixture(
        zip_path: &Path,
        root: &Path,
        workers: usize,
    ) -> Result<Vec<ImportProgress>> {
        if !root.exists() {
            fs::create_dir_all(root).unwrap();
        }
        let mut steps = Vec::new();
        extract_delivery_to_root(
            zip_path,
            root,
            workers,
            &mut |step| steps.push(step),
            &mut || false,
        )?;
        Ok(steps)
    }

    fn assert_fixture_tree(root: &Path, entries: &[(String, Vec<u8>)]) {
        for (name, bytes) in entries {
            let extracted = fs::read(root.join(name)).unwrap_or_else(|error| {
                panic!("missing extracted entry {name}: {error}");
            });
            assert_eq!(&extracted, bytes, "entry {name} differs");
        }
    }

    #[test]
    fn parallel_zip_extraction_matches_the_sequential_extraction() {
        let temp = tempfile::tempdir().unwrap();
        let entries = synthetic_entries(24);
        let borrowed = entries
            .iter()
            .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
            .collect::<Vec<_>>();
        let zip_path = temp.path().join("bundle.zip");
        write_test_zip(&zip_path, &borrowed);

        let parallel_root = temp.path().join("parallel");
        let steps = extract_zip_fixture(&zip_path, &parallel_root, 8).unwrap();
        assert_fixture_tree(&parallel_root, &entries);
        assert_eq!(
            steps
                .iter()
                .filter(|step| step.stage == "extract_entry")
                .count(),
            entries.len()
        );

        let sequential_root = temp.path().join("sequential");
        extract_zip_fixture(&zip_path, &sequential_root, 1).unwrap();
        assert_fixture_tree(&sequential_root, &entries);
    }

    #[test]
    fn parallel_zip_extraction_keeps_the_last_duplicate_entry() {
        let temp = tempfile::tempdir().unwrap();
        let zip_path = temp.path().join("duplicate.zip");
        write_test_zip(
            &zip_path,
            &[
                ("gpm_server/a.fa", b"first"),
                ("gpm_server/a.fa", b"second"),
            ],
        );
        let root = temp.path().join("out");

        let steps = extract_zip_fixture(&zip_path, &root, 4).unwrap();

        assert_eq!(
            steps
                .iter()
                .filter(|step| step.stage == "extract_entry")
                .count(),
            1,
            "a path must be planned exactly once"
        );
        assert_eq!(fs::read(root.join("gpm_server/a.fa")).unwrap(), b"second");
    }

    #[test]
    fn parallel_zip_extraction_rejects_traversal_entries() {
        let temp = tempfile::tempdir().unwrap();
        let zip_path = temp.path().join("traversal.zip");
        write_test_zip(
            &zip_path,
            &[("gpm_server/ok.fa", b"ok"), ("../escape.fa", b"escape")],
        );
        let root = temp.path().join("out");

        let error = extract_zip_fixture(&zip_path, &root, 4).unwrap_err();

        assert!(
            error.to_string().contains("unsafe path traversal"),
            "unexpected error: {error}"
        );
        assert!(!temp.path().join("escape.fa").exists());
    }

    #[test]
    fn parallel_zip_extraction_stops_workers_on_cancel() {
        let temp = tempfile::tempdir().unwrap();
        let entries = synthetic_entries(32);
        let borrowed = entries
            .iter()
            .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
            .collect::<Vec<_>>();
        let zip_path = temp.path().join("cancel.zip");
        write_test_zip(&zip_path, &borrowed);
        let root = temp.path().join("out");
        fs::create_dir_all(&root).unwrap();

        let extracted = std::cell::Cell::new(0_usize);
        let error = extract_delivery_to_root(
            &zip_path,
            &root,
            4,
            &mut |step| {
                if step.stage == "extract_entry" {
                    extracted.set(extracted.get() + 1);
                }
            },
            &mut || extracted.get() >= 3,
        )
        .unwrap_err();

        assert!(
            error.to_string().contains("cancelled"),
            "unexpected error: {error}"
        );
        assert!(extracted.get() < entries.len());
    }

    #[test]
    fn parallel_zip_extraction_propagates_worker_write_failures() {
        let temp = tempfile::tempdir().unwrap();
        let entries = synthetic_entries(6);
        let borrowed = entries
            .iter()
            .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
            .collect::<Vec<_>>();
        let zip_path = temp.path().join("blocked.zip");
        write_test_zip(&zip_path, &borrowed);
        let root = temp.path().join("out");
        // A directory where a file has to be written makes the worker's file
        // creation fail instead of racing with another worker.
        let blocked = root.join(&entries[3].0);
        fs::create_dir_all(&blocked).unwrap();

        let error = extract_zip_fixture(&zip_path, &root, 4).unwrap_err();

        assert!(
            error.to_string().contains("part_003.fa"),
            "unexpected error: {error}"
        );
    }

    #[test]
    fn parallel_zip_extraction_waits_out_quiet_periods_without_events() {
        let temp = tempfile::tempdir().unwrap();
        let entries = synthetic_entries(24);
        let borrowed = entries
            .iter()
            .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
            .collect::<Vec<_>>();
        let zip_path = temp.path().join("quiet.zip");
        write_test_zip(&zip_path, &borrowed);
        let root = temp.path().join("out");
        fs::create_dir_all(&root).unwrap();

        let planned = plan_zip_extraction(&zip_path, &root).unwrap();
        // A zero poll interval turns every quiet period into a timeout, which is
        // exactly what a loaded machine produces. Extraction must still wait for
        // the workers instead of reporting a truncated batch as complete.
        extract_zip_entries_in_parallel(
            &zip_path,
            planned,
            4,
            std::time::Duration::ZERO,
            &mut |_| {},
            &mut || false,
        )
        .unwrap();

        assert_fixture_tree(&root, &entries);
    }

    #[test]
    fn native_tar_continuous_progress_does_not_starve_cancellation() {
        let (sender, receiver) = std::sync::mpsc::sync_channel(NATIVE_TAR_ENTRY_QUEUE);
        // Prefill the bounded queue: every initial receive is immediately ready.
        for index in 0..NATIVE_TAR_ENTRY_QUEUE {
            sender.send(format!("file-{index}")).unwrap();
        }
        let emitted = std::cell::Cell::new(0);
        let polls = std::cell::Cell::new(0);
        let error = wait_for_native_tar_entries(
            &receiver,
            &mut |_| emitted.set(emitted.get() + 1),
            &mut || emitted.get() >= 3,
            || {
                polls.set(polls.get() + 1);
                Ok(false)
            },
        )
        .expect_err("cancel must be checked even when progress is always ready");
        assert!(error.to_string().contains("cancelled"));
        assert_eq!(emitted.get(), 3);
        assert_eq!(polls.get(), 2);
    }

    #[test]
    fn native_tar_exit_drains_more_than_one_queue_before_joining_readers() {
        let (sender, receiver) = std::sync::mpsc::sync_channel(NATIVE_TAR_ENTRY_QUEUE);
        let count = NATIVE_TAR_ENTRY_QUEUE * 4;
        let reader = std::thread::spawn(move || {
            for index in 0..count {
                if sender.send(format!("file-{index}")).is_err() {
                    break;
                }
            }
        });
        let mut emitted = 0;
        wait_for_native_tar_entries(&receiver, &mut |_| emitted += 1, &mut || false, || Ok(true))
            .expect("already exited process must still drain all buffered entries");
        reader.join().unwrap();
        assert_eq!(emitted, count);
    }

    #[test]
    fn native_tar_verbose_lines_become_entry_labels() {
        assert_eq!(
            native_tar_entry_label("x gpm_server/data/datasets/ds.fa").as_deref(),
            Some("gpm_server/data/datasets/ds.fa")
        );
        assert_eq!(
            native_tar_entry_label("gpm_server/data/datasets/ds.fa\r").as_deref(),
            Some("gpm_server/data/datasets/ds.fa")
        );
        assert_eq!(native_tar_entry_label("x ./").as_deref(), Some("./"));
        assert_eq!(
            native_tar_marked_entry_label("x gpm_server/metadata/reference.tsv").as_deref(),
            Some("gpm_server/metadata/reference.tsv")
        );
        assert_eq!(
            native_tar_marked_entry_label("tar: Error exit delayed"),
            None
        );
        assert_eq!(native_tar_marked_entry_label("gpm_server/top.txt"), None);
        assert_eq!(native_tar_entry_label("   "), None);
        assert_eq!(native_tar_entry_label(""), None);
    }
}
