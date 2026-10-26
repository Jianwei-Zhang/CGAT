//! Desktop-only signed updates. Remote data never supplies a shell command or path.
use reqwest::Client;
use semver::Version;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    sync::{
        Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_updater::{RemoteRelease, Update, UpdaterExt};

const DOCS: &str = "https://riceome.hzau.edu.cn/cgat/downloads";
const RELEASE: &str = "https://github.com/Jianwei-Zhang/CGAT/releases";
const MAX_PACKAGE: u64 = 256 * 1024 * 1024;
const MAX_NOTES: u64 = 256 * 1024;
const KEY: &str = match option_env!("GPM_UPDATER_PUBLIC_KEY") {
    Some(value) => value,
    None => "",
};

#[derive(Clone, Deserialize, Serialize)]
struct FileInfo {
    url: String,
    mirror_url: String,
    sha256: String,
    size: u64,
}
#[derive(Clone, Deserialize, Serialize)]
struct Package {
    #[serde(flatten)]
    file: FileInfo,
    signature: String,
}
#[derive(Clone, Deserialize, Serialize)]
struct Manifest {
    schema_version: u32,
    version: String,
    pub_date: String,
    platforms: BTreeMap<String, Package>,
    release_notes: BTreeMap<String, FileInfo>,
}
#[derive(Clone)]
struct Offer {
    manifest: Manifest,
    update: Update,
    package: Package,
}
#[derive(Default)]
struct Cache {
    offer: Option<Offer>,
    ready: Option<Vec<u8>>,
}
#[derive(Default)]
pub struct UpdateState {
    busy: AtomicBool,
    cache: Mutex<Cache>,
}
struct Operation<'a>(&'a AtomicBool);
impl Drop for Operation<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}
impl UpdateState {
    fn begin(&self) -> Result<Operation<'_>, String> {
        self.busy
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| "update_busy".to_owned())?;
        Ok(Operation(&self.busy))
    }
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    current_version: String,
    enabled: bool,
    version: Option<String>,
    ready: bool,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Progress {
    downloaded: u64,
    total: u64,
    source: &'static str,
}

fn platform() -> String {
    format!(
        "{}-{}",
        if cfg!(target_os = "macos") {
            "darwin"
        } else {
            std::env::consts::OS
        },
        std::env::consts::ARCH
    )
}
fn client() -> Result<Client, String> {
    Client::builder()
        .user_agent("GPM-App-Updater")
        .connect_timeout(Duration::from_secs(5))
        .redirect(reqwest::redirect::Policy::custom(|attempt| {
            let url = attempt.url();
            let allowed = matches!(
                url.host_str(),
                Some(
                    "riceome.hzau.edu.cn"
                        | "github.com"
                        | "release-assets.githubusercontent.com"
                        | "objects.githubusercontent.com"
                )
            );
            if attempt.previous().len() < 5 && url.scheme() == "https" && allowed {
                attempt.follow()
            } else {
                attempt.error("Untrusted update redirect")
            }
        }))
        .build()
        .map_err(|_| "update_network".into())
}
fn validate_file(file: &FileInfo, version: &str, max: u64) -> Result<(), String> {
    let github = format!("{RELEASE}/download/v{version}/");
    let docs = format!("{DOCS}/v{version}/");
    let leaf = file.url.strip_prefix(&github).ok_or("update_manifest")?;
    if leaf.is_empty()
        || matches!(leaf, "." | "..")
        || !leaf
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        || file.mirror_url != format!("{docs}{leaf}")
        || file.size == 0
        || file.size > max
        || file.sha256.len() != 64
        || !file.sha256.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err("update_manifest".into());
    }
    Ok(())
}
fn validate_manifest(raw: &[u8], target: &str) -> Result<Manifest, String> {
    let _: RemoteRelease = serde_json::from_slice(raw).map_err(|_| "update_manifest")?;
    let manifest: Manifest = serde_json::from_slice(raw).map_err(|_| "update_manifest")?;
    let version = Version::parse(&manifest.version).map_err(|_| "update_manifest")?;
    if manifest.schema_version != 1 || !version.pre.is_empty() || !version.build.is_empty() {
        return Err("update_manifest".into());
    }
    let package = manifest.platforms.get(target).ok_or("update_platform")?;
    let suffix = match target {
        "windows-x86_64" => "_win-x86_setup.exe",
        "windows-aarch64" => "_win-arm64_setup.exe",
        "darwin-x86_64" => "_mac-x86_app.tar.gz",
        "darwin-aarch64" => "_mac-arm64_app.tar.gz",
        _ => return Err("update_platform".into()),
    };
    if !package.file.url.ends_with(suffix) {
        return Err("update_platform".into());
    }
    validate_file(&package.file, &manifest.version, MAX_PACKAGE)?;
    if package.signature.is_empty() || package.signature.len() > 4096 {
        return Err("update_manifest".into());
    }
    for locale in ["en", "zh"] {
        validate_file(
            manifest
                .release_notes
                .get(locale)
                .ok_or("update_manifest")?,
            &manifest.version,
            MAX_NOTES,
        )?;
    }
    Ok(manifest)
}
async fn fetch(
    client: &Client,
    url: &str,
    limit: u64,
    deadline: Duration,
    mut progress: impl FnMut(u64),
) -> Result<Vec<u8>, String> {
    let mut response = tokio::time::timeout(
        Duration::from_secs(10).min(deadline),
        client.get(url).timeout(deadline).send(),
    )
    .await
    .map_err(|_| "update_network")?
    .and_then(|r| r.error_for_status())
    .map_err(|_| "update_network")?;
    if response.content_length().is_some_and(|size| size > limit) {
        return Err("update_size".into());
    }
    let mut bytes = Vec::new();
    loop {
        let chunk = tokio::time::timeout(Duration::from_secs(10), response.chunk())
            .await
            .map_err(|_| "update_network")?
            .map_err(|_| "update_network")?;
        let Some(chunk) = chunk else { break };
        if bytes.len() as u64 + chunk.len() as u64 > limit {
            return Err("update_size".into());
        }
        bytes.extend_from_slice(&chunk);
        progress(bytes.len() as u64);
    }
    Ok(bytes)
}
fn verify_file(file: &FileInfo, bytes: &[u8]) -> Result<(), String> {
    if bytes.len() as u64 != file.size
        || format!("{:x}", Sha256::digest(bytes)) != file.sha256.to_lowercase()
    {
        return Err("update_integrity".into());
    }
    Ok(())
}
async fn docs_first<T>(
    docs: impl std::future::Future<Output = Result<T, String>>,
    github: impl std::future::Future<Output = Result<T, String>>,
) -> Result<T, String> {
    match docs.await {
        Ok(value) => Ok(value),
        Err(_) => github.await,
    }
}
fn info(app: &AppHandle, cache: &Cache) -> UpdateInfo {
    UpdateInfo {
        current_version: app.package_info().version.to_string(),
        enabled: !KEY.trim().is_empty(),
        version: cache
            .offer
            .as_ref()
            .map(|offer| offer.manifest.version.clone()),
        ready: cache.ready.is_some(),
    }
}
#[tauri::command]
pub fn app_update_status(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<UpdateInfo, String> {
    let cache = state.cache.lock().map_err(|_| "update_state")?;
    Ok(info(&app, &cache))
}
#[tauri::command]
pub async fn app_update_check(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<UpdateInfo, String> {
    let _operation = state.begin()?;
    if KEY.trim().is_empty() {
        return Err("update_unconfigured".into());
    }
    let client = client()?;
    let target = platform();
    let docs_url = format!("{DOCS}/updates/latest.json");
    let release_url = format!("{RELEASE}/latest/download/latest.json");
    // Docs is authoritative when healthy. GitHub is a failure fallback, not a
    // parallel freshness check; publication must promote docs/latest.json last.
    async fn load(client: &Client, url: &str, target: &str) -> Result<Manifest, String> {
        let bytes = fetch(client, url, 512 * 1024, Duration::from_secs(8), |_| {}).await?;
        validate_manifest(&bytes, target)
    }
    let manifest = docs_first(
        load(&client, &docs_url, &target),
        load(&client, &release_url, &target),
    )
    .await
    .map_err(|_| "update_check_failed")?;
    let mut cache = state.cache.lock().map_err(|_| "update_state")?;
    if cache.offer.as_ref().is_some_and(|offer| {
        Version::parse(&offer.manifest.version).ok() >= Version::parse(&manifest.version).ok()
    }) {
        return Ok(info(&app, &cache));
    }
    let raw = serde_json::to_value(&manifest).map_err(|_| "update_manifest")?;
    let updater = app
        .updater_builder()
        .pubkey(KEY.trim())
        .target(target.clone())
        .build()
        .map_err(|_| "update_configuration")?;
    // restore_update binds the advertised version to the signed artifact version.
    if let Some(update) = updater.restore_update(raw).map_err(|_| "update_manifest")? {
        let package = manifest.platforms[&target].clone();
        cache.offer = Some(Offer {
            manifest,
            update,
            package,
        });
        cache.ready = None;
    }
    Ok(info(&app, &cache))
}
#[tauri::command]
pub async fn app_update_notes(
    locale: String,
    state: State<'_, UpdateState>,
) -> Result<String, String> {
    if !matches!(locale.as_str(), "en" | "zh") {
        return Err("update_locale".into());
    }
    let offer = state
        .cache
        .lock()
        .map_err(|_| "update_state")?
        .offer
        .clone()
        .ok_or("update_missing")?;
    let file = &offer.manifest.release_notes[&locale];
    let client = client()?;
    async fn load(client: &Client, file: &FileInfo, url: &str) -> Result<String, String> {
        let bytes = fetch(client, url, MAX_NOTES, Duration::from_secs(8), |_| {}).await?;
        verify_file(file, &bytes)?;
        String::from_utf8(bytes).map_err(|_| "update_notes".into())
    }
    docs_first(
        load(&client, file, &file.mirror_url),
        load(&client, file, &file.url),
    )
    .await
}
#[tauri::command]
pub async fn app_update_download(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<(), String> {
    let _operation = state.begin()?;
    let offer = state
        .cache
        .lock()
        .map_err(|_| "update_state")?
        .offer
        .clone()
        .ok_or("update_missing")?;
    let client = client()?;
    let mut last_error = "update_network".to_owned();
    for (url, source) in [
        (&offer.package.file.mirror_url, "docs"),
        (&offer.package.file.url, "github"),
    ] {
        let total = offer.package.file.size;
        let _ = app.emit(
            "app-update-progress",
            Progress {
                downloaded: 0,
                total,
                source,
            },
        );
        let mut last_emit = Instant::now();
        let result = fetch(
            &client,
            url,
            total,
            Duration::from_secs(600),
            |downloaded| {
                if last_emit.elapsed() > Duration::from_millis(100) || downloaded == total {
                    let _ = app.emit(
                        "app-update-progress",
                        Progress {
                            downloaded,
                            total,
                            source,
                        },
                    );
                    last_emit = Instant::now();
                }
            },
        )
        .await;
        let bytes = match result {
            Ok(bytes) => bytes,
            Err(error) => {
                last_error = error;
                continue;
            }
        };
        if let Err(error) = verify_file(&offer.package.file, &bytes) {
            last_error = error;
            continue;
        }
        if offer.update.verify(&bytes).is_err() {
            last_error = "update_signature".into();
            continue;
        }
        state.cache.lock().map_err(|_| "update_state")?.ready = Some(bytes);
        return Ok(());
    }
    Err(last_error)
}
#[tauri::command]
pub async fn app_update_install(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<(), String> {
    let _operation = state.begin()?;
    let (offer, bytes) = {
        let cache = state.cache.lock().map_err(|_| "update_state")?;
        (
            cache.offer.clone().ok_or("update_missing")?,
            cache.ready.clone().ok_or("update_missing")?,
        )
    };
    verify_file(&offer.package.file, &bytes)?;
    tauri::async_runtime::spawn_blocking(move || offer.update.install(bytes))
        .await
        .map_err(|_| "update_install")?
        .map_err(|_| "update_install")?;
    app.restart();
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn healthy_docs_never_contacts_github() {
        let value = docs_first(async { Ok::<_, String>(42) }, async {
            panic!("GitHub must not be contacted");
        })
        .await;
        assert_eq!(value.unwrap(), 42);
    }
    #[tokio::test]
    async fn docs_failure_falls_back_and_both_failures_are_errors() {
        assert_eq!(
            docs_first(async { Err("docs".into()) }, async { Ok(42) })
                .await
                .unwrap(),
            42
        );
        assert!(
            docs_first::<u32>(async { Err("docs".into()) }, async { Err("github".into()) })
                .await
                .is_err()
        );
    }
    #[test]
    fn updater_config_deserializes_even_without_a_production_key() {
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let updater: tauri_plugin_updater::Config =
            serde_json::from_value(config["plugins"]["updater"].clone()).unwrap();
        assert_eq!(
            updater
                .endpoints
                .iter()
                .map(|url| url.as_str())
                .collect::<Vec<_>>(),
            vec![
                format!("{DOCS}/updates/latest.json"),
                format!("{RELEASE}/latest/download/latest.json")
            ]
        );
        assert!(updater.require_signed_version);
        assert!(!updater.allow_downgrades);
    }
    #[test]
    fn malformed_dates_prereleases_and_wrong_platforms_are_rejected() {
        let mut package_file = file();
        package_file.url = package_file
            .url
            .replace("update.exe", "GPM_2.0.13_stamp_win-x86_setup.exe");
        package_file.mirror_url = package_file
            .mirror_url
            .replace("update.exe", "GPM_2.0.13_stamp_win-x86_setup.exe");
        let p = Package {
            file: package_file,
            signature: "fixture".into(),
        };
        let mut manifest = Manifest {
            schema_version: 1,
            version: "2.0.13".into(),
            pub_date: "2026-10-26T00:00:00Z".into(),
            platforms: BTreeMap::from([("windows-x86_64".into(), p)]),
            release_notes: BTreeMap::from([("en".into(), file()), ("zh".into(), file())]),
        };
        let validate =
            |m: &Manifest, target| validate_manifest(&serde_json::to_vec(m).unwrap(), target);
        assert!(validate(&manifest, "windows-x86_64").is_ok());
        assert!(validate(&manifest, "windows-aarch64").is_err());
        manifest.pub_date = "not-a-date".into();
        assert!(validate(&manifest, "windows-x86_64").is_err());
        manifest.pub_date = "2026-10-26T00:00:00Z".into();
        manifest.version = "2.0.13-beta.1".into();
        assert!(validate(&manifest, "windows-x86_64").is_err());
    }
    fn file() -> FileInfo {
        FileInfo {
            url: format!("{RELEASE}/download/v2.0.13/update.exe"),
            mirror_url: format!("{DOCS}/v2.0.13/update.exe"),
            size: 3,
            sha256: format!("{:x}", Sha256::digest(b"abc")),
        }
    }
    #[test]
    fn trusted_same_version_urls_only() {
        let mut f = file();
        assert!(validate_file(&f, "2.0.13", MAX_PACKAGE).is_ok());
        f.url = f.url.replace("github.com", "evil.example");
        assert!(validate_file(&f, "2.0.13", MAX_PACKAGE).is_err());
        let mut f = file();
        f.mirror_url.push_str("?redirect=evil");
        assert!(validate_file(&f, "2.0.13", MAX_PACKAGE).is_err());
        assert!(validate_file(&file(), "2.0.14", MAX_PACKAGE).is_err());
    }
    #[test]
    fn size_and_digest_are_both_required() {
        assert!(verify_file(&file(), b"abc").is_ok());
        assert!(verify_file(&file(), b"abd").is_err());
        assert!(verify_file(&file(), b"ab").is_err());
        let mut f = file();
        f.size = MAX_PACKAGE + 1;
        assert!(validate_file(&f, "2.0.13", MAX_PACKAGE).is_err());
    }
    #[test]
    fn operation_lock_is_released_on_failure() {
        let state = UpdateState::default();
        let operation = state.begin().unwrap();
        assert!(state.begin().is_err());
        drop(operation);
        assert!(state.begin().is_ok());
    }
}
