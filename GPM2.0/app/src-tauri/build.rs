fn main() {
    println!("cargo:rerun-if-env-changed=GPM_UPDATER_PUBLIC_KEY");
    tauri_build::build();
    // Tauri links the Common Controls v6 manifest only into application binaries.
    // Headless integration tests initialize its plugin infrastructure too; without
    // the same resource Windows cannot resolve comctl32!TaskDialogIndirect.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
    {
        let resource =
            std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("resource.lib");
        println!("cargo:rustc-link-arg-tests={}", resource.display());
    }
}
