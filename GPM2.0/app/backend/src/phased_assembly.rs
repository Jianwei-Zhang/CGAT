use std::collections::HashSet;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use crate::db::open_workspace_db;

pub const DEFAULT_PHASED_TRACK_GAP_BEFORE_PX: i64 = 20;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhasedChrTrackItem {
    pub id: i64,
    pub phased_track_id: i64,
    pub assembly_ctg_id: i64,
    pub display_order: i64,
    pub gap_before_px: i64,
    pub orient: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhasedChrTrack {
    pub id: i64,
    pub project_id: i64,
    pub parent_chr_name: String,
    pub haplotype_key: String,
    pub label: String,
    pub display_order: i64,
    pub items: Vec<PhasedChrTrackItem>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhasedChrTracks {
    pub project_id: i64,
    pub parent_chr_name: String,
    pub tracks: Vec<PhasedChrTrack>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CreatePhasedChrTrackSummary {
    pub track: PhasedChrTrack,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeletePhasedChrTrackSummary {
    pub project_id: i64,
    pub phased_track_id: i64,
    pub parent_chr_name: String,
    pub haplotype_key: String,
    pub label: String,
    pub deleted: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddPhasedChrTrackItemSummary {
    pub item: PhasedChrTrackItem,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RemovePhasedChrTrackItemSummary {
    pub project_id: i64,
    pub phased_track_id: i64,
    pub phased_track_item_id: i64,
    pub removed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReorderPhasedChrTrackItemsSummary {
    pub project_id: i64,
    pub phased_track_id: i64,
    pub item_count: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlipPhasedChrTrackItemSummary {
    pub project_id: i64,
    pub phased_track_id: i64,
    pub phased_track_item_id: i64,
    pub assembly_ctg_id: i64,
    pub orient: String,
    pub changed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProjectContext {
    reference_genome_id: i64,
    phased_assembly_enabled: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TrackContext {
    id: i64,
    project_id: i64,
    parent_chr_name: String,
    haplotype_key: String,
    label: String,
}

pub fn list_phased_chr_tracks(
    project_db_path: &Path,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<PhasedChrTracks> {
    let conn = open_workspace_db(project_db_path)?;
    list_phased_chr_tracks_with_connection(&conn, project_id, parent_chr_name)
}

pub fn list_phased_chr_tracks_with_connection(
    conn: &Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<PhasedChrTracks> {
    validate_project_id(project_id)?;
    let parent_chr_name = normalize_parent_chr_name(parent_chr_name)?;
    let project = load_project_context(conn, project_id)?;
    validate_parent_chr(conn, project.reference_genome_id, &parent_chr_name)?;
    Ok(PhasedChrTracks {
        project_id,
        parent_chr_name: parent_chr_name.clone(),
        tracks: load_tracks_for_chr(conn, project_id, &parent_chr_name)?,
    })
}

pub fn create_phased_chr_track(
    project_db_path: &Path,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<CreatePhasedChrTrackSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    create_phased_chr_track_with_connection(&mut conn, project_id, parent_chr_name)
}

pub fn create_phased_chr_track_with_connection(
    conn: &mut Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<CreatePhasedChrTrackSummary> {
    validate_project_id(project_id)?;
    let parent_chr_name = normalize_parent_chr_name(parent_chr_name)?;
    let tx = conn.transaction()?;
    let project = load_project_context(&tx, project_id)?;
    if !project.phased_assembly_enabled {
        bail!("project_id {} has phased assembly disabled", project_id);
    }
    validate_parent_chr(&tx, project.reference_genome_id, &parent_chr_name)?;
    let haplotype_key = allocate_haplotype_key(&tx, project_id, &parent_chr_name)?;
    let display_order = next_track_display_order(&tx, project_id, &parent_chr_name)?;
    let label = format!("{}{}", parent_chr_name, haplotype_key);
    let created_at = now_timestamp_string();
    tx.execute(
        "INSERT INTO phased_chr_track (
            project_id, parent_chr_name, haplotype_key, label, display_order, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)",
        params![
            project_id,
            parent_chr_name,
            haplotype_key,
            label,
            display_order,
            created_at
        ],
    )
    .context("failed to insert phased chr track")?;
    let track_id = tx.last_insert_rowid();
    let track = load_track_by_id(&tx, project_id, track_id)?;
    tx.commit()?;
    Ok(CreatePhasedChrTrackSummary { track })
}

pub fn delete_phased_chr_track(
    project_db_path: &Path,
    project_id: i64,
    phased_track_id: i64,
) -> Result<DeletePhasedChrTrackSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    delete_phased_chr_track_with_connection(&mut conn, project_id, phased_track_id)
}

pub fn delete_phased_chr_track_with_connection(
    conn: &mut Connection,
    project_id: i64,
    phased_track_id: i64,
) -> Result<DeletePhasedChrTrackSummary> {
    validate_project_id(project_id)?;
    validate_positive_id("phased_track_id", phased_track_id)?;
    let tx = conn.transaction()?;
    let track = load_track_context(&tx, project_id, phased_track_id)?;
    tx.execute(
        "DELETE FROM phased_chr_track_item
         WHERE phased_track_id = ?1",
        params![phased_track_id],
    )
    .context("failed to delete phased chr track items")?;
    tx.execute(
        "DELETE FROM phased_chr_track
         WHERE project_id = ?1
           AND id = ?2",
        params![project_id, phased_track_id],
    )
    .context("failed to delete phased chr track")?;
    compact_phased_tracks_for_chr(&tx, project_id, &track.parent_chr_name)?;
    tx.commit()?;
    Ok(DeletePhasedChrTrackSummary {
        project_id,
        phased_track_id,
        parent_chr_name: track.parent_chr_name,
        haplotype_key: track.haplotype_key,
        label: track.label,
        deleted: true,
    })
}

fn compact_phased_tracks_for_chr(
    conn: &Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<()> {
    let mut stmt = conn
        .prepare(
            "SELECT id
             FROM phased_chr_track
             WHERE project_id = ?1
               AND parent_chr_name = ?2
             ORDER BY display_order ASC, id ASC",
        )
        .context("failed to prepare phased track compaction query")?;
    let track_ids = stmt
        .query_map(params![project_id, parent_chr_name], |row| {
            row.get::<_, i64>(0)
        })
        .context("failed to query phased tracks for compaction")?
        .collect::<rusqlite::Result<Vec<_>>>()
        .context("failed to decode phased tracks for compaction")?;
    for (index, track_id) in track_ids.iter().enumerate() {
        let haplotype_key = ((b'A' + index as u8) as char).to_string();
        let label = format!("{}{}", parent_chr_name, haplotype_key);
        conn.execute(
            "UPDATE phased_chr_track
             SET haplotype_key = ?1,
                 label = ?2,
                 display_order = ?3
             WHERE project_id = ?4
               AND id = ?5",
            params![
                haplotype_key,
                label,
                (index as i64) + 1,
                project_id,
                track_id
            ],
        )
        .context("failed to compact phased chr track")?;
    }
    Ok(())
}

pub fn add_ctg_to_phased_chr_track(
    project_db_path: &Path,
    project_id: i64,
    phased_track_id: i64,
    assembly_ctg_id: i64,
) -> Result<AddPhasedChrTrackItemSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    add_ctg_to_phased_chr_track_with_connection(
        &mut conn,
        project_id,
        phased_track_id,
        assembly_ctg_id,
    )
}

pub fn add_ctg_to_phased_chr_track_with_connection(
    conn: &mut Connection,
    project_id: i64,
    phased_track_id: i64,
    assembly_ctg_id: i64,
) -> Result<AddPhasedChrTrackItemSummary> {
    validate_project_id(project_id)?;
    validate_positive_id("phased_track_id", phased_track_id)?;
    validate_positive_id("assembly_ctg_id", assembly_ctg_id)?;
    let tx = conn.transaction()?;
    let track = load_track_context(&tx, project_id, phased_track_id)?;
    validate_ctg_for_track(&tx, project_id, assembly_ctg_id, &track.parent_chr_name)?;
    let orient = load_ctg_orient(&tx, project_id, assembly_ctg_id)?;
    let display_order = next_item_display_order(&tx, phased_track_id)?;
    let created_at = now_timestamp_string();
    tx.execute(
        "INSERT INTO phased_chr_track_item (
            phased_track_id, assembly_ctg_id, display_order, gap_before_px, orient, created_at, note
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)",
        params![
            phased_track_id,
            assembly_ctg_id,
            display_order,
            DEFAULT_PHASED_TRACK_GAP_BEFORE_PX,
            orient,
            created_at
        ],
    )
    .context("failed to insert phased chr track item")?;
    let item_id = tx.last_insert_rowid();
    let item = load_track_item_by_id(&tx, phased_track_id, item_id)?;
    tx.commit()?;
    Ok(AddPhasedChrTrackItemSummary { item })
}

pub fn remove_phased_chr_track_item(
    project_db_path: &Path,
    project_id: i64,
    phased_track_item_id: i64,
) -> Result<RemovePhasedChrTrackItemSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    remove_phased_chr_track_item_with_connection(&mut conn, project_id, phased_track_item_id)
}

pub fn remove_phased_chr_track_item_with_connection(
    conn: &mut Connection,
    project_id: i64,
    phased_track_item_id: i64,
) -> Result<RemovePhasedChrTrackItemSummary> {
    validate_project_id(project_id)?;
    validate_positive_id("phased_track_item_id", phased_track_item_id)?;
    let tx = conn.transaction()?;
    let phased_track_id: i64 = tx
        .query_row(
            "SELECT t.id
             FROM phased_chr_track_item i
             JOIN phased_chr_track t ON t.id = i.phased_track_id
             WHERE t.project_id = ?1
               AND i.id = ?2",
            params![project_id, phased_track_item_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to load phased track item before remove")?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "phased_track_item_id {} does not exist in project_id {}",
                phased_track_item_id,
                project_id
            )
        })?;
    tx.execute(
        "DELETE FROM phased_chr_track_item
         WHERE id = ?1",
        params![phased_track_item_id],
    )
    .context("failed to remove phased chr track item")?;
    tx.commit()?;
    Ok(RemovePhasedChrTrackItemSummary {
        project_id,
        phased_track_id,
        phased_track_item_id,
        removed: true,
    })
}

pub fn flip_phased_chr_track_item(
    project_db_path: &Path,
    project_id: i64,
    phased_track_item_id: i64,
) -> Result<FlipPhasedChrTrackItemSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    flip_phased_chr_track_item_with_connection(&mut conn, project_id, phased_track_item_id)
}

pub fn flip_phased_chr_track_item_with_connection(
    conn: &mut Connection,
    project_id: i64,
    phased_track_item_id: i64,
) -> Result<FlipPhasedChrTrackItemSummary> {
    validate_project_id(project_id)?;
    validate_positive_id("phased_track_item_id", phased_track_item_id)?;
    let tx = conn.transaction()?;
    let before = tx
        .query_row(
            "SELECT i.phased_track_id, i.assembly_ctg_id, i.orient
             FROM phased_chr_track_item i
             JOIN phased_chr_track t ON t.id = i.phased_track_id
             WHERE t.project_id = ?1
               AND i.id = ?2",
            params![project_id, phased_track_item_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, String>(2)?,
                ))
            },
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "phased_track_item_id {} does not exist in project_id {}",
                phased_track_item_id,
                project_id
            )
        })?;
    let next_orient = flip_orient(&before.2)?;
    tx.execute(
        "UPDATE phased_chr_track_item
         SET orient = ?1
         WHERE id = ?2",
        params![next_orient, phased_track_item_id],
    )
    .context("failed to flip phased chr track item orient")?;
    tx.commit()?;
    Ok(FlipPhasedChrTrackItemSummary {
        project_id,
        phased_track_id: before.0,
        phased_track_item_id,
        assembly_ctg_id: before.1,
        orient: next_orient.to_string(),
        changed: true,
    })
}

pub fn reorder_phased_chr_track_items(
    project_db_path: &Path,
    project_id: i64,
    phased_track_id: i64,
    item_ids: &[i64],
) -> Result<ReorderPhasedChrTrackItemsSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    reorder_phased_chr_track_items_with_connection(&mut conn, project_id, phased_track_id, item_ids)
}

pub fn reorder_phased_chr_track_items_with_connection(
    conn: &mut Connection,
    project_id: i64,
    phased_track_id: i64,
    item_ids: &[i64],
) -> Result<ReorderPhasedChrTrackItemsSummary> {
    validate_project_id(project_id)?;
    validate_positive_id("phased_track_id", phased_track_id)?;
    let tx = conn.transaction()?;
    load_track_context(&tx, project_id, phased_track_id)?;
    let current_ids = load_track_item_ids(&tx, phased_track_id)?;
    let requested_ids = normalize_requested_item_ids(item_ids)?;
    let mut current_sorted = current_ids;
    current_sorted.sort_unstable();
    let mut requested_sorted = requested_ids.clone();
    requested_sorted.sort_unstable();
    if current_sorted != requested_sorted {
        bail!("item_ids must exactly match the current phased track items");
    }
    for (index, item_id) in requested_ids.iter().copied().enumerate() {
        tx.execute(
            "UPDATE phased_chr_track_item
             SET display_order = ?1
             WHERE id = ?2",
            params![index as i64 + 1, item_id],
        )
        .with_context(|| format!("failed to update display_order for item {}", item_id))?;
    }
    tx.commit()?;
    Ok(ReorderPhasedChrTrackItemsSummary {
        project_id,
        phased_track_id,
        item_count: requested_ids.len() as i64,
    })
}

fn validate_project_id(project_id: i64) -> Result<()> {
    validate_positive_id("project_id", project_id)
}

fn validate_positive_id(field_name: &str, value: i64) -> Result<()> {
    if value <= 0 {
        bail!("{} must be > 0", field_name);
    }
    Ok(())
}

fn normalize_parent_chr_name(parent_chr_name: &str) -> Result<String> {
    let normalized = parent_chr_name.trim();
    if normalized.is_empty() {
        bail!("parent_chr_name must not be blank");
    }
    Ok(normalized.to_string())
}

fn load_project_context(conn: &Connection, project_id: i64) -> Result<ProjectContext> {
    conn.query_row(
        "SELECT reference_genome_id, phased_assembly_enabled
         FROM project
         WHERE id = ?1",
        params![project_id],
        |row| {
            Ok(ProjectContext {
                reference_genome_id: row.get(0)?,
                phased_assembly_enabled: row.get::<_, i64>(1)? > 0,
            })
        },
    )
    .optional()
    .context("failed to load project phased assembly context")?
    .ok_or_else(|| anyhow::anyhow!("project_id {} does not exist", project_id))
}

fn validate_parent_chr(
    conn: &Connection,
    reference_genome_id: i64,
    parent_chr_name: &str,
) -> Result<()> {
    let exists: i64 = conn
        .query_row(
            "SELECT EXISTS(
                SELECT 1
                FROM reference_chr
                WHERE reference_genome_id = ?1
                  AND chr_name = ?2
                LIMIT 1
             )",
            params![reference_genome_id, parent_chr_name],
            |row| row.get(0),
        )
        .with_context(|| format!("failed to validate parent chr {}", parent_chr_name))?;
    if exists <= 0 {
        bail!(
            "parent_chr_name '{}' does not exist for reference_genome_id {}",
            parent_chr_name,
            reference_genome_id
        );
    }
    Ok(())
}

fn allocate_haplotype_key(
    conn: &Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<String> {
    let mut stmt = conn
        .prepare(
            "SELECT haplotype_key
             FROM phased_chr_track
             WHERE project_id = ?1
               AND parent_chr_name = ?2",
        )
        .context("failed to prepare phased track key query")?;
    let used = stmt
        .query_map(params![project_id, parent_chr_name], |row| {
            row.get::<_, String>(0)
        })
        .context("failed to query phased track keys")?
        .collect::<std::result::Result<HashSet<_>, _>>()
        .context("failed to decode phased track keys")?;
    for byte in b'A'..=b'Z' {
        let key = (byte as char).to_string();
        if !used.contains(&key) {
            return Ok(key);
        }
    }
    bail!(
        "parent_chr_name '{}' already has the maximum 26 phased tracks",
        parent_chr_name
    );
}

fn next_track_display_order(
    conn: &Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<i64> {
    conn.query_row(
        "SELECT COALESCE(MAX(display_order), 0) + 1
         FROM phased_chr_track
         WHERE project_id = ?1
           AND parent_chr_name = ?2",
        params![project_id, parent_chr_name],
        |row| row.get(0),
    )
    .context("failed to calculate next phased track display_order")
}

fn next_item_display_order(conn: &Connection, phased_track_id: i64) -> Result<i64> {
    conn.query_row(
        "SELECT COALESCE(MAX(display_order), 0) + 1
         FROM phased_chr_track_item
         WHERE phased_track_id = ?1",
        params![phased_track_id],
        |row| row.get(0),
    )
    .context("failed to calculate next phased track item display_order")
}

fn load_track_context(
    conn: &Connection,
    project_id: i64,
    phased_track_id: i64,
) -> Result<TrackContext> {
    conn.query_row(
        "SELECT id, project_id, parent_chr_name, haplotype_key, label
         FROM phased_chr_track
         WHERE project_id = ?1
           AND id = ?2",
        params![project_id, phased_track_id],
        |row| {
            Ok(TrackContext {
                id: row.get(0)?,
                project_id: row.get(1)?,
                parent_chr_name: row.get(2)?,
                haplotype_key: row.get(3)?,
                label: row.get(4)?,
            })
        },
    )
    .optional()
    .context("failed to load phased track context")?
    .ok_or_else(|| {
        anyhow::anyhow!(
            "phased_track_id {} does not exist in project_id {}",
            phased_track_id,
            project_id
        )
    })
}

fn validate_ctg_for_track(
    conn: &Connection,
    project_id: i64,
    assembly_ctg_id: i64,
    parent_chr_name: &str,
) -> Result<()> {
    let assigned_chr_name: Option<String> = conn
        .query_row(
            "SELECT assigned_chr_name
             FROM assembly_ctg
             WHERE project_id = ?1
               AND id = ?2",
            params![project_id, assembly_ctg_id],
            |row| row.get(0),
        )
        .optional()
        .context("failed to load assembly_ctg for phased track item")?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_ctg_id {} does not exist in project_id {}",
                assembly_ctg_id,
                project_id
            )
        })?;
    if assigned_chr_name.as_deref() != Some(parent_chr_name) {
        bail!(
            "assembly_ctg_id {} is not assigned to parent_chr_name '{}'",
            assembly_ctg_id,
            parent_chr_name
        );
    }
    Ok(())
}

fn load_ctg_orient(conn: &Connection, project_id: i64, assembly_ctg_id: i64) -> Result<String> {
    let orient: String = conn
        .query_row(
            "SELECT s.orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.project_id = ?1
               AND c.id = ?2",
            params![project_id, assembly_ctg_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "assembly_ctg_id {} does not exist in project_id {}",
                assembly_ctg_id,
                project_id
            )
        })?;
    Ok(normalize_orient(&orient)?.to_string())
}

fn normalize_orient(value: &str) -> Result<&'static str> {
    match value.trim() {
        "+" => Ok("+"),
        "-" => Ok("-"),
        _ => bail!("unsupported orient value: {}", value),
    }
}

fn flip_orient(value: &str) -> Result<&'static str> {
    match normalize_orient(value)? {
        "+" => Ok("-"),
        "-" => Ok("+"),
        _ => unreachable!(),
    }
}

fn load_track_by_id(
    conn: &Connection,
    project_id: i64,
    phased_track_id: i64,
) -> Result<PhasedChrTrack> {
    let mut tracks = load_tracks_by_ids(conn, project_id, &[phased_track_id])?;
    tracks
        .pop()
        .ok_or_else(|| anyhow::anyhow!("failed to load created phased track {}", phased_track_id))
}

fn load_tracks_for_chr(
    conn: &Connection,
    project_id: i64,
    parent_chr_name: &str,
) -> Result<Vec<PhasedChrTrack>> {
    let mut stmt = conn
        .prepare(
            "SELECT id
             FROM phased_chr_track
             WHERE project_id = ?1
               AND parent_chr_name = ?2
             ORDER BY display_order, id",
        )
        .context("failed to prepare phased chr track list query")?;
    let ids = stmt
        .query_map(params![project_id, parent_chr_name], |row| {
            row.get::<_, i64>(0)
        })
        .context("failed to query phased chr track ids")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode phased chr track ids")?;
    load_tracks_by_ids(conn, project_id, &ids)
}

fn load_tracks_by_ids(
    conn: &Connection,
    project_id: i64,
    track_ids: &[i64],
) -> Result<Vec<PhasedChrTrack>> {
    if track_ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut tracks = Vec::with_capacity(track_ids.len());
    for track_id in track_ids {
        let mut track = conn
            .query_row(
                "SELECT id, project_id, parent_chr_name, haplotype_key, label, display_order
                 FROM phased_chr_track
                 WHERE project_id = ?1
                   AND id = ?2",
                params![project_id, track_id],
                |row| {
                    Ok(PhasedChrTrack {
                        id: row.get(0)?,
                        project_id: row.get(1)?,
                        parent_chr_name: row.get(2)?,
                        haplotype_key: row.get(3)?,
                        label: row.get(4)?,
                        display_order: row.get(5)?,
                        items: Vec::new(),
                    })
                },
            )
            .optional()
            .with_context(|| format!("failed to load phased track {}", track_id))?
            .ok_or_else(|| anyhow::anyhow!("phased_track_id {} does not exist", track_id))?;
        track.items = load_track_items(conn, *track_id)?;
        tracks.push(track);
    }
    Ok(tracks)
}

fn load_track_items(conn: &Connection, phased_track_id: i64) -> Result<Vec<PhasedChrTrackItem>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, phased_track_id, assembly_ctg_id, display_order, gap_before_px, orient
             FROM phased_chr_track_item
             WHERE phased_track_id = ?1
             ORDER BY display_order, id",
        )
        .context("failed to prepare phased track item query")?;
    stmt.query_map(params![phased_track_id], |row| {
        Ok(PhasedChrTrackItem {
            id: row.get(0)?,
            phased_track_id: row.get(1)?,
            assembly_ctg_id: row.get(2)?,
            display_order: row.get(3)?,
            gap_before_px: row.get(4)?,
            orient: row.get(5)?,
        })
    })
    .context("failed to query phased track items")?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode phased track items")
}

fn load_track_item_by_id(
    conn: &Connection,
    phased_track_id: i64,
    item_id: i64,
) -> Result<PhasedChrTrackItem> {
    conn.query_row(
        "SELECT id, phased_track_id, assembly_ctg_id, display_order, gap_before_px, orient
         FROM phased_chr_track_item
         WHERE phased_track_id = ?1
           AND id = ?2",
        params![phased_track_id, item_id],
        |row| {
            Ok(PhasedChrTrackItem {
                id: row.get(0)?,
                phased_track_id: row.get(1)?,
                assembly_ctg_id: row.get(2)?,
                display_order: row.get(3)?,
                gap_before_px: row.get(4)?,
                orient: row.get(5)?,
            })
        },
    )
    .optional()
    .context("failed to load phased track item")?
    .ok_or_else(|| anyhow::anyhow!("phased_track_item_id {} does not exist", item_id))
}

fn load_track_item_ids(conn: &Connection, phased_track_id: i64) -> Result<Vec<i64>> {
    let mut stmt = conn
        .prepare(
            "SELECT id
             FROM phased_chr_track_item
             WHERE phased_track_id = ?1
             ORDER BY display_order, id",
        )
        .context("failed to prepare phased track item id query")?;
    stmt.query_map(params![phased_track_id], |row| row.get::<_, i64>(0))
        .context("failed to query phased track item ids")?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode phased track item ids")
}

fn normalize_requested_item_ids(item_ids: &[i64]) -> Result<Vec<i64>> {
    let mut seen = HashSet::new();
    let mut normalized = Vec::with_capacity(item_ids.len());
    for item_id in item_ids.iter().copied() {
        validate_positive_id("item_id", item_id)?;
        if !seen.insert(item_id) {
            bail!("item_ids contains duplicate item_id {}", item_id);
        }
        normalized.push(item_id);
    }
    Ok(normalized)
}

fn now_timestamp_string() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs())
        .unwrap_or(0);
    secs.to_string()
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::*;
    use crate::ctg_editor::{FlipCtgParams, flip_ctg_with_connection};
    use crate::db::init_workspace_schema;
    use rusqlite::{Connection, params};

    #[derive(Debug, Clone)]
    struct SeededProject {
        project_id: i64,
        chr01_ctg_id: i64,
        chr02_ctg_id: i64,
    }

    fn seed_project(conn: &Connection, phased_enabled: bool) -> SeededProject {
        init_workspace_schema(conn).unwrap();
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'sp', 'v1', 'D:/ref.fa', 'D:/ref.fa.fai')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (1, 1, 'Chr01', 1, 1000000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
             VALUES (2, 1, 'Chr02', 2, 1000000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (11, 'primary', 'asm', NULL, 'D:/primary.fa', 'D:/primary.fa.fai')",
            [],
        )
        .unwrap();
        for (source_seq_id, seq_name, seq_order) in
            [(101_i64, "tigA", 1_i64), (102_i64, "tigB", 2_i64)]
        {
            conn.execute(
                "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
                 VALUES (?1, 11, ?2, ?3, 1000)",
                params![source_seq_id, seq_name, seq_order],
            )
            .unwrap();
        }
        conn.execute(
            "INSERT INTO project (
                id, name, version, reference_genome_id, primary_dataset_id,
                auto_check_new_seq, phased_assembly_enabled,
                chr_assignment_min_coverage_percent, description, created_at, note
             ) VALUES (7, 'p', 1, 1, 11, 0, ?1, 60.0, NULL, '1', NULL)",
            params![if phased_enabled { 1_i64 } else { 0_i64 }],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
             VALUES (7, 11, 'primary', 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (
                id, project_id, source_seq_id, instance_key, orient, source_start, source_end,
                left_end_type, right_end_type, hidden, created_at, note
             ) VALUES (201, 7, 101, 'chr:Chr01', '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (
                id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
                anchor_start, ref_orient, placement_mode, created_at, note
             ) VALUES (301, 7, 201, 'tigA@Chr01', 'Chr01', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_seq (
                id, project_id, source_seq_id, instance_key, orient, source_start, source_end,
                left_end_type, right_end_type, hidden, created_at, note
             ) VALUES (202, 7, 102, 'chr:Chr02', '+', 1, 1000, 'normal', 'normal', 0, '1', NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO assembly_ctg (
                id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
                anchor_start, ref_orient, placement_mode, created_at, note
             ) VALUES (302, 7, 202, 'tigB@Chr02', 'Chr02', 1, 100, '+', 'auto', '1', NULL)",
            [],
        )
        .unwrap();
        SeededProject {
            project_id: 7,
            chr01_ctg_id: 301,
            chr02_ctg_id: 302,
        }
    }

    #[test]
    fn schema_defaults_phased_assembly_to_disabled() {
        let conn = Connection::open_in_memory().unwrap();
        init_workspace_schema(&conn).unwrap();
        let columns = conn
            .prepare("PRAGMA table_info(project)")
            .unwrap()
            .query_map([], |row| {
                Ok((row.get::<_, String>(1)?, row.get::<_, Option<String>>(4)?))
            })
            .unwrap()
            .collect::<std::result::Result<HashMap<_, _>, _>>()
            .unwrap();
        assert_eq!(
            columns
                .get("phased_assembly_enabled")
                .and_then(|value| value.as_deref()),
            Some("0")
        );
    }

    #[test]
    fn create_track_allocates_keys_per_chr_and_requires_enabled_project() {
        let mut disabled = Connection::open_in_memory().unwrap();
        let disabled_seed = seed_project(&disabled, false);
        let error = create_phased_chr_track_with_connection(
            &mut disabled,
            disabled_seed.project_id,
            "Chr01",
        )
        .unwrap_err();
        assert!(error.to_string().contains("disabled"));

        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        let first =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();
        let second =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();
        let chr02 =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr02").unwrap();

        assert_eq!(first.track.haplotype_key, "A");
        assert_eq!(first.track.label, "Chr01A");
        assert_eq!(second.track.haplotype_key, "B");
        assert_eq!(second.track.label, "Chr01B");
        assert_eq!(chr02.track.haplotype_key, "A");
        assert_eq!(chr02.track.label, "Chr02A");
    }

    #[test]
    fn create_track_rejects_more_than_a_to_z_for_one_chr() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        for expected_key in 'A'..='Z' {
            let summary =
                create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01")
                    .unwrap();
            assert_eq!(summary.track.haplotype_key, expected_key.to_string());
        }

        let error = create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01")
            .unwrap_err();
        assert!(error.to_string().contains("maximum 26"));
    }

    #[test]
    fn add_allows_duplicate_ctg_references_and_removes_one_item_only() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        let track =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();

        let first = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();
        let second = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();

        assert_ne!(first.item.id, second.item.id);
        assert_eq!(first.item.display_order, 1);
        assert_eq!(second.item.display_order, 2);
        assert_eq!(first.item.gap_before_px, DEFAULT_PHASED_TRACK_GAP_BEFORE_PX);
        assert_eq!(first.item.orient, "+");

        remove_phased_chr_track_item_with_connection(&mut conn, seed.project_id, first.item.id)
            .unwrap();
        let tracks =
            list_phased_chr_tracks_with_connection(&conn, seed.project_id, "Chr01").unwrap();
        assert_eq!(tracks.tracks[0].items.len(), 1);
        assert_eq!(tracks.tracks[0].items[0].id, second.item.id);
    }

    #[test]
    fn phased_track_item_orientation_is_independent_from_source_ctg() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        let track =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();

        let first = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();
        let second = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();

        let flipped =
            flip_phased_chr_track_item_with_connection(&mut conn, seed.project_id, first.item.id)
                .unwrap();
        assert_eq!(flipped.phased_track_item_id, first.item.id);
        assert_eq!(flipped.assembly_ctg_id, seed.chr01_ctg_id);
        assert_eq!(flipped.orient, "-");

        let source_orient: String = conn
            .query_row(
                "SELECT s.orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.id = ?1",
                params![seed.chr01_ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(source_orient, "+");

        let tracks =
            list_phased_chr_tracks_with_connection(&conn, seed.project_id, "Chr01").unwrap();
        assert_eq!(tracks.tracks[0].items[0].id, first.item.id);
        assert_eq!(tracks.tracks[0].items[0].orient, "-");
        assert_eq!(tracks.tracks[0].items[1].id, second.item.id);
        assert_eq!(tracks.tracks[0].items[1].orient, "+");

        flip_ctg_with_connection(
            &mut conn,
            seed.project_id,
            &FlipCtgParams {
                assembly_ctg_id: seed.chr01_ctg_id,
            },
        )
        .unwrap();
        let source_orient_after_main_flip: String = conn
            .query_row(
                "SELECT s.orient
                 FROM assembly_ctg c
                 JOIN assembly_seq s ON s.id = c.assembly_seq_id
                 WHERE c.id = ?1",
                params![seed.chr01_ctg_id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(source_orient_after_main_flip, "-");

        let tracks_after_main_flip =
            list_phased_chr_tracks_with_connection(&conn, seed.project_id, "Chr01").unwrap();
        assert_eq!(tracks_after_main_flip.tracks[0].items[0].orient, "-");
        assert_eq!(tracks_after_main_flip.tracks[0].items[1].orient, "+");
    }

    #[test]
    fn add_rejects_ctg_from_other_parent_chr() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        let track =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();

        let error = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr02_ctg_id,
        )
        .unwrap_err();
        assert!(error.to_string().contains("not assigned"));
    }

    #[test]
    fn reorder_requires_exact_item_set_and_delete_compacts_tracks() {
        let mut conn = Connection::open_in_memory().unwrap();
        let seed = seed_project(&conn, true);
        let track =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();
        let middle =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();
        let last =
            create_phased_chr_track_with_connection(&mut conn, seed.project_id, "Chr01").unwrap();
        let first = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();
        let second = add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();
        add_ctg_to_phased_chr_track_with_connection(
            &mut conn,
            seed.project_id,
            last.track.id,
            seed.chr01_ctg_id,
        )
        .unwrap();

        let deleted_middle =
            delete_phased_chr_track_with_connection(&mut conn, seed.project_id, middle.track.id)
                .unwrap();
        assert!(deleted_middle.deleted);
        let compacted =
            list_phased_chr_tracks_with_connection(&conn, seed.project_id, "Chr01").unwrap();
        assert_eq!(
            compacted
                .tracks
                .iter()
                .map(|track| (track.id, track.haplotype_key.as_str(), track.label.as_str()))
                .collect::<Vec<_>>(),
            vec![
                (track.track.id, "A", "Chr01A"),
                (last.track.id, "B", "Chr01B"),
            ]
        );

        reorder_phased_chr_track_items_with_connection(
            &mut conn,
            seed.project_id,
            track.track.id,
            &[second.item.id, first.item.id],
        )
        .unwrap();
        let tracks =
            list_phased_chr_tracks_with_connection(&conn, seed.project_id, "Chr01").unwrap();
        assert_eq!(tracks.tracks[0].items[0].id, second.item.id);
        assert_eq!(tracks.tracks[0].items[1].id, first.item.id);

        remove_phased_chr_track_item_with_connection(&mut conn, seed.project_id, first.item.id)
            .unwrap();
        remove_phased_chr_track_item_with_connection(&mut conn, seed.project_id, second.item.id)
            .unwrap();
        let summary =
            delete_phased_chr_track_with_connection(&mut conn, seed.project_id, track.track.id)
                .unwrap();
        assert!(summary.deleted);
    }
}
