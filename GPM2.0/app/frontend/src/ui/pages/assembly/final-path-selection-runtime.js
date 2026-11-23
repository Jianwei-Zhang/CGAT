import { restoreSvgTooltipTitles } from "../../tooltip-export.js";
import { resolveCurrentFinalPathChrName } from "./final-path-state.js";
import { collectFinalPathSourceCtgs, resolveFinalPathSourceRange } from "./final-path-presentation.js";
import { SOURCE, readSourceProjection, correlationSourceRange, selectedSourceRanges, clearSourceEditingSelections } from "./source-correlation.js";
import { intersectSourceInterval } from "./source-interval-projection.js";

const BOUND = Symbol("finalPathSelectionBound");
const OWNERS = new WeakMap();
const SEGMENT = "[data-final-path-segment-id]";
const OVERLAY = "[data-final-path-selection-overlay]";
const SURFACE = "[data-final-path-graph-viewport], [data-final-path-card-list], .assembly-final-path-svg-wrap";
const SOURCE_SURFACE = ".assembly-track-scroll";
const EDITABLE = 'input, select, textarea, [contenteditable]:not([contenteditable="false"])';
const CONTROL = `${EDITABLE}, button, a[href], summary`;
const DRAG_DISTANCE_PX = 4;
const scopeKey = state => JSON.stringify([state.session?.workspacePath, state.session?.projectId,
  state.assembly?.selectedChrName, state.assembly?.activeFinalPathKeyByChr?.[state.assembly?.selectedChrName]
    || state.assembly?.activeFinalPathKey || ""]);
const editingSelectionKey = state => JSON.stringify([state.assembly?.selectedCtgId, state.assembly?.trackSelectedCtgIds || [],
  state.assembly?.subview?.trackPairSelectedCtgs || [],
  (state.assembly?.subviewWorkspace?.windows || []).map(item => [item.id, item.opened, item.minimized,
    item.snapshot?.subview?.trackPairSelectedCtgs || []])]);
const sourceKey = range => JSON.stringify([range?.referenceChrName || "", range?.sourceSeqId || null,
  range?.assemblyCtgId || null, range?.datasetName || "", range?.contigName || "", range?.sourceStart, range?.sourceEnd]);
const editingCorrelationKey = owner => JSON.stringify([editingSelectionKey(owner.store.getState()),
  [...owner.surfaces.values()].map(binding => binding.store.getState().assembly?.subview?.trackPairSelectedCtgs || [])]);
const selectionKey = selection => JSON.stringify([selection.chrName, selection.segmentId]);
const sourceCtgs = state => [...new Set([
  ...collectFinalPathSourceCtgs(state.assembly),
  ...(state.assembly?.subviewWorkspace?.windows || []).filter(item => item.opened !== false)
    .flatMap(item => collectFinalPathSourceCtgs(item.snapshot)),
])];
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
  delete (box?.host || owner.host).dataset.finalPathBoxSelecting;
  if (box?.captured) {
    try { (box.host || owner.host).releasePointerCapture?.(box.pointerId); } catch { /* replaced host */ }
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

function paintIntersections(node, intersections, { x, y, width, height }, retained) {
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return;
  const overlays = [...node.children].filter(child => child.matches(OVERLAY));
  for (const [index, intersection] of intersections.entries()) {
    let overlay = overlays[index];
    if (!overlay) {
      overlay = node.ownerDocument.createElementNS("http://www.w3.org/2000/svg", "rect");
      overlay.setAttribute("data-final-path-selection-overlay", "1");
      overlay.setAttribute("class", "final-path-source-highlight");
      overlay.setAttribute("pointer-events", "none");
      const markerLayer = node.querySelector?.('[data-track-annotation-markers="1"]');
      if (markerLayer && markerLayer.parentNode === node) {
        node.insertBefore(overlay, markerLayer);
      } else {
        node.append(overlay);
      }
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

function paint(owner) {
  const { store } = owner;
  for (const [surface, binding] of owner.surfaces) {
    if (surface.isConnected === false || binding.store.isLocalViewAlive?.() === false) binding.dispose();
  }
  const nodes = (selector, currentOnly = false) => [...owner.surfaces]
    .filter(([, binding]) => !currentOnly || binding.scope === scopeKey(store.getState()))
    .flatMap(([surface]) => [...surface.querySelectorAll(selector)]);
  const state = store.getState(), scope = scopeKey(state), editing = editingSelectionKey(state);
  if (owner.box && (!isVisible(state) || owner.scope !== scope || state.assembly?.loading
    || owner.box.surface.isConnected === false)) {
    if (owner.pointer) owner.pointer.cancelled = true;
    clearBox(owner);
  }
  if (!isVisible(state) || owner.scope !== scope) {
    owner.pinned.clear(); owner.sourcePinned.clear(); owner.dismissedEditing = null;
    owner.transient = null; owner.sourceTransient = null; owner.pointer = null;
  } else if (owner.editing !== editing) {
    // Editing selections still end transient correlation, not the user's
    // independent read-only pinned comparison set.
    owner.transient = null; owner.sourceTransient = null;
  }
  owner.scope = scope; owner.editing = editing;
  const selected = new Map(owner.pinned);
  if (owner.transient) selected.set(selectionKey(owner.transient), owner.transient);
  const correlationEditing = editingCorrelationKey(owner);
  if (owner.dismissedEditing !== null && owner.dismissedEditing !== correlationEditing) owner.dismissedEditing = null;
  const triggers = isVisible(state) && !state.assembly?.loading && owner.dismissedEditing !== editingCorrelationKey(owner)
    ? selectedSourceRanges(new Map([...owner.surfaces].filter(([, binding]) => binding.scope === scope)), store) : [];
  if (isVisible(state) && !state.assembly?.loading) {
    for (const [key, pin] of owner.sourcePinned) {
      if (pin.windowId && (state.assembly?.subviewWorkspace?.generation !== pin.generation
        || !state.assembly.subviewWorkspace?.windows?.some(item => item.id === pin.windowId && item.opened !== false))) {
        owner.sourcePinned.delete(key);
      } else triggers.push(pin.range);
    }
  }
  if (owner.sourceTransient && !state.assembly?.loading) {
    const { node, host: triggerHost } = owner.sourceTransient;
    if (!owner.surfaces.has(triggerHost) || node.isConnected === false
      || !(triggerHost.contains ? triggerHost.contains(node) : [...triggerHost.querySelectorAll(SOURCE)].includes(node))) {
      owner.sourceTransient = null;
    } else {
      const range = correlationSourceRange(node);
      if (range) triggers.push(range);
    }
  }
  const ctgs = selected.size || triggers.length ? sourceCtgs(state) : [], ctgsById = new Map(), pathIndexes = new Map(), resolved = new Map();
  for (const ctg of ctgs) {
    const id = Number(ctg.assemblyCtgId);
    if (!ctgsById.has(id)) ctgsById.set(id, []);
    ctgsById.get(id).push(ctg);
  }
  const resolveRange = selection => {
    const key = selectionKey(selection);
    if (!resolved.has(key)) {
      if (!pathIndexes.has(selection.chrName)) pathIndexes.set(selection.chrName,
        new Map((state.assembly?.finalPathByChr?.[selection.chrName]?.segments || []).map(segment => [segment.segmentId, segment])));
      const segment = pathIndexes.get(selection.chrName).get(selection.segmentId);
      resolved.set(key, resolveFinalPathSourceRange(segment,
        ctgsById.get(Number(segment?.splitFragmentCtgId || segment?.assemblyCtgId)) || []));
    }
    return resolved.get(key);
  };
  const ranges = [...triggers];
  for (const [key, selection] of selected) {
    const validPhase = phaseExists(selection, state);
    const range = validPhase ? resolveRange(selection) : null;
    if (range) ranges.push(range);
    else {
      selected.delete(key);
      if (!validPhase || !state.assembly?.loading) {
        owner.pinned.delete(key);
        if (owner.transient && selectionKey(owner.transient) === key) owner.transient = null;
      }
    }
  }
  const retained = new Set();
  // Resolve each Final Path instance separately. A Local fragment can intersect
  // only part of one result; do not turn that into a whole-result outline.
  for (const node of nodes(SEGMENT)) {
    const selection = { chrName: targetChr(node, state), segmentId: node.dataset.finalPathSegmentId };
    const active = selected.has(selectionKey(selection));
    if (active) node.setAttribute("data-final-path-selected", "1");
    else node.removeAttribute("data-final-path-selected");
    const projection = triggers.length ? resolveRange(selection) : null;
    const intersections = projection ? sourceIntersections(triggers, projection) : [];
    if (intersections.length) node.setAttribute("data-final-path-correlated", "1");
    else node.removeAttribute("data-final-path-correlated");
    const bar = node.querySelector(".track-ctg");
    if (!active && bar && intersections.length) {
      paintIntersections(node, intersections, Object.fromEntries(["x", "y", "width", "height"]
        .map(key => [key, Number(bar.getAttribute(key))])), retained);
    }
  }
  for (const node of ranges.length ? nodes(SOURCE, true) : []) {
    const projection = readSourceProjection(node);
    if (!projection) continue;
    const intersections = sourceIntersections(ranges, projection);
    if (!intersections.length) continue;
    const d = node.dataset;
    const x = Number(d.trackRectX ?? d.subviewRectX), y = Number(d.trackRectY ?? d.subviewRectY);
    const width = Number(d.trackRectWidth ?? d.subviewRectWidth), height = Number(d.trackRectHeight ?? d.subviewRectHeight);
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) continue;
    paintIntersections(node, intersections, { x, y, width, height }, retained);
  }
  for (const overlay of nodes(OVERLAY)) if (!retained.has(overlay)) overlay.remove();
}

// Pinned and transient correlation live outside deletion/edit selections and
// project persistence. Rebinding after a local DOM patch only reapplies paint.
export function bindFinalPathSelection(host, store) {
  host = host?.closest?.("#route-host") || host;
  if (!host?.querySelectorAll || !host?.addEventListener || !host.ownerDocument?.createElementNS) return;
  const surfaceStore = store;
  store = store.localViewRootStore || store;
  let owner = OWNERS.get(store);
  if (!owner) {
    owner = { store, host, surfaces: new Map(), pinned: new Map(), sourcePinned: new Map(), dismissedEditing: null, transient: null, sourceTransient: null, pointer: null,
      scope: scopeKey(store.getState()), editing: editingSelectionKey(store.getState()) };
    OWNERS.set(store, owner);
    store.subscribe?.(() => paint(owner));
  }
  if (!surfaceStore.localViewRootStore) owner.host = host;
  if (!host[BOUND]) {
    const cleanups = [];
    const listen = (target, type, handler, capture = false) => {
      target?.addEventListener?.(type, handler, capture);
      cleanups.push(() => target?.removeEventListener?.(type, handler, capture));
    };
    const binding = { scope: scopeKey(store.getState()), store: host.ownerDocument === owner.host.ownerDocument ? store : surfaceStore,
      dispose() {
        owner.surfaces.delete(host);
        for (const [key, pin] of owner.sourcePinned) if (pin.host === host) owner.sourcePinned.delete(key);
        if (owner.sourceTransient?.host === host) owner.sourceTransient = null;
        if (owner.transientHost === host) owner.transient = null;
        if (owner.box?.host === host) clearBox(owner);
        cleanups.splice(0).forEach(dispose => dispose());
        delete host[BOUND];
      },
    };
    owner.surfaces.set(host, binding);
    const clearTransient = () => {
      const localSource = owner.sourceTransient?.host === host;
      const localResult = owner.transient && owner.transientHost === host;
      if (!localResult && !localSource) return;
      if (localResult) owner.transient = null;
      if (localSource) owner.sourceTransient = null;
      paint(owner);
    };
    const clearAll = () => {
      owner.pinned.clear(); owner.sourcePinned.clear();
      owner.dismissedEditing = editingCorrelationKey(owner);
      owner.transient = null; owner.sourceTransient = null;
      paint(owner);
    };
    const select = event => {
      binding.scope = scopeKey(store.getState());
      if (event.type === "pointerover" && (event.pointerType === "touch" || event.buttons)) return;
      // Pointer focus in an editable table field is not a pinned selection.
      if (event.type === "focusin" && owner.pointerFocus) return;
      const node = event.target?.closest?.(SEGMENT);
      if (node && event.relatedTarget?.closest?.(SEGMENT) === node) return;
      const state = store.getState();
      if (!isVisible(state) || state.assembly?.loading) return;
      const source = !node && event.target?.closest?.(SOURCE);
      if (source) {
        if (event.relatedTarget?.closest?.(SOURCE) === source) return;
        owner.trigger = event.type === "pointerover" ? "hover" : "focus";
        owner.transient = null;
        owner.sourceTransient = { node: source, host };
        paint(owner);
        return;
      }
      const selection = selectionFromNode(node, state);
      if (!selection) { clearTransient(); return; }
      owner.sourceTransient = null;
      owner.transientHost = host;
      owner.trigger = event.type === "pointerover" ? "hover" : "focus";
      if (owner.transient && selectionKey(owner.transient) === selectionKey(selection)) return;
      owner.transient = selection;
      paint(owner);
    };
    const leave = event => {
      const source = event.target?.closest?.(SOURCE);
      if (source && owner.sourceTransient?.node === source) {
        if (event.relatedTarget?.closest?.(SOURCE) === source || (event.type === "focusout" && owner.trigger !== "focus")) return;
        clearTransient(); return;
      }
      const node = event.target?.closest?.(SEGMENT);
      if (!node || event.relatedTarget?.closest?.(SEGMENT) === node) return;
      if (event.type === "focusout" && owner.trigger !== "focus") return;
      if (owner.transient?.segmentId === node.dataset.finalPathSegmentId
        && owner.transient.chrName === targetChr(node, store.getState())) clearTransient();
    };
    const cancelPointer = () => {
      // Focus can move from Main to a peer after that peer's pointerdown.
      // A late blur/cancel in another document must not cancel its new click.
      if (owner.box?.host === host) clearBox(owner);
      if (owner.pointer?.host === host) owner.pointer.cancelled = true;
      clearTransient();
    };
    const trackPointer = event => {
      const pointer = owner.pointer;
      if (pointer?.host && pointer.host !== host) return;
      if (!pointer || (pointer.id !== undefined && event.pointerId !== pointer.id)) return;
      if ((pointer.source && Math.abs(Number(event.clientX || 0) - pointer.x) >= 2)
        || Math.hypot(Number(event.clientX || 0) - pointer.x, Number(event.clientY || 0) - pointer.y) >= DRAG_DISTANCE_PX) pointer.moved = true;
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
    listen(host, "pointerover", select);
    listen(host, "pointerout", leave);
    listen(host, "pointerleave", () => { if (owner.trigger === "hover") clearTransient(); });
    listen(host, "dragstart", cancelPointer);
    listen(host, "pointerdown", event => {
      binding.scope = scopeKey(store.getState());
      if (owner.box && owner.pointer?.id !== event.pointerId) return;
      clearBox(owner);
      owner.pointerFocus = true; owner.pointer = null;
      const node = event.target?.closest?.(SEGMENT);
      if (!node || event.pointerType === "touch" || owner.trigger === "focus") clearTransient();
      if (event.button !== 0 || event.defaultPrevented || event.target?.closest?.(CONTROL)) return;
      const state = store.getState();
      const source = !node && event.target?.closest?.(SOURCE);
      const sourceBlank = !node && !source && event.target?.closest?.(SOURCE_SURFACE);
      if (source || sourceBlank) {
        // Ctrl/Cmd belongs to entering Local comparisons or existing edit-box
        // selection. Never intercept those gestures or convert them to pins.
        if (event.ctrlKey || event.metaKey || event.altKey) {
          return;
        }
        if (!isVisible(state) || state.assembly?.loading) return;
        const range = source && correlationSourceRange(source);
        if (source && !range) return;
        owner.pointer = { host, id: event.pointerId, source: source || null, sourceBlank: Boolean(sourceBlank),
          range, x: Number(event.clientX || 0), y: Number(event.clientY || 0),
          scope: scopeKey(state), additive: Boolean(event.shiftKey), moved: false };
        return;
      }
      const selection = selectionFromNode(node, state);
      const blank = !node && event.target?.closest?.(SURFACE);
      if (!isVisible(state) || state.assembly?.loading || (!selection && !blank)) return;
      owner.pointer = { host, id: event.pointerId, key: selection ? selectionKey(selection) : null,
        x: Number(event.clientX || 0), y: Number(event.clientY || 0), scope: scopeKey(state),
        additive: Boolean(event.ctrlKey || event.metaKey), moved: false };
      if (blank && owner.pointer.additive && !event.altKey && event.pointerType !== "touch"
        && typeof blank.getBoundingClientRect === "function") {
        owner.box = { host, surface: blank, x: event.clientX, y: event.clientY, pointerId: event.pointerId };
        event.preventDefault?.(); event.stopImmediatePropagation?.();
      }
    }, true);
    listen(host, "click", event => {
      if (owner.pointer?.host && owner.pointer.host !== host) return;
      clearBox(owner);
      const pointer = owner.pointer; owner.pointer = null;
      if (!pointer && (event.ctrlKey || event.metaKey) && !event.altKey && !event.defaultPrevented
        && !event.target?.closest?.(`${SOURCE}, ${CONTROL}`) && event.target?.closest?.(SOURCE_SURFACE)) {
        // The existing box owner commits on pointerup (including unchanged
        // sets). Its following click may re-enable a deliberately dismissed set.
        owner.dismissedEditing = null;
        paint(owner);
      }
      if (!pointer || pointer.moved || pointer.cancelled || event.button !== 0 || event.defaultPrevented
        || event.target?.closest?.(CONTROL)) return;
      const state = store.getState();
      if (!isVisible(state) || state.assembly?.loading || pointer.scope !== scopeKey(state)) return;
      if (pointer.source || pointer.sourceBlank) {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        const source = event.target?.closest?.(SOURCE);
        if (pointer.sourceBlank) {
          if (!source && event.target?.closest?.(SOURCE_SURFACE)) clearAll();
          return;
        }
        if (source !== pointer.source) return;
        const key = sourceKey(pointer.range), wasPinned = owner.sourcePinned.has(key);
        owner.transient = null; owner.sourceTransient = null;
        owner.dismissedEditing = editingCorrelationKey(owner);
        if (!pointer.additive) { owner.pinned.clear(); owner.sourcePinned.clear(); }
        if (wasPinned) owner.sourcePinned.delete(key);
        else owner.sourcePinned.set(key, { host, range: pointer.range,
          windowId: source.closest?.("[data-local-view-window]")?.dataset.localViewWindow,
          generation: state.assembly?.subviewWorkspace?.generation });
        paint(owner);
        return;
      }
      const node = event.target?.closest?.(SEGMENT), selection = selectionFromNode(node, state);
      const key = selection ? selectionKey(selection) : null;
      if (key !== pointer.key) return;
      if (!selection) {
        if (!node && event.target?.closest?.(SURFACE)) clearAll();
        return;
      }
      // A toggle-off must be visible immediately, even while still hovered.
      owner.transient = null;
      if (!pointer.additive) {
        owner.pinned.clear(); owner.sourcePinned.clear();
        owner.dismissedEditing = editingCorrelationKey(owner);
      }
      if (pointer.additive && owner.pinned.has(key)) owner.pinned.delete(key);
      else owner.pinned.set(key, selection);
      paint(owner);
    }, true);
    const document = host.ownerDocument;
    listen(document, "pointermove", trackPointer, true);
    listen(document, "pointerup", trackPointer, true);
    listen(document, "pointercancel", event => {
      if (owner.pointer && event.pointerId !== undefined && owner.pointer.id !== event.pointerId) return;
      cancelPointer();
    }, true);
    listen(document, "lostpointercapture", event => {
      if (owner.box && event.pointerId === owner.box.pointerId) cancelPointer();
    }, true);
    // Do not commit a stale screen-space rectangle after a scroll/layout move.
    listen(document, "scroll", () => { if (owner.box) cancelPointer(); }, true);
    listen(document, "keydown", event => {
      owner.pointerFocus = false;
      if (event.key === "Escape" && owner.box) {
        cancelPointer(); event.preventDefault?.(); event.stopImmediatePropagation?.(); return;
      }
      if (event.key === "Escape" && !event.defaultPrevented
        && !event.target?.closest?.(`${EDITABLE}, dialog, [role="dialog"], [data-subview-tools-host], [data-track-members-dialog]`)) {
        if (owner.pointer) owner.pointer.cancelled = true;
        clearBox(owner); clearAll();
        const state = store.getState();
        if (isVisible(state) && (!state.assembly?.activeTab || state.assembly.activeTab === "assembly")) {
          clearSourceEditingSelections(owner.surfaces, store);
        }
      }
    }, true);
    listen(host, "focusin", select);
    listen(host, "focusout", leave);
    listen(document.defaultView, "blur", cancelPointer);
    listen(document.defaultView, "resize", () => { if (owner.box) cancelPointer(); });
    listen(document, "scroll", () => { if (!owner.box) paint(owner); }, true);
    listen(document.defaultView, "pagehide", () => { binding.dispose(); paint(owner); });
    host[BOUND] = binding;
  }
  if (host[BOUND]) host[BOUND].scope = scopeKey(store.getState());
  paint(owner);
}

// Snapshot-only cleanup: never clear the live selection to obtain an export.
export function snapshotWithoutFinalPathSelection(svgNode) {
  if (!svgNode?.cloneNode) return String(svgNode?.outerHTML || "");
  const clone = svgNode.cloneNode(true);
  for (const node of clone.querySelectorAll(OVERLAY)) node.remove();
  for (const attr of ["data-final-path-selected", "data-final-path-correlated"]) {
    for (const node of clone.querySelectorAll(`[${attr}]`)) node.removeAttribute(attr);
  }
  restoreSvgTooltipTitles(clone);
  return String(clone.outerHTML || "");
}

// Native windows are independent documents but share Main's owner and store.
export function unbindFinalPathSelection(host, store) {
  host = host?.closest?.("#route-host") || host;
  host?.[BOUND]?.dispose();
  const owner = OWNERS.get(store.localViewRootStore || store);
  if (owner) paint(owner);
}
