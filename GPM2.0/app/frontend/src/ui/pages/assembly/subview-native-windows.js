import { fitNativeSubviewWindow } from "./subview-native-fit.js";
import { changeSubviewWindow, getSubviewWindowStore } from "./subview-workspace-state.js";
import { renderSubviewDockIcon, syncSubviewPinButton, subviewWindowAssembly, subviewWindowDescription } from "./render-subview-workspace.js";
import { LOCAL_VIEW_RESIZE_EDGES, resolveLocalViewWindowGesture } from "./subview-window-geometry.js";
import { bindAppTooltips } from "../../app-tooltip-runtime.js";

const DIRECTIONS = { n: "North", s: "South", e: "East", w: "West", ne: "NorthEast", nw: "NorthWest", se: "SouthEast", sw: "SouthWest" };
const managers = new WeakMap();
export function getNativeSubviewManager(store) { return managers.get(store.localViewRootStore || store); }

// window.open + Tauri's on_new_window/window_features preserves the same-origin
// opener context. Controllers and scoped stores stay in Main: no copied project
// store, competing persistence writer, or optimistic cross-window merge exists.
export function createNativeSubviewWindows(root, store, deps) {
  const win = root.ownerDocument?.defaultView;
  if (!win?.__GPM_NATIVE_LOCAL_VIEWS__) return null;
  const entries = new Map(), closing = new Map();
  let focusSequence = 0, focusTarget = null;
  let destroyed = false, syncing = false, unlistenDestroyed;
  const mainHandle = win.__TAURI__.window.getCurrentWindow();
  const itemFor = id => store.getState().assembly?.subviewWorkspace?.windows.find(item => item.id === id);
  const valid = entry => !destroyed && entries.get(entry.id) === entry && !entry.closing
    && store.getState().assembly?.subviewWorkspace?.generation === entry.generation;
  function report(error) {
    const state = store.getState();
    store.setState({ assembly: { ...state.assembly, subviewNativeError: String(error?.message || error) } });
  }
  function run(promise, entry = null) { return Promise.resolve(promise).catch(error => { if (!destroyed && (!entry || valid(entry))) report(error); }); }
  function close(entry, alreadyDestroyed = false) {
    if (entry.closing) return;
    entry.closing = true; entries.delete(entry.id); clearTimeout(entry.timeout);
    if (entry.node) entry.node.inert = true;
    entry.tooltips?.destroy();
    for (const dispose of entry.cleanups) { try { Promise.resolve(dispose?.()).catch(() => {}); } catch { /* destroyed peer */ } }
    deps.disposeWindow?.(entry.id);
    // Docking waits for the old OS window's destruction before focusing Main;
    // otherwise Windows can reactivate a sibling after Main was brought forward.
    if (alreadyDestroyed) { entry.removeGuard?.(); return Promise.resolve(); }
    let done, fallback;
    const promise = new Promise(resolve => { done = () => {
      clearTimeout(fallback); closing.delete(entry.token); entry.removeGuard?.(); resolve();
    }; });
    closing.set(entry.token, { id: entry.id, promise, done });
    void (async () => {
      try {
        const handle = entry.handle || await win.__TAURI__.webviewWindow.WebviewWindow.getByLabel(`local-view-${entry.id}--${entry.token}`);
        if (!handle) { done(); return; }
        if (itemFor(entry.id) && store.getState().assembly?.subviewWorkspace?.generation === entry.generation) {
          try {
            // Windows may report iconic coordinates (-32000, -32000) while
            // minimized. Never restore those as a real desktop placement.
            if (!await handle.isMinimized()) {
              const [position, size] = await Promise.all([handle.outerPosition(), handle.innerSize()]);
              if (itemFor(entry.id) && store.getState().assembly?.subviewWorkspace?.generation === entry.generation)
                changeSubviewWindow(store, entry.id, "native-geometry", { nativeBounds: { x: position.x, y: position.y, width: size.width, height: size.height } });
            }
          } catch { /* A window already destroyed by the OS has no bounds to retain. */ }
        }
        await handle.destroy();
        if (closing.has(entry.token)) fallback = setTimeout(done, 500);
      } catch (error) { const pending = closing.has(entry.token); done(); if (!destroyed && pending) report(error); }
    })();
    return promise;
  }

  function fail(entry, error) {
    if (!valid(entry)) return;
    close(entry);
    changeSubviewWindow(store, entry.id, "open-docked");
    report(error);
  }
  async function syncPin(entry) {
    if (!valid(entry) || !entry.handle || entry.pinPending) return;
    entry.pinPending = true;
    try {
      // Serialize native updates and coalesce rapid pin/unpin clicks. Never
      // recreate a dense graph, duplicate its store, or steal Main's focus.
      while (valid(entry) && entry.nativePinned !== (itemFor(entry.id)?.pinned !== false)) {
        const requested = itemFor(entry.id).pinned !== false;
        try {
          await win.__TAURI__.core.invoke("set_local_view_pinned", { label: entry.handle.label, pinned: requested });
        } catch (error) {
          if (valid(entry)) {
            if ((itemFor(entry.id)?.pinned !== false) === requested)
              changeSubviewWindow(store, entry.id, "pin", { pinned: entry.nativePinned });
            report(error);
          }
          return;
        }
        if (!valid(entry)) return;
        entry.nativePinned = requested;
      }
    } finally { entry.pinPending = false; }
  }
  function chrome(entry, item) {
    if (!entry.node || !valid(entry)) return;
    const state = store.getState(), labels = deps.getLabels(state);
    const description = subviewWindowDescription(item, labels, subviewWindowAssembly(state));
    if (entry.nativeTitle !== description.title) { entry.nativeTitle = description.title; run(entry.handle.setTitle(description.title), entry); }
    syncSubviewPinButton(entry.node, item, labels);
    void syncPin(entry);
    entry.node.setAttribute("role", "region");
    entry.node.setAttribute("aria-label", description.title);
    const title = entry.node.querySelector("[data-local-view-title]");
    if (title) { title.textContent = description.title; title.setAttribute("data-app-tooltip", description.tooltip); }
    const toggle = entry.node.querySelector('[data-local-view-action="dock"]');
    if (toggle) {
      toggle.innerHTML = renderSubviewDockIcon(true);
      toggle.setAttribute("aria-label", labels.window.dock); toggle.setAttribute("data-app-tooltip", labels.window.dock);
    }
    entry.win.document.documentElement.dataset.theme = root.ownerDocument.documentElement.dataset.theme || "light";
    entry.win.document.documentElement.lang = state.locale || "zh";
    for (const name of ["--app-font-size", "--graph-font-size"]) {
      const value = root.ownerDocument.documentElement.style.getPropertyValue(name);
      if (value) entry.win.document.documentElement.style.setProperty(name, value);
    }
    if (entry.minimized !== Boolean(item.minimized)) {
      entry.minimized = Boolean(item.minimized);
      run(entry.minimized ? entry.handle.minimize() : entry.handle.unminimize(), entry);
    }
  }
  async function connect(id, token, peer) {
    const entry = entries.get(id);
    if (!entry || entry.token !== token || !valid(entry) || entry.win
      || peer.opener !== win || peer.location.origin !== win.location.origin) throw new Error("Local View owner expired");
    entry.win = peer;
    entry.handle = peer.__TAURI__.window.getCurrentWindow();
    // OS destruction is asynchronous. Keep a capture-phase gate until it really
    // completes, so a closing/docked/stale peer cannot edit a new project via
    // old DOM handlers while the authoritative store has already moved on.
    const guarded = ["pointerdown", "pointermove", "pointerup", "click", "dblclick", "contextmenu", "keydown", "input", "change"];
    const guard = event => { if (!valid(entry)) { event.preventDefault(); event.stopImmediatePropagation(); } };
    guarded.forEach(type => peer.addEventListener(type, guard, true));
    entry.removeGuard = () => { try { guarded.forEach(type => peer.removeEventListener(type, guard, true)); } catch { /* closed browsing context */ } };
    entry.scoped = getSubviewWindowStore(store, id);
    const doc = peer.document, host = doc.querySelector("#route-host");
    host.innerHTML = `<section data-subview-workspace="1"><section id="${id}" data-local-view-window="${id}" class="subview-window is-native">
      <div data-local-view-context-menu class="context-menu is-hidden"></div><div class="subview-window-content">${deps.render(entry.scoped.getState())}</div>
      ${LOCAL_VIEW_RESIZE_EDGES.map(edge => `<div class="subview-window-resize" data-local-view-resize="${edge}" aria-hidden="true"></div>`).join("")}</section></section>`;
    entry.node = host.querySelector("[data-local-view-window]");
    entry.autoSize = !itemFor(id)?.nativeBounds;
    const fitContent = async () => {
      entry.fitting = true;
      try {
        const fit = await fitNativeSubviewWindow(entry.node, entry.handle, () => valid(entry) && entry.autoSize);
        if (fit) entry.autoFitSize = fit;
      } finally { entry.fitting = false; }
    };
    const listen = (node, type, callback, capture = false) => {
      node.addEventListener(type, callback, capture); entry.cleanups.push(() => node.removeEventListener(type, callback, capture));
    };
    listen(host, "click", event => {
      const button = event.target?.closest?.("[data-local-view-action]");
      if (!button || !valid(entry)) return;
      event.preventDefault(); event.stopPropagation();
      const action = button.dataset.localViewAction;
      if (action === "dock") { changeSubviewWindow(store, id, "open-docked"); void manager.focus(id); }
      else if (action === "close" || action === "minimize" || action === "pin") changeSubviewWindow(store, id, action);
    }, true);
    listen(host, "pointerdown", event => {
      if (!valid(entry)) return;
      // Explicit peer input wins over a still-pending programmatic focus request.
      focusSequence++; focusTarget = null;
      if (store.getState().assembly.subviewWorkspace.activeId !== id) changeSubviewWindow(store, id, "activate");
      deps.syncTools(entry.node, entry.scoped);
      if (event.button !== 0 || event.defaultPrevented) return;
      const kind = resolveLocalViewWindowGesture(event.target);
      if (!kind) return;
      event.preventDefault(); event.stopPropagation();
      // Once the user resizes, late evidence restoration must not refit it.
      if (kind !== "move") entry.autoSize = false;
      run(kind === "move" ? entry.handle.startDragging() : entry.handle.startResizeDragging(DIRECTIONS[kind]), entry);
    }, true);
    entry.cleanups.push(await entry.handle.onCloseRequested(event => {
      event.preventDefault();
      if (valid(entry)) changeSubviewWindow(store, id, "close");
    }));
    entry.cleanups.push(await entry.handle.onFocusChanged(({ payload }) => {
      if (!payload || !entry.ready || !valid(entry) || (focusTarget && focusTarget !== id)) return;
      run(entry.handle.isFocused().then(focused => {
        if (focused && valid(entry) && (!focusTarget || focusTarget === id)) {
          changeSubviewWindow(store, id, "activate");
          deps.syncTools(entry.node, entry.scoped);
        }
      }), entry);
    }));
    let resizeTimer;
    entry.cleanups.push(await entry.handle.onResized(({ payload }) => {
      if (!valid(entry)) return;
      // Also recognize OS-level resize/snap, not only our border handles. A
      // delayed event for our own fit must not be mistaken for user geometry.
      if (entry.ready && entry.autoSize && !entry.fitting && !itemFor(id)?.minimized
        && payload?.width > 0 && payload?.height > 0
        && (payload.width !== entry.autoFitSize?.width || payload.height !== entry.autoFitSize?.height))
        entry.autoSize = false;
      peer.clearTimeout(resizeTimer);
      // Let the OS resize the surface live; rebuild dense genomic geometry only
      // after resizing settles, not once per native resize event.
      resizeTimer = peer.setTimeout(() => {
        resizeTimer = null;
        void entry.handle.isMinimized().then(minimized => {
          if (!valid(entry)) return;
          if (minimized) { if (!itemFor(id)?.minimized) changeSubviewWindow(store, id, "minimize"); return; }
          deps.refresh(entry.node, entry.scoped);
        }).catch(error => { if (valid(entry)) report(error); });
      }, 150);
    }));
    entry.cleanups.push(() => peer.clearTimeout(resizeTimer));
    if (!valid(entry)) { run(entry.handle.destroy()); return; }
    deps.bindWindow(entry.node, entry.scoped);
    deps.onNativeMount?.(entry.node, entry.scoped);
    entry.tooltips = bindAppTooltips(doc);
    chrome(entry, itemFor(id));
    clearTimeout(entry.timeout);
    if (store.getState().assembly.subviewNativeError) store.setState({ assembly: { ...store.getState().assembly, subviewNativeError: "" } });
    await Promise.all([...closing.values()].filter(item => item.id === id).map(item => item.promise));
    if (!valid(entry)) return;
    const bounds = itemFor(id)?.nativeBounds;
    if (bounds) {
      await entry.handle.setPosition(new peer.__TAURI__.dpi.PhysicalPosition(bounds.x, bounds.y));
      await entry.handle.setSize(new peer.__TAURI__.dpi.PhysicalSize(bounds.width, bounds.height));
    } else {
      await fitContent();
    }
    if (!valid(entry)) return;
    await entry.handle.show();
    if (!valid(entry)) return;
    entry.ready = true;
    if (itemFor(id).minimized) await entry.handle.minimize();
    else await manager.focus(store.getState().assembly.subviewWorkspace.activeId);
    // Opening must honor the latest user focus, not steal it back after a slow
    // child bootstrap or a task switch that happened while the peer was hidden.
    if (!valid(entry)) return;
    const restore = deps.restoreEvidence || deps.refreshEvidence;
    if (restore && !entry.scoped.getState().assembly.subview?.pairwiseEvidence) {
      run(Promise.resolve(restore(entry.node, entry.scoped))
        .then(() => valid(entry) && entry.autoSize
          ? fitContent() : null), entry);
    }
  }
  function open(item, generation) {
    let token;
    try {
      token = win.crypto.randomUUID?.() || Array.from(win.crypto.getRandomValues(new Uint8Array(16)),
        byte => byte.toString(16).padStart(2, "0")).join("");
    } catch (error) {
      changeSubviewWindow(store, item.id, "open-docked"); report(error); return;
    }
    const entry = { id: item.id, generation, token, nativePinned: item.pinned !== false, cleanups: [], closing: false };
    entries.set(item.id, entry);
    entry.timeout = setTimeout(() => fail(entry, new Error("Local View window did not finish opening")), 30000);
    const url = new URL("local-view.html", win.location.href); url.search = new URLSearchParams({ view: item.id, token, pinned: item.pinned === false ? "0" : "1" }).toString();
    try { win.open(url.href, `gpm-${item.id}-${token}`); } catch (error) { fail(entry, error); }
  }
  function sync() {
    if (destroyed || syncing) return;
    syncing = true;
    try {
      const state = store.getState(), workspace = state.assembly?.subviewWorkspace;
      const visible = state.activeRoute === "assembly" && root.isConnected !== false;
      const wanted = new Map((visible ? workspace?.windows || [] : []).filter(item => item.floating && item.opened !== false).map(item => [item.id, item]));
      for (const entry of entries.values()) if (!wanted.has(entry.id) || workspace?.generation !== entry.generation) close(entry);
      for (const item of wanted.values()) {
        const entry = entries.get(item.id);
        if (entry) chrome(entry, item); else open(item, workspace.generation);
      }
    } finally { syncing = false; }
  }
  const bridge = { connect, fail(id, token, message) { const entry = entries.get(id); if (entry?.token === token) fail(entry, new Error(message)); } };
  win.__gpmLocalViews = bridge;
  const unsubscribe = store.subscribe(sync);
  void win.__TAURI__.event.listen("gpm-local-view-destroyed", ({ payload }) => {
    const pending = closing.get(payload?.token);
    if (pending?.id === payload?.view) pending.done();
    const entry = entries.get(payload?.view);
    if (entry?.token === payload?.token && valid(entry)) {
      close(entry, true); changeSubviewWindow(store, payload.view, "close");
    }
  }).then(dispose => { if (destroyed) dispose(); else unlistenDestroyed = dispose; });
  const observer = new win.MutationObserver(() => manager.refresh());
  observer.observe(root.ownerDocument.documentElement, { attributes: true, attributeFilter: ["data-theme", "style"] });
  const manager = {
    sync, node: id => entries.get(id)?.node || null,
    async dragPoint() {
      const generation = store.getState().assembly?.subviewWorkspace?.generation;
      const point = await win.__TAURI__.core.invoke("probe_local_view_drag");
      if (destroyed || store.getState().assembly?.subviewWorkspace?.generation !== generation) return null;
      if (point.label === "main") return { ...point, document: root.ownerDocument };
      const entry = [...entries.values()].find(item => item.handle?.label === point.label);
      if (!entry?.node || !valid(entry) || !entry.ready || itemFor(entry.id)?.minimized)
        return { ...point, document: null };
      return { ...point, document: entry.node.ownerDocument };
    },
    focus(id) {
      const request = ++focusSequence, generation = store.getState().assembly?.subviewWorkspace?.generation;
      focusTarget = id === null ? "main" : id;
      return run((async () => {
        await Promise.all([...closing.values()].filter(item => item.id === id).map(item => item.promise));
        if (destroyed || request !== focusSequence || store.getState().assembly?.subviewWorkspace?.generation !== generation) return;
        const item = itemFor(id), entry = entries.get(id);
        if (!item) {
          if (id === null) { await mainHandle.unminimize(); if (request === focusSequence) await mainHandle.setFocus(); }
          return;
        }
        changeSubviewWindow(store, id, "activate");
        if (item.floating) {
          if (!entry?.handle || !entry.ready || !valid(entry)) return;
          // An owned/transient popup is hidden with its minimized owner.
          if (item.pinned !== false) await mainHandle.unminimize();
          if (!valid(entry) || request !== focusSequence) return;
          await entry.handle.unminimize();
          if (!valid(entry) || request !== focusSequence) return;
          await entry.handle.show();
          if (valid(entry) && request === focusSequence) await entry.handle.setFocus();
        } else {
          await mainHandle.unminimize();
          if (request === focusSequence) await mainHandle.setFocus();
        }
      })().finally(() => { if (request === focusSequence) focusTarget = null; }));
    },
    refresh() {
      for (const entry of entries.values()) if (entry.node && valid(entry) && !itemFor(entry.id)?.minimized) deps.refresh(entry.node, entry.scoped);
      sync();
    },
    destroy() {
      destroyed = true; unsubscribe(); observer.disconnect(); unlistenDestroyed?.();
      for (const entry of entries.values()) close(entry);
      if (win.__gpmLocalViews === bridge) delete win.__gpmLocalViews;
      managers.delete(store);
    },
  };
  managers.set(store, manager);
  store.setState({ assembly: { ...store.getState().assembly, subviewNativeWindows: true } });
  sync();
  return manager;
}
