//! Explicit read-only benchmark; never invoked by default test discovery.
use super::*;
use rusqlite::OpenFlags;
use std::{
    fs::{self, OpenOptions},
    path::PathBuf,
    time::Instant,
};

#[test]
#[ignore = "set GPM_GEOMETRY_READONLY_DB and GPM_GEOMETRY_PROFILE_OUTPUT"]
fn profile_geometry_and_bulk_sources_readonly() {
    let path =
        PathBuf::from(std::env::var("GPM_GEOMETRY_READONLY_DB").expect("read-only database"));
    let output =
        PathBuf::from(std::env::var("GPM_GEOMETRY_PROFILE_OUTPUT").expect("private report path"));
    assert!(
        !output
            .parent()
            .unwrap()
            .canonicalize()
            .unwrap()
            .starts_with(path.parent().unwrap().canonicalize().unwrap())
    );
    let before = fs::metadata(&path).unwrap();
    let conn = Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    conn.execute_batch("PRAGMA query_only=ON; BEGIN;").unwrap();
    let mut reference_samples = Vec::new();
    for chr in ["chr1", "chr7"] {
        for sample in 0..3 {
            let start = Instant::now();
            let geometry = list_reference_track_geometry_with_connection(&conn, 1, chr).unwrap();
            let geometry_ms = start.elapsed().as_secs_f64() * 1000.0;
            let wire = reference_transport::reference_track_geometry(geometry.clone());
            let bytes = serde_json::to_vec(&wire).unwrap().len();
            let start = Instant::now();
            let full = list_reference_track_members_with_connection(&conn, 1, chr).unwrap();
            let full_ms = start.elapsed().as_secs_f64() * 1000.0;
            let hits: usize = full.iter().map(|member| member.hits.len()).sum();
            let expected = full
                .into_iter()
                .map(|mut member| {
                    member.hits.clear();
                    member
                })
                .collect::<Vec<_>>();
            assert_eq!(geometry, expected);
            reference_samples.push(serde_json::json!({"chr":chr,"sample":sample,"geometryMs":geometry_ms,"fullMs":full_ms,"fullRows":hits,"geometryBytes":bytes,"members":geometry.len(),"metadataIdentical":true}));
        }
    }
    let start = Instant::now();
    let original = list_chr_view_ctgs_with_connection_options(&conn, 1, None, None, false).unwrap();
    let summary_ms = start.elapsed().as_secs_f64() * 1000.0;
    let mut source_samples = Vec::new();
    for sample in 0..3 {
        let start = Instant::now();
        for ctg in &original {
            assert_eq!(
                ctg.source_fragment,
                load_source_fragment(&conn, ctg.assembly_ctg_id).unwrap()
            );
        }
        let scalar_ms = start.elapsed().as_secs_f64() * 1000.0;
        let mut copy = original.clone();
        let start = Instant::now();
        source_fragment_bulk::populate_source_fragments(&conn, 1, &mut copy).unwrap();
        let batch_ms = start.elapsed().as_secs_f64() * 1000.0;
        assert_eq!(copy, original);
        source_samples.push(serde_json::json!({"sample":sample,"scalarMs":scalar_ms,"batchMs":batch_ms,"allFieldsIdentical":true}));
    }
    conn.execute_batch("ROLLBACK;").unwrap();
    let after = fs::metadata(&path).unwrap();
    assert_eq!(before.len(), after.len());
    assert_eq!(before.modified().unwrap(), after.modified().unwrap());
    let report = serde_json::json!({"scope":"Rust read-only query/CPU, excludes IPC, WebView and cold-cache guarantee", "readonly":true,"databaseUnchanged":true,"reference":reference_samples,"sourceFragments":source_samples,"projectCtgs":original.len(),"summaryMs":summary_ms});
    serde_json::to_writer_pretty(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)
            .unwrap(),
        &report,
    )
    .unwrap();
    println!("{report}");
}
