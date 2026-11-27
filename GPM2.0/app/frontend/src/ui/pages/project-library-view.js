import { bindLibraryToolbar } from "./project-library-toolbar.js";
import { getMessages } from "../i18n/index.js";
import { projectIcon } from "./project-icons.js";
import { defaultProjectName } from "../../services/project-session.js";
import { projectEntryBusy } from "../../services/project-drop-controller.js";
import { readWorkspaceHistory, workspacePathIdentity } from "../../services/workspace-history.js";
import { readProjectLibrary, saveProjectLibrary, partitionChoices, partitionAncestors, projectPartition,
  editPartition, deletePartition, partitionDeletionImpact, moveProjectToPartition, revealProjectPartition } from "../../services/project-library.js";
import { bindLibraryPointerDrag } from "./project-library-drag.js";

const html = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
export const libraryLabels = state => state.locale === "en" ? {
  unassigned: "Unassigned", root: "Library root", target: "Target project", create: "New project", child: "New subproject",
  name: "Project name", parent: "Parent project", rename: "Rename project", move: "Move to…", remove: "Delete project",
  importHere: "Import here", cancel: "Cancel", save: "Save", confirmMove: "Move", actions: "Actions", select: "Select an assembly",
  selectHint: "Open an assembly from the library, or import a new one.", collapse: "Collapse all", expand: "Expand all",
  searchPlaceholder: "Filter projects or assemblies…", clearSearch: "Clear filter", noMatches: "No matching projects or assemblies",
  dropToRoot: "Drop here to move to library root",
  importHint: "Leave the project unselected to import into Unassigned. Assembly files stay in their original location.",
  deleteHint: "This project and all its subprojects will be deleted. Their assemblies will move to Unassigned; no assembly files will be deleted.",
  deleteImpact: "Projects to delete: {partitions} (including this project). Assemblies to move: {projects}.",
  errors: { storage: "Unable to read or save the project library. Existing library data has not been replaced.", name: "Enter a name (1–120 characters).",
    missing: "The assembly or project no longer exists. Choose another destination.", cycle: "A project cannot be moved into itself or a descendant.",
    duplicate: "A project with this name already exists here." },
} : {
  unassigned: "未分配", root: "项目库根层级", target: "目标项目", create: "新建项目", child: "新建子项目",
  name: "项目名称", parent: "上级项目", rename: "重命名项目", move: "移动到…", remove: "删除项目",
  importHere: "导入到此项目", cancel: "取消", save: "保存", confirmMove: "移动", actions: "操作", select: "选择一个组装",
  selectHint: "从左侧项目库打开组装，或导入新组装。", collapse: "全部折叠", expand: "全部展开",
  searchPlaceholder: "筛选项目或组装…", clearSearch: "清除筛选", noMatches: "没有匹配的项目或组装",
  dropToRoot: "拖放到此处移至项目库根层级",
  importHint: "不选择项目时，导入到“未分配”。项目不改变组装文件的存储位置。",
  deleteHint: "删除此项目及其所有子项目，内部组装全部移到“未分配”，不会删除组装文件。",
  deleteImpact: "将删除 {partitions} 个项目（含当前项目），移动 {projects} 个组装。",
  errors: { storage: "无法读取或保存项目库，未覆盖已有项目数据。", name: "请输入 1–120 个字符的项目名称。",
    missing: "组装或项目已不存在，请重新选择目标位置。", cycle: "不能把项目移动到自身或其子项目中。",
    duplicate: "此位置已存在同名项目。" },
};

export function renderLibrarySearch(state, records, library = readProjectLibrary()) {
  const query = String(state.importer?.libraryQuery || "");
  if (!records.length && !library.partitions.length && !query) return "";
  const labels = libraryLabels(state);
  return `<div class="library-search">
    ${projectIcon("search", "library-search-icon")}
    <input type="search" class="library-search-input" data-library-search value="${html(query)}" placeholder="${html(labels.searchPlaceholder)}" aria-label="${html(labels.searchPlaceholder)}" autocomplete="off" spellcheck="false" />
    <button type="button" class="library-search-clear" data-library-search-clear aria-label="${html(labels.clearSearch)}" ${query ? "" : "hidden"}>${projectIcon("close")}</button>
  </div>`;
}

export function partitionOptions(library, selected, rootLabel, excludeId = "") {
  return `<option value="">${html(rootLabel)}</option>` + partitionChoices(library, excludeId)
    .map(node => `<option value="${html(node.id)}" ${node.id === selected ? "selected" : ""}>${html(node.path)}</option>`).join("");
}

export function renderImportPartition(state) {
  const labels = libraryLabels(state), library = readProjectLibrary();
  return `<label for="import-partition">${labels.target}</label><div class="library-picker-row">
    <select id="import-partition" aria-describedby="import-partition-hint">${partitionOptions(library, state.importer.importPartitionId, labels.unassigned)}</select>
    <button type="button" class="button ghost" data-library-create="import">${projectIcon("newPartition")}${labels.create}</button>
    </div><p id="import-partition-hint" class="project-path muted">${labels.importHint}</p>`;
}

const menuCleanups = new WeakMap();

export function renderLibraryTree(state, records, library = readProjectLibrary()) {
  const labels = libraryLabels(state), busy = projectEntryBusy(state), disabled = busy ? "disabled" : "";
  const activePath = workspacePathIdentity(state.session?.workspacePath);
  const query = String(state.importer?.libraryQuery || "").trim().toLowerCase();
  const renamingId = String(state.importer?.libraryRenamingId || "");
  const renameError = String(state.importer?.libraryRenameError || "");
  const folders = new Map(), projects = new Map();
  const recordIndices = new Map(records.map((record, index) => [record, index]));
  for (const node of library.partitions) {
    if (!folders.has(node.parentId)) folders.set(node.parentId, []);
    folders.get(node.parentId).push(node);
  }
  for (const record of records) {
    const id = projectPartition(library, record);
    if (!projects.has(id)) projects.set(id, []);
    projects.get(id).push(record);
  }
  const projectName = record => (workspacePathIdentity(record.path) === activePath && state.session?.projectName)
    || record.projectName || defaultProjectName(record.path);
  const sortedProjects = id => [...(projects.get(id) || [])].sort((a, b) => projectName(a).localeCompare(projectName(b), state.locale, { numeric: true }));
  const totalCountMemo = new Map();
  const subtreeCount = (id, system = false) => {
    const key = system ? "__root__" : id;
    if (totalCountMemo.has(key)) return totalCountMemo.get(key);
    let count = (projects.get(id) || []).length;
    if (!system) {
      for (const child of folders.get(id) || []) count += subtreeCount(child.id, false);
    }
    totalCountMemo.set(key, count);
    return count;
  };
  let anyVisible = false;
  const row = (record, level, partitionId, forceVisible) => {
    const active = workspacePathIdentity(record.path) === activePath;
    const validation = state.importer.historyValidation?.[record.path];
    const failed = validation?.ok === false;
    const name = projectName(record);
    const searchText = `${name}\n${record.path}`;
    const visible = !query || forceVisible || searchText.toLowerCase().includes(query);
    if (visible) anyVisible = true;
    const tooltip = failed && validation?.message ? `${record.path} — ${validation.message}` : record.path;
    return {
      visible,
      markup: `<div role="treeitem" aria-level="${level}" aria-selected="${active}" class="project-recent-row ${active ? "is-active" : ""}${failed ? " has-validation-error" : ""}" data-workspace-history-row-path="${html(record.path)}" data-library-drag-project="${html(record.path)}" data-library-partition-id="${html(partitionId)}" data-library-search-text="${html(searchText)}" style="--library-depth:${level - 1}" ${visible ? "" : "hidden"}>
      <button class="project-recent-open" data-recent-index="${recordIndices.get(record)}" data-recent-path="${html(record.path)}" aria-current="${active}" data-app-tooltip="${html(tooltip)}" ${disabled}>
        <span class="project-recent-name">${projectIcon("project")}<strong>${html(name)}</strong></span>
      </button><button type="button" class="library-row-menu" data-library-project-menu="${html(record.path)}" aria-label="${html(labels.actions)}: ${html(name)}" aria-haspopup="menu" ${disabled}>${projectIcon("more")}</button>
    </div>`,
    };
  };
  const group = (id, name, level, system = false, ancestorMatched = false) => {
    const children = [...(system ? [] : folders.get(id) || [])].sort((a, b) => a.name.localeCompare(b.name, state.locale, { numeric: true }));
    const items = sortedProjects(id);
    const hasChildren = Boolean(children.length || items.length);
    const totalCount = subtreeCount(id, system);
    const selfMatch = Boolean(query && name.toLowerCase().includes(query));
    const childForceVisible = ancestorMatched || (selfMatch && !system);
    const renderedChildren = children.map(node => group(node.id, node.name, level + 1, false, childForceVisible));
    const renderedItems = items.map(record => row(record, level + 1, id, childForceVisible));
    const visible = !query || renderedChildren.some(child => child.visible) || renderedItems.some(item => item.visible)
      || (selfMatch && (!system || items.length > 0));
    if (visible) anyVisible = true;
    const expanded = query ? visible : !library.collapsed.includes(id);
    const renaming = !system && renamingId === id;
    const folderIcon = system
      ? projectIcon("inbox", "library-icon-system")
      : `${projectIcon("folder", "library-icon-closed")}${projectIcon("open", "library-icon-open")}`;
    const quickLabel = system ? labels.importHere : labels.child;
    const rowContent = renaming
      ? `<form class="library-inline-rename" data-library-inline-rename-form="${html(id)}" autocomplete="off">${projectIcon("folder", "library-icon-closed")}<input type="text" class="library-inline-rename-input" data-library-inline-rename="${html(id)}" value="${html(name)}" maxlength="120" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" aria-label="${html(labels.rename)}" /></form>`
      : `<button type="button" class="library-folder-name" data-library-select="${html(id)}" data-app-tooltip="${html(name)}" data-app-tooltip-overflow="span">${folderIcon}<span>${html(name)}</span>${totalCount > 0 ? `<small class="library-folder-count" aria-hidden="true">${totalCount}</small>` : ""}</button>
        <div class="library-folder-actions">
          <button type="button" class="library-row-action" data-library-quick-add="${html(id)}" aria-label="${html(quickLabel)}: ${html(name)}" data-app-tooltip="${html(quickLabel)}" ${disabled}>${projectIcon(system ? "import" : "plus")}</button>
          <button type="button" class="library-row-menu" data-library-folder-menu="${html(id)}" aria-label="${html(labels.actions)}: ${html(name)}" aria-haspopup="menu" ${disabled}>${projectIcon("more")}</button>
        </div>`;
    return {
      visible,
      markup: `<div role="treeitem" aria-level="${level}" ${hasChildren ? `aria-expanded="${expanded}"` : ""} data-library-group="${html(id)}" data-library-group-name="${html(name)}" ${system ? 'data-library-system="1"' : ""} ${visible ? "" : "hidden"}>
      <div class="library-folder-row${system ? " is-system" : ""}${!hasChildren ? " is-empty" : ""}${renaming ? " is-renaming" : ""}${state.importer.librarySelectedId === id ? " is-selected" : ""}" data-library-folder="${html(id)}" ${system ? "" : `data-library-drag-folder="${html(id)}"`} style="--library-depth:${level - 1}">
        <button type="button" class="library-chevron ${hasChildren ? "" : "is-empty"}" data-library-toggle="${html(id)}" aria-label="${html(name)}" ${hasChildren ? `aria-expanded="${expanded}"` : 'disabled aria-hidden="true" tabindex="-1"'}>${projectIcon("chevron")}</button>
        ${rowContent}
      </div>${renaming && renameError ? `<p class="library-inline-error error-text" role="alert">${html(labels.errors[renameError] || labels.errors.storage)}</p>` : ""}<div style="--library-depth:${level - 1}" role="group" ${expanded ? "" : "hidden"}>${renderedChildren.map(child => child.markup).join("")}${renderedItems.map(item => item.markup).join("")}</div>
    </div>`,
    };
  };
  const rootGroups = [
    group("", labels.unassigned, 1, true, false),
    ...(folders.get("") || []).sort((a, b) => a.name.localeCompare(b.name, state.locale, { numeric: true })).map(node => group(node.id, node.name, 1, false, false)),
  ];
  const noMatchHidden = !query || anyVisible ? "hidden" : "";
  return `${library.error || state.importer.libraryError ? `<p class="error-text" role="alert">${html(labels.errors[library.error || state.importer.libraryError] || labels.errors.storage)}</p>` : ""}
    <div class="library-tree" role="tree" aria-label="${html(state.locale === "en" ? "Project library" : "项目库")}">
    ${rootGroups.map(entry => entry.markup).join("")}
    <div class="library-search-empty" data-library-search-empty ${noMatchHidden}><p class="muted">${html(labels.noMatches)}</p><button type="button" class="button ghost" data-library-search-clear>${html(labels.clearSearch)}</button></div>
    <div class="library-root-dropzone" data-library-drop-root data-library-drop-root-label="${html(labels.root)}" aria-hidden="true">${projectIcon("arrow")}<span>${html(labels.dropToRoot)}</span></div></div>`;
}

export function renderLibraryDialog(state) {
  const dialog = state.importer.libraryDialog;
  if (!dialog) return "";
  const labels = libraryLabels(state), library = readProjectLibrary();
  const node = library.partitions.find(node => node.id === dialog.id);
  const creating = dialog.kind === "create", editing = creating || dialog.kind === "rename";
  const removing = dialog.kind === "delete";
  const title = creating ? labels.create : dialog.kind === "rename" ? labels.rename : removing ? labels.remove : labels.move;
  const deleteError = removing ? library.error || (!node ? "missing" : "") : "";
  const impact = removing && !deleteError ? partitionDeletionImpact(library, dialog.id, readWorkspaceHistory()) : null;
  return `<div class="modal-overlay library-dialog-overlay"><form class="modal-dialog library-dialog" role="dialog" aria-modal="true" aria-labelledby="library-dialog-title" autocomplete="off">
    <header class="project-dialog-head">
      <h3 id="library-dialog-title">${title}</h3>
      <button type="button" data-library-dialog-dismiss class="dialog-close-button" aria-label="${html(labels.cancel)}">×</button>
    </header>
    ${editing ? `<label for="library-name">${labels.name}</label><input id="library-name" maxlength="120" required autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" value="${html(dialog.name ?? node?.name ?? "")}" />` : `<p class="library-dialog-subject">${html(node?.name || dialog.projectName || dialog.path || "")}</p>`}
    ${removing ? `<p>${labels.deleteHint}</p>${impact ? `<p class="library-delete-impact">${labels.deleteImpact.replace("{partitions}", impact.ids.length).replace("{projects}", impact.projectCount)}</p>` : ""}` : `<label for="library-target">${editing || dialog.kind === "move-folder" ? labels.parent : labels.target}</label>
    <select id="library-target">${partitionOptions(library, dialog.parentId ?? node?.parentId ?? "", dialog.kind === "move-project" ? labels.unassigned : labels.root, dialog.id)}</select>`}
    ${dialog.error || deleteError ? `<p class="error-text" role="alert">${html(labels.errors[dialog.error || deleteError] || labels.errors.storage)}</p>` : ""}
    <footer class="project-dialog-actions"><button type="button" class="button ghost" data-library-dialog-close>${labels.cancel}</button>
    <button type="submit" class="button project-primary" ${deleteError ? "disabled" : ""}>${removing ? labels.remove : editing ? labels.save : labels.confirmMove}</button></footer>
    </form></div>`;
}

export function renderLibraryMenu(state) {
  const menu = state.importer.libraryMenu;
  if (!menu) return "";
  const labels = libraryLabels(state);
  const messages = getMessages(state, "importer");
  const overflow = state.importer.libraryOverflowActions || [];
  const icons = { create: "newPartition", validate: "validate", "delete-failed": "delete", collapse: "collapse", expand: "expand",
    import: "import", rename: "rename", "move-folder": "arrow", delete: "delete" };
  const content = (action, label) => `${projectIcon(icons[action])}<span>${html(label)}</span>`;
  const extra = (action, label, danger = false) => `<button type="button" role="menuitem" class="context-menu-item${danger ? " is-danger" : ""}" data-library-action="${action}" data-library-overflow-action="${action}" ${overflow.includes(action) ? "" : "hidden"} ${projectEntryBusy(state) || (action !== "create" && state.importer.historyValidating) ? "disabled" : ""}>${content(action, label)}</button>`;
  const item = (action, label, danger = false) => `<button type="button" role="menuitem" class="context-menu-item${danger ? " is-danger" : ""}" data-library-action="${action}">${content(action, label)}</button>`;
  return `<div class="context-menu workspace-history-context-menu" data-library-menu role="menu" aria-label="${labels.actions}" style="left:${Number(menu.x) || 0}px;top:${Number(menu.y) || 0}px">
    ${menu.root ? `${extra("create", labels.create)}${extra("validate", messages.buttons.validateHistory)}${extra("delete-failed", messages.buttons.deleteFailedRecords, true)}${item("collapse", labels.collapse)}${item("expand", labels.expand)}` : `${item("import", labels.importHere)}${menu.id ? `${item("create", labels.child)}<div role="separator" class="workspace-history-context-menu-separator"></div>${item("rename", labels.rename)}${item("move-folder", labels.move)}<div role="separator" class="workspace-history-context-menu-separator"></div>${item("delete", labels.remove, true)}` : ""}`}</div>`;
}

function applyInPlaceLibraryFilter(host, query) {
  const tree = host.querySelector(".library-tree");
  if (!tree?.querySelectorAll) return;
  const q = String(query || "").trim().toLowerCase();
  const library = readProjectLibrary();
  const collapsedSet = new Set(library.collapsed || []);
  const topGroups = [...tree.querySelectorAll(":scope > [data-library-group]")];
  let anyVisible = false;
  const walk = (group, ancestorMatched) => {
    const id = group.dataset.libraryGroup || "";
    const name = String(group.dataset.libraryGroupName || "");
    const isSystem = group.dataset.librarySystem === "1";
    const childrenWrap = group.querySelector(":scope > [role=group]");
    const childGroups = childrenWrap ? [...childrenWrap.querySelectorAll(":scope > [data-library-group]")] : [];
    const directRows = childrenWrap ? [...childrenWrap.querySelectorAll(":scope > [data-workspace-history-row-path]")] : [];
    const hasChildren = Boolean(childGroups.length || directRows.length);
    if (!q) {
      group.hidden = false;
      directRows.forEach(row => { row.hidden = false; });
      childGroups.forEach(child => walk(child, false));
      const expanded = !collapsedSet.has(id);
      if (hasChildren) {
        group.setAttribute("aria-expanded", String(expanded));
        if (childrenWrap) childrenWrap.hidden = !expanded;
        group.querySelector("[data-library-toggle]")?.setAttribute("aria-expanded", String(expanded));
      }
      return true;
    }
    const selfMatch = name.toLowerCase().includes(q);
    const forceChildren = ancestorMatched || (selfMatch && !isSystem);
    let childVisible = false;
    for (const child of childGroups) {
      if (walk(child, forceChildren)) childVisible = true;
    }
    let rowVisible = false;
    for (const row of directRows) {
      const text = String(row.dataset.librarySearchText || "").toLowerCase();
      const match = forceChildren || text.includes(q);
      row.hidden = !match;
      if (match) rowVisible = true;
    }
    const visible = childVisible || rowVisible || (selfMatch && (!isSystem || directRows.length > 0));
    group.hidden = !visible;
    if (visible && hasChildren) {
      group.setAttribute("aria-expanded", "true");
      if (childrenWrap) childrenWrap.hidden = false;
      group.querySelector("[data-library-toggle]")?.setAttribute("aria-expanded", "true");
    }
    return visible;
  };
  for (const group of topGroups) {
    if (walk(group, false)) anyVisible = true;
  }
  const emptyNode = tree.querySelector("[data-library-search-empty]");
  if (emptyNode) emptyNode.hidden = !q || anyVisible;
}

export function bindProjectLibrary(host, store, { refresh, openImport, openProjectMenu }) {
  menuCleanups.get(host)?.();
  menuCleanups.delete(host);
  const patch = value => store.setState({ importer: { ...store.getState().importer, ...value } });
  const error = cause => { patch({ libraryError: cause.message || "storage" }); refresh(); };
  const focusRow = (attribute, value) => [...host.querySelectorAll(`[${attribute}]`)].find(row => row.getAttribute(attribute) === value)?.focus();
  const openDialog = dialog => {
    patch({ libraryDialog: dialog, libraryMenu: null, workspaceContextMenu: null, libraryRenamingId: "", libraryRenameError: "", libraryError: "" }); refresh();
    host.querySelector("#library-name, #library-target, [data-library-dialog-close]")?.focus();
  };
  const startInlineRename = id => {
    if (!id || projectEntryBusy(store.getState())) return;
    patch({ libraryMenu: null, workspaceContextMenu: null, libraryRenamingId: id, libraryRenameError: "" });
    refresh();
    const input = host.querySelector("[data-library-inline-rename]");
    input?.focus();
    input?.select?.();
  };
  const reveal = id => {
    try {
      const library = readProjectLibrary();
      const ancestors = new Set(id ? partitionAncestors(library, id).map(node => node.id) : [""]);
      const collapsed = library.collapsed.filter(value => !ancestors.has(value));
      if (collapsed.length !== library.collapsed.length) saveProjectLibrary({ ...library, collapsed });
      return "";
    } catch (cause) {
      // The mutation is already committed. A preference failure must not invite a duplicate retry.
      return cause.message || "storage";
    }
  };
  const move = (source, target) => {
    if (source.kind === "project") moveProjectToPartition(source.id, target);
    else saveProjectLibrary(editPartition(readProjectLibrary(), { id: source.id, parentId: target }));
    patch({ libraryError: reveal(target) }); refresh();
  };
  host.querySelectorAll("[data-library-create]").forEach(button => button.addEventListener("click", () => {
    if (projectEntryBusy(store.getState()) && button.dataset.libraryCreate !== "import") return;
    openDialog({ kind: "create", parentId: button.dataset.libraryCreate === "import" ? store.getState().importer.importPartitionId || "" : "", forImport: button.dataset.libraryCreate === "import" });
  }));
  host.querySelector("#import-partition")?.addEventListener("change", event => patch({ importPartitionId: event.target.value }));
  host.querySelectorAll("[data-library-quick-add]").forEach(button => button.addEventListener("click", event => {
    event.stopPropagation();
    if (projectEntryBusy(store.getState())) return;
    const id = button.dataset.libraryQuickAdd || "";
    if (!id) openImport("");
    else openDialog({ kind: "create", parentId: id });
  }));
  const searchInput = host.querySelector("[data-library-search]");
  const searchClearButtons = host.querySelectorAll("[data-library-search-clear]");
  const updateSearch = value => {
    patch({ libraryQuery: value });
    if (searchInput && searchInput.value !== value) searchInput.value = value;
    const inlineClear = host.querySelector(".library-search [data-library-search-clear]");
    if (inlineClear) inlineClear.hidden = !value;
    applyInPlaceLibraryFilter(host, value);
  };
  searchInput?.addEventListener("input", event => updateSearch(event.target.value));
  searchInput?.addEventListener("keydown", event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Escape" && searchInput.value) {
      event.preventDefault();
      updateSearch("");
    } else if (event.key === "Enter") {
      const first = [...host.querySelectorAll(".library-tree [data-recent-path], .library-tree [data-library-select]")].find(node => !node.closest("[hidden]"));
      if (first) { event.preventDefault(); first.focus(); }
    }
  });
  searchClearButtons.forEach(button => button.addEventListener("click", () => {
    updateSearch("");
    searchInput?.focus();
  }));
  host.querySelectorAll("[data-library-project-menu]").forEach(button => button.addEventListener("click", event => {
    const path = button.dataset.libraryProjectMenu;
    const current = store.getState().importer.workspaceContextMenu;
    event.stopPropagation();
    if (current?.open && current.workspacePath === path && current.alignRight) {
      patch({ workspaceContextMenu: null });
      host.querySelector("[data-workspace-history-context-menu='1']")?.remove?.();
      return;
    }
    const rect = button.getBoundingClientRect();
    openProjectMenu({ preventDefault() {}, clientX: rect.right, clientY: rect.bottom + 4, alignRight: true, anchorTop: rect.top }, path);
  }));
  host.querySelectorAll("[data-project-move-path]").forEach(button => button.addEventListener("click", () => {
    if (projectEntryBusy(store.getState())) return;
    const record = readWorkspaceHistory().find(item => item.path === button.dataset.projectMovePath);
    openDialog({ kind: "move-project", path: button.dataset.projectMovePath, projectName: record?.projectName || defaultProjectName(button.dataset.projectMovePath), parentId: record ? projectPartition(readProjectLibrary(), record) : "" });
  }));
  const showMenu = (event, id, root = false, alignRight = false) => {
    event.preventDefault(); event.stopPropagation();
    if (projectEntryBusy(store.getState())) return;
    const existing = store.getState().importer.libraryMenu;
    if (alignRight && existing && Boolean(existing.root) === Boolean(root) && (existing.id || "") === (id || "")) {
      patch({ libraryMenu: null });
      host.querySelector("[data-library-menu]")?.remove?.();
      return;
    }
    patch({ libraryMenu: { id, root, x: event.clientX, y: event.clientY, alignRight, anchorTop: event.anchorTop }, workspaceContextMenu: null }); refresh();
    host.querySelector("[data-library-menu] [role=menuitem]:not([hidden]):not(:disabled)")?.focus();
  };
  host.querySelector("[data-library-root-menu]")?.addEventListener("click", event => {
    const rect = event.currentTarget.getBoundingClientRect();
    showMenu({ preventDefault() {}, stopPropagation() {}, clientX: rect.right, clientY: rect.bottom + 4, anchorTop: rect.top }, "", true, true);
  });
  host.querySelectorAll("[data-library-folder]").forEach(row => {
    row.addEventListener("contextmenu", event => showMenu(event, row.dataset.libraryFolder));
    row.querySelector("[data-library-folder-menu]")?.addEventListener("click", event => {
      const rect = event.currentTarget.getBoundingClientRect();
      showMenu({ preventDefault() {}, stopPropagation() {}, clientX: rect.right, clientY: rect.bottom + 4, anchorTop: rect.top }, row.dataset.libraryFolder, false, true);
    });
  });
  const renameForm = host.querySelector("[data-library-inline-rename-form]");
  if (renameForm) {
    const id = renameForm.dataset.libraryInlineRenameForm;
    const input = renameForm.querySelector("[data-library-inline-rename]");
    let settled = false;
    const cancel = () => {
      if (settled) return;
      settled = true;
      patch({ libraryRenamingId: "", libraryRenameError: "" });
      refresh();
      focusRow("data-library-select", id);
    };
    const commit = (fromBlur = false) => {
      if (settled) return;
      const library = readProjectLibrary();
      const currentNode = library.partitions.find(node => node.id === id);
      if (!currentNode) { cancel(); return; }
      const nextName = String(input?.value || "").trim();
      if (nextName === currentNode.name || (fromBlur && !nextName)) { cancel(); return; }
      try {
        const next = editPartition(library, { id, name: nextName, parentId: currentNode.parentId });
        saveProjectLibrary(next);
        settled = true;
        patch({ libraryRenamingId: "", libraryRenameError: "", libraryError: "" });
        refresh();
        focusRow("data-library-select", id);
      } catch (cause) {
        if (fromBlur) { cancel(); return; }
        settled = true;
        patch({ libraryRenameError: cause.message || "storage" });
        refresh();
        const retryInput = host.querySelector("[data-library-inline-rename]");
        if (retryInput) { retryInput.value = input?.value || ""; retryInput.focus(); retryInput.select?.(); }
      }
    };
    renameForm.addEventListener("submit", event => { event.preventDefault(); commit(false); });
    input?.addEventListener("keydown", event => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); cancel(); }
    });
    input?.addEventListener("blur", () => commit(true));
  }
  const toggle = (id, expand) => {
    const library = readProjectLibrary();
    const collapsed = new Set(library.collapsed);
    const nextExpanded = expand ?? collapsed.has(id);
    if (nextExpanded) collapsed.delete(id); else collapsed.add(id);
    saveProjectLibrary({ ...library, collapsed: [...collapsed] });
    const group = [...host.querySelectorAll("[data-library-group]")].find(node => node.dataset.libraryGroup === id);
    if (group) {
      if (group.hasAttribute("aria-expanded")) group.setAttribute("aria-expanded", String(nextExpanded));
      group.querySelector(":scope > [role=group]").hidden = !nextExpanded;
      group.querySelector("[data-library-toggle]")?.setAttribute("aria-expanded", String(nextExpanded));
    }
  };
  // Session restoration or switching from the global header must also reveal its location.
  const activePath = store.getState().session?.workspacePath;
  if (activePath && store.getState().importer.libraryRevealedPath !== activePath) {
    try {
      if (revealProjectPartition(activePath)) {
        const library = readProjectLibrary();
        host.querySelectorAll("[data-library-group]").forEach(group => {
          const expanded = !library.collapsed.includes(group.dataset.libraryGroup);
          if (group.hasAttribute("aria-expanded")) group.setAttribute("aria-expanded", String(expanded));
          group.querySelector(":scope > [role=group]").hidden = !expanded;
          group.querySelector("[data-library-toggle]")?.setAttribute("aria-expanded", String(expanded));
        });
      }
    } catch (cause) { patch({ libraryError: cause.message || "storage" }); }
    patch({ libraryRevealedPath: activePath });
  }
  host.querySelectorAll("[data-library-toggle]").forEach(button => button.addEventListener("click", () => {
    try { toggle(button.dataset.libraryToggle); } catch (cause) { error(cause); }
  }));
  host.querySelectorAll("[data-library-select]").forEach(button => button.addEventListener("click", () => {
    host.querySelectorAll(".library-folder-row.is-selected").forEach(row => row.classList.remove("is-selected"));
    button.closest(".library-folder-row").classList.add("is-selected");
    patch({ librarySelectedId: button.dataset.librarySelect });
    try { toggle(button.dataset.librarySelect); } catch (cause) { error(cause); }
  }));
  host.querySelectorAll("[data-recent-path]").forEach(button => button.addEventListener("click", () => {
    if (store.getState().importer.librarySelectedId !== null) {
      host.querySelectorAll(".library-folder-row.is-selected").forEach(row => row.classList.remove("is-selected"));
      patch({ librarySelectedId: null });
    }
  }));
  host.querySelector(".library-tree")?.addEventListener("keydown", event => {
    if (!event.target.matches("[data-library-select], [data-recent-path]")) return;
    const buttons = [...host.querySelectorAll(".library-tree [data-library-select], .library-tree [data-recent-path]")].filter(button => !button.closest("[hidden]"));
    const index = buttons.indexOf(event.target);
    const group = event.target.closest("[data-library-group]");
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      buttons[event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))]?.focus();
    } else if (group && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      try {
        if (event.key === "ArrowLeft" && (event.target.matches("[data-recent-path]") || group.getAttribute("aria-expanded") !== "true")) {
          const parent = event.target.matches("[data-recent-path]") ? group : group.parentElement.closest("[data-library-group]");
          parent?.querySelector("[data-library-select]")?.focus();
        } else if (event.key === "ArrowRight" && group.getAttribute("aria-expanded") === "true") buttons[index + 1]?.focus();
        else toggle(group.dataset.libraryGroup, event.key === "ArrowRight");
      } catch (cause) { error(cause); }
    } else if (event.key === "F2" && event.target.matches("[data-library-select]") && event.target.dataset.librarySelect) {
      event.preventDefault();
      startInlineRename(event.target.dataset.librarySelect);
    } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      const rect = event.target.getBoundingClientRect(); event.preventDefault();
      const coordinates = { preventDefault() {}, stopPropagation() {}, clientX: rect.left, clientY: rect.bottom };
      if (event.target.matches("[data-recent-path]")) openProjectMenu(coordinates, event.target.dataset.recentPath);
      else showMenu(coordinates, group.dataset.libraryGroup);
    }
  });
  const menu = host.querySelector("[data-library-menu]");
  if (menu) {
    const currentMenu = store.getState().importer.libraryMenu;
    const bounds = menu.getBoundingClientRect();
    const rawLeft = currentMenu?.alignRight ? bounds.left - bounds.width : bounds.left;
    let rawTop = bounds.top;
    if (currentMenu?.anchorTop != null && rawTop + bounds.height > window.innerHeight - 8 && currentMenu.anchorTop - bounds.height - 4 >= 8) {
      rawTop = currentMenu.anchorTop - bounds.height - 4;
    }
    menu.style.left = `${Math.max(8, Math.min(rawLeft, window.innerWidth - bounds.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rawTop, window.innerHeight - bounds.height - 8))}px`;
    const doc = menu.ownerDocument || globalThis.document;
    const view = doc?.defaultView || globalThis.window;
    const scroller = host.querySelector(".project-recent-list");
    const cleanup = () => {
      doc?.removeEventListener?.("pointerdown", onOutsidePointerDown, true);
      view?.removeEventListener?.("blur", onDismiss);
      view?.removeEventListener?.("resize", onDismiss);
      scroller?.removeEventListener?.("scroll", onDismiss);
      menuCleanups.delete(host);
    };
    const dismiss = () => { cleanup(); patch({ libraryMenu: null }); menu.remove(); };
    const onDismiss = () => dismiss();
    const onOutsidePointerDown = event => {
      if (menu.contains(event.target)) return;
      if (event.target?.closest?.("[data-library-root-menu], [data-library-folder-menu]")) return;
      dismiss();
    };
    doc?.addEventListener?.("pointerdown", onOutsidePointerDown, true);
    view?.addEventListener?.("blur", onDismiss);
    view?.addEventListener?.("resize", onDismiss);
    scroller?.addEventListener?.("scroll", onDismiss);
    menuCleanups.set(host, cleanup);
    menu.addEventListener("focusout", event => { if (event.relatedTarget && !menu.contains(event.relatedTarget)) dismiss(); });
    menu.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        const current = store.getState().importer.libraryMenu;
        dismiss();
        if (current?.root) host.querySelector("[data-library-root-menu]")?.focus();
        else focusRow("data-library-select", current?.id || "");
      }
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault(); const items = [...menu.querySelectorAll("[role=menuitem]:not([hidden]):not(:disabled)")], index = items.indexOf(event.target);
        items[(index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
      }
    });
    menu.querySelectorAll("[data-library-action]").forEach(button => button.addEventListener("click", () => {
      const current = store.getState().importer.libraryMenu; if (!current) return;
      const action = button.dataset.libraryAction;
      if (button.hidden || button.disabled) return;
      cleanup();
      if (["validate", "delete-failed"].includes(action)) {
        patch({ libraryMenu: null }); menu.remove();
        host.querySelector(action === "validate" ? "#validate-history-button" : "#delete-failed-history-button")?.click();
        return;
      }
      if (action === "import") { patch({ libraryMenu: null }); openImport(current.id); return; }
      if (action === "rename") { startInlineRename(current.id); return; }
      if (["collapse", "expand"].includes(action)) {
        try { const library = readProjectLibrary(); saveProjectLibrary({ ...library, collapsed: action === "collapse" ? ["", ...library.partitions.map(node => node.id)] : [] }); patch({ libraryMenu: null }); refresh(); }
        catch (cause) { error(cause); } return;
      }
      openDialog(action === "create" ? { kind: "create", parentId: current.id } : { kind: action, id: current.id });
    }));
  }
  const dialog = host.querySelector(".library-dialog");
  if (dialog) {
    // The import form stays mounted under its child dialog but must not receive keyboard input.
    const importOverlay = host.querySelector("[data-project-import-overlay]");
    if (importOverlay) { importOverlay.inert = true; importOverlay.setAttribute("aria-hidden", "true"); }
    const close = () => {
      const forImport = store.getState().importer.libraryDialog?.forImport;
      patch({ libraryDialog: null }); refresh();
      host.querySelector(forImport ? "#import-partition" : "[data-library-create]")?.focus();
    };
    dialog.querySelector("[data-library-dialog-close]").addEventListener("click", close);
    dialog.querySelector("[data-library-dialog-dismiss]")?.addEventListener("click", close);
    dialog.addEventListener("keydown", event => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
      if (event.key === "Tab") {
        const items = [...dialog.querySelectorAll("input,select,button")].filter(item => !item.disabled);
        if (event.target === (event.shiftKey ? items[0] : items.at(-1))) { event.preventDefault(); (event.shiftKey ? items.at(-1) : items[0])?.focus(); }
      }
    });
    dialog.addEventListener("submit", event => {
      event.preventDefault();
      const current = store.getState().importer.libraryDialog;
      const name = dialog.querySelector("#library-name")?.value, parentId = dialog.querySelector("#library-target")?.value || "";
      try {
        if (current.kind === "move-project") moveProjectToPartition(current.path, parentId);
        else {
          const library = readProjectLibrary();
          const next = current.kind === "delete" ? deletePartition(library, current.id, readWorkspaceHistory())
            : editPartition(library, { id: current.id, name, parentId });
          saveProjectLibrary(next);
          if (current.kind === "delete") {
            const remaining = new Set(next.partitions.map(node => node.id));
            const importer = store.getState().importer;
            patch({
              librarySelectedId: remaining.has(importer.librarySelectedId) ? importer.librarySelectedId : "",
              importPartitionId: remaining.has(importer.importPartitionId) ? importer.importPartitionId : "",
            });
          }
          if (current.forImport) patch({ importPartitionId: next.partitions.at(-1).id });
        }
        const revealError = current.kind !== "delete" ? reveal(parentId) : "";
        patch({ libraryDialog: null, libraryError: revealError }); refresh();
        if (current.forImport) host.querySelector("#import-partition")?.focus();
        else focusRow("data-library-select", current.kind === "delete" ? "" : current.kind === "move-project" ? parentId : current.id || "");
      } catch (cause) {
        patch({ libraryDialog: { ...current, name, parentId, error: cause.message || "storage" } }); refresh();
        host.querySelector("#library-name, #library-target, [data-library-dialog-close]")?.focus();
      }
    });
  }
  bindLibraryToolbar(host, actions => {
    if (JSON.stringify(actions) !== JSON.stringify(store.getState().importer.libraryOverflowActions || [])) patch({ libraryOverflowActions: actions });
  });
  bindLibraryPointerDrag(host, { busy: () => projectEntryBusy(store.getState()), move, error, toggle });
}
