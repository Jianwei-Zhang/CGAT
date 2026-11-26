//! Schema-5 validation is read-only and precedes importer database mutation.
use super::*;
use std::io::{Read, Seek, SeekFrom};
const MANIFEST: &str = "metadata/refinement/manifest.json";
const SERVER_PATH: &str = "metadata/refinement/final_path.json";
const FINAL_FASTA: &str = "data/refinement/final.fa";
const BLOCK: u64 = 1024 * 1024;

fn fail<T>(detail: impl Into<String>) -> Result<T> {
    grt_err("INVALID_REFINEMENT", detail.into())
}
fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("refinement {key} must be a string"))
}
fn positive(value: &Value, key: &str) -> Result<u64> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .filter(|n| *n > 0)
        .ok_or_else(|| anyhow!("refinement {key} must be positive"))
}
fn inventory<C>(
    root: &Path,
    dir: &Path,
    output: &mut BTreeMap<String, String>,
    cancel: &mut C,
) -> Result<()>
where
    C: FnMut() -> bool,
{
    for item in fs::read_dir(dir)? {
        if cancel() {
            bail!("import cancelled");
        }
        let item = item?;
        let kind = item.file_type()?;
        if kind.is_symlink() || (!kind.is_dir() && !kind.is_file()) {
            return fail("refined delivery contains a link/non-regular entry");
        }
        let path = item.path();
        if kind.is_dir() {
            inventory(root, &path, output, cancel)?;
        } else {
            let relative = path
                .strip_prefix(root)?
                .to_string_lossy()
                .replace('\\', "/");
            // The importer owns this live progress stream before validating
            // an extracted archive. It is not an archive payload or source.
            // All other unknown files (including databases/user edits) fail the
            // exact inventory comparison below; no sequence/evidence is exempt.
            if relative != MANIFEST && relative != "cache/import.log" {
                output.insert(relative, sha256_file_with_cancel(&path, cancel)?);
            }
        }
    }
    Ok(())
}
#[derive(Clone, Copy)]
struct IndexedRow {
    length: u64,
    offset: u64,
    bases: u64,
    width: u64,
}
struct Sources {
    rows: HashMap<(String, String), IndexedRow>,
    paths: HashMap<(String, String), PathBuf>,
}
impl Sources {
    fn load(root: &Path, tables: &HashMap<&'static str, TsvTable>) -> Result<Self> {
        let mut rows = HashMap::new();
        for dataset in &table(tables, "metadata/datasets.tsv")?.rows {
            let name = field(dataset, "dataset_name")?;
            let path =
                required_bundle_file(root, field(dataset, "fai_relpath")?, "refined source index")?;
            for line in fs::read_to_string(path)?.lines() {
                let fields = line.split('\t').collect::<Vec<_>>();
                if fields.len() < 5 {
                    return fail("refined source FAI lacks byte coordinates");
                }
                let row = IndexedRow {
                    length: fields[1].parse()?,
                    offset: fields[2].parse()?,
                    bases: fields[3].parse()?,
                    width: fields[4].parse()?,
                };
                if row.length == 0
                    || row.bases == 0
                    || row.width < row.bases
                    || row.width - row.bases > 2
                    || rows
                        .insert((name.to_string(), fields[0].to_string()), row)
                        .is_some()
                {
                    return fail("refined source FAI has duplicate/invalid coordinates");
                }
            }
        }
        let mut paths = HashMap::new();
        let mut local_indexes: HashMap<String, HashMap<String, IndexedRow>> = HashMap::new();
        for row in &table(tables, "metadata/source_seq_locator.tsv")?.rows {
            let key = (
                field(row, "dataset_name")?.to_string(),
                field(row, "seq_name")?.to_string(),
            );
            let relative = field(row, "fasta_relpath")?;
            validate_relpath(relative, "refined source FASTA")?;
            if !local_indexes.contains_key(relative) {
                let index_path = required_bundle_file(
                    root,
                    &format!("{relative}.fai"),
                    "source-local refinement FAI",
                )?;
                let mut records = HashMap::new();
                for line in fs::read_to_string(index_path)?.lines() {
                    let columns = line.split('\t').collect::<Vec<_>>();
                    if columns.len() < 5 {
                        return fail("source-local FAI lacks byte coordinates");
                    }
                    let record = IndexedRow {
                        length: columns[1].parse()?,
                        offset: columns[2].parse()?,
                        bases: columns[3].parse()?,
                        width: columns[4].parse()?,
                    };
                    if record.length == 0
                        || record.bases == 0
                        || record.width < record.bases
                        || record.width - record.bases > 2
                        || records.insert(columns[0].to_string(), record).is_some()
                    {
                        return fail("source-local FAI is invalid or duplicated");
                    }
                }
                local_indexes.insert(relative.to_string(), records);
            }
            let local = local_indexes[relative]
                .get(&key.1)
                .ok_or_else(|| anyhow!("source-local FAI lacks contig"))?;
            if rows
                .get(&key)
                .is_none_or(|catalog| catalog.length != local.length)
            {
                return fail("local source index disagrees with the dataset length catalog");
            }
            rows.insert(key.clone(), *local);
            if !rows.contains_key(&key) || paths.insert(key, root.join(relative)).is_some() {
                return fail("refined source locator is duplicate/unknown");
            }
        }
        Ok(Self { rows, paths })
    }
    fn interval(&self, source: &Value, length: u64) -> Result<((String, String), u64, u64, bool)> {
        let key = (
            string(source, "dataset")?.to_string(),
            string(source, "contig")?.to_string(),
        );
        let row = self
            .rows
            .get(&key)
            .ok_or_else(|| anyhow!("unknown refined source {}:{}", key.0, key.1))?;
        if !self.paths.contains_key(&key) {
            return fail("refined source has no locator");
        }
        let (start, end) = (positive(source, "start")?, positive(source, "end")?);
        let orient = string(source, "orientation")?;
        if !matches!(orient, "+" | "-")
            || end < start
            || end > row.length
            || end - start + 1 != length
        {
            return fail("refined source interval/strand differs from its segment");
        }
        Ok((key, start - 1, end, orient == "-"))
    }
    fn fetch(&self, key: &(String, String), start: u64, end: u64) -> Result<Vec<u8>> {
        let row = self
            .rows
            .get(key)
            .ok_or_else(|| anyhow!("unknown indexed refined source"))?;
        if start >= end || end > row.length || end - start > BLOCK {
            return fail("invalid refined source range");
        }
        let position = |v: u64| -> Result<u64> {
            row.offset
                .checked_add(
                    (v / row.bases)
                        .checked_mul(row.width)
                        .ok_or_else(|| anyhow!("FAI overflow"))?,
                )
                .and_then(|n| n.checked_add(v % row.bases))
                .ok_or_else(|| anyhow!("FAI overflow"))
        };
        let first = position(start)?;
        let last = position(end - 1)?
            .checked_add(1)
            .ok_or_else(|| anyhow!("FAI overflow"))?;
        let length = usize::try_from(last - first)?;
        if length > usize::try_from(BLOCK * 3)? {
            return fail("refined FAI stride is unbounded");
        }
        let mut file = fs::File::open(&self.paths[key]).with_context(|| {
            format!(
                "refinement source unavailable: {}",
                self.paths[key].display()
            )
        })?;
        file.seek(SeekFrom::Start(first))?;
        let mut data = vec![0; length];
        file.read_exact(&mut data)?;
        data.retain(|b| !matches!(*b, b'\n' | b'\r'));
        data.make_ascii_uppercase();
        if data.len() as u64 != end - start || data.iter().any(|b| !b"ACGTRYSWKMBDHVN".contains(b))
        {
            return fail("refined source FASTA/index mismatch");
        }
        Ok(data)
    }
}
fn project_server(server: &Value) -> Result<Value> {
    let mut expected = server.clone();
    let object = expected
        .as_object_mut()
        .ok_or_else(|| anyhow!("invalid refined Server path"))?;
    object.insert("workflow".into(), Value::from(GRT_APP_WORKFLOW));
    object.insert(
        "schema_version".into(),
        Value::from(GRT_REFINED_FINAL_PATH_SCHEMA_VERSION),
    );
    object.insert("q4_relpath".into(), Value::from(FINAL_FASTA));
    for chr in object
        .get_mut("chromosomes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| anyhow!("refined path lacks chromosomes"))?
    {
        let chr = chr
            .as_object_mut()
            .ok_or_else(|| anyhow!("invalid refined chromosome"))?;
        let length = chr
            .remove("length")
            .ok_or_else(|| anyhow!("missing refined length"))?;
        let sha = chr
            .remove("sha256")
            .ok_or_else(|| anyhow!("missing refined sequence identity"))?;
        chr.insert("q4_length".into(), length);
        chr.insert("q4_sha256".into(), sha);
        for segment in chr
            .get_mut("segments")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| anyhow!("refined chromosome lacks path"))?
        {
            let segment = segment
                .as_object_mut()
                .ok_or_else(|| anyhow!("invalid refined segment"))?;
            for key in [
                "evidence_ids",
                "evidenceIds",
                "eventId",
                "source_card_key",
                "sourceCardKey",
            ] {
                segment.remove(key);
            }
        }
    }
    Ok(expected)
}

pub(super) fn validate_refined_delivery<C>(
    root: &Path,
    tables: &HashMap<&'static str, TsvTable>,
    projected: &Value,
    full: bool,
    cancel: &mut C,
) -> Result<(RefinementReadInputs, Option<AutoRefinementEffect>)>
where
    C: FnMut() -> bool,
{
    let manifest = read_json(root, MANIFEST)?;
    if manifest["schema"] != "cgat.refinement-app-delivery"
        || manifest["schema_version"] != 1
        || manifest["package_version"] != GRT_REFINEMENT_SCHEMA_VERSION
        || manifest["final_path_version"] != GRT_REFINED_FINAL_PATH_SCHEMA_VERSION
        || manifest["package_mode"] != (if full { "full" } else { "light" })
    {
        return fail("unsupported refined manifest/full-light mode");
    }
    if !matches!(
        string(&manifest, "tool")?,
        "degap" | "tgsgapcloser" | "quartet" | "lrgapcloser"
    ) {
        return fail("unknown refinement engine");
    }
    let run_id = string(&manifest, "run_id")?;
    if run_id.len() != 32
        || !run_id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return fail("invalid refinement run identity");
    }
    let mut observed = BTreeMap::new();
    inventory(root, root, &mut observed, cancel)?;
    let expected: BTreeMap<String, String> = serde_json::from_value(manifest["files"].clone())?;
    if expected != observed {
        return fail("refined delivery inventory/hash mismatch");
    }
    if !full
        && observed.keys().any(|p| {
            matches!(
                Path::new(p).extension().and_then(|s| s.to_str()),
                Some("fa" | "fasta" | "fna" | "fq" | "fastq")
            )
        })
    {
        return fail("light refined delivery includes sequence files");
    }
    let (server, provenance) = validated_outcome_evidence(root, &manifest, projected)?;
    let measured = super::refined_source_evidence::validate(
        root, tables, &manifest, &server, &observed, cancel,
    )?;
    let mut placements = HashSet::new();
    for row in manifest["patch_placements"]
        .as_array()
        .ok_or_else(|| anyhow!("missing refinement placement provenance"))?
    {
        if row["homology_evidence"] != false
            || !placements.insert(string(row, "source_card_key")?.to_string())
        {
            return fail("invalid/duplicate refinement context placement");
        }
    }
    for card in &table(tables, "metadata/grt_used_contigs.tsv")?.rows {
        if field(card, "placement_mode")? != "refinement" {
            continue;
        }
        let key = field(card, "source_card_key")?;
        if !placements.remove(key) {
            return fail("refinement card lacks context provenance");
        }
        if !manifest["source_evidence"].is_null() {
            let measurement = measured
                .get(key)
                .ok_or_else(|| anyhow!("refinement card lacks its measured-source proof"))?;
            let context = manifest["patch_placements"]
                .as_array()
                .and_then(|rows| rows.iter().find(|row| row["source_card_key"] == key))
                .ok_or_else(|| anyhow!("missing measured refinement context"))?;
            if field(card, "ref_alignment_status")? != string(measurement, "ref_alignment_status")?
                || context["reference_measurement"] != *measurement
                || context["annotations"] != measurement["annotations"]
            {
                return fail("refinement context does not bind its independent source measurement");
            }
        }
    }
    if !placements.is_empty() {
        return fail("dangling refinement placement provenance");
    }
    let sources = Sources::load(root, tables)?;
    let mut segments = HashSet::new();
    for chr in server["chromosomes"]
        .as_array()
        .ok_or_else(|| anyhow!("invalid refined chromosomes"))?
    {
        let mut hash = Sha256::new();
        let mut cursor = 0_u64;
        for segment in chr["segments"]
            .as_array()
            .ok_or_else(|| anyhow!("invalid refined segments"))?
        {
            if cancel() {
                bail!("import cancelled");
            }
            let id = string(segment, "segment_id")?;
            let length = positive(segment, "length")?;
            if !segments.insert(id.to_string()) || segment["output_start"].as_u64() != Some(cursor)
            {
                return fail("refined segment duplicate/discontinuous placement");
            }
            let gap = string(segment, "kind")? == "gap";
            let source = segment.get(if gap { "refinement_source" } else { "source" });
            if let Some(source) = source {
                let (key, start, end, reverse) = sources.interval(source, length)?;
                if segment
                    .get("orientation")
                    .and_then(Value::as_str)
                    .is_some_and(|v| Some(v) != source["orientation"].as_str())
                {
                    return fail("refined strand mismatch");
                }
                if full {
                    let mut offset = 0;
                    while offset < length {
                        if cancel() {
                            bail!("import cancelled");
                        }
                        let size = BLOCK.min(length - offset);
                        let (a, b) = if reverse {
                            (end - offset - size, end - offset)
                        } else {
                            (start + offset, start + offset + size)
                        };
                        let data = sources.fetch(&key, a, b)?;
                        if gap && data.iter().any(|b| *b != b'N') {
                            return fail("refinement gap origin contains non-N sequence");
                        }
                        if reverse {
                            hash.update(reverse_complement(std::str::from_utf8(&data)?).as_bytes());
                        } else {
                            hash.update(data);
                        }
                        offset += size;
                    }
                }
            } else if !gap {
                return fail("refined non-gap segment lacks source");
            } else if full {
                let ns = vec![b'N'; BLOCK.min(length) as usize];
                let mut remaining = length;
                while remaining > 0 {
                    if cancel() {
                        bail!("import cancelled");
                    }
                    let size = remaining.min(BLOCK) as usize;
                    hash.update(&ns[..size]);
                    remaining -= size as u64;
                }
            }
            cursor = cursor
                .checked_add(length)
                .ok_or_else(|| anyhow!("refined sequence length overflow"))?;
            if segment["output_end"].as_u64() != Some(cursor) {
                return fail("refined segment end mismatch");
            }
        }
        if cursor != positive(chr, "length")?
            || (full && format!("{:x}", hash.finalize()) != string(chr, "sha256")?)
        {
            return fail("source reconstruction differs from admitted refined chromosome");
        }
    }
    if full {
        validate_artifact(
            root,
            FINAL_FASTA,
            string(&provenance["artifacts"], "assembly.fa")?,
            "accepted refined FASTA",
        )?;
    }
    let effect = validated_effect(&provenance, &server)?;
    Ok((
        RefinementReadInputs::from_recipe(&provenance["execution"]["recipe"]),
        effect,
    ))
}

// Read only the small, sealed outcome artifacts, never the full workspace inventory
// or FASTA. The persisted import projection binds them to this workspace even after
// manual edits; a same-tool result from another run is not an acceptable substitute.
fn validated_outcome_evidence(
    root: &Path,
    manifest: &Value,
    projected: &Value,
) -> Result<(Value, Value)> {
    validate_artifact(
        root,
        SERVER_PATH,
        string(manifest, "server_final_path_sha256")?,
        "authoritative refined path",
    )?;
    let server = read_json(root, SERVER_PATH)?;
    if server["schema"] != "cgat.refined-final-path"
        || server["schema_version"] != 1
        || server["tool"] != manifest["tool"]
        || server["baseline"] != manifest["baseline"]
    {
        return fail("refined Server path/delivery identity mismatch");
    }
    let mut actual = projected.clone();
    for chr in actual["chromosomes"]
        .as_array_mut()
        .ok_or_else(|| anyhow!("invalid projected chromosomes"))?
    {
        chr.as_object_mut()
            .ok_or_else(|| anyhow!("invalid projected chromosome"))?
            .remove("display_evidence");
    }
    if project_server(&server)? != actual {
        return fail("App Final Path is not the accepted Server refinement projection");
    }
    validate_artifact(
        root,
        "metadata/refinement/provenance.json",
        string(manifest, "provenance_sha256")?,
        "refinement provenance",
    )?;
    let provenance = read_json(root, "metadata/refinement/provenance.json")?;
    if provenance["tool"] != manifest["tool"]
        || provenance["run_id"] != manifest["run_id"]
        || provenance["execution"]["status"] != "success"
        || provenance["artifacts"]["final_path.json"] != manifest["server_final_path_sha256"]
    {
        return fail("delivery provenance is not successful admitted refinement");
    }
    Ok((server, provenance))
}

pub(super) fn recover_legacy_effect(
    root: &Path,
    projected: &Value,
) -> Result<Option<AutoRefinementEffect>> {
    let manifest = read_json(root, MANIFEST)?;
    if manifest["schema"] != "cgat.refinement-app-delivery"
        || manifest["schema_version"] != 1
        || manifest["package_version"] != GRT_REFINEMENT_SCHEMA_VERSION
        || manifest["final_path_version"] != GRT_REFINED_FINAL_PATH_SCHEMA_VERSION
    {
        return fail("unsupported legacy refinement manifest");
    }
    let (server, proof) = validated_outcome_evidence(root, &manifest, projected)?;
    validated_effect(&proof, &server)
}

fn validated_effect(proof: &Value, path: &Value) -> Result<Option<AutoRefinementEffect>> {
    // A pre-summary delivery remains usable; do not invent zeroes for it.
    if proof.get("gap_outcomes").is_none() && proof.get("counts").is_none() {
        return Ok(None);
    }
    let original = path["original_gaps"]
        .as_array()
        .context("missing original gaps for refinement outcome")?;
    let mut pending: HashSet<&str> = original
        .iter()
        .map(|r| string(r, "gap_id"))
        .collect::<Result<_>>()?;
    if pending.len() != original.len() {
        return fail("duplicate original gap in outcome summary");
    }
    let kinds = ["closed", "partial", "unfilled", "rejected"];
    let mut n = [0usize; 4];
    for row in proof["gap_outcomes"]
        .as_array()
        .context("missing per-gap outcome evidence")?
    {
        if !pending.remove(string(row, "gap_id")?) {
            return fail("unknown or repeated gap outcome");
        }
        let status = string(row, "status")?;
        let index = kinds
            .iter()
            .position(|kind| *kind == status)
            .context("unknown gap outcome")?;
        n[index] += 1;
    }
    let edits = path["edits"]
        .as_array()
        .context("missing automatic edits")?
        .len();
    if !pending.is_empty()
        || proof["accepted_edit_count"].as_u64() != Some(edits as u64)
        || proof["original_gap_count"].as_u64() != Some(original.len() as u64)
        || kinds
            .iter()
            .zip(n)
            .any(|(k, count)| proof["counts"][*k].as_u64() != Some(count as u64))
    {
        return fail("refinement outcome totals disagree with the original gaps or accepted edits");
    }
    Ok(Some(AutoRefinementEffect {
        version_id: None,
        project_adopted_gaps: None,
        chromosomes: Vec::new(),
        tool: string(proof, "tool")?.into(),
        run_id: string(proof, "run_id")?.into(),
        original_gaps: original.len(),
        accepted_edits: edits,
        closed: n[0],
        partial: n[1],
        unfilled: n[2],
        rejected: n[3],
    }))
}

#[cfg(test)]
mod effect_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn gap_results_require_distinct_originals_and_matching_totals() {
        let path = json!({"original_gaps":[{"gap_id":"A"},{"gap_id":"B"}],"edits":[]});
        let mut proof = json!({"tool":"degap","run_id":"run","accepted_edit_count":0,"original_gap_count":2,
            "gap_outcomes":[{"gap_id":"A","status":"unfilled"},{"gap_id":"B","status":"rejected"}],
            "counts":{"closed":0,"partial":0,"unfilled":1,"rejected":1}});
        let effect = validated_effect(&proof, &path).unwrap().unwrap();
        assert_eq!(
            (effect.accepted_edits, effect.rejected, effect.unfilled),
            (0, 1, 1)
        );
        proof["counts"]["closed"] = json!(1);
        assert!(validated_effect(&proof, &path).is_err());
        proof["counts"]["closed"] = json!(0);
        proof["gap_outcomes"][1]["gap_id"] = json!("A");
        assert!(validated_effect(&proof, &path).is_err());
        assert_eq!(validated_effect(&json!({}), &path).unwrap(), None);
    }
}
