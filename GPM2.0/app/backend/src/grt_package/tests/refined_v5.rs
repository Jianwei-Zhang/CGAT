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
fn refined_import_retains_original_read_hints_in_full_and_light() {
    for light in [false, true] {
        let temp = materialize(light);
        let root = temp.path().join("refined.degap");
        let provenance_path = root.join("metadata/refinement/provenance.json");
        let mut provenance: Value =
            serde_json::from_slice(&fs::read(&provenance_path).unwrap()).unwrap();
        provenance["execution"]["recipe"] = serde_json::json!({
            "reads": [{"technology":"hifi", "path":"/server/original.hifi.fq.gz", "sha256":"a".repeat(64)}],
        });
        fs::write(&provenance_path, serde_json::to_vec(&provenance).unwrap()).unwrap();
        let manifest_path = root.join("metadata/refinement/manifest.json");
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest["provenance_sha256"] = Value::from(sha256_file(&provenance_path).unwrap());
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        reseal(&root, None);
        // The fake path is intentionally not available on the desktop host.
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&root).unwrap();
        let project = initialize_grt_project(&outcome.project_db_path, "Refined inputs").unwrap();
        let inputs = crate::grt_package::load_project_refinement_read_inputs(
            &outcome.project_db_path,
            project.project_id,
        )
        .unwrap();
        assert_eq!(inputs.hifi[0].path, "/server/original.hifi.fq.gz");
        assert_eq!(
            inputs.hifi[0].sha256.as_deref(),
            Some("a".repeat(64).as_str())
        );
        let other = crate::grt_package::load_project_refinement_read_inputs(
            &outcome.project_db_path,
            project.project_id + 1,
        )
        .unwrap();
        assert!(other.hifi.is_empty());
        assert!(inputs.ont.is_empty());
    }
}

#[test]
fn refined_manual_export_uses_saved_locus_and_registers_project_owner() {
    use std::io::Read;
    let temp = materialize(false);
    let root = temp.path().join("refined.degap");
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root).unwrap();
    let project = initialize_grt_project(&outcome.project_db_path, "Manual export").unwrap();
    let mut path =
        load_grt_final_path_by_chr_for_project(&outcome.project_db_path, project.project_id)
            .unwrap();
    let (chr, record) = path
        .iter_mut()
        .find(|(_, record)| {
            record["segments"]
                .as_array()
                .is_some_and(|rows| rows.iter().any(|row| row["kind"] == "gap"))
        })
        .unwrap();
    let chr = chr.clone();
    let segments = record["segments"].as_array_mut().unwrap();
    let i = segments
        .iter()
        .position(|row| row["kind"] == "gap")
        .unwrap();
    let gap = segments[i]["segment_id"].as_str().unwrap().to_string();
    let original_request = serde_json::from_value(serde_json::json!({"loci":[{
        "chr":chr,"kind":"gap","segment_id":gap
    }]}))
    .unwrap();
    let original = temp.path().join("original-tasks.zip");
    crate::degap_jobs::export_manual_refinement(
        &root,
        project.project_id,
        &original,
        &original_request,
    )
    .unwrap();
    segments[i] = serde_json::json!({"type":"gap","segmentId":gap,"gapSizeBp":117});
    let conn = crate::db::open_workspace_db(&outcome.project_db_path).unwrap();
    conn.execute("INSERT INTO project_assembly_view_state (project_id, final_path_by_chr_json, updated_at)
        VALUES (?1, ?2, '1') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json",
        rusqlite::params![project.project_id, serde_json::to_string(&path).unwrap()]).unwrap();
    let request = serde_json::from_value(serde_json::json!({"loci":[{
        "chr":chr,"kind":"gap","segment_id":gap,"tools":["quartet","degap"]
    }],"hifi_reads":[],"ont_reads":[]}))
    .unwrap();
    let archive = temp.path().join("-project's refinement.zip");
    let result =
        crate::degap_jobs::export_manual_refinement(&root, project.project_id, &archive, &request)
            .unwrap();
    let mut zipped = zip::ZipArchive::new(fs::File::open(&archive).unwrap()).unwrap();
    let mut bytes = Vec::new();
    zipped
        .by_name("refinement_tasks.json")
        .unwrap()
        .read_to_end(&mut bytes)
        .unwrap();
    let mut readme = String::new();
    zipped
        .by_name("README.txt")
        .unwrap()
        .read_to_string(&mut readme)
        .unwrap();
    assert!(readme.contains("python .lib/tools/refine.py './-project'\"'\"'s refinement.zip'\n"));
    assert_eq!(result.loci, 1);
    assert_eq!(result.tasks, 2);
    assert_eq!(
        result.batch_sha256,
        format!("{:x}", <sha2::Sha256 as sha2::Digest>::digest(&bytes))
    );
    let value: Value = serde_json::from_slice(&bytes).unwrap();
    let locus = &value["loci"][0];
    assert_eq!(locus["gap_bp"], 117);
    assert_eq!(locus["tools"], serde_json::json!(["degap", "quartet"]));
    assert_eq!(value["reads"]["hifi"], serde_json::json!([]));
    let member = &locus["seed_plans"]["seqleft"]["members"][0];
    assert!(member["fasta_sha256"].is_string() || member["interval_sha256"].is_string());
    let receipts = root.join("metadata/refinement_exports");
    let exported_batch = result.batch_sha256;
    let ledger_file = receipts.join(format!("{exported_batch}.json"));
    let ledger: Value = serde_json::from_slice(&fs::read(&ledger_file).unwrap()).unwrap();
    assert_eq!(ledger["project_id"], project.project_id);
    assert_eq!(ledger["manifest"], value);
    assert!(
        crate::degap_jobs::export_manual_refinement(&root, project.project_id, &archive, &request)
            .is_err()
    );
    let rejected_request = serde_json::from_value(serde_json::json!({"loci":[{
        "chr":chr,"kind":"gap","segment_id":gap,"tools":["quartet","quartet"]
    }]}))
    .unwrap();
    let rejected = temp.path().join("duplicate-tools.zip");
    assert!(
        crate::degap_jobs::export_manual_refinement(
            &root,
            project.project_id,
            &rejected,
            &rejected_request
        )
        .is_err()
    );
    assert!(!rejected.exists());
    assert_eq!(fs::read_dir(receipts).unwrap().count(), 2);

    // The preview's persistent history comes from sealed exports, never from
    // a whole-view overwrite or private Server input paths.
    let history = serde_json::to_value(
        crate::degap_jobs::list_manual_refinement_exports(&root, project.project_id).unwrap(),
    )
    .unwrap();
    let rows = history.as_array().unwrap();
    assert_eq!(rows.len(), 2);
    let row = rows
        .iter()
        .find(|row| row["batchSha256"] == exported_batch)
        .unwrap();
    assert_eq!(row["outputFileName"], "-project's refinement.zip");
    assert_eq!(
        row["loci"][0]["tools"],
        serde_json::json!(["degap", "quartet"])
    );
    assert_eq!(row["tasksCount"], 2);
    assert!(!row.to_string().contains("seed_plans"));
    assert!(!row.to_string().contains("reads"));
    assert!(
        crate::degap_jobs::list_manual_refinement_exports(&root, project.project_id + 999).is_err()
    );
    let mut tampered = ledger;
    tampered["manifest"]["loci"][0]["gap_bp"] = serde_json::json!(120);
    fs::write(&ledger_file, serde_json::to_vec(&tampered).unwrap()).unwrap();
    let verified = serde_json::to_value(
        crate::degap_jobs::list_manual_refinement_exports(&root, project.project_id).unwrap(),
    )
    .unwrap();
    assert_eq!(verified.as_array().unwrap().len(), 1);
    assert_ne!(verified[0]["batchSha256"], exported_batch);
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
    assert_eq!(view.auto_refinement_effects.len(), 1);
    let effect = &view.auto_refinement_effects[0];
    assert_eq!(effect.tool, "degap");
    assert_eq!(
        (
            effect.closed,
            effect.partial,
            effect.original_gaps,
            effect.accepted_edits
        ),
        (0, 1, 1, 1)
    );
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
    let effects = load_grt_project_view_for_project(&outcome.project_db_path, project.project_id)
        .unwrap()
        .auto_refinement_effects;
    assert_eq!(effects.len(), 1);
    assert_eq!(
        (
            effects[0].tool.as_str(),
            effects[0].closed,
            effects[0].partial
        ),
        ("degap", 0, 1)
    );
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
fn previous_workspace_recovers_verified_effect_without_reinterpreting_its_final_path() -> Result<()>
{
    let temp = materialize(true);
    let (outcome, _) =
        crate::importer::import_from_extracted_bundle(&temp.path().join("refined.degap"))?;
    let db = &outcome.project_db_path;
    let original = load_grt_final_path(db)?;
    let conn = crate::db::open_workspace_db(db)?;
    conn.execute_batch("DROP TABLE grt_auto_refinement_effect; PRAGMA user_version=10;")?;
    drop(conn);
    let effects = load_grt_project_view(db)?.auto_refinement_effects;
    assert_eq!(effects.len(), 1);
    assert_eq!(
        (
            effects[0].closed,
            effects[0].partial,
            effects[0].original_gaps
        ),
        (0, 1, 1)
    );
    let project = initialize_grt_project(db, "Legacy refinement")?;
    assert_eq!(
        load_grt_project_view_for_project(db, project.project_id)?.auto_refinement_effects,
        effects
    );
    assert_eq!(load_grt_final_path(db)?, original);
    let conn = crate::db::open_workspace_db(db)?;
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM grt_auto_refinement_effect",
            [],
            |row| { row.get::<_, i64>(0) }
        )?,
        0
    );
    Ok(())
}

#[test]
fn legacy_effect_recovery_keeps_missing_corrupt_or_mismatched_evidence_unknown() -> Result<()> {
    for mode in ["missing", "hash", "totals", "projection", "pre_summary"] {
        let temp = materialize(true);
        let root = temp.path().join("refined.degap");
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&root)?;
        let db = &outcome.project_db_path;
        let conn = crate::db::open_workspace_db(db)?;
        conn.execute("DELETE FROM grt_auto_refinement_effect", [])?;
        let proof_path = root.join("metadata/refinement/provenance.json");
        if mode == "missing" {
            fs::remove_file(&proof_path)?;
        } else if mode == "projection" {
            let mut path = load_grt_final_path(db)?;
            path["tool"] = Value::from("quartet");
            conn.execute(
                "UPDATE grt_package SET final_path_json=?1",
                [path.to_string()],
            )?;
        } else {
            let mut proof: Value = serde_json::from_slice(&fs::read(&proof_path)?)?;
            if mode == "pre_summary" {
                proof.as_object_mut().unwrap().remove("counts");
                proof.as_object_mut().unwrap().remove("gap_outcomes");
            } else {
                proof["counts"]["closed"] = Value::from(99);
            }
            fs::write(&proof_path, serde_json::to_vec(&proof)?)?;
            if mode != "hash" {
                let manifest_path = root.join("metadata/refinement/manifest.json");
                let mut manifest: Value = serde_json::from_slice(&fs::read(&manifest_path)?)?;
                manifest["provenance_sha256"] = Value::from(sha256_file(&proof_path)?);
                fs::write(manifest_path, serde_json::to_vec(&manifest)?)?;
            }
        }
        assert!(
            load_grt_project_view(db)?
                .auto_refinement_effects
                .is_empty(),
            "{mode}"
        );
    }
    Ok(())
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

#[test]
fn manual_refinement_export_supports_both_scopes_and_roundtrips_sequence() -> Result<()> {
    use crate::degap_jobs::{
        export_manual_refinement, import_manual_refinement_results, list_manual_refinement_results,
        switch_manual_refinement_locus, undo_manual_refinement_locus,
    };
    use sha2::{Digest, Sha256};
    use std::io::{Read, Write};
    use zip::{ZipArchive, ZipWriter, write::FileOptions};

    let temp = materialize(false);
    let root = temp.path().join("refined.degap");
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root)?;
    let project = initialize_grt_project(&outcome.project_db_path, "Manual refinement result")?;
    let pid = project.project_id;
    let baseline = load_grt_final_path_by_chr_for_project(&outcome.project_db_path, pid)?;
    let (chr, entry) = baseline
        .iter()
        .find(|(_, entry)| {
            entry["segments"]
                .as_array()
                .is_some_and(|rows| rows.iter().any(|r| r["kind"] == "gap"))
        })
        .unwrap();
    let gap = entry["segments"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["kind"] == "gap")
        .unwrap();
    let target = gap["segment_id"].as_str().unwrap();
    let original_size = gap["length"].as_u64().unwrap();
    // Additional edited paths with their own chromosome keys exercise the actual
    // multi-chromosome manifest, without enlarging the scientific fixture.
    let other = "controlled-other-chromosome";
    let unfilled = "controlled-no-closure";
    let partial_then_closed = "controlled-partial-and-closed";
    let conn = crate::db::open_workspace_db(&outcome.project_db_path)?;
    let overlay = serde_json::to_string(&BTreeMap::from([
        (other, entry),
        (unfilled, entry),
        (partial_then_closed, entry),
    ]))?;
    conn.execute(
        "INSERT INTO project_assembly_view_state(project_id, final_path_by_chr_json, updated_at) VALUES (?1,?2,'before')",
        rusqlite::params![pid,overlay],
    )?;
    let request = |chrs: &[&str]| {
        serde_json::from_value(serde_json::json!({"loci": chrs.iter().map(|chr| {
        serde_json::json!({"chr":chr,"segment_id":target,"kind":"gap","tools":["quartet","degap"]})
    }).collect::<Vec<_>>() }))
    };
    let load_manifest = |path: &Path| -> Result<Value> {
        let mut zip = ZipArchive::new(fs::File::open(path)?)?;
        let mut bytes = Vec::new();
        zip.by_name("refinement_tasks.json")?
            .read_to_end(&mut bytes)?;
        Ok(serde_json::from_slice(&bytes)?)
    };
    let single = temp.path().join("one.zip");
    let all = temp.path().join("all.zip");
    let single_summary = export_manual_refinement(
        &root,
        pid,
        &single,
        &serde_json::from_value(serde_json::json!({
            "loci":[{"chr":chr,"segment_id":target,"kind":"gap","tools":["quartet"]}]
        }))?,
    )?;
    let all_summary = export_manual_refinement(
        &root,
        pid,
        &all,
        &request(&[chr, other, unfilled, partial_then_closed])?,
    )?;
    let manifest = load_manifest(&all)?;
    assert_eq!(single_summary.loci, 1);
    assert_eq!(load_manifest(&single)?["loci"][0]["chr"], chr.as_str());
    assert_eq!(all_summary.loci, 4);
    assert_eq!(all_summary.tasks, 8);
    assert_eq!(manifest["loci"][1]["chr"], other);
    assert_ne!(manifest["loci"][0]["id"], manifest["loci"][1]["id"]);

    let sha = |data: &[u8]| format!("{:x}", Sha256::digest(data));
    let write_batch = |path: &Path,
                       batch: &str,
                       manifest: &Value,
                       payload: &[u8],
                       status: &str|
     -> Result<()> {
        let mut rows = Vec::new();
        let mut paths = Vec::new();
        for locus in manifest["loci"].as_array().unwrap() {
            let id = locus["id"].as_str().unwrap();
            for tool in locus["tools"].as_array().unwrap().iter().rev() {
                let tool = tool.as_str().unwrap();
                if locus["chr"] == other && tool == "degap" {
                    rows.push(serde_json::json!({"locus_id":id,"tool":tool,"status":"failed","reason":"controlled_failure","patch":null}));
                    continue;
                }
                let (status, payload) = if locus["chr"] == unfilled
                    || (locus["chr"] == partial_then_closed && tool == "degap")
                {
                    ("partial", b"ANT".as_slice())
                } else {
                    (status, payload)
                };
                let path = format!("patches/{id}.{tool}.seq");
                rows.push(serde_json::json!({"locus_id":id,"tool":tool,"status":status,"reason":null,
                    "attempt_id":format!("{tool}-controlled"),"version":"2.0","revision":"synthetic-fixture",
                    "patch":{"path":path,"operation":"replace_gap","original_length":original_size,
                      "original_sha256":sha(&vec![b'N';original_size as usize]), "length":payload.len(),"sha256":sha(payload)}}));
                paths.push((path, payload.to_vec()));
            }
        }
        let mut zip = ZipWriter::new(fs::File::create(path)?);
        zip.start_file("refinement_results.json", FileOptions::default())?;
        zip.write_all(&serde_json::to_vec(
            &serde_json::json!({"schema":"cgat.app-refinement-results.v1",
            "batch_sha256":batch,"results":rows}),
        )?)?;
        for (path, bytes) in paths {
            zip.start_file(path, FileOptions::default())?;
            zip.write_all(&bytes)?;
        }
        zip.finish()?;
        Ok(())
    };
    assert!(
        manifest["loci"]
            .as_array()
            .unwrap()
            .iter()
            .all(|locus| locus["tools"] == serde_json::json!(["degap", "quartet"]))
    );
    let result_zip = temp.path().join("result.zip");
    write_batch(
        &result_zip,
        &all_summary.batch_sha256,
        &manifest,
        b"AGRY",
        "closed",
    )?;

    assert!(import_manual_refinement_results(&root, pid + 1, &result_zip).is_err());
    let result = import_manual_refinement_results(&root, pid, &result_zip)?;
    assert_eq!(result.applied, 3);
    assert_eq!(result.loci[0]["appliedTool"], "degap"); // Both closed; ignore return order.
    assert_eq!(result.loci[1]["appliedTool"], "quartet"); // DEGAP failed only at this locus.
    assert_eq!(result.loci[2]["disposition"], "no_eligible_patch");
    assert_eq!(result.loci[3]["appliedTool"], "quartet"); // Closed beats higher-ranked partial.
    let duplicate = import_manual_refinement_results(&root, pid, &result_zip)?;
    assert!(duplicate.duplicate);
    assert_eq!(duplicate.applied, 0);
    assert_eq!(list_manual_refinement_results(&root, pid)?.len(), 1);

    let reopened = crate::db::open_workspace_db(&outcome.project_db_path)?;
    let loaded: String = reopened.query_row(
        "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
        [pid],
        |row| row.get(0),
    )?;
    let loaded: Value = serde_json::from_str(&loaded)?;
    let patch_sha = sha(b"AGRY");
    let projected = loaded[chr]["segments"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            let start = row["start"].as_i64();
            let end = row["end"].as_i64();
            if row["type"] == "gap" {
                FinalPathExportSegment::Gap {
                    gap_size_bp: row["gapSizeBp"].as_i64().unwrap(),
                }
            } else if row["sourceKind"] == "refinement_patch" {
                assert_eq!(row["refinementPatchSha256"], patch_sha);
                FinalPathExportSegment::RefinementPatch {
                    sha256: patch_sha.clone(),
                    start: start.unwrap(),
                    end: end.unwrap(),
                }
            } else {
                FinalPathExportSegment::Source {
                    dataset_name: row["source"]["dataset"].as_str().unwrap().into(),
                    contig_name: row["source"]["contig"].as_str().unwrap().into(),
                    start: start.unwrap(),
                    end: end.unwrap(),
                }
            }
        })
        .collect();
    let exported = temp.path().join("reimported.fa");
    exporter::export_project_final_path_fasta(
        &outcome.project_db_path,
        pid,
        &ExportProjectFinalPathFastaParams {
            output_path: exported.clone(),
            records: vec![FinalPathFastaRecord {
                chr_name: chr.clone(),
                final_path_segments: projected,
            }],
        },
    )?;
    let reimported = read_fasta(&exported, "manual refinement roundtrip", false)?;
    let original = read_fasta(
        &root.join("data/refinement/final.fa"),
        "original path",
        false,
    )?;
    let expected = original[chr].replacen(&"N".repeat(original_size as usize), "AGRY", 1);
    assert_eq!(reimported[chr], expected);

    let late_zip = temp.path().join("late.zip");
    let partial_zip = temp.path().join("partial.zip");
    // A separate single-tool export from before adoption reaches the same locus.
    // Its zero-base result removes the Gap slot completely when explicitly selected.
    let single_manifest = load_manifest(&single)?;
    let locus_id = single_manifest["loci"][0]["id"].as_str().unwrap();
    write_batch(
        &late_zip,
        &single_summary.batch_sha256,
        &single_manifest,
        b"",
        "closed",
    )?;
    write_batch(
        &partial_zip,
        &single_summary.batch_sha256,
        &single_manifest,
        b"CNC",
        "partial",
    )?;
    let late = import_manual_refinement_results(&root, pid, &late_zip)?;
    let partial = import_manual_refinement_results(&root, pid, &partial_zip)?;
    assert_eq!(late.applied, 0);
    assert_eq!(late.loci[0]["disposition"], "already_adopted");
    assert_eq!(late.loci[0]["activeResultSha256"], result.result_sha256);
    assert_eq!(partial.applied, 0);
    assert!(
        switch_manual_refinement_locus(&root, pid, locus_id, 1, &partial.result_sha256, "quartet")
            .is_err()
    );
    assert!(undo_manual_refinement_locus(&root, pid + 1, locus_id, 1).is_err());

    let store = |paths: &Value| -> Result<()> {
        reopened.execute(
            "UPDATE project_assembly_view_state SET final_path_by_chr_json=?2 WHERE project_id=?1",
            rusqlite::params![pid, serde_json::to_string(paths)?],
        )?;
        Ok(())
    };
    let reload = || -> Result<Value> {
        let raw: String = reopened.query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [pid],
            |row| row.get(0),
        )?;
        Ok(serde_json::from_str(&raw)?)
    };
    assert_eq!(reload()?, loaded);
    let patch_slot = loaded[chr]["segments"]
        .as_array()
        .unwrap()
        .iter()
        .position(|row| row["sourceKind"] == "refinement_patch")
        .unwrap();
    let mut edited = loaded.clone();
    edited[chr]["segments"][patch_slot]["start"] = serde_json::json!(2);
    store(&edited)?;
    assert!(undo_manual_refinement_locus(&root, pid, locus_id, 1).is_err());
    assert_eq!(reload()?, edited);
    edited = loaded.clone();
    let outside_edit =
        serde_json::json!({"type":"gap","segmentId":"unrelated-appended-gap","gapSizeBp":12});
    edited[chr]["segments"]
        .as_array_mut()
        .unwrap()
        .push(outside_edit.clone());
    store(&edited)?;
    let switched =
        switch_manual_refinement_locus(&root, pid, locus_id, 1, &late.result_sha256, "quartet")?;
    assert_eq!(switched.adoption_revision, 2);
    assert_eq!(switched.active_tool.as_deref(), Some("quartet"));
    let zero = reload()?;
    assert_eq!(
        zero[chr]["segments"].as_array().unwrap().len(),
        edited[chr]["segments"].as_array().unwrap().len() - 1
    );
    assert_eq!(zero[other], loaded[other]);
    assert!(undo_manual_refinement_locus(&root, pid, locus_id, 1).is_err());
    let undone = undo_manual_refinement_locus(&root, pid, locus_id, 2)?;
    assert_eq!(undone.adoption_revision, 3);
    assert_eq!(undone.active_result_sha256, None);
    let restored = reload()?;
    assert_eq!(restored[chr]["segments"][patch_slot]["segmentId"], target);
    assert_eq!(
        restored[chr]["segments"].as_array().unwrap().last(),
        Some(&outside_edit)
    );
    let replay = import_manual_refinement_results(&root, pid, &result_zip)?;
    assert!(replay.duplicate);
    assert_eq!(replay.loci[0]["adoptionState"], "undone");
    assert_eq!(reload()?, restored);
    switch_manual_refinement_locus(&root, pid, locus_id, 3, &result.result_sha256, "degap")?;
    let history = list_manual_refinement_results(&root, pid)?;
    assert_eq!(history.len(), 3);
    assert!(
        history.iter().all(
            |batch| batch.loci[0]["activeResultSha256"] == result.result_sha256
                && batch.loci[0]["adoptionRevision"] == 4
        )
    );
    let actions: i64 = reopened.query_row(
        "SELECT count(*) FROM project_refinement_action WHERE project_id=?1",
        [pid],
        |row| row.get(0),
    )?;
    assert_eq!(actions, 3);
    Ok(())
}

#[test]
fn manual_refinement_applies_gap_and_both_tel_ends_in_one_project_batch() -> Result<()> {
    use crate::degap_jobs::{
        export_manual_refinement, import_manual_refinement_results, undo_manual_refinement_locus,
    };
    use sha2::{Digest, Sha256};
    use std::io::{Read, Write};
    use zip::{ZipArchive, ZipWriter, write::FileOptions};

    let temp = materialize(false);
    let root = temp.path().join("refined.degap");
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root)?;
    let db = &outcome.project_db_path;
    let pid = initialize_grt_project(db, "Mixed manual refinement")?.project_id;
    let baseline = load_grt_final_path_by_chr_for_project(db, pid)?;
    let (chr, entry) = baseline
        .iter()
        .find(|(_, entry)| {
            entry["segments"]
                .as_array()
                .is_some_and(|rows| rows.iter().any(|r| r["kind"] == "gap"))
        })
        .context("controlled chromosome with a Gap")?;
    let segments = entry["segments"]
        .as_array()
        .context("controlled chromosome segments")?;
    let original = read_fasta(
        &root.join("data/refinement/final.fa"),
        "controlled baseline",
        false,
    )?;
    let original = &original[chr];
    let gap = segments.iter().find(|r| r["kind"] == "gap").unwrap();
    let left = segments.first().unwrap();
    let right = segments.last().unwrap();
    let task_zip = temp.path().join("mixed.zip");
    let request = serde_json::from_value(serde_json::json!({"loci":[
        {"chr":chr,"segment_id":left["segment_id"],"kind":"tel_left","motif":"TTAGGG"},
        {"chr":chr,"segment_id":gap["segment_id"],"kind":"gap","tools":["lrgapcloser"]},
        {"chr":chr,"segment_id":right["segment_id"],"kind":"tel_right","motif":"TTAGGG"},
    ]}))?;
    let batch = export_manual_refinement(&root, pid, &task_zip, &request)?;
    assert_eq!((batch.loci, batch.tasks), (3, 3));
    let manifest: Value = {
        let mut archive = ZipArchive::new(fs::File::open(&task_zip)?)?;
        let mut data = Vec::new();
        archive
            .by_name("refinement_tasks.json")?
            .read_to_end(&mut data)?;
        serde_json::from_slice(&data)?
    };
    let sha = |bytes: &[u8]| format!("{:x}", Sha256::digest(bytes));
    let close = b"GCTA";
    let head = b"CCCTAA";
    let tail = b"TTAGGGTTAGGG";
    let loci = manifest["loci"].as_array().unwrap();
    let return_zip = |file: &Path, corrupt_right_witness: bool| -> Result<()> {
        let mut rows = Vec::new();
        let mut zip = ZipWriter::new(fs::File::create(file)?);
        for locus in loci {
            let id = locus["id"].as_str().unwrap();
            let kind = locus["kind"].as_str().unwrap();
            let tool = locus["tools"][0].as_str().unwrap();
            let (status, operation, segment, replacement) = match kind {
                "gap" => ("closed", "replace_gap", gap, close.as_slice()),
                "tel_left" => ("extended", "prepend_tel", left, head.as_slice()),
                "tel_right" => ("extended", "append_tel", right, tail.as_slice()),
                _ => unreachable!(),
            };
            let start = segment["output_start"].as_u64().unwrap() as usize;
            let end = segment["output_end"].as_u64().unwrap() as usize;
            let before = if corrupt_right_witness && kind == "tel_right" {
                "f".repeat(64)
            } else {
                sha(&original.as_bytes()[start..end])
            };
            let path = format!("patches/{id}.{tool}.seq");
            zip.start_file(&path, FileOptions::default())?;
            zip.write_all(replacement)?;
            rows.push(serde_json::json!({"locus_id":id,"tool":tool,"status":status,"reason":null,
                "attempt_id":"controlled","version":"synthetic-fixture","revision":"test",
                "patch":{"path":path,"operation":operation,"original_length":end-start,
                    "original_sha256":before,"length":replacement.len(),"sha256":sha(replacement)}}));
        }
        zip.start_file("refinement_results.json", FileOptions::default())?;
        zip.write_all(&serde_json::to_vec(
            &serde_json::json!({"schema":"cgat.app-refinement-results.v1",
            "batch_sha256":batch.batch_sha256,"results":rows}),
        )?)?;
        zip.finish()?;
        Ok(())
    };

    let wrong_endpoint = temp.path().join("wrong-endpoint.zip");
    let correct_endpoint = temp.path().join("correct-endpoint.zip");
    return_zip(&wrong_endpoint, true)?;
    return_zip(&correct_endpoint, false)?;
    let first = import_manual_refinement_results(&root, pid, &wrong_endpoint)?;
    assert_eq!(first.applied, 2);
    assert!(
        first
            .loci
            .iter()
            .any(|row| row["kind"] == "tel_right"
                && row["disposition"] == "endpoint_digest_mismatch")
    );
    let second = import_manual_refinement_results(&root, pid, &correct_endpoint)?;
    assert_eq!(second.applied, 1);
    assert!(
        second
            .loci
            .iter()
            .any(|row| row["kind"] == "tel_right" && row["disposition"] == "applied")
    );

    let verify = |file: &Path, left_ext: &str, right_ext: &str| -> Result<()> {
        let conn = crate::db::open_workspace_db(db)?;
        let raw: String = conn.query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [pid],
            |row| row.get(0),
        )?;
        let saved: Value = serde_json::from_str(&raw)?;
        let rows = saved[chr]["segments"].as_array().unwrap();
        let projected = rows
            .iter()
            .map(|segment| {
                let start = segment["start"].as_i64().unwrap();
                let end = segment["end"].as_i64().unwrap();
                if segment["sourceKind"] == "refinement_patch" {
                    FinalPathExportSegment::RefinementPatch {
                        sha256: segment["refinementPatchSha256"].as_str().unwrap().into(),
                        start,
                        end,
                    }
                } else {
                    let src = &segment["source"];
                    FinalPathExportSegment::Source {
                        dataset_name: src["dataset"].as_str().unwrap().into(),
                        contig_name: src["contig"].as_str().unwrap().into(),
                        start,
                        end,
                    }
                }
            })
            .collect();
        exporter::export_project_final_path_fasta(
            db,
            pid,
            &ExportProjectFinalPathFastaParams {
                output_path: file.to_path_buf(),
                records: vec![FinalPathFastaRecord {
                    chr_name: chr.clone(),
                    final_path_segments: projected,
                }],
            },
        )?;
        let output = read_fasta(file, "mixed result", false)?;
        let before = gap["output_start"].as_u64().unwrap() as usize;
        let after = gap["output_end"].as_u64().unwrap() as usize;
        assert_eq!(
            output[chr],
            format!(
                "{}{}{}{}{}",
                left_ext,
                &original[..before],
                std::str::from_utf8(close)?,
                &original[after..],
                right_ext
            )
        );
        Ok(())
    };
    verify(&temp.path().join("both-ends.fa"), "CCCTAA", "TTAGGGTTAGGG")?;
    let left_id = loci
        .iter()
        .find(|locus| locus["kind"] == "tel_left")
        .unwrap()["id"]
        .as_str()
        .unwrap();
    undo_manual_refinement_locus(&root, pid, left_id, 1)?;
    verify(&temp.path().join("only-right.fa"), "", "TTAGGGTTAGGG")?;
    Ok(())
}

#[test]
#[ignore = "requires Python, samtools, minimap2 and ZIP for real Server publications"]
fn cumulative_server_auto_patch_imports_all_versions_without_changing_edited_paths() -> Result<()> {
    let dir = tempdir()?;
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../server/tests/project_auto_patch_fixture.py");
    let generator = std::process::Command::new("python3")
        .arg(script)
        .arg(dir.path())
        .output()?;
    assert!(
        generator.status.success(),
        "{}",
        String::from_utf8_lossy(&generator.stderr)
    );
    let root = dir.path().join("baseline");
    let (outcome, _) = crate::importer::import_from_extracted_bundle(&root)?;
    let db = &outcome.project_db_path;
    let p = initialize_grt_project(db, "already edited LGZ")?.project_id;
    let p2 = initialize_grt_project(db, "independent LGZ")?.project_id;
    let conn = crate::db::open_workspace_db(db)?;
    let edit = "{\"chr2\":{\"user_edit_marker\":\"do not replace\"}}";
    conn.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,updated_at) VALUES(?1,?2,'before') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json",params![p,edit])?;
    let call = |project, filename: &str| -> Result<Value> {
        import_auto_patch_if_recognized(&root, project, &dir.path().join(filename))?
            .context("unrecognized automatic patch")
    };
    // A resealed ZIP with one damaged content object must not register even its intact tool.
    {
        use std::io::Read;
        let mut input = zip::ZipArchive::new(fs::File::open(dir.path().join("tgsgapcloser.zip"))?)?;
        let mut output = zip::ZipWriter::new(fs::File::create(dir.path().join("damaged.zip"))?);
        let mut damaged = false;
        for n in 0..input.len() {
            let mut member = input.by_index(n)?;
            let mut bytes = Vec::new();
            member.read_to_end(&mut bytes)?;
            if member.name().starts_with("objects/") && !damaged && !bytes.is_empty() {
                bytes[0] ^= 1;
                damaged = true;
            }
            output.start_file(member.name(), FileOptions::default())?;
            output.write_all(&bytes)?;
        }
        output.finish()?;
        assert!(damaged);
        let err = call(p, "damaged.zip").unwrap_err();
        assert!(err.to_string().contains("digest mismatch"), "{err:#}");
        for table in ["project_auto_version", "project_auto_version_object"] {
            assert_eq!(
                conn.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r
                    .get::<_, i64>(0))?,
                0
            );
        }
    }
    assert_eq!(
        call(p, "degap.zip")?["addedTools"],
        serde_json::json!(["degap"])
    );
    assert_eq!(
        call(p, "tgsgapcloser.zip")?["addedTools"],
        serde_json::json!(["tgsgapcloser"])
    );
    assert_eq!(call(p, "tgsgapcloser.zip")?["duplicate"], true);
    let version_count = |project| {
        conn.query_row(
            "SELECT COUNT(*) FROM project_auto_version WHERE project_id=?1",
            [project],
            |r| r.get::<_, i64>(0),
        )
    };
    assert_eq!(version_count(p)?, 2);
    assert_eq!(version_count(p2)?, 0);
    let objects = || {
        conn.query_row(
            "SELECT COUNT(*) FROM project_auto_version_object",
            [],
            |r| r.get::<_, i64>(0),
        )
    };
    let first = objects()?;
    assert_eq!(
        call(p2, "tgsgapcloser.zip")?["addedTools"],
        serde_json::json!(["degap", "tgsgapcloser"])
    );
    assert_eq!(first, objects()?);
    let view = load_grt_project_view_for_project(db, p)?;
    assert_eq!(
        view.auto_refinement_effects
            .iter()
            .map(|e| (&*e.tool, e.partial))
            .collect::<Vec<_>>(),
        vec![("degap", 1), ("tgsgapcloser", 1)]
    );
    let after: String = conn.query_row(
        "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
        [p],
        |r| r.get(0),
    )?;
    assert_eq!(after, edit);
    // A different immutable LGZ path is not the same project origin even when the FASTA hash still matches.
    conn.execute("UPDATE grt_package SET final_path_json=json_set(final_path_json,'$.other_origin',1) WHERE id=1",[])?;
    assert!(call(p, "tgsgapcloser.zip").is_err());
    assert_eq!(version_count(p)?, 2);
    assert_eq!(first, objects()?);
    Ok(())
}

#[test]
#[ignore = "requires Python, samtools, minimap2, pigz and ZIP for Server-generated project archives"]
fn project_full_and_light_import_both_automatic_versions_without_a_picker() -> Result<()> {
    let dir = tempdir()?;
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../server/tests/project_auto_patch_fixture.py");
    let generated = std::process::Command::new("python3")
        .arg(script)
        .arg(dir.path())
        .arg("--project-packages")
        .output()?;
    assert!(
        generated.status.success(),
        "{}",
        String::from_utf8_lossy(&generated.stderr)
    );
    let mut records = Vec::new();
    for (mode, ext) in [("full", "zip"), ("light", "tar.gz")] {
        let root = dir.path().join(format!("app-{mode}"));
        let archive = dir.path().join(format!("job.{mode}.{ext}"));
        let (out, _) = crate::importer::import_from_zip(&archive, &root)?;
        let db = &out.project_db_path;
        let p = initialize_grt_project(db, "new project")?.project_id;
        let conn = crate::db::open_workspace_db(db)?;
        let view = load_grt_project_view_for_project(db, p)?;
        assert_eq!(
            view.auto_refinement_effects
                .iter()
                .map(|e| (&*e.tool, e.partial))
                .collect::<Vec<_>>(),
            vec![("degap", 1), ("tgsgapcloser", 1)]
        );
        let mut stmt=conn.prepare("SELECT descriptor_json, baseline_json, effect_json FROM project_auto_version WHERE project_id=?1 ORDER BY tool")?;
        records.push(
            stmt.query_map([p], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                ))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?,
        );
        let count = || {
            conn.query_row(
                "SELECT COUNT(*) FROM project_auto_version_object",
                [],
                |r| r.get::<_, i64>(0),
            )
        };
        let before = count()?;
        let again =
            import_auto_patch_if_recognized(&root, p, &dir.path().join("tgsgapcloser.zip"))?
                .unwrap();
        assert_eq!(
            again["duplicate"],
            mode == "full",
            "first patch hydrates missing Light objects"
        );
        assert_eq!(again["applied"], 0);
        let repeat =
            import_auto_patch_if_recognized(&root, p, &dir.path().join("tgsgapcloser.zip"))?
                .unwrap();
        assert_eq!(repeat["duplicate"], true);
        if mode == "full" {
            assert_eq!(count()?, before);
        } else {
            assert!(count()? > before, "Light did not omit accepted FASTAs");
        }
        // Templates are immutable: a second project inherits the archive, not edits made to its sibling.
        let second = initialize_grt_project(db, "new sibling")?.project_id;
        assert_eq!(
            load_grt_project_view_for_project(db, second)?
                .auto_refinement_effects
                .len(),
            2
        );
    }
    assert_eq!(records[0], records[1]);
    let bad = dir.path().join("light/job");
    let index = bad.join("project_versions/index.json");
    fs::write(&index, b"{}")?;
    let err = crate::importer::import_from_extracted_bundle(&bad).unwrap_err();
    assert!(format!("{err:#}").contains("index checksum"), "{err:#}");
    assert!(!bad.join("project.sqlite").exists());
    Ok(())
}

#[test]
#[ignore = "requires Python, samtools, minimap2 and ZIP for Server publications"]
fn auto_gap_import_prefers_complete_closure_then_tool_priority() -> Result<()> {
    for (both_closed, expected) in [(true, "degap"), (false, "tgsgapcloser")] {
        let dir = tempdir()?;
        let script = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../server/tests/project_auto_patch_fixture.py");
        let mut generator = std::process::Command::new("python3");
        generator.arg(script).arg(dir.path()).arg("--close-tgs");
        if both_closed {
            generator.arg("--close-degap");
        }
        let output = generator.output()?;
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let root = dir.path().join("baseline");
        let (out, _) = crate::importer::import_from_extracted_bundle(&root)?;
        let db = &out.project_db_path;
        let p = initialize_grt_project(db, "closure priority")?.project_id;
        let patch = dir.path().join("tgsgapcloser.zip");
        let result = import_auto_patch_if_recognized(&root, p, &patch)?.unwrap();
        assert_eq!(result["applied"], 1, "{result}");
        let view = load_grt_project_view_for_project(db, p)?;
        assert_eq!(view.auto_refinement_effects.len(), 2);
        for tool in view.auto_refinement_effects {
            assert_eq!(
                tool.project_adopted_gaps,
                Some(usize::from(tool.tool == expected))
            );
            assert_eq!(
                tool.closed,
                usize::from(both_closed || tool.tool == "tgsgapcloser")
            );
            assert_eq!(tool.chromosomes.len(), tool.closed);
        }
        assert_eq!(
            import_auto_patch_if_recognized(&root, p, &patch)?.unwrap()["duplicate"],
            true
        );
    }
    Ok(())
}

#[test]
#[ignore = "requires Python, samtools, minimap2 and ZIP for a manual project round trip"]
fn project_manual_snapshot_and_parameters_roundtrip_without_replacing_archives() -> Result<()> {
    let dir = tempdir()?;
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../server/tests/project_manual_roundtrip_fixture.py");
    let server = |tasks: Option<&Path>| -> Result<()> {
        let mut cmd = std::process::Command::new("python3");
        cmd.arg(&script).arg(dir.path());
        if let Some(tasks) = tasks {
            cmd.arg(tasks);
        }
        let run = cmd.output()?;
        assert!(
            run.status.success(),
            "{}",
            String::from_utf8_lossy(&run.stderr)
        );
        Ok(())
    };
    server(None)?;
    let job = dir.path().join("job");
    let root = dir.path().join("app");
    let (out, _) = crate::importer::import_from_zip(&job.join("07_delivery/job.full.zip"), &root)?;
    let db = &out.project_db_path;
    let p = initialize_grt_project(db, "manual round trip")?.project_id;
    let paths = load_grt_final_path_by_chr_for_project(db, p)?;
    let (chr, entry) = paths
        .iter()
        .find(|(_, e)| {
            e["segments"]
                .as_array()
                .is_some_and(|v| v.iter().any(|s| s["kind"] == "gap"))
        })
        .unwrap();
    let gap = entry["segments"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["kind"] == "gap")
        .unwrap();
    // A separate user-created chromosome is not a selected task, but is part of the exported assembly.
    let other = "controlled-other";
    let conn = crate::db::open_workspace_db(db)?;
    conn.execute("INSERT INTO project_assembly_view_state(project_id, final_path_by_chr_json, updated_at) VALUES(?1,?2,'fixture') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json",
                 params![p,serde_json::to_string(&BTreeMap::from([(other,entry)]))?])?;
    let request = serde_json::from_value(
        serde_json::json!({"loci":[{"chr":chr,"kind":"gap","segment_id":gap["segment_id"],"tools":["lrgapcloser","degap"]}],"tool_parameters":{"lrgapcloser":{"iterations":5}}}),
    )?;
    let tasks = dir.path().join("tasks.zip");
    let exported = crate::degap_jobs::export_manual_refinement(&root, p, &tasks, &request)?;
    server(Some(&tasks))?;
    let tag = &exported.batch_sha256[..16];
    let patch = job.join(format!("07_delivery/manual/job.manual-{tag}.patch.zip"));
    let imported = crate::degap_jobs::import_manual_refinement_results(&root, p, &patch)?;
    assert_eq!(imported.applied, 1);
    assert!(crate::degap_jobs::import_manual_refinement_results(&root, p, &patch)?.duplicate);
    let genome = read_fasta(
        &job.join(format!("05_final/job.manual-{tag}.fa")),
        "Server manual genome",
        false,
    )?;
    let initial = read_fasta(&job.join("05_final/job.lgz.fa"), "unchanged LGZ", false)?;
    assert_eq!(genome[other], initial[chr]);
    let expected = initial[chr].replacen(
        &"N".repeat(gap["length"].as_u64().unwrap() as usize),
        "GATTACA",
        1,
    );
    assert_eq!(genome[chr], expected);
    let saved: String = conn.query_row(
        "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
        [p],
        |r| r.get(0),
    )?;
    let saved: Value = serde_json::from_str(&saved)?;
    let selected = saved[chr]["segments"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["sourceKind"] == "refinement_patch")
        .unwrap();
    assert_eq!(selected["refinementPatchSha256"], sha256_bytes(b"GATTACA"));
    let mut current = paths.clone();
    current.extend(serde_json::from_value::<BTreeMap<String, Value>>(saved)?);
    let mut records = Vec::new();
    for (name, value) in current {
        let path = crate::degap_jobs::canonicalize_entry(&name, value)?;
        let segments = path["segments"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| {
                if row["type"] == "gap" {
                    FinalPathExportSegment::Gap {
                        gap_size_bp: row["gapSizeBp"].as_i64().unwrap(),
                    }
                } else if row["sourceKind"] == "refinement_patch" {
                    FinalPathExportSegment::RefinementPatch {
                        sha256: row["refinementPatchSha256"].as_str().unwrap().into(),
                        start: row["start"].as_i64().unwrap(),
                        end: row["end"].as_i64().unwrap(),
                    }
                } else {
                    FinalPathExportSegment::Source {
                        dataset_name: row["datasetName"].as_str().unwrap().into(),
                        contig_name: row["ctgName"].as_str().unwrap().into(),
                        start: row["start"].as_i64().unwrap(),
                        end: row["end"].as_i64().unwrap(),
                    }
                }
            })
            .collect();
        records.push(FinalPathFastaRecord {
            chr_name: name,
            final_path_segments: segments,
        });
    }
    let app_genome = dir.path().join("exported-by-app.fa");
    exporter::export_project_final_path_fasta(
        db,
        p,
        &ExportProjectFinalPathFastaParams {
            output_path: app_genome.clone(),
            records,
        },
    )?;
    assert_eq!(read_fasta(&app_genome, "App manual genome", false)?, genome);
    Ok(())
}
