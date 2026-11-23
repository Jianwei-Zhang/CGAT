//! Project-level task export. The old DEGAP shell export remains a separate protocol.
use super::*;
use crate::grt_package::{
    RefinementReadInputs, RefinementReadSource, load_grt_final_path_for_project_with_connection,
    load_project_refinement_read_inputs,
};
use serde::{Deserialize, Serialize};
use std::io::Write;
use std::time::{SystemTime, UNIX_EPOCH};
use zip::{ZipWriter, write::FileOptions};

mod apply;
pub(crate) use apply::{
    canonicalize_entry, load_project_paths, update_length, write_project_paths,
};
mod results;
mod snapshot;

pub use apply::{
    ManualRefinementAction, ManualRefinementImport, import_manual_refinement_results,
    list_manual_refinement_results, switch_manual_refinement_locus, undo_manual_refinement_locus,
};

pub use results::{
    PatchOperation, ResultPatch, ResultRow, ResultStatus, ValidatedRefinementResults,
    validate_manual_refinement_results,
};

const SCHEMA: &str = "cgat.app-refinement-tasks.v1";
const SNAPSHOT_TASKS: &str = "cgat.app-refinement-tasks.v2";
const MANIFEST: &str = "refinement_tasks.json";
const TOOLS: &[&str] = &["degap", "lrgapcloser", "tgsgapcloser", "quartet"];
const MAX_MANIFEST: usize = 8 * 1024 * 1024;
const MAX_GAP_BP: i64 = 100_000_000;
const TGS_HIFI_MINIMAP_PRESETS: &[&str] = &[
    "-x asm20",
    "-x asm5",
    "-x asm10",
    "-x map-hifi",
    "-x map-pb",
];
const TGS_ONT_MINIMAP_PRESETS: &[&str] = &["-x ava-ont", "-x map-ont", "-x asm20", "-x asm10"];
const QUARTET_MINIMAP_PRESETS: &[&str] = &[
    "-x asm5",
    "-x asm10",
    "-x asm20",
    "-x map-hifi",
    "-x map-ont",
];
const TGS_CORRECTIONS: &[&str] = &["none", "native_racon"];

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
enum DegapLimit {
    Text(String),
    Number(i64),
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct DegapToolParametersRequest {
    max_extension_rounds: Option<DegapLimit>,
    max_extension_bp: Option<DegapLimit>,
    kmer_filter: Option<bool>,
    kmer_size: Option<i64>,
    kmer_num: Option<i64>,
    edge: Option<i64>,
    filter_depth_hifi: Option<f64>,
    filter_depth_ont: Option<f64>,
    tel_n: Option<i64>,
    tel_r: Option<f64>,
    tel_mm: Option<i64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct LrGapcloserToolParametersRequest {
    iterations: Option<i64>,
    tag_partitions: Option<i64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct TgsGapcloserToolParametersRequest {
    hifi_correction: Option<String>,
    hifi_racon_rounds: Option<i64>,
    hifi_minimap: Option<String>,
    ont_correction: Option<String>,
    ont_racon_rounds: Option<i64>,
    ont_minimap: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct QuartetToolParametersRequest {
    minimap: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct ToolParametersRequest {
    degap: Option<DegapToolParametersRequest>,
    lrgapcloser: Option<LrGapcloserToolParametersRequest>,
    tgsgapcloser: Option<TgsGapcloserToolParametersRequest>,
    quartet: Option<QuartetToolParametersRequest>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ManualRefinementRequest {
    loci: Vec<LocusRequest>,
    /// None inherits the verified project defaults. Some(empty) clears the field.
    hifi_reads: Option<Vec<String>>,
    ont_reads: Option<Vec<String>>,
    #[serde(default)]
    tool_parameters: Option<ToolParametersRequest>,
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

pub(crate) fn witness(row: &Value) -> Result<Value> {
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
        "ctg" if row["sourceKind"] == "refinement_patch" => {
            let sha = field(row, "refinementPatchSha256")?;
            if !is_sha(sha) {
                bail!("invalid manual patch identity");
            }
            Ok(
                json!({"segment_id":id,"kind":"ctg","patch_sha256":sha,"start":positive(row,"start")?,"end":positive(row,"end")?}),
            )
        }
        "ctg" if row["sourceKind"] == "ref_segment" => Ok(json!({"segment_id":id,"kind":"ctg",
            "reference":field(row,"referenceChrName")?, "member_start":positive(row,"memberStartBp")?,
            "member_end":positive(row,"memberEndBp")?, "start":positive(row,"start")?,"end":positive(row,"end")?})),
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
    seed_plan_with_maps(
        conn,
        workspace,
        project_id,
        w,
        &mut server_runtime::SourceMaps::default(),
    )
}

fn seed_plan_with_maps(
    conn: &Connection,
    workspace: &Path,
    project_id: i64,
    w: &Value,
    maps: &mut server_runtime::SourceMaps,
) -> Result<Value> {
    let start = positive(w, "start")?;
    let end = positive(w, "end")?;
    let (seed, members) = if let Some(id) = w["assembly_ctg_id"].as_i64() {
        let seed = DegapJobSeedSegment {
            assembly_ctg_id: id,
            start,
            end,
        };
        let members = load_seed_plan_with_maps(conn, workspace, project_id, "", &seed, maps)?;
        (seed, members)
    } else {
        let dataset = field(w, "dataset")?;
        let contig = field(w, "contig")?;
        if let Some((native, sha, len)) =
            crate::grt_package::lookup_auto_source(conn, project_id, dataset, contig)?
        {
            if start.max(end) > len {
                bail!("adopted automatic source interval exceeds its record");
            }
            let n = start.abs_diff(end) + 1;
            return Ok(
                json!({"start": if start<=end{1}else{n},"end":if start<=end{n}else{1},"members":[{
                "dataset":native,"name":contig,"length":len,"start":start.min(end),"end":start.max(end),"fasta_sha256":sha,"interval_sha256":null}]}),
            );
        }
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
        let file_hash = maps.bind(workspace, &fasta, dataset, contig, length)?;
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
    if req.tools.is_empty() {
        return Ok(vec!["degap".to_owned()]);
    }
    // Serialize in admission priority order, independent of the UI click order.
    let tools: Vec<String> = TOOLS
        .iter()
        .copied()
        .filter(|tool| req.tools.iter().any(|requested| requested == tool))
        .map(str::to_owned)
        .collect();
    if tools.len() != req.tools.len() {
        bail!(
            "unknown or duplicate refinement tool for {}",
            req.segment_id
        );
    }
    if req.kind != LocusKind::Gap && tools.as_slice() != ["degap"] {
        bail!("telomere refinement requires DEGAP TelSeeker");
    }
    Ok(tools)
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

fn validate_degap_limit(value: &DegapLimit, min: i64, max: i64, label: &str) -> Result<Value> {
    match value {
        DegapLimit::Text(text) if text == "unlimited" => Ok(json!("unlimited")),
        DegapLimit::Number(num) if (min..=max).contains(num) => Ok(json!(num)),
        _ => bail!("invalid DEGAP {label}: expected {min}..={max} or \"unlimited\""),
    }
}

fn validate_tool_parameters(params: &ToolParametersRequest) -> Result<Option<Value>> {
    let mut root = Map::new();
    if let Some(degap) = &params.degap {
        let mut out = Map::new();
        if let Some(v) = &degap.max_extension_rounds {
            out.insert(
                "max_extension_rounds".into(),
                validate_degap_limit(v, 1, 1000, "max_extension_rounds")?,
            );
        }
        if let Some(v) = &degap.max_extension_bp {
            out.insert(
                "max_extension_bp".into(),
                validate_degap_limit(v, 1000, MAX_GAP_BP, "max_extension_bp")?,
            );
        }
        if let Some(v) = degap.kmer_filter {
            out.insert("kmer_filter".into(), json!(v));
        }
        if let Some(v) = degap.kmer_size {
            if !(11..=127).contains(&v) {
                bail!("invalid DEGAP kmer_size: expected 11..=127");
            }
            out.insert("kmer_size".into(), json!(v));
        }
        if let Some(v) = degap.kmer_num {
            if !(1..=1000).contains(&v) {
                bail!("invalid DEGAP kmer_num: expected 1..=1000");
            }
            out.insert("kmer_num".into(), json!(v));
        }
        if let Some(v) = degap.edge {
            if !(50..=50_000).contains(&v) {
                bail!("invalid DEGAP edge: expected 50..=50000");
            }
            out.insert("edge".into(), json!(v));
        }
        for (key, value) in [
            ("filter_depth_hifi", degap.filter_depth_hifi),
            ("filter_depth_ont", degap.filter_depth_ont),
        ] {
            if let Some(v) = value {
                if !v.is_finite() || !(v > 0.0 && v < 1.0) {
                    bail!("invalid DEGAP {key}: expected a ratio strictly between 0 and 1");
                }
                out.insert(key.into(), json!(v));
            }
        }
        if let Some(v) = degap.tel_n {
            if !(10..=10_000).contains(&v) {
                bail!("invalid DEGAP tel_n: expected 10..=10000");
            }
            out.insert("tel_n".into(), json!(v));
        }
        if let Some(v) = degap.tel_r {
            if !v.is_finite() || !(0.01..=1.0).contains(&v) {
                bail!("invalid DEGAP tel_r: expected 0.01..=1.0");
            }
            out.insert("tel_r".into(), json!(v));
        }
        if let Some(v) = degap.tel_mm {
            if v != 0 && v != 1 {
                bail!("invalid DEGAP tel_mm: expected 0 or 1");
            }
            out.insert("tel_mm".into(), json!(v));
        }
        if !out.is_empty() {
            root.insert("degap".into(), Value::Object(out));
        }
    }
    if let Some(lr) = &params.lrgapcloser {
        let mut out = Map::new();
        if let Some(v) = lr.iterations {
            if !(1..=20).contains(&v) {
                bail!("invalid LR_Gapcloser iterations: expected 1..=20");
            }
            out.insert("iterations".into(), json!(v));
        }
        if let Some(v) = lr.tag_partitions {
            if !(1..=16).contains(&v) {
                bail!("invalid LR_Gapcloser tag_partitions: expected 1..=16");
            }
            out.insert("tag_partitions".into(), json!(v));
        }
        if !out.is_empty() {
            root.insert("lrgapcloser".into(), Value::Object(out));
        }
    }
    if let Some(tgs) = &params.tgsgapcloser {
        let mut out = Map::new();
        if let Some(v) = &tgs.hifi_correction {
            if !TGS_CORRECTIONS.contains(&v.as_str()) {
                bail!("invalid TGS-GapCloser hifi_correction");
            }
            out.insert("hifi_correction".into(), json!(v));
        }
        if let Some(v) = tgs.hifi_racon_rounds {
            if !(1..=5).contains(&v) {
                bail!("invalid TGS-GapCloser hifi_racon_rounds: expected 1..=5");
            }
            out.insert("hifi_racon_rounds".into(), json!(v));
        }
        if let Some(v) = &tgs.hifi_minimap {
            if !TGS_HIFI_MINIMAP_PRESETS.contains(&v.as_str()) {
                bail!("invalid TGS-GapCloser hifi_minimap preset");
            }
            out.insert("hifi_minimap".into(), json!(v));
        }
        if let Some(v) = &tgs.ont_correction {
            if !TGS_CORRECTIONS.contains(&v.as_str()) {
                bail!("invalid TGS-GapCloser ont_correction");
            }
            out.insert("ont_correction".into(), json!(v));
        }
        if let Some(v) = tgs.ont_racon_rounds {
            if !(1..=5).contains(&v) {
                bail!("invalid TGS-GapCloser ont_racon_rounds: expected 1..=5");
            }
            out.insert("ont_racon_rounds".into(), json!(v));
        }
        if let Some(v) = &tgs.ont_minimap {
            if !TGS_ONT_MINIMAP_PRESETS.contains(&v.as_str()) {
                bail!("invalid TGS-GapCloser ont_minimap preset");
            }
            out.insert("ont_minimap".into(), json!(v));
        }
        if !out.is_empty() {
            root.insert("tgsgapcloser".into(), Value::Object(out));
        }
    }
    if let Some(quartet) = &params.quartet {
        let mut out = Map::new();
        if let Some(v) = &quartet.minimap {
            if !QUARTET_MINIMAP_PRESETS.contains(&v.as_str()) {
                bail!("invalid quarTeT minimap preset");
            }
            out.insert("minimap".into(), json!(v));
        }
        if !out.is_empty() {
            root.insert("quartet".into(), Value::Object(out));
        }
    }
    if root.is_empty() {
        Ok(None)
    } else {
        Ok(Some(Value::Object(root)))
    }
}

fn build_manifest(
    conn: &Connection,
    workspace: &Path,
    project_id: i64,
    request: &ManualRefinementRequest,
    reads: RefinementReadInputs,
    export_id: &str,
    snapshot: Option<&snapshot::Snapshot>,
) -> Result<(Value, ManualExportSummary)> {
    validate_project_exists(conn, project_id)?;
    if request.loci.is_empty() {
        bail!("select at least one actual Gap or Tel locus");
    }
    let tool_parameters = request
        .tool_parameters
        .as_ref()
        .map(validate_tool_parameters)
        .transpose()?
        .flatten();
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
                let plan = match snapshot {
                    Some(frozen) => frozen.plan(&req.chr, &w)?,
                    None => seed_plan(conn, workspace, project_id, &w)?,
                };
                plans.insert(label.into(), plan);
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
    let mut manifest = json!({"schema":SCHEMA,"export_id":export_id,"origin_fasta_sha256":origin,"reads":reads,"loci":loci});
    if let Some(snapshot) = snapshot {
        manifest["schema"] = json!(SNAPSHOT_TASKS);
        manifest["snapshot_sha256"] = json!(snapshot.digest);
    }
    if let Some(params) = tool_parameters {
        manifest["tool_parameters"] = params;
    }
    Ok((manifest, summary))
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
    if request.loci.is_empty() {
        bail!("select at least one actual Gap or Tel locus");
    }
    let snapshot = snapshot::capture_if_supported(&tx, workspace, project_id, &request.loci)?;
    let (manifest, mut summary) = build_manifest(
        &tx,
        workspace,
        project_id,
        request,
        reads,
        &export_id,
        snapshot.as_ref(),
    )?;
    let bytes = serde_json::to_vec(&manifest)?;
    if bytes.len() > MAX_MANIFEST {
        bail!("manual refinement manifest exceeds 8 MiB");
    }
    summary.batch_sha256 = hex_sha(&bytes);
    tx.commit()?;
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let mut pending = tempfile::NamedTempFile::new_in(parent)?;
    let mut zip = ZipWriter::new(pending.as_file_mut());
    if let Some(snapshot) = &snapshot {
        snapshot.write_to(&mut zip)?;
    }
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
        "CGAT project manual refinement task manifest.\n\nRun from the matching CGAT Server workspace root:\npython .lib/tools/refine.py {}\n\nIf the recorded reads are unavailable on that Server, add --hifi and/or --ont with the corresponding read paths. The command runs the locked tools, updates 06_report/report.html and prints the batch report and return ZIP paths. On a new Server job, import 07_delivery/manual/<output>.manual-<batch>.patch.zip into this App project; older workspaces keep refinement_results.zip.\n\nDo not edit or run code from this archive.\n",
        shell_quote(&argument)
    )?;
    zip.finish()?.sync_all()?;
    drop(zip);
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
    if let Err(error) = pending.persist_noclobber(output) {
        fs::remove_file(&ledger)
            .context("failed to roll back incomplete refinement export receipt")?;
        return Err(error.error.into());
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_tool_parameters_accepts_valid_overrides_for_all_four_tools() {
        let req: ToolParametersRequest = serde_json::from_value(json!({
            "degap": {
                "max_extension_rounds": "unlimited",
                "max_extension_bp": 800000,
                "kmer_filter": false,
                "kmer_size": 31,
                "kmer_num": 15,
                "edge": 600,
                "filter_depth_hifi": 0.3,
                "tel_n": 120,
                "tel_r": 0.7,
                "tel_mm": 1
            },
            "lrgapcloser": { "iterations": 5, "tag_partitions": 2 },
            "tgsgapcloser": {
                "hifi_correction": "native_racon",
                "hifi_racon_rounds": 2,
                "hifi_minimap": "-x map-hifi",
                "ont_correction": "none",
                "ont_minimap": "-x map-ont"
            },
            "quartet": { "minimap": "-x asm10" }
        }))
        .expect("valid tool parameters deserialize");
        let value = validate_tool_parameters(&req)
            .expect("valid tool parameters validate")
            .expect("non-empty tool parameters");
        assert_eq!(value["degap"]["max_extension_rounds"], "unlimited");
        assert_eq!(value["degap"]["kmer_filter"], false);
        assert_eq!(value["lrgapcloser"]["iterations"], 5);
        assert_eq!(value["tgsgapcloser"]["hifi_minimap"], "-x map-hifi");
        assert_eq!(value["quartet"]["minimap"], "-x asm10");
    }

    #[test]
    fn validate_tool_parameters_omits_empty_and_rejects_unsafe_values() {
        let empty: ToolParametersRequest =
            serde_json::from_value(json!({})).expect("empty deserializes");
        assert!(validate_tool_parameters(&empty).unwrap().is_none());

        let bad_preset: ToolParametersRequest =
            serde_json::from_value(json!({ "quartet": { "minimap": "-x asm5; rm -rf /" } }))
                .expect("deserializes");
        assert!(validate_tool_parameters(&bad_preset).is_err());

        let bad_iter: ToolParametersRequest =
            serde_json::from_value(json!({ "lrgapcloser": { "iterations": 0 } }))
                .expect("deserializes");
        assert!(validate_tool_parameters(&bad_iter).is_err());

        let bad_limit: ToolParametersRequest =
            serde_json::from_value(json!({ "degap": { "max_extension_rounds": "forever" } }))
                .expect("deserializes");
        assert!(validate_tool_parameters(&bad_limit).is_err());
    }
}
