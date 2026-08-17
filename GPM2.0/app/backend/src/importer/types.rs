use super::*;

pub const EXPORTS_DIR: &str = "exports";
pub const CACHE_DIR: &str = "cache";
pub const PROJECT_DB_NAME: &str = "project.sqlite";
pub(super) const ZIP_IMPORT_PHASE_TOTAL: usize = 7;
pub(super) const EXTRACTED_IMPORT_PHASE_TOTAL: usize = 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImportMode {
    ExtractedBundle,
    ZipDelivery,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportProgress {
    pub stage: &'static str,
    pub detail: String,
    pub progress_index: Option<usize>,
    pub progress_total: Option<usize>,
    pub phase_index: Option<usize>,
    pub phase_total: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportOutcome {
    pub mode: ImportMode,
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddDatasetImportOutcome {
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
    pub project_id: Option<i64>,
    pub dataset_id: i64,
    pub dataset_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddCtgImportOutcome {
    pub bundle_root: PathBuf,
    pub workspace_root: PathBuf,
    pub project_db_path: PathBuf,
    pub project_id: i64,
    pub dataset_id: i64,
    pub source_seq_id: i64,
    pub assembly_ctg_id: Option<i64>,
    pub ctg_name: String,
    pub target_track: String,
    pub target_chr: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AddCtgImportTarget {
    pub target_chr: String,
    pub target_track: String,
}

#[derive(Debug)]
pub(super) struct ReferenceRow {
    pub(super) name: String,
    pub(super) species_name: String,
    pub(super) assembly_label: String,
    pub(super) fasta_relpath: String,
    pub(super) fai_relpath: String,
}

#[derive(Debug)]
pub(super) struct DatasetRow {
    pub(super) name: String,
    pub(super) assembler: String,
    pub(super) assembler_version: Option<String>,
    pub(super) fasta_relpath: String,
    pub(super) fai_relpath: String,
    pub(super) self_alignment_available: bool,
}

#[derive(Debug, Clone)]
pub(super) struct PackageRow {
    pub(super) package_mode: String,
    pub(super) sequence_layout: String,
    pub(super) preassigned_chr: bool,
    pub(super) chr_assignment_min_coverage_percent: f64,
    pub(super) self_alignment_scope: String,
    pub(super) cross_alignment_scope: String,
}

#[derive(Debug, Clone)]
pub(super) struct AddDatasetManifest {
    pub(super) dataset_name: String,
    pub(super) reference_name: String,
    pub(super) sequence_layout: String,
    pub(super) preassigned_chr: bool,
    pub(super) chr_assignment_min_coverage_percent: f64,
    pub(super) alignment_engine: String,
    pub(super) minimap_preset: String,
    pub(super) blastn_task: String,
    pub(super) blastn_evalue: String,
    pub(super) blastn_dust: String,
    pub(super) winnowmap_preset: String,
    pub(super) winnowmap_kmer: String,
    pub(super) winnowmap_repeat_fraction: String,
    pub(super) skip_self: bool,
    pub(super) self_alignment_available: bool,
    pub(super) tel_enabled: bool,
    pub(super) cen_enabled: bool,
}

#[derive(Debug, Clone)]
pub(super) struct AddCtgManifest {
    pub(super) ctg_name: String,
    pub(super) derived_dataset: String,
    pub(super) target_chr: String,
    pub(super) target_track: String,
    pub(super) source: String,
    pub(super) reference_name: String,
    pub(super) alignment_engine: String,
    pub(super) minimap_preset: String,
    pub(super) blastn_task: String,
    pub(super) blastn_evalue: String,
    pub(super) blastn_dust: String,
    pub(super) winnowmap_preset: String,
    pub(super) winnowmap_kmer: String,
    pub(super) winnowmap_repeat_fraction: String,
    pub(super) skip_self: bool,
    pub(super) self_alignment_scope: String,
    pub(super) cross_alignment_scope: String,
    pub(super) sequence_layout: String,
    pub(super) preassigned_chr: bool,
    pub(super) contains_fasta: bool,
}

#[derive(Debug, Clone)]
pub(super) struct DerivedCtgRow {
    pub(super) derived_dataset: String,
    pub(super) ctg_name: String,
    pub(super) source: String,
    pub(super) source_fasta_name: String,
    pub(super) source_fasta_sha256: String,
    pub(super) created_at: String,
}

#[derive(Debug, Clone)]
pub(super) struct TrackMemberRow {
    pub(super) member_dataset: String,
    pub(super) member_ctg: String,
    pub(super) target_chr: String,
    pub(super) target_track: String,
    pub(super) member_role: String,
    pub(super) created_at: String,
}

#[derive(Debug, Clone)]
pub(super) struct ValidatedAddCtgPackage {
    pub(super) target_dataset_id: i64,
    pub(super) source_length: i64,
    pub(super) anchor_start: i64,
    pub(super) track_member_orders: Vec<ImportedTrackMemberOrderRow>,
}

#[derive(Debug, Clone)]
pub(super) struct AddCtgCatalogAppend {
    pub(super) dataset_id: i64,
    pub(super) source_seq_id: i64,
}

#[derive(Debug, Clone)]
pub(super) struct ImportedChrAssignmentRow {
    pub(super) dataset_name: String,
    pub(super) seq_name: String,
    pub(super) seq_length_bp: i64,
    pub(super) assigned_chr_name: String,
    pub(super) source_orientation: String,
    pub(super) orientation_source: String,
    pub(super) support_bp: i64,
    pub(super) support_percent: f64,
    pub(super) anchor_start: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct ImportedTrackMemberOrderRow {
    pub(super) target_track: String,
    pub(super) target_chr: String,
    pub(super) member_dataset: String,
    pub(super) member_ctg: String,
    pub(super) member_order: i64,
}

#[derive(Debug, Clone)]
pub(super) struct ReferenceChrLocatorRow {
    pub(super) reference_chr_name: String,
    pub(super) fasta_relpath: String,
}

#[derive(Debug, Clone)]
pub(super) struct SourceSeqLocatorRow {
    pub(super) dataset_name: String,
    pub(super) seq_name: String,
    pub(super) fasta_relpath: String,
}

#[derive(Debug, Clone)]
pub(super) struct SourceSeqNRegionRow {
    pub(super) dataset_name: String,
    pub(super) seq_name: String,
    pub(super) start_bp: i64,
    pub(super) end_bp: i64,
    pub(super) length_bp: i64,
}

#[derive(Debug, Clone)]
pub(super) struct TelomereRuleRow {
    pub(super) rule_id: String,
    pub(super) motif: String,
    pub(super) min_repeat: i64,
    pub(super) reverse_complement: bool,
}

#[derive(Debug, Clone)]
pub(super) struct TelomereMarkRow {
    pub(super) rule_id: String,
    pub(super) dataset_name: String,
    pub(super) seq_name: String,
    pub(super) assigned_chr_name: String,
    pub(super) motif: String,
    pub(super) min_repeat: i64,
    pub(super) repeat_count: i64,
    pub(super) start_bp: i64,
    pub(super) end_bp: i64,
    pub(super) strand: String,
}

#[derive(Debug, Clone)]
pub(super) struct CentromereMarkRow {
    pub(super) cen_id: String,
    pub(super) assigned_chr_name: String,
    pub(super) query_name: String,
    pub(super) dataset_name: String,
    pub(super) seq_name: String,
    pub(super) start_bp: i64,
    pub(super) end_bp: i64,
    pub(super) strand: String,
    pub(super) align_length: i64,
    pub(super) identity: f64,
    pub(super) mapq: i64,
}

#[derive(Debug, Clone)]
pub(super) struct FaiRow {
    pub(super) seq_name: String,
    pub(super) length: i64,
    pub(super) seq_order: i64,
}
