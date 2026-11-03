use super::*;
use crate::db::init_workspace_schema;
use crate::main_view::list_chr_view_ctgs_with_connection;
use crate::phased_assembly::list_phased_chr_tracks_with_connection;

fn fixture() -> Connection {
    let conn = Connection::open_in_memory().unwrap();
    init_workspace_schema(&conn).unwrap();
    conn.execute_batch("
        INSERT INTO reference_genome (id,name,species_name,assembly_label,fasta_path,fai_path)
          VALUES (1,'ref','test','ref','missing.fa','missing.fa.fai');
        INSERT INTO reference_chr (id,reference_genome_id,chr_name,chr_order,length)
          VALUES (1,1,'chr1',1,1000),(2,1,'chr2',2,2000);
        INSERT INTO reference_chr_segment (reference_chr_id,segment_order,start_bp,end_bp)
          VALUES (1,0,1,1000),(2,0,1,2000);
        INSERT INTO dataset (id,name,assembler,fasta_path,fai_path)
          VALUES (1,'primary','test','p.fa','p.fa.fai'),(2,'support','test','s.fa','s.fa.fai');
        INSERT INTO project (id,name,version,reference_genome_id,primary_dataset_id,phased_assembly_enabled,created_at)
          VALUES (1,'one',1,1,1,1,'1'),(2,'two',1,1,2,0,'1');
        INSERT INTO source_seq (id,dataset_id,seq_name,seq_order,length)
          VALUES (1,1,'origin1',1,100),(2,1,'unplaced',2,200),(3,2,'support',1,300),
                 (4,2,'derived',2,400),(5,2,'hidden-derived',3,500),(6,1,'fragment-origin',3,800);
        INSERT INTO assembly_seq (id,project_id,source_seq_id,instance_key,orient,source_start,source_end,hidden,created_at)
          VALUES (1,1,1,'','+',1,100,0,'1'),(2,1,2,'','+',1,200,0,'1'),
                 (3,1,3,'','-',1,300,0,'1'),(4,1,4,'','+',1,400,0,'1'),
                 (5,1,5,'','+',1,500,1,'1'),(6,1,6,'manual-fragment:edit:1','-',101,400,0,'1'),
                 (7,1,1,'chr:chr2','+',1,100,0,'1'),(21,2,3,'','+',1,300,0,'1');
        INSERT INTO assembly_ctg (id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at)
          VALUES (1,1,1,'ctg1','chr1',1,100,'+','auto','1'),(2,1,2,'ctg2',NULL,NULL,NULL,NULL,'none','1'),
                 (3,1,3,'support','chr1',3,300,'-','auto','1'),(4,1,4,'derived','chr1',2,200,'+','auto','1'),
                 (5,1,5,'hidden','chr1',4,400,'+','auto','1'),(6,1,6,'fragment','chr2',2,-200,'-','manual','1'),
                 (7,1,7,'coassigned','chr2',1,100,'+','auto','1'),(21,2,21,'other-project','chr1',1,1,'+','auto','1');
        INSERT INTO source_seq_n_region (source_seq_id,start_bp,end_bp,length_bp)
          VALUES (6,91,100,10),(6,401,410,10);
        INSERT INTO derived_ctg (source_seq_id,source,created_at) VALUES (4,'manual','1'),(5,'manual','1');
        INSERT INTO derived_ctg_track_member (project_id,source_seq_id,target_dataset_id,target_chr_name,created_at)
          VALUES (1,4,1,'chr1','1'),(1,5,1,'chr1','1');
        INSERT INTO ref_alignment_hit (dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,run_name)
          VALUES (1,1,1,'+',1,100,100,199,100,100,60,'r');
        INSERT INTO phased_chr_track (id,project_id,parent_chr_name,haplotype_key,label,display_order,created_at)
          VALUES (1,1,'chr1','a','chr1a',1,'1'),(2,1,'chr1','b','chr1b',2,'1'),(3,1,'chr2','a','chr2a',1,'1');
        INSERT INTO phased_chr_track_item (id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at)
          VALUES (1,1,1,1,20,'-','1');
    ").unwrap();
    conn
}

fn summary_payload(mut value: Value) -> Value {
    for key in [
        "originSourceSeqId",
        "hits",
        "nRegions",
        "telomereMarks",
        "centromereMarks",
    ] {
        value.as_object_mut().unwrap().remove(key);
    }
    value
}

#[test]
fn overview_matches_existing_chr_and_primary_views_without_evidence() {
    let conn = fixture();
    let result = get_project_overview_sources_with_connection(&conn, 1).unwrap();
    assert_eq!(result["unplacedCtgCount"], 1);
    assert_eq!(result["unplacedBp"], 200);
    assert_eq!(result["chromosomes"].as_array().unwrap().len(), 2);
    let primary = result["primaryCtgIds"].as_array().unwrap();
    for chr in ["chr1", "chr2"] {
        let actual = result["ctgs"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|ctg| ctg["assignedChrName"] == chr)
            .cloned()
            .collect::<Vec<_>>();
        let old = list_chr_view_ctgs_with_connection(&conn, 1, Some(chr), None).unwrap();
        let expected = old
            .into_iter()
            .map(|ctg| summary_payload(serde_json::to_value(ctg).unwrap()))
            .collect::<Vec<_>>();
        assert_eq!(actual, expected);
        let actual_primary = actual
            .iter()
            .filter(|ctg| primary.contains(&ctg["assemblyCtgId"]))
            .map(|ctg| ctg["assemblyCtgId"].as_i64().unwrap())
            .collect::<Vec<_>>();
        let expected_primary = list_chr_view_ctgs_with_connection(&conn, 1, Some(chr), Some(1))
            .unwrap()
            .iter()
            .map(|ctg| ctg.assembly_ctg_id)
            .collect::<Vec<_>>();
        assert_eq!(actual_primary, expected_primary);
    }
    assert!(
        primary.contains(&json!(4)),
        "derived source targeted to primary is a member"
    );
    assert!(
        !primary.contains(&json!(5)),
        "hidden derived source must not become a primary member"
    );
    let ctgs = result["ctgs"].as_array().unwrap();
    assert!(ctgs.iter().all(|ctg| ctg["assemblyCtgId"] != 21));
    let fragment = ctgs.iter().find(|ctg| ctg["assemblyCtgId"] == 6).unwrap();
    assert_eq!(fragment["anchorStart"], -200);
    assert_eq!(fragment["orient"], "-");
    assert_eq!(fragment["sourceFragment"]["sourceStart"], 101);
    assert_eq!(fragment["sourceFragment"]["gapBeforeBp"], 10);
    assert_eq!(fragment["sourceFragment"]["gapAfterBp"], 10);
    assert_eq!(
        ctgs.iter().find(|ctg| ctg["assemblyCtgId"] == 1).unwrap()["coAssignedChrNames"],
        json!(["chr2"])
    );
    for chr in ["chr1", "chr2"] {
        let old = list_phased_chr_tracks_with_connection(&conn, 1, chr).unwrap();
        let tracks = result["phasedChrTracksByChr"][chr].as_array().unwrap();
        assert_eq!(tracks.len(), old.tracks.len());
        for (track, expected) in tracks.iter().zip(old.tracks) {
            assert_eq!(track["phasedTrackId"], expected.id);
            assert_eq!(track["label"], expected.label);
            assert_eq!(
                track["items"].as_array().unwrap().len(),
                expected.items.len()
            );
        }
    }
    assert_eq!(
        result["phasedChrTracksByChr"]["chr1"][0]["items"][0]["orient"],
        "-"
    );
}

#[test]
fn overview_is_read_only_and_does_not_require_alignment_or_end_mark_tables() {
    let conn = fixture();
    conn.execute_batch(
        "DROP TABLE ref_alignment_hit; DROP TABLE source_seq_telomere_mark;
        DROP TABLE source_seq_centromere_mark; DROP TABLE pairwise_alignment_hit;
        PRAGMA query_only=ON;",
    )
    .unwrap();
    let before: i64 = conn
        .query_row("SELECT total_changes()", [], |row| row.get(0))
        .unwrap();
    let result = get_project_overview_sources_with_connection(&conn, 1).unwrap();
    assert_eq!(result["ctgs"].as_array().unwrap().len(), 6);
    assert_eq!(
        before,
        conn.query_row::<i64, _, _>("SELECT total_changes()", [], |row| row.get(0))
            .unwrap()
    );
    for ctg in result["ctgs"].as_array().unwrap() {
        for key in ["hits", "nRegions", "telomereMarks", "centromereMarks"] {
            assert!(ctg.get(key).is_none(), "unexpected evidence field {key}");
        }
    }
}

#[test]
fn overview_handles_empty_disabled_and_unknown_projects() {
    let conn = fixture();
    conn.execute("DELETE FROM phased_chr_track_item", [])
        .unwrap();
    conn.execute("DELETE FROM phased_chr_track", []).unwrap();
    let empty_tracks = get_project_overview_sources_with_connection(&conn, 1).unwrap();
    assert_eq!(empty_tracks["phasedChrTracksByChr"], json!({}));
    let other = get_project_overview_sources_with_connection(&conn, 2).unwrap();
    assert_eq!(other["primaryCtgIds"], json!([21]));
    assert_eq!(other["phasedChrTracksByChr"], json!({}));
    conn.execute("DELETE FROM assembly_ctg WHERE project_id=2", [])
        .unwrap();
    let empty = get_project_overview_sources_with_connection(&conn, 2).unwrap();
    assert_eq!(empty["ctgs"], json!([]));
    assert_eq!(empty["primaryCtgIds"], json!([]));
    assert!(get_project_overview_sources_with_connection(&conn, 999).is_err());
}

// Optional real-data validation: never opens the supplied project for writing.
#[test]
#[ignore = "set GPM_OVERVIEW_READONLY_DB to an imported project.sqlite"]
fn profile_real_project_overview_readonly() {
    use rusqlite::OpenFlags;
    use std::time::Instant;
    let path = std::env::var("GPM_OVERVIEW_READONLY_DB").expect("set read-only database path");
    let before = std::fs::metadata(&path).unwrap();
    let conn = Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    conn.execute_batch("PRAGMA query_only=ON").unwrap();
    let tx = conn.unchecked_transaction().unwrap();
    let project_id = 1;
    let primary: i64 = tx
        .query_row(
            "SELECT primary_dataset_id FROM project WHERE id=?1",
            [project_id],
            |row| row.get(0),
        )
        .unwrap();
    let mut samples = Vec::new();
    let mut sources = Value::Null;
    for _ in 0..5 {
        let start = Instant::now();
        sources = get_project_overview_sources_with_connection(&tx, project_id).unwrap();
        samples.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    let ids = sources["primaryCtgIds"].as_array().unwrap();
    let mut old_payload_bytes = 0;
    let mut legacy_read_ms = 0.0;
    for chromosome in sources["chromosomes"].as_array().unwrap() {
        let chr = chromosome["chrName"].as_str().unwrap();
        let mut old_all = Vec::new();
        let mut old_primary = Vec::new();
        for dataset in [None, Some(primary)] {
            let start = Instant::now();
            let old_ctgs =
                list_chr_view_ctgs_with_connection(&tx, project_id, Some(chr), dataset).unwrap();
            legacy_read_ms += start.elapsed().as_secs_f64() * 1000.0;
            // Serialization and equality checking are outside the legacy read timer.
            for ctg in old_ctgs {
                let mut value = serde_json::to_value(&ctg).unwrap();
                value.as_object_mut().unwrap().remove("originSourceSeqId");
                old_payload_bytes += serde_json::to_vec(&value).unwrap().len();
                if dataset.is_none() {
                    old_all.push(summary_payload(value));
                } else {
                    old_primary.push(json!(ctg.assembly_ctg_id));
                }
            }
        }
        let actual = sources["ctgs"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|ctg| ctg["assignedChrName"] == chr)
            .cloned()
            .collect::<Vec<_>>();
        assert_eq!(actual, old_all, "summary provenance/order changed");
        let actual_primary = actual
            .iter()
            .filter(|ctg| ids.contains(&ctg["assemblyCtgId"]))
            .map(|ctg| ctg["assemblyCtgId"].clone())
            .collect::<Vec<_>>();
        assert_eq!(actual_primary, old_primary, "primary membership changed");
    }
    println!(
        "overview_readonly samples_ms={samples:?} legacy_full_ctg_reads_ms={legacy_read_ms:.3} compact_response_bytes={} legacy_ctg_payload_bytes={} chromosomes={} assigned_ctgs={} all_chromosome_summaries_equal=true",
        serde_json::to_vec(&sources).unwrap().len(),
        old_payload_bytes,
        sources["chromosomes"].as_array().unwrap().len(),
        sources["ctgs"].as_array().unwrap().len()
    );
    tx.commit().unwrap();
    let after = std::fs::metadata(&path).unwrap();
    assert_eq!(before.len(), after.len());
    assert_eq!(before.modified().unwrap(), after.modified().unwrap());
}

#[test]
fn project_wide_overview_does_not_bind_every_source_id() {
    let conn = fixture();
    // More than bundled SQLite's default 32,766 bind variables. The old
    // project-wide coassignment query failed before any summary was returned.
    conn.execute_batch("
        WITH RECURSIVE ids(id) AS (SELECT 1000 UNION ALL SELECT id+1 FROM ids WHERE id<35999)
        INSERT INTO source_seq (id,dataset_id,seq_name,seq_order,length)
          SELECT id,2,'large-'||id,id,100 FROM ids;
        INSERT INTO assembly_seq (id,project_id,source_seq_id,orient,source_start,source_end,created_at)
          SELECT id,1,id,'+',1,100,'1' FROM source_seq WHERE id>=1000;
        INSERT INTO assembly_ctg (id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at)
          SELECT id,1,id,'large-'||id,'chr1',id,id,'+','auto','1' FROM source_seq WHERE id>=1000;
        PRAGMA query_only=ON;
    ").unwrap();
    let result = get_project_overview_sources_with_connection(&conn, 1).unwrap();
    assert_eq!(result["ctgs"].as_array().unwrap().len(), 35006);
    assert_eq!(result["ctgs"][0]["coAssignedChrNames"], json!(["chr2"]));
}
