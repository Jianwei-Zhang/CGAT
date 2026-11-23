//! Project-level task export. The old DEGAP shell export remains a separate protocol.
use super::*;
use crate::grt_package::{
    RefinementReadInputs, RefinementReadSource, load_grt_final_path_for_project_with_connection,
    load_project_refinement_read_inputs,
};
use serde::{Deserialize, Serialize};
use std::io::{Cursor, Write};
use std::time::{SystemTime, UNIX_EPOCH};
use zip::{ZipWriter, write::FileOptions};

mod apply;
mod results;

pub use apply::{
    ManualRefinementAction, ManualRefinementImport, import_manual_refinement_results,
    list_manual_refinement_results, switch_manual_refinement_locus, undo_manual_refinement_locus,
};

pub use results::{
    PatchOperation, ResultPatch, ResultRow, ResultStatus, ValidatedRefinementResults,
    validate_manual_refinement_results,
};

const SCHEMA: &str = "cgat.app-refinement-tasks.v1";
const MANIFEST: &str = "refinement_tasks.json";
const TOOLS: &[&str] = &["degap", "lrgapcloser", "tgsgapcloser", "quartet"];
const MAX_MANIFEST: usize = 8 * 1024 * 1024;
const MAX_GAP_BP: i64 = 100_000_000;

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ManualRefinementRequest {
    loci: Vec<LocusRequest>,
    /// None inherits the verified project defaults. Some(empty) clears the field.
    hifi_reads: Option<Vec<String>>,
    ont_reads: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct LocusRequest {
    chr: String,
    kind: LocusKind,
    segment_id: String,
    #[serde(default)]
    tools: Vec<String>,
    motif: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum LocusKind {
    Gap,
    TelLeft,
    TelRight,
}

#[derive(Debug, Serialize)]
pub struct ManualExportSummary {
    pub batch_sha256: String,
    pub loci: usize,
    pub tasks: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ManualRefinementExportReceipt {
    batch_sha256: String,
    output_file_name: String,
    exported_at_ms: u64,
    loci_count: usize,
    tasks_count: usize,
    loci: Vec<Value>,
}

fn hex_sha(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

fn is_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn field<'a>(row: &'a Value, key: &str) -> Result<&'a str> {
    row[key]
        .as_str()
        .filter(|s| !s.is_empty() && !s.chars().any(char::is_control))
        .with_context(|| format!("Final Path requires a valid {key}"))
}

fn positive(row: &Value, key: &str) -> Result<i64> {
    row[key]
        .as_i64()
        .filter(|v| *v > 0)
        .with_context(|| format!("Final Path requires a positive {key}"))
}

fn segment_id(row: &Value) -> Result<&str> {
    let key = if row.get("type").is_some() {
        "segmentId"
    } else {
        "segment_id"
    };
    field(row, key)
}

fn row_kind(row: &Value) -> &str {
    match (row["type"].as_str(), row["kind"].as_str()) {
        (Some(kind), _) => kind,
        (None, Some("gap")) => "gap",
        (None, Some("source" | "patch")) => "ctg",
        _ => "",
    }
}

fn witness(row: &Value) -> Result<Value> {
    let id = segment_id(row)?;
    match row_kind(row) {
        "gap" => {
            let key = if row.get("type").is_some() {
                "gapSizeBp"
            } else {
                "length"
            };
            Ok(json!({"segment_id":id,"kind":"gap","gap_bp":positive(row,key)?}))
        }
        "ctg" if row["sourceKind"] != "ref_segment" => {
            if row.get("type").is_some()
                && row["serverBaseline"] != true
                && row["assemblyCtgId"].is_i64()
            {
                return Ok(
                    json!({"segment_id":id,"kind":"ctg","assembly_ctg_id":positive(row,"assemblyCtgId")?,
                    "start":positive(row,"start")?,"end":positive(row,"end")?}),
                );
            }
            let source = &row["source"];
            let (start, end) = if row.get("type").is_some() {
                (positive(row, "start")?, positive(row, "end")?)
            } else {
                let start = positive(source, "start")?;
                let end = positive(source, "end")?;
                if source["orientation"] == "-" {
                    (end, start)
                } else {
                    (start, end)
                }
            };
            Ok(
                json!({"segment_id":id,"kind":"ctg","dataset":field(source,"dataset")?,
                "contig":field(source,"contig")?,"start":start,"end":end}),
            )
        }
        _ => bail!("segment {id} lacks a supported assembly source for manual refinement"),
    }
}

fn seed_plan(conn: &Connection, workspace: &Path, project_id: i64, w: &Value) -> Result<Value> {
    let start = positive(w, "start")?;
    let end = positive(w, "end")?;
    let (seed, members) = if let Some(id) = w["assembly_ctg_id"].as_i64() {
        let seed = DegapJobSeedSegment {
            assembly_ctg_id: id,
            start,
            end,
        };
        let members = load_seed_plan(conn, workspace, project_id, "", &seed)?;
        (seed, members)
    } else {
        let dataset = field(w, "dataset")?;
        let contig = field(w, "contig")?;
        let (length, fasta): (i64, String) = conn
            .query_row(
                "SELECT ss.length, ssl.fasta_path FROM source_seq ss
             JOIN dataset d ON d.id=ss.dataset_id
             JOIN project_dataset pd ON pd.dataset_id=d.id
             JOIN source_seq_locator ssl ON ssl.source_seq_id=ss.id
             WHERE pd.project_id=?1 AND d.name=?2 AND ss.seq_name=?3",
                params![project_id, dataset, contig],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .with_context(|| format!("source {dataset}:{contig} is unavailable in the project"))?;
        let fasta = PathBuf::from(fasta);
        server_relative_locator_path(workspace, &fasta)?;
        let file_hash = server_runtime::bind_member(workspace, &fasta, dataset, contig, length)?;
        let member = SeedMemberPlan {
            source_seq_name: contig.into(),
            dataset_name: dataset.into(),
            source_length: length,
            source_start: 1,
            source_end: length,
            local_fasta_path: fasta,
            server_fasta_sha256: file_hash,
            server_fasta_path: String::new(),
        };
        (
            DegapJobSeedSegment {
                assembly_ctg_id: 0,
                start,
                end,
            },
            vec![member],
        )
    };
    let plan = server_runtime::seed_plan(&seed, &members)?;
    if plan["members"]
        .as_array()
        .context("missing seed members")?
        .iter()
        .any(|row| {
            !["fasta_sha256", "interval_sha256"]
                .iter()
                .any(|key| row[*key].as_str().is_some_and(is_sha))
        })
    {
        bail!(
            "segment {} lacks content-bound Server sources",
            w["segment_id"]
        );
    }
    Ok(plan)
}

fn locate<'a>(rows: &'a [Value], req: &LocusRequest) -> Result<Vec<(&'static str, &'a Value)>> {
    let mut matches = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| segment_id(row).ok() == Some(req.segment_id.as_str()));
    let (i, target) = matches
        .next()
        .filter(|_| matches.next().is_none())
        .with_context(|| {
            format!(
                "selected segment {} is absent or ambiguous on {}",
                req.segment_id, req.chr
            )
        })?;
    match req.kind {
        LocusKind::Gap
            if row_kind(target) == "gap"
                && i > 0
                && i + 1 < rows.len()
                && row_kind(&rows[i - 1]) == "ctg"
                && row_kind(&rows[i + 1]) == "ctg" =>
        {
            Ok(vec![
                ("seqleft", &rows[i - 1]),
                ("target", target),
                ("seqright", &rows[i + 1]),
            ])
        }
        LocusKind::TelLeft if i == 0 && row_kind(target) == "ctg" => Ok(vec![("endpoint", target)]),
        LocusKind::TelRight if i + 1 == rows.len() && row_kind(target) == "ctg" => {
            Ok(vec![("endpoint", target)])
        }
        _ => bail!(
            "segment {} is not a Gap with direct flanks or the selected physical endpoint",
            req.segment_id
        ),
    }
}

fn tools_for(req: &LocusRequest) -> Result<Vec<String>> {
    let tool = match req.tools.as_slice() {
        [] => "degap",
        [tool] if TOOLS.contains(&tool.as_str()) => tool,
        _ => bail!("select exactly one refinement tool for {}", req.segment_id),
    };
    if req.kind != LocusKind::Gap && tool != "degap" {
        bail!("telomere refinement requires DEGAP TelSeeker");
    }
    // Keep the v1 manifest array for deployed readers, with one entry per new job.
    Ok(vec![tool.to_owned()])
}

fn reads_for(
    req: &ManualRefinementRequest,
    initial: RefinementReadInputs,
) -> Result<RefinementReadInputs> {
    let group = |paths: &Option<Vec<String>>, defaults: Vec<RefinementReadSource>| {
        paths
            .as_ref()
            .map(|paths| {
                paths
                    .iter()
                    .map(|path| {
                        let sha256 = defaults
                            .iter()
                            .find(|row| &row.path == path)
                            .and_then(|row| row.sha256.clone());
                        RefinementReadSource {
                            path: path.clone(),
                            sha256,
                        }
                    })
                    .collect()
            })
            .unwrap_or(defaults)
    };
    let reads = RefinementReadInputs {
        hifi: group(&req.hifi_reads, initial.hifi),
        ont: group(&req.ont_reads, initial.ont),
    };
    let mut seen = HashSet::new();
    for row in reads.hifi.iter().chain(&reads.ont) {
        if !row.path.starts_with('/')
            || row.path.len() <= 1
            || row.path.chars().any(char::is_control)
            || !seen.insert(&row.path)
            || row.sha256.as_deref().is_some_and(|sha| !is_sha(sha))
        {
            bail!("reads must have unique absolute Server paths and valid optional digests");
        }
    }
    Ok(reads)
}

fn motif_for(conn: &Connection, req: &LocusRequest) -> Result<String> {
    let motif = if let Some(value) = &req.motif {
        value.clone()
    } else {
        let mut stmt = conn.prepare("SELECT DISTINCT motif FROM telomere_rule ORDER BY motif")?;
        let rows = stmt
            .query_map([], |r| r.get::<_, String>(0))?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        let [value] = rows.as_slice() else {
            bail!("choose a telomere motif for {}", req.chr);
        };
        value.clone()
    };
    let motif = motif.trim().to_ascii_uppercase();
    if motif.is_empty() || !motif.bytes().all(|base| b"ACGT".contains(&base)) {
        bail!("telomere motif must contain only A/C/G/T");
    }
    Ok(motif)
}

fn build_manifest(
    conn: &Connection,
    workspace: &Path,
    project_id: i64,
    request: &ManualRefinementRequest,
    reads: RefinementReadInputs,
    export_id: &str,
) -> Result<(Value, ManualExportSummary)> {
    validate_project_exists(conn, project_id)?;
    if request.loci.is_empty() {
        bail!("select at least one actual Gap or Tel locus");
    }
    let origin: String = conn
        .query_row(
            "SELECT q4_artifact_sha256 FROM grt_package WHERE id=1",
            [],
            |r| r.get(0),
        )
        .context("manual refinement requires a verified Server project of origin")?;
    if !is_sha(&origin) {
        bail!("project is missing its verified Server FASTA digest");
    }
    let persisted: Option<String> = conn
        .query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [project_id],
            |r| r.get(0),
        )
        .optional()?;
    let current: Value = serde_json::from_str(persisted.as_deref().unwrap_or("{}"))?;
    let mut baseline = None;
    let mut ids = HashSet::new();
    let mut loci = Vec::new();
    let mut task_count = 0;
    for req in &request.loci {
        if req.chr.is_empty()
            || req.segment_id.is_empty()
            || req.chr.chars().any(char::is_control)
            || req.segment_id.chars().any(char::is_control)
        {
            bail!("invalid locus identity");
        }
        let entry = if let Some(entry) = current.get(&req.chr) {
            entry
        } else {
            if baseline.is_none() {
                baseline = Some(load_grt_final_path_for_project_with_connection(
                    conn, project_id,
                )?);
            }
            baseline
                .as_ref()
                .and_then(|all| all.get(&req.chr))
                .context("chromosome has no Final Path")?
        };
        let rows = entry["segments"]
            .as_array()
            .context("chromosome has no actual Final Path segments")?;
        let located = locate(rows, req)?;
        let id = hex_sha(&serde_json::to_vec(&(&req.chr, req.kind, &req.segment_id))?);
        if !ids.insert(id.clone()) {
            bail!("duplicate selected locus {}", req.segment_id);
        }
        let tools = tools_for(req)?;
        task_count += tools.len();
        let mut witnesses = Map::new();
        let mut plans = Map::new();
        for (label, row) in located {
            let w = witness(row)?;
            if label != "target" {
                plans.insert(label.into(), seed_plan(conn, workspace, project_id, &w)?);
            }
            witnesses.insert(label.into(), w);
        }
        let mut locus = json!({"id":id,"chr":req.chr,"kind":req.kind,"target":req.segment_id,
            "tools":tools,"witnesses":witnesses,"seed_plans":plans});
        if req.kind == LocusKind::Gap {
            if req.motif.is_some() {
                bail!("a Gap does not accept a telomere motif");
            }
            let gap_bp = positive(&locus["witnesses"]["target"], "gap_bp")?;
            if gap_bp > MAX_GAP_BP {
                bail!("original Gap N run exceeds 100 Mb at {}", req.segment_id);
            }
            locus["gap_bp"] = json!(gap_bp);
        } else {
            locus["motif"] = json!(motif_for(conn, req)?);
        }
        loci.push(locus);
    }
    let summary = ManualExportSummary {
        batch_sha256: String::new(),
        loci: loci.len(),
        tasks: task_count,
    };
    Ok((
        json!({"schema":SCHEMA,"export_id":export_id,"origin_fasta_sha256":origin,"reads":reads,"loci":loci}),
        summary,
    ))
}

fn create_payload(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .with_context(|| format!("cannot create new export file {}", path.display()))?;
    let result = f.write_all(bytes).and_then(|()| f.sync_all());
    if let Err(error) = result {
        drop(f);
        let _ = fs::remove_file(path);
        return Err(error.into());
    }
    Ok(())
}

/// Export a private project receipt and a data-only ZIP. The caller flushes
/// pending edits before calling; the DB read transaction binds a single saved revision.
pub fn export_manual_refinement(
    workspace: &Path,
    project_id: i64,
    output: &Path,
    request: &ManualRefinementRequest,
) -> Result<ManualExportSummary> {
    let db = workspace.join("project.sqlite");
    if !db.is_file() {
        bail!("manual refinement requires an existing project workspace");
    }
    let defaults = load_project_refinement_read_inputs(&db, project_id)?;
    let reads = reads_for(request, defaults)?;
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction()?;
    let exported_at = SystemTime::now().duration_since(UNIX_EPOCH)?;
    let export_id = hex_sha(&serde_json::to_vec(&(
        workspace.to_string_lossy(),
        project_id,
        output.to_string_lossy(),
        exported_at.as_nanos().to_string(),
    ))?);
    let (manifest, mut summary) =
        build_manifest(&tx, workspace, project_id, request, reads, &export_id)?;
    let bytes = serde_json::to_vec(&manifest)?;
    if bytes.len() > MAX_MANIFEST {
        bail!("manual refinement manifest exceeds 8 MiB");
    }
    summary.batch_sha256 = hex_sha(&bytes);
    tx.commit()?;
    let mut zip = ZipWriter::new(Cursor::new(Vec::new()));
    zip.start_file(MANIFEST, FileOptions::default())?;
    zip.write_all(&bytes)?;
    zip.start_file("README.txt", FileOptions::default())?;
    let filename = output
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("refinement_tasks.zip");
    let argument = if filename.starts_with('-') {
        format!("./{filename}")
    } else {
        filename.to_owned()
    };
    write!(
        zip,
        "CGAT project manual refinement task manifest.\n\nRun from the matching CGAT Server workspace root:\npython .lib/tools/refine.py {}\n\nIf the recorded reads are unavailable on that Server, add --hifi and/or --ont with the corresponding read paths. The command runs the locked tools, writes the batch report under 08_refinement_jobs/02_manual/, updates 06_report/report.html, and produces a refinement_results.zip for import into this App project.\n\nDo not edit or run code from this archive.\n",
        shell_quote(&argument)
    )?;
    let archive = zip.finish()?.into_inner();
    let ledgers = workspace.join("metadata/refinement_exports");
    ensure_refinement_export_directory(workspace, &ledgers)?;
    fs::create_dir_all(&ledgers)?;
    let ledger = ledgers.join(format!("{}.json", summary.batch_sha256));
    create_payload(
        &ledger,
        &serde_json::to_vec(
            &json!({"project_id":project_id,"batch_sha256":summary.batch_sha256,"manifest":manifest,
                "output_file_name": filename, "exported_at_ms": u64::try_from(exported_at.as_millis())? }),
        )?,
    )?;
    if let Err(error) = create_payload(output, &archive) {
        fs::remove_file(&ledger)
            .context("failed to roll back incomplete refinement export receipt")?;
        return Err(error);
    }
    Ok(summary)
}

fn ensure_refinement_export_directory(workspace: &Path, dir: &Path) -> Result<()> {
    if [&workspace.join("metadata"), dir].iter().any(|path| {
        path.symlink_metadata()
            .is_ok_and(|meta| meta.is_symlink() || !meta.is_dir())
    }) {
        bail!("refinement export receipts must be stored in an ordinary workspace directory");
    }
    Ok(())
}

/// Reconstruct recent export history from the very receipts used for import.
/// This never saves the Assembly view, or returns private reads/seed paths.
pub fn list_manual_refinement_exports(
    workspace: &Path,
    project_id: i64,
) -> Result<Vec<ManualRefinementExportReceipt>> {
    let db = workspace.join("project.sqlite");
    if !db.is_file() {
        bail!("refinement export history requires an existing project workspace");
    }
    validate_project_exists(&open_workspace_db(&db)?, project_id)?;
    let ledgers = workspace.join("metadata/refinement_exports");
    ensure_refinement_export_directory(workspace, &ledgers)?;
    if !ledgers.is_dir() {
        return Ok(Vec::new());
    }
    let mut receipts = fs::read_dir(&ledgers)?
        .filter_map(|entry| {
            let entry = entry.ok()?;
            if !entry.file_type().ok()?.is_file() {
                return None;
            }
            let batch = entry
                .file_name()
                .to_str()?
                .strip_suffix(".json")?
                .to_owned();
            is_sha(&batch).then_some((entry.metadata().ok()?.modified().ok()?, batch))
        })
        .collect::<Vec<_>>();
    receipts.sort_unstable_by(|a, b| b.cmp(a));
    Ok(receipts
        .into_iter()
        .filter_map(|(_, batch)| {
            let receipt = results::registered_export_receipt(workspace, project_id, &batch).ok()?;
            let filename = field(&receipt, "output_file_name").ok()?;
            if filename.contains(['/', '\\']) || matches!(filename, "." | "..") {
                return None;
            }
            let loci = receipt["manifest"]["loci"].as_array()?;
            let tasks_count = loci
                .iter()
                .map(|locus| locus["tools"].as_array().map_or(0, Vec::len))
                .sum();
            Some(ManualRefinementExportReceipt {
                batch_sha256: batch,
                output_file_name: filename.to_owned(),
                exported_at_ms: receipt["exported_at_ms"].as_u64()?,
                loci_count: loci.len(),
                tasks_count,
                loci: loci
                    .iter()
                    .map(|locus| {
                        json!({"chr":locus["chr"], "kind":locus["kind"],
                "segmentId":locus["target"], "tools":locus["tools"], "motif":locus["motif"]})
                    })
                    .collect(),
            })
        })
        .take(20)
        .collect())
}
