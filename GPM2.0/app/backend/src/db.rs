use std::path::Path;

use anyhow::{Context, Result};
use rusqlite::Connection;

pub fn open_workspace_db(project_db_path: &Path) -> Result<Connection> {
    let conn = Connection::open(project_db_path).with_context(|| {
        format!(
            "failed to open workspace db at {}",
            project_db_path.display()
        )
    })?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")
        .context("failed to enable sqlite foreign keys")?;
    init_workspace_schema(&conn)?;
    Ok(conn)
}

pub fn init_workspace_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS reference_genome (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            species_name TEXT NOT NULL,
            assembly_label TEXT NOT NULL,
            fasta_path TEXT NOT NULL,
            fai_path TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reference_chr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_genome_id INTEGER NOT NULL,
            chr_name TEXT NOT NULL,
            chr_order INTEGER NOT NULL,
            length INTEGER NOT NULL,
            UNIQUE(reference_genome_id, chr_name),
            FOREIGN KEY(reference_genome_id) REFERENCES reference_genome(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            assembler TEXT NOT NULL,
            assembler_version TEXT,
            fasta_path TEXT NOT NULL,
            fai_path TEXT NOT NULL,
            self_alignment_available INTEGER NOT NULL DEFAULT 1,
            contig_count INTEGER NOT NULL DEFAULT 0,
            total_length_bp INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS workspace_package_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            package_mode TEXT NOT NULL DEFAULT 'fast',
            sequence_layout TEXT NOT NULL DEFAULT 'partitioned',
            preassigned_chr INTEGER NOT NULL DEFAULT 1,
            chr_assignment_min_coverage_percent REAL NOT NULL DEFAULT 60.0,
            self_alignment_scope TEXT NOT NULL DEFAULT 'chr_partition',
            cross_alignment_scope TEXT NOT NULL DEFAULT 'chr_partition'
        );

        CREATE TABLE IF NOT EXISTS source_seq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id INTEGER NOT NULL,
            seq_name TEXT NOT NULL,
            seq_order INTEGER NOT NULL,
            length INTEGER NOT NULL,
            UNIQUE(dataset_id, seq_name),
            FOREIGN KEY(dataset_id) REFERENCES dataset(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            reference_genome_id INTEGER NOT NULL,
            primary_dataset_id INTEGER NOT NULL,
            auto_pipeline_done INTEGER NOT NULL DEFAULT 0,
            auto_check_new_seq INTEGER NOT NULL DEFAULT 0,
            phased_assembly_enabled INTEGER NOT NULL DEFAULT 0,
            chr_assignment_min_coverage_percent REAL NOT NULL DEFAULT 60.0,
            description TEXT,
            created_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(reference_genome_id) REFERENCES reference_genome(id),
            FOREIGN KEY(primary_dataset_id) REFERENCES dataset(id)
        );

        CREATE INDEX IF NOT EXISTS idx_project_primary_dataset_id
            ON project(primary_dataset_id);

        CREATE TABLE IF NOT EXISTS assembly_seq (
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

        CREATE TABLE IF NOT EXISTS assembly_ctg (
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

        CREATE TABLE IF NOT EXISTS deleted_assembly_ctg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            assembly_ctg_id INTEGER NOT NULL,
            assembly_seq_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            assigned_chr_name TEXT,
            chr_order INTEGER,
            anchor_start INTEGER,
            ref_orient TEXT,
            placement_mode TEXT NOT NULL DEFAULT 'none',
            created_at TEXT NOT NULL,
            note TEXT,
            deleted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            dataset_id INTEGER NOT NULL,
            dataset_role TEXT NOT NULL CHECK(dataset_role IN ('primary', 'support')),
            display_order INTEGER NOT NULL,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
            FOREIGN KEY(dataset_id) REFERENCES dataset(id),
            UNIQUE(project_id, dataset_id)
        );

        CREATE TABLE IF NOT EXISTS ref_alignment_hit (
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
            cg_tag TEXT,
            run_name TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(dataset_id) REFERENCES dataset(id) ON DELETE CASCADE,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
            FOREIGN KEY(reference_chr_id) REFERENCES reference_chr(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS imported_chr_assignment (
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

        CREATE TABLE IF NOT EXISTS reference_chr_locator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_chr_id INTEGER NOT NULL UNIQUE,
            fasta_path TEXT NOT NULL,
            FOREIGN KEY(reference_chr_id) REFERENCES reference_chr(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_seq_locator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_seq_id INTEGER NOT NULL UNIQUE,
            fasta_path TEXT NOT NULL,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS derived_ctg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_seq_id INTEGER NOT NULL UNIQUE,
            source TEXT,
            source_fasta_name TEXT,
            source_fasta_sha256 TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS derived_ctg_track_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_seq_id INTEGER NOT NULL,
            target_dataset_id INTEGER NOT NULL,
            target_chr_name TEXT NOT NULL,
            member_role TEXT NOT NULL DEFAULT 'derived',
            created_at TEXT NOT NULL,
            UNIQUE(project_id, source_seq_id),
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
            FOREIGN KEY(target_dataset_id) REFERENCES dataset(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS telomere_rule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT NOT NULL UNIQUE,
            motif TEXT NOT NULL,
            min_repeat INTEGER NOT NULL,
            reverse_complement INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS source_seq_telomere_mark (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_seq_id INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            assigned_chr_name TEXT NOT NULL,
            motif TEXT NOT NULL,
            min_repeat INTEGER NOT NULL,
            repeat_count INTEGER NOT NULL,
            start_bp INTEGER NOT NULL,
            end_bp INTEGER NOT NULL,
            strand TEXT NOT NULL CHECK(strand IN ('+', '-')),
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
            FOREIGN KEY(rule_id) REFERENCES telomere_rule(rule_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_seq_centromere_mark (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_seq_id INTEGER NOT NULL,
            cen_id TEXT NOT NULL,
            assigned_chr_name TEXT NOT NULL,
            query_name TEXT NOT NULL,
            start_bp INTEGER NOT NULL,
            end_bp INTEGER NOT NULL,
            strand TEXT NOT NULL CHECK(strand IN ('+', '-')),
            align_length INTEGER NOT NULL,
            identity REAL NOT NULL,
            mapq INTEGER NOT NULL,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_seq_n_region (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_seq_id INTEGER NOT NULL,
            start_bp INTEGER NOT NULL,
            end_bp INTEGER NOT NULL,
            length_bp INTEGER NOT NULL,
            FOREIGN KEY(source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS export_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            export_type TEXT NOT NULL CHECK(export_type IN ('chr_fasta', 'ctg_fasta', 'chr_agp', 'ctg_agp')),
            reference_chr_id INTEGER,
            assembly_ctg_id INTEGER,
            output_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
            FOREIGN KEY(reference_chr_id) REFERENCES reference_chr(id) ON DELETE SET NULL,
            FOREIGN KEY(assembly_ctg_id) REFERENCES assembly_ctg(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS pairwise_alignment_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name TEXT NOT NULL,
            paf_path TEXT NOT NULL UNIQUE,
            query_dataset_id INTEGER NOT NULL,
            target_dataset_id INTEGER NOT NULL,
            paf_mtime_ms INTEGER NOT NULL,
            paf_size_bytes INTEGER NOT NULL,
            indexed_at TEXT NOT NULL,
            FOREIGN KEY(query_dataset_id) REFERENCES dataset(id) ON DELETE CASCADE,
            FOREIGN KEY(target_dataset_id) REFERENCES dataset(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pairwise_alignment_hit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            query_source_seq_id INTEGER NOT NULL,
            target_source_seq_id INTEGER NOT NULL,
            strand TEXT NOT NULL CHECK(strand IN ('+', '-')),
            query_start INTEGER NOT NULL,
            query_end INTEGER NOT NULL,
            target_start INTEGER NOT NULL,
            target_end INTEGER NOT NULL,
            match_length INTEGER NOT NULL,
            align_length INTEGER NOT NULL,
            mapq INTEGER NOT NULL,
            identity_pct REAL NOT NULL,
            FOREIGN KEY(run_id) REFERENCES pairwise_alignment_run(id) ON DELETE CASCADE,
            FOREIGN KEY(query_source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
            FOREIGN KEY(target_source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pairwise_alignment_scope (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            assigned_chr_name TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            query_dataset_id INTEGER NOT NULL,
            target_dataset_id INTEGER NOT NULL,
            scope_kind TEXT NOT NULL,
            source_set_hash TEXT NOT NULL,
            paf_mtime_ms INTEGER NOT NULL,
            paf_size_bytes INTEGER NOT NULL,
            built_at TEXT NOT NULL,
            UNIQUE(project_id, assigned_chr_name, run_id, source_set_hash),
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES pairwise_alignment_run(id) ON DELETE CASCADE,
            FOREIGN KEY(query_dataset_id) REFERENCES dataset(id) ON DELETE CASCADE,
            FOREIGN KEY(target_dataset_id) REFERENCES dataset(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pairwise_alignment_scoped_hit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_id INTEGER NOT NULL,
            query_source_seq_id INTEGER NOT NULL,
            target_source_seq_id INTEGER NOT NULL,
            strand TEXT NOT NULL CHECK(strand IN ('+', '-')),
            query_start INTEGER NOT NULL,
            query_end INTEGER NOT NULL,
            target_start INTEGER NOT NULL,
            target_end INTEGER NOT NULL,
            match_length INTEGER NOT NULL,
            align_length INTEGER NOT NULL,
            mapq INTEGER NOT NULL,
            identity_pct REAL NOT NULL,
            FOREIGN KEY(scope_id) REFERENCES pairwise_alignment_scope(id) ON DELETE CASCADE,
            FOREIGN KEY(query_source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE,
            FOREIGN KEY(target_source_seq_id) REFERENCES source_seq(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS runtime_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            degap_workspace_settings_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS project_assembly_view_state (
            project_id INTEGER PRIMARY KEY,
            support_dataset_id INTEGER,
            track_view_json TEXT NOT NULL DEFAULT '{}',
            support_ds_ctg_len_rules_by_chr_json TEXT NOT NULL DEFAULT '{}',
            track_scroll_state_json TEXT NOT NULL DEFAULT '{}',
            subview_track_scroll_state_json TEXT NOT NULL DEFAULT '{}',
            support_mirrored_ctgs_json TEXT NOT NULL DEFAULT '[]',
            hidden_primary_ctg_ids_json TEXT NOT NULL DEFAULT '[]',
            hidden_primary_ctg_ids_by_chr_json TEXT NOT NULL DEFAULT '{}',
            track_drag_offsets_json TEXT NOT NULL DEFAULT '[]',
            subview_track_drag_offsets_json TEXT NOT NULL DEFAULT '[]',
            subview_anchor_state_by_key_json TEXT NOT NULL DEFAULT '{}',
            final_path_view_mode TEXT NOT NULL DEFAULT 'graph',
            final_path_by_chr_json TEXT NOT NULL DEFAULT '{}',
            degap_project_state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS phased_chr_track (
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

        CREATE TABLE IF NOT EXISTS phased_chr_track_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phased_track_id INTEGER NOT NULL,
            assembly_ctg_id INTEGER NOT NULL,
            display_order INTEGER NOT NULL,
            gap_before_px INTEGER NOT NULL DEFAULT 20,
            orient TEXT NOT NULL DEFAULT '+' CHECK(orient IN ('+', '-')),
            created_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(phased_track_id) REFERENCES phased_chr_track(id) ON DELETE CASCADE,
            FOREIGN KEY(assembly_ctg_id) REFERENCES assembly_ctg(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS edit_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('editor', 'junction', 'settings', 'session')),
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_reference_chr_ref
            ON reference_chr(reference_genome_id, chr_order);
        CREATE INDEX IF NOT EXISTS idx_source_seq_dataset
            ON source_seq(dataset_id, seq_order);
        CREATE INDEX IF NOT EXISTS idx_assembly_seq_project
            ON assembly_seq(project_id);
        CREATE INDEX IF NOT EXISTS idx_assembly_ctg_project_chr
            ON assembly_ctg(project_id, assigned_chr_name, chr_order);
        CREATE INDEX IF NOT EXISTS idx_phased_chr_track_project_chr
            ON phased_chr_track(project_id, parent_chr_name, display_order);
        CREATE INDEX IF NOT EXISTS idx_phased_chr_track_item_track
            ON phased_chr_track_item(phased_track_id, display_order);
        CREATE INDEX IF NOT EXISTS idx_phased_chr_track_item_ctg
            ON phased_chr_track_item(assembly_ctg_id);
        CREATE INDEX IF NOT EXISTS idx_deleted_assembly_ctg_project_deleted
            ON deleted_assembly_ctg(project_id, deleted_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_ref_alignment_hit_source_seq
            ON ref_alignment_hit(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_ref_alignment_hit_dataset
            ON ref_alignment_hit(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_ref_alignment_hit_chr
            ON ref_alignment_hit(reference_chr_id);
        CREATE INDEX IF NOT EXISTS idx_imported_chr_assignment_source_seq
            ON imported_chr_assignment(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_imported_chr_assignment_chr
            ON imported_chr_assignment(reference_chr_id);
        CREATE INDEX IF NOT EXISTS idx_reference_chr_locator_chr
            ON reference_chr_locator(reference_chr_id);
        CREATE INDEX IF NOT EXISTS idx_source_seq_locator_source_seq
            ON source_seq_locator(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_telomere_rule_rule_id
            ON telomere_rule(rule_id);
        CREATE INDEX IF NOT EXISTS idx_source_seq_telomere_mark_source_seq
            ON source_seq_telomere_mark(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_source_seq_telomere_mark_rule
            ON source_seq_telomere_mark(rule_id);
        CREATE INDEX IF NOT EXISTS idx_source_seq_centromere_mark_source_seq
            ON source_seq_centromere_mark(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_source_seq_centromere_mark_chr
            ON source_seq_centromere_mark(assigned_chr_name);
        CREATE INDEX IF NOT EXISTS idx_source_seq_n_region_source_seq
            ON source_seq_n_region(source_seq_id);
        CREATE INDEX IF NOT EXISTS idx_export_record_project_created
            ON export_record(project_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_edit_audit_log_project_created
            ON edit_audit_log(project_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_pairwise_hit_query_target
            ON pairwise_alignment_hit(run_id, query_source_seq_id, target_source_seq_id, align_length, mapq);
        CREATE INDEX IF NOT EXISTS idx_pairwise_hit_target_query
            ON pairwise_alignment_hit(run_id, target_source_seq_id, query_source_seq_id, align_length, mapq);
        CREATE INDEX IF NOT EXISTS idx_pairwise_scope_project_chr_pair
            ON pairwise_alignment_scope(project_id, assigned_chr_name, query_dataset_id, target_dataset_id);
        CREATE INDEX IF NOT EXISTS idx_pairwise_scoped_hit_query_target
            ON pairwise_alignment_scoped_hit(scope_id, query_source_seq_id, target_source_seq_id, align_length, mapq);
        CREATE INDEX IF NOT EXISTS idx_pairwise_scoped_hit_target_query
            ON pairwise_alignment_scoped_hit(scope_id, target_source_seq_id, query_source_seq_id, align_length, mapq);
        ",
    )
    .context("failed to initialize workspace sqlite schema")?;

    ensure_column_exists(
        conn,
        "project",
        "auto_pipeline_done",
        "INTEGER NOT NULL DEFAULT 0",
    )?;
    ensure_column_exists(
        conn,
        "project",
        "auto_check_new_seq",
        "INTEGER NOT NULL DEFAULT 0",
    )?;
    ensure_column_exists(
        conn,
        "project",
        "phased_assembly_enabled",
        "INTEGER NOT NULL DEFAULT 0",
    )?;
    ensure_column_exists(
        conn,
        "project",
        "chr_assignment_min_coverage_percent",
        "REAL NOT NULL DEFAULT 60.0",
    )?;
    ensure_column_exists(conn, "project", "description", "TEXT")?;
    ensure_column_exists(
        conn,
        "runtime_settings",
        "degap_workspace_settings_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "runtime_settings",
        "updated_at",
        "TEXT NOT NULL DEFAULT '0'",
    )?;
    ensure_column_exists(conn, "runtime_settings", "note", "TEXT")?;
    ensure_column_exists(
        conn,
        "dataset",
        "self_alignment_available",
        "INTEGER NOT NULL DEFAULT 1",
    )?;
    ensure_column_exists(conn, "ref_alignment_hit", "cg_tag", "TEXT")?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "support_dataset_id",
        "INTEGER",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "track_view_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "support_ds_ctg_len_rules_by_chr_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "track_scroll_state_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "subview_track_scroll_state_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "support_mirrored_ctgs_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "hidden_primary_ctg_ids_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "hidden_primary_ctg_ids_by_chr_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "track_drag_offsets_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "subview_track_drag_offsets_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "subview_anchor_state_by_key_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "final_path_view_mode",
        "TEXT NOT NULL DEFAULT 'graph'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "final_path_by_chr_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "degap_project_state_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )?;
    ensure_column_exists(
        conn,
        "project_assembly_view_state",
        "updated_at",
        "TEXT NOT NULL DEFAULT '0'",
    )?;
    ensure_column_exists(conn, "project_assembly_view_state", "note", "TEXT")?;
    ensure_column_exists(
        conn,
        "phased_chr_track_item",
        "orient",
        "TEXT NOT NULL DEFAULT '+'",
    )?;
    backfill_phased_track_item_orient(conn)?;
    Ok(())
}

fn backfill_phased_track_item_orient(conn: &Connection) -> Result<()> {
    conn.execute(
        "UPDATE phased_chr_track_item
         SET orient = COALESCE((
             SELECT s.orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.id = phased_chr_track_item.assembly_ctg_id
               AND s.orient IN ('+', '-')
         ), '+')
         WHERE orient IS NULL OR TRIM(orient) NOT IN ('+', '-')",
        [],
    )
    .context("failed to backfill phased track item orient")?;
    Ok(())
}

fn ensure_column_exists(
    conn: &Connection,
    table_name: &str,
    column_name: &str,
    column_definition: &str,
) -> Result<()> {
    let pragma_sql = format!("PRAGMA table_info({})", table_name);
    let mut stmt = conn
        .prepare(&pragma_sql)
        .with_context(|| format!("failed to inspect table schema {}", table_name))?;
    let existing_columns = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .with_context(|| format!("failed to read table columns {}", table_name))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .with_context(|| format!("failed to collect table columns {}", table_name))?;
    if existing_columns
        .iter()
        .any(|existing| existing == column_name)
    {
        return Ok(());
    }

    let alter_sql = format!(
        "ALTER TABLE {} ADD COLUMN {} {}",
        table_name, column_name, column_definition
    );
    conn.execute_batch(&alter_sql).with_context(|| {
        format!(
            "failed to add missing column {}.{}",
            table_name, column_name
        )
    })?;
    Ok(())
}
