mod mutations;
mod snapshot;
mod types;

use std::collections::BTreeSet;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::json;

use crate::db::open_workspace_db;

use self::mutations::{inspect_delete_impact, prepare_batch_delete, prepare_editor_mutation};
use self::snapshot::{
    apply_snapshot, capture_snapshot, is_history_conflict, merge_snapshot_scopes, validate_snapshot,
};
use self::types::{
    HISTORY_CAPACITY, HISTORY_SCHEMA_VERSION, HistoryOperation, HistoryState, PreparedMutation,
};

pub use self::types::{
    MainViewDeleteImpact, MainViewHistoryMutationSummary, MainViewHistoryOperationDescriptor,
    MainViewHistoryStatus, MainViewHistoryTargetParams, RunMainViewBatchDeleteParams,
    RunMainViewEditorActionParams,
};

const HISTORY_STATE_INVALID_CODE: &str = "MAIN_VIEW_HISTORY_STATE_INVALID";

pub fn get_main_view_history_status(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
) -> Result<MainViewHistoryStatus> {
    validate_target_params(params.project_id, &params.chr_name)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn.transaction()?;
    let reference_chr_id = resolve_reference_chr_id(&tx, params.project_id, &params.chr_name)?;
    let (state, invalidated) = load_history_state(&tx, params.project_id, reference_chr_id)?;
    if invalidated {
        save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
    }
    let status = build_status(
        params.project_id,
        reference_chr_id,
        &params.chr_name,
        &state,
        invalidated,
    );
    tx.commit()?;
    Ok(status)
}

pub fn inspect_main_view_delete(
    project_db_path: &Path,
    params: &RunMainViewBatchDeleteParams,
) -> Result<MainViewDeleteImpact> {
    validate_target_params(params.project_id, &params.chr_name)?;
    let conn = open_workspace_db(project_db_path)?;
    resolve_reference_chr_id(&conn, params.project_id, &params.chr_name)?;
    inspect_delete_impact(
        &conn,
        params.project_id,
        &params.chr_name,
        &params.assembly_ctg_ids,
    )
}

pub fn run_main_view_editor_action(
    project_db_path: &Path,
    params: &RunMainViewEditorActionParams,
) -> Result<MainViewHistoryMutationSummary> {
    validate_target_params(params.project_id, &params.chr_name)?;
    let action = params.action.trim().to_ascii_lowercase();
    run_new_mutation(
        project_db_path,
        params.project_id,
        &params.chr_name,
        |conn| {
            prepare_editor_mutation(
                conn,
                params.project_id,
                &params.chr_name,
                &action,
                &params.args,
            )
        },
    )
}

pub fn run_main_view_batch_delete(
    project_db_path: &Path,
    params: &RunMainViewBatchDeleteParams,
) -> Result<MainViewHistoryMutationSummary> {
    validate_target_params(params.project_id, &params.chr_name)?;
    run_new_mutation(
        project_db_path,
        params.project_id,
        &params.chr_name,
        |conn| {
            prepare_batch_delete(
                conn,
                params.project_id,
                &params.chr_name,
                &params.assembly_ctg_ids,
            )
        },
    )
}

pub fn undo_main_view_history(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
) -> Result<MainViewHistoryMutationSummary> {
    execute_history_step(project_db_path, params, HistoryStep::Undo)
}

pub fn redo_main_view_history(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
) -> Result<MainViewHistoryMutationSummary> {
    execute_history_step(project_db_path, params, HistoryStep::Redo)
}

pub fn reset_main_view_history(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
) -> Result<MainViewHistoryMutationSummary> {
    validate_target_params(params.project_id, &params.chr_name)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let transaction_result = (|| -> Result<MainViewHistoryMutationSummary> {
        let tx = conn.transaction()?;
        let reference_chr_id = resolve_reference_chr_id(&tx, params.project_id, &params.chr_name)?;
        let (mut state, malformed) = load_history_state(&tx, params.project_id, reference_chr_id)?;
        if malformed {
            save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
            let summary = unchanged_summary(
                params.project_id,
                reference_chr_id,
                &params.chr_name,
                &state,
                true,
            );
            tx.commit()?;
            return Ok(summary);
        }
        validate_cursor(&tx, params.project_id, &state)?;
        if state.active_operation_ids.is_empty() {
            let summary = unchanged_summary(
                params.project_id,
                reference_chr_id,
                &params.chr_name,
                &state,
                false,
            );
            tx.commit()?;
            return Ok(summary);
        }

        let active_operations = resolve_active_operations(&state)?;
        let aggregate_scope = merge_snapshot_scopes(
            active_operations
                .iter()
                .flat_map(|operation| [&operation.before, &operation.after]),
        );
        let before = capture_snapshot(&tx, params.project_id, &aggregate_scope)?;
        for operation in active_operations.iter().rev() {
            apply_snapshot(&tx, params.project_id, &operation.after, &operation.before)?;
        }
        let after = capture_snapshot(&tx, params.project_id, &aggregate_scope)?;

        let logical_id = take_next_logical_id(&mut state)?;
        let before_active_ids = state.active_operation_ids.clone();
        let affected_ctg_ids = collect_ids(
            active_operations
                .iter()
                .flat_map(|operation| operation.affected_ctg_ids.iter().copied()),
        );
        let affected_seq_ids = collect_ids(
            active_operations
                .iter()
                .flat_map(|operation| operation.affected_seq_ids.iter().copied()),
        );
        let descriptor = MainViewHistoryOperationDescriptor {
            kind: "reset".to_string(),
            target_count: before_active_ids.len() as i64,
            target_name: Some(params.chr_name.clone()),
        };
        state.future.clear();
        state.past.push(HistoryOperation {
            logical_id,
            descriptor: descriptor.clone(),
            before,
            after,
            before_active_ids,
            after_active_ids: Vec::new(),
            affected_ctg_ids: affected_ctg_ids.clone(),
            affected_seq_ids: affected_seq_ids.clone(),
        });
        state.active_operation_ids.clear();
        prune_history(&mut state);
        save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
        append_history_audit(
            &tx,
            params.project_id,
            "history-reset",
            logical_id,
            &descriptor,
        )?;
        let status = build_status(
            params.project_id,
            reference_chr_id,
            &params.chr_name,
            &state,
            false,
        );
        tx.commit()?;
        Ok(MainViewHistoryMutationSummary {
            changed: true,
            invalidated: false,
            affected_ctg_ids,
            affected_seq_ids,
            descriptor: Some(descriptor),
            status,
        })
    })();
    handle_conflict_result(project_db_path, params, transaction_result)
}

fn run_new_mutation<F>(
    project_db_path: &Path,
    project_id: i64,
    chr_name: &str,
    prepare: F,
) -> Result<MainViewHistoryMutationSummary>
where
    F: FnOnce(&Connection) -> Result<PreparedMutation>,
{
    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn.transaction()?;
    let reference_chr_id = resolve_reference_chr_id(&tx, project_id, chr_name)?;
    let (mut state, malformed) = load_history_state(&tx, project_id, reference_chr_id)?;
    let cursor_invalid = !malformed && validate_cursor(&tx, project_id, &state).is_err();
    let invalidated = malformed || cursor_invalid;
    if invalidated {
        state = HistoryState::default();
    }

    let prepared = prepare(&tx)?;
    if !prepared.changed {
        if invalidated {
            save_history_state(&tx, project_id, reference_chr_id, &state)?;
        }
        let summary =
            unchanged_summary(project_id, reference_chr_id, chr_name, &state, invalidated);
        tx.commit()?;
        return Ok(summary);
    }

    state.future.clear();
    let logical_id = take_next_logical_id(&mut state)?;
    let before_active_ids = state.active_operation_ids.clone();
    let mut after_active_ids = before_active_ids.clone();
    after_active_ids.push(logical_id);
    state.past.push(HistoryOperation {
        logical_id,
        descriptor: prepared.descriptor.clone(),
        before: prepared.before,
        after: prepared.after,
        before_active_ids,
        after_active_ids: after_active_ids.clone(),
        affected_ctg_ids: prepared.affected_ctg_ids.clone(),
        affected_seq_ids: prepared.affected_seq_ids.clone(),
    });
    state.active_operation_ids = after_active_ids;
    prune_history(&mut state);
    save_history_state(&tx, project_id, reference_chr_id, &state)?;
    append_history_audit(
        &tx,
        project_id,
        &prepared.descriptor.kind,
        logical_id,
        &prepared.descriptor,
    )?;
    let status = build_status(project_id, reference_chr_id, chr_name, &state, invalidated);
    tx.commit()?;
    Ok(MainViewHistoryMutationSummary {
        changed: true,
        invalidated,
        affected_ctg_ids: prepared.affected_ctg_ids,
        affected_seq_ids: prepared.affected_seq_ids,
        descriptor: Some(prepared.descriptor),
        status,
    })
}

#[derive(Debug, Clone, Copy)]
enum HistoryStep {
    Undo,
    Redo,
}

fn execute_history_step(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
    step: HistoryStep,
) -> Result<MainViewHistoryMutationSummary> {
    validate_target_params(params.project_id, &params.chr_name)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let transaction_result = (|| -> Result<MainViewHistoryMutationSummary> {
        let tx = conn.transaction()?;
        let reference_chr_id = resolve_reference_chr_id(&tx, params.project_id, &params.chr_name)?;
        let (mut state, malformed) = load_history_state(&tx, params.project_id, reference_chr_id)?;
        if malformed {
            save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
            let summary = unchanged_summary(
                params.project_id,
                reference_chr_id,
                &params.chr_name,
                &state,
                true,
            );
            tx.commit()?;
            return Ok(summary);
        }
        let operation = match step {
            HistoryStep::Undo => state.past.last().cloned(),
            HistoryStep::Redo => state.future.last().cloned(),
        };
        let Some(operation) = operation else {
            let summary = unchanged_summary(
                params.project_id,
                reference_chr_id,
                &params.chr_name,
                &state,
                false,
            );
            tx.commit()?;
            return Ok(summary);
        };

        match step {
            HistoryStep::Undo => {
                apply_snapshot(&tx, params.project_id, &operation.after, &operation.before)?
            }
            HistoryStep::Redo => {
                apply_snapshot(&tx, params.project_id, &operation.before, &operation.after)?
            }
        }
        let audit_action = match step {
            HistoryStep::Undo => {
                state.past.pop();
                state.future.push(operation.clone());
                state.active_operation_ids = operation.before_active_ids.clone();
                "history-undo"
            }
            HistoryStep::Redo => {
                state.future.pop();
                state.past.push(operation.clone());
                state.active_operation_ids = operation.after_active_ids.clone();
                "history-redo"
            }
        };
        save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
        append_history_audit(
            &tx,
            params.project_id,
            audit_action,
            operation.logical_id,
            &operation.descriptor,
        )?;
        let status = build_status(
            params.project_id,
            reference_chr_id,
            &params.chr_name,
            &state,
            false,
        );
        tx.commit()?;
        Ok(MainViewHistoryMutationSummary {
            changed: true,
            invalidated: false,
            affected_ctg_ids: operation.affected_ctg_ids,
            affected_seq_ids: operation.affected_seq_ids,
            descriptor: Some(operation.descriptor),
            status,
        })
    })();
    handle_conflict_result(project_db_path, params, transaction_result)
}

fn handle_conflict_result(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
    result: Result<MainViewHistoryMutationSummary>,
) -> Result<MainViewHistoryMutationSummary> {
    match result {
        Ok(summary) => Ok(summary),
        Err(error) if is_history_conflict(&error) => {
            invalidate_chr_history(project_db_path, params, &error)
        }
        Err(error) => Err(error),
    }
}

fn invalidate_chr_history(
    project_db_path: &Path,
    params: &MainViewHistoryTargetParams,
    cause: &anyhow::Error,
) -> Result<MainViewHistoryMutationSummary> {
    let mut conn = open_workspace_db(project_db_path)?;
    let tx = conn.transaction()?;
    let reference_chr_id = resolve_reference_chr_id(&tx, params.project_id, &params.chr_name)?;
    let state = HistoryState::default();
    save_history_state(&tx, params.project_id, reference_chr_id, &state)?;
    let detail = json!({
        "schemaVersion": HISTORY_SCHEMA_VERSION,
        "chrName": params.chr_name,
        "reason": format!("{cause:#}"),
    });
    tx.execute(
        "INSERT INTO edit_audit_log (project_id, category, action, detail, created_at)
         VALUES (?1, 'editor', 'history-invalidated', ?2, ?3)",
        params![
            params.project_id,
            detail.to_string(),
            now_timestamp_string()
        ],
    )?;
    let summary = unchanged_summary(
        params.project_id,
        reference_chr_id,
        &params.chr_name,
        &state,
        true,
    );
    tx.commit()?;
    Ok(summary)
}

fn validate_cursor(conn: &Connection, project_id: i64, state: &HistoryState) -> Result<()> {
    if let Some(operation) = state.past.last() {
        validate_snapshot(conn, project_id, &operation.after)
    } else if let Some(operation) = state.future.last() {
        validate_snapshot(conn, project_id, &operation.before)
    } else {
        Ok(())
    }
}

fn resolve_active_operations(state: &HistoryState) -> Result<Vec<HistoryOperation>> {
    state
        .active_operation_ids
        .iter()
        .map(|logical_id| {
            state
                .past
                .iter()
                .find(|operation| operation.logical_id == *logical_id)
                .cloned()
                .ok_or_else(|| {
                    anyhow!(
                        "{HISTORY_STATE_INVALID_CODE}: active operation {logical_id} is not retained"
                    )
                })
        })
        .collect()
}

fn load_history_state(
    conn: &Connection,
    project_id: i64,
    reference_chr_id: i64,
) -> Result<(HistoryState, bool)> {
    let state_json: Option<String> = conn
        .query_row(
            "SELECT state_json FROM project_main_view_history
             WHERE project_id = ?1 AND reference_chr_id = ?2",
            params![project_id, reference_chr_id],
            |row| row.get(0),
        )
        .optional()?;
    let Some(state_json) = state_json else {
        return Ok((HistoryState::default(), false));
    };
    let Ok(state) = serde_json::from_str::<HistoryState>(&state_json) else {
        return Ok((HistoryState::default(), true));
    };
    if !is_valid_history_state(&state) {
        return Ok((HistoryState::default(), true));
    }
    Ok((state, false))
}

fn is_valid_history_state(state: &HistoryState) -> bool {
    if state.version != HISTORY_SCHEMA_VERSION
        || state.next_logical_id == 0
        || state.past.len() + state.future.len() > HISTORY_CAPACITY
    {
        return false;
    }
    let retained = state
        .past
        .iter()
        .chain(state.future.iter())
        .map(|operation| operation.logical_id)
        .collect::<BTreeSet<_>>();
    state
        .active_operation_ids
        .iter()
        .all(|logical_id| retained.contains(logical_id))
}

fn save_history_state(
    conn: &Connection,
    project_id: i64,
    reference_chr_id: i64,
    state: &HistoryState,
) -> Result<()> {
    let state_json = serde_json::to_string(state)?;
    conn.execute(
        "INSERT INTO project_main_view_history (
            project_id, reference_chr_id, state_json, updated_at
         ) VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(project_id, reference_chr_id) DO UPDATE SET
            state_json = excluded.state_json,
            updated_at = excluded.updated_at",
        params![
            project_id,
            reference_chr_id,
            state_json,
            now_timestamp_string(),
        ],
    )
    .context("failed to persist main-view history state")?;
    Ok(())
}

fn resolve_reference_chr_id(conn: &Connection, project_id: i64, chr_name: &str) -> Result<i64> {
    conn.query_row(
        "SELECT rc.id
         FROM project p
         JOIN reference_chr rc ON rc.reference_genome_id = p.reference_genome_id
         WHERE p.id = ?1 AND rc.chr_name = ?2",
        params![project_id, chr_name],
        |row| row.get(0),
    )
    .optional()?
    .ok_or_else(|| {
        anyhow!(
            "MAIN_VIEW_HISTORY_CHR_NOT_FOUND: chromosome '{chr_name}' does not exist in project_id {project_id}"
        )
    })
}

fn validate_target_params(project_id: i64, chr_name: &str) -> Result<()> {
    if project_id <= 0 {
        bail!("MAIN_VIEW_HISTORY_INVALID_REQUEST: project_id must be > 0");
    }
    if chr_name.trim().is_empty() || chr_name.trim().eq_ignore_ascii_case("unplaced") {
        bail!("MAIN_VIEW_HISTORY_INVALID_REQUEST: a formal chromosome is required");
    }
    Ok(())
}

fn take_next_logical_id(state: &mut HistoryState) -> Result<u64> {
    let logical_id = state.next_logical_id;
    state.next_logical_id = logical_id.checked_add(1).ok_or_else(|| {
        anyhow!("{HISTORY_STATE_INVALID_CODE}: logical operation id space is exhausted")
    })?;
    Ok(logical_id)
}

fn prune_history(state: &mut HistoryState) {
    let mut removed_ids = BTreeSet::new();
    while state.past.len() + state.future.len() > HISTORY_CAPACITY {
        if !state.past.is_empty() {
            removed_ids.insert(state.past.remove(0).logical_id);
        } else if !state.future.is_empty() {
            removed_ids.insert(state.future.remove(0).logical_id);
        }
    }
    if removed_ids.is_empty() {
        return;
    }
    state
        .active_operation_ids
        .retain(|logical_id| !removed_ids.contains(logical_id));
    for operation in state.past.iter_mut().chain(state.future.iter_mut()) {
        operation
            .before_active_ids
            .retain(|logical_id| !removed_ids.contains(logical_id));
        operation
            .after_active_ids
            .retain(|logical_id| !removed_ids.contains(logical_id));
    }
}

fn build_status(
    project_id: i64,
    reference_chr_id: i64,
    chr_name: &str,
    state: &HistoryState,
    invalidated: bool,
) -> MainViewHistoryStatus {
    MainViewHistoryStatus {
        project_id,
        reference_chr_id,
        chr_name: chr_name.to_string(),
        can_undo: !state.past.is_empty(),
        can_redo: !state.future.is_empty(),
        can_reset: !state.active_operation_ids.is_empty(),
        undo_operation: state
            .past
            .last()
            .map(|operation| operation.descriptor.clone()),
        redo_operation: state
            .future
            .last()
            .map(|operation| operation.descriptor.clone()),
        applied_operation_count: state.active_operation_ids.len() as i64,
        retained_operation_count: (state.past.len() + state.future.len()) as i64,
        invalidated,
    }
}

fn unchanged_summary(
    project_id: i64,
    reference_chr_id: i64,
    chr_name: &str,
    state: &HistoryState,
    invalidated: bool,
) -> MainViewHistoryMutationSummary {
    MainViewHistoryMutationSummary {
        changed: false,
        invalidated,
        affected_ctg_ids: Vec::new(),
        affected_seq_ids: Vec::new(),
        descriptor: None,
        status: build_status(project_id, reference_chr_id, chr_name, state, invalidated),
    }
}

fn append_history_audit(
    conn: &Connection,
    project_id: i64,
    action: &str,
    logical_id: u64,
    descriptor: &MainViewHistoryOperationDescriptor,
) -> Result<()> {
    let detail = json!({
        "historySchemaVersion": HISTORY_SCHEMA_VERSION,
        "historyOperationId": logical_id,
        "operation": descriptor,
    });
    conn.execute(
        "INSERT INTO edit_audit_log (project_id, category, action, detail, created_at)
         VALUES (?1, 'editor', ?2, ?3, ?4)",
        params![
            project_id,
            action,
            detail.to_string(),
            now_timestamp_string()
        ],
    )?;
    Ok(())
}

fn collect_ids(values: impl IntoIterator<Item = i64>) -> Vec<i64> {
    values
        .into_iter()
        .filter(|value| *value > 0)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn now_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
        .to_string()
}

#[cfg(test)]
mod tests;
