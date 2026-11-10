import { resolveSubviewContigDropTarget } from "./contig-drop-target.js";
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
  return targetChrName ? { kind: "final", surface, targetChrName } : null;
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
  let gesture = null, frame = null, suppressClickUntil = 0, probeTimer = null;
  const runtime = { deps, cancel, destroy };
  root[BOUND] = runtime;

  function isCurrent() {
    if (!gesture || root.isConnected === false || root.hidden || gesture.source.isConnected === false
      || store.isLocalViewAlive?.() === false) return false;
    const state = store.getState();
    return scopeOf(state) === gesture.scope && !state.assembly?.loading && !state.assembly?.mainViewHistory?.inFlight
      && !state.assembly?.sourceEditingReloadRequired
      && state.assembly?.chrCtgs === gesture.main && state.assembly?.supportChrCtgs === gesture.support
      && state.assembly?.refTrackMembers === gesture.reference
      && state.assembly?.subviewWorkspace?.generation === gesture.generation
      && (!store.localViewRootStore || state.assembly?.subview?.summary === gesture.summary);
  }
  function clearTarget() {
    gesture?.target?.surface?.classList.remove("is-final-path-append-target");
    gesture?.preview?.remove?.();
    if (gesture) { gesture.target = null; gesture.preview = null; }
  }
  function targetAt(point) {
    const node = point?.document?.elementFromPoint(point.x, point.y);
    const final = resolveFinalPathDropTarget(node);
    if (final) return final;
    if (!runtime.deps.dropLocal) return null;
    const local = resolveSubviewContigDropTarget(node, point.y);
    if (!local) return null;
    // Local-to-local copies are not implicit: this gesture only moves within
    // its source task, while Main may add to any visible task.
    if (gesture.owner && (local.id !== gesture.owner.dataset.localViewWindow
      || local.lane === gesture.localContext?.slot)) return null;
    return local;
  }
  function position(point = gesture?.point) {
    if (!gesture?.ghost) return;
    gesture.point = point;
    const target = targetAt(point);
    const targetDoc = point?.document;
    if (!targetDoc) { clearTarget(); gesture.ghost.style.display = "none"; return; }
    const peer = targetDoc.defaultView;
    const ghost = gesture.ghost;
    if (ghost.ownerDocument !== targetDoc) targetDoc.body.appendChild(ghost);
    ghost.style.display = "";
    ghost.style.left = `${Math.max(0, Math.min(point.x + 16, peer.innerWidth - ghost.offsetWidth - 8))}px`;
    ghost.style.top = `${Math.max(0, Math.min(point.y + 16, peer.innerHeight - ghost.offsetHeight - 8))}px`;
    if (target?.surface !== gesture.target?.surface || target?.lane !== gesture.target?.lane) {
      clearTarget(); gesture.target = target;
      if (target?.kind === "final" && runtime.deps.preview) {
        gesture.preview = runtime.deps.preview(targetDoc, store.getState(), gesture.context, target);
        if (gesture.preview) { targetDoc.body.appendChild(gesture.preview); gesture.previewNeedsScroll = true; }
        else gesture.target = null;
      } else if (target?.kind === "local") {
        gesture.preview = targetDoc.createElement("div");
        gesture.preview.className = "contig-drop-lane-preview";
        targetDoc.body.appendChild(gesture.preview);
      }
    }
    // Geometry may move during autoscroll even though the destination is unchanged.
    if (gesture.target && target) gesture.target = target;
    gesture.target?.surface.classList.add("is-final-path-append-target");
    if (gesture.preview) {
      const rect = target?.kind === "local" ? target.rect : gesture.target.surface.getBoundingClientRect();
      Object.assign(gesture.preview.style, { left: `${rect.left}px`, top: `${rect.top}px`,
        width: `${rect.width}px`, height: `${rect.height ?? Math.max(1, rect.bottom - rect.top)}px` });
      if (gesture.previewNeedsScroll) {
        const scroll = gesture.preview.querySelector("[data-final-path-append-preview-scroll]");
        if (scroll) { scroll.scrollLeft = Math.max(0, scroll.scrollWidth - scroll.clientWidth);
          scroll.scrollTop = Math.max(0, scroll.scrollHeight - scroll.clientHeight); }
        gesture.previewNeedsScroll = false;
      }
    }
    ghost.classList.toggle("is-valid", Boolean(gesture.target));
    const labels = runtime.deps.labels(store.getState());
    (gesture.caption || ghost).textContent = gesture.target?.kind === "local"
      ? (gesture.owner ? labels.moveLane : labels.addLane)?.replace("{lane}", labels[gesture.target.lane]) || labels.drag
      : gesture.target ? labels.drop.replace("{path}", gesture.target.targetChrName) : labels.drag;
  }
  function scrollFrame() {
    frame = null;
    if (!gesture?.moved) return;
    if (!isCurrent()) { cancel(); return; }
    const point = gesture.point;
    const targetDoc = point?.document;
    const scroller = targetDoc && (gesture.target?.surface?.closest?.(".stage-panel") || targetDoc.scrollingElement);
    const rect = scroller === targetDoc?.scrollingElement
      ? { top: 0, bottom: targetDoc?.defaultView?.innerHeight } : scroller?.getBoundingClientRect();
    if (rect && scroller) {
      const delta = point.y > rect.bottom - 48 ? 16 : point.y < rect.top + 48 ? -16 : 0;
      if (delta) { scroller.scrollTop += delta; position(); }
    }
    frame = win.requestAnimationFrame(scrollFrame);
  }
  function startTransfer() {
    if (gesture.moved) return;
    runtime.deps.cancelHorizontal?.(root);
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
    frame = win.requestAnimationFrame(scrollFrame);
    if (runtime.deps.dragPoint) void pollDesktop(gesture);
  }
  async function pollDesktop(active) {
    try {
      const point = await runtime.deps.dragPoint();
      if (gesture !== active || active.finishing) return;
      if (!isCurrent() || point?.escape) { cancel(); return; }
      position(point);
      if (point?.pressed === false) { await finish(point); return; }
      probeTimer = win.setTimeout(() => { void pollDesktop(active); }, 32);
    } catch (error) {
      if (gesture !== active) return;
      cancel(); runtime.deps.onError?.(root, store, error);
    }
  }
  function onDown(event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || gesture
      || ownerOf(event.target) !== ownerOf(root)) return;
    const hand = Boolean(event.target?.closest?.("[data-view-interaction-mode='hand']"));
    // Without transfer support, retain the original hand-mode-only contract.
    if (!hand && !runtime.deps.dropLocal) return;
    const context = resolveFinalPathDragSource(event.target);
    if (!context) return;
    const state = store.getState();
    if (state.assembly?.loading || state.assembly?.mainViewHistory?.inFlight || state.assembly?.sourceEditingReloadRequired) return;
    gesture = { context, scope: scopeOf(state), source: event.target.closest(SOURCE), originalTarget: event.target,
      owner: ownerOf(event.target), localContext: resolveSubviewFragmentContextTarget(event.target)
        || resolveSubviewTrackPairContextTarget(event.target), hand, pointerId: event.pointerId,
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, moved: false,
      point: { document: doc, x: event.clientX, y: event.clientY },
      generation: state.assembly?.subviewWorkspace?.generation,
      main: state.assembly.chrCtgs, support: state.assembly.supportChrCtgs,
      reference: state.assembly.refTrackMembers, summary: state.assembly.subview?.summary };
    // In mouse mode this is observational until vertical intent is established.
    // The existing horizontal controller is free to preview normally meanwhile.
    if (hand) { event.preventDefault(); event.stopImmediatePropagation(); }
    try { root.setPointerCapture?.(event.pointerId); } catch { /* synthetic pointer */ }
    win.addEventListener("pointermove", onMove, true);
    win.addEventListener("pointerup", onUp, true);
    win.addEventListener("pointercancel", cancel, true);
    win.addEventListener("keydown", onKey, true);
    win.addEventListener("blur", cancel);
  }
  function onMove(event) {
    if (!gesture || gesture.finishing || event.pointerId !== gesture.pointerId) return;
    if (!isCurrent()) { cancel(); return; }
    gesture.x = event.clientX; gesture.y = event.clientY;
    const dx = gesture.x - gesture.startX, dy = gesture.y - gesture.startY;
    if (!gesture.moved && (gesture.hand ? Math.hypot(dx, dy) < 4
      : Math.abs(dy) < 10 || Math.abs(dy) < Math.abs(dx) * 0.6)) return;
    event.preventDefault(); event.stopImmediatePropagation();
    startTransfer();
    // Native polling uses physical desktop hit testing. Never overwrite it with
    // client coordinates from a captured pointer outside its source window.
    if (!runtime.deps.dragPoint) position({ document: doc, x: gesture.x, y: gesture.y });
  }
  async function finish(point) {
    const active = gesture;
    if (!active || active.finishing) return;
    active.finishing = true;
    if (isCurrent() && active.moved) position(point);
    const valid = isCurrent(), { target, context, localContext, moved } = active;
    cancel();
    if (!valid || !moved || !target) return;
    try {
      if (target.kind === "local") await runtime.deps.dropLocal(root, store, {
        target, context, localContext, sourceWindowId: active.owner?.dataset.localViewWindow || null,
        workspaceGeneration: active.generation,
      });
      else await runtime.deps.append(root, store, context, { targetChrName: target.targetChrName });
    } catch (error) { runtime.deps.onError?.(root, store, error); }
  }
  function onUp(event) {
    if (!gesture || gesture.finishing || event.pointerId !== gesture.pointerId) return;
    if (!gesture.moved) { cancel(); return; }
    event.preventDefault(); event.stopImmediatePropagation();
    const active = gesture;
    if (runtime.deps.dragPoint) {
      // A final, fresh native hit test is required; a stale hover is not a drop.
      active.finishing = true;
      void runtime.deps.dragPoint().then(point => {
        if (gesture !== active) return;
        active.finishing = false;
        if (point?.escape) cancel(); else void finish(point);
      }, error => { if (gesture === active) { cancel(); runtime.deps.onError?.(root, store, error); } });
    } else void finish({ document: doc, x: event.clientX, y: event.clientY });
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
    try { root.releasePointerCapture?.(gesture.pointerId); } catch { /* already released */ }
    gesture = null;
    if (frame !== null) win.cancelAnimationFrame(frame);
    if (probeTimer !== null) win.clearTimeout(probeTimer);
    frame = probeTimer = null;
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
