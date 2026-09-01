use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

fn cancelled_imports() -> &'static Mutex<HashSet<String>> {
    static CANCELLED: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    CANCELLED.get_or_init(|| Mutex::new(HashSet::new()))
}

pub fn request_cancel(run_id: &str) -> bool {
    let normalized = run_id.trim();
    if normalized.is_empty() {
        return false;
    }
    cancelled_imports()
        .lock()
        .expect("cancelled import registry mutex poisoned")
        .insert(normalized.to_string())
}

pub fn is_cancelled(run_id: &str) -> bool {
    let normalized = run_id.trim();
    if normalized.is_empty() {
        return false;
    }
    cancelled_imports()
        .lock()
        .expect("cancelled import registry mutex poisoned")
        .contains(normalized)
}

pub fn clear_cancel(run_id: &str) -> bool {
    let normalized = run_id.trim();
    if normalized.is_empty() {
        return false;
    }
    cancelled_imports()
        .lock()
        .expect("cancelled import registry mutex poisoned")
        .remove(normalized)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cancellation_remains_registered_until_the_worker_clears_it() {
        let run_id = "cancel-before-worker-start";
        let _ = clear_cancel(run_id);

        assert!(request_cancel(run_id));
        assert!(is_cancelled(run_id));
        assert!(clear_cancel(run_id));
        assert!(!is_cancelled(run_id));
    }
}
