//! Project/Overview metadata only. Assembly evidence stays on the existing path.
use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use anyhow::Result;
use rusqlite::{Connection, params};
use serde_json::{Value, json};

use super::{list_chr_view_ctgs_with_connection_options, list_project_chromosomes_with_connection};
use crate::db::open_workspace_db;
use crate::phased_assembly::list_project_phased_chr_tracks_with_connection;

pub fn get_project_overview_sources(db: &Path, project_id: i64) -> Result<Value> {
    let conn = open_workspace_db(db)?;
    // All metadata in this response belongs to one read snapshot. No cache or
    // scientific-data writes are performed by the source reader.
    let tx = conn.unchecked_transaction()?;
    let result = get_project_overview_sources_with_connection(&tx, project_id)?;
    tx.commit()?;
    Ok(result)
}

pub fn get_project_overview_sources_with_connection(
    conn: &Connection,
    project_id: i64,
) -> Result<Value> {
    let chromosomes = list_project_chromosomes_with_connection(conn, project_id)?;
    let known_chromosomes = chromosomes
        .items
        .iter()
        .map(|chr| chr.chr_name.as_str())
        .collect::<HashSet<_>>();
    let primary_dataset_id: i64 = conn.query_row(
        "SELECT primary_dataset_id FROM project WHERE id = ?1",
        [project_id],
        |row| row.get(0),
    )?;
    // Match the primary-dataset branch of list_chr_view_ctgs exactly, including
    // visible derived sources targeted to the primary dataset. datasetId alone
    // cannot reconstruct that membership, especially for hidden derived items.
    let mut stmt = conn.prepare(
        "SELECT c.id FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         JOIN source_seq ss ON ss.id = s.source_seq_id
         LEFT JOIN derived_ctg_track_member dtm
           ON dtm.project_id = c.project_id AND dtm.source_seq_id = ss.id
         WHERE c.project_id = ?1 AND s.hidden = 0
           AND (ss.dataset_id = ?2 OR dtm.target_dataset_id = ?2)
         ORDER BY c.id",
    )?;
    let primary_ctg_ids = stmt
        .query_map(params![project_id, primary_dataset_id], |row| {
            row.get::<_, i64>(0)
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    // One project-wide summary fetch replaces all per-chromosome full-evidence
    // calls. Keep the existing provenance/ordering rules; do not compute hits,
    // N regions, telomere marks, centromere marks or CIGAR projection here.
    let ctgs = list_chr_view_ctgs_with_connection_options(conn, project_id, None, None, false)?
        .into_iter()
        .filter(|ctg| {
            ctg.assigned_chr_name
                .as_deref()
                .is_some_and(|name| known_chromosomes.contains(name))
        })
        .map(|ctg| {
            json!({
                "assemblyCtgId": ctg.assembly_ctg_id,
                "name": ctg.name,
                "originId": ctg.origin_id,
                "coAssignedChrNames": ctg.co_assigned_chr_names,
                "assignedChrName": ctg.assigned_chr_name,
                "chrOrder": ctg.chr_order,
                "anchorStart": ctg.anchor_start,
                "refOrient": ctg.ref_orient,
                "orient": ctg.orient,
                "placementMode": ctg.placement_mode,
                "memberCount": ctg.member_count,
                "totalLength": ctg.total_length,
                "datasetId": ctg.dataset_id,
                "datasetName": ctg.dataset_name,
                "derivedSource": ctg.derived_source,
                "derivedTargetDatasetId": ctg.derived_target_dataset_id,
                "derivedTargetDatasetName": ctg.derived_target_dataset_name,
                "sourceFragment": ctg.source_fragment
            })
        })
        .collect::<Vec<_>>();
    let mut phased_tracks_by_chr = BTreeMap::<String, Vec<Value>>::new();
    for track in list_project_phased_chr_tracks_with_connection(conn, project_id)? {
        if !known_chromosomes.contains(track.parent_chr_name.as_str()) {
            continue;
        }
        let items = track
            .items
            .into_iter()
            .map(|item| {
                json!({
                    "itemId": item.id,
                    "phasedTrackId": item.phased_track_id,
                    "assemblyCtgId": item.assembly_ctg_id,
                    "displayOrder": item.display_order,
                    "gapBeforePx": item.gap_before_px,
                    "orient": item.orient
                })
            })
            .collect::<Vec<_>>();
        let parent = track.parent_chr_name.clone();
        phased_tracks_by_chr.entry(parent).or_default().push(json!({
            "phasedTrackId": track.id,
            "projectId": track.project_id,
            "parentChrName": track.parent_chr_name,
            "haplotypeKey": track.haplotype_key,
            "label": track.label,
            "displayOrder": track.display_order,
            "items": items
        }));
    }
    let items = chromosomes
        .items
        .iter()
        .map(|chr| {
            json!({
                "chrName": chr.chr_name,
                "chrOrder": chr.chr_order,
                "chrLength": chr.chr_length,
                "ctgCount": chr.ctg_count,
                "placedBp": chr.placed_bp
            })
        })
        .collect::<Vec<_>>();
    Ok(json!({
        "projectId": chromosomes.project_id,
        "referenceGenomeId": chromosomes.reference_genome_id,
        "chromosomes": items,
        "unplacedCtgCount": chromosomes.unplaced_ctg_count,
        "unplacedBp": chromosomes.unplaced_bp,
        "ctgs": ctgs,
        "primaryCtgIds": primary_ctg_ids,
        "phasedChrTracksByChr": phased_tracks_by_chr
    }))
}

#[cfg(test)]
mod tests;
