import { getSubviewState, normalizeSubviewSummarySelection, normalizeSubviewTrackSummary } from "./subview-state.js";
import { createSubviewCompositionSummary } from "./subview-composition-state.js";
import { normalizeSubviewTrackDragOffsets } from "./selection-state.js";
import { normalizeSubviewHistoryByKey, normalizeSubviewCompositionViewport } from "./subview-history-state.js";
import { normalizeSubviewAnchorStateByKey } from "./subview-anchor-state.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { normalizeViewportScrollState } from "./scroll-position-state.js";

export const SUBVIEW_TASK_VERSION = 1;
export const taskProjectKey = state => JSON.stringify([state.session?.workspacePath, state.session?.projectId]);
export const taskScopeKey = assembly => JSON.stringify([assembly?.selectedChrName || "", assembly?.supportDatasetId ?? null]);
export const taskText = (value, limit) => String(value ?? "").replace(/\r\n?/g, "\n").trim().slice(0, limit);
const object = value => value && typeof value === "object" && !Array.isArray(value);
const normalized = new WeakMap();
function memo(value, normalize) {
  if (!value || typeof value !== "object") return normalize(value);
  let cache = normalized.get(value);
  if (!cache) normalized.set(value, cache = new Map());
  if (!cache.has(normalize)) cache.set(normalize, normalize(value));
  return cache.get(normalize);
}

function durableSubview(raw) {
  const summary = raw?.summary;
  if (!summary) return null;
  let normalized;
  if (summary.mode === "composition") normalized = createSubviewCompositionSummary(summary);
  else if (summary.mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary.bottomTrack);
    if (!topTrack || !bottomTrack) return null;
    normalized = { mode: "track-pair", topTrack, bottomTrack };
  } else if (summary.mode === "2-contig") {
    const top = normalizeSubviewSummarySelection(summary.top), bottom = normalizeSubviewSummarySelection(summary.bottom);
    if (!top || !bottom) return null;
    normalized = { mode: "2-contig", top, bottom };
  } else return null;
  const subview = getSubviewState({ subview: { ...raw, summary: normalized, pairwiseEvidence: null,
    trackPairSelectedCtgs: [], error: "", message: "" } });
  delete subview.pairwiseEvidence;
  return subview;
}

// Explicit allowlist. Immutable field caches avoid normalizing entire member and
// history arrays again for every scroll event or OS window focus change.
export function persistableSubviewSnapshot(snapshot) {
  const subview = memo(snapshot?.subview, durableSubview);
  if (!subview) return null;
  return {
    subview,
    subviewTrackView: memo(snapshot.subviewTrackView, resolveTrackPrefs),
    subviewTrackDragOffsets: memo(snapshot.subviewTrackDragOffsets, normalizeSubviewTrackDragOffsets),
    subviewTrackScrollState: memo(snapshot.subviewTrackScrollState, normalizeViewportScrollState),
    subviewCompositionViewport: Object.keys(snapshot.subviewCompositionViewport || {}).length
      ? memo(snapshot.subviewCompositionViewport, normalizeSubviewCompositionViewport) : {},
    subviewHistoryByKey: memo(snapshot.subviewHistoryByKey, normalizeSubviewHistoryByKey),
    subviewAnchorStateByKey: memo(snapshot.subviewAnchorStateByKey, normalizeSubviewAnchorStateByKey),
  };
}

export function normalizeSubviewTasks(value) {
  const scopes = {};
  if (value == null) return { version: SUBVIEW_TASK_VERSION, scopes };
  if (value.version !== SUBVIEW_TASK_VERSION || !object(value.scopes)) throw new Error("Unsupported Local View task document");
  for (const [key, tasks] of Object.entries(value.scopes)) {
    let scope;
    try { scope = JSON.parse(key); } catch { throw new Error("Invalid Local View task scope"); }
    if (!Array.isArray(scope) || scope.length !== 2 || typeof scope[0] !== "string" || !Array.isArray(tasks)) throw new Error("Invalid Local View task scope");
    const seen = new Set();
    scopes[key] = tasks.flatMap(task => {
      const id = String(task?.id || "");
      const snapshot = persistableSubviewSnapshot(task?.snapshot);
      if (!/^local-[a-zA-Z0-9-]+$/.test(id) || seen.has(id) || !snapshot) throw new Error("Invalid Local View task definition");
      seen.add(id);
      return [{ id, name: taskText(task.name, 80), note: taskText(task.note, 4000), snapshot }];
    });
  }
  return { version: SUBVIEW_TASK_VERSION, scopes };
}

const snapshots = new WeakMap();
function durableSnapshot(snapshot) {
  if (!snapshots.has(snapshot)) snapshots.set(snapshot, persistableSubviewSnapshot(snapshot));
  return snapshots.get(snapshot);
}
export function updateSubviewTasks(document, assembly) {
  const scope = taskScopeKey(assembly);
  const tasks = (assembly.subviewWorkspace?.windows || []).flatMap(item => {
    const snapshot = durableSnapshot(item.snapshot);
    return snapshot ? [{ id: item.id, name: item.name || "", note: item.note || "", snapshot }] : [];
  });
  const previous = document.scopes[scope];
  // An untouched empty scope is not an explicit user closure. Keeping it absent
  // permits one-time migration of the legacy saved composition on first load.
  if (!previous && tasks.length === 0) return document;
  // Evidence hydration may replace a runtime snapshot without changing any
  // durable fields. Do not enqueue an identical database write for those updates.
  tasks.forEach((task, index) => {
    const old = previous?.[index];
    if (old?.id === task.id && old.snapshot !== task.snapshot
      && Object.keys(task.snapshot).every(key => old.snapshot[key] === task.snapshot[key]
        || JSON.stringify(old.snapshot[key]) === JSON.stringify(task.snapshot[key]))) task.snapshot = old.snapshot;
  });
  if (previous && previous.length === tasks.length && tasks.every((task, i) => task.id === previous[i].id
    && task.name === previous[i].name && task.note === previous[i].note && task.snapshot === previous[i].snapshot)) return document;
  return { version: SUBVIEW_TASK_VERSION, scopes: { ...document.scopes, [scope]: tasks } };
}

export function restoredSubviewWindows(document, assembly) {
  return (document?.scopes?.[taskScopeKey(assembly)] || []).map((task, index) => ({
    ...task, number: index + 1, floating: false, opened: false, minimized: false, pinned: true,
    x: 80, y: 100, z: 0,
    snapshot: { ...task.snapshot, subviewRestoring: false,
      subviewRestoringSummary: null, subviewRestoreError: "" },
  }));
}
