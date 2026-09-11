import { listProjectCatalog, updateProjectCatalog, revealCatalogLocation } from "../../services/project-catalog.js";
import { projectIcon } from "./project-icons.js";
import { clearAssemblySessionCache } from "../shell/assembly-session-cache.js";

const messages = {
  zh: {
    datasets: "数据集", name: "名称", role: "数据类型", count: "序列数", details: "数据详情", more: "更多信息", close: "关闭",
    total: "总长度", note: "备注", actions: "操作", primary: "主组装", support: "辅助组装", derived: "派生数据", includesDerived: "含派生序列",
    reference: "参考基因组", edit: "查看详情、编辑名称与备注", emptyNote: "添加备注",
    reset: "恢复初始名称", location: "本地位置", missing: "序列文件未包含或不可用",
    partial: "部分序列文件可用", open: "打开目录",
    save: "保存", cancel: "取消", loading: "正在读取数据集…", retry: "重试",
    failure: "读取数据集失败", saveFailure: "保存失败", empty: "没有数据集", bp: "bp", pending: "正在保存…",
  },
  en: {
    datasets: "Datasets", name: "Name", role: "Data type", count: "Sequences", details: "Dataset details", more: "More information", close: "Close",
    total: "Total length", note: "Note", actions: "Actions", primary: "Primary", support: "Support", derived: "Derived", includesDerived: "Includes derived sequences",
    reference: "Reference genome", edit: "View details and edit name or note", emptyNote: "Add note",
    reset: "Restore initial name", location: "Local location", missing: "Sequence files not included or unavailable",
    partial: "Some sequence files are available", open: "Open folder",
    save: "Save", cancel: "Cancel", loading: "Loading datasets…", retry: "Retry",
    failure: "Could not load datasets", saveFailure: "Could not save", empty: "No datasets", bp: "bp", pending: "Saving…",
  },
};

const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const objectKey = row => `${row.objectType}:${row.objectId}`;
const labels = state => messages[state.locale === "en" ? "en" : "zh"];
let nextRequest = 0;

export function projectCatalogKey(state) {
  const project = state.initializer?.existingProjects?.find(item => Number(item.projectId) === Number(state.session?.projectId));
  return JSON.stringify([state.session?.workspacePath, state.session?.projectId, project?.supportDatasetIds,
    (state.initializer?.datasets || []).map(item => [item.datasetId, item.contigCount, item.totalLengthBp])]);
}

function currentCatalog(state) {
  const catalog = state.initializer?.projectCatalog;
  return catalog?.key === projectCatalogKey(state) ? catalog : {};
}

function number(value, state) {
  return value == null ? "—" : Number(value).toLocaleString(state.locale === "en" ? "en-US" : "zh-CN");
}

function length(value, state) {
  if (value == null) return "—";
  const [unit, divisor] = value >= 1e9 ? ["Gb", 1e9] : value >= 1e6 ? ["Mb", 1e6] : value >= 1e3 ? ["kb", 1e3] : ["bp", 1];
  return `<span title="${number(value, state)} bp">${Number(value / divisor).toLocaleString(state.locale === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: divisor === 1 ? 0 : 2 })} ${unit}</span>`;
}

function renderDetails(row, catalog, state) {
  const l = labels(state);
  const editor = catalog.editor;
  const busy = catalog.saving || state.importer?.inFlight || state.initializer?.autoPipelineRunning ? "disabled" : "";
  const paths = row.locations || [];
  return `<dialog class="project-catalog-dialog" data-catalog-dialog aria-labelledby="catalog-dialog-title" aria-modal="true" tabindex="-1">
    <header class="project-catalog-dialog-head"><h3 id="catalog-dialog-title">${l.details}</h3>
      <span class="project-dataset-role">${l[row.role] || escape(row.role)}</span>
      <button type="button" data-catalog-close class="button project-icon-button" aria-label="${l.close}" ${busy}>${projectIcon("close")}</button></header>
    <form data-catalog-form class="project-dataset-editor">
      <div class="project-dataset-editor-body">
      <div class="project-dataset-field-heading"><label for="catalog-display-name">${l.name}</label>
        <button type="button" data-catalog-reset class="button ghost" title="${escape(row.originalName)}" ${busy} ${editor.displayName === row.originalName ? "disabled" : ""}>${l.reset}</button></div>
      <input id="catalog-display-name" name="displayName" maxlength="200" required value="${escape(editor.displayName)}" ${busy} />
      <label for="catalog-note">${l.note}</label>
      <textarea id="catalog-note" name="note" rows="3" maxlength="10000" ${busy}>${escape(editor.note)}</textarea>
      <details class="project-catalog-more" ${editor.moreOpen ? "open" : ""}><summary>${l.more}</summary>
      <section class="project-dataset-location" aria-labelledby="catalog-location-title">
        <h4 id="catalog-location-title">${l.location}</h4>
        ${!row.fastaAvailable ? `<p class="muted">${row.availableFileCount ? l.partial : l.missing}</p>` : ""}
        ${row.availableFileCount ? `<div class="project-dataset-paths">${paths.map((path, index) => `<div class="project-dataset-path"><code>${escape(path)}</code>${globalThis.window?.__TAURI__?.core?.invoke ? `<button type="button" class="button ghost" data-catalog-reveal="${index}" ${busy}>${l.open}</button>` : ""}</div>`).join("")}</div>` : ""}
      </section>
      </details>
      ${catalog.error ? `<p class="error-text" role="alert">${escape(catalog.error)}</p>` : ""}
      </div>
      <div class="project-dataset-editor-actions"><button type="button" data-catalog-cancel class="button ghost" ${busy}>${l.cancel}</button>
        <button type="submit" class="button project-primary" ${busy}>${catalog.saving ? l.pending : l.save}</button></div>
    </form>
  </dialog>`;
}

function renderTable(rows, title, catalog, state) {
  const l = labels(state);
  return `<div class="project-dataset-section">
    <div class="project-dataset-scroll" tabindex="0" role="region" aria-label="${title}"><table class="project-dataset-table" aria-label="${title}">
      <colgroup><col span="7"><col class="project-dataset-actions-column"></colgroup>
      <thead><tr>${[l.role, l.name, l.count, l.total, "N50", "N90", l.note, l.actions].map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(row => {
        const key = objectKey(row);
        const editing = catalog.editor?.key === key;
        const disabled = catalog.saving || state.importer?.inFlight || state.initializer?.autoPipelineRunning || (catalog.editor && !editing) ? "disabled" : "";
        const stats = row.statistics || {};
        return `<tr data-catalog-object="${escape(key)}">
          <td><span class="project-dataset-role">${l[row.role] || escape(row.role)}</span></td>
          <th scope="row"><span class="project-dataset-name" title="${escape(row.displayName)}">${escape(row.displayName)}</span>${row.derived && row.role !== "derived" ? `<small class="muted">${l.includesDerived}</small>` : ""}</th>
          <td class="numeric">${number(stats.sequenceCount, state)}</td><td class="numeric">${length(stats.totalLengthBp, state)}</td>
          <td class="numeric">${length(stats.n50, state)}</td><td class="numeric">${length(stats.n90, state)}</td>
          <td><button type="button" class="project-dataset-note" data-catalog-edit="${escape(key)}" data-catalog-focus="note" title="${escape(row.note || l.emptyNote)}" ${disabled}>${escape(row.note || l.emptyNote)}</button></td>
          <td><button type="button" class="button project-icon-button" data-catalog-edit="${escape(key)}" title="${l.edit}" aria-label="${l.edit}: ${escape(row.displayName)}" aria-expanded="${editing}" ${disabled}>${projectIcon("rename")}</button></td>
        </tr>`;
      }).join("") || `<tr><td colspan="8" class="muted">${l.empty}</td></tr>`}</tbody></table></div>
      </div>`;
}

export function renderProjectCatalog(state) {
  const catalog = currentCatalog(state);
  const l = labels(state);
  const rows = [...(catalog.data?.references || []), ...(catalog.data?.datasets || [])];
  const selected = rows.find(row => objectKey(row) === catalog.editor?.key);
  return `<section id="project-data-catalog" aria-label="${l.datasets}" aria-busy="${Boolean(catalog.loading)}">
    ${catalog.data ? renderTable(rows, l.datasets, catalog, state) : `<p role="status" class="muted">${catalog.error ? l.failure : l.loading}</p>`}
    ${catalog.error && !catalog.editor ? `<p class="error-text" role="alert">${escape(catalog.error)}</p>` : ""}
    ${catalog.error && !catalog.editor ? `<button type="button" class="button ghost" data-catalog-retry ${catalog.loading || state.importer?.inFlight || state.initializer?.autoPipelineRunning ? "disabled" : ""}>${l.retry}</button>` : ""}
  </section>${selected ? renderDetails(selected, catalog, state) : ""}`;
}

export function bindProjectCatalog(host, store, rerender, deps = {}) {
  if (!host.querySelector("#project-data-catalog")) return;
  const list = deps.listProjectCatalog || listProjectCatalog;
  const update = deps.updateProjectCatalog || updateProjectCatalog;
  const key = projectCatalogKey(store.getState());
  const scope = { workspaceRoot: store.getState().session.workspacePath, projectId: Number(store.getState().session.projectId) };
  const live = () => key === projectCatalogKey(store.getState());
  const set = patch => {
    if (!live()) return;
    const state = store.getState();
    const renamed = {};
    if (patch.data) {
      for (const [field, idKey] of [["datasets", "datasetId"], ["references", "referenceGenomeId"]]) {
        renamed[field] = (state.initializer[field] || []).map(item => {
          const row = patch.data[field]?.find(entry => Number(entry.objectId) === Number(item[idKey]));
          if (row && (item.displayName || item.name || item.label) !== row.displayName) clearAssemblySessionCache();
          return row ? { ...item, displayName: row.displayName, label: row.displayName } : item;
        });
      }
    }
    store.setState({ initializer: { ...state.initializer, ...renamed, projectCatalog: { ...currentCatalog(state), key, ...patch } } });
  };
  const refresh = () => { if (live()) rerender(host, store); };
  const load = async () => {
    const requestId = ++nextRequest;
    set({ loading: true, error: "", requestId });
    const current = () => live() && currentCatalog(store.getState()).requestId === requestId;
    try { const data = await list(scope); if (current()) set({ data, loading: false }); }
    catch (error) { if (current()) set({ loading: false, error: String(error?.message || error) }); }
    refresh();
  };
  const catalog = currentCatalog(store.getState());
  if (!catalog.loading && !catalog.data && !catalog.error) void load();
  host.querySelector("[data-catalog-retry]")?.addEventListener("click", () => { void load(); refresh(); });
  host.querySelectorAll("[data-catalog-edit]").forEach(button => button.addEventListener("click", () => {
    const latest = currentCatalog(store.getState());
    const row = [...(latest.data?.datasets || []), ...(latest.data?.references || [])].find(item => objectKey(item) === button.dataset.catalogEdit);
    if (!row || latest.saving || store.getState().importer?.inFlight || store.getState().initializer?.autoPipelineRunning) return;
    if (latest.editor?.key !== objectKey(row)) set({ editor: { key: objectKey(row), displayName: row.displayName, note: row.note, focusField: button.dataset.catalogFocus === "note" ? "note" : "displayName" }, error: "" });
    refresh();
    host.querySelector(button.dataset.catalogFocus === "note" ? "#catalog-note" : "#catalog-display-name")?.focus();
  }));
  const form = host.querySelector("[data-catalog-form]");
  if (!form) return;
  const draft = () => currentCatalog(store.getState()).editor;
  const restoreFocus = editor => {
    if (live() && editor) host.querySelector(`[data-catalog-edit="${editor.key}"]${editor.focusField === "note" ? '[data-catalog-focus="note"]' : '.project-icon-button'}`)?.focus();
  };
  const dialog = host.querySelector("[data-catalog-dialog]");
  if (dialog && !dialog.open) {
    dialog.showModal();
    form.elements[draft()?.focusField || "displayName"]?.focus();
  }
  dialog?.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]')]
      .filter(element => element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls.at(-1);
    const active = dialog.ownerDocument.activeElement;
    if (!first || (event.shiftKey ? active === first || active === dialog : active === last || active === dialog)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  });
  const more = host.querySelector(".project-catalog-more");
  more?.addEventListener("toggle", () => {
    if (more.isConnected && draft()) set({ editor: { ...draft(), moreOpen: more.open } });
  });
  form.addEventListener("input", () => {
    set({ editor: { ...draft(), displayName: form.elements.displayName.value, note: form.elements.note.value } });
    const row = [...catalog.data.datasets, ...catalog.data.references].find(item => objectKey(item) === draft().key);
    const reset = host.querySelector("[data-catalog-reset]");
    if (reset) reset.disabled = form.elements.displayName.value === row.originalName;
  });
  const cancel = () => {
    if (!live() || !draft() || currentCatalog(store.getState()).saving) return;
    const editor = draft();
    set({ editor: null, error: "" }); refresh();
    restoreFocus(editor);
  };
  host.querySelector("[data-catalog-cancel]")?.addEventListener("click", cancel);
  host.querySelector("[data-catalog-close]")?.addEventListener("click", cancel);
  dialog?.addEventListener("cancel", event => { event.preventDefault(); cancel(); });
  form.addEventListener("keydown", event => { if (event.key === "Escape") { event.preventDefault(); cancel(); } });
  host.querySelector("[data-catalog-reset]")?.addEventListener("click", () => {
    const row = [...catalog.data.datasets, ...catalog.data.references].find(item => objectKey(item) === draft().key);
    set({ editor: { ...draft(), displayName: row.originalName } }); refresh();
  });
  host.querySelectorAll("[data-catalog-reveal]").forEach(button => button.addEventListener("click", async () => {
    const [objectType, id] = draft().key.split(":");
    try { await (deps.revealCatalogLocation || revealCatalogLocation)({ ...scope, objectType, objectId: Number(id), locationIndex: Number(button.dataset.catalogReveal) }); }
    catch (error) { set({ error: String(error?.message || error) }); refresh(); }
  }));
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (currentCatalog(store.getState()).saving || !live() || store.getState().importer?.inFlight || store.getState().initializer?.autoPipelineRunning) return;
    const editor = draft();
    const [objectType, id] = editor.key.split(":");
    const row = [...catalog.data.datasets, ...catalog.data.references].find(item => objectKey(item) === editor.key);
    const nameChange = editor.displayName === row.originalName ? { resetName: true } : { displayName: editor.displayName.trim() };
    const requestId = ++nextRequest;
    set({ saving: true, error: "", requestId }); refresh();
    try {
      const data = await update({ ...scope, objectType, objectId: Number(id), ...nameChange, note: editor.note });
      if (currentCatalog(store.getState()).requestId === requestId) set({ data, saving: false, editor: null });
    } catch (error) { if (currentCatalog(store.getState()).requestId === requestId) set({ saving: false, error: `${labels(store.getState()).saveFailure}: ${String(error?.message || error)}` }); }
    refresh();
    if (!draft()) restoreFocus(editor);
  });
}
