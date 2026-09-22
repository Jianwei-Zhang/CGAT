use std::ffi::OsString;
use std::fs;
use std::io::ErrorKind;
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

/// Copy a complete project workspace beside its source as `<directory>-copyN`.
/// Every project name in the copied database receives the same suffix.
pub fn copy_project_workspace(source_root: &Path) -> Result<CopiedProjectWorkspace> {
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

    let conn = open_workspace_db(&source_db)?;
    let projects = {
        let mut statement = conn
            .prepare("SELECT id, name FROM project ORDER BY id")
            .context("failed to read source project names")?;
        let rows = statement
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        if rows.is_empty() {
            bail!(
                "workspace has no project to copy: {}",
                source_root.display()
            );
        }
        rows
    };
    conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
        .context("failed to checkpoint source project database")?;
    drop(conn);

    let (target_root, copy_index) = reserve_copy_directory(source_root)?;
    let copy_result = (|| {
        copy_directory_contents(source_root, &target_root)?;
        let target_db = target_root.join("project.sqlite");
        let mut copied_conn = open_workspace_db(&target_db)?;
        let tx = copied_conn
            .transaction()
            .context("failed to start copied project rename transaction")?;
        rebase_workspace_paths(&tx, source_root, &target_root)?;
        for (project_id, project_name) in &projects {
            let copied_name = format!("{project_name}-copy{copy_index}");
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
        Ok(())
    })();

    if let Err(error) = copy_result {
        let _ = fs::remove_dir_all(&target_root);
        return Err(error);
    }

    Ok(CopiedProjectWorkspace {
        workspace_root: target_root,
        project_name: format!("{}-copy{copy_index}", projects[0].1),
        copy_index,
        project_count: projects.len(),
    })
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

fn reserve_copy_directory(source_root: &Path) -> Result<(PathBuf, usize)> {
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
        match fs::create_dir(&target_root) {
            Ok(()) => return Ok((target_root, copy_index)),
            Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(error).with_context(|| {
                    format!(
                        "failed to create copied workspace {}",
                        target_root.display()
                    )
                });
            }
        }
    }
    unreachable!("usize copy index space exhausted")
}

fn copy_directory_contents(source: &Path, target: &Path) -> Result<()> {
    copy_directory_contents_rebased(source, target, source, target)
}

fn copy_directory_contents_rebased(
    source: &Path,
    target: &Path,
    source_root: &Path,
    target_root: &Path,
) -> Result<()> {
    for entry in fs::read_dir(source)
        .with_context(|| format!("failed to read workspace directory {}", source.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read an entry under {}", source.display()))?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if matches!(
            entry.file_name().to_str(),
            Some("project.sqlite-wal" | "project.sqlite-shm")
        ) {
            continue;
        }
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
            copy_directory_contents_rebased(&source_path, &target_path, source_root, target_root)?;
        } else if file_type.is_symlink() {
            copy_symlink(&source_path, &target_path, source_root, target_root)?;
        } else if file_type.is_file() {
            fs::copy(&source_path, &target_path).with_context(|| {
                format!(
                    "failed to copy {} to {}",
                    source_path.display(),
                    target_path.display()
                )
            })?;
        }
    }
    Ok(())
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
