const copy = {
  zh: {
    title: "更新与关于",
    desc: "管理桌面 App 自动更新策略，并查看当前版本与运行环境。",
    updatesGroup: "应用更新",
    aboutGroup: "关于与环境信息",
    current: "当前版本",
    check: "检查更新",
    last: "上次检查",
    idle: "通过 CGAT 文档镜像自动检查并下载新版本。",
    checking: "正在检查更新…",
    latest: "当前已是最新版本",
    available: "发现新版本",
    downloading: "正在下载更新…",
    ready: "更新已准备就绪",
    installing: "正在保存项目并安装更新…",
    unavailable: "此构建尚未启用签名更新。",
    error: "更新失败，请重试。",
    view: "查看更新",
    download: "下载更新",
    install: "安装并重启",
    later: "稍后",
    background: "后台下载",
    mute: "24 小时内不再提醒",
    autoCheck: "启动时自动检查更新",
    autoCheckDesc: "每次打开 App 时检查一次签名更新；关闭后仍可随时手动检查。",
    snoozedUntil: "已暂停自动更新提醒至 {time}",
    clearSnooze: "恢复提醒",
    notes: "更新说明",
    loadingNotes: "正在加载更新说明…",
    failedNotes: "更新说明暂时无法加载，不影响下载更新。",
    retryNotes: "重新加载说明",
    scope: "仅更新桌面 App，不更新远端 Server。安装前将保存当前项目；请勿关闭应用。",
    appName: "应用名称",
    runtime: "运行环境",
    platform: "系统平台",
    channel: "更新渠道",
    channelValue: "CGAT Docs Mirror",
    copyDiagnostics: "复制诊断信息",
    update_storage: "无法保存免打扰设置，请检查本机存储。",
    update_work_busy: "请等待当前任务完成后再安装更新。",
    update_save_failed: "项目保存失败，已停止安装。请先解决保存问题后重试。",
    update_signature: "更新包签名验证失败，已阻止安装。",
    update_integrity: "更新包完整性验证失败，请重试。",
    update_check_failed: "无法取得有效更新清单，请检查网络后重试。",
    update_network: "网络连接失败，请重试。",
    update_install: "安装失败，当前项目未被替换。请重试。",
    update_unconfigured: "此构建尚未启用签名更新。",
  },
  en: {
    title: "Updates & About",
    desc: "Manage desktop App update checks and inspect version and environment details.",
    updatesGroup: "Software Updates",
    aboutGroup: "About & Environment",
    current: "Current version",
    check: "Check for updates",
    last: "Last checked",
    idle: "Checks and downloads updates through the CGAT docs mirror.",
    checking: "Checking for updates…",
    latest: "You are up to date",
    available: "New Version Available",
    downloading: "Downloading update…",
    ready: "Update is ready",
    installing: "Saving your project and installing…",
    unavailable: "Signed updates are not enabled in this build.",
    error: "Update failed. Please retry.",
    view: "View update",
    download: "Download update",
    install: "Install and restart",
    later: "Later",
    background: "Download in background",
    mute: "Do not remind me for 24 hours",
    autoCheck: "Automatically check for updates on launch",
    autoCheckDesc: "Runs one signed update check when the App starts. Manual checks remain available.",
    snoozedUntil: "Update reminders paused until {time}",
    clearSnooze: "Resume reminders",
    notes: "What’s new",
    loadingNotes: "Loading release notes…",
    failedNotes: "Release notes are unavailable. You can still download the update.",
    retryNotes: "Reload notes",
    scope: "Updates the desktop App only, not the remote Server. Your project will be saved before installation; do not close the app.",
    appName: "Application",
    runtime: "Runtime",
    platform: "Platform",
    channel: "Update channel",
    channelValue: "CGAT Docs Mirror",
    copyDiagnostics: "Copy diagnostic info",
    update_storage: "Could not save the reminder preference. Check local storage.",
    update_work_busy: "Wait for the current task to finish before installing.",
    update_save_failed: "Project saving failed. Installation was stopped. Resolve the save error and retry.",
    update_signature: "Update signature verification failed. Installation was blocked.",
    update_integrity: "Update integrity verification failed. Please retry.",
    update_check_failed: "No valid update manifest is available. Check your connection and retry.",
    update_network: "Network connection failed. Please retry.",
    update_install: "Installation failed. Your project was not replaced. Please retry.",
    update_unconfigured: "Signed updates are not enabled in this build.",
  },
};

const labels = locale => copy[locale === "en" ? "en" : "zh"];
const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function updateStatusText(state, locale) {
  const c = labels(locale);
  if (state.error) return c[state.error] || c.error;
  if (state.phase === "downloading" && state.total > 0) {
    return `${c.downloading} ${Math.min(100, Math.floor(state.downloaded / state.total * 100))}%`;
  }
  return c[state.phase] || c.idle;
}

export function buildDiagnosticSummary({ version = "", runtimeMode = "", platform = "", locale = "zh", settings = {} } = {}) {
  const lines = [
    `App: Genome Puzzle Master`,
    `Version: ${version || "unknown"}`,
    `Runtime: ${runtimeMode || "unknown"}`,
    `Platform: ${platform || "unknown"}`,
    `Locale: ${locale === "en" ? "en" : "zh"}`,
    `Theme: ${settings.theme || "system"}`,
    `Typography: ui=${settings.fontSize ?? 14}px, graph=${settings.graphFontSize ?? "follow"}`,
    `HistoryCapacity: ${settings.historyCapacity ?? 0}`,
    `LocalViewDefault: ${settings.localViewDefaultMode || "docked"} (pinned=${settings.localViewDefaultPinned !== false})`,
    `ImportWorkers: ${settings.importParallelism || "auto"}`,
    `AutoCheckUpdates: ${settings.autoCheckUpdates !== false}`,
  ];
  return lines.join("\n");
}

export function renderUpdateSettings(locale, state = {}, options = {}) {
  const c = labels(locale);
  const dateLocale = locale === "en" ? "en-US" : "zh-CN";
  const active = ["checking", "downloading", "installing"].includes(state.phase);
  const details = state.version && !["checking", "installing"].includes(state.phase);
  const autoCheck = options.autoCheckUpdates !== false;
  const runtimeMode = options.runtimeMode || (globalThis.window?.__TAURI__?.core?.invoke ? "Tauri Desktop" : "Browser Preview");
  const platform = options.platform || String(globalThis.navigator?.platform || globalThis.navigator?.userAgentData?.platform || "—");
  const snoozeText = state.snoozeUntil
    ? c.snoozedUntil.replace("{time}", new Date(state.snoozeUntil).toLocaleString(dateLocale))
    : "";
  const versionText = state.currentVersion ? `v${state.currentVersion}` : "—";

  return `<header class="settings-panel-header"><h3 id="settings-update-title">${c.title}</h3><p class="settings-panel-desc">${c.desc}</p></header>
    <div class="settings-group">
      <h4 class="settings-group-title">${c.updatesGroup}</h4>
      <div class="settings-update-head">
        <div class="settings-update-summary">
          <div class="settings-update-version-row">
            <span class="settings-row-title">${c.current}</span>
            <span class="settings-version-value" data-update-version>${escape(state.currentVersion || "—")}</span>
          </div>
          <p class="settings-update-status${state.error ? " is-error" : ""}" role="status" aria-live="polite">${escape(updateStatusText(state, locale))}${state.version ? ` · v${escape(state.version)}` : ""}</p>
          ${state.checkedAt ? `<p class="settings-hint">${c.last}: ${escape(new Date(state.checkedAt).toLocaleString(dateLocale))}</p>` : ""}
        </div>
        <div class="settings-update-actions">
          <button type="button" class="button ghost" data-update-check ${active || !state.enabled ? "disabled" : ""}>${c.check}</button>
          ${details ? `<button type="button" class="button primary" data-update-view>${c.view}</button>` : ""}
        </div>
      </div>
      ${snoozeText ? `<div class="settings-update-snooze"><span>${escape(snoozeText)}</span><button type="button" class="button ghost tiny" data-update-clear-snooze>${c.clearSnooze}</button></div>` : ""}
      <div class="settings-row">
        <div class="settings-row-info">
          <label class="settings-row-title" for="settings-auto-check-updates">${c.autoCheck}</label>
          <p class="settings-row-desc">${c.autoCheckDesc}</p>
        </div>
        <div class="settings-row-control">
          <label class="settings-switch">
            <input id="settings-auto-check-updates" type="checkbox" role="switch" name="autoCheckUpdates"${autoCheck ? " checked" : ""}>
            <span class="settings-switch-track" aria-hidden="true"></span>
          </label>
        </div>
      </div>
    </div>
    <div class="settings-group">
      <h4 class="settings-group-title">${c.aboutGroup}</h4>
      <dl class="settings-about-grid">
        <div class="settings-about-item"><dt>${c.appName}</dt><dd>Genome Puzzle Master</dd></div>
        <div class="settings-about-item"><dt>${c.current}</dt><dd class="settings-mono">${escape(versionText)}</dd></div>
        <div class="settings-about-item"><dt>${c.runtime}</dt><dd>${escape(runtimeMode)}</dd></div>
        <div class="settings-about-item"><dt>${c.platform}</dt><dd>${escape(platform)}</dd></div>
        <div class="settings-about-item"><dt>${c.channel}</dt><dd>${escape(c.channelValue)}</dd></div>
      </dl>
      <div class="settings-about-actions">
        <button type="button" class="button ghost tiny" data-settings-copy-diagnostics>${c.copyDiagnostics}</button>
      </div>
    </div>`;
}

// Native <dialog> and existing app-dialog/button classes retain theme, typography,
// keyboard focus trapping and the same backdrop. Remote notes use textContent only.
export function openUpdateDialog(updater, { getLocale, subscribeLocale = () => () => {} }) {
  const existing = document.querySelector("dialog.app-update-dialog");
  if (existing) { existing.focus(); return; }
  const previousFocus = document.activeElement;
  const dialog = document.createElement("dialog");
  dialog.className = "app-dialog app-update-dialog";
  dialog.setAttribute("aria-labelledby", "app-update-title");
  dialog.setAttribute("aria-describedby", "app-update-scope");
  dialog.innerHTML = `<h2 id="app-update-title" class="app-dialog-title"></h2>
    <p class="app-dialog-message" data-update-versions></p>
    <h3 data-update-notes-title></h3><div class="app-update-notes" tabindex="0"></div>
    <button type="button" class="button ghost" data-update-notes-retry hidden></button>
    <p class="app-dialog-message" id="app-update-scope"></p>
    <p class="app-update-status" role="status" aria-live="polite"></p>
    <progress class="app-update-progress" max="100" hidden></progress>
    <label class="app-update-mute"><input type="checkbox"><span></span></label>
    <div class="app-dialog-actions"><button type="button" class="button ghost" data-update-close></button><button type="button" class="button primary" data-update-action></button></div>`;
  const q = selector => dialog.querySelector(selector);
  let closed = false, notesRequest = 0, notesLocale = "", notesVersion = "", notesFailed = false;
  async function loadNotes() {
    const locale = getLocale(), c = labels(locale), request = ++notesRequest;
    notesLocale = locale; notesVersion = updater.getState().version; notesFailed = false;
    q(".app-update-notes").textContent = c.loadingNotes;
    q("[data-update-notes-retry]").hidden = true;
    try {
      const text = await updater.notes(locale);
      if (!closed && request === notesRequest) q(".app-update-notes").textContent = text;
    } catch {
      if (!closed && request === notesRequest) {
        notesFailed = true; q(".app-update-notes").textContent = labels(getLocale()).failedNotes;
        q("[data-update-notes-retry]").hidden = false;
      }
    }
  }
  function render() {
    if (closed) return;
    const s = updater.getState(), locale = getLocale(), c = labels(locale);
    q("#app-update-title").textContent = `${c.available} · v${s.version}`;
    q("[data-update-versions]").textContent = `${c.current} ${s.currentVersion} → ${s.version}`;
    q("[data-update-notes-title]").textContent = c.notes;
    q("#app-update-scope").textContent = c.scope;
    q(".app-update-mute span").textContent = c.mute;
    q(".app-update-status").textContent = updateStatusText(s, locale);
    q(".app-update-status").classList.toggle("is-error", Boolean(s.error));
    const progress = q("progress"); progress.hidden = s.phase !== "downloading";
    progress.setAttribute("aria-label", c.downloading);
    if (s.total > 0) progress.value = Math.min(100, s.downloaded / s.total * 100); else progress.removeAttribute("value");
    q("[data-update-notes-retry]").textContent = c.retryNotes;
    q("[data-update-notes-retry]").hidden = !notesFailed;
    q("[data-update-close]").textContent = s.phase === "downloading" ? c.background : c.later;
    q("[data-update-close]").disabled = s.phase === "installing";
    q(".app-update-mute input").disabled = s.phase === "installing";
    q("[data-update-action]").textContent = s.ready ? c.install : c.download;
    q("[data-update-action]").disabled = ["checking", "downloading", "installing"].includes(s.phase);
    if (locale !== notesLocale || s.version !== notesVersion) void loadNotes();
  }
  const unsubscribe = updater.subscribe(render);
  const unsubscribeLocale = subscribeLocale(render);
  function close() {
    if (updater.getState().phase === "installing" || !updater.dismiss(q("input").checked)) return;
    closed = true; unsubscribe(); unsubscribeLocale(); dialog.close(); dialog.remove();
    const focusTarget = previousFocus?.isConnected ? previousFocus
      : document.querySelector("dialog.app-settings-dialog [data-update-view], dialog.app-settings-dialog [data-update-check]")
        || document.querySelector("[data-app-settings]");
    focusTarget?.focus();
  }
  dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
  q("[data-update-close]").addEventListener("click", close);
  q("[data-update-notes-retry]").addEventListener("click", () => void loadNotes());
  q("[data-update-action]").addEventListener("click", () => {
    if (q("input").checked && !updater.snooze()) return;
    if (updater.getState().ready) void updater.install(); else void updater.download();
  });
  document.body.append(dialog); render(); dialog.showModal(); q("[data-update-close]").focus();
}
