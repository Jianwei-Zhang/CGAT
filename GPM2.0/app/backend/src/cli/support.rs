use super::*;

pub(super) fn dispatch(command: Commands) -> Result<Option<Commands>> {
    match command {
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
            println!(
                "prepare_script_path={}",
                summary.prepare_script_path.display()
            );
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
        command => return Ok(Some(command)),
    }
    Ok(None)
}
