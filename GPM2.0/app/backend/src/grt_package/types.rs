use super::*;

pub const GRT_WORKFLOW: &str = "gpm_grt_precomputed_v2";
pub const GRT_APP_WORKFLOW: &str = "gpm_grt_app_precomputed_v2";
pub const GRT_SCHEMA_VERSION: &str = "2";
pub const GRT_FINAL_PATH_SCHEMA_VERSION: &str = "1";

pub(super) type TsvRow = BTreeMap<String, String>;
pub(super) type AppQ4Validation = (BTreeMap<String, usize>, Option<BTreeMap<String, String>>);

#[derive(Debug, Clone)]
pub(super) struct TsvTable {
    pub(super) rows: Vec<TsvRow>,
}

#[derive(Debug, Clone)]
pub(crate) struct ValidatedGrtPackage {
    pub(super) tables: HashMap<&'static str, TsvTable>,
    pub(super) events: Vec<Value>,
    pub(super) final_path: Value,
    pub(super) q0_artifact_sha256: String,
    pub(super) q4_artifact_sha256: String,
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

pub(super) const REQUIRED_FILES: &[&str] = &[
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
    "metadata/grt_donor_fragments.tsv",
    "metadata/grt_evidence_registry.tsv",
    "metadata/grt_donor_usage.tsv",
    "metadata/grt_used_contigs.tsv",
    "metadata/grt_events.jsonl",
    "metadata/grt_gap_attempts.tsv",
    "metadata/grt_step2_strategies.tsv",
    "metadata/grt_step3_classifications.tsv",
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

pub(super) const PACKAGE_HEADER: &[&str] = &[
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
pub(super) const REFERENCE_HEADER: &[&str] = &[
    "reference_name",
    "species_name",
    "assembly_label",
    "fasta_relpath",
    "fai_relpath",
];
pub(super) const DATASETS_HEADER: &[&str] = &[
    "dataset_name",
    "assembler",
    "assembler_version",
    "fasta_relpath",
    "fai_relpath",
    "self_alignment_available",
];
pub(super) const SOURCE_LOCATOR_HEADER: &[&str] = &["dataset_name", "seq_name", "fasta_relpath"];
pub(super) const SOURCE_N_REGIONS_HEADER: &[&str] = &[
    "dataset_name",
    "seq_name",
    "start_bp",
    "end_bp",
    "length_bp",
];
pub(super) const TRACK_MEMBER_ORDERS_HEADER: &[&str] = &[
    "target_track",
    "target_chr",
    "member_dataset",
    "member_ctg",
    "member_order",
];
pub(super) const REFERENCE_CHR_LOCATOR_HEADER: &[&str] = &["reference_chr_name", "fasta_relpath"];
pub(super) const CHR_ASSIGNMENTS_HEADER: &[&str] = &[
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
pub(super) const RECIPE_HEADER: &[&str] = &[
    "recipe_id",
    "primary_dataset",
    "support_datasets_json",
    "reads_qc_enabled",
    "donor_set_id",
    "tel_donor_set_id",
    "q0_relpath",
    "final_q_relpath",
];
pub(super) const CONTIG_ROLES_HEADER: &[&str] = &[
    "dataset_name",
    "contig_name",
    "q_eligible",
    "donor_eligible",
    "tel_donor_eligible",
    "q_rejection_reason",
    "donor_rejection_reason",
    "tel_rejection_reason",
];
pub(super) const Q_SEGMENTS_HEADER: &[&str] = &[
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
pub(super) const DONOR_SETS_HEADER: &[&str] = &[
    "donor_set_id",
    "donor_kind",
    "manifest_relpath",
    "fasta_relpath",
    "fasta_sha256",
    "member_count",
];
pub(super) const DONOR_MEMBERS_HEADER: &[&str] = &[
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
pub(super) const DONOR_FRAGMENTS_HEADER: &[&str] = &[
    "donor_set_id",
    "member_id",
    "fragment_id",
    "fasta_record_name",
    "fragment_start",
    "fragment_end",
    "fragment_length",
    "sequence_sha256",
    "left_boundary",
    "right_boundary",
];
pub(super) const EVIDENCE_HEADER: &[&str] = &[
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
pub(super) const USAGE_HEADER: &[&str] = &[
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
pub(super) const USED_CONTIGS_HEADER: &[&str] = &[
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
pub(super) const GAP_ATTEMPTS_HEADER: &[&str] = &[
    "attempt_id",
    "chr",
    "object_id",
    "stage",
    "status",
    "reason",
    "candidate_count",
    "accepted_event_id",
];
pub(super) const STEP2_STRATEGIES_HEADER: &[&str] = &[
    "chr",
    "strategy",
    "strategy_applied",
    "gap_count",
    "patch_candidate_count",
    "validated_patch_count",
    "accepted_patch_count",
    "fallback_candidate_count",
    "accepted_fallback_count",
    "reason",
];
pub(super) const STEP3_CLASSIFICATIONS_HEADER: &[&str] = &[
    "chr",
    "object_id",
    "candidate_id",
    "error_type",
    "error_subtype",
    "error_features_json",
    "confidence",
    "confidence_score",
    "gap_in_error_region",
    "repair_mode",
    "repair_reason",
    "outcome",
    "event_id",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
];
pub(super) const STAGE_STATUS_HEADER: &[&str] = &[
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
pub(super) const TOOL_VERSIONS_HEADER: &[&str] = &["tool", "version", "executable"];

pub(super) const TABLE_SPECS: &[(&str, &[&str], usize, Option<usize>)] = &[
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
        "metadata/grt_donor_fragments.tsv",
        DONOR_FRAGMENTS_HEADER,
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
        "metadata/grt_step2_strategies.tsv",
        STEP2_STRATEGIES_HEADER,
        1,
        None,
    ),
    (
        "metadata/grt_step3_classifications.tsv",
        STEP3_CLASSIFICATIONS_HEADER,
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

pub(super) const STAGE_TRANSITIONS: &[(&str, &str, &str)] = &[
    ("donor_freeze", "q0", "q0"),
    ("step1_round1", "q0", "q0r1"),
    ("step1_filter", "q0r1", "q0f"),
    ("step1_round2", "q0f", "q1"),
    ("step2", "q1", "q2"),
    ("step3", "q2", "q3"),
    ("step4_telomere", "q3", "q4"),
    ("finalize", "q4", "q4"),
];
