use super::*;
use crate::ctg_editor::list_deleted_ctgs;

#[test]
fn support_member_delete_restore_and_history_preserve_sources_and_reference_safety() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let conn = Connection::open(&db)?;
    let final_path = json!({"Chr01":{"segments":[{"assemblyCtgId":305}]}}).to_string();
    conn.execute("INSERT INTO project_assembly_view_state (project_id, final_path_by_chr_json, updated_at) VALUES (1, ?1, '1')", [&final_path])?;
    conn.execute("INSERT INTO export_record (id, project_id, export_type, assembly_ctg_id, output_path, created_at) VALUES (601,1,'ctg_fasta',305,'out.fa','1')", [])?;
    drop(conn);
    let request = RunMainViewBatchDeleteParams {
        history_capacity: None,
        project_id: 1,
        chr_name: "Chr01".into(),
        assembly_ctg_ids: vec![305],
    };
    let impact = inspect_main_view_delete(&db, &request)?;
    assert_eq!(impact.final_path_reference_count, 1);
    assert_eq!(impact.export_record_count, 1);
    assert!(run_main_view_batch_delete(&db, &request)?.status.can_undo);
    assert!(list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?.is_empty());
    let deleted = list_deleted_ctgs(&db, 1, Some("Chr01"), Some(2))?;
    assert_eq!(deleted.len(), 1);
    assert_eq!(deleted[0].assembly_ctg_id, 305);
    assert_eq!(deleted[0].total_length, 800);
    let conn = Connection::open(&db)?;
    assert_eq!(count(&conn, "assembly_ctg", "id = 305")?, 0);
    assert_eq!(count(&conn, "assembly_seq", "id = 205")?, 1);
    assert_eq!(count(&conn, "source_seq", "id = 103")?, 1);
    drop(conn);
    undo_main_view_history(&db, &target("Chr01"))?;
    assert_eq!(load_ctg_name(&db, 305)?, "Support1");
    let conn = Connection::open(&db)?;
    assert_eq!(
        conn.query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=1",
            [],
            |row| row.get::<_, String>(0)
        )?,
        final_path
    );
    assert_eq!(
        conn.query_row(
            "SELECT assembly_ctg_id FROM export_record WHERE id=601",
            [],
            |row| row.get::<_, i64>(0)
        )?,
        305
    );
    drop(conn);
    redo_main_view_history(&db, &target("Chr01"))?;
    let record = list_deleted_ctgs(&db, 1, Some("Chr01"), Some(2))?.remove(0);
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".into(),
            action: "restore-deleted-ctg".into(),
            args: json!({"deletedCtgRecordId":record.deleted_ctg_record_id}),
        },
    )?;
    assert_eq!(load_ctg_name(&db, 305)?, "Support1");
    assert!(list_deleted_ctgs(&db, 1, Some("Chr01"), Some(2))?.is_empty());
    // Restoring a member is not a promise to restore all deletion dependencies.
    let conn = Connection::open(&db)?;
    assert_eq!(
        conn.query_row(
            "SELECT assembly_ctg_id FROM export_record WHERE id=601",
            [],
            |row| row.get::<_, Option<i64>>(0)
        )?,
        None
    );
    drop(conn);
    undo_main_view_history(&db, &target("Chr01"))?;
    assert_eq!(list_deleted_ctgs(&db, 1, Some("Chr01"), Some(2))?.len(), 1);
    redo_main_view_history(&db, &target("Chr01"))?;
    assert_eq!(load_ctg_name(&db, 305)?, "Support1");
    Ok(())
}

#[test]
fn deleted_member_dataset_scope_includes_derived_targets_without_cross_dataset_leakage()
-> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    let conn = Connection::open(&db)?;
    conn.execute("INSERT INTO derived_ctg_track_member (project_id, source_seq_id, target_dataset_id, target_chr_name, created_at) VALUES (1,103,1,'Chr01','1')", [])?;
    // A primary source assigned a support target is still excluded by the live support contract.
    conn.execute("INSERT INTO derived_ctg_track_member (project_id, source_seq_id, target_dataset_id, target_chr_name, created_at) VALUES (1,101,2,'Chr01','1')", [])?;
    drop(conn);
    run_main_view_batch_delete(
        &db,
        &RunMainViewBatchDeleteParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".into(),
            assembly_ctg_ids: vec![301, 305],
        },
    )?;
    let primary = list_deleted_ctgs(&db, 1, Some("Chr01"), Some(1))?;
    assert_eq!(primary.len(), 2);
    let support = list_deleted_ctgs(&db, 1, Some("Chr01"), Some(2))?;
    assert_eq!(support.len(), 1);
    assert_eq!(support[0].assembly_ctg_id, 305);
    assert!(list_deleted_ctgs(&db, 1, Some("Chr02"), Some(2))?.is_empty());
    assert!(list_deleted_ctgs(&db, 1, None, Some(99))?.is_empty());
    assert_eq!(list_deleted_ctgs(&db, 1, None, Some(1))?.len(), 2);
    Ok(())
}
