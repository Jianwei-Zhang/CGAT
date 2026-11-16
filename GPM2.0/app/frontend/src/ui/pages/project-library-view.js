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
  unassigned: "Unpartitioned", root: "Library root", target: "Target partition", create: "New partition", child: "New subpartition",
  name: "Partition name", parent: "Parent partition", rename: "Rename partition", move: "Move to…", remove: "Delete partition",
  importHere: "Import here", cancel: "Cancel", save: "Save", confirmMove: "Move", actions: "Actions", select: "Select a project",
  selectHint: "Open a project from the library, or import a new one.", collapse: "Collapse all", expand: "Expand all",
  importHint: "Leave unpartitioned to import without a category. Project files stay in their original location.",
  deleteHint: "This partition and all its subpartitions will be deleted. Their projects will move to Unpartitioned; no project files will be deleted.",
  deleteImpact: "Partitions to delete: {partitions} (including this partition). Projects to move: {projects}.",
  errors: { storage: "Unable to read or save the project library. Existing library data has not been replaced.", name: "Enter a name (1–120 characters).",
    missing: "The project or partition no longer exists. Choose another destination.", cycle: "A partition cannot be moved into itself or a descendant.",
    duplicate: "A partition with this name already exists here." },
} : {
  unassigned: "未分区", root: "项目库根层级", target: "目标分区", create: "新建分区", child: "新建子分区",
  name: "分区名称", parent: "上级分区", rename: "重命名分区", move: "移动到…", remove: "删除分区",
  importHere: "导入到此分区", cancel: "取消", save: "保存", confirmMove: "移动", actions: "操作", select: "选择一个项目",
  selectHint: "从左侧项目库打开项目，或导入新项目。", collapse: "全部折叠", expand: "全部展开",
  importHint: "不选择分区时，导入到“未分区”。分区不改变项目文件的存储位置。",
  deleteHint: "删除此分区及其所有子分区，内部项目全部移到“未分区”，不会删除项目文件。",
  deleteImpact: "将删除 {partitions} 个分区（含当前分区），移动 {projects} 个项目。",
  errors: { storage: "无法读取或保存项目库，未覆盖已有分区数据。", name: "请输入 1–120 个字符的分区名称。",
    missing: "项目或分区已不存在，请重新选择目标位置。", cycle: "不能把分区移动到自身或其子分区中。",
    duplicate: "此位置已存在同名分区。" },
};

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

export function renderLibraryTree(state, records, library = readProjectLibrary()) {
  const labels = libraryLabels(state), busy = projectEntryBusy(state), disabled = busy ? "disabled" : "";
  const activePath = workspacePathIdentity(state.session?.workspacePath);
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
  const row = (record, level) => {
    const active = workspacePathIdentity(record.path) === activePath;
    const failed = state.importer.historyValidation?.[record.path]?.ok === false;
    return `<div role="treeitem" aria-level="${level}" aria-selected="${active}" class="project-recent-row ${active ? "is-active" : ""}${failed ? " has-validation-error" : ""}" data-workspace-history-row-path="${html(record.path)}" data-library-drag-project="${html(record.path)}" style="--library-depth:${level - 1}">
      <button class="project-recent-open" data-recent-index="${recordIndices.get(record)}" data-recent-path="${html(record.path)}" aria-current="${active}" data-app-tooltip="${html(record.path)}" ${disabled}>
        <span class="project-recent-name">${projectIcon("project")}<strong>${html(projectName(record))}</strong></span>
      </button><button type="button" class="library-row-menu" data-library-project-menu="${html(record.path)}" aria-label="${html(labels.actions)}: ${html(projectName(record))}" aria-haspopup="menu" ${disabled}>${projectIcon("more")}</button>
    </div>`;
  };
  const group = (id, name, level, system = false) => {
    const children = [...(system ? [] : folders.get(id) || [])].sort((a, b) => a.name.localeCompare(b.name, state.locale, { numeric: true }));
    const items = sortedProjects(id);
    const hasChildren = Boolean(children.length || items.length);
    const expanded = !library.collapsed.includes(id);
    return `<div role="treeitem" aria-level="${level}" ${hasChildren ? `aria-expanded="${expanded}"` : ""} data-library-group="${html(id)}">
      <div class="library-folder-row${state.importer.librarySelectedId === id ? " is-selected" : ""}" data-library-folder="${html(id)}" ${system ? "" : `data-library-drag-folder="${html(id)}"`} style="--library-depth:${level - 1}">
        <button type="button" class="library-chevron ${hasChildren ? "" : "is-empty"}" data-library-toggle="${html(id)}" aria-label="${html(name)}" ${hasChildren ? `aria-expanded="${expanded}"` : 'disabled aria-hidden="true" tabindex="-1"'}>${projectIcon("chevron")}</button>
        <button type="button" class="library-folder-name" data-library-select="${html(id)}" data-app-tooltip="${html(name)}" data-app-tooltip-overflow="span">${projectIcon(system ? "import" : "folder")}<span>${html(name)}</span></button>
        <button type="button" class="library-row-menu" data-library-folder-menu="${html(id)}" aria-label="${html(labels.actions)}: ${html(name)}" aria-haspopup="menu" ${disabled}>${projectIcon("more")}</button>
      </div><div role="group" ${expanded ? "" : "hidden"}>${children.map(node => group(node.id, node.name, level + 1)).join("")}${items.map(record => row(record, level + 1)).join("")}</div>
    </div>`;
  };
  return `${library.error || state.importer.libraryError ? `<p class="error-text" role="alert">${html(labels.errors[library.error || state.importer.libraryError] || labels.errors.storage)}</p>` : ""}
    <div class="library-tree" role="tree" aria-label="${html(state.locale === "en" ? "Project library" : "项目库")}">
    ${group("", labels.unassigned, 1, true)}${(folders.get("") || []).sort((a, b) => a.name.localeCompare(b.name, state.locale, { numeric: true })).map(node => group(node.id, node.name, 1)).join("")}</div>`;
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
  return `<div class="modal-overlay library-dialog-overlay"><form class="modal-dialog library-dialog" role="dialog" aria-modal="true" aria-labelledby="library-dialog-title">
    <h3 id="library-dialog-title">${title}</h3>
    ${editing ? `<label for="library-name">${labels.name}</label><input id="library-name" maxlength="120" required value="${html(dialog.name ?? node?.name ?? "")}" />` : `<p class="library-dialog-subject">${html(node?.name || dialog.projectName || dialog.path || "")}</p>`}
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
  const extra = (action, label) => `<button type="button" role="menuitem" class="context-menu-item" data-library-action="${action}" data-library-overflow-action="${action}" ${overflow.includes(action) ? "" : "hidden"} ${projectEntryBusy(state) || (action !== "create" && state.importer.historyValidating) ? "disabled" : ""}>${content(action, label)}</button>`;
  const item = (action, label) => `<button type="button" role="menuitem" class="context-menu-item" data-library-action="${action}">${content(action, label)}</button>`;
  return `<div class="context-menu workspace-history-context-menu" data-library-menu role="menu" aria-label="${labels.actions}" style="left:${Number(menu.x) || 0}px;top:${Number(menu.y) || 0}px">
    ${menu.root ? `${extra("create", labels.create)}${extra("validate", messages.buttons.validateHistory)}${extra("delete-failed", messages.buttons.deleteFailedRecords)}${item("collapse", labels.collapse)}${item("expand", labels.expand)}` : `${item("import", labels.importHere)}${menu.id ? `${item("create", labels.child)}<div role="separator" class="workspace-history-context-menu-separator"></div>${item("rename", labels.rename)}${item("move-folder", labels.move)}<div role="separator" class="workspace-history-context-menu-separator"></div>${item("delete", labels.remove)}` : ""}`}</div>`;
}

export function bindProjectLibrary(host, store, { refresh, openImport, openProjectMenu }) {
  const patch = value => store.setState({ importer: { ...store.getState().importer, ...value } });
  const error = cause => { patch({ libraryError: cause.message || "storage" }); refresh(); };
  const focusRow = (attribute, value) => [...host.querySelectorAll(`[${attribute}]`)].find(row => row.getAttribute(attribute) === value)?.focus();
  const openDialog = dialog => {
    patch({ libraryDialog: dialog, libraryMenu: null, workspaceContextMenu: null, libraryError: "" }); refresh();
    host.querySelector("#library-name, #library-target, [data-library-dialog-close]")?.focus();
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
  host.querySelectorAll("[data-library-project-menu]").forEach(button => button.addEventListener("click", event => {
    const rect = button.getBoundingClientRect();
    openProjectMenu({ preventDefault() {}, clientX: rect.left, clientY: rect.bottom }, button.dataset.libraryProjectMenu);
    event.stopPropagation();
  }));
  host.querySelectorAll("[data-project-move-path]").forEach(button => button.addEventListener("click", () => {
    if (projectEntryBusy(store.getState())) return;
    const record = readWorkspaceHistory().find(item => item.path === button.dataset.projectMovePath);
    openDialog({ kind: "move-project", path: button.dataset.projectMovePath, projectName: record?.projectName || defaultProjectName(button.dataset.projectMovePath), parentId: record ? projectPartition(readProjectLibrary(), record) : "" });
  }));
  const showMenu = (event, id, root = false) => {
    event.preventDefault(); event.stopPropagation();
    if (projectEntryBusy(store.getState())) return;
    patch({ libraryMenu: { id, root, x: event.clientX, y: event.clientY }, workspaceContextMenu: null }); refresh();
    host.querySelector("[data-library-menu] [role=menuitem]:not([hidden]):not(:disabled)")?.focus();
  };
  host.querySelector("[data-library-root-menu]")?.addEventListener("click", event => {
    const rect = event.currentTarget.getBoundingClientRect();
    showMenu({ preventDefault() {}, stopPropagation() {}, clientX: rect.left, clientY: rect.bottom }, "", true);
  });
  host.querySelectorAll("[data-library-folder]").forEach(row => {
    row.addEventListener("contextmenu", event => showMenu(event, row.dataset.libraryFolder));
    row.querySelector("[data-library-folder-menu]")?.addEventListener("click", event => {
      const rect = event.currentTarget.getBoundingClientRect();
      showMenu({ preventDefault() {}, stopPropagation() {}, clientX: rect.left, clientY: rect.bottom }, row.dataset.libraryFolder);
    });
  });
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
    } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      const rect = event.target.getBoundingClientRect(); event.preventDefault();
      const coordinates = { preventDefault() {}, stopPropagation() {}, clientX: rect.left, clientY: rect.bottom };
      if (event.target.matches("[data-recent-path]")) openProjectMenu(coordinates, event.target.dataset.recentPath);
      else showMenu(coordinates, group.dataset.libraryGroup);
    }
  });
  const menu = host.querySelector("[data-library-menu]");
  if (menu) {
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(bounds.left, window.innerWidth - bounds.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(bounds.top, window.innerHeight - bounds.height - 8))}px`;
    const dismiss = () => { patch({ libraryMenu: null }); menu.remove(); };
    menu.addEventListener("focusout", event => { if (!menu.contains(event.relatedTarget)) dismiss(); });
    menu.addEventListener("keydown", event => {
      if (event.key === "Escape") { event.preventDefault(); const id = store.getState().importer.libraryMenu?.id || ""; dismiss(); focusRow("data-library-select", id); }
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault(); const items = [...menu.querySelectorAll("[role=menuitem]:not([hidden]):not(:disabled)")], index = items.indexOf(event.target);
        items[(index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
      }
    });
    menu.querySelectorAll("[data-library-action]").forEach(button => button.addEventListener("click", () => {
      const current = store.getState().importer.libraryMenu; if (!current) return;
      const action = button.dataset.libraryAction;
      if (button.hidden || button.disabled) return;
      if (["validate", "delete-failed"].includes(action)) {
        patch({ libraryMenu: null }); menu.remove();
        host.querySelector(action === "validate" ? "#validate-history-button" : "#delete-failed-history-button")?.click();
        return;
      }
      if (action === "import") { patch({ libraryMenu: null }); openImport(current.id); return; }
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
