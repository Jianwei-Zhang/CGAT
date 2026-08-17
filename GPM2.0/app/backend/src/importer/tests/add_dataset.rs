use super::test_support::*;

#[test]
fn imports_add_dataset_package_append_only_into_existing_project() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    write_prepare_options(&bundle_root, "asm10", false);
    fs::create_dir_all(bundle_root.join("runs/ds_a_vs_ref")).unwrap();
    fs::create_dir_all(bundle_root.join("runs/chr_r/ds_a_vs_self")).unwrap();
    fs::write(
        bundle_root.join("runs/ds_a_vs_ref/result.paf"),
        "d\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("runs/chr_r/ds_a_vs_self/result.paf"),
        "d\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n",
    )
    .unwrap();

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let project_id = insert_existing_project(&outcome.project_db_path);
    crate::project_initializer::bootstrap_project_assembly(&outcome.project_db_path, project_id)
        .unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();
    let existing_dataset_count = count_rows(&outcome.project_db_path, "dataset");
    let existing_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
    let existing_chr_assignment_count =
        count_rows(&outcome.project_db_path, "imported_chr_assignment");
    let existing_ref_hit_count = count_rows(&outcome.project_db_path, "ref_alignment_hit");
    let existing_pairwise_run_ids = query_pairwise_run_ids_for_dataset_names(&conn, &["ds_a"]);
    let existing_assembly_rows = query_project_assembly_rows(&conn, project_id);
    drop(conn);

    let add_zip_path = temp.path().join("add_ds4.zip");
    write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

    let (add_outcome, progress) =
        import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap();

    assert_eq!(add_outcome.dataset_name, "ds4");
    assert_eq!(add_outcome.project_id, Some(project_id));
    assert_eq!(add_outcome.bundle_root, outcome.workspace_root);
    assert!(progress.iter().any(|item| item.stage == "index_ref_paf"));
    assert!(
        progress
            .iter()
            .any(|item| item.stage == "index_pairwise_paf")
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "dataset"),
        existing_dataset_count + 1
    );
    assert_eq!(dataset_stats(&outcome.project_db_path, "ds4"), Some((1, 4)));

    let conn = Connection::open(&outcome.project_db_path).unwrap();
    let ds4_id: i64 = conn
        .query_row("SELECT id FROM dataset WHERE name = 'ds4'", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM project_dataset WHERE project_id = ?1 AND dataset_id = ?2 AND dataset_role = 'support'",
            params![project_id, ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1",
            params![ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        query_project_assembly_rows_excluding_dataset(&conn, project_id, ds4_id),
        existing_assembly_rows
    );
    let ds4_assembly_row: (String, Option<i64>, String, Option<String>) = conn
        .query_row(
            "SELECT c.name, c.chr_order, s.orient, c.ref_orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE c.project_id = ?1 AND ss.dataset_id = ?2",
            params![project_id, ds4_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(
        ds4_assembly_row,
        (
            "x@r".to_string(),
            Some(1),
            "+".to_string(),
            Some("+".to_string())
        )
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq_locator"),
        existing_locator_count + 1
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "imported_chr_assignment"),
        existing_chr_assignment_count + 1
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM ref_alignment_hit WHERE dataset_id = ?1",
            params![ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "ref_alignment_hit"),
        existing_ref_hit_count + 1
    );
    for run_id in existing_pairwise_run_ids {
        let still_present: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pairwise_alignment_run WHERE id = ?1",
                params![run_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(still_present, 1);
    }
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*)
             FROM pairwise_alignment_run
             WHERE query_dataset_id = ?1 OR target_dataset_id = ?1",
            params![ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        2
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*)
             FROM pairwise_alignment_hit h
             JOIN pairwise_alignment_run r ON r.id = h.run_id
             WHERE r.query_dataset_id = ?1 OR r.target_dataset_id = ?1",
            params![ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert!(
        fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv"))
            .unwrap()
            .contains("\nds4\t")
    );
    assert!(outcome.workspace_root.join("data/datasets/ds4.fa").exists());
    assert!(
        outcome
            .workspace_root
            .join("runs/chr_r/ds_a_vs_ds4/result.paf")
            .exists()
    );
}

#[test]
fn imports_add_dataset_package_into_workspace_without_project_link() {
    let temp = tempdir().unwrap();
    let (outcome, project_id) = import_workspace_with_project(temp.path());
    let original_project_dataset_count = count_rows(&outcome.project_db_path, "project_dataset");
    let original_assembly_rows = {
        let conn = Connection::open(&outcome.project_db_path).unwrap();
        query_project_assembly_rows(&conn, project_id)
    };
    let add_zip_path = temp.path().join("add_ds4_workspace.zip");
    write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

    let (add_outcome, _progress) =
        import_workspace_add_dataset_package(&add_zip_path, &outcome.workspace_root).unwrap();

    assert_eq!(add_outcome.dataset_name, "ds4");
    assert_eq!(add_outcome.project_id, None);
    assert_eq!(
        count_rows(&outcome.project_db_path, "dataset"),
        2,
        "workspace catalog should include the new dataset"
    );
    let conn = Connection::open(&outcome.project_db_path).unwrap();
    let ds4_id: i64 = conn
        .query_row("SELECT id FROM dataset WHERE name = 'ds4'", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM project_dataset WHERE dataset_id = ?1",
            params![ds4_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        0,
        "workspace-level add must not inject the dataset into a project"
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "project_dataset"),
        original_project_dataset_count
    );
    assert_eq!(
        query_project_assembly_rows(&conn, project_id),
        original_assembly_rows,
        "workspace-level add must not append project assembly rows"
    );
}

#[test]
fn imports_add_dataset_package_into_legacy_workspace_without_prepare_options() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    fs::create_dir_all(bundle_root.join("runs/ds_a_vs_ref")).unwrap();
    fs::create_dir_all(bundle_root.join("runs/chr_r/ds_a_vs_self")).unwrap();
    fs::write(
        bundle_root.join("runs/ds_a_vs_ref/result.paf"),
        "d\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("runs/chr_r/ds_a_vs_self/result.paf"),
        "d\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n",
    )
    .unwrap();
    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    assert!(
        !outcome
            .workspace_root
            .join("metadata/prepare_options.tsv")
            .exists(),
        "fixture should simulate older packages without prepare_options.tsv"
    );
    let add_zip_path = temp.path().join("add_ds4_legacy_workspace.zip");
    write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

    let (add_outcome, _progress) =
        import_workspace_add_dataset_package(&add_zip_path, &outcome.workspace_root).unwrap();

    assert_eq!(add_outcome.dataset_name, "ds4");
    assert_eq!(dataset_stats(&outcome.project_db_path, "ds4"), Some((1, 4)));
}

#[test]
fn rejects_invalid_add_dataset_packages_without_mutating_existing_workspace() {
    let cases = [
        (
            "wrong package type",
            AddZipOptions {
                package_type: "full".to_string(),
                ..AddZipOptions::default()
            },
            "package_type",
        ),
        (
            "duplicate dataset",
            AddZipOptions {
                dataset_name: "ds_a".to_string(),
                ..AddZipOptions::default()
            },
            "already exists",
        ),
        (
            "reference mismatch",
            AddZipOptions {
                reference_name: "other_ref".to_string(),
                ..AddZipOptions::default()
            },
            "reference",
        ),
        (
            "score mismatch",
            AddZipOptions {
                chr_assignment_min_coverage_percent: "61".to_string(),
                ..AddZipOptions::default()
            },
            "chr_assignment_min_coverage_percent",
        ),
        (
            "layout mismatch",
            AddZipOptions {
                sequence_layout: "monolithic".to_string(),
                ..AddZipOptions::default()
            },
            "sequence_layout",
        ),
        (
            "skip self mismatch",
            AddZipOptions {
                skip_self: true,
                self_alignment_available: false,
                ..AddZipOptions::default()
            },
            "skip_self",
        ),
        (
            "alignment engine mismatch",
            AddZipOptions {
                alignment_engine: "blastn".to_string(),
                ..AddZipOptions::default()
            },
            "alignment_engine mismatch",
        ),
        (
            "minimap preset mismatch",
            AddZipOptions {
                minimap_preset: "asm5".to_string(),
                ..AddZipOptions::default()
            },
            "minimap_preset mismatch",
        ),
        (
            "missing payload",
            AddZipOptions {
                include_ref_paf: false,
                ..AddZipOptions::default()
            },
            "payload",
        ),
        (
            "missing server member order metadata",
            AddZipOptions {
                include_track_member_orders: false,
                ..AddZipOptions::default()
            },
            "metadata/track_member_orders.tsv",
        ),
        (
            "missing self alignment payload",
            AddZipOptions {
                include_self_paf: false,
                ..AddZipOptions::default()
            },
            "self alignment payload",
        ),
        (
            "missing pairwise alignment payload",
            AddZipOptions {
                include_pairwise_paf: false,
                ..AddZipOptions::default()
            },
            "pairwise alignment payload",
        ),
        (
            "unsafe dataset fasta path",
            AddZipOptions {
                dataset_fasta_relpath: "../outside.fa".to_string(),
                ..AddZipOptions::default()
            },
            "unsafe path traversal",
        ),
        (
            "unsafe locator path",
            AddZipOptions {
                locator_fasta_relpath: "../outside_partition.fa".to_string(),
                ..AddZipOptions::default()
            },
            "unsafe path traversal",
        ),
        (
            "unsafe windows locator path",
            AddZipOptions {
                locator_fasta_relpath: r"..\outside_partition.fa".to_string(),
                ..AddZipOptions::default()
            },
            "unsafe path separator",
        ),
        (
            "unexpected tel payload",
            AddZipOptions {
                include_tel_payload: true,
                ..AddZipOptions::default()
            },
            "tel_enabled=false",
        ),
        (
            "unexpected cen payload",
            AddZipOptions {
                include_cen_payload: true,
                ..AddZipOptions::default()
            },
            "cen_enabled=false",
        ),
        (
            "tel flag mismatch",
            AddZipOptions {
                tel_enabled: true,
                include_tel_payload: true,
                ..AddZipOptions::default()
            },
            "tel_enabled mismatch",
        ),
        (
            "unexpected payload file",
            AddZipOptions {
                include_extra_payload_file: true,
                ..AddZipOptions::default()
            },
            "unexpected add dataset payload file",
        ),
        (
            "locator row for unknown source rolls back copied payload",
            AddZipOptions {
                locator_seq_name: Some("missing_seq".to_string()),
                ..AddZipOptions::default()
            },
            "failed to resolve source_seq",
        ),
    ];

    for (name, options, expected_error) in cases {
        let temp = tempdir().unwrap();
        let (outcome, project_id) = import_workspace_with_project(temp.path());
        let original_dataset_count = count_rows(&outcome.project_db_path, "dataset");
        let original_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
        let original_datasets_tsv =
            fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap();
        let add_zip_path = temp.path().join(format!("{}.zip", name.replace(' ', "_")));
        write_add_dataset_zip(&add_zip_path, options);

        let error = import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id)
            .unwrap_err();

        assert!(
            error.to_string().contains(expected_error),
            "{name}: {error}"
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "dataset"),
            original_dataset_count,
            "{name} mutated dataset rows"
        );
        assert_eq!(
            count_rows(&outcome.project_db_path, "source_seq_locator"),
            original_locator_count,
            "{name} mutated locator rows"
        );
        assert_eq!(
            fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap(),
            original_datasets_tsv,
            "{name} mutated metadata/datasets.tsv"
        );
        assert!(
            !outcome.workspace_root.join("data/datasets/ds4.fa").exists(),
            "{name} left copied dataset fasta behind"
        );
    }
}

#[test]
fn add_dataset_import_rolls_back_when_assembly_append_fails() {
    let temp = tempdir().unwrap();
    let (outcome, project_id) = import_workspace_with_project(temp.path());
    crate::project_initializer::bootstrap_project_assembly(&outcome.project_db_path, project_id)
        .unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();
    conn.execute(
        "UPDATE assembly_seq SET orient = '-' WHERE project_id = ?1",
        params![project_id],
    )
    .unwrap();
    conn.execute(
        "UPDATE assembly_ctg
         SET name = 'x@r',
             ref_orient = '-'
         WHERE project_id = ?1",
        params![project_id],
    )
    .unwrap();
    let original_dataset_count = count_rows(&outcome.project_db_path, "dataset");
    let original_locator_count = count_rows(&outcome.project_db_path, "source_seq_locator");
    let original_assembly_rows = query_project_assembly_rows(&conn, project_id);
    let original_datasets_tsv =
        fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap();
    drop(conn);

    let add_zip_path = temp.path().join("add_ds4_conflict.zip");
    write_add_dataset_zip(&add_zip_path, AddZipOptions::default());

    let error =
        import_add_dataset_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap_err();

    assert!(
        error
            .to_string()
            .contains("failed to insert imported auto assembly_ctg"),
        "{error:#}"
    );
    let conn = Connection::open(&outcome.project_db_path).unwrap();
    assert_eq!(
        count_rows(&outcome.project_db_path, "dataset"),
        original_dataset_count
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq_locator"),
        original_locator_count
    );
    assert_eq!(
        query_project_assembly_rows(&conn, project_id),
        original_assembly_rows
    );
    assert_eq!(
        fs::read_to_string(outcome.workspace_root.join("metadata/datasets.tsv")).unwrap(),
        original_datasets_tsv
    );
    assert!(!outcome.workspace_root.join("data/datasets/ds4.fa").exists());
}
