import { getMessages } from "../i18n/index.js";

export function renderAppShell(state) {
  const locale = state.locale === "en" ? "en" : "zh";
  const labels = getMessages(locale, "shell");

  return `
    <div class="desktop-shell">
      <nav class="panel app-nav">
        <nav class="route-nav">
          <button class="route-button" data-route="importer">${labels.project}</button>
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
