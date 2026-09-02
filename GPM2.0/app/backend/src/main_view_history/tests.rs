use anyhow::Result;
use rusqlite::{Connection, params};
use serde_json::json;

use crate::db::init_workspace_schema;

use super::*;

#[test]
fn rename_round_trips_through_persistent_undo_and_redo() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;

    let mutation = run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "renamed" }),
        },
    )?;
    assert!(mutation.changed);
    assert!(mutation.status.can_undo);
    assert_eq!(load_ctg_name(&db_path, 301)?, "renamed");

    let undone = undo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(undone.changed);
    assert!(undone.status.can_redo);
    assert_eq!(load_ctg_name(&db_path, 301)?, "Ctg1");

    let redone = redo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(redone.changed);
    assert_eq!(load_ctg_name(&db_path, 301)?, "renamed");

    let reopened = get_main_view_history_status(&db_path, &target("Chr01"))?;
    assert!(reopened.can_undo);
    assert_eq!(reopened.applied_operation_count, 1);
    Ok(())
}

#[test]
fn no_op_does_not_create_history_or_clear_forward() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "renamed" }),
        },
    )?;
    undo_main_view_history(&db_path, &target("Chr01"))?;

    let no_op = run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "Ctg1" }),
        },
    )?;
    assert!(!no_op.changed);
    assert!(no_op.status.can_redo);
    assert_eq!(no_op.status.retained_operation_count, 1);
    Ok(())
}

#[test]
fn chromosome_histories_are_independent() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "flip-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301 }),
        },
    )?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr02".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 303, "newName": "chr2-name" }),
        },
    )?;

    undo_main_view_history(&db_path, &target("Chr01"))?;
    assert_eq!(load_ctg_name(&db_path, 303)?, "chr2-name");
    assert!(get_main_view_history_status(&db_path, &target("Chr02"))?.can_undo);
    Ok(())
}

#[test]
fn new_edit_clears_only_the_current_chromosome_forward_branch() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    for (chr_name, ctg_id, new_name) in [("Chr01", 301, "chr1-first"), ("Chr02", 303, "chr2-first")]
    {
        run_main_view_editor_action(
            &db_path,
            &RunMainViewEditorActionParams {
                project_id: 1,
                chr_name: chr_name.to_string(),
                action: "rename-ctg".to_string(),
                args: json!({ "assemblyCtgId": ctg_id, "newName": new_name }),
            },
        )?;
        undo_main_view_history(&db_path, &target(chr_name))?;
    }

    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "chr1-second" }),
        },
    )?;

    assert!(!get_main_view_history_status(&db_path, &target("Chr01"))?.can_redo);
    assert!(get_main_view_history_status(&db_path, &target("Chr02"))?.can_redo);
    Ok(())
}

#[test]
fn batch_delete_and_dependencies_round_trip_atomically() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    let conn = Connection::open(&db_path)?;
    conn.execute(
        "INSERT INTO phased_chr_track
         (id, project_id, parent_chr_name, haplotype_key, label, display_order, created_at)
         VALUES (401, 1, 'Chr01', 'A', 'Chr01A', 1, '1')",
        [],
    )?;
    conn.execute(
        "INSERT INTO phased_chr_track_item
         (id, phased_track_id, assembly_ctg_id, display_order, gap_before_px, orient, created_at)
         VALUES (501, 401, 301, 1, 17, '-', '1')",
        [],
    )?;
    conn.execute(
        "INSERT INTO export_record
         (id, project_id, export_type, assembly_ctg_id, output_path, created_at)
         VALUES (601, 1, 'ctg_fasta', 301, 'out.fa', '1')",
        [],
    )?;
    conn.execute(
        "INSERT INTO project_assembly_view_state
         (project_id, final_path_by_chr_json, degap_project_state_json, updated_at)
         VALUES (1, ?1, ?2, '1')",
        params![
            json!({"Chr01":{"segments":[{"assemblyCtgId":301}]}}).to_string(),
            json!({"jobs":[{"endpoint":{"assemblyCtgId":302}}]}).to_string(),
        ],
    )?;
    drop(conn);

    let request = RunMainViewBatchDeleteParams {
        project_id: 1,
        chr_name: "Chr01".to_string(),
        assembly_ctg_ids: vec![301, 302],
    };
    let impact = inspect_main_view_delete(&db_path, &request)?;
    assert_eq!(impact.ctg_count, 2);
    assert_eq!(impact.phased_item_count, 1);
    assert_eq!(impact.export_record_count, 1);
    assert_eq!(impact.final_path_reference_count, 1);
    assert_eq!(impact.degap_reference_count, 1);

    let deleted = run_main_view_batch_delete(&db_path, &request)?;
    assert!(deleted.changed);
    assert_eq!(
        deleted.descriptor.as_ref().map(|item| item.target_count),
        Some(2)
    );
    let conn = Connection::open(&db_path)?;
    assert_eq!(count(&conn, "assembly_ctg", "id IN (301, 302)")?, 0);
    assert_eq!(count(&conn, "phased_chr_track_item", "id = 501")?, 0);
    assert_eq!(
        conn.query_row(
            "SELECT assembly_ctg_id FROM export_record WHERE id = 601",
            [],
            |row| row.get::<_, Option<i64>>(0),
        )?,
        None
    );
    drop(conn);

    undo_main_view_history(&db_path, &target("Chr01"))?;
    let conn = Connection::open(&db_path)?;
    assert_eq!(count(&conn, "assembly_ctg", "id IN (301, 302)")?, 2);
    assert_eq!(count(&conn, "phased_chr_track_item", "id = 501")?, 1);
    assert_eq!(
        conn.query_row(
            "SELECT assembly_ctg_id FROM export_record WHERE id = 601",
            [],
            |row| row.get::<_, Option<i64>>(0),
        )?,
        Some(301)
    );
    let view_json: (String, String) = conn.query_row(
        "SELECT final_path_by_chr_json, degap_project_state_json
         FROM project_assembly_view_state WHERE project_id = 1",
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    assert_eq!(
        view_json.0,
        json!({"Chr01":{"segments":[{"assemblyCtgId":301}]}}).to_string()
    );
    assert_eq!(
        view_json.1,
        json!({"jobs":[{"endpoint":{"assemblyCtgId":302}}]}).to_string()
    );
    Ok(())
}

#[test]
fn project_view_metadata_changes_do_not_invalidate_delete_history() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    Connection::open(&db_path)?.execute(
        "INSERT INTO project_assembly_view_state
         (project_id, final_path_by_chr_json, degap_project_state_json, updated_at)
         VALUES (1, ?1, '{}', 'initial')",
        params![json!({"Chr01":{"segments":[{"assemblyCtgId":301}]}}).to_string()],
    )?;
    let request = RunMainViewBatchDeleteParams {
        project_id: 1,
        chr_name: "Chr01".to_string(),
        assembly_ctg_ids: vec![301],
    };

    run_main_view_batch_delete(&db_path, &request)?;
    Connection::open(&db_path)?.execute(
        "UPDATE project_assembly_view_state
         SET updated_at = 'viewport-write-1', note = 'scroll-1'
         WHERE project_id = 1",
        [],
    )?;
    let undone = undo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(undone.changed);
    assert!(!undone.invalidated);

    Connection::open(&db_path)?.execute(
        "UPDATE project_assembly_view_state
         SET updated_at = 'viewport-write-2', note = 'scroll-2'
         WHERE project_id = 1",
        [],
    )?;
    let redone = redo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(redone.changed);
    assert!(!redone.invalidated);

    Connection::open(&db_path)?.execute(
        "UPDATE project_assembly_view_state
         SET updated_at = 'viewport-write-3', note = 'scroll-3'
         WHERE project_id = 1",
        [],
    )?;
    let reset = reset_main_view_history(&db_path, &target("Chr01"))?;
    assert!(reset.changed);
    assert!(!reset.invalidated);

    let conn = Connection::open(&db_path)?;
    assert_eq!(count(&conn, "assembly_ctg", "id = 301")?, 1);
    let metadata: (String, Option<String>) = conn.query_row(
        "SELECT updated_at, note FROM project_assembly_view_state WHERE project_id = 1",
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    assert_ne!(metadata.0, "viewport-write-3");
    assert_eq!(metadata.1.as_deref(), Some("scroll-3"));
    Ok(())
}

#[test]
fn project_view_business_change_still_invalidates_delete_history() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    Connection::open(&db_path)?.execute(
        "INSERT INTO project_assembly_view_state
         (project_id, final_path_by_chr_json, degap_project_state_json, updated_at)
         VALUES (1, ?1, '{}', 'initial')",
        params![json!({"Chr01":{"segments":[{"assemblyCtgId":301}]}}).to_string()],
    )?;
    run_main_view_batch_delete(
        &db_path,
        &RunMainViewBatchDeleteParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            assembly_ctg_ids: vec![301],
        },
    )?;
    Connection::open(&db_path)?.execute(
        "UPDATE project_assembly_view_state
         SET final_path_by_chr_json = '{\"external\":true}'
         WHERE project_id = 1",
        [],
    )?;

    let undo = undo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(!undo.changed);
    assert!(undo.invalidated);
    assert_eq!(
        count(&Connection::open(&db_path)?, "assembly_ctg", "id = 301")?,
        0
    );
    Ok(())
}

#[test]
fn external_change_invalidates_only_target_chromosome_history() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "history-name" }),
        },
    )?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr02".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 303, "newName": "chr2-name" }),
        },
    )?;
    Connection::open(&db_path)?.execute(
        "UPDATE assembly_ctg SET name = 'external-name' WHERE id = 301",
        [],
    )?;

    let undo = undo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(!undo.changed);
    assert!(undo.invalidated);
    assert!(!undo.status.can_undo);
    assert_eq!(load_ctg_name(&db_path, 301)?, "external-name");
    assert!(get_main_view_history_status(&db_path, &target("Chr02"))?.can_undo);
    Ok(())
}

#[test]
fn reset_is_one_reversible_step() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "renamed" }),
        },
    )?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "hide-seq".to_string(),
            args: json!({ "assemblySeqId": 202 }),
        },
    )?;

    let reset = reset_main_view_history(&db_path, &target("Chr01"))?;
    assert!(reset.changed);
    assert!(!reset.status.can_reset);
    assert_eq!(load_ctg_name(&db_path, 301)?, "Ctg1");
    assert_eq!(load_seq_hidden(&db_path, 202)?, 0);

    undo_main_view_history(&db_path, &target("Chr01"))?;
    assert_eq!(load_ctg_name(&db_path, 301)?, "renamed");
    assert_eq!(load_seq_hidden(&db_path, 202)?, 1);
    Ok(())
}

#[test]
fn history_retains_only_fifty_combined_steps_per_chromosome() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    for index in 1..=51 {
        run_main_view_editor_action(
            &db_path,
            &RunMainViewEditorActionParams {
                project_id: 1,
                chr_name: "Chr01".to_string(),
                action: "rename-ctg".to_string(),
                args: json!({
                    "assemblyCtgId": 301,
                    "newName": format!("retained-name-{index}"),
                }),
            },
        )?;
    }

    let status = get_main_view_history_status(&db_path, &target("Chr01"))?;
    assert_eq!(status.retained_operation_count, 50);
    assert_eq!(status.applied_operation_count, 50);
    for _ in 0..50 {
        assert!(undo_main_view_history(&db_path, &target("Chr01"))?.changed);
    }
    assert_eq!(load_ctg_name(&db_path, 301)?, "retained-name-1");
    assert!(!undo_main_view_history(&db_path, &target("Chr01"))?.changed);
    Ok(())
}

#[test]
fn invalid_batch_target_rolls_back_the_complete_delete() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    let result = run_main_view_batch_delete(
        &db_path,
        &RunMainViewBatchDeleteParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            assembly_ctg_ids: vec![301, 999_999],
        },
    );
    assert!(result.is_err());

    let conn = Connection::open(&db_path)?;
    assert_eq!(count(&conn, "assembly_ctg", "id IN (301, 302)")?, 2);
    assert_eq!(count(&conn, "deleted_assembly_ctg", "project_id = 1")?, 0);
    assert_eq!(count(&conn, "edit_audit_log", "project_id = 1")?, 0);
    drop(conn);
    assert!(!get_main_view_history_status(&db_path, &target("Chr01"))?.can_undo);
    Ok(())
}

#[test]
fn project_wide_name_conflict_invalidates_only_the_rename_history() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "renamed" }),
        },
    )?;
    Connection::open(&db_path)?
        .execute("UPDATE assembly_ctg SET name = 'Ctg1' WHERE id = 303", [])?;

    let undo = undo_main_view_history(&db_path, &target("Chr01"))?;
    assert!(undo.invalidated);
    assert!(!undo.changed);
    assert_eq!(load_ctg_name(&db_path, 301)?, "renamed");
    assert_eq!(load_ctg_name(&db_path, 303)?, "Ctg1");
    Ok(())
}

#[test]
fn additive_new_ctg_survives_undo_of_an_older_operation() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    seed_workspace(&db_path)?;
    run_main_view_editor_action(
        &db_path,
        &RunMainViewEditorActionParams {
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "rename-ctg".to_string(),
            args: json!({ "assemblyCtgId": 301, "newName": "renamed" }),
        },
    )?;
    let conn = Connection::open(&db_path)?;
    conn.execute(
        "INSERT INTO assembly_seq
         (id, project_id, source_seq_id, instance_key, orient, source_start,
          source_end, left_end_type, right_end_type, hidden, created_at)
         VALUES (204, 1, 102, 'additive:1', '+', 1, 900, 'normal', 'normal', 0, '2')",
        [],
    )?;
    conn.execute(
        "INSERT INTO assembly_ctg
         (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
          anchor_start, placement_mode, created_at)
         VALUES (304, 1, 204, 'new-additive-ctg', 'Chr01', 3, 300, 'manual', '2')",
        [],
    )?;
    drop(conn);

    undo_main_view_history(&db_path, &target("Chr01"))?;
    assert_eq!(load_ctg_name(&db_path, 301)?, "Ctg1");
    assert_eq!(load_ctg_name(&db_path, 304)?, "new-additive-ctg");
    Ok(())
}

fn target(chr_name: &str) -> MainViewHistoryTargetParams {
    MainViewHistoryTargetParams {
        project_id: 1,
        chr_name: chr_name.to_string(),
    }
}

fn seed_workspace(db_path: &std::path::Path) -> Result<()> {
    let conn = Connection::open(db_path)?;
    init_workspace_schema(&conn)?;
    conn.execute(
        "INSERT INTO reference_genome
         (id, name, species_name, assembly_label, fasta_path, fai_path)
         VALUES (1, 'ref', 'sp', 'v1', 'ref.fa', 'ref.fa.fai')",
        [],
    )?;
    conn.execute(
        "INSERT INTO reference_chr (id, reference_genome_id, chr_name, chr_order, length)
         VALUES (1, 1, 'Chr01', 1, 100000), (2, 1, 'Chr02', 2, 100000)",
        [],
    )?;
    conn.execute(
        "INSERT INTO dataset (id, name, assembler, fasta_path, fai_path)
         VALUES (1, 'ds1', 'asm', 'ds.fa', 'ds.fa.fai')",
        [],
    )?;
    conn.execute(
        "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
         VALUES (101, 1, 'tig1', 1, 1000),
                (102, 1, 'tig2', 2, 900)",
        [],
    )?;
    conn.execute(
        "INSERT INTO project
         (id, name, version, reference_genome_id, primary_dataset_id, created_at)
         VALUES (1, 'p1', 1, 1, 1, '1')",
        [],
    )?;
    conn.execute(
        "INSERT INTO assembly_seq
         (id, project_id, source_seq_id, instance_key, orient, source_start,
          source_end, left_end_type, right_end_type, hidden, created_at)
         VALUES (201, 1, 101, 'chr:1', '+', 1, 1000, 'normal', 'gap', 0, '1'),
                (202, 1, 102, 'chr:1', '-', 1, 900, 'telomere', 'normal', 0, '1'),
                (203, 1, 101, 'chr:2', '+', 1, 1000, 'normal', 'normal', 0, '1')",
        [],
    )?;
    conn.execute(
        "INSERT INTO assembly_ctg
         (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order,
          anchor_start, ref_orient, placement_mode, created_at)
         VALUES (301, 1, 201, 'Ctg1', 'Chr01', 1, 100, '+', 'auto', '1'),
                (302, 1, 202, 'Ctg2', 'Chr01', 2, 200, '-', 'auto', '1'),
                (303, 1, 203, 'Ctg3', 'Chr02', 1, 100, '+', 'auto', '1')",
        [],
    )?;
    Ok(())
}

fn load_ctg_name(db_path: &std::path::Path, ctg_id: i64) -> Result<String> {
    Ok(Connection::open(db_path)?.query_row(
        "SELECT name FROM assembly_ctg WHERE id = ?1",
        params![ctg_id],
        |row| row.get(0),
    )?)
}

fn load_seq_hidden(db_path: &std::path::Path, seq_id: i64) -> Result<i64> {
    Ok(Connection::open(db_path)?.query_row(
        "SELECT hidden FROM assembly_seq WHERE id = ?1",
        params![seq_id],
        |row| row.get(0),
    )?)
}

fn count(conn: &Connection, table: &str, predicate: &str) -> Result<i64> {
    let sql = format!("SELECT COUNT(*) FROM {table} WHERE {predicate}");
    Ok(conn.query_row(&sql, [], |row| row.get(0))?)
}
