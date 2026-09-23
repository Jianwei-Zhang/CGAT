use super::test_support::*;

fn tar_bundle(path: &Path, source: &Path) {
    let encoder =
        flate2::write::GzEncoder::new(File::create(path).unwrap(), flate2::Compression::fast());
    let mut archive = tar::Builder::new(encoder);
    archive.append_dir_all("gpm_server", source).unwrap();
    archive.into_inner().unwrap().finish().unwrap();
}

#[test]
fn imports_tar_gz_and_tgz_with_the_same_catalog_as_zip() {
    let temp = tempdir().unwrap();
    let source = temp.path().join("source");
    create_bundle_root(&source);
    for suffix in ["tar.gz", "tgz"] {
        let path = temp.path().join(format!("bundle.{suffix}"));
        tar_bundle(&path, &source);
        let workspace = temp.path().join(format!("workspace-{suffix}"));
        let mut streaming_steps = Vec::new();
        let (outcome, progress) = import_from_zip_with_hooks(
            &path,
            &workspace,
            &mut |step| streaming_steps.push(step.clone()),
            &mut || false,
        )
        .unwrap();
        assert!(
            streaming_steps
                .iter()
                .filter(|step| step.stage == "extract_entry")
                .all(|step| step.progress_total.is_none())
        );
        assert!(outcome.project_db_path.exists());
        assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
        assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
        assert_eq!(progress.last().unwrap().stage, "complete");
        assert!(!workspace.join("gpm_server").exists());
    }
}

#[test]
fn rejects_tar_links_and_traversal_and_removes_failed_workspace() {
    let temp = tempdir().unwrap();
    for (index, (name, kind)) in [
        ("../escape", tar::EntryType::Regular),
        ("gpm_server/link", tar::EntryType::Symlink),
        ("gpm_server/hard", tar::EntryType::Link),
        ("gpm_server/C:escape", tar::EntryType::Regular),
    ]
    .into_iter()
    .enumerate()
    {
        let path = temp.path().join(format!("bad-{index}.tar.gz"));
        let encoder = flate2::write::GzEncoder::new(
            File::create(&path).unwrap(),
            flate2::Compression::fast(),
        );
        let mut archive = tar::Builder::new(encoder);
        let mut header = tar::Header::new_gnu();
        header.set_mode(0o644);
        header.set_size(0);
        header.set_entry_type(kind);
        // Set the raw path to exercise traversal rejection rather than the
        // builder's own path validation.
        header.as_mut_bytes()[..name.len()].copy_from_slice(name.as_bytes());
        if kind.is_symlink() || kind.is_hard_link() {
            header.set_link_name("../escape").unwrap();
        }
        header.set_cksum();
        archive.append(&header, io::empty()).unwrap();
        archive.into_inner().unwrap().finish().unwrap();
        let workspace = temp.path().join(format!("workspace-{index}"));
        assert!(import_from_zip(&path, &workspace).is_err());
        assert!(!workspace.exists());
        assert!(!temp.path().join("escape").exists());
    }
}

#[test]
fn truncated_gzip_and_cancelled_tar_imports_leave_no_workspace() {
    let temp = tempdir().unwrap();
    let source = temp.path().join("source");
    create_bundle_root(&source);
    let path = temp.path().join("bundle.tar.gz");
    tar_bundle(&path, &source);
    let workspace = temp.path().join("cancelled");
    let mut checks = 0;
    let error = import_from_zip_with_hooks(&path, &workspace, &mut |_| {}, &mut || {
        checks += 1;
        checks > 5
    })
    .unwrap_err();
    assert!(error.to_string().contains("cancelled"));
    assert!(!workspace.exists());
    let mut bytes = fs::read(&path).unwrap();
    bytes.truncate(bytes.len() - 6);
    fs::write(&path, bytes).unwrap();
    assert!(import_from_zip(&path, &workspace).is_err());
    assert!(!workspace.exists());
}
