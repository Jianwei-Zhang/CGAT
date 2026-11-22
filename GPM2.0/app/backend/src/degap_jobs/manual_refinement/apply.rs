//! Apply only proven, project-scoped refinements. Patch sequences, receipts and
//! Final Path changes are committed together in the workspace database.
use super::*;
use crate::exporter::{load_fasta_source_interval, reverse_complement_iupac};
use rusqlite::TransactionBehavior;
use std::collections::{BTreeMap, HashMap};

mod actions;
pub use actions::{
    ManualRefinementAction, switch_manual_refinement_locus, undo_manual_refinement_locus,
};

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ManualRefinementImport {
    pub result_sha256: String,
    pub batch_sha256: String,
    pub applied: usize,
    pub duplicate: bool,
    pub changed_chromosomes: Vec<String>,
    pub loci: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Adoption {
    locus: Value,
    batch: String,
    result: String,
    row: Value,
    original: Value,
    /// None represents removal of a verified Gap with a zero-base patch.
    replacement: Option<Value>,
    #[serde(default)]
    undone: bool,
    #[serde(default = "initial_revision")]
    revision: u64,
}

fn initial_revision() -> u64 {
    1
}

fn load_project_paths(conn: &Connection, project_id: i64) -> Result<Map<String, Value>> {
    let saved: Option<String> = conn
        .query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [project_id],
            |row| row.get(0),
        )
        .optional()?;
    serde_json::from_str(saved.as_deref().unwrap_or("{}"))
        .context("invalid persisted project Final Path")
}

fn write_project_paths(
    conn: &Connection,
    project_id: i64,
    paths: &Map<String, Value>,
) -> Result<()> {
    conn.execute(
        "INSERT INTO project_assembly_view_state(project_id, final_path_by_chr_json, updated_at)
         VALUES (?1, ?2, CURRENT_TIMESTAMP) ON CONFLICT(project_id) DO UPDATE
         SET final_path_by_chr_json=excluded.final_path_by_chr_json, updated_at=excluded.updated_at",
        params![project_id, serde_json::to_string(paths)?],
    )?;
    Ok(())
}

fn canonicalize_entry(chr: &str, mut entry: Value) -> Result<Value> {
    let rows = entry
        .get_mut("segments")
        .and_then(Value::as_array_mut)
        .context("chromosome has no editable Final Path segments")?;
    for row in rows {
        if row.get("type").is_some() {
            continue;
        }
        let id = segment_id(row)?.to_owned();
        if row_kind(row) == "gap" {
            let size = positive(row, "length")?;
            row["segmentId"] = json!(id);
            row["type"] = json!("gap");
            row["gapSizeBp"] = json!(size);
        } else {
            let w = witness(row)?;
            let source_length = positive(row, "source_length")?;
            let contig = w["contig"].clone();
            row["segmentId"] = json!(id);
            row["type"] = json!("ctg");
            row["ctgName"] = contig.clone();
            row["originId"] = contig;
            row["datasetName"] = w["dataset"].clone();
            row["start"] = w["start"].clone();
            row["end"] = w["end"].clone();
            row["overallLen"] = json!(source_length);
        }
        row["serverBaseline"] = json!(true);
        let mut trace = Map::new();
        for (source, target) in [
            ("parent_segment_id", "parentSegmentId"),
            ("parent_interval", "parentInterval"),
            ("refinement_edit_id", "editId"),
            ("original_gap_ids", "originalGapIds"),
            ("refinement_source", "source"),
        ] {
            if let Some(value) = row.get(source) {
                trace.insert(target.into(), value.clone());
            }
        }
        if !trace.is_empty() && row.get("refinement").is_none() {
            row["refinement"] = Value::Object(trace);
        }
    }
    entry["mode"] = json!("segments");
    entry["chrName"] = json!(chr);
    // Any valid automatic trace stays on its own surviving source segment.
    // The new path is not itself an unchanged Server baseline.
    entry
        .as_object_mut()
        .context("invalid Final Path entry")?
        .remove("serverBaseline");
    update_length(&mut entry)?;
    Ok(entry)
}

fn update_length(entry: &mut Value) -> Result<()> {
    let mut length = 0_u64;
    for row in entry["segments"]
        .as_array()
        .context("invalid Final Path segments")?
    {
        let size = if row_kind(row) == "gap" {
            positive(row, "gapSizeBp")? as u64
        } else {
            positive(row, "start")?.abs_diff(positive(row, "end")?) + 1
        };
        length = length
            .checked_add(size)
            .context("Final Path length overflow")?;
    }
    entry["totalLength"] = json!(length);
    Ok(())
}

fn locus_req(locus: &Value) -> Result<LocusRequest> {
    Ok(LocusRequest {
        chr: field(locus, "chr")?.to_owned(),
        kind: serde_json::from_value(locus["kind"].clone())?,
        segment_id: field(locus, "target")?.to_owned(),
        tools: Vec::new(),
        motif: None,
    })
}

fn endpoint_sha(conn: &Connection, project_id: i64, plan: &Value) -> Result<String> {
    let mut hash = Sha256::new();
    let reverse = positive(plan, "start")? > positive(plan, "end")?;
    let members = plan["members"]
        .as_array()
        .context("invalid endpoint source plan")?;
    let mut indexes = (0..members.len()).collect::<Vec<_>>();
    if reverse {
        indexes.reverse();
    }
    for index in indexes {
        let member = &members[index];
        let dataset = field(member, "dataset")?;
        let name = field(member, "name")?;
        let fasta: String = conn.query_row(
            "SELECT ssl.fasta_path FROM source_seq_locator ssl
             JOIN source_seq ss ON ss.id=ssl.source_seq_id
             JOIN dataset d ON d.id=ss.dataset_id
             JOIN project_dataset pd ON pd.dataset_id=d.id
             WHERE pd.project_id=?1 AND d.name=?2 AND ss.seq_name=?3",
            params![project_id, dataset, name],
            |row| row.get(0),
        )?;
        let sequence = load_fasta_source_interval(
            Path::new(&fasta),
            name,
            positive(member, "start")?,
            positive(member, "end")?,
        )?;
        if member["interval_sha256"].as_str() != Some(hex_sha(sequence.as_bytes()).as_str()) {
            bail!("local endpoint sequence does not match the registered interval");
        }
        if reverse {
            hash.update(reverse_complement_iupac(&sequence).as_bytes());
        } else {
            hash.update(sequence.as_bytes());
        }
    }
    Ok(format!("{:x}", hash.finalize()))
}

/// Return the original target index and, for Tel, its verified current oriented digest.
fn check_current_locus(
    conn: &Connection,
    workspace: &Path,
    project: i64,
    entry: &Value,
    locus: &Value,
) -> Result<(usize, Option<String>)> {
    let req = locus_req(locus)?;
    let rows = entry["segments"]
        .as_array()
        .context("no current Final Path segments")?;
    let located = locate(rows, &req)?;
    let mut original_endpoint_sha = None;
    for (label, row) in located {
        let id = segment_id(row)?;
        if rows
            .iter()
            .filter(|other| segment_id(other).ok() == Some(id))
            .count()
            != 1
        {
            bail!("exported witness is ambiguous in the current Final Path");
        }
        let actual = witness(row)?;
        if actual != locus["witnesses"][label] {
            bail!("exported witness no longer identifies this segment");
        }
        if label != "target" {
            let plan = seed_plan(conn, workspace, project, &actual)?;
            if plan != locus["seed_plans"][label] {
                bail!("current source ranges or content differ from the export");
            }
            if label == "endpoint" {
                original_endpoint_sha = Some(endpoint_sha(conn, project, &plan)?);
            }
        }
    }
    let target = rows
        .iter()
        .position(|row| segment_id(row).ok() == Some(req.segment_id.as_str()))
        .context("exported target is absent")?;
    Ok((target, original_endpoint_sha))
}

fn applied_segment(
    locus: &Value,
    batch: &str,
    result: &str,
    row: &ResultRow,
) -> Result<Option<Value>> {
    let patch = row.patch.as_ref().context("missing verified patch")?;
    if patch.length == 0 {
        return Ok(None);
    }
    let target = field(locus, "target")?;
    Ok(Some(json!({
        "type":"ctg", "sourceKind":"refinement_patch", "refinementPatchSha256": patch.sha256,
        "segmentId":format!("refine-{}", row.locus_id), "ctgName":format!("{} · {}", target,row.tool),
        "originId":format!("refine-{}",patch.sha256), "start":1, "end":patch.length, "overallLen":patch.length,
        "refinement": {
            "mode":"manual", "tool":row.tool, "version":row.version, "revision":row.revision,
            "batchSha256":batch, "resultSha256":result, "attemptId":row.attempt_id, "locusId":row.locus_id,
            "parentSegmentId":target, "parentInterval":[0,patch.original_length],
            "originalGapIds":if patch.operation == PatchOperation::ReplaceGap { vec![target] } else { Vec::new() },
        }
    })))
}

fn store_payloads(
    conn: &Connection,
    project_id: i64,
    bundle: &mut ValidatedRefinementResults,
) -> Result<()> {
    let mut seen = HashSet::new();
    for index in 0..bundle.results.len() {
        let Some(patch) = bundle.results[index].patch.as_ref() else {
            continue;
        };
        if patch.length == 0 || !seen.insert(patch.sha256.clone()) {
            continue;
        }
        let digest = patch.sha256.clone();
        let payload = bundle.read_patch(index)?;
        conn.execute("INSERT OR IGNORE INTO project_refinement_patch(project_id,sha256,sequence) VALUES (?1,?2,?3)",
                    params![project_id,digest,payload])?;
        let intact: bool = conn.query_row(
            "SELECT sequence=?3 FROM project_refinement_patch WHERE project_id=?1 AND sha256=?2",
            params![project_id, digest, payload],
            |row| row.get(0),
        )?;
        if !intact {
            bail!("existing project refinement patch failed its content check");
        }
    }
    Ok(())
}

fn prior_adoption(conn: &Connection, project: i64, locus: &str) -> Result<Option<Adoption>> {
    let json: Option<String> = conn.query_row(
        "SELECT state_json FROM project_refinement_adoption WHERE project_id=?1 AND locus_id=?2",
        params![project,locus], |row| row.get(0),
    ).optional()?;
    json.map(|json| serde_json::from_str(&json).context("invalid project refinement adoption"))
        .transpose()
}

fn apply_planned(
    entry: &mut Value,
    index: usize,
    adoption: &Adoption,
    operation: PatchOperation,
) -> Result<()> {
    let rows = entry["segments"]
        .as_array_mut()
        .context("invalid application target")?;
    if rows.get(index) != Some(&adoption.original) {
        bail!("refinement application target changed during this transaction");
    }
    if let Some(replacement) = &adoption.replacement {
        let id = segment_id(replacement)?;
        if rows.iter().any(|row| segment_id(row).ok() == Some(id)) {
            bail!("refinement replacement identity is already present in the Final Path");
        }
    }
    match operation {
        PatchOperation::ReplaceGap => {
            rows.splice(index..=index, adoption.replacement.clone());
        }
        PatchOperation::PrependTel | PatchOperation::AppendTel => {
            let offset = usize::from(operation == PatchOperation::AppendTel);
            rows.insert(
                index + offset,
                adoption
                    .replacement
                    .clone()
                    .context("missing telomere extension")?,
            );
        }
    }
    Ok(())
}

/// Archive and project state are validated separately. Archive corruption
/// rejects the whole import; moved/edited individual loci are skipped.
pub fn import_manual_refinement_results(
    workspace: &Path,
    project_id: i64,
    archive: &Path,
) -> Result<ManualRefinementImport> {
    let mut bundle = validate_manual_refinement_results(workspace, project_id, archive)?;
    // Canonical order also makes re-zipping or reordering identical rows idempotent.
    bundle
        .results
        .sort_by(|left, right| (&left.locus_id, &left.tool).cmp(&(&right.locus_id, &right.tool)));
    let result_sha = hex_sha(&serde_json::to_vec(&(
        &bundle.batch_sha256,
        &bundle.results,
    ))?);
    let db = workspace.join("project.sqlite");
    if !db.is_file() {
        bail!("refinement import requires an existing project workspace");
    }
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    validate_project_exists(&tx, project_id)?;
    let origin: String = tx.query_row(
        "SELECT q4_artifact_sha256 FROM grt_package WHERE id=1",
        [],
        |row| row.get(0),
    )?;
    if bundle.export["origin_fasta_sha256"] != origin {
        bail!("the selected project's original Server FASTA has changed");
    }
    if let Some(report) = tx.query_row("SELECT report_json FROM project_refinement_import WHERE project_id=?1 AND result_sha256=?2",
                                       params![project_id,result_sha], |row| row.get::<_,String>(0)).optional()? {
        let mut report: ManualRefinementImport = serde_json::from_str(&report)?;
        report.duplicate = true;
        report.applied = 0;
        report.changed_chromosomes.clear();
        for row in &mut report.loci {
            if let Some(adoption) = prior_adoption(&tx, project_id, field(row, "locusId")?)? {
                actions::annotate_adoption(row, &adoption)?;
            }
        }
        tx.commit()?;
        return Ok(report);
    }
    let mut paths = load_project_paths(&tx, project_id)?;
    let mut baseline = None;
    let mut entries = BTreeMap::new();
    let mut planned: BTreeMap<String, Vec<(usize, Adoption, PatchOperation)>> = BTreeMap::new();
    let mut by_locus: HashMap<&str, Vec<&ResultRow>> = HashMap::new();
    for row in &bundle.results {
        by_locus.entry(&row.locus_id).or_default().push(row);
    }
    let mut reports = Vec::new();
    for locus in bundle.export["loci"]
        .as_array()
        .context("no registered refinement loci")?
    {
        let id = field(locus, "id")?;
        let chr = field(locus, "chr")?;
        let rows = &by_locus[id];
        let mut report = json!({"locusId":id,"chr":chr,"kind":locus["kind"],"target":locus["target"],
                                "candidates":rows,"disposition":"no_eligible_patch"});
        let prior = prior_adoption(&tx, project_id, id)?;
        if let Some(existing) = prior {
            report["disposition"] = json!(if existing.undone {
                "manually_undone"
            } else {
                "already_adopted"
            });
            actions::annotate_adoption(&mut report, &existing)?;
            reports.push(report);
            continue;
        }
        let mut candidates = rows
            .iter()
            .copied()
            .filter(|row| matches!(row.status, ResultStatus::Closed | ResultStatus::Extended))
            .collect::<Vec<_>>();
        candidates.sort_by_key(|row| {
            TOOLS
                .iter()
                .position(|tool| *tool == row.tool)
                .unwrap_or(TOOLS.len())
        });
        if candidates.is_empty() {
            reports.push(report);
            continue;
        }
        if !entries.contains_key(chr) {
            let source = if let Some(entry) = paths.get(chr) {
                Some(entry.clone())
            } else {
                if baseline.is_none() {
                    baseline = Some(load_grt_final_path_for_project_with_connection(
                        &tx, project_id,
                    )?);
                }
                baseline.as_ref().and_then(|value| value.get(chr)).cloned()
            };
            let Some(entry) = source.and_then(|entry| canonicalize_entry(chr, entry).ok()) else {
                report["disposition"] = json!("target_unavailable");
                reports.push(report);
                continue;
            };
            entries.insert(chr.to_owned(), entry);
        }
        let entry = &entries[chr];
        let Ok((index, endpoint_sha)) =
            check_current_locus(&tx, workspace, project_id, entry, locus)
        else {
            report["disposition"] = json!("target_or_boundary_changed");
            reports.push(report);
            continue;
        };
        let eligible = candidates
            .into_iter()
            .filter(|row| {
                row.patch.as_ref().is_some_and(|patch| {
                    patch.operation == PatchOperation::ReplaceGap
                        || endpoint_sha.as_deref() == Some(patch.original_sha256.as_str())
                })
            })
            .collect::<Vec<_>>();
        let Some(row) = eligible.first() else {
            report["disposition"] = json!("endpoint_digest_mismatch");
            reports.push(report);
            continue;
        };
        let patch = row
            .patch
            .as_ref()
            .context("patch candidate lost its payload")?;
        if planned.get(chr).is_some_and(|edits| {
            edits.iter().any(|(other, _, op)| {
                *other == index
                    && (*op == patch.operation
                        || *op == PatchOperation::ReplaceGap
                        || patch.operation == PatchOperation::ReplaceGap)
            })
        }) {
            report["disposition"] = json!("overlapping_edit");
            reports.push(report);
            continue;
        }
        let adoption = Adoption {
            locus: locus.clone(),
            batch: bundle.batch_sha256.clone(),
            result: result_sha.clone(),
            row: serde_json::to_value(row)?,
            original: entry["segments"][index].clone(),
            replacement: applied_segment(locus, &bundle.batch_sha256, &result_sha, row)?,
            undone: false,
            revision: initial_revision(),
        };
        report["disposition"] = json!("applied");
        report["appliedTool"] = json!(row.tool);
        actions::annotate_adoption(&mut report, &adoption)?;
        report["equivalentTools"] = json!(
            eligible
                .iter()
                .filter(|other| other.patch.as_ref().is_some_and(|p| {
                    p.operation == patch.operation
                        && p.original_sha256 == patch.original_sha256
                        && p.sha256 == patch.sha256
                }))
                .map(|other| &other.tool)
                .collect::<Vec<_>>()
        );
        planned
            .entry(chr.to_owned())
            .or_default()
            .push((index, adoption, patch.operation));
        reports.push(report);
    }
    drop(by_locus);
    store_payloads(&tx, project_id, &mut bundle)?;
    let mut result = ManualRefinementImport {
        result_sha256: result_sha,
        batch_sha256: bundle.batch_sha256,
        applied: 0,
        duplicate: false,
        changed_chromosomes: Vec::new(),
        loci: reports,
    };
    for (chr, mut edits) in planned {
        // Right-end before left-end when a one-segment chromosome has both.
        edits.sort_by_key(|(index, _, op)| {
            (std::cmp::Reverse(*index), *op == PatchOperation::PrependTel)
        });
        let mut entry = entries.remove(&chr).context("missing planned chromosome")?;
        for (index, adoption, op) in edits {
            apply_planned(&mut entry, index, &adoption, op)?;
            tx.execute("INSERT INTO project_refinement_adoption(project_id,locus_id,state_json) VALUES (?1,?2,?3)",
                       params![project_id, adoption.locus["id"].as_str(), serde_json::to_string(&adoption)?])?;
            result.applied += 1;
        }
        update_length(&mut entry)?;
        paths.insert(chr.clone(), entry);
        result.changed_chromosomes.push(chr);
    }
    if result.applied > 0 {
        write_project_paths(&tx, project_id, &paths)?;
    }
    tx.execute("INSERT INTO project_refinement_import(project_id,result_sha256,batch_sha256,report_json) VALUES (?1,?2,?3,?4)",
               params![project_id,result.result_sha256,result.batch_sha256,serde_json::to_string(&result)?])?;
    tx.commit()?;
    Ok(result)
}

pub fn list_manual_refinement_results(
    workspace: &Path,
    project_id: i64,
) -> Result<Vec<ManualRefinementImport>> {
    let db = workspace.join("project.sqlite");
    if !db.is_file() {
        bail!("refinement history requires an existing project workspace");
    }
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction()?;
    validate_project_exists(&tx, project_id)?;
    let mut statement = tx.prepare(
        "SELECT report_json FROM project_refinement_import WHERE project_id=?1 ORDER BY rowid DESC",
    )?;
    let rows = statement.query_map([project_id], |row| row.get::<_, String>(0))?;
    let mut reports = rows
        .map(|row| serde_json::from_str(&row?).context("invalid project refinement import history"))
        .collect::<Result<Vec<ManualRefinementImport>>>()?;
    let mut adoptions = HashMap::new();
    for report in &mut reports {
        for row in &mut report.loci {
            let id = field(row, "locusId")?.to_owned();
            if !adoptions.contains_key(&id) {
                adoptions.insert(id.clone(), prior_adoption(&tx, project_id, &id)?);
            }
            if let Some(adoption) = &adoptions[&id] {
                actions::annotate_adoption(row, adoption)?;
            }
        }
    }
    Ok(reports)
}
