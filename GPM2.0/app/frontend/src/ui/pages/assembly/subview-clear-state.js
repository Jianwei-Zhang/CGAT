import { buildSubviewAnchorStateKey } from "./subview-anchor-state.js";
import { buildSubviewCompositionHistoryKey } from "./subview-history-state.js";
import { getSubviewState } from "./subview-state.js";

function own(object, key) {
  return Boolean(key) && Object.prototype.hasOwnProperty.call(object || {}, key);
}

function withoutKeys(value, keys) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const remove = new Set(keys.filter(Boolean));
  return Object.fromEntries(Object.entries(source).filter(([key]) => !remove.has(key)));
}

function resolveSubviewClearKeys(assembly) {
  const subview = getSubviewState(assembly);
  const chrName = String(assembly?.selectedChrName || "").trim();
  const activePairKey = buildSubviewAnchorStateKey(subview.summary, chrName);
  const compositionKey = buildSubviewCompositionHistoryKey(chrName);
  const historyKey = String(subview.historyKey || "").trim();
  const activeHistoryKey = historyKey === activePairKey || historyKey === compositionKey
    ? historyKey
    : "";
  return {
    activePairKey,
    compositionKey,
    historyKeys: Array.from(new Set([activePairKey, compositionKey, activeHistoryKey].filter(Boolean))),
    anchorKeys: activePairKey ? [activePairKey] : [],
  };
}

function hasSubviewContent(subview) {
  return Boolean(
    subview.summary
    || subview.historyKey
    || subview.pairwiseEvidence
    || subview.selectedAContigId
    || subview.selectedBContigId
    || subview.selectedTrackSelections.length
    || subview.activeAnchors.length
    || subview.manualAnchors.length
    || subview.flippedCtgs.length
    || subview.trackPairHiddenCtgs.length
    || subview.trackPairSelectedCtgs.length
    || subview.message
    || subview.error
  );
}

function canClearSubviewState(assembly) {
  const subview = getSubviewState(assembly);
  const keys = resolveSubviewClearKeys(assembly);
  const viewport = assembly?.subviewCompositionViewport;
  const scroll = assembly?.subviewTrackScrollState;
  return hasSubviewContent(subview)
    || (Array.isArray(assembly?.subviewTrackDragOffsets)
      && assembly.subviewTrackDragOffsets.length > 0)
    || Boolean(viewport && typeof viewport === "object" && Object.keys(viewport).length)
    || Boolean(String(scroll?.viewportKey || "").trim() || Number(scroll?.scrollLeft) > 0)
    || keys.historyKeys.some((key) => own(assembly?.subviewHistoryByKey, key))
    || keys.anchorKeys.some((key) => own(assembly?.subviewAnchorStateByKey, key));
}

export function clearSubviewRecordsForSummary(assembly, summary) {
  const key = buildSubviewAnchorStateKey(summary, assembly?.selectedChrName);
  if (!key) {
    return assembly;
  }
  return {
    ...assembly,
    subviewHistoryByKey: withoutKeys(assembly?.subviewHistoryByKey, [key]),
    subviewAnchorStateByKey: withoutKeys(assembly?.subviewAnchorStateByKey, [key]),
  };
}

export function buildSubviewClearProjection(assembly) {
  if (!canClearSubviewState(assembly)) {
    return { assembly, changed: false };
  }
  const keys = resolveSubviewClearKeys(assembly);
  return {
    changed: true,
    assembly: {
      ...assembly,
      subview: getSubviewState({ subview: { mode: "2-contig" } }),
      subviewTrackDragOffsets: [],
      subviewCompositionViewport: {},
      subviewTrackScrollState: { viewportKey: "", scrollLeft: 0 },
      subviewHistoryByKey: withoutKeys(assembly?.subviewHistoryByKey, keys.historyKeys),
      subviewAnchorStateByKey: withoutKeys(assembly?.subviewAnchorStateByKey, keys.anchorKeys),
    },
  };
}
