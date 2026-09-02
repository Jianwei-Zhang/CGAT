use serde::{Deserialize, Serialize};
use serde_json::Value;

pub(super) const HISTORY_SCHEMA_VERSION: u32 = 1;
pub(super) const HISTORY_CAPACITY: usize = 50;

#[derive(Debug, Clone, PartialEq)]
pub struct RunMainViewEditorActionParams {
    pub project_id: i64,
    pub chr_name: String,
    pub action: String,
    pub args: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RunMainViewLayoutActionParams {
    pub project_id: i64,
    pub chr_name: String,
    pub action: String,
    pub args: Value,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunMainViewBatchDeleteParams {
    pub project_id: i64,
    pub chr_name: String,
    pub assembly_ctg_ids: Vec<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MainViewHistoryTargetParams {
    pub project_id: i64,
    pub chr_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MainViewHistoryOperationDescriptor {
    pub kind: String,
    pub target_count: i64,
    pub target_name: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MainViewHistoryStatus {
    pub project_id: i64,
    pub reference_chr_id: i64,
    pub chr_name: String,
    pub can_undo: bool,
    pub can_redo: bool,
    pub can_reset: bool,
    pub undo_operation: Option<MainViewHistoryOperationDescriptor>,
    pub redo_operation: Option<MainViewHistoryOperationDescriptor>,
    pub applied_operation_count: i64,
    pub retained_operation_count: i64,
    pub invalidated: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MainViewHistoryMutationSummary {
    pub changed: bool,
    pub invalidated: bool,
    pub affected_ctg_ids: Vec<i64>,
    pub affected_seq_ids: Vec<i64>,
    pub descriptor: Option<MainViewHistoryOperationDescriptor>,
    pub status: MainViewHistoryStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct MainViewDeleteImpact {
    pub ctg_count: i64,
    pub phased_item_count: i64,
    pub export_record_count: i64,
    pub final_path_reference_count: i64,
    pub degap_reference_count: i64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct AssemblyCtgRow {
    pub id: i64,
    pub project_id: i64,
    pub assembly_seq_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
    pub anchor_start: Option<i64>,
    pub ref_orient: Option<String>,
    pub placement_mode: String,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct AssemblySeqRow {
    pub id: i64,
    pub project_id: i64,
    pub source_seq_id: i64,
    pub instance_key: String,
    pub orient: String,
    pub source_start: i64,
    pub source_end: i64,
    pub left_end_type: String,
    pub right_end_type: String,
    pub hidden: i64,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct DeletedAssemblyCtgRow {
    pub id: i64,
    pub project_id: i64,
    pub assembly_ctg_id: i64,
    pub assembly_seq_id: i64,
    pub name: String,
    pub assigned_chr_name: Option<String>,
    pub chr_order: Option<i64>,
    pub anchor_start: Option<i64>,
    pub ref_orient: Option<String>,
    pub placement_mode: String,
    pub created_at: String,
    pub note: Option<String>,
    pub deleted_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct PhasedTrackRow {
    pub id: i64,
    pub project_id: i64,
    pub parent_chr_name: String,
    pub haplotype_key: String,
    pub label: String,
    pub display_order: i64,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct PhasedTrackItemRow {
    pub id: i64,
    pub phased_track_id: i64,
    pub assembly_ctg_id: i64,
    pub display_order: i64,
    pub gap_before_px: i64,
    pub orient: String,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct ExportRecordRow {
    pub id: i64,
    pub project_id: i64,
    pub export_type: String,
    pub reference_chr_id: Option<i64>,
    pub assembly_ctg_id: Option<i64>,
    pub output_path: String,
    pub created_at: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct ProjectViewDependencyRow {
    pub project_id: i64,
    pub final_path_by_chr_json: String,
    pub degap_project_state_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct ProjectViewTrackOffsetKey {
    pub track_role: String,
    pub assembly_ctg_id: i64,
    pub dataset_id: Option<i64>,
    pub phased_track_id: Option<i64>,
    pub phased_track_item_id: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct ProjectViewMirrorKey {
    pub dataset_id: i64,
    pub assembly_ctg_id: i64,
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct ProjectViewLayoutScope {
    pub track_offset_keys: Vec<ProjectViewTrackOffsetKey>,
    pub mirror_keys: Vec<ProjectViewMirrorKey>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct ProjectViewLayoutSnapshot {
    pub scoped_track_drag_offsets: Vec<Value>,
    pub scoped_support_mirrors: Vec<Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub(super) struct DatabaseSnapshot {
    pub ctg_ids: Vec<i64>,
    pub ctgs: Vec<AssemblyCtgRow>,
    pub seq_ids: Vec<i64>,
    pub seqs: Vec<AssemblySeqRow>,
    pub deleted_record_ids: Vec<i64>,
    pub deleted_ctgs: Vec<DeletedAssemblyCtgRow>,
    pub dependency_ctg_ids: Vec<i64>,
    pub phased_track_ids: Vec<i64>,
    pub phased_tracks: Vec<PhasedTrackRow>,
    pub phased_items: Vec<PhasedTrackItemRow>,
    pub export_record_ids: Vec<i64>,
    pub export_records: Vec<ExportRecordRow>,
    pub include_view_state: bool,
    pub view_state: Option<ProjectViewDependencyRow>,
    #[serde(default)]
    pub layout_scope: ProjectViewLayoutScope,
    #[serde(default)]
    pub layout_state: ProjectViewLayoutSnapshot,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(super) struct SnapshotScope {
    pub ctg_ids: Vec<i64>,
    pub seq_ids: Vec<i64>,
    pub deleted_record_ids: Vec<i64>,
    pub dependency_ctg_ids: Vec<i64>,
    pub phased_track_ids: Vec<i64>,
    pub export_record_ids: Vec<i64>,
    pub include_view_state: bool,
    pub layout_scope: ProjectViewLayoutScope,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct HistoryOperation {
    pub logical_id: u64,
    pub descriptor: MainViewHistoryOperationDescriptor,
    pub before: DatabaseSnapshot,
    pub after: DatabaseSnapshot,
    pub before_active_ids: Vec<u64>,
    pub after_active_ids: Vec<u64>,
    pub affected_ctg_ids: Vec<i64>,
    pub affected_seq_ids: Vec<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct HistoryState {
    pub version: u32,
    pub next_logical_id: u64,
    pub past: Vec<HistoryOperation>,
    pub future: Vec<HistoryOperation>,
    pub active_operation_ids: Vec<u64>,
}

impl Default for HistoryState {
    fn default() -> Self {
        Self {
            version: HISTORY_SCHEMA_VERSION,
            next_logical_id: 1,
            past: Vec::new(),
            future: Vec::new(),
            active_operation_ids: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct PreparedMutation {
    pub descriptor: MainViewHistoryOperationDescriptor,
    pub before: DatabaseSnapshot,
    pub after: DatabaseSnapshot,
    pub affected_ctg_ids: Vec<i64>,
    pub affected_seq_ids: Vec<i64>,
    pub changed: bool,
}
