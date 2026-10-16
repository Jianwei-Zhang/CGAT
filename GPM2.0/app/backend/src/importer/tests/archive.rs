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
        #[cfg(any(target_os = "windows", target_os = "macos"))]
        assert!(
            streaming_steps
                .iter()
                .any(|step| step.stage == "extract_native_archive")
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

#[test]
fn desktop_archive_import_atomically_reserves_a_new_directory_and_never_claims_existing_ones() {
    let temp = tempdir().unwrap();
    let source = temp.path().join("source");
    create_bundle_root(&source);
    for suffix in ["zip", "tar.gz"] {
        let package = temp.path().join(format!("delivery.{suffix}"));
        if suffix == "zip" {
            write_bundle_zip(&package);
        } else {
            tar_bundle(&package, &source);
        }
        let options = ImportOptions {
            require_new_workspace: true,
            ..ImportOptions::default()
        };
        let existing = temp.path().join(format!("existing-{suffix}"));
        fs::create_dir(&existing).unwrap();
        let error = import_from_zip_with_options_and_hooks(
            &package,
            &existing,
            options,
            &mut |_| {},
            &mut || false,
        )
        .unwrap_err();
        assert!(error.to_string().contains("must not exist"));
        assert!(existing.is_dir());
        assert_eq!(fs::read_dir(&existing).unwrap().count(), 0);
        fs::write(existing.join("keep.txt"), "user data").unwrap();
        assert!(
            import_from_zip_with_options_and_hooks(
                &package,
                &existing,
                options,
                &mut |_| {},
                &mut || false
            )
            .is_err()
        );
        assert_eq!(
            fs::read_to_string(existing.join("keep.txt")).unwrap(),
            "user data"
        );

        let raced = temp.path().join(format!("raced-{suffix}"));
        let mut on_progress = |step: ImportProgress| {
            if step.stage == "validate_input" {
                fs::create_dir(&raced).unwrap();
                fs::write(raced.join("keep"), "competitor").unwrap();
            }
        };
        assert!(
            import_from_zip_with_options_and_hooks(
                &package,
                &raced,
                options,
                &mut on_progress,
                &mut || false
            )
            .is_err()
        );
        assert_eq!(
            fs::read_to_string(raced.join("keep")).unwrap(),
            "competitor"
        );

        let destination = temp.path().join(format!("new-{suffix}"));
        let (outcome, _) = import_from_zip_with_options_and_hooks(
            &package,
            &destination,
            options,
            &mut |_| {},
            &mut || false,
        )
        .unwrap();
        assert!(outcome.project_db_path.exists());
        assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
        assert_eq!(
            crate::project_entry::inspect_project_entry(&destination, "")
                .unwrap()
                .kind,
            "workspace"
        );
    }
}
#[test]
fn zip_delivery_import_extracts_every_entry_through_the_shared_worker_budget() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("delivery.zip");
    write_bundle_zip(&path);
    let workspace = temp.path().join("workspace");
    let mut extracted = Vec::new();
    let (outcome, progress) = import_from_zip_with_options_and_hooks(
        &path,
        &workspace,
        ImportOptions {
            import_workers: Some(4),
            ..ImportOptions::default()
        },
        &mut |step| {
            if step.stage == "extract_entry" {
                extracted.push(step.detail.clone());
            }
        },
        &mut || false,
    )
    .unwrap();

    assert!(
        extracted.len() >= 14,
        "every zip payload entry must be reported: {extracted:?}"
    );
    let mut unique = extracted.clone();
    unique.sort();
    unique.dedup();
    assert_eq!(
        unique.len(),
        extracted.len(),
        "a duplicate zip path must be planned exactly once: {extracted:?}"
    );
    assert!(
        extracted
            .iter()
            .any(|name| name.ends_with("metadata/reference.tsv"))
    );
    assert_eq!(progress.last().unwrap().stage, "complete");
    assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
    let reference_tsv =
        fs::read_to_string(outcome.bundle_root.join("metadata/reference.tsv")).unwrap();
    assert!(reference_tsv.contains("ref_a"));
}

#[test]
fn zip_delivery_import_rejects_traversal_and_removes_the_failed_workspace() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("traversal.zip");
    {
        let file = File::create(&path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        let options = FileOptions::default().compression_method(CompressionMethod::Deflated);
        for (name, bytes) in [
            (
                "gpm_server/metadata/reference.tsv",
                b"reference_name".to_vec(),
            ),
            ("../escape.fa", b"escape".to_vec()),
        ] {
            zip.start_file(name, options).unwrap();
            zip.write_all(&bytes).unwrap();
        }
        zip.finish().unwrap();
    }
    let workspace = temp.path().join("workspace");
    let error = import_from_zip_with_options_and_hooks(
        &path,
        &workspace,
        ImportOptions {
            import_workers: Some(4),
            ..ImportOptions::default()
        },
        &mut |_| {},
        &mut || false,
    )
    .unwrap_err();

    assert!(
        error.to_string().contains("unsafe path traversal"),
        "unexpected error: {error}"
    );
    assert!(!workspace.exists());
    assert!(!temp.path().join("escape.fa").exists());
}
