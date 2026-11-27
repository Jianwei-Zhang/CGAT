use tauri::menu::AboutMetadata;

const APP_DISPLAY_NAME: &str = "Genome Puzzle Master";
pub const OPEN_SETTINGS_MENU_ID: &str = "open-settings";
pub const OPEN_SETTINGS_EVENT: &str = "gpm-open-settings";

fn about_metadata(version: &semver::Version) -> AboutMetadata<'static> {
    AboutMetadata {
        name: Some(APP_DISPLAY_NAME.into()),
        version: Some(version.to_string()),
        // On macOS muda maps this to NSAboutPanelOptionVersion (the build
        // number). None falls back to CFBundleVersion and repeats our version.
        // An explicit empty value suppresses that second number in AppKit.
        short_version: Some(String::new()),
        ..Default::default()
    }
}

// Also compile-check the menu wiring in host-side unit tests.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub fn install(app: &tauri::App) -> tauri::Result<()> {
    use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};

    // Retain the standard Services/Edit/Window menus and their native actions;
    // replace About and insert Settings… (⌘,) in Tauri's macOS application submenu.
    let menu = Menu::default(app.handle())?;
    let items = menu.items()?;
    let app_menu = items
        .first()
        .and_then(|item| item.as_submenu())
        .ok_or_else(|| std::io::Error::other("macOS application menu unavailable"))?;
    let mut metadata = about_metadata(&app.package_info().version);
    metadata.copyright = app.config().bundle.copyright.clone();
    let about = PredefinedMenuItem::about(app, Some("About Genome Puzzle Master"), Some(metadata))?;
    let separator = PredefinedMenuItem::separator(app)?;
    let settings = MenuItem::with_id(
        app,
        OPEN_SETTINGS_MENU_ID,
        "Settings…",
        true,
        Some("CmdOrCtrl+,"),
    )?;
    app_menu.remove_at(0)?;
    app_menu.insert(&about, 0)?;
    app_menu.insert(&separator, 1)?;
    app_menu.insert(&settings, 2)?;
    app.set_menu(menu)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn about_uses_full_name_and_running_version_without_build_number_fallback() {
        for version in ["2.0.20", "2.1.0-beta.1"] {
            let metadata = about_metadata(&semver::Version::parse(version).unwrap());
            assert_eq!(metadata.name.as_deref(), Some("Genome Puzzle Master"));
            assert_eq!(metadata.version.as_deref(), Some(version));
            // None would bring back the duplicate CFBundleVersion value.
            assert_eq!(metadata.short_version.as_deref(), Some(""));
        }
    }

    #[test]
    fn settings_menu_constants_match_frontend_event_contract() {
        assert_eq!(OPEN_SETTINGS_MENU_ID, "open-settings");
        assert_eq!(OPEN_SETTINGS_EVENT, "gpm-open-settings");
    }
}
