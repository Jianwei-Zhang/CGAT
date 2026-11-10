use super::*;

#[test]
fn chromosome_navigation_and_large_fractional_layout_saves_preserve_drag_history() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let db = temp.path().join("project.sqlite");
    seed_workspace(&db)?;
    Connection::open(&db)?.execute(
        "INSERT INTO project_assembly_view_state (project_id, updated_at) VALUES (1, '1')",
        [],
    )?;
    let mut expected = std::collections::BTreeMap::new();
    for (chr, id, role, offset) in [
        ("Chr01", 305, "support", -25225348.91),
        ("Chr02", 303, "primary", 11017184.73),
        ("Chr01", 305, "support", 76154742.79),
        ("Chr02", 303, "primary", -9698313.22),
        ("Chr01", 305, "support", -1720494.23),
        ("Chr02", 303, "primary", -16065919.98),
    ] {
        let _ = get_main_view_history_status(&db, &target(chr))?;
        // A view preference/scroll save after navigation writes JS-normalized
        // offsets for all chromosomes, not just the mounted one.
        let mut offsets = load_track_offsets(&db)?;
        for entry in &mut offsets {
            let offset = entry["offsetBp"].as_f64().unwrap();
            entry["offsetBp"] = json!((offset * 100.0).round() / 100.0);
        }
        Connection::open(&db)?.execute(
            "UPDATE project_assembly_view_state SET track_drag_offsets_json=?1 WHERE project_id=1",
            [serde_json::to_string(&offsets)?],
        )?;
        let mut args = json!({"trackRole":role,"assemblyCtgId":id,"offsetBp":offset});
        if role == "support" {
            args["datasetId"] = json!(2);
        }
        let result = run_main_view_layout_action(
            &db,
            &RunMainViewLayoutActionParams {
                history_capacity: None,
                project_id: 1,
                chr_name: chr.into(),
                action: "drag-ctg".into(),
                args,
            },
        )?;
        assert!(
            !result.invalidated,
            "unexpected invalidation after switching to {chr}, offset {offset}"
        );
        *expected.entry(chr).or_insert(0) += 1;
        assert_eq!(result.status.applied_operation_count, expected[chr]);
    }
    for chr in ["Chr01", "Chr02"] {
        assert!(undo_main_view_history(&db, &target(chr))?.changed);
        assert!(redo_main_view_history(&db, &target(chr))?.changed);
    }
    Ok(())
}
