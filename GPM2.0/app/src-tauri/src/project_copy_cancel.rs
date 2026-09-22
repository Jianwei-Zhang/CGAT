use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

fn cancelled_copies() -> &'static Mutex<HashSet<String>> {
    static CANCELLED: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    CANCELLED.get_or_init(|| Mutex::new(HashSet::new()))
}

pub fn request_cancel(run_id: &str) -> bool {
    let normalized = run_id.trim();
    if normalized.is_empty() {
        return false;
    }
    cancelled_copies()
        .lock()
        .expect("cancelled project copy registry mutex poisoned")
        .insert(normalized.to_string())
}

pub fn is_cancelled(run_id: &str) -> bool {
    let normalized = run_id.trim();
    !normalized.is_empty()
        && cancelled_copies()
            .lock()
            .expect("cancelled project copy registry mutex poisoned")
            .contains(normalized)
}

pub fn clear_cancel(run_id: &str) -> bool {
    let normalized = run_id.trim();
    !normalized.is_empty()
        && cancelled_copies()
            .lock()
            .expect("cancelled project copy registry mutex poisoned")
            .remove(normalized)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cancellation_remains_registered_until_worker_cleanup() {
        let run_id = "copy-cancel-test";
        let _ = clear_cancel(run_id);
        assert!(request_cancel(run_id));
        assert!(is_cancelled(run_id));
        assert!(clear_cancel(run_id));
        assert!(!is_cancelled(run_id));
    }
}
