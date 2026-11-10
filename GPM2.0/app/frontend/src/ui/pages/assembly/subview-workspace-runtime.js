import { constrainLocalViewRect, resizeLocalViewRect, resolveLocalViewWindowGesture } from "./subview-window-geometry.js";
import { changeSubviewWindow, getSubviewWindowStore, installSubviewWorkspace } from "./subview-workspace-state.js";
import { renderSubviewTaskbar, renderSubviewDockIcon, subviewWindowDescription, subviewWindowAssembly } from "./render-subview-workspace.js";

const runtimes = new WeakMap();

export function constrainLocalViewPosition(x, y, width, height, viewportWidth, viewportHeight) {
  return { x: Math.max(0, Math.min(Number(x) || 0, Math.max(0, viewportWidth - Math.min(width, viewportWidth)))),
    y: Math.max(0, Math.min(Number(y) || 0, Math.max(0, viewportHeight - Math.min(height, viewportHeight)))) };
}

export function bindSubviewWorkspace(host, store, deps) {
  if (store.localViewRootStore || !host?.querySelector || !host.ownerDocument?.createElement) return null;
  const root = host.matches?.("#route-host") ? host : host.closest?.("#route-host") || host;
  let runtime = runtimes.get(store);
  if (!runtime || runtime.root !== root) {
    runtime?.destroy();
    runtime = createRuntime(root, store, deps);
    runtimes.set(store, runtime);
  }
  if (installSubviewWorkspace(store)) runtime.render();
  else runtime.bind();
  return runtime;
}

export function getSubviewWorkspaceRuntime(store) {
  return runtimes.get(store.localViewRootStore || store);
}

function createRuntime(root, store, deps) {
  const doc = root.ownerDocument;
  const win = doc.defaultView;
  const bound = new WeakSet();
  const mountedIds = new Set();
  const rendered = new WeakMap();
  const capture = scoped => {
    const state = scoped.getState();
    const a = state.assembly;
    return [a.subview, a.subviewTrackView, a.subviewTrackDragOffsets, a.subviewCompositionViewport,
      a.subviewHistoryByKey, a.subviewAnchorStateByKey, a.chrCtgs, a.supportChrCtgs, a.refTrackMembers, a.deletedCtgs, state.locale];
  };
  const matches = (node, scoped) => rendered.get(node)?.every((value, index) => value === capture(scoped)[index]);
  let gesture = null;
  let rendering = false;
  let destroyed = false;
  const section = () => root.querySelector("[data-subview-workspace]");
  const windowNode = id => [...(section()?.querySelectorAll("[data-local-view-window]") || [])]
    .find(node => node.dataset.localViewWindow === id);

  function syncChrome() {
    const workspace = store.getState().assembly?.subviewWorkspace;
    if (!workspace) return;
    const state = store.getState();
    const assembly = subviewWindowAssembly(state);
    const labels = deps.getLabels(state);
    const taskbar = section()?.querySelector(".subview-taskbar");
    if (taskbar) taskbar.outerHTML = renderSubviewTaskbar(workspace, labels, assembly);
    for (const item of workspace.windows) {
      const node = windowNode(item.id);
      if (!node) continue;
      node.hidden = item.minimized;
      node.classList.toggle("is-floating", item.floating);
      node.classList.toggle("is-active", workspace.activeId === item.id);
      node.style.setProperty("--local-x", `${item.x}px`);
      node.style.setProperty("--local-y", `${item.y}px`);
      node.style.setProperty("--local-z", String(item.z));
      for (const dimension of ["width", "height"]) {
        if (item[dimension] > 0) node.style.setProperty(`--local-${dimension}`, `${item[dimension]}px`);
        else node.style.removeProperty(`--local-${dimension}`);
      }
      const description = subviewWindowDescription(item, labels, assembly);
      node.setAttribute("aria-label", description.title);
      const title = node.querySelector("[data-local-view-title]");
      if (title) { title.textContent = description.title; title.setAttribute("data-app-tooltip", description.tooltip); }
      const toggle = node.querySelector('[data-local-view-action="dock"]');
      if (toggle) {
        toggle.innerHTML = renderSubviewDockIcon(item.floating);
        const action = item.floating ? labels.window.dock : labels.window.float;
        toggle.setAttribute("aria-label", action);
        toggle.setAttribute("data-app-tooltip", action);
      }
    }
  }

  function fitWindow(item, node) {
    if (!item?.floating || !node) return;
    const rect = node.getBoundingClientRect();
    changeSubviewWindow(store, item.id, "position", item.width > 0
      ? constrainLocalViewRect({ ...item, width: item.width, height: item.height || rect.height }, win.innerWidth, win.innerHeight)
      : constrainLocalViewPosition(item.x, item.y, rect.width, rect.height, win.innerWidth, win.innerHeight));
  }

  function activate(id) {
    const wasMinimized = store.getState().assembly?.subviewWorkspace?.windows.find(item => item.id === id)?.minimized;
    if (!changeSubviewWindow(store, id, "activate")) return;
    syncChrome();
    bind();
    const node = windowNode(id);
    if (node) {
      fitWindow(store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id), node);
      syncChrome();
      const scoped = getSubviewWindowStore(store, id);
      if (wasMinimized || !matches(node, scoped)) deps.refresh(node, scoped);
      deps.syncTools(node, scoped);
    }
  }

  function onAction(event) {
    const button = event.target?.closest?.("[data-local-view-action]");
    if (!button || !section()?.contains(button)) return;
    event.preventDefault();
    const id = button.dataset.localViewId;
    const action = button.dataset.localViewAction;
    if (gesture && action !== "activate") finishGesture(false);
    if (action === "activate") {
      activate(id);
      windowNode(id)?.querySelector("[data-local-view-action]")?.focus?.({ preventScroll: true });
      return;
    }
    if (!changeSubviewWindow(store, id, action)) return;
    if (action === "close") {
      deps.disposeWindow?.(id);
      mountedIds.delete(id);
      windowNode(id)?.remove();
      if (!store.getState().assembly.subviewWorkspace.windows.length) {
        render(); section()?.querySelector(".subview-guide-tools")?.focus?.({ preventScroll: true }); return;
      }
    }
    syncChrome();
    if (action === "minimize" || action === "close") {
      deps.closeTools();
      const focus = section()?.querySelector(`[data-subview-task="${id}"] [data-local-view-action="activate"]`)
        || section()?.querySelector(".subview-task [data-local-view-action=activate]");
      focus?.focus?.({ preventScroll: true });
    }
    if (action === "dock") {
      fitWindow(store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id), windowNode(id));
      syncChrome();
      deps.refresh(windowNode(id), getSubviewWindowStore(store, id));
    }
  }

  function onPointerDown(event) {
    let node = event.target?.closest?.("[data-local-view-window]");
    if (!node || !section()?.contains(node)) return;
    const id = node.dataset.localViewWindow;
    const workspace = store.getState().assembly?.subviewWorkspace;
    if (!workspace?.windows.some(item => item.id === id)) return;
    const kind = resolveLocalViewWindowGesture(event.target);
    if (workspace.activeId !== id) {
      activate(id);
      node = windowNode(id);
    } else {
      // Tools owns a single overlay, retargeted on focus rather than duplicated.
      deps.syncTools(node, getSubviewWindowStore(store, id));
    }
    if (gesture || event.defaultPrevented || event.button !== 0 || !kind || !node?.classList.contains("is-floating")) return;
    const rect = node.getBoundingClientRect();
    gesture = { id, node, kind, pointerId: event.pointerId, x: event.clientX, y: event.clientY, rect };
    try { node.setPointerCapture?.(event.pointerId); } catch { /* synthetic pointer or removed node */ }
    event.preventDefault();
    event.stopPropagation();
  }

  function gestureCurrent() {
    const item = store.getState().assembly?.subviewWorkspace?.windows.find(item => item.id === gesture?.id);
    return Boolean(item?.floating && !item.minimized && windowNode(item.id) === gesture.node
      && root.isConnected !== false && store.getState().activeRoute === "assembly");
  }

  function onMove(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (!gestureCurrent()) { finishGesture(false); return; }
    const { rect, node, kind } = gesture;
    const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
    const position = kind === "move"
      ? constrainLocalViewPosition(rect.left + dx, rect.top + dy, rect.width, rect.height, win.innerWidth, win.innerHeight)
      : resizeLocalViewRect(rect, kind, dx, dy, win.innerWidth, win.innerHeight);
    for (const [key, value] of Object.entries(position)) node.style.setProperty(`--local-${key}`, `${value}px`);
    gesture.position = position;
    event.preventDefault();
  }

  function finishGesture(commit) {
    if (!gesture) return;
    const current = gesture;
    const valid = gestureCurrent();
    gesture = null;
    try { current.node.releasePointerCapture?.(current.pointerId); } catch { /* already released */ }
    if (commit && valid && current.position) {
      changeSubviewWindow(store, current.id, "position", current.position);
      // Commit once, then remeasure only this graph. Pointer moves do not rebuild
      // dense evidence; existing viewport binding preserves its genomic range.
      if (current.kind !== "move") deps.refresh(current.node, getSubviewWindowStore(store, current.id));
    }
    syncChrome();
  }

  function onUp(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    finishGesture(true);
  }
  function onCancel(event) {
    if (gesture && (event?.pointerId == null || event.pointerId === gesture.pointerId)) finishGesture(false);
  }
  function onKey(event) {
    if (gesture && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finishGesture(false); }
  }

  function onResize() {
    if (gesture) finishGesture(false);
    if (root.isConnected === false || store.getState().activeRoute !== "assembly") return;
    const visible = (store.getState().assembly?.subviewWorkspace?.windows || [])
      .map(item => ({ item, node: windowNode(item.id) })).filter(({ item, node }) => node && !item.minimized);
    for (const { item, node } of visible) fitWindow(item, node);
    // Apply all clamped dimensions before measuring/rendering individual graphs.
    syncChrome();
    if (!rendering) for (const { item, node } of visible) deps.refresh(node, getSubviewWindowStore(store, item.id));
  }

  function bind() {
    const available = new Set(store.getState().assembly?.subviewWorkspace?.windows.map(item => item.id) || []);
    for (const id of mountedIds) {
      if (available.has(id)) continue;
      deps.disposeWindow?.(id); mountedIds.delete(id);
    }
    for (const node of section()?.querySelectorAll("[data-local-view-window]") || []) {
      if (bound.has(node) || node.hidden) continue;
      bound.add(node);
      mountedIds.add(node.dataset.localViewWindow);
      const scoped = getSubviewWindowStore(store, node.dataset.localViewWindow);
      deps.bindWindow(node, scoped);
      rendered.set(node, capture(scoped));
      // Main's delegated handlers must not handle a window action a second time.
      for (const type of ["click", "dblclick", "contextmenu", "pointerdown", "keydown"])
        node.addEventListener(type, event => event.stopPropagation());
    }
    const workspace = store.getState().assembly?.subviewWorkspace;
    if (!workspace?.windows.length) deps.syncTools(section() || root, store);
    syncChrome();
  }

  function render() {
    if (rendering || destroyed) return;
    const current = section();
    if (!current) return;
    rendering = true;
    try {
      const template = doc.createElement("template");
      template.innerHTML = deps.render(store.getState());
      const next = template.content.firstElementChild;
      // Keep existing windows and their bound interaction/scroll state when a
      // second comparison is created. Only new windows need graph mounting.
      for (const node of next.querySelectorAll("[data-local-view-window]")) {
        const existing = windowNode(node.dataset.localViewWindow);
        if (existing && matches(existing, getSubviewWindowStore(store, node.dataset.localViewWindow))) node.replaceWith(existing);
      }
      current.replaceWith(next);
      bind();
      onResize();
    } finally { rendering = false; }
  }

  let lastShared = [];
  let queued = false;
  let evidenceDirty = false;
  const unsubscribe = store.subscribe?.(state => {
    const next = [state.assembly?.chrCtgs, state.assembly?.deletedCtgs, state.assembly?.supportChrCtgs,
      state.assembly?.refTrackMembers, state.assembly?.selectedChrName, state.locale];
    const changed = lastShared.length && next.some((value, index) => value !== lastShared[index]);
    evidenceDirty ||= Boolean(lastShared.length && next.slice(0, 5).some((value, index) => value !== lastShared[index]));
    lastShared = next;
    if (!changed || queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      if (!destroyed && root.isConnected !== false && store.getState().activeRoute === "assembly") {
        render();
        if (evidenceDirty) {
          evidenceDirty = false;
          for (const item of store.getState().assembly?.subviewWorkspace?.windows || []) {
            void deps.refreshEvidence?.(windowNode(item.id) || root, getSubviewWindowStore(store, item.id));
          }
        }
      }
    });
  });
  root.addEventListener("click", onAction, true);
  root.addEventListener("pointerdown", onPointerDown, true);
  root.addEventListener("focusin", onFocus, true);
  doc.addEventListener("pointermove", onMove);
  doc.addEventListener("pointerup", onUp);
  doc.addEventListener("pointercancel", onCancel);
  root.addEventListener("lostpointercapture", onCancel, true);
  doc.addEventListener("keydown", onKey, true);
  win?.addEventListener("blur", onCancel);
  win?.addEventListener("resize", onResize);
  function onFocus(event) {
    const node = event.target?.closest?.("[data-local-view-window]");
    if (node && store.getState().assembly?.subviewWorkspace?.activeId !== node.dataset.localViewWindow)
      activate(node.dataset.localViewWindow);
  }
  return { root, render, bind, syncChrome, windowNode,
    markRendered(id) {
      const node = windowNode(id);
      if (node) rendered.set(node, capture(getSubviewWindowStore(store, id)));
    }, destroy() {
    destroyed = true;
    finishGesture(false);
    unsubscribe?.();
    for (const id of mountedIds) deps.disposeWindow?.(id);
    mountedIds.clear();
    root.removeEventListener("click", onAction, true);
    root.removeEventListener("pointerdown", onPointerDown, true);
    root.removeEventListener("focusin", onFocus, true);
    doc.removeEventListener("pointermove", onMove);
    doc.removeEventListener("pointerup", onUp);
    doc.removeEventListener("pointercancel", onCancel);
    root.removeEventListener("lostpointercapture", onCancel, true);
    doc.removeEventListener("keydown", onKey, true);
    win?.removeEventListener("blur", onCancel);
    win?.removeEventListener("resize", onResize);
    gesture = null;
  } };
}
