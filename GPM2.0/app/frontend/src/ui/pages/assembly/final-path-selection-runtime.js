import { restoreSvgTooltipTitles } from "../../tooltip-export.js";
import { resolveCurrentFinalPathChrName } from "./final-path-state.js";
import { collectFinalPathSourceCtgs, resolveFinalPathSourceRange } from "./final-path-presentation.js";
import { intersectSourceInterval } from "./source-interval-projection.js";

const BOUND = Symbol("finalPathSelectionBound");
const OWNERS = new WeakMap();
const SEGMENT = "[data-final-path-segment-id]";
const OVERLAY = "[data-final-path-selection-overlay]";
const scopeKey = state => JSON.stringify([state.session?.workspacePath, state.session?.projectId,
  state.assembly?.selectedChrName, state.assembly?.activeFinalPathKeyByChr?.[state.assembly?.selectedChrName]
    || state.assembly?.activeFinalPathKey || ""]);
const editingSelectionKey = state => JSON.stringify([state.assembly?.selectedCtgId, state.assembly?.trackSelectedCtgIds || [],
  state.assembly?.subview?.trackPairSelectedCtgs || []]);
const sourceCtgs = state => collectFinalPathSourceCtgs(state.assembly);

function targetChr(node, state) {
  return node?.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName
    || resolveCurrentFinalPathChrName(state.assembly);
}

function paint(owner) {
  const { host, store } = owner;
  const state = store.getState();
  const visible = !state.activeRoute || state.activeRoute === "assembly";
  let selected = owner.selected;
  if (!visible || owner.scope !== scopeKey(state) || owner.editing !== editingSelectionKey(state)) {
    owner.selected = selected = null;
  }
  owner.scope = scopeKey(state);
  owner.editing = editingSelectionKey(state);
  if (selected?.phasedTrackId && !state.assembly?.phasedChrTracks?.some(track =>
    track.phasedTrackId === selected.phasedTrackId && track.label === selected.chrName)) {
    owner.selected = selected = null;
  }
  let segment = selected && state.assembly?.finalPathByChr?.[selected.chrName]?.segments
    ?.find(item => item.segmentId === selected.segmentId && item.type !== "gap");
  if (selected && !segment && !state.assembly?.loading) owner.selected = selected = null;
  const range = segment ? resolveFinalPathSourceRange(segment, sourceCtgs(state)) : null;
  if (selected && !range && !state.assembly?.loading) owner.selected = selected = null;
  for (const node of host.querySelectorAll(SEGMENT)) {
    const active = visible && selected && node.dataset.finalPathSegmentId === selected.segmentId
      && targetChr(node, state) === selected.chrName;
    if (active) node.setAttribute("data-final-path-selected", "1");
    else node.removeAttribute("data-final-path-selected");
  }
  const retained = new Set();
  for (const node of host.querySelectorAll("[data-source-interval-projection]")) {
    let projection;
    try { projection = JSON.parse(node.dataset.sourceIntervalProjection); } catch { continue; }
    const intersection = visible ? intersectSourceInterval(range, projection) : null;
    if (!intersection) continue;
    const d = node.dataset;
    const x = Number(d.trackRectX ?? d.subviewRectX), y = Number(d.trackRectY ?? d.subviewRectY);
    const width = Number(d.trackRectWidth ?? d.subviewRectWidth), height = Number(d.trackRectHeight ?? d.subviewRectHeight);
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) continue;
    let overlay = node.querySelector(OVERLAY);
    if (!overlay) {
      overlay = node.ownerDocument.createElementNS("http://www.w3.org/2000/svg", "rect");
      overlay.setAttribute("data-final-path-selection-overlay", "1");
      overlay.setAttribute("class", "final-path-source-highlight");
      overlay.setAttribute("pointer-events", "none");
      node.append(overlay);
    }
    const attrs = { x: x + intersection.startFraction * width, y,
      width: (intersection.endFraction - intersection.startFraction) * width, height,
      "data-source-start": intersection.sourceStart, "data-source-end": intersection.sourceEnd };
    for (const [key, value] of Object.entries(attrs)) {
      if (overlay.getAttribute(key) !== String(value)) overlay.setAttribute(key, String(value));
    }
    retained.add(overlay);
  }
  for (const overlay of host.querySelectorAll(OVERLAY)) if (!retained.has(overlay)) overlay.remove();
}

// A separate in-memory owner avoids expanding deletion/edit selections or
// persisting correlation into project data. Binding after a local DOM patch
// reapplies paint without changing focus, viewport, or the mounted graph.
export function bindFinalPathSelection(host, store) {
  host = host?.closest?.("#route-host") || host;
  if (!host?.querySelectorAll || !host?.addEventListener || !host.ownerDocument?.createElementNS) return;
  let owner = OWNERS.get(store);
  if (!owner) {
    owner = { store, host, selected: null, scope: scopeKey(store.getState()), editing: editingSelectionKey(store.getState()) };
    OWNERS.set(store, owner);
    store.subscribe?.(() => paint(owner));
  }
  owner.host = host;
  if (!host[BOUND]) {
    const clear = () => {
      if (!owner.selected) return;
      owner.selected = null;
      paint(owner);
    };
    const select = event => {
      if (event.type === "pointerover" && (event.pointerType === "touch" || event.buttons)) return;
      // A click may focus a table input, but must not pin a hover highlight.
      if (event.type === "focusin" && owner.pointerFocus) return;
      const node = event.target?.closest?.(SEGMENT);
      if (node && event.relatedTarget?.closest?.(SEGMENT) === node) return;
      const state = store.getState();
      if ((state.activeRoute && state.activeRoute !== "assembly") || state.assembly?.loading) return;
      const chrName = node && targetChr(node, state), segmentId = node?.dataset.finalPathSegmentId;
      const segment = state.assembly?.finalPathByChr?.[chrName]?.segments?.find(item => item.segmentId === segmentId);
      if (!segment || segment.type === "gap" || !resolveFinalPathSourceRange(segment, sourceCtgs(state))) {
        clear();
        return;
      }
      const phasedTrackId = state.assembly?.phasedChrTracks?.find(track => track.label === chrName)?.phasedTrackId;
      owner.trigger = event.type === "pointerover" ? "hover" : "focus";
      if (owner.selected?.chrName === chrName && owner.selected?.segmentId === segmentId) return;
      owner.selected = { chrName, segmentId, phasedTrackId };
      owner.scope = scopeKey(state); owner.editing = editingSelectionKey(state);
      paint(owner);
    };
    const leave = event => {
      const node = event.target?.closest?.(SEGMENT);
      if (!node || event.relatedTarget?.closest?.(SEGMENT) === node) return;
      if (event.type === "focusout" && owner.trigger !== "focus") return;
      const selected = owner.selected;
      if (selected?.segmentId === node.dataset.finalPathSegmentId
        && selected.chrName === targetChr(node, store.getState())) clear();
    };
    host.addEventListener("pointerover", select);
    host.addEventListener("pointerout", leave);
    host.addEventListener("pointerleave", () => { if (owner.trigger === "hover") clear(); });
    host.addEventListener("pointercancel", clear);
    host.addEventListener("dragstart", clear);
    host.addEventListener("pointerdown", event => {
      owner.pointerFocus = true;
      if (!event.target?.closest?.(SEGMENT) || event.pointerType === "touch" || owner.trigger === "focus") clear();
    }, true);
    host.ownerDocument.addEventListener("keydown", event => {
      owner.pointerFocus = false;
      if (event.key === "Escape") clear();
    }, true);
    host.addEventListener("focusin", select);
    host.addEventListener("focusout", leave);
    host.ownerDocument.defaultView?.addEventListener("blur", clear);
    host[BOUND] = true;
  }
  paint(owner);
}

// Snapshot-only cleanup: never clear the live selection to obtain an export.
export function snapshotWithoutFinalPathSelection(svgNode) {
  if (!svgNode?.cloneNode) return String(svgNode?.outerHTML || "");
  const clone = svgNode.cloneNode(true);
  for (const node of clone.querySelectorAll(OVERLAY)) node.remove();
  for (const node of clone.querySelectorAll("[data-final-path-selected]")) node.removeAttribute("data-final-path-selected");
  restoreSvgTooltipTitles(clone);
  return String(clone.outerHTML || "");
}
