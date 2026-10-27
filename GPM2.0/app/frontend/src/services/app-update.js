import { hasRunningProjectExports } from "./project-export-jobs.js";
export const UPDATE_SNOOZE_KEY = "gpm_next:update_snooze_until";
export const UPDATE_SNOOZE_MS = 24 * 60 * 60 * 1000;
const ACTIVE = new Set(["checking", "downloading", "installing"]);

// Dependency-injected state machine; all privileged operations stay in Rust.
export function createAppUpdater({ invoke, listen = async () => () => {}, storage,
  now = Date.now, prepareInstall = async () => {}, isBusy = () => false,
  canNotify = () => true, onOffer = () => {} }) {
  let state = { phase: "idle", currentVersion: "", enabled: false, version: null,
    ready: false, checkedAt: null, error: "", downloaded: 0, total: 0, source: "" };
  const subscribers = new Set();
  const dismissed = new Set();
  let notifying = false;
  let unlisten = () => {};
  const snapshot = () => ({ ...state });
  const set = patch => { state = { ...state, ...patch }; for (const fn of subscribers) fn(snapshot()); };
  const snoozed = () => {
    try { const until = Number(storage?.getItem(UPDATE_SNOOZE_KEY)); return Number.isFinite(until) && until > now(); }
    catch { return false; }
  };
  function snooze() {
    try {
      if (!storage) throw new Error("storage unavailable");
      storage.setItem(UPDATE_SNOOZE_KEY, String(now() + UPDATE_SNOOZE_MS));
      return true;
    } catch { set({ error: "update_storage" }); return false; }
  }
  function notify(manual = false) {
    if (!state.version || notifying || state.phase === "installing") return;
    if (!manual && (!["available", "ready"].includes(state.phase) || snoozed() || dismissed.has(state.version) || isBusy() || !canNotify())) return;
    notifying = true;
    try { onOffer(); } catch { notifying = false; }
  }
  return {
    getState: snapshot,
    subscribe(fn) { subscribers.add(fn); return () => subscribers.delete(fn); },
    async initialize() {
      try {
        const info = await invoke("app_update_status");
        unlisten = await listen("app-update-progress", event => {
          if (state.phase === "downloading") set(event.payload || event);
        });
        set({ ...info, phase: info.enabled ? (info.ready ? "ready" : info.version ? "available" : "idle") : "unavailable" });
      } catch { set({ enabled: false, phase: "unavailable", error: "update_unconfigured" }); }
    },
    async check({ manual = false } = {}) {
      if (ACTIVE.has(state.phase)) { if (manual && state.version) notify(true); return; }
      if (!state.enabled) return;
      if (state.ready) { notify(manual); return; }
      set({ phase: "checking", error: "" });
      try {
        const info = await invoke("app_update_check");
        set({ ...info, phase: info.ready ? "ready" : info.version ? "available" : "latest", checkedAt: now() });
        notify(manual);
      } catch (error) { set({ phase: "error", error: String(error?.message || error) }); }
    },
    notify, snooze,
    dismiss(mute = false) {
      // Do not silently claim a persistent 24h preference if storage is unavailable.
      if (mute && !snooze()) return false;
      if (!mute && state.version) dismissed.add(state.version);
      notifying = false;
      return true;
    },
    async notes(locale) { return invoke("app_update_notes", { locale: locale === "en" ? "en" : "zh" }); },
    async download() {
      if (!state.version || ACTIVE.has(state.phase) || state.ready) return;
      set({ phase: "downloading", error: "", downloaded: 0, total: 0, source: "" });
      try { await invoke("app_update_download"); set({ phase: "ready", ready: true }); }
      catch (error) { set({ phase: "error", error: String(error?.message || error) }); }
    },
    async install() {
      if (!state.ready || ACTIVE.has(state.phase)) return;
      if (isBusy()) { set({ error: "update_work_busy" }); return; }
      set({ phase: "installing", error: "" });
      try {
        await prepareInstall();
        if (isBusy()) throw new Error("update_work_busy");
        await invoke("app_update_install");
      } catch (error) { set({ phase: "ready", error: String(error?.message || error) }); }
    },
    dispose() { unlisten(); subscribers.clear(); },
  };
}

export function updateWorkBusy(state = {}, pendingCommands = 0) {
  const i = state.importer || {}, init = state.initializer || {}, a = state.assembly || {};
  return Boolean(hasRunningProjectExports() || pendingCommands || i.inFlight || i.restoringSession || i.entryResolving
    || i.copyDialog?.inFlight || init.loading || init.creating || init.updating || init.autoPipelineRunning
    || a.loading || a.bootstrapping || a.mainViewHistory?.inFlight || state.projectExport?.loading
    || state.projectExport?.job?.status === "running");
}
