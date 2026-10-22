import { getMessages } from "../i18n/index.js";
import { getAppliedAppTheme, getAppSettings, resolveAppTheme, setAppSettings, subscribeAppTheme } from "../../services/app-settings.js";
import { projectIcon } from "../pages/project-icons.js";
import { requestAppNotice } from "./app-dialog.js";

function isDarkTheme() {
  return (getAppliedAppTheme() || resolveAppTheme(getAppSettings().theme,
    globalThis.matchMedia?.("(prefers-color-scheme: dark)")?.matches)) === "dark";
}

function themeToggleLabel(labels, dark) {
  return dark ? labels.switchToLight : labels.switchToDark;
}

const themeBindings = new WeakMap();
export function bindAppThemeToggle(root, { getLocale }) {
  themeBindings.get(root)?.();
  const button = root.querySelector("[data-app-theme-toggle]");
  if (!button) return;
  const sync = () => {
    const dark = isDarkTheme(), label = themeToggleLabel(getMessages(getLocale(), "shell"), dark);
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", String(dark));
    button.innerHTML = projectIcon(dark ? "sun" : "moon");
  };
  const toggle = () => {
    try {
      setAppSettings({ ...getAppSettings(), theme: isDarkTheme() ? "light" : "dark" });
      sync();
    } catch {
      void requestAppNotice(getMessages(getLocale(), "shell").themeSaveFailed, { locale: getLocale() });
    }
  };
  button.addEventListener("click", toggle);
  const unsubscribe = subscribeAppTheme(sync);
  themeBindings.set(root, () => {
    unsubscribe();
    button.removeEventListener("click", toggle);
  });
  sync();
}

export function renderAppShell(state) {
  const locale = state.locale === "en" ? "en" : "zh";
  const labels = getMessages(locale, "shell");
  const dark = isDarkTheme(), themeLabel = themeToggleLabel(labels, dark);

  return `
    <div class="desktop-shell">
      <nav class="panel app-nav">
        <nav class="route-nav">
          <button class="route-button" data-route="importer">${labels.project}</button>
          <button class="route-button" data-route="projectPreview">${labels.projectPreview}</button>
          <button class="route-button" data-route="assembly">${labels.assembly}</button>
          <button class="route-button" data-route="projectExport">${labels.projectExport}</button>
        </nav>
        <div class="nav-session-controls">
          <label class="nav-session-field" for="session-workspace-select">
            <span>${labels.workspace}</span>
            <select id="session-workspace-select" aria-label="${labels.workspace}">
              <option value="">${labels.workspacePlaceholder}</option>
            </select>
          </label>
          <label class="nav-session-field nav-session-field-language" for="app-language-select">
            <span>${labels.language}</span>
            <select id="app-language-select" aria-label="${labels.language}">
              <option value="zh" ${locale === "zh" ? "selected" : ""}>中文</option>
              <option value="en" ${locale === "en" ? "selected" : ""}>English</option>
            </select>
          </label>
          <button type="button" class="button app-theme-toggle" data-app-theme-toggle title="${themeLabel}" aria-label="${themeLabel}" aria-pressed="${dark}">${projectIcon(dark ? "sun" : "moon")}</button>
          <button type="button" class="button app-settings-button" data-app-settings aria-haspopup="dialog">⚙ ${locale === "en" ? "Settings" : "设置"}</button>
        </div>
      </nav>
      <main class="main-stage">
        <section class="panel stage-panel">
          <div id="route-host"></div>
        </section>
      </main>
    </div>
  `;
}
