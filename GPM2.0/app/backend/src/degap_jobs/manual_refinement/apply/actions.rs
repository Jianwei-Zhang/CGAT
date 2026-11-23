//! Explicit history actions, scoped to the segment and witnesses that were adopted.
use super::super::results::{check_patch_binding, registered_export};
use super::*;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ManualRefinementAction {
    pub action: &'static str,
    pub chr: String,
    pub locus_id: String,
    pub adoption_revision: u64,
    pub active_result_sha256: Option<String>,
    pub active_tool: Option<String>,
}

pub(super) fn annotate_adoption(row: &mut Value, adoption: &Adoption) -> Result<()> {
    row["adoptionState"] = json!(if adoption.undone { "undone" } else { "active" });
    row["adoptionRevision"] = json!(adoption.revision);
    row["activeResultSha256"] = json!((!adoption.undone).then_some(&adoption.result));
    row["activeTool"] = json!(if adoption.undone {
        None
    } else {
        Some(field(&adoption.row, "tool")?)
    });
    row["activePatchLengthBp"] = json!(if adoption.undone {
        None
    } else {
        Some(
            adoption.row["patch"]["length"]
                .as_u64()
                .context("active adoption has an invalid patch length")?,
        )
    });
    let locate_id = match (adoption.undone, adoption.replacement.as_ref()) {
        (true, _) => field(&adoption.locus, "target")?,
        (false, Some(replacement)) => segment_id(replacement)?,
        (false, None) => field(&adoption.locus["witnesses"]["seqleft"], "segment_id")?,
    };
    row["locateSegmentId"] = json!(locate_id);
    Ok(())
}

fn locate_unique(rows: &[Value], id: &str) -> Result<usize> {
    let mut hits = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| segment_id(row).ok() == Some(id));
    hits.next()
        .filter(|_| hits.next().is_none())
        .map(|(index, _)| index)
        .with_context(|| format!("Final Path segment {id} is absent or ambiguous"))
}

fn patch_payload_intact(conn: &Connection, project_id: i64, patch: &ResultPatch) -> Result<()> {
    if patch.length == 0 {
        if patch.sha256 != hex_sha(b"") {
            bail!("stored zero-base refinement patch has an invalid digest");
        }
        return Ok(());
    }
    let payload: Vec<u8> = conn
        .query_row(
            "SELECT sequence FROM project_refinement_patch WHERE project_id=?1 AND sha256=?2",
            params![project_id, patch.sha256],
            |row| row.get(0),
        )
        .context("verified patch is missing from the selected project")?;
    if payload.len() as u64 != patch.length || hex_sha(&payload) != patch.sha256 {
        bail!("stored refinement sequence does not match its verified digest and length");
    }
    Ok(())
}

fn check_endpoint_digest(patch: &ResultPatch, endpoint: Option<String>) -> Result<()> {
    if patch.operation != PatchOperation::ReplaceGap
        && endpoint.as_deref() != Some(patch.original_sha256.as_str())
    {
        bail!("current oriented endpoint sequence does not match the verified result");
    }
    Ok(())
}

/// Reverse only this adoption in a private chromosome copy. The caller commits
/// only after both the restored witnesses and any replacement candidate verify.
fn restore_original(
    conn: &Connection,
    workspace: &Path,
    project_id: i64,
    entry: &mut Value,
    adoption: &Adoption,
) -> Result<()> {
    let row: ResultRow = serde_json::from_value(adoption.row.clone())?;
    let patch = row
        .patch
        .context("invalid stored adoption: missing patch")?;
    let rows = entry["segments"]
        .as_array_mut()
        .context("no current Final Path segments")?;
    if let Some(replacement) = &adoption.replacement {
        let index = locate_unique(rows, segment_id(replacement)?)?;
        let actual = &rows[index];
        if actual["type"] != "ctg"
            || actual["sourceKind"] != "refinement_patch"
            || actual["refinementPatchSha256"] != patch.sha256
            || actual["start"] != 1
            || actual["end"].as_u64() != Some(patch.length)
        {
            bail!("the adopted Final Path patch has been edited");
        }
        patch_payload_intact(conn, project_id, &patch)?;
        match patch.operation {
            PatchOperation::ReplaceGap => rows[index] = adoption.original.clone(),
            PatchOperation::PrependTel if index == 0 => {
                rows.remove(index);
            }
            PatchOperation::AppendTel if index + 1 == rows.len() => {
                rows.remove(index);
            }
            _ => bail!("the adopted telomere extension is no longer at its original end"),
        }
    } else {
        if patch.operation != PatchOperation::ReplaceGap || patch.length != 0 {
            bail!("invalid stored zero-base adoption");
        }
        patch_payload_intact(conn, project_id, &patch)?;
        let witnesses = &adoption.locus["witnesses"];
        let left = locate_unique(rows, field(&witnesses["seqleft"], "segment_id")?)?;
        let right = locate_unique(rows, field(&witnesses["seqright"], "segment_id")?)?;
        if left + 1 != right {
            bail!("the adopted zero-base Gap no longer has adjacent flanks");
        }
        rows.insert(right, adoption.original.clone());
    }
    let (_, digest) = check_current_locus(conn, workspace, project_id, entry, &adoption.locus)
        .context("the adopted locus or its required boundaries have changed")?;
    check_endpoint_digest(&patch, digest)
}

fn candidate(
    conn: &Connection,
    workspace: &Path,
    project_id: i64,
    locus_id: &str,
    result: &str,
    tool: &str,
    origin: &str,
) -> Result<(String, Value, ResultRow)> {
    if !is_sha(result) || !TOOLS.contains(&tool) {
        bail!("invalid refinement candidate identity");
    }
    let (batch, raw): (String, String) = conn.query_row(
        "SELECT batch_sha256,report_json FROM project_refinement_import WHERE project_id=?1 AND result_sha256=?2",
        params![project_id, result], |row| Ok((row.get(0)?, row.get(1)?)),
    ).context("candidate is not registered in the selected project")?;
    let report: ManualRefinementImport = serde_json::from_str(&raw)?;
    if report.result_sha256 != result || report.batch_sha256 != batch {
        bail!("invalid stored refinement candidate identity");
    }
    let export = registered_export(workspace, project_id, &batch)?;
    if export["origin_fasta_sha256"] != origin {
        bail!("candidate does not match the current Server FASTA of origin");
    }
    let locus = export["loci"]
        .as_array()
        .context("invalid registered refinement loci")?
        .iter()
        .find(|locus| locus["id"] == locus_id)
        .context("candidate export does not contain this locus")?
        .clone();
    if !locus["tools"]
        .as_array()
        .is_some_and(|tools| tools.iter().any(|entry| entry == tool))
    {
        bail!("candidate tool was not registered for this locus");
    }
    let candidate = report
        .loci
        .iter()
        .find(|row| row["locusId"] == locus_id)
        .and_then(|row| row["candidates"].as_array())
        .and_then(|rows| {
            rows.iter()
                .find(|row| row["locus_id"] == locus_id && row["tool"] == tool)
        })
        .context("candidate was not validated for this locus")?;
    let row: ResultRow = serde_json::from_value(candidate.clone())?;
    if !matches!(row.status, ResultStatus::Closed | ResultStatus::Extended) {
        bail!("only closed Gap or verified telomere extension candidates can be adopted");
    }
    check_patch_binding(&row, &locus, &mut HashMap::new())?;
    Ok((batch, locus, row))
}

fn change_adoption(
    workspace: &Path,
    project_id: i64,
    locus_id: &str,
    expected_revision: u64,
    selection: Option<(&str, &str)>,
) -> Result<ManualRefinementAction> {
    let db = workspace.join("project.sqlite");
    if !db.is_file() || !is_sha(locus_id) {
        bail!("refinement action requires an existing project and valid locus");
    }
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    validate_project_exists(&tx, project_id)?;
    let previous = prior_adoption(&tx, project_id, locus_id)?
        .context("locus has no adoption in this project")?;
    if previous.revision != expected_revision {
        bail!("refinement adoption changed; reload the project's refinement history");
    }
    if previous.undone && selection.is_none() {
        bail!("this refinement has already been undone");
    }
    if !previous.undone
        && selection
            .is_some_and(|(result, tool)| previous.result == result && previous.row["tool"] == tool)
    {
        bail!("this refinement candidate is already active");
    }
    let origin: String = tx.query_row(
        "SELECT q4_artifact_sha256 FROM grt_package WHERE id=1",
        [],
        |row| row.get(0),
    )?;
    let previous_export = registered_export(workspace, project_id, &previous.batch)?;
    if previous_export["origin_fasta_sha256"] != origin
        || !previous_export["loci"].as_array().is_some_and(|loci| {
            loci.iter()
                .any(|row| row == &previous.locus && row["id"] == locus_id)
        })
    {
        bail!("previous adoption no longer matches its original project export receipt");
    }
    let chr = field(&previous.locus, "chr")?.to_owned();
    let mut paths = load_project_paths(&tx, project_id)?;
    let entry = paths
        .get_mut(&chr)
        .context("persisted Final Path for the adopted locus is absent")?;
    if !previous.undone {
        restore_original(&tx, workspace, project_id, entry, &previous)?;
    }
    let revision = previous
        .revision
        .checked_add(1)
        .context("refinement adoption revision overflow")?;
    let (action, current) = if let Some((result, tool)) = selection {
        let (batch, locus, row) =
            candidate(&tx, workspace, project_id, locus_id, result, tool, &origin)?;
        let (index, digest) = check_current_locus(&tx, workspace, project_id, entry, &locus)
            .context("candidate no longer matches the selected locus or its boundaries")?;
        let patch = row
            .patch
            .as_ref()
            .context("candidate is missing its verified patch")?;
        check_endpoint_digest(patch, digest)?;
        patch_payload_intact(&tx, project_id, patch)?;
        let next = Adoption {
            replacement: applied_segment(&locus, &batch, result, &row)?,
            locus,
            batch,
            result: result.to_owned(),
            row: serde_json::to_value(&row)?,
            original: entry["segments"][index].clone(),
            undone: false,
            revision,
        };
        apply_planned(entry, index, &next, patch.operation)?;
        ("switch", next)
    } else {
        let mut next = previous.clone();
        next.undone = true;
        next.revision = revision;
        ("undo", next)
    };
    update_length(entry)?;
    write_project_paths(&tx, project_id, &paths)?;
    let after = serde_json::to_string(&current)?;
    tx.execute(
        "UPDATE project_refinement_adoption SET state_json=?3 WHERE project_id=?1 AND locus_id=?2",
        params![project_id, locus_id, after],
    )?;
    tx.execute("INSERT INTO project_refinement_action(project_id,locus_id,revision,action,previous_json,current_json) VALUES (?1,?2,?3,?4,?5,?6)",
               params![project_id,locus_id,revision,action,serde_json::to_string(&previous)?,after])?;
    let active_tool = if current.undone {
        None
    } else {
        Some(field(&current.row, "tool")?.to_owned())
    };
    tx.commit()?;
    Ok(ManualRefinementAction {
        action,
        chr,
        locus_id: locus_id.to_owned(),
        adoption_revision: revision,
        active_result_sha256: (!current.undone).then_some(current.result),
        active_tool,
    })
}

pub fn undo_manual_refinement_locus(
    workspace: &Path,
    project_id: i64,
    locus_id: &str,
    expected_revision: u64,
) -> Result<ManualRefinementAction> {
    change_adoption(workspace, project_id, locus_id, expected_revision, None)
}

pub fn switch_manual_refinement_locus(
    workspace: &Path,
    project_id: i64,
    locus_id: &str,
    expected_revision: u64,
    result_sha256: &str,
    tool: &str,
) -> Result<ManualRefinementAction> {
    change_adoption(
        workspace,
        project_id,
        locus_id,
        expected_revision,
        Some((result_sha256, tool)),
    )
}
