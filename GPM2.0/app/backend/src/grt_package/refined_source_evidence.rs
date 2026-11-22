//! Optional measured-source capability; no remote path or environment probing.
use super::*;
use std::io::{BufRead, BufReader};

const PROJECTION: &str = "metadata/refinement/source_evidence.json";
type Source = (String, String);
type Record = BTreeMap<String, String>;

fn fail<T>(message: &str) -> Result<T> {
    grt_err("INVALID_REFINEMENT", message)
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .with_context(|| format!("source evidence {key} must be a string"))
}
fn number(value: &Value, key: &str) -> Result<u64> {
    value[key]
        .as_u64()
        .with_context(|| format!("source evidence {key} must be nonnegative"))
}
fn array<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>> {
    value[key]
        .as_array()
        .with_context(|| format!("source evidence {key} must be an array"))
}
fn source(value: &Value) -> Result<Source> {
    Ok((
        text(value, "dataset")?.into(),
        text(value, "contig")?.into(),
    ))
}
fn records(root: &Path, relative: &str) -> Result<Vec<Record>> {
    let path = required_bundle_file(root, relative, "source evidence TSV")?;
    let mut reader = csv::ReaderBuilder::new().delimiter(b'\t').from_path(path)?;
    let header = reader.headers()?.clone();
    if header.is_empty() || header.iter().collect::<HashSet<_>>().len() != header.len() {
        return fail("source evidence TSV has missing/duplicate columns");
    }
    reader
        .records()
        .map(|row| {
            let row = row?;
            Ok(header
                .iter()
                .zip(row.iter())
                .map(|(key, value)| (key.into(), value.into()))
                .collect())
        })
        .collect()
}
fn record_number(row: &Record, key: &str) -> Result<u64> {
    row.get(key)
        .with_context(|| format!("missing source annotation {key}"))?
        .parse()
        .with_context(|| format!("invalid source annotation {key}"))
}
fn record_text<'a>(row: &'a Record, key: &str) -> Result<&'a str> {
    row.get(key)
        .map(String::as_str)
        .with_context(|| format!("missing source annotation {key}"))
}

fn cigar_spans(cigar: &str, query: u64, target: u64) -> Result<()> {
    let (mut n, mut q, mut t, mut count) = (0_u64, 0_u64, 0_u64, 0_usize);
    for byte in cigar.bytes() {
        if byte.is_ascii_digit() {
            if n == 0 && byte == b'0' {
                return fail("measured-source CIGAR has a leading zero");
            }
            n = n
                .checked_mul(10)
                .and_then(|n| n.checked_add(u64::from(byte - b'0')))
                .context("CIGAR length overflow")?;
            continue;
        }
        if n == 0 || !b"MIDN=X".contains(&byte) {
            return fail("invalid measured-source CIGAR");
        }
        if b"MI=X".contains(&byte) {
            q = q.checked_add(n).context("query CIGAR span overflow")?;
        }
        if b"MDN=X".contains(&byte) {
            t = t.checked_add(n).context("target CIGAR span overflow")?;
        }
        n = 0;
        count += 1;
    }
    if n != 0 || count == 0 || (q, t) != (query, target) {
        return fail("measured-source CIGAR differs from PAF intervals");
    }
    Ok(())
}
fn paf_hits<C>(
    root: &Path,
    dataset: &str,
    queries: &BTreeMap<String, u64>,
    reference: &BTreeMap<String, usize>,
    cancel: &mut C,
) -> Result<HashMap<String, BTreeMap<String, u64>>>
where
    C: FnMut() -> bool,
{
    let relative = format!("runs/{dataset}_vs_ref/result.paf");
    let file = required_bundle_file(root, &relative, "measured-source PAF")?;
    let mut hits: HashMap<String, BTreeMap<String, u64>> = HashMap::new();
    for line in BufReader::new(fs::File::open(file)?).lines() {
        if cancel() {
            bail!("import cancelled");
        }
        let line = line?;
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let f: Vec<_> = line.split('\t').collect();
        if f.len() < 12 {
            return fail("measured-source PAF has too few columns");
        }
        let numeric = |index: usize| -> Result<u64> { Ok(f[index].parse()?) };
        let (ql, qs, qe, tl, ts, te) = (
            numeric(1)?,
            numeric(2)?,
            numeric(3)?,
            numeric(6)?,
            numeric(7)?,
            numeric(8)?,
        );
        let (matches, block, mapq) = (numeric(9)?, numeric(10)?, numeric(11)?);
        if queries.get(f[0]) != Some(&ql)
            || reference.get(f[5]).map(|n| *n as u64) != Some(tl)
            || qs >= qe
            || qe > ql
            || ts >= te
            || te > tl
            || !matches!(f[4], "+" | "-")
            || block == 0
            || matches > block.min(qe - qs).min(te - ts)
            || mapq > 255
        {
            return fail("measured-source PAF identity/coordinates differ from inputs");
        }
        let cigars: Vec<_> = f[12..]
            .iter()
            .filter_map(|tag| tag.strip_prefix("cg:Z:"))
            .collect();
        if cigars.len() != 1 {
            return fail("measured-source PAF requires exactly one CIGAR");
        }
        cigar_spans(cigars[0], qe - qs, te - ts)?;
        let count = hits
            .entry(f[0].into())
            .or_default()
            .entry(f[5].into())
            .or_default();
        *count = count
            .checked_add(1)
            .context("measured source hit count overflow")?;
    }
    Ok(hits)
}

#[derive(Clone)]
struct Slice {
    chromosome: String,
    id: String,
    dataset: String,
    contig: String,
    start: u64,
    end: u64,
    reverse: bool,
    output: u64,
    length: u64,
    kind: String,
}
fn slices(server: &Value, lengths: &BTreeMap<Source, u64>) -> Result<Vec<Slice>> {
    let mut output = Vec::new();
    for chromosome in array(server, "chromosomes")? {
        for segment in array(chromosome, "segments")? {
            let kind = text(segment, "kind")?;
            let Some(origin) = segment.get(if kind == "gap" {
                "refinement_source"
            } else {
                "source"
            }) else {
                continue;
            };
            let key = source(origin)?;
            let (start, end, length) = (
                number(origin, "start")?,
                number(origin, "end")?,
                number(segment, "length")?,
            );
            let orientation = text(origin, "orientation")?;
            if start == 0
                || end < start
                || end - start + 1 != length
                || lengths.get(&key).is_none_or(|n| end > *n)
                || !matches!(orientation, "+" | "-")
            {
                return fail("source annotation slice differs from accepted source");
            }
            let row = Slice {
                chromosome: text(chromosome, "chr")?.into(),
                id: text(segment, "segment_id")?.into(),
                dataset: key.0,
                contig: key.1,
                start,
                end,
                reverse: orientation == "-",
                output: number(segment, "output_start")?,
                length,
                kind: kind.into(),
            };
            row.output
                .checked_add(length)
                .context("final source interval overflow")?;
            output.push(row);
        }
    }
    Ok(output)
}
fn interval_record(row: &Slice) -> Record {
    Record::from([
        ("chromosome".into(), row.chromosome.clone()),
        ("segment_id".into(), row.id.clone()),
        ("dataset".into(), row.dataset.clone()),
        ("contig".into(), row.contig.clone()),
        ("source_start".into(), row.start.to_string()),
        ("source_end".into(), row.end.to_string()),
        (
            "source_orientation".into(),
            if row.reverse { "-" } else { "+" }.into(),
        ),
        ("final_start".into(), row.output.to_string()),
        ("final_end".into(), (row.output + row.length).to_string()),
        ("segment_kind".into(), row.kind.clone()),
    ])
}
fn annotation_records<C>(
    root: &Path,
    slices: &[Slice],
    lengths: &BTreeMap<Source, u64>,
    patches: &BTreeMap<Source, Value>,
    cancel: &mut C,
) -> Result<Vec<Record>>
where
    C: FnMut() -> bool,
{
    let mut expected = std::collections::BTreeSet::new();
    let mut by_source: HashMap<(String, String, String), Vec<&Slice>> = HashMap::new();
    for row in slices {
        by_source
            .entry((
                row.dataset.clone(),
                row.contig.clone(),
                row.chromosome.clone(),
            ))
            .or_default()
            .push(row);
    }
    for chromosome in slices
        .iter()
        .map(|row| row.chromosome.clone())
        .collect::<std::collections::BTreeSet<_>>()
    {
        let mut inputs = Vec::new();
        let tel_dir = root.join(format!("tel/chr_{chromosome}"));
        if tel_dir.is_dir() {
            for item in fs::read_dir(&tel_dir)? {
                let path = item?.path();
                if path.extension().and_then(|p| p.to_str()) == Some("tsv") {
                    inputs.push((
                        "tel",
                        path.strip_prefix(root)?
                            .to_string_lossy()
                            .replace('\\', "/"),
                    ));
                }
            }
        }
        let cen = format!("cen/chr_{chromosome}/marks.tsv");
        if root.join(&cen).is_file() {
            inputs.push(("cen", cen));
        }
        for (kind, relative) in inputs {
            for mark in records(root, &relative)? {
                if cancel() {
                    bail!("import cancelled");
                }
                let dataset = mark.get("dataset_name").map(String::as_str).unwrap_or("");
                let contig = mark
                    .get(if kind == "tel" {
                        "seq_name"
                    } else {
                        "ctg_name"
                    })
                    .map(String::as_str)
                    .unwrap_or("");
                let Some(used) =
                    by_source.get(&(dataset.into(), contig.into(), chromosome.clone()))
                else {
                    continue;
                };
                let assigned = record_text(
                    &mark,
                    if kind == "tel" {
                        "assigned_chr_name"
                    } else {
                        "chr_name"
                    },
                )?;
                let start = record_number(
                    &mark,
                    if kind == "tel" {
                        "start_bp"
                    } else {
                        "ctg_start"
                    },
                )?;
                let end = record_number(&mark, if kind == "tel" { "end_bp" } else { "ctg_end" })?;
                let strand = record_text(&mark, "strand")?;
                let key = (dataset.to_string(), contig.to_string());
                if assigned != chromosome
                    || start == 0
                    || start > end
                    || end > lengths[&key]
                    || !matches!(strand, "+" | "-")
                {
                    return fail("invalid measured source annotation coordinates/strand");
                }
                let provenance = mark
                    .get("provenance")
                    .filter(|s| !s.is_empty())
                    .map(String::as_str)
                    .unwrap_or("[]");
                let _: Value = serde_json::from_str(provenance)?;
                for row in used {
                    let (a, b) = (start.max(row.start), end.min(row.end));
                    if a > b {
                        continue;
                    }
                    let final_start = row.output
                        + if row.reverse {
                            row.end - b
                        } else {
                            a - row.start
                        };
                    let final_end = row.output
                        + if row.reverse {
                            row.end - a + 1
                        } else {
                            b - row.start + 1
                        };
                    let orientation = if row.reverse {
                        if strand == "+" { "-" } else { "+" }
                    } else {
                        strand
                    };
                    expected.insert(Record::from([
                        ("kind".into(), kind.into()),
                        (
                            "annotation_id".into(),
                            record_text(&mark, if kind == "tel" { "rule_id" } else { "cen_id" })?
                                .into(),
                        ),
                        ("dataset".into(), dataset.into()),
                        ("contig".into(), contig.into()),
                        ("source_start".into(), a.to_string()),
                        ("source_end".into(), b.to_string()),
                        ("source_strand".into(), strand.into()),
                        ("chromosome".into(), chromosome.clone()),
                        ("segment_id".into(), row.id.clone()),
                        ("final_start".into(), final_start.to_string()),
                        ("final_end".into(), final_end.to_string()),
                        ("final_strand".into(), orientation.into()),
                        (
                            "projection".into(),
                            if (a, b) == (start, end) {
                                "complete_source_mark"
                            } else {
                                "clipped_source_support_not_rescanned"
                            }
                            .into(),
                        ),
                        (
                            "origin".into(),
                            if patches.contains_key(&key) {
                                "refinement_patch"
                            } else {
                                "lgz_source"
                            }
                            .into(),
                        ),
                        ("provenance".into(), provenance.into()),
                    ]));
                }
            }
        }
    }
    Ok(expected.into_iter().collect())
}

pub(super) fn validate<C>(
    root: &Path,
    tables: &HashMap<&'static str, TsvTable>,
    manifest: &Value,
    server: &Value,
    observed: &BTreeMap<String, String>,
    cancel: &mut C,
) -> Result<HashMap<String, Value>>
where
    C: FnMut() -> bool,
{
    let cards = &table(tables, "metadata/grt_used_contigs.tsv")?.rows;
    let capability = &manifest["source_evidence"];
    if capability.is_null() {
        if cards.iter().any(|row| {
            row.get("placement_mode").map(String::as_str) == Some("refinement")
                && row.get("ref_alignment_status").map(String::as_str) != Some("not_measured")
        }) {
            return fail("measured refinement card lacks source evidence capability");
        }
        return Ok(HashMap::new());
    }
    if text(capability, "file")? != PROJECTION {
        return fail("unexpected source evidence capability path");
    }
    validate_artifact(
        root,
        PROJECTION,
        text(capability, "sha256")?,
        "source evidence projection",
    )?;
    let proof = read_json(root, PROJECTION)?;
    let recipe = &proof["recipe"];
    if proof["schema"] != "cgat.refinement-source-evidence-projection"
        || proof["schema_version"] != 1
        || recipe["schema"] != "cgat.refinement-source-evidence-recipe"
        || recipe["schema_version"] != 1
        || text(&proof, "generation_sha256")?
            != sha256_bytes(q0_provenance::canonical(recipe)?.as_bytes())
        || recipe["tool"] != manifest["tool"]
        || recipe["run_id"] != manifest["run_id"]
        || recipe["provenance_sha256"] != manifest["provenance_sha256"]
    {
        return fail("source evidence recipe/generation differs from accepted refinement");
    }
    validate_sha256(
        text(&proof, "source_receipt_sha256")?,
        "source evidence receipt",
    )?;
    let files: BTreeMap<String, String> = serde_json::from_value(proof["files"].clone())?;
    for (name, sha) in &files {
        validate_sha256(sha, "measured source artifact")?;
        if observed.get(name) != Some(sha) {
            return fail("delivered source measurement changed or is missing");
        }
    }
    let frozen: BTreeMap<String, String> =
        serde_json::from_value(recipe["annotation_files"].clone())?;
    for (name, sha) in &frozen {
        validate_sha256(sha, "frozen source annotation input")?;
        if name != "cen/library.fa" && observed.get(name) != Some(sha) {
            return fail("delivered annotation rules differ from measured snapshot");
        }
    }
    let report = read_json(root, "report/manifest.json")?;
    let report_files: BTreeMap<String, String> = serde_json::from_value(report["files"].clone())?;
    let actual_report: BTreeMap<String, String> = observed
        .iter()
        .filter_map(|(name, sha)| {
            name.strip_prefix("report/")
                .filter(|name| *name != "manifest.json")
                .map(|name| (name.into(), sha.clone()))
        })
        .collect();
    if report["schema"] != "cgat.refinement-report"
        || report["schema_version"] != 1
        || report_files != actual_report
        || report["binding"]["provenance_sha256"] != manifest["provenance_sha256"]
        || report["binding"]["source_evidence_receipt_sha256"] != proof["source_receipt_sha256"]
        || report["binding"]["source_evidence_generation_sha256"] != proof["generation_sha256"]
    {
        return fail("report and measured-source provenance differ");
    }
    let summary = read_json(root, "report/summary.json")?;
    if summary["source_evidence"]["sources"] != proof["sources"] {
        return fail("report source status differs from delivered measurements");
    }
    let mut patches = BTreeMap::new();
    let mut lengths = BTreeMap::new();
    for row in array(manifest, "sources")? {
        let key = source(row)?;
        let length = number(row, "length")?;
        if length == 0 || lengths.insert(key.clone(), length).is_some() {
            return fail("invalid/duplicate accepted source catalog");
        }
        if text(row, "origin")?.starts_with("refinement:") {
            patches.insert(key, serde_json::json!({"dataset": row["dataset"], "contig": row["contig"], "length": row["length"], "fasta_sha256": row["fasta_sha256"]}));
        }
    }
    let mut declared = BTreeMap::new();
    for row in array(recipe, "patch_sources")? {
        if declared.insert(source(row)?, row.clone()).is_some() {
            return fail("duplicate measured patch source");
        }
    }
    if declared != patches {
        return fail("measured sources differ from accepted patch identities");
    }
    let reference = &table(tables, "metadata/reference.tsv")?.rows[0];
    let reference_records = read_fai_lengths(
        &required_bundle_file(
            root,
            field(reference, "fai_relpath")?,
            "measured reference index",
        )?,
        "measured reference",
    )?;
    let fasta = field(reference, "fasta_relpath")?;
    validate_sha256(
        text(recipe, "reference_sha256")?,
        "measured original reference",
    )?;
    if root.join(fasta).is_file()
        && observed.get(fasta).map(String::as_str) != Some(text(recipe, "reference_sha256")?)
    {
        return fail("delivered reference differs from measured original reference");
    }
    let mut datasets: BTreeMap<String, BTreeMap<String, u64>> = BTreeMap::new();
    for ((dataset, contig), row) in &patches {
        datasets
            .entry(dataset.clone())
            .or_default()
            .insert(contig.clone(), number(row, "length")?);
    }
    let mut hits = HashMap::new();
    for (dataset, queries) in datasets {
        if !files.contains_key(&format!("runs/{dataset}_vs_ref/result.paf")) {
            return fail("measured patch reference PAF is missing");
        }
        for (contig, records) in paf_hits(root, &dataset, &queries, &reference_records, cancel)? {
            hits.insert((dataset.clone(), contig), records);
        }
    }
    let enabled = |kind: &str| -> Result<bool> {
        recipe["annotation_enabled"][kind]
            .as_bool()
            .context("invalid source annotation enable state")
    };
    let cen_entries = if enabled("cen")? {
        records(root, "cen/reference.tsv")?
    } else {
        Vec::new()
    };
    let tel_rules = if enabled("tel")? {
        records(root, "tel/rules.tsv")?
    } else {
        Vec::new()
    };
    let mut placements = HashMap::new();
    let mut measured_keys = HashSet::new();
    for row in array(&proof, "sources")? {
        let key = source(row)?;
        let chromosome = text(row, "chromosome")?;
        let patch = patches
            .get(&key)
            .context("measured placement has no accepted patch source")?;
        let actual = hits.get(&key);
        let total =
            actual
                .into_iter()
                .flat_map(|rows| rows.values())
                .try_fold(0_u64, |total, n| {
                    total
                        .checked_add(*n)
                        .context("measured source hit count overflow")
                })?;
        let on_chr = actual
            .and_then(|rows| rows.get(chromosome))
            .copied()
            .unwrap_or(0);
        let status = if total == 0 {
            "no_hit"
        } else if on_chr == 0 {
            "other_chr_only"
        } else if total > 1 {
            "multi_hit"
        } else {
            "hit"
        };
        let annotations = serde_json::json!({"tel": if !enabled("tel")? { "disabled" } else if tel_rules.is_empty() { "no_rules" } else { "scanned" },
            "cen": if !enabled("cen")? { "disabled" } else if cen_entries.iter().any(|row| row.get("chr_name").is_some_and(|name| name == "*" || name == chromosome)) { "scanned" } else { "no_chr_library" }});
        if row["length"] != patch["length"]
            || row["fasta_sha256"] != patch["fasta_sha256"]
            || text(row, "ref_alignment_status")? != status
            || number(row, "reference_hits")? != total
            || number(row, "hits_on_chromosome")? != on_chr
            || row["annotations"] != annotations
            || !measured_keys.insert((key.0.clone(), key.1.clone(), chromosome.to_string()))
        {
            return fail("source status does not describe delivered measurements");
        }
        if enabled("tel")? && !files.contains_key(&format!("tel/chr_{chromosome}/{}.tsv", key.0)) {
            return fail("scanned patch telomere table is missing");
        }
        if enabled("cen")? && !files.contains_key(&format!("cen/chr_{chromosome}/marks.tsv")) {
            return fail("patch centromere scan state has no marks table");
        }
        placements.insert(
            format!("{}:{}:{chromosome}:refinement", key.0, key.1),
            row.clone(),
        );
    }
    let slices = slices(server, &lengths)?;
    let expected_keys: HashSet<_> = slices
        .iter()
        .filter(|row| patches.contains_key(&(row.dataset.clone(), row.contig.clone())))
        .map(|row| {
            (
                row.dataset.clone(),
                row.contig.clone(),
                row.chromosome.clone(),
            )
        })
        .collect();
    if measured_keys != expected_keys {
        return fail("measurements do not cover all accepted patch placements");
    }
    let mut intervals: Vec<_> = slices.iter().map(interval_record).collect();
    intervals.sort();
    let mut actual_intervals = records(root, "metadata/refinement/source_intervals.tsv")?;
    actual_intervals.sort();
    if intervals != actual_intervals {
        return fail("source-to-final coordinate map differs from accepted slices");
    }
    let expected_marks = annotation_records(root, &slices, &lengths, &patches, cancel)?;
    let mut actual_marks = records(root, "metadata/refinement/final_annotations.tsv")?;
    actual_marks.sort();
    if expected_marks != actual_marks {
        return fail("final annotation coordinates differ from measured source slices");
    }
    Ok(placements)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn measured_cigar_requires_exact_spans_and_bounded_lengths() {
        cigar_spans("3M2I3D", 5, 6).unwrap();
        for cigar in ["01M", "0M", "1M0", "2S1M", "184467440737095516160M", "1M"] {
            assert!(cigar_spans(cigar, 5, 6).is_err(), "{cigar}");
        }
    }
    #[test]
    fn measured_marks_clip_and_reverse_through_repeated_source_slices() {
        let temp = tempfile::tempdir().unwrap();
        let folder = temp.path().join("tel/chr_chr");
        fs::create_dir_all(&folder).unwrap();
        fs::write(folder.join("ds.tsv"), "rule_id\tdataset_name\tseq_name\tassigned_chr_name\tstart_bp\tend_bp\tstrand\nmiddle\tds\tu\tchr\t3\t7\t+\nclipped\tds\tu\tchr\t1\t3\t+\n").unwrap();
        let forward = Slice {
            chromosome: "chr".into(),
            id: "forward".into(),
            dataset: "ds".into(),
            contig: "u".into(),
            start: 2,
            end: 9,
            reverse: false,
            output: 0,
            length: 8,
            kind: "patch".into(),
        };
        let reverse = Slice {
            id: "reverse".into(),
            reverse: true,
            output: 8,
            ..forward.clone()
        };
        let key = ("ds".into(), "u".into());
        let lengths = BTreeMap::from([(key.clone(), 10_u64)]);
        let patches = BTreeMap::from([(key, Value::Null)]);
        let rows = annotation_records(
            temp.path(),
            &[forward, reverse],
            &lengths,
            &patches,
            &mut || false,
        )
        .unwrap();
        let middle = rows
            .iter()
            .find(|row| row["annotation_id"] == "middle" && row["segment_id"] == "reverse")
            .unwrap();
        assert_eq!(
            (
                middle["final_start"].as_str(),
                middle["final_end"].as_str(),
                middle["final_strand"].as_str()
            ),
            ("10", "15", "-")
        );
        let clipped = rows
            .iter()
            .find(|row| row["annotation_id"] == "clipped" && row["segment_id"] == "reverse")
            .unwrap();
        assert_eq!(clipped["final_start"], "14");
        assert_eq!(clipped["final_end"], "16");
        assert_eq!(
            clipped["projection"],
            "clipped_source_support_not_rescanned"
        );
    }
}
