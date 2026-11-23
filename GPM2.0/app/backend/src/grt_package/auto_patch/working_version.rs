//! Look up immutable, project-admitted versions. A read here never selects one or touches edits.
use super::*;
use serde_json::json;

const SERVER_PATH: &str = "metadata/refinement/final_path.json";

/// Only accept content from this workspace's object store, never a caller-supplied file path.
pub(super) fn bound_json(conn: &Connection, sha: &str, limit: u64) -> Result<Value> {
    if !is_hash(sha) {
        bail!("invalid version object identity");
    }
    let id: i64 = conn.query_row(
        "SELECT rowid FROM project_auto_version_object WHERE sha256=?1",
        [sha],
        |r| r.get(0),
    )?;
    let blob = conn.blob_open(
        DatabaseName::Main,
        "project_auto_version_object",
        "content",
        id,
        true,
    )?;
    if blob.len() as u64 > limit {
        bail!("oversized version metadata");
    }
    let mut input = blob.take(limit + 1);
    let mut buf = Vec::new();
    input.read_to_end(&mut buf)?;
    if buf.len() as u64 > limit || sha256_bytes(&buf) != sha {
        bail!("stored automatic version content changed");
    }
    Ok(serde_json::from_slice(&buf)?)
}

pub(super) fn admitted(
    conn: &Connection,
    project: i64,
    tool: &str,
    key: &str,
) -> Result<(Version, Value)> {
    if !is_hash(key) || !matches!(tool, "degap" | "lrgapcloser" | "tgsgapcloser" | "quartet") {
        bail!("invalid working version identity");
    }
    let (descriptor, baseline):(String,String)=conn.query_row("SELECT descriptor_json,baseline_json FROM project_auto_version WHERE project_id=?1 AND tool=?2 AND light_manifest=?3",params![project,tool,key],|r| Ok((r.get(0)?,r.get(1)?))).context("version is not an admitted member of this project")?;
    let v: Version = serde_json::from_str(&descriptor)?;
    let base: Value = serde_json::from_str(&baseline)?;
    let m = bound_json(conn, key, MAX_OBJECT)?;
    if v.light_manifest != key
        || m["schema"] != "cgat.refinement-app-delivery"
        || m["package_mode"] != "light"
        || m["baseline"] != base["identity"]
        || m["tool"] != tool
        || m["run_id"] != v.run_id
    {
        bail!("inconsistent automatic version descriptor");
    }
    Ok((v, m))
}

/// Return per-record evidence for the clicked row only. Do not load FASTAs, inspect the current
/// editable path, reinterpret a partial fill as a closure, or match a version by tool name alone.
pub fn preview_project_refinement_version(
    db: &Path,
    project: i64,
    tool: &str,
    key: &str,
) -> Result<Value> {
    let mut conn = Connection::open_with_flags(db, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let tx = conn.transaction()?;
    let (v, m) = admitted(&tx, project, tool, key)?;
    let sha = m["files"][SERVER_PATH]
        .as_str()
        .context("version has no Server Final Path")?;
    if m["server_final_path_sha256"] != sha {
        bail!("version Server path binding disagrees with inventory");
    }
    let path = bound_json(&tx, sha, MAX_OBJECT)?;
    if path["schema"] != "cgat.refined-final-path"
        || path["tool"] != tool
        || path["baseline"] != m["baseline"]
    {
        bail!("wrong automatic path origin");
    }
    let mut chromosomes = Vec::new();
    for c in path["chromosomes"]
        .as_array()
        .context("missing version chromosomes")?
    {
        let parts = c["segments"]
            .as_array()
            .context("missing version segments")?;
        let name = c["chr"].as_str().context("missing version record name")?;
        let bp = c["length"]
            .as_u64()
            .context("missing version record length")?;
        let digest = c["sha256"]
            .as_str()
            .filter(|s| is_hash(s))
            .context("missing version record digest")?;
        chromosomes.push(json!({"chr":name,"bp":bp,"segments":parts.len(),"gapSegments":parts.iter().filter(|r|r["kind"]=="gap").count(),"sha256":digest}));
    }
    let mut q=tx.prepare("SELECT disposition,COUNT(*) FROM project_auto_gap_review WHERE project_id=?1 AND tool=?2 AND light_manifest=?3 GROUP BY disposition ORDER BY disposition")?;
    let decisions = q
        .query_map(params![project, tool, key], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, usize>(1)?))
        })?
        .collect::<rusqlite::Result<BTreeMap<_, _>>>()?;
    Ok(
        json!({"tool":tool,"versionId":key,"runId":v.run_id,"chromosomes":chromosomes,"decisions":decisions}),
    )
}
