use super::*;

fn drag(
    db_path: &std::path::Path,
    args: serde_json::Value,
) -> Result<MainViewHistoryMutationSummary> {
    run_main_view_layout_action(
        db_path,
        &RunMainViewLayoutActionParams {
            history_capacity: None,
            project_id: 1,
            chr_name: "Chr01".to_string(),
            action: "drag-ctg".to_string(),
            args,
        },
    )
}

#[test]
fn unrelated_selected_ctgs_translate_atomically_and_round_trip() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    for (id, offset) in [(301, 20), (302, -30)] {
        drag(
            &db,
            json!({"trackRole":"primary","assemblyCtgId":id,"offsetBp":offset}),
        )?;
    }
    let before = load_track_offsets(&db)?;
    let result = drag(
        &db,
        json!({
            "trackRole":"primary","assemblyCtgId":301,"offsetBp":35,"dragSelection":true,
            "targets":[
                {"trackRole":"primary","assemblyCtgId":301,"offsetBp":35},
                {"trackRole":"primary","assemblyCtgId":302,"offsetBp":-15}
            ]
        }),
    )?;
    assert!(result.changed);
    assert_eq!(result.status.applied_operation_count, 3);
    assert_eq!(result.descriptor.as_ref().unwrap().target_count, 2);
    assert!(result.descriptor.as_ref().unwrap().target_name.is_none());
    let after = load_track_offsets(&db)?;
    for (id, offset) in [(301, 35.0), (302, -15.0)] {
        assert_eq!(
            after
                .iter()
                .find(|entry| entry["assemblyCtgId"] == id)
                .unwrap()["offsetBp"]
                .as_f64(),
            Some(offset)
        );
    }
    assert!(undo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(load_track_offsets(&db)?, before);
    assert!(redo_main_view_history(&db, &target("Chr01"))?.changed);
    assert_eq!(load_track_offsets(&db)?, after);
    Ok(())
}

#[test]
fn explicit_selection_still_rejects_cross_chr_duplicate_and_cross_track_targets() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    for second in [
        json!({"trackRole":"primary","assemblyCtgId":303,"offsetBp":5}),
        json!({"trackRole":"primary","assemblyCtgId":301,"offsetBp":5}),
        json!({"trackRole":"support","datasetId":2,"assemblyCtgId":305,"offsetBp":5}),
    ] {
        assert!(
            drag(
                &db,
                json!({"trackRole":"primary","assemblyCtgId":301,"offsetBp":5,"dragSelection":true,
            "targets":[{"trackRole":"primary","assemblyCtgId":301,"offsetBp":5},second]})
            )
            .is_err()
        );
        assert_eq!(
            count(
                &Connection::open(&db)?,
                "project_assembly_view_state",
                "track_drag_offsets_json <> '[]'"
            )?,
            0
        );
    }
    assert_eq!(
        get_main_view_history_status(&db, &target("Chr01"))?.applied_operation_count,
        0
    );
    Ok(())
}

#[test]
fn legacy_grouped_drag_cannot_silently_bypass_source_validation() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    assert!(
        drag(
            &db,
            json!({"trackRole":"primary","assemblyCtgId":301,"offsetBp":5,
        "targets":[{"trackRole":"primary","assemblyCtgId":301,"offsetBp":5},
                   {"trackRole":"primary","assemblyCtgId":302,"offsetBp":5}]})
        )
        .is_err()
    );
    assert_eq!(
        count(
            &Connection::open(&db)?,
            "project_assembly_view_state",
            "track_drag_offsets_json <> '[]'"
        )?,
        0
    );
    Ok(())
}

#[test]
fn explicit_selection_rejects_nonrigid_translation() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    assert!(
        drag(
            &db,
            json!({"trackRole":"primary","assemblyCtgId":301,"offsetBp":5,"dragSelection":true,
        "targets":[{"trackRole":"primary","assemblyCtgId":301,"offsetBp":5},
                   {"trackRole":"primary","assemblyCtgId":302,"offsetBp":6}]})
        )
        .is_err()
    );
    assert_eq!(
        count(
            &Connection::open(&db)?,
            "project_assembly_view_state",
            "track_drag_offsets_json <> '[]'"
        )?,
        0
    );
    Ok(())
}
