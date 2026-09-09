import { defaultProjectName } from "../../services/project-session.js";
import { projectIcon } from "./project-icons.js";
import { getMessages } from "../i18n/index.js";

export function projectLabels(state) {
  return state.locale === "en" ? {
    import: "Import project", open: "Open project", recent: "Project library",
    empty: "No projects yet", emptyHint: "Import a delivery bundle or open an existing project directory.",
    name: "Project name (optional)", nameDefault: "Use directory name", location: "Project directory",
    zip: "ZIP bundle", extracted: "Extracted directory", source: "Source", browse: "Browse",
    cancel: "Cancel", submit: "Import",
    legacy: "This directory contains multiple legacy projects. Select one to continue.",
    pending: "Project initialization incomplete", retry: "Retry initialization",
    delete: "Delete project files", more: "Project actions",
    selectFirst: "Open a project first", loading: "Opening project...", deleteFailed: "Deletion failed",
    sourceLocation: "Project location", legacyProjects: "Legacy projects",
    noOpen: "No project open", opened: "Open", rename: "Rename project", saved: "Save name",
    lastOpened: "Last opened", created: "Created",
  } : {
    import: "导入项目", open: "打开项目", recent: "项目库",
    empty: "尚未添加项目", emptyHint: "导入交付包，或打开已有项目目录。",
    name: "项目名称（可选）", nameDefault: "使用目录名称", location: "项目目录",
    zip: "ZIP 交付包", extracted: "已解压目录", source: "来源", browse: "选择",
    cancel: "取消", submit: "导入",
    legacy: "此目录包含多个旧版项目，请选择要打开的项目。",
    pending: "项目待初始化", retry: "重试初始化",
    delete: "删除项目文件", more: "项目操作",
    selectFirst: "请先打开项目", loading: "正在打开项目...", deleteFailed: "删除失败",
    sourceLocation: "项目位置", legacyProjects: "旧版项目",
    noOpen: "尚未打开项目", opened: "已打开", rename: "重命名项目", saved: "保存名称",
    lastOpened: "上次打开", created: "创建时间",
  };
}

const html = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

function projectValidationView(state, records) {
  const messages = getMessages(state, "importer");
  const importer = state.importer;
  const validatedPaths = new Set(importer.historyValidatedPaths || []);
  const failed = !importer.historyValidating && records.some(record =>
    validatedPaths.has(record.path) && importer.historyValidation?.[record.path]?.ok === false);
  return {
    failed,
    disabled: Boolean(importer.inFlight || importer.historyValidating || state.initializer?.autoPipelineRunning),
    label: importer.historyValidating ? messages.buttons.validatingProjects : messages.buttons.validateHistory,
  };
}

export function syncProjectValidation(host, state, records) {
  const view = projectValidationView(state, records);
  const validate = host.querySelector("#validate-history-button");
  if (validate) {
    validate.disabled = view.disabled;
    validate.textContent = view.label;
    validate.setAttribute("aria-busy", String(Boolean(state.importer.historyValidating)));
  }
  const remove = host.querySelector("#delete-failed-history-button");
  if (remove) {
    remove.hidden = !view.failed;
    remove.disabled = view.disabled || !view.failed;
  }
}

export function renderProjectImportDialog(state, messages) {
  const importer = state.importer;
  if (!importer.importDialogOpen || importer.inFlight) return "";
  const labels = projectLabels(state);
  const extracted = importer.importSource === "extracted";
  const source = extracted ? importer.extractedPath : importer.zipPath;
  const directory = extracted ? importer.extractedPath : importer.workspaceRoot;
  const ready = Boolean(String(source || "").trim() && String(directory || "").trim());
  return `<div class="modal-overlay" data-project-import-overlay>
    <form class="modal-dialog project-import-dialog" role="dialog" aria-modal="true" aria-labelledby="project-import-title">
      <h3 id="project-import-title">${labels.import}</h3>
      <fieldset class="project-source-switch"><legend>${labels.source}</legend>
        <label><input type="radio" name="project-source" value="zip" ${extracted ? "" : "checked"} />${labels.zip}</label>
        <label><input type="radio" name="project-source" value="extracted" ${extracted ? "checked" : ""} />${labels.extracted}</label>
      </fieldset>
      <label for="${extracted ? "extracted-path-input" : "zip-path-input"}">${extracted ? labels.extracted : labels.zip}</label>
      <div class="inline-input">
        <input id="${extracted ? "extracted-path-input" : "zip-path-input"}" value="${html(source)}" required />
        <button type="button" id="${extracted ? "pick-extracted-button" : "pick-zip-button"}" class="button ghost" title="${labels.browse}" aria-label="${labels.browse}">${projectIcon("open")}</button>
      </div>
      ${extracted ? `<p class="project-path muted">${messages.page.importExtractedRule}</p>` : `
        <label for="zip-workspace-root-input">${messages.page.workspaceDir}</label>
        <div class="inline-input"><input id="zip-workspace-root-input" value="${html(directory)}" required />
          <button type="button" id="pick-zip-workspace-button" class="button ghost" title="${labels.browse}" aria-label="${labels.browse}">${projectIcon("open")}</button></div>`}
      <label for="import-project-name">${labels.name}</label>
      <input id="import-project-name" value="${html(importer.projectNameInput)}" placeholder="${html(directory ? defaultProjectName(directory) : labels.nameDefault)}" />
      ${importer.projectError ? `<p class="error-text" role="alert">${html(importer.projectError)}</p>` : ""}
      <footer class="project-dialog-actions">
        <button type="button" data-project-import-close class="button ghost">${labels.cancel}</button>
        <button type="submit" id="${extracted ? "import-extracted-start-button" : "import-zip-start-button"}" class="button project-primary" ${ready ? "" : "disabled"}>${labels.submit}</button>
      </footer>
    </form>
  </div>`;
}

export function renderProjectsBody(state, { records, messages, summaryHtml }) {
  const labels = projectLabels(state);
  const importer = state.importer;
  const busy = importer.inFlight || state.initializer?.autoPipelineRunning;
  const disabled = busy ? "disabled" : "";
  const empty = !records.length && !state.session?.workspacePath;
  const actions = `<div class="project-entry-actions">
    <button id="project-import-button" class="button ${empty ? "project-primary" : "ghost"}" ${disabled}>${projectIcon("import")}${labels.import}</button>
    <button id="project-open-button" class="button ghost" ${disabled}>${projectIcon("open")}${labels.open}</button>
  </div>`;
  const validation = projectValidationView(state, records);
  const rows = records.map((record, index) => {
    const active = state.session?.workspacePath === record.path;
    const name = (active && state.session?.projectName) || record.projectName || defaultProjectName(record.path);
    return `<div class="project-recent-row ${active ? "is-active" : ""}" data-workspace-history-row-path="${html(record.path)}">
      <button class="project-recent-open" data-recent-index="${index}" data-recent-path="${html(record.path)}" aria-current="${active ? "true" : "false"}" title="${html(record.path)}" ${disabled}>
        <span class="project-recent-name">${projectIcon("folder")}<strong>${html(name)}</strong></span>
      </button>
      <details class="project-row-menu"><summary aria-label="${labels.more}" title="${labels.more}">${projectIcon("more")}</summary>
        <div class="project-row-menu-items">
          <button data-workspace-import-add-package-path="${html(record.path)}" ${disabled}>${messages.buttons.importAddPackage}</button>
          <button data-project-delete-files="${html(record.path)}" class="danger" ${disabled}>${labels.delete}</button>
        </div>
      </details>
    </div>`;
  }).join("");
  return `${importer.inFlight && !importer.importRunId ? `<p role="status">${html(importer.status || labels.loading)}</p>` : ""}
  ${importer.projectError && !importer.importDialogOpen ? `<p class="error-text" data-project-page-error role="alert">${html(importer.projectError)}</p>` : ""}
  ${importer.pendingProjectPath ? `<section class="project-pending">
    <strong>${labels.pending}</strong><span class="project-path">${html(importer.pendingProjectPath)}</span>
    <button id="project-retry-button" class="button" ${disabled}>${labels.retry}</button></section>` : ""}
  ${empty ? `<section class="project-empty" aria-labelledby="project-empty-title">
    <span class="project-empty-symbol">${projectIcon("folder")}</span>
    <h4 id="project-empty-title">${labels.empty}</h4>${actions}
  </section>` : `<div class="project-browser">
    <section class="project-recents" aria-labelledby="project-recents-title">
      ${actions}
      <header class="project-recents-header"><h4 id="project-recents-title">${labels.recent}<span class="project-count">${records.length}</span></h4>
        ${records.length ? `<div class="project-library-actions">
          <button id="validate-history-button" class="button ghost project-history-action" aria-busy="${Boolean(importer.historyValidating)}" ${validation.disabled ? "disabled" : ""}>${validation.label}</button>
          <button id="delete-failed-history-button" class="button ghost project-history-action" ${validation.disabled || !validation.failed ? "disabled" : ""} ${validation.failed ? "" : "hidden"}>${messages.buttons.deleteFailedRecords}</button>
        </div>` : ""}
      </header>
      <div class="project-recent-list">${rows}</div>
    </section>
    ${summaryHtml || `<section class="project-empty project-no-selection"><span class="project-empty-symbol">${projectIcon("open")}</span><h4>${labels.noOpen}</h4></section>`}
  </div>`}
  ${renderProjectImportDialog(state, messages)}`;
}
