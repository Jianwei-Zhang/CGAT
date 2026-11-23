//! Validate all published versions of a project Full/Light before creating its database.
use super::*;
use std::sync::Arc;

const DIR: &str = "project_versions";
const INDEX_PATH: &str = "project_versions/index.json";
const SCHEMA: &str = "cgat.project-delivery";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema: String,
    schema_version: u32,
    mode: String,
    baseline: Value,
    generation: String,
    baseline_app_path: String,
    variants: BTreeMap<String, Version>,
    objects: BTreeMap<String, String>,
    omitted_sequences: Vec<String>,
}

#[derive(Debug, Clone)]
pub(in crate::grt_package) struct ProjectVersions {
    scratch: Arc<tempfile::TempDir>,
    used: HashSet<String>,
    versions: BTreeMap<String, Version>,
    baseline_record: String,
    effects: BTreeMap<String, AutoRefinementEffect>,
}

fn regular_under(root: &Path, name: &str) -> Result<PathBuf> {
    check_name(name)?;
    let mut path = root.to_owned();
    for part in name.split('/') {
        path.push(part);
        if fs::symlink_metadata(&path)?.file_type().is_symlink() {
            bail!("linked project delivery member");
        }
    }
    if !path.is_file() {
        bail!("missing project delivery member");
    }
    Ok(path)
}

fn check_files(dir: &Path, expected: &HashSet<String>) -> Result<()> {
    let mut actual = HashSet::new();
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        if entry.file_name() == "objects" && entry.file_type()?.is_dir() {
            for file in fs::read_dir(entry.path())? {
                let file = file?;
                if !file.file_type()?.is_file() {
                    bail!("non-file project version object");
                }
                actual.insert(format!(
                    "objects/{}",
                    file.file_name()
                        .into_string()
                        .map_err(|_| anyhow!("invalid object name"))?
                ));
            }
        } else if entry.file_name() == "index.json" && entry.file_type()?.is_file() {
            actual.insert("index.json".into());
        } else {
            bail!("unexpected file in project version directory");
        }
    }
    if &actual != expected {
        bail!("project version object directory differs from manifest");
    }
    Ok(())
}

pub(in crate::grt_package) fn validate_project_versions<C: FnMut() -> bool>(
    root: &Path,
    app: &Value,
    final_path: &Value,
    refined: bool,
    cancel: &mut C,
) -> Result<Option<ProjectVersions>> {
    let Some(seal) = app.get("project_delivery") else {
        match fs::symlink_metadata(root.join(DIR)) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
            Ok(_) => bail!("unbound project version directory"),
        }
    };
    if refined || seal["index"] != INDEX_PATH {
        bail!("invalid project delivery root");
    }
    let file = regular_under(root, INDEX_PATH)?;
    if file.metadata()?.len() > 16 * 1024 * 1024 {
        bail!("oversize project version index");
    }
    let bytes = fs::read(file)?;
    if seal["sha256"] != sha256_bytes(&bytes) {
        bail!("project index checksum mismatch");
    }
    let m: Manifest = serde_json::from_slice(&bytes)?;
    let full = app["fasta_available"] == true;
    let key = serde_json::json!({"schema":SCHEMA,"schema_version":1,"baseline":m.baseline,"variants":m.variants});
    if m.schema != SCHEMA
        || m.schema_version != 1
        || m.variants.len() > 4
        || m.objects.len() > 50_000
        || m.mode != if full { "full" } else { "light" }
        || m.generation != sha256_bytes(&serde_json::to_vec(&key)?)
        || seal["generation"] != m.generation
        || m.baseline["assembly_sha256"] != app["q4_artifact_sha256"]
        || !m.baseline["final_path_sha256"]
            .as_str()
            .is_some_and(is_hash)
        || sha256_file(&regular_under(root, "metadata/grt_final_path.json")?)?
            != m.baseline_app_path
    {
        bail!("project generation, mode or LGZ identity mismatch");
    }
    let omitted: HashSet<String> = m.omitted_sequences.iter().cloned().collect();
    let declared: HashSet<String> = if full {
        HashSet::new()
    } else {
        m.variants
            .values()
            .flat_map(|v| v.accepted_sequence_objects.iter().cloned())
            .collect()
    };
    if omitted != declared || omitted.len() != m.omitted_sequences.len() {
        bail!("unexpected omitted project sequences");
    }
    let mut expected = HashSet::from(["index.json".to_owned()]);
    let mut supplied = HashSet::new();
    let scratch = Arc::new(tempfile::tempdir()?);
    let mut total = 0u64;
    for (sha, name) in &m.objects {
        if cancel() {
            bail!("import cancelled");
        }
        if !is_hash(sha) || omitted.contains(sha) {
            bail!("invalid project object");
        }
        if name.starts_with("project_versions/") {
            if *name != format!("project_versions/objects/{sha}") {
                bail!("invalid embedded object name");
            }
            expected.insert(format!("objects/{sha}"));
        }
        let path = regular_under(root, name)?;
        let length = fs::metadata(&path)?.len();
        total = total
            .checked_add(length)
            .context("oversize project objects")?;
        if length > MAX_OBJECT || total > MAX_TOTAL {
            bail!("oversize project version objects");
        }
        let mut src = fs::File::open(&path)?.take(length + 1);
        let mut dst = fs::File::create_new(scratch.path().join(sha))?;
        let mut block = [0; 65536];
        let mut hash = Sha256::new();
        let mut copied = 0u64;
        loop {
            if cancel() {
                bail!("import cancelled");
            }
            let n = src.read(&mut block)?;
            if n == 0 {
                break;
            }
            hash.update(&block[..n]);
            dst.write_all(&block[..n])?;
            copied += n as u64;
        }
        if copied != length || format!("{:x}", hash.finalize()) != *sha {
            bail!("project object checksum mismatch");
        }
        supplied.insert(sha.clone());
    }
    check_files(&root.join(DIR), &expected)?;
    let mut used = HashSet::new();
    let mut effects = BTreeMap::new();
    let ix = Index {
        schema: "cgat.project-auto-refinement-patch".into(),
        schema_version: 1,
        baseline: m.baseline,
        baseline_app_path: m.baseline_app_path,
        variants: m.variants,
    };
    if !ix.variants.is_empty() {
        let raw = ix.baseline["final_path_sha256"].as_str().unwrap();
        let base = json_at(&obj(scratch.path(), &ix.baseline_app_path)?)?;
        if &base != final_path {
            bail!("package and tool LGZ paths differ");
        }
        verify_baseline_projection(json_at(&obj(scratch.path(), raw)?)?, &base)?;
        used.extend([ix.baseline_app_path.clone(), raw.to_string()]);
        for (tool, v) in &ix.variants {
            if cancel() {
                bail!("import cancelled");
            }
            let view = tempfile::tempdir_in(scratch.path())?;
            effects.insert(
                tool.clone(),
                validate_version(
                    &ix,
                    tool,
                    v,
                    scratch.path(),
                    view.path(),
                    &mut used,
                    &omitted,
                )?,
            );
        }
    }
    if supplied != used {
        bail!("unexpected or missing project version objects");
    }
    let baseline_record = serde_json::to_string(
        &serde_json::json!({"identity":ix.baseline,"app_path":ix.baseline_app_path}),
    )?;
    Ok(Some(ProjectVersions {
        scratch,
        used,
        versions: ix.variants,
        baseline_record,
        effects,
    }))
}

pub(in crate::grt_package) fn retain_package_versions(
    tx: &Transaction<'_>,
    versions: &ProjectVersions,
) -> Result<()> {
    retain_objects(tx, versions.scratch.path(), &versions.used)?;
    for (tool, v) in &versions.versions {
        tx.execute("INSERT INTO package_auto_version(package_id,tool,light_manifest,descriptor_json,baseline_json,effect_json) VALUES(1,?1,?2,?3,?4,?5)",
            params![tool, v.light_manifest,serde_json::to_string(v)?,versions.baseline_record,serde_json::to_string(&versions.effects[tool])?])?;
    }
    Ok(())
}
