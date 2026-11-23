//! Opt-in, two-host check. This never starts native tools or transfers files.
//!
//! Point `CGAT_MANUAL_REFINE_CASE` at a JSON manifest next to the real LGZ Full
//! archive and original Server FASTA. Fields: `full`, `full_sha256`, `lgz_fasta`,
//! `lgz_fasta_sha256`, `single_chr`, `loci` and optional `hifi_reads`, `ont_reads`
//! (Server paths). A gap locus has `chr`, `kind: "gap"`, `gap_start` (0-based in
//! the LGZ FASTA) and optional `tool`. Tel loci have `chr`, `kind: "tel_left"` or
//! `"tel_right"` and `motif`. Select real loci across multiple chromosomes.
//!
//! First run the ignored `stage_actual_manual_refinement_tasks` test. From the
//! original Server workspace run `refine.py` on each emitted `refine-tasks.zip`.
//! Return the untouched result archives as `refine-results.zip` in each mode
//! directory. For each mode independently rebuild `expected.fa` from the frozen
//! LGZ FASTA and the reviewed *native tool evidence*, not the returned ZIP or App
//! output. Write `expected.json` with `results_sha256`, `fasta_sha256` and an
//! `applied_by_kind` map (omit zero counts), then run the ignored
//! `verify_actual_manual_refinement_returns` test with the same case manifest.
use super::*;
use gpm_next_backend::degap_jobs::{ResultStatus, validate_manual_refinement_results};
use gpm_next_backend::grt_package::load_grt_final_path_by_chr_for_project;
use std::collections::BTreeSet;

const MODES: [&str; 2] = ["single", "all"];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ManualCase {
    full: PathBuf,
    full_sha256: String,
    lgz_fasta: PathBuf,
    lgz_fasta_sha256: String,
    single_chr: String,
    loci: Vec<Locus>,
    hifi_reads: Option<Vec<String>>,
    ont_reads: Option<Vec<String>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Locus {
    chr: String,
    kind: String,
    gap_start: Option<u64>,
    tool: Option<String>,
    motif: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Staged {
    project_id: i64,
    batch_sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Expected {
    results_sha256: String,
    fasta_sha256: String,
    applied_by_kind: BTreeMap<String, usize>,
}

fn file_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T> {
    let bytes = fs::read(path).with_context(|| format!("read {}", path.display()))?;
    serde_json::from_slice(&bytes).with_context(|| format!("parse {}", path.display()))
}

fn save_json(path: &Path, value: impl Serialize) -> Result<()> {
    serde_json::to_writer_pretty(fs::File::create_new(path)?, &value)?;
    Ok(())
}

fn manual_case() -> Result<(PathBuf, ManualCase)> {
    let path = PathBuf::from(
        std::env::var_os("CGAT_MANUAL_REFINE_CASE").context("set CGAT_MANUAL_REFINE_CASE")?,
    );
    let root = path.canonicalize()?.parent().unwrap().to_path_buf();
    let case = file_json(&path)?;
    Ok((root, case))
}

fn resolve_locus(locus: &Locus, paths: &BTreeMap<String, Value>) -> Result<Value> {
    let segments = paths
        .get(&locus.chr)
        .and_then(|entry| entry["segments"].as_array())
        .with_context(|| format!("no LGZ path for {}", locus.chr))?;
    let picked = match (
        locus.kind.as_str(),
        locus.gap_start,
        &locus.tool,
        &locus.motif,
    ) {
        ("gap", Some(start), _, None) => {
            // App display projection can split a source on N-runs. Its
            // segment offsets are therefore the prefix sum of displayed lengths.
            let mut offset = 0_u64;
            let mut gap = None;
            for segment in segments {
                if offset == start && segment["kind"] == "gap" {
                    gap = Some(segment);
                    break;
                }
                let length = segment["length"]
                    .as_u64()
                    .context("missing LGZ segment length")?;
                offset = offset
                    .checked_add(length)
                    .context("LGZ coordinate overflow")?;
                if offset > start {
                    break;
                }
            }
            gap
        }
        ("tel_left", None, None, Some(_)) => segments.first().filter(|s| s["kind"] == "source"),
        ("tel_right", None, None, Some(_)) => segments.last().filter(|s| s["kind"] == "source"),
        _ => bail!("invalid locus specification: {} {}", locus.chr, locus.kind),
    }
    .with_context(|| {
        format!(
            "LGZ locus not found: {} {} {:?}",
            locus.chr, locus.kind, locus.gap_start
        )
    })?;
    let id = picked["segment_id"]
        .as_str()
        .context("missing LGZ segment ID")?;
    Ok(json!({"chr":locus.chr,"kind":locus.kind,"segment_id":id,
        "tools":locus.tool.iter().collect::<Vec<_>>(), "motif":locus.motif}))
}

#[test]
fn acceptance_resolves_lgz_loci_without_fabricating_endpoints() -> Result<()> {
    let paths = BTreeMap::from([(
        "chr1".to_owned(),
        json!({"segments":[{"kind":"source","segment_id":"s1","length":50},
            {"kind":"gap","segment_id":"gap","length":11,"output_start":0},
            {"kind":"source","segment_id":"s2","length":30}]}),
    )]);
    let gap: Locus = serde_json::from_value(json!({"chr":"chr1","kind":"gap","gap_start":50}))?;
    let request = resolve_locus(&gap, &paths)?;
    assert_eq!(request["segment_id"], "gap");
    assert_eq!(request["tools"], json!([])); // Exercise the production DEGAP default.
    assert!(
        resolve_locus(
            &Locus {
                gap_start: Some(49),
                ..gap
            },
            &paths
        )
        .is_err()
    );
    let end: Locus =
        serde_json::from_value(json!({"chr":"chr1","kind":"tel_right","motif":"TTTAGGG"}))?;
    assert_eq!(resolve_locus(&end, &paths)?["segment_id"], "s2");
    let mut no_right_source = paths;
    no_right_source.get_mut("chr1").unwrap()["segments"]
        .as_array_mut()
        .unwrap()
        .pop();
    assert!(resolve_locus(&end, &no_right_source).is_err());
    Ok(())
}

#[test]
#[ignore = "requires genuine LGZ Full package and frozen LGZ FASTA"]
fn stage_actual_manual_refinement_tasks() -> Result<()> {
    let (root, case) = manual_case()?;
    let archive = root.join(&case.full);
    assert_eq!(digest(&archive), case.full_sha256);
    let baseline_fa = root.join(&case.lgz_fasta);
    assert_eq!(digest(&baseline_fa), case.lgz_fasta_sha256);
    let baseline = sequences(&baseline_fa);
    let targets: BTreeSet<_> = case.loci.iter().map(|locus| locus.chr.as_str()).collect();
    assert!(targets.len() >= 2 && targets.contains(case.single_chr.as_str()));
    for kind in ["gap", "tel_left", "tel_right"] {
        assert!(
            case.loci.iter().any(|locus| locus.kind == kind),
            "missing {kind} test locus"
        );
    }
    let output = root.join("manual-desktop-roundtrip");
    fs::create_dir(&output).context("use a fresh evidence directory")?;
    for mode in MODES {
        let dir = output.join(mode);
        fs::create_dir(&dir)?;
        let workspace = dir.join("workspace");
        let workspace_str = path_to_string(&workspace);
        let (import, _) = import_from_zip_with_options_and_hooks(
            &archive,
            &workspace,
            ImportOptions {
                import_workers: Some(2),
                require_new_workspace: true,
            },
            &mut |_| {},
            &mut || false,
        )?;
        let initialized = initialize_project(InitializeProjectCommandRequest {
            workspace_root: workspace_str.clone(),
            project_name: format!("Manual refinement {mode}"),
            phased_assembly_enabled: false,
        })
        .map_err(|error| anyhow!(error.message))?;
        let project_id = initialized["projectId"]
            .as_i64()
            .context("missing project ID")?;
        let view = &initialized["grtProjectView"];
        assert_eq!(
            view["recipe"]["schema_version"], "4",
            "expected unrefined LGZ"
        );
        assert_eq!(
            view["verification"]["q4_artifact_sha256"],
            case.lgz_fasta_sha256
        );
        let paths = load_grt_final_path_by_chr_for_project(&import.project_db_path, project_id)?;
        let loci = case
            .loci
            .iter()
            .filter(|locus| mode == "all" || locus.chr == case.single_chr)
            .map(|locus| resolve_locus(locus, &paths))
            .collect::<Result<Vec<_>>>()?;
        let app_baseline = dir.join("app-before.fa");
        export_project_final_path_fasta(
            workspace_str.clone(),
            project_id,
            normalize_for_export(&dir, view, None),
            path_to_string(&app_baseline),
        )
        .map_err(|error| anyhow!(error.message))?;
        assert_eq!(
            sequences(&app_baseline),
            baseline,
            "App LGZ output differs from original"
        );
        let result = tauri::async_runtime::block_on(export_manual_refinement(
            workspace_str,
            project_id,
            path_to_string(&dir.join("refine-tasks.zip")),
            serde_json::from_value(
                json!({"loci":loci,"hifi_reads":case.hifi_reads,"ont_reads":case.ont_reads}),
            )?,
        ))
        .map_err(|error| anyhow!(error.message))?;
        assert_eq!(result["loci"], loci.len());
        assert_eq!(result["tasks"], loci.len()); // This fixture requests one tool per locus.
        let batch_sha256 = result["batch_sha256"]
            .as_str()
            .context("missing batch SHA")?
            .to_owned();
        eprintln!("{mode}: exported {} loci ({batch_sha256})", loci.len());
        save_json(
            &dir.join("staged.json"),
            Staged {
                project_id,
                batch_sha256,
            },
        )?;
    }
    Ok(())
}

#[test]
#[ignore = "requires real native result archives and independent FASTA reconstructions"]
fn verify_actual_manual_refinement_returns() -> Result<()> {
    let (root, case) = manual_case()?;
    assert_eq!(digest(&root.join(&case.full)), case.full_sha256);
    assert_eq!(digest(&root.join(&case.lgz_fasta)), case.lgz_fasta_sha256);
    let output = root.join("manual-desktop-roundtrip");
    // Check both transfers before mutating either test project.
    let inputs = MODES.map(|mode| -> Result<_> {
        let dir = output.join(mode);
        let staged: Staged = file_json(&dir.join("staged.json"))?;
        let expected: Expected = file_json(&dir.join("expected.json"))?;
        let returned = dir.join("refine-results.zip");
        let fasta = dir.join("expected.fa");
        assert_eq!(
            digest(&returned),
            expected.results_sha256,
            "{mode} return archive"
        );
        assert_eq!(
            digest(&fasta),
            expected.fasta_sha256,
            "{mode} independent FASTA"
        );
        assert!(
            !dir.join("verified.json").exists(),
            "{mode} has already been verified"
        );
        let workspace = dir.join("workspace");
        let bundle = validate_manual_refinement_results(&workspace, staged.project_id, &returned)?;
        assert_eq!(bundle.batch_sha256, staged.batch_sha256);
        let mut applied_by_kind = BTreeMap::new();
        let loci = bundle.export["loci"]
            .as_array()
            .context("missing exported loci")?;
        for row in &bundle.results {
            assert!(
                matches!(
                    row.status,
                    ResultStatus::Closed
                        | ResultStatus::Partial
                        | ResultStatus::Extended
                        | ResultStatus::NoCandidate
                        | ResultStatus::Rejected
                ),
                "{mode}: tool did not finish: {row:?}"
            );
            assert!(
                row.attempt_id.is_some() && row.revision.is_some(),
                "{mode}: missing native attempt binding: {row:?}"
            );
            if row.patch.is_some() {
                let locus = loci
                    .iter()
                    .find(|l| l["id"] == row.locus_id)
                    .context("unbound result locus")?;
                let kind = locus["kind"]
                    .as_str()
                    .context("missing locus kind")?
                    .to_owned();
                *applied_by_kind.entry(kind).or_insert(0) += 1;
            }
        }
        assert_eq!(
            applied_by_kind, expected.applied_by_kind,
            "{mode} native patch counts"
        );
        if mode == "all" {
            assert!(
                !applied_by_kind.is_empty(),
                "need a real accepted patch to exercise the write path"
            );
        }
        Ok((
            mode,
            dir,
            workspace,
            staged,
            expected,
            returned,
            fasta,
            bundle.results,
        ))
    });
    let [single, all] = inputs;
    for (mode, dir, workspace, staged, expected, returned, fasta, rows) in [single?, all?] {
        let workspace_str = path_to_string(&workspace);
        let db = workspace.join("project.sqlite");
        let id = staged.project_id;
        let before = serde_json::to_value(backend_load_grt_project_view(&db, id)?)?;
        let import = || {
            tauri::async_runtime::block_on(import_manual_refinement_results(
                workspace_str.clone(),
                id,
                path_to_string(&returned),
            ))
            .map_err(|error| anyhow!(error.message))
        };
        let result = import()?;
        assert_eq!(result["batchSha256"], staged.batch_sha256);
        assert_eq!(result["duplicate"], false);
        assert_eq!(
            result["applied"],
            expected.applied_by_kind.values().sum::<usize>()
        );
        let repeat = import()?;
        assert_eq!(repeat["duplicate"], true);
        assert_eq!(repeat["applied"], 0);
        assert_eq!(
            serde_json::to_value(backend_load_grt_project_view(&db, id)?)?,
            before,
            "LGZ baseline mutated"
        );
        let saved = tauri::async_runtime::block_on(get_project_assembly_view_state(
            workspace_str.clone(),
            id,
        ))
        .map_err(|error| anyhow!(error.message))?;
        let final_path = normalize_for_export(&dir, &before, Some(&saved["finalPathByChr"]));
        let exported = dir.join("app-after.fa");
        export_project_final_path_fasta(workspace_str, id, final_path, path_to_string(&exported))
            .map_err(|error| anyhow!(error.message))?;
        assert_eq!(
            sequences(&exported),
            sequences(&fasta),
            "{mode}: App FASTA differs from independent native reconstruction"
        );
        save_json(
            &dir.join("verified.json"),
            json!({"mode":mode,"batch_sha256":staged.batch_sha256,
            "lgz_fasta_sha256":case.lgz_fasta_sha256,"results_sha256":expected.results_sha256,
            "expected_fasta_sha256":expected.fasta_sha256,"app_fasta_sha256":digest(&exported),
            "native_rows":rows,"import":result,"repeat_idempotent":true}),
        )?;
        eprintln!("{mode}: App FASTA matches independent reconstruction; repeat did not reapply");
    }
    Ok(())
}
