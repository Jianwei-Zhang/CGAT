import { reconcileLocalSubviewWithMain } from "./subview-fragment-reconcile.js";
// Runtime-only window ownership. Project persistence continues to use the existing
// Local View fields; neither window geometry nor evidence is serialized here.
const LOCAL_KEYS = [
  "subview", "subviewTrackView", "subviewTrackDragOffsets", "subviewTrackScrollState",
  "subviewCompositionViewport", "subviewHistoryByKey", "subviewAnchorStateByKey",
  "subviewRestoring", "subviewRestoringSummary", "subviewRestoreError",
];
const localKeys = new Set(LOCAL_KEYS);
let generation = 0;
const installed = new WeakSet();
const windowStores = new WeakMap();

export function subviewWorkspaceScope(state) {
  return JSON.stringify([state.session?.workspacePath, state.session?.projectId,
    state.assembly?.selectedChrName, state.assembly?.supportDatasetId]);
}

export function captureSubviewWindow(assembly) {
  return Object.fromEntries(LOCAL_KEYS.map(key => [key, assembly?.[key]]));
}

export function startSubviewWindowDraft(assembly) {
  if (!assembly?.subviewWorkspace) return assembly;
  return { ...assembly, subviewWorkspace: { ...assembly.subviewWorkspace, activeId: null },
    subview: null, subviewTrackDragOffsets: [], subviewCompositionViewport: {},
    subviewTrackScrollState: { viewportKey: "", scrollLeft: 0 } };
}

export function reconcileSubviewWorkspace(previous, next) {
  let assembly = next.assembly;
  if (!assembly?.subviewWorkspace) return next;
  const scope = subviewWorkspaceScope(next);
  let workspace = assembly.subviewWorkspace;
  if (workspace.scope !== scope) {
    workspace = { scope, generation: ++generation, nextId: 1, activeId: null, windows: [] };
  }
  let windows = workspace.windows;
  if (!assembly.loading && (previous.assembly?.chrCtgs !== assembly.chrCtgs
    || previous.assembly?.deletedCtgs !== assembly.deletedCtgs)) {
    windows = windows.map(item => {
      if (item.id === workspace.activeId) return item;
      const reconciled = reconcileLocalSubviewWithMain({ ...assembly, ...item.snapshot });
      return { ...item, snapshot: captureSubviewWindow(reconciled) };
    });
  }
  let activeId = workspace.activeId;
  let nextId = workspace.nextId;
  if (assembly.subview?.summary && !assembly.loading) {
    const snapshot = captureSubviewWindow(assembly);
    if (!windows.some(item => item.id === activeId)) {
      activeId = `local-${workspace.generation}-${nextId++}`;
      assembly = { ...assembly, trackSelectedCtgIds: [] };
      windows = [...windows, { id: activeId, number: nextId - 1, snapshot, floating: true, minimized: false,
        x: 80 + windows.length % 6 * 24, y: 100 + windows.length % 6 * 24, z: Math.max(0, ...windows.map(item => item.z)) + 1 }];
    } else {
      windows = windows.map(item => item.id === activeId ? { ...item, snapshot } : item);
    }
  } else if (activeId && !assembly.loading) {
    windows = windows.filter(item => item.id !== activeId);
    activeId = null;
  }
  return { ...next, assembly: { ...assembly,
    subviewWorkspace: { ...workspace, windows, activeId, nextId,
      pendingSelection: activeId ? null : assembly.subview } } };
}

export function installSubviewWorkspace(store) {
  if (store.localViewRootStore || !store.addStateTransform) return false;
  if (!installed.has(store)) {
    installed.add(store);
    store.addStateTransform(reconcileSubviewWorkspace);
  }
  const state = store.getState();
  if (state.assembly?.subviewWorkspace) return false;
  store.setState({ assembly: { ...state.assembly, subviewWorkspace: {
    scope: subviewWorkspaceScope(state), generation: ++generation,
    nextId: 1, activeId: null, windows: [],
  } } });
  return true;
}

export function changeSubviewWindow(store, id, action, patch = {}) {
  store = store.localViewRootStore || store;
  const state = store.getState();
  const assembly = state.assembly;
  const workspace = assembly?.subviewWorkspace;
  const target = workspace?.windows.find(item => item.id === id);
  if (!target) return false;
  let next = assembly;
  let activeId = workspace.activeId;
  let windows = workspace.windows;
  if (action === "close") {
    windows = windows.filter(item => item.id !== id);
    if (activeId === id) {
      activeId = null;
      next = { ...assembly, subview: null, subviewTrackDragOffsets: [],
        subviewCompositionViewport: {}, subviewTrackScrollState: {} };
    }
  } else {
    if (action === "activate") {
      activeId = id;
      next = { ...assembly, ...target.snapshot };
      patch = { ...patch, minimized: false, z: Math.max(0, ...windows.map(item => item.z)) + 1 };
    }
    if (action === "minimize") patch = { minimized: true };
    if (action === "dock") patch = { floating: !target.floating };
    windows = windows.map(item => item.id === id ? { ...item, ...patch } : item);
  }
  store.setState({ assembly: { ...next, subviewWorkspace: { ...workspace, activeId, windows } } });
  return true;
}

// A window owns its Local View fields, but reads live Main/project data. Late
// asynchronous writes to closed windows or another viewing scope are discarded.
export function getSubviewWindowStore(store, id = null) {
  if (store.localViewRootStore) return store;
  const workspace = store.getState().assembly?.subviewWorkspace;
  id ||= workspace?.activeId;
  if (!id || !workspace?.windows.some(item => item.id === id)) return store;
  let cache = windowStores.get(store);
  if (!cache) windowStores.set(store, cache = new Map());
  const key = `${workspace.generation}:${id}`;
  if (cache.has(key)) return cache.get(key);
  const owner = workspace.generation;
  const lookup = state => state.assembly?.subviewWorkspace?.generation === owner
    ? state.assembly.subviewWorkspace.windows.find(item => item.id === id) : null;
  const scoped = {
    localViewRootStore: store,
    localViewWindowId: id,
    isLocalViewAlive: () => Boolean(lookup(store.getState())),
    getState() {
      const state = store.getState();
      const item = lookup(state);
      return { ...state, assembly: { ...state.assembly,
        ...(item?.snapshot || { subview: null }), subviewWindowRendering: id } };
    },
    setState(patch) {
      const live = store.getState();
      const item = lookup(live);
      if (!item) return;
      const projected = scoped.getState();
      const nextLocal = patch.assembly ? captureSubviewWindow(patch.assembly) : item.snapshot;
      const shared = {};
      for (const [field, value] of Object.entries(patch.assembly || {})) {
        if (!localKeys.has(field) && field !== "subviewWorkspace" && field !== "subviewWindowRendering"
          && value !== projected.assembly[field]) shared[field] = value;
      }
      const ws = live.assembly.subviewWorkspace;
      const windows = ws.windows.flatMap(entry => entry.id !== id ? [entry]
        : nextLocal.subview?.summary ? [{ ...entry, snapshot: nextLocal }] : []);
      const { assembly: _assembly, ...rest } = patch;
      store.setState({ ...rest, assembly: { ...live.assembly, ...shared,
        ...(ws.activeId === id ? nextLocal : {}), subviewWorkspace: { ...ws, windows } } });
    },
    subscribe(listener) { return store.subscribe(() => listener(scoped.getState())); },
  };
  cache.set(key, scoped);
  // Do not retain evidence arrays from closed scopes through cached stores.
  for (const oldKey of cache.keys()) if (!oldKey.startsWith(`${owner}:`)) cache.delete(oldKey);
  return scoped;
}
