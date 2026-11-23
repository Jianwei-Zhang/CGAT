//! Package-3 q0 proof verification. Never rerun today's selector or compare its
//! installed code hash: a historical package is checked against its own frozen
//! input bytes, selected original intervals and exact source/evidence rows.
use super::*;
use serde_json::json;

const SELECTION: &str = "metadata/grt_q0_selection.json";
const FREEZE: &str = "metadata/grt_q0_freeze.json";

#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd)]
struct Source {
    dataset: String,
    contig: String,
}
impl Source {
    fn key(&self) -> (String, String) {
        (self.dataset.clone(), self.contig.clone())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd)]
struct Span {
    start: usize,
    end: usize,
}
impl Span {
    fn check(self, length: usize) -> Result<Self> {
        if self.start >= self.end || self.end > length {
            return invalid("source interval is out of bounds");
        }
        Ok(self)
    }
}
#[derive(Deserialize)]
struct FrozenSource {
    source: Source,
    length: usize,
    sequence_sha256: String,
    occupied: Vec<Span>,
    available: Vec<Span>,
    informative_intervals: Vec<Span>,
}
#[derive(Deserialize)]
struct FrozenMember {
    donor_set_id: String,
    member_id: String,
    source: Source,
    available_member_intervals: Vec<Span>,
}
#[derive(Deserialize)]
struct Freeze {
    schema: String,
    package_schema_version: String,
    selection: String,
    selection_sha256: String,
    q0_rows_sha256: String,
    q0_evidence_sha256: String,
    artifacts: BTreeMap<String, String>,
    source_fastas: BTreeMap<String, String>,
    sources: Vec<FrozenSource>,
    members: Vec<FrozenMember>,
}
#[derive(Deserialize)]
struct Slice {
    source: Source,
    interval: Span,
    orientation: String,
    placement_id: String,
}
#[derive(Deserialize)]
struct Join {
    kind: String,
    join_id: String,
    n_bp: usize,
    gap_source: Option<Source>,
    gap_interval: Option<Span>,
}
#[derive(Deserialize)]
struct SelectedPath {
    slices: Vec<Slice>,
    joins: Vec<Join>,
}
#[derive(Deserialize)]
struct Search {
    // Null is an explicit unselected chromosome; a missing decision is corrupt.
    #[serde(deserialize_with = "required_selected_path")]
    path: Option<SelectedPath>,
}
fn required_selected_path<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<SelectedPath>, D::Error> {
    Option::<SelectedPath>::deserialize(deserializer)
}
#[derive(Deserialize)]
struct Construction {
    selector_identity: String,
    searches: BTreeMap<String, Search>,
    evidence: BTreeMap<String, Value>,
}
#[derive(Deserialize)]
struct Selection {
    schema: String,
    artifact_hashes: BTreeMap<String, String>,
    construction: Construction,
}

fn invalid<T>(message: impl std::fmt::Display) -> Result<T> {
    grt_err("INVALID_Q0_SELECTION", message)
}
fn decode<T: serde::de::DeserializeOwned>(root: &Path, relative: &str) -> Result<T> {
    serde_json::from_value(read_json(root, relative)?)
        .map_err(|error| grt_anyhow("INVALID_Q0_SELECTION", format!("{relative}: {error}")))
}
// Python's row identities use ensure_ascii=True, sorted keys, and compact JSON.
// These hashes contain strings/integers, not floating-point algorithm scores.
pub(super) fn canonical(value: &impl Serialize) -> Result<String> {
    let encoded = serde_json::to_string(value)?;
    let mut output = String::new();
    for ch in encoded.chars() {
        if ch <= '\u{7e}' {
            output.push(ch);
        } else {
            for unit in ch.encode_utf16(&mut [0; 2]) {
                output.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    Ok(output)
}
fn stable_id(prefix: &str, value: &impl Serialize) -> Result<String> {
    Ok(format!(
        "{prefix}-{}",
        &sha256_bytes(canonical(value)?.as_bytes())[..24]
    ))
}
fn row_hash(rows: &[&TsvRow]) -> Result<String> {
    Ok(sha256_bytes(canonical(&rows)?.as_bytes()))
}
fn merge(mut spans: Vec<Span>) -> Vec<Span> {
    spans.sort();
    let mut result: Vec<Span> = Vec::new();
    for span in spans {
        if let Some(last) = result.last_mut()
            && last.end >= span.start
        {
            last.end = last.end.max(span.end);
            continue;
        }
        result.push(span);
    }
    result
}
fn subtract(domain: &[Span], removed: &[Span]) -> Vec<Span> {
    let mut result = Vec::new();
    for span in domain {
        let mut cursor = span.start;
        for cut in removed {
            if cut.end <= cursor || cut.start >= span.end {
                continue;
            }
            if cut.start > cursor {
                result.push(Span {
                    start: cursor,
                    end: cut.start.min(span.end),
                });
            }
            cursor = cursor.max(cut.end).min(span.end);
        }
        if cursor < span.end {
            result.push(Span {
                start: cursor,
                end: span.end,
            });
        }
    }
    result
}
fn informative(sequence: &str) -> Vec<Span> {
    let bytes = sequence.as_bytes();
    let mut gaps = Vec::new();
    let mut cursor = 0;
    while cursor < bytes.len() {
        if bytes[cursor] != b'N' {
            cursor += 1;
            continue;
        }
        let start = cursor;
        while cursor < bytes.len() && bytes[cursor] == b'N' {
            cursor += 1;
        }
        if cursor - start >= 100 {
            gaps.push(Span { start, end: cursor });
        }
    }
    subtract(
        &[Span {
            start: 0,
            end: bytes.len(),
        }],
        &gaps,
    )
}
fn unique_spans(spans: &mut [Span]) -> Result<()> {
    spans.sort();
    if spans.windows(2).any(|pair| pair[0].end > pair[1].start) {
        return invalid("path repeats an original source interval");
    }
    Ok(())
}
fn source_span(row: &TsvRow) -> Result<Span> {
    let (start, end) = interval(row, "source_start", "source_end", "q source")?;
    Ok(Span {
        start: (start - 1) as usize,
        end: end as usize,
    })
}
pub(super) fn card_key(
    dataset: &str,
    contig: &str,
    chromosome: &str,
    assignments: &HashMap<(String, String), HashSet<String>>,
) -> String {
    let targets = assignments.get(&(dataset.to_string(), contig.to_string()));
    let mode = if targets.is_some_and(|targets| targets.contains(chromosome)) {
        "normal"
    } else if targets.is_some_and(|targets| !targets.is_empty()) {
        "cross_chr_grt_usage"
    } else {
        "grt_promoted"
    };
    format!("{dataset}:{contig}:{chromosome}:{mode}")
}

type RootKey = (String, String, String, String);
#[derive(Default)]
pub(super) struct Q0Proof {
    roots: HashMap<RootKey, Vec<(Span, HashSet<String>)>>,
}

pub(super) fn validate_q0(
    root: &Path,
    tables: &HashMap<&'static str, TsvTable>,
    sources: &HashMap<(String, String), String>,
    assignments: &HashMap<(String, String), HashSet<String>>,
    q_versions: &[&str],
) -> Result<Q0Proof> {
    let freeze: Freeze = decode(root, FREEZE)?;
    let selection: Selection = decode(root, SELECTION)?;
    if freeze.schema != "lgz_q0_donor_freeze_v2"
        || freeze.package_schema_version
            != field(one_row(tables, "metadata/package.tsv")?, "schema_version")?
        || selection.schema != "lgz_q0_selection_artifact_v1"
        || freeze.selection != SELECTION
    {
        return invalid("unsupported q0 freeze/selection schema");
    }
    validate_artifact(root, SELECTION, &freeze.selection_sha256, "q0 selection")?;
    let mut required = [
        SELECTION,
        "grt/q/q0.fa",
        "metadata/grt_recipe.tsv",
        "metadata/grt_contig_roles.tsv",
        "metadata/grt_donor_sets.tsv",
        "metadata/grt_donor_members.tsv",
        "metadata/grt_donor_fragments.tsv",
        "metadata/grt_contig_quality.tsv",
        "metadata/grt_telomere_rules.tsv",
    ]
    .into_iter()
    .map(str::to_string)
    .collect::<HashSet<_>>();
    for row in &table(tables, "metadata/grt_donor_sets.tsv")?.rows {
        for key in ["fasta_relpath", "manifest_relpath"] {
            required.insert(field(row, key)?.to_string());
        }
    }
    if freeze.artifacts.keys().cloned().collect::<HashSet<_>>() != required {
        return invalid("incomplete frozen artifact inventory");
    }
    for (path, hash) in &freeze.artifacts {
        validate_artifact(root, path, hash, "q0 frozen artifact")?;
    }
    let expected_raw = selection
        .construction
        .evidence
        .values()
        .filter_map(|row| {
            row.get("artifact")
                .and_then(Value::as_str)
                .or_else(|| row.get("catalog").and_then(Value::as_str))
        })
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if selection
        .artifact_hashes
        .keys()
        .cloned()
        .collect::<HashSet<_>>()
        != expected_raw
    {
        return invalid("incomplete q0 raw evidence inventory");
    }
    for (path, hash) in &selection.artifact_hashes {
        validate_artifact(root, path, hash, "q0 raw evidence")?;
    }
    // Later add-dataset operations extend the project, not this locked q0
    // input set. The recipe itself is a hash-bound frozen artifact above.
    let recipe = one_row(tables, "metadata/grt_recipe.tsv")?;
    let mut initial_datasets = json_string_list(
        field(recipe, "support_datasets_json")?,
        "recipe.support_datasets_json",
    )?
    .into_iter()
    .collect::<HashSet<_>>();
    initial_datasets.insert(field(recipe, "primary_dataset")?.to_string());
    let expected_fastas = table(tables, "metadata/datasets.tsv")?
        .rows
        .iter()
        .filter(|row| {
            row.get("dataset_name")
                .is_some_and(|name| initial_datasets.contains(name))
        })
        .map(|row| {
            Ok((
                field(row, "dataset_name")?.to_string(),
                field(row, "fasta_relpath")?.to_string(),
            ))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    if expected_fastas.keys().cloned().collect::<HashSet<_>>() != initial_datasets
        || freeze.source_fastas != expected_fastas
    {
        return invalid("q0 source FASTA inventory differs from locked recipe datasets");
    }

    let q_rows = &table(tables, "metadata/grt_q_segments.tsv")?.rows;
    let actual_q0 = q_rows
        .iter()
        .filter(|row| row.get("q_version").map(String::as_str) == Some("q0"))
        .collect::<Vec<_>>();
    if row_hash(&actual_q0)? != freeze.q0_rows_sha256 {
        return invalid("q0 source rows changed after freeze");
    }
    let mut expected_rows = Vec::new();
    let mut occupied: HashMap<(String, String), Vec<Span>> = HashMap::new();
    for (chr, search) in &selection.construction.searches {
        let Some(path) = &search.path else {
            continue;
        };
        if path.slices.is_empty() || path.joins.len() != path.slices.len() - 1 {
            return invalid("invalid selected q0 path shape");
        }
        let mut cursor: usize = 1;
        for (index, slice) in path.slices.iter().enumerate() {
            let sequence = sources
                .get(&slice.source.key())
                .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "unknown selected q0 source"))?;
            let span = slice.interval.check(sequence.len())?;
            orientation(&slice.orientation, "q0 selected orientation")?;
            occupied.entry(slice.source.key()).or_default().push(span);
            let segment_id = stable_id(
                "q0-source",
                &json!([
                    chr,
                    index,
                    slice.placement_id,
                    span.start,
                    span.end,
                    slice.orientation
                ]),
            )?;
            let evidence_id = stable_id(
                "ev-q0-selection",
                &json!([segment_id, selection.construction.selector_identity]),
            )?;
            let next = cursor
                .checked_add(span.end - span.start)
                .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "q0 coordinate overflow"))?;
            let mut row = types::Q_SEGMENTS_HEADER
                .iter()
                .map(|key| (key.to_string(), String::new()))
                .collect::<TsvRow>();
            for (key, value) in [
                ("q_version", "q0".to_string()),
                ("chr", chr.clone()),
                ("segment_id", segment_id),
                ("segment_kind", "source".to_string()),
                ("q_start", cursor.to_string()),
                ("q_end", (next - 1).to_string()),
                ("dataset_name", slice.source.dataset.clone()),
                ("contig_name", slice.source.contig.clone()),
                ("source_start", (span.start + 1).to_string()),
                ("source_end", span.end.to_string()),
                ("orientation", slice.orientation.clone()),
                (
                    "source_card_key",
                    card_key(
                        &slice.source.dataset,
                        &slice.source.contig,
                        chr,
                        assignments,
                    ),
                ),
                ("evidence_ids_json", canonical(&vec![evidence_id])?),
            ] {
                row.insert(key.to_string(), value);
            }
            expected_rows.push(row);
            cursor = next;
            if let Some(join) = path.joins.get(index) {
                if join.kind == "input_assembly_gap" {
                    let source = join
                        .gap_source
                        .as_ref()
                        .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "N gap lacks source"))?;
                    let sequence = sources.get(&source.key()).ok_or_else(|| {
                        grt_anyhow("INVALID_Q0_SELECTION", "unknown N-gap source")
                    })?;
                    let gap = join
                        .gap_interval
                        .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "N gap lacks interval"))?
                        .check(sequence.len())?;
                    if gap.end - gap.start != join.n_bp
                        || !sequence.as_bytes()[gap.start..gap.end]
                            .iter()
                            .all(|byte| *byte == b'N')
                    {
                        return invalid("q0 N gap differs from original source");
                    }
                    occupied.entry(source.key()).or_default().push(gap);
                }
                if join.n_bp != 0 {
                    let next = cursor
                        .checked_add(join.n_bp)
                        .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "q0 gap overflow"))?;
                    let mut row = types::Q_SEGMENTS_HEADER
                        .iter()
                        .map(|key| (key.to_string(), String::new()))
                        .collect::<TsvRow>();
                    for (key, value) in [
                        ("q_version", "q0".to_string()),
                        ("chr", chr.clone()),
                        ("segment_id", stable_id("q0-gap", &join.join_id)?),
                        ("segment_kind", "gap".to_string()),
                        ("q_start", cursor.to_string()),
                        ("q_end", (next - 1).to_string()),
                        ("evidence_ids_json", "[]".to_string()),
                    ] {
                        row.insert(key.to_string(), value);
                    }
                    expected_rows.push(row);
                    cursor = next;
                }
            }
        }
    }
    if expected_rows.iter().collect::<Vec<_>>() != actual_q0 {
        return invalid("q0 rows differ from selected paths");
    }
    for spans in occupied.values_mut() {
        unique_spans(spans)?;
    }
    let mut frozen_sources = HashMap::new();
    for frozen in &freeze.sources {
        let key = frozen.source.key();
        let sequence = sources
            .get(&key)
            .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "unknown frozen source"))?;
        if frozen_sources.insert(key.clone(), frozen).is_some() {
            return invalid("duplicate frozen source");
        }
        let domain = informative(sequence);
        let used = merge(occupied.remove(&key).unwrap_or_default());
        if frozen.length != sequence.len()
            || frozen.sequence_sha256 != sha256_bytes(sequence.as_bytes())
            || frozen.informative_intervals != domain
            || frozen.occupied != used
            || frozen.available != subtract(&domain, &used)
        {
            return invalid(
                "frozen source identity/availability disagrees with original sequence and q0",
            );
        }
    }
    let initial_sources = sources
        .keys()
        .filter(|(dataset, _)| initial_datasets.contains(dataset))
        .collect::<HashSet<_>>();
    if frozen_sources.keys().collect::<HashSet<_>>() != initial_sources || !occupied.is_empty() {
        return invalid("q0 freeze does not cover original sources");
    }
    let members = &table(tables, "metadata/grt_donor_members.tsv")?.rows;
    let member_index = members
        .iter()
        .map(|row| Ok(((field(row, "donor_set_id")?, field(row, "member_id")?), row)))
        .collect::<Result<HashMap<_, _>>>()?;
    let mut seen_members = HashSet::new();
    for member in &freeze.members {
        let key = (member.donor_set_id.as_str(), member.member_id.as_str());
        let row = member_index
            .get(&key)
            .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "unknown frozen donor member"))?;
        let source = frozen_sources
            .get(&member.source.key())
            .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "unknown member source"))?;
        if !seen_members.insert(key)
            || field(row, "dataset_name")? != member.source.dataset
            || field(row, "contig_name")? != member.source.contig
            || field(row, "source_start")? != "1"
            || field(row, "source_end")? != source.length.to_string()
            || field(row, "orientation")? != "+"
            || member.available_member_intervals != source.available
        {
            return invalid("donor context/authorization differs from complete original source");
        }
    }
    if seen_members.len() != members.len() {
        return invalid("incomplete frozen donor member inventory");
    }
    let evidence = &table(tables, "metadata/grt_evidence_registry.tsv")?.rows;
    let q0_evidence = evidence
        .iter()
        .filter(|row| row.get("stage").map(String::as_str) == Some("q0_construction"))
        .collect::<Vec<_>>();
    if row_hash(&q0_evidence)? != freeze.q0_evidence_sha256 {
        return invalid("q0 selection evidence changed after freeze");
    }
    let evidence_index = evidence
        .iter()
        .map(|row| (row["evidence_id"].as_str(), row))
        .collect::<HashMap<_, _>>();
    let mut proof = Q0Proof::default();
    for row in &actual_q0 {
        if field(row, "segment_kind")? == "gap" {
            continue;
        }
        let ids = json_string_list(field(row, "evidence_ids_json")?, "q0 source evidence")?;
        for id in &ids {
            let ev = evidence_index
                .get(id.as_str())
                .ok_or_else(|| grt_anyhow("INVALID_Q0_SELECTION", "unknown q0 source evidence"))?;
            if field(ev, "stage")? != "q0_construction"
                || field(ev, "evidence_type")? != "q0_path_selection"
                || field(ev, "status")? != "accepted"
                || field(ev, "coordinate_system")? != "source_0_based_half_open"
                || field(ev, "projection_status")? != "projected"
                || field(ev, "q_version")? != "q0"
                || field(ev, "query_artifact_relpath")?
                    != freeze.source_fastas[&row["dataset_name"]]
                || field(ev, "raw_artifact_relpath")? != SELECTION
                || field(ev, "source_dataset")? != field(row, "dataset_name")?
                || field(ev, "source_contig")? != field(row, "contig_name")?
                || field(ev, "target_chr")? != field(row, "chr")?
                || field(ev, "orientation")? != field(row, "orientation")?
                || field(ev, "source_start")? != field(row, "source_start")?
                || field(ev, "source_end")? != field(row, "source_end")?
            {
                return invalid("q0 source evidence does not prove its selected interval");
            }
        }
        let key = (
            row["chr"].clone(),
            row["dataset_name"].clone(),
            row["contig_name"].clone(),
            row["orientation"].clone(),
        );
        proof
            .roots
            .entry(key)
            .or_default()
            .push((source_span(row)?, ids.into_iter().collect()));
    }
    for roots in proof.roots.values_mut() {
        roots.sort_by_key(|row| row.0);
    }
    let expected_chrs = actual_q0
        .iter()
        .map(|row| row["chr"].clone())
        .collect::<HashSet<_>>();
    for &version in q_versions {
        let mut by_source: HashMap<(String, String), Vec<Span>> = HashMap::new();
        let mut chrs = HashSet::new();
        for row in q_rows.iter().filter(|row| row["q_version"] == version) {
            chrs.insert(row["chr"].clone());
            if row["segment_kind"] == "gap" {
                continue;
            }
            if row["source_card_key"]
                != card_key(
                    &row["dataset_name"],
                    &row["contig_name"],
                    &row["chr"],
                    assignments,
                )
            {
                return invalid("non-canonical q source card key");
            }
            by_source
                .entry((row["dataset_name"].clone(), row["contig_name"].clone()))
                .or_default()
                .push(source_span(row)?);
        }
        if chrs != expected_chrs {
            return invalid("q stage chromosome set differs from selected q0");
        }
        for spans in by_source.values_mut() {
            unique_spans(spans)?;
        }
    }
    Ok(proof)
}

impl Q0Proof {
    pub(super) fn final_roots(
        &self,
        tables: &HashMap<&'static str, TsvTable>,
        final_path: &Value,
        assignments: &HashMap<(String, String), HashSet<String>>,
    ) -> Result<HashMap<String, HashSet<String>>> {
        let mut output: HashMap<String, HashSet<String>> = HashMap::new();
        let chromosomes = final_path["chromosomes"]
            .as_array()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path chromosomes"))?;
        let rows = &table(tables, "metadata/grt_q_segments.tsv")?.rows;
        for chromosome in chromosomes {
            let chr = chromosome["chr"]
                .as_str()
                .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path chr"))?;
            let segments = chromosome["segments"]
                .as_array()
                .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path segments"))?;
            let final_version = final_q_version(field(
                one_row(tables, "metadata/package.tsv")?,
                "schema_version",
            )?);
            let mut q4 = rows
                .iter()
                .filter(|row| row["q_version"] == final_version && row["chr"] == chr)
                .collect::<Vec<_>>();
            q4.sort_by_key(|row| row["q_start"].parse::<i64>().unwrap_or(0));
            if segments.len() != q4.len() {
                return invalid("Final Path differs from q4 source mapping");
            }
            for (segment, row) in segments.iter().zip(q4) {
                let gap = row["segment_kind"] == "gap";
                let ids = json_string_list(&row["evidence_ids_json"], "q4 evidence")?;
                let source = if gap {
                    Value::Null
                } else {
                    json!({"dataset": row["dataset_name"], "contig": row["contig_name"],
                    "start": parse_positive_i64(&row["source_start"], "q4 source start")?,
                    "end": parse_positive_i64(&row["source_end"], "q4 source end")?, "orientation": row["orientation"]})
                };
                let length = parse_positive_i64(&row["q_end"], "q4 end")?
                    - parse_positive_i64(&row["q_start"], "q4 start")?
                    + 1;
                if segment["source"] != source
                    || (segment["kind"] == "gap") != gap
                    || segment["length"].as_i64() != Some(length)
                    || segment["evidence_ids"] != json!(ids)
                {
                    return invalid("Final Path differs from q4 source mapping");
                }
                if gap
                    || segment["event_id"]
                        .as_str()
                        .is_some_and(|id| !id.is_empty())
                {
                    continue;
                }
                let key = (
                    chr.to_string(),
                    row["dataset_name"].clone(),
                    row["contig_name"].clone(),
                    row["orientation"].clone(),
                );
                let span = source_span(row)?;
                let mut cursor = span.start;
                if let Some(roots) = self.roots.get(&key) {
                    for (root, links) in roots {
                        if links.is_empty()
                            || !links.iter().all(|id| ids.contains(id))
                            || root.end <= cursor
                        {
                            continue;
                        }
                        if root.start > cursor {
                            break;
                        }
                        cursor = cursor.max(root.end);
                        if cursor >= span.end {
                            break;
                        }
                    }
                }
                if cursor < span.end {
                    return invalid("Final Path source lacks frozen q0 provenance");
                }
                let card = card_key(&row["dataset_name"], &row["contig_name"], chr, assignments);
                let id = segment["segment_id"]
                    .as_str()
                    .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path segment id"))?;
                output.entry(card).or_default().insert(id.to_string());
            }
        }
        Ok(output)
    }
}

/// App projections omit Server proofs, but retain exact original-source bounds.
/// Apply the package-3 no-duplicate rule across every chromosome and strand.
pub(super) fn validate_final_source_uniqueness(final_path: &Value) -> Result<()> {
    let mut spans: HashMap<(String, String), Vec<Span>> = HashMap::new();
    let chromosomes = final_path["chromosomes"]
        .as_array()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path chromosomes"))?;
    for chr in chromosomes {
        let segments = chr["segments"]
            .as_array()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path segments"))?;
        for segment in segments {
            if segment["kind"] == "gap" {
                continue;
            }
            let source = segment["source"]
                .as_object()
                .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path source"))?;
            let key = (
                json_str(source, "dataset", "Final Path source")?.to_string(),
                json_str(source, "contig", "Final Path source")?.to_string(),
            );
            let start = json_positive_i64(source, "start", "Final Path source")? as usize;
            let end = json_positive_i64(source, "end", "Final Path source")? as usize;
            if start > end {
                return grt_err(
                    "INVALID_COORDINATE",
                    "Final Path source interval is reversed",
                );
            }
            spans.entry(key).or_default().push(Span {
                start: start - 1,
                end,
            });
        }
    }
    for intervals in spans.values_mut() {
        unique_spans(intervals).map_err(|error| grt_anyhow("INVALID_SOURCE_PATH", error))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unselected_chromosome_requires_explicit_null_not_a_missing_decision() {
        assert!(serde_json::from_str::<Search>(r#"{}"#).is_err());
        assert!(
            serde_json::from_str::<Search>(r#"{"path":null}"#)
                .unwrap()
                .path
                .is_none()
        );
    }
    #[test]
    fn canonical_hashes_escape_unicode_like_python() {
        assert_eq!(
            canonical(&vec!["chr一🧬\u{7f}"]).unwrap(),
            r#"["chr\u4e00\ud83e\uddec\u007f"]"#
        );
    }
    #[test]
    fn informative_intervals_keep_short_ns_but_exclude_long_n_runs() {
        let sequence = format!("ACNNGT{}TGC", "N".repeat(100));
        assert_eq!(
            informative(&sequence),
            vec![
                Span { start: 0, end: 6 },
                Span {
                    start: 106,
                    end: 109
                }
            ]
        );
        assert_eq!(
            subtract(&informative(&sequence), &[Span { start: 2, end: 108 }]),
            vec![
                Span { start: 0, end: 2 },
                Span {
                    start: 108,
                    end: 109
                }
            ]
        );
        assert!(unique_spans(&mut [Span { start: 0, end: 5 }, Span { start: 4, end: 8 }]).is_err());
        assert!(unique_spans(&mut [Span { start: 0, end: 5 }, Span { start: 5, end: 8 }]).is_ok());
    }
}
