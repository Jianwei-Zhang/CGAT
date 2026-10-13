use super::*;

fn seed_fragments(db_path: &std::path::Path, source_id: i64) -> Result<Vec<i64>> {
    seed_workspace(db_path)?;
    let conn = Connection::open(db_path)?;
    conn.execute(
        "INSERT INTO source_seq_n_region(source_seq_id,start_bp,end_bp,length_bp)
        VALUES(?1,401,410,10)",
        [source_id],
    )?;
    crate::source_fragments::split_new_source_instances(&conn, 1, 0)?;
    let mut stmt = conn.prepare(
        "SELECT c.id FROM assembly_ctg c
        JOIN assembly_seq s ON s.id=c.assembly_seq_id
        WHERE s.source_seq_id=?1 AND c.assigned_chr_name='Chr01' ORDER BY c.id",
    )?;
    Ok(stmt
        .query_map([source_id], |row| row.get(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?)
}

fn drag(
    db_path: &std::path::Path,
    args: serde_json::Value,
) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_layout_action(
        db_path,
        &RunMainViewLayoutActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".into(),
            action: "drag-ctg".into(),
            args,
        },
    )
}

#[test]
fn source_fragment_group_drag_is_one_persistent_undo_redo_step_in_each_track() -> Result<()> {
    for role in ["primary", "support", "phased"] {
        let temp = tempfile::tempdir()?;
        let db = temp.path().join("project.sqlite");
        let ids = seed_fragments(&db, if role == "support" { 103 } else { 101 })?;
        assert_eq!(ids.len(), 2);
        let conn = Connection::open(&db)?;
        if role == "phased" {
            conn.execute("INSERT INTO phased_chr_track(id,project_id,parent_chr_name,haplotype_key,label,display_order,created_at)
                VALUES(410,1,'Chr01','A','Chr01A',1,'1')", [])?;
            for (index, id) in ids.iter().enumerate() {
                conn.execute("INSERT INTO phased_chr_track_item(id,phased_track_id,assembly_ctg_id,display_order,gap_before_px,orient,created_at)
                    VALUES(?1,410,?2,?3,0,'+','1')", params![510 + index as i64, id, index as i64])?;
            }
        }
        let offset = |index: usize, value: f64| {
            let mut result = json!({"trackRole":role,"assemblyCtgId":ids[index],"offsetBp":value});
            if role == "support" {
                result["datasetId"] = json!(2);
            }
            if role == "phased" {
                result["phasedTrackId"] = json!(410);
                result["phasedTrackItemId"] = json!(510 + index as i64);
            }
            result
        };
        // Preserve independently positioned fragments and unrelated offsets.
        drag(&db, offset(0, 10.0))?;
        drag(&db, offset(1, -25.0))?;
        drag(
            &db,
            json!({"trackRole":"primary","assemblyCtgId":302,"offsetBp":88.0}),
        )?;
        let before = sorted_offsets(&db)?;
        let count_before =
            get_main_view_history_status(&db, &target("Chr01"))?.applied_operation_count;
        let mut args = offset(1, 0.0); // A sibling, not the first source interval, is the drag leader.
        args["targets"] = json!([offset(1, 0.0), offset(0, 35.0)]);
        let result = drag(&db, args)?;
        assert!(result.changed);
        assert_eq!(result.status.applied_operation_count, count_before + 1);
        let after = sorted_offsets(&db)?;
        assert!(
            after
                .iter()
                .any(|entry| entry["assemblyCtgId"] == ids[0] && entry["offsetBp"] == 35.0)
        );
        assert!(!after.iter().any(|entry| entry["assemblyCtgId"] == ids[1]));
        assert!(
            after
                .iter()
                .any(|entry| entry["assemblyCtgId"] == 302 && entry["offsetBp"] == 88.0)
        );
        // These APIs reopen the DB, so this also checks persistence, not only in-memory preview.
        undo_main_view_history(&db, &target("Chr01"))?;
        assert_eq!(sorted_offsets(&db)?, before);
        redo_main_view_history(&db, &target("Chr01"))?;
        assert_eq!(sorted_offsets(&db)?, after);
        let names: Vec<String> = ids
            .iter()
            .map(|id| load_ctg_name(&db, *id))
            .collect::<Result<_>>()?;
        run_main_view_editor_action(
            &db,
            &RunMainViewEditorActionParams {
                history_capacity: None,
                project_id: 1,
                chr_name: "Chr01".into(),
                action: "rename-ctg".into(),
                args: json!({"assemblyCtgId":ids[0],"newName":"one fragment only"}),
            },
        )?;
        assert_eq!(load_ctg_name(&db, ids[1])?, names[1]);
        assert_eq!(sorted_offsets(&db)?, after);
    }
    Ok(())
}

#[test]
fn source_fragment_drag_rejects_unrelated_or_cross_scope_targets_without_partial_writes()
-> Result<()> {
    for invalid in [
        "ordinary",
        "other-instance",
        "other-source",
        "cross-chromosome",
        "duplicate",
        "cross-track",
        "wrong-leader",
        "empty",
    ] {
        let temp = tempfile::tempdir()?;
        let db = temp.path().join("project.sqlite");
        let ids = seed_fragments(&db, 101)?;
        let conn = Connection::open(&db)?;
        let target_id = match invalid {
            "ordinary" => 302,
            "cross-chromosome" => 303,
            "duplicate" => ids[0],
            _ => ids[1],
        };
        if invalid == "other-instance" {
            conn.execute(
                "UPDATE assembly_seq SET instance_key='n-fragment:another:411-1000'
                WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=?1)",
                [target_id],
            )?;
        }
        if invalid == "other-source" {
            conn.execute(
                "UPDATE assembly_seq SET source_seq_id=102
                WHERE id=(SELECT assembly_seq_id FROM assembly_ctg WHERE id=?1)",
                [target_id],
            )?;
        }
        let first = json!({"trackRole":"primary","assemblyCtgId":ids[0],"offsetBp":15.0});
        drag(&db, first.clone())?;
        let before = sorted_offsets(&db)?;
        let count_before =
            get_main_view_history_status(&db, &target("Chr01"))?.applied_operation_count;
        let mut second = json!({"trackRole":"primary","assemblyCtgId":target_id,"offsetBp":20.0});
        if invalid == "cross-track" {
            second["trackRole"] = json!("support");
            second["datasetId"] = json!(1);
        }
        let mut args = first.clone();
        args["targets"] = match invalid {
            "empty" => json!([]),
            "wrong-leader" => json!([second, first]),
            _ => json!([first, second]),
        };
        assert!(drag(&db, args).is_err(), "{invalid}");
        assert_eq!(sorted_offsets(&db)?, before, "{invalid}");
        assert_eq!(
            get_main_view_history_status(&db, &target("Chr01"))?.applied_operation_count,
            count_before
        );
    }
    Ok(())
}

fn sorted_offsets(db_path: &std::path::Path) -> Result<Vec<serde_json::Value>> {
    let mut values = load_track_offsets(db_path)?;
    values.sort_by_key(|value| value.to_string());
    Ok(values)
}
