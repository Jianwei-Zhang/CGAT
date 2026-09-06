import {
  applySubviewAnchorFocus,
  buildSubviewAnchorObjects,
  collectSubviewAnchorScene,
  locateSubviewAnchorObject,
  normalizeSubviewAnchorToolsUi,
} from "./subview-anchor-objects.js";
import { renderSubviewAnchorList } from "./render-subview-anchor-list.js";

function resolveRouteHost(node, fallback) {
  return node?.closest?.("#route-host") || fallback;
}

export function createSubviewAnchorManagerController({
  session,
  deleteSubviewAnchors,
  enrichSubviewAnchorDescriptors = async () => false,
}) {
  function getUi(objects, scopeKey) {
    const current = normalizeSubviewAnchorToolsUi(session.subviewAnchorToolsState,
      objects.map((object) => object.objectId));
    session.subviewAnchorToolsState = { ...current, scopeKey };
    return session.subviewAnchorToolsState;
  }

  function getObjects(host, state) {
    return buildSubviewAnchorObjects(state?.assembly?.subview, collectSubviewAnchorScene(host));
  }

  function renderContent({ host, state, tab, scopeKey, labels, escapeHtml, escapeAttr }) {
    if (tab !== "anchors") return "";
    const objects = getObjects(host, state);
    return renderSubviewAnchorList(objects, getUi(objects, scopeKey), labels.anchorManager,
      { escapeHtml, escapeAttr });
  }

  function resetScope(scopeKey) {
    session.subviewAnchorToolsState = {
      scopeKey, focusedObjectId: "", checkedObjectIds: [], query: "",
    };
  }

  function updateUi(patch, sync) {
    session.subviewAnchorToolsState = { ...session.subviewAnchorToolsState, ...patch };
    sync();
  }

  function focus(host, target, objectId) {
    session.subviewAnchorToolsState = {
      ...session.subviewAnchorToolsState,
      focusedObjectId: objectId,
    };
    applySubviewAnchorFocus(host, objectId);
    const manager = target?.closest?.("[data-subview-anchor-manager]");
    for (const row of manager?.querySelectorAll?.("[data-subview-anchor-list-row]") || []) {
      const selected = row.dataset.subviewAnchorListRow === objectId;
      row.setAttribute("aria-pressed", String(selected));
      row.closest?.(".subview-anchor-object")?.classList.toggle("is-focused", selected);
    }
  }

  async function remove(host, objectIds, context) {
    if (!objectIds.length) return;
    const changed = await deleteSubviewAnchors(host, context.store, objectIds);
    if (!changed) return;
    const removed = new Set(objectIds);
    updateUi({
      focusedObjectId: removed.has(session.subviewAnchorToolsState.focusedObjectId)
        ? "" : session.subviewAnchorToolsState.focusedObjectId,
      checkedObjectIds: session.subviewAnchorToolsState.checkedObjectIds.filter((id) => !removed.has(id)),
    }, context.sync);
  }

  function onAction(event, context) {
    const host = resolveRouteHost(event.target, context.host);
    const deleteId = event.target.closest("[data-subview-anchor-delete]")?.dataset.subviewAnchorDelete;
    if (deleteId) return void remove(host, [deleteId], context);
    if (event.target.closest("[data-subview-anchor-delete-checked]")) {
      return void remove(host, [...session.subviewAnchorToolsState.checkedObjectIds], context);
    }
    const checkbox = event.target.closest("[data-subview-anchor-check]");
    if (checkbox) {
      const objectId = checkbox.dataset.subviewAnchorCheck;
      const checked = new Set(session.subviewAnchorToolsState.checkedObjectIds);
      if (checkbox.checked) checked.add(objectId); else checked.delete(objectId);
      updateUi({ checkedObjectIds: [...checked] }, context.sync);
      return;
    }
    const objectId = event.target.closest("[data-subview-anchor-list-row]")?.dataset.subviewAnchorListRow;
    if (objectId) focus(host, event.target, objectId);
  }

  function onInput(event, context) {
    if (event.target.matches?.("[data-subview-anchor-search]")) {
      updateUi({ query: event.target.value }, context.sync);
    }
  }

  function onDoubleClick(event, context) {
    const objectId = event.target.closest("[data-subview-anchor-list-row]")?.dataset.subviewAnchorListRow;
    if (!objectId || event.target.closest("[data-subview-anchor-check],[data-subview-anchor-delete]")) return;
    locateSubviewAnchorObject(resolveRouteHost(event.target, context.host), objectId);
  }

  function onContentKeyDown(event, context) {
    const objectId = event.target.closest("[data-subview-anchor-list-row]")?.dataset.subviewAnchorListRow;
    if (objectId && event.key === "Enter") {
      event.preventDefault();
      locateSubviewAnchorObject(resolveRouteHost(event.target, context.host), objectId);
    }
  }

  function afterRender({ host, store, tab }) {
    applySubviewAnchorFocus(host, session.subviewAnchorToolsState?.focusedObjectId || "");
    if (tab === "anchors") void enrichSubviewAnchorDescriptors(host, store);
  }

  return { renderContent, resetScope, onAction, onInput, onDoubleClick, onContentKeyDown, afterRender };
}
