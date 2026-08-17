use super::test_support::*;

#[test]
fn invalid_and_legacy_extracted_packages_create_no_workspace_database() {
    for legacy in [false, true] {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        if legacy {
            fs::write(
                bundle_root.join("metadata/package.tsv"),
                "package_mode\tsequence_layout\tpreassigned_chr\nfull\tpartitioned\ttrue\n",
            )
            .unwrap();
        } else {
            fs::remove_file(bundle_root.join("metadata/grt_recipe.tsv")).unwrap();
        }

        let error = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap_err();
        assert!(error.to_string().contains(if legacy {
            "GRT_IMPORT_INVALID_TSV"
        } else {
            "GRT_IMPORT_MISSING_REQUIRED_FILE"
        }));
        assert!(!bundle_root.join("project.sqlite").exists());
        assert!(!bundle_root.join("exports").exists());
        assert!(!bundle_root.join("cache").exists());
    }
}

#[test]
fn malformed_fai_is_rejected_before_workspace_creation() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    fs::write(
        bundle_root.join("data/datasets/primary.fa.fai"),
        "primary1\t3\t10\t4\t5\n",
    )
    .unwrap();

    let error = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap_err();
    assert!(error.to_string().contains("GRT_IMPORT_COUNT_MISMATCH"));
    assert!(!bundle_root.join("project.sqlite").exists());
}

#[test]
fn zip_import_round_trips_and_rejected_zip_leaves_no_workspace() {
    let temp = tempdir().unwrap();
    let valid_source = temp.path().join("valid_source");
    copy_tree(&fixture_root(), &valid_source);
    let valid_zip = temp.path().join("valid.zip");
    write_bundle_zip(&valid_source, &valid_zip);
    let valid_workspace = temp.path().join("valid_workspace");
    let (outcome, _) = crate::importer::import_from_zip(&valid_zip, &valid_workspace).unwrap();
    assert_eq!(
        load_grt_locked_recipe(&outcome.project_db_path)
            .unwrap()
            .recipe_id,
        "recipe-test"
    );

    let invalid_source = temp.path().join("invalid_source");
    copy_tree(&fixture_root(), &invalid_source);
    fs::remove_file(invalid_source.join("metadata/grt_recipe.tsv")).unwrap();
    let invalid_zip = temp.path().join("invalid.zip");
    write_bundle_zip(&invalid_source, &invalid_zip);
    let invalid_workspace = temp.path().join("invalid_workspace");
    let error = crate::importer::import_from_zip(&invalid_zip, &invalid_workspace).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("GRT_IMPORT_MISSING_REQUIRED_FILE")
    );
    assert!(!invalid_workspace.exists());
}
