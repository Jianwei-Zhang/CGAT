import { changeSubviewWindow, getSubviewWindowStore, installSubviewWorkspace } from "./subview-workspace-state.js";
import { renderSubviewTaskbar } from "./render-subview-workspace.js";

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
  const section = () => root.querySelector("[data-subview-workspace]");
  const windowNode = id => [...(section()?.querySelectorAll("[data-local-view-window]") || [])]
    .find(node => node.dataset.localViewWindow === id);

  function syncChrome() {
    const workspace = store.getState().assembly?.subviewWorkspace;
    if (!workspace) return;
    const labels = deps.getLabels(store.getState());
    const taskbar = section()?.querySelector(".subview-taskbar");
    if (taskbar) taskbar.outerHTML = renderSubviewTaskbar(workspace, labels, store.getState().assembly);
    for (const item of workspace.windows) {
      const node = windowNode(item.id);
      if (!node) continue;
      node.hidden = item.minimized;
      node.classList.toggle("is-floating", item.floating);
      node.classList.toggle("is-active", workspace.activeId === item.id);
      node.style.setProperty("--local-x", `${item.x}px`);
      node.style.setProperty("--local-y", `${item.y}px`);
      node.style.setProperty("--local-z", String(item.z));
      const toggle = node.querySelector('[data-local-view-action="dock"]');
      if (toggle) {
        toggle.textContent = item.floating ? labels.window.dock : labels.window.float;
        toggle.setAttribute("aria-label", toggle.textContent);
      }
    }
  }

  function activate(id) {
    if (!changeSubviewWindow(store, id, "activate")) return;
    syncChrome();
    bind();
    const node = windowNode(id);
    if (node) {
      const scoped = getSubviewWindowStore(store, id);
      if (!matches(node, scoped)) deps.refresh(node, scoped);
      deps.syncTools(node, scoped);
    }
  }

  function onAction(event) {
    const button = event.target?.closest?.("[data-local-view-action]");
    if (!button || !section()?.contains(button)) return;
    event.preventDefault();
    const id = button.dataset.localViewId;
    const action = button.dataset.localViewAction;
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
    if (action === "dock") deps.refresh(windowNode(id), getSubviewWindowStore(store, id));
  }

  function onPointerDown(event) {
    const node = event.target?.closest?.("[data-local-view-window]");
    if (!node || !section()?.contains(node)) return;
    const id = node.dataset.localViewWindow;
    if (store.getState().assembly.subviewWorkspace.activeId !== id) activate(id);
    else {
      // Tools owns a single overlay, retargeted on focus rather than duplicated.
      deps.syncTools(node, getSubviewWindowStore(store, id));
    }
    if (event.button !== 0 || !event.target.closest("[data-local-view-drag]")
      || event.target.closest("button") || !node.classList.contains("is-floating")) return;
    const rect = node.getBoundingClientRect();
    gesture = { id, node, pointerId: event.pointerId, x: event.clientX, y: event.clientY, rect };
    node.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function onMove(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const { rect, node } = gesture;
    const position = constrainLocalViewPosition(rect.left + event.clientX - gesture.x,
      rect.top + event.clientY - gesture.y, rect.width, rect.height, win.innerWidth, win.innerHeight);
    node.style.setProperty("--local-x", `${position.x}px`);
    node.style.setProperty("--local-y", `${position.y}px`);
    gesture.position = position;
  }

  function onUp(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const current = gesture;
    gesture = null;
    current.node.releasePointerCapture?.(event.pointerId);
    if (current.position) changeSubviewWindow(store, current.id, "position", current.position);
  }

  function onResize() {
    if (root.isConnected === false || store.getState().activeRoute !== "assembly") return;
    for (const item of store.getState().assembly?.subviewWorkspace?.windows || []) {
      const node = windowNode(item.id);
      if (!node || item.minimized) continue;
      const rect = node.getBoundingClientRect();
      if (item.floating) changeSubviewWindow(store, item.id, "position", constrainLocalViewPosition(
        item.x, item.y, rect.width, rect.height, win.innerWidth, win.innerHeight));
      if (!rendering) deps.refresh(node, getSubviewWindowStore(store, item.id));
    }
    syncChrome();
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
    if (rendering) return;
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
      if (root.isConnected !== false && store.getState().activeRoute === "assembly") {
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
  doc.addEventListener("pointercancel", onUp);
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
    unsubscribe?.();
    for (const id of mountedIds) deps.disposeWindow?.(id);
    mountedIds.clear();
    root.removeEventListener("click", onAction, true);
    root.removeEventListener("pointerdown", onPointerDown, true);
    root.removeEventListener("focusin", onFocus, true);
    doc.removeEventListener("pointermove", onMove);
    doc.removeEventListener("pointerup", onUp);
    doc.removeEventListener("pointercancel", onUp);
    win?.removeEventListener("resize", onResize);
    gesture = null;
  } };
}
