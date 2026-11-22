//! Same serializer output consumed by Python and Rust; no native-tool claim.
use super::test_support::*;
use crate::exporter::{
    self, ExportProjectFinalPathFastaParams, FinalPathExportSegment, FinalPathFastaRecord,
};

fn materialize(light: bool) -> tempfile::TempDir {
    materialize_named("controlled_partial.json", light)
}
fn materialize_named(name: &str, light: bool) -> tempfile::TempDir {
    let data: Value = serde_json::from_slice(
        &fs::read(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../tests/fixtures/refinement_app_v5")
                .join(name),
        )
        .unwrap(),
    )
    .unwrap();
    let temp = tempdir().unwrap();
    let root = temp.path().join("refined.degap");
    for (name, contents) in data["files"].as_object().unwrap() {
        if light
            && matches!(
                Path::new(name).extension().and_then(|e| e.to_str()),
                Some("fa" | "fasta" | "fna")
            )
        {
            continue;
        }
        let target = root.join(name);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::write(target, contents.as_str().unwrap()).unwrap();
    }
    if light {
        let path = root.join("metadata/package.tsv");
        fs::write(
            &path,
            fs::read_to_string(&path)
                .unwrap()
                .replace("\tfull\t", "\tno_fasta\t"),
        )
        .unwrap();
        let path = root.join("metadata/grt_app_manifest.json");
        let mut app: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        app["package_kind"] = Value::from("no_fasta");
        app["fasta_available"] = Value::from(false);
        fs::write(path, serde_json::to_vec(&app).unwrap()).unwrap();
        reseal(&root, Some("light"));
    }
    temp
}
fn reseal(root: &Path, mode: Option<&str>) {
    let path = root.join("metadata/refinement/manifest.json");
    let mut manifest: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    if let Some(mode) = mode {
        manifest["package_mode"] = Value::from(mode);
    }
    for (name, hash) in manifest["files"].as_object_mut().unwrap().iter_mut() {
        if root.join(name).is_file() {
            *hash = Value::from(sha256_file(&root.join(name)).unwrap());
        }
    }
    manifest["files"]
        .as_object_mut()
        .unwrap()
        .retain(|name, _| root.join(name).is_file());
    fs::write(path, serde_json::to_vec(&manifest).unwrap()).unwrap();
}
fn validate(root: &Path) -> Result<ValidatedGrtPackage> {
    validate_grt_delivery_package_with_progress_and_cancel(root, &mut |_, _| {}, &mut || false)
}
fn records(projected: &Value) -> Vec<FinalPathFastaRecord> {
    projected["chromosomes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|chr| FinalPathFastaRecord {
            chr_name: chr["chr"].as_str().unwrap().to_string(),
            final_path_segments: chr["segments"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| {
                    if s["kind"] == "gap" {
                        return FinalPathExportSegment::Gap {
                            gap_size_bp: s["length"].as_i64().unwrap(),
                        };
                    }
                    let source = &s["source"];
                    let (start, end) = (
                        source["start"].as_i64().unwrap(),
                        source["end"].as_i64().unwrap(),
                    );
                    FinalPathExportSegment::Source {
                        dataset_name: source["dataset"].as_str().unwrap().into(),
                        contig_name: source["contig"].as_str().unwrap().into(),
                        start: if source["orientation"] == "-" {
                            end
                        } else {
                            start
                        },
                        end: if source["orientation"] == "-" {
                            start
                        } else {
                            end
                        },
                    }
                })
                .collect(),
        })
        .collect()
}

#[test]
fn refined_full_import_materializes_real_bridge_and_exports_admitted_sequence() {
    let temp = materialize(false);
    let root = temp.path().join("refined.degap");
    let validated = validate(&root).unwrap();
    assert_eq!(validated.final_path["schema_version"], "4");
    let expected = read_fasta(
        &root.join("data/refinement/final.fa"),
        "refined fixture",
        false,
    )
    .unwrap();
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root).unwrap();
    let project = initialize_grt_project(&outcome.project_db_path, "DEGAP refined").unwrap();
    let view =
        load_grt_project_view_for_project(&outcome.project_db_path, project.project_id).unwrap();
    assert_eq!(view.recipe.schema_version, "5");
    assert_eq!(view.recipe.final_q_relpath, "data/refinement/final.fa");
    let card = view
        .source_cards
        .iter()
        .find(|card| card.placement_mode == "refinement")
        .unwrap();
    assert_eq!(card.ref_alignment_status, "not_measured");
    let trace =
        load_grt_source_card_trace(&outcome.project_db_path, &card.source_card_key).unwrap();
    assert!(trace.accepted_events.is_empty());
    assert!(trace.ref_evidence.is_empty());
    assert!(trace.pairwise_evidence.is_empty());
    assert_eq!(trace.final_path_segments.len(), 3);
    assert!(trace.final_path_segments[1]["refinement_source"].is_object());
    for segment in trace.final_path_segments {
        let source = if segment["kind"] == "gap" {
            &segment["refinement_source"]
        } else {
            &segment["source"]
        };
        assert_eq!(source["dataset"], card.dataset_name);
        assert_eq!(source["contig"], card.contig_name);
    }
    let path = load_grt_final_path(&outcome.project_db_path).unwrap();
    let output = temp.path().join("export.fa");
    exporter::export_project_final_path_fasta(
        &outcome.project_db_path,
        project.project_id,
        &ExportProjectFinalPathFastaParams {
            output_path: output.clone(),
            records: records(&path),
        },
    )
    .unwrap();
    assert_eq!(
        read_fasta(&output, "App re-export", false).unwrap(),
        expected
    );
    // A second independently named project does not replace the first project.
    let second = initialize_grt_project(&outcome.project_db_path, "Independent import").unwrap();
    assert_ne!(project.project_id, second.project_id);
}

#[test]
fn refined_light_import_keeps_provenance_but_does_not_claim_sequences_available() {
    let temp = materialize(true);
    let root = temp.path().join("refined.degap");
    validate(&root).unwrap();
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root).unwrap();
    let project = initialize_grt_project(&outcome.project_db_path, "Light refinement").unwrap();
    let path = load_grt_final_path(&outcome.project_db_path).unwrap();
    assert!(path["chromosomes"].as_array().unwrap().iter().any(|chr| {
        chr["segments"]
            .as_array()
            .unwrap()
            .iter()
            .any(|s| s.get("refinement_source").is_some())
    }));
    let error = exporter::export_project_final_path_fasta(
        &outcome.project_db_path,
        project.project_id,
        &ExportProjectFinalPathFastaParams {
            output_path: temp.path().join("not-ready.fa"),
            records: records(&path),
        },
    )
    .unwrap_err();
    assert!(!error.to_string().is_empty());
    assert!(!temp.path().join("not-ready.fa").exists());
}

#[test]
fn resealed_corrupt_bridge_is_rejected_before_any_workspace_database() {
    let temp = materialize(false);
    let root = temp.path().join("refined.degap");
    let patch = fs::read_dir(root.join("data/refinement/sources"))
        .unwrap()
        .map(|p| p.unwrap().path())
        .find(|p| p.extension().and_then(|s| s.to_str()) == Some("fa"))
        .unwrap();
    fs::write(
        &patch,
        fs::read_to_string(&patch)
            .unwrap()
            .replace("GTNNAC", "TTNNAC"),
    )
    .unwrap();
    reseal(&root, None);
    let error = crate::importer::import_from_extracted_bundle(&root).unwrap_err();
    assert!(
        error.to_string().contains("source reconstruction"),
        "{error:#}"
    );
    assert!(!root.join("project.sqlite").exists());
}

#[test]
fn resealed_projection_cannot_substitute_lgz_or_alter_parent_provenance() {
    let temp = materialize(true);
    let root = temp.path().join("refined.degap");
    let path = root.join("metadata/grt_final_path.json");
    let mut projected: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    projected["chromosomes"][0]["coordinate_lift"][0]["baseline_end"] = Value::from(1);
    fs::write(&path, serde_json::to_vec(&projected).unwrap()).unwrap();
    let app_path = root.join("metadata/grt_app_manifest.json");
    let mut manifest: Value = serde_json::from_slice(&fs::read(&app_path).unwrap()).unwrap();
    manifest["final_path_sha256"] = Value::from(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&projected).unwrap())
    ));
    fs::write(app_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    reseal(&root, None);
    assert!(
        validate(&root)
            .unwrap_err()
            .to_string()
            .contains("not the accepted Server refinement")
    );
}

#[test]
fn refined_zip_import_handles_owned_progress_log_and_cannot_replace_an_existing_project() {
    for light in [false, true] {
        let temp = materialize(light);
        let root = temp.path().join("refined.degap");
        let archive = temp.path().join("refined.degap.zip");
        write_bundle_zip(&root, &archive);
        let destination = temp.path().join("imported.degap");
        let options = crate::importer::ImportOptions {
            require_new_workspace: true,
            ..Default::default()
        };
        let (outcome, _) =
            crate::importer::import_from_zip_with_options(&archive, &destination, options).unwrap();
        let project = initialize_grt_project(&outcome.project_db_path, "Keep my edits").unwrap();
        let conn = open_workspace_db(&outcome.project_db_path).unwrap();
        conn.execute(
            "UPDATE project SET description='manual user note' WHERE id=?1",
            [project.project_id],
        )
        .unwrap();
        drop(conn);
        let before = sha256_file(&outcome.project_db_path).unwrap();
        assert!(
            crate::importer::import_from_zip_with_options(&archive, &destination, options).is_err()
        );
        assert_eq!(sha256_file(&outcome.project_db_path).unwrap(), before);
        assert!(destination.join("cache/import.log").is_file());
    }
}

#[test]
fn measured_source_full_light_import_keeps_real_refinement_and_export_identity() {
    for light in [false, true] {
        let temp = materialize_named("controlled_measured.json", light);
        let root = temp.path().join("refined.degap");
        validate(&root).unwrap();
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&root).unwrap();
        let project =
            initialize_grt_project(&outcome.project_db_path, "Measured source refinement").unwrap();
        let view = load_grt_project_view_for_project(&outcome.project_db_path, project.project_id)
            .unwrap();
        assert!(
            view.source_cards
                .iter()
                .any(|row| row.placement_mode == "refinement"
                    && row.ref_alignment_status == "no_hit")
        );
        let conn = open_workspace_db(&outcome.project_db_path).unwrap();
        let tel: i64 = conn
            .query_row("SELECT COUNT(*) FROM source_seq_telomere_mark", [], |row| {
                row.get(0)
            })
            .unwrap();
        let cen: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM source_seq_centromere_mark",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(
            tel > 0 && cen > 0,
            "measured source annotations must survive Full and Light import"
        );
        let path = load_grt_final_path(&outcome.project_db_path).unwrap();
        let output = temp.path().join("measured-export.fa");
        let result = exporter::export_project_final_path_fasta(
            &outcome.project_db_path,
            project.project_id,
            &ExportProjectFinalPathFastaParams {
                output_path: output.clone(),
                records: records(&path),
            },
        );
        if light {
            assert!(result.is_err());
            assert!(!output.exists());
        } else {
            result.unwrap();
            assert_eq!(
                read_fasta(&output, "measured App export", false).unwrap(),
                read_fasta(
                    &root.join("data/refinement/final.fa"),
                    "accepted refined sequence",
                    false
                )
                .unwrap()
            );
        }
    }
}

fn reseal_measured_proof(root: &Path, proof: &Value) {
    let path = root.join("metadata/refinement/source_evidence.json");
    fs::write(&path, serde_json::to_vec(proof).unwrap()).unwrap();
    let manifest_path = root.join("metadata/refinement/manifest.json");
    let mut manifest: Value = serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    manifest["source_evidence"]["sha256"] = Value::from(sha256_file(&path).unwrap());
    fs::write(manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    reseal(root, None);
}

#[test]
fn resealed_measured_status_cannot_disagree_with_actual_source_paf() {
    let temp = materialize_named("controlled_measured.json", false);
    let root = temp.path().join("refined.degap");
    let mut proof: Value = serde_json::from_slice(
        &fs::read(root.join("metadata/refinement/source_evidence.json")).unwrap(),
    )
    .unwrap();
    proof["sources"][0]["ref_alignment_status"] = Value::from("hit");
    let summary_path = root.join("report/summary.json");
    let mut summary: Value = serde_json::from_slice(&fs::read(&summary_path).unwrap()).unwrap();
    summary["source_evidence"]["sources"] = proof["sources"].clone();
    fs::write(&summary_path, serde_json::to_vec(&summary).unwrap()).unwrap();
    let report_path = root.join("report/manifest.json");
    let mut report: Value = serde_json::from_slice(&fs::read(&report_path).unwrap()).unwrap();
    report["files"]["summary.json"] = Value::from(sha256_file(&summary_path).unwrap());
    fs::write(report_path, serde_json::to_vec(&report).unwrap()).unwrap();
    reseal_measured_proof(&root, &proof);
    let error = validate(&root).unwrap_err().to_string();
    assert!(error.contains("source status does not describe"), "{error}");
    assert!(!root.join("project.sqlite").exists());
}

#[test]
fn resealed_measured_final_coordinates_cannot_drift_from_accepted_source_slices() {
    let temp = materialize_named("controlled_measured.json", false);
    let root = temp.path().join("refined.degap");
    let path = root.join("metadata/refinement/source_intervals.tsv");
    let text = fs::read_to_string(&path).unwrap();
    let mut rows: Vec<Vec<String>> = text
        .lines()
        .map(|line| line.split('\t').map(str::to_string).collect())
        .collect();
    let column = rows[0]
        .iter()
        .position(|name| name == "final_start")
        .unwrap();
    rows[1][column] = (rows[1][column].parse::<u64>().unwrap() + 1).to_string();
    fs::write(
        &path,
        rows.iter()
            .map(|row| row.join("\t"))
            .collect::<Vec<_>>()
            .join("\n")
            + "\n",
    )
    .unwrap();
    let mut proof: Value = serde_json::from_slice(
        &fs::read(root.join("metadata/refinement/source_evidence.json")).unwrap(),
    )
    .unwrap();
    proof["files"]["metadata/refinement/source_intervals.tsv"] =
        Value::from(sha256_file(&path).unwrap());
    reseal_measured_proof(&root, &proof);
    let error = validate(&root).unwrap_err().to_string();
    assert!(error.contains("coordinate map differs"), "{error}");
}
