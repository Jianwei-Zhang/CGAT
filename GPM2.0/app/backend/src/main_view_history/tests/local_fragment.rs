use super::*;

fn edit(db: &std::path::Path, args: serde_json::Value) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_editor_action(
        db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".into(),
            action: "edit-local-fragment".into(),
            args,
        },
    )
}
fn request(
    action: &str,
    start: i64,
    end: i64,
    cut: Option<i64>,
    id: i64,
    length: i64,
    orient: &str,
) -> serde_json::Value {
    json!({"action":action,"sourceStart":start,"sourceEnd":end,"cutAfter":cut,
        "targets":[{"assemblyCtgId":id,"sourceStart":1,"sourceEnd":length,"orient":orient}]})
}
fn intervals(db: &std::path::Path, source_id: i64) -> Result<Vec<(i64, i64, i64)>> {
    let conn = Connection::open(db)?;
    let mut stmt = conn.prepare("SELECT c.id,s.source_start,s.source_end FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.assigned_chr_name='Chr01' AND s.source_seq_id=?1 ORDER BY s.source_start")?;
    Ok(stmt
        .query_map([source_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))?
        .collect::<rusqlite::Result<_>>()?)
}

#[test]
fn partial_deletion_is_one_atomic_split_and_delete_with_undo_redo() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let result = edit(&db, request("delete", 201, 600, None, 301, 1000, "+"))?;
    assert!(result.changed);
    assert_eq!(result.status.applied_operation_count, 1);
    assert_eq!(result.descriptor.unwrap().kind, "delete-local-fragment");
    let after = intervals(&db, 101)?;
    assert_eq!(
        after.iter().map(|(_, a, b)| (*a, *b)).collect::<Vec<_>>(),
        vec![(1, 200), (601, 1000)]
    );
    let conn = Connection::open(&db)?;
    let deleted: (i64,i64)=conn.query_row("SELECT s.source_start,s.source_end FROM deleted_assembly_ctg d JOIN assembly_seq s ON s.id=d.assembly_seq_id WHERE d.project_id=1",[],|r|Ok((r.get(0)?,r.get(1)?)))?;
    assert_eq!(deleted, (201, 600));
    let cards = crate::ctg_editor::list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?;
    assert_eq!(cards.len(), 1);
    assert_eq!(cards[0].source_seq_id, Some(101));
    assert_eq!(cards[0].source_start, Some(201));
    assert_eq!(cards[0].source_end, Some(600));
    assert_eq!(cards[0].total_length, 400);
    assert_eq!(
        count(&conn, "assembly_ctg", "id=303")?,
        1,
        "other source instance remains untouched"
    );
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 101)?, vec![(301, 1, 1000)]);
    assert_eq!(count(&conn, "deleted_assembly_ctg", "project_id=1")?, 0);
    assert!(redo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 101)?, after);
    assert_eq!(count(&conn, "deleted_assembly_ctg", "project_id=1")?, 1);
    Ok(())
}

#[test]
fn synchronized_split_isolates_clicked_range_and_preserves_reverse_placement() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let result = edit(&db, request("split", 201, 600, Some(400), 302, 900, "-"))?;
    assert!(result.changed);
    let after = intervals(&db, 102)?;
    assert_eq!(
        after.iter().map(|(_, a, b)| (*a, *b)).collect::<Vec<_>>(),
        vec![(1, 200), (201, 400), (401, 600), (601, 900)]
    );
    let conn = Connection::open(&db)?;
    for (id, _, end) in &after {
        let (orient,anchor):(String,i64)=conn.query_row("SELECT s.orient,c.anchor_start FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.id=?1",[id],|r|Ok((r.get(0)?,r.get(1)?)))?;
        assert_eq!(orient, "-");
        assert_eq!(anchor, 200 + 900 - end);
    }
    assert_eq!(count(&conn, "deleted_assembly_ctg", "project_id=1")?, 0);
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 102)?, vec![(302, 1, 900)]);
    assert!(redo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 102)?, after);
    Ok(())
}

#[test]
fn local_join_can_synchronize_a_new_cut_across_multiple_real_siblings_in_one_entry() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    edit(&db, request("split", 1, 1000, Some(400), 301, 1000, "+"))?;
    let before = intervals(&db, 101)?;
    let targets: Vec<_> = before
        .iter()
        .map(|(id, a, b)| json!({"assemblyCtgId":id,"sourceStart":a,"sourceEnd":b,"orient":"+"}))
        .collect();
    let result = edit(
        &db,
        json!({"action":"split","sourceStart":201,"sourceEnd":800,"cutAfter":600,"targets":targets}),
    )?;
    assert_eq!(result.status.applied_operation_count, 2);
    assert_eq!(result.descriptor.unwrap().target_count, 2);
    let after = intervals(&db, 101)?;
    assert_eq!(
        after.iter().map(|(_, a, b)| (*a, *b)).collect::<Vec<_>>(),
        vec![(1, 200), (201, 400), (401, 600), (601, 800), (801, 1000)]
    );
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 101)?, before);
    assert!(redo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 101)?, after);
    Ok(())
}

#[test]
fn rejects_stale_sources_duplicates_cross_chr_auxiliary_and_missing_bases_without_partial_writes()
-> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let valid = request("delete", 201, 600, None, 301, 1000, "+");
    let mut duplicate = valid.clone();
    let first = duplicate["targets"][0].clone();
    duplicate["targets"].as_array_mut().unwrap().push(first);
    let mut stale = valid.clone();
    stale["targets"][0]["sourceEnd"] = json!(999);
    for bad in [
        duplicate,
        stale,
        request("delete", 1, 100, None, 303, 1000, "+"),
        request("delete", 1, 100, None, 305, 800, "-"),
        request("delete", 1, 1001, None, 301, 1000, "+"),
        request("split", 200, 600, Some(600), 301, 1000, "+"),
    ] {
        assert!(edit(&db, bad).is_err());
        assert_eq!(intervals(&db, 101)?, vec![(301, 1, 1000)]);
        assert_eq!(
            get_main_view_history_status(&db, &target("Chr01"))?.applied_operation_count,
            0
        );
        assert_eq!(
            count(
                &Connection::open(&db)?,
                "deleted_assembly_ctg",
                "project_id=1"
            )?,
            0
        );
    }
    Ok(())
}

#[test]
fn immutable_path_sources_and_deleted_lineage_round_trip_with_the_same_history_entry() -> Result<()>
{
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let conn = Connection::open(&db)?;
    let paths = json!({"Chr01":{"mode":"segments","segments":[{"type":"ctg","segmentId":"a","assemblyCtgId":301,"start":1,"end":1000,"overallLen":1000}]},"Chr02":{"segments":[{"type":"ctg","segmentId":"b","assemblyCtgId":303,"start":1,"end":1000}]}});
    conn.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,degap_project_state_json,track_drag_offsets_json,updated_at) VALUES(1,?1,?2,?3,'1')",params![paths.to_string(),json!({"jobs":[{"assemblyCtgId":301}]}).to_string(),json!([{"trackRole":"primary","assemblyCtgId":301,"offsetBp":42}]).to_string()])?;
    let read = || -> Result<serde_json::Value> {
        let raw: String = conn.query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=1",
            [],
            |r| r.get(0),
        )?;
        Ok(serde_json::from_str(&raw)?)
    };
    edit(&db, request("delete", 201, 600, None, 301, 1000, "+"))?;
    let after = read()?;
    assert_eq!(after["Chr02"], paths["Chr02"]);
    let segments = after["Chr01"]["segments"].as_array().unwrap();
    assert_eq!(segments.len(), 3);
    assert!(segments[1]["assemblyCtgId"].is_null());
    assert_eq!(segments[1]["source"]["start"], 201);
    assert_eq!(segments[1]["source"]["end"], 600);
    let deleted_id: i64 = conn.query_row(
        "SELECT assembly_ctg_id FROM deleted_assembly_ctg WHERE project_id=1",
        [],
        |row| row.get(0),
    )?;
    assert_eq!(segments[1]["splitFragmentCtgId"], deleted_id);
    assert_eq!(segments[1]["start"], 201);
    assert_eq!(segments[1]["end"], 600);
    let offsets = load_track_offsets(&db)?;
    assert_eq!(offsets.len(), 2);
    assert!(offsets.iter().all(|entry| entry["offsetBp"] == 42));
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(read()?, paths);
    assert!(redo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(read()?, after);
    Ok(())
}

#[test]
fn a_dependency_failure_after_an_earlier_partition_rolls_back_the_entire_batch() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    edit(&db, request("split", 1, 1000, Some(400), 301, 1000, "+"))?;
    let before = intervals(&db, 101)?;
    let invalid_path =
        json!({"Chr01":{"segments":[{"type":"ctg","assemblyCtgId":before[1].0,"start":1}]}});
    Connection::open(&db)?.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,updated_at) VALUES(1,?1,'1') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json", [invalid_path.to_string()])?;
    let targets: Vec<_> = before
        .iter()
        .map(|(id, a, b)| json!({"assemblyCtgId":id,"sourceStart":a,"sourceEnd":b,"orient":"+"}))
        .collect();
    let error = edit(
        &db,
        json!({"action":"delete","sourceStart":201,"sourceEnd":800,"targets":targets}),
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("CTG_SPLIT_INVALID_PATH"));
    assert_eq!(intervals(&db, 101)?, before);
    assert_eq!(
        count(
            &Connection::open(&db)?,
            "deleted_assembly_ctg",
            "project_id=1"
        )?,
        0
    );
    Ok(())
}

#[test]
fn main_flip_after_split_and_partial_deletion_never_flips_or_deletes_a_surviving_sibling()
-> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    edit(&db, request("split", 1, 1000, Some(400), 301, 1000, "+"))?;
    let parts = intervals(&db, 101)?;
    let left = parts[0].0;
    let right = parts[1].0;
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".into(),
            action: "flip-ctg".into(),
            args: json!({"assemblyCtgId":left}),
        },
    )?;
    let orientation = |id| -> Result<String> {
        Ok(Connection::open(&db)?.query_row(
        "SELECT s.orient FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id WHERE c.id=?1", [id], |row|row.get(0))?)
    };
    assert_eq!(orientation(left)?, "-");
    assert_eq!(orientation(right)?, "+");
    edit(
        &db,
        json!({"action":"delete","sourceStart":101,"sourceEnd":200,
        "targets":[{"assemblyCtgId":left,"sourceStart":1,"sourceEnd":400,"orient":"-"}]}),
    )?;
    assert_eq!(orientation(right)?, "+");
    assert_eq!(
        intervals(&db, 101)?
            .iter()
            .map(|(_, a, b)| (*a, *b))
            .collect::<Vec<_>>(),
        vec![(1, 100), (201, 400), (401, 1000)]
    );
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(orientation(left)?, "-");
    assert_eq!(orientation(right)?, "+");
    Ok(())
}

#[test]
fn unsplit_restores_deleted_neighbor_atomically_and_is_itself_undoable() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    edit(&db, request("delete", 201, 600, None, 301, 1000, "+"))?;
    let after_delete = intervals(&db, 101)?;
    let deleted = crate::ctg_editor::list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?.remove(0);
    assert!(
        deleted
            .source_instance_key
            .as_deref()
            .unwrap()
            .starts_with("manual-fragment:")
    );
    let args = json!({"assemblyCtgId":after_delete[0].0,"neighborCtgId":deleted.assembly_ctg_id,
        "neighborDeletedRecordId":deleted.deleted_ctg_record_id,"side":"right","sourceStart":1,"sourceEnd":200,
        "neighborSourceStart":201,"neighborSourceEnd":600,"orient":"+"});
    let run = |args| {
        run_main_view_editor_action(
            &db,
            &RunMainViewEditorActionParams {
                history_capacity: None,
                project_id: 1,
                chr_name: "Chr01".into(),
                action: "undo-contig-split".into(),
                args,
            },
        )
    };
    let mut stale = args.clone();
    stale["neighborSourceEnd"] = json!(601);
    assert!(run(stale).is_err());
    assert_eq!(
        intervals(&db, 101)?,
        after_delete,
        "failed restore must roll back atomically"
    );
    assert_eq!(
        crate::ctg_editor::list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?.len(),
        1
    );
    let restored = run(args)?;
    assert_eq!(restored.status.applied_operation_count, 2);
    assert_eq!(
        intervals(&db, 101)?
            .iter()
            .map(|(_, a, b)| (*a, *b))
            .collect::<Vec<_>>(),
        vec![(1, 600), (601, 1000)]
    );
    assert!(crate::ctg_editor::list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?.is_empty());
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(intervals(&db, 101)?, after_delete);
    assert_eq!(
        crate::ctg_editor::list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?.len(),
        1
    );
    let conn = Connection::open(&db)?;
    let (history, _) = load_history_state(&conn, 1, 1)?;
    let expected = &history.future.last().unwrap().before;
    let actual = super::super::snapshot::capture_snapshot(
        &conn,
        1,
        &super::super::snapshot::snapshot_scope(expected),
    )?;
    let expected_json = serde_json::to_value(expected)?;
    let actual_json = serde_json::to_value(actual)?;
    for (key, value) in expected_json.as_object().unwrap() {
        assert_eq!(value, &actual_json[key], "after undo field: {key}");
    }
    let redo = redo_main_view_history(&db, &target("Chr01"))?;
    if !redo.changed {
        let conn = Connection::open(&db)?;
        let reason: String = conn.query_row("SELECT detail FROM edit_audit_log WHERE action='history-invalidated' ORDER BY id DESC LIMIT 1", [], |row| row.get(0))?;
        panic!("{reason}");
    }
    assert_eq!(
        intervals(&db, 101)?
            .iter()
            .map(|(_, a, b)| (*a, *b))
            .collect::<Vec<_>>(),
        vec![(1, 600), (601, 1000)]
    );
    Ok(())
}
