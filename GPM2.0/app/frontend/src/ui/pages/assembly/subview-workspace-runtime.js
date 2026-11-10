import { createNativeSubviewWindows } from "./subview-native-windows.js";
import { requestAppPrompt } from "../../shell/app-dialog.js";
import { constrainLocalViewRect, resizeLocalViewRect, resolveLocalViewWindowGesture } from "./subview-window-geometry.js";
import { changeSubviewWindow, getSubviewWindowStore, installSubviewWorkspace } from "./subview-workspace-state.js";
import { renderSubviewTaskbar, renderSubviewTaskStatus, subviewTaskMenuItems, renderSubviewDockIcon, subviewWindowDescription, subviewWindowAssembly } from "./render-subview-workspace.js";

const runtimes = new WeakMap();

export function constrainLocalViewPosition(x, y, width, height, viewportWidth, viewportHeight) {
  return { x: Math.max(0, Math.min(Number(x) || 0, Math.max(0, viewportWidth - Math.min(width, viewportWidth)))),
    y: Math.max(0, Math.min(Number(y) || 0, Math.max(0, viewportHeight - Math.min(height, viewportHeight)))) };
}

export function bindSubviewWorkspace(host, store, deps) {
  if (store.localViewRootStore || !host?.querySelector || !host.ownerDocument?.createElement) return null;
  const root = host.matches?.("#route-host") ? host : host.closest?.("#route-host") || host;
  const usedNative = Boolean(store.getState().assembly?.subviewNativeWindows);
  if (root.ownerDocument.defaultView?.__GPM_NATIVE_LOCAL_VIEWS__ && !usedNative) {
    store.setState({ assembly: { ...store.getState().assembly, subviewNativeWindows: true } });
  }
  let runtime = runtimes.get(store);
  if (!runtime || runtime.root !== root) {
    runtime?.destroy();
    runtime = createRuntime(root, store, deps);
    runtimes.set(store, runtime);
  }
  if (installSubviewWorkspace(store) || usedNative !== Boolean(store.getState().assembly?.subviewNativeWindows)) runtime.render();
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
  let native = null;
  let gesture = null;
  let taskDrag = null;
  let suppressTaskClickUntil = 0, suppressTaskClickId = null;
  let menu = null;
  let rendering = false;
  let destroyed = false;
  const section = () => root.querySelector("[data-subview-workspace]");
  const windowNode = id => [...(section()?.querySelectorAll("[data-local-view-window]") || [])]
    .find(node => node.dataset.localViewWindow === id) || native?.node(id);

  function syncChrome() {
    const workspace = store.getState().assembly?.subviewWorkspace;
    if (!workspace) return;
    const state = store.getState();
    const assembly = subviewWindowAssembly(state);
    const labels = deps.getLabels(state);
    const status = section()?.querySelector("[data-local-view-task-status]");
    if (status) status.outerHTML = renderSubviewTaskStatus(assembly, labels);
    const taskbar = section()?.querySelector(".subview-taskbar");
    if (taskbar) taskbar.outerHTML = renderSubviewTaskbar(workspace, labels, assembly);
    for (const item of workspace.windows) {
      const node = windowNode(item.id);
      if (!node || node.ownerDocument !== doc) continue;
      node.hidden = item.minimized || item.opened === false;
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
    if (!item?.floating || !node || node.ownerDocument !== doc) return;
    const rect = node.getBoundingClientRect();
    changeSubviewWindow(store, item.id, "position", item.width > 0
      ? constrainLocalViewRect({ ...item, width: item.width, height: item.height || rect.height }, win.innerWidth, win.innerHeight)
      : constrainLocalViewPosition(item.x, item.y, rect.width, rect.height, win.innerWidth, win.innerHeight));
  }

  function activate(id) {
    const target = store.getState().assembly?.subviewWorkspace?.windows.find(item => item.id === id);
    const wasMinimized = target?.minimized || target?.opened === false;
    if (!changeSubviewWindow(store, id, "activate")) return;
    syncChrome();
    bind();
    native?.focus(id);
    const node = windowNode(id);
    if (node) {
      fitWindow(store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id), node);
      syncChrome();
      const scoped = getSubviewWindowStore(store, id);
      if (wasMinimized || !matches(node, scoped)) deps.refresh(node, scoped);
      if (!scoped.getState().assembly?.subview?.pairwiseEvidence) void (deps.restoreEvidence || deps.refreshEvidence)?.(node, scoped);
      deps.syncTools(node, scoped);
    }
  }

  function closeMenu(restoreFocus = false) {
    const id = menu?.dataset.localViewId;
    menu?.remove(); menu = null;
    if (restoreFocus && id) section()?.querySelector(`[data-subview-task="${id}"] [data-local-view-action="activate"]`)?.focus();
  }
  async function editMetadata(id, action) {
    const ws = store.getState().assembly.subviewWorkspace;
    const item = ws.windows.find(item => item.id === id);
    if (!item) return;
    const labels = deps.getLabels(store.getState()).window;
    const value = await requestAppPrompt(action === "rename" ? labels.renameHint : labels.noteHint,
      action === "rename" ? item.name || "" : item.note || "", {
        locale: store.getState().locale, title: action === "rename" ? labels.rename : labels.note,
        multiline: action === "note", maxLength: action === "rename" ? 80 : 4000,
      });
    if (destroyed || value === null || store.getState().assembly?.subviewWorkspace?.generation !== ws.generation) return;
    changeSubviewWindow(store, id, "metadata", { [action === "rename" ? "name" : "note"]: value });
    syncChrome();
    section()?.querySelector(`[data-subview-task="${id}"] [data-local-view-action="activate"]`)?.focus?.({ preventScroll: true });
  }
  function currentActionOwner(node) {
    const generation = node?.closest?.("[data-local-view-generation]")?.dataset?.localViewGeneration;
    return generation == null || Number(generation) === store.getState().assembly?.subviewWorkspace?.generation;
  }
  function onAction(event) {
    const button = event.target?.closest?.("[data-local-view-action]");
    if (!button || (!section()?.contains(button) && !menu?.contains(button)) || !currentActionOwner(button)) return;
    event.preventDefault();
    event.stopPropagation();
    closeMenu(true);
    const id = button.dataset.localViewId;
    const action = button.dataset.localViewAction;
    if (action === "activate" && id === suppressTaskClickId && Date.now() < suppressTaskClickUntil) return;
    if (action === "retry-save") { void deps.retryPersistence?.().catch(() => {}).finally(syncChrome); return; }
    if (gesture && action !== "activate") finishGesture(false);
    if (action === "rename" || action === "note") { void editMetadata(id, action); return; }
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
    if (["dock", "open-docked", "open-floating"].includes(action)) {
      // A native dock may need its formerly external DOM mounted in Main.
      if (native) render();
      bind();
      native?.focus(id);
      fitWindow(store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id), windowNode(id));
      syncChrome();
      if (windowNode(id)) deps.refresh(windowNode(id), getSubviewWindowStore(store, id));
      if (windowNode(id) && !getSubviewWindowStore(store, id).getState().assembly?.subview?.pairwiseEvidence)
        void (deps.restoreEvidence || deps.refreshEvidence)?.(windowNode(id), getSubviewWindowStore(store, id));
    }
  }

  function onPointerDown(event) {
    if (startTaskDrag(event)) return;
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
    return Boolean(item?.floating && item.opened !== false && !item.minimized && windowNode(item.id) === gesture.node
      && root.isConnected !== false && store.getState().activeRoute === "assembly");
  }

  function onMove(event) {
    if (moveTaskDrag(event)) return;
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
    if (taskDrag?.pointerId === event.pointerId) { finishTaskDrag(true); return; }
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    finishGesture(true);
  }
  function onCancel(event) {
    if (taskDrag && (event?.pointerId == null || event.pointerId === taskDrag.pointerId)) finishTaskDrag(false);
    if (gesture && (event?.pointerId == null || event.pointerId === gesture.pointerId)) finishGesture(false);
  }
  function onKey(event) {
    if (taskDrag && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finishTaskDrag(false); return; }
    if (event.key === "Tab" && menu) closeMenu(true);
    if (event.key === "Escape" && menu) { event.preventDefault(); event.stopPropagation(); closeMenu(true); return; }
    const task = event.target?.closest?.("[data-subview-task]");
    if (task && event.altKey && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      const ws = store.getState().assembly.subviewWorkspace;
      const index = ws.windows.findIndex(item => item.id === task.dataset.subviewTask);
      const adjacent = ws.windows[index + (event.key === "ArrowLeft" ? -1 : 1)];
      if (adjacent) {
        event.preventDefault(); event.stopPropagation();
        changeSubviewWindow(store, task.dataset.subviewTask, "reorder", { beforeId: adjacent.id });
        syncChrome();
        section()?.querySelector(`[data-subview-task="${task.dataset.subviewTask}"] button`)?.focus();
      }
    }
    if (gesture && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finishGesture(false); }
  }

  function onResize() {
    if (gesture) finishGesture(false);
    if (root.isConnected === false || store.getState().activeRoute !== "assembly") return;
    const visible = (store.getState().assembly?.subviewWorkspace?.windows || [])
      .map(item => ({ item, node: windowNode(item.id) })).filter(({ item, node }) => node && node.ownerDocument === doc && !item.minimized && item.opened !== false);
    for (const { item, node } of visible) fitWindow(item, node);
    // Apply all clamped dimensions before measuring/rendering individual graphs.
    syncChrome();
    if (!rendering) for (const { item, node } of visible) deps.refresh(node, getSubviewWindowStore(store, item.id));
  }

  function bind() {
    syncChrome();
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
  let nativeSharedDirty = false;
  const unsubscribe = store.subscribe?.(state => {
    const ws = state.assembly?.subviewWorkspace;
    if (menu && Number(menu.dataset.localViewGeneration) !== ws?.generation) closeMenu();
    const next = [state.assembly?.chrCtgs, state.assembly?.deletedCtgs, state.assembly?.supportChrCtgs,
      state.assembly?.refTrackMembers, state.assembly?.selectedChrName, state.locale,
      `${ws?.generation}:${ws?.windows.map(item => `${item.id}:${item.floating}`).join(",")}`, state.assembly?.localViewTaskSaveError, state.assembly?.subviewNativeError];
    const changed = lastShared.length && next.some((value, index) => value !== lastShared[index]);
    nativeSharedDirty ||= Boolean(lastShared.length && next.slice(0, 6).some((value, index) => value !== lastShared[index]));
    evidenceDirty ||= Boolean(lastShared.length && next.slice(0, 5).some((value, index) => value !== lastShared[index]));
    lastShared = next;
    if (!changed || queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      if (!destroyed && root.isConnected !== false && store.getState().activeRoute === "assembly") {
        render();
        if (nativeSharedDirty) { nativeSharedDirty = false; native?.refresh(); }
        if (evidenceDirty) {
          evidenceDirty = false;
          for (const item of store.getState().assembly?.subviewWorkspace?.windows || []) {
            if (item.opened === false || item.minimized) continue;
            void deps.refreshEvidence?.(windowNode(item.id) || root, getSubviewWindowStore(store, item.id));
          }
        }
      }
    });
  });
  function onContextMenu(event) {
    const task = event.target?.closest?.("[data-subview-task]");
    if (!task || !section()?.contains(task) || !currentActionOwner(task)) return;
    event.preventDefault(); event.stopPropagation(); closeMenu();
    const id = task.dataset.subviewTask;
    const item = store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id);
    if (!item) return;
    menu = doc.createElement("div"); menu.className = "context-menu subview-task-menu"; menu.setAttribute("role", "menu");
    menu.dataset.localViewId = id;
    menu.dataset.localViewGeneration = String(store.getState().assembly.subviewWorkspace.generation);
    menu.setAttribute("aria-label", subviewWindowDescription(item, deps.getLabels(store.getState())).title);
    let group;
    for (const entry of subviewTaskMenuItems(item, deps.getLabels(store.getState()))) {
      if (group && group !== entry.group) {
        const separator = doc.createElement("div");
        separator.className = "subview-task-menu-separator"; separator.setAttribute("role", "separator");
        menu.append(separator);
      }
      group = entry.group;
      const button = doc.createElement("button"); button.type = "button";
      button.className = `context-menu-item${entry.danger ? " is-danger" : ""}`;
      button.setAttribute("role", entry.checked === undefined ? "menuitem" : "menuitemradio");
      if (entry.checked !== undefined) button.setAttribute("aria-checked", String(Boolean(entry.checked)));
      button.dataset.localViewAction = entry.action;
      button.dataset.localViewId = id; button.disabled = Boolean(entry.disabled);
      const mark = doc.createElement("span"); mark.className = "subview-task-menu-mark";
      mark.setAttribute("aria-hidden", "true"); mark.textContent = entry.checked ? "✓" : "";
      const caption = doc.createElement("span"); caption.textContent = entry.label;
      button.append(mark, caption);
      menu.append(button);
    }
    menu.addEventListener("click", onAction);
    menu.addEventListener("keydown", event => {
      if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...menu.querySelectorAll("button:not(:disabled)")];
      const index = buttons.indexOf(doc.activeElement);
      buttons[event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
        : (index + (event.key === "ArrowUp" ? -1 : 1) + buttons.length) % buttons.length]?.focus();
    });
    doc.body.append(menu);
    const rect = task.getBoundingClientRect();
    menu.style.left = `${Math.max(0, Math.min(event.clientX || rect.left, win.innerWidth - menu.offsetWidth))}px`;
    menu.style.top = `${Math.max(0, Math.min(event.clientY || rect.bottom, win.innerHeight - menu.offsetHeight))}px`;
    menu.querySelector("button")?.focus();
  }
  function dismissMenu(event) { if (menu && !menu.contains(event.target)) closeMenu(); }
  function startTaskDrag(event) {
    const task = event.target?.closest?.("[data-subview-task]");
    if (!task || !section()?.contains(task) || !currentActionOwner(task) || event.button !== 0
      || event.target?.closest?.('[data-local-view-action="close"]')) return false;
    taskDrag = { id: task.dataset.subviewTask, generation: store.getState().assembly.subviewWorkspace.generation,
      node: task, captureNode: event.target?.closest?.("[data-local-view-action=activate]") || task, pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false, targetId: null };
    // Pointer reordering works with Tauri's native file-drop handler enabled;
    // HTML drag/drop would require disabling the App's project-drop support.
    try { taskDrag.captureNode.setPointerCapture?.(event.pointerId); } catch { /* synthetic test */ }
    closeMenu();
    return true;
  }
  function clearTaskDrag() {
    if (!taskDrag) return;
    const { pointerId, captureNode } = taskDrag;
    taskDrag = null;
    try { captureNode.releasePointerCapture?.(pointerId); } catch { /* already released */ }
    section()?.querySelectorAll(".is-drag-target").forEach(node => node.classList.remove("is-drag-target"));
  }
  function moveTaskDrag(event) {
    if (!taskDrag || event.pointerId !== taskDrag.pointerId) return false;
    if (taskDrag.generation !== store.getState().assembly?.subviewWorkspace?.generation) { clearTaskDrag(); return true; }
    if (!taskDrag.moved && Math.hypot(event.clientX - taskDrag.x, event.clientY - taskDrag.y) < 4) return true;
    taskDrag.moved = true;
    event.preventDefault();
    const bar = section()?.querySelector(".subview-taskbar"), rect = bar?.getBoundingClientRect();
    if (rect) bar.scrollLeft += event.clientX < rect.left + 24 ? -16 : event.clientX > rect.right - 24 ? 16 : 0;
    const target = doc.elementFromPoint?.(event.clientX, event.clientY)?.closest?.("[data-subview-task]");
    taskDrag.targetId = target && section()?.contains(target) ? target.dataset.subviewTask : null;
    section()?.querySelectorAll(".is-drag-target").forEach(node => node.classList.remove("is-drag-target"));
    if (taskDrag.targetId) target.classList.add("is-drag-target");
    return true;
  }
  function finishTaskDrag(commit) {
    const drag = taskDrag;
    if (!drag) return;
    clearTaskDrag();
    if (!drag.moved) return;
    suppressTaskClickUntil = Date.now() + 300; suppressTaskClickId = drag.id;
    if (commit && drag.moved && drag.generation === store.getState().assembly?.subviewWorkspace?.generation
      && drag.targetId) changeSubviewWindow(store, drag.id, "reorder", { beforeId: drag.targetId });
    syncChrome();
  }
  native = createNativeSubviewWindows(root, store, { ...deps, onNativeMount: (node, scoped) => rendered.set(node, capture(scoped)) });
  root.addEventListener("contextmenu", onContextMenu, true);
  doc.addEventListener("pointerdown", dismissMenu, true);
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
    native?.destroy();
    closeMenu(); clearTaskDrag();
    root.removeEventListener("contextmenu", onContextMenu, true);
    doc.removeEventListener("pointerdown", dismissMenu, true);
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
