use super::*;

pub(super) fn dispatch(command: Commands) -> Result<Option<Commands>> {
    match command {
        Commands::ListProjectInitializerOptions { workspace_root } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let options = list_initializer_options(&project_db_path)?;
            let recipe = load_grt_locked_recipe(&project_db_path)?;
            println!("grt_recipe_json={}", serde_json::to_string(&recipe)?);
            println!(
                "package_metadata_json={}",
                serde_json::to_string(&serde_json::json!({
                    "packageMode": options.package_metadata.package_mode,
                    "sequenceLayout": options.package_metadata.sequence_layout,
                    "preassignedChr": options.package_metadata.preassigned_chr,
                    "chrAssignmentMinCoveragePercent": options
                        .package_metadata
                        .chr_assignment_min_coverage_percent,
                    "selfAlignmentScope": options.package_metadata.self_alignment_scope,
                    "crossAlignmentScope": options.package_metadata.cross_alignment_scope,
                }))?
            );
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
                    "dataset id={} name={} assembler={} assembler_version={} contig_count={} total_length_bp={} fasta_available={} self_alignment_available={}",
                    dataset.id,
                    dataset.name,
                    dataset.assembler,
                    dataset
                        .assembler_version
                        .unwrap_or_else(|| "NULL".to_string()),
                    dataset.contig_count,
                    dataset.total_length_bp,
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
                    "project id={} name={} version={} reference_id={} primary_dataset_id={} support_dataset_ids={} is_processed={} auto_pipeline_done={} auto_check_new_seq={} phased_assembly_enabled={} chr_assignment_min_coverage_percent={} description={} created_at={}",
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
                    project.chr_assignment_min_coverage_percent,
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
            phased_assembly_enabled,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            let summary = initialize_grt_project_with_options(
                &project_db_path,
                &project_name,
                phased_assembly_enabled.unwrap_or(false),
            )?;
            println!("project_id={}", summary.project_id);
            println!("project_name={}", summary.project_name);
            println!("version={}", summary.version);
            println!("reference_genome_id={}", summary.reference_genome_id);
            println!("primary_dataset_id={}", summary.primary_dataset_id);
            println!(
                "support_dataset_ids={}",
                summary
                    .support_dataset_ids
                    .iter()
                    .map(i64::to_string)
                    .collect::<Vec<_>>()
                    .join(",")
            );
            println!("project_dataset_count={}", summary.project_dataset_count);
            println!(
                "phased_assembly_enabled={}",
                summary.phased_assembly_enabled
            );
            println!(
                "chr_assignment_min_coverage_percent={}",
                summary.chr_assignment_min_coverage_percent
            );
            println!("assembly_seq_count={}", summary.assembly_seq_count);
            println!("assembly_ctg_count={}", summary.assembly_ctg_count);
            println!(
                "materialized_source_card_count={}",
                summary.materialized_source_card_count
            );
            println!(
                "grt_project_view_json={}",
                serde_json::to_string(&load_grt_project_view(&project_db_path)?)?
            );
        }
        Commands::GetGrtProjectView {
            workspace_root,
            project_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            ensure_project_exists(&project_db_path, project_id)?;
            println!(
                "json={}",
                serde_json::to_string(&load_grt_project_view(&project_db_path)?)?
            );
        }
        Commands::GetGrtSourceCardTrace {
            workspace_root,
            project_id,
            source_card_key,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            ensure_project_exists(&project_db_path, project_id)?;
            println!(
                "json={}",
                serde_json::to_string(&load_grt_source_card_trace(
                    &project_db_path,
                    &source_card_key,
                )?)?
            );
        }
        Commands::GetGrtEventTrace {
            workspace_root,
            project_id,
            event_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            ensure_project_exists(&project_db_path, project_id)?;
            println!(
                "json={}",
                serde_json::to_string(&load_grt_event_trace(&project_db_path, &event_id)?)?
            );
        }
        Commands::GetGrtEvidence {
            workspace_root,
            project_id,
            evidence_id,
        } => {
            let project_db_path = workspace_root.join("project.sqlite");
            ensure_project_exists(&project_db_path, project_id)?;
            println!(
                "json={}",
                serde_json::to_string(&load_grt_evidence(&project_db_path, &evidence_id)?)?
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
        command => return Ok(Some(command)),
    }
    Ok(None)
}
