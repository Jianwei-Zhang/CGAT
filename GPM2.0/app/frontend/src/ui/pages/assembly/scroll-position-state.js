import { normalizeSupportDatasetId } from "./selection-state.js";
import { getSubviewState, normalizeSubviewSummarySelection } from "./subview-state.js";
import { normalizeNonNegativeInt, resolveTrackPrefs } from "./track-prefs.js";

export function normalizeViewportScrollState(value) {
  const viewportKey =
    typeof value?.viewportKey === "string" ? value.viewportKey.trim() : "";
  return {
    viewportKey,
    scrollLeft: normalizeNonNegativeInt(value?.scrollLeft),
  };
}

export function areViewportScrollStatesEqual(left, right) {
  const normalizedLeft = normalizeViewportScrollState(left);
  const normalizedRight = normalizeViewportScrollState(right);
  return normalizedLeft.viewportKey === normalizedRight.viewportKey
    && normalizedLeft.scrollLeft === normalizedRight.scrollLeft;
}

export function buildMainTrackViewportKey(state) {
  const prefs = resolveTrackPrefs(state?.assembly?.trackView);
  // Keep existing saved pixel-scroll identities valid on first legacy migration.
  const legacyKey = [
    state?.session?.projectId || "", state?.assembly?.selectedChrName || "",
    normalizeSupportDatasetId(state?.assembly?.supportDatasetId) || "",
    prefs.supportDsCtgLen, prefs.minTickUnitKb, prefs.maxTickCount,
    prefs.alignmentLength, prefs.minIdentityPct,
  ].join(":");
  const legacySpan = prefs.minTickUnitKb * 1000 * prefs.maxTickCount;
  return prefs.visibleSpanBp === legacySpan ? legacyKey : `${legacyKey}:span:${prefs.visibleSpanBp}`;
}

export function buildSubviewTrackViewportKey(state) {
  const subview = getSubviewState(state?.assembly);
  const topSelection = normalizeSubviewSummarySelection(subview?.summary?.top);
  const bottomSelection = normalizeSubviewSummarySelection(subview?.summary?.bottom);
  return [
    state?.session?.projectId || "",
    state?.assembly?.selectedChrName || "",
    topSelection?.role || "",
    topSelection?.contigId || "",
    bottomSelection?.role || "",
    bottomSelection?.contigId || "",
  ].join(":");
}

export function buildFinalPathTrackViewportKey(state) {
  const prefs = resolveTrackPrefs(state?.assembly?.finalPathTrackView);
  return [
    state?.session?.projectId || "",
    state?.assembly?.selectedChrName || "",
    "graph",
    prefs.minTickUnitKb,
    prefs.maxTickCount,
  ].join(":");
}

export function resolvePersistedViewportScrollLeft(scrollState, viewportKey) {
  const normalizedState = normalizeViewportScrollState(scrollState);
  if (!viewportKey || normalizedState.viewportKey !== String(viewportKey)) {
    return null;
  }
  return normalizedState.scrollLeft;
}
