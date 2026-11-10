import { describeMainMemberLocalState } from "./main-member-local-state.js";
import { getAssemblyI18n } from "./i18n.js";
import { requestAppConfirm } from "../../shell/app-dialog.js";
import { filterTrackMemberRows, matchesTrackMembersScope, resolveTrackMembersScope, trackMemberRows } from "./track-members-model.js";

const activeDialogs = new WeakMap();
export const trackMembersLabels = locale => locale === "en" ? {
  title: "Track Members", all: "Members", displayed: "Displayed", filtered: "Filtered", hidden: "Hidden", deleted: "Deleted",
  search: "Search member names", close: "Close", empty: "No matching members", loading: "Loading deleted members…",
  selectAll: "Select all matches", clear: "Clear selection", hide: "Hide selected", show: "Unhide selected",
  delete: "Delete selected", restore: "Restore selected", prev: "Previous", next: "Next", locate: "Locate",
  filterSettings: "Adjust filter", filteredReason: "Length below effective threshold", owner: "Assigned to another chromosome; cannot delete here",
  selected: "selected", source: "Source", failed: "Unable to load deleted members", retry: "Retry",
  restoreConfirm: "Restore the selected deleted members? Current display filters will still apply. This is not an undo of all deletion dependencies.",
  restored: "Restored members still follow current display filters. Check Filtered or Hidden if they do not appear on the track.",
} : {
  title: "轨道成员", all: "成员", displayed: "当前显示", filtered: "已过滤", hidden: "已隐藏", deleted: "已删除",
  search: "搜索成员名称", close: "关闭", empty: "没有匹配的成员", loading: "正在读取已删除成员…",
  selectAll: "全选筛选结果", clear: "清空选择", hide: "隐藏所选", show: "取消隐藏", delete: "删除所选", restore: "恢复所选",
  prev: "上一页", next: "下一页", locate: "定位", filterSettings: "调整过滤", filteredReason: "长度小于有效阈值",
  owner: "归属其他染色体，不能在这里删除", selected: "已选", source: "源", failed: "无法读取已删除成员", retry: "重试",
  restoreConfirm: "恢复所选已删除成员？恢复后仍遵守当前显示过滤条件；这不等同于撤销删除时的所有关联变更。",
  restored: "恢复后仍遵守当前显示条件；轨道中未出现的成员可在“已过滤”或“已隐藏”中查看。",
};
const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const format = value => Number(value || 0).toLocaleString("en-US");
const PAGE_SIZE = 100;

export function renderTrackMembersContent(state, scope, ui) {
  const labels = trackMembersLabels(state.locale), i18n = getAssemblyI18n(state), rows = trackMemberRows(state, scope, ui.deleted);
  const matched = filterTrackMemberRows(rows, ui.filter, ui.query);
  const page = Math.max(0, Math.min(ui.page, Math.max(0, Math.ceil(matched.length / PAGE_SIZE) - 1)));
  const selected = rows.filter(row => ui.selected.has(row.key));
  const live = selected.filter(row => !row.deleted), deleted = selected.filter(row => row.deleted);
  const busy = ui.busy || state.assembly.loading || state.assembly.mainViewHistory?.inFlight;
  const button = (action, label, disabled = false) => `<button type="button" class="button ghost tiny" data-member-action="${action}" ${busy || disabled ? "disabled" : ""}>${escape(label)}</button>`;
  return `<div class="track-members-filters">${["all", "displayed", "filtered", "hidden", "deleted"].map(filter =>
    `<button type="button" class="button ghost tiny" data-member-filter="${filter}" aria-pressed="${ui.filter === filter}" ${busy ? "disabled" : ""}>${labels[filter]} · ${filter === "deleted" && (ui.loading || ui.error) ? "…" : filterTrackMemberRows(rows, filter).length}</button>`).join("")}</div>
    <div class="track-members-selection">${button("select-all", labels.selectAll, !matched.length)}${button("clear", labels.clear, !selected.length)}<span>${labels.selected} ${selected.length}</span>
      ${scope.trackRole === "support" ? button("filter-settings", labels.filterSettings) : ""}</div>
    ${ui.loading ? `<p role="status">${labels.loading}</p>` : ""}
    ${ui.error ? `<p class="error-text" role="alert">${escape(ui.error)} ${button("retry", labels.retry)}</p>` : ""}
    ${ui.notice ? `<p role="status">${escape(ui.notice)}</p>` : ""}
    <div class="track-members-list">${matched.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(row => {
      const fragment = row.ctg.sourceFragment || row.ctg.sourceRange;
      const local = scope.trackRole === "primary" && !row.deleted ? describeMainMemberLocalState(row.ctg, state.assembly) : null;
      const localLabel = local ? i18n.page.localMemberNotes[local.kind].replace("{count}", local.count)
        .replace("{retained}", format(local.retainedBp)).replace("{total}", format(local.totalBp)) : "";
      const details = [row.filtered ? `${labels.filteredReason}: ${format(row.length)} < ${format(row.threshold)} bp` : "",
        row.hidden ? labels.hidden : "", row.deleted ? labels.deleted : "", !row.editable ? labels.owner : "",
        fragment ? `${labels.source} ${format(fragment.sourceStart)}–${format(fragment.sourceEnd)}${fragment.sourceLength ? ` / ${format(fragment.sourceLength)} bp` : ""}` : "",
        row.ctg.derivedSource, row.ctg.coAssignedChrNames?.join(", "), row.ctg.grtPlacementMode,
        localLabel, local?.ranges.map(([a, b]) => `${format(a)}–${format(b)}`).join(", ")].filter(Boolean);
      return `<div class="track-member-row${row.deleted ? " is-deleted" : ""}"><label><input type="checkbox" data-member-key="${escape(row.key)}" ${ui.selected.has(row.key) ? "checked" : ""} ${busy ? "disabled" : ""}/><span class="track-member-name"${local ? ` data-main-member-local-state="${local.kind}"` : ""}>${escape(row.name)}</span></label>
        <span>${format(row.length)} bp</span>${row.displayed ? `<button type="button" class="button ghost tiny" data-member-locate="${row.ctg.assemblyCtgId}" ${busy ? "disabled" : ""}>${labels.locate}</button>` : ""}
        ${details.length ? `<small>${details.map(escape).join(" · ")}</small>` : ""}</div>`;
    }).join("") || (ui.filter === "deleted" && (ui.loading || ui.error) ? "" : `<p class="muted">${labels.empty}</p>`)}</div>
    <div class="track-members-pagination">${button("prev", labels.prev, page === 0)}<span>${page + 1} / ${Math.max(1, Math.ceil(matched.length / PAGE_SIZE))} · ${matched.length}</span>${button("next", labels.next, (page + 1) * PAGE_SIZE >= matched.length)}</div>
    <div class="app-dialog-actions">${button("hide", labels.hide, !live.some(row => !row.hidden))}${button("show", labels.show, !live.some(row => row.hidden))}${button("delete", labels.delete, !live.some(row => row.editable))}${button("restore", labels.restore, !deleted.length || ui.loading || Boolean(ui.error))}</div>`;
}

export function openTrackMembersDialog(host, store, context, deps) {
  const scope = resolveTrackMembersScope(store.getState(), context);
  const doc = host?.ownerDocument || globalThis.document;
  if (!scope || !doc?.body || store.getState().assembly.loading) return null;
  activeDialogs.get(store)?.();
  const labels = trackMembersLabels(store.getState().locale);
  const dialog = doc.createElement("dialog");
  dialog.className = "app-dialog track-members-dialog";
  dialog.setAttribute("data-track-members-dialog", "");
  dialog.setAttribute("aria-labelledby", "track-members-title");
  dialog.innerHTML = `<header><h2 id="track-members-title">${labels.title} · ${escape(scope.name)} · ${escape(scope.chrName)}</h2><button type="button" class="button ghost" data-member-close>${labels.close}</button></header>
    <input type="search" data-member-search aria-label="${labels.search}" placeholder="${labels.search}"/>
    <div data-track-members-content></div>`;
  const content = dialog.querySelector("[data-track-members-content]");
  const ui = { deleted: [], selected: new Set(), filter: "all", query: "", page: 0, busy: false, loading: true, error: "", notice: "" };
  const initialRoute = store.getState().activeRoute;
  const initialLocale = store.getState().locale;
  const confirm = deps.confirm || requestAppConfirm;
  let closed = false, generation = 0, unsubscribe;
  const current = () => !closed && matchesTrackMembersScope(store.getState(), scope) && store.getState().activeRoute === initialRoute && store.getState().locale === initialLocale;
  const close = () => {
    if (closed) return;
    closed = true; generation++; unsubscribe?.();
    if (dialog.open) dialog.close();
    dialog.remove(); activeDialogs.delete(store);
  };
  const render = () => {
    if (!current()) return;
    const scroll = content.querySelector?.(".track-members-list")?.scrollTop || 0;
    const active = doc.activeElement;
    const identity = active && content.contains?.(active)
      ? ["data-member-key", "data-member-action", "data-member-filter"].map(key => [key, active.getAttribute(key)]).find(([, value]) => value != null) : null;
    content.innerHTML = renderTrackMembersContent(store.getState(), scope, ui);
    const list = content.querySelector?.(".track-members-list");
    if (list) list.scrollTop = scroll;
    if (identity) [...content.querySelectorAll(`[${identity[0]}]`)].find(node => node.getAttribute(identity[0]) === identity[1])?.focus({ preventScroll: true });
  };
  const loadDeleted = async () => {
    const request = ++generation;
    ui.loading = true; ui.error = ""; render();
    try {
      const result = await deps.listDeletedCtgs({ workspaceRoot: scope.workspacePath, projectId: scope.projectId, chrName: scope.chrName, datasetId: scope.datasetId });
      if (!current() || request !== generation) return;
      ui.deleted = Array.isArray(result?.items) ? result.items : [];
    } catch (error) {
      if (current() && request === generation) ui.error = `${labels.failed}: ${error?.message || error}`;
    } finally {
      if (current() && request === generation) { ui.loading = false; render(); }
    }
  };
  const selectedRows = () => trackMemberRows(store.getState(), scope, ui.deleted).filter(row => ui.selected.has(row.key));
  const act = async action => {
    if (!current() || ui.busy || store.getState().assembly.loading || store.getState().assembly.mainViewHistory?.inFlight) return;
    const rows = trackMemberRows(store.getState(), scope, ui.deleted);
    const matches = filterTrackMemberRows(rows, ui.filter, ui.query);
    if (action === "select-all") { ui.selected = new Set(matches.map(row => row.key)); render(); return; }
    if (action === "clear") { ui.selected.clear(); render(); return; }
    if (action === "prev" || action === "next") { ui.page = Math.max(0, Math.min(ui.page + (action === "next" ? 1 : -1), Math.ceil(matches.length / PAGE_SIZE) - 1)); render(); return; }
    if (action === "retry") { await loadDeleted(); return; }
    if (action === "filter-settings") { close(); deps.focusFilter?.(host); return; }
    const selected = selectedRows();
    ui.busy = true; ui.notice = ""; render();
    try {
      if (action === "restore") {
        const ids = selected.filter(row => row.deleted).map(row => row.ctg.deletedCtgRecordId);
        if (ids.length && await confirm(labels.restoreConfirm, { store }) && current()) {
          await deps.restore(host, store, ids);
          ui.notice = labels.restored;
        }
      } else if (action === "delete") {
        const ids = selected.filter(row => !row.deleted && row.editable).map(row => row.ctg.assemblyCtgId);
        if (ids.length) await deps.delete(host, store, ids, { ...scope, confirm: (message, options) => confirm(message, { ...options, store }) });
      } else if (action === "hide" || action === "show") {
        const ids = selected.filter(row => !row.deleted).map(row => row.ctg.assemblyCtgId);
        if (ids.length) await deps.setHidden(host, store, scope, ids, action === "hide");
      }
      if (!current()) return;
      ui.selected.clear();
      if (store.getState().assembly.actionError) ui.notice = store.getState().assembly.actionError;
      if (action === "delete" || action === "restore") await loadDeleted();
    } catch (error) {
      if (current()) ui.notice = String(error?.message || error);
    } finally { ui.busy = false; render(); }
  };
  dialog.addEventListener("click", event => {
    if (event.target.closest?.("[data-member-close]")) { close(); return; }
    const filter = event.target.closest?.("[data-member-filter]")?.dataset.memberFilter;
    if (filter && !ui.busy) { ui.filter = filter; ui.page = 0; ui.selected.clear(); render(); return; }
    const action = event.target.closest?.("[data-member-action]")?.dataset.memberAction;
    if (action) { void act(action); return; }
    const locate = Number(event.target.closest?.("[data-member-locate]")?.dataset.memberLocate);
    if (locate && !ui.busy && current()) { close(); void deps.locate(host, store, locate); }
  });
  dialog.addEventListener("input", event => {
    if (event.target.matches?.("[data-member-search]")) {
      ui.query = event.target.value; ui.page = 0; ui.selected.clear(); render();
    }
  });
  dialog.addEventListener("change", event => {
    const key = event.target.dataset?.memberKey;
    if (!key || ui.busy) return;
    if (event.target.checked) ui.selected.add(key); else ui.selected.delete(key);
    render();
  });
  dialog.addEventListener("keydown", event => {
    if (event.key !== "Delete" || event.target.matches?.("input[type='search']") || event.ctrlKey || event.altKey || event.metaKey) return;
    event.preventDefault(); event.stopPropagation(); void act("delete");
  });
  dialog.addEventListener("close", close);
  dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
  unsubscribe = store.subscribe?.(() => { if (!current()) close(); else if (!ui.busy) render(); });
  activeDialogs.set(store, close);
  doc.body.append(dialog); render(); dialog.showModal();
  dialog.querySelector("[data-member-search]").focus();
  void loadDeleted();
  return { close, loadDeleted };
}
