use super::test_support::*;

fn materialize() -> tempfile::TempDir {
    materialize_named("frozen_server.json")
}

fn materialize_named(name: &str) -> tempfile::TempDir {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/grt_contract_v3")
        .join(name);
    let data: Value = serde_json::from_slice(&fs::read(fixture).unwrap()).unwrap();
    let temp = tempdir().unwrap();
    for (name, content) in data["files"].as_object().unwrap() {
        let path = temp.path().join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, content.as_str().unwrap()).unwrap();
    }
    temp
}
fn edit_json(root: &Path, relative: &str, edit: impl FnOnce(&mut Value)) {
    let path = root.join(relative);
    let mut data: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    edit(&mut data);
    fs::write(path, serde_json::to_vec_pretty(&data).unwrap()).unwrap();
}

#[test]
fn accepts_frozen_reverse_unassigned_q0_without_repair_events() {
    let temp = materialize();
    let package = validate_grt_package(temp.path()).unwrap();
    assert_eq!(
        one_row(&package.tables, "metadata/package.tsv").unwrap()["schema_version"],
        "3"
    );
    let card = &table(&package.tables, "metadata/grt_used_contigs.tsv")
        .unwrap()
        .rows[0];
    assert_eq!(card["placement_mode"], "grt_promoted");
    assert_eq!(card["orientation"], "-");
    assert_eq!(card["accepted_event_ids_json"], "[]");
    assert_eq!(card["pairwise_evidence_ids_json"], "[]");
}

#[test]
fn rejects_missing_frozen_artifact_binding() {
    let temp = materialize();
    edit_json(temp.path(), "metadata/grt_q0_freeze.json", |data| {
        data["artifacts"]
            .as_object_mut()
            .unwrap()
            .remove("metadata/grt_contig_quality.tsv");
    });
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(
        error.contains("incomplete frozen artifact inventory"),
        "{error}"
    );
}

#[test]
fn rejects_forged_source_availability_even_when_q0_dna_is_unchanged() {
    let temp = materialize();
    edit_json(temp.path(), "metadata/grt_q0_freeze.json", |data| {
        data["sources"][0]["available"] = serde_json::json!([{"start": 0, "end": 2000}]);
    });
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(error.contains("availability"), "{error}");
}

#[test]
fn rejects_missing_retained_root_card() {
    let temp = materialize();
    let path = temp.path().join("metadata/grt_used_contigs.tsv");
    let text = fs::read_to_string(&path).unwrap();
    fs::write(path, format!("{}\n", text.lines().next().unwrap())).unwrap();
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(error.contains("used cards do not exactly cover"), "{error}");
}

#[test]
fn rejects_final_path_evidence_not_matching_q4_source_map() {
    let temp = materialize();
    edit_json(temp.path(), "metadata/grt_final_path.json", |data| {
        data["chromosomes"][0]["segments"][0]["evidence_ids"] = serde_json::json!([]);
    });
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(error.contains("q4 source mapping"), "{error}");
}

#[test]
fn imports_and_persists_q0_root_provenance_without_fabricated_events() {
    let temp = materialize();
    let (outcome, _) = crate::importer::import_from_extracted_bundle(temp.path()).unwrap();
    let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
    assert_eq!(recipe.schema_version, "3");
    let card = load_grt_source_card_trace(&outcome.project_db_path, "only:only:chr1:grt_promoted")
        .unwrap();
    assert!(card.accepted_events.is_empty());
    assert_eq!(card.final_path_segments.len(), 1);
    let final_path = load_grt_final_path(&outcome.project_db_path).unwrap();
    assert_eq!(
        final_path["chromosomes"][0]["segments"][0]["source"]["orientation"],
        "-"
    );
    let verification = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap();
    assert_eq!(verification.chromosome_count, 1);
}

#[test]
fn accepts_multi_dataset_reverse_bridge_and_original_n_adjacency() {
    let temp = materialize_named("frozen_bridge_server.json");
    let package = validate_grt_package(temp.path()).unwrap();
    assert_eq!(
        package.final_path["chromosomes"].as_array().unwrap().len(),
        2
    );
    let c = package.final_path["chromosomes"][0]["segments"]
        .as_array()
        .unwrap()
        .iter()
        .find(|segment| segment["source"]["dataset"] == "c")
        .unwrap();
    assert_eq!(c["source"]["orientation"], "-");
    let card = table(&package.tables, "metadata/grt_used_contigs.tsv")
        .unwrap()
        .rows
        .iter()
        .find(|row| row["dataset_name"] == "c")
        .unwrap();
    assert_eq!(card["orientation"], "+");
    assert!(
        package.final_path["chromosomes"][1]["segments"]
            .as_array()
            .unwrap()
            .iter()
            .any(|segment| segment["kind"] == "gap" && segment["length"] == 137)
    );
}

#[test]
fn imports_schema3_app_full_and_no_fasta_without_server_audit_artifacts() {
    for name in ["frozen_app_full.json", "frozen_app_no_fasta.json"] {
        let temp = materialize_named(name);
        assert!(!temp.path().join("metadata/grt_q0_freeze.json").exists());
        let package = validate_grt_delivery_package_with_progress_and_cancel(
            temp.path(),
            &mut |_, _| {},
            &mut || false,
        )
        .unwrap();
        assert_eq!(
            one_row(&package.tables, "metadata/package.tsv").unwrap()["schema_version"],
            "3"
        );
        let (outcome, _) = crate::importer::import_from_extracted_bundle(temp.path()).unwrap();
        let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
        assert_eq!(recipe.schema_version, "3");
        let initialized =
            initialize_grt_project(&outcome.project_db_path, "q0-only-project").unwrap();
        assert_eq!(initialized.materialized_source_card_count, 1);
        let view =
            load_grt_project_view_for_project(&outcome.project_db_path, initialized.project_id)
                .unwrap();
        assert_eq!(view.source_cards.len(), 1);
        assert_eq!(
            view.final_path_by_chr["chr1"]["grt_display_available"],
            true
        );
        let path = load_grt_final_path(&outcome.project_db_path).unwrap();
        assert_eq!(
            path["chromosomes"][0]["segments"][0]["source"]["orientation"],
            "-"
        );
        if name == "frozen_app_full.json" {
            assert_eq!(
                verify_persisted_grt_final_path(&outcome.project_db_path)
                    .unwrap()
                    .chromosome_count,
                1
            );
        }
    }
}

#[test]
fn app_schema3_cannot_reuse_an_original_source_interval_even_without_fasta() {
    let temp = materialize_named("frozen_app_no_fasta.json");
    edit_json(temp.path(), "metadata/grt_final_path.json", |data| {
        let mut second = data["chromosomes"][0]["segments"][0].clone();
        second["segment_id"] = Value::String("repeated-root".to_string());
        data["chromosomes"][0]["segments"]
            .as_array_mut()
            .unwrap()
            .push(second);
        data["chromosomes"][0]["q4_length"] = serde_json::json!(4000);
    });
    let path: Value = serde_json::from_slice(
        &fs::read(temp.path().join("metadata/grt_final_path.json")).unwrap(),
    )
    .unwrap();
    let digest = sha256_bytes(serde_json::to_string(&path).unwrap().as_bytes());
    edit_json(temp.path(), "metadata/grt_app_manifest.json", |data| {
        data["final_path_sha256"] = Value::String(digest);
        data["q4_length_bp"] = serde_json::json!(4000);
        data["q4_chromosome_lengths"]["chr1"] = serde_json::json!(4000);
    });
    let error = validate_grt_delivery_package_with_progress_and_cancel(
        temp.path(),
        &mut |_, _| {},
        &mut || false,
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("INVALID_SOURCE_PATH"), "{error}");
}

#[test]
fn source_free_event_cannot_be_forged_into_an_accepted_source_edit() {
    let temp = materialize();
    let path = temp.path().join("metadata/grt_events.jsonl");
    let mut events = fs::read_to_string(&path)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    let event = events
        .iter_mut()
        .find(|event| event["source"].is_null())
        .expect("fixture retains a source-free event");
    event["action"] = Value::String("fill".to_string());
    event["status"] = Value::String("accepted".to_string());
    let text = events
        .iter()
        .map(|event| serde_json::to_string(event).unwrap())
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    fs::write(path, text).unwrap();
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(error.contains("requires source provenance"), "{error}");
}

#[test]
fn later_project_dataset_does_not_join_the_locked_q0_input_set() {
    let temp = materialize();
    let fixture: Value = serde_json::from_slice(
        &fs::read(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../tests/fixtures/grt_contract_v3/post_freeze_dataset.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let freeze_path = temp.path().join("metadata/grt_q0_freeze.json");
    let before = fs::read(&freeze_path).unwrap();
    for (name, text) in fixture["append"].as_object().unwrap() {
        let path = temp.path().join(name);
        let content = fs::read_to_string(&path).unwrap() + text.as_str().unwrap();
        fs::write(path, content).unwrap();
    }
    for (name, text) in fixture["files"].as_object().unwrap() {
        fs::write(temp.path().join(name), text.as_str().unwrap()).unwrap();
    }
    validate_grt_package(temp.path()).unwrap();
    assert_eq!(fs::read(&freeze_path).unwrap(), before);
    let (outcome, _) = crate::importer::import_from_extracted_bundle(temp.path()).unwrap();
    let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
    assert_eq!(recipe.primary_dataset, "only");
    edit_json(temp.path(), "metadata/grt_q0_freeze.json", |data| {
        data["source_fastas"]["later"] = Value::String("data/datasets/later.fa".to_string());
    });
    let error = validate_grt_package(temp.path()).unwrap_err().to_string();
    assert!(error.contains("locked recipe datasets"), "{error}");
}
