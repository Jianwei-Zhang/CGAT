use super::test_support::*;
use crate::grt_package::delivery_validator::{
    validate_app_final_path_manifest_hash, validate_app_source_fasta_paths,
};
use crate::grt_package::parsing::{
    read_fasta_summaries_with_sha256_and_cancel, read_fasta_with_cancel,
    read_fasta_with_sha256_and_cancel, sha256_file,
};

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
fn app_final_path_accepts_reference_subset_and_rejects_unknown_chromosome() {
    let temp = tempdir().unwrap();
    let references = BTreeMap::from([("Chr06".to_string(), 10), ("Chr09".to_string(), 10)]);
    let sources = HashMap::new();
    let manifest = serde_json::Map::new();
    let display_source_cards = HashSet::new();
    let final_path = serde_json::json!({
        "workflow": GRT_APP_WORKFLOW,
        "schema_version": GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION,
        "q4_relpath": "grt/q/q4.fa",
        "chromosomes": [{
            "chr": "Chr06",
            "q4_length": 10,
            "q4_sha256": "0".repeat(64),
            "segments": [{
                "segment_id": "gap-1",
                "kind": "gap",
                "length": 10
            }]
        }]
    });

    let (lengths, q4_records) = validate_app_final_path(
        temp.path(),
        &final_path,
        AppFinalPathValidationContext {
            reference_records: &references,
            sources: &sources,
            manifest: &manifest,
            fasta_available: false,
            source_sequences: None,
            expected_schema_version: GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION,
            display_source_cards: &display_source_cards,
        },
    )
    .unwrap();
    assert_eq!(lengths, BTreeMap::from([("Chr06".to_string(), 10)]));
    assert!(q4_records.is_none());

    let mut unknown = final_path;
    unknown["chromosomes"][0]["chr"] = serde_json::json!("Chr10");
    let error = validate_app_final_path(
        temp.path(),
        &unknown,
        AppFinalPathValidationContext {
            reference_records: &references,
            sources: &sources,
            manifest: &manifest,
            fasta_available: false,
            source_sequences: None,
            expected_schema_version: GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION,
            display_source_cards: &display_source_cards,
        },
    )
    .unwrap_err();
    assert!(error.to_string().contains(
        "GRT_IMPORT_BROKEN_REFERENCE: App Final Path references unknown chromosome Chr10"
    ));
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

#[test]
fn fasta_validation_observes_cancellation_while_streaming() {
    let temp = tempdir().unwrap();
    let fasta = temp.path().join("large.fa");
    let mut text = String::from(">chr1\n");
    for _ in 0..1024 {
        text.push_str("ACGTACGTACGTACGT\n");
    }
    fs::write(&fasta, text).unwrap();
    let mut checks = 0;
    let error = read_fasta_with_cancel(&fasta, "large FASTA", false, &mut || {
        checks += 1;
        checks >= 3
    })
    .unwrap_err();
    assert!(error.to_string().contains("import cancelled"));
}

#[test]
fn app_source_fasta_import_check_is_lightweight_but_requires_safe_existing_files() {
    let temp = tempdir().unwrap();
    let relative = "data/partitions/chr/Chr01/dataset.fa";
    let path = temp.path().join(relative);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, [0xff, 0x00, 0x7f]).unwrap();
    let table = TsvTable {
        rows: vec![BTreeMap::from([
            ("dataset_name".to_string(), "dataset".to_string()),
            ("seq_name".to_string(), "contig".to_string()),
            ("fasta_relpath".to_string(), relative.to_string()),
        ])],
    };
    validate_app_source_fasta_paths(temp.path(), &table, &mut || false).unwrap();

    fs::remove_file(&path).unwrap();
    let missing = validate_app_source_fasta_paths(temp.path(), &table, &mut || false).unwrap_err();
    assert!(missing.to_string().contains("does not exist"));

    let unsafe_table = TsvTable {
        rows: vec![BTreeMap::from([
            ("dataset_name".to_string(), "dataset".to_string()),
            ("seq_name".to_string(), "contig".to_string()),
            ("fasta_relpath".to_string(), "../outside.fa".to_string()),
        ])],
    };
    let unsafe_error =
        validate_app_source_fasta_paths(temp.path(), &unsafe_table, &mut || false).unwrap_err();
    assert!(unsafe_error.to_string().contains("safe relative path"));
}

#[test]
fn q4_fasta_digest_comes_from_the_same_pass_as_the_records() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("q4.fa");
    let contents = ">chr1\nACGTN\nACGT\n>chr2\nNNNN\n";
    fs::write(&path, contents).unwrap();

    let (records, digest) =
        read_fasta_with_sha256_and_cancel(&path, "App q4 FASTA", false, &mut || false).unwrap();

    assert_eq!(records.get("chr1").map(String::as_str), Some("ACGTNACGT"));
    assert_eq!(records.get("chr2").map(String::as_str), Some("NNNN"));
    assert_eq!(digest, sha256_file(&path).unwrap());
    assert_eq!(
        digest, "bcd80d30c15226a9b70ccd7499440fc97f47a34fcffedb8af009e6496ce5bc64",
        "the digest must cover every byte of the artifact"
    );
}

#[test]
#[ignore = "opt-in read-only q4 performance probe"]
fn benchmark_q4_validation() {
    let temp = tempdir().unwrap();
    let path = if let Some(path) = std::env::var_os("GPM_IMPORT_BENCH_Q4") {
        PathBuf::from(path)
    } else {
        let path = temp.path().join("q4.fa");
        let mut output = std::io::BufWriter::new(fs::File::create(&path).unwrap());
        for chromosome in 0..8 {
            writeln!(output, ">Chr{chromosome}").unwrap();
            let line = format!("{}\n", "ACGTNRYKMSWBDHV".repeat(5));
            for _ in 0..112_000 {
                output.write_all(line.as_bytes()).unwrap();
            }
        }
        output.flush().unwrap();
        path
    };
    let started = std::time::Instant::now();
    let (records, artifact_hash) =
        read_fasta_with_sha256_and_cancel(&path, "q4 benchmark", false, &mut || false).unwrap();
    let summaries = records
        .iter()
        .map(|(name, sequence)| {
            (
                name.clone(),
                (sequence.len(), sha256_bytes(sequence.as_bytes())),
            )
        })
        .collect::<BTreeMap<_, _>>();
    println!(
        "q4_records bytes={} records={} elapsed_ms={} artifact_hash={artifact_hash}",
        fs::metadata(&path).unwrap().len(),
        records.len(),
        started.elapsed().as_millis()
    );
    drop(records);
    let started = std::time::Instant::now();
    let (observed, observed_hash) =
        read_fasta_summaries_with_sha256_and_cancel(&path, "q4 benchmark", false, &mut || false)
            .unwrap();
    let elapsed = started.elapsed();
    assert_eq!(observed_hash, artifact_hash);
    for (name, (length, hash)) in &summaries {
        assert_eq!(observed[name].length, *length);
        assert_eq!(observed[name].sha256, *hash);
    }
    assert_eq!(observed.len(), summaries.len());
    println!(
        "q4_summaries bytes={} records={} elapsed_ms={} retained_sequence_bytes=0 artifact_hash={observed_hash}",
        fs::metadata(&path).unwrap().len(),
        observed.len(),
        elapsed.as_millis()
    );
    if std::env::var_os("GPM_IMPORT_BENCH_Q4").is_some() {
        let root = path.parent().unwrap().parent().unwrap().parent().unwrap();
        let started = std::time::Instant::now();
        let detected = crate::workspace::resolve_bundle_root_dir(root).unwrap();
        println!(
            "resolve_bundle_root elapsed_us={} root={}",
            started.elapsed().as_micros(),
            detected.display()
        );
    }
}

#[test]
fn fasta_summary_matches_record_validation_and_both_hashes() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("q4.fa");
    let text = " \r\n>Chr01 Mixed case header\r\n acgtnry \r\n kmswbdhv\r\n\r\n>Chr02\nNNnn\n";
    fs::write(&path, text).unwrap();
    let (records, file_hash) =
        read_fasta_with_sha256_and_cancel(&path, "q4", false, &mut || false).unwrap();
    let (summaries, observed_hash) =
        read_fasta_summaries_with_sha256_and_cancel(&path, "q4", false, &mut || false).unwrap();
    assert_eq!(observed_hash, file_hash);
    assert_eq!(observed_hash, sha256_file(&path).unwrap());
    assert_eq!(summaries.len(), records.len());
    for (name, sequence) in records {
        assert_eq!(summaries[&name].length, sequence.len());
        assert_eq!(summaries[&name].sha256, sha256_bytes(sequence.as_bytes()));
    }
}

#[test]
fn fasta_summary_preserves_invalid_fasta_errors_and_empty_mode() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("q4.fa");
    for text in [
        "",
        "NN\n",
        ">\nNN\n",
        ">Chr01\n",
        ">Chr01\n>Chr02\nNN\n",
        ">Chr01\nNN\n>Chr01 duplicate\nNN\n",
        ">Chr01\nACGU\n",
        ">Chr01\nA C\n",
        ">Chr01\n非ASCII\n",
    ] {
        fs::write(&path, text).unwrap();
        let full_error =
            read_fasta_with_sha256_and_cancel(&path, "q4", false, &mut || false).unwrap_err();
        let summary_error =
            read_fasta_summaries_with_sha256_and_cancel(&path, "q4", false, &mut || false)
                .unwrap_err();
        assert_eq!(
            summary_error.to_string(),
            full_error.to_string(),
            "input={text:?}"
        );
    }
    fs::write(&path, [b'>', b'x', b'\n', 0xff]).unwrap();
    assert!(
        read_fasta_summaries_with_sha256_and_cancel(&path, "q4", false, &mut || false)
            .unwrap_err()
            .to_string()
            .contains("not UTF-8")
    );
    fs::write(&path, "\n").unwrap();
    let (summaries, digest) =
        read_fasta_summaries_with_sha256_and_cancel(&path, "q4", true, &mut || false).unwrap();
    assert!(summaries.is_empty());
    assert_eq!(digest, sha256_file(&path).unwrap());
}

#[test]
fn fasta_summary_observes_mid_stream_cancellation() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("q4.fa");
    fs::write(&path, format!(">Chr01\n{}", "NNNN\n".repeat(2048))).unwrap();
    let mut checks = 0;
    let error = read_fasta_summaries_with_sha256_and_cancel(&path, "q4", false, &mut || {
        checks += 1;
        checks > 2
    })
    .unwrap_err();
    assert_eq!(checks, 3);
    assert!(error.to_string().contains("import cancelled"));
}

#[test]
fn app_q4_summary_checks_artifact_chromosome_and_reconstruction_contracts() {
    let temp = tempdir().unwrap();
    fs::create_dir_all(temp.path().join("grt/q")).unwrap();
    let path = temp.path().join("grt/q/q4.fa");
    let text = ">Chr06\nnnnnnnnnnn\n";
    fs::write(&path, text).unwrap();
    let references = BTreeMap::from([("Chr06".to_string(), 10)]);
    let sources = HashMap::new();
    let cards = HashSet::new();
    let manifest = serde_json::Map::from_iter([(
        "q4_artifact_sha256".to_string(),
        Value::String(sha256_bytes(text.as_bytes())),
    )]);
    let final_path = serde_json::json!({
        "workflow": GRT_APP_WORKFLOW,
        "schema_version": GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION,
        "q4_relpath": "grt/q/q4.fa",
        "chromosomes": [{"chr": "Chr06", "q4_length": 10,
            "q4_sha256": sha256_bytes(b"NNNNNNNNNN"),
            "segments": [{"segment_id": "gap-1", "kind": "gap", "length": 10}]}]
    });
    let validate = |final_path: &Value, manifest: &Map<String, Value>, source_sequences| {
        validate_app_final_path(
            temp.path(),
            final_path,
            AppFinalPathValidationContext {
                reference_records: &references,
                sources: &sources,
                manifest,
                fasta_available: true,
                source_sequences,
                expected_schema_version: GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION,
                display_source_cards: &cards,
            },
        )
    };
    let (lengths, records) = validate(&final_path, &manifest, None).unwrap();
    assert_eq!(lengths["Chr06"], 10);
    assert!(
        records.is_none(),
        "App import must not retain q4 sequence strings"
    );
    let source_sequences = HashMap::new();
    let (_, records) = validate(&final_path, &manifest, Some(&source_sequences)).unwrap();
    assert_eq!(records.unwrap()["Chr06"], "NNNNNNNNNN");
    let mut wrong_manifest = manifest.clone();
    wrong_manifest["q4_artifact_sha256"] = Value::String("0".repeat(64));
    assert!(
        validate(&final_path, &wrong_manifest, None)
            .unwrap_err()
            .to_string()
            .contains("GRT_IMPORT_CHECKSUM_MISMATCH")
    );
    let mut wrong_path = final_path.clone();
    wrong_path["chromosomes"][0]["q4_sha256"] = Value::String("0".repeat(64));
    assert!(
        validate(&wrong_path, &manifest, None)
            .unwrap_err()
            .to_string()
            .contains("GRT_IMPORT_FINAL_PATH_MISMATCH")
    );
    wrong_path = final_path.clone();
    wrong_path["chromosomes"][0]["q4_length"] = Value::from(11);
    wrong_path["chromosomes"][0]["segments"][0]["length"] = Value::from(11);
    assert!(
        validate(&wrong_path, &manifest, None)
            .unwrap_err()
            .to_string()
            .contains("GRT_IMPORT_FINAL_PATH_MISMATCH")
    );
    let missing = ">Chr09\nnnnnnnnnnn\n";
    fs::write(&path, missing).unwrap();
    wrong_manifest["q4_artifact_sha256"] = Value::String(sha256_bytes(missing.as_bytes()));
    assert!(
        validate(&final_path, &wrong_manifest, None)
            .unwrap_err()
            .to_string()
            .contains("lacks chromosome Chr06")
    );
}

#[test]
fn q4_hash_batches_preserve_short_long_lines_and_chromosome_boundaries() {
    let temp = tempdir().unwrap();
    let path = temp.path().join("q4.fa");
    let long = "acgtnrykmswbdhv".repeat(10_000);
    fs::write(
        &path,
        format!(
            ">first\n{}>second\n{long}\n>third\nNN\n",
            "acgtn\n".repeat(20_000)
        ),
    )
    .unwrap();
    let (records, file_hash) =
        read_fasta_with_sha256_and_cancel(&path, "q4", false, &mut || false).unwrap();
    let (summaries, digest) =
        read_fasta_summaries_with_sha256_and_cancel(&path, "q4", false, &mut || false).unwrap();
    assert_eq!(digest, file_hash);
    for (name, sequence) in records {
        assert_eq!(summaries[&name].length, sequence.len());
        assert_eq!(summaries[&name].sha256, sha256_bytes(sequence.as_bytes()));
    }
}
