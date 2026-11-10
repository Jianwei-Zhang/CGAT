use tauri::{Emitter, Manager};

fn local_view_id(url: &tauri::Url, main: &tauri::Url) -> Option<String> {
    // url::Url gives custom schemes (tauri:// on macOS/Linux) opaque origins.
    // Compare their explicit authority instead of two unequal opaque tokens.
    if url.scheme() != main.scheme()
        || url.host_str() != main.host_str()
        || url.port_or_known_default() != main.port_or_known_default()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.path() != "/local-view.html"
    {
        return None;
    }
    let id = url
        .query_pairs()
        .find(|(key, _)| key == "view")?
        .1
        .into_owned();
    let token = url
        .query_pairs()
        .find(|(key, _)| key == "token")?
        .1
        .into_owned();
    if !id.starts_with("local-")
        || id.len() > 100
        || token.len() < 16
        || token.len() > 100
        || token.contains("--")
        || !id
            .chars()
            .chain(token.chars())
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return None;
    }
    Some(id)
}

pub fn create_main_window(app: &tauri::App) -> tauri::Result<()> {
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .expect("main window configuration")
        .clone();
    let owner = app.handle().clone();
    tauri::WebviewWindowBuilder::from_config(app, &config)?
        .title(super::main_window_title(&app.package_info().version))
        .initialization_script("window.__GPM_NATIVE_LOCAL_VIEWS__ = true;")
        .on_new_window(move |url, features| {
            let Some(main) = owner
                .get_webview_window("main")
                .and_then(|window| window.url().ok())
            else {
                return tauri::webview::NewWindowResponse::Deny;
            };
            let Some(id) = local_view_id(&url, &main) else {
                return tauri::webview::NewWindowResponse::Deny;
            };
            let token = url
                .query_pairs()
                .find(|(key, _)| key == "token")
                .expect("validated token")
                .1
                .into_owned();
            // Each opening gets a different native label. A delayed destroyed
            // event from an old peer cannot close a newly restored task (ABA).
            let label = format!("local-view-{id}--{token}");
            if owner.get_webview_window(&label).is_some() {
                return tauri::webview::NewWindowResponse::Deny;
            }
            let expected = url.clone();
            let result = tauri::WebviewWindowBuilder::new(
                &owner,
                &label,
                tauri::WebviewUrl::External("about:blank".parse().expect("blank URL")),
            )
            // Preserve the opener browsing context, not a second app/store.
            .window_features(features)
            .on_navigation(move |target| target.as_str() == "about:blank" || target == &expected)
            .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
            .title("Local View")
            .inner_size(1080.0, 560.0)
            .min_inner_size(480.0, 220.0)
            .decorations(false)
            .resizable(true)
            .maximizable(false)
            .focused(false)
            .visible(false)
            .disable_drag_drop_handler()
            .build();
            match result {
                Ok(window) => tauri::webview::NewWindowResponse::Create { window },
                Err(error) => {
                    eprintln!("Local View window creation failed: {error}");
                    tauri::webview::NewWindowResponse::Deny
                }
            }
        })
        .build()?;
    Ok(())
}

pub fn on_window_event(window: &tauri::Window, event: &tauri::WindowEvent) {
    if !matches!(event, tauri::WindowEvent::Destroyed) {
        return;
    }
    let owner = window.app_handle();
    if window.label() == "main" {
        for (label, child) in owner.webview_windows() {
            if label.starts_with("local-view-") {
                let _ = child.destroy();
            }
        }
    } else if let Some((id, token)) = window
        .label()
        .strip_prefix("local-view-")
        .and_then(|value| value.rsplit_once("--"))
    {
        let _ = owner.emit_to(
            "main",
            "gpm-local-view-destroyed",
            serde_json::json!({"view": id, "token": token}),
        );
    }
}

// Resolve the real desktop window under the cursor, not a guessed screen/CSS
// coordinate offset. Physical client bounds and each window's DPI must agree.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DragProbe {
    label: Option<String>,
    x: f64,
    y: f64,
    pressed: Option<bool>,
    escape: bool,
}

#[cfg(target_os = "windows")]
mod desktop_hit {
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct Point {
        x: i32,
        y: i32,
    }
    #[link(name = "user32")]
    unsafe extern "system" {
        fn WindowFromPoint(point: Point) -> *mut std::ffi::c_void;
        fn GetAncestor(window: *mut std::ffi::c_void, flags: u32) -> *mut std::ffi::c_void;
        fn GetAsyncKeyState(key: i32) -> i16;
    }
    pub fn root_at(x: f64, y: f64) -> isize {
        // GA_ROOT: WebView2 may report a nested child HWND.
        unsafe {
            GetAncestor(
                WindowFromPoint(Point {
                    x: x as i32,
                    y: y as i32,
                }),
                2,
            ) as isize
        }
    }
    pub fn buttons() -> (Option<bool>, bool) {
        unsafe { (Some(GetAsyncKeyState(1) < 0), GetAsyncKeyState(0x1b) < 0) }
    }
}

#[tauri::command]
pub fn probe_local_view_drag(app: tauri::AppHandle) -> Result<DragProbe, String> {
    let main = app
        .get_webview_window("main")
        .ok_or("Main window unavailable")?;
    let cursor = main.cursor_position().map_err(|error| error.to_string())?;
    #[cfg(target_os = "windows")]
    let (pressed, escape) = desktop_hit::buttons();
    #[cfg(not(target_os = "windows"))]
    let (pressed, escape) = (None, false);
    let mut probe = DragProbe {
        label: None,
        x: 0.0,
        y: 0.0,
        pressed,
        escape,
    };
    let mut candidates = Vec::new();
    for (label, window) in app.webview_windows() {
        if label != "main" && !label.starts_with("local-view-") {
            continue;
        }
        if !window.is_visible().unwrap_or(false) || window.is_minimized().unwrap_or(true) {
            continue;
        }
        let Ok(position) = window.inner_position() else {
            continue;
        };
        let Ok(size) = window.inner_size() else {
            continue;
        };
        let Ok(scale) = window.scale_factor() else {
            continue;
        };
        if !scale.is_finite() || scale <= 0.0 {
            continue;
        }
        let x = cursor.x - f64::from(position.x);
        let y = cursor.y - f64::from(position.y);
        if x < 0.0 || y < 0.0 || x >= f64::from(size.width) || y >= f64::from(size.height) {
            continue;
        }
        #[cfg(target_os = "windows")]
        {
            let Ok(hwnd) = window.hwnd() else {
                continue;
            };
            if hwnd.0 as isize != desktop_hit::root_at(cursor.x, cursor.y) {
                continue;
            }
        }
        candidates.push((
            label,
            x / scale,
            y / scale,
            window.is_focused().unwrap_or(false),
        ));
    }
    // On other platforms, accept unambiguous bounds or the focused peer only.
    // Never choose an arbitrary overlapping task by its creation order.
    let target = if candidates.len() == 1 {
        candidates.pop()
    } else {
        candidates.into_iter().find(|item| item.3)
    };
    if let Some((label, x, y, _)) = target {
        probe.label = Some(label);
        probe.x = x;
        probe.y = y;
    }
    Ok(probe)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn custom_protocol_local_views_keep_the_same_authority() {
        let main = "tauri://localhost/index.html".parse().unwrap();
        let child = "tauri://localhost/local-view.html?view=local-123&token=0123456789abcdef";
        assert_eq!(
            local_view_id(&child.parse().unwrap(), &main),
            Some("local-123".into())
        );
        assert!(
            local_view_id(&child.replace("localhost", "other").parse().unwrap(), &main).is_none()
        );
        assert!(
            local_view_id(
                &child.replace("tauri://", "https://").parse().unwrap(),
                &main
            )
            .is_none()
        );
    }

    #[test]
    fn only_scoped_same_origin_local_view_popups_are_accepted() {
        let main = "http://127.0.0.1:5174/".parse().unwrap();
        let good = "http://127.0.0.1:5174/local-view.html?view=local-123&token=0123456789abcdef";
        assert_eq!(
            local_view_id(&good.parse().unwrap(), &main),
            Some("local-123".into())
        );
        for bad in [
            good.replace("5174", "9999"),
            good.replace("local-view.html", "index.html"),
            good.replace("local-123", "../main"),
            good.replace("0123456789abcdef", "short"),
        ] {
            assert_eq!(local_view_id(&bad.parse().unwrap(), &main), None);
        }
    }
}
