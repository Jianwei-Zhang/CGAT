import { getMessages } from "../i18n/index.js";

export function renderAppShell(state) {
  const locale = state.locale === "en" ? "en" : "zh";
  const labels = getMessages(locale, "shell");

  return `
    <div class="desktop-shell">
      <header class="topbar panel">
        <div class="topbar-brand">
          <div class="topbar-brand-text">
            <p class="kicker">GPM Next</p>
            <h1>${labels.title}</h1>
          </div>
        </div>
        <div class="session-meta">
          <div class="meta-item">
            <span>${labels.workspace}</span>
            <select id="session-workspace-select" aria-label="${labels.workspace}">
              <option value="">${labels.workspacePlaceholder}</option>
            </select>
          </div>
          <div class="meta-item">
            <span>${labels.project}</span>
            <select id="session-project-select" aria-label="${labels.project}">
              <option value="">${labels.projectPlaceholder}</option>
            </select>
          </div>
          <div class="meta-item meta-item-language">
            <span>${labels.language}</span>
            <select id="app-language-select">
              <option value="zh" ${locale === "zh" ? "selected" : ""}>中文</option>
              <option value="en" ${locale === "en" ? "selected" : ""}>English</option>
            </select>
          </div>
        </div>
      </header>
      <nav class="panel app-nav">
        <nav class="route-nav">
          <button class="route-button" data-route="importer">${labels.importer}</button>
          <button class="route-button" data-route="workspace">${labels.workspaceRoute}</button>
          <button class="route-button" data-route="assembly">${labels.assembly}</button>
          <button class="route-button" data-route="projectExport">${labels.projectExport}</button>
        </nav>
      </nav>
      <main class="main-stage">
        <section class="panel stage-panel">
          <div id="route-host"></div>
        </section>
      </main>
    </div>
  `;
}
