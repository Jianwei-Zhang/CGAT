use super::*;

fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("project.sqlite");
    let conn = open_workspace_db(&path).unwrap();
    conn.execute_batch("INSERT INTO reference_genome(id,name,species_name,assembly_label,fasta_path,fai_path)
        VALUES(1,'ref','species','v1','missing.fa','ref.fai');
        INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'chr1',1,100);
        INSERT INTO dataset(id,name,assembler,fasta_path,fai_path) VALUES(1,'original','assembler','missing.fa','ds.fai'),(2,'other','assembler','missing.fa','other.fai');
        INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(1,1,'a',1,60),(2,1,'b',2,30),(3,1,'c',3,10);
        INSERT INTO project(id,name,version,reference_genome_id,primary_dataset_id,created_at) VALUES(1,'project',1,1,1,'0');
        INSERT INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,1,'primary',1);").unwrap();
    (dir, path)
}

fn update() -> CatalogUpdate {
    CatalogUpdate {
        project_id: 1,
        object_type: "dataset".into(),
        object_id: 1,
        display_name: None,
        note: None,
        reset_name: false,
    }
}

#[test]
fn nx_uses_all_records_with_exact_thresholds() {
    let stats = statistics(vec![10, 30, 60]).unwrap();
    assert_eq!(
        (stats.n50, stats.n90, stats.l50, stats.longest),
        (Some(60), Some(30), Some(1), Some(60))
    );
    assert_eq!(statistics(vec![1, 1, 1]).unwrap().l50, Some(2));
    assert_eq!(statistics(vec![]).unwrap().n50, None);
    assert_eq!(statistics(vec![0]).unwrap().n90, None);
    assert!(statistics(vec![-1]).is_err());
    assert!(statistics(vec![i64::MAX, 1]).is_err());
}

#[test]
fn light_package_statistics_and_names_survive_reopen_and_reset() {
    let (_dir, path) = fixture();
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.datasets.len(), 1);
    assert!(!catalog.datasets[0].fasta_available);
    assert_eq!(catalog.datasets[0].statistics.total_length_bp, 100);
    let mut request = update();
    request.display_name = Some(" 我的组装 ".into());
    request.note = Some("第一行\n第二行 <script>".into());
    update_project_catalog(&path, &request).unwrap();
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.datasets[0].display_name, "我的组装");
    assert_eq!(catalog.datasets[0].original_name, "original");
    assert_eq!(catalog.datasets[0].note, "第一行\n第二行 <script>");
    let mut reset = update();
    reset.reset_name = true;
    let catalog = update_project_catalog(&path, &reset).unwrap();
    assert_eq!(catalog.datasets[0].display_name, "original");
    assert_eq!(catalog.datasets[0].note, request.note.unwrap());
    let conn = open_workspace_db(&path).unwrap();
    assert_eq!(
        conn.query_row("SELECT name FROM dataset WHERE id=1", [], |r| r
            .get::<_, String>(0))
            .unwrap(),
        "original"
    );
}

#[test]
fn annotations_are_scoped_and_invalid_edits_roll_back() {
    let (_dir, path) = fixture();
    let mut request = update();
    request.object_id = 2;
    request.note = Some("unrelated".into());
    assert!(update_project_catalog(&path, &request).is_err());
    request.object_id = 1;
    request.display_name = Some("changed".into());
    request.note = Some("x".repeat(10001));
    assert!(update_project_catalog(&path, &request).is_err());
    assert_eq!(
        list_project_catalog(&path, 1).unwrap().datasets[0].display_name,
        "original"
    );
    request.object_type = "reference".into();
    request.note = Some("reference note".into());
    update_project_catalog(&path, &request).unwrap();
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.references[0].note, "reference note");
    assert_eq!(catalog.datasets[0].note, "");
    request.note = Some("".into());
    assert_eq!(
        update_project_catalog(&path, &request).unwrap().references[0].note,
        ""
    );
}

#[test]
fn locations_check_actual_files_and_statistics_follow_dataset_contents() {
    let (dir, path) = fixture();
    let fasta = dir.path().join("partition.fa");
    std::fs::write(&fasta, ">a\nA\n").unwrap();
    let conn = open_workspace_db(&path).unwrap();
    for id in 1..=3 {
        conn.execute(
            "INSERT INTO source_seq_locator(source_seq_id,fasta_path) VALUES(?1,?2)",
            params![id, fasta.to_str().unwrap()],
        )
        .unwrap();
    }
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert!(catalog.datasets[0].fasta_available);
    assert_eq!(catalog.datasets[0].locations.len(), 1);
    conn.execute(
        "INSERT INTO source_seq(dataset_id,seq_name,seq_order,length) VALUES(1,'new',4,100)",
        [],
    )
    .unwrap();
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.datasets[0].statistics.n50, Some(100));
    assert!(!catalog.datasets[0].fasta_available);
}

#[test]
fn v3_workspace_migrates_without_changing_canonical_names() {
    let (_dir, path) = fixture();
    let conn = open_workspace_db(&path).unwrap();
    for table in ["dataset", "reference_genome"] {
        conn.execute_batch(&format!(
            "ALTER TABLE {table} DROP COLUMN display_name; ALTER TABLE {table} DROP COLUMN note;"
        ))
        .unwrap();
    }
    conn.pragma_update(None, "user_version", 3).unwrap();
    drop(conn);
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.datasets[0].display_name, "original");
    assert_eq!(catalog.references[0].note, "");
}

#[test]
fn derived_collections_have_independent_statistics_and_notes() {
    let (_dir, path) = fixture();
    let conn = open_workspace_db(&path).unwrap();
    conn.execute_batch("INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(4,2,'patch',1,25);
        INSERT INTO derived_ctg(source_seq_id,created_at) VALUES(4,'0');
        INSERT INTO derived_ctg_track_member(project_id,source_seq_id,target_dataset_id,target_chr_name,created_at)
        VALUES(1,4,1,'chr1','0');").unwrap();
    let catalog = list_project_catalog(&path, 1).unwrap();
    assert_eq!(catalog.datasets.len(), 2);
    assert_eq!(catalog.datasets[1].role, "derived");
    assert_eq!(catalog.datasets[1].statistics.total_length_bp, 25);
    assert_eq!(catalog.datasets[1].statistics.sequence_count, 1);
    let mut request = update();
    request.object_id = 2;
    request.note = Some("patch collection".into());
    let catalog = update_project_catalog(&path, &request).unwrap();
    assert_eq!(catalog.datasets[1].note, "patch collection");
    assert_eq!(catalog.datasets[0].note, "");
    conn.execute("INSERT INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,2,'support',2)", []).unwrap();
    assert_eq!(list_project_catalog(&path, 1).unwrap().datasets.len(), 2);
}
