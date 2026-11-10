use tauri::Manager;

fn is_local_view_label(label: &str) -> bool {
    let Some((id, token)) = label
        .strip_prefix("local-view-")
        .and_then(|s| s.rsplit_once("--"))
    else {
        return false;
    };
    id.starts_with("local-")
        && id.len() <= 100
        && (16..=100).contains(&token.len())
        && !token.contains("--")
        && id
            .chars()
            .chain(token.chars())
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
}

// Native ownership/transience, NOT global always-on-top and NOT a focus loop.
// This keeps Main interactive while a pinned Local View stays above Main.
#[tauri::command]
pub async fn set_local_view_pinned(
    app: tauri::AppHandle,
    label: String,
    pinned: bool,
) -> Result<(), String> {
    if !is_local_view_label(&label) {
        return Err("Invalid Local View window".into());
    }
    let (send, receive) = tokio::sync::oneshot::channel();
    let owner = app.clone();
    app.run_on_main_thread(move || {
        let result = (|| {
            let child = owner
                .get_webview_window(&label)
                .ok_or("Local View window expired")?;
            let main = owner
                .get_webview_window("main")
                .ok_or("Main window unavailable")?;
            set_parent(&child, &main, pinned)
        })();
        let _ = send.send(result);
    })
    .map_err(|error| error.to_string())?;
    receive.await.map_err(|error| error.to_string())?
}

#[cfg(target_os = "windows")]
fn set_parent(
    child: &tauri::WebviewWindow,
    main: &tauri::WebviewWindow,
    pinned: bool,
) -> Result<(), String> {
    use std::ffi::c_void;
    #[link(name = "user32")]
    unsafe extern "system" {
        #[cfg_attr(target_pointer_width = "32", link_name = "SetWindowLongW")]
        fn SetWindowLongPtrW(window: *mut c_void, index: i32, value: isize) -> isize;
        fn SetWindowPos(
            window: *mut c_void,
            after: *mut c_void,
            x: i32,
            y: i32,
            width: i32,
            height: i32,
            flags: u32,
        ) -> i32;
        fn GetForegroundWindow() -> *mut c_void;
        fn GetWindowThreadProcessId(window: *mut c_void, process_id: *mut u32) -> u32;
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn SetLastError(error: u32);
        fn GetLastError() -> u32;
    }
    let window = child.hwnd().map_err(|error| error.to_string())?.0;
    let parent = if pinned {
        main.hwnd().map_err(|error| error.to_string())?.0 as isize
    } else {
        0
    };
    let visible = pinned
        && !child.is_minimized().map_err(|error| error.to_string())?
        && !main.is_minimized().map_err(|error| error.to_string())?;
    let mut foreground_process = 0;
    unsafe {
        GetWindowThreadProcessId(GetForegroundWindow(), &mut foreground_process);
    }
    // GWLP_HWNDPARENT changes the owner of a top-level popup; do not use
    // SetParent/WS_CHILD, which would constrain it to Main's client rectangle.
    unsafe {
        SetLastError(0);
    }
    let previous = unsafe { SetWindowLongPtrW(window, -8, parent) };
    let error = unsafe { GetLastError() };
    if previous == 0 && error != 0 {
        return Err(format!("Could not change Local View ownership ({error})"));
    }
    if visible && foreground_process == std::process::id() {
        // HWND_TOP, not HWND_TOPMOST. NOACTIVATE preserves Main's input focus.
        let placed = unsafe {
            SetWindowPos(
                window,
                std::ptr::null_mut(),
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010 | 0x0200,
            )
        };
        if placed == 0 {
            let error = unsafe { GetLastError() };
            unsafe {
                SetWindowLongPtrW(window, -8, previous);
            }
            return Err(format!("Could not order Local View above Main ({error})"));
        }
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn set_parent(
    child: &tauri::WebviewWindow,
    main: &tauri::WebviewWindow,
    pinned: bool,
) -> Result<(), String> {
    let child = child.ns_window().map_err(|error| error.to_string())?;
    let main = main.ns_window().map_err(|error| error.to_string())?;
    if child.is_null() || main.is_null() {
        return Err("Native window unavailable".into());
    }
    // The command dispatches this closure onto AppKit's main thread. Retain
    // normal NSWindow levels so activating another app still covers this group.
    unsafe {
        let child = &*(child as *mut objc2::runtime::AnyObject);
        let main = &*(main as *mut objc2::runtime::AnyObject);
        if pinned {
            let _: () = objc2::msg_send![main, addChildWindow: child, ordered: 1isize];
        } else {
            let _: () = objc2::msg_send![main, removeChildWindow: child];
        }
    }
    Ok(())
}

#[cfg(any(
    target_os = "linux",
    target_os = "dragonfly",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd"
))]
fn set_parent(
    child: &tauri::WebviewWindow,
    main: &tauri::WebviewWindow,
    pinned: bool,
) -> Result<(), String> {
    use gtk::prelude::GtkWindowExt;
    let child = child.gtk_window().map_err(|error| error.to_string())?;
    let main = main.gtk_window().map_err(|error| error.to_string())?;
    child.set_transient_for(if pinned { Some(&main) } else { None });
    Ok(())
}

#[cfg(not(any(
    target_os = "windows",
    target_os = "macos",
    target_os = "linux",
    target_os = "dragonfly",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd"
)))]
fn set_parent(
    _child: &tauri::WebviewWindow,
    _main: &tauri::WebviewWindow,
    _pinned: bool,
) -> Result<(), String> {
    Err("Local View pinning is unavailable on this platform".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pin_commands_cannot_target_main_or_unscoped_windows() {
        assert!(is_local_view_label(
            "local-view-local-123--0123456789abcdef"
        ));
        for label in [
            "main",
            "local-view-main--0123456789abcdef",
            "local-view-local-1--short",
            "local-view-local-1--0123456789abc/ef",
        ] {
            assert!(!is_local_view_label(label));
        }
    }
}
