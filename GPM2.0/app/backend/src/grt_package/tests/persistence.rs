use super::test_support::*;

#[test]
fn imports_shared_fixture_and_round_trips_recipe_final_path_and_trace_links() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let attempts_path = bundle_root.join("metadata/grt_gap_attempts.tsv");
    let attempts = fs::read_to_string(&attempts_path).unwrap();
    fs::write(
        attempts_path,
        format!(
            "{attempts}attempt-terminal-right\tChr01\tterminal-right\tstep4_telomere\tunresolved\tno_candidate\t0\t\n"
        ),
    )
    .unwrap();

    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
    let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
    assert_eq!(recipe.recipe_id, "recipe-test");
    assert_eq!(recipe.primary_dataset, "primary");
    assert_eq!(recipe.support_datasets, vec!["support"]);

    let final_path = load_grt_final_path(&outcome.project_db_path).unwrap();
    assert_eq!(
        final_path["chromosomes"][0]["q4_sha256"],
        "a6c7cf707ec32204560c3967f3af57cb57cd3faa8302c0a1a6f36a5d78abfa2e"
    );
    let final_path_by_chr = load_grt_final_path_by_chr(&outcome.project_db_path).unwrap();
    assert_eq!(final_path_by_chr.len(), 1);
    assert_eq!(
        final_path_by_chr["Chr01"]["segments"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    assert!(
        final_path_by_chr["Chr01"]["segments"][0]
            .get("event_id")
            .is_none()
    );
    assert!(
        final_path_by_chr["Chr01"]["segments"][1]
            .get("evidence_ids")
            .is_none()
    );
    assert_eq!(
        final_path_by_chr["Chr01"]["segments"][0]["source_length"],
        4
    );
    assert_eq!(
        final_path_by_chr["Chr01"]["segments"][1]["source_length"],
        4
    );
    let object_attempts = load_grt_object_attempts(&outcome.project_db_path).unwrap();
    assert_eq!(object_attempts.len(), 2);
    assert_eq!(object_attempts[0]["object_kind"], "gap");
    assert_eq!(object_attempts[1]["object_kind"], "terminal");

    let card = load_grt_source_card_trace(
        &outcome.project_db_path,
        "support:donor1:Chr01:grt_promoted",
    )
    .unwrap();
    assert_eq!(card.accepted_events.len(), 1);
    assert_eq!(card.final_path_segments.len(), 1);
    assert_eq!(card.ref_evidence.len(), 1);
    assert_eq!(card.pairwise_evidence.len(), 1);
    assert_eq!(card.donor_usage.len(), 1);
    assert_eq!(card.donor_members.len(), 1);
    assert_eq!(card.donor_sets.len(), 1);
    let evidence = load_grt_evidence(&outcome.project_db_path, "ev-step1-round1").unwrap();
    assert_eq!(evidence["source_start"], "1");
    assert_eq!(evidence["source_end"], "4");
    assert_eq!(evidence["target_start"], "5");
    assert_eq!(evidence["target_end"], "8");
    assert_eq!(evidence["coordinate_system"], "paf_0_based_half_open");
    assert_eq!(evidence["projection_status"], "projected");

    let event = load_grt_event_trace(&outcome.project_db_path, "evt-step1-round1").unwrap();
    assert_eq!(event.evidence.len(), 1);
    assert_eq!(event.donor_usage.len(), 1);
    assert!(event.final_path_segment.is_some());
    assert!(event.source_card.is_some());

    let verification = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap();
    assert_eq!(verification.chromosome_count, 1);
    assert_eq!(verification.segment_count, 2);
    assert_eq!(verification.q4_artifact_sha256, recipe.q4_artifact_sha256);
}

#[test]
fn initializes_locked_recipe_and_materializes_used_unplaced_source_card() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();

    let initialized = initialize_grt_project(&outcome.project_db_path, "locked-project")
        .expect("initialize locked GRT project");
    assert_eq!(initialized.primary_dataset_id, 1);
    assert_eq!(initialized.support_dataset_ids, vec![2]);
    assert_eq!(initialized.project_dataset_count, 2);
    assert_eq!(initialized.assembly_seq_count, 4);
    assert_eq!(initialized.assembly_ctg_count, 4);
    assert_eq!(initialized.materialized_source_card_count, 1);

    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    let promoted: (String, String, String, String) = conn
        .query_row(
            "SELECT d.name, ss.seq_name, c.assigned_chr_name, c.placement_mode
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE c.project_id = ?1 AND c.placement_mode = 'grt_promoted'",
            params![initialized.project_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(
        promoted,
        (
            "support".to_string(),
            "donor1".to_string(),
            "Chr01".to_string(),
            "grt_promoted".to_string(),
        )
    );
    let auto_pipeline_done: i64 = conn
        .query_row(
            "SELECT auto_pipeline_done FROM project WHERE id = ?1",
            params![initialized.project_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(auto_pipeline_done, 1);
    let final_counts: (i64, i64) = conn
        .query_row(
            "SELECT
                (SELECT COUNT(*) FROM assembly_seq WHERE project_id = ?1),
                (SELECT COUNT(*) FROM assembly_ctg WHERE project_id = ?1)",
            params![initialized.project_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(final_counts, (4, 4));

    let view = load_grt_project_view(&outcome.project_db_path).unwrap();
    assert_eq!(view.recipe.recipe_id, "recipe-test");
    assert_eq!(view.final_path_by_chr.len(), 1);
    assert_eq!(view.source_cards.len(), 1);
    assert_eq!(view.source_cards[0].placement_mode, "grt_promoted");
    let serialized = serde_json::to_value(&view).unwrap();
    assert!(serialized.get("object_attempts").is_none());
    assert_eq!(serialized["source_cards"][0].as_object().unwrap().len(), 6);
    assert!(
        serialized["source_cards"][0]
            .get("accepted_events")
            .is_none()
    );
    assert!(
        serialized["final_path_by_chr"]["Chr01"]["segments"][0]
            .get("event_id")
            .is_none()
    );
}

#[test]
fn display_contract_project_view_maps_segments_to_project_ctgs_or_disables_chromosome() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
    let initialized = initialize_grt_project(&outcome.project_db_path, "display-project").unwrap();
    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    conn.execute(
        "UPDATE grt_package SET final_path_schema_version = ?1 WHERE id = 1",
        params![GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION],
    )
    .unwrap();
    drop(conn);

    let view = load_grt_project_view_for_project(&outcome.project_db_path, initialized.project_id)
        .unwrap();
    let chr = &view.final_path_by_chr["Chr01"];
    assert_eq!(chr["grt_display_available"], true);
    for segment in chr["segments"].as_array().unwrap() {
        assert!(segment["assembly_ctg_id"].as_i64().unwrap() > 0);
        assert_eq!(segment["assembly_source_start"], 1);
        assert_eq!(segment["assembly_source_end"], 4);
    }

    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    conn.execute(
        "UPDATE assembly_seq SET hidden = 1
         WHERE project_id = ?1
           AND source_seq_id = (
               SELECT ss.id
               FROM source_seq ss
               JOIN dataset d ON d.id = ss.dataset_id
               WHERE d.name = 'support' AND ss.seq_name = 'donor1'
           )",
        params![initialized.project_id],
    )
    .unwrap();
    drop(conn);

    let view = load_grt_project_view_for_project(&outcome.project_db_path, initialized.project_id)
        .unwrap();
    let chr = &view.final_path_by_chr["Chr01"];
    assert_eq!(chr["grt_display_available"], false);
    assert!(chr["segments"][0].get("assembly_ctg_id").is_none());
    assert!(chr["segments"][1].get("assembly_ctg_id").is_none());
}

#[test]
fn project_view_reuses_persisted_verification_without_reading_q4() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
    let expected = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap();
    let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
    let q4_path = outcome
        .project_db_path
        .parent()
        .unwrap()
        .join(recipe.final_q_relpath);
    fs::remove_file(&q4_path).unwrap();

    let view = load_grt_project_view(&outcome.project_db_path).unwrap();
    assert_eq!(view.verification, expected);

    let error = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap_err();
    assert!(error.to_string().contains("failed to read artifact"));
}

#[test]
fn initialization_cleans_project_when_assignment_projection_is_corrupted() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    let primary_source_seq_id: i64 = conn
        .query_row(
            "SELECT ss.id
             FROM source_seq ss
             JOIN dataset d ON d.id = ss.dataset_id
             WHERE d.name = 'primary' AND ss.seq_name = 'primary1'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    conn.execute_batch(&format!(
        "CREATE TRIGGER corrupt_assignment_projection
         AFTER INSERT ON assembly_seq
         WHEN NEW.source_seq_id = {primary_source_seq_id}
         BEGIN
             UPDATE assembly_seq SET orient = '-' WHERE id = NEW.id;
         END;"
    ))
    .unwrap();
    drop(conn);

    let error = initialize_grt_project(&outcome.project_db_path, "corrupt-project")
        .expect_err("projection mismatch must reject locked project initialization");
    assert!(
        error
            .to_string()
            .contains("disagrees with main-view source orientation or anchor")
    );

    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    let project_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM project WHERE name = 'corrupt-project'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(project_count, 0);
}

#[test]
fn initializes_locked_recipe_with_requested_phased_assembly_capability() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();

    let initialized = initialize_grt_project_with_options(
        &outcome.project_db_path,
        "phased-locked-project",
        true,
    )
    .expect("initialize phased locked GRT project");
    assert!(initialized.phased_assembly_enabled);

    let conn = open_workspace_db(&outcome.project_db_path).unwrap();
    let enabled: i64 = conn
        .query_row(
            "SELECT phased_assembly_enabled FROM project WHERE id = ?1",
            params![initialized.project_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(enabled, 1);
}
