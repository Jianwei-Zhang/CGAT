use std::path::{Path, PathBuf};

use anyhow::Result;
use clap::{Parser, Subcommand};
use gpm_next_backend::auto_orientation::{AutoOrientContigsParams, auto_orient_contigs};
use gpm_next_backend::auto_placement::{AutoAssignChrParams, auto_assign_chr};
use gpm_next_backend::ctg_editor::{
    DeleteCtgParams, FlipCtgParams, FlipSeqParams, HideSeqParams, RenameCtgParams,
    RestoreDeletedCtgParams, SetEndTypeParams, ShowSeqParams, delete_ctg, flip_ctg, flip_seq,
    hide_seq, list_deleted_ctgs, rename_ctg, restore_deleted_ctg, set_end_type, show_seq,
};
use gpm_next_backend::degap_jobs::{
    ExportDegapJobsParams, export_degap_jobs, parse_degap_export_jobs, parse_degap_export_settings,
};
use gpm_next_backend::exporter::{
    ExportChrAgpParams, ExportChrFastaParams, ExportCtgAgpParams, ExportCtgFastaParams,
    ListExportRecordsParams, export_chr_agp, export_chr_fasta, export_ctg_agp, export_ctg_fasta,
    list_export_records,
};
use gpm_next_backend::grt_package::{
    initialize_grt_project_with_options, load_grt_event_trace, load_grt_evidence,
    load_grt_locked_recipe, load_grt_project_view_for_project, load_grt_source_card_trace,
};
use gpm_next_backend::importer::{
    AddDatasetImportOutcome, ImportOutcome, import_from_extracted_bundle, import_from_zip,
    import_workspace_add_dataset_package,
};
use gpm_next_backend::junction_inspection::{GetJunctionInspectionParams, get_junction_inspection};
use gpm_next_backend::main_view::{
    get_ctg_detail, list_chr_view_ctgs, list_ctg_edit_candidates, list_project_chromosomes,
    list_project_new_sequences, list_reference_track_members,
};
use gpm_next_backend::phased_assembly::{
    add_ctg_to_phased_chr_track, create_phased_chr_track, delete_phased_chr_track,
    list_phased_chr_tracks, remove_phased_chr_track_item, reorder_phased_chr_track_items,
};
use gpm_next_backend::project_initializer::{
    ProjectUpdateRequest, bootstrap_project_assembly, delete_project, list_initializer_options,
    set_project_auto_pipeline_done, update_project,
};
use gpm_next_backend::runtime_persistence::{
    AppendEditAuditLogParams, ListEditAuditLogsParams, UpdateRuntimeSettingsParams,
    append_edit_audit_log, clear_edit_audit_logs, get_runtime_settings, list_edit_audit_logs,
    update_runtime_settings,
};
use gpm_next_backend::workspace::resolve_extracted_bundle_workspace;

#[derive(Debug, Parser)]
#[command(name = "gpm_next_backend")]
#[command(about = "GPM2.0 backend bootstrap CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    InspectBundleRoot {
        path: PathBuf,
    },
    ImportExtracted {
        path: PathBuf,
    },
    ImportZip {
        zip_path: PathBuf,
        workspace_root: PathBuf,
    },
    ImportAddDatasetPackage {
        zip_path: PathBuf,
        workspace_root: PathBuf,
    },
    ListProjectInitializerOptions {
        workspace_root: PathBuf,
    },
    InitializeProject {
        workspace_root: PathBuf,
        project_name: String,
        #[arg(long)]
        phased_assembly_enabled: Option<bool>,
    },
    GetGrtProjectView {
        workspace_root: PathBuf,
        project_id: i64,
    },
    GetGrtSourceCardTrace {
        workspace_root: PathBuf,
        project_id: i64,
        source_card_key: String,
    },
    GetGrtEventTrace {
        workspace_root: PathBuf,
        project_id: i64,
        event_id: String,
    },
    GetGrtEvidence {
        workspace_root: PathBuf,
        project_id: i64,
        evidence_id: String,
    },
    DeleteProject {
        workspace_root: PathBuf,
        project_id: i64,
    },
    SetProjectAutoPipelineDone {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long, default_value_t = true)]
        done: bool,
    },
    UpdateProject {
        workspace_root: PathBuf,
        project_id: i64,
        project_name: String,
        reference_genome_id: i64,
        primary_dataset_id: i64,
        #[arg(long)]
        support_dataset_ids: Option<String>,
        #[arg(long)]
        phased_assembly_enabled: Option<bool>,
    },
    ListProjectChromosomes {
        workspace_root: PathBuf,
        project_id: i64,
    },
    ListNewSequences {
        workspace_root: PathBuf,
        project_id: i64,
    },
    ListChrViewCtgs {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
        #[arg(long)]
        dataset_id: Option<i64>,
    },
    ListReferenceTrackMembers {
        workspace_root: PathBuf,
        project_id: i64,
        chr_name: String,
    },
    ListPhasedChrTracks {
        workspace_root: PathBuf,
        project_id: i64,
        parent_chr_name: String,
    },
    CreatePhasedChrTrack {
        workspace_root: PathBuf,
        project_id: i64,
        parent_chr_name: String,
    },
    DeletePhasedChrTrack {
        workspace_root: PathBuf,
        project_id: i64,
        phased_track_id: i64,
    },
    AddCtgToPhasedChrTrack {
        workspace_root: PathBuf,
        project_id: i64,
        phased_track_id: i64,
        assembly_ctg_id: i64,
    },
    RemovePhasedChrTrackItem {
        workspace_root: PathBuf,
        project_id: i64,
        phased_track_item_id: i64,
    },
    ReorderPhasedChrTrackItems {
        workspace_root: PathBuf,
        project_id: i64,
        phased_track_id: i64,
        item_ids: String,
    },
    GetCtgDetail {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_ctg_id: i64,
    },
    ListCtgEditCandidates {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_ctg_id: i64,
    },
    BootstrapProjectAssembly {
        workspace_root: PathBuf,
        project_id: i64,
    },
    AutoAssignChr {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long, default_value_t = 1000)]
        alignment_block_size: i64,
        #[arg(long, default_value_t = 25.0)]
        alignment_coverage_percent: f64,
        #[arg(long, default_value_t = true)]
        assign_unplaced: bool,
        #[arg(long, default_value_t = false)]
        reposition_anchored: bool,
        #[arg(long, default_value_t = true)]
        skip_manual: bool,
    },
    AutoOrientContigs {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long, default_value_t = 1000)]
        alignment_block_size: i64,
        #[arg(long, default_value_t = 25.0)]
        alignment_coverage_percent: f64,
        #[arg(long, default_value_t = true)]
        skip_manual: bool,
    },
    RenameCtg {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_ctg_id: i64,
        new_name: String,
    },
    FlipCtg {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_ctg_id: i64,
    },
    FlipSeq {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_seq_id: i64,
    },
    SetEndType {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_seq_id: i64,
        left_end_type: String,
        right_end_type: String,
    },
    HideSeq {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_seq_id: i64,
    },
    ShowSeq {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_seq_id: i64,
    },
    DeleteCtg {
        workspace_root: PathBuf,
        project_id: i64,
        assembly_ctg_id: i64,
    },
    ListDeletedCtgs {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
        #[arg(long)]
        dataset_id: Option<i64>,
    },
    RestoreDeletedCtg {
        workspace_root: PathBuf,
        project_id: i64,
        deleted_ctg_record_id: i64,
    },
    ExportCtgFasta {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
        #[arg(long)]
        assembly_ctg_id: Option<i64>,
    },
    ExportChrFasta {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
    },
    ExportCtgAgp {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
        #[arg(long)]
        assembly_ctg_id: Option<i64>,
    },
    ExportChrAgp {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long)]
        chr_name: Option<String>,
        #[arg(long, default_value = "ctg")]
        element: String,
    },
    ListExportRecords {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long, default_value_t = 50)]
        limit: i64,
    },
    ExportDegapJobs {
        workspace_root: PathBuf,
        project_id: i64,
        output_dir: PathBuf,
        #[arg(long)]
        settings_json: String,
        #[arg(long)]
        jobs_json: String,
    },
    GetRuntimeSettings {
        workspace_root: PathBuf,
    },
    UpdateRuntimeSettings {
        workspace_root: PathBuf,
        #[arg(long)]
        degap_workspace_settings_json: Option<String>,
    },
    AppendEditAuditLog {
        workspace_root: PathBuf,
        project_id: i64,
        category: String,
        action: String,
        #[arg(long)]
        detail: Option<String>,
    },
    ListEditAuditLogs {
        workspace_root: PathBuf,
        project_id: i64,
        #[arg(long, default_value_t = 200)]
        limit: i64,
    },
    ClearEditAuditLogs {
        workspace_root: PathBuf,
        project_id: i64,
    },
    GetJunctionInspection {
        workspace_root: PathBuf,
        project_id: i64,
        left_assembly_ctg_id: i64,
        right_assembly_ctg_id: i64,
        #[arg(long)]
        min_align_length: Option<i64>,
        #[arg(long)]
        min_mapq: Option<i64>,
    },
}

mod assembly;
mod imports;
mod support;
mod workspace;

pub(crate) fn run() -> Result<()> {
    let command = Cli::parse().command;
    let Some(command) = imports::dispatch(command)? else {
        return Ok(());
    };
    let Some(command) = workspace::dispatch(command)? else {
        return Ok(());
    };
    let Some(command) = assembly::dispatch(command)? else {
        return Ok(());
    };
    let Some(command) = support::dispatch(command)? else {
        return Ok(());
    };
    Err(anyhow::anyhow!("unsupported command: {command:?}"))
}

fn print_progress(progress: &[gpm_next_backend::importer::ImportProgress]) {
    for event in progress {
        println!("stage={} detail={}", event.stage, event.detail);
    }
}

fn print_outcome(outcome: &ImportOutcome) {
    println!("mode={:?}", outcome.mode);
    println!("bundle_root={}", outcome.bundle_root.display());
    println!("workspace_root={}", outcome.workspace_root.display());
    println!("project_db_path={}", outcome.project_db_path.display());
}

fn print_add_dataset_outcome(outcome: &AddDatasetImportOutcome) {
    println!("bundle_root={}", outcome.bundle_root.display());
    println!("workspace_root={}", outcome.workspace_root.display());
    println!("project_db_path={}", outcome.project_db_path.display());
    println!("project_id={}", opt_i64(outcome.project_id));
    println!("dataset_id={}", outcome.dataset_id);
    println!("dataset_name={}", outcome.dataset_name);
}

fn ensure_project_exists(project_db_path: &Path, project_id: i64) -> Result<()> {
    let options = list_initializer_options(project_db_path)?;
    if options
        .existing_projects
        .iter()
        .any(|project| project.id == project_id)
    {
        return Ok(());
    }
    anyhow::bail!("project_id {project_id} does not exist")
}

fn parse_support_dataset_ids(input: Option<String>) -> Result<Vec<i64>> {
    parse_id_list(input)
}

fn parse_id_list(input: Option<String>) -> Result<Vec<i64>> {
    let Some(input) = input else {
        return Ok(Vec::new());
    };
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return Ok(Vec::new());
    }

    let mut values = Vec::new();
    for segment in trimmed.split(',') {
        let item = segment.trim();
        if item.is_empty() {
            continue;
        }
        let value: i64 = item.parse()?;
        values.push(value);
    }
    Ok(values)
}

fn print_phased_chr_tracks(result: &gpm_next_backend::phased_assembly::PhasedChrTracks) {
    println!("project_id={}", result.project_id);
    println!("parent_chr_name={}", result.parent_chr_name);
    println!("track_count={}", result.tracks.len());
    for track in &result.tracks {
        println!(
            "track id={} parent_chr_name={} haplotype_key={} label={} display_order={} item_count={}",
            track.id,
            track.parent_chr_name,
            track.haplotype_key,
            track.label,
            track.display_order,
            track.items.len()
        );
        for item in &track.items {
            println!(
                "item id={} phased_track_id={} assembly_ctg_id={} display_order={} gap_before_px={} orient={}",
                item.id,
                item.phased_track_id,
                item.assembly_ctg_id,
                item.display_order,
                item.gap_before_px,
                item.orient
            );
        }
    }
}

fn opt_i64(value: Option<i64>) -> String {
    value
        .map(|v| v.to_string())
        .unwrap_or_else(|| "NULL".to_string())
}

fn opt_f64(value: Option<f64>) -> String {
    value
        .map(|v| format!("{:.6}", v))
        .unwrap_or_else(|| "NULL".to_string())
}

fn opt_string(value: Option<&str>) -> String {
    value
        .map(ToString::to_string)
        .unwrap_or_else(|| "NULL".to_string())
}
