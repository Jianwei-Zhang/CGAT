//! Explicit opt-in diagnostics. All inputs stay read-only; output must be a
//! caller-supplied private scratch directory, never an existing project path.
use super::pack_reference_track_members;
use crate::main_view::reference_transport::compact_reference_track_members;
use crate::main_view::{
    list_chr_view_ctgs_with_connection, list_reference_track_members_with_connection,
};
use rusqlite::{Connection, OpenFlags};
use serde_json::json;
use std::{
    fs::{self, OpenOptions},
    io::{BufWriter, Write},
    path::PathBuf,
    time::Instant,
};

#[test]
#[ignore = "set GPM_REFERENCE_READONLY_DB and GPM_REFERENCE_PROFILE_OUTPUT to private scratch"]
fn profile_large_reference_tracks_readonly() {
    let path = PathBuf::from(std::env::var("GPM_REFERENCE_READONLY_DB").expect("set read-only DB"));
    let output =
        PathBuf::from(std::env::var("GPM_REFERENCE_PROFILE_OUTPUT").expect("set private output"));
    assert!(output.is_dir());
    assert!(!output.join("project.sqlite").exists());
    assert!(
        !output
            .canonicalize()
            .unwrap()
            .starts_with(path.parent().unwrap().canonicalize().unwrap())
    );
    let before = fs::metadata(&path).unwrap();
    let conn = Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    conn.execute_batch("PRAGMA query_only=ON; BEGIN;").unwrap();
    let project_id: i64 = std::env::var("GPM_REFERENCE_PROJECT_ID")
        .unwrap_or_else(|_| "1".into())
        .parse()
        .unwrap();
    let chr = std::env::var("GPM_REFERENCE_CHR").unwrap_or_else(|_| "chr1".into());
    let mut samples = Vec::new();
    for sample in 0..3 {
        for encoding in ["v1", "v2"] {
            let start = Instant::now();
            let items =
                list_reference_track_members_with_connection(&conn, project_id, &chr).unwrap();
            let read_ms = start.elapsed().as_secs_f64() * 1000.0;
            let counts: Vec<_> = items.iter().map(|item| item.hits.len()).collect();
            let start = Instant::now();
            let out_path = output.join(format!("reference-{encoding}-{sample}.json"));
            // Never overwrite diagnostic or project files.
            let file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&out_path)
                .unwrap();
            let mut writer = BufWriter::new(file);
            let pack_ms;
            if encoding == "v1" {
                let result = compact_reference_track_members(items);
                pack_ms = start.elapsed().as_secs_f64() * 1000.0;
                serde_json::to_writer(&mut writer, &result).unwrap();
            } else {
                let result = pack_reference_track_members(items);
                pack_ms = start.elapsed().as_secs_f64() * 1000.0;
                serde_json::to_writer(&mut writer, &result).unwrap();
            }
            writer.flush().unwrap();
            drop(writer);
            let pack_and_write_ms = start.elapsed().as_secs_f64() * 1000.0;
            let bytes = fs::metadata(&out_path).unwrap().len();
            let row = json!({"sample":sample,"encoding":encoding,"readMs":read_ms,"packMs":pack_ms,
                "packAndWriteMs":pack_and_write_ms,"bytes":bytes,"hitCounts":counts});
            println!("reference_readonly {row}");
            samples.push(row);
        }
    }
    let primary: i64 = conn
        .query_row(
            "SELECT primary_dataset_id FROM project WHERE id=?1",
            [project_id],
            |r| r.get(0),
        )
        .unwrap();
    let support: Option<i64> = conn
        .query_row(
            "SELECT support_dataset_id FROM project_assembly_view_state WHERE project_id=?1",
            [project_id],
            |r| r.get(0),
        )
        .unwrap();
    for (label, dataset) in [("primary", Some(primary)), ("support", support)] {
        if let Some(dataset) = dataset {
            let items =
                list_chr_view_ctgs_with_connection(&conn, project_id, Some(&chr), Some(dataset))
                    .unwrap();
            let file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(output.join(format!("{label}.json")))
                .unwrap();
            serde_json::to_writer(BufWriter::new(file), &items).unwrap();
        }
    }
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output.join("backend-report.json"))
        .unwrap();
    serde_json::to_writer_pretty(file, &json!({"scope":"Windows Rust; one read-only connection/transaction; no IPC/UI",
        "projectId":project_id,"chrName":chr,"primaryDatasetId":primary,"supportDatasetId":support,"samples":samples})).unwrap();
    conn.execute_batch("ROLLBACK;").unwrap();
    let after = fs::metadata(&path).unwrap();
    assert_eq!(before.len(), after.len());
    assert_eq!(before.modified().unwrap(), after.modified().unwrap());
}
