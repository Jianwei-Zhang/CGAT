use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Result, bail};

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

    fn create_bundle_root(bundle_root: &Path) {
        fs::create_dir_all(bundle_root.join("metadata")).unwrap();
        fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
        fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
        fs::create_dir_all(bundle_root.join("runs")).unwrap();
        fs::write(bundle_root.join("metadata/reference.tsv"), "id\tname\n").unwrap();
        fs::write(bundle_root.join("metadata/datasets.tsv"), "id\tname\n").unwrap();
    }
}
