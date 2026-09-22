use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use rusqlite::{Transaction, params};

use crate::db::open_workspace_db;

const REQUIRED_BUNDLE_ROOT_PATHS: &[&str] = &[
    "metadata/reference.tsv",
    "metadata/datasets.tsv",
    "data/reference",
    "data/datasets",
    "runs",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractedBundleWorkspace {
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CopiedProjectWorkspace {
    pub workspace_root: PathBuf,
    pub project_name: String,
    pub copy_index: usize,
    pub project_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectCopyDefaults {
    pub project_name: String,
    pub target_root: PathBuf,
    pub copy_index: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectCopyProgress {
    pub stage: &'static str,
    pub detail: String,
    pub completed_bytes: u64,
    pub total_bytes: u64,
    pub completed_files: u64,
    pub total_files: u64,
    pub cancellable: bool,
}

#[derive(Debug, Default, Clone, Copy)]
struct ProjectCopyStats {
    bytes: u64,
    files: u64,
}

const COPY_PROGRESS_BYTE_STEP: u64 = 8 * 1024 * 1024;

pub fn get_project_copy_defaults(source_root: &Path) -> Result<ProjectCopyDefaults> {
    validate_project_copy_source(source_root)?;
    let projects = read_source_projects(source_root)?;
    let (target_root, copy_index) = next_copy_target(source_root)?;
    Ok(ProjectCopyDefaults {
        project_name: format!("{}-copy{copy_index}", projects[0].1),
        target_root,
        copy_index,
    })
}

/// Copy a complete project workspace beside its source as `<directory>-copyN`.
/// Every project name in the copied database receives the same suffix.
pub fn copy_project_workspace(source_root: &Path) -> Result<CopiedProjectWorkspace> {
    let defaults = get_project_copy_defaults(source_root)?;
    let mut copied = copy_project_workspace_to_with_hooks(
        source_root,
        &defaults.target_root,
        &defaults.project_name,
        &mut |_| {},
        &mut || false,
    )?;
    copied.copy_index = defaults.copy_index;
    Ok(copied)
}

pub fn copy_project_workspace_to_with_hooks<P, C>(
    source_root: &Path,
    target_root: &Path,
    project_name: &str,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<CopiedProjectWorkspace>
where
    P: FnMut(ProjectCopyProgress),
    C: FnMut() -> bool,
{
    emit_copy_progress(
        on_progress,
        "validating",
        "",
        ProjectCopyStats::default(),
        ProjectCopyStats::default(),
        true,
    );
    validate_project_copy_source(source_root)?;
    validate_project_copy_target(source_root, target_root, project_name)?;
    ensure_copy_not_cancelled(should_cancel)?;

    let source_db = source_root.join("project.sqlite");
    let projects = read_source_projects(source_root)?;
    let conn = open_workspace_db(&source_db)?;
    conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
        .context("failed to checkpoint source project database")?;
    drop(conn);

    emit_copy_progress(
        on_progress,
        "scanning",
        "",
        ProjectCopyStats::default(),
        ProjectCopyStats::default(),
        true,
    );
    let totals = scan_directory_contents(source_root, should_cancel)?;
    ensure_copy_not_cancelled(should_cancel)?;
    fs::create_dir(target_root).with_context(|| {
        format!(
            "failed to create copied workspace {}",
            target_root.display()
        )
    })?;
    let copy_result = (|| {
        let mut completed = ProjectCopyStats::default();
        let mut last_reported_bytes = 0_u64;
        copy_directory_contents_with_hooks(
            source_root,
            target_root,
            source_root,
            target_root,
            totals,
            &mut completed,
            &mut last_reported_bytes,
            on_progress,
            should_cancel,
        )?;
        ensure_copy_not_cancelled(should_cancel)?;
        emit_copy_progress(on_progress, "finalizing", "", completed, totals, false);
        let target_db = target_root.join("project.sqlite");
        let mut copied_conn = open_workspace_db(&target_db)?;
        let tx = copied_conn
            .transaction()
            .context("failed to start copied project rename transaction")?;
        rebase_workspace_paths(&tx, source_root, target_root)?;
        for (index, (project_id, source_project_name)) in projects.iter().enumerate() {
            let copied_name = if index == 0 {
                project_name.trim().to_string()
            } else {
                format!("{source_project_name}-copy")
            };
            let changed = tx.execute(
                "UPDATE project SET name = ?1 WHERE id = ?2",
                params![copied_name, project_id],
            )?;
            if changed != 1 {
                bail!("failed to rename copied project id {project_id}");
            }
        }
        tx.commit()
            .context("failed to commit copied project names")?;
        emit_copy_progress(on_progress, "verifying", "", completed, totals, false);
        let verification = open_workspace_db(&target_db)?;
        let copied_project_count: i64 =
            verification.query_row("SELECT COUNT(*) FROM project", [], |row| row.get(0))?;
        if copied_project_count != projects.len() as i64 {
            bail!("copied project verification failed");
        }
        emit_copy_progress(on_progress, "complete", "", totals, totals, false);
        Ok(())
    })();

    if let Err(error) = copy_result {
        let _ = fs::remove_dir_all(target_root);
        return Err(error);
    }

    Ok(CopiedProjectWorkspace {
        workspace_root: target_root.to_path_buf(),
        project_name: project_name.trim().to_string(),
        copy_index: 0,
        project_count: projects.len(),
    })
}

fn emit_copy_progress<P: FnMut(ProjectCopyProgress)>(
    on_progress: &mut P,
    stage: &'static str,
    detail: &str,
    completed: ProjectCopyStats,
    totals: ProjectCopyStats,
    cancellable: bool,
) {
    on_progress(ProjectCopyProgress {
        stage,
        detail: detail.to_string(),
        completed_bytes: completed.bytes,
        total_bytes: totals.bytes,
        completed_files: completed.files,
        total_files: totals.files,
        cancellable,
    });
}

fn validate_project_copy_source(source_root: &Path) -> Result<()> {
    if !source_root.exists() {
        bail!("workspace root does not exist: {}", source_root.display());
    }
    if !source_root.is_dir() {
        bail!(
            "workspace root is not a directory: {}",
            source_root.display()
        );
    }
    let source_db = source_root.join("project.sqlite");
    if !source_db.is_file() {
        bail!("workspace missing project.sqlite: {}", source_db.display());
    }
    Ok(())
}

fn validate_project_copy_target(
    source_root: &Path,
    target_root: &Path,
    project_name: &str,
) -> Result<()> {
    if project_name.trim().is_empty() {
        bail!("project name must not be empty");
    }
    if target_root.as_os_str().is_empty() {
        bail!("target workspace path must not be empty");
    }
    if target_root.exists() {
        bail!("target workspace already exists: {}", target_root.display());
    }
    let parent = target_root.parent().ok_or_else(|| {
        anyhow::anyhow!("target workspace has no parent: {}", target_root.display())
    })?;
    if !parent.is_dir() {
        bail!(
            "target parent directory does not exist: {}",
            parent.display()
        );
    }
    let canonical_source = source_root.canonicalize().with_context(|| {
        format!(
            "failed to resolve source workspace {}",
            source_root.display()
        )
    })?;
    let canonical_parent = parent
        .canonicalize()
        .with_context(|| format!("failed to resolve target parent {}", parent.display()))?;
    let target_name = target_root.file_name().ok_or_else(|| {
        anyhow::anyhow!(
            "target workspace has no directory name: {}",
            target_root.display()
        )
    })?;
    let resolved_target = canonical_parent.join(target_name);
    if resolved_target == canonical_source {
        bail!("target workspace must differ from source workspace");
    }
    if resolved_target.starts_with(&canonical_source) {
        bail!("target workspace must not be inside source workspace");
    }
    Ok(())
}

fn read_source_projects(source_root: &Path) -> Result<Vec<(i64, String)>> {
    let conn = open_workspace_db(&source_root.join("project.sqlite"))?;
    let mut statement = conn
        .prepare("SELECT id, name FROM project ORDER BY id")
        .context("failed to read source project names")?;
    let projects = statement
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    if projects.is_empty() {
        bail!(
            "workspace has no project to copy: {}",
            source_root.display()
        );
    }
    Ok(projects)
}

fn rebase_workspace_paths(
    tx: &Transaction<'_>,
    source_root: &Path,
    target_root: &Path,
) -> Result<()> {
    const PATH_COLUMNS: &[(&str, &str)] = &[
        ("reference_genome", "fasta_path"),
        ("reference_genome", "fai_path"),
        ("dataset", "fasta_path"),
        ("dataset", "fai_path"),
        ("reference_chr_locator", "fasta_path"),
        ("source_seq_locator", "fasta_path"),
        ("pairwise_alignment_run", "paf_path"),
        ("export_record", "output_path"),
    ];

    for (table, column) in PATH_COLUMNS {
        let select_sql = format!("SELECT rowid, {column} FROM {table}");
        let rows = {
            let mut statement = tx.prepare(&select_sql).with_context(|| {
                format!("failed to read copied workspace path column {table}.{column}")
            })?;
            statement
                .query_map([], |row| {
                    Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
                })?
                .collect::<rusqlite::Result<Vec<_>>>()?
        };
        let update_sql = format!("UPDATE {table} SET {column} = ?1 WHERE rowid = ?2");
        for (row_id, stored_path) in rows {
            let stored = Path::new(&stored_path);
            let Ok(relative_path) = stored.strip_prefix(source_root) else {
                continue;
            };
            let copied_path = target_root.join(relative_path);
            tx.execute(&update_sql, params![copied_path.to_string_lossy(), row_id])
                .with_context(|| {
                    format!("failed to rebase copied workspace path {table}.{column}")
                })?;
        }
    }
    Ok(())
}

fn next_copy_target(source_root: &Path) -> Result<(PathBuf, usize)> {
    let parent = source_root.parent().ok_or_else(|| {
        anyhow::anyhow!(
            "workspace root has no parent directory: {}",
            source_root.display()
        )
    })?;
    let source_name = source_root.file_name().ok_or_else(|| {
        anyhow::anyhow!(
            "workspace root has no directory name: {}",
            source_root.display()
        )
    })?;
    for copy_index in 1..=usize::MAX {
        let mut target_name = OsString::from(source_name);
        target_name.push(format!("-copy{copy_index}"));
        let target_root = parent.join(target_name);
        if !target_root.exists() {
            return Ok((target_root, copy_index));
        }
    }
    unreachable!("usize copy index space exhausted")
}

fn ensure_copy_not_cancelled<C: FnMut() -> bool>(should_cancel: &mut C) -> Result<()> {
    if should_cancel() {
        bail!("PROJECT_COPY_CANCELLED");
    }
    Ok(())
}

fn is_transient_sqlite_file(path: &Path) -> bool {
    matches!(
        path.file_name().and_then(|name| name.to_str()),
        Some("project.sqlite-wal" | "project.sqlite-shm")
    )
}

fn scan_directory_contents<C: FnMut() -> bool>(
    source: &Path,
    should_cancel: &mut C,
) -> Result<ProjectCopyStats> {
    ensure_copy_not_cancelled(should_cancel)?;
    let mut stats = ProjectCopyStats::default();
    for entry in fs::read_dir(source)
        .with_context(|| format!("failed to read workspace directory {}", source.display()))?
    {
        ensure_copy_not_cancelled(should_cancel)?;
        let entry = entry?;
        let path = entry.path();
        if is_transient_sqlite_file(&path) {
            continue;
        }
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            let nested = scan_directory_contents(&path, should_cancel)?;
            stats.bytes = stats.bytes.saturating_add(nested.bytes);
            stats.files = stats.files.saturating_add(nested.files);
        } else if file_type.is_file() {
            stats.bytes = stats.bytes.saturating_add(entry.metadata()?.len());
            stats.files = stats.files.saturating_add(1);
        } else if file_type.is_symlink() {
            stats.files = stats.files.saturating_add(1);
        }
    }
    Ok(stats)
}

#[allow(clippy::too_many_arguments)]
fn copy_directory_contents_with_hooks<P, C>(
    source: &Path,
    target: &Path,
    source_root: &Path,
    target_root: &Path,
    totals: ProjectCopyStats,
    completed: &mut ProjectCopyStats,
    last_reported_bytes: &mut u64,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ProjectCopyProgress),
    C: FnMut() -> bool,
{
    ensure_copy_not_cancelled(should_cancel)?;
    for entry in fs::read_dir(source)
        .with_context(|| format!("failed to read workspace directory {}", source.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read an entry under {}", source.display()))?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if is_transient_sqlite_file(&source_path) {
            continue;
        }
        ensure_copy_not_cancelled(should_cancel)?;
        let file_type = entry
            .file_type()
            .with_context(|| format!("failed to inspect {}", source_path.display()))?;
        if file_type.is_dir() {
            fs::create_dir(&target_path).with_context(|| {
                format!(
                    "failed to create copied directory {}",
                    target_path.display()
                )
            })?;
            copy_directory_contents_with_hooks(
                &source_path,
                &target_path,
                source_root,
                target_root,
                totals,
                completed,
                last_reported_bytes,
                on_progress,
                should_cancel,
            )?;
        } else if file_type.is_symlink() {
            copy_symlink(&source_path, &target_path, source_root, target_root)?;
            completed.files = completed.files.saturating_add(1);
            emit_copy_progress(
                on_progress,
                "copying",
                &relative_copy_detail(source_root, &source_path),
                *completed,
                totals,
                true,
            );
        } else if file_type.is_file() {
            copy_file_with_progress(
                &source_path,
                &target_path,
                source_root,
                totals,
                completed,
                last_reported_bytes,
                on_progress,
                should_cancel,
            )?;
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn copy_file_with_progress<P, C>(
    source: &Path,
    target: &Path,
    source_root: &Path,
    totals: ProjectCopyStats,
    completed: &mut ProjectCopyStats,
    last_reported_bytes: &mut u64,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ProjectCopyProgress),
    C: FnMut() -> bool,
{
    let mut input = File::open(source)
        .with_context(|| format!("failed to open source file {}", source.display()))?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)
        .with_context(|| format!("failed to create copied file {}", target.display()))?;
    let detail = relative_copy_detail(source_root, source);
    let mut buffer = vec![0_u8; 1024 * 1024];
    loop {
        ensure_copy_not_cancelled(should_cancel)?;
        let read = input
            .read(&mut buffer)
            .with_context(|| format!("failed to read source file {}", source.display()))?;
        if read == 0 {
            break;
        }
        output
            .write_all(&buffer[..read])
            .with_context(|| format!("failed to write copied file {}", target.display()))?;
        completed.bytes = completed.bytes.saturating_add(read as u64);
        if completed.bytes.saturating_sub(*last_reported_bytes) >= COPY_PROGRESS_BYTE_STEP {
            *last_reported_bytes = completed.bytes;
            emit_copy_progress(on_progress, "copying", &detail, *completed, totals, true);
        }
    }
    output
        .flush()
        .with_context(|| format!("failed to flush copied file {}", target.display()))?;
    fs::set_permissions(target, fs::metadata(source)?.permissions())?;
    completed.files = completed.files.saturating_add(1);
    emit_copy_progress(on_progress, "copying", &detail, *completed, totals, true);
    Ok(())
}

fn relative_copy_detail(source_root: &Path, source: &Path) -> String {
    source
        .strip_prefix(source_root)
        .unwrap_or(source)
        .to_string_lossy()
        .to_string()
}

#[cfg(unix)]
fn copy_symlink(
    source: &Path,
    target: &Path,
    source_root: &Path,
    target_root: &Path,
) -> Result<()> {
    let link_target = fs::read_link(source)
        .with_context(|| format!("failed to read symlink {}", source.display()))?;
    let link_target = rebase_internal_path(&link_target, source_root, target_root);
    std::os::unix::fs::symlink(link_target, target)
        .with_context(|| format!("failed to copy symlink {}", source.display()))
}

#[cfg(windows)]
fn copy_symlink(
    source: &Path,
    target: &Path,
    source_root: &Path,
    target_root: &Path,
) -> Result<()> {
    let link_target = fs::read_link(source)
        .with_context(|| format!("failed to read symlink {}", source.display()))?;
    let link_target = rebase_internal_path(&link_target, source_root, target_root);
    let result = if source.is_dir() {
        std::os::windows::fs::symlink_dir(link_target, target)
    } else {
        std::os::windows::fs::symlink_file(link_target, target)
    };
    result.with_context(|| format!("failed to copy symlink {}", source.display()))
}

fn rebase_internal_path(path: &Path, source_root: &Path, target_root: &Path) -> PathBuf {
    path.strip_prefix(source_root)
        .map(|relative| target_root.join(relative))
        .unwrap_or_else(|_| path.to_path_buf())
}

pub fn looks_like_bundle_root(candidate: &Path) -> bool {
    REQUIRED_BUNDLE_ROOT_PATHS
        .iter()
        .all(|required| candidate.join(required).exists())
}

pub fn resolve_bundle_root_dir(input: &Path) -> Result<PathBuf> {
    if looks_like_bundle_root(input) {
        return Ok(input.to_path_buf());
    }

    let nested = input.join("gpm_server");
    if looks_like_bundle_root(&nested) {
        return Ok(nested);
    }

    let child_bundle_roots: Vec<PathBuf> = fs::read_dir(input)
        .ok()
        .into_iter()
        .flat_map(|entries| entries.filter_map(|entry| entry.ok()))
        .map(|entry| entry.path())
        .filter(|path| path.is_dir() && looks_like_bundle_root(path))
        .collect();
    if child_bundle_roots.len() == 1 {
        return Ok(child_bundle_roots[0].clone());
    }

    bail!(
        "selected path does not look like an extracted gpm_server directory: {}",
        input.display()
    )
}

pub fn default_workspace_root_for_bundle_root(bundle_root: &Path) -> PathBuf {
    bundle_root.to_path_buf()
}

pub fn resolve_extracted_bundle_workspace(input: &Path) -> Result<ExtractedBundleWorkspace> {
    let bundle_root = resolve_bundle_root_dir(input)?;
    let workspace_root = default_workspace_root_for_bundle_root(&bundle_root);
    Ok(ExtractedBundleWorkspace {
        bundle_root,
        workspace_root,
    })
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;
    use std::fs;

    use rusqlite::{Connection, params};
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn resolves_bundle_root_when_selected_path_is_gpm_server() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        create_bundle_root(&bundle_root);

        let resolved = resolve_extracted_bundle_workspace(&bundle_root).unwrap();

        assert_eq!(resolved.bundle_root, bundle_root);
        assert_eq!(resolved.workspace_root, bundle_root);
    }

    #[test]
    fn resolves_bundle_root_when_selected_path_is_parent_directory() {
        let temp = tempdir().unwrap();
        let delivery_root = temp.path().join("delivery");
        let bundle_root = delivery_root.join("gpm_server");
        create_bundle_root(&bundle_root);

        let resolved = resolve_extracted_bundle_workspace(&delivery_root).unwrap();

        assert_eq!(resolved.bundle_root, bundle_root);
    }

    #[test]
    fn resolves_bundle_root_when_selected_path_is_parent_of_renamed_bundle_directory() {
        let temp = tempdir().unwrap();
        let delivery_root = temp.path().join("delivery");
        let bundle_root = delivery_root.join("qqq");
        create_bundle_root(&bundle_root);

        let resolved = resolve_extracted_bundle_workspace(&delivery_root).unwrap();

        assert_eq!(resolved.bundle_root, bundle_root);
        assert_eq!(resolved.workspace_root, bundle_root);
    }

    #[test]
    fn rejects_directory_that_is_not_bundle_root() {
        let temp = tempdir().unwrap();
        let error = resolve_bundle_root_dir(temp.path()).unwrap_err();
        assert!(
            error
                .to_string()
                .contains("does not look like an extracted gpm_server directory")
        );
    }

    #[test]
    fn copies_workspace_beside_source_and_renames_project() {
        let temp = tempdir().unwrap();
        let source = temp.path().join("rice");
        create_project_workspace(&source, "Rice");
        fs::create_dir_all(source.join("runs/q4")).unwrap();
        fs::write(source.join("runs/q4/result.txt"), "kept").unwrap();

        let copied = copy_project_workspace(&source).unwrap();

        assert_eq!(copied.workspace_root, temp.path().join("rice-copy1"));
        assert_eq!(copied.project_name, "Rice-copy1");
        assert_eq!(copied.copy_index, 1);
        assert_eq!(copied.project_count, 1);
        assert_eq!(
            fs::read_to_string(copied.workspace_root.join("runs/q4/result.txt")).unwrap(),
            "kept"
        );
        assert_eq!(read_project_name(&source), "Rice");
        assert_eq!(read_project_name(&copied.workspace_root), "Rice-copy1");
        assert_workspace_paths_rebased(&source, &copied.workspace_root);
    }

    #[test]
    fn advances_copy_suffix_when_sibling_already_exists() {
        let temp = tempdir().unwrap();
        let source = temp.path().join("wheat");
        create_project_workspace(&source, "Wheat");
        fs::create_dir(temp.path().join("wheat-copy1")).unwrap();

        let copied = copy_project_workspace(&source).unwrap();

        assert_eq!(copied.workspace_root, temp.path().join("wheat-copy2"));
        assert_eq!(copied.project_name, "Wheat-copy2");
        assert_eq!(copied.copy_index, 2);
    }

    #[test]
    fn copies_workspace_to_custom_path_with_progress() {
        let temp = tempdir().unwrap();
        let source = temp.path().join("rice");
        let archive = temp.path().join("archive");
        let target = archive.join("rice-review");
        create_project_workspace(&source, "Rice");
        fs::create_dir(&archive).unwrap();
        fs::write(source.join("notes.txt"), "copy me").unwrap();
        let mut stages = Vec::new();

        let copied = copy_project_workspace_to_with_hooks(
            &source,
            &target,
            "Rice review",
            &mut |progress: ProjectCopyProgress| stages.push(progress.stage),
            &mut || false,
        )
        .unwrap();

        assert_eq!(copied.workspace_root, target);
        assert_eq!(copied.project_name, "Rice review");
        assert_eq!(copied.copy_index, 0);
        assert_eq!(
            fs::read_to_string(target.join("notes.txt")).unwrap(),
            "copy me"
        );
        assert_eq!(read_project_name(&target), "Rice review");
        assert_workspace_paths_rebased(&source, &target);
        assert!(stages.contains(&"scanning"));
        assert!(stages.contains(&"copying"));
        assert!(stages.contains(&"finalizing"));
        assert!(stages.contains(&"verifying"));
        assert_eq!(stages.last(), Some(&"complete"));
    }

    #[test]
    fn cancellation_removes_partial_workspace_copy() {
        let temp = tempdir().unwrap();
        let source = temp.path().join("wheat");
        let target = temp.path().join("wheat-cancelled");
        create_project_workspace(&source, "Wheat");
        fs::write(source.join("extra.bin"), vec![7_u8; 2 * 1024 * 1024]).unwrap();
        let cancel = Cell::new(false);

        let error = copy_project_workspace_to_with_hooks(
            &source,
            &target,
            "Wheat cancelled",
            &mut |progress: ProjectCopyProgress| {
                if progress.stage == "copying" {
                    cancel.set(true);
                }
            },
            &mut || cancel.get(),
        )
        .unwrap_err();

        assert!(error.to_string().contains("PROJECT_COPY_CANCELLED"));
        assert!(!target.exists());
        assert_eq!(read_project_name(&source), "Wheat");
    }

    fn create_bundle_root(bundle_root: &Path) {
        fs::create_dir_all(bundle_root.join("metadata")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
        fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
        fs::create_dir_all(bundle_root.join("runs")).unwrap();
        fs::write(bundle_root.join("metadata/reference.tsv"), "id\tname\n").unwrap();
        fs::write(bundle_root.join("metadata/datasets.tsv"), "id\tname\n").unwrap();
    }

    fn create_project_workspace(workspace_root: &Path, project_name: &str) {
        fs::create_dir_all(workspace_root).unwrap();
        fs::create_dir_all(workspace_root.join("data/reference")).unwrap();
        fs::create_dir_all(workspace_root.join("data/datasets/primary")).unwrap();
        fs::create_dir_all(workspace_root.join("runs/primary_vs_primary")).unwrap();
        let conn = crate::db::open_workspace_db(&workspace_root.join("project.sqlite")).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (name, species_name, assembly_label, fasta_path, fai_path)
             VALUES ('ref', 'species', 'assembly', ?1, ?2)",
            params![
                workspace_root.join("data/reference/ref.fa").to_string_lossy(),
                workspace_root.join("data/reference/ref.fa.fai").to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (name, assembler, fasta_path, fai_path)
             VALUES ('primary', 'test', ?1, ?2)",
            params![
                workspace_root
                    .join("data/datasets/primary/primary.fa")
                    .to_string_lossy(),
                workspace_root
                    .join("data/datasets/primary/primary.fa.fai")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 'Chr1', 1, 100)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq (dataset_id, seq_name, seq_order, length)
             VALUES (1, 'ctg1', 1, 100)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr_locator (reference_chr_id, fasta_path) VALUES (1, ?1)",
            params![
                workspace_root
                    .join("data/reference/Chr1.fa")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path) VALUES (1, ?1)",
            params![
                workspace_root
                    .join("data/datasets/primary/ctg1.fa")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO pairwise_alignment_run (
                run_name, paf_path, query_dataset_id, target_dataset_id,
                paf_mtime_ms, paf_size_bytes, indexed_at
             ) VALUES ('primary_vs_primary', ?1, 1, 1, 0, 0, '2026-09-22T00:00:00Z')",
            params![
                workspace_root
                    .join("runs/primary_vs_primary/result.paf")
                    .to_string_lossy()
            ],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project (
                name, version, reference_genome_id, primary_dataset_id, created_at
             ) VALUES (?1, 1, 1, 1, '2026-09-22T00:00:00Z')",
            params![project_name],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO export_record (project_id, export_type, output_path, created_at)
             VALUES (1, 'chr_fasta', ?1, '2026-09-22T00:00:00Z')",
            params![workspace_root.join("exports/Chr1.fa").to_string_lossy()],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO export_record (project_id, export_type, output_path, created_at)
             VALUES (1, 'ctg_fasta', ?1, '2026-09-22T00:00:00Z')",
            params![
                workspace_root
                    .parent()
                    .unwrap()
                    .join("external.fa")
                    .to_string_lossy()
            ],
        )
        .unwrap();
    }

    fn read_project_name(workspace_root: &Path) -> String {
        let conn = Connection::open(workspace_root.join("project.sqlite")).unwrap();
        conn.query_row("SELECT name FROM project WHERE id = 1", [], |row| {
            row.get(0)
        })
        .unwrap()
    }

    fn assert_workspace_paths_rebased(source_root: &Path, copied_root: &Path) {
        let conn = Connection::open(copied_root.join("project.sqlite")).unwrap();
        for (table, column) in [
            ("reference_genome", "fasta_path"),
            ("reference_genome", "fai_path"),
            ("dataset", "fasta_path"),
            ("dataset", "fai_path"),
            ("reference_chr_locator", "fasta_path"),
            ("source_seq_locator", "fasta_path"),
            ("pairwise_alignment_run", "paf_path"),
            ("export_record", "output_path"),
        ] {
            let value: String = conn
                .query_row(
                    &format!("SELECT {column} FROM {table} LIMIT 1"),
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            assert!(
                Path::new(&value).starts_with(copied_root),
                "{table}.{column}: {value}"
            );
            assert!(
                !Path::new(&value).starts_with(source_root),
                "{table}.{column}: {value}"
            );
        }
        let external_export: String = conn
            .query_row(
                "SELECT output_path FROM export_record ORDER BY id DESC LIMIT 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(
            Path::new(&external_export),
            source_root.parent().unwrap().join("external.fa")
        );
    }
}
