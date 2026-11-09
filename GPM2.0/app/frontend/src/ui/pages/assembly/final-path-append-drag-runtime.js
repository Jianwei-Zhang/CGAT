import { createFinalPathDragCopy } from "./final-path-append-preview.js";
import { resolveAssemblyCtgContextTarget, resolveSubviewFragmentContextTarget,
  resolveSubviewTrackPairContextTarget } from "./context-menu.js";
import { buildSubviewFinalPathContext } from "./final-path-contig-context.js";

const BOUND = Symbol("finalPathAppendDrag");
const SOURCE = "[data-track-contig-id][data-track-role], [data-subview-track-pair-contig-id], [data-subview-fragment-key]";
const ownerOf = node => node?.closest?.("[data-local-view-window]") || null;

export function resolveFinalPathDragSource(target) {
  if (!target?.closest?.(SOURCE)) return null;
  const fragmentNode = target.closest("[data-subview-fragment-key]");
  if (fragmentNode) {
    const fragment = resolveSubviewFragmentContextTarget(target);
    return fragment ? buildSubviewFinalPathContext(fragment) : null;
  }
  const local = resolveSubviewTrackPairContextTarget(target);
  return local ? buildSubviewFinalPathContext(local) : resolveAssemblyCtgContextTarget(target);
}

export function resolveFinalPathDropTarget(target) {
  const surface = target?.closest?.("[data-final-path-graph-viewport], [data-final-path-card-list]");
  const card = surface?.closest?.(".final-path-card");
  if (!surface || !card || !["graph", "table"].includes(card.dataset?.finalPathViewMode)) return null;
  const destination = surface.closest("[data-final-path-target-chr-name]");
  const targetChrName = String(destination?.dataset?.finalPathTargetChrName || "").trim();
  return targetChrName ? { surface, targetChrName } : null;
}

function scopeOf(state) {
  return JSON.stringify([state.session?.workspacePath, state.session?.projectId,
    state.activeRoute, state.assembly?.activeTab, state.assembly?.selectedChrName, state.assembly?.supportDatasetId]);
}

export function bindFinalPathAppendDrag(host, store, deps) {
  const root = ownerOf(host) || host?.closest?.("#route-host") || host;
  const doc = root?.ownerDocument;
  if (!root?.addEventListener || !doc?.elementFromPoint) return null;
  if (root[BOUND]) { root[BOUND].deps = deps; return root[BOUND]; }
  const win = doc.defaultView;
  let gesture = null, frame = null, suppressClickUntil = 0;
  const runtime = { deps, cancel, destroy };
  root[BOUND] = runtime;

  function isCurrent() {
    if (!gesture || root.isConnected === false || root.hidden || gesture.source.isConnected === false
      || store.isLocalViewAlive?.() === false) return false;
    const state = store.getState();
    return scopeOf(state) === gesture.scope && !state.assembly?.loading && !state.assembly?.sourceEditingReloadRequired
      && state.assembly?.chrCtgs === gesture.main && state.assembly?.supportChrCtgs === gesture.support
      && state.assembly?.refTrackMembers === gesture.reference
      && (!store.localViewRootStore || state.assembly?.subview?.summary === gesture.summary);
  }

  function clearTarget() {
    gesture?.target?.surface?.classList.remove("is-final-path-append-target");
    gesture?.preview?.remove?.();
    if (gesture) { gesture.target = null; gesture.preview = null; }
  }

  function position() {
    if (!gesture?.ghost) return;
    const { x, y, ghost } = gesture;
    ghost.style.left = `${Math.max(0, Math.min(x + 16, win.innerWidth - ghost.offsetWidth - 8))}px`;
    ghost.style.top = `${Math.max(0, Math.min(y + 16, win.innerHeight - ghost.offsetHeight - 8))}px`;
    const target = resolveFinalPathDropTarget(doc.elementFromPoint(x, y));
    if (target?.surface !== gesture.target?.surface) {
      clearTarget(); gesture.target = target;
      if (target && runtime.deps.preview) {
        gesture.preview = runtime.deps.preview(doc, store.getState(), gesture.context, target);
        if (gesture.preview) { doc.body.appendChild(gesture.preview); gesture.previewNeedsScroll = true; }
        else gesture.target = null;
      }
    }
    gesture.target?.surface.classList.add("is-final-path-append-target");
    if (gesture.preview) {
      const rect = gesture.target.surface.getBoundingClientRect();
      Object.assign(gesture.preview.style, { left: `${rect.left}px`, top: `${rect.top}px`,
        width: `${rect.width}px`, height: `${rect.height}px` });
      if (gesture.previewNeedsScroll) {
        const previewScroll = gesture.preview.querySelector("[data-final-path-append-preview-scroll]");
        if (previewScroll) {
          previewScroll.scrollLeft = Math.max(0, previewScroll.scrollWidth - previewScroll.clientWidth);
          previewScroll.scrollTop = Math.max(0, previewScroll.scrollHeight - previewScroll.clientHeight);
        }
        gesture.previewNeedsScroll = false;
      }
    }
    ghost.classList.toggle("is-valid", Boolean(gesture.target));
    const labels = runtime.deps.labels(store.getState());
    (gesture.caption || ghost).textContent = gesture.target ? labels.drop.replace("{path}", gesture.target.targetChrName) : labels.drag;
  }

  function scrollFrame() {
    frame = null;
    if (!gesture?.moved) return;
    if (!isCurrent()) { cancel(); return; }
    const scroller = root.closest?.(".stage-panel") || doc.scrollingElement;
    const rect = scroller === doc.scrollingElement ? { top: 0, bottom: win.innerHeight } : scroller?.getBoundingClientRect();
    if (rect && scroller) {
      const delta = gesture.y > rect.bottom - 48 ? 16 : gesture.y < rect.top + 48 ? -16 : 0;
      if (delta) { scroller.scrollTop += delta; position(); }
    }
    frame = win.requestAnimationFrame(scrollFrame);
  }

  function onDown(event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || gesture
      || ownerOf(event.target) !== ownerOf(root)) return;
    const scroll = event.target?.closest?.("[data-view-interaction-mode='hand']");
    if (!scroll) return;
    const context = resolveFinalPathDragSource(event.target);
    if (!context) return;
    const state = store.getState();
    if (state.assembly?.loading || state.assembly?.sourceEditingReloadRequired) return;
    gesture = { context, scope: scopeOf(state), source: event.target.closest(SOURCE), originalTarget: event.target, pointerId: event.pointerId,
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, moved: false,
      main: state.assembly.chrCtgs, support: state.assembly.supportChrCtgs,
      reference: state.assembly.refTrackMembers, summary: state.assembly.subview?.summary };
    // A contig drag owns this gesture. Blank plot space still belongs to pan.
    event.preventDefault(); event.stopImmediatePropagation();
    try { root.setPointerCapture?.(event.pointerId); } catch { /* synthetic pointer */ }
    win.addEventListener("pointermove", onMove, true);
    win.addEventListener("pointerup", onUp, true);
    win.addEventListener("pointercancel", cancel, true);
    win.addEventListener("keydown", onKey, true);
    win.addEventListener("blur", cancel);
  }

  function onMove(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (!isCurrent()) { cancel(); return; }
    gesture.x = event.clientX; gesture.y = event.clientY;
    if (!gesture.moved && Math.hypot(gesture.x - gesture.startX, gesture.y - gesture.startY) < 4) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (!gesture.moved) {
      gesture.moved = true;
      const ghost = doc.createElement("div");
      ghost.className = "final-path-append-ghost"; ghost.setAttribute("role", "status");
      const copy = createFinalPathDragCopy(doc, gesture.originalTarget);
      if (copy) {
        ghost.appendChild(copy);
        const caption = doc.createElement("div"); caption.className = "final-path-append-caption";
        ghost.appendChild(caption); gesture.caption = caption;
      }
      doc.body.appendChild(ghost); gesture.ghost = ghost;
      if (ownerOf(root)) {
        gesture.previousPointerEvents = root.style.pointerEvents;
        root.style.pointerEvents = "none";
        root.classList.add("is-final-path-append-source");
      }
      frame = win.requestAnimationFrame(scrollFrame);
    }
    position();
  }

  function onUp(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const valid = isCurrent();
    gesture.x = event.clientX; gesture.y = event.clientY;
    if (gesture.moved) position();
    const { target, context, moved } = gesture;
    cancel();
    if (!moved) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (valid && target) {
      Promise.resolve(runtime.deps.append(root, store, context, { targetChrName: target.targetChrName }))
        .catch(error => runtime.deps.onError?.(root, store, error));
    }
  }

  function onKey(event) { if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); cancel(); } }
  function onClick(event) {
    if (Date.now() >= suppressClickUntil) return;
    event.preventDefault(); event.stopImmediatePropagation();
  }
  function cancel() {
    if (!gesture) return;
    clearTarget();
    if (gesture.moved) suppressClickUntil = Date.now() + 300;
    gesture.ghost?.remove();
    if (gesture.previousPointerEvents !== undefined) {
      root.style.pointerEvents = gesture.previousPointerEvents;
      root.classList.remove("is-final-path-append-source");
    }
    try { root.releasePointerCapture?.(gesture.pointerId); } catch { /* already released */ }
    gesture = null;
    if (frame !== null) win.cancelAnimationFrame(frame);
    frame = null;
    win.removeEventListener("pointermove", onMove, true);
    win.removeEventListener("pointerup", onUp, true);
    win.removeEventListener("pointercancel", cancel, true);
    win.removeEventListener("keydown", onKey, true);
    win.removeEventListener("blur", cancel);
  }
  function destroy() {
    cancel(); root.removeEventListener("pointerdown", onDown, true); root.removeEventListener("click", onClick, true);
    delete root[BOUND];
  }
  root.addEventListener("pointerdown", onDown, true);
  root.addEventListener("click", onClick, true);
  return runtime;
}
