import { invokeCommand } from "../../../services/backend-api.js";
import { hydrateSubviewTasks, installSubviewWorkspace } from "./subview-workspace-state.js";
import { taskProjectKey } from "./subview-task-state.js";

const controllers = new WeakMap();
const preview = new Map();
const native = () => Boolean(globalThis.window?.__TAURI__?.core?.invoke);
async function load(args) {
  return native() ? invokeCommand("get_project_local_view_tasks", args)
    : preview.get(JSON.stringify([args.workspaceRoot, args.projectId])) || { version: 1, scopes: {} };
}
async function save(args) {
  if (native()) await invokeCommand("set_project_local_view_tasks", args);
  else preview.set(JSON.stringify([args.workspaceRoot, args.projectId]), structuredClone(args.state));
}

// A single writer per project owner, never per scoped view. Capture the identity
// with each save; late loads from project A cannot hydrate project B (or ABA).
export function installSubviewTaskPersistence(store, deps = {}) {
  if (store.localViewRootStore || !store.subscribe || !store.addStateTransform) return null;
  if (controllers.has(store)) return controllers.get(store);
  let session, chain = Promise.resolve(), timer = null;
  const clearPending = () => { if (timer !== null) clearTimeout(timer); timer = null; };
  const report = error => {
    const state = store.getState();
    store.setState({ assembly: { ...state.assembly, localViewTaskSaveError: String(error?.message || error) } });
  };
  function write(owner, retry = false) {
    if (!owner?.ready || owner.latest === owner.saved || owner.latest === owner.enqueued
      || (!retry && owner.latest === owner.failed)) return chain;
    const document = owner.latest;
    owner.enqueued = document;
    chain = chain.catch(() => {}).then(async () => {
      try {
        await (deps.save || save)({ ...owner.identity, state: document });
        owner.saved = document;
        if (owner.failed === document) owner.failed = null;
        if (session === owner && store.getState().assembly.localViewTaskSaveError) {
          const state = store.getState();
          store.setState({ assembly: { ...state.assembly, localViewTaskSaveError: "" } });
        }
      } catch (error) {
        owner.failed = document;
        throw error;
      } finally {
        if (owner.enqueued === document) owner.enqueued = null;
      }
    });
    // A failed autosave is not automatically retried by the error notification's
    // own state update. Retry only on a new edit or explicit checked flush.
    chain.catch(error => { if (session === owner) report(error); });
    return chain;
  }
  function read(owner) {
    owner.error = null;
    owner.loading = chain.catch(() => {}).then(() => (deps.load || load)(owner.identity)).then(saved => {
      if (session !== owner || taskProjectKey(store.getState()) !== owner.key) return;
      hydrateSubviewTasks(store, saved, owner.baseline);
      owner.latest = store.getState().assembly.localViewTasks;
      owner.ready = true;
      void write(owner);
    }).catch(error => { owner.error = error; if (session === owner) report(error); });
    return owner.loading;
  }
  function observe(state) {
    const key = taskProjectKey(state), identity = { workspaceRoot: state.session?.workspacePath, projectId: state.session?.projectId };
    if (!identity.workspaceRoot || !identity.projectId || !state.assembly?.subviewWorkspace) {
      clearPending(); write(session); session = null; return;
    }
    if (session?.key !== key) {
      clearPending(); write(session);
      const owner = session = { key, identity, latest: state.assembly.localViewTasks, baseline: state.assembly.localViewTasks, ready: false };
      void read(owner);
    }
    const changed = session.latest !== state.assembly.localViewTasks;
    session.latest = state.assembly.localViewTasks;
    if (!changed || !session.ready) return;
    clearPending();
    timer = setTimeout(() => { timer = null; void write(session); }, deps.saveDelay ?? 250);
  }
  const unsubscribe = store.subscribe(observe);
  const controller = {
    async ready() {
      observe(store.getState());
      const owner = session;
      await owner?.loading;
      return owner ? Boolean(owner.ready && !owner.error) : true;
    },
    async flush() {
      observe(store.getState());
      clearPending();
      const owner = session;
      if (owner?.error) await read(owner);
      else await owner?.loading;
      if (owner?.error) throw owner.error;
      do {
        await write(owner, true);
      } while (owner?.ready && session === owner && owner.latest !== owner.saved);
    },
    destroy() { clearPending(); unsubscribe(); controllers.delete(store); },
  };
  controllers.set(store, controller);
  observe(store.getState());
  return controller;
}

export async function flushSubviewTasks(store) {
  await controllers.get(store.localViewRootStore || store)?.flush();
}

// Initial assembly loading waits for task definitions before migrating the old
// single-comparison history, avoiding a duplicate legacy task racing the read.
export async function prepareSubviewTasks(store) {
  store = store.localViewRootStore || store;
  installSubviewWorkspace(store);
  return await installSubviewTaskPersistence(store)?.ready() ?? true;
}
