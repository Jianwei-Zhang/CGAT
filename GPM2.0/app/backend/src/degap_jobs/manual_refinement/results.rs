//! Verify the return archive against the selected project's original task export.
//! Nothing is extracted to disk or applied to Final Path here.
use super::*;
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use zip::ZipArchive;

const RESULTS_SCHEMA: &str = "cgat.app-refinement-results.v1";
const RESULTS_MANIFEST: &str = "refinement_results.json";
const MAX_RECEIPT: u64 = MAX_MANIFEST as u64 + 1024;

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ResultManifest {
    schema: String,
    batch_sha256: String,
    results: Vec<ResultRow>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResultRow {
    pub locus_id: String,
    pub tool: String,
    pub status: ResultStatus,
    pub reason: Option<String>,
    pub patch: Option<ResultPatch>,
    pub version: Option<String>,
    pub revision: Option<String>,
    pub attempt_id: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResultStatus {
    Closed,
    Partial,
    Extended,
    NoCandidate,
    Rejected,
    MissingReads,
    InputUnavailable,
    Failed,
    Incomplete,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResultPatch {
    pub operation: PatchOperation,
    pub original_length: u64,
    pub original_sha256: String,
    pub path: String,
    pub length: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PatchOperation {
    ReplaceGap,
    PrependTel,
    AppendTel,
}

pub struct ValidatedRefinementResults {
    pub batch_sha256: String,
    /// The locally recorded export, never a task definition supplied by the results ZIP.
    pub export: Value,
    pub results: Vec<ResultRow>,
    zip: ZipArchive<File>,
}

impl ValidatedRefinementResults {
    /// Recheck content when reading an admitted payload for application. The open
    /// archive handle is retained, so a path replacement cannot redirect the read.
    pub fn read_patch(&mut self, row: usize) -> Result<Vec<u8>> {
        let row = self
            .results
            .get(row)
            .context("unknown refinement result row")?;
        let patch = row.patch.as_ref().context("result has no patch")?;
        let mut result = Vec::with_capacity(patch.length as usize);
        read_patch(&mut self.zip, row, patch, |block| {
            result.extend_from_slice(block)
        })?;
        Ok(result)
    }
}

fn read_bounded(mut reader: impl Read, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader.by_ref().take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        bail!("refinement JSON exceeds its size limit");
    }
    Ok(bytes)
}

pub(super) fn registered_export(workspace: &Path, project_id: i64, batch: &str) -> Result<Value> {
    if !is_sha(batch) {
        bail!("invalid refinement batch digest");
    }
    let ledgers = workspace.join("metadata/refinement_exports");
    let receipt = ledgers.join(format!("{batch}.json"));
    if [workspace.join("metadata"), ledgers, receipt.clone()]
        .iter()
        .any(|path| path.symlink_metadata().is_ok_and(|meta| meta.is_symlink()))
        || !receipt.is_file()
    {
        bail!("no matching refinement export receipt in this workspace");
    }
    let saved: Value = serde_json::from_slice(&read_bounded(File::open(receipt)?, MAX_RECEIPT)?)?;
    let export = &saved["manifest"];
    if saved["project_id"].as_i64() != Some(project_id)
        || saved["batch_sha256"] != batch
        || export["schema"] != SCHEMA
        || hex_sha(&serde_json::to_vec(export)?) != batch
    {
        bail!("refinement results do not match the selected project's original export receipt");
    }
    Ok(export.clone())
}

fn all_ns_digest(length: u64) -> String {
    let mut digest = Sha256::new();
    let block = [b'N'; 65_536];
    for _ in 0..length / block.len() as u64 {
        digest.update(block);
    }
    digest.update(&block[..(length % block.len() as u64) as usize]);
    format!("{:x}", digest.finalize())
}

pub(super) fn check_patch_binding(
    row: &ResultRow,
    locus: &Value,
    n_digests: &mut HashMap<u64, String>,
) -> Result<()> {
    let kind: LocusKind = serde_json::from_value(locus["kind"].clone())?;
    let expected_operation = match (kind, row.status) {
        (LocusKind::Gap, ResultStatus::Closed | ResultStatus::Partial) => {
            Some(PatchOperation::ReplaceGap)
        }
        (LocusKind::TelLeft, ResultStatus::Extended) => Some(PatchOperation::PrependTel),
        (LocusKind::TelRight, ResultStatus::Extended) => Some(PatchOperation::AppendTel),
        (_, ResultStatus::Closed | ResultStatus::Partial | ResultStatus::Extended) => {
            bail!("refinement status is not valid for its exported locus kind")
        }
        _ => None,
    };
    let patch = match (&row.patch, expected_operation) {
        (None, None) => return Ok(()),
        (Some(patch), Some(operation)) if patch.operation == operation => patch,
        _ => bail!("refinement status and patch operation do not agree"),
    };
    if patch.path != format!("patches/{}.{}.seq", row.locus_id, row.tool)
        || patch.length > MAX_GAP_BP as u64
        || patch.original_length == 0
        || !is_sha(&patch.sha256)
        || !is_sha(&patch.original_sha256)
        || [&row.version, &row.revision, &row.attempt_id]
            .into_iter()
            .any(|field| {
                !field
                    .as_ref()
                    .is_some_and(|s| !s.is_empty() && !s.chars().any(char::is_control))
            })
    {
        bail!("refinement patch is missing its archive or execution identity");
    }
    match patch.operation {
        PatchOperation::ReplaceGap => {
            let size = locus["gap_bp"]
                .as_u64()
                .filter(|size| *size > 0 && *size <= MAX_GAP_BP as u64)
                .context("invalid original Gap length in export receipt")?;
            if patch.original_length != size
                || &patch.original_sha256
                    != n_digests.entry(size).or_insert_with(|| all_ns_digest(size))
            {
                bail!("Gap patch does not bind the exported original N interval");
            }
        }
        PatchOperation::PrependTel | PatchOperation::AppendTel => {
            let endpoint = &locus["witnesses"]["endpoint"];
            let size = positive(endpoint, "start")?.abs_diff(positive(endpoint, "end")?) + 1;
            if patch.length == 0 || patch.original_length != size {
                bail!(
                    "telomere patch has no extension or does not match the exported endpoint span"
                );
            }
            // Application must also verify original_sha256 against the currently
            // resolved, oriented original endpoint sequence before inserting it.
        }
    }
    Ok(())
}

fn read_patch(
    zip: &mut ZipArchive<File>,
    row: &ResultRow,
    patch: &ResultPatch,
    mut write: impl FnMut(&[u8]),
) -> Result<()> {
    let entry = zip.by_name(&patch.path)?;
    if entry.size() != patch.length {
        bail!("refinement patch length does not match its manifest");
    }
    let mut reader = entry.take(patch.length + 1);
    let mut digest = Sha256::new();
    let mut has_n = false;
    let mut has_non_n = false;
    let mut length = 0_u64;
    let mut block = [0_u8; 65_536];
    loop {
        let n = reader.read(&mut block)?;
        if n == 0 {
            break;
        }
        let bytes = &block[..n];
        if !bytes.iter().all(|base| b"ACGTRYSWKMBDHVN".contains(base)) {
            bail!("refinement patch is not uppercase IUPAC DNA");
        }
        has_n |= bytes.contains(&b'N');
        has_non_n |= bytes.iter().any(|base| *base != b'N');
        digest.update(bytes);
        write(bytes);
        length += n as u64;
    }
    if length != patch.length || format!("{:x}", digest.finalize()) != patch.sha256 {
        bail!("refinement patch bytes do not match the declared length and digest");
    }
    if (row.status == ResultStatus::Partial && !(has_non_n && has_n))
        || (row.status != ResultStatus::Partial && has_n)
    {
        bail!("refinement status does not agree with the patch's N content");
    }
    Ok(())
}

/// Reject wrong-project deliveries, missing/extra rows, or malformed payloads
/// before any mutation. Failure outcomes for individual exported tasks are valid
/// rows, not a malformed archive. The returned export remains authoritative.
pub fn validate_manual_refinement_results(
    workspace: &Path,
    project_id: i64,
    archive: &Path,
) -> Result<ValidatedRefinementResults> {
    if !archive.is_file() {
        bail!("expected a refinement results ZIP");
    }
    let mut zip = ZipArchive::new(File::open(archive)?)?;
    let manifest: ResultManifest = {
        let entry = zip
            .by_name(RESULTS_MANIFEST)
            .context("missing refinement result manifest")?;
        if entry.size() > MAX_MANIFEST as u64 {
            bail!("refinement result manifest exceeds 8 MiB");
        }
        serde_json::from_slice(&read_bounded(entry, MAX_MANIFEST as u64)?)?
    };
    let batch = manifest.batch_sha256;
    if manifest.schema != RESULTS_SCHEMA || !is_sha(&batch) {
        bail!("invalid refinement result schema or batch identity");
    }
    let export = registered_export(workspace, project_id, &batch)?;
    let mut expected = HashMap::new();
    for locus in export["loci"]
        .as_array()
        .context("invalid refinement export loci")?
    {
        let id = field(locus, "id")?;
        if !is_sha(id) {
            bail!("invalid refinement locus identity in export receipt");
        }
        for tool in locus["tools"].as_array().context("missing export tools")? {
            let tool = tool
                .as_str()
                .filter(|t| TOOLS.contains(t))
                .context("unknown export tool")?;
            if expected.insert((id, tool), locus).is_some() {
                bail!("duplicate refinement task in export receipt");
            }
        }
    }
    if manifest.results.is_empty() || manifest.results.len() != expected.len() {
        bail!("result rows must match the complete set of exported locus and tool pairs");
    }
    let mut paths = HashSet::from([RESULTS_MANIFEST]);
    let mut n_digests = HashMap::new();
    for row in &manifest.results {
        let locus = expected
            .remove(&(row.locus_id.as_str(), row.tool.as_str()))
            .context("unexpected or duplicate locus and tool pair in refinement results")?;
        check_patch_binding(row, locus, &mut n_digests)?;
        if let Some(patch) = &row.patch {
            if !paths.insert(&patch.path) {
                bail!("duplicate refinement patch path");
            }
        }
    }
    for i in 0..zip.len() {
        let entry = zip.by_index(i)?;
        if entry.is_dir()
            || entry
                .unix_mode()
                .is_some_and(|mode| !matches!(mode & 0o170_000, 0 | 0o100_000))
            || !paths.remove(entry.name())
        {
            bail!(
                "unexpected or duplicate refinement ZIP entry: {}",
                entry.name()
            );
        }
    }
    if !paths.is_empty() || !expected.is_empty() {
        bail!("incomplete refinement result archive");
    }
    for row in &manifest.results {
        if let Some(patch) = &row.patch {
            read_patch(&mut zip, row, patch, |_| {})?;
        }
    }
    Ok(ValidatedRefinementResults {
        batch_sha256: batch,
        export,
        results: manifest.results,
        zip,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Result<(tempfile::TempDir, Value, Value)> {
        let dir = tempfile::tempdir()?;
        let locus = "a".repeat(64);
        let export = json!({
            "schema": SCHEMA,
            "loci": [{"id":locus,"kind":"gap","gap_bp":3,"tools":["degap","quartet"]}],
        });
        let batch = hex_sha(&serde_json::to_vec(&export)?);
        let ledgers = dir.path().join("metadata/refinement_exports");
        fs::create_dir_all(&ledgers)?;
        fs::write(
            ledgers.join(format!("{batch}.json")),
            serde_json::to_vec(&json!({"project_id": 7,"batch_sha256": batch,"manifest": export}))?,
        )?;
        let result = json!({
            "schema": RESULTS_SCHEMA,
            "batch_sha256": batch,
            "results": [
                {"locus_id":locus,"tool":"degap","status":"closed","version":"2.0","revision":"abc","attempt_id":"one",
                 "reason":null,"patch":{"operation":"replace_gap","original_length":3,"original_sha256":hex_sha(b"NNN"),
                   "path":format!("patches/{locus}.degap.seq"),"length":4,"sha256":hex_sha(b"ACGT")}},
                {"locus_id":locus,"tool":"quartet","status":"missing_reads","reason":"No ONT reads","patch":null},
            ],
        });
        Ok((dir, result, export))
    }

    fn pack(root: &Path, manifest: &Value, entries: &[(&str, &[u8])]) -> Result<PathBuf> {
        let path = root.join("refinement_results.zip");
        let mut zip = ZipWriter::new(File::create(&path)?);
        zip.start_file(RESULTS_MANIFEST, FileOptions::default())?;
        zip.write_all(&serde_json::to_vec(manifest)?)?;
        for (name, bytes) in entries {
            zip.start_file(*name, FileOptions::default())?;
            zip.write_all(bytes)?;
        }
        zip.finish()?;
        Ok(path)
    }

    #[test]
    fn validates_content_and_binds_the_selected_project() -> Result<()> {
        let (dir, manifest, export) = fixture()?;
        let patch = manifest["results"][0]["patch"]["path"].as_str().unwrap();
        let path = pack(dir.path(), &manifest, &[(patch, b"ACGT")])?;
        let mut checked = validate_manual_refinement_results(dir.path(), 7, &path)?;
        assert_eq!(checked.export, export);
        assert_eq!(checked.read_patch(0)?, b"ACGT");
        assert_eq!(checked.results[1].status, ResultStatus::MissingReads);
        assert!(validate_manual_refinement_results(dir.path(), 8, &path).is_err());
        let path = pack(dir.path(), &manifest, &[(patch, b"CCGT")])?;
        assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_err());
        Ok(())
    }

    #[test]
    fn rejects_duplicate_or_unrequested_tasks_and_zip_members() -> Result<()> {
        let (dir, mut manifest, _) = fixture()?;
        let patch = manifest["results"][0]["patch"]["path"]
            .as_str()
            .unwrap()
            .to_owned();
        for entries in [
            vec![(&*patch, &b"ACGT"[..]), (&*patch, &b"ACGT"[..])],
            vec![(&*patch, &b"ACGT"[..]), ("../unexpected", &b"x"[..])],
            vec![],
        ] {
            let path = pack(dir.path(), &manifest, &entries)?;
            assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_err());
        }
        manifest["results"][1]["tool"] = json!("degap");
        let path = pack(dir.path(), &manifest, &[(&patch, b"ACGT")])?;
        assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_err());
        Ok(())
    }

    #[test]
    fn rejects_gap_replacement_inconsistent_with_original_length_or_n_content() -> Result<()> {
        let (dir, mut manifest, _) = fixture()?;
        let patch = manifest["results"][0]["patch"]["path"]
            .as_str()
            .unwrap()
            .to_owned();
        manifest["results"][0]["patch"]["original_length"] = json!(4);
        let path = pack(dir.path(), &manifest, &[(&patch, b"ACGT")])?;
        assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_err());
        manifest["results"][0]["patch"]["original_length"] = json!(3);
        manifest["results"][0]["patch"]["sha256"] = json!(hex_sha(b"ACNT"));
        let path = pack(dir.path(), &manifest, &[(&patch, b"ACNT")])?;
        assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_err());
        manifest["results"][0]["status"] = json!("partial");
        let path = pack(dir.path(), &manifest, &[(&patch, b"ACNT")])?;
        assert!(validate_manual_refinement_results(dir.path(), 7, &path).is_ok());
        Ok(())
    }
}
