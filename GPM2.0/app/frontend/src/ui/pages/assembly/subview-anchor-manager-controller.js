import {
  applySubviewAnchorFocus,
  buildSubviewAnchorObjects,
  collectSubviewAnchorScene,
  locateSubviewAnchorObject,
  normalizeSubviewAnchorToolsUi,
} from "./subview-anchor-objects.js";
import { renderSubviewAnchorList } from "./render-subview-anchor-list.js";
import { buildSubviewGrtAnchorReferences } from "./subview-grt-anchor-state.js";

function resolveRouteHost(node, fallback) {
  return node?.closest?.("#route-host") || fallback;
}

export function createSubviewAnchorManagerController({
  session,
  deleteSubviewAnchors,
  copySubviewGrtAnchor,
  enrichSubviewAnchorDescriptors = async () => false,
}) {
  function getUi(objects, scopeKey) {
    const current = normalizeSubviewAnchorToolsUi(session.subviewAnchorToolsState,
      objects.map((object) => object.objectId));
    session.subviewAnchorToolsState = { ...current, scopeKey };
    return session.subviewAnchorToolsState;
  }

  function getObjects(host, state) {
    const scene = collectSubviewAnchorScene(host);
    return [
      ...buildSubviewAnchorObjects(state?.assembly?.subview, scene),
      ...buildSubviewGrtAnchorReferences(state?.assembly, scene),
    ];
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

  function focus(host, target, objectId = "") {
    const normalizedObjectId = String(objectId || "").trim();
    session.subviewAnchorToolsState = {
      ...session.subviewAnchorToolsState,
      focusedObjectId: normalizedObjectId,
    };
    applySubviewAnchorFocus(host, normalizedObjectId);
    const manager = target?.closest?.("[data-subview-anchor-manager]");
    for (const row of manager?.querySelectorAll?.("[data-subview-anchor-list-row]") || []) {
      const selected = row.dataset.subviewAnchorListRow === normalizedObjectId;
      row.setAttribute("aria-current", String(selected));
      row.classList?.toggle("is-focused", selected);
      row.closest?.(".subview-anchor-object")?.classList.toggle("is-focused", selected);
    }
  }

  async function remove(host, objectIds, context) {
    const deletable = new Set(getObjects(host, context.store.getState())
      .filter((object) => object.canDelete).map((object) => object.objectId));
    const targets = objectIds.filter((objectId) => deletable.has(objectId));
    if (!targets.length) return;
    const changed = await deleteSubviewAnchors(host, context.store, targets);
    if (!changed) return;
    const removed = new Set(targets);
    updateUi({
      focusedObjectId: removed.has(session.subviewAnchorToolsState.focusedObjectId)
        ? "" : session.subviewAnchorToolsState.focusedObjectId,
      checkedObjectIds: session.subviewAnchorToolsState.checkedObjectIds.filter((id) => !removed.has(id)),
    }, context.sync);
  }

  async function copyGrt(host, originId, context) {
    const result = await copySubviewGrtAnchor(host, context.store, { originId });
    if (!result?.objectId) return;
    updateUi({ focusedObjectId: result.objectId }, context.sync);
    applySubviewAnchorFocus(host, result.objectId);
  }

  function onAction(event, context) {
    const host = resolveRouteHost(event.target, context.host);
    const copyOriginId = event.target.closest("[data-subview-anchor-copy-grt]")
      ?.dataset.subviewAnchorCopyGrt;
    if (copyOriginId) return void copyGrt(host, copyOriginId, context);
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
  }

  function onInput(event, context) {
    if (event.target.matches?.("[data-subview-anchor-search]")) {
      updateUi({ query: event.target.value }, context.sync);
    }
  }

  function onPointerOver(event, context) {
    const row = event.target.closest?.("[data-subview-anchor-list-row]");
    const objectId = row?.dataset.subviewAnchorListRow;
    if (!objectId) return;
    focus(resolveRouteHost(event.target, context.host), row, objectId);
  }

  function onPointerOut(event, context) {
    const row = event.target.closest?.("[data-subview-anchor-list-row]");
    const objectId = row?.dataset.subviewAnchorListRow;
    if (!objectId || row.contains?.(event.relatedTarget)) return;
    if (session.subviewAnchorToolsState?.focusedObjectId !== objectId) return;
    focus(resolveRouteHost(event.target, context.host), row, "");
  }

  function onDoubleClick(event, context) {
    const objectId = event.target.closest("[data-subview-anchor-list-row]")?.dataset.subviewAnchorListRow;
    if (!objectId || event.target.closest(
      "[data-subview-anchor-check],[data-subview-anchor-delete],[data-subview-anchor-copy-grt]",
    )) return;
    locateSubviewAnchorObject(resolveRouteHost(event.target, context.host), objectId);
  }

  function onContentKeyDown(event, context) {
    const objectId = event.target.closest("[data-subview-anchor-list-row]")?.dataset.subviewAnchorListRow;
    if (objectId && event.key === "Enter" && !event.target.closest("[data-subview-anchor-copy-grt]")) {
      event.preventDefault();
      locateSubviewAnchorObject(resolveRouteHost(event.target, context.host), objectId);
    }
  }

  function afterRender({ host, store, tab }) {
    applySubviewAnchorFocus(host, session.subviewAnchorToolsState?.focusedObjectId || "");
    if (tab === "anchors") void enrichSubviewAnchorDescriptors(host, store);
  }

  return {
    renderContent,
    resetScope,
    onAction,
    onInput,
    onPointerOver,
    onPointerOut,
    onDoubleClick,
    onContentKeyDown,
    afterRender,
  };
}
