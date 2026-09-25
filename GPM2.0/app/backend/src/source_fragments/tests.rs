use super::*;

pub(crate) fn seed(conn: &Connection, sequence: &str, orient: &str) {
    crate::db::init_workspace_schema(conn).unwrap();
    conn.execute_batch(
        "INSERT INTO reference_genome(id,name,species_name,assembly_label,fasta_path,fai_path)
         VALUES(1,'ref','sp','v1','','');
         INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'Chr01',1,1000);
         INSERT INTO dataset(id,name,assembler,fasta_path,fai_path) VALUES(1,'primary','asm','','');
         INSERT INTO project(id,name,version,reference_genome_id,primary_dataset_id,created_at) VALUES(1,'test',1,1,1,'0');
         INSERT INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,1,'primary',1);",
    ).unwrap();
    conn.execute("INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(1,1,'scaffold',1,?1)", [sequence.len() as i64]).unwrap();
    for gap in crate::reference_segments::detect_reference_gap_intervals(sequence, 1) {
        conn.execute("INSERT INTO source_seq_n_region(source_seq_id,start_bp,end_bp,length_bp) VALUES(1,?1,?2,?3)",
            params![gap.start_bp,gap.end_bp,gap.end_bp-gap.start_bp+1]).unwrap();
    }
    conn.execute("INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at) VALUES(1,1,1,'chr:Chr01',?1,1,?2,'0')",params![orient,sequence.len() as i64]).unwrap();
    conn.execute("INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,placement_mode,created_at) VALUES(1,1,1,'scaffold@Chr01','Chr01',1,10,'auto','0')",[]).unwrap();
}

#[test]
fn all_n_runs_split_without_losing_single_base_fragments_or_source_coordinates() {
    for orient in ["+", "-"] {
        let conn = Connection::open_in_memory().unwrap();
        seed(&conn, "NACnTNNGGN", orient);
        split_new_source_instances(&conn, 1, 0).unwrap();
        let mut stmt = conn.prepare("SELECT s.source_start,s.source_end,s.orient,c.anchor_start,c.name FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id ORDER BY c.anchor_start").unwrap();
        let rows = stmt
            .query_map([], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, i64>(3)?,
                    r.get::<_, String>(4)?,
                ))
            })
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap();
        let expected = if orient == "+" {
            vec![(2, 3, 11), (5, 5, 14), (8, 9, 17)]
        } else {
            vec![(8, 9, 11), (5, 5, 15), (2, 3, 17)]
        };
        assert_eq!(
            rows.iter().map(|r| (r.0, r.1, r.3)).collect::<Vec<_>>(),
            expected
        );
        assert!(
            rows.iter()
                .all(|r| r.2 == orient && r.4.contains(&format!("[{}-{}]", r.0, r.1)))
        );
        assert_eq!(
            source_gaps(&conn, 1).unwrap(),
            vec![(1, 1), (4, 4), (6, 7), (10, 10)]
        );
        split_new_source_instances(&conn, 1, 0).unwrap();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM assembly_ctg", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            3
        );
        let ctgs =
            crate::main_view::list_chr_view_ctgs_with_connection(&conn, 1, Some("Chr01"), None)
                .unwrap();
        assert!(ctgs.iter().all(|c| c.n_regions.is_empty()));
        assert_eq!(
            ctgs.iter()
                .map(|c| c.source_fragment.as_ref().unwrap().source_start)
                .collect::<Vec<_>>(),
            expected.iter().map(|p| p.0).collect::<Vec<_>>()
        );
    }
}

#[test]
fn new_project_bootstrap_applies_partition_and_reports_fragment_counts() {
    let mut conn = Connection::open_in_memory().unwrap();
    seed(&conn, "ANnCNG", "+");
    conn.execute_batch("DELETE FROM assembly_ctg; DELETE FROM assembly_seq;")
        .unwrap();
    let result =
        crate::project_initializer::bootstrap_project_assembly_with_connection(&mut conn, 1)
            .unwrap();
    assert_eq!(result.assembly_ctg_count, 3);
    assert_eq!(result.assembly_seq_count, 3);
}

#[test]
fn all_n_sources_keep_gap_metadata_without_empty_contigs() {
    let conn = Connection::open_in_memory().unwrap();
    seed(&conn, "NnnN", "+");
    split_new_source_instances(&conn, 1, 0).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM assembly_ctg", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        0
    );
    assert_eq!(source_gaps(&conn, 1).unwrap(), vec![(1, 4)]);
    assert_eq!(
        conn.query_row("SELECT length FROM source_seq WHERE id=1", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        4
    );
}

#[test]
fn source_instance_cutoff_does_not_rewrite_existing_projects() {
    let conn = Connection::open_in_memory().unwrap();
    seed(&conn, "ANC", "+");
    split_new_source_instances(&conn, 1, 1).unwrap();
    assert_eq!(
        conn.query_row("SELECT name FROM assembly_ctg", [], |r| r
            .get::<_, String>(0))
            .unwrap(),
        "scaffold@Chr01"
    );
}

#[test]
fn clipping_respects_indels_and_does_not_invent_cross_fragment_matches() {
    // Q 1..5 -> T 1..5; Q 6..8 insertion; Q 9..13 -> T 6..10.
    let p = clip_alignment(1, 13, 1, 10, "+", Some("5M3I5M"), (9, 13), (1, 10)).unwrap();
    assert_eq!(
        p,
        vec![AlignmentSlice {
            query_start: 9,
            query_end: 13,
            target_start: 6,
            target_end: 10
        }]
    );
    assert!(
        clip_alignment(1, 13, 1, 10, "+", Some("5M3I5M"), (9, 13), (1, 5))
            .unwrap()
            .is_empty()
    );
    assert!(
        clip_alignment(1, 13, 1, 10, "+", Some("5M3I5M"), (6, 8), (1, 10))
            .unwrap()
            .is_empty()
    );
    let p = clip_alignment(1, 13, 1, 10, "-", Some("5M3I5M"), (9, 13), (1, 10)).unwrap();
    assert_eq!(
        p,
        vec![AlignmentSlice {
            query_start: 9,
            query_end: 13,
            target_start: 1,
            target_end: 5
        }]
    );
    assert!(
        clip_alignment(1, 100, 1, 100, "+", None, (1, 30), (70, 100))
            .unwrap()
            .is_empty()
    );
    assert!(
        clip_alignment(1, 100, 1, 100, "-", None, (1, 30), (1, 30))
            .unwrap()
            .is_empty()
    );
    assert!(clip_alignment(1, 13, 1, 10, "+", Some("13M"), (1, 13), (1, 10)).is_err());
}
