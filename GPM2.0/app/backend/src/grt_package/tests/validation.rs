use super::test_support::*;
use crate::grt_package::delivery_validator::validate_app_final_path_manifest_hash;

#[test]
fn project_view_uses_authoritative_source_lengths_for_repeated_and_split_segments() {
    let source_lengths = HashMap::from([
        (
            ("hifiasm".to_string(), "ptg000002l".to_string()),
            43_726_252,
        ),
        (("flye".to_string(), "scaffold_50".to_string()), 30_370_176),
    ]);
    let chromosome = serde_json::json!({
        "chr": "Chr01",
        "q4_length": 1,
        "q4_sha256": "sha",
        "segments": [
            {
                "segment_id": "patch-1",
                "kind": "patch",
                "length": 8,
                "source": {
                    "dataset": "hifiasm",
                    "contig": "ptg000002l",
                    "start": 28_911_536,
                    "end": 28_911_543,
                    "orientation": "-"
                }
            },
            {
                "segment_id": "patch-2",
                "kind": "patch",
                "length": 5_493,
                "source": {
                    "dataset": "hifiasm",
                    "contig": "ptg000002l",
                    "start": 22_716_743,
                    "end": 22_722_235,
                    "orientation": "-"
                }
            },
            {
                "segment_id": "source-left",
                "kind": "source",
                "length": 30_205_115,
                "source": {
                    "dataset": "flye",
                    "contig": "scaffold_50",
                    "start": 1,
                    "end": 30_205_115,
                    "orientation": "+"
                }
            },
            {
                "segment_id": "source-right",
                "kind": "source",
                "length": 164_937,
                "source": {
                    "dataset": "flye",
                    "contig": "scaffold_50",
                    "start": 30_205_229,
                    "end": 30_370_165,
                    "orientation": "+"
                }
            }
        ]
    });

    let projected =
        project_grt_final_path_chromosome(chromosome, "Chr01", &source_lengths).unwrap();
    let segments = projected["segments"].as_array().unwrap();
    assert_eq!(segments[0]["source_length"], 43_726_252);
    assert_eq!(segments[1]["source_length"], 43_726_252);
    assert_eq!(segments[2]["source_length"], 30_370_176);
    assert_eq!(segments[3]["source_length"], 30_370_176);
    assert_eq!(segments[0]["source"]["start"], 28_911_536);
    assert_eq!(segments[0]["source"]["end"], 28_911_543);
    assert_eq!(segments[3]["source"]["start"], 30_205_229);
    assert_eq!(segments[3]["source"]["end"], 30_370_165);
}

#[test]
fn project_view_rejects_missing_or_out_of_range_source_lengths() {
    let chromosome = serde_json::json!({
        "chr": "Chr01",
        "q4_length": 1,
        "q4_sha256": "sha",
        "segments": [{
            "segment_id": "source-1",
            "kind": "source",
            "length": 5,
            "source": {
                "dataset": "primary",
                "contig": "ctg1",
                "start": 8,
                "end": 12,
                "orientation": "+"
            }
        }]
    });

    let missing_error =
        project_grt_final_path_chromosome(chromosome.clone(), "Chr01", &HashMap::new())
            .unwrap_err();
    assert!(
        missing_error
            .to_string()
            .contains("missing source primary:ctg1")
    );

    let out_of_range_error = project_grt_final_path_chromosome(
        chromosome,
        "Chr01",
        &HashMap::from([(("primary".to_string(), "ctg1".to_string()), 10)]),
    )
    .unwrap_err();
    assert!(
        out_of_range_error
            .to_string()
            .contains("interval 8-12 exceeds source length 10")
    );
}

#[test]
fn validates_shared_grt_v2_fixture() {
    let package = validate_grt_package(&fixture_root()).unwrap();
    assert_eq!(package.final_path["workflow"].as_str(), Some(GRT_WORKFLOW));
    assert_eq!(package.events.len(), 1);
}

#[test]
fn validates_app_final_path_manifest_canonical_hash() {
    let final_path = serde_json::json!({"b": 2, "a": 1});
    let manifest = serde_json::json!({
        "final_path_sha256": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    });

    validate_app_final_path_manifest_hash(&final_path, manifest.as_object().unwrap()).unwrap();

    let mut tampered_manifest = manifest;
    tampered_manifest["final_path_sha256"] = serde_json::json!("0".repeat(64));
    let error =
        validate_app_final_path_manifest_hash(&final_path, tampered_manifest.as_object().unwrap())
            .unwrap_err();
    assert!(error.to_string().contains("GRT_IMPORT_HASH_MISMATCH"));
}

#[test]
fn validates_schema_three_display_evidence_links_coordinates_and_enums() {
    let base = serde_json::json!({
        "display_evidence": [{
            "evidence_id": "grt-display-local-1",
            "event_id": "event-1",
            "final_path_segment_id": "patch-1",
            "stage": "step3",
            "action": "refill",
            "association": "supporting_precursor",
            "supporting_event_id": "event-precursor",
            "tool": "mummer",
            "preset": "nucmer-profile",
            "role": "left_anchor",
            "aligned_length": 801,
            "identity": 0.998,
            "mapq": null,
            "source": {
                "dataset": "support",
                "contig": "donor1",
                "start": 100,
                "end": 900,
                "orientation": "+"
            },
            "target": {
                "dataset": "primary",
                "contig": "primary1",
                "start": 200,
                "end": 1000,
                "orientation": "+"
            }
        }]
    });
    let sources = HashMap::from([
        (("support".to_string(), "donor1".to_string()), 2_000),
        (("primary".to_string(), "primary1".to_string()), 2_000),
    ]);
    let cards = HashSet::from([
        (
            "support".to_string(),
            "donor1".to_string(),
            "Chr01".to_string(),
        ),
        (
            "primary".to_string(),
            "primary1".to_string(),
            "Chr01".to_string(),
        ),
    ]);
    let segment_events = HashMap::from([("patch-1".to_string(), "event-1".to_string())]);

    validate_app_display_evidence(
        base.as_object().unwrap(),
        "Chr01",
        &segment_events,
        &mut HashSet::new(),
        &sources,
        &cards,
    )
    .unwrap();

    for (field, value, expected) in [
        ("tool", serde_json::json!("blast"), "INVALID_VALUE"),
        ("role", serde_json::json!("middle_anchor"), "INVALID_VALUE"),
        (
            "event_id",
            serde_json::json!("missing-event"),
            "BROKEN_REFERENCE",
        ),
    ] {
        let mut invalid = base.clone();
        invalid["display_evidence"][0][field] = value;
        let error = validate_app_display_evidence(
            invalid.as_object().unwrap(),
            "Chr01",
            &segment_events,
            &mut HashSet::new(),
            &sources,
            &cards,
        )
        .unwrap_err();
        assert!(error.to_string().contains(expected), "{field}: {error}");
    }

    let mut out_of_range = base.clone();
    out_of_range["display_evidence"][0]["source"]["end"] = serde_json::json!(2_001);
    let error = validate_app_display_evidence(
        out_of_range.as_object().unwrap(),
        "Chr01",
        &segment_events,
        &mut HashSet::new(),
        &sources,
        &cards,
    )
    .unwrap_err();
    assert!(error.to_string().contains("INVALID_COORDINATE"));
}

#[test]
fn app_source_cards_accept_signed_normal_anchor_and_require_positive_grt_anchor() {
    let normal_card = "support:multi:Chr04:normal";
    let normal_row = BTreeMap::from([
        ("source_card_key".to_string(), normal_card.to_string()),
        ("dataset_name".to_string(), "support".to_string()),
        ("contig_name".to_string(), "multi".to_string()),
        ("original_assignment".to_string(), "assigned".to_string()),
        ("target_chr".to_string(), "Chr04".to_string()),
        ("placement_mode".to_string(), "normal".to_string()),
        ("ref_alignment_status".to_string(), "multi_hit".to_string()),
        ("anchor_start".to_string(), "-205687".to_string()),
        ("orientation".to_string(), "+".to_string()),
        ("ref_evidence_ids_json".to_string(), "[]".to_string()),
        ("accepted_event_ids_json".to_string(), "[]".to_string()),
        ("final_path_segment_ids_json".to_string(), "[]".to_string()),
        ("pairwise_evidence_ids_json".to_string(), "[]".to_string()),
    ]);
    let sources = HashMap::from([(("support".to_string(), "multi".to_string()), 633_129)]);
    let baselines = HashMap::from([
        (
            (
                "support".to_string(),
                "multi".to_string(),
                "Chr02".to_string(),
            ),
            ("+".to_string(), -172_703),
        ),
        (
            (
                "support".to_string(),
                "multi".to_string(),
                "Chr04".to_string(),
            ),
            ("+".to_string(), -205_687),
        ),
    ]);
    let references = BTreeMap::from([
        ("Chr02".to_string(), 1_000_000),
        ("Chr04".to_string(), 1_000_000),
    ]);

    validate_app_source_cards(
        &TsvTable {
            rows: vec![normal_row],
        },
        &sources,
        &baselines,
        &references,
    )
    .unwrap();

    let promoted_card = "support:multi:Chr04:grt_promoted";
    let promoted_row = BTreeMap::from([
        ("source_card_key".to_string(), promoted_card.to_string()),
        ("dataset_name".to_string(), "support".to_string()),
        ("contig_name".to_string(), "multi".to_string()),
        ("original_assignment".to_string(), "unplaced".to_string()),
        ("target_chr".to_string(), "Chr04".to_string()),
        ("placement_mode".to_string(), "grt_promoted".to_string()),
        ("ref_alignment_status".to_string(), "no_hit".to_string()),
        ("anchor_start".to_string(), "0".to_string()),
        ("orientation".to_string(), "+".to_string()),
        ("ref_evidence_ids_json".to_string(), "[]".to_string()),
        ("accepted_event_ids_json".to_string(), "[]".to_string()),
        ("final_path_segment_ids_json".to_string(), "[]".to_string()),
        ("pairwise_evidence_ids_json".to_string(), "[]".to_string()),
    ]);
    let error = validate_app_source_cards(
        &TsvTable {
            rows: vec![promoted_row],
        },
        &sources,
        &baselines,
        &references,
    )
    .unwrap_err();
    assert!(error.to_string().contains("GRT_IMPORT_INVALID_COORDINATE"));
}

#[test]
fn reports_grt_validation_stages_in_execution_order() {
    let mut stages = Vec::new();
    let package = validate_grt_package_with_progress(&fixture_root(), &mut |stage, _detail| {
        stages.push(stage)
    })
    .unwrap();

    assert_eq!(package.events.len(), 1);
    assert_eq!(
        stages,
        vec![
            "validate_grt_required_files",
            "validate_grt_metadata_tables",
            "validate_grt_source_fastas",
            "validate_grt_recipe",
            "validate_grt_q_artifacts",
            "validate_grt_donor_artifacts",
            "validate_grt_evidence",
            "validate_grt_final_path",
            "validate_grt_trace_integrity",
        ]
    );
}

#[test]
fn reports_recipe_validation_before_quoted_json_failure() {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    copy_tree(&fixture_root(), &bundle_root);
    let recipe_path = bundle_root.join("metadata/grt_recipe.tsv");
    let recipe = fs::read_to_string(&recipe_path).unwrap();
    fs::write(
        recipe_path,
        recipe.replace("\"[\"\"support\"\"]\"", "not-json"),
    )
    .unwrap();

    let mut stages = Vec::new();
    let error =
        validate_grt_package_with_progress(&bundle_root, &mut |stage, _detail| stages.push(stage))
            .unwrap_err();

    assert!(error.to_string().contains("GRT_IMPORT_INVALID_JSON"));
    assert_eq!(stages.last(), Some(&"validate_grt_recipe"));
}

#[test]
fn reads_standard_quoted_tsv_fields() {
    let temp = tempdir().unwrap();
    fs::write(
        temp.path().join("quoted.tsv"),
        concat!(
            "id\tpayload\tnote\n",
            "row-1\t\"{\"\"items\"\":[\"\"a\"\",\"\"b\"\"]}\"\t\"left\tright\"\n"
        ),
    )
    .unwrap();

    let table = read_tsv(
        temp.path(),
        "quoted.tsv",
        &["id", "payload", "note"],
        1,
        Some(1),
    )
    .unwrap();
    assert_eq!(
        field(&table.rows[0], "payload").unwrap(),
        r#"{"items":["a","b"]}"#
    );
    assert_eq!(field(&table.rows[0], "note").unwrap(), "left\tright");
}

#[test]
fn rejects_inconsistent_quoted_tsv_width_with_stable_code() {
    let temp = tempdir().unwrap();
    fs::write(
        temp.path().join("bad.tsv"),
        "id\tpayload\nrow-1\tvalue\textra\n",
    )
    .unwrap();

    let error = read_tsv(temp.path(), "bad.tsv", &["id", "payload"], 1, Some(1)).unwrap_err();
    assert!(error.to_string().contains("GRT_IMPORT_INVALID_TSV"));
}

#[test]
fn rejects_all_shared_invalid_fixture_mutations_with_stable_codes() {
    let cases: Vec<Value> =
        serde_json::from_slice(&fs::read(invalid_cases_path()).unwrap()).unwrap();
    for case in cases {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let operation = case["operation"].as_object().unwrap();
        let path = bundle_root.join(operation["path"].as_str().unwrap());
        match operation["type"].as_str().unwrap() {
            "remove" => fs::remove_file(path).unwrap(),
            "replace_text" => {
                let original = fs::read_to_string(&path).unwrap();
                let old = operation["old"].as_str().unwrap();
                let new = operation["new"].as_str().unwrap();
                assert!(original.contains(old));
                fs::write(path, original.replacen(old, new, 1)).unwrap();
            }
            other => panic!("unsupported fixture mutation {other}"),
        }
        let error = validate_grt_package(&bundle_root).unwrap_err();
        let expected = format!("GRT_IMPORT_{}", case["expected_code"].as_str().unwrap());
        assert!(
            error.to_string().contains(&expected),
            "case {} expected {expected}, got {error:#}",
            case["name"].as_str().unwrap()
        );
    }
}
