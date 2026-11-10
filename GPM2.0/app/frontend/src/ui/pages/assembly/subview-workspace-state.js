import { taskProjectKey, taskScopeKey, normalizeSubviewTasks, updateSubviewTasks, restoredSubviewWindows, taskText } from "./subview-task-state.js";
import { reconcileLocalSubviewWithMain } from "./subview-fragment-reconcile.js";
// Runtime ownership stays separate from the durable task document. Geometry,
// focus and evidence never enter project task storage.
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
  const project = taskProjectKey(next);
  const projectChanged = assembly.localViewTaskProject !== project;
  if (projectChanged) assembly = { ...assembly, localViewTaskSaveError: "", subviewNativeError: "" };
  let document = projectChanged ? normalizeSubviewTasks(null) : assembly.localViewTasks || normalizeSubviewTasks(null);
  const scope = subviewWorkspaceScope(next);
  let workspace = assembly.subviewWorkspace;
  if (workspace.scope !== scope || projectChanged || workspace.reloadTasks) {
    const keepDraft = workspace.reloadTasks && workspace.scope === scope && !projectChanged && !assembly.subview?.summary;
    const windows = restoredSubviewWindows(document, assembly);
    workspace = { scope, generation: ++generation, nextId: 1, activeId: null, windows };
    // A restored task starts unopened; never reuse the previous chromosome's
    // active summary as a new task in this scope.
    if (!keepDraft && (previous.assembly?.subviewWorkspace || windows.length)) assembly = { ...assembly, subview: null };
  }
  if (!previous.assembly?.loading && assembly.loading) workspace = { ...workspace, loadActiveId: workspace.activeId };
  if (previous.assembly?.loading && !assembly.loading) {
    const current = workspace.windows.find(item => item.id === workspace.activeId);
    // Main loading carries a legacy single-view snapshot captured at request
    // start. Never apply that stale snapshot to a different/current task, nor
    // resurrect a task closed while the Main request was in flight.
    if (current) assembly = { ...assembly, ...current.snapshot };
    else if (workspace.loadActiveId) assembly = { ...assembly, ...captureSubviewWindow(previous.assembly) };
    workspace = { ...workspace, loadActiveId: null };
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
    let snapshot = captureSubviewWindow(assembly);
    const oldSnapshot = windows.find(item => item.id === activeId)?.snapshot;
    if (oldSnapshot && LOCAL_KEYS.every(key => oldSnapshot[key] === snapshot[key])) snapshot = oldSnapshot;
    if (!windows.some(item => item.id === activeId)) {
      activeId = globalThis.crypto?.randomUUID ? `local-${globalThis.crypto.randomUUID()}` : `local-${Date.now()}-${workspace.generation}-${nextId++}`;
      assembly = { ...assembly, trackSelectedCtgIds: [] };
      windows = [...windows, { id: activeId, number: windows.length + 1, snapshot, name: "", note: "", opened: true, floating: true, minimized: false,
        x: 80 + windows.length % 6 * 24, y: 100 + windows.length % 6 * 24, z: Math.max(0, ...windows.map(item => item.z)) + 1 }];
    } else {
      windows = windows.map(item => item.id === activeId ? { ...item, snapshot } : item);
    }
  } else if (activeId && !assembly.loading) {
    windows = windows.filter(item => item.id !== activeId);
    activeId = null;
  }
  windows = windows.map((item, index) => item.number === index + 1 ? item : { ...item, number: index + 1 });
  assembly = { ...assembly, subviewWorkspace: { ...workspace, windows, activeId, nextId,
    pendingSelection: activeId ? null : assembly.subview } };
  document = updateSubviewTasks(document, assembly);
  return { ...next, assembly: { ...assembly, localViewTaskProject: project, localViewTasks: document } };
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
  if (!["close", "activate", "minimize", "dock", "open-docked", "open-floating", "metadata", "reorder", "position", "native-geometry"].includes(action)) return false;
  if (action === "position") patch = Object.fromEntries(["x", "y", "width", "height"].filter(key => Number.isFinite(patch[key])).map(key => [key, patch[key]]));
  if (action === "native-geometry") {
    const rect = patch.nativeBounds;
    if (!["x", "y", "width", "height"].every(key => Number.isFinite(rect?.[key])) || rect.width <= 0 || rect.height <= 0) return false;
    patch = { nativeBounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
  }
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
    if (action === "metadata") patch = { name: taskText(patch.name ?? target.name, 80), note: taskText(patch.note ?? target.note, 4000) };
    if (action === "reorder") {
      const destination = windows.findIndex(item => item.id === patch.beforeId);
      if (destination < 0 || patch.beforeId === id) return false;
      windows = windows.filter(item => item.id !== id);
      windows.splice(destination, 0, target);
      patch = {};
    }
    if (action === "dock" || action === "open-docked" || action === "open-floating") {
      patch = { floating: action === "dock" ? !target.floating : action === "open-floating", opened: true, minimized: false };
      action = "activate";
    }
    if (action === "activate") {
      activeId = id;
      next = { ...assembly, ...target.snapshot };
      patch = { ...patch, opened: true, minimized: false, z: Math.max(0, ...windows.map(item => item.z)) + 1 };
    }
    if (action === "minimize") patch = { minimized: true };
    // Exactly one docked slot. Replacing it leaves the old task unopened.
    if (action === "activate" && !(patch.floating ?? target.floating)) {
      windows = windows.map(item => item.id !== id && !item.floating ? { ...item, opened: false } : item);
    }
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

export function hydrateSubviewTasks(store, saved, baseline) {
  const state = store.getState(), assembly = state.assembly;
  if (!saved) throw new Error("Invalid Local View task document");
  const loaded = normalizeSubviewTasks(saved);
  const current = assembly.localViewTasks || normalizeSubviewTasks(null);
  // Merge changes made while loading by stable ID. Newly created tasks must not
  // erase saved tasks that were not visible yet; only known IDs can be deleted.
  const scopes = { ...loaded.scopes };
  for (const [key, tasks] of Object.entries(current.scopes)) {
    const before = baseline?.scopes?.[key];
    if (!(key in scopes)) { scopes[key] = tasks; continue; }
    if (tasks === before) continue;
    const known = new Set((before || []).map(task => task.id));
    const live = new Set(tasks.map(task => task.id));
    const previouslyUnseen = scopes[key].filter(task => !known.has(task.id) && !live.has(task.id));
    scopes[key] = [...previouslyUnseen, ...tasks];
  }
  const scope = taskScopeKey(assembly), document = { version: 1, scopes };
  const changedWhileLoading = current.scopes[scope] !== baseline?.scopes?.[scope];
  const keepLive = changedWhileLoading || !(scope in loaded.scopes);
  const existing = new Map(assembly.subviewWorkspace.windows.map(item => [item.id, item]));
  const windows = keepLive ? restoredSubviewWindows(document, assembly).map(item => existing.get(item.id) || item)
    : assembly.subviewWorkspace.windows;
  store.setState({ assembly: { ...assembly, localViewTasks: document,
    subviewWorkspace: { ...assembly.subviewWorkspace, windows, reloadTasks: !keepLive } } });
}
