use super::*;
use crate::db::init_workspace_schema;
use crate::main_view_history::{
    MainViewHistoryTargetParams, RunMainViewEditorActionParams, get_main_view_history_status,
    redo_main_view_history, run_main_view_editor_action, undo_main_view_history,
};
use tempfile::{TempDir, tempdir};
fn seed() -> Result<(TempDir, std::path::PathBuf)> {
    let dir = tempdir()?;
    let db = dir.path().join("project.sqlite");
    let c = Connection::open(&db)?;
    init_workspace_schema(&c)?;
    c.execute_batch("INSERT INTO reference_genome(id,name,species_name,assembly_label,fasta_path,fai_path) VALUES(1,'ref','sp','v1','r.fa','r.fai');
        INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'A',1,200000),(2,1,'B',2,200000),(3,1,'C',3,200000);
        INSERT INTO dataset(id,name,assembler,fasta_path,fai_path) VALUES(1,'ds','asm','ds.fa','ds.fai'),(2,'other','asm','o.fa','o.fai');
        INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(1,1,'tig',1,100000),(2,2,'tig',1,100000);
        INSERT INTO project(id,name,version,reference_genome_id,primary_dataset_id,created_at) VALUES(1,'p',1,1,1,'1');
        INSERT INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,1,'primary',1);
        INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,left_end_type,right_end_type,created_at) VALUES(1,1,1,'manual-fragment:seed:1','-',40001,100000,'telomere','normal','1');
        INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,placement_mode,created_at) VALUES(1,1,1,'tig.1','A',1,-39999,'manual','1');
        INSERT INTO ref_alignment_hit(dataset_id,source_seq_id,reference_chr_id,strand,query_start,query_end,ref_start,ref_end,match_length,block_length,mapq,cg_tag,run_name) VALUES
        (1,1,2,'+',30001,100000,1001,71000,70000,70000,60,'70000M','test'),
        (1,1,2,'+',60001,80000,31001,51000,20000,20000,60,'20000M','test'),
        (1,1,3,'+',1,10000,1,10000,10000,10000,60,'10000M','test');
        INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,hidden_primary_ctg_ids_json,hidden_primary_ctg_ids_by_chr_json,updated_at) VALUES(1,'{\"A\":{\"segments\":[]},\"B\":{\"segments\":[]}}','[99]','{\"C\":[99]}','1');")?;
    Ok((dir, db))
}
fn request() -> ChrAlignmentParams {
    ChrAlignmentParams {
        assembly_ctg_id: 1,
        min_alignment_length: 10000,
        min_identity_pct: 90.0,
    }
}
fn view(c: &Connection) -> Result<String> {
    Ok(c.query_row(
        "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=1",
        [],
        |r| r.get(0),
    )?)
}
fn add(
    db: &Path,
    overlap: bool,
) -> Result<crate::main_view_history::MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "A".into(),
            action: "add-contig-to-chr".into(),
            history_capacity: None,
            args: json!({"assemblyCtgId":1,"sourceSeqId":1,"sourceStart":40001,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0,"allowOverlap":overlap}),
        },
    )
}
fn history() -> MainViewHistoryTargetParams {
    MainViewHistoryTargetParams {
        project_id: 1,
        chr_name: "B".into(),
        history_capacity: None,
    }
}
fn existing(c: &Connection, source: i64, a: i64, b: i64, hidden: bool) -> Result<()> {
    c.execute("INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,hidden,created_at) VALUES(2,1,?1,'other-instance','-',?2,?3,?4,'1')",params![source,a,b,hidden])?;
    c.execute("INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,anchor_start,placement_mode,created_at) VALUES(2,1,2,'renamed','B',77,'manual','1')",[])?;
    Ok(())
}
#[test]
fn preview_is_read_only_clips_current_fragment_unions_coverage_and_respects_filters() -> Result<()>
{
    let (_dir, db) = seed()?;
    let before = std::fs::read(&db)?;
    let p = get_contig_chr_alignments(&db, 1, &request())?;
    assert_eq!(std::fs::read(&db)?, before);
    assert_eq!(p.items.len(), 1);
    let b = &p.items[0];
    assert_eq!(b.candidate.chr_name, "B");
    assert_eq!(b.candidate.coverage_bp, 60000);
    assert_eq!(b.candidate.coverage_percent, 100.0);
    assert_eq!(b.hits[0].query_start, 40001);
    assert_eq!(b.hits[0].ref_start, 11001);
    assert_eq!(b.presence, "missing");
    let mut r = request();
    r.min_alignment_length = 100000;
    assert!(get_contig_chr_alignments(&db, 1, &r)?.items.is_empty());
    r.min_identity_pct = 101.0;
    assert!(get_contig_chr_alignments(&db, 1, &r).is_err());
    Ok(())
}
#[test]
fn add_is_idempotent_preserves_source_final_path_and_undo_redo() -> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    let paths = view(&c)?;
    let first = add(&db, false)?;
    assert!(first.changed);
    let id = first.affected_ctg_ids[0];
    assert_ne!(id, 1);
    let row=c.query_row("SELECT s.source_start,s.source_end,s.orient,c.anchor_start,c.placement_mode,s.left_end_type,s.right_end_type FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.id=?1",[id],|r|Ok((r.get::<_,i64>(0)?,r.get::<_,i64>(1)?,r.get::<_,String>(2)?,r.get::<_,i64>(3)?,r.get::<_,String>(4)?,r.get::<_,String>(5)?,r.get::<_,String>(6)?)))?;
    assert_eq!(
        row,
        (
            40001,
            100000,
            "+".into(),
            11001,
            "manual".into(),
            "normal".into(),
            "telomere".into()
        )
    );
    let fragment = crate::main_view::load_source_fragment(&c, id)?.unwrap();
    assert_eq!(fragment.source_start, 40001);
    assert_ne!(
        fragment.group_key,
        crate::main_view::load_source_fragment(&c, 1)?
            .unwrap()
            .group_key
    );
    assert!(!add(&db, false)?.changed);
    assert_eq!(view(&c)?, paths);
    assert_eq!(
        c.query_row::<i64, _, _>(
            "SELECT anchor_start FROM assembly_ctg WHERE id=1",
            [],
            |r| r.get(0)
        )?,
        -39999
    );
    assert!(undo_main_view_history(&db, &history())?.changed);
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg", [], |r| r.get(0))?,
        1
    );
    assert!(redo_main_view_history(&db, &history())?.changed);
    assert_eq!(view(&c)?, paths);
    Ok(())
}
#[test]
fn exact_identity_ignores_name_and_orientation_but_not_dataset() -> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 40001, 100000, false)?;
    let p = get_contig_chr_alignments(&db, 1, &request())?;
    assert_eq!(p.items[0].presence, "existing");
    assert_eq!(p.items[0].existing_ctg_id, Some(2));
    assert!(!add(&db, false)?.changed);
    c.execute("UPDATE assembly_seq SET source_seq_id=2 WHERE id=2", [])?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "missing"
    );
    assert!(add(&db, false)?.changed);
    Ok(())
}
#[test]
fn hidden_exact_is_restored_in_place_and_visibility_roundtrips_without_clobbering_other_chr()
-> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 40001, 100000, true)?;
    set_hidden_flags(&c, 1, "B", 2, true, true, false)?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "hidden"
    );
    let result = add(&db, false)?;
    assert_eq!(result.affected_ctg_ids, vec![2]);
    assert_eq!(hidden_flags(&c, 1, "B", 2)?, (false, false, false));
    set_hidden_flags(&c, 1, "C", 98, true, true, false)?;
    undo_main_view_history(&db, &history())?;
    assert_eq!(hidden_flags(&c, 1, "B", 2)?, (true, true, false));
    assert_eq!(hidden_flags(&c, 1, "C", 98)?, (true, true, false));
    redo_main_view_history(&db, &history())?;
    assert_eq!(hidden_flags(&c, 1, "B", 2)?, (false, false, false));
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT hidden FROM assembly_seq WHERE id=2", [], |r| r
            .get(0))?,
        0
    );
    Ok(())
}
#[test]
fn containing_and_partial_overlap_are_not_silently_duplicated() -> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 1, 100000, false)?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "contained"
    );
    assert!(add(&db, true).is_err());
    c.execute("UPDATE assembly_seq SET source_end=50000 WHERE id=2", [])?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "overlap"
    );
    assert!(add(&db, false).is_err());
    assert!(add(&db, true)?.changed);
    Ok(())
}
#[test]
fn disjoint_source_intervals_do_not_block_add_and_stale_or_unsupported_requests_do_not_write()
-> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 1, 40000, false)?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "missing"
    );
    let base = json!({"assemblyCtgId":1,"sourceSeqId":1,"sourceStart":40001,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0});
    for (key, value) in [
        ("sourceStart", json!(1)),
        ("sourceSeqId", json!(2)),
        ("orient", json!("+")),
        ("targetChrName", json!("C")),
        ("targetChrName", json!("A")),
        ("minIdentityPct", json!(101.0)),
    ] {
        let mut args = base.clone();
        args[key] = value;
        assert!(
            run_main_view_editor_action(
                &db,
                &RunMainViewEditorActionParams {
                    project_id: 1,
                    chr_name: "A".into(),
                    action: "add-contig-to-chr".into(),
                    history_capacity: None,
                    args
                }
            )
            .is_err()
        );
    }
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg", [], |r| r.get(0))?,
        2
    );
    assert!(add(&db, false)?.changed);
    Ok(())
}

#[test]
fn legacy_final_path_visibility_is_revealed_without_changing_segments_and_roundtrips() -> Result<()>
{
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 40001, 100000, false)?;
    c.execute("UPDATE project_assembly_view_state SET final_path_by_chr_json=?1 WHERE project_id=1",[json!({"A":{"segments":[]},"B":{"segments":[{"type":"gap","gapSizeBp":17}],"hiddenPrimaryCtgIds":[2,88]}}).to_string()])?;
    assert_eq!(
        get_contig_chr_alignments(&db, 1, &request())?.items[0].presence,
        "hidden"
    );
    add(&db, false)?;
    let paths: Value = serde_json::from_str(&view(&c)?)?;
    assert_eq!(paths["B"]["hiddenPrimaryCtgIds"], json!([88]));
    assert_eq!(
        paths["B"]["segments"],
        json!([{"type":"gap","gapSizeBp":17}])
    );
    undo_main_view_history(&db, &history())?;
    assert_eq!(hidden_flags(&c, 1, "B", 2)?, (false, false, true));
    redo_main_view_history(&db, &history())?;
    assert_eq!(hidden_flags(&c, 1, "B", 2)?, (false, false, false));
    Ok(())
}
#[test]
fn hidden_containing_instance_can_be_revealed_but_never_replaced_with_a_duplicate() -> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    existing(&c, 1, 1, 100000, true)?;
    let p = get_contig_chr_alignments(&db, 1, &request())?;
    assert_eq!(p.items[0].presence, "contained");
    assert!(p.items[0].existing_hidden);
    let args = json!({"assemblyCtgId":1,"sourceSeqId":1,"sourceStart":40001,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0,"revealContained":true});
    let result = run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "A".into(),
            history_capacity: None,
            action: "add-contig-to-chr".into(),
            args,
        },
    )?;
    assert_eq!(result.affected_ctg_ids, vec![2]);
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg", [], |r| r.get(0))?,
        2
    );
    assert_eq!(
        c.query_row::<i64, _, _>(
            "SELECT source_start FROM assembly_seq WHERE id=2",
            [],
            |r| r.get(0)
        )?,
        1
    );
    undo_main_view_history(&db, &history())?;
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT hidden FROM assembly_seq WHERE id=2", [], |r| r
            .get(0))?,
        1
    );
    Ok(())
}
#[test]
fn undo_does_not_delete_a_target_that_was_edited_or_adopted_after_add() -> Result<()> {
    for final_path_change in [false, true] {
        let (_dir, db) = seed()?;
        let c = Connection::open(&db)?;
        let added = add(&db, false)?;
        let id = added.affected_ctg_ids[0];
        if final_path_change {
            c.execute("UPDATE project_assembly_view_state SET final_path_by_chr_json=?1 WHERE project_id=1",[json!({"B":{"segments":[{"assemblyCtgId":id,"type":"ctg"}]}}).to_string()])?;
        } else {
            c.execute(
                "UPDATE assembly_ctg SET name='target-user-edit' WHERE id=?1",
                [id],
            )?;
        }
        let result = undo_main_view_history(&db, &history())?;
        assert!(!result.changed);
        assert!(result.invalidated);
        assert_eq!(
            c.query_row::<i64, _, _>("SELECT COUNT(*) FROM assembly_ctg WHERE id=?1", [id], |r| r
                .get(0))?,
            1
        );
    }
    Ok(())
}

#[test]
fn filters_use_clipped_visible_block_lengths_not_the_full_source_alignment_length() -> Result<()> {
    let (_dir, db) = seed()?;
    let c = Connection::open(&db)?;
    c.execute("UPDATE assembly_seq SET source_start=99991 WHERE id=1", [])?;
    assert!(
        get_contig_chr_alignments(&db, 1, &request())?
            .items
            .is_empty()
    );
    c.execute("UPDATE assembly_seq SET source_start=40001 WHERE id=1", [])?;
    c.execute(
        "INSERT INTO source_seq_n_region(source_seq_id,start_bp,end_bp,length_bp) VALUES(1,50001,90000,40000)",
        [],
    )?;
    let mut r = request();
    r.min_alignment_length = 20000;
    assert!(get_contig_chr_alignments(&db, 1, &r)?.items.is_empty());
    Ok(())
}

#[test]
fn uncached_legacy_reference_fasta_is_read_without_attempting_cache_writes() -> Result<()> {
    let (dir, db) = seed()?;
    let c = Connection::open(&db)?;
    let fasta = dir.path().join("ref.fa");
    let sequence = format!(
        "{}{}{}",
        "A".repeat(20000),
        "N".repeat(10000),
        "A".repeat(170000)
    );
    std::fs::write(&fasta, format!(">B\n{sequence}\n"))?;
    c.execute(
        "UPDATE reference_genome SET fasta_path=?1 WHERE id=1",
        [fasta.to_string_lossy().as_ref()],
    )?;
    let before = std::fs::read(&db)?;
    let preview = get_contig_chr_alignments(&db, 1, &request())?;
    assert_eq!(std::fs::read(&db)?, before);
    assert!(preview.items[0].candidate.coverage_bp < 60000);
    assert_eq!(
        c.query_row::<i64, _, _>("SELECT COUNT(*) FROM reference_chr_segment", [], |r| r
            .get(0))?,
        0
    );
    Ok(())
}

#[test]
fn additions_belong_only_to_destination_history_and_keep_source_steps_independent() -> Result<()> {
    let (_dir, db) = seed()?;
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "A".into(),
            history_capacity: None,
            action: "split-manual-contig".into(),
            args: json!({"assemblyCtgId":1,"sourceStart":40001,"sourceEnd":100000,"orient":"-","cutAfter":70000}),
        },
    )?;
    let source_history = MainViewHistoryTargetParams {
        chr_name: "A".into(),
        ..history()
    };
    let before = get_main_view_history_status(&db, &source_history)?;
    let result = run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "A".into(),
            history_capacity: None,
            action: "add-contig-to-chr".into(),
            args: json!({"assemblyCtgId":3,"sourceSeqId":1,"sourceStart":70001,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0}),
        },
    )?;
    assert_eq!(result.status.chr_name, "B");
    assert_eq!(result.status.applied_operation_count, 1);
    assert_eq!(get_main_view_history_status(&db, &source_history)?, before);
    assert!(undo_main_view_history(&db, &source_history)?.changed);
    let conn = Connection::open(&db)?;
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name='B'",
            [],
            |r| r.get(0)
        )?,
        1
    );
    assert!(undo_main_view_history(&db, &history())?.changed);
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name='B'",
            [],
            |r| r.get(0)
        )?,
        0
    );
    assert!(redo_main_view_history(&db, &history())?.changed);
    assert!(redo_main_view_history(&db, &source_history)?.changed);
    Ok(())
}

#[test]
fn destination_add_history_ignores_unrelated_paths_but_protects_adoption_on_any_chr() -> Result<()>
{
    for adopted in [false, true] {
        let (_dir, db) = seed()?;
        let result = add(&db, false)?;
        let id = result.affected_ctg_ids[0];
        let conn = Connection::open(&db)?;
        let segment = if adopted {
            json!({"type":"ctg","assemblyCtgId":id})
        } else {
            json!({"type":"gap","gapSizeBp":17})
        };
        conn.execute(
            "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
            [json!({"A":{"segments":[segment]},"B":{"segments":[]}}).to_string()],
        )?;
        let before = view(&conn)?;
        let undo = undo_main_view_history(&db, &history())?;
        assert_eq!(undo.changed, !adopted);
        assert_eq!(undo.invalidated, adopted);
        assert_eq!(
            view(&conn)?,
            before,
            "never overwrite the source chromosome's path"
        );
    }
    Ok(())
}

#[test]
fn full_contigs_and_auxiliary_dataset_sources_support_cross_chr_inspection_and_addition()
-> Result<()> {
    for auxiliary in [false, true] {
        let (_dir, db) = seed()?;
        let conn = Connection::open(&db)?;
        conn.execute("UPDATE assembly_seq SET instance_key='chr:1',source_start=1,source_end=100000,source_seq_id=?1 WHERE id=1",[if auxiliary {2} else {1}])?;
        if auxiliary {
            conn.execute(
                "UPDATE ref_alignment_hit SET source_seq_id=2,dataset_id=2",
                [],
            )?;
        }
        assert!(crate::main_view::load_source_fragment(&conn, 1)?.is_none());
        let preview = get_contig_chr_alignments(&db, 1, &request())?;
        assert_eq!(preview.source.source_start, 1);
        assert_eq!(preview.source.source_end, 100000);
        assert!(preview.items.iter().any(|i| i.candidate.chr_name == "B"));
        let result = run_main_view_editor_action(
            &db,
            &RunMainViewEditorActionParams {
                project_id: 1,
                chr_name: "A".into(),
                history_capacity: None,
                action: "add-contig-to-chr".into(),
                args: json!({"assemblyCtgId":1,"sourceSeqId":if auxiliary {2} else {1},"sourceStart":1,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0}),
            },
        )?;
        let id = result.affected_ctg_ids[0];
        let source:(i64,i64,i64)=conn.query_row("SELECT s.source_seq_id,s.source_start,s.source_end FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.id=?1",[id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?)))?;
        assert_eq!(source, (if auxiliary { 2 } else { 1 }, 1, 100000));
        assert_eq!(result.status.chr_name, "B");
        assert!(undo_main_view_history(&db, &history())?.changed);
        assert!(redo_main_view_history(&db, &history())?.changed);
        if auxiliary {
            assert!(
                crate::contig_split::load_split_source(&conn, 1, 1).is_err(),
                "split remains primary-only"
            );
        }
    }
    Ok(())
}

#[test]
fn unplaced_and_mirrored_sources_validate_actual_source_chr_but_record_destination_history()
-> Result<()> {
    for unplaced in [false, true] {
        let (_dir, db) = seed()?;
        let conn = Connection::open(&db)?;
        if unplaced {
            conn.execute(
                "UPDATE assembly_ctg SET assigned_chr_name=NULL WHERE id=1",
                [],
            )?;
        }
        let source_chr = if unplaced { "unplaced" } else { "A" };
        let result = run_main_view_editor_action(
            &db,
            &RunMainViewEditorActionParams {
                project_id: 1,
                chr_name: if unplaced { "unplaced" } else { "C" }.into(),
                history_capacity: None,
                action: "add-contig-to-chr".into(),
                args: json!({"assemblyCtgId":1,"sourceSeqId":1,"sourceChrName":source_chr,"sourceStart":40001,"sourceEnd":100000,"orient":"-","targetChrName":"B","minAlignmentLength":10000,"minIdentityPct":90.0}),
            },
        )?;
        assert_eq!(result.status.chr_name, "B");
        assert!(undo_main_view_history(&db, &history())?.changed);
    }
    Ok(())
}

#[test]
fn destination_add_history_protects_new_degap_jobs_without_owning_source_jobs() -> Result<()> {
    for target_job in [false, true] {
        let (_dir, db) = seed()?;
        let result = add(&db, false)?;
        let conn = Connection::open(&db)?;
        let id = if target_job {
            result.affected_ctg_ids[0]
        } else {
            1
        };
        let state = json!({"jobs":[{"source":{"assemblyCtgId":id}}]}).to_string();
        conn.execute(
            "UPDATE project_assembly_view_state SET degap_project_state_json=?1",
            [&state],
        )?;
        let undo = undo_main_view_history(&db, &history())?;
        assert_eq!(undo.changed, !target_job);
        assert_eq!(undo.invalidated, target_job);
        assert_eq!(
            conn.query_row::<String, _, _>(
                "SELECT degap_project_state_json FROM project_assembly_view_state",
                [],
                |r| r.get(0)
            )?,
            state
        );
    }
    Ok(())
}

#[test]
fn adding_preserves_source_redo_and_appends_to_existing_destination_steps() -> Result<()> {
    let (_dir, db) = seed()?;
    let conn = Connection::open(&db)?;
    existing(&conn, 1, 1, 10000, false)?;
    let edit = |chr: &str, id: i64, name: &str| {
        run_main_view_editor_action(
            &db,
            &RunMainViewEditorActionParams {
                project_id: 1,
                chr_name: chr.into(),
                history_capacity: None,
                action: "rename-ctg".into(),
                args: json!({"assemblyCtgId":id,"newName":name}),
            },
        )
    };
    edit("A", 1, "source-renamed")?;
    let source_history = MainViewHistoryTargetParams {
        chr_name: "A".into(),
        ..history()
    };
    assert!(undo_main_view_history(&db, &source_history)?.changed);
    let source_before = get_main_view_history_status(&db, &source_history)?;
    assert!(source_before.can_redo);
    edit("B", 2, "destination-renamed")?;
    let added = add(&db, false)?;
    assert_eq!(added.status.applied_operation_count, 2);
    assert_eq!(
        get_main_view_history_status(&db, &source_history)?,
        source_before
    );
    assert!(undo_main_view_history(&db, &history())?.changed);
    assert_eq!(
        conn.query_row::<String, _, _>("SELECT name FROM assembly_ctg WHERE id=2", [], |r| r
            .get(0))?,
        "destination-renamed"
    );
    assert!(undo_main_view_history(&db, &history())?.changed);
    assert_eq!(
        conn.query_row::<String, _, _>("SELECT name FROM assembly_ctg WHERE id=2", [], |r| r
            .get(0))?,
        "renamed"
    );
    assert!(redo_main_view_history(&db, &history())?.changed);
    assert!(redo_main_view_history(&db, &history())?.changed);
    assert!(redo_main_view_history(&db, &source_history)?.changed);
    assert!(crate::main_view_history::reset_main_view_history(&db, &history())?.changed);
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name='B'",
            [],
            |r| r.get(0)
        )?,
        1
    );
    assert_eq!(
        conn.query_row::<String, _, _>("SELECT name FROM assembly_ctg WHERE id=1", [], |r| r
            .get(0))?,
        "source-renamed"
    );
    assert!(undo_main_view_history(&db, &history())?.changed);
    assert_eq!(
        conn.query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM assembly_ctg WHERE assigned_chr_name='B'",
            [],
            |r| r.get(0)
        )?,
        2
    );
    Ok(())
}
