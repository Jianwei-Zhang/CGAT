//! Opt-in integration test with unmodified archives from actual Server runs.
//! Runs desktop command bodies and frontend state normalization without a window.
use super::*;
use gpm_next_backend::grt_package::load_grt_source_card_trace;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::process::Command;

#[path = "refinement_acceptance_manual.rs"]
mod manual;

#[derive(Deserialize)]
struct Case {
    id: String,
    tool: Option<String>,
    full: PathBuf,
    light: PathBuf,
    full_sha256: String,
    light_sha256: String,
    accepted: usize,
    assembly: PathBuf,
    assembly_sha256: String,
}

fn digest(path: &Path) -> String {
    let mut hash = Sha256::new();
    std::io::copy(&mut fs::File::open(path).unwrap(), &mut hash).unwrap();
    format!("{:x}", hash.finalize())
}

fn sequences(path: &Path) -> BTreeMap<String, String> {
    let mut result = BTreeMap::new();
    let mut name = String::new();
    for line in fs::read_to_string(path).unwrap().lines() {
        if let Some(header) = line.strip_prefix('>') {
            name = header.split_whitespace().next().unwrap().into();
            assert!(result.insert(name.clone(), String::new()).is_none());
        } else {
            result.get_mut(&name).unwrap().push_str(line.trim());
        }
    }
    assert!(!result.is_empty());
    result
}

// Strict comparison with bounded diagnostics: never dump two whole genomes on error.
fn assert_same_sequences(path: &Path, expected: &BTreeMap<String, String>, case: &str) {
    let actual = sequences(path);
    assert!(
        actual.keys().eq(expected.keys()),
        "{case}: exported record names differ"
    );
    for (name, want) in expected {
        let got = &actual[name];
        assert_eq!(
            got.len(),
            want.len(),
            "{case}/{name}: exported length differs"
        );
        if got == want {
            continue;
        }
        if let Some((index, (a, b))) = got
            .bytes()
            .zip(want.bytes())
            .enumerate()
            .find(|(_, (a, b))| a != b)
        {
            panic!(
                "{case}/{name}: first differing base at {}: App={}, Server={}",
                index + 1,
                char::from(a),
                char::from(b)
            );
        }
    }
}

fn normalize_for_export(case_dir: &Path, view: &Value, saved: Option<&Value>) -> Value {
    let input = case_dir.join("native-project-view.json");
    fs::write(&input, serde_json::to_vec_pretty(view).unwrap()).unwrap();
    let mut node =
        Command::new(std::env::var_os("CGAT_ACCEPTANCE_NODE").unwrap_or_else(|| "node".into()));
    node.arg(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../scripts/normalize-refinement-acceptance.mjs"),
    )
    .arg(input);
    if let Some(saved) = saved {
        let input = case_dir.join("saved-final-path.json");
        fs::write(&input, serde_json::to_vec(&saved).unwrap()).unwrap();
        node.arg(input);
    }
    let output = node.output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).unwrap()
}

#[test]
#[ignore = "requires opt-in actual Server Full/Light packages and Windows Node"]
fn actual_server_archives_roundtrip_through_desktop_commands() {
    let input = PathBuf::from(
        std::env::var_os("CGAT_REFINEMENT_APP_CASES").expect("set actual case manifest"),
    );
    let root = input.parent().unwrap();
    let cases: Vec<Case> = serde_json::from_slice(&fs::read(&input).unwrap()).unwrap();
    assert!(!cases.is_empty());
    let output = root.join("desktop-roundtrip");
    fs::create_dir(&output).expect("use a fresh evidence directory");
    let mut evidence = Vec::new();
    for case in cases {
        assert!(
            !case.id.is_empty()
                && case
                    .id
                    .bytes()
                    .all(|ch| ch.is_ascii_alphanumeric() || ch == b'-')
        );
        let options = ImportOptions {
            import_workers: Some(2),
            require_new_workspace: true,
        };
        let assembly = root.join(&case.assembly);
        assert_eq!(
            digest(&assembly),
            case.assembly_sha256,
            "{} Server FASTA",
            case.id
        );
        let expected = sequences(&assembly);
        for (mode, archive, archive_sha) in [
            ("full", &case.full, &case.full_sha256),
            ("light", &case.light, &case.light_sha256),
        ] {
            let archive = root.join(archive);
            assert_eq!(&digest(&archive), archive_sha, "{} {mode} archive", case.id);
            let light = mode == "light";
            let case_dir = output.join(format!("{}-{mode}", case.id));
            fs::create_dir(&case_dir).unwrap();
            let workspace = case_dir.join("workspace");
            let import = || {
                import_from_zip_with_options_and_hooks(
                    &archive,
                    &workspace,
                    options,
                    &mut |_| {},
                    &mut || false,
                )
            };
            let (outcome, _) =
                import().unwrap_or_else(|error| panic!("{} {mode}: {error:#}", case.id));
            let workspace_str = path_to_string(&workspace);
            let initialized = initialize_project(InitializeProjectCommandRequest {
                workspace_root: workspace_str.clone(),
                project_name: format!("{} {mode}", case.id),
                phased_assembly_enabled: false,
            })
            .unwrap();
            let id = initialized["projectId"].as_i64().unwrap();
            let raw_view = &initialized["grtProjectView"];
            let refined = case.tool.is_some();
            assert_eq!(
                raw_view["recipe"]["schema_version"],
                if refined { "5" } else { "4" }
            );
            if let Some(tool) = &case.tool {
                let raw =
                    gpm_next_backend::grt_package::load_grt_final_path(&outcome.project_db_path)
                        .unwrap();
                assert_eq!(&raw["tool"], tool.as_str());
                assert_eq!(
                    raw_view["recipe"]["final_q_relpath"],
                    "data/refinement/final.fa"
                );
                assert_eq!(
                    raw_view["verification"]["q4_artifact_sha256"],
                    case.assembly_sha256
                );
            }
            let cards = raw_view["source_cards"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|card| card["placement_mode"] == "refinement")
                .collect::<Vec<_>>();
            if case.accepted > 0 {
                assert!(!cards.is_empty());
            } else {
                assert!(cards.is_empty());
            }
            for card in &cards {
                let key = card["source_card_key"].as_str().unwrap();
                let trace = load_grt_source_card_trace(&outcome.project_db_path, key).unwrap();
                assert!(
                    !trace.final_path_segments.is_empty(),
                    "missing refined path trace for {key}"
                );
            }
            let initializer = backend_list_initializer_options(&outcome.project_db_path).unwrap();
            let description = initializer
                .existing_projects
                .iter()
                .find(|project| project.id == id)
                .unwrap()
                .description
                .as_deref()
                .unwrap();
            if case.accepted > 0 {
                assert!(description.contains("accepted refinement"));
            } else if refined {
                assert!(description.contains("zero accepted edits"));
            } else {
                assert!(description.starts_with("locked LGZ recipe"));
            }
            assert!(!initializer.datasets.is_empty());
            assert!(
                initializer
                    .datasets
                    .iter()
                    .all(|dataset| dataset.fasta_available != light)
            );
            let final_path = normalize_for_export(&case_dir, raw_view, None);
            let export = case_dir.join("app-export.fa");
            let result = export_project_final_path_fasta(
                workspace_str.clone(),
                id,
                final_path.clone(),
                path_to_string(&export),
            );
            if light {
                assert!(result.is_err(), "Light must not export phantom sequences");
                assert!(!export.exists());
            } else {
                result.unwrap();
                assert_same_sequences(&export, &expected, &case.id);
            }
            // Save an actual changed Final Path using the desktop persistence body.
            let mut manual = final_path;
            let entry = manual.as_object_mut().unwrap().values_mut().next().unwrap();
            entry["segments"]
                .as_array_mut()
                .unwrap()
                .push(json!({"segmentId":"manual-tail","type":"gap","gapSizeBp":7}));
            update_project_assembly_view_state(serde_json::from_value(json!({
                "workspaceRoot":workspace_str,"projectId":id,"trackView":{},
                "supportDsCtgLenRulesByChr":{},"trackScrollState":{},"subviewTrackScrollState":{},
                "supportMirroredCtgs":[],"hiddenPrimaryCtgIds":[],"hiddenPrimaryCtgIdsByChr":{},
                "trackDragOffsets":[],"subviewTrackDragOffsets":[],"subviewAnchorStateByKey":{},
                "finalPathViewMode":"table","finalPathByChr":manual,"degapProjectState":{}
            })).unwrap()).unwrap();
            let before = digest(&outcome.project_db_path);
            let rejection = import().unwrap_err();
            assert!(format!("{rejection:#}").contains("destination must not exist"));
            assert_eq!(
                digest(&outcome.project_db_path),
                before,
                "repeat import mutated edited database"
            );
            let reloaded =
                tauri::async_runtime::block_on(get_project_assembly_view_state(workspace_str, id))
                    .unwrap();
            assert_eq!(reloaded["finalPathByChr"], manual);
            let baseline_after =
                backend_load_grt_project_view(&outcome.project_db_path, id).unwrap();
            assert_eq!(serde_json::to_value(baseline_after).unwrap(), *raw_view);
            eprintln!(
                "{} {mode}: archive/trace/{} / edit preserved",
                case.id,
                if light {
                    "export refused"
                } else {
                    "sourced export equal"
                }
            );
            evidence.push(
                json!({"case":case.id,"mode":mode,"tool":case.tool,"archive_sha256":archive_sha,
                "server_assembly_sha256":case.assembly_sha256,"accepted_edits":case.accepted,
                "refinement_source_cards":cards.len(),"edited_db_sha256":before,
                "repeat_import_rejected_without_mutation":true,"saved_edit_reloaded":true,
                "sourced_export_sha256":(!light).then(|| digest(&export)),
                "light_export_unavailable":light}),
            );
        }
    }
    fs::write(
        output.join("roundtrip-receipt.json"),
        serde_json::to_vec_pretty(&evidence).unwrap(),
    )
    .unwrap();
}
