//! Batch candidates are checked against local export receipts before mutation.
//! An outer rollback covers the entire batch, including source associations.
use super::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::io::Read;

pub fn is_degap_results_package(path: &Path) -> Result<bool> {
    let name = path.to_string_lossy().to_ascii_lowercase();
    if name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        return Ok(false);
    }
    let mut archive = ZipArchive::new(File::open(path)?)?;
    let legacy = archive.by_name("degap_results.json").is_ok();
    if legacy && archive.by_name("refinement_results.json").is_ok() {
        bail!("ambiguous refinement archive contains both legacy and current manifests");
    }
    Ok(legacy)
}

fn hash_file(path: &Path) -> Result<String> {
    let mut hash = Sha256::new();
    let mut file = File::open(path)?;
    let mut buffer = [0_u8; 65536];
    loop {
        let size = file.read(&mut buffer)?;
        if size == 0 {
            break;
        }
        hash.update(&buffer[..size]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn field<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .with_context(|| format!("DEGAP result requires {key}"))
}

fn register_payload_paths(root: &Path, dir: &Path, union: &Path) -> Result<()> {
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        let dest = union.join(path.strip_prefix(root)?);
        if path.is_dir() {
            fs::create_dir_all(&dest)?;
            register_payload_paths(root, &path, union)?;
        } else {
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::write(dest, b"")?;
        }
    }
    Ok(())
}

pub fn import_degap_results_with_hooks<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(Vec<Value>, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    process_degap_results(
        zip_path,
        workspace_root,
        project_id,
        false,
        on_progress,
        should_cancel,
    )
}

/// The project refinement card may accept verified legacy candidate metadata,
/// but these archives do not establish a modern locus and replacement interval.
pub(crate) fn validate_legacy_degap_candidates(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
) -> Result<Vec<Value>> {
    let (candidates, _) = process_degap_results(
        zip_path,
        workspace_root,
        project_id,
        true,
        &mut |_| {},
        &mut || false,
    )?;
    Ok(candidates)
}

fn legacy_candidate(entry: &Value) -> Value {
    let recipe = &entry["recipe"];
    json!({"locusId":recipe["token"], "chr":recipe["chr_name"], "kind":"legacy",
        "target":recipe["job_id"], "disposition":"legacy_candidate_only",
        "candidates":[{"tool":"degap","status":"legacy_candidate_only",
            "ctgName":entry["ctg_name"], "sha256":entry["sha256"]}]})
}

fn process_degap_results<P, C>(
    zip_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    candidates_only: bool,
    on_progress: &mut P,
    should_cancel: &mut C,
) -> Result<(Vec<Value>, Vec<ImportProgress>)>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    validate_archive_path(zip_path)?;
    let mut outer = ZipArchive::new(File::open(zip_path)?)?;
    let mut seen = HashSet::new();
    for index in 0..outer.len() {
        let entry = outer.by_index(index)?;
        let name = entry.name();
        let package = name
            .strip_prefix("packages/")
            .is_some_and(|tail| !tail.contains('/') && tail.ends_with(".zip"));
        if !seen.insert(name.to_string())
            || !(name == "degap_results.json" || name == "packages/" || package)
        {
            bail!("Unexpected or duplicate DEGAP result archive entry: {name}");
        }
    }
    drop(outer);
    check_import_cancel(should_cancel)?;
    let db = workspace_root.join(PROJECT_DB_NAME);
    if !db.is_file() {
        bail!("DEGAP results require an existing project workspace");
    }
    let root = workspace_root.join(CACHE_DIR).join(format!(
        "degap_results_{}",
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    ));
    fs::create_dir_all(&root)?;
    let result = (|| -> Result<(Vec<Value>, Vec<ImportProgress>)> {
        let mut progress = Vec::new();
        let mut emit = |step: ImportProgress| {
            on_progress(step.clone());
            progress.push(step);
        };
        extract_delivery_to_root(
            zip_path,
            &root,
            default_import_workers(),
            &mut emit,
            should_cancel,
        )?;
        let manifest: Value = serde_json::from_slice(&fs::read(root.join("degap_results.json"))?)?;
        if manifest["schema"] != "gpm.degap.results.v1" {
            bail!("Unsupported DEGAP result package");
        }
        let entries = manifest["results"]
            .as_array()
            .filter(|rows| !rows.is_empty())
            .context("DEGAP result package has no candidates")?;
        let union = root.join("rollback-payload");
        fs::create_dir_all(&union)?;
        let conn = open_workspace_db(&db)?;
        let mut tokens = HashSet::new();
        let mut packages = Vec::new();
        let mut candidates = Vec::new();
        for (index, entry) in entries.iter().enumerate() {
            check_import_cancel(should_cancel)?;
            let recipe = &entry["recipe"];
            let token = field(recipe, "token")?;
            if token.len() != 64
                || !token.bytes().all(|b| b.is_ascii_hexdigit())
                || !tokens.insert(token.to_string())
            {
                bail!("Invalid or duplicate DEGAP task token");
            }
            let metadata = workspace_root.join("metadata");
            let exports = metadata.join("degap_exports");
            let ledger = exports.join(format!("{token}.json"));
            for path in [&metadata, &exports, &ledger] {
                if path.symlink_metadata().is_ok_and(|meta| meta.is_symlink()) {
                    bail!("DEGAP export receipt must not traverse a symlink");
                }
            }
            let saved: Value = serde_json::from_slice(
                &fs::read(&ledger)
                    .with_context(|| "This DEGAP task was not exported from this workspace")?,
            )?;
            if &saved != recipe || saved["project_id"].as_i64() != Some(project_id) {
                bail!("DEGAP result does not match the original project/task receipt");
            }
            let ids: Vec<i64> = recipe["segments"]
                .as_array()
                .context("Missing DEGAP seed identities")?
                .iter()
                .map(|s| s["id"].as_i64().context("Invalid DEGAP seed identity"))
                .collect::<Result<_>>()?;
            if crate::degap_jobs::degap_seed_snapshot(&conn, project_id, &ids)? != recipe["sources"]
            {
                bail!(
                    "DEGAP source objects changed since export; review the original task before importing"
                );
            }
            if crate::degap_jobs::degap_final_path_snapshot(
                &conn,
                project_id,
                field(recipe, "chr_name")?,
            )? != recipe["final_path"]
            {
                bail!(
                    "Final Path changed since this DEGAP export; review and re-export the task before importing"
                );
            }
            if let Some(plans) = recipe.get("seed_plans") {
                let proof = &entry["source_proof"];
                if proof["schema"] != "cgat.degap-seed-sources"
                    || proof["schema_version"] != 1
                    || proof["token"] != token
                {
                    bail!("DEGAP result lacks the exported source-resolution proof");
                }
                let is_sha = |value: &Value| {
                    value.as_str().is_some_and(|text| {
                        text.len() == 64 && text.bytes().all(|byte| byte.is_ascii_hexdigit())
                    })
                };
                let plans = plans.as_object().context("invalid exported seed plans")?;
                let labels = proof["labels"]
                    .as_object()
                    .context("missing resolved seed labels")?;
                if labels.len() != plans.len() {
                    bail!("resolved seed labels differ from the export");
                }
                for (label, plan) in plans {
                    let resolved = labels.get(label).context("missing resolved seed label")?;
                    let filename = if label == "endpoint" {
                        "endpoint.ctg.fa".to_string()
                    } else {
                        format!("{label}.fa")
                    };
                    if resolved["plan"] != *plan
                        || !is_sha(&resolved["seed_sha256"])
                        || resolved["seed_sha256"] != entry["seed_sha256"][&filename]
                    {
                        bail!("DEGAP consumed seeds differ from the resolved export plan");
                    }
                    let members = plan["members"]
                        .as_array()
                        .context("missing seed source members")?;
                    let sources = resolved["sources"]
                        .as_array()
                        .context("missing resolved sources")?;
                    if members.len() != sources.len() {
                        bail!("DEGAP resolved source count differs");
                    }
                    for (member, source) in members.iter().zip(sources) {
                        for key in ["dataset", "name", "length", "start", "end"] {
                            if member[key] != source[key] {
                                bail!("DEGAP resolved source identity differs");
                            }
                        }
                        for key in ["fasta_sha256", "interval_sha256"] {
                            if !is_sha(&source[key]) {
                                bail!("DEGAP resolved source content hash is missing");
                            }
                            if !member[key].is_null() && member[key] != source[key] {
                                bail!("DEGAP source content differs from the exported identity");
                            }
                        }
                    }
                }
            }
            let imported_path = PathBuf::from(format!("metadata/degap_imports/{token}.json"));
            let relative = field(entry, "package")?;
            validate_add_payload_relpath("DEGAP nested package", relative)?;
            if !relative
                .strip_prefix("packages/")
                .is_some_and(|name| !name.contains('/') && name.ends_with(".zip"))
            {
                bail!("invalid DEGAP nested candidate package path");
            }
            let archive = root.join(relative);
            if hash_file(&archive)? != field(entry, "sha256")? {
                bail!("DEGAP result package checksum mismatch");
            }
            // Collections are cumulative: jobs that finish later share a package
            // with earlier imports. Skip only byte-verified, identical deliveries;
            // never overwrite a prior candidate or trust a token alone.
            let imported_receipt = workspace_root.join(&imported_path);
            if imported_receipt.exists() {
                if imported_receipt.symlink_metadata()?.is_symlink()
                    || imported_receipt
                        .parent()
                        .context("missing DEGAP receipt directory")?
                        .symlink_metadata()?
                        .is_symlink()
                {
                    bail!("DEGAP import receipt must not traverse a symlink");
                }
                let previous: Value = serde_json::from_slice(&fs::read(imported_receipt)?)?;
                if previous["recipe"] != *recipe || previous["delivery"] != *entry {
                    bail!("DEGAP result differs from the previously imported task receipt");
                }
                if candidates_only {
                    candidates.push(legacy_candidate(entry));
                }
                continue;
            }
            let extracted = root.join(format!("candidate-{index}"));
            extract_delivery_to_root(
                &archive,
                &extracted,
                default_import_workers(),
                &mut emit,
                should_cancel,
            )?;
            let nested = read_add_ctg_manifest(&extracted)?;
            if nested.ctg_name != field(entry, "ctg_name")?
                || nested.target_chr != field(recipe, "target_chr")?
                || nested.target_track != field(recipe, "target_track")?
            {
                bail!("DEGAP candidate target does not match its export receipt");
            }
            if nested.source != format!("DEGAP:{token}:{}", field(recipe, "job_id")?) {
                bail!("DEGAP candidate provenance does not match its task receipt");
            }
            let payload = extracted.join("gpm_server");
            validate_add_ctg_payload_merge_targets(&payload, workspace_root, &payload)?;
            if candidates_only {
                manifests::validate_add_ctg_package(
                    &db,
                    workspace_root,
                    project_id,
                    &nested,
                    &payload,
                )?;
                candidates.push(legacy_candidate(entry));
                continue;
            }
            register_payload_paths(&payload, &payload, &union)?;
            fs::create_dir_all(union.join("metadata/degap_imports"))?;
            fs::write(union.join(&imported_path), b"")?;
            packages.push((archive, imported_path, entry.clone()));
        }
        drop(conn);
        if candidates_only {
            return Ok((candidates, progress));
        }
        if packages.is_empty() {
            bail!("All DEGAP tasks in this package have already been imported");
        }
        let mut rollback = AddImportRollback::capture(workspace_root, &db, &union)?;
        let imported = (|| -> Result<Vec<Value>> {
            let mut outcomes = Vec::new();
            for (archive, imported_path, delivery) in packages {
                let recipe = delivery["recipe"].clone();
                check_import_cancel(should_cancel)?;
                let target = AddCtgImportTarget {
                    target_chr: field(&recipe, "target_chr")?.to_string(),
                    target_track: field(&recipe, "target_track")?.to_string(),
                };
                let (outcome, _) = add_ctg::import_add_ctg_package_internal(
                    &archive,
                    workspace_root,
                    project_id,
                    Some(target),
                    &mut emit,
                    should_cancel,
                )?;
                let value = json!({"jobId": recipe["job_id"], "chrName": recipe["chr_name"],
                    "token": recipe["token"], "ctgName": outcome.ctg_name,
                    "assemblyCtgId": outcome.assembly_ctg_id, "datasetId": outcome.dataset_id,
                    "sourceSeqId": outcome.source_seq_id, "targetChr": outcome.target_chr,
                    "targetTrack": outcome.target_track,
                    "uncompletedJobCount": manifest["notes"].as_array().map_or(0, Vec::len)});
                let path = workspace_root.join(imported_path);
                fs::create_dir_all(path.parent().unwrap())?;
                fs::write(
                    path,
                    serde_json::to_vec_pretty(
                        &json!({"recipe": recipe, "delivery": delivery, "result": value}),
                    )?,
                )?;
                let conn = open_workspace_db(&db)?;
                let raw: Option<String> = conn.query_row("SELECT degap_project_state_json FROM project_assembly_view_state WHERE project_id=?1", [project_id], |r| r.get(0)).optional()?;
                let mut state: Value = serde_json::from_str(raw.as_deref().unwrap_or("{}"))?;
                if let Some(jobs) = state["jobs"].as_array_mut() {
                    for job in jobs {
                        if job["jobId"] == value["jobId"] && job["chrName"] == value["chrName"] {
                            if !job["importedResults"].is_array() {
                                job["importedResults"] = json!([]);
                            }
                            job["importedResults"]
                                .as_array_mut()
                                .unwrap()
                                .push(value.clone());
                        }
                    }
                    conn.execute("UPDATE project_assembly_view_state SET degap_project_state_json=?1 WHERE project_id=?2", params![state.to_string(), project_id])?;
                }
                outcomes.push(value);
            }
            check_import_cancel(should_cancel)?;
            Ok(outcomes)
        })();
        match imported {
            Ok(outcomes) => {
                rollback.disarm()?;
                Ok((outcomes, progress))
            }
            Err(error) => {
                rollback
                    .rollback()
                    .context("DEGAP batch import rollback failed")?;
                Err(error)
            }
        }
    })();
    let _ = fs::remove_dir_all(root);
    result
}
