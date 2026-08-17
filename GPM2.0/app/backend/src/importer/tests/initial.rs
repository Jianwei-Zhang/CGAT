use super::test_support::*;

#[test]
fn imports_extracted_bundle_and_prepares_workspace_in_bundle_root() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);

    let (outcome, progress) = import_from_extracted_bundle(&bundle_root).unwrap();

    assert_eq!(outcome.mode, ImportMode::ExtractedBundle);
    assert_eq!(outcome.bundle_root, bundle_root);
    assert_eq!(outcome.workspace_root, outcome.bundle_root);
    assert!(outcome.project_db_path.exists());
    assert!(outcome.workspace_root.join(EXPORTS_DIR).exists());
    assert!(outcome.workspace_root.join(CACHE_DIR).exists());
    assert_eq!(count_rows(&outcome.project_db_path, "reference_genome"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "reference_chr"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
    assert_eq!(
        dataset_stats(&outcome.project_db_path, "ds_a"),
        Some((1, 2))
    );
    assert_eq!(progress.last().unwrap().stage, "complete");
}

#[test]
fn imports_zip_delivery_and_prepares_named_workspace() {
    let temp = tempdir().unwrap();
    let zip_path = temp.path().join("delivery.zip");
    write_bundle_zip(&zip_path);

    let workspace_root = temp.path().join("workspaces").join("project_alpha");
    let (outcome, progress) = import_from_zip(&zip_path, &workspace_root).unwrap();

    assert_eq!(outcome.mode, ImportMode::ZipDelivery);
    assert_eq!(outcome.bundle_root, workspace_root);
    assert_eq!(outcome.workspace_root, workspace_root);
    assert!(outcome.project_db_path.exists());
    assert!(outcome.workspace_root.join(EXPORTS_DIR).exists());
    assert!(outcome.workspace_root.join(CACHE_DIR).exists());
    assert!(looks_like_bundle_root(&outcome.bundle_root));
    assert!(!outcome.workspace_root.join("gpm_server").exists());
    assert_eq!(count_rows(&outcome.project_db_path, "reference_genome"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "dataset"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "reference_chr"), 1);
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), 1);
    assert_eq!(
        dataset_stats(&outcome.project_db_path, "ds_a"),
        Some((1, 4))
    );
    assert_eq!(progress.last().unwrap().stage, "complete");
    assert!(progress.iter().all(|item| item.progress_index.is_some()
        && item.progress_total == progress.last().unwrap().progress_total));
    assert!(progress.iter().all(|item| item.phase_total == Some(7)));
    assert_eq!(progress.first().unwrap().phase_index, Some(1));
    assert_eq!(progress.last().unwrap().phase_index, Some(7));
    assert!(progress.windows(2).all(|items| {
        items[0].phase_index.unwrap_or_default() <= items[1].phase_index.unwrap_or_default()
    }));
    let stages = progress.iter().map(|item| item.stage).collect::<Vec<_>>();
    let normalize_index = stages
        .iter()
        .position(|stage| *stage == "normalize_workspace_layout")
        .unwrap();
    let validation_start_index = stages
        .iter()
        .position(|stage| *stage == "validate_grt_contract_start")
        .unwrap();
    let validation_complete_index = stages
        .iter()
        .position(|stage| *stage == "validate_grt_contract")
        .unwrap();
    assert!(normalize_index < validation_start_index);
    assert!(validation_start_index < validation_complete_index);
    assert!(stages.contains(&"validate_grt_source_fastas"));
    assert!(stages.contains(&"validate_grt_final_path"));
    assert!(
        progress
            .iter()
            .filter(|item| item.stage == "extract_entry")
            .all(|item| !item.detail.contains(" (") && !item.detail.ends_with(')'))
    );
    assert!(
        progress
            .last()
            .unwrap()
            .progress_total
            .is_some_and(|total| total > 0)
    );
}

#[test]
fn rejects_zip_delivery_without_required_grt_payload_and_cleans_workspace() {
    let temp = tempdir().unwrap();
    let zip_path = temp.path().join("delivery-light.zip");
    write_bundle_zip_without_fasta(&zip_path);

    let workspace_root = temp.path().join("workspaces").join("project_alpha");
    let mut observed_progress = Vec::new();
    let error = import_from_zip_with_hooks(
        &zip_path,
        &workspace_root,
        &mut |step| observed_progress.push(step),
        &mut || false,
    )
    .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("GRT_IMPORT_MISSING_REQUIRED_FILE")
    );
    assert!(!workspace_root.exists());
    assert_eq!(
        observed_progress.last().map(|step| step.stage),
        Some("validate_grt_required_files")
    );
    assert_eq!(
        observed_progress.last().and_then(|step| step.phase_index),
        Some(4)
    );
}

#[test]
fn imports_zip_delivery_with_skipped_self_alignment_capability() {
    let temp = tempdir().unwrap();
    let zip_path = temp.path().join("delivery-no-self.zip");
    write_bundle_zip_with_self_alignment_flag(&zip_path, false);

    let workspace_root = temp.path().join("workspaces").join("project_alpha");
    let (outcome, _progress) = import_from_zip(&zip_path, &workspace_root).unwrap();
    let options =
        crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();

    assert_eq!(
        options
            .datasets
            .first()
            .map(|dataset| dataset.self_alignment_available),
        Some(false)
    );
}

#[test]
fn imports_server_package_metadata_and_chr_assignments() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::write(
        bundle_root.join("metadata/chr_assignments.tsv"),
        concat!(
            "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\n",
            "ds_a\td\t2\tr\t-\tref_alignment\t2\t100.000\t9\n",
        ),
    )
    .unwrap();
    install_minimal_grt_contract(&bundle_root);
    fs::write(
        bundle_root.join("metadata/package.tsv"),
        concat!(
            "workflow\tschema_version\tpackage_mode\tsequence_layout\tpreassigned_chr\tself_alignment_scope\tcross_alignment_scope\tchr_assignment_min_coverage_percent\tgrt_precompute_enabled\trecipe_locked\tfinal_path_schema_version\treads_qc_enabled\n",
            "gpm_grt_precomputed_v2\t2\tfast\tpartitioned\ttrue\tchr_partition\tchr_partition\t72\ttrue\ttrue\t1\tfalse\n",
        ),
    )
    .unwrap();

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();

    let metadata_row: (String, String, i64, f64, String, String) = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr, chr_assignment_min_coverage_percent, self_alignment_scope, cross_alignment_scope
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            },
        )
        .unwrap();
    assert_eq!(
        metadata_row,
        (
            "fast".to_string(),
            "partitioned".to_string(),
            1,
            72.0,
            "chr_partition".to_string(),
            "chr_partition".to_string(),
        )
    );

    let imported_row = conn
        .query_row(
            "SELECT source_orientation, orientation_source, support_bp,
                    support_percent, anchor_start
             FROM imported_chr_assignment",
            [],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, f64>(3)?,
                    row.get::<_, i64>(4)?,
                ))
            },
        )
        .unwrap();
    assert_eq!(
        imported_row,
        ("-".to_string(), "ref_alignment".to_string(), 2, 100.0, 9)
    );
    assert_eq!(
        conn.query_row(
            "SELECT member_order FROM imported_track_member_order",
            [],
            |row| row.get::<_, i64>(0),
        )
        .unwrap(),
        1
    );
}

#[test]
fn imports_optional_telomere_rules_and_marks() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::create_dir_all(bundle_root.join("tel/chr_r")).unwrap();
    fs::write(
        bundle_root.join("tel/rules.tsv"),
        "rule_id\tmotif\tmin_repeat\treverse_complement\ntel1\tTTAGGG\t20\ttrue\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("tel/chr_r/ds_a.tsv"),
        concat!(
            "rule_id\tdataset_name\tseq_name\tassigned_chr_name\tmotif\tmin_repeat\trepeat_count\tstart_bp\tend_bp\tstrand\n",
            "tel1\tds_a\td\tr\tTTAGGG\t20\t21\t3\t128\t+\n",
        ),
    )
    .unwrap();

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();

    let rule_row: (String, String, i64, i64) = conn
        .query_row(
            "SELECT rule_id, motif, min_repeat, reverse_complement FROM telomere_rule WHERE rule_id = 'tel1'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(rule_row, ("tel1".to_string(), "TTAGGG".to_string(), 20, 1));

    let mark_row: (String, String, String, i64, i64, i64, i64, String) = conn
        .query_row(
            "SELECT tr.rule_id, tr.motif, tm.assigned_chr_name, tm.min_repeat, tm.repeat_count, tm.start_bp, tm.end_bp, tm.strand
             FROM source_seq_telomere_mark tm
             JOIN telomere_rule tr ON tr.rule_id = tm.rule_id
             JOIN source_seq ss ON ss.id = tm.source_seq_id
             WHERE ss.seq_name = 'd'",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                ))
            },
        )
        .unwrap();
    assert_eq!(
        mark_row,
        (
            "tel1".to_string(),
            "TTAGGG".to_string(),
            "r".to_string(),
            20,
            21,
            3,
            128,
            "+".to_string(),
        )
    );
}

#[test]
fn imports_optional_centromere_marks() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::create_dir_all(bundle_root.join("cen/chr_r")).unwrap();
    fs::write(
        bundle_root.join("cen/reference.tsv"),
        "cen_id\tchr_name\tsequence_name\tfasta_relpath\tmin_len\tmin_identity\ncen\tr\tr_centromere\tdata/centromere/ref_cen.fa\t10000\t80\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("cen/chr_r/marks.tsv"),
        concat!(
            "cen_id\tchr_name\tquery_name\tdataset_name\tctg_name\tctg_start\tctg_end\tstrand\talign_length\tidentity\tmapq\n",
            "cen\tr\tr_centromere\tds_a\td\t3\t128\t+\t126\t96.500\t60\n",
        ),
    )
    .unwrap();

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();

    let mark_row: (String, String, String, i64, i64, String, i64, f64, i64) = conn
        .query_row(
            "SELECT cm.cen_id, cm.assigned_chr_name, cm.query_name, cm.start_bp, cm.end_bp, cm.strand, cm.align_length, cm.identity, cm.mapq
             FROM source_seq_centromere_mark cm
             JOIN source_seq ss ON ss.id = cm.source_seq_id
             WHERE ss.seq_name = 'd'",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                    row.get(8)?,
                ))
            },
        )
        .unwrap();
    assert_eq!(
        mark_row,
        (
            "cen".to_string(),
            "r".to_string(),
            "r_centromere".to_string(),
            3,
            128,
            "+".to_string(),
            126,
            96.5,
            60,
        )
    );
}

#[test]
fn imports_source_seq_n_regions() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::write(
        bundle_root.join("metadata/source_seq_n_regions.tsv"),
        "dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\nds_a\td\t2\t2\t1\n",
    )
    .unwrap();

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();

    let region_row: (String, i64, i64, i64) = conn
        .query_row(
            "SELECT ss.seq_name, nr.start_bp, nr.end_bp, nr.length_bp
             FROM source_seq_n_region nr
             JOIN source_seq ss ON ss.id = nr.source_seq_id",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(region_row, ("d".to_string(), 2, 2, 1));
}

#[test]
fn rejects_non_partitioned_package_metadata() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::write(
        bundle_root.join("metadata/package.tsv"),
        concat!(
            "workflow\tschema_version\tpackage_mode\tsequence_layout\tpreassigned_chr\tself_alignment_scope\tcross_alignment_scope\tchr_assignment_min_coverage_percent\tgrt_precompute_enabled\trecipe_locked\tfinal_path_schema_version\treads_qc_enabled\n",
            "gpm_grt_precomputed_v2\t2\tfull\tmonolithic\tfalse\tnone\tchr_partition\t60\ttrue\ttrue\t1\tfalse\n",
        ),
    )
    .unwrap();

    let error = import_from_extracted_bundle(&bundle_root).unwrap_err();
    assert!(error.to_string().contains("partitioned"));
}

#[test]
fn imports_partitioned_fast_locators_and_reports_fasta_available_when_payload_exists() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);

    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = Connection::open(&outcome.project_db_path).unwrap();

    let metadata_row: (String, String, i64) = conn
        .query_row(
            "SELECT package_mode, sequence_layout, preassigned_chr
             FROM workspace_package_metadata
             WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(
        metadata_row,
        ("fast".to_string(), "partitioned".to_string(), 1)
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "reference_chr_locator"),
        1
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq_locator"),
        1
    );

    let dataset_locator_path: String = conn
        .query_row(
            "SELECT ssl.fasta_path
             FROM source_seq_locator ssl
             JOIN source_seq ss ON ss.id = ssl.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE d.name = 'ds_a' AND ss.seq_name = 'd'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert!(dataset_locator_path.ends_with("data/partitions/chr/r/ds_a.fa"));

    let options =
        crate::project_initializer::list_initializer_options(&outcome.project_db_path).unwrap();
    assert_eq!(
        options
            .datasets
            .first()
            .map(|dataset| dataset.fasta_available),
        Some(true)
    );
}

#[test]
fn rejects_initial_package_without_required_grt_payload() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, false);

    let error = import_from_extracted_bundle(&bundle_root).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("GRT_IMPORT_MISSING_REQUIRED_FILE")
    );
    assert!(!bundle_root.join(PROJECT_DB_NAME).exists());
}

#[test]
fn imports_partitioned_alignment_pafs_into_global_hit_tables() {
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

    let (outcome, progress) = import_from_extracted_bundle(&bundle_root).unwrap();

    assert_eq!(count_rows(&outcome.project_db_path, "ref_alignment_hit"), 1);
    assert_eq!(
        count_rows(&outcome.project_db_path, "pairwise_alignment_run"),
        1
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "pairwise_alignment_hit"),
        0
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "pairwise_alignment_scope"),
        0
    );
    assert!(
        progress
            .iter()
            .any(|item| item.stage == "index_ref_paf" && item.detail.contains("ds_a_vs_ref"))
    );
    assert!(progress.iter().any(
        |item| item.stage == "index_pairwise_paf" && item.detail.contains("chr_r/ds_a_vs_self")
    ));
    let log_text = fs::read_to_string(outcome.workspace_root.join("cache/import.log")).unwrap();
    assert!(log_text.contains("index_ref_paf"));
    assert!(log_text.contains("index_pairwise_paf"));
}

#[test]
fn rejects_non_zip_input_file() {
    let temp = tempdir().unwrap();
    let bad_path = temp.path().join("delivery.txt");
    fs::write(&bad_path, "not zip").unwrap();
    let workspace_root = temp.path().join("workspaces").join("project_alpha");

    let error = import_from_zip(&bad_path, &workspace_root).unwrap_err();
    assert!(error.to_string().contains("expected a .zip file"));
}

#[test]
fn rejects_delivery_without_track_member_order_metadata() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_bundle_root(&bundle_root);
    fs::remove_file(bundle_root.join("metadata/track_member_orders.tsv")).unwrap();

    let error = import_from_extracted_bundle(&bundle_root).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("metadata/track_member_orders.tsv")
    );
}
