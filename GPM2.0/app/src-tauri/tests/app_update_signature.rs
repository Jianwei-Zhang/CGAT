//! Headless updater integration tests. No download, installer or native window.
use tauri_plugin_updater::UpdaterExt;

#[test]
fn signed_payload_and_announced_version_are_both_verified() {
    use base64::{Engine, engine::general_purpose::STANDARD};
    // Public throwaway vector from tauri-plugin-updater 2.14 offline_tests.
    // Payload is "test"; no private key or actual installer is used.
    let public_key = "untrusted comment: minisign public key: A49EF4746FA6E6D7\nRWTX5qZvdPSepDGWg2bz8n6ArQnBMwgQK1geVosorcbLzcunD+KJ+cYe";
    let signature = "untrusted comment: signature from tauri secret key\nRUTX5qZvdPSepPF2zsjvP/L/TQtBLRnWRvaq+4omK1UEugtQp/USrGiI1v762sDy3id3aor7bRC9ETyeot6lMHHrWoZ5hjUM1Qc=\ntrusted comment: timestamp:1791649051\tfile:payload\tversion:2.0.0\nDDq2CLOEl5cQmC2eJRHlnZPVViOZsu1CjpPKQoei4A/XBfkDqGO0B+QMrcrHgEQ5qV3mne75tdFWhJpqUXh9AA==";
    let config: serde_json::Value =
        serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    let mut plugin_config = config["plugins"]["updater"].clone();
    plugin_config["pubkey"] = serde_json::json!(STANDARD.encode(public_key));
    let mut context = tauri::test::mock_context(tauri::test::noop_assets());
    context
        .config_mut()
        .plugins
        .0
        .insert("updater".into(), plugin_config);
    let app = tauri::test::mock_builder()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .build(context)
        .unwrap();
    let updater = app.updater_builder().target("test-target").build().unwrap();
    let manifest = serde_json::json!({"version":"2.0.0", "platforms": {"test-target": {
        "url":"https://example.invalid/update", "signature": STANDARD.encode(signature)
    }}});
    let update = updater.restore_update(manifest.clone()).unwrap().unwrap();
    assert!(update.verify(b"test").is_ok());
    assert!(update.verify(b"tampered").is_err());
    let mut forged = manifest;
    forged["version"] = serde_json::json!("9.0.0");
    assert!(
        updater
            .restore_update(forged)
            .unwrap()
            .unwrap()
            .verify(b"test")
            .is_err()
    );
}

#[test]
fn updater_plugin_initializes_with_the_real_disabled_build_configuration() {
    let config: serde_json::Value =
        serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    let mut context = tauri::test::mock_context(tauri::test::noop_assets());
    context
        .config_mut()
        .plugins
        .0
        .insert("updater".into(), config["plugins"]["updater"].clone());
    let _app = tauri::test::mock_builder()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .build(context)
        .unwrap();
}
