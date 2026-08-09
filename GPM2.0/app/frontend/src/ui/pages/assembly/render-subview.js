import { buildDualTrackModel } from "./track-layout.js";
import {
  ALIGNMENT_LENGTH_OPTIONS,
  MAPQ_OPTIONS,
  MAX_TICK_COUNT_OPTIONS,
  MIN_TICK_UNIT_KB_OPTIONS,
  SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackInnerWidthFromScale,
  resolveTickBpFromScale,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackDragOffsets,
  normalizeTrackRole,
  normalizeTrackSelectionCtgIds,
  normalizeSubviewTrackDragOffsets,
} from "./selection-state.js";
import {
  buildRefSubviewCtgPool,
  buildSubviewFlippedCtgKey,
  buildSubviewTrackSelectionKey,
  buildSupportSubviewCtgPool,
  buildPhasedSubviewCtgPool,
  buildSubviewTrackPairHiddenCtgKey,
  buildSubviewCandidateSelectionKey,
  buildPhasedSubviewCtgHits,
  flipSubviewHitRange,
  getSubviewSelections,
  getSubviewState as getSubviewStateImpl,
  getSubviewTrackSelections,
  resolveSubviewCtgOrientValue,
  normalizeSubviewRole,
  normalizeSubviewSummarySelection,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackPairSelectionCtgs,
  normalizeSubviewTrackSelectionItem,
  normalizeSubviewTrackSource,
  normalizeSubviewTrackSummary,
  resolveSubviewSelectionCtg,
  resolveSubviewTrackSummaryCtgs,
} from "./subview-state.js";
import {
  buildSubviewAnchorEndpointKey,
  deriveSubviewContigFragments,
} from "./subview-anchor-state.js";
import {
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
  hasAdvancedSupportDsCtgLenRules,
} from "./support-ds-ctg-len-rules.js";
import { resolveSubviewAutoTrackOffsets } from "./subview-offset-state.js";
import { renderAssemblyFinalPathCard as renderAssemblyFinalPathCardImpl } from "./render-final-path.js";
import {
  buildTrackCtgHoverTitle,
  resolveBoundedTrackCtgLabelPlacement,
  resolveTrackCtgDisplayName,
  resolveTrackCtgLabelLeftBoundary,
  resolveTrackCtgLabelText,
  resolveTrackCtgLabelRightBoundary,
  resolveTrackCtgOrient,
  resolveTrackCtgVisibleName,
} from "./track-label-geometry.js";
import {
  buildEmptyTrackModelLike,
  buildCollinearityBandPoints,
  buildTrackBpX,
  buildTrackHitRect,
  buildTrackHitRectWithinCtgDisplay,
  buildTrackRect,
  buildTrackRectsWithMinGap,
  buildTrackReferenceWidth,
  buildTrackTickItems,
  isTrackTickLabelOverlap,
  renderSubviewVirtualRuler,
  resolveHitMapq,
  resolveMaxTrackEndBp,
  roundTrackMetric,
  sortTrackEntriesForRender,
} from "./track-render-geometry.js";

export const SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS = 500;
const filteredRefSubviewCtgCache = new WeakMap();
const refSubviewSegmentPairCache = new Map();

function resolveRefOverlapBpCached(leftSegment, rightSegment) {
  const leftStart = Math.min(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const leftEnd = Math.max(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const rightStart = Math.min(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const rightEnd = Math.max(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const start = Math.max(leftStart, rightStart);
  const end = Math.min(leftEnd, rightEnd);
  return Math.max(0, end - start);
}

function pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? [...topSegments] : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? [...bottomSegments] : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  safeTopSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });
  safeBottomSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });

  const pairs = [];
  let bottomWindowStart = 0;
  for (const topSegment of safeTopSegments) {
    while (
      bottomWindowStart < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomWindowStart]?.refEnd || 0) <= Number(topSegment.refStart || 0)
    ) {
      bottomWindowStart += 1;
    }
    for (
      let bottomIndex = bottomWindowStart;
      bottomIndex < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomIndex]?.refStart || 0) < Number(topSegment.refEnd || 0);
      bottomIndex += 1
    ) {
      const bottomSegment = safeBottomSegments[bottomIndex];
      if (resolveRefOverlapBpCached(topSegment, bottomSegment) <= 0) {
        continue;
      }
      pairs.push({ topSegment, bottomSegment });
    }
  }
  return pairs;
}

function pairSubviewTrackSegmentsByReferenceCached(topSegments, bottomSegments) {
  return pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments).filter(
    ({ topSegment, bottomSegment }) => {
      const overlapBp = resolveRefOverlapBpCached(topSegment, bottomSegment);
      const topSpanBp = Math.max(
        1,
        Math.abs((Number(topSegment?.refEnd) || 0) - (Number(topSegment?.refStart) || 0)),
      );
      const bottomSpanBp = Math.max(
        1,
        Math.abs((Number(bottomSegment?.refEnd) || 0) - (Number(bottomSegment?.refStart) || 0)),
      );
      const minSpanBp = Math.min(topSpanBp, bottomSpanBp);
      return overlapBp / minSpanBp >= 0.5;
    },
  );
}

function pairSubviewSegmentsByProjectionKey(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? topSegments : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? bottomSegments : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  const bottomByKey = new Map();
  safeBottomSegments.forEach((segment) => {
    const pairKey = String(segment?.pairKey || segment?.hitKey || "").trim();
    if (!pairKey) {
      return;
    }
    const current = bottomByKey.get(pairKey) || [];
    current.push(segment);
    bottomByKey.set(pairKey, current);
  });
  return safeTopSegments.flatMap((topSegment) => {
    const pairKey = String(topSegment?.pairKey || topSegment?.hitKey || "").trim();
    if (!pairKey) {
      return [];
    }
    const matches = bottomByKey.get(pairKey) || [];
    const bottomSegment = matches.shift();
    if (!bottomSegment) {
      return [];
    }
    return [{ topSegment, bottomSegment }];
  });
}

function resolveRefTrackSegmentBounds(ctg) {
  const segmentStartBp = Math.max(
    1,
    normalizePositiveInt(ctg?.segmentStartBp ?? ctg?.startBp ?? ctg?.anchorStart ?? 1) ?? 1,
  );
  const totalLength = Math.max(
    1,
    normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
  );
  const segmentEndBp = Math.max(
    segmentStartBp,
    normalizePositiveInt(ctg?.segmentEndBp ?? ctg?.endBp ?? (segmentStartBp + totalLength - 1)) ?? (segmentStartBp + totalLength - 1),
  );
  return {
    segmentStartBp,
    segmentEndBp,
    totalLength,
  };
}

function projectRefIntervalToLocalRange(ctg, refStart, refEnd) {
  const { segmentStartBp, segmentEndBp, totalLength } = resolveRefTrackSegmentBounds(ctg);
  const normalizedRefStart = Math.min(Number(refStart) || 0, Number(refEnd) || 0);
  const normalizedRefEnd = Math.max(Number(refStart) || 0, Number(refEnd) || 0);
  if (
    !Number.isFinite(normalizedRefStart)
    || !Number.isFinite(normalizedRefEnd)
    || normalizedRefEnd < segmentStartBp
    || normalizedRefStart > segmentEndBp
  ) {
    return null;
  }
  const clampedStart = Math.max(segmentStartBp, normalizedRefStart);
  const clampedEnd = Math.min(segmentEndBp, normalizedRefEnd);
  const localStart = Math.max(1, Math.min(totalLength, clampedStart - segmentStartBp + 1));
  const localEnd = Math.max(localStart, Math.min(totalLength, clampedEnd - segmentStartBp + 1));
  return {
    ctgStart: localStart,
    ctgEnd: localEnd,
  };
}

function buildProjectedRefSubviewHits(refCtg, sourceHits) {
  return (Array.isArray(sourceHits) ? sourceHits : [])
    .map((hit, index) => {
      const projectedRange = projectRefIntervalToLocalRange(
        refCtg,
        hit?.refStart,
        hit?.refEnd,
      );
      if (!projectedRange) {
        return null;
      }
      const hitKey = String(hit?.hitKey || `hit-${index + 1}`);
      const pairKey = String(hit?.pairKey || hitKey);
      return {
        ...hit,
        hitKey,
        pairKey,
        ctgStart: projectedRange.ctgStart,
        ctgEnd: projectedRange.ctgEnd,
      };
    })
    .filter(Boolean);
}

function buildSubviewPairwiseEvidenceKey(summary, scope = {}) {
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    const topIds = (Array.isArray(scope?.topAssemblyCtgIds) ? scope.topAssemblyCtgIds : [])
      .map((value) => normalizeSupportDatasetId(value))
      .filter((value) => value)
      .sort((left, right) => left - right);
    const bottomIds = (Array.isArray(scope?.bottomAssemblyCtgIds) ? scope.bottomAssemblyCtgIds : [])
      .map((value) => normalizeSupportDatasetId(value))
      .filter((value) => value)
      .sort((left, right) => left - right);
    if (!topTrack || !bottomTrack || topTrack.role === "ref" || bottomTrack.role === "ref" || !topIds.length || !bottomIds.length) {
      return "";
    }
    const topTrackKey = `${buildSubviewTrackSelectionKey(topTrack)}:${topIds.join(",")}`;
    const bottomTrackKey = `${buildSubviewTrackSelectionKey(bottomTrack)}:${bottomIds.join(",")}`;
    return `track-pair:${topTrackKey}|${bottomTrackKey}`;
  }
  if (mode !== "2-contig") {
    return "";
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  if (!top || !bottom) {
    return "";
  }
  return `2-contig:${buildSubviewCandidateSelectionKey(top)}:${buildSubviewCandidateSelectionKey(bottom)}`;
}

function isDsDsSubviewSummary(summary) {
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

function resolveSubviewPairwiseEvidence(subview, summary, scope = {}) {
  if (!isDsDsSubviewSummary(summary)) {
    return {
      enabled: false,
      key: "",
      evidence: null,
    };
  }
  const key = buildSubviewPairwiseEvidenceKey(summary, scope);
  const evidence = subview?.pairwiseEvidence || null;
  if (!evidence || String(evidence.key || "") !== key) {
    return {
      enabled: false,
      key,
      evidence: null,
    };
  }
  return {
    enabled: true,
    key,
    evidence,
  };
}

function resolvePairwiseHitTrackRanges(hit, topSelection, bottomSelection) {
  const topContigId = normalizeSupportDatasetId(topSelection?.contigId);
  const bottomContigId = normalizeSupportDatasetId(bottomSelection?.contigId);
  const queryAssemblyCtgId = normalizeSupportDatasetId(
    hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id,
  );
  const subjectAssemblyCtgId = normalizeSupportDatasetId(
    hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id,
  );
  const queryStart = Number(hit?.queryStart ?? hit?.query_start);
  const queryEnd = Number(hit?.queryEnd ?? hit?.query_end);
  const subjectStart = Number(hit?.subjectStart ?? hit?.subject_start);
  const subjectEnd = Number(hit?.subjectEnd ?? hit?.subject_end);
  if (
    !topContigId
    || !bottomContigId
    || !queryAssemblyCtgId
    || !subjectAssemblyCtgId
    || !Number.isFinite(queryStart)
    || !Number.isFinite(queryEnd)
    || !Number.isFinite(subjectStart)
    || !Number.isFinite(subjectEnd)
  ) {
    return null;
  }
  if (queryAssemblyCtgId === topContigId && subjectAssemblyCtgId === bottomContigId) {
    return {
      topStart: queryStart,
      topEnd: queryEnd,
      bottomStart: subjectStart,
      bottomEnd: subjectEnd,
    };
  }
  if (queryAssemblyCtgId === bottomContigId && subjectAssemblyCtgId === topContigId) {
    return {
      topStart: subjectStart,
      topEnd: subjectEnd,
      bottomStart: queryStart,
      bottomEnd: queryEnd,
    };
  }
  return null;
}

function resolvePairwiseHitDisplayReversed(hit) {
  const strand = String(hit?.strand || "").trim();
  return strand === "-";
}

function resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topFlipped, bottomFlipped) {
  let reversed = resolvePairwiseHitDisplayReversed(hit);
  if (topFlipped === true) {
    reversed = !reversed;
  }
  if (bottomFlipped === true) {
    reversed = !reversed;
  }
  return reversed;
}

function isSubviewRenderableContigLocallyFlipped(ctg) {
  return ctg?.subviewLocallyFlipped === true;
}

function isSubviewPairwiseRangeMirrored(ctg) {
  return Boolean(ctg?.subviewPhasedOrientFlipped) !== isSubviewRenderableContigLocallyFlipped(ctg);
}

function resolveSubviewPairwiseCtgLengthBp(ctg) {
  const candidates = [
    ctg?.lengthBp,
    ctg?.totalLength,
    ctg?.length,
  ];
  for (const candidate of candidates) {
    const parsed = normalizePositiveInt(candidate);
    if (parsed && parsed > 0) {
      return parsed;
    }
  }
  return 1;
}

function resolveSubviewPairwiseDisplayRange(start, end, ctg, flipped) {
  const numericStart = Number(start);
  const numericEnd = Number(end);
  if (!Number.isFinite(numericStart) || !Number.isFinite(numericEnd)) {
    return null;
  }
  if (flipped !== true) {
    return { start: numericStart, end: numericEnd };
  }
  const totalLength = Math.max(1, resolveSubviewPairwiseCtgLengthBp(ctg));
  return {
    start: totalLength - numericEnd + 1,
    end: totalLength - numericStart + 1,
  };
}

function buildSubviewPairwiseRenderableHits({
  evidence,
  topSelection,
  bottomSelection,
  topCtg,
  bottomCtg,
  blockLength,
  minMapq,
}) {
  if (normalizeSupportDatasetId(topSelection?.contigId) === normalizeSupportDatasetId(bottomSelection?.contigId)) {
    return { topHits: [], bottomHits: [] };
  }
  const topHits = [];
  const bottomHits = [];
  const topMirrored = isSubviewPairwiseRangeMirrored(topCtg);
  const bottomMirrored = isSubviewPairwiseRangeMirrored(bottomCtg);
  const hits = Array.isArray(evidence?.hits) ? evidence.hits : [];
  hits.forEach((hit, index) => {
    const alignLength = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
    const mapq = Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
    if (alignLength < blockLength || mapq < minMapq) {
      return;
    }
    const ranges = resolvePairwiseHitTrackRanges(hit, topSelection, bottomSelection);
    if (!ranges) {
      return;
    }
    const topRange = resolveSubviewPairwiseDisplayRange(
      ranges.topStart,
      ranges.topEnd,
      topCtg,
      topMirrored,
    );
    const bottomRange = resolveSubviewPairwiseDisplayRange(
      ranges.bottomStart,
      ranges.bottomEnd,
      bottomCtg,
      bottomMirrored,
    );
    if (!topRange || !bottomRange) {
      return;
    }
    const pairOrdinal = index + 1;
    const pairKey = `pairwise-${pairOrdinal}`;
    const hitKey = String(hit?.hitKey || pairKey);
    const reversed = resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topMirrored, bottomMirrored);
    const refStart = pairOrdinal;
    const refEnd = pairOrdinal + 1;
    topHits.push({
      hitKey,
      pairKey,
      reversed,
      ctgStart: Math.min(topRange.start, topRange.end),
      ctgEnd: Math.max(topRange.start, topRange.end),
      refStart,
      refEnd,
      refMid: (refStart + refEnd) / 2,
    });
    bottomHits.push({
      hitKey,
      pairKey,
      reversed,
      ctgStart: Math.min(bottomRange.start, bottomRange.end),
      ctgEnd: Math.max(bottomRange.start, bottomRange.end),
      refStart,
      refEnd,
      refMid: (refStart + refEnd) / 2,
    });
  });
  return { topHits, bottomHits };
}

function resolveSubviewRefDatasetId(subview, supportContext = {}) {
  const summary = subview?.summary || null;
  if (!summary) {
    return null;
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const tracks = [summary?.topTrack, summary?.bottomTrack]
      .map((track) => normalizeSubviewTrackSummary(track))
      .filter(Boolean);
    const nonRefTrack = tracks.find((track) => track.role !== "ref");
    if (!nonRefTrack) {
      return null;
    }
    if (nonRefTrack.role === "primary") {
      return normalizeSupportDatasetId(supportContext?.primaryDatasetId);
    }
    return normalizeSupportDatasetId(nonRefTrack.datasetId);
  }
  const selections = [summary?.top, summary?.bottom]
    .map((selection) => normalizeSubviewSummarySelection(selection))
    .filter(Boolean);
  const nonRefSelection = selections.find((selection) => selection.role !== "ref");
  if (!nonRefSelection) {
    return null;
  }
  if (nonRefSelection.role === "primary") {
    return normalizeSupportDatasetId(supportContext?.primaryDatasetId);
  }
  const matchedSupportCtg = resolveSubviewSelectionCtg(nonRefSelection, supportContext);
  return normalizeSupportDatasetId(
    matchedSupportCtg?.datasetId ?? supportContext?.supportDatasetId ?? null,
  );
}

function buildSubviewRefCacheSelectionKey(summary) {
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    return [
      "track-pair",
      topTrack
        ? [topTrack.role, topTrack.source, normalizeSupportDatasetId(topTrack.datasetId) || 0, topTrack.isMirror ? 1 : 0].join(":")
        : "",
      bottomTrack
        ? [bottomTrack.role, bottomTrack.source, normalizeSupportDatasetId(bottomTrack.datasetId) || 0, bottomTrack.isMirror ? 1 : 0].join(":")
        : "",
    ].join("|");
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  return [
    "2-contig",
    top ? `${top.role}:${top.contigId}` : "",
    bottom ? `${bottom.role}:${bottom.contigId}` : "",
  ].join("|");
}

export function getCachedFilteredRefSubviewCtgs({
  refTrackMembers,
  subview,
  supportContext = {},
}) {
  const list = Array.isArray(refTrackMembers) ? refTrackMembers : [];
  const datasetId = resolveSubviewRefDatasetId(subview, supportContext);
  const selectionKey = buildSubviewRefCacheSelectionKey(subview?.summary || null);
  const cacheKey = `${String(supportContext?.refTrackLabel || supportContext?.selectedChrName || "")}|${selectionKey}|${normalizeSupportDatasetId(datasetId) || 0}`;
  let cacheBySelection = filteredRefSubviewCtgCache.get(list);
  if (!cacheBySelection) {
    cacheBySelection = new Map();
    filteredRefSubviewCtgCache.set(list, cacheBySelection);
  }
  if (cacheBySelection.has(cacheKey)) {
    return cacheBySelection.get(cacheKey);
  }
  const value = buildRefSubviewCtgPool(list, { datasetId });
  cacheBySelection.set(cacheKey, value);
  return value;
}

function buildSubviewSegmentSignature(segments) {
  return (Array.isArray(segments) ? segments : [])
    .map((segment) => [
      normalizeSupportDatasetId(segment?.ctgId) || 0,
      String(segment?.hitKey || ""),
      Number(segment?.refStart || 0),
      Number(segment?.refEnd || 0),
      Number(segment?.ctgStart || 0),
      Number(segment?.ctgEnd || 0),
      Number(segment?.x || 0),
      Number(segment?.width || 0),
    ].join(":"))
    .join("|");
}

function pairRefSubviewSegmentsWithCache({
  cacheKey,
  topSegments,
  bottomSegments,
  trackMode = "2-contig",
  pairingMode = "reference-overlap",
}) {
  if (pairingMode === "projection-key") {
    return pairSubviewSegmentsByProjectionKey(topSegments, bottomSegments);
  }
  const pairCacheKey = [
    trackMode,
    String(cacheKey || ""),
    buildSubviewSegmentSignature(topSegments),
    buildSubviewSegmentSignature(bottomSegments),
  ].join("::");
  if (refSubviewSegmentPairCache.has(pairCacheKey)) {
    return refSubviewSegmentPairCache.get(pairCacheKey);
  }
  const value = trackMode === "track-pair"
    ? pairSubviewTrackSegmentsByReferenceCached(topSegments, bottomSegments)
    : pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments);
  refSubviewSegmentPairCache.set(pairCacheKey, value);
  return value;
}

export function __testBuildFilteredRefSubviewCtgs(args) {
  return getCachedFilteredRefSubviewCtgs(args);
}

export function __testPairRefSubviewSegmentsWithCache(args) {
  return pairRefSubviewSegmentsWithCache(args);
}

export function getSubviewSlotToken(subview, role, contigId) {
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  const normalizedRole = normalizeSubviewRole(role);
  if (!normalizedContigId || !normalizedRole) {
    return "";
  }
  const selections = getSubviewSelections(subview);
  const matchedIndex = selections.findIndex(
    (selection) =>
      Number(selection.contigId) === Number(normalizedContigId) && selection.role === normalizedRole,
  );
  if (matchedIndex < 0) {
    return "";
  }
  return matchedIndex === 0 ? "A" : "B";
}

export function createAssemblySubviewRenderer(deps = {}) {
  const {
    escapeAttr,
    escapeHtml,
    formatBpInterval,
    getMeasuredTrackViewportPx,
    renderTrackNumberInput,
    resolveSubviewTrackDragOffsetPx,
    resolveSubviewTrackSelectionLabel,
    resolveTrackToneClass,
  } = deps;
  if (
    typeof escapeAttr !== "function"
    || typeof escapeHtml !== "function"
    || typeof formatBpInterval !== "function"
    || typeof getMeasuredTrackViewportPx !== "function"
    || typeof renderTrackNumberInput !== "function"
    || typeof resolveSubviewTrackDragOffsetPx !== "function"
    || typeof resolveSubviewTrackSelectionLabel !== "function"
    || typeof resolveTrackToneClass !== "function"
  ) {
    throw new Error("render-subview.js missing required render dependencies");
  }

function renderSubviewSelectionPanel(assembly, supportContext, trackPrefs, i18n) {
  const subview = getSubviewStateImpl(assembly);
  const candidates = getSubviewSelections(subview);
  const trackSelections = getSubviewTrackSelections(subview);
  const candidateBadges = candidates
    .map((selection, index) => {
      const slot = index === 0 ? "A" : "B";
      const resolvedCtg = resolveSubviewSelectionCtg(selection, supportContext);
      const ctgName = resolveTrackCtgDisplayName(resolvedCtg, selection.contigId);
      const visibleCtgName = resolveTrackCtgVisibleName(resolvedCtg, selection.contigId);
      const roleLabel = selection.role === "support"
        ? i18n.trackControls.supportDataset
        : selection.role === "ref"
          ? String(supportContext?.refTrackLabel || "ref")
          : selection.role === "phased"
            ? i18n.trackControls.phasedTrackLabel.replace(
              "{key}",
              String(selection.phasedHaplotypeKey || resolvedCtg?.phasedHaplotypeKey || "").trim() || "phased",
            )
            : i18n.trackControls.primaryTrackLabel;
      const phasedRemoveAttrs = selection.role === "phased"
        ? ` data-subview-remove-phased-track-id="${Number(selection.phasedTrackId || 0)}" data-subview-remove-phased-track-item-id="${Number(selection.phasedTrackItemId || 0)}" data-subview-remove-phased-haplotype-key="${escapeAttr(selection.phasedHaplotypeKey || "")}"`
        : "";
      return `<span class="subview-candidate-badge" title="${escapeAttr(ctgName)}"><strong>${slot}</strong>${escapeHtml(visibleCtgName)} · ${escapeHtml(roleLabel)}<button type="button" class="subview-candidate-remove" data-subview-remove-type="candidate" data-subview-remove-role="${escapeAttr(selection.role)}" data-subview-remove-contig-id="${selection.contigId}"${phasedRemoveAttrs} aria-label="${escapeAttr(i18n.subview.removeCandidateAria)}" title="${escapeAttr(i18n.subview.removeCandidateAria)}">&times;</button></span>`;
    })
    .join("");
  const trackBadges = trackSelections
    .map((selection, index) => {
      const slot = index === 0 ? "T1" : "T2";
      return `<span class="subview-candidate-badge"><strong>${slot}</strong>${escapeHtml(
        resolveSubviewTrackSelectionLabel(selection, supportContext, i18n),
      )}<button type="button" class="subview-candidate-remove" data-subview-remove-type="track" data-subview-remove-role="${escapeAttr(selection.role)}" data-subview-remove-source="${escapeAttr(selection.source || "mother")}" data-subview-remove-dataset-id="${Number(selection.datasetId || 0)}" data-subview-remove-is-mirror="${selection.isMirror ? "1" : "0"}" aria-label="${escapeAttr(i18n.subview.removeTrackCandidateAria)}" title="${escapeAttr(i18n.subview.removeTrackCandidateAria)}">&times;</button></span>`;
    })
    .join("");
  const allBadges = `${candidateBadges}${trackBadges}`;
  const sameContigWarning = resolveSubviewPanelSameContigWarningText(subview, supportContext, i18n);
  return `
    <article class="card subview-selection-panel" data-subview-panel="1">
      <div class="subview-panel-head">
        <h4>${escapeHtml(i18n.subview.panelTitle)}${sameContigWarning ? ` <span class="subview-same-contig-warning">${escapeHtml(sameContigWarning)}</span>` : ""}</h4>
        <div class="subview-panel-guide-inline">
          <p class="muted">${escapeHtml(i18n.subview.guide)}</p>
          ${
            allBadges
              ? `<div class="subview-candidate-row">${allBadges}</div>`
              : ""
          }
        </div>
      </div>
      ${subview.error ? `<p class="error-text">${escapeHtml(subview.error)}</p>` : ""}
      ${renderSubviewAlignmentCard(subview, supportContext, trackPrefs, assembly?.subviewTrackDragOffsets, i18n)}
    </article>
  `;
}

function renderSubviewTrackInlineControls(trackPrefs, i18n) {
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "subview-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs?.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "subview-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs?.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "subview-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs?.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "subview-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs?.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  return `
    <div class="assembly-track-inline-controls subview-track-inline-controls" role="group" aria-label="${escapeAttr(i18n.subview.trackControlsAria)}">
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.minTickUnitKb)}</span>
        ${minTickUnitInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.maxTickCount)}</span>
        ${maxTickCountInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</span>
        ${alignmentInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.mapq)}</span>
        ${mapqInput}
      </label>
    </div>
  `;
}

function renderSubviewTrackOrderToggleButton({ className = "", style = "", swapTrackOrderLabel = "" } = {}) {
  const resolvedClassName = String(className || "").trim();
  const resolvedStyle = String(style || "").trim();
  return `
    <button
      type="button"
      class="button ghost tiny subview-track-order-toggle${resolvedClassName ? ` ${resolvedClassName}` : ""}"
      data-subview-action="swap-track-order"
      aria-label="${escapeAttr(swapTrackOrderLabel)}"
      title="${escapeAttr(swapTrackOrderLabel)}"
      ${resolvedStyle ? `style="${escapeAttr(resolvedStyle)}"` : ""}
    >⇅</button>
  `;
}

function buildSubviewActiveAnchorKeySet(activeAnchors) {
  const keys = new Set();
  (Array.isArray(activeAnchors) ? activeAnchors : []).forEach((anchor) => {
    const hitKey = String(anchor?.hitKey || "").trim();
    const edge = String(anchor?.edge || "").trim();
    if (!hitKey || !edge) {
      return;
    }
    keys.add(`${hitKey}:${edge}`);
    const match = hitKey.match(/^pair:([^:]*):([^:]*):([^:]*):([^:]*)$/);
    if (match) {
      keys.add(`pair:${match[3]}:${match[4]}:${match[1]}:${match[2]}:${edge}`);
    }
  });
  return keys;
}

function buildSubviewFlippedCtgKeySet(flippedCtgs) {
  return new Set(
    (Array.isArray(flippedCtgs) ? flippedCtgs : []).map((entry) =>
      buildSubviewFlippedCtgKey(entry?.slot, entry?.contigId),
    ).filter(Boolean),
  );
}

function buildSubviewLocallyFlippedContig(ctg) {
  const totalLength = Math.max(
    1,
    normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
  );
  const flippedHits = (Array.isArray(ctg?.hits) ? ctg.hits : []).map((hit) => ({
    ...hit,
    ...flipSubviewHitRange(hit, totalLength, "ctgStart", "ctgEnd"),
    ...flipSubviewHitRange(hit, totalLength, "ctg_start", "ctg_end"),
    ...flipSubviewHitRange(hit, totalLength, "queryStart", "queryEnd"),
    ...flipSubviewHitRange(hit, totalLength, "query_start", "query_end"),
    ...flipSubviewHitRange(hit, totalLength, "hitStart", "hitEnd"),
    ...flipSubviewHitRange(hit, totalLength, "hit_start", "hit_end"),
  }));
  const nextOrient = resolveTrackCtgOrient(ctg) === "-" ? "+" : "-";
  return {
    ...ctg,
    subviewLocallyFlipped: true,
    orient: nextOrient,
    refOrient: nextOrient,
    ref_orient: nextOrient,
    hits: flippedHits,
  };
}

function resolveTrackRenderableHits(ctg) {
  // Main-track hits from list_chr_view_ctgs are already projected into ctg display coordinates.
  return Array.isArray(ctg?.hits) ? ctg.hits : [];
}

function resolveTrackHitStrand(hit) {
  const strand = String(hit?.strand || "").trim();
  return strand === "-" || strand === "+" ? strand : "";
}

function resolveTrackHitDisplayReversed(ctg, hit) {
  const hitStrand = resolveTrackHitStrand(hit);
  if (!hitStrand) {
    return false;
  }
  return resolveTrackCtgOrient(ctg) !== hitStrand;
}

function resolveSubviewRenderableContig(ctg, flippedKeySet, slot) {
  const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
  if (!contigId || !(flippedKeySet instanceof Set)) {
    return ctg;
  }
  return flippedKeySet.has(buildSubviewFlippedCtgKey(slot, contigId))
    ? buildSubviewLocallyFlippedContig(ctg)
    : ctg;
}

function resolveSubviewSameContigWarningText(topContigIds, bottomContigIds, i18n) {
  const topIds = new Set(
    (Array.isArray(topContigIds) ? topContigIds : [])
      .map((contigId) => normalizeSupportDatasetId(contigId))
      .filter(Boolean),
  );
  if (!topIds.size) {
    return "";
  }
  for (const contigId of (Array.isArray(bottomContigIds) ? bottomContigIds : [])
    .map((value) => normalizeSupportDatasetId(value))
    .filter(Boolean)) {
    if (topIds.has(contigId)) {
      return i18n?.subview?.sameContigSkippedHint || "";
    }
  }
  return "";
}

function resolveSubviewPanelSameContigWarningText(subview, supportContext, i18n) {
  const summary = subview?.summary || null;
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    if (!topTrack || !bottomTrack) {
      return "";
    }
    return resolveSubviewSameContigWarningText(
      (resolveSubviewTrackSummaryCtgs(topTrack, supportContext) || []).map((ctg) => ctg?.assemblyCtgId),
      (resolveSubviewTrackSummaryCtgs(bottomTrack, supportContext) || []).map((ctg) => ctg?.assemblyCtgId),
      i18n,
    );
  }
  const topSelection = normalizeSubviewSummarySelection(summary?.top);
  const bottomSelection = normalizeSubviewSummarySelection(summary?.bottom);
  if (!topSelection || !bottomSelection) {
    return "";
  }
  return resolveSubviewSameContigWarningText(
    [topSelection.contigId],
    [bottomSelection.contigId],
    i18n,
  );
}

function buildSubviewActiveAnchorCutsByContig(anchorEdges) {
  const cutsByContig = new Map();
  (Array.isArray(anchorEdges) ? anchorEdges : [])
    .filter((edge) => edge?.active)
    .forEach((edge) => {
      const topContigId = normalizeSupportDatasetId(edge?.topContigId);
      const bottomContigId = normalizeSupportDatasetId(edge?.bottomContigId);
      const topCutBp = normalizePositiveInt(edge?.topCutBp);
      const bottomCutBp = normalizePositiveInt(edge?.bottomCutBp);
      if (topContigId && topCutBp) {
        const current = cutsByContig.get(topContigId) || [];
        cutsByContig.set(topContigId, [...current, topCutBp]);
      }
      if (bottomContigId && bottomCutBp) {
        const current = cutsByContig.get(bottomContigId) || [];
        cutsByContig.set(bottomContigId, [...current, bottomCutBp]);
      }
    });
  return cutsByContig;
}

function resolveSubviewAnchorEndpointX({ barX, barWidth, lengthBp, cutBp }) {
  const safeLengthBp = Math.max(1, normalizePositiveInt(lengthBp) ?? 1);
  const normalizedCutBp = Math.max(1, Math.min(safeLengthBp, Number(cutBp || 1)));
  return Number(barX || 0) + Number(barWidth || 0) * ((normalizedCutBp - 1) / safeLengthBp);
}

function buildSubviewManualAnchorEdges(manualAnchors, { topEndpoint, bottomEndpoint }) {
  if (!topEndpoint?.endpointKey || !bottomEndpoint?.endpointKey) {
    return [];
  }
  return (Array.isArray(manualAnchors) ? manualAnchors : []).flatMap((anchor) => {
    const endpointA = anchor?.endpointA || null;
    const endpointB = anchor?.endpointB || null;
    const topManualEndpoint = endpointA?.endpointKey === topEndpoint.endpointKey
      ? endpointA
      : endpointB?.endpointKey === topEndpoint.endpointKey
        ? endpointB
        : null;
    const bottomManualEndpoint = endpointA?.endpointKey === bottomEndpoint.endpointKey
      ? endpointA
      : endpointB?.endpointKey === bottomEndpoint.endpointKey
        ? endpointB
        : null;
    const topCutBp = normalizePositiveInt(topManualEndpoint?.cutBp);
    const bottomCutBp = normalizePositiveInt(bottomManualEndpoint?.cutBp);
    if (!topManualEndpoint || !bottomManualEndpoint || !topCutBp || !bottomCutBp) {
      return [];
    }
    return [{
      manualAnchorId: String(anchor?.manualAnchorId || "").trim(),
      hitKey: String(anchor?.manualAnchorId || "").trim(),
      edge: "manual",
      active: true,
      topX: topEndpoint.xForCut(topCutBp),
      bottomX: bottomEndpoint.xForCut(bottomCutBp),
      topY: topEndpoint.topY,
      bottomY: bottomEndpoint.bottomY,
      hitTopY: topEndpoint.hitY,
      hitBottomY: bottomEndpoint.hitY,
      topContigId: topEndpoint.contigId,
      bottomContigId: bottomEndpoint.contigId,
      topEndpointKey: topEndpoint.endpointKey,
      bottomEndpointKey: bottomEndpoint.endpointKey,
      topCutBp,
      bottomCutBp,
      topLengthBp: topEndpoint.lengthBp,
      bottomLengthBp: bottomEndpoint.lengthBp,
    }];
  }).filter((edge) => edge.manualAnchorId);
}

function buildSubviewManualAnchorEdgesFromEndpointMaps(manualAnchors, { topEndpointsByKey, bottomEndpointsByKey }) {
  const topMap = topEndpointsByKey instanceof Map ? topEndpointsByKey : new Map();
  const bottomMap = bottomEndpointsByKey instanceof Map ? bottomEndpointsByKey : new Map();
  return (Array.isArray(manualAnchors) ? manualAnchors : []).flatMap((anchor) => {
    const endpointA = anchor?.endpointA || null;
    const endpointB = anchor?.endpointB || null;
    const topManualEndpoint = topMap.has(endpointA?.endpointKey)
      ? endpointA
      : topMap.has(endpointB?.endpointKey)
        ? endpointB
        : null;
    const bottomManualEndpoint = bottomMap.has(endpointA?.endpointKey)
      ? endpointA
      : bottomMap.has(endpointB?.endpointKey)
        ? endpointB
        : null;
    if (!topManualEndpoint || !bottomManualEndpoint) {
      return [];
    }
    const topEndpoint = topMap.get(topManualEndpoint.endpointKey);
    const bottomEndpoint = bottomMap.get(bottomManualEndpoint.endpointKey);
    return buildSubviewManualAnchorEdges([anchor], { topEndpoint, bottomEndpoint });
  });
}

function buildSubviewFragmentRects({
  fragments,
  slot,
  role,
  barX,
  barY,
  barWidth,
  barHeight,
  ctgLengthBp,
  ctgName,
  contigId,
  datasetId,
  isMirror,
  refOrient,
  sourceKind,
  referenceChrId,
  referenceChrName,
  segmentStartBp,
  segmentEndBp,
  phasedTrackId,
  phasedTrackItemId,
  phasedHaplotypeKey,
}) {
  return fragments.map((fragment) => {
    const safeLengthBp = Math.max(1, Number(ctgLengthBp || 0));
    const fragmentStart = normalizePositiveInt(fragment.start) || 1;
    const fragmentEnd = normalizePositiveInt(fragment.end) || fragmentStart;
    const fragmentLengthBp = Math.max(0, fragmentEnd - fragmentStart + 1);
    const hoverTitle = buildTrackCtgHoverTitle(ctgName, {
      startBp: fragmentStart,
      lengthBp: fragmentLengthBp,
    });
    const startRatio = Math.max(0, (Number(fragment.start || 1) - 1) / safeLengthBp);
    const endRatio = Math.max(startRatio, Number(fragment.end || 0) / safeLengthBp);
    const x = Number(barX || 0) + Number(barWidth || 0) * startRatio;
    const right = Number(barX || 0) + Number(barWidth || 0) * endRatio;
    const width = Math.max(1, right - x);
    return `
              <rect
                class="subview-fragment-hit-zone"
                x="${x.toFixed(2)}"
                y="${Number(barY || 0).toFixed(2)}"
                width="${width.toFixed(2)}"
                height="${Number(barHeight || 0).toFixed(2)}"
                fill="transparent"
                data-subview-fragment-key="${escapeAttr(fragment.fragmentKey)}"
                data-subview-fragment-slot="${escapeAttr(slot)}"
                data-subview-fragment-role="${escapeAttr(role)}"
                data-subview-fragment-contig-id="${contigId}"
                data-subview-fragment-start="${fragment.start}"
                data-subview-fragment-end="${fragment.end}"
                data-subview-fragment-ctg-name="${escapeAttr(ctgName)}"
                data-subview-fragment-dataset-id="${Number(datasetId || 0)}"
                data-subview-fragment-is-mirror="${isMirror ? "1" : "0"}"
                data-subview-fragment-ref-orient="${escapeAttr(refOrient || "+")}"
                data-subview-fragment-source-kind="${escapeAttr(sourceKind || "assembly_ctg")}"
                data-subview-fragment-reference-chr-id="${Number(referenceChrId || 0)}"
                data-subview-fragment-reference-chr-name="${escapeAttr(referenceChrName || "")}"
                data-subview-fragment-segment-start-bp="${Number(segmentStartBp || 0)}"
                data-subview-fragment-segment-end-bp="${Number(segmentEndBp || 0)}"
                data-subview-fragment-phased-track-id="${Number(phasedTrackId || 0)}"
                data-subview-fragment-phased-track-item-id="${Number(phasedTrackItemId || 0)}"
                data-subview-fragment-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey || "")}"
              >
                <title>${escapeHtml(hoverTitle)}</title>
              </rect>
              <rect
                class="subview-fragment-outline"
                x="${x.toFixed(2)}"
                y="${Number(barY || 0).toFixed(2)}"
                width="${width.toFixed(2)}"
                height="${Number(barHeight || 0).toFixed(2)}"
                rx="4"
                ry="4"
                fill="none"
                stroke="transparent"
                stroke-width="2.5"
                pointer-events="none"
              />`;
  }).join("");
}

function renderSubviewAnchorLines(anchorEdges, { topY, bottomY, hitTopY, hitBottomY }) {
  return (Array.isArray(anchorEdges) ? anchorEdges : [])
    .map(
      (edge) => {
        const anchorKind = edge.manualAnchorId ? "manual" : "evidence";
        const anchorEdge = edge.manualAnchorId ? "manual" : String(edge.edge || "");
        return `<line
                  class="subview-anchor-line${edge.active ? " is-active" : ""}"
                  x1="${Number(edge.topX || 0).toFixed(2)}"
                  y1="${Number(hitTopY ?? edge.hitTopY ?? edge.topY ?? topY ?? 0).toFixed(2)}"
                  x2="${Number(edge.bottomX || 0).toFixed(2)}"
                  y2="${Number(hitBottomY ?? edge.hitBottomY ?? edge.bottomY ?? bottomY ?? 0).toFixed(2)}"
                  stroke="${edge.active ? "red" : "transparent"}"
                  stroke-width="3"
                  pointer-events="none"
                />
                <line
                  class="subview-anchor-hit-zone${edge.active ? " is-active" : ""}"
                  x1="${Number(edge.topX || 0).toFixed(2)}"
                  y1="${Number(hitTopY ?? edge.hitTopY ?? edge.topY ?? topY ?? 0).toFixed(2)}"
                  x2="${Number(edge.bottomX || 0).toFixed(2)}"
                  y2="${Number(hitBottomY ?? edge.hitBottomY ?? edge.bottomY ?? bottomY ?? 0).toFixed(2)}"
                  stroke="transparent"
                  stroke-width="3"
                  pointer-events="stroke"
                  data-subview-anchor-kind="${anchorKind}"
                  data-subview-anchor-hit-key="${escapeAttr(edge.hitKey)}"
                  data-subview-anchor-edge="${escapeAttr(anchorEdge)}"
                  data-subview-anchor-active="${edge.active ? "1" : "0"}"
                  data-subview-manual-anchor-id="${escapeAttr(edge.manualAnchorId || "")}"
                  data-subview-anchor-top-endpoint-key="${escapeAttr(edge.topEndpointKey || "")}"
                  data-subview-anchor-bottom-endpoint-key="${escapeAttr(edge.bottomEndpointKey || "")}"
                  data-subview-anchor-top-contig-id="${Number(edge.topContigId || 0)}"
                  data-subview-anchor-bottom-contig-id="${Number(edge.bottomContigId || 0)}"
                  data-subview-anchor-top-cut-bp="${Number(edge.topCutBp || 0)}"
                  data-subview-anchor-bottom-cut-bp="${Number(edge.bottomCutBp || 0)}"
                  data-subview-anchor-top-length-bp="${Number(edge.topLengthBp || 0)}"
                  data-subview-anchor-bottom-length-bp="${Number(edge.bottomLengthBp || 0)}"
                  data-subview-anchor-top-x="${Number(edge.topX || 0).toFixed(4)}"
                  data-subview-anchor-bottom-x="${Number(edge.bottomX || 0).toFixed(4)}"
                />`;
      },
    )
    .join("");
}

function parseTrackBandPoints(pointsText) {
  return String(pointsText || "")
    .trim()
    .split(/\s+/)
    .map((point) => {
      const [rawX = "", rawY = ""] = String(point || "").split(",");
      const x = Number(rawX);
      const y = Number(rawY);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        return null;
      }
      return [roundTrackMetric(x), roundTrackMetric(y)];
    })
    .filter(Boolean);
}

function stringifyTrackBandCanvasScene(scene) {
  return JSON.stringify(scene).replaceAll("</", "<\\/");
}

function renderTrackBandCanvasLayer({
  sceneKind,
  width,
  height,
  viewBoxMinX = 0,
  clipRect = null,
  bands = [],
}) {
  const scene = {
    version: 1,
    kind: String(sceneKind || "").trim() || "track",
    width: roundTrackMetric(width),
    height: roundTrackMetric(height),
    viewBoxMinX: roundTrackMetric(viewBoxMinX),
    clipRect: clipRect
      ? {
          x: roundTrackMetric(clipRect.x),
          y: roundTrackMetric(clipRect.y),
          width: roundTrackMetric(clipRect.width),
          height: roundTrackMetric(clipRect.height),
        }
      : null,
    bands: (Array.isArray(bands) ? bands : [])
      .map((band) => {
        const points = parseTrackBandPoints(band?.points);
        if (points.length < 4) {
          return null;
        }
        return {
          hitKey: String(band?.hitKey || ""),
          tone: String(band?.tone || "").trim() || "primary",
          points,
        };
      })
      .filter(Boolean),
  };
  return `
    <div
      class="track-band-canvas-layer"
      data-track-band-canvas-layer="1"
      data-track-band-canvas-scene-kind="${escapeAttr(scene.kind)}"
      style="width:${scene.width.toFixed(2)}px;height:${scene.height.toFixed(2)}px"
      aria-hidden="true"
    >
      <canvas class="track-band-canvas" data-track-band-canvas="1"></canvas>
      <script type="application/json" data-track-band-canvas-scene>${escapeHtml(stringifyTrackBandCanvasScene(scene))}</script>
    </div>
  `;
}

function resolveSubviewSegmentCtgBpByRef(segment, refBp) {
  const refStart = Number(segment?.refStart || 0);
  const refEnd = Number(segment?.refEnd || 0);
  const ctgStart = Number(segment?.ctgStart || 0);
  const ctgEnd = Number(segment?.ctgEnd || 0);
  if (!Number.isFinite(refStart) || !Number.isFinite(refEnd) || !Number.isFinite(ctgStart) || !Number.isFinite(ctgEnd)) {
    return null;
  }
  const safeRefSpan = Math.max(1, refEnd - refStart);
  const clampedRefBp = Math.max(refStart, Math.min(refEnd, Number(refBp || 0)));
  const ratio = (clampedRefBp - refStart) / safeRefSpan;
  const ctgValue = ctgStart + ratio * (ctgEnd - ctgStart);
  const normalized = Math.round(ctgValue);
  return normalized > 0 ? normalized : null;
}

function renderSubviewAlignmentCard(subview, supportContext, trackPrefs, subviewTrackDragOffsets = [], i18n) {
  const summary = subview?.summary || null;
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "") === "track-pair") {
    return renderSubviewTrackPairAlignmentCard(
      subview,
      supportContext,
      trackPrefs,
      subviewTrackDragOffsets,
      i18n,
    );
  }
  const topSelection = normalizeSubviewSummarySelection(summary.top);
  const bottomSelection = normalizeSubviewSummarySelection(summary.bottom);
  if (!topSelection || !bottomSelection) {
    return "";
  }
  const flippedKeySet = buildSubviewFlippedCtgKeySet(subview?.flippedCtgs);
  const topCtg = resolveSubviewRenderableContig(
    resolveSubviewSelectionCtg(topSelection, supportContext),
    flippedKeySet,
    "top",
  );
  const bottomCtg = resolveSubviewRenderableContig(
    resolveSubviewSelectionCtg(bottomSelection, supportContext),
    flippedKeySet,
    "bottom",
  );
  if (!topCtg || !bottomCtg) {
    return `<article class="assembly-track-panel subview-alignment-card"><p class="muted">${escapeHtml(i18n.subview.invalidCandidate)}</p></article>`;
  }
  const resolvedTrackPrefs = resolveTrackPrefs(trackPrefs || {});
  const blockLength = Math.max(1, normalizePositiveInt(resolvedTrackPrefs.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(resolvedTrackPrefs.mapq) ?? 0);
  const activeAnchorHitKeys = new Set(
    (Array.isArray(subview?.activeAnchors) ? subview.activeAnchors : [])
      .map((entry) => String(entry?.hitKey || "").trim())
      .filter(Boolean),
  );
  const topHits = collectSubviewRenderableHits(topCtg, {
    blockLength,
    minMapq,
    preserveHitKeys: activeAnchorHitKeys,
  });
  const bottomHits = collectSubviewRenderableHits(bottomCtg, {
    blockLength,
    minMapq,
    preserveHitKeys: activeAnchorHitKeys,
  });
  const usesRefProjection =
    (topSelection.role === "ref" && bottomSelection.role !== "ref")
    || (bottomSelection.role === "ref" && topSelection.role !== "ref");
  const pairwiseEvidenceState = resolveSubviewPairwiseEvidence(subview, summary);
  const isPairwiseEvidenceLoading =
    pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loading";
  const pairwiseHits = pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loaded"
    ? buildSubviewPairwiseRenderableHits({
      evidence: pairwiseEvidenceState.evidence,
      topSelection,
      bottomSelection,
      topCtg,
      bottomCtg,
      blockLength,
      minMapq,
    })
    : null;
  const resolvedTopHits = pairwiseEvidenceState.enabled
    ? pairwiseHits?.topHits || []
    : usesRefProjection
      ? topSelection.role === "ref"
        ? buildProjectedRefSubviewHits(topCtg, bottomHits)
        : topHits
      : topHits;
  const resolvedBottomHits = pairwiseEvidenceState.enabled
    ? pairwiseHits?.bottomHits || []
    : usesRefProjection
      ? bottomSelection.role === "ref"
        ? buildProjectedRefSubviewHits(bottomCtg, topHits)
        : bottomHits
      : bottomHits;
  const topCtgName = resolveTrackCtgDisplayName(topCtg, topSelection.contigId);
  const bottomCtgName = resolveTrackCtgDisplayName(bottomCtg, bottomSelection.contigId);
  const topVisibleCtgName = resolveTrackCtgVisibleName(topCtg, topSelection.contigId);
  const bottomVisibleCtgName = resolveTrackCtgVisibleName(bottomCtg, bottomSelection.contigId);
  const subviewDomainSpanBp = Math.max(
    1,
    resolveSubviewCtgLengthBp(topCtg, resolvedTopHits),
    resolveSubviewCtgLengthBp(bottomCtg, resolvedBottomHits),
  );
  const subviewRenderInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: subviewDomainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: getMeasuredTrackViewportPx("subview"),
  });
  const refPairCacheKey = [
    buildSubviewRefCacheSelectionKey(summary),
    normalizeSupportDatasetId(resolveSubviewRefDatasetId(subview, supportContext)) || 0,
    normalizePositiveInt(resolvedTrackPrefs.alignmentLength) || 0,
    normalizeNonNegativeInt(resolvedTrackPrefs.mapq) || 0,
  ].join("|");
  const svgModel = buildSubviewAlignmentSvgModel({
    topCtg,
    bottomCtg,
    topHits: resolvedTopHits,
    bottomHits: resolvedBottomHits,
    pairCacheKey: refPairCacheKey,
    pairingMode: (usesRefProjection || pairwiseEvidenceState.enabled)
      ? "projection-key"
      : "reference-overlap",
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    topManualOffsetPx: resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      "top",
      topSelection.contigId,
      {
        domainSpanBp: subviewDomainSpanBp,
        innerWidth: subviewRenderInnerWidth,
      },
    ),
    bottomManualOffsetPx: resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      "bottom",
      bottomSelection.contigId,
      {
        domainSpanBp: subviewDomainSpanBp,
        innerWidth: subviewRenderInnerWidth,
      },
    ),
  });
  const topRowClass = resolveTrackToneClass(topSelection.role);
  const bottomRowClass = resolveTrackToneClass(bottomSelection.role);
  const connectorClass = topSelection.role === "support" ? " is-companion" : "";
  const bandTone = topSelection.role === "support" ? "companion" : "primary";
  const topLabelText = resolveTrackCtgLabelText(topCtg, topSelection.contigId);
  const bottomLabelText = resolveTrackCtgLabelText(bottomCtg, bottomSelection.contigId);
  const topLabelPlacement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: topLabelText,
    role: topSelection.role,
    rect: {
      x: svgModel.topBarX,
      width: svgModel.topBarWidth,
      centerX: svgModel.topBarX + (svgModel.topBarWidth / 2),
    },
    barY: svgModel.topBarY,
    barHeight: svgModel.barHeight,
    inlineTextOffsetY: svgModel.textOffsetY,
    hideOutsideLabel: true,
    minVisibleX: 0,
    maxVisibleX: svgModel.renderInnerWidth,
  });
  const bottomLabelPlacement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: bottomLabelText,
    role: bottomSelection.role,
    rect: {
      x: svgModel.bottomBarX,
      width: svgModel.bottomBarWidth,
      centerX: svgModel.bottomBarX + (svgModel.bottomBarWidth / 2),
    },
    barY: svgModel.bottomBarY,
    barHeight: svgModel.barHeight,
    inlineTextOffsetY: svgModel.textOffsetY,
    hideOutsideLabel: true,
    minVisibleX: 0,
    maxVisibleX: svgModel.renderInnerWidth,
  });
  const trackOrderButtonTopPx = ((Number(svgModel.topLabelTop) + Number(svgModel.bottomLabelTop)) / 2).toFixed(2);
  const activeAnchorKeys = buildSubviewActiveAnchorKeySet(subview?.activeAnchors);
  const topEndpointKey = buildSubviewAnchorEndpointKey({
    ...topSelection,
    role: topSelection.role,
    contigId: topSelection.contigId,
    datasetId: topCtg?.datasetId,
    isMirror: String(topCtg?.subviewSource || "") === "mirror",
    sourceKind: topCtg?.sourceKind,
  });
  const bottomEndpointKey = buildSubviewAnchorEndpointKey({
    ...bottomSelection,
    role: bottomSelection.role,
    contigId: bottomSelection.contigId,
    datasetId: bottomCtg?.datasetId,
    isMirror: String(bottomCtg?.subviewSource || "") === "mirror",
    sourceKind: bottomCtg?.sourceKind,
  });
  const evidenceAnchorEdges = (Array.isArray(svgModel.anchorEdges) ? svgModel.anchorEdges : []).map((edge) => ({
    ...edge,
    topEndpointKey,
    bottomEndpointKey,
    topLengthBp: svgModel.topLengthBp,
    bottomLengthBp: svgModel.bottomLengthBp,
    active: activeAnchorKeys.has(`${String(edge.hitKey || "").trim()}:${String(edge.edge || "").trim()}`),
  }));
  const manualAnchorEdges = buildSubviewManualAnchorEdges(subview?.manualAnchors, {
    topEndpoint: {
      endpointKey: topEndpointKey,
      contigId: topSelection.contigId,
      lengthBp: svgModel.topLengthBp,
      topY: svgModel.topBarY,
      bottomY: svgModel.topBarY + svgModel.barHeight,
      hitY: svgModel.topBarY + svgModel.barHeight,
      xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
        barX: svgModel.topBarX,
        barWidth: svgModel.topBarWidth,
        lengthBp: svgModel.topLengthBp,
        cutBp,
      }),
    },
    bottomEndpoint: {
      endpointKey: bottomEndpointKey,
      contigId: bottomSelection.contigId,
      lengthBp: svgModel.bottomLengthBp,
      topY: svgModel.bottomBarY,
      bottomY: svgModel.bottomBarY + svgModel.barHeight,
      hitY: svgModel.bottomBarY,
      xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
        barX: svgModel.bottomBarX,
        barWidth: svgModel.bottomBarWidth,
        lengthBp: svgModel.bottomLengthBp,
        cutBp,
      }),
    },
  });
  const anchorEdges = [...evidenceAnchorEdges, ...manualAnchorEdges];
  const activeAnchorCutsByContig = buildSubviewActiveAnchorCutsByContig(anchorEdges);
  const topFragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: topSelection.contigId,
      role: topSelection.role,
      lengthBp: svgModel.topLengthBp,
    },
    anchorCuts: activeAnchorCutsByContig.get(topSelection.contigId) || [],
  });
  const bottomFragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: bottomSelection.contigId,
      role: bottomSelection.role,
      lengthBp: svgModel.bottomLengthBp,
    },
    anchorCuts: activeAnchorCutsByContig.get(bottomSelection.contigId) || [],
  });
  const loadingOverlay = isPairwiseEvidenceLoading
    ? `<div class="subview-pairwise-loading-overlay" data-subview-pairwise-loading="1">
        <div class="subview-pairwise-loading-panel">
          <button type="button" class="subview-pairwise-loading-close" data-subview-pairwise-cancel="1" aria-label="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}" title="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}">&times;</button>
          <div class="subview-pairwise-loading-spinner" aria-hidden="true"></div>
          <p class="subview-pairwise-loading-text">${escapeHtml(i18n.subview.loadingPairwiseEvidence)}</p>
        </div>
      </div>`
    : "";
  const topCtgTitle = buildTrackCtgHoverTitle(topCtgName, {
    startBp: 0,
    lengthBp: svgModel.topLengthBp,
  });
  const bottomCtgTitle = buildTrackCtgHoverTitle(bottomCtgName, {
    startBp: 0,
    lengthBp: svgModel.bottomLengthBp,
  });
  return `
    <article class="assembly-track-panel subview-alignment-card">
      <div class="assembly-track-panel-head">
        <strong>${escapeHtml(`${topVisibleCtgName} vs ${bottomVisibleCtgName}`)}</strong>
        ${renderSubviewTrackInlineControls(resolvedTrackPrefs, i18n)}
      </div>
      <div class="assembly-track-layout subview-track-layout">
        <div class="assembly-track-label-column subview-track-label-column" style="width:${svgModel.labelColumnWidth}px;height:${svgModel.contentBottom}px">
          <div class="assembly-track-label-row${topRowClass}" style="top:${svgModel.topLabelTop}px" title="${escapeAttr(topCtgName)}">${escapeHtml(topVisibleCtgName)}</div>
          ${renderSubviewTrackOrderToggleButton({
            className: "is-in-label-column",
            style: `top:${trackOrderButtonTopPx}px`,
            swapTrackOrderLabel: i18n.subview.swapTrackOrderAria,
          })}
          <div class="assembly-track-label-row${bottomRowClass}" style="top:${svgModel.bottomLabelTop}px" title="${escapeAttr(bottomCtgName)}">${escapeHtml(bottomVisibleCtgName)}</div>
        </div>
        <div
          class="assembly-track-scroll subview-track-scroll"
          data-track-role="subview"
          data-subview-domain-span-bp="${svgModel.domainSpanBp}"
          data-subview-inner-width="${svgModel.renderInnerWidth}"
        >
          ${renderTrackBandCanvasLayer({
            sceneKind: "subview-ctg",
            width: svgModel.renderInnerWidth,
            height: svgModel.contentBottom,
            bands: svgModel.collinearityBands.map((band) => ({
              ...band,
              tone: bandTone,
            })),
          })}
          <div
            class="subview-band-tooltip is-hidden"
            data-subview-band-tooltip-delay-ms="${SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS}"
            aria-hidden="true"
          ></div>
          <svg class="assembly-track-svg subview-track-svg" width="${svgModel.renderInnerWidth}" height="${svgModel.contentBottom}" viewBox="0 0 ${svgModel.renderInnerWidth} ${svgModel.contentBottom}" preserveAspectRatio="xMinYMin meet">
            <line class="track-ruler-line" x1="0" y1="${svgModel.rulerTop}" x2="${svgModel.renderInnerWidth}" y2="${svgModel.rulerTop}" />
            ${renderSubviewVirtualRuler({
              windowStart: 0,
              windowEnd: svgModel.domainSpanBp,
              tickBp: svgModel.tickBp,
              innerWidth: svgModel.renderInnerWidth,
              domainSpanBp: svgModel.domainSpanBp,
              tickY1: svgModel.tickY1,
              tickY2: svgModel.tickY2,
              tickLabelY: svgModel.tickLabelY,
              edgeLabelPadding: 16,
            })}
            ${svgModel.collinearityBands
              .map(
                (band) => {
                  const hitKey = String(band.hitKey || "");
                  return `<polygon class="track-collinearity-band${connectorClass}" points="${band.points}" pointer-events="visibleFill" data-track-band-proxy="1" data-subview-top-contig-id="${topSelection.contigId}" data-subview-bottom-contig-id="${bottomSelection.contigId}" data-subview-band-tooltip="${escapeAttr(band.tooltipText)}" data-subview-hit-key="${escapeAttr(hitKey)}" data-subview-hit-left-active="${activeAnchorKeys.has(`${hitKey}:left`) ? "1" : "0"}" data-subview-hit-right-active="${activeAnchorKeys.has(`${hitKey}:right`) ? "1" : "0"}" />`;
                },
              )
              .join("")}
            <g
              class="subview-track-ctg-group${topRowClass}"
              data-subview-track-pair-role="${escapeAttr(topSelection.role)}"
              data-subview-track-pair-contig-id="${topSelection.contigId}"
              data-subview-track-pair-dataset-id="${Number(topCtg?.datasetId || 0)}"
              data-subview-track-pair-is-mirror="${String(topCtg?.subviewSource || "") === "mirror" ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${Number(topCtg?.phasedTrackId || 0)}"
              data-subview-track-pair-phased-track-item-id="${Number(topCtg?.phasedTrackItemId || 0)}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(topCtg?.phasedHaplotypeKey || "")}"
              data-subview-track-slot="top"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(topCtg))}"
              data-subview-track-role="${escapeAttr(topSelection.role)}"
              data-subview-contig-id="${topSelection.contigId}"
              data-subview-rect-x="${svgModel.topBarX.toFixed(2)}"
              data-subview-rect-y="${svgModel.topBarY.toFixed(2)}"
              data-subview-rect-width="${svgModel.topBarWidth.toFixed(2)}"
              data-subview-rect-height="${svgModel.barHeight}"
            >
              <title>${escapeHtml(topCtgTitle)}</title>
              <rect class="track-ctg subview-track-ctg${topRowClass}" x="${svgModel.topBarX.toFixed(2)}" y="${svgModel.topBarY.toFixed(2)}" width="${svgModel.topBarWidth.toFixed(2)}" height="${svgModel.barHeight}" rx="4" ry="4" pointer-events="all">
                <title>${escapeHtml(topCtgTitle)}</title>
              </rect>
              ${topFragments.length
                ? buildSubviewFragmentRects({
                    fragments: topFragments,
                    slot: "top",
                    role: topSelection.role,
                    barX: svgModel.topBarX,
                    barY: svgModel.topBarY,
                    barWidth: svgModel.topBarWidth,
                    barHeight: svgModel.barHeight,
                    ctgLengthBp: svgModel.topLengthBp,
                    ctgName: topCtgName,
                    contigId: topSelection.contigId,
                    datasetId: topCtg?.datasetId,
                    isMirror: String(topCtg?.subviewSource || "") === "mirror",
                    refOrient: resolveTrackCtgOrient(topCtg),
                    sourceKind: topCtg?.sourceKind,
                    referenceChrId: topCtg?.referenceChrId,
                    referenceChrName: topCtg?.referenceChrName,
                    segmentStartBp: topCtg?.segmentStartBp,
                    segmentEndBp: topCtg?.segmentEndBp,
                    phasedTrackId: topCtg?.phasedTrackId,
                    phasedTrackItemId: topCtg?.phasedTrackItemId,
                    phasedHaplotypeKey: topCtg?.phasedHaplotypeKey,
                  })
                : ""}
            </g>
            <g
              class="subview-track-ctg-group${bottomRowClass}"
              data-subview-track-pair-role="${escapeAttr(bottomSelection.role)}"
              data-subview-track-pair-contig-id="${bottomSelection.contigId}"
              data-subview-track-pair-dataset-id="${Number(bottomCtg?.datasetId || 0)}"
              data-subview-track-pair-is-mirror="${String(bottomCtg?.subviewSource || "") === "mirror" ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${Number(bottomCtg?.phasedTrackId || 0)}"
              data-subview-track-pair-phased-track-item-id="${Number(bottomCtg?.phasedTrackItemId || 0)}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(bottomCtg?.phasedHaplotypeKey || "")}"
              data-subview-track-slot="bottom"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(bottomCtg))}"
              data-subview-track-role="${escapeAttr(bottomSelection.role)}"
              data-subview-contig-id="${bottomSelection.contigId}"
              data-subview-rect-x="${svgModel.bottomBarX.toFixed(2)}"
              data-subview-rect-y="${svgModel.bottomBarY.toFixed(2)}"
              data-subview-rect-width="${svgModel.bottomBarWidth.toFixed(2)}"
              data-subview-rect-height="${svgModel.barHeight}"
            >
              <title>${escapeHtml(bottomCtgTitle)}</title>
              <rect class="track-ctg subview-track-ctg${bottomRowClass}" x="${svgModel.bottomBarX.toFixed(2)}" y="${svgModel.bottomBarY.toFixed(2)}" width="${svgModel.bottomBarWidth.toFixed(2)}" height="${svgModel.barHeight}" rx="4" ry="4" pointer-events="all">
                <title>${escapeHtml(bottomCtgTitle)}</title>
              </rect>
              ${bottomFragments.length
                ? buildSubviewFragmentRects({
                    fragments: bottomFragments,
                    slot: "bottom",
                    role: bottomSelection.role,
                    barX: svgModel.bottomBarX,
                    barY: svgModel.bottomBarY,
                    barWidth: svgModel.bottomBarWidth,
                    barHeight: svgModel.barHeight,
                    ctgLengthBp: svgModel.bottomLengthBp,
                    ctgName: bottomCtgName,
                    contigId: bottomSelection.contigId,
                    datasetId: bottomCtg?.datasetId,
                    isMirror: String(bottomCtg?.subviewSource || "") === "mirror",
                    refOrient: resolveTrackCtgOrient(bottomCtg),
                    sourceKind: bottomCtg?.sourceKind,
                    referenceChrId: bottomCtg?.referenceChrId,
                    referenceChrName: bottomCtg?.referenceChrName,
                    segmentStartBp: bottomCtg?.segmentStartBp,
                    segmentEndBp: bottomCtg?.segmentEndBp,
                    phasedTrackId: bottomCtg?.phasedTrackId,
                    phasedTrackItemId: bottomCtg?.phasedTrackItemId,
                    phasedHaplotypeKey: bottomCtg?.phasedHaplotypeKey,
                  })
                : ""}
            </g>
            ${renderSubviewAnchorLines(anchorEdges, {
              topY: svgModel.topBarY,
              bottomY: svgModel.bottomBarY + svgModel.barHeight,
            })}
            ${topLabelPlacement?.hidden
              ? ""
              : `<text class="track-ctg-label${topRowClass}${topLabelPlacement.classSuffix}" x="${topLabelPlacement.x.toFixed(2)}" y="${topLabelPlacement.y.toFixed(2)}"${topLabelPlacement.transformAttr} text-anchor="${topLabelPlacement.textAnchor}" data-subview-label-slot="top" data-subview-label-role="${escapeAttr(topSelection.role)}" data-subview-label-contig-id="${topSelection.contigId}">${escapeHtml(topLabelText)}</text>`}
            ${bottomLabelPlacement?.hidden
              ? ""
              : `<text class="track-ctg-label${bottomRowClass}${bottomLabelPlacement.classSuffix}" x="${bottomLabelPlacement.x.toFixed(2)}" y="${bottomLabelPlacement.y.toFixed(2)}"${bottomLabelPlacement.transformAttr} text-anchor="${bottomLabelPlacement.textAnchor}" data-subview-label-slot="bottom" data-subview-label-role="${escapeAttr(bottomSelection.role)}" data-subview-label-contig-id="${bottomSelection.contigId}">${escapeHtml(bottomLabelText)}</text>`}
          </svg>
        </div>
      </div>
      ${loadingOverlay}
    </article>
  `;
}

function renderSubviewTrackPairAlignmentCard(
  subview,
  supportContext,
  trackPrefs,
  subviewTrackDragOffsets = [],
  i18n,
) {
  const summary = subview?.summary || null;
  const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
  const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
  if (!topTrack || !bottomTrack) {
    return "";
  }
  const rawTopCtgs = resolveSubviewTrackSummaryCtgs(topTrack, supportContext) || [];
  const rawBottomCtgs = resolveSubviewTrackSummaryCtgs(bottomTrack, supportContext) || [];
  const pairwiseEvidenceState = resolveSubviewPairwiseEvidence(subview, summary, {
    topAssemblyCtgIds: rawTopCtgs.map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId)).filter(Boolean),
    bottomAssemblyCtgIds: rawBottomCtgs.map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId)).filter(Boolean),
  });
  const isPairwiseEvidenceLoading =
    pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loading";
  const flippedKeySet = buildSubviewFlippedCtgKeySet(subview?.flippedCtgs);
  const hiddenKeySet = new Set(
    normalizeSubviewTrackPairHiddenCtgs(subview?.trackPairHiddenCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const topCtgs = rawTopCtgs
    .filter((ctg) =>
      !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(topTrack.role, ctg?.assemblyCtgId)),
    )
    .map((ctg) => resolveSubviewRenderableContig(ctg, flippedKeySet, "top"));
  const bottomCtgs = rawBottomCtgs
    .filter((ctg) =>
      !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(bottomTrack.role, ctg?.assemblyCtgId)),
    )
    .map((ctg) => resolveSubviewRenderableContig(ctg, flippedKeySet, "bottom"));
  const resolvedTrackPrefs = resolveTrackPrefs(trackPrefs || {});
  const pairModel = buildDualTrackModel({
    primaryCtgs: bottomCtgs,
    companionCtgs: topCtgs,
    selectedPrimaryCtgId: null,
    selectedCompanionCtgId: null,
    prefs: resolvedTrackPrefs,
    preserveInputOrder: true,
  });
  const domainStart = Number(pairModel.windowStart || 0);
  const domainEnd = Math.max(domainStart, Number(pairModel.windowEnd || 0));
  const domainSpanBp = Math.max(1, domainEnd - domainStart + 1);
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_EMPTY_TEXT_OFFSET_Y = 12 * TRACK_HEIGHT_SCALE;
  const TRACK_MIN_ADJACENT_GAP_PX = 20;
  const LABEL_COLUMN_WIDTH_PX = 136;
  const baseInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: Math.max(1, Number(pairModel.innerWidth || getMeasuredTrackViewportPx("subview"))),
  });
  const topLayout = {
    id: "top",
    role: topTrack.role,
    source: topTrack.source,
    datasetId: topTrack.datasetId,
    isMirror: topTrack.isMirror === true,
    phasedTrackId: topTrack.phasedTrackId,
    haplotypeKey: topTrack.haplotypeKey,
    trackModel: pairModel.companion || buildEmptyTrackModelLike(),
    className: resolveTrackToneClass(topTrack.role).trim(),
    emptyMessage: i18n.trackControls.topTrackEmpty,
  };
  const bottomLayout = {
    id: "bottom",
    role: bottomTrack.role,
    source: bottomTrack.source,
    datasetId: bottomTrack.datasetId,
    isMirror: bottomTrack.isMirror === true,
    phasedTrackId: bottomTrack.phasedTrackId,
    haplotypeKey: bottomTrack.haplotypeKey,
    trackModel: pairModel.primary || buildEmptyTrackModelLike(),
    className: resolveTrackToneClass(bottomTrack.role).trim(),
    emptyMessage: i18n.trackControls.bottomTrackEmpty,
  };
  const rowLayouts = [topLayout, bottomLayout].map((layout) => ({
    ...layout,
    laneCount: Math.max(1, Number(layout.trackModel?.laneCount || 1)),
  }));

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  rowLayouts.forEach((layout, index) => {
    const rowHeight = layout.laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
    layout.rowTop = cursorY;
    layout.laneTop = cursorY + TRACK_ROW_PADDING_TOP;
    layout.labelTop = layout.laneTop - TRACK_LABEL_OFFSET_Y;
    layout.rowBottom = cursorY + rowHeight;
    cursorY += rowHeight + (index === rowLayouts.length - 1 ? 0 : TRACK_ROW_GAP);
  });
  const [resolvedTopLayout, resolvedBottomLayout] = rowLayouts;
  const contentBottom = cursorY;

  const tickBp = resolveTickBpFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    fallbackTickBp: resolvedTrackPrefs.tickBp,
  });
  const buildRectsForLayout = (layout) =>
    buildTrackRectsWithMinGap(layout.trackModel?.ctgs || [], {
      windowStart: domainStart,
      domainSpanBp,
      innerWidth: baseInnerWidth,
      minGapPx: TRACK_MIN_ADJACENT_GAP_PX,
    });
  const baseRectsByLayoutId = new Map(
    rowLayouts.map((layout) => [layout.id, buildRectsForLayout(layout)]),
  );
  const resolveLayoutSlot = (layoutId) => (layoutId === "top" ? "top" : "bottom");
  const resolveTrackPairDisplayRect = (layout, ctg, index) => {
    const baseRect = (baseRectsByLayoutId.get(layout.id) || [])[index] || buildTrackRect(ctg, {
      windowStart: domainStart,
      domainSpanBp,
      innerWidth: baseInnerWidth,
    });
    const offsetPx = resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      resolveLayoutSlot(layout.id),
      ctg?.assemblyCtgId,
      {
        domainSpanBp,
        innerWidth: baseInnerWidth,
      },
    );
    if (!Number.isFinite(offsetPx) || Math.abs(offsetPx) < 0.01) {
      return baseRect;
    }
    return {
      ...baseRect,
      x: roundTrackMetric(baseRect.x + offsetPx),
      centerX: roundTrackMetric(baseRect.centerX + offsetPx),
    };
  };
  const maxRectRight = Math.max(
    baseInnerWidth,
    ...rowLayouts
      .flatMap((layout) => (layout.trackModel?.ctgs || []).map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackPairDisplayRect(layout, ctg, index);
        return Number(rect.x) + Number(rect.width);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const minRectLeft = Math.min(
    0,
    ...rowLayouts
      .flatMap((layout) => (layout.trackModel?.ctgs || []).map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => Number(resolveTrackPairDisplayRect(layout, ctg, index).x))
      .filter((value) => Number.isFinite(value)),
  );
  const labelVisibleMinX = Math.floor(Math.min(0, minRectLeft));
  const labelVisibleMaxX = Math.ceil(Math.max(baseInnerWidth, maxRectRight));
  const maxLabelRight = rowLayouts.reduce((layoutMax, layout) => {
    return (layout.trackModel?.ctgs || []).reduce((ctgMax, ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMax;
      }
      const labelRight = resolveTrackCtgLabelRightBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.max(ctgMax, labelRight);
    }, layoutMax);
  }, baseInnerWidth);
  const minLabelLeft = rowLayouts.reduce((layoutMin, layout) => {
    return (layout.trackModel?.ctgs || []).reduce((ctgMin, ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMin;
      }
      const labelLeft = resolveTrackCtgLabelLeftBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.min(ctgMin, labelLeft);
    }, layoutMin);
  }, 0);
  const renderViewBoxMinX = Math.floor(Math.min(0, minRectLeft, minLabelLeft));
  const renderMaxX = Math.ceil(Math.max(baseInnerWidth, maxRectRight, maxLabelRight));
  const renderInnerWidth = Math.max(baseInnerWidth, renderMaxX - renderViewBoxMinX);
  const blockLength = Math.max(1, normalizePositiveInt(resolvedTrackPrefs.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(resolvedTrackPrefs.mapq) ?? 0);
  const refPairCacheKey = [
    buildSubviewRefCacheSelectionKey(summary),
    normalizeSupportDatasetId(resolveSubviewRefDatasetId(subview, supportContext)) || 0,
    normalizePositiveInt(resolvedTrackPrefs.alignmentLength) || 0,
    normalizeNonNegativeInt(resolvedTrackPrefs.mapq) || 0,
  ].join("|");
  const buildSegmentsForLayout = (layout) =>
    (layout.trackModel?.ctgs || []).flatMap((ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
      const barBottom = barTop + TRACK_BAR_HEIGHT;
      const endpointKey = buildSubviewAnchorEndpointKey({
        role: layout.role,
        contigId: ctg?.assemblyCtgId,
        datasetId: layout.datasetId,
        source: layout.source,
        isMirror: layout.isMirror === true,
        phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
        phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
        phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
      });
      return collectSubviewRenderableHits(ctg, { blockLength, minMapq }).map((hit) => {
        const hitRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: hit.ctgStart,
          ctgEndOffset: hit.ctgEnd,
        });
        return {
          ctgId: normalizeSupportDatasetId(ctg?.assemblyCtgId),
          ctgName: String(ctg?.name || ""),
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
          ),
          hitKey: String(hit?.hitKey || ""),
          pairKey: String(hit?.pairKey || hit?.hitKey || ""),
          ctgStart: hit.ctgStart,
          ctgEnd: hit.ctgEnd,
          refStart: hit.refStart,
          refEnd: hit.refEnd,
          refMid: hit.refMid,
          role: layout.role,
          datasetId: normalizeSupportDatasetId(layout.datasetId),
          isMirror: layout.isMirror === true,
          endpointKey,
          x: hitRect.x,
          width: hitRect.width,
          midX: hitRect.centerX,
          barTop,
          barBottom,
        };
      });
    });
  const buildLayoutEntryByCtgId = (layout) =>
    new Map(
      (layout.trackModel?.ctgs || [])
        .map((ctg, index) => {
          const ctgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (!ctgId) {
            return null;
          }
          const rect = resolveTrackPairDisplayRect(layout, ctg, index);
          const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
          const barBottom = barTop + TRACK_BAR_HEIGHT;
          const endpointKey = buildSubviewAnchorEndpointKey({
            role: layout.role,
            contigId: ctg?.assemblyCtgId,
            datasetId: layout.datasetId,
            source: layout.source,
            isMirror: layout.isMirror === true,
            phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
            phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
            phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
          });
          return [ctgId, { ctg, rect, barTop, barBottom, endpointKey }];
        })
        .filter(Boolean),
    );
  const buildPairwiseSegmentsForTrackPair = (evidence) => {
    const topEntriesByCtgId = buildLayoutEntryByCtgId(resolvedTopLayout);
    const bottomEntriesByCtgId = buildLayoutEntryByCtgId(resolvedBottomLayout);
    const topSegments = [];
    const bottomSegments = [];
    const hits = Array.isArray(evidence?.hits) ? evidence.hits : [];
    const renderedPairs = [];
    const pushRenderablePair = (pairRecord) => {
      const {
        topEntry,
        bottomEntry,
        topRange,
        bottomRange,
        hitKey,
        pairKey,
        reversed,
        ordinal,
      } = pairRecord;
      const refStart = ordinal + 1;
      const refEnd = ordinal + 2;
      const topRect = buildTrackHitRectWithinCtgDisplay({
        ctgRect: topEntry.rect,
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(topEntry.ctg?.lengthBp ?? topEntry.ctg?.totalLength) ?? 1,
        ),
        ctgStartOffset: Math.min(topRange.start, topRange.end),
        ctgEndOffset: Math.max(topRange.start, topRange.end),
      });
      const bottomRect = buildTrackHitRectWithinCtgDisplay({
        ctgRect: bottomEntry.rect,
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(bottomEntry.ctg?.lengthBp ?? bottomEntry.ctg?.totalLength) ?? 1,
        ),
        ctgStartOffset: Math.min(bottomRange.start, bottomRange.end),
        ctgEndOffset: Math.max(bottomRange.start, bottomRange.end),
      });
      topSegments.push({
        ctgId: normalizeSupportDatasetId(topEntry.ctg?.assemblyCtgId),
        ctgName: String(topEntry.ctg?.name || ""),
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(topEntry.ctg?.lengthBp ?? topEntry.ctg?.totalLength) ?? 1,
        ),
        hitKey,
        pairKey,
        reversed,
        ctgStart: Math.min(topRange.start, topRange.end),
        ctgEnd: Math.max(topRange.start, topRange.end),
        refStart,
        refEnd,
        refMid: (refStart + refEnd) / 2,
        role: resolvedTopLayout.role,
        datasetId: normalizeSupportDatasetId(resolvedTopLayout.datasetId),
        isMirror: resolvedTopLayout.isMirror === true,
        endpointKey: topEntry.endpointKey,
        x: topRect.x,
        width: topRect.width,
        midX: topRect.centerX,
        barTop: topEntry.barTop,
        barBottom: topEntry.barBottom,
      });
      bottomSegments.push({
        ctgId: normalizeSupportDatasetId(bottomEntry.ctg?.assemblyCtgId),
        ctgName: String(bottomEntry.ctg?.name || ""),
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(bottomEntry.ctg?.lengthBp ?? bottomEntry.ctg?.totalLength) ?? 1,
        ),
        hitKey,
        pairKey,
        reversed,
        ctgStart: Math.min(bottomRange.start, bottomRange.end),
        ctgEnd: Math.max(bottomRange.start, bottomRange.end),
        refStart,
        refEnd,
        refMid: (refStart + refEnd) / 2,
        role: resolvedBottomLayout.role,
        datasetId: normalizeSupportDatasetId(resolvedBottomLayout.datasetId),
        isMirror: resolvedBottomLayout.isMirror === true,
        endpointKey: bottomEntry.endpointKey,
        x: bottomRect.x,
        width: bottomRect.width,
        midX: bottomRect.centerX,
        barTop: bottomEntry.barTop,
        barBottom: bottomEntry.barBottom,
      });
    };
    hits.forEach((hit, index) => {
      const alignLength = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
      const mapq = Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
      if (alignLength < blockLength || mapq < minMapq) {
        return;
      }
      const queryAssemblyCtgId = normalizeSupportDatasetId(
        hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id,
      );
      const subjectAssemblyCtgId = normalizeSupportDatasetId(
        hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id,
      );
      const queryStart = Number(hit?.queryStart ?? hit?.query_start);
      const queryEnd = Number(hit?.queryEnd ?? hit?.query_end);
      const subjectStart = Number(hit?.subjectStart ?? hit?.subject_start);
      const subjectEnd = Number(hit?.subjectEnd ?? hit?.subject_end);
      if (
        !queryAssemblyCtgId
        || !subjectAssemblyCtgId
        || !Number.isFinite(queryStart)
        || !Number.isFinite(queryEnd)
        || !Number.isFinite(subjectStart)
        || !Number.isFinite(subjectEnd)
      ) {
        return;
      }
      let topEntry = topEntriesByCtgId.get(queryAssemblyCtgId) || null;
      let bottomEntry = bottomEntriesByCtgId.get(subjectAssemblyCtgId) || null;
      let topStart = queryStart;
      let topEnd = queryEnd;
      let bottomStart = subjectStart;
      let bottomEnd = subjectEnd;
      if (!topEntry || !bottomEntry) {
        topEntry = topEntriesByCtgId.get(subjectAssemblyCtgId) || null;
        bottomEntry = bottomEntriesByCtgId.get(queryAssemblyCtgId) || null;
        topStart = subjectStart;
        topEnd = subjectEnd;
        bottomStart = queryStart;
        bottomEnd = queryEnd;
      }
      if (!topEntry || !bottomEntry) {
        return;
      }
      const topMirrored = isSubviewPairwiseRangeMirrored(topEntry.ctg);
      const bottomMirrored = isSubviewPairwiseRangeMirrored(bottomEntry.ctg);
      const topRange = resolveSubviewPairwiseDisplayRange(topStart, topEnd, topEntry.ctg, topMirrored);
      const bottomRange = resolveSubviewPairwiseDisplayRange(
        bottomStart,
        bottomEnd,
        bottomEntry.ctg,
        bottomMirrored,
      );
      if (!topRange || !bottomRange) {
        return;
      }
      const hitKey = String(hit?.hitKey || `pairwise-track-${index + 1}`);
      const pairKey = String(hit?.pairKey || hitKey);
      const reversed = resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topMirrored, bottomMirrored);
      const sameContigHit = normalizeSupportDatasetId(topEntry.ctg?.assemblyCtgId)
        === normalizeSupportDatasetId(bottomEntry.ctg?.assemblyCtgId);
      if (sameContigHit) {
        return;
      }
      renderedPairs.push({
        topEntry,
        bottomEntry,
        topRange,
        bottomRange,
        hitKey,
        pairKey,
        reversed,
        index,
      });
    });
    renderedPairs.forEach((pairRecord) => {
      pushRenderablePair({
        ...pairRecord,
        ordinal: pairRecord.index,
      });
    });
    return { topSegments, bottomSegments };
  };
  const buildProjectedRefSegmentsForLayout = (layout, sourceSegments) => {
    const refEntries = (layout.trackModel?.ctgs || []).map((ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
      const barBottom = barTop + TRACK_BAR_HEIGHT;
      const bounds = resolveRefTrackSegmentBounds(ctg);
      const endpointKey = buildSubviewAnchorEndpointKey({
        role: layout.role,
        contigId: ctg?.assemblyCtgId,
        datasetId: layout.datasetId,
        source: layout.source,
        isMirror: layout.isMirror === true,
        phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
        phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
        phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
      });
      return {
        ctg,
        rect,
        barTop,
        barBottom,
        endpointKey,
        segmentStartBp: bounds.segmentStartBp,
        segmentEndBp: bounds.segmentEndBp,
      };
    });
    return (Array.isArray(sourceSegments) ? sourceSegments : [])
      .map((segment) => {
        const refEntry = refEntries.find(
          (entry) =>
            Number(segment?.refStart || 0) >= entry.segmentStartBp
            && Number(segment?.refEnd || 0) <= entry.segmentEndBp,
        );
        if (!refEntry) {
          return null;
        }
        const projectedRange = projectRefIntervalToLocalRange(
          refEntry.ctg,
          segment?.refStart,
          segment?.refEnd,
        );
        if (!projectedRange) {
          return null;
        }
        const hitRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: refEntry.rect,
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(refEntry.ctg?.lengthBp ?? refEntry.ctg?.totalLength) ?? 1,
          ),
          ctgStartOffset: projectedRange.ctgStart,
          ctgEndOffset: projectedRange.ctgEnd,
        });
        return {
          ctgId: normalizeSupportDatasetId(refEntry.ctg?.assemblyCtgId),
          ctgName: String(refEntry.ctg?.name || ""),
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(refEntry.ctg?.lengthBp ?? refEntry.ctg?.totalLength) ?? 1,
          ),
          hitKey: String(segment?.hitKey || ""),
          pairKey: String(segment?.pairKey || segment?.hitKey || ""),
          ctgStart: projectedRange.ctgStart,
          ctgEnd: projectedRange.ctgEnd,
          refStart: segment.refStart,
          refEnd: segment.refEnd,
          refMid: segment.refMid,
          role: layout.role,
          datasetId: normalizeSupportDatasetId(segment?.datasetId ?? null),
          isMirror: false,
          endpointKey: refEntry.endpointKey,
          x: hitRect.x,
          width: hitRect.width,
          midX: hitRect.centerX,
          barTop: refEntry.barTop,
          barBottom: refEntry.barBottom,
        };
      })
      .filter(Boolean);
  };
  const usesRefProjection =
    (resolvedTopLayout.role === "ref" && resolvedBottomLayout.role !== "ref")
    || (resolvedBottomLayout.role === "ref" && resolvedTopLayout.role !== "ref");
  const pairwiseTrackSegments = pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loaded"
    ? buildPairwiseSegmentsForTrackPair(pairwiseEvidenceState.evidence)
    : null;
  const sourceTopSegments = pairwiseEvidenceState.enabled
    ? (pairwiseTrackSegments?.topSegments || [])
    : resolvedTopLayout.role === "ref"
      ? []
      : buildSegmentsForLayout(resolvedTopLayout);
  const sourceBottomSegments = pairwiseEvidenceState.enabled
    ? (pairwiseTrackSegments?.bottomSegments || [])
    : resolvedBottomLayout.role === "ref"
      ? []
      : buildSegmentsForLayout(resolvedBottomLayout);
  const topSegments = usesRefProjection
    ? resolvedTopLayout.role === "ref"
      ? buildProjectedRefSegmentsForLayout(resolvedTopLayout, sourceBottomSegments)
      : sourceTopSegments
    : sourceTopSegments;
  const bottomSegments = usesRefProjection
    ? resolvedBottomLayout.role === "ref"
      ? buildProjectedRefSegmentsForLayout(resolvedBottomLayout, sourceTopSegments)
      : sourceBottomSegments
    : sourceBottomSegments;
  const buildOverlapRectWithinSegment = (segment, overlapStart, overlapEnd) => {
    const segmentRefStart = Number(segment?.refStart || 0);
    const segmentRefEnd = Number(segment?.refEnd || 0);
    const segmentX = Number(segment?.x || 0);
    const segmentWidth = Math.max(1, Number(segment?.width || 1));
    const segmentRight = segmentX + segmentWidth;
    const refSpan = Math.max(1, segmentRefEnd - segmentRefStart);
    const clampedStart = Math.max(segmentRefStart, Math.min(segmentRefEnd, Number(overlapStart || 0)));
    const clampedEnd = Math.max(segmentRefStart, Math.min(segmentRefEnd, Number(overlapEnd || 0)));
    const startRatio = Math.max(0, Math.min(1, (clampedStart - segmentRefStart) / refSpan));
    const endRatio = Math.max(startRatio, Math.min(1, (clampedEnd - segmentRefStart) / refSpan));
    const projectedLeft = segmentX + startRatio * segmentWidth;
    const projectedRight = segmentX + endRatio * segmentWidth;
    const x = Math.min(segmentRight, Math.max(segmentX, projectedLeft));
    const right = Math.min(segmentRight, Math.max(x, projectedRight));
    const width = Math.max(0, right - x);
    return {
      x,
      width,
      midX: x + width / 2,
    };
  };
  const activeAnchorKeys = buildSubviewActiveAnchorKeySet(subview?.activeAnchors);
  const pairedTrackSegments = pairRefSubviewSegmentsWithCache({
    cacheKey: refPairCacheKey,
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
    pairingMode: (usesRefProjection || pairwiseTrackSegments) ? "projection-key" : "reference-overlap",
  });
  const collinearityBands = pairedTrackSegments
    .map(({ topSegment, bottomSegment }, index) => {
      const overlapStart = Math.max(Number(topSegment.refStart || 0), Number(bottomSegment.refStart || 0));
      const overlapEnd = Math.min(Number(topSegment.refEnd || 0), Number(bottomSegment.refEnd || 0));
      if (!Number.isFinite(overlapStart) || !Number.isFinite(overlapEnd) || overlapEnd <= overlapStart) {
        return null;
      }
      const topOverlapRect = buildOverlapRectWithinSegment(topSegment, overlapStart, overlapEnd);
      const bottomOverlapRect = buildOverlapRectWithinSegment(bottomSegment, overlapStart, overlapEnd);
      const hitKey = buildSubviewTrackPairHitKey(topSegment, bottomSegment);
      const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
      const topLeftX = topOverlapRect.x;
      const topRightX = topOverlapRect.x + topOverlapRect.width;
      const bottomLeftX = bottomOverlapRect.x;
      const bottomRightX = bottomOverlapRect.x + bottomOverlapRect.width;
      return {
        hitKey,
        topContigId: topSegment.ctgId,
        bottomContigId: bottomSegment.ctgId,
        leftActive: activeAnchorKeys.has(`${hitKey}:left`),
        rightActive: activeAnchorKeys.has(`${hitKey}:right`),
        tooltipText: buildSubviewBandTooltipText({
          topName: topSegment.ctgName,
          bottomName: bottomSegment.ctgName,
          topSegment,
          bottomSegment,
        }),
        points: (reversed
          ? [
              `${topLeftX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${topRightX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${bottomLeftX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
              `${bottomRightX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
            ]
          : [
              `${topLeftX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${topRightX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${bottomRightX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
              `${bottomLeftX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
            ]).join(" "),
      };
    })
    .filter(Boolean);
  const anchorEdges = pairedTrackSegments
    .flatMap(({ topSegment, bottomSegment }, index) => {
      const overlapStart = Math.max(Number(topSegment.refStart || 0), Number(bottomSegment.refStart || 0));
      const overlapEnd = Math.min(Number(topSegment.refEnd || 0), Number(bottomSegment.refEnd || 0));
      if (!Number.isFinite(overlapStart) || !Number.isFinite(overlapEnd) || overlapEnd <= overlapStart) {
        return [];
      }
      const topOverlapRect = buildOverlapRectWithinSegment(topSegment, overlapStart, overlapEnd);
      const bottomOverlapRect = buildOverlapRectWithinSegment(bottomSegment, overlapStart, overlapEnd);
      const hitKey = buildSubviewTrackPairHitKey(topSegment, bottomSegment);
      const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
      const topLeftX = topOverlapRect.x;
      const topRightX = topOverlapRect.x + topOverlapRect.width;
      const bottomLeftX = bottomOverlapRect.x;
      const bottomRightX = bottomOverlapRect.x + bottomOverlapRect.width;
      const topLeftCutBp = resolveSubviewSegmentCtgBpByRef(topSegment, overlapStart);
      const topRightCutBp = resolveSubviewSegmentCtgBpByRef(topSegment, overlapEnd);
      const bottomLeftCutBp = resolveSubviewSegmentCtgBpByRef(bottomSegment, overlapStart);
      const bottomRightCutBp = resolveSubviewSegmentCtgBpByRef(bottomSegment, overlapEnd);
      return [
        {
          hitKey,
          edge: "left",
          topX: topLeftX,
          bottomX: reversed ? bottomRightX : bottomLeftX,
          topY: topSegment.barTop,
          bottomY: bottomSegment.barBottom,
          hitTopY: topSegment.barBottom,
          hitBottomY: bottomSegment.barTop,
          topContigId: topSegment.ctgId,
          bottomContigId: bottomSegment.ctgId,
          topEndpointKey: topSegment.endpointKey,
          bottomEndpointKey: bottomSegment.endpointKey,
          topCutBp: topLeftCutBp,
          bottomCutBp: reversed ? bottomRightCutBp : bottomLeftCutBp,
          topLengthBp: topSegment.ctgLengthBp,
          bottomLengthBp: bottomSegment.ctgLengthBp,
        },
        {
          hitKey,
          edge: "right",
          topX: topRightX,
          bottomX: reversed ? bottomLeftX : bottomRightX,
          topY: topSegment.barTop,
          bottomY: bottomSegment.barBottom,
          hitTopY: topSegment.barBottom,
          hitBottomY: bottomSegment.barTop,
          topContigId: topSegment.ctgId,
          bottomContigId: bottomSegment.ctgId,
          topEndpointKey: topSegment.endpointKey,
          bottomEndpointKey: bottomSegment.endpointKey,
          topCutBp: topRightCutBp,
          bottomCutBp: reversed ? bottomLeftCutBp : bottomRightCutBp,
          topLengthBp: topSegment.ctgLengthBp,
          bottomLengthBp: bottomSegment.ctgLengthBp,
        },
      ];
    })
    .map((edge) => ({
      ...edge,
      active: activeAnchorKeys.has(`${String(edge.hitKey || "").trim()}:${String(edge.edge || "").trim()}`),
    }));
  const buildManualEndpointMapForLayout = (layout) =>
    new Map(
      (layout.trackModel?.ctgs || [])
        .map((ctg, index) => {
          const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (!contigId) {
            return null;
          }
          const rect = resolveTrackPairDisplayRect(layout, ctg, index);
          const lengthBp = Math.max(1, normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1);
          const laneTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
          const endpointKey = buildSubviewAnchorEndpointKey({
            role: layout.role,
            contigId,
            datasetId: layout.datasetId,
            source: layout.source,
            isMirror: layout.isMirror === true,
            phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
            phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
            phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
          });
          if (!endpointKey) {
            return null;
          }
          return [endpointKey, {
            endpointKey,
            contigId,
            lengthBp,
            topY: laneTop,
            bottomY: laneTop + TRACK_BAR_HEIGHT,
            hitY: layout.id === "top" ? laneTop + TRACK_BAR_HEIGHT : laneTop,
            xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
              barX: rect.x,
              barWidth: rect.width,
              lengthBp,
              cutBp,
            }),
          }];
        })
        .filter(Boolean),
    );
  const manualAnchorEdges = buildSubviewManualAnchorEdgesFromEndpointMaps(subview?.manualAnchors, {
    topEndpointsByKey: buildManualEndpointMapForLayout(resolvedTopLayout),
    bottomEndpointsByKey: buildManualEndpointMapForLayout(resolvedBottomLayout),
  });
  const allAnchorEdges = [...anchorEdges, ...manualAnchorEdges];
  const activeAnchorCutsByContig = buildSubviewActiveAnchorCutsByContig(allAnchorEdges);
  const selectedTrackPairKeySet = new Set(
    normalizeSubviewTrackPairSelectionCtgs(subview?.trackPairSelectedCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const topTrackLabel = resolveSubviewTrackSelectionLabel(topTrack, supportContext, i18n);
  const bottomTrackLabel = resolveSubviewTrackSelectionLabel(bottomTrack, supportContext, i18n);
  const topRoleClass = resolveTrackToneClass(topTrack.role);
  const bottomRoleClass = resolveTrackToneClass(bottomTrack.role);
  const trackOrderButtonTopPx = (
    (Number(resolvedTopLayout.labelTop) + Number(resolvedBottomLayout.labelTop)) / 2
  ).toFixed(2);
  const bandClipId = "subview-track-band-clip";
  const bandClipInsetPx = 0.75;
  const bandClipTop = roundTrackMetric(
    resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT + bandClipInsetPx,
  );
  const bandClipBottom = roundTrackMetric(resolvedBottomLayout.laneTop - bandClipInsetPx);
  const bandClipHeight = Math.max(0, roundTrackMetric(bandClipBottom - bandClipTop));
  const loadingOverlay = isPairwiseEvidenceLoading
    ? `<div class="subview-pairwise-loading-overlay" data-subview-pairwise-loading="1">
        <div class="subview-pairwise-loading-panel">
          <button type="button" class="subview-pairwise-loading-close" data-subview-pairwise-cancel="1" aria-label="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}" title="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}">&times;</button>
          <div class="subview-pairwise-loading-spinner" aria-hidden="true"></div>
          <p class="subview-pairwise-loading-text">${escapeHtml(i18n.subview.loadingPairwiseEvidence)}</p>
        </div>
      </div>`
    : "";
  const renderTrackCtgs = (layout, roleClass) => {
    const ctgs = Array.isArray(layout.trackModel?.ctgs) ? layout.trackModel.ctgs : [];
    if (!ctgs.length) {
      return `<text class="track-row-empty-label" x="12" y="${(layout.laneTop + TRACK_EMPTY_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(layout.emptyMessage)}</text>`;
    }
    const renderEntries = ctgs
      .map((ctg, index) => {
        const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
        if (!contigId) {
          return null;
        }
        const rect = resolveTrackPairDisplayRect(layout, ctg, index);
        const y = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
        const displayName = resolveTrackCtgDisplayName(ctg, contigId);
        const labelText = resolveTrackCtgLabelText(ctg, contigId);
        const placement = resolveBoundedTrackCtgLabelPlacement({
          ctgName: labelText,
          role: layout.role,
          rect,
          barY: y,
          barHeight: TRACK_BAR_HEIGHT,
          inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
          hideOutsideLabel: true,
          minVisibleX: labelVisibleMinX,
          maxVisibleX: labelVisibleMaxX,
        });
        const selectedClass = selectedTrackPairKeySet.has(
          buildSubviewTrackPairHiddenCtgKey(layout.role, contigId),
        )
          ? " is-multi-selected"
          : "";
        const ctgLengthBp = Math.max(
          1,
          normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
        );
        const ctgTitle = buildTrackCtgHoverTitle(displayName, {
          startBp: ctg?.startBp,
          lengthBp: ctg?.lengthBp ?? ctg?.totalLength,
        });
        const fragments = deriveSubviewContigFragments({
          contig: {
            assemblyCtgId: contigId,
            role: layout.role,
            lengthBp: ctgLengthBp,
          },
          anchorCuts: activeAnchorCutsByContig.get(contigId) || [],
        });
        const trackPairDatasetId = layout.role === "support"
          ? (normalizeSupportDatasetId(layout.datasetId)
            || normalizeSupportDatasetId(supportContext?.supportDatasetId)
            || 0)
          : 0;
        const phasedTrackId = normalizeSupportDatasetId(ctg?.phasedTrackId);
        const phasedTrackItemId = normalizeSupportDatasetId(ctg?.phasedTrackItemId);
        const phasedHaplotypeKey = String(ctg?.phasedHaplotypeKey || "").trim();
        const labelMarkup = placement.hidden
          ? ""
          : `<text class="track-ctg-label${roleClass}${placement.classSuffix}" x="${placement.x.toFixed(2)}" y="${placement.y.toFixed(2)}"${placement.transformAttr} text-anchor="${placement.textAnchor}" data-subview-label-slot="${escapeAttr(resolveLayoutSlot(layout.id))}" data-subview-label-role="${escapeAttr(layout.role)}" data-subview-label-contig-id="${contigId}">${escapeHtml(labelText)}</text>`;
        return {
          ctg,
          rect,
          markup: `<g
              class="track-ctg-group${roleClass}${selectedClass}"
              data-subview-track-pair-role="${escapeAttr(layout.role)}"
              data-subview-track-pair-contig-id="${contigId}"
              data-subview-track-pair-dataset-id="${trackPairDatasetId}"
              data-subview-track-pair-is-mirror="${layout.isMirror ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${phasedTrackId || 0}"
              data-subview-track-pair-phased-track-item-id="${phasedTrackItemId || 0}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(ctg))}"
              data-subview-track-slot="${escapeAttr(resolveLayoutSlot(layout.id))}"
              data-subview-track-role="${escapeAttr(layout.role)}"
              data-subview-contig-id="${contigId}"
              data-subview-rect-x="${rect.x.toFixed(2)}"
              data-subview-rect-y="${y.toFixed(2)}"
              data-subview-rect-width="${rect.width.toFixed(2)}"
              data-subview-rect-height="${TRACK_BAR_HEIGHT}"
            >
              <title>${escapeHtml(ctgTitle)}</title>
              <rect
                class="track-ctg subview-track-ctg${roleClass}${selectedClass}"
                x="${rect.x.toFixed(2)}"
                y="${y.toFixed(2)}"
                width="${rect.width.toFixed(2)}"
                height="${TRACK_BAR_HEIGHT}"
                rx="4"
                ry="4"
                pointer-events="all"
              >
                <title>${escapeHtml(ctgTitle)}</title>
              </rect>
              ${fragments.length
                ? buildSubviewFragmentRects({
                    fragments,
                    slot: resolveLayoutSlot(layout.id),
                    role: layout.role,
                    barX: rect.x,
                    barY: y,
                    barWidth: rect.width,
                    barHeight: TRACK_BAR_HEIGHT,
                    ctgLengthBp,
                    ctgName: displayName,
                    contigId,
                    datasetId: trackPairDatasetId,
                    isMirror: layout.isMirror,
                    refOrient: resolveTrackCtgOrient(ctg),
                    sourceKind: ctg?.sourceKind,
                    referenceChrId: ctg?.referenceChrId,
                    referenceChrName: ctg?.referenceChrName,
                    segmentStartBp: ctg?.segmentStartBp,
                    segmentEndBp: ctg?.segmentEndBp,
                    ctgTitle,
                    phasedTrackId,
                    phasedTrackItemId,
                    phasedHaplotypeKey,
                  })
                : ""}
              ${labelMarkup}
            </g>`,
        };
      })
      .filter((entry) => entry && entry.markup);
    return sortTrackEntriesForRender(renderEntries)
      .map((entry) => entry.markup)
      .join("");
  };
  return `
    <article class="assembly-track-panel subview-alignment-card">
      <div class="assembly-track-panel-head">
        <strong>${escapeHtml(`${topTrackLabel} vs ${bottomTrackLabel}`)}</strong>
        ${renderSubviewTrackInlineControls(resolvedTrackPrefs, i18n)}
      </div>
      <div class="assembly-track-layout subview-track-layout">
        <div class="assembly-track-label-column subview-track-label-column" style="width:${LABEL_COLUMN_WIDTH_PX}px;height:${contentBottom}px">
          <div class="assembly-track-label-row${topRoleClass}" style="top:${resolvedTopLayout.labelTop}px">${escapeHtml(topTrackLabel)}</div>
          ${renderSubviewTrackOrderToggleButton({
            className: "is-in-label-column",
            style: `top:${trackOrderButtonTopPx}px`,
            swapTrackOrderLabel: i18n.subview.swapTrackOrderAria,
          })}
          <div class="assembly-track-label-row${bottomRoleClass}" style="top:${resolvedBottomLayout.labelTop}px">${escapeHtml(bottomTrackLabel)}</div>
        </div>
        <div class="assembly-track-scroll subview-track-scroll" data-track-role="subview" data-subview-domain-span-bp="${domainSpanBp}" data-subview-inner-width="${baseInnerWidth}" data-subview-viewbox-min-x="${renderViewBoxMinX}">
          ${renderTrackBandCanvasLayer({
            sceneKind: "subview-track-pair",
            width: renderInnerWidth,
            height: contentBottom,
            viewBoxMinX: renderViewBoxMinX,
            clipRect: {
              x: renderViewBoxMinX,
              y: bandClipTop,
              width: renderInnerWidth,
              height: bandClipHeight,
            },
            bands: collinearityBands.map((band) => ({
              ...band,
              tone: topTrack.role === "support" ? "companion" : "primary",
            })),
          })}
          <div class="subview-band-tooltip is-hidden" data-subview-band-tooltip-delay-ms="${SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS}" aria-hidden="true"></div>
          <svg class="assembly-track-svg subview-track-svg" width="${renderInnerWidth}" height="${contentBottom}" viewBox="${renderViewBoxMinX} 0 ${renderInnerWidth} ${contentBottom}" preserveAspectRatio="xMinYMin meet">
            <defs>
              <clipPath id="${bandClipId}" clipPathUnits="userSpaceOnUse">
                <rect x="${renderViewBoxMinX.toFixed(2)}" y="${bandClipTop.toFixed(2)}" width="${renderInnerWidth.toFixed(2)}" height="${bandClipHeight.toFixed(2)}" />
              </clipPath>
            </defs>
            <line class="track-ruler-line" x1="0" y1="${rulerTop}" x2="${baseInnerWidth}" y2="${rulerTop}" />
            ${renderSubviewVirtualRuler({
              windowStart: domainStart,
              windowEnd: domainEnd,
              tickBp,
              innerWidth: baseInnerWidth,
              domainSpanBp,
              tickY1: rulerTop + TRACK_LABEL_OFFSET_Y,
              tickY2: contentBottom - 3 * TRACK_HEIGHT_SCALE,
              tickLabelY: rulerTop - TRACK_LABEL_OFFSET_Y,
              edgeLabelPadding: TRACK_EDGE_LABEL_PADDING,
            })}
            <g clip-path="url(#${bandClipId})">
              ${collinearityBands
                .map(
                  (band) =>
                  `<polygon class="track-collinearity-band${topRoleClass}" points="${band.points}" pointer-events="visibleFill" data-track-band-proxy="1" data-subview-top-contig-id="${band.topContigId}" data-subview-bottom-contig-id="${band.bottomContigId}" data-subview-band-tooltip="${escapeAttr(band.tooltipText)}" data-subview-hit-key="${escapeAttr(band.hitKey)}" data-subview-hit-left-active="${band.leftActive ? "1" : "0"}" data-subview-hit-right-active="${band.rightActive ? "1" : "0"}" />`,
                )
                .join("")}
            </g>
            ${renderTrackCtgs(resolvedTopLayout, topRoleClass)}
            ${renderTrackCtgs(resolvedBottomLayout, bottomRoleClass)}
            ${renderSubviewAnchorLines(allAnchorEdges, {
              topY: resolvedTopLayout.laneTop,
              bottomY: resolvedBottomLayout.laneTop + TRACK_BAR_HEIGHT,
            })}
          </svg>
        </div>
      </div>
      ${loadingOverlay}
    </article>
  `;
}

function collectSubviewRenderableHits(ctg, { blockLength, minMapq, preserveHitKeys = null }) {
  const hits = Array.isArray(ctg?.hits) ? ctg.hits : [];
  const preserved = preserveHitKeys instanceof Set ? preserveHitKeys : new Set(preserveHitKeys || []);
  return hits
    .map((hit, index) => {
      const hitBlockLength = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
      const hitMapq = resolveHitMapq(hit);
      const refStart = Number(hit?.refStart ?? hit?.ref_start);
      const refEnd = Number(hit?.refEnd ?? hit?.ref_end);
      const ctgStart = Number(
        hit?.ctgStart
        ?? hit?.ctg_start
        ?? hit?.queryStart
        ?? hit?.query_start
        ?? hit?.hitStart
        ?? hit?.hit_start,
      );
      const ctgEnd = Number(
        hit?.ctgEnd
        ?? hit?.ctg_end
        ?? hit?.queryEnd
        ?? hit?.query_end
        ?? hit?.hitEnd
        ?? hit?.hit_end,
      );
      if (
        (!preserved.has(`hit-${index + 1}`) && hitBlockLength < blockLength) ||
        (!preserved.has(`hit-${index + 1}`) && hitMapq < minMapq)
      ) {
        return null;
      }
      if (
        !Number.isFinite(ctgStart)
        || !Number.isFinite(ctgEnd)
        || !Number.isFinite(refStart)
        || !Number.isFinite(refEnd)
      ) {
        return null;
      }
      const normalizedRefStart = Math.min(refStart, refEnd);
      const normalizedRefEnd = Math.max(refStart, refEnd);
      return {
        hitKey: `hit-${index + 1}`,
        pairKey: String(hit?.pairKey || `hit-${index + 1}`),
        ctgStart: Math.min(ctgStart, ctgEnd),
        ctgEnd: Math.max(ctgStart, ctgEnd),
        refStart: normalizedRefStart,
        refEnd: normalizedRefEnd,
        refMid: (normalizedRefStart + normalizedRefEnd) / 2,
      };
    })
    .filter(Boolean);
}

function buildSubviewAlignmentSvgModel({
  topCtg,
  bottomCtg,
  topHits,
  bottomHits,
  pairCacheKey = "",
  pairingMode = "reference-overlap",
  minTickUnitKb,
  maxTickCount,
  topManualOffsetPx = 0,
  bottomManualOffsetPx = 0,
}) {
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const TRACK_TAIL_PADDING = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_MIN_DRAG_VISIBLE_PX = 24;
  const LABEL_COLUMN_WIDTH_PX = 136;

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  const rowHeight = TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
  const topBarY = cursorY + TRACK_ROW_PADDING_TOP;
  const topLabelTop = topBarY;
  cursorY += rowHeight + TRACK_ROW_GAP;
  const bottomBarY = cursorY + TRACK_ROW_PADDING_TOP;
  const bottomLabelTop = bottomBarY;
  cursorY += rowHeight + TRACK_TAIL_PADDING;
  const contentBottom = cursorY;

  const safeMinTickUnitKb = Math.max(1, normalizePositiveInt(minTickUnitKb) ?? 1);
  const safeMaxTickCount = Math.max(1, normalizePositiveInt(maxTickCount) ?? 10);
  const topLengthBp = resolveSubviewCtgLengthBp(topCtg, topHits);
  const bottomLengthBp = resolveSubviewCtgLengthBp(bottomCtg, bottomHits);
  const domainStart = 0;
  const domainEnd = Math.max(topLengthBp, bottomLengthBp);
  const domainSpan = Math.max(1, domainEnd - domainStart);
  const renderInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: domainSpan,
    minTickUnitKb: safeMinTickUnitKb,
    maxTickCount: safeMaxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: getMeasuredTrackViewportPx("subview"),
  });
  const tickBp = resolveTickBpFromScale({
    domainSpanBp: domainSpan,
    minTickUnitKb: safeMinTickUnitKb,
    maxTickCount: safeMaxTickCount,
    fallbackTickBp: safeMinTickUnitKb * 1000,
  });
  const toX = (bpValue) =>
    (Math.max(0, Math.min(domainEnd, Number(bpValue) || 0)) / domainSpan) * Math.max(1, renderInnerWidth);
  const topBarWidth = toX(topLengthBp);
  const bottomBarWidth = toX(bottomLengthBp);
  const toSegments = (hits, trackOffsetBp = 0) =>
    hits.map((hit) => {
      const x1 = toX((Number(hit.ctgStart) || 0) + trackOffsetBp);
      const x2 = toX((Number(hit.ctgEnd) || 0) + trackOffsetBp);
      return {
        hitKey: String(hit?.hitKey || ""),
        pairKey: String(hit?.pairKey || hit?.hitKey || ""),
        reversed: hit?.reversed === true,
        ctgStart: Math.min(Number(hit.ctgStart) || 0, Number(hit.ctgEnd) || 0),
        ctgEnd: Math.max(Number(hit.ctgStart) || 0, Number(hit.ctgEnd) || 0),
        x: Math.min(x1, x2),
        width: Math.max(1, Math.abs(x2 - x1)),
        midX: (x1 + x2) / 2,
        refStart: Math.min(Number(hit.refStart) || 0, Number(hit.refEnd) || 0),
        refEnd: Math.max(Number(hit.refStart) || 0, Number(hit.refEnd) || 0),
        refMid: Number(hit.refMid || 0),
      };
    });
  const baseTopSegments = toSegments(topHits).sort((left, right) => left.refMid - right.refMid);
  const baseBottomSegments = toSegments(bottomHits).sort(
    (left, right) => left.refMid - right.refMid,
  );
  const baseSegmentPairs = pairRefSubviewSegmentsWithCache({
    cacheKey: `${pairCacheKey}:base`,
    topSegments: baseTopSegments,
    bottomSegments: baseBottomSegments,
    trackMode: "2-contig",
    pairingMode,
  });
  const { topOffsetBp, bottomOffsetBp } = resolveSubviewAutoTrackOffsets({
    topLengthBp,
    bottomLengthBp,
    domainEnd,
    segmentPairs: baseSegmentPairs,
  });
  const topBarBaseX = toX(topOffsetBp);
  const bottomBarBaseX = toX(bottomOffsetBp);
  const resolveClampedManualOffsetPx = (requestedOffsetPx, barBaseX, barWidth) => {
    const numeric = Number(requestedOffsetPx || 0);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    const minOffset = -barBaseX;
    const maxOffset = Math.max(0, renderInnerWidth - (barBaseX + barWidth));
    if (maxOffset - minOffset > 0.01) {
      return roundTrackMetric(Math.min(Math.max(numeric, minOffset), maxOffset));
    }
    const minVisiblePx = Math.min(Math.max(3, Number(barWidth) || 0), TRACK_MIN_DRAG_VISIBLE_PX);
    const relaxedMinOffset = minVisiblePx - (barBaseX + barWidth);
    const relaxedMaxOffset = renderInnerWidth - minVisiblePx - barBaseX;
    if (relaxedMaxOffset < relaxedMinOffset) {
      return 0;
    }
    return roundTrackMetric(Math.min(Math.max(numeric, relaxedMinOffset), relaxedMaxOffset));
  };
  const resolvedTopManualOffsetPx = resolveClampedManualOffsetPx(topManualOffsetPx, topBarBaseX, topBarWidth);
  const resolvedBottomManualOffsetPx = resolveClampedManualOffsetPx(bottomManualOffsetPx, bottomBarBaseX, bottomBarWidth);
  const topBarX = roundTrackMetric(topBarBaseX + resolvedTopManualOffsetPx);
  const bottomBarX = roundTrackMetric(bottomBarBaseX + resolvedBottomManualOffsetPx);
  const topSegments = toSegments(topHits, topOffsetBp).sort((left, right) => left.refMid - right.refMid);
  const bottomSegments = toSegments(bottomHits, bottomOffsetBp).sort(
    (left, right) => left.refMid - right.refMid,
  );
  const shiftedTopSegments = topSegments.map((segment) => ({
    ...segment,
    x: roundTrackMetric(segment.x + resolvedTopManualOffsetPx),
    midX: roundTrackMetric(segment.midX + resolvedTopManualOffsetPx),
  }));
  const shiftedBottomSegments = bottomSegments.map((segment) => ({
    ...segment,
    x: roundTrackMetric(segment.x + resolvedBottomManualOffsetPx),
    midX: roundTrackMetric(segment.midX + resolvedBottomManualOffsetPx),
  }));
  const segmentPairs = pairRefSubviewSegmentsWithCache({
    cacheKey: `${pairCacheKey}:shifted`,
    topSegments: shiftedTopSegments,
    bottomSegments: shiftedBottomSegments,
    trackMode: "2-contig",
    pairingMode,
  });
  const collinearityBands = segmentPairs.map(({ topSegment, bottomSegment }) => {
    const topStartX = topSegment.x;
    const topEndX = topSegment.x + topSegment.width;
    const bottomStartX = bottomSegment.x;
    const bottomEndX = bottomSegment.x + bottomSegment.width;
    const hitKey = String(topSegment?.hitKey || bottomSegment?.hitKey || "");
    const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
    return {
      hitKey,
      tooltipText: buildSubviewBandTooltipText({
        topName: String(topCtg?.name || ""),
        bottomName: String(bottomCtg?.name || ""),
        topSegment,
        bottomSegment,
      }),
      points: (reversed
        ? [
            `${topStartX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${topEndX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${bottomStartX.toFixed(2)},${bottomBarY.toFixed(2)}`,
            `${bottomEndX.toFixed(2)},${bottomBarY.toFixed(2)}`,
          ]
        : [
            `${topStartX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${topEndX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${bottomEndX.toFixed(2)},${bottomBarY.toFixed(2)}`,
            `${bottomStartX.toFixed(2)},${bottomBarY.toFixed(2)}`,
          ]).join(" "),
    };
  });
  const anchorEdges = segmentPairs.flatMap(({ topSegment, bottomSegment }, index) => {
    const hitKey = String(topSegment?.hitKey || bottomSegment?.hitKey || `hit-${index + 1}`);
    const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
    return [
      {
        hitKey,
        edge: "left",
        topX: topSegment.x,
        bottomX: reversed ? bottomSegment.x + bottomSegment.width : bottomSegment.x,
        topY: topBarY,
        bottomY: bottomBarY + TRACK_BAR_HEIGHT,
        hitTopY: topBarY + TRACK_BAR_HEIGHT,
        hitBottomY: bottomBarY,
        topContigId: normalizeSupportDatasetId(topCtg?.assemblyCtgId),
        bottomContigId: normalizeSupportDatasetId(bottomCtg?.assemblyCtgId),
        topCutBp: topSegment.ctgStart,
        bottomCutBp: reversed ? bottomSegment.ctgEnd : bottomSegment.ctgStart,
      },
      {
        hitKey,
        edge: "right",
        topX: topSegment.x + topSegment.width,
        bottomX: reversed ? bottomSegment.x : bottomSegment.x + bottomSegment.width,
        topY: topBarY,
        bottomY: bottomBarY + TRACK_BAR_HEIGHT,
        hitTopY: topBarY + TRACK_BAR_HEIGHT,
        hitBottomY: bottomBarY,
        topContigId: normalizeSupportDatasetId(topCtg?.assemblyCtgId),
        bottomContigId: normalizeSupportDatasetId(bottomCtg?.assemblyCtgId),
        topCutBp: topSegment.ctgEnd,
        bottomCutBp: reversed ? bottomSegment.ctgStart : bottomSegment.ctgEnd,
      },
    ];
  });
  return {
    labelColumnWidth: LABEL_COLUMN_WIDTH_PX,
    contentBottom,
    domainSpanBp: domainSpan,
    renderInnerWidth,
    rulerTop,
    tickY1: rulerTop + TRACK_LABEL_OFFSET_Y,
    tickY2: contentBottom - 3 * TRACK_HEIGHT_SCALE,
    tickLabelY: rulerTop - TRACK_LABEL_OFFSET_Y,
    tickBp,
    topBarY,
    bottomBarY,
    topBarX,
    bottomBarX,
    topBarWidth,
    bottomBarWidth,
    topLabelTop,
    bottomLabelTop,
    barHeight: TRACK_BAR_HEIGHT,
    textOffsetY: TRACK_TEXT_OFFSET_Y,
    collinearityBands,
    anchorEdges,
    topLengthBp,
    bottomLengthBp,
  };
}

function buildSubviewBandTooltipText({ topName, bottomName, topSegment, bottomSegment }) {
  const resolvedTopName = String(topName || "Top");
  const resolvedBottomName = String(bottomName || "Bottom");
  return [
    `${resolvedTopName}: ${formatBpInterval(topSegment?.ctgStart, topSegment?.ctgEnd)}`,
    `${resolvedBottomName}: ${formatBpInterval(bottomSegment?.ctgStart, bottomSegment?.ctgEnd)}`,
  ].join(" | ");
}

function buildSubviewTrackPairHitKey(topSegment, bottomSegment) {
  const topContigId = normalizeSupportDatasetId(topSegment?.ctgId) || 0;
  const bottomContigId = normalizeSupportDatasetId(bottomSegment?.ctgId) || 0;
  const topHitKey = String(topSegment?.hitKey || "").trim();
  const bottomHitKey = String(bottomSegment?.hitKey || "").trim();
  return `pair:${topContigId}:${topHitKey}:${bottomContigId}:${bottomHitKey}`;
}

function resolveSubviewCtgLengthBp(ctg, hits) {
  const candidates = [
    ctg?.totalLength,
    ctg?.lengthBp,
    ctg?.length,
  ];
  for (const candidate of candidates) {
    const parsed = normalizePositiveInt(candidate);
    if (parsed && parsed > 0) {
      return parsed;
    }
  }
  const fallbackHitEnd = (Array.isArray(hits) ? hits : []).reduce((maxValue, hit) => {
    const hitEnd = Number(hit?.ctgEnd);
    if (!Number.isFinite(hitEnd)) {
      return maxValue;
    }
    return Math.max(maxValue, hitEnd);
  }, 0);
  return Math.max(1, fallbackHitEnd || 1);
}

  return {
    renderSubviewSelectionPanel,
    renderTrackBandCanvasLayer,
    resolveTrackHitDisplayReversed,
    resolveTrackRenderableHits,
  };
}
