use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::db::open_workspace_db;
use crate::project_initializer::{
    ProjectInitializationRequest, bootstrap_project_assembly_with_connection,
    delete_project_with_connection, initialize_project_with_connection,
    list_initializer_options_with_connection, set_project_auto_pipeline_done_with_connection,
};

pub const GRT_WORKFLOW: &str = "gpm_grt_precomputed_v1";
pub const GRT_APP_WORKFLOW: &str = "gpm_grt_app_precomputed_v1";
pub const GRT_SCHEMA_VERSION: &str = "1";
pub const GRT_FINAL_PATH_SCHEMA_VERSION: &str = "1";

type TsvRow = BTreeMap<String, String>;
type AppQ4Validation = (BTreeMap<String, usize>, Option<BTreeMap<String, String>>);

#[derive(Debug, Clone)]
struct TsvTable {
    rows: Vec<TsvRow>,
}

#[derive(Debug, Clone)]
pub(crate) struct ValidatedGrtPackage {
    tables: HashMap<&'static str, TsvTable>,
    events: Vec<Value>,
    final_path: Value,
    q0_artifact_sha256: String,
    q4_artifact_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrtLockedRecipe {
    pub workflow: String,
    pub schema_version: String,
    pub final_path_schema_version: String,
    pub recipe_id: String,
    pub primary_dataset: String,
    pub support_datasets: Vec<String>,
    pub reads_qc_enabled: bool,
    pub donor_set_id: String,
    pub tel_donor_set_id: String,
    pub q0_relpath: String,
    pub final_q_relpath: String,
    pub q0_artifact_sha256: String,
    pub q4_artifact_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrtSourceCardStatus {
    pub source_card_key: String,
    pub dataset_name: String,
    pub contig_name: String,
    pub target_chr: String,
    pub placement_mode: String,
    pub ref_alignment_status: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GrtSourceCardTrace {
    pub source_card: Value,
    pub accepted_events: Vec<Value>,
    pub final_path_segments: Vec<Value>,
    pub ref_evidence: Vec<Value>,
    pub pairwise_evidence: Vec<Value>,
    pub donor_usage: Vec<Value>,
    pub donor_members: Vec<Value>,
    pub donor_sets: Vec<Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GrtEventTrace {
    pub event: Value,
    pub evidence: Vec<Value>,
    pub donor_usage: Vec<Value>,
    pub final_path_segment: Option<Value>,
    pub source_card: Option<Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrtFinalPathVerification {
    pub chromosome_count: usize,
    pub segment_count: usize,
    pub q4_artifact_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GrtProjectInitializationSummary {
    pub project_id: i64,
    pub project_name: String,
    pub version: i64,
    pub reference_genome_id: i64,
    pub primary_dataset_id: i64,
    pub support_dataset_ids: Vec<i64>,
    pub project_dataset_count: i64,
    pub phased_assembly_enabled: bool,
    pub chr_assignment_min_coverage_percent: f64,
    pub assembly_seq_count: i64,
    pub assembly_ctg_count: i64,
    pub materialized_source_card_count: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GrtProjectView {
    pub recipe: GrtLockedRecipe,
    pub final_path_by_chr: BTreeMap<String, Value>,
    pub source_cards: Vec<GrtSourceCardStatus>,
    pub verification: GrtFinalPathVerification,
}

const REQUIRED_FILES: &[&str] = &[
    "metadata/package.tsv",
    "metadata/reference.tsv",
    "metadata/datasets.tsv",
    "metadata/source_seq_locator.tsv",
    "metadata/chr_assignments.tsv",
    "metadata/grt_recipe.tsv",
    "metadata/grt_contig_roles.tsv",
    "metadata/grt_q_segments.tsv",
    "metadata/grt_donor_sets.tsv",
    "metadata/grt_donor_members.tsv",
    "metadata/grt_evidence_registry.tsv",
    "metadata/grt_donor_usage.tsv",
    "metadata/grt_used_contigs.tsv",
    "metadata/grt_events.jsonl",
    "metadata/grt_gap_attempts.tsv",
    "metadata/grt_stage_status.tsv",
    "metadata/grt_tool_versions.tsv",
    "metadata/grt_final_path.json",
    "grt/q/q0.fa",
    "grt/q/q0r1.fa",
    "grt/q/q0f.fa",
    "grt/q/q1.fa",
    "grt/q/q2.fa",
    "grt/q/q3.fa",
    "grt/q/q4.fa",
];

const PACKAGE_HEADER: &[&str] = &[
    "workflow",
    "schema_version",
    "package_mode",
    "sequence_layout",
    "preassigned_chr",
    "self_alignment_scope",
    "cross_alignment_scope",
    "chr_assignment_min_coverage_percent",
    "grt_precompute_enabled",
    "recipe_locked",
    "final_path_schema_version",
    "reads_qc_enabled",
];
const REFERENCE_HEADER: &[&str] = &[
    "reference_name",
    "species_name",
    "assembly_label",
    "fasta_relpath",
    "fai_relpath",
];
const DATASETS_HEADER: &[&str] = &[
    "dataset_name",
    "assembler",
    "assembler_version",
    "fasta_relpath",
    "fai_relpath",
    "self_alignment_available",
];
const SOURCE_LOCATOR_HEADER: &[&str] = &["dataset_name", "seq_name", "fasta_relpath"];
const CHR_ASSIGNMENTS_HEADER: &[&str] = &[
    "dataset_name",
    "seq_name",
    "seq_length_bp",
    "assigned_chr_name",
    "source_orientation",
    "orientation_source",
    "support_bp",
    "support_percent",
    "anchor_start",
];
const RECIPE_HEADER: &[&str] = &[
    "recipe_id",
    "primary_dataset",
    "support_datasets_json",
    "reads_qc_enabled",
    "donor_set_id",
    "tel_donor_set_id",
    "q0_relpath",
    "final_q_relpath",
];
const CONTIG_ROLES_HEADER: &[&str] = &[
    "dataset_name",
    "contig_name",
    "q_eligible",
    "donor_eligible",
    "tel_donor_eligible",
    "q_rejection_reason",
    "donor_rejection_reason",
    "tel_rejection_reason",
];
const Q_SEGMENTS_HEADER: &[&str] = &[
    "q_version",
    "chr",
    "segment_id",
    "segment_kind",
    "q_start",
    "q_end",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "source_card_key",
    "evidence_ids_json",
];
const DONOR_SETS_HEADER: &[&str] = &[
    "donor_set_id",
    "donor_kind",
    "manifest_relpath",
    "fasta_relpath",
    "fasta_sha256",
    "member_count",
];
const DONOR_MEMBERS_HEADER: &[&str] = &[
    "donor_set_id",
    "member_id",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "fasta_record_name",
    "sequence_sha256",
];
const EVIDENCE_HEADER: &[&str] = &[
    "evidence_id",
    "stage",
    "evidence_type",
    "status",
    "q_version",
    "q_source_sha256",
    "query_artifact_relpath",
    "query_sha256",
    "donor_set_id",
    "target_artifact_relpath",
    "target_sha256",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "target_chr",
    "target_start",
    "target_end",
    "tool",
    "tool_version",
    "preset",
    "parameters_json",
    "raw_artifact_relpath",
    "raw_artifact_sha256",
    "coordinate_system",
    "projection_status",
];
const USAGE_HEADER: &[&str] = &[
    "usage_id",
    "donor_set_id",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "stage",
    "status",
    "event_id",
    "final_path_segment_id",
    "reason",
];
const USED_CONTIGS_HEADER: &[&str] = &[
    "source_card_key",
    "dataset_name",
    "contig_name",
    "original_assignment",
    "target_chr",
    "placement_mode",
    "ref_alignment_status",
    "anchor_start",
    "orientation",
    "ref_evidence_ids_json",
    "accepted_event_ids_json",
    "final_path_segment_ids_json",
    "pairwise_evidence_ids_json",
];
const GAP_ATTEMPTS_HEADER: &[&str] = &[
    "attempt_id",
    "chr",
    "object_id",
    "stage",
    "status",
    "reason",
    "candidate_count",
    "accepted_event_id",
];
const STAGE_STATUS_HEADER: &[&str] = &[
    "stage",
    "q_input_version",
    "q_input_sha256",
    "q_output_version",
    "q_output_sha256",
    "donor_set_id",
    "status",
    "checkpoint_relpath",
    "checkpoint_sha256",
];
const TOOL_VERSIONS_HEADER: &[&str] = &["tool", "version", "executable"];

const TABLE_SPECS: &[(&str, &[&str], usize, Option<usize>)] = &[
    ("metadata/package.tsv", PACKAGE_HEADER, 1, Some(1)),
    ("metadata/reference.tsv", REFERENCE_HEADER, 1, Some(1)),
    ("metadata/datasets.tsv", DATASETS_HEADER, 1, None),
    (
        "metadata/source_seq_locator.tsv",
        SOURCE_LOCATOR_HEADER,
        1,
        None,
    ),
    (
        "metadata/chr_assignments.tsv",
        CHR_ASSIGNMENTS_HEADER,
        1,
        None,
    ),
    ("metadata/grt_recipe.tsv", RECIPE_HEADER, 1, Some(1)),
    (
        "metadata/grt_contig_roles.tsv",
        CONTIG_ROLES_HEADER,
        1,
        None,
    ),
    ("metadata/grt_q_segments.tsv", Q_SEGMENTS_HEADER, 1, None),
    ("metadata/grt_donor_sets.tsv", DONOR_SETS_HEADER, 2, None),
    (
        "metadata/grt_donor_members.tsv",
        DONOR_MEMBERS_HEADER,
        0,
        None,
    ),
    (
        "metadata/grt_evidence_registry.tsv",
        EVIDENCE_HEADER,
        1,
        None,
    ),
    ("metadata/grt_donor_usage.tsv", USAGE_HEADER, 0, None),
    (
        "metadata/grt_used_contigs.tsv",
        USED_CONTIGS_HEADER,
        0,
        None,
    ),
    (
        "metadata/grt_gap_attempts.tsv",
        GAP_ATTEMPTS_HEADER,
        0,
        None,
    ),
    (
        "metadata/grt_stage_status.tsv",
        STAGE_STATUS_HEADER,
        8,
        Some(8),
    ),
    (
        "metadata/grt_tool_versions.tsv",
        TOOL_VERSIONS_HEADER,
        1,
        None,
    ),
];

const STAGE_TRANSITIONS: &[(&str, &str, &str)] = &[
    ("donor_freeze", "q0", "q0"),
    ("step1_round1", "q0", "q0r1"),
    ("step1_filter", "q0r1", "q0f"),
    ("step1_round2", "q0f", "q1"),
    ("step2", "q1", "q2"),
    ("step3", "q2", "q3"),
    ("step4_telomere", "q3", "q4"),
    ("finalize", "q4", "q4"),
];

#[cfg(test)]
pub(crate) fn validate_grt_package(bundle_root: &Path) -> Result<ValidatedGrtPackage> {
    validate_grt_package_with_progress(bundle_root, &mut |_, _| {})
}

pub(crate) fn validate_grt_package_with_progress<P>(
    bundle_root: &Path,
    on_progress: &mut P,
) -> Result<ValidatedGrtPackage>
where
    P: FnMut(&'static str, &'static str),
{
    if !bundle_root.is_dir() {
        return grt_err(
            "MISSING_BUNDLE",
            format!("bundle directory does not exist: {}", bundle_root.display()),
        );
    }
    on_progress(
        "validate_grt_required_files",
        "checking required GRT package files",
    );
    for relpath in REQUIRED_FILES {
        required_bundle_file(bundle_root, relpath, relpath)?;
    }

    on_progress(
        "validate_grt_metadata_tables",
        "parsing GRT metadata tables",
    );
    let mut tables = HashMap::new();
    for (relpath, header, minimum, maximum) in TABLE_SPECS {
        tables.insert(
            *relpath,
            read_tsv(bundle_root, relpath, header, *minimum, *maximum)?,
        );
    }

    let package = one_row(&tables, "metadata/package.tsv")?;
    if field(package, "workflow")? != GRT_WORKFLOW
        || field(package, "schema_version")? != GRT_SCHEMA_VERSION
        || field(package, "final_path_schema_version")? != GRT_FINAL_PATH_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "expected gpm_grt_precomputed_v1 schema 1 / Final Path schema 1",
        );
    }
    if !parse_bool(
        field(package, "grt_precompute_enabled")?,
        "package.grt_precompute_enabled",
    )? || !parse_bool(field(package, "recipe_locked")?, "package.recipe_locked")?
    {
        return grt_err(
            "INVALID_VALUE",
            "GRT precompute and locked recipe must both be true",
        );
    }
    if field(package, "sequence_layout")? != "partitioned"
        || !parse_bool(
            field(package, "preassigned_chr")?,
            "package.preassigned_chr",
        )?
    {
        return grt_err(
            "INVALID_VALUE",
            "GRT package requires partitioned, preassigned chromosome data",
        );
    }
    let threshold = parse_f64(
        field(package, "chr_assignment_min_coverage_percent")?,
        "package threshold",
    )?;
    if !(0.0..=100.0).contains(&threshold) {
        return grt_err(
            "INVALID_VALUE",
            "package threshold must be between 0 and 100",
        );
    }
    let reads_qc = parse_bool(
        field(package, "reads_qc_enabled")?,
        "package.reads_qc_enabled",
    )?;

    on_progress(
        "validate_grt_source_fastas",
        "validating reference and dataset FASTA/FAI",
    );
    let dataset_rows = table(&tables, "metadata/datasets.tsv")?;
    let mut dataset_names = HashSet::new();
    for row in &dataset_rows.rows {
        let name = nonempty(row, "dataset_name", "dataset")?;
        if !dataset_names.insert(name.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate dataset_name={name}"));
        }
        let fasta_path = required_bundle_file(
            bundle_root,
            field(row, "fasta_relpath")?,
            &format!("dataset {name} FASTA"),
        )?;
        let fai_path = required_bundle_file(
            bundle_root,
            field(row, "fai_relpath")?,
            &format!("dataset {name} FAI"),
        )?;
        validate_fasta_fai_pair(&fasta_path, &fai_path, &format!("dataset {name}"))?;
        parse_bool(
            field(row, "self_alignment_available")?,
            &format!("dataset {name}.self_alignment_available"),
        )?;
    }

    let reference = one_row(&tables, "metadata/reference.tsv")?;
    let reference_fasta = required_bundle_file(
        bundle_root,
        field(reference, "fasta_relpath")?,
        "reference FASTA",
    )?;
    let reference_fai = required_bundle_file(
        bundle_root,
        field(reference, "fai_relpath")?,
        "reference FAI",
    )?;
    let reference_records = read_fasta(&reference_fasta, "reference FASTA", false)?;
    validate_fasta_fai_records(&reference_records, &reference_fai, "reference")?;
    let sources = source_catalog(
        bundle_root,
        table(&tables, "metadata/source_seq_locator.tsv")?,
    )?;

    let mut assignments: HashMap<(String, String), HashSet<String>> = HashMap::new();
    let mut assignment_baselines: HashMap<(String, String, String), (String, i64)> = HashMap::new();
    let mut assignment_ids = HashSet::new();
    for row in &table(&tables, "metadata/chr_assignments.tsv")?.rows {
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "seq_name")?.to_string(),
        );
        let chromosome = nonempty(row, "assigned_chr_name", "chr assignment chromosome")?;
        let Some(sequence) = sources.get(&key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!(
                    "chr assignment references unknown source {}:{}",
                    key.0, key.1
                ),
            );
        };
        if !reference_records.contains_key(chromosome) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown chromosome {chromosome}"),
            );
        }
        if !assignment_ids.insert((key.clone(), chromosome.to_string())) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate chr assignment {}:{}:{chromosome}", key.0, key.1),
            );
        }
        let source_orientation = orientation(
            field(row, "source_orientation")?,
            "chr assignment source_orientation",
        )?;
        if field(row, "orientation_source")? != "ref_alignment" {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment orientation_source must be ref_alignment",
            );
        }
        if parse_positive_i64(field(row, "seq_length_bp")?, "chr assignment seq_length_bp")?
            as usize
            != sequence.len()
        {
            return grt_err(
                "COUNT_MISMATCH",
                format!(
                    "chr assignment source length differs for {}:{}",
                    key.0, key.1
                ),
            );
        }
        let support = parse_positive_i64(field(row, "support_bp")?, "chr assignment support_bp")?;
        if support as usize > sequence.len() {
            return grt_err(
                "INVALID_COORDINATE",
                "chr assignment support exceeds source length",
            );
        }
        let support_percent = parse_f64(
            field(row, "support_percent")?,
            "chr assignment support_percent",
        )?;
        if !(0.0..=100.0).contains(&support_percent) {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment support_percent must be between 0 and 100",
            );
        }
        let anchor_start = parse_i64(field(row, "anchor_start")?, "chr assignment anchor_start")?;
        assignment_baselines.insert(
            (key.0.clone(), key.1.clone(), chromosome.to_string()),
            (source_orientation.to_string(), anchor_start),
        );
        assignments
            .entry(key)
            .or_default()
            .insert(chromosome.to_string());
    }

    on_progress("validate_grt_recipe", "validating the locked GRT recipe");
    let recipe = one_row(&tables, "metadata/grt_recipe.tsv")?;
    let primary_dataset = nonempty(recipe, "primary_dataset", "recipe primary dataset")?;
    if !dataset_names.contains(primary_dataset) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe primary_dataset is absent from datasets.tsv",
        );
    }
    let support_datasets = json_string_list(
        field(recipe, "support_datasets_json")?,
        "recipe.support_datasets_json",
    )?;
    let mut support_seen = HashSet::new();
    if support_datasets.iter().any(|name| {
        name == primary_dataset
            || !dataset_names.contains(name)
            || !support_seen.insert(name.clone())
    }) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe support datasets must be unique, known, and exclude primary",
        );
    }
    if parse_bool(
        field(recipe, "reads_qc_enabled")?,
        "recipe.reads_qc_enabled",
    )? != reads_qc
    {
        return grt_err(
            "INVALID_VALUE",
            "recipe and package reads_qc_enabled disagree",
        );
    }
    if field(recipe, "q0_relpath")? != "grt/q/q0.fa"
        || field(recipe, "final_q_relpath")? != "grt/q/q4.fa"
    {
        return grt_err(
            "INVALID_VALUE",
            "recipe q paths must identify q0.fa and q4.fa",
        );
    }

    let mut recipe_datasets = support_datasets.iter().cloned().collect::<HashSet<_>>();
    recipe_datasets.insert(primary_dataset.to_string());
    let mut role_keys = HashSet::new();
    for row in &table(&tables, "metadata/grt_contig_roles.tsv")?.rows {
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("contig role references unknown source {}:{}", key.0, key.1),
            );
        }
        if !role_keys.insert(key) {
            return grt_err("DUPLICATE_ID", "duplicate GRT contig role");
        }
        for name in ["q_eligible", "donor_eligible", "tel_donor_eligible"] {
            parse_bool(field(row, name)?, &format!("contig role {name}"))?;
        }
    }
    let expected_role_keys = sources
        .keys()
        .filter(|(dataset, _)| recipe_datasets.contains(dataset))
        .cloned()
        .collect::<HashSet<_>>();
    if role_keys != expected_role_keys {
        return grt_err(
            "BROKEN_REFERENCE",
            "contig roles must cover the locked recipe source catalog exactly once",
        );
    }

    on_progress(
        "validate_grt_q_artifacts",
        "validating q0-q4 artifacts and segment reconstruction",
    );
    let mut q_records = HashMap::<String, BTreeMap<String, String>>::new();
    let mut q_artifact_hashes = HashMap::<String, String>::new();
    for q_version in ["q0", "q0r1", "q0f", "q1", "q2", "q3", "q4"] {
        let relpath = format!("grt/q/{q_version}.fa");
        let path = required_bundle_file(bundle_root, &relpath, &relpath)?;
        q_artifact_hashes.insert(q_version.to_string(), sha256_file(&path)?);
        q_records.insert(q_version.to_string(), read_fasta(&path, &relpath, false)?);
    }

    let mut q_segment_ids = HashSet::new();
    let mut q_segment_evidence = HashMap::<String, Vec<String>>::new();
    let mut q_segments_by_record =
        HashMap::<(String, String), Vec<(i64, i64, String, String)>>::new();
    for row in &table(&tables, "metadata/grt_q_segments.tsv")?.rows {
        let q_version = nonempty(row, "q_version", "q segment q_version")?;
        let chr_name = nonempty(row, "chr", "q segment chr")?;
        let segment_id = nonempty(row, "segment_id", "q segment id")?;
        if !q_records.contains_key(q_version) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segment {segment_id} references unknown q version"),
            );
        }
        if !q_segment_ids.insert(segment_id.to_string()) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate q segment_id={segment_id}"),
            );
        }
        let (q_start, q_end) = interval(
            row,
            "q_start",
            "q_end",
            &format!("q segment {segment_id}.q"),
        )?;
        let evidence_ids = json_string_list(
            field(row, "evidence_ids_json")?,
            &format!("q segment {segment_id}.evidence"),
        )?;
        let sequence = match field(row, "segment_kind")? {
            "gap" => {
                if [
                    "dataset_name",
                    "contig_name",
                    "source_start",
                    "source_end",
                    "orientation",
                    "source_card_key",
                ]
                .iter()
                .any(|key| !field(row, key).unwrap_or("").is_empty())
                    || !evidence_ids.is_empty()
                {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("q gap segment {segment_id} cannot carry source/evidence"),
                    );
                }
                "N".repeat((q_end - q_start + 1) as usize)
            }
            "source" => {
                let key = (
                    field(row, "dataset_name")?.to_string(),
                    field(row, "contig_name")?.to_string(),
                );
                let Some(source) = sources.get(&key) else {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("q segment {segment_id} references unknown source"),
                    );
                };
                let (start, end) = interval(
                    row,
                    "source_start",
                    "source_end",
                    &format!("q segment {segment_id}.source"),
                )?;
                if end as usize > source.len() || q_end - q_start != end - start {
                    return grt_err(
                        "INVALID_COORDINATE",
                        format!("q segment {segment_id} q/source lengths differ"),
                    );
                }
                let orientation = orientation(
                    field(row, "orientation")?,
                    &format!("q segment {segment_id}"),
                )?;
                if field(row, "source_card_key")?.is_empty() || evidence_ids.is_empty() {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("q segment {segment_id} lacks source card/evidence"),
                    );
                }
                if q_version == "q0" {
                    if !assignments
                        .get(&key)
                        .is_some_and(|chrs| chrs.contains(chr_name))
                    {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} source is not assigned to {chr_name}"),
                        );
                    }
                    let Some(baseline) = assignment_baselines.get(&(
                        key.0.clone(),
                        key.1.clone(),
                        chr_name.to_string(),
                    )) else {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} lacks an assignment baseline"),
                        );
                    };
                    if orientation != baseline.0.as_str() {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!(
                                "q0 segment {segment_id} orientation disagrees with chr_assignments.tsv"
                            ),
                        );
                    }
                    let expected = format!("{}:{}:{chr_name}:normal", key.0, key.1);
                    if field(row, "source_card_key")? != expected {
                        return grt_err(
                            "BROKEN_REFERENCE",
                            format!("q0 segment {segment_id} has non-canonical source card key"),
                        );
                    }
                }
                orient_sequence(&source[(start - 1) as usize..end as usize], orientation)
            }
            other => {
                return grt_err(
                    "INVALID_VALUE",
                    format!("q segment {segment_id} has invalid segment_kind={other}"),
                );
            }
        };
        q_segment_evidence.insert(segment_id.to_string(), evidence_ids);
        q_segments_by_record
            .entry((q_version.to_string(), chr_name.to_string()))
            .or_default()
            .push((q_start, q_end, sequence, segment_id.to_string()));
    }
    for ((q_version, chr_name), segments) in &mut q_segments_by_record {
        let Some(expected) = q_records
            .get(q_version)
            .and_then(|records| records.get(chr_name))
        else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segments reference missing {q_version}:{chr_name}"),
            );
        };
        segments.sort_by_key(|value| value.0);
        let mut next = 1_i64;
        let mut rebuilt = String::new();
        for (start, end, sequence, segment_id) in segments {
            if *start != next {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("q segment {segment_id} is not contiguous"),
                );
            }
            next = *end + 1;
            rebuilt.push_str(sequence);
        }
        if &rebuilt != expected {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("q segments do not reconstruct {q_version}:{chr_name}"),
            );
        }
    }
    let q0_segment_records = q_segments_by_record
        .keys()
        .filter(|(version, _)| version == "q0")
        .map(|(_, chr)| chr.clone())
        .collect::<HashSet<_>>();
    let q0_record_names = q_records["q0"].keys().cloned().collect::<HashSet<_>>();
    if q0_segment_records != q0_record_names {
        return grt_err(
            "BROKEN_REFERENCE",
            "q0 segment mapping does not cover every q0 record",
        );
    }

    on_progress(
        "validate_grt_donor_artifacts",
        "validating D0/Dtel donor artifacts and member manifests",
    );
    let donor_sets_table = table(&tables, "metadata/grt_donor_sets.tsv")?;
    let mut donor_sets = HashMap::<String, &TsvRow>::new();
    let mut donor_kind_count = HashMap::<String, usize>::new();
    let mut donor_fastas = HashMap::<String, BTreeMap<String, String>>::new();
    for row in &donor_sets_table.rows {
        let id = nonempty(row, "donor_set_id", "donor set id")?;
        if donor_sets.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate donor_set_id={id}"));
        }
        let kind = field(row, "donor_kind")?;
        if !matches!(kind, "ordinary" | "telomere") {
            return grt_err("INVALID_VALUE", format!("unknown donor_kind={kind}"));
        }
        *donor_kind_count.entry(kind.to_string()).or_default() += 1;
        parse_nonnegative_i64(
            field(row, "member_count")?,
            &format!("donor set {id}.member_count"),
        )?;
        let fasta_path = validate_artifact(
            bundle_root,
            field(row, "fasta_relpath")?,
            field(row, "fasta_sha256")?,
            &format!("donor set {id} FASTA"),
        )?;
        donor_fastas.insert(
            id.to_string(),
            read_fasta(&fasta_path, &format!("donor set {id} FASTA"), true)?,
        );
        required_bundle_file(
            bundle_root,
            field(row, "manifest_relpath")?,
            &format!("donor set {id} manifest"),
        )?;
    }
    if donor_kind_count.get("ordinary") != Some(&1)
        || donor_kind_count.get("telomere") != Some(&1)
        || donor_sets.len() != 2
    {
        return grt_err(
            "INVALID_VALUE",
            "contract requires exactly one ordinary and one telomere donor set",
        );
    }
    for (field_name, kind) in [
        ("donor_set_id", "ordinary"),
        ("tel_donor_set_id", "telomere"),
    ] {
        let id = field(recipe, field_name)?;
        if donor_sets
            .get(id)
            .and_then(|row| row.get("donor_kind"))
            .map(String::as_str)
            != Some(kind)
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("recipe {field_name} must reference the {kind} donor set"),
            );
        }
    }

    let mut members = HashMap::<(String, String), &TsvRow>::new();
    let mut member_rows_by_set = HashMap::<String, Vec<&TsvRow>>::new();
    for row in &table(&tables, "metadata/grt_donor_members.tsv")?.rows {
        let set_id = field(row, "donor_set_id")?.to_string();
        let member_id = nonempty(row, "member_id", "donor member id")?.to_string();
        if !donor_sets.contains_key(&set_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("donor member references unknown donor_set_id={set_id}"),
            );
        }
        if members
            .insert((set_id.clone(), member_id.clone()), row)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate donor member {set_id}:{member_id}"),
            );
        }
        let source_key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        let Some(source) = sources.get(&source_key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!(
                    "donor member references unknown source {}:{}",
                    source_key.0, source_key.1
                ),
            );
        };
        let (start, end) = interval(
            row,
            "source_start",
            "source_end",
            &format!("donor member {member_id}"),
        )?;
        if end as usize > source.len() {
            return grt_err(
                "INVALID_COORDINATE",
                format!("donor member {member_id} exceeds source length"),
            );
        }
        let orient = orientation(
            field(row, "orientation")?,
            &format!("donor member {member_id}"),
        )?;
        let sequence = orient_sequence(&source[(start - 1) as usize..end as usize], orient);
        let sequence_sha = field(row, "sequence_sha256")?;
        validate_sha256(
            sequence_sha,
            &format!("donor member {member_id}.sequence_sha256"),
        )?;
        if sha256_bytes(sequence.as_bytes()) != sequence_sha {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("donor member {member_id} sequence hash differs from source slice"),
            );
        }
        let fasta_name = field(row, "fasta_record_name")?;
        if donor_fastas
            .get(&set_id)
            .and_then(|records| records.get(fasta_name))
            != Some(&sequence)
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("donor member {member_id} FASTA differs from source slice"),
            );
        }
        member_rows_by_set.entry(set_id).or_default().push(row);
    }
    for (set_id, donor_set) in &donor_sets {
        let expected =
            parse_nonnegative_i64(field(donor_set, "member_count")?, "donor member count")?
                as usize;
        let rows = member_rows_by_set.get(set_id).cloned().unwrap_or_default();
        if rows.len() != expected || donor_fastas.get(set_id).map(BTreeMap::len) != Some(expected) {
            return grt_err(
                "COUNT_MISMATCH",
                format!("donor set {set_id} member_count differs from registry/FASTA"),
            );
        }
        let manifest = read_tsv(
            bundle_root,
            field(donor_set, "manifest_relpath")?,
            DONOR_MEMBERS_HEADER,
            0,
            None,
        )?;
        if manifest.rows != rows.into_iter().cloned().collect::<Vec<_>>() {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("donor set {set_id} manifest differs from member registry"),
            );
        }
    }

    on_progress(
        "validate_grt_evidence",
        "validating evidence, usage, and event links",
    );
    let evidence_table = table(&tables, "metadata/grt_evidence_registry.tsv")?;
    let mut evidence = HashMap::<String, &TsvRow>::new();
    for row in &evidence_table.rows {
        let id = nonempty(row, "evidence_id", "evidence id")?;
        if evidence.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate evidence_id={id}"));
        }
        enum_value(
            field(row, "stage")?,
            &[
                "assignment",
                "step1_round1",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
                "candidate_validation",
                "display_pairwise",
            ],
            &format!("evidence {id}.stage"),
        )?;
        enum_value(
            field(row, "status")?,
            &[
                "candidate",
                "accepted",
                "superseded",
                "rejected",
                "conflicted",
                "background",
            ],
            &format!("evidence {id}.status"),
        )?;
        enum_value(
            field(row, "coordinate_system")?,
            &[
                "paf_0_based_half_open",
                "mummer_1_based_closed",
                "app_1_based_closed",
            ],
            &format!("evidence {id}.coordinate_system"),
        )?;
        enum_value(
            field(row, "projection_status")?,
            &["native", "projected"],
            &format!("evidence {id}.projection_status"),
        )?;
        parse_json_object(
            field(row, "parameters_json")?,
            &format!("evidence {id}.parameters_json"),
        )?;
        let source_values = [
            field(row, "source_dataset")?,
            field(row, "source_contig")?,
            field(row, "source_start")?,
            field(row, "source_end")?,
        ];
        if source_values.iter().any(|value| !value.is_empty()) {
            if source_values.iter().any(|value| value.is_empty()) {
                return grt_err(
                    "INVALID_VALUE",
                    format!("evidence {id} has partial source identity"),
                );
            }
            let key = (source_values[0].to_string(), source_values[1].to_string());
            let Some(source) = sources.get(&key) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("evidence {id} references unknown source"),
                );
            };
            let (_start, end) = interval(
                row,
                "source_start",
                "source_end",
                &format!("evidence {id}.source"),
            )?;
            if end as usize > source.len() {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("evidence {id} source exceeds source length"),
                );
            }
            orientation(field(row, "orientation")?, &format!("evidence {id}"))?;
        }
        let target_start = field(row, "target_start")?;
        let target_end = field(row, "target_end")?;
        if !target_start.is_empty() || !target_end.is_empty() {
            if target_start.is_empty()
                || target_end.is_empty()
                || field(row, "target_chr")?.is_empty()
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("evidence {id} has partial target interval"),
                );
            }
            interval(
                row,
                "target_start",
                "target_end",
                &format!("evidence {id}.target"),
            )?;
        }
        for (path_field, hash_field) in [
            ("query_artifact_relpath", "query_sha256"),
            ("target_artifact_relpath", "target_sha256"),
        ] {
            let relpath = field(row, path_field)?;
            let hash = field(row, hash_field)?;
            if !relpath.is_empty() || !hash.is_empty() {
                if relpath.is_empty() || hash.is_empty() {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("evidence {id} has partial artifact identity"),
                    );
                }
                validate_artifact(
                    bundle_root,
                    relpath,
                    hash,
                    &format!("evidence {id}.{path_field}"),
                )?;
            }
        }
        validate_artifact(
            bundle_root,
            field(row, "raw_artifact_relpath")?,
            field(row, "raw_artifact_sha256")?,
            &format!("evidence {id}.raw_artifact"),
        )?;
        let q_version = field(row, "q_version")?;
        if !q_version.is_empty() {
            if q_artifact_hashes.get(q_version).map(String::as_str)
                != Some(field(row, "q_source_sha256")?)
            {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("evidence {id} q source hash mismatch"),
                );
            }
        } else if !field(row, "q_source_sha256")?.is_empty() {
            return grt_err(
                "INVALID_VALUE",
                format!("evidence {id} has q hash without q_version"),
            );
        }
        let donor_set_id = field(row, "donor_set_id")?;
        if !donor_set_id.is_empty() {
            let Some(donor_set) = donor_sets.get(donor_set_id) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("evidence {id} references unknown donor set"),
                );
            };
            if field(row, "target_sha256")? != field(donor_set, "fasta_sha256")? {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("evidence {id} target hash differs from donor set"),
                );
            }
        }
    }
    for (segment_id, ids) in &q_segment_evidence {
        if ids.iter().any(|id| !evidence.contains_key(id)) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("q segment {segment_id} references unknown evidence"),
            );
        }
    }

    let usage_table = table(&tables, "metadata/grt_donor_usage.tsv")?;
    let mut usage = HashMap::<String, &TsvRow>::new();
    for row in &usage_table.rows {
        let id = nonempty(row, "usage_id", "usage id")?;
        if usage.insert(id.to_string(), row).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate usage_id={id}"));
        }
        let member_key = (
            field(row, "donor_set_id")?.to_string(),
            field(row, "member_id")?.to_string(),
        );
        let Some(member) = members.get(&member_key) else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} references unknown donor member"),
            );
        };
        enum_value(
            field(row, "status")?,
            &[
                "available",
                "candidate",
                "accepted",
                "consumed",
                "superseded",
                "rejected",
                "conflicted",
            ],
            &format!("usage {id}.status"),
        )?;
        enum_value(
            field(row, "stage")?,
            &[
                "step1_round1",
                "step1_filter",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
            ],
            &format!("usage {id}.stage"),
        )?;
        let (start, end) = interval(
            row,
            "source_start",
            "source_end",
            &format!("usage {id}.source"),
        )?;
        if field(row, "source_dataset")? != field(member, "dataset_name")?
            || field(row, "source_contig")? != field(member, "contig_name")?
            || start < parse_positive_i64(field(member, "source_start")?, "member start")?
            || end > parse_positive_i64(field(member, "source_end")?, "member end")?
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} source differs from donor member"),
            );
        }
        if matches!(field(row, "status")?, "accepted" | "consumed")
            && field(row, "event_id")?.is_empty()
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {id} accepted/consumed row lacks event"),
            );
        }
    }

    let events = read_jsonl(bundle_root, "metadata/grt_events.jsonl")?;
    let mut event_index = HashMap::<String, &Value>::new();
    for event in &events {
        let object = event
            .as_object()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "GRT event must be an object"))?;
        for field_name in [
            "run_id",
            "event_id",
            "stage",
            "chr",
            "object_id",
            "action",
            "status",
            "reason",
            "q_before",
            "q_after",
            "source",
            "evidence_ids",
            "usage_ids",
            "source_card_key",
            "final_path_segment_id",
        ] {
            if !object.contains_key(field_name) {
                return grt_err(
                    "INVALID_JSON",
                    format!("event is missing required field {field_name}"),
                );
            }
        }
        let id = json_nonempty_str(object, "event_id", "event")?;
        if event_index.insert(id.to_string(), event).is_some() {
            return grt_err("DUPLICATE_ID", format!("duplicate event_id={id}"));
        }
        enum_value(
            json_str(object, "stage", id)?,
            &[
                "step1_round1",
                "step1_filter",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
            ],
            &format!("event {id}.stage"),
        )?;
        enum_value(
            json_str(object, "status", id)?,
            &[
                "accepted",
                "superseded",
                "rejected",
                "conflicted",
                "unresolved",
            ],
            &format!("event {id}.status"),
        )?;
        enum_value(
            json_str(object, "action", id)?,
            &[
                "fill",
                "filter_component",
                "patch",
                "delete",
                "replace",
                "correct_boundary",
                "refill",
                "extend_telomere",
            ],
            &format!("event {id}.action"),
        )?;
        for link_field in ["evidence_ids", "usage_ids"] {
            let ids = json_value_string_list(
                object.get(link_field).unwrap(),
                &format!("event {id}.{link_field}"),
            )?;
            let known = if link_field == "evidence_ids" {
                ids.iter().all(|item| evidence.contains_key(item))
            } else {
                ids.iter().all(|item| usage.contains_key(item))
            };
            if !known {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {id} references unknown {link_field}"),
                );
            }
        }
        for q_field in ["q_before", "q_after"] {
            let q = object
                .get(q_field)
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("event {id}.{q_field} has invalid shape"),
                    )
                })?;
            let version = json_nonempty_str(q, "version", &format!("event {id}.{q_field}"))?;
            let start = json_positive_i64(q, "start", &format!("event {id}.{q_field}"))?;
            let end = json_positive_i64(q, "end", &format!("event {id}.{q_field}"))?;
            if start > end {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("event {id}.{q_field} has reversed interval"),
                );
            }
            let hash = json_nonempty_str(q, "sha256", &format!("event {id}.{q_field}"))?;
            validate_sha256(hash, &format!("event {id}.{q_field}.sha256"))?;
            if q_artifact_hashes.get(version).map(String::as_str) != Some(hash) {
                return grt_err(
                    "CHECKSUM_MISMATCH",
                    format!("event {id}.{q_field} q hash mismatch"),
                );
            }
            let chr_name = json_str(object, "chr", id)?;
            if q_records
                .get(version)
                .and_then(|records| records.get(chr_name))
                .map(String::len)
                .is_none_or(|length| end as usize > length)
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("event {id}.{q_field} exceeds q chromosome"),
                );
            }
        }
        if let Some(source) = object.get("source").and_then(Value::as_object) {
            if !source.is_empty() {
                let key = (
                    json_nonempty_str(source, "dataset", id)?.to_string(),
                    json_nonempty_str(source, "contig", id)?.to_string(),
                );
                let Some(sequence) = sources.get(&key) else {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("event {id} references unknown source"),
                    );
                };
                let start = json_positive_i64(source, "start", id)?;
                let end = json_positive_i64(source, "end", id)?;
                if start > end || end as usize > sequence.len() {
                    return grt_err(
                        "INVALID_COORDINATE",
                        format!("event {id} has invalid source interval"),
                    );
                }
                orientation(
                    json_str(source, "orientation", id)?,
                    &format!("event {id}.source"),
                )?;
                enum_value(
                    json_str(source, "original_assignment", id)?,
                    &["assigned", "unplaced", "cross_chr"],
                    &format!("event {id}.source.original_assignment"),
                )?;
            }
        } else if object.get("source") != Some(&Value::Null) {
            return grt_err(
                "INVALID_JSON",
                format!("event {id}.source has invalid shape"),
            );
        }
    }
    for (usage_id, row) in &usage {
        let event_id = field(row, "event_id")?;
        if !event_id.is_empty() && !event_index.contains_key(event_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {usage_id} references unknown event {event_id}"),
            );
        }
    }

    on_progress(
        "validate_grt_final_path",
        "rebuilding and validating the Final Path",
    );
    validate_stage_status(
        bundle_root,
        table(&tables, "metadata/grt_stage_status.tsv")?,
        &q_artifact_hashes,
        &donor_sets,
    )?;
    validate_tool_versions(table(&tables, "metadata/grt_tool_versions.tsv")?)?;

    let final_path = read_json(bundle_root, "metadata/grt_final_path.json")?;
    let final_object = final_path
        .as_object()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", "grt_final_path.json must contain an object"))?;
    if json_str(final_object, "workflow", "Final Path")? != GRT_WORKFLOW
        || json_str(final_object, "schema_version", "Final Path")? != GRT_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "grt_final_path.json has unsupported workflow/schema",
        );
    }
    if json_str(final_object, "q4_relpath", "Final Path")? != field(recipe, "final_q_relpath")? {
        return grt_err(
            "BROKEN_REFERENCE",
            "Final Path q4_relpath differs from recipe",
        );
    }
    let chromosomes = final_object
        .get("chromosomes")
        .and_then(Value::as_array)
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "Final Path chromosomes must be a non-empty array",
            )
        })?;
    let mut final_chr_names = HashSet::new();
    let mut final_segments = HashMap::<String, (&Value, String)>::new();
    for chromosome in chromosomes {
        let chr = chromosome
            .as_object()
            .ok_or_else(|| grt_anyhow("INVALID_JSON", "Final Path chromosome must be an object"))?;
        let chr_name = json_nonempty_str(chr, "chr", "Final Path chromosome")?;
        if !final_chr_names.insert(chr_name.to_string()) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate Final Path chromosome {chr_name}"),
            );
        }
        let expected_q4 = q_records["q4"].get(chr_name).ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("Final Path references unknown q4 chromosome {chr_name}"),
            )
        })?;
        if json_positive_i64(chr, "q4_length", chr_name)? as usize != expected_q4.len() {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("Final Path {chr_name} q4 length mismatch"),
            );
        }
        if json_nonempty_str(chr, "q4_sha256", chr_name)? != sha256_bytes(expected_q4.as_bytes()) {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("Final Path {chr_name} q4 sequence hash mismatch"),
            );
        }
        let segments = chr
            .get("segments")
            .and_then(Value::as_array)
            .filter(|rows| !rows.is_empty())
            .ok_or_else(|| {
                grt_anyhow(
                    "INVALID_JSON",
                    format!("Final Path {chr_name}.segments must be non-empty"),
                )
            })?;
        let mut rebuilt = String::new();
        for segment in segments {
            let segment_object = segment.as_object().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "Final Path segment must be an object")
            })?;
            let segment_id = json_nonempty_str(segment_object, "segment_id", "Final Path segment")?;
            if final_segments
                .insert(segment_id.to_string(), (segment, chr_name.to_string()))
                .is_some()
            {
                return grt_err(
                    "DUPLICATE_ID",
                    format!("duplicate Final Path segment_id={segment_id}"),
                );
            }
            let kind = json_str(segment_object, "kind", segment_id)?;
            enum_value(
                kind,
                &["source", "patch", "correction", "telomere", "gap"],
                &format!("segment {segment_id}.kind"),
            )?;
            let length = json_positive_i64(segment_object, "length", segment_id)? as usize;
            let evidence_ids = json_value_string_list(
                segment_object.get("evidence_ids").ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("segment {segment_id} lacks evidence_ids"),
                    )
                })?,
                &format!("segment {segment_id}.evidence_ids"),
            )?;
            if evidence_ids.iter().any(|id| !evidence.contains_key(id)) {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("segment {segment_id} references unknown evidence"),
                );
            }
            if kind == "gap" {
                if segment_object
                    .get("source")
                    .is_some_and(|value| !value.is_null())
                    || segment_object
                        .get("event_id")
                        .is_some_and(|value| !value.is_null())
                {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("gap segment {segment_id} cannot have source/event"),
                    );
                }
                rebuilt.push_str(&"N".repeat(length));
                continue;
            }
            let orient = orientation(
                json_str(segment_object, "orientation", segment_id)?,
                &format!("segment {segment_id}"),
            )?;
            let source = segment_object
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("segment {segment_id}.source has invalid shape"),
                    )
                })?;
            let key = (
                json_nonempty_str(source, "dataset", segment_id)?.to_string(),
                json_nonempty_str(source, "contig", segment_id)?.to_string(),
            );
            let Some(source_sequence) = sources.get(&key) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("segment {segment_id} references unknown source"),
                );
            };
            let start = json_positive_i64(source, "start", segment_id)?;
            let end = json_positive_i64(source, "end", segment_id)?;
            if start > end
                || end as usize > source_sequence.len()
                || end - start + 1 != length as i64
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("segment {segment_id} source interval does not match length"),
                );
            }
            if orientation(
                json_str(source, "orientation", segment_id)?,
                &format!("segment {segment_id}.source"),
            )? != orient
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("segment {segment_id} orientation differs from source"),
                );
            }
            let event_id = segment_object
                .get("event_id")
                .and_then(Value::as_str)
                .unwrap_or("");
            if !event_id.is_empty() {
                let event = event_index.get(event_id).ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("segment {segment_id} references unknown event"),
                    )
                })?;
                if event.get("status").and_then(Value::as_str) != Some("accepted") {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("segment {segment_id} references non-accepted event"),
                    );
                }
            } else if matches!(kind, "patch" | "correction" | "telomere") {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("GRT segment {segment_id} lacks accepted event"),
                );
            }
            rebuilt.push_str(&orient_sequence(
                &source_sequence[(start - 1) as usize..end as usize],
                orient,
            ));
        }
        if &rebuilt != expected_q4 {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("Final Path segments do not reconstruct q4 chromosome {chr_name}"),
            );
        }
    }
    if final_chr_names != q_records["q4"].keys().cloned().collect::<HashSet<_>>() {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "Final Path chromosome set differs from q4 FASTA",
        );
    }

    for (event_id, event) in &event_index {
        let status = event.get("status").and_then(Value::as_str).unwrap_or("");
        let action = event.get("action").and_then(Value::as_str).unwrap_or("");
        let segment_id = event
            .get("final_path_segment_id")
            .and_then(Value::as_str)
            .unwrap_or("");
        let path_producing = status == "accepted"
            && matches!(
                action,
                "fill" | "patch" | "replace" | "correct_boundary" | "refill" | "extend_telomere"
            );
        if path_producing && segment_id.is_empty() {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("accepted path-producing event {event_id} lacks Final Path segment"),
            );
        }
        if !segment_id.is_empty() {
            let Some((segment, _)) = final_segments.get(segment_id) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {event_id} references unknown Final Path segment"),
                );
            };
            if segment.get("event_id").and_then(Value::as_str) != Some(event_id) {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("event {event_id} and Final Path segment are not bidirectional"),
                );
            }
        }
    }
    for (usage_id, row) in &usage {
        let segment_id = field(row, "final_path_segment_id")?;
        if !segment_id.is_empty() && !final_segments.contains_key(segment_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("usage {usage_id} references unknown Final Path segment"),
            );
        }
    }

    on_progress(
        "validate_grt_trace_integrity",
        "validating source-card trace integrity",
    );
    validate_source_cards(
        table(&tables, "metadata/grt_used_contigs.tsv")?,
        &sources,
        &assignment_baselines,
        &evidence,
        &event_index,
        &final_segments,
    )?;
    validate_gap_attempts(
        table(&tables, "metadata/grt_gap_attempts.tsv")?,
        &event_index,
    )?;

    Ok(ValidatedGrtPackage {
        tables,
        events,
        final_path,
        q0_artifact_sha256: q_artifact_hashes.remove("q0").unwrap(),
        q4_artifact_sha256: q_artifact_hashes.remove("q4").unwrap(),
    })
}

/// Validate the delivery contract selected by metadata/package.tsv.  Server
/// workdirs keep using the exhaustive GRT closure validator; App delivery
/// archives use the projected contract and therefore do not need Server-only
/// q-stage, donor, evidence, cache, or checkpoint artifacts.
pub(crate) fn validate_grt_delivery_package_with_progress<P>(
    bundle_root: &Path,
    on_progress: &mut P,
) -> Result<ValidatedGrtPackage>
where
    P: FnMut(&'static str, &'static str),
{
    let workflow = fs::read_to_string(bundle_root.join("metadata/package.tsv"))
        .ok()
        .and_then(|text| {
            let mut lines = text.lines();
            let header = lines.next()?.split('\t').collect::<Vec<_>>();
            let workflow_index = header.iter().position(|column| *column == "workflow")?;
            let row = lines
                .find(|line| !line.trim().is_empty())?
                .split('\t')
                .collect::<Vec<_>>();
            row.get(workflow_index).map(|value| value.to_string())
        });
    if workflow.as_deref() == Some(GRT_APP_WORKFLOW) {
        validate_grt_app_package_with_progress(bundle_root, on_progress)
    } else {
        validate_grt_package_with_progress(bundle_root, on_progress)
    }
}

fn validate_grt_app_package_with_progress<P>(
    bundle_root: &Path,
    on_progress: &mut P,
) -> Result<ValidatedGrtPackage>
where
    P: FnMut(&'static str, &'static str),
{
    if !bundle_root.is_dir() {
        return grt_err(
            "MISSING_BUNDLE",
            format!("bundle directory does not exist: {}", bundle_root.display()),
        );
    }
    on_progress(
        "validate_grt_app_required_files",
        "checking minimal App delivery files",
    );
    let core_specs: &[(&str, &[&str], usize, Option<usize>)] = &[
        ("metadata/package.tsv", PACKAGE_HEADER, 1, Some(1)),
        ("metadata/reference.tsv", REFERENCE_HEADER, 1, Some(1)),
        ("metadata/datasets.tsv", DATASETS_HEADER, 1, None),
        (
            "metadata/source_seq_locator.tsv",
            SOURCE_LOCATOR_HEADER,
            1,
            None,
        ),
        (
            "metadata/chr_assignments.tsv",
            CHR_ASSIGNMENTS_HEADER,
            1,
            None,
        ),
        ("metadata/grt_recipe.tsv", RECIPE_HEADER, 1, Some(1)),
        (
            "metadata/grt_used_contigs.tsv",
            USED_CONTIGS_HEADER,
            0,
            None,
        ),
    ];
    let mut tables = HashMap::new();
    for (relpath, header, minimum, maximum) in core_specs {
        tables.insert(
            *relpath,
            read_tsv(bundle_root, relpath, header, *minimum, *maximum)?,
        );
    }
    let package = one_row(&tables, "metadata/package.tsv")?;
    if field(package, "workflow")? != GRT_APP_WORKFLOW
        || field(package, "schema_version")? != GRT_SCHEMA_VERSION
        || field(package, "final_path_schema_version")? != GRT_FINAL_PATH_SCHEMA_VERSION
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "expected gpm_grt_app_precomputed_v1 schema 1 / Final Path schema 1",
        );
    }
    if !parse_bool(
        field(package, "grt_precompute_enabled")?,
        "package.grt_precompute_enabled",
    )? || !parse_bool(field(package, "recipe_locked")?, "package.recipe_locked")?
    {
        return grt_err(
            "INVALID_VALUE",
            "App package must retain a precomputed and locked GRT result",
        );
    }
    if field(package, "sequence_layout")? != "partitioned"
        || !parse_bool(
            field(package, "preassigned_chr")?,
            "package.preassigned_chr",
        )?
    {
        return grt_err(
            "INVALID_VALUE",
            "App package requires partitioned, preassigned chromosome data",
        );
    }
    let package_mode = field(package, "package_mode")?;
    if !matches!(package_mode, "full" | "no_fasta") {
        return grt_err(
            "INVALID_VALUE",
            format!("unsupported App package_mode={package_mode}"),
        );
    }
    let threshold = parse_f64(
        field(package, "chr_assignment_min_coverage_percent")?,
        "package threshold",
    )?;
    if !(0.0..=100.0).contains(&threshold) {
        return grt_err(
            "INVALID_VALUE",
            "package threshold must be between 0 and 100",
        );
    }
    let reads_qc = parse_bool(
        field(package, "reads_qc_enabled")?,
        "package.reads_qc_enabled",
    )?;

    let manifest = read_json(bundle_root, "metadata/grt_app_manifest.json")?;
    let manifest_object = manifest.as_object().ok_or_else(|| {
        grt_anyhow(
            "INVALID_JSON",
            "metadata/grt_app_manifest.json must be an object",
        )
    })?;
    if json_str(manifest_object, "workflow", "App manifest")? != GRT_APP_WORKFLOW
        || json_str(manifest_object, "schema_version", "App manifest")? != GRT_SCHEMA_VERSION
        || json_str(manifest_object, "package_kind", "App manifest")? != package_mode
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "App manifest and package metadata disagree",
        );
    }
    let fasta_available = manifest_object
        .get("fasta_available")
        .and_then(Value::as_bool)
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App manifest.fasta_available must be boolean",
            )
        })?;
    if fasta_available != (package_mode == "full") {
        return grt_err(
            "INVALID_VALUE",
            "App manifest FASTA mode disagrees with package mode",
        );
    }
    let q4_relpath = json_str(manifest_object, "q4_relpath", "App manifest")?;
    if q4_relpath != "grt/q/q4.fa" {
        return grt_err(
            "INVALID_PATH",
            "App manifest q4_relpath must be grt/q/q4.fa",
        );
    }
    let q4_artifact_sha256 =
        json_nonempty_str(manifest_object, "q4_artifact_sha256", "App manifest")?;
    validate_sha256(q4_artifact_sha256, "App manifest.q4_artifact_sha256")?;
    validate_sha256(
        json_nonempty_str(manifest_object, "final_path_sha256", "App manifest")?,
        "App manifest.final_path_sha256",
    )?;

    on_progress(
        "validate_grt_app_fai",
        "validating source and reference FAI lengths",
    );
    let datasets = table(&tables, "metadata/datasets.tsv")?;
    let mut dataset_names = HashSet::new();
    let mut dataset_fai = HashMap::<String, BTreeMap<String, usize>>::new();
    for row in &datasets.rows {
        let dataset = nonempty(row, "dataset_name", "dataset")?;
        if !dataset_names.insert(dataset.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate dataset_name={dataset}"));
        }
        let fai_path = required_bundle_file(
            bundle_root,
            field(row, "fai_relpath")?,
            &format!("dataset {dataset} FAI"),
        )?;
        dataset_fai.insert(
            dataset.to_string(),
            read_fai_lengths(&fai_path, &format!("dataset {dataset}"))?,
        );
        parse_bool(
            field(row, "self_alignment_available")?,
            &format!("dataset {dataset}.self_alignment_available"),
        )?;
    }
    let reference = one_row(&tables, "metadata/reference.tsv")?;
    let reference_fai = required_bundle_file(
        bundle_root,
        field(reference, "fai_relpath")?,
        "reference FAI",
    )?;
    let reference_records = read_fai_lengths(&reference_fai, "reference")?;
    let sources = source_length_catalog(
        bundle_root,
        table(&tables, "metadata/source_seq_locator.tsv")?,
        &dataset_fai,
    )?;

    let mut assignment_baselines = HashMap::<(String, String, String), (String, i64)>::new();
    let mut assignment_ids = HashSet::new();
    for row in &table(&tables, "metadata/chr_assignments.tsv")?.rows {
        let dataset = field(row, "dataset_name")?.to_string();
        let seq = field(row, "seq_name")?.to_string();
        let key = (dataset.clone(), seq.clone());
        let source_length = sources.get(&key).ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown source {dataset}:{seq}"),
            )
        })?;
        let chr = nonempty(row, "assigned_chr_name", "chr assignment chromosome")?;
        if !reference_records.contains_key(chr) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("chr assignment references unknown chromosome {chr}"),
            );
        }
        if !assignment_ids.insert((key.clone(), chr.to_string())) {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate chr assignment {dataset}:{seq}:{chr}"),
            );
        }
        let orient = orientation(
            field(row, "source_orientation")?,
            "chr assignment source_orientation",
        )?;
        if field(row, "orientation_source")? != "ref_alignment" {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment orientation_source must be ref_alignment",
            );
        }
        if parse_positive_i64(field(row, "seq_length_bp")?, "chr assignment seq_length_bp")?
            as usize
            != *source_length
        {
            return grt_err(
                "COUNT_MISMATCH",
                format!("chr assignment source length differs for {dataset}:{seq}"),
            );
        }
        let support =
            parse_positive_i64(field(row, "support_bp")?, "chr assignment support_bp")? as usize;
        if support > *source_length {
            return grt_err(
                "INVALID_COORDINATE",
                "chr assignment support exceeds source length",
            );
        }
        let support_percent = parse_f64(
            field(row, "support_percent")?,
            "chr assignment support_percent",
        )?;
        if !(0.0..=100.0).contains(&support_percent) {
            return grt_err(
                "INVALID_VALUE",
                "chr assignment support_percent must be between 0 and 100",
            );
        }
        assignment_baselines.insert(
            (dataset, seq, chr.to_string()),
            (
                orient.to_string(),
                parse_i64(field(row, "anchor_start")?, "chr assignment anchor_start")?,
            ),
        );
    }

    let recipe = one_row(&tables, "metadata/grt_recipe.tsv")?;
    let primary_dataset = nonempty(recipe, "primary_dataset", "recipe primary dataset")?;
    if !dataset_names.contains(primary_dataset) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe primary_dataset is absent from datasets.tsv",
        );
    }
    let support_datasets = json_string_list(
        field(recipe, "support_datasets_json")?,
        "recipe.support_datasets_json",
    )?;
    let mut support_seen = HashSet::new();
    if support_datasets.iter().any(|name| {
        name == primary_dataset
            || !dataset_names.contains(name)
            || !support_seen.insert(name.clone())
    }) {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe support datasets must be unique, known, and exclude primary",
        );
    }
    if parse_bool(
        field(recipe, "reads_qc_enabled")?,
        "recipe.reads_qc_enabled",
    )? != reads_qc
    {
        return grt_err(
            "INVALID_VALUE",
            "recipe and package reads_qc_enabled disagree",
        );
    }
    if field(recipe, "final_q_relpath")? != q4_relpath {
        return grt_err(
            "BROKEN_REFERENCE",
            "recipe final_q_relpath differs from App manifest",
        );
    }

    validate_app_source_cards(
        table(&tables, "metadata/grt_used_contigs.tsv")?,
        &sources,
        &assignment_baselines,
        &reference_records,
    )?;
    let source_sequences = if fasta_available {
        Some(source_catalog(
            bundle_root,
            table(&tables, "metadata/source_seq_locator.tsv")?,
        )?)
    } else {
        None
    };
    let final_path = read_json(bundle_root, "metadata/grt_final_path.json")?;
    let (q4_lengths, _q4_records) = validate_app_final_path(
        bundle_root,
        &final_path,
        &reference_records,
        &sources,
        manifest_object,
        fasta_available,
        source_sequences.as_ref(),
    )?;
    if let Some(expected_lengths) = manifest_object
        .get("q4_chromosome_lengths")
        .and_then(Value::as_object)
    {
        for (chr, expected) in expected_lengths {
            let value = expected.as_u64().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "App manifest chromosome length is invalid")
            })?;
            if q4_lengths.get(chr).copied() != Some(value as usize) {
                return grt_err(
                    "FINAL_PATH_MISMATCH",
                    format!("App manifest q4 length differs for {chr}"),
                );
            }
        }
    }
    let expected_total =
        json_positive_i64(manifest_object, "q4_length_bp", "App manifest")? as usize;
    if expected_total != q4_lengths.values().sum::<usize>() {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "App manifest q4_length_bp differs from chromosome lengths",
        );
    }

    // The catalog persistence layer intentionally keeps the Server-shaped
    // tables, but App packages do not carry those trace tables.  Empty tables
    // make the absence explicit without retaining any Server audit payload.
    for (relpath, header, _, _) in TABLE_SPECS {
        tables
            .entry(*relpath)
            .or_insert_with(|| TsvTable { rows: Vec::new() });
        let _ = header;
    }
    Ok(ValidatedGrtPackage {
        tables,
        events: Vec::new(),
        final_path,
        q0_artifact_sha256: String::new(),
        q4_artifact_sha256: q4_artifact_sha256.to_string(),
    })
}

fn read_fai_lengths(path: &Path, label: &str) -> Result<BTreeMap<String, usize>> {
    let text = fs::read_to_string(path)
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{label} FAI is not UTF-8: {error}")))?;
    let mut lengths = BTreeMap::new();
    for (offset, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let columns = line.trim_end_matches('\r').split('\t').collect::<Vec<_>>();
        if columns.len() < 2 || columns[0].is_empty() {
            return grt_err(
                "INVALID_TSV",
                format!("{label} FAI row {} is invalid", offset + 1),
            );
        }
        let length = columns[1].parse::<usize>().map_err(|_| {
            grt_anyhow(
                "INVALID_VALUE",
                format!("{label} FAI row {} has invalid length", offset + 1),
            )
        })?;
        if length == 0 || lengths.insert(columns[0].to_string(), length).is_some() {
            return grt_err(
                "DUPLICATE_ID",
                format!("{label} FAI has empty or duplicate sequence {}", columns[0]),
            );
        }
    }
    if lengths.is_empty() {
        return grt_err("INVALID_TSV", format!("{label} FAI contains no records"));
    }
    Ok(lengths)
}

fn source_length_catalog(
    _bundle_root: &Path,
    table: &TsvTable,
    dataset_fai: &HashMap<String, BTreeMap<String, usize>>,
) -> Result<HashMap<(String, String), usize>> {
    let mut sources = HashMap::new();
    for row in &table.rows {
        let dataset = nonempty(row, "dataset_name", "source locator dataset")?.to_string();
        let contig = nonempty(row, "seq_name", "source locator sequence")?.to_string();
        let relpath = field(row, "fasta_relpath")?;
        validate_relpath(relpath, "source locator fasta_relpath")?;
        let records = if let Some(records) = dataset_fai.get(&dataset) {
            records
        } else {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source locator references unknown dataset {dataset}"),
            );
        };
        let length = records.get(&contig).copied().ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("source locator {dataset}:{contig} is absent from its dataset FAI"),
            )
        })?;
        if sources
            .insert((dataset.clone(), contig.clone()), length)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate source locator for {dataset}:{contig}"),
            );
        }
    }
    Ok(sources)
}

fn validate_app_source_cards(
    table: &TsvTable,
    sources: &HashMap<(String, String), usize>,
    assignment_baselines: &HashMap<(String, String, String), (String, i64)>,
    reference_records: &BTreeMap<String, usize>,
) -> Result<()> {
    let mut ids = HashSet::new();
    for row in &table.rows {
        let card = nonempty(row, "source_card_key", "source card key")?;
        if !ids.insert(card.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate source card {card}"));
        }
        let dataset = field(row, "dataset_name")?;
        let contig = field(row, "contig_name")?;
        let target_chr = nonempty(row, "target_chr", "source card target chromosome")?;
        if !reference_records.contains_key(target_chr) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown chromosome {target_chr}"),
            );
        }
        let key = (dataset.to_string(), contig.to_string());
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown source"),
            );
        }
        enum_value(
            field(row, "original_assignment")?,
            &["assigned", "unplaced", "cross_chr"],
            &format!("source card {card}.original_assignment"),
        )?;
        let placement = field(row, "placement_mode")?;
        enum_value(
            placement,
            &["normal", "grt_promoted", "cross_chr_grt_usage"],
            &format!("source card {card}.placement_mode"),
        )?;
        enum_value(
            field(row, "ref_alignment_status")?,
            &["hit", "weak_hit", "multi_hit", "other_chr_only", "no_hit"],
            &format!("source card {card}.ref_alignment_status"),
        )?;
        orientation(field(row, "orientation")?, &format!("source card {card}"))?;
        let anchor = parse_positive_i64(
            field(row, "anchor_start")?,
            &format!("source card {card}.anchor_start"),
        )?;
        let expected = format!("{}:{}:{}:{}", dataset, contig, target_chr, placement);
        if card != expected {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} is non-canonical"),
            );
        }
        if placement == "normal" {
            let baseline_key = (
                dataset.to_string(),
                contig.to_string(),
                target_chr.to_string(),
            );
            let Some((baseline_orientation, baseline_anchor)) =
                assignment_baselines.get(&baseline_key)
            else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} lacks assignment baseline"),
                );
            };
            if field(row, "orientation")? != baseline_orientation || anchor != *baseline_anchor {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} disagrees with assignment baseline"),
                );
            }
        }
        for trace_field in [
            "ref_evidence_ids_json",
            "accepted_event_ids_json",
            "final_path_segment_ids_json",
            "pairwise_evidence_ids_json",
        ] {
            let value = field(row, trace_field)?;
            if !value.is_empty() {
                let ids = json_string_list(value, &format!("source card {card}.{trace_field}"))?;
                if !ids.is_empty() {
                    return grt_err(
                        "INVALID_VALUE",
                        format!("App source card {card} retains Server trace links"),
                    );
                }
            }
        }
    }
    Ok(())
}

fn validate_app_final_path(
    bundle_root: &Path,
    final_path: &Value,
    reference_records: &BTreeMap<String, usize>,
    sources: &HashMap<(String, String), usize>,
    manifest: &Map<String, Value>,
    fasta_available: bool,
    source_sequences: Option<&HashMap<(String, String), String>>,
) -> Result<AppQ4Validation> {
    let object = final_path
        .as_object()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", "App Final Path must be an object"))?;
    if json_str(object, "workflow", "App Final Path")? != GRT_APP_WORKFLOW
        || json_str(object, "schema_version", "App Final Path")? != GRT_SCHEMA_VERSION
        || json_str(object, "q4_relpath", "App Final Path")? != "grt/q/q4.fa"
    {
        return grt_err(
            "UNSUPPORTED_SCHEMA",
            "App Final Path has unsupported workflow/schema",
        );
    }
    let chromosomes = object
        .get("chromosomes")
        .and_then(Value::as_array)
        .filter(|items| !items.is_empty())
        .ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App Final Path chromosomes must be non-empty",
            )
        })?;
    let mut final_lengths = BTreeMap::new();
    let mut segment_ids = HashSet::new();
    for chromosome in chromosomes {
        let chr = chromosome.as_object().ok_or_else(|| {
            grt_anyhow(
                "INVALID_JSON",
                "App Final Path chromosome must be an object",
            )
        })?;
        let chr_name = json_nonempty_str(chr, "chr", "App Final Path chromosome")?;
        if final_lengths
            .insert(
                chr_name.to_string(),
                json_positive_i64(chr, "q4_length", chr_name)? as usize,
            )
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate App Final Path chromosome {chr_name}"),
            );
        }
        if !reference_records.contains_key(chr_name) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("App Final Path references unknown chromosome {chr_name}"),
            );
        }
        validate_sha256(
            json_nonempty_str(chr, "q4_sha256", chr_name)?,
            &format!("App Final Path {chr_name}.q4_sha256"),
        )?;
        let segments = chr
            .get("segments")
            .and_then(Value::as_array)
            .filter(|items| !items.is_empty())
            .ok_or_else(|| {
                grt_anyhow(
                    "INVALID_JSON",
                    format!("App Final Path {chr_name}.segments must be non-empty"),
                )
            })?;
        let mut segment_total = 0_usize;
        for segment in segments {
            let segment = segment.as_object().ok_or_else(|| {
                grt_anyhow("INVALID_JSON", "App Final Path segment must be an object")
            })?;
            let id = json_nonempty_str(segment, "segment_id", "App Final Path segment")?;
            if !segment_ids.insert(id.to_string()) {
                return grt_err(
                    "DUPLICATE_ID",
                    format!("duplicate App Final Path segment {id}"),
                );
            }
            let length = json_positive_i64(segment, "length", id)? as usize;
            segment_total = segment_total.checked_add(length).ok_or_else(|| {
                grt_anyhow(
                    "INVALID_COORDINATE",
                    "App Final Path segment lengths overflow",
                )
            })?;
            let kind = json_str(segment, "kind", id)?;
            enum_value(
                kind,
                &["source", "patch", "correction", "telomere", "gap"],
                &format!("App segment {id}.kind"),
            )?;
            if kind == "gap" {
                continue;
            }
            let orient = orientation(
                json_str(segment, "orientation", id)?,
                &format!("App segment {id}"),
            )?;
            let source = segment
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "INVALID_JSON",
                        format!("App segment {id}.source is invalid"),
                    )
                })?;
            let source_key = (
                json_nonempty_str(source, "dataset", id)?.to_string(),
                json_nonempty_str(source, "contig", id)?.to_string(),
            );
            let source_length = sources.get(&source_key).ok_or_else(|| {
                grt_anyhow(
                    "BROKEN_REFERENCE",
                    format!("App segment {id} references unknown source"),
                )
            })?;
            let start = json_positive_i64(source, "start", id)?;
            let end = json_positive_i64(source, "end", id)?;
            if end < start || end as usize > *source_length || (end - start + 1) as usize != length
            {
                return grt_err(
                    "INVALID_COORDINATE",
                    format!("App segment {id} source interval does not match length"),
                );
            }
            if orientation(
                json_str(source, "orientation", id)?,
                &format!("App segment {id}.source"),
            )? != orient
            {
                return grt_err(
                    "INVALID_VALUE",
                    format!("App segment {id} orientation differs from source"),
                );
            }
        }
        if segment_total != final_lengths[chr_name] {
            return grt_err(
                "FINAL_PATH_MISMATCH",
                format!("App Final Path segment lengths differ for {chr_name}"),
            );
        }
    }
    if final_lengths.keys().collect::<HashSet<_>>()
        != reference_records.keys().collect::<HashSet<_>>()
    {
        return grt_err(
            "FINAL_PATH_MISMATCH",
            "App Final Path chromosome set differs from reference FAI",
        );
    }
    let mut q4_records = None;
    let q4_path = bundle_root.join("grt/q/q4.fa");
    if fasta_available {
        let records = read_fasta(
            &required_bundle_file(bundle_root, "grt/q/q4.fa", "App q4 FASTA")?,
            "App q4 FASTA",
            false,
        )?;
        if sha256_file(&q4_path)?
            != json_nonempty_str(manifest, "q4_artifact_sha256", "App manifest")?
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                "App q4 artifact checksum differs from manifest",
            );
        }
        for chromosome in chromosomes {
            let chr = chromosome.as_object().unwrap();
            let name = json_str(chr, "chr", "App Final Path chromosome")?;
            let sequence = records.get(name).ok_or_else(|| {
                grt_anyhow(
                    "FINAL_PATH_MISMATCH",
                    format!("App q4 FASTA lacks chromosome {name}"),
                )
            })?;
            if sequence.len() != final_lengths[name]
                || sha256_bytes(sequence.as_bytes()) != json_str(chr, "q4_sha256", name)?
            {
                return grt_err(
                    "FINAL_PATH_MISMATCH",
                    format!("App q4 FASTA differs from Final Path for {name}"),
                );
            }
            if let Some(source_sequences) = source_sequences {
                let mut rebuilt = String::new();
                for segment in chr["segments"].as_array().unwrap() {
                    let segment = segment.as_object().unwrap();
                    let length = json_positive_i64(segment, "length", name)? as usize;
                    if segment.get("kind").and_then(Value::as_str) == Some("gap") {
                        rebuilt.push_str(&"N".repeat(length));
                        continue;
                    }
                    let source = segment["source"].as_object().unwrap();
                    let key = (
                        json_str(source, "dataset", name)?.to_string(),
                        json_str(source, "contig", name)?.to_string(),
                    );
                    let start = json_positive_i64(source, "start", name)?;
                    let end = json_positive_i64(source, "end", name)?;
                    let orient = orientation(json_str(source, "orientation", name)?, name)?;
                    let source_sequence = source_sequences.get(&key).ok_or_else(|| {
                        grt_anyhow(
                            "BROKEN_REFERENCE",
                            format!("App q4 source record is missing for {name}"),
                        )
                    })?;
                    rebuilt.push_str(&orient_sequence(
                        &source_sequence[(start - 1) as usize..end as usize],
                        orient,
                    ));
                }
                if rebuilt != *sequence {
                    return grt_err(
                        "FINAL_PATH_MISMATCH",
                        format!("App Final Path source reconstruction differs from q4 for {name}"),
                    );
                }
            }
        }
        q4_records = Some(records);
    } else if q4_path.exists() {
        return grt_err(
            "INVALID_VALUE",
            "no_fasta App package must not contain grt/q/q4.fa",
        );
    }
    Ok((final_lengths, q4_records))
}

fn validate_stage_status(
    bundle_root: &Path,
    table: &TsvTable,
    q_hashes: &HashMap<String, String>,
    donor_sets: &HashMap<String, &TsvRow>,
) -> Result<()> {
    for (row, (stage, input, output)) in table.rows.iter().zip(STAGE_TRANSITIONS.iter()) {
        if field(row, "stage")? != *stage
            || field(row, "q_input_version")? != *input
            || field(row, "q_output_version")? != *output
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("stage transition must be {stage}:{input}->{output}"),
            );
        }
        if field(row, "status")? != "success"
            || q_hashes.get(*input).map(String::as_str) != Some(field(row, "q_input_sha256")?)
            || q_hashes.get(*output).map(String::as_str) != Some(field(row, "q_output_sha256")?)
        {
            return grt_err(
                "CHECKSUM_MISMATCH",
                format!("stage {stage} q transition checksum mismatch"),
            );
        }
        let donor_set_id = field(row, "donor_set_id")?;
        if !donor_set_id.is_empty() && !donor_sets.contains_key(donor_set_id) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("stage {stage} references unknown donor set"),
            );
        }
        validate_artifact(
            bundle_root,
            field(row, "checkpoint_relpath")?,
            field(row, "checkpoint_sha256")?,
            &format!("stage {stage} checkpoint"),
        )?;
    }
    Ok(())
}

fn validate_tool_versions(table: &TsvTable) -> Result<()> {
    let mut tools = HashSet::new();
    for row in &table.rows {
        let tool = nonempty(row, "tool", "tool version tool")?;
        nonempty(row, "version", "tool version")?;
        nonempty(row, "executable", "tool executable")?;
        if !tools.insert(tool.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate tool version {tool}"));
        }
    }
    Ok(())
}

fn validate_source_cards(
    table: &TsvTable,
    sources: &HashMap<(String, String), String>,
    assignment_baselines: &HashMap<(String, String, String), (String, i64)>,
    evidence: &HashMap<String, &TsvRow>,
    events: &HashMap<String, &Value>,
    segments: &HashMap<String, (&Value, String)>,
) -> Result<()> {
    let mut card_ids = HashSet::new();
    for row in &table.rows {
        let card = nonempty(row, "source_card_key", "source card key")?;
        if !card_ids.insert(card.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate source card {card}"));
        }
        let key = (
            field(row, "dataset_name")?.to_string(),
            field(row, "contig_name")?.to_string(),
        );
        if !sources.contains_key(&key) {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} references unknown source"),
            );
        }
        enum_value(
            field(row, "original_assignment")?,
            &["assigned", "unplaced", "cross_chr"],
            &format!("source card {card}.original_assignment"),
        )?;
        enum_value(
            field(row, "placement_mode")?,
            &["normal", "grt_promoted", "cross_chr_grt_usage"],
            &format!("source card {card}.placement_mode"),
        )?;
        enum_value(
            field(row, "ref_alignment_status")?,
            &["hit", "weak_hit", "multi_hit", "other_chr_only", "no_hit"],
            &format!("source card {card}.ref_alignment_status"),
        )?;
        let card_orientation =
            orientation(field(row, "orientation")?, &format!("source card {card}"))?;
        let card_anchor = parse_i64(
            field(row, "anchor_start")?,
            &format!("source card {card}.anchor_start"),
        )?;
        if field(row, "placement_mode")? == "normal" {
            let assignment_key = (
                key.0.clone(),
                key.1.clone(),
                field(row, "target_chr")?.to_string(),
            );
            let Some((baseline_orientation, baseline_anchor)) =
                assignment_baselines.get(&assignment_key)
            else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} lacks an assignment baseline"),
                );
            };
            if card_orientation != baseline_orientation || card_anchor != *baseline_anchor {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("normal source card {card} disagrees with chr assignment baseline"),
                );
            }
        }
        let expected = format!(
            "{}:{}:{}:{}",
            key.0,
            key.1,
            field(row, "target_chr")?,
            field(row, "placement_mode")?
        );
        if card != expected {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} is non-canonical"),
            );
        }
        let refs = json_string_list(
            field(row, "ref_evidence_ids_json")?,
            &format!("source card {card}.ref evidence"),
        )?;
        let event_ids = json_string_list(
            field(row, "accepted_event_ids_json")?,
            &format!("source card {card}.events"),
        )?;
        let segment_ids = json_string_list(
            field(row, "final_path_segment_ids_json")?,
            &format!("source card {card}.segments"),
        )?;
        let pairwise = json_string_list(
            field(row, "pairwise_evidence_ids_json")?,
            &format!("source card {card}.pairwise evidence"),
        )?;
        if refs.is_empty() || event_ids.is_empty() || segment_ids.is_empty() || pairwise.is_empty()
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} has incomplete trace chain"),
            );
        }
        if refs.iter().any(|id| {
            evidence.get(id).is_none_or(|row| {
                field(row, "stage").ok() != Some("assignment")
                    || field(row, "status").ok() != Some("accepted")
            })
        }) || pairwise.iter().any(|id| {
            evidence.get(id).is_none_or(|row| {
                field(row, "stage").ok() != Some("display_pairwise")
                    || field(row, "status").ok() != Some("accepted")
            })
        }) || event_ids.iter().any(|id| {
            events
                .get(id)
                .is_none_or(|event| event.get("status").and_then(Value::as_str) != Some("accepted"))
        }) || segment_ids.iter().any(|id| !segments.contains_key(id))
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} contains an invalid trace link"),
            );
        }
        let expected_event_ids = events
            .iter()
            .filter_map(|(event_id, event)| {
                let action = event.get("action").and_then(Value::as_str).unwrap_or("");
                (event.get("status").and_then(Value::as_str) == Some("accepted")
                    && event.get("source_card_key").and_then(Value::as_str) == Some(card)
                    && matches!(
                        action,
                        "fill"
                            | "patch"
                            | "replace"
                            | "correct_boundary"
                            | "refill"
                            | "extend_telomere"
                    ))
                .then(|| event_id.clone())
            })
            .collect::<HashSet<_>>();
        if event_ids.iter().cloned().collect::<HashSet<_>>() != expected_event_ids {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} accepted-event set is not exact"),
            );
        }
        let expected_segment_ids = expected_event_ids
            .iter()
            .filter_map(|event_id| {
                events[event_id]
                    .get("final_path_segment_id")
                    .and_then(Value::as_str)
                    .filter(|value| !value.is_empty())
                    .map(ToString::to_string)
            })
            .collect::<HashSet<_>>();
        if segment_ids.iter().cloned().collect::<HashSet<_>>() != expected_segment_ids {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("source card {card} Final Path segment set is not exact"),
            );
        }
        for evidence_id in refs.iter().chain(&pairwise) {
            let evidence_row = evidence[evidence_id];
            if field(evidence_row, "source_dataset")? != key.0.as_str()
                || field(evidence_row, "source_contig")? != key.1.as_str()
                || field(evidence_row, "source_start")? != "1"
                || parse_positive_i64(
                    field(evidence_row, "source_end")?,
                    &format!("source card {card} evidence end"),
                )? as usize
                    != sources[&key].len()
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} evidence is not full-source evidence"),
                );
            }
            let parameters = parse_json_object(
                field(evidence_row, "parameters_json")?,
                &format!("source card {card} evidence parameters"),
            )?;
            let role = parameters.get("role").and_then(Value::as_str);
            if refs.contains(evidence_id) && role != Some("source_ref_profile") {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} lacks source ref-profile role metadata"),
                );
            }
            if pairwise.contains(evidence_id) {
                if role != Some("display_pairwise") {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("source card {card} lacks display-pairwise role metadata"),
                    );
                }
                let expected_provenance = if field(row, "placement_mode")? == "normal" {
                    "existing_main_view"
                } else {
                    "grt_supplement"
                };
                if parameters.get("provenance").and_then(Value::as_str) != Some(expected_provenance)
                {
                    return grt_err(
                        "BROKEN_REFERENCE",
                        format!("source card {card} has invalid pairwise provenance"),
                    );
                }
            }
        }
        for event_id in &event_ids {
            if events[event_id]
                .get("source_card_key")
                .and_then(Value::as_str)
                != Some(card)
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} event link is not bidirectional"),
                );
            }
        }
        for segment_id in &segment_ids {
            let segment = segments[segment_id].0;
            let Some(source) = segment.get("source").and_then(Value::as_object) else {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} points to sourceless segment"),
                );
            };
            if source.get("dataset").and_then(Value::as_str) != Some(key.0.as_str())
                || source.get("contig").and_then(Value::as_str) != Some(key.1.as_str())
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} segment source differs"),
                );
            }
            let event_id = segment
                .get("event_id")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("source card {card} segment lacks event"),
                    )
                })?;
            let event_source = events[event_id]
                .get("source")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    grt_anyhow(
                        "BROKEN_REFERENCE",
                        format!("source card {card} event lacks source"),
                    )
                })?;
            if source.get("start") != event_source.get("start")
                || source.get("end") != event_source.get("end")
                || source.get("orientation") != event_source.get("orientation")
            {
                return grt_err(
                    "BROKEN_REFERENCE",
                    format!("source card {card} event and segment source intervals differ"),
                );
            }
        }
    }
    Ok(())
}

fn validate_gap_attempts(table: &TsvTable, events: &HashMap<String, &Value>) -> Result<()> {
    let mut ids = HashSet::new();
    for row in &table.rows {
        let id = nonempty(row, "attempt_id", "gap attempt id")?;
        if !ids.insert(id.to_string()) {
            return grt_err("DUPLICATE_ID", format!("duplicate gap attempt {id}"));
        }
        nonempty(row, "chr", &format!("gap attempt {id}.chr"))?;
        nonempty(row, "object_id", &format!("gap attempt {id}.object_id"))?;
        enum_value(
            field(row, "stage")?,
            &[
                "step1_round1",
                "step1_filter",
                "step1_round2",
                "step2",
                "step3",
                "step4_telomere",
            ],
            &format!("gap attempt {id}.stage"),
        )?;
        parse_nonnegative_i64(
            field(row, "candidate_count")?,
            &format!("gap attempt {id}.candidate_count"),
        )?;
        let event_id = field(row, "accepted_event_id")?;
        if !event_id.is_empty()
            && events
                .get(event_id)
                .is_none_or(|event| event.get("status").and_then(Value::as_str) != Some("accepted"))
        {
            return grt_err(
                "BROKEN_REFERENCE",
                format!("gap attempt {id} references invalid accepted event"),
            );
        }
    }
    Ok(())
}

fn source_catalog(
    bundle_root: &Path,
    table: &TsvTable,
) -> Result<HashMap<(String, String), String>> {
    let mut cache = HashMap::<String, BTreeMap<String, String>>::new();
    let mut sources = HashMap::new();
    for row in &table.rows {
        let dataset = nonempty(row, "dataset_name", "source locator dataset")?.to_string();
        let contig = nonempty(row, "seq_name", "source locator sequence")?.to_string();
        let relpath = field(row, "fasta_relpath")?.to_string();
        if !cache.contains_key(&relpath) {
            let path = required_bundle_file(
                bundle_root,
                &relpath,
                &format!("source locator {dataset}:{contig}"),
            )?;
            cache.insert(relpath.clone(), read_fasta(&path, &relpath, false)?);
        }
        let sequence = cache[&relpath].get(&contig).cloned().ok_or_else(|| {
            grt_anyhow(
                "BROKEN_REFERENCE",
                format!("source locator {dataset}:{contig} is absent from {relpath}"),
            )
        })?;
        if sources
            .insert((dataset.clone(), contig.clone()), sequence)
            .is_some()
        {
            return grt_err(
                "DUPLICATE_ID",
                format!("duplicate source locator for {dataset}:{contig}"),
            );
        }
    }
    Ok(sources)
}

fn read_tsv(
    bundle_root: &Path,
    relpath: &str,
    expected_header: &[&str],
    minimum: usize,
    maximum: Option<usize>,
) -> Result<TsvTable> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let text = fs::read_to_string(&path).map_err(|error| {
        grt_anyhow(
            "INVALID_TSV",
            format!("cannot read {relpath} as UTF-8: {error}"),
        )
    })?;
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(b'\t')
        .has_headers(false)
        .flexible(false)
        .from_reader(text.as_bytes());
    let mut records = reader.records();
    let header = records
        .next()
        .transpose()
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{relpath}: {error}")))?
        .unwrap_or_default()
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    if !header
        .iter()
        .map(String::as_str)
        .eq(expected_header.iter().copied())
    {
        return grt_err(
            "INVALID_TSV",
            format!(
                "{relpath} header must be {:?}, got {:?}",
                expected_header, header
            ),
        );
    }
    let mut rows = Vec::new();
    for record in records {
        let values =
            record.map_err(|error| grt_anyhow("INVALID_TSV", format!("{relpath}: {error}")))?;
        rows.push(
            header
                .iter()
                .zip(values.iter())
                .map(|(key, value)| (key.clone(), value.to_string()))
                .collect(),
        );
    }
    if rows.len() < minimum || maximum.is_some_and(|limit| rows.len() > limit) {
        return grt_err(
            "INVALID_TSV",
            format!(
                "{relpath} row count {} is outside contract bounds",
                rows.len()
            ),
        );
    }
    Ok(TsvTable { rows })
}

fn read_json(bundle_root: &Path, relpath: &str) -> Result<Value> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let bytes = fs::read(&path)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("cannot read {relpath}: {error}")))?;
    serde_json::from_slice(&bytes)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{relpath}: {error}")))
}

fn read_jsonl(bundle_root: &Path, relpath: &str) -> Result<Vec<Value>> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let text = fs::read_to_string(&path).map_err(|error| {
        grt_anyhow(
            "INVALID_JSON",
            format!("cannot read {relpath} as UTF-8: {error}"),
        )
    })?;
    text.lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(offset, line)| {
            let value: Value = serde_json::from_str(line).map_err(|error| {
                grt_anyhow("INVALID_JSON", format!("{relpath}:{}: {error}", offset + 1))
            })?;
            if !value.is_object() {
                return grt_err(
                    "INVALID_JSON",
                    format!("{relpath}:{} must contain an object", offset + 1),
                );
            }
            Ok(value)
        })
        .collect()
}

fn read_fasta(path: &Path, label: &str, allow_empty: bool) -> Result<BTreeMap<String, String>> {
    let text = fs::read_to_string(path)
        .map_err(|error| grt_anyhow("INVALID_FASTA", format!("{label} is not UTF-8: {error}")))?;
    let mut records = BTreeMap::new();
    let mut name: Option<String> = None;
    let mut sequence = String::new();
    for (offset, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if let Some(header) = line.strip_prefix('>') {
            if let Some(previous) = name.take()
                && (sequence.is_empty()
                    || records
                        .insert(previous.clone(), std::mem::take(&mut sequence))
                        .is_some())
            {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has empty or duplicate record", offset + 1),
                );
            }
            let record_name = header.split_whitespace().next().unwrap_or("");
            if record_name.is_empty() || records.contains_key(record_name) {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has empty or duplicate record", offset + 1),
                );
            }
            name = Some(record_name.to_string());
        } else if !line.is_empty() {
            if name.is_none() {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has sequence before header", offset + 1),
                );
            }
            let upper = line.to_ascii_uppercase();
            if !upper.bytes().all(|base| b"ACGTNRYKMSWBDHV".contains(&base)) {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has unsupported bases", offset + 1),
                );
            }
            sequence.push_str(&upper);
        }
    }
    if let Some(previous) = name
        && (sequence.is_empty() || records.insert(previous, sequence).is_some())
    {
        return grt_err(
            "INVALID_FASTA",
            format!("{label} has empty or duplicate record"),
        );
    }
    if records.is_empty() && !allow_empty {
        return grt_err("INVALID_FASTA", format!("{label} has no non-empty records"));
    }
    Ok(records)
}

fn validate_fasta_fai_pair(fasta_path: &Path, fai_path: &Path, label: &str) -> Result<()> {
    let records = read_fasta(fasta_path, &format!("{label} FASTA"), false)?;
    validate_fasta_fai_records(&records, fai_path, label)
}

fn validate_fasta_fai_records(
    records: &BTreeMap<String, String>,
    fai_path: &Path,
    label: &str,
) -> Result<()> {
    let text = fs::read_to_string(fai_path)
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{label} FAI is not UTF-8: {error}")))?;
    let mut indexed = BTreeMap::<String, usize>::new();
    for (offset, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let columns = line.trim_end_matches('\r').split('\t').collect::<Vec<_>>();
        if columns.len() < 2 || columns[0].is_empty() {
            return grt_err(
                "INVALID_TSV",
                format!("{label} FAI row {} is invalid", offset + 1),
            );
        }
        let length = columns[1].parse::<usize>().map_err(|_| {
            grt_anyhow(
                "INVALID_VALUE",
                format!("{label} FAI row {} has invalid length", offset + 1),
            )
        })?;
        if length == 0 || indexed.insert(columns[0].to_string(), length).is_some() {
            return grt_err(
                "DUPLICATE_ID",
                format!("{label} FAI has empty or duplicate sequence {}", columns[0]),
            );
        }
    }
    let actual = records
        .iter()
        .map(|(name, sequence)| (name.clone(), sequence.len()))
        .collect::<BTreeMap<_, _>>();
    if indexed != actual {
        return grt_err(
            "COUNT_MISMATCH",
            format!("{label} FASTA and FAI sequence names/lengths differ"),
        );
    }
    Ok(())
}

fn required_bundle_file(bundle_root: &Path, relpath: &str, label: &str) -> Result<PathBuf> {
    validate_relpath(relpath, label)?;
    let path = bundle_root.join(relpath);
    if !path.is_file() {
        return grt_err(
            "MISSING_REQUIRED_FILE",
            format!("{label} does not exist: {relpath}"),
        );
    }
    Ok(path)
}

fn validate_relpath(relpath: &str, label: &str) -> Result<()> {
    if relpath.is_empty() || relpath.contains('\\') {
        return grt_err(
            "INVALID_PATH",
            format!("{label} is not a safe relative path: {relpath}"),
        );
    }
    let path = Path::new(relpath);
    if path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return grt_err(
            "INVALID_PATH",
            format!("{label} is not a safe relative path: {relpath}"),
        );
    }
    Ok(())
}

fn validate_artifact(
    bundle_root: &Path,
    relpath: &str,
    expected: &str,
    label: &str,
) -> Result<PathBuf> {
    validate_sha256(expected, &format!("{label}.sha256"))?;
    let path = required_bundle_file(bundle_root, relpath, label)?;
    let actual = sha256_file(&path)?;
    if actual != expected {
        return grt_err(
            "CHECKSUM_MISMATCH",
            format!("{label} expected {expected}, got {actual}"),
        );
    }
    Ok(path)
}

fn sha256_file(path: &Path) -> Result<String> {
    let bytes =
        fs::read(path).with_context(|| format!("failed to read artifact {}", path.display()))?;
    Ok(sha256_bytes(&bytes))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn validate_sha256(value: &str, label: &str) -> Result<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return grt_err(
            "INVALID_VALUE",
            format!("{label} must be a lowercase SHA-256"),
        );
    }
    Ok(())
}

fn reverse_complement(sequence: &str) -> String {
    sequence
        .chars()
        .rev()
        .map(|base| match base {
            'A' => 'T',
            'C' => 'G',
            'G' => 'C',
            'T' => 'A',
            'N' => 'N',
            'R' => 'Y',
            'Y' => 'R',
            'K' => 'M',
            'M' => 'K',
            'S' => 'S',
            'W' => 'W',
            'B' => 'V',
            'D' => 'H',
            'H' => 'D',
            'V' => 'B',
            other => other,
        })
        .collect()
}

fn orient_sequence(sequence: &str, orientation: &str) -> String {
    if orientation == "-" {
        reverse_complement(sequence)
    } else {
        sequence.to_string()
    }
}

fn table<'a>(tables: &'a HashMap<&'static str, TsvTable>, name: &str) -> Result<&'a TsvTable> {
    tables.get(name).ok_or_else(|| {
        grt_anyhow(
            "MISSING_REQUIRED_FILE",
            format!("missing parsed table {name}"),
        )
    })
}
fn one_row<'a>(tables: &'a HashMap<&'static str, TsvTable>, name: &str) -> Result<&'a TsvRow> {
    table(tables, name)?
        .rows
        .first()
        .ok_or_else(|| grt_anyhow("INVALID_TSV", format!("{name} requires exactly one row")))
}
fn field<'a>(row: &'a TsvRow, key: &str) -> Result<&'a str> {
    row.get(key)
        .map(String::as_str)
        .ok_or_else(|| grt_anyhow("INVALID_TSV", format!("missing field {key}")))
}
fn nonempty<'a>(row: &'a TsvRow, key: &str, label: &str) -> Result<&'a str> {
    let value = field(row, key)?;
    if value.is_empty() {
        return grt_err("INVALID_VALUE", format!("{label} must not be empty"));
    }
    Ok(value)
}
fn parse_bool(value: &str, label: &str) -> Result<bool> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => grt_err("INVALID_VALUE", format!("{label} must be true or false")),
    }
}
fn parse_i64(value: &str, label: &str) -> Result<i64> {
    value
        .parse()
        .map_err(|_| grt_anyhow("INVALID_VALUE", format!("{label} must be an integer")))
}
fn parse_positive_i64(value: &str, label: &str) -> Result<i64> {
    let parsed = parse_i64(value, label)?;
    if parsed < 1 {
        return grt_err("INVALID_COORDINATE", format!("{label} must be >= 1"));
    }
    Ok(parsed)
}
fn parse_nonnegative_i64(value: &str, label: &str) -> Result<i64> {
    let parsed = parse_i64(value, label)?;
    if parsed < 0 {
        return grt_err("INVALID_VALUE", format!("{label} must be >= 0"));
    }
    Ok(parsed)
}
fn parse_f64(value: &str, label: &str) -> Result<f64> {
    value
        .parse()
        .map_err(|_| grt_anyhow("INVALID_VALUE", format!("{label} must be numeric")))
}
fn interval(row: &TsvRow, start: &str, end: &str, label: &str) -> Result<(i64, i64)> {
    let start = parse_positive_i64(field(row, start)?, &format!("{label}.start"))?;
    let end = parse_positive_i64(field(row, end)?, &format!("{label}.end"))?;
    if start > end {
        return grt_err(
            "INVALID_COORDINATE",
            format!("{label} must satisfy start <= end"),
        );
    }
    Ok((start, end))
}
fn orientation<'a>(value: &'a str, label: &str) -> Result<&'a str> {
    enum_value(value, &["+", "-"], label)
}
fn enum_value<'a>(value: &'a str, allowed: &[&str], label: &str) -> Result<&'a str> {
    if !allowed.contains(&value) {
        return grt_err(
            "INVALID_VALUE",
            format!("{label} has unsupported value {value}"),
        );
    }
    Ok(value)
}
fn json_string_list(value: &str, label: &str) -> Result<Vec<String>> {
    let parsed: Value = serde_json::from_str(value)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{label}: {error}")))?;
    json_value_string_list(&parsed, label)
}
fn json_value_string_list(value: &Value, label: &str) -> Result<Vec<String>> {
    let array = value
        .as_array()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label} must contain an array")))?;
    array
        .iter()
        .map(|item| {
            item.as_str().map(ToString::to_string).ok_or_else(|| {
                grt_anyhow("INVALID_JSON", format!("{label} must contain only strings"))
            })
        })
        .collect()
}
fn parse_json_object(value: &str, label: &str) -> Result<Value> {
    let parsed: Value = serde_json::from_str(value)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{label}: {error}")))?;
    if !parsed.is_object() {
        return grt_err("INVALID_JSON", format!("{label} must contain an object"));
    }
    Ok(parsed)
}
fn json_str<'a>(object: &'a Map<String, Value>, key: &str, label: &str) -> Result<&'a str> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label}.{key} must be a string")))
}
fn json_nonempty_str<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a str> {
    let value = json_str(object, key, label)?;
    if value.is_empty() {
        return grt_err("INVALID_VALUE", format!("{label}.{key} must not be empty"));
    }
    Ok(value)
}
fn json_positive_i64(object: &Map<String, Value>, key: &str, label: &str) -> Result<i64> {
    let value = object
        .get(key)
        .and_then(Value::as_i64)
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label}.{key} must be an integer")))?;
    if value < 1 {
        return grt_err("INVALID_COORDINATE", format!("{label}.{key} must be >= 1"));
    }
    Ok(value)
}
fn grt_anyhow(code: &str, message: impl std::fmt::Display) -> anyhow::Error {
    anyhow!("GRT_IMPORT_{code}: {message}")
}
fn grt_err<T>(code: &str, message: impl std::fmt::Display) -> Result<T> {
    Err(grt_anyhow(code, message))
}

// Persistence and query functions are intentionally colocated with validation so the
// importer can pass one already-validated in-memory package into the catalog transaction.
pub(crate) fn persist_grt_package(
    tx: &Transaction<'_>,
    package: &ValidatedGrtPackage,
) -> Result<()> {
    clear_grt_tables(tx)?;
    let package_row = one_row(&package.tables, "metadata/package.tsv")?;
    let recipe = one_row(&package.tables, "metadata/grt_recipe.tsv")?;
    tx.execute(
        "INSERT INTO grt_package (
            id, workflow, schema_version, final_path_schema_version, recipe_id, primary_dataset,
            support_datasets_json, reads_qc_enabled, donor_set_id, tel_donor_set_id, q0_relpath,
            final_q_relpath, q0_artifact_sha256, q4_artifact_sha256, final_path_json
         ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        params![
            field(package_row, "workflow")?,
            field(package_row, "schema_version")?,
            field(package_row, "final_path_schema_version")?,
            field(recipe, "recipe_id")?,
            field(recipe, "primary_dataset")?,
            field(recipe, "support_datasets_json")?,
            if parse_bool(
                field(recipe, "reads_qc_enabled")?,
                "recipe.reads_qc_enabled"
            )? {
                1
            } else {
                0
            },
            field(recipe, "donor_set_id")?,
            field(recipe, "tel_donor_set_id")?,
            field(recipe, "q0_relpath")?,
            field(recipe, "final_q_relpath")?,
            package.q0_artifact_sha256,
            package.q4_artifact_sha256,
            serde_json::to_string(&package.final_path)?,
        ],
    )
    .context("failed to persist locked GRT package recipe")?;

    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_contig_roles.tsv")?,
        "grt_contig_role",
        &["dataset_name", "contig_name"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_sets.tsv")?,
        "grt_donor_set",
        &["donor_set_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_members.tsv")?,
        "grt_donor_member",
        &["donor_set_id", "member_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_q_segments.tsv")?,
        "grt_q_segment",
        &["segment_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_evidence_registry.tsv")?,
        "grt_evidence",
        &["evidence_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_donor_usage.tsv")?,
        "grt_donor_usage",
        &["usage_id"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_used_contigs.tsv")?,
        "grt_source_card",
        &["source_card_key"],
    )?;
    for row in &table(&package.tables, "metadata/grt_gap_attempts.tsv")?.rows {
        let stage = field(row, "stage")?;
        tx.execute(
            "INSERT INTO grt_object_attempt (
                attempt_id, chr, object_id, object_kind, stage, status,
                accepted_event_id, row_json
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                field(row, "attempt_id")?,
                field(row, "chr")?,
                field(row, "object_id")?,
                if stage == "step4_telomere" {
                    "terminal"
                } else {
                    "gap"
                },
                stage,
                field(row, "status")?,
                field(row, "accepted_event_id")?,
                serde_json::to_string(row)?,
            ],
        )
        .context("failed to persist GRT gap/terminal object attempt")?;
    }
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_stage_status.tsv")?,
        "grt_stage_status",
        &["stage"],
    )?;
    persist_row_table(
        tx,
        table(&package.tables, "metadata/grt_tool_versions.tsv")?,
        "grt_tool_version",
        &["tool"],
    )?;

    for event in &package.events {
        let object = event.as_object().unwrap();
        tx.execute(
            "INSERT INTO grt_event (event_id, stage, chr, object_id, action, status, source_card_key, final_path_segment_id, event_json)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                json_str(object, "event_id", "event")?, json_str(object, "stage", "event")?,
                json_str(object, "chr", "event")?, json_str(object, "object_id", "event")?,
                json_str(object, "action", "event")?, json_str(object, "status", "event")?,
                object.get("source_card_key").and_then(Value::as_str).unwrap_or(""),
                object.get("final_path_segment_id").and_then(Value::as_str).unwrap_or(""),
                serde_json::to_string(event)?,
            ],
        ).context("failed to persist GRT event")?;
    }
    let chromosomes = package.final_path["chromosomes"].as_array().unwrap();
    for chromosome in chromosomes {
        let object = chromosome.as_object().unwrap();
        let chr_name = json_str(object, "chr", "Final Path chromosome")?;
        tx.execute(
            "INSERT INTO grt_final_path_chr (chr, q4_length, q4_sha256, chromosome_json) VALUES (?1, ?2, ?3, ?4)",
            params![chr_name, json_positive_i64(object, "q4_length", chr_name)?, json_str(object, "q4_sha256", chr_name)?, serde_json::to_string(chromosome)?],
        ).context("failed to persist GRT Final Path chromosome")?;
        for (offset, segment) in object["segments"].as_array().unwrap().iter().enumerate() {
            let segment_object = segment.as_object().unwrap();
            tx.execute(
                "INSERT INTO grt_final_path_segment (segment_id, chr, segment_order, kind, event_id, segment_json)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    json_str(segment_object, "segment_id", "segment")?, chr_name, (offset + 1) as i64,
                    json_str(segment_object, "kind", "segment")?, segment_object.get("event_id").and_then(Value::as_str),
                    serde_json::to_string(segment)?,
                ],
            ).context("failed to persist GRT Final Path segment")?;
        }
    }
    Ok(())
}

fn persist_row_table(
    tx: &Transaction<'_>,
    table: &TsvTable,
    sql_table: &str,
    id_columns: &[&str],
) -> Result<()> {
    let placeholders = (1..=id_columns.len() + 1)
        .map(|index| format!("?{index}"))
        .collect::<Vec<_>>()
        .join(", ");
    let mut columns = id_columns.join(", ");
    if !columns.is_empty() {
        columns.push_str(", ");
    }
    columns.push_str("row_json");
    let sql = format!("INSERT INTO {sql_table} ({columns}) VALUES ({placeholders})");
    for row in &table.rows {
        let row_json = serde_json::to_string(row)?;
        let mut values = id_columns
            .iter()
            .map(|column| field(row, column).map(ToString::to_string))
            .collect::<Result<Vec<_>>>()?;
        values.push(row_json);
        tx.execute(&sql, rusqlite::params_from_iter(values.iter()))
            .with_context(|| format!("failed to persist {sql_table}"))?;
    }
    Ok(())
}

fn clear_grt_tables(tx: &Transaction<'_>) -> Result<()> {
    for table in [
        "grt_final_path_segment",
        "grt_final_path_chr",
        "grt_event",
        "grt_object_attempt",
        "grt_source_card",
        "grt_donor_usage",
        "grt_evidence",
        "grt_q_segment",
        "grt_donor_member",
        "grt_donor_set",
        "grt_contig_role",
        "grt_stage_status",
        "grt_tool_version",
        "grt_package",
    ] {
        tx.execute(&format!("DELETE FROM {table}"), [])
            .with_context(|| format!("failed to clear {table}"))?;
    }
    Ok(())
}

pub fn load_grt_locked_recipe(project_db_path: &Path) -> Result<GrtLockedRecipe> {
    let conn = open_workspace_db(project_db_path)?;
    conn.query_row(
        "SELECT workflow, schema_version, final_path_schema_version, recipe_id, primary_dataset,
                support_datasets_json, reads_qc_enabled, donor_set_id, tel_donor_set_id,
                q0_relpath, final_q_relpath, q0_artifact_sha256, q4_artifact_sha256
         FROM grt_package WHERE id = 1",
        [],
        |row| {
            let support_json: String = row.get(5)?;
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                support_json,
                row.get::<_, i64>(6)? > 0,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
                row.get::<_, String>(9)?,
                row.get::<_, String>(10)?,
                row.get::<_, String>(11)?,
                row.get::<_, String>(12)?,
            ))
        },
    )
    .optional()
    .context("failed to query locked GRT recipe")?
    .ok_or_else(|| anyhow!("GRT package recipe is not available"))
    .and_then(|row| {
        Ok(GrtLockedRecipe {
            workflow: row.0,
            schema_version: row.1,
            final_path_schema_version: row.2,
            recipe_id: row.3,
            primary_dataset: row.4,
            support_datasets: serde_json::from_str(&row.5)
                .context("persisted GRT support dataset JSON is invalid")?,
            reads_qc_enabled: row.6,
            donor_set_id: row.7,
            tel_donor_set_id: row.8,
            q0_relpath: row.9,
            final_q_relpath: row.10,
            q0_artifact_sha256: row.11,
            q4_artifact_sha256: row.12,
        })
    })
}

pub fn load_grt_final_path(project_db_path: &Path) -> Result<Value> {
    let conn = open_workspace_db(project_db_path)?;
    let json: String = conn
        .query_row(
            "SELECT final_path_json FROM grt_package WHERE id = 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .context("failed to query precomputed GRT Final Path")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    serde_json::from_str(&json).context("persisted GRT Final Path JSON is invalid")
}

pub fn load_grt_final_path_by_chr(project_db_path: &Path) -> Result<BTreeMap<String, Value>> {
    let conn = open_workspace_db(project_db_path)?;
    let mut stmt = conn
        .prepare("SELECT chr, chromosome_json FROM grt_final_path_chr ORDER BY chr")
        .context("failed to prepare precomputed GRT Final Path chromosome query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    rows.into_iter()
        .map(|(chr_name, json)| {
            let chromosome: Value = serde_json::from_str(&json)
                .context("persisted GRT Final Path chromosome JSON is invalid")?;
            Ok((chr_name, project_grt_final_path_chromosome(chromosome)?))
        })
        .collect()
}

fn project_grt_final_path_chromosome(mut chromosome: Value) -> Result<Value> {
    let object = chromosome
        .as_object_mut()
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome JSON is invalid"))?;
    let segments = object
        .get_mut("segments")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome segments are invalid"))?;
    for segment in segments {
        let segment_object = segment
            .as_object_mut()
            .ok_or_else(|| anyhow!("persisted GRT Final Path segment JSON is invalid"))?;
        for key in [
            "event_id",
            "eventId",
            "evidence_ids",
            "evidenceIds",
            "source_card_key",
            "sourceCardKey",
        ] {
            segment_object.remove(key);
        }
    }
    Ok(chromosome)
}

pub fn load_grt_object_attempts(project_db_path: &Path) -> Result<Vec<Value>> {
    let conn = open_workspace_db(project_db_path)?;
    let mut stmt = conn
        .prepare(
            "SELECT object_kind, row_json
             FROM grt_object_attempt
             ORDER BY chr, object_kind, object_id, stage, attempt_id",
        )
        .context("failed to prepare GRT object attempt query")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    rows.into_iter()
        .map(|(object_kind, json)| {
            let mut value: Value = serde_json::from_str(&json)
                .context("persisted GRT object attempt JSON is invalid")?;
            value
                .as_object_mut()
                .ok_or_else(|| anyhow!("persisted GRT object attempt must be an object"))?
                .insert("object_kind".to_string(), Value::String(object_kind));
            Ok(value)
        })
        .collect()
}

pub fn load_grt_source_cards(project_db_path: &Path) -> Result<Vec<Value>> {
    let conn = open_workspace_db(project_db_path)?;
    load_matching_json(
        &conn,
        "SELECT row_json FROM grt_source_card ORDER BY source_card_key",
        |_| true,
    )
}

pub fn load_grt_source_card_statuses(project_db_path: &Path) -> Result<Vec<GrtSourceCardStatus>> {
    load_grt_source_cards(project_db_path)?
        .into_iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| anyhow!("persisted GRT source card JSON is invalid"))?;
            Ok(GrtSourceCardStatus {
                source_card_key: object
                    .get("source_card_key")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                dataset_name: object
                    .get("dataset_name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                contig_name: object
                    .get("contig_name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                target_chr: object
                    .get("target_chr")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                placement_mode: object
                    .get("placement_mode")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                ref_alignment_status: object
                    .get("ref_alignment_status")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            })
        })
        .collect()
}

pub fn load_grt_project_view(project_db_path: &Path) -> Result<GrtProjectView> {
    Ok(GrtProjectView {
        recipe: load_grt_locked_recipe(project_db_path)?,
        final_path_by_chr: load_grt_final_path_by_chr(project_db_path)?,
        source_cards: load_grt_source_card_statuses(project_db_path)?,
        verification: load_persisted_grt_final_path_verification(project_db_path)?,
    })
}

pub fn load_persisted_grt_final_path_verification(
    project_db_path: &Path,
) -> Result<GrtFinalPathVerification> {
    let conn = open_workspace_db(project_db_path)?;
    let (chromosome_count, segment_count, q4_artifact_sha256): (i64, i64, String) = conn
        .query_row(
            "SELECT
                (SELECT COUNT(*) FROM grt_final_path_chr),
                (SELECT COUNT(*) FROM grt_final_path_segment),
                q4_artifact_sha256
             FROM grt_package
             WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .context("failed to load persisted GRT Final Path verification summary")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    Ok(GrtFinalPathVerification {
        chromosome_count: usize::try_from(chromosome_count)
            .context("persisted GRT chromosome count is invalid")?,
        segment_count: usize::try_from(segment_count)
            .context("persisted GRT segment count is invalid")?,
        q4_artifact_sha256,
    })
}

pub fn initialize_grt_project(
    project_db_path: &Path,
    project_name: &str,
) -> Result<GrtProjectInitializationSummary> {
    let recipe = load_grt_locked_recipe(project_db_path)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let options = list_initializer_options_with_connection(&conn)?;
    if options.references.len() != 1 {
        bail!(
            "GRT locked recipe requires exactly one imported reference, found {}",
            options.references.len()
        );
    }
    let reference_genome_id = options.references[0].id;
    let dataset_id_by_name = options
        .datasets
        .iter()
        .map(|dataset| (dataset.name.as_str(), dataset.id))
        .collect::<HashMap<_, _>>();
    let primary_dataset_id = dataset_id_by_name
        .get(recipe.primary_dataset.as_str())
        .copied()
        .ok_or_else(|| {
            anyhow!(
                "GRT locked primary dataset '{}' is not present in the workspace catalog",
                recipe.primary_dataset
            )
        })?;
    let support_dataset_ids =
        recipe
            .support_datasets
            .iter()
            .map(|name| {
                dataset_id_by_name.get(name.as_str()).copied().ok_or_else(|| {
                anyhow!(
                    "GRT locked support dataset '{}' is not present in the workspace catalog",
                    name
                )
            })
            })
            .collect::<Result<Vec<_>>>()?;

    let initialized = initialize_project_with_connection(
        &mut conn,
        &ProjectInitializationRequest {
            project_name: project_name.to_string(),
            reference_genome_id,
            primary_dataset_id,
            support_dataset_ids: support_dataset_ids.clone(),
            auto_check_new_seq: false,
            phased_assembly_enabled: Some(false),
            chr_assignment_min_coverage_percent: None,
            description: Some(format!("locked GRT recipe {}", recipe.recipe_id)),
        },
    )?;
    let project_id = initialized.project_id;
    let completed = (|| {
        let assembly = bootstrap_project_assembly_with_connection(&mut conn, project_id)?;
        let materialized_source_card_count =
            materialize_grt_source_cards_with_connection(&mut conn, project_id)?;
        verify_project_assignment_orientation_projection(&conn, project_id)?;
        set_project_auto_pipeline_done_with_connection(&mut conn, project_id, true)?;
        Ok((assembly, materialized_source_card_count))
    })();
    let (assembly, materialized_source_card_count) = match completed {
        Ok(value) => value,
        Err(error) => {
            delete_project_with_connection(&mut conn, project_id).with_context(|| {
                format!("failed to clean up incomplete locked GRT project after: {error:#}")
            })?;
            return Err(error);
        }
    };

    Ok(GrtProjectInitializationSummary {
        project_id,
        project_name: initialized.project_name,
        version: initialized.version,
        reference_genome_id: initialized.reference_genome_id,
        primary_dataset_id: initialized.primary_dataset_id,
        support_dataset_ids,
        project_dataset_count: initialized.project_dataset_count,
        phased_assembly_enabled: initialized.phased_assembly_enabled,
        chr_assignment_min_coverage_percent: initialized.chr_assignment_min_coverage_percent,
        assembly_seq_count: assembly.assembly_seq_count + materialized_source_card_count as i64,
        assembly_ctg_count: assembly.assembly_ctg_count + materialized_source_card_count as i64,
        materialized_source_card_count,
    })
}

fn materialize_grt_source_cards_with_connection(
    conn: &mut Connection,
    project_id: i64,
) -> Result<usize> {
    let source_cards = load_matching_json(
        conn,
        "SELECT row_json FROM grt_source_card ORDER BY source_card_key",
        |_| true,
    )?;
    let tx = conn
        .transaction()
        .context("failed to start GRT source-card materialization transaction")?;
    let created_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string();
    let mut inserted = 0_usize;
    for card in source_cards {
        let object = card
            .as_object()
            .ok_or_else(|| anyhow!("persisted GRT source card must be an object"))?;
        let placement_mode = json_nonempty_str(object, "placement_mode", "GRT source card")?;
        if placement_mode != "grt_promoted" && placement_mode != "cross_chr_grt_usage" {
            continue;
        }
        let source_card_key = json_nonempty_str(object, "source_card_key", "GRT source card")?;
        let dataset_name = json_nonempty_str(object, "dataset_name", "GRT source card")?;
        let contig_name = json_nonempty_str(object, "contig_name", "GRT source card")?;
        let target_chr = json_nonempty_str(object, "target_chr", "GRT source card")?;
        let anchor_start = parse_positive_i64(
            json_nonempty_str(object, "anchor_start", "GRT source card")?,
            "GRT source card.anchor_start",
        )?;
        let orient = orientation(
            json_nonempty_str(object, "orientation", "GRT source card")?,
            "GRT source card orientation",
        )?;
        let original_assignment =
            json_nonempty_str(object, "original_assignment", "GRT source card")?;
        let ref_alignment_status =
            json_nonempty_str(object, "ref_alignment_status", "GRT source card")?;
        let (source_seq_id, source_length): (i64, i64) = tx
            .query_row(
                "SELECT ss.id, ss.length
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 JOIN project_dataset pd ON pd.dataset_id = d.id
                 WHERE pd.project_id = ?1 AND d.name = ?2 AND ss.seq_name = ?3",
                params![project_id, dataset_name, contig_name],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .with_context(|| {
                format!(
                    "failed to resolve GRT source card {source_card_key} to a project source sequence"
                )
            })?;
        let already_visible: Option<(i64, String, Option<i64>, String)> = tx
            .query_row(
                "SELECT c.id, s.orient, c.anchor_start, c.placement_mode
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.project_id = ?1 AND s.source_seq_id = ?2 AND c.assigned_chr_name = ?3
                 LIMIT 1",
                params![project_id, source_seq_id, target_chr],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()
            .context("failed to check existing GRT source-card placement")?;
        if placement_mode == "normal" {
            let Some((_, existing_orient, existing_anchor, _)) = already_visible else {
                bail!("normal GRT source card {source_card_key} is absent from the main view");
            };
            if existing_orient != orient || existing_anchor != Some(anchor_start) {
                bail!(
                    "normal GRT source card {source_card_key} disagrees with the main-view source orientation or anchor"
                );
            }
            continue;
        }
        if let Some((_, existing_orient, existing_anchor, existing_mode)) = already_visible {
            if existing_orient != orient
                || existing_anchor != Some(anchor_start)
                || existing_mode != placement_mode
            {
                bail!(
                    "GRT source card {source_card_key} conflicts with an existing main-view placement"
                );
            }
            continue;
        }
        let assembly_seq_id = {
            tx.execute(
                "INSERT INTO assembly_seq (
                    project_id, source_seq_id, instance_key, orient, source_start, source_end,
                    left_end_type, right_end_type, hidden, created_at, note
                 ) VALUES (?1, ?2, ?3, ?4, 1, ?5, 'normal', 'normal', 0, ?6, ?7)",
                params![
                    project_id,
                    source_seq_id,
                    format!("grt:{source_card_key}"),
                    orient,
                    source_length,
                    created_at,
                    format!("grt_source_card_key={source_card_key}")
                ],
            )
            .with_context(|| format!("failed to materialize GRT source card {source_card_key}"))?;
            tx.last_insert_rowid()
        };
        let chr_order: i64 = tx
            .query_row(
                "SELECT COALESCE(MAX(chr_order), 0) + 1
                 FROM assembly_ctg
                 WHERE project_id = ?1 AND assigned_chr_name = ?2",
                params![project_id, target_chr],
                |row| row.get(0),
            )
            .context("failed to allocate GRT source-card chromosome order")?;
        let preferred_name = format!("{contig_name}@{target_chr}");
        let name_exists: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM assembly_ctg WHERE project_id = ?1 AND name = ?2)",
            params![project_id, preferred_name],
            |row| row.get::<_, i64>(0),
        )? > 0;
        let ctg_name = if name_exists {
            format!("{dataset_name}:{contig_name}@{target_chr}")
        } else {
            preferred_name
        };
        tx.execute(
            "INSERT INTO assembly_ctg (
                project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start,
                ref_orient, placement_mode, created_at, note
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                project_id,
                assembly_seq_id,
                ctg_name,
                target_chr,
                chr_order,
                anchor_start,
                orient,
                placement_mode,
                created_at,
                format!(
                    "grt_source_card_key={source_card_key}; original_assignment={original_assignment}; ref_alignment_status={ref_alignment_status}"
                )
            ],
        )
        .with_context(|| format!("failed to place GRT source card {source_card_key}"))?;
        inserted += 1;
    }
    tx.commit()
        .context("failed to commit GRT source-card materialization")?;
    Ok(inserted)
}

fn verify_project_assignment_orientation_projection(
    conn: &Connection,
    project_id: i64,
) -> Result<()> {
    let mut baseline_stmt = conn
        .prepare(
            "SELECT
                ica.source_seq_id,
                d.name,
                ss.seq_name,
                rc.chr_name,
                ica.source_orientation,
                ica.orientation_source,
                ica.anchor_start
             FROM imported_chr_assignment ica
             JOIN source_seq ss ON ss.id = ica.source_seq_id
             JOIN dataset d ON d.id = ss.dataset_id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             JOIN project_dataset pd ON pd.dataset_id = ss.dataset_id
             WHERE pd.project_id = ?1
             ORDER BY d.id, ss.id, rc.id",
        )
        .context("failed to prepare GRT assignment projection verification")?;
    let baselines = baseline_stmt
        .query_map(params![project_id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, i64>(6)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut projected_stmt = conn
        .prepare(
            "SELECT s.orient, c.anchor_start
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.project_id = ?1
               AND s.source_seq_id = ?2
               AND c.assigned_chr_name = ?3",
        )
        .context("failed to prepare projected GRT assignment query")?;
    for (
        source_seq_id,
        dataset_name,
        seq_name,
        chr_name,
        source_orientation,
        orientation_source,
        anchor_start,
    ) in baselines
    {
        if orientation_source != "ref_alignment" {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} has unsupported orientation_source={orientation_source}"
            );
        }
        let projected = projected_stmt
            .query_map(params![project_id, source_seq_id, chr_name], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, Option<i64>>(1)?))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        if projected.len() != 1 {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} projected {} main-view cards, expected 1",
                projected.len()
            );
        }
        let (projected_orientation, projected_anchor) = &projected[0];
        if projected_orientation != &source_orientation || *projected_anchor != Some(anchor_start) {
            bail!(
                "assignment baseline {dataset_name}:{seq_name}:{chr_name} disagrees with main-view source orientation or anchor"
            );
        }
    }
    Ok(())
}

pub fn load_grt_evidence(project_db_path: &Path, evidence_id: &str) -> Result<Value> {
    load_row_json(
        project_db_path,
        "grt_evidence",
        "evidence_id",
        evidence_id,
        "GRT evidence",
    )
}

pub fn verify_persisted_grt_final_path(project_db_path: &Path) -> Result<GrtFinalPathVerification> {
    let conn = open_workspace_db(project_db_path)?;
    let (final_path_json, final_q_relpath, expected_artifact_sha): (String, String, String) = conn
        .query_row(
            "SELECT final_path_json, final_q_relpath, q4_artifact_sha256
             FROM grt_package WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .context("failed to load persisted GRT Final Path verification inputs")?
        .ok_or_else(|| anyhow!("precomputed GRT Final Path is not available"))?;
    let final_path: Value = serde_json::from_str(&final_path_json)
        .context("persisted GRT Final Path JSON is invalid")?;
    let chromosomes = final_path["chromosomes"]
        .as_array()
        .ok_or_else(|| anyhow!("persisted GRT Final Path chromosomes are invalid"))?;
    let mut fasta_cache = HashMap::<String, BTreeMap<String, String>>::new();
    let mut rebuilt_records = BTreeMap::<String, String>::new();
    let mut segment_count = 0_usize;
    for chromosome in chromosomes {
        let object = chromosome
            .as_object()
            .ok_or_else(|| anyhow!("persisted GRT Final Path chromosome is invalid"))?;
        let chr_name = json_nonempty_str(object, "chr", "persisted Final Path chromosome")?;
        let segments = object["segments"]
            .as_array()
            .ok_or_else(|| anyhow!("persisted Final Path {chr_name} segments are invalid"))?;
        let mut rebuilt = String::new();
        for segment in segments {
            segment_count += 1;
            let segment_object = segment
                .as_object()
                .ok_or_else(|| anyhow!("persisted Final Path segment is invalid"))?;
            let length = json_positive_i64(segment_object, "length", "persisted segment")?;
            if segment_object.get("kind").and_then(Value::as_str) == Some("gap") {
                rebuilt.push_str(&"N".repeat(length as usize));
                continue;
            }
            let source = segment_object["source"]
                .as_object()
                .ok_or_else(|| anyhow!("persisted Final Path source is invalid"))?;
            let dataset = json_nonempty_str(source, "dataset", "persisted segment source")?;
            let contig = json_nonempty_str(source, "contig", "persisted segment source")?;
            let fasta_path: String = conn
                .query_row(
                    "SELECT ssl.fasta_path
                     FROM source_seq_locator ssl
                     JOIN source_seq ss ON ss.id = ssl.source_seq_id
                     JOIN dataset d ON d.id = ss.dataset_id
                     WHERE d.name = ?1 AND ss.seq_name = ?2",
                    params![dataset, contig],
                    |row| row.get(0),
                )
                .with_context(|| format!("failed to locate persisted source {dataset}:{contig}"))?;
            if !fasta_cache.contains_key(&fasta_path) {
                fasta_cache.insert(
                    fasta_path.clone(),
                    read_fasta(Path::new(&fasta_path), &fasta_path, false)?,
                );
            }
            let source_sequence = fasta_cache[&fasta_path].get(contig).ok_or_else(|| {
                anyhow!("persisted source {dataset}:{contig} is absent from its FASTA")
            })?;
            let start = json_positive_i64(source, "start", "persisted segment source")?;
            let end = json_positive_i64(source, "end", "persisted segment source")?;
            if start > end || end as usize > source_sequence.len() || end - start + 1 != length {
                return Err(anyhow!(
                    "persisted Final Path source interval is invalid for {dataset}:{contig}"
                ));
            }
            let orient = orientation(
                json_str(source, "orientation", "persisted segment source")?,
                "persisted segment source",
            )?;
            rebuilt.push_str(&orient_sequence(
                &source_sequence[(start - 1) as usize..end as usize],
                orient,
            ));
        }
        if rebuilt.len() != json_positive_i64(object, "q4_length", chr_name)? as usize
            || sha256_bytes(rebuilt.as_bytes()) != json_nonempty_str(object, "q4_sha256", chr_name)?
        {
            return Err(anyhow!(
                "persisted Final Path does not reconstruct q4 checksum for {chr_name}"
            ));
        }
        rebuilt_records.insert(chr_name.to_string(), rebuilt);
    }
    let workspace_root = project_db_path
        .parent()
        .ok_or_else(|| anyhow!("workspace database has no parent directory"))?;
    let q4_path = workspace_root.join(final_q_relpath);
    let actual_artifact_sha = sha256_file(&q4_path)?;
    if actual_artifact_sha != expected_artifact_sha {
        return Err(anyhow!("persisted q4 artifact checksum mismatch"));
    }
    let q4_records = read_fasta(&q4_path, "persisted q4 FASTA", false)?;
    if q4_records != rebuilt_records {
        return Err(anyhow!(
            "persisted Final Path sequences differ from q4 FASTA"
        ));
    }
    Ok(GrtFinalPathVerification {
        chromosome_count: chromosomes.len(),
        segment_count,
        q4_artifact_sha256: actual_artifact_sha,
    })
}

pub fn load_grt_source_card_trace(
    project_db_path: &Path,
    source_card_key: &str,
) -> Result<GrtSourceCardTrace> {
    let conn = open_workspace_db(project_db_path)?;
    let source_card = load_row_json_with_conn(
        &conn,
        "grt_source_card",
        "source_card_key",
        source_card_key,
        "GRT source card",
    )?;
    let card = source_card
        .as_object()
        .ok_or_else(|| anyhow!("persisted GRT source card JSON is invalid"))?;
    let event_ids = stored_string_list(card, "accepted_event_ids_json")?;
    let segment_ids = stored_string_list(card, "final_path_segment_ids_json")?;
    let ref_ids = stored_string_list(card, "ref_evidence_ids_json")?;
    let pairwise_ids = stored_string_list(card, "pairwise_evidence_ids_json")?;
    let donor_usage = load_matching_json(
        &conn,
        "SELECT row_json FROM grt_donor_usage ORDER BY usage_id",
        |value| {
            value
                .get("event_id")
                .and_then(Value::as_str)
                .is_some_and(|id| event_ids.iter().any(|candidate| candidate == id))
        },
    )?;
    let member_keys = donor_usage
        .iter()
        .filter_map(|value| {
            Some((
                value.get("donor_set_id")?.as_str()?.to_string(),
                value.get("member_id")?.as_str()?.to_string(),
            ))
        })
        .collect::<HashSet<_>>();
    let donor_set_ids = member_keys
        .iter()
        .map(|(donor_set_id, _)| donor_set_id.clone())
        .collect::<HashSet<_>>();
    let donor_members = load_matching_json(
        &conn,
        "SELECT row_json FROM grt_donor_member ORDER BY donor_set_id, member_id",
        |value| {
            value
                .get("donor_set_id")
                .and_then(Value::as_str)
                .zip(value.get("member_id").and_then(Value::as_str))
                .is_some_and(|(donor_set_id, member_id)| {
                    member_keys.contains(&(donor_set_id.to_string(), member_id.to_string()))
                })
        },
    )?;
    Ok(GrtSourceCardTrace {
        source_card,
        accepted_events: load_many_json(&conn, "grt_event", "event_id", "event_json", &event_ids)?,
        final_path_segments: load_many_json(
            &conn,
            "grt_final_path_segment",
            "segment_id",
            "segment_json",
            &segment_ids,
        )?,
        ref_evidence: load_many_json(&conn, "grt_evidence", "evidence_id", "row_json", &ref_ids)?,
        pairwise_evidence: load_many_json(
            &conn,
            "grt_evidence",
            "evidence_id",
            "row_json",
            &pairwise_ids,
        )?,
        donor_usage,
        donor_members,
        donor_sets: load_matching_json(
            &conn,
            "SELECT row_json FROM grt_donor_set ORDER BY donor_set_id",
            |value| {
                value
                    .get("donor_set_id")
                    .and_then(Value::as_str)
                    .is_some_and(|id| donor_set_ids.contains(id))
            },
        )?,
    })
}

pub fn load_grt_event_trace(project_db_path: &Path, event_id: &str) -> Result<GrtEventTrace> {
    let conn = open_workspace_db(project_db_path)?;
    let event = load_json_column_with_conn(
        &conn,
        "grt_event",
        "event_id",
        event_id,
        "event_json",
        "GRT event",
    )?;
    let object = event
        .as_object()
        .ok_or_else(|| anyhow!("persisted GRT event JSON is invalid"))?;
    let evidence_ids = object
        .get("evidence_ids")
        .map(|value| json_value_string_list(value, "event evidence_ids"))
        .transpose()?
        .unwrap_or_default();
    let usage_ids = object
        .get("usage_ids")
        .map(|value| json_value_string_list(value, "event usage_ids"))
        .transpose()?
        .unwrap_or_default();
    let segment_id = object
        .get("final_path_segment_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let source_card_key = object
        .get("source_card_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    Ok(GrtEventTrace {
        event,
        evidence: load_many_json(
            &conn,
            "grt_evidence",
            "evidence_id",
            "row_json",
            &evidence_ids,
        )?,
        donor_usage: load_many_json(&conn, "grt_donor_usage", "usage_id", "row_json", &usage_ids)?,
        final_path_segment: if segment_id.is_empty() {
            None
        } else {
            Some(load_json_column_with_conn(
                &conn,
                "grt_final_path_segment",
                "segment_id",
                &segment_id,
                "segment_json",
                "GRT Final Path segment",
            )?)
        },
        source_card: if source_card_key.is_empty() {
            None
        } else {
            Some(load_row_json_with_conn(
                &conn,
                "grt_source_card",
                "source_card_key",
                &source_card_key,
                "GRT source card",
            )?)
        },
    })
}

fn load_row_json(
    project_db_path: &Path,
    table: &str,
    key_column: &str,
    key: &str,
    label: &str,
) -> Result<Value> {
    let conn = open_workspace_db(project_db_path)?;
    load_row_json_with_conn(&conn, table, key_column, key, label)
}
fn load_row_json_with_conn(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    key: &str,
    label: &str,
) -> Result<Value> {
    load_json_column_with_conn(conn, table, key_column, key, "row_json", label)
}
fn load_json_column_with_conn(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    key: &str,
    json_column: &str,
    label: &str,
) -> Result<Value> {
    let sql = format!("SELECT {json_column} FROM {table} WHERE {key_column} = ?1");
    let json: String = conn
        .query_row(&sql, params![key], |row| row.get(0))
        .optional()
        .with_context(|| format!("failed to query {label}"))?
        .ok_or_else(|| anyhow!("{label} does not exist: {key}"))?;
    serde_json::from_str(&json).with_context(|| format!("persisted {label} JSON is invalid"))
}
fn load_many_json(
    conn: &rusqlite::Connection,
    table: &str,
    key_column: &str,
    json_column: &str,
    ids: &[String],
) -> Result<Vec<Value>> {
    ids.iter()
        .map(|id| load_json_column_with_conn(conn, table, key_column, id, json_column, table))
        .collect()
}
fn load_matching_json(
    conn: &rusqlite::Connection,
    sql: &str,
    predicate: impl Fn(&Value) -> bool,
) -> Result<Vec<Value>> {
    let mut stmt = conn.prepare(sql)?;
    let values = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    values
        .into_iter()
        .map(|json| serde_json::from_str(&json).context("persisted GRT row JSON is invalid"))
        .filter_map(|result| match result {
            Ok(value) if predicate(&value) => Some(Ok(value)),
            Ok(_) => None,
            Err(error) => Some(Err(error)),
        })
        .collect()
}
fn stored_string_list(object: &Map<String, Value>, key: &str) -> Result<Vec<String>> {
    let encoded = object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("persisted GRT source card lacks {key}"))?;
    serde_json::from_str(encoded)
        .with_context(|| format!("persisted GRT source card {key} is invalid"))
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::io::Write;

    use serde_json::Value;
    use tempfile::tempdir;
    use zip::CompressionMethod;
    use zip::write::FileOptions;

    use super::*;

    fn fixture_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/grt_contract_v1/valid/gpm_server")
    }

    fn invalid_cases_path() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/grt_contract_v1/invalid_cases.json")
    }

    fn copy_tree(source: &Path, target: &Path) {
        fs::create_dir_all(target).unwrap();
        for entry in fs::read_dir(source).unwrap() {
            let entry = entry.unwrap();
            let source_path = entry.path();
            let target_path = target.join(entry.file_name());
            if source_path.is_dir() {
                copy_tree(&source_path, &target_path);
            } else {
                fs::copy(source_path, target_path).unwrap();
            }
        }
    }

    fn write_bundle_zip(source: &Path, zip_path: &Path) {
        let file = fs::File::create(zip_path).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        append_tree_to_zip(&mut zip, source, Path::new("gpm_server"));
        zip.finish().unwrap();
    }

    fn append_tree_to_zip(zip: &mut zip::ZipWriter<fs::File>, source: &Path, archive_path: &Path) {
        let options = FileOptions::default().compression_method(CompressionMethod::Stored);
        zip.add_directory(
            format!("{}/", archive_path.to_string_lossy().replace('\\', "/")),
            options,
        )
        .unwrap();
        for entry in fs::read_dir(source).unwrap() {
            let entry = entry.unwrap();
            let source_path = entry.path();
            let child_archive_path = archive_path.join(entry.file_name());
            if source_path.is_dir() {
                append_tree_to_zip(zip, &source_path, &child_archive_path);
            } else {
                zip.start_file(
                    child_archive_path.to_string_lossy().replace('\\', "/"),
                    options,
                )
                .unwrap();
                zip.write_all(&fs::read(source_path).unwrap()).unwrap();
            }
        }
    }

    #[test]
    fn validates_shared_grt_v1_fixture() {
        let package = validate_grt_package(&fixture_root()).unwrap();
        assert_eq!(package.final_path["workflow"].as_str(), Some(GRT_WORKFLOW));
        assert_eq!(package.events.len(), 1);
    }

    #[test]
    fn reports_grt_validation_stages_in_execution_order() {
        let mut stages = Vec::new();
        let package = validate_grt_package_with_progress(&fixture_root(), &mut |stage, _detail| {
            stages.push(stage)
        })
        .unwrap();

        assert_eq!(package.events.len(), 1);
        assert_eq!(
            stages,
            vec![
                "validate_grt_required_files",
                "validate_grt_metadata_tables",
                "validate_grt_source_fastas",
                "validate_grt_recipe",
                "validate_grt_q_artifacts",
                "validate_grt_donor_artifacts",
                "validate_grt_evidence",
                "validate_grt_final_path",
                "validate_grt_trace_integrity",
            ]
        );
    }

    #[test]
    fn reports_recipe_validation_before_quoted_json_failure() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let recipe_path = bundle_root.join("metadata/grt_recipe.tsv");
        let recipe = fs::read_to_string(&recipe_path).unwrap();
        fs::write(
            recipe_path,
            recipe.replace("\"[\"\"support\"\"]\"", "not-json"),
        )
        .unwrap();

        let mut stages = Vec::new();
        let error = validate_grt_package_with_progress(&bundle_root, &mut |stage, _detail| {
            stages.push(stage)
        })
        .unwrap_err();

        assert!(error.to_string().contains("GRT_IMPORT_INVALID_JSON"));
        assert_eq!(stages.last(), Some(&"validate_grt_recipe"));
    }

    #[test]
    fn reads_standard_quoted_tsv_fields() {
        let temp = tempdir().unwrap();
        fs::write(
            temp.path().join("quoted.tsv"),
            concat!(
                "id\tpayload\tnote\n",
                "row-1\t\"{\"\"items\"\":[\"\"a\"\",\"\"b\"\"]}\"\t\"left\tright\"\n"
            ),
        )
        .unwrap();

        let table = read_tsv(
            temp.path(),
            "quoted.tsv",
            &["id", "payload", "note"],
            1,
            Some(1),
        )
        .unwrap();
        assert_eq!(
            field(&table.rows[0], "payload").unwrap(),
            r#"{"items":["a","b"]}"#
        );
        assert_eq!(field(&table.rows[0], "note").unwrap(), "left\tright");
    }

    #[test]
    fn rejects_inconsistent_quoted_tsv_width_with_stable_code() {
        let temp = tempdir().unwrap();
        fs::write(
            temp.path().join("bad.tsv"),
            "id\tpayload\nrow-1\tvalue\textra\n",
        )
        .unwrap();

        let error = read_tsv(temp.path(), "bad.tsv", &["id", "payload"], 1, Some(1)).unwrap_err();
        assert!(error.to_string().contains("GRT_IMPORT_INVALID_TSV"));
    }

    #[test]
    fn rejects_all_shared_invalid_fixture_mutations_with_stable_codes() {
        let cases: Vec<Value> =
            serde_json::from_slice(&fs::read(invalid_cases_path()).unwrap()).unwrap();
        for case in cases {
            let temp = tempdir().unwrap();
            let bundle_root = temp.path().join("gpm_server");
            copy_tree(&fixture_root(), &bundle_root);
            let operation = case["operation"].as_object().unwrap();
            let path = bundle_root.join(operation["path"].as_str().unwrap());
            match operation["type"].as_str().unwrap() {
                "remove" => fs::remove_file(path).unwrap(),
                "replace_text" => {
                    let original = fs::read_to_string(&path).unwrap();
                    let old = operation["old"].as_str().unwrap();
                    let new = operation["new"].as_str().unwrap();
                    assert!(original.contains(old));
                    fs::write(path, original.replacen(old, new, 1)).unwrap();
                }
                other => panic!("unsupported fixture mutation {other}"),
            }
            let error = validate_grt_package(&bundle_root).unwrap_err();
            let expected = format!("GRT_IMPORT_{}", case["expected_code"].as_str().unwrap());
            assert!(
                error.to_string().contains(&expected),
                "case {} expected {expected}, got {error:#}",
                case["name"].as_str().unwrap()
            );
        }
    }

    #[test]
    fn imports_shared_fixture_and_round_trips_recipe_final_path_and_trace_links() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let attempts_path = bundle_root.join("metadata/grt_gap_attempts.tsv");
        let attempts = fs::read_to_string(&attempts_path).unwrap();
        fs::write(
            attempts_path,
            format!(
                "{attempts}attempt-terminal-right\tChr01\tterminal-right\tstep4_telomere\tunresolved\tno_candidate\t0\t\n"
            ),
        )
        .unwrap();

        let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
        let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
        assert_eq!(recipe.recipe_id, "recipe-test");
        assert_eq!(recipe.primary_dataset, "primary");
        assert_eq!(recipe.support_datasets, vec!["support"]);

        let final_path = load_grt_final_path(&outcome.project_db_path).unwrap();
        assert_eq!(
            final_path["chromosomes"][0]["q4_sha256"],
            "a6c7cf707ec32204560c3967f3af57cb57cd3faa8302c0a1a6f36a5d78abfa2e"
        );
        let final_path_by_chr = load_grt_final_path_by_chr(&outcome.project_db_path).unwrap();
        assert_eq!(final_path_by_chr.len(), 1);
        assert_eq!(
            final_path_by_chr["Chr01"]["segments"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        assert!(
            final_path_by_chr["Chr01"]["segments"][0]
                .get("event_id")
                .is_none()
        );
        assert!(
            final_path_by_chr["Chr01"]["segments"][1]
                .get("evidence_ids")
                .is_none()
        );
        let object_attempts = load_grt_object_attempts(&outcome.project_db_path).unwrap();
        assert_eq!(object_attempts.len(), 2);
        assert_eq!(object_attempts[0]["object_kind"], "gap");
        assert_eq!(object_attempts[1]["object_kind"], "terminal");

        let card = load_grt_source_card_trace(
            &outcome.project_db_path,
            "support:donor1:Chr01:grt_promoted",
        )
        .unwrap();
        assert_eq!(card.accepted_events.len(), 1);
        assert_eq!(card.final_path_segments.len(), 1);
        assert_eq!(card.ref_evidence.len(), 1);
        assert_eq!(card.pairwise_evidence.len(), 1);
        assert_eq!(card.donor_usage.len(), 1);
        assert_eq!(card.donor_members.len(), 1);
        assert_eq!(card.donor_sets.len(), 1);
        let evidence = load_grt_evidence(&outcome.project_db_path, "ev-step1-round1").unwrap();
        assert_eq!(evidence["source_start"], "1");
        assert_eq!(evidence["source_end"], "4");
        assert_eq!(evidence["target_start"], "5");
        assert_eq!(evidence["target_end"], "8");
        assert_eq!(evidence["coordinate_system"], "paf_0_based_half_open");
        assert_eq!(evidence["projection_status"], "projected");

        let event = load_grt_event_trace(&outcome.project_db_path, "evt-step1-round1").unwrap();
        assert_eq!(event.evidence.len(), 1);
        assert_eq!(event.donor_usage.len(), 1);
        assert!(event.final_path_segment.is_some());
        assert!(event.source_card.is_some());

        let verification = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap();
        assert_eq!(verification.chromosome_count, 1);
        assert_eq!(verification.segment_count, 2);
        assert_eq!(verification.q4_artifact_sha256, recipe.q4_artifact_sha256);
    }

    #[test]
    fn initializes_locked_recipe_and_materializes_used_unplaced_source_card() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();

        let initialized = initialize_grt_project(&outcome.project_db_path, "locked-project")
            .expect("initialize locked GRT project");
        assert_eq!(initialized.primary_dataset_id, 1);
        assert_eq!(initialized.support_dataset_ids, vec![2]);
        assert_eq!(initialized.project_dataset_count, 2);
        assert_eq!(initialized.assembly_seq_count, 4);
        assert_eq!(initialized.assembly_ctg_count, 4);
        assert_eq!(initialized.materialized_source_card_count, 1);

        let conn = open_workspace_db(&outcome.project_db_path).unwrap();
        let promoted: (String, String, String, String) = conn
            .query_row(
                "SELECT d.name, ss.seq_name, c.assigned_chr_name, c.placement_mode
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 JOIN source_seq ss ON ss.id = s.source_seq_id
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE c.project_id = ?1 AND c.placement_mode = 'grt_promoted'",
                params![initialized.project_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert_eq!(
            promoted,
            (
                "support".to_string(),
                "donor1".to_string(),
                "Chr01".to_string(),
                "grt_promoted".to_string(),
            )
        );
        let auto_pipeline_done: i64 = conn
            .query_row(
                "SELECT auto_pipeline_done FROM project WHERE id = ?1",
                params![initialized.project_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(auto_pipeline_done, 1);
        let final_counts: (i64, i64) = conn
            .query_row(
                "SELECT
                    (SELECT COUNT(*) FROM assembly_seq WHERE project_id = ?1),
                    (SELECT COUNT(*) FROM assembly_ctg WHERE project_id = ?1)",
                params![initialized.project_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert_eq!(final_counts, (4, 4));

        let view = load_grt_project_view(&outcome.project_db_path).unwrap();
        assert_eq!(view.recipe.recipe_id, "recipe-test");
        assert_eq!(view.final_path_by_chr.len(), 1);
        assert_eq!(view.source_cards.len(), 1);
        assert_eq!(view.source_cards[0].placement_mode, "grt_promoted");
        let serialized = serde_json::to_value(&view).unwrap();
        assert!(serialized.get("object_attempts").is_none());
        assert_eq!(serialized["source_cards"][0].as_object().unwrap().len(), 6);
        assert!(
            serialized["source_cards"][0]
                .get("accepted_events")
                .is_none()
        );
        assert!(
            serialized["final_path_by_chr"]["Chr01"]["segments"][0]
                .get("event_id")
                .is_none()
        );
    }

    #[test]
    fn project_view_reuses_persisted_verification_without_reading_q4() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
        let expected = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap();
        let recipe = load_grt_locked_recipe(&outcome.project_db_path).unwrap();
        let q4_path = outcome
            .project_db_path
            .parent()
            .unwrap()
            .join(recipe.final_q_relpath);
        fs::remove_file(&q4_path).unwrap();

        let view = load_grt_project_view(&outcome.project_db_path).unwrap();
        assert_eq!(view.verification, expected);

        let error = verify_persisted_grt_final_path(&outcome.project_db_path).unwrap_err();
        assert!(error.to_string().contains("failed to read artifact"));
    }

    #[test]
    fn initialization_cleans_project_when_assignment_projection_is_corrupted() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        let (outcome, _) = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap();
        let conn = open_workspace_db(&outcome.project_db_path).unwrap();
        let primary_source_seq_id: i64 = conn
            .query_row(
                "SELECT ss.id
                 FROM source_seq ss
                 JOIN dataset d ON d.id = ss.dataset_id
                 WHERE d.name = 'primary' AND ss.seq_name = 'primary1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        conn.execute_batch(&format!(
            "CREATE TRIGGER corrupt_assignment_projection
             AFTER INSERT ON assembly_seq
             WHEN NEW.source_seq_id = {primary_source_seq_id}
             BEGIN
                 UPDATE assembly_seq SET orient = '-' WHERE id = NEW.id;
             END;"
        ))
        .unwrap();
        drop(conn);

        let error = initialize_grt_project(&outcome.project_db_path, "corrupt-project")
            .expect_err("projection mismatch must reject locked project initialization");
        assert!(
            error
                .to_string()
                .contains("disagrees with main-view source orientation or anchor")
        );

        let conn = open_workspace_db(&outcome.project_db_path).unwrap();
        let project_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM project WHERE name = 'corrupt-project'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(project_count, 0);
    }

    #[test]
    fn invalid_and_legacy_extracted_packages_create_no_workspace_database() {
        for legacy in [false, true] {
            let temp = tempdir().unwrap();
            let bundle_root = temp.path().join("gpm_server");
            copy_tree(&fixture_root(), &bundle_root);
            if legacy {
                fs::write(
                    bundle_root.join("metadata/package.tsv"),
                    "package_mode\tsequence_layout\tpreassigned_chr\nfull\tpartitioned\ttrue\n",
                )
                .unwrap();
            } else {
                fs::remove_file(bundle_root.join("metadata/grt_recipe.tsv")).unwrap();
            }

            let error = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap_err();
            assert!(error.to_string().contains(if legacy {
                "GRT_IMPORT_INVALID_TSV"
            } else {
                "GRT_IMPORT_MISSING_REQUIRED_FILE"
            }));
            assert!(!bundle_root.join("project.sqlite").exists());
            assert!(!bundle_root.join("exports").exists());
            assert!(!bundle_root.join("cache").exists());
        }
    }

    #[test]
    fn malformed_fai_is_rejected_before_workspace_creation() {
        let temp = tempdir().unwrap();
        let bundle_root = temp.path().join("gpm_server");
        copy_tree(&fixture_root(), &bundle_root);
        fs::write(
            bundle_root.join("data/datasets/primary.fa.fai"),
            "primary1\t3\t10\t4\t5\n",
        )
        .unwrap();

        let error = crate::importer::import_from_extracted_bundle(&bundle_root).unwrap_err();
        assert!(error.to_string().contains("GRT_IMPORT_COUNT_MISMATCH"));
        assert!(!bundle_root.join("project.sqlite").exists());
    }

    #[test]
    fn zip_import_round_trips_and_rejected_zip_leaves_no_workspace() {
        let temp = tempdir().unwrap();
        let valid_source = temp.path().join("valid_source");
        copy_tree(&fixture_root(), &valid_source);
        let valid_zip = temp.path().join("valid.zip");
        write_bundle_zip(&valid_source, &valid_zip);
        let valid_workspace = temp.path().join("valid_workspace");
        let (outcome, _) = crate::importer::import_from_zip(&valid_zip, &valid_workspace).unwrap();
        assert_eq!(
            load_grt_locked_recipe(&outcome.project_db_path)
                .unwrap()
                .recipe_id,
            "recipe-test"
        );

        let invalid_source = temp.path().join("invalid_source");
        copy_tree(&fixture_root(), &invalid_source);
        fs::remove_file(invalid_source.join("metadata/grt_recipe.tsv")).unwrap();
        let invalid_zip = temp.path().join("invalid.zip");
        write_bundle_zip(&invalid_source, &invalid_zip);
        let invalid_workspace = temp.path().join("invalid_workspace");
        let error = crate::importer::import_from_zip(&invalid_zip, &invalid_workspace).unwrap_err();
        assert!(
            error
                .to_string()
                .contains("GRT_IMPORT_MISSING_REQUIRED_FILE")
        );
        assert!(!invalid_workspace.exists());
    }
}
