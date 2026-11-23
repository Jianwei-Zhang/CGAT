//! Freeze the effective project assembly in the same database transaction as the task witnesses.
//! The ZIP carries only sequence intervals unavailable from a content-bound Server source.
use super::*;
use std::collections::BTreeMap;
use std::io::Seek;

const FILE: &str = "assembly_snapshot.json";
const MAX_INDEX: usize = 128 * 1024 * 1024;
const MAX_OBJECT: usize = 512 * 1024 * 1024;

pub(super) struct Snapshot {
    scratch: tempfile::TempDir,
    objects: BTreeMap<String, usize>,
    total: usize,
    source_maps: server_runtime::SourceMaps,
    pub(super) digest: String,
    segments: BTreeMap<(String, String), Value>,
}

impl Snapshot {
    fn empty() -> Result<Self> {
        Ok(Self {
            scratch: tempfile::tempdir()?,
            total: 0,
            source_maps: Default::default(),
            objects: BTreeMap::new(),
            segments: BTreeMap::new(),
            digest: String::new(),
        })
    }

    fn object(&mut self, bytes: &[u8]) -> Result<String> {
        if bytes.is_empty()
            || bytes.len() > MAX_OBJECT
            || !bytes.iter().all(|b| b"ACGTRYSWKMBDHVN".contains(b))
        {
            bail!("invalid or oversized App-only snapshot interval");
        }
        let sha = hex_sha(bytes);
        if !self.objects.contains_key(&sha) {
            self.total = self
                .total
                .checked_add(bytes.len())
                .context("oversized snapshot")?;
            if self.total as u64 > 8 * 1024u64.pow(3) || self.objects.len() >= 50_000 {
                bail!("snapshot exceeds portable object limits");
            }
            fs::write(self.scratch.path().join(&sha), bytes)?;
            self.objects.insert(sha.clone(), bytes.len());
        }
        Ok(sha)
    }

    pub(super) fn plan(&self, chr: &str, w: &Value) -> Result<Value> {
        let row = self
            .segments
            .get(&(chr.to_owned(), field(w, "segment_id")?.to_owned()))
            .context("task is not on the exported whole-project path")?;
        if &row["witness"] != w {
            bail!("task witness differs from its frozen assembly");
        }
        Ok(row["plan"].clone())
    }

    pub(super) fn write_to<W: Write + Seek>(&self, zip: &mut ZipWriter<W>) -> Result<()> {
        let options = FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        zip.start_file(FILE, options)?;
        std::io::copy(&mut fs::File::open(self.scratch.path().join(FILE))?, zip)?;
        for sha in self.objects.keys() {
            zip.start_file(format!("snapshot_objects/{sha}"), options)?;
            std::io::copy(&mut fs::File::open(self.scratch.path().join(sha))?, zip)?;
        }
        Ok(())
    }
}

fn single(member: Value, from: i64, to: i64) -> Value {
    let size = from.abs_diff(to) + 1;
    json!({"members":[member],"start":if from<=to {1} else {size},"end":if from<=to {size} else {1}})
}

pub(super) fn special_current_plan(
    conn: &Connection,
    workspace: &Path,
    project: i64,
    w: &Value,
) -> Result<Value> {
    let references = reference_map(conn)?;
    build_plan(
        &mut Snapshot::empty()?,
        conn,
        workspace,
        project,
        w,
        &references,
    )
}

fn reference_map(conn: &Connection) -> Result<Value> {
    let raw: Option<String> = conn
        .query_row(
            "SELECT reference_sources_json FROM package_delivery_identity WHERE package_id=1",
            [],
            |r| r.get(0),
        )
        .optional()?;
    Ok(serde_json::from_str(raw.as_deref().unwrap_or("{}"))?)
}

fn build_plan(
    snapshot: &mut Snapshot,
    conn: &Connection,
    workspace: &Path,
    project: i64,
    w: &Value,
    references: &Value,
) -> Result<Value> {
    let a = positive(w, "start")?;
    let b = positive(w, "end")?;
    if let Some(sha) = w["patch_sha256"].as_str() {
        let bytes: Vec<u8> = conn.query_row(
            "SELECT sequence FROM project_refinement_patch WHERE project_id=?1 AND sha256=?2",
            params![project, sha],
            |r| r.get(0),
        )?;
        if hex_sha(&bytes) != sha || a.max(b) as u64 > bytes.len() as u64 {
            bail!("stale manual patch interval");
        }
        let bound = snapshot.object(&bytes[(a.min(b) - 1) as usize..a.max(b) as usize])?;
        return Ok(single(
            json!({"name":sha,"dataset":"@app-patch","start":a.min(b),"end":a.max(b),"length":bytes.len(),"fasta_sha256":null,"interval_sha256":bound}),
            a,
            b,
        ));
    }
    if let Some(chr) = w["reference"].as_str() {
        let (length,fasta):(i64,String)=conn.query_row("SELECT rc.length,rcl.fasta_path FROM project p JOIN reference_chr rc ON rc.reference_genome_id=p.reference_genome_id JOIN reference_chr_locator rcl ON rcl.reference_chr_id=rc.id WHERE p.id=?1 AND rc.chr_name=?2",params![project,chr],|r|Ok((r.get(0)?,r.get(1)?)))?;
        let first = positive(w, "member_start")?;
        let last = positive(w, "member_end")?;
        if last > length || first > last || a.max(b) > last - first + 1 {
            bail!("invalid reference interval");
        }
        let (lo, hi) = (first - 1 + a.min(b), first - 1 + a.max(b));
        let file_sha = references
            .get(chr)
            .and_then(Value::as_str)
            .filter(|x| is_sha(x));
        let interval = if Path::new(&fasta).is_file() {
            Some(hex_sha(
                crate::exporter::load_fasta_source_interval(Path::new(&fasta), chr, lo, hi)?
                    .as_bytes(),
            ))
        } else {
            None
        };
        if file_sha.is_none() && interval.is_none() {
            bail!(
                "cannot identify reference {chr}; restore its FASTA or use a package with reference identities"
            );
        }
        return Ok(single(
            json!({"name":chr,"dataset":"@reference","start":lo,"end":hi,"length":length,"fasta_sha256":file_sha,"interval_sha256":interval}),
            a,
            b,
        ));
    }
    let plan = seed_plan_with_maps(conn, workspace, project, w, &mut snapshot.source_maps)?;
    for m in plan["members"]
        .as_array()
        .context("missing snapshot members")?
    {
        if m["fasta_sha256"].is_string() {
            continue;
        }
        let (ds, name) = (field(m, "dataset")?, field(m, "name")?);
        let fasta:String=conn.query_row("SELECT ssl.fasta_path FROM project_dataset pd JOIN dataset d ON d.id=pd.dataset_id JOIN source_seq ss ON ss.dataset_id=d.id JOIN source_seq_locator ssl ON ssl.source_seq_id=ss.id WHERE pd.project_id=?1 AND d.name=?2 AND ss.seq_name=?3",params![project,ds,name],|r|r.get(0))?;
        let bytes = crate::exporter::load_fasta_source_interval(
            Path::new(&fasta),
            name,
            positive(m, "start")?,
            positive(m, "end")?,
        )?;
        if m["interval_sha256"] != snapshot.object(bytes.as_bytes())? {
            bail!("App-only source {ds}:{name} changed during export");
        }
    }
    Ok(plan)
}

pub(super) fn capture_if_supported(
    conn: &Connection,
    workspace: &Path,
    project: i64,
    loci: &[LocusRequest],
) -> Result<Option<Snapshot>> {
    // Old imported packages keep their compatible task protocol. A project archive makes
    // the complete snapshot mandatory even when the user selected just one gap.
    let is_project: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM package_delivery_identity WHERE package_id=1)",
        [],
        |r| r.get(0),
    )?;
    if !is_project {
        // The first project-package reader (schema 13) did not persist the outer marker.
        let marker = workspace.join("metadata/grt_app_manifest.json");
        if !marker.is_file() {
            return Ok(None);
        }
        let app: Value = serde_json::from_slice(&fs::read(marker)?)?;
        if app["workflow"] != "gpm_grt_app_project_v1" {
            return Ok(None);
        }
    }
    let origin: String = conn.query_row(
        "SELECT q4_artifact_sha256 FROM grt_package WHERE id=1",
        [],
        |r| r.get(0),
    )?;
    let mut paths = load_grt_final_path_for_project_with_connection(conn, project)?;
    let edits: Option<String> = conn
        .query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [project],
            |r| r.get(0),
        )
        .optional()?;
    paths.extend(serde_json::from_str::<BTreeMap<String, Value>>(
        edits.as_deref().unwrap_or("{}"),
    )?);
    let tracks =
        crate::phased_assembly::list_project_phased_chr_tracks_with_connection(conn, project)?;
    for t in &tracks {
        paths.remove(&t.parent_chr_name);
    }
    let mut order = Vec::new();
    let mut stmt=conn.prepare("SELECT rc.chr_name FROM reference_chr rc JOIN project p ON p.reference_genome_id=rc.reference_genome_id WHERE p.id=?1 ORDER BY rc.chr_order,rc.id")?;
    for name in stmt.query_map([project], |r| r.get::<_, String>(0))? {
        let name = name?;
        order.push(name.clone());
        order.extend(
            tracks
                .iter()
                .filter(|t| t.parent_chr_name == name)
                .map(|t| t.label.clone()),
        );
    }
    order.extend(paths.keys().cloned());
    let references = reference_map(conn)?;
    let mut out = Snapshot::empty()?;
    let mut chromosomes = Vec::new();
    for chr in order {
        let Some(entry) = paths.remove(&chr) else {
            continue;
        };
        if chr.is_empty() || chr.contains(|c: char| c.is_control()) || chr.starts_with('>') {
            bail!("invalid FASTA record name");
        }
        let rows = entry["segments"]
            .as_array()
            .context("invalid project chromosome path")?;
        if rows.is_empty() {
            continue;
        }
        // Only the requested witnesses are looked up again to encode refinement_tasks.json.
        // Do not retain two independent copies of an entire wheat-size assembly plan.
        let mut needed = HashSet::new();
        for req in loci.iter().filter(|req| req.chr == chr) {
            for (role, row) in locate(rows, req)? {
                if role != "target" {
                    needed.insert(segment_id(row)?);
                }
            }
        }
        let mut seen = HashSet::new();
        let mut segments = Vec::with_capacity(rows.len());
        for row in rows {
            let w = witness(row).with_context(|| format!("cannot freeze a segment on {chr}"))?;
            let plan = if w["kind"] == "gap" {
                Value::Null
            } else {
                build_plan(&mut out, conn, workspace, project, &w, &references)?
            };
            let id = segment_id(row)?;
            if !seen.insert(id) {
                bail!("duplicate snapshot segment on {chr}");
            }
            let part = json!({"witness":w,"plan":plan});
            if needed.contains(id) {
                out.segments
                    .insert((chr.clone(), id.to_owned()), part.clone());
            }
            segments.push(part);
        }
        chromosomes.push(json!({"chr":chr,"segments":segments}));
    }
    if chromosomes.is_empty() {
        bail!("the project has no exportable assembly");
    }
    let bytes = serde_json::to_vec(
        &json!({"schema":"cgat.manual-assembly-snapshot.v1","origin_fasta_sha256":origin,"chromosomes":chromosomes,"objects":out.objects}),
    )?;
    if bytes.len() > MAX_INDEX {
        bail!("snapshot paths exceed 128 MiB");
    }
    out.digest = hex_sha(&bytes);
    fs::write(out.scratch.path().join(FILE), bytes)?;
    Ok(Some(out))
}
