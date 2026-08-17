use super::test_support::*;

#[test]
fn imports_add_ctg_package_into_target_track() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    add_second_chr_dataset_to_bundle_root(&bundle_root, true);
    write_prepare_options(&bundle_root, "asm10", false);
    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let project_id = insert_existing_project(&outcome.project_db_path);
    insert_support_project_dataset(&outcome.project_db_path, project_id, "ds_b", 2);
    crate::project_initializer::bootstrap_project_assembly(&outcome.project_db_path, project_id)
        .unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();
    let target_dataset_id: i64 = conn
        .query_row("SELECT id FROM dataset WHERE name = 'ds_a'", [], |row| {
            row.get(0)
        })
        .unwrap();
    drop(conn);

    let add_zip_path = temp.path().join("add_gap_filled.zip");
    write_add_ctg_zip(&add_zip_path);

    let (add_outcome, progress) =
        import_add_ctg_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap();

    assert_eq!(add_outcome.ctg_name, "gap_filled");
    assert_eq!(add_outcome.target_track, "ds_a");
    assert_eq!(add_outcome.target_chr, "r");
    assert!(add_outcome.assembly_ctg_id.is_some());
    assert!(progress.iter().any(|item| item.stage == "index_ref_paf"));
    assert!(
        progress
            .iter()
            .any(|item| item.stage == "index_pairwise_paf")
    );
    assert!(progress.iter().any(|item| {
        item.stage == "index_pairwise_paf_complete" && item.detail.contains("indexed_runs=2")
    }));

    let conn = Connection::open(&outcome.project_db_path).unwrap();
    let derived_dataset_id: i64 = conn
        .query_row(
            "SELECT id FROM dataset WHERE name = 'derived_ctg'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(add_outcome.dataset_id, derived_dataset_id);
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM source_seq WHERE dataset_id = ?1 AND seq_name = 'gap_filled'",
            params![derived_dataset_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*)
             FROM derived_ctg_track_member
             WHERE project_id = ?1
               AND source_seq_id = ?2
               AND target_dataset_id = ?3
               AND target_chr_name = 'r'",
            params![project_id, add_outcome.source_seq_id, target_dataset_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM ref_alignment_hit WHERE source_seq_id = ?1",
            params![add_outcome.source_seq_id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*)
             FROM pairwise_alignment_run
             WHERE run_name IN ('ds_a_vs_gap_filled', 'ds_b_vs_gap_filled')",
            [],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        2
    );
    drop(conn);

    let target_track_ctgs = crate::main_view::list_chr_view_ctgs(
        &outcome.project_db_path,
        project_id,
        Some("r"),
        Some(target_dataset_id),
    )
    .unwrap();
    assert_eq!(
        target_track_ctgs
            .iter()
            .map(|item| (item.name.as_str(), item.chr_order))
            .collect::<Vec<_>>(),
        vec![("gap_filled", Some(1)), ("d@r", Some(2))]
    );
    let derived_item = target_track_ctgs
        .iter()
        .find(|item| item.name == "gap_filled")
        .expect("derived ctg should appear in target track view");
    assert_eq!(derived_item.derived_source.as_deref(), Some("gapfiller"));
    assert_eq!(
        derived_item.derived_target_dataset_id,
        Some(target_dataset_id)
    );
    assert_eq!(derived_item.hits.len(), 2);
    let workspace_orders = read_imported_track_member_order_rows(&outcome.workspace_root).unwrap();
    assert_eq!(
        workspace_orders
            .iter()
            .filter(|row| row.target_track == "ds_a" && row.target_chr == "r")
            .map(|row| {
                (
                    row.member_dataset.as_str(),
                    row.member_ctg.as_str(),
                    row.member_order,
                )
            })
            .collect::<Vec<_>>(),
        vec![("derived_ctg", "gap_filled", 1), ("ds_a", "d", 2)]
    );
    assert!(
        workspace_orders
            .iter()
            .any(|row| row.target_track == "ds_b" && row.member_ctg == "e")
    );
}

#[test]
fn rejects_add_ctg_package_for_different_clicked_track() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    write_prepare_options(&bundle_root, "asm10", false);
    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let project_id = insert_existing_project(&outcome.project_db_path);
    let add_zip_path = temp.path().join("add_gap_filled.zip");
    write_add_ctg_zip(&add_zip_path);

    let error = import_add_ctg_package_with_hooks(
        &add_zip_path,
        &outcome.workspace_root,
        project_id,
        Some(AddCtgImportTarget {
            target_chr: "r".to_string(),
            target_track: "ds_b".to_string(),
        }),
        &mut |_| {},
        &mut || false,
    )
    .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("该 add_ctg 包属于 r / ds_a 轨道"),
        "unexpected error: {error}"
    );
}

#[test]
fn rejects_legacy_add_ctg_package_without_server_member_order_metadata() {
    let temp = tempdir().unwrap();
    let (outcome, project_id) = import_workspace_with_project(temp.path());
    let original_source_count = count_rows(&outcome.project_db_path, "source_seq");
    let add_zip_path = temp.path().join("legacy_add_gap_filled.zip");
    write_add_ctg_zip_with_order(&add_zip_path, false);

    let error =
        import_add_ctg_package(&add_zip_path, &outcome.workspace_root, project_id).unwrap_err();

    assert!(
        error
            .to_string()
            .contains("metadata/track_member_orders.tsv"),
        "{error:#}"
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq"),
        original_source_count
    );
    assert!(
        !outcome
            .workspace_root
            .join("data/derived_ctgs/gap_filled.fa")
            .exists()
    );
}
