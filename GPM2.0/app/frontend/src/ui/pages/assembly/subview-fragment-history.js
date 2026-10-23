import {
  activateSubviewHistory, applySubviewEditableSnapshot, buildSubviewCompositionHistoryKey,
  normalizeSubviewHistoryByKey, SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION, buildSubviewEditableSnapshot,
} from "./subview-history-state.js";
import { applySubviewComposition } from "./subview-composition-state.js";
import { getSubviewState } from "./subview-state.js";
import { projectCurrentSubviewToComposition } from "./subview-composition-controller.js";

// Upgrade source references BEFORE the native mutation retires any real parent.
// Preserve the legacy history's operation count, offsets, order, hide/flip state,
// anchors and redo branch; do not replace its baseline with an easier new one.
export function prepareSourceOwnedSubviewHistory(state, host, { viewport, projectHistorical, preserveLegacy = false } = {}) {
  const activated = activateSubviewHistory(state.assembly, { stateOrLocale: state });
  const assembly = activated.assembly, subview = getSubviewState(assembly);
  const records = normalizeSubviewHistoryByKey(assembly.subviewHistoryByKey);
  const old = records[activated.pairKey];
  if (!old) throw new Error("Local View history cannot be prepared");
  const cache = new Map();
  const convert = (snapshot) => {
    if (snapshot?.kind === "composition") return snapshot;
    const legacy = snapshot?.kind === "legacy" ? snapshot : { kind: "legacy", summary: subview.summary, editableSnapshot: snapshot };
    const key = JSON.stringify(legacy);
    if (cache.has(key)) return cache.get(key);
    const applied = applySubviewEditableSnapshot({ ...subview, summary: legacy.summary,
      mode: legacy.summary.mode }, legacy.editableSnapshot, state);
    if (!applied) throw new Error("A saved Local View history snapshot is incompatible");
    const historicalState = { ...state, assembly: { ...assembly, subview: applied.subview,
      subviewTrackDragOffsets: applied.subviewTrackDragOffsets } };
    if (!legacy.sourceProjection && typeof projectHistorical !== "function") throw new Error("Historical Local View projection is required");
    const projection = legacy.sourceProjection || projectHistorical(historicalState);
    const result = preserveLegacy ? { ...legacy, sourceProjection: projection } : { kind: "composition", composition: projection };
    cache.set(key, result); return result;
  };
  const composition = projectCurrentSubviewToComposition({ ...state, assembly }, host);
  const record = { ...old, version: SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION,
    pairKey: buildSubviewCompositionHistoryKey(assembly.selectedChrName),
    current: preserveLegacy && subview.summary?.mode !== "composition"
      ? { kind: "legacy", summary: subview.summary, editableSnapshot: buildSubviewEditableSnapshot(subview, assembly.subviewTrackDragOffsets), sourceProjection: composition }
      : { kind: "composition", composition }, default: convert(old.default),
    past: old.past.map((entry) => ({ ...entry, snapshot: convert(entry.snapshot) })),
    forward: old.forward.map((entry) => ({ ...entry, snapshot: convert(entry.snapshot) })), viewport };
  return { ...assembly, subview: preserveLegacy && subview.summary?.mode !== "composition"
    ? { ...subview, historyKey: record.pairKey } : applySubviewComposition(subview, composition, { historyKey: record.pairKey }),
    subviewCompositionViewport: viewport, subviewHistoryByKey: { ...records, [record.pairKey]: record } };
}
