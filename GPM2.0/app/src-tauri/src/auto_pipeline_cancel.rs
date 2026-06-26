use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

static CANCELLED_RUNS: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();

fn cancelled_runs() -> &'static Mutex<HashSet<String>> {
    CANCELLED_RUNS.get_or_init(|| Mutex::new(HashSet::new()))
}

fn make_key(workspace_root: &str, project_id: i64, run_id: &str) -> String {
    format!("{}::{}::{}", workspace_root, project_id, run_id)
}

pub fn request_cancel(workspace_root: &str, project_id: i64, run_id: &str) -> bool {
    let key = make_key(workspace_root, project_id, run_id);
    let mut guard = cancelled_runs()
        .lock()
        .expect("cancelled run registry mutex poisoned");
    guard.insert(key)
}

pub fn is_cancelled(workspace_root: &str, project_id: i64, run_id: &str) -> bool {
    let key = make_key(workspace_root, project_id, run_id);
    let guard = cancelled_runs()
        .lock()
        .expect("cancelled run registry mutex poisoned");
    guard.contains(&key)
}

pub fn clear_cancel(workspace_root: &str, project_id: i64, run_id: &str) -> bool {
    let key = make_key(workspace_root, project_id, run_id);
    let mut guard = cancelled_runs()
        .lock()
        .expect("cancelled run registry mutex poisoned");
    guard.remove(&key)
}
