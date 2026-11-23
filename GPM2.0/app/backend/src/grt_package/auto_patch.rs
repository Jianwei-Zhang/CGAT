//! Add validated, immutable tool versions to one existing project. Never update the edit overlay.
use super::*;
use rusqlite::{DatabaseName, TransactionBehavior};
use std::io::{Read, Write};
use zip::ZipArchive;

const INDEX: &str = "auto_refinement.json";
const LIGHT_MANIFEST: &str = "metadata/refinement/manifest.json";
const MAX_OBJECT: u64 = 512 * 1024 * 1024;
const MAX_TOTAL: u64 = 8 * 1024 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Index {
    schema: String,
    schema_version: u32,
    baseline: Value,
    baseline_app_path: String,
    variants: BTreeMap<String, Version>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Version {
    run_id: String,
    light_manifest: String,
    accepted_sequence_objects: Vec<String>,
}

fn is_hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn obj(root: &Path, sha: &str) -> Result<PathBuf> {
    if !is_hash(sha) {
        bail!("invalid automatic patch object digest");
    }
    let p = root.join(sha);
    if !p.is_file() {
        bail!("missing automatic patch object {sha}");
    }
    Ok(p)
}
fn json_at(p: &Path) -> Result<Value> {
    Ok(serde_json::from_reader(std::io::BufReader::new(
        fs::File::open(p)?,
    ))?)
}
fn check_name(name: &str) -> Result<()> {
    validate_relpath(name, "automatic version member")?;
    for p in name.split('/') {
        let device = p.split('.').next().unwrap_or("").to_ascii_uppercase();
        if p.is_empty()
            || p.ends_with(['.', ' '])
            || p.chars().any(|c| c.is_control() || "<>:\"|?*".contains(c))
            || matches!(
                device.as_str(),
                "CON" | "AUX" | "NUL" | "PRN" | "CONIN$" | "CONOUT$"
            )
            || device
                .strip_prefix("COM")
                .or_else(|| device.strip_prefix("LPT"))
                .is_some_and(|s| s.chars().count() == 1 && "123456789¹²³".contains(s))
        {
            bail!("invalid automatic version file name");
        }
    }
    Ok(())
}
// Only the display fields listed in lgz_app_package.project_final_path differ.
// Comparing the two paths ties the App project identity to the very Server
// baseline hash referenced by each tool's independently validated manifest.
fn verify_baseline_projection(mut server: Value, app: &Value) -> Result<()> {
    let mut projected = app.clone();
    for key in ["workflow", "schema_version", "q4_relpath"] {
        if server.get(key).is_none() || projected.get(key).is_none() {
            bail!("missing baseline path metadata");
        }
        server[key] = projected[key].clone();
    }
    for chr in server["chromosomes"]
        .as_array_mut()
        .context("missing baseline chromosomes")?
    {
        chr.as_object_mut()
            .context("invalid original chromosome")?
            .remove("display_evidence");
        for segment in chr["segments"]
            .as_array_mut()
            .context("missing baseline segments")?
        {
            let fields = segment
                .as_object_mut()
                .context("invalid baseline segment")?;
            for key in [
                "eventId",
                "evidence_ids",
                "evidenceIds",
                "source_card_key",
                "sourceCardKey",
            ] {
                fields.remove(key);
            }
        }
    }
    for chr in projected["chromosomes"]
        .as_array_mut()
        .context("missing projected chromosomes")?
    {
        chr.as_object_mut()
            .context("invalid projected chromosome")?
            .remove("display_evidence");
    }
    if server != projected {
        bail!("automatic patch Server and App baseline paths differ");
    }
    Ok(())
}
fn base_matches(conn: &Connection, project: i64, index: &Index, app_base: &Value) -> Result<()> {
    let (sha, raw): (String,String) = conn.query_row("SELECT q4_artifact_sha256,final_path_json FROM grt_package WHERE id=1 AND EXISTS(SELECT 1 FROM project WHERE id=?1)", [project], |r| Ok((r.get(0)?,r.get(1)?)))?;
    let saved: Value = serde_json::from_str(&raw)?;
    if saved["schema"] == "cgat.refined-final-path"
        || saved.get("baseline").is_some_and(|v| v.is_object()) && saved.get("tool").is_some()
    {
        if saved["baseline"] != index.baseline {
            bail!("automatic patch belongs to a different LGZ baseline");
        }
    } else if &saved != app_base || index.baseline["assembly_sha256"].as_str() != Some(&sha) {
        bail!("automatic patch does not match the imported LGZ Final Path and FASTA");
    }
    Ok(())
}
fn read_objects(zip: &mut ZipArchive<fs::File>, objects: &Path) -> Result<HashSet<String>> {
    let mut seen = HashSet::new();
    let mut total = 0u64;
    let mut count_index = 0;
    for n in 0..zip.len() {
        let mut f = zip.by_index(n)?;
        let mode = f.unix_mode().unwrap_or(0) & 0o170000;
        if !matches!(mode, 0 | 0o100000) || f.is_dir() {
            bail!("unexpected non-file in automatic patch");
        }
        if f.name() == INDEX {
            count_index += 1;
            continue;
        }
        let sha = f
            .name()
            .strip_prefix("objects/")
            .filter(|s| is_hash(s))
            .context("unexpected automatic patch member")?
            .to_owned();
        if !seen.insert(sha.clone()) {
            bail!("duplicate automatic patch member");
        }
        let size = f.size();
        total = total
            .checked_add(size)
            .context("oversize automatic patch")?;
        if size > MAX_OBJECT || total > MAX_TOTAL {
            bail!("automatic patch exceeds import limits");
        }
        let mut out = fs::File::create_new(objects.join(&sha))?;
        let mut hash = Sha256::new();
        let mut reader = (&mut f).take(size + 1);
        let mut block = [0u8; 65536];
        let mut len = 0;
        loop {
            let n = reader.read(&mut block)?;
            if n == 0 {
                break;
            }
            hash.update(&block[..n]);
            out.write_all(&block[..n])?;
            len += n as u64;
        }
        if len != size || format!("{:x}", hash.finalize()) != sha {
            bail!("automatic patch member length or digest mismatch");
        }
    }
    if count_index != 1 {
        bail!("duplicate automatic patch manifest");
    }
    Ok(seen)
}
fn validate_version(
    index: &Index,
    tool: &str,
    v: &Version,
    objects: &Path,
    view: &Path,
    used: &mut HashSet<String>,
) -> Result<AutoRefinementEffect> {
    if !matches!(tool, "degap" | "tgsgapcloser" | "quartet" | "lrgapcloser") {
        bail!("unknown automatic tool");
    }
    let mp = obj(objects, &v.light_manifest)?;
    let m = json_at(&mp)?;
    if m["package_mode"] != "light"
        || m["tool"] != tool
        || m["run_id"] != v.run_id
        || m["baseline"] != index.baseline
    {
        bail!("automatic patch tool identity or baseline mismatch");
    }
    let mut names = HashSet::from([LIGHT_MANIFEST.to_owned()]);
    let files = m["files"]
        .as_object()
        .context("missing Light file inventory")?;
    for (name, hash) in files {
        check_name(name)?;
        let low = name.to_ascii_lowercase();
        if !names.insert(low.clone())
            || [
                ".fa",
                ".fasta",
                ".fna",
                ".fq",
                ".fastq",
                ".fa.gz",
                ".fasta.gz",
                ".fna.gz",
                ".fq.gz",
                ".fastq.gz",
            ]
            .iter()
            .any(|s| low.ends_with(s))
        {
            bail!("non-Light or repeated member in automatic version");
        }
        let sha = hash
            .as_str()
            .context("invalid automatic version file digest")?;
        let src = obj(objects, sha)?;
        let dst = view.join(name);
        fs::create_dir_all(dst.parent().unwrap())?;
        fs::hard_link(src, &dst)?;
        used.insert(sha.to_owned());
    }
    fs::hard_link(mp, view.join(LIGHT_MANIFEST))?;
    used.insert(v.light_manifest.clone());
    let allowed = format!("refinement:{tool}");
    let mut sources: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
    for row in m["sources"]
        .as_array()
        .context("invalid automatic source catalog")?
    {
        if row["origin"] == "lgz" {
            continue;
        }
        if row["origin"] != allowed {
            bail!("unexpected automatic source origin");
        }
        let sha = row["fasta_sha256"]
            .as_str()
            .context("missing accepted FASTA digest")?;
        let name = row["contig"]
            .as_str()
            .context("missing accepted contig identity")?;
        let length = usize::try_from(
            row["length"]
                .as_u64()
                .context("invalid accepted contig length")?,
        )?;
        if sources
            .entry(sha.into())
            .or_default()
            .insert(name.into(), length)
            .is_some()
        {
            bail!("duplicate accepted contig");
        }
    }
    if sources.keys().ne(v.accepted_sequence_objects.iter()) {
        bail!("automatic patch sequence set differs from accepted sources");
    }
    for (sha, expected) in sources {
        let records = read_fasta(&obj(objects, &sha)?, "automatic patch sources", false)?;
        if records.len() != expected.len()
            || records
                .iter()
                .any(|(n, s)| expected.get(n) != Some(&s.len()))
        {
            bail!("automatic patch source sequences do not match the tool catalog");
        }
        used.insert(sha);
    }
    let validated =
        validate_grt_delivery_package_with_progress_and_cancel(view, &mut |_, _| {}, &mut || {
            false
        })?;
    validated
        .auto_effect
        .context("automatic version lacks verified per-tool outcome evidence")
}

/// None means this is not the automatic protocol; let the manual/legacy reader validate it.
pub fn import_auto_patch_if_recognized(
    workspace: &Path,
    project: i64,
    file: &Path,
) -> Result<Option<Value>> {
    let mut zip = ZipArchive::new(fs::File::open(file)?)?;
    if !zip.file_names().any(|n| n == INDEX) {
        return Ok(None);
    }
    if zip.len() > 50_000 {
        bail!("too many automatic patch members");
    }
    let index: Index = {
        let entry = zip.by_name(INDEX)?;
        if entry.size() > 1024 * 1024 {
            bail!("oversize automatic patch manifest");
        }
        serde_json::from_reader(entry.take(1024 * 1024 + 1))?
    };
    if index.schema != "cgat.project-auto-refinement-patch"
        || index.schema_version != 1
        || index.variants.is_empty()
        || index.variants.len() > 4
        || !["assembly_sha256", "final_path_sha256"]
            .iter()
            .all(|k| index.baseline[*k].as_str().is_some_and(is_hash))
    {
        bail!("invalid automatic refinement patch");
    }
    let db = workspace.join("project.sqlite");
    if !db.is_file() {
        bail!("automatic patch needs an existing project");
    }
    let tmp = tempfile::tempdir()?;
    let objects = tmp.path().join("objects");
    fs::create_dir(&objects)?;
    let supplied = read_objects(&mut zip, &objects)?;
    let base = json_at(&obj(&objects, &index.baseline_app_path)?)?;
    let server_sha = index.baseline["final_path_sha256"]
        .as_str()
        .context("missing baseline identity")?;
    verify_baseline_projection(json_at(&obj(&objects, server_sha)?)?, &base)?;
    {
        let reader = Connection::open_with_flags(&db, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        base_matches(&reader, project, &index, &base)?;
    }
    let mut used = HashSet::from([index.baseline_app_path.clone(), server_sha.to_owned()]);
    let mut effects = BTreeMap::new();
    for (tool, v) in &index.variants {
        let view = tempfile::tempdir_in(tmp.path())?;
        effects.insert(
            tool,
            validate_version(&index, tool, v, &objects, view.path(), &mut used)?,
        );
    }
    if supplied != used {
        bail!("automatic patch contains unreferenced or missing data");
    }
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    base_matches(&tx, project, &index, &base)?;
    for sha in &used {
        let path = obj(&objects, sha)?;
        let size = i64::try_from(fs::metadata(&path)?.len())?;
        let inserted = tx.execute("INSERT INTO project_auto_version_object(sha256,content) VALUES(?1,zeroblob(?2)) ON CONFLICT(sha256) DO NOTHING",params![sha,size])?;
        let id = tx.query_row(
            "SELECT rowid FROM project_auto_version_object WHERE sha256=?1",
            [sha],
            |r| r.get(0),
        )?;
        let mut blob = tx.blob_open(
            DatabaseName::Main,
            "project_auto_version_object",
            "content",
            id,
            inserted == 0,
        )?;
        if inserted != 0 {
            if std::io::copy(&mut fs::File::open(path)?, &mut blob)? != size as u64 {
                bail!("incomplete version object");
            }
        } else {
            let mut h = Sha256::new();
            std::io::copy(&mut blob, &mut h)?;
            if format!("{:x}", h.finalize()) != *sha {
                bail!("stored automatic object has changed");
            }
        }
    }
    let mut added = Vec::new();
    for (tool, v) in &index.variants {
        let descriptor = serde_json::to_string(v)?;
        let base_record = serde_json::to_string(
            &serde_json::json!({"identity":index.baseline,"app_path":index.baseline_app_path}),
        )?;
        let effect = serde_json::to_string(&effects[tool])?;
        let n=tx.execute("INSERT INTO project_auto_version(project_id,tool,light_manifest,descriptor_json,baseline_json,effect_json) VALUES(?1,?2,?3,?4,?5,?6) ON CONFLICT(project_id,tool,light_manifest) DO NOTHING",params![project,tool,v.light_manifest,descriptor,base_record,effect])?;
        if n!=0 { added.push(tool); }
        else if !tx.query_row("SELECT descriptor_json=?4 AND baseline_json=?5 AND effect_json=?6 FROM project_auto_version WHERE project_id=?1 AND tool=?2 AND light_manifest=?3",params![project,tool,v.light_manifest,descriptor,base_record,effect],|r|r.get::<_,bool>(0))? { bail!("existing automatic version has a different identity"); }
    }
    tx.commit()?;
    Ok(Some(
        serde_json::json!({"kind":"automatic", "addedTools":added,"versions":index.variants.len(),"duplicate":added.is_empty()}),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn automatic_members_have_portable_non_aliasing_names() {
        for name in ["../x", "tmp/COM¹.A", "LPT²", "p/NUL.tsv", "name. ", "a:b", "a\\b"] {
            assert!(check_name(name).is_err(), "{name}");
        }
        assert!(check_name("metadata/refinement/measurements.tsv").is_ok());
    }
}
