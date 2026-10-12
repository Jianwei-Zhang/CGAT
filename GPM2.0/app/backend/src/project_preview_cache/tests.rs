use super::*;
use tempfile::TempDir;

fn fixture() -> Result<(TempDir, std::path::PathBuf)> {
    let root = tempfile::tempdir()?;
    let db = root.path().join("project.sqlite");
    let conn = open_workspace_db(&db)?;
    conn.execute_batch(
        r#"INSERT INTO reference_genome(id,name,species_name,assembly_label,fasta_path,fai_path) VALUES(1,'ref','s','a','ref.fa','ref.fai');
         INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'Chr1',1,1000),(2,1,'Chr2',2,1000);
         INSERT INTO dataset(id,name,assembler,fasta_path,fai_path) VALUES(1,'ds','a','ds.fa','ds.fai');
         INSERT INTO project(id,name,version,reference_genome_id,primary_dataset_id,created_at) VALUES(1,'p',1,1,1,'0'),(2,'q',1,1,1,'0');
         INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(1,1,'a',1,1000),(2,1,'b',2,1000);
         INSERT INTO assembly_seq(id,project_id,source_seq_id,source_end,created_at) VALUES(1,1,1,1000,'0'),(2,1,2,1000,'0');
         INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,anchor_start,created_at) VALUES(1,1,1,'a','Chr1',0,'0'),(2,1,2,'b','Chr2',0,'0');
         INSERT INTO project_assembly_view_state(project_id,updated_at,final_path_by_chr_json) VALUES(1,'0','{"Chr1":{"mode":"segments","segments":[]},"Chr2":{"mode":"segments","segments":[]}}');"#
    )?;
    Ok((root, db))
}

fn metadata(db: &Path) -> Result<Value> {
    get_project_preview_cache(db, 1, 1, None, None)
}

fn snapshot() -> Value {
    json!({"modelVersion": 1, "cards": [], "dependencies": [
        {"chrName": "Chr1", "ctgIds": [1], "sourceNames": []}, {"chrName": "Chr2", "ctgIds": [1,2], "sourceNames": []}]})
}

fn store(db: &Path, state: &Value) -> Result<Value> {
    put_project_preview_cache(
        db,
        1,
        1,
        state["identity"].as_str().unwrap(),
        state["revision"].as_i64().unwrap(),
        &snapshot(),
    )
}

#[test]
fn persisted_hit_and_metadata_only_memory_hit_do_not_invalidate_content() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    assert_eq!(state["valid"], false);
    assert_eq!(store(&db, &state)?["stored"], true);
    let reopened = metadata(&db)?;
    assert_eq!(reopened["valid"], true);
    assert_eq!(reopened["snapshot"], snapshot());
    assert_eq!(reopened["revision"], state["revision"]);
    let warm = get_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str(),
        state["revision"].as_i64(),
    )?;
    assert_eq!(warm["memoryValid"], true);
    assert!(warm["snapshot"].is_null());
    Ok(())
}

#[test]
fn view_scroll_timestamp_and_noop_content_writes_keep_validity() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let conn = open_workspace_db(&db)?;
    conn.execute_batch(r#"UPDATE project_assembly_view_state SET updated_at='1', track_scroll_state_json='{"main":{"left":3}}'; UPDATE assembly_ctg SET name=name;
        UPDATE project_assembly_view_state SET final_path_by_chr_json=json_set(final_path_by_chr_json, '$.Chr1.updatedAt', 'later');"#)?;
    assert_eq!(metadata(&db)?["revision"], state["revision"]);
    Ok(())
}

#[test]
fn local_path_change_invalidates_only_its_parent_and_is_transactional() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let mut conn = open_workspace_db(&db)?;
    let tx = conn.transaction()?;
    let paths = json!({"Chr1": {"mode":"segments","segments":[{"type":"gap","gapSizeBp":1}]},
        "Chr2": {"mode":"segments","segments":[]}});
    tx.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
        [paths.to_string()],
    )?;
    tx.rollback()?;
    assert_eq!(metadata(&db)?["revision"], state["revision"]);
    conn.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1",
        [paths.to_string()],
    )?;
    let changed = get_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str(),
        state["revision"].as_i64(),
    )?;
    assert_eq!(changed["dirtyChrNames"], json!(["Chr1"]));
    assert_eq!(changed["valid"], false);
    assert_eq!(store(&db, &state)?["superseded"], true);
    Ok(())
}

#[test]
fn reused_contig_invalidates_assignment_and_cached_source_dependencies() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let other_before = get_project_preview_cache(&db, 2, 1, None, None)?;
    open_workspace_db(&db)?.execute("UPDATE assembly_ctg SET name='changed' WHERE id=1", [])?;
    let changed = get_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str(),
        state["revision"].as_i64(),
    )?;
    assert_eq!(changed["dirtyChrNames"], json!(["Chr1", "Chr2"]));
    let other = get_project_preview_cache(&db, 2, 1, None, None)?;
    assert_eq!(other["revision"], other_before["revision"]);
    Ok(())
}

#[test]
fn migration_is_additive_and_corrupt_or_incompatible_cache_is_a_miss() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let conn = open_workspace_db(&db)?;
    conn.execute_batch(
        "DROP TRIGGER preview_v1_assembly_ctg_update; DROP TABLE project_preview_schema;",
    )?;
    drop(conn);
    let _reinstalled = metadata(&db)?;
    let conn = open_workspace_db(&db)?;
    assert_eq!(
        conn.query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))?,
        crate::db::CURRENT_SCHEMA_VERSION
    );
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM assembly_ctg", [], |row| row
            .get::<_, i64>(0))?,
        2
    );
    conn.execute(
        "UPDATE project_preview_cache SET payload_json='broken' WHERE project_id=1",
        [],
    )?;
    assert_eq!(metadata(&db)?["valid"], false);
    store(&db, &_reinstalled)?;
    assert_eq!(
        get_project_preview_cache(&db, 1, 2, None, None)?["valid"],
        false
    );
    conn.execute("DELETE FROM project_preview_cache WHERE project_id=1", [])?;
    assert_eq!(metadata(&db)?["valid"], false);
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM assembly_ctg", [], |row| row
            .get::<_, i64>(0))?,
        2
    );
    Ok(())
}

#[test]
fn copied_workspaces_keep_snapshots_but_new_databases_get_distinct_identity() -> Result<()> {
    let (root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let copied = root.path().join("relocated.sqlite");
    std::fs::copy(&db, &copied)?;
    let copied_state = metadata(&copied)?;
    assert_eq!(copied_state["valid"], true);
    assert_eq!(copied_state["identity"], state["identity"]);
    let (_other_root, other_db) = fixture()?;
    assert_ne!(metadata(&other_db)?["identity"], state["identity"]);
    Ok(())
}

#[test]
fn original_source_dependencies_cover_new_ctgs_without_previous_assembly_ids() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    let payload = json!({"modelVersion":1,"cards":[],"dependencies":[
        {"chrName":"Chr2","ctgIds":[],"sourceNames":[{"datasetName":"ds","contigName":"a"}]}]});
    put_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str().unwrap(),
        state["revision"].as_i64().unwrap(),
        &payload,
    )?;
    open_workspace_db(&db)?.execute_batch("INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,source_end,created_at) VALUES(3,1,1,'another-instance',1000,'0');
        INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,anchor_start,created_at) VALUES(3,1,3,'new-a','Chr1',0,'0');")?;
    let changed = get_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str(),
        state["revision"].as_i64(),
    )?;
    assert_eq!(changed["dirtyChrNames"], json!(["Chr1", "Chr2"]));
    Ok(())
}

#[test]
fn optional_cache_schema_failure_does_not_change_normal_project_read_schema() -> Result<()> {
    let (_root, db) = fixture()?;
    metadata(&db)?;
    let conn = open_workspace_db(&db)?;
    conn.execute("UPDATE project_preview_schema SET version=99", [])?;
    assert!(metadata(&db).is_err());
    assert_eq!(
        crate::main_view::list_chr_view_ctgs(&db, 1, None, None)?.len(),
        2
    );
    assert_eq!(
        conn.query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))?,
        crate::db::CURRENT_SCHEMA_VERSION
    );
    Ok(())
}

#[test]
fn project_deletion_cascades_derived_metadata_without_blocking_source_deletion() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let conn = open_workspace_db(&db)?;
    conn.execute("DELETE FROM project WHERE id=1", [])?;
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM project_preview_cache", [], |row| row
            .get::<_, i64>(
            0
        ))?,
        0
    );
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM project WHERE id=2", [], |row| row
            .get::<_, i64>(0))?,
        1
    );
    Ok(())
}

#[test]
fn full_schema_installs_invalidation_for_every_semantic_source() -> Result<()> {
    let (_root, db) = fixture()?;
    metadata(&db)?;
    let conn = open_workspace_db(&db)?;
    for table in [
        "assembly_ctg",
        "assembly_seq",
        "project_assembly_view_state",
        "project",
        "project_dataset",
        "derived_ctg_track_member",
        "phased_chr_track",
        "phased_chr_track_item",
        "dataset",
        "source_seq",
        "source_seq_n_region",
        "reference_chr",
        "imported_chr_assignment",
        "ref_alignment_hit",
        "imported_track_member_order",
        "derived_ctg",
        "grt_package",
        "grt_final_path_chr",
        "grt_final_path_segment",
    ] {
        for event in ["insert", "update", "delete"] {
            let trigger = format!("preview_v1_{table}_{event}");
            let exists: bool = conn.query_row(
                "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?1)",
                [&trigger],
                |row| row.get(0),
            )?;
            assert!(exists, "missing {trigger}");
        }
    }
    Ok(())
}

#[test]
fn source_reference_and_project_edits_invalidate_shared_dependencies() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let conn = open_workspace_db(&db)?;
    for statement in [
        "UPDATE dataset SET name='renamed' WHERE id=1",
        "UPDATE source_seq SET length=1200 WHERE id=1",
        "UPDATE reference_chr SET length=1300 WHERE id=1",
        "UPDATE project SET phased_assembly_enabled=1 WHERE id=1",
    ] {
        let before = metadata(&db)?;
        conn.execute(statement, [])?;
        let after = get_project_preview_cache(
            &db,
            1,
            1,
            before["identity"].as_str(),
            before["revision"].as_i64(),
        )?;
        assert!(
            after["revision"].as_i64() > before["revision"].as_i64(),
            "{statement}"
        );
        assert_eq!(after["dirtyChrNames"], json!(["*"]));
        assert_eq!(after["valid"], false);
    }
    Ok(())
}

#[test]
fn removed_paths_and_legacy_nonobject_entries_cannot_break_source_saves() -> Result<()> {
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let conn = open_workspace_db(&db)?;
    for paths in [
        json!({"Chr1": {"mode":"segments","segments":[]}, "Chr2":"legacy"}),
        json!({"Chr2":"legacy"}),
        json!({}),
    ] {
        conn.execute(
            "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1 WHERE project_id=1",
            [paths.to_string()],
        )?;
    }
    assert_eq!(metadata(&db)?["valid"], false);
    Ok(())
}

#[test]
fn phased_path_changes_invalidate_parent_chromosome_not_track_label() -> Result<()> {
    let (_root, db) = fixture()?;
    let conn = open_workspace_db(&db)?;
    conn.execute_batch("INSERT INTO phased_chr_track(id,project_id,parent_chr_name,haplotype_key,label,display_order,created_at) VALUES(1,1,'Chr1','h1','Chr1_h1',1,'0');")?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    let paths = json!({"Chr1": {"mode":"segments","segments":[]}, "Chr2":{"mode":"segments","segments":[]},
        "Chr1_h1": {"mode":"segments","segments":[{"type":"gap","gapSizeBp":1}]}});
    conn.execute(
        "UPDATE project_assembly_view_state SET final_path_by_chr_json=?1 WHERE project_id=1",
        [paths.to_string()],
    )?;
    let after = get_project_preview_cache(
        &db,
        1,
        1,
        state["identity"].as_str(),
        state["revision"].as_i64(),
    )?;
    assert_eq!(after["dirtyChrNames"], json!(["Chr1"]));
    Ok(())
}

#[test]
fn native_editor_undo_and_redo_all_invalidate_cached_content() -> Result<()> {
    use crate::main_view_history::{
        MainViewHistoryTargetParams, RunMainViewEditorActionParams, redo_main_view_history,
        run_main_view_editor_action, undo_main_view_history,
    };
    let (_root, db) = fixture()?;
    let state = metadata(&db)?;
    store(&db, &state)?;
    run_main_view_editor_action(
        &db,
        &RunMainViewEditorActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr1".to_owned(),
            action: "rename-ctg".to_owned(),
            args: json!({"assemblyCtgId":1,"newName":"renamed"}),
        },
    )?;
    let target = MainViewHistoryTargetParams {
        history_capacity: None,
        project_id: 1,
        chr_name: "Chr1".to_owned(),
    };
    for action in [undo_main_view_history, redo_main_view_history] {
        let before = metadata(&db)?;
        action(&db, &target)?;
        let after = get_project_preview_cache(
            &db,
            1,
            1,
            before["identity"].as_str(),
            before["revision"].as_i64(),
        )?;
        assert!(after["revision"].as_i64() > before["revision"].as_i64());
        assert_eq!(after["valid"], false);
    }
    Ok(())
}

#[test]
fn source_n_gap_changes_invalidate_snapshots_and_reject_inflight_publication() -> Result<()> {
    use crate::grt_package::load_grt_final_path_by_chr_for_project;
    let (_root, db) = fixture()?;
    let conn = open_workspace_db(&db)?;
    conn.execute_batch("INSERT INTO grt_package VALUES(1,'gpm_grt_app_precomputed_v2','2','2','recipe','ds','[]',0,'','','','','','','{}');")?;
    let chromosome = json!({"chr":"Chr1","q4_length":1000,"segments":[{"segment_id":"source","kind":"contig","length":1000,
        "source":{"dataset":"ds","contig":"a","start":1,"end":1000,"orientation":"+"}}]});
    conn.execute("INSERT INTO grt_final_path_chr(chr,q4_length,q4_sha256,chromosome_json) VALUES('Chr1',1000,'',?1)", [chromosome.to_string()])?;
    for (sql, expected_gap) in [
        (
            "INSERT INTO source_seq_n_region(source_seq_id,start_bp,end_bp,length_bp) VALUES(1,401,450,50)",
            50,
        ),
        (
            "UPDATE source_seq_n_region SET end_bp=500,length_bp=100 WHERE source_seq_id=1",
            100,
        ),
        ("DELETE FROM source_seq_n_region WHERE source_seq_id=1", 0),
    ] {
        let before = metadata(&db)?;
        let mut payload = snapshot();
        payload["baseline"] =
            serde_json::to_value(load_grt_final_path_by_chr_for_project(&db, 1)?)?;
        put_project_preview_cache(
            &db,
            1,
            1,
            before["identity"].as_str().unwrap(),
            before["revision"].as_i64().unwrap(),
            &payload,
        )?;
        conn.execute(sql, [])?;
        let changed = get_project_preview_cache(
            &db,
            1,
            1,
            before["identity"].as_str(),
            before["revision"].as_i64(),
        )?;
        assert_eq!(changed["valid"], false);
        assert_eq!(changed["memoryValid"], false);
        assert_eq!(changed["dirtyChrNames"], json!(["*"]));
        assert_eq!(
            put_project_preview_cache(
                &db,
                1,
                1,
                before["identity"].as_str().unwrap(),
                before["revision"].as_i64().unwrap(),
                &payload
            )?["superseded"],
            true
        );
        let cold = serde_json::to_value(load_grt_final_path_by_chr_for_project(&db, 1)?)?;
        let gap_length: i64 = cold["Chr1"]["segments"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|part| part["kind"] == "gap")
            .map(|part| part["length"].as_i64().unwrap())
            .sum();
        assert_eq!(gap_length, expected_gap);
        payload["baseline"] = cold.clone();
        put_project_preview_cache(
            &db,
            1,
            1,
            changed["identity"].as_str().unwrap(),
            changed["revision"].as_i64().unwrap(),
            &payload,
        )?;
        assert_eq!(metadata(&db)?["snapshot"]["baseline"], cold);
    }
    Ok(())
}

#[test]
fn cache_v2_upgrade_resets_identity_and_reinstalls_n_gap_tracking() -> Result<()> {
    let (_root, db) = fixture()?;
    let before = metadata(&db)?;
    store(&db, &before)?;
    let conn = open_workspace_db(&db)?;
    conn.execute_batch("UPDATE project_preview_schema SET version=2; DROP TRIGGER preview_v1_source_seq_n_region_insert; DROP TRIGGER preview_v1_source_seq_n_region_update; DROP TRIGGER preview_v1_source_seq_n_region_delete;")?;
    let upgraded = metadata(&db)?;
    assert_ne!(upgraded["identity"], before["identity"]);
    assert_eq!(upgraded["valid"], false);
    assert_eq!(upgraded["trackingVersion"], 3);
    conn.execute("INSERT INTO source_seq_n_region(source_seq_id,start_bp,end_bp,length_bp) VALUES(1,401,450,50)", [])?;
    assert!(metadata(&db)?["revision"].as_i64() > upgraded["revision"].as_i64());
    assert_eq!(
        conn.query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))?,
        crate::db::CURRENT_SCHEMA_VERSION
    );
    Ok(())
}

#[test]
fn source_and_chromosome_reassignment_invalidates_old_and_new_scopes() -> Result<()> {
    let (_root, db) = fixture()?;
    let before = metadata(&db)?;
    store(&db, &before)?;
    let conn = open_workspace_db(&db)?;
    conn.execute(
        "UPDATE assembly_ctg SET assigned_chr_name='Chr2' WHERE id=1",
        [],
    )?;
    let changed = get_project_preview_cache(
        &db,
        1,
        1,
        before["identity"].as_str(),
        before["revision"].as_i64(),
    )?;
    assert_eq!(changed["dirtyChrNames"], json!(["Chr1", "Chr2"]));
    let payload = json!({"modelVersion":1,"cards":[],"dependencies":[
        {"chrName":"Chr1","ctgIds":[],"sourceNames":[{"datasetName":"ds","contigName":"a"}]},
        {"chrName":"Chr2","ctgIds":[],"sourceNames":[{"datasetName":"ds","contigName":"b"}]}]});
    put_project_preview_cache(
        &db,
        1,
        1,
        changed["identity"].as_str().unwrap(),
        changed["revision"].as_i64().unwrap(),
        &payload,
    )?;
    conn.execute(
        "UPDATE assembly_seq SET source_seq_id=2,instance_key='reassigned' WHERE id=1",
        [],
    )?;
    let after = get_project_preview_cache(
        &db,
        1,
        1,
        changed["identity"].as_str(),
        changed["revision"].as_i64(),
    )?;
    assert_eq!(after["dirtyChrNames"], json!(["Chr1", "Chr2"]));
    Ok(())
}
