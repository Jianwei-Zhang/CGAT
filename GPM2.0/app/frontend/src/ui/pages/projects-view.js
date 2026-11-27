import { libraryLabels, renderImportPartition, renderLibrarySearch, renderLibraryTree, renderLibraryDialog, renderLibraryMenu } from "./project-library-view.js";
import { projectEntryBusy } from "../../services/project-drop-controller.js";
import { projectImportName } from "../../services/project-session.js";
import { projectIcon } from "./project-icons.js";
import { getMessages } from "../i18n/index.js";
import { importParserWorkerChoices, normalizeImportParserWorkers, recommendedImportParserWorkers } from "../../services/import-parallelism.js";
import { readProjectSidebarCollapsed } from "./project-sidebar-resize.js";

export function projectLabels(state) {
  return state.locale === "en" ? {
    projectInformation: "Assembly Information",
    resizeLibrary: "Resize project library",
    collapseSidebar: "Collapse library",
    expandSidebar: "Expand library",
    switchSidebarCount: "Switch assembly ({count})",
    import: "Import", open: "Open", importTitle: "Import Assembly", recent: "Assemblies",
    empty: "No assemblies yet", emptyHint: "Import a delivery bundle or open an existing assembly directory.",
    name: "Assembly name (optional)", nameDefault: "Use directory name", location: "Assembly directory",
    zip: "Bundle (ZIP / tar.gz)", extracted: "Extracted directory", extractedOption: "Extracted Directory", source: "Source", browse: "Browse",
    cancel: "Cancel", submit: "Import",
    newDirectory: "Assembly directory (will be created)",
    directoryHint: "You may edit this path. Existing directories will not be overwritten.",
    legacy: "This directory contains multiple legacy assemblies. Select one to continue.",
    pending: "Assembly initialization incomplete", retry: "Retry initialization",
    delete: "Delete Assembly Files",
    selectFirst: "Open an assembly first", loading: "Opening assembly...", deleteFailed: "Deletion failed",
    sourceLocation: "Assembly location", openLocation: "Open Assembly File Location", openLocationFailed: "Unable to open assembly file location", legacyProjects: "Legacy assemblies",
    noOpen: "No assembly open", opened: "Open", rename: "Rename Assembly", saved: "Save name",
    lastOpened: "Last opened", created: "Created",
    importThreads: "Parallel import workers", importThreadsHint: "Shared by archive extraction and PAF parsing during import; SQLite still uses one writer.",
    recommendedThreads: "{number} (Recommended)",
  } : {
    projectInformation: "组装信息",
    resizeLibrary: "调整项目库宽度",
    collapseSidebar: "收起项目库",
    expandSidebar: "展开项目库",
    switchSidebarCount: "快速切换组装（{count}）",
    import: "导入", open: "打开", importTitle: "导入组装", recent: "组装",
    empty: "尚未添加组装", emptyHint: "导入交付包，或打开已有组装目录。",
    name: "组装名称（可选）", nameDefault: "使用目录名称", location: "组装目录",
    zip: "交付包（ZIP / tar.gz）", extracted: "已解压目录", extractedOption: "已解压目录", source: "来源", browse: "选择",
    cancel: "取消", submit: "导入",
    newDirectory: "工作目录（将新建）",
    directoryHint: "可修改此路径；不会覆盖已有目录。",
    legacy: "此目录包含多个旧版组装，请选择要打开的组装。",
    pending: "组装待初始化", retry: "重试初始化",
    delete: "删除组装文件",
    selectFirst: "请先打开组装", loading: "正在打开组装...", deleteFailed: "删除失败",
    sourceLocation: "组装位置", openLocation: "打开组装文件所在位置", openLocationFailed: "无法打开组装文件所在位置", legacyProjects: "旧版组装",
    noOpen: "尚未打开组装", opened: "已打开", rename: "重命名组装", saved: "保存名称",
    lastOpened: "上次打开", created: "创建时间",
    importThreads: "并行导入线程", importThreadsHint: "导入时由交付包解压与 PAF 解析共用；SQLite 仍只使用一个写入线程。",
    recommendedThreads: "{number}（推荐）",
  };
}

const html = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

function projectValidationView(state, records) {
  const messages = getMessages(state, "importer");
  const importer = state.importer;
  const validatedPaths = new Set(importer.historyValidatedPaths || []);
  const failed = records.some(record =>
    validatedPaths.has(record.path) && importer.historyValidation?.[record.path]?.ok === false);
  return {
    failed,
    disabled: Boolean(importer.inFlight || importer.historyValidating || state.initializer?.autoPipelineRunning),
    accessibleLabel: importer.historyValidating ? messages.buttons.validatingProjects : messages.buttons.validateHistoryLabel,
  };
}

export function syncProjectValidation(host, state, records) {
  const view = projectValidationView(state, records);
  host.querySelectorAll("[data-workspace-history-row-path]").forEach(row => {
    row.classList.toggle("has-validation-error",
      state.importer.historyValidation?.[row.dataset.workspaceHistoryRowPath]?.ok === false);
  });
  const validate = host.querySelector("#validate-history-button");
  if (validate) {
    validate.disabled = view.disabled;
    validate.setAttribute("data-app-tooltip", view.accessibleLabel);
    validate.setAttribute("aria-label", view.accessibleLabel);
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
  const recommendedWorkers = recommendedImportParserWorkers();
  const selectedWorkers = normalizeImportParserWorkers(importer.importParallelism);
  const workerOptions = importParserWorkerChoices().map((value) => {
    const label = value === String(recommendedWorkers)
      ? labels.recommendedThreads.replace("{number}", value)
      : value;
    return `<option value="${value}" ${value === selectedWorkers ? "selected" : ""}>${label}</option>`;
  }).join("");
  return `<div class="modal-overlay" data-project-import-overlay>
    <form class="modal-dialog project-import-dialog" role="dialog" aria-modal="true" aria-labelledby="project-import-title" autocomplete="off">
      <header class="project-dialog-head">
        <h3 id="project-import-title">${labels.importTitle}</h3>
        <button type="button" data-project-import-dismiss class="dialog-close-button" aria-label="${html(labels.cancel)}">×</button>
      </header>
      <fieldset class="project-source-switch"><legend>${labels.source}</legend>
        <label><input type="radio" name="project-source" value="zip" ${extracted ? "" : "checked"} />${labels.zip}</label>
        <label><input type="radio" name="project-source" value="extracted" ${extracted ? "checked" : ""} />${labels.extractedOption}</label>
      </fieldset>
      <label for="${extracted ? "extracted-path-input" : "zip-path-input"}">${extracted ? labels.extracted : labels.zip}</label>
      <div class="inline-input">
        <input id="${extracted ? "extracted-path-input" : "zip-path-input"}" value="${html(source)}" autocomplete="off" spellcheck="false" required />
        <button type="button" id="${extracted ? "pick-extracted-button" : "pick-zip-button"}" class="button ghost" data-app-tooltip="${labels.browse}" aria-label="${labels.browse}">${projectIcon("open")}</button>
      </div>
      ${extracted ? `<p class="project-path muted">${messages.page.importExtractedRule}</p>` : `
        <label for="zip-workspace-root-input">${importer.requireNewWorkspace ? labels.newDirectory : messages.page.workspaceDir}</label>
        <div class="inline-input"><input id="zip-workspace-root-input" value="${html(directory)}" ${importer.requireNewWorkspace ? 'aria-describedby="project-workspace-hint"' : ""} autocomplete="off" spellcheck="false" required />
          <button type="button" id="pick-zip-workspace-button" class="button ghost" data-app-tooltip="${labels.browse}" aria-label="${labels.browse}">${projectIcon("open")}</button></div>
        ${importer.requireNewWorkspace ? `<p id="project-workspace-hint" class="project-path muted">${labels.directoryHint}</p>` : ""}`}
      <label for="import-parallelism-select">${labels.importThreads}</label>
      <select id="import-parallelism-select" name="importParallelism" aria-describedby="import-parallelism-hint">${workerOptions}</select>
      <p id="import-parallelism-hint" class="project-path muted">${labels.importThreadsHint}</p>
      ${renderImportPartition(state)}
      <label for="import-project-name">${labels.name}</label>
      <input id="import-project-name" value="${html(projectImportName(importer, directory))}" placeholder="${html(labels.nameDefault)}" autocomplete="off" spellcheck="false" />
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
  const busy = projectEntryBusy(state);
  const disabled = busy ? "disabled" : "";
  const empty = !records.length && !state.session?.workspacePath;
  const collapsed = readProjectSidebarCollapsed();
  const toggleLabel = collapsed ? labels.expandSidebar : labels.collapseSidebar;
  const railTooltip = labels.switchSidebarCount.replace("{count}", records.length);
  const actions = `<div class="project-entry-actions">
    <button id="project-import-button" class="button ${empty ? "project-primary" : "ghost"}"${collapsed ? ` data-app-tooltip="${html(labels.import)}"` : ""} aria-label="${html(labels.import)}" ${disabled}>${projectIcon("import")}<span class="project-entry-label">${labels.import}</span></button>
    <button id="project-open-button" class="button ghost"${collapsed ? ` data-app-tooltip="${html(labels.open)}"` : ""} aria-label="${html(labels.open)}" ${disabled}>${projectIcon("open")}<span class="project-entry-label">${labels.open}</span></button>
    <button type="button" class="button ghost project-sidebar-toggle" data-project-sidebar-toggle data-collapse-label="${html(labels.collapseSidebar)}" data-expand-label="${html(labels.expandSidebar)}" data-app-tooltip="${html(toggleLabel)}" aria-label="${html(toggleLabel)}" aria-controls="project-recents" aria-expanded="${!collapsed}">${projectIcon(collapsed ? "sidebarExpand" : "sidebarCollapse")}</button>
  </div>
  <button type="button" class="project-sidebar-rail-count" data-project-sidebar-switcher aria-haspopup="dialog" aria-expanded="false" aria-controls="project-sidebar-flyout" data-app-tooltip="${html(railTooltip)}" aria-label="${html(railTooltip)}">${projectIcon("project")}<span>${records.length}</span></button>`;
  const validation = projectValidationView(state, records);
  const library = libraryLabels(state);
  const rows = renderLibraryTree(state, records);
  return `${importer.pendingProjectPath ? `<section class="project-pending">
    <strong>${labels.pending}</strong><span class="project-path">${html(importer.pendingProjectPath)}</span>
    <button id="project-retry-button" class="button" ${disabled}>${labels.retry}</button></section>` : ""}
  <div class="project-browser${collapsed ? " is-sidebar-collapsed" : ""}">
    <section class="project-recents" id="project-recents" aria-labelledby="project-recents-title">
      ${actions}
      <div class="project-library-panel" id="project-sidebar-flyout">
        <header class="project-recents-header" data-library-drop-root data-library-drop-root-label="${html(library.root)}"><h4 id="project-recents-title"><span class="project-recents-title-label">${labels.recent}</span><span class="project-count"><span aria-hidden="true">·</span>${records.length}</span></h4>
          <div class="project-library-toolbar project-library-actions">
            <span data-library-command="create"><button type="button" class="library-toolbar-button" data-library-create="root" aria-label="${library.create}" data-app-tooltip="${library.create}" ${disabled}>${projectIcon("newPartition")}</button></span>
            ${records.length ? `<span data-library-command="validate">
            <button id="validate-history-button" class="library-toolbar-button" data-app-tooltip="${html(validation.accessibleLabel)}" aria-label="${html(validation.accessibleLabel)}" aria-busy="${Boolean(importer.historyValidating)}" ${validation.disabled ? "disabled" : ""}>${projectIcon("validate")}</button></span>
            <span data-library-command="delete-failed"><button id="delete-failed-history-button" class="button ghost project-history-action" data-app-tooltip="${html(messages.buttons.confirmDeleteFailed)}" aria-label="${html(messages.buttons.confirmDeleteFailed)}" ${validation.disabled || !validation.failed ? "disabled" : ""} ${validation.failed ? "" : "hidden"}>${messages.buttons.deleteFailedRecords}</button></span>
            ` : ""}
            <button type="button" class="library-toolbar-button" data-library-root-menu aria-label="${library.actions}" aria-haspopup="menu" ${disabled}>${projectIcon("more")}</button>
          </div>
        </header>
        ${renderLibrarySearch(state, records)}
        <div class="project-recent-list">${rows}</div>
      </div>
    </section>
    <div class="project-sidebar-splitter" role="separator" tabindex="0" aria-orientation="vertical" aria-controls="project-recents" aria-label="${labels.resizeLibrary}" aria-valuemin="220" aria-valuemax="560" aria-valuenow="280"></div>
    ${summaryHtml || `<section class="project-empty project-no-selection"><span class="project-empty-symbol">${projectIcon(empty ? "folder" : "open")}</span><h4>${empty ? labels.empty : library.select}</h4><p class="muted">${empty ? labels.emptyHint : library.selectHint}</p></section>`}
  </div>
  ${renderProjectImportDialog(state, messages)}${renderLibraryMenu(state)}${renderLibraryDialog(state)}`;
}
