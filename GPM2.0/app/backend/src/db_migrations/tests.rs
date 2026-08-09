use super::*;

type RequiredColumn = (String, String, String, bool, i64);

#[test]
fn fresh_database_initializes_at_current_version() -> Result<()> {
    let conn = Connection::open_in_memory()?;

    super::migrate_workspace_schema(&conn)?;

    assert_eq!(user_version(&conn)?, CURRENT_SCHEMA_VERSION);
    assert!(table_exists(&conn, "project")?);
    assert!(column_exists(
        &conn,
        "imported_chr_assignment",
        "source_orientation"
    )?);
    assert!(column_exists(
        &conn,
        "project_assembly_view_state",
        "subview_anchor_state_by_key_json"
    )?);
    Ok(())
}

#[test]
fn unversioned_legacy_database_migrates_without_losing_data() -> Result<()> {
    let conn = legacy_fixture()?;

    super::migrate_workspace_schema(&conn)?;

    assert_eq!(user_version(&conn)?, CURRENT_SCHEMA_VERSION);
    assert_eq!(
        conn.query_row("SELECT name FROM project WHERE id = 1", [], |row| row
            .get::<_, String>(0))?,
        "legacy_project"
    );
    assert_eq!(
        conn.query_row(
            "SELECT track_view_json FROM project_assembly_view_state WHERE project_id = 1",
            [],
            |row| row.get::<_, String>(0)
        )?,
        "{\"legacy\":true}"
    );
    assert_eq!(
        conn.query_row(
            "SELECT orient FROM phased_chr_track_item WHERE id = 1",
            [],
            |row| row.get::<_, String>(0)
        )?,
        "-"
    );
    assert_eq!(
        conn.query_row(
            "SELECT source_orientation || ':' || orientation_source
             FROM imported_chr_assignment WHERE source_seq_id = 1",
            [],
            |row| row.get::<_, String>(0)
        )?,
        "-:ref_alignment"
    );
    assert!(table_exists(&conn, "grt_package")?);
    Ok(())
}

#[test]
fn fresh_and_legacy_databases_reach_the_same_required_schema() -> Result<()> {
    let fresh = Connection::open_in_memory()?;
    super::migrate_workspace_schema(&fresh)?;
    let legacy = legacy_fixture()?;
    super::migrate_workspace_schema(&legacy)?;

    assert_eq!(
        required_schema_signature(&legacy)?,
        required_schema_signature(&fresh)?
    );
    Ok(())
}

#[test]
fn partially_existing_legacy_columns_are_preserved() -> Result<()> {
    let conn = legacy_fixture()?;
    conn.execute_batch(
        "ALTER TABLE project ADD COLUMN auto_pipeline_done INTEGER NOT NULL DEFAULT 0;
         UPDATE project SET auto_pipeline_done = 1;
         ALTER TABLE project_assembly_view_state ADD COLUMN support_dataset_id INTEGER;
         UPDATE project_assembly_view_state SET support_dataset_id = 17;
         ALTER TABLE imported_chr_assignment ADD COLUMN source_orientation
             TEXT NOT NULL DEFAULT '+' CHECK(source_orientation IN ('+', '-'));
         UPDATE imported_chr_assignment SET source_orientation = '-';",
    )?;

    super::migrate_workspace_schema(&conn)?;

    assert_eq!(
        conn.query_row(
            "SELECT auto_pipeline_done FROM project WHERE id = 1",
            [],
            |row| row.get::<_, i64>(0)
        )?,
        1
    );
    assert_eq!(
        conn.query_row(
            "SELECT support_dataset_id FROM project_assembly_view_state WHERE project_id = 1",
            [],
            |row| row.get::<_, i64>(0)
        )?,
        17
    );
    assert_eq!(
        conn.query_row(
            "SELECT source_orientation FROM imported_chr_assignment WHERE source_seq_id = 1",
            [],
            |row| row.get::<_, String>(0)
        )?,
        "-"
    );
    Ok(())
}

#[test]
fn reopening_current_database_is_idempotent() -> Result<()> {
    let conn = Connection::open_in_memory()?;
    super::migrate_workspace_schema(&conn)?;
    let schema_version_before = sqlite_schema_version(&conn)?;

    super::migrate_workspace_schema(&conn)?;

    assert_eq!(user_version(&conn)?, CURRENT_SCHEMA_VERSION);
    assert_eq!(sqlite_schema_version(&conn)?, schema_version_before);
    Ok(())
}

#[test]
fn future_database_version_is_rejected_without_mutation() -> Result<()> {
    let conn = Connection::open_in_memory()?;
    set_user_version(&conn, CURRENT_SCHEMA_VERSION + 1)?;

    let error = super::migrate_workspace_schema(&conn).expect_err("future version must fail");

    assert!(format!("{error:#}").contains(FUTURE_VERSION_ERROR));
    assert_eq!(user_version(&conn)?, CURRENT_SCHEMA_VERSION + 1);
    assert!(!database_has_user_tables(&conn)?);
    Ok(())
}

#[test]
fn migration_failure_rolls_back_schema_and_version() -> Result<()> {
    let conn = Connection::open_in_memory()?;
    conn.execute_batch("CREATE TABLE preserved (value TEXT NOT NULL);")?;
    let migrations = [Migration {
        version: 1,
        name: "injected_failure",
        apply: failing_migration,
    }];

    let error = apply_pending_migrations(&conn, 0, &migrations, 1)
        .expect_err("injected migration must fail");

    assert!(format!("{error:#}").contains(MIGRATION_FAILED_ERROR));
    assert_eq!(user_version(&conn)?, 0);
    assert!(!table_exists(&conn, "must_rollback")?);
    assert!(table_exists(&conn, "preserved")?);
    Ok(())
}

#[test]
fn ordered_migrations_apply_step_by_step() -> Result<()> {
    let conn = Connection::open_in_memory()?;
    let migrations = [
        Migration {
            version: 1,
            name: "create_chain",
            apply: synthetic_migration_v1,
        },
        Migration {
            version: 2,
            name: "extend_chain",
            apply: synthetic_migration_v2,
        },
    ];

    apply_pending_migrations(&conn, 0, &migrations, 2)?;

    assert_eq!(user_version(&conn)?, 2);
    assert_eq!(
        conn.query_row("SELECT detail FROM migration_chain", [], |row| row
            .get::<_, String>(0))?,
        "v2"
    );
    Ok(())
}

#[test]
fn real_open_path_reopens_migrated_workspace() -> Result<()> {
    let temp_dir = tempfile::tempdir()?;
    let db_path = temp_dir.path().join("project.sqlite");
    {
        let conn = super::super::open_workspace_db(&db_path)?;
        conn.execute_batch(
            "CREATE TABLE caller_owned_marker (value TEXT NOT NULL);
             INSERT INTO caller_owned_marker (value) VALUES ('preserved');",
        )?;
    }

    let conn = super::super::open_workspace_db(&db_path)?;

    assert_eq!(user_version(&conn)?, CURRENT_SCHEMA_VERSION);
    assert_eq!(
        conn.query_row("SELECT value FROM caller_owned_marker", [], |row| row
            .get::<_, String>(0))?,
        "preserved"
    );
    Ok(())
}

#[test]
fn production_migration_registry_is_contiguous() -> Result<()> {
    validate_migration_registry()
}

fn failing_migration(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE must_rollback (value TEXT NOT NULL);
         INSERT INTO must_rollback (value) VALUES ('transient');",
    )?;
    anyhow::bail!("injected failure")
}

fn synthetic_migration_v1(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE migration_chain (
             id INTEGER PRIMARY KEY CHECK (id = 1),
             detail TEXT NOT NULL
         );
         INSERT INTO migration_chain (id, detail) VALUES (1, 'v1');",
    )?;
    Ok(())
}

fn synthetic_migration_v2(conn: &Connection) -> Result<()> {
    conn.execute("UPDATE migration_chain SET detail = 'v2' WHERE id = 1", [])?;
    Ok(())
}

fn legacy_fixture() -> Result<Connection> {
    let conn = Connection::open_in_memory()?;
    conn.execute_batch(LEGACY_SCHEMA_FIXTURE)?;
    Ok(conn)
}

fn table_exists(conn: &Connection, table: &str) -> Result<bool> {
    conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?1)",
        [table],
        |row| row.get::<_, bool>(0),
    )
    .context("failed to inspect fixture table")
}

fn column_exists(conn: &Connection, table: &str, column: &str) -> Result<bool> {
    let mut statement = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let columns = statement
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(columns.iter().any(|existing| existing == column))
}

fn sqlite_schema_version(conn: &Connection) -> Result<i64> {
    conn.query_row("PRAGMA schema_version", [], |row| row.get(0))
        .context("failed to read sqlite schema_version")
}

fn required_schema_signature(conn: &Connection) -> Result<Vec<RequiredColumn>> {
    let mut table_statement = conn.prepare(
        "SELECT name
         FROM sqlite_schema
         WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
         ORDER BY name",
    )?;
    let table_names = table_statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut signature = Vec::new();
    for table_name in table_names {
        let quoted_table = table_name.replace('"', "\"\"");
        let mut statement = conn.prepare(&format!("PRAGMA table_info(\"{quoted_table}\")"))?;
        let columns = statement.query_map([], |row| {
            Ok((
                table_name.clone(),
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, bool>(3)?,
                row.get::<_, i64>(5)?,
            ))
        })?;
        signature.extend(columns.collect::<std::result::Result<Vec<_>, _>>()?);
    }
    signature.sort();
    Ok(signature)
}

const LEGACY_SCHEMA_FIXTURE: &str = r#"
    PRAGMA foreign_keys = ON;
    CREATE TABLE reference_genome (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        species_name TEXT NOT NULL,
        assembly_label TEXT NOT NULL,
        fasta_path TEXT NOT NULL,
        fai_path TEXT NOT NULL
    );
    CREATE TABLE reference_chr (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_genome_id INTEGER NOT NULL,
        chr_name TEXT NOT NULL,
        chr_order INTEGER NOT NULL,
        length INTEGER NOT NULL,
        UNIQUE(reference_genome_id, chr_name),
        FOREIGN KEY(reference_genome_id) REFERENCES reference_genome(id) ON DELETE CASCADE
    );
    CREATE TABLE dataset (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        assembler TEXT NOT NULL,
        assembler_version TEXT,
        fasta_path TEXT NOT NULL,
        fai_path TEXT NOT NULL,
        contig_count INTEGER NOT NULL DEFAULT 0,
        total_length_bp INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE source_seq (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER NOT NULL,
        seq_name TEXT NOT NULL,
        seq_order INTEGER NOT NULL,
        length INTEGER NOT NULL,
        UNIQUE(dataset_id, seq_name),
        FOREIGN KEY(dataset_id) REFERENCES dataset(id) ON DELETE CASCADE
    );
    CREATE TABLE project (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version INTEGER NOT NULL,
        reference_genome_id INTEGER NOT NULL,
        primary_dataset_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(reference_genome_id) REFERENCES reference_genome(id),
        FOREIGN KEY(primary_dataset_id) REFERENCES dataset(id)
    );
    CREATE TABLE assembly_seq (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        source_seq_id INTEGER NOT NULL,
        instance_key TEXT NOT NULL DEFAULT '',
        orient TEXT NOT NULL DEFAULT '+',
        source_start INTEGER NOT NULL DEFAULT 1,
        source_end INTEGER NOT NULL,
        left_end_type TEXT NOT NULL DEFAULT 'normal',
        right_end_type TEXT NOT NULL DEFAULT 'normal',
        hidden INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        note TEXT,
        UNIQUE(project_id, source_seq_id, instance_key),
        FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
        FOREIGN KEY(source_seq_id) REFERENCES source_seq(id)
    );
    CREATE TABLE assembly_ctg (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        assembly_seq_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        assigned_chr_name TEXT,
        chr_order INTEGER,
        anchor_start INTEGER,
        ref_orient TEXT,
        placement_mode TEXT NOT NULL DEFAULT 'none',
        created_at TEXT NOT NULL,
        note TEXT,
        UNIQUE(project_id, name),
        UNIQUE(project_id, assembly_seq_id),
        FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
        FOREIGN KEY(assembly_seq_id) REFERENCES assembly_seq(id) ON DELETE CASCADE
    );
    CREATE TABLE ref_alignment_hit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER NOT NULL,
        source_seq_id INTEGER NOT NULL,
        reference_chr_id INTEGER NOT NULL,
        strand TEXT NOT NULL CHECK(strand IN ('+', '-')),
        query_start INTEGER NOT NULL,
        query_end INTEGER NOT NULL,
        ref_start INTEGER NOT NULL,
        ref_end INTEGER NOT NULL,
        match_length INTEGER NOT NULL,
        block_length INTEGER NOT NULL,
        mapq INTEGER NOT NULL,
        run_name TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(dataset_id) REFERENCES dataset(id) ON DELETE CASCADE,
        FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
        FOREIGN KEY(reference_chr_id) REFERENCES reference_chr(id) ON DELETE CASCADE
    );
    CREATE TABLE imported_chr_assignment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_seq_id INTEGER NOT NULL,
        reference_chr_id INTEGER NOT NULL,
        support_bp INTEGER NOT NULL,
        support_percent REAL NOT NULL,
        anchor_start INTEGER NOT NULL,
        UNIQUE(source_seq_id, reference_chr_id),
        FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
        FOREIGN KEY(reference_chr_id) REFERENCES reference_chr(id) ON DELETE CASCADE
    );
    CREATE TABLE runtime_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1)
    );
    CREATE TABLE project_assembly_view_state (
        project_id INTEGER PRIMARY KEY,
        track_view_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
    );
    CREATE TABLE phased_chr_track (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        parent_chr_name TEXT NOT NULL,
        haplotype_key TEXT NOT NULL,
        label TEXT NOT NULL,
        display_order INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        note TEXT,
        UNIQUE(project_id, parent_chr_name, haplotype_key),
        FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
    );
    CREATE TABLE phased_chr_track_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phased_track_id INTEGER NOT NULL,
        assembly_ctg_id INTEGER NOT NULL,
        display_order INTEGER NOT NULL,
        gap_before_px INTEGER NOT NULL DEFAULT 20,
        created_at TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(phased_track_id) REFERENCES phased_chr_track(id) ON DELETE CASCADE,
        FOREIGN KEY(assembly_ctg_id) REFERENCES assembly_ctg(id) ON DELETE CASCADE
    );

    INSERT INTO reference_genome
        (id, name, species_name, assembly_label, fasta_path, fai_path)
        VALUES (1, 'ref', 'rice', 'v1', 'ref.fa', 'ref.fa.fai');
    INSERT INTO reference_chr
        (id, reference_genome_id, chr_name, chr_order, length)
        VALUES (1, 1, 'Chr01', 1, 1000);
    INSERT INTO dataset
        (id, name, assembler, fasta_path, fai_path, contig_count, total_length_bp)
        VALUES (1, 'legacy_ds', 'legacy', 'ds.fa', 'ds.fa.fai', 1, 100);
    INSERT INTO source_seq
        (id, dataset_id, seq_name, seq_order, length)
        VALUES (1, 1, 'ctg1', 1, 100);
    INSERT INTO project
        (id, name, version, reference_genome_id, primary_dataset_id, created_at)
        VALUES (1, 'legacy_project', 1, 1, 1, 'legacy-time');
    INSERT INTO assembly_seq
        (id, project_id, source_seq_id, orient, source_end, created_at)
        VALUES (1, 1, 1, '-', 100, 'legacy-time');
    INSERT INTO assembly_ctg
        (id, project_id, assembly_seq_id, name, created_at)
        VALUES (1, 1, 1, 'ctg1', 'legacy-time');
    INSERT INTO ref_alignment_hit
        (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end,
         ref_start, ref_end, match_length, block_length, mapq, run_name)
        VALUES (1, 1, 1, '+', 0, 40, 10, 50, 38, 40, 60, 'legacy_plus');
    INSERT INTO ref_alignment_hit
        (dataset_id, source_seq_id, reference_chr_id, strand, query_start, query_end,
         ref_start, ref_end, match_length, block_length, mapq, run_name)
        VALUES (1, 1, 1, '-', 40, 100, 50, 110, 58, 60, 60, 'legacy_minus');
    INSERT INTO imported_chr_assignment
        (source_seq_id, reference_chr_id, support_bp, support_percent, anchor_start)
        VALUES (1, 1, 100, 100.0, 10);
    INSERT INTO runtime_settings (id) VALUES (1);
    INSERT INTO project_assembly_view_state (project_id, track_view_json)
        VALUES (1, '{"legacy":true}');
    INSERT INTO phased_chr_track
        (id, project_id, parent_chr_name, haplotype_key, label, display_order, created_at)
        VALUES (1, 1, 'Chr01', 'a', 'A', 1, 'legacy-time');
    INSERT INTO phased_chr_track_item
        (id, phased_track_id, assembly_ctg_id, display_order, created_at)
        VALUES (1, 1, 1, 1, 'legacy-time');
"#;
