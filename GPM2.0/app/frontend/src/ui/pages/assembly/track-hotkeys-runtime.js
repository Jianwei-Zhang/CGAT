import { filterPrimaryTrackSelectionCtgIds, normalizeTrackSelectionCtgIds } from "./selection-state.js";
import { resolveFilteredSubviewTrackPairSelectionsFromAssembly } from "./subview-state.js";

const ASSEMBLY_TRACK_HOTKEYS_BOUND = Symbol("assemblyTrackHotkeysBound");
const ASSEMBLY_TRACK_HOTKEYS_HANDLER = Symbol("assemblyTrackHotkeysHandler");
const REQUIRED_TRACK_HOTKEY_BINDING_DEPS = ["handleTrackDeleteHotkey"];
const REQUIRED_TRACK_HOTKEY_ACTION_DEPS = [
  "deleteSelectedSubviewTrackPairCtgs",
  "deleteSelectedTrackCtgs",
];

function assertTrackHotkeyBindingDeps(deps) {
  const missing = REQUIRED_TRACK_HOTKEY_BINDING_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing track hotkey binding deps: ${missing.join(", ")}`);
}

function assertTrackHotkeyActionDeps(deps) {
  const missing = REQUIRED_TRACK_HOTKEY_ACTION_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing track hotkey action deps: ${missing.join(", ")}`);
}

function getWindowObject() {
  return globalThis.window;
}

export function bindTrackSelectionHotkeys(host, store, deps) {
  assertTrackHotkeyBindingDeps(deps);
  if (host[ASSEMBLY_TRACK_HOTKEYS_BOUND]) {
    return;
  }
  const keydownHandler = (event) => {
    void deps.handleTrackDeleteHotkey(host, store, event);
  };
  getWindowObject()?.addEventListener?.("keydown", keydownHandler, true);
  host[ASSEMBLY_TRACK_HOTKEYS_HANDLER] = keydownHandler;
  host[ASSEMBLY_TRACK_HOTKEYS_BOUND] = true;
}

export async function handleTrackDeleteHotkey(host, store, event, deps) {
  assertTrackHotkeyActionDeps(deps);
  const state = store.getState();
  if (!shouldHandleTrackDeleteHotkey(event, state)) {
    return false;
  }
  const subviewSelectedEntries = resolveFilteredSubviewTrackPairSelectionsFromAssembly(state.assembly);
  if (subviewSelectedEntries.length) {
    event.preventDefault?.();
    await deps.deleteSelectedSubviewTrackPairCtgs(host, store, subviewSelectedEntries);
    return true;
  }
  const primarySelectedIds = filterPrimaryTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds, state.assembly);
  if (!primarySelectedIds.length) {
    return false;
  }
  event.preventDefault?.();
  await deps.deleteSelectedTrackCtgs(host, store, primarySelectedIds);
  return true;
}

export function shouldHandleTrackDeleteHotkey(event, state) {
  if (String(event?.key || "").trim() !== "Delete") {
    return false;
  }
  if (event?.ctrlKey || event?.metaKey || event?.altKey) {
    return false;
  }
  if (String(state?.assembly?.activeTab || "") !== "assembly") {
    return false;
  }
  const selectedIds = normalizeTrackSelectionCtgIds(state?.assembly?.trackSelectedCtgIds);
  const selectedSubviewTrackPairCtgs = resolveFilteredSubviewTrackPairSelectionsFromAssembly(state?.assembly);
  if (!selectedIds.length && !selectedSubviewTrackPairCtgs.length) {
    return false;
  }
  const target = event?.target;
  const tagName = String(target?.tagName || "").toUpperCase();
  if (tagName === "INPUT" || tagName === "TEXTAREA") {
    return false;
  }
  if (target?.isContentEditable) {
    return false;
  }
  return true;
}
