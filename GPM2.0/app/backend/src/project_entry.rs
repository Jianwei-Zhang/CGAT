//! Read-only filesystem classification for desktop project entry.
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;

use crate::workspace::looks_like_bundle_root;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectEntry {
    pub kind: &'static str,
    pub path: String,
    pub suggested_workspace: Option<String>,
}

pub fn canonical_workspace_path(path: &Path) -> Result<PathBuf> {
    if !path.is_dir() {
        bail!("workspace directory does not exist: {}", path.display());
    }
    fs::canonicalize(path).with_context(|| format!("cannot resolve directory: {}", path.display()))
}

pub fn display_path(path: &Path) -> String {
    let value = path.to_string_lossy();
    // Windows canonicalization uses extended-length paths; keep UI paths readable.
    if let Some(unc) = value.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else {
        value.strip_prefix(r"\\?\").unwrap_or(&value).to_string()
    }
}

pub fn workspace_aliases(workspace: &Path, history: &[String]) -> Vec<String> {
    let Ok(identity) = fs::canonicalize(workspace) else {
        return Vec::new();
    };
    history
        .iter()
        .take(20)
        .filter(|path| {
            #[cfg(unix)]
            {
                use std::os::unix::fs::MetadataExt;
                // macOS can be case-insensitive; inode identity avoids guessing from
                // path capitalization and also handles realpath/symlink aliases.
                match (fs::metadata(&identity), fs::metadata(path)) {
                    (Ok(a), Ok(b)) => {
                        a.is_dir() && b.is_dir() && a.dev() == b.dev() && a.ino() == b.ino()
                    }
                    _ => false,
                }
            }
            #[cfg(not(unix))]
            {
                fs::canonicalize(path).is_ok_and(|candidate| candidate == identity)
            }
        })
        .cloned()
        .collect()
}

fn archive_stem(path: &Path) -> Result<String> {
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .context("archive filename is not valid UTF-8")?;
    let lower = name.to_ascii_lowercase();
    for suffix in [".tar.gz", ".zip", ".tgz"] {
        if lower.ends_with(suffix) {
            let stem = &name[..name.len() - suffix.len()];
            if !stem.is_empty() {
                return Ok(stem.to_string());
            }
        }
    }
    bail!(
        "expected a .zip, .tar.gz or .tgz delivery: {}",
        path.display()
    )
}

pub fn suggest_archive_workspace(path: &Path, timestamp: &str) -> Result<PathBuf> {
    // The timestamp comes from the desktop's local clock, never from a path component.
    if timestamp.len() != 15
        || timestamp.as_bytes()[8] != b'_'
        || !timestamp
            .bytes()
            .enumerate()
            .all(|(i, b)| i == 8 || b.is_ascii_digit())
    {
        bail!("invalid workspace timestamp; expected YYYYMMDD_HHMMSS");
    }
    let stem = archive_stem(path)?;
    let parent = path.parent().context("archive has no parent directory")?;
    let name = format!("{stem}_{timestamp}");
    for index in 0..10_000 {
        let leaf = if index == 0 {
            name.clone()
        } else {
            format!("{name}_{index:02}")
        };
        let candidate = parent.join(leaf);
        // Includes dangling symlinks; never suggest an occupied filesystem entry.
        match fs::symlink_metadata(&candidate) {
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(candidate),
            Err(err) => return Err(err).context("cannot inspect suggested workspace destination"),
            Ok(_) => {}
        }
    }
    bail!("too many existing destinations beside the delivery package")
}

fn inspect_directory(path: &Path) -> Result<Option<&'static str>> {
    let db = path.join("project.sqlite");
    if fs::symlink_metadata(&db).is_ok() {
        // Never open with CREATE or migrations during classification. A broken existing
        // database must not be treated as permission to import over the old workspace.
        let conn = Connection::open_with_flags(&db, OpenFlags::SQLITE_OPEN_READ_ONLY)
            .with_context(|| {
                format!(
                    "existing workspace database cannot be opened: {}",
                    db.display()
                )
            })?;
        let tables: i64 = conn.query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('project', 'dataset', 'reference_genome')",
            [], |row| row.get(0),
        ).with_context(|| format!("existing workspace database is invalid: {}", db.display()))?;
        if tables != 3 {
            bail!(
                "existing workspace database is incomplete: {}",
                db.display()
            );
        }
        return Ok(Some("workspace"));
    }
    if looks_like_bundle_root(path) {
        return Ok(Some("extracted"));
    }
    Ok(None)
}

pub fn inspect_project_entry(path: &Path, timestamp: &str) -> Result<ProjectEntry> {
    let canonical = fs::canonicalize(path).with_context(|| {
        format!(
            "dropped path does not exist or cannot be accessed: {}",
            path.display()
        )
    })?;
    if canonical.is_file() {
        archive_stem(&canonical)?;
        let file = fs::File::open(&canonical).context("cannot read delivery archive")?;
        if canonical
            .file_name()
            .unwrap()
            .to_string_lossy()
            .to_ascii_lowercase()
            .ends_with(".zip")
        {
            let archive = zip::ZipArchive::new(file).context("invalid ZIP delivery archive")?;
            if archive.is_empty() {
                bail!("delivery archive is empty");
            }
        } else {
            let mut archive = tar::Archive::new(flate2::read::GzDecoder::new(file));
            let mut entries = archive
                .entries()
                .context("invalid tar.gz delivery archive")?;
            entries
                .next()
                .context("delivery archive is empty")?
                .context("invalid tar.gz delivery header")?;
        }
        let suggested = suggest_archive_workspace(&canonical, timestamp)?;
        return Ok(ProjectEntry {
            kind: "archive",
            path: display_path(&canonical),
            suggested_workspace: Some(display_path(&suggested)),
        });
    }
    if !canonical.is_dir() {
        bail!("drop a delivery archive or workspace directory");
    }
    if let Some(kind) = inspect_directory(&canonical)? {
        return Ok(ProjectEntry {
            kind,
            path: display_path(&canonical),
            suggested_workspace: None,
        });
    }
    let mut candidates = Vec::new();
    for entry in fs::read_dir(&canonical).context("cannot inspect dropped directory")? {
        let child = entry?.path();
        if child.is_dir()
            && (child.join("project.sqlite").exists() || looks_like_bundle_root(&child))
        {
            candidates.push(child);
            if candidates.len() > 1 {
                bail!("directory contains multiple projects; drop the project directory itself");
            }
        }
    }
    if let Some(child) = candidates.pop() {
        let resolved = canonical_workspace_path(&child)?;
        let kind = inspect_directory(&resolved)?.context("directory is not a GPM project")?;
        return Ok(ProjectEntry {
            kind,
            path: display_path(&resolved),
            suggested_workspace: None,
        });
    }
    bail!(
        "directory is neither an existing GPM workspace nor an extracted delivery: {}",
        path.display()
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn bundle(root: &Path) {
        for dir in ["metadata", "data/reference", "data/datasets", "runs"] {
            fs::create_dir_all(root.join(dir)).unwrap();
        }
        for file in ["metadata/reference.tsv", "metadata/datasets.tsv"] {
            fs::write(root.join(file), "").unwrap();
        }
    }
    fn workspace(root: &Path) {
        fs::create_dir_all(root).unwrap();
        let conn = Connection::open(root.join("project.sqlite")).unwrap();
        crate::db::init_workspace_schema(&conn).unwrap();
    }
    #[test]
    fn archive_suffixes_timestamp_and_collision_are_read_only() {
        let temp = tempdir().unwrap();
        for suffix in [".zip", ".tar.gz", ".tgz", ".TAR.GZ"] {
            let source = temp.path().join(format!("sample.no_fasta{suffix}"));
            if suffix == ".zip" {
                let mut archive = zip::ZipWriter::new(fs::File::create(&source).unwrap());
                archive
                    .add_directory("metadata/", zip::write::FileOptions::default())
                    .unwrap();
                archive.finish().unwrap();
            } else {
                let encoder = flate2::write::GzEncoder::new(
                    fs::File::create(&source).unwrap(),
                    flate2::Compression::fast(),
                );
                let mut archive = tar::Builder::new(encoder);
                archive.append_dir("metadata", temp.path()).unwrap();
                archive.into_inner().unwrap().finish().unwrap();
            }
            let first = inspect_project_entry(&source, "20261008_143025").unwrap();
            assert_eq!(first.kind, "archive");
            let expected = temp.path().join("sample.no_fasta_20261008_143025");
            assert_eq!(first.suggested_workspace, Some(display_path(&expected)));
            assert!(!expected.exists());
            fs::create_dir(&expected).unwrap();
            let second = inspect_project_entry(&source, "20261008_143025").unwrap();
            assert!(second.suggested_workspace.unwrap().ends_with("_01"));
            fs::remove_dir(expected).unwrap();
        }
        assert!(suggest_archive_workspace(&temp.path().join("x.zip"), "../../something").is_err());
        assert!(
            inspect_project_entry(&temp.path().join("missing.zip"), "20261008_143025").is_err()
        );
    }
    #[test]
    fn root_and_unique_wrapper_detect_existing_workspace_before_delivery() {
        let temp = tempdir().unwrap();
        let root = temp.path().join("gpm_server");
        bundle(&root);
        assert_eq!(
            inspect_project_entry(temp.path(), "").unwrap().kind,
            "extracted"
        );
        workspace(&root);
        let db = fs::read(root.join("project.sqlite")).unwrap();
        assert_eq!(
            inspect_project_entry(temp.path(), "").unwrap().kind,
            "workspace"
        );
        assert_eq!(inspect_project_entry(&root, "").unwrap().kind, "workspace");
        assert_eq!(fs::read(root.join("project.sqlite")).unwrap(), db);
        assert!(!root.join("cache").exists());
        let other = temp.path().join("second");
        bundle(&other);
        assert!(inspect_project_entry(temp.path(), "").is_err());
    }
    #[test]
    fn invalid_database_never_falls_back_to_extracted_import() {
        let temp = tempdir().unwrap();
        bundle(temp.path());
        let db = temp.path().join("project.sqlite");
        fs::write(&db, "broken").unwrap();
        assert!(inspect_project_entry(temp.path(), "").is_err());
        assert_eq!(fs::read_to_string(&db).unwrap(), "broken");
        fs::remove_file(&db).unwrap();
        Connection::open(&db).unwrap();
        assert!(inspect_project_entry(temp.path(), "").is_err());
    }
    #[test]
    fn path_aliases_do_not_merge_distinct_copies() {
        let temp = tempdir().unwrap();
        let a = temp.path().join("a");
        let b = temp.path().join("b");
        workspace(&a);
        workspace(&b);
        let alias = a.join(".").to_string_lossy().to_string();
        assert_eq!(
            workspace_aliases(&a, &[alias.clone(), display_path(&b)]),
            vec![alias]
        );
    }
    #[cfg(windows)]
    #[test]
    fn windows_case_aliases_are_resolved_by_the_filesystem() {
        let temp = tempdir().unwrap();
        let root = temp.path().join("MixedCaseProject");
        workspace(&root);
        let alias = display_path(&root).to_ascii_uppercase();
        assert_eq!(workspace_aliases(&root, &[alias.clone()]), vec![alias]);
    }
    #[test]
    fn corrupt_archives_and_unsupported_files_do_not_create_a_workspace() {
        let temp = tempdir().unwrap();
        for suffix in ["zip", "tar.gz", "txt"] {
            let source = temp.path().join(format!("corrupt.{suffix}"));
            fs::write(&source, "not an archive").unwrap();
            assert!(inspect_project_entry(&source, "20261008_143025").is_err());
        }
        assert_eq!(fs::read_dir(temp.path()).unwrap().count(), 3);
    }
    #[cfg(unix)]
    #[test]
    fn canonical_aliases_and_case_sensitive_paths() {
        let temp = tempdir().unwrap();
        let a = temp.path().join("A");
        let b = temp.path().join("a");
        workspace(&a);
        workspace(&b);
        let alias = temp.path().join("link");
        std::os::unix::fs::symlink(&a, &alias).unwrap();
        assert_eq!(
            workspace_aliases(&a, &[display_path(&alias), display_path(&b)]),
            vec![display_path(&alias)]
        );
        assert_eq!(
            inspect_project_entry(&alias, "").unwrap().path,
            display_path(&a)
        );
    }
}
