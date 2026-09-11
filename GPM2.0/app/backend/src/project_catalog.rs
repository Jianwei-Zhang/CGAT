//! User-facing catalog metadata. Canonical names remain package identifiers.
use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};

use crate::db::open_workspace_db;

#[derive(Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SequenceStatistics {
    pub sequence_count: usize,
    pub total_length_bp: i64,
    pub n50: Option<i64>,
    pub n90: Option<i64>,
    pub l50: Option<usize>,
    pub longest: Option<i64>,
}

fn statistics(mut lengths: Vec<i64>) -> Result<SequenceStatistics> {
    if lengths.iter().any(|length| *length < 0) {
        bail!("negative sequence length in dataset");
    }
    lengths.sort_unstable_by(|a, b| b.cmp(a));
    let total = lengths
        .iter()
        .try_fold(0_i64, |sum, length| sum.checked_add(*length))
        .ok_or_else(|| anyhow::anyhow!("dataset length exceeds supported range"))?;
    let mut result = SequenceStatistics {
        sequence_count: lengths.len(),
        total_length_bp: total,
        longest: lengths.first().copied(),
        ..Default::default()
    };
    let mut cumulative = 0_i128;
    for (index, length) in lengths.iter().enumerate() {
        cumulative += i128::from(*length);
        if total > 0 && result.n50.is_none() && cumulative * 100 >= i128::from(total) * 50 {
            result.n50 = Some(*length);
            result.l50 = Some(index + 1);
        }
        if total > 0 && result.n90.is_none() && cumulative * 100 >= i128::from(total) * 90 {
            result.n90 = Some(*length);
        }
    }
    Ok(result)
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CatalogEntry {
    pub object_type: String,
    pub object_id: i64,
    pub original_name: String,
    pub display_name: String,
    pub note: String,
    pub role: String,
    pub derived: bool,
    pub statistics: SequenceStatistics,
    /// Existing local directories, grouped at the chromosome partition root.
    pub locations: Vec<String>,
    pub available_file_count: usize,
    pub fasta_available: bool,
    pub self_alignment_available: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectCatalog {
    pub project_id: i64,
    pub datasets: Vec<CatalogEntry>,
    pub references: Vec<CatalogEntry>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CatalogUpdate {
    pub project_id: i64,
    pub object_type: String,
    pub object_id: i64,
    pub display_name: Option<String>,
    pub note: Option<String>,
    #[serde(default)]
    pub reset_name: bool,
}

fn open_existing(path: &Path) -> Result<Connection> {
    if !path.is_file() {
        bail!("workspace missing project.sqlite");
    }
    open_workspace_db(path)
}

pub fn list_project_catalog(path: &Path, project_id: i64) -> Result<ProjectCatalog> {
    list_with_connection(&open_existing(path)?, project_id)
}

pub fn resolve_catalog_directory(
    path: &Path,
    project_id: i64,
    object_type: &str,
    object_id: i64,
    location_index: usize,
) -> Result<PathBuf> {
    let catalog = list_project_catalog(path, project_id)?;
    let entry = catalog
        .datasets
        .iter()
        .chain(catalog.references.iter())
        .find(|entry| entry.object_type == object_type && entry.object_id == object_id)
        .ok_or_else(|| anyhow::anyhow!("catalog object does not belong to this project"))?;
    let location = entry
        .locations
        .get(location_index)
        .ok_or_else(|| anyhow::anyhow!("location no longer available"))?;
    let directory = Path::new(location).canonicalize()?;
    if !directory.is_dir() {
        bail!("location is not a directory");
    }
    Ok(directory)
}

fn containing_catalog_directory(file: &Path) -> Option<&Path> {
    // Standard packages split one dataset into chr/<chromosome>/<dataset>.fa.
    // Keep unplaced and other storage roots separate instead of broadening to
    // a shared workspace ancestor that also contains unrelated objects.
    file.ancestors()
        .skip(1)
        .find(|directory| directory.ends_with("data/partitions/chr"))
        .or_else(|| file.parent())
}

fn list_with_connection(conn: &Connection, project_id: i64) -> Result<ProjectCatalog> {
    let reference_id: i64 = conn.query_row(
        "SELECT reference_genome_id FROM project WHERE id = ?1",
        [project_id],
        |row| row.get(0),
    )?;
    let mut stmt = conn.prepare(
        "SELECT dataset_id, dataset_role FROM (
            SELECT dataset_id, dataset_role, display_order FROM project_dataset WHERE project_id = ?1
            UNION ALL
            SELECT DISTINCT s.dataset_id, 'derived', 2147483647 FROM derived_ctg_track_member m
            JOIN source_seq s ON s.id = m.source_seq_id
            WHERE m.project_id = ?1 AND NOT EXISTS(
                SELECT 1 FROM project_dataset pd WHERE pd.project_id = ?1 AND pd.dataset_id = s.dataset_id
            )
         ) ORDER BY display_order, dataset_id",
    )?;
    let ids = stmt
        .query_map([project_id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let datasets = ids
        .into_iter()
        .map(|(id, role)| read_entry(conn, "dataset", id, role))
        .collect::<Result<Vec<_>>>()?;
    Ok(ProjectCatalog {
        project_id,
        datasets,
        references: vec![read_entry(
            conn,
            "reference",
            reference_id,
            "reference".into(),
        )?],
    })
}

fn read_entry(conn: &Connection, kind: &str, id: i64, role: String) -> Result<CatalogEntry> {
    let reference = kind == "reference";
    let (table, sequences, foreign_key, locator, locator_key) = if reference {
        (
            "reference_genome",
            "reference_chr",
            "reference_genome_id",
            "reference_chr_locator",
            "reference_chr_id",
        )
    } else {
        (
            "dataset",
            "source_seq",
            "dataset_id",
            "source_seq_locator",
            "source_seq_id",
        )
    };
    let (original_name, display_name, note): (String, String, String) = conn.query_row(
        &format!("SELECT name, COALESCE(display_name, name), note FROM {table} WHERE id = ?1"),
        [id],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    )?;
    let mut stmt = conn.prepare(&format!(
        "SELECT s.length, l.fasta_path FROM {sequences} s LEFT JOIN {locator} l ON l.{locator_key} = s.id WHERE s.{foreign_key} = ?1"
    ))?;
    let rows = stmt
        .query_map([id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, Option<String>>(1)?))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let all_located = !rows.is_empty() && rows.iter().all(|(_, path)| path.is_some());
    let mut locations = rows
        .iter()
        .filter_map(|(_, path)| path.clone())
        .collect::<Vec<_>>();
    locations.sort();
    locations.dedup();
    let available_file_count = locations
        .iter()
        .filter(|path| Path::new(path).is_file())
        .count();
    let fasta_available = all_located && available_file_count == locations.len();
    locations.retain(|path| Path::new(path).is_file());
    locations = locations
        .iter()
        .filter_map(|path| containing_catalog_directory(Path::new(path)))
        .map(|directory| directory.to_string_lossy().into_owned())
        .collect();
    locations.sort();
    locations.dedup();
    let derived = !reference && conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM derived_ctg d JOIN source_seq s ON s.id = d.source_seq_id WHERE s.dataset_id = ?1)",
        [id], |row| row.get(0),
    )?;
    let self_alignment_available = !reference
        && conn.query_row(
            "SELECT self_alignment_available FROM dataset WHERE id = ?1",
            [id],
            |row| row.get(0),
        )?;
    Ok(CatalogEntry {
        object_type: kind.into(),
        object_id: id,
        original_name,
        display_name,
        note,
        role,
        derived,
        statistics: statistics(rows.into_iter().map(|(length, _)| length).collect())?,
        locations,
        available_file_count,
        fasta_available,
        self_alignment_available,
    })
}

pub fn update_project_catalog(path: &Path, request: &CatalogUpdate) -> Result<ProjectCatalog> {
    let mut conn = open_existing(path)?;
    let tx = conn.transaction()?;
    let (table, allowed): (&str, bool) = match request.object_type.as_str() {
        "dataset" => ("dataset", tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM project_dataset WHERE project_id = ?1 AND dataset_id = ?2)
             OR EXISTS(SELECT 1 FROM derived_ctg_track_member m JOIN source_seq s ON s.id = m.source_seq_id
                       WHERE m.project_id = ?1 AND s.dataset_id = ?2)",
            params![request.project_id, request.object_id], |row| row.get(0),
        )?),
        "reference" => ("reference_genome", tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM project WHERE id = ?1 AND reference_genome_id = ?2)",
            params![request.project_id, request.object_id], |row| row.get(0),
        )?),
        _ => bail!("unsupported catalog object type"),
    };
    if !allowed {
        bail!("catalog object does not belong to this project");
    }
    if request.reset_name && request.display_name.is_some() {
        bail!("cannot rename and reset the name together");
    }
    if let Some(name) = &request.display_name {
        let name = name.trim();
        if name.is_empty() || name.chars().count() > 200 || name.chars().any(char::is_control) {
            bail!("display name must contain 1 to 200 characters without control characters");
        }
        tx.execute(&format!("UPDATE {table} SET display_name = CASE WHEN name = ?1 THEN NULL ELSE ?1 END WHERE id = ?2"), params![name, request.object_id])?;
    } else if request.reset_name {
        tx.execute(
            &format!("UPDATE {table} SET display_name = NULL WHERE id = ?1"),
            [request.object_id],
        )?;
    }
    if let Some(note) = &request.note {
        if note.chars().count() > 10000 || note.contains('\0') {
            bail!("note exceeds 10000 characters or contains a null character");
        }
        tx.execute(
            &format!("UPDATE {table} SET note = ?1 WHERE id = ?2"),
            params![note, request.object_id],
        )?;
    }
    let result = list_with_connection(&tx, request.project_id)?;
    tx.commit()?;
    Ok(result)
}

#[cfg(test)]
mod tests;
