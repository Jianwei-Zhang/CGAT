use super::*;

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_chr_view_ctgs(
    workspaceRoot: String,
    projectId: i64,
    chrName: Option<String>,
    datasetId: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_chr_view_ctgs(
            &project_db_path(&workspaceRoot),
            projectId,
            chrName.as_deref(),
            datasetId,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                let hits = item
                    .hits
                    .into_iter()
                    .map(|hit| {
                        json!({
                            "hitId": hit.hit_id,
                            "assemblyCtgMemberId": hit.assembly_ctg_member_id,
                            "assemblySeqId": hit.assembly_seq_id,
                            "sourceSeqId": hit.source_seq_id,
                            "strand": hit.strand,
                            "queryStart": hit.query_start,
                            "queryEnd": hit.query_end,
                            "refStart": hit.ref_start,
                            "refEnd": hit.ref_end,
                            "matchLength": hit.match_length,
                            "blockLength": hit.block_length,
                            "mapq": hit.mapq,
                            "ctgStart": hit.ctg_start,
                            "ctgEnd": hit.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let n_regions = item
                    .n_regions
                    .into_iter()
                    .map(|region| {
                        json!({
                            "startBp": region.start_bp,
                            "endBp": region.end_bp,
                            "lengthBp": region.length_bp,
                            "ctgStart": region.ctg_start,
                            "ctgEnd": region.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let telomere_marks = item
                    .telomere_marks
                    .into_iter()
                    .map(|mark| {
                        json!({
                            "ruleId": mark.rule_id,
                            "motif": mark.motif,
                            "minRepeat": mark.min_repeat,
                            "repeatCount": mark.repeat_count,
                            "startBp": mark.start_bp,
                            "endBp": mark.end_bp,
                            "strand": mark.strand,
                            "ctgStart": mark.ctg_start,
                            "ctgEnd": mark.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                let centromere_marks = item
                    .centromere_marks
                    .into_iter()
                    .map(|mark| {
                        json!({
                            "cenId": mark.cen_id,
                            "queryName": mark.query_name,
                            "startBp": mark.start_bp,
                            "endBp": mark.end_bp,
                            "strand": mark.strand,
                            "alignLength": mark.align_length,
                            "identity": mark.identity,
                            "mapq": mark.mapq,
                            "ctgStart": mark.ctg_start,
                            "ctgEnd": mark.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                json!({
                    "assemblyCtgId": item.assembly_ctg_id,
                    "name": item.name,
                    "originId": item.origin_id,
                    "coAssignedChrNames": item.co_assigned_chr_names,
                    "assignedChrName": item.assigned_chr_name,
                    "chrOrder": item.chr_order,
                    "anchorStart": item.anchor_start,
                    "refOrient": item.ref_orient,
                    "orient": item.orient,
                    "placementMode": item.placement_mode,
                    "memberCount": item.member_count,
                    "totalLength": item.total_length,
                    "datasetId": item.dataset_id,
                    "datasetName": item.dataset_name,
                    "derivedSource": item.derived_source,
                    "derivedTargetDatasetId": item.derived_target_dataset_id,
                    "derivedTargetDatasetName": item.derived_target_dataset_name,
                    "hits": hits,
                    "nRegions": n_regions,
                    "telomereMarks": telomere_marks,
                    "centromereMarks": centromere_marks
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_deleted_ctgs(
    workspaceRoot: String,
    projectId: i64,
    chrName: Option<String>,
    datasetId: Option<i64>,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_deleted_ctgs(
            &project_db_path(&workspaceRoot),
            projectId,
            chrName.as_deref(),
            datasetId,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                json!({
                    "deletedCtgRecordId": item.deleted_ctg_record_id,
                    "projectId": item.project_id,
                    "assemblyCtgId": item.assembly_ctg_id,
                    "name": item.name,
                    "assignedChrName": item.assigned_chr_name,
                    "chrOrder": item.chr_order,
                    "anchorStart": item.anchor_start,
                    "refOrient": item.ref_orient,
                    "placementMode": item.placement_mode,
                    "memberCount": item.member_count,
                    "totalLength": item.total_length,
                    "deletedAt": item.deleted_at
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_reference_track_members(
    workspaceRoot: String,
    projectId: i64,
    chrName: String,
) -> Result<Value, String> {
    (|| {
        let items = backend_list_reference_track_members(
            &project_db_path(&workspaceRoot),
            projectId,
            &chrName,
        )?;
        let mapped = items
            .into_iter()
            .map(|item| {
                let hits = item
                    .hits
                    .into_iter()
                    .map(|hit| {
                        json!({
                            "hitId": hit.hit_id,
                            "datasetId": hit.dataset_id,
                            "sourceSeqId": hit.source_seq_id,
                            "strand": hit.strand,
                            "queryStart": hit.query_start,
                            "queryEnd": hit.query_end,
                            "refStart": hit.ref_start,
                            "refEnd": hit.ref_end,
                            "matchLength": hit.match_length,
                            "blockLength": hit.block_length,
                            "mapq": hit.mapq,
                            "ctgStart": hit.ctg_start,
                            "ctgEnd": hit.ctg_end
                        })
                    })
                    .collect::<Vec<_>>();
                json!({
                    "sourceKind": item.source_kind,
                    "referenceChrId": item.reference_chr_id,
                    "referenceChrName": item.reference_chr_name,
                    "segmentOrder": item.segment_order,
                    "segmentStartBp": item.segment_start_bp,
                    "segmentEndBp": item.segment_end_bp,
                    "name": item.name,
                    "anchorStart": item.anchor_start,
                    "totalLength": item.total_length,
                    "refOrient": item.ref_orient,
                    "hits": hits
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({ "items": mapped }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_phased_chr_tracks(
    workspaceRoot: String,
    projectId: i64,
    parentChrName: String,
) -> Result<Value, String> {
    (|| {
        let result = backend_list_phased_chr_tracks(
            &project_db_path(&workspaceRoot),
            projectId,
            &parentChrName,
        )?;
        let tracks = result
            .tracks
            .into_iter()
            .map(map_phased_track)
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": result.project_id,
            "parentChrName": result.parent_chr_name,
            "tracks": tracks
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn create_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    parentChrName: String,
) -> Result<Value, String> {
    (|| {
        let summary = backend_create_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            &parentChrName,
        )?;
        Ok(json!({ "track": map_phased_track(summary.track) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn delete_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_delete_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "parentChrName": summary.parent_chr_name,
            "haplotypeKey": summary.haplotype_key,
            "label": summary.label,
            "deleted": summary.deleted
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn add_ctg_to_phased_chr_track(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_add_ctg_to_phased_chr_track(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
            assemblyCtgId,
        )?;
        Ok(json!({ "item": map_phased_track_item(summary.item) }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn remove_phased_chr_track_item(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackItemId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_remove_phased_chr_track_item(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackItemId,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "phasedTrackItemId": summary.phased_track_item_id,
            "removed": summary.removed
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn reorder_phased_chr_track_items(
    workspaceRoot: String,
    projectId: i64,
    phasedTrackId: i64,
    itemIds: Vec<i64>,
) -> Result<Value, String> {
    (|| {
        let summary = backend_reorder_phased_chr_track_items(
            &project_db_path(&workspaceRoot),
            projectId,
            phasedTrackId,
            &itemIds,
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "phasedTrackId": summary.phased_track_id,
            "itemCount": summary.item_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn get_ctg_detail(
    workspaceRoot: String,
    projectId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let detail =
            backend_get_ctg_detail(&project_db_path(&workspaceRoot), projectId, assemblyCtgId)?;
        let members = detail
            .members
            .into_iter()
            .map(|member| {
                json!({
                    "assemblyCtgMemberId": member.assembly_ctg_member_id,
                    "memberOrder": member.member_order,
                    "assemblySeqId": member.assembly_seq_id,
                    "datasetName": member.dataset_name,
                    "seqName": member.seq_name,
                    "seqLength": member.seq_length,
                    "orient": member.orient,
                    "sourceStart": member.source_start,
                    "sourceEnd": member.source_end,
                    "leftEndType": member.left_end_type,
                    "rightEndType": member.right_end_type,
                    "hidden": member.hidden
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "assemblyCtgId": detail.assembly_ctg_id,
            "projectId": detail.project_id,
            "name": detail.name,
            "assignedChrName": detail.assigned_chr_name,
            "chrOrder": detail.chr_order,
            "anchorStart": detail.anchor_start,
            "refOrient": detail.ref_orient,
            "placementMode": detail.placement_mode,
            "members": members
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn list_ctg_edit_candidates(
    workspaceRoot: String,
    projectId: i64,
    assemblyCtgId: i64,
) -> Result<Value, String> {
    (|| {
        let candidates = backend_list_ctg_edit_candidates(
            &project_db_path(&workspaceRoot),
            projectId,
            assemblyCtgId,
        )?;
        let move_targets = candidates
            .move_target_ctgs
            .into_iter()
            .map(|ctg| {
                json!({
                    "assemblyCtgId": ctg.assembly_ctg_id,
                    "name": ctg.name,
                    "assignedChrName": ctg.assigned_chr_name,
                    "chrOrder": ctg.chr_order
                })
            })
            .collect::<Vec<_>>();
        let add_seq_candidates = candidates
            .add_seq_candidates
            .into_iter()
            .map(|seq| {
                json!({
                    "assemblySeqId": seq.assembly_seq_id,
                    "datasetName": seq.dataset_name,
                    "seqName": seq.seq_name,
                    "seqLength": seq.seq_length,
                    "hidden": seq.hidden
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": candidates.project_id,
            "assemblyCtgId": candidates.assembly_ctg_id,
            "moveTargetCtgs": move_targets,
            "addSeqCandidates": add_seq_candidates
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn restore_deleted_ctg(
    workspaceRoot: String,
    projectId: i64,
    deletedCtgRecordId: i64,
) -> Result<Value, String> {
    (|| {
        let summary = backend_restore_deleted_ctg(
            &project_db_path(&workspaceRoot),
            projectId,
            &RestoreDeletedCtgParams {
                deleted_ctg_record_id: deletedCtgRecordId,
            },
        )?;
        Ok(json!({
            "projectId": summary.project_id,
            "deletedCtgRecordId": summary.deleted_ctg_record_id,
            "assemblyCtgId": summary.assembly_ctg_id,
            "restoredMemberCount": summary.restored_member_count,
            "refreshedChrCount": summary.refreshed_chr_count
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub fn run_ctg_editor_action(
    workspaceRoot: String,
    projectId: i64,
    action: String,
    args: Value,
) -> Result<Value, String> {
    (|| {
        let project_db = project_db_path(&workspaceRoot);
        let normalized = action.trim().to_ascii_lowercase();
        let changed = match normalized.as_str() {
            "rename-ctg" => {
                rename_ctg(
                    &project_db,
                    projectId,
                    &RenameCtgParams {
                        assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                        new_name: get_required_string(&args, "newName")?,
                    },
                )?
                .changed
            }
            "flip-ctg" => {
                let phased_track_item_id = match args.get("phasedTrackItemId") {
                    Some(value) if !value.is_null() => {
                        let parsed = value_to_i64(value, "phasedTrackItemId")?;
                        (parsed > 0).then_some(parsed)
                    }
                    _ => None,
                };
                if let Some(phased_track_item_id) = phased_track_item_id {
                    backend_flip_phased_chr_track_item(
                        &project_db,
                        projectId,
                        phased_track_item_id,
                    )?;
                } else {
                    flip_ctg(
                        &project_db,
                        projectId,
                        &FlipCtgParams {
                            assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                        },
                    )?;
                }
                true
            }
            "delete-ctg" => {
                delete_ctg(
                    &project_db,
                    projectId,
                    &DeleteCtgParams {
                        assembly_ctg_id: get_required_i64(&args, "assemblyCtgId")?,
                    },
                )?;
                true
            }
            "restore-deleted-ctg" => {
                backend_restore_deleted_ctg(
                    &project_db,
                    projectId,
                    &RestoreDeletedCtgParams {
                        deleted_ctg_record_id: get_required_i64(&args, "deletedCtgRecordId")?,
                    },
                )?;
                true
            }
            "flip-seq" => {
                flip_seq(
                    &project_db,
                    projectId,
                    &FlipSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?;
                true
            }
            "hide-seq" => {
                hide_seq(
                    &project_db,
                    projectId,
                    &HideSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?
                .changed
            }
            "show-seq" => {
                show_seq(
                    &project_db,
                    projectId,
                    &ShowSeqParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                    },
                )?
                .changed
            }
            "set-end-type" => {
                set_end_type(
                    &project_db,
                    projectId,
                    &SetEndTypeParams {
                        assembly_seq_id: get_required_i64(&args, "assemblySeqId")?,
                        left_end_type: get_required_string(&args, "leftEndType")?,
                        right_end_type: get_required_string(&args, "rightEndType")?,
                    },
                )?
                .changed
            }
            _ => bail!("unsupported ctg editor action: {}", normalized),
        };
        Ok(json!({
            "action": normalized,
            "changed": changed
        }))
    })()
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn get_junction_inspection(
    workspaceRoot: String,
    projectId: i64,
    leftAssemblyCtgId: i64,
    rightAssemblyCtgId: i64,
    minAlignmentLength: Option<i64>,
    minMapq: Option<i64>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    tauri::async_runtime::spawn_blocking(move || {
        let params = GetJunctionInspectionParams {
            project_id: projectId,
            left_assembly_ctg_id: leftAssemblyCtgId,
            right_assembly_ctg_id: rightAssemblyCtgId,
            min_align_length: minAlignmentLength,
            min_mapq: minMapq,
        };
        let report = backend_get_junction_inspection(&project_db_path(&workspace_root), &params)?;
        let hits = report
            .hits
            .into_iter()
            .map(|hit| {
                json!({
                    "queryAssemblyCtgId": hit.query_assembly_ctg_id,
                    "querySourceSeqId": hit.query_source_seq_id,
                    "querySourceSeqName": hit.query_source_seq_name,
                    "subjectAssemblyCtgId": hit.subject_assembly_ctg_id,
                    "subjectSourceSeqId": hit.subject_source_seq_id,
                    "subjectSourceSeqName": hit.subject_source_seq_name,
                    "strand": hit.strand,
                    "queryStart": hit.query_start,
                    "queryEnd": hit.query_end,
                    "subjectStart": hit.subject_start,
                    "subjectEnd": hit.subject_end,
                    "mapq": hit.mapq,
                    "identityPct": hit.identity_pct,
                    "alignLength": hit.align_length,
                    "mismatchCount": hit.mismatch_count,
                    "gapOpenCount": hit.gap_open_count,
                    "evalue": hit.evalue,
                    "bitScore": hit.bit_score,
                    "evidenceOrigin": hit.evidence_origin
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": report.project_id,
            "assignedChrName": report.assigned_chr_name,
            "placementRelation": report.placement_relation,
            "overlapBp": report.overlap_bp,
            "gapBp": report.gap_bp,
            "sameDataset": report.same_dataset,
            "evidenceSource": report.evidence_source,
            "evidenceHitCount": report.evidence_hit_count,
            "left": {
                "assemblyCtgId": report.left.assembly_ctg_id,
                "name": report.left.name,
                "assignedChrName": report.left.assigned_chr_name,
                "anchorStart": report.left.anchor_start,
                "anchorEnd": report.left.anchor_end,
                "spanLength": report.left.span_length,
                "placementMode": report.left.placement_mode,
                "memberCount": report.left.member_count,
                "visibleMemberCount": report.left.visible_member_count,
                "datasetIds": report.left.dataset_ids,
                "datasetNames": report.left.dataset_names
            },
            "right": {
                "assemblyCtgId": report.right.assembly_ctg_id,
                "name": report.right.name,
                "assignedChrName": report.right.assigned_chr_name,
                "anchorStart": report.right.anchor_start,
                "anchorEnd": report.right.anchor_end,
                "spanLength": report.right.span_length,
                "placementMode": report.right.placement_mode,
                "memberCount": report.right.member_count,
                "visibleMemberCount": report.right.visible_member_count,
                "datasetIds": report.right.dataset_ids,
                "datasetNames": report.right.dataset_names
            },
            "hits": hits
        }))
    })
    .await
    .map_err(|join_error| format!("get_junction_inspection join error: {join_error}"))?
    .map_err(format_error)
}

#[tauri::command]
#[allow(non_snake_case)]
pub async fn get_track_pairwise_evidence(
    workspaceRoot: String,
    projectId: i64,
    topAssemblyCtgIds: Vec<i64>,
    bottomAssemblyCtgIds: Vec<i64>,
    minAlignmentLength: Option<i64>,
    minMapq: Option<i64>,
) -> Result<Value, String> {
    let workspace_root = workspaceRoot;
    tauri::async_runtime::spawn_blocking(move || {
        let params = GetTrackPairwiseEvidenceParams {
            project_id: projectId,
            top_assembly_ctg_ids: topAssemblyCtgIds,
            bottom_assembly_ctg_ids: bottomAssemblyCtgIds,
            min_align_length: minAlignmentLength,
            min_mapq: minMapq,
        };
        let report =
            backend_get_track_pairwise_evidence(&project_db_path(&workspace_root), &params)?;
        let hits = report
            .hits
            .into_iter()
            .map(|hit| {
                json!({
                    "queryAssemblyCtgId": hit.query_assembly_ctg_id,
                    "querySourceSeqId": hit.query_source_seq_id,
                    "querySourceSeqName": hit.query_source_seq_name,
                    "subjectAssemblyCtgId": hit.subject_assembly_ctg_id,
                    "subjectSourceSeqId": hit.subject_source_seq_id,
                    "subjectSourceSeqName": hit.subject_source_seq_name,
                    "strand": hit.strand,
                    "queryStart": hit.query_start,
                    "queryEnd": hit.query_end,
                    "subjectStart": hit.subject_start,
                    "subjectEnd": hit.subject_end,
                    "mapq": hit.mapq,
                    "identityPct": hit.identity_pct,
                    "alignLength": hit.align_length,
                    "mismatchCount": hit.mismatch_count,
                    "gapOpenCount": hit.gap_open_count,
                    "evalue": hit.evalue,
                    "bitScore": hit.bit_score,
                    "evidenceOrigin": hit.evidence_origin
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "projectId": report.project_id,
            "assignedChrName": report.assigned_chr_name,
            "sameDataset": report.same_dataset,
            "evidenceSource": report.evidence_source,
            "evidenceHitCount": report.evidence_hit_count,
            "topAssemblyCtgIds": report.top_assembly_ctg_ids,
            "bottomAssemblyCtgIds": report.bottom_assembly_ctg_ids,
            "hits": hits
        }))
    })
    .await
    .map_err(|join_error| format!("get_track_pairwise_evidence join error: {join_error}"))?
    .map_err(format_error)
}
