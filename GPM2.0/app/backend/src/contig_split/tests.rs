use super::*;
use crate::main_view_history::*;
use serde_json::{Value, json};

fn seed() -> Result<(tempfile::TempDir, std::path::PathBuf)> {
    let dir = tempfile::tempdir()?;
    let db = dir.path().join("project.sqlite");
    let conn = Connection::open(&db)?;
    crate::db::init_workspace_schema(&conn)?;
    conn.execute_batch("INSERT INTO reference_genome(id,name,species_name,assembly_label,fasta_path,fai_path) VALUES(1,'ref','sp','v1','ref.fa','ref.fa.fai');
        INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'ChrA',1,200000),(2,1,'ChrB',2,200000);
        INSERT INTO dataset(id,name,assembler,fasta_path,fai_path) VALUES(1,'ds','asm','ds.fa','ds.fa.fai');
        INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(1,1,'tig',1,100000);
        INSERT INTO project(id,name,version,reference_genome_id,primary_dataset_id,created_at) VALUES(1,'p',1,1,1,'1');
        INSERT INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,1,'primary',1);
        INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,left_end_type,right_end_type,created_at) VALUES(1,1,1,'chr:1','-',1,100000,'telomere','normal','1');
        INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,placement_mode,created_at) VALUES(1,1,1,'tig@ChrA','ChrA',1,-39999,'auto','1');
        INSERT INTO ref_alignment_hit(dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,cg_tag,run_name)
        VALUES(1,1,1,'-',1,60000,1,60000,59900,60000,60,'60000M','test'),(1,1,2,'-',59901,100000,2001,42100,40000,40100,60,'40100M','test');")?;
    let paths = json!({"ChrA":{"chrName":"ChrA","mode":"segments","segments":[
        {"type":"ctg","segmentId":"baseline","assemblyCtgId":null,"source":{"dataset":"ds","contig":"tig","start":1,"end":100000,"orientation":"-"},"start":100000,"end":1,"overallLen":100000,"serverBaseline":true},
        {"type":"gap","segmentId":"gap","gapSizeBp":100}],"totalLength":100100},
        "ChrB":{"chrName":"ChrB","segments":[]}});
    conn.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,updated_at) VALUES(1,?1,'1')",[paths.to_string()])?;
    Ok((dir, db))
}
fn target() -> MainViewHistoryTargetParams {
    MainViewHistoryTargetParams {
        history_capacity: None,
        project_id: 1,
        chr_name: "ChrA".into(),
    }
}
fn preview(db: &Path, cuts: Vec<i64>) -> Result<SplitPreview> {
    preview_contig_split(
        db,
        1,
        &SplitPreviewParams {
            assembly_ctg_id: 1,
            cut_after: cuts,
        },
    )
}
fn commit(db: &Path, p: &SplitPreview) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "split-source-ctg".into(),
            args: json!({"assemblyCtgId":1,"cutAfter":p.cut_after,"assignments":["ChrA","ChrB"],"previewToken":p.preview_token,"reason":"recommended"}),
        },
    )
}
fn paths(db: &Path) -> Result<Value> {
    Ok(serde_json::from_str(
        &Connection::open(db)?.query_row::<String, _, _>(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=1",
            [],
            |r| r.get(0),
        )?,
    )?)
}

#[test]
fn read_only_preview_uses_fragment_denominators_and_overlap_alternatives() -> Result<()> {
    let (_dir, db) = seed()?;
    let before = std::fs::read(&db)?;
    let p = preview(&db, vec![60000])?;
    assert_eq!(std::fs::read(&db)?, before);
    assert_eq!(p.parts[1].candidates[0].chr_name, "ChrB");
    assert_eq!(p.parts[1].candidates[0].coverage_percent, 100.0);
    assert_eq!(p.parts[1].candidates[0].orient, "-");
    assert_eq!(p.parts[1].candidates[0].anchor_start, 2001);
    assert!(
        p.recommendations
            .iter()
            .any(|r| r.cut_after == vec![59900] && r.kind == "overlap")
    );
    assert!(
        p.recommendations
            .iter()
            .any(|r| r.cut_after == vec![60000] && r.kind == "overlap")
    );
    assert_eq!(p.final_path_reference_count, 1);
    Ok(())
}

#[test]
fn split_moves_only_fragments_and_undo_redo_restore_both_chromosomes() -> Result<()> {
    let (_dir, db) = seed()?;
    let original = paths(&db)?;
    let p = preview(&db, vec![60000])?;
    let result = commit(&db, &p)?;
    assert_eq!(result.affected_ctg_ids, vec![1, 2, 3]);
    let conn = Connection::open(&db)?;
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name='ChrB'",
            [],
            |r| r.get(0)
        )?,
        1
    );
    let fragment = crate::main_view::load_source_fragment(&conn, 3)?.unwrap();
    assert_eq!(
        (
            fragment.source_start,
            fragment.source_end,
            fragment.gap_before_bp
        ),
        (60001, 100000, 0)
    );
    assert_eq!(conn.query_row::<i64,_,_>("SELECT SUM(s.source_end-s.source_start+1) FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id",[],|r|r.get(0))?,100000);
    assert_eq!(
        conn.query_row::<String, _, _>(
            "SELECT left_end_type FROM assembly_seq WHERE id=3",
            [],
            |r| r.get(0)
        )?,
        "telomere"
    );
    assert_eq!(
        conn.query_row::<String, _, _>(
            "SELECT left_end_type FROM assembly_seq WHERE id=2",
            [],
            |r| r.get(0)
        )?,
        "normal"
    );
    let split_paths = paths(&db)?;
    assert_eq!(split_paths["ChrA"]["segments"][0]["start"], 100000);
    assert_eq!(split_paths["ChrA"]["segments"][0]["end"], 60001);
    assert_eq!(split_paths["ChrA"]["segments"][1]["start"], 60000);
    assert_eq!(split_paths["ChrA"]["segments"][1]["end"], 1);
    assert_eq!(split_paths["ChrB"], original["ChrB"]);
    assert_eq!(
        split_paths["ChrA"]["segments"][2],
        original["ChrA"]["segments"][1]
    );
    undo_main_view_history(&db, &target())?;
    assert_eq!(paths(&db)?, original);
    assert_eq!(
        conn.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg", [], |r| r.get(0))?,
        1
    );
    assert_eq!(
        conn.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_seq", [], |r| r.get(0))?,
        1
    );
    redo_main_view_history(&db, &target())?;
    assert_eq!(paths(&db)?, split_paths);
    reset_main_view_history(&db, &target())?;
    assert_eq!(paths(&db)?, original);
    undo_main_view_history(&db, &target())?;
    assert_eq!(paths(&db)?, split_paths);
    Ok(())
}

#[test]
fn rejects_stale_preview_and_invalid_assignments_without_partial_mutation() -> Result<()> {
    let (_dir, db) = seed()?;
    let p = preview(&db, vec![60000])?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE assembly_ctg SET name='changed' WHERE id=1", [])?;
    assert!(format!("{:#}", commit(&db, &p).unwrap_err()).contains("CTG_SPLIT_STALE_PREVIEW"));
    let p = preview(&db, vec![60000])?;
    let err=run_main_view_editor_action(&db,&RunMainViewEditorActionParams {history_capacity:None,project_id:1,chr_name:"ChrA".into(),action:"split-source-ctg".into(),args:json!({"assemblyCtgId":1,"cutAfter":p.cut_after,"assignments":["missing","ChrB"],"previewToken":p.preview_token,"reason":"manual"})}).unwrap_err();
    assert!(format!("{err:#}").contains("CTG_SPLIT_UNSUPPORTED_ASSIGNMENT"));
    assert_eq!(
        conn.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_seq", [], |r| r.get(0))?,
        1
    );
    for cuts in [vec![0], vec![100000], vec![60000, 60000]] {
        assert!(preview(&db, cuts).is_err());
    }
    Ok(())
}

#[test]
fn undo_does_not_overwrite_subsequent_edits_in_destination_chr() -> Result<()> {
    let (_dir, db) = seed()?;
    commit(&db, &preview(&db, vec![60000])?)?;
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrB".into(),
            action: "rename-ctg".into(),
            args: json!({"assemblyCtgId":3,"newName":"user-edit"}),
        },
    )?;
    let undo = undo_main_view_history(&db, &target())?;
    assert!(undo.invalidated && !undo.changed);
    assert_eq!(
        Connection::open(&db)?.query_row::<String, _, _>(
            "SELECT name FROM assembly_ctg WHERE id=3",
            [],
            |r| r.get(0)
        )?,
        "user-edit"
    );
    Ok(())
}

#[test]
fn duplicate_hits_do_not_inflate_coverage_or_recommend_same_chr_gaps() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE ref_alignment_hit SET reference_chr_id=1", [])?;
    conn.execute("INSERT INTO ref_alignment_hit(dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,cg_tag,run_name) SELECT dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,cg_tag,run_name FROM ref_alignment_hit",[])?;
    let p = preview(&db, vec![])?;
    assert_eq!(p.parts[0].candidates[0].coverage_percent, 100.0);
    assert!(p.recommendations.is_empty());
    conn.execute("UPDATE ref_alignment_hit SET mapq=0", [])?;
    assert!(preview(&db, vec![])?.recommendations.is_empty());
    Ok(())
}

#[test]
fn final_path_export_dna_is_identical_after_reverse_split() -> Result<()> {
    use crate::exporter::{
        ExportFinalPathFastaParams, FinalPathExportSegment, export_final_path_fasta,
    };
    let (dir, db) = seed()?;
    let dna = "AACCGT".repeat(16667)[..100000].to_string();
    let fasta = dir.path().join("ds.fa");
    let fai = dir.path().join("ds.fa.fai");
    std::fs::write(&fasta, format!(">tig\n{dna}\n"))?;
    std::fs::write(&fai, "tig\t100000\t5\t100000\t100001\n")?;
    Connection::open(&db)?.execute(
        "UPDATE dataset SET fasta_path=?1,fai_path=?2 WHERE id=1",
        params![fasta.to_string_lossy(), fai.to_string_lossy()],
    )?;
    Connection::open(&db)?.execute(
        "INSERT INTO source_seq_locator(source_seq_id,fasta_path) VALUES(1,?1)",
        [fasta.to_string_lossy()],
    )?;
    let before = dir.path().join("before.fa");
    let after = dir.path().join("after.fa");
    export_final_path_fasta(
        &db,
        1,
        &ExportFinalPathFastaParams {
            chr_name: "ChrA".into(),
            output_path: before.clone(),
            final_path_segments: vec![
                FinalPathExportSegment::Source {
                    dataset_name: "ds".into(),
                    contig_name: "tig".into(),
                    start: 100000,
                    end: 1,
                },
                FinalPathExportSegment::Gap { gap_size_bp: 100 },
            ],
        },
    )?;
    cut_manual(&db, 1, 60000, 1, 100000, "-")?;
    let paths = paths(&db)?;
    let segments = paths["ChrA"]["segments"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| {
            if s["type"] == "gap" {
                FinalPathExportSegment::Gap {
                    gap_size_bp: s["gapSizeBp"].as_i64().unwrap(),
                }
            } else {
                FinalPathExportSegment::Source {
                    dataset_name: "ds".into(),
                    contig_name: "tig".into(),
                    start: s["start"].as_i64().unwrap(),
                    end: s["end"].as_i64().unwrap(),
                }
            }
        })
        .collect();
    export_final_path_fasta(
        &db,
        1,
        &ExportFinalPathFastaParams {
            chr_name: "ChrA".into(),
            output_path: after.clone(),
            final_path_segments: segments,
        },
    )?;
    assert_eq!(std::fs::read(before)?, std::fs::read(after)?);
    Ok(())
}

#[test]
fn trimmed_ctg_path_conversion_is_source_relative_not_display_relative() -> Result<()> {
    let (_dir, db) = seed()?;
    let mut source = preview(&db, vec![])?.source;
    source.source_start = 101;
    source.source_end = 900;
    let mut paths = json!({"ChrA":{"segments":[{"type":"ctg","assemblyCtgId":1,"segmentId":"trimmed","start":700,"end":200}]}});
    rewrite_final_paths(&mut paths, &source, &[500], &[(2, 101, 500), (3, 501, 900)])?;
    assert_eq!(paths["ChrA"]["segments"][0]["start"], 800);
    assert_eq!(paths["ChrA"]["segments"][0]["end"], 501);
    assert_eq!(paths["ChrA"]["segments"][1]["start"], 500);
    assert_eq!(paths["ChrA"]["segments"][1]["end"], 300);
    Ok(())
}

#[test]
fn unaligned_transition_can_keep_middle_fragment_unplaced_and_preserve_phase_members() -> Result<()>
{
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE ref_alignment_hit SET query_start=70001,ref_end=32000,block_length=30000,match_length=29900,cg_tag='30000M' WHERE reference_chr_id=2",[])?;
    conn.execute_batch("INSERT INTO phased_chr_track(id,project_id,parent_chr_name,haplotype_key,label,display_order,created_at) VALUES(1,1,'ChrA','A','phase',1,'1');
      INSERT INTO phased_chr_track_item(id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at) VALUES(1,1,1,1,7,'-','1');")?;
    let p = preview(&db, vec![60000, 70000])?;
    assert!(
        p.recommendations
            .iter()
            .any(|r| r.cut_after == vec![60000, 70000] && r.kind == "unaligned")
    );
    assert!(p.parts[1].candidates.is_empty());
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "split-source-ctg".into(),
            args: json!({"assemblyCtgId":1,"cutAfter":p.cut_after,"assignments":["ChrA",null,"ChrB"],"previewToken":p.preview_token,"reason":"recommended"}),
        },
    )?;
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name IS NULL",
            [],
            |r| r.get(0)
        )?,
        1
    );
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT assembly_ctg_id FROM phased_chr_track_item",
            [],
            |r| r.get(0)
        )?,
        2
    );
    undo_main_view_history(&db, &target())?;
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT assembly_ctg_id FROM phased_chr_track_item",
            [],
            |r| r.get(0)
        )?,
        1
    );
    redo_main_view_history(&db, &target())?;
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT assembly_ctg_id FROM phased_chr_track_item",
            [],
            |r| r.get(0)
        )?,
        2
    );
    Ok(())
}

#[test]
fn frontend_json_key_order_does_not_invalidate_split_history() -> Result<()> {
    let (_dir, db) = seed()?;
    let original = paths(&db)?;
    commit(&db, &preview(&db, vec![60000])?)?;
    let conn = Connection::open(&db)?;
    let formatted = serde_json::to_string_pretty(&paths(&db)?)?;
    conn.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
        [formatted],
    )?;
    let result = undo_main_view_history(&db, &target())?;
    assert!(result.changed && !result.invalidated);
    assert_eq!(paths(&db)?, original);
    Ok(())
}

#[test]
fn chromosome_export_does_not_insert_gap_between_adjacent_manual_fragments() -> Result<()> {
    use crate::exporter::{ExportChrFastaParams, export_chr_fasta};
    let (dir, db) = seed()?;
    let fasta = dir.path().join("ds.fa");
    let dna = "AACCGT".repeat(16667)[..100000].to_string();
    std::fs::write(&fasta, format!(">tig\n{dna}\n"))?;
    let conn = Connection::open(&db)?;
    conn.execute(
        "INSERT INTO source_seq_locator(source_seq_id,fasta_path) VALUES(1,?1)",
        [fasta.to_string_lossy()],
    )?;
    conn.execute("UPDATE ref_alignment_hit SET reference_chr_id=1", [])?;
    let before = export_chr_fasta(
        &db,
        1,
        &ExportChrFastaParams {
            chr_name: Some("ChrA".into()),
        },
    )?;
    let original = std::fs::read(&before.output_path)?;
    let p = preview(&db, vec![60000])?;
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "split-source-ctg".into(),
            args: json!({"assemblyCtgId":1,"cutAfter":p.cut_after,"assignments":["ChrA","ChrA"],"previewToken":p.preview_token,"reason":"manual"}),
        },
    )?;
    // Place in original source order for an unchanged chromosome export.
    conn.execute(
        "UPDATE assembly_ctg SET chr_order=CASE id WHEN 3 THEN 1 ELSE 2 END",
        [],
    )?;
    let after = export_chr_fasta(
        &db,
        1,
        &ExportChrFastaParams {
            chr_name: Some("ChrA".into()),
        },
    )?;
    assert_eq!(std::fs::read(&after.output_path)?, original);
    Ok(())
}

fn cut_ref(
    db: &Path,
    ctg_id: i64,
    side: &str,
    cut: i64,
    min_length: i64,
    identity: f64,
) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "split-ref-boundary".into(),
            args: json!({"assemblyCtgId":ctg_id,"side":side,"cutAfter":cut,"minAlignmentLength":min_length,"minIdentityPct":identity}),
        },
    )
}

#[test]
fn ref_boundary_keeps_reverse_fragments_in_original_track_with_short_display_names() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE assembly_ctg SET ref_orient='-',chr_order=7", [])?;
    conn.execute(
        "UPDATE project_assembly_view_state SET track_drag_offsets_json=?1",
        [json!([
        {"trackRole":"primary","assemblyCtgId":1,"offsetBp":1234},
        {"trackRole":"primary","assemblyCtgId":99,"offsetBp":99}])
        .to_string()],
    )?;
    let before = paths(&db)?;
    cut_ref(&db, 1, "left", 60000, 10000, 0.0)?;
    let mut q=conn.prepare("SELECT c.name,c.assigned_chr_name,c.anchor_start,c.chr_order,c.ref_orient,s.orient,s.source_start,s.source_end FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id ORDER BY c.anchor_start")?;
    let parts = q
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, String>(4)?,
                r.get::<_, String>(5)?,
                r.get::<_, i64>(6)?,
                r.get::<_, i64>(7)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    assert_eq!(
        parts,
        vec![
            (
                "tig.1".into(),
                "ChrA".into(),
                -39999,
                7,
                "-".into(),
                "-".into(),
                60001,
                100000
            ),
            (
                "tig.2".into(),
                "ChrA".into(),
                1,
                7,
                "-".into(),
                "-".into(),
                1,
                60000
            )
        ]
    );
    let offsets: Value = serde_json::from_str(&conn.query_row::<String, _, _>(
        "SELECT track_drag_offsets_json FROM project_assembly_view_state",
        [],
        |r| r.get(0),
    )?)?;
    assert_eq!(offsets.as_array().unwrap().len(), 3);
    assert_eq!(
        offsets
            .as_array()
            .unwrap()
            .iter()
            .filter(|o| o["offsetBp"] == 1234)
            .count(),
        2
    );
    let items = crate::main_view::list_chr_view_ctgs_with_connection(&conn, 1, Some("ChrA"), None)?;
    assert_eq!(items.len(), 2);
    assert_eq!(items.iter().map(|i| i.total_length).sum::<i64>(), 100000);
    assert!(
        items
            .iter()
            .find(|i| i.name == "tig.1")
            .unwrap()
            .hits
            .is_empty(),
        "unaligned tail remains in current track"
    );
    assert_eq!(paths(&db)?["ChrB"], before["ChrB"]);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert_eq!(paths(&db)?, before);
    let restored: Value = serde_json::from_str(&conn.query_row::<String, _, _>(
        "SELECT track_drag_offsets_json FROM project_assembly_view_state",
        [],
        |r| r.get(0),
    )?)?;
    assert_eq!(restored.as_array().unwrap().len(), 2);
    assert!(redo_main_view_history(&db, &target())?.changed);
    Ok(())
}

#[test]
fn ref_boundary_uses_all_current_chr_hits_and_display_filters_not_an_individual_hit() -> Result<()>
{
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE assembly_seq SET orient='+'", [])?;
    conn.execute("INSERT INTO ref_alignment_hit(dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,cg_tag,run_name) VALUES(1,1,1,'+',70001,90000,100001,120000,19800,20000,60,'20000M','test')",[])?;
    assert!(
        cut_ref(&db, 1, "right", 60000, 10000, 0.0).is_err(),
        "not the envelope edge"
    );
    assert!(
        cut_ref(&db, 1, "right", 100000, 10000, 0.0).is_err(),
        "other chr hits do not extend envelope"
    );
    cut_ref(&db, 1, "right", 90000, 10000, 0.0)?;
    assert!(undo_main_view_history(&db, &target())?.changed);
    cut_ref(&db, 1, "right", 60000, 30000, 0.0)?;
    assert!(undo_main_view_history(&db, &target())?.changed);
    cut_ref(&db, 1, "right", 60000, 10000, 99.5)?;
    Ok(())
}

#[test]
fn ref_boundary_rejects_absent_terminal_and_stale_edges_without_partial_writes() -> Result<()> {
    let (_dir, db) = seed()?;
    let original = paths(&db)?;
    for (side, cut, length) in [
        ("right", 0, 1),
        ("left", 60000, 100000),
        ("left", 59900, 1),
        ("invalid", 60000, 1),
    ] {
        assert!(cut_ref(&db, 1, side, cut, length, 0.0).is_err());
    }
    assert_eq!(paths(&db)?, original);
    assert_eq!(
        Connection::open(&db)?.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg",
            [],
            |r| r.get(0)
        )?,
        1
    );
    Ok(())
}

#[test]
fn ref_boundary_without_saved_view_roundtrips_and_repeat_cut_preserves_sibling_identity()
-> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("DELETE FROM project_assembly_view_state", [])?;
    conn.execute("UPDATE ref_alignment_hit SET query_start=1001,ref_end=59000,block_length=59000,match_length=58900,cg_tag='59000M' WHERE reference_chr_id=1",[])?;
    cut_ref(&db, 1, "left", 60000, 10000, 0.0)?;
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert!(redo_main_view_history(&db, &target())?.changed);
    cut_ref(&db, 2, "right", 1000, 10000, 0.0)?;
    let groups = conn
        .prepare("SELECT instance_key FROM assembly_seq WHERE hidden=0")?
        .query_map([], |r| r.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    assert_eq!(groups.len(), 3);
    assert!(groups.iter().all(|g| g.starts_with("manual-fragment:1:")));
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert!(undo_main_view_history(&db, &target())?.changed);
    Ok(())
}

fn cut_manual(
    db: &Path,
    ctg_id: i64,
    cut: i64,
    start: i64,
    end: i64,
    orient: &str,
) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "split-manual-contig".into(),
            args: json!({"assemblyCtgId":ctg_id,"cutAfter":cut,"sourceStart":start,"sourceEnd":end,"orient":orient}),
        },
    )
}

#[test]
fn manual_cut_accepts_non_alignment_position_and_retains_track_orientation_placement_and_history()
-> Result<()> {
    let (_dir, db) = seed()?;
    let before = paths(&db)?;
    let result = cut_manual(&db, 1, 42424, 1, 100000, "-")?;
    assert_eq!(result.descriptor.unwrap().kind, "split-manual-contig");
    let conn = Connection::open(&db)?;
    let rows=conn.prepare("SELECT c.name,c.assigned_chr_name,c.anchor_start,s.source_start,s.source_end,s.orient FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id ORDER BY c.anchor_start")?
        .query_map([],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,i64>(2)?,r.get::<_,i64>(3)?,r.get::<_,i64>(4)?,r.get::<_,String>(5)?)))?.collect::<rusqlite::Result<Vec<_>>>()?;
    assert_eq!(
        rows,
        vec![
            (
                "tig.1".into(),
                "ChrA".into(),
                -39999,
                42425,
                100000,
                "-".into()
            ),
            ("tig.2".into(), "ChrA".into(), 17577, 1, 42424, "-".into())
        ]
    );
    assert_eq!(paths(&db)?["ChrB"], before["ChrB"]);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert_eq!(paths(&db)?, before);
    assert!(redo_main_view_history(&db, &target())?.changed);
    Ok(())
}

#[test]
fn manual_cut_without_reference_hits_and_repeated_fragment_coordinates_are_supported() -> Result<()>
{
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("DELETE FROM ref_alignment_hit", [])?;
    conn.execute("UPDATE assembly_seq SET orient='+'", [])?;
    cut_manual(&db, 1, 40000, 1, 100000, "+")?;
    cut_manual(&db, 3, 70000, 40001, 100000, "+")?;
    let count=conn.query_row::<i64,_,_>("SELECT SUM(s.source_end-s.source_start+1) FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id",[],|r|r.get(0))?;
    assert_eq!(count, 100000);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert!(undo_main_view_history(&db, &target())?.changed);
    Ok(())
}

#[test]
fn manual_cut_rejects_invalid_or_stale_source_without_creating_fragments() -> Result<()> {
    let (_dir, db) = seed()?;
    let before = paths(&db)?;
    for (cut, start, end, orient) in [
        (0, 1, 100000, "-"),
        (100000, 1, 100000, "-"),
        (50000, 2, 100000, "-"),
        (50000, 1, 99999, "-"),
        (50000, 1, 100000, "+"),
    ] {
        assert!(cut_manual(&db, 1, cut, start, end, orient).is_err());
    }
    let conn = Connection::open(&db)?;
    assert_eq!(
        conn.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg", [], |r| r.get(0))?,
        1
    );
    assert_eq!(paths(&db)?, before);
    Ok(())
}

fn unsplit_args(db: &Path, id: i64, neighbor: i64, side: &str) -> Result<Value> {
    let conn = Connection::open(db)?;
    let a = load_split_source(&conn, 1, id)?;
    let b = load_split_source(&conn, 1, neighbor)?;
    Ok(
        json!({"assemblyCtgId":id,"neighborCtgId":neighbor,"side":side,"sourceStart":a.source_start,"sourceEnd":a.source_end,
        "orient":a.orient,"neighborSourceStart":b.source_start,"neighborSourceEnd":b.source_end}),
    )
}
fn unsplit(db: &Path, args: Value) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "ChrA".into(),
            action: "undo-contig-split".into(),
            args,
        },
    )
}
fn active_intervals(db: &Path) -> Result<Vec<(i64, i64)>> {
    Ok(Connection::open(db)?.prepare("SELECT s.source_start,s.source_end FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id ORDER BY s.source_start")?
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?.collect::<rusqlite::Result<Vec<_>>>()?)
}

#[test]
fn unsplit_left_and_right_follow_display_orientation_and_roundtrip_history() -> Result<()> {
    for orient in ["+", "-"] {
        for side in ["left", "right"] {
            let (_dir, db) = seed()?;
            let conn = Connection::open(&db)?;
            conn.execute("UPDATE assembly_seq SET orient=?1", [orient])?;
            cut_manual(&db, 1, 30000, 1, 100000, orient)?;
            cut_manual(&db, 3, 70000, 30001, 100000, orient)?;
            // IDs: 2=[1,30000], 4=[30001,70000], 5=[70001,100000].
            let low_side = (side == "left") != (orient == "-");
            let other = if low_side { 2 } else { 5 };
            let before = paths(&db)?;
            let old_anchor: i64 = conn.query_row(
                "SELECT anchor_start FROM assembly_ctg WHERE id=4",
                [],
                |r| r.get(0),
            )?;
            let result = unsplit(&db, unsplit_args(&db, 4, other, side)?)?;
            assert_eq!(result.descriptor.unwrap().kind, "undo-contig-split");
            assert_eq!(
                active_intervals(&db)?,
                if low_side {
                    vec![(1, 70000), (70001, 100000)]
                } else {
                    vec![(1, 30000), (30001, 100000)]
                }
            );
            assert_eq!(
                conn.query_row::<i64, _, _>(
                    "SELECT anchor_start FROM assembly_ctg WHERE id=4",
                    [],
                    |r| r.get(0)
                )?,
                old_anchor - if side == "left" { 30000 } else { 0 }
            );
            assert_eq!(paths(&db)?["ChrB"], before["ChrB"]);
            let after = paths(&db)?;
            let mut before_dna = before.clone();
            let mut after_dna = after.clone();
            for value in [&mut before_dna, &mut after_dna] {
                for path in value.as_object_mut().unwrap().values_mut() {
                    for seg in path["segments"].as_array_mut().unwrap() {
                        seg.as_object_mut().unwrap().remove("splitFragmentCtgId");
                    }
                }
            }
            assert_eq!(
                before_dna, after_dna,
                "source intervals, strand, order and gaps stay unchanged"
            );
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert_eq!(
                active_intervals(&db)?,
                vec![(1, 30000), (30001, 70000), (70001, 100000)]
            );
            assert_eq!(paths(&db)?, before);
            assert!(redo_main_view_history(&db, &target())?.changed);
            assert_eq!(paths(&db)?, after);
            // Remove the remaining boundary; a full original interval remains.
            let remaining = if low_side { 5 } else { 2 };
            let other_side = if side == "left" { "right" } else { "left" };
            unsplit(&db, unsplit_args(&db, 4, remaining, other_side)?)?;
            assert_eq!(active_intervals(&db)?, vec![(1, 100000)]);
            // Splitting a restored interval again must not collide with retired keys.
            cut_manual(&db, 4, 30000, 1, 100000, orient)?;
            assert_eq!(active_intervals(&db)?, vec![(1, 30000), (30001, 100000)]);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert_eq!(active_intervals(&db)?, vec![(1, 100000)]);
        }
    }
    Ok(())
}

#[test]
fn unsplit_rejects_stale_wrong_side_nonadjacent_flipped_foreign_group_and_hidden_fragments_atomically()
-> Result<()> {
    for case in 0..8 {
        let (_dir, db) = seed()?;
        cut_manual(&db, 1, 30000, 1, 100000, "-")?;
        cut_manual(&db, 3, 70000, 30001, 100000, "-")?;
        let conn = Connection::open(&db)?;
        let mut args = unsplit_args(&db, 4, 5, "left")?;
        match case {
            0 => args["sourceStart"] = json!(30002),
            1 => args["neighborSourceEnd"] = json!(99999),
            2 => args["side"] = json!("right"),
            3 => {
                conn.execute("UPDATE assembly_seq SET source_start=70002 WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=5)", [])?;
                args = unsplit_args(&db, 4, 5, "left")?;
            }
            4 => {
                conn.execute("UPDATE assembly_seq SET orient='+' WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=5)", [])?;
            }
            5 => {
                conn.execute("UPDATE assembly_seq SET instance_key='manual-fragment:99:70001-100000' WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=5)", [])?;
            }
            6 => {
                conn.execute("UPDATE assembly_seq SET hidden=1 WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=5)", [])?;
            }
            _ => {
                conn.execute(
                    "UPDATE assembly_ctg SET assigned_chr_name='ChrB' WHERE id=5",
                    [],
                )?;
            }
        }
        let before = paths(&db)?;
        let intervals = active_intervals(&db)?;
        assert!(unsplit(&db, args).is_err(), "case {case}");
        assert_eq!(paths(&db)?, before);
        assert_eq!(active_intervals(&db)?, intervals);
    }
    Ok(())
}

#[test]
fn unsplit_preserves_adopted_partial_intervals_gaps_metadata_and_all_chromosomes() -> Result<()> {
    let (_dir, db) = seed()?;
    cut_manual(&db, 1, 40000, 1, 100000, "-")?;
    let conn = Connection::open(&db)?;
    let before = json!({"ChrA":{"segments":[
        {"type":"ctg","segmentId":"partial","assemblyCtgId":3,"start":20000,"end":2,"custom":"keep"},
        {"type":"gap","segmentId":"gap","gapSizeBp":99}],"totalLength":20098},
        "ChrB":{"segments":[{"type":"ctg","segmentId":"other","assemblyCtgId":2,"start":1,"end":10}]}});
    conn.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
        [before.to_string()],
    )?;
    unsplit(&db, unsplit_args(&db, 2, 3, "left")?)?;
    let after = paths(&db)?;
    assert_eq!(
        after["ChrA"]["segments"][0]["source"],
        json!({"dataset":"ds","contig":"tig","start":40002,"end":60000,"orientation":"-"})
    );
    assert_eq!(after["ChrA"]["segments"][0]["start"], 60000);
    assert_eq!(after["ChrA"]["segments"][0]["end"], 40002);
    assert_eq!(after["ChrA"]["segments"][0]["segmentId"], "partial");
    assert_eq!(after["ChrA"]["segments"][0]["custom"], "keep");
    assert_eq!(after["ChrA"]["segments"][1], before["ChrA"]["segments"][1]);
    assert_eq!(after["ChrA"]["totalLength"], before["ChrA"]["totalLength"]);
    assert_eq!(after["ChrB"]["segments"][0]["source"]["start"], 1);
    assert_eq!(after["ChrB"]["segments"][0]["source"]["end"], 10);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert_eq!(paths(&db)?, before);
    assert!(redo_main_view_history(&db, &target())?.changed);
    assert_eq!(paths(&db)?, after);
    Ok(())
}

#[test]
fn unsplit_preserves_exterior_end_types_offsets_and_unrelated_layout() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute(
        "UPDATE project_assembly_view_state SET track_drag_offsets_json=?1",
        [json!([
            {"trackRole":"primary","assemblyCtgId":1,"offsetBp":123},
            {"trackRole":"support","assemblyCtgId":99,"datasetId":2,"offsetBp":456}
        ])
        .to_string()],
    )?;
    cut_manual(&db, 1, 40000, 1, 100000, "-")?;
    let before_offsets: Value = serde_json::from_str(&conn.query_row::<String, _, _>(
        "SELECT track_drag_offsets_json FROM project_assembly_view_state",
        [],
        |r| r.get(0),
    )?)?;
    unsplit(&db, unsplit_args(&db, 2, 3, "left")?)?;
    let ends: (String,String) = conn.query_row("SELECT left_end_type,right_end_type FROM assembly_seq WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=2)",[],|r|Ok((r.get(0)?,r.get(1)?)))?;
    assert_eq!(ends, ("telomere".into(), "normal".into()));
    let offsets: Value = serde_json::from_str(&conn.query_row::<String, _, _>(
        "SELECT track_drag_offsets_json FROM project_assembly_view_state",
        [],
        |r| r.get(0),
    )?)?;
    assert_eq!(
        offsets,
        json!([
            {"trackRole":"support","assemblyCtgId":99,"datasetId":2,"offsetBp":456},
            {"trackRole":"primary","assemblyCtgId":2,"offsetBp":123}
        ])
    );
    assert!(undo_main_view_history(&db, &target())?.changed);
    let restored: Value = serde_json::from_str(&conn.query_row::<String, _, _>(
        "SELECT track_drag_offsets_json FROM project_assembly_view_state",
        [],
        |r| r.get(0),
    )?)?;
    assert_eq!(restored, before_offsets);
    Ok(())
}

#[test]
fn unsplit_without_saved_view_supports_undo_redo() -> Result<()> {
    let (_dir, db) = seed()?;
    Connection::open(&db)?.execute("DELETE FROM project_assembly_view_state", [])?;
    cut_manual(&db, 1, 40000, 1, 100000, "-")?;
    unsplit(&db, unsplit_args(&db, 2, 3, "left")?)?;
    assert_eq!(active_intervals(&db)?, vec![(1, 100000)]);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert_eq!(active_intervals(&db)?, vec![(1, 40000), (40001, 100000)]);
    assert!(redo_main_view_history(&db, &target())?.changed);
    assert_eq!(active_intervals(&db)?, vec![(1, 100000)]);
    assert_eq!(
        Connection::open(&db)?.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM project_assembly_view_state",
            [],
            |r| r.get(0)
        )?,
        0
    );
    Ok(())
}

#[test]
fn unsplit_coalesces_compatible_phased_pair_and_rejects_partial_or_job_dependencies() -> Result<()>
{
    for case in 0..4 {
        let (_dir, db) = seed()?;
        let conn = Connection::open(&db)?;
        cut_manual(&db, 1, 40000, 1, 100000, "-")?;
        conn.execute("INSERT INTO phased_chr_track(id,project_id,parent_chr_name,haplotype_key,label,display_order,created_at) VALUES(1,1,'ChrA','h1','hap1',1,'1')",[])?;
        conn.execute("INSERT INTO phased_chr_track_item(id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at) VALUES(1,1,3,1,5,'-','1')",[])?;
        if case != 1 {
            conn.execute("INSERT INTO phased_chr_track_item(id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at) VALUES(2,1,2,2,?1,'-','1')",[if case==2 {10} else {0}])?;
        }
        if case == 3 {
            conn.execute(
                "UPDATE project_assembly_view_state SET degap_project_state_json=?1",
                [json!({"jobs":[{"source":{"assemblyCtgId":3}}]}).to_string()],
            )?;
        }
        let before = paths(&db)?;
        let result = unsplit(&db, unsplit_args(&db, 2, 3, "left")?);
        if case == 0 {
            assert!(result?.changed);
            let items: Vec<(i64,i64)> = conn.prepare("SELECT assembly_ctg_id,gap_before_px FROM phased_chr_track_item ORDER BY display_order")?
                .query_map([],|r|Ok((r.get(0)?,r.get(1)?)))?.collect::<rusqlite::Result<_>>()?;
            assert_eq!(items, vec![(2, 5)]);
            assert!(undo_main_view_history(&db, &target())?.changed);
            assert_eq!(
                conn.query_row::<i64, _, _>(
                    "SELECT COUNT(*) FROM phased_chr_track_item",
                    [],
                    |r| r.get(0)
                )?,
                2
            );
            assert_eq!(paths(&db)?, before);
            assert!(redo_main_view_history(&db, &target())?.changed);
        } else {
            assert!(result.is_err(), "case {case}");
            assert_eq!(paths(&db)?, before);
            assert_eq!(active_intervals(&db)?, vec![(1, 40000), (40001, 100000)]);
        }
    }
    Ok(())
}

#[test]
fn unsplit_final_path_export_dna_is_unchanged_for_partial_reverse_adoptions() -> Result<()> {
    use crate::exporter::{
        ExportFinalPathFastaParams, FinalPathExportSegment, export_final_path_fasta,
    };
    let (dir, db) = seed()?;
    let dna = "AACCGT".repeat(16667)[..100000].to_string();
    let fasta = dir.path().join("ds.fa");
    std::fs::write(&fasta, format!(">tig\n{dna}\n"))?;
    Connection::open(&db)?.execute(
        "INSERT INTO source_seq_locator(source_seq_id,fasta_path) VALUES(1,?1)",
        [fasta.to_string_lossy()],
    )?;
    cut_manual(&db, 1, 40000, 1, 100000, "-")?;
    let adopted = json!({"ChrA":{"segments":[
        {"type":"ctg","segmentId":"partial","assemblyCtgId":3,"start":20000,"end":2},
        {"type":"gap","gapSizeBp":31},
        {"type":"ctg","segmentId":"retained","assemblyCtgId":2,"start":39999,"end":123}]}});
    Connection::open(&db)?.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
        [adopted.to_string()],
    )?;
    let export = |name: &str| -> Result<Vec<u8>> {
        let path = paths(&db)?;
        let segments = path["ChrA"]["segments"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| {
                if s["type"] == "gap" {
                    FinalPathExportSegment::Gap {
                        gap_size_bp: s["gapSizeBp"].as_i64().unwrap(),
                    }
                } else if s["source"].is_object() {
                    FinalPathExportSegment::Source {
                        dataset_name: "ds".into(),
                        contig_name: "tig".into(),
                        start: s["start"].as_i64().unwrap(),
                        end: s["end"].as_i64().unwrap(),
                    }
                } else {
                    FinalPathExportSegment::Ctg {
                        assembly_ctg_id: s["assemblyCtgId"].as_i64().unwrap(),
                        start: s["start"].as_i64().unwrap(),
                        end: s["end"].as_i64().unwrap(),
                    }
                }
            })
            .collect();
        let output = dir.path().join(name);
        export_final_path_fasta(
            &db,
            1,
            &ExportFinalPathFastaParams {
                chr_name: "ChrA".into(),
                output_path: output.clone(),
                final_path_segments: segments,
            },
        )?;
        Ok(std::fs::read(output)?)
    };
    let before = export("before-unsplit.fa")?;
    unsplit(&db, unsplit_args(&db, 2, 3, "left")?)?;
    assert_eq!(export("after-unsplit.fa")?, before);
    assert!(undo_main_view_history(&db, &target())?.changed);
    assert_eq!(export("undo-unsplit.fa")?, before);
    assert!(redo_main_view_history(&db, &target())?.changed);
    assert_eq!(export("redo-unsplit.fa")?, before);
    Ok(())
}

#[test]
fn unknown_mapq_preserves_hits_but_never_supplies_high_quality_or_recommendations() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute("UPDATE ref_alignment_hit SET mapq=255", [])?;
    drop(conn);
    let before = std::fs::read(&db)?;
    let p = preview(&db, vec![60000])?;
    assert_eq!(std::fs::read(&db)?, before);
    assert!(!p.hits.is_empty());
    assert!(p.hits.iter().all(|hit| hit.mapq == 255));
    assert!(p.recommendations.is_empty());
    for part in &p.parts {
        assert!(!part.candidates.is_empty());
        assert!(part.candidates.iter().all(|candidate| {
            candidate.coverage_bp > 0
                && candidate.high_quality_coverage_percent == 0.0
                && candidate.min_mapq == 255
        }));
    }
    let wire = serde_json::to_value(&p)?;
    assert_eq!(wire["hits"][0]["mapq"], 255);
    assert_eq!(wire["parts"][0]["candidates"][0]["minMapq"], 255);
    Ok(())
}

#[test]
fn mapq_threshold_accepts_known_values_not_the_missing_sentinel_or_invalid_values() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    for (mapq, high_quality) in [
        (-1, false),
        (0, false),
        (19, false),
        (20, true),
        (60, true),
        (254, true),
        (255, false),
        (256, false),
    ] {
        conn.execute("UPDATE ref_alignment_hit SET mapq=?1", [mapq])?;
        let p = preview(&db, vec![60000])?;
        assert_eq!(!p.recommendations.is_empty(), high_quality, "MAPQ {mapq}");
        assert_eq!(
            p.parts[1].candidates[0].high_quality_coverage_percent > 0.0,
            high_quality,
            "MAPQ {mapq}"
        );
        assert!(p.hits.iter().all(|hit| hit.mapq == mapq));
    }
    Ok(())
}

#[test]
fn missing_mapq_cannot_form_one_side_of_a_recommended_boundary() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    conn.execute(
        "UPDATE ref_alignment_hit SET mapq=255 WHERE reference_chr_id=1",
        [],
    )?;
    let p = preview(&db, vec![60000])?;
    assert!(p.recommendations.is_empty());
    assert!(p.parts[0].candidates.iter().any(|c| c.chr_name == "ChrA"
        && c.coverage_percent == 100.0
        && c.high_quality_coverage_percent == 0.0));
    assert!(
        p.parts[1]
            .candidates
            .iter()
            .any(|c| c.chr_name == "ChrB" && c.high_quality_coverage_percent == 100.0)
    );
    Ok(())
}

#[test]
fn missing_mapq_does_not_inflate_mixed_quality_coverage_or_outrank_known_support() -> Result<()> {
    let hit = |id, chr: &str, start, end, mapq| SplitHit {
        id,
        chr_name: chr.into(),
        strand: "+".into(),
        query_start: start,
        query_end: end,
        ref_start: start,
        ref_end: end,
        match_length: end - start + 1,
        block_length: end - start + 1,
        mapq,
        cigar: Some(format!("{}M", end - start + 1)),
    };
    let candidates = rank_candidates(
        &[hit(1, "unknown", 1, 100, 255), hit(2, "known", 1, 80, 20)],
        1,
        100,
    )?;
    assert_eq!(candidates[0].chr_name, "known");
    assert_eq!(candidates[0].high_quality_coverage_percent, 80.0);
    assert_eq!(candidates[1].coverage_percent, 100.0);
    assert_eq!(candidates[1].high_quality_coverage_percent, 0.0);
    let mixed = rank_candidates(
        &[hit(1, "ChrA", 1, 60, 255), hit(2, "ChrA", 41, 100, 60)],
        1,
        100,
    )?;
    assert_eq!(mixed[0].coverage_bp, 100);
    assert_eq!(mixed[0].high_quality_coverage_percent, 60.0);
    assert_eq!(mixed[0].min_mapq, 60);
    Ok(())
}
