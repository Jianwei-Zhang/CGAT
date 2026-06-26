import {
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  buildSubviewTrackSelectionKey,
  normalizeSubviewSummarySelection,
  normalizeSubviewTrackSummary,
} from "./subview-state.js";

function normalizeAssemblyCtgIdList(values) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map((value) => normalizePositiveInt(value))
        .filter((value) => value && value > 0),
    ),
  ).sort((left, right) => left - right);
}

function buildTrackPairScopeToken(trackSummary, contigIds) {
  const normalizedTrack = normalizeSubviewTrackSummary(trackSummary);
  if (!normalizedTrack) {
    return "";
  }
  const trackKey = buildSubviewTrackSelectionKey(normalizedTrack);
  const ids = normalizeAssemblyCtgIdList(contigIds);
  return `${trackKey}:${ids.join(",")}`;
}

function resolveRequestedThresholds(trackPrefs = {}) {
  const prefs = resolveTrackPrefs(trackPrefs || {});
  return {
    minAlignmentLength: Math.max(1, normalizePositiveInt(prefs.alignmentLength) ?? 1),
    minMapq: Math.max(0, normalizeNonNegativeInt(prefs.mapq) ?? 0),
  };
}

function resolveCoverageThresholds(evidence = {}) {
  return {
    loadedMinAlignmentLength: Math.max(
      1,
      normalizePositiveInt(evidence?.loadedMinAlignmentLength ?? evidence?.minAlignmentLength) ?? Number.MAX_SAFE_INTEGER,
    ),
    loadedMinMapq: Math.max(
      0,
      normalizeNonNegativeInt(evidence?.loadedMinMapq ?? evidence?.minMapq) ?? Number.MAX_SAFE_INTEGER,
    ),
    requestedMinAlignmentLength: Math.max(
      1,
      normalizePositiveInt(evidence?.requestedMinAlignmentLength ?? evidence?.minAlignmentLength) ?? Number.MAX_SAFE_INTEGER,
    ),
    requestedMinMapq: Math.max(
      0,
      normalizeNonNegativeInt(evidence?.requestedMinMapq ?? evidence?.minMapq) ?? Number.MAX_SAFE_INTEGER,
    ),
  };
}

export function buildSubviewPairwiseEvidenceKey(summary, scope = {}) {
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    if (!topTrack || !bottomTrack || topTrack.role === "ref" || bottomTrack.role === "ref") {
      return "";
    }
    const topToken = buildTrackPairScopeToken(topTrack, scope?.topAssemblyCtgIds);
    const bottomToken = buildTrackPairScopeToken(bottomTrack, scope?.bottomAssemblyCtgIds);
    if (!topToken || !bottomToken) {
      return "";
    }
    return `track-pair:${topToken}|${bottomToken}`;
  }
  if (mode !== "2-contig") {
    return "";
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  if (!top || !bottom) {
    return "";
  }
  return `2-contig:${top.role}:${top.contigId}:${bottom.role}:${bottom.contigId}`;
}

export function shouldLoadSubviewPairwiseEvidence(summary) {
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    return Boolean(topTrack && bottomTrack && topTrack.role !== "ref" && bottomTrack.role !== "ref");
  }
  if (mode !== "2-contig") {
    return false;
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  return Boolean(top && bottom && top.role !== "ref" && bottom.role !== "ref");
}

export function shouldRefetchSubviewPairwiseEvidence({ summary, trackPrefs = {}, evidence = null, scope = {} }) {
  if (!shouldLoadSubviewPairwiseEvidence(summary)) {
    return false;
  }
  const key = buildSubviewPairwiseEvidenceKey(summary, scope);
  if (!key) {
    return false;
  }
  if (!evidence || String(evidence?.key || "") !== key) {
    return true;
  }
  const requested = resolveRequestedThresholds(trackPrefs);
  const coverage = resolveCoverageThresholds(evidence);
  if (String(evidence?.status || "") === "loading") {
    return (
      requested.minAlignmentLength < coverage.requestedMinAlignmentLength
      || requested.minMapq < coverage.requestedMinMapq
    );
  }
  if (String(evidence?.status || "") !== "loaded") {
    return true;
  }
  return (
    requested.minAlignmentLength < coverage.loadedMinAlignmentLength
    || requested.minMapq < coverage.loadedMinMapq
    || !Array.isArray(evidence?.hits)
  );
}
