use super::*;

pub(super) fn dispatch(command: Commands) -> Result<Option<Commands>> {
    match command {
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
        command => return Ok(Some(command)),
    }
    Ok(None)
}
