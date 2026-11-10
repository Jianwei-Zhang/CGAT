import { restoreSvgTooltipTitles } from "../../tooltip-export.js";
import { resolveCurrentFinalPathChrName } from "./final-path-state.js";
import { collectFinalPathSourceCtgs, resolveFinalPathSourceRange } from "./final-path-presentation.js";
import { intersectSourceInterval } from "./source-interval-projection.js";

const BOUND = Symbol("finalPathSelectionBound");
const OWNERS = new WeakMap();
const SEGMENT = "[data-final-path-segment-id]";
const OVERLAY = "[data-final-path-selection-overlay]";
const SURFACE = "[data-final-path-graph-viewport], [data-final-path-card-list], .assembly-final-path-svg-wrap";
const EDITABLE = 'input, select, textarea, [contenteditable]:not([contenteditable="false"])';
const CONTROL = `${EDITABLE}, button, a[href], summary`;
const DRAG_DISTANCE_PX = 4;
const scopeKey = state => JSON.stringify([state.session?.workspacePath, state.session?.projectId,
  state.assembly?.selectedChrName, state.assembly?.activeFinalPathKeyByChr?.[state.assembly?.selectedChrName]
    || state.assembly?.activeFinalPathKey || ""]);
const editingSelectionKey = state => JSON.stringify([state.assembly?.selectedCtgId, state.assembly?.trackSelectedCtgIds || [],
  state.assembly?.subview?.trackPairSelectedCtgs || []]);
const selectionKey = selection => JSON.stringify([selection.chrName, selection.segmentId]);
const sourceCtgs = state => collectFinalPathSourceCtgs(state.assembly);
const isVisible = state => !state.activeRoute || state.activeRoute === "assembly";

function targetChr(node, state) {
  return node?.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName
    || resolveCurrentFinalPathChrName(state.assembly);
}

function phaseExists(selection, state) {
  return !selection.phasedTrackId || state.assembly?.phasedChrTracks?.some(track =>
    track.phasedTrackId === selection.phasedTrackId && track.label === selection.chrName);
}

function selectionRange(selection, state, ctgs) {
  const segment = state.assembly?.finalPathByChr?.[selection.chrName]?.segments
    ?.find(item => item.segmentId === selection.segmentId && item.type !== "gap");
  return segment ? resolveFinalPathSourceRange(segment, ctgs) : null;
}

function selectionFromNode(node, state, ctgs) {
  if (!node || !isVisible(state) || state.assembly?.loading) return null;
  const chrName = targetChr(node, state), segmentId = node.dataset.finalPathSegmentId;
  const phasedTrackId = state.assembly?.phasedChrTracks?.find(track => track.label === chrName)?.phasedTrackId;
  const selection = { chrName, segmentId, phasedTrackId };
  return selectionRange(selection, state, ctgs || sourceCtgs(state)) ? selection : null;
}

// A box is only a transient screen-space gesture. Pins remain unchanged until
// release; cancellation never changes editing selections or the project store.
function clearBox(owner) {
  const box = owner.box;
  owner.box = null;
  box?.overlay?.remove();
  delete owner.host.dataset.finalPathBoxSelecting;
  if (box?.captured) {
    try { owner.host.releasePointerCapture?.(box.pointerId); } catch { /* replaced host */ }
  }
}

function boxRect(box, x, y) {
  const bounds = box.surface.getBoundingClientRect();
  const clampX = value => Math.max(bounds.left, Math.min(bounds.right, value));
  const clampY = value => Math.max(bounds.top, Math.min(bounds.bottom, value));
  const startX = clampX(box.x), endX = clampX(x), startY = clampY(box.y), endY = clampY(y);
  return { left: Math.min(startX, endX), right: Math.max(startX, endX),
    top: Math.min(startY, endY), bottom: Math.max(startY, endY) };
}

function boxedSelections(box, rect, state) {
  const selected = new Map(), visuals = new Set(), ctgs = sourceCtgs(state);
  if (rect.right <= rect.left || rect.bottom <= rect.top) return selected;
  for (const node of box.surface.querySelectorAll(SEGMENT)) {
    // Table inputs repeat segment IDs. Hit-test their owning row only; graph
    // labels must not enlarge a segment's visual hit area.
    const visual = node.closest(".final-path-sort-row") || node.querySelector(".track-ctg") || node;
    if (visuals.has(visual)) continue;
    visuals.add(visual);
    const bounds = visual.getBoundingClientRect?.();
    if (!bounds || bounds.right <= bounds.left || bounds.bottom <= bounds.top
      || bounds.right <= rect.left || bounds.left >= rect.right
      || bounds.bottom <= rect.top || bounds.top >= rect.bottom) continue;
    const selection = selectionFromNode(node, state, ctgs);
    if (selection) selected.set(selectionKey(selection), selection);
  }
  return selected;
}

// Union only overlapping/adjacent inclusive source intervals. Never bridge an
// unadopted gap between two selected pieces of the same original Contig.
function sourceIntersections(ranges, projection) {
  const intersections = ranges.map(range => intersectSourceInterval(range, projection)).filter(Boolean)
    .sort((a, b) => a.sourceStart - b.sourceStart || a.sourceEnd - b.sourceEnd);
  const merged = [];
  for (const intersection of intersections) {
    const previous = merged.at(-1);
    if (previous && intersection.sourceStart <= previous.sourceEnd + 1) {
      previous.sourceEnd = Math.max(previous.sourceEnd, intersection.sourceEnd);
      previous.startFraction = Math.min(previous.startFraction, intersection.startFraction);
      previous.endFraction = Math.max(previous.endFraction, intersection.endFraction);
    } else merged.push({ ...intersection });
  }
  return merged;
}

function paint(owner) {
  const { host, store } = owner;
  const state = store.getState(), scope = scopeKey(state), editing = editingSelectionKey(state);
  if (owner.box && (!isVisible(state) || owner.scope !== scope || state.assembly?.loading
    || owner.box.surface.isConnected === false)) {
    if (owner.pointer) owner.pointer.cancelled = true;
    clearBox(owner);
  }
  if (!isVisible(state) || owner.scope !== scope) {
    owner.pinned.clear(); owner.transient = null; owner.pointer = null;
  } else if (owner.editing !== editing) {
    // Editing selections still end transient correlation, not the user's
    // independent read-only pinned comparison set.
    owner.transient = null;
  }
  owner.scope = scope; owner.editing = editing;
  const selected = new Map(owner.pinned);
  if (owner.transient) selected.set(selectionKey(owner.transient), owner.transient);
  const ctgs = selected.size ? sourceCtgs(state) : [];
  const ranges = [];
  for (const [key, selection] of selected) {
    const validPhase = phaseExists(selection, state);
    const range = validPhase ? selectionRange(selection, state, ctgs) : null;
    if (range) ranges.push(range);
    else {
      selected.delete(key);
      if (!validPhase || !state.assembly?.loading) {
        owner.pinned.delete(key);
        if (owner.transient && selectionKey(owner.transient) === key) owner.transient = null;
      }
    }
  }
  for (const node of host.querySelectorAll(SEGMENT)) {
    const active = selected.has(selectionKey({ chrName: targetChr(node, state), segmentId: node.dataset.finalPathSegmentId }));
    if (active) node.setAttribute("data-final-path-selected", "1");
    else node.removeAttribute("data-final-path-selected");
  }
  const retained = new Set();
  for (const node of host.querySelectorAll("[data-source-interval-projection]")) {
    let projection;
    try { projection = JSON.parse(node.dataset.sourceIntervalProjection); } catch { continue; }
    const intersections = sourceIntersections(ranges, projection);
    if (!intersections.length) continue;
    const d = node.dataset;
    const x = Number(d.trackRectX ?? d.subviewRectX), y = Number(d.trackRectY ?? d.subviewRectY);
    const width = Number(d.trackRectWidth ?? d.subviewRectWidth), height = Number(d.trackRectHeight ?? d.subviewRectHeight);
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) continue;
    const overlays = [...node.children].filter(child => child.matches(OVERLAY));
    for (const [index, intersection] of intersections.entries()) {
      let overlay = overlays[index];
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
  }
  for (const overlay of host.querySelectorAll(OVERLAY)) if (!retained.has(overlay)) overlay.remove();
}

// Pinned and transient correlation live outside deletion/edit selections and
// project persistence. Rebinding after a local DOM patch only reapplies paint.
export function bindFinalPathSelection(host, store) {
  host = host?.closest?.("#route-host") || host;
  if (!host?.querySelectorAll || !host?.addEventListener || !host.ownerDocument?.createElementNS) return;
  let owner = OWNERS.get(store);
  if (!owner) {
    owner = { store, host, pinned: new Map(), transient: null, pointer: null,
      scope: scopeKey(store.getState()), editing: editingSelectionKey(store.getState()) };
    OWNERS.set(store, owner);
    store.subscribe?.(() => paint(owner));
  }
  owner.host = host;
  if (!host[BOUND]) {
    const clearTransient = () => {
      if (!owner.transient) return;
      owner.transient = null;
      paint(owner);
    };
    const clearAll = () => {
      owner.pinned.clear(); owner.transient = null;
      paint(owner);
    };
    const select = event => {
      if (event.type === "pointerover" && (event.pointerType === "touch" || event.buttons)) return;
      // Pointer focus in an editable table field is not a pinned selection.
      if (event.type === "focusin" && owner.pointerFocus) return;
      const node = event.target?.closest?.(SEGMENT);
      if (node && event.relatedTarget?.closest?.(SEGMENT) === node) return;
      const state = store.getState();
      if (!isVisible(state) || state.assembly?.loading) return;
      const selection = selectionFromNode(node, state);
      if (!selection) { clearTransient(); return; }
      owner.trigger = event.type === "pointerover" ? "hover" : "focus";
      if (owner.transient && selectionKey(owner.transient) === selectionKey(selection)) return;
      owner.transient = selection;
      paint(owner);
    };
    const leave = event => {
      const node = event.target?.closest?.(SEGMENT);
      if (!node || event.relatedTarget?.closest?.(SEGMENT) === node) return;
      if (event.type === "focusout" && owner.trigger !== "focus") return;
      if (owner.transient?.segmentId === node.dataset.finalPathSegmentId
        && owner.transient.chrName === targetChr(node, store.getState())) clearTransient();
    };
    const cancelPointer = () => {
      clearBox(owner);
      if (owner.pointer) owner.pointer.cancelled = true;
      clearTransient();
    };
    const trackPointer = event => {
      const pointer = owner.pointer;
      if (!pointer || (pointer.id !== undefined && event.pointerId !== pointer.id)) return;
      if (Math.hypot(Number(event.clientX || 0) - pointer.x, Number(event.clientY || 0) - pointer.y) >= DRAG_DISTANCE_PX) pointer.moved = true;
      const box = owner.box;
      if (!box || pointer.cancelled || !pointer.moved) return;
      const state = store.getState();
      if (pointer.scope !== scopeKey(state) || !isVisible(state) || state.assembly?.loading
        || box.surface.isConnected === false || host.isConnected === false) { cancelPointer(); return; }
      event.preventDefault?.(); event.stopImmediatePropagation?.();
      const rect = boxRect(box, event.clientX, event.clientY);
      if (event.type === "pointerup") {
        for (const [key, selection] of boxedSelections(box, rect, state)) owner.pinned.set(key, selection);
        clearBox(owner); owner.transient = null; paint(owner);
        return;
      }
      if (!box.overlay) {
        host.dataset.finalPathBoxSelecting = "1";
        box.overlay = host.ownerDocument.createElement("div");
        box.overlay.setAttribute("class", "final-path-selection-box");
        box.overlay.setAttribute("aria-hidden", "true");
        host.ownerDocument.body.append(box.overlay);
        try { host.setPointerCapture?.(pointer.id); box.captured = true; } catch { /* unsupported pointer */ }
      }
      Object.assign(box.overlay.style, { left: `${rect.left}px`, top: `${rect.top}px`,
        width: `${rect.right - rect.left}px`, height: `${rect.bottom - rect.top}px` });
    };
    host.addEventListener("pointerover", select);
    host.addEventListener("pointerout", leave);
    host.addEventListener("pointerleave", () => { if (owner.trigger === "hover") clearTransient(); });
    host.addEventListener("dragstart", cancelPointer);
    host.addEventListener("pointerdown", event => {
      if (owner.box && owner.pointer?.id !== event.pointerId) return;
      clearBox(owner);
      owner.pointerFocus = true; owner.pointer = null;
      const node = event.target?.closest?.(SEGMENT);
      if (!node || event.pointerType === "touch" || owner.trigger === "focus") clearTransient();
      if (event.button !== 0 || event.defaultPrevented || event.target?.closest?.(CONTROL)) return;
      const state = store.getState();
      const selection = selectionFromNode(node, state);
      const blank = !node && event.target?.closest?.(SURFACE);
      if (!isVisible(state) || state.assembly?.loading || (!selection && !blank)) return;
      owner.pointer = { id: event.pointerId, key: selection ? selectionKey(selection) : null,
        x: Number(event.clientX || 0), y: Number(event.clientY || 0), scope: scopeKey(state),
        additive: Boolean(event.ctrlKey || event.metaKey), moved: false };
      if (blank && owner.pointer.additive && !event.altKey && event.pointerType !== "touch"
        && typeof blank.getBoundingClientRect === "function") {
        owner.box = { surface: blank, x: event.clientX, y: event.clientY, pointerId: event.pointerId };
        event.preventDefault?.(); event.stopImmediatePropagation?.();
      }
    }, true);
    host.addEventListener("click", event => {
      clearBox(owner);
      const pointer = owner.pointer; owner.pointer = null;
      if (!pointer || pointer.moved || pointer.cancelled || event.button !== 0 || event.defaultPrevented
        || event.target?.closest?.(CONTROL)) return;
      const state = store.getState();
      if (!isVisible(state) || state.assembly?.loading || pointer.scope !== scopeKey(state)) return;
      const node = event.target?.closest?.(SEGMENT), selection = selectionFromNode(node, state);
      const key = selection ? selectionKey(selection) : null;
      if (key !== pointer.key) return;
      if (!selection) {
        if (!node && event.target?.closest?.(SURFACE)) clearAll();
        return;
      }
      // A toggle-off must be visible immediately, even while still hovered.
      owner.transient = null;
      if (!pointer.additive) owner.pinned.clear();
      if (pointer.additive && owner.pinned.has(key)) owner.pinned.delete(key);
      else owner.pinned.set(key, selection);
      paint(owner);
    }, true);
    const document = host.ownerDocument;
    document.addEventListener("pointermove", trackPointer, true);
    document.addEventListener("pointerup", trackPointer, true);
    document.addEventListener("pointercancel", event => {
      if (owner.pointer && event.pointerId !== undefined && owner.pointer.id !== event.pointerId) return;
      cancelPointer();
    }, true);
    document.addEventListener("lostpointercapture", event => {
      if (owner.box && event.pointerId === owner.box.pointerId) cancelPointer();
    }, true);
    // Do not commit a stale screen-space rectangle after a scroll/layout move.
    document.addEventListener("scroll", () => { if (owner.box) cancelPointer(); }, true);
    document.addEventListener("keydown", event => {
      owner.pointerFocus = false;
      if (event.key === "Escape" && owner.box) {
        cancelPointer(); event.preventDefault?.(); event.stopImmediatePropagation?.(); return;
      }
      if (event.key === "Escape" && !event.defaultPrevented && !event.target?.closest?.(EDITABLE)) {
        if (owner.pointer) owner.pointer.cancelled = true;
        clearBox(owner); clearAll();
      }
    }, true);
    host.addEventListener("focusin", select);
    host.addEventListener("focusout", leave);
    document.defaultView?.addEventListener("blur", cancelPointer);
    document.defaultView?.addEventListener("resize", () => { if (owner.box) cancelPointer(); });
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
