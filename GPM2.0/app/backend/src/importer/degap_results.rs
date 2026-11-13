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
    Ok(archive.by_name("degap_results.json").is_ok())
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
            let ledger = workspace_root
                .join("metadata/degap_exports")
                .join(format!("{token}.json"));
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
            let imported_path = PathBuf::from(format!("metadata/degap_imports/{token}.json"));
            if workspace_root.join(&imported_path).exists() {
                bail!(
                    "DEGAP task {} has already been imported",
                    field(recipe, "job_id")?
                );
            }
            let relative = field(entry, "package")?;
            validate_add_payload_relpath("DEGAP nested package", relative)?;
            let archive = root.join(relative);
            if hash_file(&archive)? != field(entry, "sha256")? {
                bail!("DEGAP result package checksum mismatch");
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
            register_payload_paths(&payload, &payload, &union)?;
            fs::create_dir_all(union.join("metadata/degap_imports"))?;
            fs::write(union.join(&imported_path), b"")?;
            packages.push((archive, imported_path, entry.clone()));
        }
        drop(conn);
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
