use std::path::PathBuf;

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
    ExportDegapJobsParams, export_degap_jobs, parse_degap_export_jobs,
    parse_degap_export_settings,
};
use gpm_next_backend::exporter::{
    ExportChrAgpParams, ExportChrFastaParams, ExportCtgAgpParams, ExportCtgFastaParams,
    ListExportRecordsParams, export_chr_agp, export_chr_fasta, export_ctg_agp, export_ctg_fasta,
    list_export_records,
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
    ProjectInitializationRequest, ProjectUpdateRequest, bootstrap_project_assembly, delete_project,
    initialize_project, list_initializer_options, set_project_auto_pipeline_done, update_project,
};
use gpm_next_backend::runtime_persistence::{
    AppendEditAuditLogParams, ListEditAuditLogsParams, UpdateRuntimeSettingsParams,
    append_edit_audit_log, clear_edit_audit_logs, get_runtime_settings, list_edit_audit_logs,
    update_runtime_settings,
};
use gpm_next_backend::workspace::resolve_extracted_bundle_workspace;

#[derive(Debug, Parser)]
#[command(name = "gpm_next_backend")]
#[command(about = "GPM Next backend bootstrap CLI")]
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
        reference_genome_id: i64,
        primary_dataset_id: i64,
        #[arg(long)]
        support_dataset_ids: Option<String>,
        #[arg(long, default_value_t = false)]
        auto_check_new_seq: bool,
        #[arg(long)]
        phased_assembly_enabled: Option<bool>,
        #[arg(long)]
        description: Option<String>,
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

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::InspectBundleRoot { path } => {
            let resolved = resolve_extracted_bundle_workspace(&path)?;
            println!("bundle_root={}", resolved.bundle_root.display());
            println!("workspace_root={}", resolved.workspace_root.display());
        }
        Commands::ImportExtracted { path } => {
            let (outcome, progress) = import_from_extracted_bundle(&path)?;
            print_progress(&progress);
            print_outcome(&outcome);
        }
        Commands::ImportZip {
            zip_path,
            workspace_root,
        } => {
            let (outcome, progress) = import_from_zip(&zip_path, &workspace_root)?;
            print_progress(&progress);
            print_outcome(&outcome);
        }
        Commands::ImportAddDatasetPackage {
            zip_path,
            workspace_root,
        } => {
            let (outcome, progress) =
                import_workspace_add_dataset_package(&zip_path, &workspace_root)?;
            print_progress(&progress);
            print_add_dataset_outcome(&outcome);
        }
        Commands::ListProjectInitializerOptions { workspace_root } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let options = list_initializer_options(&project_db_path)?;
            println!("references={}", options.references.len());
            for reference in options.references {
                println!(
                    "reference id={} name={} species={} assembly={}",
                    reference.id, reference.name, reference.species_name, reference.assembly_label
                );
            }
            println!("datasets={}", options.datasets.len());
            for dataset in options.datasets {
                println!(
                    "dataset id={} name={} assembler={} assembler_version={} fasta_available={} self_alignment_available={}",
                    dataset.id,
                    dataset.name,
                    dataset.assembler,
                    dataset
                        .assembler_version
                        .unwrap_or_else(|| "NULL".to_string()),
                    dataset.fasta_available,
                    dataset.self_alignment_available
                );
            }
            println!("existing_projects={}", options.existing_projects.len());
            for project in options.existing_projects {
                let support_dataset_ids = if project.support_dataset_ids.is_empty() {
                    "NULL".to_string()
                } else {
                    project
                        .support_dataset_ids
                        .iter()
                        .map(|id| id.to_string())
                        .collect::<Vec<_>>()
                        .join(",")
                };
                println!(
                    "project id={} name={} version={} reference_id={} primary_dataset_id={} support_dataset_ids={} is_processed={} auto_pipeline_done={} auto_check_new_seq={} phased_assembly_enabled={} description={} created_at={}",
                    project.id,
                    project.name,
                    project.version,
                    project.reference_genome_id,
                    project.primary_dataset_id,
                    support_dataset_ids,
                    project.is_processed,
                    project.auto_pipeline_done,
                    project.auto_check_new_seq,
                    project.phased_assembly_enabled,
                    project.description.unwrap_or_else(|| "NULL".to_string()),
                    project.created_at
                );
            }
        }
        Commands::DeleteProject {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            delete_project(&project_db_path, project_id)?;
            println!("project_id={}", project_id);
            println!("deleted=true");
        }
        Commands::SetProjectAutoPipelineDone {
            workspace_root,
            project_id,
            done,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            set_project_auto_pipeline_done(&project_db_path, project_id, done)?;
            println!("project_id={}", project_id);
            println!("auto_pipeline_done={}", done);
        }
        Commands::InitializeProject {
            workspace_root,
            project_name,
            reference_genome_id,
            primary_dataset_id,
            support_dataset_ids,
            auto_check_new_seq,
            phased_assembly_enabled,
            description,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let support_dataset_ids = parse_support_dataset_ids(support_dataset_ids)?;
            let summary = initialize_project(
                &project_db_path,
                &ProjectInitializationRequest {
                    project_name,
                    reference_genome_id,
                    primary_dataset_id,
                    support_dataset_ids,
                    auto_check_new_seq,
                    phased_assembly_enabled,
                    chr_assignment_min_coverage_percent: None,
                    description,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("project_name={}", summary.project_name);
            println!("version={}", summary.version);
            println!("reference_genome_id={}", summary.reference_genome_id);
            println!("primary_dataset_id={}", summary.primary_dataset_id);
            println!("project_dataset_count={}", summary.project_dataset_count);
            println!(
                "phased_assembly_enabled={}",
                summary.phased_assembly_enabled
            );
        }
        Commands::UpdateProject {
            workspace_root,
            project_id,
            project_name,
            reference_genome_id,
            primary_dataset_id,
            support_dataset_ids,
            phased_assembly_enabled,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let support_dataset_ids = parse_support_dataset_ids(support_dataset_ids)?;
            let summary = update_project(
                &project_db_path,
                &ProjectUpdateRequest {
                    project_id,
                    project_name,
                    reference_genome_id,
                    primary_dataset_id,
                    support_dataset_ids,
                    phased_assembly_enabled,
                    chr_assignment_min_coverage_percent: None,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("project_name={}", summary.project_name);
            println!("reference_genome_id={}", summary.reference_genome_id);
            println!("primary_dataset_id={}", summary.primary_dataset_id);
            println!("project_dataset_count={}", summary.project_dataset_count);
            println!(
                "phased_assembly_enabled={}",
                summary.phased_assembly_enabled
            );
            println!("is_processed={}", summary.is_processed);
        }
        Commands::ListProjectChromosomes {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let chromosomes = list_project_chromosomes(&project_db_path, project_id)?;
            println!("project_id={}", chromosomes.project_id);
            println!("reference_genome_id={}", chromosomes.reference_genome_id);
            println!(
                "unplaced_ctg_count={} unplaced_bp={}",
                chromosomes.unplaced_ctg_count, chromosomes.unplaced_bp
            );
            println!("chromosome_count={}", chromosomes.items.len());
            for item in chromosomes.items {
                println!(
                    "chr name={} order={} length={} ctg_count={} placed_bp={}",
                    item.chr_name, item.chr_order, item.chr_length, item.ctg_count, item.placed_bp
                );
            }
        }
        Commands::ListNewSequences {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let items = list_project_new_sequences(&project_db_path, project_id)?;
            println!("new_sequence_count={}", items.len());
            for item in items {
                println!(
                    "sequence assembly_seq_id={} dataset={} seq={} len={} hidden={}",
                    item.assembly_seq_id,
                    item.dataset_name,
                    item.seq_name,
                    item.seq_length,
                    item.hidden
                );
            }
        }
        Commands::ListChrViewCtgs {
            workspace_root,
            project_id,
            chr_name,
            dataset_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let items = list_chr_view_ctgs(
                &project_db_path,
                project_id,
                chr_name.as_deref(),
                dataset_id,
            )?;
            println!("ctg_count={}", items.len());
            for item in items {
                println!(
                    "ctg id={} name={} chr={} chr_order={} anchor_start={} ref_orient={} mode={} members={} bp={} dataset_id={} dataset={}",
                    item.assembly_ctg_id,
                    item.name,
                    item.assigned_chr_name
                        .unwrap_or_else(|| "UNPLACED".to_string()),
                    opt_i64(item.chr_order),
                    opt_i64(item.anchor_start),
                    item.ref_orient.unwrap_or_else(|| "NULL".to_string()),
                    item.placement_mode,
                    item.member_count,
                    item.total_length,
                    opt_i64(item.dataset_id),
                    item.dataset_name.as_deref().unwrap_or("MIXED")
                );
            }
        }
        Commands::ListReferenceTrackMembers {
            workspace_root,
            project_id,
            chr_name,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let items = list_reference_track_members(&project_db_path, project_id, &chr_name)?;
            println!("member_count={}", items.len());
            for item in items {
                println!(
                    "member order={} ref_chr_id={} name={} chr={} start={} end={} anchor_start={} ref_orient={} bp={} hits={}",
                    item.segment_order,
                    item.reference_chr_id,
                    item.name,
                    item.reference_chr_name,
                    item.segment_start_bp,
                    item.segment_end_bp,
                    item.anchor_start,
                    item.ref_orient,
                    item.total_length,
                    item.hits.len()
                );
                for hit in item.hits {
                    println!(
                        "hit member_order={} hit_id={} dataset_id={} source_seq_id={} strand={} query_start={} query_end={} ref_start={} ref_end={} block_length={} mapq={} ctg_start={} ctg_end={}",
                        item.segment_order,
                        hit.hit_id,
                        hit.dataset_id,
                        hit.source_seq_id,
                        hit.strand,
                        hit.query_start,
                        hit.query_end,
                        hit.ref_start,
                        hit.ref_end,
                        hit.block_length,
                        hit.mapq,
                        hit.ctg_start,
                        hit.ctg_end
                    );
                }
            }
        }
        Commands::ListPhasedChrTracks {
            workspace_root,
            project_id,
            parent_chr_name,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let result = list_phased_chr_tracks(&project_db_path, project_id, &parent_chr_name)?;
            print_phased_chr_tracks(&result);
        }
        Commands::CreatePhasedChrTrack {
            workspace_root,
            project_id,
            parent_chr_name,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = create_phased_chr_track(&project_db_path, project_id, &parent_chr_name)?;
            println!("project_id={}", summary.track.project_id);
            println!("phased_track_id={}", summary.track.id);
            println!("parent_chr_name={}", summary.track.parent_chr_name);
            println!("haplotype_key={}", summary.track.haplotype_key);
            println!("label={}", summary.track.label);
            println!("display_order={}", summary.track.display_order);
            println!("item_count={}", summary.track.items.len());
        }
        Commands::DeletePhasedChrTrack {
            workspace_root,
            project_id,
            phased_track_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = delete_phased_chr_track(&project_db_path, project_id, phased_track_id)?;
            println!("project_id={}", summary.project_id);
            println!("phased_track_id={}", summary.phased_track_id);
            println!("parent_chr_name={}", summary.parent_chr_name);
            println!("haplotype_key={}", summary.haplotype_key);
            println!("label={}", summary.label);
            println!("deleted={}", summary.deleted);
        }
        Commands::AddCtgToPhasedChrTrack {
            workspace_root,
            project_id,
            phased_track_id,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = add_ctg_to_phased_chr_track(
                &project_db_path,
                project_id,
                phased_track_id,
                assembly_ctg_id,
            )?;
            let item = summary.item;
            println!("project_id={}", project_id);
            println!("phased_track_item_id={}", item.id);
            println!("phased_track_id={}", item.phased_track_id);
            println!("assembly_ctg_id={}", item.assembly_ctg_id);
            println!("display_order={}", item.display_order);
            println!("gap_before_px={}", item.gap_before_px);
            println!("orient={}", item.orient);
        }
        Commands::RemovePhasedChrTrackItem {
            workspace_root,
            project_id,
            phased_track_item_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary =
                remove_phased_chr_track_item(&project_db_path, project_id, phased_track_item_id)?;
            println!("project_id={}", summary.project_id);
            println!("phased_track_id={}", summary.phased_track_id);
            println!("phased_track_item_id={}", summary.phased_track_item_id);
            println!("removed={}", summary.removed);
        }
        Commands::ReorderPhasedChrTrackItems {
            workspace_root,
            project_id,
            phased_track_id,
            item_ids,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let item_ids = parse_id_list(Some(item_ids))?;
            let summary = reorder_phased_chr_track_items(
                &project_db_path,
                project_id,
                phased_track_id,
                &item_ids,
            )?;
            println!("project_id={}", summary.project_id);
            println!("phased_track_id={}", summary.phased_track_id);
            println!("item_count={}", summary.item_count);
        }
        Commands::GetCtgDetail {
            workspace_root,
            project_id,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let detail = get_ctg_detail(&project_db_path, project_id, assembly_ctg_id)?;
            println!(
                "ctg id={} name={} chr={} chr_order={} anchor_start={} ref_orient={} mode={}",
                detail.assembly_ctg_id,
                detail.name,
                detail
                    .assigned_chr_name
                    .unwrap_or_else(|| "UNPLACED".to_string()),
                opt_i64(detail.chr_order),
                opt_i64(detail.anchor_start),
                detail.ref_orient.unwrap_or_else(|| "NULL".to_string()),
                detail.placement_mode
            );
            println!("member_count={}", detail.members.len());
            for member in detail.members {
                println!(
                    "member id={} order={} assembly_seq_id={} dataset={} seq={} len={} orient={} range={}..{} left_end_type={} right_end_type={} hidden={}",
                    member.assembly_ctg_member_id,
                    member.member_order,
                    member.assembly_seq_id,
                    member.dataset_name,
                    member.seq_name,
                    member.seq_length,
                    member.orient,
                    member.source_start,
                    member.source_end,
                    member.left_end_type,
                    member.right_end_type,
                    member.hidden
                );
            }
        }
        Commands::ListCtgEditCandidates {
            workspace_root,
            project_id,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let candidates =
                list_ctg_edit_candidates(&project_db_path, project_id, assembly_ctg_id)?;
            println!(
                "move_target_count={} add_seq_count={}",
                candidates.move_target_ctgs.len(),
                candidates.add_seq_candidates.len()
            );
            for ctg in candidates.move_target_ctgs {
                println!(
                    "move_target id={} name={} chr={} chr_order={}",
                    ctg.assembly_ctg_id,
                    ctg.name,
                    ctg.assigned_chr_name
                        .unwrap_or_else(|| "UNPLACED".to_string()),
                    opt_i64(ctg.chr_order)
                );
            }
            for seq in candidates.add_seq_candidates {
                println!(
                    "add_seq assembly_seq_id={} dataset={} seq={} len={} hidden={}",
                    seq.assembly_seq_id, seq.dataset_name, seq.seq_name, seq.seq_length, seq.hidden
                );
            }
        }
        Commands::BootstrapProjectAssembly {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = bootstrap_project_assembly(&project_db_path, project_id)?;
            println!("project_id={}", summary.project_id);
            println!("assembly_seq_count={}", summary.assembly_seq_count);
            println!("assembly_ctg_count={}", summary.assembly_ctg_count);
            println!("assembly_member_count={}", summary.assembly_member_count);
        }
        Commands::AutoAssignChr {
            workspace_root,
            project_id,
            alignment_block_size,
            alignment_coverage_percent,
            assign_unplaced,
            reposition_anchored,
            skip_manual,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = auto_assign_chr(
                &project_db_path,
                project_id,
                &AutoAssignChrParams {
                    alignment_block_size,
                    alignment_coverage_percent,
                    assign_unplaced,
                    reposition_anchored,
                    skip_manual,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("processed_ctg_count={}", summary.processed_ctg_count);
            println!("assigned_count={}", summary.assigned_count);
            println!("repositioned_count={}", summary.repositioned_count);
            println!("cleared_count={}", summary.cleared_count);
            println!("skipped_manual_count={}", summary.skipped_manual_count);
            println!("no_evidence_count={}", summary.no_evidence_count);
            println!("refreshed_chr_count={}", summary.refreshed_chr_count);
            println!(
                "loaded_alignment_dataset_count={}",
                summary.loaded_alignment_dataset_count
            );
            println!(
                "loaded_alignment_hit_count={}",
                summary.loaded_alignment_hit_count
            );
        }
        Commands::AutoOrientContigs {
            workspace_root,
            project_id,
            alignment_block_size,
            alignment_coverage_percent,
            skip_manual,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = auto_orient_contigs(
                &project_db_path,
                project_id,
                &AutoOrientContigsParams {
                    alignment_block_size,
                    alignment_coverage_percent,
                    skip_manual,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("processed_ctg_count={}", summary.processed_ctg_count);
            println!("oriented_ctg_count={}", summary.oriented_ctg_count);
            println!("flipped_ctg_count={}", summary.flipped_ctg_count);
            println!("no_evidence_count={}", summary.no_evidence_count);
            println!("skipped_manual_count={}", summary.skipped_manual_count);
            println!(
                "loaded_alignment_dataset_count={}",
                summary.loaded_alignment_dataset_count
            );
            println!(
                "loaded_alignment_hit_count={}",
                summary.loaded_alignment_hit_count
            );
        }
        Commands::RenameCtg {
            workspace_root,
            project_id,
            assembly_ctg_id,
            new_name,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = rename_ctg(
                &project_db_path,
                project_id,
                &RenameCtgParams {
                    assembly_ctg_id,
                    new_name,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("old_name={}", summary.old_name);
            println!("new_name={}", summary.new_name);
            println!("changed={}", summary.changed);
        }
        Commands::FlipCtg {
            workspace_root,
            project_id,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = flip_ctg(
                &project_db_path,
                project_id,
                &FlipCtgParams { assembly_ctg_id },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("member_count={}", summary.member_count);
            println!(
                "ref_orient={}",
                summary.ref_orient.unwrap_or_else(|| "NULL".to_string())
            );
        }
        Commands::FlipSeq {
            workspace_root,
            project_id,
            assembly_seq_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = flip_seq(
                &project_db_path,
                project_id,
                &FlipSeqParams { assembly_seq_id },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_seq_id={}", summary.assembly_seq_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("orient={}", summary.orient);
            println!("left_end_type={}", summary.left_end_type);
            println!("right_end_type={}", summary.right_end_type);
            println!(
                "ref_orient={}",
                summary.ref_orient.unwrap_or_else(|| "NULL".to_string())
            );
        }
        Commands::SetEndType {
            workspace_root,
            project_id,
            assembly_seq_id,
            left_end_type,
            right_end_type,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = set_end_type(
                &project_db_path,
                project_id,
                &SetEndTypeParams {
                    assembly_seq_id,
                    left_end_type,
                    right_end_type,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_seq_id={}", summary.assembly_seq_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("left_end_type={}", summary.left_end_type);
            println!("right_end_type={}", summary.right_end_type);
            println!(
                "ref_orient={}",
                summary.ref_orient.unwrap_or_else(|| "NULL".to_string())
            );
            println!("changed={}", summary.changed);
        }
        Commands::HideSeq {
            workspace_root,
            project_id,
            assembly_seq_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = hide_seq(
                &project_db_path,
                project_id,
                &HideSeqParams { assembly_seq_id },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_seq_id={}", summary.assembly_seq_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("hidden={}", summary.hidden);
            println!(
                "ref_orient={}",
                summary.ref_orient.unwrap_or_else(|| "NULL".to_string())
            );
            println!("changed={}", summary.changed);
        }
        Commands::ShowSeq {
            workspace_root,
            project_id,
            assembly_seq_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = show_seq(
                &project_db_path,
                project_id,
                &ShowSeqParams { assembly_seq_id },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_seq_id={}", summary.assembly_seq_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("hidden={}", summary.hidden);
            println!(
                "ref_orient={}",
                summary.ref_orient.unwrap_or_else(|| "NULL".to_string())
            );
            println!("changed={}", summary.changed);
        }
        Commands::DeleteCtg {
            workspace_root,
            project_id,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = delete_ctg(
                &project_db_path,
                project_id,
                &DeleteCtgParams { assembly_ctg_id },
            )?;
            println!("project_id={}", summary.project_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!(
                "released_assembly_seq_ids={}",
                summary
                    .released_assembly_seq_ids
                    .iter()
                    .map(|value| value.to_string())
                    .collect::<Vec<_>>()
                    .join(",")
            );
            println!(
                "released_assembly_seq_count={}",
                summary.released_assembly_seq_count
            );
            println!("refreshed_chr_count={}", summary.refreshed_chr_count);
        }
        Commands::ListDeletedCtgs {
            workspace_root,
            project_id,
            chr_name,
            dataset_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let items = list_deleted_ctgs(
                &project_db_path,
                project_id,
                chr_name.as_deref(),
                dataset_id,
            )?;
            println!("project_id={}", project_id);
            println!("deleted_ctg_count={}", items.len());
            for item in items {
                println!(
                    "deleted_ctg record_id={} ctg_id={} name={} chr={} chr_order={} anchor_start={} ref_orient={} mode={} members={} bp={} deleted_at={}",
                    item.deleted_ctg_record_id,
                    item.assembly_ctg_id,
                    item.name,
                    item.assigned_chr_name.unwrap_or_else(|| "NULL".to_string()),
                    opt_i64(item.chr_order),
                    opt_i64(item.anchor_start),
                    item.ref_orient.unwrap_or_else(|| "NULL".to_string()),
                    item.placement_mode,
                    item.member_count,
                    item.total_length,
                    item.deleted_at
                );
            }
        }
        Commands::RestoreDeletedCtg {
            workspace_root,
            project_id,
            deleted_ctg_record_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = restore_deleted_ctg(
                &project_db_path,
                project_id,
                &RestoreDeletedCtgParams {
                    deleted_ctg_record_id,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("deleted_ctg_record_id={}", summary.deleted_ctg_record_id);
            println!("assembly_ctg_id={}", summary.assembly_ctg_id);
            println!("restored_member_count={}", summary.restored_member_count);
            println!("refreshed_chr_count={}", summary.refreshed_chr_count);
        }
        Commands::ExportCtgFasta {
            workspace_root,
            project_id,
            chr_name,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = export_ctg_fasta(
                &project_db_path,
                project_id,
                &ExportCtgFastaParams {
                    chr_name,
                    assembly_ctg_id,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("export_type={}", summary.export_type);
            println!("record_id={}", summary.record_id);
            println!("record_count={}", summary.record_count);
            println!("output_path={}", summary.output_path.display());
        }
        Commands::ExportChrFasta {
            workspace_root,
            project_id,
            chr_name,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = export_chr_fasta(
                &project_db_path,
                project_id,
                &ExportChrFastaParams { chr_name },
            )?;
            println!("project_id={}", summary.project_id);
            println!("export_type={}", summary.export_type);
            println!("record_id={}", summary.record_id);
            println!("record_count={}", summary.record_count);
            println!("output_path={}", summary.output_path.display());
        }
        Commands::ExportCtgAgp {
            workspace_root,
            project_id,
            chr_name,
            assembly_ctg_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = export_ctg_agp(
                &project_db_path,
                project_id,
                &ExportCtgAgpParams {
                    chr_name,
                    assembly_ctg_id,
                },
            )?;
            println!("project_id={}", summary.project_id);
            println!("export_type={}", summary.export_type);
            println!("record_id={}", summary.record_id);
            println!("record_count={}", summary.record_count);
            println!("output_path={}", summary.output_path.display());
        }
        Commands::ExportChrAgp {
            workspace_root,
            project_id,
            chr_name,
            element,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = export_chr_agp(
                &project_db_path,
                project_id,
                &ExportChrAgpParams { chr_name, element },
            )?;
            println!("project_id={}", summary.project_id);
            println!("export_type={}", summary.export_type);
            println!("record_id={}", summary.record_id);
            println!("record_count={}", summary.record_count);
            println!("output_path={}", summary.output_path.display());
        }
        Commands::ListExportRecords {
            workspace_root,
            project_id,
            limit,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let rows = list_export_records(
                &project_db_path,
                project_id,
                &ListExportRecordsParams { limit },
            )?;
            println!("record_count={}", rows.len());
            for row in rows {
                println!(
                    "record id={} project_id={} export_type={} reference_chr_id={} assembly_ctg_id={} output_path={} created_at={} note={}",
                    row.id,
                    row.project_id,
                    row.export_type,
                    opt_i64(row.reference_chr_id),
                    opt_i64(row.assembly_ctg_id),
                    row.output_path,
                    row.created_at,
                    row.note.unwrap_or_else(|| "NULL".to_string())
                );
            }
        }
        Commands::ExportDegapJobs {
            workspace_root,
            project_id,
            output_dir,
            settings_json,
            jobs_json,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let settings_value: serde_json::Value = serde_json::from_str(&settings_json)?;
            let jobs_value: serde_json::Value = serde_json::from_str(&jobs_json)?;
            let summary = export_degap_jobs(
                &project_db_path,
                &workspace_root,
                project_id,
                &ExportDegapJobsParams {
                    output_dir,
                    settings: parse_degap_export_settings(&settings_value)?,
                    jobs: parse_degap_export_jobs(&jobs_value)?,
                },
            )?;
            println!("output_dir={}", summary.output_dir.display());
            println!("manifest_path={}", summary.manifest_path.display());
            println!("prepare_script_path={}", summary.prepare_script_path.display());
            for script in summary.scripts {
                println!(
                    "script job_id={} script_path={} out_path={} seqleft_path={} seqright_path={} ctg_path={}",
                    script.job_id,
                    script.script_path.display(),
                    script.out_path,
                    script.seqleft_path,
                    script.seqright_path,
                    script.ctg_path
                );
            }
        }
        Commands::GetRuntimeSettings { workspace_root } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let settings = get_runtime_settings(&project_db_path)?;
            println!("updated_at={}", settings.updated_at);
            println!(
                "degap_workspace_settings_json={}",
                settings.degap_workspace_settings_json
            );
        }
        Commands::UpdateRuntimeSettings {
            workspace_root,
            degap_workspace_settings_json,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let settings = update_runtime_settings(
                &project_db_path,
                &UpdateRuntimeSettingsParams {
                    degap_workspace_settings_json: degap_workspace_settings_json
                        .unwrap_or_else(|| "{}".to_string()),
                },
            )?;
            println!("updated_at={}", settings.updated_at);
            println!(
                "degap_workspace_settings_json={}",
                settings.degap_workspace_settings_json
            );
        }
        Commands::AppendEditAuditLog {
            workspace_root,
            project_id,
            category,
            action,
            detail,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let row = append_edit_audit_log(
                &project_db_path,
                &AppendEditAuditLogParams {
                    project_id,
                    category,
                    action,
                    detail,
                },
            )?;
            println!("id={}", row.id);
            println!("project_id={}", row.project_id);
            println!("category={}", row.category);
            println!("action={}", row.action);
            println!("detail={}", opt_string(row.detail.as_deref()));
            println!("created_at={}", row.created_at);
        }
        Commands::ListEditAuditLogs {
            workspace_root,
            project_id,
            limit,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let rows = list_edit_audit_logs(
                &project_db_path,
                &ListEditAuditLogsParams { project_id, limit },
            )?;
            println!("record_count={}", rows.len());
            for row in rows {
                println!(
                    "log id={} project_id={} category={} action={} detail={} created_at={}",
                    row.id,
                    row.project_id,
                    row.category,
                    row.action,
                    opt_string(row.detail.as_deref()),
                    row.created_at
                );
            }
        }
        Commands::ClearEditAuditLogs {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let deleted_count = clear_edit_audit_logs(&project_db_path, project_id)?;
            println!("project_id={}", project_id);
            println!("deleted_count={}", deleted_count);
        }
        Commands::GetJunctionInspection {
            workspace_root,
            project_id,
            left_assembly_ctg_id,
            right_assembly_ctg_id,
            min_align_length,
            min_mapq,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let report = get_junction_inspection(
                &project_db_path,
                &GetJunctionInspectionParams {
                    project_id,
                    left_assembly_ctg_id,
                    right_assembly_ctg_id,
                    min_align_length,
                    min_mapq,
                },
            )?;
            println!("project_id={}", report.project_id);
            println!("assigned_chr_name={}", report.assigned_chr_name);
            println!(
                "left_ctg_id={} left_name={} left_anchor={} left_end={} left_span={}",
                report.left.assembly_ctg_id,
                report.left.name,
                opt_i64(report.left.anchor_start),
                opt_i64(report.left.anchor_end),
                report.left.span_length
            );
            println!(
                "right_ctg_id={} right_name={} right_anchor={} right_end={} right_span={}",
                report.right.assembly_ctg_id,
                report.right.name,
                opt_i64(report.right.anchor_start),
                opt_i64(report.right.anchor_end),
                report.right.span_length
            );
            println!("placement_relation={}", report.placement_relation);
            println!("overlap_bp={}", opt_i64(report.overlap_bp));
            println!("gap_bp={}", opt_i64(report.gap_bp));
            println!("same_dataset={}", report.same_dataset);
            println!("evidence_source={}", report.evidence_source);
            println!("evidence_hit_count={}", report.evidence_hit_count);
            for hit in report.hits {
                println!(
                    "hit query_ctg_id={} query_id={} query_name={} subject_ctg_id={} subject_id={} subject_name={} strand={} q={}..{} s={}..{} mapq={} identity_pct={:.4} align_length={} mismatch_count={} gap_open_count={} evalue={} bit_score={} origin={}",
                    hit.query_assembly_ctg_id,
                    hit.query_source_seq_id,
                    hit.query_source_seq_name,
                    hit.subject_assembly_ctg_id,
                    hit.subject_source_seq_id,
                    hit.subject_source_seq_name,
                    hit.strand,
                    hit.query_start,
                    hit.query_end,
                    hit.subject_start,
                    hit.subject_end,
                    hit.mapq,
                    hit.identity_pct,
                    hit.align_length,
                    opt_i64(hit.mismatch_count),
                    opt_i64(hit.gap_open_count),
                    opt_f64(hit.evalue),
                    opt_f64(hit.bit_score),
                    hit.evidence_origin
                );
            }
        }
    }

    Ok(())
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
